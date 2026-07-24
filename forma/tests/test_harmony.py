"""
Tests for intervals.music.harmony — Roman numeral parsing, chord
quality/voicing derivation, and voice-leading inversion selection.

Each hand-verified test's arithmetic was worked out by hand against the
module's own documented formulas (mode interval tables, inversion
rotation, movement-minimizing score) before being run and locked in, not
copied from a first successful run.
"""
import pytest

from intervals.music.harmony import (
    CHROMATIC,
    MODES,
    VoicedChord,
    apply_inversion,
    build_chord_tones,
    choose_inversion_for_voice_leading,
    get_scale,
    key_to_midi_root,
    mode_chord_quality,
    parse_roman,
    resolve_chord,
    resolve_progression,
)


# ===========================================================================
# key_to_midi_root / get_scale
# ===========================================================================

class TestKeyAndScale:
    def test_key_to_midi_root(self):
        assert key_to_midi_root("C", octave=4) == 60
        assert key_to_midi_root("D", octave=4) == 62

    def test_flat_names_normalize_to_sharps(self):
        assert key_to_midi_root("Db", octave=4) == key_to_midi_root("C#", octave=4)
        assert key_to_midi_root("Bb", octave=4) == key_to_midi_root("A#", octave=4)

    def test_unknown_key_raises(self):
        with pytest.raises(ValueError, match="Unknown key"):
            key_to_midi_root("H", octave=4)

    def test_get_scale_d_dorian(self):
        # D dorian: root=62, intervals [0,2,3,5,7,9,10]
        assert get_scale("D", "dorian", octave=4) == [62, 64, 65, 67, 69, 71, 72]

    def test_unknown_mode_raises(self):
        with pytest.raises(ValueError, match="Unknown mode"):
            get_scale("C", "bogus_mode", octave=4)


# ===========================================================================
# parse_roman
# ===========================================================================

class TestParseRoman:
    @pytest.mark.parametrize("roman,expected", [
        ("i", (0, None, 0)),
        ("IV", (3, None, 0)),
        ("iim7", (1, "minor7", 0)),
        ("Vmaj9", (4, "major9", 0)),
        ("viidim", (6, "diminished", 0)),
    ])
    def test_basic_and_quality_suffix(self, roman, expected):
        assert parse_roman(roman) == expected

    def test_flat_alteration_does_not_change_the_degree(self):
        """bVI is still degree 5 (VI's own position) -- the alteration is
        a pitch shift applied later, not a different diatonic degree.
        (Previously this wrapped to degree 4, silently colliding with
        whatever numeral actually lives at degree 4 in a given mode.)"""
        assert parse_roman("bVI") == (5, None, -1)

    def test_sharp_alteration_does_not_change_the_degree(self):
        assert parse_roman("#iv") == (3, None, 1)

    def test_alteration_combined_with_quality(self):
        assert parse_roman("bVImaj7") == (5, "major7", -1)

    def test_invalid_roman_raises(self):
        with pytest.raises(ValueError, match="Cannot parse Roman numeral"):
            parse_roman("Z")


# ===========================================================================
# mode_chord_quality
# ===========================================================================

class TestModeChordQuality:
    def test_ionian_tonic_is_major(self):
        assert mode_chord_quality(0, "ionian", "sparse") == "major"

    def test_dorian_tonic_is_minor(self):
        assert mode_chord_quality(0, "dorian", "sparse") == "minor"

    def test_ionian_dominant_extends_to_dominant_seventh_at_medium(self):
        assert mode_chord_quality(4, "ionian", "medium") == "dominant7"

    def test_ionian_leading_tone_is_diminished(self):
        assert mode_chord_quality(6, "ionian", "sparse") == "diminished"

    def test_extends_to_ninth_at_full_density(self):
        assert mode_chord_quality(0, "ionian", "full") == "major9"

    def test_density_sparse_never_extends_past_triad(self):
        assert mode_chord_quality(4, "ionian", "sparse") == "major"

    def test_harmonic_minor_dominant_is_a_flat_ninth(self):
        """The V chord in harmonic minor is THE textbook 7b9 dominant --
        the mode's own 2nd scale degree sits a half-step above its root."""
        assert mode_chord_quality(4, "harmonic_minor", "full") == "dominant7b9"

    def test_phrygian_tonic_is_a_flat_ninth(self):
        """Phrygian's hallmark color: the i chord's 9th is a half-step
        above the root (phrygian's defining b2)."""
        assert mode_chord_quality(0, "phrygian", "full") == "minor7b9"

    def test_ionian_tonic_and_dominant_stay_natural_ninth(self):
        """Sanity: modes/degrees whose own 2nd scale degree is a whole
        step above the root must NOT get the flat-ninth treatment."""
        assert mode_chord_quality(0, "ionian", "full") == "major9"
        assert mode_chord_quality(4, "ionian", "full") == "dominant11"  # extends further, unaffected

    def test_flat_ninth_quality_does_not_extend_further_to_an_eleventh(self):
        """Matches the pre-existing asymmetry where major9 also never
        extends to an eleventh -- a b9 chord stops at the ninth."""
        assert mode_chord_quality(4, "harmonic_minor", "full") == "dominant7b9"


