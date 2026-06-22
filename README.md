# FormaComposition

A generative structural harmony system that produces multi-voice MIDI compositions from declarative JSON definitions. Designed for long-form ambient and new age music — pieces you perform over, not just listen to.

The system sits between pure randomness and full composition. You define the harmonic architecture: key, mode, chord progressions, section structure, and motivic material. FormaComposition generates the voices — harmony, bass, melody, and counterpoint — with musical coherence rather than noise.

Output is instrument-agnostic MIDI. Assign sounds in your DAW.

---

## How it works

A **theme** defines the musical environment shared across related pieces:
- Key and mode
- Tempo range
- A **motif** — a short interval sequence that serves as melodic DNA

A **piece** defines a specific composition within that environment:
- Actual tempo
- Sections, each with a chord progression, density, bass style, and dynamic arc
- Optional counterpoint per section

The engine resolves Roman numeral progressions to voiced MIDI chords, generates bass lines in five styles, produces melody using one of four behaviors (with Bach-style motif transforms), and optionally adds a counterpoint voice following classical rules.

No GM program change messages are written. Track names (`Harmony`, `Bass`, `Melody`, `Counterpoint`) appear in your DAW ready for instrument assignment.

---

## Architecture

```
intervals/
  music/
    harmony.py       Roman numeral → voiced MIDI chords, all 7 modes, extensions to 11th
    bass.py          Five bass styles: root_only, root_fifth, walking, pulse, pedal
    melody.py        Four behaviors: generative, lyrical, sparse, develop
    motif.py         Bach-style transforms: inversion, retrograde, augmentation, diminution
    counterpoint.py  1st species and free species, classical rules, above or below
    rhythm.py        Density → timing patterns, velocity arcs, swing
  core/
    generator.py     Assembles all voices into a multi-track MIDI file

main.py              CLI entry point
compositions/        Example themes and pieces
```

---

## Quick start

```bash
git clone https://github.com/yourusername/FormaComposition
cd FormaComposition
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
```

Generate the included example:

```bash
python main.py compositions/theme_evening_water.json compositions/still_cove.json
```

Preview without generating:

```bash
python main.py compositions/theme_evening_water.json compositions/still_cove.json --info
```

Generate multiple pieces at once:

```bash
python main.py theme.json piece_01.json piece_02.json piece_03.json --outdir ./album/
```

---

## Defining a theme

```json
{
  "theme": {
    "name": "Evening Water",
    "key": "D",
    "mode": "dorian",
    "tempo": { "min": 60, "max": 80 },
    "motif": {
      "name": "evening_water",
      "intervals": [2, -1, 3, -2],
      "rhythm": [1.0, 0.5, 0.5, 1.0],
      "transform_pool": ["inversion", "retrograde", "augmentation"]
    }
  }
}
```

**Modes:** `ionian`, `dorian`, `phrygian`, `lydian`, `mixolydian`, `aeolian`, `locrian`

**Motif intervals** are semitone steps between successive notes. `[2, -1, 3, -2]` means: up a whole tone, down a half tone, up a minor third, down a whole tone.

---

## Defining a piece

```json
{
  "piece": {
    "title": "Still Cove",
    "tempo": 68,
    "sections": [
      {
        "name": "opening",
        "bars": 8,
        "progression": ["i", "VII", "iv", "v"],
        "density": "sparse",
        "melody": "sparse",
        "bass_style": "pedal",
        "arc": "fade_in",
        "counterpoint": {
          "species": "first",
          "register": "below",
          "dissonance": "none"
        }
      },
      {
        "name": "swell",
        "bars": 12,
        "progression": ["i", "III", "VII", "i"],
        "density": "medium",
        "melody": "lyrical",
        "bass_style": "root_fifth",
        "arc": "swell"
      }
    ]
  }
}
```

### Section fields

| Field | Options | Description |
|---|---|---|
| `density` | `sparse`, `medium`, `full` | Note density across all voices |
| `melody` | `generative`, `lyrical`, `sparse`, `develop` | Melodic behavior |
| `bass_style` | `root_only`, `root_fifth`, `walking`, `pulse`, `pedal` | Bass pattern |
| `arc` | `flat`, `swell`, `fade_in`, `fade_out`, `breath` | Dynamic shape |

### Chord progressions

Progressions use Roman numeral notation. Uppercase = major quality, lowercase = minor, quality overrides are supported:

```
"i", "IV", "v", "VII"          — mode-derived quality
"Vmaj7", "iim7", "VII7"        — explicit extensions
```

### Counterpoint (optional per section)

```json
"counterpoint": {
  "species": "first",       // "first" or "free"
  "register": "below",      // "above" or "below"
  "dissonance": "none"      // "none" or "passing"
}
```

First species: strict note-against-note, all consonances. Free species: mixed rhythms, passing tones on weak beats, more musical movement.

---

## Documenting Logic Pro sessions

The piece JSON supports an optional `logic_instruments` field for recording what you assigned in your DAW after generation. This is purely documentation — it has no effect on generation.

```json
"logic_instruments": {
  "track_1_harmony": {
    "plugin": "JUP-8000 V",
    "preset": "Trance Bass",
    "notes": "Sawtooth + resonant filter. Filter envelope creates pulse on pedal bass."
  }
}
```

---

## Requirements

- Python 3.10+
- `mido`
- `numpy`

```bash
pip install -r requirements.txt
```

---

## Design principles

**Randomness needs structure to be musical.** Pure randomness produces incoherent output. Motif development — Bach-style transformation and evolution — gives ambient music its sense of going somewhere.

**The engine provides skeleton, the DAW provides flesh.** MIDI output is instrument-agnostic by design. The harmonic and rhythmic structure is real; the timbre and character come from instrument assignment in Logic Pro or any other DAW.

**Composing many short pieces beats engineering non-repetition.** For long sessions, write 10–20 thematically related pieces against a shared theme and string them together. The theme ensures they feel unified; each piece has its own arc.
