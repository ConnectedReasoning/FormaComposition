#!/usr/bin/env python3
"""
slop_metrics.py — FormaComposition output analyzer.

lint.py answers "will every setting I wrote actually be heard?"
schemas.py answers "is this piece well-formed?"

This module answers a third question, and it does it on the *rendered MIDI*
rather than the JSON: **is what came out memorable, or is it merely legal?**

The constraint system cannot write a wrong note. That is its whole point, and
it means the failure mode is never "that chord is incorrect" — it is "that was
four minutes of correct music nobody will remember." Slop here is legal but
unmemorable, and it has a measurable signature.

The signature, measured across the catalog: **rhythm n-gram reuse of 90–100%
against pitch-contour reuse of 3–50%.** That is a rhythmic stencil laid over a
random walk — the exact output of `rhythm: "motif"` combined with a non-`develop`
melody behavior, which is the most common section configuration in the catalog.
Memorable music inverts that ratio: the pitch shape recurs and the rhythm
breathes.

Nothing here blocks anything. These are judgments about taste with numbers
attached, and every threshold is arguable — see THRESHOLDS below, where each
one is labeled as either a music-theory prior or a value calibrated against
pieces already judged good by ear. The ear remains the final arbiter. This
module exists so the ear gets a second opinion before the render goes to Logic.

Usage:
    python slop_metrics.py output/piece_long_amen.mid
    python slop_metrics.py output/*.mid --summary
    python slop_metrics.py output/piece.mid --strict   # exit 1 on any FAIL
"""

from __future__ import annotations

import argparse
import hashlib
import statistics
import sys
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterator, Optional

import mido

# ─────────────────────────────────────────────────────────────────────────────
# Track identification
#
# generator.py writes fixed, named tracks. Names are matched case-insensitively
# and by prefix so "Counterpoint 2" lands with "Counterpoint". Anything on MIDI
# channel 9, or named like a drum track, is excluded from every pitch-based
# metric — a kick drum has no melodic contour and no register discipline.
# ─────────────────────────────────────────────────────────────────────────────

LEAD_TRACK: str = "melody"
HARMONY_TRACK: str = "harmony"
BASS_TRACK: str = "bass"
PERCUSSION_TRACKS: frozenset[str] = frozenset({"drums", "percussion"})

# Inner voices — the ones where flatness is least audible as a choice and most
# audible as a machine. Checked for velocity variety and duration variety.
INNER_VOICE_PREFIXES: tuple[str, ...] = ("counterpoint", "bass", "harmony")


# ─────────────────────────────────────────────────────────────────────────────
# THRESHOLDS
#
# Two kinds live here and they are not equally firm:
#
#   [PRIOR]      — a claim about tonal melody in general (Piston, chorale
#                  practice, common-practice voice leading). Change only with
#                  an argument about music, not about one piece.
#   [CALIBRATED] — a number read off pieces in this catalog already judged
#                  good or bad by ear. These are the arguable ones. Retune
#                  them freely as the catalog grows; that is not cheating,
#                  it is what calibration means.
# ─────────────────────────────────────────────────────────────────────────────

# [CALIBRATED] 4-interval contour n-grams that appear more than once, as a share
# of all such n-grams in the lead. Reference points: piece_long_amen 0.03 (a
# motif that never reaches pitch), piece_shake_v5 0.54 and piece_slack_key 0.67
# (three and four `develop` sections respectively). Below WARN, the piece has
# no melodic identity to remember; below FAIL, the "motif" is decorative.
MOTIF_IDENTITY_FAIL: float = 0.10   # bottom ~30% of the catalog
MOTIF_IDENTITY_WARN: float = 0.25   # bottom ~55%

# [CALIBRATED] The inverse check, and the one that surprises people. Rhythm
# n-gram reuse across the catalog runs 89–100%: the motif cell tiles and every
# phrase gets the same rhythmic surface. Total reuse is not groove, it is
# wallpaper. Nothing in the JSON fixes this directly except `note_length_range`
# under `rhythm: "free"` — which is currently null in every piece in the
# catalog. Measured on durations quantized to RHYTHM_QUANTUM so humanization
# noise doesn't read as variety.
RHYTHM_STENCIL_FAIL: float = 0.95
RHYTHM_STENCIL_WARN: float = 0.85
RHYTHM_QUANTUM: float = 0.125  # beats

