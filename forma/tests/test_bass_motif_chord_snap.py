"""
Regression tests for two bass fixes found in review of the G minor sonata:

1. style_motif's chord-tone snap must compare by pitch class in every octave
   of the bass register. With a register wider than one octave the old
   single-octave chord tones missed the dominant's raised third, so an
   Alberti figure played F natural (a D minor figure) under D major.
2. The piece's last bass note must land on the root of the final chord.
"""
import pytest

from intervals.music.bass import (
    BassNote,
    land_bass_on_root,
    snap_to_chord_tone,
    style_motif,
)
from intervals.music.harmony import resolve_chord

ALBERTI = {"intervals": [-4, 4, -2, 2, -4, 4, -2, 2], "rhythm": [0.5] * 8}


def _alberti_pitches(roman, key, mode, bottom, top):
    chord = resolve_chord(roman, key, mode)
    notes = style_motif([chord], [1.0], 4, "sparse", 54, key=key, mode=mode,
                        octave_bottom=bottom, octave_top=top, motif=ALBERTI)
    return chord, [n.midi_note for n in notes]


@pytest.mark.parametrize("bottom,top", [(36, 48), (36, 60), (40, 60), (39, 57), (38, 62)])
def test_dominant_alberti_never_plays_natural_third(bottom, top):
    chord, pitches = _alberti_pitches("V/i", "G", "aeolian", bottom, top)
    chord_pcs = {n % 12 for n in chord.midi_notes}
    assert 5 not in {p % 12 for p in pitches}           # no F natural over D major
    assert {p % 12 for p in pitches} <= chord_pcs        # every note is a chord tone


@pytest.mark.parametrize("bottom,top", [(36, 48), (40, 60)])
def test_snap_leaves_tonic_triad_alone(bottom, top):
    chord, pitches = _alberti_pitches("i", "G", "aeolian", bottom, top)
    assert {p % 12 for p in pitches} <= {n % 12 for n in chord.midi_notes}


def test_snap_helper_respects_register_and_distance():
    assert snap_to_chord_tone(53, {2, 6, 9}, 40, 60) == 54      # F -> F#
    assert snap_to_chord_tone(54, {2, 6, 9}, 40, 60) == 54      # already a chord tone
    assert snap_to_chord_tone(53, {2, 9}, 40, 60) == 53         # nothing within 2 semitones
    assert snap_to_chord_tone(53, {6}, 40, 53) == 53            # snap target outside register


def test_last_bass_note_lands_on_final_chord_root():
    chord = resolve_chord("i", "G", "aeolian")
    notes = [BassNote(43, 0.0, 0.5), BassNote(50, 0.5, 0.5)]   # ends on D, not G
    land_bass_on_root(notes, chord)
    assert notes[-1].midi_note % 12 == 7 and notes[-1].midi_note == 43


def test_land_on_root_is_noop_when_already_root():
    chord = resolve_chord("i", "G", "aeolian")
    notes = [BassNote(50, 0.0, 0.5), BassNote(55, 0.5, 0.5)]
    land_bass_on_root(notes, chord)
    assert [n.midi_note for n in notes] == [50, 55]


def test_land_on_root_handles_empty_and_missing_chord():
    assert land_bass_on_root([], resolve_chord("i", "G", "aeolian")) == []
    notes = [BassNote(50, 0.0, 0.5)]
    assert land_bass_on_root(notes, None)[0].midi_note == 50
