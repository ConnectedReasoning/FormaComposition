"""
test_voice_velocity.py — section-level harmony_velocity and bass_velocity.

Why this exists
---------------
Melody (voices[].velocity), extra voices and drums could be given velocities in
the JSON; harmony (fixed 65) and bass (fixed 70) could not. Paired with
arc: "none" (test_arc_none.py) these two fields complete hand control of
dynamics.

Contract
--------
  * harmony_velocity / bass_velocity are optional ints, 1..127.
  * Unset -> exactly the old behaviour (harmony 65, bass 70): byte-identical.
  * harmony_velocity is the base the harmony rhythm source scales. "sustain"
    scales by 1.0, so with arc: "none" every harmony note renders at exactly
    the value written. Other sources (pattern / motif) multiply it by their
    per-onset scale, as before.
  * bass_velocity is the bass base. Bass accents (root_fifth's fifth, walking
    and melodic off-beats, pulse repeats) are softer than the base but must
    NEVER be louder than it. Previously they had hard floors of 50-60, so at a
    low base the "softer" note came out LOUDER than the downbeat.
  * root_only and pedal add a +/-4 humanization jitter around the base; that
    is deliberate (it fixed a flat-bass problem) and is documented, not removed.
"""

import sys
from pathlib import Path

import mido
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from intervals.core.generator import generate_piece
from intervals.core.schemas import SectionModel
from intervals.music.bass import generate_bass
from intervals.music.harmony import resolve_chord  # noqa: F401  (import guard only)

BASS_STYLES = ["root_only", "root_fifth", "walking", "steady", "melodic", "pulse", "pedal", "motif"]
JITTER_STYLES = {"root_only", "pedal"}   # +/-4 around the base, by design

MOTIF = {
    "name": "m", "intervals": [0, 2, -1, 1], "rhythm": [1.5, 0.5, 1.0, 1.0],
    "velocities": [0.8, 0.8, 0.8, 0.8], "transform_pool": ["inversion"],
}


def _section(**over):
    s = {
        "name": "a", "bars": 8, "progression": ["i", "VII", "iv", "v"],
        "density": "medium", "melody": "lyrical", "bass_style": "root_fifth",
        "rhythm": "free", "harmony_rhythm": {"rhythm": "sustain"},
        "rest_probability": 0.0, "arc": "none",
    }
    s.update(over)
    return s


def _piece(**sec_over):
    return {
        "name": "v", "title": "v", "key": "D", "mode": "dorian",
        "tempo": {"min": 90, "max": 90}, "seed": 42, "motif": MOTIF,
        "sections": [_section(**sec_over)],
    }


def _vels(path, track):
    mid = mido.MidiFile(path)
    tr = next(t for t in mid.tracks if t.name == track)
    return [m.velocity for m in tr if m.type == "note_on" and m.velocity > 0]


def _render(tmp_path, **sec_over):
    return generate_piece(_piece(**sec_over), str(tmp_path / "p.mid"))


# ---------------------------------------------------------------------------
# Schema
# ---------------------------------------------------------------------------

class TestSchema:
    def test_default_is_unset(self):
        s = SectionModel.model_validate(_section())
        assert s.harmony_velocity is None and s.bass_velocity is None

    @pytest.mark.parametrize("field", ["harmony_velocity", "bass_velocity"])
    @pytest.mark.parametrize("v", [1, 64, 127])
    def test_accepts_midi_range(self, field, v):
        assert getattr(SectionModel.model_validate(_section(**{field: v})), field) == v

    @pytest.mark.parametrize("field", ["harmony_velocity", "bass_velocity"])
    @pytest.mark.parametrize("v", [0, 128, -5])
    def test_rejects_out_of_range(self, field, v):
        with pytest.raises(Exception):
            SectionModel.model_validate(_section(**{field: v}))


# ---------------------------------------------------------------------------
# Harmony
# ---------------------------------------------------------------------------