# [PRIOR] Tonal melody is overwhelmingly conjunct. Steps and repeats should
# carry the line; leaps are events, not texture. A weighted random draw inside
# a register box produces roughly the opposite distribution, which is exactly
# what shows up in the non-`develop` sections (piece_long_amen: 41% leaps, 16%
# of intervals an octave or wider — that is not a melody, that is a walk).
LEAP_SHARE_FAIL: float = 0.35  # intervals >= 5 semitones; worst ~15%
LEAP_SHARE_WARN: float = 0.28  # above the catalog median of 27%
WIDE_LEAP_SHARE_FAIL: float = 0.10  # intervals >= 8 semitones
WIDE_LEAP_SHARE_WARN: float = 0.05

# [PRIOR/CALIBRATED] Melodic span. Every piece in the catalog measures a lead
# span of exactly 24 semitones — the melody hits both walls of the default
# 60–84 register box in every single render. A tune that used its ceiling in
# bar 3 has nothing left for the climax. The prior is that a melody lives in
# roughly a ninth or tenth; the numbers are the catalog's own boundary.
SPAN_SEMITONES_FAIL: int = 24
SPAN_SEMITONES_WARN: int = 21

# [CALIBRATED] Harmony events divided by lead events. The kept Broadway Boogie
# versions (v7/v8) sit at 1.1; the ones that read as a wall of pad sit at 7.7
# (psb_early), 8.0 (whats_i_say, workspace_ambient), 8.3 (aural_anthem). Low
# velocity does not rescue a chord bed with eight times the note count — mass
# wins the mix. Exempt a piece deliberately built as a pad by passing
# --pad-piece.
HARMONY_MASS_FAIL: float = 4.0
HARMONY_MASS_WARN: float = 3.0

# [CALIBRATED] Inner-voice flatness — the clearest machine tell in the catalog,
# ahead of any pitch choice. Counterpoint across a dozen pieces measures a
# velocity standard deviation of 1.3 with two distinct values, and exactly one
# distinct note duration for its entire run (1,864 notes in Broadway Boogie).
# Bass frequently renders at a flat 70. Human inner voices breathe.
VELOCITY_SPREAD_FAIL: float = 2.0
VELOCITY_SPREAD_WARN: float = 4.0
MIN_NOTES_FOR_FLATNESS: int = 40  # below this, one duration is a phrase, not a rut

# [CALIBRATED] Voice dropout. A voice that vanishes for a quarter of the piece
# is either an orchestration decision or an accident, and the engine gives no
# way to tell them apart. Broadway Boogie's counterpoint has a 546-beat gap —
# nine minutes of silence in a track that is otherwise continuous. Worth a look
# either way.
DROPOUT_SHARE_FAIL: float = 0.25
DROPOUT_SHARE_WARN: float = 0.15

# Below this many lead notes, every metric here is noise.
MIN_NOTES_FOR_ANALYSIS: int = 12

NGRAM: int = 4


# ─────────────────────────────────────────────────────────────────────────────
# Findings
# ─────────────────────────────────────────────────────────────────────────────

FAIL, WARN, PASS, SKIP = "FAIL", "WARN", "PASS", "SKIP"
_RANK = {FAIL: 3, WARN: 2, PASS: 1, SKIP: 0}


PIECE, ENGINE = "piece", "engine"


