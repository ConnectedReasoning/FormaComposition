"""
rhythm.py — Intervals Engine
Rhythmic pattern generation with groove templates, density, and swing.

Three independent axes:
  groove    — where notes land within a bar (the pattern/feel)
  density   — how many slots are active (sparse/medium/full)
  swing     — timing push on offbeats. Public-facing field (section.swing,
              harmony_rhythm.swing, drums.swing) is 0.0-1.0 where 0.0 = off
              and 1.0 = heaviest swing. That is NOT the same scale apply_swing()
              and _apply_swing_to_drums() operate on internally (0.5 = straight,
              0.67 = triplet, 1.0 = heavy) — always convert public swing values
              through remap_swing_ratio() before passing them in. Passing a raw
              public swing value (e.g. 0.2) directly as swing_ratio pushes
              offbeats EARLY instead of late; see remap_swing_ratio() docstring.

Timing humanization (correlated jitter across voices) is handled by the
groove pass in apply_groove.py, not per-voice. Per-voice independent jitter
is deliberately absent — it produces anti-group-time behaviour.

Rhythm is expressed in beats (float), tempo-agnostic.
The generator converts beats → MIDI ticks using tempo + PPQ.

Groove is optional. When no groove is specified, behavior falls through
to the original density-based grid patterns for full backward compatibility.
"""

import random
import math
from dataclasses import dataclass
from typing import Optional

from intervals.core.musical_time import MusicalTime, is_downbeat_float

# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------

@dataclass
class RhythmEvent:
    """A single rhythmic event — a slot in time with an onset and duration."""
    start_beat: float
    duration_beats: float
    velocity_scale: float = 1.0   # multiplier applied to base velocity (0.0–1.0)
    is_rest: bool = False

    def __repr__(self):
        kind = "REST" if self.is_rest else "NOTE"
        return f"RhythmEvent({kind} beat={self.start_beat:.2f} dur={self.duration_beats:.2f} vel={self.velocity_scale:.2f})"


# ═══════════════════════════════════════════════════════════════════════════
# GROOVE SYSTEM
# ═══════════════════════════════════════════════════════════════════════════

@dataclass
class GrooveSlot:
    """A single slot in a per-bar groove template."""
    beat: float           # position within a bar (0.0–3.999 for 4/4)
    duration: float       # note duration in beats
    velocity_scale: float # velocity multiplier (1.0 = full, 0.4 = ghost)
    priority: int         # 1=primary, 2=secondary, 3=ghost/fill


# ---------------------------------------------------------------------------
# Groove templates
# ---------------------------------------------------------------------------
# Each groove is a per-bar template (assumes 4/4 unless noted).
# Priority controls density filtering:
#   1 = primary (always plays, even at sparse)
#   2 = secondary (plays at medium+)
#   3 = ghost/fill (plays at full only)

