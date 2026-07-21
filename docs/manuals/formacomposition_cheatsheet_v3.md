# FormaComposition JSON Cheat Sheet (v3 — merged)

---

## THEME (`theme_*.json`)

### `theme` (top-level object)
| Field | Type | Required | Notes |
|---|---|---|---|
| `key` | string | **yes** | any non-empty string (not enum-checked at theme level — see Section `key` for the enum enforced at render time) |
| `mode` | string | **yes** | any non-empty string at theme level (not enum-checked here — see Section `mode`) |
| `motif` | object | one of `motif`/`motifs` | single motif, see Motif below |
| `motifs` | array of motif objects | one of `motif`/`motifs` | if both present, `motifs` wins and `motif` is ignored (warning, not error). Must be non-empty if present. Missing both → warns, generation still works (purely generative) |
| `name` | string | no | free text |
| `tempo` | object `{min, max}` | **yes** | see TempoRange below |

`extra="allow"` — you can add documentation fields freely; only `palette` is flagged obsolete (warns: "instruments live in Logic").

### `tempo` (TempoRangeModel)
| Field | Type | Range |
|---|---|---|
| `max` | int | 20–300, must be ≥ `min` |
| `min` | int | 20–300 |

### `motif` / each entry in `motifs[]` (MotifModel)
| Field | Type | Required | Notes |
|---|---|---|---|
| `intervals` | array of int | **yes**, min 1 entry | **semitones**, not scale steps |
| `name` | string | no | |
| `rhythm` | array of float | no | beat durations; needed if any section uses `rhythm: "motif"` |
| `transform_pool` | array of TransformLiteral | no, defaults `[]` | see Transform enum below. **Only meaningfully affects `develop`-behavior melody and harmony's independent motif mechanism.** Of the 12 valid transform names, only `inversion`, `retrograde`, `shuffle`, and `sequence` actually vary **pitch** in `develop` (traced to `melody.py`'s `apply_transform`). `augmentation`/`diminution` are rhythm-only by design (handled in `rhythm.py`). `transpose_up`/`transpose_down` are **dead** — `apply_transform` still checks for a literal `"transpose"` string no longer in the schema (confirmed unfixed, logged issue). `retrograde_inversion`, `expand`, `compress` are schema-valid but unimplemented as pitch transforms — silent pitch no-op (rhythm may still shift via the separate rhythm-transform path). **If you want a `develop` voice to audibly vary pitch, restrict this pool to `inversion`/`retrograde`/`shuffle`/`sequence`.** |
| `velocities` | array of float | no | must match `rhythm` length if present; **0.0–1.0 scale multipliers, not raw MIDI velocity** (0.8, not 80/102 — guarded because it silently overflows into invalid MIDI bytes downstream) |

`extra="allow"` on motif too.

---

## Motif selection logic — which motif actually plays, verified against source

If a theme's `motifs[]` pool has more than one entry, **nothing chooses between
them automatically.** Resolution is purely positional, stated in the code's own
docstring (`motif_loader.py`): *"The first motif in the array is the primary —
it anchors the rhythm for the section."* `motifs[0]` (or `theme.motif` if using
the singular form) is the one and only default. There's no randomization, no
per-section cycling, no fallback logic beyond position `[0]`.

**That one resolved motif — call it the "primary" — drives three things by default:**

| Consumer | Uses primary by default? | Can be redirected to a different pool motif? |
|---|---|---|
| Bass (`bass_style: "motif"`) | always | **No.** Hard-wired to the theme's primary — no override field reaches bass at all. |
| Melody rhythm **and** pitch (`rhythm: "motif"`) | yes, if unset | **Yes** — the lead voice's own `motif` field (`voices[0]`, or `melody` given as a dict) replaces both rhythm and pitch together, as one unit. |
| Harmony (`harmony_rhythm.rhythm: "motif"`) | yes, if unset | Yes — via `harmony_rhythm.motif`, independent of melody's choice. |
| Counterpoint (`counterpoint[].motif`, free species only) | n/a — no implicit default | Yes — but **rhythm only, never pitch**; consonance/voice-leading stays fully rule-driven regardless. |

