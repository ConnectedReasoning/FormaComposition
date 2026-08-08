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
    _check_harmony_melody_ratio,
    _check_harmony_motif_groove_noop,
    _check_harmony_motif_without_motif_rhythm,
    _check_harmony_rest_on_sustain,
    _check_inherited_motif_coerced_to_free,
    _check_lead_velocity_margin,
    _check_long_progression_seed_collision,
    _check_melodic_arc_apex_unreachable,
    _check_melodic_variation_noop,
    _check_motif_never_developed,
    _check_note_length_range_vs_groove,
    _check_note_length_range_vs_rhythm,
    _check_section_motif_override,
    _check_transform_imitation_unimplemented,
    _check_voice_motif,
)
from intervals.core.schemas import CounterpointModel, PieceModel, SectionModel, VoiceModel


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


def test_check_voice_motif_does_not_fire_for_entry_role_voice():
    """entry_role voices consume `motif` via generate_subject_entry,
    independent of `behavior` — the default behavior='lyrical' left on
    such a voice must not trip this check."""
    section = _section(voices=[
        {"register": "soprano", "entry_role": "subject", "motif": "call"},
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


def test_check_harmony_groove_noop_fires_under_sustain():
    """
    Coverage gap fix: groove is just as inert under 'sustain' (one held
    note per chord, no onset grid) as it is under 'motif'. Confirmed live
    in piece_long_amen.json, which set this exact combination on all four
    of its sections and passed lint clean before this fix.
    """
    section = _section(harmony_rhythm={"rhythm": "sustain", "groove": "straight"})
    found = list(_check_harmony_motif_groove_noop(section))
    assert len(found) == 1
    assert "groove='straight'" in found[0].setting
    assert "sustain" in found[0].cause


def test_check_harmony_groove_noop_silent_under_free():
    """groove is genuinely audible under 'free' -- must not fire here."""
    section = _section(harmony_rhythm={"rhythm": "free", "groove": "straight"})
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
# 18. _check_melodic_arc_apex_unreachable
# ===========================================================================

def test_check_melodic_arc_fires_when_apex_degree_unreachable():
    # degree 51 (1-indexed schema value -> engine degree 50) confirmed
    # unreachable in the default 'mid' register (63-81) before pinning.
    section = _section(key="C", mode="ionian",
                        melodic_arc={"apex_degree": 51, "apex_position": 0.7})
    found = list(_check_melodic_arc_apex_unreachable(section))
    assert len(found) == 1
    assert "apex_degree=51" in found[0].setting
    assert "C ionian" in found[0].cause


def test_check_melodic_arc_silent_when_apex_degree_reachable():
    # degree 5 (1-indexed -> engine degree 4, the dominant) confirmed
    # reachable in the default register before pinning.
    section = _section(key="C", mode="ionian",
                        melodic_arc={"apex_degree": 5, "apex_position": 0.7})
    assert list(_check_melodic_arc_apex_unreachable(section)) == []


def test_check_melodic_arc_silent_when_no_melodic_arc():
    section = _section(key="C", mode="ionian")
    assert list(_check_melodic_arc_apex_unreachable(section)) == []


def test_check_melodic_arc_silent_when_apex_degree_not_set():
    # melodic_arc present but only enabling cadence pull, no apex target
    # -- nothing for this check to evaluate.
    section = _section(key="C", mode="ionian",
                        melodic_arc={"resolve_every_cycle": True})
    assert list(_check_melodic_arc_apex_unreachable(section)) == []


def test_check_melodic_arc_silent_when_key_or_mode_not_declared_on_section():
    # Documented limitation: this check only fires when the section
    # explicitly declares its own key AND mode, since lint_section() has
    # no access to piece-level inheritance. A section relying on the
    # piece's key/mode is silently skipped, not incorrectly flagged.
    section = _section(melodic_arc={"apex_degree": 51, "apex_position": 0.7})
    assert section.key is None and section.mode is None
    assert list(_check_melodic_arc_apex_unreachable(section)) == []


def test_check_melodic_arc_uses_voice_register_when_melody_is_a_voice_model():
    # degree 5 (dominant) is reachable in the default 'mid' register, but
    # a narrow explicit voice register can make it genuinely unreachable
    # -- confirms register resolution actually reads section.melody's
    # VoiceModel form, not just falling back to the default every time.
    section = _section(
        key="C", mode="ionian",
        melody={"register": "low", "behavior": "lyrical"},
        melodic_arc={"apex_degree": 51, "apex_position": 0.7},
    )
    found = list(_check_melodic_arc_apex_unreachable(section))
    assert len(found) == 1
    assert "[36, 54]" in found[0].cause


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


def test_check_develop_peer_voice_noop_silent_for_entry_role_peer():
    """A peer voice with entry_role set renders via generate_subject_entry
    regardless of `behavior` — a leftover/explicit behavior='develop' on
    it must not trip this check, since the "renders exactly as
    generative" claim would be false."""
    section = _section(voices=[
        {"register": "soprano", "entry_role": "subject", "motif": "call"},
        {"register": "alto", "entry_role": "answer", "motif": "call",
         "behavior": "develop"},
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
# 17. _check_harmony_pattern_silently_empty — RETIRED (known-issues #7).
#
# This check used to catch the INHERITED "pattern" harmony gap (section.
# rhythm='pattern', no explicit harmony_rhythm.rhythm, no harmony_pattern
# block -> harmony renders completely silent, no print, no error). That gap
# is now closed one layer upstream: SectionModel._validate_rhythm_
# dependencies() in schemas.py raises ValueError for both the explicit and
# the inherited case, so a SectionModel with this problem can no longer be
# constructed at all -- this lint check's trigger condition became
# unreachable. Keeping an unreachable check around is its own kind of silent
# trap (a future reader could believe it's still doing something), so it was
# deleted rather than left as dead code. The three cases it used to cover
# are now asserted as schema ValidationErrors instead -- see
# test_schemas.py's harmony-pattern-inheritance tests.
# ===========================================================================


# ===========================================================================
# _check_inherited_motif_coerced_to_free (known-issues #6)
#
# Unlike #7, this ISN'T a schema-error candidate: the coercion (inherited
# 'motif' -> 'free') is intentional, documented, deliberate behavior in
# harmony.py, not a bug. The gap was purely visibility -- a print-only
# status line at render time, nothing before render, nothing in lint. This
# check makes the same fact visible earlier, without changing what happens.
# ===========================================================================

def test_check_inherited_motif_coerced_to_free_fires():
    section = _section(rhythm="motif")
    found = list(_check_inherited_motif_coerced_to_free(section))
    assert len(found) == 1
    assert "inheriting rhythm='motif'" in found[0].setting
    assert "coerced to 'free'" in found[0].cause


def test_check_inherited_motif_coerced_to_free_fires_with_empty_harmony_rhythm_block():
    """A harmony_rhythm block that sets other fields (density/groove) but
    not .rhythm still inherits 'motif' -> still coerced -> still warns."""
    section = _section(rhythm="motif", harmony_rhythm={"density": "sparse"})
    found = list(_check_inherited_motif_coerced_to_free(section))
    assert len(found) == 1


def test_check_inherited_motif_coerced_to_free_silent_when_explicit_motif():
    """harmony_rhythm.rhythm='motif' set explicitly is honored, not
    coerced -- this check must stay silent."""
    section = _section(
        rhythm="motif",
        harmony_rhythm={"rhythm": "motif", "motif": {
            "intervals": [0, 2, 4], "rhythm": [1.0, 1.0, 2.0],
        }},
    )
    assert list(_check_inherited_motif_coerced_to_free(section)) == []


def test_check_inherited_motif_coerced_to_free_silent_when_section_rhythm_not_motif():
    section = _section(rhythm="free")
    assert list(_check_inherited_motif_coerced_to_free(section)) == []


def test_check_inherited_motif_coerced_to_free_silent_when_explicit_other_source():
    """Section rhythm is 'motif' but harmony_rhythm explicitly opts into a
    different source ('sustain') -- no coercion happens, nothing to warn."""
    section = _section(rhythm="motif", harmony_rhythm={"rhythm": "sustain"})
    assert list(_check_inherited_motif_coerced_to_free(section)) == []


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
# 19. _check_motif_never_developed
# ===========================================================================

def test_check_motif_never_developed_fires_with_no_develop_or_entry_role():
    piece = PieceModel.model_validate({
        "key": "C", "mode": "ionian", "tempo": 100,
        "motif": {"intervals": [0, 1, -1], "rhythm": [1.0, 1.0, 1.0]},
        "sections": [{"progression": ["i"], "rhythm": "free", "bars": 4}],
    })
    section = _section(voices=[{"register": "soprano", "behavior": "lyrical"}])
    found = list(_check_motif_never_developed(piece, [section]))
    assert len(found) == 1
    assert "no section's lead voice uses behavior='develop'" in found[0].cause


def test_check_motif_never_developed_silent_when_lead_voice_develops():
    piece = PieceModel.model_validate({
        "key": "C", "mode": "ionian", "tempo": 100,
        "motif": {"intervals": [0, 1, -1], "rhythm": [1.0, 1.0, 1.0]},
        "sections": [{"progression": ["i"], "rhythm": "free", "bars": 4}],
    })
    section = _section(voices=[{"register": "soprano", "behavior": "develop"}])
    assert list(_check_motif_never_developed(piece, [section])) == []


def test_check_motif_never_developed_silent_when_lead_voice_states_entry_role():
    """entry_role='subject'/'answer' plays the motif's pitch shape
    literally via generate_subject_entry -- this must count as "the
    motif was heard" the same way behavior='develop' does, even though
    the voice's `behavior` field itself stays at its unrelated default."""
    piece = PieceModel.model_validate({
        "key": "C", "mode": "ionian", "tempo": 100,
        "motif": {"intervals": [0, 1, -1], "rhythm": [1.0, 1.0, 1.0]},
        "sections": [{"progression": ["i"], "rhythm": "free", "bars": 4}],
    })
    section = _section(voices=[
        {"register": "soprano", "entry_role": "subject", "motif": "m"},
    ])
    assert list(_check_motif_never_developed(piece, [section])) == []


# ===========================================================================
# _check_lead_velocity_margin
# ===========================================================================

def test_check_lead_velocity_margin_fires_on_plain_default_section():
    """A section that never touches velocity at all (bare melody string,
    no voices[]) resolves to the real generator.py fallback (72), which
    clears bass/harmony's defaults (70/65) by only 2 points — well under
    LEAD_VELOCITY_MARGIN_TRIGGER (15). This SHOULD warn: it's the exact
    "lead nearly buried" case this check exists to catch. (Previously this
    was silent because lint.py re-declared LEAD_VELOCITY_DEFAULT as 88
    instead of importing the real 72 from generator.py — see known-issues
    #1. Fixed by importing the constant directly.)"""
    section = _section(melody="generative")
    found = list(_check_lead_velocity_margin(section))
    assert len(found) == 1
    assert "lead velocity=72" in found[0].setting
    assert "2 points" in found[0].cause


def test_check_lead_velocity_margin_fires_on_low_explicit_lead_velocity():
    section = _section(voices=[
        {"register": "soprano", "behavior": "lyrical", "velocity": 64},
    ])
    found = list(_check_lead_velocity_margin(section))
    assert len(found) == 1
    c = found[0]
    assert "lead velocity=64" in c.setting
    assert "bass defaults to 70" in c.cause
    assert "QUIETER" in c.cause  # 64 < 70: lead is actually below bass


def test_check_lead_velocity_margin_fires_when_margin_thin_but_positive():
    # 80 - 70 = 10, below the 15-point trigger, but still nominally louder.
    section = _section(voices=[
        {"register": "soprano", "behavior": "lyrical", "velocity": 80},
    ])
    found = list(_check_lead_velocity_margin(section))
    assert len(found) == 1
    assert "QUIETER" not in found[0].cause
    assert "10 points" in found[0].cause


def test_check_lead_velocity_margin_silent_when_explicit_lead_velocity_clears_it():
    section = _section(voices=[
        {"register": "soprano", "behavior": "lyrical", "velocity": 90},
    ])
    assert list(_check_lead_velocity_margin(section)) == []


# ===========================================================================
# Sanity: CHECKS registry contains all 17 section-only checks. Three more
# are piece-level and invoked directly by lint_piece instead of through this
# registry, because each needs context beyond a single SectionModel:
#   _check_melodic_variation_noop      — needs the theme's motif pool size
#   _check_motif_never_developed       — needs every section at once (it's
#                                         a piece-wide "was it ever used"
#                                         check, not a per-section one)
#   _check_harmony_melody_ratio        — needs the piece's primary motif,
#                                         for the "motif" rhythm-source case
# ===========================================================================

def test_checks_registry_has_nineteen_entries_plus_melodic_variation_separately():
    # Net unchanged at 19: _check_harmony_pattern_silently_empty was
    # retired (known-issues #7 — promoted to a schema ValidationError, so
    # the lint check's trigger condition became unreachable and was
    # deleted rather than left as dead code), and
    # _check_inherited_motif_coerced_to_free was added (known-issues #6 —
    # a genuinely new check, not a replacement for #7's).
    assert len(CHECKS) == 19
    assert _check_melodic_variation_noop not in CHECKS
    assert _check_motif_never_developed not in CHECKS
    assert _check_harmony_melody_ratio not in CHECKS
    assert _check_lead_velocity_margin in CHECKS
    assert _check_inherited_motif_coerced_to_free in CHECKS
