"""
lint.py — FormaComposition consumption linter.

Structural validity (is this a well-formed piece?) lives in schemas.py.
This module answers a different question: *given a well-formed piece, will
every setting the composer wrote actually be heard?*

The engine has a handful of consume-gates — places where a schema-legal field
is only read under some other setting. Set the field outside that gate and it
silently does nothing: no error, no sound, no clue. That silence is the whole
complaint this module exists to kill. Each gate is written down once, in
COUPLINGS below, and each check names the gate out loud when it's tripped.

These are *warnings*, not errors. Generation still produces valid MIDI — just
not the MIDI the composer thought they asked for. Nothing here blocks a render;
it only makes the ignored settings visible on every run.

Adding a coupling
-----------------
1. Document the gate in COUPLINGS (this is the human-readable registry).
2. Write a `_check_*` function that yields Contradiction(s) for a section.
3. Add it to CHECKS.
That's it — the report and main.py wiring pick it up automatically.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterator

from intervals.core.schemas import PieceModel, SectionModel, VoiceModel

# ─────────────────────────────────────────────────────────────────────────────
# Engine facts — the consume-gates, as verified in the engine source.
# These are the single source of truth for "feature X is only read when Y".
# If the engine changes, change these constants (and the render code) together.
# ─────────────────────────────────────────────────────────────────────────────

# melody.py: generate_melody() forwards `motif` to the behavior generator ONLY
# when behavior == "develop"; every other behavior drops it. So a motif's pitch
# shape is heard only under "develop".
MOTIF_CONSUMING_BEHAVIORS: frozenset[str] = frozenset({"develop"})

# bass.py: _CONTINUOUS_BASS_STYLES — these lines depend on stepwise continuity,
# so generate_bass() refuses bass_rest_probability for them (random drops would
# break the line rather than thin it).
CONTINUOUS_BASS_STYLES: frozenset[str] = frozenset({"walking", "melodic"})

# harmony path: harmony_rest_probability thins multi-onset chord windows. On the
# "sustain" source there is exactly one onset per harmonic span, so a rest roll
# there would delete the whole chord, not thin it — the field is a no-op.
SUSTAIN_HARMONY_SOURCE: str = "sustain"

# Unlike the gates above (verified engine facts — a field IS or ISN'T read
# under some condition), this one is a heuristic. Nothing is silently dropped
# here; a value is silently *derived*: SectionModel.bars_list() divides `bars`
# evenly across len(progression) whenever chord_bars is omitted, so the count
# of chords you chose to write becomes the divisor that sets how long each one
# is held. A short split (e.g. 2 bars/chord) is almost always intended; this
# threshold exists so the check only fires on splits long enough to plausibly
# be an accidental stretch rather than a deliberate slow harmonic rhythm.
# Tune freely — it's a judgment call, not a fact about the engine.
LONG_EVEN_SPLIT_BARS_THRESHOLD: float = 4.0


# A plain-language registry of every gate the linter knows about. This table is
# itself the answer to "which settings depend on which other settings?" — read
# it top to bottom to see every hidden coupling in one place.
COUPLINGS: list[str] = [
    "voice.motif       is heard only when voice.behavior == 'develop' "
    "(other behaviors ignore the motif's pitch shape).",
    "section.motif / section.motifs  are not read at render time; only the "
    "theme's motif pool is consulted. Section-level overrides do nothing.",
    "section.harmony_rest_probability  is a no-op on harmony source 'sustain' "
    "(single-onset spans can't be thinned, only deleted).",
    "section.bass_rest_probability  is ignored for bass_style 'walking' and "
    "'melodic' (continuous lines can't take random drops).",
    "section.note_length_range  is ignored when a groove is set (the groove "
    "fully specifies note durations — groove wins).",
    "section.note_length_range  is ignored when rhythm is 'pattern' or 'motif' "
    "(those sources supply their own onset/duration grid). Needs rhythm='free'.",
    "section.bars, without chord_bars, is split evenly across every chord in "
    "the progression — the chord *count* silently becomes the duration "
    "divisor. Heuristic: flagged only when the resulting split exceeds "
    f"{LONG_EVEN_SPLIT_BARS_THRESHOLD} bars/chord.",
]

# Rhythm sources that supply their own onset+duration grid, so the free
# note-length sampler is never reached (generator.py precomputes the events and
# passes them as an override, bypassing get_pattern's range branch).
GRID_OVERRIDING_RHYTHM_SOURCES: frozenset[str] = frozenset({"pattern", "motif"})


# ─────────────────────────────────────────────────────────────────────────────
# Finding type
# ─────────────────────────────────────────────────────────────────────────────

@dataclass(frozen=True)
class Contradiction:
    """One declared-but-ignored setting, with the reason and the fix."""
    where:   str   # "section 'verse'" / "section 'verse' → voice 2 (lead)"
    setting: str   # the field that won't take effect, e.g. "motif='call'"
    cause:   str   # the other setting that gates it out
    effect:  str   # what actually happens instead
    fix:     str   # how to make the setting take effect

    def format(self) -> str:
        return (
            f"{self.where}: {self.setting} but {self.cause} — {self.effect}. "
            f"{self.fix}"
        )


# ─────────────────────────────────────────────────────────────────────────────
# Individual checks. Each takes a SectionModel and yields Contradictions.
# ─────────────────────────────────────────────────────────────────────────────

def _voice_label(idx: int, voice: VoiceModel) -> str:
    # voices are 1-indexed for humans; there's no voice.name field, so fall
    # back to its register as a mild disambiguator.
    return f"voice {idx + 1} ({voice.v_register})"


def _check_voice_motif(section: SectionModel) -> Iterator[Contradiction]:
    """
    A melodic voice carries a motif but its behavior won't build pitches from
    it. Scoped deliberately to voices with an *explicit* motif field: that's
    the unambiguous "I attached this motif here" signal. We do NOT flag the
    section's own melody line against the theme motif — nearly every section
    is non-develop over a theme that has a motif, so that would fire on almost
    everything and mean nothing.

    Counterpoint voices (species set) go through counterpoint.py, not the
    melody develop path, so the motif gate doesn't apply — skip them.
    """
    for i, v in enumerate(section.voices or []):
        if v.species is not None:
            continue
        if v.motif is None:
            continue
        if v.behavior in MOTIF_CONSUMING_BEHAVIORS:
            continue
        motif_desc = v.motif if isinstance(v.motif, str) else "inline motif"
        yield Contradiction(
            where=f"section '{section.name or '?'}' → {_voice_label(i, v)}",
            setting=f"motif={motif_desc!r} is set",
            cause=f"behavior={v.behavior!r} ignores motifs",
            effect="the motif's pitch shape will not sound",
            fix="set this voice's behavior to 'develop' to hear the motif, "
                "or drop the motif field if the free line is intended.",
        )


def _check_section_motif_override(section: SectionModel) -> Iterator[Contradiction]:
    """
    section.motif / section.motifs are documented as restricting the motif pool
    for the section, but render-time motif resolution never reads them — only
    the theme's pool is consulted (see schemas.SectionModel.validate_against_theme).
    So they're a pure no-op today.
    """
    if section.motif is None and section.motifs is None:
        return
    which = "motif" if section.motif is not None else "motifs"
    yield Contradiction(
        where=f"section '{section.name or '?'}'",
        setting=f"section-level {which} is set",
        cause="the engine only reads the theme's motif pool at render time",
        effect="this section-level override does nothing",
        fix="define the motif in the theme, or attach it to a specific voice "
            "with behavior='develop'.",
    )


def _check_harmony_rest_on_sustain(section: SectionModel) -> Iterator[Contradiction]:
    """harmony_rest_probability can't thin a single-onset sustain span."""
    hr = section.harmony_rhythm
    if section.harmony_rest_probability <= 0.0:
        return
    if hr is not None and hr.rhythm == SUSTAIN_HARMONY_SOURCE:
        yield Contradiction(
            where=f"section '{section.name or '?'}'",
            setting=f"harmony_rest_probability={section.harmony_rest_probability}",
            cause="harmony_rhythm.rhythm='sustain' has one onset per span",
            effect="there is nothing to thin (a rest would delete the chord)",
            fix="use a multi-onset harmony source (motif/pattern/free) to thin "
                "the bed, or drop harmony_rest_probability.",
        )


