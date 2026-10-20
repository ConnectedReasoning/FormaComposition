"""section.bass_motif: the bass plays its own riff under bass_style='motif'."""
import mido
import pytest

from intervals.core import generator
from intervals.core.schemas import PieceModel

RIFF_A = {"name": "a", "intervals": [0, 0, 0, 0], "rhythm": [1.0, 1.0, 1.0, 1.0]}
RIFF_B = {"name": "b", "intervals": [0, 2, -1, -1], "rhythm": [1.0, 1.0, 1.0, 1.0]}


def _piece(**section):
    sec = {"name": "s", "bars": 2, "rhythm": "free", "progression": ["I"],
           "chord_bars": [2], "bass_style": "motif",
           "bass_register": {"min": 33, "max": 57},
           "voices": [{"behavior": "lyrical"}]}
    sec.update(section)
    return {"key": "E", "mode": "dorian", "tempo": 90, "seed": 7,
            "motif": RIFF_A, "sections": [sec]}


def _bass_pitches(piece, tmp_path):
    out = tmp_path / "b.mid"
    generator.generate_piece(piece, str(out))
    for t in mido.MidiFile(out).tracks:
        if t.name == "Bass":
            return [m.note for m in t if m.type == "note_on" and m.velocity > 0]
    raise AssertionError("no Bass track")


def test_default_bass_follows_piece_motif(tmp_path):
    # RIFF_A is all repeats: one pitch only.
    assert len(set(_bass_pitches(_piece(), tmp_path))) == 1


def test_inline_bass_motif_overrides_piece_motif(tmp_path):
    ps = _bass_pitches(_piece(bass_motif=RIFF_B), tmp_path)
    assert len(set(ps)) > 1


def test_named_bass_motif_resolves_from_theme_pool(tmp_path):
    piece = _piece(bass_motif="b")
    piece.pop("motif")
    piece["motifs"] = [RIFF_A, RIFF_B]
    ps = _bass_pitches(piece, tmp_path)
    assert len(set(ps)) > 1


def test_bass_motif_must_be_bar_aligned():
    bad = {"name": "bad", "intervals": [0, 1, -1], "rhythm": [1.0, 1.0, 1.0]}
    with pytest.raises(ValueError, match="bass_motif"):
        PieceModel.model_validate(_piece(bass_motif=bad)).validate_against_theme(
            PieceModel.model_validate(_piece(bass_motif=bad)))


def test_bass_motif_needs_rhythm():
    bad = {"name": "norhythm", "intervals": [0, 1, -1, 0]}
    m = PieceModel.model_validate(_piece(bass_motif=bad))
    with pytest.raises(ValueError, match="rhythm"):
        m.validate_against_theme(m)
