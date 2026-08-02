# FormaComposition

**A rule-based generative music engine, grounded in classical harmonic theory — not machine learning — that turns JSON piece definitions into multi-voice MIDI.**

No training data, no statistical model. Every note the engine writes — which chord tone a melody leans toward, how a bass line approaches a chord change, how a counterpoint voice resolves a dissonance — traces to an explicit rule out of Walter Piston's *Harmony*. You define a motif, a key/mode/tempo, and a section-by-section form in one JSON file; the engine resolves it into melody, harmony, bass, counterpoint, and percussion that stay musically aware of each other, and renders it to a standard MIDI file for production in your DAW of choice.

Built and maintained by [Connected Reasoning](https://github.com/ConnectedReasoning).

---

## Quickstart

**Requirements:** Python 3.10+, [`pydantic`](https://pypi.org/project/pydantic/) v2, [`mido`](https://pypi.org/project/mido/)

```bash
git clone https://github.com/ConnectedReasoning/FormaComposition.git
cd FormaComposition
pip install pydantic mido
```

### Generate your first piece

Save this as `piece.json`:

```json
{
  "title": "Dorian Dawn",
  "key": "D",
  "mode": "dorian",
  "tempo": 72,
  "motif": {
    "name": "ascending_hope",
    "intervals": [2, 2, 1, 2],
    "rhythm": [1.0, 1.0, 0.5, 1.5]
  },
  "sections": [
    {
      "name": "opening",
      "bars": 8,
      "progression": ["i", "bVII", "IV", "i"],
      "rhythm": "motif",
      "arc": "fade_in"
    }
  ]
}
```

Then run it:

```bash
python main.py piece.json
```

That writes a standard `.mid` file with independently generated melody, harmony, and bass tracks — ready to import into Logic Pro, Ableton, or any DAW. Other useful flags:

```bash
python main.py piece.json --output ./output/name.mid   # explicit output path
python main.py p1.json p2.json --outdir ./album/        # batch, one file per piece
python main.py piece.json --info                        # inspect without generating
```

Before you write a real piece, skim the **[cheat sheet](docs/CHEATSHEET.md)** — it documents every field, every enum value, and every setting that's schema-legal but musically a no-op (there are more of these than you'd expect, and the engine's own linter will tell you about them at generation time).

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

One JSON file per piece. Shared motifs live in `compositions/motifs/` and are referenced by name; a piece can also define its own motif inline.

### Core modules

| Module | Role |
|---|---|
| `generator.py` | Main engine — resolves motifs, applies transforms, writes MIDI via `mido`. Builds per-chord context for statefulness. |
| `schemas.py` | Pydantic v2 models — the single source of truth for what a piece file may contain. |
| `lint.py` | A dedicated linter that catches settings which are schema-legal but musically inert, and reports them on every generation run. |
| `motif_loader.py` | Resolves a motif reference — inline pool name, embedded dict, or shared-library fallback. |
| `melody.py` | Four behavior modes: `lyrical`, `generative`, `sparse`, `develop`. |
| `harmony.py` | Roman-numeral progressions resolved into voiced MIDI chords; can develop its own independent motivic rhythm. |
| `bass.py` | Eight styles, including a `motif`-anchored style that re-derives from the piece's own motif at each chord root. |
| `counterpoint.py` | Free and strict first-species counterpoint — independent voices with their own register and dissonance treatment. |
| `percussion.py` | Five named drum patterns with groove templates and swing. |
| `rhythm_extract.py` | Imports hand-played MIDI loops from your DAW and converts them into reusable rhythm patterns. |
| `context.py` | Cross-voice and cross-section memory — melody's opening note is biased by where the previous section left off. |

### Statefulness

Without it, each chord is generated in isolation — a melody has no idea a deceptive cadence (V→vi) or a modal color chord is about to arrive, and can sound caught off guard when it does. FormaComposition builds a context dictionary per chord (what's next, how many bars, what section) and threads it through the melody generator, so a phrase can lean toward the next chord's tones before it arrives. That's voice-leading gravity, implemented directly — not a post-processing smoothing pass. Full detail, including the deceptive-cadence test case, is in the [whitepaper](docs/WHITEPAPER.md#4-statefulness-context-aware-generation).

### Validation and guardrails

Two layers, deliberately separate: structural validation (`schemas.py`) rejects a malformed piece before generation starts — missing fields, out-of-range values, typo'd enums. Consumption linting (`lint.py`) catches the harder problem — a piece that's perfectly valid but sets something the engine will never actually consult (a groove assigned to a rhythm source with no onset grid to shape it, a motif override on a voice whose species can't use it). Findings surface on every generation run, not buried in docs you have to remember to check.

---

## Documentation

- **[docs/WHITEPAPER.md](docs/WHITEPAPER.md)** — the full technical and compositional deep dive: theory, architecture, the motif transform pool, dynamics arcs, fugal techniques, and case studies from the actual catalog.
- **[docs/CHEATSHEET.md](docs/CHEATSHEET.md)** — the complete JSON schema reference, field by field, including every documented no-op and validation gotcha.

---

## Made With

Composed with FormaComposition, produced in Logic Pro with Arturia's V Collection and FX Collection, mixed with Valhalla reverbs. Released under [Connected Reasoning](https://github.com/ConnectedReasoning) — see the [whitepaper's production toolchain](docs/WHITEPAPER.md#6-production-toolchain) for the full setup.

## Status

Actively developed, two-pieces-a-week release cadence. See [docs/WHITEPAPER.md §9](docs/WHITEPAPER.md#9-current-state--practice) for what's recently shipped.

## License

This project is licensed under the [PolyForm Noncommercial License 1.0.0](https://polyformproject.org/licenses/noncommercial/1.0.0/).
