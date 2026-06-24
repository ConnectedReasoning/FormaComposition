"""
counterpoint.py — Intervals Engine
Generates a counterpoint voice against a melody using classical rules.

Supports:
  1st species  — note against note, strict consonance rules
  Free species — mixed rhythms, passing tones, suspensions, more musical

Register:
  above  — counterpoint voice sits above the melody (descant)
  below  — counterpoint voice sits below the melody (classical tenor/alto)

Rules implemented:
  - Consonance/dissonance classification
  - Forbidden parallel perfect 5ths and octaves
  - Forbidden direct (hidden) 5ths
  - Voice crossing prevention (configurable)
  - Stepwise motion preference
  - Post-leap stepwise recovery
  - Contrary motion preference
  - Dissonance resolution (passing tones on weak beats only)
  - Cadence approach rules (leading tone resolution)
"""

import random
from dataclasses import dataclass, field
from typing import Optional
from intervals.music.harmony import VoicedChord, CHROMATIC, MODES, key_to_midi_root
from intervals.music.melody import MelodyNote
from intervals.music.rhythm import get_pattern
from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from intervals.core.schemas import CounterpointModel

# ---------------------------------------------------------------------------
# Interval classification
# ---------------------------------------------------------------------------

# Intervals (mod 12) classified by consonance
PERFECT_CONSONANCES  = {0, 7, 12}   # unison, perfect 5th, octave
IMPERFECT_CONSONANCES = {3, 4, 8, 9} # minor 3rd, major 3rd, minor 6th, major 6th
CONSONANCES          = PERFECT_CONSONANCES | IMPERFECT_CONSONANCES
DISSONANCES          = {1, 2, 5, 6, 10, 11}  # 2nds, 4th, tritone, 7ths

def interval_class(a: int, b: int) -> int:
    """Return the interval class (0-12) between two MIDI notes."""
    return abs(a - b) % 12 if abs(a - b) % 12 <= 6 else 12 - (abs(a - b) % 12)


def raw_interval(a: int, b: int) -> int:
    """Return the raw semitone distance (not reduced mod 12)."""
    return abs(a - b)


def is_consonant(a: int, b: int) -> bool:
    ic = interval_class(a, b)
    return ic in CONSONANCES


def is_perfect_consonance(a: int, b: int) -> bool:
    ic = interval_class(a, b)
    return ic in PERFECT_CONSONANCES


def is_dissonant(a: int, b: int) -> bool:
    return not is_consonant(a, b)


# ---------------------------------------------------------------------------
# Motion classification
# ---------------------------------------------------------------------------

def motion_type(melody_prev: int, melody_curr: int,
                cp_prev: int,    cp_curr: int) -> str:
    """
    Classify the motion between two voices across one step.
    Returns: 'contrary' | 'similar' | 'oblique' | 'parallel'
    """
    md = melody_curr - melody_prev
    cd = cp_curr    - cp_prev

    if md == 0 and cd == 0:
        return "parallel"   # both stationary — technically parallel unison
    if md == 0 or cd == 0:
        return "oblique"
    if (md > 0 and cd < 0) or (md < 0 and cd > 0):
        return "contrary"
    if md == cd:
        return "parallel"
    return "similar"


# ---------------------------------------------------------------------------
# Rule checker
# ---------------------------------------------------------------------------

@dataclass
class RuleViolation:
    rule: str
    severity: str   # 'hard' (forbidden) | 'soft' (avoid if possible)
    description: str

    def __repr__(self):
        return f"[{self.severity.upper()}] {self.rule}: {self.description}"


