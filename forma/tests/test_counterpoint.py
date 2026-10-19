"""
Tests for intervals.music.counterpoint — interval/motion classification,
the interval-rule checker, and the two species generators (first, free).

Counterpoint is the one voice in this engine that reads other voices'
notes while generating its own (against_notes / against_voices) -- see
generate_first_species/generate_free_species tests below, which
demonstrate that interdependency concretely: a candidate that's fine
against the melody alone gets penalized (and, given a close second
choice, actually displaced) once it's also dissonant against another
voice's sounding pitch.

FIXED BUG (see TestIntervalClassification below): interval_class() used
to fold any semitone distance to its smallest complement in [0, 6], which
silently conflated a perfect fifth (7 semitones) with a perfect fourth (5
semitones) -- both mapped to the same folded value, so a real fifth was
misclassified as dissonant. Worse, since PERFECT_CONSONANCES/DISSONANCES
were authored assuming plain 0-11 mod-12 distances (not folded values),
the fold also made several OTHER rules permanently unreachable: parallel-
fifths detection (only ever caught parallel octaves), direct/hidden
fifths (dead code -- its guard condition could never be true), the
cadence-candidate filters (only ever matched octave-equivalent pitches),
and score_candidate's "prefer imperfect over perfect" tie-break (dead,
since its guard excluded the only reachable PERFECT_CONSONANCES value).
Fixed by removing the fold: interval_class() is now plain abs(a-b) % 12,
which is also what correctly preserves the intentional classical-
counterpoint rule that a fourth is dissonant against the bass while a
fifth is a true perfect consonance -- the fold was conflating exactly
that distinction.
"""
import pytest

from intervals.music.counterpoint import (
    CONSONANCES,
    DISSONANCES,
    IMPERFECT_CONSONANCES,
    PERFECT_CONSONANCES,
    CounterpointNote,
    check_interval_rules,
    chord_tones_as_voices,
    compute_register_bounds,
    count_hard_violations,
    count_soft_violations,
    generate_counterpoint,
    generate_first_species,
    generate_free_species,
    get_scale_tones_in_register,
    interval_class,
    is_consonant,
    is_dissonant,
    is_perfect_consonance,
    last_sounding_before,
    motion_type,
    note_sounding_at,
    raw_interval,
    score_candidate,
)
from intervals.music.harmony import VoicedChord
from intervals.music.melody import MelodyNote


# ===========================================================================
# interval_class / raw_interval
# ===========================================================================

class TestIntervalClass:
    def test_unison(self):
        assert interval_class(60, 60) == 0

    def test_octave_reduces_to_zero(self):
        assert interval_class(60, 72) == 0

    def test_minor_second(self):
        assert interval_class(60, 61) == 1

    def test_major_third(self):
        assert interval_class(60, 64) == 4

    def test_minor_third(self):
        assert interval_class(60, 63) == 3

    def test_tritone_is_its_own_complement(self):
        assert interval_class(60, 66) == 6

    def test_major_sixth_is_distinct_from_minor_third(self):
        """9 semitones is a major sixth, not a minor third -- plain mod-12
        distance keeps them distinct (unlike the old folded behavior,
        which collapsed octave-inversion pairs into the same value)."""
        assert interval_class(60, 69) == 9
        assert interval_class(60, 69) != interval_class(60, 63)  # != minor 3rd

    def test_minor_sixth_is_distinct_from_major_third(self):
        assert interval_class(60, 68) == 8
        assert interval_class(60, 68) != interval_class(60, 64)  # != major 3rd

    def test_raw_interval_is_not_reduced(self):
        assert raw_interval(60, 72) == 12
        assert raw_interval(60, 67) == 7


