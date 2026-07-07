# FormaComposition JSON Cheat Sheet
Source: `intervals/core/schemas.py` (Pydantic v2) + `intervals/music/rhythm.py` (groove data). Not inferred from example files — pulled from the actual validators.

---

## THEME (`theme_*.json`)

### `theme` (top-level object)
| Field | Type | Required | Notes |
|---|---|---|---|
| `key` | string | **yes** | any non-empty string (not enum-checked at theme level — see Section `key` below for the actual enum used at render time) |
| `mode` | string | **yes** | any non-empty string at theme level (not enum-checked here — see Section `mode` for the enforced enum) |
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
| `intervals` | array of int | **yes**, min 1 entry | **semitones**, not scale steps (this bit you before — v2 slack key note confirms) |
| `name` | string | no | |
| `rhythm` | array of float | no | beat durations; needed if any section uses `rhythm: "motif"` |
| `transform_pool` | array of TransformLiteral | no, defaults `[]` | see Transform enum below |
| `velocities` | array of float | no | must match `rhythm` length if present; **0.0–1.0 scale multipliers, not raw MIDI velocity** (0.8, not 80/102 — this is explicitly guarded because it silently overflows into invalid MIDI bytes downstream) |

`extra="allow"` on motif too.

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

`extra="allow"` at piece level, and note the loader accepts either `{"piece": {...}}` (what your files use) or a flat dict.

### Section (SectionModel) — narrative `sections[]` entries or song-form `sections{}` values
| Field | Type | Required | Range / Enum |
|---|---|---|---|
| `arc` | enum | no, default `"swell"` | `swell, fade, build, plateau, decay, fade_in, fade_out, breath` |
| `bars` | float | no | defaults to 8 with a warning if neither this nor `chord_bars` given |
| `bass_rest_probability` | float | no, default 0.0 | 0.0–1.0. **New.** Thins the bass line, independent of melody `rest_probability`. Applied on `root_only/root_fifth/steady/pedal/pulse` + the motif-anchor path; **refused with a `UserWarning` on `walking`/`melodic`** (their stepwise lines break if notes are dropped). See resolved note #4. |
| `bass_style` | enum | no, default `"root_fifth"` | `root_fifth, walking, pedal,  root_only, melodic, steady, pulse, motif`  `motif` is new and does work — see note below. |
| `beats_per_bar` | int | no, default 4 | 1–16 |
| `chord_bars` | array of float | no | per-chord bar durations; length must match `progression`; if given, overrides/derives `bars` (mismatch → warning, `chord_bars` wins) |
| `counterpoint` | object or array | no | up to 3 voices (>3 raises an error); bare object form auto-wrapped into a 1-item list |
| `density` | enum | no, default `"medium"` | `low, sparse, medium, full` |
| `drums` | string or object | no | bare string like `"four_on_floor"` is coerced to `{"pattern": "four_on_floor"}` |
| `fugal_techniques` | dict | no | untyped |
| `groove` | string | no | must be a key in `GROOVES` (see Groove list below) — validated at render time in `rhythm.py`, not at schema level |
| `harmony_pattern` | object | conditional | required if `harmony_rhythm.rhythm: "pattern"` |
| `harmony_rest_probability` | float | no, default 0.0 | 0.0–1.0. **New.** Thins the chord bed, independent of melody `rest_probability`. **No-op on the `sustain` source and on any single-onset chord window** (a rest roll there deletes the whole chord, not a note) — only bites on `pattern`/`motif`/`free` harmony with multiple onsets. See resolved note #4. |
| `harmony_rhythm` | object | no | see HarmonyRhythm below. **Must be an object** — `"harmony_rhythm": "sustain"` as a bare string raises an error; use `{"rhythm": "sustain"}` |
| `key` | string | no | overrides theme key. **Enum-checked**: `C, C#, D, D#, E, F, F#, G, G#, A, A#, B, Db, Eb, Gb, Ab, Bb` |
| `melody` | enum | no, default `"generative"` | `lyrical, generative, motif, sparse, rhythmic, develop` |
| `mode` | string | no | overrides theme mode. **Enum-checked** (case-insensitive): `ionian, dorian, phrygian, lydian, mixolydian, aeolian, locrian` |
| `motif` | string \| dict | no | overrides theme motif pool for this section (single) |
| `motifs` | array of string\|dict | no | restricts pool to exactly these |
| `name` | string | no | |
| `notes` | string | no | free text |
| `percussion` | dict | no | untyped, future-proofed |
| `progression` | array of string | **yes**, min 1 | chord symbols (e.g. `"I"`, `"vi"`, `"I7"`) — **not enum-validated**; typos/unsupported Roman numerals (your open `ii`/`VI` question) pass schema validation and only fail (or silently misbehave) downstream in `harmony.py` |
| `rest_probability` | float | no, default 0.0 | 0.0–1.0 |
| `rhythm` | enum | **yes**, no default | `motif, pattern, free` |
| `rhythm_pattern` | object | conditional | required if `rhythm: "pattern"` |
| `swing` | float | no, default 0.0 | 0.0 (off) – 1.0 (heaviest). Remapped internally via `rhythm.remap_swing_ratio()` before use — raw value is NOT the internal ratio `apply_swing()` consumes, don't assume it. |
| `voices` | array of Voice objects | no | peer voices, replaces melody+counterpoint. **Schema-complete but unimplemented in the generator** per your notes — confirmed still true in this codebase snapshot |

