"""
Tests for intervals.music.bass — the bass-register helpers and the eight
named bass styles (root_only, root_fifth, walking, steady, melodic,
pulse, pedal, motif).

Where a style's output is fully positional (root_only, root_fifth, pulse,
pedal), tests use directly-constructed root-position VoicedChord fixtures
and assert hand-verified exact output. Where a style is RNG/scale-driven
(walking, steady, melodic, motif), tests assert seeded determinism and
hand-verified structural properties instead of the full note sequence.
"""
import warnings

import pytest

from intervals.music.bass import (
    BASS_OCTAVE_BOTTOM,
    BASS_OCTAVE_TOP,
    BASS_STYLES,
    BassNote,
    _apply_swing_to_bass,
    approach_note,
    bass_chord_tones,
    bass_fifth,
    bass_root,
    bass_third,
    generate_bass,
    get_bass_scale_tones,
    scale_neighbors,
    style_pedal,
    style_pulse,
    style_root_fifth,
    style_root_only,
)
from intervals.music.harmony import VoicedChord, resolve_progression


def _root_position_chord(root="D", quality="minor7", notes=(62, 65, 69, 72)):
    """A chord whose midi_notes are in canonical root-third-fifth-seventh
    order, so bass_root/bass_fifth/bass_third's positional indexing means
    exactly what their names say (see note in bass tests about
    resolve_progression's already-inverted output making that indexing
    fragile downstream -- avoided here by construction)."""
    return VoicedChord(root_name=root, quality=quality, midi_notes=list(notes),
                        inversion=0, roman="i", degree=0)


# ===========================================================================
# Bass-register tone helpers
# ===========================================================================

class TestBassToneHelpers:
    def test_bass_root(self):
        assert bass_root(_root_position_chord()) == 38  # D pc=2, 36+2

    def test_bass_fifth(self):
        assert bass_fifth(_root_position_chord()) == 45  # midi_notes[2]=69, pc9 -> 36+9

    def test_bass_third(self):
        assert bass_third(_root_position_chord()) == 41  # midi_notes[1]=65, pc5 -> 36+5

    def test_bass_fifth_none_for_two_note_chord(self):
        chord = _root_position_chord(notes=(62, 65))
        assert bass_fifth(chord) is None

    def test_bass_third_none_for_single_note_chord(self):
        chord = _root_position_chord(notes=(62,))
        assert bass_third(chord) is None

    def test_bass_chord_tones_reflects_actual_voiced_pitch_classes(self):
        chord = _root_position_chord(notes=(62, 65, 69, 72))
        # pitch classes 2,5,9,0 (72%12=0) -> bass register: 38,41,45,36
        assert bass_chord_tones(chord) == sorted({36, 38, 41, 45})

    def test_get_bass_scale_tones_d_dorian_hand_verified(self):
        assert get_bass_scale_tones("D", "dorian") == [35, 36, 38, 40, 41, 43, 45, 47, 48, 50]

    def test_approach_note_prefers_non_scale_tone(self):
        scale = get_bass_scale_tones("D", "dorian")
        # 39 is not in the D dorian scale -> preferred over 41 (which is)
        assert approach_note(40, scale) == 39

    def test_scale_neighbors_hand_verified_order(self):
        scale = get_bass_scale_tones("D", "dorian")
        # neighbors of 38 within +/-4, closest first, ties in scale order
        assert scale_neighbors(38, scale) == [36, 40, 35, 41]


# ===========================================================================
# style_root_only
# ===========================================================================

class TestStyleRootOnly:
    def test_hand_verified_one_root_per_chord(self):
        chords = [_root_position_chord("D"), _root_position_chord("G", notes=(67, 71, 74, 77))]
        notes = style_root_only(chords, [1.0, 1.0], beats_per_bar=4, velocity=70, seed=1)
        # Pitch/timing are exact; velocity now carries a small deterministic
        # jitter (+/-4) instead of being pinned to exactly 70 for every note
        # — see style_root_only's docstring. Same seed -> same jitter, so
        # this is still a reproducible assertion, just not a bare equality
        # on the full tuple.
        assert [n.midi_note for n in notes] == [38, 43]
        assert [n.start_beat for n in notes] == [0.0, 4.0]
        assert [n.duration_beats for n in notes] == [4.0, 4.0]
        assert all(66 <= n.velocity <= 74 for n in notes)
        # Same seed reproduces the same jitter exactly.
        again = style_root_only(chords, [1.0, 1.0], beats_per_bar=4, velocity=70, seed=1)
        assert notes == again


# ===========================================================================
# style_root_fifth
# ===========================================================================

