"""
Tests for intervals.music.rhythm — arc curves, boundary blending, the
groove pattern system, and swing timing. Pure, deterministic functions
(given an explicit seed); no schema or file I/O dependency.
"""
import math

import pytest

from intervals.music.rhythm import (
    GROOVES,
    VALID_GROOVES,
    RhythmEvent,
    apply_swing,
    arc_blend_bars,
    arc_multiplier,
    blended_arc_multiplier,
    get_pattern,
    groove_pattern,
    remap_swing_ratio,
    swing_offset,
)


# ===========================================================================
# arc_multiplier — curve shape at known positions
# ===========================================================================

class TestArcMultiplierSwell:
    def test_endpoints(self):
        assert arc_multiplier("swell", 0.0) == pytest.approx(0.75)
        assert arc_multiplier("swell", 1.0) == pytest.approx(1.10)

    def test_monotonically_increasing(self):
        ts = [0.0, 0.25, 0.5, 0.75, 1.0]
        values = [arc_multiplier("swell", t) for t in ts]
        assert values == sorted(values)
        assert values[0] < values[-1]


class TestArcMultiplierBuild:
    def test_endpoints(self):
        assert arc_multiplier("build", 0.0) == pytest.approx(0.70)
        assert arc_multiplier("build", 1.0) == pytest.approx(1.20)

    def test_monotonically_increasing(self):
        values = [arc_multiplier("build", t) for t in (0.0, 0.25, 0.5, 0.75, 1.0)]
        assert values == sorted(values)

    def test_steeper_rise_than_swell(self):
        """Docstring: build rises quadratically steeper than swell."""
        assert arc_multiplier("build", 1.0) > arc_multiplier("swell", 1.0)
        # Same relationship should already hold partway through the curve.
        assert arc_multiplier("build", 0.5) - arc_multiplier("build", 0.0) > (
            arc_multiplier("swell", 0.5) - arc_multiplier("swell", 0.0)
        )


class TestArcMultiplierFade:
    @pytest.mark.parametrize("arc_name", ["fade", "fade_out"])
    def test_endpoints(self, arc_name):
        assert arc_multiplier(arc_name, 0.0) == pytest.approx(1.00)
        assert arc_multiplier(arc_name, 1.0) == pytest.approx(0.65)

    @pytest.mark.parametrize("arc_name", ["fade", "fade_out"])
    def test_monotonically_decreasing(self, arc_name):
        values = [arc_multiplier(arc_name, t) for t in (0.0, 0.25, 0.5, 0.75, 1.0)]
        assert values == sorted(values, reverse=True)
        assert values[0] > values[-1]

    def test_fade_and_fade_out_are_aliases(self):
        for t in (0.0, 0.3, 0.7, 1.0):
            assert arc_multiplier("fade", t) == arc_multiplier("fade_out", t)


class TestArcMultiplierFadeIn:
    def test_endpoints(self):
        assert arc_multiplier("fade_in", 0.0) == pytest.approx(0.65)
        assert arc_multiplier("fade_in", 1.0) == pytest.approx(1.00)

    def test_monotonically_increasing(self):
        values = [arc_multiplier("fade_in", t) for t in (0.0, 0.25, 0.5, 0.75, 1.0)]
        assert values == sorted(values)


class TestArcMultiplierBreath:
    def test_edges_low_middle_high(self):
        """Arch shape: 0.85 at both edges, peaking at 1.15 in the middle."""
        assert arc_multiplier("breath", 0.0) == pytest.approx(0.85, abs=1e-9)
        assert arc_multiplier("breath", 1.0) == pytest.approx(0.85, abs=1e-9)
        assert arc_multiplier("breath", 0.5) == pytest.approx(1.15)

    def test_rises_then_falls(self):
        values = [arc_multiplier("breath", t) for t in (0.0, 0.25, 0.5, 0.75, 1.0)]
        # First half rises to the peak, second half falls back down.
        assert values[0] < values[1] < values[2]
        assert values[2] > values[3] > values[4]


class TestArcMultiplierPlateau:
    def test_always_flat_one(self):
        for t in (0.0, 0.3, 0.5, 0.8, 1.0):
            assert arc_multiplier("plateau", t) == 1.0


