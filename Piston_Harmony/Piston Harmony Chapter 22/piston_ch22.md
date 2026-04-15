# Piston — Harmony: Chapter 22
## The Raised Supertonic and Submediant

> *The resolutions are typical of the principle that a chromatically altered tone receives a tendency to continue movement in the direction of its alteration.*

---

## Three Sources of Chromatic Alteration

In a literal sense, any chord affected by an accidental is "altered." But Piston distinguishes three sources:

1. **Mode mixture / key signature conventions** — using sharps or flats that belong to the mode but not the current key signature (e.g., the raised leading-tone in minor). These are not truly "altered chords."

2. **Secondary dominants** — accidentals that borrow from the temporary key of a secondary dominant. Also not "altered chords" in the strict sense.

3. **Genuine chromatic alteration** — accidentals applied to chord members that are not accountable by either of the above. These are the **truly altered chords**: raised supertonic and submediant (Ch. 22), Neapolitan sixth (Ch. 23), augmented sixth chords (Ch. 24), and chords with altered fifths (Ch. 25).

---

## The Raised Supertonic (II7 Raised) and Submediant (VI7 Raised)

The **raised supertonic seventh chord** and **raised submediant seventh chord** — with root and third chromatically raised — are **nondominant diminished seventh chords** functioning as leading-tone approach chords. They were identified in Ch. 16 as forms that do **not** fall in the dominant category.

### Structure in C Major

**II7 raised** (D raised to D# and F raised to F#):
```
D# — F# — A — C  =  an appoggiatura chord resolving to I
```

**VI7 raised** (A raised to A# and C raised to C#):
```
A# — C# — E — G  =  an appoggiatura chord resolving to V7
```

Both chords contain **raised tones whose tendency is upward** (a chromatically raised note has a natural tendency to continue upward). The root itself — being raised — tends melodically upward, not downward as a root normally would. This makes these chords behave like **leading-tone appoggiatura chords** rather than true harmonic roots.

> *"The root being thus altered does not seem like a harmonic root, but more like a melodic tendency tone."*

### Resolutions

- **II7 raised → I** (the raised supertonic seventh resolves to the tonic)
- **VI7 raised → V7** (the raised submediant seventh resolves to the dominant seventh)

The resolutions show all four factors moving in the direction of their alterations (raised tones continue upward, diatonic tones move by step).

---

## Rhythm and Approach

When the chord and its resolution are in the **strong-to-weak** rhythmic relationship, the chord has the character of an appoggiatura chord — or a triple appoggiatura over a single harmonic root.

When the voices approach as **auxiliary tones** (step up and back), the chord is of weak rhythmic value — a passing embellishment.

When the chord enters as **chromatic passing tones**, it becomes a passing chord.

All three rhythmic contexts are used. The chord may also appear as an **independent chord of equal rhythmic value** with its surroundings:
- **VI7 raised** is useful for introducing the dominant half cadence to emphasize the key
- **II7 raised** often appears prominently before the cadential six-four chord

---

## Notation

Composers are notably indifferent to the grammatical notation of these chords, especially for keyboard instruments. The raised second degree is often written as the minor third degree (Eb instead of D#); the raised sixth as the lowered seventh degree. This enharmonic notation creates analytical ambiguities:

- **II7 raised in C** (D# F# A C) may be written as Eb G Ab C — which looks like a different chord entirely
- **VI7 raised in C** (A# C# E G) may be notated as Bb Db E G

> *"Music is fortunately a matter of sound rather than symbols."*

The analytical approach: judge the chord by what it does (its resolution), not by how it is written.

---

## Mode

Both chords are more suggestive of the **major mode** than the minor:
- **VI7 raised** contains the major third degree
- **II7 raised** implies the raised second degree

Both can be employed in the minor mode. If the resolution of II7 raised is treated not as I but as **VofIV**, there is no difficulty continuing in minor. VI7 raised can also be used in predominantly minor surroundings.

---

## Cross-Relation

The two altered tones of either chord create cross-relations with their diatonic forms in adjacent chords. In a melodic group of double thirds or sixths (forming a double cambiata), the resulting cross-relations are **not avoided** — the cambiata quality of the altered tones makes the cross-relation acceptable.

The cross-relations between D-flat and D-natural (or F-natural and F-sharp) in successive voices are characteristic of the chromatic style and should be recognized rather than avoided.

---

## Irregular Resolution

Irregular resolution of these diminished seventh chords (in the harmonic sense, to an unexpected root) is **rare**. However, variations in the form of the chord of resolution can be employed without destroying the identity of the diminished seventh.

In the resolution of **II7 raised**, VofIV may be used either as:
- A dominant seventh chord, or  
- An incomplete minor ninth (usually = diminished seventh chord)

This second case results in **consecutive diminished seventh chords moving in parallel** — a characteristic chromatic texture.

---

## Modulation

Using diminished seventh chords in a nondominant function greatly expands their already versatile use as pivot chords. When a dominant-function chord becomes a nondominant function in the new key (or vice versa), the modulation is:
- **Effective** — unexpected harmonic reinterpretation
- **Somewhat unexpected** — the nondominant quality is not strongly directional, so the key change is less anticipated

Example: The incomplete dominant minor ninth of C (= B D F Ab) is left as II7 raised in the new key (= Ab major). Or: left as VI7 raised, the distant key of D-flat will be introduced.

The best practice: present the chord with its resolution in the **first key** before using it as a pivot, so the ear has already registered its function before the reinterpretation occurs.

---

## FormaComposition Implications

**Raised supertonic and submediant chords are the last significant pre-dominant tool before augmented sixths.** The II7 raised (D# F# A C in C major) before the cadential six-four is a characteristic early Romantic chromatic gesture — darker than plain II7, more chromatic than secondary dominants, creating a distinctive sharp edge at the cadence.

**These chords are appoggiatura chords — rhythmically strong, melodically resolved.** For FormaComposition, they belong on strong beats immediately before their resolution targets (I or V7). The strong-to-weak placement is the natural one; weak placement makes them auxiliary or passing.

**The enharmonic notation issue is real for any system that reads chord symbols.** FormaComposition's JSON layer should specify II7-raised and VI7-raised by their resolution targets and voice-leading direction rather than by a chord name that might be ambiguous. "Chord that resolves by step to I with all raised tones moving upward" is more specific than "D# F# A C."

**The modulation resource is significant.** The same diminished seventh chord can be heard as V°9 (dominant function) or as II7-raised/VI7-raised (nondominant function). This double identity — without enharmonic change — gives the dim7 four interpretations as V°9 and additional interpretations as these nondominant forms. Piston's total count: **twelve interpretations** per chord, with enharmonic changes **forty-eight**.

---

*Source: Walter Piston, Harmony (revised edition, 1948 / reissued 1959). Chapter 22, pages 255–264.*
