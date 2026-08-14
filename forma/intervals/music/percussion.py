"""
percussion.py — Intervals Engine
Generates drum patterns that track the bass and lock to density/rhythm.

Drum patterns are MIDI-based: kick, snare, hi-hat, ghost notes.
They follow the same density/swing system as other voices. Groove is
honored only where its name overlaps with a defined drum pattern (see
generate_drums()'s docstring) -- there is no general mapping from an
arbitrary single-voice groove name onto a full kick/snare/hi-hat kit.

The drums reinforce bass note onsets and add rhythmic definition at the
subdivision level. Five named patterns: four_on_floor, backbeat, halftime,
minimal, sideclick.

MIDI channels:
  Kick:       note 36 (C1 in drum notation)
  Snare:      note 38 (D1)
  Hi-hat:     note 42 (F#1)
  Ride:       note 51 (D#2)
  Sidestick:  note 37 (C#1)
"""

import math
import random
from dataclasses import dataclass
from typing import Optional
from intervals.music.bass import BassNote
from intervals.music.rhythm import RhythmEvent, get_pattern, apply_swing, remap_swing_ratio


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------

@dataclass
class DrumHit:
    """A single drum note — note number + timing + velocity."""
    midi_note: int       # 36=kick, 38=snare, 42=hi-hat, etc.
    start_beat: float
    duration_beats: float = 0.1  # brief attack/release
    velocity: int = 80
    # Section-relative bar index (0-based) this hit was tiled into, and the
    # section's total bar count. Both default to 0 for callers that build a
    # DrumHit directly (bass-reinforcement, swing) without a phrase context.
    # Purely descriptive metadata at this stage -- nothing reads it yet. It
    # exists so a future per-bar pattern-selection pass (fills, builds) has
    # bar position already threaded through the pipeline instead of having
    # to re-derive it a second time from start_beat downstream.
    bar_index: int = 0
    total_bars: int = 0

    def __repr__(self):
        names = {36: "KICK", 38: "SNARE", 42: "HI-HAT", 51: "RIDE", 37: "SIDESTICK"}
        name = names.get(self.midi_note, f"DRUM({self.midi_note})")
        return f"DrumHit({name} beat={self.start_beat:.2f} vel={self.velocity})"


# ---------------------------------------------------------------------------
# MIDI Drum Kit
# ---------------------------------------------------------------------------

DRUM_KIT = {
    "kick":     36,    # Bass drum
    "snare":    38,    # Snare
    "hi_hat":   42,    # Closed hi-hat
    "ride":     51,    # Ride cymbal
    "sidestick": 37,   # Sidestick / cross-stick
    "tom_hi":   50,    # High tom
    "tom_mid":  48,    # Mid tom
    "tom_lo":   45,    # Low tom
}


# ---------------------------------------------------------------------------
# Drum Pattern Definitions
# Each pattern is a list of (instrument_name, beat_within_bar, velocity, priority)
# Priority: 1=sparse, 2=medium, 3=full
# ---------------------------------------------------------------------------

