# Piston — Harmony: Chapter 9
## Chords of the Sixth — The Figured Bass

> *Melodically, the use of chords of the sixth permits the bass to move by step in progressions in which the roots would move by skip.*

---

## What a Chord of the Sixth Is

A **chord of the sixth** is a triad in **first inversion** — the third of the chord is in the bass. The characteristic interval from bass to the highest note is a sixth, which gives the chord type its name.

### The Figured Bass System
Inversions are identified by Arabic numerals showing the intervals formed between the bass and the upper voices:

| Position | Symbol | Meaning |
|---|---|---|
| Root position | (none, or 5/3) | Bass is root; fifth and third above |
| First inversion | **6** (or 6/3) | Bass is third; sixth and third above |
| Second inversion | **6/4** | Bass is fifth; sixth and fourth above |

The "6" alone is sufficient for first inversion — the third is understood. Root position requires no figure at all. An accidental standing alone, or beside a numeral, applies to the third above the bass. A line drawn through a numeral means to raise that interval by a half step.

---

## Doubling Rules for First Inversions

Root position triads: **double the root** (Ch. 2 rule).
First inversion triads: **different rule entirely**.

> *"The deciding factor is almost invariably the position of the doubled tone in the tonality."*

Two guiding principles:
- **a.** If the bass note (the chord's third) is a **tonal degree** (I, IV, V, or II) — double it.
- **b.** If the bass note is **not** a tonal degree (it's a modal degree — III or VI) — do not double it; double a tonal degree within the chord instead.

This keeps the doubling focused on the tones most important to the key, regardless of which note happens to be in the bass.

---

## General Effect: Weight and Texture

The triad in first inversion is **lighter, less ponderous, less blocklike** than the same triad in root position. It provides variety when used alongside root position chords, prevents harmonic stagnation, and enables the bass to move melodically.

**Rhythmically:** First inversions carry less weight than root position chords. The progressions V6→I, I6→IV, and II6→V all feel weak-to-strong. Conversely, I→I6 feels strong-to-weak. This rhythmic difference is useful but must be weighed against all other rhythmic factors — it is not the sole criterion.

**Melodically:** First inversions solve the bass's fundamental problem. When all chords are in root position, the bass must follow the root succession — which often means large skips. First inversions allow the bass to move by step even when the root progression skips. This gives the bass voice its own melodic identity.

---

## Voice Leading

No new principles. Move all voices to the nearest available position. Smooth connection remains the objective. The important reminder: **doubling and spacing are less important than melodic movement**. In first inversions, the need for a good bass line may override the standard doubling preference.

### Consecutive Chords of the Sixth
When several first inversions appear in succession, all voices tend to move in similar motion — a scalewise passage in all parts simultaneously. Direct octaves between tenor and bass can arise but can be avoided with a more balanced arrangement.

---

## The Seven First Inversions — Individual Characters

### I₆ — First Inversion of the Tonic
One of the most useful chords in the vocabulary, and one of the most neglected by beginners.

**Function:** Relieves the finality and weight of the tonic in root position. Provides necessary variety when a chord is needed after V but the full root-position tonic would be too conclusive. Particularly natural when the melody moves from tonic to dominant by skip — the bass can then move down from the third to the root or up to the fifth, creating a smooth stepwise line.

Common formulae: `I6–II6–V`, `I6–IV–V`, `V–I6–IV`, `I–I6–II6–V`

### II₆ — First Inversion of the Supertonic
Very common in cadences. **Strongly subdominant in feeling** — the bass note (the subdominant degree) is doubled. The II6 chord often follows I directly, where II in root position after I would be an awkward progression. In minor, II6 is strongly preferred over the root position diminished triad.

Common formulae: `I–II6–V–I`, `IV–II6–V–I`

### III₆ — First Inversion of the Mediant
Not usually an independent chord. Typically functions as a **passing or neighbor chord of V** — the mediant degree temporarily displaces a tone of the dominant. Rhythmically weak. In the minor mode, this is the first inversion of the augmented triad, with characteristic exotic color. When it proceeds to VI, the third may be doubled and it acts temporarily as a dominant of VI.

### IV₆ — First Inversion of the Subdominant
Often used **after V** — the bass moves up by step from the dominant, avoiding the tritone cross-relation that occurs in V–IV root position (Ch. 3). Relieves the weight of the root-position subdominant while retaining the subdominant harmonic character. Adds lightness and melodic quality to the bass.

Common formulae: `V–IV6–I6`, `I–V–IV6–V`, `V6–IV–IV6–V`

### V₆ — First Inversion of the Dominant
The **leading-tone in the bass** gives the bass strong melodic significance. Because the leading-tone has strong upward pull toward the tonic, the bass will almost always move up by half-step to the tonic — so the next chord will very probably be I. In descending scale passages the bass may proceed downward. In the minor mode, this is the occasion for the descending melodic minor scale in the bass.

Common formulae: `I–V6–I`, `I–V6–IV6`, `V6–I6–V`

### VI₆ — First Inversion of the Submediant
Nearly always functions as the **tonic chord with the sixth degree as a melodic tone resolving down to the fifth**. It is rarely an independent chord. Exceptions appear in scalewise passages of consecutive chords of the sixth.

### VII₆ — First Inversion of the Leading-Tone Triad
A **passing chord between I and I6**, or between I6 and I. Rhythmically weak; it barely disturbs the sense of tonic harmony. It is frequently analyzed as a grouping of melodic tones above the tonic root. However, if given prominence or dwelt upon, it can function as true dominant harmony (since the leading-tone triad is incomplete dominant seventh — Ch. 13 topic).

Common formulae: `I–VII6–I6`, `I6–VII6–I`, `IV–VII6–I6–II6–V`

---

## The Figured Bass: Historical Context

The figured bass system was a practical notation tool of the Baroque era (Bach, Handel). The keyboard player (*basso continuo*) read only the bass line with figures and improvised the upper voices in real time. Today it has no practical performance role, but it remains:
- The standard notation for chord inversions in harmonic analysis
- A useful exercise for keyboard harmony practice (playing through figured basses at the keyboard, always differently, always rhythmically)

> *"The proper method of reading the figures consists in finding the notes by interval and afterwards identifying the resulting chord. The combinations, with practice, get to be as familiar as the notes themselves."*

---

## FormaComposition Implications

**First inversions are the primary tool for making the bass voice melodic.** The Ch. 7 finding (bass should be a contrapuntal line, not just root-hopping) requires first inversions. When the root progression skips, the bass can take a first inversion and move by step instead. FormaComposition's bass module needs to evaluate whether a first inversion at a given chord produces a better bass line — this is the core logic of a melodic bass generator.

**I6 after V is one of the most common two-chord patterns in tonal music.** The sequence V–I6 is lighter than V–I and avoids the heavy closure of the authentic cadence when a phrase needs to continue. FormaComposition sections that end internally (not at the final cadence) should prefer V–I6 over V–I to avoid premature closure.

**II6 is the standard pre-dominant in cadential progressions.** The sequence II6–V–I is the most common cadential approach in common-practice music — more idiomatic than II root position in most contexts, and preferred in minor. The engine's cadence-building logic should generate II6–V–I as the default authentic cadence.

**V6 signals imminent resolution to I.** When the engine assigns a V6 to a section, the next chord should almost certainly be I (or I6). This is a near-deterministic voice-leading constraint.

**The weight hierarchy is: root position > first inversion > (second inversion — Ch. 11).** Placing a root-position chord at a metrically or harmonically strong point and a first-inversion chord at a weaker point produces natural rhythmic shaping without any change to the harmony itself. This maps directly to the `harmony_pattern` duration logic: a heavier chord (root position) deserves a longer duration or a strong beat; a first inversion can absorb a shorter duration or a weak beat.

**The scalewise bass is the signature of first-inversion passages.** The pattern C–D–E–F–G in the bass, moving through I–II6–III6–IV6–V or similar, is one of the most distinctive textures in tonal music. FormaComposition's bass module should recognize "stepwise ascending/descending bass" as a specific compositional gesture and know to assign first inversions along the way.

---

*Source: Walter Piston, Harmony (revised edition, 1948 / reissued 1959). Chapter 9, pages 87–101.*
