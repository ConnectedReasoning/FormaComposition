"""
Regression: peer voices (section.voices[1:]) must follow the SECTION's
key/mode override, like the lead melody, bass and harmony do.

They used to read the piece-level key, so a section that modulated (e.g.
A mixolydian inside a D aeolian piece) got counterpoint in the old key and
sat a semitone off the harmony on every differing scale degree.
"""
import mido
import pytest

from intervals.core import generator
from song_helpers import song_piece, first_section

NOTE_PC = {"C": 0, "D": 2, "E": 4, "F": 5, "G": 7, "A": 9, "B": 11}
MODES = {
    "aeolian":    [0, 2, 3, 5, 7, 8, 10],
    "mixolydian": [0, 2, 4, 5, 7, 9, 10],
    "ionian":     [0, 2, 4, 5, 7, 9, 11],
}


def _scale(key, mode):
    return {(NOTE_PC[key] + i) % 12 for i in MODES[mode]}


def _track_pitches(path, name):
    m = mido.MidiFile(path)
    out = []
    for t in m.tracks:
        if t.name == name:
            out += [g.note for g in t if g.type == "note_on" and g.velocity > 0]
    return out


def _piece(peer_voice):
    # Two sections: first in the piece key (D aeolian), second overrides to
    # A mixolydian. Pitch classes differ on B/Bb, C#/C, F#/F.
    return song_piece({
        "key": "D", "mode": "aeolian", "tempo": 84, "seed": 5,
        "sections": [
            {"name": "home", "bars": 4, "rhythm": "free", "density": "medium",
             "progression": ["i", "iv", "v", "i"], "chord_bars": [1, 1, 1, 1]},
            {"name": "away", "bars": 8, "key": "A", "mode": "mixolydian",
             "rhythm": "free", "density": "medium",
             "progression": ["I", "IV", "v", "I"], "chord_bars": [2, 2, 2, 2],
             "voices": [{"behavior": "lyrical", "velocity": 72}, peer_voice]},
        ],
    })


@pytest.mark.parametrize("peer_voice", [
    {"species": "free", "register": "tenor", "dissonance": "none", "velocity": 58},
    {"species": "first", "register": "tenor", "dissonance": "none", "velocity": 58},
    {"behavior": "lyrical", "register": "tenor", "velocity": 58},
], ids=["counterpoint-free", "counterpoint-first", "melody-path-peer"])
def test_peer_voice_uses_section_key_not_piece_key(tmp_path, peer_voice):
    out = str(tmp_path / "p.mid")
    generator.generate_piece(_piece(peer_voice), out)

    # Section "away" occupies beats 16..48 (4 bars * 4 beats home, then 8 bars).
    m = mido.MidiFile(out)
    tpb = m.ticks_per_beat
    away_notes = []
    for t in m.tracks:
        if t.name != "Counterpoint":
            continue
        a = 0
        for g in t:
            a += g.time
            if g.type == "note_on" and g.velocity > 0 and 16 * tpb <= a < 48 * tpb:
                away_notes.append(g.note)

    assert away_notes, "expected the peer voice to play in the overriding section"
    scale = _scale("A", "mixolydian")
    outside = [n for n in away_notes if n % 12 not in scale]
    assert not outside, (
        f"peer voice played {len(outside)}/{len(away_notes)} notes outside "
        f"A mixolydian (pitch classes {sorted({n % 12 for n in outside})}) — "
        f"it is following the piece key instead of the section key"
    )
