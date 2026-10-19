#!/usr/bin/env python3
"""
migrate_voices.py — convert piece JSON from the pre-2026-09 schema to the
consolidated `voices[]` form.

What it rewrites, per section:

  melody: {...}      ->  voices[0]                  (the dict/VoiceModel arm
                         of `melody` is retired; the lead is just voices[0])
  counterpoint: [..] ->  voices[1:]                 (CounterpointModel retired;
                         every field it carried lives on VoiceModel)
  second_melody: {}  ->  a voices[] peer            (it was a melody-path peer
                         in all but name)
  motif / motifs     ->  DELETED                    (never read at render time)
  percussion         ->  DELETED                    (never read by anything)
  harmony_rhythm.transform_imitation -> DELETED     (only value raised ValueError)

Seed equivalence
----------------
counterpoint[] -> voices[] is seed-identical: the old counterpoint loop and
the peer-voice loop both enumerate from 0 and build the seed the same way
(base_seed + seed_offsets[i] + voice_idx), so counterpoint[0] and voices[1]
land on the same seed.

second_melody is NOT seed-identical. The retired block used a fixed offset of
+200; as a peer it takes +voice_idx like every other voice. Pitch selection
therefore changes. Every piece affected is listed explicitly in the report —
those need a re-listen, or a deliberate decision to leave the released render
alone. The same voices also move from the dedicated second-melody MIDI channel
onto a peer channel (which now recycles that same channel number as the 4th
peer slot), so a Logic project mapping channels to instruments may need a look.

Usage
-----
    python forma/migrate_voices.py compositions/*.json          # in place
    python forma/migrate_voices.py --dry-run compositions/*.json
    python forma/migrate_voices.py --outdir migrated/ compositions/*.json
"""

from __future__ import annotations

import argparse
import json
import shutil
import sys
from pathlib import Path

# Field renames when a CounterpointModel entry becomes a VoiceModel entry.
# Everything else carried the same name on both models already.
_CP_RENAMES = {
    # CounterpointModel used alias "register" for cp_register; VoiceModel
    # uses alias "register" for v_register. Same JSON key, no rewrite needed.
}

# CounterpointModel fields that VoiceModel now carries verbatim.
_CP_PASSTHROUGH = {
    "species", "register", "dissonance", "velocity", "canon_offset",
    "motif", "rhythm_density", "groove", "note_length_range",
}

_DROP_FROM_SECTION = ("motif", "motifs", "percussion")


class Report:
    def __init__(self) -> None:
        self.changed: list[str] = []
        self.unchanged: list[str] = []
        self.second_melody_pieces: list[str] = []
        self.dropped: dict[str, int] = {}
        self.overflow: list[str] = []

    def drop(self, field: str) -> None:
        self.dropped[field] = self.dropped.get(field, 0) + 1


def _migrate_section(sec: dict, rep: Report, piece_label: str) -> bool:
    """Rewrite one section in place. Returns True if anything changed."""
    touched = False

    # ── Assemble voices[] ─────────────────────────────────────────────────
    voices = sec.get("voices")
    already_had_voices = voices is not None
    voices = list(voices) if already_had_voices else []

    # Lead: melody-as-dict becomes voices[0]. A bare string stays as `melody`.
    melody = sec.get("melody")
    if isinstance(melody, dict):
        if already_had_voices:
            # Both forms present is contradictory — generator.py let voices[]
            # win silently. Preserve that outcome, but say so.
            print(f"  ! {piece_label}: section "
                  f"{sec.get('name', '?')!r} had BOTH melody-as-dict and "
                  f"voices[]; voices[] won at render time, so the melody dict "
                  f"is dropped (this matches what it actually sounded like).")
        else:
            voices.insert(0, dict(melody))
        # The lead's behavior stays readable as the plain shorthand too.
        sec["melody"] = melody.get("behavior", "generative")
        touched = True

    # If we're about to add peers but have no lead, synthesise voices[0] from
    # the bare `melody` string so peer indices line up with the old loop.
    #
    # velocity is pinned to 72 deliberately. A bare-string `melody` used
    # generator.py's LEAD_VELOCITY_DEFAULT (72); VoiceModel.velocity defaults
    # to 64. Left unpinned, every migrated lead that never named a velocity
    # would drop 8 — inaudible in a test assertion, obvious in a byte-diff of
    # the rendered MIDI. Register needs no pin: MELODY_OCTAVE_BOTTOM/TOP are
    # literally REGISTER_BOUNDS["mid"], which is VoiceModel's own default.
    def _ensure_lead() -> None:
        nonlocal voices
        if not voices:
            beh = sec.get("melody")
            voices = [{
                "behavior": beh if isinstance(beh, str) else "generative",
                "velocity": 72,
            }]

    # Counterpoint entries become peers, in order.
    cp = sec.get("counterpoint")
    if cp is not None:
        if isinstance(cp, dict):      # legacy bare-object form
            cp = [cp]
        _ensure_lead()
        for entry in cp:
            v = {k: val for k, val in entry.items() if k in _CP_PASSTHROUGH}
            unknown = set(entry) - _CP_PASSTHROUGH
            if unknown:
                print(f"  ! {piece_label}: dropping unrecognised counterpoint "
                      f"key(s) {sorted(unknown)} in section "
                      f"{sec.get('name', '?')!r}")
            # A counterpoint voice defaulted to species="free",
            # register="below" (now: tenor) and velocity=58; VoiceModel defaults to no
            # species (melody path), register="mid" and velocity=64. Pin all
            # three so the migrated voice takes the same code path at the
            # same loudness it always did. Without the velocity pin the
            # migration is silently +6 on every counterpoint line that never
            # named one — caught by byte-diffing rendered MIDI, not by tests.
            v.setdefault("species", "free")
            v.setdefault("register", "tenor")
            v.setdefault("velocity", 58)
            voices.append(v)
        del sec["counterpoint"]
        touched = True

    # second_melody becomes a melody-path peer (no species).
    sm = sec.get("second_melody")
    if sm is not None:
        _ensure_lead()
        v = dict(sm)
        v.pop("species", None)      # schema rejected these here anyway
        v.pop("entry_role", None)
        voices.append(v)
        del sec["second_melody"]
        if piece_label not in rep.second_melody_pieces:
            rep.second_melody_pieces.append(piece_label)
        touched = True

    if voices:
        if len(voices) > 5:
            rep.overflow.append(
                f"{piece_label} section {sec.get('name', '?')!r}: "
                f"{len(voices)} voices (cap is 5)")
        sec["voices"] = voices

    # ── Drop the dead fields ──────────────────────────────────────────────
    for field in _DROP_FROM_SECTION:
        if field in sec:
            del sec[field]
            rep.drop(f"section.{field}")
            touched = True

    hr = sec.get("harmony_rhythm")
    if isinstance(hr, dict) and "transform_imitation" in hr:
        del hr["transform_imitation"]
        rep.drop("harmony_rhythm.transform_imitation")
        touched = True

    return touched


