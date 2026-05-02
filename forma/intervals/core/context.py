"""
context.py — Cross-voice and cross-section compositional memory.

Provides SectionContext (shared state *within* a section, updated as each
voice is generated) and PieceContext (shared state *across* sections,
carrying a summary of what each previous section produced).

These objects are the conductor layer that lets FormaComposition move from
"good parts stacked together" to "voices that listen to each other."

Drop this file into:  forma/intervals/core/context.py
"""

from __future__ import annotations

import random as _random_module
from dataclasses import dataclass, field
from typing import Optional


# ═══════════════════════════════════════════════════════════════════════
# Voice Snapshot — lightweight summary of what a single voice produced
# ═══════════════════════════════════════════════════════════════════════

@dataclass
class VoiceSnapshot:
    """
    Captures the musically-relevant output of a single voice after it
    finishes generating.  Downstream voices read these to make informed
    decisions (contrary motion, register avoidance, rhythmic locking).

    All fields are optional — a voice only fills in what it can.
    """

    # ── Pitch / register ────────────────────────────────────────────
    last_pitch: Optional[int] = None
    """MIDI note number of the last sounding note (not rest)."""

    pitch_center: Optional[float] = None
    """Mean MIDI pitch across all sounding notes — the voice's
    registral 'home' for this section."""

    pitch_low: Optional[int] = None
    """Lowest MIDI note produced."""

    pitch_high: Optional[int] = None
    """Highest MIDI note produced."""

    # ── Contour ─────────────────────────────────────────────────────
    ending_contour: Optional[str] = None
    """Direction the voice was heading at the end of the section.
    One of: 'ascending', 'descending', 'static', 'peaked', 'troughed'.

    Computed from the last 3-4 sounding notes:
      - ascending:   each note >= previous
      - descending:  each note <= previous
      - static:      all within 2 semitones
      - peaked:      went up then down (arch)
      - troughed:    went down then up (valley)
    """

    # ── Rhythm / density ────────────────────────────────────────────
    achieved_density: Optional[float] = None
    """Fraction of available grid slots that received a note (0.0–1.0).
    This is *actual* density — what came out of the generator after
    density gates, groove filtering, and humanization — not the
    requested density string."""

    avg_note_duration_beats: Optional[float] = None
    """Mean note duration in beats.  Short = active texture,
    long = sustained/pad texture."""

    rhythmic_profile: Optional[str] = None
    """Coarse description of rhythmic character.
    One of: 'sustained', 'steady', 'syncopated', 'sparse'.

    Heuristic:
      - sustained:  avg duration > 2 beats, density < 0.3
      - steady:     notes roughly evenly spaced, density 0.3-0.7
      - syncopated: significant off-beat emphasis
      - sparse:     density < 0.2 regardless of duration
    """

    # ── Motif / transform ───────────────────────────────────────────
    last_transform: Optional[str] = None
    """Name of the last motif transform applied (e.g. 'retrograde',
    'inversion').  Used by PieceContext to track transform history
    and prevent undirected repetition."""

    # ── Harmony ─────────────────────────────────────────────────────
    last_chord_degree: Optional[str] = None
    """Roman numeral of the last chord in the section (e.g. 'V', 'iv').
    Useful for next-section decisions about harmonic continuity."""

    last_scale_degree: Optional[int] = None
    """Scale degree (1-7) of last_pitch relative to the key.
    More useful than raw MIDI note for melodic continuation logic."""


# ═══════════════════════════════════════════════════════════════════════
# Section Context — the scratchpad *within* a single section
# ═══════════════════════════════════════════════════════════════════════

