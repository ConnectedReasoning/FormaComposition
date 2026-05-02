# FormaComposition

**User Manual — Revision 3**

JSON-driven MIDI Generation Engine

Connected Reasoning · April 2026

---

## 1 — Overview

FormaComposition is a Python-based MIDI generation engine that automates
music theory decisions — chord voicing, scale-aware note selection,
voice leading, groove, and dynamics — while keeping all compositional
intent in a pair of JSON files. The engine writes a multi-track MIDI
file that you assign to instruments in Logic Pro.

### Architecture at a Glance

| **Layer** | **Responsibility** |
|---|---|
| theme.json | Key, mode, tempo range, seed motif, pitch phrase, rhythm phrase, colour palette |
| piece.json | Sections (or song form), progressions, bar counts, voice settings |
| generator.py | Assembles all voices, writes .mid file |
| harmony.py | Chord voicing, voice leading, inversions |
| melody.py | Four melodic behaviours over chord tones / motif transforms |
| bass.py | Seven bass styles (root, fifth, walking, steady, melodic, pulse, pedal) |
| rhythm.py | 11 groove templates + swing + velocity arcs |

| percussion.py | 5 drum patterns with velocity and arc |
| motif.py | Motif data type + 7 Bach-style transforms |
| context.py | SectionContext (cross-voice) + PieceContext (cross-section memory) |
| rhythm_extract.py | Imports hand-played MIDI loops → JSON rhythm patterns |

### MIDI Track Layout

| **Track** | **Name** | **MIDI Channel** | **Purpose** |
|---|---|---|---|
| 0 | Metadata | — | Tempo, time signature |
| 1 | Melody | Ch 1 (0) | Lead melodic line |
| 2 | Counterpoint | Ch 2 (1) | Optional second melodic voice |
| 3 | Harmony | Ch 3 (2) | Voiced chords |
| 4 | Bass | Ch 4 (3) | Bass line |
| 5 | Drums | Ch 10 (9) | Percussion (GM drum map) |

> **NOTE:** No GM program_change messages are written. Assign Arturia
> instruments in Logic Pro after importing the MIDI.

---

## 2 — Command-Line Usage

```
# Single piece
python main.py theme.json piece.json

# Custom output path
python main.py theme.json piece.json --output ./output/name.mid

# Batch: multiple pieces → one output directory
python main.py theme.json p1.json p2.json --outdir ./album/

# Dry-run: show piece info without generating
python main.py theme.json piece.json --info
```

| **Flag** | **Short** | **Description** |
|---|---|---|
| --output PATH | -o | Output .mid file path (single piece only) |
| --outdir DIR | -d | Output directory for batch generation |
| --info | -i | Display piece structure summary without generating |

### rhythm_extract.py — Import Hand-Played Rhythms

Play a rhythm in Logic Pro, export the MIDI region, then run:

```
# Auto-detect pattern length
python rhythm_extract.py groove.mid

# Specify exact length in beats
python rhythm_extract.py groove.mid --beats 4

# Extract from a specific track (0-indexed)
python rhythm_extract.py groove.mid --track 0 --name melody_rhythm

# Quantize to 16th notes (default) or 8th
python rhythm_extract.py groove.mid --quantize 16

# Output bare JSON ready to paste
python rhythm_extract.py groove.mid --json-only
```

The output is a `rhythm_pattern` block to paste into your section JSON (see §4.8).

---

## 3 — theme.json Reference

The theme defines the invariant musical identity of a piece or album.
One theme file can serve many piece files.

```json
{
  "name": "Still Cove",
  "key": "D",
  "mode": "dorian",
  "tempo": { "min": 65, "max": 72 },

  // Option A — explicit motif (rhythm propagates to all voices)
  "motif": {
    "name": "cove_theme",
    "intervals": [2, -1, 3, -2],
    "rhythm": [1.0, 0.5, 0.5, 1.0],
    "transform_pool": ["inversion","retrograde","augmentation"]
  },
}
```

