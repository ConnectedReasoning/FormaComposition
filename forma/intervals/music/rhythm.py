"""
rhythm.py — Intervals Engine
Maps density levels and styles to rhythmic timing patterns.

Produces beat grids and note event timing for harmony and melody voices.
Rhythm is expressed in beats (float), tempo-agnostic.
The generator converts beats → MIDI ticks using tempo + PPQ.
"""

import random
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


# ---------------------------------------------------------------------------
# Core grid builders
# ---------------------------------------------------------------------------

def grid(
    total_beats: float,
    subdivision: float,
    rest_probability: float = 0.0,
    accent_beats: Optional[list[float]] = None,
    accent_boost: float = 0.15,
    seed: Optional[int] = None,
) -> list[RhythmEvent]:
    """
    Build a uniform grid of RhythmEvents.

    Args:
        total_beats:      Total duration to fill
        subdivision:      Note duration (e.g. 1.0=quarter, 0.5=eighth, 2.0=half)
        rest_probability: Chance any given slot becomes a rest (0.0–1.0)
        accent_beats:     Beat positions to accent (e.g. [0, 2] for beats 1 and 3)
        accent_boost:     Velocity boost for accented beats
        seed:             Random seed for reproducibility

    Returns:
        List of RhythmEvent
    """
    if seed is not None:
        random.seed(seed)

    if accent_beats is None:
        accent_beats = []

    events = []
    beat = 0.0
    while beat < total_beats - 0.001:
        dur = min(subdivision, total_beats - beat)
        is_rest = random.random() < rest_probability

        # Velocity scaling: accent if beat falls on accent position
        beat_in_bar = beat % 4.0  # assumes 4/4
        vel = 1.0
        if any(abs(beat_in_bar - a) < 0.001 for a in accent_beats):
            vel = min(1.0, vel + accent_boost)
        else:
            vel = max(0.5, vel - 0.05)

        events.append(RhythmEvent(beat, dur, vel, is_rest))
        beat += subdivision

    return events


# ---------------------------------------------------------------------------
# Named rhythm patterns
# ---------------------------------------------------------------------------

def pattern_whole(total_beats: float, **kwargs) -> list[RhythmEvent]:
    """One note per chord — whole notes. Very sparse, meditative."""
    return grid(total_beats, subdivision=total_beats, rest_probability=0.0,
                accent_beats=[0.0], **kwargs)


def pattern_half(total_beats: float, **kwargs) -> list[RhythmEvent]:
    """Half note grid. Slow, breathing."""
    return grid(total_beats, subdivision=2.0, rest_probability=0.1,
                accent_beats=[0.0, 2.0], **kwargs)


def pattern_quarter(total_beats: float, **kwargs) -> list[RhythmEvent]:
    """Quarter note grid. Steady, grounded."""
    return grid(total_beats, subdivision=1.0, rest_probability=0.15,
                accent_beats=[0.0, 2.0], **kwargs)


def pattern_quarter_sparse(total_beats: float, **kwargs) -> list[RhythmEvent]:
    """Quarter note grid with more rests — creates breathing space."""
    return grid(total_beats, subdivision=1.0, rest_probability=0.40,
                accent_beats=[0.0], **kwargs)


def pattern_eighth(total_beats: float, **kwargs) -> list[RhythmEvent]:
    """Eighth note grid. More melodic motion."""
    return grid(total_beats, subdivision=0.5, rest_probability=0.25,
                accent_beats=[0.0, 1.0, 2.0, 3.0], **kwargs)


def pattern_eighth_sparse(total_beats: float, **kwargs) -> list[RhythmEvent]:
    """Eighth notes with heavy rests — pointillistic, ambient."""
    return grid(total_beats, subdivision=0.5, rest_probability=0.55,
                accent_beats=[0.0, 2.0], **kwargs)


def pattern_dotted(total_beats: float, **kwargs) -> list[RhythmEvent]:
    """Dotted quarter + eighth feel. Gives a gentle lilt."""
    events = []
    beat = 0.0
    while beat < total_beats - 0.001:
        # Alternate dotted quarter (1.5) and eighth (0.5)
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
    """
    Freely varied note lengths. Ambient, non-metronomic feel.
    Durations drawn from [0.5, 1.0, 1.5, 2.0, 3.0] with weighted probability.
    """
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


# ---------------------------------------------------------------------------
# Density → pattern mapping
# ---------------------------------------------------------------------------