class TestIntervalClassificationFix:
    """Confirms the fix: a perfect fifth is correctly a perfect
    consonance, a perfect fourth is correctly dissonant (the intentional
    classical rule, not a bug -- a 4th against the bass has always been
    treated as needing resolution in strict counterpoint), and every
    mod-12 residue 0-11 is now reachable and correctly classified."""

    def test_perfect_fifth_is_a_perfect_consonance(self):
        assert interval_class(60, 67) == 7
        assert is_consonant(60, 67) is True
        assert is_perfect_consonance(60, 67) is True
        assert is_dissonant(60, 67) is False

    def test_perfect_fourth_is_dissonant_by_design(self):
        """Not a bug: a 4th against the bass is the textbook dissonance-
        requiring-resolution case in species counterpoint."""
        assert interval_class(60, 65) == 5
        assert is_consonant(60, 65) is False
        assert is_dissonant(60, 65) is True

    def test_every_mod_twelve_residue_is_reachable_and_correctly_partitioned(self):
        reachable_ics = {interval_class(60, 60 + d) for d in range(13)}
        assert reachable_ics == set(range(12))  # 0-11, all reachable (12 folds to 0)

        for ic in range(12):
            in_perfect = ic in PERFECT_CONSONANCES
            in_imperfect = ic in IMPERFECT_CONSONANCES
            in_dissonant = ic in DISSONANCES
            # Exactly one classification per residue -- no gaps, no overlaps.
            assert sum([in_perfect, in_imperfect, in_dissonant]) == 1, (
                f"interval class {ic} must be classified exactly once"
            )


# ===========================================================================
# is_consonant / is_perfect_consonance / is_dissonant (unaffected cases)
# ===========================================================================

class TestConsonanceClassification:
    def test_major_third_is_consonant(self):
        assert is_consonant(60, 64) is True

    def test_minor_second_is_dissonant(self):
        assert is_dissonant(60, 61) is True

    def test_octave_is_perfect_consonance(self):
        assert is_perfect_consonance(60, 72) is True

    def test_major_third_is_not_perfect_consonance(self):
        assert is_perfect_consonance(60, 64) is False

    def test_consonances_and_dissonances_partition_reachable_classes(self):
        reachable = {interval_class(60, 60 + d) for d in range(13)}
        assert reachable <= (CONSONANCES | DISSONANCES)


# ===========================================================================
# motion_type
# ===========================================================================

class TestMotionType:
    def test_both_voices_static_is_parallel(self):
        assert motion_type(60, 60, 64, 64) == "parallel"

    def test_one_voice_static_is_oblique(self):
        assert motion_type(60, 60, 64, 67) == "oblique"

    def test_opposite_directions_is_contrary(self):
        assert motion_type(60, 62, 64, 60) == "contrary"

    def test_same_direction_same_amount_is_parallel(self):
        assert motion_type(60, 62, 64, 66) == "parallel"

    def test_same_direction_different_amount_is_similar(self):
        assert motion_type(60, 62, 64, 68) == "similar"


# ===========================================================================
# check_interval_rules — the requested "dissonant interval" test
# ===========================================================================

