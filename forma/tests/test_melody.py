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
    def test_hand_verified_sequence(self):
        # start=60, intervals=[2,-1,3] -> running pitch 62,61,64
        # snap to scale [60,62,64,65,67,69,71]: 62->62, 61->closest(60 or 62,
        # tie -> min() picks first in list order = 60, so 61 snaps to 60,
        # then 60+3=63 snaps to nearest of {..} -> 62 (dist1) vs 64(dist1)
        # tie -> 62 comes first in list -> 62
        result = motif_to_notes(
            60, [2, -1, 3], [1.0, 1.0, 1.0],
            scale_tones=[60, 62, 64, 65, 67, 69, 71],
            chord_tones=[60, 64, 67],
            octave_bottom=48, octave_top=84,
        )
        assert result == [(62, 1.0), (60, 1.0), (62, 1.0)]

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
