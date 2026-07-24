"""
Tests for intervals.core.lint — the 17 consume-gate guardrails.

Each test constructs the exact minimal SectionModel shape a given
`_check_*` function is documented to catch, calls that function directly
(not lint_section/lint_piece), and asserts a Contradiction fires with the
expected field/message content.

Two of these checks (`_check_counterpoint_species_unimplemented`'s two
branches) guard against a state that schemas.py's own field validators
now block at construction time -- CounterpointModel and VoiceModel both
raise ValidationError for any species outside {'first', 'free'} before a
SectionModel can ever hold one. That means the normal path to a
SectionModel can no longer produce the input these checks were written
for. To test the checks' own logic in isolation (which is what this task
asks for -- lint.py and schemas.py are separate lines of defense, tested
separately), those two tests build the malformed value with
`model_construct()` / `model_copy(update=...)`, which bypass field
validation on purpose. This is flagged again in the final summary as a
real dead-code finding, not fixed here (out of scope for a test-writing
task).
"""
import pytest

from intervals.core.lint import (
    CHECKS,
    _check_bass_rest_on_continuous,
    _check_bass_swing_noop,
    _check_canon_interval_without_canonic_imitation,
    _check_counterpoint_motif_species_noop,
    _check_counterpoint_species_unimplemented,
    _check_develop_peer_voice_noop,
    _check_even_chord_split,
    _check_harmony_motif_groove_noop,
    _check_harmony_motif_without_motif_rhythm,
    _check_harmony_pattern_silently_empty,
    _check_harmony_rest_on_sustain,
    _check_long_progression_seed_collision,
    _check_melodic_variation_noop,
    _check_note_length_range_vs_groove,
    _check_note_length_range_vs_rhythm,
    _check_section_motif_override,
    _check_transform_imitation_unimplemented,
    _check_voice_motif,
)
from intervals.core.schemas import CounterpointModel, SectionModel, VoiceModel


def _section(**overrides) -> SectionModel:
    base = {
        "progression": ["i", "iv", "v"],
        "rhythm": "free",
        "bars": 8,
    }
    base.update(overrides)
    return SectionModel.model_validate(base)


# ===========================================================================
# 1. _check_voice_motif
# ===========================================================================

def test_check_voice_motif_fires_on_non_develop_behavior_with_motif():
    section = _section(voices=[
        {"register": "soprano", "behavior": "lyrical", "motif": "call"},
    ])
    found = list(_check_voice_motif(section))
    assert len(found) == 1
    c = found[0]
    assert "motif='call'" in c.setting
    assert "behavior='lyrical'" in c.cause
    assert "voice 1 (soprano)" in c.where


def test_check_voice_motif_does_not_fire_when_develop():
    section = _section(voices=[
        {"register": "soprano", "behavior": "develop", "motif": "call"},
    ])
    assert list(_check_voice_motif(section)) == []


# ===========================================================================
# 2. _check_harmony_motif_without_motif_rhythm
# ===========================================================================

def test_check_harmony_motif_without_motif_rhythm_fires():
    section = _section(harmony_rhythm={"rhythm": "free", "motif": "bell"})
    found = list(_check_harmony_motif_without_motif_rhythm(section))
    assert len(found) == 1
    assert "harmony_rhythm.motif='bell'" in found[0].setting
    assert "'free'" in found[0].cause


def test_check_harmony_motif_without_motif_rhythm_silent_when_rhythm_is_motif():
    section = _section(harmony_rhythm={"rhythm": "motif", "motif": "bell"})
    assert list(_check_harmony_motif_without_motif_rhythm(section)) == []


# ===========================================================================
# 3. _check_harmony_motif_groove_noop
# ===========================================================================

def test_check_harmony_motif_groove_noop_fires():
    section = _section(harmony_rhythm={"rhythm": "motif", "groove": "straight"})
    found = list(_check_harmony_motif_groove_noop(section))
    assert len(found) == 1
    assert "groove='straight'" in found[0].setting
    assert "motif" in found[0].cause


def test_check_harmony_motif_groove_noop_silent_without_groove():
    section = _section(harmony_rhythm={"rhythm": "motif"})
    assert list(_check_harmony_motif_groove_noop(section)) == []


# ===========================================================================
# 4. _check_counterpoint_motif_species_noop
# ===========================================================================

def test_check_counterpoint_motif_species_noop_fires_on_first_species_motif():
    section = _section(counterpoint=[{"species": "first", "motif": "riff"}])
    found = list(_check_counterpoint_motif_species_noop(section))
    assert len(found) == 1
    assert "motif='riff'" in found[0].setting
    assert "species='first'" in found[0].cause