| **Field** | **Type** | **Required** | **Description** |
|---|---|---|---|
| key | string | ✓ | Root note: C, D, Eb, F#, etc. |
| mode | string | ✓ | Scale mode (see §3.1) |
| tempo | object | ✓ | { min: BPM, max: BPM } |
| motif | object | — | Explicit motif definition (see §3.2) |
| name | string | — | Label shown in --info output |
| palette | object | — | Default voice settings for pieces using this theme |

### 3.1 — Valid Modes

| **Mode** | **Character** | **Example Use** |
|---|---|---|
| ionian | Major — bright, resolved | Happy, triumphant, folk |
| dorian | Minor with raised 6th — soulful | Jazz, Celtic, ambient |
| phrygian | Minor with flat 2nd — dark, Spanish | Cinematic tension, flamenco |
| lydian | Major with raised 4th — floating | Film scores, wonder, Eno-esque |
| mixolydian | Major with flat 7th — bluesy | Rock, country, anthem |
| aeolian | Natural minor — melancholic | Pop ballads, classical |
| locrian | Diminished root — unstable | Extreme tension; handle carefully |

### 3.2 — Motif Definition

The motif is the rhythmic and melodic identity of a piece. When a
`rhythm` field is present, that rhythm propagates automatically to all
three pitched voices — melody, harmony, and bass — at different
articulation densities. This means a single motif rhythm gives the whole
piece a shared rhythmic fingerprint without any per-section configuration.

**Articulation levels:**

| **Voice** | **Articulation** | **Behaviour** |
|---|---|---|
| Melody | Full | Every onset in the motif cycle. Pronounces the rhythm. |
| Harmony | Stressed | Onsets whose duration ≥ the median duration in the cycle. Re-articulates on strong beats; sustains between them. |
| Bass | Anchor | First onset of each cycle only. One root note per cycle, sustaining to the next hit. |

**Fields:**

| **Field** | **Type** | **Description** |
|---|---|---|
| name | string | Identifier for the motif |
| intervals | int[] | Semitone steps between successive notes. [2, -1, 3] = up 2, down 1, up 3. |
| rhythm | float[] | Duration in beats per note. Must match interval count — auto-trimmed/padded. When present, drives rhythm for all voices (see articulation table above). |
| velocities | float[] | Per-note velocity scale (0.0–1.0). Optional; defaults to 0.8 per note. Must match interval count if provided. |
| transform_pool | string[] | Transforms used during `develop` behaviour (see §3.3) |

> **NOTE:** `rhythm` length must equal `intervals` length. The Motif
> system enforces this — extra values are trimmed, missing values are
> padded with 1.0. Always match lengths explicitly to avoid surprises.

### 3.3 — Motif Transforms (used in develop behaviour)

| **Transform** | **Description** |
|---|---|
| inversion | Flip all intervals: [2, -1, 3] → [-2, 1, -3] |
| retrograde | Reverse interval order |
| augmentation | Double all note durations |
| diminution | Halve all note durations |
| transpose_up | Shift root pitch up by a diatonic step |
| transpose_down | Shift root pitch down by a diatonic step |
| shuffle | Randomly permute interval order |

---

## 4 — piece.json Reference

A piece file defines the composition structure. Two form types are
supported: narrative (default) and song.

### 4.1 — Top-Level Fields

| **Field** | **Type** | **Default** | **Description** |
|---|---|---|---|
| title | string | "" | Piece name (appears in MIDI track metadata) |
| form_type | string | "narrative" | "narrative" or "song" |
| tempo | number | theme midpoint | BPM for this piece. Must be within theme tempo range. |
| seed | number | 42 | Base random seed. Change to get different-feeling outputs from the same JSON. |
| sections | array/dict | required | Narrative: ordered array. Song: named dict of section definitions. |
| form | array | song only | Ordered list of section names / variation dicts (song form only). |

### 4.2 — Narrative Form (default)

Sections play in order, once.

