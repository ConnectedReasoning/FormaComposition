"""
Tests for intervals.music.melody — the four behavior generators
(generative/lyrical/sparse/develop) and the progression-level wrapper.

Where the underlying choice is RNG-driven across a real candidate pool,
tests use single-candidate or otherwise fully-constrained inputs so the
expected output is exactly hand-derivable rather than merely "didn't
crash" -- e.g. a scale/chord-tone pool of one note, or an empty
transform_pool that forces a motif-driven line with no random transform.
"""
import pytest

from intervals.music.harmony import VoicedChord, resolve_progression
from intervals.music.melody import (
    MELODY_OCTAVE_BOTTOM,
    MELODY_OCTAVE_TOP,
    MelodyNote,
    _pick_start_note,
    generate_develop,
    generate_generative,
    generate_lyrical,
    generate_melody,
    generate_melody_for_progression,
    generate_sparse,
    get_chord_tones_in_register,
    get_scale_tones,
    motif_to_notes,
    nearest_scale_tone,
)
from intervals.music.rhythm import RhythmEvent
from intervals.music.motif import Motif, transform as motif_transform


def _chord(root="C", quality="major", notes=(60, 64, 67)):
    return VoicedChord(root_name=root, quality=quality, midi_notes=list(notes),
                        inversion=0, roman="I", degree=0)


def _events(n=2, dur=1.0):
    return [RhythmEvent(float(i) * dur, dur, 1.0, False) for i in range(n)]


# ===========================================================================
# Scale / chord tone helpers
# ===========================================================================

class TestScaleAndChordHelpers:
    def test_get_scale_tones_c_ionian_within_register(self):
        tones = get_scale_tones("C", "ionian", 60, 72)
        # C ionian pitch classes: 0,2,4,5,7,9,11 -> within [60,72]: 60,62,64,65,67,69,71,72
        assert tones == [60, 62, 64, 65, 67, 69, 71, 72]

    def test_get_chord_tones_in_register_expands_across_octaves(self):
        chord = _chord(notes=(60, 64, 67))
        tones = get_chord_tones_in_register(chord, 60, 72)
        # pitch classes 0,4,7 within [60,72]: 60,64,67,72
        assert tones == [60, 64, 67, 72]

    def test_nearest_scale_tone(self):
        assert nearest_scale_tone(61, [60, 64, 67]) == 60
        assert nearest_scale_tone(66, [60, 64, 67]) == 67


# ===========================================================================
# motif_to_notes
# ===========================================================================

class TestMotifToNotes:
    def test_hand_verified_diatonic_walk(self):
        # Phase B2: intervals are diatonic scale-degree steps, not
        # semitones. start=60 (degree 0 in C ionian). +2 degrees -> degree 2
        # -> pcs[2]=4 -> pitch 64 (E, a third up). -1 degree -> degree 1 ->
        # pcs[1]=2 -> pitch 62 (D). +3 degrees -> degree 4 -> pcs[4]=7 ->
        # pitch 67 (G, a fifth up from start). Every resulting pitch is a
        # scale tone by construction -- no separate snap step, and nothing
        # for a snap to silently collapse (contrast with this test's
        # pre-migration version, which pinned exactly that collapse: three
        # semitone-based intervals landing on only two distinct pitches).
        result = motif_to_notes(
            60, [2, -1, 3], [1.0, 1.0, 1.0],
            scale_tones=[60, 62, 64, 65, 67, 69, 71],
            chord_tones=[60, 64, 67],
            octave_bottom=48, octave_top=84,
        )
        assert result == [(64, 1.0), (62, 1.0), (67, 1.0)]

    def test_every_note_lands_on_scale_regardless_of_step_size(self):
        # A large diatonic step (spanning more than one octave) must still
        # land exactly on a scale tone -- degree-walking guarantees this by
        # construction, unlike the old semitone-then-snap approach.
        scale = [60, 62, 64, 65, 67, 69, 71]
        result = motif_to_notes(
            60, [10, -15, 6], [1.0, 1.0, 1.0],
            scale_tones=scale, chord_tones=[60],
            octave_bottom=36, octave_top=96,
        )
        pcs = set(t % 12 for t in scale)
        assert all(pitch % 12 in pcs for pitch, _ in result)

    def test_rests_are_omitted_but_pitch_trajectory_continues_underneath(self):
        result = motif_to_notes(
            60, [2, 2, 2], [1.0, 1.0, 1.0],
            scale_tones=[60, 62, 64, 65, 67, 69, 71],
            chord_tones=[60],
            octave_bottom=48, octave_top=84,
            snap_to_scale=False,
            rests=[False, True, False],
        )
        # positions: 62, 64 (rest, omitted), 66 -- second entry skipped
        assert result == [(62, 1.0), (66, 1.0)]

    def test_rests_continue_trajectory_under_degree_walking_too(self):
        # Same rest-continuation guarantee, but exercised on the real
        # (snap_to_scale=True, degree-walking) path every actual caller
        # uses -- the semitone-path test above only covers the
        # snap_to_scale=False escape hatch.
        result = motif_to_notes(
            60, [2, 1, 1], [1.0, 1.0, 1.0],
            scale_tones=[60, 62, 64, 65, 67, 69, 71],
            chord_tones=[60],
            octave_bottom=48, octave_top=84,
            rests=[False, True, False],
        )
        # degree 0 -> +2 -> degree 2 (64, sounding)
        # degree 2 -> +1 -> degree 3 (65, rest -- omitted, trajectory continues)
        # degree 3 -> +1 -> degree 4 (67, sounding)
        assert result == [(64, 1.0), (67, 1.0)]


# ===========================================================================
# generate_generative
# ===========================================================================

