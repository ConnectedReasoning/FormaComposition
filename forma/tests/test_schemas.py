"""
Tests for intervals.core.schemas — the Pydantic v2 validation gatekeeper.

Every model gets at least one valid-input test (parses cleanly, fields land
where expected) and at least one invalid-input test (raises ValidationError
for the right reason: bad enum value, out-of-range field, missing required
field, or a custom cross-field check). Some models get more than one
invalid case where the model has several genuinely distinct failure modes
worth locking in separately (e.g. SectionModel's rhythm/pattern
cross-dependency vs. its plain missing-required-field case).

Custom validators (`@field_validator`, `@model_validator`) that raise
`ValueError` are surfaced by Pydantic as `ValidationError` at the
`Model(...)` / `Model.model_validate(...)` call site — confirmed directly
against this codebase's Pydantic version before relying on it here, rather
than assumed from general Pydantic v1/v2 knowledge.
"""
import warnings

import pytest
from pydantic import ValidationError

from intervals.core.schemas import (
    CounterpointModel,
    DrumModel,
    HarmonyRhythmModel,
    MotifModel,
    NoteLengthRangeModel,
    MelodicArcModel,
    PieceModel,
    RhythmPatternModel,
    SectionModel,
    SongFormEntryModel,
    TempoRangeModel,
    VoiceModel,
)


# ---------------------------------------------------------------------------
# Shared minimal valid fixtures
# ---------------------------------------------------------------------------

def _minimal_section(**overrides) -> dict:
    """A minimal section dict that validates cleanly on its own (no theme
    needed) — the baseline every SectionModel test starts from."""
    base = {
        "progression": ["i", "iv", "v"],
        "rhythm": "free",
        "bars": 8,
    }
    base.update(overrides)
    return base


def _minimal_piece(**overrides) -> dict:
    """
    A minimal piece dict that validates cleanly through PieceModel —
    includes key/mode/tempo (absorbed from the retired ThemeModel) plus a
    bare sections list. Baseline for tests exercising theme-side fields
    (motif, motifs, key, mode) now that they live on PieceModel directly.
    """
    base = {
        "key": "C",
        "mode": "ionian",
        "tempo": {"min": 60, "max": 120},
        "sections": [_minimal_section()],
    }
    base.update(overrides)
    return base


# ===========================================================================
# RhythmPatternModel
# ===========================================================================

class TestRhythmPatternModel:
    def test_valid(self):
        m = RhythmPatternModel(
            onsets=[0.0, 1.0, 2.0],
            durations=[1.0, 1.0, 1.0],
            velocities=[0.5, 0.6, 0.7],
            length_beats=4.0,
        )
        assert m.onsets == [0.0, 1.0, 2.0]
        assert m.length_beats == 4.0

    def test_invalid_onsets_durations_length_mismatch(self):
        with pytest.raises(ValidationError, match="same length"):
            RhythmPatternModel(onsets=[0.0, 1.0], durations=[1.0])

    def test_invalid_velocities_out_of_range(self):
        """velocities are 0.0-1.0 scale multipliers, not raw MIDI (0-127) —
        a raw MIDI value here is the exact authoring mistake this guards."""
        with pytest.raises(ValidationError, match="0.0-1.0"):
            RhythmPatternModel(onsets=[0.0], durations=[1.0], velocities=[80.0])

    def test_invalid_unknown_field_rejected(self):
        """extra='forbid' — a typo'd or removed field must not silently vanish."""
        with pytest.raises(ValidationError):
            RhythmPatternModel(
                onsets=[0.0], durations=[1.0], bogus_field="nope",
            )


# ===========================================================================
# HarmonyRhythmModel
# ===========================================================================

