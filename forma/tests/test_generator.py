"""
Reproducibility tests for the seed scheme actually used in generator.py.

The blake2b-based `derive_seed()` function this file used to import was
removed when the seed migration was reverted (the migration audibly
degraded piece character on Broadway Boogie Woogie; the revert to the
original arithmetic was correct -- see project notes). generator.py now
computes each section's seed directly as `base_seed + seed_offset`, where
`seed_offset` is `i * 10` for section i (or the first occurrence's offset,
for exact_repeat song-form entries) -- see the `seed_offsets` block and the
`seed=base_seed + seed_offset` call sites in generate_piece().

Since that's plain integer arithmetic rather than a hash, the cross-process/
PYTHONHASHSEED concern that motivated the old derive_seed tests no longer
applies to a standalone function -- but it's still worth confirming at the
generate_piece() level, since PYTHONHASHSEED affects dict/set iteration
order too, and this piece's generation touches both.

These tests exercise the scheme through the public generate_piece() API
using the shake_v5 fixture, rather than importing a private function that
no longer exists.
"""
import json
import os
import subprocess
import sys
from pathlib import Path

from intervals.core.generator import generate_piece


FIXTURES_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "validation",
)


def _load_shake_theme_and_piece():
    with open(os.path.join(FIXTURES_DIR, "theme_shake_v2.json")) as f:
        theme = json.load(f)["theme"]
    with open(os.path.join(FIXTURES_DIR, "piece_shake_v5.json")) as f:
        piece = json.load(f)["piece"]
    return theme, piece


def _midi_bytes(path):
    with open(path, "rb") as f:
        return f.read()


def test_same_seed_same_process_reproducible(tmp_path):
    """Rendering the same piece dict twice in the same process with the
    same `seed` field must produce byte-identical MIDI."""
    theme, piece = _load_shake_theme_and_piece()

    path_a = generate_piece(theme, piece, str(tmp_path / "a.mid"))
    path_b = generate_piece(theme, piece, str(tmp_path / "b.mid"))

    assert _midi_bytes(path_a) == _midi_bytes(path_b)


def test_same_seed_cross_process_reproducible(tmp_path):
    """base_seed + i*10 is plain integer arithmetic, not a hash -- confirm
    a subprocess with a different PYTHONHASHSEED renders identical MIDI
    bytes to this process."""
    theme_path = os.path.join(FIXTURES_DIR, "theme_shake_v2.json")
    piece_path = os.path.join(FIXTURES_DIR, "piece_shake_v5.json")

    theme, piece = _load_shake_theme_and_piece()
    in_process_path = tmp_path / "in_process.mid"
    generate_piece(theme, piece, str(in_process_path))
    in_process_bytes = _midi_bytes(str(in_process_path))

    repo_root = str(Path(__file__).resolve().parents[1])
    env = dict(os.environ)
    env.pop("PYTHONHASHSEED", None)
    env["PYTHONHASHSEED"] = "999"  # deliberately different from this process
    existing_path = env.get("PYTHONPATH", "")
    env["PYTHONPATH"] = (
        repo_root if not existing_path else f"{repo_root}{os.pathsep}{existing_path}"
    )

    subprocess_out = tmp_path / "subprocess.mid"
    script = (
        "import json\n"
        "from intervals.core.generator import generate_piece\n"
        f"theme = json.load(open({theme_path!r}))['theme']\n"
        f"piece = json.load(open({piece_path!r}))['piece']\n"
        f"generate_piece(theme, piece, {str(subprocess_out)!r})\n"
    )
    subprocess.run(
        [sys.executable, "-c", script],
        capture_output=True,
        text=True,
        check=True,
        env=env,
    )

    assert _midi_bytes(str(subprocess_out)) == in_process_bytes


def test_different_seed_changes_output(tmp_path):
    """Sanity check that `piece["seed"]` actually participates in
    generation -- a different base_seed must not render identical output."""
    theme, piece = _load_shake_theme_and_piece()

    piece_a = dict(piece)
    piece_a["seed"] = 42
    piece_b = dict(piece)
    piece_b["seed"] = 43

    path_a = generate_piece(theme, piece_a, str(tmp_path / "seed42.mid"))
    path_b = generate_piece(theme, piece_b, str(tmp_path / "seed43.mid"))

    assert _midi_bytes(path_a) != _midi_bytes(path_b)
