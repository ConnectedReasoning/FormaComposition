# Piston — Harmony: Chapter 19
## The Sequence

> *The harmonic sequence, the systematic transposition of a melodic, rhythmic, and harmonic pattern, is a resource of development in music. The change of pitch adds the element of variety to the unity of repetition.*

---

## What the Sequence Is

A **harmonic sequence** is the systematic transposition of a complete pattern — melodic, rhythmic, and harmonic together — to a different pitch level. It is one of the primary mechanisms of musical development: it creates forward momentum through repetition while avoiding stasis through the change of pitch.

Though the sequence may become a "refuge for the composer of lesser talent," it has been used with great effectiveness by the best composers — Bach, Mozart, Beethoven, Brahms. It is often discovered on analysis to be the structural basis for passages that don't initially seem sequential, particularly in fugal developments and symphonic transitions.

---

## The Initial Pattern

The pattern can range from a single short motive on a single chord to a complete phrase. Patterns of one chord are harmonically thin — their interest depends almost entirely on contrapuntal arrangement. **Patterns of two chords** are the most common and most immediately recognizable, creating a clear unit that the ear grasps.

Patterns of longer length become less perceptibly sequential — the ear must hear the unit as a whole before it can recognize the repetition.

---

## Harmonic Rhythm in the Pattern

The harmonic formula of the pattern has its own rhythmic shape, arising from:
- The choice of root progressions (strong vs. weak)
- The time values assigned to each chord
- The placement of the pattern relative to the bar-line

**Simple strong-to-weak**: pattern of two chords where the strong chord opens and the weak closes (e.g., I–IV: root motion up a fourth, strong progression)

**Anacrusic pattern**: pattern beginning with an upbeat gives a more fluent, forward-pressing sequence. A long anacrusis followed by a short down-beat heightens the impression of pressing forward.

The harmonic rhythm must be in agreement with the meter, while the melodic rhythm may create syncopation or cross-rhythm against it.

---

## Length of the Sequence

> *"It is generally agreed that a single transposition of the pattern does not constitute a sequence, the systematic transposition not being established until the third appearance of the initial group."*

Standard sequence structure: **three appearances minimum**. The sequence is felt from the third iteration onward.

On the other hand, composers seldom extend beyond the **third appearance** without breaking the symmetry — either by variation or by abandoning the sequence altogether. Exceptions occur in virtuosic passagework and technical études, but as an aesthetic principle: three appearances, rarely more.

---

## Degree of Transposition

The pattern may be transposed by **any interval**, up or down. The interval chosen depends on:
1. **The harmonic destination** — where the sequence needs to arrive
2. **The feasibility of connection** — how smoothly the pattern connects to its own transposition

These two constraints govern the choice of transposition interval. Construction of a sequence requires thinking about both simultaneously.

---

## The Nonmodulating Sequence (Tonal Sequence)

In the **nonmodulating sequence** (also called *tonal sequence*), there is a **single tonal center throughout**. Transpositions are made to degrees of the scale of the key rather than exact (chromatic) transposition.

This means the pattern is **diatonic** at each transposition — the intervals between degrees are not always equal. For example, a pattern of two triads a fifth apart in C major:
- Starting on I: C major and G major (major–major)
- Transposed up one step to II: D minor and A minor (minor–minor)
- Transposed up again to III: E minor and B diminished (minor–diminished)

The pattern varies internally at each transposition because the scale is not equal-interval. This natural variation is actually desirable — it prevents the mechanical repetitiveness of exact transposition and keeps the music within the key.

> *"Both of these variations are present in the sequence shown below, descending by seconds. The root progressions are by fourths throughout the entire passage, all perfect fourths except from VI to II."*

---

## Secondary Dominants in the Nonmodulating Sequence

Secondary dominants add **harmonic color** to the nonmodulating sequence:
- They introduce tones foreign to the scale of the main key
- They contribute rhythmic dissonance
- They **emphasize the unity of each pattern group** — the secondary dominant and its temporary tonic form a tightly bound two-chord unit

Example: instead of I–IV → II–V → III–VI (plain diatonic sequence), use:
VofIV–IV → VofV–V → VofVI–VI