# Maps (density, style) → pattern function
# style: "chord" (harmony voicings), "melody" (single-note lines)
DENSITY_PATTERNS = {
    # Chord voicing patterns — tend to be slower, more sustained
    ("sparse", "chord"):  pattern_whole,
    ("medium", "chord"):  pattern_half,
    ("full",   "chord"):  pattern_quarter,

    # Melody patterns — more active, more rests for breathing
    ("sparse", "melody"): pattern_free,
    ("medium", "melody"): pattern_eighth_sparse,
    ("full",   "melody"): pattern_eighth,

    # Bass handled in bass.py but rhythm.py can provide timing grids
    ("sparse", "bass"):   pattern_whole,
    ("medium", "bass"):   pattern_half,
    ("full",   "bass"):   pattern_quarter,
}


def get_pattern(
    total_beats: float,
    density: str = "medium",
    voice_type: str = "chord",
    seed: Optional[int] = None,
) -> list[RhythmEvent]:
    """
    Get a rhythm pattern for a given density and voice type.

    Args:
        total_beats:  Total beats to fill (bars * beats_per_bar)
        density:      "sparse" | "medium" | "full"
        voice_type:   "chord" | "melody" | "bass"
        seed:         Optional random seed

    Returns:
        List of RhythmEvent
    """
    key = (density, voice_type)
    if key not in DENSITY_PATTERNS:
        raise ValueError(f"No pattern for density='{density}', voice_type='{voice_type}'.")

    fn = DENSITY_PATTERNS[key]
    if seed is not None:
        return fn(total_beats, seed=seed)
    return fn(total_beats)


# ---------------------------------------------------------------------------
# Swing
# ---------------------------------------------------------------------------

def apply_swing(events: list[RhythmEvent], swing_ratio: float = 0.67) -> list[RhythmEvent]:
    """
    Apply swing to an eighth-note grid by delaying the offbeat eighth notes.

    swing_ratio: 0.5 = straight, 0.67 = triplet swing, 0.75 = heavy swing.
    Only affects events on eighth-note offbeats (beat positions x.5).

    Args:
        events:       List of RhythmEvent
        swing_ratio:  How much to push offbeats (0.5–0.75)

    Returns:
        New list of RhythmEvent with swing applied
    """
    swung = []
    for ev in events:
        beat = ev.start_beat
        # Detect offbeat eighth notes (fractional part ~= 0.5)
        frac = beat % 1.0
        if abs(frac - 0.5) < 0.01:
            # Push offbeat forward
            offset = swing_ratio - 0.5
            new_beat = beat + offset
            # Shorten duration to compensate
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
    """
    Apply a velocity arc across a list of events, returning (event, velocity) pairs.

    arc options:
      flat       — constant velocity
      swell      — crescendo to midpoint, decrescendo back
      fade_in    — starts soft, builds
      fade_out   — starts loud, fades
      breath     — gentle swell, more organic

    Args:
        events:        List of RhythmEvent
        arc:           Arc shape name
        base_velocity: Base MIDI velocity (0–127)

    Returns:
        List of (RhythmEvent, int) tuples
    """
    n = len(events)
    if n == 0:
        return []

    result = []
    for i, ev in enumerate(events):
        t = i / max(n - 1, 1)  # normalised position 0.0–1.0

        if arc == "flat":
            arc_scale = 1.0
        elif arc == "swell":
            arc_scale = 1.0 - abs(t - 0.5) * 0.6
        elif arc == "fade_in":
            arc_scale = 0.5 + t * 0.5
        elif arc == "fade_out":
            arc_scale = 1.0 - t * 0.5
        elif arc == "breath":
            # Two gentle swells
            import math
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

    total = 8.0  # 2 bars of 4/4

    for density in ("sparse", "medium", "full"):
        for vtype in ("chord", "melody"):
            events = get_pattern(total, density=density, voice_type=vtype, seed=42)
            non_rest = [e for e in events if not e.is_rest]
            rests = [e for e in events if e.is_rest]
            print(f"density={density:6s} voice={vtype:6s} → {len(events):2d} events "
                  f"({len(non_rest)} notes, {len(rests)} rests)")
            for e in events[:4]:
                print(f"    {e}")
            if len(events) > 4:
                print(f"    ... ({len(events) - 4} more)")
            print()

    # Swing demo
    print("--- Swing applied to medium/melody ---")
    events = get_pattern(4.0, density="medium", voice_type="melody", seed=7)
    swung = apply_swing(events, swing_ratio=0.67)
    for orig, sw in zip(events[:6], swung[:6]):
        if abs(orig.start_beat - sw.start_beat) > 0.001:
            print(f"  {orig.start_beat:.2f} → {sw.start_beat:.2f}  (swung)")
        else:
            print(f"  {orig.start_beat:.2f} → {sw.start_beat:.2f}")
    print()

    # Velocity arc demo
    print("--- Velocity arc: swell ---")
    events = get_pattern(8.0, density="full", voice_type="chord", seed=1)
    arced = apply_velocity_arc(events, arc="swell", base_velocity=80)
    for ev, vel in arced[:8]:
        print(f"  beat={ev.start_beat:.1f}  vel={vel}")
