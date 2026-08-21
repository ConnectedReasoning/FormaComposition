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
  motif       — the theme's own motif (intervals + rhythm), re-anchored to
                each chord's root and sequenced through the changing harmony.
                Requires a `motif` dict passed through from the caller;
                falls back to root_only with a warning if none is given.
                Bach-style: a fixed melodic-rhythmic cell repeated at a new
                pitch level under each new chord.
"""

import random
import warnings
from dataclasses import dataclass, field
from typing import Optional
from intervals.music.harmony import VoicedChord, CHROMATIC, MODES, key_to_midi_root
from intervals.music.scale_degrees import pitch_classes, degree_to_pitch, pitch_to_degree
from intervals.music.rhythm import remap_swing_ratio, swing_offset

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

def _pitch_class_to_bass_note(pc: int, octave_bottom: int, octave_top: int) -> int:
    """
    Place a pitch class into [octave_bottom, octave_top] register bounds,
    correctly, regardless of whether octave_bottom itself happens to be a C.

    Bug fix (2026-08): the previous formula in bass_root/bass_fifth/
    bass_third was `octave_bottom + pc`, which only produces the right
    absolute pitch when octave_bottom IS a C (pitch class 0) -- true for
    this module's own BASS_OCTAVE_BOTTOM=36 (C2) default, so the bug never
    surfaced until a caller passed a non-C-aligned box through
    section.bass_register (e.g. schemas.py's REGISTER_BOUNDS["bass"] =
    (39, 57), deliberately centered on C3 with an asymmetric 18-semitone
    span -- its floor, D#2, is NOT a C). With that box, every chord root
    landed up to 11 semitones off the intended pitch class -- silently:
    no error, no warning, no schema violation, just the wrong note. Caught
    only by a composer looking at the piano roll and asking why a C-chord
    bass note was D#.

    Fix: find the C at or below octave_bottom, add the pitch class to
    THAT, then fold into range with the same wrap-loop as before. For a
    C-aligned octave_bottom (base_c == octave_bottom) this is byte-
    identical to the old formula -- verified against test_bass.py's
    existing bass_root/bass_fifth/bass_third assertions, all of which use
    the C-aligned default and are unaffected.
    """
    base_c = (octave_bottom // 12) * 12
    note = base_c + pc
    while note < octave_bottom:
        note += 12
    while note > octave_top:
        note -= 12
    return note


def bass_root(chord: VoicedChord, octave_bottom: int = BASS_OCTAVE_BOTTOM,
              octave_top: int = BASS_OCTAVE_TOP) -> int:
    """Return the root note of a chord dropped into bass register."""
    root_pc = CHROMATIC.index(chord.root_name)
    return _pitch_class_to_bass_note(root_pc, octave_bottom, octave_top)


def bass_fifth(chord: VoicedChord, octave_bottom: int = BASS_OCTAVE_BOTTOM,
               octave_top: int = BASS_OCTAVE_TOP) -> Optional[int]:
    """Return the fifth of the chord in bass register, or None."""
    if len(chord.midi_notes) < 3:
        return None
    fifth_pc = chord.midi_notes[2] % 12
    return _pitch_class_to_bass_note(fifth_pc, octave_bottom, octave_top)


def bass_third(chord: VoicedChord, octave_bottom: int = BASS_OCTAVE_BOTTOM,
               octave_top: int = BASS_OCTAVE_TOP) -> Optional[int]:
    """Return the third of the chord in bass register."""
    if len(chord.midi_notes) < 2:
        return None
    third_pc = chord.midi_notes[1] % 12
    return _pitch_class_to_bass_note(third_pc, octave_bottom, octave_top)


def bass_chord_tones(chord: VoicedChord, octave_bottom: int = BASS_OCTAVE_BOTTOM,
                      octave_top: int = BASS_OCTAVE_TOP) -> list[int]:
    """
    All of the chord's actual voiced tones — root, third, fifth, seventh,
    any extension resolve_chord produced — placed in the bass register.

    Unlike bass_root()/bass_third()/bass_fifth() (which only ever cover a
    plain triad), this reflects the chord's real quality. Snap logic that
    only checks against {root, third, fifth} will treat a chord's 7th (or
    9th, or any other color tone) as a non-chord-tone and shove it onto
    the nearest triad tone instead — silently erasing the note that may be
    the whole harmonic point of the chord (e.g. a dominant 7th's flat-7).
    """
    pcs = sorted(set(n % 12 for n in chord.midi_notes))
    tones = [_pitch_class_to_bass_note(pc, octave_bottom, octave_top) for pc in pcs]
    return sorted(set(tones))


def get_bass_scale_tones(key: str, mode: str, octave_bottom: int = BASS_OCTAVE_BOTTOM,
                          octave_top: int = BASS_OCTAVE_TOP) -> list[int]:
    """All scale tones in the bass register, sorted."""
    intervals = MODES[mode.lower()]
    tones = []
    for octave in range(0, 7):
        root = key_to_midi_root(key, octave)
        for interval in intervals:
            n = root + interval
            if octave_bottom - 2 <= n <= octave_top + 2:
                tones.append(n)
    return sorted(set(tones))


def nearest_scale_tone(note: int, scale_tones: list[int]) -> int:
    """Return the closest scale tone to a given MIDI note."""
    if not scale_tones:
        return note
    return min(scale_tones, key=lambda s: abs(s - note))


def approach_note(target: int, scale_tones: list[int], octave_bottom: int = BASS_OCTAVE_BOTTOM,
                   octave_top: int = BASS_OCTAVE_TOP) -> int:
    """
    Chromatic approach note to the target — half step above or below.
    Prefers the approach that is NOT a scale tone (stronger pull).
    """
    above = target + 1
    below = target - 1
    above_in = above in scale_tones
    below_in = below in scale_tones
    if not below_in and below >= octave_bottom:
        return below
    if not above_in and above <= octave_top:
        return above
    return below if below >= octave_bottom else above


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
                    velocity=70, swing_ratio: float = 0.5, seed=None,
                    octave_bottom: int = BASS_OCTAVE_BOTTOM, octave_top: int = BASS_OCTAVE_TOP,
                    **kwargs):
    """
    One root note per chord, held for full duration.

    Velocity gets a small deterministic jitter per note rather than the
    exact same number every time — this was the flattest style in the
    engine (no rng at all previously), and it's exactly the style an
    ambient piece with few other moving parts tends to lean on, which
    makes its flatness the most exposed. The held-note character (one
    note, full chord duration) is unchanged; only the attack velocity
    varies, the way a real player's touch differs slightly note to note
    even on a simple part.
    """
    notes = []
    beat = 0.0
    rng = random.Random(seed) if seed is not None else random.Random()
    for i, chord in enumerate(chords):
        dur = bars_per_chord[i] * beats_per_bar
        vel = max(1, min(127, velocity + rng.randint(-4, 4)))
        notes.append(BassNote(bass_root(chord, octave_bottom, octave_top), beat, dur, vel))
        beat += dur
    return notes


# ---------------------------------------------------------------------------
# Style: root_fifth
# ---------------------------------------------------------------------------

def style_root_fifth(chords, bars_per_chord, beats_per_bar=4, density="medium",
                     velocity=70, swing_ratio: float = 0.5,
                     octave_bottom: int = BASS_OCTAVE_BOTTOM, octave_top: int = BASS_OCTAVE_TOP,
                     **kwargs):
    """Alternates root and fifth within each chord's duration."""
    notes = []
    beat = 0.0
    for i, chord in enumerate(chords):
        total = bars_per_chord[i] * beats_per_bar
        half = total / 2.0
        root = bass_root(chord, octave_bottom, octave_top)
        fifth = bass_fifth(chord, octave_bottom, octave_top) or root
        notes.append(BassNote(root, beat, half, velocity))
        notes.append(BassNote(fifth, beat + half, half, max(60, velocity - 8)))
        beat += total
    return notes


# ---------------------------------------------------------------------------
# Style: walking (rebuilt — scale-tone based)
# ---------------------------------------------------------------------------

def style_walking(chords, bars_per_chord, beats_per_bar=4, density="medium",
                  velocity=72, key="C", mode="ionian", seed=None,
                  swing_ratio: float = 0.5,
                  octave_bottom: int = BASS_OCTAVE_BOTTOM, octave_top: int = BASS_OCTAVE_TOP,
                  **kwargs):
    """
    Classic walking bass: quarter notes on scale tones.

    Beat 1: root (strong).
    Beat 3 (midpoint): fifth or third.
    Other beats: scale-wise passing tones moving between anchors.
    Last beat: chromatic approach note into next chord's root.
    """
    if seed is None:
        raise ValueError(f"Deterministic generation requires an explicit seed in {__name__}")
    rng = random.Random(seed)

    scale = get_bass_scale_tones(key, mode, octave_bottom, octave_top)
    notes = []
    beat = 0.0

    for i, chord in enumerate(chords):
        total = bars_per_chord[i] * beats_per_bar
        num_beats = max(1, int(total))

        root = bass_root(chord, octave_bottom, octave_top)
        fifth = bass_fifth(chord, octave_bottom, octave_top) or nearest_scale_tone(root + 7, scale)
        third = bass_third(chord, octave_bottom, octave_top) or nearest_scale_tone(root + 4, scale)
        next_root = bass_root(chords[(i + 1) % len(chords)], octave_bottom, octave_top)

        bar_notes = []
        for j in range(num_beats):
            is_last = (j == num_beats - 1) and (num_beats > 1)

            if j == 0:
                n = root
            elif is_last:
                n = approach_note(next_root, scale, octave_bottom, octave_top)
            elif j % beats_per_bar == (beats_per_bar // 2):
                n = rng.choice([fifth, fifth, third])
            else:
                prev = bar_notes[-1] if bar_notes else root
                nbrs = scale_neighbors(prev, scale)
                if nbrs:
                    target = fifth if j < num_beats // 2 else root
                    toward = [s for s in nbrs if abs(s - target) < abs(prev - target)]
                    n = rng.choice(toward) if toward else rng.choice(nbrs)
                else:
                    n = nearest_scale_tone(prev + rng.choice([-2, -1, 1, 2]), scale)

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
                 velocity=70, key="C", mode="ionian", seed=None,
                 swing_ratio: float = 0.5,
                 octave_bottom: int = BASS_OCTAVE_BOTTOM, octave_top: int = BASS_OCTAVE_TOP,
                 **kwargs):
    """
    A locked bass figure that repeats per chord.
    Picks one figure for the section and tiles it.
    Last beat at chord boundaries becomes an approach note.
    """
    if seed is None:
        raise ValueError(f"Deterministic generation requires an explicit seed in {__name__}")
    rng = random.Random(seed)

    scale = get_bass_scale_tones(key, mode, octave_bottom, octave_top)
    figure = rng.choice(STEADY_FIGURES)
    notes = []
    beat = 0.0

    for i, chord in enumerate(chords):
        total = bars_per_chord[i] * beats_per_bar
        root = bass_root(chord, octave_bottom, octave_top)
        fifth = bass_fifth(chord, octave_bottom, octave_top) or nearest_scale_tone(root + 7, scale)
        octave = root + 12 if root + 12 <= octave_top + 2 else root
        third = bass_third(chord, octave_bottom, octave_top) or nearest_scale_tone(root + 4, scale)
        next_root = bass_root(chords[(i + 1) % len(chords)], octave_bottom, octave_top)
        appr = approach_note(next_root, scale, octave_bottom, octave_top)

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
                  velocity=72, key="C", mode="ionian", seed=None,
                  swing_ratio: float = 0.5,
                  octave_bottom: int = BASS_OCTAVE_BOTTOM, octave_top: int = BASS_OCTAVE_TOP,
                  **kwargs):
    """
    Expressive bass line through scale tones with its own contour.

    Beat 1: root (anchored). Other beats: scale-wise movement with
    direction — rises toward fifth in first half, explores in middle,
    returns toward root area before approaching next chord. Occasional
    eighth-note pairs and leaps for rhythmic and melodic interest.
    """
    if seed is None:
        raise ValueError(f"Deterministic generation requires an explicit seed in {__name__}")
    rng = random.Random(seed)

    scale = get_bass_scale_tones(key, mode, octave_bottom, octave_top)
    notes = []
    beat = 0.0

    for i, chord in enumerate(chords):
        total = bars_per_chord[i] * beats_per_bar
        root = bass_root(chord, octave_bottom, octave_top)
        fifth = bass_fifth(chord, octave_bottom, octave_top) or nearest_scale_tone(root + 7, scale)
        third = bass_third(chord, octave_bottom, octave_top) or nearest_scale_tone(root + 4, scale)
        next_root = bass_root(chords[(i + 1) % len(chords)], octave_bottom, octave_top)
        appr = approach_note(next_root, scale, octave_bottom, octave_top)

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
                    target = rng.choice([third, fifth, root])
                else:
                    target = root

                nbrs = scale_neighbors(current, scale)
                if not nbrs:
                    nbrs = [nearest_scale_tone(current + rng.choice([-2, 2]), scale)]

                toward = [s for s in nbrs if abs(s - target) <= abs(current - target)]
                away = [s for s in nbrs if s not in toward]

                if toward and rng.random() < 0.70:
                    n = rng.choice(toward)
                elif away:
                    n = rng.choice(away)
                else:
                    n = rng.choice(nbrs)

                # Occasional leap for expressiveness
                if rng.random() < 0.15 and phrase_pos < 0.6:
                    n = rng.choice([fifth, third])

                # Occasional eighth note pair
                if rng.random() < 0.20 and remaining >= 1.0:
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
            onset = beat + t
            notes.append(BassNote(n, onset, actual_dur, vel))
            current = n
            t += actual_dur

        beat += total
    return notes


