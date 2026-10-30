#!/usr/bin/env python3
"""
migrate_to_motif_events.py — rewrite motifs from the parallel-array form

    "intervals":  [ 0,   2,   -2,  -2 ],
    "rhythm":     [ 1.5, 0.5, 1.0, 1.0 ],
    "velocities": [ 1.0, 0.8, 0.9, 0.8 ],
    "rests":      [ false, false, false, true ]

to one object per note

    "events": [
      { "step":  0, "beats": 1.5, "velocity": 1.0 },
      { "step":  2, "beats": 0.5, "velocity": 0.8 },
      { "step": -2, "beats": 1.0, "velocity": 0.9 },
      { "step": -2, "beats": 1.0, "velocity": 0.8, "rest": true }
    ]

Works on every motif the engine reads as a dict: piece `motif` / `motifs`,
`bass_motif`, voice and harmony_rhythm motifs, and library motif files.

Text-surgical: only the intervals / rhythm / rests / velocities entries of a
motif are touched; the `events` block takes the place of `intervals`. Every
other byte of the file (key order, `notes` text, your layout elsewhere) is left
exactly as written, which a json.load/json.dump round-trip would not do.

A rest slot keeps its `step` (as the legacy form keeps intervals[i] for a
rests[i] slot), so the round trip is exact. Motifs whose arrays disagree in
length are reported and left alone.

Safety: before anything is written, the new file is compared with the old one
structurally. Every migrated motif, once expanded back, must equal the original
motif dict; everything else must be identical; and if the file is a piece, both
versions must produce the same validated PieceModel. A file that fails any of
those is left untouched.

Usage:
    python migrate_to_motif_events.py compositions/*.json --dry-run
    python migrate_to_motif_events.py compositions/*.json        # in place, writes .json.bak
    python migrate_to_motif_events.py compositions/*.json --outdir migrated/
"""

from __future__ import annotations

import argparse
import json
import shutil
import sys
import warnings
from pathlib import Path

_HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(_HERE))

from intervals.core.schemas import PieceModel  # noqa: E402
from intervals.music.motif import normalize_motif_dict  # noqa: E402
from migrate_to_harmony import _delete_entry, _skip_ws  # noqa: E402

_DEC = json.JSONDecoder()
_MOTIF_KEYS = ("intervals", "rhythm", "rests", "velocities", "events")


# ── Scanner ──────────────────────────────────────────────────────────────────