class TestStyleRootFifth:
    def test_hand_verified_alternates_root_and_fifth(self):
        chords = [_root_position_chord("D")]
        notes = style_root_fifth(chords, [1.0], beats_per_bar=4, velocity=70)
        assert notes == [
            BassNote(38, 0.0, 2.0, 70),
            BassNote(45, 2.0, 2.0, 62),  # max(60, 70-8) = 62
        ]

    def test_falls_back_to_root_when_no_fifth_available(self):
        chords = [_root_position_chord("D", notes=(62,))]  # single note, no fifth
        notes = style_root_fifth(chords, [1.0], beats_per_bar=4, velocity=70)
        assert notes[0].midi_note == notes[1].midi_note == 38


# ===========================================================================
# style_pulse
# ===========================================================================

class TestStylePulse:
    def test_hand_verified_repeats_root_every_subdivision(self):
        chords = [_root_position_chord("D")]
        notes = style_pulse(chords, [1.0], beats_per_bar=4, subdivision=1.0, velocity=75)
        assert [n.start_beat for n in notes] == [0.0, 1.0, 2.0, 3.0]
        assert all(n.midi_note == 38 for n in notes)
        # first hit at full velocity, rest softened by 15 (floored at 55)
        assert notes[0].velocity == 75
        assert all(n.velocity == 60 for n in notes[1:])


# ===========================================================================
# style_pedal
# ===========================================================================

class TestStylePedal:
    def test_holds_first_chord_root_across_every_chord(self):
        chords = [_root_position_chord("D"), _root_position_chord("G", notes=(67, 71, 74, 77))]
        notes = style_pedal(chords, [1.0, 1.0], beats_per_bar=4, velocity=65)
        assert [n.midi_note for n in notes] == [38, 38]  # D pedal held under both chords
        assert [n.start_beat for n in notes] == [0.0, 4.0]
        assert [n.duration_beats for n in notes] == [4.0, 4.0]

    def test_explicit_tonic_overrides_first_chord_root(self):
        chords = [_root_position_chord("D")]
        notes = style_pedal(chords, [1.0], beats_per_bar=4, tonic_midi=48)
        assert notes[0].midi_note == 48


# ===========================================================================
# generate_bass — dispatch, seeding, rest handling
# ===========================================================================

class TestGenerateBass:
    def test_unknown_style_raises(self):
        chords = [_root_position_chord("D")]
        with pytest.raises(ValueError, match="Unknown bass style"):
            generate_bass(chords, style="bogus", seed=1)

    def test_walking_style_reproducible_with_same_seed(self):
        chords = resolve_progression(["i", "iv"], "D", "dorian", density="medium")
        a = generate_bass(chords, style="walking", bars_per_chord=1.0,
                           key="D", mode="dorian", seed=1)
        b = generate_bass(chords, style="walking", bars_per_chord=1.0,
                           key="D", mode="dorian", seed=1)
        assert a == b

    def test_rest_probability_ignored_and_warned_for_continuous_style(self):
        """walking depends on stepwise continuity -- bass_rest_probability
        must be refused (with a warning), not silently applied."""
        chords = resolve_progression(["i", "iv"], "D", "dorian", density="medium")
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            with_rests = generate_bass(chords, style="walking", bars_per_chord=1.0,
                                        key="D", mode="dorian", seed=1, rest_probability=0.9)
        without_rests = generate_bass(chords, style="walking", bars_per_chord=1.0,
                                       key="D", mode="dorian", seed=1, rest_probability=0.0)
        assert any("ignored" in str(w.message) for w in caught)
        assert with_rests == without_rests  # unaffected, not thinned

    def test_rest_probability_thins_notes_for_noncontinuous_style(self):
        """root_fifth has no continuity requirement -- rest_probability
        actually drops notes (deterministically, given a seed)."""
        chords = [_root_position_chord("D"), _root_position_chord("G", notes=(67, 71, 74, 77))]
        full = generate_bass(chords, style="root_fifth", bars_per_chord=1.0, seed=1,
                              rest_probability=0.0)
        thinned = generate_bass(chords, style="root_fifth", bars_per_chord=1.0, seed=1,
                                 rest_probability=0.9)
        assert len(thinned) < len(full)

    def test_motif_style_falls_back_to_root_only_without_a_motif(self):
        """Edge case: bass_style='motif' with no motif dict supplied must
        warn and degrade to root_only rather than crash or silently
        produce nothing."""
        chords = [_root_position_chord("D"), _root_position_chord("G", notes=(67, 71, 74, 77))]
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            notes = generate_bass(chords, style="motif", bars_per_chord=1.0, seed=1, motif=None)
        assert any("falling back to root_only" in str(w.message) for w in caught)
        assert notes == style_root_only(chords, [1.0, 1.0], beats_per_bar=4, velocity=70, seed=1)

    def test_motif_style_reproducible_with_a_real_motif(self):
        chords = resolve_progression(["i", "iv"], "D", "dorian", density="medium")
        motif = {"intervals": [2, -1, 3], "rhythm": [1.0, 1.0, 1.0]}
        a = generate_bass(chords, style="motif", bars_per_chord=1.0,
                           key="D", mode="dorian", seed=1, motif=motif)
        b = generate_bass(chords, style="motif", bars_per_chord=1.0,
                           key="D", mode="dorian", seed=1, motif=motif)
        assert a == b

    def test_empty_chord_list_returns_no_notes(self):
        assert generate_bass([], style="root_only", seed=1) == []


