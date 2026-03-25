"""
generator.py — Intervals Engine
Assembles harmony, bass, melody, and rhythm into a MIDI file.

Takes a theme dict and a piece dict (as parsed from JSON),
runs all voices through their respective modules,
and writes a multi-track MIDI file.

Track layout:
  Track 0 — tempo / time signature metadata
  Track 1 — Melody   (ch 0)
  Track 2 — Counterpoint (ch 1, optional)
  Track 3 — Harmony  (ch 2)
  Track 4 — Bass     (ch 3)


No GM program_change messages are written. Assign instruments
in your DAW (Logic Pro + Arturia V Collection).
"""

import json
import os
from pathlib import Path
from typing import Optional

import mido
from mido import MidiFile, MidiTrack, Message, MetaMessage

from intervals.music.harmony  import resolve_progression, VoicedChord, CHROMATIC
from intervals.music.bass     import generate_bass, BassNote
from intervals.music.melody   import generate_melody_for_progression, MelodyNote
from intervals.music.counterpoint import generate_counterpoint, CounterpointNote
from intervals.music.rhythm   import apply_velocity_arc
from intervals.music.motif    import from_dict as motif_from_dict, to_dict as motif_to_dict, Motif
from intervals.music.prosody  import phrase_to_motif

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

PPQ = 480  # pulses per quarter note — standard resolution

# MIDI channels (0-indexed, channel 9 reserved for drums)
CHANNEL_MELODY       = 0
CHANNEL_HARMONY      = 1
CHANNEL_COUNTERPOINT = 2
CHANNEL_BASS         = 3

# Track names shown in Logic Pro
TRACK_NAME_MELODY       = "Melody"
TRACK_NAME_HARMONY      = "Harmony"
TRACK_NAME_COUNTERPOINT = "Counterpoint"
TRACK_NAME_BASS         = "Bass"

# ---------------------------------------------------------------------------
# Timing helpers
# ---------------------------------------------------------------------------

def beats_to_ticks(beats: float, ppq: int = PPQ) -> int:
    """Convert beats (float) to MIDI ticks."""
    return int(round(beats * ppq))


def bpm_to_tempo(bpm: float) -> int:
    """Convert BPM to MIDI tempo (microseconds per beat)."""
    return int(60_000_000 / bpm)


# ---------------------------------------------------------------------------
# Track builders
# ---------------------------------------------------------------------------

def build_metadata_track(
    bpm: float,
    time_sig_numerator: int = 4,
    time_sig_denominator: int = 4,
    piece_name: str = "Intervals Piece",
) -> MidiTrack:
    """Build track 0 with tempo and time signature."""
    track = MidiTrack()
    track.append(MetaMessage("track_name", name=piece_name, time=0))
    track.append(MetaMessage(
        "time_signature",
        numerator=time_sig_numerator,
        denominator=time_sig_denominator,
        clocks_per_click=24,
        notated_32nd_notes_per_beat=8,
        time=0,
    ))
    track.append(MetaMessage("set_tempo", tempo=bpm_to_tempo(bpm), time=0))
    return track


def build_harmony_track(
    chords: list[VoicedChord],
    bars_per_chord: float,
    beats_per_bar: int,
    density: str,
    velocity: int = 65,
    channel: int = CHANNEL_HARMONY,
    arc: str = "swell",
) -> MidiTrack:
    """
    Build the harmony track — voiced chords with rhythmic timing from density.
    """
    from intervals.music.rhythm import get_pattern, apply_velocity_arc

    track = MidiTrack()
    track.append(MetaMessage("track_name", name=TRACK_NAME_HARMONY, time=0))
    print(TRACK_NAME_HARMONY)
    total_beats_per_chord = bars_per_chord * beats_per_bar

    # Build a flat event list: (absolute_tick, 'on'/'off', notes, velocity)
    events = []

    beat_offset = 0.0
    for chord in chords:
        rhythm_events = get_pattern(total_beats_per_chord, density=density, voice_type="chord")
        arced = apply_velocity_arc(rhythm_events, arc=arc, base_velocity=velocity)

        for ev, vel in arced:
            if ev.is_rest:
                beat_offset_local = beat_offset + ev.start_beat
                continue
            abs_start = beat_offset + ev.start_beat
            abs_end   = abs_start + ev.duration_beats
            for note in chord.midi_notes:
                events.append((abs_start, "on",  note, min(127, vel), channel))
                events.append((abs_end,   "off", note, 0,             channel))

        beat_offset += total_beats_per_chord

    _write_events_to_track(track, events)
    return track


