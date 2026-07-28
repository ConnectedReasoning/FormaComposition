# FormaComposition JSON Cheat Sheet (v7 — trimmed to reference, no changelog/footnotes)

One file per piece (`piece_*.json`) — no separate `theme_*.json`. `key`/`mode`/`motif`/
`motifs`/`tempo` live on the piece top level alongside `title`/`sections`/`form`.
`extra="allow"` at piece/motif level unless noted; unknown keys warn, not error.

---

## Theme fields (on the piece file)

| Field | Type | Required | Notes |
|---|---|---|---|
| `key` | string | yes | not enum-checked here |
| `mode` | string | yes | not enum-checked here |
| `motif` | object | one of motif/motifs | see Motif below |
| `motifs` | array | one of motif/motifs | if both set, `motifs` wins |
| `tempo` | `{min,max}` or int | yes | bare int auto-coerced to fixed range |
| `name` | string | no | |

### `tempo`
| Field | Range |
|---|---|
| `min` / `max` | 20–300, max ≥ min |

### `motif` / `motifs[]`
| Field | Type | Required | Notes |
|---|---|---|---|
| `intervals` | array of int | yes | semitones |
| `rhythm` | array of float | no | needed for `rhythm: "motif"` |
| `transform_pool` | array | no, default `[]` | only `inversion`/`retrograde`/`shuffle`/`sequence` vary pitch in `develop`. `augmentation`/`diminution` are rhythm-only. `transpose_up`/`transpose_down` are dead. `retrograde_inversion`/`expand`/`compress` are pitch no-ops. |
| `velocities` | array of float | no | 0.0–1.0 multipliers, not raw MIDI velocity |
| `name` | string | no | |

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
| Field | Type | Required | Notes |
|---|---|---|---|
| `form` | array | song form only | each entry's `section` must exist in `sections` |
| `form_type` | `narrative`\|`song` | no, default `narrative` | |
| `sections` | array (narrative) or dict (song) | yes | |
| `seed` | int | no, default 42 | |
| `title` | string | no | |
| `transform_sequence` | array | no | wraps if shorter than section count |

### Section (SectionModel)
| Field | Type | Default | Notes |
|---|---|---|---|
| `arc` | enum | `swell` | `swell, build, fade, fade_in, fade_out, plateau, decay, breath` — see Arc table |
| `bars` | float | 8 | |
| `bass_rest_probability` | float | 0.0 | thins bass; refused on `walking`/`melodic` |
| `bass_style` | enum | `root_fifth` | `root_fifth, walking, pedal, root_only, melodic, steady, pulse, motif`. `motif` needs a theme motif with `intervals`+`rhythm`. Swing only audible on `melodic`/`motif`. |
| `beats_per_bar` | int | 4 | 1–16 |
| `chord_bars` | array of float | — | must match `progression` length; tiles to fill `bars` if shorter |
| `counterpoint` | object/array | — | up to 3 voices; `voices[]` overrides if both set |
| `density` | enum | `medium` | `low, sparse, medium, full` |
| `drums` | string/object | — | patterns: `four_on_floor, backbeat, halftime, minimal, sideclick` |
| `fugal_techniques` | dict | — | `canon_interval` needs `canonic_imitation: true` or it's a no-op |
| `groove` | string | — | must be a valid `GROOVES` key |
| `harmony_pattern` | object | — | required if `harmony_rhythm.rhythm: "pattern"` |
| `harmony_rest_probability` | float | 0.0 | no-op under `sustain` |
| `harmony_rhythm` | object | — | must be an object, not a bare string — see table below |
| `key` | string | — | overrides theme key |
| `melodic_variation` | enum | — | `isorhythmic` — needs `rhythm: "motif"` + multi-motif pool + no lead motif override |
| `melody` | enum/object | `generative` (bare) / `lyrical` (dict, unset `behavior`) | `lyrical, generative, sparse, develop`. `develop` is lead-voice only — no-op on peer voices. |
| `mode` | string | — | overrides theme mode |
| `note_length_range` | `{min,max,quantum?}` | — | melody + free-species counterpoint only; needs `rhythm: "free"`; ignored under `groove` or `pattern`/`motif` rhythm |
| `progression` | array of string | yes | not enum-validated, no max length |
| `rest_probability` | float | 0.0 | melody only |
| `rhythm` | enum | yes | `motif, pattern, free` — timing, separate from `melody` behavior |
| `swing` | float | 0.0 | 0–1; audible on bass only via `melodic`/`motif` |
| `voices` | array | — | peer voices, up to 4 total — see table below |

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
| Field | Notes |
|---|---|
| `density` | `low, sparse, medium, full` — no effect under `sustain` |
| `groove` | inert under `sustain`/`motif`, audible only under `free` |
| `motif` | harmony's own motif, independent of melody's; only resolves under `rhythm: "motif"` |
| `rhythm` | `motif, pattern, sustain, free`. `sustain` = zero internal motion. |
| `swing` | 0–1 |
| `transform_imitation` | **don't set** — `"strict"` hard-crashes at render time |

