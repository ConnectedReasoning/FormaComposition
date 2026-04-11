"""
rhythmic_template.py — Prosodic Rhythm Canon: Phase 1

RhythmicTemplate: the rhythmic skeleton of a phrase, without pitch.
Every voice reads this through a lens to get its own rhythm events.

Lives alongside prosody.py in:  forma/intervals/music/rhythmic_template.py

Usage:
    from intervals.music.rhythmic_template import (
        RhythmicTemplate,
        analysis_to_rhythm_template,
        phrase_to_rhythm_template,
        tile_template,
    )

    # From a phrase
    template = phrase_to_rhythm_template("Glass Cathedral")

    # From an existing ProsodyAnalysis
    template = analysis_to_rhythm_template(analysis, seed=42)

    # Tile to fill a section
    tiled = tile_template(template, total_beats=32.0)
"""

import random
from dataclasses import dataclass, field
from typing import Optional

# Import prosody internals we share
from intervals.music.prosody import (
    analyze_phrase,
    ProsodyAnalysis,
    Syllable,
    LONG_VOWELS,
    RHYTHM_SLOW,
    RHYTHM_NORM,
)


# ═══════════════════════════════════════════════════════════════════════
# RhythmicTemplate — the rhythmic DNA of a phrase
# ═══════════════════════════════════════════════════════════════════════

@dataclass
class RhythmicTemplate:
    """
    The rhythmic skeleton of a text phrase — onsets, durations, accents —
    without any pitch information.

    This is the shared rhythmic DNA that all voices interpret through
    their own lens.  "Glass Cathedral" becomes a pattern of strong and
    weak beats that bass, harmony, counterpoint, and drums all follow
    in their own way.

    Attributes:
        name:         Identifier (usually the phrase, lowercased)
        phrase:       Original text phrase
        onsets:       Beat position of each syllable onset
        durations:    Duration in beats of each syllable
        accents:      Velocity/emphasis weight per onset (0.0–1.0)
        stresses:     Raw CMU stress values (1=primary, 2=secondary, 0=unstressed)
        total_beats:  Total duration of one statement of the template
        syllable_texts: The text of each syllable for debugging/display
    """
    name: str
    phrase: str
    onsets: list[float]
    durations: list[float]
    accents: list[float]
    stresses: list[int]
    total_beats: float
    syllable_texts: list[str] = field(default_factory=list)

    def __len__(self) -> int:
        return len(self.onsets)

    def __repr__(self) -> str:
        beats = f"{self.total_beats:.1f}b"
        n = len(self.onsets)
        stressed = sum(1 for a in self.accents if a > 0.6)
        return f"RhythmicTemplate('{self.phrase}' {n}syl {stressed}stress {beats})"

    @property
    def stressed_onsets(self) -> list[float]:
        """Beat positions of primary-stressed syllables only."""
        return [o for o, a in zip(self.onsets, self.accents) if a > 0.6]

    @property
    def primary_onsets(self) -> list[float]:
        """Beat positions where stress == 1 (primary accent)."""
        return [o for o, s in zip(self.onsets, self.stresses) if s == 1]

    @property
    def secondary_onsets(self) -> list[float]:
        """Beat positions where stress == 2 (secondary accent)."""
        return [o for o, s in zip(self.onsets, self.stresses) if s == 2]

    def onset_at(self, index: int) -> float:
        """Get onset beat at index, wrapping if needed."""
        return self.onsets[index % len(self.onsets)]

    def accent_at(self, index: int) -> float:
        """Get accent weight at index, wrapping if needed."""
        return self.accents[index % len(self.accents)]


# ═══════════════════════════════════════════════════════════════════════
# Stress → accent mapping
# ═══════════════════════════════════════════════════════════════════════

# CMU stress values (0, 1, 2) → musical accent weight (0.0–1.0)
# These are the default weights.  Voice lenses interpret these
# differently (bass might treat > 0.6 as "play", harmony > 0.7).

STRESS_TO_ACCENT = {
    1: 0.9,    # primary stress   → strong accent
    2: 0.55,   # secondary stress → moderate accent
    0: 0.25,   # unstressed       → weak/ghost
}

# Word-initial and phrase-initial bonuses
WORD_INITIAL_BONUS = 0.1
PHRASE_INITIAL_BONUS = 0.15