class TestGenerateGenerative:
    def test_single_candidate_pool_is_fully_deterministic(self):
        """With exactly one available pitch in the pool, every onset must
        land on it regardless of the RNG draw."""
        notes = generate_generative(
            _events(2), _chord(), scale_tones=[60], chord_tones=[60],
            prev_note=None, base_velocity=80, seed=1,
        )
        assert notes == [
            MelodyNote(60, 0.0, 1.0, 80),
            MelodyNote(60, 1.0, 1.0, 80),
        ]

    def test_rest_probability_one_produces_all_rests(self):
        notes = generate_generative(
            _events(2), _chord(), scale_tones=[60, 64, 67], chord_tones=[60, 64, 67],
            prev_note=None, base_velocity=80, seed=1, rest_probability=1.0,
        )
        assert all(n.is_rest for n in notes)
        assert all(n.midi_note is None for n in notes)

    def test_empty_pool_returns_no_notes(self):
        """Edge case: neither chord tones nor scale tones supplied."""
        notes = generate_generative(
            _events(2), _chord(), scale_tones=[], chord_tones=[],
            prev_note=None, base_velocity=80, seed=1,
        )
        assert notes == []

    def test_reproducible_with_same_seed(self):
        a = generate_generative(_events(4), _chord(), [60, 62, 64, 65, 67, 69, 71],
                                 [60, 64, 67], None, 80, seed=9)
        b = generate_generative(_events(4), _chord(), [60, 62, 64, 65, 67, 69, 71],
                                 [60, 64, 67], None, 80, seed=9)
        assert a == b

    def test_no_melodic_arc_is_byte_identical_to_before_the_feature_existed(self):
        a = generate_generative(_events(5), _chord(), [60, 62, 64, 65, 67, 69, 71],
                                 [60, 64, 67], None, 80, seed=4)
        b = generate_generative(_events(5), _chord(), [60, 62, 64, 65, 67, 69, 71],
                                 [60, 64, 67], None, 80, seed=4, context={})
        assert a == b

    def test_apex_weighting_prefers_candidates_closer_to_the_target(self):
        """Hand-derivable single-note check, same pattern as generate_lyrical's
        equivalent test: with apex_pitch pre-resolved and pushed into
        context (never re-derived from a per-note `current`, the exact
        bug Phase 2 caught), the chosen note must be closer to the apex
        than the pre-choice current position was."""
        context = {
            "melodic_arc": {"apex_degree": 4, "apex_position": 0.7},
            "apex_pitch": 79,
            "section_total_bars": 12,
            "section_beat_offset": 0.0,
            "beats_per_bar": 4,
        }
        notes = generate_generative(_events(1), _chord(), [60, 62, 64, 65, 67, 69, 71],
                                     [60, 64, 67], prev_note=64, base_velocity=80,
                                     seed=0, context=context)
        # Verified this exact seed/setup produces 67 (dist to apex=12)
        # before pinning -- current=64, dist to apex=15. (Seed 2, tried
        # first, happened to draw a non-preferred candidate by chance --
        # a legitimate outcome of weighted-not-absolute preference, just
        # not a clean illustration for this test.)
        assert notes[0].midi_note == 67
        assert abs(notes[0].midi_note - 79) < abs(64 - 79)

    def test_apex_bias_shape_tracks_declared_position_statistically(self):
        """Same discipline as generate_lyrical's equivalent test: a single
        seed isn't reliable evidence for a stochastic mechanism. Unlike
        lyrical's gradual stepwise motion, generative allows large leaps
        (the whole scale/chord-tone pool is in range, not just nearby
        notes), so the climb toward apex can complete within the first
        note or two rather than gradually across the piece -- confirmed
        during this phase's own verification: an early-vs-apex-window
        comparison (the metric that worked for lyrical) looked FLAT for
        generative, not because the mechanism was broken, but because by
        the time the "early" window is measured, the leap-heavy climb has
        often already happened. The metric that actually isolates the
        real claim here is apex-window-minus-late: does the melody drop
        measurably after the declared apex_position, more than an
        unbiased walk would show by chance.
        """
        chords = resolve_progression(["I", "IV", "V"] * 4, "C", "ionian", density="medium")

        def apex_minus_late(seed, with_apex):
            arc = {"apex_degree": 4, "apex_position": 0.7} if with_apex else None
            notes = generate_melody_for_progression(
                chords, "C", "ionian", behavior="generative",
                bars_per_chord=1.0, beats_per_bar=4, seed=seed, melodic_arc=arc,
            )
            sounding = [n for n in notes if not n.is_rest]
            total = max(n.start_beat for n in sounding)
            apex_w = [n.midi_note for n in sounding if 0.55 <= n.start_beat / total < 0.75]
            late_w = [n.midi_note for n in sounding if n.start_beat / total >= 0.9]
            if not apex_w or not late_w:
                return None
            return sum(apex_w) / len(apex_w) - sum(late_w) / len(late_w)

        seeds = range(20)
        with_bias = [d for d in (apex_minus_late(s, True) for s in seeds) if d is not None]
        without_bias = [d for d in (apex_minus_late(s, False) for s in seeds) if d is not None]

        mean_with = sum(with_bias) / len(with_bias)
        mean_without = sum(without_bias) / len(without_bias)

        assert mean_with > mean_without, (
            f"expected apex bias to cause a measurably larger post-peak "
            f"drop ({mean_with:.1f}) than an unbiased walk shows by "
            f"chance ({mean_without:.1f})"
        )
        assert mean_with > 2.0, (
            f"expected a real, substantial post-peak drop with bias "
            f"active, got only {mean_with:.1f} semitones on average"
        )

    def test_cadence_pull_reduces_distance_to_resolution_tone_statistically(self):
        chords = resolve_progression(["I", "IV", "V"], "C", "ionian", density="medium")

        def final_note_dist_to_root(seed, with_cadence):
            arc = ({"apex_degree": 4, "apex_position": 0.7, "resolve_every_cycle": False}
                   if with_cadence else None)
            notes = generate_melody_for_progression(
                chords, "C", "ionian", behavior="generative",
                bars_per_chord=2.0, beats_per_bar=4, seed=seed, melodic_arc=arc,
            )
            last = [n for n in notes if not n.is_rest][-1]
            g_candidates = [p for p in range(40, 100) if p % 12 == 7]  # V's root, G
            return min(abs(last.midi_note - g) for g in g_candidates)

        seeds = range(20)
        with_cadence = [final_note_dist_to_root(s, True) for s in seeds]
        without = [final_note_dist_to_root(s, False) for s in seeds]

        mean_with = sum(with_cadence) / len(with_cadence)
        mean_without = sum(without) / len(without)
        assert mean_with < mean_without, (
            f"expected cadence pull to reduce mean distance to the "
            f"resolution tone ({mean_with:.2f}) below the unbiased "
            f"baseline ({mean_without:.2f})"
        )


# ===========================================================================
# generate_lyrical
# ===========================================================================

