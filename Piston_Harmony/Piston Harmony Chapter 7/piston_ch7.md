# Piston — Harmony: Chapter 7
## Harmonization of a Given Part

> *True harmonization means a consideration of the alternatives in available chords, the reasoned selection of one of these alternatives, and the tasteful arrangement of the texture of the added parts with due regard for consistency of style.*

---

## What Harmonization Actually Is

Harmonization is **not** the goal. The ability to put chords under a melody is a by-product of understanding harmony, not the point of studying it. What makes it valuable as an exercise is the mental discipline: you are forced to enumerate alternatives, weigh them, and choose. This mirrors exactly what a composer does.

> *"Any melody is capable of suggesting more than one choice of chords."*

There is no single "correct" harmonization. There are better and worse ones. The difference lies in how well the chosen chords serve unity, variety, voice leading, harmonic rhythm, and style — simultaneously.

---

## Step 1 — Determine the Tonality

Before touching a chord, analyze the melody for its key. Look at:
- **Range** — what pitches appear; what accidentals
- **The final note** — often but not always the tonic
- **The cadence point** — the harmonic formula at the end reveals the key most reliably
- **Mode** — does the sixth and seventh suggest major, harmonic minor, melodic minor?

A melody of restricted range may offer **several possible keys** even before introducing inversions or chromaticism. A melody that ends on G could be in C (V), G (I), D (IV), E minor (III), or A minor (VII). The cadential context narrows it down.

Work out multiple harmonic readings when the key is ambiguous. The final choice depends on which reading best serves the harmonic goals of the whole phrase.

---

## Step 2 — Determine Harmonic Rhythm

Before assigning specific chords, decide roughly how often the harmony will change. Options:
- One chord per melody note (maximum density — often too busy)
- One chord per beat
- One chord per measure
- Varying (the norm — mix of long and short)

**Melodic skips** are a key indicator: when a melody moves by skip, both notes of the skip are likely chord tones of the **same chord**. The skip is the arpeggio of a single harmony. Changing chord on a skip is possible but requires a harmonic rhythm reason (weak-to-strong motion).

> *"When a melody moves by skip, it is likely that the best procedure will be to use the same harmony for both notes."*

Exception: if the skip happens at a point where harmonic rhythm naturally moves from weak to strong — the second chord of the skip can fall on the strong beat as a chord change.

**Sustained tones** create the opposite opportunity: a melody note held through two beats or more can serve as a **common tone** for two different chords. The harmony changes while the melody stays — a textural effect that multiplies variety from a single note.

---

## Step 3 — Available Chords Per Melody Note

The core analytical move. Any given melody note can be:
- The **root** of a chord built on that note
- The **third** of a chord whose root is a third below
- The **fifth** of a chord whose root is a fifth below

This gives **three possible triads** for every note. In C major, the note E can be:
- Root of III (E minor)
- Third of I (C major — E is the third of C-E-G)
- Fifth of VI (A minor — E is the fifth of A-C-E)

Write out all three interpretations for every note in the melody. This is the raw material from which the selection is made.

### The Grid in Practice

For the melody note-by-note, write three rows of Roman numerals: one for each possible chord interpretation. This produces a grid of options. Most notes will have 2–3 viable chords; some positions (like the final note) narrow quickly to 1–2.

---

## Step 4 — Selection

With the grid in hand, begin eliminating:

**Start from the cadence.** The last chord is almost always V or I. Working backward from the cadence, the penultimate chord must fit with V or I. This constrains the choices at the end of the phrase first, then propagates backward.

**Apply elimination rules:**
1. **Parallel octaves and fifths** — eliminate any chord transition that would produce these between any voice pair
2. **Poor bass line** — a bass that skips constantly has no contrapuntal identity; prefer chords that give the bass a coherent melodic line
3. **Unity** — avoid using VI when the same position could use I (if the phrase already has plenty of variety)
4. **Variety** — once the phrase skeleton is clear, find the one moment to use a modal degree (III or VI) for color
5. **Voice leading** — prefer chord changes that keep common tones and move other voices by step