class TestHarmonyRhythmModel:
    def test_valid(self):
        m = HarmonyRhythmModel(rhythm="pattern", density="medium", groove="straight", swing=0.5)
        assert m.rhythm == "pattern"
        assert m.swing == 0.5

    def test_invalid_bad_enum_rhythm(self):
        with pytest.raises(ValidationError):
            HarmonyRhythmModel(rhythm="bogus_source")

    def test_invalid_swing_out_of_range(self):
        with pytest.raises(ValidationError):
            HarmonyRhythmModel(swing=1.5)

    def test_invalid_note_duration_field_removed(self):
        """note_duration was deliberately removed (2026-07): it was
        schema-legal but consumed nowhere — extra='forbid' must reject it
        loudly instead of silently accepting a no-op field again."""
        with pytest.raises(ValidationError):
            HarmonyRhythmModel(note_duration=1.0)


# ===========================================================================
# NoteLengthRangeModel
# ===========================================================================

class TestNoteLengthRangeModel:
    def test_valid(self):
        m = NoteLengthRangeModel(min=0.25, max=1.0)
        assert m.as_tuple() == (0.25, 1.0)
        assert m.quantum == 0.25  # default

    def test_invalid_max_less_than_min(self):
        with pytest.raises(ValidationError, match="must be >= min"):
            NoteLengthRangeModel(min=1.0, max=0.5)

    def test_invalid_non_positive_min(self):
        with pytest.raises(ValidationError):
            NoteLengthRangeModel(min=0.0, max=1.0)


# ===========================================================================
# MelodicArcModel
# ===========================================================================

class TestMelodicArcModel:
    def test_valid_full(self):
        m = MelodicArcModel(apex_degree=5, apex_position=0.6, resolve_every_cycle=True)
        assert m.apex_degree == 5
        assert m.apex_position == 0.6
        assert m.resolve_every_cycle is True

    def test_defaults_when_only_apex_degree_given(self):
        m = MelodicArcModel(apex_degree=5)
        assert m.apex_position == 0.7  # matches generate_lyrical/generative's own default
        assert m.resolve_every_cycle is False

    def test_valid_with_no_apex_degree_cadence_only(self):
        # A melodic_arc block can enable cadence pull on its own, with no
        # climax target at all -- apex_degree stays None.
        m = MelodicArcModel(resolve_every_cycle=True)
        assert m.apex_degree is None
        assert m.resolve_every_cycle is True

    def test_apex_position_out_of_range_rejected(self):
        with pytest.raises(ValidationError):
            MelodicArcModel(apex_degree=5, apex_position=1.5)
        with pytest.raises(ValidationError):
            MelodicArcModel(apex_degree=5, apex_position=-0.1)

    def test_apex_position_boundary_values_accepted(self):
        assert MelodicArcModel(apex_degree=5, apex_position=0.0).apex_position == 0.0
        assert MelodicArcModel(apex_degree=5, apex_position=1.0).apex_position == 1.0

    def test_unknown_field_rejected(self):
        with pytest.raises(ValidationError):
            MelodicArcModel(apex_degree=5, strength=10)


# ===========================================================================
# CounterpointModel
# ===========================================================================

class TestCounterpointModel:
    def test_valid(self):
        m = CounterpointModel(species="first", register="above", velocity=70)
        assert m.species == "first"
        assert m.cp_register == "above"  # populated via alias

    def test_valid_free_species_default(self):
        m = CounterpointModel()
        assert m.species == "free"
        assert m.cp_register == "below"

    def test_invalid_unimplemented_species(self):
        """'second'/'third'/'fourth'/'fifth' are schema-valid *names* in the
        Literal but not implemented in counterpoint.py — must be blocked at
        validation time, not left to crash at render time."""
        with pytest.raises(ValidationError, match="not implemented"):
            CounterpointModel(species="third")

    def test_invalid_velocity_out_of_range(self):
        with pytest.raises(ValidationError):
            CounterpointModel(velocity=200)

    def test_invalid_bad_dissonance_enum(self):
        with pytest.raises(ValidationError):
            CounterpointModel(dissonance="bogus")


# ===========================================================================
# VoiceModel
# ===========================================================================

