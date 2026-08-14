"""
Tests for the multi-bar accelerando mechanism in intervals.music.percussion:
_generate_accelerando_hits and generate_drums()'s `accelerando` kwarg
end-to-end. See _generate_accelerando_hits's docstring for why this is a
genuinely different mechanism from fills, not a bigger version of them.
"""
import pytest

from intervals.music.percussion import (
    DRUM_KIT,
    _generate_accelerando_hits,
    generate_drums,
)


# ===========================================================================
# _generate_accelerando_hits
# ===========================================================================

class TestGenerateAccelerandoHits:
    def test_first_onset_at_group_start(self):
        hits = _generate_accelerando_hits(
            {"instrument": "snare", "subdivision_start": 0.25, "subdivision_end": 0.0625},
            group_start_beat=10.0, span_beats=16.0,
        )
        assert hits[0].start_beat == 10.0

    def test_subdivision_tightens_monotonically_exponential(self):
        hits = _generate_accelerando_hits(
            {"instrument": "snare", "subdivision_start": 0.25, "subdivision_end": 0.0625,
             "curve": "exponential"},
            group_start_beat=0.0, span_beats=16.0,
        )
        gaps = [b - a for a, b in zip(
            [h.start_beat for h in hits], [h.start_beat for h in hits][1:]
        )]
        # Monotonically non-increasing -- each gap is <= the previous one
        assert all(g2 <= g1 + 1e-9 for g1, g2 in zip(gaps, gaps[1:]))
        # Starts near subdivision_start, ends near subdivision_end
        assert gaps[0] == pytest.approx(0.25, abs=0.01)
        assert gaps[-1] < 0.15  # well below the starting gap by the end

    def test_linear_curve_differs_from_exponential(self):
        kwargs = dict(group_start_beat=0.0, span_beats=16.0)
        exp_hits = _generate_accelerando_hits(
            {"instrument": "snare", "subdivision_start": 0.25, "subdivision_end": 0.0625,
             "curve": "exponential"}, **kwargs,
        )
        lin_hits = _generate_accelerando_hits(
            {"instrument": "snare", "subdivision_start": 0.25, "subdivision_end": 0.0625,
             "curve": "linear"}, **kwargs,
        )
        # Different onset counts / positions -- the two curves are not the same shape
        assert [h.start_beat for h in exp_hits] != [h.start_beat for h in lin_hits]

    def test_velocity_ramps_linearly_start_to_end(self):
        hits = _generate_accelerando_hits(
            {"instrument": "snare", "subdivision_start": 0.25, "subdivision_end": 0.0625,
             "velocity_start": 0.2, "velocity_end": 1.0},
            group_start_beat=0.0, span_beats=16.0,
        )
        velocities = [h.velocity for h in hits]
        assert velocities[0] < velocities[-1]
        assert velocities == sorted(velocities)  # monotonic ramp

    def test_landing_is_close_to_but_not_necessarily_exactly_the_span_end(self):
        # Documented approximate-landing tradeoff: last onset should land
        # within one subdivision_end of the span boundary.
        span = 16.0
        hits = _generate_accelerando_hits(
            {"instrument": "snare", "subdivision_start": 0.25, "subdivision_end": 0.0625},
            group_start_beat=0.0, span_beats=span,
        )
        assert span - hits[-1].start_beat < 0.0625 + 0.01

    def test_unknown_instrument_returns_empty(self):
        hits = _generate_accelerando_hits(
            {"instrument": "bogus_instrument"}, group_start_beat=0.0, span_beats=16.0,
        )
        assert hits == []

    def test_all_hits_are_the_requested_instrument(self):
        hits = _generate_accelerando_hits(
            {"instrument": "tom_hi"}, group_start_beat=0.0, span_beats=8.0,
        )
        assert all(h.midi_note == DRUM_KIT["tom_hi"] for h in hits)

    def test_zero_span_does_not_hang(self):
        hits = _generate_accelerando_hits({"instrument": "snare"}, group_start_beat=0.0, span_beats=0.0)
        assert hits == []


# ===========================================================================
# generate_drums — accelerando integration, determinism, regression safety
# ===========================================================================

