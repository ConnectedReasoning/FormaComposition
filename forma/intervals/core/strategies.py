"""
strategies.py — retired (item 9, ST-2a).

Every class and function this module used to own — HarmonyRhythmContext,
HarmonyChordContext, _build_chord_events, HarmonyStrategy and its four
concrete subclasses, _StrategyRegistry, HarmonyStrategyRegistry,
build_harmony_chord_context — has been relocated to intervals/music/harmony.py.

That move puts harmony's domain logic in the voice module that owns it,
matching how counterpoint.py and bass.py already own theirs, instead of
dispatching through a core-layer strategy file.

Grep-confirmed (2026-07): zero references to intervals.core.strategies
anywhere in the codebase. generator.py and strategies_typed.py both import
these names from intervals.music.harmony directly. This file is kept as a
marker rather than deleted outright, so anyone who goes looking for
"strategies.py" finds a pointer to where the logic actually lives now,
instead of a missing file with no explanation.
"""