class TestVoiceModel:
    def test_valid(self):
        m = VoiceModel(register="soprano", behavior="lyrical", velocity=90)
        assert m.bounds() == (63, 81)  # soprano, 18 semitones, centered C5
        assert m.is_relative() is False

    def test_valid_relative_register(self):
        m = VoiceModel(register="above")
        assert m.bounds() is None
        assert m.is_relative() is True

    def test_invalid_unimplemented_species(self):
        with pytest.raises(ValidationError, match="not implemented"):
            VoiceModel(species="fifth")

    def test_invalid_bad_register_enum(self):
        with pytest.raises(ValidationError):
            VoiceModel(register="falsetto")

    def test_invalid_velocity_out_of_range(self):
        with pytest.raises(ValidationError):
            VoiceModel(velocity=0)


# ===========================================================================
# DrumModel
# ===========================================================================

class TestDrumModel:
    def test_valid(self):
        m = DrumModel(pattern="backbeat", density="sparse")
        density, groove, swing = m.resolve(
            section_density="full", section_groove="straight", section_swing=0.2,
        )
        assert density == "sparse"        # own value wins
        assert groove == "straight"        # inherits from section (None -> fallback)
        assert swing == 0.2                # inherits from section

    def test_invalid_bad_pattern_enum(self):
        with pytest.raises(ValidationError):
            DrumModel(pattern="bogus_pattern")

    def test_invalid_unknown_field(self):
        with pytest.raises(ValidationError):
            DrumModel(pattern="four_on_floor", tempo_sync=True)


# ===========================================================================
# MotifModel
# ===========================================================================

class TestMotifModel:
    def test_valid(self):
        m = MotifModel(
            name="plea",
            intervals=[0, 2, 4],
            rhythm=[1.0, 1.0, 2.0],
            rests=[False, False, False],
            velocities=[0.6, 0.7, 0.8],
        )
        assert m.name == "plea"
        assert len(m.intervals) == 3

    def test_invalid_empty_intervals(self):
        with pytest.raises(ValidationError):
            MotifModel(intervals=[])

    def test_invalid_missing_required_intervals(self):
        with pytest.raises(ValidationError):
            MotifModel(name="no_intervals")

    def test_invalid_velocities_length_mismatch(self):
        with pytest.raises(ValidationError, match="must match rhythm length"):
            MotifModel(intervals=[0, 2], rhythm=[1.0, 1.0], velocities=[0.5])

    def test_invalid_rests_length_mismatch(self):
        with pytest.raises(ValidationError, match="must match rhythm length"):
            MotifModel(intervals=[0, 2], rhythm=[1.0, 1.0], rests=[True])

    def test_invalid_velocities_out_of_range(self):
        with pytest.raises(ValidationError, match="0.0-1.0"):
            MotifModel(intervals=[0, 2], rhythm=[1.0, 1.0], velocities=[0.5, 90.0])

    def test_melodic_scale_defaults_to_none(self):
        """Absent melodic_scale means 'use the piece's own mode' -- every
        motif written before this field existed behaves identically."""
        m = MotifModel(intervals=[0, 2])
        assert m.melodic_scale is None

    def test_melodic_scale_accepts_standard_mode(self):
        m = MotifModel(intervals=[0, 2], melodic_scale="Dorian")
        assert m.melodic_scale == "dorian"  # normalized lowercase, like piece.mode

    def test_melodic_scale_accepts_pentatonic_and_blues(self):
        """The whole point of this field: scales that are deliberately
        INVALID as a piece's harmonic mode (see PieceModel._validate_mode)
        are valid here, since this never touches Roman-numeral resolution."""
        for scale in ("pentatonic_major", "pentatonic_minor", "blues"):
            m = MotifModel(intervals=[0, 2], melodic_scale=scale)
            assert m.melodic_scale == scale

    def test_melodic_scale_rejects_unknown_value(self):
        with pytest.raises(ValidationError, match="not valid"):
            MotifModel(intervals=[0, 2], melodic_scale="not_a_real_scale")