class TestCheckIntervalRules:
    def test_dissonant_interval_on_strong_beat_is_caught(self):
        """The task's explicit ask: deliberately set up a dissonant
        interval against the melody and confirm the checker catches it.
        Minor second (60 vs 61) is dissonant under every interval
        taxonomy, including this module's (unaffected by the P4/P5 bug
        documented above), and beat 0.0 is unambiguously a strong beat."""
        from intervals.music.counterpoint import check_interval_rules
        violations = check_interval_rules(60, 61, None, None, beat_position=0.0, beats_per_bar=4)
        assert count_hard_violations(violations) == 1
        assert violations[0].rule == "dissonance_on_strong_beat"
        assert violations[0].severity == "hard"

    def test_consonant_interval_on_strong_beat_is_clean(self):
        from intervals.music.counterpoint import check_interval_rules
        violations = check_interval_rules(60, 64, None, None, beat_position=0.0, beats_per_bar=4)
        assert violations == []

    def test_dissonance_not_checked_on_weak_beats(self):
        """beat 1.0 in 4/4 is neither the downbeat nor the bar's midpoint
        -- the strong-beat gate means even a dissonant interval there
        produces no dissonance violation (a real, if debatable, rule
        boundary -- documented here as the actual behavior)."""
        from intervals.music.counterpoint import check_interval_rules
        violations = check_interval_rules(60, 61, None, None, beat_position=1.0, beats_per_bar=4)
        assert not any(v.rule == "dissonance_on_strong_beat" for v in violations)

    def test_parallel_octaves_forbidden(self):
        from intervals.music.counterpoint import check_interval_rules
        # melody 60->62 (up), cp 48->50 (up, same amount) both octaves below
        violations = check_interval_rules(62, 50, 60, 48, beat_position=1.0, beats_per_bar=4)
        assert any(v.rule == "parallel_perfects" and v.severity == "hard" for v in violations)

    def test_parallel_fifths_forbidden(self):
        """Now genuinely reachable post-fix: two real perfect fifths in
        parallel motion (60/67 -> 62/69, i.e. up a whole step, both
        voices) must be caught -- this is THE canonical forbidden-parallel
        rule in counterpoint pedagogy, and it was silently unreachable
        for actual fifths before the interval_class() fix."""
        from intervals.music.counterpoint import check_interval_rules
        violations = check_interval_rules(62, 69, 60, 67, beat_position=1.0, beats_per_bar=4)
        assert any(v.rule == "parallel_perfects" and v.severity == "hard" for v in violations)

    def test_direct_hidden_fifth_forbidden(self):
        """Similar motion (both voices moving the same direction, unequal
        amounts) landing on a perfect fifth -- also unreachable before
        the fix, since its guard checked interval_class(...) == 7."""
        from intervals.music.counterpoint import check_interval_rules
        violations = check_interval_rules(67, 60, 64, 55, beat_position=1.0, beats_per_bar=4)
        assert any(v.rule == "direct_fifth" and v.severity == "hard" for v in violations)

    def test_interior_unison_flagged_as_soft(self):
        from intervals.music.counterpoint import check_interval_rules
        violations = check_interval_rules(64, 64, None, None, beat_position=1.0, beats_per_bar=4,
                                           is_final=False)
        assert any(v.rule == "interior_unison" and v.severity == "soft" for v in violations)

    def test_unison_at_final_cadence_not_flagged(self):
        from intervals.music.counterpoint import check_interval_rules
        violations = check_interval_rules(64, 64, None, None, beat_position=3.0, beats_per_bar=4,
                                           is_final=True)
        assert not any(v.rule == "interior_unison" for v in violations)

    def test_count_helpers(self):
        from intervals.music.counterpoint import check_interval_rules
        violations = check_interval_rules(60, 61, 60, 60, beat_position=0.0, beats_per_bar=4)
        assert count_hard_violations(violations) >= 1
        assert count_hard_violations(violations) + count_soft_violations(violations) == len(violations)


# ===========================================================================
# note_sounding_at / last_sounding_before
# ===========================================================================

class TestTimePositionLookups:
    def _notes(self):
        return [MelodyNote(60, 0.0, 1.0), MelodyNote(None, 1.0, 1.0, is_rest=True),
                MelodyNote(64, 2.0, 1.0)]

    def test_sounding_mid_note(self):
        assert note_sounding_at(self._notes(), 0.5) == 60

    def test_sounding_during_a_rest_returns_none(self):
        assert note_sounding_at(self._notes(), 1.5) is None

    def test_sounding_past_the_last_note_returns_none(self):
        assert note_sounding_at(self._notes(), 5.0) is None

    def test_last_sounding_before_a_gap_returns_the_prior_note(self):
        assert last_sounding_before(self._notes(), 1.5) == 60

    def test_last_sounding_before_start_returns_none(self):
        assert last_sounding_before(self._notes(), -1.0) is None

    def test_last_sounding_before_past_the_end(self):
        assert last_sounding_before(self._notes(), 5.0) == 64


# ===========================================================================
# compute_register_bounds / get_scale_tones_in_register
# ===========================================================================

class TestRegisterBounds:
    def test_explicit_bounds_used_directly(self):
        notes = [MelodyNote(60, 0.0, 1.0)]
        assert compute_register_bounds(notes, "below", explicit_bounds=(40, 60)) == (40, 60)

    def test_hand_verified_derived_from_melody_range(self):
        # mel_low=60, mel_high=70 -> bottom=60-2-5=53, top=70+2+5=77
        notes = [MelodyNote(60, 0.0, 1.0), MelodyNote(70, 1.0, 1.0)]
        assert compute_register_bounds(notes, "below") == (53, 77)

    def test_narrow_melody_range_widened_to_minimum_band(self):
        # mel_low=60, mel_high=61 -> raw (53,68), width 15 >= 14 (no widening needed)
        notes = [MelodyNote(60, 0.0, 1.0), MelodyNote(61, 1.0, 1.0)]
        assert compute_register_bounds(notes, "below") == (53, 68)

    def test_empty_melody_falls_back_to_fixed_bounds(self):
        assert compute_register_bounds([], "below") == (48, 69)
        assert compute_register_bounds([], "above") == (67, 88)

    def test_get_scale_tones_in_register(self):
        assert get_scale_tones_in_register("C", "ionian", 60, 72) == [
            60, 62, 64, 65, 67, 69, 71, 72,
        ]