class TestHarmonyVelocity:
    def test_default_unchanged_is_65(self, tmp_path):
        assert set(_vels(_render(tmp_path), "Harmony")) == {65}

    @pytest.mark.parametrize("v", [18, 40, 90, 127])
    def test_sustain_with_arc_none_renders_exactly_the_value(self, tmp_path, v):
        p = _render(tmp_path, harmony_velocity=v)
        assert set(_vels(p, "Harmony")) == {v}

    def test_value_below_the_old_40_floor_survives_with_none(self, tmp_path):
        assert min(_vels(_render(tmp_path, harmony_velocity=22), "Harmony")) == 22

    def test_arc_still_multiplies_it_when_an_arc_is_chosen(self, tmp_path):
        # harmony_velocity is the BASE; an explicit arc still shapes it.
        p = _render(tmp_path, harmony_velocity=100, arc="fade_out")
        vels = _vels(p, "Harmony")
        assert max(vels) > min(vels)        # shaped, not flat
        assert max(vels) <= 100             # fade_out never exceeds its start

    def test_pattern_source_scales_the_base(self, tmp_path):
        p = _render(
            tmp_path, harmony_velocity=100,
            harmony_rhythm={"rhythm": "pattern"},
            harmony_pattern={"onsets": [0.0, 2.0], "durations": [2.0, 2.0],
                             "velocities": [0.5, 0.5], "length_beats": 4.0},
        )
        assert set(_vels(p, "Harmony")) == {50}


# ---------------------------------------------------------------------------
# Bass
# ---------------------------------------------------------------------------

class TestBassVelocity:
    def test_default_root_fifth_unchanged(self, tmp_path):
        # Pin of today's behaviour: root at 70, fifth at max(60, 70-8) = 62.
        assert set(_vels(_render(tmp_path), "Bass")) == {70, 62}

    def test_root_fifth_exact_with_explicit_value(self, tmp_path):
        assert set(_vels(_render(tmp_path, bass_velocity=100), "Bass")) == {100, 92}

    def test_root_fifth_accent_never_louder_than_base_at_low_values(self, tmp_path):
        # The bug this guards: base 45 used to give a fifth at max(60, 37) = 60.
        vels = _vels(_render(tmp_path, bass_velocity=45), "Bass")
        assert max(vels) == 45 and min(vels) <= 45

    @pytest.mark.parametrize("style", BASS_STYLES)
    @pytest.mark.parametrize("v", [30, 45, 100])
    def test_no_style_exceeds_the_base(self, tmp_path, style, v):
        vels = _vels(_render(tmp_path, bass_style=style, bass_velocity=v), "Bass")
        assert vels
        slack = 4 if style in JITTER_STYLES else 0
        assert max(vels) <= v + slack, (style, v, max(vels))
        assert min(vels) >= 1

    @pytest.mark.parametrize("style", ["root_fifth", "walking", "melodic", "pulse"])
    def test_downbeat_hits_the_base_exactly(self, tmp_path, style):
        # The loudest note of these (non-jittered, non-figure) styles is the base.
        # steady / motif scale each note by a figure weight, so they are excluded.
        vels = _vels(_render(tmp_path, bass_style=style, bass_velocity=88), "Bass")
        assert max(vels) == 88

    @pytest.mark.parametrize("style", JITTER_STYLES)
    def test_jitter_styles_stay_within_four_of_base(self, tmp_path, style):
        vels = _vels(_render(tmp_path, bass_style=style, bass_velocity=80), "Bass")
        assert min(vels) >= 76 and max(vels) <= 84


class TestBassStyleFloorsDirect:
    """generate_bass() directly: the old floors must not invert accents."""

    @pytest.mark.parametrize("style", ["root_fifth", "walking", "melodic", "pulse"])
    def test_accents_not_louder_than_base_at_low_velocity(self, style):
        from intervals.music.harmony import resolve_chord
        chords = [resolve_chord(r, "D", "dorian") for r in ["i", "VII", "iv", "v"]]
        notes = generate_bass(chords, style=style, bars_per_chord=2.0, beats_per_bar=4,
                              density="medium", velocity=40, key="D", mode="dorian", seed=7)
        assert notes and max(n.velocity for n in notes) <= 40

    @pytest.mark.parametrize("style", ["root_fifth", "walking", "melodic", "pulse"])
    def test_default_velocity_70_output_is_unchanged_in_shape(self, style):
        # At the default base the floors never bound, so accents are v-8 / v-6 /
        # v-10 / v-15 exactly as before: nothing may fall below 55.
        from intervals.music.harmony import resolve_chord
        chords = [resolve_chord(r, "D", "dorian") for r in ["i", "VII", "iv", "v"]]
        notes = generate_bass(chords, style=style, bars_per_chord=2.0, beats_per_bar=4,
                              density="medium", velocity=70, key="D", mode="dorian", seed=7)
        assert min(n.velocity for n in notes) >= 55 and max(n.velocity for n in notes) <= 70