DRUM_PATTERNS = {
    # ── four_on_floor ─────────────────────────────────────────────────────
    # Classic electronic: kick on every beat, snare on 2+4, hi-hats on eighths
    "four_on_floor": [
        # Kick: every beat
        ("kick",     0.0, 0.95, 1),
        ("kick",     1.0, 0.90, 1),
        ("kick",     2.0, 0.95, 1),
        ("kick",     3.0, 0.90, 1),
        # Snare: 2 and 4
        ("snare",    1.0, 0.85, 1),
        ("snare",    3.0, 0.85, 1),
        # Hi-hat: eighths (sparse has closed at beats, medium adds offbeats, full adds more)
        ("hi_hat",   0.0, 0.65, 1),
        ("hi_hat",   0.5, 0.55, 2),
        ("hi_hat",   1.0, 0.65, 1),
        ("hi_hat",   1.5, 0.55, 2),
        ("hi_hat",   2.0, 0.65, 1),
        ("hi_hat",   2.5, 0.55, 2),
        ("hi_hat",   3.0, 0.65, 1),
        ("hi_hat",   3.5, 0.55, 2),
    ],

    # ── backbeat ───────────────────────────────────────────────────────────
    # Kick on beat 1, syncopated snare, hi-hat shuffled. Pop/soul.
    "backbeat": [
        ("kick",     0.0, 1.00, 1),
        ("kick",     2.0, 0.80, 2),
        ("snare",    1.0, 0.90, 1),
        ("snare",    2.5, 0.70, 2),
        ("snare",    3.0, 0.95, 1),
        ("hi_hat",   0.0, 0.65, 1),
        ("hi_hat",   0.5, 0.50, 3),
        ("hi_hat",   1.0, 0.70, 1),
        ("hi_hat",   1.5, 0.55, 2),
        ("hi_hat",   2.0, 0.65, 1),
        ("hi_hat",   2.5, 0.50, 3),
        ("hi_hat",   3.0, 0.70, 1),
        ("hi_hat",   3.5, 0.55, 2),
    ],

    # ── halftime ───────────────────────────────────────────────────────────
    # Spacious, lo-fi vibe. Kick on 1, snare on 3, sparse hi-hat.
    "halftime": [
        ("kick",     0.0, 0.95, 1),
        ("snare",    2.0, 0.85, 1),
        ("hi_hat",   0.0, 0.60, 1),
        ("hi_hat",   1.0, 0.50, 2),
        ("hi_hat",   2.0, 0.60, 1),
        ("hi_hat",   3.0, 0.50, 2),
        ("kick",     1.0, 0.65, 3),  # ghost kick
        ("snare",    3.0, 0.60, 3),  # ghost snare
    ],

    # ── minimal ────────────────────────────────────────────────────────────
    # Just kick on beats, snare on backbeat. Very sparse, open.
    "minimal": [
        ("kick",     0.0, 0.95, 1),
        ("kick",     2.0, 0.90, 1),
        ("snare",    1.0, 0.90, 1),
        ("snare",    3.0, 0.90, 1),
    ],

    # ── sideclick ──────────────────────────────────────────────────────────
    # Sidestick for pocket rhythm, kick on 1, snare accent on 3.
    "sideclick": [
        ("kick",     0.0, 0.95, 1),
        ("snare",    2.0, 0.85, 1),
        ("sidestick", 0.5, 0.70, 1),
        ("sidestick", 1.5, 0.75, 1),
        ("sidestick", 2.5, 0.70, 1),
        ("sidestick", 3.5, 0.75, 1),
        ("hi_hat",   1.0, 0.55, 2),
        ("hi_hat",   3.0, 0.55, 2),
    ],
}

VALID_DRUM_PATTERNS = list(DRUM_PATTERNS.keys())


# ---------------------------------------------------------------------------
# Percussion Generation
# ---------------------------------------------------------------------------

def _compute_fill_bar_groups(
    fill: dict,
    total_bars: int,
) -> list[range]:
    """
    Which section-relative bar indices belong to a fill, grouped by fill
    instance (a "group" = one fill event, possibly spanning `bars` > 1
    consecutive bars). Grouping matters only so probability is rolled once
    per fill EVENT, not once per bar within it -- a bars=2 fill should never
    fire on only its second bar.

    placement="phrase_end": one group ending on the last bar of every
        phrase_bars-bar block (bar indices phrase_bars-1, 2*phrase_bars-1, ...).
        A section shorter than phrase_bars produces zero groups.
    placement="section_end": exactly one group, ending on the section's
        final bar.
    """
    groups: list[range] = []
    bars = max(1, fill.get("bars", 1))
    placement = fill.get("placement", "phrase_end")

    if placement == "phrase_end":
        phrase_bars = max(1, fill.get("phrase_bars", 8))
        end = phrase_bars - 1
        while end < total_bars:
            start = max(0, end - bars + 1)
            groups.append(range(start, end + 1))
            end += phrase_bars
    elif placement == "section_end":
        if total_bars > 0:
            end = total_bars - 1
            start = max(0, end - bars + 1)
            groups.append(range(start, end + 1))

    return groups


def _generate_fill_slots(fill: dict, beats_per_bar: int) -> list[tuple]:
    """
    One fill bar's worth of (instrument, beat_in_bar, velocity_scale,
    priority) slots, at `fill["subdivision"]` resolution across the bar,
    velocity ramping linearly from velocity_start to velocity_end WITHIN
    this bar. If a fill spans multiple bars (bars > 1), each bar gets this
    same independent ramp -- consecutive identical ramps, not one ramp
    stretched across the whole span. A true multi-bar accelerando (the
    subdivision itself tightening bar over bar, e.g. 16ths -> 32nds) is a
    different, stateful mechanism and out of scope here.
    """
    instrument = fill.get("instrument", "hi_hat")
    subdivision = fill.get("subdivision", 0.25)
    vel_start = fill.get("velocity_start", 0.5)
    vel_end = fill.get("velocity_end", 1.0)

    n = max(1, round(beats_per_bar / subdivision))
    slots = []
    for i in range(n):
        beat_in_bar = i * subdivision
        if beat_in_bar >= beats_per_bar:
            break
        t = i / (n - 1) if n > 1 else 1.0
        vel_scale = vel_start + (vel_end - vel_start) * t
        slots.append((instrument, beat_in_bar, vel_scale, 1))
    return slots


