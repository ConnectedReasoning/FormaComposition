"""
prosody.py — Intervals Engine
Speech-to-motif conversion using phonetic stress analysis and harmonic awareness.

Converts a text phrase into a Motif by analysing the natural prosody of speech
— syllable stress, vowel duration, pitch contour — and mapping these to musical
intervals chosen from the actual harmony at that moment.

The core idea: when you say "Rebecca" naturally, you're already making music.
re-BEC-ca is short-LONG-short, pitch rises on the stressed syllable. That
contour becomes the melodic shape. But instead of mapping stress to raw
semitone intervals, we map it to actual chord tones and extensions — root,
third, fifth, seventh, ninth — chosen according to how much harmonic tension
the section is allowed to carry.

Tension is automatic, driven by section properties:
    arc      → sets the tension ceiling (swell allows more than fade_in)
    melody   → sets how often tension tones are used (develop > lyrical > sparse)
    density  → controls passing tone budget

Tension hierarchy (from stable to expressive):
    STABLE   → root, fifth              (always safe, stressed downbeats)
    WARM     → third, sixth, major 7th  (adds color without tension)
    COLOR    → ninth, thirteenth        (rich, slightly yearning)
    TENSION  → minor 7th, eleventh      (pulls toward resolution)
    PASSING  → chromatic neighbors      (very brief, unstressed only)

Voice leading rules enforced:
    - Tension tones resolve by step (7th steps down, leading tone steps up)
    - No two large leaps in the same direction consecutively
    - Phrase endings resolve to stable tones
    - After a leap, prefer stepwise return

Usage:
    from intervals.music.prosody import phrase_to_motif, phrase_to_motif_dict

    # Simple - just a phrase
    motif = phrase_to_motif("Rebecca")

    # With harmonic context from a section
    section = {"arc": "swell", "melody": "lyrical", "density": "medium"}
    motif = phrase_to_motif("Rebecca", section=section,
                             chord="I", key="G", mode="ionian")

    # As a theme motif dict (drop-in for theme JSON)
    d = phrase_to_motif_dict("Rebecca", name="rebecca",
                              section=section, chord="I", key="G", mode="ionian")
"""

import re
import random
from dataclasses import dataclass, field
from typing import Optional

try:
    import pronouncing
    PRONOUNCING_AVAILABLE = True
except ImportError:
    PRONOUNCING_AVAILABLE = False

from intervals.music.motif import Motif
from intervals.music.harmony import resolve_chord, get_scale, CHROMATIC


# ---------------------------------------------------------------------------
# Tension levels
# ---------------------------------------------------------------------------

STABLE  = "stable"    # root, fifth
WARM    = "warm"      # third, sixth, major 7th
COLOR   = "color"     # ninth, thirteenth
TENSION = "tension"   # minor 7th, eleventh
PASSING = "passing"   # chromatic neighbors (very brief)

# Semitone offsets from chord root for each tension level
TENSION_INTERVALS = {
    STABLE:  [0, 7],
    WARM:    [4, 3, 9, 11],
    COLOR:   [14, 21],
    TENSION: [10, 17],
    PASSING: [1, -1, 2, -2],
}

# ---------------------------------------------------------------------------
# Section to tension profile
# ---------------------------------------------------------------------------

ARC_CEILING = {
    "fade_in":  WARM,
    "swell":    TENSION,
    "breath":   COLOR,
    "fade_out": WARM,
    "flat":     WARM,
}

MELODY_TENSION_FREQ = {
    "sparse":     0.05,
    "lyrical":    0.30,
    "generative": 0.20,
    "develop":    0.55,
}

DENSITY_PASSING = {
    "sparse": 0.0,
    "medium": 0.15,
    "full":   0.35,
}

TENSION_ORDER = [STABLE, WARM, COLOR, TENSION, PASSING]


def _level_index(level: str) -> int:
    try:
        return TENSION_ORDER.index(level)
    except ValueError:
        return 0


