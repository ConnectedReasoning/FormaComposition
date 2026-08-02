# FormaComposition JSON Cheat Sheet (v10 — diatonic-motif migration + transform_pool fixes reflected; see Motif section)

One file per piece (`piece_*.json`) — no separate `theme_*.json`. `key`/`mode`/`motif`/
`motifs`/`tempo` live on the piece top level alongside `title`/`sections`/`form`.
`extra="allow"` at piece/motif level unless noted; unknown keys warn, not error.

---

## Theme fields (on the piece file)

| Field | Type | Required | Values |
|---|---|---|---|
| `key` | string | yes | `C, C#, D, D#, E, F, F#, G, G#, A, A#, B, Db, Eb, Gb, Ab, Bb` |
| `mode` | string | yes | `ionian, dorian, phrygian, lydian, mixolydian, aeolian, locrian` |
| `motif` | object | one of motif/motifs | see Motif section below |
| `motifs` | array | one of motif/motifs | array of motif objects — see Motif section below |
| `tempo` | object or int | yes | `{min,max}` or bare int |
| `name` | string | no | free text |

- `key`/`mode` at this level are not enum-checked by the engine, but the values above are the only real ones.
- If both `motif` and `motifs` are set, `motifs` wins.
- A bare int for `tempo` is auto-coerced to a fixed range.

### `tempo`
| Field | Values |
|---|---|
| `min` / `max` | 20–300, max ≥ min |

### `motif` / `motifs[]`
| Field | Type | Required | Values |
|---|---|---|---|
| `intervals` | array of int | yes | diatonic scale-degree steps (NOT semitones — migrated; see below) |
| `rhythm` | array of float | no | — |
| `transform_pool` | array | no, default `[]` | `original, inversion, retrograde, retrograde_inversion, augmentation, diminution, transpose_up, transpose_down, shuffle, expand, compress, sequence` |
| `velocities` | array of float | no | 0.0–1.0 |
| `name` | string | no | free text |
| `melodic_scale` | string | no | 7 standard modes, or `pentatonic_major`, `pentatonic_minor`, `blues` |

- `rhythm` is needed for `rhythm: "motif"`.
- **`intervals` are diatonic scale-degree steps**, resolved against the mode (or `melodic_scale`, if set) — not semitones. `[2, -1, 3]` means up 2 scale degrees, down 1, up 3. Every resulting note lands on a scale tone by construction; there's no separate quantization step to silently erase a small interval the way the old semitone contract could (a ±1-semitone neighbor-tone step could land exactly between two scale tones a whole-tone apart and snap back to where it started — the bug that motivated this migration). Chromatic alterations (borrowed chords, secondary-dominant coloring) are intentionally out of scope for this field — author those by hand in Logic after render.
- **All `transform_pool` values now genuinely work in `develop`**, including pitch variation: `inversion`, `retrograde`, `retrograde_inversion`, `transpose_up`, `transpose_down`, `shuffle`, `expand`, `compress`, `sequence` (harmony-aware), and `original` (explicit no-op). Earlier versions of this doc listed `transpose_up`/`transpose_down` as dead and `retrograde_inversion`/`expand`/`compress` as pitch no-ops — that was accurate at the time (a routing gap meant those names fell through to a silent no-op in `develop` specifically) and has since been fixed.
- **`augmentation`/`diminution` now genuinely stretch/compress real output**, not just an internally-computed value that got discarded — a statement using either drives its actual timing from the transformed (doubled/halved) rhythm, clamped to fit the available span exactly, rather than reusing the section's pre-built onset grid. Half as many notes at twice the length (augmentation) or twice as many at half the length (diminution), same total span.
- **`shuffle` reorders intervals + rhythm + rests together as one paired permutation** — a piece using `shuffle` may sound different from before this was fixed (pitch and rests used to be able to shuffle out of alignment; now they move as a unit).
- **`melodic_scale`** (optional): overrides which scale `intervals` walks for THIS motif's pitches, independent of the piece's harmonic `mode`. Chords/Roman-numeral resolution never read this field — harmony stays on the piece's `mode` regardless, so a piece can keep ordinary diatonic I–IV–V7 harmony while its melody walks a pentatonic/blues scale on top, which is the actual relationship blues melody has to its harmony (the two scales genuinely differ — that's what makes a blue note "blue"). Accepts the 7 standard modes too, not just pentatonic/blues. Omitted → melody uses the piece's `mode`, unchanged from before this field existed.
- `velocities` are multipliers, not raw MIDI velocity.

---

## Motif selection

Only the **primary** motif (`motifs[0]`, or `motif`) plays by default — no cycling, no randomization.