def _select_slots_for_bar(
    active_slots: list,
    bar_index: int,
    fill: Optional[dict],
    fill_bar_set: set,
    beats_per_bar: int,
) -> list:
    """
    Per-bar slot selection seam for generate_drums()'s tiling loop.

    Identity unless `fill` is set and `bar_index` is in `fill_bar_set` (the
    precomputed, probability-filtered set of bars that actually get a fill
    this render). When it fires: every existing slot for the fill's target
    instrument is stripped from this bar only (the rest of the kit --
    typically kick -- keeps playing underneath, per design: fills replace
    one voice's part for a bar, they don't silence the groove), and
    replaced with the fill's own onsets.

    This remains the general extension point for future per-bar variation
    beyond fills; bar_index/total_bars are still available to any future
    caller of this seam even though the current fill logic only needs the
    precomputed set membership.
    """
    if fill is None or bar_index not in fill_bar_set:
        return active_slots

    target_instrument = fill.get("instrument", "hi_hat")
    filtered = [s for s in active_slots if s[0] != target_instrument]
    return filtered + _generate_fill_slots(fill, beats_per_bar)


def _generate_accelerando_hits(
    accelerando: dict,
    group_start_beat: float,
    span_beats: float,
) -> list["DrumHit"]:
    """
    One accelerando roll's absolute-beat onsets, covering `span_beats`
    starting at `group_start_beat`.

    This is a genuinely different mechanism from _generate_fill_slots, not
    a bigger version of it. A fill is called once per bar from the tiling
    loop's per-bar seam, stateless between calls -- fine, because a
    single-bar fill doesn't need to remember anything. An accelerando's
    subdivision tightens continuously across its WHOLE span (e.g. bar 3 of
    4 needs to know it's 75% of the way through the roll), which the
    per-bar seam has no way to carry between calls. So this generates the
    entire multi-bar span in one call up front, as a flat DrumHit list,
    the same way _reinforce_bass_with_kick builds a separate flat list
    that gets merged into `hits` rather than threaded through the tiling
    loop.

    subdivision: interpolated via a quadratic ("exponential") ease by
    default -- slow to tighten early, rapidly tightening near the end,
    matching the same quadratic shape rhythm.arc_multiplier()'s "build"
    curve already uses elsewhere in this engine. curve="linear" opts into
    a straight interpolation instead.

    velocity: ramps linearly start->end, independent of the subdivision
    curve and using the same convention _generate_fill_slots uses (a
    0.0-1.0 multiplier of the same base-80 velocity scale). This is an
    explicit design choice, not an oversight: a section's own arc:"build"
    (if present) already shapes velocity at the whole-section level: a
    roll's crescendo is usually sharper and more localized than that, so
    the two are deliberately allowed to stack rather than one being
    folded into the other.

    Landing is APPROXIMATE, not exact: onsets are stepped greedily (the
    same "while position < end" pattern used everywhere else in this
    file), so the last onset typically lands within one subdivision_end
    of the span's actual end -- a fraction of a beat, not exactly on it.
    An exact-landing version exists (solve analytically for onset count
    given start/end subdivision and total span) but adds real complexity
    for a difference unlikely to be audible as anything other than "rolls
    right up to the drop." This is the pragmatic choice, flagged
    explicitly rather than picked silently.
    """
    instrument = accelerando.get("instrument", "snare")
    sub_start = accelerando.get("subdivision_start", 0.25)
    sub_end = accelerando.get("subdivision_end", 0.0625)
    vel_start = accelerando.get("velocity_start", 0.5)
    vel_end = accelerando.get("velocity_end", 1.0)
    curve = accelerando.get("curve", "exponential")

    midi_note = DRUM_KIT.get(instrument)
    if midi_note is None:
        return []

    hits = []
    elapsed = 0.0
    while elapsed < span_beats - 0.001:
        t = elapsed / span_beats if span_beats > 0 else 1.0
        eased = t * t if curve == "exponential" else t
        cur_subdivision = sub_start + (sub_end - sub_start) * eased
        # Guard against a pathological start/end pair collapsing to a
        # near-zero step, which would spin this loop effectively forever.
        cur_subdivision = max(cur_subdivision, 0.01)

        vel_scale = vel_start + (vel_end - vel_start) * t
        base_vel = max(40, min(120, int(round(80 * vel_scale))))

        hits.append(DrumHit(
            midi_note=midi_note,
            start_beat=group_start_beat + elapsed,
            duration_beats=0.1,
            velocity=base_vel,
        ))
        elapsed += cur_subdivision

    return hits


