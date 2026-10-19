"""migrate_registers: above/below -> named SATB registers, text-preserving."""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import migrate_registers as mr  # noqa: E402


def _piece(voices, **sec):
    return {"sections": [{"name": "a", "voices": voices, **sec}]}


def _run(doc_text):
    new, changes = mr.migrate_text(doc_text)
    return new, changes


def test_below_and_above_a_default_lead():
    text = json.dumps(_piece([{"register": "mid"}, {"register": "below"}, {"register": "above"}]))
    new, _ = _run(text)
    regs = [v["register"] for v in json.loads(new)["sections"][0]["voices"]]
    assert regs == ["mid", "tenor", "soprano"]


def test_unpinned_lead_defaults_to_mid():
    new, _ = _run(json.dumps(_piece([{}, {"register": "below"}])))
    assert json.loads(new)["sections"][0]["voices"][1]["register"] == "tenor"


def test_peers_on_same_side_step_progressively():
    text = json.dumps(_piece([{"register": "soprano"}, {"register": "below"}, {"register": "below"}]))
    new, _ = _run(text)
    regs = [v["register"] for v in json.loads(new)["sections"][0]["voices"]]
    assert regs == ["soprano", "alto", "tenor"]


def test_nothing_above_is_flagged():
    _, changes = _run(json.dumps(_piece([{"register": "high"}, {"register": "above"}])))
    assert changes[0]["new"] == "soprano" and changes[0]["note"]


def test_melody_register_overrides_lead_register():
    text = json.dumps(_piece([{"register": "mid"}, {"register": "below"}],
                             melody_register={"min": 36, "max": 60}))
    new, _ = _run(text)  # lead centre 48 -> nothing clearly below except none
    assert json.loads(new)["sections"][0]["voices"][1]["register"] == "bass"


def test_formatting_preserved_byte_for_byte():
    text = ('{\n  "sections": [{\n    "name": "a",\n'
            '    "voices": [\n      {"register": "mid"},\n'
            '      { "register":  "below", "x": [ 0,  2, -1 ] }\n    ]\n  }]\n}\n')
    new, _ = _run(text)
    assert new == text.replace('"below"', '"tenor"')


def test_idempotent():
    text = json.dumps(_piece([{"register": "mid"}, {"register": "below"}]))
    once, _ = _run(text)
    twice, changes = _run(once)
    assert once == twice and changes == []


def test_non_relative_registers_untouched():
    text = json.dumps(_piece([{"register": "alto"}, {"register": "bass"}]))
    new, changes = _run(text)
    assert new == text and changes == []


def test_text_parse_mismatch_refuses_to_edit():
    import pytest
    text = '{"voices": [{"register": "below"}]}'
    with pytest.raises(ValueError, match="refusing"):   # count mismatch
        mr.apply(text, [])
    with pytest.raises(ValueError, match="refusing"):   # value mismatch
        mr.apply(text, [{"old": "above", "new": "soprano"}])


def test_result_validates_against_current_schema():
    from intervals.core.schemas import VoiceModel
    new, _ = _run(json.dumps(_piece([{"register": "mid"}, {"register": "below", "species": "free"}])))
    for v in json.loads(new)["sections"][0]["voices"]:
        VoiceModel(**v)