GROOVES = {
    # ── straight ──────────────────────────────────────────────────────
    # Even quarter notes, accented on 1 and 3. The vanilla grid.
    "straight": [
        GrooveSlot(0.0, 1.0, 1.00, 1),
        GrooveSlot(1.0, 1.0, 0.80, 2),
        GrooveSlot(2.0, 1.0, 0.95, 1),
        GrooveSlot(3.0, 1.0, 0.75, 2),
    ],

    # ── push ──────────────────────────────────────────────────────────
    # Anticipates beat 1 and 3 by an eighth note. Forward momentum.
    "push": [
        GrooveSlot(0.0, 0.5, 1.00, 1),    # beat 1
        GrooveSlot(1.5, 0.5, 0.70, 3),    # ghost push
        GrooveSlot(2.0, 0.5, 0.85, 1),    # beat 3
        GrooveSlot(2.5, 0.5, 0.90, 2),    # anticipate beat 3
        GrooveSlot(3.5, 0.5, 0.90, 2),    # anticipate next bar
    ],

    # ── backbeat ──────────────────────────────────────────────────────
    # Accents on 2 and 4. Classic pop/soul feel.
    "backbeat": [
        GrooveSlot(0.0, 1.0, 0.70, 2),    # beat 1 (soft)
        GrooveSlot(0.5, 0.5, 0.45, 3),    # ghost &-of-1
        GrooveSlot(1.0, 1.0, 1.00, 1),    # beat 2 (ACCENT)
        GrooveSlot(2.0, 1.0, 0.65, 2),    # beat 3 (soft)
        GrooveSlot(2.5, 0.5, 0.45, 3),    # ghost &-of-3
        GrooveSlot(3.0, 1.0, 1.00, 1),    # beat 4 (ACCENT)
    ],

    # ── syncopated ────────────────────────────────────────────────────
    # Offbeat emphasis. Latin / bossa influenced.
    "syncopated": [
        GrooveSlot(0.0, 0.75, 1.00, 1),   # beat 1 (short)
        GrooveSlot(1.0, 0.5,  0.50, 3),   # ghost beat 2
        GrooveSlot(1.5, 1.0,  0.90, 1),   # &-of-2 (ACCENT)
        GrooveSlot(2.5, 0.75, 0.85, 2),   # &-of-3
        GrooveSlot(3.0, 0.5,  0.60, 3),   # beat 4 (ghost)
        GrooveSlot(3.5, 0.5,  0.80, 2),   # &-of-4 (pickup)
    ],

    # ── halftime ──────────────────────────────────────────────────────
    # Wide spacing, emphasis on 1 and 3. Cinematic, lo-fi, spacious.
    "halftime": [
        GrooveSlot(0.0, 2.0, 1.00, 1),    # beat 1 (long)
        GrooveSlot(2.0, 2.0, 0.85, 1),    # beat 3 (long)
        GrooveSlot(1.0, 0.5, 0.45, 3),    # ghost beat 2
        GrooveSlot(3.5, 0.5, 0.50, 3),    # ghost pickup
    ],

    # ── shuffle ───────────────────────────────────────────────────────
    # Triplet-based grid. Swing is baked in — don't apply swing on top.
    "shuffle": [
        GrooveSlot(0.0,    0.67, 1.00, 1),
        GrooveSlot(0.67,   0.33, 0.70, 2),
        GrooveSlot(1.0,    0.67, 0.85, 2),
        GrooveSlot(1.67,   0.33, 0.55, 3),
        GrooveSlot(2.0,    0.67, 0.95, 1),
        GrooveSlot(2.67,   0.33, 0.70, 2),
        GrooveSlot(3.0,    0.67, 0.80, 2),
        GrooveSlot(3.67,   0.33, 0.55, 3),
    ],

    # ── broken ────────────────────────────────────────────────────────
    # 3+3+2 grouping over 4/4. Afro-Cuban tresillo.
    "broken": [
        GrooveSlot(0.0,  0.75, 1.00, 1),
        GrooveSlot(0.75, 0.25, 0.40, 3),
        GrooveSlot(1.5,  0.75, 0.90, 1),
        GrooveSlot(2.25, 0.25, 0.40, 3),
        GrooveSlot(3.0,  1.0,  0.85, 1),
        GrooveSlot(3.5,  0.5,  0.60, 2),
    ],

    # ── clave ─────────────────────────────────────────────────────────
    # 3-2 son clave.
    "clave": [
        GrooveSlot(0.0, 0.75, 1.00, 1),
        GrooveSlot(1.5, 0.75, 0.90, 1),
        GrooveSlot(3.0, 0.5,  0.85, 1),
        GrooveSlot(1.0, 0.5,  0.45, 3),
        GrooveSlot(2.0, 0.5,  0.50, 2),
    ],

    # ── waltz ─────────────────────────────────────────────────────────
    # 3/4 feel: strong-weak-weak. Use with beats_per_bar=3.
    "waltz": [
        GrooveSlot(0.0, 1.0, 1.00, 1),
        GrooveSlot(1.0, 1.0, 0.65, 2),
        GrooveSlot(2.0, 1.0, 0.60, 2),
        GrooveSlot(0.5, 0.5, 0.40, 3),
    ],

    # ── offbeat ───────────────────────────────────────────────────────
    # All events on the &'s. Reggae / dub / ska feel.
    "offbeat": [
        GrooveSlot(0.5, 0.5, 1.00, 1),
        GrooveSlot(1.5, 0.5, 0.90, 1),
        GrooveSlot(2.5, 0.5, 0.85, 2),
        GrooveSlot(3.5, 0.5, 0.80, 2),
        GrooveSlot(0.0, 0.25, 0.35, 3),
        GrooveSlot(2.0, 0.25, 0.35, 3),
    ],

    # ── driving ───────────────────────────────────────────────────────
    # Eighth note pulse. Motorik / krautrock / mid-tempo drive.
    "driving": [
        GrooveSlot(0.0, 0.5, 1.00, 1),
        GrooveSlot(0.5, 0.5, 0.70, 2),
        GrooveSlot(1.0, 0.5, 0.85, 1),
        GrooveSlot(1.5, 0.5, 0.65, 3),
        GrooveSlot(2.0, 0.5, 0.95, 1),
        GrooveSlot(2.5, 0.5, 0.70, 2),
        GrooveSlot(3.0, 0.5, 0.80, 2),
        GrooveSlot(3.5, 0.5, 0.65, 3),
    ],
}

VALID_GROOVES = list(GROOVES.keys())

DENSITY_PRIORITY = {
    "sparse": 1,
    "medium": 2,
    "full":   3,
}


