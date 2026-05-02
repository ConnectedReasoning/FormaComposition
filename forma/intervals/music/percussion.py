"""
percussion.py — Intervals Engine
Generates drum patterns that track the bass and lock to groove/rhythm.

Drum patterns are MIDI-based: kick, snare, hi-hat, ghost notes.
They follow the same groove/density/swing system as other voices.

The drums reinforce bass note onsets and add rhythmic definition at the
subdivision level. Five named patterns: four_on_floor, backbeat, halftime,
minimal, sideclick.

MIDI channels:
  Kick:       note 36 (C1 in drum notation)
  Snare:      note 38 (D1)
  Hi-hat:     note 42 (F#1)
  Ride:       note 51 (D#2)
  Sidestick:  note 37 (C#1)
"""

import random
from dataclasses import dataclass
from typing import Optional
from intervals.music.bass import BassNote
from intervals.music.rhythm import RhythmEvent, get_pattern, apply_swing


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------

@dataclass
class DrumHit:
    """A single drum note — note number + timing + velocity."""
    midi_note: int       # 36=kick, 38=snare, 42=hi-hat, etc.
    start_beat: float
    duration_beats: float = 0.1  # brief attack/release
    velocity: int = 80

    def __repr__(self):
        names = {36: "KICK", 38: "SNARE", 42: "HI-HAT", 51: "RIDE", 37: "SIDESTICK"}
        name = names.get(self.midi_note, f"DRUM({self.midi_note})")
        return f"DrumHit({name} beat={self.start_beat:.2f} vel={self.velocity})"


# ---------------------------------------------------------------------------
# MIDI Drum Kit
# ---------------------------------------------------------------------------

DRUM_KIT = {
    "kick":     36,    # Bass drum
    "snare":    38,    # Snare
    "hi_hat":   42,    # Closed hi-hat
    "ride":     51,    # Ride cymbal
    "sidestick": 37,   # Sidestick / cross-stick
    "tom_hi":   50,    # High tom
    "tom_mid":  48,    # Mid tom
    "tom_lo":   45,    # Low tom
}


# ---------------------------------------------------------------------------
# Drum Pattern Definitions
# Each pattern is a list of (instrument_name, beat_within_bar, velocity, priority)
# Priority: 1=sparse, 2=medium, 3=full
# ---------------------------------------------------------------------------

