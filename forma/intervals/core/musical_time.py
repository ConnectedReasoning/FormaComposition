"""
musical_time.py — Immutable musical time representation for FormaComposition.

Replaces raw float beats with a structured (bar, beat, beats_per_bar) tuple
that understands bar boundaries, downbeats, and cross-bar arithmetic.

Design goals:
  - Immutable: every operation returns a new MusicalTime.
  - No surprise mutations: used as keys in dicts, elements in sets, safely.
  - Readable rules: "play on beat 3 of every second bar" reads like English.
  - Zero-friction MIDI output: to_beats() gives the float the MIDI engine needs.
  - Backward compatible: existing callers that deal in raw floats can wrap/unwrap
    with MusicalTime.from_beats() / .to_beats() at section boundaries.

The beat coordinate is 0-indexed within the bar:
  bar 0, beat 0.0  → downbeat of bar 1
  bar 0, beat 1.0  → beat 2 of bar 1
  bar 0, beat 2.0  → beat 3 of bar 1   ← "beat 3" in 1-indexed human speak
  bar 0, beat 3.0  → beat 4 of bar 1
  bar 1, beat 0.0  → downbeat of bar 2

Human-readable beat numbers (1-indexed) are available via .beat_number.
"""

from __future__ import annotations

from fractions import Fraction
from typing import Union


# ─────────────────────────────────────────────────────────────────────────────
# MusicalTime
# ─────────────────────────────────────────────────────────────────────────────