def build_bass_track(
    bass_notes: list[BassNote],
    channel: int = CHANNEL_BASS,
) -> MidiTrack:
    """Build the bass track from a list of BassNote objects."""
    track = MidiTrack()
    print(TRACK_NAME_BASS)
    track.append(MetaMessage("track_name", name=TRACK_NAME_BASS, time=0))

    events = []
    for bn in bass_notes:
        start = bn.start_beat
        end   = start + bn.duration_beats
        events.append((start, "on",  bn.midi_note, bn.velocity,  channel))
        events.append((end,   "off", bn.midi_note, 0,            channel))

    _write_events_to_track(track, events)
    return track


def build_counterpoint_track(
    cp_notes: list[CounterpointNote],
    channel: int = CHANNEL_COUNTERPOINT,
) -> MidiTrack:
    """Build the counterpoint track from a list of CounterpointNote objects."""
    track = MidiTrack()
    track.append(MetaMessage("track_name", name=TRACK_NAME_COUNTERPOINT, time=0))
    print(TRACK_NAME_COUNTERPOINT)

    events = []
    for cn in cp_notes:
        if cn.is_rest or cn.midi_note is None:
            continue
        start = cn.start_beat
        end   = start + cn.duration_beats
        events.append((start, "on",  cn.midi_note, cn.velocity, channel))
        events.append((end,   "off", cn.midi_note, 0,           channel))

    _write_events_to_track(track, events)
    return track


def build_melody_track(
    melody_notes: list[MelodyNote],
    channel: int = CHANNEL_MELODY,
) -> MidiTrack:
    """Build the melody track from a list of MelodyNote objects."""
    track = MidiTrack()
    track.append(MetaMessage("track_name", name=TRACK_NAME_MELODY, time=0))
    print(TRACK_NAME_MELODY)
    events = []
    for mn in melody_notes:
        if mn.is_rest or mn.midi_note is None:
            continue
        start = mn.start_beat
        end   = start + mn.duration_beats
        events.append((start, "on",  mn.midi_note, mn.velocity, channel))
        events.append((end,   "off", mn.midi_note, 0,           channel))

    _write_events_to_track(track, events)
    return track


# ---------------------------------------------------------------------------
# Event writer (absolute → delta time conversion)
# ---------------------------------------------------------------------------

def _write_events_to_track(track: MidiTrack, events: list[tuple]) -> None:
    """
    Sort events by time and write them as delta-time MIDI messages.

    events: list of (abs_beat, 'on'/'off', note, velocity, channel)
    """
    # Sort: by time, then note-offs before note-ons at same tick
    events.sort(key=lambda e: (e[0], 0 if e[1] == "off" else 1))

    current_tick = 0
    for abs_beat, kind, note, vel, channel in events:
        tick = beats_to_ticks(abs_beat)
        delta = tick - current_tick
        current_tick = tick

        if kind == "on":
            track.append(Message("note_on",  note=note, velocity=vel,    channel=channel, time=delta))
        else:
            track.append(Message("note_off", note=note, velocity=0,      channel=channel, time=delta))

    track.append(MetaMessage("end_of_track", time=0))


# ---------------------------------------------------------------------------
# Section assembler
# ---------------------------------------------------------------------------

