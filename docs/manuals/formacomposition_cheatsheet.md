# FormaComposition JSON Cheat Sheet
Source: `intervals/core/schemas.py` (Pydantic v2) + `intervals/music/rhythm.py` (groove data). Not inferred from example files — pulled from the actual validators.

---

## THEME (`theme_*.json`)

### `theme` (top-level object)
| Field | Type | Required | Notes |
|---|---|---|---|
| `name` | string | no | free text |
| `key` | string | **yes** | any non-empty string (not enum-checked at theme level — see Section `key` below for the actual enum used at render time) |
| `mode` | string | **yes** | any non-empty string at theme level (not enum-checked here — see Section `mode` for the enforced enum) |
| `tempo` | object `{min, max}` | **yes** | see TempoRange below |
| `motif` | object | one of `motif`/`motifs` | single motif, see Motif below |
| `motifs` | array of motif objects | one of `motif`/`motifs` | if both present, `motifs` wins and `motif` is ignored (warning, not error). Must be non-empty if present. Missing both → warns, generation still works (purely generative) |

`extra="allow"` — you can add documentation fields freely; only `palette` is flagged obsolete (warns: "instruments live in Logic").

### `tempo` (TempoRangeModel)
| Field | Type | Range |
|---|---|---|
| `min` | int | 20–300 |
| `max` | int | 20–300, must be ≥ `min` |

### `motif` / each entry in `motifs[]` (MotifModel)
| Field | Type | Required | Notes |
|---|---|---|---|
| `name` | string | no | |
| `intervals` | array of int | **yes**, min 1 entry | **semitones**, not scale steps (this bit you before — v2 slack key note confirms) |
| `rhythm` | array of float | no | beat durations; needed if any section uses `rhythm: "motif"` |
| `velocities` | array of float | no | must match `rhythm` length if present; **0.0–1.0 scale multipliers, not raw MIDI velocity** (0.8, not 80/102 — this is explicitly guarded because it silently overflows into invalid MIDI bytes downstream) |
| `transform_pool` | array of TransformLiteral | no, defaults `[]` | see Transform enum below |

`extra="allow"` on motif too.

---

## PIECE (`piece_*.json`)

### `piece` (top-level object, PieceModel)
| Field | Type | Required | Notes |
|---|---|---|---|
| `title` | string | no | |
| `tempo` | int | no | 20–300. If omitted, warns and falls back to theme tempo midpoint |
| `seed` | int | no, default 42 | |
| `form_type` | `"narrative"` \| `"song"` | no, default `"narrative"` | |
| `sections` | array (narrative) or dict (song) | conditional | narrative form → non-empty list required; song form → dict of named section defs required |
| `form` | array of SongFormEntry or string | song form only | required if `form_type: "song"`; each entry's `section` name must exist in `sections` dict |
| `transform_sequence` | array of TransformLiteral | no | warns if shorter than section count (wraps/repeats) |

`extra="allow"` at piece level, and note the loader accepts either `{"piece": {...}}` (what your files use) or a flat dict.

### Section (SectionModel) — narrative `sections[]` entries or song-form `sections{}` values
| Field | Type | Required | Range / Enum |
|---|---|---|---|
| `name` | string | no | |
| `key` | string | no | overrides theme key. **Enum-checked**: `C, C#, D, D#, E, F, F#, G, G#, A, A#, B, Db, Eb, Gb, Ab, Bb` |
| `mode` | string | no | overrides theme mode. **Enum-checked** (case-insensitive): `ionian, dorian, phrygian, lydian, mixolydian, aeolian, locrian` |
| `motif` | string \| dict | no | overrides theme motif pool for this section (single) |
| `motifs` | array of string\|dict | no | restricts pool to exactly these |
| `progression` | array of string | **yes**, min 1 | chord symbols (e.g. `"I"`, `"vi"`, `"I7"`) — **not enum-validated**; typos/unsupported Roman numerals (your open `ii`/`VI` question) pass schema validation and only fail (or silently misbehave) downstream in `harmony.py` |
| `chord_bars` | array of float | no | per-chord bar durations; length must match `progression`; if given, overrides/derives `bars` (mismatch → warning, `chord_bars` wins) |
| `bars` | float | no | defaults to 8 with a warning if neither this nor `chord_bars` given |
| `beats_per_bar` | int | no, default 4 | 1–16 |
| `density` | enum | no, default `"medium"` | `low, sparse, medium, high, full` — **see density gotcha below** |
| `melody` | enum | no, default `"generative"` | `lyrical, generative, motif, sparse, rhythmic, develop` |
| `bass_style` | enum | no, default `"root_fifth"` | `root_fifth, walking, pedal, arpeggiated, sparse, root_only, melodic, steady, pulse` |
| `arc` | enum | no, default `"swell"` | `swell, fade, build, plateau, decay, fade_in, fade_out, breath` |
| `rhythm` | enum | **yes**, no default | `motif, pattern, free` |
| `harmony_rhythm` | object | no | see HarmonyRhythm below. **Must be an object** — `"harmony_rhythm": "sustain"` as a bare string raises an error; use `{"rhythm": "sustain"}` |
| `rhythm_pattern` | object | conditional | required if `rhythm: "pattern"` |
| `harmony_pattern` | object | conditional | required if `harmony_rhythm.rhythm: "pattern"` |
| `groove` | string | no | must be a key in `GROOVES` (see Groove list below) — validated at render time in `rhythm.py`, not at schema level |
| `swing` | float | no, default 0.0 | 0.0–1.0 |
| `rest_probability` | float | no, default 0.0 | 0.0–1.0 |
| `fugal_techniques` | dict | no | untyped |
| `counterpoint` | object or array | no | up to 3 voices (>3 raises an error); bare object form auto-wrapped into a 1-item list |
| `voices` | array of Voice objects | no | peer voices, replaces melody+counterpoint. **Schema-complete but unimplemented in the generator** per your notes — confirmed still true in this codebase snapshot |
| `drums` | string or object | no | bare string like `"four_on_floor"` is coerced to `{"pattern": "four_on_floor"}` |
| `percussion` | dict | no | untyped, future-proofed |
| `notes` | string | no | free text |

