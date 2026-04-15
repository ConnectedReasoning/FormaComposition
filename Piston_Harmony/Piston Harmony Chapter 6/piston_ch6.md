# Piston — Harmony: Chapter 6
## The Harmonic Structure of the Phrase

> *Harmonically, a phrase consists of a series of harmonic progressions or formulae designed to make clear and maintain the tonality, and to confirm and enhance the harmonic implications in the melodic line.*

---

## What a Phrase Is

A phrase is the basic unit of musical thought — a complete harmonic and melodic statement. The norm in common-practice music:

| Tempo | Phrase length |
|---|---|
| Very slow | 2 measures |
| Normal | **4 or 8 measures** (the overwhelming norm) |
| Very fast | 16 measures |

Phrases that don't fit these lengths fall into two categories: originally 4 or 8 bars that have been **extended** by technical processes (sequences, deceptive cadences), or genuinely odd-length phrases from the start.

**Important:** Real music has far fewer chord changes per phrase than a harmony exercise. Chorales and hymns, with a chord on almost every beat, represent a tiny fraction of the literature and are not representative of common practice.

---

## Number of Harmonic Changes

**One extreme — static harmony:** An entire phrase on one chord. Valid when the phrase serves an introductory or closing function — setting the stage or settling after motion. The Mendelssohn *Songs Without Words* Op.62 No.4 example: the static phrase opens and closes the piece as an intentional frame.

**Other extreme — continuous change:** Every beat a new chord. Creates restlessness in fast tempo, dignity and sturdiness in slow tempo. The Schumann *Symphonic Studies* and Chopin Nocturne Op.37 examples.

**The norm:** Balanced harmonic activity. Chord changes lend life and movement without drawing attention to themselves. The changes form a **pattern of short and long time values** combined with **weak and strong rhythmic progressions**.

### Regular Pulse
Changes recurring at regular intervals (like a steady pulse) are fairly common. The Brahms Waltz Op.39 No.1: alternating I and V on every dotted half note, simple and regular. This creates a hypnotic forward motion — the harmonic rhythm is locked to the metric pulse.

### Varied Pattern (the norm)
Most phrases mix long and short durations, strong and weak progressions, creating shape within the phrase. The Beethoven Op.49 No.1 example: V I VI V | I VI IV I — a mix of short and long, strong and weak arrivals.

---

## The Phrase Beginning

A phrase does not necessarily begin on the tonic chord, nor on the first beat of a measure. Two independent parameters:

**Rhythmically:** May start on a downbeat (thesis) or an upbeat (anacrusis).

**Harmonically:** It is customary for the first two or three chords to establish the tonality clearly. This does **not** require the tonic chord — as shown in Chapter 4, certain two-chord formulae define the key without I. The Mozart K.281 example begins on V-of-II (a secondary dominant — a topic for a later chapter), which is nonetheless heard clearly in B-flat major.

---

## The Phrase Ending — The Cadence

The end of every phrase is marked by a **cadence**: a conventional harmonic formula that signals closure, partial or complete.

### Authentic Cadence
**V → I**

The full stop. The period at the end of a sentence. Complete closure — the dominant resolves to the tonic, both rhythmically and harmonically. The strongest cadence in tonal music.

### Half Cadence
**Any chord → V**

The comma. An unfinished statement. The phrase ends on V — it could be approached from any direction (II–V, IV–V, I–V, VI–V). The ear registers incompleteness; a continuation is expected.

The half cadence and authentic cadence work together as a pair: **antecedent phrase** (ending on V) + **consequent phrase** (ending on I) = the fundamental two-phrase unit of tonal music.

---

## Masculine and Feminine Cadences

These terms describe the **rhythmic placement** of the final chord, not its harmonic type:

| Type | Character | Definition |
|---|---|---|
| **Masculine** | Strong ending | Final chord on a metrically strong beat (bar-line placed just *before* the final chord) |
| **Feminine** | Weak ending | Final chord on a metrically weak beat (strong-to-weak rhythmic progression at the cadence) |

A masculine authentic cadence: the V falls on beat 4 (upbeat/anacrusis) and I arrives on beat 1 (the strong beat). The arrival is accented, definitive.

A feminine authentic cadence: V falls on beat 3 (strong) and I arrives on beat 4 (weak). The resolution is soft, settling, trailing off.

Both types apply to both authentic and half cadences. The choice of masculine vs. feminine ending is a primary tool for controlling the character of phrase endings.

---

## Unity and Variety Within the Phrase

The phrase must balance two opposing forces:

