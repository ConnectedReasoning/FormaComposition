"""
bass.py — Intervals Engine
Generates bass lines from a resolved chord progression.

Bass styles:
  root_only   — whole note root, one per chord. Minimal, drone-like.
  root_fifth  — alternates root and fifth. Classic new age / ambient.
  walking     — scale-wise quarter notes: root on 1, chord tones on strong
                beats, approach note into the next chord. Classic jazz/pop.
  steady      — a short locked figure that repeats per chord. The bass IS
                the groove. Cliff Williams, Adam Clayton.
  melodic     — expressive line through scale tones with contour and leaps.
                The bass is a second melody. Sting, Geddy Lee.
  pulse       — repeated root notes on the beat. Rhythmic, driving.
  pedal       — holds a single pedal tone (tonic) regardless of chord. Eno-ish.
"""

import random
from dataclasses import dataclass, field
from typing import Optional
from intervals.music.harmony import VoicedChord, CHROMATIC, MODES, key_to_midi_root

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

BASS_OCTAVE_BOTTOM = 36   # C2
BASS_OCTAVE_TOP    = 48   # C3

# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------

@dataclass
class BassNote:
    """A single bass note with timing."""
    midi_note: int
    start_beat: float
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
    root_pc = CHROMATIC.index(chord.root_name)
    note = octave_bottom + root_pc
    while note < octave_bottom:
        note += 12
    while note > BASS_OCTAVE_TOP:
        note -= 12
    return note


def bass_fifth(chord: VoicedChord, octave_bottom: int = BASS_OCTAVE_BOTTOM) -> Optional[int]:
    """Return the fifth of the chord in bass register, or None."""
    if len(chord.midi_notes) < 3:
        return None
    fifth_pc = chord.midi_notes[2] % 12
    note = octave_bottom + fifth_pc
    while note < octave_bottom:
        note += 12
    while note > BASS_OCTAVE_TOP:
        note -= 12
    return note


def bass_third(chord: VoicedChord, octave_bottom: int = BASS_OCTAVE_BOTTOM) -> Optional[int]:
    """Return the third of the chord in bass register."""
    if len(chord.midi_notes) < 2:
        return None
    third_pc = chord.midi_notes[1] % 12
    note = octave_bottom + third_pc
    while note < octave_bottom:
        note += 12
    while note > BASS_OCTAVE_TOP:
        note -= 12
    return note


def get_bass_scale_tones(key: str, mode: str) -> list[int]:
    """All scale tones in the bass register, sorted."""
    intervals = MODES[mode.lower()]
    tones = []
    for octave in range(1, 5):
        root = key_to_midi_root(key, octave)
        for interval in intervals:
            n = root + interval
            if BASS_OCTAVE_BOTTOM - 2 <= n <= BASS_OCTAVE_TOP + 2:
                tones.append(n)
    return sorted(set(tones))


def nearest_scale_tone(note: int, scale_tones: list[int]) -> int:
    """Return the closest scale tone to a given MIDI note."""
    if not scale_tones:
        return note
    return min(scale_tones, key=lambda s: abs(s - note))


def approach_note(target: int, scale_tones: list[int]) -> int:
    """
    Chromatic approach note to the target — half step above or below.
    Prefers the approach that is NOT a scale tone (stronger pull).
    """
    above = target + 1
    below = target - 1
    above_in = above in scale_tones
    below_in = below in scale_tones
    if not below_in and below >= BASS_OCTAVE_BOTTOM:
        return below
    if not above_in and above <= BASS_OCTAVE_TOP:
        return above
    return below if below >= BASS_OCTAVE_BOTTOM else above


def scale_neighbors(note: int, scale_tones: list[int], direction: int = 0) -> list[int]:
    """Scale tones adjacent to note (within 4 semitones)."""
    neighbors = []
    for s in scale_tones:
        dist = s - note
        if dist == 0:
            continue
        if abs(dist) > 4:
            continue
        if direction > 0 and dist < 0:
            continue
        if direction < 0 and dist > 0:
            continue
        neighbors.append(s)
    return sorted(neighbors, key=lambda s: abs(s - note))