def check_interval_rules(
    melody_note: int,
    cp_note: int,
    melody_prev: Optional[int],
    cp_prev: Optional[int],
    beat_position: float,
    beats_per_bar: int = 4,
    is_final: bool = False,
) -> list[RuleViolation]:
    """
    Check all interval and motion rules for a single counterpoint note.
    Returns a list of RuleViolation objects (empty = clean).
    """
    violations = []
    beat_in_bar = beat_position % beats_per_bar
    is_strong_beat = beat_in_bar < 1.0 or abs(beat_in_bar - (beats_per_bar / 2)) < 0.01

    # 1. Consonance on strong beats
    if is_strong_beat and is_dissonant(melody_note, cp_note):
        violations.append(RuleViolation(
            "dissonance_on_strong_beat", "hard",
            f"Interval {interval_class(melody_note, cp_note)} is dissonant on beat {beat_in_bar:.1f}"
        ))

    # 2. Unison — only at phrase start/end
    if interval_class(melody_note, cp_note) == 0 and not is_final and beat_position > 0:
        violations.append(RuleViolation(
            "interior_unison", "soft",
            "Unison should only appear at phrase start or cadence"
        ))

    if melody_prev is not None and cp_prev is not None:
        mt = motion_type(melody_prev, melody_note, cp_prev, cp_note)

        # 3. Parallel perfect consonances
        if mt == "parallel" and is_perfect_consonance(melody_note, cp_note):
            if is_perfect_consonance(melody_prev, cp_prev):
                violations.append(RuleViolation(
                    "parallel_perfects", "hard",
                    f"Parallel {interval_class(melody_note, cp_note)}-semitone intervals forbidden"
                ))

        # 4. Direct (hidden) 5ths — similar motion into a perfect 5th
        # Exempt final cadence note (Bach does this at closes)
        if mt == "similar" and interval_class(melody_note, cp_note) == 7 and not is_final:
            violations.append(RuleViolation(
                "direct_fifth", "hard",
                "Direct (hidden) 5th: similar motion into perfect 5th"
            ))

        # 5. Direct octaves — exempt final cadence note
        if mt == "similar" and interval_class(melody_note, cp_note) == 0 and not is_final:
            violations.append(RuleViolation(
                "direct_octave", "hard",
                "Direct (hidden) octave: similar motion into octave"
            ))

        # 6. Contrary motion preferred — penalise parallel/similar
        if mt == "parallel":
            violations.append(RuleViolation(
                "parallel_motion", "soft",
                "Parallel motion — contrary motion preferred"
            ))

    return violations


def count_hard_violations(violations: list[RuleViolation]) -> int:
    return sum(1 for v in violations if v.severity == "hard")


def count_soft_violations(violations: list[RuleViolation]) -> int:
    return sum(1 for v in violations if v.severity == "soft")


# ---------------------------------------------------------------------------
# Time-position lookups (for rhythmically independent voices)
# ---------------------------------------------------------------------------
#
# Once a counterpoint voice has its own rhythm grid, "what is the melody
# (or another voice) doing right now" can no longer be answered by sharing
# an index into melody_notes — a voice's own onset may fall in the middle
# of a sustained melody note, in a melody rest, or past the melody's last
# note. These two helpers answer that by actual beat position instead.

def note_sounding_at(notes: list, beat: float) -> Optional[int]:
    """
    Return the MIDI pitch of `notes` (any list of objects exposing
    midi_note / start_beat / duration_beats / is_rest — MelodyNote or
    CounterpointNote both qualify) that is actually sounding at `beat`.

    A note is sounding if start_beat <= beat < start_beat + duration_beats.
    Returns None if the voice is resting, hasn't started, or has already
    finished its last note by `beat`. Assumes `notes` is sorted ascending
    by start_beat, which holds for every voice this engine generates.
    """
    for n in notes:
        if n.midi_note is None or n.is_rest:
            continue
        start = n.start_beat
        end = start + n.duration_beats
        if start - 1e-6 <= beat < end - 1e-6:
            return n.midi_note
    return None


def last_sounding_before(notes: list, beat: float) -> Optional[int]:
    """
    Return the pitch of the most recent note in `notes` that began at or
    before `beat`, even if it has already finished sounding (i.e. `beat`
    falls in a gap or rest). Used as a harmonic reference when a
    rhythmically independent counterpoint onset lands where the melody
    has gone quiet, so the candidate scorer still has *something* to
    check consonance against rather than no constraint at all.
    """
    last = None
    for n in notes:
        if n.midi_note is None or n.is_rest:
            continue
        if n.start_beat <= beat + 1e-6:
            last = n.midi_note
        else:
            break
    return last


# ---------------------------------------------------------------------------
# Data class
# ---------------------------------------------------------------------------

