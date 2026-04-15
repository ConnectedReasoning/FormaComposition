# Piston — Harmony: Chapter 8
## Modulation

> *Modulation is an element of variety but also of unity when the balance of the keys in support of a main tonality is used to advantage. The key-scheme is therefore one of the most significant ingredients of form.*

---

## What Modulation Is

Modulation is **change of key** — the adoption of a different tonal center, to which all other tones become related. To remain in one key throughout a piece of any length is aesthetically undesirable. The key-scheme, the pattern of tonal centers visited across a composition, is one of the fundamental elements of musical form.

The technical basis for modulation is the **ambiguity of chords** established in Chapter 4. Any chord can be interpreted in multiple keys. The C major triad can be heard as:

| Function | Key |
|---|---|
| I | C major |
| IV | G major |
| V | F major |
| VI | E minor |
| III | A minor |
| II (with chromatic context) | B-flat major |

The relationships to the other six tones require chromatic alterations and belong to later chapters. The principle is the same: chord ambiguity is the *mechanism* of modulation.

---

## The Three Stages of Modulation

Every modulation passes through three stages:

### Stage 1 — Establish the Initial Key
The first key must be clearly heard before the modulation begins. The dominant must be perceived as a dominant. If modal degrees have been overused, the phrase may already sound like it's in the second key before the modulation even starts — especially if that second key is strongly established later.

When the modulating phrase is not the first phrase, Stage 1 may be brief — the preceding cadence carries the tonal memory of the key.

### Stage 2 — The Pivot Chord
The pivot chord is a chord **common to both keys**, heard first as belonging to the initial key, then immediately reinterpreted as belonging to the new key. It gets a **double analysis**:

```
C: I
G: IV
```

The pivot chord is written with a brace showing both interpretations. The hearer is still in the old key at this moment — only the composer knows the new key is coming.

**The pivot chord should preferably NOT be V of the new key.** V of the new key belongs to Stage 3 (establishing the new key). Using V of the new key as the pivot collapses Stages 2 and 3 together, producing an abrupt modulation without the characteristic "reinterpretation" effect.

### Stage 3 — Establish the New Key
The new key is made clear by a **cadence** — half or authentic — in the new key. Strong progressions in the new key (IV–V, II–V) heard before the cadence reinforce the arrival. Once the dominant of the new key resolves (or is heard as dominant), the modulation is complete.

---

## Related Keys

"Related" means closely related — the degree of relationship is a continuum.

### Definition by Shared Tones
The simplest measure: how many tones do two keys share? C major and G major share six of seven tones — they differ only in F vs. F-sharp. This is the closest possible relationship.

> *"The keys of nearest relationship to a given key are those having one sharp (or flat) more or less in the signature."*

### The Family of Keys — Major Mode
For any major key, the closely related keys are:

| Relationship | From C major |
|---|---|
| Dominant (up a 5th) | G major |
| Subdominant (down a 5th / up a 4th) | F major |
| Relative minor | A minor |
| Relative minor of dominant | E minor |
| Relative minor of subdominant | D minor |

These five keys, plus the home key, form the **family** of a major key. The key-notes of these related keys are the same as the scale degrees of the home key (excluding VII).

### The Family of Keys — Minor Mode
The minor key family differs from major in one important way: **II is missing** (diminished triad — cannot serve as tonic). VII appears instead, as the major triad on the seventh degree of the descending melodic minor scale:

| Relationship | From A minor |
|---|---|
| Dominant | E minor |
| Subdominant | D minor |
| Relative major | C major |
| Relative major of dominant | G major |
| Relative major of subdominant | F major |

### Interchange of Modes — The Enlarged Family
The 19th century discovered that the **major and minor modes on the same tonic** are in practice nearly interchangeable — they differ only in the third degree, and share the same tonal degrees (I, IV, V, II). This enormously expands the family:

- C major and C minor are closely related despite differing by three key signatures
- A-flat major is related to C major as the **minor sixth degree**
- D major is related to C minor as the **dominant of the dominant**
- G minor is related to C major as dominant minor, subdominant of II, etc.

Rather than compiling an exhaustive list, the practical approach is to interpret any new tonic note as a chord in the initial key — its function in the initial key describes the relationship.

---