def test_check_counterpoint_motif_species_noop_silent_for_free_species():
    section = _section(counterpoint=[{"species": "free", "motif": "riff"}])
    assert list(_check_counterpoint_motif_species_noop(section)) == []


# ===========================================================================
# 5. _check_melodic_variation_noop
# ===========================================================================

def test_check_melodic_variation_noop_fires_when_rhythm_is_not_motif():
    section = _section(rhythm="free", melodic_variation="isorhythmic")
    found = list(_check_melodic_variation_noop(section, motif_pool_size=-1))
    assert len(found) == 1
    assert "melodic_variation='isorhythmic'" in found[0].setting
    assert "rhythm='free'" in found[0].cause


def test_check_melodic_variation_noop_fires_on_small_pool_even_with_rhythm_motif():
    section = _section(rhythm="motif", melodic_variation="isorhythmic")
    found = list(_check_melodic_variation_noop(section, motif_pool_size=1))
    assert len(found) == 1
    assert "only 1 motif(s)" in found[0].cause


def test_check_melodic_variation_noop_silent_when_all_conditions_met():
    section = _section(rhythm="motif", melodic_variation="isorhythmic")
    assert list(_check_melodic_variation_noop(section, motif_pool_size=3)) == []


# ===========================================================================
# 6. _check_section_motif_override
# ===========================================================================

def test_check_section_motif_override_fires_on_section_motif():
    section = _section(motif="theme_a")
    found = list(_check_section_motif_override(section))
    assert len(found) == 1
    assert "section-level motif is set" in found[0].setting


def test_check_section_motif_override_fires_on_section_motifs_list():
    section = _section(motifs=["theme_a", "theme_b"])
    found = list(_check_section_motif_override(section))
    assert len(found) == 1
    assert "motifs" in found[0].setting


def test_check_section_motif_override_silent_when_unset():
    section = _section()
    assert list(_check_section_motif_override(section)) == []


# ===========================================================================
# 7. _check_harmony_rest_on_sustain
# ===========================================================================

def test_check_harmony_rest_on_sustain_fires():
    section = _section(
        harmony_rhythm={"rhythm": "sustain"},
        harmony_rest_probability=0.3,
    )
    found = list(_check_harmony_rest_on_sustain(section))
    assert len(found) == 1
    assert "harmony_rest_probability=0.3" in found[0].setting
    assert "sustain" in found[0].cause


def test_check_harmony_rest_on_sustain_silent_when_zero():
    section = _section(
        harmony_rhythm={"rhythm": "sustain"},
        harmony_rest_probability=0.0,
    )
    assert list(_check_harmony_rest_on_sustain(section)) == []


# ===========================================================================
# 8. _check_bass_rest_on_continuous
# ===========================================================================

def test_check_bass_rest_on_continuous_fires():
    section = _section(bass_style="walking", bass_rest_probability=0.2)
    found = list(_check_bass_rest_on_continuous(section))
    assert len(found) == 1
    assert "bass_rest_probability=0.2" in found[0].setting
    assert "walking" in found[0].cause


def test_check_bass_rest_on_continuous_silent_for_noncontinuous_style():
    section = _section(bass_style="root_fifth", bass_rest_probability=0.2)
    assert list(_check_bass_rest_on_continuous(section)) == []


# ===========================================================================
# 9. _check_note_length_range_vs_groove
# ===========================================================================

def test_check_note_length_range_vs_groove_fires():
    section = _section(
        note_length_range={"min": 0.25, "max": 1.0},
        groove="straight",
    )
    found = list(_check_note_length_range_vs_groove(section))
    assert len(found) == 1
    assert "note_length_range=(0.25, 1.0)" in found[0].setting
    assert "groove='straight'" in found[0].cause


def test_check_note_length_range_vs_groove_silent_without_groove():
    section = _section(note_length_range={"min": 0.25, "max": 1.0})
    assert list(_check_note_length_range_vs_groove(section)) == []


# ===========================================================================
# 10. _check_note_length_range_vs_rhythm
# ===========================================================================

def test_check_note_length_range_vs_rhythm_fires_for_motif_rhythm():
    section = _section(rhythm="motif", note_length_range={"min": 0.25, "max": 1.0})
    found = list(_check_note_length_range_vs_rhythm(section))
    assert len(found) == 1
    assert "rhythm='motif'" in found[0].cause


def test_check_note_length_range_vs_rhythm_silent_for_free_rhythm():
    section = _section(rhythm="free", note_length_range={"min": 0.25, "max": 1.0})
    assert list(_check_note_length_range_vs_rhythm(section)) == []


# ===========================================================================
# 11. _check_even_chord_split
# ===========================================================================

