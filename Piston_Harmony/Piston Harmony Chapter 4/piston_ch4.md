# Piston — Harmony: Chapter 4
## Tonality and Modality

> *Tonality is the organized relationship of tones in music — a central tone with all other tones supporting it or tending toward it.*

---

## Definitions

**Tonality** = the key. The organized system of relationships between all tones and a central tonic. Synonymous with "key." A piece in C major has C as its tonal center; all other pitches exist in relation to that center.

**Modality** = the scale. The specific collection of pitches used to establish that tonal center. Synonymous with "scale" or "mode."

These two concepts are independent but intertwined. You can be in the *tonality* of C while using the *modality* of Dorian. The tonal center stays; the color of the scale changes.

---

## The Modes

Piston lists these modes (all shown on C in the book) as examples of the "extremely large number" that can exist, but explicitly **limits the book to major, minor, and chromatic** as the common-practice vocabulary:

| Mode | Characteristic interval vs major | Character |
|---|---|---|
| **Dorian** | b3, b7 | Minor with raised 6th; open, modal |
| **Phrygian** | b2, b3, b6, b7 | Minor with flat 2nd; dark, Spanish feel |
| **Lydian** | #4 | Major with raised 4th; bright, floating |
| **Mixolydian** | b7 | Major with flat 7th; folk, unresolved dominant |
| **Aeolian** | b3, b6, b7 | Natural minor (no leading tone) |
| **Pentatonic** | No semitones | 5-note scale; open, universally familiar |
| **Whole-tone** | All whole steps | 6 equal steps; ambiguous, impressionist |
| **"Hungarian"** | Aug 2nds | Double harmonic scale; exotic, Eastern |

**Key observation:** These modes were used "occasionally" during the harmonic period but were never common practice. They re-enter prominence in the 20th century. Piston acknowledges them, frames them as departures from the norm, and moves on.

**The "major-minor system"** — 300 years of common practice has so thoroughly conditioned the ear to interpret music in major or minor that we tend to hear modal music as "trying to be" one or the other, often with "somewhat unsatisfactory results." Brahms's Fourth Symphony second movement opens in what sounds like C major — until it becomes clear that E is the tonal center (E Phrygian).

---

## Tonal Functions of Scale Degrees

Each scale degree has a **tonal function** — its role in establishing and maintaining the key. This is the deeper reason why certain progressions feel stronger than others.

### Tonal Degrees — establish the key

| Degree | Function | Notes |
|---|---|---|
| **I** | Tonic | The center of gravity |
| **IV** | Subdominant | Balances the dominant; "weight on the other side" |
| **V** | Dominant | The strongest tonal factor; determines key more decisively than tonic itself |
| **II** | Quasi-tonal | Partakes of both dominant and subdominant character; "dominant of the dominant"; often absorbed into IV |

> *"The dominant, standing alone, determines the key much more decisively than the tonic chord itself."*

The progressions **IV–V** and **II–V** cannot be interpreted in more than one tonality without chromatic alteration. They are key-defining gestures that don't even need I to confirm the key.

### Modal Degrees — suggest the mode, not the key

| Degree | Function | Notes |
|---|---|---|
| **III** | Mediant | Carries the third of the tonic chord; one note distinguishes major from minor |
| **VI** | Submediant | Also modal; "colors" the tonality |

These degrees have **very little tonal effect** — they don't pull toward the tonic — but they determine whether the music sounds major or minor. Overuse of modal degrees shifts the tonal center: too much III and VI, and the ear begins accepting a different tonic.

### The Leading-Tone (VII)

Melodically important (pulls strongly to I) but harmonically absorbed into V. The progression VII→I is melodically V–I, harmonically speaking. Not considered a basic structural tonal degree.

---

## Tonal Strength of Progressions

A single chord heard alone is ambiguous — C major triad could be:
- I in C major
- IV in G major
- V in F major
- VI in E minor
- III in A-flat major...

**Two chords** reduce the ambiguity dramatically. Each two-chord progression has implications of tonality, in varying degrees:

**Strongly tonal (unambiguous in one key):**
- IV–V, II–V — cannot be heard in two keys without chromatic alteration
- V–VI — "strongly indicative of a single tonality"

**Weakly tonal (ambiguous across keys):**
- I–IV, I–VI, I–III — each can be interpreted in multiple keys

