"""
schemas.py — Pydantic v2 models for FormaComposition input validation.

Replaces the manual validate_piece() dictionary inspection with formal
typed models. Every field mirrors what generate_section() and the factory
functions currently read via .get() — defaults are preserved exactly.

Validation hierarchy:
    PieceModel
    ├── SectionModel          (narrative: list of these)
    │   ├── HarmonyRhythmModel
    │   ├── CounterpointModel
    │   ├── RhythmPatternModel
    │   ├── DrumModel
    │   └── FugalTechniquesModel (just a list[str])
    └── SongFormEntryModel    (song form: form array entries)

MotifModel and ThemeModel cover the theme side.

Usage
-----
    from intervals.core.schemas import PieceModel, ThemeModel, SectionModel

    # Validate at load time — raises ValidationError with field-level detail
    theme = ThemeModel.model_validate(raw_theme_dict)
    piece = PieceModel.model_validate(raw_piece_dict)

    # Pass the validated Section to the factory builders
    section = piece.sections[0]   # SectionModel instance
    ctx = build_rhythm_context_from_model(section, motif_def, total_beats, seed, offset)
"""

from __future__ import annotations

from typing import Annotated, Literal, Optional, Union
import warnings

from pydantic import (
    BaseModel,
    Field,
    field_validator,
    model_validator,
    ConfigDict,
)

# ─── Literal enum aliases (single source of truth) ───────────────────────────

DensityLiteral     = Literal["low", "sparse", "medium", "high", "full"]
MelodyLiteral      = Literal["lyrical", "generative", "motif", "sparse", "rhythmic", "develop"]
BassStyleLiteral   = Literal[
    "root_fifth", "walking", "pedal", "arpeggiated", "sparse",
    "root_only", "melodic", "steady", "pulse",
]
ArcLiteral         = Literal[
    "swell", "fade", "build", "plateau", "decay",
    "fade_in", "fade_out", "breath",
]
RhythmSourceLiteral        = Literal["motif", "pattern", "free"]
HarmonyRhythmSourceLiteral = Literal["motif", "pattern", "sustain", "free"]
TransformLiteral   = Literal[
    "original", "inversion", "retrograde", "retrograde_inversion",
    "augmentation", "diminution", "transpose_up", "transpose_down",
    "shuffle", "expand", "compress",
]
CounterpointSpeciesLiteral  = Literal["free", "first", "second", "third", "fourth", "fifth"]
CounterpointRegisterLiteral = Literal["above", "below"]
DissonanceLiteral           = Literal["none", "passing", "neighbor", "free"]

# ─── Shared config ─────────────────────────────────────────────────────────

class _StrictBase(BaseModel):
    """Reject unknown keys so typos surface immediately (mirrors VALID_SECTION_KEYS check)."""
    model_config = ConfigDict(extra="forbid", populate_by_name=True)


# ═══════════════════════════════════════════════════════════════════════════════
# Sub-models
# ═══════════════════════════════════════════════════════════════════════════════

class RhythmPatternModel(_StrictBase):
    """
    Hand-played rhythm pattern produced by rhythm_extract.py.
    Corresponds to section["rhythm_pattern"] / section["harmony_pattern"].
    """
    onsets:       list[float]
    durations:    list[float]
    velocities:   Optional[list[float]] = None
    length_beats: float = Field(default=8.0, gt=0)

    @model_validator(mode="after")
    def _lengths_match(self) -> "RhythmPatternModel":
        if len(self.onsets) != len(self.durations):
            raise ValueError(
                f"rhythm_pattern: onsets ({len(self.onsets)}) and "
                f"durations ({len(self.durations)}) must have the same length"
            )
        if self.velocities is not None and len(self.velocities) != len(self.onsets):
            raise ValueError(
                f"rhythm_pattern: velocities ({len(self.velocities)}) must match "
                f"onsets ({len(self.onsets)})"
            )
        return self


