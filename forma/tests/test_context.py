"""
Tests for intervals.core.context — the orchestration layer that threads
shared scaffold parameters (key, mode, arc, density, section boundaries,
total section count) to every voice within a section, while keeping each
voice's own generated output (VoiceSnapshot) isolated from voices that
haven't generated yet or that live in a different section.

Two properties this task specifically asks to lock in:
  1. Scaffold sharing works: every SectionContext built from the same
     PieceContext for the same piece sees the same key/mode/total_sections,
     and correctly picks up each section's own arc/density from that
     section's own dict.
  2. Per-voice state does NOT leak: one voice's VoiceSnapshot (pitches,
     contour, etc.) is invisible to a different SectionContext instance,
     invisible to a voice slot that hasn't been written yet, and adding
     one voice's snapshot never mutates another voice's already-stored
     snapshot in the same section.
"""
import pytest

from intervals.core.context import (
    PieceContext,
    SectionContext,
    SectionSummary,
    VoiceSnapshot,
    compute_contour,
    compute_rhythmic_profile,
    compute_voice_snapshot,
)


# ===========================================================================
# Scaffold sharing — SectionContext construction from PieceContext
# ===========================================================================

class TestScaffoldSharing:
    def test_piece_level_key_and_mode_thread_into_every_section(self):
        """key/mode/total_sections are piece-wide scaffold: every section
        built from the same PieceContext must see identical values,
        regardless of that section's own content."""
        piece_ctx = PieceContext(total_sections=3, key="D", mode="dorian")

        ctx0 = piece_ctx.make_section_context({"name": "intro"}, 0)
        ctx1 = piece_ctx.make_section_context({"name": "verse"}, 1)
        ctx2 = piece_ctx.make_section_context({"name": "outro"}, 2)

        for ctx in (ctx0, ctx1, ctx2):
            assert ctx.key == "D"
            assert ctx.mode == "dorian"
            assert ctx.total_sections == 3

    def test_each_section_picks_up_its_own_arc_and_density(self):
        """arc/density come from each section's OWN dict, not shared or
        averaged across sections -- confirms scaffold-sharing doesn't
        overreach into per-section content."""
        piece_ctx = PieceContext(total_sections=2, key="C", mode="ionian")
        sec0 = {"name": "intro", "arc": "build", "density": "sparse"}
        sec1 = {"name": "verse", "arc": "swell", "density": "medium"}

        ctx0 = piece_ctx.make_section_context(sec0, 0)
        ctx1 = piece_ctx.make_section_context(sec1, 1)

        assert (ctx0.arc, ctx0.density) == ("build", "sparse")
        assert (ctx1.arc, ctx1.density) == ("swell", "medium")

    def test_missing_arc_density_fall_back_to_scaffold_defaults(self):
        piece_ctx = PieceContext(total_sections=1)
        ctx = piece_ctx.make_section_context({"name": "bare"}, 0)
        assert ctx.arc == "swell"
        assert ctx.density == "medium"

    def test_section_index_and_form_position_thread_correctly(self):
        piece_ctx = PieceContext(total_sections=4)
        ctx = piece_ctx.make_section_context({"name": "third"}, 2)
        assert ctx.section_index == 2
        assert ctx.total_sections == 4
        assert ctx.form_position == pytest.approx(2 / 3)  # 2 / (4-1)


# ===========================================================================
# Per-voice state does NOT leak
# ===========================================================================