# ---------------------------------------------------------------------------
# Style: motif (Bach-style sequence — the theme's own cell drives the bass)
# ---------------------------------------------------------------------------

def style_motif(chords, bars_per_chord, beats_per_bar=4, density="medium",
                velocity=68, key="C", mode="ionian", seed=None,
                motif=None, swing_ratio: float = 0.5,
                octave_bottom: int = BASS_OCTAVE_BOTTOM, octave_top: int = BASS_OCTAVE_TOP,
                **kwargs):
    """
    Threads the theme's motif (intervals + rhythm) through the bass line,
    re-anchoring to each chord's root as the harmony changes — the classic
    "sequence" technique: a fixed melodic-rhythmic cell repeated at a new
    pitch level under each new chord, rather than a single continuous line
    ignoring the chord changes underneath it.

    Per chord:
      - The first note is always that chord's root (establishes the
        harmony clearly; the motif's own first interval, conventionally
        0, is consistent with this anyway).
      - The motif's remaining intervals/rhythm cycle from there, wrapping
        around if the chord's duration outlasts one full motif pass.
      - `intervals` are diatonic scale-degree steps (not semitones) —
        same contract as melody's motif_to_notes (see motif.py's
        Motif.intervals docstring). Each step moves by that many scale
        degrees, landing on a scale tone by construction, before the
        chord-tone-preference check below runs.
      - Each resulting pitch snaps to the nearest chord tone (root/third/
        fifth) if it's within a whole step of one, otherwise stays on
        the diatonic degree-walked scale tone — keeps the motif's shape
        recognizable without clashing against the harmony it's walking
        through. Degree tracking re-anchors to whichever pitch actually
        gets played (including a chord-tone override), so the next
        interval continues from the real position, not the pre-override
        one — the same principle motif_to_notes uses for continuity.
      - Each chord restarts the motif fresh (not threaded continuously
        across chord boundaries) — this is what keeps the harmony legible
        under a moving bass line; it does mean the motif does not carry
        rhythmic phase across a chord change.

    Requires `motif`: a dict with 'intervals' and 'rhythm' keys (pass the
    section's active_motif_def through). Falls back to root_only with a
    warning if no motif is provided — a "motif" bass line with no motif
    to play isn't meaningfully different from a bug.
    """
    if not motif or not motif.get("intervals") or not motif.get("rhythm"):
        warnings.warn(
            "bass_style 'motif' requires a motif dict with 'intervals' and "
            "'rhythm' (pass the section's active motif through) — none was "
            "provided, falling back to root_only.",
            stacklevel=2,
        )
        return style_root_only(chords, bars_per_chord, beats_per_bar, density,
                                velocity, key=key, mode=mode, seed=seed,
                                octave_bottom=octave_bottom, octave_top=octave_top, **kwargs)

    intervals  = motif["intervals"]
    rhythm     = motif["rhythm"]
    velocities = motif.get("velocities")
    rests      = motif.get("rests")
    cycle_len  = min(len(intervals), len(rhythm))

    scale = get_bass_scale_tones(key, mode, octave_bottom, octave_top)
    pcs = pitch_classes(scale) if scale else []
    notes = []
    beat = 0.0

    for i, chord in enumerate(chords):
        total = bars_per_chord[i] * beats_per_bar
        root  = bass_root(chord, octave_bottom, octave_top)
        chord_tones = bass_chord_tones(chord, octave_bottom, octave_top)

        current = root
        current_degree = pitch_to_degree(root, pcs) if pcs else None
        t = 0.0
        step = 0

        while t < total - 0.01:
            dur = rhythm[step % cycle_len]
            vel_scale = velocities[step % len(velocities)] if velocities else 1.0
            is_rest = bool(rests) and rests[step % cycle_len]

            if step == 0:
                candidate = root
            else:
                interval = intervals[step % cycle_len]
                if pcs:
                    current_degree = current_degree + interval
                    candidate = degree_to_pitch(current_degree, pcs)
                else:
                    # No scale available (shouldn't normally happen --
                    # get_bass_scale_tones always returns something for a
                    # real key/mode) -- fall back to the old literal
                    # semitone addition rather than crash.
                    candidate = current + interval
                while candidate < octave_bottom:
                    candidate += 12
                while candidate > octave_top:
                    candidate -= 12
                nearest_chord_tone = min(chord_tones, key=lambda c: abs(c - candidate))
                if abs(nearest_chord_tone - candidate) <= 2:
                    candidate = nearest_chord_tone
                if pcs:
                    # Re-anchor degree tracking to whatever actually gets
                    # played (a chord-tone override moves us off the raw
                    # degree-walked position) so the NEXT interval
                    # continues from the real note, not the discarded one.
                    current_degree = pitch_to_degree(candidate, pcs, prev_degree=current_degree)

            actual_dur = min(dur, total - t)
            if not is_rest:
                vel = int(velocity * vel_scale)
                onset = beat + t
                notes.append(BassNote(candidate, onset, actual_dur, vel))
            current = candidate
            t += actual_dur
            step += 1

        beat += total
    return notes


