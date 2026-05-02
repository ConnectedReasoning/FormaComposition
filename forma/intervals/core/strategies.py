"""
strategies.py — Strategy Pattern for rhythm and melody behavior selection.

Replaces the if/elif/else switchboards in generate_section with a clean
dispatch mechanism. Each strategy is a self-contained unit that knows how
to produce rhythm events or melody notes for one specific source/behavior.

Architecture:
  RhythmContext       — immutable data bundle passed to every rhythm strategy
  RhythmStrategy      — abstract base; concrete subclasses own one rhythm source
  MelodyContext       — immutable data bundle passed to every melody strategy
  MelodyBehaviorStrategy — abstract base; thin wrappers over generate_melody_for_progression

Usage (in generate_section):
  ctx = RhythmContext(...)
  melody_events, bass_events = RhythmStrategyRegistry.resolve(rhythm_source).apply(ctx)

  mctx = MelodyContext(...)
  notes = MelodyStrategyRegistry.resolve(melody_beh).apply(mctx)
"""

from __future__ import annotations

import statistics as _stats
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Optional

from intervals.music.rhythm import (
    RhythmEvent, get_pattern,
    apply_velocity_arc, apply_swing,
)
from intervals.music.melody import generate_melody_for_progression, MelodyNote
from intervals.music.harmony import VoicedChord

# MIDI channel for harmony voice — mirrors the constant in generator.py.
# Defined here so HarmonyStrategy subclasses don't import generator (circular).
_CHANNEL_HARMONY = 1
_REARTIC_GAP = 0.03   # beats — inaudible gap prevents note-off/on overlap


# ═══════════════════════════════════════════════════════════════════════════════
# Rhythm utility functions — live here to avoid circular imports with generator
# ═══════════════════════════════════════════════════════════════════════════════

def rhythm_pattern_to_events(pattern: dict, total_beats: float) -> list[RhythmEvent]:
    """
    Convert a rhythm_pattern dict (from rhythm_extract.py) into a tiled
    list of RhythmEvent covering total_beats.

    The pattern is repeated as many times as needed to fill the section.
    Last repetition is trimmed at the section boundary.
    """
    onsets = pattern["onsets"]
    durations = pattern["durations"]
    velocities = pattern.get("velocities", [0.7] * len(onsets))
    cycle_length = pattern.get("length_beats", 8.0)

    if not onsets or cycle_length <= 0:
        return []

    events = []
    offset = 0.0
    while offset < total_beats:
        for i in range(len(onsets)):
            abs_onset = offset + onsets[i]
            if abs_onset >= total_beats:
                break
            dur = durations[i] if i < len(durations) else 0.5
            dur = min(dur, total_beats - abs_onset)
            vel = velocities[i] if i < len(velocities) else 0.7
            events.append(RhythmEvent(
                start_beat=abs_onset,
                duration_beats=max(0.25, dur),
                velocity_scale=vel,
                is_rest=False,
            ))
        offset += cycle_length
    return events


def _motif_rhythm_to_events(
    rhythm: list,
    total_beats: float,
    articulation: str = "full",
    velocities: Optional[list] = None,
) -> list[RhythmEvent]:
    """
    Convert a motif rhythm (list of beat durations) to a tiled list of
    RhythmEvent covering total_beats.

    articulation controls onset density per voice:
      "full"     — every onset (melody)
      "stressed" — onsets >= median duration (harmony)
      "anchor"   — downbeat only (bass)
    """
    if not rhythm or total_beats <= 0:
        return []
    cycle_length = sum(rhythm)
    if cycle_length <= 0:
        return []

    onsets = []
    t = 0.0
    for dur in rhythm:
        onsets.append(t)
        t += dur

    if articulation == "anchor":
        keep = [0]
    elif articulation == "stressed":
        median_dur = _stats.median(rhythm)
        keep = [i for i, d in enumerate(rhythm) if d >= median_dur]
        if 0 not in keep:
            keep = [0] + keep
    else:  # "full"
        keep = list(range(len(rhythm)))

    if velocities is None or len(velocities) != len(rhythm):
        velocities = [0.8] * len(rhythm)

    events = []
    offset = 0.0
    while offset < total_beats:
        for i in keep:
            abs_onset = offset + onsets[i]
            if abs_onset >= total_beats:
                break
            dur = min(rhythm[i], total_beats - abs_onset)
            if dur < 0.25:
                continue
            events.append(RhythmEvent(
                start_beat=abs_onset,
                duration_beats=dur,
                velocity_scale=velocities[i],
                is_rest=False,
            ))
        offset += cycle_length
    return events


