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
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import mido
from mido import MidiFile, MidiTrack, Message, MetaMessage

from intervals.music.harmony  import resolve_progression, VoicedChord, CHROMATIC
from intervals.music.bass     import generate_bass, BassNote
from intervals.music.melody   import generate_melody_for_progression, MelodyNote
from intervals.music.counterpoint import generate_counterpoint, CounterpointNote
from intervals.music.rhythm   import (
    apply_velocity_arc, apply_swing,
    get_pattern, RhythmEvent,
)
from intervals.music.motif    import from_dict as motif_from_dict, to_dict as motif_to_dict, Motif, transform as apply_motif_transform
from intervals.music.prosody  import phrase_to_motif
from intervals.music.percussion import generate_drums, DrumHit
from intervals.music.rhythmic_template import (
    RhythmicTemplate,
)
from intervals.core.motif_loader import resolve_motif_from_theme, resolve_motif_pool_from_theme
from intervals.core.context import (
    PieceContext,
    SectionContext,
    VoiceSnapshot,
    compute_voice_snapshot,
)
from intervals.core.strategies import (
    RhythmStrategyRegistry,
    MelodyStrategyRegistry,
    HarmonyStrategyRegistry,
    HarmonyRhythmContext,
    build_rhythm_context,
    build_melody_context,
    build_harmony_chord_context,
    build_harmony_rhythm_context,
    # Re-imported here so external callers (main.py, tests) don't need to change
    rhythm_pattern_to_events,
    _motif_rhythm_to_events,
    _slice_events_into_window,
)
from intervals.core.schemas import (
    SectionModel,
    ThemeModel,
    PieceModel,
    # Exported Literal sets — replaces VALID_DENSITY etc. defined below
    VALID_DENSITY,
    VALID_MELODY_BEH,
    VALID_BASS_STYLE,
    VALID_ARC,
    VALID_RHYTHM_SOURCE,
    VALID_HARMONY_RHYTHM_SOURCE,
    VALID_TRANSFORMS,
)
from intervals.core.strategies_typed import (
    build_rhythm_context_from_model,
    build_harmony_rhythm_context_from_model,
    build_melody_context_from_model,
)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

PPQ = 480  # pulses per quarter note — standard resolution

# MIDI channels (0-indexed, channel 9 reserved for drums)
CHANNEL_MELODY       = 0
CHANNEL_HARMONY      = 1
CHANNEL_COUNTERPOINT = 2
CHANNEL_BASS         = 3
CHANNEL_DRUMS        = 9

# Track names shown in Logic Pro
TRACK_NAME_MELODY       = "Melody"
TRACK_NAME_HARMONY      = "Harmony"
TRACK_NAME_COUNTERPOINT = "Counterpoint"
TRACK_NAME_BASS         = "Bass"
TRACK_NAME_DRUMS        = "Drums"

# ---------------------------------------------------------------------------
# Section result contract
# ---------------------------------------------------------------------------

@dataclass
class SectionResult:
    """
    Typed return value from generate_section().

    Replaces the anonymous 9-element tuple, eliminating positional coupling
    between the producer (generate_section) and consumer (generate_piece).

    Fields
    ------
    chords                 : Voiced chord objects for each chord slot.
    bass_notes             : BassNote objects for this section (beat-local).
    melody_notes           : MelodyNote objects for this section (beat-local).
    total_beats            : Total duration of the section in beats.
    bars_list              : Per-chord bar durations (length == len(chords)).
    beats_per_bar          : Time signature numerator (usually 4).
    density                : Density literal used ("sparse" | "medium" | "full").
    section_model          : The validated SectionModel instance (source of truth
                             for all section metadata; prefer over the raw dict).
    harmony_section_events : Pre-computed harmony rhythm events, or None (free),
                             or the sentinel string "sustain".
    """
    chords:                 list[VoicedChord]
    bass_notes:             list[BassNote]
    melody_notes:           list[MelodyNote]
    total_beats:            float
    bars_list:              list[float]
    beats_per_bar:          int
    density:                str
    section_model:          "SectionModel"
    harmony_section_events: "list[RhythmEvent] | str | None"


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

