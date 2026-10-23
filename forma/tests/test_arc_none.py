"""
test_arc_none.py — arc: "none" (hand-set velocities, no arc shaping at all).

Why this exists
---------------
Every section carries a dynamic arc, and the schema default is "swell". An arc
multiplies the velocities the author set (0.6x-1.25x), crossfades in from the
previous section's ending level over up to 4 bars, and — for harmony — clamps
the result into [40, 120]. "plateau" is documented as a no-op, but it is not
one in a sequence: after a fade it still blends up from the previous level, and
harmony's floor still applies.

arc: "none" is the explicit opt-out. It must:
  1. validate as a section arc,
  2. leave melody / harmony / drum velocities exactly as authored,
  3. ignore the previous section's ending level (no blend-in),
  4. not apply the 40 floor / 120 ceiling to harmony (only MIDI-valid 1..127),
and it must change NOTHING for any piece that doesn't write it — in particular
the schema default stays "swell".
"""

import sys
from pathlib import Path

import mido
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from intervals.core.generator import generate_piece, velocity_envelope
from intervals.core.schemas import PieceModel, SectionModel
from intervals.music.rhythm import (
    RhythmEvent,
    apply_velocity_arc,
    arc_multiplier,
    blended_arc_multiplier,
)


# ---------------------------------------------------------------------------
# Unit: the curve itself
# ---------------------------------------------------------------------------

class TestNoneCurve:
    @pytest.mark.parametrize("t", [0.0, 0.25, 0.5, 1.0])
    def test_multiplier_is_unity_everywhere(self, t):
        assert arc_multiplier("none", t) == 1.0

    def test_no_blend_from_previous_section(self):
        # prev section ended at 0.65 (fade_out). "none" must not ease up from it.
        assert blended_arc_multiplier("none", 0.0, prev_end=0.65, blend_t=0.25) == 1.0
        assert blended_arc_multiplier("none", 0.1, prev_end=1.25, blend_t=0.25) == 1.0

    def test_plateau_still_blends_documenting_the_difference(self):
        # This is WHY "none" exists: plateau starts at prev_end, not at 1.0.
        assert blended_arc_multiplier("plateau", 0.0, prev_end=0.65, blend_t=0.25) == pytest.approx(0.65)

    def test_melody_envelope_ignores_previous_ending(self):
        for bar in range(8):
            assert velocity_envelope("none", bar, 8, prev_arc_end=0.65, blend_bars=2.0) == 1.0


# ---------------------------------------------------------------------------
# Unit: harmony's per-chord velocity (the only place with a clamp)
# ---------------------------------------------------------------------------

def _events(scale):
    return [RhythmEvent(start_beat=0.0, duration_beats=1.0, velocity_scale=scale)]


class TestNoneVelocityClamp:
    def test_none_has_no_floor_of_40(self):
        out = apply_velocity_arc(_events(1.0), arc="none", base_velocity=30)
        assert out[0][1] == 30

    def test_none_has_no_ceiling_of_120(self):
        out = apply_velocity_arc(_events(1.0), arc="none", base_velocity=125)
        assert out[0][1] == 125

    def test_none_stays_midi_valid(self):
        assert apply_velocity_arc(_events(0.01), arc="none", base_velocity=10)[0][1] == 1
        assert apply_velocity_arc(_events(2.0), arc="none", base_velocity=120)[0][1] == 127

    def test_none_ignores_blend_arguments(self):
        out = apply_velocity_arc(
            _events(1.0), arc="none", base_velocity=64,
            arc_t=0.0, prev_arc_end=0.65, arc_blend_t=0.5,
        )
        assert out[0][1] == 64

    def test_plateau_and_existing_arcs_keep_the_40_120_clamp(self):
        # Regression guard: nothing that existed before changes.
        assert apply_velocity_arc(_events(1.0), arc="plateau", base_velocity=30)[0][1] == 40
        assert apply_velocity_arc(_events(1.0), arc="plateau", base_velocity=125)[0][1] == 120
        assert apply_velocity_arc(_events(1.0), arc="swell", base_velocity=30, arc_t=0.0)[0][1] == 40


# ---------------------------------------------------------------------------
# Schema
# ---------------------------------------------------------------------------

def _section(**over):
    s = {
        "name": "a", "bars": 4, "progression": ["i", "VII"],
        "density": "medium", "melody": "lyrical", "bass_style": "root_only",
        "rhythm": "free", "harmony_rhythm": {"rhythm": "sustain"},
    }
    s.update(over)
    return s


