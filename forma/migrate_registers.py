#!/usr/bin/env python3
"""
migrate_registers.py -- convert removed "above"/"below" voice registers to
named SATB registers, editing the files in place.

"above" and "below" had no fixed band: a counterpoint voice using one
stretched across the melody's whole span plus margins (~30 semitones), which
let lines leap between registers. Every named register is a fixed 18-semitone
box instead. This tool rewrites each such voice to the named register that
sits clearly higher ("above") or lower ("below") than the section's lead
voice (at least 3 semitones between centres), stepping one further for each additional voice on the same side so
peers get distinct registers instead of sharing one box.

Only the register VALUE is changed, by text substitution -- the rest of the
file (column-aligned arrays, comments-in-strings, key order, spacing) is left
byte-for-byte as written.

Usage:
    python forma/migrate_registers.py compositions/*.json
    python forma/migrate_registers.py compositions/*.json --dry-run

Review the report. Where there is nothing higher than the lead (a soprano or
high lead with an "above" voice) the voice is placed in "soprano" and flagged:
it shares the lead's box, so you may want a different arrangement there.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Iterator, Optional

# Register centres (MIDI pitch), from REGISTER_BOUNDS in intervals/core/schemas.py.
# Kept literal here so the tool runs on files the current schema rejects.
_CENTERS = {
    "soprano": 72.0, "alto": 67.0, "tenor": 60.0, "baritone": 55.0, "bass": 48.0,
    "high": 76.0, "mid": 69.0, "low_mid": 57.0, "low": 45.0,
}
# The ladder voices are moved along: the five named SATB registers only.
_LADDER = ("bass", "baritone", "tenor", "alto", "soprano")
_DEFAULT_LEAD = "mid"   # VoiceModel's own default register
_RELATIVE = ("above", "below")
# A peer must sit at least this many semitones from the lead's centre to count
# as "above"/"below" it -- "alto" (centre 67) under the default "mid" lead
# (centre 69) is the same box in all but name.
_MIN_STEP = 3.0


def lead_center(section: dict) -> float:
    """Centre pitch of the section's lead voice register."""
    mr = section.get("melody_register")
    if isinstance(mr, dict) and "min" in mr and "max" in mr:
        return (mr["min"] + mr["max"]) / 2
    voices = section.get("voices") or []
    reg = voices[0].get("register", _DEFAULT_LEAD) if voices else _DEFAULT_LEAD
    return _CENTERS.get(reg, _CENTERS[_DEFAULT_LEAD])


def peer_register(center: float, relation: str, ordinal: int = 0) -> tuple[str, Optional[str]]:
    """
    Named register for the `ordinal`-th (0-based) peer on `relation` ('above'
    or 'below') of a lead whose register is centred on `center`.

    Returns (register, note). note is None for a clean mapping, else a short
    reason the result deserves a look.
    """
    if relation == "below":
        steps = sorted((r for r in _LADDER if _CENTERS[r] <= center - _MIN_STEP),
                       key=lambda r: -_CENTERS[r])
    else:
        steps = sorted((r for r in _LADDER if _CENTERS[r] >= center + _MIN_STEP),
                       key=lambda r: _CENTERS[r])
    if not steps:
        edge = "soprano" if relation == "above" else "bass"
        return edge, f"nothing {relation} the lead -- shares the {edge} box"
    if ordinal < len(steps):
        return steps[ordinal], None
    return steps[-1], f"only {len(steps)} register(s) {relation} the lead -- shares {steps[-1]} with another voice"


def _walk(node, path: tuple = ()) -> Iterator[tuple[tuple, dict]]:
    """Yield (path, dict) for every dict, depth-first in document order."""
    if isinstance(node, dict):
        yield path, node
        for k, v in node.items():
            yield from _walk(v, path + (k,))
    elif isinstance(node, list):
        for i, v in enumerate(node):
            yield from _walk(v, path + (i,))


