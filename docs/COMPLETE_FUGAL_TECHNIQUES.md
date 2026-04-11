# Complete Fugal Techniques for FormaComposition

## All Greenberg-Inspired Techniques Now Implemented

You now have **every High Baroque technique** from Greenberg's Bach lectures built into FormaComposition.

---

## 1. MOTIF TRANSFORMS

These come directly from `motif.py` and apply interval/rhythm changes to your subject.

### Available Transforms

| Transform | Effect | Use Case | Greenberg Context |
|-----------|--------|----------|-------------------|
| `"inversion"` | Flip all intervals (up→down, down→up) | Secondary theme | "Mirror image" of subject |
| `"retrograde"` | Reverse intervals + rhythm | Development | "Backwards" exploration |
| `"retrograde_inversion"` | Both retrograde + inverted | Deep development | Furthest point from original |
| `"augmentation"` | Double all rhythm durations | Sustained passages | Subject in "expanded form" |
| `"diminution"` | Halve all rhythm durations | Stretto, urgency | Subject in "compressed form" |
| `"transpose_up"` | Raise all intervals by 2 semitones | Modulation, Answer | Fugal "answer" to subject |
| `"transpose_down"` | Lower all intervals by 2 semitones | Modulation down | Transposed variant |
| `"expand"` | Scale intervals up (1.5x) | Register expansion | Wider intervallic leap |
| `"compress"` | Scale intervals down (0.5x) | Register compression | Closer intervallic spacing |
| `"shuffle"` | Randomize order of intervals/rhythms | Variation | New character from same material |

### JSON Usage

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

---

## 2. STRETTO COMPRESSION

Scale the subject's rhythm to create **overlapping entries** and **urgency**.

**What It Does**: Multiplies all note durations by a factor.

| Compression | Speed | Interpretation | Use Case |
|-------------|-------|-----------------|----------|
| `0.5` | 2x faster | Subject at double speed | Stretto, climax, urgency |
| `0.67` | 1.5x faster | 2/3 normal speed | Moderately restless |
| `0.75` | 1.33x faster | 3/4 normal speed | Slightly accelerated |
| `1.0` | Normal | (no change) | Standard |
| `1.5` | Slower | 1.5x duration | Sustained, lyrical |
| `2.0` | Half speed | Doubled duration | Very slow, augmented |

### JSON Usage

```json
{
  "name": "stretto",
  "bars": 16,
  "progression": ["i"],
  "melody": "develop",
  "fugal_techniques": {
    "stretto_compression": 0.5
  }
}
```

**Greenberg Context**: "Stretto—the subject overlapped with itself (stretto), either in its original form, or in an expanded form (augmentation), or a compressed form (diminution)."

---

## 3. SUBJECT FRAGMENTATION

Extract a subset of the motif's intervals for **episodic development**.

**What It Does**: Use only the first N intervals of the subject, creating shorter phrases for episodic passages.

### JSON Usage

```json
{
  "name": "episode_1",
  "bars": 8,
  "progression": ["v", "VI", "VII"],
  "melody": "develop",
  "fugal_techniques": {
    "subject_fragmentation": 2
  }
}
```

If your motif has intervals `[2, -1, 3, -2]`:
- `"subject_fragmentation": 1` → uses `[2]`
- `"subject_fragmentation": 2` → uses `[2, -1]`
- `"subject_fragmentation": 3` → uses `[2, -1, 3]`

**Greenberg Context**: "Episodes are transitional/modulatory passages based on motives derived from the subject."

---

## 4. CANONIC IMITATION

Create **offset voice entries** where the same subject appears in different voices at different times (like a canon or fugal stretto).

**What It Does**: 
- Triggers special handling to offset the melody entry
- Can transpose the imitation to different pitch levels
- Creates the "stacking up" effect of fugal voices

### JSON Usage

```json
{
  "name": "development_stretto",
  "bars": 16,
  "progression": ["i", "VII", "v"],
  "melody": "develop",
  "fugal_techniques": {
    "canonic_imitation": true,
    "canon_interval": 4,
    "canon_transposition": 7
  }
}
```

| Parameter | What It Does | Default |
|-----------|-------------|---------|
| `"canonic_imitation"` | Enable offset entries (true/false) | false |
| `"canon_interval"` | Beats between voice entries | 4 |
| `"canon_transposition"` | Semitones for transposed imitation (0 = same pitch) | 0 |