class TestSchema:
    def test_none_is_a_valid_arc(self):
        assert SectionModel.model_validate(_section(arc="none")).arc == "none"

    def test_default_arc_is_still_swell(self):
        # Deliberately NOT changed: flipping the default would change every
        # existing piece on its next render.
        assert SectionModel.model_validate(_section()).arc == "swell"

    def test_unknown_arc_still_rejected(self):
        with pytest.raises(Exception):
            SectionModel.model_validate(_section(arc="bogus"))


# ---------------------------------------------------------------------------
# Integration: rendered MIDI
# ---------------------------------------------------------------------------

LOW_VEL_MOTIF = {
    "name": "soft", "intervals": [0, 2, -1, 1], "rhythm": [1.5, 0.5, 1.0, 1.0],
    "velocities": [0.3, 0.3, 0.3, 0.3], "transform_pool": ["inversion"],
}


def _piece(arcs, harmony_motif=False, drums=True):
    secs = []
    for i, arc in enumerate(arcs):
        s = _section(name=f"s{i}", bars=8, arc=arc,
                     progression=["i", "VII", "iv", "v"], rest_probability=0.0)
        if harmony_motif:
            # A hand-set harmony velocity of 19: well under the 40 floor.
            s["harmony_velocity"] = 19
        if drums:
            s["drums"] = {"pattern": "backbeat"}
        secs.append(s)
    return {
        "name": "arc none", "title": "arc none", "key": "D", "mode": "dorian",
        "tempo": {"min": 90, "max": 90}, "seed": 42,
        "motif": LOW_VEL_MOTIF, "sections": secs,
    }


def _notes(path, track_name, bars=None, beats_per_bar=4):
    mid = mido.MidiFile(path)
    tr = next(t for t in mid.tracks if t.name == track_name)
    t, out = 0, []
    for m in tr:
        t += m.time
        if m.type == "note_on" and m.velocity > 0:
            out.append((round(t / mid.ticks_per_beat, 4), m.note, m.velocity))
    out.sort()
    if bars is not None:
        lo, hi = bars[0] * beats_per_bar, bars[1] * beats_per_bar
        out = [n for n in out if lo <= n[0] < hi]
    return out


class TestRender:
    def test_single_section_none_equals_plateau_for_melody_and_drums(self, tmp_path):
        a = generate_piece(_piece(["none"]), str(tmp_path / "none.mid"))
        b = generate_piece(_piece(["plateau"]), str(tmp_path / "plat.mid"))
        assert _notes(a, "Melody") == _notes(b, "Melody")
        assert _notes(a, "Drums") == _notes(b, "Drums")

    def test_none_ignores_previous_section_fade(self, tmp_path):
        # Section 2 is "none" in both renders; only section 1's arc differs.
        # Section 2's melody/drum velocities must be identical regardless.
        a = generate_piece(_piece(["fade_out", "none"]), str(tmp_path / "a.mid"))
        b = generate_piece(_piece(["none", "none"]), str(tmp_path / "b.mid"))
        for track in ("Melody", "Drums"):
            assert _notes(a, track, bars=(8, 16)) == _notes(b, track, bars=(8, 16))

    def test_plateau_after_fade_is_shaped_documenting_the_difference(self, tmp_path):
        a = generate_piece(_piece(["fade_out", "plateau"]), str(tmp_path / "a.mid"))
        b = generate_piece(_piece(["none", "none"]), str(tmp_path / "b.mid"))
        va = [n[2] for n in _notes(a, "Melody", bars=(8, 12))]
        vb = [n[2] for n in _notes(b, "Melody", bars=(8, 12))]
        assert va != vb and sum(va) < sum(vb)

    def test_harmony_below_40_survives_under_none(self, tmp_path):
        p = generate_piece(_piece(["none"], harmony_motif=True), str(tmp_path / "h.mid"))
        vels = [n[2] for n in _notes(p, "Harmony")]
        assert vels and min(vels) < 40

    def test_harmony_floor_still_applies_under_plateau(self, tmp_path):
        p = generate_piece(_piece(["plateau"], harmony_motif=True), str(tmp_path / "h.mid"))
        vels = [n[2] for n in _notes(p, "Harmony")]
        assert vels and min(vels) >= 40

    def test_piece_with_none_validates(self):
        PieceModel.model_validate(_piece(["none", "swell", "none"]))
