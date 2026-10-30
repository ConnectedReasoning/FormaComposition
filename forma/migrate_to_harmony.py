#!/usr/bin/env python3
"""
migrate_to_harmony.py — rewrite section chords from the parallel-array form

    "bars": 5,
    "progression": [ "I", "II", "I", "IV" ],
    "chord_bars":  [ 0.5, 1.5, 1, 2 ]

to one object per chord

    "harmony": [
      { "chord": "I",  "bars": 0.5 },
      { "chord": "II", "bars": 1.5 },
      { "chord": "I",  "bars": 1.0 },
      { "chord": "IV", "bars": 2.0 }
    ]

Text-surgical: only the progression / chord_bars / redundant `bars` entries
are touched. Every other byte of the file (your horizontally aligned motif
blocks, key order, comments-in-notes) is left exactly as written, which a
json.load/json.dump round-trip would not do.

Section-level `bars` is dropped only when it equals sum(chord_bars) (pure
redundancy). It is kept when the chord cell tiles (bars > cell total), when
it disagrees with the total (the engine already warns about that), and when
there is no chord_bars (harmony entries then carry no `bars`, and the
section's `bars` is split evenly, as before).

Safety: before anything is written, the migrated text is loaded through
PieceModel next to the original and the two model dumps must be identical
(progression, chord_bars, bars, bars_list(), resolved_progression() — and
every other field). A file that fails that check is left untouched.

Usage:
    python migrate_to_harmony.py compositions/*.json --dry-run
    python migrate_to_harmony.py compositions/*.json            # in place, writes .json.bak
    python migrate_to_harmony.py compositions/*.json --outdir migrated/
"""

from __future__ import annotations

import argparse
import json
import re
import shutil
import sys
import warnings
from pathlib import Path

_HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(_HERE))

from intervals.core.schemas import PieceModel  # noqa: E402

_DEC = json.JSONDecoder()
_WS = " \t\r\n"
_SECTION_KEYS = ("progression", "chord_bars", "bars", "harmony")


# ── Scanner ──────────────────────────────────────────────────────────────────

def _skip_ws(text: str, i: int) -> int:
    while i < len(text) and text[i] in _WS:
        i += 1
    return i


def _scan_objects(text: str) -> list[dict]:
    """
    Walk the JSON text once and return, for every object that has a
    `progression` key, the spans of its section-relevant keys:
        {"keys": {name: (key_start, val_start, val_end)}}
    Strings are skipped correctly (escapes, keys vs values); the values of
    the keys we care about are measured with raw_decode so their extent is
    exact whatever their internal whitespace looks like.
    """
    stack: list[dict | None] = []
    found: list[dict] = []
    i, n = 0, len(text)
    while i < n:
        c = text[i]
        if c == "{":
            stack.append({"keys": {}})
            i += 1
        elif c == "[":
            stack.append(None)
            i += 1
        elif c in "}]":
            done = stack.pop()
            if done is not None and "progression" in done["keys"]:
                found.append(done)
            i += 1
        elif c == '"':
            end = i + 1
            while text[end] != '"':
                end += 2 if text[end] == "\\" else 1
            end += 1
            j = _skip_ws(text, end)
            is_key = j < n and text[j] == ":" and stack and stack[-1] is not None
            if is_key:
                name = json.loads(text[i:end])
                if name in _SECTION_KEYS:
                    val_start = _skip_ws(text, j + 1)
                    _, val_end = _DEC.raw_decode(text, val_start)
                    stack[-1]["keys"][name] = (i, val_start, val_end)
                    i = val_end
                    continue
            i = end
        else:
            i += 1
    return found


# ── Text edits ───────────────────────────────────────────────────────────────

def _fmt_bars(b) -> str:
    return repr(float(b))


def _harmony_text(progression: list[str], chord_bars, key_start: int, text: str) -> str:
    chords = [json.dumps(c) for c in progression]
    width = max(len(c) for c in chords)
    line_start = text.rfind("\n", 0, key_start) + 1
    lead = text[line_start:key_start]
    if lead.strip():                      # key is mid-line (compact JSON)
        rows = []
        for k, c in enumerate(chords):
            rows.append(f'{{ "chord": {c}' + (
                f', "bars": {_fmt_bars(chord_bars[k])} }}' if chord_bars else " }"))
        return '"harmony": [ ' + ", ".join(rows) + " ]"
    indent = lead
    rows = []
    for k, c in enumerate(chords):
        if chord_bars:
            pad = " " * (width - len(c))
            rows.append(f'{indent}  {{ "chord": {c},{pad} "bars": {_fmt_bars(chord_bars[k])} }}')
        else:
            rows.append(f'{indent}  {{ "chord": {c} }}')
    return '"harmony": [\n' + ",\n".join(rows) + f"\n{indent}]"


