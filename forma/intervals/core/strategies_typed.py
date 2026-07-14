"""
strategies_typed.py — SectionModel-aware context factory for harmony.

Builds HarmonyRhythmContext from a validated SectionModel rather than a raw
dict, so there are no silent key-name typos or missing defaults.
"""

from __future__ import annotations

from typing import Optional

from intervals.music.harmony import VoicedChord, HarmonyRhythmContext
from intervals.music.rhythm import RhythmEvent
from intervals.core.schemas import SectionModel


# ═══════════════════════════════════════════════════════════════════════════════
# HarmonyRhythmContext factory — model-aware
# ═══════════════════════════════════════════════════════════════════════════════

def build_harmony_rhythm_context_from_model(
    section: SectionModel,
    active_motif_def: Optional[dict],
    total_beats_section: float,
    total_per_chord: float,
    beat_offset: float,
    precomputed_events,                # list[RhythmEvent] | "sustain" | None
    seed: int = 42,
) -> HarmonyRhythmContext:
    """
    Typed replacement for build_harmony_rhythm_context(section_dict, ...).

    ``section.harmony_rhythm`` is already a validated ``HarmonyRhythmModel``
    (or None), so we read its fields directly rather than doing nested .get().
    """
    hr = section.harmony_rhythm

    # Determine effective harmony rhythm source:
    # - If harmony_rhythm block is present AND sets .rhythm, use it.
    # - Otherwise (block absent, or present but .rhythm unset — e.g. a
    #   harmony_rhythm block that only overrides density/groove) fall back
    #   to the section's main rhythm source. Pre-existing bug fixed here:
    #   `hr.rhythm if hr is not None else section.rhythm` only fell back
    #   when the whole block was absent, not when it was present with
    #   .rhythm left None — silently producing h_source=None (and later a
    #   KeyError at dispatch) for any harmony_rhythm block that set
    #   density/groove without also setting rhythm.
    _explicit_h_rhythm = hr.rhythm if hr is not None else None
    h_source = _explicit_h_rhythm or section.rhythm

    # "motif" is a valid harmony rhythm source again (reintroduced 2026-07,
    # see schemas.py HarmonyRhythmSourceLiteral) — but only when set
    # explicitly on the harmony_rhythm block itself. This line still
    # inherits section.rhythm when harmony_rhythm is absent/unset, and
    # nearly every melodic section sets rhythm="motif" — letting that
    # inheritance activate harmony's independent motif mechanism would
    # reopen the exact back door "motif" was retired for the first time.
    # Coerce the *inherited* case to "free"; the *explicit* case dispatches
    # to _MotifHarmonyStrategy normally.
    if h_source == "motif" and _explicit_h_rhythm != "motif":
        h_source = "free"

    # Harmony-specific overrides (groove / density come from the hr block when set)
    density = (hr.density if hr is not None and hr.density is not None
               else section.density)
    groove  = (hr.groove  if hr is not None and hr.groove  is not None
               else section.groove)

    motif_rhythm:     Optional[list[float]] = None
    motif_velocities: Optional[list[float]] = None
    if active_motif_def and h_source == "motif":
        motif_rhythm     = active_motif_def.get("rhythm")
        motif_velocities = active_motif_def.get("velocities")

    harmony_pattern_dict: Optional[dict] = None
    if h_source == "pattern" and section.harmony_pattern is not None:
        harmony_pattern_dict = section.harmony_pattern.model_dump(exclude_none=True)

    return HarmonyRhythmContext(
        source=h_source,
        total_beats_section=total_beats_section,
        total_per_chord=total_per_chord,
        beat_offset=beat_offset,
        density=density,
        groove=groove,
        beats_per_bar=section.beats_per_bar,
        harmony_pattern=harmony_pattern_dict,
        motif_rhythm=motif_rhythm,
        motif_velocities=motif_velocities,
        precomputed_events=precomputed_events,
        seed=seed,
    )


# ═══════════════════════════════════════════════════════════════════════════════
# Migration helper — validate once, call anywhere
# ═══════════════════════════════════════════════════════════════════════════════

def validate_section_dict(section: dict) -> SectionModel:
    """
    Validate and coerce a raw section dict to a SectionModel.
    Call this once at the top of generate_section() to get the typed object,
    then pass it to the _from_model factory functions.

    Raises pydantic.ValidationError (not ValueError) — callers that currently
    catch ValueError should also catch ValidationError, or convert it:

        from pydantic import ValidationError
        try:
            sec = validate_section_dict(section)
        except ValidationError as exc:
            raise ValueError(str(exc)) from exc
    """
    from intervals.core.schemas import SectionModel
    return SectionModel.model_validate(section)
