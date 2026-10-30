"""
Two small, separate fixes:

1. `velocities` on a bass_motif used to be dropped (generator.py rebuilt the
   bass motif through motif_to_dict(), which has no velocities). They now
   reach the bass line, and are validated like a MotifModel's.
2. A motif whose rhythm does not fill whole bars now gets a note-by-note
   explanation (bar|beat positions, the note that crosses the bar line, the
   nearest totals that fit) appended to the existing validation error.
"""
import json
import sys
from pathlib import Path

import mido
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from intervals.core.generator import generate_piece
from intervals.core.motif_loader import resolve_motif_velocities
from intervals.core.schemas import PieceModel
from intervals.music.motif import bar_alignment_report

# ── helpers ──────────────────────────────────────────────────────────────────

BASS_RHYTHM = [1.0, 1.0, 1.0, 1.0]
BASS_INTERVALS = [0, 2, -1, -1]
HEAD = {"name": "head", "intervals": [0, 2, -1, -1], "rhythm": [1.0] * 4,
        "transform_pool": ["original"]}


def piece(bass_motif, bars=2):
    return {
        "key": "C", "mode": "ionian", "tempo": {"min": 100, "max": 100}, "seed": 7,
        "form_type": "song", "form": ["a"], "motif": HEAD,
        "sections": {"a": {
            "name": "a", "rhythm": "motif", "bars": bars, "progression": ["I"],
            "bass_style": "motif", "bass_velocity": 80, "arc": "none",
            "bass_motif": bass_motif,
        }},
    }


def bass_velocities(tmp_path, bass_motif, name="x.mid"):
    path = tmp_path / name
    generate_piece(piece(bass_motif), str(path))
    mid = mido.MidiFile(str(path))
    for tr in mid.tracks:
        if any(m.type == "track_name" and "bass" in m.name.lower() for m in tr):
            return [m.velocity for m in tr if m.type == "note_on" and m.velocity > 0]
    raise AssertionError("no bass track")


def validated(bass_motif):
    pm = PieceModel.model_validate(piece(bass_motif))
    pm.validate_against_theme(pm)
    return pm


# ── 1. bass_motif velocities ─────────────────────────────────────────────────

class TestBassMotifVelocity:
    def test_velocities_reach_the_bass_line(self, tmp_path):
        scales = [1.0, 0.5, 0.75, 0.25]
        got = bass_velocities(tmp_path, {"name": "b", "intervals": BASS_INTERVALS,
                                         "rhythm": BASS_RHYTHM, "velocities": scales})
        assert got[:4] == [int(80 * s) for s in scales]          # 80, 40, 60, 20
        assert got[4:8] == got[:4]                                # the cell repeats

    def test_events_form_gives_the_same_velocities(self, tmp_path):
        scales = [1.0, 0.5, 0.75, 0.25]
        legacy = bass_velocities(tmp_path, {"name": "b", "intervals": BASS_INTERVALS,
                                            "rhythm": BASS_RHYTHM, "velocities": scales}, "l.mid")
        events = bass_velocities(tmp_path, {"name": "b", "events": [
            {"step": s, "beats": 1.0, "velocity": v} for s, v in zip(BASS_INTERVALS, scales)]}, "e.mid")
        assert events == legacy

    def test_no_velocities_is_unchanged(self, tmp_path):
        plain = {"name": "b", "intervals": BASS_INTERVALS, "rhythm": BASS_RHYTHM}
        ones = {**plain, "velocities": [1.0] * 4}
        a = bass_velocities(tmp_path, plain, "a.mid")
        b = bass_velocities(tmp_path, ones, "b.mid")
        assert a == b == [80] * len(a)
        assert (tmp_path / "a.mid").read_bytes() == (tmp_path / "b.mid").read_bytes()

    def test_velocities_from_the_inline_pool_by_name(self, tmp_path):
        p = piece("riff")
        p["motifs"] = [HEAD, {"name": "riff", "intervals": BASS_INTERVALS, "rhythm": BASS_RHYTHM,
                              "velocities": [1.0, 0.5, 1.0, 0.5]}]
        del p["motif"]
        path = tmp_path / "pool.mid"
        generate_piece(p, str(path))
        mid = mido.MidiFile(str(path))
        bass = next(t for t in mid.tracks
                    if any(m.type == "track_name" and "bass" in m.name.lower() for m in t))
        vels = [m.velocity for m in bass if m.type == "note_on" and m.velocity > 0]
        assert vels[:4] == [80, 40, 80, 40]


class TestResolveMotifVelocities:
    def test_embedded_dict(self):
        assert resolve_motif_velocities({"intervals": [0], "rhythm": [1], "velocities": [0.5]}) == [0.5]

    def test_events_dict(self):
        assert resolve_motif_velocities(
            {"events": [{"step": 0, "beats": 1, "velocity": 0.4}, {"step": 1, "beats": 1, "velocity": 0.9}]}
        ) == [0.4, 0.9]

    def test_none_and_missing(self):
        assert resolve_motif_velocities(None) is None
        assert resolve_motif_velocities({"intervals": [0], "rhythm": [1]}) is None
        assert resolve_motif_velocities("nothing_by_this_name", theme_pool=[]) is None

    def test_pool_name(self):
        pool = [{"name": "riff", "intervals": [0], "rhythm": [1], "velocities": [0.3]}]
        assert resolve_motif_velocities("riff", theme_pool=pool) == [0.3]

    def test_library_file(self, tmp_path):
        (tmp_path / "motif_riff.json").write_text(json.dumps(
            {"motif": {"name": "riff", "events": [{"step": 0, "beats": 1, "velocity": 0.6}]}}))
        assert resolve_motif_velocities("riff", motifs_dir=str(tmp_path)) == [0.6]