def groove_pattern(
    total_beats: float,
    groove: str = "straight",
    density: str = "medium",
    beats_per_bar: int = 4,
    rest_probability: float = 0.0,
    seed: Optional[int] = None,
) -> list[RhythmEvent]:
    """
    Generate a rhythm pattern from a named groove template.
    The groove template defines per-bar slot positions with priorities.
    Density filters which priority levels are active.
    The template tiles across total_beats.
    """
    if seed is None:
        raise ValueError(f"Deterministic generation requires an explicit seed in {__name__}")
    rng = random.Random(seed)

    if groove not in GROOVES:
        raise ValueError(f"Unknown groove: '{groove}'. Choose from: {VALID_GROOVES}")

    template = GROOVES[groove]

    if density == "low":
        # "low" sits between sparse (priority 1 only, always) and medium
        # (priority 1+2, always): priority 1 slots are always active;
        # priority 2 slots are included probabilistically per bar
        # occurrence rather than deterministically every bar. Priority
        # is a strict int (1/2/3), so this can't be expressed as a
        # numeric threshold alone — it needs this per-bar randomization
        # instead.
        primary_slots = sorted([s for s in template if s.priority == 1], key=lambda s: s.beat)
        secondary_slots = sorted([s for s in template if s.priority == 2], key=lambda s: s.beat)
        if not primary_slots:
            primary_slots = [template[0]]

        events = []
        bar_start = 0.0

        while bar_start < total_beats - 0.001:
            for slot in primary_slots:
                abs_beat = bar_start + slot.beat
                if abs_beat >= total_beats - 0.001:
                    continue
                dur = min(slot.duration, total_beats - abs_beat)
                is_rest = rng.random() < rest_probability
                events.append(RhythmEvent(abs_beat, dur, slot.velocity_scale, is_rest))

            if secondary_slots and rng.random() < 0.4:
                for slot in secondary_slots:
                    abs_beat = bar_start + slot.beat
                    if abs_beat >= total_beats - 0.001:
                        continue
                    dur = min(slot.duration, total_beats - abs_beat)
                    is_rest = rng.random() < rest_probability
                    events.append(RhythmEvent(abs_beat, dur, slot.velocity_scale, is_rest))

            bar_start += beats_per_bar

        events.sort(key=lambda e: e.start_beat)
        return events

    max_priority = DENSITY_PRIORITY.get(density, 2)

    active_slots = [s for s in template if s.priority <= max_priority]
    if not active_slots:
        active_slots = [s for s in template if s.priority == 1] or [template[0]]

    active_slots.sort(key=lambda s: s.beat)

    events = []
    bar_start = 0.0

    while bar_start < total_beats - 0.001:
        for slot in active_slots:
            abs_beat = bar_start + slot.beat
            if abs_beat >= total_beats - 0.001:
                continue
            dur = min(slot.duration, total_beats - abs_beat)
            is_rest = rng.random() < rest_probability
            events.append(RhythmEvent(abs_beat, dur, slot.velocity_scale, is_rest))
        bar_start += beats_per_bar

    events.sort(key=lambda e: e.start_beat)
    return events



# ═══════════════════════════════════════════════════════════════════════════
# ORIGINAL GRID-BASED SYSTEM (preserved for backward compatibility)
# ═══════════════════════════════════════════════════════════════════════════

def grid(
    total_beats: float,
    subdivision: float,
    rest_probability: float = 0.0,
    accent_beats: Optional[list[float]] = None,
    accent_boost: float = 0.15,
    seed: Optional[int] = None,
    **kwargs,
) -> list[RhythmEvent]:
    """Build a uniform grid of RhythmEvents."""
    if seed is None:
        raise ValueError(f"Deterministic generation requires an explicit seed in {__name__}")
    rng = random.Random(seed)
    if accent_beats is None:
        accent_beats = []

    events = []
    beat = 0.0
    while beat < total_beats - 0.001:
        dur = min(subdivision, total_beats - beat)
        is_rest = rng.random() < rest_probability
        # Use MusicalTime so this respects beats_per_bar rather than hardcoding 4.0
        beat_in_bar = MusicalTime.from_beats(beat, beats_per_bar=int(kwargs.get("beats_per_bar", 4))).beat
        vel = 1.0
        if any(abs(beat_in_bar - a) < 0.001 for a in accent_beats):
            vel = min(1.0, vel + accent_boost)
        else:
            vel = max(0.5, vel - 0.05)
        events.append(RhythmEvent(beat, dur, vel, is_rest))
        beat += subdivision
    return events


def pattern_whole(total_beats: float, **kwargs) -> list[RhythmEvent]:
    """One note per chord — whole notes. Used by bass sparse."""
    return grid(total_beats, subdivision=total_beats, rest_probability=0.0,
                accent_beats=[0.0], **kwargs)