| Consumer | Default | Override |
|---|---|---|
| Bass (`bass_style: "motif"`) | always primary | none — hardwired |
| Melody (`rhythm: "motif"`) | primary | `voices[0].motif` |
| Harmony (`harmony_rhythm.rhythm: "motif"`) | primary | `harmony_rhythm.motif` |
| Counterpoint (free species) | none | `counterpoint[].motif` — rhythm only, never pitch |

- `transform_sequence` (piece-level) varies the primary's *transform* per section — doesn't change which motif plays.
- `melodic_variation: "isorhythmic"` is the only way to get pitch variety from the rest of the pool (rhythm stays anchored to primary, pitch redraws from other pool members).
- Section-level `motif`/`motifs` fields do nothing.
- Unknown motif name → validation error, not a render-time crash.

---

## PIECE (`piece_*.json`)

### Top level (PieceModel)
| Field | Type | Required | Values |
|---|---|---|---|
| `form` | array | song form only | array of `{section, exact_repeat}` — see Song form below |
| `form_type` | enum | no, default `narrative` | `narrative, song` |
| `sections` | array or dict | yes | array (narrative form) or dict (song form) |
| `seed` | int | no, default 42 | — |
| `title` | string | no | free text |
| `transform_sequence` | array | no | — |

- Each `form[]` entry's `section` must exist in `sections`.
- `transform_sequence` wraps if shorter than the section count.

### Section (SectionModel)
| Field | Type | Default | Values |
|---|---|---|---|
| `arc` | enum | `swell` | `swell, build, fade, fade_in, fade_out, plateau, decay, breath` — see Arc table |
| `bars` | float | 8 | — |
| `bass_rest_probability` | float | 0.0 | 0.0–1.0 |
| `bass_style` | enum | `root_fifth` | `root_fifth, walking, pedal, root_only, melodic, steady, pulse, motif` |
| `beats_per_bar` | int | 4 | 1–16 |
| `chord_bars` | array of float | — | — |
| `counterpoint` | object or array | — | see Counterpoint table below |
| `density` | enum | `medium` | `low, sparse, medium, full` |
| `drums` | string or object | — | see Drums table below |
| `fugal_techniques` | dict | — | — |
| `groove` | string | — | `straight, push, backbeat, syncopated, halftime, shuffle, broken, clave, waltz, offbeat, driving` |
| `harmony_pattern` | object | — | see `rhythm_pattern` / `harmony_pattern` table below |
| `harmony_rest_probability` | float | 0.0 | 0.0–1.0 |
| `harmony_rhythm` | object | — | see Harmony rhythm table below |
| `key` | string | — | `C, C#, D, D#, E, F, F#, G, G#, A, A#, B, Db, Eb, Gb, Ab, Bb` |
| `melodic_variation` | enum | — | `isorhythmic` |
| `melody` | enum or object | `generative` (bare) / `lyrical` (dict, unset `behavior`) | `lyrical, generative, sparse, develop` |
| `mode` | string | — | `ionian, dorian, phrygian, lydian, mixolydian, aeolian, locrian` |
| `note_length_range` | object | — | `{min, max, quantum?}` |
| `progression` | array of string | yes | Roman numerals, not enum-validated, no max length |
| `rest_probability` | float | 0.0 | 0.0–1.0 |
| `rhythm` | enum | yes | `motif, pattern, free` |
| `swing` | float | 0.0 | 0–1 |
| `voices` | array | — | up to 4 total — see Voices table below |

- `bass_rest_probability` is refused on `walking`/`melodic` bass styles.
- `bass_style: "motif"` needs a theme motif with `intervals`+`rhythm`. Swing on bass is only audible on `melodic`/`motif`.
- `chord_bars` must match `progression` length; tiles to fill `bars` if shorter.
- `counterpoint`: up to 3 voices; `voices[]` overrides if both set.
- `drums` string is a pattern name; object form uses the Drums table.
- `fugal_techniques.canon_interval` needs `canonic_imitation: true` or it's a no-op.
- `harmony_pattern` is required if `harmony_rhythm.rhythm: "pattern"`.
- `harmony_rest_probability` is a no-op under `sustain`.
- `harmony_rhythm` must be an object, not a bare string.
- `key`/`mode` here override the theme-level key/mode.
- `melodic_variation: "isorhythmic"` needs `rhythm: "motif"` + multi-motif pool + no lead motif override.
- `melody: "develop"` is lead-voice only — no-op on peer voices.
- `note_length_range` applies to melody + free-species counterpoint only; needs `rhythm: "free"`; ignored under `groove` or `pattern`/`motif` rhythm.
- `rest_probability` is melody only.
- `rhythm` (timing) is separate from `melody` (behavior).
- `swing` on bass is audible only via `melodic`/`motif` bass styles.

