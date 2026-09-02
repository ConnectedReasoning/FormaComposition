# Bass Fix Impact Report — Full Catalog Comparison

Compared 60 rendered pieces, fixed vs. pre-fix `bass.py`, 
identical compositions and seeds, bass track only.

## Summary

- **44 of 60 pieces (73%) had incorrect bass notes before this fix.**

- 16 pieces unaffected (used the default C-aligned bass register — never triggered the bug).

- 'uniform' pattern = one consistent pitch-class error throughout (piece used one fixed custom bass_register).

- 'scattered' pattern = errors vary per chord root (more complex progressions interacting with a misaligned floor differently per root) — these are the pieces where the corruption was least predictable.


## Per-piece detail

| Piece | Notes changed | Total bass notes | Pattern | Pitch-class errors (semitones) |
|---|---|---|---|---|
| piece_aural_anthem | 447 | 484 | scattered | [0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11] |
| piece_still_seeking_synth | 419 | 419 | uniform | [9] |
| piece_eno | 402 | 402 | scattered | [8, 10] |
| piece_minimalism | 384 | 384 | scattered | [8, 10] |
| piece_still_seeking | 356 | 356 | uniform | [9] |
| piece_shake_v2 | 332 | 332 | uniform | [3] |
| piece_shake_v5 | 332 | 332 | uniform | [3] |
| piece_serialism | 316 | 334 | scattered | [0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11] |
| piece_stand | 312 | 312 | scattered | [8, 10] |
| piece_cool_jazz | 301 | 320 | scattered | [0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11] |
| piece_liquid_air_longer | 298 | 298 | uniform | [8] |
| piece_house_test | 260 | 260 | uniform | [8] |
| piece_trap_test | 260 | 260 | uniform | [8] |
| piece_whats_i_say | 242 | 242 | uniform | [8] |
| piece_rebecca | 193 | 205 | scattered | [0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11] |
| piece_sonata | 139 | 146 | scattered | [0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11] |
| piece_liquid_air_v2 | 125 | 128 | scattered | [2, 4, 5, 6, 7, 8, 9, 10] |
| piece_copper_dusk | 123 | 126 | scattered | [0, 1, 2, 4, 5, 7, 8, 9, 10] |
| piece_test_lofi | 121 | 134 | scattered | [1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11] |
| piece_return | 97 | 102 | scattered | [1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11] |
| piece_returned | 97 | 102 | scattered | [1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11] |
| piece_impressionism | 84 | 95 | scattered | [0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10] |
| piece_liquid_air_long | 80 | 80 | uniform | [8] |
| piece_drone_any | 72 | 72 | uniform | [8] |
| piece_drone_augmented_hexatonic | 60 | 60 | uniform | [3] |
| piece_still_cove_v4 | 58 | 58 | uniform | [3] |
| piece_liquid_air | 40 | 40 | uniform | [8] |
| piece_sanity_bass | 32 | 32 | scattered | [8, 10] |
| piece_focus | 15 | 15 | uniform | [8] |
| piece_training_with_chordbars | 15 | 15 | uniform | [8] |
| piece_apex_cadence | 14 | 14 | uniform | [8] |
| piece_sanity_blues | 12 | 12 | uniform | [3] |
| piece_sparse_baseline | 12 | 12 | uniform | [8] |
| piece_sparse_with_apex | 12 | 12 | uniform | [8] |
| piece_train | 12 | 12 | uniform | [8] |
| piece_ambient | 11 | 11 | uniform | [3] |
| piece_training_no_chordbars | 11 | 11 | uniform | [8] |
| piece_fugue_entry_demo | 8 | 8 | uniform | [8] |
| piece_gem_fugue | 8 | 8 | uniform | [3] |
| piece_gem_fugue_v2 | 8 | 8 | uniform | [3] |
| piece_finding0 | 6 | 6 | uniform | [3] |
| piece_sanity | 6 | 6 | uniform | [3] |
| piece_drone_blues | 1 | 1 | uniform | [8] |
| piece_drone_insen | 1 | 1 | uniform | [8] |