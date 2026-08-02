# Pop / Hook-Driven Music — Design Principles → FormaComposition Practice

For song-form, short-play pieces. Goal: a hook the listener notices and recalls after one listen.

| Principle | FormaComposition Practice |
|---|---|
| **Simplicity in service of catchiness, not restraint** | Short `progression` (3–4 chords) built around real functional movement (V→I, V→vi), not static modal loops. `chord_bars` short relative to section length so chords turn over and go somewhere. Keep `harmony_rhythm.rhythm` off `sustain` for hook sections — use `motif` or `pattern` so harmony has its own forward motion. |
| **The hook is the point** | `melody: "develop"` on `voices[0]`, with `transform_pool` pruned to `inversion`/`retrograde`/`shuffle`/`sequence` so identity keeps recurring recognizably. `rhythm: "motif"` on the lead (not `free`) — the rhythmic stencil should be anchored and recognizable. One deliberate wide-`register` leap at the hook's peak, contrasted against narrower register elsewhere (some leap is good — the `slop_metrics` failure mode is ≥35%/10%, not leap itself). `bass_style: "motif"` so bass reinforces the hook rather than running an independent line. |
| **Repetition builds the hook, doesn't hide it** | `form_type: "song"` with an explicit `form[]`; reuse the same `section` entry for repeated choruses, `exact_repeat: true` where the chorus should return byte-identical. Use a bridge/contrast section with a different `arc` (`build`/`breath`) and optional `key`/`mode` override so the hook's return afterward reads as a return. Keep the chorus's transform static across repeats (don't let `transform_sequence` wrap a different transform onto it each time) — reserve transform variation for verses/bridge. |
| **Rate of new information is high, but focused** | Higher `harmony_rhythm.density` and section `density: "full"` at the hook, dropping to `"medium"`/`"sparse"` in verses — contrast section-by-section, not uniform across the piece. Low `rest_probability` and low `bass_rest_probability` at the hook (continuous presence); allow more space off-hook. Thin or lower `velocity` on counterpoint/peer `voices[]` during the hook specifically so nothing competes with the lead. |

## Note on conflation risk

This bundle (`progression` length, `harmony_rhythm.rhythm`, `density`, `transform_pool`) is the near-exact inverse of the background-music bundle on the same fields. A piece cannot honor both — half-applying one (e.g., a `develop` hook melody sitting over `harmony_rhythm: "sustain"`) is the specific failure mode to check for when reviewing older catalog pieces.