# ---------------------------------------------------------------------------
# Style: pulse
# ---------------------------------------------------------------------------

def style_pulse(chords, bars_per_chord, beats_per_bar=4, density="full",
                velocity=75, subdivision=1.0, offset=0.0, swing_ratio: float = 0.5,
                octave_bottom: int = BASS_OCTAVE_BOTTOM, octave_top: int = BASS_OCTAVE_TOP,
                **kwargs):
    """
    Repeated root notes on every subdivision, optionally phase-shifted by
    `offset` within each chord's span.

    offset=0.0 (default): unchanged from before this parameter existed --
    the pulse starts on the downbeat.

    offset=0.5, subdivision=1.0: the classic offbeat house/garage bass --
    quarter notes landing purely on the "and" of each beat, never
    coinciding with a four-on-floor kick on the downbeat. This is
    distinct from just using subdivision=0.5 with offset=0.0, which
    produces eighth notes on BOTH the beat and the offbeat.
    """
    notes = []
    beat = 0.0
    for i, chord in enumerate(chords):
        total = bars_per_chord[i] * beats_per_bar
        root = bass_root(chord, octave_bottom, octave_top)
        t = offset
        first_in_chord = True
        while t < total - 0.01:
            vel = velocity if first_in_chord else max(55, velocity - 15)
            notes.append(BassNote(root, beat + t, subdivision, vel))
            t += subdivision
            first_in_chord = False
        beat += total
    return notes


