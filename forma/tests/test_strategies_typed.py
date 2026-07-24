"""
Tests for intervals.core.strategies_typed — the SectionModel-aware
HarmonyRhythmContext factory.

This is the other scaffold-threading path in the orchestration layer:
build_harmony_rhythm_context_from_model() takes a validated SectionModel
plus piece-level timing (total_beats_section, total_per_chord, beat_offset)
and threads section-level scaffold (beats_per_bar, density, groove) into
the HarmonyRhythmContext every harmony strategy reads from -- with the
harmony_rhythm block's own overrides winning when present.

The specific non-leak case tested here: a motif dict (the kind of
per-voice-specific data melody/bass consume) must NOT populate the
context's motif_rhythm/motif_velocities fields unless harmony's rhythm
source is EXPLICITLY "motif" on the harmony_rhythm block itself -- an
inherited section.rhythm == "motif" (the common case for melodic
sections) must not silently leak into harmony's own motif mechanism.
"""
import pytest

from intervals.core.schemas import SectionModel
from intervals.core.strategies_typed import (
    build_harmony_rhythm_context_from_model,
    validate_section_dict,
)


def _section(**overrides):
    base = {
        "progression": ["i", "iv"],
        "rhythm": "free",
        "bars": 8,
        "beats_per_bar": 4,
    }
    base.update(overrides)
    return SectionModel.model_validate(base)


MOTIF = {"intervals": [2, -1], "rhythm": [1.0, 1.0], "velocities": [0.6, 0.7]}


# ===========================================================================
# Scaffold threading
# ===========================================================================

class TestScaffoldThreading:
    def test_beats_per_bar_threads_from_section(self):
        section = _section(beats_per_bar=3)
        ctx = build_harmony_rhythm_context_from_model(
            section, None, total_beats_section=24.0, total_per_chord=12.0,
            beat_offset=0.0, precomputed_events=None,
        )
        assert ctx.beats_per_bar == 3

    def test_density_and_groove_fall_back_to_section_when_hr_block_absent(self):
        section = _section(density="full", groove="straight")
        ctx = build_harmony_rhythm_context_from_model(
            section, None, total_beats_section=32.0, total_per_chord=16.0,
            beat_offset=0.0, precomputed_events=None,
        )
        assert ctx.density == "full"
        assert ctx.groove == "straight"

    def test_harmony_rhythm_block_overrides_win_over_section_scaffold(self):
        section = _section(density="sparse", groove="straight",
                            harmony_rhythm={"density": "full", "groove": "waltz"})
        ctx = build_harmony_rhythm_context_from_model(
            section, None, total_beats_section=32.0, total_per_chord=16.0,
            beat_offset=0.0, precomputed_events=None,
        )
        assert ctx.density == "full"
        assert ctx.groove == "waltz"

    def test_partial_override_still_inherits_the_unset_scaffold_field(self):
        """harmony_rhythm overriding density only must still inherit
        section.groove -- a partial override shouldn't blank out the
        sibling scaffold field it didn't touch."""
        section = _section(density="sparse", groove="straight",
                            harmony_rhythm={"density": "full"})
        ctx = build_harmony_rhythm_context_from_model(
            section, None, total_beats_section=32.0, total_per_chord=16.0,
            beat_offset=0.0, precomputed_events=None,
        )
        assert ctx.density == "full"     # hr override
        assert ctx.groove == "straight"  # inherited from section scaffold

    def test_timing_scaffold_passes_through_unchanged(self):
        section = _section()
        ctx = build_harmony_rhythm_context_from_model(
            section, None, total_beats_section=64.0, total_per_chord=16.0,
            beat_offset=32.0, precomputed_events=None, seed=7,
        )
        assert ctx.total_beats_section == 64.0
        assert ctx.total_per_chord == 16.0
        assert ctx.beat_offset == 32.0
        assert ctx.seed == 7

    def test_explicit_harmony_source_wins_over_section_rhythm(self):
        section = _section(rhythm="free", harmony_rhythm={"rhythm": "sustain"})
        ctx = build_harmony_rhythm_context_from_model(
            section, None, total_beats_section=32.0, total_per_chord=16.0,
            beat_offset=0.0, precomputed_events=None,
        )
        assert ctx.source == "sustain"

    def test_absent_harmony_rhythm_block_falls_back_to_section_rhythm(self):
        section = _section(rhythm="free")
        ctx = build_harmony_rhythm_context_from_model(
            section, None, total_beats_section=32.0, total_per_chord=16.0,
            beat_offset=0.0, precomputed_events=None,
        )
        assert ctx.source == "free"

    def test_harmony_rhythm_block_present_but_rhythm_unset_still_falls_back(self):
        """Regression case named directly in the source comment: a
        harmony_rhythm block that only sets density/groove (leaving
        .rhythm None) must still fall back to section.rhythm, not
        silently produce source=None."""
        section = _section(rhythm="free", harmony_rhythm={"density": "full"})
        ctx = build_harmony_rhythm_context_from_model(
            section, None, total_beats_section=32.0, total_per_chord=16.0,
            beat_offset=0.0, precomputed_events=None,
        )
        assert ctx.source == "free"