def _midi_safe(text: str) -> str:
    """Sanitize text for MIDI meta messages (latin-1 only)."""
    return text.encode("latin-1", errors="replace").decode("latin-1")


def build_metadata_track(
    bpm: float,
    time_sig_numerator: int = 4,
    time_sig_denominator: int = 4,
    piece_name: str = "Intervals Piece",
) -> MidiTrack:
    """Build track 0 with tempo and time signature."""
    track = MidiTrack()
    track.append(MetaMessage("track_name", name=_midi_safe(piece_name), time=0))
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


def build_drums_track(
    drum_hits: list[DrumHit],
    channel: int = CHANNEL_DRUMS,
) -> MidiTrack:
    """Build the drums track from a list of DrumHit objects on channel 9 (GM drums)."""
    track = MidiTrack()
    track.append(MetaMessage("track_name", name=TRACK_NAME_DRUMS, time=0))
    print(TRACK_NAME_DRUMS)

    events = []
    for dh in drum_hits:
        start = dh.start_beat
        end   = start + dh.duration_beats
        events.append((start, "on",  dh.midi_note, dh.velocity, channel))
        events.append((end,   "off", dh.midi_note, 0,           channel))

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
# Hand-played rhythm pattern support
# ---------------------------------------------------------------------------

# rhythm_pattern_to_events, _motif_rhythm_to_events, and _slice_events_into_window
# have been moved to intervals/core/strategies.py to avoid circular imports.
# They are re-imported above and remain accessible from this module for
# backward compatibility with any external callers.


# ---------------------------------------------------------------------------
# Section assembler
# ---------------------------------------------------------------------------

