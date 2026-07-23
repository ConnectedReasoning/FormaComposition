"""
Regression probe: `exact_repeat: true` song-form entries must render
byte-identical events for EVERY voice — melody, harmony, bass, every
counterpoint voice, and drums — not just melody and bass.

Uses validation/piece_shake_v5.json's "chorus" section, which appears twice in
the song form (form index 2, and form index 4 with exact_repeat: true).
generate_piece()'s seed_offset reuse logic is specifically designed to make
these two renders of "chorus" identical (see the comment above
`seed_offsets` in generate_piece: "Song form entries with exact_repeat=True
reuse the seed_offset of the first occurrence ... so generation is
identical — same notes, same voicings, same rhythm").

This probe renders the WHOLE piece once (exactly as a user would), then
slices the written MIDI by each chorus occurrence's absolute beat window
and diffs every voice's note list between the two windows. It is
deliberately a black-box, output-only check — it does not assume anything
about which internal seed arithmetic the generator uses, only that the
final MIDI for both choruses must match.

NOTE ON THE DRUMS VOICE: validation/piece_shake_v5.json does not define a
`drums` block on any section (none of its voices use percussion). To
exercise the drum-hit path at all, this probe works from a copy of the
piece with a minimal `drums: {"pattern": "four_on_floor"}` added to the
chorus section only. Everything else (progression, melody, both
counterpoint voices, harmony) is the original, untouched fixture.
"""

import copy
import json
import os

import mido

from intervals.core.generator import generate_piece, beats_to_ticks


FIXTURES_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "validation",
)


# ---------------------------------------------------------------------------
# Fixture loading
# ---------------------------------------------------------------------------

def _load_shake_theme_and_piece():
    with open(os.path.join(FIXTURES_DIR, "theme_shake_v2.json")) as f:
        theme = json.load(f)["theme"]
    with open(os.path.join(FIXTURES_DIR, "piece_shake_v5.json")) as f:
        piece = json.load(f)["piece"]

    # Add a minimal drums block to "chorus" only, so the drum-hit voice is
    # actually exercised by this probe (see module docstring). Deep-copied
    # so this never mutates a shared fixture dict across test runs.
    piece = copy.deepcopy(piece)
    piece["sections"]["chorus"]["drums"] = {"pattern": "four_on_floor"}
    return theme, piece


# ---------------------------------------------------------------------------
# MIDI introspection helpers
# ---------------------------------------------------------------------------

def _track_by_name(mid: "mido.MidiFile", name: str):
    """Find a track by its track_name meta message. Returns None if absent
    (e.g. a counterpoint voice or drums that no section actually uses)."""
    for track in mid.tracks:
        for msg in track:
            if msg.is_meta and msg.type == "track_name" and msg.name == name:
                return track
    return None


def _absolute_events(track):
    """Walk a track's delta-time messages into (abs_tick, type, note, velocity)
    tuples for note_on/note_off only (meta/program_change ignored)."""
    events = []
    abs_tick = 0
    for msg in track:
        abs_tick += msg.time
        if msg.type in ("note_on", "note_off"):
            events.append((abs_tick, msg.type, msg.note, msg.velocity))
    return events


def _paired_notes(events):
    """Pair note_on/note_off into (onset_tick, pitch, velocity, duration_tick)
    tuples, FIFO per pitch (matches how _write_events_to_track emits them —
    sorted by tick, offs before ons at the same tick)."""
    from collections import deque, defaultdict

    pending = defaultdict(deque)
    notes = []
    for abs_tick, kind, pitch, vel in events:
        if kind == "note_on":
            pending[pitch].append((abs_tick, vel))
        else:
            if pending[pitch]:
                onset_tick, onset_vel = pending[pitch].popleft()
                notes.append((onset_tick, pitch, onset_vel, abs_tick - onset_tick))
    notes.sort(key=lambda n: (n[0], n[1]))
    return notes


def _notes_in_window(notes, start_tick, end_tick):
    """Notes whose onset falls in [start_tick, end_tick), normalized so the
    window's own start becomes tick 0 — this is what makes two different
    absolute-time occurrences of "the same section" directly comparable."""
    return [
        (onset - start_tick, pitch, vel, dur)
        for onset, pitch, vel, dur in notes
        if start_tick <= onset < end_tick
    ]


