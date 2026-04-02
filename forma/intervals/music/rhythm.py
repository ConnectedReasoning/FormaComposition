"""
rhythm.py — Intervals Engine
Rhythmic pattern generation with groove templates, density, swing, and humanization.

Four independent axes:
  groove    — where notes land within a bar (the pattern/feel)
  density   — how many slots are active (sparse/medium/full)
  swing     — timing push on offbeats (0.0 = straight, 0.67 = triplet)
  humanize  — timing jitter + velocity variation (0.0–1.0)

Rhythm is expressed in beats (float), tempo-agnostic.
The generator converts beats → MIDI ticks using tempo + PPQ.

Groove is optional. When no groove is specified, behavior falls through
to the original density-based grid patterns for full backward compatibility.
"""

import random
import math
from dataclasses import dataclass
from typing import Optional

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
    if seed is not None:
        random.seed(seed)

    if groove not in GROOVES:
        raise ValueError(f"Unknown groove: '{groove}'. Choose from: {VALID_GROOVES}")

    template = GROOVES[groove]
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
            is_rest = random.random() < rest_probability
            events.append(RhythmEvent(abs_beat, dur, slot.velocity_scale, is_rest))
        bar_start += beats_per_bar

    events.sort(key=lambda e: e.start_beat)
    return events


# ---------------------------------------------------------------------------
# Humanization
# ---------------------------------------------------------------------------

def apply_humanize(
    events: list[RhythmEvent],
    amount: float = 0.3,
    seed: Optional[int] = None,
) -> list[RhythmEvent]:
    """
    Add human feel: timing jitter, velocity variation, duration micro-variation.

    amount controls intensity (0.0 = robotic, 1.0 = very loose):
      - Timing jitter: +/-(amount * 0.05) beats
      - Velocity variation: +/-(amount * 0.15)
      - Duration: +/-10% at full humanize
      - Downbeats get less jitter (more anchored)
    """
    if amount <= 0.0:
        return list(events)

    if seed is not None:
        random.seed(seed)

    result = []
    for ev in events:
        beat_in_bar = ev.start_beat % 4.0
        is_downbeat = beat_in_bar < 0.01
        jitter_range = amount * 0.05 * (0.3 if is_downbeat else 1.0)
        time_jitter = random.uniform(-jitter_range, jitter_range)
        new_beat = max(0.0, ev.start_beat + time_jitter)

        vel_range = amount * 0.15
        vel_jitter = random.uniform(-vel_range, vel_range)
        new_vel = max(0.2, min(1.0, ev.velocity_scale + vel_jitter))

        dur_factor = 1.0 + random.uniform(-0.1, 0.1) * amount
        new_dur = max(0.1, ev.duration_beats * dur_factor)

        result.append(RhythmEvent(new_beat, new_dur, new_vel, ev.is_rest))

    return result


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
    if seed is not None:
        random.seed(seed)
    if accent_beats is None:
        accent_beats = []

    events = []
    beat = 0.0
    while beat < total_beats - 0.001:
        dur = min(subdivision, total_beats - beat)
        is_rest = random.random() < rest_probability
        beat_in_bar = beat % 4.0
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
    if seed is not None:
        random.seed(seed)

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
            vel = random.uniform(0.65, 0.80)

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
    if seed is not None:
        random.seed(seed)

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
            vel_3 = random.uniform(0.75, 0.88)
            events.append(RhythmEvent(beat + mid, dur_3, vel_3, is_rest=False))

        # Occasional ghost on an offbeat (~15%)
        if random.random() < 0.15 and bar_beats >= beats_per_bar:
            ghost_beat = beat + random.choice([1.0, 3.0])
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
    if seed is not None:
        random.seed(seed)

    events = []
    beat = 0.0

    while beat < total_beats - 0.001:
        for beat_in_bar in range(beats_per_bar):
            abs_beat = beat + beat_in_bar
            if abs_beat >= total_beats - 0.001:
                break

            remaining = total_beats - abs_beat

            # Beat 4 sometimes rests for breathing
            if beat_in_bar == beats_per_bar - 1 and random.random() < 0.20:
                events.append(RhythmEvent(abs_beat, min(1.0, remaining), 0.0, is_rest=True))
                continue

            # Accent pattern
            if beat_in_bar == 0:
                vel = 1.0
            elif beat_in_bar == beats_per_bar // 2:
                vel = random.uniform(0.85, 0.95)
            else:
                vel = random.uniform(0.60, 0.75)

            dur = min(1.0, remaining)
            events.append(RhythmEvent(abs_beat, dur, vel, is_rest=False))

        # Occasional eighth-note ghost pickup before next bar
        pickup_beat = beat + beats_per_bar - 0.5
        if random.random() < 0.12 and pickup_beat < total_beats - 0.2:
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