def generate_section(
    section: dict,
    theme: dict,
    base_seed: int = 42,
    seed_offset: int = 0,
    sec_ctx: Optional[SectionContext] = None,
    piece_ctx: Optional[PieceContext] = None,
    transform_sequence: Optional[list[str]] = None,
) -> SectionResult:
    """
    Generate all voices for a single section.

    Args:
        section:             Section dict from piece JSON
        theme:               Theme dict
        base_seed:           Base seed for reproducibility (from piece JSON, defaults to 42)
        seed_offset:         Seed offset for reproducibility (per-section variation)
        sec_ctx:             SectionContext for cross-voice awareness (optional)
        piece_ctx:           PieceContext for cross-section memory (optional)
        transform_sequence:  Explicit motif transform plan from piece JSON (optional)

    Returns:
        SectionResult with all generated voice data and section metadata.
    """
    key          = theme["key"]
    mode         = theme["mode"]

    # Validate and coerce the raw section dict once — all downstream code
    # uses the typed model via the _from_model factory functions.
    from pydantic import ValidationError as _PydanticValidationError
    try:
        section_model = SectionModel.model_validate(section)
    except _PydanticValidationError as exc:
        raise ValueError(
            f"Section '{section.get('name', '?')}' failed validation:\n{exc}"
        ) from exc

    # Resolve motif — single primary (for rhythm + transform) and full pool (for melody variety)
    motif_obj = resolve_motif_from_theme(theme)
    motif_def = motif_to_dict(motif_obj) if motif_obj else None
    motif_pool = resolve_motif_pool_from_theme(theme)  # list of dicts; primary is [0]

    # When using theme.motifs array, resolve_motif_from_theme returns None
    # (it only reads theme.motif). Use the first pool entry as the primary.
    if motif_def is None and motif_pool:
        motif_def = motif_pool[0]

    progression  = section_model.progression
    bars         = section_model.bars or 8.0
    density      = section_model.density
    melody_beh   = section_model.melody
    bass_style   = section_model.bass_style
    beats_per_bar= section_model.beats_per_bar
    groove       = section_model.groove
    swing        = section_model.swing

    # Per-chord bar durations — model helper handles chord_bars vs bars logic
    bars_list = section_model.bars_list()

    # Resolve chords
    chords = resolve_progression(progression, key, mode, density=density)

    # ── Compute section totals (used for snapshots) ───────────────
    total_beats_section = sum(b * beats_per_bar for b in bars_list)
    total_slots = int(total_beats_section * 2)  # 8th-note resolution

    rhythm_source = section.get("rhythm", "free")  # required — validator enforces

    # Normalize harmony_rhythm: if someone wrote "harmony_rhythm": "sustain"
    # (bare string), convert to {"rhythm": "sustain"} so all downstream
    # code can safely call .get() on it. The validator will have already
    # flagged this as an error, but we don't crash during generation.
    _hr_raw = section.get("harmony_rhythm", {})
    if isinstance(_hr_raw, str):
        _hr_normalized = {"rhythm": _hr_raw}
    else:
        _hr_normalized = _hr_raw

    # ── Resolve active motif for this section ────────────────────────
    # transform_sequence selects a named transform by section index.
    # The transformed motif drives ALL voices — melody, harmony, bass —
    # so the selection must happen before rhythm events are computed.
    # "original" is a valid sequence value meaning no transform applied.
    active_motif_def = motif_def  # default: original
    active_transform_name = None

    if motif_def and transform_sequence and piece_ctx is not None:
        pool = motif_def.get("transform_pool", [])
        section_index = sec_ctx.section_index if sec_ctx else 0
        active_transform_name = piece_ctx.suggest_transform(
            available=pool,
            transform_sequence=transform_sequence,
            section_index=section_index,
        )
        if active_transform_name and active_transform_name != "original":
            motif_obj_active = motif_from_dict(motif_def)
            transformed = apply_motif_transform(
                motif_obj_active, active_transform_name,
                seed=base_seed + seed_offset,
            )
            active_motif_def = motif_to_dict(transformed)
            print(f"    Motif transform: {active_transform_name} "
                  f"→ intervals={active_motif_def['intervals']} "
                  f"rhythm={active_motif_def['rhythm']}")
        else:
            print(f"    Motif transform: original")

    # ── Melody + bass rhythm (explicit switch on section.rhythm) ────
    melody_rhythm_events = None
    bass_rhythm_events   = None

    if rhythm_source == "pattern":
        rp = section.get("rhythm_pattern")
        if rp:
            melody_rhythm_events = rhythm_pattern_to_events(rp, total_beats=total_beats_section)
            bass_rhythm_events   = melody_rhythm_events
            print(f"    Melody/Bass rhythm: hand-played pattern "
                  f"({len(rp['onsets'])} onsets, {rp.get('length_beats','?')}b)")

    elif rhythm_source == "motif":
        melody_rhythm_events = _motif_rhythm_to_events(
            active_motif_def["rhythm"], total_beats_section, "full",
            velocities=active_motif_def.get("velocities"),
        )
        bass_rhythm_events = _motif_rhythm_to_events(
            active_motif_def["rhythm"], total_beats_section, "anchor",
            velocities=active_motif_def.get("velocities"),
        )
        cycle = sum(active_motif_def["rhythm"])
        print(f"    Melody rhythm: motif full   ({len(active_motif_def['rhythm'])} notes, {cycle:.1f}b cycle)")
        print(f"    Bass rhythm:   motif anchor ({len(bass_rhythm_events)} triggers, {cycle:.1f}b cycle)")

    else:  # "free"
        print(f"    Melody/Bass rhythm: free (density grid)")

    # ── Harmony section events (explicit switch on harmony_rhythm.rhythm) ─
    hr_block = _hr_normalized
    h_rhythm_source = hr_block.get("rhythm", rhythm_source)

    harmony_section_events = None  # None → free; "sustain" → sustain sentinel

    if h_rhythm_source == "sustain":
        harmony_section_events = "sustain"
        print(f"    Harmony rhythm: sustain")

    elif h_rhythm_source == "pattern":
        hp = section.get("harmony_pattern")
        if hp:
            harmony_section_events = rhythm_pattern_to_events(hp, total_beats=total_beats_section)
            print(f"    Harmony rhythm: hand-played pattern ({len(hp['onsets'])} onsets)")

    elif h_rhythm_source == "motif":
        harmony_section_events = _motif_rhythm_to_events(
            active_motif_def["rhythm"], total_beats_section, "stressed",
            velocities=active_motif_def.get("velocities"),
        )
        cycle = sum(active_motif_def["rhythm"])
        print(f"    Harmony rhythm: motif stressed ({len(harmony_section_events)} triggers, {cycle:.1f}b cycle)")

    else:  # "free"
        harmony_section_events = None
        print(f"    Harmony rhythm: free (density grid)")

    # ══════════════════════════════════════════════════════════════
    # BASS — generates first, writes snapshot for downstream voices
    # ══════════════════════════════════════════════════════════════
    bass_notes = generate_bass(
        chords,
        style=bass_style,
        bars_per_chord=bars_list,
        beats_per_bar=beats_per_bar,
        density=density,
        key=key,
        mode=mode,
        seed=base_seed + seed_offset,
        rhythm_events_override=bass_rhythm_events,
    )

    # Record bass snapshot so melody/counterpoint can read it
    if sec_ctx is not None:
        sec_ctx.add_voice("bass", compute_voice_snapshot(
            pitches=[bn.midi_note for bn in bass_notes],
            durations=[bn.duration_beats for bn in bass_notes],
            total_beats=total_beats_section,
            total_slots=total_slots,
            last_chord_degree=progression[-1],
            key=key,
            mode=mode,
        ))

    # ══════════════════════════════════════════════════════════════
    # MELODY — generates second, can read bass snapshot
    # ══════════════════════════════════════════════════════════════

    if motif_pool and len(motif_pool) > 1:
        print(f"    Motif pool: {len(motif_pool)} motifs "
              f"({', '.join(m.get('name', '?') for m in motif_pool)})")

    melody_notes = generate_melody_for_progression(
        chords, key, mode,
        behavior=melody_beh,
        density=density,
        bars_per_chord=bars_list,
        beats_per_bar=beats_per_bar,
        motif=active_motif_def,
        motif_pool=motif_pool if len(motif_pool) > 1 else None,
        groove=groove,
        swing=swing,
        seed=base_seed + seed_offset,
        section_name=section_model.name or "",
        rhythm_events_override=melody_rhythm_events,
        fugal_techniques=section_model.fugal_techniques,
        rest_probability=section_model.rest_probability,
    )

    # Record melody snapshot for counterpoint and next-section memory
    if sec_ctx is not None:
        melody_pitches = [mn.midi_note for mn in melody_notes
                          if not mn.is_rest and mn.midi_note is not None]
        melody_durations = [mn.duration_beats for mn in melody_notes
                            if not mn.is_rest and mn.midi_note is not None]
        sec_ctx.add_voice("melody", compute_voice_snapshot(
            pitches=melody_pitches,
            durations=melody_durations,
            total_beats=total_beats_section,
            total_slots=total_slots,
            last_transform=active_transform_name,
            last_chord_degree=progression[-1],
            key=key,
            mode=mode,
        ))

    total_beats = bars * beats_per_bar
    return SectionResult(
        chords=chords,
        bass_notes=bass_notes,
        melody_notes=melody_notes,
        total_beats=total_beats,
        bars_list=bars_list,
        beats_per_bar=beats_per_bar,
        density=density,
        section_model=section_model,
        harmony_section_events=harmony_section_events,
    )


