# FormaComposition — Complete Options Reference

## Modes (Tonality)

| Mode | Intervals from Root | Feel | Example in D |
|------|-------------------|------|-------------|
| **ionian** | W-W-H-W-W-W-H | Major, bright | D E F# G A B C# |
| **dorian** | W-H-W-W-W-H-W | Minor with raised 6, jazzy | D E F G A B C |
| **phrygian** | H-W-W-W-H-W-W | Minor with flat 2, Spanish | D Eb F G A Bb C |
| **lydian** | W-W-W-H-W-W-H | Major with raised 4, dreamy | D E F# G# A B C# |
| **mixolydian** | W-W-H-W-W-H-W | Major with flat 7, bluesy | D E F# G A B C |
| **aeolian** | W-H-W-W-H-W-W | Natural minor | D E F G A Bb C |
| **locrian** | H-W-W-H-W-W-W | Minor with flat 2 & 5, dark | D Eb F G Ab Bb C |

---

## Melody Behaviors

### **sparse**
- Few notes, lots of space
- Wide intervals, leaps across register
- Play probability: ~40%
- **Use when:** Intimate, ambient, questions
- **Good for:** Fade sections, sparse density

### **generative**
- Free choice from chord + scale tones
- Weights: chord 50%, scale 45%, chromatic 5%
- Prefers notes within 5th of current note (smooth motion)
- **Use when:** Open, flowing, experimental
- **Good for:** Medium density, wandering sections

### **lyrical**
- Stepwise motion (prefer scale tones 1-3 semitones away)
- Gravitates toward chord tones
- Random directional bias (up/down preference per phrase)
- **With statefulness:** Leans toward next chord's tones at phrase end
- **Use when:** Vocal-like, singing, emotional
- **Good for:** Swell sections, warmth

### **develop**
- Uses motif + transforms (inversion, retrograde, augmentation)
- Falls back to generative if no motif
- **Use when:** Building variation, climax, development
- **Good for:** Full density, peak moments

---

## Bass Styles

| Style | Pattern | Feel | Motion | **Use When** |
|-------|---------|------|--------|------------|
| **pedal** | Root held throughout | Drone, static | None | Sparse sections, ambience |
| **root_only** | Root once per chord | Minimal, anchoring | Root movement only | Fade-in/out, sparse |
| **root_fifth** | Root, then fifth, alternating | Classic, gentle | Root→fifth→root | Medium, warm, new age |
| **pulse** | Root on beat, repeated | Rhythmic, driving | Root pulsing | Upbeat, moving sections |
| **steady** | Locked figure per chord (4 variants) | Groove-based, locked | Repeating figure | Medium/full density |
| **walking** | Quarter notes: root→scale→chord→approach | Jazz/pop, forward | Scale-wise movement | Medium/full, motion |
| **melodic** | Expressive line, contour, leaps | Singing, fluid | Scale+chord tones, varied | Full density, expressiveness |

**Steady Figures:**
1. Root-root-fifth-root (AC/DC feel)
2. Root-fifth-octave-fifth (U2 feel)
3. Root-rest-fifth-root (breathing)
4. Root-root-root-approach (locked with lead-in)

---

## Density Levels

| Density | Note Density | Feel | Rhythm Pattern | Use When |
|---------|------------|------|-----------------|----------|
| **sparse** | ~25% fill | Minimal, spacious | Fewer, longer notes | Questions, ambient, fade |
| **medium** | ~50% fill | Balanced, conversational | Mixed note lengths | Verse, movement |
| **full** | ~80% fill | Active, energetic | More notes, rhythmic | Climax, peak, driving |

Density affects:
- Melody: how many notes per phrase
- Harmony: how often chords articulate
- Rhythm: how many hits per bar

---

## Harmonic Rhythm (Density for Harmony Track)

Same as density (sparse/medium/full), but controls *how the chord voices*.

- **sparse:** Chord hits once or twice per bar
- **medium:** Chord hits on major beats
- **full:** Chord articulates every beat or faster

---

## Percussion Patterns

| Pattern | Feel | Tempo Range | Use When |
|---------|------|-------------|----------|
| **four_on_floor** | 4/4 beat on 1,2,3,4 | Medium-fast | Driving, electronic |
| **off_beat** | Syncopated, hip-hop feel | Medium-fast | Groove, modern |
| **sparse_kicks** | Minimal kick hits | Slow-medium | Ambient, questioning |
| **tight_snare** | Snare on 2 & 4 | Medium-fast | Rock, tight feel |
| **ghost_notes** | Ghost fills underneath | Any | Textural, layered |

---

## Arcs (Emotional Trajectory)

| Arc | Curve | Feel | Use When |
|-----|-------|------|----------|
| **fade_in** | Slow entrance | Arriving, appearing | Opening, threshold |
| **swell** | Crescendo to middle | Building, growing | Movement, intensity |
| **breath** | Swell then gentle recede | Natural breathing | Recognition, reflection |
| **fade_out** | Diminuendo exit | Leaving, disappearing | Closing, settling |

Arc controls:
- Velocity curve over section
- Density intensity (if implemented)
- Presence in mix

---

## Chord Symbols

### Quality (Auto-Derived from Mode/Degree)
- **major** — root + major third + fifth
- **minor** — root + minor third + fifth
- **diminished** — root + minor third + flat 5
- **major7** — major + major 7
- **minor7** — minor + minor 7
- **dominant7** (V in major/minor)
- etc.

### Alterations (Roman Numeral Prefixes)
- `IV` — fourth degree, natural quality
- `bIV` — fourth degree lowered (borrowed from parallel minor)
- `#VI` — sixth degree raised (chromatic)
- `viidim` — seventh degree, diminished quality
- `bVImaj7` — sixth lowered, major 7 quality

---

## Groove Templates

