"""
Tests for intervals.music.percussion — drum pattern tiling, density
filtering, bass-onset reinforcement, and swing.
"""
import pytest

from intervals.music.bass import BassNote
from intervals.music.percussion import (
    DRUM_KIT,
    DRUM_PATTERNS,
    DrumHit,
    _apply_swing_to_drums,
    _reinforce_bass_with_kick,
    generate_drums,
)


# ===========================================================================
# generate_drums — core generation path
# ===========================================================================

class TestGenerateDrums:
    def test_missing_seed_raises(self):
        with pytest.raises(ValueError, match="explicit seed"):
            generate_drums(4.0, [], seed=None)

    def test_unknown_pattern_raises(self):
        with pytest.raises(ValueError, match="Unknown drum pattern"):
            generate_drums(4.0, [], pattern="bogus_pattern", seed=1)

    def test_hand_verified_sparse_density_on_four_on_floor(self):
        """Sparse keeps only priority-1 slots: kick on every beat, snare
        on 2 and 4, hi-hat on every beat (the offbeat hi-hats are
        priority 2, excluded). Velocities are int(80 * pattern_scale)."""
        hits = generate_drums(4.0, [], pattern="four_on_floor", density="sparse",
                               beats_per_bar=4, seed=1)
        result = [(h.midi_note, h.start_beat, h.velocity) for h in hits]
        assert result == [
            (DRUM_KIT["kick"], 0.0, 76), (DRUM_KIT["hi_hat"], 0.0, 52),
            (DRUM_KIT["kick"], 1.0, 72), (DRUM_KIT["snare"], 1.0, 68), (DRUM_KIT["hi_hat"], 1.0, 52),
            (DRUM_KIT["kick"], 2.0, 76), (DRUM_KIT["hi_hat"], 2.0, 52),
            (DRUM_KIT["kick"], 3.0, 72), (DRUM_KIT["snare"], 3.0, 68), (DRUM_KIT["hi_hat"], 3.0, 52),
        ]

    def test_full_density_adds_offbeat_hi_hats(self):
        sparse = generate_drums(4.0, [], pattern="four_on_floor", density="sparse",
                                 beats_per_bar=4, seed=1)
        full = generate_drums(4.0, [], pattern="four_on_floor", density="full",
                               beats_per_bar=4, seed=1)
        assert len(full) > len(sparse)
        offbeat_hihats_full = [h for h in full
                                if h.midi_note == DRUM_KIT["hi_hat"] and h.start_beat % 1.0 == 0.5]
        assert len(offbeat_hihats_full) > 0

    def test_pattern_tiles_across_multiple_bars(self):
        one_bar = generate_drums(4.0, [], pattern="minimal", beats_per_bar=4, seed=1)
        two_bars = generate_drums(8.0, [], pattern="minimal", beats_per_bar=4, seed=1)
        assert len(two_bars) == 2 * len(one_bar)

    def test_reproducible_with_same_seed(self):
        a = generate_drums(8.0, [], pattern="backbeat", density="full", seed=7)
        b = generate_drums(8.0, [], pattern="backbeat", density="full", seed=7)
        assert a == b

    def test_hits_are_sorted_by_start_beat(self):
        hits = generate_drums(8.0, [], pattern="syncopated" if "syncopated" in DRUM_PATTERNS
                               else "backbeat", density="full", seed=3)
        starts = [h.start_beat for h in hits]
        assert starts == sorted(starts)

    def test_reinforces_bass_note_onsets_with_ghost_kicks(self):
        """Edge case: an off-the-grid bass onset (not near a beat
        boundary) must produce an extra soft kick to lock the pocket."""
        bass_notes = [BassNote(50, 1.5, 1.0)]
        hits = generate_drums(4.0, bass_notes, pattern="minimal", seed=1)
        ghost_kicks = [h for h in hits
                       if h.midi_note == DRUM_KIT["kick"] and h.start_beat == 1.5]
        assert len(ghost_kicks) == 1
        assert ghost_kicks[0].velocity == 45


# ===========================================================================
# _reinforce_bass_with_kick
# ===========================================================================

class TestReinforceBassWithKick:
    def test_notes_near_beat_boundary_are_not_double_reinforced(self):
        bass_notes = [BassNote(50, 0.0, 1.0), BassNote(48, 2.03, 1.0)]
        result = _reinforce_bass_with_kick(bass_notes, total_beats=4.0, priority_level=2)
        assert result == []

    def test_note_off_the_grid_gets_a_ghost_kick(self):
        bass_notes = [BassNote(52, 1.5, 1.0)]
        result = _reinforce_bass_with_kick(bass_notes, total_beats=4.0, priority_level=2)
        assert len(result) == 1
        assert result[0].midi_note == DRUM_KIT["kick"]
        assert result[0].start_beat == 1.5
        assert result[0].velocity == 45

    def test_notes_past_total_beats_are_ignored(self):
        bass_notes = [BassNote(50, 5.5, 1.0)]
        result = _reinforce_bass_with_kick(bass_notes, total_beats=4.0, priority_level=2)
        assert result == []


# ===========================================================================
# _apply_swing_to_drums
# ===========================================================================

