# FormaComposition: Live MIDI Integration Design Document

**Project:** FormaComposition  
**Author:** Manuel (Connected Reasoning) & Claude  
**Date:** March 31, 2026  
**Status:** Proposal / Future Work  

---

## 1. Inspiration: Thirty Years from Theory to Tools

### The Foundation: Walter Piston's *Harmony*

The real origin of FormaComposition is not a YouTube video. It's a textbook.

In the mid-1990s, a self-study of Walter Piston's *Harmony* planted the compositional vocabulary that would eventually become the engine's foundation: voice leading, harmonic progression, counterpoint, the structural logic that determines *why* certain notes follow others and *how* independent voices relate to each other. This wasn't generative music theory — it was classical compositional theory, the kind that explains Bach and Beethoven and everything built on their principles.

The knowledge was there. The tools were not.

In the 1990s, there was no accessible pipeline for turning compositional theory into realized music without either a room full of musicians or years of instrumental virtuosity. MIDI existed but was clunky. Software instruments were primitive. The gap between understanding harmony and hearing it rendered as music was enormous. The theory went into long-term storage — understood, internalized, but without an outlet.

### The Catalyst: Brian Eno's Probability Engine

Thirty years later, a BBC Click interview resurfaced the idea. In the 2017 segment titled *"Brian Eno: How To Make Original Ambient Music,"* Spencer Kelly watched Eno demonstrate a generative composition workflow in Logic Pro X using the **Scripter MIDI FX plugin** — a JavaScript environment that processes MIDI events in real-time.

At the time, the demonstration appeared to reveal something deep: a bespoke generative system, a personal compositional engine, the kind of tool a pioneer builds when commercial software doesn't go far enough. The scientific terminology Eno used — probability, stochastic processes — implied a sophistication that demanded investigation and, ultimately, a response.

That response became GenMuso, then GenMuso2, then FormaComposition.

### The Misunderstanding That Built Something Real

Returning to the video years later, the reality is more modest. Eno's setup consists of three custom JavaScript modules inside Logic's Scripter:

- **Chance of Playing** — a probability gate deciding whether each note fires
- **Random Transposer** — pitch shifting constrained to allowed notes in a scale
- **Random Repeater** — probabilistic repetition for rolls and density variation

This is a filter on existing material — not a generative compositional engine. There are no motif transforms, no harmonic progression awareness, no multi-voice architecture, no dynamics arcs. It's elegant and effective, but it's fundamentally a set of probability gates applied to drum patterns.

The YouTube comments section caught this too. Commenters from the algorave and live-coding communities — TidalCycles, SuperCollider, Max/MSP — pointed out that probability-based generative music was well-established territory by 2017. When the interviewer asked if anyone else was doing this, Eno said "not as far as I know." The ones who plant the seeds don't always recognize the orchard.

But the misunderstanding was productive. The imagined depth of Eno's system — the version that seemed to encode real compositional intelligence — became the design target. FormaComposition wasn't built to replicate what Eno actually had. It was built to be the thing Eno's demonstration *appeared* to be: a system where compositional theory — Piston's theory, studied thirty years prior — drives generative music with structural rigor, not just randomness.

### What Eno Did Contribute

The misreading of Eno's depth doesn't diminish what he genuinely demonstrated: the **feedback loop**. His workflow of starting the system, leaving the room, returning to adjust parameters, and listening for what works — composition as curation — remains the aspirational model. The creative act is not writing notes. It's tuning the system until it produces music the composer wants to live with.

That feedback loop — the tight connection between parameter adjustment and auditory result, where the system and the listener occupy the same moment — is what FormaComposition still lacks and what this design document proposes to build.

---

## 2. What FormaComposition Has Accomplished

FormaComposition is a Python-based generative MIDI engine with a companion Swift macOS application. It represents the mature evolution of earlier generative projects (GenMuso, GenMuso2) and is designed for producing ambient, new age, and structurally rich compositions for distribution under the artist name **Connected Reasoning**.

