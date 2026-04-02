# Motif System Architecture

## Overview

The FormaComposition engine now uses a **four-level hierarchy** for musical organization:

```
Motif (atomic musical DNA)
  ↓
Theme (musical world)
  ↓
Piece (arrangement)
  ↓
Section (local variations)
```

This allows you to:
- **Reuse motifs** across multiple themes
- **Build a motif library** of melodic ideas
- **Experiment** with the same motif in different keys/modes
- **Share motifs** between compositions

---

## File Structure

```
compositions/
├── motifs/
│   ├── motif_ascending_hope.json
│   ├── motif_descending_melancholy.json
│   ├── motif_lydian_shimmer.json
│   └── motif_<name>.json
│
├── theme_*.json                    # Themes reference motifs by name
└── *.json                          # Pieces reference themes by name
```

---

## Motif Files

**Format:** `motifs/motif_<name>.json`

```json
{
  "motif": {
    "name": "ascending_hope",
    "intervals": [2, 2, 1, 2],
    "rhythm": [1.0, 1.0, 0.5, 1.5],
    "transform_pool": [
      "inversion",
      "retrograde",
      "augmentation",
      "diminution",
      "transpose_up",
      "transpose_down"
    ]
  }
}
```

**Fields:**
- `name`: Unique identifier (must match filename without prefix/extension)
- `intervals`: Semitone steps between notes (e.g., [2, 2, 1, 2] = whole, whole, half, whole)
- `rhythm`: Duration in beats for each note
- `transform_pool`: Available Bach-style transforms for variation

**Available Transforms:**
- `inversion` — Mirror the melodic shape (negate all intervals)
- `retrograde` — Reverse the sequence
- `augmentation` — Double all note durations
- `diminution` — Halve all note durations
- `transpose_up` — Shift up 2 semitones
- `transpose_down` — Shift down 2 semitones
- `shuffle` — Randomly reorder intervals
- `expand` — Scale intervals by 1.5 (wider leaps)
- `compress` — Scale intervals by 0.5 (smaller steps)
- `retrograde_inversion` — Reverse then negate

---

## Theme Files (Updated)

Themes now reference motifs **by name** instead of embedding them:

**Old format (still supported):**
```json
{
  "theme": {
    "name": "Evening Water",
    "key": "D",
    "mode": "dorian",
    "tempo": {"min": 60, "max": 80},
    "motif": {
      "intervals": [2, -1, 3, -2],
      "rhythm": [1.0, 0.5, 0.5, 1.0]
    }
  }
}
```

**New format (recommended):**
```json
{
  "theme": {
    "name": "Evening Water",
    "key": "D",
    "mode": "dorian",
    "tempo": {"min": 60, "max": 80},
    "motif": "ascending_hope"
  }
}
```

The generator will:
1. Check if `"motif"` is a **string** → load from `motifs/motif_<name>.json`
2. Check if `"motif"` is a **dict** → use embedded definition (backward compatible)
3. Check if `"phrase"` exists → generate motif from prosody (still works)

---

## Python API

### Loading Motifs

```python
from intervals.core.motif_loader import load_motif, list_available_motifs

# List all motifs in library
motifs = list_available_motifs()
print(motifs)  # ['ascending_hope', 'descending_melancholy', ...]

# Load a specific motif
motif = load_motif("ascending_hope")
print(motif.intervals)  # [2, 2, 1, 2]
print(motif.rhythm)     # [1.0, 1.0, 0.5, 1.5]
```

### Saving Motifs

```python
from intervals.music.motif import Motif
from intervals.core.motif_loader import save_motif

# Create a new motif
motif = Motif(
    name="my_idea",
    intervals=[3, -1, 2, -2],
    rhythm=[1.0, 0.5, 0.5, 1.0],
    transform_pool=["inversion", "retrograde"]
)

# Save to library
save_motif(motif)  # Creates motifs/motif_my_idea.json
```

### Generator Integration

The generator automatically resolves motifs from themes:

```python
from intervals.core.motif_loader import resolve_motif_from_theme

# Supports all three formats:
theme_new = {"motif": "ascending_hope"}          # Name reference
theme_old = {"motif": {"intervals": [...]}}      # Embedded dict
theme_prosody = {"phrase": "light on still water"}  # Prosody

motif = resolve_motif_from_theme(theme_new)
```

---

## Migration Guide

### Converting Existing Themes

If you have themes with embedded motifs, you can extract them:

**Step 1:** Save the motif to the library
```python
from intervals.music.motif import from_dict
from intervals.core.motif_loader import save_motif

# Extract motif from theme
theme = load_theme("theme_evening_water.json")
motif_dict = theme["motif"]
motif = from_dict(motif_dict)
motif.name = "evening_water"  # Give it a name

# Save to library
save_motif(motif)
```