class HarmonyRhythmModel(_StrictBase):
    """
    Corresponds to section["harmony_rhythm"] block.
    When omitted from a section, HarmonyRhythmModel is not instantiated —
    the factory falls back to the section's main rhythm source.
    """
    rhythm:  HarmonyRhythmSourceLiteral
    density: Optional[DensityLiteral] = None
    groove:  Optional[str] = None
    swing:   Annotated[float, Field(ge=0.0, le=1.0)] = 0.0


class CounterpointModel(_StrictBase):
    """Corresponds to section["counterpoint"] block."""
    species:      CounterpointSpeciesLiteral  = "free"
    register:     CounterpointRegisterLiteral = "below"
    dissonance:   DissonanceLiteral           = "passing"
    velocity:     Annotated[int, Field(ge=1, le=127)] = 58
    canon_offset: Annotated[float, Field(ge=0.0)]     = 0.0


class DrumModel(_StrictBase):
    """
    Corresponds to section["drums"].
    Accepts either the bare string form (``"four_on_floor"``) or a
    full dict — both are normalised to this model by the SectionModel
    validator below.
    """
    pattern: str = "four_on_floor"


class MotifModel(BaseModel):
    """
    A single motif definition (theme["motif"] or an entry in theme["motifs"]).
    extra="allow" because composers sometimes add documentation fields.
    """
    model_config = ConfigDict(extra="allow")

    name:            Optional[str]         = None
    intervals:       list[int]             = Field(min_length=1)
    rhythm:          Optional[list[float]] = None
    velocities:      Optional[list[float]] = None
    transform_pool:  list[TransformLiteral] = Field(default_factory=list)

    @model_validator(mode="after")
    def _rhythm_vel_match(self) -> "MotifModel":
        if self.rhythm is not None and self.velocities is not None:
            if len(self.velocities) != len(self.rhythm):
                raise ValueError(
                    f"motif '{self.name}': velocities length ({len(self.velocities)}) "
                    f"must match rhythm length ({len(self.rhythm)})"
                )
        return self


# ═══════════════════════════════════════════════════════════════════════════════
# SectionModel — the main validated input for generate_section()
# ═══════════════════════════════════════════════════════════════════════════════

