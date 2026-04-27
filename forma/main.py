#!/usr/bin/env python3
"""
main.py — Intervals Engine

Generate MIDI pieces from theme + piece JSON files.

Usage:
    python main.py theme.json piece.json
    python main.py theme.json piece.json --output ./output/name.mid
    python main.py theme.json piece_01.json piece_02.json --outdir ./album/
    python main.py theme.json piece.json --info
"""

import argparse
import os
import sys
from pathlib import Path
from typing import Optional

from intervals.core.generator import generate_piece, load_theme, load_piece, bpm_to_tempo, PPQ
from intervals.music.motif import from_dict as motif_from_dict
from intervals.music.prosody import phrase_to_motif, analyze_phrase, PRONOUNCING_AVAILABLE
from intervals.music.rhythm import VALID_GROOVES
from intervals.music.percussion import VALID_DRUM_PATTERNS

# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------

VALID_MODES       = ["ionian","dorian","phrygian","lydian","mixolydian","aeolian","locrian"]
VALID_DENSITIES   = ["sparse", "medium", "full"]
VALID_BEHAVIORS   = ["generative", "lyrical", "sparse", "develop"]
VALID_BASS_STYLES = ["root_only", "root_fifth", "walking", "steady", "melodic", "pulse", "pedal"]
VALID_ARCS        = ["flat", "swell", "fade_in", "fade_out", "breath"]


def validate_theme(theme: dict) -> list:
    errors = []
    if "key" not in theme:
        errors.append("theme.key is required")
    if "mode" not in theme:
        errors.append("theme.mode is required")
    elif theme["mode"].lower() not in VALID_MODES:
        errors.append(f"theme.mode '{theme['mode']}' unknown. Valid: {VALID_MODES}")
    if "tempo" not in theme:
        errors.append("theme.tempo is required (object with min/max keys)")
    else:
        t = theme["tempo"]
        if "min" not in t or "max" not in t:
            errors.append("theme.tempo must have 'min' and 'max' keys")
        elif t["min"] > t["max"]:
            errors.append("theme.tempo.min must be <= theme.tempo.max")
    if theme.get("motif") and theme.get("phrase"):
        errors.append(
            "theme has both 'motif' and 'phrase' — explicit motif takes "
            "precedence, phrase will be ignored (proceeding anyway)"
        )
    return errors


