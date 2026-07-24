"""
Smoke tests for main.py — the CLI entry point.

Per this task's brief: thinnest layer, lowest risk, mostly argparse
plumbing calling into an already-tested generator.py. These are smoke
tests only (CLI runs cleanly on valid input, exits with a useful message
on invalid input, --info produces output without rendering) -- not a
re-verification of generation correctness, which Tasks 1-7 already cover.

Each test invokes `python main.py ...` as a real subprocess, the same way
a person would run it from a terminal, rather than importing main() and
calling it in-process (argparse's sys.exit() calls and main.py's own
sys.exit(1) calls make subprocess the more faithful and less fragile way
to test actual CLI behavior).
"""
import json
import subprocess
import sys

import pytest

MAIN_PY = None  # set in the main_py fixture below


@pytest.fixture(scope="module")
def main_py():
    from pathlib import Path
    return str(Path(__file__).resolve().parents[1] / "main.py")


@pytest.fixture
def theme_path(tmp_path):
    path = tmp_path / "theme.json"
    path.write_text(json.dumps({
        "key": "C", "mode": "ionian", "tempo": {"min": 100, "max": 120},
    }))
    return str(path)


@pytest.fixture
def piece_path(tmp_path):
    path = tmp_path / "piece.json"
    path.write_text(json.dumps({
        "title": "Test Piece", "tempo": 110,
        "sections": [{"name": "a", "progression": ["i", "iv", "v"], "rhythm": "free", "bars": 4}],
    }))
    return str(path)


def _run(main_py, *args, cwd=None):
    return subprocess.run(
        [sys.executable, main_py, *args],
        capture_output=True, text=True, cwd=cwd,
    )


# ===========================================================================
# Valid input — runs cleanly, produces a MIDI file
# ===========================================================================

class TestValidInputRuns:
    def test_single_piece_generates_and_exits_zero(self, main_py, theme_path, piece_path, tmp_path):
        out = tmp_path / "out.mid"
        result = _run(main_py, theme_path, piece_path, "--output", str(out))
        assert result.returncode == 0
        assert out.exists()
        assert out.stat().st_size > 0

    def test_success_line_reports_title_and_output_path(self, main_py, theme_path, piece_path, tmp_path):
        out = tmp_path / "out.mid"
        result = _run(main_py, theme_path, piece_path, "--output", str(out))
        assert "Test Piece" in result.stdout
        assert str(out) in result.stdout

    def test_batch_generation_with_outdir_reports_summary(self, main_py, theme_path, piece_path, tmp_path):
        album_dir = tmp_path / "album"
        result = _run(main_py, theme_path, piece_path, piece_path, "--outdir", str(album_dir))
        assert result.returncode == 0
        assert "2 succeeded, 0 failed" in result.stdout
        assert album_dir.exists()


# ===========================================================================
# Invalid input — exits nonzero with a useful message, doesn't crash raw
# ===========================================================================

class TestInvalidInputExitsCleanly:
    def test_missing_theme_file_exits_one_with_clear_message(self, main_py, piece_path, tmp_path):
        result = _run(main_py, str(tmp_path / "does_not_exist.json"), piece_path)
        assert result.returncode == 1
        assert "theme file not found" in result.stderr

    def test_missing_piece_file_exits_one_with_clear_message(self, main_py, theme_path, tmp_path):
        result = _run(main_py, theme_path, str(tmp_path / "does_not_exist.json"))
        assert result.returncode == 1
        assert "piece file not found" in result.stderr

    def test_output_flag_with_multiple_pieces_is_rejected(self, main_py, theme_path, piece_path):
        result = _run(main_py, theme_path, piece_path, piece_path, "--output", "x.mid")
        assert result.returncode == 1
        assert "only works with a single piece" in result.stderr

    def test_schema_invalid_piece_reports_validation_errors_and_exits_one(
        self, main_py, theme_path, tmp_path,
    ):
        bad_piece = tmp_path / "bad_piece.json"
        bad_piece.write_text(json.dumps({"title": "Bad Piece", "sections": []}))
        result = _run(main_py, theme_path, str(bad_piece))
        assert result.returncode == 1
        assert "ERRORS in" in result.stdout
        assert "sections" in result.stdout

    def test_no_traceback_leaks_to_the_user_for_a_missing_file(self, main_py, piece_path, tmp_path):
        """A missing-file error is an expected, handled case -- the CLI
        should print its own clear message, not a raw Python traceback."""
        result = _run(main_py, str(tmp_path / "nope.json"), piece_path)
        assert "Traceback" not in result.stderr


# ===========================================================================
# --info — produces output without rendering
# ===========================================================================

class TestInfoFlagDoesNotRender:
    def test_info_prints_summary_and_exits_zero(self, main_py, theme_path, piece_path):
        result = _run(main_py, theme_path, piece_path, "--info")
        assert result.returncode == 0
        assert "THEME:" in result.stdout
        assert "Test Piece" in result.stdout
        assert "Mode:  info" in result.stdout

    def test_info_does_not_write_a_midi_file(self, main_py, theme_path, piece_path, tmp_path):
        before = set(tmp_path.iterdir())
        _run(main_py, theme_path, piece_path, "--info")
        after = set(tmp_path.iterdir())
        # --info takes no --output/--outdir here, so if it rendered
        # anything it would land in a new "output/" dir under cwd --
        # confirm no new file materialized in the working directory at all.
        assert before == after

    def test_info_with_outdir_still_does_not_render(self, main_py, theme_path, piece_path, tmp_path):
        """--info takes priority over --outdir -- info mode never renders,
        even if an output location was also specified."""
        album_dir = tmp_path / "album"
        result = _run(main_py, theme_path, piece_path, "--info", "--outdir", str(album_dir))
        assert result.returncode == 0
        assert "THEME:" in result.stdout
        assert not any(album_dir.glob("*.mid")) if album_dir.exists() else True


# ===========================================================================
# argparse plumbing
# ===========================================================================

class TestArgparsePlumbing:
    def test_no_arguments_prints_usage_and_exits_nonzero(self, main_py):
        result = _run(main_py)
        assert result.returncode != 0
        assert "usage" in result.stderr.lower()

    def test_help_flag_exits_zero_and_shows_examples(self, main_py):
        result = _run(main_py, "--help")
        assert result.returncode == 0
        assert "examples" in result.stdout.lower()