Unknown keys outside the known set warn (not error) — good for catching typos.

### `harmony_rhythm` (HarmonyRhythmModel)
| Field | Type | Enum/Range |
|---|---|---|
| `rhythm` | enum, optional | `motif, pattern, sustain, free` (cascades: `harmony_rhythm.rhythm` → `section.rhythm` → `"free"` if all omitted) |
| `density` | enum, optional | `low, sparse, medium, high, full` |
| `groove` | string, optional | must be a valid `GROOVES` key |
| `swing` | float, default 0.0 | 0.0–1.0 |
| `note_duration` | enum, optional | `whole, half, quarter, eighth` |

**Note:** `"groove": "swing"` — the field you flagged as unconfirmed — is **not** a valid groove name. `swing` is a separate float parameter (0.0–1.0) applied on top of a groove, not a groove itself. If any piece file has `"groove": "swing"`, that will raise `ValueError: Unknown groove` at render time. Valid groove names are listed below.

### `counterpoint[]` entries (CounterpointModel)
| Field | Type | Default | Enum/Range |
|---|---|---|---|
| `species` | enum | `"free"` | `free, first, second, third, fourth, fifth` |
| `register` (alias for `cp_register`) | enum | `"below"` | `above, below` |
| `dissonance` | enum | `"passing"` | `none, passing, neighbor, free` |
| `velocity` | int | 58 | 1–127 |
| `canon_offset` | float | 0.0 | ≥ 0.0 |
| `rhythm_density` | enum | `"medium"` | `sparse, medium, full` — only matters for `species: "free"`; `"first"` species is always note-against-note regardless |
| `groove` | string, optional | — | valid `GROOVES` key |

### `voices[]` entries (VoiceModel) — unimplemented in generator, schema only
| Field | Type | Default | Enum/Range |
|---|---|---|---|
| `register` (alias for `v_register`) | enum | `"mid"` | `high, mid, low_mid, low, above, below` — pitch ranges: high=G4–E6, mid=C4–A5, low_mid=C3–A4, low=C2–A3 |
| `behavior` | enum | `"lyrical"` | same MelodyLiteral set as section `melody` |
| `velocity` | int | 64 | 1–127 |
| `motif` | string \| dict, optional | — | name from theme pool or inline dict |
| `rhythm` | enum | `"free"` | `motif, pattern, free` |
| `species` | enum, optional | — | if present → counterpoint.py path; if absent → melody.py path |
| `dissonance` | enum | `"passing"` | `none, passing, neighbor, free` |
| `canon_offset` | float | 0.0 | ≥ 0.0 |
| `rest_probability` | float, optional | — | 0.0–1.0, overrides section default |

### `drums` (DrumModel)
| Field | Type | Default |
|---|---|---|
| `pattern` | string | `"four_on_floor"` |
| `density` | enum, optional | `low, sparse, medium, high, full` — `None` inherits section density |
| `groove` | string, optional | `None` inherits section groove |
| `swing` | float, optional | `None` inherits section swing |

### `rhythm_pattern` / `harmony_pattern` (RhythmPatternModel — from `rhythm_extract.py`)
| Field | Type | Notes |
|---|---|---|
| `onsets` | array of float | required |
| `durations` | array of float | required, same length as `onsets` |
| `velocities` | array of float, optional | same length as `onsets`; 0.0–1.0 scale multipliers, same overflow warning as motif velocities |
| `length_beats` | float | default 8.0, must be > 0 |

### Song form: `form[]` entries (SongFormEntryModel)
| Field | Type | Default |
|---|---|---|
| `section` | string, required | name must exist in `sections{}` dict |
| `variation` | float | 0.0, range 0.0–1.0 |
| `exact_repeat` | bool | `false` — set `true` for true verbatim chorus repetition |

---

## Enum reference (all Literal values)

- **Density**: `low, sparse, medium, high, full`
- **Melody**: `lyrical, generative, motif, sparse, rhythmic, develop`
- **Bass style**: `root_fifth, walking, pedal, arpeggiated, sparse, root_only, melodic, steady, pulse`
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



The `ii`/`VI` Roman-numeral question in Still Cove is real but different in kind: `progression` is just `list[str]` with no enum validation at the schema layer, so nonstandard numerals pass Pydantic fine and only surface as a problem (or don't) once `harmony.py` tries to parse them into chords. Worth tracing `harmony.py`'s chord-symbol parser directly rather than assuming the schema would have caught it — it wouldn't have.