### Architecture

FormaComposition uses a **JSON-driven composition schema** organized in a four-level hierarchy:

| Level | Purpose |
|---|---|
| **Motif** | The atomic musical idea — a short melodic or rhythmic figure with defined pitches, durations, and velocities |
| **Theme** | A collection of motifs with assigned voices, harmonic context, and development rules |
| **Piece** | A sequence of themes organized into sections (verse, bridge, chorus, etc.) with dynamics arcs and temporal structure |
| **Arrangement** | The top-level container specifying tempo, key, time signature, and section ordering |

### Core Modules

- **`generator.py`** — The main engine. Reads a JSON composition, resolves motifs, applies transforms, and writes MIDI output via `mido`.
- **`motif_loader.py`** — Loads standalone motif files from `compositions/motifs/`, providing reusability across compositions. Backward-compatible with embedded motif dictionaries.
- **`percussion.py`** — Five named drum patterns rendered to MIDI channel 9 with groove templates, swing, and humanization.
- **`bass.py`** — Three bass behaviors (steady, melodic, walking) that respond to harmonic context.
- **`rhythm.py`** — Rhythm generation with harmony-rhythm independence and per-chord `chord_bars` arrays.

### Compositional Features

- **Bach-style motif transforms:** inversion, retrograde, retrograde inversion, augmentation, diminution
- **Dynamics arcs:** Named presets and custom `[position, intensity]` control point curves for shaping energy across a piece
- **Humanization profiles:** Velocity variation, timing drift, and articulation randomness to escape mechanical rigidity
- **Groove templates:** Swing ratios and micro-timing offsets applied per voice
- **Harmony-rhythm independence:** Chord changes and rhythmic patterns operate on separate clocks, creating natural-feeling phasing

### Swift macOS Application

The companion app follows the planzu-swift architecture (Models / Model Stores / ViewModels / Services / Views) and provides a GUI for composing and triggering generation. The outstanding task is wiring the Generate button to the Python engine — which is precisely the integration point this design document addresses.

### What Works

FormaComposition reliably produces multi-voice MIDI compositions that, when assigned to Arturia instruments in Logic Pro and layered with effects (Valhalla Shimmer, Valhalla Supermassive, Arturia Rev LX-24), yield distributable ambient and new age tracks. The JSON schema successfully separates musical intent from engine mechanics, allowing rapid iteration on compositions without code changes.

### What's Missing

The workflow today is:

```
Edit JSON → Run Python → Export MIDI file → Import into Logic → Assign instruments → Listen → Repeat
```

Every iteration requires a full round trip. The composer cannot hear the effect of a parameter change without re-running the engine, re-importing the file, and re-listening. This is functional but slow, and it fundamentally breaks the feedback loop that makes Eno's approach powerful. The system and the listener do not occupy the same moment.

---

## 3. The Aspiration: Closing the Feedback Loop

FormaComposition already surpasses Eno's Scripter setup in compositional depth — that was the unintended consequence of building toward the imagined version rather than the real one. What Eno's workflow *does* have that FormaComposition lacks is immediacy. He adjusts a parameter and hears the result in the same breath. That feedback loop — not the probability gates, not the JavaScript — is the thing worth taking.

The goal is to transform FormaComposition from a **batch MIDI generator** into a **live generative instrument** — one where the composer adjusts parameters in the Swift GUI and immediately hears the result through Logic Pro's instrument and effects chain.

### Current State vs. Target State

| Dimension | Current | Target |
|---|---|---|
| **Generation mode** | Batch (full piece rendered to file) | Streaming (MIDI events sent in real-time) |
| **Feedback latency** | Minutes (edit → generate → import → listen) | Milliseconds (adjust parameter → hear change) |
| **Iteration style** | Sequential (stop, change, restart) | Continuous (tweak while listening) |
| **Logic Pro role** | Post-production (receives finished MIDI) | Live instrument rack (receives live MIDI stream) |
| **Composer posture** | Editor at a desk | Listener in a room, returning to adjust |