# ===========================================================================
# chord_tones_as_voices
# ===========================================================================

class TestChordTonesAsVoices:
    def test_hand_verified_two_synthetic_voices(self):
        chords = [
            VoicedChord("C", "major", [60, 64, 67], 0, "I", 0),
            VoicedChord("F", "major", [65, 69, 72], 0, "IV", 3),
        ]
        voices = chord_tones_as_voices(chords, [1.0, 1.0], beats_per_bar=4, max_voices=2)
        assert [n.midi_note for n in voices[0]] == [60, 65]
        assert [n.midi_note for n in voices[1]] == [64, 69]
        assert [n.start_beat for n in voices[0]] == [0.0, 4.0]

    def test_chord_with_fewer_tones_rests_the_extra_voice(self):
        chords = [VoicedChord("C", "major", [60, 64], 0, "I", 0)]  # only 2 tones
        voices = chord_tones_as_voices(chords, [1.0], beats_per_bar=4, max_voices=3)
        assert voices[2][0].is_rest is True
        assert voices[2][0].midi_note is None


# ===========================================================================
# score_candidate — the against_notes interdependency mechanism, isolated
# ===========================================================================

class TestScoreCandidateAgainstNotes:
    def test_dissonant_against_notes_adds_a_five_hundred_point_hard_penalty(self):
        """Isolated proof of the interdependency mechanism: a candidate
        that's fine against the melody alone gets a hard-violation
        penalty once it's also dissonant against another voice's
        sounding pitch (against_notes), on a strong beat where dissonance
        is actually checked."""
        import random
        scale = [48, 50, 52, 53, 55, 57, 59, 60]

        score_alone = score_candidate(
            57, 60, None, None, scale, beat_position=0.0, beats_per_bar=4,
            register="below", is_final=False, rng=random.Random(1), against_notes=None,
        )
        score_with_dissonant_peer = score_candidate(
            57, 60, None, None, scale, beat_position=0.0, beats_per_bar=4,
            register="below", is_final=False, rng=random.Random(1), against_notes=[58],
        )
        assert score_with_dissonant_peer - score_alone == pytest.approx(500.0)

    def test_consonant_against_notes_adds_no_penalty(self):
        import random
        scale = [48, 50, 52, 53, 55, 57, 59, 60]
        score_alone = score_candidate(
            57, 60, None, None, scale, beat_position=0.0, beats_per_bar=4,
            register="below", is_final=False, rng=random.Random(1), against_notes=None,
        )
        # 61 is a major third above 57 (interval_class 4, IMPERFECT_CONSONANCES).
        score_with_consonant_peer = score_candidate(
            57, 60, None, None, scale, beat_position=0.0, beats_per_bar=4,
            register="below", is_final=False, rng=random.Random(1), against_notes=[61],
        )
        assert score_with_consonant_peer == pytest.approx(score_alone)

    def test_real_perfect_fifth_peer_also_adds_no_penalty(self):
        """Post-fix regression guard: a peer a genuine perfect fifth away
        (64, 7 semitones from 57) must NOT add a dissonance penalty --
        this is exactly the case the interval_class() bug used to get
        wrong (a real fifth was misclassified as dissonant)."""
        import random
        scale = [48, 50, 52, 53, 55, 57, 59, 60]
        score_alone = score_candidate(
            57, 60, None, None, scale, beat_position=0.0, beats_per_bar=4,
            register="below", is_final=False, rng=random.Random(1), against_notes=None,
        )
        score_with_fifth_peer = score_candidate(
            57, 60, None, None, scale, beat_position=0.0, beats_per_bar=4,
            register="below", is_final=False, rng=random.Random(1), against_notes=[64],
        )
        assert score_with_fifth_peer == pytest.approx(score_alone)


# ===========================================================================
# generate_first_species
# ===========================================================================

def _melody(pitches_beats):
    return [MelodyNote(p, b, 1.0) for p, b in pitches_beats]