# ---------------------------------------------------------------------------
# Chord context builder (statefulness pattern)
# ---------------------------------------------------------------------------

def create_chord_context(
    chord_index: int,
    chords: list[VoicedChord],
    bars_per_chord: list[float],
    beats_per_bar: int,
    section_name: str = "",
) -> dict:
    """
    Build context dict for a single chord in a progression.
    Passed to melody/bass/counterpoint generators for awareness of
    position, next chord, and section context.

    Args:
        chord_index:      Index of current chord in progression
        chords:           Full list of VoicedChord in progression
        bars_per_chord:   List of bar durations per chord
        beats_per_bar:    Beats per bar (usually 4)
        section_name:     Name of section (e.g., "bloom", "return")

    Returns:
        Dict with chord context for generators
    """
    next_idx = (chord_index + 1) % len(chords)
    return {
        "chord_index": chord_index,
        "total_chords": len(chords),
        "next_chord": chords[next_idx],
        "next_chord_root": chords[next_idx].root_name,
        "bars_in_this_chord": bars_per_chord[chord_index],
        "bars_in_next_chord": bars_per_chord[next_idx],
        "section_name": section_name,
    }


# ---------------------------------------------------------------------------
# Song form helpers
# ---------------------------------------------------------------------------

def _expand_song_form(piece: dict) -> list[dict]:
    """
    Expand a song form structure into an ordered list of sections.

    Input piece format:
    {
      "form_type": "song",
      "form": [
        { "section": "verse_A", "variation": 0.0 },
        { "section": "verse_A", "variation": 0.2 },
        { "section": "chorus", "variation": 0.0 },
        ...
      ],
      "sections": {
        "verse_A": { "bars": 12, "progression": [...], ... },
        "chorus": { "bars": 8, "progression": [...], ... },
        ...
      }
    }

    Returns: Flattened list of section dicts with variation applied
    """
    form_array = piece.get("form", [])
    section_defs = piece.get("sections", {})

    if not form_array:
        raise ValueError("Song form specified but no 'form' array provided.")
    if not section_defs:
        raise ValueError("Song form specified but no 'sections' dict provided.")

    expanded = []
    for form_item in form_array:
        if isinstance(form_item, str):
            # Simple string reference: "verse_A"
            section_name = form_item
            variation = 0.0
        else:
            # Dict with section name and variation
            section_name = form_item.get("section")
            variation = form_item.get("variation", 0.0)

        if section_name not in section_defs:
            raise ValueError(f"Song form references undefined section: '{section_name}'")

        # Get base section definition
        base_section = section_defs[section_name]

        # Apply variation
        if variation > 0.0:
            section = _apply_variation(base_section, variation)
        else:
            section = dict(base_section)  # Exact copy for 0.0 variation

        expanded.append(section)

    return expanded


