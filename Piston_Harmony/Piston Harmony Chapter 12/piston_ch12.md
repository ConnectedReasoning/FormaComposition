# Piston — Harmony: Chapter 12
## Cadences

> *There are no more important formulae than those used for phrase endings. They mark the breathing places in the music, establish the tonality, and render coherent the formal structure.*

---

## The Four Cadence Types

The cadential formulae of common-practice music remained essentially stable across two centuries of enormous stylistic change. Changes in harmonic color and external manner didn't disturb the fundamental cadence types — they only confirmed their universality.

---

### 1. The Authentic Cadence — V → I

The full-stop. The dominant resolving to the tonic. Can be extended with the cadential approach: **II6–I64–V–I** is the strongest possible form of final cadence.

#### Perfect vs. Imperfect

**Perfect authentic cadence:**
- Both V and I in **root position**
- **Tonic note in the soprano** at the end
- Most conclusive arrangement possible

**Imperfect authentic cadence** — any other form of V→I:
- V in first inversion (V6) approaching I → less conclusive
- Third or fifth in soprano at the end → less finality
- Any combination producing less-than-maximum closure

A hard boundary between perfect and imperfect is neither possible nor important. The degree of finality is a continuum, dependent on many contributing factors.

#### Approach to the Dominant

**Avoid root-position I directly before V** in a cadence — the tonic note in the bass appears to anticipate the final tonic, weakening the cadence by foreshadowing it. **Prefer I6** (first inversion tonic) in the penultimate position.

#### Ornamentation at the Cadence

The final tonic chord may be decorated:
- **Appoggiatura** arriving on I (melody leans by step into the tonic)
- **Suspension** of the dominant over the tonic bass (V sounds above the tonic bass note before resolving)
- The dominant may continue over the tonic bass briefly before resolving upward

#### Chromatically Raised Fourth Degree

A chromatically raised fourth degree appearing before V acts as a **leading-tone to the dominant** — a temporary V-of-V feeling. This has more melodic than harmonic significance. If it leads to a full VofV chord (dominant of dominant), it may be better analyzed as a brief modulation to the dominant key.

---

### 2. The Half Cadence — any chord → V

The comma. Unfinished. Expectant. The phrase ends on V without resolving. **Any chord may precede V** in a half cadence.

Common approaches:
- `IV–V` — subdominant to dominant
- `II–V` or `II6–V` — supertonic (root or first inversion) to dominant
- `I–V` — tonic to dominant (simplest)
- `VI–V` — submediant to dominant (unusual)
- `VofV–V` — dominant of dominant, strengthens the dominant arrival

#### Accentuating the Half Cadence with I64

The cadential six-four frequently appears before V in a half cadence:
- `IV–I64–V` — most common
- `VI–I64–V`
- `I–I64–V` — when I precedes I64, prefer I6 root not root-position I

The VofV chord appearing before V at a half cadence raises an analytical question: is this a modulation to the dominant key, or just a chromatic approach chord? When the subsequent phrase continues in the tonic key, it seems useless to analyze the VofV as a modulation. When a strong series of chords in the dominant key leads to the cadence, a modulation analysis is appropriate.

---

### 3. The Plagal Cadence — IV → I

**Most often used after an authentic cadence** as a final gesture — the "Amen" cadence. After the dominant-and-tonic emphasis of the authentic cadence, the subdominant is tonally satisfying before the final tonic.

Can also appear as a standalone phrase ending, without a preceding authentic cadence.

#### The Minor Plagal in Major Context
Using the **minor form of IV** (iv, with flattened sixth degree) in a major-mode plagal cadence gives a particularly colorful ending. The modal color of the minor subdominant against the major tonic creates a warm, expansive effect heard frequently in 19th-century closings.

#### With the Supertonic
The supertonic (II) may be added to the subdominant chord without destroying the plagal effect:
- As a passing tone
- As a chord tone (first inversion seventh chord): `II6/5 → I`
- In the extreme case: supertonic triad over a tonic pedal in the bass (creating a Neapolitan-adjacent sound)

The supertonic acts as a subdominant substitute here — the entire subdominant family (IV and II) partakes of the plagal quality.

---

### 4. The Deceptive Cadence — V → anything but I

V followed by any chord **except I**. The dominant has been established; the expected resolution is withheld.