### What This Enables

- **Real-time parameter tuning.** Adjust motif density, probability weights, transposition rules, dynamics curves, and hear the effect immediately through Logic's instruments and effects.
- **Extended generative sessions.** Let the engine run for hours, producing non-repeating material — the 2–4 hour ambient session goal — while the composer listens and intervenes only when something needs adjustment.
- **Live performance potential.** The Swift GUI becomes a performance interface. Shift the harmonic center, swap motif families, change bass behavior — all while the music plays.
- **Eno's "leave the room" workflow.** Start the engine, walk away, come back when something catches your ear or grates. Composition as curation.

### What This Does NOT Change

- **The JSON composition schema remains the source of truth.** Live mode streams from the same data structures; it doesn't replace the compositional vocabulary.
- **Motif transforms, dynamics arcs, and humanization continue to function identically.** The engine's musical intelligence is preserved.
- **Logic Pro remains the sound design environment.** Instrument assignment, effects chains, and mixing stay in the DAW where they belong. FormaComposition sends MIDI; Logic makes sound.

---

## 4. Path 1 Strategy: IAC MIDI Bus Integration

### Overview

macOS includes the **IAC Driver** (Inter-Application Communication Driver), a built-in virtual MIDI bus that allows applications to send MIDI data to each other without hardware. FormaComposition's Python engine will send MIDI events over the IAC bus in real-time. Logic Pro will receive those events on instrument tracks, exactly as if they were coming from a physical MIDI controller.

The Swift GUI controls the Python engine's parameters. The Python engine streams MIDI to Logic. Logic renders audio through its instrument and effects chain. The composer hears the result immediately.

```
┌─────────────────┐      Parameters       ┌─────────────────┐
│                  │ ───────────────────▶   │                  │
│   Swift GUI      │                        │  Python Engine   │
│   (macOS App)    │  ◀───────────────────  │  (generator.py)  │
│                  │      Status/State      │                  │
└─────────────────┘                        └────────┬─────────┘
                                                    │
                                               MIDI Events
                                              (via mido)
                                                    │
                                                    ▼
                                           ┌─────────────────┐
                                           │   IAC Driver     │
                                           │  (macOS Virtual  │
                                           │   MIDI Bus)      │
                                           └────────┬─────────┘
                                                    │
                                              Virtual MIDI
                                                    │
                                                    ▼
                                           ┌─────────────────┐
                                           │   Logic Pro      │
                                           │                  │
                                           │  - Instrument    │
                                           │    tracks        │
                                           │  - Arturia VIs   │
                                           │  - Effects chain │
                                           │  - Audio output  │
                                           └─────────────────┘
```

### 4.1 Enabling the IAC Driver

The IAC Driver is present on all Macs but disabled by default.

1. Open **Audio MIDI Setup** (Applications → Utilities)
2. Select **Window → Show MIDI Studio**
3. Double-click the **IAC Driver** icon
4. Check **"Device is online"**
5. Optionally rename the default port or add named ports (e.g., `FormaComp Melody`, `FormaComp Bass`, `FormaComp Drums`) for per-voice routing

Multiple IAC bus ports allow FormaComposition to route each voice to a separate Logic track, preserving the instrument assignment workflow that already exists.

### 4.2 Python Engine: Real-Time MIDI Streaming

The core change is in `generator.py`. Today, it builds a complete `mido.MidiFile` and writes it to disk. In live mode, it will instead open a `mido` output port connected to the IAC Driver and send MIDI messages in real-time.

#### Port Connection

```python
import mido

# List available outputs — IAC Driver will appear here
# e.g., 'IAC Driver Bus 1' or custom-named ports
print(mido.get_output_names())

# Open the IAC port
port = mido.open_output('IAC Driver Bus 1')
```