def _apply_variation(section: dict, variation: float) -> dict:
    """
    Apply variation to a section (0.0 = exact, 1.0 = maximum change).

    Variation affects:
    - 0.0-0.2:   Melody might shift slightly (sparse→lyrical)
    - 0.3-0.5:   Density might increase, melody behavior changes
    - 0.6-1.0:   Major changes: behavior, density, add/remove counterpoint
    """
    import random
    import copy

    varied = copy.deepcopy(section)

    if variation <= 0.0:
        return varied

    # Seed with variation amount for reproducibility
    random.seed(int(variation * 1000))

    # Melody behavior shifts (higher variation = more change)
    melody_behaviors = ["sparse", "generative", "lyrical", "develop"]
    original_melody = varied.get("melody", "generative")

    if variation > 0.15:
        # Slight shift in melody behavior
        if original_melody in melody_behaviors:
            idx = melody_behaviors.index(original_melody)
            # Shift by 1 position (circular)
            new_idx = (idx + random.randint(0, 1)) % len(melody_behaviors)
            if new_idx != idx:
                varied["melody"] = melody_behaviors[new_idx]

    # Density might shift with higher variation
    if variation > 0.4:
        densities = ["sparse", "medium", "full"]
        original_density = varied.get("density", "medium")
        if original_density in densities:
            idx = densities.index(original_density)
            if variation > 0.6 and idx < len(densities) - 1:
                # Increase density slightly
                varied["density"] = densities[idx + 1]

    # Arc might shift
    if variation > 0.5:
        arcs = ["fade_in", "swell", "breath", "fade_out"]
        original_arc = varied.get("arc", "swell")
        if original_arc in arcs and variation > 0.7:
            idx = arcs.index(original_arc)
            if idx < len(arcs) - 1:
                varied["arc"] = arcs[idx + 1]

    # Add counterpoint if none exists, high variation
    if variation > 0.7 and "counterpoint" not in varied:
        varied["counterpoint"] = {
            "species": "free",
            "register": "below",
            "dissonance": "passing",
            "velocity": 54
        }

    return varied