@dataclass
class CounterpointNote:
    """A single counterpoint note."""
    midi_note: Optional[int]
    start_beat: float
    duration_beats: float
    velocity: int = 60
    is_rest: bool = False
    violations: list[RuleViolation] = field(default_factory=list)

    def __repr__(self):
        if self.is_rest:
            return f"CP(REST beat={self.start_beat:.2f} dur={self.duration_beats:.2f})"
        name = CHROMATIC[self.midi_note % 12] if self.midi_note else "?"
        v = f" [{len(self.violations)}v]" if self.violations else ""
        return f"CP({name}{self.midi_note} beat={self.start_beat:.2f} dur={self.duration_beats:.2f}{v})"


# ---------------------------------------------------------------------------
# Scale helpers
# ---------------------------------------------------------------------------

def get_scale_tones_in_register(
    key: str, mode: str,
    bottom: int, top: int
) -> list[int]:
    """All scale tones in a register."""
    intervals = MODES[mode.lower()]
    root = key_to_midi_root(key, octave=2)
    tones = []
    n = root
    while n <= top + 12:
        for i in intervals:
            note = n + i
            if bottom <= note <= top:
                tones.append(note)
        n += 12
    return sorted(set(tones))


def leading_tone(key: str, mode: str) -> int:
    """Return the leading tone pitch class for a key/mode."""
    intervals = MODES[mode.lower()]
    root_pc = CHROMATIC.index(key.strip())
    # Leading tone = 7th scale degree
    return (root_pc + intervals[6]) % 12


# ---------------------------------------------------------------------------
# Candidate scorer
# ---------------------------------------------------------------------------

def score_candidate(
    candidate: int,
    melody_note: int,
    melody_prev: Optional[int],
    cp_prev: Optional[int],
    scale_tones: list[int],
    beat_position: float,
    beats_per_bar: int,
    register: str,
    is_final: bool = False,
    rng=None,
    against_notes: Optional[list[int]] = None,
) -> float:
    """
    Score a candidate counterpoint note. Lower = better.
    Returns a float penalty score.

    against_notes: list of sounding MIDI pitches from all previously generated
    voices at this beat position.  The scorer checks interval rules against
    each of them, not just the primary melody note.
    """
    score = 0.0

    # Hard rule violations — heavy penalty
    violations = check_interval_rules(
        melody_note, candidate, melody_prev, cp_prev,
        beat_position, beats_per_bar, is_final
    )
    score += count_hard_violations(violations) * 1000.0
    score += count_soft_violations(violations) * 10.0

    # Additional interval checks against all other sounding voices
    if against_notes:
        for other in against_notes:
            if other == melody_note:
                continue  # already checked above
            add_viols = check_interval_rules(
                other, candidate, None, cp_prev,
                beat_position, beats_per_bar, is_final
            )
            score += count_hard_violations(add_viols) * 500.0
            score += count_soft_violations(add_viols) * 5.0

    # Prefer imperfect consonances (3rds, 6ths) over perfect (5ths, octaves)
    ic = interval_class(melody_note, candidate)
    if ic in IMPERFECT_CONSONANCES:
        score -= 5.0
    elif ic in PERFECT_CONSONANCES and ic != 0:
        score += 2.0

    # Prefer stepwise motion in counterpoint voice
    if cp_prev is not None:
        leap = abs(candidate - cp_prev)
        if leap <= 2:
            score -= 8.0    # stepwise — strongly preferred
        elif leap <= 4:
            score -= 2.0    # small leap — ok
        elif leap <= 7:
            score += 5.0    # large leap — penalise
        else:
            score += 15.0   # very large leap — avoid

    # Prefer contrary motion
    if cp_prev is not None and melody_prev is not None:
        mt = motion_type(melody_prev, melody_note, cp_prev, candidate)
        if mt == "contrary":
            score -= 10.0
        elif mt == "oblique":
            score -= 3.0
        elif mt == "similar":
            score += 3.0
        elif mt == "parallel":
            score += 8.0

    # Register enforcement — keep voice in correct relation to melody
    if register == "below" and candidate >= melody_note:
        score += 50.0   # voice crossing penalty
    if register == "above" and candidate <= melody_note:
        score += 50.0

    # Prefer scale tones
    if candidate not in scale_tones:
        score += 20.0

    # Slight randomness to avoid mechanical repetition
    _rng = rng if rng is not None else random.Random()
    score += _rng.uniform(0.0, 1.5)

    return score


# ---------------------------------------------------------------------------
# 1st species generator
# ---------------------------------------------------------------------------

