"""
strategies_typed.py — Model-aware factory functions for strategies.py.

Drop-in replacements for build_rhythm_context() and build_melody_context()
that accept a validated SectionModel instead of a raw dict.

Integration
-----------
In strategies.py, add these two imports at the top of the file:

    from intervals.core.schemas import SectionModel
    from intervals.core.strategies_typed import (
        build_rhythm_context_from_model,
        build_harmony_rhythm_context_from_model,
        build_melody_context_from_model,
    )

Then in generate_section() (generator.py), replace the three
build_*_context() calls with the _from_model variants:

    # BEFORE
    section_dict = section  # raw dict
    rctx = build_rhythm_context(section_dict, active_motif_def, ...)

    # AFTER
    section_model = SectionModel.model_validate(section)   # validate once
    rctx = build_rhythm_context_from_model(section_model, active_motif_def, ...)

The raw-dict factories remain untouched for now — both forms work
during the migration period.

Why keep both?
--------------
The old factories are still called by tests and external scripts.
The new _from_model variants are the canonical path going forward.
Once all callers are migrated, the raw-dict versions can be deleted.
"""

from __future__ import annotations

from typing import Optional

from intervals.music.harmony import VoicedChord
from intervals.music.rhythm import RhythmEvent
from intervals.core.schemas import SectionModel
from intervals.core.strategies import (
    RhythmContext,
    HarmonyRhythmContext,
    MelodyContext,
)


# ═══════════════════════════════════════════════════════════════════════════════
# RhythmContext factory — model-aware
# ═══════════════════════════════════════════════════════════════════════════════

def build_rhythm_context_from_model(
    section: SectionModel,
    active_motif_def: Optional[dict],
    total_beats: float,
    base_seed: int,
    seed_offset: int,
) -> RhythmContext:
    """
    Typed replacement for build_rhythm_context(section_dict, ...).

    All .get() calls replaced by direct attribute access on the validated
    SectionModel, so there are no silent key-name typos or missing defaults.

    Key differences from the raw-dict version
    ------------------------------------------
    * ``section.rhythm`` is *required* by the model — it cannot be None here.
      The validator already raised if it was missing.
    * ``section.density``, ``section.beats_per_bar``, etc. carry their
      Pydantic defaults — no more fragile .get("density", "medium").
    * ``section.rhythm_pattern`` is already a ``RhythmPatternModel`` (or None),
      so we call ``.model_dump()`` to hand a plain dict to the downstream
      ``rhythm_pattern_to_events()`` function that hasn't been typed yet.
    """
    rhythm_source = section.rhythm   # Literal["motif", "pattern", "free"]

    motif_rhythm:     Optional[list[float]] = None
    motif_velocities: Optional[list[float]] = None

    if active_motif_def and rhythm_source == "motif":
        motif_rhythm     = active_motif_def.get("rhythm")
        motif_velocities = active_motif_def.get("velocities")

    # Serialise RhythmPatternModel → plain dict for downstream consumers
    # that still work with raw dicts (rhythm_pattern_to_events, etc.)
    rhythm_pattern_dict: Optional[dict] = None
    if rhythm_source == "pattern" and section.rhythm_pattern is not None:
        rhythm_pattern_dict = section.rhythm_pattern.model_dump(exclude_none=True)

    return RhythmContext(
        source=rhythm_source,
        total_beats=total_beats,
        density=section.density,
        rhythm_pattern=rhythm_pattern_dict,
        motif_rhythm=motif_rhythm,
        motif_velocities=motif_velocities,
        groove=section.groove,
        swing=section.swing,
        beats_per_bar=section.beats_per_bar,
        seed=base_seed + seed_offset,
    )


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
) -> HarmonyRhythmContext:
    """
    Typed replacement for build_harmony_rhythm_context(section_dict, ...).

    ``section.harmony_rhythm`` is already a validated ``HarmonyRhythmModel``
    (or None), so we read its fields directly rather than doing nested .get().
    """
    hr = section.harmony_rhythm

    # Determine effective harmony rhythm source:
    # - If harmony_rhythm block is present, use its .rhythm field.
    # - Otherwise fall back to the section's main rhythm source.
    h_source = hr.rhythm if hr is not None else section.rhythm

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
    )


# ═══════════════════════════════════════════════════════════════════════════════
# MelodyContext factory — model-aware
# ═══════════════════════════════════════════════════════════════════════════════

def build_melody_context_from_model(
    section: SectionModel,
    chords: list[VoicedChord],
    key: str,
    mode: str,
    active_motif_def: Optional[dict],
    motif_pool: list[dict],
    melody_rhythm_events: Optional[list[RhythmEvent]],
    base_seed: int,
    seed_offset: int,
) -> MelodyContext:
    """
    Typed replacement for build_melody_context(section_dict, ...).

    ``bars_list`` is now derived from ``section.bars_list()`` (the model
    helper method) — no separate parameter needed.

    Compared to the raw-dict version:
    * ``section.melody``, ``section.density``, etc. are guaranteed valid
      Literal values — no runtime enum-check needed here.
    * ``section.rest_probability`` and ``section.swing`` are already
      float-range-validated (0.0–1.0) by Pydantic.
    * ``section.fugal_techniques`` is Optional[list[str]] — type safe.
    """
    bars_list = section.bars_list()

    return MelodyContext(
        behavior=section.melody,
        chords=chords,
        key=key,
        mode=mode,
        density=section.density,
        bars_per_chord=bars_list,
        beats_per_bar=section.beats_per_bar,
        motif=active_motif_def,
        motif_pool=motif_pool if len(motif_pool) > 1 else None,
        groove=section.groove,
        swing=section.swing,
        seed=base_seed + seed_offset,
        section_name=section.name or "",
        rhythm_events_override=melody_rhythm_events,
        fugal_techniques=section.fugal_techniques,
        rest_probability=section.rest_probability,
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