DRUM_PATTERNS = {
    # ── four_on_floor ─────────────────────────────────────────────────────
    # Classic electronic: kick on every beat, snare on 2+4, hi-hats on eighths
    "four_on_floor": [
        # Kick: every beat
        ("kick",     0.0, 0.95, 1),
        ("kick",     1.0, 0.90, 1),
        ("kick",     2.0, 0.95, 1),
        ("kick",     3.0, 0.90, 1),
        # Snare: 2 and 4
        ("snare",    1.0, 0.85, 1),
        ("snare",    3.0, 0.85, 1),
        # Hi-hat: eighths (sparse has closed at beats, medium adds offbeats, full adds more)
        ("hi_hat",   0.0, 0.65, 1),
        ("hi_hat",   0.5, 0.55, 2),
        ("hi_hat",   1.0, 0.65, 1),
        ("hi_hat",   1.5, 0.55, 2),
        ("hi_hat",   2.0, 0.65, 1),
        ("hi_hat",   2.5, 0.55, 2),
        ("hi_hat",   3.0, 0.65, 1),
        ("hi_hat",   3.5, 0.55, 2),
    ],

    # ── backbeat ───────────────────────────────────────────────────────────
    # Kick on beat 1, syncopated snare, hi-hat shuffled. Pop/soul.
    "backbeat": [
        ("kick",     0.0, 1.00, 1),
        ("kick",     2.0, 0.80, 2),
        ("snare",    1.0, 0.90, 1),
        ("snare",    2.5, 0.70, 2),
        ("snare",    3.0, 0.95, 1),
        ("hi_hat",   0.0, 0.65, 1),
        ("hi_hat",   0.5, 0.50, 3),
        ("hi_hat",   1.0, 0.70, 1),
        ("hi_hat",   1.5, 0.55, 2),
        ("hi_hat",   2.0, 0.65, 1),
        ("hi_hat",   2.5, 0.50, 3),
        ("hi_hat",   3.0, 0.70, 1),
        ("hi_hat",   3.5, 0.55, 2),
    ],

    # ── halftime ───────────────────────────────────────────────────────────
    # Spacious, lo-fi vibe. Kick on 1, snare on 3, sparse hi-hat.
    "halftime": [
        ("kick",     0.0, 0.95, 1),
        ("snare",    2.0, 0.85, 1),
        ("hi_hat",   0.0, 0.60, 1),
        ("hi_hat",   1.0, 0.50, 2),
        ("hi_hat",   2.0, 0.60, 1),
        ("hi_hat",   3.0, 0.50, 2),
        ("kick",     1.0, 0.65, 3),  # ghost kick
        ("snare",    3.0, 0.60, 3),  # ghost snare
    ],

    # ── minimal ────────────────────────────────────────────────────────────
    # Just kick on beats, snare on backbeat. Very sparse, open.
    "minimal": [
        ("kick",     0.0, 0.95, 1),
        ("kick",     2.0, 0.90, 1),
        ("snare",    1.0, 0.90, 1),
        ("snare",    3.0, 0.90, 1),
    ],

    # ── sideclick ──────────────────────────────────────────────────────────
    # Sidestick for pocket rhythm, kick on 1, snare accent on 3.
    "sideclick": [
        ("kick",     0.0, 0.95, 1),
        ("snare",    2.0, 0.85, 1),
        ("sidestick", 0.5, 0.70, 1),
        ("sidestick", 1.5, 0.75, 1),
        ("sidestick", 2.5, 0.70, 1),
        ("sidestick", 3.5, 0.75, 1),
        ("hi_hat",   1.0, 0.55, 2),
        ("hi_hat",   3.0, 0.55, 2),
    ],
}

VALID_DRUM_PATTERNS = list(DRUM_PATTERNS.keys())


# ---------------------------------------------------------------------------
# Percussion Generation
# ---------------------------------------------------------------------------

def generate_drums(
    total_beats: float,
    bass_notes: list[BassNote],
    pattern: str = "four_on_floor",
    density: str = "medium",
    groove: Optional[str] = None,
    swing: float = 0.0,
    beats_per_bar: int = 4,
    seed: Optional[int] = None,
) -> list[DrumHit]:
    """
    Generate drum hits that track the bass and lock to groove/density.

    The function:
    1. Tiles the named drum pattern across total_beats
    2. Filters by density (sparse/medium/full)
    3. Reinforces bass note onsets with kick hits
    4. Applies swing

    Args:
        total_beats:    Total beats to fill
        bass_notes:     List of BassNote to track
        pattern:        Drum pattern name
        density:        "sparse" | "medium" | "full"
        groove:         Optional groove name
        swing:          Swing ratio (0.0 = straight, 0.67 = triplet)
        beats_per_bar:  Beats per bar (default 4)
        seed:           Random seed

    Returns:
        List of DrumHit
    """
    rng = random.Random(seed) if seed is not None else random.Random()

    if pattern not in DRUM_PATTERNS:
        raise ValueError(
            f"Unknown drum pattern: '{pattern}'. "
            f"Choose from: {VALID_DRUM_PATTERNS}"
        )

    # Density filtering: 1=sparse, 2=medium, 3=full
    density_levels = {"sparse": 1, "medium": 2, "full": 3}
    max_priority = density_levels.get(density, 2)

    template = DRUM_PATTERNS[pattern]
    active_slots = [s for s in template if s[3] <= max_priority]

    if not active_slots:
        active_slots = [s for s in template if s[3] == 1] or [template[0]]

    # Generate hits by tiling the pattern across bars
    hits = []
    bar_start = 0.0
    bar_duration = beats_per_bar

    while bar_start < total_beats:
        for instrument, beat_in_bar, velocity_scale, _priority in active_slots:
            abs_beat = bar_start + beat_in_bar
            if abs_beat >= total_beats:
                continue

            midi_note = DRUM_KIT.get(instrument)
            if midi_note is None:
                continue

            # Base velocity from pattern
            base_vel = int(80 * velocity_scale)
            base_vel = max(40, min(120, base_vel))

            hits.append(
                DrumHit(
                    midi_note=midi_note,
                    start_beat=abs_beat,
                    duration_beats=0.1,
                    velocity=base_vel,
                )
            )

        bar_start += bar_duration

    # Reinforce bass note onsets with soft kick hits
    hits.extend(_reinforce_bass_with_kick(bass_notes, total_beats, max_priority))

    # Apply swing if specified
    if swing > 0.001:
        hits = _apply_swing_to_drums(hits, swing, beats_per_bar)

    # Sort by beat and return
    hits.sort(key=lambda h: h.start_beat)
    return hits


