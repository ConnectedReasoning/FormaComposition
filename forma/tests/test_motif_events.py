"""
Tests for the motif `events` authoring form:

    "events": [ {"step": 0, "beats": 1.5, "velocity": 1.0}, {"step": 2, "beats": 0.5, "rest": true}, ... ]

which must behave exactly like the legacy parallel intervals / rhythm /
velocities / rests arrays (it normalizes to them), on every path a motif can
take: piece `motif` / `motifs`, `bass_motif`, the library loader. Plus the
migrate_to_motif_events.py rewriter.
"""
import json
import sys
from pathlib import Path

import pytest
from pydantic import ValidationError

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import migrate_to_motif_events as mig
import slop_metrics
from intervals.core.generator import generate_piece
from intervals.core.motif_loader import (
    load_motif, resolve_motif_pool_from_theme, resolve_motif_value,
)
from intervals.core.schemas import MotifModel, PieceModel, SectionModel
from intervals.music.motif import expand_motif_events, from_dict, normalize_motif_dict, to_dict

EVENTS = [
    {"step":  0, "beats": 1.5, "velocity": 1.0},
    {"step":  2, "beats": 0.5, "velocity": 0.8},
    {"step": -2, "beats": 1.0, "velocity": 0.9, "rest": True},
    {"step":  1, "beats": 1.0, "velocity": 0.8},
]
LEGACY = {
    "intervals":  [0, 2, -2, 1],
    "rhythm":     [1.5, 0.5, 1.0, 1.0],
    "velocities": [1.0, 0.8, 0.9, 0.8],
    "rests":      [False, False, True, False],
}


# ── Expansion ────────────────────────────────────────────────────────────────

class TestExpand:
    def test_matches_legacy_arrays(self):
        assert expand_motif_events(EVENTS) == LEGACY

    def test_step_only(self):
        assert expand_motif_events([{"step": 1}, {"step": -1}]) == {"intervals": [1, -1]}

    def test_step_defaults_to_zero(self):
        assert expand_motif_events([{"beats": 1}, {"beats": 2}]) == {
            "intervals": [0, 0], "rhythm": [1, 2]}

    def test_no_rest_key_means_no_rests_array(self):
        assert "rests" not in expand_motif_events([{"step": 0, "beats": 1}])

    def test_rest_mentioned_once_makes_a_full_rests_array(self):
        out = expand_motif_events([{"step": 0, "beats": 1, "rest": False}, {"step": 1, "beats": 1}])
        assert out["rests"] == [False, False]

    def test_integral_float_step_is_accepted(self):
        assert expand_motif_events([{"step": 2.0}])["intervals"] == [2]

    def test_normalize_leaves_legacy_dicts_untouched(self):
        d = {"intervals": [0, 1], "rhythm": [1, 1]}
        assert normalize_motif_dict(d) is d
        assert normalize_motif_dict("rebecca") == "rebecca"

    def test_normalize_keeps_other_keys_and_drops_events(self):
        out = normalize_motif_dict({"name": "m", "transform_pool": ["inversion"],
                                    "melodic_scale": "blues", "events": EVENTS})
        assert out["name"] == "m" and out["transform_pool"] == ["inversion"]
        assert out["melodic_scale"] == "blues"
        assert "events" not in out
        assert {k: out[k] for k in LEGACY} == LEGACY


# ── Errors ───────────────────────────────────────────────────────────────────