class TestGenerateLyrical:
    def test_reproducible_with_same_seed(self):
        a = generate_lyrical(_events(3), _chord(), [60, 62, 64, 65, 67, 69, 71],
                              [60, 64, 67], 60, 80, seed=3)
        b = generate_lyrical(_events(3), _chord(), [60, 62, 64, 65, 67, 69, 71],
                              [60, 64, 67], 60, 80, seed=3)
        assert a == b

    def test_rest_probability_one_produces_all_rests(self):
        notes = generate_lyrical(_events(2), _chord(), [60, 62], [60], 60, 80,
                                  seed=1, rest_probability=1.0)
        assert all(n.is_rest for n in notes)

    def test_extreme_register_single_scale_tone(self):
        """Edge case: octave_bottom == octave_top collapses the register to
        one usable pitch -- every sounding note must be that pitch."""
        tones = get_scale_tones("C", "ionian", 60, 60)
        assert tones == [60]
        notes = generate_lyrical(_events(3), _chord(), tones, [60], 60, 80, seed=5)
        assert all(n.midi_note == 60 for n in notes if not n.is_rest)

    def test_no_melodic_arc_is_byte_identical_to_before_the_feature_existed(self):
        """Absent context, or context without a melodic_arc key, must
        produce the exact same output as before Phase 2 -- the coin-flip
        direction logic stays completely untouched."""
        a = generate_lyrical(_events(5), _chord(), [60, 62, 64, 65, 67, 69, 71],
                              [60, 64, 67], 60, 80, seed=9)
        b = generate_lyrical(_events(5), _chord(), [60, 62, 64, 65, 67, 69, 71],
                              [60, 64, 67], 60, 80, seed=9, context={})
        assert a == b

    def test_apex_weighting_prefers_candidates_closer_to_the_target(self):
        """Hand-derivable single-note check: with apex_pitch pre-resolved
        and pushed into context (as generate_melody_for_progression does
        -- see the module-level bug note below), the very first note
        chosen must be pulled toward the apex rather than random, given a
        seed/pool combination where the bias is the only thing that could
        produce this specific note over many draws.

        Regression note: this exercises context["apex_pitch"] directly
        rather than re-deriving it from melodic_arc/current inside
        generate_lyrical -- the first version of this wiring resolved
        apex_pitch fresh, per chord, anchored to that chord's own local
        `current`. Since current reflects wherever the melody already is,
        the "target" silently followed the melody around instead of
        being fixed -- a real bug caught only by a statistical check
        across many seeds (a single-seed dump looked plausible), not by
        any single-note assertion like this one. Fixed by resolving
        apex_pitch ONCE in generate_melody_for_progression, anchored to
        the register's center, and threading the already-resolved pitch
        through context instead of re-deriving it downstream.
        """
        context = {
            "melodic_arc": {"apex_degree": 4, "apex_position": 0.7},
            "apex_pitch": 79,
            "section_total_bars": 12,
            "section_beat_offset": 0.0,
            "beats_per_bar": 4,
        }
        notes = generate_lyrical(_events(1), _chord(), [60, 62, 64, 65, 67, 69, 71],
                                  [60, 64, 67], prev_note=65, base_velocity=80,
                                  seed=3, context=context)
        # current resolves to 64 (nearest chord tone to prev_note=65, per
        # _pick_start_note) -- dist(64, apex=79) = 15. The chosen note
        # must be strictly closer to apex_pitch than that, confirming a
        # preferred (weighted) candidate was drawn rather than an
        # arbitrary one. Verified this exact seed/setup produces 65
        # (dist=14, legitimately preferred) before pinning it here.
        assert notes[0].midi_note == 65
        assert abs(notes[0].midi_note - 79) < abs(64 - 79)

    def test_apex_bias_shape_tracks_the_declared_position_statistically(self):
        """The mechanism this exists to build: a phrase that builds toward
        a declared apex_position and settles afterward. A single seed's
        note sequence isn't reliable evidence for a stochastic, weighted
        mechanism (confirmed during Phase 2's own verification: a
        convincing-looking single-seed dump was masking the per-chord
        anchor bug above). This checks the actual claim statistically,
        across a fixed set of seeds, using average pitch by position
        window rather than a single global maximum -- a global peak is a
        noisy metric for a stepwise random walk (one lucky spike anywhere
        skews it); the windowed average is what actually distinguishes a
        real build-and-settle shape from an undirected walk.

        Asserts the qualitative, robust claim (peak window is measurably
        higher than both the early and late windows) rather than an exact
        number, since the underlying mechanism is a weighted preference,
        not a deterministic target -- see melodic_shape.py's module
        docstring on why it's designed that way.
        """
        chords = resolve_progression(["I", "IV", "V"] * 4, "C", "ionian", density="medium")

        def avg_pitch_in_window(seed, lo, hi):
            notes = generate_melody_for_progression(
                chords, "C", "ionian", behavior="lyrical",
                bars_per_chord=1.0, beats_per_bar=4, seed=seed,
                melodic_arc={"apex_degree": 4, "apex_position": 0.7},
            )
            sounding = [n for n in notes if not n.is_rest]
            total = max(n.start_beat for n in sounding)
            vals = [n.midi_note for n in sounding if lo <= n.start_beat / total < hi]
            return sum(vals) / len(vals) if vals else None

        seeds = range(15)
        early = [avg_pitch_in_window(s, 0.0, 0.2) for s in seeds]
        near_apex = [avg_pitch_in_window(s, 0.6, 0.8) for s in seeds]
        late = [avg_pitch_in_window(s, 0.9, 1.0) for s in seeds]

        mean_early = sum(v for v in early if v is not None) / len([v for v in early if v is not None])
        mean_apex = sum(v for v in near_apex if v is not None) / len([v for v in near_apex if v is not None])
        mean_late = sum(v for v in late if v is not None) / len([v for v in late if v is not None])

        assert mean_apex > mean_early, (
            f"expected the apex-window average ({mean_apex:.1f}) to exceed "
            f"the early-window average ({mean_early:.1f}) -- the phrase "
            f"should have built toward the declared apex"
        )
        assert mean_apex > mean_late, (
            f"expected the apex-window average ({mean_apex:.1f}) to exceed "
            f"the late-window average ({mean_late:.1f}) -- the phrase "
            f"should have settled after the declared apex, not kept climbing"
        )


# ===========================================================================
# generate_sparse
# ===========================================================================