@dataclass
class SectionContext:
    """
    Accumulates voice snapshots as each voice in a section is generated.
    Passed to each voice's generation function so downstream voices can
    read what upstream voices produced.

    Voices are already processed in JSON order (this was set up for
    rhythm locking).  SectionContext formalizes that dependency:

        bass generates  →  writes snapshot  →
        melody reads bass snapshot  →  writes its own  →
        counterpoint reads both  →  writes its own  →
        ...

    Usage in generate_section():
        ctx = SectionContext(section_name=section["name"], ...)
        bass_notes = generate_bass(..., ctx=ctx)
        ctx.add_voice("bass", compute_snapshot(bass_notes, ...))
        melody_notes = generate_melody(..., ctx=ctx)
        ctx.add_voice("melody", compute_snapshot(melody_notes, ...))
    """

    section_name: str = ""
    """Name from the JSON section definition."""

    section_index: int = 0
    """Zero-based position of this section in the piece."""

    total_sections: int = 1
    """Total number of sections in the piece.  Lets voices know where
    they are in the large-scale form (e.g. "we're in the last quarter")."""

    arc: str = "swell"
    """The section's declared arc (swell, build, fade, etc.)."""

    density: str = "medium"
    """The section's declared density."""

    key: str = "C"
    """Current key."""

    mode: str = "ionian"
    """Current mode."""

    # ── Per-voice snapshots (accumulated during generation) ─────────
    voices: dict[str, VoiceSnapshot] = field(default_factory=dict)
    """Map of voice_name → VoiceSnapshot, built up as voices generate."""

    def add_voice(self, name: str, snapshot: VoiceSnapshot) -> None:
        """Register a voice's output.  Call after each voice generates."""
        self.voices[name] = snapshot

    def get_voice(self, name: str) -> Optional[VoiceSnapshot]:
        """Read a previously-generated voice's snapshot.  Returns None
        if that voice hasn't generated yet (or doesn't exist)."""
        return self.voices.get(name)

    # ── Convenience queries ─────────────────────────────────────────

    @property
    def bass(self) -> Optional[VoiceSnapshot]:
        """Shortcut for the bass voice snapshot."""
        return self.voices.get("bass")

    @property
    def melody(self) -> Optional[VoiceSnapshot]:
        """Shortcut for the melody voice snapshot."""
        return self.voices.get("melody")

    @property
    def form_position(self) -> float:
        """Where we are in the piece as a 0.0–1.0 fraction.
        0.0 = first section, 1.0 = last section."""
        if self.total_sections <= 1:
            return 0.0
        return self.section_index / (self.total_sections - 1)


# ═══════════════════════════════════════════════════════════════════════
# Section Summary — frozen snapshot of a completed section
# ═══════════════════════════════════════════════════════════════════════

@dataclass
class SectionSummary:
    """
    Immutable record of a completed section.  Stored in PieceContext
    so future sections can reference what came before.

    Created from a SectionContext after all voices in that section
    have finished generating.
    """

    section_name: str
    section_index: int
    arc: str
    density: str
    key: str
    mode: str
    voices: dict[str, VoiceSnapshot] = field(default_factory=dict)

    @classmethod
    def from_section_context(cls, ctx: SectionContext) -> SectionSummary:
        """Freeze a SectionContext into an immutable summary."""
        return cls(
            section_name=ctx.section_name,
            section_index=ctx.section_index,
            arc=ctx.arc,
            density=ctx.density,
            key=ctx.key,
            mode=ctx.mode,
            voices=dict(ctx.voices),  # shallow copy of the dict
        )


# ═══════════════════════════════════════════════════════════════════════
# Piece Context — memory across sections
# ═══════════════════════════════════════════════════════════════════════