def _iter_sections(container) -> list:
    """Sections may be a list (narrative form) or a name-keyed dict (song
    form, under either `sections` or `song_sections` depending on how the
    piece was written). Yield the section dicts from whichever shape."""
    if isinstance(container, list):
        return [s for s in container if isinstance(s, dict)]
    if isinstance(container, dict):
        return [s for s in container.values() if isinstance(s, dict)]
    return []


def migrate_piece(data: dict, rep: Report, label: str) -> bool:
    # Piece files are written as {"piece": {...}}; accept a bare piece dict
    # too, since main.py's loader tolerates both.
    body = data.get("piece") if isinstance(data.get("piece"), dict) else data
    touched = False
    for key in ("sections", "song_sections"):
        for sec in _iter_sections(body.get(key)):
            touched |= _migrate_section(sec, rep, label)
    return touched


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("pieces", nargs="+", type=Path)
    ap.add_argument("--dry-run", action="store_true",
                    help="report what would change; write nothing")
    ap.add_argument("--outdir", type=Path,
                    help="write migrated copies here instead of in place")
    ap.add_argument("--no-backup", action="store_true",
                    help="skip the .json.bak copy when migrating in place")
    args = ap.parse_args(argv)

    rep = Report()
    for path in args.pieces:
        try:
            data = json.loads(path.read_text())
        except Exception as exc:                       # noqa: BLE001
            print(f"  ! {path.name}: unreadable ({exc}) — skipped")
            continue

        if not migrate_piece(data, rep, path.name):
            rep.unchanged.append(path.name)
            continue

        rep.changed.append(path.name)
        if args.dry_run:
            continue

        out = (args.outdir / path.name) if args.outdir else path
        if args.outdir:
            args.outdir.mkdir(parents=True, exist_ok=True)
        elif not args.no_backup:
            shutil.copy2(path, path.with_suffix(".json.bak"))
        out.write_text(json.dumps(data, indent=2) + "\n")

    # ── Report ────────────────────────────────────────────────────────────
    print()
    print(f"migrated : {len(rep.changed)}")
    print(f"unchanged: {len(rep.unchanged)}")
    if rep.dropped:
        print("\ndead fields removed (these never did anything at render time):")
        for field, n in sorted(rep.dropped.items()):
            print(f"  {field}: {n}")
    if rep.overflow:
        print("\n  ! OVER THE VOICE CAP — these will fail validation:")
        for line in rep.overflow:
            print(f"    {line}")
    if rep.second_melody_pieces:
        print("\n  ! OUTPUT WILL CHANGE in these pieces (second_melody -> peer voice):")
        for name in rep.second_melody_pieces:
            print(f"    {name}")
        print("    The retired block used seed offset +200; a peer voice uses")
        print("    +voice_idx, so pitch selection differs. Re-listen, or keep")
        print("    the released render and leave the piece unmigrated.")
        print("    These voices also move to a peer MIDI channel — check any")
        print("    Logic project that maps channels to instruments.")
    if args.dry_run:
        print("\n(dry run — nothing written)")
    return 1 if rep.overflow else 0


if __name__ == "__main__":
    sys.exit(main())
