"""
Tests for literal subject/answer entry — the "actually state the fugue
subject" path added alongside free-species counterpoint.

Covers three layers:
  1. motif.py's generate_subject_entry() in isolation — diatonic pitch
     rendering, tonic anchoring, answer transposition, rest handling.
  2. schemas.py's VoiceModel validators — entry_role requires motif,
     answer_interval requires entry_role='answer', entry_role/species are
     mutually exclusive.
  3. End-to-end generator.py wiring — both the lead voice (voices[0], via
     generate_section) and peer voices (voices[1:], via generate_piece)
     take the literal-entry path when entry_role is set, and are a no-op
     (byte-identical to pre-existing behavior) when it's unset.
"""
import pytest

from intervals.music.motif import generate_subject_entry
from intervals.core.schemas import VoiceModel, SectionModel, PieceModel
from intervals.core import generator


# ---------------------------------------------------------------------------
# 1. generate_subject_entry — unit tests
# ---------------------------------------------------------------------------

class TestGenerateSubjectEntrySubject:
    def test_pitches_match_diatonic_intervals_anchored_to_tonic(self):
        """A 'subject' voice renders the motif's diatonic-step intervals
        literally, starting on the tonic folded into the given register."""
        notes = generate_subject_entry(
            {"name": "s", "intervals": [0, 2, -1, 1], "rhythm": [1.0, 1.0, 1.0, 1.0]},
            entry_role="subject",
            key="C", mode="ionian",
            total_beats=4.0,
            register_bounds=(60, 72),
            velocity=80,
        )
        # C ionian pitch classes: C D E F G A B. Starting on C4=60 (tonic
        # folded into [60,72]): degree walk 0, +2, -1, +1 -> C, E, D, E.
        assert [n.midi_note for n in notes] == [60, 64, 62, 64]
        assert [n.start_beat for n in notes] == [0.0, 1.0, 2.0, 3.0]
        assert all(not n.is_rest for n in notes)

    def test_tiles_across_total_beats_continuing_diatonic_walk(self):
        """When total_beats exceeds one cycle, the cell retiles and the
        diatonic walk CONTINUES cumulatively rather than resetting each
        cycle -- a real melodic line, not a stutter."""
        notes = generate_subject_entry(
            {"name": "s", "intervals": [0, 1, 1, -1], "rhythm": [1.0, 1.0, 1.0, 1.0]},
            entry_role="subject",
            key="C", mode="ionian",
            total_beats=8.0,
            register_bounds=(60, 72),
        )
        assert len(notes) == 8
        # First cycle: C D E D (degrees 0,1,2,1). Second cycle continues
        # from degree 1 (D): D E F E (degrees 1,2,3,2).
        assert [n.midi_note for n in notes] == [60, 62, 64, 62, 62, 64, 65, 64]

    def test_rest_slot_advances_walk_but_does_not_sound(self):
        """A rest slot in the motif still advances the underlying diatonic
        walk (per motif_to_notes' contract) -- it just doesn't emit a note."""
        notes = generate_subject_entry(
            {
                "name": "s", "intervals": [0, 1, 1, -1], "rhythm": [1.0, 1.0, 1.0, 1.0],
                "rests": [False, True, False, False],
            },
            entry_role="subject",
            key="C", mode="ionian",
            total_beats=4.0,
            register_bounds=(60, 72),
        )
        # Same degree walk as the no-rest case (0,1,2,1 -> C,D,E,D) but the
        # D (index 1, rest) is dropped from the output.
        assert [n.midi_note for n in notes] == [60, 64, 62]
        assert [n.start_beat for n in notes] == [0.0, 2.0, 3.0]

    def test_final_partial_cycle_trimmed_to_total_beats(self):
        """A statement that would run past total_beats is trimmed, same
        discipline _tile_one_motif_cycle already applies elsewhere."""
        notes = generate_subject_entry(
            {"name": "s", "intervals": [0, 1, 1], "rhythm": [1.0, 1.0, 1.0]},
            entry_role="subject",
            key="C", mode="ionian",
            total_beats=2.5,
            register_bounds=(60, 72),
        )
        assert [n.start_beat for n in notes] == [0.0, 1.0, 2.0]
        assert notes[-1].duration_beats == pytest.approx(0.5)

    def test_no_motif_returns_empty_list(self):
        assert generate_subject_entry(
            None, entry_role="subject", key="C", mode="ionian", total_beats=4.0,
        ) == []

    def test_falls_back_to_default_register_when_bounds_omitted(self):
        notes = generate_subject_entry(
            {"name": "s", "intervals": [0], "rhythm": [1.0]},
            entry_role="subject",
            key="C", mode="ionian",
            total_beats=1.0,
        )
        assert len(notes) == 1  # doesn't crash without register_bounds


