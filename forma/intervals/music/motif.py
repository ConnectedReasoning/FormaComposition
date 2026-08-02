"""
motif.py — Intervals Engine
Standalone motif definition, transformation, and generation system.

A motif is the melodic DNA of a theme — a short interval sequence with
a rhythmic profile. Interval units are migrating from semitones to
diatonic scale-degree steps (see Motif.intervals docstring below for the
target contract and current implementation status). This module handles:
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

    intervals:      CONTRACT (as of 2026-08, pending implementation — see
                    Phase B of the diatonic-motif migration): diatonic
                    scale-degree steps between successive notes, resolved
                    against the piece's mode. e.g. [2, -1, 3, -2] means: up
                    2 scale degrees, down 1, up 3, down 2 — NOT semitones.
                    A diatonic step always lands on a scale tone by
                    construction, so downstream snap-to-scale quantization
                    (melody.py's motif_to_notes) no longer erases small
                    steps the way semitone intervals did (see the E-mixolydian
                    trace that motivated this: four of nine ±1-semitone
                    steps collapsed back to their starting pitch because the
                    local scale gap was a whole tone).
                    STATUS: motif_to_notes (Phase B2) now walks diatonic
                    degree space natively, apply_transform's transpose
                    (Phase B3) uses the decided magnitude of 1 diatonic
                    step, melodic_scale (Phase B4) lets a motif walk a
                    scale decoupled from the piece's harmonic mode, and
                    interval_range()/semitone_span() (Phase B5) now state
                    plainly which of the two questions each one answers —
                    scale-degree span vs. actual semitone/register width —
                    instead of leaving that ambiguous. All now implement
                    this docstring's contract, not the old one. Still
                    untouched: mutate()'s and generate_random()'s default
                    interval_range/max_interval values (2 and 5) were tuned
                    for semitone-scale variation; whether those specific
                    defaults are still the right magnitudes for diatonic-
                    step variation is a separate, unscoped question -- not
                    addressed by B2/B3/B5, since none of those functions
                    are apply_transform/transform()/interval_range().
                    Chromatic alterations (borrowed chords, secondary-
                    dominant coloring of the melodic line) remain
                    intentionally out of scope for this field — those are
                    authored manually in Logic after render, not modeled
                    by `intervals`.
    rhythm:         Duration in beats for each note.
                    e.g. [1.0, 0.5, 0.5, 1.0]
    name:           Optional label for identification.
    transform_pool: Transforms eligible for variation generation.
    generation:     How many transforms away from the original (0 = source).
    parent_name:    Name of the motif this was derived from.
    melodic_scale:  Optional scale override for THIS motif's pitches,
                    independent of the piece's harmonic mode (Phase B4 —
                    see schemas.py's MotifModel._validate_melodic_scale for
                    the full contract). None means "use the piece's mode",
                    unchanged from before this field existed.
    """
    intervals: list[int]
    rhythm: list[float]
    rests: Optional[list[bool]] = None
    name: str = "motif"
    transform_pool: list[str] = field(default_factory=lambda: [
        "inversion", "retrograde", "augmentation", "diminution", "transpose_up",
        "transpose_down", "shuffle"
    ])
    generation: int = 0
    parent_name: Optional[str] = None
    melodic_scale: Optional[str] = None

    def __post_init__(self):
        # Pad or trim rhythm to match interval count
        n = len(self.intervals)
        if len(self.rhythm) < n:
            self.rhythm = (self.rhythm * ((n // len(self.rhythm)) + 1))[:n]
        elif len(self.rhythm) > n:
            self.rhythm = self.rhythm[:n]
        # Pad or trim rests to match — default False (sounds) for anything
        # added by padding, since a rest must be deliberately authored.
        if self.rests is not None:
            if len(self.rests) < n:
                self.rests = self.rests + [False] * (n - len(self.rests))
            elif len(self.rests) > n:
                self.rests = self.rests[:n]

    def __repr__(self):
        return (f"Motif('{self.name}' gen={self.generation} "
                f"intervals={self.intervals} rhythm={self.rhythm})")

    def note_count(self) -> int:
        return len(self.intervals)

    def total_duration(self) -> float:
        return sum(self.rhythm)

    def interval_range(self) -> int:
        """
        Total DIATONIC SCALE-DEGREE span of the motif — how many scale
        steps separate its highest and lowest points, not semitones.

        This is a genuine unit change (Phase B5), not a hedge: every motif
        produced by motif_to_notes or apply_transform's transpose (Phase
        B2/B3) now holds diatonic steps in `intervals`, so this number
        means "spans N scale degrees," e.g. 4 means a fourth-to-fifth-ish
        range depending on the mode — not "spans 4 semitones." A motif
        with the same shape sounds like a wider or narrower leap in
        different modes even though this number is identical, because a
        diatonic step is a variable number of semitones depending on where
        in the mode it falls (most steps are a whole tone, but every mode
        has exactly one or two half-step positions — see harmony.py's
        MODES). If you need the actual semitone/register width instead of
        the scale-degree count, use semitone_span(mode) below, which
        resolves this the way it actually sounds in a given mode.
        """
        pos = 0
        positions = [0]
        for i in self.intervals:
            pos += i
            positions.append(pos)
        return max(positions) - min(positions)

    def semitone_span(self, mode: str) -> int:
        """
        Actual semitone width the motif spans when interpreted in `mode`.

        interval_range() alone can't answer this (Phase B5): it returns
        diatonic-DEGREE span, which doesn't translate to a fixed semitone
        count without knowing the mode's own step pattern. This resolves
        each cumulative scale-degree position to its real semitone offset
        within `mode` and returns the true register width — the question
        interval_range() used to answer for free back when `intervals`
        held semitones directly, before Phase B2/B3 changed what unit is
        actually stored.

        Reuses harmony.py's MODES (already a sorted pitch-class list per
        mode, same shape scale_degrees.degree_to_pitch expects) rather
        than re-deriving scale tones from a key/register — this only
        needs the mode's shape, not an absolute pitch, since it's
        measuring a relative span.
        """
        from intervals.music.harmony import MODES
        from intervals.music.scale_degrees import degree_to_pitch

        pcs = MODES[mode.lower()]
        pos = 0
        pitches = [degree_to_pitch(0, pcs)]
        for i in self.intervals:
            pos += i
            pitches.append(degree_to_pitch(pos, pcs))
        return max(pitches) - min(pitches)

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
    # DECIDED (Phase B3): 1 diatonic step (nearest scale-degree neighbor).
    "transpose_up":  "Shift all intervals up by 1 diatonic step",
    "transpose_down":"Shift all intervals down by 1 diatonic step",
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
        rng = random.Random(seed)
    else:
        rng = random.Random()

    intervals = list(motif.intervals)
    rhythm    = list(motif.rhythm)
    rests     = list(motif.rests) if motif.rests is not None else None
    name      = f"{motif.name}_{transform_name}"

    if transform_name == "inversion":
        intervals = [-i for i in intervals]

    elif transform_name == "retrograde":
        intervals = list(reversed(intervals))
        rhythm    = list(reversed(rhythm))
        if rests is not None:
            rests = list(reversed(rests))

    elif transform_name == "retrograde_inversion":
        intervals = [-i for i in reversed(intervals)]
        rhythm    = list(reversed(rhythm))
        if rests is not None:
            rests = list(reversed(rests))

    elif transform_name == "augmentation":
        rhythm = [r * 2.0 for r in rhythm]

    elif transform_name == "diminution":
        rhythm = [max(0.25, r * 0.5) for r in rhythm]

    elif transform_name == "transpose_up":
        # Phase B3: 1 diatonic step (decided) -- was 2 under the old
        # semitone contract; see TRANSFORM_DESCRIPTIONS above.
        intervals = [i + 1 for i in intervals]

    elif transform_name == "transpose_down":
        intervals = [i - 1 for i in intervals]

    elif transform_name == "shuffle":
        if rests is not None:
            combined = list(zip(intervals, rhythm, rests))
            rng.shuffle(combined)
            intervals, rhythm, rests = zip(*combined) if combined else ([], [], [])
            intervals, rhythm, rests = list(intervals), list(rhythm), list(rests)
        else:
            combined = list(zip(intervals, rhythm))
            rng.shuffle(combined)
            intervals, rhythm = zip(*combined) if combined else ([], [])
            intervals = list(intervals)
            rhythm    = list(rhythm)

    elif transform_name == "expand":
        intervals = [int(round(i * 1.5)) for i in intervals]

    elif transform_name == "compress":
        compressed = []
        for original_i in intervals:
            c = int(round(original_i * 0.5))
            # Ensure no zero intervals (use +/-1 minimum for non-zero):
            # rounding a nonzero original interval down to 0 (e.g. a single
            # semitone) would otherwise collapse a real melodic step into no
            # step at all. Substitute +/-1, matching the original interval's
            # direction, so the contour survives compression. A genuinely
            # zero original interval stays 0 -- there was no step to preserve.
            if c == 0 and original_i != 0:
                c = 1 if original_i > 0 else -1
            compressed.append(c)
        intervals = compressed

    else:
        raise ValueError(
            f"Unknown transform: '{transform_name}'. "
            f"Choose from: {list(TRANSFORM_DESCRIPTIONS.keys())}"
        )

    return Motif(
        intervals=intervals,
        rhythm=rhythm,
        rests=rests,
        name=name,
        transform_pool=list(motif.transform_pool),
        generation=motif.generation + 1,
        parent_name=motif.name,
        melodic_scale=motif.melodic_scale,
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
        interval_range: Max change per mutation, in whatever unit
                        motif.intervals currently holds (semitones today;
                        diatonic scale-degree steps once Phase B lands —
                        see Motif.intervals docstring)
        seed:           Random seed

    Returns:
        New Motif with random mutations applied
    """
    rng = random.Random(seed) if seed is not None else random.Random()

    intervals = list(motif.intervals)
    for i in range(len(intervals)):
        if rng.random() < mutation_rate:
            delta = rng.randint(-interval_range, interval_range)
            intervals[i] += delta

    return Motif(
        intervals=intervals,
        rhythm=list(motif.rhythm),
        name=f"{motif.name}_mutated",
        transform_pool=list(motif.transform_pool),
        generation=motif.generation + 1,
        parent_name=motif.name,
        melodic_scale=motif.melodic_scale,
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
        max_interval: Maximum absolute jump, in whatever unit
                      motif.intervals currently holds (semitones today;
                      diatonic scale-degree steps once Phase B lands —
                      see Motif.intervals docstring)
        rhythm_pool:  Durations to sample from (default: [0.5, 1.0, 1.5, 2.0])
        name:         Motif name
        seed:         Random seed

    Returns:
        New random Motif
    """
    rng = random.Random(seed) if seed is not None else random.Random()

    if rhythm_pool is None:
        rhythm_pool = [0.5, 1.0, 1.5, 2.0]

    # Avoid all-zero intervals
    intervals = []
    for _ in range(length):
        v = 0
        while v == 0:
            v = rng.randint(-max_interval, max_interval)
        intervals.append(v)

    rhythm = [rng.choice(rhythm_pool) for _ in range(length)]

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

    Expected keys: intervals, rhythm, name (optional), transform_pool (optional),
    melodic_scale (optional, Phase B4 — see Motif.melodic_scale docstring)
    """
    return Motif(
        intervals=d["intervals"],
        rhythm=d.get("rhythm", [1.0] * len(d["intervals"])),
        rests=d.get("rests"),
        name=d.get("name", "motif"),
        transform_pool=d.get("transform_pool", [
            "inversion", "retrograde", "augmentation",
            "diminution", "transpose_up", "transpose_down"
        ]),
        melodic_scale=d.get("melodic_scale"),
    )


def to_dict(motif: Motif) -> dict:
    """Serialise a Motif to a dictionary suitable for JSON output."""
    d = {
        "name":           motif.name,
        "intervals":      motif.intervals,
        "rhythm":         motif.rhythm,
        "transform_pool": motif.transform_pool,
        "generation":     motif.generation,
        "parent_name":    motif.parent_name,
    }
    if motif.rests is not None:
        d["rests"] = motif.rests
    if motif.melodic_scale is not None:
        d["melodic_scale"] = motif.melodic_scale
    return d


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
    print(f"Range:   {source.interval_range()} diatonic scale degrees")
    print(f"Span:    {source.semitone_span('dorian')} semitones (in dorian)")
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
