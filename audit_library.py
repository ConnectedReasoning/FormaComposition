#!/usr/bin/env python3
"""
audit_library.py — FormaComposition JSON Library Auditor

Recursively walks a directory, validates every theme.json and piece.json
(or all .json files) against ThemeModel / PieceModel from intervals.core.schemas,
and prints a structured report.

Usage:
    python audit_library.py ./compositions
    python audit_library.py ./compositions --all-json
    python audit_library.py ./compositions --strict
    python audit_library.py ./compositions --output report.txt
"""

from __future__ import annotations

import argparse
import json
import sys
import os
import textwrap
from pathlib import Path
from typing import Optional
from dataclasses import dataclass, field

# ── Path bootstrap ────────────────────────────────────────────────────────────
# Ensure the project root (directory containing this script) is on sys.path so
# `intervals` is importable whether the script runs from the project root, a
# subdirectory, or via an absolute path. Runs before any intervals import.
_SCRIPT_DIR = Path(__file__).resolve().parent
if str(_SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPT_DIR))

# ── Schema imports — fail fast with a clear message if not found ──────────────
try:
    from pydantic import ValidationError as _ValidationError
    from intervals.core.schemas import ThemeModel as _ThemeModel
    from intervals.core.schemas import PieceModel as _PieceModel
except ModuleNotFoundError as _exc:
    print(
        f"\nError: cannot import FormaComposition modules ({_exc}).\n"
        f"Run this script from the project root, or ensure the project root\n"
        f"is on PYTHONPATH:\n\n"
        f"    cd /path/to/FormaComposition\n"
        f"    python audit_library.py ./compositions --all-json\n",
        file=sys.stderr,
    )
    sys.exit(2)

# ── Colour helpers (graceful no-op on Windows / when piped) ──────────────────

_USE_COLOUR = sys.stdout.isatty() and os.name != "nt"

def _c(code: str, text: str) -> str:
    return f"\033[{code}m{text}\033[0m" if _USE_COLOUR else text

OK    = lambda s: _c("32", s)   # green
WARN  = lambda s: _c("33", s)   # yellow
ERR   = lambda s: _c("31", s)   # red
BOLD  = lambda s: _c("1",  s)   # bold
DIM   = lambda s: _c("2",  s)   # grey


# ── Result types ─────────────────────────────────────────────────────────────

@dataclass
class FileResult:
    path: Path
    model_type: str           # "theme" | "piece" | "unknown"
    status: str               # "ok" | "warn" | "error" | "json_error" | "skip"
    errors: list[str]         = field(default_factory=list)
    warnings: list[str]       = field(default_factory=list)
    extra_keys: dict[str, list[str]] = field(default_factory=dict)
    # extra_keys: {"<context_path>": [key1, key2, ...]}


# ── Extra-key detection ───────────────────────────────────────────────────────

def _collect_extra_keys(model_instance, path_prefix: str = "") -> dict[str, list[str]]:
    """
    Walk a Pydantic model instance and collect all extra fields.
    Returns a dict mapping dotted-path → [key, ...].

    For models with extra="allow" (ThemeModel, SectionModel, MotifModel,
    PieceModel) Pydantic stores extras in model_extra. For extra="forbid"
    models, extras cause a ValidationError before we get here.
    """
    result: dict[str, list[str]] = {}

    extras = getattr(model_instance, "model_extra", None) or {}
    if extras:
        result[path_prefix or "(root)"] = sorted(extras.keys())

    # Recurse into sub-model fields
    for fname, fval in model_instance.__dict__.items():
        if fname.startswith("_") or fname == "model_extra":
            continue
        child_path = f"{path_prefix}.{fname}" if path_prefix else fname
        if hasattr(fval, "model_extra"):          # single sub-model
            sub = _collect_extra_keys(fval, child_path)
            result.update(sub)
        elif isinstance(fval, list):
            for idx, item in enumerate(fval):
                if hasattr(item, "model_extra"):
                    sub = _collect_extra_keys(item, f"{child_path}[{idx}]")
                    result.update(sub)
        elif isinstance(fval, dict):
            for k, item in fval.items():
                if hasattr(item, "model_extra"):
                    sub = _collect_extra_keys(item, f"{child_path}.{k}")
                    result.update(sub)

    return result


# ── Model detection ───────────────────────────────────────────────────────────

def _detect_model_type(filename: str, data: dict) -> str:
    """
    Determine whether a JSON file is a theme or piece.

    Priority order:
      1. Filename contains 'theme' → theme
      2. Filename contains 'piece' → piece
      3. Content sniff: key/mode/tempo dict → theme; sections/form_type → piece
      4. Fallback: assume piece (the more common type in a compositions dir)
    """
    name = filename.lower()
    if "theme" in name:
        return "theme"
    if "piece" in name:
        return "piece"
    # Content sniff — discriminating keys
    if "key" in data and "mode" in data and "tempo" in data and isinstance(data.get("tempo"), dict):
        return "theme"
    if "sections" in data or "form_type" in data or "form" in data:
        return "piece"
    # Fallback: treat as piece — most composition files are pieces.
    # The validator will produce a clear error if that assumption is wrong.
    return "piece"