@dataclass
class Finding:
    """
    One metric, its measured value, its verdict, and what to do about it.

    `tier` is the important field. A metric only belongs in the per-piece gate
    if it actually varies between pieces; measured across 71 renders:

        motif identity   0% / 4% / 13% / 37% / 96%   (min/p25/med/p75/max)
        leap share      10% / 20% / 27% / 32% / 78%
        harmony mass    0.1× / 1.9× / 2.5× / 3.6× / 8.3×
        rhythm reuse     0% / 84% / 92% / 98% / 100%
        register span   19st / 24st / 24st / 24st / 29st   (61 of 71 = exactly 24)

    The first three sort pieces. The last two do not — they measure the engine.
    Register span is 24 in 61 of 71 renders because 24 is the width of the
    default 60–84 box and almost nothing ever overrides it; rhythm reuse sits
    near ceiling because the motif cell tiles unchanged and `note_length_range`
    is null everywhere. Gating each piece on a system-wide constant produces a
    tool that fails 100% of its input, which is the same as no tool at all —
    so ENGINE findings are collected once per batch and reported as an
    architecture list, not as a verdict on any one piece.
    """
    metric: str
    verdict: str
    value: str
    detail: str
    remedy: str = ""
    tier: str = PIECE

    def format(self) -> str:
        mark = {FAIL: "✗", WARN: "!", PASS: "✓", SKIP: "–"}[self.verdict]
        line = f"  {mark} {self.metric:<20} {self.value:>10}   {self.detail}"
        if self.remedy and self.verdict in (FAIL, WARN):
            line += f"\n      → {self.remedy}"
        return line


@dataclass
class Note:
    start: float      # beats
    duration: float   # beats
    pitch: int
    velocity: int


@dataclass
class Report:
    path: Path
    findings: list[Finding] = field(default_factory=list)
    fingerprint: str = ""
    beats: float = 0.0

    @property
    def verdict(self) -> str:
        """Piece-tier only — engine constants are not this piece's fault."""
        piece = [f.verdict for f in self.findings if f.tier == PIECE]
        if not piece:
            return SKIP
        return max(piece, key=lambda v: _RANK[v])


# ─────────────────────────────────────────────────────────────────────────────
# MIDI reading
# ─────────────────────────────────────────────────────────────────────────────

def _read_tracks(path: Path) -> tuple[dict[str, list[Note]], float]:
    """
    Absolute-time note extraction per named track, in beats.

    Pairs note_on/note_off per pitch in FIFO order, which is correct for the
    engine's output (it never overlaps the same pitch within a voice) and
    degrades gracefully if some future version does.
    """
    mid = mido.MidiFile(str(path))
    tpb = mid.ticks_per_beat or 480
    tracks: dict[str, list[Note]] = {}

    for index, track in enumerate(mid.tracks):
        name = (track.name or f"track_{index}").strip()
        clock = 0
        pending: dict[int, list[tuple[int, int]]] = {}
        notes: list[Note] = []
        is_percussion = False

        for msg in track:
            clock += msg.time
            if msg.type == "note_on" and msg.velocity > 0:
                if getattr(msg, "channel", 0) == 9:
                    is_percussion = True
                pending.setdefault(msg.note, []).append((clock, msg.velocity))
            elif msg.type == "note_off" or (msg.type == "note_on" and msg.velocity == 0):
                queue = pending.get(msg.note)
                if queue:
                    start, velocity = queue.pop(0)
                    notes.append(Note(start / tpb, (clock - start) / tpb, msg.note, velocity))

        if not notes:
            continue
        key = name if not is_percussion else f"{name} (perc)"
        tracks[key] = sorted(notes, key=lambda n: (n.start, n.pitch))

    span = max((n.start + n.duration for ns in tracks.values() for n in ns), default=0.0)
    return tracks, span


def _find(tracks: dict[str, list[Note]], wanted: str) -> list[Note]:
    for name, notes in tracks.items():
        if name.lower().startswith(wanted) and "(perc)" not in name:
            return notes
    return []


def _is_percussion(name: str) -> bool:
    low = name.lower()
    return "(perc)" in low or any(low.startswith(p) for p in PERCUSSION_TRACKS)


def _reuse(sequence: list, n: int = NGRAM) -> Optional[float]:
    """Share of n-grams that occur more than once. None if too short to judge."""
    if len(sequence) < n + 4:
        return None
    grams = Counter(tuple(sequence[i:i + n]) for i in range(len(sequence) - n + 1))
    total = sum(grams.values())
    repeated = sum(count for count in grams.values() if count > 1)
    return repeated / total


def _verdict(value: float, warn: float, fail: float, higher_is_worse: bool = True) -> str:
    if higher_is_worse:
        if value >= fail:
            return FAIL
        return WARN if value >= warn else PASS
    if value <= fail:
        return FAIL
    return WARN if value <= warn else PASS