@dataclass
class PieceContext:
    """
    Persists across the entire piece generation.  Each time a section
    completes, its SectionSummary is appended here.  The next section's
    SectionContext is then initialized with awareness of what came before.

    Also tracks motif transform history to enable directed development.

    Usage in generate_piece():
        piece_ctx = PieceContext(total_sections=len(sections))

        for i, section in enumerate(sections):
            sec_ctx = piece_ctx.make_section_context(section, i)
            # ... generate all voices using sec_ctx ...
            piece_ctx.complete_section(sec_ctx)
    """

    total_sections: int = 1
    """Total number of sections in the piece."""

    key: str = "C"
    """Piece-level key (from theme)."""

    mode: str = "ionian"
    """Piece-level mode (from theme)."""

    # ── Section history ─────────────────────────────────────────────
    completed_sections: list[SectionSummary] = field(default_factory=list)
    """Ordered list of completed section summaries."""

    # ── Transform history (for directed motif development) ──────────
    transform_history: list[str] = field(default_factory=list)
    """Ordered list of transforms applied across all sections.
    Used to weight future transform selection and prevent repetition."""

    # ── Seeded RNG instance (never use the global random module) ────
    seed: int = 42
    """Base seed for this piece's PieceContext RNG."""

    def __post_init__(self) -> None:
        # Instance-based RNG: isolated from global random state.
        object.__setattr__(self, "_rng", _random_module.Random(self.seed))

    def complete_section(self, ctx: SectionContext) -> None:
        """Freeze a SectionContext and store it.  Also extracts any
        transform info from the melody voice into transform_history."""
        summary = SectionSummary.from_section_context(ctx)
        self.completed_sections.append(summary)

        # Track motif transforms from any voice that reported one
        for voice_snap in ctx.voices.values():
            if voice_snap.last_transform:
                self.transform_history.append(voice_snap.last_transform)

    def make_section_context(
        self,
        section: dict,
        section_index: int,
    ) -> SectionContext:
        """Create a SectionContext for the next section, pre-loaded
        with piece-level info."""
        return SectionContext(
            section_name=section.get("name", f"section_{section_index}"),
            section_index=section_index,
            total_sections=self.total_sections,
            arc=section.get("arc", "swell"),
            density=section.get("density", "medium"),
            key=self.key,
            mode=self.mode,
        )

    # ── Query helpers ───────────────────────────────────────────────

    @property
    def previous_section(self) -> Optional[SectionSummary]:
        """The most recently completed section, or None."""
        return self.completed_sections[-1] if self.completed_sections else None

    @property
    def previous_melody(self) -> Optional[VoiceSnapshot]:
        """Melody snapshot from the previous section."""
        prev = self.previous_section
        return prev.voices.get("melody") if prev else None

    @property
    def previous_bass(self) -> Optional[VoiceSnapshot]:
        """Bass snapshot from the previous section."""
        prev = self.previous_section
        return prev.voices.get("bass") if prev else None

    def transforms_used(self) -> dict[str, int]:
        """Count of each transform used so far across all sections."""
        counts: dict[str, int] = {}
        for t in self.transform_history:
            counts[t] = counts.get(t, 0) + 1
        return counts

    def suggest_transform(
        self,
        available: list[str],
        transform_sequence: Optional[list[str]] = None,
        section_index: int = 0,
    ) -> str:
        """
        Pick the next motif transform, respecting either:

        1. An explicit transform_sequence from the piece JSON (if provided)
        2. Weighted random selection that penalizes recently-used transforms

        Args:
            available:          The motif's transform_pool
            transform_sequence: Optional explicit ordering from piece JSON
            section_index:      Current section index

        Returns:
            Name of the selected transform
        """
        # Explicit plan takes priority — wraps if shorter than section count
        if transform_sequence:
            requested = transform_sequence[section_index % len(transform_sequence)]
            if requested in available or requested == "original":
                return requested

        # Weighted random: penalize recent usage
        # Uses self._rng (instance-based) — never the global random module.
        counts = self.transforms_used()

        weights = []
        for t in available:
            use_count = counts.get(t, 0)
            # Each prior use halves the weight
            w = 1.0 / (2 ** use_count)
            # Extra penalty if this was the most recent transform
            if self.transform_history and self.transform_history[-1] == t:
                w *= 0.25
            weights.append(w)

        # Normalize
        total = sum(weights)
        if total == 0:
            return self._rng.choice(available)

        weights = [w / total for w in weights]

        # Weighted selection
        r = self._rng.random()
        cumulative = 0.0
        for t, w in zip(available, weights):
            cumulative += w
            if r <= cumulative:
                return t

        return available[-1]  # fallback


# ═══════════════════════════════════════════════════════════════════════
# Snapshot computation helpers
# ═══════════════════════════════════════════════════════════════════════

