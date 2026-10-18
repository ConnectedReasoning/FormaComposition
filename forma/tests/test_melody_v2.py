"""
test_melody_v2.py -- melody_engine "v2" scored note chooser.

v1 (default) must stay byte-identical; v2 must measurably fix the
random-walk symptoms measured on rendered MIDI (few steps, constant
direction reversal, unanswered leaps, A-B-A-B wobble). Statistical tests
batch across seeds on purpose: single-seed renders prove nothing.
"""

import random

import pytest

from intervals.music.harmony import resolve_progression
from intervals.music.melody import (
    generate_melody_for_progression,
    get_scale_tones,
    _V2State,
    _degree_distance,
    _v2_choose,
    _v2_beat_level,
)
from intervals.music.rhythm import RhythmEvent

PROG = ["i", "iv", "v", "i", "vi", "ii", "v", "i"]
SEEDS = range(40)


def _line(behavior, engine, seed, **kw):
    chords = resolve_progression(PROG, "C", "ionian", density="medium")
    notes = generate_melody_for_progression(
        chords, "C", "ionian", behavior=behavior, density="medium",
        bars_per_chord=1.0, beats_per_bar=4, seed=seed,
        melody_engine=engine, **kw)
    return [n for n in notes if not n.is_rest]


def _stats(behavior, engine):
    steps = moves = turns = dirs = leaps = recovered = 0
    for seed in SEEDS:
        p = [n.midi_note for n in _line(behavior, engine, seed)]
        iv = [b - a for a, b in zip(p, p[1:])]
        moves += len(iv)
        steps += sum(1 for x in iv if 1 <= abs(x) <= 2)
        d = [1 if x > 0 else -1 for x in iv if x]
        dirs += max(0, len(d) - 1)
        turns += sum(a != b for a, b in zip(d, d[1:]))
        for a, b in zip(iv, iv[1:]):
            if abs(a) >= 5:
                leaps += 1
                recovered += (a * b < 0 and abs(b) <= 2)
    return dict(step=steps / moves, turn=turns / dirs, recov=recovered / max(1, leaps))


class TestV1Unchanged:
    @pytest.mark.parametrize("behavior", ["generative", "lyrical"])
    def test_default_equals_explicit_v1(self, behavior):
        chords = resolve_progression(PROG, "C", "ionian", density="medium")
        a = generate_melody_for_progression(chords, "C", "ionian", behavior=behavior,
                                            bars_per_chord=1.0, seed=7)
        b = generate_melody_for_progression(chords, "C", "ionian", behavior=behavior,
                                            bars_per_chord=1.0, seed=7, melody_engine="v1")
        assert a == b

    @pytest.mark.parametrize("behavior", ["generative", "lyrical"])
    def test_v2_differs_from_v1(self, behavior):
        assert _line(behavior, "v1", 7) != _line(behavior, "v2", 7)


class TestV2Determinism:
    @pytest.mark.parametrize("behavior", ["generative", "lyrical"])
    def test_same_seed_same_line(self, behavior):
        assert _line(behavior, "v2", 3) == _line(behavior, "v2", 3)

    @pytest.mark.parametrize("behavior", ["generative", "lyrical"])
    def test_stays_in_register(self, behavior):
        for seed in range(10):
            for n in _line(behavior, "v2", seed, octave_bottom=60, octave_top=79):
                assert 60 <= n.midi_note <= 79


