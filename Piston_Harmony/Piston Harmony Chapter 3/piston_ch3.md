# Piston — Harmony: Chapter 3
## Harmonic Progression

> *The individual sonority of the two chords is of far less importance than the relation of the two roots to each other and to the scale from which they are drawn.*

---

## The Two Questions of Progression

When chords follow one another, two things must be decided simultaneously:

1. **Which chord comes next** — the choice of root succession
2. **How the voices connect it** — the procedure of voice leading

These are inseparable in practice but can be studied independently. Crucially: **root succession is primary**. No change in chord quality or voicing can fix a bad root progression. The Roman numeral relationship between roots governs everything.

Chord succession can always be reduced to **root succession** — a sequence of scale degrees. The variety of chords built on those roots is secondary.

---

## Table of Usual Root Progressions

This is the central reference table of tonal harmony. Learn it cold.

| From | Strong / Usual | Sometimes | Less Often |
|---|---|---|---|
| **I** | → IV, V | → VI | → II, III |
| **II** | → V | → VI | → I, III, IV |
| **III** | → VI | → IV | → II, V |
| **IV** | → V | → I, II | → III, VI |
| **V** | → I | → VI, IV | → III, II |
| **VI** | → II, V | → III, IV | → I |
| **VII** | → III | *(rarely used in root position)* | |

### The quality of root motion

Three types of root movement, each with a distinct effect:

**Root moves down a fifth (= up a fourth):** The strongest progression. V→I is the paradigm — the dominant-to-tonic resolution is the most satisfying motion in tonal harmony. "One can easily sense the repose." Other down-a-fifth progressions (II→V, VI→II, III→VI) have an analogous, if less marked, effect. These are **strong progressions**.

**Root moves by step:** Produces an entirely new set of notes — maximum harmonic color change. These are also strong but in a different way — they introduce fresh tonal material rather than resolving tension.

**Root moves up a third (= down a sixth):** A very soft, low-contrast effect. I→III, I→VI, IV→VI. Common tones are shared, the harmonic change is gentle. These are **weak progressions** — not wrong, but low-energy. Use deliberately for relaxation and continuity, not for drive.

---

## Special Cases

### The Leading-Tone Triad (VII)
Rarely used in root position. Contains the diminished fifth, making it a dissonant chord. Its lower note is the leading-tone itself, with strong pull toward the tonic. Piston treats it as an **incomplete dominant seventh** — it behaves like V7 with the root omitted. Resolves to I or III (sequential contexts only).

### The Diminished Triad on II in Minor
The II chord in minor is diminished (like VII in major) but differs in one important way: its lower tone is *not* a tendency tone with strong directional pull. Composers have used it freely in root position, unlike VII. Resolves naturally to V.

### The Augmented Triad on III in Minor
The only augmented triad in common practice. Contains an augmented fifth between root and top tone (the leading-tone). **Double the third** — which is the fifth scale degree, the dominant. This sidesteps the leading-tone doubling problem and the augmented fifth instability.

---

## Voice Leading

Once root succession is decided, the voices must be connected. The goal is always **smoothness** — making one chord flow into the next.

### Rule 1 — Common tones
If the two chords share one or more notes, **hold the common tone(s) in the same voice**. The remaining voice(s) move to the nearest available position.

> **Exception — II→V:** Do *not* hold the common tone. Instead, move all three upper voices down to the next available position. This produces better melodic lines.

### Rule 2 — No common tones
If the two chords share no tones, the **three upper voices move contrary to the bass**, always to the nearest available position.

> **Exception — V→VI (the Interrupted/Deceptive Cadence):**
> The ear expects V→I; V→VI is the "deceptive" surprise. Because the leading-tone (in V) has strong upward pull to the tonic, it moves *up* one step to the tonic. The other two upper voices then descend to the nearest chord tones of VI. This results in the **third of VI being doubled** instead of the root — the standard doubling rule is suspended here.

---

## Relative Motion Between Voices

Two voices can relate in three ways:

| Type | Definition | Use |
|---|---|---|
| **Contrary** | Moving in opposite directions | Most independence; preferred |
| **Oblique** | One voice stationary, other moves | Useful contrast |
| **Similar** | Both moving in same direction | Use with care |

