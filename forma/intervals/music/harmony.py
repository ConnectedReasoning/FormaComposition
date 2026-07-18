"""
harmony.py — Intervals Engine
Resolves Roman numeral progressions to voiced MIDI chords.
Handles modes, inversions, and extensions (triads, 7ths, 9ths, 11ths).
"""

from dataclasses import dataclass, field
from typing import Optional

import random
from abc import ABC, abstractmethod

from intervals.core.musical_time import MusicalTime, bar_beat_from_event_offset
from intervals.music.rhythm import (
    RhythmEvent, get_pattern,
    apply_velocity_arc, apply_swing, remap_swing_ratio,
    _slice_events_into_window, rhythm_pattern_to_events,
    _motif_rhythm_to_events_varied,
)

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
    # Non-diatonic additions
    "harmonic_minor":  [0, 2, 3, 5, 7, 8, 11],  # raised 7th — fugues, dramatic cadences
    "melodic_minor":   [0, 2, 3, 5, 7, 9, 11],  # jazz minor — ascending form
    "pentatonic_major":[0, 2, 4, 7, 9],          # 5 notes — open, no tension
    "pentatonic_minor":[0, 3, 5, 7, 10],         # blues foundation
    "blues":           [0, 3, 5, 6, 7, 10],      # pentatonic minor + flat 5
    "whole_tone":      [0, 2, 4, 6, 8, 10],      # all whole steps — Debussy, dreamy
    "diminished":      [0, 2, 3, 5, 6, 8, 9, 11],# alternating whole/half — tension
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
    n = len(intervals)
    max_tones = DENSITY_TONES.get(density, 3)

    # Build intervals: third and fifth relative to degree root
    third = (intervals[(degree + 2) % n] - intervals[degree]) % 12
    fifth = (intervals[(degree + 4) % n] - intervals[degree]) % 12
    seventh = (intervals[(degree + 6) % n] - intervals[degree]) % 12

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
    ninth_interval = (intervals[(degree + 1) % n] - intervals[degree]) % 12 + 12
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

def _resolve_secondary_chord(
    roman: str,
    key: str,
    mode: str,
    density: str,
    prev_chord: Optional[VoicedChord],
    register_bottom: int,
    register_top: int,
    octave: int,
) -> VoicedChord:
    """
    Resolve a secondary/applied chord written as "APPLIED/TARGET", e.g. "V7/ii"
    (the dominant seventh that tonicizes ii), "V/IV", "vii/V", etc.

    TARGET is only ever used to locate a root — its own quality is resolved
    and then discarded; it never sounds. APPLIED is built as an absolute
    chord on top of TARGET's root, not the section's actual tonic. That's
    what "tonicizing" TARGET means: APPLIED borrows the function it would
    have if TARGET were briefly the tonic.

    The interval from the mode's tonic to APPLIED's scale degree (reusing
    the same scale table ordinary chords use) is added on top of TARGET's
    root rather than the tonic's. This is mode-invariant for 6 of the 7
    supported modes — V sits at +7 semitones in everything except Locrian,
    where it's +6 — reusing the existing table keeps that consistent
    automatically rather than hardcoding a fixed "always a perfect fifth"
    interval that would be wrong specifically for Locrian.

    APPLIED's quality: an explicit suffix if given ("V7" -> dominant7),
    else defaults to plain "major" — never the mode's diatonic derivation.
    A secondary chord is foreign to the diatonic scale by definition; there
    is no meaningful "natural" mode-derived quality to fall back to.

    Disambiguation: TARGET must parse as a valid Roman numeral. "/" is also
    standard notation for slash chords / inversions ("C/E", "I/3"), which
    this engine does not implement. Rather than silently misinterpreting
    that as a malformed secondary chord (dropping the numerator's meaning
    the way the old comma-progression bug did), an unrecognized TARGET
    raises a clear, specific error instead.
    """
    applied_str, target_str = roman.split("/", 1)
    applied_str = applied_str.strip()
    target_str = target_str.strip()

    try:
        target_degree, _ = parse_roman(target_str)
    except ValueError:
        raise ValueError(
            f"Cannot resolve '{roman}': '{target_str}' is not a valid Roman "
            f"numeral. Secondary-dominant notation requires a Roman numeral "
            f"target ('V7/ii', 'V/IV'). Slash-chord / inversion notation "
            f"('C/E', 'I/3') is not implemented — if that's what you meant, "
            f"this piece needs a different approach for now."
        )

    applied_degree, applied_quality_override = parse_roman(applied_str)

    scale = get_scale(key, mode, octave)
    tonic_midi = scale[0]
    target_root_midi = scale[target_degree]
    applied_offset = scale[applied_degree] - tonic_midi
    applied_root_midi = target_root_midi + applied_offset

    root_name = CHROMATIC[applied_root_midi % 12]
    quality = applied_quality_override if applied_quality_override else "major"

    raw_tones = build_chord_tones(applied_root_midi, quality, density)
    voiced, inversion = choose_inversion_for_voice_leading(
        raw_tones, prev_chord, register_bottom, register_top
    )

    return VoicedChord(
        root_name=root_name,
        quality=quality,
        midi_notes=voiced,
        inversion=inversion,
        roman=roman,
        degree=applied_degree,
    )


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
        roman:          Roman numeral string e.g. "i", "IV", "iim7", or a
                         secondary/applied chord "APPLIED/TARGET" e.g. "V7/ii"
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
    if "/" in roman:
        return _resolve_secondary_chord(
            roman, key, mode, density, prev_chord, register_bottom, register_top, octave
        )

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