def test_check_even_chord_split_fires_above_threshold():
    # 2 chords over 10 bars, no chord_bars -> 5.0 bars/chord (> 4.0 threshold)
    section = _section(progression=["i", "v"], bars=10)
    found = list(_check_even_chord_split(section))
    assert len(found) == 1
    assert "bars=10" in found[0].setting
    assert "2 chords" in found[0].setting


def test_check_even_chord_split_silent_at_or_below_threshold():
    # 4 chords over 8 bars -> exactly 2.0 bars/chord (well under threshold)
    section = _section(progression=["i", "iv", "v", "i"], bars=8)
    assert list(_check_even_chord_split(section)) == []


def test_check_even_chord_split_silent_when_chord_bars_explicit():
    section = _section(
        progression=["i", "v"], bars=10, chord_bars=[5.0, 5.0],
    )
    assert list(_check_even_chord_split(section)) == []


# ===========================================================================
# 12. _check_develop_peer_voice_noop
# ===========================================================================

def test_check_develop_peer_voice_noop_fires_on_peer_index():
    section = _section(voices=[
        {"register": "soprano", "behavior": "lyrical"},
        {"register": "alto", "behavior": "develop"},
    ])
    found = list(_check_develop_peer_voice_noop(section))
    assert len(found) == 1
    assert "behavior='develop'" in found[0].setting
    assert "voice 2 (alto)" in found[0].where


def test_check_develop_peer_voice_noop_silent_for_lead_voice():
    section = _section(voices=[
        {"register": "soprano", "behavior": "develop"},
    ])
    assert list(_check_develop_peer_voice_noop(section)) == []


# ===========================================================================
# 13. _check_bass_swing_noop
# ===========================================================================

def test_check_bass_swing_noop_fires():
    section = _section(swing=0.5, bass_style="root_fifth")
    found = list(_check_bass_swing_noop(section))
    assert len(found) == 1
    assert "swing=0.5" in found[0].setting
    assert "root_fifth" in found[0].cause


def test_check_bass_swing_noop_silent_for_consuming_style():
    section = _section(swing=0.5, bass_style="melodic")
    assert list(_check_bass_swing_noop(section)) == []


# ===========================================================================
# 14. _check_counterpoint_species_unimplemented
# ===========================================================================
#
# schemas.py's CounterpointModel/VoiceModel now block any species outside
# {'first', 'free'} at field-validation time -- see module docstring above.
# model_construct() / model_copy(update=...) bypass that validation so this
# check's own logic (which predates or duplicates that schema guard) can
# still be exercised directly, as the task asks.

def test_check_counterpoint_species_unimplemented_fires_for_counterpoint_list():
    section = _section()
    bad_cp = CounterpointModel.model_construct(
        species="third", cp_register="below", dissonance="passing",
        velocity=58, canon_offset=0.0, rhythm_density="medium",
        groove=None, note_length_range=None, motif=None,
    )
    section = section.model_copy(update={"counterpoint": [bad_cp]})
    found = list(_check_counterpoint_species_unimplemented(section))
    assert len(found) == 1
    assert "species='third'" in found[0].setting
    assert "WILL raise ValueError" in found[0].effect


def test_check_counterpoint_species_unimplemented_fires_for_voices_list():
    section = _section()
    bad_voice = VoiceModel.model_construct(
        v_register="mid", behavior="lyrical", velocity=64, motif=None,
        species="fifth", dissonance="passing", canon_offset=0.0,
        rest_probability=None,
    )
    section = section.model_copy(update={"voices": [bad_voice]})
    found = list(_check_counterpoint_species_unimplemented(section))
    assert len(found) == 1
    assert "species='fifth'" in found[0].setting


def test_check_counterpoint_species_unimplemented_silent_for_implemented_species():
    section = _section(counterpoint=[{"species": "first"}, {"species": "free"}])
    assert list(_check_counterpoint_species_unimplemented(section)) == []


# ===========================================================================
# 15. _check_transform_imitation_unimplemented
# ===========================================================================

def test_check_transform_imitation_unimplemented_fires():
    # rhythm='free' (not 'motif') so this stays schema-legal at
    # SectionModel construction -- schemas.py only blocks the combination
    # with rhythm='motif' specifically (see test_schemas.py). The lint
    # check itself fires on transform_imitation='strict' alone, so this
    # is still a genuine, reachable case for it.
    section = _section(harmony_rhythm={
        "rhythm": "free", "transform_imitation": "strict",
    })
    found = list(_check_transform_imitation_unimplemented(section))
    assert len(found) == 1
    assert "transform_imitation='strict'" in found[0].setting
    assert "WILL raise ValueError" in found[0].effect