def _slice_events_into_window(
    events: list,
    window_start: float,
    window_length: float,
    min_duration: float = 0.25,
) -> list[RhythmEvent]:
    """
    Extract RhythmEvents whose start falls inside [window_start, window_start +
    window_length), translated to window-local coordinates.

    Events trimmed shorter than min_duration at the boundary are dropped.
    """
    window_end = window_start + window_length
    sliced = []
    for ev in events:
        if ev.start_beat < window_start or ev.start_beat >= window_end:
            continue
        local_start = ev.start_beat - window_start
        local_dur = min(ev.duration_beats, window_length - local_start)
        if local_dur < min_duration:
            continue
        sliced.append(RhythmEvent(
            start_beat=local_start,
            duration_beats=local_dur,
            velocity_scale=ev.velocity_scale,
            is_rest=ev.is_rest,
        ))
    return sliced


# ═══════════════════════════════════════════════════════════════════════════════
# Data bundles — keep strategies decoupled from the raw section dict
# ═══════════════════════════════════════════════════════════════════════════════

@dataclass(frozen=True)
class RhythmContext:
    """
    Everything a RhythmStrategy needs to produce melody + bass rhythm events.
    Constructed once per section from validated section/theme data.
    """
    source: str                        # "pattern" | "motif" | "free"
    total_beats: float
    density: str

    # Hand-played pattern (used by PatternRhythmStrategy)
    rhythm_pattern: Optional[dict] = None

    # Motif rhythm (used by MotifRhythmStrategy)
    motif_rhythm: Optional[list[float]] = None
    motif_velocities: Optional[list[float]] = None

    # Grid fallback parameters (used by FreeRhythmStrategy)
    groove: Optional[str] = None
    swing: float = 0.0
    beats_per_bar: int = 4
    seed: int = 42


@dataclass(frozen=True)
class HarmonyRhythmContext:
    """
    Everything a HarmonyRhythmStrategy needs to produce chord rhythm events
    for a single chord window.
    """
    source: str                        # "sustain" | "pattern" | "motif" | "free"
    total_beats_section: float         # full section length (for pattern tiling)
    total_per_chord: float             # this chord window's beat length
    beat_offset: float                 # absolute offset of this chord in section

    density: str
    groove: Optional[str] = None
    beats_per_bar: int = 4
    swing: float = 0.0

    # Hand-played harmony pattern (optional, used by PatternHarmonyStrategy)
    harmony_pattern: Optional[dict] = None

    # Motif rhythm fields
    motif_rhythm: Optional[list[float]] = None
    motif_velocities: Optional[list[float]] = None

    # Pre-resolved section events (passed through from pre-computation step)
    # Kept as an escape hatch so the refactor doesn't break the existing
    # _resolve_harmony_rhythm call in generate_piece.
    precomputed_events: Optional[list] = None   # list[RhythmEvent] or "sustain"


