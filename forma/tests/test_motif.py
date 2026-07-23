"""
Tests for intervals.music.motif — the Motif dataclass and its transforms.

Every transform test asserts a hand-verified expected output (computed by
hand against the transform's stated formula, then cross-checked against
the running code before being written down as an assertion) — not merely
that the call succeeds.
"""
import pytest

from intervals.music.motif import (
    Motif,
    apply_transform_sequence,
    from_dict,
    generate_random,
    mutate,
    similarity,
    to_dict,
    to_note_sequence,
    transform,
)


def _src() -> Motif:
    """The motif used across most transform tests: intervals=[2,-1,3,-2],
    rhythm=[1.0,0.5,0.5,1.0] -- matches the module's own __main__ demo."""
    return Motif(intervals=[2, -1, 3, -2], rhythm=[1.0, 0.5, 0.5, 1.0], name="src")


# ===========================================================================
# Motif construction / __post_init__ padding & trimming
# ===========================================================================

class TestMotifConstruction:
    def test_rhythm_shorter_than_intervals_is_tiled_and_trimmed(self):
        m = Motif(intervals=[1, 2, 3, 4, 5], rhythm=[1.0, 2.0])
        assert m.rhythm == [1.0, 2.0, 1.0, 2.0, 1.0]

    def test_rhythm_longer_than_intervals_is_trimmed(self):
        m = Motif(intervals=[1, 2], rhythm=[1.0, 2.0, 3.0, 4.0])
        assert m.rhythm == [1.0, 2.0]

    def test_rests_shorter_than_intervals_padded_with_false(self):
        m = Motif(intervals=[1, 2, 3], rhythm=[1, 1, 1], rests=[True])
        assert m.rests == [True, False, False]

    def test_rests_longer_than_intervals_trimmed(self):
        m = Motif(intervals=[1, 2], rhythm=[1, 1], rests=[True, False, True, True])
        assert m.rests == [True, False]

    def test_note_count(self):
        assert _src().note_count() == 4

    def test_total_duration(self):
        assert _src().total_duration() == pytest.approx(3.0)

    def test_interval_range(self):
        # positions: 0, 2, 1, 4, 2 -> max 4, min 0 -> range 4
        assert _src().interval_range() == 4

    def test_contour(self):
        assert _src().contour() == ["U", "D", "U", "D"]

    def test_contour_marks_zero_as_same(self):
        m = Motif(intervals=[0, 2, -2], rhythm=[1, 1, 1])
        assert m.contour() == ["S", "U", "D"]


# ===========================================================================
# transform() — each transform against a hand-verified expected output
# ===========================================================================

class TestTransformInversion:
    def test_negates_every_interval(self):
        result = transform(_src(), "inversion")
        assert result.intervals == [-2, 1, -3, 2]

    def test_rhythm_is_unchanged(self):
        result = transform(_src(), "inversion")
        assert result.rhythm == [1.0, 0.5, 0.5, 1.0]

    def test_metadata_updated(self):
        result = transform(_src(), "inversion")
        assert result.name == "src_inversion"
        assert result.generation == 1
        assert result.parent_name == "src"


class TestTransformRetrograde:
    def test_reverses_intervals_and_rhythm_together(self):
        result = transform(_src(), "retrograde")
        assert result.intervals == [-2, 3, -1, 2]
        assert result.rhythm == [1.0, 0.5, 0.5, 1.0]  # palindromic rhythm here

    def test_reverses_rests_too(self):
        m = Motif(intervals=[1, 2, 3], rhythm=[1, 1, 1], rests=[True, False, False])
        result = transform(m, "retrograde")
        assert result.rests == [False, False, True]


class TestTransformRetrogradeInversion:
    def test_reverses_then_negates(self):
        result = transform(_src(), "retrograde_inversion")
        # retrograde gives [-2, 3, -1, 2]; negate -> [2, -3, 1, -2]
        assert result.intervals == [2, -3, 1, -2]

    def test_equals_retrograde_then_inversion_chained(self):
        chained = apply_transform_sequence(_src(), ["retrograde", "inversion"])
        direct = transform(_src(), "retrograde_inversion")
        assert chained.intervals == direct.intervals


