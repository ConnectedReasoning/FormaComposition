"""
melody.py — Intervals Engine
Generates melodic lines over a chord progression using a motif + behavior system.

Melody behaviors:
  generative  — freely generates from scale + chord tones, loosely motif-informed
  lyrical     — longer phrases, stepwise motion, stays close to chord tones
  sparse      — few notes, wide intervals, lots of space
  develop     — applies motif transforms (inversion, retrograde, augmentation)

Motif is defined in theme.json as:
  {
    "intervals": [2, -1, 3],        # semitone steps between notes
    "rhythm":    [1.0, 0.5, 0.5],   # note durations in beats
    "transform_pool": ["inversion", "retrograde", "augmentation"]
  }
"""

import random
import math
from dataclasses import dataclass
from typing import Optional
from intervals.music.harmony import VoicedChord, CHROMATIC, MODES, key_to_midi_root
from intervals.music.rhythm import RhythmEvent, get_pattern, apply_swing, remap_swing_ratio

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

MELODY_OCTAVE_BOTTOM = 60   # C4
MELODY_OCTAVE_TOP    = 84   # C6

# Behavior → how aggressively to follow chord tones vs scale tones
# (chord_tone_weight, scale_tone_weight, chromatic_weight)
BEHAVIOR_WEIGHTS = {
    "generative": (0.50, 0.45, 0.05),
    "lyrical":    (0.65, 0.33, 0.02),
    "sparse":     (0.55, 0.40, 0.05),
    "develop":    (0.45, 0.50, 0.05),
}

# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------

@dataclass
class MelodyNote:
    """A single melody note or rest."""
    midi_note: Optional[int]    # None = rest
    start_beat: float
    duration_beats: float
    velocity: int = 72
    is_rest: bool = False

    def __repr__(self):
        if self.is_rest:
            return f"MelodyNote(REST beat={self.start_beat:.2f} dur={self.duration_beats:.2f})"
        name = CHROMATIC[self.midi_note % 12] if self.midi_note else "?"
        return f"MelodyNote({name}{self.midi_note} beat={self.start_beat:.2f} dur={self.duration_beats:.2f} vel={self.velocity})"


# ---------------------------------------------------------------------------
# Scale + chord tone helpers
# ---------------------------------------------------------------------------

def get_scale_tones(key: str, mode: str, octave_bottom: int, octave_top: int) -> list[int]:
    """All MIDI notes in the scale within the melody register."""
    mode = mode.lower()
    intervals = MODES[mode]
    root = key_to_midi_root(key, octave=2)  # start low and walk up
    tones = []
    note = root
    while note <= octave_top + 12:
        for interval in intervals:
            n = note + interval
            if octave_bottom <= n <= octave_top:
                tones.append(n)
        note += 12
    return sorted(set(tones))


def get_chord_tones_in_register(chord: VoicedChord, octave_bottom: int, octave_top: int) -> list[int]:
    """Expand chord tones across the melody register."""
    tones = []
    for midi in chord.midi_notes:
        pc = midi % 12
        # Walk all octaves
        n = pc + 48  # start at C3
        while n <= octave_top + 12:
            if octave_bottom <= n <= octave_top:
                tones.append(n)
            n += 12
    return sorted(set(tones))


def nearest_scale_tone(note: int, scale_tones: list[int]) -> int:
    """Return the closest scale tone to a given MIDI note."""
    return min(scale_tones, key=lambda s: abs(s - note))


# ---------------------------------------------------------------------------
# Motif engine
# ---------------------------------------------------------------------------

def apply_transform(intervals: list[int], transform: str, rng=None) -> list[int]:
    """
    Apply a Bach-style transform to an interval sequence.

    Transforms:
      inversion    — negate all intervals
      retrograde   — reverse the sequence
      augmentation — double all durations (applied to rhythm separately)
      diminution   — halve all durations (applied to rhythm separately)
      transpose    — shift all intervals by +2 (adds variety)
      shuffle      — randomly reorder intervals
    """
    if rng is None:
        import random as _r
        rng = _r.Random()
    if transform == "inversion":
        return [-i for i in intervals]
    elif transform == "retrograde":
        return list(reversed(intervals))
    elif transform == "transpose":
        return [i + 2 for i in intervals]
    elif transform == "shuffle":
        shuffled = list(intervals)
        rng.shuffle(shuffled)
        return shuffled
    else:
        # augmentation / diminution affect rhythm, not intervals
        return list(intervals)


