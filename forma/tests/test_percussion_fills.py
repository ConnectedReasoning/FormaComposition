"""
Tests for the fill mechanism added to intervals.music.percussion:
_compute_fill_bar_groups, _generate_fill_slots, _select_slots_for_bar,
and generate_drums()'s `fill` kwarg end-to-end.
"""
import pytest

from intervals.music.percussion import (
    DRUM_KIT,
    _compute_fill_bar_groups,
    _generate_fill_slots,
    _select_slots_for_bar,
    generate_drums,
)


# ===========================================================================
# _compute_fill_bar_groups
# ===========================================================================

class TestComputeFillBarGroups:
    def test_phrase_end_single_bar(self):
        groups = _compute_fill_bar_groups(
            {"placement": "phrase_end", "phrase_bars": 8, "bars": 1}, total_bars=16,
        )
        assert [list(g) for g in groups] == [[7], [15]]

    def test_phrase_end_multi_bar_span(self):
        groups = _compute_fill_bar_groups(
            {"placement": "phrase_end", "phrase_bars": 8, "bars": 2}, total_bars=16,
        )
        assert [list(g) for g in groups] == [[6, 7], [14, 15]]

    def test_phrase_end_section_shorter_than_phrase_yields_no_groups(self):
        groups = _compute_fill_bar_groups(
            {"placement": "phrase_end", "phrase_bars": 8, "bars": 1}, total_bars=4,
        )
        assert groups == []

    def test_section_end_single_bar(self):
        groups = _compute_fill_bar_groups(
            {"placement": "section_end", "bars": 1}, total_bars=16,
        )
        assert [list(g) for g in groups] == [[15]]

    def test_section_end_multi_bar_span(self):
        groups = _compute_fill_bar_groups(
            {"placement": "section_end", "bars": 3}, total_bars=16,
        )
        assert [list(g) for g in groups] == [[13, 14, 15]]

    def test_section_end_bars_clamped_to_available_bars(self):
        # bars=5 requested but section is only 3 bars — start clamps to 0,
        # never a negative bar index.
        groups = _compute_fill_bar_groups(
            {"placement": "section_end", "bars": 5}, total_bars=3,
        )
        assert [list(g) for g in groups] == [[0, 1, 2]]

    def test_zero_total_bars_yields_no_groups(self):
        assert _compute_fill_bar_groups({"placement": "section_end"}, total_bars=0) == []


# ===========================================================================
# _generate_fill_slots
# ===========================================================================

class TestGenerateFillSlots:
    def test_default_16th_note_count(self):
        slots = _generate_fill_slots({}, beats_per_bar=4)
        # subdivision default 0.25 over 4 beats -> 16 onsets
        assert len(slots) == 16

    def test_all_slots_are_the_requested_instrument(self):
        slots = _generate_fill_slots({"instrument": "snare"}, beats_per_bar=4)
        assert all(s[0] == "snare" for s in slots)

    def test_velocity_ramps_start_to_end(self):
        slots = _generate_fill_slots(
            {"velocity_start": 0.2, "velocity_end": 1.0, "subdivision": 1.0},
            beats_per_bar=4,
        )
        velocities = [s[2] for s in slots]
        assert velocities[0] == pytest.approx(0.2)
        assert velocities[-1] == pytest.approx(1.0)
        assert velocities == sorted(velocities)  # monotonic ramp

    def test_single_onset_uses_velocity_end(self):
        # n == 1 (subdivision >= beats_per_bar): t branch must not divide by zero
        slots = _generate_fill_slots(
            {"subdivision": 8.0, "velocity_start": 0.3, "velocity_end": 0.9},
            beats_per_bar=4,
        )
        assert len(slots) == 1
        assert slots[0][2] == pytest.approx(0.9)

    def test_onsets_stay_within_the_bar(self):
        slots = _generate_fill_slots({"subdivision": 0.25}, beats_per_bar=4)
        assert all(0.0 <= s[1] < 4.0 for s in slots)


# ===========================================================================
# _select_slots_for_bar
# ===========================================================================

class TestSelectSlotsForBar:
    def test_no_fill_is_identity(self):
        slots = [("kick", 0.0, 1.0, 1)]
        result = _select_slots_for_bar(slots, bar_index=0, fill=None,
                                        fill_bar_set=set(), beats_per_bar=4)
        assert result == slots

    def test_bar_not_in_fill_set_is_identity(self):
        slots = [("kick", 0.0, 1.0, 1)]
        result = _select_slots_for_bar(
            slots, bar_index=0, fill={"instrument": "hi_hat"},
            fill_bar_set={7}, beats_per_bar=4,
        )
        assert result == slots

    def test_fill_bar_strips_only_target_instrument(self):
        slots = [("kick", 0.0, 1.0, 1), ("hi_hat", 0.0, 0.6, 1), ("hi_hat", 0.5, 0.5, 2)]
        result = _select_slots_for_bar(
            slots, bar_index=7, fill={"instrument": "hi_hat", "subdivision": 1.0},
            fill_bar_set={7}, beats_per_bar=4,
        )
        # kick survives untouched (design decision: kick keeps going under a fill)
        assert ("kick", 0.0, 1.0, 1) in result
        # original hi_hat slots are gone
        assert ("hi_hat", 0.0, 0.6, 1) not in result
        assert ("hi_hat", 0.5, 0.5, 2) not in result
        # replaced with fill-generated hi_hat slots
        assert all(s[0] == "hi_hat" for s in result if s[0] == "hi_hat")
        assert len([s for s in result if s[0] == "hi_hat"]) == 4  # subdivision=1.0 over 4 beats


