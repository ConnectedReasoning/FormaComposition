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
        VoiceRegisterLiteral,
        VALID_DENSITY, VALID_MELODY_BEH, VALID_BASS_STYLE, VALID_ARC,
        VALID_RHYTHM_SOURCE, VALID_HARMONY_RHYTHM_SOURCE, VALID_TRANSFORMS,
    )
"""

from __future__ import annotations

import math
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

DensityLiteral     = Literal["low", "sparse", "medium", "full"]
MelodyLiteral      = Literal["lyrical", "generative", "sparse", "develop"]
BassStyleLiteral   = Literal[
    "root_fifth", "walking", "pedal", "root_only",
    "melodic", "steady", "pulse", "motif",
]
ArcLiteral         = Literal[
    "swell", "fade", "build", "plateau", "decay",
    "fade_in", "fade_out", "breath",
]
RhythmSourceLiteral        = Literal["motif", "pattern", "free"]
# "motif" was retired from harmony_rhythm.rhythm for one release (2026-07)
# because the old implementation never built independent harmony content:
# it silently borrowed melody's motif rhythm verbatim (filtered to
# "stressed" onsets) and ignored this block's own density/groove fields,
# since _motif_rhythm_to_events took neither.
#
# Reintroduced (2026-07, same release) as a real, independent mechanism:
#   - harmony_rhythm.motif names its own motif (string ref or embedded
#     dict), independent of melody's. Omitted -> falls back to the
#     section's active theme motif, same as before this field existed.
#   - The motif's rhythm cell is tiled across the WHOLE SECTION as one
#     continuous onset stream, then sliced per chord window (see
#     generator.py's _enrich_chords_with_rhythm / strategies.py
#     _MotifHarmonyStrategy) -- so the comping pattern keeps its own
#     life independent of chord-change points, instead of resetting at
#     every chord like a per-chord retile would.
#   - density is honored for real this time: it selects the onset
#     articulation (full / stressed / anchor -- the same subsetting
#     _motif_rhythm_to_events already does for melody/bass motif
#     rhythm), so "sparse" thins the comping pattern and "full" plays
#     every onset.
#   - groove remains intentionally inert here, same as it already is for
#     melody's "motif" rhythm source: the motif cell IS the rhythm, there
#     is no grid for a groove to shape. lint.py flags harmony_rhythm.groove
#     set alongside rhythm="motif" as a no-op rather than leaving it silent.
HarmonyRhythmSourceLiteral = Literal["pattern", "sustain", "free", "motif"]
TransformLiteral   = Literal[
    "original", "inversion", "retrograde", "retrograde_inversion",
    "augmentation", "diminution", "transpose_up", "transpose_down",
    "shuffle", "expand", "compress", "sequence",
]
CounterpointSpeciesLiteral  = Literal["free", "first", "second", "third", "fourth", "fifth"]
CounterpointRegisterLiteral = Literal["above", "below"]
DissonanceLiteral           = Literal["none", "passing", "neighbor", "free"]
VoiceRegisterLiteral        = Literal[
    # Traditional SATB(+baritone) names (canonical, preferred)
    "soprano", "alto", "tenor", "baritone", "bass",
    # Legacy register names — kept as aliases so existing pieces validate
    "high", "mid", "low_mid", "low",
    # Counterpoint-relative aliases (resolved against the lead voice)
    "above", "below",
]

# Absolute (bottom, top) MIDI bounds per register name. Widened 2026-07 from
# the original choir-SATB tessitura (~21 semitones each) to a full 2-octave
# span per voice: real instruments have far more usable range than a human
# voice part, and the tighter bands were visibly clipping both ends once
# melodic content actually used the space (measured: 31% of notes sitting
# at the tenor floor on a real develop-behavior line, dropping to 20% at
# these wider bounds — floor-clustering itself is a separate, deeper
# mechanism, see generate_develop's anchor carry-forward; widening reduces
# how often it triggers but doesn't remove the mechanism). Anchored on
# clean C/G note names, alternating by a fifth going down, so they're easy
# to reason about and still overlap generously at the seams (~1.5 octaves)
# for real multi-voice writing. Legacy aliases updated to match.
# 'above'/'below' are intentionally absent — they are relative, not
# absolute, and resolved by the generator against the lead voice.
REGISTER_BOUNDS: dict[str, tuple[int, int]] = {
    # Traditional SATB + baritone (canonical) — each a full 2 octaves
    "soprano":  (60, 84),   # C4–C6
    "alto":     (55, 79),   # G3–G5
    "tenor":    (48, 72),   # C3–C5
    "baritone": (43, 67),   # G2–G4
    "bass":     (36, 60),   # C2–C4
    # Legacy aliases (widened to match their SATB equivalents)
    "high":     (64, 88),   # E4–E6
    "mid":      (60, 84),   # C4–C6  (== soprano)
    "low_mid":  (48, 72),   # C3–C5  (== tenor)
    "low":      (33, 57),   # A1–A3
}

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
        if self.velocities is not None:
            bad = [v for v in self.velocities if not (0.0 <= v <= 1.0)]
            if bad:
                raise ValueError(
                    f"rhythm_pattern: velocities must be 0.0-1.0 scale multipliers "
                    f"(they're multiplied directly into a base MIDI velocity downstream), "
                    f"got out-of-range value(s) {bad}. If you meant raw MIDI velocities "
                    f"(0-127), divide by 127 first — e.g. 0.8 instead of 80 or 102."
                )
        return self

class HarmonyRhythmModel(BaseModel):
    """
    Corresponds to section["harmony_rhythm"] block.

    ``rhythm`` is Optional: existing compositions may omit it and supply only
    density/groove overrides; the factory cascades:
    harmony_rhythm.rhythm -> section.rhythm -> "free".

    ``note_duration`` was removed (2026-07): it was schema-legal but consumed
    nowhere in the harmony path, so setting it silently did nothing. Chord
    length comes from the rhythm source ("sustain" holds the harmonic span;
    "motif" takes durations from the motif cell). extra="forbid" now rejects
    it loudly instead of lying.

    ``motif`` (string library reference or embedded dict) names harmony's
    own motif when ``rhythm == "motif"``. Omitted -> falls back to the
    section's active theme motif. Ignored (see lint.py) when rhythm isn't
    "motif" -- there's nothing for it to feed.
    """
    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    rhythm:        Optional[HarmonyRhythmSourceLiteral] = None
    density:       Optional[DensityLiteral]             = None
    groove:        Optional[str]                        = None
    motif:         Optional[Union[str, dict]]            = None
    # 0.0 = off, 1.0 = heaviest swing. Internally remapped via
    # rhythm.remap_swing_ratio() before use — do not confuse with the
    # 0.5-straight scale apply_swing()/_apply_swing_to_drums() consume.
    swing:         Annotated[float, Field(ge=0.0, le=1.0)] = 0.0

class NoteLengthRangeModel(BaseModel):
    """
    Decouples note length from density for melody / free-species counterpoint.

    When present on a section (or a counterpoint voice), note durations are
    sampled freely within [min, max] beats instead of being pinned to the
    density grid. Density still controls how busy the line is (rest frequency);
    this controls only how long each note is. The two become independent axes.

    Applies to melody and free-species counterpoint only — harmony and bass
    stay grid-disciplined by design. Ignored when a groove is set (groove
    fully specifies durations) or when the section's rhythm source is
    "pattern"/"motif" (those supply their own onset grid). The lint surfaces
    both no-op cases.

    quantum snaps sampled lengths to a grid so they stay legible in the DAW:
    0.5 = eighth-legible, 0.25 = sixteenth (default), smaller = more fluid.
    """
    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    min:     Annotated[float, Field(gt=0.0)]
    max:     Annotated[float, Field(gt=0.0)]
    quantum: Annotated[float, Field(gt=0.0)] = 0.25

    @model_validator(mode="after")
    def _check_bounds(self) -> "NoteLengthRangeModel":
        if self.max < self.min:
            raise ValueError(
                f"note_length_range.max ({self.max}) must be >= min ({self.min})"
            )
        return self

    def as_tuple(self) -> tuple[float, float]:
        return (self.min, self.max)

class CounterpointModel(BaseModel):
    """Corresponds to section["counterpoint"] block."""
    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    species:      CounterpointSpeciesLiteral  = "free"
    cp_register:  CounterpointRegisterLiteral = Field(default="below", alias="register")
    dissonance:   DissonanceLiteral           = "passing"
    velocity:     Annotated[int, Field(ge=1, le=127)] = 58
    canon_offset: Annotated[float, Field(ge=0.0)]     = 0.0

    # Rhythmic independence (free species only — see counterpoint.py).
    # "first" species stays note-against-note with the cantus firmus by
    # classical convention regardless of these fields.
    rhythm_density: Literal["sparse", "medium", "full"] = "medium"
    groove:         Optional[str]                       = None
    # Per-voice note-length range override (free species only). When set, this
    # voice samples its durations in-range independently of the section-level
    # setting; when None it inherits the section's note_length_range (if any).
    note_length_range: Optional[NoteLengthRangeModel]   = None

class VoiceModel(BaseModel):
    """
    A single peer voice in the voices array (or the lead voice, if given as
    a dict in section.melody instead of a bare behavior string).

    When ``species`` is present, the voice is generated by counterpoint.py
    (consonance scoring, voice-leading rules).  When absent, it is generated
    by melody.py (behavior-driven generative / lyrical / develop / sparse).

    Each voice is fully independent: its own register and velocity.  The
    engine generates them sequentially; each voice reads the snapshots of
    all previously generated voices so it can avoid collisions.

    2026-07 history: an earlier revision carried ``motif`` and ``rhythm``
    fields, but neither was ever actually read by the generator for peer
    voices — they validated cleanly and did nothing, so they were removed
    rather than left as dead weight (same silent-gap pattern found and
    fixed elsewhere in this engine; see the harmony-motif retirement note
    on HarmonyRhythmSourceLiteral). ``rhythm`` stays removed — still
    unconsumed. ``motif`` is reinstated here, properly wired this time:
    the LEAD voice's ``motif`` (section.melody given in dict form, or
    voices[0]) overrides the theme's motif for melody generation only —
    see generator.py's melody_motif_def resolution. It is a string
    (library reference) or an embedded dict; omitted -> falls back to the
    theme's motif, zero extra effort. Non-lead peer voices may still set
    it schema-legally but it is currently only consumed for the lead
    voice — see lint.py's _check_voice_motif for the pitch-shaping gate
    (behavior must be "develop") that applies regardless of voice position.

    ``register`` maps to MIDI pitch ranges — see REGISTER_BOUNDS above.
    ``above`` / ``below`` are relative aliases accepted for counterpoint compat.
    """
    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    v_register: VoiceRegisterLiteral = Field(default="mid", alias="register")
    behavior:   MelodyLiteral                               = "lyrical"
    velocity:   Annotated[int, Field(ge=1, le=127)]         = 64

    # Independent per-voice motif override (string ref or embedded dict).
    # See class docstring — currently wired for the lead voice only.
    motif:      Optional[Union[str, dict]]                   = None

    # Species — present → counterpoint.py path; absent → melody.py path.
    # Confirmed working end-to-end (chord-aware consonance filtering,
    # canon_offset, per-voice dissonance) — kept as-is, unlike motif/rhythm.
    species:    Optional[CounterpointSpeciesLiteral]        = None
    dissonance: DissonanceLiteral                           = "passing"
    canon_offset: Annotated[float, Field(ge=0.0)]           = 0.0

    # Per-voice rest probability (overrides section default when set)
    rest_probability: Optional[Annotated[float, Field(ge=0.0, le=1.0)]] = None

    def bounds(self) -> "Optional[tuple[int, int]]":
        """
        Absolute (bottom, top) MIDI range for this voice's register, or None
        for the counterpoint-relative aliases ('above'/'below'), which have
        no fixed band — they position relative to the lead voice and are
        resolved by the generator, not here.
        """
        return REGISTER_BOUNDS.get(self.v_register)

    def is_relative(self) -> bool:
        """True for 'above'/'below' — positioned relative to the lead voice."""
        return self.v_register in ("above", "below")

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
    rests:          Optional[list[bool]]   = None
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
        if self.rhythm is not None and self.rests is not None:
            if len(self.rests) != len(self.rhythm):
                raise ValueError(
                    f"motif '{self.name}': rests length ({len(self.rests)}) "
                    f"must match rhythm length ({len(self.rhythm)}) — each rhythm "
                    f"slot needs exactly one corresponding rests entry (true/false)."
                )
        if self.velocities is not None:
            bad = [v for v in self.velocities if not (0.0 <= v <= 1.0)]
            if bad:
                raise ValueError(
                    f"motif '{self.name}': velocities must be 0.0-1.0 scale "
                    f"multipliers, not raw MIDI values — they're multiplied directly "
                    f"into a voice's base velocity (e.g. bass: int(velocity * "
                    f"velocity_scale)) with no clamp before the chosen value, so "
                    f"velocities authored on a 0-127 scale silently overflow into "
                    f"invalid MIDI bytes downstream. Got out-of-range value(s) {bad} "
                    f"— if these were meant as raw MIDI velocities, divide by 127 "
                    f"first (e.g. 0.8 instead of 80 or 102)."
                )
        return self

# ═══════════════════════════════════════════════════════════════════════════════
# SectionModel
# ═══════════════════════════════════════════════════════════════════════════════

def _resolve_motif_value_safe(value: Optional[Union[str, dict]]):
    """
    Resolve a voice/harmony_rhythm motif override value (string ref or
    embedded dict) for cross-model validation in SectionModel.
    validate_against_theme. Wraps motif_loader errors (bad name, malformed
    file) into ValueError so a bad override surfaces with the same
    exception type as every other check in that method, rather than a bare
    FileNotFoundError bubbling up from a different module.

    Returns None for a None value — that's the "not overridden, fall back
    to the theme" case, not an error.
    """
    if value is None:
        return None
    from intervals.core.motif_loader import resolve_motif_value
    try:
        return resolve_motif_value(value)
    except (FileNotFoundError, ValueError, TypeError) as exc:
        raise ValueError(f"could not resolve motif override: {exc}") from exc

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

    # ── Identity ──────────────────────────────────────────────────────────────
    name:          Optional[str] = None

    # ── Section-level key / mode override (falls back to theme if absent) ─────
    key:  Optional[str] = None
    mode: Optional[str] = None

    # ── Section-level motif override (falls back to theme pool if absent) ─────
    # Accepts a motif name (str), embedded dict, or a list of either.
    # A single value is treated as the sole motif for this section.
    # A list restricts the pool to exactly those motifs.
    motif:  Optional[Union[str, dict]] = None
    motifs: Optional[list[Union[str, dict]]] = None

    # ── Harmony / progression ─────────────────────────────────────────────────
    progression:   list[str]          = Field(min_length=1)
    chord_bars:    Optional[list[float]] = None
    bars:          Optional[float]       = None
    beats_per_bar: int = Field(default=4, ge=1, le=16)

    # ── Density / behaviour ───────────────────────────────────────────────────
    density:    DensityLiteral   = "medium"
    # Bare string (legacy): "generative", "lyrical", etc. — behavior only,
    # default 'mid' register (60-81). Dict form: same shape as a voices[]
    # entry ({behavior, register, velocity, ...}) — lets the lead line get
    # an explicit register without needing the full voices array wrapper.
    melody:     Union[MelodyLiteral, "VoiceModel"]    = "generative"
    bass_style: BassStyleLiteral = "root_fifth"
    arc:        ArcLiteral       = "swell"

    # ── Rhythm ────────────────────────────────────────────────────────────────
    rhythm:          RhythmSourceLiteral                    # required, no default
    harmony_rhythm:  Optional[HarmonyRhythmModel] = None
    rhythm_pattern:  Optional[RhythmPatternModel] = None
    harmony_pattern: Optional[RhythmPatternModel] = None

    groove: Optional[str]                                = None
    # 0.0 = off, 1.0 = heaviest swing — see HarmonyRhythmModel.swing comment
    # and rhythm.remap_swing_ratio() for the internal conversion.
    swing:  Annotated[float, Field(ge=0.0, le=1.0)]     = 0.0

    # ── Melody tuning ─────────────────────────────────────────────────────────
    rest_probability: Annotated[float, Field(ge=0.0, le=1.0)] = 0.0
    fugal_techniques: Optional[dict]                            = None

    # Note-length range (melody + free-species counterpoint). Decouples note
    # length from density: when set, durations are sampled in [min, max] beats
    # and density governs only rest frequency. Applies to ALL melody behaviors
    # (lyrical/generative/sparse/develop) since it operates at the rhythm layer
    # below behavior. Harmony/bass are untouched by design. No-op under a groove
    # or a "pattern"/"motif" rhythm source (lint flags both).
    note_length_range: Optional[NoteLengthRangeModel]           = None

    # ── Per-voice rest probability (independent of melody rest_probability) ────
    # These thin the harmony bed and bass line respectively. They are NOT
    # coupled to melody rest_probability: the common ambient case is a
    # continuous pad + steady bass under a melody that leaves space, which a
    # single shared knob cannot express. Both default off.
    #   harmony_rest_probability: no-op on the "sustain" harmony source and on
    #     any single-onset chord window (a rest roll there would delete the
    #     whole chord, not thin it). Only thins multi-onset windows.
    #   bass_rest_probability: ignored (with a warning) for the "walking" and
    #     "melodic" styles, whose lines depend on stepwise continuity — random
    #     drops break the line rather than add breath.
    harmony_rest_probability: Annotated[float, Field(ge=0.0, le=1.0)] = 0.0
    bass_rest_probability:    Annotated[float, Field(ge=0.0, le=1.0)] = 0.0

    # ── Optional voices ───────────────────────────────────────────────────────
    counterpoint: Optional[list[CounterpointModel]] = None
    voices:       Optional[list[VoiceModel]]  = None   # peer voices (replaces melody+counterpoint)
    drums:        Optional[DrumModel]         = None
    percussion:   Optional[dict]              = None   # future-proofed, untyped

    # ── Free-form documentation ───────────────────────────────────────────────
    notes: Optional[str] = None

    # ─────────────────────────────────────────────────────────────────────────
    # Field coercions (mode="before")
    # ─────────────────────────────────────────────────────────────────────────

    @field_validator("progression", mode="before")
    @classmethod
    def _validate_progression_tokens(cls, v):
        if v is None:
            return v
        for entry in v:
            if isinstance(entry, str) and "," in entry:
                raise ValueError(
                    f"progression entry {entry!r} contains a comma. A chord "
                    f"symbol never legitimately contains one — this almost "
                    f"always means several chords were written as a single "
                    f"comma-separated string inside one array element "
                    f"(e.g. [\"ii, v, i\"]) instead of separate elements "
                    f"([\"ii\", \"v\", \"i\"]). The single-string form parses "
                    f"silently as just the first chord, with every chord "
                    f"after the comma discarded — no error, no chord "
                    f"changes, and no clue why. Split it into separate "
                    f"array elements."
                )
        return v

    @field_validator("key", mode="before")
    @classmethod
    def _validate_section_key(cls, v):
        if v is None:
            return v
        VALID_KEYS = {
            "C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B",
            "Db", "Eb", "Gb", "Ab", "Bb",
        }
        if v not in VALID_KEYS:
            raise ValueError(f"Section key '{v}' is not a valid note name.")
        return v

    @field_validator("mode", mode="before")
    @classmethod
    def _validate_section_mode(cls, v):
        if v is None:
            return v
        VALID_MODES = {"ionian", "dorian", "phrygian", "lydian", "mixolydian", "aeolian", "locrian"}
        if v.lower() not in VALID_MODES:
            raise ValueError(f"Section mode '{v}' is not valid. Choose from {sorted(VALID_MODES)}.")
        return v.lower()

    @field_validator("counterpoint", mode="before")
    @classmethod
    def _coerce_counterpoint(cls, v):
        """
        Accept the legacy bare-object form ("counterpoint": {...}) and
        normalise it to a one-item list, so every existing composition
        file keeps validating unchanged. New compositions may instead
        supply a list directly for 2-3 independent counterpoint voices.
        """
        if v is None:
            return v
        if isinstance(v, dict):
            return [v]
        return v

    @field_validator("counterpoint", mode="after")
    @classmethod
    def _validate_counterpoint_count(cls, v):
        """Cap at three independent counterpoint voices (practical/audible limit)."""
        if v is not None and len(v) > 3:
            raise ValueError(
                f"counterpoint supports at most 3 voices, got {len(v)}"
            )
        return v

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
        Warn about section keys this model doesn't declare — typos, or keys
        from an older schema version. Uses warnings.warn so generation
        continues; these are [WARN]-level issues, not errors.

        `model_extra` is exactly the set we want: because model_config is
        extra="allow", Pydantic binds every declared field itself and leaves
        only unrecognised keys here. So the field list IS the known-key list —
        no separate roster to hand-maintain, and no way for a newly added
        field to be flagged by mistake.
        """
        unknown = set(self.model_extra or {})
        if unknown:
            warnings.warn(
                f"Section '{self.name}': unknown field(s) {sorted(unknown)} — "
                f"possible typo or obsolete key.",
                stacklevel=4,
            )
        return self

    @model_validator(mode="after")
    def _validate_bars(self) -> "SectionModel":
        """
        Migrated from validate_piece() bar/chord_bars checks, extended with
        cell-tiling: chord_bars + progression can describe one short cycle
        (a "cell") that repeats to fill `bars`, rather than the complete,
        one-entry-per-chord sequence for the whole section.

        Which mode is in effect is inferred, not declared: if the cell's own
        total is shorter than `bars`, it's a cell meant to repeat — bars is
        left as authored (it's the tiled *total*, not a mismatch to resolve).
        Otherwise this is the original behavior: chord_bars is the complete
        sequence, and it wins outright over `bars` (with a warning if they
        disagree). No new field needed to distinguish the two: a cell must be
        shorter than bars to tile, and a complete sequence is never shorter
        than the total it's describing, so the two cases can't collide.

        Tiling requires an exact whole-number fit — no partial final cycle —
        and fails loudly with the nearest valid bar counts if it doesn't.
        """
        if self.chord_bars is not None:
            if len(self.chord_bars) != len(self.progression):
                raise ValueError(
                    f"chord_bars has {len(self.chord_bars)} entries but "
                    f"progression has {len(self.progression)} chords"
                )
            cell_bars = sum(self.chord_bars)

            if self.bars is not None and cell_bars < self.bars - 0.01:
                # Tiling case: this is a cell, not the whole thing.
                reps = self.bars / cell_bars
                rounded = round(reps)
                if rounded < 1 or abs(rounded * cell_bars - self.bars) > 0.01:
                    lo = math.floor(reps) * cell_bars
                    hi = math.ceil(reps) * cell_bars
                    raise ValueError(
                        f"Section '{self.name}': chord_bars cell totals "
                        f"{cell_bars:g} bars ({len(self.chord_bars)} chords) "
                        f"but bars={self.bars:g} is not a whole multiple of "
                        f"it ({reps:.3f} cycles). Nearest exact fits: "
                        f"bars={lo:g} ({math.floor(reps):g} cycles) or "
                        f"bars={hi:g} ({math.ceil(reps):g} cycles)."
                    )
                # bars stays as authored — it's the tiled total, not a
                # mismatch. resolved_progression()/bars_list() do the tiling.

            else:
                # Original behavior: chord_bars is the complete sequence.
                derived = cell_bars
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

        Raises ValueError if rhythm='motif' but neither the theme nor the
        relevant independent override (voice.motif / harmony_rhythm.motif)
        supplies a motif rhythm. Call PieceModel.validate_against_theme(
        theme_model) to run this for every section at once.
        """
        primary = theme_model.primary_motif
        theme_has_rhythm = primary is not None and primary.rhythm is not None
        label = self.name or "?"

        lead = self.lead_voice()
        voice_motif_value    = lead.motif if lead is not None else None
        harmony_motif_value  = (
            self.harmony_rhythm.motif if self.harmony_rhythm is not None else None
        )
        voice_motif    = _resolve_motif_value_safe(voice_motif_value)
        harmony_motif  = _resolve_motif_value_safe(harmony_motif_value)
        voice_has_rhythm   = voice_motif is not None and voice_motif.rhythm is not None
        harmony_has_rhythm = harmony_motif is not None and harmony_motif.rhythm is not None

        if self.rhythm == "motif" and not theme_has_rhythm and not voice_has_rhythm:
            raise ValueError(
                f"Section '{label}': rhythm='motif' but neither the theme's "
                f"primary motif nor the lead voice's own 'motif' override "
                f"has a 'rhythm' field"
            )
        if (
            self.harmony_rhythm is not None
            and self.harmony_rhythm.rhythm == "motif"
            and not theme_has_rhythm
            and not harmony_has_rhythm
        ):
            raise ValueError(
                f"Section '{label}': harmony_rhythm.rhythm='motif' but "
                f"neither the theme's primary motif nor harmony_rhythm's "
                f"own 'motif' override has a 'rhythm' field"
            )

        # Any of these three consume the theme's motif rhythm directly, whether
        # or not the section's own `rhythm` field says "motif" — bass_style
        # "motif" reads the theme's motif independently of the section's
        # rhythm source, and harmony_rhythm has its own separate switch.
        # (bass never reads voice.motif / harmony_rhythm.motif — those two
        # overrides are melody- and harmony-scoped only — so bass_style
        # "motif" is checked against the theme pool exclusively, same as
        # before this feature existed.)
        uses_motif_rhythm = (
            self.rhythm == "motif"
            or (self.harmony_rhythm is not None and self.harmony_rhythm.rhythm == "motif")
            or self.bass_style == "motif"
        )
        if uses_motif_rhythm:
            # NOTE: section-level `motif`/`motifs` overrides are documented as
            # restricting the pool for this section, but generator.py's actual
            # motif resolution never reads them — only the theme's pool is
            # ever consulted at render time. Checking against the theme's pool
            # here matches what will actually happen, not what the schema
            # implies should happen.
            candidates = list(theme_model.motifs) if theme_model.motifs else (
                [theme_model.motif] if theme_model.motif else []
            )
            for m in candidates:
                if m is None:
                    continue
                self._check_bar_alignment(m.name, m.rhythm, label)

        # Independent per-voice / per-harmony motif rhythm-alignment checks.
        # A voice or harmony_rhythm that names its own motif (rather than
        # falling back to the theme's) can have a rhythm cell whose own
        # total doesn't line up with the bar either — same failure mode as
        # the theme-pool loop above, just against a different motif source,
        # and one the loop above can't see since it only reads the theme.
        if voice_motif is not None:
            self._check_bar_alignment(voice_motif.name, voice_motif.rhythm, label, where="voice.motif")
        if harmony_motif is not None:
            self._check_bar_alignment(harmony_motif.name, harmony_motif.rhythm, label, where="harmony_rhythm.motif")

    def _check_bar_alignment(
        self,
        motif_name: Optional[str],
        motif_rhythm: Optional[list[float]],
        label: str,
        where: str = "motif",
    ) -> None:
        """
        Shared by the theme-pool loop and the independent voice/harmony
        motif checks in validate_against_theme — raises if a motif's
        rhythm cell total isn't a whole multiple of beats_per_bar.
        """
        if motif_rhythm is None:
            return
        total = sum(motif_rhythm)
        remainder = total % self.beats_per_bar
        if remainder > 1e-6 and abs(remainder - self.beats_per_bar) > 1e-6:
            raise ValueError(
                f"Section '{label}': {where} '{motif_name or '?'}' has a rhythm "
                f"totaling {total:g} beats, which is not a whole multiple "
                f"of this section's beats_per_bar ({self.beats_per_bar}). "
                f"{total:g} / {self.beats_per_bar} = {total / self.beats_per_bar:g}. "
                f"A motif cycle that doesn't line up with the bar means its "
                f"phase drifts relative to the barline on every repeat — "
                f"extend or trim the motif's rhythm so its total is a clean "
                f"multiple of {self.beats_per_bar}."
            )

    # ── Convenience helpers ───────────────────────────────────────────────────

    def _progression_cycles(self) -> int:
        """
        How many times the (progression, chord_bars) cell repeats to fill
        `bars`. Always 1 except in the tiling case — a chord_bars cell whose
        own total is shorter than `bars` — which _validate_bars has already
        confirmed divides evenly, so this is a plain, safe division.
        """
        if self.chord_bars is None or self.bars is None:
            return 1
        cell_bars = sum(self.chord_bars)
        if cell_bars >= self.bars - 0.01:
            return 1
        return round(self.bars / cell_bars)

    def lead_voice(self) -> "Optional[VoiceModel]":
        """
        The lead voice as a VoiceModel, from whichever of the two places it
        was actually specified: section.voices[0] takes precedence (true
        multi-voice section); otherwise section.melody, but only if it was
        given in dict form (a bare behavior string carries no register, so
        there's no VoiceModel to return — None means "use the old default
        wide range", not "no melody").
        """
        if self.voices:
            return self.voices[0]
        if isinstance(self.melody, VoiceModel):
            return self.melody
        return None

    def melody_behavior(self) -> str:
        """
        The lead voice's behavior as a plain string, regardless of whether
        section.melody was given as a bare string or a dict, and regardless
        of whether section.voices is in use instead. Use this instead of
        reading .melody directly wherever a plain MelodyLiteral is needed.
        """
        if self.voices:
            return self.voices[0].behavior
        if isinstance(self.melody, VoiceModel):
            return self.melody.behavior
        return self.melody

    def resolved_progression(self) -> list[str]:
        """
        progression, tiled to match bars_list() when chord_bars describes a
        shorter repeating cell rather than the section's complete sequence.
        Callers building chords from `progression` should use this instead of
        the raw field whenever they also consume bars_list() — the two must
        stay the same length, one entry per chord.
        """
        return list(self.progression) * self._progression_cycles()

    def bars_list(self) -> list[float]:
        """
        Return per-chord bar durations (chord_bars takes precedence over
        bars). Tiled to fill `bars` when chord_bars is a shorter repeating
        cell (see _progression_cycles) — length always matches
        resolved_progression().
        """
        if self.chord_bars is not None:
            return [float(b) for b in self.chord_bars] * self._progression_cycles()
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

    section:      str
    exact_repeat: bool = False

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
        For song form this is the expanded play order: each `form` entry
        resolved to its section definition, in sequence. Repeated entries
        resolve to the same definition — they diverge at generation time via
        per-repetition seed offsetting (see generator.py), not here.
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