def _reinforce_bass_with_kick(
    bass_notes: list[BassNote],
    total_beats: float,
    priority_level: int,
) -> list[DrumHit]:
    """
    Add soft kick hits wherever the bass plays (for groove pocket).
    Only add if priority allows (medium+ for ghost kicks).
    """
    reinforcement = []

    for bass_note in bass_notes:
        if bass_note.start_beat >= total_beats:
            continue

        # Don't double-hit if bass and pattern kick already coincide
        beat_frac = bass_note.start_beat % 1.0
        if abs(beat_frac - 0.0) < 0.05:  # Close to beat boundary
            continue

        # Ghost kick at lower velocity to lock the bass into pocket
        reinforcement.append(
            DrumHit(
                midi_note=DRUM_KIT["kick"],
                start_beat=bass_note.start_beat,
                duration_beats=0.1,
                velocity=45,  # Soft, doesn't dominate
            )
        )

    return reinforcement


def _apply_swing_to_drums(
    hits: list[DrumHit],
    swing_ratio: float,
    beats_per_bar: int,
) -> list[DrumHit]:
    """
    Apply swing to drum hits by delaying offbeat notes.
    Primarily affects hi-hat and rides on eighth-note offbeats.
    """
    if abs(swing_ratio - 0.5) < 0.001:
        return hits

    swung = []
    for hit in hits:
        beat = hit.start_beat
        beat_in_bar = beat % beats_per_bar
        frac = beat_in_bar % 1.0

        # Swing offbeat eighths (0.5 beat offset within a beat)
        if abs(frac - 0.5) < 0.01 and hit.midi_note in [DRUM_KIT["hi_hat"], DRUM_KIT["ride"]]:
            offset = swing_ratio - 0.5
            swung.append(
                DrumHit(
                    midi_note=hit.midi_note,
                    start_beat=hit.start_beat + offset,
                    duration_beats=hit.duration_beats,
                    velocity=hit.velocity,
                )
            )
        else:
            swung.append(hit)

    return swung


# ---------------------------------------------------------------------------
# Quick test / demo
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    print("=== Percussion Module Demo ===\n")

    from intervals.music.bass import BassNote

    # Dummy bass line for testing
    test_bass = [
        BassNote(midi_note=43, start_beat=0.0, duration_beats=4.0),
        BassNote(midi_note=48, start_beat=4.0, duration_beats=4.0),
        BassNote(midi_note=45, start_beat=8.0, duration_beats=4.0),
        BassNote(midi_note=43, start_beat=12.0, duration_beats=4.0),
    ]

    print("Drum patterns available:")
    for pattern_name in VALID_DRUM_PATTERNS:
        print(f"  - {pattern_name}")

    print("\nGenerating drums for 16 beats:\n")

    for pattern in VALID_DRUM_PATTERNS[:3]:  # Just show first 3
        hits = generate_drums(
            total_beats=16.0,
            bass_notes=test_bass,
            pattern=pattern,
            density="medium",
            seed=42,
        )
        print(f"Pattern '{pattern}' (medium density): {len(hits)} hits")
        for hit in hits[:5]:
            print(f"  {hit}")
        if len(hits) > 5:
            print(f"  ... and {len(hits) - 5} more")
        print()