# ── Single-file validation ────────────────────────────────────────────────────

def _validate_file(
    path: Path,
    strict: bool = False,
) -> FileResult:
    """Load and validate one JSON file. Returns a FileResult."""

    # ── JSON parse ────────────────────────────────────────────────────────
    try:
        raw = path.read_text(encoding="utf-8")
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        return FileResult(
            path=path,
            model_type="unknown",
            status="json_error",
            errors=[f"Invalid JSON: {exc}"],
        )
    except OSError as exc:
        return FileResult(
            path=path,
            model_type="unknown",
            status="json_error",
            errors=[f"Could not read file: {exc}"],
        )

    if not isinstance(data, dict):
        return FileResult(
            path=path,
            model_type="unknown",
            status="json_error",
            errors=["File root must be a JSON object ({}), not a list or scalar."],
        )

    # ── Model detection ───────────────────────────────────────────────────
    model_type = _detect_model_type(path.name, data)

    # ── Pydantic validation ───────────────────────────────────────────────
    import warnings as _warnings_mod

    Model = _ThemeModel if model_type == "theme" else _PieceModel

    captured_warnings: list[str] = []

    def _warning_handler(message, category, filename, lineno, file=None, line=None):
        captured_warnings.append(str(message))

    old_handler = _warnings_mod.showwarning
    _warnings_mod.showwarning = _warning_handler
    _warnings_mod.simplefilter("always")

    try:
        instance = Model.model_validate(data)
        _warnings_mod.showwarning = old_handler
    except _ValidationError as exc:
        _warnings_mod.showwarning = old_handler
        errors = []
        for e in exc.errors():
            loc = " → ".join(str(p) for p in e["loc"]) if e["loc"] else "(root)"
            msg = e["msg"]
            val = e.get("input", "")
            # Trim long values
            val_str = repr(val) if not isinstance(val, (dict, list)) else f"<{type(val).__name__}>"
            errors.append(f"{loc}: {msg}  (got {val_str})")
        return FileResult(
            path=path,
            model_type=model_type,
            status="error",
            errors=errors,
            warnings=captured_warnings,
        )

    # ── Extra-key collection ──────────────────────────────────────────────
    extra_keys = _collect_extra_keys(instance)
    # Filter out internal pydantic noise
    extra_keys = {k: v for k, v in extra_keys.items() if v}

    status = "ok"
    if captured_warnings:
        status = "warn"
    if strict and extra_keys:
        status = "warn"

    return FileResult(
        path=path,
        model_type=model_type,
        status=status,
        warnings=captured_warnings,
        extra_keys=extra_keys,
    )


# ── Directory walk ────────────────────────────────────────────────────────────

def _find_json_files(root: Path, all_json: bool) -> list[Path]:
    """
    Walk root recursively.
    - all_json=False: return only theme.json and piece.json files.
    - all_json=True:  return all *.json files.
    Skip __pycache__, .git, node_modules directories.
    """
    skip_dirs = {"__pycache__", ".git", "node_modules", ".venv", "venv"}
    found = []
    for dirpath, dirnames, filenames in os.walk(root):
        # Prune skip dirs in-place so os.walk doesn't descend into them
        dirnames[:] = [d for d in dirnames if d not in skip_dirs]
        for fname in sorted(filenames):
            if not fname.endswith(".json"):
                continue
            if all_json or fname in ("theme.json", "piece.json"):
                found.append(Path(dirpath) / fname)
    return found


# ── Report rendering ──────────────────────────────────────────────────────────

def _render_result(result: FileResult, root: Path, verbose: bool) -> list[str]:
    lines = []
    rel = result.path.relative_to(root) if result.path.is_relative_to(root) else result.path

    # ── Status badge ──────────────────────────────────────────────────────
    if result.status == "ok":
        badge = OK("  ✔ PASS  ")
    elif result.status == "warn":
        badge = WARN("  ⚠ WARN  ")
    elif result.status == "skip":
        badge = DIM("  ─ SKIP  ")
    else:
        badge = ERR("  ✖ FAIL  ")

    type_tag = DIM(f"[{result.model_type}]") if result.model_type != "unknown" else DIM("[?]")
    lines.append(f"{badge} {type_tag}  {rel}")

    # ── Errors ────────────────────────────────────────────────────────────
    for err in result.errors:
        wrapped = textwrap.fill(err, width=90, initial_indent="         ✖ ", subsequent_indent="           ")
        lines.append(ERR(wrapped))

    # ── Warnings ─────────────────────────────────────────────────────────
    for w in result.warnings:
        wrapped = textwrap.fill(w, width=90, initial_indent="         ⚠ ", subsequent_indent="           ")
        lines.append(WARN(wrapped))

    # ── Extra keys ───────────────────────────────────────────────────────
    if result.extra_keys:
        lines.append(WARN("         ⊕ Extra keys detected (not in schema):"))
        for ctx, keys in result.extra_keys.items():
            keys_str = ", ".join(f'"{k}"' for k in keys)
            lines.append(WARN(f"           {ctx}: {keys_str}"))

    return lines


