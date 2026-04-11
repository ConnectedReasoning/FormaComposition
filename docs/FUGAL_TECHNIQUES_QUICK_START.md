# Fugal Techniques — Quick Start

You now have **motif_transform** and **stretto_compression** built into FormaComposition.

## What You Have

**2 files to integrate:**
1. `melody.py` — Replace `intervals/music/melody.py`
2. `generator.py` — Replace `intervals/core/generator.py`

**2 example JSONs to reference:**
1. `still_cove_sonata_form_with_fugal_techniques.json` — Complete Sonata form with all techniques
2. `FUGAL_TECHNIQUES_GUIDE.md` — Full documentation

---

## 5-Minute Setup

### 1. Backup your current files
```bash
cp intervals/music/melody.py intervals/music/melody.py.backup
cp intervals/core/generator.py intervals/core/generator.py.backup
```

### 2. Install the new files
```bash
cp melody.py intervals/music/
cp generator.py intervals/core/
```

### 3. Test it works
```bash
python main.py theme_evening_water.json still_cove_v2.json --output test_output.mid
# Should generate MIDI without errors
```

---

## Using Fugal Techniques

### Simplest Example: Inversion

```json
{
  "name": "exposition_secondary",
  "bars": 12,
  "progression": ["III", "V", "I"],
  "melody": "lyrical",
  "fugal_techniques": {
    "motif_transform": "inversion"
  }
}
```

That's it. The motif will be inverted (intervals flipped).

### With Compression

```json
{
  "name": "stretto",
  "bars": 16,
  "progression": ["i"],
  "melody": "develop",
  "fugal_techniques": {
    "motif_transform": "none",
    "stretto_compression": 0.5
  }
}
```

Motif moves at double speed (half duration).

### Combination

```json
{
  "name": "development",
  "bars": 8,
  "progression": ["v", "VI", "VII"],
  "melody": "develop",
  "fugal_techniques": {
    "motif_transform": "retrograde",
    "stretto_compression": 0.75
  }
}
```

Retrograde motif at 3/4 speed (restless, exploratory).

---

## Workflow

### 1. Write your form structure (sections, progressions, arcs)
```json
"sections": [
  { "name": "exposition_primary", "bars": 12, "progression": [...] },
  { "name": "exposition_secondary", "bars": 12, "progression": [...] },
  { "name": "development", "bars": 16, "progression": [...] }
]
```

### 2. Add fugal_techniques to key sections
```json
"sections": [
  { "name": "exposition_primary", "bars": 12, "progression": [...], "fugal_techniques": { "motif_transform": "none" } },
  { "name": "exposition_secondary", "bars": 12, "progression": [...], "fugal_techniques": { "motif_transform": "inversion" } },
  { "name": "development", "bars": 16, "progression": [...], "fugal_techniques": { "motif_transform": "retrograde", "stretto_compression": 0.75 } }
]
```

### 3. Generate
```bash
python main.py theme_evening_water.json your_piece.json
```

### 4. Listen in Logic
Ear-check. Does the transformation work? Does the compression feel right?

### 5. Iterate
If inversion sounds too different, try retrograde. If compression is too fast, try 0.67 or 0.75.

---

## Transform Options

| Transform | Effect | Use Case |
|-----------|--------|----------|
| `"none"` | Original motif | Opening theme, returns, coda |
| `"inversion"` | Flip intervals | Secondary theme (contrasting) |
| `"retrograde"` | Play backwards | Development (exploratory) |
| `"retrograde_inversion"` | Reverse + flip | Deep development (furthest point) |

## Compression Options

| Value | Speed | Use Case |
|-------|-------|----------|
| `1.0` | Normal | Standard |
| `0.5` | 2x fast | Urgency, stretto |
| `0.75` | 1.33x fast | Slightly restless |
| `0.67` | 1.5x fast | Medium restless |
| `2.0` | 2x slow | Sustained, lyrical |

---

## Real Example: Sonata Form

Use the included `still_cove_sonata_form_with_fugal_techniques.json` as your template:

- **Exposition A**: Original motif (`"none"`)
- **Exposition B**: Inverted motif (`"inversion"`)
- **Development A**: Retrograde, slightly compressed (`0.75`)
- **Development B**: Retrograde inversion, very compressed (`0.5`) — furthest point
- **Development C**: Rest, original motif (`"none"`) — preparation for return
- **Recap A**: Original motif (`"none"`) — feels like resolution
- **Recap B**: Original motif (`"none"`) — settling
- **Coda**: Inverted motif (`"inversion"`) — final gesture

**Result**: 80-bar piece (~5.5 min at 68 BPM) with intentional melodic development and architectural form.

---

## Troubleshooting

### Error: "KeyError: 'motif_transform'"
Make sure your JSON is valid. Use a JSON validator: https://jsonlint.com

### "The melody doesn't sound different"
- Check that `melody` behavior is set (not just `"sparse"`)
- Verify the progression is different per section
- Try a different seed (change `"seed": 42` to `100`)

### "Transform sounds too extreme"
- Inversion creates maximum contrast—that's intentional
- Pair it with a different progression (e.g., relative major)
- Try `retrograde` instead of `inversion`

### "Compression makes it unsingable"
- Try 0.75 instead of 0.5
- Remember: compression scales *motif* rhythm, not section density
- If the melody is still too fast, reduce density or switch melody behavior

---

## What's Next

Once you ship a Sonata form piece using these techniques:

1. **Generate it** (seed 42)
2. **Listen in Logic** (instrument assignment by ear)
3. **Try 2–3 seeds** (100, 200) to explore variations
4. **Pick the best version**
5. **Ship it**

Then build your next piece using different form (Rondo, Theme & Variations, etc.).

**Future features** (not yet shipped):
- `answer_transposition`: Fugal-style transposed answer
- `subject_fragmentation`: Break motif into pieces
- `canonic_imitation`: Canon-like voice entry

For now, `motif_transform` + `stretto_compression` give you enough to compose sophisticated, form-driven music.

---

## Reference

Full documentation: `FUGAL_TECHNIQUES_GUIDE.md`

Example patterns:
- Sonata form: `still_cove_sonata_form_with_fugal_techniques.json`
- More patterns in the guide

You're ready to compose.
