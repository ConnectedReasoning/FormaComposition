# Background Music — Design Principles → FormaComposition Practice

For extended-play / focus / sleep pieces. Goal: ignorable-as-interesting, not memorable.

| Principle | FormaComposition Practice |
|---|---|
| **Minimize rate of new information, not layer count** | `harmony_rhythm.rhythm: "sustain"` for zero-motion harmony (ignore `harmony_rhythm.density` — it's a no-op under `sustain`). Short `progression` (2–4 chords) with long `chord_bars`. Long section `bars`, few section boundaries. Melody `rhythm: "free"` with a wide `note_length_range`, not `rhythm: "motif"`. Section `density: "low"`/`"sparse"`. All 5 layers can stay active — the constraint is event rate per layer, not layer count. |
| **No hooks, on purpose** | Avoid `melody: "develop"` on `voices[0]`; use `lyrical` or `sparse` instead. Leave `transform_pool` empty, or limit to `augmentation`/`diminution` (rhythm-only, no pitch identity). Narrow `register` (SATB band, not full octave+). Leave `harmony_rhythm.motif` unset — one undifferentiated harmonic bed, not two competing ideas. Favor static/modal progressions (`i`, `bVII`, `IV` loops); avoid strong V→I / V→vi cadences as section endings. |
| **Silence is a texture, not a gap** | Push melody `rest_probability` up meaningfully. For bass rests, use `bass_style: "root_only"`, `"pedal"`, or `"steady"` — `bass_rest_probability` is refused on `walking`/`melodic`. Note: `harmony_rest_probability` is a no-op under `sustain`; if audible harmonic rests matter more than total stillness, use `harmony_rhythm.rhythm: "pattern"`/`"motif"` with rests in the onset grid instead — pick one deliberately, they trade off against each other. |
| **Survives repetition (the 40th-listen test)** | Vary `velocity` per section — inner-voice flatness is an engine-wide unfixed constant, cheap high-leverage fix. Gentle macro-arc across the whole form (`breath`, `swell` at section level) even while each section stays internally `plateau`. Very low `swing` on bass (`melodic`/`motif` only) for felt-not-noticed variation. Don't randomize seed per render as a substitute for real variation — that breaks reproducibility without adding musical variety. |

## Note on evaluation

`slop_metrics.py` thresholds are calibrated for pop/hook-driven output. Motif-identity FAIL <10%/WARN <25% will flag correctly-built ambient pieces as failures — low motif identity is the *goal* here, not a defect. Leap-profile and harmony-mass thresholds still apply. Consider a separate background-music profile for the tool rather than reading its default verdict at face value on these pieces.