class TestErrors:
    def test_events_plus_legacy_key_is_an_error(self):
        with pytest.raises(ValueError, match="use one or the other"):
            normalize_motif_dict({"events": EVENTS, "rhythm": [1, 1, 1, 1]})

    @pytest.mark.parametrize("bad", [[], {}, "x", None])
    def test_not_a_non_empty_list(self, bad):
        with pytest.raises(ValueError, match="non-empty list"):
            expand_motif_events(bad)

    def test_bare_number_entry_points_at_the_expected_shape(self):
        with pytest.raises(ValueError, match=r"events\[1\].*object"):
            expand_motif_events([{"step": 0}, 2])

    def test_unknown_key_is_rejected_not_ignored(self):
        with pytest.raises(ValueError, match=r"events\[0\].*unknown"):
            expand_motif_events([{"step": 0, "duration": 1}])

    @pytest.mark.parametrize("bad", [1.5, "up", True, None])
    def test_bad_step(self, bad):
        with pytest.raises(ValueError, match=r"events\[0\] \(step\)"):
            expand_motif_events([{"step": bad}])

    @pytest.mark.parametrize("bad", [0, -1, "long", True])
    def test_bad_beats(self, bad):
        with pytest.raises(ValueError, match=r"events\[0\] \(beats\)"):
            expand_motif_events([{"step": 0, "beats": bad}])

    def test_bad_rest(self):
        with pytest.raises(ValueError, match=r"events\[0\] \(rest\)"):
            expand_motif_events([{"step": 0, "beats": 1, "rest": 1}])

    def test_beats_on_some_entries_but_not_all(self):
        with pytest.raises(ValueError, match=r"'beats'.*missing on \[1\]"):
            expand_motif_events([{"step": 0, "beats": 1}, {"step": 1}])

    def test_velocity_on_some_entries_but_not_all(self):
        with pytest.raises(ValueError, match=r"'velocity'.*missing on \[0\]"):
            expand_motif_events([{"step": 0, "beats": 1}, {"step": 1, "beats": 1, "velocity": 0.5}])

    def test_velocity_range_is_still_checked_by_the_model(self):
        with pytest.raises(ValidationError, match="0.0-1.0"):
            MotifModel.model_validate({"name": "m", "events": [
                {"step": 0, "beats": 1, "velocity": 90}]})

    def test_error_surfaces_through_the_model(self):
        with pytest.raises(ValidationError, match=r"events\[1\]"):
            MotifModel.model_validate({"events": [{"step": 0}, "x"]})


# ── Same result on every path ────────────────────────────────────────────────

class TestEquivalence:
    def test_motif_model_matches_legacy_field_for_field(self):
        new = MotifModel.model_validate({"name": "m", "events": EVENTS,
                                         "transform_pool": ["original", "sequence"]})
        old = MotifModel.model_validate({"name": "m", **LEGACY,
                                         "transform_pool": ["original", "sequence"]})
        assert new.model_dump() == old.model_dump()
        assert "events" not in new.model_dump()
        assert not (new.model_extra or {}).get("events")

    def test_from_dict_matches_legacy(self):
        new = to_dict(from_dict({"name": "m", "events": EVENTS}))
        old = to_dict(from_dict({"name": "m", **LEGACY}))
        assert new == old

    def test_resolve_motif_value_embedded_dict(self):
        new = resolve_motif_value({"name": "m", "events": EVENTS})
        assert (new.intervals, new.rhythm, new.rests) == (
            LEGACY["intervals"], LEGACY["rhythm"], LEGACY["rests"])

    def test_inline_pool_name_reference_resolves(self):
        pool = [{"name": "riff", "events": EVENTS}]
        m = resolve_motif_value("riff", theme_pool=pool)
        assert m.intervals == LEGACY["intervals"]

    def test_theme_motif_pool_hands_downstream_the_legacy_shape(self):
        # generator / strategies read pool entries as raw dicts (.get("rhythm"))
        pool = resolve_motif_pool_from_theme({"motifs": [{"name": "a", "events": EVENTS}]})
        assert pool[0]["rhythm"] == LEGACY["rhythm"]
        assert pool[0]["velocities"] == LEGACY["velocities"]
        assert "events" not in pool[0]

    def test_library_file_with_events(self, tmp_path):
        (tmp_path / "motif_riff.json").write_text(json.dumps(
            {"motif": {"name": "riff", "events": EVENTS}}))
        assert load_motif("riff", str(tmp_path)).rests == LEGACY["rests"]

    def test_library_file_without_intervals_or_events_still_fails(self, tmp_path):
        (tmp_path / "motif_bad.json").write_text(json.dumps({"motif": {"name": "bad"}}))
        with pytest.raises(ValueError, match="missing 'intervals'"):
            load_motif("bad", str(tmp_path))

    def test_slop_metrics_sees_an_events_only_motif(self):
        assert slop_metrics.has_motif({"motif": {"name": "m", "events": EVENTS}})
        assert not slop_metrics.has_motif({"motif": {"name": "m"}})


# ── bass_motif (a plain dict that never builds a MotifModel) ─────────────────

BASS_EVENTS = [{"step": -4, "beats": 0.5}, {"step": 4, "beats": 0.5},
               {"step": -2, "beats": 0.5}, {"step": 2, "beats": 0.5}] * 2
BASS_LEGACY = {"intervals": [-4, 4, -2, 2] * 2, "rhythm": [0.5] * 8}


def _section(**over):
    base = {"name": "a", "rhythm": "free", "bars": 2, "progression": ["I", "IV"],
            "bass_style": "motif"}
    base.update(over)
    return base