class TestVoiceStateDoesNotLeak:
    def test_a_voice_not_yet_generated_reads_as_none(self):
        ctx = SectionContext(section_name="verse")
        assert ctx.melody is None
        assert ctx.bass is None
        assert ctx.get_voice("counterpoint") is None

    def test_two_separate_section_contexts_do_not_share_voice_state(self):
        """The exact leak this task asks to rule out: one section's bass
        snapshot must not appear in a different section's context, even
        though both were built from the same PieceContext."""
        piece_ctx = PieceContext(total_sections=2, key="C", mode="ionian")
        ctx0 = piece_ctx.make_section_context({"name": "intro"}, 0)
        ctx1 = piece_ctx.make_section_context({"name": "verse"}, 1)

        ctx0.add_voice("bass", VoiceSnapshot(last_pitch=38))

        assert ctx0.bass is not None
        assert ctx1.bass is None  # not leaked from ctx0

    def test_adding_one_voice_does_not_mutate_another_already_stored(self):
        """Confirms the per-voice dict entries are independent objects --
        writing melody's snapshot must not alter bass's already-stored
        snapshot in any way (pitch, contour, or otherwise)."""
        ctx = SectionContext(section_name="verse")
        bass_snap = VoiceSnapshot(last_pitch=38, pitch_center=40.0,
                                   ending_contour="static")
        ctx.add_voice("bass", bass_snap)

        ctx.add_voice("melody", VoiceSnapshot(last_pitch=79, pitch_center=72.0,
                                               ending_contour="ascending"))

        assert ctx.bass.last_pitch == 38
        assert ctx.bass.pitch_center == 40.0
        assert ctx.bass.ending_contour == "static"
        # Melody's very different pitch data hasn't bled into bass's:
        assert ctx.bass.last_pitch != ctx.melody.last_pitch
        assert ctx.bass.ending_contour != ctx.melody.ending_contour

    def test_re_adding_a_voice_overwrites_only_that_voice(self):
        ctx = SectionContext(section_name="verse")
        ctx.add_voice("bass", VoiceSnapshot(last_pitch=38))
        ctx.add_voice("melody", VoiceSnapshot(last_pitch=79))

        ctx.add_voice("bass", VoiceSnapshot(last_pitch=41))  # bass revises its snapshot

        assert ctx.bass.last_pitch == 41
        assert ctx.melody.last_pitch == 79  # untouched by bass's update

    def test_frozen_section_summary_is_a_separate_copy_not_a_live_view(self):
        """SectionSummary.from_section_context takes a shallow copy of the
        voices dict -- mutating the live SectionContext afterward must
        not retroactively change the frozen summary."""
        ctx = SectionContext(section_name="verse")
        ctx.add_voice("bass", VoiceSnapshot(last_pitch=38))
        summary = SectionSummary.from_section_context(ctx)

        ctx.add_voice("bass", VoiceSnapshot(last_pitch=99))  # mutate after freezing
        ctx.add_voice("melody", VoiceSnapshot(last_pitch=72))  # add a new voice after freezing

        assert summary.voices["bass"].last_pitch == 38  # frozen value, unaffected
        assert "melody" not in summary.voices          # new voice not retroactively added


# ===========================================================================
# Cross-section memory (PieceContext) — isolation across section boundaries
# ===========================================================================

class TestCrossSectionMemoryIsolation:
    def test_previous_melody_and_previous_bass_are_independently_tracked(self):
        piece_ctx = PieceContext(total_sections=2, key="D", mode="dorian")
        ctx0 = piece_ctx.make_section_context({"name": "intro"}, 0)
        ctx0.add_voice("bass", VoiceSnapshot(last_pitch=38, ending_contour="static"))
        ctx0.add_voice("melody", VoiceSnapshot(last_pitch=67, ending_contour="ascending"))
        piece_ctx.complete_section(ctx0)

        assert piece_ctx.previous_bass.last_pitch == 38
        assert piece_ctx.previous_melody.last_pitch == 67
        # Not accidentally swapped or merged:
        assert piece_ctx.previous_bass.ending_contour == "static"
        assert piece_ctx.previous_melody.ending_contour == "ascending"

    def test_no_completed_sections_yields_none_not_a_crash(self):
        piece_ctx = PieceContext(total_sections=3)
        assert piece_ctx.previous_section is None
        assert piece_ctx.previous_melody is None
        assert piece_ctx.previous_bass is None

    def test_only_the_most_recent_section_is_visible_as_previous(self):
        piece_ctx = PieceContext(total_sections=3)
        for i, pitch in enumerate([60, 65, 70]):
            ctx = piece_ctx.make_section_context({"name": f"sec{i}"}, i)
            ctx.add_voice("melody", VoiceSnapshot(last_pitch=pitch))
            piece_ctx.complete_section(ctx)
        # After three completed sections, "previous" is the third (70), not
        # the first or second -- old section data doesn't leak forward
        # past the section that actually replaced it.
        assert piece_ctx.previous_melody.last_pitch == 70

    def test_transform_history_only_records_voices_that_reported_one(self):
        piece_ctx = PieceContext(total_sections=1)
        ctx = piece_ctx.make_section_context({"name": "verse"}, 0)
        ctx.add_voice("bass", VoiceSnapshot(last_pitch=38))  # no transform reported
        ctx.add_voice("melody", VoiceSnapshot(last_pitch=67, last_transform="inversion"))
        piece_ctx.complete_section(ctx)
        assert piece_ctx.transform_history == ["inversion"]


# ===========================================================================
# suggest_transform — instance-level RNG isolation
# ===========================================================================

