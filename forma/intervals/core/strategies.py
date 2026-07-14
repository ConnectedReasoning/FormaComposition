"""
strategies.py — translation layer between a validated section and harmony's generation.

Scope note (item 9, ST-0): this module used to advertise a Strategy Pattern for
EVERY voice — RhythmStrategy/MelodyStrategy registries meant to replace the
if/elif switchboards in generate_section(). Those were never wired up: the
registries had no callers, and the melody wrappers turned out to hold no logic
at all (generator.py calls melody.py directly). They have been deleted rather
than reconnected — per-voice dispatch belongs inside each voice module, the way
counterpoint.py and bass.py already do it, not centralised in core/.

What remains is harmony's path only, and only until item 9's later sub-tasks
relocate it into harmony.py:

  HarmonyRhythmContext  — section-scoped harmony rhythm config
  HarmonyChordContext   — one chord's slice of it, plus the arc state
  HarmonyStrategy       — abstract base; one subclass per harmony rhythm source
  HarmonyStrategyRegistry — source label → strategy lookup

Plus three voice-agnostic tiling helpers (rhythm_pattern_to_events,
_motif_rhythm_to_events, _slice_events_into_window) that are shared by melody
and harmony and live here only to avoid a circular import with generator.
"""

from __future__ import annotations

import random
import statistics as _stats
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Optional

