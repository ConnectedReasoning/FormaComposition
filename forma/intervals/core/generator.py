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
from intervals.music.rhythm   import (
    apply_velocity_arc, apply_swing,
    get_pattern, RhythmEvent,
)
from intervals.music.motif    import from_dict as motif_from_dict, to_dict as motif_to_dict, Motif
from intervals.music.prosody  import phrase_to_motif
from intervals.music.percussion import generate_drums, DrumHit
from intervals.music.rhythmic_template import (
    phrase_to_rhythm_template,
    tile_template,
    apply_lens,
    melody_lens,
    bass_lens,
    harmony_lens,
    counterpoint_lens,
    drums_lens,
    RhythmicTemplate,
)
from intervals.core.motif_loader import resolve_motif_from_theme
from intervals.core.context import (
    PieceContext,
    SectionContext,
    VoiceSnapshot,
    compute_voice_snapshot,
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

def rhythm_pattern_to_events(
    pattern: dict,
    total_beats: float,
) -> list:
    """
    Convert a rhythm_pattern dict (from rhythm_extract.py) into a tiled
    list of RhythmEvent covering total_beats.

    The pattern is repeated as many times as needed to fill the section.
    Last repetition is trimmed at the section boundary.

    Args:
        pattern:      Dict with onsets, durations, velocities, length_beats
        total_beats:  Total beats to fill

    Returns:
        list[RhythmEvent]
    """
    onsets = pattern["onsets"]
    durations = pattern["durations"]
    velocities = pattern.get("velocities", [0.7] * len(onsets))
    cycle_length = pattern.get("length_beats", 8.0)

    if not onsets or cycle_length <= 0:
        return []

    events = []
    offset = 0.0
    while offset < total_beats:
        for i in range(len(onsets)):
            abs_onset = offset + onsets[i]
            if abs_onset >= total_beats:
                break
            dur = durations[i] if i < len(durations) else 0.5
            # Trim if it exceeds section boundary
            dur = min(dur, total_beats - abs_onset)
            vel = velocities[i] if i < len(velocities) else 0.7

            events.append(RhythmEvent(
                start_beat=abs_onset,
                duration_beats=max(0.25, dur),
                velocity_scale=vel,
                is_rest=False,
            ))
        offset += cycle_length

    return events


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
) -> tuple[list[VoicedChord], list[BassNote], list[MelodyNote], float]:
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
        (chords, bass_notes, melody_notes, total_beats,
         bars_list, beats_per_bar, density, section)
    """
    key          = theme["key"]
    mode         = theme["mode"]

    # Resolve motif using new loader (supports both embedded and referenced motifs)
    motif_obj = resolve_motif_from_theme(theme)
    motif_def = motif_to_dict(motif_obj) if motif_obj else None

    progression  = section["progression"]
    bars         = section.get("bars", 8)
    density      = section.get("density", "medium")
    melody_beh   = section.get("melody", "generative")
    bass_style   = section.get("bass_style", "root_fifth")
    beats_per_bar= section.get("beats_per_bar", 4)
    groove       = section.get("groove")       # None = original grid behavior
    swing        = section.get("swing", 0.0)   # 0.0 = straight

    # Per-chord bar durations: explicit list or even distribution
    # If chord_bars is provided, it is the source of truth — bars is derived from it.
    chord_bars = section.get("chord_bars")
    if chord_bars is not None:
        bars_list = [float(b) for b in chord_bars]
        bars = sum(bars_list)   # derive bars — chord_bars wins
    else:
        even = bars / len(progression)
        bars_list = [even] * len(progression)

    # Resolve chords
    chords = resolve_progression(progression, key, mode, density=density)

    # ── Compute section totals (used for snapshots) ───────────────
    total_beats_section = sum(b * beats_per_bar for b in bars_list)
    total_slots = int(total_beats_section * 2)  # 8th-note resolution

    # ── Resolve prosodic rhythm template ───────────────────────────
    # Priority: section rhythm_phrase > theme rhythm_phrase > none
    # Section-level allows per-section rhythmic identity.
    # phrase (without rhythm_phrase) is a separate pitch-contour tool
    # and does not affect the rhythm template.
    rhythm_template = None
    rhythm_phrase = section.get("rhythm_phrase") or theme.get("rhythm_phrase")
    if rhythm_phrase:
        rhythm_template = phrase_to_rhythm_template(
            rhythm_phrase, seed=base_seed + seed_offset,
        )
        source = "section" if section.get("rhythm_phrase") else "theme"
        print(f"    Rhythm phrase ({source}): '{rhythm_phrase}' → "
              f"{len(rhythm_template)} syllables, "
              f"{rhythm_template.total_beats:.1f}b template")

    # ── Resolve melody rhythm events ────────────────────────────────
    # Priority: 1) hand-played rhythm_pattern
    #           2) motif rhythm ("full" articulation)
    #           3) prosodic lens
    #           4) get_pattern() density-based fallback
    melody_rhythm_events = None
    rhythm_pattern = section.get("rhythm_pattern")
    if rhythm_pattern:
        melody_rhythm_events = rhythm_pattern_to_events(
            rhythm_pattern, total_beats=total_beats_section,
        )
        print(f"    Melody rhythm: hand-played pattern, "
              f"{len(rhythm_pattern['onsets'])} notes, "
              f"{rhythm_pattern.get('length_beats', '?')}b cycle")
    elif motif_def and motif_def.get("rhythm"):
        melody_rhythm_events = _motif_rhythm_to_events(
            motif_def["rhythm"], total_beats_section, "full",
            velocities=motif_def.get("velocities"),
        )
        cycle = sum(motif_def["rhythm"])
        print(f"    Melody rhythm: motif ({len(motif_def['rhythm'])} notes, {cycle:.1f}b cycle)")
    elif rhythm_template is not None:
        melody_rhythm_events = melody_lens(
            rhythm_template,
            total_beats=total_beats_section,
            seed=base_seed + seed_offset,
        )

    # ── Resolve motif rhythm events for harmony and bass ────────────
    # Derived from the same motif rhythm at reduced articulation density.
    # These are section-level event lists; the harmony per-chord loop
    # slices them into chord windows via _slice_events_into_window.
    # Bass uses them as whole-section timing anchors.
    motif_harmony_events = None
    motif_bass_events    = None
    if motif_def and motif_def.get("rhythm"):
        motif_harmony_events = _motif_rhythm_to_events(
            motif_def["rhythm"], total_beats_section, "stressed",
            velocities=motif_def.get("velocities"),
        )
        motif_bass_events = _motif_rhythm_to_events(
            motif_def["rhythm"], total_beats_section, "anchor",
            velocities=motif_def.get("velocities"),
        )
        cycle = sum(motif_def["rhythm"])
        print(f"    Harmony rhythm: motif (stressed, {len(motif_harmony_events)} triggers, {cycle:.1f}b cycle)")
        print(f"    Bass rhythm:    motif (anchor,   {len(motif_bass_events)} triggers, {cycle:.1f}b cycle)")

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
        rhythm_events_override=motif_bass_events,
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

    # If using 'develop' behavior, pick a directed transform
    last_xform = None
    if melody_beh == "develop" and piece_ctx is not None:
        pool = []
        if isinstance(motif_def, dict):
            pool = motif_def.get("transform_pool", [])
        if pool:
            last_xform = piece_ctx.suggest_transform(
                available=pool,
                transform_sequence=transform_sequence,
                section_index=sec_ctx.section_index if sec_ctx else 0,
            )

    melody_notes = generate_melody_for_progression(
        chords, key, mode,
        behavior=melody_beh,
        density=density,
        bars_per_chord=bars_list,
        beats_per_bar=beats_per_bar,
        motif=motif_def,
        groove=groove,
        swing=swing,
        seed=base_seed + seed_offset,
        section_name=section.get("name", ""),
        rhythm_events_override=melody_rhythm_events,
        fugal_techniques=section.get("fugal_techniques"),
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
            last_transform=last_xform,
            last_chord_degree=progression[-1],
            key=key,
            mode=mode,
        ))

    total_beats = bars * beats_per_bar
    return chords, bass_notes, melody_notes, total_beats, bars_list, beats_per_bar, density, section, rhythm_template, motif_harmony_events


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
# Validator
# ---------------------------------------------------------------------------

VALID_SECTION_KEYS = {
    "name", "bars", "chord_bars", "progression", "density", "melody",
    "bass_style", "arc", "harmony_rhythm", "beats_per_bar", "groove",
    "swing", "counterpoint", "notes", "percussion", "drums",
    "rhythm_pattern", "harmony_pattern", "fugal_techniques", "rhythm_phrase",
}

OBSOLETE_THEME_KEYS = {"palette"}

VALID_DENSITY    = {"low", "medium", "high", "sparse", "full"}
VALID_MELODY_BEH = {"lyrical", "generative", "motif", "sparse", "rhythmic", "develop"}
VALID_BASS_STYLE = {"root_fifth", "walking", "pedal", "arpeggiated", "sparse", "root_only", "melodic", "steady", "pulse"}
VALID_ARC        = {"swell", "fade", "build", "plateau", "decay", "fade_in", "fade_out", "breath"}


def validate_piece(theme: dict, piece: dict) -> list[str]:
    """
    Validate a theme + piece pair before generation.

    Returns a list of error/warning strings.
    Empty list means all clear.
    Errors are prefixed with [ERROR], warnings with [WARN].
    """
    issues = []

    # Unwrap if nested under "theme" / "piece" keys
    t = theme.get("theme", theme)
    p = piece.get("piece", piece)
    for key in OBSOLETE_THEME_KEYS:
        if key in t:
            issues.append(f"[WARN] theme has obsolete field '{key}' — remove it (instruments live in Logic)")

    if "motif" not in t:
        issues.append("[WARN] theme has no motif defined — melodic identity will be purely generative")

    # --- rhythm_phrase prerequisite check ------------------------------
    # rhythm_phrase drives the rhythmic template for all voices.
    # It is a separate tool from phrase (pitch contour only).
    # The CMU pronouncing dictionary MUST be available for rhythm_phrase
    # to produce valid output. Without it, every syllable is treated as
    # primary stress, making the rhythm template fictional.
    if t.get("prosodic_rhythm"):
        issues.append(
            "[ERROR] 'prosodic_rhythm' is no longer supported. "
            "Use 'rhythm_phrase' for phrase-driven rhythm (all voices) "
            "and 'phrase' for pitch contour only. These are now separate keys."
        )

    if t.get("rhythm_phrase"):
        try:
            from intervals.music.prosody import PRONOUNCING_AVAILABLE
        except ImportError:
            PRONOUNCING_AVAILABLE = False
        if not PRONOUNCING_AVAILABLE:
            issues.append(
                "[ERROR] theme has 'rhythm_phrase' but the 'pronouncing' "
                "library is not installed. Without the CMU pronouncing "
                "dictionary, syllable stress cannot be analyzed and the "
                "rhythm template output is structurally wrong. "
                "Install with: pip install pronouncing"
            )
        else:
            from intervals.music.prosody import analyze_phrase
            analysis = analyze_phrase(t["rhythm_phrase"])
            if analysis.fallback_words:
                issues.append(
                    f"[WARN] rhythm_phrase '{t['rhythm_phrase']}' contains "
                    f"words not in the CMU dictionary: {analysis.fallback_words}. "
                    f"Stress for these words is guessed by syllable count "
                    f"and may not match natural speech."
                )

    # --- Piece-level checks ---
    if "tempo" not in p and "tempo" not in t:
        issues.append("[WARN] piece has no tempo — will use theme midpoint")

    # Validate transform_sequence if present
    transform_seq = p.get("transform_sequence")
    if transform_seq is not None:
        if not isinstance(transform_seq, list):
            issues.append("[ERROR] transform_sequence must be a list of transform names")
        else:
            form_type = p.get("form_type", "narrative")
            if form_type == "song":
                form = p.get("form", [])
                n_sections = len(form)
            else:
                n_sections = len(p.get("sections", []))
            if len(transform_seq) < n_sections:
                issues.append(
                    f"[WARN] transform_sequence has {len(transform_seq)} entries "
                    f"but piece has {n_sections} sections — later sections will use weighted random"
                )

    form_type = p.get("form_type", "narrative")

    if form_type == "song":
        # Song form: validate form array references sections
        form = p.get("form", [])
        section_defs = p.get("sections", {})
        if not form:
            issues.append("[ERROR] form_type is 'song' but no 'form' array defined")
        if not section_defs:
            issues.append("[ERROR] form_type is 'song' but no 'sections' dict defined")
        for item in form:
            name = item.get("section") if isinstance(item, dict) else item
            if name and name not in section_defs:
                issues.append(f"[ERROR] form references undefined section '{name}'")
        sections = list(section_defs.values())
    else:
        # Narrative form
        sections = p.get("sections", [])
        if not sections:
            issues.append("[ERROR] piece has no sections")

    # --- Section-level checks ---
    for i, section in enumerate(sections):
        label = section.get("name", f"section[{i}]")

        # Unknown keys
        unknown = set(section.keys()) - VALID_SECTION_KEYS
        if unknown:
            issues.append(f"[WARN] {label}: unknown field(s) {sorted(unknown)} — typo?")

        # progression required
        if "progression" not in section:
            issues.append(f"[ERROR] {label}: missing 'progression'")
            continue

        prog = section["progression"]
        chord_bars = section.get("chord_bars")
        bars = section.get("bars")

        # chord_bars length must match progression
        if chord_bars is not None:
            if len(chord_bars) != len(prog):
                issues.append(
                    f"[ERROR] {label}: chord_bars has {len(chord_bars)} entries "
                    f"but progression has {len(prog)} chords"
                )
            # bars declared but doesn't match sum(chord_bars)
            if bars is not None:
                derived = sum(float(b) for b in chord_bars)
                if abs(derived - bars) > 0.01:
                    issues.append(
                        f"[WARN] {label}: declared bars={bars} but sum(chord_bars)={derived} — "
                        f"'bars' is ignored when chord_bars is present; consider removing it"
                    )
        else:
            if bars is None:
                issues.append(f"[WARN] {label}: no 'bars' or 'chord_bars' — defaulting to 8 bars")

        # Enum validation
        density = section.get("density")
        if density and density not in VALID_DENSITY:
            issues.append(f"[ERROR] {label}: density='{density}' — must be one of {sorted(VALID_DENSITY)}")

        melody_beh = section.get("melody")
        if melody_beh and melody_beh not in VALID_MELODY_BEH:
            issues.append(f"[ERROR] {label}: melody='{melody_beh}' — must be one of {sorted(VALID_MELODY_BEH)}")

        bass_style = section.get("bass_style")
        if bass_style and bass_style not in VALID_BASS_STYLE:
            issues.append(f"[ERROR] {label}: bass_style='{bass_style}' — must be one of {sorted(VALID_BASS_STYLE)}")

        arc = section.get("arc")
        if arc and arc not in VALID_ARC:
            issues.append(f"[ERROR] {label}: arc='{arc}' — must be one of {sorted(VALID_ARC)}")

        # Section-level rhythm_phrase — same CMU requirement as theme-level
        sec_rp = section.get("rhythm_phrase")
        if sec_rp:
            try:
                from intervals.music.prosody import PRONOUNCING_AVAILABLE as _PA
            except ImportError:
                _PA = False
            if not _PA:
                issues.append(
                    f"[ERROR] {label}: rhythm_phrase requires the 'pronouncing' "
                    f"library. Install with: pip install pronouncing"
                )
            else:
                from intervals.music.prosody import analyze_phrase as _ap
                _analysis = _ap(sec_rp)
                if _analysis.fallback_words:
                    issues.append(
                        f"[WARN] {label}: rhythm_phrase '{sec_rp}' contains words "
                        f"not in the CMU dictionary: {_analysis.fallback_words}. "
                        f"Stress for these words is estimated by syllable count."
                    )

    return issues


# ---------------------------------------------------------------------------
# Harmony rhythm resolution helpers
# ---------------------------------------------------------------------------

def _slice_events_into_window(
    events: list,
    window_start: float,
    window_length: float,
    min_duration: float = 0.25,
) -> list:
    """
    Take a list of section-level RhythmEvents and return only those whose
    start_beat falls inside [window_start, window_start + window_length),
    translated to coordinates local to the window.

    Events with duration shorter than `min_duration` after trimming at the
    window boundary are dropped (boundary artifacts, not musical content).

    Used by the harmony rhythm priority chain to extract the per-chord
    portion of whole-section event streams (hand-played harmony_pattern,
    prosodic harmony_lens). Returns an empty list if no events fall in the
    window — the caller is responsible for any fallback behavior.
    """
    window_end = window_start + window_length
    sliced = []
    for ev in events:
        if ev.start_beat < window_start or ev.start_beat >= window_end:
            continue
        local_start = ev.start_beat - window_start
        local_dur = min(ev.duration_beats, window_length - local_start)
        if local_dur < min_duration:
            continue
        sliced.append(RhythmEvent(
            start_beat=local_start,
            duration_beats=local_dur,
            velocity_scale=ev.velocity_scale,
            is_rest=ev.is_rest,
        ))
    return sliced


def _motif_rhythm_to_events(
    rhythm: list,
    total_beats: float,
    articulation: str = "full",
    velocities: Optional[list] = None,
) -> list:
    """
    Convert a motif rhythm (list of beat durations, e.g. [1.0, 0.5, 1.5, 1.0])
    to a tiled list of RhythmEvent covering total_beats.

    This is the bridge between the motif system and the voice rhythm system.
    The motif's rhythmic identity propagates to all voices, each expressing
    it at an appropriate articulation density:

      "full"     — every onset in the cycle (melody density: pronounces)
      "stressed" — onsets whose duration >= median duration in the cycle
                   (harmony density: accompanies on strong beats)
      "anchor"   — first onset of each cycle only (bass density: anchors)

    Example: rhythm = [1.0, 0.5, 1.5, 1.0], cycle = 4.0 beats
      full:     onsets [0.0, 1.0, 1.5, 3.0]  → 4 events per cycle
      stressed: onsets [0.0, 1.5, 3.0]        → 3 events (dur >= median 1.0)
      anchor:   onsets [0.0]                  → 1 event per cycle

    Returns empty list if rhythm is empty or total_beats <= 0.
    The caller is responsible for any fallback if the list is empty.
    """
    import statistics as _stats

    if not rhythm or total_beats <= 0:
        return []
    cycle_length = sum(rhythm)
    if cycle_length <= 0:
        return []

    # Compute per-onset positions and decide which to keep
    onsets = []
    t = 0.0
    for dur in rhythm:
        onsets.append(t)
        t += dur

    if articulation == "anchor":
        keep = [0]
    elif articulation == "stressed":
        median_dur = _stats.median(rhythm)
        keep = [i for i, d in enumerate(rhythm) if d >= median_dur]
        if 0 not in keep:          # always include the downbeat
            keep = [0] + keep
    else:                           # "full"
        keep = list(range(len(rhythm)))

    if velocities is None or len(velocities) != len(rhythm):
        velocities = [0.8] * len(rhythm)

    events = []
    offset = 0.0
    while offset < total_beats:
        for i in keep:
            abs_onset = offset + onsets[i]
            if abs_onset >= total_beats:
                break
            dur = min(rhythm[i], total_beats - abs_onset)
            if dur < 0.25:
                continue
            events.append(RhythmEvent(
                start_beat=abs_onset,
                duration_beats=dur,
                velocity_scale=velocities[i],
                is_rest=False,
            ))
        offset += cycle_length
    return events


def _resolve_harmony_rhythm(
    section_dict: dict,
    chord_index: int,
    total_per_chord: float,
    beat_offset_local: float,
    beats_per_bar: int,
    rhythm_template: Optional[RhythmicTemplate],
    harmony_hand_events: Optional[list],
    harmony_prosodic_events: Optional[list],
    harmony_motif_events: Optional[list],
    h_density: str,
    h_groove: Optional[str],
    h_note_duration: Optional[str],
) -> list:
    """
    Return rhythm events for a single chord window, applying the harmony
    rhythm priority chain.

    Current priority order (highest first):
      1) harmony_pattern   — hand-played whole-section pattern, sliced
      2) note_duration     — explicit single-event override
      3) motif rhythm      — motif["rhythm"] at "stressed" articulation
      4) prosodic lens     — phrase-driven harmony_lens, sliced
      5) get_pattern()     — density-based grid fallback

    The motif rhythm (priority 3) fires automatically when the theme has a
    motif with a rhythm field and no higher-priority override is set. This
    propagates the motif's rhythmic identity to harmony without any
    explicit section-level config — the harmony breathes with the motif.

    note_duration (priority 2) stays above motif rhythm so that explicit
    `harmony_rhythm: {note_duration: "whole"}` overrides are still respected.

    The `section_dict` and `chord_index` parameters are currently unused but
    accepted for future per-chord features without changing the call site.
    """
    # 1) Hand-played harmony pattern — slice the section-level event stream
    if harmony_hand_events is not None:
        events = _slice_events_into_window(
            harmony_hand_events, beat_offset_local, total_per_chord,
            min_duration=0.25,
        )
        if not events:
            events = [RhythmEvent(start_beat=0.0, duration_beats=total_per_chord,
                                  velocity_scale=0.7, is_rest=False)]
        return events

    # 2) Simple note_duration — single sustained event per chord
    if h_note_duration:
        return [RhythmEvent(start_beat=0.0, duration_beats=total_per_chord,
                            velocity_scale=1.0, is_rest=False)]

    # 3) Motif rhythm at "stressed" articulation — slice section-level events
    if harmony_motif_events is not None:
        events = _slice_events_into_window(
            harmony_motif_events, beat_offset_local, total_per_chord,
            min_duration=0.25,
        )
        if not events:
            # Fallback within this path: sustain the full chord window.
            # This happens when no stressed motif onset falls in this chord's
            # window (e.g. short chord, long motif cycle). Sustaining is more
            # musical than silencing.
            events = [RhythmEvent(start_beat=0.0, duration_beats=total_per_chord,
                                  velocity_scale=0.7, is_rest=False)]
        return events

    # 4) Prosodic harmony lens — slice the section-level event stream
    if harmony_prosodic_events is not None:
        events = _slice_events_into_window(
            harmony_prosodic_events, beat_offset_local, total_per_chord,
            min_duration=0.5,
        )
        if not events:
            events = [RhythmEvent(start_beat=0.0, duration_beats=total_per_chord,
                                  velocity_scale=0.7, is_rest=False)]
        return events

    # 5) Density-based grid fallback
    return get_pattern(
        total_per_chord, density=h_density,
        voice_type="chord", groove=h_groove,
        beats_per_bar=beats_per_bar,
    )


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
    # Validate before generation — print warnings, raise on errors
    issues = validate_piece(theme, piece)
    errors   = [i for i in issues if i.startswith("[ERROR]")]
    warnings = [i for i in issues if i.startswith("[WARN]")]
    for w in warnings:
        print(f"  {w}")
    if errors:
        for e in errors:
            print(f"  {e}")
        raise ValueError(f"Piece validation failed with {len(errors)} error(s). Fix before generating.")

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
        chords, bass_notes, melody_notes, total_beats, bars_list, beats_per_bar, density, section_dict, rhythm_template, motif_harmony_events = \
            generate_section(section, theme, base_seed=base_seed, seed_offset=i * 10,
                             sec_ctx=sec_ctx, piece_ctx=piece_ctx,
                             transform_sequence=transform_sequence)

        # Section-level rhythm defaults (used by melody, bass)
        groove   = section_dict.get("groove")
        swing    = section_dict.get("swing", 0.0)

        # Harmony-specific rhythm: independent from melody when specified
        hr = section_dict.get("harmony_rhythm", {})
        h_density  = hr.get("density", density)
        h_groove   = hr.get("groove", groove)
        h_swing    = hr.get("swing", swing)
        h_note_duration = hr.get("note_duration")  # "whole", "half", "quarter", etc.

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
                seed=base_seed + i * 10,
            )

            # Canon offset: when prosodic rhythm is active, shift counterpoint
            # forward in time by one stressed-syllable duration. This creates
            # the round effect — same musical material, staggered entry.
            if rhythm_template is not None:
                # Default offset: duration of first stressed syllable
                canon_offset = cp_def.get("canon_offset")
                if canon_offset is None:
                    for ti in range(len(rhythm_template)):
                        if rhythm_template.accents[ti] > 0.5:
                            canon_offset = rhythm_template.durations[ti]
                            break
                    if canon_offset is None:
                        canon_offset = rhythm_template.durations[0] if rhythm_template.durations else 0.0

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

        # Harmony events — uses harmony-specific rhythm profile
        beat_offset_local = 0.0

        # Resolve harmony rhythm events
        # Priority: 1) harmony_pattern  2) note_duration  3) motif rhythm
        #           4) prosodic lens  5) get_pattern
        # (See _resolve_harmony_rhythm docstring for priority rationale.)
        harmony_hand_events = None
        harmony_pattern = section_dict.get("harmony_pattern")
        if harmony_pattern:
            harmony_hand_events = rhythm_pattern_to_events(
                harmony_pattern, total_beats=total_beats,
            )
            print(f"    Harmony rhythm: hand-played pattern, "
                  f"{len(harmony_pattern['onsets'])} notes, "
                  f"{harmony_pattern.get('length_beats', '?')}b cycle")

        harmony_prosodic_events = None
        if harmony_hand_events is None and rhythm_template is not None:
            harmony_prosodic_events = harmony_lens(
                rhythm_template,
                total_beats=total_beats,
            )

        for ci, chord in enumerate(chords):
            total_per_chord = bars_list[ci] * beats_per_bar

            rhythm_events = _resolve_harmony_rhythm(
                section_dict=section_dict,
                chord_index=ci,
                total_per_chord=total_per_chord,
                beat_offset_local=beat_offset_local,
                beats_per_bar=beats_per_bar,
                rhythm_template=rhythm_template,
                harmony_hand_events=harmony_hand_events,
                harmony_prosodic_events=harmony_prosodic_events,
                harmony_motif_events=motif_harmony_events,
                h_density=h_density,
                h_groove=h_groove,
                h_note_duration=h_note_duration,
            )

            if h_swing and h_swing > 0:
                rhythm_events = apply_swing(rhythm_events, swing_ratio=h_swing)

            arc = section.get("arc", "swell")
            arced = apply_velocity_arc(rhythm_events, arc=arc, base_velocity=65)

            # Build harmony note events with clean re-articulation.
            # Cap each event's duration so it ends before the next event starts,
            # with a tiny gap for clean note-off → note-on transitions.
            REARTIC_GAP = 0.03  # ~1/32 beat — inaudible but prevents overlap
            arced_list = [(ev, vel) for ev, vel in arced if not ev.is_rest]

            for idx_ev, (ev, vel) in enumerate(arced_list):
                abs_start = global_beat + beat_offset_local + ev.start_beat
                dur = ev.duration_beats

                # If there's a next event, cap duration at the gap
                if idx_ev + 1 < len(arced_list):
                    next_ev = arced_list[idx_ev + 1][0]
                    next_start = global_beat + beat_offset_local + next_ev.start_beat
                    max_dur = next_start - abs_start - REARTIC_GAP
                    dur = max(0.25, min(dur, max_dur))

                abs_end = abs_start + dur
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

        # Drums (optional — only if section defines it)
        if "drums" in section_dict:
            drum_config = section_dict.get("drums", "four_on_floor")

            # Handle both string and dict forms
            if isinstance(drum_config, str):
                pattern = drum_config
            else:
                pattern = drum_config.get("pattern", "four_on_floor")

            # Get rhythm parameters for drums (can use harmony_rhythm if specified)
            drums_density = h_density      # Use harmony_rhythm density if available, else section density
            drums_groove = h_groove
            drums_swing = h_swing

            drum_hits = generate_drums(
                total_beats=total_beats,
                bass_notes=bass_notes,
                pattern=pattern,
                density=drums_density,
                groove=drums_groove,
                swing=drums_swing,
                beats_per_bar=int(section_dict.get("beats_per_bar", 4)),
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
