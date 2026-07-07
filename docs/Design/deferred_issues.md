# FormaComposition — Deferred Issues Log
Compiled from working sessions through July 2026. These are known, real gaps — each was found and verified against actual code, not speculated. None are fixed. Logged here so a future session doesn't have to re-derive them from scratch, and so a "surprising" render result can be checked against this list before being mistaken for a new bug.

---

## Large — architectural, needs its own dedicated session

### 1. No real time-signature / compound-meter support
`beats_per_bar` is a bare pulse count with no concept of a denominator anywhere in the generative logic — nothing distinguishes "6 quarter-note pulses" from "6 eighth-note pulses grouped as 2 dotted-quarter beats" (i.e. true 6/8 feel). This affects several places that all currently assume simple meter with quarter-note pulses:
- `GROOVES` templates in `rhythm.py` are bar-relative and quarter-note-implicit.
- `apply_swing()`'s eligibility check (`beat % 1.0 == 0.5`) assumes the offbeat-eighth convention of simple meter; this isn't the right test in compound meter.
- `_motif_rhythm_to_events`' articulation/priority filtering has the same implicit assumption.

**Fixed as of the last session:** the MIDI file's displayed time signature now at least matches `beats_per_bar` as a numerator (previously hardcoded to always show 4/4 regardless of actual data — this part is resolved). What's still missing is true subdivision/accent semantics for compound and odd meters. This blocks writing anything that isn't effectively simple meter (no real 6/8, 7/8, prog-rock-style meter changes, etc.) with correct-feeling results.

**Scope:** comparable to a full modulation feature (see #2) — not a small patch, needs deliberate design before code.

### 2. No true mid-section modulation (real key change)
Secondary dominants (`V7/ii` syntax) are implemented and working — they tonicize a chord for a beat without leaving the key. What's still missing is an actual pivot-chord modulation: a chord partway through a progression permanently changing the tonal center for everything after it. This would require the section schema to carry a per-chord (not per-section) key/mode override, `resolve_progression` switching reference frames mid-list, and every downstream consumer of "the section's key" (melody scale tones, bass scale tones, counterpoint) knowing which key applies at which beat rather than assuming one key per section.

**Status:** deliberately not started. Real design work, real blast radius across files. Start this only when a specific piece actually needs it, not speculatively.

### 3. Sequence transposition for repeated progressions (Bach-style sequences)
Discussed, not built, no syntax agreed yet. The idea: repeat a progression pattern but transpose it by a schedule each pass (e.g. `"sequence_transpose": [0, 2, 4]` alongside a base progression) — the classical technique of moving the same harmonic shape to a new tonal center each repetition, rather than repeating it verbatim. Bounded and buildable, but needs a syntax decision before code, same as everything else this session that touched the schema.

---

## Medium — real, scoped, but with a real tradeoff attached

### 4. `melody: "develop"` can desync a motif's authored rest from its intended beat
`generate_develop` rolls its own second, independent random transform on top of whatever the theme's motif already went through upstream. Since rest positions get reordered by whichever transform each side independently picked, a rest authored at beat 3 can end up sounding at a different beat than the fixed timing grid expects. Verified concretely — it never crashes and never changes the *count* of sounding notes (every transform is a reordering/negation, never an insertion or deletion), so this shows up as "the rest isn't exactly where I put it," not as a broken render.

**Decision (explicit, not an oversight):** left unmitigated on purpose — could produce a happy accident. Only affects `melody: "develop"` sections; every other melody behavior doesn't do the second transform and isn't affected. Revisit only if it actually produces something you don't want, not preemptively.

### 5. `groove` is completely unconsumed when `rhythm: "motif"` is set
`_motif_rhythm_to_events` has no `groove` parameter at all — any `groove` value on a section using motif-driven rhythm (or `harmony_rhythm.rhythm: "motif"`) is silently inert. Three options were laid out and none were built:
- **A — groove as accent only:** look up each motif onset's `beat % beats_per_bar` against the groove template and apply its velocity accent, without touching timing. The original objection (accents would drift unpredictably if the motif's cycle length wasn't a multiple of the bar) is now moot, since the motif-length-vs-`beats_per_bar` validator (shipped this session, see bottom of this doc) guarantees that alignment for anything that gets past validation — worth reconsidering now that constraint exists.
- **B — groove as onset filter (thin notes by priority):** rejected outright — no principled way to map an independently-cycling motif's onsets onto a bar-relative template without arbitrary, potentially rhythm-corrupting assumptions.
- **C — leave it inert, but warn:** flag when both `rhythm: "motif"` and a `groove` value are set on the same block, so it's a known no-op instead of a silent one.

**Status:** investigated, not decided. No warning currently exists either — a `groove` value next to `rhythm: "motif"` still fails silently today.

---

## Small — known gaps, low urgency, worth remembering rather than fixing now

### 6. Secondary dominants untested in Locrian
The interval math (`scale[applied_degree] - scale[0]`, added on top of the target's root) is mode-invariant for 6 of the 7 supported modes — but Locrian's 5th degree sits at +6 semitones instead of the usual +7, since Locrian has no perfect fifth from its own tonic. The code should handle this correctly automatically (it reuses the mode's own scale table rather than hardcoding an interval), but it has not actually been rendered and verified in Locrian. Low priority — deliberately deferred ("we'll get to it when we get to it").

### 7. `section.motif` / `section.motifs` overrides are documented but not implemented
The schema and cheat sheet describe these as restricting or overriding the theme's motif pool for a specific section. `generator.py`'s actual motif resolution never reads them — only the theme's pool is ever consulted at render time, regardless of what a section's `motif`/`motifs` field says. Found incidentally while building the motif-length validator (shipped this session, see bottom of this doc), which is why that validator checks the theme's pool only — checking a section override that's never actually consulted would be misleading. If this ever gets implemented for real, the validator's candidate-resolution logic needs to be revisited alongside it.

---

## Resolved this session, listed here only for cross-reference
Motif-length-vs-`beats_per_bar` validation (a motif's rhythm must sum to a whole multiple of the section's beat count, or the piece refuses to build), the MIDI time-signature display bug, secondary-dominant notation, the `swing` semantics bug, the bass motif chord-tone snapping bug, and motif-authored rests are all shipped and verified — not reproduced here since they're closed, not deferred.
