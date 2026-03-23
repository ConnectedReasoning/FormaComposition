"""
bass.py — Intervals Engine
Generates bass lines from a resolved chord progression.

Bass styles:
  root_only   — whole note root, one per chord. Minimal, drone-like.
  root_fifth  — alternates root and fifth. Classic new age / ambient.
  walking     — stepwise movement between chord roots. More melodic.
  pulse       — repeated root notes on the beat. Rhythmic, driving.
  pedal       — holds a single pedal tone (tonic) regardless of chord. Eno-ish.
"""

import random
from dataclasses import dataclass, field
from typing import Optional
from intervals.music.harmony import VoicedChord, CHROMATIC

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

BASS_OCTAVE_BOTTOM = 36   # C2
BASS_OCTAVE_TOP    = 48   # C3

# Density → rhythmic subdivision multiplier (in beats, assuming 4/4)
# These are note durations in beats
DENSITY_DURATIONS = {
    "sparse": 4.0,    # whole note per chord change
    "medium": 2.0,    # half note
    "full":   1.0,    # quarter note
}

# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------

@dataclass
class BassNote:
    """A single bass note with timing."""
    midi_note: int
    start_beat: float       # beat position within the section
    duration_beats: float
    velocity: int = 70

    def __repr__(self):
        name = CHROMATIC[self.midi_note % 12]
        return f"BassNote({name}{self.midi_note} beat={self.start_beat:.1f} dur={self.duration_beats:.1f})"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def bass_root(chord: VoicedChord, octave_bottom: int = BASS_OCTAVE_BOTTOM) -> int:
    """Return the root note of a chord dropped into bass register."""
    root_pc = chord.midi_notes[0] % 12  # pitch class of lowest voiced note
    # Find root pitch class from chord root name
    root_pc = CHROMATIC.index(chord.root_name)
    note = octave_bottom + root_pc
    # Nudge up an octave if too low
    while note < octave_bottom:
        note += 12
    while note > BASS_OCTAVE_TOP:
        note -= 12
    return note


def bass_fifth(chord: VoicedChord, octave_bottom: int = BASS_OCTAVE_BOTTOM) -> Optional[int]:
    """Return the fifth of the chord in bass register, or None if not present."""
    if len(chord.midi_notes) < 3:
        return None
    # Fifth is the third tone (index 2) in root-position chord
    fifth_pc = chord.midi_notes[2] % 12
    note = octave_bottom + fifth_pc
    while note < octave_bottom:
        note += 12
    while note > BASS_OCTAVE_TOP:
        note -= 12
    return note