| Groove | Feel | Swing | Use When |
|--------|------|-------|----------|
| `swing` | Jazz-like, triplet shuffle | ~0.67 | Jazz, swing sections |
| (custom) | Manual beat placement | Manual | Experimental |

---

## Counterpoint Species (When Enabled)

| Species | Rules | Feel | Use When |
|---------|-------|------|----------|
| **free** | Mostly independent motion | Modern, flexible | Default, most uses |
| **first** | Note-against-note alignment | Strict, Renaissance | Classical, rigid |

### Counterpoint Registers
- **above** — counterpoint above melody
- **below** — counterpoint below melody (default)

### Dissonance Handling
- **none** — all consonances only
- **passing** — passing tones allowed
- **suspension** — suspensions allowed
- **free** — any dissonance

---

## Motif Transforms

| Transform | Effect | Preserves | Use When |
|-----------|--------|-----------|----------|
| **inversion** | Flip intervals (up↔down) | Contour shape | Variation, questioning |
| **retrograde** | Reverse the sequence | Length, rhythm | Reflection, return |
| **augmentation** | Double all durations | Interval pattern | Expanding, slowing |

Combine in `transform_pool` to create variation sets.

---

## Chord Notation in Progressions

```json
"progression": ["I", "IV", "V", "I"]
```

### Base Roman Numerals
- Uppercase = major/natural quality: `I`, `IV`, `V`
- Lowercase = minor/natural quality: `i`, `iv`, `v`

### Alterations
- `b` prefix = flat (lower by semitone): `bVI`, `bVII`
- `#` prefix = sharp (raise by semitone): `#IV`, `#vi`

### Quality Overrides (Optional)
- `maj7` — explicit major 7: `Imaj7`
- `m7` — explicit minor 7: `iim7`
- `dim` — diminished: `viidim`
- `m7b5` — half-diminished: `iim7b5`

---

## JSON Structure Template

```json
{
  "piece": {
    "title": "Composition Name",
    "theme": "theme_name",
    "tempo": 60,
    "notes": "Optional narrative...",
    "sections": [
      {
        "name": "section_name",
        "bars": 16,
        "progression": ["I", "IV", "V", "I"],
        "chord_bars": [4, 4, 4, 4],
        "density": "medium",
        "harmony_rhythm": {
          "density": "medium",
          "groove": "swing",
          "swing": 0.67,
          "humanize": 0.1
        },
        "melody": "lyrical",
        "bass_style": "walking",
        "arc": "swell",
        "counterpoint": {
          "species": "free",
          "register": "below",
          "dissonance": "passing",
          "velocity": 54
        },
        "drums": "four_on_floor",
        "notes": "Section description..."
      }
    ]
  }
}
```

---

## JSON Structure Template (Theme)

```json
{
  "theme": {
    "name": "Theme Name",
    "key": "C",
    "mode": "ionian",
    "tempo": { "min": 50, "max": 80 },
    "motif": {
      "name": "motif_name",
      "intervals": [2, -1, 3, -2],
      "rhythm": [1.0, 0.5, 0.5, 1.0],
      "transform_pool": ["inversion", "retrograde", "augmentation"],
      "notes": "Motif description..."
    },
    "palette": {
      "harmony": "strings",
      "melody": "warm_pad",
      "bass": "cello",
      "counterpoint": "strings"
    },
    "notes": "Theme narrative..."
  }
}
```

---

## Statefulness Context (Automatic, Internal)

When a melody/bass/counterpoint generator runs, it receives:

```python
context = {
    "chord_index": 1,           # Which chord (0-indexed)
    "total_chords": 6,          # Total chords in section
    "next_chord": VoicedChord,  # The next chord object
    "next_chord_root": "vi",    # Next chord's root name
    "bars_in_this_chord": 2.0,  # Duration of current chord
    "bars_in_next_chord": 3.0,  # Duration of next chord
    "section_name": "bloom",    # Section name
}
```

**Used by:** Melody (lyrical especially) biases toward next chord tones at phrase end.

---

## Practical Decision Tree

**Starting a new section, what do I choose?**

1. **What's the emotional role?**
   - Opening → arc: fade_in, density: sparse
   - Building → arc: swell, density: medium→full
   - Peak → arc: swell, density: full
   - Closing → arc: fade_out, density: sparse

2. **What melody behavior?**
   - Intimate, floating → sparse
   - Moving, warm → lyrical
   - Experimental, wandering → generative
   - Developing, climax → develop

3. **What bass motion?**
   - Static, ambient → pedal or root_only
   - Gentle movement → root_fifth
   - Driving motion → walking or steady
   - Expressive second melody → melodic

4. **What chords?**
   - Diatonic? Write: `I IV V I`
   - Borrowed from minor? Write: `iv` (lowercase)
   - Chromatic alteration? Write: `bVI` or `#IV`
   - Deceptive moment? Write: `V bVI` (the jump)

5. **Test it.** Generate. Listen. Iterate.

---

## Quick Reference: What Changes the Sound Most?

1. **Mode** — Fundamental tonality (ionian vs. phrygian is huge)
2. **Bass style** — Pedal vs. walking changes everything
3. **Melody behavior** — Sparse vs. full density
4. **Progression** — Diatonic vs. chromatic chords
5. **Arc** — Fade vs. swell, natural dynamics
6. **Density** — Sparse vs. full articulation

Start with these. Forget grove/swing until you have the basics right.

---

## Notes for Future Expansion

- Form awareness: allow sections to auto-adjust behavior based on role
- Harmonic function: v knows it wants i (but not forced)
- Voice-leading constraints: melody aware of bass, avoiding parallel fifths
- Stateful prosody: stress patterns evolve with arc
- Phrase boundaries: from linguistic or harmonic structure, not arbitrary bars