```json
{
  "title": "Still Cove",
  "tempo": 68,
  "seed": 7,
  "sections": [
    {
      "name": "intro",
      "bars": 8,
      "progression": ["i", "VII", "iv", "i"],
      "density": "sparse",
      "melody": "sparse",
      "bass_style": "root_only",
      "arc": "fade_in"
    },
    {
      "name": "main",
      "bars": 16,
      "progression": ["i", "VII", "iv", "V"],
      "density": "medium",
      "melody": "lyrical",
      "bass_style": "walking",
      "arc": "swell"
    }
  ]
}
```

### 4.3 — Song Form

Define named section templates in `sections` (a dict), then sequence
them in `form`. The same section definition plays each time it appears;
use `variation` (0.0–1.0) to introduce controlled randomness.

```json
{
  "title": "City Grid",
  "form_type": "song",
  "tempo": 98,
  "form": [
    "intro",
    "verse",
    "chorus",
    "verse",
    { "section": "chorus", "variation": 0.3 },
    "bridge",
    "chorus",
    "outro"
  ],
  "sections": {
    "intro":  { "bars": 8,  "progression": [...], ... },
    "verse":  { "bars": 16, "progression": [...], ... },
    "chorus": { "bars": 8,  "progression": [...], ... },
    "bridge": { "bars": 8,  "progression": [...], ... },
    "outro":  { "bars": 8,  "progression": [...], ... }
  }
}
```

### 4.4 — Section Fields

| **Field** | **Type** | **Default** | **Description** |
|---|---|---|---|
| name | string | required | Label shown in --info and MIDI track names |
| bars | number | required* | Total bar count. Derived from chord_bars sum if present. |
| progression | string[] | required | Roman numeral chord sequence: ["I", "IV", "V", "I"] |
| chord_bars | number[] | — | Per-chord bar durations. Length must match progression. Overrides bars. |
| density | string | "medium" | Overall note density: sparse / medium / full |
| melody | string | "generative" | Melody behaviour (see §4.5) |
| bass_style | string | "root_only" | Bass pattern (see §4.6). Bypassed when motif rhythm is active (bass plays chord roots at motif anchor timing). |
| arc | string | "swell" | Velocity shape: flat / swell / fade_in / fade_out / breath |
| groove | string | — | Groove template for all voices (see §4.7) |
| swing | number | 0.0 | Swing ratio 0.0–0.75 (0.67 = triplet feel) |
| beats_per_bar | number | 4 | Time signature numerator |
| harmony_rhythm | object | — | Separate rhythm control for harmony voice (see §4.8) |
| rhythm_pattern | object | — | Hand-played melody rhythm (highest priority for melody) |
| drums | string/object | — | Drum pattern (see §4.9) |
| counterpoint | boolean | false | Enable counterpoint voice |

> **NOTE:** \*bars is required unless chord_bars is provided. When
> chord_bars is present, bars is ignored and the section length is
> computed from sum(chord_bars).

### 4.5 — Melody Behaviours

| **Behaviour** | **Description** |
|---|---|
| generative | Step-wise motion through scale tones. Active, fills space. |
| lyrical | Chord tones with occasional passing tones. Singable, connected. |
| sparse | Long tones on chord roots / fifths. Minimal, ambient. |
| develop | Applies Bach-style transforms from the theme motif's transform_pool. Requires motif in theme. |

### 4.6 — Bass Styles

| **Style** | **Description** |
|---|---|
| root_only | Single root note per chord. Minimal; great for sparse sections. |
| root_fifth | Alternates root and fifth. Classic two-feel. |
| walking | Scale-wise quarter notes. Root on beat 1, chord tones on strong beats. |
| steady | Short locked figure that repeats per chord. The bass IS the groove. |
| melodic | Expressive line through scale tones with contour and leaps. |
| pulse | Driving eighth-note pattern. Dense, rhythmic. |
| pedal | Sustained root note held across bar boundaries. Droning. |