# ═════════════════════════════════════════════════════════════════════════════
# Harmony chord-event generation — relocated from strategies.py (item 9, ST-2a)
# ═════════════════════════════════════════════════════════════════════════════
#
# Everything below was in intervals/core/strategies.py. It moved here because
# harmony's domain logic (strategy dispatch, chord event production, context
# dataclasses) belongs in the voice module, not in a core-layer dispatcher.
# counterpoint.py and bass.py already own their equivalent logic; this
# completes the pattern for the fourth voice.


_CHANNEL_HARMONY = 1
_REARTIC_GAP = 0.03   # beats — inaudible gap prevents note-off/on overlap


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


# ═════════════════════════════════════════════════════════════════════════════
# Section-level rhythm source resolution — relocated from generator.py (item 9, ST-2b)
# ═════════════════════════════════════════════════════════════════════════════
#
# This is harmony's other rhythm decision, distinct from build_harmony_chord_context
# above: which source (sustain/pattern/motif/free) applies to the WHOLE section,
# and what section-wide event stream (if any) that source produces. Formerly an
# inline switchboard in generate_piece() — moved here so harmony owns both halves
# of its rhythm decision in one module, matching build_harmony_chord_context's
# per-chord half.
#
# Deliberately NOT moved here: resolving harmony's motif (harmony_rhythm.motif vs
# the theme's active_motif_def fallback) and dumping harmony_pattern's Pydantic
# model to a plain dict. Both are declared-config reads keyed off SectionModel,
# same translation-layer work generate_piece() already does for melody's motif —
# keeping them there avoids harmony.py importing schemas.py (a music -> core
# import this module has never needed) and motif_loader.py (a further core ->
# music zigzag). This function receives the resolved results as plain values.

