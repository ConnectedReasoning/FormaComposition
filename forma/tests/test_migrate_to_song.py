"""Tests for migrate_to_song.py: narrative (list) pieces -> song form."""
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import migrate_to_song
from intervals.core.generator import generate_piece
from intervals.core.schemas import PieceModel

SECTION_A = '''{
      "name": "a",
      "bars": 4,
      "progression": [ "i",  "iv" ],
      "chord_bars":  [  2,    2  ],
      "rhythm": "free"
    }'''
SECTION_B = '''{
      "name": "b",
      "bars": 4,
      "progression": ["v", "i"],
      "rhythm": "free"
    }'''


def _narrative_text(sections, wrapped=True, form_type=None):
    ft = f'"form_type": "{form_type}",\n    ' if form_type else ""
    inner = f'''{ft}"key": "C",
    "mode": "ionian",
    "tempo": 90,
    "sections": [
    {", ".join(sections)}
    ]'''
    if wrapped:
        return '{\n  "piece": {\n    ' + inner + '\n  }\n}\n'
    return '{\n  ' + inner + '\n}\n'


def _piece(text):
    d = json.loads(text)
    return d.get("piece", d)


class TestConvertText:
    @pytest.mark.parametrize("wrapped", [True, False])
    def test_converts_to_song_form_in_original_order(self, wrapped):
        new, form = migrate_to_song.convert_text(
            _narrative_text([SECTION_A, SECTION_B], wrapped=wrapped))
        p = _piece(new)
        assert p["form_type"] == "song"
        assert p["form"] == form == ["a", "b"]
        assert list(p["sections"]) == ["a", "b"]
        PieceModel.model_validate(json.loads(new))      # passes the real schema

    def test_section_content_unchanged(self):
        old = _piece(_narrative_text([SECTION_A, SECTION_B]))["sections"]
        new = _piece(migrate_to_song.convert_text(_narrative_text([SECTION_A, SECTION_B]))[0])
        assert [new["sections"][k] for k in new["form"]] == old

    def test_formatting_of_sections_is_preserved(self):
        new, _ = migrate_to_song.convert_text(_narrative_text([SECTION_A, SECTION_B]))
        assert '"progression": [ "i",  "iv" ],' in new     # aligned array kept
        assert '"chord_bars":  [  2,    2  ],' in new

    def test_existing_narrative_form_type_is_replaced_not_duplicated(self):
        new, _ = migrate_to_song.convert_text(
            _narrative_text([SECTION_A], form_type="narrative"))
        assert new.count('"form_type"') == 1
        assert _piece(new)["form_type"] == "song"

    def test_identical_same_named_sections_become_one_definition_twice_in_form(self):
        new, form = migrate_to_song.convert_text(
            _narrative_text([SECTION_A, SECTION_B, SECTION_A]))
        p = _piece(new)
        assert form == ["a", "b", "a"]
        assert list(p["sections"]) == ["a", "b"]

    def test_different_same_named_sections_get_suffixed_keys(self):
        other = SECTION_A.replace('"bars": 4', '"bars": 8')
        new, form = migrate_to_song.convert_text(_narrative_text([SECTION_A, other]))
        p = _piece(new)
        assert form == ["a", "a_2"]
        assert p["sections"]["a_2"]["name"] == "a"      # internal name kept
        assert p["sections"]["a_2"]["bars"] == 8

    def test_unnamed_sections_get_positional_keys(self):
        unnamed = SECTION_A.replace('"name": "a",', "")
        new, form = migrate_to_song.convert_text(_narrative_text([unnamed]))
        assert form == ["section_0"]

    def test_sections_sharing_a_line_are_converted(self):
        text = ('{"key": "C", "mode": "ionian", "tempo": 90, "sections": '
                '[{"name": "a", "bars": 4, "progression": ["i"], "rhythm": "free"}, '
                '{"name": "b", "bars": 4, "progression": ["v"], "rhythm": "free"}]}')
        new, form = migrate_to_song.convert_text(text)
        assert form == ["a", "b"]
        PieceModel.model_validate(json.loads(new))

    def test_already_song_form_is_refused(self):
        song = json.dumps({"key": "C", "mode": "ionian", "form_type": "song",
                           "form": ["a"], "sections": {"a": {"bars": 4}}})
        with pytest.raises(ValueError, match="not a narrative piece"):
            migrate_to_song.convert_text(song)

    def test_converted_piece_renders(self, tmp_path):
        new, _ = migrate_to_song.convert_text(_narrative_text([SECTION_A, SECTION_B]))
        out = generate_piece(json.loads(new)["piece"], str(tmp_path / "x.mid"))
        assert Path(out).stat().st_size > 0


class TestCli:
    def test_in_place_conversion_keeps_backup(self, tmp_path):
        f = tmp_path / "p.json"
        original = _narrative_text([SECTION_A, SECTION_B])
        f.write_text(original)
        assert migrate_to_song.main([str(f)]) == 0
        assert _piece(f.read_text())["form_type"] == "song"
        assert (tmp_path / "p.json.bak").read_text() == original

    def test_no_backup_flag(self, tmp_path):
        f = tmp_path / "p.json"
        f.write_text(_narrative_text([SECTION_A]))
        migrate_to_song.main([str(f), "--no-backup"])
        assert not (tmp_path / "p.json.bak").exists()

    def test_dry_run_writes_nothing(self, tmp_path):
        f = tmp_path / "p.json"
        original = _narrative_text([SECTION_A])
        f.write_text(original)
        migrate_to_song.main([str(f), "--dry-run"])
        assert f.read_text() == original
        assert not (tmp_path / "p.json.bak").exists()

    def test_outdir_leaves_source_untouched(self, tmp_path):
        f = tmp_path / "p.json"
        original = _narrative_text([SECTION_A])
        f.write_text(original)
        migrate_to_song.main([str(f), "--outdir", str(tmp_path / "out")])
        assert f.read_text() == original
        assert _piece((tmp_path / "out" / "p.json").read_text())["form_type"] == "song"

    def test_song_form_files_are_skipped_not_failed(self, tmp_path, capsys):
        f = tmp_path / "s.json"
        f.write_text(json.dumps({"key": "C", "mode": "ionian", "form_type": "song",
                                 "form": ["a"], "sections": {"a": {"bars": 4}}}))
        assert migrate_to_song.main([str(f)]) == 0
        assert "skip" in capsys.readouterr().out

    def test_malformed_json_returns_nonzero(self, tmp_path):
        f = tmp_path / "bad.json"
        f.write_text("{ not json")
        assert migrate_to_song.main([str(f)]) == 1