from intervals.core.musical_time import MusicalTime, bar_beat_from_event_offset
from intervals.music.rhythm import (
    RhythmEvent, get_pattern,
    apply_velocity_arc, apply_swing, remap_swing_ratio,
)
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
    rests: Optional[list] = None,
) -> list[RhythmEvent]:
    """
    Convert a motif rhythm (list of beat durations) to a tiled list of
    RhythmEvent covering total_beats.

    articulation controls onset density per voice:
      "full"     — every onset (melody)
      "stressed" — onsets >= median duration (harmony)
      "anchor"   — downbeat only (bass)

    rests: optional, same length as rhythm. True = this slot is silent and
    is excluded from the emitted events regardless of articulation mode —
    a rest never sounds, whether or not it would otherwise have been kept.
    The slot's duration still occupies its place in the timing grid (onsets
    for every other slot are computed exactly as if the rest weren't there),
    it's just never selected into the output.
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

    if rests is not None:
        keep = [i for i in keep if not (i < len(rests) and rests[i])]

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
class HarmonyRhythmContext:
    """
    Context data for harmony chord rhythm resolution.
    Consumed by HarmonyStrategyRegistry dispatch (_*HarmonyStrategy.apply).
    """
    source: str                        # "sustain" | "pattern" | "motif" | "free"
    total_beats_section: float         # full section length (for pattern tiling)
    total_per_chord: float             # this chord window's beat length
    beat_offset: float                 # absolute offset of this chord in section

    density: str
    groove: Optional[str] = None
    beats_per_bar: int = 4
    swing: float = 0.0

    # Hand-played harmony pattern (optional, used by _PatternHarmonyStrategy)
    harmony_pattern: Optional[dict] = None

    # Motif rhythm fields
    motif_rhythm: Optional[list[float]] = None
    motif_velocities: Optional[list[float]] = None

    # Pre-resolved section events (passed through from pre-computation step)
    # Kept as an escape hatch so the refactor doesn't break the existing
    # _resolve_harmony_rhythm call in generate_piece.
    precomputed_events: Optional[list] = None   # list[RhythmEvent] or "sustain"

    # Seed for deterministic chord-level rhythm generation.
    # Derived from piece base_seed + section_index * 10 + chord_index
    # so every chord gets unique but reproducible variation.
    seed: int = 42


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

    musical_time is the absolute position of this chord's downbeat expressed
    as MusicalTime. Strategy subclasses can query t.is_downbeat(), t.is_beat(3),
    t.is_bar_mod(2), etc. to build position-aware articulation rules without
    any float modulo arithmetic.
    """
    chord: VoicedChord                 # chord whose notes are voiced
    harmony_rhythm_ctx: HarmonyRhythmContext

    # Absolute timing for this chord within the piece
    global_beat: float                 # beat offset of the whole section
    beat_offset_local: float           # beat offset within the section

    # Articulation / expression
    arc: str                           # velocity arc shape (e.g. "swell")
    # This chord's normalised position within its SECTION: 0.0 at the section's
    # first chord, 1.0 at its last. The arc curve advances across these, so a
    # section's dynamic shape spans the whole section rather than restarting at
    # every chord. Computed by generate_piece()'s harmony loop, which is the
    # only place that knows the section's chord layout.
    arc_t: float = 0.0
    # The previous section's final arc multiplier, and how much of THIS section
    # (in t units) is spent easing from it into this section's own curve.
    # None = first section in the form: start on our own curve, nothing to ease from.
    prev_arc_end: Optional[float] = None
    arc_blend_t: float = 0.0
    base_velocity: int = 65
    channel: int = _CHANNEL_HARMONY

    # Per-section harmony rest probability. Passed straight into
    # _build_chord_events, which no-ops it on the "sustain" source and on any
    # single-onset chord window (see that function's rest-thinning block).
    harmony_rest_probability: float = 0.0

    # Optional MusicalTime for the chord's absolute onset position.
    # When present, strategies can use bar-aware predicates directly.
    musical_time: Optional[MusicalTime] = None

    @property
    def h_swing(self) -> float:
        """Convenience accessor — swing lives on the rhythm context."""
        return self.harmony_rhythm_ctx.swing

    @property
    def onset(self) -> MusicalTime:
        """The chord's absolute onset as MusicalTime.

        Falls back to computing from global_beat + beat_offset_local when
        musical_time is not explicitly provided (backward compatible).
        """
        if self.musical_time is not None:
            return self.musical_time
        return MusicalTime.from_beats(
            self.global_beat + self.beat_offset_local,
            beats_per_bar=self.harmony_rhythm_ctx.beats_per_bar,
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
    rest_probability: float = 0.0,
    rest_seed: int = 0,
    source: str = "",
    arc_t: float = 0.0,
    prev_arc_end: Optional[float] = None,
    arc_blend_t: float = 0.0,
) -> list[tuple]:
    """
    Shared event-building kernel.  Given a list of RhythmEvents for one chord
    window, apply swing → velocity arc → rest thinning → rearticulation gap,
    then expand into (abs_beat, 'on'/'off', note, vel, channel) tuples for
    every MIDI note in the chord.

    This is the single place that knows the output tuple format.

    rest_probability thins the chord's onsets: each onset is independently
    dropped with this probability, seeded from rest_seed for determinism.
    It is deliberately a no-op when source == "sustain" or when the window
    has a single onset — a rest roll there would delete the whole chord
    rather than thin it, which is never the intent for a harmony bed.
    """
    # h_swing is the public 0.0-1.0 field; apply_swing() expects the internal
    # 0.5-straight scale, so convert first (see remap_swing_ratio docstring).
    if h_swing and h_swing > 0:
        rhythm_events = apply_swing(rhythm_events, swing_ratio=remap_swing_ratio(h_swing))

    arced = apply_velocity_arc(
        rhythm_events, arc=arc, base_velocity=base_velocity, arc_t=arc_t,
        prev_arc_end=prev_arc_end, arc_blend_t=arc_blend_t,
    )
    arced_list = [(ev, vel) for ev, vel in arced if not ev.is_rest]

    # Per-section harmony rest thinning. Guarded so it only ever thins a
    # multi-onset window: on "sustain" (or any window that resolved to a
    # single event) a rest roll would drop the entire chord, so skip it.
    if rest_probability > 0.0 and source != "sustain" and len(arced_list) > 1:
        rng = random.Random(rest_seed)
        arced_list = [
            (ev, vel) for (ev, vel) in arced_list
            if rng.random() >= rest_probability
        ]

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
            rest_probability=ctx.harmony_rest_probability,
            rest_seed=rctx.seed, source=rctx.source, arc_t=ctx.arc_t,
            prev_arc_end=ctx.prev_arc_end, arc_blend_t=ctx.arc_blend_t,
        )