# ---------------------------------------------------------------------------
# Harmony rhythm resolution helpers
# ---------------------------------------------------------------------------
# _resolve_harmony_rhythm, _slice_events_into_window and _motif_rhythm_to_events
# have been moved to intervals/core/strategies.py to break circular imports.
# They are re-imported at the top of this file and remain callable here.
# _resolve_harmony_rhythm has been removed — its logic now lives entirely
# in the HarmonyStrategy subclasses (SustainHarmonyStrategy, FreeHarmonyStrategy,
# PatternHarmonyStrategy, MotifHarmonyStrategy).


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
    Supports both narrative arcs and song forms.

    Creates PieceContext for cross-section memory and SectionContext
    per section for cross-voice awareness.

    Args:
        theme:       Parsed theme dict (from theme.json)
        piece:       Parsed piece dict (from piece.json)
        output_path: File path to write the .mid file

    Returns:
        Absolute path of the written file
    """
    # Validate theme + piece via Pydantic models before generation.
    # ThemeModel / PieceModel raise ValidationError with field-level detail;
    # we convert to ValueError so callers that catch ValueError still work.
    from pydantic import ValidationError as _PydanticValidationError
    try:
        theme_model = ThemeModel.model_validate(theme)
        piece_model = PieceModel.model_validate(piece)
        # Cross-model checks: rhythm='motif' requires theme motif.rhythm, etc.
        piece_model.validate_against_theme(theme_model)
    except _PydanticValidationError as exc:
        raise ValueError(
            f"Validation failed before generation:\n{exc}"
        ) from exc

    bpm      = piece.get("tempo", (theme["tempo"]["min"] + theme["tempo"]["max"]) // 2)
    base_seed = piece.get("seed", 42)  # Optional seed parameter, defaults to 42

    # Determine form type (song or narrative)
    form_type = piece.get("form_type", "narrative")

    if form_type == "song":
        # Song form: expand "form" array into ordered sections with variation
        sections = _expand_song_form(piece)
    else:
        # Narrative form: sections are already defined in order
        sections = piece.get("sections", [])

    if not sections:
        raise ValueError("Piece has no sections defined.")

    # ══════════════════════════════════════════════════════════════
    # CREATE PIECE CONTEXT — cross-section compositional memory
    # ══════════════════════════════════════════════════════════════
    piece_ctx = PieceContext(
        total_sections=len(sections),
        key=theme["key"],
        mode=theme["mode"],
    )

    # Optional explicit transform plan from piece JSON
    transform_sequence = piece.get("transform_sequence")

    # Accumulate all voice events with beat offsets across sections
    all_chord_events  = []   # (abs_beat, 'on'/'off', note, vel, channel)
    all_bass_notes    = []
    all_melody_notes  = []
    all_cp_notes      = []
    all_drum_hits     = []

    global_beat = 0.0

    for i, section in enumerate(sections):

        # ══════════════════════════════════════════════════════════
        # CREATE SECTION CONTEXT — cross-voice awareness scratchpad
        # ══════════════════════════════════════════════════════════
        sec_ctx = piece_ctx.make_section_context(section, i)

        # In song forms, the same section may repeat with variation.
        # Use section index for seed to ensure variation is deterministic.
        res = generate_section(
            section, theme, base_seed=base_seed, seed_offset=i * 10,
            sec_ctx=sec_ctx, piece_ctx=piece_ctx,
            transform_sequence=transform_sequence,
        )

        chords                 = res.chords
        bass_notes             = res.bass_notes
        melody_notes           = res.melody_notes
        total_beats            = res.total_beats
        bars_list              = res.bars_list
        beats_per_bar          = res.beats_per_bar
        density                = res.density
        section_model          = res.section_model
        harmony_section_events = res.harmony_section_events

        # section_dict: raw dict still needed for a few optional fields
        # (drums, counterpoint, arc) that are not yet on SectionModel.
        # Derive it from the validated model's own dict to keep a single
        # source of truth and avoid re-reading the raw section arg.
        section_dict = section_model.model_dump(exclude_none=True)

        # Section-level rhythm defaults (used by melody, bass)
        groove = section_dict.get("groove")
        swing  = section_dict.get("swing", 0.0)

        # Counterpoint (optional — only if section defines it)
        cp_model = section_model.counterpoint
        if cp_model is not None:
            cp_notes = generate_counterpoint(
                melody_notes,
                key=theme["key"],
                mode=theme["mode"],
                beats_per_bar=section_model.beats_per_bar,
                seed=base_seed + i * 10,
                cp_model=cp_model,
            )

            # Canon offset: shift counterpoint forward in time.
            canon_offset = cp_model.canon_offset
            if canon_offset > 0:
                for cn in cp_notes:
                    cn.start_beat += canon_offset
                # Trim notes that now extend past section boundary
                cp_notes = [cn for cn in cp_notes
                            if cn.start_beat < total_beats]

            # Record counterpoint snapshot
            if sec_ctx is not None:
                cp_pitches = [cn.midi_note for cn in cp_notes
                              if not cn.is_rest and cn.midi_note is not None]
                cp_durations = [cn.duration_beats for cn in cp_notes
                                if not cn.is_rest and cn.midi_note is not None]
                _tb = sum(b * beats_per_bar for b in bars_list)
                sec_ctx.add_voice("counterpoint", compute_voice_snapshot(
                    pitches=cp_pitches,
                    durations=cp_durations,
                    total_beats=_tb,
                    total_slots=int(_tb * 2),
                    key=theme["key"], mode=theme["mode"],
                ))

            for cn in cp_notes:
                cn.start_beat += global_beat
            all_cp_notes.extend(cp_notes)

        # ── Harmony events — pure strategy dispatch, zero if/else ───────────
        # HarmonyRhythmContext absorbs all HR overrides (density/groove/swing).
        # HarmonyStrategyRegistry selects the correct implementation from ctx.source.
        # The loop body is clean: build context → dispatch → extend.

        arc = section.get("arc", "swell")
        beat_offset_local = 0.0

        for ci, chord in enumerate(chords):
            total_per_chord = bars_list[ci] * beats_per_bar

            hrctx = build_harmony_rhythm_context(
                section=section_dict,
                active_motif_def=None,   # motif rhythm already in precomputed_events
                total_beats_section=total_beats,
                total_per_chord=total_per_chord,
                beat_offset=beat_offset_local,
                precomputed_events=harmony_section_events,
            )
            hctx = build_harmony_chord_context(
                harmony_rhythm_ctx=hrctx,
                chord=chord,
                global_beat=global_beat,
                beat_offset_local=beat_offset_local,
                arc=arc,
            )
            all_chord_events.extend(
                HarmonyStrategyRegistry.resolve(hrctx.source).apply(hctx)
            )
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

        # Drums (optional — only if section defines it)
        drum_model = section_model.drums
        if drum_model is not None:
            # DrumModel.resolve() applies section-level density/groove/swing
            # as fallbacks for any field left as None on the model.
            drums_density, drums_groove, drums_swing = drum_model.resolve(
                section_density=density,
                section_groove=section_model.groove,
                section_swing=section_model.swing,
            )

            drum_hits = generate_drums(
                total_beats=total_beats,
                bass_notes=bass_notes,
                pattern=drum_model.pattern,
                density=drums_density,
                groove=drums_groove,
                swing=drums_swing,
                beats_per_bar=section_model.beats_per_bar,
                seed=base_seed + i * 10,
            )

            # Offset drum hits by global beat
            for dh in drum_hits:
                all_drum_hits.append(DrumHit(
                    midi_note=dh.midi_note,
                    start_beat=dh.start_beat + global_beat,
                    duration_beats=dh.duration_beats,
                    velocity=dh.velocity,
                ))

        global_beat += total_beats

        # ══════════════════════════════════════════════════════════
        # FREEZE SECTION — store in piece history for next section
        # ══════════════════════════════════════════════════════════
        piece_ctx.complete_section(sec_ctx)

    # ── Log context summary ───────────────────────────────────────
    print(f"\n  Context summary:")
    print(f"    Sections completed: {len(piece_ctx.completed_sections)}")
    if piece_ctx.transform_history:
        print(f"    Transform history:  {piece_ctx.transform_history}")
        print(f"    Transform counts:   {piece_ctx.transforms_used()}")
    for ss in piece_ctx.completed_sections:
        voices_str = ", ".join(
            f"{name}(pitch={v.last_pitch}, contour={v.ending_contour}, "
            f"density={v.achieved_density:.2f})"
            for name, v in ss.voices.items()
            if v.last_pitch is not None
        )
        print(f"    [{ss.section_name}] {voices_str}")

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

    # Drums track (only if any sections used it)
    if all_drum_hits:
        mid.tracks.append(build_drums_track(all_drum_hits, channel=CHANNEL_DRUMS))

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
        "transform_sequence": ["original", "inversion", "retrograde"],
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