Unknown keys outside the known set warn (not error) — good for catching typos.

### `harmony_rhythm` (HarmonyRhythmModel)
| Field | Type | Enum/Range |
|---|---|---|
| `density` | enum, optional | `low, sparse, medium, full` |
| `groove` | string, optional | must be a valid `GROOVES` key |
| `note_duration` | enum, optional | `whole, half, quarter, eighth` |
| `rhythm` | enum, optional | `motif, pattern, sustain, free` (cascades: `harmony_rhythm.rhythm` → `section.rhythm` → `"free"` if all omitted) |
| `swing` | float, default 0.0 | 0.0 (off) – 1.0 (heaviest); same `remap_swing_ratio()` conversion as the section-level field |

**Note:** `"groove": "swing"` — the field you flagged as unconfirmed — is **not** a valid groove name. `swing` is a separate float parameter (0.0–1.0) applied on top of a groove, not a groove itself. If any piece file has `"groove": "swing"`, that will raise `ValueError: Unknown groove` at render time. Valid groove names are listed below.

### `counterpoint[]` entries (CounterpointModel)
| Field | Type | Default | Enum/Range |
|---|---|---|---|
| `canon_offset` | float | 0.0 | ≥ 0.0 |
| `dissonance` | enum | `"passing"` | `none, passing, neighbor, free` |
| `groove` | string, optional | — | valid `GROOVES` key |
| `register` (alias for `cp_register`) | enum | `"below"` | `above, below` |
| `rhythm_density` | enum | `"medium"` | `sparse, medium, full` — only matters for `species: "free"`; `"first"` species is always note-against-note regardless |
| `species` | enum | `"free"` | `free, first, second, third, fourth, fifth` |
| `velocity` | int | 58 | 1–127 |

### `voices[]` entries (VoiceModel) — unimplemented in generator, schema only
| Field | Type | Default | Enum/Range |
|---|---|---|---|
| `behavior` | enum | `"lyrical"` | same MelodyLiteral set as section `melody` |
| `canon_offset` | float | 0.0 | ≥ 0.0 |
| `dissonance` | enum | `"passing"` | `none, passing, neighbor, free` |
| `motif` | string \| dict, optional | — | name from theme pool or inline dict |
| `register` (alias for `v_register`) | enum | `"mid"` | `high, mid, low_mid, low, above, below` — pitch ranges: high=G4–E6, mid=C4–A5, low_mid=C3–A4, low=C2–A3 |
| `rest_probability` | float, optional | — | 0.0–1.0, overrides section default |
| `rhythm` | enum | `"free"` | `motif, pattern, free` |
| `species` | enum, optional | — | if present → counterpoint.py path; if absent → melody.py path |
| `velocity` | int | 64 | 1–127 |

