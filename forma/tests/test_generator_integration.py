"""
Integration tests for intervals.core.generator — the layer that calls
every module verified in Tasks 1-6 and renders a real MIDI file.

Per this task's brief, these tests drive generate_piece() with the real
theme+piece JSON fixtures in validation/ (piece_shake_v5.json /
theme_shake_v2.json, piece_broadway_boogie_v7.json /
theme_broadway_boogie_v3.json) rather than synthetic minimal inputs --
these are the actual pieces in the catalog, exercising real motif pools,
song form with exact_repeat, multiple counterpoint voices, and varied
harmony rhythm sources per section.

The exact_repeat regression test from Task 0 (tests/test_exact_repeat_
regression.py) is imported and re-invoked directly from this suite (see
TestExactRepeatIsPartOfThisSuite below), per this task's explicit
"passing as part of this suite, not standing alone" requirement -- it
remains runnable on its own too, but this suite no longer depends on
that being the only place it's exercised.
"""
import copy
import json
import os

import mido
import pytest

from intervals.core.generator import (
    CHANNEL_BASS,
    CHANNEL_MELODY,
    TRACK_NAME_BASS,
    TRACK_NAME_HARMONY,
    TRACK_NAME_MELODY,
    bpm_to_tempo,
    generate_piece,
    load_piece,
    load_theme,
)

FIXTURES_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "validation",
)


def _fixture_path(name: str) -> str:
    return os.path.join(FIXTURES_DIR, name)


def _load_shake():
    with open(_fixture_path("theme_shake_v2.json")) as f:
        theme = json.load(f)["theme"]
    with open(_fixture_path("piece_shake_v5.json")) as f:
        piece = json.load(f)["piece"]
    return theme, piece


def _load_broadway_boogie():
    with open(_fixture_path("theme_broadway_boogie_v3.json")) as f:
        theme = json.load(f)["theme"]
    with open(_fixture_path("piece_broadway_boogie_v7.json")) as f:
        piece = json.load(f)["piece"]
    return theme, piece


def _midi_bytes(path: str) -> bytes:
    with open(path, "rb") as f:
        return f.read()


# ===========================================================================
# Byte-identical full-render regression
# ===========================================================================

class TestByteIdenticalFullRender:
    @pytest.mark.parametrize("loader", [_load_shake, _load_broadway_boogie],
                             ids=["shake_v5", "broadway_boogie_v7"])
    def test_two_separate_runs_produce_identical_bytes(self, loader, tmp_path):
        """The core regression this task asks for: render each real
        catalog piece twice, as two entirely separate generate_piece()
        calls (fresh MidiFile, fresh RNG seeding from scratch each time),
        and confirm the written .mid files are byte-for-byte identical."""
        theme, piece = loader()
        path_a = generate_piece(theme, piece, str(tmp_path / "run_a.mid"))
        path_b = generate_piece(theme, piece, str(tmp_path / "run_b.mid"))
        assert _midi_bytes(path_a) == _midi_bytes(path_b)

    def test_identical_across_a_fresh_process(self, tmp_path):
        """Same check as above but spanning a real process boundary
        (different PYTHONHASHSEED), confirming the byte-identity isn't an
        artifact of shared in-process state."""
        import subprocess
        import sys
        from pathlib import Path

        theme_path = _fixture_path("theme_shake_v2.json")
        piece_path = _fixture_path("piece_shake_v5.json")
        theme, piece = _load_shake()

        in_process_path = tmp_path / "in_process.mid"
        generate_piece(theme, piece, str(in_process_path))
        in_process_bytes = _midi_bytes(str(in_process_path))

        repo_root = str(Path(__file__).resolve().parents[1])
        env = dict(os.environ)
        env["PYTHONHASHSEED"] = "12345"
        existing = env.get("PYTHONPATH", "")
        env["PYTHONPATH"] = repo_root if not existing else f"{repo_root}{os.pathsep}{existing}"

        subprocess_out = tmp_path / "subprocess.mid"
        script = (
            "import json\n"
            "from intervals.core.generator import generate_piece\n"
            f"theme = json.load(open({theme_path!r}))['theme']\n"
            f"piece = json.load(open({piece_path!r}))['piece']\n"
            f"generate_piece(theme, piece, {str(subprocess_out)!r})\n"
        )
        subprocess.run([sys.executable, "-c", script], capture_output=True,
                        text=True, check=True, env=env)

        assert _midi_bytes(str(subprocess_out)) == in_process_bytes

    def test_different_fixtures_do_not_coincidentally_match(self, tmp_path):
        """Sanity check on the byte-identity tests themselves: two
        genuinely different pieces must NOT produce identical bytes --
        rules out a degenerate generator that ignores its input."""
        shake_theme, shake_piece = _load_shake()
        bbw_theme, bbw_piece = _load_broadway_boogie()

        shake_path = generate_piece(shake_theme, shake_piece, str(tmp_path / "shake.mid"))
        bbw_path = generate_piece(bbw_theme, bbw_piece, str(tmp_path / "bbw.mid"))

        assert _midi_bytes(shake_path) != _midi_bytes(bbw_path)

    def test_different_seed_on_same_piece_changes_output(self, tmp_path):
        theme, piece = _load_shake()
        piece_seed_a = dict(piece)
        piece_seed_a["seed"] = 1
        piece_seed_b = dict(piece)
        piece_seed_b["seed"] = 2

        path_a = generate_piece(theme, piece_seed_a, str(tmp_path / "seed1.mid"))
        path_b = generate_piece(theme, piece_seed_b, str(tmp_path / "seed2.mid"))
        assert _midi_bytes(path_a) != _midi_bytes(path_b)