@dataclass(frozen=True)
class HarmonyChordContext:
    """
    Everything a HarmonyStrategy needs to produce MIDI event tuples for
    a single chord window inside generate_piece's section loop.

    This is distinct from HarmonyRhythmContext (which only carries rhythm
    resolution inputs). HarmonyChordContext wraps that rhythm context and
    adds the chord itself, timing offsets, articulation, and channel so that
    apply() returns ready-to-append event tuples.

    Returned event tuple format:
        (abs_beat: float, kind: str, note: int, vel: int, channel: int)
    where kind is 'on' or 'off'.
    """
    chord: VoicedChord                 # chord whose notes are voiced
    harmony_rhythm_ctx: HarmonyRhythmContext

    # Absolute timing for this chord within the piece
    global_beat: float                 # beat offset of the whole section
    beat_offset_local: float           # beat offset within the section

    # Articulation / expression
    arc: str                           # velocity arc shape (e.g. "swell")
    base_velocity: int = 65
    channel: int = _CHANNEL_HARMONY

    @property
    def h_swing(self) -> float:
        """Convenience accessor — swing lives on the rhythm context."""
        return self.harmony_rhythm_ctx.swing


@dataclass(frozen=True)
class MelodyContext:
    """
    Everything a MelodyBehaviorStrategy needs to generate melody notes.
    """
    behavior: str
    chords: list[VoicedChord]
    key: str
    mode: str
    density: str
    bars_per_chord: list[float]
    beats_per_bar: int
    motif: Optional[dict]
    motif_pool: Optional[list[dict]]
    groove: Optional[str]
    swing: float
    seed: int
    section_name: str
    rhythm_events_override: Optional[list[RhythmEvent]]
    fugal_techniques: Optional[list]
    rest_probability: float


# ═══════════════════════════════════════════════════════════════════════════════
# Rhythm strategies
# ═══════════════════════════════════════════════════════════════════════════════

class RhythmStrategy(ABC):
    """
    Abstract base: produce melody and bass rhythm event lists for a section.

    Both lists cover the full section length (total_beats). The caller
    passes them as rhythm_events_override into the bass and melody generators.
    Returning None means "let the generator use its own density grid."
    """

    @abstractmethod
    def apply(self, ctx: RhythmContext) -> tuple[
        Optional[list[RhythmEvent]],   # melody rhythm
        Optional[list[RhythmEvent]],   # bass rhythm
    ]:
        ...

    @property
    @abstractmethod
    def label(self) -> str:
        """Short human-readable name for console logging."""
        ...


class PatternRhythmStrategy(RhythmStrategy):
    """
    Rhythm source: "pattern"
    Uses a hand-played RhythmExtract pattern (onsets / durations / velocities)
    tiled to fill the section. Same events for melody and bass — the pattern
    is the performance groove the user played in.
    """

    @property
    def label(self) -> str:
        return "pattern"

    def apply(self, ctx: RhythmContext) -> tuple[
        Optional[list[RhythmEvent]], Optional[list[RhythmEvent]]
    ]:
        rp = ctx.rhythm_pattern
        if not rp:
            return None, None

        events = rhythm_pattern_to_events(rp, total_beats=ctx.total_beats)
        n_onsets = len(rp.get("onsets", []))
        length_b = rp.get("length_beats", "?")
        print(f"    Melody/Bass rhythm: hand-played pattern ({n_onsets} onsets, {length_b}b)")
        return events, events


class MotifRhythmStrategy(RhythmStrategy):
    """
    Rhythm source: "motif"
    Derives rhythm from the active motif's rhythm list, articulated at
    different densities per voice:
      melody → "full"   (every onset)
      bass   → "anchor" (downbeat only)
    """

    @property
    def label(self) -> str:
        return "motif"

    def apply(self, ctx: RhythmContext) -> tuple[
        Optional[list[RhythmEvent]], Optional[list[RhythmEvent]]
    ]:
        rhythm = ctx.motif_rhythm
        if not rhythm:
            return None, None

        mel_events = _motif_rhythm_to_events(
            rhythm, ctx.total_beats, "full", velocities=ctx.motif_velocities
        )
        bass_events = _motif_rhythm_to_events(
            rhythm, ctx.total_beats, "anchor", velocities=ctx.motif_velocities
        )
        cycle = sum(rhythm)
        print(f"    Melody rhythm: motif full   ({len(rhythm)} notes, {cycle:.1f}b cycle)")
        print(f"    Bass rhythm:   motif anchor ({len(bass_events)} triggers, {cycle:.1f}b cycle)")
        return mel_events, bass_events