def _validate_section(section: dict, prefix: str) -> list:
    """Validate a single section dict. Used for both narrative and song form."""
    errors = []
    if "progression" not in section or not section["progression"]:
        errors.append(f"{prefix}: progression is required")
    if "bars" not in section:
        errors.append(f"{prefix}: bars is required")

    chord_bars = section.get("chord_bars")
    if chord_bars is not None:
        prog = section.get("progression", [])
        if len(chord_bars) != len(prog):
            errors.append(
                f"{prefix}: chord_bars has {len(chord_bars)} entries "
                f"but progression has {len(prog)} chords — must match"
            )
        bars_total = section.get("bars", 0)
        cb_sum = sum(chord_bars)
        if abs(cb_sum - bars_total) > 0.01:
            errors.append(
                f"{prefix}: chord_bars sum ({cb_sum}) does not match "
                f"bars ({bars_total}) (proceeding anyway)"
            )

    if section.get("density") and section["density"] not in VALID_DENSITIES:
        errors.append(f"{prefix}: density '{section['density']}' invalid. Valid: {VALID_DENSITIES}")
    if section.get("melody") and section["melody"] not in VALID_BEHAVIORS:
        errors.append(f"{prefix}: melody behavior '{section['melody']}' invalid. Valid: {VALID_BEHAVIORS}")
    if section.get("bass_style") and section["bass_style"] not in VALID_BASS_STYLES:
        errors.append(f"{prefix}: bass_style '{section['bass_style']}' invalid. Valid: {VALID_BASS_STYLES}")
    if section.get("arc") and section["arc"] not in VALID_ARCS:
        errors.append(f"{prefix}: arc '{section['arc']}' invalid. Valid: {VALID_ARCS}")
    if section.get("groove") and section["groove"] not in VALID_GROOVES:
        errors.append(f"{prefix}: groove '{section['groove']}' invalid. Valid: {VALID_GROOVES}")

    swing = section.get("swing")
    if swing is not None and not (0.0 <= swing <= 0.75):
        errors.append(f"{prefix}: swing {swing} out of range. Valid: 0.0–0.75")

    hr = section.get("harmony_rhythm")
    if hr and isinstance(hr, dict):
        hp = f"{prefix}.harmony_rhythm"
        if hr.get("density") and hr["density"] not in VALID_DENSITIES:
            errors.append(f"{hp}: density '{hr['density']}' invalid. Valid: {VALID_DENSITIES}")
        if hr.get("groove") and hr["groove"] not in VALID_GROOVES:
            errors.append(f"{hp}: groove '{hr['groove']}' invalid. Valid: {VALID_GROOVES}")
        hr_swing = hr.get("swing")
        if hr_swing is not None and not (0.0 <= hr_swing <= 0.75):
            errors.append(f"{hp}: swing {hr_swing} out of range. Valid: 0.0–0.75")
        if hr.get("note_duration"):
            valid_durations = ["whole", "half", "quarter", "eighth"]
            if hr["note_duration"] not in valid_durations:
                errors.append(f"{hp}: note_duration '{hr['note_duration']}' invalid. Valid: {valid_durations}")

    # Drum validation
    drums_config = section.get("drums")
    if drums_config:
        if isinstance(drums_config, str):
            pattern = drums_config
        else:
            pattern = drums_config.get("pattern") if isinstance(drums_config, dict) else None

        if pattern and pattern not in VALID_DRUM_PATTERNS:
            errors.append(
                f"{prefix}: drum pattern '{pattern}' invalid. "
                f"Valid: {VALID_DRUM_PATTERNS}"
            )

        if isinstance(drums_config, dict):
            velocity = drums_config.get("velocity")
            if velocity is not None and not (0 <= velocity <= 127):
                errors.append(
                    f"{prefix}: drums velocity {velocity} out of range. Valid: 0–127"
                )

    return errors


def validate_piece(piece: dict, theme: dict) -> list:
    errors = []

    # Determine form type (song or narrative)
    form_type = piece.get("form_type", "narrative")

    if form_type == "song":
        # Song form mode
        if "form" not in piece or not piece["form"]:
            errors.append("piece.form is required for song form")
            return errors
        if "sections" not in piece or not piece["sections"]:
            errors.append("piece.sections dict is required for song form")
            return errors

        # Validate form array references
        sections_dict = piece["sections"]
        for form_item in piece["form"]:
            if isinstance(form_item, dict):
                section_name = form_item.get("section")
                variation = form_item.get("variation", 0.0)
                if not (0.0 <= variation <= 1.0):
                    errors.append(f"form item section '{section_name}': variation {variation} out of range. Valid: 0.0–1.0")
            else:
                section_name = form_item

            if section_name not in sections_dict:
                errors.append(f"form references undefined section: '{section_name}'")

        # Validate each section definition in the dict
        for section_name, section in sections_dict.items():
            prefix = f"sections['{section_name}']"
            section_errors = _validate_section(section, prefix)
            errors.extend(section_errors)
    else:
        # Narrative mode
        if "sections" not in piece or not piece["sections"]:
            errors.append("piece.sections is required and must be non-empty")
            return errors

        # Validate each section in the list
        for i, section in enumerate(piece["sections"]):
            prefix = f"sections[{i}] '{section.get('name', '?')}'"
            section_errors = _validate_section(section, prefix)
            errors.extend(section_errors)

    # Check tempo range
    tempo = piece.get("tempo")
    if tempo is not None:
        t = theme.get("tempo", {})
        if t.get("min") and t.get("max"):
            if not (t["min"] <= tempo <= t["max"]):
                errors.append(
                    f"piece.tempo {tempo} is outside theme range "
                    f"{t['min']}–{t['max']} BPM (proceeding anyway)"
                )

    return errors


# ---------------------------------------------------------------------------
# Info display
# ---------------------------------------------------------------------------