def pattern_half(total_beats: float, **kwargs) -> list[RhythmEvent]:
    """Half note grid. Used by bass medium."""
    return grid(total_beats, subdivision=2.0, rest_probability=0.1,
                accent_beats=[0.0, 2.0], **kwargs)

def pattern_quarter(total_beats: float, **kwargs) -> list[RhythmEvent]:
    """Quarter note grid. Used by bass full."""
    return grid(total_beats, subdivision=1.0, rest_probability=0.15,
                accent_beats=[0.0, 2.0], **kwargs)

def pattern_quarter_sparse(total_beats: float, **kwargs) -> list[RhythmEvent]:
    """Quarter note grid with more rests."""
    return grid(total_beats, subdivision=1.0, rest_probability=0.40,
                accent_beats=[0.0], **kwargs)


# ---------------------------------------------------------------------------
# Chord-specific patterns (how a player actually articulates chords)
# ---------------------------------------------------------------------------

def pattern_chord_sparse(total_beats: float, beats_per_bar: int = 4,
                         seed: Optional[int] = None, **kwargs) -> list[RhythmEvent]:
    """
    Sparse chord articulation: re-strike at bar boundaries.

    A pad player's rhythm — hold a long note, then re-articulate on beat 1
    of the next bar. For a 5-bar chord you hear 5 attacks, each sustained,
    with beat 1 of the first bar strongest and subsequent bars gentler.
    Not one 20-beat wall.
    """
    if seed is None:
        raise ValueError(f"Deterministic generation requires an explicit seed in {__name__}")
    rng = random.Random(seed)

    events = []
    beat = 0.0
    bar_index = 0

    while beat < total_beats - 0.001:
        remaining = total_beats - beat
        dur = min(float(beats_per_bar), remaining)

        # Velocity: first bar strong, subsequent bars softer with slight variation
        if bar_index == 0:
            vel = 1.0
        else:
            vel = rng.uniform(0.65, 0.80)

        events.append(RhythmEvent(beat, dur, vel, is_rest=False))
        beat += beats_per_bar
        bar_index += 1

    return events


def pattern_chord_medium(total_beats: float, beats_per_bar: int = 4,
                         seed: Optional[int] = None, **kwargs) -> list[RhythmEvent]:
    """
    Medium chord articulation: hits on beats 1 and 3 (half-note feel).

    Beat 1: strong attack, held for 2 beats.
    Beat 3: softer re-articulation, held for 2 beats.
    Occasional ghost on beat 2 or 4 (~15% chance) adds subtle life.
    """
    if seed is None:
        raise ValueError(f"Deterministic generation requires an explicit seed in {__name__}")
    rng = random.Random(seed)

    events = []
    beat = 0.0
    mid = beats_per_bar // 2  # beat 3 in 4/4, beat 2 in 3/4

    while beat < total_beats - 0.001:
        remaining = total_beats - beat
        bar_beats = min(float(beats_per_bar), remaining)

        # Beat 1: strong
        dur_1 = min(float(mid), remaining)
        events.append(RhythmEvent(beat, dur_1, 1.0, is_rest=False))

        # Beat 3 (midpoint): softer re-articulation
        if beat + mid < total_beats - 0.001:
            dur_3 = min(float(beats_per_bar - mid), total_beats - (beat + mid))
            vel_3 = rng.uniform(0.75, 0.88)
            events.append(RhythmEvent(beat + mid, dur_3, vel_3, is_rest=False))

        # Occasional ghost on an offbeat (~15%)
        if rng.random() < 0.15 and bar_beats >= beats_per_bar:
            ghost_beat = beat + rng.choice([1.0, 3.0])
            if ghost_beat < total_beats - 0.5:
                events.append(RhythmEvent(ghost_beat, 0.5, 0.45, is_rest=False))

        beat += beats_per_bar

    events.sort(key=lambda e: e.start_beat)
    return events