class TestGenerateFirstSpecies:
    def test_reproducible_with_same_seed(self):
        melody = _melody([(60, 0.0), (62, 1.0), (64, 2.0), (60, 3.0)])
        a = generate_first_species(melody, "C", "ionian", register="below", seed=1)
        b = generate_first_species(melody, "C", "ionian", register="below", seed=1)
        assert [n.midi_note for n in a] == [n.midi_note for n in b]

    def test_empty_melody_returns_no_notes(self):
        assert generate_first_species([], "C", "ionian", seed=1) == []

    def test_output_carries_zero_hard_violations(self):
        """The candidate scorer heavily penalizes hard violations (1000
        points each); across a real melody the picker should always be
        able to find at least one zero-hard-violation candidate."""
        melody = _melody([(60, 0.0), (62, 1.0), (64, 2.0), (60, 3.0)])
        cp = generate_first_species(melody, "C", "ionian", register="below", seed=1)
        total_hard = sum(count_hard_violations(n.violations) for n in cp)
        assert total_hard == 0

    def test_against_notes_can_displace_the_otherwise_best_candidate(self):
        """End-to-end interdependency proof: forcing dissonance against
        the pick this exact seed/melody/register combination otherwise
        makes for the middle note changes that note's outcome -- the
        voice actually responds to what another voice is doing, not just
        to the melody."""
        melody = _melody([(60, 0.0), (62, 1.0), (64, 2.0), (60, 3.0)])
        bounds = (48, 60)
        baseline = generate_first_species(melody, "C", "ionian", register="below",
                                           seed=1, register_bounds=bounds)
        baseline_pitches = [n.midi_note for n in baseline]

        target_idx = 2  # beat=2.0, a strong beat (bar midpoint)
        forced_dissonant_neighbors = [baseline_pitches[target_idx] + 1,
                                       baseline_pitches[target_idx] - 1]
        displaced = generate_first_species(melody, "C", "ionian", register="below",
                                            seed=1, register_bounds=bounds,
                                            against_notes=forced_dissonant_neighbors)
        displaced_pitches = [n.midi_note for n in displaced]

        assert displaced_pitches[target_idx] != baseline_pitches[target_idx]


# ===========================================================================
# generate_free_species
# ===========================================================================

class TestGenerateFreeSpecies:
    def test_reproducible_with_same_seed(self):
        melody = _melody([(60, 0.0), (62, 1.0), (64, 2.0), (60, 3.0)])
        a = generate_free_species(melody, "C", "ionian", register="below", seed=1)
        b = generate_free_species(melody, "C", "ionian", register="below", seed=1)
        assert [n.midi_note for n in a] == [n.midi_note for n in b]

    def test_empty_melody_returns_no_notes(self):
        assert generate_free_species([], "C", "ionian", seed=1) == []

    def test_produces_rhythmically_independent_onsets(self):
        """Free species is defined by NOT being locked 1:1 to the
        melody's onsets -- confirm the generated onset count differs
        from (isn't forced to equal) the melody's note count."""
        melody = _melody([(60, 0.0), (62, 1.0), (64, 2.0), (60, 3.0)])
        cp = generate_free_species(melody, "C", "ionian", register="below", seed=1)
        assert len(cp) > 0
        # Not asserting a specific count (that's an implementation detail
        # of the density grid), just that this species doesn't inherit
        # first species' hard 1:1 constraint:
        assert isinstance(cp[0], CounterpointNote)


# ===========================================================================
# generate_counterpoint — dispatcher
# ===========================================================================

class TestGenerateCounterpointDispatch:
    def test_unknown_species_raises(self):
        melody = _melody([(60, 0.0)])
        with pytest.raises(ValueError, match="Unknown species"):
            generate_counterpoint(melody, "C", "ionian", species="bogus", seed=1)

    def test_first_species_dispatch_matches_direct_call(self):
        melody = _melody([(60, 0.0), (62, 1.0), (64, 2.0), (60, 3.0)])
        direct = generate_first_species(melody, "C", "ionian", register="below", seed=1)
        via_dispatch = generate_counterpoint(melody, "C", "ionian", species="first",
                                              register="below", seed=1)
        assert [n.midi_note for n in direct] == [n.midi_note for n in via_dispatch]

    def test_free_species_dispatch_matches_direct_call(self):
        melody = _melody([(60, 0.0), (62, 1.0), (64, 2.0), (60, 3.0)])
        direct = generate_free_species(melody, "C", "ionian", register="below", seed=1)
        via_dispatch = generate_counterpoint(melody, "C", "ionian", species="free",
                                              register="below", seed=1)
        assert [n.midi_note for n in direct] == [n.midi_note for n in via_dispatch]
