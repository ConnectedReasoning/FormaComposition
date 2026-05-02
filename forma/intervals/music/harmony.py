"""
harmony.py — Intervals Engine
Resolves Roman numeral progressions to voiced MIDI chords.
Handles modes, inversions, and extensions (triads, 7ths, 9ths, 11ths).
"""

from dataclasses import dataclass, field
from typing import Optional

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

CHROMATIC = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"]

# Interval patterns for each mode (whole/half steps as semitone offsets from root)
MODES = {
    "ionian":     [0, 2, 4, 5, 7, 9, 11],   # major
    "dorian":     [0, 2, 3, 5, 7, 9, 10],
    "phrygian":   [0, 1, 3, 5, 7, 8, 10],
    "lydian":     [0, 2, 4, 6, 7, 9, 11],
    "mixolydian": [0, 2, 4, 5, 7, 9, 10],
    "aeolian":    [0, 2, 3, 5, 7, 8, 10],   # natural minor
    "locrian":    [0, 1, 3, 5, 6, 8, 10],
}

# Roman numeral → scale degree index (0-based)
ROMAN_TO_DEGREE = {
    "I": 0, "II": 1, "III": 2, "IV": 3, "V": 4, "VI": 5, "VII": 6,
    "i": 0, "ii": 1, "iii": 2, "iv": 3, "v": 4, "vi": 5, "vii": 6,
}

# Chord quality overrides — explicit symbols take precedence over mode-derived quality
QUALITY_SYMBOLS = {
    "maj":  "major",
    "min":  "minor",
    "dim":  "diminished",
    "aug":  "augmented",
    "maj7": "major7",
    "m7":   "minor7",
    "7":    "dominant7",
    "dim7": "diminished7",
    "m9":   "minor9",
    "maj9": "major9",
    "9":    "dominant9",
    "m11":  "minor11",
    "11":   "dominant11",
}

# Semitone intervals for chord tones relative to chord root
# Format: (third, fifth, seventh, ninth, eleventh)
CHORD_INTERVALS = {
    "major":        (4, 7),
    "minor":        (3, 7),
    "diminished":   (3, 6),
    "augmented":    (4, 8),
    "major7":       (4, 7, 11),
    "minor7":       (3, 7, 10),
    "dominant7":    (4, 7, 10),
    "diminished7":  (3, 6, 9),
    "minor9":       (3, 7, 10, 14),
    "major9":       (4, 7, 11, 14),
    "dominant9":    (4, 7, 10, 14),
    "minor11":      (3, 7, 10, 14, 17),
    "dominant11":   (4, 7, 10, 14, 17),
}

# Density → maximum number of chord tones to voice
DENSITY_TONES = {
    "sparse": 3,    # triad only
    "medium": 4,    # triad + seventh
    "full":   6,    # all available extensions
}

# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------

@dataclass
class VoicedChord:
    """A fully resolved, voiced chord ready for MIDI output."""
    root_name: str          # e.g. "D"
    quality: str            # e.g. "minor7"
    midi_notes: list[int]   # absolute MIDI note numbers, lowest first
    inversion: int = 0      # 0=root, 1=first, 2=second, 3=third
    roman: str = ""         # original Roman numeral string
    degree: int = 0         # scale degree 0-6

    # Per-chord rhythm DNA.  When present, the harmony strategy uses these
    # events instead of the section-level stencil.  Events are expressed in
    # chord-local beat coordinates (first onset at 0.0).
    # Set by _enrich_chords_with_rhythm() in generator.py; never populated by
    # resolve_progression() or resolve_chord() directly.
    rhythm_events: Optional[list] = field(default=None, repr=False)

    def __repr__(self):
        notes_str = ", ".join(str(n) for n in self.midi_notes)
        dna = f" dna={len(self.rhythm_events)}ev" if self.rhythm_events else ""
        return f"VoicedChord({self.root_name}{self.quality} inv={self.inversion} [{notes_str}]{dna})"


# ---------------------------------------------------------------------------
# Core helpers
# ---------------------------------------------------------------------------

def key_to_midi_root(key: str, octave: int = 4) -> int:
    """Return the MIDI note number for a key name at a given octave."""
    key = key.strip()
    # Normalise flats to sharps
    flat_map = {"Db": "C#", "Eb": "D#", "Gb": "F#", "Ab": "G#", "Bb": "A#"}
    key = flat_map.get(key, key)
    if key not in CHROMATIC:
        raise ValueError(f"Unknown key: '{key}'. Use note names like C, D#, Bb.")
    return (octave + 1) * 12 + CHROMATIC.index(key)


def get_scale(key: str, mode: str, octave: int = 4) -> list[int]:
    """Return MIDI note numbers for a one-octave scale."""
    mode = mode.lower()
    if mode not in MODES:
        raise ValueError(f"Unknown mode: '{mode}'. Choose from {list(MODES.keys())}.")
    root_midi = key_to_midi_root(key, octave)
    return [root_midi + interval for interval in MODES[mode]]


