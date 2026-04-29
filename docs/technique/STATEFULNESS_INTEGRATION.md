# Statefulness Pattern Integration

## Overview
This update integrates the statefulness pattern from Subsequence into FormaComposition, enabling motifs and voice generators to be context-aware without becoming brittle or self-referential.

**Release Date:** April 2, 2026  
**Version:** FormaComposition 2.1 (statefulness beta)

---

## What Changed

### 1. **Chord Context Builder** (`generator.py`)
Added `create_chord_context()` function that builds a context dict for each chord in a progression:

```python
{
    "chord_index": 1,           # Position in progression (0-indexed)
    "total_chords": 6,          # Total chords in section
    "next_chord": VoicedChord,  # The chord that follows this one
    "next_chord_root": "vi",    # Root name of next chord
    "bars_in_this_chord": 2.0,  # Duration of current chord
    "bars_in_next_chord": 3.0,  # Duration of next chord
    "section_name": "bloom",    # Name of the section
}
```

This context is built **once per chord** and passed through to all voice generators.

### 2. **Melody Generator Updates** (`melody.py`)
- `generate_melody_for_progression()` now accepts `section_name` parameter
- Builds `chord_context` for each chord and passes it to `generate_melody()`
- `generate_melody()` now accepts `context: Optional[dict]` parameter
- All behavior generators (`generate_generative`, `generate_lyrical`, `generate_sparse`, `generate_develop`) now accept `context` parameter

### 3. **Statefulness Logic in Lyrical Melody**
The `generate_lyrical()` function now uses next-chord context to create voice-leading gravity:

```python
# Near the end of a phrase, bias toward next chord's tones
is_last_note = (i == len(rhythm_events) - 1)
if is_last_note and context and next_chord_tones != chord_tones:
    candidates.extend(next_chord_tones)
```

**Why lyrical only?** Sparse and generative are too loosely-constrained to benefit. Develop uses motif transforms so context would conflict. Lyrical, which is already stepwise-constrained, gains obvious voice-leading improvement from knowing "the next chord is vi, land there."

---

## Philosophy: Why This Is Safe

**This design avoids the brittleness trap:**

- ✅ **Responsive, not predictive**: Generators look at what's *actually coming* (next chord), not at abstract rules about what *should* happen
- ✅ **Minimal state**: Only pass what's needed. No harmonic function analysis, no self-referential rules
- ✅ **Backward compatible**: All context parameters are `Optional[dict] = None`, so old code still works
- ✅ **Easy to test**: Generate Rebecca with statefulness, listen. If it improves, iterate. If not, revert.

**Avoids circular reference:** The generator never says "I think I should resolve." It says "Here's what's next, lean toward it." The composition leads; the generator follows.

---

## How to Use It

### For Rebecca (or any existing piece):
No changes needed. The system adds context automatically. Just generate as normal:

```python
from forma.intervals.core.generator import generate_piece

theme = load_theme("theme_rebecca.json")
piece = load_piece("rebecca.json")
generate_piece(theme, piece, "rebecca_stateful.mid")
```

The melody generator will automatically:
- Know which chord in the progression it's on
- Know what comes next
- Use that to inform last-note placement in lyrical sections

### For Custom Compositions:
If you extend the melody module with new behaviors, they'll automatically receive `context`:

```python
def generate_my_custom_behavior(
    rhythm_events,
    chord,
    scale_tones,
    chord_tones,
    prev_note,
    base_velocity,
    seed,
    context: Optional[dict] = None,  # Add this
) -> list[MelodyNote]:
    # Use context.get("next_chord") to look ahead
    # Use context.get("chord_index") for position
    pass
```

---

## Testing & Iteration

1. **Generate Rebecca:**
   ```bash
   python forma/main.py compositions/rebecca.json
   ```

2. **Listen in Logic Pro** with full Valhalla reverb chain (no changes to reverb needed)

3. **Does it flow better?**
   - Melody should feel less "surprised" by chord changes
   - Listen especially to transitions between chords (bars 1-2 of new chord)
   - Check "bloom" section (V→vi deceptive cadence) — melody should respond to the vi

4. **If it improves:** Keep it. Move to bass statefulness next.

5. **If it doesn't help:** Revert. The pattern itself is sound; maybe the implementation needs tuning.

---

## Next Steps (Not Yet Implemented)

- **Bass statefulness**: Bass already looks ahead (approach notes). Could extend to pass full context.
- **Counterpoint context**: Counterpoint generator could avoid voice-leading conflicts by knowing melody and bass context.
- **Form-aware density**: Section name in context enables density/behavior adjustments mid-piece.

Start with melody. Ship if it works. Expand later.

---

## Files Modified

- `forma/intervals/core/generator.py` — Added `create_chord_context()`, updated `generate_piece()` to pass section name
- `forma/intervals/music/melody.py` — Updated all generators to accept and use `context` parameter

No breaking changes. All existing compositions work unchanged.

---

## Technical Notes

- Context is created fresh for each chord, so memory is minimal
- Next chord lookup uses modulo wrapping: last chord's "next" points to first chord (useful for loops)
- Voice-leading bias in lyrical only extends candidates list; doesn't force a choice
- Random seed is maintained across chord boundaries, so behavior is deterministic and reproducible

---

## Questions?

If the melody sounds wrong or over-constrained after this update:
1. Listen without reverb (context effect should be subtle)
2. Check that your progressions have intentional deceptive cadences (V→vi). That's where statefulness matters most.
3. Revert to original if needed; this is a beta feature.

The goal: motifs that *respond* to harmony, not *predict* it.