class TestTransformAugmentation:
    def test_doubles_every_duration(self):
        result = transform(_src(), "augmentation")
        assert result.rhythm == [2.0, 1.0, 1.0, 2.0]

    def test_intervals_unchanged(self):
        result = transform(_src(), "augmentation")
        assert result.intervals == [2, -1, 3, -2]


class TestTransformDiminution:
    def test_halves_every_duration(self):
        result = transform(_src(), "diminution")
        assert result.rhythm == [0.5, 0.25, 0.25, 0.5]

    def test_floors_at_quarter_beat(self):
        """A duration under 0.5 beats would halve below the 0.25 floor --
        must clamp there instead of going smaller."""
        m = Motif(intervals=[1], rhythm=[0.4])
        result = transform(m, "diminution")
        assert result.rhythm == [0.25]


class TestTransformTranspose:
    def test_transpose_up_adds_two_semitones(self):
        result = transform(_src(), "transpose_up")
        assert result.intervals == [4, 1, 5, 0]

    def test_transpose_down_subtracts_two_semitones(self):
        result = transform(_src(), "transpose_down")
        assert result.intervals == [0, -3, 1, -4]


class TestTransformExpand:
    def test_scales_intervals_by_one_point_five_rounded(self):
        result = transform(_src(), "expand")
        # 2*1.5=3, -1*1.5=-1.5->round(-1.5)=-2, 3*1.5=4.5->round=4, -2*1.5=-3
        assert result.intervals == [3, -2, 4, -3]


class TestTransformCompress:
    def test_scales_intervals_by_half_rounded(self):
        m = Motif(intervals=[1, 3, 5, -1, -3], rhythm=[1, 1, 1, 1, 1])
        result = transform(m, "compress")
        # Python's round() is round-half-to-even: round(0.5)=0, round(1.5)=2,
        # round(2.5)=2, round(-0.5)=0, round(-1.5)=-2 -- but 1 and -1 round
        # to 0, which the zero-interval guard then bumps to +/-1 (see below),
        # so the final result is [1, 2, 2, -1, -2], not [0, 2, 2, 0, -2].
        assert result.intervals == [1, 2, 2, -1, -2]

    def test_never_collapses_a_nonzero_interval_to_zero(self):
        """Bugfix lock-in: the guard used to check the already-rounded
        value against itself (`i if i != 0 else 0`), which is a no-op --
        it never substituted anything. It now checks the ORIGINAL
        interval's sign and substitutes +/-1 when rounding would collapse
        it to 0, so a single semitone step survives compression as a
        step, matching the docstring's stated guarantee."""
        m = Motif(intervals=[1], rhythm=[1.0])
        assert transform(m, "compress").intervals == [1]

        m_neg = Motif(intervals=[-1], rhythm=[1.0])
        assert transform(m_neg, "compress").intervals == [-1]

    def test_a_genuinely_zero_original_interval_stays_zero(self):
        """The substitution only applies when compression collapses a
        real step to nothing -- an original interval that was already 0
        (no step) has nothing to preserve and stays 0."""
        m = Motif(intervals=[0, 2, -2, 4, -4], rhythm=[1, 1, 1, 1, 1])
        assert transform(m, "compress").intervals == [0, 1, -1, 2, -2]


class TestTransformShuffle:
    def test_reproducible_with_same_seed(self):
        a = transform(_src(), "shuffle", seed=5)
        b = transform(_src(), "shuffle", seed=5)
        assert a.intervals == b.intervals
        assert a.rhythm == b.rhythm

    def test_preserves_the_same_multiset_of_intervals(self):
        result = transform(_src(), "shuffle", seed=5)
        assert sorted(result.intervals) == sorted(_src().intervals)

    def test_keeps_interval_rhythm_pairs_together(self):
        """Shuffle must reorder (interval, rhythm) as paired tuples, not
        shuffle each list independently."""
        m = Motif(intervals=[10, 20, 30], rhythm=[0.1, 0.2, 0.3])
        result = transform(m, "shuffle", seed=1)
        pairs = set(zip(result.intervals, result.rhythm))
        assert pairs == {(10, 0.1), (20, 0.2), (30, 0.3)}

    def test_shuffles_rests_in_lockstep_too(self):
        m = Motif(intervals=[10, 20, 30], rhythm=[0.1, 0.2, 0.3],
                   rests=[True, False, True])
        result = transform(m, "shuffle", seed=1)
        triples = set(zip(result.intervals, result.rhythm, result.rests))
        assert triples == {(10, 0.1, True), (20, 0.2, False), (30, 0.3, True)}