class _PatternHarmonyStrategy(HarmonyStrategy):
    """
    Harmony source: "pattern" (hand-played harmony groove)

    Priority dispatch:
      1. chord.rhythm_events       — DNA: pre-enriched chord-local events. Use as-is.
      2. rctx.precomputed_events   — global stencil: slice on demand (legacy path).
      3. Single sustain event      — fallback when both sources are absent or empty.
    """

    @property
    def label(self) -> str:
        return "pattern"

    def apply(self, ctx: HarmonyChordContext) -> list[tuple]:
        rctx = ctx.harmony_rhythm_ctx

        # Priority 1 — DNA path: chord was pre-enriched by _enrich_chords_with_rhythm.
        # Events are already in chord-local coordinates; use them directly.
        if ctx.chord.rhythm_events:
            rhythm_events = ctx.chord.rhythm_events

        # Priority 2 — global stencil: slice from section-level tiled events.
        # This is the legacy path for any chord that was not enriched.
        elif rctx.precomputed_events and rctx.precomputed_events != "sustain":
            rhythm_events = _slice_events_into_window(
                rctx.precomputed_events,
                rctx.beat_offset,
                rctx.total_per_chord,
                min_duration=0.25,
            )
            if not rhythm_events:
                rhythm_events = [RhythmEvent(0.0, rctx.total_per_chord, 0.7, False)]

        # Priority 3 — sustain fallback.
        else:
            rhythm_events = [RhythmEvent(0.0, rctx.total_per_chord, 1.0, False)]

        return _build_chord_events(
            rhythm_events, ctx.chord,
            ctx.global_beat, ctx.beat_offset_local,
            ctx.arc, ctx.h_swing, ctx.base_velocity, ctx.channel,
            rest_probability=ctx.harmony_rest_probability,
            rest_seed=rctx.seed, source=rctx.source, arc_t=ctx.arc_t,
            prev_arc_end=ctx.prev_arc_end, arc_blend_t=ctx.arc_blend_t,
        )


class _MotifHarmonyStrategy(HarmonyStrategy):
    """
    Harmony source: "motif" — reintroduced 2026-07 as an independent
    per-section onset stream (see the HarmonyRhythmSourceLiteral comment
    in schemas.py for the full history/design rationale).

    generator.py's generate_section() resolves harmony's own motif
    (harmony_rhythm.motif, falling back to the section's active theme
    motif) and tiles its rhythm across the WHOLE section — independent of
    chord-change points — into harmony_section_events, honoring density
    via onset articulation (full/stressed/anchor). _enrich_chords_with_rhythm
    then slices that continuous stream into each chord's local window and
    attaches it as chord.rhythm_events (the DNA path below), so a comping
    pattern keeps its own life through a chord change rather than
    resetting at every chord boundary.

    Priority dispatch mirrors _PatternHarmonyStrategy — same consumption
    shape, different upstream source for the section-wide event list:
      1. chord.rhythm_events       — DNA: pre-enriched chord-local events.
      2. rctx.precomputed_events   — global motif stencil, sliced on demand
                                      (legacy path — DNA should cover every
                                      chord once enrichment runs, but this
                                      stays as the same escape hatch
                                      _PatternHarmonyStrategy keeps).
      3. Single sustain event      — fallback.
    """

    @property
    def label(self) -> str:
        return "motif"

    def apply(self, ctx: HarmonyChordContext) -> list[tuple]:
        rctx = ctx.harmony_rhythm_ctx

        # Priority 1 — DNA path.
        if ctx.chord.rhythm_events:
            rhythm_events = ctx.chord.rhythm_events

        # Priority 2 — global motif stencil slice (legacy path).
        elif rctx.precomputed_events and rctx.precomputed_events != "sustain":
            rhythm_events = _slice_events_into_window(
                rctx.precomputed_events,
                rctx.beat_offset,
                rctx.total_per_chord,
                min_duration=0.25,
            )
            if not rhythm_events:
                rhythm_events = [RhythmEvent(0.0, rctx.total_per_chord, 0.7, False)]

        # Priority 3 — sustain fallback.
        else:
            rhythm_events = [RhythmEvent(0.0, rctx.total_per_chord, 0.7, False)]

        return _build_chord_events(
            rhythm_events, ctx.chord,
            ctx.global_beat, ctx.beat_offset_local,
            ctx.arc, ctx.h_swing, ctx.base_velocity, ctx.channel,
            rest_probability=ctx.harmony_rest_probability,
            rest_seed=rctx.seed, source=rctx.source, arc_t=ctx.arc_t,
            prev_arc_end=ctx.prev_arc_end, arc_blend_t=ctx.arc_blend_t,
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
            seed=rctx.seed,
        )
        return _build_chord_events(
            rhythm_events, ctx.chord,
            ctx.global_beat, ctx.beat_offset_local,
            ctx.arc, ctx.h_swing, ctx.base_velocity, ctx.channel,
            rest_probability=ctx.harmony_rest_probability,
            rest_seed=rctx.seed, source=rctx.source, arc_t=ctx.arc_t,
            prev_arc_end=ctx.prev_arc_end, arc_blend_t=ctx.arc_blend_t,
        )