def tension_profile_from_section(section: Optional[dict]) -> dict:
    """
    Derive a tension profile dict from a section definition.
    Keys: ceiling, freq, passing_prob
    """
    if section is None:
        return {"ceiling": WARM, "freq": 0.20, "passing_prob": 0.0}

    arc     = section.get("arc", "breath")
    melody  = section.get("melody", "lyrical")
    density = section.get("density", "medium")

    ceiling      = ARC_CEILING.get(arc, WARM)
    freq         = MELODY_TENSION_FREQ.get(melody, 0.20)
    passing_prob = DENSITY_PASSING.get(density, 0.0)

    if arc == "swell" and melody == "develop":
        freq = min(1.0, freq * 1.3)
    if arc == "fade_out":
        passing_prob = 0.0

    return {"ceiling": ceiling, "freq": freq, "passing_prob": passing_prob}


# ---------------------------------------------------------------------------
# Syllable / analysis data classes
# ---------------------------------------------------------------------------

LONG_VOWELS = {"EY", "IY", "OW", "UW", "AY", "AW", "OY"}
VOWEL_CHARS = set("aeiouAEIOU")


@dataclass
class Syllable:
    text: str
    word: str
    stress: int
    position: int
    is_first: bool = False
    is_last: bool = False
    vowel: str = ""


@dataclass
class ProsodyAnalysis:
    phrase: str
    syllables: list
    words: list
    stress_pattern: str
    found_in_dict: list = field(default_factory=list)
    fallback_words: list = field(default_factory=list)


# ---------------------------------------------------------------------------
# Phonetic analysis
# ---------------------------------------------------------------------------

def _count_syllables_fallback(word: str) -> int:
    word = word.lower().strip(".,!?;:")
    count, in_vowel = 0, False
    for ch in word:
        if ch in VOWEL_CHARS:
            if not in_vowel:
                count += 1
                in_vowel = True
        else:
            in_vowel = False
    if word.endswith("e") and len(word) > 2 and word[-2] not in VOWEL_CHARS:
        count = max(1, count - 1)
    return max(1, count)


def _stress_fallback(word: str) -> str:
    n = _count_syllables_fallback(word)
    if n == 1: return "1"
    if n == 2: return "10"
    if n == 3: return "100"
    s = ["0"] * n
    s[1] = "1"
    return "".join(s)


def _get_word_phones(word: str):
    if not PRONOUNCING_AVAILABLE:
        return None, None
    clean = word.lower().strip(".,!?;:'\"")
    phones_list = pronouncing.phones_for_word(clean)
    if not phones_list:
        return None, None
    phones = phones_list[0]
    return phones, pronouncing.stresses(phones)


def _extract_vowel(phones: str, idx: int) -> str:
    if not phones:
        return ""
    vowels = [p for p in phones.split() if p[-1] in "012"]
    return re.sub(r"[012]$", "", vowels[idx]) if idx < len(vowels) else ""


def analyze_phrase(phrase: str) -> ProsodyAnalysis:
    """Analyze prosody of a text phrase. Returns ProsodyAnalysis."""
    words = [w.strip(".,!?;:'\"").lower() for w in phrase.split() if w.strip(".,!?;:'\"")]
    syllables, full_stress = [], []
    found_in_dict, fallback_words = [], []
    position = 0

    for word in words:
        phones, stress_str = _get_word_phones(word)
        if stress_str:
            found_in_dict.append(word)
        else:
            stress_str = _stress_fallback(word)
            fallback_words.append(word)

        for i, s in enumerate(stress_str):
            vowel = _extract_vowel(phones, i) if phones else ""
            syllables.append(Syllable(
                text=word, word=word, stress=int(s), position=position,
                is_first=(i == 0), is_last=(i == len(stress_str) - 1), vowel=vowel,
            ))
            full_stress.append(s)
            position += 1

    return ProsodyAnalysis(
        phrase=phrase, syllables=syllables, words=words,
        stress_pattern="".join(full_stress),
        found_in_dict=found_in_dict, fallback_words=fallback_words,
    )


# ---------------------------------------------------------------------------
# Harmonic note pool
# ---------------------------------------------------------------------------