def display_info(theme: dict, piece: dict) -> None:
    tempo_range = theme.get("tempo", {})
    bpm = piece.get("tempo", (tempo_range.get("min", 60) + tempo_range.get("max", 80)) // 2)
    beats_per_bar = 4

    print(f"\n{'─'*56}")
    print(f"  THEME:  {theme.get('name', '(unnamed)')}")
    print(f"  Key:    {theme.get('key', '?')} {theme.get('mode', '?')}")
    print(f"  Tempo:  {tempo_range.get('min')}–{tempo_range.get('max')} BPM")

    motif_def = theme.get("motif")
    if motif_def:
        m = motif_from_dict(motif_def)
        print(f"  Motif:  intervals={m.intervals}  rhythm={m.rhythm}")
        print(f"          contour={''.join(m.contour())}  transforms={m.transform_pool}")

    phrase = theme.get("phrase")
    if phrase:
        analysis = analyze_phrase(phrase)
        print(f"  Phrase:  \"{phrase}\"  (prosody → motif)")
        print(f"           stress={analysis.stress_pattern}  "
              f"syllables={len(analysis.syllables)}  "
              f"CMU={'yes' if PRONOUNCING_AVAILABLE else 'fallback'}")
        if motif_def:
            print(f"           (explicit motif takes precedence over phrase)")

    palette = theme.get("palette", {})
    if palette:
        print(f"  Palette: harmony={palette.get('harmony')}  "
              f"melody={palette.get('melody')}  bass={palette.get('bass')}")

    print(f"\n  PIECE:  {piece.get('title', '(untitled)')}")
    print(f"  Tempo:  {bpm} BPM")

    form_type = piece.get("form_type", "narrative")
    if form_type == "song":
        print(f"  Form:   song")
        print(f"  Form array:")
        for form_item in piece.get("form", []):
            if isinstance(form_item, dict):
                section_name = form_item.get("section", "?")
                variation = form_item.get("variation", 0.0)
                print(f"    - {section_name} (variation={variation})")
            else:
                print(f"    - {form_item}")
        print(f"  Section definitions:")
        sections_to_display = piece.get("sections", {}).values()
    else:
        print(f"  Sections:")
        sections_to_display = piece.get("sections", [])

    total_bars = 0
    for s in sections_to_display:
        bars = s.get("bars", 0)
        total_bars += bars
        prog = " → ".join(s.get("progression", []))
        chord_bars = s.get("chord_bars")
        if chord_bars:
            # Show progression with per-chord bars: I(4) → V(2) → vi(2) → IV(4)
            prog_parts = s.get("progression", [])
            prog = " → ".join(f"{c}({int(b) if b == int(b) else b})"
                               for c, b in zip(prog_parts, chord_bars))
        groove_info = ""
        if s.get("groove"):
            parts = [s["groove"]]
            if s.get("swing"):
                parts.append(f"swing={s['swing']}")
            groove_info = f"  groove={','.join(parts)}"
        print(f"    [{s.get('name', '?'):12s}]  {bars:2d} bars  "
              f"{s.get('density','?'):6s}  {s.get('melody','?'):11s}  "
              f"bass={s.get('bass_style','?')}{groove_info}  [{prog}]")
        hr = s.get("harmony_rhythm")
        if hr:
            hr_parts = []
            if hr.get("density"):
                hr_parts.append(f"density={hr['density']}")
            if hr.get("groove"):
                hr_parts.append(f"groove={hr['groove']}")
            if hr.get("swing"):
                hr_parts.append(f"swing={hr['swing']}")
            if hr.get("note_duration"):
                hr_parts.append(f"note_duration={hr['note_duration']}")
            if hr_parts:
                print(f"      harmony_rhythm: {', '.join(hr_parts)}")

        drums_config = s.get("drums")
        if drums_config:
            if isinstance(drums_config, str):
                drums_info = f"drums={drums_config}"
            else:
                pattern = drums_config.get("pattern", "four_on_floor")
                velocity = drums_config.get("velocity", 80)
                drums_info = f"drums={pattern} (velocity={velocity})"
            print(f"      {drums_info}")

    total_beats   = total_bars * beats_per_bar
    total_seconds = total_beats * (60.0 / bpm)
    mins, secs = divmod(int(total_seconds), 60)
    print(f"\n  Total:  {total_bars} bars / {total_beats} beats / {mins}m {secs:02d}s at {bpm} BPM")
    print(f"{'─'*56}\n")


# ---------------------------------------------------------------------------
# Single piece generation
# ---------------------------------------------------------------------------

def run_single(theme_path: str, piece_path: str, output_path: Optional[str], info_only: bool) -> bool:
    try:
        theme = load_theme(theme_path)
    except Exception as e:
        print(f"  ERROR loading theme '{theme_path}': {e}", file=sys.stderr)
        return False

    try:
        piece = load_piece(piece_path)
    except Exception as e:
        print(f"  ERROR loading piece '{piece_path}': {e}", file=sys.stderr)
        return False

    theme_errors = validate_theme(theme)
    piece_errors = validate_piece(piece, theme)
    all_errors   = theme_errors + piece_errors

    warnings    = [e for e in all_errors if "proceeding anyway" in e]
    hard_errors = [e for e in all_errors if "proceeding anyway" not in e]

    for w in warnings:
        print(f"  WARNING: {w}")

    if hard_errors:
        print(f"  ERRORS in '{piece_path}':")
        for e in hard_errors:
            print(f"    • {e}")
        return False

    if info_only:
        display_info(theme, piece)
        return True

    if output_path is None:
        stem = Path(piece_path).stem
        output_path = os.path.join("output", f"{stem}.mid")

    os.makedirs(os.path.dirname(output_path) or "output", exist_ok=True)

    try:
        result = generate_piece(theme, piece, output_path)
        import mido
        mid = mido.MidiFile(result)
        total_ticks = max(sum(m.time for m in track) for track in mid.tracks)
        bpm = piece.get("tempo", (theme["tempo"]["min"] + theme["tempo"]["max"]) // 2)
        total_seconds = mido.tick2second(total_ticks, PPQ, bpm_to_tempo(bpm))
        mins, secs = divmod(int(total_seconds), 60)
        size_kb = os.path.getsize(result) / 1024
        print(f"  ✓  {piece.get('title', Path(piece_path).stem):30s}  "
              f"{mins}m {secs:02d}s  {size_kb:.1f} KB  →  {result}")
        return True
    except Exception as e:
        print(f"  ERROR generating '{piece_path}': {e}", file=sys.stderr)
        import traceback
        traceback.print_exc()
        return False


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        prog="intervals",
        description="Intervals Engine — generate MIDI from theme + piece JSON.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
examples:
  python main.py theme.json piece.json
  python main.py theme.json piece.json --output ./output/name.mid
  python main.py theme.json p1.json p2.json --outdir ./album/
  python main.py theme.json piece.json --info
        """,
    )

    parser.add_argument("theme",  help="Path to theme.json")
    parser.add_argument("pieces", nargs="+", help="One or more piece JSON files")
    parser.add_argument("--output", "-o", default=None,
                        help="Output .mid path (single piece only)")
    parser.add_argument("--outdir", "-d", default=None,
                        help="Output directory for batch generation")
    parser.add_argument("--info", "-i", action="store_true",
                        help="Display piece info without generating")

    args = parser.parse_args()

    if not os.path.exists(args.theme):
        print(f"ERROR: theme file not found: '{args.theme}'", file=sys.stderr)
        sys.exit(1)

    missing = [p for p in args.pieces if not os.path.exists(p)]
    if missing:
        for m in missing:
            print(f"ERROR: piece file not found: '{m}'", file=sys.stderr)
        sys.exit(1)

    if args.output and len(args.pieces) > 1:
        print("ERROR: --output only works with a single piece. Use --outdir for batch.",
              file=sys.stderr)
        sys.exit(1)

    if args.outdir:
        os.makedirs(args.outdir, exist_ok=True)

    print(f"\nIntervals Engine")
    print(f"Theme: {args.theme}")
    print(f"Mode:  {'info' if args.info else 'generate'}")
    print()

    success = failure = 0

    for piece_path in args.pieces:
        if args.info:
            out = None
        elif args.output:
            out = args.output
        elif args.outdir:
            out = str(Path(args.outdir) / f"{Path(piece_path).stem}.mid")
        else:
            out = None

        ok = run_single(args.theme, piece_path, out, args.info)
        if ok:
            success += 1
        else:
            failure += 1

    print()
    if len(args.pieces) > 1:
        print(f"Done: {success} succeeded, {failure} failed.")
    elif failure:
        sys.exit(1)


if __name__ == "__main__":
    main()