def _delete_entry(text: str, key_start: int, val_end: int) -> str:
    """Remove `"key": value` plus exactly one adjoining comma."""
    m = re.match(r"\s*,[ \t]*(?:\r?\n[ \t]*)?", text[val_end:])
    if m:                                  # has a following sibling
        return text[:key_start] + text[val_end + m.end():]
    m = re.search(r",\s*$", text[:key_start])   # last entry: take the comma before
    if m:
        return text[:m.start()] + text[val_end:]
    return text[:key_start] + text[val_end:]


def migrate_text(text: str) -> tuple[str, list[str]]:
    """Return (new_text, notes). Idempotent: sections already on `harmony` are skipped."""
    notes: list[str] = []
    objs = [o for o in _scan_objects(text) if "harmony" not in o["keys"]]
    # Apply from the end of the file backwards so earlier offsets stay valid.
    for obj in sorted(objs, key=lambda o: -o["keys"]["progression"][0]):
        keys = obj["keys"]
        p_ks, p_vs, p_ve = keys["progression"]
        progression = json.loads(text[p_vs:p_ve])
        if not (isinstance(progression, list) and progression
                and all(isinstance(c, str) for c in progression)):
            notes.append("skipped a progression that is not a non-empty list of strings")
            continue
        chord_bars = None
        if "chord_bars" in keys:
            _, c_vs, c_ve = keys["chord_bars"]
            chord_bars = json.loads(text[c_vs:c_ve])
            if (not isinstance(chord_bars, list) or len(chord_bars) != len(progression)
                    or not all(isinstance(b, (int, float)) and not isinstance(b, bool) and b > 0
                               for b in chord_bars)):
                notes.append("skipped a section whose chord_bars is not a matching list of positive numbers")
                continue

        drop_bars = False
        if chord_bars is not None and "bars" in keys:
            b_ks, b_vs, b_ve = keys["bars"]
            bars = json.loads(text[b_vs:b_ve])
            drop_bars = isinstance(bars, (int, float)) and abs(bars - sum(chord_bars)) <= 0.01

        edits = [("replace", p_ks, p_ve, _harmony_text(progression, chord_bars, p_ks, text))]
        if chord_bars is not None:
            edits.append(("delete", keys["chord_bars"][0], keys["chord_bars"][2], None))
        if drop_bars:
            edits.append(("delete", keys["bars"][0], keys["bars"][2], None))
        for kind, a, b, new in sorted(edits, key=lambda e: -e[1]):
            text = (text[:a] + new + text[b:]) if kind == "replace" else _delete_entry(text, a, b)
    return text, notes


# ── Verification ─────────────────────────────────────────────────────────────

def _model_dump(text: str) -> dict:
    data = json.loads(text)
    piece = data.get("piece", data)
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        return PieceModel.model_validate(piece).model_dump()


def verify(old: str, new: str) -> str | None:
    """None if equivalent, else a short reason."""
    try:
        a, b = _model_dump(old), _model_dump(new)
    except Exception as exc:               # noqa: BLE001 - report, don't crash the batch
        return f"validation error: {exc}"
    if a != b:
        diffs = [k for k in a if a.get(k) != b.get(k)]
        return f"model differs after migration (fields: {', '.join(diffs[:5])})"
    return None


# ── CLI ──────────────────────────────────────────────────────────────────────

def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("pieces", nargs="+", type=Path)
    ap.add_argument("--dry-run", action="store_true",
                    help="report what would change; write nothing")
    ap.add_argument("--outdir", type=Path,
                    help="write migrated copies here instead of in place")
    ap.add_argument("--no-backup", action="store_true",
                    help="skip the .json.bak copy when migrating in place")
    args = ap.parse_args(argv)

    failed = 0
    for path in args.pieces:
        old = path.read_text()
        new, notes = migrate_text(old)
        n_old = len([o for o in _scan_objects(old) if "harmony" not in o["keys"]])
        label = f"{path.name}: {n_old} section(s)"
        for note in notes:
            print(f"  note  {path.name}: {note}")
        if new == old:
            print(f"  skip  {label} — nothing to migrate")
            continue
        problem = verify(old, new)
        if problem:
            failed += 1
            print(f"  FAIL  {label} — {problem}; file left untouched")
            continue
        if args.dry_run:
            print(f"  ok    {label} — would migrate (verified identical after validation)")
            continue
        if args.outdir:
            args.outdir.mkdir(parents=True, exist_ok=True)
            (args.outdir / path.name).write_text(new)
            print(f"  ok    {label} — wrote {args.outdir / path.name}")
        else:
            if not args.no_backup:
                shutil.copy2(path, path.with_suffix(path.suffix + ".bak"))
            path.write_text(new)
            print(f"  ok    {label} — migrated in place")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
