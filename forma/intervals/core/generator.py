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
from intervals.music.rhythm   import RhythmEvent
from intervals.music.motif    import from_dict as motif_from_dict, to_dict as motif_to_dict, Motif, transform as apply_motif_transform
from intervals.music.percussion import generate_drums, DrumHit

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
    build_harmony_chord_context,
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
CHANNEL_COUNTERPOINT_2 = 4
CHANNEL_COUNTERPOINT_3 = 5
CHANNEL_DRUMS        = 9

# Program numbers — one unique value per voice so Logic Pro creates
# separate software instrument tracks on import (program_change at tick 0).
# Values are arbitrary; no GM instrument is implied.
PROGRAM_MELODY       = 0
PROGRAM_HARMONY      = 1
PROGRAM_COUNTERPOINT = 2
PROGRAM_BASS         = 3
PROGRAM_DRUMS        = 0   # channel 9 ignores program in GM, but emit for completeness

# Track names shown in Logic Pro
TRACK_NAME_MELODY       = "Melody"
TRACK_NAME_HARMONY      = "Harmony"
TRACK_NAME_COUNTERPOINT = "Counterpoint"
TRACK_NAME_COUNTERPOINT_2 = "Counterpoint 2"
TRACK_NAME_COUNTERPOINT_3 = "Counterpoint 3"
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
# Arc-driven velocity envelopes (composer behavior)
# ---------------------------------------------------------------------------

# Velocity clamp range applied after the arc multiplier (MIDI velocity units)
VELOCITY_CLAMP_MIN = 40
VELOCITY_CLAMP_MAX = 120


def velocity_envelope(arc: str, bar_index: int, total_bars: int) -> float:
    """
    Return a velocity multiplier (0.6–1.25) for a bar position within a
    section, shaped by the section's declared arc. This is what makes
    "arc" an audible dynamic curve rather than a label.

    Curves (t = 0.0 at first bar, 1.0 at final bar):
      swell:    0.75 → 1.10, quadratic rise
      build:    0.70 → 1.20, quadratic rise steeper than swell
      fade_out / fade: 1.00 → 0.65, linear fall
      fade_in:  0.65 → 1.00, linear rise
      breath:   arch — 0.85 at the edges, peaking 1.15 at midpoint
      plateau:  flat 1.0
      decay:    0.95 → 0.70, gradual linear fall
      anything else: 1.0 (neutral — guarantees no change for unknown arcs)
    """
    if total_bars <= 1:
        t = 0.0
    else:
        t = bar_index / (total_bars - 1)
    t = max(0.0, min(1.0, t))

    if arc == "swell":
        m = 0.75 + 0.35 * (t ** 2)
    elif arc == "build":
        m = 0.70 + 0.50 * (t ** 2)
    elif arc in ("fade_out", "fade"):
        m = 1.00 - 0.35 * t
    elif arc == "fade_in":
        m = 0.65 + 0.35 * t
    elif arc == "breath":
        import math as _math
        m = 0.85 + 0.30 * _math.sin(_math.pi * t)
    elif arc == "plateau":
        m = 1.0
    elif arc == "decay":
        m = 0.95 - 0.25 * t
    else:
        m = 1.0

    return max(0.6, min(1.25, m))


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