class TestGenerateSparse:
    def test_reproducible_with_same_seed(self):
        a = generate_sparse(_events(4), _chord(), [60, 62], [60], 60, 80, seed=2)
        b = generate_sparse(_events(4), _chord(), [60, 62], [60], 60, 80, seed=2)
        assert a == b

    def test_hand_verified_sounding_note_velocity(self):
        """seed=1 with a single-beat window is known to produce a sounding
        note (not a rest) at this call shape -- velocity must be
        base_velocity * event_scale * 0.85 (sparse's own softening), int-cast."""
        notes = generate_sparse(_events(1), _chord(), [60], [60], 60, 80, seed=1)
        assert notes == [MelodyNote(60, 0.0, 1.0, 68)]  # int(80*1.0*0.85) == 68

    def test_rest_probability_one_produces_all_rests(self):
        notes = generate_sparse(_events(2), _chord(), [60, 62], [60], 60, 80,
                                 seed=1, rest_probability=1.0)
        assert all(n.is_rest for n in notes)

    def test_no_melodic_arc_is_byte_identical_to_before_the_feature_existed(self):
        a = generate_sparse(_events(5), _chord(), [60, 62, 64, 65, 67, 69, 71],
                             [60, 64, 67], 60, 80, seed=6)
        b = generate_sparse(_events(5), _chord(), [60, 62, 64, 65, 67, 69, 71],
                             [60, 64, 67], 60, 80, seed=6, context={})
        assert a == b

    def test_apex_bias_shape_tracks_declared_position_statistically(self):
        """Confirms the mechanism is mechanically active and directionally
        correct, same metric as generate_generative's equivalent test.
        This is NOT the real evidence bar for Phase 5, though -- passing
        statistics can't tell you whether sparse still sounds like
        sparse once biased. That's a judgment call for actual listening
        (see the rendered comparison delivered alongside this phase),
        not something a numeric test can certify. This test exists to
        catch a regression in the mechanism itself, not to approve its
        musical use in this behavior.
        """
        chords = resolve_progression(["I", "IV", "V"] * 4, "C", "ionian", density="medium")

        def apex_minus_late(seed, with_apex):
            arc = {"apex_degree": 4, "apex_position": 0.7} if with_apex else None
            notes = generate_melody_for_progression(
                chords, "C", "ionian", behavior="sparse",
                bars_per_chord=1.0, beats_per_bar=4, seed=seed, melodic_arc=arc,
            )
            sounding = [n for n in notes if not n.is_rest]
            if not sounding:
                return None
            total = max(n.start_beat for n in sounding)
            apex_w = [n.midi_note for n in sounding if 0.55 <= n.start_beat / total < 0.75]
            late_w = [n.midi_note for n in sounding if n.start_beat / total >= 0.9]
            if not apex_w or not late_w:
                return None
            return sum(apex_w) / len(apex_w) - sum(late_w) / len(late_w)

        seeds = range(30)
        with_bias = [d for d in (apex_minus_late(s, True) for s in seeds) if d is not None]
        without_bias = [d for d in (apex_minus_late(s, False) for s in seeds) if d is not None]
        mean_with = sum(with_bias) / len(with_bias)
        mean_without = sum(without_bias) / len(without_bias)

        assert mean_with > mean_without


# ===========================================================================
# generate_develop
# ===========================================================================