def test_check_transform_imitation_unimplemented_silent_when_unset():
    section = _section(harmony_rhythm={"rhythm": "free"})
    assert list(_check_transform_imitation_unimplemented(section)) == []


# ===========================================================================
# 16. _check_long_progression_seed_collision
# ===========================================================================

def test_check_long_progression_seed_collision_fires_above_threshold():
    long_progression = ["i"] * 11  # > LONG_PROGRESSION_SEED_COLLISION_THRESHOLD (10)
    section = _section(progression=long_progression, rhythm="free", bars=44)
    found = list(_check_long_progression_seed_collision(section))
    assert len(found) == 1
    assert "11 chords" in found[0].setting
    assert "'free'" in found[0].cause


def test_check_long_progression_seed_collision_silent_at_threshold():
    exactly_ten = ["i"] * 10
    section = _section(progression=exactly_ten, rhythm="free", bars=40)
    assert list(_check_long_progression_seed_collision(section)) == []


def test_check_long_progression_seed_collision_silent_for_non_risk_source():
    long_progression = ["i"] * 11
    section = _section(
        progression=long_progression, rhythm="free", bars=44,
        harmony_rhythm={"rhythm": "sustain"},
    )
    assert list(_check_long_progression_seed_collision(section)) == []


# ===========================================================================
# 17. _check_harmony_pattern_silently_empty
# ===========================================================================

def test_check_harmony_pattern_silently_empty_fires():
    section = _section(
        rhythm="pattern",
        rhythm_pattern={"onsets": [0.0], "durations": [1.0]},
        # harmony_rhythm left unset -> inherits 'pattern', no harmony_pattern block
    )
    found = list(_check_harmony_pattern_silently_empty(section))
    assert len(found) == 1
    assert "inheriting rhythm='pattern'" in found[0].setting
    assert "completely silent" in found[0].effect


def test_check_harmony_pattern_silently_empty_silent_when_block_present():
    section = _section(
        rhythm="pattern",
        rhythm_pattern={"onsets": [0.0], "durations": [1.0]},
        harmony_pattern={"onsets": [0.0], "durations": [1.0]},
    )
    assert list(_check_harmony_pattern_silently_empty(section)) == []


def test_check_harmony_pattern_silently_empty_silent_when_explicit_harmony_rhythm():
    """The explicit-harmony_rhythm.rhythm='pattern' case is already
    schema-enforced (requires harmony_pattern) -- this check only covers
    the *inherited* gap, so it must stay silent here."""
    section = _section(
        rhythm="pattern",
        rhythm_pattern={"onsets": [0.0], "durations": [1.0]},
        harmony_rhythm={"rhythm": "sustain"},
    )
    assert list(_check_harmony_pattern_silently_empty(section)) == []


# ===========================================================================
# 18. _check_canon_interval_without_canonic_imitation
# ===========================================================================

def test_check_canon_interval_without_canonic_imitation_fires_when_absent():
    section = _section(fugal_techniques={"canon_interval": 4})
    found = list(_check_canon_interval_without_canonic_imitation(section))
    assert len(found) == 1
    assert "canon_interval=4" in found[0].setting
    assert "canonic_imitation is not true" in found[0].cause


def test_check_canon_interval_without_canonic_imitation_fires_when_explicitly_false():
    section = _section(fugal_techniques={"canon_interval": 4, "canonic_imitation": False})
    found = list(_check_canon_interval_without_canonic_imitation(section))
    assert len(found) == 1


def test_check_canon_interval_without_canonic_imitation_silent_when_both_set():
    section = _section(fugal_techniques={"canon_interval": 4, "canonic_imitation": True})
    assert list(_check_canon_interval_without_canonic_imitation(section)) == []


def test_check_canon_interval_without_canonic_imitation_silent_with_no_fugal_techniques():
    section = _section()
    assert list(_check_canon_interval_without_canonic_imitation(section)) == []


def test_check_canon_interval_without_canonic_imitation_silent_without_interval_key():
    """canonic_imitation=True with no canon_interval key uses the function's
    own default (4 beats) internally -- nothing for the linter to flag."""
    section = _section(fugal_techniques={"canonic_imitation": True})
    assert list(_check_canon_interval_without_canonic_imitation(section)) == []


# ===========================================================================
# Sanity: CHECKS registry contains all 17 section-only checks (the 18th,
# _check_melodic_variation_noop, is invoked separately by lint_piece because
# it needs theme context -- see its docstring and lint_piece's signature).
# ===========================================================================

def test_checks_registry_has_seventeen_entries_plus_melodic_variation_separately():
    assert len(CHECKS) == 17
    assert _check_melodic_variation_noop not in CHECKS