def generate_section(
    section: dict,
    theme: dict,
    seed_offset: int = 0,
) -> tuple[list[VoicedChord], list[BassNote], list[MelodyNote], float]:
    """
    Generate all voices for a single section.

    Returns:
        (chords, bass_notes, melody_notes, total_beats)
    """
    key          = theme["key"]
    mode         = theme["mode"]
    motif_def    = theme.get("motif")

    progression  = section["progression"]
    bars         = section.get("bars", 8)
    density      = section.get("density", "medium")
    melody_beh   = section.get("melody", "generative")
    bass_style   = section.get("bass_style", "root_fifth")
    beats_per_bar= section.get("beats_per_bar", 4)

    # Distribute bars evenly across chords
    bars_per_chord = bars / len(progression)

    # Resolve chords
    chords = resolve_progression(progression, key, mode, density=density)

    # Resolve motif: explicit motif dict takes precedence, then prosody phrase
    if motif_def is None and theme.get("phrase"):
        # Generate a section-aware motif from the prosody phrase.
        # Uses the first chord of the progression for harmonic context
        # and the section's arc/melody/density for tension profiling.
        prosody_motif = phrase_to_motif(
            theme["phrase"],
            name=theme.get("name", "prosody").lower().replace(" ", "_"),
            section=section,
            chord=progression[0],
            key=key,
            mode=mode,
            seed=42 + seed_offset,
        )
        motif_def = motif_to_dict(prosody_motif)

    # Generate bass
    bass_notes = generate_bass(
        chords,
        style=bass_style,
        bars_per_chord=bars_per_chord,
        beats_per_bar=beats_per_bar,
        density=density,
    )

    # Generate melody
    melody_notes = generate_melody_for_progression(
        chords, key, mode,
        behavior=melody_beh,
        density=density,
        bars_per_chord=bars_per_chord,
        beats_per_bar=beats_per_bar,
        motif=motif_def,
        seed=42 + seed_offset,
    )

    total_beats = bars * beats_per_bar
    return chords, bass_notes, melody_notes, total_beats, bars_per_chord, beats_per_bar, density, section


# ---------------------------------------------------------------------------
# Main generation entry point
# ---------------------------------------------------------------------------