class SectionModel(BaseModel):
    """
    Validated representation of a single section dict.

    All .get() defaults from generator.py / strategies.py are encoded here
    as Pydantic field defaults so callers can access ``section.density``
    instead of ``section.get("density", "medium")``.

    extra="allow" is intentional: the "notes" field is free-form documentation
    and there may be future extension fields. Unknown *structural* keys (ones
    that affect generation) are caught by validate_piece() which still runs
    as a cross-section sanity pass.
    """
    model_config = ConfigDict(extra="allow", populate_by_name=True)

    # ── Identity ──────────────────────────────────────────────────────────────
    name:          Optional[str] = None

    # ── Harmony / progression ─────────────────────────────────────────────────
    progression:   list[str]    = Field(min_length=1)

    # chord_bars is the source of truth when present; bars is derived from it.
    # When only bars is supplied it's distributed evenly across chords.
    chord_bars:    Optional[list[float]] = None
    bars:          Optional[float]       = None

    beats_per_bar: int = Field(default=4, ge=1, le=16)

    # ── Density / behaviour ───────────────────────────────────────────────────
    density:       DensityLiteral   = "medium"
    melody:        MelodyLiteral    = "generative"
    bass_style:    BassStyleLiteral = "root_fifth"
    arc:           ArcLiteral       = "swell"

    # ── Rhythm ────────────────────────────────────────────────────────────────
    rhythm:         RhythmSourceLiteral                  # required — no default
    harmony_rhythm: Optional[HarmonyRhythmModel] = None
    rhythm_pattern:  Optional[RhythmPatternModel] = None
    harmony_pattern: Optional[RhythmPatternModel] = None

    groove: Optional[str]                                    = None
    swing:  Annotated[float, Field(ge=0.0, le=1.0)]         = 0.0

    # ── Melody tuning ─────────────────────────────────────────────────────────
    rest_probability: Annotated[float, Field(ge=0.0, le=1.0)] = 0.0
    fugal_techniques: Optional[list[str]]                      = None

    # ── Optional voices ───────────────────────────────────────────────────────
    counterpoint: Optional[CounterpointModel] = None
    drums:        Optional[DrumModel]         = None
    percussion:   Optional[dict]              = None   # future-proofed, untyped

    # ── Free-form documentation ───────────────────────────────────────────────
    notes: Optional[str] = None

    # ── Cross-field validation ────────────────────────────────────────────────

    @model_validator(mode="after")
    def _validate_bars(self) -> "SectionModel":
        if self.chord_bars is not None:
            if len(self.chord_bars) != len(self.progression):
                raise ValueError(
                    f"chord_bars has {len(self.chord_bars)} entries but "
                    f"progression has {len(self.progression)} chords"
                )
            derived = sum(self.chord_bars)
            if self.bars is not None and abs(derived - self.bars) > 0.01:
                warnings.warn(
                    f"Section '{self.name}': bars={self.bars} but "
                    f"sum(chord_bars)={derived}. chord_bars wins; "
                    f"consider removing 'bars'.",
                    stacklevel=4,
                )
            # Normalise: bars is always derivable
            object.__setattr__(self, "bars", derived)
        elif self.bars is None:
            warnings.warn(
                f"Section '{self.name}': no 'bars' or 'chord_bars' — "
                f"defaulting to 8 bars.",
                stacklevel=4,
            )
            object.__setattr__(self, "bars", 8.0)
        return self

    @model_validator(mode="after")
    def _validate_rhythm_dependencies(self) -> "SectionModel":
        if self.rhythm == "pattern" and self.rhythm_pattern is None:
            raise ValueError(
                f"Section '{self.name}': rhythm='pattern' requires a "
                f"rhythm_pattern block"
            )
        if self.harmony_rhythm is not None:
            hr = self.harmony_rhythm
            if hr.rhythm == "pattern" and self.harmony_pattern is None:
                raise ValueError(
                    f"Section '{self.name}': harmony_rhythm.rhythm='pattern' "
                    f"requires a harmony_pattern block"
                )
        return self

    # ── Convenience helpers ───────────────────────────────────────────────────

    def bars_list(self) -> list[float]:
        """Return per-chord bar durations (same logic as generator.py)."""
        if self.chord_bars is not None:
            return [float(b) for b in self.chord_bars]
        bars = self.bars or 8.0
        even = bars / len(self.progression)
        return [even] * len(self.progression)

    def total_beats(self) -> float:
        return sum(b * self.beats_per_bar for b in self.bars_list())

    def to_dict(self) -> dict:
        """
        Serialise back to a plain dict compatible with the legacy generator.
        Useful during the migration period when some callers still expect raw dicts.
        """
        return self.model_dump(exclude_none=True)


# ─── Normaliser: bare string drums → DrumModel ───────────────────────────────

@field_validator("drums", mode="before")
def _coerce_drums(cls, v):  # noqa: N805  (pydantic convention)
    if isinstance(v, str):
        return {"pattern": v}
    return v

SectionModel.drums = field_validator("drums", mode="before")(
    lambda cls, v: {"pattern": v} if isinstance(v, str) else v
)


# ═══════════════════════════════════════════════════════════════════════════════
# Song-form models
# ═══════════════════════════════════════════════════════════════════════════════

class SongFormEntryModel(BaseModel):
    """One entry in the piece["form"] array (song form only)."""
    model_config = ConfigDict(extra="forbid")

    section:   str
    variation: Annotated[float, Field(ge=0.0, le=1.0)] = 0.0


# ═══════════════════════════════════════════════════════════════════════════════
# ThemeModel
# ═══════════════════════════════════════════════════════════════════════════════

class TempoRangeModel(BaseModel):
    model_config = ConfigDict(extra="forbid")
    min: Annotated[int, Field(ge=20, le=300)]
    max: Annotated[int, Field(ge=20, le=300)]

    @model_validator(mode="after")
    def _min_lt_max(self) -> "TempoRangeModel":
        if self.min > self.max:
            raise ValueError(f"tempo.min ({self.min}) must be ≤ tempo.max ({self.max})")
        return self


