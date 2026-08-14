"""
schemas.py — Pydantic v2 models for FormaComposition input validation.

Single source of truth for all structural and enum-based validation.
``validate_piece()`` in generator.py has been retired; call
``PieceModel.model_validate(piece)`` instead.

Validation hierarchy:
    PieceModel
    ├── SectionModel          (narrative: list of these)
    │   ├── HarmonyRhythmModel
    │   ├── CounterpointModel
    │   ├── RhythmPatternModel
    │   └── DrumModel
    └── SongFormEntryModel    (song form: form array entries)

MotifModel covers the theme side (motif/motifs). ThemeModel has been
retired — its fields (name, key, mode, tempo, motif, motifs) are absorbed
directly into PieceModel: theme is merged into piece now (single-file
format, one JSON per piece instead of a paired theme.json + piece.json).

Usage
-----
    from intervals.core.schemas import PieceModel, SectionModel

    piece = PieceModel.model_validate(raw_piece_dict)
    piece.validate_against_theme(piece)   # self-check: rhythm-source
                                           # prerequisites against the
                                           # piece's own motif/motifs

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
# Grooves are a fixed onset-accent vocabulary defined in rhythm.py's GROOVES
# dict (verified against source 2026-07). groove was previously plain str
# at all four of its locations (section, harmony_rhythm, counterpoint,
# drums) — schema-legal for any typo, only caught (as "Unknown groove:
# '...'") deep in rhythm.py at render time. Literal-typing it here closes
# that gap the same way every other music-vocabulary field in this file
# already is; keep this list in sync with rhythm.py's GROOVES keys by hand
# (no import — schemas.py doesn't depend on the render modules, matching
# this file's existing direction of dependency).
GrooveLiteral = Literal[
    "straight", "push", "backbeat", "syncopated", "halftime",
    "shuffle", "broken", "clave", "waltz", "offbeat", "driving",
]
# Same story for drums.pattern — plain str, schema-legal for a typo,
# caught only as "Unknown drum pattern: '...'" at render time in
# percussion.py. Keep in sync with percussion.py's DRUM_PATTERNS keys.
DrumPatternLiteral = Literal[
    "four_on_floor", "backbeat", "halftime", "minimal", "sideclick",
]
VoiceRegisterLiteral        = Literal[
    # Traditional SATB(+baritone) names (canonical, preferred)
    "soprano", "alto", "tenor", "baritone", "bass",
    # Legacy register names — kept as aliases so existing pieces validate
    "high", "mid", "low_mid", "low",
    # Counterpoint-relative aliases (resolved against the lead voice)
    "above", "below",
]

# Absolute (bottom, top) MIDI bounds per register name. 18-semitone span (an
# octave + a sixth) per voice, centered on the same pitch each name has
# always centered on. Previously a full 24-semitone (2-octave) span; that
# width was what let melody hit both walls in essentially every render
# (measured: register span == exactly 24 semitones in 61 of 71 catalog
# renders) — pitch selection samples close to uniformly across whatever box
# it's given (motif_to_notes octave-folds into [octave_bottom, octave_top]
# with no center-weighting), so the box's width IS the piece's effective
# melodic range, not a ceiling that's rarely touched. Narrowing directly
# caps that. Centers are unchanged from the original 24-semitone version, so
# nothing shifted relative to another voice's center — soprano is still
# centered on C5, tenor still on C4, etc. — only each wall moved 3
# semitones closer to its own center.
REGISTER_BOUNDS: dict[str, tuple[int, int]] = {
    # Traditional SATB + baritone (canonical) — 18 semitones, same centers
    "soprano":  (63, 81),   # D#4–A5, centered C5
    "alto":     (58, 76),   # A#3–E5, centered G4
    "tenor":    (51, 69),   # D#3–A4, centered C4
    "baritone": (46, 64),   # A#2–E4, centered G3
    "bass":     (39, 57),   # D#2–A3, centered C3
    # Legacy aliases (same treatment, same centers as their SATB equivalents)
    "high":     (67, 85),   # G4–C#6, centered E5
    "mid":      (63, 81),   # D#4–A5, centered C5  (== soprano)
    "low_mid":  (51, 69),   # D#3–A4, centered C4  (== tenor)
    "low":      (36, 54),   # C2–F#3, centered A2
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
VALID_GROOVES                = set(get_args(GrooveLiteral))
VALID_DRUM_PATTERNS          = set(get_args(DrumPatternLiteral))

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
    groove:        Optional[GrooveLiteral]               = None
    motif:         Optional[Union[str, dict]]            = None
    # 0.0 = off, 1.0 = heaviest swing. Internally remapped via
    # rhythm.remap_swing_ratio() before use — do not confuse with the
    # 0.5-straight scale apply_swing()/_apply_swing_to_drums() consume.
    swing:         Annotated[float, Field(ge=0.0, le=1.0)] = 0.0

    # Item 17 / ST-5: harmony's motif rhythm used to tile the exact same
    # cell verbatim across a whole section -- untransformed clones, no
    # variation. Default (None): harmony picks its own transform each
    # repetition, independently, from the motif's transform_pool -- this is
    # "free imitation" in counterpoint-theory terms (voices vary
    # independently), so it needs no literal value of its own; absence
    # already means it. "strict" opts INTO "strict imitation" instead --
    # harmony inherits melody's transform choice each repetition and
    # reapplies it to its own comping shape, staying in lockstep.
    #
    # transform_ prefix is deliberate: this is scoped to which TRANSFORM got
    # picked, not a general "imitation" concept -- melody.py's unrelated
    # canonic_imitation (fugal_techniques, offset voice entries in time) is
    # a different mechanism in a different config surface entirely; the two
    # terms shouldn't be confused for each other.
    transform_imitation: Optional[Literal["strict"]] = None

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


class MelodicArcModel(BaseModel):
    """
    Apex/goal-tone phrase shaping. Optional; absent means no apex or
    cadence bias at all — every section without this field behaves
    exactly as before this feature existed. See melody.py's
    generate_lyrical/generate_generative/generate_sparse/generate_develop
    docstrings and melodic_shape.py for the full mechanism.

    apex_degree: 1-indexed scale degree the phrase builds toward (1 =
    tonic, 5 = dominant — matching how a composer actually talks about
    scale degrees, NOT the engine's internal 0-indexed convention;
    generator.py converts by subtracting 1 at the wiring boundary — see
    melodic_shape.py's module docstring on why that translation belongs
    here and not baked into the primitive itself). None (default): no
    apex bias, even if resolve_every_cycle is set — a melodic_arc block
    can enable cadence pull on its own, without a climax target.

    apex_position: 0.0-1.0, where in the section the peak should land.
    Defaults to 0.7, matching generate_lyrical/generate_generative's own
    default when this field is present but unset.

    resolve_every_cycle: Phase 0's cadence decision. False (default): a
    repeating progression only resolves once, at the section's true end
    — a vamp/loop that keeps its groove through every repeat, the way
    the "na-na-na" coda of "Hey Jude" rides an open vamp specifically so
    it can extend indefinitely. True: resolves at the end of EVERY
    progression cycle — a hook that lands every time it comes around,
    the way Depeche Mode's "Just Can't Get Enough" resolves its short
    repeating cell on every single pass. Both are real techniques, not
    one "correct" default with an edge-case toggle.

    Wired into all four melody behaviors (generative/lyrical/develop as
    of Phase 2-4, sparse as of Phase 5). One documented caveat: combined
    with `melody: "sparse"`, the effect is real and statistically
    measurable but was confirmed via direct listening comparison to be
    hard to perceive — sparse's wide-leap, low-density, long-silence
    character buries a slow directional trend in noise. Left wired as a
    genuine, deliberate choice rather than artificially strengthened for
    that one behavior, which would trade away some of sparse's actual
    unpredictable identity just to make the shape audible. Treat
    melodic_arc on a sparse section as a subtle structural nudge, not a
    foreground effect you should expect to hear clearly.
    """
    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    apex_degree:  Optional[int] = None
    apex_position: Annotated[float, Field(ge=0.0, le=1.0)] = 0.7
    resolve_every_cycle: bool = False


class CounterpointModel(BaseModel):
    """Corresponds to section["counterpoint"] block."""
    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    species:      CounterpointSpeciesLiteral  = "free"
    cp_register:  CounterpointRegisterLiteral = Field(default="below", alias="register")
    dissonance:   DissonanceLiteral           = "passing"
    velocity:     Annotated[int, Field(ge=1, le=127)] = 58
    canon_offset: Annotated[float, Field(ge=0.0)]     = 0.0

    @field_validator("species", mode="after")
    @classmethod
    def _validate_species_implemented(cls, v):
        """
        Only 'first' and 'free' species are implemented in counterpoint.py.
        'second'/'third'/'fourth'/'fifth' are schema-valid *names*
        (CounterpointSpeciesLiteral accepts all six) but raise ValueError
        ("Unknown species: ... Choose 'first' or 'free'.") the moment
        generate_counterpoint() runs — previously only surfaced as a
        non-blocking lint warning (_check_counterpoint_species_unimplemented),
        not caught at validation time. lint.py's check still runs — it just
        can no longer actually fire, since this now blocks first.
        """
        if v not in ("first", "free"):
            raise ValueError(
                f"species='{v}' is not implemented in counterpoint.py — "
                f"only 'first' and 'free' are. 'second'/'third'/'fourth'/"
                f"'fifth' are schema-valid names but raise ValueError at "
                f"render time."
            )
        return v

    # Rhythmic independence (free species only — see counterpoint.py).
    # "first" species stays note-against-note with the cantus firmus by
    # classical convention regardless of these fields.
    rhythm_density: Literal["sparse", "medium", "full"] = "medium"
    groove:         Optional[GrooveLiteral]              = None
    # Per-voice note-length range override (free species only). When set, this
    # voice samples its durations in-range independently of the section-level
    # setting; when None it inherits the section's note_length_range (if any).
    note_length_range: Optional[NoteLengthRangeModel]   = None

    # Independent per-voice motif override (string ref or embedded dict),
    # mirroring VoiceModel.motif's shape exactly (item MT-1, option A).
    # Resolved via resolve_motif_value with the theme's motif pool, same as
    # the lead voice's and harmony's own motif overrides — a string checks
    # theme.motifs by name first, then falls through to the external
    # library; an embedded dict is used directly.
    #
    # RHYTHM ONLY, never pitch (see generate_free_species's
    # rhythm_events_override in counterpoint.py): consonance/voice-leading
    # stays fully rule-driven regardless of this field. Only "free" species
    # can honor it — "first" species is rhythmically locked to the melody by
    # definition (see generate_first_species's docstring) and silently
    # ignores it if set; not an error, since the classical species
    # definition already determines rhythm for that voice.
    #
    # Opt-in per voice by construction: unset (the default) means this
    # voice's rhythm is exactly what it was before this field existed —
    # its own density/groove grid. No section-level trigger; setting the
    # section's rhythm to "motif" has no effect on a counterpoint voice
    # that doesn't independently set this field.
    motif: Optional[Union[str, dict]] = None

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

    # 2026-08: opt-in, defaults to 0.0 (byte-identical to pre-existing
    # behavior). Per-note probability that "lyrical" behavior considers a
    # skip-a-degree leap (2 scale-degree steps) instead of only its normal
    # stepwise/chord-adjacent motion. Added because generate_lyrical's
    # candidate filter was hardcoded to <=3/<=5 semitones regardless of
    # mode, which meant non-heptatonic modes (pelog, hirajoshi, insen,
    # etc.) never got to show the wide "gap" leaps that are their actual
    # distinguishing character — see melody.py's generate_lyrical
    # docstring and _skip_degree_candidates for the mechanism. Only
    # consumed by "lyrical"; schema-legal but currently a no-op on other
    # behaviors (generative/sparse already permit wider motion natively;
    # develop reads motif intervals literally and ignores this field).
    leap_probability: Annotated[float, Field(ge=0.0, le=1.0)] = 0.0

    @field_validator("species", mode="after")
    @classmethod
    def _validate_species_implemented(cls, v):
        """Mirrors CounterpointModel's check — see its docstring. None
        (the default, meaning "no species — use melody.py") is exempt."""
        if v is not None and v not in ("first", "free"):
            raise ValueError(
                f"species='{v}' is not implemented in counterpoint.py — "
                f"only 'first' and 'free' are. 'second'/'third'/'fourth'/"
                f"'fifth' are schema-valid names but raise ValueError at "
                f"render time."
            )
        return v

    # Per-voice rest probability (overrides section default when set)
    rest_probability: Optional[Annotated[float, Field(ge=0.0, le=1.0)]] = None

    # ── Literal subject/answer entry (fugue-style) ──────────────────────
    # When set, this voice renders `motif` literally via
    # generate_subject_entry() instead of going through generate_counterpoint
    # (species path) or generate_melody_for_progression (free melody path).
    # None (the default) is a strict no-op — every existing piece JSON is
    # unaffected. See motif.py's generate_subject_entry docstring for the
    # rendering contract.
    entry_role: Optional[Literal["subject", "answer"]] = None

    # Semitone transposition applied when entry_role == "answer". None
    # (the default) means the real answer: +7 semitones (perfect 5th
    # above). Tonal-answer mutation is out of scope for Phase 1 — see
    # generate_subject_entry's docstring.
    answer_interval: Optional[int] = None

    @field_validator("entry_role", mode="after")
    @classmethod
    def _validate_entry_role_needs_motif(cls, v, info):
        """entry_role renders `motif` literally — without one there is
        nothing to render. Raising here beats the alternative (a voice
        that validates cleanly and then silently produces zero notes),
        matching how this schema treats every other silent-gap risk."""
        if v is not None and info.data.get("motif") is None:
            raise ValueError(
                f"entry_role='{v}' requires this voice's `motif` field "
                f"to be set — there is nothing to render literally "
                f"without one."
            )
        return v

    @field_validator("answer_interval", mode="after")
    @classmethod
    def _validate_answer_interval_needs_answer(cls, v, info):
        """answer_interval only means something for entry_role='answer'.
        Setting it alongside 'subject' (or with entry_role unset) would
        otherwise validate cleanly and do nothing."""
        if v is not None and info.data.get("entry_role") != "answer":
            raise ValueError(
                "answer_interval is only meaningful when "
                "entry_role='answer' (it has no effect on 'subject' or "
                "when entry_role is unset)."
            )
        return v

    @model_validator(mode="after")
    def _validate_entry_role_species_exclusive(self):
        """entry_role and species pick different, mutually-exclusive
        rendering paths for this voice (generate_subject_entry vs.
        generate_counterpoint) — generator.py's dispatch checks entry_role
        first, which would silently strand a `species` value set alongside
        it. Forcing the composer to pick one avoids that silent-ignore."""
        if self.entry_role is not None and self.species is not None:
            raise ValueError(
                "entry_role and species are mutually exclusive on a "
                "voice — entry_role renders the motif literally; species "
                "generates free counterpoint against the melody. Pick one."
            )
        return self

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

class DrumFillModel(BaseModel):
    """
    Corresponds to section["drums"]["fills"]. Describes a single-bar (or
    short multi-bar) fill spliced into the drum pattern on eligible bars --
    the mechanism scoped as item 2 in the EDM/house/techno work: fills and
    a true multi-bar accelerando roll are different mechanisms (this is
    only the former; see percussion.py's _generate_fill_slots docstring).
    """
    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    placement:      Literal["phrase_end", "section_end"] = "phrase_end"
    phrase_bars:    int = Field(default=8, ge=1)   # only consulted for "phrase_end"
    bars:           int = Field(default=1, ge=1)   # span of the fill, ending at the boundary
    instrument:     Literal["kick", "snare", "hi_hat", "ride", "sidestick",
                             "tom_hi", "tom_mid", "tom_lo"] = "hi_hat"
    subdivision:    Annotated[float, Field(gt=0.0, le=1.0)] = 0.25   # 0.25 = 16th notes
    velocity_start: Annotated[float, Field(ge=0.0, le=1.0)] = 0.5
    velocity_end:   Annotated[float, Field(ge=0.0, le=1.0)] = 1.0
    # Rolled once per fill EVENT (a whole `bars`-span group), not once per
    # bar -- a multi-bar fill never fires on only part of its span. Thins
    # which otherwise-eligible fills occur; placement itself stays
    # structural via `placement`/`phrase_bars`, not probabilistic.
    probability:    Annotated[float, Field(ge=0.0, le=1.0)] = 1.0


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

    pattern: DrumPatternLiteral           = "four_on_floor"
    density: Optional[DensityLiteral]    = None   # None → inherit from section
    groove:  Optional[GrooveLiteral]      = None   # None → inherit from section
    swing:   Optional[float]             = None   # None → inherit from section
    fills:   Optional[DrumFillModel]      = None   # None → no fills (unchanged behavior)

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
    intervals:      list[int]              = Field(
        min_length=1,
        description=(
            "Diatonic scale-degree steps between successive notes, resolved "
            "against the piece's mode (or melodic_scale, if set) -- NOT "
            "semitones. E.g. [2, -1, 3] means up 2 scale degrees, down 1, "
            "up 3. Every resulting note lands on a scale tone by "
            "construction. See motif.py's Motif.intervals docstring for "
            "the full contract and migration history."
        ),
    )
    rhythm:         Optional[list[float]]  = None
    rests:          Optional[list[bool]]   = None
    velocities:     Optional[list[float]]  = None
    transform_pool: list[TransformLiteral] = Field(default_factory=list)
    melodic_scale:  Optional[str]          = None

    @field_validator("melodic_scale", mode="before")
    @classmethod
    def _validate_melodic_scale(cls, v):
        """
        Phase B4 (melodic-scale decoupling): an optional override of which
        scale motif_to_notes walks for THIS motif's pitches, independent of
        the piece's harmonic mode. When None (the default), melody walks
        the piece's own mode exactly as before this field existed.

        Chords/Roman-numeral resolution never read this field — harmony.py's
        resolve_progression always uses the piece's `mode`, so a piece keeps
        ordinary diatonic I-IV-V7 harmony (which needs a 7-note scale for
        Roman numerals to mean anything) while its melody can walk a
        pentatonic/blues scale on top. That's the actual relationship blues
        melody has to its underlying harmony — the melody scale and the
        harmony scale genuinely differ, which is what makes a blue note
        "blue" rather than a wrong note. A single shared `mode` field can't
        express that; this field exists so the diatonic-motif contract
        (every interval lands on a scale tone by construction — see
        motif.py's Motif.intervals docstring) doesn't have to sacrifice
        that guarantee to get blues color, and doesn't have to carve out a
        chromatic exception either.

        Wider whitelist than piece.mode's _validate_mode: pentatonic/blues
        scales are deliberately INVALID as a piece's harmonic mode (only 5
        or 6 notes — harmony.py's chord-quality math stacks thirds off
        exactly 7 scale degrees per ROMAN_TO_DEGREE, so a 5-note scale
        there produces nonsense chords), but they're exactly the point of
        this field, which never touches that code path at all.
        """
        if v is None or not isinstance(v, str):
            return v
        VALID_MELODIC_SCALES = {
            "ionian", "dorian", "phrygian", "lydian",
            "mixolydian", "aeolian", "locrian",
            "pentatonic_major", "pentatonic_minor", "blues",
        }
        if v.lower() not in VALID_MELODIC_SCALES:
            raise ValueError(
                f"motif melodic_scale '{v}' is not valid. "
                f"Choose from {sorted(VALID_MELODIC_SCALES)}."
            )
        return v.lower()

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

def _resolve_motif_value_safe(value: Optional[Union[str, dict]], theme_pool: Optional[list] = None):
    """
    Resolve a voice/harmony_rhythm motif override value (string ref or
    embedded dict) for cross-model validation in SectionModel.
    validate_against_theme. Wraps motif_loader errors (bad name, malformed
    file) into ValueError so a bad override surfaces with the same
    exception type as every other check in that method, rather than a bare
    FileNotFoundError bubbling up from a different module.

    theme_pool (item MT-0): the theme's inline motif pool as a list of dicts,
    so a string name reference resolves against motifs declared inline in the
    theme before falling through to the external library — the same
    resolution order the generator uses. Without it, a name that exists only
    inline (never as a library file) would fail validation even though the
    generator can resolve it, splitting the two paths.

    Returns None for a None value — that's the "not overridden, fall back
    to the theme" case, not an error.
    """
    if value is None:
        return None
    from intervals.core.motif_loader import resolve_motif_value
    try:
        return resolve_motif_value(value, theme_pool=theme_pool)
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

    # Melody pitch-source strategy when rhythm == "motif" and the theme has
    # more than one motif in its pool (item MT-3). Default (None): pitch is
    # PINNED to the same motif driving the rhythm — one motif, fully
    # committed, both dimensions. "isorhythmic" opts INTO the previously-
    # unreconciled behavior where rhythm stays anchored to one motif while
    # pitch contour is redrawn from a different pool member each chord — a
    # real technique (isorhythm: a fixed talea against a varying color), not
    # a bug, for composers who want it deliberately.
    #
    # No effect when: rhythm != "motif" (nothing to decouple from); the
    # theme's pool has 0-1 motifs (nothing to vary between); or the lead
    # voice sets its own explicit motif override (a specific single motif
    # chosen for the voice already wins outright — see generator.py's
    # melody_motif_pool resolution). lint.py flags the no-op cases.
    melodic_variation: Optional[Literal["isorhythmic"]] = None

    groove: Optional[GrooveLiteral]                       = None
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

    # Apex/goal-tone phrase shaping (Phase 6 of the apex/goal-tone build).
    # See MelodicArcModel's docstring for the full contract, including the
    # documented sparse caveat. Optional; absent means every section
    # behaves exactly as before this feature existed.
    melodic_arc: Optional[MelodicArcModel] = None

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

    # Only consumed by bass_style="pulse" -- generate_bass() warns (does not
    # silently ignore) if either is set with any other style, same pattern
    # as bass_rest_probability's walking/melodic guard above.
    #   bass_subdivision: beats between pulse onsets. None inherits
    #     style_pulse()'s own default (1.0, quarter notes) -- unchanged
    #     behavior for every existing piece.
    #   bass_offset: phase-shifts the pulse grid's start within each chord.
    #     None = 0.0 (on the downbeat, unchanged behavior). The classic
    #     offbeat house/garage bass is bass_subdivision=1.0,
    #     bass_offset=0.5 -- quarter notes landing purely on the "and",
    #     never coinciding with a four-on-floor kick on the downbeat.
    bass_subdivision: Optional[Annotated[float, Field(gt=0.0, le=4.0)]] = None
    bass_offset:      Optional[Annotated[float, Field(ge=0.0, lt=4.0)]] = None

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

    @field_validator("voices", mode="after")
    @classmethod
    def _validate_voices_count(cls, v):
        """
        Cap at 4 total voices (1 lead + 3 peers). generator.py writes peer
        voices (section.voices[1:]) to MIDI tracks via a hardcoded 3-entry
        _cp_track_specs list, indexed by peer position — a 4th peer voice
        (voices[4], the 5th entry overall) would index past the end of that
        list and crash with an IndexError deep in MIDI writing, well after
        generation has already run. Catching it here instead gives a clean
        error at validation time, before any generation starts, mirroring
        the existing counterpoint cap above.
        """
        if v is not None and len(v) > 4:
            raise ValueError(
                f"voices supports at most 4 total (1 lead + 3 peers), got {len(v)}"
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
    def _warn_lead_canon_offset_is_dead(self) -> "SectionModel":
        """
        Known-issues #3: canon_offset is schema-legal on every VoiceModel
        instance, but generator.py only ever reads it in two places — the
        peer-voice loop (section.voices[1:]) and the counterpoint[] loop —
        neither of which the lead voice passes through. The lead voice is
        section.voices[0] when voices[] is used, OR section.melody when
        given in VoiceModel dict form (lead_voice() resolves whichever one
        actually applies) — canon_offset is equally dead on both, since
        generator.py never touches section.melody's VoiceModel at all and
        never iterates voices[0].

        Pydantic has no way to know a given VoiceModel instance is "the
        lead" vs. "a peer" — that's positional/contextual, not something
        the field itself can express — so this can only be caught here, at
        the section level, not on VoiceModel itself.

        Warning, not an error: the field simply does nothing, same category
        as the engine's other silent-no-op traps (#4/#5/#6) rather than
        #7's total-output-loss case — the section still renders fully,
        just without the (never-applied) canon shift on this one voice.
        """
        lead = self.lead_voice()
        if lead is not None and lead.canon_offset > 0:
            source = "voices[0]" if self.voices else "melody (dict form)"
            warnings.warn(
                f"Section '{self.name}': {source}.canon_offset="
                f"{lead.canon_offset} is set on the LEAD voice, but "
                f"generator.py never reads canon_offset for the lead — only "
                f"peer voices (section.voices[1:]) and counterpoint[] "
                f"entries apply it. This value is silently ignored; the "
                f"lead's timing is unaffected. If you meant to offset a "
                f"peer voice, set canon_offset on a voices[1:] entry "
                f"instead — canon_offset on the lead has no mechanism to "
                f"apply it against.",
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

        The harmony_rhythm 'pattern' check covers BOTH the explicit case
        (harmony_rhythm.rhythm='pattern' set directly) and the inherited
        case (section.rhythm='pattern', no harmony_rhythm override) — see
        known-issues #7. Previously only the explicit case was caught here;
        the inherited case reached harmony.py's resolve_harmony_section_
        events() and returned silently with zero events, zero print, zero
        warning.
        """
        if self.rhythm == "pattern" and self.rhythm_pattern is None:
            raise ValueError(
                f"Section '{self.name}': rhythm='pattern' requires a "
                f"rhythm_pattern block"
            )
        # Effective harmony rhythm source, mirroring the exact cascade
        # harmony.py's resolve_harmony_section_events() applies at render
        # time (source = explicit_source or melody_rhythm_source): an
        # explicit harmony_rhythm.rhythm always wins; otherwise harmony
        # inherits section.rhythm. Computed once here so both the explicit
        # and inherited "pattern" cases below are governed by the same
        # dependency check instead of only catching the explicit one.
        explicit_hr_rhythm = self.harmony_rhythm.rhythm if self.harmony_rhythm else None
        effective_hr_source = explicit_hr_rhythm or self.rhythm
        if effective_hr_source == "pattern" and self.harmony_pattern is None:
            if explicit_hr_rhythm == "pattern":
                raise ValueError(
                    f"Section '{self.name}': harmony_rhythm.rhythm='pattern' "
                    f"requires a harmony_pattern block"
                )
            # Inherited case: no harmony_rhythm block at all, or one present
            # but not setting rhythm, so harmony silently falls back to
            # section.rhythm='pattern' with nothing to render — total
            # silence at render time (zero harmony events, no print, no
            # warning) rather than the coerced-but-audible outcome the
            # 'motif' inheritance case gets. Known-issues #7: promoted from
            # lint-warning candidate straight to a schema error, since the
            # failure mode is total output loss, not a degraded result.
            raise ValueError(
                f"Section '{self.name}': rhythm='pattern' is inherited by "
                f"harmony (no harmony_rhythm.rhythm override, or harmony_rhythm "
                f"omitted entirely), but no harmony_pattern block is present — "
                f"harmony would render zero events with no warning. Either add "
                f"a harmony_pattern block, or set harmony_rhythm.rhythm to "
                f"something else ('sustain', 'free', 'motif') to opt harmony "
                f"out of the inherited pattern source."
            )
        if self.harmony_rhythm is not None:
            hr = self.harmony_rhythm
            # harmony_rhythm.transform_imitation='strict' is schema-legal
            # (Literal["strict"]) but NOT implemented — resolve_harmony_
            # section_events() in harmony.py raises ValueError whenever it's
            # combined with an EXPLICIT harmony_rhythm.rhythm='motif' (the
            # only branch that reads transform_imitation at all; motif
            # inherited from section.rhythm without an explicit
            # harmony_rhythm.rhythm is coerced to 'free' before this field
            # is ever consulted, so that combination is harmless and not
            # checked here). Catching the live combination at validation
            # time turns a mid-render crash into an immediate, clear error —
            # same reasoning as the harmony_pattern check just above.
            if hr.transform_imitation == "strict" and hr.rhythm == "motif":
                raise ValueError(
                    f"Section '{self.name}': harmony_rhythm.transform_imitation="
                    f"'strict' combined with harmony_rhythm.rhythm='motif' is "
                    f"not implemented — this will raise ValueError at render "
                    f"time in harmony.py (melody's transform choices don't "
                    f"exist yet at the point harmony resolves, and the two "
                    f"voices' repetition cadence isn't the same shape to "
                    f"inherit across). Remove transform_imitation (leave it "
                    f"unset) for harmony's independent per-repetition "
                    f"transform selection — the only mode currently "
                    f"implemented."
                )
        return self

    # ─────────────────────────────────────────────────────────────────────────
    # Cross-model validation (requires theme — called by PieceModel)
    # ─────────────────────────────────────────────────────────────────────────

    def validate_against_theme(self, theme_model: "PieceModel") -> None:
        """
        Validate rhythm-source prerequisites that depend on theme content
        (key, mode, motif/motifs — absorbed into PieceModel; theme is
        merged into piece now, single-file format). theme_model is the
        containing PieceModel itself, passed in by
        PieceModel.validate_against_theme() as a self-check rather than a
        genuinely separate model.

        Raises ValueError if rhythm='motif' but neither the piece's own
        motif nor the relevant independent override (voice.motif /
        harmony_rhythm.motif) supplies a motif rhythm. Call
        PieceModel.validate_against_theme(self) to run this for every
        section at once.
        """
        primary = theme_model.primary_motif
        theme_has_rhythm = primary is not None and primary.rhythm is not None
        label = self.name or "?"

        lead = self.lead_voice()
        voice_motif_value    = lead.motif if lead is not None else None
        harmony_motif_value  = (
            self.harmony_rhythm.motif if self.harmony_rhythm is not None else None
        )
        # Inline motif pool (item MT-0): a string motif reference on a voice
        # or harmony_rhythm resolves against motifs declared inline in the
        # theme before the external library. model_dump each MotifModel to the
        # plain-dict shape resolve_motif_value matches names against.
        #
        # Falls back to the singular `motif` field when `motifs` isn't set,
        # mirroring primary_motif's own fallback — otherwise a piece using
        # the standard single-motif format could never have a voice
        # reference its own top-level motif by name (item MT-1).
        pool_source = theme_model.motifs or (
            [theme_model.motif] if theme_model.motif is not None else None
        )
        theme_pool = None
        if pool_source:
            theme_pool = [m.model_dump(exclude_none=True) for m in pool_source]

        voice_motif    = _resolve_motif_value_safe(voice_motif_value, theme_pool)
        harmony_motif  = _resolve_motif_value_safe(harmony_motif_value, theme_pool)
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

        # counterpoint[].motif and peer voices[1:].motif — a *different*
        # crash gap from the two checks just above. The lead voice
        # (voices[0] / melody-as-dict) and harmony_rhythm.motif are both
        # resolved here via _resolve_motif_value_safe, which converts a
        # bad name into this method's clean ValueError. But at render time,
        # counterpoint[] entries and peer voices route through a different
        # resolver entirely — generator.py's _resolve_voice_motif_rhythm —
        # which calls resolve_motif_value() directly with no error handling
        # at all, and does so unconditionally whenever .motif is set,
        # regardless of species (even a "first"-species voice, where the
        # motif is otherwise inert per lint.py, still hits this call). A
        # typo'd name there previously reached generation as a raw,
        # uncaught FileNotFoundError instead of this method's ValueError.
        # voices[0] is skipped here — already covered above via voice_motif
        # / lead_voice().
        for cp in (self.counterpoint or []):
            if cp.motif is not None:
                cp_motif = _resolve_motif_value_safe(cp.motif, theme_pool)
                self._check_bar_alignment(
                    cp_motif.name, cp_motif.rhythm, label, where="counterpoint[].motif"
                )
        for peer in (self.voices or [])[1:]:
            if peer.motif is not None:
                peer_motif = _resolve_motif_value_safe(peer.motif, theme_pool)
                self._check_bar_alignment(
                    peer_motif.name, peer_motif.rhythm, label, where="voices[].motif"
                )

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
# TempoRangeModel
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

# ThemeModel retired — its fields (name, key, mode, tempo, motif, motifs)
# and validators (_validate_theme_key/_mode, _warn_obsolete_theme_keys,
# _motif_consistency, primary_motif) are absorbed directly into PieceModel
# below (single-file format: theme merged into piece).

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
    tempo:     Optional[TempoRangeModel] = None
    seed:      int = 42

    form_type: Literal["narrative", "song"] = "narrative"

    # Narrative form
    sections:      Optional[list[SectionModel]]          = None
    # Song form
    song_sections: Optional[dict[str, SectionModel]]     = None
    form:          Optional[list[Union[SongFormEntryModel, str]]] = None

    transform_sequence: Optional[list[TransformLiteral]] = None

    # Absorbed from ThemeModel (theme merged into piece — single-file format).
    name:   Optional[str]              = None
    key:    str                        = Field(min_length=1)
    mode:   str                        = Field(min_length=1)
    motif:  Optional[MotifModel]       = None
    motifs: Optional[list[MotifModel]] = None

    def resolved_tempo(self) -> Optional[int]:
        """
        Resolve ``tempo`` (a TempoRangeModel) to a single bpm value for
        generation. Exact value when min == max (composer set a fixed
        tempo), otherwise the midpoint of the range.

        Single source of truth for the midpoint formula that used to be
        duplicated in main.py (x2) and generator.py (x1). Returns None
        when tempo is unset entirely — callers fall back appropriately
        (see the theme-midpoint fallback, retired once theme merges in).
        """
        if self.tempo is None:
            return None
        if self.tempo.min == self.tempo.max:
            return self.tempo.min
        return (self.tempo.min + self.tempo.max) // 2

    @property
    def primary_motif(self) -> Optional[MotifModel]:
        """
        Absorbed from ThemeModel. Return the effective primary motif
        (motifs[0] if the array is set, else the single 'motif' field).
        """
        if self.motifs:
            return self.motifs[0]
        return self.motif

    @field_validator("key", mode="before")
    @classmethod
    def _validate_key(cls, v):
        """
        Absorbed from ThemeModel._validate_theme_key. key/mode were
        previously plain str (min_length=1 only) — schema-legal for any
        typo. A section that doesn't override key/mode inherits this
        value directly into harmony.py's chord resolution, where a bad
        one only surfaces as "Unknown key: '...'" at render time.
        """
        if not isinstance(v, str):
            return v  # let Pydantic's own type check produce its message
        VALID_KEYS = {
            "C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B",
            "Db", "Eb", "Gb", "Ab", "Bb",
        }
        if v not in VALID_KEYS:
            raise ValueError(
                f"Piece key '{v}' is not a valid note name. "
                f"Choose from {sorted(VALID_KEYS)}."
            )
        return v

    @field_validator("mode", mode="before")
    @classmethod
    def _validate_mode(cls, v):
        """Absorbed from ThemeModel._validate_theme_mode — see _validate_key."""
        if not isinstance(v, str):
            return v
        VALID_MODES = {
            "ionian", "dorian", "phrygian", "lydian",
            "mixolydian", "aeolian", "locrian",
            # 2026-08: unblocked — these were already fully implemented in
            # harmony.py's MODES dict (imported by melody/bass/counterpoint
            # too) but rejected here before ever reaching the generator.
            "harmonic_minor", "melodic_minor",
            "pentatonic_major", "pentatonic_minor",
            "blues", "whole_tone", "diminished",
            # 2026-08: new — see harmony.py's MODES dict for interval
            # sourcing/caveats (non-heptatonic roman numeral aliasing).
            "pelog", "arabic", "hirajoshi", "insen", "augmented_hexatonic"
        }
        if v.lower() not in VALID_MODES:
            raise ValueError(
                f"Piece mode '{v}' is not valid. Choose from {sorted(VALID_MODES)}."
            )
        return v.lower()

    @model_validator(mode="before")
    @classmethod
    def _warn_obsolete_keys(cls, data: dict) -> dict:
        """
        Absorbed from ThemeModel._warn_obsolete_theme_keys. Flat check now
        that theme is merged in — no more {"theme": {...}} sub-dict to
        unwrap for this specific check.
        """
        if not isinstance(data, dict):
            return data
        for key in _OBSOLETE_THEME_KEYS:
            if key in data:
                warnings.warn(
                    f"piece has obsolete field '{key}' — remove it "
                    f"(instruments live in Logic)",
                    stacklevel=5,
                )
        return data

    @model_validator(mode="before")
    @classmethod
    def _unwrap_nested_and_sections(cls, data: dict) -> dict:
        """
        1. Accept both {"piece": {...}} and flat dict forms.
        2. Disambiguate sections list vs dict into separate fields.
        3. Coerce a bare-int tempo (every existing catalog piece) into
           {"min": v, "max": v} so old JSON keeps validating unchanged
           now that tempo is a TempoRangeModel. Fixed-value range and a
           bare exact bpm are the same thing; this just accepts both
           spellings rather than forcing a catalog-wide rewrite as a
           side effect of the schema step.
        """
        if "piece" in data and isinstance(data["piece"], dict):
            data = data["piece"]
        else:
            data = dict(data)

        raw_tempo = data.get("tempo")
        if isinstance(raw_tempo, (int, float)):
            data["tempo"] = {"min": raw_tempo, "max": raw_tempo}

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

    @model_validator(mode="after")
    def _motif_consistency(self) -> "PieceModel":
        """
        Absorbed from ThemeModel._motif_consistency. No-motif case is a
        warning, not an error (generation still works, purely generative).
        """
        if self.motif is None and self.motifs is None:
            warnings.warn(
                "piece has no motif or motifs defined — melodic identity "
                "will be purely generative",
                stacklevel=4,
            )
        if self.motif is not None and self.motifs is not None:
            warnings.warn(
                "piece has both 'motif' and 'motifs' — 'motifs' array takes "
                "precedence; 'motif' is ignored.",
                stacklevel=4,
            )
        if self.motifs is not None and len(self.motifs) == 0:
            raise ValueError("piece 'motifs' must be a non-empty list")
        return self

    def validate_against_theme(self, theme_model: "PieceModel") -> None:
        """
        Run the cross-checks that used to require a separate ThemeModel
        (rhythm='motif' needs a motif.rhythm somewhere, etc.). Theme's
        fields are absorbed into PieceModel now (single-file format), so
        this is a self-check — call as `piece_model.validate_against_theme(
        piece_model)` after PieceModel.model_validate() succeeds (see
        generator.generate_piece).

        Also warns if the piece has no explicit tempo — this was a [WARN]
        in the old validate_piece() that can't live in a single-model
        field validator (needs the whole model constructed first).
        """
        if self.tempo is None:
            # generate_piece()'s resolved_tempo() falls back to a plain
            # 120bpm default when tempo is unset entirely.
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
