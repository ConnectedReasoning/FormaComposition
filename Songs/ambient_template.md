# Ambient Piece Template — Logic Pro Checklist

Oct 31, 2026 · @Manuel Hernandez

## 1. One-time project setup

Build this Logic project once and save it as a template; every piece then starts from it.

- [ ] Tempo 60 BPM, 4/4, 48 kHz / 24-bit. One beat equals one second, so a loop length in beats reads directly as seconds.
- [ ] Three summing stacks: Melody, Pads, Bass. Route every instrument track to its stack.
- [ ] One Analog Lab instance per track. Load the chosen patch once per role, then use Copy / Paste Channel Strip Settings to fill the other loops' tracks.
- [ ] Melody stack: Channel EQ, high-pass about 120 Hz, cut about 2 dB near 250 Hz.
- [ ] Pads stack: Channel EQ, high-pass about 150 Hz, cut 2-3 dB near 250 Hz.
- [ ] Bass stack: Channel EQ, high-pass about 40 Hz, gentle roll-off above about 400 Hz.
- [ ] Master: Loudness Meter, then Limiter with ceiling -1 dB, then Channel EQ left flat with the analyzer set to post.
- [ ] Reverb bus: leave off by default. Add it only if the patches sound too dry once stacked.

## 2. Per-piece workflow

Each new piece takes five steps, from the loop JSONs to staggered regions in the template.

1. Design the loops. Choose a key and mode, loop count and loop lengths (30-45 beats). Keep the loop lengths coprime-ish. With two loops, make their combined cycle longer than the piece.
2. Apply the melody rules so renders come out clean:
   - Every chord has at least one note starting inside it.
   - No note crosses a chord change.
   - Leave 2-3 beats of rest before the loop point.
3. Set the length. Passes = minutes x BPM / loop beats, rounded up. At 60 BPM a 20-minute piece is 1,200 beats: a 33-beat loop needs 37 passes. Fill `form` with that many `"loop"` entries and keep `form_type` set to `"song"`.
4. Render, then check. Every melody pass should be identical (one unique pass per file), harmony and bass the same, and file ends within a few seconds of each other.
5. Import into the template. One region per file, no copies. Stagger the start of each loop by several bars so the openings don't pile up.

## 3. Patches, placement and balance

Pick three patches per piece, then place each melody in its own register and filter it once, so there is no need to analyze all 15 tracks.

- [ ] Pick one patch per role (melody, pad, bass) using the tag recipe for the piece.
- [ ] Keep one bass track and one or two pad tracks audible. Mute the rest of the bass and pad tracks.
- [ ] Play one test note on each audible track and read the lowest strong peak in the analyzer. This gives the sounding pitch, which can differ from the MIDI note.
- [ ] Spread the melodies so each owns about an octave. Use region Transpose in octaves, not EQ.
- [ ] Set each track's high-pass at about 60% of its lowest sounding fundamental.
- [ ] Bass fundamental about 60-120 Hz. If a bass is too quiet on small speakers, add upper harmonics with a light tube-preamp stage instead of transposing higher.
- [ ] Starting balance: pads quietest, bass in the middle, melodies clearest. Adjust by ear, then leave the faders alone.

## 4. Loudness, fades and export

Target about -18 LUFS integrated with true peak at or below -1 dB, which suits background and sleep listening.

- [ ] Read integrated loudness on the Loudness Meter over a full pass of the piece, not just the opening.
- [ ] Master Limiter ceiling at -1 dB. If it works hard, lower the stack faders instead of pushing the limiter.
- [ ] Fade in over 5-10 seconds and fade out over 10-20 seconds.
- [ ] Bounce a 48 kHz / 24-bit WAV for the master, plus whatever compressed format the platform needs.
- [ ] Confirm the bounce length matches the plan (for example, 20:00).

## 5. QA listen

A piece is ready when the first two minutes, a random middle section and the last two minutes all pass the checks below.

- [ ] Listen to the first 2 minutes, a random 2 minutes in the middle, and the last 2 minutes.
- [ ] No clicks, dropouts or cut-off notes at the loop points. Check at least two loop boundaries.
- [ ] No peak where several notes coincide. Watch the limiter for sudden gain reduction.
- [ ] Low end is clear: no beating or blur around 60-100 Hz.
- [ ] Low-mid is clear: no buildup around 200-400 Hz.
- [ ] Listen on headphones, laptop speakers and a phone, and check the mix in mono.
- [ ] Nothing in the first 10 minutes sounds like an obvious repeat.

## 6. Disclosure, publishing and catalog log

Describe the method honestly everywhere, and keep a one-line record of each piece's recipe so the catalog stays varied.

- [ ] Describe the process plainly in the description. Check each platform's and community's current AI-disclosure rules before posting.
- [ ] Use visuals that are not AI-generated, or label them clearly where the rules allow. Real photos with slow crossfades are the safe default.
- [ ] Write the title, description and thumbnail with the discoverability skill.
- [ ] Log the recipe: key and mode, tonal centres, loop count and lengths, passes, BPM, patches, register and date released.
- [ ] Before starting the next piece, compare its recipe with the last three. Change at least three of the following: mode, register, loop count, density, patch set, tempo.