class TestBassMotif:
    def test_validates_with_events(self):
        SectionModel.model_validate(_section(bass_motif={"name": "alb", "events": BASS_EVENTS}))

    @pytest.mark.parametrize("bass_motif", [
        {"name": "alb", "events": [{"step": 0}, {"step": 1}]},       # events, no beats
        {"name": "alb", "intervals": [0, 1]},                         # legacy, no rhythm
    ])
    def test_motif_without_rhythm_fails_the_same_way_in_both_forms(self, bass_motif):
        piece = PieceModel.model_validate(_piece({"motif": {"name": "head", **MOTIF_LEGACY}}, bass_motif))
        with pytest.raises(ValueError, match="needs both"):
            piece.validate_against_theme(piece)

    def test_events_bass_motif_passes_the_cross_check(self):
        piece = PieceModel.model_validate(_piece({"motif": {"name": "head", **MOTIF_LEGACY}},
                                                 {"name": "alb", "events": BASS_EVENTS}))
        piece.validate_against_theme(piece)

    def test_bass_riff_resolves_to_the_same_motif(self):
        new = resolve_motif_value({"name": "alb", "events": BASS_EVENTS})
        old = resolve_motif_value({"name": "alb", **BASS_LEGACY})
        assert to_dict(new) == to_dict(old)


# ── Whole-piece behavior ─────────────────────────────────────────────────────

def _piece(motif_block, bass_motif):
    sec = _section(rhythm="motif", bass_motif=bass_motif)
    return {
        "key": "C", "mode": "ionian", "tempo": {"min": 100, "max": 100}, "seed": 7,
        "form_type": "song", "form": ["a"], "sections": {"a": sec},
        **motif_block,
    }


def _render(piece, path):
    generate_piece(piece, str(path))
    return path.read_bytes()


MOTIF_EVENTS = [{"step": 0, "beats": 1.0, "velocity": 1.0}, {"step": 2, "beats": 1.0, "velocity": 0.7},
                {"step": -1, "beats": 1.0, "velocity": 0.8}, {"step": -1, "beats": 1.0, "velocity": 0.6}]
MOTIF_LEGACY = {"intervals": [0, 2, -1, -1], "rhythm": [1.0] * 4, "velocities": [1.0, 0.7, 0.8, 0.6]}


@pytest.mark.parametrize("form", ["motif", "motifs"])
def test_piece_renders_identical_midi_to_legacy(tmp_path, form):
    def block(body):
        m = {"name": "head", **body, "transform_pool": ["original"]}
        return {"motif": m} if form == "motif" else {"motifs": [m]}

    old = _piece(block(MOTIF_LEGACY), {"name": "alb", **BASS_LEGACY})
    new = _piece(block({"events": MOTIF_EVENTS}), {"name": "alb", "events": BASS_EVENTS})
    assert _render(old, tmp_path / "old.mid") == _render(new, tmp_path / "new.mid")


# ── migrate_to_motif_events.py ───────────────────────────────────────────────

LEGACY_TEXT = """{
  "piece": {
    "key": "C",
    "mode": "ionian",
    "tempo": 100,
    "form_type": "song",
    "form": ["a"],
    "motif": {
      "name": "head",
      "intervals":  [ 0,   2,   -2,  1 ],
      "rhythm":     [ 1.5, 0.5, 1.0, 1.0 ],
      "velocities": [ 1.0, 0.8, 0.9, 0.8 ],
      "rests":      [ false, false, true, false ],
      "transform_pool": ["original"]
    },
    "sections": {
      "a": {
        "name": "a",
        "rhythm": "motif",
        "bars": 2,
        "progression": ["I", "IV"],
        "bass_style": "motif",
        "bass_motif": {
          "name": "alb",
          "intervals": [-4, 4, -2, 2, -4, 4, -2, 2],
          "rhythm": [0.5, 0.5, 0.5, 0.5, 0.5, 0.5, 0.5, 0.5]
        }
      }
    }
  }
}
"""