`piece.transform_sequence` can still vary the primary motif's *transform*
(inversion/retrograde/etc.) per section — that's a different lever from
*which* motif is chosen, and never swaps in a different pool member.

**Pitch variety from the rest of the pool is opt-in, and off by default.**
Even with multiple motifs available, melody's pitch is pinned to the same
single motif driving its rhythm unless the section sets
`melodic_variation: "isorhythmic"` — only then does pitch redraw from other
pool members across repetitions while rhythm stays anchored to the primary.

**Section-level `motif`/`motifs` (set directly on a section, not inside a
voice/harmony/counterpoint block) do nothing at all** — confirmed dead in the
schema's own comment, and lint-flagged if you try it. The only way to reach a
non-primary motif is by naming it explicitly on the lead voice, on
`harmony_rhythm.motif`, or on a `counterpoint[]`/peer-voice entry — nowhere
else.

**Naming a motif that doesn't exist is now caught at validation time, not
render time** — a schema-level check resolves every `motif` reference
(lead voice, harmony, counterpoint, peer voices) against the theme's pool and
raises a clean error on a typo, rather than an uncaught `FileNotFoundError`
mid-render.

Worked example, from your own `theme_shake_v2.json` (`[plea, arpeggio,
counterline]`): `plea` sits at index 0, so it's the implicit primary — the
main melody's `rhythm: "motif"` carries it with zero configuration, exactly
as the piece's own notes describe. `arpeggio` and `counterline` are otherwise
invisible to the engine; they only become audible in `piece_shake_v5.json`
because `counterpoint[].motif` names them explicitly, one per voice.

---

## PIECE (`piece_*.json`)

### `piece` (top-level object, PieceModel)
| Field | Type | Required | Notes |
|---|---|---|---|
| `form` | array of SongFormEntry or string | song form only | required if `form_type: "song"`; each entry's `section` name must exist in `sections` dict |
| `form_type` | `"narrative"` \| `"song"` | no, default `"narrative"` | |
| `sections` | array (narrative) or dict (song) | conditional | narrative form → non-empty list required; song form → dict of named section defs required |
| `seed` | int | no, default 42 | |
| `tempo` | int | no | 20–300. If omitted, warns and falls back to theme tempo midpoint |
| `title` | string | no | |
| `transform_sequence` | array of TransformLiteral | no | warns if shorter than section count (wraps/repeats) |

`extra="allow"` at piece level; the loader accepts either `{"piece": {...}}` or a flat dict.

### Section (SectionModel) — narrative `sections[]` entries or song-form `sections{}` values

