"""
Test helper: build song-form pieces.

Song form is the engine's only supported form. Most test fixtures are easiest
to write as a plain list of section dicts; ``song_piece`` turns that into the
song-form shape (``form_type``/``form``/``sections`` dict) so every fixture
goes through the same code path as a real piece.

Each section is keyed by its ``name`` (or ``section_<i>`` when unnamed).
Sections with the same name and identical content share one key and appear
twice in ``form``; same-named sections with different content get a numeric
suffix on the key.
"""
import copy
import json


def song_piece(piece: dict) -> dict:
    """Return ``piece`` with its list-style ``sections`` rewritten as song form.

    A piece that is already song form (or has no list of sections) is returned
    unchanged. The input is not mutated.
    """
    p = copy.deepcopy(piece)
    secs = p.get("sections")
    if not isinstance(secs, list) or p.get("form_type") == "song":
        return p
    defs, form = {}, []
    for i, sec in enumerate(secs):
        base = sec.get("name") or f"section_{i}"
        if base in defs and json.dumps(defs[base], sort_keys=True) == json.dumps(sec, sort_keys=True):
            form.append(base)
            continue
        key, n = base, 2
        while key in defs:
            key, n = f"{base}_{n}", n + 1
        defs[key] = sec
        form.append(key)
    p["form_type"] = "song"
    p["form"] = form
    p["sections"] = defs
    return p


def first_section(piece: dict) -> dict:
    """The first section definition in play order of a song-form piece."""
    return piece["sections"][piece["form"][0]]