> *"The deceptive cadence is quite as good an indicator of the tonality as the other cadences — often even better."*

It is the establishment of V **as dominant** that shows the key — not its ultimate resolution. A deceptive cadence identifies the key just as clearly as an authentic one.

**Most common: V → VI**
The most frequent deceptive resolution. The dominant appears as an appoggiatura chord over the sixth degree bass. The leading-tone of V resolves upward to the tonic; the other two upper voices descend to the nearest chord tones of VI; the third of VI is doubled (Ch. 3 rule).

**Other common resolutions:**
- **V → IV6** — subdominant in first inversion, on the same bass note as VI (the sixth degree serves as bass for both). Effective because it avoids the tritone cross-relation of V–IV root position.
- **V → chromatically altered chord** — seventh chord on the sixth degree with raised root and third; would proceed to V if allowed to resolve in the key.
- **V → pivot chord** — the chord of resolution begins a new key. The deceptive cadence serves simultaneously as the end of one phrase and the beginning of a modulation.

#### At the End of a Piece
Using a deceptive cadence near the end sustains interest at the moment when the final authentic cadence is expected, providing the composer an opportunity to add another phrase before the true close.

---

## Phrase Overlapping at the Cadence

The deceptive cadence often functions as a **joint between two overlapping phrases**. The second phrase begins simultaneously with the last chord of the first phrase. The melodic movement over the last chord of the first phrase then acts as an anacrusis to the downbeat of the second phrase.

Non-overlapping phrases may appear to overlap because of melodic continuity in the final measure — the melody moves over the last chord of the first phrase in the form of an anacrusis to the second phrase's first beat.

---

## Cadential Extensions

Cadences may be extended by:
- **Repetition of the cadential formula** — the V–I is stated, then repeated before continuing
- **Lengthening the harmonic rhythm** — the motion of root changes slows while melodic activity continues above

---

## Summary Table

| Type | Formula | Character | Most Common Context |
|---|---|---|---|
| **Perfect authentic** | (II6–I64–)V–I, root pos, tonic in S | Maximum finality | Final cadence of movement |
| **Imperfect authentic** | V6–I, or non-tonic soprano | Less final | Mid-movement phrase endings |
| **Half** | (any)–V | Expectant, open | Antecedent phrases; mid-period |
| **Plagal** | IV–I (or iv–I) | Settled, warm | After authentic; final "Amen" |
| **Deceptive** | V–VI (or V–other) | Surprise; continuation | Avoiding closure; phrase overlap |

---

## FormaComposition Implications

**Every section needs a cadence type, not just a final chord.** The current JSON defines `progression` as a list of Roman numerals, but doesn't explicitly label the cadential formula at the end. Adding a `cadence` field with values like `"authentic_perfect"`, `"half"`, `"plagal"`, `"deceptive_vi"` would make the engine's section endings intentional rather than coincidental.

**The strongest authentic cadence is II6–I64–V–I.** FormaComposition currently generates V–I at the end of sections. That's correct but minimal. Inserting II6–I64 before the final V–I costs two extra chords and immediately makes the cadence sound like real composed music rather than a chord exercise.

**Avoid root-position I directly before V in a cadence.** When the section's second-to-last chord is I root position going to V, this should trigger the validator to suggest I6 instead. The anticipation of the final tonic weakens the authentic cadence — this is one of the most audible ways that generated progressions can feel "off."

**The deceptive cadence at the section boundary is a structural tool.** When a FormaComposition section ends on V→VI instead of V→I, it creates continuation and momentum rather than closure. This is how to keep a multi-section piece driving forward rather than stopping and restarting at each section line. Planning which sections end with authentic and which end with deceptive or half cadences is the large-scale structural architecture of a piece.

**The minor plagal (iv–I) in a major-mode close** is a single voicing choice — lower the third of IV by a half-step — but produces one of the most distinctive, warm cadential sounds in the vocabulary. Worth naming as a specific option: `"cadence": "plagal_minor"`.

**Cadential extension is a named technique.** A section that repeats its final V–I before continuing is doing something specific and intentional. The `chord_bars` list already supports this implicitly (just add more bars with V and I at the end), but labeling it as "cadential extension" in the analysis vocabulary helps compositional planning.

---

*Source: Walter Piston, Harmony (revised edition, 1948 / reissued 1959). Chapter 12, pages 125–137.*
