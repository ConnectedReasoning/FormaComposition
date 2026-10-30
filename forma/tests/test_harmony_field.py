"""
Tests for the section-level `harmony` authoring form:

    "harmony": [ {"chord": "I", "bars": 0.5}, {"chord": "II", "bars": 1.5}, ... ]

which must behave exactly like the legacy parallel `progression` + `chord_bars`
arrays (it normalizes to them), plus the migrate_to_harmony.py rewriter.
"""
import json
import subprocess
import sys
import warnings
from pathlib import Path

import pytest
from pydantic import ValidationError

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import migrate_to_harmony
from intervals.core.generator import generate_piece
from intervals.core.schemas import PieceModel, SectionModel, expand_harmony

MAIN_PY = str(Path(__file__).resolve().parents[1] / "main.py")

HARMONY = [
    {"chord": "I", "bars": 0.5},
    {"chord": "II", "bars": 1.5},
    {"chord": "I", "bars": 1.0},
    {"chord": "IV", "bars": 2.0},
]


def section(**over):
    base = {"name": "s", "rhythm": "free"}
    base.update(over)
    return base


def build(**over) -> SectionModel:
    return SectionModel.model_validate(section(**over))


# ── Equivalence with the legacy form ─────────────────────────────────────────

class TestEquivalence:
    def test_matches_legacy_arrays_field_for_field(self):
        new = build(harmony=HARMONY)
        old = build(bars=5, progression=["I", "II", "I", "IV"],
                    chord_bars=[0.5, 1.5, 1, 2])
        assert new.model_dump() == old.model_dump()
        assert new.bars_list() == old.bars_list() == [0.5, 1.5, 1.0, 2.0]
        assert new.resolved_progression() == old.resolved_progression()
        assert new.total_beats() == old.total_beats()

    def test_bars_is_derived_from_the_chords(self):
        assert build(harmony=HARMONY).bars == 5.0

    def test_harmony_key_does_not_leak_into_the_model(self):
        m = build(harmony=HARMONY)
        assert "harmony" not in m.model_dump()
        assert not (m.model_extra or {}).get("harmony")

    def test_section_bars_matching_total_is_accepted_silently(self):
        with warnings.catch_warnings():
            warnings.simplefilter("error")
            build(harmony=HARMONY, bars=5)

    def test_section_bars_disagreeing_with_total_warns_like_chord_bars(self):
        with pytest.warns(UserWarning, match="chord_bars wins"):
            m = build(harmony=HARMONY, bars=4.5)
        assert m.bars == 5.0

    def test_cell_tiles_to_fill_section_bars(self):
        m = build(harmony=[{"chord": "i", "bars": 1}, {"chord": "iv", "bars": 1}], bars=8)
        assert m.resolved_progression() == ["i", "iv"] * 4
        assert m.bars_list() == [1.0, 1.0] * 4

    def test_tiling_with_a_non_dividing_bars_fails_loudly(self):
        with pytest.raises(ValidationError, match="whole multiple"):
            build(harmony=[{"chord": "i", "bars": 1.5}], bars=4)

    def test_tension_clause_comma_is_still_one_chord(self):
        m = build(harmony=[{"chord": "V7(9,13)", "bars": 2}])
        assert m.progression == ["V7(9,13)"]

    def test_chord_without_bars_everywhere_splits_section_bars_evenly(self):
        m = build(harmony=[{"chord": "i"}, {"chord": "iv"}], bars=8)
        assert m.chord_bars is None
        assert m.bars_list() == [4.0, 4.0]


# ── Rejections ───────────────────────────────────────────────────────────────

class TestRejections:
    @pytest.mark.parametrize("legacy", [
        {"progression": ["I"]},
        {"chord_bars": [1]},
        {"progression": ["I"], "chord_bars": [1]},
    ])
    def test_harmony_plus_legacy_keys_is_an_error(self, legacy):
        with pytest.raises(ValidationError, match="use one or the other"):
            build(harmony=[{"chord": "I", "bars": 1}], **legacy)

    def test_empty_harmony(self):
        with pytest.raises(ValidationError, match="non-empty"):
            build(harmony=[])

    def test_not_a_list(self):
        with pytest.raises(ValidationError, match="non-empty list"):
            build(harmony={"chord": "I", "bars": 1})

    def test_bare_string_entry_points_at_the_expected_shape(self):
        with pytest.raises(ValidationError, match=r"harmony\[1\].*object"):
            build(harmony=[{"chord": "I", "bars": 1}, "IV"])

    def test_entry_missing_chord(self):
        with pytest.raises(ValidationError, match=r"harmony\[0\].*chord"):
            build(harmony=[{"bars": 1}])

    def test_unknown_entry_key_is_rejected_not_ignored(self):
        with pytest.raises(ValidationError, match=r"harmony\[0\]"):
            build(harmony=[{"chord": "I", "bars": 1, "length": 2}])

    @pytest.mark.parametrize("bad", [0, -1, "two"])
    def test_bad_bars_value(self, bad):
        with pytest.raises(ValidationError, match=r"harmony\[0\]"):
            build(harmony=[{"chord": "I", "bars": bad}])

    def test_bars_on_some_entries_but_not_all(self):
        with pytest.raises(ValidationError, match=r"missing on \[1\]"):
            build(harmony=[{"chord": "I", "bars": 1}, {"chord": "IV"}])

    def test_expand_harmony_direct(self):
        assert expand_harmony(HARMONY) == (["I", "II", "I", "IV"], [0.5, 1.5, 1.0, 2.0])


