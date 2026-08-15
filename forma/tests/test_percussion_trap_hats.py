"""
Tests for the trap hat mechanism in intervals.music.percussion:
_generate_trap_hat_hits and generate_drums()'s `trap_hats` kwarg
end-to-end. See _generate_trap_hat_hits's docstring for why this is a
third, distinct mechanism from fills and accelerando -- a continuous
whole-section texture, not an event.
"""
import random

import pytest

from intervals.music.percussion import (
    DRUM_KIT,
    _generate_trap_hat_hits,
    generate_drums,
)


# ===========================================================================
# _generate_trap_hat_hits
# ===========================================================================

class TestGenerateTrapHatHits:
    def test_produces_hits_spanning_the_whole_input_range(self):
        hits = _generate_trap_hat_hits({}, total_beats=16.0, rng=random.Random(1))
        assert hits
        assert hits[0].start_beat < 1.0
        assert hits[-1].start_beat < 16.0
        assert hits[-1].start_beat > 12.0  # runs close to the full span, not truncated early

    def test_all_hits_are_closed_or_open_hi_hat(self):
        hits = _generate_trap_hat_hits({}, total_beats=16.0, rng=random.Random(1))
        allowed = {DRUM_KIT["hi_hat"], DRUM_KIT["hi_hat_open"]}
        assert all(h.midi_note in allowed for h in hits)

    def test_zero_open_hat_probability_never_uses_open_hat(self):
        hits = _generate_trap_hat_hits(
            {"open_hat_probability": 0.0}, total_beats=16.0, rng=random.Random(1),
        )
        assert all(h.midi_note == DRUM_KIT["hi_hat"] for h in hits)

    def test_high_open_hat_probability_uses_open_hat_at_least_once(self):
        hits = _generate_trap_hat_hits(
            {"open_hat_probability": 1.0, "accent_probability": 1.0},
            total_beats=16.0, rng=random.Random(1),
        )
        assert any(h.midi_note == DRUM_KIT["hi_hat_open"] for h in hits)

    def test_ghost_notes_are_quieter_than_accent_notes(self):
        # accent_probability=1.0 -> every step is an accent, all at
        # accent_velocity. Compare against ghost_velocity=1.0 pinned config
        # to confirm the two velocity paths actually differ.
        accented = _generate_trap_hat_hits(
            {"accent_probability": 1.0, "accent_velocity": 1.0},
            total_beats=8.0, rng=random.Random(1),
        )
        ghosted = _generate_trap_hat_hits(
            {"accent_probability": 0.0, "ghost_velocity": 0.2},
            total_beats=8.0, rng=random.Random(1),
        )
        assert min(h.velocity for h in accented) > max(h.velocity for h in ghosted)

    def test_velocity_can_go_below_the_40_floor_used_elsewhere(self):
        # Deliberate deviation documented in the docstring: ghost notes
        # need to sit below the 40-120 clamp used by patterns/fills/accel.
        hits = _generate_trap_hat_hits(
            {"accent_probability": 0.0, "ghost_velocity": 0.1},
            total_beats=8.0, rng=random.Random(1),
        )
        assert any(h.velocity < 40 for h in hits)

    def test_burst_probability_zero_never_tightens_the_grid(self):
        hits = _generate_trap_hat_hits(
            {"base_subdivision": 0.25, "burst_probability": 0.0},
            total_beats=16.0, rng=random.Random(1),
        )
        gaps = [b - a for a, b in zip(
            [h.start_beat for h in hits], [h.start_beat for h in hits][1:]
        )]
        assert all(g == pytest.approx(0.25, abs=1e-6) for g in gaps)

    def test_burst_probability_one_stays_in_burst_subdivision_throughout(self):
        # With every beat boundary triggering a fresh burst before the
        # previous one expires, the grid should never fall back to base.
        hits = _generate_trap_hat_hits(
            {"base_subdivision": 0.25, "burst_subdivision": 0.125,
             "burst_probability": 1.0, "burst_span_beats": 1.0},
            total_beats=8.0, rng=random.Random(1),
        )
        gaps = [b - a for a, b in zip(
            [h.start_beat for h in hits], [h.start_beat for h in hits][1:]
        )]
        assert all(g == pytest.approx(0.125, abs=1e-6) for g in gaps)

    def test_unknown_instrument_returns_empty(self):
        hits = _generate_trap_hat_hits(
            {"instrument": "bogus"}, total_beats=8.0, rng=random.Random(1),
        )
        assert hits == []

    def test_deterministic_under_fixed_rng_seed(self):
        a = _generate_trap_hat_hits({}, total_beats=16.0, rng=random.Random(5))
        b = _generate_trap_hat_hits({}, total_beats=16.0, rng=random.Random(5))
        assert a == b

    def test_burst_subdivision_literal_options_both_work(self):
        for sub in (0.125, 0.0833):
            hits = _generate_trap_hat_hits(
                {"burst_subdivision": sub, "burst_probability": 1.0},
                total_beats=4.0, rng=random.Random(1),
            )
            assert hits