# ===========================================================================
# TempoRangeModel
# ===========================================================================

class TestTempoRangeModel:
    def test_valid(self):
        m = TempoRangeModel(min=60, max=120)
        assert m.min == 60 and m.max == 120

    def test_invalid_min_greater_than_max(self):
        with pytest.raises(ValidationError, match="must be"):
            TempoRangeModel(min=120, max=60)

    def test_invalid_out_of_range(self):
        with pytest.raises(ValidationError):
            TempoRangeModel(min=10, max=60)  # below the ge=20 floor


# ===========================================================================
# SongFormEntryModel
# ===========================================================================

class TestSongFormEntryModel:
    def test_valid(self):
        m = SongFormEntryModel(section="chorus", exact_repeat=True)
        assert m.section == "chorus"
        assert m.exact_repeat is True

    def test_invalid_missing_required_section(self):
        with pytest.raises(ValidationError):
            SongFormEntryModel(exact_repeat=True)

    def test_invalid_unknown_field(self):
        with pytest.raises(ValidationError):
            SongFormEntryModel(section="chorus", repeat_count=2)


# ===========================================================================
# PieceModel — theme-side fields (absorbed from the retired ThemeModel:
# key, mode, tempo, motif, motifs, primary_motif)
# ===========================================================================

class TestPieceModelThemeFields:
    def test_valid_with_motif(self):
        piece = PieceModel.model_validate(_minimal_piece(
            motif={"intervals": [0, 2, 4], "rhythm": [1.0, 1.0, 2.0]},
        ))
        assert piece.key == "C"
        assert piece.mode == "ionian"
        assert piece.primary_motif is not None
        assert piece.primary_motif.rhythm == [1.0, 1.0, 2.0]

    def test_primary_motif_prefers_motifs_array_over_motif(self):
        piece = PieceModel.model_validate(_minimal_piece(
            motif={"intervals": [0, 2, 4], "rhythm": [1.0, 1.0, 2.0]},
            motifs=[{"intervals": [7, 7], "rhythm": [1.0, 1.0]}],
        ))
        assert piece.primary_motif.intervals == [7, 7]

    def test_invalid_bad_key(self):
        with pytest.raises(ValidationError, match="not a valid note name"):
            PieceModel.model_validate(_minimal_piece(key="H"))

    def test_invalid_bad_mode(self):
        with pytest.raises(ValidationError, match="not valid"):
            PieceModel.model_validate(_minimal_piece(mode="atonal"))

    def test_invalid_empty_motifs_list(self):
        with pytest.raises(ValidationError, match="non-empty list"):
            PieceModel.model_validate(_minimal_piece(motifs=[]))

    def test_mode_is_case_insensitive_and_normalized(self):
        piece = PieceModel.model_validate(_minimal_piece(mode="IONIAN"))
        assert piece.mode == "ionian"


# ===========================================================================
# SectionModel
# ===========================================================================