class TestBassMotifVelocityValidation:
    base = {"name": "b", "intervals": BASS_INTERVALS, "rhythm": BASS_RHYTHM}

    def test_valid_velocities_pass(self):
        validated({**self.base, "velocities": [1.0, 0.5, 0.75, 0.25]})

    def test_midi_scale_values_are_rejected_not_silently_applied(self):
        with pytest.raises(ValueError, match=r"bass_motif.*0\.0-1\.0.*\[90"):
            validated({**self.base, "velocities": [90, 64, 64, 64]})

    def test_length_mismatch(self):
        with pytest.raises(ValueError, match=r"bass_motif.*velocities length \(3\).*rhythm length \(4\)"):
            validated({**self.base, "velocities": [1.0, 0.5, 0.5]})

    def test_events_form_is_validated_too(self):
        with pytest.raises(ValueError, match=r"0\.0-1\.0"):
            validated({"name": "b", "events": [{"step": 0, "beats": 4.0, "velocity": 2.0}]})

    def test_not_a_list(self):
        with pytest.raises(ValueError, match="list of numbers"):
            validated({**self.base, "velocities": "loud"})


# ── 2. bar alignment report ──────────────────────────────────────────────────

class TestBarAlignmentReport:
    def test_the_copper_dusk_case(self):
        out = bar_alignment_report([2.0, 0.5, 0.5, 4.0, 2.0], 4)
        lines = out.splitlines()
        assert lines[0].split() == ["note", "starts", "beats"]
        assert lines[1].split()[:2] == ["1", "1|1"]
        assert lines[3].split()[:2] == ["3", "1|3.5"]
        assert "<- crosses into bar 2" in lines[4]
        assert "<- crosses into bar 3" in lines[5]
        assert "crosses" not in lines[1] + lines[2] + lines[3]
        assert lines[-1].strip() == "ends 3|2 (9 beats). A fit needs 8 (trim 1) or 12 (add 3)."

    def test_three_four_time(self):
        out = bar_alignment_report([1.0, 1.0, 1.5], 3)
        assert "ends 2|1.5 (3.5 beats)" in out
        assert "3 (trim 0.5) or 6 (add 2.5)" in out

    def test_shorter_than_one_bar_only_offers_adding(self):
        out = bar_alignment_report([1.5], 4)
        assert out.splitlines()[-1].strip() == "ends 1|2.5 (1.5 beats). A fit needs 4 (add 2.5)."

    def test_whole_bar_hold_is_not_flagged(self):
        out = bar_alignment_report([8.0, 1.0, 1.0, 1.0], 4)
        assert "crosses" not in out.splitlines()[1]       # starts and ends on bar lines

    def test_note_ending_exactly_on_a_bar_line_is_not_flagged(self):
        assert "crosses" not in bar_alignment_report([2.0, 2.0, 1.0], 4)

    def test_floating_point_noise_does_not_invent_a_crossing(self):
        out = bar_alignment_report([0.1] * 40 + [1.0], 4)  # 0.1 * 40 accumulates float error
        assert "1|1" in out and "crosses" not in "\n".join(out.splitlines()[1:6])

    def test_long_motifs_are_truncated(self):
        out = bar_alignment_report([0.5] * 40 + [0.25], 4, max_rows=10)
        assert "more note(s)" in out and len(out.splitlines()) <= 13

    def test_empty(self):
        assert bar_alignment_report([], 4) == ""


class TestBarAlignmentError:
    def _piece_with_events(self, beats):
        return {
            "key": "C", "mode": "ionian", "tempo": {"min": 100, "max": 100}, "seed": 7,
            "form_type": "song", "form": ["a"],
            "motif": {"name": "copper", "events": [{"step": 0, "beats": b} for b in beats]},
            "sections": {"a": {"name": "a", "rhythm": "motif", "bars": 2, "progression": ["I"]}},
        }

    def test_misaligned_motif_error_keeps_its_original_message_and_adds_the_table(self):
        pm = PieceModel.model_validate(self._piece_with_events([2.0, 0.5, 0.5, 4.0, 2.0]))
        with pytest.raises(ValueError) as exc:
            pm.validate_against_theme(pm)
        msg = str(exc.value)
        assert "which is not a whole multiple of this section's beats_per_bar (4)" in msg
        assert "<- crosses into bar 2" in msg
        assert "A fit needs 8 (trim 1) or 12 (add 3)." in msg

    def test_aligned_motif_still_passes(self):
        pm = PieceModel.model_validate(self._piece_with_events([2.0, 0.5, 0.5, 3.0, 2.0]))
        pm.validate_against_theme(pm)

    def test_bass_motif_gets_the_table_too(self):
        p = piece({"name": "b", "intervals": [0, 1, 2], "rhythm": [1.0, 1.0, 1.5]})
        pm = PieceModel.model_validate(p)
        with pytest.raises(ValueError, match=r"bass_motif 'b'.*crosses|bass_motif 'b'[\s\S]*ends 1\|4\.5"):
            pm.validate_against_theme(pm)
