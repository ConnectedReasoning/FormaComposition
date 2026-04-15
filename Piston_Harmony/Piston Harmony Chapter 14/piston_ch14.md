# Piston — Harmony: Chapter 14
## Secondary Dominants

> *Any degree of the scale may be preceded by its own dominant harmony without weakening the fundamental tonality.*

---

## The Core Principle

Virtually any page of common-practice music contains accidentals — sharps, flats, naturals — that don't indicate modulation. Many of these arise from one pervasive tendency: **composers prefer dominant harmony**. Every chord can be made to sound more directed, more purposeful, by preceding it with its own dominant. The result is a **secondary dominant** — a dominant chord built not on the fifth of the key but on the fifth of some other chord.

Far from weakening the tonality, secondary dominants **strengthen** it. Each tonal degree that gets its own dominant support becomes more anchored, and the whole tonal structure becomes stronger. Beethoven's First Symphony opens with exactly this logic — the tonic is delayed in its arrival but made more inevitable by the support structures established beforehand.

The rule stated:
> **Any degree of the scale may be preceded by its own dominant harmony without weakening the fundamental tonality.**

---

## What Counts as a Secondary Dominant

All forms applicable to the regular dominant are usable:
- Major triad (VofX)
- Dominant seventh chord (V⁷ofX)
- Leading-tone triad without root = VII of X
- All inversions of the above

The notation: **VofX**, V⁷ofX, etc. Read "V of II" as "the dominant of the second degree."

---

## Resolution

The secondary dominant and its temporary tonic form a **tonal unit of two chords**. All resolution principles from Ch. 13 apply:
- The seventh descends by step
- The leading-tone (chromatically raised note) ascends by step
- The temporary tonic is treated exactly as a regular tonic within those two chords

**Chromatic alteration creates tendency:** A note chromatically raised has a strong tendency to continue upward. A note chromatically lowered has a tendency to continue downward. Secondary dominants harness this.

---

## Method of Introduction

The smoothest approach: **introduce the secondary dominant from a chord that can also be analyzed in the temporary key.** This creates a group of three chords where the middle chord is the secondary dominant:

```
Chord 1    → Chord 2 (VofX)  → Chord 3 (X)
(true key)   (temporary key)   (true key, now tonicized)
```

Chords 1 and 3 remain firmly in the true key. Only the middle chord is temporarily "borrowed." The three together can be heard as a brief excursion into the temporary key or as a chromatic enrichment of the true key — the ambiguity is the point.

---

## Cross-Relation

When chromatic alteration introduces a note that appears simultaneously (in a different voice) with its diatonic form from the previous chord, a **cross-relation** (or false relation) results. This occurs frequently with secondary dominants since they introduce altered tones.

**Acceptable cross-relation:** When the two tones involved are scale degrees of the melodic or harmonic minor scale — there is a logical basis in the scale itself.

**Problematic cross-relation:** In a firmly established major context, cross-relation is generally avoided by arranging the chromatic progression to occur in a **single voice** rather than across voices. The diatonic note and its chromatically altered form should appear in the same voice on successive beats, not in two different voices at the same time.

---

## The Five Secondary Dominants

### VofII — Dominant of the Supertonic

In C major: **A major** (or A⁷). Root = 6th degree. The tonic note (C) is chromatically raised to C-sharp, which becomes the leading-tone of D (II).

- **Not used when the minor mode prevails** — in minor, II is a diminished triad and cannot serve as a temporary tonic
- Most natural when preceded by VI (the A-minor chord, which shares most of its tones with the A-major secondary dominant)

### VofIII — Dominant of the Mediant

Two forms exist since major mode has both major III and minor III. The major form (VofIII major) requires raising **both the 2nd and 4th degrees** simultaneously — the most chromatic of the common secondary dominants.

- In C major major-mode: **B major** (raises D to D-sharp and F to F-sharp)
- In C major minor-mode: **G major** = the key's own dominant going to Eb (bIII) — sounds like VofVI in the relative major
- The chromatically raised 2nd and 4th degrees both resolve upward