# ===========================================================================
# Real file-loading round trip (load_theme / load_piece / generate_piece)
# ===========================================================================

class TestLoadersAndFullPipeline:
    def test_load_theme_and_load_piece_unwrap_the_json_wrapper(self):
        theme = load_theme(_fixture_path("theme_shake_v2.json"))
        piece = load_piece(_fixture_path("piece_shake_v5.json"))
        assert theme["key"] == "D"
        assert theme["mode"] == "aeolian"
        assert piece["title"] == "Shake the Disease (FormaComposition) v5"

    def test_full_pipeline_from_disk_is_byte_identical_to_in_memory_dicts(self, tmp_path):
        """The realistic end-to-end path (load from disk, then generate)
        must match generating from the already-parsed dicts -- i.e.
        load_theme/load_piece don't introduce any nondeterminism of
        their own (dict key ordering, etc.)."""
        theme_from_disk = load_theme(_fixture_path("theme_shake_v2.json"))
        piece_from_disk = load_piece(_fixture_path("piece_shake_v5.json"))
        theme_in_memory, piece_in_memory = _load_shake()

        path_disk = generate_piece(theme_from_disk, piece_from_disk,
                                    str(tmp_path / "from_disk.mid"))
        path_memory = generate_piece(theme_in_memory, piece_in_memory,
                                      str(tmp_path / "from_memory.mid"))
        assert _midi_bytes(path_disk) == _midi_bytes(path_memory)


# ===========================================================================
# Structural / metadata assertions against the real fixtures
# ===========================================================================

class TestRenderedStructure:
    def test_metadata_track_reflects_piece_title_and_tempo(self, tmp_path):
        theme, piece = _load_shake()
        path = generate_piece(theme, piece, str(tmp_path / "shake.mid"))
        mid = mido.MidiFile(path)

        meta_track = mid.tracks[0]
        track_name = next(m.name for m in meta_track if m.type == "track_name")
        tempo_msg = next(m for m in meta_track if m.type == "set_tempo")

        assert track_name == piece["title"]
        assert tempo_msg.tempo == bpm_to_tempo(piece["tempo"])

    def test_expected_track_names_are_present(self, tmp_path):
        """shake_v5 has melody, two counterpoint voices, harmony, and bass
        on every section -- confirm each gets its own named track."""
        theme, piece = _load_shake()
        path = generate_piece(theme, piece, str(tmp_path / "shake.mid"))
        mid = mido.MidiFile(path)

        track_names = {
            m.name for track in mid.tracks for m in track if m.type == "track_name"
        }
        assert TRACK_NAME_MELODY in track_names
        assert TRACK_NAME_HARMONY in track_names
        assert TRACK_NAME_BASS in track_names
        assert "Counterpoint" in track_names
        assert "Counterpoint 2" in track_names

    def test_no_drum_track_when_no_section_uses_percussion(self, tmp_path):
        """The real (unmodified) shake_v5 fixture defines no drums block
        on any section -- generate_piece must not emit an empty drums
        track just because the constant exists."""
        theme, piece = _load_shake()
        path = generate_piece(theme, piece, str(tmp_path / "shake.mid"))
        mid = mido.MidiFile(path)
        track_names = {
            m.name for track in mid.tracks for m in track if m.type == "track_name"
        }
        assert "Drums" not in track_names

    def test_melody_channel_notes_stay_within_theme_register_conventions(self, tmp_path):
        """Coarse sanity check that the rendered melody notes are
        plausible MIDI pitches (0-127), not a channel mixup or garbage
        from a broken voice-routing path."""
        theme, piece = _load_shake()
        path = generate_piece(theme, piece, str(tmp_path / "shake.mid"))
        mid = mido.MidiFile(path)

        melody_track = next(t for t in mid.tracks
                             if any(m.type == "track_name" and m.name == TRACK_NAME_MELODY
                                    for m in t))
        note_ons = [m for m in melody_track if m.type == "note_on" and m.velocity > 0]
        assert note_ons  # sanity: melody actually produced notes
        assert all(0 <= m.note <= 127 for m in note_ons)
        assert all(m.channel == CHANNEL_MELODY for m in note_ons)