# ---------------------------------------------------------------------------
# Style: pedal
# ---------------------------------------------------------------------------

def style_pedal(chords, bars_per_chord, beats_per_bar=4, density="sparse",
                velocity=65, tonic_midi=None, swing_ratio: float = 0.5, seed=None,
                octave_bottom: int = BASS_OCTAVE_BOTTOM, octave_top: int = BASS_OCTAVE_TOP,
                **kwargs):
    """
    Holds a single pedal tone (tonic) throughout.

    Same fix as style_root_only: a small deterministic velocity jitter per
    re-articulation instead of the exact same number every time. This was
    the actual style behind the "bass mean velocity 70.0, one unique value"
    finding — long_amen and v9 both use bass_style='pedal', not 'root_only'
    (style_root_only alone wasn't the whole fix).
    """
    notes = []
    beat = 0.0
    if tonic_midi is None:
        tonic_midi = bass_root(chords[0], octave_bottom, octave_top)
    rng = random.Random(seed) if seed is not None else random.Random()
    for i, chord in enumerate(chords):
        total = bars_per_chord[i] * beats_per_bar
        vel = max(1, min(127, velocity + rng.randint(-4, 4)))
        notes.append(BassNote(tonic_midi, beat, total, vel))
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
    "motif":      style_motif,
}


