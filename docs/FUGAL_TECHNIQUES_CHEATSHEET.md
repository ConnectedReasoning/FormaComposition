# Fugal Techniques — Quick Reference Card

## All Techniques at a Glance

```json
{
  "fugal_techniques": {
    // MOTIF TRANSFORMS (change intervals/rhythm)
    "motif_transform": "inversion" | "retrograde" | "retrograde_inversion" | 
                       "augmentation" | "diminution" | "transpose_up" | 
                       "transpose_down" | "expand" | "compress" | "shuffle" | "none",
    
    // RHYTHM COMPRESSION (speed up/slow down)
    "stretto_compression": 0.5,  // 2x faster, 1.0 normal, 2.0 2x slower
    
    // EPISODIC DEVELOPMENT (use first N intervals)
    "subject_fragmentation": 2,  // Use first 2 intervals only
    
    // OFFSET VOICE ENTRIES (like stretto)
    "canonic_imitation": true,
    "canon_interval": 4,         // Beats between entries
    "canon_transposition": 7     // Semitones for transposed imitation
  }
}
```

---

## The Transforms Explained in 30 Seconds

| What | Input | Output | Greenberg Says |
|------|-------|--------|-----------------|
| **inversion** | `[2, -1, 3]` | `[-2, 1, -3]` | Mirror image of subject |
| **retrograde** | `[2, -1, 3]` | `[3, -1, 2]` | Play backwards |
| **retrograde_inversion** | `[2, -1, 3]` | `[-3, 1, -2]` | Both |
| **augmentation** | rhythm `[1, 0.5]` | `[2, 1]` | "Expanded form" |
| **diminution** | rhythm `[1, 0.5]` | `[0.5, 0.25]` | "Compressed form" |
| **stretto_compression** | rhythm `[1, 0.5]` scaled by 0.5 | `[0.5, 0.25]` | Subject overlapped, urgency |
| **subject_fragmentation** | `[2, -1, 3, -2]` take first 2 | `[2, -1]` | Episode material from subject |

---

## Sonata Form Template

Copy-paste this and fill in your progressions:

```json
{
  "piece": {
    "title": "Your Title",
    "theme": "Your Theme",
    "tempo": 68,
    "seed": 42,
    "sections": [
      {
        "name": "exposition_primary",
        "bars": 12,
        "progression": ["i", "VII", "iv", "v"],
        "melody": "lyrical",
        "arc": "fade_in",
        "fugal_techniques": { "motif_transform": "none" }
      },
      {
        "name": "exposition_secondary",
        "bars": 12,
        "progression": ["III", "V", "I"],
        "melody": "lyrical",
        "arc": "swell",
        "fugal_techniques": { "motif_transform": "inversion" }
      },
      {
        "name": "development_a",
        "bars": 8,
        "progression": ["v", "VI", "VII"],
        "melody": "develop",
        "density": "full",
        "arc": "peak",
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
        "arc": "peak",
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
        "arc": "swell",
        "fugal_techniques": { "motif_transform": "none" }
      },
      {
        "name": "coda",
        "bars": 8,
        "progression": ["i"],
        "melody": "sparse",
        "arc": "fade_out",
        "fugal_techniques": { "motif_transform": "inversion" }
      }
    ]
  }
}
```

---

## Quick Recipes

### Create Urgency (Stretto Effect)
```json
"fugal_techniques": {
  "stretto_compression": 0.5
}
```

### Create Contrast (Secondary Theme)
```json
"fugal_techniques": {
  "motif_transform": "inversion"
}
```

### Create Development (Episode)
```json
"fugal_techniques": {
  "motif_transform": "retrograde",
  "subject_fragmentation": 2,
  "stretto_compression": 0.75
}
```

### Create Climax (Furthest Point)
```json
"fugal_techniques": {
  "motif_transform": "retrograde_inversion",
  "stretto_compression": 0.5,
  "subject_fragmentation": 3
}
```

### Create Resolution (Return)
```json
"fugal_techniques": {
  "motif_transform": "none"
}
```

---

## All Transform Options

### Motif Transforms (`motif_transform`)
- `"none"` — Original
- `"inversion"` — Flip intervals
- `"retrograde"` — Reverse order
- `"retrograde_inversion"` — Both
- `"augmentation"` — 2x longer
- `"diminution"` — 0.5x shorter
- `"transpose_up"` — Up 2 semitones
- `"transpose_down"` — Down 2 semitones
- `"expand"` — 1.5x wider intervals
- `"compress"` — 0.5x narrower intervals
- `"shuffle"` — Randomize

### Compression Values (`stretto_compression`)
- `0.5` = 2x faster ⚡⚡
- `0.67` = 1.5x faster ⚡
- `0.75` = 1.33x faster ◸
- `1.0` = normal ●
- `1.5` = slower ◿
- `2.0` = 2x slower ◐◐

---

## The Golden Rule

**Every technique must serve the form.**

Don't use inversion just because it's cool. Use it because exposition B needs to contrast with exposition A. Don't compress rhythm just for urgency. Compress it in the development where the listener expects restlessness.

Form drives technique. Technique serves form.

---

## Ear-Check Workflow

1. **Write your form** (section names, progressions, arcs)
2. **Add fugal_techniques** (one transform per section to start)
3. **Generate** (`python main.py theme.json piece.json`)
4. **Listen** (in Logic, full ear-check)
5. **Iterate** (if it doesn't work, try a different transform or seed)
6. **Ship** (when it sounds like a journey)

---

## Need Help?

- **Full guide**: See `COMPLETE_FUGAL_TECHNIQUES.md`
- **Bach theory**: Greenberg's lectures (you have them)
- **Motif design**: Make sure your motif works when inverted/retrograded
- **Form structure**: Sonata form is A-B-A; Theme & Variations is A-A'-A''-A

---

## You Have Everything

- ✅ Form structure (sections, progressions, arcs)
- ✅ All Baroque transforms (inversion, retrograde, augmentation, diminution)
- ✅ Rhythm control (compression, humanization, swing)
- ✅ Counterpoint (species, register, dissonance)
- ✅ Melody behavior (lyrical, sparse, develop, generative)
- ✅ Bass styles (pedal, root_fifth, walking, melodic)
- ✅ Seed variation (explore alternatives)

**Ship it.**