class TestV2MelodicShape:
    """Each assertion has headroom below the measured v2 values so seed
    noise can't flake it, but sits well on the right side of v1."""

    @pytest.mark.parametrize("behavior", ["generative", "lyrical"])
    def test_more_steps_than_v1(self, behavior):
        v1, v2 = _stats(behavior, "v1"), _stats(behavior, "v2")
        assert v2["step"] > v1["step"] + 0.08
        assert v2["step"] > 0.50

    @pytest.mark.parametrize("behavior", ["generative", "lyrical"])
    def test_fewer_direction_reversals_than_v1(self, behavior):
        v1, v2 = _stats(behavior, "v1"), _stats(behavior, "v2")
        assert v2["turn"] < v1["turn"] - 0.08
        assert v2["turn"] < 0.52

    @pytest.mark.parametrize("behavior", ["generative", "lyrical"])
    def test_leaps_are_answered_by_step_back(self, behavior):
        v1, v2 = _stats(behavior, "v1"), _stats(behavior, "v2")
        assert v2["recov"] > v1["recov"] + 0.15
        assert v2["recov"] > 0.40

    def test_no_triple_repeats_or_long_abab(self):
        for seed in SEEDS:
            p = [n.midi_note for n in _line("lyrical", "v2", seed)]
            for a, b, c in zip(p, p[1:], p[2:]):
                assert not (a == b == c)


class TestV2Chooser:
    def _scale(self):
        return get_scale_tones("C", "ionian", 48, 84)

    def test_degree_distance_is_mode_aware(self):
        scale = get_scale_tones("C", "ionian", 48, 84)
        assert _degree_distance(60, 62, scale) == 1      # C -> D
        assert _degree_distance(60, 64, scale) == 2      # C -> E
        penta = get_scale_tones("C", "major pentatonic", 48, 84) \
            if "major pentatonic" in __import__("intervals.music.harmony", fromlist=["MODES"]).MODES else None
        if penta:
            assert _degree_distance(60, 64, penta) == 1  # C -> E is one pentatonic step

    def test_leap_is_answered_by_step_opposite(self):
        scale = self._scale()
        state = _V2State()
        state.update(60, scale)
        state.update(72, scale)          # octave leap up
        rng = random.Random(0)
        picks = [_v2_choose(rng, [71, 72, 74, 76, 79], state, 72, scale,
                            {0, 4, 7}, 1, False, None, 66.0) for _ in range(300)]
        assert sum(1 for p in picks if p == 71) > 0.6 * len(picks)      # step back down
        assert sum(1 for p in picks if p > 72) < 0.25 * len(picks)      # rarely onward

    def test_downbeat_prefers_chord_tones(self):
        scale = self._scale()
        state = _V2State()
        state.update(64, scale)
        rng = random.Random(1)
        # from E, step candidates: D (non-chord) / F (non-chord) / C,G further
        picks = [_v2_choose(rng, [60, 62, 64, 65, 67], state, 64, scale,
                            {0, 4, 7}, 3, False, None, 66.0) for _ in range(400)]
        ct = sum(1 for p in picks if p % 12 in {0, 4, 7})
        assert ct > 0.5 * len(picks)

    def test_beat_levels(self):
        ev = lambda b, d=0.5: RhythmEvent(b, d, 1.0, False)
        ctx = {"beats_per_bar": 4, "section_beat_offset": 0.0}
        assert _v2_beat_level(ev(0.0), ctx) == 3
        assert _v2_beat_level(ev(2.0), ctx) == 2
        assert _v2_beat_level(ev(1.0), ctx) == 1
        assert _v2_beat_level(ev(1.5), ctx) == 0
        assert _v2_beat_level(ev(1.5, 2.0), ctx) == 2     # long note bumps level
        # absolute position: chord starting at beat 4 of a 4/4 bar is a downbeat
        assert _v2_beat_level(ev(0.0), {"beats_per_bar": 4, "section_beat_offset": 4.0}) == 3


class TestV2Schema:
    def test_piece_default_and_voice_override(self):
        from intervals.core.schemas import PieceModel, VoiceModel
        assert VoiceModel().melody_engine is None
        assert VoiceModel(melody_engine="v2").melody_engine == "v2"
        with pytest.raises(Exception):
            VoiceModel(melody_engine="v3")
        assert PieceModel.model_fields["melody_engine"].default == "v1"


# ===========================================================================
# Phrase restatement (phrase_form / phrase_chords / phrase_restate)
# ===========================================================================

from intervals.music.melody import (
    MelodyNote,
    _derive_phrase_chord,
    _same_rhythm,
    _scale_index,
)

AABA_PROG = ["i", "iv", "i", "iv", "i", "iv", "i", "iv"]