# ─────────────────────────────────────────────────────────────────────────────
# The checks
# ─────────────────────────────────────────────────────────────────────────────

def has_motif(piece: dict) -> bool:
    """
    True if the piece defines a primary motif with real `intervals` —
    same resolution order as the engine's own `PieceModel.primary_motif`
    (`motifs[0]` if the array is set, else `motif`).

    Used to waive the motif-identity metric entirely for pieces that never
    claimed a hook in the first place: a purely generative/ambient piece
    with no motif block isn't failing to be memorable, it's honestly
    textural, and shouldn't score the same FAIL as a piece that defined
    `intervals` and then never developed them (see lint.py's
    `_check_motif_never_developed`, the authoring-time half of this check).
    """
    p = piece.get("piece", piece)
    motifs = p.get("motifs")
    m = motifs[0] if motifs else p.get("motif")
    if not m:
        return False
    if isinstance(m, dict):
        return bool(m.get("intervals"))
    return True  # named string ref to a pool entry — can't resolve the pool
                 # here, so assume real rather than false-waiving a valid piece


def _check_motif_identity(lead: list[Note], waived: bool = False) -> Iterator[Finding]:
    intervals = [b.pitch - a.pitch for a, b in zip(lead, lead[1:])]
    reuse = _reuse(intervals)
    if reuse is None:
        return
    if waived:
        yield Finding(
            "motif identity", SKIP, f"{reuse:.0%}",
            "no motif defined for this piece — nothing to develop, not scored",
            "", PIECE,
        )
        return
    verdict = _verdict(reuse, MOTIF_IDENTITY_WARN, MOTIF_IDENTITY_FAIL, higher_is_worse=False)
    yield Finding(
        "motif identity", verdict, f"{reuse:.0%}",
        f"contour {NGRAM}-grams recurring (want >{MOTIF_IDENTITY_WARN:.0%})",
        "the lead's pitch shape never returns — set behavior: \"develop\" on voices[0], "
        "and prune transform_pool to inversion/retrograde/shuffle/sequence "
        "(the rest are rhythm-only or dead)",
    )


def _check_rhythm_stencil(lead: list[Note]) -> Iterator[Finding]:
    durations = [round(n.duration / RHYTHM_QUANTUM) for n in lead]
    reuse = _reuse(durations)
    if reuse is None:
        return
    verdict = _verdict(reuse, RHYTHM_STENCIL_WARN, RHYTHM_STENCIL_FAIL, higher_is_worse=True)
    distinct = len({n.duration for n in lead})
    yield Finding(
        "rhythm stencil", verdict, f"{reuse:.0%}",
        f"duration {NGRAM}-grams recurring, {distinct} distinct lengths "
        f"(want <{RHYTHM_STENCIL_WARN:.0%})",
        "the motif cell is tiling unchanged — give at least the breathing sections "
        "rhythm: \"free\" plus a note_length_range, or vary chord_bars so phrases "
        "stop landing identically",
        tier=ENGINE,
    )


def _check_leap_profile(lead: list[Note]) -> Iterator[Finding]:
    intervals = [abs(b.pitch - a.pitch) for a, b in zip(lead, lead[1:])]
    if not intervals:
        return
    leaps = sum(1 for i in intervals if i >= 5) / len(intervals)
    wide = sum(1 for i in intervals if i >= 8) / len(intervals)
    verdict = max(
        _verdict(leaps, LEAP_SHARE_WARN, LEAP_SHARE_FAIL),
        _verdict(wide, WIDE_LEAP_SHARE_WARN, WIDE_LEAP_SHARE_FAIL),
        key=lambda v: _RANK[v],
    )
    yield Finding(
        "leap profile", verdict, f"{leaps:.0%}",
        f"intervals ≥4th, {wide:.0%} ≥m6 (want <{LEAP_SHARE_WARN:.0%} / "
        f"<{WIDE_LEAP_SHARE_WARN:.0%})",
        "a disjunct line is the signature of a random draw inside a register box — "
        "narrow the lead's register and prefer develop over lyrical/generative",
    )


