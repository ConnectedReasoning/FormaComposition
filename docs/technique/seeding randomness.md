# Generating "Threshold" — Quick Start

## Step 1: Set Up

Replace your current `intervals/music/melody.py` with the enhanced version:
```bash
cp melody_enhanced.py your_forma/intervals/music/melody.py
```

Verify your theme file exists:
```bash
your_forma/compositions/themes/theme_evening_water.json
```

---

## Step 2: Generate with Default Seed

```bash
python main.py theme_evening_water.json threshold_sonata_form.json --output threshold_seed_137.mid
```

This generates Threshold with seed 137 (the primary version designed).

**Expected output**: `threshold_seed_137.mid` (~5 minutes, 98 bars at 70 BPM)

---

## Step 3: Import to Logic Pro

1. **Create new session** (70 BPM, 4/4 time)
2. **File → Import → MIDI** → Select `threshold_seed_137.mid`
3. **Drag MIDI to arrange** (creates new software instrument track)
4. **Create 4 new tracks** (total 5: harmony, melody, counterpoint, bass, drums)
5. **Separate by channel** if needed

---

## Step 4: Assign Instruments

Use your Connected Reasoning toolkit:

| Track | Instrument | Plugin | Suggested Preset |
|-------|-----------|--------|------------------|
| Harmony | Pad | Pigments | "A Place to Rest" or "Warm Pad" |
| Melody | Synth | Juno-6V | "Vintage Synth" or "Warm Lead" |
| Counterpoint | Strings | Rev LX-24 or Mini Moog | "Choir Pad" or "String Section" |
| Bass | Sub | JUP-8000 V | "Sub Bass" or "Steady Pulse" |
| Drums | (optional) | Percussion/Drums | "Minimal Pulse" |

---

## Step 5: Ear-Check the Journey

Play through and listen for:

### Exposition (0:00–0:55)
- ✓ Sparse opening with contemplative subject
- ✓ Gradual density increase
- ✓ Secondary theme (inverted) sounds contrasting but related
- ✓ Clear two-theme structure

**Question**: Does the transition from primary to secondary feel natural?

### Development (0:55–2:40)
- ✓ Retrograde fragment feels like exploration (familiar reshuffled)
- ✓ Intensity gradually increases (Dev A → B → C)
- ✓ Climax (Dev C) at ~1:55 feels urgent
- ✓ Breath section releases tension

**Question**: Does the climax feel like a "peak"? Does the breath section feel like relief?

### Recapitulation (2:40–3:40)
- ✓ Original subject feels like "homecoming"
- ✓ Inverted subject in home key sounds resolved (not restless)
- ✓ Overall feel = recognition + transformation

**Question**: Does the recap feel different from the exposition, despite using the same material?

### Coda (3:40–4:12)
- ✓ Augmented (slowed) subject feels reflective
- ✓ Fade-out gradual (not abrupt)
- ✓ Final gesture feels complete

**Question**: Does the ending feel like resolution rather than just stopping?

---

## Step 6: Adjust and Regenerate

### If exposition feels flat:
- Try higher density in primary section (change to "medium")
- Increase velocity in counterpoint (change to 70 instead of 60)
- Try different seed (see below)

### If development doesn't feel like a journey:
- Increase compression in Dev C (try 0.4 instead of 0.45)
- Add reverb/delay to the melody track to simulate the fragmentation
- Adjust compression ratio

### If recap doesn't feel "different enough":
- Increase melody density (change "flowing" to "generative")
- Add more counterpoint dissonance
- Try different harmonic context (rewrite some progressions)

### If coda doesn't feel resolved:
- Extend the final progression (add a few more i chords)
- Reduce volume with automation (makes fade feel gradual)
- Add a final reverb tail (let it ring out)

---

## Step 7: Explore Different Seeds

The same composition with different seeds produces different melodic contours (same harmony, different voice leading):