class TestSectionModel:
    def test_valid_minimal(self):
        s = SectionModel.model_validate(_minimal_section())
        assert s.rhythm == "free"
        assert s.bars == 8.0
        assert s.resolved_progression() == ["i", "iv", "v"]

    def test_valid_with_voices_and_counterpoint(self):
        s = SectionModel.model_validate(_minimal_section(
            voices=[
                {"register": "soprano", "behavior": "lyrical"},
                {"register": "alto", "species": "first"},
            ],
            counterpoint=None,
        ))
        assert len(s.voices) == 2
        assert s.lead_voice().v_register == "soprano"

    def test_invalid_missing_required_progression(self):
        with pytest.raises(ValidationError):
            SectionModel.model_validate({"rhythm": "free", "bars": 8})

    def test_invalid_missing_required_rhythm(self):
        with pytest.raises(ValidationError):
            SectionModel.model_validate({"progression": ["i", "v"], "bars": 8})

    def test_invalid_bad_density_enum(self):
        with pytest.raises(ValidationError):
            SectionModel.model_validate(_minimal_section(density="bogus"))

    def test_invalid_beats_per_bar_out_of_range(self):
        with pytest.raises(ValidationError):
            SectionModel.model_validate(_minimal_section(beats_per_bar=32))

    def test_invalid_progression_entry_with_comma(self):
        """Known mobile-transcription artifact: several chords typed into
        one comma-separated array element instead of separate elements."""
        with pytest.raises(ValidationError, match="comma"):
            SectionModel.model_validate(_minimal_section(progression=["ii, v, i"]))

    def test_invalid_rhythm_pattern_requires_block(self):
        with pytest.raises(ValidationError, match="requires a rhythm_pattern"):
            SectionModel.model_validate(_minimal_section(rhythm="pattern"))

    def test_invalid_chord_bars_length_mismatch(self):
        with pytest.raises(ValidationError, match="chord_bars has"):
            SectionModel.model_validate(_minimal_section(
                progression=["i", "iv", "v"], chord_bars=[2.0, 2.0],
            ))

    def test_invalid_chord_bars_not_whole_multiple_of_bars(self):
        with pytest.raises(ValidationError, match="not a whole multiple"):
            SectionModel.model_validate(_minimal_section(
                progression=["i", "iv"], chord_bars=[1.0, 1.0], bars=5,
            ))

    def test_invalid_too_many_counterpoint_voices(self):
        cp = [{"species": "free"}] * 4
        with pytest.raises(ValidationError, match="at most 3 voices"):
            SectionModel.model_validate(_minimal_section(counterpoint=cp))

    def test_invalid_too_many_total_voices(self):
        voices = [{"register": "soprano"}] * 5
        with pytest.raises(ValidationError, match="at most 4 total"):
            SectionModel.model_validate(_minimal_section(voices=voices))

    def test_invalid_harmony_rhythm_pattern_requires_block(self):
        with pytest.raises(ValidationError, match="harmony_pattern block"):
            SectionModel.model_validate(_minimal_section(
                harmony_rhythm={"rhythm": "pattern"},
            ))

    def test_invalid_inherited_pattern_requires_harmony_pattern_block(self):
        """Known-issues #7: section.rhythm='pattern' with no harmony_rhythm
        override at all inherits 'pattern' for harmony too — previously this
        rendered zero harmony events with no warning. Now a schema error,
        same as the explicit case just above."""
        with pytest.raises(ValidationError, match="inherited by harmony"):
            SectionModel.model_validate(_minimal_section(
                rhythm="pattern",
                rhythm_pattern={"onsets": [0.0], "durations": [1.0]},
            ))

    def test_invalid_inherited_pattern_with_empty_harmony_rhythm_block(self):
        """Same gap, but with an explicit harmony_rhythm block present that
        doesn't set rhythm (e.g. only overrides density/groove) — still
        inherits 'pattern' from the section, still needs harmony_pattern."""
        with pytest.raises(ValidationError, match="inherited by harmony"):
            SectionModel.model_validate(_minimal_section(
                rhythm="pattern",
                rhythm_pattern={"onsets": [0.0], "durations": [1.0]},
                harmony_rhythm={"density": "sparse"},
            ))

    def test_valid_inherited_pattern_with_harmony_pattern_block(self):
        """The inherited case is fine once a harmony_pattern block is
        supplied — should not raise."""
        SectionModel.model_validate(_minimal_section(
            rhythm="pattern",
            rhythm_pattern={"onsets": [0.0], "durations": [1.0]},
            harmony_pattern={"onsets": [0.0], "durations": [1.0]},
        ))

    def test_valid_inherited_pattern_with_explicit_harmony_rhythm_override(self):
        """Opting harmony out of the inherited 'pattern' source with an
        explicit override (e.g. 'sustain') should not raise, even with no
        harmony_pattern block — the pattern source never actually applies
        to harmony in this case."""
        SectionModel.model_validate(_minimal_section(
            rhythm="pattern",
            rhythm_pattern={"onsets": [0.0], "durations": [1.0]},
            harmony_rhythm={"rhythm": "sustain"},
        ))

    def test_invalid_transform_imitation_strict_with_motif_rhythm(self):
        with pytest.raises(ValidationError, match="not implemented"):
            SectionModel.model_validate(_minimal_section(
                harmony_rhythm={"rhythm": "motif", "transform_imitation": "strict"},
            ))

    def test_unknown_top_level_key_warns_not_raises(self):
        """extra='allow' + _warn_unknown_keys: typo'd/legacy keys warn,
        they don't block generation."""
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            s = SectionModel.model_validate(_minimal_section(totally_made_up_key=1))
        assert s.model_extra.get("totally_made_up_key") == 1
        assert any("unknown field" in str(w.message) for w in caught)

    def test_lead_canon_offset_warns_when_set_on_voices0(self):
        """Known-issues #3: canon_offset on voices[0] (the lead) is dead —
        generator.py's peer-voice loop only reads voices[1:]."""
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            SectionModel.model_validate(_minimal_section(voices=[
                {"register": "soprano", "canon_offset": 2.0},
            ]))
        assert any("canon_offset" in str(w.message) and "never reads" in str(w.message)
                    for w in caught)

    def test_lead_canon_offset_warns_when_set_on_melody_dict_form(self):
        """Same dead field, reached via section.melody given as a VoiceModel
        dict instead of voices[] — lead_voice() resolves either, and
        generator.py never touches section.melody's VoiceModel at all."""
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            SectionModel.model_validate(_minimal_section(
                melody={"behavior": "lyrical", "canon_offset": 1.5},
            ))
        assert any("canon_offset" in str(w.message) and "never reads" in str(w.message)
                    for w in caught)

    def test_lead_canon_offset_silent_when_zero(self):
        """Default canon_offset=0.0 shouldn't warn — nothing is actually
        being ignored when there's no offset to apply in the first place."""
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            SectionModel.model_validate(_minimal_section(voices=[
                {"register": "soprano"},
            ]))
        assert not any("never reads" in str(w.message) for w in caught)

    def test_peer_voice_canon_offset_does_not_warn(self):
        """canon_offset on voices[1:] (a real peer, not the lead) IS
        honored by generator.py — must not trigger this warning."""
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            SectionModel.model_validate(_minimal_section(voices=[
                {"register": "soprano"},
                {"register": "alto", "canon_offset": 2.0},
            ]))
        assert not any("never reads" in str(w.message) for w in caught)