def _check_register_discipline(lead: list[Note]) -> Iterator[Finding]:
    pitches = [n.pitch for n in lead]
    span = max(pitches) - min(pitches)
    verdict = _verdict(float(span), float(SPAN_SEMITONES_WARN), float(SPAN_SEMITONES_FAIL))
    concentration = sum(c for _, c in Counter(pitches).most_common(5)) / len(pitches)
    yield Finding(
        "register span", verdict, f"{span} st",
        f"lead spans {span} semitones, top-5 pitches {concentration:.0%} of notes",
        "the lead is using both walls of its register box, so the climax has nowhere "
        "to go — set an explicit narrow register and widen it in exactly one section",
        tier=ENGINE,
    )


def _check_harmony_mass(lead: list[Note], harmony: list[Note], pad_piece: bool) -> Iterator[Finding]:
    if not harmony or not lead:
        return
    ratio = len(harmony) / len(lead)
    if pad_piece:
        yield Finding("harmony mass", SKIP, f"{ratio:.1f}×",
                      "pad piece — mass check waived", "")
        return
    verdict = _verdict(ratio, HARMONY_MASS_WARN, HARMONY_MASS_FAIL)
    yield Finding(
        "harmony mass", verdict, f"{ratio:.1f}×",
        f"{len(harmony)} chord events vs {len(lead)} lead events",
        "the chord bed outweighs the tune and will win the mix regardless of velocity — "
        "move harmony_rhythm toward \"sustain\", or drop its density",
    )


def _check_voice_flatness(tracks: dict[str, list[Note]]) -> Iterator[Finding]:
    for name, notes in tracks.items():
        if _is_percussion(name):
            continue
        if not any(name.lower().startswith(p) for p in INNER_VOICE_PREFIXES):
            continue
        if len(notes) < MIN_NOTES_FOR_FLATNESS:
            continue
        velocities = [n.velocity for n in notes]
        spread = statistics.pstdev(velocities) if len(set(velocities)) > 1 else 0.0
        distinct_durations = len({round(n.duration / RHYTHM_QUANTUM) for n in notes})
        verdict = _verdict(spread, VELOCITY_SPREAD_WARN, VELOCITY_SPREAD_FAIL,
                           higher_is_worse=False)
        if distinct_durations == 1 and verdict == PASS:
            verdict = WARN

        remedies = []
        if spread < VELOCITY_SPREAD_WARN:
            remedies.append("this voice holds one velocity for the whole render — "
                            "vary its `velocity` per section so the arc can act on it")
        if distinct_durations == 1:
            remedies.append("and one note length throughout — free species with its own "
                            "note_length_range, or a groove, will break the lockstep")
        yield Finding(
            f"flatness: {name[:12]}", verdict, f"σ{spread:.1f}",
            f"{len(set(velocities))} distinct velocities, {distinct_durations} "
            f"distinct durations over {len(notes)} notes",
            " ".join(remedies),
            tier=ENGINE,
        )


def _check_dropout(tracks: dict[str, list[Note]], span: float) -> Iterator[Finding]:
    if span <= 0:
        return
    for name, notes in tracks.items():
        if _is_percussion(name) or len(notes) < 8:
            continue
        onsets = sorted({n.start for n in notes})
        gaps = [b - a for a, b in zip(onsets, onsets[1:])]
        if not gaps:
            continue
        widest = max(gaps)
        share = widest / span
        verdict = _verdict(share, DROPOUT_SHARE_WARN, DROPOUT_SHARE_FAIL)
        if verdict == PASS:
            continue
        yield Finding(
            f"dropout: {name[:12]}", verdict, f"{widest:.0f} beats",
            f"silent for {share:.0%} of the piece",
            "either an orchestration choice or an accident, and the render can't tell "
            "you which — confirm the voice is meant to be absent there",
        )


# ─────────────────────────────────────────────────────────────────────────────
# Section attribution
#
# The checks above judge a whole rendered track. That tells you a piece has a
# problem; it doesn't tell you where. This maps the piece JSON's own bar map
# onto beat ranges and re-runs the piece-tier checks on each slice, so a FAIL
# can be pointed at "bridge" instead of "beat 214".
#
# One honest caveat, learned the hard way on Frère Jacques: motif identity is
# an n-gram-share metric, and short slices don't give it enough grams to be
# reliable. A section only gets a verdict here if it clears
# MIN_NOTES_FOR_SECTION; shorter sections are listed but marked INFO rather
# than judged, so a four-bar intro doesn't get a false FAIL for the crime of
# being short. Assumes 4/4 (matches main.py's own beats_per_bar assumption in
# display_info/duration math); a piece in another meter will misattribute bar
# boundaries and should be read with that in mind.
# ─────────────────────────────────────────────────────────────────────────────