# ---------------------------------------------------------------------------
# Style: root_only
# ---------------------------------------------------------------------------

def style_root_only(chords, bars_per_chord, beats_per_bar=4, density="sparse",
                    velocity=70, **kwargs):
    """One root note per chord, held for full duration."""
    notes = []
    beat = 0.0
    for i, chord in enumerate(chords):
        dur = bars_per_chord[i] * beats_per_bar
        notes.append(BassNote(bass_root(chord), beat, dur, velocity))
        beat += dur
    return notes


# ---------------------------------------------------------------------------
# Style: root_fifth
# ---------------------------------------------------------------------------

def style_root_fifth(chords, bars_per_chord, beats_per_bar=4, density="medium",
                     velocity=70, **kwargs):
    """Alternates root and fifth within each chord's duration."""
    notes = []
    beat = 0.0
    for i, chord in enumerate(chords):
        total = bars_per_chord[i] * beats_per_bar
        half = total / 2.0
        root = bass_root(chord)
        fifth = bass_fifth(chord) or root
        notes.append(BassNote(root, beat, half, velocity))
        notes.append(BassNote(fifth, beat + half, half, max(60, velocity - 8)))
        beat += total
    return notes


# ---------------------------------------------------------------------------
# Style: walking (rebuilt — scale-tone based)
# ---------------------------------------------------------------------------