def parse_roman(roman: str) -> tuple[int, Optional[str]]:
    """
    Parse a Roman numeral string into (degree_index, quality_override_or_None).
    Supports chromatic alterations with 'b' (flat) and '#' (sharp) prefixes.

    Examples:
        "i"      → (0, None)
        "IV"     → (3, None)
        "iim7"   → (1, "minor7")
        "Vmaj9"  → (4, "major9")
        "viidim" → (6, "diminished")
        "bVI"    → (5, None)  [VI lowered by semitone]
        "#iv"    → (3, None)  [iv raised by semitone]
        "bVImaj7" → (5, "major7")  [alteration + quality]
    """
    # Strip leading/trailing whitespace
    roman = roman.strip()

    # Check for chromatic alteration prefix
    alteration = 0  # -1 for flat, +1 for sharp
    if roman.startswith('b'):
        alteration = -1
        roman = roman[1:]
    elif roman.startswith('#'):
        alteration = 1
        roman = roman[1:]

    # Extract the base Roman numeral (uppercase comparison)
    upper = roman.upper()
    base = None
    for r in sorted(ROMAN_TO_DEGREE.keys(), key=len, reverse=True):
        if upper.startswith(r.upper()):
            base = r.upper()
            break
    if base is None:
        raise ValueError(f"Cannot parse Roman numeral: '{roman}'")

    degree = ROMAN_TO_DEGREE[base.upper()]

    # Apply chromatic alteration
    # In a 7-degree system, alterations wrap: bI → VII, #VII → I, etc.
    degree = (degree + alteration) % 7

    remainder = roman[len(base):]  # anything after the numeral

    # Check for explicit quality symbol
    quality_override = None
    for symbol in sorted(QUALITY_SYMBOLS.keys(), key=len, reverse=True):
        if remainder.lower().startswith(symbol.lower()):
            quality_override = QUALITY_SYMBOLS[symbol.lower()]
            break

    return degree, quality_override


def mode_chord_quality(degree: int, mode: str, density: str) -> str:
    """
    Derive the natural chord quality at a scale degree within a mode,
    then extend it based on density.
    """
    mode = mode.lower()
    intervals = MODES[mode]
    max_tones = DENSITY_TONES.get(density, 3)

    # Build intervals: third and fifth relative to degree root
    third = (intervals[(degree + 2) % 7] - intervals[degree]) % 12
    fifth = (intervals[(degree + 4) % 7] - intervals[degree]) % 12
    seventh = (intervals[(degree + 6) % 7] - intervals[degree]) % 12

    # Determine triad quality
    if third == 4 and fifth == 7:
        base = "major"
    elif third == 3 and fifth == 7:
        base = "minor"
    elif third == 3 and fifth == 6:
        base = "diminished"
    elif third == 4 and fifth == 8:
        base = "augmented"
    else:
        base = "major"  # fallback

    if max_tones <= 3:
        return base

    # Extend to seventh
    if max_tones >= 4:
        if base == "major" and seventh == 11:
            quality = "major7"
        elif base == "major" and seventh == 10:
            quality = "dominant7"
        elif base == "minor" and seventh == 10:
            quality = "minor7"
        elif base == "diminished" and seventh == 9:
            quality = "diminished7"
        else:
            quality = base  # no clean seventh, stay as triad
    else:
        quality = base

    if max_tones <= 4:
        return quality

    # Extend to ninth
    ninth_interval = (intervals[(degree + 1) % 7] - intervals[degree]) % 12 + 12
    if "major7" in quality:
        quality = "major9"
    elif "minor7" in quality:
        quality = "minor9"
    elif "dominant7" in quality:
        quality = "dominant9"

    if max_tones <= 5:
        return quality

    # Extend to eleventh
    if "minor9" in quality:
        quality = "minor11"
    elif "dominant9" in quality:
        quality = "dominant11"

    return quality


# ---------------------------------------------------------------------------
# Voicing
# ---------------------------------------------------------------------------

def build_chord_tones(root_midi: int, quality: str, density: str) -> list[int]:
    """
    Build the MIDI note list for a chord given its root and quality,
    capped by density.
    """
    if quality not in CHORD_INTERVALS:
        # Fallback: treat as major triad
        quality = "major"
    intervals = CHORD_INTERVALS[quality]
    max_tones = DENSITY_TONES.get(density, 3)
    tones = [root_midi] + [root_midi + i for i in intervals]
    return tones[:max_tones]


def apply_inversion(tones: list[int], inversion: int) -> list[int]:
    """
    Apply a chord inversion by rotating the bass note up an octave.
    inversion=0 → root position
    inversion=1 → first inversion (third in bass)
    inversion=2 → second inversion (fifth in bass)
    inversion=3 → third inversion (seventh in bass, if present)
    """
    if inversion == 0 or len(tones) <= inversion:
        return sorted(tones)
    result = list(tones)
    for _ in range(inversion):
        result[0] += 12
        result = sorted(result)
    return result