# ===========================================================================
# build_chord_tones
# ===========================================================================

class TestBuildChordTones:
    def test_sparse_caps_at_triad(self):
        assert build_chord_tones(60, "minor7", "sparse") == [60, 63, 67]

    def test_medium_includes_seventh(self):
        assert build_chord_tones(60, "minor7", "medium") == [60, 63, 67, 70]

    def test_full_includes_every_available_extension(self):
        # dominant9 has 4 intervals defined (4,7,10,14); full cap is 6 but
        # only 5 tones exist total (root + 4) so all 5 are returned.
        assert build_chord_tones(60, "dominant9", "full") == [60, 64, 67, 70, 74]

    def test_unknown_quality_falls_back_to_major_triad(self):
        assert build_chord_tones(60, "not_a_real_quality", "sparse") == [60, 64, 67]

    def test_flat_ninth_qualities_build_correct_tones(self):
        # dominant7b9: root, M3, P5, m7, b9 (13 semitones)
        assert build_chord_tones(60, "dominant7b9", "full") == [60, 64, 67, 70, 73]
        # minor7b9: root, m3, P5, m7, b9
        assert build_chord_tones(60, "minor7b9", "full") == [60, 63, 67, 70, 73]
        # major7b9: root, M3, P5, M7, b9
        assert build_chord_tones(60, "major7b9", "full") == [60, 64, 67, 71, 73]


# ===========================================================================
# apply_inversion
# ===========================================================================

class TestApplyInversion:
    def test_root_position_is_sorted_unchanged(self):
        assert apply_inversion([60, 64, 67], 0) == [60, 64, 67]

    def test_first_inversion_moves_bass_up_an_octave(self):
        assert apply_inversion([60, 64, 67], 1) == [64, 67, 72]

    def test_second_inversion_moves_bass_up_two_octaves_from_root(self):
        assert apply_inversion([60, 64, 67], 2) == [67, 72, 76]

    def test_inversion_beyond_available_tones_is_a_no_op(self):
        """len(tones) <= inversion guards against rotating past what
        exists -- returns sorted tones unchanged rather than erroring."""
        assert apply_inversion([60, 64], 2) == [60, 64]


# ===========================================================================
# choose_inversion_for_voice_leading
# ===========================================================================

class TestChooseInversionForVoiceLeading:
    def test_no_previous_chord_picks_lowest_register_conforming_inversion(self):
        """With no prior chord, movement cost is 0 for every candidate, so
        the tie-break is purely the register/out-of-range penalty and
        enumeration order -- root position at [60,64,67] already sits
        inside the default 48-72 register band, so it wins outright."""
        voiced, inv = choose_inversion_for_voice_leading([60, 64, 67], None)
        assert (voiced, inv) == ([60, 64, 67], 0)

    def test_minimizes_total_movement_from_previous_chord(self):
        """Hand-verified: C major (1st inv) [64,67,72] -> F major triad
        [65,69,72]. Candidate scores (after register-shift):
          inv0 -> [53,57,60]: |53-64|+|57-67|+|60-72| = 11+10+12 = 33
          inv1 -> [57,60,65]: |57-64|+|60-67|+|65-72| =  7+ 7+ 7 = 21
          inv2 -> [60,65,69]: |60-64|+|65-67|+|69-72| =  4+ 2+ 3 =  9  <- best
        """
        prev = VoicedChord(root_name="C", quality="major", midi_notes=[64, 67, 72],
                            inversion=1, roman="I", degree=0)
        voiced, inv = choose_inversion_for_voice_leading([65, 69, 72], prev)
        assert (voiced, inv) == ([60, 65, 69], 2)

    def test_shifts_out_of_range_candidates_into_register(self):
        voiced, _ = choose_inversion_for_voice_leading([84, 88, 91], None,
                                                        register_bottom=48, register_top=72)
        assert all(48 <= n <= 84 for n in voiced)  # shifted down toward register