> **NOTE:** When a motif with a `rhythm` field is set in theme.json,
> `bass_style` is bypassed. The bass plays chord roots at the motif's
> anchor timing (one hit per cycle, sustained to the next). To restore
> style-based bass behaviour, set `harmony_rhythm: {note_duration: ...}`
> or remove the `rhythm` field from the motif.

### 4.7 — Groove Templates

Grooves define where notes land within a bar. Applied to all voices when
set at section level. Can also be set independently in `harmony_rhythm`.

| **Groove** | **Feel** | **Use Case** |
|---|---|---|
| straight | Even grid — no displacement | Clinical, mechanical, classical |
| push | Notes arrive slightly early | Urgency, tension, forward drive |
| backbeat | Emphasis on beats 2 and 4 | Pop, rock, R&B |
| syncopated | Off-beat emphasis, gaps on downbeats | Funk, jazz, Latin |
| halftime | Groove feels at half the tempo | Hip-hop, slow burn |
| shuffle | Triplet-based swing — don't add swing on top | Blues, jazz, swing |
| broken | Irregular gaps, suspended feel | Ambient, experimental |
| clave | 3-2 or 2-3 African/Afro-Cuban rhythm | Latin, world music |
| waltz | 3/4 emphasis (beats 1-2-3) | Classical, folk, ballad |
| offbeat | Sustained off-beat landing points | Reggae, ska |
| driving | Dense, consistent eighth-note feel | Rock, cinematic build |

> **NOTE:** shuffle has triplet swing baked in. Setting swing on top of
> shuffle will double-apply and sound wrong.

### 4.8 — harmony_rhythm Block

Controls harmony voice rhythm independently of the section groove.
Priority chain (highest first):

1. **harmony_pattern** — hand-played whole-section pattern
2. **note_duration** — single sustained event per chord
3. **Motif rhythm** — if theme motif has a `rhythm` field; re-articulates at stressed onsets (durations ≥ median)
4. **Density-based grid fallback**

```json
"harmony_rhythm": {
  "density": "medium",     // sparse | medium | full
  "groove": "backbeat",    // any groove template
  "swing": 0.2,            // 0.0–0.75
  "note_duration": "quarter" // whole | half | quarter | eighth
}
```

Setting `note_duration` (priority 2) overrides the motif rhythm (priority 3)
for harmony. Use this when you want held chords regardless of the motif's
rhythmic character.

To use a hand-played pattern, paste the output of rhythm_extract.py as
`harmony_pattern` at section level:

```json
"harmony_pattern": {
  "onsets":    [0.0, 1.0, 1.5, 2.5, 3.0],
  "durations": [0.75, 0.5, 0.75, 0.5, 1.0],
  "velocities":[0.9, 0.6, 0.8, 0.5, 0.7],
  "length_beats": 4.0
}
```

### 4.9 — Drums

Drums are optional. Pass a pattern name (string) or an object for fine
control:

```json
// Simple — just a pattern name
"drums": "backbeat"

// With velocity override
"drums": {
  "pattern": "four_on_floor",
  "velocity": 85
}
```

| **Pattern** | **Description** |
|---|---|
| four_on_floor | Kick on every beat. Classic house/dance. |
| backbeat | Kick on 1 & 3, snare on 2 & 4. Standard pop/rock. |
| halftime | Sparse kick/snare, half-time feel. Hip-hop, trap. |
| minimal | Barely-there hits. Ambient, cinematic. |
| sideclick | Rimshot / sidestick pattern. Jazz, bossa. |

> **NOTE:** velocity range is 0–127. Default is 80.

---

## 5 — Chord Progressions & Roman Numeral Notation

Progressions are arrays of Roman numeral strings. The engine resolves
these relative to the theme's key and mode.

```
"progression": ["I", "IV", "V", "I"]      // major diatonic
"progression": ["i", "VII", "iv", "V"]    // minor / dorian mix
"progression": ["I", "V/V", "V", "I"]     // secondary dominant
"progression": ["Imaj7", "IVmaj7", "V7"]  // jazz extensions
```

### 5.1 — Quality Suffixes