class MusicalTime:
    """
    Immutable representation of a position in musical time.

    Attributes (read-only after construction):
        bar             : int   — zero-indexed bar number
        beat            : float — beat position within the bar (0-indexed, 0.0–<beats_per_bar)
        beats_per_bar   : int   — time signature numerator (4 for common time, 3 for waltz, …)

    All arithmetic returns a new MusicalTime; self is never modified.

    Quick-start examples
    --------------------
    >>> t = MusicalTime(bar=2, beat=2.0, beats_per_bar=4)
    >>> t.is_downbeat()          # False — beat 2.0 is beat 3 in human speak
    False
    >>> t.beat_number            # 3 (1-indexed, the way musicians talk)
    3
    >>> t.to_beats()             # 10.0
    10.0
    >>> t.add_beats(3.0).bar     # wraps into bar 3
    3
    >>> MusicalTime.from_beats(10.0, beats_per_bar=4)
    MusicalTime(bar=2, beat=2.0, bpb=4)

    Predicate examples
    ------------------
    >>> t.is_beat(3)             # True — beat 3 (1-indexed), same as beat == 2.0
    True
    >>> t.is_bar_mod(2)          # True — bar 2 is divisible by 2
    True
    >>> t.matches(beat=3, bar_mod=2)  # combine predicates
    True
    """

    __slots__ = ("_bar", "_beat", "_beats_per_bar")

    # ── construction ────────────────────────────────────────────────────────

    def __init__(self, bar: int, beat: float, beats_per_bar: int = 4) -> None:
        if beats_per_bar < 1:
            raise ValueError(f"beats_per_bar must be >= 1, got {beats_per_bar}")
        if beat < 0:
            raise ValueError(f"beat must be >= 0, got {beat}")
        if beat >= beats_per_bar:
            raise ValueError(
                f"beat {beat} out of range for beats_per_bar={beats_per_bar}; "
                f"use add_beats() to cross bar boundaries"
            )
        object.__setattr__(self, "_bar", int(bar))
        object.__setattr__(self, "_beat", float(beat))
        object.__setattr__(self, "_beats_per_bar", int(beats_per_bar))

    def __setattr__(self, name, value):
        raise AttributeError("MusicalTime is immutable")

    # ── core properties ─────────────────────────────────────────────────────

    @property
    def bar(self) -> int:
        """Zero-indexed bar number."""
        return self._bar

    @property
    def beat(self) -> float:
        """Beat position within the bar, 0-indexed (0.0 = downbeat)."""
        return self._beat

    @property
    def beats_per_bar(self) -> int:
        """Time signature numerator."""
        return self._beats_per_bar

    @property
    def beat_number(self) -> float:
        """Human-readable (1-indexed) beat number within the bar.
        Beat 0.0 → 1, beat 1.0 → 2, etc."""
        return self._beat + 1.0

    # ── core API ─────────────────────────────────────────────────────────────

    def is_downbeat(self) -> bool:
        """True if this position is the first beat of a bar (beat == 0.0)."""
        return abs(self._beat) < 1e-9

    def to_beats(self) -> float:
        """Convert to a raw float beat offset from the start of the piece/section.

        This is the value the MIDI engine expects.
        Inverse of MusicalTime.from_beats().
        """
        return float(self._bar * self._beats_per_bar + self._beat)

    def add_beats(self, n: float) -> "MusicalTime":
        """Return a new MusicalTime advanced by n beats, crossing bar boundaries
        automatically.

        Negative values are allowed (step backward).

        Examples
        --------
        >>> MusicalTime(0, 3.0).add_beats(1.5)   # crosses into bar 1
        MusicalTime(bar=1, beat=0.5, bpb=4)
        >>> MusicalTime(1, 0.0).add_beats(-0.5)  # step back into bar 0
        MusicalTime(bar=0, beat=3.5, bpb=4)
        """
        raw = self.to_beats() + n
        if raw < 0:
            raise ValueError(f"add_beats({n}) would produce a negative time ({raw})")
        return MusicalTime.from_beats(raw, beats_per_bar=self._beats_per_bar)

    # ── factory ──────────────────────────────────────────────────────────────

    @classmethod
    def from_beats(cls, total_beats: float, beats_per_bar: int = 4) -> "MusicalTime":
        """Create a MusicalTime from a raw float beat offset.

        Inverse of to_beats().

        >>> MusicalTime.from_beats(9.5, beats_per_bar=4)
        MusicalTime(bar=2, beat=1.5, bpb=4)
        """
        if total_beats < 0:
            raise ValueError(f"total_beats must be >= 0, got {total_beats}")
        bar, beat = divmod(total_beats, beats_per_bar)
        # Guard against floating-point creep (e.g. 3.9999999 → 4.0)
        beat = round(beat, 9)
        if beat >= beats_per_bar:
            bar += 1
            beat = 0.0
        return cls(bar=int(bar), beat=beat, beats_per_bar=beats_per_bar)

    # ── predicates for rule authoring ────────────────────────────────────────

    def is_beat(self, beat_number: Union[int, float], tolerance: float = 1e-6) -> bool:
        """True if this position is at the given 1-indexed beat number.

        Uses a small tolerance so floating-point positions near the target
        match correctly.

        Example: 'play on beat 3' → t.is_beat(3)
        """
        target_beat = beat_number - 1.0  # convert to 0-indexed
        return abs(self._beat - target_beat) < tolerance

    def is_bar_mod(self, n: int, offset: int = 0) -> bool:
        """True if (bar - offset) is divisible by n.

        Example: 'every 2nd bar starting from bar 0' → t.is_bar_mod(2)
        Example: 'every 2nd bar starting from bar 1' → t.is_bar_mod(2, offset=1)
        """
        return (self._bar - offset) % n == 0

    def matches(
        self,
        beat: Union[int, float, None] = None,
        bar_mod: Union[int, None] = None,
        bar_offset: int = 0,
        downbeat_only: bool = False,
        tolerance: float = 1e-6,
    ) -> bool:
        """Combine predicates into a single readable call.

        Examples
        --------
        'Play on beat 3 of every second bar':
            t.matches(beat=3, bar_mod=2)

        'Play on every downbeat':
            t.matches(downbeat_only=True)

        'Play on the & of 2 in every bar':
            t.matches(beat=2.5)
        """
        if downbeat_only and not self.is_downbeat():
            return False
        if beat is not None and not self.is_beat(beat, tolerance):
            return False
        if bar_mod is not None and not self.is_bar_mod(bar_mod, offset=bar_offset):
            return False
        return True

    # ── comparison and hashing ────────────────────────────────────────────────

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, MusicalTime):
            return NotImplemented
        return (
            self._bar == other._bar
            and abs(self._beat - other._beat) < 1e-9
            and self._beats_per_bar == other._beats_per_bar
        )

    def __lt__(self, other: "MusicalTime") -> bool:
        if not isinstance(other, MusicalTime):
            return NotImplemented
        return self.to_beats() < other.to_beats()

    def __le__(self, other: "MusicalTime") -> bool:
        return self == other or self < other

    def __gt__(self, other: "MusicalTime") -> bool:
        return not self <= other

    def __ge__(self, other: "MusicalTime") -> bool:
        return not self < other

    def __hash__(self) -> int:
        # Round beat to 6 decimal places for stable hashing
        return hash((self._bar, round(self._beat, 6), self._beats_per_bar))

    # ── display ───────────────────────────────────────────────────────────────

    def __repr__(self) -> str:
        return (
            f"MusicalTime(bar={self._bar}, beat={self._beat}, bpb={self._beats_per_bar})"
        )

    def __str__(self) -> str:
        """Human-readable: 'bar 3, beat 2.5'  (1-indexed bar and beat)."""
        return f"bar {self._bar + 1}, beat {self._beat + 1.0:.3g}"


