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
    "intervals": [2, -1, 3],        # diatonic scale-degree steps between
                                     # notes, resolved against the piece's
                                     # mode (NOT semitones) — see
                                     # motif.py's Motif.intervals docstring
                                     # for the full contract. PENDING as of
                                     # 2026-08: motif_to_notes below still
                                     # implements the old semitone contract;
                                     # this comment states the Phase B target.
    "rhythm":    [1.0, 0.5, 0.5],   # note durations in beats
    "transform_pool": ["inversion", "retrograde", "augmentation"]
  }
"""

import random
import math
from dataclasses import dataclass
from typing import Optional
from intervals.music.harmony import VoicedChord, CHROMATIC, MODES, key_to_midi_root
from intervals.music.scale_degrees import pitch_classes, degree_to_pitch, pitch_to_degree
from intervals.music.motif import Motif, transform as apply_motif_transform
from intervals.music.rhythm import (
    RhythmEvent, get_pattern, apply_swing, remap_swing_ratio,
    apply_rhythm_transform, apply_rests_transform, section_position_t,
)
from intervals.music.melodic_shape import (
    resolve_apex_pitch, apex_weighted_candidates, cadence_weighted_candidates,
    directed_anchor_shift,
)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

from intervals.core.schemas import REGISTER_BOUNDS

# Default lead-melody register when no explicit register is set on the piece.
# Was hardcoded here as a literal (60, 84) duplicating REGISTER_BOUNDS["mid"]
# by coincidence, not by reference — the two could silently drift apart, and
# in fact this was the actual default path for most renders (voices[0].bounds()
# only overrides it when a section sets an explicit register), so editing
# REGISTER_BOUNDS alone had no effect on the common case. Derived now instead
# of duplicated.
MELODY_OCTAVE_BOTTOM, MELODY_OCTAVE_TOP = REGISTER_BOUNDS["mid"]

# "sparse" behavior's own onset scarcity, independent of rest_probability
# (see generate_sparse docstring for the decoupling rationale).
SPARSE_PLAY_PROBABILITY = 0.40

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

def _wrap_degree_diff(raw: int, scale_len: int = 7) -> int:
    """
    Wrap a raw scale-degree difference into the smallest-magnitude signed
    equivalent (e.g. for a 7-note scale: range [-3, 3]).

    A root motion of "down a step" (-4) and "up a fourth" (+3) land on the
    same pitch class, differing only by a full octave (7 diatonic steps
    apart). Picking the smaller-magnitude option keeps the sequenced melody
    in a sensible register instead of leaping an unnecessary octave — it
    does not change which harmonic motion is being followed, only which
    octave the answer is voiced in.
    """
    half = scale_len // 2
    return ((raw + half) % scale_len) - half


def _sequence_intervals_diatonically(
    intervals: list[int], scale_tones: list[int], degree_shift: int
) -> list[int]:
    """
    Transpose a motif's interval shape by `degree_shift` diatonic scale
    steps (not semitones), snapping each note to the scale.

    PENDING (Phase B): this function currently assumes `intervals` arrives
    in semitones. Once Motif.intervals natively holds diatonic steps (see
    that docstring), Phase B2 reuses the same scale_degrees primitives this
    function now calls — motif_to_notes will walk degree space directly
    instead of converting semitones to degrees just for this one transform.

    This is a real/tonal sequence in the Piston sense: the harmony moves by
    some interval (e.g. the descending-fifths vi-ii-v-I chain), and the
    melodic cell is restated at the new scale position — same shape, but
    its exact semitone content adjusts as needed to stay diatonic (a major
    third from one scale step may become a minor third from another).
    That's what makes it "tonal" rather than a literal chromatic shift:
    apply_transform's existing "transpose" moves every interval by a fixed
    +2 semitones regardless of harmony; this moves the whole shape to a new
    scale degree and re-derives each interval from there.

    Degree arithmetic is deliberately unbounded (no clamping to
    `scale_tones`'s register window) — clamping there silently flattened
    the top of the contour whenever a shift pushed past the window edge
    (verified: a +3 shift on this piece's motif collapsed four distinct
    notes to a single repeated pitch). `motif_to_notes` already folds the
    final absolute pitches into the melody register one octave at a time,
    so this only needs to get the pitch-class shape right; register
    placement is someone else's job, correctly, downstream.

    Pitch-to-degree conversion (Phase B1) is sequential: each note's degree
    is resolved relative to the previous note's degree, not independently,
    so a genuine tie (a pitch exactly halfway between two scale degrees)
    breaks toward the small step rather than an accidental octave jump —
    see scale_degrees.pitch_to_degree for the case that motivated this.
    """
    if not scale_tones or degree_shift == 0:
        return list(intervals)

    pcs = pitch_classes(scale_tones)
    anchor = scale_tones[len(scale_tones) // 2]

    anchor_degree = pitch_to_degree(anchor, pcs)
    abs_pitches = [anchor + iv for iv in intervals]
    degrees = []
    prev_degree = anchor_degree
    for p in abs_pitches:
        d = pitch_to_degree(p, pcs, prev_degree=prev_degree)
        degrees.append(d)
        prev_degree = d

    # PRE-EXISTING BUG FIX (found while doing Phase B1, not introduced by
    # it — the original code had this same defect, just never exercised by
    # any test): motif_to_notes consumes `intervals` as successive deltas
    # (each one added cumulatively to a running pitch), the same convention
    # every other transform in apply_transform already follows. The
    # previous version here returned offsets-from-the-first-note instead,
    # which is a different shape entirely once fed through cumulative
    # addition (verified: produced deltas like 16, 31, 43 on a real motif
    # instead of small diatonic steps). Fixed by shifting the anchor's own
    # degree along with every note's, then re-deriving successive deltas
    # from that shifted reference point — this preserves the motif's shape
    # exactly the way "sequence" is supposed to (same relative contour,
    # restated `degree_shift` diatonic steps higher/lower).
    shifted_anchor_pitch = degree_to_pitch(anchor_degree + degree_shift, pcs)
    shifted_pitches = [degree_to_pitch(d + degree_shift, pcs) for d in degrees]
    deltas = []
    prev_pitch = shifted_anchor_pitch
    for p in shifted_pitches:
        deltas.append(p - prev_pitch)
        prev_pitch = p
    return deltas


def apply_transform(
    intervals: list[int],
    transform: str,
    rng=None,
    scale_tones: Optional[list[int]] = None,
    degree_shift: int = 0,
) -> list[int]:
    """
    Apply a Bach-style transform to an interval sequence.

    Transforms:
      inversion    — negate all intervals
      retrograde   — reverse the sequence
      augmentation — double all durations (applied to rhythm separately)
      diminution   — halve all durations (applied to rhythm separately)
      transpose    — shift all intervals by +1 diatonic step (decided,
                     Phase B3 — was +2 semitones under the old contract;
                     adds variety; NOT harmony-aware, unlike "sequence"
                     below)
      shuffle      — randomly reorder intervals
      sequence     — diatonic (harmony-aware) restatement at a new scale
                     degree; requires scale_tones + degree_shift from the
                     caller (see _sequence_intervals_diatonically). Falls
                     back to a no-op if no harmonic context is available,
                     rather than guessing — a silent wrong transposition is
                     worse than no transform at all.
    """
    if rng is None:
        import random as _r
        rng = _r.Random()
    if transform == "inversion":
        return [-i for i in intervals]
    elif transform == "retrograde":
        return list(reversed(intervals))
    elif transform == "transpose":
        return [i + 1 for i in intervals]
    elif transform == "shuffle":
        shuffled = list(intervals)
        rng.shuffle(shuffled)
        return shuffled
    elif transform == "sequence":
        return _sequence_intervals_diatonically(intervals, scale_tones, degree_shift)
    else:
        # augmentation / diminution affect rhythm, not intervals
        return list(intervals)


def fold_to_register(pitch: int, octave_bottom: int, octave_top: int,
                      near: Optional[int] = None,
                      scale_tones: Optional[list[int]] = None) -> int:
    """
    Bring `pitch` into [octave_bottom, octave_top] — but ONLY when `pitch`
    is actually out of bounds. An already-valid pitch is returned untouched.

    Once `pitch` is genuinely out of bounds, normalizing it toward the
    register by whole octaves (the loop below) always converges to a
    window exactly 12 semitones wide, sitting just outside whichever wall
    was crossed — so at most ONE octave-equivalent of `pitch` ever lands
    back in [octave_bottom, octave_top] (proven exhaustively, not just
    argued: swept every out-of-bounds pitch against several register
    widths from 12 to 80 semitones, zero cases produced more than one
    in-bounds candidate). Practically: this function's own "pick whichever
    candidate is closest to X" step never actually has more than one
    option to choose between. `near`'s only real effect is through the
    scale_tones fallback below — it is NOT a meaningful lever on the pure
    octave-shift path, and no caller should rely on it being one there.

    scale_tones: when given together with `near`, this is where the actual
    fix lives. It picks the closest ACTUAL scale tone in [octave_bottom,
    octave_top] to `near`, rather than accepting whatever single octave-
    equivalent the shift above produces — because that one forced option
    can be far from where the line actually is. A register box under ~2
    octaves wide (a soprano/mid box is 18 semitones — not even 1.5
    octaves) makes this common: reported directly against a rendered
    fugue, a subject voice hovering around MIDI 64-65 (just above its
    63-note floor) would occasionally compute a raw next-degree pitch one
    step below the floor; the ONLY octave-equivalent inside the box was
    74, so every such step surfaced as an isolated note roughly a 9th
    above its neighbors, recurring at the same point in the subject's
    tiling cycle on every repeat. Landing on the nearest scale tone to the
    previous note instead — even if that means repeating it, or landing on
    a different scale degree than the raw unfolded computation implied —
    keeps the line where the ear expects it; manually correcting these by
    ear (pulling the note back down next to its neighbors) is exactly this
    policy applied by hand.

    Deliberately NOT wired into every caller: generate_develop's cadence-
    pull mechanism back-calculates a retile anchor as resolution_pitch
    minus the motif's net diatonic displacement, an equation that assumes
    register-folding only ever shifts pitch by whole octaves (true of the
    plain path below, false of the scale_tones fallback). So
    motif_to_notes (melody.py, shared by cadence-pull) passes `near` alone
    — inert per the proof above, but harmless, and kept for the day this
    function's normalization changes and a real multi-candidate case
    becomes reachable. generate_subject_entry (motif.py) — which has no
    cadence-pull mechanism to break — passes both `near` and scale_tones,
    getting the actual fix.

    That "only when out of bounds" guard was missing in the first version of
    this function, and it was a real bug, not a tuning choice: the function
    searched every octave-equivalent and picked whichever was nearest center
    regardless of whether the original pitch needed to move at all. Traced
    directly from a reported artifact (a neighbor-tone step that should have
    been E-F#-E rendering as E-F#[an octave low]-E): pitch=78 with bounds
    (63, 81) was folded down to 66, even though 78 sits comfortably inside
    the register with room to spare — the pre-guard code still ran the full
    candidate search on an already-valid pitch, where p itself (78) and
    p-12 (66) are BOTH valid candidates (this is the one regime that really
    does produce more than one option — an in-bounds pitch that should
    never have reached this logic at all). 78 and 66 are equidistant from
    the center (72), so the tie-break silently dragged a perfectly valid
    note down an octave — and the same mechanism was doing it to any
    in-bounds note whose octave-equivalent happened to sit closer to
    center, not just exact ties (measured on a real render: 63->75,
    64->76, both moved a full octave for no reason). This was pulling
    melodic content toward the register's center far more aggressively
    than intended, which is the "voice feels limited" complaint in
    stronger form than a width tuning issue would produce on its own. The
    guard below is what actually fixed that bug; everything past it only
    ever runs on pitches that are genuinely out of bounds.
    """
    if octave_bottom <= pitch <= octave_top:
        return pitch

    if near is not None and scale_tones:
        in_register = [s for s in scale_tones if octave_bottom <= s <= octave_top]
        if in_register:
            return min(in_register, key=lambda s: (abs(s - near), s))

    p = pitch
    while p < octave_bottom - 12:
        p += 12
    while p > octave_top + 12:
        p -= 12
    candidates = [c for c in (p - 12, p, p + 12) if octave_bottom <= c <= octave_top]
    if not candidates:
        return max(octave_bottom, min(octave_top, p))
    if len(candidates) == 1:
        return candidates[0]
    # Unreachable for genuinely out-of-bounds input per the proof above —
    # kept as a deterministic, documented fallback rather than an
    # unguarded assumption, in case a future change to the normalization
    # loop above ever makes this reachable again.
    target = near if near is not None else (octave_bottom + octave_top) / 2
    return min(candidates, key=lambda c: (abs(c - target), c))


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
    prefer_neighbor_fold: bool = False,
) -> list[tuple[int, float]]:
    """
    Convert a motif (interval sequence + rhythm) to (midi_note, duration) pairs
    starting from start_midi.

    prefer_neighbor_fold: when True, an out-of-bounds step folds to the
    nearest ACTUAL scale tone to the previous rendered pitch (fold_to_
    register's scale_tones fallback) instead of being stuck with whatever
    single octave-equivalent the plain shift produces — see fold_to_
    register's docstring for why a narrow register makes that single
    option regularly land a 9th-or-more from the line's actual
    neighborhood. Defaults to False because generate_develop's cadence-
    pull mechanism (see its call site) predicts the walk's LAST note by
    assuming register-folding only ever shifts pitch by whole octaves;
    the scale_tones fallback can land on a different scale degree
    entirely, which breaks that prediction. generate_develop passes True
    whenever melodic_arc is absent for the whole progression (not just at
    the cadential chord -- a preceding statement's altered ending pitch
    still feeds the next statement's anchor, so the flag has to stay
    consistent across an entire melodic_arc-bearing progression, not just
    the cadential moment; see generate_develop's arc_bias_active comment).
    generate_subject_entry always passes True; it has no cadence-pull
    mechanism to break.

    intervals: diatonic scale-degree steps (Phase B2 of the diatonic-motif
    migration — see motif.py's Motif.intervals docstring for the full
    contract). Each step moves `current` by that many scale-degree
    positions in `scale_tones`, not semitones — by construction, every
    resulting pitch is a scale tone, so there is no separate quantization
    pass and nothing to erase. This replaces the old behavior (add the
    interval as semitones, then snap the result to the nearest scale tone),
    which was the root cause of the bug that motivated this whole
    migration: a motif built from ±1-semitone neighbor-tone steps in a mode
    whose local scale gap was a whole tone had those steps silently
    snapped back to their starting pitch — six of nine notes in one real
    catalog motif collapsed to a single repeated pitch (traced and
    confirmed against piece_train's motif in E mixolydian).

    snap_to_scale: when True (the default, and the only path any current
    caller uses), walks diatonic degree space as described above. When
    False, preserves this parameter's ORIGINAL meaning unchanged from
    before this migration: `intervals` are treated as literal, unquantized
    semitone deltas — no scale awareness at all, register-folding only.
    This is a deliberate escape hatch for chromatic content that is
    explicitly out of the diatonic-motif contract (per the "chromatic
    alterations are authored manually in Logic after render, not modeled
    by intervals" decision), not a removed or half-migrated feature.

    rests: optional, same length as rhythm. True = this slot is silent and is
    omitted from the returned list entirely (not included as a placeholder).
    The interval is still applied to the running pitch position underneath a
    rest, so the melodic shape's trajectory continues correctly once sounding
    notes resume — a rest pauses the line, it doesn't freeze its contour.

    Returns list of (midi_note, duration_beats), one entry per SOUNDING slot.
    """
    notes = []
    pairs = list(zip(intervals, rhythm))
    if not pairs:
        return notes

    pcs = pitch_classes(scale_tones) if scale_tones else []
    walk_degrees = snap_to_scale and bool(pcs)

    current_pitch = start_midi
    current_degree = pitch_to_degree(start_midi, pcs) if walk_degrees else None
    prev_pitch = start_midi

    for idx, (interval, dur) in enumerate(pairs):
        if walk_degrees:
            current_degree = current_degree + interval
            current_pitch = degree_to_pitch(current_degree, pcs)
        else:
            current_pitch = current_pitch + interval
        # Clamp to register. See prefer_neighbor_fold's docstring above for
        # when the stronger (scale_tones) fallback is and isn't safe to use.
        # Folding by whole octaves preserves pitch class exactly, so a
        # pitch that was already on-scale from the degree walk above stays
        # on-scale after folding either way; no re-snap is needed here.
        current_pitch = fold_to_register(
            current_pitch, octave_bottom, octave_top, near=prev_pitch,
            scale_tones=scale_tones if prefer_neighbor_fold else None,
        )
        prev_pitch = current_pitch
        if rests is not None and idx < len(rests) and rests[idx]:
            continue
        notes.append((current_pitch, dur))

    return notes


# ---------------------------------------------------------------------------
# Behavior generators
# ---------------------------------------------------------------------------

def _position_t_from_context(context: Optional[dict], local_start_beat: float) -> float:
    """
    Melody's normalized position within the SECTION (not just the current
    chord), for apex/cadence bias (Phase 2 of the apex/goal-tone build).

    generate_lyrical/generate_develop/etc. are called per-CHORD with
    rhythm_events expressed in chord-LOCAL beat coordinates (first onset
    at 0.0 for every chord) — see generate_melody_for_progression's
    chord_rhythm slicing. That local coordinate alone can't answer "how
    far through the section are we," so generate_melody_for_progression
    threads section_total_bars/section_beat_offset/beats_per_bar through
    chord_context for exactly this purpose.

    Converts to bar_index and calls rhythm.section_position_t() — the
    SAME formula generator.py's velocity_envelope already uses for the
    dynamic arc, extracted there specifically so this wouldn't become a
    second, independently-drifting implementation of "where are we in
    the section" (see melodic_shape.py's module docstring, and
    rhythm.section_position_t's own docstring, for why that mattered
    enough to extract ahead of building this).

    Returns 0.0 (start-of-section) if the required context fields are
    absent — safe and inert, since callers only consult this value when
    melodic_arc bias was actually requested; a missing field here means
    generate_melody_for_progression didn't provide it, not that position
    is genuinely unknown for a caller that needs it.
    """
    if not context:
        return 0.0
    total_bars = context.get("section_total_bars")
    beat_offset = context.get("section_beat_offset")
    bpb = context.get("beats_per_bar")
    if total_bars is None or beat_offset is None or not bpb:
        return 0.0
    absolute_beat = beat_offset + local_start_beat
    bar_index = int(absolute_beat // bpb)
    return section_position_t(bar_index, total_bars)


def _cadence_resolution_pitch(chord: VoicedChord, chord_tones: list[int], current: int) -> int:
    """
    The pitch cadence_weighted_candidates should resolve toward: this
    chord's ROOT, in melody register, nearest wherever the melody
    currently sits — not necessarily chord_tones[0] (which is register-
    sorted, not root-first once the chord is expanded across octaves),
    and not the piece's tonic (a section can legitimately cadence on a
    non-tonic harmonic goal, e.g. a half-cadence on V — resolving toward
    whatever chord is actually functioning as the cadential goal is the
    musically honest interpretation of "goal-tone pull," matching the
    original diagnosis: weight toward the target of the CURRENT harmonic
    function, not an assumed one).

    chord.root_name is authoritative regardless of inversion (midi_notes[0]
    is the lowest voiced note, which for an inverted chord is the third or
    fifth, not the root) — CHROMATIC gives its pitch class directly.
    """
    root_pc = CHROMATIC.index(chord.root_name)
    root_candidates = [c for c in chord_tones if c % 12 == root_pc]
    if not root_candidates:
        return chord_tones[0] if chord_tones else current
    return min(root_candidates, key=lambda c: abs(c - current))


def _last_sounding_index(intervals: list[int], rests: Optional[list[bool]]) -> Optional[int]:
    """
    Index of the last non-rest slot in a transformed motif statement, or
    None if every slot is a rest. Used by generate_develop's cadence
    bias to find how many of `intervals` actually contribute to the
    statement's audible ending, so the anchor can be back-calculated to
    land THAT note near resolution — not just the statement's first note
    (see generate_develop's cadence branch for why this distinction
    matters: an anchor shifted straight toward the resolution pitch
    controls where a statement starts, and the motif's own transformed
    shape can walk several more diatonic steps away from there before
    its last sounding note, undoing the shift entirely — caught via
    statistical verification, not by inspection).
    """
    if not intervals:
        return None
    if rests is None:
        return len(intervals) - 1
    for idx in range(len(intervals) - 1, -1, -1):
        if idx >= len(rests) or not rests[idx]:
            return idx
    return None


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
    """
    Freely picks notes from weighted pool of chord + scale tones.

    Apex/goal-tone bias (Phase 3 of the apex/goal-tone build): when
    context["melodic_arc"] is present with an "apex_degree", the
    proximity-filtered candidate pool below is additionally weighted
    toward the declared apex before apex_position, and away from it
    after — see melodic_shape.apex_weighted_candidates. Absent
    melodic_arc, behavior is byte-identical to before this existed.

    Cadence pull is new here, not a generalization of an existing
    mechanism the way it was for generate_lyrical (which already had an
    is_last_note/next-chord-tone extension to generalize) — this
    behavior had no cadence-adjacent logic at all before this phase.
    """
    rng = random.Random(seed) if seed is not None else random.Random()

    cw, sw, _ = BEHAVIOR_WEIGHTS["generative"]
    pool = ([(n, cw / len(chord_tones)) for n in chord_tones] if chord_tones else []) + \
           ([(n, sw / len(scale_tones)) for n in scale_tones] if scale_tones else [])

    if not pool:
        return []

    notes_out = []
    current = prev_note or _pick_start_note(chord_tones, scale_tones, None)

    melodic_arc = context.get("melodic_arc") if context else None
    apex_pitch = context.get("apex_pitch") if context else None
    apex_position = (melodic_arc.get("apex_position", 0.7) if melodic_arc else 0.7)

    for i, ev in enumerate(rhythm_events):
        if ev.is_rest or (rest_probability > 0 and rng.random() < rest_probability):
            notes_out.append(MelodyNote(None, ev.start_beat, ev.duration_beats, is_rest=True))
            continue
        # Prefer notes within a 5th of current for smooth motion
        close = [n for n, _ in pool if abs(n - current) <= 7]
        candidates = close if close else [n for n, _ in pool]

        if apex_pitch is not None:
            position_t = _position_t_from_context(context, ev.start_beat)
            candidates = apex_weighted_candidates(
                candidates, current, apex_pitch, position_t, apex_position,
            )

        is_last_note = (i == len(rhythm_events) - 1)
        if melodic_arc and is_last_note and context and context.get("is_cadential_chord"):
            resolution_pitch = _cadence_resolution_pitch(chord, chord_tones, current)
            candidates = cadence_weighted_candidates(candidates, resolution_pitch)

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
    """
    Stepwise motion, gravitates toward chord tones, longer phrases.

    Apex/goal-tone bias (Phase 2 of the apex/goal-tone build): when
    context["melodic_arc"] is present with an "apex_degree", this
    behavior's previously-aimless per-note coin flip (`direction =
    rng.choice([-1, 1])`) is replaced by a purposeful bias toward the
    declared apex before apex_position, and away from it (settling)
    after — see melodic_shape.apex_weighted_candidates. Absent
    melodic_arc, behavior is byte-identical to before this existed: same
    coin flip, same everything.

    Cadence pull layers on top, independently: at whichever chord Phase
    0's cadence decision marks as cadential (context["is_cadential_chord"]),
    the final note is additionally weighted toward that chord's root —
    generalizing the existing next-chord-tone extension below (which stays
    unconditional; it's a different, always-useful thing: smooth
    voice-leading into whatever comes next, not a harmonic arrival).
    """
    rng = random.Random(seed) if seed is not None else random.Random()

    notes_out = []
    current = _pick_start_note(chord_tones, scale_tones, prev_note)

    next_chord_tones = chord_tones
    if context and context.get("next_chord"):
        next_chord_tones = get_chord_tones_in_register(
            context["next_chord"],
            context.get("octave_bottom", MELODY_OCTAVE_BOTTOM),
            context.get("octave_top", MELODY_OCTAVE_TOP),
        )

    melodic_arc = context.get("melodic_arc") if context else None
    apex_pitch = context.get("apex_pitch") if context else None
    apex_position = (melodic_arc.get("apex_position", 0.7) if melodic_arc else 0.7)

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

        if apex_pitch is not None:
            position_t = _position_t_from_context(context, ev.start_beat)
            candidates = apex_weighted_candidates(
                candidates, current, apex_pitch, position_t, apex_position,
            )
        else:
            direction = rng.choice([-1, 1])
            directed = [n for n in candidates if (n - current) * direction > 0]
            if directed:
                candidates = directed

        if melodic_arc and is_last_note and context and context.get("is_cadential_chord"):
            resolution_pitch = _cadence_resolution_pitch(chord, chord_tones, current)
            candidates = cadence_weighted_candidates(candidates, resolution_pitch)

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
    rest_probability: float = 0.0,
) -> list[MelodyNote]:
    """
    Wide intervals, few notes, lots of space. Very ambient.

    Decoupled (2026-07): rest_probability used to be absorbed into this
    behavior's own onset-thinning via `max(0.10, 0.40 - rest_probability)`.
    That mixed two concerns into one number and, worse, silently collapsed:
    every rest_probability >= 0.30 floored at the same 0.10 play rate, so a
    section arc that graduates rest_probability upward (e.g. 0.5 -> 0.6 ->
    0.85 -> 0.9 across a dissolve) produced IDENTICAL melody density at
    every step instead of actually thinning further.

    Now rest_probability is the same flat per-onset filter every other
    behavior (generative/lyrical/develop) already uses, applied first.
    SPARSE_PLAY_PROBABILITY governs only this behavior's own baked-in
    scarcity, applied independently to whatever onsets survive that filter.
    The two probabilities compose multiplicatively (independent events), so
    at rest_probability=0.0 sparse behaves exactly as before (~40% of
    onsets), and at rest_probability=1.0 the section goes fully silent —
    matching the other three behaviors' contract instead of floor-locking
    at 10% no matter how high rest_probability climbs.

    Apex/goal-tone bias (Phase 5 of the apex/goal-tone build, wired for
    consistency across all four behaviors — the LAST of the four, and
    deliberately given less confidence than the others): when
    context["melodic_arc"] is present, this behavior's uniform
    "chord tone anywhere in register" choice gets the same
    apex_weighted_candidates/cadence_weighted_candidates treatment as
    generate_generative, same strength, not softened. That's a
    deliberate choice, not an oversight — softening it automatically
    would be an implicit special-case baked into the engine; the real
    control a composer has is simply whether to declare melodic_arc on
    a sparse section at all. But sparse's entire identity is
    unpredictable wide leaps, and a directional pull toward a peak is in
    real tension with that — unlike the other three phases, passing
    statistics here don't settle whether the result still sounds like
    sparse. That's a judgment call for actual listening, not something
    this docstring or the test suite can certify on its own.
    """
    rng = random.Random(seed) if seed is not None else random.Random()

    notes_out = []
    current = _pick_start_note(chord_tones, scale_tones, prev_note)

    melodic_arc = context.get("melodic_arc") if context else None
    apex_pitch = context.get("apex_pitch") if context else None
    apex_position = (melodic_arc.get("apex_position", 0.7) if melodic_arc else 0.7)

    for i, ev in enumerate(rhythm_events):
        if ev.is_rest or (rest_probability > 0 and rng.random() < rest_probability):
            notes_out.append(MelodyNote(None, ev.start_beat, ev.duration_beats, is_rest=True))
            continue

        if rng.random() > SPARSE_PLAY_PROBABILITY:
            notes_out.append(MelodyNote(None, ev.start_beat, ev.duration_beats, is_rest=True))
            continue

        # Wide leaps preferred — chord tones anywhere in register
        candidates = list(chord_tones) if chord_tones else list(scale_tones)

        if apex_pitch is not None:
            position_t = _position_t_from_context(context, ev.start_beat)
            candidates = apex_weighted_candidates(
                candidates, current, apex_pitch, position_t, apex_position,
            )

        is_last_note = (i == len(rhythm_events) - 1)
        if melodic_arc and is_last_note and context and context.get("is_cadential_chord"):
            resolution_pitch = _cadence_resolution_pitch(chord, chord_tones, current)
            candidates = cadence_weighted_candidates(candidates, resolution_pitch)

        note = rng.choice(candidates)
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
    Builds the melody FROM the motif, using transforms for variety across
    repetitions. Falls back to generative if no motif provided.

    Rewritten (2026-07): the previous version built exactly one statement
    of the (transformed) motif per chord and let every onset past the end
    of that single statement fall through to unrelated rng.choice(chord_tones)
    filler. For any chord whose rhythm grid spans more than one motif cycle
    — the common case, since rhythm="motif" tiles the cycle across the
    whole section — that meant the overwhelming majority of "develop"
    notes were never motif-derived at all (measured: 87.5% filler on a
    64-beat chord against an 8-beat cycle). That's not development, it's a
    single quotation followed by unrelated noise wearing its label.

    Now: the motif is retiled, once per full cycle, for as many
    repetitions as the chord's onset grid requires. Each repetition picks
    its own transform independently (never the same transform as the
    immediately preceding repetition, when the pool has more than one
    option) — this is the "variety" half of the request: real developing
    variation restates the cell continuously, changing how each time,
    rather than reaching for unrelated material once the first statement
    runs out.
    """
    if motif is None or not motif.get("intervals"):
        return generate_generative(
            rhythm_events, chord, scale_tones, chord_tones,
            prev_note, base_velocity, seed, context, rest_probability
        )

    rng = random.Random(seed) if seed is not None else random.Random()

    base_intervals = list(motif["intervals"])
    base_rhythm    = list(motif.get("rhythm", [1.0] * len(base_intervals)))
    base_rests     = list(motif["rests"]) if motif.get("rests") is not None else None
    pool           = motif.get("transform_pool", ["inversion", "retrograde"])

    degree_shift = 0
    if context and "progression_root_degree" in context:
        raw = chord.degree - context["progression_root_degree"]
        degree_shift = _wrap_degree_diff(raw)

    def _transformed_statement(prev_transform: Optional[str]) -> tuple[list[int], list[float], Optional[list[bool]]]:
        """One retransformed pass of the motif, avoiding an immediate repeat
        of the previous repetition's transform when the pool allows it.

        Unified (Finding 0, scoped separately from Phase C): previously this
        called three independent functions -- apply_transform (pitch),
        apply_rhythm_transform (rhythm), apply_rests_transform (rests) --
        none of which recognized transpose_up/transpose_down/
        retrograde_inversion/expand/compress, all of which are valid
        TransformLiteral schema values. Any pool containing one of those
        silently did nothing when chosen: no error, no log, just an
        unchanged repetition indistinguishable from a deliberate one. Now
        routes through motif.py's transform() -- the canonical, complete
        implementation already used by the piece-level transform_sequence
        mechanism -- for every transform except two that transform() can't
        (or, for one of them, must not) handle:

        - "sequence": harmony-aware (needs scale_tones + degree_shift from
          THIS chord's position in the progression), which has no place in
          transform()'s signature. Stays a melody.py-side special case,
          unchanged from before.
        - "original" / no transform chosen: transform() raises
          ValueError("Unknown transform: 'original'") -- it has no no-op
          case, because motif.py's other caller (the piece-level
          transform_sequence mechanism) handles "original" as a sentinel
          BEFORE ever calling transform(), not inside it. Here, the only
          reason "original" appearing in a transform_pool has ever worked
          is that the OLD three-function split's fallthrough (`else:
          return list(intervals)`) happened to produce the right answer by
          accident. That fallthrough is exactly what's being removed, so
          "original" needs its own explicit no-op case now, or a piece
          using it in transform_pool would start crashing instead of
          silently working -- a real regression risk, caught during
          scoping, not after.

        A real, deliberate behavior change from unifying (not a bug in
        this change): motif.py's shuffle reorders intervals+rhythm+rests
        TOGETHER as one paired shuffle. The old split-call approach
        couldn't do that -- neither apply_transform nor
        apply_rhythm_transform had a "shuffle" case for rhythm/rests, so
        pitch reordered while rests stayed in original position: the
        WRONG notes could end up treated as the ones to skip. This is
        NOT an audible-duration change, though -- generate_develop always
        takes a note's actual duration from the external rhythm_events
        grid (see the final MelodyNote construction below: `note, _ =
        motif_notes[statement_idx]` discards the motif's own rhythm
        value explicitly). The observable consequence of correct pairing
        here is which pitches survive a rest-bearing motif's shuffle, not
        how long they last.
        """
        choices = pool
        if pool and len(pool) > 1 and prev_transform is not None:
            choices = [t for t in pool if t != prev_transform] or pool
        transform_name = rng.choice(choices) if choices else None

        if not transform_name or transform_name == "original":
            return base_intervals, base_rhythm, base_rests, transform_name

        if transform_name == "sequence":
            iv = apply_transform(
                base_intervals, transform_name, rng=rng,
                scale_tones=scale_tones, degree_shift=degree_shift,
            )
            return iv, base_rhythm, base_rests, transform_name

        # Sub-seed derived from the live rng, not the outer `seed` param
        # directly -- keeps transform()'s internal shuffle randomness
        # deterministic without correlating every shuffle to the same
        # draw as the pool's transform-name choice.
        sub_seed = rng.randint(0, 2**31 - 1)
        source = Motif(intervals=base_intervals, rhythm=base_rhythm, rests=base_rests)
        transformed = apply_motif_transform(source, transform_name, seed=sub_seed)
        return transformed.intervals, transformed.rhythm, transformed.rests, transform_name

    notes_out = []
    start = _pick_start_note(chord_tones, scale_tones, prev_note)
    motif_notes: list[tuple[int, float]] = []
    statement_idx = 0
    last_transform: Optional[str] = None

    melodic_arc = context.get("melodic_arc") if context else None
    apex_pitch = context.get("apex_pitch") if context else None
    apex_position = (melodic_arc.get("apex_position", 0.7) if melodic_arc else 0.7)
    is_cadential_chord = bool(context and context.get("is_cadential_chord"))

    # Hard ceiling for augmentation/diminution's real-timing playback below
    # (see that branch) -- this call's total span, so a stretched statement
    # gets clamped to fit exactly, the same discipline chord-boundary
    # slicing already applies elsewhere (e.g. _slice_events_into_window).
    section_total_beats = (
        rhythm_events[-1].start_beat + rhythm_events[-1].duration_beats
        if rhythm_events else 0.0
    )

    ev_idx = 0
    n_events = len(rhythm_events)
    while ev_idx < n_events:
        ev = rhythm_events[ev_idx]

        if ev.is_rest or (rest_probability > 0 and rng.random() < rest_probability):
            notes_out.append(MelodyNote(None, ev.start_beat, ev.duration_beats, is_rest=True))
            ev_idx += 1
            continue

        # Out of pre-built motif notes — retile a fresh (re-transformed)
        # statement, continuing the pitch line from wherever the last one
        # ended rather than resetting to the chord tone anchor every time.
        if statement_idx >= len(motif_notes):
            result = _transformed_statement(last_transform)
            iv, rh, rs = result[0], result[1], result[2]
            last_transform = result[3] if len(result) > 3 else None
            anchor = motif_notes[-1][0] if motif_notes else start
            # prefer_neighbor_fold is only active when melodic_arc is
            # absent (see the fuller explanation a few lines down, at the
            # motif_to_notes call) -- compute it here too since the
            # register-health pull just below needs to know before the
            # apex/cadence block runs.
            arc_bias_active = melodic_arc is not None

            if not arc_bias_active and motif_notes:
                # Register-health restoring pull, companion to
                # prefer_neighbor_fold (see motif_to_notes' docstring):
                # neighbor-folding an out-of-bounds note keeps it close to
                # its immediate predecessor but supplies NO pull back
                # toward the register's center, so repeated corrections
                # across many CHAINED statements (this statement's anchor
                # is the previous one's last note) can lock the whole line
                # onto one corner of the register instead of just fixing
                # the single note that triggered a fold. Measured directly
                # on a real piece: without this pull, out-of-bounds
                # corrections grew from 24 to 52 over the piece, and 59%
                # of a 352-note melody ended up on just two adjacent
                # pitches near the register floor (vs 22%, spread across
                # more pitches, before prefer_neighbor_fold existed at
                # all) -- a piece-wide "gravity well" invisible in any
                # single statement, only visible in the aggregate.
                # A mild, CAPPED degree-nudge toward center when the
                # anchor is already sitting near a wall -- not a hard
                # reset -- restores the same restoring force center-fold
                # always provided, without reintroducing the within-
                # statement forced leaps prefer_neighbor_fold exists to
                # avoid: an anchor that's healthily centered already gets
                # left alone (directed_anchor_shift is a no-op at zero
                # distance), and even a wall-hugging one only moves by
                # ANCHOR_SHIFT_MAX_STEP diatonic steps, not straight to
                # the center.
                register_center = (MELODY_OCTAVE_BOTTOM + MELODY_OCTAVE_TOP) // 2
                wall_margin = 4
                if (anchor <= MELODY_OCTAVE_BOTTOM + wall_margin
                        or anchor >= MELODY_OCTAVE_TOP - wall_margin):
                    anchor = directed_anchor_shift(
                        anchor, register_center, scale_tones,
                        position_t=0.0, apex_position=1.0,
                    )

            # Apex/cadence bias (Phase 4 of the apex/goal-tone build).
            # develop has no per-note candidate list to weight the way
            # lyrical/generative do -- motif_to_notes builds each
            # retiled statement deterministically from wherever the
            # anchor sits, so bias here means nudging THIS anchor before
            # the statement gets built from it, cascading through every
            # note of the next statement. See melodic_shape.py's Phase 4
            # module note for why this is directed_anchor_shift, not
            # apex_weighted_candidates. Absent melodic_arc, `anchor` is
            # completely unchanged from before this phase existed --
            # both branches below (normal and augmentation/diminution)
            # consume whatever `anchor` holds without needing to know
            # whether it was shifted.
            if apex_pitch is not None:
                position_t = _position_t_from_context(context, ev.start_beat)
                anchor = directed_anchor_shift(
                    anchor, apex_pitch, scale_tones, position_t, apex_position,
                )
            if melodic_arc and is_cadential_chord:
                # Cadence should pull the LAST sounding note of this
                # statement toward resolution, not just where the
                # statement starts. The transformed motif walks
                # net_degree_shift diatonic steps from its first note to
                # its last sounding one (rests still consume a slot in
                # the interval sequence but don't sound, so the "last"
                # one is the last non-rest index, not necessarily the
                # final slot) -- shifting the anchor straight toward the
                # resolution pitch only controls the START, and that
                # walk can undo the shift entirely by the time the
                # statement actually ends. Confirmed by statistics, not
                # inspection: an earlier version of this shifted toward
                # the resolution pitch directly and measurably made the
                # final note LAND FARTHER from resolution on average
                # than doing nothing at all.
                resolution_pitch = _cadence_resolution_pitch(chord, chord_tones, anchor)
                last_idx = _last_sounding_index(iv, rs)
                net_degree_shift = sum(iv[:last_idx + 1]) if last_idx is not None else 0
                pcs = pitch_classes(scale_tones)
                resolution_degree = pitch_to_degree(resolution_pitch, pcs)
                adjusted_target = degree_to_pitch(resolution_degree - net_degree_shift, pcs)
                anchor = directed_anchor_shift(
                    anchor, adjusted_target, scale_tones,
                    position_t=0.0, apex_position=1.0,  # always-approach, see docstring
                )

            # Cadence-pull's math (just above, when it fires) predicts this
            # statement's last note by assuming register-folding only ever
            # shifts pitch by whole octaves -- the stronger neighbor-fold
            # fallback can break that prediction (see motif_to_notes'
            # prefer_neighbor_fold docstring). Scoping this off ONLY on the
            # cadential chord's own statement isn't enough: this statement's
            # `anchor` is literally the previous statement's last rendered
            # pitch (a few lines up), and directed_anchor_shift only nudges
            # by a capped number of degrees from wherever the anchor
            # already sits -- so a PRECEDING, non-cadential statement's
            # altered ending pitch changes the anchor the cadential
            # statement starts from, and the capped nudge can't fully
            # absorb that (measured: scoping to only the cadential call
            # made the regression WORSE, not better -- confirming the
            # contamination flows through anchor-chaining, not just the
            # cadential call itself). Any statement in a melodic_arc-
            # bearing progression can feed a later cadential one, so the
            # flag stays off for the whole progression whenever
            # melodic_arc is set at all, not just at the cadential moment.
            motif_notes = motif_to_notes(
                anchor, iv, rh, scale_tones, chord_tones,
                MELODY_OCTAVE_BOTTOM, MELODY_OCTAVE_TOP, rests=rs,
                prefer_neighbor_fold=not arc_bias_active,
            )
            statement_idx = 0
            if not motif_notes:
                # Degenerate motif (e.g. all-rest) — fall back honestly
                # rather than looping forever.
                candidates = chord_tones if chord_tones else scale_tones
                note = rng.choice(candidates) if candidates else 60
                vel = int(base_velocity * ev.velocity_scale)
                notes_out.append(MelodyNote(note, ev.start_beat, ev.duration_beats, vel))
                ev_idx += 1
                continue

            if last_transform in ("augmentation", "diminution"):
                # Real timing, not a relabeled grid onset. Augmentation/
                # diminution are supposed to mean the same notes at twice
                # or half the rate -- genuinely taking twice or half the
                # time, the same way Bach's actual technique does, not a
                # doubled duration number nobody ever plays. Drive this
                # whole statement's timing from the TRANSFORMED motif's
                # own (scaled) rhythm directly, starting at this onset,
                # instead of consuming rhythm_events one-for-one.
                #
                # motif_notes (above) already dropped rest slots' timing
                # entirely -- motif_to_notes with rests=rs never returns
                # a duration for a rest, so summing motif_notes' own
                # durations would silently compress the statement's true
                # span whenever it has any rests. Recomputing with
                # rests=None gets one entry per slot (sounding AND rest)
                # so real elapsed time is correct either way; the rests
                # mask is reapplied here to decide what actually sounds.
                all_slot_notes = motif_to_notes(
                    anchor, iv, rh, scale_tones, chord_tones,
                    MELODY_OCTAVE_BOTTOM, MELODY_OCTAVE_TOP, rests=None,
                    prefer_neighbor_fold=not arc_bias_active,
                )
                t = ev.start_beat
                vel = int(base_velocity * ev.velocity_scale)
                for i, (note_pitch, dur) in enumerate(all_slot_notes):
                    if t >= section_total_beats - 1e-9:
                        break
                    dur = min(dur, section_total_beats - t)
                    is_rest_slot = rs is not None and i < len(rs) and rs[i]
                    if not is_rest_slot:
                        notes_out.append(MelodyNote(note_pitch, t, dur, vel))
                    t += dur
                statement_idx = len(motif_notes)  # fully consumed this pass
                t_capped = min(t, section_total_beats)
                while ev_idx < n_events and rhythm_events[ev_idx].start_beat < t_capped - 1e-9:
                    ev_idx += 1
                continue

        note, _ = motif_notes[statement_idx]
        statement_idx += 1
        vel = int(base_velocity * ev.velocity_scale)
        notes_out.append(MelodyNote(note, ev.start_beat, ev.duration_beats, vel))
        ev_idx += 1

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
    note_length_range: Optional[tuple[float, float]] = None,
    note_length_quantum: float = 0.25,
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

    # Phase B4: a motif can declare its own melodic_scale, independent of
    # the piece's harmonic mode (e.g. a blues/pentatonic melody scale over
    # ordinary diatonic I-IV-V7 harmony). Falls back to the piece's mode
    # when absent -- every motif without this field behaves exactly as
    # before it existed. Chord/Roman-numeral resolution is untouched by
    # this: chords are already resolved (VoicedChord objects passed in)
    # using the piece's true mode before generate_melody ever runs, so
    # this only ever affects which scale the MELODY line is quantized to.
    melodic_scale = None
    if motif:
        melodic_scale = motif.get("melodic_scale") if isinstance(motif, dict) \
            else getattr(motif, "melodic_scale", None)
    scale_tones = get_scale_tones(key, melodic_scale or mode, octave_bottom, octave_top)
    chord_tones = get_chord_tones_in_register(chord, octave_bottom, octave_top)

    # Use prosodic rhythm if provided, otherwise get_pattern
    if rhythm_events_override is not None:
        rhythm_events = rhythm_events_override
    else:
        rhythm_events = get_pattern(total_beats, density=density, voice_type="melody",
                                    groove=groove, beats_per_bar=beats_per_bar, seed=seed,
                                    note_length_range=note_length_range,
                                    note_length_quantum=note_length_quantum)

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
    # fold into the melody register (centered fold, not nearest-wall).
    anchor = prev.last_pitch + (4 if direction == "up" else -4)
    anchor = fold_to_register(anchor, MELODY_OCTAVE_BOTTOM, MELODY_OCTAVE_TOP)
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
    octave_bottom: int = MELODY_OCTAVE_BOTTOM,
    octave_top: int = MELODY_OCTAVE_TOP,
    rhythm_events_override: Optional[list] = None,
    fugal_techniques: Optional[dict] = None,
    rest_probability: float = 0.0,
    piece_ctx: Optional[object] = None,
    arc: Optional[str] = None,
    note_length_range: Optional[tuple[float, float]] = None,
    note_length_quantum: float = 0.25,
    melodic_arc: Optional[dict] = None,
    progression_cycle_length: Optional[int] = None,
) -> list[MelodyNote]:
    """
    Generate a continuous melodic line across a full chord progression.
    Maintains note continuity between chords.

    Args:
        bars_per_chord: Float (uniform) or list[float] (per-chord durations).
        section_name: Name of section for context-aware generation.
        rhythm_events_override: Pre-computed rhythm events for the FULL progression.
            When provided, events are sliced per chord by beat range.
        fugal_techniques: Optional dict of fugal-development controls:
            - motif_transform (str): applies a motif.py transform (inversion,
              retrograde, augmentation, etc.) to the subject before generation.
            - stretto_compression (float): scales the subject's rhythm values
              by this factor (e.g. 0.5 = twice as fast).
            - subject_fragmentation (int): truncates the subject to its first
              N notes, for episodic development.
            - canonic_imitation (bool) + canon_interval (float, beats):
              delays this voice's entire generated line by canon_interval
              beats (silence beforehand), trimming anything that would
              land past the progression's total length. Mirrors
              VoiceModel.canon_offset, which does the same thing for peer
              voices (section.voices[1:]) at the generator.py level --
              this is the equivalent for the lead voice, via section-level
              fugal_techniques.
        piece_ctx: Optional PieceContext for cross-section memory. When provided
            (with arc), the opening note of the FIRST chord is biased relative to
            the previous section's ending contour. Only the section opening is
            affected; normal generation takes over afterward.
        arc: The section's declared arc (used only for the opening bias).
        melodic_arc: Optional apex/goal-tone config (Phase 2 of the
            apex/goal-tone build — see melodic_shape.py), e.g.
            {"apex_degree": 4, "apex_position": 0.7}. Absent (the
            default) means no apex or cadence bias at all — every call
            site that doesn't pass this behaves exactly as before this
            feature existed. Wired into all four behaviors (generative,
            lyrical, sparse, develop) — see schemas.py's MelodicArcModel
            docstring for the same fact stated the correct way.
        progression_cycle_length: The ORIGINAL (untiled) progression
            length, for cadence detection (Phase 0's "resolve every
            cycle" decision) — REQUIRED if melodic_arc's
            resolve_every_cycle is True, since `chords` here is already
            tiled (see resolved_progression() in schemas.py) and carries
            no memory of how long one repeat was. resolve_every_cycle
            False (the default) ignores this entirely and treats `chords`
            as a single cycle — cadence fires once, on the true final
            chord: a vamp that keeps its groove through every repeat and
            only resolves when the section actually ends.
            resolve_every_cycle True fires cadence at every repeat
            instead — a hook that resolves each time it comes around.
            Both are real (see melodic_shape.py's module docstring for
            which songs motivated keeping both); this single field is
            the actual toggle between them, not a separate knob a caller
            could set inconsistently with melodic_arc's own declared intent.

    Returns:
        Flat list of MelodyNote spanning the entire progression
    """
    # Normalize to list
    if isinstance(bars_per_chord, (int, float)):
        bpc_list = [float(bars_per_chord)] * len(chords)
    else:
        bpc_list = list(bars_per_chord)

    # Section-wide bar count, for apex/cadence bias's position_t (Phase 2
    # of the apex/goal-tone build) -- matches generator.py's
    # env_total_bars = max(1, int(round(total_beats / beats_per_bar)))
    # rounding convention exactly, so melody's dynamic-arc position and
    # its apex-bias position agree on what "N bars" means for this
    # section, not just on the position-within-those-bars formula
    # (already unified via rhythm.section_position_t).
    section_total_bars = max(1, int(round(sum(bpc_list))))
    # resolve_every_cycle is the single, actually-functional toggle here
    # (Phase 0's cadence decision) -- not a separate cycle_length knob a
    # caller could set inconsistently with what melodic_arc declares.
    # progression_cycle_length is only consulted when resolve_every_cycle
    # is explicitly True; otherwise cadence always means "the section's
    # true final chord," regardless of whether a cycle length was passed.
    resolve_every_cycle = bool(melodic_arc and melodic_arc.get("resolve_every_cycle"))
    effective_cycle_length = (
        progression_cycle_length
        if resolve_every_cycle and progression_cycle_length
        else len(chords)
    )

    # Resolve the apex target ONCE for the whole section, not per chord.
    # BUG CAUGHT DURING THIS PHASE'S OWN VERIFICATION (statistical check
    # across 30 seeds showed no measurable position effect, despite a
    # single-seed dump looking convincing): the first version of this
    # wiring called resolve_apex_pitch() fresh inside generate_lyrical on
    # every per-chord invocation, anchored to THAT call's own local
    # `current`. Since `current` reflects wherever the melody already is
    # at that point, the "target" silently followed the melody around
    # instead of being a fixed point to build toward -- defeating the
    # entire mechanism while still returning plausible-looking notes, so
    # nothing about it looked obviously broken until measured statistically.
    # Anchoring to the register's center instead gives a stable,
    # predictable octave placement independent of where the melody
    # happens to wander.
    apex_pitch = None
    if melodic_arc and melodic_arc.get("apex_degree") is not None:
        scale_tones_for_apex = get_scale_tones(key, mode, octave_bottom, octave_top)
        register_center = (octave_bottom + octave_top) // 2
        apex_pitch = resolve_apex_pitch(
            melodic_arc["apex_degree"], scale_tones_for_apex,
            octave_bottom, octave_top, anchor=register_center,
        )

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
            # Reference point for the "sequence" transform: root motion is
            # measured against this section's OPENING chord, not the
            # previous chord, so a repeating progression (e.g. two loops of
            # vi-ii-v-I) sequences consistently each time rather than
            # accumulating drift across loops.
            "progression_root_degree": chords[0].degree,
            # Register bounds for this voice, so per-note lookups (e.g.
            # generate_lyrical's next-chord biasing) stay inside the voice's
            # actual range instead of the global melody default.
            "octave_bottom": octave_bottom,
            "octave_top": octave_top,
            # Apex/goal-tone bias (Phase 2 of the apex/goal-tone build).
            # melodic_arc itself is just handed through unchanged; the
            # three fields below let a behavior function compute this
            # note's position_t via _position_t_from_context() without
            # needing to know beat_offset/total_bars are section-wide
            # concepts this per-chord call wouldn't otherwise have access
            # to (rhythm_events here are already chord-local).
            "melodic_arc": melodic_arc,
            "apex_pitch": apex_pitch,
            "section_total_bars": section_total_bars,
            "section_beat_offset": beat_offset,
            "beats_per_bar": beats_per_bar,
            # True exactly at the chord(s) Phase 0's cadence decision
            # identifies as cadential: every effective_cycle_length-th
            # chord. effective_cycle_length == len(chords) (the default,
            # cycle_length not passed) means this fires ONCE, on the
            # section's true final chord only -- a vamp/loop keeps its
            # groove through every repeat and only resolves when the
            # section actually ends. Passing the ORIGINAL (untiled)
            # progression length instead fires it at every repeat -- a
            # hook that resolves each time it comes around. Both are
            # real (see melodic_shape.py's module docstring); this is
            # the one place that decision is made, so every behavior's
            # notion of "is this cadential" means the same thing.
            "is_cadential_chord": (i % effective_cycle_length) == (effective_cycle_length - 1),
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
            octave_bottom=octave_bottom,
            octave_top=octave_top,
            groove=groove,
            beats_per_bar=beats_per_bar,
            swing=swing,
            seed=chord_seed,
            context=chord_context,
            rhythm_events_override=chord_rhythm,
            rest_probability=rest_probability,
            note_length_range=note_length_range,
            note_length_quantum=note_length_quantum,
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

    # ════════════════════════════════════════════════════════════
    # CANONIC IMITATION (offset voice entries like stretto)
    # Applied once, after the whole line is generated: shift every
    # note forward by canon_interval beats, then drop anything that
    # lands past the progression's total length. This mirrors the
    # already-working VoiceModel.canon_offset mechanism generator.py
    # applies to PEER voices (section.voices[1:]) -- same underlying
    # idea (delay this voice's entrance, trim the tail), just scoped
    # here to the LEAD voice via section-level fugal_techniques,
    # since peer voices already have their own per-voice canon_offset
    # field for the same purpose. Applying it as a post-pass (rather
    # than threading an offset through the per-chord loop above) keeps
    # every chord's own generation, and the prev_note continuity
    # tracking between chords, completely unaffected by the shift --
    # only the final presentation timing moves.
    # ════════════════════════════════════════════════════════════
    if canonic_imitation and canon_interval > 0:
        for n in all_notes:
            n.start_beat += canon_interval
        all_notes = [n for n in all_notes if n.start_beat < beat_offset]

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