def _check_bass_rest_on_continuous(section: SectionModel) -> Iterator[Contradiction]:
    """bass_rest_probability is refused for stepwise-continuous bass styles."""
    if section.bass_rest_probability <= 0.0:
        return
    if section.bass_style in CONTINUOUS_BASS_STYLES:
        yield Contradiction(
            where=f"section '{section.name or '?'}'",
            setting=f"bass_rest_probability={section.bass_rest_probability}",
            cause=f"bass_style={section.bass_style!r} is a continuous line",
            effect="the rests are dropped to keep the line stepwise",
            fix="use a non-continuous bass_style (e.g. root_fifth, pedal, "
                "steady) to add breath, or drop bass_rest_probability.",
        )


def _check_note_length_range_vs_groove(section: SectionModel) -> Iterator[Contradiction]:
    """note_length_range is overridden by a groove (groove owns durations)."""
    if section.note_length_range is None or section.groove is None:
        return
    yield Contradiction(
        where=f"section '{section.name or '?'}'",
        setting=f"note_length_range={section.note_length_range.as_tuple()}",
        cause=f"groove={section.groove!r} fully specifies note durations",
        effect="the range is ignored; the groove's own lengths are used",
        fix="drop the groove to sample lengths in-range, or drop "
            "note_length_range if the groove's durations are what you want.",
    )