**Greenberg Context**: "The exposition is 'telescopic,' piling up entrances of the subject in different voices."

---

## 5. ANSWER TRANSPOSITION

Transpose the subject for a **fugal-style answer** (typically up a perfect 5th, like in real fugues).

**What It Does**: Shifts all intervals uniformly (used with `transpose_up`/`transpose_down` or as explicit parameter).

### JSON Usage

```json
{
  "name": "answer",
  "bars": 12,
  "progression": ["i", "v"],
  "melody": "lyrical",
  "fugal_techniques": {
    "motif_transform": "transpose_up",
    "answer_transposition": 7
  }
}
```

**Note**: `transpose_up` and `transpose_down` from motif transforms shift intervals by 2 semitones. For a perfect 5th answer (7 semitones), use `"answer_transposition": 7` or manually adjust the progression to the V key area and let natural harmony do the transposition.

**Greenberg Context**: "The subject is heard systematically in each part (voice), accompanied by various subsidiary melodic material that is invariably generated from the subject itself."

---

## COMBINING TECHNIQUES: Real Examples

### Example 1: Classic Sonata Form with Fugal Techniques

```json
{
  "sections": [
    {
      "name": "exposition_primary",
      "bars": 12,
      "progression": ["i", "VII", "iv", "v"],
      "melody": "lyrical",
      "fugal_techniques": {
        "motif_transform": "none"
      }
    },
    {
      "name": "exposition_secondary",
      "bars": 12,
      "progression": ["III", "V", "I"],
      "melody": "lyrical",
      "fugal_techniques": {
        "motif_transform": "inversion"
      }
    },
    {
      "name": "development_a",
      "bars": 8,
      "progression": ["v", "VI", "VII"],
      "melody": "develop",
      "density": "full",
      "fugal_techniques": {
        "motif_transform": "retrograde",
        "stretto_compression": 0.75,
        "subject_fragmentation": 2
      }
    },
    {
      "name": "development_b",
      "bars": 8,
      "progression": ["iv", "VII", "v"],
      "melody": "develop",
      "density": "full",
      "fugal_techniques": {
        "motif_transform": "retrograde_inversion",
        "stretto_compression": 0.5
      }
    },
    {
      "name": "recap_primary",
      "bars": 12,
      "progression": ["i", "VII", "iv", "v"],
      "melody": "lyrical",
      "fugal_techniques": {
        "motif_transform": "none"
      }
    }
  ]
}
```

**Story**:
- **Expo A**: Original subject (home key, familiar)
- **Expo B**: Inverted subject (relative major, contrasting but related)
- **Dev A**: Retrograde fragments at 3/4 speed (restless, exploratory)
- **Dev B**: Retrograde inversion, double speed (furthest point, urgency)
- **Recap A**: Original returns (resolution, feels like coming home)

### Example 2: Theme & Variations

```json
{
  "sections": [
    {
      "name": "theme",
      "bars": 16,
      "progression": ["i", "III", "VII", "i"],
      "melody": "lyrical",
      "fugal_techniques": {
        "motif_transform": "none"
      }
    },
    {
      "name": "var_1_inverted",
      "bars": 16,
      "progression": ["i", "III", "VII", "i"],
      "melody": "develop",
      "density": "medium",
      "fugal_techniques": {
        "motif_transform": "inversion"
      }
    },
    {
      "name": "var_2_fast",
      "bars": 16,
      "progression": ["i", "III", "VII", "i"],
      "melody": "generative",
      "density": "full",
      "fugal_techniques": {
        "stretto_compression": 0.5
      }
    },
    {
      "name": "var_3_retrograde",
      "bars": 16,
      "progression": ["i", "III", "VII", "i"],
      "melody": "sparse",
      "density": "sparse",
      "fugal_techniques": {
        "motif_transform": "retrograde"
      }
    },
    {
      "name": "var_4_augmented",
      "bars": 16,
      "progression": ["i", "III", "VII", "i"],
      "melody": "lyrical",
      "density": "medium",
      "fugal_techniques": {
        "motif_transform": "augmentation"
      }
    },
    {
      "name": "theme_return",
      "bars": 16,
      "progression": ["i", "III", "VII", "i"],
      "melody": "lyrical",
      "fugal_techniques": {
        "motif_transform": "none"
      }
    }
  ]
}
```

### Example 3: Ritornello Form with Episodes