**Parallel motion** is similar motion at a fixed interval. Some parallel intervals are prohibited, others are encouraged:

| Interval | Status | Reason |
|---|---|---|
| Parallel unisons | **Forbidden** | Voices merge; lose independence |
| Parallel octaves | **Forbidden** | Voices merge; lose independence |
| Parallel perfect 5ths | **Forbidden** | Hollow sound; voices lose independence |
| Parallel 3rds | **Good** | Common and pleasing |
| Parallel 6ths | **Good** | Common and pleasing |
| Parallel 4ths | **OK if** supported by parallel 3rds below | Needs harmonic grounding |
| Parallel dissonant intervals | **Occasional** | Only in specific nonharmonic and irregular resolution contexts |

### The Direct Octave and Fifth
Approaching a perfect octave or fifth by **similar motion with a skip in one voice** is called a direct (or hidden) octave/fifth. Generally avoided, especially between soprano and bass (the outer voices). Exception: the upper voice may move by a minor second acting as a leading-tone.

---

## The Tritone and False Relation

The tritone (augmented 4th / diminished 5th = 6 semitones, *diabolus in musica*) is the one interval that produces a "cross-relation" or **false relation** when it appears between successive tones in different voices.

The practically important case: **V→IV in root position.** The leading-tone in V and the bass of IV form a tritone across the barline between different voices. This is almost always avoided. The progression V→IV is itself rare for this reason.

False relation is **acceptable** when the tritone appears melodically in a *single* voice, or when the leading-tone is in an inner voice where the effect is less prominent.

---

## Overlapping Voices

When two voices move upward in similar motion, the lower voice must not move *above* the position just vacated by the upper voice. Same rule in reverse for descending motion. This avoids melodic ambiguity — the ear would follow an apparent continuation between the two voices that was not intended.

---

## Melodic Quality of Individual Lines

**Conjunct motion** — movement by step.
**Disjunct motion** — movement by skip.

A good melodic line contains **mostly conjunct motion**, with disjunct motion used judiciously for variety. Too many skips produce angularity rather than a flowing line.

Voice-specific tendencies:
- **Bass:** naturally more disjunct (it carries root-position roots, which skip widely)
- **Alto and tenor:** should have few, if any, large skips
- **Soprano:** is heard as melody; it requires the most care — should be predominantly conjunct

### Practical tools for a better soprano
- **Double the third or fifth** (instead of root) to free the soprano to move to a different note
- **Change between close and open position** — a position change gives the soprano a fresh note at the same chord
- **Omit the fifth** (three roots + one third) to give the soprano more options; omitting the third leaves an empty open-fifth sound and is not in style

---

## FormaComposition Implications

**The root progression table is the direct source for your `progression` field logic.** The "strong / sometimes / less often" column is literally a probability weight table. If you ever formalize weighted progression generation, this is the reference.

**Root motion down a 5th = strong; up a 3rd = weak.** The engine needs to know this distinction to generate progressions with genuine harmonic drive vs. harmonic relaxation. A section with arc "rise" should favor strong (down-5th) progressions; a section with arc "settle" can use more third-motion.

**The V→VI deceptive cadence is a named event, not an accident.** When the engine generates a V followed by VI, it needs the special voice leading rule (leading-tone up, third of VI doubled), or the output will have parallel octaves or other errors.

**Parallel fifths and octaves are MIDI-checkable.** If the engine ever produces parallel fifths or octaves between any two voices, that is a deterministic bug, not a taste question. A validator pass over generated output could flag these.

**The tritone false relation (V→IV root position) should be avoided by default.** This is one concrete case where a chord progression that looks reasonable on paper (V followed by IV) produces a specific, identifiable badness.

**Conjunct soprano = conjunct melody voice.** The melody voice in FormaComposition should be predominantly stepwise, with leaps used intentionally. A generator that randomizes pitch selection without a step-preference bias will produce melodically angular output.

**"Continued application of the voice-leading procedure will result in rather dull music."** Piston says this directly. The rules produce correct output; musical output requires deliberate departures. This maps exactly to the role of the `arc`, `motif`, and `melody` behavior fields — they exist to introduce the purposeful violations that make a line interesting.

---

*Source: Walter Piston, Harmony (revised edition, 1948 / reissued 1959). Chapter 3, pages 17–28.*