| **Suffix** | **Quality** | **Example** |
|---|---|---|
| (none) | Triad — major or minor per mode | I, iv |
| maj7 | Major seventh | Imaj7 |
| 7 | Dominant seventh | V7 |
| m7 | Minor seventh | iim7 |
| dim | Diminished triad | viidim |
| aug | Augmented triad | IIIaug |
| sus2 | Suspended 2nd | Isus2 |
| sus4 | Suspended 4th | Vsus4 |

### 5.2 — chord_bars: Unequal Chord Durations

By default each chord in the progression gets equal time. Use
`chord_bars` to assign different bar counts per chord:

```json
"progression": ["I", "V", "vi", "IV"],
"chord_bars":  [4,   2,   2,    4  ]
// Total = 12 bars. bars field is ignored when chord_bars is present.
```

---

## 8 — Context System

The context system gives voices the ability to listen to each other and
remember across sections.

### 8.1 — SectionContext (within a section)

Updated sequentially as each voice generates. Downstream voices read it
to:

- Avoid register collisions with the melody or counterpoint
- Lock rhythmically to the bass or drums
- Apply contrary motion relative to the previous voice's contour

### 8.2 — PieceContext (cross-section)

Carries a VoiceSnapshot forward from each section. Each snapshot
records:

| **Field** | **Description** |
|---|---|
| last_pitch | MIDI note number of the last sounding note |
| pitch_center | Mean MIDI pitch — the voice's registral home for that section |
| pitch_low / pitch_high | Register extremes |
| ending_contour | ascending / descending / static / peaked / troughed |
| achieved_density | Fraction of available slots that received a note (0.0–1.0) |
| avg_note_duration_beats | Mean note duration — short = active, long = sustained |
| rhythmic_profile | sustained / steady / syncopated / sparse |

---

## 9 — Validation

Validation runs automatically before every generation. Hard errors stop
generation; warnings print and continue.

### 9.1 — Theme Validation

- `key`, `mode`, `tempo` are required
- `tempo.min` must be ≤ `tempo.max`

### 9.2 — Piece Validation

- Every section must have `progression` and `bars` (or `chord_bars`)
- `chord_bars` length must match `progression` length
- All enum fields (density, melody, bass_style, arc, groove, drum pattern) must be valid
- `swing` must be 0.0–0.75
- `drums` velocity must be 0–127
- Song form: every name in `form` array must exist in `sections` dict
- Song form: `variation` must be 0.0–1.0

> **NOTE:** Run `python main.py theme.json piece.json --info` to validate
> and preview structure without generating MIDI.

---

## 10 — Seed System

FormaComposition is deterministic given the same JSON and seed. Change
the seed to get different-feeling output from the same composition.

```json
"seed": 42   // default — backward-compatible with all existing pieces
"seed": 7    // try different values to shift feel
"seed": 1001 // still the same structure, different micro-decisions
```

In song form, the same section definition played twice uses a different
seed offset per occurrence (`base_seed + section_index * 10`), so
repeated sections have variation while remaining musically coherent.

---

## 11 — Complete Example: Ambient Piece

**theme.json**

```json
{
  "name": "Ember Grove",
  "key": "G",
  "mode": "dorian",
  "tempo": { "min": 60, "max": 72 },
  "motif": {
    "name": "ember",
    "intervals": [3, -1, 2, -3],
    "rhythm": [1.0, 0.5, 0.5, 2.0],
    "transform_pool": ["inversion", "retrograde", "augmentation"]
  }
}
```

With this theme, the motif rhythm `[1.0, 0.5, 0.5, 2.0]` (4-beat cycle)
propagates to all voices automatically:

- **Melody** pronounces all four durations per cycle
- **Harmony** re-articulates on the 1.0 and 2.0 beats (≥ median 0.75), sustains through the short 0.5 syllables
- **Bass** hits on beat 0 of each 4-beat cycle, sustaining to the next hit

**piece.json**