def generate_drums(
    total_beats: float,
    bass_notes: list[BassNote],
    pattern: str = "four_on_floor",
    density: str = "medium",
    groove: Optional[str] = None,
    swing: float = 0.0,
    beats_per_bar: int = 4,
    seed: Optional[int] = None,
    fill: Optional[dict] = None,
    accelerando: Optional[dict] = None,
) -> list[DrumHit]:
    """
    Generate drum hits that track the bass and lock to density/rhythm.

    The function:
    1. Tiles the named drum pattern across total_beats
    2. Filters by density (sparse/medium/full)
    3. Reinforces bass note onsets with kick hits
    4. Applies swing
    5. Splices in a fill on eligible bars, if `fill` is set

    Args:
        total_beats:    Total beats to fill
        bass_notes:     List of BassNote to track
        pattern:        Drum pattern name
        density:        "sparse" | "medium" | "full"
        groove:         Optional groove name (from rhythm.py's VALID_GROOVES,
                        the same vocabulary melody/bass/harmony use). There
                        is no general mapping from a single-voice groove
                        onto a full kick/snare/hi-hat kit, so this only
                        takes effect when the name ALSO happens to be a
                        defined drum pattern (currently "backbeat" or
                        "halftime") -- in that case it overrides `pattern`.
                        Any other groove name (e.g. "shuffle", "waltz",
                        "push") is a deliberate no-op here: swing still
                        applies regardless of groove, but the pattern
                        itself is unaffected.
        swing:          Public swing amount, 0.0-1.0 (0.0 = off, 1.0 = heaviest).
                        Converted internally via remap_swing_ratio() before
                        being applied — do not confuse with the internal
                        0.5-straight swing_ratio scale used downstream.
                        _apply_swing_to_drums()'s gate is purely "beat-
                        fraction exactly 0.5 AND hi_hat/ride" -- it has no
                        concept of a fill onset specifically. A fine-
                        subdivision fill's grid still touches the 0.5 point
                        periodically (every other 16th, every 4th 32nd), so
                        THOSE specific onsets get swung along with the rest
                        of the fill staying straight -- not a clean "fills
                        are exempt from swing," which was an earlier,
                        inaccurate claim about this function.
        beats_per_bar:  Beats per bar (default 4)
        seed:           Random seed
        fill:           Optional dict describing a per-bar fill, mirroring
                        the dict-based convention generate_bass() already
                        uses for its `motif` argument (kept as a plain dict
                        rather than a pydantic model so this module stays
                        decoupled from the schema layer). Keys:
                          placement:      "phrase_end" | "section_end"
                                          (default "phrase_end")
                          phrase_bars:    int, default 8 (only used by
                                          "phrase_end")
                          bars:           int, default 1 -- span of the fill,
                                          ending at the boundary
                          instrument:     drum-kit key, default "hi_hat".
                                          Only this instrument's existing
                                          slots are replaced on a fill bar;
                                          everything else (kick, etc.) keeps
                                          playing underneath by design.
                          subdivision:    beats between fill onsets, default
                                          0.25 (16th notes)
                          velocity_start: 0.0-1.0, default 0.5
                          velocity_end:   0.0-1.0, default 1.0
                          probability:    0.0-1.0, default 1.0 -- rolled once
                                          per fill EVENT (not per bar), so a
                                          multi-bar fill never fires partway.
                                          This thins which otherwise-eligible
                                          fills occur; it is not the primary
                                          placement mechanism, which stays
                                          structural via `placement`.
                        Omitted (None, the default): no fills, output
                        unchanged from before this feature existed.
        accelerando:    Optional dict describing a multi-bar accelerando
                        roll -- a DIFFERENT mechanism from `fill` (see
                        _generate_accelerando_hits's docstring for why),
                        not a bigger version of it. Keys:
                          placement:         "phrase_end" | "section_end"
                                              (default "section_end")
                          phrase_bars:        int, default 8 (only used by
                                              "phrase_end")
                          bars:               int, default 4 -- span of the
                                              whole roll
                          instrument:         drum-kit key, default "snare".
                                              Only this instrument's existing
                                              hits are replaced across the
                                              roll's bars; everything else
                                              keeps playing underneath, same
                                              design as `fill`.
                          subdivision_start:  beats between onsets at the
                                              roll's start, default 0.25
                                              (16ths)
                          subdivision_end:    beats between onsets at the
                                              roll's end, default 0.0625
                                              (64ths)
                          velocity_start:     0.0-1.0, default 0.5
                          velocity_end:       0.0-1.0, default 1.0
                          curve:              "exponential" (default) |
                                              "linear" -- how subdivision
                                              interpolates from start to end
                          probability:        0.0-1.0, default 1.0 -- rolled
                                              once per roll EVENT, same as
                                              `fill`'s probability
                        Omitted (None, the default): no accelerando, output
                        unchanged from before this feature existed.

    Returns:
        List of DrumHit
    """
    if seed is None:
        raise ValueError(f"Deterministic generation requires an explicit seed in {__name__}")
    rng = random.Random(seed)

    # Groove/drum-pattern vocabulary overlap: "backbeat" and "halftime" exist
    # in both rhythm.py's VALID_GROOVES and this module's DRUM_PATTERNS. When
    # the section's groove happens to name a real drum pattern, honor it --
    # this is the only place the docstring's promise is actually
    # implementable (see the `groove` arg doc above for why every other
    # groove name stays a no-op). An explicit `pattern` argument is what the
    # caller asked for by name, so groove only steps in as an override here,
    # not silently underneath an already-specific choice made elsewhere.
    if groove is not None and groove in DRUM_PATTERNS:
        pattern = groove

    if pattern not in DRUM_PATTERNS:
        raise ValueError(
            f"Unknown drum pattern: '{pattern}'. "
            f"Choose from: {VALID_DRUM_PATTERNS}"
        )

    # Density filtering: 1=sparse, 2=medium, 3=full
    density_levels = {"sparse": 1, "medium": 2, "full": 3}
    max_priority = density_levels.get(density, 2)

    template = DRUM_PATTERNS[pattern]
    active_slots = [s for s in template if s[3] <= max_priority]

    if not active_slots:
        active_slots = [s for s in template if s[3] == 1] or [template[0]]

    # Generate hits by tiling the pattern across bars
    hits = []
    bar_duration = beats_per_bar
    total_bars = math.ceil(total_beats / bar_duration) if bar_duration > 0 else 0

    # Which bars actually get a fill this render. Probability is rolled once
    # per fill EVENT (group of `bars` consecutive bars), using the same rng
    # as everything else here so fill placement stays deterministic under a
    # fixed seed like the rest of the engine.
    fill_bar_set: set = set()
    if fill is not None:
        for group in _compute_fill_bar_groups(fill, total_bars):
            if rng.random() < fill.get("probability", 1.0):
                fill_bar_set.update(group)

    # Accelerando: same group/probability computation as fills (placement,
    # phrase_bars, bars, probability mean the same thing for both -- see
    # _compute_fill_bar_groups's docstring, reused here rather than
    # duplicated), but the roll itself is generated as one flat multi-bar
    # list up front, not per-bar through the tiling seam below. See
    # _generate_accelerando_hits's docstring for why.
    accel_hits: list[DrumHit] = []
    accel_bar_set: set = set()
    if accelerando is not None:
        for group in _compute_fill_bar_groups(accelerando, total_bars):
            if rng.random() < accelerando.get("probability", 1.0):
                accel_bar_set.update(group)
                group_start_beat = group.start * bar_duration
                span_beats = len(group) * bar_duration
                accel_hits.extend(
                    _generate_accelerando_hits(accelerando, group_start_beat, span_beats)
                )

    bar_index = 0
    bar_start = 0.0
    while bar_start < total_beats:
        # Per-bar slot selection seam -- identity unless this bar is in
        # fill_bar_set (see _select_slots_for_bar's docstring).
        bar_slots = _select_slots_for_bar(
            active_slots, bar_index, fill, fill_bar_set, beats_per_bar,
        )

        for instrument, beat_in_bar, velocity_scale, _priority in bar_slots:
            abs_beat = bar_start + beat_in_bar
            if abs_beat >= total_beats:
                continue

            midi_note = DRUM_KIT.get(instrument)
            if midi_note is None:
                continue

            # Base velocity from pattern
            base_vel = int(80 * velocity_scale)
            base_vel = max(40, min(120, base_vel))

            hits.append(
                DrumHit(
                    midi_note=midi_note,
                    start_beat=abs_beat,
                    duration_beats=0.1,
                    velocity=base_vel,
                    bar_index=bar_index,
                    total_bars=total_bars,
                )
            )

        bar_start += bar_duration
        bar_index += 1

    # Splice in the accelerando: strip this instrument's normal
    # pattern-tiled hits within the roll's bars (same "this instrument's
    # part is replaced, everything else keeps playing" design as fills),
    # then merge in the precomputed roll.
    if accelerando is not None and accel_bar_set:
        accel_note = DRUM_KIT.get(accelerando.get("instrument", "snare"))
        hits = [h for h in hits if not (h.midi_note == accel_note and h.bar_index in accel_bar_set)]
    hits.extend(accel_hits)

    # Reinforce bass note onsets with soft kick hits
    hits.extend(_reinforce_bass_with_kick(bass_notes, total_beats, max_priority))

    # Apply swing if specified. `swing` here is the public 0.0-1.0 field;
    # _apply_swing_to_drums() expects the internal 0.5-straight scale.
    if swing > 0.001:
        hits = _apply_swing_to_drums(hits, remap_swing_ratio(swing), beats_per_bar)

    # Sort by beat and return
    hits.sort(key=lambda h: h.start_beat)
    return hits