```bash
# Seed 137 (current)
python main.py theme_evening_water.json threshold_sonata_form.json --output threshold_seed_137.mid

# Seed 100 (try this)
cp threshold_sonata_form.json threshold_seed_100.json
# Edit: change "seed": 137 → "seed": 100
python main.py theme_evening_water.json threshold_seed_100.json --output threshold_seed_100.mid

# Seed 200 (try this)
cp threshold_sonata_form.json threshold_seed_200.json
# Edit: change "seed": 137 → "seed": 200
python main.py theme_evening_water.json threshold_seed_200.json --output threshold_seed_200.mid

# Seed 75 (try this)
cp threshold_sonata_form.json threshold_seed_75.json
# Edit: change "seed": 137 → "seed": 75
python main.py theme_evening_water.json threshold_seed_75.json --output threshold_seed_75.mid
```

Listen to all 4 versions. Which one sings the best?

---

## Step 8: Pick the Winner

Compare the four seeds ear-check-style:

| Seed | Expo | Dev Climax | Recap | Winner? |
|------|------|-----------|-------|---------|
| 137 | ? | ? | ? | ○ |
| 100 | ? | ? | ? | ○ |
| 200 | ? | ? | ? | ○ |
| 75 | ? | ? | ? | ○ |

Choose the one where:
- Exposition melody is singable
- Climax feels urgent but not chaotic
- Recap feels like genuine resolution
- Coda feels meditative

---

## Step 9: Fine-Tune the Winner

Once you've chosen the best seed:

1. **Adjust volumes** to balance parts (melody clear, harmony supporting)
2. **Add reverb** to harmony track (long, lush reverb)
3. **Add delay** to melody track (1/4 note delay, synced to tempo)
4. **Adjust bass** density (if too present, lower velocity)
5. **Tweak counterpoint** register if it's fighting the melody

---

## Step 10: Finalize and Export

```bash
# Export as WAV from Logic Pro
File → Export → WAV (44.1 kHz, 16-bit)
Name: "Threshold_[seed]_final.wav"

# Or export as compressed audio for streaming
File → Export → AAC (256 kbps)
Name: "Threshold_[seed]_final.m4a"
```

---

## Step 11: Release Preparation

Once finalized:

1. **Create artwork** (3000×3000 PNG using your standard process)
2. **Write liner notes** (include seed used, techniques employed, form explanation)
3. **Tag metadata** (ID3 tags: artist="Connected Reasoning", genre="Ambient", etc.)
4. **Upload to DistroKid**:
   - Title: "Threshold"
   - Artist: "Connected Reasoning"
   - Genre: "Ambient" or "Experimental"
   - Description: Brief explanation of form and techniques

---

## What You're Demonstrating

"Threshold" proves that FormaComposition can produce **sophisticated, form-driven music** using:
- ✅ Sonata form (exposition/development/recap/coda)
- ✅ Motif transformations (inversion, retrograde, retrograde inversion, augmentation)
- ✅ Fugal techniques (subject/answer, episodes, stretto)
- ✅ Composer intent (all decisions in JSON)
- ✅ Reproducibility (seed-based variation)

This is **professional-grade compositional work**, not random generation.

---

## Timeline

- **Generation**: 5 minutes
- **Import + setup**: 10 minutes
- **Ear-check + notes**: 20 minutes
- **Adjust + regenerate seeds**: 30 minutes
- **Finalize + export**: 15 minutes
- **Metadata + artwork**: 20 minutes

**Total time to release: ~2 hours**

---

## If Something Doesn't Work

### "MIDI won't import"
- Check tempo matches (70 BPM in Logic)
- Check time signature (4/4)
- Try drag-and-drop instead of File → Import

### "Melody is too high/low"
- Adjust octave_bottom/octave_top in melody.py if needed (advanced)
- Or transpose the MIDI in Logic after import

### "Counterpoint overlaps melody"
- Change register to "above" or "below" in counterpoint section
- Adjust velocity (lower counterpoint, raise melody)

### "Climax doesn't feel urgent"
- Increase compression (try 0.35 instead of 0.45 in Dev C)
- Add attack/sustain adjustment to synth
- Layer a second melody line (create new track, duplicate melody)

### "I don't like this seed"
- Try another seed! That's the point
- Or adjust progressions (change the harmony, regenerate)

---

## You're Ready

You have:
- ✓ Sonata form composition (threshold_sonata_form.json)
- ✓ Enhanced melody generator (melody_enhanced.py)
- ✓ All Greenberg techniques built in
- ✓ Seed-based variation capability
- ✓ Detailed analysis of every section

**Generate Threshold. Listen to it. Refine it. Ship it.**

This is the future of Connected Reasoning.