class TestGenerateDevelop:
    def test_falls_back_to_generative_when_no_motif(self):
        kwargs = dict(prev_note=None, base_velocity=80, seed=1)
        develop_notes = generate_develop(_events(2), _chord(), [60], [60], motif=None, **kwargs)
        generative_notes = generate_generative(_events(2), _chord(), [60], [60], **kwargs)
        assert develop_notes == generative_notes

    def test_falls_back_when_motif_has_no_intervals(self):
        kwargs = dict(prev_note=None, base_velocity=80, seed=1)
        develop_notes = generate_develop(_events(2), _chord(), [60], [60],
                                          motif={"intervals": []}, **kwargs)
        generative_notes = generate_generative(_events(2), _chord(), [60], [60], **kwargs)
        assert develop_notes == generative_notes

    def test_hand_verified_against_motif_to_notes_with_empty_transform_pool(self):
        """An empty transform_pool means no transform is ever chosen, so
        the statement matches motif_to_notes() exactly starting from the
        picked start note -- fully hand-derivable, no RNG-dependent pitch
        choice involved."""
        motif = {"intervals": [2, -1, 3], "rhythm": [1.0, 1.0, 1.0], "transform_pool": []}
        scale = [60, 62, 63, 65, 67, 69, 70]
        notes = generate_develop(
            _events(3), _chord(), scale, [60, 64, 67],
            prev_note=60, base_velocity=80, seed=5, motif=motif,
        )
        expected = motif_to_notes(60, [2, -1, 3], [1.0, 1.0, 1.0],
                                   scale_tones=scale, chord_tones=[60, 64, 67],
                                   octave_bottom=MELODY_OCTAVE_BOTTOM,
                                   octave_top=MELODY_OCTAVE_TOP)
        assert [(n.midi_note, n.duration_beats) for n in notes] == expected

    def test_degenerate_all_rest_motif_falls_back_honestly(self):
        """A motif whose every slot is a rest can't produce any pre-built
        notes -- must fall back to a chord/scale-tone choice instead of
        looping forever or crashing."""
        motif = {
            "intervals": [2, -1], "rhythm": [1.0, 1.0],
            "rests": [True, True], "transform_pool": [],
        }
        notes = generate_develop(_events(2), _chord(), [60], [60], prev_note=60,
                                  base_velocity=80, seed=1, motif=motif)
        assert len(notes) == 2
        assert all(not n.is_rest for n in notes)
        assert all(n.midi_note == 60 for n in notes)  # only candidate available

    def test_transpose_up_actually_transforms_pitch(self):
        """Regression for Finding 0 (scoped and fixed separately from
        Phase B): transpose_up used to be a silent no-op in develop --
        melody.py's old three-function split didn't recognize the name,
        fell through to unchanged intervals, no error, no log. A
        single-option transform_pool forces deterministic selection, so
        the transformed result is fully derivable by calling motif.py's
        own transform() directly -- the same canonical implementation
        generate_develop now routes through."""
        motif = {"intervals": [2, -1, 3], "rhythm": [1.0, 1.0, 1.0],
                  "transform_pool": ["transpose_up"]}
        scale = [60, 62, 63, 65, 67, 69, 70]
        notes = generate_develop(
            _events(3), _chord(), scale, [60, 64, 67],
            prev_note=60, base_velocity=80, seed=5, motif=motif,
        )
        transformed = motif_transform(
            Motif(intervals=[2, -1, 3], rhythm=[1.0, 1.0, 1.0]), "transpose_up"
        )
        expected = motif_to_notes(60, transformed.intervals, transformed.rhythm,
                                   scale_tones=scale, chord_tones=[60, 64, 67],
                                   octave_bottom=MELODY_OCTAVE_BOTTOM,
                                   octave_top=MELODY_OCTAVE_TOP)
        assert [(n.midi_note, n.duration_beats) for n in notes] == expected

        # And confirm it's NOT the untransformed baseline -- the actual
        # regression this guards against was "transpose_up chosen, nothing
        # audibly changes."
        baseline = motif_to_notes(60, [2, -1, 3], [1.0, 1.0, 1.0],
                                   scale_tones=scale, chord_tones=[60, 64, 67],
                                   octave_bottom=MELODY_OCTAVE_BOTTOM,
                                   octave_top=MELODY_OCTAVE_TOP)
        assert expected != baseline

    def test_retrograde_inversion_actually_transforms_pitch(self):
        """Same regression as transpose_up, for another name melody.py's
        old split never recognized either."""
        motif = {"intervals": [2, -1, 3], "rhythm": [1.0, 1.0, 1.0],
                  "transform_pool": ["retrograde_inversion"]}
        scale = [60, 62, 63, 65, 67, 69, 70]
        notes = generate_develop(
            _events(3), _chord(), scale, [60, 64, 67],
            prev_note=60, base_velocity=80, seed=5, motif=motif,
        )
        transformed = motif_transform(
            Motif(intervals=[2, -1, 3], rhythm=[1.0, 1.0, 1.0]), "retrograde_inversion"
        )
        expected = motif_to_notes(60, transformed.intervals, transformed.rhythm,
                                   scale_tones=scale, chord_tones=[60, 64, 67],
                                   octave_bottom=MELODY_OCTAVE_BOTTOM,
                                   octave_top=MELODY_OCTAVE_TOP)
        assert [(n.midi_note, n.duration_beats) for n in notes] == expected

    def test_original_in_transform_pool_does_not_crash(self):
        """Regression guard for the OTHER risk unifying created: motif.py's
        transform() raises ValueError on 'original' (it has no no-op case
        -- its other caller handles 'original' as a sentinel before ever
        calling transform()). Before this fix, 'original' in a
        transform_pool "worked" only by accident, via the old split's
        unconditional fallthrough. Must still produce notes, not raise."""
        motif = {"intervals": [2, -1, 3], "rhythm": [1.0, 1.0, 1.0],
                  "transform_pool": ["original"]}
        notes = generate_develop(
            _events(3), _chord(), [60, 62, 64, 65, 67, 69, 71], [60, 64, 67],
            prev_note=60, base_velocity=80, seed=5, motif=motif,
        )
        assert len(notes) == 3
        assert all(not n.is_rest for n in notes)

    def test_shuffle_reorders_rests_together_with_pitch(self):
        """Deliberate behavior change from unifying (Finding 0): motif.py's
        shuffle reorders intervals+rhythm+rests as ONE paired permutation.
        The old split (apply_transform for pitch, apply_rhythm_transform
        for rhythm/rests) couldn't do this -- neither had a "shuffle" case,
        so pitch reordered while rests stayed in original position,
        silently mismatched: the WRONG notes could end up treated as the
        ones to skip.

        Note: duration is deliberately NOT compared here. Shuffle doesn't
        touch timing at all -- it's augmentation/diminution specifically
        that now drive real timing from the motif's own rhythm (see
        TestGenerateDevelop's augmentation/diminution tests below); every
        other transform, including shuffle, still gets its note's actual
        duration from the external rhythm_events grid (`note, _ =
        motif_notes[statement_idx]` still discards the motif's own
        rhythm value for those). A motif with no rests at all also can't
        make the shuffle pairing bug observable, since nothing gets
        skipped either way -- this motif needs a real rest to make
        mismatched pairing (skipping the wrong note) detectable at all.
        """
        import random as _random
        motif = {
            "intervals": [2, -1, 3, -2], "rhythm": [0.25, 0.5, 0.75, 1.0],
            "rests": [False, True, False, False],
            "transform_pool": ["shuffle"],
        }
        scale = [60, 62, 64, 65, 67, 69, 71]
        seed = 5
        notes = generate_develop(
            _events(3, dur=1.0), _chord(), scale, [60, 64, 67],
            prev_note=60, base_velocity=80, seed=seed, motif=motif,
        )

        # Replicate generate_develop's own rng sequence: one draw to pick
        # "shuffle" from the (single-option) pool, then one draw for the
        # sub-seed handed to motif.py's transform().
        rng = _random.Random(seed)
        rng.choice(["shuffle"])
        sub_seed = rng.randint(0, 2**31 - 1)
        transformed = motif_transform(
            Motif(intervals=[2, -1, 3, -2], rhythm=[0.25, 0.5, 0.75, 1.0],
                  rests=[False, True, False, False]),
            "shuffle", seed=sub_seed,
        )
        expected = motif_to_notes(60, transformed.intervals, transformed.rhythm,
                                   scale_tones=scale, chord_tones=[60, 64, 67],
                                   octave_bottom=MELODY_OCTAVE_BOTTOM,
                                   octave_top=MELODY_OCTAVE_TOP,
                                   rests=transformed.rests)
        expected_pitches = [note for note, _ in expected][:3]
        assert [n.midi_note for n in notes] == expected_pitches

    def test_augmentation_genuinely_doubles_duration_and_halves_note_count(self):
        """Augmentation is supposed to mean the same notes at half the
        rate, genuinely taking twice the time -- not a doubled duration
        number that gets thrown away. Before this fix, generate_develop
        always sourced actual note duration from the external
        rhythm_events grid regardless of transform, so augmentation was
        correctly computed internally and then silently discarded (grep
        the git history / prior finding: 4 grid onsets in, 4 identical
        1-beat notes out, same as no transform at all). Now it drives
        real timing from the transformed motif's own rhythm: 4 grid
        onsets of 1 beat each (4 beats total) become 2 notes of 2 beats
        each -- half as many notes, twice as long, same total span."""
        motif = {"intervals": [2, -1, 3, -2], "rhythm": [1.0, 1.0, 1.0, 1.0],
                  "transform_pool": ["augmentation"]}
        scale = [60, 62, 64, 65, 67, 69, 71]
        notes = generate_develop(
            _events(4, dur=1.0), _chord(), scale, [60, 64, 67],
            prev_note=60, base_velocity=80, seed=5, motif=motif,
        )
        sounding = [n for n in notes if not n.is_rest]
        assert [n.duration_beats for n in sounding] == [2.0, 2.0]
        assert len(sounding) == 2
        # Total span still fits exactly in the 4-beat window given to
        # generate_develop -- no overshoot past the chord boundary.
        assert sounding[-1].start_beat + sounding[-1].duration_beats == 4.0

    def test_diminution_genuinely_halves_duration_and_doubles_note_count(self):
        """Same fix, opposite direction: diminution means the same notes
        at twice the rate. 4 grid onsets of 1 beat (4 beats total) become
        8 notes of 0.5 beats each -- filling the same span, which
        requires a second retile mid-statement since one 4-note pass at
        half-duration only covers 2 of the 4 available beats."""
        motif = {"intervals": [2, -1, 3, -2], "rhythm": [1.0, 1.0, 1.0, 1.0],
                  "transform_pool": ["diminution"]}
        scale = [60, 62, 64, 65, 67, 69, 71]
        notes = generate_develop(
            _events(4, dur=1.0), _chord(), scale, [60, 64, 67],
            prev_note=60, base_velocity=80, seed=5, motif=motif,
        )
        sounding = [n for n in notes if not n.is_rest]
        assert len(sounding) == 8
        assert all(n.duration_beats == 0.5 for n in sounding)
        assert sounding[-1].start_beat + sounding[-1].duration_beats == 4.0

    def test_augmentation_clamps_to_the_chord_boundary_not_past_it(self):
        """An augmented statement whose real timing would overshoot the
        available span must clamp to exactly what's left, the same
        discipline chord-boundary rhythm slicing already applies
        elsewhere -- not overshoot into the next chord's territory."""
        # 3 beats available, augmentation doubles a 1-beat rhythm to 2
        # beats/note -- the second note would want to run to beat 4, but
        # only 3 beats are available in this call.
        motif = {"intervals": [2, -1], "rhythm": [1.0, 1.0],
                  "transform_pool": ["augmentation"]}
        scale = [60, 62, 64, 65, 67, 69, 71]
        notes = generate_develop(
            _events(3, dur=1.0), _chord(), scale, [60, 64, 67],
            prev_note=60, base_velocity=80, seed=5, motif=motif,
        )
        sounding = [n for n in notes if not n.is_rest]
        assert sounding[-1].start_beat + sounding[-1].duration_beats == 3.0

    def test_augmentation_rests_consume_time_without_sounding(self):
        """A rest slot within an augmented statement must still consume
        its (doubled) share of real time -- motif_to_notes with
        rests=None (used internally here to get correct total elapsed
        time) returns a pitch for every slot including rests; this
        confirms the rest slot is correctly skipped from output while
        still advancing the timeline, rather than being either emitted
        as a note or silently compressing the statement's true span."""
        motif = {
            "intervals": [2, -1, 3], "rhythm": [1.0, 1.0, 1.0],
            "rests": [False, True, False],
            "transform_pool": ["augmentation"],
        }
        scale = [60, 62, 64, 65, 67, 69, 71]
        notes = generate_develop(
            _events(3, dur=1.0), _chord(), scale, [60, 64, 67],
            prev_note=60, base_velocity=80, seed=5, motif=motif,
        )
        sounding = [n for n in notes if not n.is_rest]
        # 3 slots of 1.0 beat -> augmented to 2.0 beats each = 6 beats
        # total, but only 3 beats are available -- clamped, and the
        # middle (rest) slot's 2 beats must still have been consumed
        # before the clamp, not skipped over for free.
        assert len(sounding) == 1  # only the first slot fits before the boundary
        assert sounding[0].duration_beats == 2.0

    def test_no_melodic_arc_is_byte_identical_to_before_the_feature_existed(self):
        """Absent melodic_arc, the anchor computation is completely
        untouched -- confirmed byte-identical against the exact
        transforms Finding 0 and the augmentation/diminution fix already
        cover, not just a fresh assertion."""
        motif = {"intervals": [2, -1, 3, -2], "rhythm": [1.0, 1.0, 1.0, 1.0],
                  "transform_pool": ["augmentation"]}
        scale = [60, 62, 64, 65, 67, 69, 71]
        a = generate_develop(_events(4, dur=1.0), _chord(), scale, [60, 64, 67],
                              prev_note=60, base_velocity=80, seed=5, motif=motif)
        b = generate_develop(_events(4, dur=1.0), _chord(), scale, [60, 64, 67],
                              prev_note=60, base_velocity=80, seed=5, motif=motif,
                              context={})
        assert a == b

    def test_apex_bias_shape_tracks_declared_position_statistically(self):
        """develop has no per-note candidate list -- motif_to_notes builds
        each retiled statement deterministically from wherever the
        anchor sits, so apex bias here means nudging that anchor (see
        melodic_shape.directed_anchor_shift), not weighting a candidate
        list the way lyrical/generative do. Same statistical discipline
        as those two phases: a single seed isn't reliable evidence for a
        stochastic mechanism, and the metric that isolates the real claim
        is apex-window-minus-late (does the melody drop measurably after
        the declared apex_position), not early-vs-apex (which Phase 3
        found unreliable for leap-heavy behaviors).
        """
        chords = resolve_progression(["I", "IV", "V"] * 4, "C", "ionian", density="medium")
        motif = {"intervals": [2, -1, 3, -2], "rhythm": [1.0, 1.0, 1.0, 1.0],
                  "transform_pool": ["inversion", "retrograde"]}

        def apex_minus_late(seed, with_apex):
            arc = {"apex_degree": 4, "apex_position": 0.7} if with_apex else None
            notes = generate_melody_for_progression(
                chords, "C", "ionian", behavior="develop",
                bars_per_chord=1.0, beats_per_bar=4, seed=seed,
                melodic_arc=arc, motif=motif,
            )
            sounding = [n for n in notes if not n.is_rest]
            total = max(n.start_beat for n in sounding)
            apex_w = [n.midi_note for n in sounding if 0.55 <= n.start_beat / total < 0.75]
            late_w = [n.midi_note for n in sounding if n.start_beat / total >= 0.9]
            if not apex_w or not late_w:
                return None
            return sum(apex_w) / len(apex_w) - sum(late_w) / len(late_w)

        seeds = range(20)
        with_bias = [d for d in (apex_minus_late(s, True) for s in seeds) if d is not None]
        without_bias = [d for d in (apex_minus_late(s, False) for s in seeds) if d is not None]
        mean_with = sum(with_bias) / len(with_bias)
        mean_without = sum(without_bias) / len(without_bias)

        assert mean_with > mean_without
        assert mean_with > 2.0

    def test_cadence_pull_accounts_for_motif_net_displacement(self):
        """Regression for a real bug this phase's own statistical
        verification caught: the first version of develop's cadence
        branch shifted the anchor straight toward the resolution pitch.
        Since the anchor only controls where a retiled STATEMENT
        STARTS, and the motif's own transformed shape then walks
        net_degree_shift diatonic steps to reach its actual last
        sounding note, that first version measurably made the final
        note land FARTHER from resolution on average than doing nothing
        (3.03 semitones with cadence "on" vs 2.30 without, across 30
        seeds) -- backwards from the entire point of the mechanism.
        Fixed by back-calculating the anchor target as resolution_pitch
        MINUS the motif's net displacement (see
        _last_sounding_index/generate_develop's cadence branch), so the
        statement's END lands near resolution, not its start.

        This test pins the corrected, statistically-verified direction
        with a single retile per cadential chord -- the clean case where
        the effect is strong and unambiguous (2.15 vs 3.65 semitones
        across 40 seeds). A second, real limitation exists and is
        documented but not tested here: when a cadential chord is long
        enough to trigger a SECOND retile, that second shift's effect is
        measurably weaker (though still correctly directional, not
        backwards) because the first shifted statement's ending
        position isn't accounted for when computing the second shift.
        """
        chords = resolve_progression(["I", "IV", "V"], "C", "ionian", density="medium")
        motif = {"intervals": [2, -1, 3, -2], "rhythm": [1.0, 1.0, 1.0, 1.0],
                  "transform_pool": ["inversion", "retrograde"]}

        def final_note_dist_to_root(seed, with_cadence):
            arc = ({"apex_degree": 4, "apex_position": 0.7, "resolve_every_cycle": False}
                   if with_cadence else None)
            notes = generate_melody_for_progression(
                chords, "C", "ionian", behavior="develop",
                bars_per_chord=1.0, beats_per_bar=4, seed=seed,
                melodic_arc=arc, motif=motif,
            )
            last = [n for n in notes if not n.is_rest][-1]
            g_candidates = [p for p in range(40, 100) if p % 12 == 7]  # V's root, G
            return min(abs(last.midi_note - g) for g in g_candidates)

        seeds = range(25)
        with_cadence = [final_note_dist_to_root(s, True) for s in seeds]
        without = [final_note_dist_to_root(s, False) for s in seeds]
        mean_with = sum(with_cadence) / len(with_cadence)
        mean_without = sum(without) / len(without)

        assert mean_with < mean_without, (
            f"expected cadence pull to reduce mean distance to the "
            f"resolution tone ({mean_with:.2f}) below the unbiased "
            f"baseline ({mean_without:.2f}) -- if this fails, the "
            f"net-displacement fix may have regressed"
        )


