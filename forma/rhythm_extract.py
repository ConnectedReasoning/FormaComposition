#!/usr/bin/env python3
"""
rhythm_extract.py — Extract rhythm patterns from MIDI files.

Play a rhythm on your keyboard in Logic Pro, export the MIDI,
run this tool, and paste the output into your FormaComposition JSON.

The tool extracts onset positions, durations, and velocities from
MIDI note events, normalizes them into a repeatable pattern, and
outputs a JSON block ready for your section definitions.

Usage:
    # Extract pattern from a MIDI file (auto-detects pattern length)
    python rhythm_extract.py groove.mid

    # Specify pattern length in beats (e.g., 4 beats = 1 bar of 4/4)
    python rhythm_extract.py groove.mid --beats 4

    # Extract 2-bar pattern
    python rhythm_extract.py groove.mid --beats 8

    # Extract separate melody and harmony patterns from a multi-track file
    python rhythm_extract.py groove.mid --track 0 --name melody_rhythm
    python rhythm_extract.py groove.mid --track 1 --name harmony_rhythm

    # Quantize to 16th notes (default) or 8th notes
    python rhythm_extract.py groove.mid --quantize 16
    python rhythm_extract.py groove.mid --quantize 8

    # Output just the JSON (no display), ready to paste
    python rhythm_extract.py groove.mid --json-only

Output (paste into your section JSON):
    "rhythm_pattern": {
        "onsets": [0.0, 1.0, 1.5, 2.5, 3.0],
        "durations": [0.75, 0.5, 0.75, 0.5, 1.0],
        "velocities": [0.9, 0.6, 0.8, 0.5, 0.7],
        "length_beats": 4.0
    }
"""

import argparse
import json
import sys
from dataclasses import dataclass, field
from typing import Optional

try:
    import mido
except ImportError:
    print("Error: mido is required. Install with: pip install mido")
    sys.exit(1)


# ─────────────────────────────────────────────────────────────────────
# Data
# ─────────────────────────────────────────────────────────────────────

@dataclass
class NoteEvent:
    """A single note extracted from MIDI."""
    pitch: int
    onset_tick: int
    duration_tick: int
    velocity: int

    @property
    def onset_beat(self) -> float:
        return 0.0  # filled in after extraction

    @property
    def duration_beat(self) -> float:
        return 0.0  # filled in after extraction


@dataclass
class RhythmPattern:
    """Extracted rhythm pattern ready for JSON output."""
    name: str
    onsets: list[float]
    durations: list[float]
    velocities: list[float]
    length_beats: float
    source_file: str = ""
    note_count: int = 0
    ppq: int = 480

    def to_dict(self) -> dict:
        return {
            "onsets": self.onsets,
            "durations": self.durations,
            "velocities": self.velocities,
            "length_beats": self.length_beats,
        }

    def to_json(self, indent: int = 4) -> str:
        return json.dumps(self.to_dict(), indent=indent)


# ─────────────────────────────────────────────────────────────────────
# MIDI reading
# ─────────────────────────────────────────────────────────────────────

def extract_notes(midi_path: str, track_index: Optional[int] = None) -> tuple[list[NoteEvent], int]:
    """
    Extract note events from a MIDI file.

    Args:
        midi_path:    Path to the .mid file
        track_index:  Specific track to extract (None = all tracks)

    Returns:
        (list of NoteEvent, PPQ)
    """
    mid = mido.MidiFile(midi_path)
    ppq = mid.ticks_per_beat

    notes = []
    pending = {}  # note -> onset_tick

    if track_index is not None:
        if track_index >= len(mid.tracks):
            print(f"Error: track {track_index} does not exist. "
                  f"File has {len(mid.tracks)} tracks (0-{len(mid.tracks)-1}).")
            sys.exit(1)
        tracks = [(track_index, mid.tracks[track_index])]
    else:
        tracks = list(enumerate(mid.tracks))

    for tidx, track in tracks:
        abs_tick = 0
        pending = {}
        for msg in track:
            abs_tick += msg.time
            if not hasattr(msg, 'type'):
                continue
            if msg.type == 'note_on' and msg.velocity > 0:
                pending[msg.note] = (abs_tick, msg.velocity)
            elif msg.type == 'note_off' or (msg.type == 'note_on' and msg.velocity == 0):
                if msg.note in pending:
                    onset, vel = pending.pop(msg.note)
                    notes.append(NoteEvent(
                        pitch=msg.note,
                        onset_tick=onset,
                        duration_tick=abs_tick - onset,
                        velocity=vel,
                    ))

    notes.sort(key=lambda n: n.onset_tick)
    return notes, ppq