class TestMigrator:
    def test_migrates_every_motif_and_verifies(self):
        new, notes = mig.migrate_text(LEGACY_TEXT)
        assert notes == []
        assert mig.verify(LEGACY_TEXT, new) is None
        data = json.loads(new)["piece"]
        assert len(data["motif"]["events"]) == 4
        assert len(data["sections"]["a"]["bass_motif"]["events"]) == 8
        for gone in ("intervals", "rhythm", "velocities", "rests"):
            assert gone not in data["motif"]
            assert gone not in data["sections"]["a"]["bass_motif"]

    def test_expanded_events_equal_the_original_arrays(self):
        new, _ = mig.migrate_text(LEGACY_TEXT)
        m = json.loads(new)["piece"]["motif"]
        got = normalize_motif_dict(m)
        assert {k: got[k] for k in LEGACY} == LEGACY

    def test_rest_slot_keeps_its_step(self):
        new, _ = mig.migrate_text(LEGACY_TEXT)
        ev = json.loads(new)["piece"]["motif"]["events"]
        assert ev[2] == {"step": -2, "beats": 1.0, "velocity": 0.9, "rest": True}

    def test_idempotent(self):
        once, _ = mig.migrate_text(LEGACY_TEXT)
        twice, _ = mig.migrate_text(once)
        assert twice == once

    def test_untouched_bytes_stay_untouched(self):
        new, _ = mig.migrate_text(LEGACY_TEXT)
        for line in ('"name": "head",', '"transform_pool": ["original"]',
                     '"progression": ["I", "IV"],', '"form": ["a"],'):
            assert line in new

    def test_rows_are_column_aligned(self):
        new, _ = mig.migrate_text(LEGACY_TEXT)
        rows = [l for l in new.splitlines() if '"step"' in l and '"velocity"' in l]
        assert len(rows) == 4
        assert len({l.index('"beats"') for l in rows}) == 1
        assert len({l.index('"velocity"') for l in rows}) == 1
        assert len({len(l.rstrip(",")) for l in rows}) == 1        # closing braces line up

    def test_migrated_piece_renders_identical_midi(self, tmp_path):
        new, _ = mig.migrate_text(LEGACY_TEXT)
        a = _render(json.loads(LEGACY_TEXT)["piece"], tmp_path / "a.mid")
        b = _render(json.loads(new)["piece"], tmp_path / "b.mid")
        assert a == b

    def test_explicit_all_false_rests_survive(self):
        text = '{"motif": {"intervals": [0, 1], "rhythm": [1, 1], "rests": [false, false]}}'
        new, _ = mig.migrate_text(text)
        assert mig.verify(text, new) is None
        assert normalize_motif_dict(json.loads(new)["motif"])["rests"] == [False, False]

    def test_intervals_only_motif(self):
        text = '{"motif": {"name": "m", "intervals": [0, 2, -1]}}'
        new, _ = mig.migrate_text(text)
        assert mig.verify(text, new) is None
        assert json.loads(new)["motif"]["events"] == [{"step": 0}, {"step": 2}, {"step": -1}]

    def test_compact_json(self):
        text = '{"motif":{"name":"m","intervals":[0,2],"rhythm":[1,2]}}'
        new, _ = mig.migrate_text(text)
        assert mig.verify(text, new) is None
        assert json.loads(new)["motif"]["events"] == [
            {"step": 0, "beats": 1.0}, {"step": 2, "beats": 2.0}]

    def test_library_motif_file_that_is_not_a_piece(self):
        text = '{"motif": {"name": "riff", "intervals": [0, 2], "rhythm": [1.0, 1.0]}}'
        new, _ = mig.migrate_text(text)
        assert mig.verify(text, new) is None

    def test_length_mismatch_is_skipped_and_reported(self):
        text = '{"motif": {"intervals": [0, 2, 1], "rhythm": [1, 1]}}'
        new, notes = mig.migrate_text(text)
        assert new == text
        assert notes and "do not match" in notes[0]

    def test_verify_catches_a_bad_rewrite(self):
        new, _ = mig.migrate_text(LEGACY_TEXT)
        broken = new.replace('"step":  0, "beats": 1.5', '"step":  1, "beats": 1.5')
        assert mig.verify(LEGACY_TEXT, broken) is not None

    def test_cli_dry_run_writes_nothing(self, tmp_path, capsys):
        p = tmp_path / "p.json"
        p.write_text(LEGACY_TEXT)
        assert mig.main([str(p), "--dry-run"]) == 0
        assert p.read_text() == LEGACY_TEXT
        assert "would migrate" in capsys.readouterr().out

    def test_cli_in_place_writes_a_backup(self, tmp_path):
        p = tmp_path / "p.json"
        p.write_text(LEGACY_TEXT)
        assert mig.main([str(p)]) == 0
        assert (tmp_path / "p.json.bak").read_text() == LEGACY_TEXT
        assert "events" in p.read_text()