## Exploration of Pivot Chords

Given two keys, find all possible pivot chords by writing out all triads of the first key and checking each against the second key:

**Example: C to B-flat**

| C major | B-flat interpretation |
|---|---|
| I (C) | II of B-flat |
| II (D minor) | III of B-flat |
| III (E minor) | IV of B-flat |
| IV (F) | V of B-flat ← avoid as pivot |
| V (G) | VI of B-flat |
| VI (A minor) | VII of B-flat (diminished — weak) |

Best pivots: C major as II of B-flat, or E minor as IV of B-flat, or G major as VI of B-flat. The IV-of-B-flat option (C=IV→B-flat V→I) is technically clean but Piston notes the B-flat triad would need to appear as part of the descending melodic minor scale of C, requiring care.

---

## Modulation is Both Variety AND Unity

> *"Modulation is an element of variety but also of unity when the balance of the keys in support of a main tonality is used to advantage."*

A modulation to the dominant (up a fifth) strengthens the sense of the home key — it is the closest neighbor, and returning to the tonic after visiting the dominant makes the tonic feel more settled. A modulation to a very distant key creates maximum variety but risks losing the sense of the home tonal center.

The **key-scheme** — which keys are visited, in what order, and for how long — is a primary architectural element of any substantial composition. A well-designed key-scheme gives a piece its tonal arc in the same way that harmonic progression gives a phrase its shape.

---

## Examples of Modulating Phrases

**C → G (up a perfect fifth):** I of C = IV of G. The pivot is the tonic chord reinterpreted as subdominant. Then II–V–I in G closes the phrase. The modulation is smooth and natural — the closest possible relationship.

**B major → D-sharp minor (up a minor third, to relative minor of dominant):** I of B = IV of D-sharp, making the strong progression IV–V–I in the new key.

**D major → F-sharp minor (up a major third):** VI of D major = IV of F-sharp minor. The pivot is the modal degree of the first key becoming the subdominant of the second.

**D major → B major (minor key to relative major, up a minor third):** The pivot is IV of D minor reinterpreted as II of B major, proceeding to V–I of B.

---

## FormaComposition Implications

**Modulation is the tool for section-to-section key changes.** FormaComposition already supports a `key` field per section. The question is: does the transition between sections handle the pivot mechanism, or does it jump abruptly? An abrupt key change (no pivot) is a valid effect — a sudden shift — but it should be intentional. A smooth modulation requires a pivot chord at the section boundary.

**The key family table is the harmonic map for section key planning.** When designing a multi-section piece, keys in the same family (dominant, subdominant, relative minor) feel natural and connected. Distant keys feel dramatic and disorienting. For ambient/new-age music, staying within the family (or using parallel mode mixture) is usually more effective than distant modulations.

**The pivot chord at a section boundary is a specific JSON design challenge.** The last chord of Section A needs to be reinterpretable as a chord in Section B's key. The FormaComposition generator doesn't currently plan this — it generates each section independently. This is a known gap. The simplest fix: allow the final chord of a section to be specified explicitly, and match it to the first chord of the next section with a dual analysis.

**Parallel mode (C major → C minor) is the smoothest possible "modulation."** It's not technically a modulation (tonal center stays the same), but the modal color shift is dramatic. This is the most useful transition for ambient music — same key, flipped mode — and it requires no pivot chord at all. The `mode` field handles this already; it just needs to be recognized as a compositional tool, not a bug.

**The key-scheme is the piece-level arc.** What FormaComposition calls `narrative_arc` at the piece level is, harmonically, the key-scheme. The choice of which section to put in which key (or mode) is the large-scale harmonic architecture. A simple key-scheme for an 8-section ambient piece: home key → dominant → home key → parallel minor → home key → subdominant → home key. That gives a complete tonal arc with three different kinds of "away."

**"Distance" between keys is measurable.** Keys that share more tones are closer. A FormaComposition validator could flag key changes between sections that are very distant (e.g., C major to F-sharp major — only 2 shared tones out of 7) and suggest the composer intended the effect deliberately. This isn't a prohibition — tritone-distance modulations are dramatically effective — but they should be intentional.

---

*Source: Walter Piston, Harmony (revised edition, 1948 / reissued 1959). Chapter 8, pages 77–86.*