def generate_first_species(
    melody_notes: list[MelodyNote],
    key: str,
    mode: str,
    register: str = "below",
    beats_per_bar: int = 4,
    velocity: int = 60,
    seed: Optional[int] = None,
    against_notes: Optional[list[int]] = None,
    against_voices: Optional[list[list]] = None,
) -> list[CounterpointNote]:
    """
    Generate strict 1st species counterpoint (note against note).
    One counterpoint note per melody note, consonant on every beat.

    Rhythm is intentionally NOT made independent here. Real first-species
    counterpoint is defined as note-against-note with the cantus firmus —
    the 1:1 rhythmic lockstep is the species, not a missing feature. Voices
    that should move independently in time belong in 'free' species (see
    generate_free_species), which is where FEATURE_REQUEST_counterpoint_
    rhythmic_independence.md's fix lives. If ratio-based first species
    (2:1, 4:1 against the cantus firmus) is ever wanted, that's a separate,
    deliberate addition — not a default.

    Args:
        melody_notes:   List of MelodyNote (non-rest) from melody.py
        key:            Key center
        mode:           Mode name
        register:       'above' | 'below'
        beats_per_bar:  Time signature numerator
        velocity:       Base MIDI velocity
        seed:           Random seed
        against_notes:  Sounding pitches from all prior voices (multi-voice awareness)
        against_voices: Optional list of prior voices' note lists. Accepted for a
                        uniform call signature with generate_free_species; flattened
                        into a coarse pitch pool here rather than checked by exact
                        time position, since this species is rhythmically locked to
                        the melody anyway (so "what's sounding now" is unambiguous —
                        it's whatever the prior voice's same-index note is, which a
                        flattened pool already approximates well enough).

    Returns:
        List of CounterpointNote
    """
    if seed is not None:
        rng = random.Random(seed)
    else:
        rng = random.Random()

    if against_voices:
        flattened = [
            n.midi_note for voice in against_voices for n in voice
            if not n.is_rest and n.midi_note is not None
        ]
        against_notes = (against_notes or []) + flattened

    # Register ranges
    if register == "below":
        bottom, top = 48, 69   # C3–A4
    else:
        bottom, top = 67, 88   # G4–E6

    scale_tones = get_scale_tones_in_register(key, mode, bottom, top)
    sounding = [n for n in melody_notes if not n.is_rest and n.midi_note is not None]

    if not sounding:
        return []

    result = []
    cp_prev = None
    melody_prev = None
    total = len(sounding)

    for i, mn in enumerate(sounding):
        is_final = (i == total - 1)
        beat = mn.start_beat

        # At final note: strongly prefer unison, octave, or 5th (cadence)
        if is_final:
            cadence_candidates = [
                n for n in scale_tones
                if interval_class(mn.midi_note, n) in {0, 7, 12}
            ]
            if not cadence_candidates:
                cadence_candidates = scale_tones

        candidates = cadence_candidates if is_final else scale_tones

        # Score all candidates
        scored = []
        for c in candidates:
            s = score_candidate(
                c, mn.midi_note, melody_prev, cp_prev,
                scale_tones, beat, beats_per_bar, register, is_final,
                rng=rng,
                against_notes=against_notes,
            )
            scored.append((s, c))

        scored.sort(key=lambda x: x[0])

        # Pick best candidate
        best_score, best = scored[0]
        violations = check_interval_rules(
            mn.midi_note, best, melody_prev, cp_prev,
            beat, beats_per_bar, is_final
        )

        result.append(CounterpointNote(
            midi_note=best,
            start_beat=beat,
            duration_beats=mn.duration_beats,
            velocity=velocity,
            violations=violations,
        ))

        cp_prev = best
        melody_prev = mn.midi_note

    return result


# ---------------------------------------------------------------------------
# Free species generator
# ---------------------------------------------------------------------------