### `drums` (DrumModel)
| Field | Type | Default |
|---|---|---|
| `density` | enum, optional | `low, sparse, medium, full` — `None` inherits section density |
| `groove` | string, optional | `None` inherits section groove |
| `pattern` | string | `"four_on_floor"` |
| `swing` | float, optional | `None` inherits section swing; same `remap_swing_ratio()` conversion applies |

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
| `variation` | float | 0.0, range 0.0–1.0 |

---

## Enum reference (all Literal values)

- **Density**: `low, sparse, medium, full`. (`"high"` existed in earlier schema versions but was dead — it silently fell back to `"medium"` behavior in the groove engine. Removed from `DensityLiteral` as of this revision; any old piece file using `"high"` will now fail schema validation instead of silently degrading, which is the point.)
- **Melody**: `lyrical, generative, motif, sparse, rhythmic, develop`
- **Bass style**: `root_fifth, walking, pedal, root_only, melodic, steady, pulse, motif`.
- **Arc**: `swell, fade, build, plateau, decay, fade_in, fade_out, breath`
- **Rhythm source (section)**: `motif, pattern, free`
- **Harmony rhythm source**: `motif, pattern, sustain, free`
- **Transform**: `original, inversion, retrograde, retrograde_inversion, augmentation, diminution, transpose_up, transpose_down, shuffle, expand, compress`
- **Counterpoint species**: `free, first, second, third, fourth, fifth`
- **Counterpoint register**: `above, below`
- **Dissonance**: `none, passing, neighbor, free`
- **Voice register**: `high, mid, low_mid, low, above, below`
- **Section key**: `C, C#, D, D#, E, F, F#, G, G#, A, A#, B, Db, Eb, Gb, Ab, Bb`
- **Section mode**: `ionian, dorian, phrygian, lydian, mixolydian, aeolian, locrian`
- **Groove** (from `rhythm.py GROOVES`, validated at render time, not schema time): `straight, push, backbeat, syncopated, halftime, shuffle, broken, clave, waltz, offbeat, driving`
  - `shuffle` has swing baked into the template — don't stack a `swing` value on top of it.
  - `waltz` assumes `beats_per_bar: 3`.

---

## Resolved since the first pass of this doc