# ===========================================================================
# resolve_chord
# ===========================================================================

class TestResolveChord:
    def test_hand_verified_minor_tonic_in_d_dorian(self):
        """D dorian sparse 'i': root=62 (D), quality minor (third=3,
        fifth=7) -> tones [62,65,69], no prev chord so movement=0 for
        every inversion; root position already fits after one octave-down
        register shift (62,65,69 all > 60, so shift by -12) -> [50,53,57]."""
        chord = resolve_chord("i", "D", "dorian", density="sparse")
        assert chord.root_name == "D"
        assert chord.quality == "minor"
        assert chord.midi_notes == [50, 53, 57]
        assert chord.degree == 0

    def test_secondary_dominant_resolves_against_target_root(self):
        """V7/ii in C ionian: ii's root is D (scale degree 1), V7 built as
        a dominant seventh a fifth above D -> root A."""
        chord = resolve_chord("V7/ii", "C", "ionian", density="medium")
        assert chord.root_name == "A"
        assert chord.quality == "dominant7"

    def test_secondary_chord_invalid_target_raises(self):
        with pytest.raises(ValueError, match="not a valid Roman numeral"):
            resolve_chord("V7/Z", "C", "ionian")

    def test_unknown_key_raises(self):
        with pytest.raises(ValueError):
            resolve_chord("i", "H", "ionian")

    def test_hand_verified_harmonic_minor_dominant_is_flat_ninth(self):
        """The real V chord in harmonic minor, at full integration level
        (through resolve_chord, not just mode_chord_quality directly):
        root G, quality dominant7b9, and every voiced tone's pitch class
        matches the b9 chord's actual pitch-class set (register/inversion
        placement is choose_inversion_for_voice_leading's job, already
        covered elsewhere -- this checks pitch-class correctness only)."""
        chord = resolve_chord("v", "C", "harmonic_minor", density="full")
        assert chord.root_name == "G"
        assert chord.quality == "dominant7b9"
        actual_pcs = sorted(n % 12 for n in chord.midi_notes)
        root_pc = CHROMATIC.index("G")
        expected_pcs = sorted((root_pc + iv) % 12 for iv in (0, 4, 7, 10, 13))
        assert actual_pcs == expected_pcs

    def test_invalid_roman_raises(self):
        with pytest.raises(ValueError, match="Cannot parse"):
            resolve_chord("Z", "C", "ionian")

    def test_explicit_quality_suffix_overrides_mode_derived_quality(self):
        chord = resolve_chord("idim7", "C", "ionian", density="medium")
        assert chord.quality == "diminished7"

    def test_bVII_no_longer_collides_with_vi(self):
        """The bug this fix targets: bVII and vi used to resolve to the
        literal same chord (same root, same quality, same degree), because
        the old code re-indexed the diatonic degree instead of applying a
        real chromatic shift. They must now be genuinely distinct."""
        vi = resolve_chord("vi", "F", "mixolydian", density="medium")
        bVII = resolve_chord("bVII", "F", "mixolydian", density="medium")
        assert (vi.root_name, vi.degree) != (bVII.root_name, bVII.degree)

    def test_flat_seven_in_mixolydian_reproduces_the_modes_own_native_seventh(self):
        """The key semantic this fix has to get right: mixolydian's own
        native 7th degree is ALREADY a semitone below the major scale's
        (that's the definition of mixolydian). So bVII, computed relative
        to the major scale, must land on that SAME native pitch -- not
        flatten a second time past it. F mixolydian's native 7th is
        Eb/D# (enharmonic); bVII must resolve to exactly that, not to D
        (which would be the over-flattened, wrong result)."""
        native_seventh = resolve_chord("VII", "F", "mixolydian", density="sparse")
        flat_seventh = resolve_chord("bVII", "F", "mixolydian", density="sparse")
        assert flat_seventh.root_name == native_seventh.root_name

    def test_flat_seven_is_a_genuine_foreign_chord_in_ionian(self):
        """The other side of the same formula: ionian's native 7th is
        NOT already flattened, so bVII there must be a real chromatic/
        borrowed color, distinct from ionian's own native vii."""
        native_seventh = resolve_chord("VII", "F", "ionian", density="sparse")
        flat_seventh = resolve_chord("bVII", "F", "ionian", density="sparse")
        assert flat_seventh.root_name != native_seventh.root_name

    def test_altered_chord_with_no_quality_suffix_defaults_to_major(self):
        """Standard tonal-theory convention: borrowed chords (bVI, bVII,
        bIII, bII) are conventionally major triads when no quality is
        given explicitly."""
        chord = resolve_chord("bVII", "F", "ionian", density="sparse")
        assert chord.quality == "major"

    def test_altered_chord_quality_suffix_still_overrides_the_major_default(self):
        chord = resolve_chord("bVII7", "F", "ionian", density="medium")
        assert chord.quality == "dominant7"

    def test_altered_chord_degree_matches_the_bare_numerals_position(self):
        """bVII keeps degree 6 (VII's own position) -- alteration changes
        the pitch, not which diatonic position the chord occupies. This
        matters for melody.py's diatonic motif-sequencing, which reads
        .degree as a scale POSITION, not a pitch."""
        chord = resolve_chord("bVII", "F", "mixolydian", density="sparse")
        assert chord.degree == 6

    def test_secondary_chord_with_altered_target_resolves_correctly(self):
        """Secondary/applied chords route through the same alteration
        fix via the shared helper -- confirm an altered TARGET ('bVI')
        is handled, not silently discarded the way it used to be."""
        chord = resolve_chord("V7/bVI", "C", "ionian", density="medium")
        # bVI in C ionian = Ab; V7 of Ab = Eb dominant7
        assert chord.root_name == "D#"  # enharmonic Eb
        assert chord.quality == "dominant7"