**Unity:** The harmony maintains the tonality. This is achieved by repeating root progressions, using tonal degrees (I, IV, V, II) consistently, and keeping the key clear. Without unity the phrase has no tonal center.

**Variety:** The harmony avoids monotony. Achieved by:
- Introducing **modal degrees** (III, VI) for color
- Using different rhythmic patterns on the same roots
- Chromatic alteration (later chapters)
- Modulation (later chapters)

> *"The harmony alone will often seem to possess too much unity, with many repetitions of the same root progressions."*

This is exactly why purely algorithmic progressions sound mechanical — they achieve unity without variety. The balance requires compositional judgment applied at the phrase level.

### The Schubert Analysis (Ex. 113–116)

Piston walks through a complete four-step analysis-and-reconstruction of a Schubert phrase. This is the chapter's central practical demonstration:

**Step a — Extract the root rhythm:**
The phrase in A-flat major reads: `I V | I V | I III VI II | V`
Root rhythm: half note, half note | half, half | quarter, quarter, quarter, half | dotted half

**Step b — Note what the rhythm does:**
- Measures 1–2: I–V repeated — pure tonal unity, regular pulse
- Measure 3: I III VI II — variety arrives; modal degrees III and VI appear; harmonic acceleration (four roots vs two)
- Measure 4: V alone — half cadence, masculine (V on the downbeat)

The modal degrees in measure 3 are the variety mechanism. Without them, the phrase would be I V I V I V — hypnotic but thin. With them, the third measure opens up the harmonic color before the cadential arrival.

**Step c — Reconstruct differently:**
Using the same root rhythm pattern as a skeleton, build a completely different phrase. The surface changes entirely; the structural logic (unity then variety, ending with half cadence) stays.

---

## The Three-Step Composition Process

Piston lays out a replicable method for phrase construction:

1. **Derive the rhythmic pattern of roots** — abstract the harmonic rhythm and root succession as a rhythm-only skeleton
2. **Construct the four-part harmonic scheme** — flesh out the skeleton as SATB block chords
3. **Create an original phrase from the skeleton** — use the harmonic scheme as a scaffold; add melodic movement, rhythmic variety, nonharmonic tones

This process is compositional — not analytical. Starting from a rhythm skeleton rather than a chord list is the key insight. The rhythm *constrains* which chord changes feel natural, and *determines* where the phrase breathes.

---

## FormaComposition Implications

**Sections map directly to phrases.** The 4-bar and 8-bar norm is the structural norm for FormaComposition sections. Sections shorter than 4 bars will feel like phrase fragments; longer than 8 without internal structure will feel like a single undifferentiated mass unless the harmonic rhythm creates internal shape.

**Every section needs a cadential ending.** The section's final chord progression should be either V (half cadence — tension, continuation) or V→I (authentic cadence — resolution, closure). The `arc` field implicitly controls this: rising arc → half cadence; falling/resolving arc → authentic cadence. Making this explicit in the JSON (`"cadence": "half"` or `"cadence": "authentic"`) would formalize what sections currently do by accident.

**Masculine vs. feminine ending is a `harmony_pattern` decision.** If V falls on a weak beat and I lands on the downbeat = masculine. If V falls on a strong beat and I lands on a weak = feminine. The `harmony_pattern` field directly controls this. It's currently not labeled — it could be.

**The antecedent/consequent pair is the fundamental two-section unit.** A section ending on V (half cadence) followed by a section ending on I (authentic cadence) is the most structurally complete phrase pair in tonal music. FormaComposition's section-by-section workflow is naturally suited to this: write the antecedent, listen, then write the consequent to answer it.

**The three-step process is the FormaComposition generation pipeline.** Step 1 (root rhythm) = `chord_bars` + `progression`. Step 2 (harmonic scheme) = the engine's chord generation. Step 3 (melodic surface) = melody, counterpoint, and bass voice generation over the scheme. The pipeline Piston describes for human composers is structurally identical to what the engine does. The main difference: the engine currently doesn't start from a rhythm skeleton — it derives rhythm from `harmony_pattern`. That's fine; it just means `harmony_pattern` is doing Step 1's work.

**Modal degrees in the penultimate bar = the variety mechanism.** The Schubert pattern (tonal → tonal → modal → cadence) is a proven formula for phrase construction. In FormaComposition terms: a section that stays on I, IV, V for its first half, then introduces III or VI in the second half before the cadence, will naturally feel shaped. This could be a named `section_shape` template.

---

*Source: Walter Piston, Harmony (revised edition, 1948 / reissued 1959). Chapter 6, pages 56–66.*