def _reinforce_bass_with_kick(
    bass_notes: list[BassNote],
    total_beats: float,
    priority_level: int,
) -> list[DrumHit]:
    """
    Add soft kick hits wherever the bass plays (for groove pocket).
    Only add if priority allows (medium+ for ghost kicks).
    """
    reinforcement = []

    for bass_note in bass_notes:
        if bass_note.start_beat >= total_beats:
            continue

        # Don't double-hit if bass and pattern kick already coincide
        beat_frac = bass_note.start_beat % 1.0
        if abs(beat_frac - 0.0) < 0.05:  # Close to beat boundary
            continue

        # Ghost kick at lower velocity to lock the bass into pocket
        reinforcement.append(
            DrumHit(
                midi_note=DRUM_KIT["kick"],
                start_beat=bass_note.start_beat,
                duration_beats=0.1,
                velocity=45,  # Soft, doesn't dominate
            )
        )

    return reinforcement


def _apply_swing_to_drums(
    hits: list[DrumHit],
    swing_ratio: float,
    beats_per_bar: int,
) -> list[DrumHit]:
    """
    Apply swing to drum hits by delaying offbeat notes.
    Primarily affects hi-hat and rides on eighth-note offbeats.
    """
    if abs(swing_ratio - 0.5) < 0.001:
        return hits

    swung = []
    for hit in hits:
        beat = hit.start_beat
        beat_in_bar = beat % beats_per_bar
        frac = beat_in_bar % 1.0

        # Swing offbeat eighths (0.5 beat offset within a beat)
        if abs(frac - 0.5) < 0.01 and hit.midi_note in [DRUM_KIT["hi_hat"], DRUM_KIT["ride"]]:
            offset = swing_ratio - 0.5
            swung.append(
                DrumHit(
                    midi_note=hit.midi_note,
                    start_beat=hit.start_beat + offset,
                    duration_beats=hit.duration_beats,
                    velocity=hit.velocity,
                )
            )
        else:
            swung.append(hit)

    return swung


# ---------------------------------------------------------------------------
# Quick test / demo
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    print("=== Percussion Module Demo ===\n")

    from intervals.music.bass import BassNote

    # Dummy bass line for testing
    test_bass = [
        BassNote(midi_note=43, start_beat=0.0, duration_beats=4.0),
        BassNote(midi_note=48, start_beat=4.0, duration_beats=4.0),
        BassNote(midi_note=45, start_beat=8.0, duration_beats=4.0),
        BassNote(midi_note=43, start_beat=12.0, duration_beats=4.0),
    ]

    print("Drum patterns available:")
    for pattern_name in VALID_DRUM_PATTERNS:
        print(f"  - {pattern_name}")

    print("\nGenerating drums for 16 beats:\n")

    for pattern in VALID_DRUM_PATTERNS[:3]:  # Just show first 3
        hits = generate_drums(
            total_beats=16.0,
            bass_notes=test_bass,
            pattern=pattern,
            density="medium",
            seed=42,
        )
        print(f"Pattern '{pattern}' (medium density): {len(hits)} hits")
        for hit in hits[:5]:
            print(f"  {hit}")
        if len(hits) > 5:
            print(f"  ... and {len(hits) - 5} more")
        print()