def build_note_pool(
    chord_root_midi: int,
    quality: str,
    key: str,
    mode: str,
    ceiling: str,
    register_bottom: int = 62,
    register_top: int = 84,
) -> dict:
    """
    Build available MIDI notes per tension level, up to ceiling.
    Returns dict: tension_level -> list of MIDI notes in register.
    """
    ceiling_idx = _level_index(ceiling)
    scale_tones = set()
    for oct in range(3, 8):
        for t in get_scale(key, mode, oct):
            scale_tones.add(t % 12)

    pool = {}
    for level in TENSION_ORDER[:ceiling_idx + 1]:
        notes = []
        for interval in TENSION_INTERVALS[level]:
            base = chord_root_midi + interval
            while base < register_bottom: base += 12
            while base > register_top:   base -= 12
            if level == PASSING:
                if (base % 12) not in scale_tones:
                    notes.append(base)
            else:
                notes.append(base)
        if notes:
            pool[level] = sorted(set(notes))

    return pool


# ---------------------------------------------------------------------------
# Note selection with voice leading
# ---------------------------------------------------------------------------

def _nearest(target: int, notes: list) -> int:
    return min(notes, key=lambda n: abs(n - target)) if notes else target


def choose_note(
    syllable: Syllable,
    pool: dict,
    profile: dict,
    prev_note: Optional[int],
    prev_tension: Optional[str],
    is_phrase_end: bool,
    chord_root_midi: int,
    rng=None,
) -> tuple:
    """
    Choose a MIDI note and tension level for a syllable.
    Enforces voice leading: tension resolves, phrase ends on stable tones.
    Returns (midi_note, tension_level).
    """
    _rng = rng if rng is not None else random.Random()
    stress = syllable.stress
    freq   = profile["freq"]
    p_pass = profile["passing_prob"]

    # Phrase end: always resolve to stable
    if is_phrase_end:
        stable = pool.get(STABLE, [chord_root_midi])
        return _nearest(prev_note or chord_root_midi, stable), STABLE

    # Previous tension must resolve by step downward
    if prev_note is not None and prev_tension in (TENSION, PASSING):
        target = prev_note - 1
        candidates = pool.get(STABLE, []) + pool.get(WARM, [])
        if candidates:
            return _nearest(target, candidates), STABLE

    # Choose tension level by stress + profile
    if stress == 1:
        if _rng.random() < freq * 0.4 and COLOR in pool:
            level = COLOR
        elif _rng.random() < freq * 0.6 and WARM in pool:
            level = WARM
        else:
            level = STABLE
    elif stress == 2:
        if _rng.random() < freq and COLOR in pool:
            level = COLOR
        elif WARM in pool:
            level = WARM
        else:
            level = STABLE
    else:
        if _rng.random() < p_pass and PASSING in pool:
            level = PASSING
        elif _rng.random() < freq and TENSION in pool:
            level = TENSION
        elif _rng.random() < freq and COLOR in pool:
            level = COLOR
        else:
            level = WARM if WARM in pool else STABLE

    candidates = pool.get(level, pool.get(STABLE, [chord_root_midi]))
    if not candidates:
        candidates = [chord_root_midi]
        level = STABLE

    if prev_note is not None:
        # Prefer a note that moves — avoid repeating the same pitch
        moving = [n for n in candidates if n != prev_note]
        if moving:
            note = _nearest(prev_note, moving)
        else:
            # All candidates are the same pitch — extend pool to neighbors
            all_notes = []
            for l in TENSION_ORDER[:_level_index(level) + 2]:
                all_notes.extend(pool.get(l, []))
            moving = [n for n in all_notes if n != prev_note]
            note = _nearest(prev_note, moving) if moving else prev_note
    else:
        # First note — start on a stable tone in the middle of the register
        stable = pool.get(STABLE, candidates)
        note = stable[len(stable) // 2] if stable else candidates[0]

    return note, level


# ---------------------------------------------------------------------------
# Rhythm
# ---------------------------------------------------------------------------

RHYTHM_SLOW = {1: [2.0, 2.5, 3.0], 2: [1.0, 1.5], 0: [0.5, 0.75, 1.0]}
RHYTHM_NORM = {1: [1.5, 2.0],       2: [1.0, 1.5], 0: [0.5, 0.75]}


def _rhythm(stress: int, is_long_vowel: bool, slow: bool, rng=None) -> float:
    pool = (RHYTHM_SLOW if slow else RHYTHM_NORM).get(stress, [1.0])
    _rng = rng if rng is not None else random.Random()
    r = _rng.choice(pool)
    if is_long_vowel and stress >= 1:
        r = round(r * 1.25 * 4) / 4
    return r


# ---------------------------------------------------------------------------
# Contour
# ---------------------------------------------------------------------------

def _compute_directions(stress_pattern: str) -> list:
    stresses = [int(s) for s in stress_pattern]
    n = len(stresses)
    if n <= 1:
        return [+1] * n
    peak = max(range(n), key=lambda i: stresses[i])
    return [+1 if i <= peak else -1 for i in range(n)]


# ---------------------------------------------------------------------------
# Core conversion
# ---------------------------------------------------------------------------

def analysis_to_motif(
    analysis: ProsodyAnalysis,
    name: Optional[str] = None,
    slow: bool = True,
    seed: Optional[int] = None,
    max_syllables: int = 8,
    transform_pool: Optional[list] = None,
    section: Optional[dict] = None,
    chord: Optional[str] = None,
    key: Optional[str] = None,
    mode: Optional[str] = None,
    register_bottom: int = 62,
    register_top: int = 84,
) -> Motif:
    """
    Convert ProsodyAnalysis to a Motif.

    With key/mode/chord: notes chosen from chord tones and extensions,
    tension governed by section properties.

    Without harmonic context: falls back to interval-based mode.
    """
    if seed is not None:
        rng = random.Random(seed)
    else:
        rng = random.Random()

    syllables = analysis.syllables[:max_syllables]
    stress_pattern = analysis.stress_pattern[:max_syllables]

    if not syllables:
        return Motif(intervals=[2], rhythm=[1.0], name=name or "motif")

    if transform_pool is None:
        transform_pool = ["inversion", "augmentation", "retrograde"]

    motif_name = name or analysis.phrase.lower().replace(" ", "_")

    # Harmonic mode
    if key and mode and chord:
        profile = tension_profile_from_section(section)
        density = section.get("density", "medium") if section else "medium"

        voiced = resolve_chord(chord, key, mode, density=density,
                               register_bottom=register_bottom,
                               register_top=register_top)
        chord_root_midi = voiced.midi_notes[0]
        while chord_root_midi < register_bottom: chord_root_midi += 12
        while chord_root_midi > register_top:   chord_root_midi -= 12

        note_pool = build_note_pool(
            chord_root_midi, voiced.quality, key, mode,
            ceiling=profile["ceiling"],
            register_bottom=register_bottom,
            register_top=register_top,
        )

        notes, rhythms = [], []
        prev_note, prev_tension = None, None

        for i, syl in enumerate(syllables):
            midi_note, tension_level = choose_note(
                syl, note_pool, profile,
                prev_note, prev_tension,
                is_phrase_end=(i == len(syllables) - 1),
                chord_root_midi=chord_root_midi,
                rng=rng,
            )
            notes.append(midi_note)
            rhythms.append(_rhythm(syl.stress, syl.vowel in LONG_VOWELS, slow, rng=rng))
            prev_note, prev_tension = midi_note, tension_level

        intervals = [notes[i] - notes[i-1] for i in range(1, len(notes))]
        return Motif(
            intervals=intervals or [0],
            rhythm=rhythms[1:] or [1.0],
            name=motif_name,
            transform_pool=transform_pool,
        )

    # Interval fallback mode
    INTERVAL_MAP = {
        (1, +1): [3, 4, 5], (1, -1): [2, 3],
        (2, +1): [1, 2],    (2, -1): [1, 2],
        (0, +1): [-1, 0, 1],(0, -1): [-2, -1, 0],
    }
    directions = _compute_directions(stress_pattern)
    intervals, rhythms, prev_iv = [], [], None

    for i, syl in enumerate(syllables):
        direction = directions[i] if i < len(directions) else +1
        pool = INTERVAL_MAP.get((syl.stress, direction), [0, 1, -1])
        if prev_iv is not None and len(pool) > 1:
            pool = [x for x in pool if x != prev_iv] or pool
        iv = rng.choice(pool)
        intervals.append(iv)
        rhythms.append(_rhythm(syl.stress, syl.vowel in LONG_VOWELS, slow, rng=rng))
        prev_iv = iv

    return Motif(intervals=intervals, rhythm=rhythms,
                 name=motif_name, transform_pool=transform_pool)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def phrase_to_motif(
    phrase: str,
    name: Optional[str] = None,
    slow: bool = True,
    seed: Optional[int] = None,
    max_syllables: int = 8,
    transform_pool: Optional[list] = None,
    section: Optional[dict] = None,
    chord: Optional[str] = None,
    key: Optional[str] = None,
    mode: Optional[str] = None,
) -> Motif:
    """Convert a text phrase to a Motif."""
    return analysis_to_motif(
        analyze_phrase(phrase),
        name=name, slow=slow, seed=seed,
        max_syllables=max_syllables, transform_pool=transform_pool,
        section=section, chord=chord, key=key, mode=mode,
    )


def phrase_to_motif_dict(
    phrase: str,
    name: Optional[str] = None,
    slow: bool = True,
    seed: Optional[int] = None,
    max_syllables: int = 8,
    transform_pool: Optional[list] = None,
    section: Optional[dict] = None,
    chord: Optional[str] = None,
    key: Optional[str] = None,
    mode: Optional[str] = None,
) -> dict:
    """Convert a phrase to a motif dict ready for a theme JSON 'motif' field."""
    from intervals.music.motif import to_dict
    return to_dict(phrase_to_motif(
        phrase, name=name, slow=slow, seed=seed,
        max_syllables=max_syllables, transform_pool=transform_pool,
        section=section, chord=chord, key=key, mode=mode,
    ))


# ---------------------------------------------------------------------------
# Display / demo
# ---------------------------------------------------------------------------

def print_analysis(analysis: ProsodyAnalysis) -> None:
    labels = {0: "unstressed", 1: "PRIMARY  ", 2: "secondary"}
    print(f"\n{'─'*56}")
    print(f"  Phrase:  \"{analysis.phrase}\"")
    print(f"  Pattern: {analysis.stress_pattern}")
    if analysis.fallback_words:
        print(f"  Fallback: {', '.join(analysis.fallback_words)}")
    print(f"\n  Syllables:")
    for syl in analysis.syllables:
        v = f"  [{syl.vowel}]" if syl.vowel else ""
        l = "  ♩" if syl.vowel in LONG_VOWELS else ""
        print(f"    [{syl.position}] {syl.word:14s}  stress={labels.get(syl.stress,'?')}{v}{l}")
    print(f"{'─'*56}\n")


def print_motif_from_phrase(phrase, seed=42, section=None, chord=None, key=None, mode=None):
    from intervals.music.motif import to_dict
    analysis = analyze_phrase(phrase)
    print_analysis(analysis)
    if key and mode and chord:
        p = tension_profile_from_section(section)
        print(f"  Harmonic: {key} {mode}  chord={chord}")
        print(f"  Tension:  ceiling={p['ceiling']}  freq={p['freq']:.2f}  passing={p['passing_prob']:.2f}")
    motif = analysis_to_motif(analysis, seed=seed, section=section,
                               chord=chord, key=key, mode=mode)
    print(f"  Motif:    intervals={motif.intervals}")
    print(f"  Rhythm:   {[round(r,2) for r in motif.rhythm]}")
    print(f"  Contour:  {''.join(motif.contour())}")
    print(f"  Duration: {round(motif.total_duration(),2)} beats\n")


if __name__ == "__main__":
    print("=== prosody.py — Speech to Motif ===")
    print(f"CMU dict: {PRONOUNCING_AVAILABLE}\n")

    print("── Rebecca, no harmonic context ──")
    print_motif_from_phrase("Rebecca", seed=42)

    sections_demo = [
        ("approach",   {"arc": "fade_in",  "melody": "sparse",  "density": "sparse"}),
        ("tenderness", {"arc": "swell",    "melody": "lyrical", "density": "medium"}),
        ("bloom",      {"arc": "swell",    "melody": "develop", "density": "full"}),
        ("evening",    {"arc": "fade_out", "melody": "sparse",  "density": "sparse"}),
    ]

    print("── Rebecca with harmonic context: G ionian, chord I ──")
    for sec_name, sec in sections_demo:
        print(f"  [{sec_name}]")
        print_motif_from_phrase("Rebecca", seed=42, section=sec,
                                chord="I", key="G", mode="ionian")

    print("── 'I have loved you' — bloom section ──")
    print_motif_from_phrase("I have loved you", seed=42,
                            section={"arc":"swell","melody":"develop","density":"full"},
                            chord="I", key="G", mode="ionian")