def build_bass_track(
    bass_notes: list[BassNote],
    channel: int = CHANNEL_BASS,
) -> MidiTrack:
    """Build the bass track from a list of BassNote objects."""
    track = MidiTrack()
    print(TRACK_NAME_BASS)
    track.append(MetaMessage("track_name", name=TRACK_NAME_BASS, time=0))
    track.append(Message("program_change", program=PROGRAM_BASS, channel=channel, time=0))

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
    track_name: str = TRACK_NAME_COUNTERPOINT,
    program: int = PROGRAM_COUNTERPOINT,
) -> MidiTrack:
    """
    Build a counterpoint track from a list of CounterpointNote objects.

    Each independent counterpoint voice gets its own track/channel so they
    can be routed to separate instruments in Logic, the same way Melody,
    Harmony, and Bass already are. Callers pass a distinct channel/name
    per voice when a section defines more than one counterpoint voice.
    """
    track = MidiTrack()
    track.append(MetaMessage("track_name", name=track_name, time=0))
    track.append(Message("program_change", program=program, channel=channel, time=0))
    print(track_name)

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
    track.append(Message("program_change", program=PROGRAM_MELODY, channel=channel, time=0))
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
    track.append(Message("program_change", program=PROGRAM_DRUMS, channel=channel, time=0))
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
            # Defensive clamp: mido raises ValueError for any data byte outside
            # 0..127, which crashes the whole render deep inside MIDI writing —
            # the worst possible place to discover an upstream scaling bug.
            # The real fix is to stop bad velocities from being produced in the
            # first place (see MotifModel/RhythmPatternModel validation in
            # schemas.py); this clamp is just insurance so a stray bad value
            # degrades gracefully instead of crashing the render.
            safe_vel = max(1, min(127, int(vel)))
            if safe_vel != vel:
                print(f"    WARNING: clamped out-of-range velocity {vel} -> {safe_vel} "
                      f"(note={note}, beat={abs_beat:.2f}, channel={channel})")
            track.append(Message("note_on",  note=note, velocity=safe_vel, channel=channel, time=delta))
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
    # Validate and coerce the raw section dict once — all downstream code
    # uses the typed model via the _from_model factory functions.
    from pydantic import ValidationError as _PydanticValidationError
    try:
        section_model = SectionModel.model_validate(section)
    except _PydanticValidationError as exc:
        raise ValueError(
            f"Section '{section.get('name', '?')}' failed validation:\n{exc}"
        ) from exc

    key  = section_model.key  or theme["key"]
    mode = section_model.mode or theme["mode"]

    if section_model.key or section_model.mode:
        print(f"    Key/mode override: {key} {mode}")

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

    rhythm_source = section_model.rhythm

    # harmony_rhythm is already a validated HarmonyRhythmModel (or None).
    # The Pydantic validator _coerce_harmony_rhythm rejects bare strings at
    # load time, so no isinstance normalisation is needed here.
    _hr_model = section_model.harmony_rhythm

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
            total_sections=sec_ctx.total_sections if sec_ctx else None,
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
        rp_model = section_model.rhythm_pattern
        if rp_model:
            rp = rp_model.model_dump(exclude_none=True)
            melody_rhythm_events = rhythm_pattern_to_events(rp, total_beats=total_beats_section)
            bass_rhythm_events   = melody_rhythm_events
            print(f"    Melody/Bass rhythm: hand-played pattern "
                  f"({len(rp['onsets'])} onsets, {rp.get('length_beats','?')}b)")

    elif rhythm_source == "motif":
        melody_rhythm_events = _motif_rhythm_to_events(
            active_motif_def["rhythm"], total_beats_section, "full",
            velocities=active_motif_def.get("velocities"),
            rests=active_motif_def.get("rests"),
        )
        # Decouple pass (2026-07): bass_rhythm_events is deliberately NOT
        # built here anymore. It used to carry the motif's "anchor" grid
        # into generate_bass(), whose override path bypassed style dispatch
        # for every bass_style except "motif" — so rhythm: "motif" +
        # bass_style: "steady" silently produced anchor roots instead of the
        # declared steady figure. Explicit beats implicit: bass_style always
        # wins now. (bass_style: "motif" never used this path anyway — it
        # reads the motif dict directly in style_motif.) Hand-played
        # "pattern" rhythm still drives the bass above, unchanged.
        cycle = sum(active_motif_def["rhythm"])
        print(f"    Melody rhythm: motif full   ({len(active_motif_def['rhythm'])} notes, {cycle:.1f}b cycle)")
        print(f"    Bass rhythm:   from bass_style '{bass_style}' (decoupled from motif cell)")

    else:  # "free"
        print(f"    Melody/Bass rhythm: free (density grid)")

    # ── Harmony section events (explicit switch on harmony_rhythm.rhythm) ─
    h_rhythm_source = (_hr_model.rhythm if _hr_model is not None else None) or rhythm_source

    harmony_section_events = None  # None → free; "sustain" → sustain sentinel

    if h_rhythm_source == "sustain":
        harmony_section_events = "sustain"
        print(f"    Harmony rhythm: sustain")

    elif h_rhythm_source == "pattern":
        hp_model = section_model.harmony_pattern
        if hp_model:
            hp = hp_model.model_dump(exclude_none=True)
            harmony_section_events = rhythm_pattern_to_events(hp, total_beats=total_beats_section)
            print(f"    Harmony rhythm: hand-played pattern ({len(hp['onsets'])} onsets)")

    elif h_rhythm_source == "motif":
        harmony_section_events = _motif_rhythm_to_events(
            active_motif_def["rhythm"], total_beats_section, "stressed",
            velocities=active_motif_def.get("velocities"),
            rests=active_motif_def.get("rests"),
        )
        cycle = sum(active_motif_def["rhythm"])
        print(f"    Harmony rhythm: motif stressed ({len(harmony_section_events)} triggers, {cycle:.1f}b cycle)")

    else:  # "free"
        harmony_section_events = None
        print(f"    Harmony rhythm: free (density grid)")

    # ── Enrichment Pass ───────────────────────────────────────────────────────
    # Distribute section-level harmony events into per-chord rhythm_events DNA.
    # Must run after harmony_section_events is fully resolved above.
    # No-op when source is "free" (None) or "sustain" — those strategies own
    # their own rhythm resolution and do not consult chord.rhythm_events.
    chords = _enrich_chords_with_rhythm(
        chords=chords,
        bars_list=bars_list,
        beats_per_bar=beats_per_bar,
        harmony_section_events=harmony_section_events,
    )

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
        motif=active_motif_def,
        rhythm_events_override=bass_rhythm_events,
        rest_probability=section_model.bass_rest_probability,
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
        piece_ctx=piece_ctx,
        arc=section_model.arc,
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
        { "section": "verse_A" },
        { "section": "chorus" },
        ...
      ],
      "sections": {
        "verse_A": { "bars": 12, "progression": [...], ... },
        "chorus": { "bars": 8, "progression": [...], ... },
        ...
      }
    }

    Each form entry may also be a plain string: "verse_A".
    Repeated references to the same section produce deterministic output
    because generation is fully seed-driven (base_seed + section_index offset).

    Returns: Flattened list of section dicts (shallow copies of the base defs).
    """
    form_array = piece.get("form", [])
    section_defs = piece.get("sections", {})

    if not form_array:
        raise ValueError("Song form specified but no 'form' array provided.")
    if not section_defs:
        raise ValueError("Song form specified but no 'sections' dict provided.")

    expanded = []
    for form_item in form_array:
        # Accept both plain strings ("verse_A") and dicts ({"section": "verse_A"})
        if isinstance(form_item, str):
            section_name = form_item
        else:
            section_name = form_item.get("section")

        if section_name not in section_defs:
            raise ValueError(f"Song form references undefined section: '{section_name}'")

        # Shallow copy so that per-section generation cannot mutate the master def.
        expanded.append(dict(section_defs[section_name]))

    return expanded


# ---------------------------------------------------------------------------
# Harmony rhythm resolution helpers
# ---------------------------------------------------------------------------
# _resolve_harmony_rhythm, _slice_events_into_window and _motif_rhythm_to_events
# have been moved to intervals/core/strategies.py to break circular imports.
# They are re-imported at the top of this file and remain callable here.
# _resolve_harmony_rhythm has been removed — its logic now lives entirely
# in the HarmonyStrategy subclasses (_SustainHarmonyStrategy, _FreeHarmonyStrategy,
# _PatternHarmonyStrategy, _MotifHarmonyStrategy), dispatched via HarmonyStrategyRegistry.


def _enrich_chords_with_rhythm(
    chords: list[VoicedChord],
    bars_list: list[float],
    beats_per_bar: int,
    harmony_section_events,   # list[RhythmEvent] | "sustain" | None
) -> list[VoicedChord]:
    """
    Attach chord-local RhythmEvent slices to each VoicedChord.

    This is the Enrichment Pass — the single place that translates section-level
    pre-tiled harmony events into per-chord beat-local coordinates.  The resulting
    chord.rhythm_events list is consumed by _PatternHarmonyStrategy and
    _MotifHarmonyStrategy as Priority 1 (DNA path), bypassing the legacy
    slice-on-demand path in those strategies.

    Returns new VoicedChord instances (via dataclasses.replace); originals are
    never mutated.

    Chords receive rhythm_events=None when:
      - harmony_section_events is None     → "free" strategy handles rhythm itself
      - harmony_section_events is "sustain" → sustain strategy handles it
      - The window slice is empty           → strategy falls back to sustain event
    """
    from dataclasses import replace as _dc_replace

    if not harmony_section_events or harmony_section_events == "sustain":
        # Nothing to distribute — originals already have rhythm_events=None.
        return chords

    enriched = []
    beat_cursor = 0.0
    for chord, bars in zip(chords, bars_list):
        window_beats = bars * beats_per_bar
        sliced = _slice_events_into_window(
            harmony_section_events,
            window_start=beat_cursor,
            window_length=window_beats,
            min_duration=0.25,
        )
        enriched.append(_dc_replace(chord, rhythm_events=sliced if sliced else None))
        beat_cursor += window_beats
    return enriched


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
        seed=base_seed,
    )

    # Optional explicit transform plan from piece JSON
    transform_sequence = piece.get("transform_sequence")

    # Build per-section seed offsets. Song form entries with exact_repeat=True
    # reuse the seed_offset of the first occurrence of that section name so
    # generation is identical — same notes, same voicings, same rhythm.
    if form_type == "song":
        _first_offset: dict[str, int] = {}
        seed_offsets: list[int] = []
        for _i, _entry in enumerate(piece_model.form or []):
            _name   = _entry if isinstance(_entry, str) else _entry.section
            _exact  = False if isinstance(_entry, str) else _entry.exact_repeat
            _offset = _first_offset[_name] if (_exact and _name in _first_offset) else _i * 10
            _first_offset.setdefault(_name, _offset)
            seed_offsets.append(_offset)
    else:
        seed_offsets = [i * 10 for i in range(len(sections))]

    # Accumulate all voice events with beat offsets across sections
    all_chord_events  = []   # (abs_beat, 'on'/'off', note, vel, channel)
    all_bass_notes    = []
    all_melody_notes  = []
    # Keyed by voice index (0, 1, 2) so each independent counterpoint
    # voice accumulates its own notes across every section, and ends up
    # on its own MIDI track instead of being merged into one.
    all_cp_notes: dict[int, list] = {}
    all_drum_hits     = []

    global_beat = 0.0

    for i, section in enumerate(sections):

        # ══════════════════════════════════════════════════════════
        # CREATE SECTION CONTEXT — cross-voice awareness scratchpad
        # ══════════════════════════════════════════════════════════
        sec_ctx = piece_ctx.make_section_context(section, i)

        res = generate_section(
            section, theme, base_seed=base_seed, seed_offset=seed_offsets[i],
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

        # Section-level rhythm defaults (used by melody, bass)
        groove = section_model.groove
        swing  = section_model.swing or 0.0

        # Counterpoint (optional — only if section defines it).
        # section_model.counterpoint is a list of 1-3 CounterpointModel
        # entries (legacy single-object files are normalised to a
        # one-item list by the schema). Each voice is generated in turn,
        # checked against the melody AND every counterpoint voice already
        # generated this section, so a third voice can't silently collide
        # with the second the way it would if voices were independent.
        cp_voice_models = section_model.counterpoint
        if cp_voice_models:
            # Sounding pitches so far this section: starts with the melody,
            # then grows as each counterpoint voice is added below.
            # Kept as a coarse, time-agnostic pool for back-compat / first
            # species (see generate_first_species docstring).
            against_notes = [
                mn.midi_note for mn in melody_notes
                if not mn.is_rest and mn.midi_note is not None
            ]
            # Time-aware pool: actual note lists, so free species can ask
            # "what is voice X sounding at beat Y" instead of assuming
            # shared-index alignment with the melody. Section-local time
            # (pre global_beat offset), same basis as melody_notes.
            against_voices = [melody_notes]

            for voice_idx, cp_model in enumerate(cp_voice_models):
                cp_notes = generate_counterpoint(
                    melody_notes,
                    key=theme["key"],
                    mode=theme["mode"],
                    beats_per_bar=section_model.beats_per_bar,
                    seed=base_seed + i * 10 + voice_idx,
                    cp_model=cp_model,
                    against_notes=against_notes,
                    against_voices=against_voices,
                )

                # Canon offset: shift this voice forward in time.
                canon_offset = cp_model.canon_offset
                if canon_offset > 0:
                    for cn in cp_notes:
                        cn.start_beat += canon_offset
                    # Trim notes that now extend past section boundary
                    cp_notes = [cn for cn in cp_notes
                                if cn.start_beat < total_beats]

                # Record this voice's snapshot under a distinct name so
                # multiple counterpoint voices don't overwrite each other
                # in cross-section memory.
                if sec_ctx is not None:
                    cp_pitches = [cn.midi_note for cn in cp_notes
                                  if not cn.is_rest and cn.midi_note is not None]
                    cp_durations = [cn.duration_beats for cn in cp_notes
                                    if not cn.is_rest and cn.midi_note is not None]
                    _tb = sum(b * beats_per_bar for b in bars_list)
                    voice_name = (
                        "counterpoint" if len(cp_voice_models) == 1
                        else f"counterpoint_{voice_idx + 1}"
                    )
                    sec_ctx.add_voice(voice_name, compute_voice_snapshot(
                        pitches=cp_pitches,
                        durations=cp_durations,
                        total_beats=_tb,
                        total_slots=int(_tb * 2),
                        key=theme["key"], mode=theme["mode"],
                    ))

                # Feed this voice's pitches forward (both pools) so the
                # *next* counterpoint voice, if any, avoids colliding with
                # it too — including by exact time position, not just a
                # flattened pitch pool.
                against_notes = against_notes + [
                    cn.midi_note for cn in cp_notes
                    if not cn.is_rest and cn.midi_note is not None
                ]
                against_voices = against_voices + [cp_notes]

                for cn in cp_notes:
                    cn.start_beat += global_beat
                all_cp_notes.setdefault(voice_idx, []).extend(cp_notes)

        # ── Harmony events — pure strategy dispatch, zero if/else ───────────
        # HarmonyRhythmContext absorbs all HR overrides (density/groove/swing).
        # HarmonyStrategyRegistry selects the correct implementation from ctx.source.
        # The loop body is clean: build context → dispatch → extend.

        arc = res.section_model.arc
        beat_offset_local = 0.0

        for ci, chord in enumerate(chords):
            total_per_chord = bars_list[ci] * beats_per_bar

            hrctx = build_harmony_rhythm_context_from_model(
                section=section_model,
                active_motif_def=None,   # motif rhythm already in precomputed_events
                total_beats_section=total_beats,
                total_per_chord=total_per_chord,
                beat_offset=beat_offset_local,
                precomputed_events=harmony_section_events,
                seed=base_seed + i * 10 + ci,
            )
            hctx = build_harmony_chord_context(
                harmony_rhythm_ctx=hrctx,
                chord=chord,
                global_beat=global_beat,
                beat_offset_local=beat_offset_local,
                arc=arc,
                harmony_rest_probability=section_model.harmony_rest_probability,
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

        # Melody notes — offset by global beat, with arc-driven velocity
        # envelope applied at write time (melody only — bass and drums
        # keep their declared velocities).  Multiplier 1.0 (plateau /
        # unknown arc) is a strict no-op so existing output is unchanged.
        section_arc = res.section_model.arc
        env_total_bars = max(1, int(round(total_beats / beats_per_bar)))
        for mn in melody_notes:
            vel = mn.velocity
            if not mn.is_rest and mn.midi_note is not None:
                bar_index = int(mn.start_beat // beats_per_bar)
                mult = velocity_envelope(section_arc, bar_index, env_total_bars)
                if mult != 1.0:
                    vel = int(round(vel * mult))
                    vel = max(VELOCITY_CLAMP_MIN, min(VELOCITY_CLAMP_MAX, vel))
            all_melody_notes.append(MelodyNote(
                mn.midi_note,
                mn.start_beat + global_beat,
                mn.duration_beats,
                vel,
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

    # Time signature numerator: use the first section's beats_per_bar rather
    # than the hardcoded default. This is a single top-level meta-event —
    # if sections genuinely mix time signatures, only the first one is
    # reflected here. True per-section time signature changes (and real
    # meter/subdivision awareness generally) are a separate, deferred piece
    # of work, not something this fixes.
    sections_for_sig = piece_model.iter_sections()
    time_sig_num = sections_for_sig[0].beats_per_bar if sections_for_sig else 4

    mid.tracks.append(build_metadata_track(
        bpm=bpm,
        time_sig_numerator=time_sig_num,
        piece_name=piece.get("title", "Intervals Piece")
    ))

    # Melody track
    mid.tracks.append(build_melody_track(all_melody_notes))

    # Counterpoint tracks — one per independent voice (only if any
    # sections used counterpoint at all). Voice 0 keeps the original
    # channel/name ("Counterpoint") so single-voice files render
    # identically to before this feature existed. Voices 1 and 2 (if
    # present) get their own channel and a distinguishing track name.
    _cp_track_specs = [
        (CHANNEL_COUNTERPOINT,   TRACK_NAME_COUNTERPOINT,   PROGRAM_COUNTERPOINT),
        (CHANNEL_COUNTERPOINT_2, TRACK_NAME_COUNTERPOINT_2, PROGRAM_COUNTERPOINT),
        (CHANNEL_COUNTERPOINT_3, TRACK_NAME_COUNTERPOINT_3, PROGRAM_COUNTERPOINT),
    ]
    for voice_idx in sorted(all_cp_notes.keys()):
        notes = all_cp_notes[voice_idx]
        if not notes:
            continue
        channel, track_name, program = _cp_track_specs[voice_idx]
        mid.tracks.append(build_counterpoint_track(
            notes, channel=channel, track_name=track_name, program=program,
        ))

    # Harmony track
    harmony_track = MidiTrack()
    harmony_track.append(MetaMessage("track_name", name=TRACK_NAME_HARMONY, time=0))
    harmony_track.append(Message("program_change", program=PROGRAM_HARMONY, channel=CHANNEL_HARMONY, time=0))
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