**Three chords** can be essentially unambiguous. Piston recommends building a personal notebook of these "harmonic words" — two- and three-chord formulae that define keys with certainty, studied for their tonal strength, rhythmic character, and frequency in the literature.

---

## Interchangeability of Modes

This is one of Piston's most practically important points:

> *"Major and minor modes are not as distinct in usage as their two scales would seem to indicate."*

**Mode mixture is common and normal.** The major and minor of the same tonic freely share chords:
- In a major context: the minor VI (submediant with minor 6th) is frequently used — it adds color
- In a minor context: the major forms of II and IV (from melodic minor) are used freely
- The final tonic chord of a minor movement may be **major** (the Picardy third)

**The Picardy Third (tierce de Picardie):** Ending a minor-mode piece on a major tonic chord. A standard mannerism of 18th-century writing. The raised third is not a modulation — it is a coloristic gesture on the final chord only.

**Beethoven's Waldstein Sonata** is cited: the I–V progression is stated in C minor, then immediately in C major, and back — only the third degree changes. One note, completely different mode, same tonal center.

**Beethoven's Fifth Symphony** is called the "C minor Symphony" despite its final movement being unambiguously in C major. The tonality is C; the mode changes.

---

## Notes Outside the Scale Don't Break Tonality

> *"Notes outside the scale do not necessarily affect the tonality. Tonality is established by the progression of roots and the tonal functions of the chords, even though the superstructure of the music may contain all the tones of the chromatic scale."*

This is a crucial principle for chromatic music. Chromaticism enriches the harmonic surface; it does not destroy the tonal architecture underneath. The roots and their functional relationships carry the key. All 12 chromatic tones can appear in a passage in C major — as long as the root progressions maintain tonal function, the key is secure.

---

## The Dominant as Key-Definer

The strongest evidence of this principle: **the dominant determines the key**. Hearing a G major triad followed by a C major triad is heard as V–I in C, not as I–IV in G, because the V→I root motion activates the tonal function of the dominant. The tonic is *confirmed* by the dominant's resolution — it barely needs to prove itself independently.

The addition of dissonances and chromatic alterations (the dominant seventh, altered dominants) further intensifies the feeling of tonality by creating additional tendency tones beyond the leading-tone alone.

---

## FormaComposition Implications

**Your `mode` field is a modality choice, not a tonality choice.** The key (tonality) is set by `key`; the mode sets the scale color. Piston's framework validates exactly this separation — they are independent parameters.

**Modal degrees (III, VI) are the color tools.** When FormaComposition needs to add variety to a progression without disturbing the tonal center, III and VI are the right instruments. They add modal color without tonal confusion. This is why progressions like I–VI–IV–V are so common — VI provides modal color while the I–IV–V backbone holds the tonality.

**Mode mixture is free, not exceptional.** The engine should treat major-tonic and minor-tonic chords in the same key as interchangeable, not as separate systems. In C major, a bVI chord (Ab major) is a standard modal mixture chord. In FormaComposition terms: cross-mode borrowing is compositionally valid and should not require special handling.

**II–V is the single strongest key-establishing gesture.** If a section needs to feel tonally anchored quickly, II–V–I (or just II–V if unresolved tension is wanted) is the most efficient tool. This also means that if the engine generates a II–V pattern, the key is being strongly asserted whether that was intended or not.

**The Picardy third is a named device.** A minor-mode piece or section ending on a major I chord is a deliberate, named effect — not an error. Worth having as an explicit option in section/piece JSON: `"picardy_third": true` on the final chord of a minor-mode section.

**Overemphasis on modal degrees shifts the tonal center.** If the engine generates progressions that dwell heavily on III and VI, the ear will re-interpret III as a new tonic (or VI as a new tonic). This is either a bug or an intentional modulation — but it needs to be intentional. The validator should check that tonal and modal degrees are distributed appropriately for the stated key.

**Modes are valid for FormaComposition themes.** Piston treats them as departures from the norm but acknowledges them completely. Dorian, Mixolydian, and Lydian are all compositionally coherent choices for theme definitions — they just generate different harmonic vocabularies (e.g., Dorian's natural II chord is minor, not diminished). The engine's chord-building logic must account for modal interval structures when `mode` is set to anything other than major/minor.

---

*Source: Walter Piston, Harmony (revised edition, 1948 / reissued 1959). Chapter 4, pages 29–40.*