def compute_contour(pitches: list[int]) -> str:
    """
    Determine the ending contour direction from the last few pitches.

    Args:
        pitches: List of MIDI note numbers (sounding notes only, no rests)

    Returns:
        One of: 'ascending', 'descending', 'static', 'peaked', 'troughed'
    """
    if len(pitches) < 2:
        return "static"

    tail = pitches[-4:] if len(pitches) >= 4 else pitches[-3:]

    if max(tail) - min(tail) <= 2:
        return "static"

    # Check for arch (peaked) or valley (troughed)
    if len(tail) >= 3:
        max_idx = tail.index(max(tail))
        min_idx = tail.index(min(tail))

        if 0 < max_idx < len(tail) - 1:
            return "peaked"
        if 0 < min_idx < len(tail) - 1:
            return "troughed"

    # Monotonic check
    diffs = [tail[i + 1] - tail[i] for i in range(len(tail) - 1)]
    if all(d >= 0 for d in diffs):
        return "ascending"
    if all(d <= 0 for d in diffs):
        return "descending"

    # Mixed — use net direction
    net = tail[-1] - tail[0]
    if net > 0:
        return "ascending"
    elif net < 0:
        return "descending"
    return "static"


def compute_rhythmic_profile(
    note_count: int,
    total_beats: float,
    avg_duration: float,
    density: float,
) -> str:
    """
    Classify the rhythmic character of a voice's output.

    Returns one of: 'sustained', 'steady', 'syncopated', 'sparse'
    """
    if density < 0.2:
        return "sparse"
    if avg_duration > 2.0 and density < 0.3:
        return "sustained"
    # TODO: syncopation detection requires beat-position analysis;
    # for now, classify everything else as 'steady'
    return "steady"


def compute_voice_snapshot(
    pitches: list[int],
    durations: list[float],
    total_beats: float,
    total_slots: int,
    last_transform: Optional[str] = None,
    last_chord_degree: Optional[str] = None,
    key: Optional[str] = None,
    mode: Optional[str] = None,
) -> VoiceSnapshot:
    """
    Build a VoiceSnapshot from raw note data.

    Args:
        pitches:      MIDI note numbers of sounding notes (no rests)
        durations:    Duration in beats for each sounding note
        total_beats:  Total beats in the section
        total_slots:  Total available grid slots
        last_transform:    Name of last motif transform applied
        last_chord_degree: Roman numeral of last chord

    Returns:
        A populated VoiceSnapshot
    """
    if not pitches:
        return VoiceSnapshot(
            last_transform=last_transform,
            last_chord_degree=last_chord_degree,
        )

    avg_dur = sum(durations) / len(durations) if durations else 0.0
    density = len(pitches) / total_slots if total_slots > 0 else 0.0

    snap = VoiceSnapshot(
        last_pitch=pitches[-1],
        pitch_center=sum(pitches) / len(pitches),
        pitch_low=min(pitches),
        pitch_high=max(pitches),
        ending_contour=compute_contour(pitches),
        achieved_density=density,
        avg_note_duration_beats=avg_dur,
        rhythmic_profile=compute_rhythmic_profile(
            len(pitches), total_beats, avg_dur, density
        ),
        last_transform=last_transform,
        last_chord_degree=last_chord_degree,
    )

    # Compute scale degree of last pitch if key is provided
    if key and pitches:
        NOTE_TO_PC = {
            "C": 0, "C#": 1, "Db": 1, "D": 2, "D#": 3, "Eb": 3,
            "E": 4, "F": 5, "F#": 6, "Gb": 6, "G": 7, "G#": 8,
            "Ab": 8, "A": 9, "A#": 10, "Bb": 10, "B": 11,
        }

        # Mode intervals (semitones from root for each scale degree)
        MODE_INTERVALS = {
            "ionian":     [0, 2, 4, 5, 7, 9, 11],
            "dorian":     [0, 2, 3, 5, 7, 9, 10],
            "phrygian":   [0, 1, 3, 5, 7, 8, 10],
            "lydian":     [0, 2, 4, 6, 7, 9, 11],
            "mixolydian": [0, 2, 4, 5, 7, 9, 10],
            "aeolian":    [0, 2, 3, 5, 7, 8, 10],
            "locrian":    [0, 1, 3, 5, 6, 8, 10],
        }

        root_pc = NOTE_TO_PC.get(key, 0)
        intervals = MODE_INTERVALS.get(mode or "ionian", MODE_INTERVALS["ionian"])
        pitch_pc = pitches[-1] % 12
        relative_pc = (pitch_pc - root_pc) % 12

        # Find closest scale degree
        best_degree = 1
        best_dist = 12
        for i, interval in enumerate(intervals):
            dist = min(abs(relative_pc - interval), 12 - abs(relative_pc - interval))
            if dist < best_dist:
                best_dist = dist
                best_degree = i + 1  # 1-indexed

        snap.last_scale_degree = best_degree

    return snap