### Arc curves
| `arc` | Shape | Range |
|---|---|---|
| `swell` | quadratic rise | 0.75 → 1.10 |
| `build` | steeper rise | 0.70 → 1.20 |
| `fade` / `fade_out` | linear fall | 1.00 → 0.65 |
| `fade_in` | linear rise | 0.65 → 1.00 |
| `breath` | arch, peaks mid | 0.85 → 1.15 → 0.85 |
| `plateau` | flat | 1.0 |
| `decay` | gentle fall | 0.95 → 0.70 |

Cross-section blending is always on (up to 4 bars / 25% of section) — not disableable.

### `harmony_rhythm`
| Field | Values |
|---|---|
| `density` | `low, sparse, medium, full` |
| `groove` | must be a valid groove name — see Section `groove` values |
| `motif` | object — see Motif section |
| `rhythm` | `motif, pattern, sustain, free` |
| `swing` | 0–1 |
| `transform_imitation` | do not set |

- `density` has no effect under `sustain`.
- `groove` is inert under `sustain`/`motif`, audible only under `free`.
- `motif` is harmony's own motif, independent of melody's; only resolves under `rhythm: "motif"`.
- `rhythm: "sustain"` = zero internal motion.
- `transform_imitation: "strict"` hard-crashes at render time.

### `counterpoint[]`
| Field | Default | Values |
|---|---|---|
| `canon_offset` | 0.0 | — |
| `dissonance` | `passing` | `none, passing, neighbor, free` |
| `groove` | — | valid groove name — free species only |
| `motif` | — | object — free species only |
| `note_length_range` | — | `{min, max, quantum?}` — free species only |
| `register` | `below` | `above, below` |
| `rhythm_density` | `medium` | `low, sparse, medium, full` — free species only |
| `species` | `free` | `free, first, second, third, fourth, fifth` |
| `velocity` | 58 | 1–127 |

- `register` (`above`/`below`) is relative to melody's rendered range, not a fixed band.
- Of the `species` values, only `free`/`first` are implemented — others fail at validation.
- `motif` on a counterpoint voice affects rhythm only, never pitch.
- Cap: 3 voices max.

### `voices[]` — up to 4 total (1 lead + 3 peers)
| Field | Default | Values |
|---|---|---|
| `behavior` | `lyrical` | `lyrical, generative, sparse, develop` |
| `canon_offset` | 0.0 | — |
| `dissonance` | `passing` | `none, passing, neighbor, free` |
| `motif` | — | object |
| `register` | `mid` | `high, mid, low_mid, low, above, below` + SATB names |
| `rest_probability` | — | 0.0–1.0 |
| `species` | — | `free, first, second, third, fourth, fifth` |
| `velocity` | 64 | 1–127 |