MIN_NOTES_FOR_SECTION: int = 10
BEATS_PER_BAR: int = 4
INFO = "INFO"
_RANK[INFO] = 0


def section_timeline(piece: dict) -> list[tuple[str, float, float]]:
    """[(section_name, start_beat, end_beat), ...] in performance order."""
    sections = piece.get("sections", {})
    if piece.get("form_type") == "song":
        order = [f.get("section") if isinstance(f, dict) else f
                 for f in piece.get("form", [])]
        lookup = sections if isinstance(sections, dict) else {s.get("name"): s for s in sections}
    else:
        seq = sections if isinstance(sections, list) else list(sections.values())
        order = [s.get("name", f"section_{i}") for i, s in enumerate(seq)]
        lookup = {s.get("name", f"section_{i}"): s for i, s in enumerate(seq)}

    timeline, clock = [], 0.0
    seen: dict[str, int] = {}
    for name in order:
        bars = (lookup.get(name) or {}).get("bars", 0)
        beats = bars * BEATS_PER_BAR
        seen[name] = seen.get(name, 0) + 1
        occurrences = order.count(name)
        label = name if occurrences == 1 else f"{name} #{seen[name]}"
        timeline.append((label, clock, clock + beats))
        clock += beats
    return timeline


def _slice(notes: list[Note], start: float, end: float) -> list[Note]:
    return [n for n in notes if start <= n.start < end]


def analyze_sections(tracks: dict[str, list[Note]], piece: dict) -> list[Finding]:
    lead = _find(tracks, LEAD_TRACK)
    harmony = _find(tracks, HARMONY_TRACK)
    findings: list[Finding] = []

    for name, start, end in section_timeline(piece):
        lead_slice = _slice(lead, start, end)
        if len(lead_slice) < MIN_NOTES_FOR_SECTION:
            findings.append(Finding(
                f"§{name}", INFO, f"{len(lead_slice)}n",
                "too short to judge on its own — read in context of neighbors", "", PIECE))
            continue
        for finding in list(_check_motif_identity(lead_slice)) + list(_check_leap_profile(lead_slice)):
            if finding.verdict in (FAIL, WARN):
                finding.metric = f"§{name}: {finding.metric}"
                findings.append(finding)
        harmony_slice = _slice(harmony, start, end)
        for finding in _check_harmony_mass(lead_slice, harmony_slice, pad_piece=False):
            if finding.verdict in (FAIL, WARN):
                finding.metric = f"§{name}: {finding.metric}"
                findings.append(finding)

    return findings


def format_section_report(findings: list[Finding]) -> str:
    trouble = [f for f in findings if f.verdict in (FAIL, WARN)]
    if not trouble:
        return ""
    lines = ["  trouble sections:"]
    lines += [f.format() for f in trouble]
    return "\n".join(lines)


_MARK = {FAIL: "FAIL", WARN: "warn", PASS: "ok", SKIP: "-", INFO: "-"}


def _row_metrics(lead_slice: list[Note], harmony_slice: list[Note], waived: bool = False) -> dict[str, Finding]:
    """One Finding per metric, keyed by name — PASS included, not just trouble."""
    out: dict[str, Finding] = {}
    for f in _check_motif_identity(lead_slice, waived=waived):
        out["motif"] = f
    for f in _check_leap_profile(lead_slice):
        out["leap"] = f
    for f in _check_harmony_mass(lead_slice, harmony_slice, pad_piece=False):
        out["harmony"] = f
    return out