class TestArcMultiplierDecay:
    def test_endpoints(self):
        assert arc_multiplier("decay", 0.0) == pytest.approx(0.95)
        assert arc_multiplier("decay", 1.0) == pytest.approx(0.70)

    def test_monotonically_decreasing(self):
        values = [arc_multiplier("decay", t) for t in (0.0, 0.25, 0.5, 0.75, 1.0)]
        assert values == sorted(values, reverse=True)
        assert values[0] > values[-1]


class TestArcMultiplierUnknownAndClamping:
    def test_unknown_arc_name_is_neutral(self):
        for t in (0.0, 0.5, 1.0):
            assert arc_multiplier("not_a_real_arc", t) == 1.0

    def test_t_is_clamped_below_zero(self):
        """t outside [0, 1] is clamped before the curve formula runs, so an
        out-of-range t behaves exactly like its nearest boundary value."""
        assert arc_multiplier("build", -3.0) == arc_multiplier("build", 0.0)

    def test_t_is_clamped_above_one(self):
        assert arc_multiplier("build", 5.0) == arc_multiplier("build", 1.0)

    def test_all_curves_stay_within_documented_clamp_range(self):
        arcs = ["swell", "build", "fade", "fade_in", "breath", "plateau", "decay"]
        for arc in arcs:
            for t in (0.0, 0.1, 0.25, 0.5, 0.75, 0.9, 1.0):
                m = arc_multiplier(arc, t)
                assert 0.6 <= m <= 1.25


# ===========================================================================
# arc_blend_bars
# ===========================================================================

class TestArcBlendBars:
    def test_quarter_of_a_short_section(self):
        assert arc_blend_bars(8.0) == pytest.approx(2.0)

    def test_capped_at_four_bars_for_long_sections(self):
        assert arc_blend_bars(20.0) == pytest.approx(4.0)
        assert arc_blend_bars(100.0) == pytest.approx(4.0)

    def test_zero_bars_gives_zero_blend(self):
        assert arc_blend_bars(0.0) == 0.0

    def test_negative_bars_floored_at_zero(self):
        assert arc_blend_bars(-5.0) == 0.0


# ===========================================================================
# blended_arc_multiplier — boundary continuity, not a sharp cut
# ===========================================================================

class TestBlendedArcMultiplier:
    def test_no_previous_section_falls_back_to_own_curve(self):
        assert blended_arc_multiplier("swell", 0.3, prev_end=None, blend_t=0.2) == (
            arc_multiplier("swell", 0.3)
        )

    def test_zero_blend_length_falls_back_to_own_curve(self):
        assert blended_arc_multiplier("swell", 0.3, prev_end=0.9, blend_t=0.0) == (
            arc_multiplier("swell", 0.3)
        )

    def test_boundary_is_continuous_at_t_zero(self):
        """At t=0 the blended value must equal prev_end exactly -- the
        whole point of blending is no jump at the section boundary."""
        result = blended_arc_multiplier("swell", 0.0, prev_end=0.9, blend_t=0.2)
        assert result == pytest.approx(0.9)

    def test_reaches_own_curve_exactly_at_blend_end(self):
        result = blended_arc_multiplier("swell", 0.2, prev_end=0.9, blend_t=0.2)
        assert result == pytest.approx(arc_multiplier("swell", 0.2))

    def test_past_blend_end_matches_own_curve_unblended(self):
        result = blended_arc_multiplier("swell", 0.5, prev_end=0.9, blend_t=0.2)
        assert result == pytest.approx(arc_multiplier("swell", 0.5))

    def test_is_a_gradual_crossfade_not_a_sharp_cut(self):
        """The defining behavior this task asks to lock in: sampling
        several points across the blend window should show a smooth,
        monotonic glide from prev_end toward the arc's own curve --
        not an early jump straight to the destination value."""
        prev_end = 0.9
        blend_t = 0.4
        own_at_blend_end = arc_multiplier("swell", blend_t)
        assert prev_end > own_at_blend_end  # sanity: confirms this is a falling glide

        samples = [
            blended_arc_multiplier("swell", t, prev_end=prev_end, blend_t=blend_t)
            for t in (0.0, 0.1, 0.2, 0.3, 0.4)
        ]

        # Starts exactly at prev_end, ends exactly at the arc's own value.
        assert samples[0] == pytest.approx(prev_end)
        assert samples[-1] == pytest.approx(own_at_blend_end)

        # Monotonic glide from one to the other -- no point already at (or
        # past) the destination value before the blend window ends. A sharp
        # cut would show samples[1] jumping straight to own_at_blend_end
        # instead of easing toward it.
        assert samples == sorted(samples, reverse=True)
        for mid_value in samples[1:-1]:
            assert own_at_blend_end < mid_value < prev_end

    def test_crossfade_weight_is_linear(self):
        """At the blend window's midpoint, the result should sit exactly
        halfway between prev_end and the arc's own value at that point --
        confirms linear (not eased/stepped) interpolation."""
        prev_end = 0.9
        blend_t = 0.4
        t = 0.2  # halfway through the blend window
        own = arc_multiplier("swell", t)
        expected_midpoint = (prev_end + own) / 2.0

        result = blended_arc_multiplier("swell", t, prev_end=prev_end, blend_t=blend_t)
        assert result == pytest.approx(expected_midpoint)