# ===========================================================================
# generate_drums — trap_hats integration, regression safety, precedence
# ===========================================================================

class TestGenerateDrumsWithTrapHats:
    def test_trap_hats_none_matches_omitting_the_kwarg(self):
        a = generate_drums(32.0, [], pattern="four_on_floor", density="full", seed=42)
        b = generate_drums(32.0, [], pattern="four_on_floor", density="full", seed=42, trap_hats=None)
        assert a == b

    def test_trap_hats_replaces_normal_hi_hat_pattern_entirely(self):
        no_trap = generate_drums(32.0, [], pattern="four_on_floor", density="full", seed=42)
        with_trap = generate_drums(
            32.0, [], pattern="four_on_floor", density="full", seed=42,
            trap_hats={"base_subdivision": 0.25},
        )
        no_trap_hats = sorted(h.start_beat for h in no_trap if h.midi_note == DRUM_KIT["hi_hat"])
        with_trap_hats = sorted(h.start_beat for h in with_trap
                                 if h.midi_note in (DRUM_KIT["hi_hat"], DRUM_KIT["hi_hat_open"]))
        assert no_trap_hats != with_trap_hats

    def test_kick_and_snare_untouched_by_trap_hats(self):
        no_trap = generate_drums(32.0, [], pattern="four_on_floor", density="full", seed=42)
        with_trap = generate_drums(
            32.0, [], pattern="four_on_floor", density="full", seed=42,
            trap_hats={"base_subdivision": 0.25},
        )
        for note_name in ("kick", "snare"):
            note = DRUM_KIT[note_name]
            a = [h.start_beat for h in no_trap if h.midi_note == note]
            b = [h.start_beat for h in with_trap if h.midi_note == note]
            assert a == b, f"{note_name} should be untouched by trap_hats"

    def test_density_does_not_affect_trap_hat_output(self):
        # Confirmed design decision: trap_hats always runs full intensity,
        # density only continues to govern the rest of the kit.
        sparse = generate_drums(
            32.0, [], pattern="four_on_floor", density="sparse", seed=42,
            trap_hats={"base_subdivision": 0.25},
        )
        full = generate_drums(
            32.0, [], pattern="four_on_floor", density="full", seed=42,
            trap_hats={"base_subdivision": 0.25},
        )
        sparse_hats = [h for h in sparse if h.midi_note in (DRUM_KIT["hi_hat"], DRUM_KIT["hi_hat_open"])]
        full_hats = [h for h in full if h.midi_note in (DRUM_KIT["hi_hat"], DRUM_KIT["hi_hat_open"])]
        assert sparse_hats == full_hats

    def test_trap_hats_wins_over_fill_on_same_instrument(self):
        # If both target "hi_hat", trap_hats is applied last and strips
        # ALL hi-hat-family hits (base pattern's own AND the fill's) before
        # splicing its own generation in. Testing this by comparing against
        # a differently-seeded control run isn't valid -- the fill's own
        # probability roll consumes an rng draw before trap_hats generates,
        # so trap_hats' stream legitimately differs once a fill is also
        # present (same shared-rng-sequence design as fills/accelerando).
        # Instead: check the fill bar's specific window directly. The fill
        # alone (subdivision=0.5 over 1 bar) would produce exactly 8 evenly
        # spaced onsets there; trap_hats' base_subdivision=0.25 alone
        # produces at least 16 in the same window. A count clearly above 8
        # in that window demonstrates trap_hats' continuous texture won,
        # not the fill's coarser fixed spacing.
        hits = generate_drums(
            32.0, [], pattern="four_on_floor", density="full", seed=42,
            fill={"placement": "phrase_end", "phrase_bars": 8, "bars": 1,
                  "instrument": "hi_hat", "subdivision": 0.5, "probability": 1.0},
            trap_hats={"base_subdivision": 0.25},
        )
        fill_bar_hats = [h for h in hits
                         if h.midi_note in (DRUM_KIT["hi_hat"], DRUM_KIT["hi_hat_open"])
                         and 28.0 <= h.start_beat < 32.0]
        assert len(fill_bar_hats) > 8

    def test_deterministic_end_to_end(self):
        kwargs = dict(
            total_beats=32.0, bass_notes=[], pattern="four_on_floor", density="full", seed=9,
            trap_hats={"base_subdivision": 0.25, "burst_probability": 0.3},
        )
        assert generate_drums(**kwargs) == generate_drums(**kwargs)

    def test_coexists_with_accelerando_on_a_different_instrument(self):
        hits = generate_drums(
            64.0, [], pattern="four_on_floor", density="full", seed=42,
            trap_hats={"base_subdivision": 0.25},
            accelerando={"placement": "section_end", "bars": 4, "instrument": "snare",
                         "probability": 1.0},
        )
        assert any(h.midi_note in (DRUM_KIT["hi_hat"], DRUM_KIT["hi_hat_open"]) for h in hits)
        assert any(h.midi_note == DRUM_KIT["snare"] for h in hits)
        assert any(h.midi_note == DRUM_KIT["kick"] for h in hits)