def generate_free_species(
    melody_notes: list[MelodyNote],
    key: str,
    mode: str,
    register: str = "below",
    beats_per_bar: int = 4,
    velocity: int = 60,
    dissonance: str = "passing",   # 'none' | 'passing' | 'free'
    seed: Optional[int] = None,
    against_notes: Optional[list[int]] = None,
    against_voices: Optional[list[list]] = None,
    rhythm_density: str = "medium",
    groove: Optional[str] = None,
) -> list[CounterpointNote]:
    """
    Generate free species counterpoint — mixed note values, passing tones,
    suspensions, and more organic voice leading.

    Unlike 1st species, this voice generates its OWN rhythm grid (onsets
    and durations) independently of melody_notes, then selects pitches
    against whatever the melody (and any prior voices) is actually
    sounding at each of its own onset times. This is what makes the line
    sound like real counterpoint rather than a harmonized doubling of the
    melody: notes can land off the melody's beats, rest while the melody
    moves, and keep moving while the melody holds or rests.

    Args:
        melody_notes:   List of MelodyNote from melody.py
        key:            Key center
        mode:           Mode name
        register:       'above' | 'below'
        beats_per_bar:  Time signature numerator
        velocity:       Base MIDI velocity
        dissonance:     How freely to use dissonance:
                         'none'    — consonances only (like strict 1st species)
                         'passing' — dissonance allowed on weak beats as passing tones
                         'free'    — dissonance with resolution, more expressive
        seed:           Random seed
        against_notes:  Flat pitch pool from prior voices (coarse, time-agnostic;
                         kept for back-compat / standalone calls).
        against_voices: List of prior voices' note lists (MelodyNote or
                        CounterpointNote). Preferred over against_notes — each
                        candidate is checked against what every prior voice is
                        ACTUALLY sounding at this voice's own onset time, via
                        note_sounding_at(), not a flattened whole-section pool.
        rhythm_density: 'sparse' | 'medium' | 'full' — passed to
                        rhythm.get_pattern() to control how many of this
                        voice's own onsets are active.
        groove:         Optional named groove (see rhythm.GROOVES) for this
                        voice's onset pattern. None → ungrooved density grid.

    Returns:
        List of CounterpointNote
    """
    if seed is not None:
        rng = random.Random(seed)
    else:
        rng = random.Random()

    if register == "below":
        bottom, top = 48, 69
    else:
        bottom, top = 67, 88

    scale_tones = get_scale_tones_in_register(key, mode, bottom, top)
    sounding_melody = [n for n in melody_notes if not n.is_rest and n.midi_note is not None]

    if not sounding_melody:
        return []

    # The melody's full span is the harmonic backdrop this voice plays
    # against; its own rhythm shouldn't run past it.
    total_beats = max(n.start_beat + n.duration_beats for n in melody_notes)

    # ── 1. Generate this voice's own rhythm grid, independent of the melody ──
    rhythm_seed = seed if seed is not None else rng.randint(0, 10_000_000)
    cp_rhythm = get_pattern(
        total_beats,
        density=rhythm_density,
        voice_type="melody",
        groove=groove,
        beats_per_bar=beats_per_bar,
        seed=rhythm_seed,
    )
    # Clip to the melody's span — a groove/density grid tiles past the end.
    clipped = []
    for ev in cp_rhythm:
        if ev.start_beat >= total_beats - 1e-6:
            continue
        ev.duration_beats = min(ev.duration_beats, total_beats - ev.start_beat)
        clipped.append(ev)
    onsets = [ev for ev in clipped if not ev.is_rest]

    if not onsets:
        return []

    result = []
    cp_prev = None
    melody_prev = None
    total = len(onsets)
    prev_was_dissonant = False

    for i, ev in enumerate(onsets):
        beat = ev.start_beat
        is_final = (i == total - 1)
        beat_in_bar = beat % beats_per_bar
        is_strong = beat_in_bar < 1.0 or abs(beat_in_bar - beats_per_bar / 2) < 0.01

        # What is the melody actually doing right now? Not "the i-th melody
        # note" — this voice has its own clock. If the melody is between
        # notes or resting, fall back to the last pitch it sounded so we
        # still have a harmonic reference to check consonance against.
        melody_now = note_sounding_at(sounding_melody, beat)
        if melody_now is None:
            melody_now = last_sounding_before(sounding_melody, beat)
        if melody_now is None:
            melody_now = melody_prev  # nothing has sounded yet — rare edge case

        # What are prior voices (melody + any earlier counterpoint voices)
        # actually sounding at this exact beat, by time position?
        sounding_others: list[int] = []
        if against_voices:
            for voice in against_voices:
                p = note_sounding_at(voice, beat)
                if p is not None and p != melody_now:
                    sounding_others.append(p)
        if against_notes:
            sounding_others.extend(against_notes)

        if melody_now is None:
            # No harmonic reference exists yet at all (only possible if this
            # voice's rhythm starts before the melody's first note). Don't
            # fabricate rule checks against nothing — just stay in scale.
            candidates = scale_tones
        else:
            # Build candidate pool (same logic as before, now keyed off
            # melody_now instead of a same-index melody note).
            if dissonance == "none" or is_strong:
                candidates = [n for n in scale_tones if is_consonant(melody_now, n)]
            elif dissonance == "passing" and not is_strong:
                if cp_prev is not None:
                    passing = [n for n in scale_tones if abs(n - cp_prev) <= 2]
                    candidates = passing if passing else scale_tones
                else:
                    candidates = scale_tones
            else:
                # 'free' — all scale tones, dissonance must resolve
                if prev_was_dissonant and cp_prev is not None:
                    candidates = [n for n in scale_tones if abs(n - cp_prev) <= 2]
                else:
                    candidates = scale_tones

            if not candidates:
                candidates = scale_tones

            # Final note: cadence — prefer consonant approach
            if is_final:
                cadence = [n for n in candidates if interval_class(melody_now, n) in {0, 7, 4, 3}]
                if cadence:
                    candidates = cadence

        # Score candidates
        scored = []
        for c in candidates:
            s = score_candidate(
                c, melody_now if melody_now is not None else c,
                melody_prev, cp_prev,
                scale_tones, beat, beats_per_bar, register, is_final,
                rng=rng,
                against_notes=sounding_others,
            )
            scored.append((s, c))

        scored.sort(key=lambda x: x[0])
        _, best = scored[0]

        if melody_now is not None:
            violations = check_interval_rules(
                melody_now, best, melody_prev, cp_prev,
                beat, beats_per_bar, is_final
            )
        else:
            violations = []

        note_velocity = max(1, min(127, round(velocity * ev.velocity_scale)))

        result.append(CounterpointNote(
            midi_note=best,
            start_beat=beat,
            duration_beats=ev.duration_beats,
            velocity=note_velocity,
            violations=violations,
        ))
        prev_was_dissonant = melody_now is not None and is_dissonant(melody_now, best)
        cp_prev = best
        melody_prev = melody_now

    return result


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def generate_counterpoint(
    melody_notes: list[MelodyNote],
    key: str,
    mode: str,
    species: str = "free",
    register: str = "below",
    beats_per_bar: int = 4,
    velocity: int = 60,
    dissonance: str = "passing",
    seed: Optional[int] = None,
    *,
    cp_model: "Optional[CounterpointModel]" = None,
    against_notes: Optional[list[int]] = None,
    against_voices: Optional[list[list]] = None,
    rhythm_density: str = "medium",
    groove: Optional[str] = None,
) -> list[CounterpointNote]:
    """
    Generate a counterpoint voice against a melody.

    Args:
        melody_notes:   List of MelodyNote from melody.py
        key:            Key center e.g. "D"
        mode:           Mode name e.g. "dorian"
        species:        "first" | "free"
        register:       "above" | "below"
        beats_per_bar:  Time signature numerator
        velocity:       Base MIDI velocity
        dissonance:     For free species: "none" | "passing" | "free"
        seed:           Random seed
        cp_model:       Optional CounterpointModel instance.  When provided,
                        its fields override the individual keyword arguments so
                        the caller does not need to unpack the model manually.
        against_notes:  Sounding pitches from all prior voices in the section.
                        Used to avoid parallel fifths/octaves across all peers,
                        not just the primary melody. Time-agnostic; kept for
                        back-compat. Prefer against_voices for free species.
        against_voices: Note lists (MelodyNote/CounterpointNote) of all prior
                        voices this section, including the melody. Free species
                        uses these to check what each prior voice is actually
                        sounding at THIS voice's own onset time, rather than a
                        flattened whole-section pool. First species flattens
                        them internally (rhythm is locked to the melody there,
                        so exact time-position lookup isn't needed).
        rhythm_density: "sparse" | "medium" | "full" — free species only;
                        controls how active this voice's own rhythm grid is.
        groove:         Optional named groove (rhythm.GROOVES) for free
                        species' onset pattern. None → ungrooved density grid.

    Returns:
        List of CounterpointNote
    """
    # If a typed model is supplied, let it win over individual kwargs.
    if cp_model is not None:
        species        = cp_model.species
        register       = cp_model.cp_register
        beats_per_bar  = beats_per_bar  # not on CounterpointModel — caller supplies
        velocity       = cp_model.velocity
        dissonance     = cp_model.dissonance
        rhythm_density = cp_model.rhythm_density
        groove         = cp_model.groove

    if species == "first":
        return generate_first_species(
            melody_notes, key, mode, register, beats_per_bar, velocity, seed,
            against_notes=against_notes,
            against_voices=against_voices,
        )
    elif species == "free":
        return generate_free_species(
            melody_notes, key, mode, register, beats_per_bar,
            velocity, dissonance, seed,
            against_notes=against_notes,
            against_voices=against_voices,
            rhythm_density=rhythm_density,
            groove=groove,
        )
    else:
        raise ValueError(f"Unknown species: '{species}'. Choose 'first' or 'free'.")