# ===========================================================================
# Groove templates and groove_pattern()
# ===========================================================================

class TestGrooveTemplates:
    def test_valid_grooves_matches_groove_keys(self):
        assert set(VALID_GROOVES) == set(GROOVES.keys())

    def test_every_groove_has_at_least_one_priority_one_slot(self):
        """Priority 1 = primary, must always play even at sparse density --
        a groove with none would make sparse density silent."""
        for name, slots in GROOVES.items():
            assert any(s.priority == 1 for s in slots), (
                f"groove '{name}' has no priority-1 (primary) slot"
            )


class TestGroovePattern:
    def test_missing_seed_raises(self):
        with pytest.raises(ValueError, match="explicit seed"):
            groove_pattern(4.0, groove="straight", seed=None)

    def test_unknown_groove_raises(self):
        with pytest.raises(ValueError, match="Unknown groove"):
            groove_pattern(4.0, groove="bogus_groove", seed=1)

    def test_sparse_density_plays_only_primary_slots(self):
        """'straight' groove, one 4/4 bar: priority-1 slots are beat 0.0
        (vel 1.00) and beat 2.0 (vel 0.95) -- the accented 1 and 3."""
        events = groove_pattern(4.0, groove="straight", density="sparse",
                                 beats_per_bar=4, seed=1)
        assert [(e.start_beat, e.velocity_scale) for e in events] == [
            (0.0, 1.00), (2.0, 0.95),
        ]

    def test_medium_density_adds_priority_two_slots(self):
        events = groove_pattern(4.0, groove="straight", density="medium",
                                 beats_per_bar=4, seed=1)
        assert [e.start_beat for e in events] == [0.0, 1.0, 2.0, 3.0]

    def test_full_density_matches_medium_when_no_priority_three_slots(self):
        """'straight' has no ghost/fill (priority 3) slots at all, so
        full density degenerates to exactly the same set as medium."""
        medium = groove_pattern(4.0, groove="straight", density="medium",
                                 beats_per_bar=4, seed=1)
        full = groove_pattern(4.0, groove="straight", density="full",
                               beats_per_bar=4, seed=1)
        assert medium == full

    def test_full_density_adds_ghost_slots_for_a_groove_that_has_them(self):
        """'push' has a priority-3 ghost slot at beat 1.5 -- present at
        full density, absent at medium."""
        medium = groove_pattern(4.0, groove="push", density="medium",
                                 beats_per_bar=4, seed=1)
        full = groove_pattern(4.0, groove="push", density="full",
                               beats_per_bar=4, seed=1)
        assert 1.5 not in [e.start_beat for e in medium]
        assert 1.5 in [e.start_beat for e in full]

    def test_events_are_sorted_by_start_beat(self):
        events = groove_pattern(8.0, groove="syncopated", density="full",
                                 beats_per_bar=4, seed=3)
        starts = [e.start_beat for e in events]
        assert starts == sorted(starts)

    def test_deterministic_with_same_seed(self):
        a = groove_pattern(8.0, groove="broken", density="full",
                            beats_per_bar=4, seed=42)
        b = groove_pattern(8.0, groove="broken", density="full",
                            beats_per_bar=4, seed=42)
        assert a == b

    def test_seed_does_not_affect_output_with_zero_rest_probability(self):
        """rest_probability defaults to 0.0, so is_rest is never True
        regardless of what the RNG draws -- output should be seed-
        independent in that case."""
        a = groove_pattern(4.0, groove="straight", density="medium",
                            beats_per_bar=4, seed=1)
        b = groove_pattern(4.0, groove="straight", density="medium",
                            beats_per_bar=4, seed=999)
        assert a == b

    def test_low_density_always_includes_primary_slots(self):
        """'low' density sits between sparse and medium: primary slots
        always play, secondary slots appear probabilistically per bar --
        but the primaries must be there in every bar regardless of seed."""
        for seed in (1, 2, 3, 4, 5):
            events = groove_pattern(8.0, groove="straight", density="low",
                                     beats_per_bar=4, seed=seed)
            starts = {e.start_beat for e in events}
            assert {0.0, 2.0, 4.0, 6.0} <= starts

    def test_low_density_deterministic_with_same_seed(self):
        a = groove_pattern(8.0, groove="straight", density="low",
                            beats_per_bar=4, seed=7)
        b = groove_pattern(8.0, groove="straight", density="low",
                            beats_per_bar=4, seed=7)
        assert a == b

    def test_waltz_groove_with_three_beats_per_bar(self):
        events = groove_pattern(3.0, groove="waltz", density="medium",
                                 beats_per_bar=3, seed=1)
        assert [e.start_beat for e in events] == [0.0, 1.0, 2.0]