### VofIV — Dominant of the Subdominant *(one of the commonest)*

In C major: the **tonic triad with an added minor seventh** — C–E–G–B-flat. The tonic triad itself, in dominant seventh position, pointing to IV.

> *"The major tonic triad actually stands in relation of dominant to the subdominant, although it needs the addition of a minor seventh to clarify this relationship to the hearer."*

- One of the most common secondary dominants in the literature
- Very often used **toward the end of a piece** — the emphasis on the subdominant balances the earlier dominant-heavy activity
- Also used at the beginning of a movement to establish the subdominant area before the tonic itself arrives

### VofV — Dominant of the Dominant *(already familiar)*

In C major: **D major** (raises F to F-sharp). This has been encountered already in Ch. 12 in the context of half cadences. The D–F#–A chord (VofV) or D–F#–A–C (V⁷ofV) leads to G, which then leads to C.

- The strongest half cadence formula includes VofV: `...–V⁷ofV–V`
- The most common secondary dominant after VofIV

### VofVI — Dominant of the Submediant

In C major (major VI): **E major** (raises the tonic C to C-sharp, becoming the leading-tone of A). If a seventh is added (E–G#–B–D), the D is a new chromatic tone (the lowered 2nd degree of C major).

- Major VofVI is by far the more common form
- The key's own dominant is chromatically raised (G → G#)
- The submediant of the **minor** mode is fairly common in major harmonic surroundings (VI minor in major = mode mixture)

### VofVII — Not Used

The leading-tone (VII) is not a possible temporary tonic — it is a diminished triad and cannot function as a tonic even temporarily. Therefore VofVII is not employed.

**However:** The lowered 7th degree of the minor scale (the natural minor seventh, e.g., Bb in C major) can be attended by a dominant harmony. Used in connection with an established major mode, this demonstrates the coloristic possibilities of modal interchangeability.

---

## Sequential Secondary Dominants — The Chain of Fifths

Each chord becomes the dominant of the next in a cascading series:

`VofIII → VofVI → VofII → VofV → V → I`

Each step is a resolution of a dominant to its tonic — but the "tonic" immediately becomes a new dominant. The chain descends by fifths until the real V resolves to I. This produces one of the most directional, driving harmonic sequences in tonal music. Employed by Bach, Mozart, Beethoven in various lengths.

---

## FormaComposition Implications

**Secondary dominants are the single most effective harmonic color tool within a key.** Without modulating, they introduce new notes (chromatic alterations) that give harmonic surprise, direction, and interest. They are the difference between a harmonically plain progression and one that feels composed.

**VofIV (I7) is the easiest and most available.** In any major key, simply add a minor seventh to the tonic chord. In FormaComposition JSON: adding `b7` to the tonic chord quality creates VofIV. This one chord change immediately enriches any section.

**VofV sharpens the dominant.** Adding a VofV before V in any progression — especially at a half cadence — dramatically increases the urgency of the dominant arrival. Pattern: `...–VofV–V–I` or `...–VofV–V` (half cadence).

**The chain of secondary dominants is a named sequence template.** `VofIII–VofVI–VofII–VofV–V–I` is a self-contained harmonic passage that can anchor an entire phrase or section. It has strong directional pull and introduces multiple chromatic tones while remaining firmly in the home key.

**Cross-relation is a style flag, not a prohibition.** When the engine introduces a secondary dominant, the preceding chord may contain the diatonic form of the note being chromatically raised. If that diatonic note is in a different voice from the chromatic version, a cross-relation results. In a major-mode context, the engine should arrange the chromatic progression within a single voice. In a minor-mode context, cross-relation is more acceptable.

**Secondary dominants require specific chord quality.** VofIV in C major is not just "a chord before F" — it is specifically C–E–G–Bb (major triad + minor seventh). The quality is non-negotiable; a C minor seventh would not function as VofIV. FormaComposition's chord builder, when given "VofIV," must produce the correct major-with-minor-seventh structure, not just any chord on the tonic.

---

*Source: Walter Piston, Harmony (revised edition, 1948 / reissued 1959). Chapter 14, pages 150–162.*