class FreeRhythmStrategy(RhythmStrategy):
    """
    Rhythm source: "free"
    Delegates entirely to the density-based grid inside each voice generator.
    Returns (None, None) — the downstream generators pick their own patterns.
    """

    @property
    def label(self) -> str:
        return "free"

    def apply(self, ctx: RhythmContext) -> tuple[None, None]:
        print(f"    Melody/Bass rhythm: free (density grid)")
        return None, None


# ═══════════════════════════════════════════════════════════════════════════════
# Harmony rhythm strategies
# ═══════════════════════════════════════════════════════════════════════════════

class HarmonyRhythmStrategy(ABC):
    """
    Abstract base: produce chord rhythm events for a single chord window.
    Called once per chord in the section loop inside generate_piece.
    """

    @abstractmethod
    def apply(self, ctx: HarmonyRhythmContext) -> list[RhythmEvent]:
        ...

    @property
    @abstractmethod
    def label(self) -> str:
        ...


class SustainHarmonyStrategy(HarmonyRhythmStrategy):
    """
    Harmony rhythm: "sustain"
    One held note per chord, full window duration.
    """

    @property
    def label(self) -> str:
        return "sustain"

    def apply(self, ctx: HarmonyRhythmContext) -> list[RhythmEvent]:
        return [RhythmEvent(
            start_beat=0.0,
            duration_beats=ctx.total_per_chord,
            velocity_scale=1.0,
            is_rest=False,
        )]


class PatternHarmonyStrategy(HarmonyRhythmStrategy):
    """
    Harmony rhythm: "pattern" (hand-played harmony groove)
    Slices the pre-tiled section event list into this chord's window.
    """

    @property
    def label(self) -> str:
        return "pattern"

    def apply(self, ctx: HarmonyRhythmContext) -> list[RhythmEvent]:
        if not ctx.precomputed_events or ctx.precomputed_events == "sustain":
            # Fallback: single sustain event
            return [RhythmEvent(0.0, ctx.total_per_chord, 1.0, False)]

        events = _slice_events_into_window(
            ctx.precomputed_events,
            ctx.beat_offset,
            ctx.total_per_chord,
            min_duration=0.25,
        )
        if not events:
            events = [RhythmEvent(0.0, ctx.total_per_chord, 0.7, False)]
        return events


class MotifHarmonyStrategy(HarmonyRhythmStrategy):
    """
    Harmony rhythm: "motif" (stressed articulation — strong beats only)
    Same slice approach as PatternHarmonyStrategy but from motif-derived events.
    """

    @property
    def label(self) -> str:
        return "motif"

    def apply(self, ctx: HarmonyRhythmContext) -> list[RhythmEvent]:
        if not ctx.precomputed_events or ctx.precomputed_events == "sustain":
            return [RhythmEvent(0.0, ctx.total_per_chord, 0.7, False)]

        events = _slice_events_into_window(
            ctx.precomputed_events,
            ctx.beat_offset,
            ctx.total_per_chord,
            min_duration=0.25,
        )
        if not events:
            events = [RhythmEvent(0.0, ctx.total_per_chord, 0.7, False)]
        return events


class FreeHarmonyStrategy(HarmonyRhythmStrategy):
    """
    Harmony rhythm: "free" — density-based grid, same as the legacy default.
    """

    @property
    def label(self) -> str:
        return "free"

    def apply(self, ctx: HarmonyRhythmContext) -> list[RhythmEvent]:
        return get_pattern(
            ctx.total_per_chord,
            density=ctx.density,
            voice_type="chord",
            groove=ctx.groove,
            beats_per_bar=ctx.beats_per_bar,
        )


# ═══════════════════════════════════════════════════════════════════════════════
# HarmonyStrategy — full chord-event production (rhythm → MIDI tuples)
# ═══════════════════════════════════════════════════════════════════════════════