# ===========================================================================
# Bugfix / feature: swing applied uniformly, independent of bass style.
#
# Previously only style_melodic and style_motif consulted swing_ratio at
# all -- every other style silently ignored it, even though every style
# accepted it as a parameter. Swing is now applied as a single centralized
# post-pass (_apply_swing_to_bass) after style dispatch, so every style
# gets correct swing behavior automatically. Styles whose figures never
# place a note on an offbeat eighth (root_only, root_fifth, walking,
# steady, pedal, pulse at its default subdivision) are correctly
# unaffected -- not because they're skipped, but because there's nothing
# on their onset grid for swing to displace.
# ===========================================================================

class TestApplySwingToBass:
    def test_straight_ratio_is_a_no_op(self):
        notes = [BassNote(50, 1.5, 0.5, 70)]
        assert _apply_swing_to_bass(notes, 0.5) == notes

    def test_on_beat_note_passes_through_unchanged(self):
        notes = [BassNote(50, 2.0, 1.0, 70)]
        assert _apply_swing_to_bass(notes, 0.67) == notes

    def test_offbeat_note_is_delayed_and_shortened(self):
        notes = [BassNote(50, 1.5, 0.5, 70)]
        result = _apply_swing_to_bass(notes, 0.67)
        assert result[0].start_beat == pytest.approx(1.67)
        assert result[0].duration_beats == pytest.approx(0.33)
        assert result[0].midi_note == 50
        assert result[0].velocity == 70

    def test_duration_is_floored_at_point_one_beat(self):
        notes = [BassNote(50, 1.5, 0.15, 70)]
        result = _apply_swing_to_bass(notes, 0.9)
        assert result[0].duration_beats == pytest.approx(0.1)

    def test_empty_list_returns_empty_list(self):
        assert _apply_swing_to_bass([], 0.67) == []

    def test_mixed_on_and_off_beat_notes_in_one_pass(self):
        notes = [BassNote(50, 0.0, 1.0, 70), BassNote(52, 1.5, 0.5, 70),
                 BassNote(50, 2.0, 1.0, 70)]
        result = _apply_swing_to_bass(notes, 0.67)
        starts = [round(n.start_beat, 2) for n in result]
        assert starts == [0.0, 1.67, 2.0]


class TestSwingIsUniformAcrossEveryStyle:
    def _kwargs_for(self, style):
        if style == "motif":
            return {"motif": {"intervals": [2, -1, 3, -2], "rhythm": [1.0, 0.5, 0.5, 1.0]}}
        return {}

    @pytest.mark.parametrize("style", list(BASS_STYLES.keys()))
    def test_every_style_accepts_swing_without_crashing(self, style):
        chords = resolve_progression(["i", "iv", "v", "i"], "D", "dorian", density="medium")
        notes = generate_bass(chords, style=style, bars_per_chord=1.0, key="D", mode="dorian",
                               swing=0.34, seed=1, **self._kwargs_for(style))
        assert isinstance(notes, list)

    @pytest.mark.parametrize("style", [
        "root_only", "root_fifth", "walking", "steady", "pulse", "pedal",
    ])
    def test_styles_with_no_offbeat_content_are_unaffected_by_swing(self, style):
        """Not skipped -- genuinely unaffected, because these styles never
        place a note on an offbeat eighth in the first place."""
        chords = resolve_progression(["i", "iv", "v", "i"], "D", "dorian", density="medium")
        swung = generate_bass(chords, style=style, bars_per_chord=1.0, key="D", mode="dorian",
                               swing=0.34, seed=1)
        straight = generate_bass(chords, style=style, bars_per_chord=1.0, key="D", mode="dorian",
                                  swing=0.0, seed=1)
        assert swung == straight

    @pytest.mark.parametrize("style", ["melodic", "motif"])
    def test_styles_with_offbeat_content_still_genuinely_swing(self, style):
        """Regression guard: the two styles that already worked before this
        refactor must still actually respond to swing, not just silently
        pass the byte-identity check above."""
        chords = resolve_progression(["i", "iv", "v", "i"], "D", "dorian", density="medium")
        swung = generate_bass(chords, style=style, bars_per_chord=1.0, key="D", mode="dorian",
                               swing=0.34, seed=1, **self._kwargs_for(style))
        straight = generate_bass(chords, style=style, bars_per_chord=1.0, key="D", mode="dorian",
                                  swing=0.0, seed=1, **self._kwargs_for(style))
        assert swung != straight