def generate_piece(
    theme: dict,
    piece: dict,
    output_path: str,
) -> str:
    """
    Generate a complete MIDI file from theme + piece dicts.

    Args:
        theme:       Parsed theme dict (from theme.json)
        piece:       Parsed piece dict (from piece.json)
        output_path: File path to write the .mid file

    Returns:
        Absolute path of the written file
    """
    bpm      = piece.get("tempo", (theme["tempo"]["min"] + theme["tempo"]["max"]) // 2)

    sections = piece.get("sections", [])
    if not sections:
        raise ValueError("Piece has no sections defined.")

    # Accumulate all voice events with beat offsets across sections
    all_chord_events  = []   # (abs_beat, 'on'/'off', note, vel, channel)
    all_bass_notes    = []
    all_melody_notes  = []
    all_cp_notes      = []

    global_beat = 0.0

    for i, section in enumerate(sections):
        chords, bass_notes, melody_notes, total_beats, bars_per_chord, beats_per_bar, density, section_dict = \
            generate_section(section, theme, seed_offset=i * 10)

        # Counterpoint (optional — only if section defines it)
        cp_def = section_dict.get("counterpoint")
        if cp_def:
            cp_notes = generate_counterpoint(
                melody_notes,
                key=theme["key"],
                mode=theme["mode"],
                species=cp_def.get("species", "free"),
                register=cp_def.get("register", "below"),
                beats_per_bar=int(section_dict.get("beats_per_bar", 4)),
                velocity=cp_def.get("velocity", 58),
                dissonance=cp_def.get("dissonance", "passing"),
                seed=42 + i * 10,
            )
            for cn in cp_notes:
                cn.start_beat += global_beat
            all_cp_notes.extend(cp_notes)

        # Harmony events
        from intervals.music.rhythm import get_pattern, apply_velocity_arc
        beat_offset_local = 0.0
        total_per_chord = bars_per_chord * beats_per_bar

        for chord in chords:
            rhythm_events = get_pattern(total_per_chord, density=density, voice_type="chord")
            arc = section.get("arc", "swell")
            arced = apply_velocity_arc(rhythm_events, arc=arc, base_velocity=65)
            for ev, vel in arced:
                if ev.is_rest:
                    continue
                abs_start = global_beat + beat_offset_local + ev.start_beat
                abs_end   = abs_start + ev.duration_beats
                for note in chord.midi_notes:
                    all_chord_events.append((abs_start, "on",  note, min(127, vel), CHANNEL_HARMONY))
                    all_chord_events.append((abs_end,   "off", note, 0,             CHANNEL_HARMONY))
            beat_offset_local += total_per_chord

        # Bass notes — offset by global beat
        for bn in bass_notes:
            all_bass_notes.append(BassNote(
                bn.midi_note,
                bn.start_beat + global_beat,
                bn.duration_beats,
                bn.velocity,
            ))

        # Melody notes — offset by global beat
        for mn in melody_notes:
            all_melody_notes.append(MelodyNote(
                mn.midi_note,
                mn.start_beat + global_beat,
                mn.duration_beats,
                mn.velocity,
                mn.is_rest,
            ))

        global_beat += total_beats

    # Build MIDI file
    mid = MidiFile(type=1, ticks_per_beat=PPQ)

    mid.tracks.append(build_metadata_track(
        bpm=bpm,
        piece_name=piece.get("title", "Intervals Piece")
    ))

    # Melody track
    mid.tracks.append(build_melody_track(all_melody_notes))

    # Counterpoint track (only if any sections used it)
    if all_cp_notes:
        mid.tracks.append(build_counterpoint_track(all_cp_notes))

    # Harmony track
    harmony_track = MidiTrack()
    harmony_track.append(MetaMessage("track_name", name=TRACK_NAME_HARMONY, time=0))
    _write_events_to_track(harmony_track, all_chord_events)
    mid.tracks.append(harmony_track)

    # Bass track
    mid.tracks.append(build_bass_track(all_bass_notes))

    # Write file
    output_path = str(Path(output_path).with_suffix(".mid"))
    mid.save(output_path)
    return os.path.abspath(output_path)


# ---------------------------------------------------------------------------
# JSON loaders
# ---------------------------------------------------------------------------

def load_theme(path: str) -> dict:
    with open(path) as f:
        data = json.load(f)
    return data.get("theme", data)


def load_piece(path: str) -> dict:
    with open(path) as f:
        data = json.load(f)
    return data.get("piece", data)


# ---------------------------------------------------------------------------
# Quick test / demo
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import tempfile

    print("=== Intervals Engine — generator.py demo ===\n")

    # Inline theme + piece (no files needed for demo)
    theme = {
        "name": "Evening Water",
        "key": "D",
        "mode": "dorian",
        "tempo": {"min": 60, "max": 80},
        "motif": {
            "name": "evening_water",
            "intervals": [2, -1, 3, -2],
            "rhythm": [1.0, 0.5, 0.5, 1.0],
            "transform_pool": ["inversion", "retrograde", "augmentation"]
        },

    }

    piece = {
        "title": "Still Cove",
        "tempo": 68,
        "sections": [
            {
                "name": "opening",
                "bars": 8,
                "progression": ["i", "VII", "iv", "v"],
                "density": "sparse",
                "melody": "sparse",
                "bass_style": "pedal",
                "arc": "fade_in",
            },
            {
                "name": "swell",
                "bars": 12,
                "progression": ["i", "III", "VII", "i"],
                "density": "medium",
                "melody": "lyrical",
                "bass_style": "root_fifth",
                "arc": "swell",
            },
            {
                "name": "release",
                "bars": 8,
                "progression": ["iv", "i"],
                "density": "sparse",
                "melody": "develop",
                "bass_style": "root_only",
                "arc": "fade_out",
            },
        ]
    }

    out_path = "/mnt/user-data/outputs/still_cove.mid"
    result = generate_piece(theme, piece, out_path)

    mid = MidiFile(result)
    total_ticks = max(
        sum(msg.time for msg in track)
        for track in mid.tracks
    )
    total_beats = total_ticks / PPQ
    total_seconds = mido.tick2second(total_ticks, PPQ, bpm_to_tempo(piece["tempo"]))

    print(f"  Title:    {piece['title']}")
    print(f"  Key:      {theme['key']} {theme['mode']}")
    print(f"  Tempo:    {piece['tempo']} BPM")
    print(f"  Sections: {len(piece['sections'])}")
    print(f"  Tracks:   {len(mid.tracks)} (metadata + harmony + bass + melody)")
    print(f"  Duration: {total_beats:.0f} beats / {total_seconds:.1f} seconds")
    print(f"  Output:   {result}")
    print()
    print("  Track summary:")
    for i, track in enumerate(mid.tracks):
        msg_count = sum(1 for m in track if not m.is_meta)
        print(f"    Track {i}: '{track.name}'  {msg_count} MIDI messages")