def _build_chord_events(
    rhythm_events: list[RhythmEvent],
    chord: VoicedChord,
    global_beat: float,
    beat_offset_local: float,
    arc: str,
    h_swing: float,
    base_velocity: int,
    channel: int,
) -> list[tuple]:
    """
    Shared event-building kernel.  Given a list of RhythmEvents for one chord
    window, apply swing → velocity arc → rearticulation gap, then expand into
    (abs_beat, 'on'/'off', note, vel, channel) tuples for every MIDI note in
    the chord.

    This is the single place that knows the output tuple format.
    """
    if h_swing and h_swing > 0:
        rhythm_events = apply_swing(rhythm_events, swing_ratio=h_swing)

    arced = apply_velocity_arc(rhythm_events, arc=arc, base_velocity=base_velocity)
    arced_list = [(ev, vel) for ev, vel in arced if not ev.is_rest]

    events: list[tuple] = []
    for idx_ev, (ev, vel) in enumerate(arced_list):
        abs_start = global_beat + beat_offset_local + ev.start_beat
        dur = ev.duration_beats

        # Cap duration so the note ends before the next event starts
        if idx_ev + 1 < len(arced_list):
            next_ev = arced_list[idx_ev + 1][0]
            next_start = global_beat + beat_offset_local + next_ev.start_beat
            max_dur = next_start - abs_start - _REARTIC_GAP
            dur = max(0.25, min(dur, max_dur))

        abs_end = abs_start + dur
        for note in chord.midi_notes:
            events.append((abs_start, "on",  note, min(127, vel), channel))
            events.append((abs_end,   "off", note, 0,             channel))
    return events


class HarmonyStrategy(ABC):
    """
    Abstract base: produce all MIDI event tuples for one chord window.

    apply() encapsulates the full pipeline:
        rhythm resolution → swing → velocity arc → rearticulation → MIDI tuples

    The returned list is appended directly to all_chord_events in generate_piece.
    Event tuple format: (abs_beat: float, kind: str, note: int, vel: int, ch: int)
    """

    @abstractmethod
    def apply(self, ctx: HarmonyChordContext) -> list[tuple]:
        ...

    @property
    @abstractmethod
    def label(self) -> str:
        ...


class _SustainHarmonyStrategy(HarmonyStrategy):
    """
    Harmony source: "sustain"
    One held event per chord, spanning the full chord window.
    """

    @property
    def label(self) -> str:
        return "sustain"

    def apply(self, ctx: HarmonyChordContext) -> list[tuple]:
        rctx = ctx.harmony_rhythm_ctx
        rhythm_events = [RhythmEvent(
            start_beat=0.0,
            duration_beats=rctx.total_per_chord,
            velocity_scale=1.0,
            is_rest=False,
        )]
        return _build_chord_events(
            rhythm_events, ctx.chord,
            ctx.global_beat, ctx.beat_offset_local,
            ctx.arc, ctx.h_swing, ctx.base_velocity, ctx.channel,
        )


class _PatternHarmonyStrategy(HarmonyStrategy):
    """
    Harmony source: "pattern" (hand-played harmony groove)
    Slices the pre-tiled section event list into this chord's window.
    Falls back to a single sustain event if the slice is empty.
    """

    @property
    def label(self) -> str:
        return "pattern"

    def apply(self, ctx: HarmonyChordContext) -> list[tuple]:
        rctx = ctx.harmony_rhythm_ctx
        if not rctx.precomputed_events or rctx.precomputed_events == "sustain":
            rhythm_events = [RhythmEvent(0.0, rctx.total_per_chord, 1.0, False)]
        else:
            rhythm_events = _slice_events_into_window(
                rctx.precomputed_events,
                rctx.beat_offset,
                rctx.total_per_chord,
                min_duration=0.25,
            )
            if not rhythm_events:
                rhythm_events = [RhythmEvent(0.0, rctx.total_per_chord, 0.7, False)]

        return _build_chord_events(
            rhythm_events, ctx.chord,
            ctx.global_beat, ctx.beat_offset_local,
            ctx.arc, ctx.h_swing, ctx.base_velocity, ctx.channel,
        )