`mido` supports virtual MIDI ports on macOS natively via the `rtmidi` backend (installed as `python-rtmidi`). No additional drivers or middleware are required.

#### Streaming Loop

The engine needs a **real-time event scheduler** that replaces file-based tick timing with wall-clock timing:

```python
import time

def stream_events(events, port, bpm=120):
    """
    events: list of (delta_seconds, mido.Message) tuples,
            pre-computed from the composition with all transforms,
            dynamics, and humanization applied.
    """
    for delta, msg in events:
        if delta > 0:
            time.sleep(delta)
        port.send(msg)
```

In practice, `time.sleep()` has limited precision (~1ms on macOS). For tighter timing, a high-resolution timer or a dedicated scheduling thread is advisable. The `mido` library's own `mido.backends.rtmidi` backend provides low-latency message sending; the bottleneck is scheduling, not transmission.

#### Dual-Mode Generator

The generator should support both modes without forking the codebase:

```python
class GeneratorMode:
    FILE = "file"       # Current behavior: render full MIDI file
    STREAM = "stream"   # New behavior: real-time IAC output

def generate(composition, mode=GeneratorMode.FILE, port=None):
    events = build_events(composition)  # Existing logic, unchanged

    if mode == GeneratorMode.FILE:
        write_midi_file(events, output_path)
    elif mode == GeneratorMode.STREAM:
        stream_events(events, port)
```

The `build_events()` function is the existing composition pipeline — motif loading, transforms, dynamics arcs, humanization, percussion, bass — producing a flat list of timed MIDI events. The only change is what happens *after* the events are built.

#### Multi-Channel Routing

FormaComposition already assigns voices to MIDI channels (percussion on channel 9, etc.). When streaming to IAC, each channel maps to a Logic track:

| MIDI Channel | FormaComposition Voice | Logic Instrument |
|---|---|---|
| 1 | Melody | Arturia (e.g., Wurlitzer, Piano) |
| 2 | Counterpoint / Harmony | Arturia (e.g., Strings, Pad) |
| 3 | Bass | Arturia (e.g., Mini V, Bass) |
| 9 | Percussion | Arturia (e.g., Spark, LinnDrum) |

Logic receives all channels on a single IAC input and demultiplexes by channel number — standard MIDI behavior. Alternatively, multiple IAC bus ports (one per voice) can be used for cleaner routing, at the cost of more port management.

### 4.3 Swift GUI: Parameter Control Interface

The Swift app's role expands from "trigger generation and display results" to "control a running generative engine in real-time."

#### Communication: Swift ↔ Python

The Swift app and Python engine need a bidirectional communication channel. Recommended approach: **a local WebSocket or Unix domain socket**, with JSON messages.

```
Swift GUI  ──WebSocket──▶  Python Engine
           ◀──WebSocket──
```

**Swift → Python messages (commands):**

```json
{ "command": "start", "composition": "rebecca.json", "bpm": 90 }
{ "command": "stop" }
{ "command": "set_param", "param": "melody_density", "value": 0.6 }
{ "command": "set_param", "param": "bass_behavior", "value": "walking" }
{ "command": "set_param", "param": "motif_family", "value": "dawn" }
{ "command": "set_param", "param": "dynamics_arc", "value": "gentle_swell" }
{ "command": "swap_chord_progression", "progression": ["Am", "F", "C", "G"] }
```

**Python → Swift messages (status):**

```json
{ "status": "playing", "position": "section:verse bar:12", "bpm": 90 }
{ "status": "stopped" }
{ "event": "section_change", "section": "bridge" }
{ "event": "motif_triggered", "motif": "dawn_rising", "voice": "melody" }
```

#### Hot Parameters

Not every parameter can be changed mid-stream without disruption. The design should classify parameters by mutability:

| Parameter | Hot-Swappable? | Notes |
|---|---|---|
| Melody density / probability | Yes | Affects note generation on next beat |
| Bass behavior | Yes | Switches on next bar boundary |
| Dynamics intensity | Yes | Interpolates to new value over N beats |
| Motif family | Yes (bar boundary) | New motifs start at next phrase boundary |
| Chord progression | Conditional | Safe at section boundary; mid-section requires voice-leading logic |
| BPM / tempo | Conditional | Requires recalculating sleep deltas; apply at bar boundary |
| Key / scale | Conditional | Safe at section boundary; mid-section may produce dissonance |
| Time signature | No | Requires full restart |

### 4.4 Logic Pro Configuration

On the Logic side, setup is straightforward:

1. **Create instrument tracks** for each voice (melody, harmony, bass, percussion)
2. **Set each track's MIDI input** to the IAC Driver (or specific IAC bus port)
3. **Assign channel filters** so each track responds only to its designated MIDI channel
4. **Load Arturia instruments** and effects chains as usual
5. **Enable input monitoring** on each track so incoming MIDI triggers audio immediately
6. **Optionally arm tracks for recording** to capture the generated MIDI into Logic's timeline for further editing

Logic does not need to know or care that the MIDI is coming from a Python script. From its perspective, it's receiving MIDI input from an external controller — a workflow it's designed for.

### 4.5 The Streaming Engine: Architectural Considerations

#### Continuous Generation vs. Pre-Computed Streaming

Two sub-strategies exist:

**Option A — Pre-compute, then stream.** Generate the full event list (as today), then play it back in real-time over IAC. Parameter changes trigger a re-generation of upcoming events while already-scheduled events continue playing. Simpler to implement; may introduce brief gaps during re-computation.

**Option B — Generate on the fly.** The engine runs a real-time loop, deciding what to play on each beat/bar based on current parameters. More responsive to parameter changes; requires rethinking the generator from batch to incremental. This is closer to what Eno's Scripter does.

**Recommended first step:** Option A. It preserves the existing generator architecture entirely. The streaming layer is purely a playback mechanism — a MIDI player that sends events to IAC instead of writing to a file. Parameter changes queue a partial re-generation of future events.

**Future evolution:** Option B, where the engine generates events incrementally, bar by bar, consulting current parameter state for each bar. This is the full "live instrument" mode but represents a more significant refactor.

#### Threading Model

The streaming engine requires at least two threads:

1. **Playback thread** — Sends MIDI events at precise wall-clock intervals. Must not be blocked by parameter changes or re-generation.
2. **Control thread** — Listens for WebSocket messages from the Swift GUI, updates shared parameter state, and triggers re-generation when needed.

A thread-safe parameter store (e.g., Python `queue.Queue` or `threading.Lock`-protected dict) mediates between the two.

#### Timing Precision

For ambient music at moderate tempos (60–120 BPM), `time.sleep()` precision (~1ms) is adequate. Sixteenth notes at 120 BPM are 125ms apart — 1ms of jitter is below perceptual threshold, especially with humanization already adding intentional timing drift.

For tighter timing requirements (e.g., percussion patterns with swing), a busy-wait loop with `time.perf_counter()` can achieve sub-millisecond precision at the cost of CPU usage.

### 4.6 Implementation Phases

#### Phase 1 — Proof of Concept (Minimal Viable Stream)

- Enable IAC Driver on Mac Studio
- Modify `generator.py` to open an IAC output port via `mido`
- Add a `stream_events()` function that plays a pre-computed event list in real-time
- Test with a known composition: generate events, stream to Logic, confirm audio output
- **Success criteria:** Hear FormaComposition output through Logic instruments in real-time, no file export required

#### Phase 2 — Swift GUI Integration

- Implement WebSocket server in the Python engine
- Wire the Swift app's Generate button to send `start` command over WebSocket
- Display playback status (current section, bar number) in the Swift GUI
- **Success criteria:** Click Generate in Swift app, hear music in Logic