def format_table(path: Path, report: Report, tracks: dict[str, list[Note]], piece: dict) -> str:
    """
    One row per section plus an OVERALL row. Same three piece-tier metrics as
    the bullet report, just laid out so the worst section is visible at a
    glance instead of buried in a wall of text. `-` means the metric didn't
    apply (no harmony in that slice, or too few notes to judge).
    """
    lead = _find(tracks, LEAD_TRACK)
    harmony = _find(tracks, HARMONY_TRACK)
    waived = not has_motif(piece)

    rows: list[tuple[str, int, dict[str, Finding]]] = []
    rows.append(("OVERALL", len(lead), _row_metrics(lead, harmony, waived=waived)))

    for name, start, end in section_timeline(piece):
        lslice = _slice(lead, start, end)
        if len(lslice) < MIN_NOTES_FOR_SECTION:
            rows.append((name, len(lslice), {}))
            continue
        hslice = _slice(harmony, start, end)
        rows.append((name, len(lslice), _row_metrics(lslice, hslice, waived=waived)))

    name_w = max(7, max(len(r[0]) for r in rows))
    cols = [("notes", 5), ("motif", 12), ("leap", 14), ("harmony", 10)]
    header = f"{'section':<{name_w}} | " + " | ".join(f"{c:<{w}}" for c, w in cols)
    sep = "-" * len(header)

    def cell(f: Optional[Finding], width: int) -> str:
        if f is None:
            return "-".ljust(width)
        return f"{f.value} {_MARK[f.verdict]}".ljust(width)

    lines = [f"{path.name}  [{report.verdict}]  {report.beats:.0f} beats", header, sep]
    for name, n, metrics in rows:
        lines.append(
            f"{name:<{name_w}} | {str(n):<5} | "
            f"{cell(metrics.get('motif'), 12)} | "
            f"{cell(metrics.get('leap'), 14)} | "
            f"{cell(metrics.get('harmony'), 10)}"
        )
        if n < MIN_NOTES_FOR_SECTION and name != "OVERALL":
            lines[-1] += "   (too short to judge alone)"
    return "\n".join(lines)


# ─────────────────────────────────────────────────────────────────────────────
# Orchestration
# ─────────────────────────────────────────────────────────────────────────────

def analyze(path: Path, pad_piece: bool = False, piece: Optional[dict] = None) -> Report:
    tracks, span = _read_tracks(path)
    report = Report(path=path, beats=span)
    report.fingerprint = hashlib.sha1(path.read_bytes()).hexdigest()[:12]

    lead = _find(tracks, LEAD_TRACK)
    harmony = _find(tracks, HARMONY_TRACK)
    waived = piece is not None and not has_motif(piece)

    if len(lead) < MIN_NOTES_FOR_ANALYSIS:
        report.findings.append(Finding(
            "lead track", SKIP, f"{len(lead)}",
            "too few lead notes to judge — melodic metrics skipped", ""))
    else:
        report.findings.extend(_check_motif_identity(lead, waived=waived))
        report.findings.extend(_check_rhythm_stencil(lead))
        report.findings.extend(_check_leap_profile(lead))
        report.findings.extend(_check_register_discipline(lead))

    report.findings.extend(_check_harmony_mass(lead, harmony, pad_piece))
    report.findings.extend(_check_voice_flatness(tracks))
    report.findings.extend(_check_dropout(tracks, span))
    return report


def report_for_piece(midi_path: str, piece: dict, verbose: bool = False, table: bool = True) -> str:
    """
    Entry point for main.py. Same posture as lint's format_report: call after
    a successful render, print if non-empty, never raise, never block.
    Needs the piece dict (not just the path) to build the section timeline —
    main.py already has it in memory from load_song(), so pass that same dict.

    table=True (default) renders the compact per-section grid — the right
    default for a workflow that runs on every render, since a wall of bullet
    findings per piece stops getting read after the second file. Pass
    table=False for the old bullet-list detail when digging into one piece.
    """
    path = Path(midi_path)
    try:
        tracks, _ = _read_tracks(path)
        report = analyze(path, piece=piece)
    except Exception as exc:
        return f"  (slop_metrics skipped: {exc})"

    if table:
        return format_table(path, report, tracks, piece)

    section_findings = analyze_sections(tracks, piece)
    body = format_report(report, verbose=verbose)
    section_block = format_section_report(section_findings)
    return body + ("\n" + section_block if section_block else "")


