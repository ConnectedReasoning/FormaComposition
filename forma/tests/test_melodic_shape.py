"""
Tests for intervals.music.melodic_shape — the apex/goal-tone mechanism,
Phase 1: built and tested in complete isolation before any of the four
melody behaviors (generative, lyrical, sparse, develop) are wired to it.
"""
import pytest

from intervals.music.melodic_shape import (
    APEX_BIAS_STRENGTH,
    CADENCE_BIAS_STRENGTH,
    CADENCE_RESOLUTION_THRESHOLD,
    ANCHOR_SHIFT_MAX_STEP,
    resolve_apex_pitch,
    apex_degree_reachable,
    apex_weighted_candidates,
    cadence_weighted_candidates,
    directed_anchor_shift,
)


C_IONIAN = [60, 62, 64, 65, 67, 69, 71]  # C4..B4, pcs [0,2,4,5,7,9,11]


class TestResolveApexPitch:
    def test_places_target_near_anchor_octave(self):
        # degree 4 (dominant, G) near anchor C4 (60) -> G4 (67), the
        # SAME octave as the anchor, not some fixed reference octave.
        assert resolve_apex_pitch(4, C_IONIAN, 48, 84, anchor=60) == 67

    def test_places_target_near_a_higher_anchor_octave(self):
        # Same degree 4, anchor now C5 (72) -> should resolve to G5 (79),
        # tracking the anchor's octave, not staying pinned near C4.
        assert resolve_apex_pitch(4, C_IONIAN, 48, 96, anchor=72) == 79

    def test_folds_into_register_when_anchor_octave_placement_overshoots(self):
        # Degree 9 (two octaves' worth of steps up from a degree-2 anchor)
        # pushed above a tight register must fold back down by whole
        # octaves, landing on the SAME pitch class each time.
        pitch = resolve_apex_pitch(9, C_IONIAN, 60, 72, anchor=62)
        assert 60 <= pitch <= 72
        assert pitch % 12 in {p % 12 for p in C_IONIAN}

    def test_never_raises_for_an_extreme_degree(self):
        # Absurdly large degree must still fold to something playable,
        # never crash the render (Phase 0: unreachable is a lint warning,
        # never a render-time failure).
        pitch = resolve_apex_pitch(500, C_IONIAN, 48, 84, anchor=60)
        assert 48 <= pitch <= 84

    def test_result_is_always_a_genuine_scale_tone(self):
        pcs = {p % 12 for p in C_IONIAN}
        for degree in range(-10, 20):
            pitch = resolve_apex_pitch(degree, C_IONIAN, 48, 84, anchor=60)
            assert pitch % 12 in pcs


class TestApexDegreeReachable:
    def test_tonic_is_reachable_in_a_normal_register(self):
        assert apex_degree_reachable(0, C_IONIAN, 48, 84) is True

    def test_dominant_is_reachable_in_a_normal_register(self):
        assert apex_degree_reachable(4, C_IONIAN, 48, 84) is True

    def test_unreachable_in_a_narrow_register(self):
        """
        Regression note: this test originally asserted degree 9 was
        unreachable in a full one-octave register (60-71), reasoning
        that "9 steps is more than an octave, so it can't fit in a
        one-octave window." That reasoning was actually wrong, caught
        during Phase 6 while writing the lint check that consumes this
        function: apex_degree_reachable doesn't need degree 9 to be
        voiced 9 steps above a co-located tonic instance -- it only
        needs THAT degree's pitch class to recur somewhere in the
        window, in any octave, and a diatonic scale's degrees recur
        every 12 semitones regardless of how "far" the degree number
        looks. degree 9 mod 7 = degree 2 (E in C ionian), and E
        genuinely does fall inside 60-71 (at 64) -- confirmed
        independently by resolve_apex_pitch, which was never buggy,
        agreeing on the exact same placement. A real unreachable case
        needs a window too narrow to contain the target pitch class in
        ANY octave, not just "a large-looking degree number."
        """
        assert apex_degree_reachable(9, C_IONIAN, 60, 62) is False

    def test_reachable_once_register_is_widened_to_fit(self):
        # Same narrow case, register widened enough to contain the
        # target pitch class -- confirms the function is genuinely
        # register-sensitive, not just always False for a small window.
        assert apex_degree_reachable(9, C_IONIAN, 60, 71) is True

    def test_extreme_degree_still_correctly_evaluated(self):
        # An absurd degree value must still be handled gracefully and
        # correctly (Phase 0: never crash), not just avoid raising.
        assert apex_degree_reachable(500, C_IONIAN, 60, 71) is False