# ===========================================================================
# SectionModel.validate_against_theme (cross-model)
# ===========================================================================

class TestSectionValidateAgainstTheme:
    def test_valid_motif_rhythm_from_theme(self):
        piece = PieceModel.model_validate(_minimal_piece(
            motif={"intervals": [0, 2, 4], "rhythm": [1.0, 1.0, 2.0]},
        ))
        section = SectionModel.model_validate(_minimal_section(rhythm="motif"))
        section.validate_against_theme(piece)  # should not raise

    def test_invalid_motif_rhythm_missing_everywhere(self):
        """rhythm='motif' but neither the piece's primary motif nor the
        lead voice's own override supplies a rhythm cell."""
        piece = PieceModel.model_validate(_minimal_piece(
            motif={"intervals": [0, 2, 4]},  # no rhythm field
        ))
        section = SectionModel.model_validate(_minimal_section(rhythm="motif"))
        with pytest.raises(ValueError, match="rhythm='motif'"):
            section.validate_against_theme(piece)

    def test_invalid_motif_rhythm_not_bar_aligned(self):
        """A motif rhythm whose total isn't a whole multiple of
        beats_per_bar must be rejected — it would drift out of phase with
        the barline on every repeat."""
        piece = PieceModel.model_validate(_minimal_piece(
            motif={"intervals": [0, 2, 4], "rhythm": [1.0, 1.0, 1.0]},  # 3 beats, bpb=4
        ))
        section = SectionModel.model_validate(_minimal_section(
            rhythm="motif", beats_per_bar=4,
        ))
        with pytest.raises(ValueError, match="not a whole multiple"):
            section.validate_against_theme(piece)