def style_walking(chords, bars_per_chord, beats_per_bar=4, density="medium",
                  velocity=72, key="C", mode="ionian", seed=None, **kwargs):
    """
    Classic walking bass: quarter notes on scale tones.

    Beat 1: root (strong).
    Beat 3 (midpoint): fifth or third.
    Other beats: scale-wise passing tones moving between anchors.
    Last beat: chromatic approach note into next chord's root.
    """
    if seed is not None:
        random.seed(seed)

    scale = get_bass_scale_tones(key, mode)
    notes = []
    beat = 0.0

    for i, chord in enumerate(chords):
        total = bars_per_chord[i] * beats_per_bar
        num_beats = max(1, int(total))

        root = bass_root(chord)
        fifth = bass_fifth(chord) or nearest_scale_tone(root + 7, scale)
        third = bass_third(chord) or nearest_scale_tone(root + 4, scale)
        next_root = bass_root(chords[(i + 1) % len(chords)])

        bar_notes = []
        for j in range(num_beats):
            is_last = (j == num_beats - 1) and (num_beats > 1)

            if j == 0:
                n = root
            elif is_last:
                n = approach_note(next_root, scale)
            elif j % beats_per_bar == (beats_per_bar // 2):
                n = random.choice([fifth, fifth, third])
            else:
                prev = bar_notes[-1] if bar_notes else root
                nbrs = scale_neighbors(prev, scale)
                if nbrs:
                    target = fifth if j < num_beats // 2 else root
                    toward = [s for s in nbrs if abs(s - target) < abs(prev - target)]
                    n = random.choice(toward) if toward else random.choice(nbrs)
                else:
                    n = nearest_scale_tone(prev + random.choice([-2, -1, 1, 2]), scale)

            vel = velocity if j % beats_per_bar == 0 else max(58, velocity - 6)
            bar_notes.append(n)
            notes.append(BassNote(n, beat + j * 1.0, 1.0, vel))

        beat += total
    return notes


# ---------------------------------------------------------------------------
# Style: steady (locked figure — Clayton, Williams)
# ---------------------------------------------------------------------------

STEADY_FIGURES = [
    # Root-root-fifth-root: the AC/DC
    [(0.0, "root", 1.0, 1.0), (1.0, "root", 1.0, 0.85),
     (2.0, "fifth", 1.0, 0.90), (3.0, "root", 1.0, 0.80)],
    # Root-fifth-octave-fifth: the U2
    [(0.0, "root", 1.0, 1.0), (1.0, "fifth", 1.0, 0.85),
     (2.0, "octave", 1.0, 0.90), (3.0, "fifth", 1.0, 0.80)],
    # Root-rest-fifth-root: breathing room
    [(0.0, "root", 1.5, 1.0), (2.0, "fifth", 1.0, 0.85),
     (3.0, "root", 1.0, 0.80)],
    # Root-root-root-approach: locked with lead-in
    [(0.0, "root", 1.0, 1.0), (1.0, "root", 1.0, 0.75),
     (2.0, "root", 1.0, 0.80), (3.0, "approach", 1.0, 0.90)],
]


def style_steady(chords, bars_per_chord, beats_per_bar=4, density="medium",
                 velocity=70, key="C", mode="ionian", seed=None, **kwargs):
    """
    A locked bass figure that repeats per chord.
    Picks one figure for the section and tiles it.
    Last beat at chord boundaries becomes an approach note.
    """
    if seed is not None:
        random.seed(seed)

    scale = get_bass_scale_tones(key, mode)
    figure = random.choice(STEADY_FIGURES)
    notes = []
    beat = 0.0

    for i, chord in enumerate(chords):
        total = bars_per_chord[i] * beats_per_bar
        root = bass_root(chord)
        fifth = bass_fifth(chord) or nearest_scale_tone(root + 7, scale)
        octave = root + 12 if root + 12 <= BASS_OCTAVE_TOP + 2 else root
        third = bass_third(chord) or nearest_scale_tone(root + 4, scale)
        next_root = bass_root(chords[(i + 1) % len(chords)])
        appr = approach_note(next_root, scale)

        tone_map = {"root": root, "fifth": fifth, "third": third,
                    "octave": octave, "approach": appr}

        bar_offset = 0.0
        while bar_offset < total - 0.01:
            for slot_beat, func, dur, vel_scale in figure:
                abs_beat = bar_offset + slot_beat
                if abs_beat >= total - 0.01:
                    break
                is_last = (abs_beat + dur >= total - 0.01) and (i < len(chords) - 1)
                n = appr if is_last and func != "approach" else tone_map.get(func, root)
                actual_dur = min(dur, total - abs_beat)
                notes.append(BassNote(n, beat + abs_beat, actual_dur, int(velocity * vel_scale)))
            bar_offset += beats_per_bar

        beat += total
    return notes


# ---------------------------------------------------------------------------
# Style: melodic (expressive — Sting, Geddy Lee)
# ---------------------------------------------------------------------------

def style_melodic(chords, bars_per_chord, beats_per_bar=4, density="medium",
                  velocity=72, key="C", mode="ionian", seed=None, **kwargs):
    """
    Expressive bass line through scale tones with its own contour.

    Beat 1: root (anchored). Other beats: scale-wise movement with
    direction — rises toward fifth in first half, explores in middle,
    returns toward root area before approaching next chord. Occasional
    eighth-note pairs and leaps for rhythmic and melodic interest.
    """
    if seed is not None:
        random.seed(seed)

    scale = get_bass_scale_tones(key, mode)
    notes = []
    beat = 0.0

    for i, chord in enumerate(chords):
        total = bars_per_chord[i] * beats_per_bar
        root = bass_root(chord)
        fifth = bass_fifth(chord) or nearest_scale_tone(root + 7, scale)
        third = bass_third(chord) or nearest_scale_tone(root + 4, scale)
        next_root = bass_root(chords[(i + 1) % len(chords)])
        appr = approach_note(next_root, scale)

        current = root
        t = 0.0

        while t < total - 0.01:
            remaining = total - t
            is_first = (t < 0.01)
            is_last_region = (remaining <= 1.5)
            phrase_pos = t / total

            if is_first:
                n = root
                dur = 1.0
            elif is_last_region and i < len(chords) - 1:
                n = appr
                dur = min(1.0, remaining)
            else:
                # Direction based on phrase position
                if phrase_pos < 0.4:
                    target = fifth
                elif phrase_pos < 0.7:
                    target = random.choice([third, fifth, root])
                else:
                    target = root

                nbrs = scale_neighbors(current, scale)
                if not nbrs:
                    nbrs = [nearest_scale_tone(current + random.choice([-2, 2]), scale)]

                toward = [s for s in nbrs if abs(s - target) <= abs(current - target)]
                away = [s for s in nbrs if s not in toward]

                if toward and random.random() < 0.70:
                    n = random.choice(toward)
                elif away:
                    n = random.choice(away)
                else:
                    n = random.choice(nbrs)

                # Occasional leap for expressiveness
                if random.random() < 0.15 and phrase_pos < 0.6:
                    n = random.choice([fifth, third])

                # Occasional eighth note pair
                if random.random() < 0.20 and remaining >= 1.0:
                    dur = 0.5
                else:
                    dur = 1.0

            # Velocity shaping
            if is_first:
                vel = velocity
            elif dur < 1.0:
                vel = max(50, velocity - 15)
            else:
                vel = velocity - 4 if (t % beats_per_bar) < 0.01 else max(55, velocity - 10)

            actual_dur = min(dur, remaining)
            notes.append(BassNote(n, beat + t, actual_dur, vel))
            current = n
            t += actual_dur

        beat += total
    return notes


# ---------------------------------------------------------------------------
# Style: pulse
# ---------------------------------------------------------------------------

def style_pulse(chords, bars_per_chord, beats_per_bar=4, density="full",
                velocity=75, subdivision=1.0, **kwargs):
    """Repeated root notes on every subdivision."""
    notes = []
    beat = 0.0
    for i, chord in enumerate(chords):
        total = bars_per_chord[i] * beats_per_bar
        root = bass_root(chord)
        t = 0.0
        while t < total - 0.01:
            vel = velocity if t == 0.0 else max(55, velocity - 15)
            notes.append(BassNote(root, beat + t, subdivision, vel))
            t += subdivision
        beat += total
    return notes


# ---------------------------------------------------------------------------
# Style: pedal
# ---------------------------------------------------------------------------

def style_pedal(chords, bars_per_chord, beats_per_bar=4, density="sparse",
                velocity=65, tonic_midi=None, **kwargs):
    """Holds a single pedal tone (tonic) throughout."""
    notes = []
    beat = 0.0
    if tonic_midi is None:
        tonic_midi = bass_root(chords[0])
    for i, chord in enumerate(chords):
        total = bars_per_chord[i] * beats_per_bar
        notes.append(BassNote(tonic_midi, beat, total, velocity))
        beat += total
    return notes


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

BASS_STYLES = {
    "root_only":  style_root_only,
    "root_fifth": style_root_fifth,
    "walking":    style_walking,
    "steady":     style_steady,
    "melodic":    style_melodic,
    "pulse":      style_pulse,
    "pedal":      style_pedal,
}


def generate_bass(
    chords: list[VoicedChord],
    style: str = "root_fifth",
    bars_per_chord=2.0,
    beats_per_bar: int = 4,
    density: str = "medium",
    velocity: int = 70,
    key: str = "C",
    mode: str = "ionian",
    seed: Optional[int] = None,
    **kwargs,
) -> list[BassNote]:
    """
    Generate a bass line for a chord progression.

    Args:
        chords:         List of VoicedChord
        style:          root_only | root_fifth | walking | steady | melodic | pulse | pedal
        bars_per_chord: Float (uniform) or list[float] (per-chord)
        beats_per_bar:  Time signature numerator (default 4)
        density:        "sparse" | "medium" | "full"
        velocity:       Base MIDI velocity
        key:            Key center (for scale-aware styles)
        mode:           Mode name (for scale-aware styles)
        seed:           Random seed
    """
    if style not in BASS_STYLES:
        raise ValueError(f"Unknown bass style: '{style}'. Choose from {list(BASS_STYLES.keys())}.")

    if isinstance(bars_per_chord, (int, float)):
        bars_per_chord = [float(bars_per_chord)] * len(chords)

    fn = BASS_STYLES[style]
    return fn(chords, bars_per_chord, beats_per_bar, density, velocity,
              key=key, mode=mode, seed=seed, **kwargs)