class TestGenerateDrumsWithAccelerando:
    def test_accelerando_none_matches_omitting_the_kwarg(self):
        a = generate_drums(64.0, [], pattern="four_on_floor", density="full", seed=42)
        b = generate_drums(64.0, [], pattern="four_on_floor", density="full", seed=42, accelerando=None)
        assert a == b

    def test_section_end_roll_lands_in_the_final_bars(self):
        # 64 beats = 16 bars at beats_per_bar=4. bars=4 section_end -> bars 12-15
        # (beats 48-64). The normal pattern still has backbeat snare hits
        # elsewhere in the piece (bars 0-11) -- only the roll WINDOW itself
        # should be dense, not every snare hit in the whole piece.
        hits = generate_drums(
            64.0, [], pattern="four_on_floor", density="full", seed=42,
            accelerando={"placement": "section_end", "bars": 4, "instrument": "snare",
                         "subdivision_start": 0.25, "subdivision_end": 0.0625, "probability": 1.0},
        )
        roll_window_hits = [h for h in hits
                             if h.midi_note == DRUM_KIT["snare"] and 48.0 <= h.start_beat < 64.0]
        assert roll_window_hits, "expected snare roll onsets inside the roll's bars"
        # Should be noticeably denser than a plain backbeat (2 hits across
        # 4 bars) -- a roll tightening toward 64ths packs in far more.
        assert len(roll_window_hits) > 16
        # And no snare hits after the roll's bars end (edge of the section).
        assert not any(h.midi_note == DRUM_KIT["snare"] and h.start_beat >= 64.0 for h in hits)

    def test_probability_zero_produces_no_roll(self):
        with_roll = generate_drums(
            64.0, [], pattern="four_on_floor", density="full", seed=42,
            accelerando={"placement": "section_end", "bars": 4, "instrument": "snare", "probability": 0.0},
        )
        without_roll = generate_drums(64.0, [], pattern="four_on_floor", density="full", seed=42)
        assert with_roll == without_roll

    def test_deterministic_under_fixed_seed(self):
        kwargs = dict(
            total_beats=64.0, bass_notes=[], pattern="four_on_floor", density="full", seed=7,
            accelerando={"placement": "section_end", "bars": 4, "instrument": "snare", "probability": 0.5},
        )
        assert generate_drums(**kwargs) == generate_drums(**kwargs)

    def test_kick_untouched_by_snare_accelerando(self):
        # Same "other instruments keep playing underneath" design as fills.
        no_roll = generate_drums(64.0, [], pattern="four_on_floor", density="full", seed=42)
        with_roll = generate_drums(
            64.0, [], pattern="four_on_floor", density="full", seed=42,
            accelerando={"placement": "section_end", "bars": 4, "instrument": "snare", "probability": 1.0},
        )
        no_roll_kicks = [h.start_beat for h in no_roll if h.midi_note == DRUM_KIT["kick"]]
        with_roll_kicks = [h.start_beat for h in with_roll if h.midi_note == DRUM_KIT["kick"]]
        assert no_roll_kicks == with_roll_kicks

    def test_original_snare_hits_in_roll_bars_are_replaced_not_layered(self):
        hits = generate_drums(
            64.0, [], pattern="four_on_floor", density="full", seed=42,
            accelerando={"placement": "section_end", "bars": 4, "instrument": "snare",
                         "subdivision_start": 0.25, "subdivision_end": 0.0625, "probability": 1.0},
        )
        # four_on_floor's plain backbeat snare hits land on beats 1 and 3 of
        # each bar (fraction .0 at specific offsets) -- with the roll active,
        # those exact plain-pattern positions should be gone, replaced by
        # the roll's own (denser, non-backbeat-aligned) onsets.
        snare_beats = {round(h.start_beat, 6) for h in hits if h.midi_note == DRUM_KIT["snare"]}
        # Sanity: roll onsets present and much denser than 2-per-bar backbeat
        assert len(snare_beats) > 8  # 4 bars * 2 backbeat hits/bar = 8

    def test_fill_and_accelerando_can_coexist_on_different_instruments(self):
        hits = generate_drums(
            64.0, [], pattern="four_on_floor", density="full", seed=42,
            fill={"placement": "phrase_end", "phrase_bars": 8, "bars": 1,
                  "instrument": "hi_hat", "probability": 1.0},
            accelerando={"placement": "section_end", "bars": 4, "instrument": "snare",
                         "probability": 1.0},
        )
        assert any(h.midi_note == DRUM_KIT["hi_hat"] for h in hits)
        assert any(h.midi_note == DRUM_KIT["snare"] for h in hits)
        assert any(h.midi_note == DRUM_KIT["kick"] for h in hits)
