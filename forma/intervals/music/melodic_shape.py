"""
melodic_shape.py — Intervals Engine

Apex/goal-tone mechanism (Phase 1 of the apex/goal-tone build). Two
independent, composable pieces of phrase-level melodic direction that none
of the four melody behaviors (generative, lyrical, sparse, develop) have
today:

  apex pull:     bias note choice toward a declared scale degree as a
                 phrase approaches a declared position within the section,
                 then away from it afterward -- "build to a peak, then
                 settle" as an actual mechanism, not just a hoped-for side
                 effect of random choice.
  cadence pull:  bias the last note(s) of a cadential moment toward a
                 resolution tone, generalizing the ad-hoc `is_last_note`
                 pattern generate_lyrical already has into something all
                 four behaviors can share and mean the same thing by.

Built and unit-tested here in complete isolation from melody.py — none of
the four generate_* behaviors import anything from this module yet. That's
deliberate: a bug in this math is trivial to find and fix here; the same
bug discovered after it's live in four behaviors is a much bigger
untangling job, and this codebase has hit that exact shape of problem
enough times already (the pitch_to_degree tie-break gravity well, the
_sequence_intervals_diatonically offset bug, the Motif-dataclass silent
field drop) to take the isolation-first discipline seriously here too.

Design decisions this module deliberately encodes, settled before any code
was written:

  - Position (`position_t`) is NOT computed in here. Callers must derive it
    using the exact same formula rhythm.section_position_t() already uses
    for the dynamic arc envelope, so a section's loudest moment and its
    melodic apex are guaranteed to agree about what "70% through" means —
    two independent implementations of that concept is precisely the shape
    Finding 0 was (two implementations of one transform-dispatch concept,
    one got fixed, the other silently didn't). This module only accepts
    position_t as a plain float; it has no opinion on bar indices, beat
    offsets, or which voice's time base produced it.

  - Weighting is by list repetition, not a rewritten rng.choice contract.
    Every function here returns a re-weighted candidate list — preferred
    candidates appear multiple times, everything else appears once, never
    zero times. Callers keep calling rng.choice(result) exactly as every
    behavior already does today; this only shapes the odds, never removes
    an option outright, and never hands back an empty list (matching the
    codebase's "never break the render" discipline — see motif_to_notes's
    degenerate-motif fallback, generate_develop's same fallback, and
    bass.py's chord-tone-preference clamp, none of which ever produce no
    candidates at all).

  - apex_degree is an unbounded diatonic scale-degree offset from the
    tonic (degree 0), in the same 0-indexed convention scale_degrees.py
    and motif.py's intervals already use — NOT the 1-indexed "scale degree
    5" language a composer would use when talking about the dominant.
    That translation (composer-facing 1-indexed -> engine-internal
    0-indexed) belongs in the schema/wiring layer (Phase 6), not here;
    this module stays consistent with the internal convention it composes
    with directly (pitch_to_degree/degree_to_pitch).

  - Strength is a hardcoded module constant for v1 (Phase 0 decision #4),
    not yet a schema-exposed field — smaller surface area to validate on
    the first pass; promotable to a real field later without changing
    this module's contract, since every function already accepts strength
    as a parameter with the module constant as its default.
"""

from typing import Optional

from intervals.music.scale_degrees import pitch_classes, degree_to_pitch, pitch_to_degree


# ---------------------------------------------------------------------------
# Tunable defaults (Phase 0 decision #4: hardcoded for v1, not schema-exposed)
# ---------------------------------------------------------------------------

# How many times a preferred candidate is repeated in the weighted list
# relative to a non-preferred one (which always appears exactly once).
# 3 means "preferred candidates are picked ~3x as often as any single
# non-preferred one" under a uniform rng.choice over the returned list —
# a real, audible lean, not an absolute override; other candidates always
# stay reachable, preserving some variety rather than a fully mechanical
# phrase shape every time.
APEX_BIAS_STRENGTH = 3

# Cadence is a more local, decisive moment than the phrase-long apex build
# (see module docstring — "a local, sudden arrival, not a slow gradient"),
# so it pulls harder by default.
CADENCE_BIAS_STRENGTH = 4