def _scan_motifs(text: str) -> list[dict]:
    """
    Walk the JSON text once and return, for every object that has an
    `intervals` key, the spans of its motif keys:
        {"keys": {name: (key_start, val_start, val_end)}}
    Same string-aware walk as migrate_to_harmony, keyed on `intervals`.
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
            if done is not None and "intervals" in done["keys"]:
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
                if name in _MOTIF_KEYS:
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

def _num(x) -> str:
    return repr(float(x))


def _column(values) -> list[str]:
    """Format a numeric column so decimal points line up (0.5 / 0.65 -> 0.50 / 0.65)."""
    raw = [_num(v) for v in values]
    if any("e" in r or "inf" in r or "nan" in r for r in raw):
        return raw
    frac = max(len(r.split(".")[1]) for r in raw)
    padded = [r + "0" * (frac - len(r.split(".")[1])) for r in raw]
    w = max(len(r) for r in padded)
    return [r.rjust(w) for r in padded]


def _events_text(intervals, rhythm, rests, velocities, key_start: int, text: str) -> str:
    n = len(intervals)
    steps = [str(int(s)) for s in intervals]
    beats = _column(rhythm) if rhythm is not None else None
    vels = _column(velocities) if velocities is not None else None
    rest_col = rests if rests is not None else None
    any_true = bool(rest_col) and any(rest_col)
    if rest_col is not None and not any_true:
        # An explicit all-false list must survive the round trip, so the first
        # event carries "rest": false (the key's presence is what makes the list).
        flags = [k == 0 for k in range(n)]
    else:
        flags = list(rest_col) if rest_col is not None else [False] * n

    sw = max(len(s) for s in steps)
    bw = max(len(b) for b in beats) if beats else 0
    vw = max(len(v) for v in vels) if vels else 0
    rest_text = [
        (', "rest": true' if rest_col is not None and any_true and rest_col[k] else
         ', "rest": false' if rest_col is not None and not any_true and k == 0 else "")
        for k in range(n)
    ]
    rw = max(len(r) for r in rest_text)

    def row(k: int) -> str:
        parts = [f'"step": {steps[k].rjust(sw)}']
        if beats:
            parts.append(f'"beats": {beats[k].rjust(bw)}')
        if vels:
            parts.append(f'"velocity": {vels[k].rjust(vw)}')
        body = ", ".join(parts) + rest_text[k]
        return body, rest_text[k]

    line_start = text.rfind("\n", 0, key_start) + 1
    lead = text[line_start:key_start]
    if lead.strip():                      # key is mid-line (compact JSON)
        rows = ["{ " + row(k)[0] + " }" for k in range(n)]
        return '"events": [ ' + ", ".join(rows) + " ]"
    indent = lead
    rows = []
    for k in range(n):
        body, rt = row(k)
        pad = " " * (rw - len(rt))
        rows.append(f"{indent}  {{ {body}{pad} }}")
    return '"events": [\n' + ",\n".join(rows) + f"\n{indent}]"


def migrate_text(text: str) -> tuple[str, list[str]]:
    """Return (new_text, notes). Idempotent: motifs already on `events` are skipped."""
    notes: list[str] = []
    objs = [o for o in _scan_motifs(text) if "events" not in o["keys"]]
    # Apply from the end of the file backwards so earlier offsets stay valid.
    for obj in sorted(objs, key=lambda o: -o["keys"]["intervals"][0]):
        keys = obj["keys"]
        i_ks, i_vs, i_ve = keys["intervals"]
        intervals = json.loads(text[i_vs:i_ve])
        if not (isinstance(intervals, list) and intervals
                and all(isinstance(s, int) and not isinstance(s, bool) for s in intervals)):
            notes.append("skipped a motif whose intervals is not a non-empty list of whole numbers")
            continue

        def column(name, kind):
            if name not in keys:
                return None, True
            val = json.loads(text[keys[name][1]:keys[name][2]])
            ok = (isinstance(val, list) and len(val) == len(intervals)
                  and all(kind(x) for x in val))
            return val, ok

        num = lambda x: isinstance(x, (int, float)) and not isinstance(x, bool)  # noqa: E731
        rhythm, ok_r = column("rhythm", lambda x: num(x) and x > 0)
        rests, ok_s = column("rests", lambda x: isinstance(x, bool))
        vels, ok_v = column("velocities", num)
        if not (ok_r and ok_s and ok_v):
            notes.append("skipped a motif whose rhythm / rests / velocities do not match "
                         "intervals in length (or hold non-numbers)")
            continue

        edits = [("replace", i_ks, i_ve, _events_text(intervals, rhythm, rests, vels, i_ks, text))]
        for name in ("rhythm", "rests", "velocities"):
            if name in keys:
                edits.append(("delete", keys[name][0], keys[name][2], None))
        for kind, a, b, new in sorted(edits, key=lambda e: -e[1]):
            text = (text[:a] + new + text[b:]) if kind == "replace" else _delete_entry(text, a, b)
    return text, notes


# ── Verification ─────────────────────────────────────────────────────────────

def _equivalent(old, new, path="$") -> str | None:
    """
    Structural comparison. Where `new` has an `events` motif and `old` has the
    legacy motif at the same place, expanding `new` must give exactly `old`.
    Returns None if equivalent, else the path of the first difference.
    """
    if isinstance(old, dict) and isinstance(new, dict):
        if "events" in new and "events" not in old:
            try:
                expanded = normalize_motif_dict(new)
            except ValueError as exc:
                return f"{path}: {exc}"
            return None if expanded == old else f"{path}: expanded events differ from original motif"
        if set(old) != set(new):
            return f"{path}: keys differ ({sorted(set(old) ^ set(new))})"
        for k in old:
            bad = _equivalent(old[k], new[k], f"{path}.{k}")
            if bad:
                return bad
        return None
    if isinstance(old, list) and isinstance(new, list):
        if len(old) != len(new):
            return f"{path}: length {len(old)} vs {len(new)}"
        for i, (a, b) in enumerate(zip(old, new)):
            bad = _equivalent(a, b, f"{path}[{i}]")
            if bad:
                return bad
        return None
    return None if old == new else f"{path}: {old!r} vs {new!r}"


def _expand_deep(obj):
    """Expand every `events` motif in a dump. Motifs that stay raw dicts inside
    the model (bass_motif, voice and harmony_rhythm motifs) still show `events`
    in model_dump(); expanding them lets the two dumps be compared like for like."""
    if isinstance(obj, dict):
        obj = normalize_motif_dict(obj)
        return {k: _expand_deep(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_expand_deep(v) for v in obj]
    return obj


def _model_dump(data: dict) -> dict | None:
    piece = data.get("piece", data)
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            return _expand_deep(PieceModel.model_validate(piece).model_dump())
    except Exception:                      # noqa: BLE001 - not a piece (theme / library motif)
        return None


def verify(old: str, new: str) -> str | None:
    """None if equivalent, else a short reason."""
    try:
        a, b = json.loads(old), json.loads(new)
    except json.JSONDecodeError as exc:
        return f"result is not valid JSON: {exc}"
    bad = _equivalent(a, b)
    if bad:
        return bad
    da, db = _model_dump(a), _model_dump(b)
    if da != db:
        return "validated model differs after migration"
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
        n_old = len([o for o in _scan_motifs(old) if "events" not in o["keys"]])
        label = f"{path.name}: {n_old} motif(s)"
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
            print(f"  ok    {label} — would migrate (verified identical after expansion)")
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
