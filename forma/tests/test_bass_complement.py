"""
bass_complement: "thin" -- the bass steps back where the melody is busy.

The bass is generated before the melody and never sees it. thin_bass_for_melody
is a post-pass: in any beat where the melody has 2+ onsets, the bass keeps only
its on-beat note (held through the beat); elsewhere it is untouched.
"""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from intervals.core.schemas import SectionModel
from intervals.music.bass import BassNote, thin_bass_for_melody
from intervals.music.melody import MelodyNote


def _bass_eighths(bars=1):
    return [BassNote(40 + (i % 4), i * 0.5, 0.5, 54) for i in range(8 * bars)]


def _mel(onsets, dur=0.5):
    return [MelodyNote(60, o, dur) for o in onsets]


def test_busy_melody_thins_offbeat_bass_and_holds_onbeat_note():
    out = thin_bass_for_melody(_bass_eighths(), _mel([i * 0.5 for i in range(8)]))
    assert [n.start_beat for n in out] == [0.0, 1.0, 2.0, 3.0]
    assert all(n.duration_beats == 1.0 for n in out)


def test_sparse_melody_leaves_bass_untouched():
    bass = _bass_eighths()
    out = thin_bass_for_melody(bass, _mel([0.0, 1.5, 2.0, 3.0], dur=1.0))
    assert [(n.start_beat, n.duration_beats) for n in out] == \
           [(n.start_beat, n.duration_beats) for n in bass]


def test_only_busy_beats_are_thinned():
    # melody busy in beat 0 only (onsets 0, 0.5); rest sparse
    out = thin_bass_for_melody(_bass_eighths(), _mel([0.0, 0.5, 2.0], dur=1.0))
    starts = [n.start_beat for n in out]
    assert 0.5 not in starts and 0.0 in starts       # beat 0 thinned
    assert 1.5 in starts and 2.5 in starts            # others intact
    assert out[0].duration_beats == 1.0


def test_pitches_and_velocity_never_change_and_input_not_mutated():
    bass = _bass_eighths()
    snap = [(n.midi_note, n.start_beat, n.duration_beats, n.velocity) for n in bass]
    out = thin_bass_for_melody(bass, _mel([i * 0.5 for i in range(8)]))
    assert snap == [(n.midi_note, n.start_beat, n.duration_beats, n.velocity) for n in bass]
    for n in out:
        assert (n.midi_note, n.velocity) in {(m, v) for m, _, _, v in snap}


def test_melody_rests_do_not_count_as_onsets():
    mel = [MelodyNote(None, 0.0, 0.5, is_rest=True), MelodyNote(60, 0.5, 0.5)]
    bass = _bass_eighths()
    assert len(thin_bass_for_melody(bass, mel)) == len(bass)


def test_empty_inputs():
    assert thin_bass_for_melody([], _mel([0.0, 0.5])) == []
    bass = _bass_eighths()
    assert len(thin_bass_for_melody(bass, [])) == len(bass)


def test_deterministic():
    mel = _mel([i * 0.5 for i in range(8)])
    a = thin_bass_for_melody(_bass_eighths(), mel)
    b = thin_bass_for_melody(_bass_eighths(), mel)
    assert [(n.midi_note, n.start_beat, n.duration_beats) for n in a] == \
           [(n.midi_note, n.start_beat, n.duration_beats) for n in b]


def test_schema_field_defaults_none_and_rejects_unknown_value():
    assert SectionModel.model_fields["bass_complement"].default is None
    with pytest.raises(Exception):
        SectionModel.model_validate({"name": "x", "bass_complement": "bogus"})
