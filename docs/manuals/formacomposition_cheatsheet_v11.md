# FormaComposition JSON Cheat Sheet 

One file per piece (`piece_*.json`) — no separate `theme_*.json`. `key`/`mode`/`motif`/
`motifs`/`tempo` live on the piece top level alongside `title`/`sections`/`form`.
`extra="allow"` at piece/motif level unless noted; unknown keys warn, not error.

---

## Running it

```bash
python main.py piece.json                    # render one piece
python main.py piece.json --output out.mid   # -o — explicit output path (single piece only)
python main.py a.json b.json --outdir dir/    # -d — batch-generate multiple pieces into a directory
python main.py piece.json --info              # -i — show piece info without generating
```

`pieces` takes one or more files (`main.py a.json b.json ...`). `--output`/`-o` only
makes sense for a single piece; use `--outdir`/`-d` for batch runs.

---

## Theme fields (on the piece file)

| Field | Type | Required | Values |
|---|---|---|---|
| `key` | string | yes | `C, C#, D, D#, E, F, F#, G, G#, A, A#, B, Db, Eb, Gb, Ab, Bb` |
| `mode` | string | yes | `ionian, dorian, phrygian, lydian, mixolydian, aeolian, locrian, harmonic_minor, melodic_minor, pentatonic_major, pentatonic_minor, blues, whole_tone, diminished, augmented_hexatonic, pelog, arabic, hirajoshi, insen` — 19 total, see Modes reference below |
| `motif` | object | one of motif/motifs | see Motif section below |
| `motifs` | array | one of motif/motifs | array of motif objects — see Motif section below |
| `tempo` | object or int | yes | `{min,max}` or bare int |
| `name` | string | no | free text — absorbed from the retired theme-file format; same idea as `title` |

- `key`/`mode` at this level **are** enum-checked — an invalid value raises a validation error naming the valid set, not a silent pass-through.
- **This piece-level `mode` accepts all 19 modes** (the 7 traditional + 12 new). `section.mode` (the per-section override) does **not** — it's still validated against only the original 7. See the Section table note and the Modes reference below.
- If both `motif` and `motifs` are set, `motifs` wins.
- A bare int for `tempo` is auto-coerced to a fixed range.

### Modes reference