def apply_rhythm_transform(rhythm: list[float], transform: str) -> list[float]:
    """Apply time-based transforms to a rhythm sequence."""
    if transform == "augmentation":
        return [r * 2.0 for r in rhythm]
    elif transform == "diminution":
        return [max(0.25, r * 0.5) for r in rhythm]
    elif transform == "retrograde":
        return list(reversed(rhythm))
    else:
        return list(rhythm)


def apply_rests_transform(rests: Optional[list[bool]], transform: str) -> Optional[list[bool]]:
    """
    Keep a rests array aligned with whatever reordering apply_rhythm_transform
    performs on the paired rhythm array. Only "retrograde" reorders here (this
    local shuffle implementation, unlike motif.py's canonical one, doesn't
    reorder rhythm either, so rests correctly stays untouched for shuffle too).
    """
    if rests is None:
        return None
    if transform == "retrograde":
        return list(reversed(rests))
    return list(rests)


def motif_to_notes(
    start_midi: int,
    intervals: list[int],
    rhythm: list[float],
    scale_tones: list[int],
    chord_tones: list[int],
    octave_bottom: int,
    octave_top: int,
    snap_to_scale: bool = True,
    rests: Optional[list[bool]] = None,
) -> list[tuple[int, float]]:
    """
    Convert a motif (interval sequence + rhythm) to (midi_note, duration) pairs
    starting from start_midi.

    rests: optional, same length as rhythm. True = this slot is silent and is
    omitted from the returned list entirely (not included as a placeholder).
    The interval is still applied to the running pitch position underneath a
    rest, so the melodic shape's trajectory continues correctly once sounding
    notes resume — a rest pauses the line, it doesn't freeze its contour.

    Returns list of (midi_note, duration_beats), one entry per SOUNDING slot.
    """
    notes = []
    current = start_midi

    # Pair up intervals and rhythm (zip to shorter)
    pairs = list(zip(intervals, rhythm))

    for idx, (interval, dur) in enumerate(pairs):
        current = current + interval
        # Clamp to register
        while current < octave_bottom:
            current += 12
        while current > octave_top:
            current -= 12
        # Snap to scale
        if snap_to_scale and scale_tones:
            current = nearest_scale_tone(current, scale_tones)
        if rests is not None and idx < len(rests) and rests[idx]:
            continue
        notes.append((current, dur))

    return notes


# ---------------------------------------------------------------------------
# Behavior generators
# ---------------------------------------------------------------------------