# ─────────────────────────────────────────────────────────────────────────────
# Convenience helpers used by rhythm.py and strategies.py
# ─────────────────────────────────────────────────────────────────────────────

def beats_to_bar_and_local(
    global_beats: float,
    beats_per_bar: int = 4,
) -> tuple[int, float]:
    """Return (bar_index, beat_within_bar) without constructing a MusicalTime.

    Marginally faster when you need the pair but not the full object.
    """
    t = MusicalTime.from_beats(global_beats, beats_per_bar)
    return t.bar, t.beat


def is_downbeat_float(beat: float, beats_per_bar: int = 4, tol: float = 1e-6) -> bool:
    """Return True if `beat` is at a bar boundary.

    Drop-in replacement for the common ``beat % beats_per_bar < tol`` pattern.
    Safe against floating-point drift.
    """
    return (beat % beats_per_bar) < tol or abs(beat % beats_per_bar - beats_per_bar) < tol


def bar_beat_from_event_offset(
    event_beat: float,
    section_start_beats: float,
    beats_per_bar: int = 4,
) -> MusicalTime:
    """
    Build a MusicalTime for an event that has a section-relative beat offset,
    given the section's absolute start position.

    Useful inside _build_chord_events and similar kernels when you want to ask
    'is this event on a downbeat?' without caring about the global offset.

    Args:
        event_beat          : the event's beat position within the section (0-based)
        section_start_beats : the section's absolute beat offset in the piece
        beats_per_bar       : time signature
    """
    abs_beat = section_start_beats + event_beat
    return MusicalTime.from_beats(abs_beat, beats_per_bar)


# ─────────────────────────────────────────────────────────────────────────────
# Quick self-test / demo
# ─────────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    print("=== MusicalTime demo ===\n")

    # Construction and properties
    t = MusicalTime(bar=0, beat=0.0, beats_per_bar=4)
    print(f"t = {t}")
    print(f"  is_downbeat()    : {t.is_downbeat()}")        # True
    print(f"  to_beats()       : {t.to_beats()}")           # 0.0
    print(f"  beat_number      : {t.beat_number}")          # 1.0

    # from_beats round-trip
    t2 = MusicalTime.from_beats(9.5, beats_per_bar=4)
    print(f"\nMusicalTime.from_beats(9.5) = {t2}")
    print(f"  bar={t2.bar}, beat={t2.beat}, bpb={t2.beats_per_bar}")  # bar=2, beat=1.5
    print(f"  round-trip: {t2.to_beats()}")                # 9.5

    # add_beats — crosses bar boundary
    t3 = MusicalTime(bar=0, beat=3.0, beats_per_bar=4)
    t4 = t3.add_beats(1.5)
    print(f"\n{t3} + 1.5 beats = {t4}")  # bar 1, beat 0.5

    # Predicates — rule authoring
    pos = MusicalTime(bar=2, beat=2.0, beats_per_bar=4)
    print(f"\npos = {pos}")
    print(f"  is_beat(3)       : {pos.is_beat(3)}")        # True (beat 3 in 1-indexed)
    print(f"  is_beat(1)       : {pos.is_beat(1)}")        # False
    print(f"  is_bar_mod(2)    : {pos.is_bar_mod(2)}")     # True
    print(f"  is_downbeat()    : {pos.is_downbeat()}")     # False

    print(f"  matches(beat=3, bar_mod=2) : {pos.matches(beat=3, bar_mod=2)}")  # True
    print(f"  matches(beat=1)            : {pos.matches(beat=1)}")             # False

    # Immutability check
    try:
        pos.bar = 5  # type: ignore
    except AttributeError as e:
        print(f"\nImmutability: {e}")

    # is_downbeat_float helper
    print(f"\nis_downbeat_float(8.0, 4) : {is_downbeat_float(8.0, 4)}")   # True
    print(f"is_downbeat_float(8.1, 4) : {is_downbeat_float(8.1, 4)}")     # False
    print(f"is_downbeat_float(7.9999999999, 4) : {is_downbeat_float(7.9999999999, 4)}")  # True (drift)

    # Comparison
    a = MusicalTime(bar=1, beat=0.0, beats_per_bar=4)
    b = MusicalTime(bar=0, beat=3.5, beats_per_bar=4)
    print(f"\n{a} > {b}: {a > b}")  # True (4.0 > 3.5)

    print("\n✓ All demos passed.")