class TestTransformUnknownName:
    def test_raises_value_error_with_choices_listed(self):
        with pytest.raises(ValueError, match="Unknown transform"):
            transform(_src(), "not_a_real_transform")


class TestApplyTransformSequence:
    def test_empty_sequence_returns_equivalent_motif(self):
        result = apply_transform_sequence(_src(), [])
        assert result.intervals == _src().intervals
        assert result.rhythm == _src().rhythm

    def test_chain_of_three_applies_in_order(self):
        # inversion then transpose_up then retrograde
        result = apply_transform_sequence(_src(), ["inversion", "transpose_up", "retrograde"])
        step1 = transform(_src(), "inversion")
        step2 = transform(step1, "transpose_up")
        step3 = transform(step2, "retrograde")
        assert result.intervals == step3.intervals


# ===========================================================================
# mutate()
# ===========================================================================

class TestMutate:
    def test_zero_mutation_rate_leaves_intervals_unchanged(self):
        result = mutate(_src(), mutation_rate=0.0, seed=1)
        assert result.intervals == _src().intervals

    def test_reproducible_with_same_seed(self):
        a = mutate(_src(), mutation_rate=1.0, interval_range=2, seed=3)
        b = mutate(_src(), mutation_rate=1.0, interval_range=2, seed=3)
        assert a.intervals == b.intervals

    def test_full_mutation_rate_changes_are_within_interval_range(self):
        result = mutate(_src(), mutation_rate=1.0, interval_range=2, seed=3)
        for original, mutated in zip(_src().intervals, result.intervals):
            assert abs(mutated - original) <= 2

    def test_metadata_updated(self):
        result = mutate(_src(), mutation_rate=1.0, seed=3)
        assert result.generation == 1
        assert result.parent_name == "src"


# ===========================================================================
# generate_random()
# ===========================================================================

class TestGenerateRandom:
    def test_reproducible_with_same_seed(self):
        a = generate_random(length=6, max_interval=4, seed=10)
        b = generate_random(length=6, max_interval=4, seed=10)
        assert a.intervals == b.intervals
        assert a.rhythm == b.rhythm

    def test_correct_length(self):
        m = generate_random(length=7, seed=1)
        assert m.note_count() == 7

    def test_never_produces_zero_intervals(self):
        m = generate_random(length=20, max_interval=3, seed=42)
        assert all(i != 0 for i in m.intervals)

    def test_intervals_within_max_range(self):
        m = generate_random(length=20, max_interval=4, seed=42)
        assert all(abs(i) <= 4 for i in m.intervals)

    def test_rhythm_drawn_from_custom_pool(self):
        m = generate_random(length=10, rhythm_pool=[0.25, 0.75], seed=1)
        assert all(r in (0.25, 0.75) for r in m.rhythm)


# ===========================================================================
# similarity()
# ===========================================================================

class TestSimilarity:
    def test_identical_motifs_score_one(self):
        m = _src()
        assert similarity(m, m) == pytest.approx(1.0)

    def test_hand_verified_partial_match(self):
        """b is the exact inversion of a's intervals (opposite contour at
        every step) with the same rhythm.
        contour(a) = U D U D; contour(b) = D U D U -> 0/4 match -> 0.0
        interval diffs: |2-(-2)|=4, |-1-1|=2, |3-(-3)|=6, |-2-2|=4 -> max=6
        interval_score = 1 - 6/12 = 0.5
        similarity = 0.6*0.0 + 0.4*0.5 = 0.2
        """
        a = Motif(intervals=[2, -1, 3, -2], rhythm=[1, 1, 1, 1])
        b = Motif(intervals=[-2, 1, -3, 2], rhythm=[1, 1, 1, 1])
        assert similarity(a, b) == pytest.approx(0.2)

    def test_partial_overlap_hand_verified_second_case(self):
        # Simulate low overlap using two 1-note motifs of opposite
        # contour and maximally distant intervals, since an empty
        # Motif can't be constructed through the normal dataclass path
        # (the min_len==0 guard in similarity() exists for a mismatched
        # pair that reduces to zero overlap, not a truly empty Motif).
        a = Motif(intervals=[1], rhythm=[1])
        b = Motif(intervals=[-1], rhythm=[1])
        # contour a=[U], b=[D] -> 0 match. interval diff=2 -> score=1-2/12
        expected = 0.6 * 0.0 + 0.4 * (1 - 2 / 12)
        assert similarity(a, b) == pytest.approx(expected)