class TestSuggestTransformIsolation:
    def test_reproducible_with_same_seed_across_separate_instances(self):
        """The RNG lives on the PieceContext instance, not module/global
        state -- two separate PieceContexts with the same seed must
        produce identical sequences, and (implicitly) mustn't interfere
        with each other's draws."""
        pool = ["inversion", "retrograde", "augmentation"]
        pc_a = PieceContext(total_sections=4, seed=99)
        pc_b = PieceContext(total_sections=4, seed=99)
        seq_a = [pc_a.suggest_transform(pool, section_index=i) for i in range(4)]
        seq_b = [pc_b.suggest_transform(pool, section_index=i) for i in range(4)]
        assert seq_a == seq_b

    def test_different_seeds_are_independent_streams(self):
        pool = ["inversion", "retrograde", "augmentation", "diminution"]
        pc_a = PieceContext(total_sections=6, seed=1)
        pc_b = PieceContext(total_sections=6, seed=2)
        seq_a = [pc_a.suggest_transform(pool, section_index=i) for i in range(6)]
        seq_b = [pc_b.suggest_transform(pool, section_index=i) for i in range(6)]
        assert seq_a != seq_b  # different seeds, different draws (overwhelmingly likely)

    def test_explicit_transform_sequence_wraps_around(self):
        piece_ctx = PieceContext(total_sections=4)
        pool = ["inversion", "retrograde"]
        explicit = ["retrograde", "inversion"]
        result = [piece_ctx.suggest_transform(pool, transform_sequence=explicit,
                                               section_index=i) for i in range(4)]
        assert result == ["retrograde", "inversion", "retrograde", "inversion"]


# ===========================================================================
# compute_contour
# ===========================================================================

class TestComputeContour:
    def test_ascending(self):
        assert compute_contour([60, 62, 64, 67]) == "ascending"

    def test_descending(self):
        assert compute_contour([67, 64, 62, 60]) == "descending"

    def test_static_within_two_semitones(self):
        assert compute_contour([60, 61, 60, 61]) == "static"

    def test_peaked_arch_shape(self):
        assert compute_contour([60, 67, 64]) == "peaked"

    def test_troughed_valley_shape(self):
        assert compute_contour([67, 60, 64]) == "troughed"

    def test_single_pitch_is_static(self):
        assert compute_contour([60]) == "static"

    def test_empty_list_is_static(self):
        assert compute_contour([]) == "static"


# ===========================================================================
# compute_rhythmic_profile
# ===========================================================================

class TestComputeRhythmicProfile:
    def test_low_density_is_sparse_regardless_of_duration(self):
        assert compute_rhythmic_profile(5, 16.0, avg_duration=0.5, density=0.15) == "sparse"

    def test_long_duration_and_moderate_low_density_is_sustained(self):
        assert compute_rhythmic_profile(5, 16.0, avg_duration=3.0, density=0.25) == "sustained"

    def test_everything_else_is_steady(self):
        assert compute_rhythmic_profile(5, 16.0, avg_duration=1.0, density=0.5) == "steady"


# ===========================================================================
# compute_voice_snapshot
# ===========================================================================

class TestComputeVoiceSnapshot:
    def test_empty_pitches_returns_mostly_none_snapshot(self):
        snap = compute_voice_snapshot([], [], total_beats=16.0, total_slots=16,
                                       last_transform="inversion", last_chord_degree="V")
        assert snap.last_pitch is None
        assert snap.achieved_density is None
        # Metadata passed straight through even with no sounding notes:
        assert snap.last_transform == "inversion"
        assert snap.last_chord_degree == "V"

    def test_hand_verified_snapshot_fields(self):
        snap = compute_voice_snapshot(
            [62, 64, 67], [1.0, 1.0, 2.0], total_beats=16.0, total_slots=16,
            key="D", mode="dorian",
        )
        assert snap.last_pitch == 67
        assert snap.pitch_center == pytest.approx((62 + 64 + 67) / 3)
        assert snap.pitch_low == 62
        assert snap.pitch_high == 67
        assert snap.ending_contour == "ascending"
        assert snap.achieved_density == pytest.approx(3 / 16)
        assert snap.avg_note_duration_beats == pytest.approx((1.0 + 1.0 + 2.0) / 3)

    def test_scale_degree_computed_only_when_key_provided(self):
        without_key = compute_voice_snapshot([67], [1.0], total_beats=4.0, total_slots=4)
        assert without_key.last_scale_degree is None

        with_key = compute_voice_snapshot([67], [1.0], total_beats=4.0, total_slots=4,
                                           key="D", mode="dorian")
        assert with_key.last_scale_degree is not None