| Field | Type | Required | Range / Enum / Notes |
|---|---|---|---|
| `arc` | enum | no, default `"swell"` | `swell, build, fade, fade_in, fade_out, plateau, decay, breath`. **Exact curve shapes** (each is a distinct named shape, not just "shaped vs. flat" — see the Arc table below). Cross-section blending is always on — see below. |
| `bars` | float | no | defaults to 8 with a warning if neither this nor `chord_bars` given |
| `bass_rest_probability` | float | no, default 0.0 | 0.0–1.0. Thins the bass line, independent of melody `rest_probability`. Applied on `root_only/root_fifth/steady/pedal/pulse` + the motif-anchor path; **refused with a `UserWarning` on `walking`/`melodic`** (their stepwise lines break if notes drop). |
| `bass_style` | enum | no, default `"root_fifth"` | `root_fifth, walking, pedal, root_only, melodic, steady, pulse, motif` (8 styles). `steady` = a locked figure from `STEADY_FIGURES`, re-approached each chord change. `motif` reuses the theme's `intervals`+`rhythm`, re-anchored to each chord's root, snapping to the nearest chord tone (root/3rd/5th) within a whole step, else nearest scale tone; **requires a theme motif with both `intervals` and `rhythm`** or it falls back to `root_only` with a `UserWarning`. **Swing gotcha:** every bass style *accepts* a `swing`/`swing_ratio` parameter, but only `melodic` and `motif` actually call `swing_offset()`. The other 6 styles silently ignore it — the field validates cleanly and has zero audible effect. **No separate rhythm layer** — timing comes entirely from `bass_style`; there's no `bass_rhythm` block. **Collision, fixed:** if both `rhythm: "motif"` (a generic bass rhythm-anchor override, unpitched) and `bass_style: "motif"` (pitched) are set on the same section, `bass_style` now wins. |
| `beats_per_bar` | int | no, default 4 | 1–16 |
| `chord_bars` | array of float | no | per-chord bar durations; length must match `progression` exactly or hard error; overrides/derives `bars` (mismatch → warning, `chord_bars` wins). If the cell's own total is shorter than `bars`, it tiles to fill — must divide evenly (hard error otherwise). See Harmonic structure below for the >10-chord seeding caveat. |
| `counterpoint` | object or array | no | up to 3 voices (>3 raises an error); bare object auto-wrapped into a 1-item list. **`voices[]` supersedes `counterpoint` outright if both are present on a section.** See the dedicated tables below — and note the `species` crash risk (only `first`/`free` implemented). |
| `density` | enum | no, default `"medium"` | `low, sparse, medium, full` (`"high"` removed — see Enum reference) |
| `drums` | string or object | no | bare string like `"four_on_floor"` coerced to `{"pattern": "four_on_floor"}`. Valid patterns: `four_on_floor, backbeat, halftime, minimal, sideclick` (5 total). Unlike bass, drums' swing is a genuine blanket pass — not style-gated. |
| `fugal_techniques` | dict | no | untyped. Unrelated to `harmony_rhythm.transform_imitation` despite the conceptual overlap — different mechanism, same-sounding idea, don't conflate them. |
| `groove` | string | no | must be a key in `GROOVES` (see Groove list below) — validated at render time in `rhythm.py`, not at schema level |
| `harmony_pattern` | object | conditional | required if `harmony_rhythm.rhythm: "pattern"` |
| `harmony_rest_probability` | float | no, default 0.0 | 0.0–1.0. Thins the chord bed, independent of melody `rest_probability`. **No-op on the `sustain` source and on any single-onset chord window** (a rest roll there would delete the whole chord) — only bites on `pattern`/`motif`/`free` harmony with multiple onsets. |
| `harmony_rhythm` | object | no | **Must be an object** — `"harmony_rhythm": "sustain"` as a bare string raises an error; use `{"rhythm": "sustain"}`. See the expanded table below — includes `motif`/`transform_imitation`, and a correction: `rhythm: "motif"` is **not** retired. |
| `key` | string | no | overrides theme key. Enum-checked: `C, C#, D, D#, E, F, F#, G, G#, A, A#, B, Db, Eb, Gb, Ab, Bb` |
| `melodic_variation` | enum | no | **New.** `isorhythmic` — only meaningful when `rhythm: "motif"` **and** the theme's pool has >1 motif **and** the lead voice has no motif override of its own (any one of these three alone makes it inert; lint-checked). Default (unset): pitch is pinned to the same motif driving the rhythm. `"isorhythmic"`: rhythm stays anchored to one motif while pitch is redrawn from a different pool member each repetition — fixed talea, varying color; opt-in only. |
| `melody` | enum or object | no, default `"generative"` | `lyrical, generative, sparse, develop`. **Gotcha, two different defaults:** omit `melody` entirely → defaults to `"generative"`. Give it as a dict (or use `voices[0]`) and omit `behavior` inside → defaults to `"lyrical"` instead (`VoiceModel.behavior`'s own default). Same field, two fallback values depending on which form you used. Behavior meanings (pitch selection logic): `lyrical`/`generative` = fresh weighted random draw per note. `develop` = continuously restates/re-transforms the motif cell across the entire chord/section (falls back to `generative` if no motif at all); **verified wired for the lead voice only** — a peer voice (`voices[1:]`) with `develop` is a silent no-op, not even lint-checked, rendering as if `generative`. `sparse` = same pool as lyrical, thinner. Dict form also accepts `register`/`velocity`. **New — cross-section continuity:** every section after the first biases its melody's opening note toward or away from the previous section's ending note, based on that section's `arc` (ascending-ending + `swell`/`build` → continues upward; ascending-ending + `fade`/`fade_out`/`decay` → reverses downward; descending-ending + `build` → reverses upward; otherwise no bias). Always on, not disableable — means two `exact_repeat` occurrences of the same section will **not** necessarily open on the same note if preceded by different sections. |
| `mode` | string | no | overrides theme mode. Enum-checked (case-insensitive): `ionian, dorian, phrygian, lydian, mixolydian, aeolian, locrian` |
| `name` | string | no | |
| `note_length_range` | object `{min, max, quantum?}` | no | Decouples note length from density, **melody + free-species counterpoint only**. Set `{"min": 0.5, "max": 3.0}` and durations sample freely in that range instead of the density grid; `density` then governs only rest frequency. Applies uniformly to all melody behaviors. Harmony/bass never sample it (their call sites pass `voice_type="bass"/"chord"`, which the range branch ignores) — restriction for accompaniment, freedom for the lead, by design. `quantum` (default `0.25`) snaps sampled lengths to stay grid-legible in Logic. **Two no-op traps, both lint-flagged:** ignored under a `groove` (groove wins), and ignored under `rhythm: "pattern"`/`"motif"` (those sources precompute their own onset/duration grid). Precedence: `groove` > `note_length_range` > `density` grid; range needs `rhythm: "free"`. Per-voice override available on `counterpoint[]` entries (free species only). Bounds: `min`/`max` both `> 0`, `max >= min`, `quantum > 0` default `0.25`, `extra="forbid"`. |
| `notes` | string | no | free text |
| `percussion` | dict | no | untyped, future-proofed |
| `progression` | array of string | **yes**, min 1 | chord symbols (`"I"`, `"vi"`, `"I7"`) — **not enum-validated**; typos/unsupported Roman numerals pass schema validation and only fail (or silently misbehave) once `harmony.py` parses them. A comma-separated single string (`["ii, v, i"]` instead of `["ii","v","i"]`) is now explicitly caught and rejected at validation — that specific footgun is closed. **No max length** — nothing stops a 12+ chord section. See Harmonic structure below for the >10-chord seed-collision caveat, which directly applies to your own `m1_grid_1` (12 chords) in Broadway Boogie Woogie. |
| `rest_probability` | float | no, default 0.0 | 0.0–1.0. Reaches **melody only** — see `harmony_rest_probability`/`bass_rest_probability` for the other two voices, deliberately decoupled (a continuous pad + steady bass under a melody that breathes is exactly the case one shared knob can't express). |
| `rhythm` | enum | **yes**, no default | `motif, pattern, free`. **Note timing, not pitch** — a separate lever from `melody`'s `behavior`. `develop` pitch behavior with `free` rhythm, or `lyrical` pitch with `motif` rhythm, are both valid and mean different things. `motif` needs a theme motif with `rhythm` populated; `pattern` needs a hand-authored `rhythm_pattern` block or it's a hard validation error. |
| `rhythm_pattern` | object | conditional | required if `rhythm: "pattern"` |
| `swing` | float | no, default 0.0 | 0.0 (off) – 1.0 (heaviest). Remapped internally via `rhythm.remap_swing_ratio()` — the raw JSON value is **not** the internal ratio `apply_swing()` consumes (public `0.0`=off/`1.0`=heaviest maps to internal `0.5–1.0`; values under 0.5 used to rush notes *earlier* before the remap fix — old files with `swing` between 0 and 0.5 now render audibly later instead of earlier, same JSON). Reaches melody/harmony/drums; reaches bass only via `melodic`/`motif` bass styles (6 of 8 styles ignore it). |
| `voices` | array of Voice objects | no | peer voices, replaces melody+counterpoint. **Implemented** — dispatches to `melody.py` or `counterpoint.py` per-voice depending on which fields are set (an earlier doc pass calling this "schema-complete but unimplemented" was stale). See the expanded table below, including the real 4-voice hard cap. |

Unknown keys outside the known set warn (not error) — good for catching typos.

### Arc — exact curve shapes (`arc_multiplier`)

| `arc` | Shape | Range |
|---|---|---|
| `swell` | quadratic rise | 0.75 → 1.10 |
| `build` | quadratic rise, steeper than swell | 0.70 → 1.20 |
| `fade` / `fade_out` | linear fall | 1.00 → 0.65 |
| `fade_in` | linear rise | 0.65 → 1.00 |
| `breath` | arch (sine), peaks at midpoint | 0.85 (edges) → 1.15 (t=0.5) |
| `plateau` | flat — deliberate no-op | 1.0 constant |
| `decay` | linear fall, gentler than fade | 0.95 → 0.70 |
| anything unrecognized | neutral | 1.0 constant |

`build` and `breath` both exceed 1.0 — "louder than the section's own base velocity" is a
real, reachable outcome of some arcs, not just attenuation. **Cross-section blending,
always on:** every section after the first eases *into* its own arc from wherever the
previous section's arc actually ended, rather than jump-cutting at the bar line. Blend
span = `min(4 bars, 25% of this section's length)` — not fixed, not disableable from
JSON. Applies identically to melody and harmony (each converts the shared blend length
into its own time units). This is the single biggest reason a section's opening dynamic
can feel different from what its `arc` name alone suggests.

### `harmony_rhythm` (HarmonyRhythmModel)
| Field | Type | Enum/Range |
|---|---|---|
| `density` | enum, optional | `low, sparse, medium, full`. Under `"free"`: thins/thickens the onset grid. Under `"motif"`: **now genuinely honored** — selects which subset of the motif's onsets play (`full`/`stressed`/`anchor` articulation). No effect under `"sustain"`. |
| `groove` | string, optional | must be a valid `GROOVES` key. Inert under `"sustain"` (no onset pattern) **and** under `"motif"` (the motif cell supplies its own fixed onset grid) — only audible under `"free"`. Lint-checked. |
| `motif` | string ref or embedded dict, optional | **New, live.** Names harmony's own motif, independent of melody's. Omitted → falls back to the section's active theme motif. Only resolved when `rhythm: "motif"` (lint-checked no-op otherwise). Tiles across the **whole section continuously** (not reset per chord); each repetition independently picks its own transform from the motif's `transform_pool` (the only implemented mode — see `transform_imitation` below, which does not work). |
| `note_duration` | enum, optional | `whole, half, quarter, eighth` |
| `rhythm` | enum, optional | `motif, pattern, sustain, free` (cascades: `harmony_rhythm.rhythm` → `section.rhythm` → `"free"` if all omitted). **Correction: `"motif"` is NOT retired** — it was pulled for one release (the old implementation just borrowed melody's motif rhythm verbatim), then reintroduced as a real, independent mechanism. `sustain` = one held note per chord span, zero internal movement — **the** lever for "does this section have any internal motion at all," independent of progression variety, `chord_bars` shaping, groove, or density. `free` = density-grid-driven, can re-articulate within a chord. `pattern` needs a hand-authored `harmony_pattern` block or it's a hard validation error. |
| `swing` | float, default 0.0 | 0.0–1.0; same `remap_swing_ratio()` conversion as the section-level field. Needs onsets to swing — same inert cases as `groove`. |
| `transform_imitation` | `strict`, optional | **Not implemented — hard-crashes, not a working mode.** Setting this to `"strict"` raises `ValueError` at render time whenever `rhythm: "motif"` is also active (the only branch that reads it) — confirmed in `harmony.py`. Per the engine's own error message: harmony's motif rhythm resolves *before* melody's notes (and its transform choices) exist yet, and the two voices' repetition cadence isn't even the same shape to begin with — a real pipeline-ordering blocker, not a missing feature waiting to be flipped on. **Leave this field unset.** The only implemented mode is the unset default: harmony picks its own transform each repetition, independent of melody. |

**Note:** `"groove": "swing"` is **not** a valid groove name — `swing` is a separate float
parameter applied on top of a groove, not a groove itself. `ValueError: Unknown groove`
at render time if this shows up anywhere.

### `counterpoint[]` entries (CounterpointModel)
| Field | Type | Default | Enum/Range |
|---|---|---|---|
| `canon_offset` | float | 0.0 | ≥ 0.0 |
| `dissonance` | enum | `"passing"` | `none, passing, neighbor, free`. `none` requires genuine chord-tone membership (checked against synthetic per-chord-tone reference voices), not just melodic consonance. |
| `groove` | string, optional | — | valid `GROOVES` key. **Free species only.** Verified wired through to this voice's own onset pattern. |
| `motif` | string ref or embedded dict, optional | — | **Free species only — rhythm only, never pitch.** Consonance/voice-leading stays fully rule-driven regardless. `species: "first"` silently ignores this entirely (rhythmically locked to the melody by definition) — **this no-op is lint-checked** (it bit a real piece where species-per-voice-position varied section to section, so the same field was live in some sections, inert in others, with no warning at the time). |
| `note_length_range` | object `{min, max, quantum?}`, optional | — | **Free species only.** Per-voice override of the section's range; falls back to the section-level range if unset. |
| `register` (alias `cp_register`) | enum | `"below"` | `above, below`. Relative to the melody's *actual rendered range* each render, not a fixed band — the odd one out vs. `voices[]`'s absolute registers. |
| `rhythm_density` | enum | `"medium"` | `sparse, medium, full` — **free species only**; `"first"` species is always note-against-note regardless. |
| `species` | enum | `"free"` | `free, first, second, third, fourth, fifth`. **Only `first` and `free` are actually implemented.** Setting `second`/`third`/`fourth`/`fifth` passes schema validation cleanly and then raises `ValueError` ("Unknown species — choose 'first' or 'free'") at render time — a hard crash, not a quality tradeoff, and **not lint-checked.** |
| `velocity` | int | 58 | 1–127 |

### `voices[]` entries (VoiceModel) — implemented, up to 4 total (1 lead + 3 peers)

| Field | Type | Default | Enum/Range |
|---|---|---|---|
| `behavior` | enum | `"lyrical"` | same MelodyLiteral set as section `melody`. Present → this voice runs through `melody.py`. Peer voices (`voices[1:]`) with `develop` are a silent no-op regardless of setting — not lint-checked. |
| `canon_offset` | float | 0.0 | ≥ 0.0 |
| `dissonance` | enum | `"passing"` | `none, passing, neighbor, free` |
| `motif` | string \| dict, optional | — | name from theme pool or inline dict. Reinstated (previously dead). **Wired for the lead voice (`voices[0]`) only.** |
| `register` (alias `v_register`) | enum | `"mid"` | `high, mid, low_mid, low, above, below` (+ `soprano`/`alto`/`tenor`/`baritone`/`bass`). **Absolute**, unlike `counterpoint[]`'s relative register — see Register table below for exact MIDI bounds, and the legacy-alias correction (they are *not* all a clean SATB mapping). |
| `rest_probability` | float, optional | — | 0.0–1.0, overrides section default |
| `rhythm` | — | — | **Dead — not a declared field on `VoiceModel` at all.** Since `VoiceModel` is `extra="forbid"`, adding it now causes a hard validation error rather than silently doing nothing. |
| `species` | enum, optional | — | if present → `counterpoint.py` path instead of `melody.py`; `above`/`below` is *derived* from whether this voice's register sits above/below the lead's, not independently settable. Same second/third/fourth/fifth crash risk as `counterpoint[]` applies. |
| `velocity` | int | 64 | 1–127 |

**4-voice hard cap:** more than 3 peer voices (4 total including lead) crashes with an
`IndexError` — the MIDI track-writer has exactly 3 pre-built peer-track channel/name
slots and indexes into them directly.

### `drums` (DrumModel)
| Field | Type | Default |
|---|---|---|
| `density` | enum, optional | `low, sparse, medium, full` — `None` inherits section density |
| `groove` | string, optional | `None` inherits section groove |
| `pattern` | string | `"four_on_floor"` — valid values: `four_on_floor, backbeat, halftime, minimal, sideclick` (5 total) |
| `swing` | float, optional | `None` inherits section swing; same `remap_swing_ratio()` conversion applies |

Unlike bass, drums' swing is a genuine blanket pass (`_apply_swing_to_drums`, through the
same `remap_swing_ratio()` as every other voice) — it isn't style-gated the way bass's is.

### `rhythm_pattern` / `harmony_pattern` (RhythmPatternModel — from `rhythm_extract.py`)
| Field | Type | Notes |
|---|---|---|
| `durations` | array of float | required, same length as `onsets` |
| `length_beats` | float | default 8.0, must be > 0 |
| `onsets` | array of float | required |
| `velocities` | array of float, optional | same length as `onsets`; 0.0–1.0 scale multipliers, same overflow warning as motif velocities |

### Song form: `form[]` entries (SongFormEntryModel)
| Field | Type | Default |
|---|---|---|
| `exact_repeat` | bool | `false` — set `true` for true verbatim chorus repetition |
| `section` | string, required | name must exist in `sections{}` dict |
| `variation` | — | **Retired — hard-fails validation.** `SongFormEntryModel` is `extra="forbid"` with only `section`/`exact_repeat` as legal fields. Setting `variation` on a form entry is now a schema error, not a valid field with a default. Neither of your two example pieces uses it. |

---

## Register / pitch range reference (cross-voice)

| Name | MIDI range | Note names |
|---|---|---|
| `soprano` | 60–84 | C4–C6 |
| `alto` | 55–79 | G3–G5 |
| `tenor` | 48–72 | C3–C5 |
| `baritone` | 43–67 | G2–G4 |
| `bass` | 36–60 | C2–C4 |

**Correction — legacy aliases are not all a clean SATB mapping.** `mid` (60–84) is
exactly `soprano`, and `low_mid` (48–72) is exactly `tenor` — but `high` (64–88, E4–E6)
and `low` (33–57, A1–A3) are their own distinct 2-octave bands, offset by a few
semitones from the nearest SATB name. Don't assume `high == soprano` or `low == bass`;
they're close but not identical. Omitting `register` on melody defaults to 60–84
(soprano's range).

Counterpoint's `above`/`below` is the odd one out — relative to the melody's actual
rendered range each render, not one of these fixed bands.

---

## Dynamics / velocity stacking

Three layers stack **multiplicatively**: `final_velocity = base_velocity × groove_accent
× arc_scale`, clamped at the end to **40–120 MIDI velocity units** regardless of what the
math produces.

| Layer | Field | Effect | Controllable? |
|---|---|---|---|
| Base | `velocity` | sets the reference point | yes, per voice |
| Arc | `arc` | see exact curves above, each independently clamped to 0.6–1.25× before the final MIDI clamp | yes, one value per section, shared across melody/bass/harmony |
| Groove accent | baked into the `GROOVES` template | ~0.4–1.0 per onset | only by choosing/omitting `groove` |

`velocity` is a **ceiling**, not a fixed value — arc multipliers can push the final
number up to ~1.25× before the clamp, not just down.

---

## Harmonic structure — extra notes

| Concept | Field | Notes |
|---|---|---|
| Chord sequence | `progression` | list of Roman numerals, not enum-validated. Comma-separated single-string footgun is now caught and rejected at validation. |
| Per-chord duration | `chord_bars` | must match `progression` length exactly, or hard error |
| Cell tiling | `chord_bars` sum vs. `bars` | if the cell's own total is shorter than `bars`, it tiles to fill — must divide evenly (hard error otherwise) |
| No length cap | — | `progression` has a minimum of 1 and **no maximum** |

**Seed-collision caveat — directly relevant to your own catalog.** Harmony's per-chord
seed is derived as `(section index × 10) + chord index` before hashing. That spacing
assumes no section has more than 10 chords. A section with **more than 10 chords** can
produce the same derived seed as a different chord in an adjacent section — confirmed:
**Broadway Boogie Woogie's `m1_grid_1`, at 12 chords, collides with `m1_grid_2`'s second
chord.** This is currently harmless in your v7 piece because the only randomness that
seed feeds (rest-thinning) is an explicit no-op under `harmony_rhythm.rhythm: "sustain"`,
which is what `m1_grid_1` uses. **It would become audible the moment that section's
harmony source changes to `"free"`, `"motif"`, or gets a hand-authored `"pattern"`** —
worth remembering if you ever revisit that section's harmony treatment. Until the seeding
gets a proper fix, keep progressions ≤10 chords per section for any harmony source other
than `sustain`.

---

## Enum reference (all Literal values)

- **Density**: `low, sparse, medium, full`. (`"high"` existed in earlier schema versions but was dead — silently fell back to `"medium"` in the groove engine. Removed as of this revision; an old piece file using `"high"` now fails schema validation instead of silently degrading.)
- **Melody**: `lyrical, generative, sparse, develop`. (Earlier revisions listed `motif` and `rhythmic` — both were always invalid: not in `MelodyLiteral`, not in `BEHAVIOR_GENERATORS`. Removed.)
- **Bass style**: `root_fifth, walking, pedal, root_only, melodic, steady, pulse, motif`.
- **Arc**: `swell, fade, build, plateau, decay, fade_in, fade_out, breath`
- **Rhythm source (section)**: `motif, pattern, free`
- **Harmony rhythm source**: `motif, pattern, sustain, free`
- **Transform**: `original, inversion, retrograde, retrograde_inversion, augmentation, diminution, transpose_up, transpose_down, shuffle, expand, compress`
- **Counterpoint species**: `free, first, second, third, fourth, fifth` — only `free`/`first` actually implemented; the rest crash at render.
- **Counterpoint register**: `above, below`
- **Dissonance**: `none, passing, neighbor, free`
- **Voice register**: `high, mid, low_mid, low, above, below` (+ SATB names — see Register table above)
- **Section key**: `C, C#, D, D#, E, F, F#, G, G#, A, A#, B, Db, Eb, Gb, Ab, Bb`
- **Section mode**: `ionian, dorian, phrygian, lydian, mixolydian, aeolian, locrian`
- **Drum pattern**: `four_on_floor, backbeat, halftime, minimal, sideclick`
- **Groove** (from `rhythm.py GROOVES`, validated at render time, not schema time): `straight, push, backbeat, syncopated, halftime, shuffle, broken, clave, waltz, offbeat, driving`
  - `shuffle` has swing baked into the template — don't stack a `swing` value on top of it.
  - `waltz` assumes `beats_per_bar: 3`.

---

## Quick decision guide

| You want... | Set this |
|---|---|
| A held, ambient pad with zero internal motion | `harmony_rhythm.rhythm: "sustain"` |
| Harmony that re-articulates with its own independent motivic identity | `harmony_rhythm.rhythm: "motif"`, optionally its own `harmony_rhythm.motif` |
| Harmony that freely re-articulates without a fixed motif | `harmony_rhythm.rhythm: "free"`, tune `density` |
| Real thematic continuity in the lead melody | `behavior: "develop"` on `voices[0]` (or `melody` as a dict) — restrict `transform_pool` to `inversion`/`retrograde`/`shuffle`/`sequence` if you want pitch variety, not just rhythm-only/dead transforms |
| Thematic continuity on a peer voice | Not currently available — `develop` on `voices[1:]` is a silent no-op regardless of settings |
| A voice that won't leap two octaves unexpectedly | Set an explicit `register` — the default is wider than it looks |
| One section louder than another | Raise `velocity` — `arc` alone reaches 1.20–1.25× but that's still relative to your base |
| A section's dynamic to snap cleanly at its own boundary | Not directly possible — cross-section arc blending is always on (up to 4 bars / 25% of section) |
| A chord progression that doesn't loop into monotony | Check `bars / sum(chord_bars)` — flagged past ~4 bars/chord if `chord_bars` is omitted |
| A counterpoint voice with real classical species rules | `species: "first"` or `species: "free"` **only** — anything else crashes at render |
| Swing that's actually audible on bass | `bass_style: "melodic"` or `"motif"` — the other 6 styles ignore the swing field entirely |
| A long section that doesn't hit the harmony-seed collision risk | Keep `progression` ≤10 chords, or use `harmony_rhythm.rhythm: "sustain"` if it must be longer |

---
 

---

The `ii`/`VI` Roman-numeral question in Still Cove is real but different in kind:
`progression` is just `list[str]` with no enum validation at the schema layer, so
nonstandard numerals pass Pydantic fine and only surface as a problem (or don't) once
`harmony.py` tries to parse them into chords. The comma-separated-string variant of this
footgun is now closed, but the underlying "no enum check on Roman numerals" gap is not —
worth tracing `harmony.py`'s chord-symbol parser directly rather than assuming the schema
would catch a bad numeral.