```json
{
  "title": "The Circle at Ember Grove",
  "tempo": 65,
  "seed": 12,
  "sections": [
    {
      "name": "opening",
      "bars": 8,
      "progression": ["i", "VII", "III", "VII"],
      "density": "sparse",
      "melody": "sparse",
      "arc": "fade_in"
    },
    {
      "name": "body",
      "bars": 16,
      "progression": ["i", "VII", "iv", "V"],
      "chord_bars": [4, 4, 4, 4],
      "density": "medium",
      "melody": "lyrical",
      "arc": "swell",
      "groove": "backbeat"
    },
    {
      "name": "develop",
      "bars": 12,
      "progression": ["i", "iv", "VII", "III"],
      "density": "full",
      "melody": "develop",
      "arc": "swell",
      "drums": "minimal"
    },
    {
      "name": "close",
      "bars": 8,
      "progression": ["i", "VII", "i"],
      "density": "sparse",
      "melody": "sparse",
      "arc": "fade_out"
    }
  ]
}
```

> **NOTE:** `bass_style` is omitted from all sections. Since the theme
> motif has a `rhythm` field, the bass voice is automatically driven by
> the motif anchor timing — one root note per 4-beat cycle, sustained.
> Specifying `bass_style` would be ignored when motif rhythm is active.

---

## 12 — Recommended Workflow

### New Piece

- Start from a single-section template. Generate and listen.
- Internalize what you hear. Promote any caught fragment to a motif in
  theme.json, including its rhythm.
- Append the next section to the JSON. Repeat.
- Use `--info` to preview bar counts and timing before committing a
  generation.
- Bounce to audio and walk with it. Your ears are the final validator.

### Rhythm Capture

- Play a rhythm into Logic Pro on the Keystep.
- Export the MIDI region.
- Run `rhythm_extract.py` and paste the JSON block into your section as
  `rhythm_pattern` (melody) or `harmony_pattern` (harmony).
- Hand-played rhythm takes priority over all algorithmic groove
  templates and motif rhythm when present.

### AI-Assisted Composition

Use LLMs (Claude for design decisions, Haiku for well-defined
implementation) to generate piece JSON from a constraint-informed
prompt. Good prompt ingredients:

- Key, mode, target tempo
- Arc description (e.g. 'starts sparse, builds to full, fades')
- Specific emotion or reference track
- Target duration in minutes
- Bass style and groove character preferences

---

## 13 — Quick Reference Tables

### All Valid Enums

| **Field** | **Valid Values** |
|---|---|
| mode | ionian · dorian · phrygian · lydian · mixolydian · aeolian · locrian |
| density | sparse · medium · full |
| melody | generative · lyrical · sparse · develop |
| bass_style | root_only · root_fifth · walking · steady · melodic · pulse · pedal |
| arc | flat · swell · fade_in · fade_out · breath |
| groove | straight · push · backbeat · syncopated · halftime · shuffle · broken · clave · waltz · offbeat · driving |
| swing | 0.0 – 0.75 (0.0 = straight · 0.67 = triplet · 0.75 = heavy) |
| drums pattern | four_on_floor · backbeat · halftime · minimal · sideclick |
| harmony_rhythm note_duration | whole · half · quarter · eighth |
| motif transform_pool | inversion · retrograde · augmentation · diminution · transpose_up · transpose_down · shuffle |

### Common Errors

| **Error Message** | **Fix** |
|---|---|
| chord_bars has N entries but progression has M | Make chord_bars and progression the same length |
| chord_bars sum (X) does not match bars (Y) | Remove bars or correct sum(chord_bars); chord_bars wins |
| melody behavior 'X' invalid | Check spelling against valid list (§12 above) |
| drum pattern 'X' invalid | Use one of the 5 valid pattern names |
| swing X out of range | Keep swing between 0.0 and 0.75 |
| form references undefined section 'X' | Add 'X' to the sections dict, or fix the typo in form array |
| piece.tempo outside theme range | Warning only; adjust piece.tempo or widen theme tempo range |

---

*FormaComposition · Connected Reasoning · Rev 3 · April 2026*