def format_report(report: Report, verbose: bool = False) -> str:
    """Per-file block, piece tier only. Same posture as lint's report: visible, not alarming."""
    piece = [f for f in report.findings if f.tier == PIECE]
    shown = piece if verbose else [f for f in piece if f.verdict in (FAIL, WARN, SKIP)]
    header = f"{report.path.name}  [{report.verdict}]  {report.beats:.0f} beats"
    if not shown:
        return header + "\n  ✓ clean"
    return "\n".join([header] + [f.format() for f in shown])


def format_engine_findings(reports: list[Report]) -> str:
    """
    Engine-tier findings, collapsed across the batch.

    These are properties of the system rather than choices in any one piece, so
    they are reported once as a standing architecture list. Each line shows how
    many renders in this batch exhibit it — a count of 71 out of 71 is not a
    quality signal about the pieces, it is a to-do item about the engine.
    """
    tally: dict[str, list[Finding]] = {}
    for r in reports:
        for f in r.findings:
            if f.tier == ENGINE and f.verdict in (FAIL, WARN):
                tally.setdefault(f.metric.split(":")[0].strip(), []).append(f)
    if not tally:
        return ""
    total = len(reports)
    lines = ["engine-level findings (not any one piece's fault):"]
    for metric, hits in sorted(tally.items(), key=lambda kv: -len(kv[1])):
        affected = len({id(h) for h in hits})
        lines.append(f"  · {metric:<18} {affected:>3} findings across {total} renders")
        lines.append(f"      {hits[0].remedy}")
    return "\n".join(lines)


def _duplicate_renders(reports: list[Report]) -> list[list[Report]]:
    """
    Byte-identical renders under different names. Four such pairs currently sit
    in the catalog. Two files that sound the same mean one of them didn't
    happen — a real cost against a two-pieces-per-week cadence.
    """
    groups: dict[str, list[Report]] = {}
    for r in reports:
        groups.setdefault(r.fingerprint, []).append(r)
    return [g for g in groups.values() if len(g) > 1]


def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        description="Judge rendered FormaComposition MIDI for legal-but-unmemorable output.")
    parser.add_argument("files", nargs="+", type=Path, help="rendered .mid file(s)")
    parser.add_argument("--verbose", "-v", action="store_true",
                        help="show passing metrics too")
    parser.add_argument("--pad-piece", action="store_true",
                        help="waive the harmony-mass check (piece is deliberately a pad)")
    parser.add_argument("--strict", action="store_true",
                        help="exit 1 if any file has a FAIL")
    parser.add_argument("--summary", action="store_true",
                        help="one line per file instead of full findings")
    parser.add_argument("--table", action="store_true",
                        help="compact per-section ASCII grid (needs --piece)")
    parser.add_argument("--piece", type=Path, default=None,
                        help="matching piece JSON, for section attribution "
                             "(--table and --strict section checks need this)")
    args = parser.parse_args(argv)

    piece_json = None
    if args.piece:
        import json
        piece_json = json.loads(args.piece.read_text())

    reports: list[Report] = []
    for path in args.files:
        try:
            reports.append(analyze(path, pad_piece=args.pad_piece, piece=piece_json))
        except Exception as exc:  # a bad file shouldn't take the batch down
            print(f"{path.name}: could not read ({exc})", file=sys.stderr)

    for report in reports:
        if args.table:
            if piece_json is None:
                print(f"{report.path.name}: --table needs --piece piece.json", file=sys.stderr)
                continue
            tracks, _ = _read_tracks(report.path)
            print(format_table(report.path, report, tracks, piece_json))
            print()
        elif args.summary:
            counts = Counter(f.verdict for f in report.findings if f.tier == PIECE)
            print(f"{report.verdict:<4} {report.path.name:<40} "
                  f"{counts[FAIL]} fail, {counts[WARN]} warn")
        else:
            print(format_report(report, verbose=args.verbose))
            print()

    engine = format_engine_findings(reports)
    if engine:
        print(engine)
        print()

    for group in _duplicate_renders(reports):
        names = ", ".join(r.path.name for r in group)
        print(f"!  identical renders: {names}")

    # strict gates on the piece tier only — engine constants are a backlog,
    # not a reason to block a render.
    if args.strict and any(r.verdict == FAIL for r in reports):
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