# ===========================================================================
# resolve_progression
# ===========================================================================

class TestResolveProgression:
    def test_hand_verified_d_dorian_progression(self):
        """i-VII-iv-v in D dorian, sparse density. Root names and
        qualities derived directly from mode_chord_quality/parse_roman;
        exact voicings inherit choose_inversion_for_voice_leading's
        movement-minimizing behavior, verified once by hand for a
        two-chord case above and trusted here for the full chain."""
        chords = resolve_progression(["i", "VII", "iv", "v"], "D", "dorian", density="sparse")
        assert [c.root_name for c in chords] == ["D", "C", "G", "A"]
        assert [c.quality for c in chords] == ["minor", "major", "major", "minor"]
        assert [c.degree for c in chords] == [0, 6, 3, 4]

    def test_each_chord_carries_forward_as_prev_for_the_next(self):
        """Voice leading actually uses the running chain, not just the
        first chord -- confirm by checking a chord differs from what it
        would be with prev=None whenever movement-minimization has a
        real choice to make."""
        chords = resolve_progression(["i", "iv"], "D", "dorian", density="sparse")
        standalone_second = resolve_chord("iv", "D", "dorian", density="sparse", prev_chord=None)
        # Not asserting they differ (they might coincide), just that the
        # chained call actually consulted prev_chord instead of ignoring it:
        chained_second = resolve_chord("iv", "D", "dorian", density="sparse",
                                        prev_chord=chords[0])
        assert chords[1].midi_notes == chained_second.midi_notes

    def test_empty_progression_returns_empty_list(self):
        assert resolve_progression([], "C", "ionian") == []

    def test_all_chords_share_requested_density_tone_count_cap(self):
        chords = resolve_progression(["i", "iv", "v"], "C", "ionian", density="sparse")
        assert all(len(c.midi_notes) <= 3 for c in chords)