# ===========================================================================
# get_pattern() — groove-aware dispatch
# ===========================================================================

class TestGetPattern:
    def test_groove_argument_delegates_to_groove_pattern(self):
        via_get_pattern = get_pattern(
            4.0, density="sparse", voice_type="melody",
            groove="straight", beats_per_bar=4, seed=1,
        )
        via_groove_pattern = groove_pattern(
            4.0, groove="straight", density="sparse",
            beats_per_bar=4, rest_probability=0.12, seed=1,
        )
        assert via_get_pattern == via_groove_pattern

    def test_unknown_density_voice_type_combo_without_groove_raises(self):
        with pytest.raises(ValueError, match="No pattern for"):
            get_pattern(4.0, density="bogus_density", voice_type="bogus_voice", seed=1)

    def test_default_grid_path_still_returns_events_without_groove(self):
        """Sanity check that the non-groove (density-grid) path is intact
        and unaffected by the groove system living alongside it."""
        events = get_pattern(8.0, density="medium", voice_type="bass", seed=1)
        assert len(events) > 0
        assert all(isinstance(e, RhythmEvent) for e in events)


# ===========================================================================
# remap_swing_ratio — public 0.0-1.0 scale -> internal 0.5-1.0 scale
# ===========================================================================

class TestRemapSwingRatio:
    def test_zero_maps_to_straight(self):
        assert remap_swing_ratio(0.0) == pytest.approx(0.5)

    def test_negative_maps_to_straight(self):
        """Safety net -- callers should already guard with `if swing > 0`,
        but a negative value must not compute an offset below straight."""
        assert remap_swing_ratio(-0.5) == pytest.approx(0.5)

    def test_full_swing_maps_to_heaviest(self):
        assert remap_swing_ratio(1.0) == pytest.approx(1.0)

    def test_midpoint_public_value(self):
        assert remap_swing_ratio(0.5) == pytest.approx(0.75)

    def test_above_one_is_clamped_to_heaviest(self):
        assert remap_swing_ratio(2.0) == pytest.approx(1.0)

    def test_monotonically_increasing_over_valid_range(self):
        values = [remap_swing_ratio(s) for s in (0.0, 0.2, 0.5, 0.8, 1.0)]
        assert values == sorted(values)
        assert values[0] < values[-1]


# ===========================================================================
# swing_offset — per-onset displacement
# ===========================================================================

