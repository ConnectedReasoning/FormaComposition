"""
Tests for intervals.core.musical_time — MusicalTime and its module-level
helpers. Pure, deterministic, no I/O and no dependency on schemas being
called correctly (see Task 2 rationale).
"""
import pytest

from intervals.core.musical_time import (
    MusicalTime,
    bar_beat_from_event_offset,
    beats_to_bar_and_local,
    is_downbeat_float,
)


# ===========================================================================
# Construction
# ===========================================================================

class TestConstruction:
    def test_valid_construction(self):
        t = MusicalTime(bar=2, beat=1.5, beats_per_bar=4)
        assert t.bar == 2
        assert t.beat == 1.5
        assert t.beats_per_bar == 4

    def test_invalid_beats_per_bar_less_than_one(self):
        with pytest.raises(ValueError, match="beats_per_bar must be >= 1"):
            MusicalTime(bar=0, beat=0.0, beats_per_bar=0)

    def test_invalid_negative_beat(self):
        with pytest.raises(ValueError, match="beat must be >= 0"):
            MusicalTime(bar=0, beat=-0.5, beats_per_bar=4)

    def test_invalid_beat_out_of_range_for_bar(self):
        """beat must stay within [0, beats_per_bar) -- crossing a bar
        boundary is add_beats()'s job, not a raw constructor value."""
        with pytest.raises(ValueError, match="out of range"):
            MusicalTime(bar=0, beat=4.0, beats_per_bar=4)

    def test_immutable(self):
        t = MusicalTime(bar=0, beat=0.0, beats_per_bar=4)
        with pytest.raises(AttributeError, match="immutable"):
            t.bar = 5


# ===========================================================================
# Core properties / predicates
# ===========================================================================

class TestCoreProperties:
    def test_is_downbeat_true_at_beat_zero(self):
        assert MusicalTime(bar=3, beat=0.0, beats_per_bar=4).is_downbeat() is True

    def test_is_downbeat_false_elsewhere(self):
        assert MusicalTime(bar=3, beat=2.0, beats_per_bar=4).is_downbeat() is False

    def test_beat_number_is_one_indexed(self):
        assert MusicalTime(bar=0, beat=0.0, beats_per_bar=4).beat_number == 1.0
        assert MusicalTime(bar=0, beat=2.0, beats_per_bar=4).beat_number == 3.0

    def test_to_beats(self):
        t = MusicalTime(bar=2, beat=2.0, beats_per_bar=4)
        assert t.to_beats() == 10.0

    def test_is_beat_matches_one_indexed_target(self):
        pos = MusicalTime(bar=2, beat=2.0, beats_per_bar=4)
        assert pos.is_beat(3) is True    # beat 2.0 == "beat 3" (1-indexed)
        assert pos.is_beat(1) is False

    def test_is_bar_mod(self):
        pos = MusicalTime(bar=4, beat=0.0, beats_per_bar=4)
        assert pos.is_bar_mod(2) is True
        assert pos.is_bar_mod(2, offset=1) is False
        assert pos.is_bar_mod(3) is False

    def test_matches_combines_predicates(self):
        pos = MusicalTime(bar=2, beat=2.0, beats_per_bar=4)
        assert pos.matches(beat=3, bar_mod=2) is True
        assert pos.matches(beat=1) is False
        assert pos.matches(downbeat_only=True) is False

    def test_matches_downbeat_only(self):
        pos = MusicalTime(bar=2, beat=0.0, beats_per_bar=4)
        assert pos.matches(downbeat_only=True) is True


# ===========================================================================
# add_beats / from_beats round-trip and bar-crossing
# ===========================================================================