def pattern_dotted(total_beats: float, **kwargs) -> list[RhythmEvent]:
    """Dotted quarter + eighth feel."""
    events = []
    beat = 0.0
    while beat < total_beats - 0.001:
        for dur in [1.5, 0.5]:
            if beat >= total_beats - 0.001:
                break
            actual_dur = min(dur, total_beats - beat)
            vel = 1.0 if dur == 1.5 else 0.75
            is_rest = random.random() < 0.15
            events.append(RhythmEvent(beat, actual_dur, vel, is_rest))
            beat += actual_dur
    return events

def pattern_free(total_beats: float, seed: Optional[int] = None, **kwargs) -> list[RhythmEvent]:
    """Freely varied note lengths. Ambient, non-metronomic feel."""
    if seed is not None:
        random.seed(seed)
    durations = [0.5, 1.0, 1.5, 2.0, 3.0]
    weights   = [0.10, 0.30, 0.25, 0.25, 0.10]
    events = []
    beat = 0.0
    while beat < total_beats - 0.001:
        dur = random.choices(durations, weights=weights, k=1)[0]
        dur = min(dur, total_beats - beat)
        is_rest = random.random() < 0.20
        vel = random.uniform(0.65, 1.0)
        events.append(RhythmEvent(beat, dur, vel, is_rest))
        beat += dur
    return events


DENSITY_PATTERNS = {
    # Chord voicing patterns — articulate like a player, not a grid
    ("sparse", "chord"):  pattern_chord_sparse,
    ("medium", "chord"):  pattern_chord_medium,
    ("full",   "chord"):  pattern_chord_full,
    # Melody patterns — more active, more rests for breathing
    ("sparse", "melody"): pattern_free,
    ("medium", "melody"): pattern_eighth_sparse,
    ("full",   "melody"): pattern_eighth,
    # Bass patterns — kept simple, bass.py handles the real work
    ("sparse", "bass"):   pattern_whole,
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
) -> list[RhythmEvent]:
    """
    Get a rhythm pattern for a given density and voice type.

    If groove is specified, uses the groove template system.
    Otherwise falls through to the original density-based grid patterns.

    Args:
        total_beats:    Total beats to fill
        density:        "sparse" | "medium" | "full"
        voice_type:     "chord" | "melody" | "bass"
        groove:         Optional groove name. Overrides grid patterns when set.
        beats_per_bar:  Beats per bar (used by groove templates)
        seed:           Optional random seed

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

    key = (density, voice_type)
    if key not in DENSITY_PATTERNS:
        raise ValueError(f"No pattern for density='{density}', voice_type='{voice_type}'.")

    fn = DENSITY_PATTERNS[key]
    return fn(total_beats, beats_per_bar=beats_per_bar, seed=seed)


# ---------------------------------------------------------------------------
# Swing
# ---------------------------------------------------------------------------

def apply_swing(events: list[RhythmEvent], swing_ratio: float = 0.67) -> list[RhythmEvent]:
    """
    Apply swing by delaying offbeat eighth notes.
    swing_ratio: 0.5 = straight, 0.67 = triplet swing, 0.75 = heavy swing.
    """
    if abs(swing_ratio - 0.5) < 0.001:
        return list(events)

    swung = []
    for ev in events:
        beat = ev.start_beat
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

def apply_velocity_arc(
    events: list[RhythmEvent],
    arc: str = "flat",
    base_velocity: int = 70,
) -> list[tuple[RhythmEvent, int]]:
    """Apply a velocity arc across events. Returns (event, velocity) pairs."""
    n = len(events)
    if n == 0:
        return []

    result = []
    for i, ev in enumerate(events):
        t = i / max(n - 1, 1)
        if arc == "flat":
            arc_scale = 1.0
        elif arc == "swell":
            arc_scale = 1.0 - abs(t - 0.5) * 0.6
        elif arc == "fade_in":
            arc_scale = 0.5 + t * 0.5
        elif arc == "fade_out":
            arc_scale = 1.0 - t * 0.5
        elif arc == "breath":
            arc_scale = 0.75 + 0.25 * math.sin(t * 2 * math.pi)
        else:
            arc_scale = 1.0

        vel = int(base_velocity * ev.velocity_scale * arc_scale)
        vel = max(20, min(127, vel))
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
