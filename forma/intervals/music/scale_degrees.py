"""
scale_degrees.py — Intervals Engine

Shared diatonic scale-degree <-> absolute-pitch primitives.

Promoted out of melody.py's _sequence_intervals_diatonically (Phase B1 of
the diatonic-motif migration — see motif.py's Motif.intervals docstring for
the full contract this serves). That function needed to convert an absolute
MIDI pitch to an unbounded scale-degree index and back, purely to implement
one transform ("sequence"). Phase B2 needs the exact same conversion as the
core of motif_to_notes itself once Motif.intervals natively holds diatonic
steps, so the primitive is generalized here rather than re-implemented.

Degree indexing is unbounded (not folded to a register window): degree 0 is
the scale tone at the reference pitch class list's index 0, within whatever
octave the target pitch falls in. `degree_to_pitch` and `pitch_to_degree`
are exact inverses of one another for any degree an int can hold.

Tie-break fix (Phase B1): the original _pitch_to_degree picked the nearest
scale degree by pitch-class distance alone, iterating candidates in a fixed
order — which meant a pitch sitting exactly halfway between two scale tones
(e.g. one semitone below the tonic in a mode whose scale gap there is a
whole tone) could resolve to whichever candidate happened to be considered
first, silently jumping a full octave rather than taking the small step.
This surfaced twice: once inside the engine's own nearest_scale_tone/
motif_to_notes path (the bug that motivated the whole diatonic-motif
migration), and again in an offline catalog-conversion script written to
migrate existing pieces' motif data, which hit the identical failure mode
on real catalog motifs (piece_train, piece_shake's "plea") before the fix
below was applied. pitch_to_degree here takes an explicit `prev_degree` and
breaks ties toward whichever candidate is the smaller degree-step away from
it, so a genuine tie resolves to local continuity instead of an accidental
octave leap. Callers doing a one-shot, non-sequential conversion can omit
`prev_degree` (defaults to 0); callers walking a sequence of pitches should
thread the previous call's return value through, exactly as
_sequence_intervals_diatonically and motif_to_notes (Phase B2) both do.
"""

from typing import Iterable


def pitch_classes(scale_tones: Iterable[int]) -> list[int]:
    """
    Reduce a list of absolute scale-tone MIDI pitches (possibly spanning
    several octaves, as returned by get_scale_tones) to the sorted, deduped
    set of pitch classes (0-11) that defines the scale's shape.
    """
    return sorted(set(t % 12 for t in scale_tones))


def degree_to_pitch(degree: int, pcs: list[int]) -> int:
    """
    Convert an unbounded diatonic scale-degree index to an absolute MIDI
    pitch, given a scale's pitch-class list (as returned by pitch_classes).

    Degree 0 -> pcs[0] in the reference octave (octave offset 0, i.e. the
    pitch classes as given, un-transposed). Degree n (where n = len(pcs))
    is exactly one octave above degree 0, and so on in both directions.
    """
    n = len(pcs)
    octave, idx = divmod(degree, n)
    return pcs[idx] + 12 * octave


def pitch_to_degree(pitch: int, pcs: list[int], prev_degree: int = 0) -> int:
    """
    Convert an absolute MIDI pitch to the nearest diatonic scale-degree
    index, given a scale's pitch-class list.

    The search window is located from `pitch` itself (via pitch // 12, its
    own octave — always the correct region, for any pitch), checking that
    octave and its immediate neighbors to correctly handle a pitch class
    sitting right at the scale's octave seam. `prev_degree` is used only
    to break a genuine tie (a pitch exactly equidistant between two scale
    degrees) toward local continuity — see module docstring — not to
    locate the search region. An earlier version of this function centered
    the search window on `prev_degree` with a small fixed radius, which
    made it silently return nonsense for any pitch far from degree 0 when
    called with the default prev_degree=0 (caught before shipping: a
    quick manual sanity check on the "sequence" transform returned degrees
    in the teens/twenties for pitches around MIDI 73, because the correct
    degree — around 45 — was simply outside the search window).
    """
    n = len(pcs)
    octave_est, _ = divmod(pitch, 12)

    candidates = [
        idx + n * (octave_est + oct_offset)
        for oct_offset in (-1, 0, 1)
        for idx in range(n)
    ]

    def key(d: int):
        dist = abs(degree_to_pitch(d, pcs) - pitch)
        step = abs(d - prev_degree)
        return (dist, step)

    return min(candidates, key=key)