class TestArithmetic:
    def test_add_beats_within_bar(self):
        t = MusicalTime(bar=0, beat=1.0, beats_per_bar=4)
        result = t.add_beats(1.0)
        assert (result.bar, result.beat) == (0, 2.0)

    def test_add_beats_crosses_bar_boundary(self):
        t = MusicalTime(bar=0, beat=3.0, beats_per_bar=4)
        result = t.add_beats(1.5)
        assert (result.bar, result.beat) == (1, 0.5)

    def test_add_beats_negative_steps_back(self):
        t = MusicalTime(bar=1, beat=0.0, beats_per_bar=4)
        result = t.add_beats(-0.5)
        assert (result.bar, result.beat) == (0, 3.5)

    def test_add_beats_negative_below_zero_raises(self):
        t = MusicalTime(bar=0, beat=1.0, beats_per_bar=4)
        with pytest.raises(ValueError, match="negative time"):
            t.add_beats(-5.0)

    def test_add_beats_does_not_mutate_original(self):
        """Every operation returns a new MusicalTime -- self is never touched."""
        t = MusicalTime(bar=0, beat=1.0, beats_per_bar=4)
        _ = t.add_beats(2.0)
        assert (t.bar, t.beat) == (0, 1.0)

    def test_from_beats_round_trip(self):
        t = MusicalTime.from_beats(9.5, beats_per_bar=4)
        assert (t.bar, t.beat) == (2, 1.5)
        assert t.to_beats() == 9.5

    def test_from_beats_negative_raises(self):
        with pytest.raises(ValueError, match="total_beats must be >= 0"):
            MusicalTime.from_beats(-1.0, beats_per_bar=4)

    def test_from_beats_guards_floating_point_creep(self):
        """3.9999999 beats should round up to the next bar, not linger as
        an invalid beat==beats_per_bar position."""
        t = MusicalTime.from_beats(3.9999999999, beats_per_bar=4)
        assert (t.bar, t.beat) == (1, 0.0)


# ===========================================================================
# Comparison and hashing
# ===========================================================================

class TestComparisonAndHashing:
    def test_equality(self):
        a = MusicalTime(bar=1, beat=2.0, beats_per_bar=4)
        b = MusicalTime(bar=1, beat=2.0, beats_per_bar=4)
        assert a == b

    def test_inequality_different_beat(self):
        a = MusicalTime(bar=1, beat=2.0, beats_per_bar=4)
        b = MusicalTime(bar=1, beat=1.0, beats_per_bar=4)
        assert a != b

    def test_ordering(self):
        a = MusicalTime(bar=1, beat=0.0, beats_per_bar=4)
        b = MusicalTime(bar=0, beat=3.5, beats_per_bar=4)
        assert a > b
        assert b < a
        assert a >= b
        assert b <= a

    def test_hashable_and_usable_as_dict_key(self):
        a = MusicalTime(bar=1, beat=2.0, beats_per_bar=4)
        b = MusicalTime(bar=1, beat=2.0, beats_per_bar=4)
        d = {a: "value"}
        assert d[b] == "value"  # equal instances hash the same

    def test_equality_against_non_musicaltime_is_not_equal(self):
        a = MusicalTime(bar=0, beat=0.0, beats_per_bar=4)
        assert (a == "not a musical time") is False


# ===========================================================================
# Module-level helpers
# ===========================================================================

class TestHelperFunctions:
    def test_beats_to_bar_and_local(self):
        assert beats_to_bar_and_local(10.0, beats_per_bar=4) == (2, 2.0)

    def test_is_downbeat_float_true_at_bar_boundary(self):
        assert is_downbeat_float(8.0, beats_per_bar=4) is True

    def test_is_downbeat_float_false_off_boundary(self):
        assert is_downbeat_float(8.1, beats_per_bar=4) is False

    def test_is_downbeat_float_tolerates_drift(self):
        assert is_downbeat_float(7.9999999999, beats_per_bar=4) is True

    def test_bar_beat_from_event_offset(self):
        # Section starts at absolute beat 16; event is 2 beats into it.
        result = bar_beat_from_event_offset(
            event_beat=2.0, section_start_beats=16.0, beats_per_bar=4,
        )
        assert (result.bar, result.beat) == (4, 2.0)