# ===========================================================================
# exact_repeat — imported and re-run from Task 0's regression file, so it's
# exercised as part of THIS suite too, not standing alone in one file.
# ===========================================================================

class TestExactRepeatIsPartOfThisSuite:
    def test_task0_exact_repeat_regression_passes_from_within_this_suite(self):
        """Directly imports and calls the Task 0 regression test function.
        If that probe ever regresses, this integration suite fails too --
        exact_repeat correctness is no longer verified by only one
        standalone file."""
        from tests.test_exact_repeat_regression import (
            test_exact_repeat_chorus_is_byte_identical_across_every_voice,
        )
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            from pathlib import Path
            test_exact_repeat_chorus_is_byte_identical_across_every_voice(Path(tmp))

    def test_exact_repeat_also_holds_for_a_different_seed(self, tmp_path):
        """Broader than Task 0's single-seed probe: confirm exact_repeat
        equivalence isn't an accident of the fixture's default seed by
        re-running the same chorus-window diff at a different base seed."""
        from tests.test_exact_repeat_regression import (
            _chorus_windows_ticks,
            _voice_events_in_window,
            VOICE_TRACK_NAMES,
        )

        theme, piece = _load_shake()
        piece = copy.deepcopy(piece)
        piece["sections"]["chorus"]["drums"] = {"pattern": "four_on_floor"}
        piece["seed"] = 999  # different from the fixture's default

        out_path = generate_piece(theme, piece, str(tmp_path / "shake_seed999.mid"))
        mid = mido.MidiFile(out_path)

        (first_start, first_end), (repeat_start, repeat_end) = _chorus_windows_ticks(piece)
        for voice_name in VOICE_TRACK_NAMES:
            first_notes = _voice_events_in_window(mid, voice_name, first_start, first_end)
            repeat_notes = _voice_events_in_window(mid, voice_name, repeat_start, repeat_end)
            assert first_notes == repeat_notes, (
                f"voice '{voice_name}' diverged between chorus occurrences at seed=999"
            )


# ===========================================================================
# Bugfix regression: peer voices (section.voices[1:]) must receive the
# section's own groove/swing, the same as the lead melody voice does.
# ===========================================================================

class TestPeerVoiceInheritsSectionGrooveAndSwing:
    def test_peer_voice_call_receives_section_groove_and_swing(self):
        """generate_piece() used to extract a section's groove/swing into
        local variables (comment: "used by melody, bass") but only ever
        passed them to the LEAD melody voice's generate_melody_for_
        progression() call -- every peer voice (section.voices[1:], the
        non-counterpoint-species case) called the same function without
        groove/swing at all, silently falling back to that function's own
        defaults (groove=None, swing=0.0) regardless of what the section
        actually specified.

        This intercepts every real call to generate_melody_for_progression
        during a full generate_piece() render and confirms BOTH the lead
        voice's call and every peer voice's call receive the section's
        actual groove/swing -- not just the lead."""
        from unittest.mock import patch
        import intervals.core.generator as gen

        theme = {"key": "C", "mode": "ionian", "tempo": {"min": 100, "max": 120}}
        piece = {
            "title": "peer-groove-swing-test", "tempo": 110, "seed": 1,
            "sections": [{
                "name": "a", "progression": ["i", "iv"], "rhythm": "free", "bars": 4,
                "swing": 0.73, "groove": "shuffle",
                "voices": [
                    {"register": "soprano", "behavior": "lyrical"},
                    {"register": "alto", "behavior": "generative"},
                ],
            }],
        }

        captured_kwargs = []
        real_fn = gen.generate_melody_for_progression

        def _spy(*args, **kwargs):
            captured_kwargs.append(kwargs)
            return real_fn(*args, **kwargs)

        with patch.object(gen, "generate_melody_for_progression", side_effect=_spy):
            gen.generate_piece(theme, piece, "/tmp/_peer_groove_swing_regression.mid")

        # One call for the lead voice, one for the single peer voice.
        assert len(captured_kwargs) == 2
        for kwargs in captured_kwargs:
            assert kwargs.get("groove") == "shuffle"
            assert kwargs.get("swing") == 0.73