class TestApplySwingToDrums:
    def test_straight_ratio_is_a_no_op(self):
        hits = [DrumHit(DRUM_KIT["hi_hat"], 0.5, 0.1, 60)]
        result = _apply_swing_to_drums(hits, swing_ratio=0.5, beats_per_bar=4)
        assert result == hits

    def test_only_hi_hat_and_ride_offbeats_are_displaced(self):
        hits = [
            DrumHit(DRUM_KIT["hi_hat"], 0.5, 0.1, 60),   # displaced
            DrumHit(DRUM_KIT["kick"], 0.5, 0.1, 60),     # same beat, wrong instrument
            DrumHit(DRUM_KIT["hi_hat"], 0.0, 0.1, 60),   # on-beat, untouched
        ]
        result = _apply_swing_to_drums(hits, swing_ratio=0.67, beats_per_bar=4)
        by_note_and_orig_beat = {(h.midi_note, round(h.start_beat, 2)) for h in result}
        assert (DRUM_KIT["hi_hat"], 0.67) in by_note_and_orig_beat
        assert (DRUM_KIT["kick"], 0.5) in by_note_and_orig_beat       # untouched
        assert (DRUM_KIT["hi_hat"], 0.0) in by_note_and_orig_beat     # untouched

    def test_ride_offbeat_also_displaced(self):
        hits = [DrumHit(DRUM_KIT["ride"], 1.5, 0.1, 60)]
        result = _apply_swing_to_drums(hits, swing_ratio=0.67, beats_per_bar=4)
        assert result[0].start_beat == pytest.approx(1.5 + (0.67 - 0.5))


# ===========================================================================
# generate_drums + swing integration
# ===========================================================================

class TestGenerateDrumsSwingIntegration:
    def test_swing_shifts_offbeat_hihats_in_full_pattern(self):
        straight = generate_drums(4.0, [], pattern="four_on_floor", density="full",
                                   beats_per_bar=4, swing=0.0, seed=1)
        swung = generate_drums(4.0, [], pattern="four_on_floor", density="full",
                                beats_per_bar=4, swing=1.0, seed=1)
        straight_offbeat_starts = sorted(
            h.start_beat for h in straight
            if h.midi_note == DRUM_KIT["hi_hat"] and abs(h.start_beat % 1.0 - 0.5) < 0.01
        )
        swung_same_notes = sorted(
            h.start_beat for h in swung
            if h.midi_note == DRUM_KIT["hi_hat"] and abs(h.start_beat % 1.0 - 0.5) >= 0.01
        )
        assert straight_offbeat_starts  # sanity: there are offbeats to swing
        assert swung_same_notes  # they moved off the exact half-beat grid


# ===========================================================================
# Bugfix regression: `groove` used to be a fully documented parameter that
# had zero effect. It now overrides `pattern` when the groove name also
# happens to be a defined drum pattern ("backbeat" or "halftime") -- the
# only case where a single-voice groove name has an unambiguous drum-kit
# meaning. Every other groove name remains a deliberate, documented no-op.
# ===========================================================================

class TestGrooveOverridesPatternWhenNamesOverlap:
    def test_groove_backbeat_produces_the_same_hits_as_explicit_pattern_backbeat(self):
        via_groove = generate_drums(4.0, [], pattern="four_on_floor", groove="backbeat",
                                     density="sparse", seed=1)
        via_explicit_pattern = generate_drums(4.0, [], pattern="backbeat",
                                               density="sparse", seed=1)
        assert via_groove == via_explicit_pattern

    def test_groove_halftime_produces_the_same_hits_as_explicit_pattern_halftime(self):
        via_groove = generate_drums(4.0, [], pattern="four_on_floor", groove="halftime",
                                     density="sparse", seed=1)
        via_explicit_pattern = generate_drums(4.0, [], pattern="halftime",
                                               density="sparse", seed=1)
        assert via_groove == via_explicit_pattern

    def test_groove_override_actually_changes_output_from_the_original_pattern(self):
        """Confirms this isn't a no-op that happens to coincide -- the
        overridden pattern's hits genuinely differ from what `pattern`
        alone would have produced."""
        without_groove = generate_drums(4.0, [], pattern="four_on_floor",
                                         density="sparse", seed=1)
        with_groove_override = generate_drums(4.0, [], pattern="four_on_floor",
                                               groove="backbeat", density="sparse", seed=1)
        assert without_groove != with_groove_override

    def test_non_matching_groove_name_remains_a_documented_no_op(self):
        """'shuffle' is a valid rhythm.py groove name but has no defined
        drum-kit mapping -- must not silently do anything to the pattern."""
        without_groove = generate_drums(4.0, [], pattern="minimal",
                                         density="sparse", seed=1)
        with_unmapped_groove = generate_drums(4.0, [], pattern="minimal",
                                               groove="shuffle", density="sparse", seed=1)
        assert without_groove == with_unmapped_groove

    def test_no_groove_is_unaffected(self):
        without_groove_kw = generate_drums(4.0, [], pattern="four_on_floor",
                                            density="sparse", seed=1)
        with_explicit_none = generate_drums(4.0, [], pattern="four_on_floor", groove=None,
                                             density="sparse", seed=1)
        assert without_groove_kw == with_explicit_none