The 7 traditional modes plus 12 additions (all in `harmony.py`'s `MODES` dict, all enum-checked at the piece level).

| Mode | Notes | Character / source |
|---|---|---|
| `ionian` | 7 | major |
| `dorian` | 7 | minor with a natural 6th |
| `phrygian` | 7 | minor with a flat 2nd |
| `lydian` | 7 | major with a sharp 4th |
| `mixolydian` | 7 | major with a flat 7th |
| `aeolian` | 7 | natural minor |
| `locrian` | 7 | diminished tonic, unstable |
| `harmonic_minor` | 7 | raised 7th — fugues, dramatic cadences |
| `melodic_minor` | 7 | jazz minor (ascending form) |
| `arabic` | 7 | double harmonic major / Byzantine / Hijaz Kar — two augmented-second leaps give it a "two semitones flanking wide gaps" character. Common Western umbrella term; real maqam practice uses quarter-tone inflections a 12TET scale can't represent |
| `pentatonic_major` | 5 | open, no tension |
| `pentatonic_minor` | 5 | blues foundation |
| `hirajoshi` | 5 | Japanese pentatonic (koto tuning) — NOT the same scale as `pentatonic_minor`/`blues`; different semitone steps (2-1-4-1-4) and no minor 7th, which is exactly what gives it a "Japanese" rather than "blues" character despite both being 5-note scales |
| `insen` | 5 | symmetric, no clear tonal center — suits static/non-functional ambient fields |
| `blues` | 6 | pentatonic minor + flat 5 |
| `whole_tone` | 6 | all whole steps — Debussy, dreamy |
| `augmented_hexatonic` | 6 | alternating minor-3rd/half-step steps (the "augmented scale") — symmetric, ambiguous tonal center, no traditional tonal function |
| `pelog` | 6 | gapped, wide leaps — not an authentic Javanese pelog tuning (real pelog is non-12TET and varies by ensemble); this is Satie's own 12TET approximation, the exact scale of *Gnossienne No. 3* (D-E-F-G#-A-B), written after he heard gamelan at the 1889 Paris Exposition — an impressionistic gesture toward pelog's character, not a transcription |
| `diminished` | 8 | alternating whole/half steps — tension |

#### Roman-numeral aliasing caveat (non-heptatonic modes)

`ROMAN_TO_DEGREE` only defines I–VII as scale-degree positions 0–6, on the assumption of a 7-note scale. Any mode with a different note count breaks that assumption in one of two ways:

- **5-note modes** (`pentatonic_major`, `pentatonic_minor`, `hirajoshi`, `insen`): `VI` aliases onto the same root as `I`; `VII` aliases onto the same root as `II`.
- **6-note modes** (`blues`, `whole_tone`, `augmented_hexatonic`, `pelog`): `VII` aliases onto the same root as `I`. (`VI` is fine — it's the mode's own unique 6th degree.)
- **8-note mode** (`diminished`): the opposite problem — `I`–`VII` all land on distinct, valid tones (no aliasing), but the scale's 8th tone is simply unreachable by any bare roman numeral, and chord-quality construction (which stacks thirds `% 8` instead of `% 7`) doesn't line up with the usual diatonic expectation.
- **`arabic` (7 notes) is unaffected** — don't assume every new mode needs this caveat.

This is schema-legal and produces **no error or warning** — it silently builds a different chord than the roman numeral implies. Keep progressions within a mode's actual degree count (I–VI for a 6-note mode, I–V for any 5-note mode) until a lint check for this exists.

### `tempo`
| Field | Values |
|---|---|
| `min` / `max` | 20–300, max ≥ min |

### `motif` / `motifs[]`
| Field | Type | Required | Values |
|---|---|---|---|
| `intervals` | array of int | yes | diatonic scale-degree steps (NOT semitones — migrated; see below) |
| `rhythm` | array of float | no | — |
| `rests` | array of bool | no, must match `rhythm` length if set | `true` = silent slot. The underlying diatonic walk still advances through a rest — it just doesn't sound. Consumed across bass.py, melody.py, motif.py, and rhythm.py — this is a general motif field, not `entry_role`-specific |
| `transform_pool` | array | no, default `[]` | `original, inversion, retrograde, retrograde_inversion, augmentation, diminution, transpose_up, transpose_down, shuffle, expand, compress, sequence` |
| `velocities` | array of float | no | 0.0–1.0 |
| `name` | string | no | free text |
| `melodic_scale` | string | no | 7 standard modes, or `pentatonic_major`, `pentatonic_minor`, `blues` |

- `rhythm` is needed for `rhythm: "motif"`.
- `rests`, if set, must be the same length as `rhythm` (validation error otherwise).
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
| Melody rhythm (`rhythm: "motif"`) | primary | `voices[0].motif` |
| Melody pitch (any voice, `behavior: "develop"`) | primary | `voices[].motif` |
| Harmony (`harmony_rhythm.rhythm: "motif"`) | primary | `harmony_rhythm.motif` |
| Counterpoint (free species, `counterpoint[]`) | none | `counterpoint[].motif` — rhythm only, never pitch |
| Peer voice, species set (`voices[1:]`, `species` set) | none | `voices[].motif` — rhythm only, never pitch (same rule as `counterpoint[]`) |
| Peer voice, literal entry (`voices[1:]`, `entry_role` set) | none | `voices[].motif` — rhythm **and** pitch, rendered literally (see `entry_role` below) |

**Two independent gates, easy to conflate — they are not the same mechanism:**
- **`rhythm: "motif"`** (section-level) controls the RHYTHM/timing grid — which motif's onset pattern gets tiled as the melody's durations.
- **`behavior: "develop"`** (per-voice) controls whether that motif's PITCH INTERVALS get used at all — every other behavior (`lyrical`/`generative`/`sparse`) receives no motif pitch data whatsoever, even if the voice has a `motif` field set and even if `rhythm: "motif"` is active. A voice can mix these freely (e.g. `rhythm: "free"` + `behavior: "develop"` for a pitch-driven line on a free rhythm grid, or `rhythm: "motif"` + `behavior: "generative"` for a rhythmically-tiled but freely-pitched line) — but a `motif` field on a non-`develop` voice is a silent no-op for pitch. `lint.py`'s `_check_voice_motif` flags exactly this.
- `transform_sequence` (piece-level) varies the primary's *transform* per section — doesn't change which motif plays.
- `melodic_variation: "isorhythmic"` is the only way to get pitch variety from the rest of the pool (rhythm stays anchored to primary, pitch redraws from other pool members).
- Section-level `motif`/`motifs` fields do nothing (see the Section table note).
- Unknown motif name → validation error, not a render-time crash.
- `fugal_techniques.motif_transform` (see below) applies a transform to whichever motif a section resolves — a different mechanism from `transform_sequence`, scoped to one section rather than stepping through the piece.
- `entry_role` is the one place a peer voice's own `motif` drives pitch, not just rhythm — everywhere else in this table, a peer/counterpoint voice's `motif` field is rhythm-only.

---

## PIECE (`piece_*.json`)

### Top level (PieceModel)
| Field | Type | Required | Values |
|---|---|---|---|
| `form` | array | song form only | array of section names (bare strings), or `{section, exact_repeat}` objects, or a mix of both — see Song form below |
| `form_type` | enum | no, default `narrative` | `narrative, song` |
| `sections` | array (narrative) / `song_sections` dict (song) | yes | two distinct fields, not one field taking either shape — a narrative-form piece uses `sections` (a list); a song-form piece uses `song_sections` (a dict keyed by section name). Disambiguated before validation from whichever shape the input JSON actually has |
| `seed` | int | no, default 42 | — |
| `title` | string | no | free text |
| `name` | string | no | free text — see Theme fields above |
| `transform_sequence` | array | no | — |

- Each `form[]` entry's `section` must exist in `sections`.
- `transform_sequence` wraps if shorter than the section count.

### Section (SectionModel)
| Field | Type | Default | Values |
|---|---|---|---|
| `arc` | enum | `swell` | `swell, build, fade, fade_in, fade_out, plateau, decay, breath` — see Arc table |
| `bars` | float | — (see note) | — |
| `bass_rest_probability` | float | 0.0 | 0.0–1.0 |
| `bass_style` | enum | `root_fifth` | `root_fifth, walking, pedal, root_only, melodic, steady, pulse, motif` |
| `beats_per_bar` | int | 4 | 1–16 |
| `chord_bars` | array of float | — | — |
| `counterpoint` | object or array | — | see Counterpoint table below |
| `density` | enum | `medium` | `low, sparse, medium, full` |
| `drums` | string or object | — | see Drums table below |
| `fugal_techniques` | dict | — | see `fugal_techniques` table below |
| `groove` | string | — | `straight, push, backbeat, syncopated, halftime, shuffle, broken, clave, waltz, offbeat, driving` |
| `harmony_pattern` | object | — | see `rhythm_pattern` / `harmony_pattern` table below |
| `harmony_rest_probability` | float | 0.0 | 0.0–1.0 |
| `harmony_rhythm` | object | — | see Harmony rhythm table below |
| `key` | string | — | `C, C#, D, D#, E, F, F#, G, G#, A, A#, B, Db, Eb, Gb, Ab, Bb` |
| `melodic_arc` | object | — | see `melodic_arc` table below |
| `melodic_variation` | enum | — | `isorhythmic` |
| `melody` | enum or object | `generative` (bare) / `lyrical` (dict, unset `behavior`) | `lyrical, generative, sparse, develop` |
| `mode` | string | — | `ionian, dorian, phrygian, lydian, mixolydian, aeolian, locrian` — **only the 7 traditional modes**, unlike the piece-level `mode` (see note below) |
| `motif` | string, object, or array | — | **does nothing — see note below** |
| `motifs` | array | — | **does nothing — see note below** |
| `name` | string | — | free text — section label, used in lint messages and render logs |
| `note_length_range` | object | — | `{min, max, quantum?}` |
| `notes` | string | — | free text — composer documentation, not read by the engine |
| `percussion` | dict | — | reserved/future-proofed; accepted but not yet consumed by the generator |
| `progression` | array of string | yes | Roman numerals, not enum-validated, no max length — see Harmonic structure below for the quality-suffix and chromatic-alteration syntax it accepts |
| `rest_probability` | float | 0.0 | 0.0–1.0 |
| `rhythm` | enum | yes | `motif, pattern, free` |
| `swing` | float | 0.0 | 0–1 |
| `voices` | array | — | up to 4 total — see Voices table below |

- `bars`: no literal schema default. If omitted and `chord_bars` is given, `bars` is derived from it. If both are omitted, the engine falls back to 8 bars and warns (`"no 'bars' or 'chord_bars' — defaulting to 8 bars"`) — the same effective number this doc previously listed as the default, just arrived at differently.
- **`bars` without `chord_bars` splits evenly across every chord in `progression`** — `bars / len(progression)`, so the number of chords you happened to write becomes the duration divisor, even though "which chords" and "how long each one lasts" are independent decisions. Silent — no warning below a 4-bars/chord split; `lint.py` only flags it above that threshold, on the assumption a short split (e.g. 2 bars/chord) is intentional. Set `chord_bars` explicitly to control duration independent of chord count.
- `bass_rest_probability` is refused on `walking`/`melodic` bass styles.
- `bass_style: "motif"` needs a theme motif with `intervals`+`rhythm`. Swing on bass is only audible on `melodic`/`motif`.
- `chord_bars` must match `progression` length; tiles to fill `bars` if shorter.
- `counterpoint`: up to 3 voices; `voices[]` overrides if both set.
- `drums` string is a pattern name; object form uses the Drums table.
- `fugal_techniques.canon_interval` needs `canonic_imitation: true` or it's a no-op.
- `harmony_pattern` is required if `harmony_rhythm.rhythm: "pattern"` is set **explicitly**. If `harmony_rhythm` is omitted entirely and `section.rhythm: "pattern"` is inherited, there is no such requirement enforced — and no `harmony_pattern` block in that case means **harmony renders completely silent for the section**: no events, no print, no error. This inherited case isn't schema-checked, only lint-checked. Set `harmony_rhythm.rhythm` explicitly (to `"pattern"` with a block, or to `"sustain"`/`"free"`/`"motif"`) to avoid it.
- `harmony_rest_probability` is a no-op under `sustain`.
- `harmony_rhythm` must be an object, not a bare string.
- **`harmony_rhythm.rhythm` does *not* inherit `"motif"` from `section.rhythm`.** Density/groove both cascade from the section when unset on `harmony_rhythm` — but an *inherited* `"motif"` (i.e. `section.rhythm: "motif"` with no explicit `harmony_rhythm.rhythm`) is silently coerced to `"free"` instead. Harmony's own motif-tiling only activates when `harmony_rhythm.rhythm: "motif"` is set explicitly, on that block itself.
- `key`/`mode` here override the theme-level key/mode. **`mode` here is restricted to the 7 traditional modes only** — none of the 12 new modes (see Modes reference) can be set at the section level, only at the piece level. Trying to use e.g. `pelog` as a section override raises a validation error even though it's valid as the piece's own `mode`.
- `melodic_variation: "isorhythmic"` needs `rhythm: "motif"` + multi-motif pool + no lead motif override.
- `melody: "develop"` is lead-voice only — no-op on peer voices.
- **`motif` / `motifs` at the section level do nothing at render time** — only the theme's/piece's own motif pool is ever consulted. Schema-legal, warned by neither validation nor default output; `lint.py`'s `_check_section_motif_override` catches it. Define the motif at the piece level, or attach it to a specific voice with `behavior: "develop"`, instead.
- `note_length_range` applies to melody + free-species counterpoint only; needs `rhythm: "free"`; ignored under `groove` or `pattern`/`motif` rhythm. `quantum` (default `0.25`) snaps sampled lengths to a grid so they stay legible in the DAW — `0.5` = eighth-note legible, `0.25` = sixteenth (default), smaller = more fluid/less quantized.
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

### `melodic_arc`
| Field | Default | Values |
|---|---|---|
| `apex_degree` | — | int, 1-indexed scale degree (1 = tonic, 5 = dominant) |
| `apex_position` | 0.7 | 0.0–1.0, fraction of the section where the peak should land |
| `resolve_every_cycle` | `false` | boolean |

Apex/goal-tone phrase shaping: the melody builds toward `apex_degree` as the section
approaches `apex_position`, then settles afterward, instead of wandering without a
target. Layered on top of whichever `melody` behavior the section uses (works on all
four: `lyrical`, `generative`, `develop`, `sparse`).

- `resolve_every_cycle: false` (default) — a repeating progression resolves once, at the section's true end; a vamp/loop keeps its groove through every repeat.
- `resolve_every_cycle: true` — resolves at the end of *every* progression cycle; a hook that lands every time it comes around.
- Omit `melodic_arc` entirely for the old, targetless behavior.
- On `melody: "sparse"`: the effect is real but easy to miss by ear — sparse's wide leaps and low note density bury a slow directional trend. Don't expect it to be as audible here as on the other three behaviors.
- If `apex_degree` doesn't fit the section's (or voice's) register, the render still completes — the target quietly clamps to the nearest reachable degree — but the lint pass warns first so you can widen the register or lower the degree instead of finding out by ear.

### `fugal_techniques`
| Field | Default | Values |
|---|---|---|
| `motif_transform` | — | `inversion, retrograde, retrograde_inversion, augmentation, diminution, transpose_up, transpose_down, expand, compress, shuffle` |
| `stretto_compression` | — | float multiplier on the motif's rhythm values (floor 0.125 beats) |
| `subject_fragmentation` | — | int — truncates the motif to its first N intervals/rhythms |
| `canonic_imitation` | `false` | boolean |
| `canon_interval` | 4 (beats) | float — no-op unless `canonic_imitation: true` |

Applies to whichever motif the section resolves, once, for the whole section — a
different mechanism from the piece-level `transform_sequence` (which steps through
transforms section by section) and from `voices[].canon_offset` (the peer-voice
equivalent of `canon_interval`, delaying that voice's own line instead of the lead's).

- **`motif_transform` / `stretto_compression` / `subject_fragmentation` only take effect when the lead voice's `behavior: "develop"`.** These three transform the motif object before generation, but the transformed motif is only forwarded into the note-generating function under `develop` — every other behavior (`lyrical`/`generative`/`sparse`) drops it, exactly like the `voice.motif` pitch gate above. Set unconditionally with no warning otherwise.
- **`canonic_imitation` / `canon_interval` are exempt from that gate** — they're applied as a pass over the *already-generated* note list, after generation, regardless of behavior. These two work on any behavior; the other three don't.

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
- `rhythm` does **not** inherit `"motif"` from `section.rhythm` — an inherited `"motif"` is silently coerced to `"free"`. Must be set explicitly here to activate harmony's own motif tiling. (Inherited `"pattern"` has a related, separate trap — see the Section table note on `harmony_pattern`.)
- `transform_imitation: "strict"` hard-crashes at render time — but **only when paired with `rhythm: "motif"` on this same block** (the only branch that reads `transform_imitation` at all). Paired with any other `rhythm` value it's a silent no-op, not a crash. Simplest is still: don't set it.

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
- Of the `species` values, only `free`/`first` are implemented. The others are schema-valid — they pass validation — but raise a `ValueError` and abort the render if you actually use one; the lint pass flags this beforehand so it shows up as a warning, not a traceback mid-render.
- `motif` on a counterpoint voice affects rhythm only, never pitch.
- Cap: 3 voices max.

### `voices[]` — up to 4 total (1 lead + 3 peers)
| Field | Default | Values |
|---|---|---|
| `answer_interval` | — (real answer, +7) | int — semitones; `entry_role: "answer"` only |
| `behavior` | `lyrical` | `lyrical, generative, sparse, develop` |
| `canon_offset` | 0.0 | — |
| `dissonance` | `passing` | `none, passing, neighbor, free` |
| `entry_role` | — | `subject, answer` |
| `motif` | — | object |
| `register` | `mid` | `high, mid, low_mid, low, above, below` + SATB names |
| `rest_probability` | — | 0.0–1.0 |
| `species` | — | `free, first, second, third, fourth, fifth` |
| `velocity` | 64 | 1–127 |

- `behavior: "develop"` is a no-op on peer voices (`voices[1:]`) — see the Motif selection table's develop-gate note for what "no-op" means specifically (pitch, not rhythm).
- **`behavior`-path pitch content (`voice.motif`'s intervals) is only read when this voice's `behavior: "develop"`.** Every other behavior ignores the motif's pitch shape entirely, even with `motif` set. See Motif selection above.
- **`canon_offset` only works on peer voices (`voices[1:]`) — it is never consumed on `voices[0]` (the lead).** Schema-legal on the lead voice, silently ignored at render time; there's no validation error to catch the mistake. If you want the lead's entrance delayed, use `fugal_techniques.canon_interval` + `canonic_imitation: true` at the section level instead — that's the actual lead-voice equivalent, not this field.
- **`dissonance` only has an effect when `species` is also set on this same voice.** It's read exclusively inside the counterpoint-path call (`generate_counterpoint`); a lead voice, a melody-path peer voice (no `species`), or an `entry_role` voice all silently ignore it.
- `motif` applies to any voice, lead or peer — see the Motif selection table above for exactly what each path does with it (rhythm only under `species`, pitch only under `behavior: "develop"`, rhythm *and* pitch under `entry_role`).
- `register` is absolute (unlike counterpoint's relative `above`/`below`).
- `rest_probability` overrides the section default.
- Setting `species` switches the voice onto the counterpoint path.
- Setting `entry_role` switches the voice onto the literal subject/answer path — see below. `entry_role` and `species` are mutually exclusive on the same voice (validation error if both are set); `entry_role` requires `motif` to be set (validation error otherwise — nothing to render literally without one).
- Cap: 4 voices max.

### `entry_role` / `answer_interval` — literal subject/answer entries
- `entry_role: "subject"` renders `motif`'s intervals literally, starting on the tonic, tiled across however much of the section this voice has available — the "actually state the theme" path, distinct from `species`'s free improvisation and from `behavior: "develop"`'s transform-varied restatement. Works on **any** voice, including `voices[0]` (the lead) — unlike every other peer-only mechanism on this page, this one is wired into both.
- `entry_role: "answer"` renders the same motif transposed by `answer_interval` semitones (default +7, the real/strict answer a perfect 5th above) before folding into the voice's register. This ships **real** (strict) transposition only — tonal-answer mutation (the classic adjustment that keeps an opening tonic-dominant leap from implying early modulation) is not implemented.
- **Tiling, not a single entry**: a voice with `entry_role` set generates the motif's intervals repeating for its whole available window (the section length, minus whatever `canon_offset` trims off the far end) — it does not fire once and then fall silent or switch to free material. Combined with staggered `canon_offset`s, this naturally produces an *accumulating canon*: the earliest-entering voice (smallest `canon_offset`) restates the most times before later voices join, converging into a full ensemble texture by the time the last voice enters. If you want a short, punchy exposition rather than a canon that fills the whole section, size the section to roughly `(number of voices) × (entry spacing)` and let a separate following section carry on with `species`/`develop` for continued free development.
- A rest slot in the motif's `rests` array still advances the underlying diatonic walk under `entry_role` — it just doesn't sound. Same convention as motif-driven pitch rendering elsewhere in the engine.
- Existing rhythm/bar-alignment validation (the same check that already applies to any voice's `motif`) still applies — a misaligned `motif.rhythm` on an `entry_role` voice is still caught before render.
- A `species` voice generated after an `entry_role` voice in the same section counterpoints against its literal notes automatically — no special configuration needed.

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

### `rhythm_extract.py` — importing a played groove

Standalone companion script, not part of `main.py`. Play a rhythm on a keyboard in
Logic, export the MIDI, run this on it, paste the output straight into a section's
`rhythm_pattern`/`harmony_pattern`.

```bash
python rhythm_extract.py groove.mid                          # auto-detects pattern length
python rhythm_extract.py groove.mid --beats 4                 # 1 bar of 4/4
python rhythm_extract.py groove.mid --track 0 --name melody_rhythm
python rhythm_extract.py groove.mid --quantize 8               # default is 16
python rhythm_extract.py groove.mid --json-only                # bare JSON, paste-ready
```

| Flag | Default | Values |
|---|---|---|
| `--beats` | auto-detect | float — pattern length in beats |
| `--track` | — | int — which track to extract, for multi-track files |
| `--quantize` | 16 | `0, 4, 8, 16, 32` |
| `--name` | `rhythm_pattern` | string — label for the extracted pattern |
| `--field` | `rhythm_pattern` | string — output JSON key |
| `--list-tracks` | — | boolean — list tracks so you can pick a `--track` index |
| `--json-only` | — | boolean — bare JSON, no display commentary |
| `--output` / `-o` | — | string — write to a file instead of stdout |

### Song form: `form[]`
| Field | Default | Values |
|---|---|---|
| `exact_repeat` | `false` | boolean |
| `section` | required | must exist in `sections` |
| `variation` | — | not a recognized field — rejected the same as any unknown key |

`form[]` entries can be a bare section-name string or a `{section, exact_repeat}`
object — both are accepted, mixed freely in the same array.

---

## Register reference

| Name | MIDI range |
|---|---|
| `soprano` | 63–81 |
| `alto` | 58–76 |
| `tenor` | 51–69 |
| `baritone` | 46–64 |
| `bass` | 39–57 |
| `mid` | = soprano (63–81) |
| `low_mid` | = tenor (51–69) |
| `high` | 67–85 (not soprano) |
| `low` | 36–54 (not bass) |

Default melody register: 63–81. Counterpoint's `above`/`below` is relative to melody's actual range, not one of these fixed bands.

---

## Dynamics stacking

`final_velocity = velocity × groove_accent × arc_scale`, clamped 40–120.

| Layer | Field | Range |
|---|---|---|
| Base | `velocity` | ceiling, not fixed |
| Arc | `arc` | 0.6–1.25× |
| Groove | baked into template | ~0.4–1.0× |

---

## MIDI export

| Track | Channel |
|---|---|
| Melody | 0 |
| Harmony | 1 |
| Counterpoint | 2 |
| Bass | 3 |
| Counterpoint 2 | 4 |
| Counterpoint 3 | 5 |
| Drums | 9 (GM percussion) |

Track names in the exported file match the channel table above (`Melody`, `Harmony`,
`Counterpoint`, `Counterpoint 2`, `Counterpoint 3`, `Bass`, `Drums`) — what you'll see
on import in Logic.

---

## Harmonic structure

| Concept | Field | Values |
|---|---|---|
| Chord sequence | `progression` | list of Roman numerals, not enum-validated |
| Per-chord duration | `chord_bars` | must match `progression` length |
| No length cap | — | keep ≤10 chords/section (seed-collision risk above that, unless the effective harmony source is `"sustain"` or `"pattern"` — only `"free"`/`"motif"` consume the chord-level seed that can collide) |

`progression` entries take more than a bare numeral:

- **Quality suffixes**: `maj, min, dim, aug, maj7, m7, 7, dim7, m9, maj9, 9, m11, 11` — e.g. `iim7`, `Vmaj9`, `viidim`.
- **Chromatic alterations**: `b`/`#` prefixes for borrowed/altered chords — `bVI`, `#iv`, and combined with a quality suffix (`bVImaj7`). The alteration changes the pitch built at that scale position, not which position it is — `bVII` stays the seventh-position chord (same position as plain `VII`), just flattened, rather than collapsing to `vi`.

---

## Anti-slop guidelines

Legal ≠ memorable. `lint.py` catches broken settings; `slop_metrics.py` (auto-runs via `main.py`) catches boring ones.

**Core finding:** rhythm repeats 84–100%, pitch contour repeats 0–96% (median 13%). Backwards. Fix: make pitch recur, let rhythm breathe.

### Piece-tier metrics (these discriminate)
| Metric | Threshold | Fix |
|---|---|---|
| Motif identity | FAIL <10%, WARN <25% | `develop` on `voices[0]`; a smaller `transform_pool` gives tighter, more recognizable identity (all 10 real transforms now vary pitch or rhythm — this is a variety-vs-recognizability choice, not working around a dead transform) |
| Leap profile | FAIL ≥35% (≥4th) / ≥10% (≥m6), WARN ≥28% (≥4th) / ≥5% (≥m6) | narrow `register`; prefer `develop` over `lyrical`/`generative` |
| Harmony mass | FAIL ≥4.0×, WARN ≥3.0× | move toward `rhythm: "sustain"`, or drop `density` |

Leap profile is two separate tiers tracked together, not one number: how often a leap is a 4th-or-larger, and separately, how often it's a wide (m6-or-larger) leap.

Always check section-level, not just OVERALL — an average can hide one bad section.

### Reading the section table
|Column| Meaning|Direction|
|---|---|---|
|notes|lead-melody note count in that slice|	below ~10, shown as - — too short to judge|
|motif|	% of 4-note pitch-contour shapes that recur in the slice — "does the tune have a hook"	higher = better|
|leap|	% of intervals ≥ a 4th, plus the separate ≥m6 "wide leap" tier tracked alongside it — "does it move by step or by jump"|	lower = better|
|harmony|chord events ÷ melody events — "does the pad outweigh the tune"	|lower = better, <3× is fine|

### Engine-wide constants (not per-piece fixes)
- Rhythm stencil sits at 84–100% everywhere (FAIL ≥0.95, WARN ≥0.85) — `note_length_range` is the only lever and it's unset catalog-wide.
- Register span is 24 semitones in most renders — this is also the enforced FAIL threshold (`SPAN_SEMITONES_FAIL`), not just an observation; set it explicitly, widen once at the climax.
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

| Flag | Does |
|---|---|
| `--verbose` / `-v` | show passing metrics too, not just failures |
| `--pad-piece` | waive the harmony-mass check — for pieces deliberately built as a pad |
| `--strict` | exit 1 if any file has a FAIL (for CI/batch gating) |
| `--summary` | one line per file instead of full findings |
| `--table` | compact per-section ASCII grid (needs `--piece`) |
| `--piece` | matching piece JSON, for section attribution (`--table` and `--strict` section checks need this) |

Motif-identity reuse is unreliable under ~40 notes — treat WARN on a short section as "worth a listen," not a verdict.

---

## Quick decision guide

| You want... | Set this |
|---|---|
| Held ambient pad, zero motion | `harmony_rhythm.rhythm: "sustain"` |
| Harmony with its own motivic identity | `harmony_rhythm.rhythm: "motif"` + `harmony_rhythm.motif` |
| Harmony that freely re-articulates | `harmony_rhythm.rhythm: "free"`, tune `density` |
| Real thematic continuity in the lead | `develop` on `voices[0]`, pruned `transform_pool` |
| Transform-varied thematic continuity on a peer voice | not available — `develop` on `voices[1:]` is a no-op |
| A real fugue subject/answer entry, any voice | `entry_role: "subject"`/`"answer"` on `voices[]` (needs `motif` set) |
| A melody that builds to a climax and settles | `melodic_arc` on the section |
| A voice that won't leap unexpectedly | explicit `register` |
| One section louder than another | raise `velocity` |
| A progression that doesn't loop into monotony | check `bars / sum(chord_bars)` |
| Real classical species counterpoint | `species: "first"` or `"free"` only |
| Audible bass swing | `bass_style: "melodic"` or `"motif"` |
| Avoid the harmony-seed collision | ≤10 chords/section, or use `sustain`/`pattern` |
| A hand-played groove imported as JSON | `rhythm_extract.py` on the exported MIDI |
| A delayed lead-voice entrance (canon/stretto) | `fugal_techniques.canon_interval` + `canonic_imitation: true` at the section level — **not** `voices[0].canon_offset`, which is never read |
| A delayed peer-voice entrance | `voices[N].canon_offset` (`N > 0` only) |
| Non-traditional color (blues, whole-tone, gamelan-ish, etc.) | one of the 12 new `mode` values — piece-level only, see Modes reference |
| A render that's actually good, not just valid | read the `slop_metrics.py` section table — check every row |

---

## Changelog (v12 → v13)

Source-code audit against the full codebase (schemas.py, lint.py's COUPLINGS registry,
harmony.py, melody.py, generator.py). No engine behavior changed — this is entirely a
doc-completeness pass. Two real code issues turned up along the way; they are **not**
fixed here and are tracked separately (see `forma_known_issues.md`) rather than folded
into this reference doc.

**New (previously undocumented in code, not just in this doc):**
- **12 new `mode` values** (piece-level only) — `harmonic_minor`, `melodic_minor`,
  `pentatonic_major`, `pentatonic_minor`, `blues`, `whole_tone`, `diminished`,
  `augmented_hexatonic`, `pelog`, `arabic`, `hirajoshi`, `insen`. New `## Modes
  reference` section with note count and character for all 19 modes — including
  `augmented_hexatonic`, which had no character description anywhere, even in the
  source comments; written fresh for this doc.
- **Roman-numeral aliasing caveat**, fully enumerated by mode for the first time:
  which specific roman numerals alias onto which degree, split out by 5-note/6-note/
  8-note mode, with `arabic` (7 notes) explicitly confirmed unaffected.
- **`section.mode`'s restricted enum** — only the 7 traditional modes, unlike the
  piece-level `mode` which accepts all 19. This asymmetry existed in code but was
  invisible in the doc (the two `mode` fields looked identical).
- **`motif`/`motifs[].rests`** field — real, actively-consumed (bass.py, melody.py,
  motif.py, rhythm.py), previously absent from the motif table entirely.

**Silent no-op traps, newly documented (behavior unchanged, now written down):**
- `voice.motif`'s pitch content requires `behavior: "develop"` — previously implied
  only via the Motif selection table's `rhythm: "motif"` row, which is a *different*
  mechanism; now split into two explicit rows plus a clarifying note.
- `fugal_techniques.motif_transform` / `stretto_compression` / `subject_fragmentation`
  are *also* gated by `behavior: "develop"` — previously undocumented entirely.
  `canonic_imitation`/`canon_interval` are NOT gated the same way (behavior-independent
  post-pass) — now stated explicitly as the exception.
- **`voices[0].canon_offset` (the lead voice) is never read** — only `voices[1:]` and
  `counterpoint[]` consume it. Previously implied ("peer-voice counterpart") but not
  stated as a hard restriction on the field itself. Quick decision guide now points to
  `fugal_techniques.canon_interval` as the actual lead-voice mechanism.
- `voices[].dissonance` only has an effect when `species` is also set on that voice —
  previously undocumented.
- `harmony_rhythm.rhythm` does not inherit `"motif"` from `section.rhythm` (silently
  coerced to `"free"` instead) — previously undocumented.
- An inherited `"pattern"` harmony source (via `section.rhythm`, no explicit
  `harmony_rhythm` block, no `harmony_pattern`) renders **completely silent harmony,
  no error** — a gap the schema's "pattern needs a block" check doesn't cover, since
  that check only fires for an explicit `harmony_rhythm.rhythm: "pattern"`. Previously
  undocumented; the existing `harmony_pattern` note only covered the explicit case.
- `bars` without `chord_bars` splitting evenly across every chord — the mechanism and
  its 4-bars/chord lint threshold were both previously undocumented.
- `section.motif`/`section.motifs` doing nothing was documented in the Motif selection
  prose but absent from the Section field table itself — now listed there too, so it's
  discoverable by scanning the table, not just by reading every bullet underneath it.

**Corrections to existing entries:**
- Seed-collision exemption — was listed as `sustain` only; `pattern` is equally exempt
  (`SEED_COLLISION_RISK_HARMONY_SOURCES` only covers `free`/`motif`).
- `transform_imitation: "strict"` — was stated as an unconditional hard-crash; it only
  crashes when paired with `rhythm: "motif"` on the same `harmony_rhythm` block. With
  any other `rhythm` value it's a silent no-op, not a crash. (Still: don't set it.)
- `note_length_range.quantum` — default (`0.25`) and meaning (DAW-legibility snap grid)
  were both missing; table only showed the field existed.

---

## Changelog (v11 → v12)

New engine capability, not a doc-audit correction — this changes what the engine can
render, not just what was previously undocumented about it.

**New:**
- **`entry_role` / `answer_interval`** (`voices[]`) — literal subject/answer statement, the "actually state the fugue subject" path that was previously missing entirely: a voice referencing a motif at a `canon_offset` used to only share its rhythm cell (via the pre-existing rhythm-only `motif` behavior on `species` voices) while independently improvising its own pitches. `entry_role` closes that gap. New table, new subsection, both under `voices[]`.
- Wired into **both** the lead voice (`voices[0]`) and peer voices (`voices[1:]`) — every other peer-adjacent mechanism on this page (`species`, peer `motif`-for-rhythm) is peer-only; `entry_role` is the exception.

**Corrections made alongside the new feature:**
- **`voices[].motif` "only applies to the lead voice"** — this was already inaccurate before `entry_role` existed: a peer voice's own `motif` has always driven its rhythm under `species` (same rule `counterpoint[].motif` follows). Fixed in the `voices[]` notes and cross-referenced against the Motif selection table, which now has explicit rows for both peer-voice motif paths (rhythm-only under `species`, rhythm+pitch under `entry_role`).
- **Quick decision guide** — the "thematic continuity on a peer voice: not available" row was only true for `develop`'s transform-varied continuity; retitled to be specific to `develop`, plus a new row for the `entry_role` path.

---

## Changelog (v10 → v11)

Corrections and additions from a source-code audit. CONFIRMED content is unchanged;
everything below was either wrong or missing.

**Corrections:**
- **Register reference table** — all 9 entries were wrong (soprano, alto, tenor, baritone, bass, mid, low_mid, high, low), along with the derived "default melody register" line. The table predated a register revision that moved every band to an 18-semitone span. Fixed against `REGISTER_BOUNDS` in `schemas.py`.
- **`bars` default** — was listed as a plain default of `8`; actually has no schema default (`None`), with 8 only appearing as an engine-level fallback (with a warning) when neither `bars` nor `chord_bars` is given. Clarified in the Section table and its notes.
- **`sections` field** — was described as one field taking "array or dict"; it's actually two distinct fields (`sections` for narrative form, `song_sections` for song form), disambiguated before validation. Fixed in the Top level table.
- **`form[]` entries** — doc only showed the `{section, exact_repeat}` object form; bare section-name strings are also accepted, mixed freely. Fixed in both the Top level table and the Song form section.
- **`variation` field** — doc asserted it was "removed — hard validation error if set," implying a specific migration check. No such field or dedicated validator exists in the source; it's simply rejected like any other unrecognized key. Softened to avoid asserting unconfirmed history.
- **Counterpoint `species` failure mode** — doc said unimplemented species (anything but `free`/`first`) "fail at validation." They're actually schema-valid and fail with a `ValueError` at render time; lint surfaces the problem beforehand. Fixed in the `counterpoint[]` notes.
- **Theme-level `key`/`mode` enum-checking** — doc said these "are not enum-checked by the engine." They are — invalid values raise a validation error. Fixed in Theme fields.
- **Leap profile metric** — doc's "≥ a 4th" description covered only one of two tracked tiers; the metric is actually two separate thresholds (≥4th and the wider ≥m6 tier) reported together. Clarified in the Piece-tier metrics table and the section-table reading guide.

**Additions (previously undocumented, confirmed present in source):**
- **`## Running it`** — `main.py`'s CLI flags (`--output`/`-o`, `--outdir`/`-d`, `--info`/`-i`, multi-piece invocation). The doc had no reference for the primary render command at all.
- **`melodic_arc`** — new Section field and dedicated table: apex/goal-tone phrase shaping (`apex_degree`, `apex_position`, `resolve_every_cycle`), including the sparse-behavior caveat and the register-reachability lint warning. Fully implemented, previously absent from the doc entirely.
- **`fugal_techniques`** — expanded from a single mentioned key (`canon_interval`) to all five: `motif_transform`, `stretto_compression`, `subject_fragmentation`, `canonic_imitation`, `canon_interval` (including its 4-beat default).
- **Progression notation** — the Harmonic structure section now documents the quality suffixes (`maj7`, `m7`, `dim7`, etc.) and chromatic `b`/`#` alteration prefixes that `progression` entries actually accept, previously reduced to "Roman numerals, not enum-validated."
- **`rhythm_extract.py`** — new subsection documenting the standalone groove-import tool and its 8 flags, placed next to the `rhythm_pattern`/`harmony_pattern` table it feeds.
- **`## MIDI export`** — new section: channel assignments (Melody 0 through Drums on 9) and exported track names, for DAW routing.
- **Minor field additions** — `piece.name`, `section.name`, `section.notes`, `section.percussion` (reserved/unconsumed) added to their respective tables; `voices[].canon_offset` given a one-line explanation (was listed with no description); `slop_metrics.py`'s `--pad-piece`/`--strict`/`--summary`/`--table` flags given a proper table instead of one example invocation; a `melodic_arc` row added to the Quick decision guide.