def plan(doc: dict) -> list[dict]:
    """
    One entry per `"register": <string>` occurrence anywhere in the document,
    in document order. Entries for above/below voices carry the new register;
    everything else carries new=None (left alone). Returning ALL occurrences
    -- not just the ones to change -- is what lets apply() verify the text
    matches the parse before it writes anything.
    """
    # Group voices[] arrays so each peer knows its section's lead and its
    # ordinal among peers on the same side.
    entries: list[dict] = []
    seen_ordinals: dict[tuple, dict[str, int]] = {}
    for path, d in _walk(doc):
        if "register" not in d or not isinstance(d["register"], str):
            continue
        entry = {"old": d["register"], "new": None, "path": path, "note": None,
                 "lead": None}
        in_voices = len(path) >= 2 and path[-2] == "voices" and isinstance(path[-1], int)
        if d["register"] in _RELATIVE and in_voices:
            sec_path = path[:-2]
            section = doc
            for p in sec_path:
                section = section[p]
            center = lead_center(section)
            counts = seen_ordinals.setdefault(sec_path, {"above": 0, "below": 0})
            new, note = peer_register(center, d["register"], counts[d["register"]])
            counts[d["register"]] += 1
            entry.update(new=new, note=note, lead=center)
        elif d["register"] in _RELATIVE:
            entry["note"] = "outside a voices[] list -- not migrated (run migrate_voices.py first)"
        entries.append(entry)
    return entries


_PATTERN = re.compile(r'("register"\s*:\s*)"([^"\\]*)"')


def apply(text: str, entries: list[dict]) -> str:
    """Substitute the planned registers into `text`, touching nothing else."""
    matches = list(_PATTERN.finditer(text))
    if len(matches) != len(entries):
        raise ValueError(
            f"found {len(matches)} \"register\" strings in the text but "
            f"{len(entries)} in the parsed JSON -- refusing to edit (is a "
            f"register literal quoted inside a string?)"
        )
    out, last = [], 0
    for m, e in zip(matches, entries):
        if m.group(2) != e["old"]:
            raise ValueError(
                f"text/parse mismatch at offset {m.start()}: text has "
                f"{m.group(2)!r}, parse has {e['old']!r} -- refusing to edit"
            )
        out.append(text[last:m.start()])
        out.append(m.group(1) + '"' + (e["new"] or m.group(2)) + '"')
        last = m.end()
    out.append(text[last:])
    return "".join(out)


def migrate_text(text: str) -> tuple[str, list[dict]]:
    """(new_text, changes) for one file's text. changes lists only edits made."""
    doc = json.loads(text)
    entries = plan(doc)
    changes = [e for e in entries if e["new"] is not None]
    skipped = [e for e in entries if e["old"] in _RELATIVE and e["new"] is None]
    new_text = apply(text, entries) if changes else text
    return new_text, changes + skipped


def _where(path: tuple) -> str:
    return "/".join(str(p) for p in path)


def main(argv: Optional[list[str]] = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("files", nargs="+", type=Path)
    ap.add_argument("--dry-run", action="store_true", help="report only; write nothing")
    args = ap.parse_args(argv)

    changed_files = flagged = failures = 0
    for f in args.files:
        try:
            text = f.read_text()
            new_text, items = migrate_text(text)
        except (ValueError, OSError) as exc:     # JSONDecodeError is a ValueError
            print(f"  ! {f}: {exc}")
            failures += 1
            continue
        if not items:
            continue
        print(f"{f}")
        for e in items:
            tag = f"{e['old']} -> {e['new']}" if e["new"] else f"{e['old']} (unchanged)"
            lead = f"  [lead centre {e['lead']:.0f}]" if e["lead"] is not None else ""
            note = f"   ** {e['note']}" if e["note"] else ""
            flagged += bool(e["note"])
            print(f"   {_where(e['path'])}: {tag}{lead}{note}")
        if new_text != text:
            changed_files += 1
            if not args.dry_run:
                f.write_text(new_text)
    verb = "would change" if args.dry_run else "changed"
    print(f"\n{verb} {changed_files} file(s); {flagged} voice(s) flagged for review; "
          f"{failures} file(s) skipped with errors")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
