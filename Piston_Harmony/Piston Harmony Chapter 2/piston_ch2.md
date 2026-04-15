# Piston — Harmony: Chapter 2
## Triads

> *The triad is the basis of our whole harmonic system.*

---

## What a Triad Is

A chord is two or more intervals combined. Chords are built by **superposing intervals of a third**. The triad — three tones, two stacked thirds — is the simplest chord and the foundation of the entire common-practice harmonic system.

The three factors of the triad have fixed names regardless of their arrangement:
- **Root** (also: fundamental) — the generating tone, the one the chord is named after
- **Third** — a third above the root
- **Fifth** — a fifth above the root (a third above the third)

---

## Inversions

Which factor sits in the bass determines the position:

| Bass note | Name |
|---|---|
| Root | **Root position** |
| Third | **First inversion** |
| Fifth | **Second inversion** |

Roman numerals identify both the scale degree *and* the position. The chord quality (major, minor, etc.) doesn't change with inversion — only the bass note does.

---

## Four Kinds of Triads

Classified by the intervals between root and the other two tones:

| Type | Third | Fifth | Sound |
|---|---|---|---|
| **Major** | major 3rd | perfect 5th | stable, bright |
| **Minor** | minor 3rd | perfect 5th | stable, dark |
| **Augmented** | major 3rd | augmented 5th | dissonant, unstable |
| **Diminished** | minor 3rd | diminished 5th | dissonant, unstable |

Major and minor are **consonant** (contain only consonant intervals). Augmented and diminished are **dissonant** — their instability demands resolution.

---

## Triads on Each Scale Degree

This table is one of the most important reference tables in the book. Which triad type falls on which degree is not arbitrary — it follows directly from the scale's interval pattern.

### Major mode
| Degree | Triad type |
|---|---|
| I | **major** |
| II | minor |
| III | minor |
| IV | **major** |
| V | **major** |
| VI | minor |
| VII | diminished |

### Minor mode (harmonic)
| Degree | Triad type |
|---|---|
| I | minor |
| II | diminished |
| III | **augmented** |
| IV | minor |
| V | **major** |
| VI | **major** |
| VII | diminished |

**Critical observations:**

- **V is major in both modes.** This is *why* harmonic minor raises the VII — to keep the dominant chord major, preserving the leading-tone pull to tonic. Natural minor would give a minor V, which is far weaker.
- **VII is diminished in both modes.**
- The only augmented triad in common practice is **III in minor** — it is rare and handled carefully.
- **I, IV, V** being major in the major mode is the bedrock of tonal harmony. Everything else is color and tension relative to this foundation.

---

## Four-Part Writing

Piston establishes SATB (soprano/alto/tenor/bass) as the working model for harmony exercises throughout the book. Three points:

1. **"Voices" doesn't mean vocal.** It means melodic lines with independent horizontal motion, whether sung or played.
2. **Four parts solve the doubling problem.** A triad has three tones; four-part writing requires doubling one of them.
3. **Voice leading always takes precedence** over vertical chord considerations. Chords exist because melodic voices coincide — the horizontal creates the vertical.

### Voice ranges (approximate)
| Voice | Range |
|---|---|
| Soprano | C4 – G5 |
| Alto | G3 – C5 |
| Tenor | C3 – G4 |
| Bass | E2 – C4 |

Exceeding these occasionally is fine; the "center of gravity" of each voice should stay within normal range.

---

## Doubling

With a three-tone triad in four parts, one tone must be doubled. The default rule:

> **In root position, double the root.**

The root may be doubled at the octave above or even at the unison. This is the norm; exceptions exist and will be addressed in later chapters as specific chord types demand different treatment (e.g., the leading-tone is generally *not* doubled).

---

## Spacing

**The commonest arrangement:** wide intervals at the bottom, smaller intervals at the top. This mirrors the overtone series — lower harmonics are more spread out.

**Practical rule:** Intervals wider than an octave are avoided between soprano–alto and alto–tenor, but are acceptable between tenor and bass.

### Close vs. Open Position

| Type | Definition |
|---|---|
| **Close position** | Three upper voices (SAT) all within a single octave |
| **Open position** | Soprano and tenor are more than an octave apart |

Both are equally valid. The choice depends on melodic direction of the parts, register of the soprano, and the overall balance needed. The ideal — all voices in corresponding registers (all high, all medium, all low) — is rarely achievable because melodic motion overrides it.

> *"The intervals between the voices are an important factor in the texture and actual sound of the music."*

This is a direct connection to FormaComposition's harmony voice spacing — uneven spacing (close upper voices, gap to bass) is the most common texture, and deliberately varying it is a meaningful compositional choice.

---

## FormaComposition Implications

**The triad-type-per-degree table is the engine's harmonic vocabulary table.** When the engine selects chord tones for a given Roman numeral in a given mode, it is traversing exactly this table. Any bug in that logic — e.g., treating III in minor as minor rather than augmented — produces wrong output.

**V is major in both modes.** If the engine generates a minor V chord in a minor key, that is incorrect by Piston's standard. This is the most common source of "sounds wrong but I can't place why" in generated harmony.

**Doubling the root is the safe default.** For the harmony voice, when in root position, doubling the bass note (root) at the octave is the correct starting point. Deviations — doubling the third or fifth — produce specific coloristic effects and have specific rules attached.

**Close vs. open position is a spacing decision that affects texture substantially.** The engine's voice spacing logic should be explicit about which it is choosing, not leave it to chance. Close position is denser and tighter; open position is airier and more spread. Both are correct; the choice should be intentional.

**Voice leading priority over chord priority.** Piston states this explicitly: chords arise from the coincidence of melodic lines, not the other way around. This means the counterpoint voice should not merely fill in chord tones — it should be a melodic entity that *happens* to harmonize correctly.

---

*Source: Walter Piston, Harmony (revised edition, 1948 / reissued 1959). Chapter 2, pages 10–16.*
