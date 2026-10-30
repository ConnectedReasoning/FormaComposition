#!/usr/bin/env python3
"""
migrate_to_song.py — convert legacy narrative pieces to song form.

The narrative form (``"sections": [ {...}, {...} ]``, played once in order)
has been removed; song form is the only supported form. This rewrites a
piece file so that:

  * ``"form_type": "song"`` is set (replacing ``"narrative"`` if present),
  * ``"form"`` lists the section names in play order, and
  * ``"sections"`` becomes a name-keyed dict.

Each section is played once, in its original order, so the rendered MIDI is
unchanged. Section keys are taken from each section's ``name`` (or
``section_<index>`` when unnamed). Sections that share a name AND have
identical content are collapsed into one definition that appears twice in
``form`` (a true repeat); same-named sections with different content get a
numeric suffix on the key (``name_2``) and keep their ``name`` field.

The file's original formatting (indentation, aligned arrays) is preserved:
only the ``sections`` container and the new ``form_type``/``form`` lines are
rewritten, and each section's own text is moved over unchanged.

Usage:
    python migrate_to_song.py piece.json [piece2.json ...]
    python migrate_to_song.py pieces/*.json --dry-run
    python migrate_to_song.py pieces/*.json --outdir converted/
    python migrate_to_song.py piece.json --no-backup

Files that are already song form are skipped. In-place conversions keep a
``.json.bak`` copy unless ``--no-backup`` is given.
"""
import argparse
import json
import re
import shutil
import sys
from pathlib import Path


def _piece_depth(root) -> int:
    """Container depth of the piece-level keys: 2 if wrapped in {"piece": ...}."""
    return 2 if isinstance(root, dict) and isinstance(root.get("piece"), dict) else 1


def _find_sections_list(text: str, piece_depth: int) -> tuple[int, int]:
    """Return (key_start, array_open) for the piece-level ``"sections": [``."""
    depth, i, n = 0, 0, len(text)
    in_str = False
    while i < n:
        c = text[i]
        if in_str:
            if c == "\\":
                i += 2
                continue
            if c == '"':
                in_str = False
            i += 1
            continue
        if c == '"':
            j = i + 1
            while text[j] != '"':
                j += 2 if text[j] == "\\" else 1
            k = j + 1
            while k < n and text[k] in " \t\r\n":
                k += 1
            if depth == piece_depth and text[i + 1:j] == "sections" and k < n and text[k] == ":":
                k += 1
                while text[k] in " \t\r\n":
                    k += 1
                if text[k] == "[":
                    return i, k
            i = j + 1
            continue
        if c in "{[":
            depth += 1
        elif c in "}]":
            depth -= 1
        i += 1
    raise ValueError("no piece-level \"sections\" list found")


def _element_spans(text: str, arr_open: int) -> tuple[list[tuple[int, int]], int]:
    """Spans of each ``{...}`` element of the array at ``arr_open``, and the
    index of its closing ``]``."""
    spans, depth, in_str, start = [], 0, False, None
    i, n = arr_open, len(text)
    while i < n:
        c = text[i]
        if in_str:
            if c == "\\":
                i += 2
                continue
            if c == '"':
                in_str = False
            i += 1
            continue
        if c == '"':
            in_str = True
        elif c in "{[":
            depth += 1
            if depth == 2 and c == "{":
                start = i
        elif c in "}]":
            if depth == 2 and c == "}":
                spans.append((start, i + 1))
            depth -= 1
            if depth == 0:
                return spans, i
        i += 1
    raise ValueError("unterminated sections list")