def pattern_chord_full(total_beats: float, beats_per_bar: int = 4,
                       seed: Optional[int] = None, **kwargs) -> list[RhythmEvent]:
    """
    Full chord articulation: quarter notes with musical accents.

    Beat 1: strong (1.0). Beat 3: accented (0.90).
    Beats 2, 4: softer (0.65-0.75).
    ~20% chance beat 4 becomes a rest (breathing room before next bar).
    Occasional eighth-note ghost pickup on the "and" of 4 (~12%).
    """
    if seed is None:
        raise ValueError(f"Deterministic generation requires an explicit seed in {__name__}")
    rng = random.Random(seed)

    events = []
    beat = 0.0

    while beat < total_beats - 0.001:
        for beat_in_bar in range(beats_per_bar):
            abs_beat = beat + beat_in_bar
            if abs_beat >= total_beats - 0.001:
                break

            remaining = total_beats - abs_beat

            # Beat 4 sometimes rests for breathing
            if beat_in_bar == beats_per_bar - 1 and rng.random() < 0.20:
                events.append(RhythmEvent(abs_beat, min(1.0, remaining), 0.0, is_rest=True))
                continue

            # Accent pattern
            if beat_in_bar == 0:
                vel = 1.0
            elif beat_in_bar == beats_per_bar // 2:
                vel = rng.uniform(0.85, 0.95)
            else:
                vel = rng.uniform(0.60, 0.75)

            dur = min(1.0, remaining)
            events.append(RhythmEvent(abs_beat, dur, vel, is_rest=False))

        # Occasional eighth-note ghost pickup before next bar
        pickup_beat = beat + beats_per_bar - 0.5
        if rng.random() < 0.12 and pickup_beat < total_beats - 0.2:
            events.append(RhythmEvent(pickup_beat, 0.5, 0.40, is_rest=False))

        beat += beats_per_bar

    events.sort(key=lambda e: e.start_beat)
    return events

def pattern_eighth(total_beats: float, **kwargs) -> list[RhythmEvent]:
    """Eighth note grid."""
    return grid(total_beats, subdivision=0.5, rest_probability=0.25,
                accent_beats=[0.0, 1.0, 2.0, 3.0], **kwargs)

def pattern_eighth_sparse(total_beats: float, **kwargs) -> list[RhythmEvent]:
    """Eighth notes with heavy rests — pointillistic, ambient."""
    return grid(total_beats, subdivision=0.5, rest_probability=0.55,
                accent_beats=[0.0, 2.0], **kwargs)

def pattern_dotted(total_beats: float, seed: Optional[int] = None, **kwargs) -> list[RhythmEvent]:
    """Dotted quarter + eighth feel."""
    if seed is None:
        raise ValueError(f"Deterministic generation requires an explicit seed in {__name__}")
    rng = random.Random(seed)
    events = []
    beat = 0.0
    while beat < total_beats - 0.001:
        for dur in [1.5, 0.5]:
            if beat >= total_beats - 0.001:
                break
            actual_dur = min(dur, total_beats - beat)
            vel = 1.0 if dur == 1.5 else 0.75
            is_rest = rng.random() < 0.15
            events.append(RhythmEvent(beat, actual_dur, vel, is_rest))
            beat += actual_dur
    return events

def pattern_free(total_beats: float, seed: Optional[int] = None, **kwargs) -> list[RhythmEvent]:
    """Freely varied note lengths. Ambient, non-metronomic feel."""
    if seed is None:
        raise ValueError(f"Deterministic generation requires an explicit seed in {__name__}")
    rng = random.Random(seed)
    durations = [0.5, 1.0, 1.5, 2.0, 3.0]
    weights   = [0.10, 0.30, 0.25, 0.25, 0.10]
    events = []
    beat = 0.0
    while beat < total_beats - 0.001:
        dur = rng.choices(durations, weights=weights, k=1)[0]
        dur = min(dur, total_beats - beat)
        is_rest = rng.random() < 0.20
        vel = rng.uniform(0.65, 1.0)
        events.append(RhythmEvent(beat, dur, vel, is_rest))
        beat += dur
    return events


def pattern_free_low(total_beats: float, seed: Optional[int] = None, **kwargs) -> list[RhythmEvent]:
    """Freely varied note lengths, busier than sparse but still non-metronomic.
    Sits between pattern_free (sparse) and pattern_eighth_sparse (medium):
    shorter average durations and lower rest probability than sparse, while
    keeping the free/ambient character rather than locking to the eighth grid."""
    if seed is None:
        raise ValueError(f"Deterministic generation requires an explicit seed in {__name__}")
    rng = random.Random(seed)
    durations = [0.5, 1.0, 1.5, 2.0]
    weights   = [0.30, 0.40, 0.20, 0.10]
    events = []
    beat = 0.0
    while beat < total_beats - 0.001:
        dur = rng.choices(durations, weights=weights, k=1)[0]
        dur = min(dur, total_beats - beat)
        is_rest = rng.random() < 0.12
        vel = rng.uniform(0.65, 1.0)
        events.append(RhythmEvent(beat, dur, vel, is_rest))
        beat += dur
    return events


def pattern_bar(total_beats: float, **kwargs) -> list[RhythmEvent]:
    """One note per bar. Sits between pattern_whole (one sustained note for
    the whole chord span) and pattern_half (one note every 2 beats).
    Used for bass low density."""
    bpb = float(kwargs.get("beats_per_bar", 4))
    return grid(total_beats, subdivision=bpb, rest_probability=0.05,
                accent_beats=[0.0], **kwargs)