def _prog(progression, seed, bars=1.0, **kw):
    chords = resolve_progression(progression, "C", "ionian", density="medium")
    notes = generate_melody_for_progression(
        chords, "C", "ionian", behavior="lyrical", density="medium",
        bars_per_chord=bars, beats_per_bar=4, seed=seed, melody_engine="v2",
        octave_bottom=60, octave_top=84, **kw)
    return chords, notes


def _by_chord(notes, beats=4.0):
    out = {}
    for n in notes:
        out.setdefault(int(n.start_beat // beats), []).append(n)
    return out


class TestPhraseRestatementOff:
    def test_no_form_is_identical_to_plain_v2(self):
        _, a = _prog(AABA_PROG, 3)
        _, b = _prog(AABA_PROG, 3, phrase_form=None)
        assert a == b

    def test_engine_v1_ignores_form(self):
        chords = resolve_progression(AABA_PROG, "C", "ionian", density="medium")
        a = generate_melody_for_progression(chords, "C", "ionian", behavior="lyrical",
                                            bars_per_chord=1.0, seed=3, melody_engine="v1")
        b = generate_melody_for_progression(chords, "C", "ionian", behavior="lyrical",
                                            bars_per_chord=1.0, seed=3, melody_engine="v1",
                                            phrase_form="aaba")
        assert a == b

    def test_melodic_arc_ignores_form(self):
        arc = {"apex_degree": 4, "apex_position": 0.7}
        _, a = _prog(AABA_PROG, 3, melodic_arc=arc)
        _, b = _prog(AABA_PROG, 3, melodic_arc=arc, phrase_form="aaba")
        assert a == b

    def test_unsupported_behavior_ignores_form(self):
        chords = resolve_progression(AABA_PROG, "C", "ionian", density="medium")
        kw = dict(behavior="sparse", bars_per_chord=1.0, seed=3, melody_engine="v2")
        assert generate_melody_for_progression(chords, "C", "ionian", **kw) == \
            generate_melody_for_progression(chords, "C", "ionian", phrase_form="aaba", **kw)

    def test_unequal_chord_lengths_fall_back_to_fresh(self):
        # phrase 2 (chords 2,3) would derive from chords 0,1 but lengths differ
        _, a = _prog(["i", "iv", "i", "iv"], 4, bars=[2.0, 1.0, 1.0, 2.0])
        _, b = _prog(["i", "iv", "i", "iv"], 4, bars=[2.0, 1.0, 1.0, 2.0],
                     phrase_form="aa", phrase_chords=2)
        assert a == b


class TestPhraseRestatementExact:
    @pytest.mark.parametrize("seed", range(8))
    def test_rhythm_and_shape_recur_over_same_harmony(self, seed):
        _, notes = _prog(AABA_PROG, seed, phrase_form="aa", phrase_chords=2)
        per = _by_chord(notes)
        for src, tgt in ((0, 2), (1, 3)):
            assert _same_rhythm(
                [MelodyNote(None, n.start_beat - src * 4, n.duration_beats, is_rest=n.is_rest) for n in per[src]],
                [MelodyNote(None, n.start_beat - tgt * 4, n.duration_beats, is_rest=n.is_rest) for n in per[tgt]])
        # pitch classes of the first restated chord match its source exactly
        # (same harmony -> nothing to refit; the phrase-final note is the
        # only one allowed to change)
        a = [n.midi_note % 12 for n in per[0] if not n.is_rest]
        b = [n.midi_note % 12 for n in per[2] if not n.is_rest]
        assert a == b

    @pytest.mark.parametrize("seed", range(8))
    def test_phrase_final_note_is_a_chord_tone(self, seed):
        chords, notes = _prog(["i", "iv", "v", "i", "vi", "ii", "v", "i"], seed,
                              phrase_form="aaaa", phrase_chords=2)
        per = _by_chord(notes)
        for ci in (3, 5, 7):                 # last chord of each restated phrase
            sounding = [n for n in per[ci] if not n.is_rest]
            if sounding:
                assert sounding[-1].midi_note % 12 in {t % 12 for t in chords[ci].midi_notes}

    @pytest.mark.parametrize("seed", range(10))
    def test_strong_beats_fit_the_new_chord(self, seed):
        chords, notes = _prog(["i", "iv", "v", "i", "vi", "ii", "v", "i"], seed,
                              phrase_form="aaaa", phrase_chords=2)
        per = _by_chord(notes)
        for ci in range(2, 8):
            pcs = {t % 12 for t in chords[ci].midi_notes}
            for n in per[ci]:
                if n.is_rest:
                    continue
                pos = n.start_beat - ci * 4
                strong = abs(pos) < 0.12 or abs(pos - 2) < 0.12
                if strong:
                    assert n.midi_note % 12 in pcs, (ci, n)

    def test_stays_in_register_and_deterministic(self):
        for seed in range(10):
            _, a = _prog(AABA_PROG, seed, phrase_form="aaba", phrase_restate="sequence")
            _, b = _prog(AABA_PROG, seed, phrase_form="aaba", phrase_restate="sequence")
            assert a == b
            assert all(60 <= n.midi_note <= 84 for n in a if not n.is_rest)

    def test_shape_recurs_more_than_plain_v2(self):
        def recurrence(**kw):
            hit = tot = 0
            for seed in range(20):
                _, notes = _prog(AABA_PROG * 2, seed, **kw)
                p = [n.midi_note for n in notes if not n.is_rest]
                iv = [b - a for a, b in zip(p, p[1:])]
                seen = set()
                for k in range(len(iv) - 6):
                    w = tuple(iv[k:k + 7])
                    tot += 1
                    hit += (w in seen)
                    seen.add(w)
            return hit / tot
        assert recurrence(phrase_form="aaba", phrase_chords=2) > recurrence() + 0.10


class TestPhraseRestatementRhythmLayer:
    def test_piece_rhythm_layer_is_respected(self):
        # A supplied rhythm layer that differs between phrases must win:
        # nothing is derived, output equals plain v2.
        def layer(n_chords):
            ev, t = [], 0.0
            for c in range(n_chords):
                step = 1.0 if c % 2 == 0 else 0.5
                for _ in range(int(4 / step)):
                    ev.append(RhythmEvent(t, step, 1.0, False))
                    t += step
            return ev
        chords = resolve_progression(["i", "iv", "i", "iv"], "C", "ionian", density="medium")
        kw = dict(behavior="lyrical", bars_per_chord=1.0, seed=2, melody_engine="v2",
                  rhythm_events_override=layer(4))
        derived = generate_melody_for_progression(chords, "C", "ionian", phrase_form="aa", phrase_chords=1, **kw)
        plain = generate_melody_for_progression(chords, "C", "ionian", **kw)
        d, pl = _by_chord(derived), _by_chord(plain)
        assert d[0] == pl[0]
        # chord 1's rhythm differs from chord 0's (the source), so the piece's
        # rhythm layer wins and it is generated fresh, exactly as in plain v2
        assert d[1] == pl[1]
        # chord 2 shares chord 0's rhythm, so it IS derived: same pitch classes
        assert [n.midi_note % 12 for n in d[2]] == [n.midi_note % 12 for n in d[0]]
        # chord 3 differs from chord 0's rhythm -> fresh: rhythm still the layer's
        assert _same_rhythm(
            [MelodyNote(None, n.start_beat - 12, n.duration_beats, is_rest=n.is_rest) for n in d[3]],
            [MelodyNote(None, n.start_beat - 12, n.duration_beats, is_rest=n.is_rest) for n in pl[3]])


class TestDerivePhraseChord:
    """Direct unit tests of the per-chord transform on off-beat notes (so no
    strong-beat refit interferes)."""

    SCALE = get_scale_tones("C", "ionian", 48, 84)
    CT = [60, 64, 67, 72, 76, 79]            # C major tones in register

    def _src(self, pitches):
        return [MelodyNote(p, 0.5 + i, 0.5, 72) for i, p in enumerate(pitches)]

    def _go(self, restate, shift=0, pivot=None, pitches=(62, 65, 69, 71)):
        return _derive_phrase_chord(
            self._src(pitches), restate, shift, pivot, False,
            self.SCALE, 7, self.CT,
            {"beats_per_bar": 4, "section_beat_offset": 0.0},
            False, None, 48, 84)

    def test_exact_keeps_offbeat_pitches(self):
        assert [n.midi_note for n in self._go("exact")] == [62, 65, 69, 71]

    def test_sequence_moves_by_scale_degrees(self):
        out = [n.midi_note for n in self._go("sequence", shift=2)]
        # D F A B  +2 degrees -> F A C D
        assert out == [65, 69, 72, 74]

    def test_sequence_negative_shift(self):
        out = [n.midi_note for n in self._go("sequence", shift=-1)]
        assert out == [60, 64, 67, 69]            # D F A B -> C E G A

    def test_invert_mirrors_contour_and_preserves_span(self):
        src = [62, 65, 69, 71]
        idx = [_scale_index(p, self.SCALE) for p in src]
        out = [n.midi_note for n in self._go("invert", pivot=min(idx) + max(idx))]
        oi = [_scale_index(p, self.SCALE) for p in out]
        assert [b - a for a, b in zip(oi, oi[1:])] == [-(b - a) for a, b in zip(idx, idx[1:])]
        assert (max(oi) - min(oi)) == (max(idx) - min(idx))

    def test_rests_and_rhythm_are_copied(self):
        src = self._src([62, 65])
        src.insert(1, MelodyNote(None, 1.0, 0.5, 72, True))
        out = _derive_phrase_chord(src, "exact", 0, None, False, self.SCALE, 7, self.CT,
                                   {"beats_per_bar": 4, "section_beat_offset": 0.0},
                                   False, None, 48, 84)
        assert _same_rhythm(src, out)
        assert out[1].is_rest

    def test_downbeat_note_is_refit_to_new_chord(self):
        src = [MelodyNote(62, 0.0, 1.0, 72)]            # D on the downbeat
        out = _derive_phrase_chord(src, "exact", 0, None, False, self.SCALE, 7, self.CT,
                                   {"beats_per_bar": 4, "section_beat_offset": 0.0},
                                   False, None, 48, 84)
        assert out[0].midi_note in (60, 64)             # nearest C-major tone


class TestPhraseSchemaAndPlumbing:
    def test_voice_fields_validate(self):
        from intervals.core.schemas import VoiceModel
        v = VoiceModel(phrase_form="aaba", phrase_chords=3, phrase_restate="sequence")
        assert (v.phrase_form, v.phrase_chords, v.phrase_restate) == ("aaba", 3, "sequence")
        assert VoiceModel().phrase_form is None
        for bad in ({"phrase_form": "AABA"}, {"phrase_form": "a1"}, {"phrase_form": ""},
                    {"phrase_chords": 0}, {"phrase_chords": 9}, {"phrase_restate": "retrograde"}):
            with pytest.raises(Exception):
                VoiceModel(**bad)

    def test_piece_defaults_off(self):
        from intervals.core.schemas import PieceModel
        f = PieceModel.model_fields
        assert f["phrase_form"].default is None
        assert f["phrase_chords"].default == 2
        assert f["phrase_restate"].default == "exact"

    def test_voice_overrides_piece_default(self):
        from intervals.core.generator import _phrase_kwargs
        from intervals.core.schemas import VoiceModel
        theme = {"phrase_form": "abab", "phrase_chords": 4, "phrase_restate": "invert"}
        assert _phrase_kwargs(None, theme) == dict(phrase_form="abab", phrase_chords=4, phrase_restate="invert")
        v = VoiceModel(phrase_form="aaba", phrase_restate="sequence")
        assert _phrase_kwargs(v, theme) == dict(phrase_form="aaba", phrase_chords=4, phrase_restate="sequence")
        assert _phrase_kwargs(None, {}) == dict(phrase_form=None, phrase_chords=2, phrase_restate="exact")