# ─────────────────────────────────────────────────────────────────────
# Quantization
# ─────────────────────────────────────────────────────────────────────

def quantize_beat(beat: float, resolution: int = 16) -> float:
    """
    Quantize a beat position to the nearest grid line.

    Args:
        beat:       Beat position (float)
        resolution: Grid resolution (16 = 16th notes, 8 = 8th notes)

    Returns:
        Quantized beat position
    """
    grid = 4.0 / resolution  # e.g., 16th = 0.25, 8th = 0.5
    return round(beat / grid) * grid


# ─────────────────────────────────────────────────────────────────────
# Pattern extraction
# ─────────────────────────────────────────────────────────────────────

def extract_pattern(
    notes: list[NoteEvent],
    ppq: int,
    length_beats: Optional[float] = None,
    quantize: int = 16,
    name: str = "rhythm_pattern",
    source_file: str = "",
) -> RhythmPattern:
    """
    Convert note events into a RhythmPattern.

    When length_beats is not specified, attempts to detect a repeating
    loop by analyzing onset spacing patterns.  If a loop is found,
    extracts just one cycle and averages velocities across repetitions.

    Args:
        notes:         List of NoteEvent from MIDI
        ppq:           Pulses per quarter note
        length_beats:  Pattern length in beats (None = auto-detect loop)
        quantize:      Quantization grid (16 = 16th notes, 8 = 8th, 0 = none)
        name:          Pattern name
        source_file:   Source filename for reference

    Returns:
        RhythmPattern
    """
    if not notes:
        return RhythmPattern(
            name=name, onsets=[0.0], durations=[1.0],
            velocities=[0.7], length_beats=4.0, source_file=source_file,
        )

    # Convert ticks to beats
    onsets_raw = [n.onset_tick / ppq for n in notes]
    durations_raw = [n.duration_tick / ppq for n in notes]
    velocities_raw = [n.velocity / 127.0 for n in notes]

    # Normalize onsets relative to pattern start
    first_onset = onsets_raw[0]
    onsets_norm = [o - first_onset for o in onsets_raw]

    # Quantize early so loop detection works on clean values
    if quantize > 0:
        onsets_q = [quantize_beat(o, quantize) for o in onsets_norm]
        durations_q = [max(4.0 / quantize, quantize_beat(d, quantize)) for d in durations_raw]
    else:
        onsets_q = list(onsets_norm)
        durations_q = list(durations_raw)

    # ── Collapse simultaneous notes ───────────────────────────────
    # When multiple notes land on the same beat (chords, double-taps),
    # merge them into a single onset: longest duration, highest velocity.
    if len(onsets_q) > 1:
        collapsed_onsets = [onsets_q[0]]
        collapsed_durations = [durations_q[0]]
        collapsed_velocities = [velocities_raw[0]]
        for i in range(1, len(onsets_q)):
            if abs(onsets_q[i] - collapsed_onsets[-1]) < 0.01:
                # Same beat — merge
                collapsed_durations[-1] = max(collapsed_durations[-1], durations_q[i])
                collapsed_velocities[-1] = max(collapsed_velocities[-1], velocities_raw[i])
            else:
                collapsed_onsets.append(onsets_q[i])
                collapsed_durations.append(durations_q[i])
                collapsed_velocities.append(velocities_raw[i])

        if len(collapsed_onsets) < len(onsets_q):
            removed = len(onsets_q) - len(collapsed_onsets)
            print(f"  Collapsed {removed} simultaneous note(s) → {len(collapsed_onsets)} onsets")

        onsets_q = collapsed_onsets
        durations_q = collapsed_durations
        velocities_raw = collapsed_velocities

    # ── Loop detection ────────────────────────────────────────────
    if length_beats is None:
        detected = _detect_loop(onsets_q, durations_q, velocities_raw)
        if detected is not None:
            cycle_len, n_per_cycle, n_reps = detected
            # Round cycle length to nearest bar
            cycle_len = round_up_to(cycle_len, 4.0)
            length_beats = cycle_len

            # Average velocities across repetitions for the first cycle
            avg_velocities = []
            for i in range(n_per_cycle):
                vels = []
                for rep in range(n_reps):
                    idx = rep * n_per_cycle + i
                    if idx < len(velocities_raw):
                        vels.append(velocities_raw[idx])
                avg_velocities.append(sum(vels) / len(vels))

            # Take just the first cycle
            onsets_q = onsets_q[:n_per_cycle]
            durations_q = durations_q[:n_per_cycle]
            velocities_raw = avg_velocities

            print(f"  Loop detected: {n_per_cycle} notes × {n_reps} repetitions, "
                  f"cycle = {length_beats} beats")
        else:
            # No loop found — use full length
            last_end = max(o + d for o, d in zip(onsets_q, durations_q))
            length_beats = max(4.0, round_up_to(last_end, 4.0))
            print(f"  No loop detected. Using full length: {length_beats} beats")

    # Trim to pattern length
    trimmed_onsets = []
    trimmed_durations = []
    trimmed_velocities = []
    for o, d, v in zip(onsets_q, durations_q, velocities_raw):
        if o < length_beats:
            d = min(d, length_beats - o)
            trimmed_onsets.append(round(o, 4))
            trimmed_durations.append(round(d, 4))
            trimmed_velocities.append(round(v, 2))

    return RhythmPattern(
        name=name,
        onsets=trimmed_onsets,
        durations=trimmed_durations,
        velocities=trimmed_velocities,
        length_beats=length_beats,
        source_file=source_file,
        note_count=len(trimmed_onsets),
        ppq=ppq,
    )


