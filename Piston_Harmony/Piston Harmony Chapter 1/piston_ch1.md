# Piston — Harmony: Chapter 1
## Scales and Intervals

> *The unit of harmony is the interval.*

---

## Core Premise

The interval is the fundamental unit of harmony — not the chord, not the scale. Everything else is built from pairs of notes and their relationships.

---

## Scales (Three Only)

Piston recognizes three scales as the basis of common-practice music:

**Major** — the baseline reference. All intervals are named relative to major scale degrees.

**Harmonic minor** — raised VII creates the leading-tone pull. The augmented second between VI and VII is a *harmonic* feature, not a melodic one.

**Melodic minor** — raises VI *and* VII ascending to smooth the augmented second; reverts to natural descending. Piston's simplification: major and minor scales differ only in III and VI — everything else is identical.

**Chromatic scale** — treated as a variant/alteration of the other two, not an independent system.

*(Modes are not discussed here — they appear in Ch. 4, Tonality and Modality.)*

---

## Scale Degree Names

| Roman | Name | Notes |
|---|---|---|
| I | Tonic | Key center |
| II | Supertonic | One step above tonic |
| III | Mediant | Halfway tonic → dominant |
| IV | Subdominant | As far below tonic as V is above |
| V | Dominant | "Actually a dominant element in the key" |
| VI | Submediant | Halfway down tonic → subdominant |
| VII | Leading-tone | Strong melodic pull toward tonic |

These names are the vocabulary for harmonic function — directly what Roman numeral progressions encode.

---

## Interval Classification

Two layers:

**General name** — count lines and spaces between the two notes: second, third, fourth... ninth.

**Specific quality** — measure against the major scale built on the *lower* note:

| Result | Quality |
|---|---|
| Coincides with major scale degree | **major** (or **perfect** for unison, 4th, 5th, octave) |
| Half-step smaller than major | **minor** |
| Half-step larger than major/perfect | **augmented** |
| Half-step smaller than minor/perfect | **diminished** |

**Compound intervals:** Anything beyond an octave. The ninth is a "characteristic feature of certain harmonic forms" — it carries its own harmonic identity, not merely an octave-transposed second.

---

## Consonance vs. Dissonance

**Consonant:** perfect intervals + major/minor thirds and sixths

**Dissonant:** augmented/diminished intervals + seconds, sevenths, ninths

*(Exception: perfect fourth is dissonant when there is no third or perfect fifth below it.)*

Imperfect consonances (thirds and sixths) are set apart from perfect consonances — the sixth in certain tonal relationships with the bass can lack stability and need resolution to the fifth.

> *"Music without dissonant intervals is often lifeless and negative, since it is the dissonant element which furnishes much of the sense of movement and rhythmic energy."*

This is the theoretical grounding for why static consonant textures produce lifeless output. Dissonance is not decoration — it is structurally necessary for energy and movement.

---

## Inversion of Intervals

Three types:

**True (mirror) inversion** — intervals extend equal distances in opposite directions from a common point. Rare; mostly academic. The systematic application is "mirror-writing."

**Contrapuntal inversion** — same scale kept for both forms; voices swap positions. Common in counterpoint. The general name stays the same but the specific name may differ.

**Harmonic inversion** — the lower note becomes the upper (or vice versa). Both the general *and* specific names usually change. Example: major 6th inverts to minor 3rd.

This is the foundation for chord inversions. When the bass plays the third or fifth instead of the root, that is harmonic inversion.

---

## Enharmonic Intervals

Same sound, different spelling (e.g., augmented second vs. minor third). They are distinguishable in harmonic context even when acoustically identical in isolation.

This is why Roman numeral spelling matters: `bVII` and `#VI` may produce the same MIDI pitch but carry different harmonic meaning and different resolution tendencies.

---

## FormaComposition Implications

**The consonance/dissonance table is a tension map.** Consonant intervals = stable/resolved; dissonant intervals = energy/movement. The `arc` and `density` fields gesture at this; Piston gives the underlying mechanism.

**The leading-tone (VII → I) is the strongest single force in tonal harmony.** It is why dominant chords are powerful — the V chord contains the leading-tone. Ch. 13 (Dominant Seventh) will formalize this.

**Static consonant pads are a structural problem, not just an aesthetic one.** Piston is explicit: dissonance is what generates rhythmic energy. Chord voicings need dissonant intervals to have life.

**Enharmonic equivalence in MIDI requires harmonic context to resolve correctly.** The engine must track harmonic function, not just pitch class, or resolution logic breaks.

---

*Source: Walter Piston, Harmony (revised edition, 1948 / reissued 1959). Chapter 1, pages 3–9.*