def pattern_chord_low(total_beats: float, beats_per_bar: int = 4,
                       seed: Optional[int] = None, **kwargs) -> list[RhythmEvent]:
    """Low density chord articulation: bar-boundary re-strikes like sparse,
    with a softer beat-3 re-touch on roughly 40% of bars (vs. medium's
    deterministic every-bar beat-3 hit)."""
    if seed is None:
        raise ValueError(f"Deterministic generation requires an explicit seed in {__name__}")
    rng = random.Random(seed)
    events = []
    beat = 0.0
    mid = beats_per_bar // 2

    while beat < total_beats - 0.001:
        remaining = total_beats - beat
        dur_1 = min(float(beats_per_bar), remaining)
        vel_1 = 1.0 if beat == 0 else rng.uniform(0.70, 0.85)
        events.append(RhythmEvent(beat, dur_1, vel_1, is_rest=False))

        if rng.random() < 0.4 and beat + mid < total_beats - 0.001:
            dur_3 = min(float(beats_per_bar - mid), total_beats - (beat + mid))
            events.append(RhythmEvent(beat + mid, dur_3, rng.uniform(0.50, 0.65), is_rest=False))

        beat += beats_per_bar

    events.sort(key=lambda e: e.start_beat)
    return events


# ---------------------------------------------------------------------------
# Note-length range sampler (melody / counterpoint only)
# ---------------------------------------------------------------------------
# Decouples note *length* from density. When a section sets note_length_range,
# duration is sampled freely within [min, max] instead of being pinned to the
# density grid — while density keeps its separate job of governing how busy the
# line is, via the rest-probability map below. The two are now orthogonal knobs.
#
# Only ever reached for voice_type == "melody" (melody + free-species
# counterpoint). Bass and chord never sample here — see get_pattern's gate.

# density still means "how busy": more density → fewer rests → busier line.
# Values chosen so the range sampler spans the same busy↔sparse feel the old
# melody grid had, without touching duration (which the range now owns).
_RANGE_REST_PROB = {
    "sparse": 0.20,   # matches pattern_free's breathing
    "low":    0.12,   # matches pattern_free_low
    "medium": 0.08,   # busier — mostly continuous, occasional gap
    "full":   0.04,   # near-continuous
}


def pattern_range(
    total_beats: float,
    min_len: float,
    max_len: float,
    rest_probability: float = 0.08,
    quantum: float = 0.25,
    seed: Optional[int] = None,
    **kwargs,
) -> list[RhythmEvent]:
    """
    Tile the span with notes whose lengths are sampled from [min_len, max_len],
    snapped to `quantum` so durations stay grid-legible in the DAW rather than
    landing on arbitrary floats. quantum is the freedom dial: 0.5 → eighth-note
    legible, 0.25 → sixteenth, smaller → more fluid.

    Duration variety comes from here; how many notes / how much rest comes from
    rest_probability (fed by density upstream). Deterministic given seed.
    """
    if seed is None:
        raise ValueError(f"Deterministic generation requires an explicit seed in {__name__}")
    if quantum <= 0:
        raise ValueError(f"quantum must be > 0, got {quantum}")

    # Build the quantized candidate set, snapping the bounds inward/outward to
    # the grid. Guarantee at least one candidate even if min==max or the range
    # is narrower than one quantum.
    lo = max(quantum, round(min_len / quantum) * quantum)
    hi = max(lo, round(max_len / quantum) * quantum)
    steps = int(round((hi - lo) / quantum))
    candidates = [round(lo + i * quantum, 6) for i in range(steps + 1)]

    rng = random.Random(seed)
    events: list[RhythmEvent] = []
    beat = 0.0
    while beat < total_beats - 0.001:
        dur = rng.choice(candidates)
        dur = min(dur, total_beats - beat)
        if dur < 0.001:
            break
        is_rest = rng.random() < rest_probability
        vel = rng.uniform(0.65, 1.0)
        events.append(RhythmEvent(beat, dur, vel, is_rest))
        beat += dur
    return events


DENSITY_PATTERNS = {
    # Chord voicing patterns — articulate like a player, not a grid
    ("sparse", "chord"):  pattern_chord_sparse,
    ("low",    "chord"):  pattern_chord_low,
    ("medium", "chord"):  pattern_chord_medium,
    ("full",   "chord"):  pattern_chord_full,
    # Melody patterns — more active, more rests for breathing
    ("sparse", "melody"): pattern_free,
    ("low",    "melody"): pattern_free_low,
    ("medium", "melody"): pattern_eighth_sparse,
    ("full",   "melody"): pattern_eighth,
    # Bass patterns — kept simple, bass.py handles the real work
    ("sparse", "bass"):   pattern_whole,
    ("low",    "bass"):   pattern_bar,
    ("medium", "bass"):   pattern_half,
    ("full",   "bass"):   pattern_quarter,
}