### `counterpoint[]`
| Field | Default | Notes |
|---|---|---|
| `canon_offset` | 0.0 | |
| `dissonance` | `passing` | `none, passing, neighbor, free` |
| `groove` | — | free species only |
| `motif` | — | free species only, rhythm only |
| `note_length_range` | — | free species only |
| `register` | `below` | `above, below` — relative to melody's rendered range |
| `rhythm_density` | `medium` | free species only |
| `species` | `free` | only `free`/`first` implemented — others fail at validation |
| `velocity` | 58 | 1–127 |

Cap: 3 voices max.

### `voices[]` — up to 4 total (1 lead + 3 peers)
| Field | Default | Notes |
|---|---|---|
| `behavior` | `lyrical` | `develop` no-op on peer voices |
| `canon_offset` | 0.0 | |
| `dissonance` | `passing` | |
| `motif` | — | lead voice (`voices[0]`) only |
| `register` | `mid` | absolute — `high, mid, low_mid, low, above, below` + SATB names |
| `rest_probability` | — | overrides section default |
| `species` | — | switches to counterpoint path |
| `velocity` | 64 | 1–127 |

Cap: 4 voices max.

### `drums`
| Field | Default |
|---|---|
| `density` | inherits section |
| `groove` | inherits section |
| `pattern` | `four_on_floor` (5 total patterns) |
| `swing` | inherits section |

### `rhythm_pattern` / `harmony_pattern`
| Field | Notes |
|---|---|
| `durations` | required, matches `onsets` length |
| `length_beats` | default 8.0 |
| `onsets` | required |
| `velocities` | optional, 0.0–1.0 multipliers |

### Song form: `form[]`
| Field | Default |
|---|---|
| `exact_repeat` | `false` |
| `section` | required, must exist in `sections` |
| `variation` | removed — hard validation error if set |

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

| Concept | Field | Notes |
|---|---|---|
| Chord sequence | `progression` | list of Roman numerals, not enum-validated |
| Per-chord duration | `chord_bars` | must match `progression` length |
| No length cap | — | keep ≤10 chords/section (seed-collision risk above that, unless `rhythm: "sustain"`) |

---

## Enum reference

- **Density**: `low, sparse, medium, full`
- **Melody**: `lyrical, generative, sparse, develop`
- **Bass style**: `root_fifth, walking, pedal, root_only, melodic, steady, pulse, motif`
- **Arc**: `swell, fade, build, plateau, decay, fade_in, fade_out, breath`
- **Rhythm source (section)**: `motif, pattern, free`
- **Harmony rhythm source**: `motif, pattern, sustain, free`
- **Transform**: `original, inversion, retrograde, retrograde_inversion, augmentation, diminution, transpose_up, transpose_down, shuffle, expand, compress, sequence` — only `inversion, retrograde, shuffle, sequence` vary pitch in `develop`
- **Counterpoint species**: `free, first, second, third, fourth, fifth` — only `free`/`first` implemented
- **Counterpoint register**: `above, below`
- **Dissonance**: `none, passing, neighbor, free`
- **Voice register**: `high, mid, low_mid, low, above, below` + SATB names
- **Section key**: `C, C#, D, D#, E, F, F#, G, G#, A, A#, B, Db, Eb, Gb, Ab, Bb`
- **Section mode**: `ionian, dorian, phrygian, lydian, mixolydian, aeolian, locrian`
- **Drum pattern**: `four_on_floor, backbeat, halftime, minimal, sideclick`
- **Groove**: `straight, push, backbeat, syncopated, halftime, shuffle, broken, clave, waltz, offbeat, driving`

---

## Anti-slop guidelines

Legal ≠ memorable. `lint.py` catches broken settings; `slop_metrics.py` (auto-runs via `main.py`) catches boring ones.

**Core finding:** rhythm repeats 84–100%, pitch contour repeats 0–96% (median 13%). Backwards. Fix: make pitch recur, let rhythm breathe.

### Piece-tier metrics (these discriminate)
| Metric | Threshold | Fix |
|---|---|---|
| Motif identity | FAIL <10%, WARN <25% | `develop` on `voices[0]`; prune `transform_pool` to `inversion`/`retrograde`/`shuffle`/`sequence` |
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