# ===========================================================================
# to_note_sequence()
# ===========================================================================

class TestToNoteSequence:
    def test_hand_verified_pitches_and_durations(self):
        m = Motif(intervals=[2, -1, 3, -2], rhythm=[1.0, 0.5, 0.5, 1.0])
        scale = [60, 62, 64, 65, 67, 69, 71]  # C major, starting at C4
        seq = to_note_sequence(
            m, start_midi=60, scale_tones=scale,
            octave_bottom=48, octave_top=84, snap_to_scale=True,
        )
        # `current` carries the SNAPPED value forward into the next
        # interval addition (it's reassigned in place), so each step
        # builds on the previous step's snapped pitch, not the raw one:
        #   start=60
        #   +2  -> 62 (already in scale)                    -> current=62
        #   -1  -> 61 -> nearest of {60,62,...} is a tie at
        #          distance 1 (60 and 62); min() keeps the first
        #          encountered in list order -> 60            -> current=60
        #   +3  -> 63 -> nearest is a tie at distance 1
        #          (62 and 64); 62 comes first in the list     -> current=62
        #   -2  -> 60 (already in scale)                       -> current=60
        assert seq == [(62, 1.0), (60, 0.5), (62, 0.5), (60, 1.0)]

    def test_wraps_into_register_before_snapping(self):
        m = Motif(intervals=[0, 24, -24], rhythm=[1, 1, 1])
        scale = [60, 62, 64, 65, 67, 69, 71]
        seq = to_note_sequence(
            m, start_midi=60, scale_tones=scale,
            octave_bottom=60, octave_top=72, snap_to_scale=True,
        )
        # start 60 (in bounds) -> snap -> 60
        # 60+24=84 -> wrap down while >72: 84-12=72 -> in bounds -> snap to
        #   nearest of scale: distances to 72 are 12,10,8,7,5,3,1 -> nearest 71
        # 71-24=47 -> wrap up while <60: 47+12=59(<60)+12=71 -> snap -> 71
        assert seq == [(60, 1), (71, 1), (71, 1)]

    def test_no_snap_returns_raw_wrapped_pitch(self):
        m = Motif(intervals=[1], rhythm=[1.0])
        seq = to_note_sequence(
            m, start_midi=60, scale_tones=[60, 64, 67],
            octave_bottom=48, octave_top=84, snap_to_scale=False,
        )
        assert seq == [(61, 1.0)]


# ===========================================================================
# from_dict / to_dict
# ===========================================================================

class TestSerialisation:
    def test_from_dict_missing_intervals_raises(self):
        with pytest.raises(KeyError):
            from_dict({"rhythm": [1.0]})

    def test_from_dict_applies_defaults(self):
        m = from_dict({"intervals": [1, 2, 3]})
        assert m.rhythm == [1.0, 1.0, 1.0]
        assert m.name == "motif"
        assert "inversion" in m.transform_pool

    def test_round_trip_preserves_core_fields(self):
        original = Motif(
            intervals=[1, 2, 3], rhythm=[1, 1, 1], rests=[False, True, False],
            name="x", transform_pool=["inversion"],
        )
        restored = from_dict(to_dict(original))
        assert restored.intervals == original.intervals
        assert restored.rhythm == original.rhythm
        assert restored.rests == original.rests
        assert restored.name == original.name

    def test_to_dict_omits_rests_when_none(self):
        m = Motif(intervals=[1, 2], rhythm=[1, 1])
        d = to_dict(m)
        assert "rests" not in d
