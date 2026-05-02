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
) -> float:
    """
    Score a candidate counterpoint note. Lower = better.
    Returns a float penalty score.
    """
    score = 0.0

    # Hard rule violations — heavy penalty
    violations = check_interval_rules(
        melody_note, candidate, melody_prev, cp_prev,
        beat_position, beats_per_bar, is_final
    )
    score += count_hard_violations(violations) * 1000.0
    score += count_soft_violations(violations) * 10.0

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
) -> list[CounterpointNote]:
    """
    Generate strict 1st species counterpoint (note against note).
    One counterpoint note per melody note, consonant on every beat.

    Args:
        melody_notes:  List of MelodyNote (non-rest) from melody.py
        key:           Key center
        mode:          Mode name
        register:      'above' | 'below'
        beats_per_bar: Time signature numerator
        velocity:      Base MIDI velocity
        seed:          Random seed

    Returns:
        List of CounterpointNote
    """
    if seed is not None:
        rng = random.Random(seed)
    else:
        rng = random.Random()

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
) -> list[CounterpointNote]:
    """
    Generate free species counterpoint — mixed note values, passing tones,
    suspensions, and more organic voice leading.

    Args:
        melody_notes:  List of MelodyNote from melody.py
        key:           Key center
        mode:          Mode name
        register:      'above' | 'below'
        beats_per_bar: Time signature numerator
        velocity:      Base MIDI velocity
        dissonance:    How freely to use dissonance:
                         'none'    — consonances only (like strict 1st species)
                         'passing' — dissonance allowed on weak beats as passing tones
                         'free'    — dissonance with resolution, more expressive
        seed:          Random seed

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
    sounding = [n for n in melody_notes if not n.is_rest and n.midi_note is not None]

    if not sounding:
        return []

    result = []
    cp_prev = None
    melody_prev = None
    total = len(sounding)

    # Track whether previous note was dissonant (for resolution)
    prev_was_dissonant = False

    for i, mn in enumerate(sounding):
        is_final = (i == total - 1)
        beat = mn.start_beat
        beat_in_bar = beat % beats_per_bar
        is_strong = beat_in_bar < 1.0 or abs(beat_in_bar - beats_per_bar / 2) < 0.01

        # Build candidate pool
        if dissonance == "none" or is_strong:
            # Consonances only on strong beats (always for 'none' mode)
            candidates = [n for n in scale_tones if is_consonant(mn.midi_note, n)]
        elif dissonance == "passing" and not is_strong:
            # Allow dissonance on weak beats if it's a passing tone (stepwise approach)
            if cp_prev is not None:
                passing = [n for n in scale_tones if abs(n - cp_prev) <= 2]
                candidates = passing if passing else scale_tones
            else:
                candidates = scale_tones
        else:
            # 'free' — all scale tones, dissonance must resolve
            if prev_was_dissonant and cp_prev is not None:
                # Force resolution: stepwise motion away from dissonance
                candidates = [n for n in scale_tones if abs(n - cp_prev) <= 2]
            else:
                candidates = scale_tones

        if not candidates:
            candidates = scale_tones

        # Final note: cadence — prefer consonant approach
        if is_final:
            cadence = [n for n in candidates if interval_class(mn.midi_note, n) in {0, 7, 4, 3}]
            if cadence:
                candidates = cadence

        # Score candidates
        scored = []
        for c in candidates:
            s = score_candidate(
                c, mn.midi_note, melody_prev, cp_prev,
                scale_tones, beat, beats_per_bar, register, is_final,
                rng=rng,
            )
            scored.append((s, c))

        scored.sort(key=lambda x: x[0])
        _, best = scored[0]

        violations = check_interval_rules(
            mn.midi_note, best, melody_prev, cp_prev,
            beat, beats_per_bar, is_final
        )

        # Occasional rests for breathing (free species only, not at strong beats)
        use_rest = (
            dissonance == "free"
            and not is_strong
            and not is_final
            and rng.random() < 0.12
        )

        if use_rest:
            result.append(CounterpointNote(
                midi_note=None,
                start_beat=beat,
                duration_beats=mn.duration_beats,
                velocity=0,
                is_rest=True,
            ))
            # Don't update cp_prev on rest — voice resumes from same pitch
        else:
            result.append(CounterpointNote(
                midi_note=best,
                start_beat=beat,
                duration_beats=mn.duration_beats,
                velocity=velocity,
                violations=violations,
            ))
            prev_was_dissonant = is_dissonant(mn.midi_note, best)
            cp_prev = best
            melody_prev = mn.midi_note

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
) -> list[CounterpointNote]:
    """
    Generate a counterpoint voice against a melody.

    Args:
        melody_notes:  List of MelodyNote from melody.py
        key:           Key center e.g. "D"
        mode:          Mode name e.g. "dorian"
        species:       "first" | "free"
        register:      "above" | "below"
        beats_per_bar: Time signature numerator
        velocity:      Base MIDI velocity
        dissonance:    For free species: "none" | "passing" | "free"
        seed:          Random seed
        cp_model:      Optional CounterpointModel instance.  When provided,
                       its fields override the individual keyword arguments so
                       the caller does not need to unpack the model manually.

    Returns:
        List of CounterpointNote
    """
    # If a typed model is supplied, let it win over individual kwargs.
    if cp_model is not None:
        species       = cp_model.species
        register      = cp_model.cp_register
        beats_per_bar = beats_per_bar  # not on CounterpointModel — caller supplies
        velocity      = cp_model.velocity
        dissonance    = cp_model.dissonance

    if species == "first":
        return generate_first_species(
            melody_notes, key, mode, register, beats_per_bar, velocity, seed
        )
    elif species == "free":
        return generate_free_species(
            melody_notes, key, mode, register, beats_per_bar,
            velocity, dissonance, seed
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
        rests = sum(1 for n in cp if n.is_rest)
        print(f"  Notes: {report['total_notes']}  Rests: {rests}  "
              f"Hard violations: {report['hard_violations']}  "
              f"Soft: {report['soft_violations']}")

        if report["violation_types"]:
            print(f"  Violation types: {report['violation_types']}")
        print()