class TestApexWeightedCandidates:
    def test_approaching_prefers_candidates_closer_to_apex(self):
        # current=60, apex=72 (an octave up), approaching (before
        # apex_position). 65 is closer to 72 than 60 is; 55 is farther.
        result = apex_weighted_candidates(
            candidates=[55, 65], current=60, apex_pitch=72,
            position_t=0.2, apex_position=0.7,
        )
        assert result.count(65) > result.count(55)

    def test_receding_prefers_candidates_farther_from_apex(self):
        # Same setup, but past apex_position now -- preference flips.
        result = apex_weighted_candidates(
            candidates=[55, 65], current=60, apex_pitch=72,
            position_t=0.9, apex_position=0.7,
        )
        assert result.count(55) > result.count(65)

    def test_strength_controls_repetition_count_exactly(self):
        result = apex_weighted_candidates(
            candidates=[55, 65], current=60, apex_pitch=72,
            position_t=0.2, apex_position=0.7, strength=5,
        )
        assert result.count(65) == 5
        assert result.count(55) == 1

    def test_never_empty_and_never_excludes_a_candidate(self):
        result = apex_weighted_candidates(
            candidates=[55, 65], current=60, apex_pitch=72,
            position_t=0.2, apex_position=0.7,
        )
        assert 55 in result and 65 in result

    def test_no_preferred_candidate_returns_input_unchanged(self):
        # Single candidate can't be "closer than itself" -- current ==
        # candidate, distance comparison is never strictly less, so
        # nothing is preferred and the list passes through as-is.
        result = apex_weighted_candidates(
            candidates=[60], current=60, apex_pitch=72,
            position_t=0.2, apex_position=0.7,
        )
        assert result == [60]

    def test_current_already_past_apex_self_corrects(self):
        # current=80 has already overshot apex_pitch=72. Approaching
        # phase should still prefer whichever candidate is CLOSER to 72,
        # even though that means preferring a candidate below current --
        # "closer" self-corrects regardless of overshoot direction.
        result = apex_weighted_candidates(
            candidates=[70, 90], current=80, apex_pitch=72,
            position_t=0.2, apex_position=0.7,
        )
        assert result.count(70) > result.count(90)

    def test_default_strength_matches_module_constant(self):
        result = apex_weighted_candidates(
            candidates=[55, 65], current=60, apex_pitch=72,
            position_t=0.2, apex_position=0.7,
        )
        assert result.count(65) == APEX_BIAS_STRENGTH


class TestCadenceWeightedCandidates:
    def test_prefers_resolution_pitch_itself(self):
        result = cadence_weighted_candidates(
            candidates=[60, 64, 67], resolution_pitch=60,
        )
        assert result.count(60) > result.count(64)
        assert result.count(60) > result.count(67)

    def test_threshold_includes_near_misses(self):
        # 61 is within CADENCE_RESOLUTION_THRESHOLD (2 semitones) of the
        # resolution pitch 60 -- should be weighted, not just an exact
        # match.
        result = cadence_weighted_candidates(
            candidates=[61, 67], resolution_pitch=60,
        )
        assert result.count(61) > result.count(67)

    def test_threshold_excludes_far_candidates(self):
        # 67 is 7 semitones from 60 -- well past the threshold, must not
        # be preferentially weighted even though it's a plausible chord
        # tone in other contexts.
        result = cadence_weighted_candidates(
            candidates=[61, 67], resolution_pitch=60,
        )
        assert result.count(67) == 1

    def test_strength_controls_repetition_count_exactly(self):
        result = cadence_weighted_candidates(
            candidates=[60, 67], resolution_pitch=60, strength=6,
        )
        assert result.count(60) == 6
        assert result.count(67) == 1

    def test_never_empty_and_never_excludes_a_candidate(self):
        result = cadence_weighted_candidates(
            candidates=[60, 67], resolution_pitch=60,
        )
        assert 60 in result and 67 in result

    def test_no_resolving_candidate_returns_input_unchanged(self):
        result = cadence_weighted_candidates(
            candidates=[66, 74], resolution_pitch=60,
        )
        assert result == [66, 74]

    def test_default_strength_matches_module_constant(self):
        result = cadence_weighted_candidates(
            candidates=[60, 67], resolution_pitch=60,
        )
        assert result.count(60) == CADENCE_BIAS_STRENGTH

    def test_default_threshold_matches_module_constant(self):
        boundary = 60 + CADENCE_RESOLUTION_THRESHOLD
        just_outside = boundary + 1
        result = cadence_weighted_candidates(
            candidates=[boundary, just_outside], resolution_pitch=60,
        )
        assert result.count(boundary) > 1
        assert result.count(just_outside) == 1