# Styles whose lines depend on stepwise continuity into the next chord root.
# Dropping notes at random breaks the line rather than adding breath, so
# bass_rest_probability is refused (loudly) for these — see generate_bass.
_CONTINUOUS_BASS_STYLES = {"walking", "melodic"}


def _apply_bass_rests(
    notes: list[BassNote],
    rest_probability: float,
    seed: Optional[int],
) -> list[BassNote]:
    """
    Drop each bass note independently with probability rest_probability,
    seeded for determinism. A bass rest is simply an omitted note (BassNote
    has no rest flag). The caller owns the per-style guard; this helper just
    thins whatever list it's given.

    The RNG is decorrelated from the style functions' own seed stream (which
    already consumed `seed` for pitch/contour choices) so the rest pattern is
    independent of the note-selection pattern rather than locked to it.
    """
    if rest_probability <= 0.0 or not notes:
        return notes
    rng = random.Random((seed or 0) ^ 0x8A5)
    return [n for n in notes if rng.random() >= rest_probability]


def _apply_swing_to_bass(notes: list[BassNote], swing_ratio: float) -> list[BassNote]:
    """
    Apply swing displacement to a finished bass note list, uniformly,
    regardless of which style produced it.

    This used to be each style's own responsibility -- style_melodic and
    style_motif applied it inline, per-note, during construction; every
    other style silently ignored swing_ratio entirely. That meant swing
    only ever worked for two of the eight styles, and a new style added
    later would silently be swing-deaf unless someone remembered to wire
    it in by hand. Centralizing it here as a single post-pass (mirroring
    rhythm.py's apply_swing() for melody, and percussion.py's
    _apply_swing_to_drums()) means every style gets identical, correct
    swing behavior automatically, including styles added in the future.

    Only offbeat-eighth onsets (beat % 1.0 == 0.5, within swing_offset()'s
    tolerance) are ever displaced -- an onset on a whole beat is returned
    completely unchanged. Styles whose figures never place a note off the
    beat (root_only, root_fifth, walking, steady, pedal, and pulse at its
    default quarter-note subdivision) are therefore correctly unaffected
    by this pass, not because it skips them, but because there's nothing
    on their grid for swing_offset() to act on.
    """
    if swing_ratio == 0.5 or not notes:  # straight -- every offset would be 0 anyway
        return notes
    swung = []
    for n in notes:
        off = swing_offset(n.start_beat, swing_ratio)
        if off:
            swung.append(BassNote(
                n.midi_note,
                n.start_beat + off,
                max(0.1, n.duration_beats - off),
                n.velocity,
            ))
        else:
            swung.append(n)
    return swung


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
    motif: Optional[dict] = None,
    swing: float = 0.0,
    rhythm_events_override: Optional[list] = None,
    rest_probability: float = 0.0,
    bass_subdivision: Optional[float] = None,
    bass_offset: Optional[float] = None,
    octave_bottom: int = BASS_OCTAVE_BOTTOM,
    octave_top: int = BASS_OCTAVE_TOP,
    **kwargs,
) -> list[BassNote]:
    """
    Generate a bass line for a chord progression.

    Args:
        chords:                 List of VoicedChord
        style:                  root_only | root_fifth | walking | steady | melodic | pulse | pedal | motif
        bars_per_chord:         Float (uniform) or list[float] (per-chord)
        beats_per_bar:          Time signature numerator (default 4)
        density:                "sparse" | "medium" | "full"
        velocity:               Base MIDI velocity
        key:                    Key center (for scale-aware styles)
        mode:                   Mode name (for scale-aware styles)
        seed:                   Random seed
        octave_bottom/top:      MIDI register window for every bass tone this
                                 call produces. Defaults to the module constants
                                 (36-48, unchanged behavior). Threaded through
                                 every style function and its scale/chord-tone
                                 helpers -- this is the one place that actually
                                 decides where the bass sits.
        motif:                  Optional motif dict ({'intervals', 'rhythm', ...}).
                                 Only consumed by style="motif" — ignored by every
                                 other style. Pass the section's active_motif_def.
        rhythm_events_override: Optional list of RhythmEvent from _motif_rhythm_to_events.
                                When provided, bypasses style dispatch entirely and
                                generates root notes at the specified beat positions.
                                The style parameter is ignored — timing comes from the
                                motif rhythm, pitches are chord roots in bass register.
                                This is the "anchor" articulation path: the bass follows
                                the motif's primary beats, one root per onset.
        bass_subdivision:       Only consumed by style="pulse" (via style_pulse's
                                 `subdivision` param). None inherits style_pulse's own
                                 default (1.0, quarter notes). Ignored, with a warning,
                                 for every other style — including when
                                 rhythm_events_override is active, which bypasses style
                                 dispatch (and therefore style_pulse) entirely regardless
                                 of what `style` is set to.
        bass_offset:            Only consumed by style="pulse" (via style_pulse's
                                 `offset` param). None = 0.0 (on the downbeat). Same
                                 ignored-with-warning behavior as bass_subdivision above.
                                 bass_subdivision=1.0, bass_offset=0.5 is the classic
                                 offbeat house/garage bass.
    """
    if isinstance(bars_per_chord, (int, float)):
        bars_per_chord = [float(bars_per_chord)] * len(chords)

    # Neither knob has any effect once the motif-rhythm-override path fires
    # below (it bypasses style dispatch, and therefore style_pulse, outright)
    # or under any style other than "pulse". Warn rather than silently drop
    # them — same discipline as the rest_probability guard further down.
    _pulse_only_set = bass_subdivision is not None or bass_offset is not None
    _override_active = (
        rhythm_events_override is not None and rhythm_events_override and style != "motif"
    )
    if _pulse_only_set and (style != "pulse" or _override_active):
        reason = (
            "rhythm_events_override is active (bypasses style dispatch entirely)"
            if _override_active else
            f"style='{style}' (only 'pulse' consumes them)"
        )
        warnings.warn(
            f"bass_subdivision/bass_offset set but ignored: {reason}.",
            stacklevel=2,
        )

    # ── Motif rhythm override path ───────────────────────────────────
    # When the motif provides timing, bypass the style functions entirely.
    # Walk the override events, determine which chord is sounding at each
    # beat, and emit a root BassNote at that position.
    #
    # Exception: style="motif" is skipped from this bypass on purpose.
    # rhythm_events_override gets populated whenever section.rhythm ==
    # "motif" (the generic melody/bass rhythm cascade), independent of
    # bass_style. If both are set — rhythm: "motif" AND bass_style:
    # "motif" — the more specific, explicit instruction (bass_style)
    # should win, not lose silently to the generic anchor-root behavior.
    if _override_active:
        # Build a lookup: beat → chord index
        chord_start_beats = []
        beat = 0.0
        for bars in bars_per_chord:
            chord_start_beats.append(beat)
            beat += bars * beats_per_bar

        def _chord_at_beat(b: float) -> VoicedChord:
            idx = 0
            for i, start in enumerate(chord_start_beats):
                if b >= start:
                    idx = i
            return chords[idx]

        notes = []
        for k, ev in enumerate(rhythm_events_override):
            if ev.is_rest:
                continue
            chord = _chord_at_beat(ev.start_beat)
            root  = bass_root(chord, octave_bottom, octave_top)
            vel   = int(velocity * ev.velocity_scale)
            # Sustain to the next event's onset (or end of section),
            # not just for the motif note's duration. Bass should hold,
            # not leave gaps between motif anchor hits.
            if k + 1 < len(rhythm_events_override):
                dur = rhythm_events_override[k + 1].start_beat - ev.start_beat
            else:
                # Last note: sustain to end of section
                total_section = sum(b * beats_per_bar for b in bars_per_chord)
                dur = total_section - ev.start_beat
            dur = max(0.25, dur)
            notes.append(BassNote(root, ev.start_beat, dur, vel))
        # Anchor-root override path: roots are independent (no stepwise
        # continuity requirement), so rests are always safe here regardless
        # of the nominal style.
        return _apply_bass_rests(notes, rest_probability, seed)

    # ── Style dispatch (existing behavior) ──────────────────────────
    if style not in BASS_STYLES:
        raise ValueError(f"Unknown bass style: '{style}'. Choose from {list(BASS_STYLES.keys())}.")

    fn = BASS_STYLES[style]
    # `swing` is the public 0.0-1.0 section field; the placement rule
    # (rhythm.swing_offset) works on the internal 0.5-straight scale, so convert
    # once here — the same conversion melody does before calling apply_swing.
    swing_ratio = remap_swing_ratio(swing) if swing and swing > 0 else 0.5

    # bass_subdivision/bass_offset are explicit named params (not folded
    # into **kwargs) specifically so the guard above can warn on misuse
    # instead of letting them silently vanish into style functions that
    # don't read them. Forward only what's actually set, so style_pulse's
    # own defaults (subdivision=1.0, offset=0.0) still apply when unset.
    _pulse_kwargs = {}
    if style == "pulse":
        if bass_subdivision is not None:
            _pulse_kwargs["subdivision"] = bass_subdivision
        if bass_offset is not None:
            _pulse_kwargs["offset"] = bass_offset

    notes = fn(chords, bars_per_chord, beats_per_bar, density, velocity,
               key=key, mode=mode, seed=seed, motif=motif,
               swing_ratio=swing_ratio, octave_bottom=octave_bottom, octave_top=octave_top,
               **_pulse_kwargs, **kwargs)

    # Swing is applied uniformly here, once, regardless of style — see
    # _apply_swing_to_bass()'s docstring. Every style's output passes
    # through this; styles whose onsets never land on an offbeat eighth
    # (root_only, root_fifth, walking, steady, pedal, pulse at its default
    # subdivision) come back byte-identical, not because they're skipped.
    notes = _apply_swing_to_bass(notes, swing_ratio)

    # Style-path rest guard: walking/melodic lines rely on stepwise motion
    # into the next chord root, so random note drops break the line rather
    # than add breath. Refuse the knob loudly instead of silently mangling it.
    if rest_probability > 0.0 and style in _CONTINUOUS_BASS_STYLES:
        warnings.warn(
            f"bass_rest_probability={rest_probability} ignored for "
            f"style='{style}': walking/melodic lines depend on stepwise "
            f"continuity and would break if thinned. Use root_only, steady, "
            f"pedal, pulse, or root_fifth for probabilistic bass rests.",
            stacklevel=2,
        )
        return notes
    return _apply_bass_rests(notes, rest_probability, seed)