def convert_text(text: str) -> tuple[str, list[str]]:
    """Convert one piece's JSON text. Returns (new_text, form).

    Raises ValueError if the piece is not a narrative piece.
    """
    root = json.loads(text)
    piece = root["piece"] if isinstance(root.get("piece"), dict) else root
    secs = piece.get("sections")
    if not isinstance(secs, list) or piece.get("form_type") not in (None, "narrative"):
        raise ValueError("not a narrative piece (already song form?)")

    defs: dict[str, dict] = {}
    form: list[str] = []
    keys: list = []
    for idx, sec in enumerate(secs):
        base = sec.get("name") or f"section_{idx}"
        if base in defs and json.dumps(defs[base], sort_keys=True) == json.dumps(sec, sort_keys=True):
            form.append(base)
            keys.append(None)          # identical repeat: reuse the definition
            continue
        key, n = base, 2
        while key in defs:
            key, n = f"{base}_{n}", n + 1
        defs[key] = sec
        form.append(key)
        keys.append(key)

    key_start, arr_open = _find_sections_list(text, _piece_depth(root))
    spans, close = _element_spans(text, arr_open)
    if len(spans) != len(secs):
        raise ValueError("could not locate every section in the file text")

    line_start = text.rfind("\n", 0, key_start) + 1
    indent = re.match(r"[ \t]*", text[line_start:key_start]).group()

    body = ""
    kept = [(a, b, k) for (a, b), k in zip(spans, keys) if k is not None]
    for n_, (a, b, k) in enumerate(kept):
        before = text[text.rfind("\n", 0, a) + 1:a]
        # Indent like the original when the element starts its own line; when
        # elements share a line (e.g. "[{...}, {...}]") start a fresh indented one.
        lead = before if not before.strip() else indent + "  "
        body += ("\n" if n_ == 0 else ",\n") + lead + json.dumps(k) + ": " + text[a:b]
    new_sections = '"sections": {' + body + "\n" + indent + "}"

    items = [json.dumps(k) for k in form]
    one_line = "[" + ", ".join(items) + "]"
    if len(one_line) + len(indent) + 10 <= 110:
        form_txt = f'"form": {one_line}'
    else:
        rows = [", ".join(items[i:i + 4]) for i in range(0, len(items), 4)]
        form_txt = '"form": [\n' + ",\n".join(indent + "  " + r for r in rows) + "\n" + indent + "]"

    head, tail = text[:key_start], text[close + 1:]
    narrative = re.compile(r'"form_type"\s*:\s*"narrative"')
    if narrative.search(head + tail):
        head = narrative.sub('"form_type": "song"', head)
        tail = narrative.sub('"form_type": "song"', tail)
        inject = form_txt + ",\n" + indent
    else:
        inject = '"form_type": "song",\n' + indent + form_txt + ",\n" + indent
    new = head + inject + new_sections + tail

    # Verify: the result parses, is song form, and each form entry resolves to
    # the same section content the original had at that position.
    out_root = json.loads(new)
    out = out_root["piece"] if isinstance(out_root.get("piece"), dict) else out_root
    assert out["form_type"] == "song" and out["form"] == form
    assert [out["sections"][k] for k in form] == secs
    return new, form


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("pieces", nargs="+", type=Path)
    ap.add_argument("--dry-run", action="store_true", help="report only; write nothing")
    ap.add_argument("--outdir", type=Path, help="write converted copies here instead of in place")
    ap.add_argument("--no-backup", action="store_true",
                    help="skip the .json.bak copy when converting in place")
    args = ap.parse_args(argv)

    if args.outdir and not args.dry_run:
        args.outdir.mkdir(parents=True, exist_ok=True)

    converted = skipped = failed = 0
    for path in args.pieces:
        try:
            new, form = convert_text(path.read_text())
        except json.JSONDecodeError as e:           # a ValueError subclass: check first
            failed += 1
            print(f"  FAIL   {path}: invalid JSON ({e})", file=sys.stderr)
            continue
        except ValueError as e:
            skipped += 1
            print(f"  skip   {path}: {e}")
            continue
        except Exception as e:
            failed += 1
            print(f"  FAIL   {path}: {e}", file=sys.stderr)
            continue
        converted += 1
        distinct = len(set(form))
        print(f"  {'would convert' if args.dry_run else 'convert'}  {path}: "
              f"{len(form)} sections in form, {distinct} definitions")
        if args.dry_run:
            continue
        if args.outdir:
            (args.outdir / path.name).write_text(new)
        else:
            if not args.no_backup:
                shutil.copy2(path, path.with_suffix(path.suffix + ".bak"))
            path.write_text(new)
    print(f"\n{converted} converted, {skipped} skipped, {failed} failed")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