# ---------------------------------------------------------------------------
# Public API — get_pattern (groove-aware)
# ---------------------------------------------------------------------------

def get_pattern(
    total_beats: float,
    density: str = "medium",
    voice_type: str = "chord",
    groove: Optional[str] = None,
    beats_per_bar: int = 4,
    seed: Optional[int] = None,
    note_length_range: Optional[tuple[float, float]] = None,
    note_length_quantum: float = 0.25,
) -> list[RhythmEvent]:
    """
    Get a rhythm pattern for a given density and voice type.

    Precedence for melody/counterpoint duration:
        groove  >  note_length_range  >  density grid
    A groove fully specifies onsets and durations, so it wins outright; when a
    groove is set, note_length_range is ignored (the lint surfaces this).

    Args:
        total_beats:    Total beats to fill
        density:        "sparse" | "medium" | "full"
        voice_type:     "chord" | "melody" | "bass"
        groove:         Optional groove name. Overrides grid patterns when set.
        beats_per_bar:  Beats per bar (used by groove templates)
        seed:           Optional random seed
        note_length_range:  Optional (min, max) beats. Melody/counterpoint only:
            when set (and no groove), duration is sampled in-range instead of
            from the density grid; density then only governs rest probability.
            Ignored for chord/bass voice types — those stay grid-disciplined.
        note_length_quantum:  Grid-snap for range sampling (default 0.25).

    Returns:
        List of RhythmEvent
    """
    if groove is not None:
        rest_prob = {"chord": 0.0, "melody": 0.12, "bass": 0.0}.get(voice_type, 0.05)
        return groove_pattern(
            total_beats, groove=groove, density=density,
            beats_per_bar=beats_per_bar,
            rest_probability=rest_prob, seed=seed,
        )

    # Free note-length range — melody/counterpoint only. Harmony and bass are
    # deliberately excluded so they stay grid-disciplined (design decision:
    # restrictions are right for accompaniment, freedom for the lead voices).
    if note_length_range is not None and voice_type == "melody":
        min_len, max_len = note_length_range
        rest_prob = _RANGE_REST_PROB.get(density, 0.08)
        return pattern_range(
            total_beats,
            min_len=min_len, max_len=max_len,
            rest_probability=rest_prob,
            quantum=note_length_quantum,
            seed=seed,
        )

    key = (density, voice_type)
    if key not in DENSITY_PATTERNS:
        raise ValueError(f"No pattern for density='{density}', voice_type='{voice_type}'.")

    fn = DENSITY_PATTERNS[key]
    return fn(total_beats, beats_per_bar=beats_per_bar, seed=seed)


# ---------------------------------------------------------------------------
# Swing
# ---------------------------------------------------------------------------

def remap_swing_ratio(swing: float) -> float:
    """
    Convert the public-facing swing amount into the internal swing_ratio
    scale consumed by apply_swing() and _apply_swing_to_drums().

    Public field (section.swing / harmony_rhythm.swing / drums.swing,
    schema range 0.0-1.0):
        0.0 = no swing (off)
        1.0 = heaviest swing

    Internal swing_ratio scale (what apply_swing/_apply_swing_to_drums
    actually compute against):
        0.5 = straight (no-op)
        0.67 = standard triplet swing
        1.0 = heavy swing

    These are different scales with different zero-points. Feeding a raw
    public swing value straight into swing_ratio (e.g. treating 0.2 as
    "a little swing") computes an offset of 0.2 - 0.5 = -0.3 beats —
    pushing offbeats EARLY (rushed) instead of late (swung). This was a
    real bug in earlier piece files that followed the old (now-removed)
    manual's incorrect 0.0-0.75 guidance.

    This function is the single conversion point. Every caller that takes
    a public swing value and forwards it to apply_swing() or
    _apply_swing_to_drums() must route it through here first.

    swing <= 0 maps to 0.5 (straight/no-op) as a safety net, though
    callers should already be guarding with `if swing > 0` before calling
    at all.
    """
    if swing <= 0:
        return 0.5
    return 0.5 + (min(swing, 1.0) * 0.5)


def apply_swing(events: list[RhythmEvent], swing_ratio: float = 0.67) -> list[RhythmEvent]:
    """
    Apply swing by delaying offbeat eighth notes.
    swing_ratio: 0.5 = straight, 0.67 = triplet swing, 0.75 = heavy swing.
    This is the INTERNAL scale — callers holding a public 0.0-1.0 swing
    value must convert with remap_swing_ratio() first, not pass it here
    directly.
    """
    if abs(swing_ratio - 0.5) < 0.001:
        return list(events)

    swung = []
    for ev in events:
        beat = ev.start_beat
        # Detect offbeat eighth notes: position is at the half-beat subdivision.
        # Use modulo on the eighth-note grid (0.5 beats) rather than raw % 1.0
        # so future time signatures don't silently break swing detection.
        frac = beat % 1.0
        if abs(frac - 0.5) < 0.01:
            offset = swing_ratio - 0.5
            new_beat = beat + offset
            new_dur = max(0.1, ev.duration_beats - offset)
            swung.append(RhythmEvent(new_beat, new_dur, ev.velocity_scale, ev.is_rest))
        else:
            swung.append(ev)
    return swung