# Phase 4 (generate_develop): max diatonic scale-degree steps a single
# retile's anchor is allowed to shift toward a target (apex or cadence
# resolution) in one move. develop has no per-note candidate list to
# weight the way lyrical/generative do -- motif_to_notes builds each
# retiled statement deterministically from wherever the anchor sits, so
# apex/cadence bias here means nudging that anchor instead, cascading
# through the whole next statement. Capped small so the cumulative pull
# across many retiles produces real movement without a single retile
# jumping far enough to break the motif's own identity.
ANCHOR_SHIFT_MAX_STEP = 2

# A candidate within this many semitones of the resolution pitch counts as
# "resolving" for cadence-pull purposes — matches motif_to_notes and
# bass.py's existing "within a whole step" chord-tone-preference threshold
# (both use <= 2 semitones for an analogous "close enough to count" check),
# reused here rather than inventing a third threshold convention.
CADENCE_RESOLUTION_THRESHOLD = 2


def resolve_apex_pitch(
    apex_degree: int,
    scale_tones: list[int],
    octave_bottom: int,
    octave_top: int,
    anchor: int,
) -> int:
    """
    Convert a diatonic apex_degree into an actual target MIDI pitch.

    Placed in the octave nearest `anchor` (so the target sits near
    wherever the melody currently is, not always in some fixed reference
    octave), then folded into [octave_bottom, octave_top] by whole
    octaves if it still falls outside — the identical fold discipline
    motif_to_notes and bass.py's style_motif already use. Folding by
    whole octaves preserves the pitch class exactly, so the result is
    still genuinely degree `apex_degree` of this scale, just relocated —
    never a different degree substituted in its place.

    This always returns a pitch (never raises) — Phase 0 decided
    unreachable targets are a lint-time warning, not a render-time
    failure. Use apex_degree_reachable() below to check reachability
    for that warning; this function's job is only to always produce
    something playable.
    """
    pcs = pitch_classes(scale_tones)
    n = len(pcs)
    anchor_degree = pitch_to_degree(anchor, pcs)
    anchor_octave = anchor_degree // n

    pitch = degree_to_pitch(apex_degree + anchor_octave * n, pcs)
    while pitch < octave_bottom:
        pitch += 12
    while pitch > octave_top:
        pitch -= 12
    return pitch


def apex_degree_reachable(
    apex_degree: int,
    scale_tones: list[int],
    octave_bottom: int,
    octave_top: int,
) -> bool:
    """
    True if apex_degree lands natively inside [octave_bottom, octave_top]
    in at least one octave placement — i.e. the register genuinely spans
    this degree as declared, not merely "some pitch survives being folded
    there by resolve_apex_pitch()" (folding always succeeds; this checks
    whether the target was honored as authored, for the Phase 6 lint
    warning that tells a composer their apex_degree doesn't fit the
    section's register before they render, not after).
    """
    pcs = pitch_classes(scale_tones)
    n = len(pcs)
    span_octaves = (octave_top - octave_bottom) // 12 + 2
    for octave in range(-span_octaves, span_octaves + 1):
        pitch = degree_to_pitch(apex_degree + octave * n, pcs)
        if octave_bottom <= pitch <= octave_top:
            return True
    return False


def apex_weighted_candidates(
    candidates: list[int],
    current: int,
    apex_pitch: int,
    position_t: float,
    apex_position: float,
    strength: int = APEX_BIAS_STRENGTH,
) -> list[int]:
    """
    Re-weight `candidates` to prefer motion toward apex_pitch before
    apex_position, and away from it after — "build to a peak, then
    settle."

    Distance-based, not a fixed up/down sign convention: a candidate is
    "preferred" pre-apex if it's genuinely CLOSER to apex_pitch than
    `current` already is (abs(candidate - apex_pitch) < abs(current -
    apex_pitch)), and post-apex if it's genuinely FARTHER. This handles
    the case where `current` has already overshot apex_pitch (or the
    phrase never reached it) gracefully — "closer" and "farther" self-
    correct toward the intended shape regardless of where the melody
    actually is, rather than a rigid "always prefer ascending" rule that
    would make no sense once the melody is already above the target.

    Never returns an empty list, and never excludes a candidate outright
    — non-preferred candidates still appear once; only their relative
    odds change. If nothing in `candidates` satisfies the preference
    (e.g. a single candidate, or every option moves the "wrong" way),
    returns `candidates` unchanged rather than fabricating a preference
    that isn't there.
    """
    if not candidates:
        return list(candidates)

    approaching = position_t < apex_position
    current_dist = abs(current - apex_pitch)

    def is_preferred(c: int) -> bool:
        c_dist = abs(c - apex_pitch)
        return c_dist < current_dist if approaching else c_dist > current_dist

    preferred = [c for c in candidates if is_preferred(c)]
    if not preferred:
        return list(candidates)

    weighted = []
    for c in candidates:
        weighted.append(c)
        if is_preferred(c):
            weighted.extend([c] * (strength - 1))
    return weighted