class _MotifHarmonyStrategy(HarmonyStrategy):
    """
    Harmony source: "motif" (stressed articulation — strong beats only)
    Same slice approach as _PatternHarmonyStrategy but with motif-derived events.
    """

    @property
    def label(self) -> str:
        return "motif"

    def apply(self, ctx: HarmonyChordContext) -> list[tuple]:
        rctx = ctx.harmony_rhythm_ctx
        if not rctx.precomputed_events or rctx.precomputed_events == "sustain":
            rhythm_events = [RhythmEvent(0.0, rctx.total_per_chord, 0.7, False)]
        else:
            rhythm_events = _slice_events_into_window(
                rctx.precomputed_events,
                rctx.beat_offset,
                rctx.total_per_chord,
                min_duration=0.25,
            )
            if not rhythm_events:
                rhythm_events = [RhythmEvent(0.0, rctx.total_per_chord, 0.7, False)]

        return _build_chord_events(
            rhythm_events, ctx.chord,
            ctx.global_beat, ctx.beat_offset_local,
            ctx.arc, ctx.h_swing, ctx.base_velocity, ctx.channel,
        )


class _FreeHarmonyStrategy(HarmonyStrategy):
    """
    Harmony source: "free" — density-based grid, same as the legacy default.
    """

    @property
    def label(self) -> str:
        return "free"

    def apply(self, ctx: HarmonyChordContext) -> list[tuple]:
        rctx = ctx.harmony_rhythm_ctx
        rhythm_events = get_pattern(
            rctx.total_per_chord,
            density=rctx.density,
            voice_type="chord",
            groove=rctx.groove,
            beats_per_bar=rctx.beats_per_bar,
        )
        return _build_chord_events(
            rhythm_events, ctx.chord,
            ctx.global_beat, ctx.beat_offset_local,
            ctx.arc, ctx.h_swing, ctx.base_velocity, ctx.channel,
        )


# ═══════════════════════════════════════════════════════════════════════════════
# Melody behavior strategies
# ═══════════════════════════════════════════════════════════════════════════════

class MelodyBehaviorStrategy(ABC):
    """
    Abstract base: generate melody notes for a section.
    Concrete subclasses map one-to-one with VALID_MELODY_BEH values.
    Currently they're thin wrappers — the real logic lives in melody.py.
    The strategy layer gives us a clean home for per-behavior pre/post hooks
    (e.g., generative might want a different default rest_probability).
    """

    @abstractmethod
    def apply(self, ctx: MelodyContext) -> list[MelodyNote]:
        ...

    @property
    @abstractmethod
    def label(self) -> str:
        ...


class _DelegatingMelodyStrategy(MelodyBehaviorStrategy):
    """
    Shared base: all current behaviors delegate to generate_melody_for_progression.
    Subclasses override `label` and can hook `_pre` / `_post` for customization.
    """

    def apply(self, ctx: MelodyContext) -> list[MelodyNote]:
        return generate_melody_for_progression(
            ctx.chords, ctx.key, ctx.mode,
            behavior=ctx.behavior,
            density=ctx.density,
            bars_per_chord=ctx.bars_per_chord,
            beats_per_bar=ctx.beats_per_bar,
            motif=ctx.motif,
            motif_pool=ctx.motif_pool,
            groove=ctx.groove,
            swing=ctx.swing,
            seed=ctx.seed,
            section_name=ctx.section_name,
            rhythm_events_override=ctx.rhythm_events_override,
            fugal_techniques=ctx.fugal_techniques,
            rest_probability=ctx.rest_probability,
        )


class LyricalMelodyStrategy(_DelegatingMelodyStrategy):
    @property
    def label(self) -> str:
        return "lyrical"


class GenerativeMelodyStrategy(_DelegatingMelodyStrategy):
    @property
    def label(self) -> str:
        return "generative"


