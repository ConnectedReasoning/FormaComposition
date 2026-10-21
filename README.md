# FormaComposition

**A rule-based generative music engine, grounded in classical harmonic theory — not machine learning — that turns JSON piece definitions into multi-voice MIDI.**

No training data, no statistical model. Every note the engine writes — which chord tone a melody leans toward, how a bass line approaches a chord change, how a counterpoint voice resolves a dissonance — traces to an explicit rule out of Walter Piston's *Harmony*. You define a motif, a key/mode/tempo, and a section-by-section form in one JSON file; the engine resolves it into melody, harmony, bass, counterpoint, and percussion that stay musically aware of each other, and renders it to a standard MIDI file for production in your DAW of choice.

Built and maintained by [Connected Reasoning](https://github.com/ConnectedReasoning).

---

## Quickstart

**Requirements:** Python 3.10+, [`pydantic`](https://pypi.org/project/pydantic/) v2, [`mido`](https://pypi.org/project/mido/), `numpy`

```bash
git clone https://github.com/ConnectedReasoning/FormaComposition.git
cd FormaComposition
pip install -r requirements.txt
```

### Generate your first piece

A complete, working piece ships as [`examples/quickstart.json`](examples/quickstart.json):

```json
{
  "title": "Dorian Dawn",
  "key": "D",
  "mode": "dorian",
  "tempo": { "min": 68, "max": 76 },
  "seed": 42,
  "motif": {
    "name": "ascending_hope",
    "intervals": [2, 2, 1, -2, -1],
    "rhythm": [1.0, 0.5, 0.5, 1.0, 1.0],
    "transform_pool": ["inversion", "retrograde"]
  },
  "form_type": "song",
  "form": ["opening", "lift", "opening"],
  "sections": {
    "opening": {
      "bars": 8,
      "progression": ["i", "bVII", "IV", "i"],
      "density": "sparse",
      "melody": "develop",
      "bass_style": "pedal",
      "arc": "fade_in",
      "rhythm": "motif",
      "harmony_rhythm": { "rhythm": "sustain" },
      "voices": [{ "register": "alto", "behavior": "develop", "velocity": 90 }]
    },
    "lift": {
      "bars": 8,
      "progression": ["i", "v", "bVII", "IV"],
      "density": "medium",
      "melody": "develop",
      "bass_style": "root_fifth",
      "arc": "swell",
      "rhythm": "motif",
      "harmony_rhythm": { "rhythm": "sustain" },
      "voices": [{ "register": "alto", "behavior": "develop", "velocity": 90 }]
    }
  }
}
```

Run it from the repo root:

```bash
python forma/main.py examples/quickstart.json
```

That writes a standard type 1 `.mid` file with separate melody, harmony, bass and chord-marker tracks, ready to import into Logic Pro, Ableton, or any DAW. Same file + same `seed` = byte-identical MIDI. Other useful flags:

```bash
python forma/main.py piece.json --output ./output/name.mid   # explicit output path
python forma/main.py p1.json p2.json --outdir ./album/        # batch, one file per piece
python forma/main.py piece.json --info                        # inspect without generating
```

More complete pieces, from one-section sketches to a multi-minute fugue, are in [`compositions/`](compositions/).

Before you write a real piece, skim the **[cheat sheet](docs/manuals/formacomposition_cheatsheet_v11.md)**. It documents every field, every enum value, and every setting that's schema-legal but musically a no-op (there are more of these than you'd expect, and the engine's own linter will tell you about them at generation time).

---

---

## Why This Exists

FormaComposition isn't trying to automate composition — it's trying to make *composed* music generatable at a pace a composer's ear can keep up with, without losing the thing that makes composed music worth hearing: the sense that every note is where it is on purpose. A statistical model can't tell you *why* a note belongs where it is, only that it's statistically plausible. This engine always can, because the "why" is Piston's theory, written as code: **functional harmony** (a chord is a role within a key — tonic, subdominant, dominant — so a progression is tension and release, not a random walk), **voice leading** (independent lines resolve tendency tones in their expected direction and avoid parallel motion — the direct basis for the engine's chord-context statefulness), and **counterpoint** (species rules for how simultaneous lines relate — consonance, controlled dissonance, contrary motion).

The origin story, for anyone curious: it traces to a 2017 BBC interview where Brian Eno appeared to describe a sophisticated generative composition system. The reality turned out to be three simple JavaScript probability gates in Logic's Scripter plugin — elegant, but not what it seemed. The gap between that misreading and the real thing became the design target: a system that actually does what Eno's demo *appeared* to do.

---

## Architecture

### The hierarchy

| Level | Purpose |
|---|---|
| **Motif** | The atomic musical idea — intervals, rhythm, and a transform pool. Reusable across pieces via a shared library, or defined inline for a one-off. |
| **Piece identity** | Key, mode, tempo range — declared once at the top of the piece file. |
| **Section** | Local variation — harmonic progression, arc, density, groove, per-voice behavior. |

One JSON file per piece. A piece defines its motif inline, or several named motifs (`motifs`) that sections reference by name.

### Core modules

The engine lives in `forma/intervals/` (`core/` for orchestration and validation, `music/` for the voice generators).

| Module | Role |
|---|---|
| `generator.py` | Main engine — resolves motifs, applies transforms, writes MIDI via `mido`. Builds per-chord context for statefulness. |
| `schemas.py` | Pydantic v2 models — the single source of truth for what a piece file may contain. |
| `lint.py` | A dedicated linter that catches settings which are schema-legal but musically inert, and reports them on every generation run. |
| `motif_loader.py` | Resolves a motif reference — a named motif from the piece's `motifs`, or the piece's inline `motif`. |
| `melody.py` | Four behaviors: `lyrical`, `generative`, `sparse`, `develop` (`develop` is the one that reads the motif's pitch shape). |
| `harmony.py` | Roman-numeral progressions resolved into voiced MIDI chords; can develop its own independent motivic rhythm. |
| `bass.py` | Eight styles, including a `motif`-anchored style that re-derives from the piece's own motif at each chord root. |
| `counterpoint.py` | Species 1–5 and free counterpoint. Parallel fifths/octaves, hidden fifths/octaves and strong-beat dissonance are forbidden; voice crossing and parallel motion are penalized. |
| `percussion.py` | Five named drum patterns with groove templates and swing. |
| `rhythm_extract.py` | Turns a rhythm you play in your DAW (exported as MIDI) into a JSON pattern you can paste into a section. |
| `context.py` | Cross-voice and cross-section memory — melody's opening note is biased by where the previous section left off. |

### Motif development

A motif develops through 12 transforms: `original`, `inversion`, `retrograde`, `retrograde_inversion`, `augmentation`, `diminution`, `transpose_up`, `transpose_down`, `shuffle`, `expand`, `compress`, `sequence`. Script the order with a piece-level `transform_sequence` (one entry per section), or let the engine choose from the motif's `transform_pool`.

### Statefulness

Without it, each chord is generated in isolation — a melody has no idea a deceptive cadence (V→vi) or a modal color chord is about to arrive, and can sound caught off guard when it does. FormaComposition builds a context dictionary per chord (what's next, how many bars, what section) and threads it through the melody generator, so a phrase can lean toward the next chord's tones before it arrives. That's voice-leading gravity, implemented directly — not a post-processing smoothing pass. Full detail, including the deceptive-cadence test case, is in the [whitepaper](docs/FormaComposition_Whitepaper.md#4-statefulness-context-aware-generation).

### Validation and guardrails

Two layers, deliberately separate: structural validation (`schemas.py`) rejects a malformed piece before generation starts — missing fields, out-of-range values, typo'd enums. Consumption linting (`lint.py`) catches the harder problem — a piece that's perfectly valid but sets something the engine will never actually consult (a groove assigned to a rhythm source with no onset grid to shape it, a motif override on a voice whose species can't use it). Findings surface on every generation run, not buried in docs you have to remember to check.

---

## Documentation

- **[docs/FormaComposition_Whitepaper.md](docs/FormaComposition_Whitepaper.md)** — the full technical and compositional deep dive: theory, architecture, the motif transform pool, dynamics arcs, fugal techniques, and case studies from the actual catalog.
- **[docs/manuals/formacomposition_cheatsheet_v11.md](docs/manuals/formacomposition_cheatsheet_v11.md)** — the complete JSON schema reference, field by field, including every documented no-op and validation gotcha.

---

## Made With

Composed with FormaComposition, produced in Logic Pro with Arturia's V Collection and FX Collection, mixed with Valhalla reverbs. Released under [Connected Reasoning](https://github.com/ConnectedReasoning) — see the [whitepaper's production toolchain](docs/FormaComposition_Whitepaper.md#6-production-toolchain) for the full setup.

## Status

Actively developed, two-pieces-a-week release cadence. See [whitepaper §9](docs/FormaComposition_Whitepaper.md#9-current-state--practice) for what's recently shipped.

## Known Limits

- **Output is MIDI only.** Instruments, sound design and mixing happen in your DAW.
- **Sections aren't fully isolated.** A melody's opening note and its transform choice depend on what earlier sections left behind, so editing one section can change everything after it. To lock the transform order, set a piece-level `transform_sequence`.
- **The rules keep voice leading clean; they don't make a piece memorable.** That part is still your ear and your JSON choices.
- **The JSON schema is unstable.** Field names and defaults may change between commits. The engine rejects retired fields with a message (and a migration script, where one exists).

## Tests

```bash
pip install pytest
cd forma && python -m pytest
```

One test is marked `xfail` as a known regression: the melody "anchor-health" pull no longer reduces register concentration in its fugue scenario (see the reason string in `forma/tests/test_melody.py`).

## License

Code, documentation and example JSON files are released under the [MIT License](LICENSE). The recordings, the catalog and the Connected Reasoning name are not covered by it.
