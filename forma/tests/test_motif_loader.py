"""
Tests for intervals.core.motif_loader — the motif library and pool
resolution layer. Uses pytest's tmp_path for filesystem isolation; no
test touches the real compositions/motifs directory.
"""
import json

import pytest

from intervals.core.motif_loader import (
    list_available_motifs,
    load_motif,
    resolve_motif_from_theme,
    resolve_motif_pool_from_theme,
    resolve_motif_value,
    save_motif,
)
from intervals.music.motif import Motif


def _write_motif_file(directory, name, motif_dict, wrapped=True):
    payload = {"motif": motif_dict} if wrapped else motif_dict
    path = directory / f"motif_{name}.json"
    path.write_text(json.dumps(payload))
    return path


# ===========================================================================
# load_motif
# ===========================================================================

class TestLoadMotif:
    def test_loads_wrapped_motif_file(self, tmp_path):
        _write_motif_file(tmp_path, "rebecca", {
            "name": "rebecca", "intervals": [2, -1, 3, -2], "rhythm": [1, 0.5, 0.5, 1],
        })
        m = load_motif("rebecca", motifs_dir=str(tmp_path))
        assert m.intervals == [2, -1, 3, -2]
        assert m.name == "rebecca"

    def test_loads_unwrapped_flat_motif_file(self, tmp_path):
        """The 'motif' key wrapper is optional -- a flat dict is accepted too."""
        _write_motif_file(tmp_path, "flat", {"intervals": [1, 1, 1], "rhythm": [1, 1, 1]},
                           wrapped=False)
        m = load_motif("flat", motifs_dir=str(tmp_path))
        assert m.intervals == [1, 1, 1]

    def test_missing_file_raises_with_available_motifs_listed(self, tmp_path):
        _write_motif_file(tmp_path, "rebecca", {"intervals": [1], "rhythm": [1]})
        with pytest.raises(FileNotFoundError, match="Available motifs"):
            load_motif("nope", motifs_dir=str(tmp_path))

    def test_malformed_motif_missing_intervals_raises_value_error(self, tmp_path):
        _write_motif_file(tmp_path, "broken", {"rhythm": [1, 1]})
        with pytest.raises(ValueError, match="missing 'intervals' key"):
            load_motif("broken", motifs_dir=str(tmp_path))

    def test_malformed_json_syntax_raises(self, tmp_path):
        path = tmp_path / "motif_bad_syntax.json"
        path.write_text("{not valid json")
        with pytest.raises(json.JSONDecodeError):
            load_motif("bad_syntax", motifs_dir=str(tmp_path))


# ===========================================================================
# list_available_motifs
# ===========================================================================

class TestListAvailableMotifs:
    def test_lists_names_without_prefix_or_extension(self, tmp_path):
        _write_motif_file(tmp_path, "alpha", {"intervals": [1], "rhythm": [1]})
        _write_motif_file(tmp_path, "beta", {"intervals": [2], "rhythm": [1]})
        assert sorted(list_available_motifs(str(tmp_path))) == ["alpha", "beta"]

    def test_ignores_non_motif_files(self, tmp_path):
        _write_motif_file(tmp_path, "alpha", {"intervals": [1], "rhythm": [1]})
        (tmp_path / "readme.txt").write_text("not a motif")
        (tmp_path / "theme_something.json").write_text("{}")
        assert list_available_motifs(str(tmp_path)) == ["alpha"]

    def test_nonexistent_directory_returns_empty_list(self, tmp_path):
        assert list_available_motifs(str(tmp_path / "does_not_exist")) == []

    def test_empty_directory_returns_empty_list(self, tmp_path):
        assert list_available_motifs(str(tmp_path)) == []


# ===========================================================================
# save_motif
# ===========================================================================

class TestSaveMotif:
    def test_round_trips_through_save_and_load(self, tmp_path):
        original = Motif(intervals=[1, 2, 3], rhythm=[1, 1, 1], name="saved_one")
        path = save_motif(original, motifs_dir=str(tmp_path))
        assert path.endswith("motif_saved_one.json")

        reloaded = load_motif("saved_one", motifs_dir=str(tmp_path))
        assert reloaded.intervals == original.intervals
        assert reloaded.rhythm == original.rhythm

    def test_wraps_output_in_motif_key(self, tmp_path):
        save_motif(Motif(intervals=[1], rhythm=[1], name="wrapped_check"),
                   motifs_dir=str(tmp_path))
        raw = json.loads((tmp_path / "motif_wrapped_check.json").read_text())
        assert "motif" in raw
        assert raw["motif"]["intervals"] == [1]

    def test_creates_directory_if_missing(self, tmp_path):
        target = tmp_path / "nested" / "motifs"
        save_motif(Motif(intervals=[1], rhythm=[1], name="x"), motifs_dir=str(target))
        assert (target / "motif_x.json").exists()


