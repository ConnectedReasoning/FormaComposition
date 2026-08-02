"""
Tests for intervals.music.scale_degrees — the shared diatonic
scale-degree <-> absolute-pitch primitives promoted out of melody.py's
_sequence_intervals_diatonically (Phase B1 of the diatonic-motif
migration).
"""
import pytest

from intervals.music.scale_degrees import (
    pitch_classes,
    degree_to_pitch,
    pitch_to_degree,
)


AEOLIAN_PCS_FROM_A = pitch_classes([57, 59, 60, 62, 64, 65, 67])  # A aeolian
# pitch classes: A=9, B=11, C=0, D=2, E=4, F=5, G=7 -> sorted: [0,2,4,5,7,9,11]


class TestPitchClasses:
    def test_dedupes_and_sorts_across_octaves(self):
        scale_tones = [60, 62, 64, 65, 67, 69, 71, 72, 74]  # C ionian, 2 octaves
        assert pitch_classes(scale_tones) == [0, 2, 4, 5, 7, 9, 11]


class TestDegreeToPitch:
    def test_degree_zero_is_first_pitch_class(self):
        pcs = [0, 2, 4, 5, 7, 9, 11]  # C ionian
        assert degree_to_pitch(0, pcs) == 0

    def test_degree_equal_to_scale_length_is_one_octave_up(self):
        pcs = [0, 2, 4, 5, 7, 9, 11]
        assert degree_to_pitch(7, pcs) == 12

    def test_negative_degree_goes_down_an_octave(self):
        pcs = [0, 2, 4, 5, 7, 9, 11]
        assert degree_to_pitch(-7, pcs) == -12
        assert degree_to_pitch(-1, pcs) == -1  # one degree below 0 -> pcs[-1] - 12 = 11-12=-1

    def test_round_trip_with_pitch_to_degree(self):
        pcs = [0, 2, 4, 5, 7, 9, 11]
        for d in range(-10, 11):
            p = degree_to_pitch(d, pcs)
            assert pitch_to_degree(p, pcs, prev_degree=d) == d


class TestPitchToDegreeTieBreak:
    """
    Regression coverage for the gravity-well tie-break bug: a pitch sitting
    exactly halfway between two scale degrees must resolve to the smaller
    step from prev_degree, not an arbitrary (and potentially octave-jumping)
    candidate. This is the exact failure mode found twice: once in the
    engine's own motif rendering (the diagnosis that started the diatonic-
    motif migration), and again in an offline catalog-conversion script
    before this fix was written.
    """

    def test_exact_tie_breaks_toward_prev_degree_not_octave_jump(self):
        # A aeolian pitch classes: [0, 2, 4, 5, 7, 9, 11]. Degree 6 (idx 6,
        # pc 11) sits at absolute pitch 11 in the reference octave; degree 7
        # (idx 0, next octave) sits at pitch 12. Target pitch 11.5 isn't a
        # real MIDI pitch, so instead reproduce the real case: target pitch
        # -1, exactly halfway between degree -1 (pc 11, octave -1 -> -1) and
        # degree 0 (pc 0, octave 0 -> 0). Both are distance 1 from -1.
        pcs = [0, 2, 4, 5, 7, 9, 11]
        # Coming from prev_degree=0 (the tonic), the smaller step to either
        # candidate is degree -1 (step size 1) vs degree 7... both step-1
        # candidates tie in raw distance; the fix must not jump to something
        # like degree -8 or +6 the way the old per-index iteration could.
        result = pitch_to_degree(-1, pcs, prev_degree=0)
        assert abs(result - 0) <= 1, (
            f"expected a same-neighborhood degree near prev_degree=0, got {result} "
            "-- this is the exact regression this module exists to prevent"
        )

    def test_catalog_regression_piece_train_style_motif(self):
        # piece_train's motif ([-1, 1, -1, 1, 2, -2, -1, 0, 0] in E
        # mixolydian) was the motif whose semitone-neighbor steps exposed
        # the original bug. Confirms the fixed primitive doesn't produce a
        # spurious octave-scale interval when walked sequentially the way
        # the catalog-migration script and (eventually) motif_to_notes do.
        pcs = pitch_classes([64, 66, 68, 69, 71, 73, 74])  # E mixolydian
        intervals = [-1, 1, -1, 1, 2, -2, -1, 0, 0]
        cum = [0]
        for iv in intervals:
            cum.append(cum[-1] + iv)
        degrees = [0]
        for p in cum[1:]:
            degrees.append(pitch_to_degree(p, pcs, prev_degree=degrees[-1]))
        new_intervals = [degrees[i + 1] - degrees[i] for i in range(len(intervals))]
        assert max(abs(x) for x in new_intervals) <= 2, (
            f"expected small diatonic steps, got {new_intervals} -- a value "
            ">= 7 here would mean the tie-break regression is back"
        )