**Step 2:** Update theme to reference by name
```json
{
  "theme": {
    "name": "Evening Water",
    "motif": "evening_water"
  }
}
```

### No Breaking Changes

The old embedded format still works! The loader handles both:
- **New**: `"motif": "ascending_hope"` (string reference)
- **Old**: `"motif": {"intervals": [...]}` (embedded dict)
- **Prosody**: `"phrase": "light on still water"` (auto-generated)

---

## Workflow Examples

### Reusing a Motif Across Themes

```json
// theme_dorian_dawn.json
{
  "theme": {
    "name": "Dorian Dawn",
    "key": "D",
    "mode": "dorian",
    "motif": "ascending_hope"
  }
}

// theme_lydian_light.json
{
  "theme": {
    "name": "Lydian Light",
    "key": "F",
    "mode": "lydian",
    "motif": "ascending_hope"
  }
}
```

Same melodic DNA, completely different harmonic worlds.

### Building a Motif from a Phrase

```python
from intervals.music.prosody import phrase_to_motif
from intervals.core.motif_loader import save_motif

# Convert phrase to motif
motif = phrase_to_motif("light on still water")
motif.name = "still_water"

# Save for reuse
save_motif(motif)
```

Now you can reference it: `"motif": "still_water"`

### Creating a Motif Library

```bash
compositions/motifs/
├── motif_ascending_hope.json      # Major upward motion
├── motif_descending_melancholy.json  # Minor downward motion
├── motif_lydian_shimmer.json      # Raised 4th character
├── motif_still_water.json         # Prosody-derived
├── motif_bach_subject_01.json     # Baroque counterpoint
└── motif_eno_ambient.json         # Slow evolving
```

Mix and match across themes as needed.

---

## Design Philosophy

**Motif = Atomic Musical DNA**
- A small, memorable intervallic idea
- Can be transformed (Bach-style)
- Lives independently of key/mode

**Theme = Musical World**
- Defines tonality (key + mode)
- References a motif (not owns it)
- Sets tempo and palette

**Piece = Arrangement**
- Uses a theme's world
- Defines section structure
- Specific tempo within theme's range

**Section = Local Variation**
- Overrides theme defaults
- Defines progression and arc
- Controls density, groove, etc.

This separation lets you experiment freely: "What does this motif sound like in Phrygian? In Lydian? At 120 BPM vs 60 BPM?"

---

## Testing the New System

### Command Line

```bash
# Create a new motif file
cat > compositions/motifs/motif_test.json << 'EOF'
{
  "motif": {
    "name": "test",
    "intervals": [2, 2, -1, 3],
    "rhythm": [1.0, 0.5, 0.5, 1.0]
  }
}
EOF

# Create a theme that references it
cat > compositions/theme_test.json << 'EOF'
{
  "theme": {
    "name": "Test Theme",
    "key": "C",
    "mode": "ionian",
    "tempo": {"min": 60, "max": 80},
    "motif": "test"
  }
}
EOF

# Generate a piece using it
python forma/main.py compositions/theme_test.json compositions/light_on_still_water.json
```

### Python REPL

```python
from intervals.core.motif_loader import load_motif, list_available_motifs

# List available
print(list_available_motifs())

# Load and inspect
motif = load_motif("ascending_hope")
print(f"Intervals: {motif.intervals}")
print(f"Contour: {''.join(motif.contour())}")
print(f"Range: {motif.interval_range()} semitones")
```

---

## Future Enhancements

Potential additions to the motif system:

1. **Per-section motif selection**
   - Sections could override theme's motif
   - `"section": {"motif": "different_motif"}`

2. **Motif blending**
   - Interpolate between two motifs over time
   - `"motif_a": "hope", "motif_b": "melancholy", "blend": 0.5`

3. **Motif chains**
   - Sequence of motifs: A → B → A' → C
   - `"motif_sequence": ["hope", "melancholy", "hope"]`

4. **Dynamic transform selection**
   - Control which transforms are used per section
   - `"transforms": ["inversion", "retrograde"]`

For now, the system is **one motif per theme**, but the architecture supports these extensions cleanly.

---

## Summary

**Before (3 levels):**
```
Theme (contains motif) → Piece → Section
```

**After (4 levels):**
```
Motif → Theme (references motif) → Piece → Section
```

**Benefits:**
- ✅ Reuse melodic ideas across themes
- ✅ Build a library of motifs
- ✅ Experiment with same motif in different tonalities
- ✅ Backward compatible with existing themes
- ✅ Prosody integration still works

**No breaking changes** — all existing themes continue to work as-is!