### The VII Caution
VII in root position produces a doubled leading-tone in four-part writing — almost always wrong. When a melody note could be harmonized as VII root position, that option should nearly always be eliminated.

### The II Caution in Measure 2
Piston works through a specific example: II on the second beat of measure 2 would require the bass to move in a way that creates parallel octaves with the subsequent I chord. The analytical step of checking voice-leading consequences before committing is the key discipline.

---

## Use of Formulae

Rather than treating every melody note as an isolated chord problem, recognize melodic figures as **the upper voice of known harmonic formulae**. A group of four conjunct quarter notes ascending could be the soprano of IV–I–V–I, or II–V–I–VI, or other known patterns.

> *"One recognizes an upper voice of one of the formulae as part of the melody and the stage of considering alternate chords becomes a stage of considering alternate formulae."*

This is how experienced composers work — they hear a melodic contour and retrieve a harmonic formula from memory, then adapt it. The formulae vocabulary (built from Ch. 3's root progression table and Ch. 6's phrase structures) is the engine of fast, idiomatic harmonization.

---

## Division into Phrases

A longer melody must be divided into phrases before harmonization. Phrase breaks are usually signaled by:
- An obvious **resting point** or break in the melodic line
- A note held longer than surrounding notes
- A point of registral change (leap followed by sustained note)

When the melody does not make phrase breaks obvious, it is the harmonic rhythm's job to **create** them — by arriving at a cadential formula (half or authentic) at a structurally plausible point, even when the melody alone is ambiguous. The harmony punctuates the melody's prose.

---

## Criteria for a Good Harmonization

Piston's summary at the end of the chapter — these are the standards against which a harmonization is judged:

1. **Maintains tonality** — the harmony makes the key clear and keeps it clear
2. **Has something unexpected** — "the harmony should at some moment present some aspect which is not entirely commonplace and expected"
3. **Good contrapuntal bass** — the bass is an independent melodic line, not just root-hopping
4. **Harmonic rhythm corroborates the pulse** — the rate of chord change confirms the metric structure and adds interest where the given melody has none
5. **Consistent style** — all added parts (bass, inner voices) match the rhythmic and melodic style implied by the given part

---

## FormaComposition Implications

**Every melody note in FormaComposition has exactly three candidate chords — this is the basis for the melody-to-harmony binding logic.** The engine currently generates a melody over a predetermined chord progression. Piston's framework suggests the inverse is also compositionally valid: derive chord possibilities *from* the melody and select based on context. Both directions are useful; the note-as-root/third/fifth framework is the connection.

**The skip rule is a chord-duration heuristic.** When the melody skips, hold the chord. When the melody moves by step, the chord can (but doesn't have to) change. This gives a mechanical way to derive a `harmony_pattern` from the melody's interval content: long chord durations at skips, potential chord changes at stepwise motion.

**Formulae recognition is the mature version of chord generation.** Instead of evaluating each note independently, the engine could recognize melodic contours as matching known harmonic formulae and select the whole formula at once. This is more musically idiomatic and less prone to note-by-note optimization traps. It's also how the prosody module could be extended — not just note selection, but formula selection from melodic shape.

**The bass as contrapuntal line is a design principle for the bass voice.** FormaComposition's bass module should be generating a *melodic* bass line, not just playing roots. A bass that follows the root progression mechanically fails criterion 3. The `walking` and `melodic` bass styles address this; `steady` (root only) fails Piston's standard unless the texture specifically calls for it.

**"Something unexpected" is a first-class requirement, not a nice-to-have.** Piston states it directly: a harmonization without an unexpected element is inadequate. This is the formal rationale for FormaComposition's `arc` field, motif transforms, and the use of modal degrees — they exist to provide the "not entirely commonplace" moment every phrase needs. If a section's progression never introduces a chord that wasn't predictable from the root progression table, it needs revision.

**The cadence drives backward, not forward.** When determining which chord to use at any given point, the most important constraint is what cadence the phrase ends on. Start from the end, constrain backward. The FormaComposition validator could check this: does the section's final chord progression form a recognizable cadence?

---

*Source: Walter Piston, Harmony (revised edition, 1948 / reissued 1959). Chapter 7, pages 67–76.*