# Long vowel bonus (stressed long vowels get extra weight)
LONG_VOWEL_BONUS = 0.05


def _compute_accent(syl: Syllable, position: int, total: int) -> float:
    """
    Compute accent weight for a syllable.

    Combines CMU stress level with positional bonuses:
    - Word-initial syllables get a small bump
    - Phrase-initial syllable gets an extra bump
    - Long vowels on stressed syllables get a bump
    - Phrase-final syllable gets a slight reduction (natural decay)
    """
    accent = STRESS_TO_ACCENT.get(syl.stress, 0.25)

    if syl.is_first:
        accent += WORD_INITIAL_BONUS
    if position == 0:
        accent += PHRASE_INITIAL_BONUS
    if syl.vowel in LONG_VOWELS and syl.stress >= 1:
        accent += LONG_VOWEL_BONUS
    if position == total - 1 and syl.stress == 0:
        accent *= 0.8  # phrase-final unstressed syllable decays

    return min(1.0, max(0.0, accent))


# ═══════════════════════════════════════════════════════════════════════
# Duration computation (mirrors prosody.py's _rhythm but deterministic)
# ═══════════════════════════════════════════════════════════════════════

def _template_duration(
    stress: int,
    is_long_vowel: bool,
    slow: bool,
    seed_val: Optional[int] = None,
) -> float:
    """
    Compute syllable duration for the template.

    Uses the same pools as prosody.py's _rhythm() but with optional
    deterministic selection (median of pool) for reproducibility.
    When seed_val is provided, uses seeded random for variety.
    """
    pool = (RHYTHM_SLOW if slow else RHYTHM_NORM).get(stress, [1.0])

    if seed_val is not None:
        rng = random.Random(seed_val)
        r = rng.choice(pool)
    else:
        # Deterministic: use median of pool
        sorted_pool = sorted(pool)
        r = sorted_pool[len(sorted_pool) // 2]

    if is_long_vowel and stress >= 1:
        r = round(r * 1.25 * 4) / 4

    return r


# ═══════════════════════════════════════════════════════════════════════
# Core conversion
# ═══════════════════════════════════════════════════════════════════════

def analysis_to_rhythm_template(
    analysis: ProsodyAnalysis,
    name: Optional[str] = None,
    slow: bool = True,
    seed: Optional[int] = None,
    max_syllables: int = 8,
) -> RhythmicTemplate:
    """
    Convert a ProsodyAnalysis to a RhythmicTemplate.

    This extracts ONLY the rhythmic information — no pitches, no
    intervals.  The template captures when each syllable lands,
    how long it lasts, and how strongly it's accented.

    Args:
        analysis:       ProsodyAnalysis from analyze_phrase()
        name:           Template name (defaults to phrase text)
        slow:           Use slow tempo duration pools (default True)
        seed:           Random seed for duration variety
        max_syllables:  Cap on syllable count

    Returns:
        RhythmicTemplate
    """
    syllables = analysis.syllables[:max_syllables]

    if not syllables:
        return RhythmicTemplate(
            name=name or "empty",
            phrase=analysis.phrase,
            onsets=[0.0],
            durations=[2.0],
            accents=[0.5],
            stresses=[1],
            total_beats=2.0,
            syllable_texts=["?"],
        )

    template_name = name or analysis.phrase.lower().replace(" ", "_")
    total = len(syllables)

    # Compute durations
    durations = []
    for i, syl in enumerate(syllables):
        is_long = syl.vowel in LONG_VOWELS
        seed_val = (seed + i * 7) if seed is not None else None
        dur = _template_duration(syl.stress, is_long, slow, seed_val)
        durations.append(dur)

    # Compute onsets (cumulative sum)
    onsets = []
    beat = 0.0
    for dur in durations:
        onsets.append(round(beat * 4) / 4)  # quantize to 16th notes
        beat += dur

    # Compute accents
    accents = [_compute_accent(syl, i, total) for i, syl in enumerate(syllables)]

    # Raw stresses
    stresses = [syl.stress for syl in syllables]

    # Syllable texts for debugging
    syl_texts = [syl.text for syl in syllables]

    total_beats = round(beat * 4) / 4  # quantize total

    return RhythmicTemplate(
        name=template_name,
        phrase=analysis.phrase,
        onsets=onsets,
        durations=durations,
        accents=accents,
        stresses=stresses,
        total_beats=total_beats,
        syllable_texts=syl_texts,
    )


# ═══════════════════════════════════════════════════════════════════════
# Convenience API
# ═══════════════════════════════════════════════════════════════════════

def phrase_to_rhythm_template(
    phrase: str,
    name: Optional[str] = None,
    slow: bool = True,
    seed: Optional[int] = None,
    max_syllables: int = 8,
) -> RhythmicTemplate:
    """
    Convert a text phrase directly to a RhythmicTemplate.

    This is the main entry point for the prosodic rhythm system.

    Args:
        phrase:         Text phrase (e.g., "Glass Cathedral")
        name:           Template name (defaults to phrase)
        slow:           Use slow tempo duration pools
        seed:           Random seed
        max_syllables:  Maximum syllables to process

    Returns:
        RhythmicTemplate
    """
    analysis = analyze_phrase(phrase)
    return analysis_to_rhythm_template(
        analysis, name=name, slow=slow, seed=seed,
        max_syllables=max_syllables,
    )


# ═══════════════════════════════════════════════════════════════════════
# Template tiling — repeat template to fill a section
# ═══════════════════════════════════════════════════════════════════════

def tile_template(
    template: RhythmicTemplate,
    total_beats: float,
    gap_beats: float = 0.0,
) -> RhythmicTemplate:
    """
    Tile (repeat) a template to fill a given number of beats.

    Each repetition is offset by template.total_beats + gap_beats.
    Useful for filling a 16-bar section with a 4-beat phrase pattern.

    Args:
        template:    Source template
        total_beats: Total beats to fill
        gap_beats:   Silence between repetitions (default 0.0)

    Returns:
        New RhythmicTemplate covering the full duration
    """
    if template.total_beats <= 0:
        return template

    stride = template.total_beats + gap_beats
    onsets = []
    durations = []
    accents = []
    stresses = []
    syl_texts = []

    offset = 0.0
    while offset < total_beats:
        for i in range(len(template)):
            onset = offset + template.onsets[i]
            if onset >= total_beats:
                break
            # Trim last note if it would exceed total_beats
            dur = template.durations[i]
            if onset + dur > total_beats:
                dur = total_beats - onset
            onsets.append(round(onset * 4) / 4)
            durations.append(dur)
            accents.append(template.accents[i])
            stresses.append(template.stresses[i])
            syl_texts.append(template.syllable_texts[i] if i < len(template.syllable_texts) else "")
        offset += stride

    return RhythmicTemplate(
        name=template.name,
        phrase=template.phrase,
        onsets=onsets,
        durations=durations,
        accents=accents,
        stresses=stresses,
        total_beats=total_beats,
        syllable_texts=syl_texts,
    )


# ═══════════════════════════════════════════════════════════════════════
# Prosodic chord timing — chord changes land on stressed syllables
# ═══════════════════════════════════════════════════════════════════════

def prosodic_chord_bars(
    template: RhythmicTemplate,
    n_chords: int,
    total_bars: float,
    beats_per_bar: int = 4,
    accent_threshold: float = 0.6,
) -> list[float]:
    """
    Derive per-chord bar durations from the prosodic stress pattern.

    Instead of even spacing (e.g., [4, 4, 4, 4]), chord changes land
    on stressed syllables of the tiled phrase.  The result is uneven
    phrasing that follows the natural speech rhythm.

    Algorithm:
      1. Tile the template across the section's total beats
      2. Collect all stressed onsets (accent > threshold)
      3. Distribute N chords across the stressed onsets as evenly
         as possible (every Kth stressed onset)
      4. Derive bar durations from the gaps between chord changes

    Args:
        template:          RhythmicTemplate from the phrase
        n_chords:          Number of chords in the progression
        total_bars:        Total bars in the section
        beats_per_bar:     Beats per bar (default 4)
        accent_threshold:  Minimum accent to count as stressed (default 0.6)

    Returns:
        list[float] of bar durations per chord (sums to total_bars)

    Example:
        "Behind the Waterfall" with 4 chords over 16 bars:
        → [3.12, 4.5, 3.62, 4.5] instead of [4.0, 4.0, 4.0, 4.0]
    """
    total_beats = total_bars * beats_per_bar

    if n_chords <= 0:
        return []
    if n_chords == 1:
        return [total_bars]

    # Tile template and find stressed onsets
    tiled = tile_template(template, total_beats)
    stressed = [tiled.onsets[i] for i in range(len(tiled))
                if tiled.accents[i] > accent_threshold]

    if len(stressed) < n_chords:
        # Not enough stressed onsets — fall back to even split
        even = total_bars / n_chords
        return [even] * n_chords

    # Distribute chords across stressed onsets as evenly as possible
    stride = len(stressed) / n_chords
    chord_change_beats = [stressed[int(i * stride)] for i in range(n_chords)]

    # First chord should start at beat 0 (or very close)
    # If the first stressed onset isn't at 0, shift to 0
    if chord_change_beats[0] > 0.5:
        chord_change_beats[0] = 0.0

    # Derive bar durations from the gaps
    chord_change_beats.append(total_beats)
    bars_list = []
    for i in range(n_chords):
        dur_beats = chord_change_beats[i + 1] - chord_change_beats[i]
        bars_list.append(dur_beats / beats_per_bar)

    # Quantize to quarter-bar resolution (0.25) for cleaner MIDI
    bars_list = [round(b * 4) / 4 for b in bars_list]

    # Adjust rounding errors so sum matches total_bars exactly
    diff = total_bars - sum(bars_list)
    if abs(diff) > 0.01:
        # Add/subtract the difference to the longest chord
        longest_idx = bars_list.index(max(bars_list))
        bars_list[longest_idx] += diff
        bars_list[longest_idx] = round(bars_list[longest_idx] * 4) / 4

    return bars_list


# ═══════════════════════════════════════════════════════════════════════
# VOICE LENSES — transform a template into RhythmEvents for each voice
# ═══════════════════════════════════════════════════════════════════════
#
# Each lens: RhythmicTemplate → list[RhythmEvent]
# The output replaces what get_pattern() normally provides.
# Swing and humanize still apply AFTER the lens, same as before.

from intervals.music.rhythm import RhythmEvent


def melody_lens(
    template: RhythmicTemplate,
    total_beats: float,
    gap_beats: float = 0.0,
    rest_probability: float = 0.08,
    seed: Optional[int] = None,
) -> list[RhythmEvent]:
    """
    Direct lens — melody follows the template closely.

    Every syllable onset becomes a note event. Accent maps to velocity
    scale. Unstressed syllables have a small chance of becoming rests
    (breathing room).
    """
    rng = random.Random(seed)
    tiled = tile_template(template, total_beats, gap_beats)
    events = []
    for i in range(len(tiled)):
        is_rest = (tiled.accents[i] < 0.4 and rng.random() < rest_probability)
        events.append(RhythmEvent(
            start_beat=tiled.onsets[i],
            duration_beats=tiled.durations[i],
            velocity_scale=tiled.accents[i],
            is_rest=is_rest,
        ))
    return events


def bass_lens(
    template: RhythmicTemplate,
    total_beats: float,
    accent_threshold: float = 0.5,
    duration_mult: float = 2.0,
    gap_beats: float = 0.0,
) -> list[RhythmEvent]:
    """
    Stress-filtered, augmented lens — bass plays on stressed onsets only.

    Onsets below the accent threshold are skipped. Durations are multiplied
    (default 2x) so bass notes sustain through unstressed syllables.
    Duration is capped at the distance to the next bass onset.

    "re-BEC-ca" → bass plays on BEC, holds through ca.
    """
    tiled = tile_template(template, total_beats, gap_beats)

    # Collect only stressed onsets
    stressed = [(tiled.onsets[i], tiled.durations[i], tiled.accents[i])
                for i in range(len(tiled))
                if tiled.accents[i] >= accent_threshold]

    if not stressed:
        # Fallback: play on first onset of each template repetition
        stressed = [(tiled.onsets[0], tiled.durations[0], tiled.accents[0])]

    events = []
    for j, (onset, dur, accent) in enumerate(stressed):
        # Augment duration
        aug_dur = dur * duration_mult
        # Cap at distance to next stressed onset
        if j + 1 < len(stressed):
            max_dur = stressed[j + 1][0] - onset
            aug_dur = min(aug_dur, max_dur)
        # Cap at total_beats
        aug_dur = min(aug_dur, total_beats - onset)
        aug_dur = max(0.25, aug_dur)

        events.append(RhythmEvent(
            start_beat=onset,
            duration_beats=aug_dur,
            velocity_scale=accent,
            is_rest=False,
        ))
    return events


def harmony_lens(
    template: RhythmicTemplate,
    total_beats: float,
    primary_threshold: float = 0.6,
    secondary_threshold: float = 0.5,
    gap_beats: float = 0.0,
) -> list[RhythmEvent]:
    """
    Onset-triggered sustain lens — harmony voices chords on stressed beats.

    Primary accents (above primary_threshold) trigger a new chord voicing.
    Secondary accents (above secondary_threshold) optionally re-articulate.
    The chord sustains between triggers — unstressed syllables are NOT
    re-articulated.

    Result: harmony breathes with the phrase instead of pulsing on a grid.
    """
    tiled = tile_template(template, total_beats, gap_beats)

    # Collect trigger points
    triggers = []
    for i in range(len(tiled)):
        accent = tiled.accents[i]
        if accent >= primary_threshold:
            triggers.append((tiled.onsets[i], accent, "primary"))
        elif accent >= secondary_threshold:
            triggers.append((tiled.onsets[i], accent, "secondary"))

    if not triggers:
        # Fallback: single sustained chord
        return [RhythmEvent(start_beat=0.0, duration_beats=total_beats,
                            velocity_scale=0.7, is_rest=False)]

    events = []
    for j, (onset, accent, kind) in enumerate(triggers):
        # Duration extends to the next trigger or end of section
        if j + 1 < len(triggers):
            dur = triggers[j + 1][0] - onset
        else:
            dur = total_beats - onset
        dur = max(0.5, dur)

        # Secondary re-articulations are softer
        vel_scale = accent if kind == "primary" else accent * 0.75

        events.append(RhythmEvent(
            start_beat=onset,
            duration_beats=dur,
            velocity_scale=vel_scale,
            is_rest=False,
        ))
    return events


def counterpoint_lens(
    template: RhythmicTemplate,
    total_beats: float,
    offset_beats: Optional[float] = None,
    gap_beats: float = 0.0,
    rest_probability: float = 0.1,
    seed: Optional[int] = None,
) -> list[RhythmEvent]:
    """
    Canon offset lens — same rhythm, displaced in time.

    Applies the full template but shifted forward by offset_beats.
    Default offset: duration of the first stressed syllable (creates
    a natural stagger).

    This is the "Row Row Row Your Boat" effect.
    """
    rng = random.Random(seed)
    tiled = tile_template(template, total_beats, gap_beats)

    # Default offset: duration of first stressed syllable
    if offset_beats is None:
        for i in range(len(template)):
            if template.accents[i] > 0.5:
                offset_beats = template.durations[i]
                break
        if offset_beats is None:
            offset_beats = template.durations[0] if template.durations else 1.0

    events = []
    for i in range(len(tiled)):
        onset = tiled.onsets[i] + offset_beats
        if onset >= total_beats:
            continue
        dur = min(tiled.durations[i], total_beats - onset)
        if dur <= 0:
            continue
        is_rest = (tiled.accents[i] < 0.3 and rng.random() < rest_probability)
        events.append(RhythmEvent(
            start_beat=round(onset * 4) / 4,  # quantize
            duration_beats=dur,
            velocity_scale=tiled.accents[i] * 0.85,  # slightly softer than melody
            is_rest=is_rest,
        ))
    return events


def drums_lens(
    template: RhythmicTemplate,
    total_beats: float,
    gap_beats: float = 0.0,
) -> list[RhythmEvent]:
    """
    Accent-mapped lens — maps stress pattern to drum emphasis.

    Returns RhythmEvents where velocity_scale encodes the accent level.
    The drum generator can interpret this as:
      accent > 0.7 → kick + snare
      accent 0.4-0.7 → hi-hat accent
      accent < 0.4 → ghost hi-hat

    The actual drum note mapping happens in percussion.py — this lens
    just provides the rhythmic skeleton with accent weighting.
    """
    tiled = tile_template(template, total_beats, gap_beats)
    events = []
    for i in range(len(tiled)):
        events.append(RhythmEvent(
            start_beat=tiled.onsets[i],
            duration_beats=min(tiled.durations[i], 0.5),  # short hits
            velocity_scale=tiled.accents[i],
            is_rest=False,
        ))
    return events


# ── Lens registry ─────────────────────────────────────────────────────

VOICE_LENSES = {
    "melody":       melody_lens,
    "direct":       melody_lens,        # alias
    "bass":         bass_lens,
    "stress":       bass_lens,          # alias
    "harmony":      harmony_lens,
    "onset_sustain": harmony_lens,      # alias
    "counterpoint": counterpoint_lens,
    "canon":        counterpoint_lens,  # alias
    "drums":        drums_lens,
    "accent":       drums_lens,         # alias
}


def apply_lens(
    lens_name: str,
    template: RhythmicTemplate,
    total_beats: float,
    **kwargs,
) -> list[RhythmEvent]:
    """
    Apply a named voice lens to a template.

    Args:
        lens_name:    Name from VOICE_LENSES registry
        template:     RhythmicTemplate to interpret
        total_beats:  Total beats to fill
        **kwargs:     Lens-specific parameters

    Returns:
        list[RhythmEvent]
    """
    fn = VOICE_LENSES.get(lens_name)
    if fn is None:
        raise ValueError(f"Unknown lens '{lens_name}'. "
                         f"Choose from: {sorted(set(VOICE_LENSES.keys()))}")
    return fn(template, total_beats, **kwargs)


# ═══════════════════════════════════════════════════════════════════════
# Display / debug
# ═══════════════════════════════════════════════════════════════════════

def print_template(template: RhythmicTemplate) -> None:
    """Pretty-print a RhythmicTemplate for debugging."""
    stress_labels = {0: "·", 1: "●", 2: "○"}

    print(f"\n{'─' * 62}")
    print(f"  RhythmicTemplate: \"{template.phrase}\"")
    print(f"  Total: {template.total_beats:.1f} beats, {len(template)} syllables")
    print(f"  Stressed onsets: {template.stressed_onsets}")
    print(f"\n  {'Syl':<10} {'Onset':>6} {'Dur':>5} {'Accent':>7} {'Stress':>7}")
    print(f"  {'───':<10} {'─────':>6} {'────':>5} {'──────':>7} {'──────':>7}")

    for i in range(len(template)):
        text = template.syllable_texts[i] if i < len(template.syllable_texts) else "?"
        onset = template.onsets[i]
        dur = template.durations[i]
        accent = template.accents[i]
        stress = template.stresses[i]
        marker = stress_labels.get(stress, "?")

        # Visual accent bar
        bar_len = int(accent * 20)
        bar = "█" * bar_len + "░" * (20 - bar_len)

        print(f"  {text:<10} {onset:6.2f} {dur:5.2f} {accent:7.2f} {marker:>4}  {bar}")

    print(f"{'─' * 62}")


# ═══════════════════════════════════════════════════════════════════════
# Quick test / demo
# ═══════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    print("=== Prosodic Rhythm Canon — RhythmicTemplate + Voice Lenses ===\n")

    # Test phrases
    phrases = [
        "Glass Cathedral",
        "Rebecca",
        "Behind the Waterfall",
    ]

    for phrase in phrases:
        template = phrase_to_rhythm_template(phrase, seed=42)
        print_template(template)
        print()

    # Test all lenses on "Glass Cathedral"
    print("\n=== Voice Lenses: 'Glass Cathedral' tiled to 16 beats ===\n")
    base = phrase_to_rhythm_template("Glass Cathedral", seed=42)
    total = 16.0

    lens_kwargs = {
        "melody":       {"seed": 42},
        "bass":         {},
        "harmony":      {},
        "counterpoint": {"seed": 42},
        "drums":        {},
    }

    for lens_name in ["melody", "bass", "harmony", "counterpoint", "drums"]:
        events = apply_lens(lens_name, base, total, **lens_kwargs[lens_name])
        notes = [e for e in events if not e.is_rest]
        rests = [e for e in events if e.is_rest]
        print(f"  {lens_name:14s}  {len(notes):2d} notes, {len(rests)} rests")
        for e in events[:8]:
            kind = "REST" if e.is_rest else "NOTE"
            print(f"    {kind} beat={e.start_beat:5.2f}  dur={e.duration_beats:4.2f}  vel={e.velocity_scale:.2f}")
        if len(events) > 8:
            print(f"    ... ({len(events) - 8} more)")
        print()