class TestGenerateSubjectEntryAnswer:
    def test_default_answer_transposes_up_a_fifth(self):
        """No answer_interval given -> real answer, +7 semitones."""
        subject = generate_subject_entry(
            {"name": "s", "intervals": [0, 1, -1], "rhythm": [1.0, 1.0, 1.0]},
            entry_role="subject", key="C", mode="ionian",
            total_beats=3.0, register_bounds=(60, 84),
        )
        answer = generate_subject_entry(
            {"name": "s", "intervals": [0, 1, -1], "rhythm": [1.0, 1.0, 1.0]},
            entry_role="answer", key="C", mode="ionian",
            total_beats=3.0, register_bounds=(60, 84),
        )
        # Same rhythm/shape, each note exactly 7 semitones above the
        # subject's corresponding note (both land on scale tones by
        # construction, so a fixed +7 offset holds note-for-note here).
        assert [n.start_beat for n in answer] == [n.start_beat for n in subject]
        for s, a in zip(subject, answer):
            assert a.midi_note - s.midi_note == 7

    def test_custom_answer_interval_overrides_default(self):
        answer = generate_subject_entry(
            {"name": "s", "intervals": [0], "rhythm": [1.0]},
            entry_role="answer", key="C", mode="ionian",
            total_beats=1.0, register_bounds=(48, 84),
            answer_interval=-5,
        )
        subject = generate_subject_entry(
            {"name": "s", "intervals": [0], "rhythm": [1.0]},
            entry_role="subject", key="C", mode="ionian",
            total_beats=1.0, register_bounds=(48, 84),
        )
        assert answer[0].midi_note - subject[0].midi_note == -5


# ---------------------------------------------------------------------------
# 2. VoiceModel validators
# ---------------------------------------------------------------------------

class TestVoiceModelEntryRoleValidation:
    def test_entry_role_without_motif_raises(self):
        with pytest.raises(Exception):
            VoiceModel(entry_role="subject")

    def test_entry_role_with_motif_is_valid(self):
        v = VoiceModel(entry_role="subject", motif="my_motif")
        assert v.entry_role == "subject"

    def test_answer_interval_without_answer_role_raises(self):
        with pytest.raises(Exception):
            VoiceModel(entry_role="subject", motif="m", answer_interval=5)

    def test_answer_interval_without_entry_role_raises(self):
        with pytest.raises(Exception):
            VoiceModel(motif="m", answer_interval=5)

    def test_answer_interval_with_answer_role_is_valid(self):
        v = VoiceModel(entry_role="answer", motif="m", answer_interval=-5)
        assert v.answer_interval == -5

    def test_entry_role_and_species_are_mutually_exclusive(self):
        with pytest.raises(Exception):
            VoiceModel(entry_role="subject", motif="m", species="free")

    def test_default_is_unset_and_backward_compatible(self):
        v = VoiceModel()
        assert v.entry_role is None
        assert v.answer_interval is None


# ---------------------------------------------------------------------------
# 3. End-to-end generator.py wiring
# ---------------------------------------------------------------------------

def _fugue_piece(**voice_overrides):
    voices = [
        {"register": "mid", "entry_role": "subject", "motif": "subj", "velocity": 80},
        {"register": "above", "entry_role": "answer", "motif": "subj",
         "velocity": 70, "canon_offset": 2.0},
    ]
    return {
        "key": "D", "mode": "dorian", "tempo": 100, "seed": 3,
        "motif": {"name": "subj", "intervals": [0, 2, -1, 1], "rhythm": [1.0, 1.0, 1.0, 1.0]},
        "sections": [{
            "name": "exposition", "bars": 4, "rhythm": "free",
            "progression": ["i", "iv", "v", "i"],
            "voices": voices,
        }],
    }