# ── Whole-piece behavior ─────────────────────────────────────────────────────

def _piece(sec):
    return {
        "key": "C", "mode": "ionian", "tempo": {"min": 100, "max": 100}, "seed": 7,
        "form_type": "song", "form": ["a"], "sections": {"a": sec},
    }


def test_piece_with_harmony_renders_identical_midi_to_legacy(tmp_path):
    old = section(name="a", bars=5, progression=["I", "II", "I", "IV"],
                  chord_bars=[0.5, 1.5, 1, 2])
    new = section(name="a", harmony=HARMONY)
    p_old, p_new = tmp_path / "old.mid", tmp_path / "new.mid"
    generate_piece(_piece(old), str(p_old))
    generate_piece(_piece(new), str(p_new))
    assert p_old.read_bytes() == p_new.read_bytes()


def test_info_display_shows_harmony_sections(tmp_path):
    path = tmp_path / "p.json"
    path.write_text(json.dumps(_piece(section(name="a", harmony=HARMONY))))
    res = subprocess.run([sys.executable, MAIN_PY, str(path), "--info"],
                         capture_output=True, text=True)
    assert res.returncode == 0, res.stderr
    assert "I(0.5) → II(1.5) → I(1) → IV(2)" in res.stdout
    assert " 5 bars" in res.stdout


# ── migrate_to_harmony.py ────────────────────────────────────────────────────

LEGACY_TEXT = """{
  "piece": {
    "key": "C",
    "mode": "ionian",
    "tempo": 100,
    "form_type": "song",
    "form": ["a", "b"],
    "sections": {
      "a": {
        "name": "a",
        "bars": 5,
        "progression": [ "I", "II", "I", "IV" ],
        "chord_bars": [ 0.5, 1.5, 1, 2 ],
        "rhythm": "free",
        "notes": "has \\"progression\\" and chord_bars: in a string"
      },
      "b": {
        "name": "b",
        "rhythm": "free",
        "bars": 8,
        "progression": [
          "i",
          "iv"
        ],
        "chord_bars": [
          1,
          1
        ]
      }
    }
  }
}
"""


class TestMigrationScript:
    def test_rewrites_to_harmony_and_validates_identically(self):
        new, notes = migrate_to_harmony.migrate_text(LEGACY_TEXT)
        assert notes == []
        data = json.loads(new)["piece"]["sections"]
        assert data["a"]["harmony"] == [
            {"chord": "I", "bars": 0.5}, {"chord": "II", "bars": 1.5},
            {"chord": "I", "bars": 1.0}, {"chord": "IV", "bars": 2.0},
        ]
        assert "progression" not in data["a"] and "chord_bars" not in data["a"]
        assert "bars" not in data["a"]                      # redundant: equals the total
        assert data["b"]["bars"] == 8                       # tiling cell: bars must stay
        assert migrate_to_harmony.verify(LEGACY_TEXT, new) is None

    def test_untouched_bytes_stay_untouched(self):
        new, _ = migrate_to_harmony.migrate_text(LEGACY_TEXT)
        assert '"form": ["a", "b"],' in new                 # inline array not reflowed
        assert 'has \\"progression\\" and chord_bars: in a string' in new

    def test_output_is_one_aligned_object_per_chord(self):
        new, _ = migrate_to_harmony.migrate_text(LEGACY_TEXT)
        assert '{ "chord": "I",  "bars": 0.5 },' in new
        assert '{ "chord": "II", "bars": 1.5 },' in new

    def test_is_idempotent(self):
        once, _ = migrate_to_harmony.migrate_text(LEGACY_TEXT)
        twice, _ = migrate_to_harmony.migrate_text(once)
        assert once == twice

    def test_no_chord_bars_keeps_section_bars_and_omits_entry_bars(self):
        text = '{"key":"C","mode":"ionian","form_type":"song","form":["a"],' \
               '"sections":{"a":{"name":"a","rhythm":"free","bars":8,"progression":["i","iv"]}}}'
        new, _ = migrate_to_harmony.migrate_text(text)
        sec = json.loads(new)["sections"]["a"]
        assert sec["harmony"] == [{"chord": "i"}, {"chord": "iv"}]
        assert sec["bars"] == 8
        assert migrate_to_harmony.verify(text, new) is None

    def test_cli_in_place_writes_backup_and_dry_run_writes_nothing(self, tmp_path):
        f = tmp_path / "piece.json"
        f.write_text(LEGACY_TEXT)
        assert migrate_to_harmony.main([str(f), "--dry-run"]) == 0
        assert f.read_text() == LEGACY_TEXT
        assert migrate_to_harmony.main([str(f)]) == 0
        assert (tmp_path / "piece.json.bak").read_text() == LEGACY_TEXT
        assert '"harmony"' in f.read_text()

    def test_unmigratable_section_is_reported_and_left_alone(self):
        text = '{"sections":{"a":{"progression":["I"],"chord_bars":[1,2]}}}'
        new, notes = migrate_to_harmony.migrate_text(text)
        assert new == text and notes
