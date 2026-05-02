"""
schemas.py — Pydantic v2 models for FormaComposition input validation.

Single source of truth for all structural and enum-based validation.
``validate_piece()`` in generator.py has been retired; call
``PieceModel.model_validate(piece)`` and ``ThemeModel.model_validate(theme)``
instead.

Validation hierarchy:
    PieceModel
    ├── SectionModel          (narrative: list of these)
    │   ├── HarmonyRhythmModel
    │   ├── CounterpointModel
    │   ├── RhythmPatternModel
    │   └── DrumModel
    └── SongFormEntryModel    (song form: form array entries)

MotifModel and ThemeModel cover the theme side.

Usage
-----
    from intervals.core.schemas import PieceModel, ThemeModel, SectionModel

    theme = ThemeModel.model_validate(raw_theme_dict)
    piece = PieceModel.model_validate(raw_piece_dict)
    piece.validate_against_theme(theme)   # cross-model rhythm checks

Exported Literal aliases
------------------------
Import these instead of maintaining local constant sets in generator.py:

    from intervals.core.schemas import (
        DensityLiteral, MelodyLiteral, BassStyleLiteral, ArcLiteral,
        RhythmSourceLiteral, HarmonyRhythmSourceLiteral, TransformLiteral,
        CounterpointSpeciesLiteral, CounterpointRegisterLiteral, DissonanceLiteral,
        VALID_DENSITY, VALID_MELODY_BEH, VALID_BASS_STYLE, VALID_ARC,
        VALID_RHYTHM_SOURCE, VALID_HARMONY_RHYTHM_SOURCE, VALID_TRANSFORMS,
    )
"""

from __future__ import annotations

import warnings
from typing import Annotated, Literal, Optional, Union, get_args

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

# Convenience sets for runtime checks — derived from Literals, not duplicated.
# These replace VALID_DENSITY, VALID_MELODY_BEH, etc. in generator.py.
VALID_DENSITY               = set(get_args(DensityLiteral))
VALID_MELODY_BEH            = set(get_args(MelodyLiteral))
VALID_BASS_STYLE            = set(get_args(BassStyleLiteral))
VALID_ARC                   = set(get_args(ArcLiteral))
VALID_RHYTHM_SOURCE         = set(get_args(RhythmSourceLiteral))
VALID_HARMONY_RHYTHM_SOURCE = set(get_args(HarmonyRhythmSourceLiteral))
VALID_TRANSFORMS            = set(get_args(TransformLiteral))

# ─── Obsolete field registries ───────────────────────────────────────────────

_OBSOLETE_THEME_KEYS    = {"palette"}


# ═══════════════════════════════════════════════════════════════════════════════
# Sub-models
# ═══════════════════════════════════════════════════════════════════════════════

class RhythmPatternModel(BaseModel):
    """
    Hand-played rhythm pattern produced by rhythm_extract.py.
    Corresponds to section["rhythm_pattern"] / section["harmony_pattern"].
    """
    model_config = ConfigDict(extra="forbid", populate_by_name=True)

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


class HarmonyRhythmModel(BaseModel):
    """
    Corresponds to section["harmony_rhythm"] block.

    ``rhythm`` is Optional: existing compositions may omit it and supply only
    density/groove/note_duration overrides; the factory cascades:
    harmony_rhythm.rhythm -> section.rhythm -> "free".
    """
    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    rhythm:        Optional[HarmonyRhythmSourceLiteral] = None
    density:       Optional[DensityLiteral]             = None
    groove:        Optional[str]                        = None
    swing:         Annotated[float, Field(ge=0.0, le=1.0)] = 0.0
    note_duration: Optional[Literal["whole", "half", "quarter", "eighth"]] = None


class CounterpointModel(BaseModel):
    """Corresponds to section["counterpoint"] block."""
    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    species:      CounterpointSpeciesLiteral  = "free"
    cp_register:  CounterpointRegisterLiteral = Field(default="below", alias="register")
    dissonance:   DissonanceLiteral           = "passing"
    velocity:     Annotated[int, Field(ge=1, le=127)] = 58
    canon_offset: Annotated[float, Field(ge=0.0)]     = 0.0