def _detect_loop(
    onsets: list[float],
    durations: list[float],
    velocities: list[float],
    tolerance: float = 0.3,
) -> Optional[tuple[float, int, int]]:
    """
    Detect a repeating loop pattern in a sequence of note onsets.

    Strategy: try dividing the notes into 2, 3, 4, ... equal groups.
    For each candidate group size, check if the onset *intervals* within
    each group match (within tolerance).  The smallest group that matches
    consistently is the loop.

    Args:
        onsets:     Quantized onset positions in beats
        durations:  Note durations in beats
        velocities: Note velocities (0-1)
        tolerance:  Maximum beat deviation to consider a match

    Returns:
        (cycle_length_beats, notes_per_cycle, n_repetitions) or None
    """
    n = len(onsets)
    if n < 4:
        return None

    # Try candidate cycle sizes from smallest to largest
    for notes_per_cycle in range(2, n // 2 + 1):
        if n % notes_per_cycle != 0:
            continue

        n_reps = n // notes_per_cycle

        if n_reps < 2:
            continue

        # Compute the interval pattern for the first cycle
        first_cycle = onsets[:notes_per_cycle]
        first_intervals = [first_cycle[i+1] - first_cycle[i]
                           for i in range(notes_per_cycle - 1)]

        # Also compute the gap from the last note of one cycle to
        # the first note of the next — this is part of the rhythm
        if notes_per_cycle < n:
            cycle_gap = onsets[notes_per_cycle] - onsets[notes_per_cycle - 1]
        else:
            continue

        # Check if all repetitions have the same interval pattern
        match = True
        for rep in range(1, n_reps):
            rep_start = rep * notes_per_cycle
            rep_cycle = onsets[rep_start:rep_start + notes_per_cycle]

            if len(rep_cycle) < notes_per_cycle:
                match = False
                break

            rep_intervals = [rep_cycle[i+1] - rep_cycle[i]
                             for i in range(notes_per_cycle - 1)]

            # Compare intervals
            for a, b in zip(first_intervals, rep_intervals):
                if abs(a - b) > tolerance:
                    match = False
                    break

            if not match:
                break

            # Check the gap between this rep and the previous one
            if rep > 0:
                gap = onsets[rep_start] - onsets[rep_start - 1]
                if abs(gap - cycle_gap) > tolerance:
                    match = False
                    break

        if match:
            # Compute cycle length from first note to first note of next rep
            cycle_length = onsets[notes_per_cycle] - onsets[0]
            return (cycle_length, notes_per_cycle, n_reps)

    return None


def round_up_to(value: float, multiple: float) -> float:
    """Round up to the nearest multiple."""
    import math
    return math.ceil(value / multiple) * multiple


# ─────────────────────────────────────────────────────────────────────
# Display
# ─────────────────────────────────────────────────────────────────────

def print_pattern(pattern: RhythmPattern) -> None:
    """Pretty-print a rhythm pattern."""
    print(f"\n{'─' * 64}")
    print(f"  Pattern: \"{pattern.name}\"")
    if pattern.source_file:
        print(f"  Source:  {pattern.source_file}")
    print(f"  Length:  {pattern.length_beats} beats "
          f"({pattern.length_beats / 4:.0f} bar{'s' if pattern.length_beats > 4 else ''} of 4/4)")
    print(f"  Notes:   {pattern.note_count}")

    print(f"\n  {'#':>3}  {'Onset':>6}  {'Dur':>5}  {'Vel':>5}  {'Visual'}")
    print(f"  {'─':>3}  {'─────':>6}  {'────':>5}  {'────':>5}  {'──────'}")

    grid_width = 48
    for i, (onset, dur, vel) in enumerate(zip(pattern.onsets, pattern.durations, pattern.velocities)):
        # Visual bar showing position and duration
        pos = int(onset / pattern.length_beats * grid_width)
        width = max(1, int(dur / pattern.length_beats * grid_width))
        bar = '·' * pos + '█' * width + '·' * max(0, grid_width - pos - width)

        print(f"  {i+1:3d}  {onset:6.2f}  {dur:5.2f}  {vel:5.2f}  {bar}")

    print(f"{'─' * 64}")


def print_tracks(midi_path: str) -> None:
    """List tracks in a MIDI file."""
    mid = mido.MidiFile(midi_path)
    print(f"\nTracks in {midi_path}:")
    for i, track in enumerate(mid.tracks):
        note_count = sum(1 for m in track
                         if hasattr(m, 'type') and m.type == 'note_on' and m.velocity > 0)
        name = track.name or "(unnamed)"
        print(f"  Track {i}: {name:20s}  {note_count} notes")
    print()


# ─────────────────────────────────────────────────────────────────────
# JSON output for FormaComposition
# ─────────────────────────────────────────────────────────────────────

def format_for_section(pattern: RhythmPattern, field_name: str = "rhythm_pattern") -> str:
    """
    Format the pattern as a JSON block ready to paste into a section definition.

    Returns a string like:
        "rhythm_pattern": {
            "onsets": [0.0, 1.0, 1.5],
            ...
        }
    """
    d = pattern.to_dict()
    inner = json.dumps(d, indent=6)
    # Indent for nesting inside a section
    lines = inner.split('\n')
    indented = '\n'.join('    ' + line for line in lines)
    return f'    "{field_name}": {indented.strip()}'


# ─────────────────────────────────────────────────────────────────────
# CLI
# ─────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="Extract rhythm patterns from MIDI for FormaComposition",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s groove.mid                    Extract pattern (auto-detect length)
  %(prog)s groove.mid --beats 4          Extract 1-bar pattern
  %(prog)s groove.mid --beats 8          Extract 2-bar pattern
  %(prog)s groove.mid --track 0          Extract from specific track
  %(prog)s groove.mid --list-tracks      Show available tracks
  %(prog)s groove.mid --json-only        Output just the JSON block
  %(prog)s groove.mid --name my_groove   Name the pattern
        """,
    )
    parser.add_argument("midi_file", help="Path to MIDI file")
    parser.add_argument("--beats", type=float, default=None,
                        help="Pattern length in beats (default: auto-detect)")
    parser.add_argument("--track", type=int, default=None,
                        help="Track index to extract (default: all)")
    parser.add_argument("--quantize", type=int, default=16, choices=[0, 4, 8, 16, 32],
                        help="Quantize grid (16=16th notes, 0=none)")
    parser.add_argument("--name", type=str, default="rhythm_pattern",
                        help="Pattern name")
    parser.add_argument("--field", type=str, default="rhythm_pattern",
                        help="JSON field name (e.g., 'melody_rhythm' or 'harmony_rhythm')")
    parser.add_argument("--list-tracks", action="store_true",
                        help="List tracks in the MIDI file and exit")
    parser.add_argument("--json-only", action="store_true",
                        help="Output only the JSON block (for piping)")
    parser.add_argument("-o", "--output", type=str, default=None,
                        help="Write pattern to a JSON file (e.g., -o verse_groove.json)")

    args = parser.parse_args()

    if args.list_tracks:
        print_tracks(args.midi_file)
        return

    # Extract notes
    notes, ppq = extract_notes(args.midi_file, track_index=args.track)

    if not notes:
        print(f"No notes found in {args.midi_file}"
              f"{f' track {args.track}' if args.track is not None else ''}.")
        sys.exit(1)

    # Build pattern
    pattern = extract_pattern(
        notes, ppq,
        length_beats=args.beats,
        quantize=args.quantize,
        name=args.name,
        source_file=args.midi_file,
    )

    # Write to file
    if args.output:
        out = {args.field: pattern.to_dict()}
        with open(args.output, 'w') as f:
            json.dump(out, f, indent=2)
        print(f"\n  Written to {args.output}")
        # Still show the visual
        print_pattern(pattern)

    elif args.json_only:
        # Just output the JSON block
        print(format_for_section(pattern, field_name=args.field))
    else:
        # Full display
        print_pattern(pattern)
        print(f"\n  Paste this into your section JSON:\n")
        print(format_for_section(pattern, field_name=args.field))
        print()


if __name__ == "__main__":
    main()