1. **`density: "high"` — removed from the schema.** It used to be legal but inert (silently treated as `"medium"` in `rhythm.py`'s groove engine). As of this revision `DensityLiteral` is `low, sparse, medium, full` — `"high"` is gone entirely. Confirmed against your three example pieces and the rest of this repo: nothing currently uses `"high"`, so this cost nothing. If an older piece file surfaces later with `"high"` in it, it will now fail validation loudly instead of degrading silently — that's intentional, but it means a file that used to "just render weird" will now hard-stop until you change it to `"medium"` or `"full"`.

2. **`swing` semantics — fixed at the source, not just documented.** The public `swing` field (0.0–1.0 on sections, `harmony_rhythm`, and `drums`) used to be passed straight into `apply_swing()`/`_apply_swing_to_drums()`, whose internal scale treats `0.5` as straight and anything below that as pushing notes *earlier*. So values like `0.2` — which read as "a little swing" — were actually rushing the offbeats, not swinging them. A new `remap_swing_ratio()` in `rhythm.py` is now the single conversion point all three consumers (melody, harmony rhythm, drums) route through: public `0.0` = off, `1.0` = heaviest, correctly mapped to the internal `0.5–1.0` range. Verified with a direct before/after test (`0.2` now moves a note from beat `0.5` to `0.6`, late, instead of to `0.2`, early).
   - **Still open, and still yours to check:** any *existing* piece file with a `swing` value between 0 and 0.5 will now render audibly differently — later instead of earlier — with the exact same JSON. That's the correct behavior, but it's a behavior change on old files, not just a bug fix in isolation. Grep your catalog for `"swing":` values in that range and give them a listen before you assume the new render matches what you'd approved before.
   - Also confirm the `"groove": "swing"` string (a different, unrelated bug — `swing` was never a valid groove *name*, it's the separate float field) has actually been corrected in whatever reference doc or piece file it came from. That one still hard-errors (`Unknown groove: 'swing'`) if it's still sitting anywhere.

3. **`bass_style: "motif"` — new.** The theme's own `intervals`+`rhythm` now drive the bass line: re-anchored to each chord's root at the start of every chord (harmonic clarity), then the motif's shape cycles from there, snapping to the nearest chord tone (root/third/fifth) within a whole step, falling back to the nearest scale tone otherwise, clamped to the bass register. It reuses your theme's existing motif definition — no new JSON fields, just the new enum value.
   - **Requires a motif.** If the theme has no `motif`/`motifs` with both `intervals` and `rhythm` populated, it falls back to `root_only` and raises a `UserWarning` rather than crashing or silently doing nothing.
   - **Collision fixed, not just avoided:** `section.rhythm: "motif"` independently populates a generic bass rhythm-anchor override (root notes on the motif's rhythm, no pitch shape) — that mechanism existed before this and is unrelated to `bass_style`. If both `rhythm: "motif"` and `bass_style: "motif"` are set on the same section, the explicit `bass_style` now wins; before this fix, the generic override would have silently swallowed the new pitched behavior with no indication anything was wrong.
   - **Character depends on your motif's interval sizes.** A motif with small steps (Slack Key's ±2/±3 semitones) produces a subtle wobble around the chord tones, since the snap threshold pulls anything within 2 semitones onto a chord tone. A motif with wider leaps will travel further before snapping. This is a real behavioral consequence of the snap threshold, not a neutral default — worth listening to before assuming it's giving you as much "motif" character as you want.

4. **Per-voice rest probability — `harmony_rest_probability` + `bass_rest_probability`, new.** Before this, `rest_probability` reached the **melody only**. The bass generator took no such parameter, and harmony chord events were built (swing → velocity arc → rearticulation) with no rest step anywhere in the kernel. So the harmony bed and bass line could not breathe on their own. These two new section-level floats fix that, and they are **deliberately decoupled from melody `rest_probability`** — the ambient default (a continuous pad and steady bass under a melody that leaves space) is exactly the case a single shared knob can't express, since it would force all three voices to breathe on the same schedule. Both default `0.0`, which is a strict no-op (byte-identical to the old render).
   - **`harmony_rest_probability` — guarded twice.** It thins a chord's onsets, but it's a no-op when the harmony source is `sustain` *or* when the chord window resolved to a single onset — a rest roll there would delete the whole chord rather than thin it. So it only does something on `pattern`/`motif`/`free` harmony that actually has multiple onsets per chord. **The trap:** if you want an ambient pad to breathe and you're on `sustain`, this knob does nothing by design — you need real onsets (`pattern`/`motif`/`free`) to thin. It won't error, it just won't respond.
   - **`bass_rest_probability` — refused on the continuous styles.** Safe and applied on `root_only`/`root_fifth`/`steady`/`pedal`/`pulse` and on the motif-anchor override path (where "bass" is just independent roots). On `walking` and `melodic` it is **refused with a `UserWarning` and the line is left intact** — those styles depend on stepwise motion into the next chord root, so random note drops break the line instead of adding breath. The refusal is loud, not silent, consistent with the rest of the engine's "no silent no-ops" stance.
   - **Deterministic and decorrelated.** Both are seed-driven and reproducible. The bass rest RNG is XOR-decorrelated from each style function's own seed stream, so the *gaps* don't lock to the *note choices* — you get an independent rest pattern rather than one that mirrors the pitch decisions.
   - **Watch the silence at the top of the range.** At high probability on a short section, a voice can go fully silent — `root_only` at `0.4` over 4 bars zeroed out in testing. That's the same designed behavior as melody `rest_probability` approaching `1.0` (full silence), not a bug. Size the value to the section length; `0.1–0.25` is breathing room, `0.4+` on a short section is a real risk of dropout.

The `ii`/`VI` Roman-numeral question in Still Cove is real but different in kind: `progression` is just `list[str]` with no enum validation at the schema layer, so nonstandard numerals pass Pydantic fine and only surface as a problem (or don't) once `harmony.py` tries to parse them into chords. Worth tracing `harmony.py`'s chord-symbol parser directly rather than assuming the schema would have caught it — it wouldn't have.