class TestDirectedAnchorShift:
    """
    Phase 4's develop-specific mechanism -- see melodic_shape.py's Phase 4
    module note on why this differs from apex_weighted_candidates/
    cadence_weighted_candidates rather than reusing them: develop has no
    per-note candidate list, only an anchor each retile builds an entire
    statement from.
    """

    def test_approaching_shifts_toward_target(self):
        # anchor=60 (C4), target=72 (C5, an octave up). Before
        # apex_position: shifts toward it, capped at the default 2
        # diatonic steps.
        result = directed_anchor_shift(60, 72, C_IONIAN, position_t=0.2, apex_position=0.7)
        assert result == 64

    def test_receding_shifts_away_from_target(self):
        # Same anchor/target, but past apex_position: shifts the OTHER
        # way -- the phrase settles back down after its declared peak
        # instead of continuing to climb.
        result = directed_anchor_shift(60, 72, C_IONIAN, position_t=0.9, apex_position=0.7)
        assert result == 57
        # Confirm it's genuinely the opposite direction from approaching,
        # not just a different magnitude.
        approaching_result = directed_anchor_shift(60, 72, C_IONIAN, position_t=0.2, apex_position=0.7)
        assert result < 60 < approaching_result

    def test_shift_is_capped_regardless_of_target_distance(self):
        # target is 3 octaves up (21 diatonic degrees away) -- the shift
        # must still be capped at max_step_degrees, not scale with
        # distance. Same result as the one-octave case above confirms
        # the cap is doing its job, not coincidence.
        result = directed_anchor_shift(60, 96, C_IONIAN, position_t=0.2, apex_position=0.7)
        assert result == 64

    def test_custom_max_step_is_respected(self):
        result = directed_anchor_shift(60, 72, C_IONIAN, position_t=0.2,
                                        apex_position=0.7, max_step_degrees=1)
        # One diatonic step up from C4 (degree-wise) lands on D4.
        assert result == 62

    def test_already_at_target_returns_anchor_unchanged(self):
        result = directed_anchor_shift(64, 64, C_IONIAN, position_t=0.2, apex_position=0.7)
        assert result == 64

    def test_cadence_reuse_pattern_always_approaches(self):
        """Cadence has no 'settle after' phase -- callers get that by
        passing position_t=0.0, apex_position=1.0 (position_t is always
        < apex_position, forcing the approaching branch unconditionally),
        rather than needing a second, near-duplicate function."""
        result = directed_anchor_shift(60, 72, C_IONIAN, position_t=0.0, apex_position=1.0)
        approaching_result = directed_anchor_shift(60, 72, C_IONIAN, position_t=0.2, apex_position=0.7)
        assert result == approaching_result == 64

    def test_default_max_step_matches_module_constant(self):
        result_default = directed_anchor_shift(60, 72, C_IONIAN, position_t=0.2, apex_position=0.7)
        result_explicit = directed_anchor_shift(60, 72, C_IONIAN, position_t=0.2,
                                                  apex_position=0.7,
                                                  max_step_degrees=ANCHOR_SHIFT_MAX_STEP)
        assert result_default == result_explicit