class DrumModel(BaseModel):
    """
    Corresponds to section["drums"].
    Accepts either the bare string form ("four_on_floor") or a full dict.
    Both are normalised by the SectionModel field_validator below.

    density / groove / swing default to None, meaning "inherit from the
    parent SectionModel".  The generator calls DrumModel.resolve() to get
    concrete values, passing the section-level defaults as fallbacks.
    """
    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    pattern: str                         = "four_on_floor"
    density: Optional[DensityLiteral]    = None   # None → inherit from section
    groove:  Optional[str]               = None   # None → inherit from section
    swing:   Optional[float]             = None   # None → inherit from section

    def resolve(
        self,
        section_density: str,
        section_groove: Optional[str],
        section_swing: float,
    ) -> tuple[str, Optional[str], float]:
        """Return (density, groove, swing) with section-level fallbacks applied."""
        return (
            self.density if self.density is not None else section_density,
            self.groove  if self.groove  is not None else section_groove,
            self.swing   if self.swing   is not None else section_swing,
        )


class MotifModel(BaseModel):
    """
    A single motif definition (theme["motif"] or an entry in theme["motifs"]).
    extra="allow" because composers sometimes add documentation fields.
    """
    model_config = ConfigDict(extra="allow")

    name:           Optional[str]          = None
    intervals:      list[int]              = Field(min_length=1)
    rhythm:         Optional[list[float]]  = None
    velocities:     Optional[list[float]]  = None
    transform_pool: list[TransformLiteral] = Field(default_factory=list)

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
# SectionModel
# ═══════════════════════════════════════════════════════════════════════════════