def resolve_harmony_section_events(
    explicit_source: Optional[str],
    melody_rhythm_source: str,
    section_name: str,
    total_beats_section: float,
    density: str,
    harmony_pattern: Optional[dict],
    hr_density: Optional[str],
    harmony_motif_def: Optional[dict],
    harmony_motif_desc: str,
    transform_imitation: Optional[str] = None,
    seed: Optional[int] = None,
) -> tuple:
    """
    Resolve harmony's rhythm source for one section into a section-wide event
    stream (or sentinel), plus a description of what was chosen.

    transform_imitation, seed (item 17 / ST-5): only consulted on the
    "motif" branch. None (default) -> harmony picks its own transform each
    repetition, independently, from harmony_motif_def's transform_pool,
    seeded from `seed` for determinism. "strict" -> NOT YET IMPLEMENTED;
    raises rather than silently falling back to the default or ignoring the
    setting -- see the ValueError's own message for why (melody's transform
    choices don't exist yet at the point harmony resolves; the two voices'
    "repetition" isn't even the same shape -- melody's is chord-scoped and
    develop-behavior-only, harmony's is a continuous section-wide cycle).

    Returns (harmony_section_events, description):
      harmony_section_events — "sustain" | list[RhythmEvent] | None.
        None means "free": the _FreeHarmonyStrategy density grid handles it,
        including the case where "pattern" was declared but no harmony_pattern
        was actually supplied (silent no-op, preserved from the original
        switchboard rather than "fixed" here — a relocation, not a bug hunt).
      description — a ready-to-print string, possibly containing an embedded
        newline (the inherited-motif coercion case produces two lines, exactly
        as the original two separate print() calls did), or None when nothing
        should be printed. This function never prints; the caller owns that
        (item 9 ST-2b decision — voice modules return text, generate_piece()
        prints it, matching how every other voice's summary line works).

    explicit_source: harmony_rhythm.rhythm if a harmony_rhythm block is present
      and set, else None. melody_rhythm_source: the section's top-level rhythm
      (harmony's fallback when explicit_source is unset).
    """
    source = explicit_source or melody_rhythm_source

    # "motif" is only valid for harmony when set EXPLICITLY on harmony_rhythm
    # itself. Falling back to the section's top-level `rhythm` — "motif" for
    # nearly every melodic section — would silently activate harmony's
    # independent motif mechanism on every such section whether or not it was
    # asked for. Coerce the inherited case to "free"; the explicit case is
    # untouched. Falls through to the "free" branch below (not a separate
    # return) so the two print lines the original produced — the coercion
    # notice, then "free"'s own line — are both preserved.
    lines = []
    if source == "motif" and explicit_source != "motif":
        source = "free"
        lines.append("    Harmony rhythm: 'motif' inherited from section rhythm — "
                      "not valid for harmony, defaulting to 'free'")

    if source == "sustain":
        lines.append("    Harmony rhythm: sustain")
        return "sustain", "\n".join(lines)

    if source == "pattern":
        if harmony_pattern:
            events = rhythm_pattern_to_events(harmony_pattern, total_beats=total_beats_section)
            lines.append(f"    Harmony rhythm: hand-played pattern "
                          f"({len(harmony_pattern['onsets'])} onsets)")
            return events, "\n".join(lines)
        # harmony_rhythm.rhythm == "pattern" but no harmony_pattern block was
        # supplied. Original switchboard fell all the way through with no
        # events, no print, no error — same here.
        return None, ("\n".join(lines) if lines else None)

    if source == "motif":
        # Harmony's own motif, independent of melody's. Resolution (which
        # motif, with what fallback) already happened in generate_piece();
        # this function only validates the RESULT and decides what to do
        # with it, which is a harmony-domain judgment, not a config read.
        if not harmony_motif_def or not harmony_motif_def.get("rhythm"):
            raise ValueError(
                f"Section '{section_name}': harmony_rhythm.rhythm="
                f"'motif' but no motif with a 'rhythm' field is available "
                f"(neither harmony_rhythm.motif nor the theme's motif)"
            )

        # item 17 / ST-5: "strict" (harmony inherits melody's transform
        # choice each repetition) is not yet implemented. Raising here
        # rather than silently falling back to independent selection or
        # ignoring the field -- exactly the silent-no-op failure mode this
        # engine's lint checks exist to catch elsewhere, so the un-built
        # path shouldn't quietly become one itself. Two open problems
        # block it, not implementation effort: (1) harmony's rhythm
        # resolves here, in generate_section, BEFORE melody's actual notes
        # (and therefore its transform choices) are generated at all --
        # there is no "melody's choice" yet to inherit at this point in the
        # pipeline; (2) melody's transform selection only exists for
        # "develop" behavior, chosen per-chord inside generate_develop,
        # while harmony's cycling is continuous across the whole section
        # regardless of behavior or chord boundaries -- the two voices'
        # "repetition" isn't the same shape, so "the same choice" isn't
        # well-defined yet even once ordering is solved.
        if transform_imitation == "strict":
            raise ValueError(
                f"Section '{section_name}': harmony_rhythm.transform_imitation="
                f"'strict' is not yet implemented. Harmony's motif rhythm "
                f"resolves before melody's notes (and its transform choices) "
                f"exist, and the two voices' repetition cadence don't "
                f"currently share a common shape to inherit across. Leave "
                f"transform_imitation unset for harmony's independent "
                f"per-repetition transform selection (item 17's shipped fix)."
            )

        # density selects onset articulation — full/stressed/anchor, the same
        # subsetting _motif_rhythm_to_events already offers melody and bass —
        # so density has a real, audible effect here instead of being
        # silently ignored the way the retired version left it. groove is
        # intentionally NOT consulted: the motif cell already IS the rhythm,
        # same as melody's "motif" rhythm source. lint.py flags
        # harmony_rhythm.groove set alongside this as a no-op.
        h_density = hr_density if hr_density else density
        articulation = {
            "low": "anchor", "sparse": "anchor",
            "medium": "stressed", "full": "full",
        }.get(h_density, "stressed")

        # Tiled across the WHOLE section (not per chord) so the onset stream
        # runs continuously through chord changes — the "its own syncopated
        # life against the bass" behavior the theme file asks for.
        # _enrich_chords_with_rhythm slices this into each chord's local
        # window; _MotifHarmonyStrategy consumes those slices exactly like
        # _PatternHarmonyStrategy does.
        #
        # item 17 / ST-5 fix: each cycle of the tile now gets its own
        # independently-chosen transform from the motif's transform_pool
        # (empty/absent pool degrades to exactly the old verbatim-tiling
        # behavior — see _motif_rhythm_to_events_varied's own docstring),
        # replacing the confirmed bug where every repetition across the
        # section was an untransformed clone of the first.
        events = _motif_rhythm_to_events_varied(
            harmony_motif_def["rhythm"], total_beats_section,
            harmony_motif_def.get("transform_pool", []), articulation,
            velocities=harmony_motif_def.get("velocities"),
            rests=harmony_motif_def.get("rests"),
            seed=seed,
        )
        cycle = sum(harmony_motif_def["rhythm"])
        lines.append(f"    Harmony rhythm: motif {articulation} ({len(events)} "
                      f"onsets, {cycle:.1f}b cycle, density={h_density}, "
                      f"motif={harmony_motif_desc}) — continuous across chord changes")
        return events, "\n".join(lines)

    # "free"
    lines.append("    Harmony rhythm: free (density grid)")
    return None, "\n".join(lines)