# ═══════════════════════════════════════════════════════════════════════════════
# Registry — harmony source label → strategy
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


# ---------------------------------------------------------------------------
# Active production dispatch path for harmony resolution.
# HarmonyStrategyRegistry is the sole entry point for selecting how a chord
# window is rendered to MIDI events.  All call sites use .resolve(source)
# to obtain the appropriate _*HarmonyStrategy and call .apply(ctx) on it.
# ---------------------------------------------------------------------------
HarmonyStrategyRegistry = _StrategyRegistry(
    strategies=[
        _SustainHarmonyStrategy(),
        _PatternHarmonyStrategy(),
        _MotifHarmonyStrategy(),
        _FreeHarmonyStrategy(),
    ],
    name="harmony source",
)


# ═══════════════════════════════════════════════════════════════════════════════
# Context factory — harmony chord context
# ═══════════════════════════════════════════════════════════════════════════════


def build_harmony_chord_context(
    harmony_rhythm_ctx: HarmonyRhythmContext,
    chord: VoicedChord,
    global_beat: float,
    beat_offset_local: float,
    arc: str,
    arc_t: float = 0.0,
    prev_arc_end: Optional[float] = None,
    arc_blend_t: float = 0.0,
    base_velocity: int = 65,
    channel: int = _CHANNEL_HARMONY,
    musical_time: Optional[MusicalTime] = None,
    harmony_rest_probability: float = 0.0,
) -> HarmonyChordContext:
    """
    Construct a HarmonyChordContext for one chord in the section loop.
    Called once per chord by the generate_piece loop.

    musical_time, when provided, becomes ctx.onset — a MusicalTime representing
    the chord's absolute position. If omitted, ctx.onset computes it lazily from
    global_beat + beat_offset_local (backward compatible).

    swing is no longer a direct parameter — it is read from harmony_rhythm_ctx
    via the h_swing property so the caller has zero manual HR field handling.
    """
    # If caller didn't supply musical_time, derive it from the float offsets.
    if musical_time is None:
        musical_time = MusicalTime.from_beats(
            global_beat + beat_offset_local,
            beats_per_bar=harmony_rhythm_ctx.beats_per_bar,
        )
    return HarmonyChordContext(
        chord=chord,
        harmony_rhythm_ctx=harmony_rhythm_ctx,
        global_beat=global_beat,
        beat_offset_local=beat_offset_local,
        arc=arc,
        arc_t=arc_t,
        prev_arc_end=prev_arc_end,
        arc_blend_t=arc_blend_t,
        base_velocity=base_velocity,
        channel=channel,
        musical_time=musical_time,
        harmony_rest_probability=harmony_rest_probability,
    )
