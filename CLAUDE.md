# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Commands

All commands run from the project root with `.venv` active (`source .venv/bin/activate`).

**Generate a MIDI piece:**
```bash
python forma/main.py themes/theme_evening_water.json compositions/piece_still_cove.json
```

**Preview without generating (--info):**
```bash
python forma/main.py themes/theme_evening_water.json compositions/piece_still_cove.json --info
```

**Specify output path:**
```bash
python forma/main.py themes/theme.json compositions/piece.json --output output/name.mid
```

**Batch generation into a directory:**
```bash
python forma/main.py themes/theme.json compositions/p1.json compositions/p2.json --outdir ./output/
```

**Extract a rhythm pattern from a MIDI file (to paste into JSON):**
```bash
python forma/rhythm_extract.py groove.mid --beats 4
```

**Validate a library of JSON files:**
```bash
PYTHONPATH=forma python audit_library.py ./compositions
```

## Architecture

The engine lives entirely inside `forma/`. Python adds `forma/` to `sys.path` when you run `python forma/main.py`, making `intervals` importable.

```
forma/
  main.py               CLI — argument parsing, calls generate_piece()
  rhythm_extract.py     Extract rhythm patterns from MIDI into JSON blocks
  intervals/
    music/              Voice generators — each returns typed note objects
      harmony.py        Roman numeral → VoicedChord (all modes + extensions to 11th)
      bass.py           Five styles: root_only, root_fifth, walking, pulse, pedal
      melody.py         Behaviors: generative, lyrical, sparse, develop, motif, rhythmic
      motif.py          Bach-style transforms: inversion, retrograde, augmentation, etc.
      counterpoint.py   First/free species; 1–3 independent voices per section
      rhythm.py         Density → RhythmEvent lists, swing, groove patterns
      percussion.py     Drum patterns mapped to GM note numbers (ch 9)
    core/
      generator.py      Orchestrates all voices; writes multi-track MIDI via mido
      schemas.py        Pydantic v2 models — single source of truth for all validation
      context.py        PieceContext + SectionContext — cross-section / cross-voice memory
      strategies.py     Strategy classes for rhythm, melody, and harmony dispatch
      strategies_typed.py  Factory functions that build context objects from Pydantic models
      motif_loader.py   Resolves theme.motif / theme.motifs into a pool for generation
      musical_time.py   Bar/beat helpers
```

### Data flow

`generate_piece()` in `generator.py` is the main entry point. For each section it:
1. Calls `generate_section()` → returns a `SectionResult` dataclass
2. Inside `generate_section()`, voices are generated in order: **bass → melody → counterpoint** (each writes a `VoiceSnapshot` to `SectionContext` so later voices can read it)
3. Harmony events are dispatched via `HarmonyStrategyRegistry` (strategy pattern — no if/elif in the loop body)
4. After all sections, accumulates global beat offsets and builds the MIDI tracks

### JSON input structure

Two files are always required: a **theme** and a **piece**.

- `themes/` — theme JSON files (key, mode, tempo range, motif)
- `compositions/` — piece JSON files (tempo, sections with progressions, per-section options)

The theme may define `motif` (single) or `motifs` (pool); if both are present, `motifs` takes precedence.

Pieces support two form types:
- **narrative** (default): `"sections": [...]` — ordered list, generated once
- **song**: `"form_type": "song"` with `"form": [...]` array referencing a `"sections": {}` dict of named reusable section definitions

### Section fields that drive generation

| Field | Effect |
|---|---|
| `rhythm` | `"free"` (density grid), `"motif"` (motif rhythm tiled), `"pattern"` (hand-played, requires `rhythm_pattern` block) |
| `harmony_rhythm` | Object with optional `rhythm`, `density`, `groove`, `swing` overrides for the harmony voice only |
| `counterpoint` | Object or list of up to 3 objects; `species` = `"first"` or `"free"` |
| `drums` | String shorthand (`"four_on_floor"`) or object with `pattern`, `density`, `groove`, `swing` |
| `arc` | Dynamic shape applied to melody velocity: `swell`, `build`, `fade_in`, `fade_out`, `breath`, `plateau`, `decay` |
| `transform_sequence` | Piece-level list of motif transforms applied in order across sections |

### Validation

`schemas.py` defines Pydantic v2 models (`ThemeModel`, `PieceModel`, `SectionModel`, etc.) that are the single source of truth for all valid values. `PieceModel.validate_against_theme(theme_model)` handles cross-file checks (e.g., `rhythm='motif'` requires a theme motif with a `rhythm` field).

### MIDI output layout

Track 0: tempo/time signature metadata  
Track 1: Melody (ch 0)  
Track 2–4: Counterpoint voices (ch 2–4, only if sections use them)  
Track 5: Harmony (ch 1)  
Track 6: Bass (ch 3)  
Track 7: Drums (ch 9, only if sections use them)  

No GM `program_change` messages carry instrument meaning — assign sounds in your DAW (Logic Pro). Track names (`Melody`, `Harmony`, `Bass`, etc.) are written as MIDI meta messages.

PPQ is 480 (ticks per quarter note).