# ═══════════════════════════════════════════════════════════════════════
# Quick test / demo
# ═══════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    print("=== context.py demo ===\n")

    # Simulate a 4-section piece
    piece_ctx = PieceContext(total_sections=4, key="D", mode="dorian")

    # Simulate section 0
    section_0 = {"name": "intro", "arc": "build", "density": "sparse",
                 "progression": ["i", "iv"]}
    sec_ctx = piece_ctx.make_section_context(section_0, 0)

    # Bass generates first
    bass_snap = compute_voice_snapshot(
        pitches=[38, 38, 45, 38],  # D2, D2, A2, D2
        durations=[4.0, 4.0, 4.0, 4.0],
        total_beats=16.0,
        total_slots=16,
        last_chord_degree="iv",
        key="D", mode="dorian",
    )
    sec_ctx.add_voice("bass", bass_snap)
    print(f"Bass: last_pitch={bass_snap.last_pitch}, contour={bass_snap.ending_contour}, "
          f"density={bass_snap.achieved_density:.2f}, profile={bass_snap.rhythmic_profile}")

    # Melody generates second, can read bass
    print(f"\nMelody can see bass: {sec_ctx.bass is not None}")
    print(f"  Bass ending contour: {sec_ctx.bass.ending_contour}")
    print(f"  Bass pitch center:   {sec_ctx.bass.pitch_center:.1f}")

    melody_snap = compute_voice_snapshot(
        pitches=[62, 64, 66, 69, 67, 66, 64, 62],
        durations=[1.0, 1.0, 2.0, 1.0, 1.0, 2.0, 1.0, 2.0],
        total_beats=16.0,
        total_slots=32,
        last_transform="original",
        last_chord_degree="iv",
        key="D", mode="dorian",
    )
    sec_ctx.add_voice("melody", melody_snap)

    # Complete section 0
    piece_ctx.complete_section(sec_ctx)
    print(f"\nSection 0 complete. Transform history: {piece_ctx.transform_history}")
    print(f"Form position was: {sec_ctx.form_position:.2f}")

    # Section 1 can now see what section 0 did
    section_1 = {"name": "verse", "arc": "swell", "density": "medium",
                 "progression": ["i", "VII", "iv", "v"]}
    sec_ctx_1 = piece_ctx.make_section_context(section_1, 1)

    print(f"\nSection 1 starts. Previous melody ended on pitch "
          f"{piece_ctx.previous_melody.last_pitch}, "
          f"contour was '{piece_ctx.previous_melody.ending_contour}', "
          f"scale degree {piece_ctx.previous_melody.last_scale_degree}")

    # Test transform suggestion
    pool = ["inversion", "retrograde", "augmentation", "diminution", "transpose_up"]
    for i in range(4):
        t = piece_ctx.suggest_transform(pool, section_index=i)
        piece_ctx.transform_history.append(t)
        print(f"  Section {i} suggested transform: {t}")

    print(f"\nFinal transform history: {piece_ctx.transform_history}")
    print(f"Transform counts: {piece_ctx.transforms_used()}")

    # Test explicit transform sequence
    piece_ctx_2 = PieceContext(total_sections=5)
    explicit = ["original", "inversion", "augmentation", "retrograde", "original"]
    print(f"\nExplicit transform sequence: {explicit}")
    for i in range(5):
        t = piece_ctx_2.suggest_transform(pool, transform_sequence=explicit, section_index=i)
        print(f"  Section {i}: {t}")