# ===========================================================================
# generate_drums — fill integration, determinism, regression safety
# ===========================================================================

class TestGenerateDrumsWithFill:
    def test_fill_none_matches_no_fill_kwarg_at_all(self):
        # Explicit fill=None must be byte-identical to omitting the kwarg —
        # regression guarantee for every pre-existing caller.
        a = generate_drums(32.0, [], pattern="four_on_floor", density="full", seed=42)
        b = generate_drums(32.0, [], pattern="four_on_floor", density="full", seed=42, fill=None)
        assert a == b

    def test_fill_fires_on_expected_bar(self):
        hits = generate_drums(
            32.0, [], pattern="four_on_floor", density="full", seed=42,
            fill={"placement": "phrase_end", "phrase_bars": 8, "bars": 1,
                  "instrument": "hi_hat", "subdivision": 0.25, "probability": 1.0},
        )
        # bar 7 (beats 28-32) and bar 15 don't exist (section is only 32 beats
        # = 8 bars), so only bar 7 should show fill-density hi_hats
        bar7_hats = [h for h in hits if h.midi_note == DRUM_KIT["hi_hat"] and 28.0 <= h.start_beat < 32.0]
        assert len(bar7_hats) == 16  # 16th notes across 4 beats

    def test_probability_zero_produces_no_fill(self):
        with_fill = generate_drums(
            32.0, [], pattern="four_on_floor", density="full", seed=42,
            fill={"placement": "phrase_end", "phrase_bars": 8, "bars": 1,
                  "instrument": "hi_hat", "probability": 0.0},
        )
        without_fill = generate_drums(32.0, [], pattern="four_on_floor", density="full", seed=42)
        assert with_fill == without_fill

    def test_deterministic_under_fixed_seed(self):
        kwargs = dict(
            total_beats=64.0, bass_notes=[], pattern="four_on_floor", density="full", seed=7,
            fill={"placement": "phrase_end", "phrase_bars": 8, "bars": 2,
                  "instrument": "hi_hat", "probability": 0.5},
        )
        a = generate_drums(**kwargs)
        b = generate_drums(**kwargs)
        assert a == b

    def test_kick_untouched_by_hi_hat_fill(self):
        # Design decision confirmed with the composer: fills replace one
        # instrument's part for the bar; the rest of the kit (kick) keeps
        # playing underneath rather than dropping out.
        no_fill = generate_drums(32.0, [], pattern="four_on_floor", density="full", seed=42)
        with_fill = generate_drums(
            32.0, [], pattern="four_on_floor", density="full", seed=42,
            fill={"placement": "phrase_end", "phrase_bars": 8, "bars": 1,
                  "instrument": "hi_hat", "probability": 1.0},
        )
        no_fill_kicks = [h.start_beat for h in no_fill if h.midi_note == DRUM_KIT["kick"]]
        with_fill_kicks = [h.start_beat for h in with_fill if h.midi_note == DRUM_KIT["kick"]]
        assert no_fill_kicks == with_fill_kicks

    def test_multi_bar_fill_group_gated_by_single_probability_roll(self):
        # With probability=0 the whole 2-bar group must be absent, never a
        # partial fill on just one of the two bars.
        hits = generate_drums(
            32.0, [], pattern="four_on_floor", density="full", seed=1,
            fill={"placement": "phrase_end", "phrase_bars": 8, "bars": 2,
                  "instrument": "hi_hat", "probability": 0.0},
        )
        baseline = generate_drums(32.0, [], pattern="four_on_floor", density="full", seed=1)
        assert hits == baseline

    def test_swing_touches_only_fill_onsets_that_land_exactly_on_the_half_beat(self):
        # CORRECTION to earlier claim: _apply_swing_to_drums()'s gate is
        # "beat-fraction exactly 0.5 AND hi_hat/ride" -- it has no concept
        # of "this onset came from a fill". A 16th-note (0.25) fill's grid
        # includes the 0.5 point every other onset, so those onsets DO get
        # swung (moved off their straight position) while the rest don't.
        # "Fills pass through swing untouched" was wrong; the accurate claim
        # is "only the subset of fill onsets that coincide with the
        # eighth-note offbeat get swung, same as any other hi_hat hit would."
        # (Comparing by value-membership, not by sorted index, since a
        # shifted onset can reorder past its neighbors after sorting.)
        hits = generate_drums(
            32.0, [], pattern="four_on_floor", density="full", seed=42, swing=0.8,
            fill={"placement": "phrase_end", "phrase_bars": 8, "bars": 1,
                  "instrument": "hi_hat", "subdivision": 0.25, "probability": 1.0},
        )
        bar7_beats = {round(h.start_beat, 6) for h in hits
                      if h.midi_note == DRUM_KIT["hi_hat"] and 28.0 <= h.start_beat < 32.0}
        straight = [28.0 + i * 0.25 for i in range(16)]
        on_half_beat = [b for b in straight if abs((b % 1.0) - 0.5) < 0.01]
        off_half_beat = [b for b in straight if abs((b % 1.0) - 0.5) >= 0.01]

        # Half-beat onsets got moved -- their original straight position is gone.
        for b in on_half_beat:
            assert round(b, 6) not in bar7_beats, f"{b} should have been swung off its straight position"
        # Everything else stayed exactly where it was.
        for b in off_half_beat:
            assert round(b, 6) in bar7_beats, f"{b} should be untouched by swing"