class MotifMelodyStrategy(_DelegatingMelodyStrategy):
    @property
    def label(self) -> str:
        return "motif"


class SparseMelodyStrategy(_DelegatingMelodyStrategy):
    @property
    def label(self) -> str:
        return "sparse"


class RhythmicMelodyStrategy(_DelegatingMelodyStrategy):
    @property
    def label(self) -> str:
        return "rhythmic"


class DevelopMelodyStrategy(_DelegatingMelodyStrategy):
    @property
    def label(self) -> str:
        return "develop"


# ═══════════════════════════════════════════════════════════════════════════════
# Registries — single point of dispatch, no if/elif anywhere else
# ═══════════════════════════════════════════════════════════════════════════════

class _StrategyRegistry:
    """
    Generic string → strategy lookup. Raises KeyError with a clear message
    so the validator catches bad values before they hit generation.
    """

    def __init__(self, strategies: list, name: str):
        self._map: dict[str, object] = {s.label: s for s in strategies}
        self._name = name

    def resolve(self, key: str) -> object:
        try:
            return self._map[key]
        except KeyError:
            valid = sorted(self._map)
            raise KeyError(
                f"Unknown {self._name} '{key}'. Valid options: {valid}"
            ) from None

    def register(self, strategy) -> None:
        """Add a new strategy at runtime (e.g., plugins, tests)."""
        self._map[strategy.label] = strategy


RhythmStrategyRegistry = _StrategyRegistry(
    strategies=[
        PatternRhythmStrategy(),
        MotifRhythmStrategy(),
        FreeRhythmStrategy(),
    ],
    name="rhythm source",
)

HarmonyRhythmStrategyRegistry = _StrategyRegistry(
    strategies=[
        SustainHarmonyStrategy(),
        PatternHarmonyStrategy(),
        MotifHarmonyStrategy(),
        FreeHarmonyStrategy(),
    ],
    name="harmony rhythm source",
)

HarmonyStrategyRegistry = _StrategyRegistry(
    strategies=[
        _SustainHarmonyStrategy(),
        _PatternHarmonyStrategy(),
        _MotifHarmonyStrategy(),
        _FreeHarmonyStrategy(),
    ],
    name="harmony source",
)

MelodyStrategyRegistry = _StrategyRegistry(
    strategies=[
        LyricalMelodyStrategy(),
        GenerativeMelodyStrategy(),
        MotifMelodyStrategy(),
        SparseMelodyStrategy(),
        RhythmicMelodyStrategy(),
        DevelopMelodyStrategy(),
    ],
    name="melody behavior",
)


# ═══════════════════════════════════════════════════════════════════════════════
# Context factory — builds typed context objects from the raw section dict
# ═══════════════════════════════════════════════════════════════════════════════

def build_rhythm_context(
    section: dict,
    active_motif_def: Optional[dict],
    total_beats: float,
    base_seed: int,
    seed_offset: int,
) -> RhythmContext:
    """
    Construct a RhythmContext from the raw section dict and resolved motif.
    This is the one place that knows the section dict's key names.
    """
    rhythm_source = section.get("rhythm", "free")
    density = section.get("density", "medium")
    beats_per_bar = int(section.get("beats_per_bar", 4))

    motif_rhythm = None
    motif_velocities = None
    if active_motif_def and rhythm_source == "motif":
        motif_rhythm = active_motif_def.get("rhythm")
        motif_velocities = active_motif_def.get("velocities")

    return RhythmContext(
        source=rhythm_source,
        total_beats=total_beats,
        density=density,
        rhythm_pattern=section.get("rhythm_pattern") if rhythm_source == "pattern" else None,
        motif_rhythm=motif_rhythm,
        motif_velocities=motif_velocities,
        groove=section.get("groove"),
        swing=float(section.get("swing", 0.0)),
        beats_per_bar=beats_per_bar,
        seed=base_seed + seed_offset,
    )