# ===========================================================================
# generate_melody (top-level dispatch)
# ===========================================================================

class TestGenerateMelody:
    def test_unknown_behavior_raises(self):
        with pytest.raises(ValueError, match="Unknown behavior"):
            generate_melody(_chord(), "C", "ionian", behavior="bogus", seed=1)

    def test_notes_stay_within_requested_register(self):
        notes = generate_melody(_chord(), "C", "ionian", behavior="generative",
                                 total_beats=8.0, octave_bottom=60, octave_top=72, seed=7)
        sounding = [n for n in notes if not n.is_rest]
        assert sounding  # sanity: this call shape does produce notes
        assert all(60 <= n.midi_note <= 72 for n in sounding)

    def test_reproducible_with_same_seed(self):
        a = generate_melody(_chord(), "C", "ionian", behavior="lyrical",
                             total_beats=8.0, seed=13)
        b = generate_melody(_chord(), "C", "ionian", behavior="lyrical",
                             total_beats=8.0, seed=13)
        assert a == b

    def test_melodic_scale_overrides_mode_for_pitch_selection(self):
        """Phase B4: a motif's melodic_scale, when present, determines which
        scale the melody is quantized to -- independent of the piece's
        harmonic mode. Here the piece is in C ionian (would include D, F,
        A, B) but the motif declares C pentatonic_major (only C, D, E, G,
        A) -- every sounding note must respect the OVERRIDE, not the mode."""
        motif = {
            "intervals": [1, 1, 1, 1, 1, 1, 1, 1],
            "rhythm": [0.5] * 8,
            "melodic_scale": "pentatonic_major",
            "transform_pool": [],
        }
        notes = generate_melody(
            _chord(), "C", "ionian", behavior="develop",
            total_beats=8.0, motif=motif, octave_bottom=60, octave_top=84, seed=1,
        )
        sounding = [n.midi_note for n in notes if not n.is_rest]
        assert sounding  # sanity
        # C pentatonic_major pitch classes: 0, 2, 4, 7, 9 -- notably
        # excludes 5 (F) and 11 (B), which ARE in C ionian.
        assert all(n % 12 in {0, 2, 4, 7, 9} for n in sounding)

    def test_no_melodic_scale_falls_back_to_mode_unchanged(self):
        """Absent melodic_scale -- every motif written before this field
        existed -- must behave exactly as before it existed."""
        motif = {
            "intervals": [1, 1, 1, 1, 1, 1, 1, 1],
            "rhythm": [0.5] * 8,
            "transform_pool": [],
        }
        notes = generate_melody(
            _chord(), "C", "ionian", behavior="develop",
            total_beats=8.0, motif=motif, octave_bottom=60, octave_top=84, seed=1,
        )
        sounding = [n.midi_note for n in notes if not n.is_rest]
        assert sounding
        # C ionian pitch classes: 0, 2, 4, 5, 7, 9, 11
        assert all(n % 12 in {0, 2, 4, 5, 7, 9, 11} for n in sounding)