def interpolate_steps(start: int, end: int, steps: int) -> list[int]:
    """
    Generate a stepwise chromatic walk from start to end in `steps` notes.
    Used for walking bass transitions.
    """
    if steps <= 1:
        return [start]
    direction = 1 if end >= start else -1
    total = abs(end - start)
    step_size = max(1, total // steps)
    notes = []
    current = start
    for i in range(steps):
        notes.append(current)
        if i < steps - 1:
            current = min(end, current + step_size * direction) if direction > 0 \
                      else max(end, current + step_size * direction)
    return notes


# ---------------------------------------------------------------------------
# Bass style generators
# ---------------------------------------------------------------------------

def style_root_only(
    chords: list[VoicedChord],
    bars_per_chord: float,
    beats_per_bar: int = 4,
    density: str = "sparse",
    velocity: int = 70,
) -> list[BassNote]:
    """One root note per chord, held for full duration."""
    notes = []
    beat = 0.0
    dur = bars_per_chord * beats_per_bar
    for chord in chords:
        root = bass_root(chord)
        notes.append(BassNote(root, beat, dur, velocity))
        beat += dur
    return notes


def style_root_fifth(
    chords: list[VoicedChord],
    bars_per_chord: float,
    beats_per_bar: int = 4,
    density: str = "medium",
    velocity: int = 70,
) -> list[BassNote]:
    """Alternates root and fifth within each chord's duration."""
    notes = []
    beat = 0.0
    total_beats = bars_per_chord * beats_per_bar
    half = total_beats / 2.0

    for chord in chords:
        root = bass_root(chord)
        fifth = bass_fifth(chord)
        notes.append(BassNote(root, beat, half, velocity))
        if fifth:
            notes.append(BassNote(fifth, beat + half, half, max(60, velocity - 8)))
        else:
            notes.append(BassNote(root, beat + half, half, max(60, velocity - 8)))
        beat += total_beats
    return notes


def style_walking(
    chords: list[VoicedChord],
    bars_per_chord: float,
    beats_per_bar: int = 4,
    density: str = "medium",
    velocity: int = 72,
) -> list[BassNote]:
    """
    Stepwise walk toward next chord's root.
    Last beat of each chord walks toward the next chord's root.
    """
    notes = []
    beat = 0.0
    total_beats = bars_per_chord * beats_per_bar
    beat_dur = 1.0  # quarter note steps

    for i, chord in enumerate(chords):
        root = bass_root(chord)
        next_root = bass_root(chords[(i + 1) % len(chords)])
        num_beats = int(total_beats)

        walk = interpolate_steps(root, next_root, num_beats)
        for j, note in enumerate(walk):
            vel = velocity if j == 0 else max(58, velocity - 6)
            notes.append(BassNote(note, beat + j * beat_dur, beat_dur, vel))
        beat += total_beats
    return notes


def style_pulse(
    chords: list[VoicedChord],
    bars_per_chord: float,
    beats_per_bar: int = 4,
    density: str = "full",
    velocity: int = 75,
    subdivision: float = 1.0,  # 1.0 = quarter notes, 0.5 = eighth notes
) -> list[BassNote]:
    """Repeated root notes on every subdivision. Rhythmic, driving."""
    notes = []
    beat = 0.0
    total_beats = bars_per_chord * beats_per_bar

    for chord in chords:
        root = bass_root(chord)
        t = 0.0
        while t < total_beats - 0.01:
            # Accent beat 1, soften others
            vel = velocity if t == 0.0 else max(55, velocity - 15)
            notes.append(BassNote(root, beat + t, subdivision, vel))
            t += subdivision
        beat += total_beats
    return notes


def style_pedal(
    chords: list[VoicedChord],
    bars_per_chord: float,
    beats_per_bar: int = 4,
    density: str = "sparse",
    velocity: int = 65,
    tonic_midi: Optional[int] = None,
) -> list[BassNote]:
    """
    Holds a single pedal tone (tonic) throughout regardless of harmony.
    Very ambient / Eno-ish. Tonic derived from first chord if not specified.
    """
    notes = []
    beat = 0.0
    total_beats = bars_per_chord * beats_per_bar

    if tonic_midi is None:
        tonic_midi = bass_root(chords[0])

    for chord in chords:
        notes.append(BassNote(tonic_midi, beat, total_beats, velocity))
        beat += total_beats
    return notes


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

BASS_STYLES = {
    "root_only":  style_root_only,
    "root_fifth": style_root_fifth,
    "walking":    style_walking,
    "pulse":      style_pulse,
    "pedal":      style_pedal,
}


def generate_bass(
    chords: list[VoicedChord],
    style: str = "root_fifth",
    bars_per_chord: float = 2.0,
    beats_per_bar: int = 4,
    density: str = "medium",
    velocity: int = 70,
    **kwargs,
) -> list[BassNote]:
    """
    Generate a bass line for a chord progression.

    Args:
        chords:         List of VoicedChord from harmony.resolve_progression()
        style:          Bass style name — root_only | root_fifth | walking | pulse | pedal
        bars_per_chord: How many bars each chord lasts
        beats_per_bar:  Time signature numerator (default 4)
        density:        "sparse" | "medium" | "full" — affects rhythm and activity
        velocity:       Base MIDI velocity
        **kwargs:       Style-specific options (e.g. subdivision for pulse, tonic_midi for pedal)

    Returns:
        List of BassNote objects
    """
    if style not in BASS_STYLES:
        raise ValueError(f"Unknown bass style: '{style}'. Choose from {list(BASS_STYLES.keys())}.")

    fn = BASS_STYLES[style]
    return fn(chords, bars_per_chord, beats_per_bar, density, velocity, **kwargs)


# ---------------------------------------------------------------------------
# Quick test / demo
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    from harmony import resolve_progression

    key = "D"
    mode = "dorian"
    progression = ["i", "VII", "iv", "v"]

    print("=== Intervals Engine — bass.py demo ===\n")
    chords = resolve_progression(progression, key, mode, density="medium")

    for style in BASS_STYLES:
        print(f"Style: {style}")
        notes = generate_bass(chords, style=style, bars_per_chord=2, density="medium")
        for n in notes:
            print(f"  {n}")
        print()