def cadence_weighted_candidates(
    candidates: list[int],
    resolution_pitch: int,
    strength: int = CADENCE_BIAS_STRENGTH,
) -> list[int]:
    """
    Re-weight `candidates` toward resolution_pitch (typically the current
    chord's root, or the tonic) for use at a cadential moment — the last
    note, or last two, of whichever chord Phase 0's cadence decision
    identifies as cadential (see melody.py's eventual wiring: either the
    section's true final chord, or every progression-cycle boundary,
    depending on the section's resolve_every_cycle setting — this
    function doesn't know or care which; it only weights toward whatever
    resolution_pitch it's given).

    "Resolving" means within CADENCE_RESOLUTION_THRESHOLD semitones of
    resolution_pitch, not only an exact pitch-class match — the same
    "close enough to count" threshold motif_to_notes and bass.py's
    style_motif already use for their own chord-tone-preference checks,
    reused here rather than a fourth threshold convention.

    Same never-empty, never-exclude discipline as apex_weighted_candidates.
    """
    if not candidates:
        return list(candidates)

    def is_resolving(c: int) -> bool:
        return abs(c - resolution_pitch) <= CADENCE_RESOLUTION_THRESHOLD

    preferred = [c for c in candidates if is_resolving(c)]
    if not preferred:
        return list(candidates)

    weighted = []
    for c in candidates:
        weighted.append(c)
        if is_resolving(c):
            weighted.extend([c] * (strength - 1))
    return weighted


def directed_anchor_shift(
    anchor: int,
    target_pitch: int,
    scale_tones: list[int],
    position_t: float,
    apex_position: float,
    max_step_degrees: int = ANCHOR_SHIFT_MAX_STEP,
) -> int:
    """
    Nudge a retile anchor's pitch toward target_pitch, by at most
    max_step_degrees diatonic scale-degree steps, in the direction
    implied by position_t vs apex_position (Phase 4: generate_develop's
    anchor-shift mechanism — see module docstring's Phase 4 note above
    on why this differs from apex_weighted_candidates/
    cadence_weighted_candidates rather than reusing them directly).

    Before apex_position ("approaching"): shifts toward target_pitch.
    At or after apex_position ("receding"): shifts AWAY from
    target_pitch — the anchor drifts back down (or up, symmetrically)
    once the phrase has passed its declared peak, rather than
    continuing to climb indefinitely.

    Reused for cadence by the caller passing position_t=0.0,
    apex_position=1.0 (or any position_t < apex_position) — cadence has
    no "settle after" phase of its own, it's a single always-approach
    pull toward the resolution pitch, so forcing the "approaching"
    branch unconditionally gives the right behavior without a second,
    near-duplicate function.

    Distance is measured in degree space nearest THIS anchor's own
    placement (pitch_to_degree's prev_degree parameter), not target_pitch's
    literal octave — so a target several octaves away from the anchor
    doesn't produce one enormous, identity-breaking leap; the shift is
    always capped at max_step_degrees regardless of how far apart anchor
    and target actually are.

    Returns `anchor` unchanged if it's already exactly at target_pitch's
    nearest degree (distance 0) — nothing to shift toward.
    """
    pcs = pitch_classes(scale_tones)
    anchor_degree = pitch_to_degree(anchor, pcs)
    target_degree = pitch_to_degree(target_pitch, pcs, prev_degree=anchor_degree)
    distance = target_degree - anchor_degree
    if distance == 0:
        return anchor

    toward_target = 1 if distance > 0 else -1
    direction = toward_target if position_t < apex_position else -toward_target
    step = direction * min(abs(distance), max_step_degrees)

    return degree_to_pitch(anchor_degree + step, pcs)