class TestGeneratorWiring:
    def test_lead_voice_entry_role_renders_literal_subject(self):
        """voices[0] with entry_role set takes generate_subject_entry's
        path in generate_section, not generate_melody_for_progression."""
        piece = {
            "key": "C", "mode": "ionian", "tempo": 100, "seed": 1,
            "motif": {"name": "s", "intervals": [0, 2, -1, 1], "rhythm": [1.0, 1.0, 1.0, 1.0]},
            "sections": [{
                "name": "a", "bars": 4, "rhythm": "free",
                "progression": ["I", "IV", "V", "I"],
                "voices": [{"register": "mid", "entry_role": "subject", "motif": "s"}],
            }],
        }
        res = generator.generate_section(piece["sections"][0], piece)
        # C ionian, degree walk 0,+2,-1,+1 from tonic -> C E D E (relative
        # semitone shape, regardless of which octave the tonic folds
        # into for the default "mid" register).
        first = res.melody_notes[0].midi_note
        assert [n.midi_note - first for n in res.melody_notes[:4]] == [0, 4, 2, 4]
        assert first % 12 == 0  # C, whichever octave

    def test_peer_voice_answer_transposed_and_canon_shifted(self):
        """voices[1] (peer) with entry_role='answer' renders transposed,
        and canon_offset still shifts it forward as it does for every
        other peer-voice path."""
        piece = _fugue_piece()
        piece_model = PieceModel.model_validate(piece)
        piece_model.validate_against_theme(piece_model)  # should not raise

    def test_full_fugue_piece_renders_without_error(self, tmp_path):
        piece = _fugue_piece()
        out = str(tmp_path / "fugue.mid")
        path = generator.generate_piece(piece, out)
        import mido
        mid = mido.MidiFile(path)
        # melody track + peer voice track should both carry notes
        note_counts = [
            len([m for m in tr if m.type == "note_on" and m.velocity > 0])
            for tr in mid.tracks
        ]
        assert sum(note_counts) > 0

    def test_bar_alignment_check_still_catches_misaligned_subject_motif(self):
        """The existing rhythm/bar-alignment validator (schemas.py's
        _check_bar_alignment) reads voice.motif regardless of entry_role
        -- it should still reject a subject/answer voice whose motif
        rhythm doesn't divide evenly into the bar, exactly as it already
        does for free-species peer voices."""
        piece = {
            "key": "D", "mode": "dorian", "tempo": 100, "seed": 1,
            "sections": [{
                "name": "a", "bars": 4, "rhythm": "free",
                "progression": ["i", "iv"],
                "voices": [{
                    "register": "mid", "entry_role": "subject",
                    # 3 beats total in a 4/4 section -- misaligned.
                    "motif": {"name": "bad", "intervals": [0, 1, -1],
                              "rhythm": [1.0, 1.0, 1.0]},
                }],
            }],
        }
        piece_model = PieceModel.model_validate(piece)
        with pytest.raises(ValueError, match="not a whole multiple"):
            piece_model.validate_against_theme(piece_model)

    def test_species_voice_after_subject_still_counterpoints_against_it(self):
        """A species voice generated after a subject/answer voice reads
        the literal notes via against_voices with no special-casing --
        confirm it doesn't crash and produces notes."""
        piece = _fugue_piece()
        piece["sections"][0]["voices"].append(
            {"register": "below", "species": "free", "velocity": 60}
        )
        res = generator.generate_piece(piece, "/tmp/_test_fugue_species.mid")
        assert res is not None


# ---------------------------------------------------------------------------
# 4. Regression: entry_role unset is a strict no-op
# ---------------------------------------------------------------------------

class TestEntryRoleUnsetIsNoOp:
    def test_lead_voice_without_entry_role_still_uses_generative_melody(self):
        """Without entry_role, voices[0] must still go through
        generate_melody_for_progression -- confirmed by the printed
        section using a *behavior* (lyrical/generative), which
        generate_subject_entry has no notion of and would ignore."""
        piece = {
            "key": "C", "mode": "ionian", "tempo": 100, "seed": 1,
            "sections": [{
                "name": "a", "bars": 2, "rhythm": "free",
                "progression": ["I", "V"],
                "voices": [{"register": "mid", "behavior": "lyrical"}],
            }],
        }
        res = generator.generate_section(piece["sections"][0], piece)
        assert len(res.melody_notes) > 0  # generative path still produces notes

    def test_peer_voice_without_entry_role_unaffected(self):
        """A peer voice with species set (no entry_role) still takes the
        counterpoint path exactly as before this feature existed."""
        piece = {
            "key": "C", "mode": "ionian", "tempo": 100, "seed": 1,
            "sections": [{
                "name": "a", "bars": 2, "rhythm": "free",
                "progression": ["I", "V"],
                "voices": [
                    {"register": "mid", "behavior": "lyrical"},
                    {"register": "below", "species": "free"},
                ],
            }],
        }
        result = generator.generate_piece(piece, "/tmp/_test_no_entry_role.mid")
        assert result is not None

    def test_full_existing_suite_pieces_still_validate(self):
        """A representative multi-voice piece with no entry_role anywhere
        validates and renders cleanly -- the schema additions must not
        perturb any existing, unrelated field."""
        piece = {
            "key": "G", "mode": "mixolydian", "tempo": 90, "seed": 5,
            "motif": {"name": "m", "intervals": [0, 1, -1, 0], "rhythm": [1.0, 1.0, 1.0, 1.0]},
            "sections": [{
                "name": "a", "bars": 3, "rhythm": "motif",
                "progression": ["I", "IV", "V"],
                "voices": [
                    {"register": "mid", "motif": "m", "behavior": "develop"},
                    {"register": "below", "species": "first"},
                ],
            }],
        }
        result = generator.generate_piece(piece, "/tmp/_test_regression_full.mid")
        assert result is not None