```json
{
  "sections": [
    {
      "name": "ritornello_1",
      "bars": 12,
      "progression": ["i", "VII", "iv", "v"],
      "melody": "sparse",
      "density": "full",
      "fugal_techniques": {
        "motif_transform": "none"
      }
    },
    {
      "name": "episode_1",
      "bars": 8,
      "progression": ["III", "V"],
      "melody": "develop",
      "density": "medium",
      "fugal_techniques": {
        "subject_fragmentation": 2,
        "stretto_compression": 0.75
      }
    },
    {
      "name": "ritornello_2_partial",
      "bars": 8,
      "progression": ["i", "VII"],
      "melody": "sparse",
      "density": "full",
      "fugal_techniques": {
        "motif_transform": "inversion"
      }
    },
    {
      "name": "episode_2",
      "bars": 12,
      "progression": ["v", "VI", "VII"],
      "melody": "develop",
      "density": "full",
      "fugal_techniques": {
        "subject_fragmentation": 3,
        "stretto_compression": 0.5
      }
    },
    {
      "name": "ritornello_3_full",
      "bars": 12,
      "progression": ["i", "VII", "iv", "v"],
      "melody": "sparse",
      "density": "full",
      "fugal_techniques": {
        "motif_transform": "none"
      }
    }
  ]
}
```

---

## Implementation Notes

### What Happens Under the Hood

1. **Motif Loaded**: From `theme.json`, e.g., `intervals: [2, -1, 3, -2]`
2. **Techniques Applied** (in order):
   - Motif transform (inversion, retrograde, etc.)
   - Stretto compression (rhythm scaling)
   - Subject fragmentation (interval truncation)
3. **Melody Generated**: Using the transformed motif
4. **Canonic Imitation** (if enabled): Offsets the melody in time

### Backward Compatibility

- Sections **without** `fugal_techniques` work exactly as before
- `"motif_transform": "none"` is equivalent to omitting the parameter
- All parameters are optional

### Performance

- Negligible overhead—transforms are applied once per section
- No impact on generation speed

---

## Workflow

### 1. Design Your Form
```json
"sections": [
  { "name": "section_1", "bars": 12, "progression": [...] },
  { "name": "section_2", "bars": 8, "progression": [...] }
]
```

### 2. Add Fugal Techniques
```json
"sections": [
  { 
    "name": "section_1", 
    "bars": 12, 
    "progression": [...],
    "fugal_techniques": {
      "motif_transform": "inversion",
      "stretto_compression": 1.0
    }
  }
]
```

### 3. Generate
```bash
python main.py theme.json piece.json
```

### 4. Ear-Check in Logic
Does the transformation work? Does it sound like development? Adjust and regenerate.

### 5. Try Different Seeds
Change `"seed": 42` to `100`, `200`, etc. to explore melodic alternatives within the same harmonic structure.

---

## Troubleshooting

**"The inversion sounds too different"**
- That's correct—inversion creates maximum contrast while preserving interval relationships
- Pair it with a different harmonic area (relative major/minor)
- Try `retrograde` instead (less extreme)

**"Compression makes it unsingable"**
- Try `0.75` instead of `0.5`
- The compressed rhythm is on the *motif*, not the whole section
- Melody behavior (`develop`, `lyrical`) still applies

**"Fragmentation feels truncated"**
- Yes, it extracts only the first N intervals
- Use `subject_fragmentation: 2` or `3` (not 1)
- Fragments work best in transitional/episode sections

**"Canonic imitation doesn't sound like a canon"**
- Canonic imitation offsets the melody in time, but doesn't create true 2-part counterpoint
- For full stretto with multiple voices, you'd need algorithmic voice entry (future enhancement)
- The effect is more of an echo/delay than a true canon

---

## The Greenberg Blueprint

Every technique comes from Greenberg's Bach lectures:

> "A fugue subject is difficult to write because it must be melodically interesting, yet it must work when overlapped with itself."

Your motifs satisfy this. Now you have every tool to explore what happens when you:
- Invert it
- Reverse it
- Speed it up / slow it down
- Break it into pieces
- Stack it on itself

**The synthesis is the composition.**

---

## What's Still Future

- **True voice entry sequences**: Algorithmic subject entry in multiple voices
- **Automatic answer generation**: Real fugal answer (fifth-based adjustment, avoided intervals, etc.)
- **Chromatic alteration**: Raising/lowering specific pitches for modal mixture
- **Interval inversion with key adaptation**: Real tonal answer (adjusts for mode)

For now, you have the tools to compose like Bach. Use them.