def _check_note_length_range_vs_rhythm(section: SectionModel) -> Iterator[Contradiction]:
    """note_length_range needs rhythm='free'; pattern/motif supply their own grid."""
    if section.note_length_range is None:
        return
    if section.rhythm in GRID_OVERRIDING_RHYTHM_SOURCES:
        yield Contradiction(
            where=f"section '{section.name or '?'}'",
            setting=f"note_length_range={section.note_length_range.as_tuple()}",
            cause=f"rhythm={section.rhythm!r} supplies its own onset/duration grid",
            effect="the range never runs (the grid is used for durations)",
            fix="set rhythm='free' to sample lengths in-range, or drop "
                "note_length_range if the pattern/motif rhythm is intended.",
        )


def _check_even_chord_split(section: SectionModel) -> Iterator[Contradiction]:
    """
    chord_bars, not bars, is what actually controls each chord's duration.

    Omit chord_bars and SectionModel.bars_list() gives every chord in the
    progression an equal share of `bars` (bars / len(progression)) — so the
    number of chords you chose to write becomes the divisor that decides how
    long each one is held, even though "which chords" and "how long each one
    lasts" are independent musical decisions. A short progression dropped
    into a long section is silently stretched, with nothing in the render
    log to say so.

    Heuristic, not a hard gate (see LONG_EVEN_SPLIT_BARS_THRESHOLD): only
    fires when the even split works out to more than the threshold, since a
    short split (e.g. 2 bars/chord) is almost always exactly what was meant.
    Also skipped for a single-chord progression — there's nothing to split.
    """
    if section.chord_bars is not None:
        return
    n = len(section.progression)
    if n <= 1:
        return
    bars = section.bars or 8.0
    even = bars / n
    if even <= LONG_EVEN_SPLIT_BARS_THRESHOLD:
        return
    yield Contradiction(
        where=f"section '{section.name or '?'}'",
        setting=f"bars={bars} with {n} chords in progression",
        cause=f"no chord_bars — bars is split evenly across all {n} chords",
        effect=f"every chord is held for {even:.1f} bars, regardless of "
               f"whether that pacing was intended",
        fix=f"set chord_bars explicitly (a {n}-entry list) to control each "
            f"chord's duration independent of how many chords are listed.",
    )


CHECKS = [
    _check_voice_motif,
    _check_section_motif_override,
    _check_harmony_rest_on_sustain,
    _check_bass_rest_on_continuous,
    _check_note_length_range_vs_groove,
    _check_note_length_range_vs_rhythm,
    _check_even_chord_split,
]


# ─────────────────────────────────────────────────────────────────────────────
# Public API
# ─────────────────────────────────────────────────────────────────────────────

def lint_section(section: SectionModel) -> list[Contradiction]:
    """Run every check against one section."""
    found: list[Contradiction] = []
    for check in CHECKS:
        found.extend(check(section))
    return found


def lint_piece(piece: PieceModel) -> list[Contradiction]:
    """
    Run every check against every *unique* section definition.

    Song form expands the same named section many times in play order; we lint
    each definition once (song_sections values) so a repeated chorus doesn't
    report the same contradiction four times.
    """
    if piece.form_type == "song":
        sections = list((piece.song_sections or {}).values())
    else:
        sections = list(piece.sections or [])

    found: list[Contradiction] = []
    for section in sections:
        found.extend(lint_section(section))
    return found


def format_report(contradictions: list[Contradiction]) -> str:
    """
    Render findings as a compact, non-alarming block. Empty list → empty
    string (callers can skip printing entirely when clean).
    """
    if not contradictions:
        return ""
    lines = ["  ⚠  ignored settings (generation continues):"]
    for c in contradictions:
        lines.append(f"     • {c.format()}")
    return "\n".join(lines)