# ===========================================================================
# Non-leak: motif data must not bleed into harmony's context unless
# harmony's OWN rhythm source is explicitly "motif"
# ===========================================================================

class TestMotifNonLeak:
    def test_motif_data_absent_when_harmony_source_is_free(self):
        section = _section(rhythm="free")
        ctx = build_harmony_rhythm_context_from_model(
            section, MOTIF, total_beats_section=32.0, total_per_chord=16.0,
            beat_offset=0.0, precomputed_events=None,
        )
        assert ctx.source == "free"
        assert ctx.motif_rhythm is None
        assert ctx.motif_velocities is None

    def test_inherited_section_rhythm_motif_does_not_leak_into_harmony(self):
        """The exact leak this module's docstring calls out: nearly every
        melodic section sets rhythm='motif' for its OWN (melody's)
        purposes. Letting that inheritance silently activate harmony's
        independent motif mechanism would be per-voice data (melody's
        motif choice) leaking into a voice that never asked for it.
        Confirmed: source coerces to 'free', motif fields stay None even
        though a real motif dict was passed in."""
        section = _section(rhythm="motif")  # no explicit harmony_rhythm block at all
        ctx = build_harmony_rhythm_context_from_model(
            section, MOTIF, total_beats_section=32.0, total_per_chord=16.0,
            beat_offset=0.0, precomputed_events=None,
        )
        assert ctx.source == "free"  # coerced, not "motif"
        assert ctx.motif_rhythm is None
        assert ctx.motif_velocities is None

    def test_explicit_harmony_rhythm_motif_does_populate_motif_data(self):
        """The other side of the same boundary: when harmony's rhythm
        source is set EXPLICITLY (not inherited) to 'motif' on the
        harmony_rhythm block itself, the motif data legitimately belongs
        to harmony now and must populate."""
        section = _section(rhythm="free", harmony_rhythm={"rhythm": "motif"})
        ctx = build_harmony_rhythm_context_from_model(
            section, MOTIF, total_beats_section=32.0, total_per_chord=16.0,
            beat_offset=0.0, precomputed_events=None,
        )
        assert ctx.source == "motif"
        assert ctx.motif_rhythm == [1.0, 1.0]
        assert ctx.motif_velocities == [0.6, 0.7]

    def test_no_motif_def_leaves_motif_fields_none_even_for_explicit_motif_source(self):
        section = _section(rhythm="free", harmony_rhythm={"rhythm": "motif"})
        ctx = build_harmony_rhythm_context_from_model(
            section, None, total_beats_section=32.0, total_per_chord=16.0,
            beat_offset=0.0, precomputed_events=None,
        )
        assert ctx.source == "motif"
        assert ctx.motif_rhythm is None
        assert ctx.motif_velocities is None

    def test_harmony_pattern_only_populated_when_source_is_pattern(self):
        """Same non-leak principle for the pattern block: it should only
        surface in the context when harmony's own source is 'pattern'."""
        section_free = _section(rhythm="free")
        ctx_free = build_harmony_rhythm_context_from_model(
            section_free, None, total_beats_section=32.0, total_per_chord=16.0,
            beat_offset=0.0, precomputed_events=None,
        )
        assert ctx_free.harmony_pattern is None

        section_pattern = _section(
            rhythm="free",
            harmony_rhythm={"rhythm": "pattern"},
            harmony_pattern={"onsets": [0.0], "durations": [1.0]},
        )
        ctx_pattern = build_harmony_rhythm_context_from_model(
            section_pattern, None, total_beats_section=32.0, total_per_chord=16.0,
            beat_offset=0.0, precomputed_events=None,
        )
        assert ctx_pattern.harmony_pattern is not None
        assert ctx_pattern.harmony_pattern["onsets"] == [0.0]


# ===========================================================================
# validate_section_dict
# ===========================================================================

class TestValidateSectionDict:
    def test_valid_dict_returns_a_section_model(self):
        result = validate_section_dict({
            "progression": ["i", "iv"], "rhythm": "free", "bars": 8,
        })
        assert isinstance(result, SectionModel)
        assert result.progression == ["i", "iv"]

    def test_invalid_dict_raises_pydantic_validation_error(self):
        from pydantic import ValidationError
        with pytest.raises(ValidationError):
            validate_section_dict({"rhythm": "free", "bars": 8})  # missing progression