def build_harmony_rhythm_context(
    section: dict,
    active_motif_def: Optional[dict],
    total_beats_section: float,
    total_per_chord: float,
    beat_offset: float,
    precomputed_events,           # list[RhythmEvent] | "sustain" | None
) -> HarmonyRhythmContext:
    """
    Construct a HarmonyRhythmContext for a single chord window.

    Absorbs all harmony_rhythm block overrides (density, groove, swing)
    so callers never touch the raw section dict for these values.
    The resolved source field drives HarmonyStrategyRegistry dispatch.
    """
    _hr_raw = section.get("harmony_rhythm", {})
    _hr_block: dict = {"rhythm": _hr_raw} if isinstance(_hr_raw, str) else _hr_raw

    rhythm_fallback = section.get("rhythm", "free")
    h_source   = _hr_block.get("rhythm",   rhythm_fallback)

    # HR block can override density, groove, and swing per-section.
    # Falls back to the section-level values so omitting the field is safe.
    h_density  = _hr_block.get("density",  section.get("density",  "medium"))
    h_groove   = _hr_block.get("groove",   section.get("groove"))
    h_swing    = float(_hr_block.get("swing", section.get("swing", 0.0)))
    beats_per_bar = int(section.get("beats_per_bar", 4))

    motif_rhythm = None
    motif_velocities = None
    if active_motif_def and h_source == "motif":
        motif_rhythm = active_motif_def.get("rhythm")
        motif_velocities = active_motif_def.get("velocities")

    return HarmonyRhythmContext(
        source=h_source,
        total_beats_section=total_beats_section,
        total_per_chord=total_per_chord,
        beat_offset=beat_offset,
        density=h_density,
        groove=h_groove,
        swing=h_swing,
        beats_per_bar=beats_per_bar,
        harmony_pattern=section.get("harmony_pattern") if h_source == "pattern" else None,
        motif_rhythm=motif_rhythm,
        motif_velocities=motif_velocities,
        precomputed_events=precomputed_events,
    )


def build_harmony_chord_context(
    harmony_rhythm_ctx: HarmonyRhythmContext,
    chord: VoicedChord,
    global_beat: float,
    beat_offset_local: float,
    arc: str,
    base_velocity: int = 65,
    channel: int = _CHANNEL_HARMONY,
) -> HarmonyChordContext:
    """
    Construct a HarmonyChordContext for one chord in the section loop.
    Called once per chord by the generate_piece loop.

    swing is no longer a direct parameter — it is read from harmony_rhythm_ctx
    via the h_swing property so the caller has zero manual HR field handling.
    """
    return HarmonyChordContext(
        chord=chord,
        harmony_rhythm_ctx=harmony_rhythm_ctx,
        global_beat=global_beat,
        beat_offset_local=beat_offset_local,
        arc=arc,
        base_velocity=base_velocity,
        channel=channel,
    )


def build_melody_context(
    section: dict,
    chords: list[VoicedChord],
    key: str,
    mode: str,
    bars_list: list[float],
    active_motif_def: Optional[dict],
    motif_pool: list[dict],
    melody_rhythm_events: Optional[list[RhythmEvent]],
    base_seed: int,
    seed_offset: int,
) -> MelodyContext:
    """
    Construct a MelodyContext from resolved section + voice data.
    """
    return MelodyContext(
        behavior=section.get("melody", "generative"),
        chords=chords,
        key=key,
        mode=mode,
        density=section.get("density", "medium"),
        bars_per_chord=bars_list,
        beats_per_bar=int(section.get("beats_per_bar", 4)),
        motif=active_motif_def,
        motif_pool=motif_pool if len(motif_pool) > 1 else None,
        groove=section.get("groove"),
        swing=float(section.get("swing", 0.0)),
        seed=base_seed + seed_offset,
        section_name=section.get("name", ""),
        rhythm_events_override=melody_rhythm_events,
        fugal_techniques=section.get("fugal_techniques"),
        rest_probability=float(section.get("rest_probability", 0.0)),
    )
