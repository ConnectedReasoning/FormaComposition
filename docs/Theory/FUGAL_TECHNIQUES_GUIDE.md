# Fugal Techniques in FormaComposition

## Overview

FormaComposition now supports **modular fugal techniques** as optional per-section parameters. These tools allow you to control motif transformations and rhythmic compression without enforcing strict fugal form.

Use them individually, mix and match, or skip them entirely—they're compositional tools, not algorithmic constraints.

---

## Available Techniques

### 1. `motif_transform`

**What it does**: Applies a mathematical transformation to the motif's intervals.

**Options**:
- `"none"` — Original motif (default, no transform)
- `"inversion"` — Flip all intervals (up becomes down, down becomes up)
- `"retrograde"` — Reverse the order of intervals and rhythm
- `"retrograde_inversion"` — Retrograde of the inverted motif

**Example**:

Original motif: `intervals: [2, -1, 3, -2]` (up 2, down 1, up 3, down 2)

- **Inversion**: `[-2, 1, -3, 2]` (down 2, up 1, down 3, up 2) — mirror image
- **Retrograde**: `[-2, 3, -1, 2]` (play intervals backwards)
- **Retrograde Inversion**: `[2, -3, 1, -2]` (retrograde + inverted)

**JSON**:
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

**Use case**: Exposition B (secondary theme) uses inverted motif to create contrasting character while maintaining motivic unity.

---

### 2. `stretto_compression`

**What it does**: Scales all rhythm durations of the motif by a factor.

**Value**: Float multiplier (0.5 = half speed, 2.0 = double speed, 1.0 = no change)

**Example**:

Original motif rhythm: `[1.0, 0.5, 0.5, 1.0]` (quarter, eighth, eighth, quarter)

- **0.5 compression**: `[0.5, 0.25, 0.25, 0.5]` (double speed, half the duration)
- **2.0 compression**: `[2.0, 1.0, 1.0, 2.0]` (half speed, double the duration)

**JSON**:
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

**Use case**: Development or stretto section where the motif moves faster, creating urgency and propulsion.

---

## Typical Usage Patterns