# ---------------------------------------------------------------------------
# Velocity shaping over time (arc)
# ---------------------------------------------------------------------------

# Velocity clamp range applied after the arc multiplier (MIDI velocity units).
# Shared by every voice that shapes velocity by arc — melody's write-time
# envelope in generator.py and harmony's chord-event builder both clamp here,
# so one arc value means one dynamic range across the whole ensemble.
VELOCITY_CLAMP_MIN = 40
VELOCITY_CLAMP_MAX = 120


def arc_multiplier(arc: str, t: float) -> float:
    """
    The single source of truth for what a declared `arc` means as a dynamic
    curve. Returns a velocity multiplier (0.6–1.25) for a normalised position
    `t` within a section (0.0 at the section's start, 1.0 at its end).

    Every voice shares these curves; each voice computes its own `t` from
    whatever time unit it naturally advances in (melody: bar index within the
    section; harmony: chord onset offset within the section). That split is
    deliberate — the *curve* is a shared musical decision, the *time base* is
    a per-voice implementation detail.

    Curves:
      swell:    0.75 → 1.10, quadratic rise
      build:    0.70 → 1.20, quadratic rise steeper than swell
      fade_out / fade: 1.00 → 0.65, linear fall
      fade_in:  0.65 → 1.00, linear rise
      breath:   arch — 0.85 at the edges, peaking 1.15 at midpoint
      plateau:  flat 1.0 — intentionally a strict no-op, not an unimplemented
                branch; a section declaring `plateau` wants no dynamic shaping.
      decay:    0.95 → 0.70, gradual linear fall
      anything else: 1.0 (neutral — guarantees no change for unknown arcs)
    """
    t = max(0.0, min(1.0, t))

    if arc == "swell":
        m = 0.75 + 0.35 * (t ** 2)
    elif arc == "build":
        m = 0.70 + 0.50 * (t ** 2)
    elif arc in ("fade_out", "fade"):
        m = 1.00 - 0.35 * t
    elif arc == "fade_in":
        m = 0.65 + 0.35 * t
    elif arc == "breath":
        m = 0.85 + 0.30 * math.sin(math.pi * t)
    elif arc == "plateau":
        m = 1.0
    elif arc == "decay":
        m = 0.95 - 0.25 * t
    else:
        m = 1.0

    return max(0.6, min(1.25, m))


def apply_velocity_arc(
    events: list[RhythmEvent],
    arc: str = "flat",
    base_velocity: int = 70,
    arc_t: float = 0.0,
) -> list[tuple[RhythmEvent, int]]:
    """
    Apply the section's velocity arc to one chord window's events.
    Returns (event, velocity) pairs.

    `arc_t` is this chord window's normalised position within its *section*
    (0.0 at the section's first chord, 1.0 at its last), supplied by the
    caller. It is deliberately NOT derived from the event index: these events
    belong to a single chord window, so an index-derived t would restart the
    curve at every chord — which is exactly the bug this signature replaces.
    All events in one window share the window's multiplier; the curve advances
    chord to chord, giving harmony a genuinely section-wide shape.
    """
    if not events:
        return []

    arc_scale = arc_multiplier(arc, arc_t)

    result = []
    for ev in events:
        vel = int(base_velocity * ev.velocity_scale * arc_scale)
        vel = max(VELOCITY_CLAMP_MIN, min(VELOCITY_CLAMP_MAX, vel))
        result.append((ev, vel))

    return result


# ---------------------------------------------------------------------------
# Quick test / demo
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    print("=== Intervals Engine — rhythm.py demo ===\n")

    total = 8.0

    print("── Groove patterns ──\n")
    for groove_name in GROOVES:
        for density in ("sparse", "medium", "full"):
            events = get_pattern(total, density=density, voice_type="melody",
                                 groove=groove_name, seed=42)
            non_rest = [e for e in events if not e.is_rest]
            print(f"groove={groove_name:12s} density={density:6s} → "
                  f"{len(events):2d} events ({len(non_rest)} notes)")
        print()

    print("── Backward compat: no groove ──\n")
    for density in ("sparse", "medium", "full"):
        events = get_pattern(total, density=density, voice_type="melody", seed=42)
        non_rest = [e for e in events if not e.is_rest]
        print(f"density={density:6s} → {len(events):2d} events ({len(non_rest)} notes)")
