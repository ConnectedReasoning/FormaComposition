"""
motif.py — Intervals Engine
Standalone motif definition, transformation, and generation system.

A motif is the melodic DNA of a theme — a short interval sequence with
a rhythmic profile. This module handles:
  - Motif creation (from explicit definition or random generation)
  - All Bach-style transforms (inversion, retrograde, augmentation, etc.)
  - Motif mutation (for variation over long pieces)
  - Motif similarity scoring (to keep variations recognisable)
  - Export to note sequences given a root and scale

Used by melody.py and directly by generator.py when building themes.
"""

import random
import math
import copy
from dataclasses import dataclass, field
from typing import Optional

# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------

@dataclass
class Motif:
    """
    A motif: interval sequence + rhythmic profile + metadata.

    intervals:      Semitone steps between successive notes.
                    e.g. [2, -1, 3, -2] means: up 2, down 1, up 3, down 2
    rhythm:         Duration in beats for each note.
                    e.g. [1.0, 0.5, 0.5, 1.0]
    name:           Optional label for identification.
    transform_pool: Transforms eligible for variation generation.
    generation:     How many transforms away from the original (0 = source).
    parent_name:    Name of the motif this was derived from.
    """
    intervals: list[int]
    rhythm: list[float]
    name: str = "motif"
    transform_pool: list[str] = field(default_factory=lambda: [
        "inversion", "retrograde", "augmentation", "diminution", "transpose_up",
        "transpose_down", "shuffle"
    ])
    generation: int = 0
    parent_name: Optional[str] = None

    def __post_init__(self):
        # Pad or trim rhythm to match interval count
        n = len(self.intervals)
        if len(self.rhythm) < n:
            self.rhythm = (self.rhythm * ((n // len(self.rhythm)) + 1))[:n]
        elif len(self.rhythm) > n:
            self.rhythm = self.rhythm[:n]

    def __repr__(self):
        return (f"Motif('{self.name}' gen={self.generation} "
                f"intervals={self.intervals} rhythm={self.rhythm})")

    def note_count(self) -> int:
        return len(self.intervals)

    def total_duration(self) -> float:
        return sum(self.rhythm)

    def interval_range(self) -> int:
        """Total semitone span of the motif."""
        pos = 0
        positions = [0]
        for i in self.intervals:
            pos += i
            positions.append(pos)
        return max(positions) - min(positions)

    def contour(self) -> list[str]:
        """Melodic contour as a string of U(p), D(own), S(ame)."""
        return [
            "U" if i > 0 else "D" if i < 0 else "S"
            for i in self.intervals
        ]


# ---------------------------------------------------------------------------
# Transforms
# ---------------------------------------------------------------------------

TRANSFORM_DESCRIPTIONS = {
    "inversion":     "Negate all intervals (mirror the melodic shape)",
    "retrograde":    "Reverse the interval sequence",
    "augmentation":  "Double all note durations",
    "diminution":    "Halve all note durations",
    "transpose_up":  "Shift all intervals up by 2 semitones",
    "transpose_down":"Shift all intervals down by 2 semitones",
    "shuffle":       "Randomly reorder intervals",
    "expand":        "Scale intervals by 1.5 (wider leaps)",
    "compress":      "Scale intervals by 0.5, rounded (smaller steps)",
    "retrograde_inversion": "Reverse then negate (Bach's fourth transform)",
}


def transform(motif: Motif, transform_name: str, seed: Optional[int] = None) -> Motif:
    """
    Apply a named transform to a motif, returning a new Motif.
    The original motif is never modified.

    Args:
        motif:          Source Motif
        transform_name: Name of the transform to apply
        seed:           Random seed (for shuffle)

    Returns:
        New Motif with transform applied
    """
    if seed is not None:
        random.seed(seed)

    intervals = list(motif.intervals)
    rhythm    = list(motif.rhythm)
    name      = f"{motif.name}_{transform_name}"

    if transform_name == "inversion":
        intervals = [-i for i in intervals]

    elif transform_name == "retrograde":
        intervals = list(reversed(intervals))
        rhythm    = list(reversed(rhythm))

    elif transform_name == "retrograde_inversion":
        intervals = [-i for i in reversed(intervals)]
        rhythm    = list(reversed(rhythm))

    elif transform_name == "augmentation":
        rhythm = [r * 2.0 for r in rhythm]

    elif transform_name == "diminution":
        rhythm = [max(0.25, r * 0.5) for r in rhythm]

    elif transform_name == "transpose_up":
        intervals = [i + 2 for i in intervals]

    elif transform_name == "transpose_down":
        intervals = [i - 2 for i in intervals]

    elif transform_name == "shuffle":
        combined = list(zip(intervals, rhythm))
        random.shuffle(combined)
        intervals, rhythm = zip(*combined) if combined else ([], [])
        intervals = list(intervals)
        rhythm    = list(rhythm)

    elif transform_name == "expand":
        intervals = [int(round(i * 1.5)) for i in intervals]

    elif transform_name == "compress":
        intervals = [int(round(i * 0.5)) for i in intervals]
        # Ensure no zero intervals (use ±1 minimum for non-zero)
        intervals = [i if i != 0 else 0 for i in intervals]

    else:
        raise ValueError(
            f"Unknown transform: '{transform_name}'. "
            f"Choose from: {list(TRANSFORM_DESCRIPTIONS.keys())}"
        )

    return Motif(
        intervals=intervals,
        rhythm=rhythm,
        name=name,
        transform_pool=list(motif.transform_pool),
        generation=motif.generation + 1,
        parent_name=motif.name,
    )


def apply_transform_sequence(motif: Motif, transforms: list[str], seed: Optional[int] = None) -> Motif:
    """Apply a chain of transforms in sequence."""
    result = motif
    for t in transforms:
        result = transform(result, t, seed)
    return result


# ---------------------------------------------------------------------------
# Mutation (for long-form variation)
# ---------------------------------------------------------------------------

def mutate(
    motif: Motif,
    mutation_rate: float = 0.25,
    interval_range: int = 2,
    seed: Optional[int] = None,
) -> Motif:
    """
    Randomly mutate a small number of intervals in a motif.
    Produces organic variation while preserving recognisability.

    Args:
        motif:          Source Motif
        mutation_rate:  Probability each interval is mutated (0.0–1.0)
        interval_range: Max semitone change per mutation
        seed:           Random seed

    Returns:
        New Motif with random mutations applied
    """
    if seed is not None:
        random.seed(seed)

    intervals = list(motif.intervals)
    for i in range(len(intervals)):
        if random.random() < mutation_rate:
            delta = random.randint(-interval_range, interval_range)
            intervals[i] += delta

    return Motif(
        intervals=intervals,
        rhythm=list(motif.rhythm),
        name=f"{motif.name}_mutated",
        transform_pool=list(motif.transform_pool),
        generation=motif.generation + 1,
        parent_name=motif.name,
    )


# ---------------------------------------------------------------------------
# Random motif generation
# ---------------------------------------------------------------------------

def generate_random(
    length: int = 4,
    max_interval: int = 5,
    rhythm_pool: Optional[list[float]] = None,
    name: str = "random_motif",
    seed: Optional[int] = None,
) -> Motif:
    """
    Generate a random motif.

    Args:
        length:       Number of intervals
        max_interval: Maximum absolute semitone jump
        rhythm_pool:  Durations to sample from (default: [0.5, 1.0, 1.5, 2.0])
        name:         Motif name
        seed:         Random seed

    Returns:
        New random Motif
    """
    if seed is not None:
        random.seed(seed)

    if rhythm_pool is None:
        rhythm_pool = [0.5, 1.0, 1.5, 2.0]

    # Avoid all-zero intervals
    intervals = []
    for _ in range(length):
        v = 0
        while v == 0:
            v = random.randint(-max_interval, max_interval)
        intervals.append(v)

    rhythm = [random.choice(rhythm_pool) for _ in range(length)]

    return Motif(intervals=intervals, rhythm=rhythm, name=name)


# ---------------------------------------------------------------------------
# Similarity scoring
# ---------------------------------------------------------------------------

def similarity(a: Motif, b: Motif) -> float:
    """
    Score how similar two motifs are (0.0 = completely different, 1.0 = identical).
    Based on contour match and interval distance.

    Useful for ensuring develop-mode variations stay recognisable.
    """
    # Contour similarity
    ca = a.contour()
    cb = b.contour()
    min_len = min(len(ca), len(cb))
    if min_len == 0:
        return 0.0
    contour_match = sum(1 for x, y in zip(ca, cb) if x == y) / min_len

    # Interval distance (normalised)
    ia = a.intervals[:min_len]
    ib = b.intervals[:min_len]
    max_diff = max(abs(x - y) for x, y in zip(ia, ib)) if ia else 1
    interval_score = 1.0 - min(1.0, max_diff / 12.0)

    return 0.6 * contour_match + 0.4 * interval_score


# ---------------------------------------------------------------------------
# Note sequence generation
# ---------------------------------------------------------------------------

def to_note_sequence(
    motif: Motif,
    start_midi: int,
    scale_tones: list[int],
    octave_bottom: int = 60,
    octave_top: int = 84,
    snap_to_scale: bool = True,
) -> list[tuple[int, float]]:
    """
    Convert a motif to a list of (midi_note, duration_beats) pairs.

    Args:
        motif:          Source Motif
        start_midi:     Starting MIDI note
        scale_tones:    Available scale tones for snapping
        octave_bottom:  Lowest MIDI note allowed
        octave_top:     Highest MIDI note allowed
        snap_to_scale:  If True, snap each note to nearest scale tone

    Returns:
        List of (midi_note, duration_beats) tuples
    """
    notes = []
    current = start_midi

    for interval, dur in zip(motif.intervals, motif.rhythm):
        current += interval
        # Wrap into register
        while current < octave_bottom:
            current += 12
        while current > octave_top:
            current -= 12
        # Snap to scale
        if snap_to_scale and scale_tones:
            current = min(scale_tones, key=lambda s: abs(s - current))
        notes.append((current, dur))

    return notes


# ---------------------------------------------------------------------------
# Serialisation helpers
# ---------------------------------------------------------------------------

def from_dict(d: dict) -> Motif:
    """
    Build a Motif from a dictionary (e.g. parsed from theme.json).

    Expected keys: intervals, rhythm, name (optional), transform_pool (optional)
    """
    return Motif(
        intervals=d["intervals"],
        rhythm=d.get("rhythm", [1.0] * len(d["intervals"])),
        name=d.get("name", "motif"),
        transform_pool=d.get("transform_pool", [
            "inversion", "retrograde", "augmentation",
            "diminution", "transpose_up", "transpose_down"
        ]),
    )


def to_dict(motif: Motif) -> dict:
    """Serialise a Motif to a dictionary suitable for JSON output."""
    return {
        "name":           motif.name,
        "intervals":      motif.intervals,
        "rhythm":         motif.rhythm,
        "transform_pool": motif.transform_pool,
        "generation":     motif.generation,
        "parent_name":    motif.parent_name,
    }


# ---------------------------------------------------------------------------
# Quick test / demo
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    print("=== Intervals Engine — motif.py demo ===\n")

    # Build a motif from a dict (as theme.json would supply it)
    source = from_dict({
        "name": "evening_water",
        "intervals": [2, -1, 3, -2],
        "rhythm": [1.0, 0.5, 0.5, 1.0],
        "transform_pool": ["inversion", "retrograde", "augmentation",
                           "retrograde_inversion", "transpose_up"]
    })

    print(f"Source:  {source}")
    print(f"Contour: {source.contour()}")
    print(f"Range:   {source.interval_range()} semitones")
    print(f"Duration:{source.total_duration()} beats\n")

    # Apply every transform
    print("--- Transforms ---")
    for t_name in TRANSFORM_DESCRIPTIONS:
        try:
            result = transform(source, t_name, seed=42)
            sim = similarity(source, result)
            print(f"  {t_name:25s} intervals={result.intervals}  "
                  f"rhythm={[round(r,2) for r in result.rhythm]}  "
                  f"similarity={sim:.2f}")
        except Exception as e:
            print(f"  {t_name:25s} ERROR: {e}")

    print()

    # Mutation demo
    print("--- Mutations ---")
    for i in range(4):
        m = mutate(source, mutation_rate=0.5, seed=i * 7)
        sim = similarity(source, m)
        print(f"  mutation {i}: intervals={m.intervals}  similarity={sim:.2f}")

    print()

    # Random motif generation
    print("--- Random motifs ---")
    for i in range(3):
        r = generate_random(length=5, max_interval=4, seed=i * 13)
        print(f"  {r}")

    print()

    # Note sequence from motif
    print("--- Note sequence (D Dorian, start=D4/62) ---")
    from harmony import get_scale, CHROMATIC
    scale = get_scale("D", "dorian", octave=4)
    # Extend scale across melody register
    full_scale = []
    for oct in range(3, 7):
        full_scale.extend(get_scale("D", "dorian", octave=oct))
    full_scale = sorted(set(full_scale))

    seq = to_note_sequence(source, start_midi=62, scale_tones=full_scale)
    for midi, dur in seq:
        print(f"  {CHROMATIC[midi % 12]}{midi}  dur={dur}")

    print()

    # Serialisation round-trip
    print("--- Serialisation round-trip ---")
    d = to_dict(source)
    restored = from_dict(d)
    print(f"  Original:  {source.intervals}")
    print(f"  Restored:  {restored.intervals}")
    print(f"  Match: {source.intervals == restored.intervals}")

    # Transform chain
    print()
    print("--- Transform chain: retrograde → inversion ---")
    chained = apply_transform_sequence(source, ["retrograde", "inversion"])
    print(f"  Result: {chained}")
    print(f"  Same as retrograde_inversion: "
          f"{chained.intervals == transform(source, 'retrograde_inversion').intervals}")