def _voice_events_in_window(mid, track_name, start_tick, end_tick):
    track = _track_by_name(mid, track_name)
    if track is None:
        return []
    return _notes_in_window(_paired_notes(_absolute_events(track)), start_tick, end_tick)


# ---------------------------------------------------------------------------
# Section-window computation
# ---------------------------------------------------------------------------

def _chorus_windows_ticks(piece: dict) -> tuple[tuple[int, int], tuple[int, int]]:
    """
    Compute the [start_tick, end_tick) window for each occurrence of
    "chorus" in the song form, purely from the piece's own form/sections
    declarations (bars * beats_per_bar per section — chord_bars only
    redistributes a section's bars across its progression, it never changes
    the section's total length, so this is exact regardless of how chords
    are split).

    Returns (first_chorus_window, exact_repeat_chorus_window).
    """
    sections = piece["sections"]
    cumulative_beat = 0.0
    windows = {}  # form_index -> (start_beat, end_beat)

    for form_index, form_entry in enumerate(piece["form"]):
        name = form_entry if isinstance(form_entry, str) else form_entry["section"]
        sec = sections[name]
        bpb = sec.get("beats_per_bar", 4)
        total_beats = sec["bars"] * bpb

        start_beat = cumulative_beat
        end_beat = cumulative_beat + total_beats
        if name == "chorus":
            windows[form_index] = (start_beat, end_beat)
        cumulative_beat = end_beat

    chorus_indices = sorted(windows.keys())
    assert len(chorus_indices) == 2, (
        f"Expected exactly 2 'chorus' occurrences in the form, found "
        f"{len(chorus_indices)}: {chorus_indices}"
    )
    first_idx, repeat_idx = chorus_indices

    # Confirm the second occurrence is actually the exact_repeat one, so
    # this probe fails loudly (not silently on the wrong pair) if the
    # fixture's form array is ever reordered.
    repeat_entry = piece["form"][repeat_idx]
    assert isinstance(repeat_entry, dict) and repeat_entry.get("exact_repeat") is True, (
        f"Expected form[{repeat_idx}] to be the exact_repeat chorus entry, "
        f"got: {repeat_entry!r}"
    )

    def to_ticks(window):
        start_beat, end_beat = window
        return beats_to_ticks(start_beat), beats_to_ticks(end_beat)

    return to_ticks(windows[first_idx]), to_ticks(windows[repeat_idx])


# ---------------------------------------------------------------------------
# The probe
# ---------------------------------------------------------------------------

VOICE_TRACK_NAMES = [
    "Melody",
    "Harmony",
    "Bass",
    "Counterpoint",     # counterpoint voice 0 (arpeggio slot)
    "Counterpoint 2",    # counterpoint voice 1 (counterline slot)
    "Drums",
]


def test_exact_repeat_chorus_is_byte_identical_across_every_voice(tmp_path):
    theme, piece = _load_shake_theme_and_piece()

    out_path = tmp_path / "shake_v5_exact_repeat_probe.mid"
    rendered_path = generate_piece(theme, piece, str(out_path))
    mid = mido.MidiFile(rendered_path)

    (first_start, first_end), (repeat_start, repeat_end) = _chorus_windows_ticks(piece)

    failures = []
    for voice_name in VOICE_TRACK_NAMES:
        first_notes = _voice_events_in_window(mid, voice_name, first_start, first_end)
        repeat_notes = _voice_events_in_window(mid, voice_name, repeat_start, repeat_end)

        if first_notes != repeat_notes:
            failures.append(
                f"\n  Voice '{voice_name}' diverged between the two chorus "
                f"occurrences ({len(first_notes)} vs {len(repeat_notes)} notes).\n"
                f"    first  (window {first_start}-{first_end}):  {first_notes[:8]}"
                f"{' ...' if len(first_notes) > 8 else ''}\n"
                f"    repeat (window {repeat_start}-{repeat_end}): {repeat_notes[:8]}"
                f"{' ...' if len(repeat_notes) > 8 else ''}"
            )

    assert not failures, (
        "exact_repeat should make every voice byte-identical between "
        "chorus occurrences, but the following voices diverged:"
        + "".join(failures)
    )