def _render_summary(results: list[FileResult]) -> list[str]:
    total  = len(results)
    ok     = sum(1 for r in results if r.status == "ok")
    warn   = sum(1 for r in results if r.status == "warn")
    fail   = sum(1 for r in results if r.status in ("error", "json_error"))
    extras = sum(1 for r in results if r.extra_keys)

    lines = [
        "",
        BOLD("─" * 60),
        BOLD("  Audit Summary"),
        BOLD("─" * 60),
        f"  Files processed : {total}",
        OK( f"  Passed          : {ok}"),
        WARN(f"  Warnings        : {warn}"),
        ERR( f"  Failed          : {fail}"),
        WARN(f"  Files with extra keys: {extras}"),
        BOLD("─" * 60),
    ]

    if fail == 0 and warn == 0:
        lines.append(OK("  All files are schema-compliant. ✔"))
    elif fail > 0:
        lines.append(ERR(f"  {fail} file(s) require attention."))

    # Collect a deduplicated list of all extra key paths
    all_extras: dict[str, set[str]] = {}
    for r in results:
        for ctx, keys in r.extra_keys.items():
            for k in keys:
                all_extras.setdefault(k, set()).add(ctx)

    if all_extras:
        lines.append("")
        lines.append(BOLD("  All distinct extra keys found across library:"))
        for k in sorted(all_extras):
            paths = sorted(all_extras[k])
            locations = ", ".join(paths[:3])
            if len(paths) > 3:
                locations += f" (+{len(paths)-3} more)"
            lines.append(WARN(f"    \"{k}\"  — seen in: {locations}"))

    lines.append(BOLD("─" * 60))
    return lines


# ── Main ──────────────────────────────────────────────────────────────────────

def main() -> int:
    parser = argparse.ArgumentParser(
        description="Audit a FormaComposition JSON library against Pydantic schemas.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=textwrap.dedent("""\
            Examples:
              python audit_library.py ./compositions
              python audit_library.py ./compositions --all-json
              python audit_library.py ./compositions --strict --output report.txt
              python audit_library.py ./compositions --fail-only
        """),
    )
    parser.add_argument(
        "directory",
        type=Path,
        help="Root directory to search for JSON files.",
    )
    parser.add_argument(
        "--all-json",
        action="store_true",
        help="Validate ALL .json files, not just theme.json and piece.json.",
    )
    parser.add_argument(
        "--strict",
        action="store_true",
        help="Treat extra keys as warnings (upgrade files with extras to 'warn' status).",
    )
    parser.add_argument(
        "--fail-only",
        action="store_true",
        help="Only print files that failed or warned; suppress passing files.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=None,
        help="Write the report to a file in addition to stdout.",
    )
    args = parser.parse_args()

    root = args.directory.resolve()
    if not root.is_dir():
        print(ERR(f"Error: '{root}' is not a directory."), file=sys.stderr)
        return 2

    # ── Discover files ────────────────────────────────────────────────────
    files = _find_json_files(root, args.all_json)
    if not files:
        print(WARN(f"No JSON files found under '{root}'."))
        return 0

    print(BOLD(f"\n  FormaComposition Library Audit"))
    print(DIM(f"  Directory : {root}"))
    print(DIM(f"  Files found: {len(files)}"))
    print(DIM(f"  Mode      : {'all .json' if args.all_json else 'theme.json / piece.json only'}"))
    print(DIM(f"  Strict    : {args.strict}"))
    print(BOLD("─" * 60))

    # ── Validate each file ────────────────────────────────────────────────
    results: list[FileResult] = []
    all_output_lines: list[str] = []

    for fpath in files:
        result = _validate_file(fpath, strict=args.strict)
        results.append(result)

        is_interesting = result.status in ("error", "json_error", "warn") or result.extra_keys
        if args.fail_only and not is_interesting:
            continue

        lines = _render_result(result, root, verbose=True)
        for line in lines:
            print(line)
        all_output_lines.extend(lines)

    # ── Summary ───────────────────────────────────────────────────────────
    summary_lines = _render_summary(results)
    for line in summary_lines:
        print(line)
    all_output_lines.extend(summary_lines)

    # ── Optional file output (strip ANSI codes) ───────────────────────────
    if args.output:
        import re
        ansi_escape = re.compile(r"\033\[[0-9;]*m")
        clean_lines = [ansi_escape.sub("", l) for l in all_output_lines]
        args.output.write_text("\n".join(clean_lines) + "\n", encoding="utf-8")
        print(DIM(f"\n  Report written to: {args.output}"))

    # Return exit code: 0 = all pass, 1 = some failures
    any_fail = any(r.status in ("error", "json_error") for r in results)
    return 1 if any_fail else 0


if __name__ == "__main__":
    sys.exit(main())