# ===========================================================================
# PieceModel
# ===========================================================================

class TestPieceModel:
    def test_valid_narrative(self):
        piece = PieceModel.model_validate({
            "key": "C", "mode": "ionian",
            "sections": [_minimal_section()],
        })
        assert piece.form_type == "narrative"
        assert len(piece.iter_sections()) == 1
        assert piece.seed == 42  # default

    def test_valid_song_form(self):
        piece = PieceModel.model_validate({
            "key": "C", "mode": "ionian",
            "form_type": "song",
            "form": ["verse", {"section": "chorus", "exact_repeat": False},
                     {"section": "chorus", "exact_repeat": True}],
            "sections": {
                "verse":  _minimal_section(),
                "chorus": _minimal_section(progression=["v", "i"]),
            },
        })
        assert piece.form_type == "song"
        assert len(piece.iter_sections()) == 3
        assert piece.iter_sections()[1].progression == ["v", "i"]

    def test_valid_wrapped_piece_key(self):
        """{"piece": {...}} wrapper form must unwrap the same as flat dicts."""
        piece = PieceModel.model_validate({
            "piece": {"key": "C", "mode": "ionian", "sections": [_minimal_section()]},
        })
        assert len(piece.iter_sections()) == 1

    def test_invalid_narrative_missing_sections(self):
        with pytest.raises(ValidationError, match="non-empty 'sections' list"):
            PieceModel.model_validate({"key": "C", "mode": "ionian", "sections": []})

    def test_invalid_song_missing_form(self):
        with pytest.raises(ValidationError, match="requires a 'form' array"):
            PieceModel.model_validate({
                "key": "C", "mode": "ionian",
                "form_type": "song",
                "sections": {"verse": _minimal_section()},
            })

    def test_invalid_song_missing_sections_dict(self):
        with pytest.raises(ValidationError, match="requires a 'sections' dict"):
            PieceModel.model_validate({
                "key": "C", "mode": "ionian",
                "form_type": "song",
                "form": ["verse"],
            })

    def test_invalid_song_form_references_undefined_section(self):
        with pytest.raises(ValidationError, match="undefined section"):
            PieceModel.model_validate({
                "key": "C", "mode": "ionian",
                "form_type": "song",
                "form": ["verse", "bridge"],
                "sections": {"verse": _minimal_section()},
            })

    def test_invalid_bad_tempo_out_of_range(self):
        with pytest.raises(ValidationError):
            PieceModel.model_validate({
                "key": "C", "mode": "ionian",
                "sections": [_minimal_section()],
                "tempo": 500,
            })

    def test_invalid_bad_transform_in_sequence(self):
        with pytest.raises(ValidationError):
            PieceModel.model_validate({
                "key": "C", "mode": "ionian",
                "sections": [_minimal_section()],
                "transform_sequence": ["not_a_real_transform"],
            })

    def test_no_tempo_warns_via_validate_against_theme(self):
        piece = PieceModel.model_validate({
            "key": "C", "mode": "ionian",
            "sections": [_minimal_section()],
        })
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            piece.validate_against_theme(piece)  # self-check, theme absorbed
        assert any("no explicit 'tempo'" in str(w.message) for w in caught)

    def test_invalid_missing_required_key(self):
        """key/mode absorbed from ThemeModel are now required on PieceModel."""
        with pytest.raises(ValidationError):
            PieceModel.model_validate({
                "mode": "ionian",
                "sections": [_minimal_section()],
            })

    def test_no_motif_warns(self):
        """Absorbed from ThemeModel._motif_consistency — now a self-check."""
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            PieceModel.model_validate({
                "key": "C", "mode": "ionian",
                "sections": [_minimal_section()],
            })
        assert any("no motif or motifs defined" in str(w.message) for w in caught)