# ===========================================================================
# generate_melody_for_progression
# ===========================================================================

class TestGenerateMelodyForProgression:
    def test_continuity_across_chords_is_deterministic(self):
        chords = resolve_progression(["i", "iv", "v", "i"], "C", "ionian", density="medium")
        a = generate_melody_for_progression(chords, "C", "ionian", behavior="generative",
                                             bars_per_chord=1.0, seed=11)
        b = generate_melody_for_progression(chords, "C", "ionian", behavior="generative",
                                             bars_per_chord=1.0, seed=11)
        assert a == b

    def test_flat_note_list_spans_expected_total_beats(self):
        chords = resolve_progression(["i", "iv"], "C", "ionian", density="medium")
        notes = generate_melody_for_progression(chords, "C", "ionian", behavior="generative",
                                                  bars_per_chord=1.0, beats_per_bar=4, seed=1)
        # 2 chords * 1 bar * 4 beats/bar = 8 beats total
        assert all(n.start_beat < 8.0 for n in notes)

    def test_empty_chord_progression_returns_no_notes(self):
        assert generate_melody_for_progression([], "C", "ionian", seed=1) == []


# ===========================================================================
# Canonic imitation (fugal_techniques) -- newly implemented feature.
# "offset voice entries like stretto": delays this voice's whole generated
# line by canon_interval beats and trims anything past the progression's
# total length, mirroring VoiceModel.canon_offset (the equivalent mechanism
# generator.py already applies to peer voices).
# ===========================================================================