def violation_report(notes: list[CounterpointNote]) -> dict:
    """
    Summarise rule violations across a counterpoint voice.
    Useful for debugging and validating 1st species output.
    """
    total = len([n for n in notes if not n.is_rest])
    hard  = sum(count_hard_violations(n.violations) for n in notes)
    soft  = sum(count_soft_violations(n.violations) for n in notes)
    types = {}
    for n in notes:
        for v in n.violations:
            types[v.rule] = types.get(v.rule, 0) + 1
    return {
        "total_notes": total,
        "hard_violations": hard,
        "soft_violations": soft,
        "violation_types": types,
        "clean": hard == 0,
    }


# ---------------------------------------------------------------------------
# Quick test / demo
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    from harmony import resolve_progression
    from melody  import generate_melody_for_progression

    print("=== Intervals Engine — counterpoint.py demo ===\n")

    key  = "D"
    mode = "dorian"
    prog = ["i", "VII", "iv", "v"]

    chords = resolve_progression(prog, key, mode, density="medium")
    melody = generate_melody_for_progression(
        chords, key, mode,
        behavior="lyrical",
        density="medium",
        bars_per_chord=2,
        seed=42,
    )

    sounding = [n for n in melody if not n.is_rest]
    print(f"Melody: {len(sounding)} sounding notes\n")

    # ── 1st species ──────────────────────────────────────────────────────
    for register in ("below", "above"):
        print(f"--- 1st species  register={register} ---")
        cp = generate_counterpoint(
            melody, key, mode,
            species="first",
            register=register,
            seed=7,
        )
        report = violation_report(cp)
        print(f"  Notes: {report['total_notes']}  "
              f"Hard violations: {report['hard_violations']}  "
              f"Soft: {report['soft_violations']}  "
              f"Clean: {report['clean']}")

        # Show first 6 pairs
        pairs = [(m, c) for m, c in zip(sounding, cp) if not c.is_rest][:6]
        for mn, cn in pairs:
            m_name = CHROMATIC[mn.midi_note % 12]
            c_name = CHROMATIC[cn.midi_note % 12]
            ic = interval_class(mn.midi_note, cn.midi_note)
            cons = "CONS" if is_consonant(mn.midi_note, cn.midi_note) else "DISS"
            print(f"    beat={mn.start_beat:5.1f}  melody={m_name}{mn.midi_note}  "
                  f"cp={c_name}{cn.midi_note}  interval={ic}  {cons}")
        print()

    # ── Free species ─────────────────────────────────────────────────────
    for dissonance in ("none", "passing", "free"):
        print(f"--- Free species  register=below  dissonance={dissonance} ---")
        cp = generate_counterpoint(
            melody, key, mode,
            species="free",
            register="below",
            dissonance=dissonance,
            seed=13,
        )
        report = violation_report(cp)
        notes_only = [n for n in cp if not n.is_rest]
        print(f"  Onsets: {len(cp)}  Notes: {report['total_notes']}  "
              f"Hard violations: {report['hard_violations']}  "
              f"Soft: {report['soft_violations']}")

        # Show first 6 onsets with their own independent timing — no longer
        # index-paired with the melody, since rhythm is generated separately.
        for cn in notes_only[:6]:
            c_name = CHROMATIC[cn.midi_note % 12]
            print(f"    beat={cn.start_beat:5.2f}  dur={cn.duration_beats:.2f}  "
                  f"cp={c_name}{cn.midi_note}")

        if report["violation_types"]:
            print(f"  Violation types: {report['violation_types']}")
        print()