### Pattern 1: Sonata Form Development

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
      "fugal_techniques": {
        "motif_transform": "retrograde",
        "stretto_compression": 0.75
      }
    },
    {
      "name": "development_b",
      "bars": 8,
      "progression": ["iv", "VII", "v"],
      "melody": "develop",
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
    },
    {
      "name": "coda",
      "bars": 8,
      "progression": ["i"],
      "melody": "sparse",
      "fugal_techniques": {
        "motif_transform": "inversion"
      }
    }
  ]
}
```

**Story**:
- Expo A: Original motif (familiar)
- Expo B: Inverted (contrasting, but related)
- Dev A: Retrograde (fragments, explores)
- Dev B: Retrograde inversion (furthest point, compressed for urgency)
- Recap A: Original returns (resolution)
- Coda: Inverted echo (final gesture)

---

### Pattern 2: Theme & Variations

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
      "name": "variation_1_inverted",
      "bars": 16,
      "progression": ["i", "III", "VII", "i"],
      "melody": "develop",
      "density": "medium",
      "fugal_techniques": {
        "motif_transform": "inversion"
      }
    },
    {
      "name": "variation_2_fast",
      "bars": 16,
      "progression": ["i", "III", "VII", "i"],
      "melody": "generative",
      "density": "full",
      "fugal_techniques": {
        "motif_transform": "none",
        "stretto_compression": 0.5
      }
    },
    {
      "name": "variation_3_retrograde",
      "bars": 16,
      "progression": ["i", "III", "VII", "i"],
      "melody": "sparse",
      "density": "sparse",
      "fugal_techniques": {
        "motif_transform": "retrograde"
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

**Story**:
- Theme: Original motif, medium density
- Var 1: Inverted, more developed
- Var 2: Original but fast (compression 0.5)
- Var 3: Retrograde, sparse (furthest variation)
- Return: Original again (feels like home)

---

### Pattern 3: Rondo with Fugal Refrain

```json
{
  "sections": [
    {
      "name": "A_first",
      "bars": 16,
      "progression": ["i", "VII", "iv", "v"],
      "melody": "lyrical",
      "fugal_techniques": {
        "motif_transform": "none"
      }
    },
    {
      "name": "B",
      "bars": 12,
      "progression": ["III", "V", "I"],
      "melody": "develop",
      "fugal_techniques": {
        "motif_transform": "inversion"
      }
    },
    {
      "name": "A_return",
      "bars": 16,
      "progression": ["i", "VII", "iv", "v"],
      "melody": "lyrical",
      "fugal_techniques": {
        "motif_transform": "none"
      }
    },
    {
      "name": "C",
      "bars": 12,
      "progression": ["v", "VI", "VII"],
      "melody": "generative",
      "density": "full",
      "fugal_techniques": {
        "motif_transform": "retrograde",
        "stretto_compression": 0.5
      }
    },
    {
      "name": "A_final",
      "bars": 16,
      "progression": ["i", "VII", "iv", "v"],
      "melody": "lyrical",
      "fugal_techniques": {
        "motif_transform": "none"
      }
    }
  ]
}
```

**Story**: A-B-A-C-A rondo with different transforms in B and C sections.

---

## Implementation Details

### How Transforms Work

1. **Motif loaded from theme.json** as dict with `"intervals"` and `"rhythm"`
2. **At section generation time**, if `fugal_techniques` is present:
   - Motif dict is converted to Motif object
   - Specified transform is applied (inversion, retrograde, etc.)
   - Compression is applied to rhythm if specified
   - Motif is converted back to dict
   - Melody generator uses the transformed motif
3. **Original motif unchanged** — transforms are applied per-section, not globally

### Backward Compatibility

- Sections **without** `fugal_techniques` work exactly as before
- Existing piece JSONs need no changes
- `motif_transform: "none"` is equivalent to omitting the parameter

### Performance

- Negligible overhead (transforms are simple interval/rhythm operations)
- Applied once per section, not per note
- No impact on generation speed

---

## Practical Workflow

### Step 1: Write your section structure
```json
{
  "name": "exposition_primary",
  "bars": 12,
  "progression": ["i", "VII", "iv", "v"],
  "melody": "lyrical"
}
```

### Step 2: Add fugal_techniques
```json
{
  "name": "exposition_primary",
  "bars": 12,
  "progression": ["i", "VII", "iv", "v"],
  "melody": "lyrical",
  "fugal_techniques": {
    "motif_transform": "inversion"
  }
}
```

### Step 3: Generate and ear-check
```bash
python main.py theme_evening_water.json still_cove_development.json
# Listen in Logic
```

### Step 4: Iterate
If the inversion doesn't work, try `"retrograde"` or remove `fugal_techniques` entirely.

---

## Troubleshooting

### "The inverted motif sounds disconnected from the original"

**This is actually correct behavior.** Inversion creates maximum contrast while maintaining interval relationships. If it feels too disconnected:
- Try `"retrograde"` instead (less extreme transformation)
- Pair it with a different progression (e.g., relative major)
- Increase density/velocity to make it feel less fragile

### "Stretto compression 0.5 makes the melody too fast"

Try 0.75 (3/4 speed) or 0.67 (2/3 speed) instead. Find the sweet spot for your tempo and listener's ear.

### "I want the transform but also want to modify the rhythm separately"

Use `"motif_transform"` for the interval transformation, then let `rhythm_pattern` (hand-played) override if needed in the section. Or adjust `density` and `melody` behavior to change articulation independently.

---

## Examples Included

See the provided JSONs:
- `still_cove_v2_with_seed.json` — Base version (use as reference)
- Write your own Sonata form using the patterns above

---

## What's Coming (Not Yet Implemented)

These are planned but not shipped in this version:

- `answer_transposition`: Transposed answer (fugal technique)
- `subject_fragmentation`: Break motif into smaller pieces
- `canonic_imitation`: Offset voice entries (canon-like effect)
- `augmentation`: Stretch all note durations

**For now**: `motif_transform` + `stretto_compression` give you 80% of what you need for most form-driven compositions.

---

## Design Philosophy

**These tools are:**
- ✅ Composable (use them together or separately)
- ✅ Optional (skip them if you don't need them)
- ✅ Modular (each section can have different transforms)
- ✅ Ear-checkable (generate, listen, iterate)

**These tools are NOT:**
- ❌ Algorithms that enforce fugal form
- ❌ Automatic answer generation
- ❌ Strict voice entry rules

You're in control. The system provides tools; you compose with intent.