class TestSwingOffset:
    def test_straight_ratio_never_offsets_anything(self):
        """swing_ratio == 0.5 (straight) is a no-op regardless of beat
        position -- even squarely on an offbeat eighth."""
        assert swing_offset(0.5, swing_ratio=0.5) == 0.0
        assert swing_offset(1.5, swing_ratio=0.5) == 0.0

    def test_on_beat_position_is_untouched(self):
        """Swing only ever displaces offbeat eighths -- an on-the-beat
        onset (whole-number beat) has nothing to move."""
        assert swing_offset(0.0, swing_ratio=0.67) == 0.0
        assert swing_offset(1.0, swing_ratio=0.67) == 0.0
        assert swing_offset(2.0, swing_ratio=0.67) == 0.0

    def test_offbeat_eighth_is_delayed_by_ratio_minus_half(self):
        offset = swing_offset(0.5, swing_ratio=0.67)
        assert offset == pytest.approx(0.17)

    def test_offbeat_detection_is_beat_local_not_absolute(self):
        """The &-of-1 (beat 0.5) and the &-of-2 (beat 1.5) get the same
        offset -- detection is beat % 1.0, not the absolute position."""
        assert swing_offset(0.5, swing_ratio=0.67) == pytest.approx(
            swing_offset(1.5, swing_ratio=0.67)
        )

    def test_within_tolerance_of_offbeat_still_triggers(self):
        assert swing_offset(0.505, swing_ratio=0.67) == pytest.approx(0.17)

    def test_outside_tolerance_of_offbeat_does_not_trigger(self):
        assert swing_offset(0.52, swing_ratio=0.67) == 0.0

    def test_heavier_swing_ratio_gives_larger_offset(self):
        light = swing_offset(0.5, swing_ratio=0.6)
        heavy = swing_offset(0.5, swing_ratio=0.9)
        assert heavy > light


# ===========================================================================
# apply_swing — blanket post-pass over a finished event list
# ===========================================================================

class TestApplySwing:
    def test_on_beat_events_pass_through_unchanged(self):
        events = [RhythmEvent(0.0, 1.0, 1.0, False)]
        result = apply_swing(events, swing_ratio=0.67)
        assert result == events

    def test_offbeat_event_is_delayed_and_shortened(self):
        events = [RhythmEvent(0.5, 0.5, 0.8, False)]
        result = apply_swing(events, swing_ratio=0.67)
        assert len(result) == 1
        swung = result[0]
        assert swung.start_beat == pytest.approx(0.67)
        assert swung.duration_beats == pytest.approx(0.33)
        # Velocity and rest flag are untouched -- swing only moves timing.
        assert swung.velocity_scale == 0.8
        assert swung.is_rest is False

    def test_straight_ratio_leaves_every_event_untouched(self):
        events = [
            RhythmEvent(0.0, 1.0, 1.0, False),
            RhythmEvent(0.5, 0.5, 0.8, False),
            RhythmEvent(1.5, 0.5, 0.7, False),
        ]
        result = apply_swing(events, swing_ratio=0.5)
        assert result == events

    def test_duration_is_floored_at_point_one_beat(self):
        """A very short offbeat note under heavy swing must not shrink to
        zero or negative duration -- floored at 0.1 beats."""
        events = [RhythmEvent(0.5, 0.15, 1.0, False)]
        result = apply_swing(events, swing_ratio=0.75)
        assert result[0].duration_beats == pytest.approx(0.1)

    def test_mixed_on_and_off_beat_events_in_one_pass(self):
        events = [
            RhythmEvent(0.0, 1.0, 1.0, False),
            RhythmEvent(0.5, 0.5, 0.8, False),
            RhythmEvent(1.0, 1.0, 1.0, False),
        ]
        result = apply_swing(events, swing_ratio=0.67)
        starts = [e.start_beat for e in result]
        assert starts[0] == pytest.approx(0.0)   # on-beat, untouched
        assert starts[1] == pytest.approx(0.67)  # offbeat, delayed
        assert starts[2] == pytest.approx(1.0)   # on-beat, untouched

    def test_preserves_event_count_and_order(self):
        events = [
            RhythmEvent(0.0, 1.0, 1.0, False),
            RhythmEvent(0.5, 0.5, 0.8, False),
            RhythmEvent(1.0, 1.0, 1.0, False),
            RhythmEvent(1.5, 0.5, 0.7, False),
        ]
        result = apply_swing(events, swing_ratio=0.67)
        assert len(result) == len(events)