Each pair is bound by the dominant–tonic relationship, making the sequence's group structure clearer and harmonically richer.

When the secondary dominant appears **on the third iteration** of the pattern, the expected temporary tonic may be a minor triad — a diminished triad in minor mode — which cannot serve as a temporary tonic. In such cases the secondary dominant is **omitted** on the third iteration.

---

## The Modulating Sequence

In the **modulating sequence**, the tonal center changes with each transposition. The pattern is stated in key A, then transposed (exactly or approximately) to key B, then to key C.

The most common form: **three keys**. There is no return to the initial key within the sequence.

The **pivot chord** is the final chord of each pattern statement — it serves simultaneously as the last chord of the old key and the first chord of the new.

The modulation to the second key is called a **passing modulation** — there is no permanence to the key. It represents a stage in the modulation to the third (ultimate) key. Passing modulations are not exclusively sequential, but the modulating sequence always contains one.

The pattern in a modulating sequence is typically **constructed on a clearly tonal harmonic basis** — often just II–V — which can establish different tonal centers each time it appears. This allows three or more key changes with a single short two-chord pattern.

### Chromatic Transposition

The modulating sequence can use **chromatic** (exact interval) transposition, creating distant key relationships with each step. The Weber example (Der Freischütz) moves through keys a major third apart — C, Eb, G — with chromatic secondary chords between.

---

## Sequence and Harmonization

A sequence in a melodic voice is not always accompanied by sequence in the other voices or harmony. However:

> *"It is advisable in the study of harmony to treat sequences in given parts as harmonic sequences, until the facility is acquired of arranging these sequences whenever desired."*

The key practical point: when a melodic part contains a sequence, look for it and treat it as a harmonic sequence. Avoidance of sequential treatment should be a deliberate compositional choice, not a failure to recognize the opportunity.

Unusual progressions (like VII–IV, with its augmented fourth relationship) are **justified by the logic of the symmetrical melodic movement** in a sequence. The sequence legitimizes root progressions that would otherwise be avoided.

---

## Keyboard Practice

The sequence is an extremely useful practice medium: take any harmonic formula and run it as a sequence through all keys across the full range of the keyboard. Two appearances are sufficient to establish the pattern; the continuation becomes a mental exercise rather than mechanical reading.

---

## FormaComposition Implications

**The sequence is the most powerful harmonic development tool in the vocabulary.** It turns a two-chord pattern into a self-propelling forward-motion machine. For FormaComposition, implementing sequences means: define a two-chord pattern, specify the transposition interval, and repeat it two or three times. This alone can generate an entire section.

**The nonmodulating sequence with secondary dominants is the richest single harmonic texture.** The pattern VofX–X repeated through three transpositions (e.g., VofVI–VI → VofV–V → VofIV–IV) creates a six-chord passage with chromatic color, strong internal logic, and clear forward direction — all while remaining in one key. It is functionally the same as the circle-of-fifths chain from Ch. 14, but now understood structurally as a sequence.

**The minimum is three pattern appearances.** A two-appearance sequence is not yet a sequence by convention — it's just a pair of chords repeated once. FormaComposition should enforce three repetitions when generating a sequential passage.

**The modulating sequence is the bridge between sections in different keys.** When two adjacent sections are in different keys, routing through a two- or three-key modulating sequence (with the second key as a passing modulation) creates a smooth, purposeful transition rather than an abrupt cut. The `modulation` field in FormaComposition JSON could specify a sequence path between sections.

**Descending-fifths sequence (circle of fifths) is the commonest strong sequence.** Root motion descending by a fifth (or ascending by a fourth) at each step: I–IV–VII–III–VI–II–V–I. This produces the maximum-strength root progressions throughout. FormaComposition should have this as a named sequence template.

**The sequence justifies unusual progressions.** Within a sequential passage, VII–IV (which would normally be avoided as an augmented fourth root motion) becomes acceptable because the symmetrical melodic logic overrides the harmonic preference. This is the sequence's special license: the architectural logic of the pattern supersedes the normal rules of root motion.

---

*Source: Walter Piston, Harmony (revised edition, 1948 / reissued 1959). Chapter 19, pages 212–223.*