#### Phase 3 — Hot Parameter Control

- Add parameter sliders/controls to the Swift GUI (density, bass behavior, dynamics)
- Implement parameter message handling in the Python engine
- Support mid-stream parameter changes (Option A: re-generate future events)
- **Success criteria:** Move a slider in the GUI, hear the change in Logic within one bar

#### Phase 4 — Incremental Generation (Option B)

- Refactor generator to produce events bar-by-bar instead of pre-computing the full piece
- Each bar consults current parameter state before generating
- Support indefinite-length sessions (no pre-determined piece length)
- **Success criteria:** Engine runs continuously for 30+ minutes with parameter changes producing musically coherent transitions

#### Phase 5 — Record and Capture

- Logic records the incoming MIDI stream to its timeline
- Swift GUI can mark "good sections" with timestamps
- Export workflow: stream → record in Logic → select best sections → bounce to audio → distribute
- **Success criteria:** Complete a distributable track using only the live workflow

### 4.7 Dependencies and Requirements

| Dependency | Status | Notes |
|---|---|---|
| `mido` (Python) | Already installed | Core MIDI library |
| `python-rtmidi` | May need install | Backend for `mido` on macOS; enables IAC access |
| IAC Driver | macOS built-in | Needs to be enabled in Audio MIDI Setup |
| WebSocket library (Python) | Needs install | `websockets` or `asyncio`-based server |
| WebSocket client (Swift) | Needs implementation | `URLSessionWebSocketTask` (built into Foundation) |
| Logic Pro | Already installed | No changes needed beyond track setup |
| Mac Studio M1 (32GB) | Available | Primary development and performance machine |

### 4.8 Risks and Mitigations

| Risk | Impact | Mitigation |
|---|---|---|
| `python-rtmidi` doesn't see IAC ports | Blocks Phase 1 | Test immediately; fallback to `pygame.midi` or direct CoreMIDI via `ctypes` |
| Timing jitter causes audible artifacts | Degrades musical quality | Humanization already masks small jitter; use `time.perf_counter()` busy-wait for percussion |
| Parameter changes cause musical discontinuities | Breaks coherence | Apply changes at bar/section boundaries; crossfade dynamics values |
| WebSocket latency between Swift and Python | Sluggish GUI response | Unix domain socket instead of TCP; or shared memory for hot parameters |
| Long sessions exhaust memory | Crashes after hours | Circular buffer for event history; generate incrementally (Phase 4) |
| Logic track configuration complexity | Friction for each session | Save a Logic template with IAC routing pre-configured |

---

## Summary

FormaComposition exists at the intersection of two moments separated by three decades: the study of Walter Piston's *Harmony* in the 1990s, which provided the compositional vocabulary, and the emergence of accessible tools — Python, `mido`, Logic Pro, Arturia's instrument libraries — that finally made it possible to express that vocabulary as realized music.

Brian Eno's BBC Click demonstration was the catalyst that connected the two, even if the connection was built on a productive misunderstanding. The imagined depth of Eno's system became the design target; FormaComposition overshot it by encoding actual compositional theory — motif development, harmonic structure, voice independence, dynamics as narrative — into a generative engine. What Eno genuinely contributed was the workflow model: composition as curation, the tight feedback loop between system and listener.

The IAC Driver integration closes the last gap. The Python engine gains a new output mode (stream instead of file). The Swift GUI gains real-time parameter controls. Logic Pro does what it already does — render MIDI through world-class instruments and effects — but now it receives that MIDI live.

Planck introduced quantization as a mathematical trick. Einstein gave it physical reality but rejected where it led. Bohr embraced it, extended it, and built the framework. FormaComposition follows the same arc: Eno planted the seed of automated composition, then stopped at probability gates. FormaComposition embraces the idea, extends it with classical compositional rigor, and builds the framework he never did.

The system proposes; the composer disposes. Thirty years in the making.