class SectionModel(BaseModel):
    """
    Validated representation of a single section dict.

    extra="allow" retains backward compatibility for the free-form ``notes``
    field and any composer-added documentation.  The ``notes`` field is also
    declared explicitly so it gets type-checking when present.

    Unknown *structural* keys are caught by the ``_warn_unknown_keys``
    model_validator, which emits warnings rather than raising errors, matching
    the spirit of the old validate_piece() [WARN] messages.
    """
    model_config = ConfigDict(extra="allow", populate_by_name=True)

    # Known structural keys — used for unknown-key warning
    _KNOWN_KEYS: set[str] = {
        "name", "bars", "chord_bars", "progression", "density", "melody",
        "bass_style", "arc", "harmony_rhythm", "beats_per_bar", "groove",
        "swing", "counterpoint", "notes", "percussion", "drums",
        "rhythm_pattern", "harmony_pattern", "fugal_techniques",
        "rhythm", "rest_probability",
    }

    # ── Identity ──────────────────────────────────────────────────────────────
    name:          Optional[str] = None

    # ── Harmony / progression ─────────────────────────────────────────────────
    progression:   list[str]          = Field(min_length=1)
    chord_bars:    Optional[list[float]] = None
    bars:          Optional[float]       = None
    beats_per_bar: int = Field(default=4, ge=1, le=16)

    # ── Density / behaviour ───────────────────────────────────────────────────
    density:    DensityLiteral   = "medium"
    melody:     MelodyLiteral    = "generative"
    bass_style: BassStyleLiteral = "root_fifth"
    arc:        ArcLiteral       = "swell"

    # ── Rhythm ────────────────────────────────────────────────────────────────
    rhythm:          RhythmSourceLiteral                    # required, no default
    harmony_rhythm:  Optional[HarmonyRhythmModel] = None
    rhythm_pattern:  Optional[RhythmPatternModel] = None
    harmony_pattern: Optional[RhythmPatternModel] = None

    groove: Optional[str]                                = None
    swing:  Annotated[float, Field(ge=0.0, le=1.0)]     = 0.0

    # ── Melody tuning ─────────────────────────────────────────────────────────
    rest_probability: Annotated[float, Field(ge=0.0, le=1.0)] = 0.0
    fugal_techniques: Optional[list[str]]                      = None

    # ── Optional voices ───────────────────────────────────────────────────────
    counterpoint: Optional[CounterpointModel] = None
    drums:        Optional[DrumModel]         = None
    percussion:   Optional[dict]              = None   # future-proofed, untyped

    # ── Free-form documentation ───────────────────────────────────────────────
    notes: Optional[str] = None

    # ─────────────────────────────────────────────────────────────────────────
    # Field coercions (mode="before")
    # ─────────────────────────────────────────────────────────────────────────

    @field_validator("drums", mode="before")
    @classmethod
    def _coerce_drums(cls, v):
        """Accept bare string form: "drums": "four_on_floor"."""
        if isinstance(v, str):
            return {"pattern": v}
        return v

    @field_validator("harmony_rhythm", mode="before")
    @classmethod
    def _coerce_harmony_rhythm(cls, v):
        """
        Reject bare string form ("harmony_rhythm": "sustain") with a clear error.
        Migrated from validate_piece() [ERROR] block.
        """
        if isinstance(v, str):
            raise ValueError(
                f"harmony_rhythm must be an object, not a bare string. "
                f'Use: {{"rhythm": "{v}"}}'
            )
        return v

    # ─────────────────────────────────────────────────────────────────────────
    # Cross-field validators (mode="after")
    # ─────────────────────────────────────────────────────────────────────────

    @model_validator(mode="after")
    def _warn_unknown_keys(self) -> "SectionModel":
        """
        Warn about keys outside the known structural set and flag obsolete keys.
        Migrated from the VALID_SECTION_KEYS / rhythm_phrase checks in validate_piece().
        Uses warnings.warn so generation continues; these are [WARN]-level issues.
        """
        extra_keys = set(self.model_extra or {})
        unknown = extra_keys - self._KNOWN_KEYS
        if unknown:
            warnings.warn(
                f"Section '{self.name}': unknown field(s) {sorted(unknown)} — "
                f"possible typo or obsolete key.",
                stacklevel=4,
            )
        return self

    @model_validator(mode="after")
    def _validate_bars(self) -> "SectionModel":
        """Migrated from validate_piece() bar/chord_bars checks."""
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
        """
        Validate rhythm/pattern cross-dependencies that don't need the theme.
        Theme-dependent checks (rhythm='motif' requires theme motif.rhythm)
        live in validate_against_theme() below.
        Migrated from validate_piece() rhythm cross-validate block.
        """
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

    # ─────────────────────────────────────────────────────────────────────────
    # Cross-model validation (requires theme — called by PieceModel)
    # ─────────────────────────────────────────────────────────────────────────

    def validate_against_theme(self, theme_model: "ThemeModel") -> None:
        """
        Validate rhythm-source prerequisites that depend on theme content.
        Migrated from the cross-validate block in validate_piece().

        Raises ValueError if rhythm='motif' but the theme has no motif rhythm.
        Call PieceModel.validate_against_theme(theme_model) to run this for
        every section at once.
        """
        primary = theme_model.primary_motif
        theme_has_rhythm = primary is not None and primary.rhythm is not None
        label = self.name or "?"

        if self.rhythm == "motif" and not theme_has_rhythm:
            raise ValueError(
                f"Section '{label}': rhythm='motif' but the theme's primary "
                f"motif has no 'rhythm' field"
            )
        if (
            self.harmony_rhythm is not None
            and self.harmony_rhythm.rhythm == "motif"
            and not theme_has_rhythm
        ):
            raise ValueError(
                f"Section '{label}': harmony_rhythm.rhythm='motif' but "
                f"the theme's primary motif has no 'rhythm' field"
            )

    # ── Convenience helpers ───────────────────────────────────────────────────

    def bars_list(self) -> list[float]:
        """Return per-chord bar durations (chord_bars takes precedence over bars)."""
        if self.chord_bars is not None:
            return [float(b) for b in self.chord_bars]
        bars = self.bars or 8.0
        even = bars / len(self.progression)
        return [even] * len(self.progression)

    def total_beats(self) -> float:
        return sum(b * self.beats_per_bar for b in self.bars_list())

    def to_dict(self) -> dict:
        """Serialise back to a plain dict compatible with the legacy generator."""
        return self.model_dump(exclude_none=True)


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

    name:   Optional[str]          = None
    key:    str                    = Field(min_length=1)
    mode:   str                    = Field(min_length=1)
    tempo:  TempoRangeModel

    motif:  Optional[MotifModel]       = None
    motifs: Optional[list[MotifModel]] = None

    @model_validator(mode="before")
    @classmethod
    def _warn_obsolete_theme_keys(cls, data: dict) -> dict:
        """
        Warn about known obsolete theme keys before field validation.
        Migrated from validate_piece() obsolete-key and prosodic-rhythm checks.
        """
        if not isinstance(data, dict):
            return data
        # Support both wrapped {"theme": {...}} and flat dict
        t = data.get("theme", data)
        for key in _OBSOLETE_THEME_KEYS:
            if key in t:
                warnings.warn(
                    f"theme has obsolete field '{key}' — remove it "
                    f"(instruments live in Logic)",
                    stacklevel=5,
                )
        return data

    @model_validator(mode="after")
    def _motif_consistency(self) -> "ThemeModel":
        """
        Migrated from validate_piece() motif/motifs consistency checks.
        No-motif case is a warning, not an error (generation still works).
        """
        if self.motif is None and self.motifs is None:
            warnings.warn(
                "theme has no motif or motifs defined — melodic identity "
                "will be purely generative",
                stacklevel=4,
            )
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
    - Song form:      a ``dict[str, SectionModel]``

    We disambiguate in ``_unwrap_nested_and_sections`` before Pydantic sees
    the fields, populating either ``sections`` or ``song_sections``.
    """
    model_config = ConfigDict(extra="allow", populate_by_name=True)

    title:     Optional[str] = None
    tempo:     Optional[Annotated[int, Field(ge=20, le=300)]] = None
    seed:      int = 42

    form_type: Literal["narrative", "song"] = "narrative"

    # Narrative form
    sections:      Optional[list[SectionModel]]          = None
    # Song form
    song_sections: Optional[dict[str, SectionModel]]     = None
    form:          Optional[list[Union[SongFormEntryModel, str]]] = None

    transform_sequence: Optional[list[TransformLiteral]] = None

    @model_validator(mode="before")
    @classmethod
    def _unwrap_nested_and_sections(cls, data: dict) -> dict:
        """
        1. Accept both {"piece": {...}} and flat dict forms.
        2. Disambiguate sections list vs dict into separate fields.
        """
        if "piece" in data and isinstance(data["piece"], dict):
            data = data["piece"]
        else:
            data = dict(data)

        raw_sections = data.get("sections")
        if isinstance(raw_sections, dict):
            data["song_sections"] = raw_sections
            data.pop("sections", None)

        return data

    @model_validator(mode="after")
    def _form_consistency(self) -> "PieceModel":
        """
        Structural form validation.
        Migrated from validate_piece() song/narrative form checks, including
        the form-array → section-name resolution check.
        """
        if self.form_type == "song":
            if not self.form:
                raise ValueError("form_type='song' requires a 'form' array")
            if not self.song_sections:
                raise ValueError(
                    "form_type='song' requires a 'sections' dict of named "
                    "section definitions"
                )
            for entry in self.form:
                name = entry if isinstance(entry, str) else entry.section
                if name not in (self.song_sections or {}):
                    raise ValueError(
                        f"form references undefined section '{name}'"
                    )
        else:
            if not self.sections:
                raise ValueError("Narrative piece must have a non-empty 'sections' list")
        return self

    @model_validator(mode="after")
    def _validate_transform_sequence(self) -> "PieceModel":
        """
        Warn when transform_sequence is shorter than the section count.
        TransformLiteral on the field catches invalid transform names at parse time.
        Migrated from validate_piece() transform_sequence block.
        """
        if self.transform_sequence is None:
            return self
        n_sections = (
            len(self.form or [])
            if self.form_type == "song"
            else len(self.sections or [])
        )
        if len(self.transform_sequence) < n_sections:
            warnings.warn(
                f"transform_sequence has {len(self.transform_sequence)} entries "
                f"but piece has {n_sections} sections — "
                f"sequence wraps (repeats from start)",
                stacklevel=4,
            )
        return self

    def validate_against_theme(self, theme_model: ThemeModel) -> None:
        """
        Run cross-model checks that require both piece and theme.
        Call this after ThemeModel.model_validate() and PieceModel.model_validate()
        both succeed.

        Also warns if piece has no tempo and theme has no tempo — this was a
        [WARN] in validate_piece() that can't live in a single-model validator.
        """
        if self.tempo is None:
            # Can't check theme.tempo here (TempoRangeModel always validates),
            # but the midpoint fallback in generate_piece() handles the None case.
            warnings.warn(
                "piece has no explicit 'tempo' — will use theme midpoint",
                stacklevel=3,
            )
        for section in self.iter_sections():
            section.validate_against_theme(theme_model)

    def iter_sections(self) -> list[SectionModel]:
        """
        Return sections in generation order for both form types.
        For song form this is the expanded play order (before _apply_variation).
        """
        if self.form_type == "narrative":
            return self.sections or []
        result = []
        for entry in (self.form or []):
            name = entry if isinstance(entry, str) else entry.section
            defn = (self.song_sections or {}).get(name)
            if defn is None:
                raise ValueError(f"Song form references undefined section '{name}'")
            result.append(defn)
        return result
