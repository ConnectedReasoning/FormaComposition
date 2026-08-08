# FormaComposition
## Technical & Compositional Whitepaper

**Connected Reasoning · Version 2.2 · August 2026**

*A generative music composition engine grounded in classical compositional theory, built for the modern composer-developer.*

---

## Table of Contents

1. [Origin & Philosophy](#1-origin--philosophy)
2. [System Architecture](#2-system-architecture)
3. [The Motif System](#3-the-motif-system)
4. [Statefulness: Context-Aware Generation](#4-statefulness-context-aware-generation)
5. [Compositional Techniques & Form](#5-compositional-techniques--form)
6. [Production Toolchain](#6-production-toolchain)
7. [Composition Case Studies](#7-composition-case-studies)
8. [Roadmap & Known Issues](#8-roadmap--known-issues)
9. [Closing](#9-closing-the-system-proposes-the-composer-disposes)

---

## 1. Origin & Philosophy

### 1.1 From Piston to Python: Thirty Years of Deferred Theory

FormaComposition is not a weekend project. Its intellectual roots trace to the mid-1990s, when a sustained self-study of Walter Piston's *Harmony* established the compositional vocabulary that would eventually become the engine's foundation: voice leading, harmonic progression, counterpoint — the structural logic that determines why certain notes follow others and how independent voices relate to each other.

This was classical compositional theory of the highest order, the kind that explains Bach and Beethoven. The knowledge was internalized. But the tools to hear it realized — to close the gap between understanding harmony and experiencing it as music — did not yet exist in accessible form. MIDI existed but was clunky. Software instruments were primitive. The theory went into long-term storage.

### 1.2 The Catalyst: A Productive Misunderstanding

In 2017, a BBC Click interview with Brian Eno appeared to reveal something profound: a bespoke generative composition engine, a personal system where compositional intelligence drove automated music. Eno's use of scientific terminology — probability, stochastic processes — implied a depth that demanded a response.

That response became GenMuso, then GenMuso2, then FormaComposition.

Returning to the video years later, the reality proved more modest. Eno's system consists of three JavaScript modules inside Logic Pro's Scripter plugin:

- **Chance of Playing** — a probability gate deciding whether each note fires
- **Random Transposer** — pitch shifting constrained to allowed scale tones
- **Random Repeater** — probabilistic repetition for density variation

This is a filter on existing material, not a generative compositional engine. There are no motif transforms, no harmonic progression awareness, no multi-voice architecture, no dynamics arcs. It is elegant, but it is fundamentally a set of probability gates.

The misunderstanding was productive. The imagined depth of Eno's system became the design target. FormaComposition was built not to replicate what Eno had, but to be the thing his demonstration *appeared* to be: a system where classical compositional theory — Piston's theory — drives generative music with structural rigor, not just randomness.

> **Key Insight:** FormaComposition overshot Eno's actual system by encoding real compositional theory. The misreading of a source produced something more ambitious than the source itself.

### 1.3 What Eno Did Contribute

The misreading of Eno's depth does not diminish what he genuinely demonstrated: the feedback loop. His workflow — starting the system, leaving the room, returning to adjust parameters, listening for what works — frames composition as curation. The creative act is not writing notes. It is tuning the system until it produces music the composer wants to live with.

That feedback loop — the tight connection between parameter adjustment and auditory result — remains the aspirational model for FormaComposition's ongoing work.

### 1.4 Artistic Influences

| Influence | Contribution to FormaComposition |
|---|---|
| Walter Piston | Harmonic theory, voice leading, counterpoint — the compositional DNA |
| Brian Eno | Generative approach, composition as curation, feedback loop workflow |
| Will Ackerman | New age warmth, emotional directness, acoustic clarity |
| Max Richter | Cinematic minimalism, emotional weight through simplicity |
| David Lanz | Mid-tempo new age, melodic memorability, accessible complexity |
| Led Zeppelin | Dynamic range, tension and release, the value of space and silence |

### 1.5 Core Design Philosophy

- **JSON as the single source of truth.** All compositional decisions live in the JSON layer. No CLI flags for compositional intent.
- **Ear as final arbiter.** Listening tests — including walking with bounced audio — are the primary signal for whether changes work.
- **Hand-played rhythm beats algorithmic rhythm.** The rhythm extractor exists precisely because algorithmic rhythm generation could not achieve the desired musical feel.
- **Prove the system on one complete piece before expanding scope.** Quality over quantity; one strong song beats two weak ones.
- **Artifact as composition.** The most compelling moments emerge from reverb tails, sustain, and effects — not just the notes. FormaComposition generates the harmonic skeleton; Logic Pro and Arturia instruments are where the music actually lives.
- **Iterative pair programming produces more robust results than one-shot generation.** Each iteration emerges from actually using the system.

---

## 2. System Architecture

### 2.1 The Three-Level Hierarchy

FormaComposition organizes every composition into three levels that separate musical concerns cleanly:

| Level | Purpose |
|---|---|
| **Motif** | The atomic musical idea — a short melodic/rhythmic figure with defined intervals, durations, and a transform pool. Lives independently of key or mode. |
| **Piece** | The tonal and formal home — key, mode, tempo range, section structure, and motif references all live here. |
| **Section** | Local variation — overrides piece defaults, defines harmonic progression, arc, density, groove, and per-voice behavior. |

> **What changed since v2.1:** earlier versions split tonal identity into a separate Theme file that pieces referenced — a four-level hierarchy (Motif/Theme/Piece/Section). That split is gone. Theme's fields (key, mode, tempo, motif pool) are absorbed directly into the piece — one JSON file per piece instead of a paired `theme.json` + `piece.json`. What actually mattered about the original split is unchanged: a motif still carries no key information, so the same melodic DNA can be heard in D Dorian, F Lydian, and A Phrygian without rewriting a note.

### 2.2 File Structure

```
compositions/
├── motifs/
│   ├── motif_ascending_hope.json
│   ├── motif_descending_melancholy.json
│   └── motif_<name>.json
└── *.json                # Pieces — key, mode, tempo, section structure,
                           # and motif references all live in one file
```

### 2.3 Core Python Modules

| Module | Role | Description |
|---|---|---|
| `generator.py` | Main engine | Reads JSON, resolves motifs, applies transforms, writes MIDI via mido. Includes `create_chord_context()` for statefulness. |
| `motif_loader.py` | Motif resolution | Resolves a motif reference to a `Motif` object — a string name (checked first against motifs declared inline on the piece, then against the external library) or an embedded dict. |
| `melody.py` | Melody generation | Four behavior modes: generative, lyrical, sparse, develop. All accept optional chord context for statefulness. |
| `bass.py` | Bass generation | Eight styles: root_only, root_fifth, walking, steady, melodic, pulse, pedal, motif. Responds to harmonic context. |
| `percussion.py` | Drum patterns | Five named patterns rendered to MIDI ch.9 with groove templates, swing, and humanization. |
| `rhythm_extract.py` | Rhythm import | Imports hand-played Logic Pro MIDI loops, auto-detects boundaries, quantizes, outputs JSON rhythm patterns. |
| `context.py` | Cross-voice memory | `SectionContext` (cross-voice awareness) and `PieceContext` (cross-section memory). |
| `schemas.py` | Validation | Pydantic v2 models — the single source of validation truth. `PieceModel.model_validate()` replaces the old `validate_piece()` function. |

---

## 3. The Motif System

### 3.1 Motif as Atomic Musical DNA

A motif in FormaComposition is the smallest self-contained musical idea. It has three properties:

- **Intervals** — the semitone steps between successive notes (e.g., `[2, 2, 1, 2]` = whole, whole, half, whole)
- **Rhythm** — the duration in beats for each note (e.g., `[1.0, 1.0, 0.5, 1.5]`)
- **Transform Pool** — the Bach-style transforms available for variation

Critically, the motif carries no key information. It is a pure intervallic and rhythmic idea. The piece assigns it to a tonal world.

### 3.2 Motif File Format

```json
{
  "motif": {
    "name": "ascending_hope",
    "intervals": [2, 2, 1, 2],
    "rhythm": [1.0, 1.0, 0.5, 1.5],
    "transform_pool": [
      "inversion",
      "retrograde",
      "augmentation",
      "diminution",
      "transpose_up",
      "transpose_down"
    ]
  }
}
```

### 3.3 The Transform Pool: Bach-Style Variation

Every motif can be transformed using classical compositional techniques. Each has a specific expressive character:

| Transform | Musical Character |
|---|---|
| `inversion` | Mirror the melodic shape (negate all intervals). Turns ascent into descent — contrast, the "answer" in fugal form. |
| `retrograde` | Reverse the sequence. The same material heard backwards — exploration, "what if we came from a different direction?" |
| `augmentation` | Double all note durations. Time slows down — reflection, meditation, the coda feeling. |
| `diminution` | Halve all note durations. Time accelerates — urgency, development, compressed tension. |
| `retrograde_inversion` | Reverse and negate. Maximum distance from the original while using identical material — the furthest developmental point. |
| `transpose_up` | Shift the motif up 2 semitones. Brightness, lift, departure. |
| `transpose_down` | Shift the motif down 2 semitones. Gravity, return, settling. |
| `shuffle` | Randomly reorder intervals. Dissolution — the motif losing its shape. |
| `expand` | Scale intervals by 1.5x. Wider leaps — drama, operatic gesture. |
| `compress` | Scale intervals by 0.5x. Smaller steps — intimacy, murmuring. |

> **Bach Principle:** The genius of Bach is intentional rule-breaking. FormaComposition's transform system enables surprise, not just correctness. Subverting harmonic expectations rather than confirming them is the target.

### 3.4 Motif Resolution

Pieces reference motifs rather than always embedding them, so the same motif can live inside multiple pieces:

```json
{
  "piece": {
    "name": "Dorian Dawn",
    "key": "D",
    "mode": "dorian",
    "tempo": {"min": 60, "max": 80},
    "motif": "ascending_hope"
  }
}
```

A `motif` field resolves one of two ways:

| Format | Resolution |
|---|---|
| `"motif": "ascending_hope"` | String — checked first against motifs the piece declares inline (its own `motifs` pool), then against the external library at `motifs/motif_ascending_hope.json` |
| `"motif": {"intervals": [...]}` | Dict — used directly as the embedded definition |

This means a motif can now be named and referenced entirely within a single piece file, with no separate library entry required, while existing library-file references keep working unchanged.

---

## 4. Statefulness: Context-Aware Generation

### 4.1 The Problem: Melody That Doesn't Know What's Coming

Without statefulness, each chord in a progression is generated in isolation. The melody creates notes that work over the current chord — but it has no knowledge of what follows. When a deceptive cadence arrives (V→vi instead of V→I), the melody can sound caught off guard. When a modal color chord appears (bVII in D Mixolydian), the melody may treat it as a chromatic accident rather than an intentional destination.

The result is music that sounds *generated* rather than *composed*. The notes are technically correct but lack the forward-leaning intention that characterizes composed melody.

### 4.2 The Solution: Chord Context

FormaComposition introduces a chord context system. For each chord in a progression, the generator builds a context dictionary:

| Key | Value |
|---|---|
| `chord_index` | Position in progression (0-indexed) |
| `total_chords` | Total chords in section |
| `next_chord` | The `VoicedChord` object that follows |
| `next_chord_root` | Root name of next chord (e.g., `"vi"`) |
| `bars_in_this_chord` | Duration of current chord in bars |
| `bars_in_next_chord` | Duration of next chord in bars |
| `section_name` | Name of the current section |

This context is passed through to all voice generators. The melody generator uses it to create voice-leading gravity — biasing the final note of each phrase toward tones that belong to the next chord.

### 4.3 Implementation: Lyrical Behavior

Statefulness is implemented in the lyrical melody behavior. The logic is surgical:

```python
# Near the end of a phrase, bias toward next chord's tones
is_last_note = (i == len(rhythm_events) - 1)
if is_last_note and context and next_chord_tones != chord_tones:
    candidates.extend(next_chord_tones)
```

This extends the candidate pool rather than forcing a choice. The melody "leans toward" the next chord without being locked into it. The effect is subtle — heard as voice-leading intention rather than a mechanical rule.

> **Design Principle:** Responsive, not predictive. The generator looks at what's actually coming (next chord), not at abstract rules about what should happen. The composition leads; the generator follows.

### 4.4 Why Lyrical Only?

- **Sparse** behavior is too loosely constrained to benefit from look-ahead.
- **Develop** behavior uses motif transforms, and chord context would conflict with the transform logic.
- **Generative** behavior is intentionally aimless by design.

Lyrical — already stepwise-constrained, already singing — gains the most obvious improvement from knowing where it's landing.

### 4.5 The Deceptive Cadence Test Case

The composition "Return" (D Mixolydian, 62 BPM) was designed specifically to test statefulness in practice. The Passage section uses a V→bVI deceptive cadence — the harmonic moment where traditional expectation (V resolves to I) is subverted.

**Without statefulness:** the melody generates over V expecting resolution to I, and may land on chord tones that make the bVI arrival feel wrong or accidental.

**With statefulness:** the melody knows bVI is coming. At the end of the V phrase, it leans toward bVI tones. The deceptive cadence feels compositionally intentional — the "false resolution" is heard as a choice, not a bug.

---

## 5. Compositional Techniques & Form

### 5.1 Three Independent Compositional Dimensions

Every piece operates across three independent axes. Melody lives at their intersection:

| Dimension | Description |
|---|---|
| **Harmony (vertical)** | What is sounding at any moment — chord voicing, voice leading, progression logic |
| **Rhythm (within-bar)** | How notes articulate inside each bar — groove, swing, humanization, density |
| **Temporal (large-scale)** | How sections relate over time — arc, dynamics, section structure, emotional narrative |

A common failure mode in generative music is treating harmony and rhythm as one concern. FormaComposition treats them as separate clocks, creating natural-feeling phasing even when chord changes and rhythmic patterns have different periodicities.

### 5.2 Modal Palette

Harmony in FormaComposition isn't limited to major/minor. The mode list spans the seven diatonic modes (Ionian through Locrian) and a set of non-diatonic additions — harmonic minor, melodic minor, pentatonic major, pentatonic minor, blues, whole tone, diminished, and augmented hexatonic — plus, new this month, four modes chosen for real musicological reference points rather than as generic "more presets":

- **Pelog** — not an authentic Javanese pelog tuning (real pelog is non-12-TET and varies by ensemble), but Satie's own 12-TET approximation of it: the exact six-note scale of *Gnossienne No. 3*, written after he heard gamelan at the 1889 Paris Exposition. Same honesty level as Debussy's pentatonic "Pagodes" — an impressionistic gesture, not a transcription.
- **Arabic** (double harmonic major / Hijaz Kar) — two augmented-second leaps give it its character. The common Western umbrella term "Arabic scale" covers real maqam practice, which actually uses quarter-tone inflections a 12-TET scale can't represent.
- **Hirajoshi** — Japanese koto pentatonic tuning. Not the same shape as the pentatonic minor / blues scales above — different interval steps, no minor 7th — which is exactly what gives it a distinct "Japanese" character instead of reading as "blues with different notes."
- **Insen** — a symmetric five-note scale with no clear tonal center. Where the other three above are borrowed color from a specific tradition, this one earns its place through ambiguity: static, non-functional, well suited to ambient fields that aren't trying to resolve anywhere.

> **Known caveat:** Roman numeral progressions assume seven scale degrees. On the non-heptatonic modes above — pelog (6 notes), hirajoshi / pentatonic major / pentatonic minor (5 notes) — a numeral beyond the mode's actual note count silently wraps and aliases onto an earlier degree instead of erroring. On pelog, "VII" lands on the same root as "I." On hirajoshi, "VI" wraps to "I" and "VII" wraps to "II." No crash, no warning — just a different chord than the numeral implies. Until a lint check exists for this, keep progressions within a mode's actual degree count: I–VI for pelog, I–V for any pentatonic mode.

### 5.3 Harmonic Authorship: From Sampling to Structure

Recent work moved harmonic choice away from random sampling within a mode and toward deliberate structural control. Two moves in particular:

- **Pedal and drone bass anchoring.** A `pedal` bass style holds a single tone — the tonic — under the whole progression regardless of what the chords above are doing. The harmonic field stays static while the surface moves: an Eno-ish drone rather than a bassline that walks or outlines every chord change.
- **Canon-offset call-and-response.** A `canon_offset` parameter delays a voice's entry by a set number of beats relative to another voice — the mechanism for genuine question-and-answer between voices, not just parallel harmony.

Together these make the two catalog strategies actually distinct instead of variations on the same randomness: ambient/background work leans on the static harmonic field and pedal anchoring, with no functional dominant pull; pop/song-form work keeps functional harmonic motion, exact-repeat hooks, and transform development. Applying them inconsistently is what made earlier output feel arbitrary. The fix wasn't a new algorithm — it was choosing on purpose which strategy a given piece is using.

### 5.4 Dynamics Arcs

Every section carries a named arc that shapes energy across its duration. These drive which notes are chosen, how densely they're voiced, and how generators select from available candidates — not just post-production volume.

| Arc | Musical Character |
|---|---|
| `fade_in` | Begins sparse and quiet, builds toward section end — opening, arrival, waking up |
| `swell` | Builds to a peak in the middle, recedes — the breath of a section, wave-like |
| `peak` | High energy throughout, sustained intensity — development climax, urgency |
| `breath` | Releases tension deliberately — the exhale after a climax, preparation for return |
| `fade_out` | Recedes toward silence — closing, reflection, dissolution |

### 5.5 Sonata Form in FormaComposition

"Threshold" demonstrates full sonata form — 98 bars, ~5 minutes — implemented entirely in the JSON schema. This is not an approximation; it is Exposition, Development, Recapitulation, and Coda with proper harmonic relationships.

| Section | Technique | Character |
|---|---|---|
| Exposition A (16 bars) | Subject — original motif in home key (i) | fade_in, sparse, pedal bass |
| Exposition B (14 bars) | Answer — inverted motif, modulates to relative major | swell, medium density |
| Development A (10 bars) | Retrograde fragment, 0.85x compression, tonal unrest | swell, episodic |
| Development B (10 bars) | Retrograde inversion, 0.6x, peak density, dissonant counterpoint | peak, intensification |
| Development C (8 bars) | Stretto climax — 0.45x compression, maximum urgency | peak, brief |
| Development D (10 bars) | Breath — original motif, 1 interval fragment, sparse | breath, release |
| Recapitulation A (16 bars) | Subject returns in home key, slightly richer texture | swell, recognition |
| Recapitulation B (14 bars) | Answer reharmonized — stays in home key now | swell, resolution |
| Coda (12 bars) | Augmented subject — half speed, reflective, fades to silence | fade_out, reflection |

### 5.6 Fugal Techniques

Every technique serves an emotional purpose:

- **Inversion = contrast.** The inverted subject provides the "answer" — familiar but different.
- **Retrograde = exploration.** The subject heard backwards suggests "what if we came from another direction?"
- **Retrograde inversion = maximum distance.** Both transforms applied simultaneously — the developmental peak, furthest from home.
- **Stretto compression = urgency.** Subjects entering in rapid succession — the feeling of compression before release.
- **Augmentation = reflection.** The subject at half speed in the coda — time expanding, the piece becoming contemplative.

None of these is deployed as an academic exercise. Each serves the arc: stability → adventure → homecoming → reflection.

### 5.7 The Rhythm Extraction Philosophy

FormaComposition originally attempted to generate rhythms algorithmically. The results were technically correct but musically unconvincing. The solution was to stop fighting it.

`rhythm_extract.py` imports hand-played Logic Pro MIDI loops, auto-detects loop boundaries, quantizes them, and exports JSON rhythm patterns. These real-played rhythms become the rhythmic DNA for generated compositions.

The implication: the best rhythm generation is no rhythm generation. Record it by hand, extract it, and let the engine borrow the feel.

---

## 6. Production Toolchain

### 6.1 Hardware

| Device | Role |
|---|---|
| Mac Studio M1 (32GB) | Primary development and performance machine |
| Arturia Keystep | Manual motif input |

### 6.2 Software Instruments (Arturia V Collection)

| Instrument | Character |
|---|---|
| Pigments | Primary synthesizer — wavetable, virtual analog, granular |
| Mini Moog V4 | Bass and lead lines — warm, clear pitch definition |
| Solina V | String ensemble — warmth, vintage texture |
| Mellotron V | Orchestral color — tape warmth, distinctive timbres |
| Juno-6V | Pad and chord textures — lush, chorused |
| Modular V3 | Experimental sound design |
| Augmented Collection | Hybrid acoustic/electronic textures |

### 6.3 Effects Chain

| Effect | Role |
|---|---|
| Valhalla Shimmer | Primary reverb — the signature ambient texture. The reverb tail *is* the composition. |
| Valhalla Supermassive | Secondary reverb/delay — space and depth |
| Arturia Sitral-295 | Stereo field treatment |
| Arturia Chorus JUN-6 | Vintage chorus modeled on the Juno-6 |
| Arturia Pre 1973-PRE | Preamp character and warmth |
| Arturia Comp TUBE-STA | Compression with tube character |
| Arturia Rev LX-24 | Hall reverb for counterpoint voices |

### 6.4 Distribution

| Tool | Purpose |
|---|---|
| DistroKid | Streaming distribution (Spotify, Apple Music, etc.) |
| Cyanite | AI mood/genre analysis for metadata optimization |
| Pixelmator | Album artwork — SVG to PNG conversion |
| Python / Pillow | Generative album artwork creation |

### 6.5 Mixing Philosophy: Stacking Warmth

A key technical lesson from the Connected Reasoning catalog: stacking warmth across all channels creates low-mid competition that muddies the mix. Each voice must give something up for the whole mix to work.

Practically: if the pad is warm, the melody should be bright. If the bass is full, the counterpoint should be thin. The mix is a negotiation between voices, not a stacking of identical textures.

---

## 7. Composition Case Studies

### 7.1 City Night Patrol — What Works Without Melody

"City Night Patrol" is a released Connected Reasoning track that works specifically because it avoids carrying a melody. The insight is counterintuitive: many ambient and cinematic pieces succeed not through melodic development but through harmonic motion, rhythm, texture, and space.

The most compelling moments came from reverb tails, sustain, and effects artifacts — not the notes. The Edge's guitar work operates on the same principle: the delay and reverb artifact *is* the composition. The notes are the seed; what they become in space and time is the music.

> **Key Craft Lesson:** Melody is a craft requiring deliberate effort. Pieces that avoid carrying melody succeed more reliably than those leading with it before the melodic craft is strong enough to carry the piece.

### 7.2 Return — Testing Statefulness in Practice

"Return" (D Mixolydian, 62 BPM) was composed specifically as a test bed for the statefulness system. Its concept — *returning to a place that's home but changed* — maps directly onto its harmonic structure.

D Mixolydian was chosen deliberately: the flattened seventh (C natural) creates a bittersweet, floating quality. The major tonality (D-F#-A) provides warmth and openness. The b7 never resolves — it just lives there. This is the perfect metaphor: familiar but not quite the same.

| Section | Compositional Idea |
|---|---|
| Threshold (12 bars) | Sparse, pedal bass on D, I-V-vi — the question before the journey |
| Passage (16 bars) | V→bVI deceptive cadence — the compositional and emotional center. Melody must anticipate bVI. |
| Recognition (20 bars) | bVII reveal (C major) — the Mixolydian color becomes obvious. Walking bass, motif transforms. |
| Settling (16 bars) | I-bVII-IV-I loop, sparse — acceptance without resolution. The piece doesn't end; it accepts. |

### 7.3 Threshold — Full Sonata Form

"Threshold" is the most formally ambitious composition in the FormaComposition catalog, implementing complete sonata form (98 bars, ~5 minutes) using Evening Water as its thematic material (D Dorian / A Aeolian, 70 BPM, seed 137).

The piece demonstrates that form-driven composition with classical techniques is not academic exercise — it is creative storytelling. Every technique serves the emotional arc: exposition (stability) → development (adventure and tension) → recapitulation (homecoming) → coda (reflection).

The stretto climax in Development C (0.45x compression, 8 bars) is the turning point. After it, the breath section is necessary and earned — not a structural convention but a genuine relief from urgency.

> **Insight:** Seed-based variation means the same composition can yield multiple melodically distinct versions with identical harmonic structure. Generate four seeds, ear-check all four, ship the one that sings.

---

## 8. Roadmap & Known Issues

### 8.1 Active Development

| Item | Status |
|---|---|
| Per-chord embedded rhythm patterns | **Critical.** Harmony voices holding whole notes while melody articulates above creates lifeless output. The fix is per-chord onset/duration/velocity patterns so chord changes "swing." Toto's "Africa" is the reference model. |
| `motif_transform` wiring | Function signatures updated in `generator.py` and `melody.py`; wiring into `generate_develop` and validator incomplete. |
| IAC MIDI streaming (proof of concept) | Round-trip via file export today; an IAC Driver bridge would let generated MIDI stream straight into Logic in real time. Early-stage — no GUI, no live parameter control yet. |

### 8.2 Known Issues

| Item | Status |
|---|---|
| Roman numeral aliasing on non-heptatonic modes | Roman numerals I–VII assume 7 scale degrees. On 5- or 6-note modes (pelog, hirajoshi, both pentatonics) numerals beyond the mode's actual degree count silently wrap onto an earlier degree rather than erroring — see §5.2 for specifics. Keep progressions within the mode's real degree count until a lint check exists. |

### 8.3 Backlog

| Item | Notes |
|---|---|
| Bass statefulness | Bass already looks ahead (approach notes). Extend to full chord context. |
| Counterpoint context | Counterpoint generator could avoid voice-leading conflicts by knowing melody and bass context. |
| LinnDrum MIDI library | Integration of LinnDrum pattern library for historical rhythm authenticity. |
| Fugal mode flag | Optional — test on a few pieces before committing. Not foundational. |
| Piece-awareness | Generator reads any piece JSON, adjusts chord vocabulary to mode automatically. |
| Per-section lock toggles | Swift companion app — lock individual sections during generation. |
| Motif blending | Interpolate between two motifs over time: `motif_a`, `motif_b`, `blend: 0.5`. |
| Motif chains | Sequence of motifs: A → B → A' → C for larger-scale melodic planning. |
| Open-source release | GitHub release of FormaComposition. Potential `Forma` GitHub organization. |

### 8.4 Production Target

Two pieces per week under Connected Reasoning. Released catalog includes: City Night Patrol, The Circle at Ember Grove, Rebecca, Still Cove (~4 min, D Dorian, 68 BPM), and others.

The quality filter is active and intentional: one strong song beats two weak ones.

### 8.5 AI in the Workflow — Two Different Claims

FormaComposition does not use AI or statistical models to generate music. Every note the engine writes comes from constraint satisfaction over encoded music theory — voice leading rules from Piston, harmonic function, mode and scale definitions, transform logic. There is no trained model anywhere in the generation path; the same JSON input with the same seed produces the same output every time, because it's deterministic code, not sampling from a distribution.

Separately: Claude was used to help *build* the tool — pair-programming the engine itself, the way you'd use any collaborator, with Claude Haiku handling narrower, already-scoped implementation work once a design is settled. That's a claim about how the software was written, not about how the software writes music. Conflating "AI helped build this" with "AI is generating your music" would be exactly the misunderstanding this audience is primed to assume — worth stating both halves plainly, separately, and without hedging.

---

## 9. Closing: The System Proposes, the Composer Disposes

FormaComposition exists at the intersection of two moments separated by three decades: the study of Walter Piston's *Harmony* in the 1990s, which provided the compositional vocabulary, and the emergence of accessible tools — Python, mido, Logic Pro, Arturia's instrument libraries — that finally made it possible to express that vocabulary as realized music.

Brian Eno's BBC demonstration was the catalyst that connected the two, even if the connection was built on a productive misunderstanding. The imagined depth of Eno's system became the design target. FormaComposition overshot it by encoding actual compositional theory — motif development, harmonic structure, voice independence, dynamics as narrative — into a generative engine.

There is a parallel here to the history of quantum mechanics. Planck introduced quantization as a mathematical trick. Einstein gave it physical reality but rejected where it led. Bohr embraced it, extended it, and built the framework. Eno planted the seed of automated composition, then stopped at probability gates. FormaComposition embraces the idea, extends it with classical compositional rigor, and builds the framework he never did.

The system proposes. The composer disposes. Thirty years in the making.

---

*Connected Reasoning · FormaComposition v2.2 · August 2026*