# ===========================================================================
# resolve_motif_value
# ===========================================================================

class TestResolveMotifValue:
    def test_none_returns_none(self):
        assert resolve_motif_value(None) is None

    def test_embedded_dict_resolves_directly(self):
        result = resolve_motif_value({"intervals": [9, 9], "rhythm": [1, 1]})
        assert result.intervals == [9, 9]

    def test_string_resolves_against_theme_pool_first(self):
        pool = [{"name": "poolmotif", "intervals": [5, 5], "rhythm": [1, 1]}]
        result = resolve_motif_value("poolmotif", theme_pool=pool)
        assert result.intervals == [5, 5]

    def test_string_not_in_pool_falls_through_to_library(self, tmp_path):
        _write_motif_file(tmp_path, "rebecca", {"intervals": [2, -1], "rhythm": [1, 1]})
        pool = [{"name": "poolmotif", "intervals": [5, 5], "rhythm": [1, 1]}]
        result = resolve_motif_value("rebecca", motifs_dir=str(tmp_path), theme_pool=pool)
        assert result.intervals == [2, -1]

    def test_string_not_found_anywhere_raises_and_lists_pool_names(self, tmp_path):
        pool = [{"name": "poolmotif", "intervals": [5, 5], "rhythm": [1, 1]}]
        with pytest.raises(FileNotFoundError, match="Inline theme motifs available"):
            resolve_motif_value("totally_missing", motifs_dir=str(tmp_path), theme_pool=pool)

    def test_string_not_found_no_pool_raises_plain_error(self, tmp_path):
        with pytest.raises(FileNotFoundError) as exc_info:
            resolve_motif_value("totally_missing", motifs_dir=str(tmp_path))
        assert "Inline theme motifs" not in str(exc_info.value)

    def test_invalid_type_raises_type_error(self):
        with pytest.raises(TypeError, match="must be a string.*or dict"):
            resolve_motif_value(42)


# ===========================================================================
# resolve_motif_from_theme
# ===========================================================================

class TestResolveMotifFromTheme:
    def test_embedded_motif_resolves(self):
        theme = {"motif": {"intervals": [3, 3], "rhythm": [1, 1]}}
        result = resolve_motif_from_theme(theme)
        assert result.intervals == [3, 3]

    def test_no_motif_key_returns_none(self):
        assert resolve_motif_from_theme({}) is None

    def test_string_reference_resolves_from_library(self, tmp_path):
        _write_motif_file(tmp_path, "rebecca", {"intervals": [2, -1], "rhythm": [1, 1]})
        theme = {"motif": "rebecca"}
        result = resolve_motif_from_theme(theme, motifs_dir=str(tmp_path))
        assert result.intervals == [2, -1]


# ===========================================================================
# resolve_motif_pool_from_theme
# ===========================================================================

class TestResolveMotifPoolFromTheme:
    def test_motifs_array_of_dicts_returned_as_is(self):
        theme = {"motifs": [
            {"name": "a", "intervals": [1, 1], "rhythm": [1, 1]},
            {"name": "b", "intervals": [2, 2], "rhythm": [1, 1]},
        ]}
        pool = resolve_motif_pool_from_theme(theme)
        assert [m["name"] for m in pool] == ["a", "b"]

    def test_motifs_array_of_strings_loaded_from_library(self, tmp_path):
        _write_motif_file(tmp_path, "rebecca", {
            "name": "rebecca", "intervals": [2, -1], "rhythm": [1, 1],
        })
        theme = {"motifs": ["rebecca"]}
        pool = resolve_motif_pool_from_theme(theme, motifs_dir=str(tmp_path))
        assert len(pool) == 1
        assert pool[0]["name"] == "rebecca"
        assert pool[0]["intervals"] == [2, -1]

    def test_falls_back_to_single_motif_as_one_element_pool(self):
        theme = {"motif": {"intervals": [7, 7], "rhythm": [1, 1]}}
        pool = resolve_motif_pool_from_theme(theme)
        assert len(pool) == 1
        assert pool[0]["intervals"] == [7, 7]

    def test_no_motif_defined_returns_empty_list(self):
        assert resolve_motif_pool_from_theme({}) == []

    def test_motifs_array_takes_precedence_over_single_motif(self):
        theme = {
            "motif": {"intervals": [7, 7], "rhythm": [1, 1]},
            "motifs": [{"name": "a", "intervals": [1, 1], "rhythm": [1, 1]}],
        }
        pool = resolve_motif_pool_from_theme(theme)
        assert len(pool) == 1
        assert pool[0]["name"] == "a"