class ThemeModel(BaseModel):
    """
    Validated theme dict.
    extra="allow" — composers add documentation fields freely.
    """
    model_config = ConfigDict(extra="allow")

    name:   Optional[str] = None
    key:    str           = Field(min_length=1)
    mode:   str           = Field(min_length=1)
    tempo:  TempoRangeModel

    motif:  Optional[MotifModel]       = None
    motifs: Optional[list[MotifModel]] = None

    @model_validator(mode="after")
    def _motif_consistency(self) -> "ThemeModel":
        if self.motif is not None and self.motifs is not None:
            warnings.warn(
                "theme has both 'motif' and 'motifs' — 'motifs' array takes "
                "precedence; 'motif' is ignored.",
                stacklevel=4,
            )
        if self.motifs is not None and len(self.motifs) == 0:
            raise ValueError("theme 'motifs' must be a non-empty list")
        return self

    @property
    def primary_motif(self) -> Optional[MotifModel]:
        """Return the effective primary motif (motifs[0] if array, else motif)."""
        if self.motifs:
            return self.motifs[0]
        return self.motif


# ═══════════════════════════════════════════════════════════════════════════════
# PieceModel
# ═══════════════════════════════════════════════════════════════════════════════

class PieceModel(BaseModel):
    """
    Validated piece dict.
    Supports both narrative (sections: list) and song (form_type='song') forms.

    The JSON key ``sections`` is overloaded by the engine:
    - Narrative form: a ``list[SectionModel]``
    - Song form:      a ``dict[str, SectionModel]`` (named section definitions)

    We disambiguate in ``_unwrap_sections`` before Pydantic sees the fields,
    populating either ``sections`` (list) or ``song_sections`` (dict) so the
    two form types don't fight over the same field name.
    """
    model_config = ConfigDict(extra="allow", populate_by_name=True)

    title:     Optional[str] = None
    tempo:     Optional[Annotated[int, Field(ge=20, le=300)]] = None
    seed:      int = 42

    form_type: Literal["narrative", "song"] = "narrative"

    # Narrative form — populated by _unwrap_sections when sections is a list
    sections: Optional[list[SectionModel]] = None

    # Song form — populated by _unwrap_sections when sections is a dict
    song_sections: Optional[dict[str, SectionModel]] = None

    # Song form — play order
    form: Optional[list[Union[SongFormEntryModel, str]]] = None

    transform_sequence: Optional[list[TransformLiteral]] = None

    @model_validator(mode="before")
    @classmethod
    def _unwrap_nested_and_sections(cls, data: dict) -> dict:
        """
        1. Accept both ``{"piece": {...}}`` and flat dict forms.
        2. Disambiguate the overloaded ``sections`` key into
           ``sections`` (list) or ``song_sections`` (dict).
        """
        if "piece" in data and isinstance(data["piece"], dict):
            data = data["piece"]
        else:
            data = dict(data)  # shallow copy — don't mutate caller's dict

        raw_sections = data.get("sections")
        if isinstance(raw_sections, dict):
            # Song form: move to song_sections so the list field stays clean
            data["song_sections"] = raw_sections
            data.pop("sections", None)
        # If it's a list (or absent), leave as-is for the narrative field

        return data

    @model_validator(mode="after")
    def _form_consistency(self) -> "PieceModel":
        if self.form_type == "song":
            if not self.form:
                raise ValueError("form_type='song' requires a 'form' array")
            if not self.song_sections:
                raise ValueError(
                    "form_type='song' requires a 'sections' dict of named "
                    "section definitions"
                )
        else:
            if not self.sections:
                raise ValueError("Narrative piece must have a non-empty 'sections' list")
        return self

    def iter_sections(self) -> list[SectionModel]:
        """
        Return sections in generation order, handling both form types.
        For song form this is the expanded list (variation application
        is still handled by the generator's ``_apply_variation``).
        For narrative this is sections directly.
        """
        if self.form_type == "narrative":
            return self.sections or []
        # Song form: resolve form-array references
        result = []
        for entry in (self.form or []):
            name = entry if isinstance(entry, str) else entry.section
            defn = (self.song_sections or {}).get(name)
            if defn is None:
                raise ValueError(f"Song form references undefined section '{name}'")
            result.append(defn)
        return result