def _pick_start_note(chord_tones: list[int], scale_tones: list[int], prev_note: Optional[int]) -> int:
    """Pick a good starting note — chord tone near previous note if available."""
    if not chord_tones:
        return scale_tones[len(scale_tones) // 2] if scale_tones else 60
    if prev_note is None:
        # Start on root or third
        return chord_tones[0] if chord_tones else 60
    # Pick chord tone closest to previous note
    return min(chord_tones, key=lambda n: abs(n - prev_note))


def generate_generative(
    rhythm_events: list[RhythmEvent],
    chord: VoicedChord,
    scale_tones: list[int],
    chord_tones: list[int],
    prev_note: Optional[int],
    base_velocity: int,
    seed: Optional[int],
    context: Optional[dict] = None,
    rest_probability: float = 0.0,
) -> list[MelodyNote]:
    """Freely picks notes from weighted pool of chord + scale tones."""
    rng = random.Random(seed) if seed is not None else random.Random()

    cw, sw, _ = BEHAVIOR_WEIGHTS["generative"]
    pool = ([(n, cw / len(chord_tones)) for n in chord_tones] if chord_tones else []) + \
           ([(n, sw / len(scale_tones)) for n in scale_tones] if scale_tones else [])

    if not pool:
        return []

    notes_out = []
    current = prev_note or _pick_start_note(chord_tones, scale_tones, None)

    for ev in rhythm_events:
        if ev.is_rest or (rest_probability > 0 and rng.random() < rest_probability):
            notes_out.append(MelodyNote(None, ev.start_beat, ev.duration_beats, is_rest=True))
            continue
        # Prefer notes within a 5th of current for smooth motion
        close = [n for n, _ in pool if abs(n - current) <= 7]
        candidates = close if close else [n for n, _ in pool]
        note = rng.choice(candidates)
        vel = int(base_velocity * ev.velocity_scale)
        notes_out.append(MelodyNote(note, ev.start_beat, ev.duration_beats, vel))
        current = note

    return notes_out


def generate_lyrical(
    rhythm_events: list[RhythmEvent],
    chord: VoicedChord,
    scale_tones: list[int],
    chord_tones: list[int],
    prev_note: Optional[int],
    base_velocity: int,
    seed: Optional[int],
    context: Optional[dict] = None,
    rest_probability: float = 0.0,
) -> list[MelodyNote]:
    """Stepwise motion, gravitates toward chord tones, longer phrases."""
    rng = random.Random(seed) if seed is not None else random.Random()

    notes_out = []
    current = _pick_start_note(chord_tones, scale_tones, prev_note)

    next_chord_tones = chord_tones
    if context and context.get("next_chord"):
        next_chord_tones = get_chord_tones_in_register(
            context["next_chord"], MELODY_OCTAVE_BOTTOM, MELODY_OCTAVE_TOP
        )

    for i, ev in enumerate(rhythm_events):
        if ev.is_rest or (rest_probability > 0 and rng.random() < rest_probability):
            notes_out.append(MelodyNote(None, ev.start_beat, ev.duration_beats, is_rest=True))
            continue

        stepwise = [n for n in scale_tones if 1 <= abs(n - current) <= 3]
        chord_nearby = [n for n in chord_tones if abs(n - current) <= 5]

        candidates = stepwise + chord_nearby
        if not candidates:
            candidates = scale_tones

        is_last_note = (i == len(rhythm_events) - 1)
        if is_last_note and context and next_chord_tones != chord_tones:
            candidates.extend(next_chord_tones)

        direction = rng.choice([-1, 1])
        directed = [n for n in candidates if (n - current) * direction > 0]
        if directed:
            candidates = directed

        note = rng.choice(candidates) if candidates else current
        vel = int(base_velocity * ev.velocity_scale)
        notes_out.append(MelodyNote(note, ev.start_beat, ev.duration_beats, vel))
        current = note

    return notes_out


def generate_sparse(
    rhythm_events: list[RhythmEvent],
    chord: VoicedChord,
    scale_tones: list[int],
    chord_tones: list[int],
    prev_note: Optional[int],
    base_velocity: int,
    seed: Optional[int],
    context: Optional[dict] = None,
    rest_probability: float = 0.0,          # ← was missing
) -> list[MelodyNote]:
    """Wide intervals, few notes, lots of space. Very ambient."""
    rng = random.Random(seed) if seed is not None else random.Random()

    notes_out = []
    current = _pick_start_note(chord_tones, scale_tones, prev_note)
    # Force extra rests — only play ~40% of non-rest slots
    # rest_probability from section can push this further toward silence
    play_probability = max(0.10, 0.40 - rest_probability)

    for ev in rhythm_events:
        if ev.is_rest or rng.random() > play_probability:
            notes_out.append(MelodyNote(None, ev.start_beat, ev.duration_beats, is_rest=True))
            continue

        # Wide leaps preferred — chord tones anywhere in register
        note = rng.choice(chord_tones) if chord_tones else rng.choice(scale_tones)
        vel = int(base_velocity * ev.velocity_scale * 0.85)  # slightly softer
        notes_out.append(MelodyNote(note, ev.start_beat, ev.duration_beats, vel))
        current = note

    return notes_out


def generate_develop(
    rhythm_events: list[RhythmEvent],
    chord: VoicedChord,
    scale_tones: list[int],
    chord_tones: list[int],
    prev_note: Optional[int],
    base_velocity: int,
    seed: Optional[int],
    motif: Optional[dict] = None,
    context: Optional[dict] = None,
    rest_probability: float = 0.0,
) -> list[MelodyNote]:
    """
    Applies motif transforms to generate melodic material.
    Falls back to generative if no motif provided.
    """
    if motif is None or not motif.get("intervals"):
        return generate_generative(
            rhythm_events, chord, scale_tones, chord_tones,
            prev_note, base_velocity, seed, context, rest_probability
        )

    rng = random.Random(seed) if seed is not None else random.Random()

    intervals = list(motif["intervals"])
    rhythm    = list(motif.get("rhythm", [1.0] * len(intervals)))
    rests     = list(motif["rests"]) if motif.get("rests") is not None else None
    pool      = motif.get("transform_pool", ["inversion", "retrograde"])

    # Pick a random transform
    transform = rng.choice(pool) if pool else None
    if transform:
        intervals = apply_transform(intervals, transform, rng=rng)
        rhythm    = apply_rhythm_transform(rhythm, transform)
        rests     = apply_rests_transform(rests, transform)

    start = _pick_start_note(chord_tones, scale_tones, prev_note)
    motif_notes = motif_to_notes(
        start, intervals, rhythm, scale_tones, chord_tones,
        MELODY_OCTAVE_BOTTOM, MELODY_OCTAVE_TOP, rests=rests
    )

    notes_out = []
    motif_idx = 0

    for ev in rhythm_events:
        if ev.is_rest or (rest_probability > 0 and rng.random() < rest_probability):
            notes_out.append(MelodyNote(None, ev.start_beat, ev.duration_beats, is_rest=True))
            continue

        if motif_idx < len(motif_notes):
            note, _ = motif_notes[motif_idx]
            motif_idx += 1
        else:
            candidates = chord_tones if chord_tones else scale_tones
            note = rng.choice(candidates) if candidates else 60

        vel = int(base_velocity * ev.velocity_scale)
        notes_out.append(MelodyNote(note, ev.start_beat, ev.duration_beats, vel))

    return notes_out


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

BEHAVIOR_GENERATORS = {
    "generative": generate_generative,
    "lyrical":    generate_lyrical,
    "sparse":     generate_sparse,
    "develop":    generate_develop,
}


def generate_melody(
    chord: VoicedChord,
    key: str,
    mode: str,
    behavior: str = "generative",
    density: str = "medium",
    total_beats: float = 8.0,
    base_velocity: int = 72,
    prev_note: Optional[int] = None,
    motif: Optional[dict] = None,
    octave_bottom: int = MELODY_OCTAVE_BOTTOM,
    octave_top: int = MELODY_OCTAVE_TOP,
    groove: Optional[str] = None,
    beats_per_bar: int = 4,
    swing: float = 0.0,
    seed: Optional[int] = None,
    context: Optional[dict] = None,
    rhythm_events_override: Optional[list] = None,
    rest_probability: float = 0.0,
) -> list[MelodyNote]:
    """
    Generate a melodic line over a single chord.

    Args:
        chord:          VoicedChord to melodize over
        key:            Key center e.g. "D"
        mode:           Mode name e.g. "dorian"
        behavior:       "generative" | "lyrical" | "sparse" | "develop"
        density:        "sparse" | "medium" | "full"
        total_beats:    Duration to fill
        base_velocity:  Base MIDI velocity
        prev_note:      Last note of previous phrase (for continuity)
        motif:          Motif dict from theme.json (for "develop" behavior)
        octave_bottom:  Lowest melody MIDI note
        octave_top:     Highest melody MIDI note
        groove:         Optional groove name (overrides density grid)
        beats_per_bar:  Beats per bar (for groove tiling)
        swing:          Swing ratio (0.0=straight, 0.67=triplet)
        seed:           Random seed
        rhythm_events_override: Pre-computed rhythm events from prosodic lens (skips get_pattern)

    Returns:
        List of MelodyNote
    """
    if behavior not in BEHAVIOR_GENERATORS:
        raise ValueError(f"Unknown behavior: '{behavior}'. Choose from {list(BEHAVIOR_GENERATORS.keys())}.")

    scale_tones = get_scale_tones(key, mode, octave_bottom, octave_top)
    chord_tones = get_chord_tones_in_register(chord, octave_bottom, octave_top)

    # Use prosodic rhythm if provided, otherwise get_pattern
    if rhythm_events_override is not None:
        rhythm_events = rhythm_events_override
    else:
        rhythm_events = get_pattern(total_beats, density=density, voice_type="melody",
                                    groove=groove, beats_per_bar=beats_per_bar, seed=seed)

    # Apply swing to melody rhythm. `swing` here is the public 0.0-1.0 field;
    # apply_swing() expects the internal 0.5-straight scale, so convert first.
    if swing and swing > 0:
        rhythm_events = apply_swing(rhythm_events, swing_ratio=remap_swing_ratio(swing))

    fn = BEHAVIOR_GENERATORS[behavior]

    if behavior == "develop":
        return fn(rhythm_events, chord, scale_tones, chord_tones,
                  prev_note, base_velocity, seed, motif, context, rest_probability)
    else:
        return fn(rhythm_events, chord, scale_tones, chord_tones,
                  prev_note, base_velocity, seed, context, rest_probability)


def _opening_bias_direction(ending_contour: Optional[str], arc: Optional[str]) -> Optional[str]:
    """
    Decide how the section opening should relate to the previous section's
    ending — the composer's "where do we pick up from here" decision.

      prev ascending  + arc swell/build        → continue ascending ("up")
      prev ascending  + arc fade_out/fade/decay → conscious reversal ("down")
      prev descending + arc build              → reversal upward ("up")
      prev static/peaked/troughed (or unknown) → no strong bias (None)
    """
    if not ending_contour or not arc:
        return None
    if ending_contour == "ascending":
        if arc in ("swell", "build"):
            return "up"
        if arc in ("fade_out", "fade", "decay"):
            return "down"
    elif ending_contour == "descending":
        if arc == "build":
            return "up"
    return None


def _opening_anchor_from_previous(piece_ctx, arc: Optional[str]) -> Optional[int]:
    """
    Compute a biased anchor pitch for the FIRST chord of a section, derived
    from the previous section's melody snapshot.  The anchor is fed to the
    behavior generators as prev_note, pulling the opening note selection
    toward (or consciously away from) where the previous section left off.

    Returns None when no previous melody exists or no bias applies —
    callers fall back to normal generation, so behavior is unchanged for
    the first section and for all existing call sites that don't pass
    piece_ctx.
    """
    if piece_ctx is None:
        return None
    prev = getattr(piece_ctx, "previous_melody", None)
    if prev is None or prev.last_pitch is None:
        return None

    direction = _opening_bias_direction(prev.ending_contour, arc)
    if direction is None:
        return None

    # Shift the anchor a third above/below the previous ending pitch so
    # nearest-candidate selection lands in the intended direction, then
    # fold into the melody register.
    anchor = prev.last_pitch + (4 if direction == "up" else -4)
    while anchor < MELODY_OCTAVE_BOTTOM:
        anchor += 12
    while anchor > MELODY_OCTAVE_TOP:
        anchor -= 12
    return anchor


def generate_melody_for_progression(
    chords: list[VoicedChord],
    key: str,
    mode: str,
    behavior: str = "generative",
    density: str = "medium",
    bars_per_chord=2.0,
    beats_per_bar: int = 4,
    base_velocity: int = 72,
    motif: Optional[dict] = None,
    motif_pool: Optional[list] = None,
    groove: Optional[str] = None,
    swing: float = 0.0,
    seed: Optional[int] = None,
    section_name: str = "",
    rhythm_events_override: Optional[list] = None,
    fugal_techniques: Optional[dict] = None,
    rest_probability: float = 0.0,
    piece_ctx: Optional[object] = None,
    arc: Optional[str] = None,
) -> list[MelodyNote]:
    """
    Generate a continuous melodic line across a full chord progression.
    Maintains note continuity between chords.

    Args:
        bars_per_chord: Float (uniform) or list[float] (per-chord durations).
        section_name: Name of section for context-aware generation.
        rhythm_events_override: Pre-computed rhythm events for the FULL progression.
            When provided, events are sliced per chord by beat range.
        fugal_techniques: Optional dict with keys like "motif_transform", "stretto_compression", etc.
        piece_ctx: Optional PieceContext for cross-section memory. When provided
            (with arc), the opening note of the FIRST chord is biased relative to
            the previous section's ending contour. Only the section opening is
            affected; normal generation takes over afterward.
        arc: The section's declared arc (used only for the opening bias).

    Returns:
        Flat list of MelodyNote spanning the entire progression
    """
    # Normalize to list
    if isinstance(bars_per_chord, (int, float)):
        bpc_list = [float(bars_per_chord)] * len(chords)
    else:
        bpc_list = list(bars_per_chord)

    # Apply fugal techniques to motif if specified
    effective_motif = motif
    fugal_tech = fugal_techniques or {}

    if fugal_tech and motif:
        from intervals.music.motif import transform as transform_motif, from_dict as motif_from_dict, to_dict as motif_to_dict

        # Convert dict to Motif object if needed
        if isinstance(motif, dict):
            motif_obj = motif_from_dict(motif)
        else:
            motif_obj = motif

        # ════════════════════════════════════════════════════════════
        # MOTIF TRANSFORMS (inversion, retrograde, augmentation, etc.)
        # ════════════════════════════════════════════════════════════

        transform_name = fugal_tech.get("motif_transform")
        if transform_name and transform_name != "none":
            # Support multiple transform options from motif.py
            valid_transforms = [
                "inversion", "retrograde", "retrograde_inversion",
                "augmentation", "diminution",
                "transpose_up", "transpose_down",
                "expand", "compress", "shuffle"
            ]
            if transform_name in valid_transforms:
                motif_obj = transform_motif(motif_obj, transform_name, seed=seed)

        # ════════════════════════════════════════════════════════════
        # STRETTO COMPRESSION (rhythm scaling)
        # ════════════════════════════════════════════════════════════

        compression = fugal_tech.get("stretto_compression")
        if compression and compression != 1.0:
            # Scale all rhythm values by compression factor
            # Ensure minimum duration to avoid zero-length notes
            compressed_rhythm = [max(0.125, r * compression) for r in motif_obj.rhythm]
            motif_obj.rhythm = compressed_rhythm

        # ════════════════════════════════════════════════════════════
        # SUBJECT FRAGMENTATION (episodic development)
        # ════════════════════════════════════════════════════════════

        fragment_size = fugal_tech.get("subject_fragmentation")
        if fragment_size and isinstance(fragment_size, int) and fragment_size > 0:
            # Use only first N intervals of the motif
            n = min(fragment_size, len(motif_obj.intervals))
            motif_obj.intervals = motif_obj.intervals[:n]
            motif_obj.rhythm = motif_obj.rhythm[:n]
            motif_obj.name = f"{motif_obj.name}_fragment_{n}"

        # Convert back to dict for use in generate_melody
        effective_motif = motif_to_dict(motif_obj)

    all_notes = []
    prev_note = None
    beat_offset = 0.0

    # ════════════════════════════════════════════════════════════
    # CROSS-SECTION OPENING BIAS (composer behavior)
    # Seed prev_note for the FIRST chord only — once chord 0 has
    # generated, the loop's own continuity tracking takes over.
    # No-op when piece_ctx is None, when this is the first section,
    # or when contour/arc combination implies no strong bias.
    # ════════════════════════════════════════════════════════════
    opening_anchor = _opening_anchor_from_previous(piece_ctx, arc)
    if opening_anchor is not None:
        prev_note = opening_anchor

    # ════════════════════════════════════════════════════════════
    # CANONIC IMITATION (offset voice entries like stretto)
    # ════════════════════════════════════════════════════════════

    canonic_imitation = fugal_tech.get("canonic_imitation", False) if fugal_tech else False
    canon_interval = fugal_tech.get("canon_interval", 4) if fugal_tech else 4  # beats

    for i, chord in enumerate(chords):
        total_beats = bpc_list[i] * beats_per_bar
        chord_seed = (seed + i) if seed is not None else None

        # Pick motif for this chord — draw from pool if available, else use primary
        if motif_pool and len(motif_pool) > 1:
            rng = random.Random(chord_seed)
            chord_motif = rng.choice(motif_pool)
        else:
            chord_motif = effective_motif

        # Build chord context for this position in progression
        chord_context = {
            "chord_index": i,
            "total_chords": len(chords),
            "next_chord": chords[(i + 1) % len(chords)],
            "next_chord_root": chords[(i + 1) % len(chords)].root_name,
            "bars_in_this_chord": bpc_list[i],
            "bars_in_next_chord": bpc_list[(i + 1) % len(chords)],
            "section_name": section_name,
        }

        # Slice rhythm events for this chord's time window
        chord_rhythm = None
        if rhythm_events_override is not None:
            chord_end = beat_offset + total_beats
            chord_rhythm = []
            for ev in rhythm_events_override:
                if ev.start_beat >= beat_offset and ev.start_beat < chord_end:
                    from intervals.music.rhythm import RhythmEvent
                    local_start = ev.start_beat - beat_offset
                    local_dur = min(ev.duration_beats, total_beats - local_start)
                    chord_rhythm.append(RhythmEvent(
                        start_beat=local_start,
                        duration_beats=max(0.25, local_dur),
                        velocity_scale=ev.velocity_scale,
                        is_rest=ev.is_rest,
                    ))
            if not chord_rhythm:
                chord_rhythm = None

        notes = generate_melody(
            chord, key, mode,
            behavior=behavior,
            density=density,
            total_beats=total_beats,
            base_velocity=base_velocity,
            prev_note=prev_note,
            motif=chord_motif,
            groove=groove,
            beats_per_bar=beats_per_bar,
            swing=swing,
            seed=chord_seed,
            context=chord_context,
            rhythm_events_override=chord_rhythm,
            rest_probability=rest_probability,
        )
        # Offset beat positions
        for n in notes:
            n.start_beat += beat_offset
        all_notes.extend(notes)

        # Track last sounding note for continuity
        sounding = [n for n in notes if not n.is_rest]
        if sounding:
            prev_note = sounding[-1].midi_note

        beat_offset += total_beats

    return all_notes


# ---------------------------------------------------------------------------
# Quick test / demo
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    from harmony import resolve_progression

    key = "D"
    mode = "dorian"
    progression = ["i", "VII", "iv", "v"]
    motif = {
        "intervals": [2, -1, 3, -2],
        "rhythm": [1.0, 0.5, 0.5, 1.0],
        "transform_pool": ["inversion", "retrograde", "augmentation"]
    }

    print("=== Intervals Engine — melody.py demo ===\n")
    chords = resolve_progression(progression, key, mode, density="medium")

    for behavior in ("generative", "lyrical", "sparse", "develop"):
        print(f"Behavior: {behavior}  Key: {key}  Mode: {mode}  Density: medium")
        notes = generate_melody_for_progression(
            chords, key, mode,
            behavior=behavior,
            density="medium",
            bars_per_chord=2,
            motif=motif,
            seed=42,
        )
        sounding = [n for n in notes if not n.is_rest]
        rests    = [n for n in notes if n.is_rest]
        print(f"  {len(sounding)} notes, {len(rests)} rests across {len(chords)} chords")
        for n in sounding[:6]:
            name = CHROMATIC[n.midi_note % 12]
            print(f"    beat={n.start_beat:5.1f}  {name}{n.midi_note}  dur={n.duration_beats:.2f}  vel={n.velocity}")
        if len(sounding) > 6:
            print(f"    ... ({len(sounding) - 6} more notes)")
        print()