def choose_inversion_for_voice_leading(
    tones: list[int],
    prev_chord: Optional["VoicedChord"],
    register_bottom: int = 48,   # C3
    register_top: int = 72,      # C5
) -> tuple[list[int], int]:
    """
    Choose the inversion that minimises total movement from the previous chord
    and keeps notes within the target register.
    Returns (voiced_notes, inversion_number).
    """
    max_inv = min(3, len(tones) - 1)
    candidates = []

    for inv in range(max_inv + 1):
        voiced = apply_inversion(tones, inv)
        # Shift the whole chord into register if needed
        while voiced[0] < register_bottom:
            voiced = [n + 12 for n in voiced]
        while voiced[0] > register_bottom + 12:
            voiced = [n - 12 for n in voiced]
        # Score: minimize voice movement from previous chord
        if prev_chord is not None:
            prev = prev_chord.midi_notes
            min_len = min(len(voiced), len(prev))
            movement = sum(abs(voiced[i] - prev[i]) for i in range(min_len))
        else:
            movement = 0
        # Penalise notes outside register
        out_of_range = sum(1 for n in voiced if n < register_bottom or n > register_top)
        score = movement + out_of_range * 10
        candidates.append((score, inv, voiced))

    candidates.sort(key=lambda x: x[0])
    _, best_inv, best_voiced = candidates[0]
    return best_voiced, best_inv


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def resolve_chord(
    roman: str,
    key: str,
    mode: str,
    density: str = "medium",
    prev_chord: Optional[VoicedChord] = None,
    register_bottom: int = 48,
    register_top: int = 72,
    octave: int = 4,
) -> VoicedChord:
    """
    Resolve a Roman numeral to a fully voiced VoicedChord.

    Args:
        roman:          Roman numeral string e.g. "i", "IV", "iim7"
        key:            Key center e.g. "D", "F#", "Bb"
        mode:           Mode name e.g. "dorian", "ionian"
        density:        "sparse" | "medium" | "full"
        prev_chord:     Previous VoicedChord for voice leading (or None)
        register_bottom: Lowest acceptable MIDI note
        register_top:   Highest acceptable MIDI note
        octave:         Base octave for scale construction

    Returns:
        VoicedChord with MIDI notes, inversion, quality, root name
    """
    degree, quality_override = parse_roman(roman)
    scale = get_scale(key, mode, octave)
    root_midi = scale[degree]
    root_name = CHROMATIC[root_midi % 12]

    quality = quality_override if quality_override else mode_chord_quality(degree, mode, density)

    raw_tones = build_chord_tones(root_midi, quality, density)
    voiced, inversion = choose_inversion_for_voice_leading(
        raw_tones, prev_chord, register_bottom, register_top
    )

    return VoicedChord(
        root_name=root_name,
        quality=quality,
        midi_notes=voiced,
        inversion=inversion,
        roman=roman,
        degree=degree,
    )


def resolve_progression(
    progression: list[str],
    key: str,
    mode: str,
    density: str = "medium",
    register_bottom: int = 48,
    register_top: int = 72,
    octave: int = 4,
) -> list[VoicedChord]:
    """
    Resolve a full progression to a list of VoicedChords with smooth voice leading.

    Args:
        progression:    List of Roman numeral strings e.g. ["i", "VII", "iv", "v"]
        key:            Key center
        mode:           Mode name
        density:        "sparse" | "medium" | "full"
        register_bottom/top: MIDI note range for voicing
        octave:         Base octave

    Returns:
        List of VoicedChord objects
    """
    chords = []
    prev = None
    for roman in progression:
        chord = resolve_chord(
            roman, key, mode, density, prev, register_bottom, register_top, octave
        )
        chords.append(chord)
        prev = chord
    return chords


# ---------------------------------------------------------------------------
# Quick test / demo
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    print("=== Intervals Engine — harmony.py demo ===\n")

    key = "D"
    mode = "dorian"
    progression = ["i", "VII", "iv", "v"]

    for density in ("sparse", "medium", "full"):
        print(f"Key: {key}  Mode: {mode}  Density: {density}")
        chords = resolve_progression(progression, key, mode, density)
        for roman, chord in zip(progression, chords):
            names = [f"{CHROMATIC[n % 12]}{n}" for n in chord.midi_notes]
            print(f"  {roman:6s} → {chord.root_name:3s} {chord.quality:12s}  inv={chord.inversion}  {names}")
        print()

    # Test a different key and mode
    print("Key: F  Mode: lydian  Density: full")
    chords = resolve_progression(["I", "II", "VII", "I"], "F", "lydian", "full")
    for roman, chord in zip(["I", "II", "VII", "I"], chords):
        names = [f"{CHROMATIC[n % 12]}{n}" for n in chord.midi_notes]
        print(f"  {roman:6s} → {chord.root_name:3s} {chord.quality:12s}  inv={chord.inversion}  {names}")