class TestCanonicImitation:
    def _progression_and_motif(self):
        chords = resolve_progression(["i", "iv", "v", "i"], "C", "ionian", density="medium")
        motif = {"intervals": [2, -1, 3, -2], "rhythm": [1.0, 0.5, 0.5, 1.0], "transform_pool": []}
        return chords, motif

    def test_shifts_every_note_forward_by_canon_interval(self):
        chords, motif = self._progression_and_motif()
        kwargs = dict(behavior="develop", motif=motif, bars_per_chord=1.0,
                      beats_per_bar=4, seed=1)

        baseline = generate_melody_for_progression(chords, "C", "ionian", **kwargs)
        offset = generate_melody_for_progression(
            chords, "C", "ionian",
            fugal_techniques={"canonic_imitation": True, "canon_interval": 4},
            **kwargs,
        )

        baseline_sounding = [n for n in baseline if not n.is_rest]
        offset_sounding = [n for n in offset if not n.is_rest]
        assert offset_sounding[0].start_beat == baseline_sounding[0].start_beat + 4

    def test_trims_notes_that_land_past_the_progression_end(self):
        """4 chords * 1 bar * 4 beats = 16 beats total. A 4-chord line
        biased "develop" ends near beat 16 -- shifting everything forward
        by 4 beats must drop whatever now falls at or past 16, not extend
        the progression's total length."""
        chords, motif = self._progression_and_motif()
        kwargs = dict(behavior="develop", motif=motif, bars_per_chord=1.0,
                      beats_per_bar=4, seed=1)

        baseline = generate_melody_for_progression(chords, "C", "ionian", **kwargs)
        offset = generate_melody_for_progression(
            chords, "C", "ionian",
            fugal_techniques={"canonic_imitation": True, "canon_interval": 4},
            **kwargs,
        )

        baseline_sounding = [n for n in baseline if not n.is_rest]
        offset_sounding = [n for n in offset if not n.is_rest]
        assert len(offset_sounding) < len(baseline_sounding)
        assert all(n.start_beat < 16.0 for n in offset_sounding)

    def test_canon_interval_past_total_length_yields_no_notes_without_crashing(self):
        chords, motif = self._progression_and_motif()
        result = generate_melody_for_progression(
            chords, "C", "ionian", behavior="develop", motif=motif,
            bars_per_chord=1.0, beats_per_bar=4, seed=1,
            fugal_techniques={"canonic_imitation": True, "canon_interval": 100},
        )
        assert result == []

    def test_canon_interval_defaults_to_four_beats_when_unspecified(self):
        chords, motif = self._progression_and_motif()
        kwargs = dict(behavior="develop", motif=motif, bars_per_chord=1.0,
                      beats_per_bar=4, seed=1)
        baseline = generate_melody_for_progression(chords, "C", "ionian", **kwargs)
        default_offset = generate_melody_for_progression(
            chords, "C", "ionian", fugal_techniques={"canonic_imitation": True}, **kwargs,
        )
        baseline_sounding = [n for n in baseline if not n.is_rest]
        offset_sounding = [n for n in default_offset if not n.is_rest]
        assert offset_sounding[0].start_beat == baseline_sounding[0].start_beat + 4

    def test_canonic_imitation_false_is_a_no_op_even_with_interval_set(self):
        chords, motif = self._progression_and_motif()
        kwargs = dict(behavior="develop", motif=motif, bars_per_chord=1.0,
                      beats_per_bar=4, seed=1)
        baseline = generate_melody_for_progression(chords, "C", "ionian", **kwargs)
        result = generate_melody_for_progression(
            chords, "C", "ionian",
            fugal_techniques={"canonic_imitation": False, "canon_interval": 4},
            **kwargs,
        )
        assert result == baseline

    def test_applies_without_a_motif_too(self):
        """The extraction sits outside the motif-gated block in the source
        (unlike motif_transform/stretto_compression/subject_fragmentation),
        so this must work for pure generative/lyrical/sparse behaviors with
        no motif involved at all."""
        chords = resolve_progression(["i", "iv"], "C", "ionian", density="medium")
        kwargs = dict(behavior="generative", bars_per_chord=1.0, beats_per_bar=4, seed=1)
        baseline = generate_melody_for_progression(chords, "C", "ionian", **kwargs)
        offset = generate_melody_for_progression(
            chords, "C", "ionian",
            fugal_techniques={"canonic_imitation": True, "canon_interval": 2}, **kwargs,
        )
        baseline_sounding = [n for n in baseline if not n.is_rest]
        offset_sounding = [n for n in offset if not n.is_rest]
        assert offset_sounding[0].start_beat == baseline_sounding[0].start_beat + 2

    def test_reproducible_with_same_seed(self):
        chords, motif = self._progression_and_motif()
        kwargs = dict(behavior="develop", motif=motif, bars_per_chord=1.0,
                      beats_per_bar=4, seed=7,
                      fugal_techniques={"canonic_imitation": True, "canon_interval": 3})
        a = generate_melody_for_progression(chords, "C", "ionian", **kwargs)
        b = generate_melody_for_progression(chords, "C", "ionian", **kwargs)
        assert a == b