- `behavior: "develop"` is a no-op on peer voices (`voices[1:]`).
- `motif` only applies to the lead voice (`voices[0]`).
- `register` is absolute (unlike counterpoint's relative `above`/`below`).
- `rest_probability` overrides the section default.
- Setting `species` switches the voice onto the counterpoint path.
- Cap: 4 voices max.

### `drums`
| Field | Default | Values |
|---|---|---|
| `density` | inherits section | `low, sparse, medium, full` |
| `groove` | inherits section | valid groove name |
| `pattern` | `four_on_floor` | `four_on_floor, backbeat, halftime, minimal, sideclick` |
| `swing` | inherits section | 0–1 |

### `rhythm_pattern` / `harmony_pattern`
| Field | Required | Values |
|---|---|---|
| `durations` | yes | array, matches `onsets` length |
| `length_beats` | no, default 8.0 | — |
| `onsets` | yes | array |
| `velocities` | no | 0.0–1.0 |

### Song form: `form[]`
| Field | Default | Values |
|---|---|---|
| `exact_repeat` | `false` | boolean |
| `section` | required | must exist in `sections` |
| `variation` | — | removed — hard validation error if set |

---

## Register reference

| Name | MIDI range |
|---|---|
| `soprano` | 60–84 |
| `alto` | 55–79 |
| `tenor` | 48–72 |
| `baritone` | 43–67 |
| `bass` | 36–60 |
| `mid` | = soprano (60–84) |
| `low_mid` | = tenor (48–72) |
| `high` | 64–88 (not soprano) |
| `low` | 33–57 (not bass) |

Default melody register: 60–84. Counterpoint's `above`/`below` is relative to melody's actual range, not one of these fixed bands.

---

## Dynamics stacking

`final_velocity = velocity × groove_accent × arc_scale`, clamped 40–120.

| Layer | Field | Range |
|---|---|---|
| Base | `velocity` | ceiling, not fixed |
| Arc | `arc` | 0.6–1.25× |
| Groove | baked into template | ~0.4–1.0× |

---

## Harmonic structure

| Concept | Field | Values |
|---|---|---|
| Chord sequence | `progression` | list of Roman numerals, not enum-validated |
| Per-chord duration | `chord_bars` | must match `progression` length |
| No length cap | — | keep ≤10 chords/section (seed-collision risk above that, unless `rhythm: "sustain"`) |

---

## Anti-slop guidelines

Legal ≠ memorable. `lint.py` catches broken settings; `slop_metrics.py` (auto-runs via `main.py`) catches boring ones.

**Core finding:** rhythm repeats 84–100%, pitch contour repeats 0–96% (median 13%). Backwards. Fix: make pitch recur, let rhythm breathe.

### Piece-tier metrics (these discriminate)
| Metric | Threshold | Fix |
|---|---|---|
| Motif identity | FAIL <10%, WARN <25% | `develop` on `voices[0]`; a smaller `transform_pool` gives tighter, more recognizable identity (all 10 real transforms now vary pitch or rhythm — this is a variety-vs-recognizability choice, not working around a dead transform) |
| Leap profile | FAIL ≥35%/10%, WARN ≥28%/5% | narrow `register`; prefer `develop` over `lyrical`/`generative` |
| Harmony mass | FAIL ≥4.0×, WARN ≥3.0× | move toward `rhythm: "sustain"`, or drop `density` |

Always check section-level, not just OVERALL — an average can hide one bad section.

### Reading the section table
|Column| Meaning|Direction|
|---|---|---|
|notes|lead-melody note count in that slice|	below ~10, shown as - — too short to judge|
|motif|	% of 4-note pitch-contour shapes that recur in the slice — "does the tune have a hook"	higher = better|
|leap|	% of intervals ≥ a 4th — "does it move by step or by jump"|	lower = better|
|harmony|chord events ÷ melody events — "does the pad outweigh the tune"	|lower = better, <3× is fine|

### Engine-wide constants (not per-piece fixes)
- Rhythm stencil sits at 84–100% everywhere — `note_length_range` is the only lever and it's unset catalog-wide.
- Register span is 24 semitones in most renders — set it explicitly, widen once at the climax.
- Inner-voice flatness — vary `velocity` per section; free-species voices need their own `note_length_range`.

### Common problems
| Symptom | Fix |
|---|---|
| Melody forgettable, no hook | `develop` on `voices[0]` |
| Motif never returns | prune `transform_pool` |
| Melody disjunct, hits ceiling early | narrow `register` |
| Chords bury the tune | `rhythm_rhythm: "sustain"` or lower density, or give harmony its own motif |
| Inner voices robotic | vary velocity, add `note_length_range` |
| Piece passes but feels uneven live | check the section table, not just OVERALL |
| Two renders sound identical | `slop_metrics.py --summary` flags identical fingerprints |

### Running it
Auto-runs via `main.py`, prints a per-section table. For full explanations on one piece:
```bash
python slop_metrics.py output/piece.mid --verbose --piece compositions/piece.json
```
Motif-identity reuse is unreliable under ~40 notes — treat WARN on a short section as "worth a listen," not a verdict.

---

## Quick decision guide

| You want... | Set this |
|---|---|
| Held ambient pad, zero motion | `harmony_rhythm.rhythm: "sustain"` |
| Harmony with its own motivic identity | `harmony_rhythm.rhythm: "motif"` + `harmony_rhythm.motif` |
| Harmony that freely re-articulates | `harmony_rhythm.rhythm: "free"`, tune `density` |
| Real thematic continuity in the lead | `develop` on `voices[0]`, pruned `transform_pool` |
| Thematic continuity on a peer voice | not available — `develop` on `voices[1:]` is a no-op |
| A voice that won't leap unexpectedly | explicit `register` |
| One section louder than another | raise `velocity` |
| A progression that doesn't loop into monotony | check `bars / sum(chord_bars)` |
| Real classical species counterpoint | `species: "first"` or `"free"` only |
| Audible bass swing | `bass_style: "melodic"` or `"motif"` |
| Avoid the harmony-seed collision | ≤10 chords/section, or use `sustain` |
| A render that's actually good, not just valid | read the `slop_metrics.py` section table — check every row |
