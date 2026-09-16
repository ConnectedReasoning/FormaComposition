#!/usr/bin/env bash
#
# verify_migration.sh — render every migrated piece both before and after,
# and report whether the audio actually changed.
#
# Relies on the .json.bak files migrate_voices.py leaves behind by default
# (run without --no-backup and without --outdir). For each compositions/X.json
# that has a matching X.json.bak, this renders both and byte-diffs the MIDI.
#
# IMPORTANT: the .bak file is in the OLD (pre-migration) JSON schema —
# counterpoint[], second_melody, melody-as-dict. Once you've merged the
# refactored engine (schemas.py's _reject_retired_fields etc.), your current
# forma/main.py will REFUSE to render that old JSON — on purpose, that's the
# check doing its job. So the .bak must be rendered with the OLD engine, and
# the .json with the current one. Point --old-engine at a checkout of the
# engine from before the voices[] consolidation (a git worktree, a backup
# copy, whatever you kept). Without it, this script can't do the comparison
# and instead just smoke-tests that every piece still renders with the
# current engine.
#
# Usage (from the repo root, same place you run forma/main.py):
#   forma/verify_migration.sh --old-engine /path/to/pre-refactor-repo
#   forma/verify_migration.sh --old-engine /path/to/pre-refactor-repo compositions/piece_broadway_boogie_v8.json
#   forma/verify_migration.sh                                          # smoke test only, no diff
#   forma/verify_migration.sh --keep                                   # don't delete scratch output
#
# Exit status: 0 if every DIFFERS was expected (see EXPECTED_TO_DIFFER below)
# and nothing FAILed; 1 otherwise.

set -u

COMPOSITIONS_DIR="compositions"
SCRATCH="$(mktemp -d)"
KEEP=0
OLD_ENGINE=""
PIECES=()

while [ $# -gt 0 ]; do
    case "$1" in
        --keep)       KEEP=1; shift ;;
        --old-engine) OLD_ENGINE="$2"; shift 2 ;;
        *)            PIECES+=("$1"); shift ;;
    esac
done

if [ ${#PIECES[@]} -eq 0 ]; then
    PIECES=("$COMPOSITIONS_DIR"/*.json)
fi

OLD_MAIN=""
if [ -n "$OLD_ENGINE" ]; then
    OLD_MAIN="$OLD_ENGINE/forma/main.py"
    if [ ! -f "$OLD_MAIN" ]; then
        echo "! --old-engine given but $OLD_MAIN doesn't exist — aborting."
        exit 1
    fi
fi

# Pieces whose audio is EXPECTED to change (second_melody -> peer voice uses
# a different seed offset — see migrate_voices.py's report for the current
# list). Edit this to match what your migration run actually flagged, so an
# expected change reports as OK instead of a false alarm.
EXPECTED_TO_DIFFER=(
    # "piece_la_rail.json"
    # "piece_polymeter.json"
)

is_expected() {
    local name="$1"
    for e in "${EXPECTED_TO_DIFFER[@]:-}"; do
        [ "$e" = "$name" ] && return 0
    done
    return 1
}

n_identical=0
n_differs_expected=0
n_differs_unexpected=0
n_failed=0
n_skipped_no_bak=0

printf '%-42s %s\n' "PIECE" "RESULT"
printf '%-42s %s\n' "-----" "------"

for path in "${PIECES[@]}"; do
    [ -f "$path" ] || continue
    name="$(basename "$path")"
    bak="${path%.json}.json.bak"

    if [ ! -f "$bak" ]; then
        # No backup: this piece wasn't touched by the migration (or was run
        # with --no-backup/--outdir). Render once as a smoke test only.
        if python3 forma/main.py "$path" -o "$SCRATCH/${name%.json}.mid" >"$SCRATCH/${name}.log" 2>&1; then
            printf '%-42s %s\n' "$name" "ok (no .bak — not migrated)"
            n_skipped_no_bak=$((n_skipped_no_bak + 1))
        else
            printf '%-42s %s\n' "$name" "RENDER FAILED — see $SCRATCH/${name}.log"
            n_failed=$((n_failed + 1))
        fi
        continue
    fi

    if [ -z "$OLD_MAIN" ]; then
        # No old engine to compare against — smoke-test the migrated JSON
        # only. Byte-diffing needs --old-engine; see the header comment.
        if python3 forma/main.py "$path" -o "$SCRATCH/${name%.json}.mid" >"$SCRATCH/${name}.log" 2>&1; then
            printf '%-42s %s\n' "$name" "ok (no --old-engine — diff skipped)"
            n_skipped_no_bak=$((n_skipped_no_bak + 1))
        else
            printf '%-42s %s\n' "$name" "RENDER FAILED — see $SCRATCH/${name}.log"
            n_failed=$((n_failed + 1))
        fi
        continue
    fi

    before_mid="$SCRATCH/${name%.json}.before.mid"
    after_mid="$SCRATCH/${name%.json}.after.mid"

    if ! python3 "$OLD_MAIN" "$bak"  -o "$before_mid" >"$SCRATCH/${name}.before.log" 2>&1; then
        printf '%-42s %s\n' "$name" "FAIL (pre-migration render, old engine) — see $SCRATCH/${name}.before.log"
        n_failed=$((n_failed + 1))
        continue
    fi
    if ! python3 forma/main.py "$path" -o "$after_mid"  >"$SCRATCH/${name}.after.log" 2>&1; then
        printf '%-42s %s\n' "$name" "FAIL (post-migration render, current engine) — see $SCRATCH/${name}.after.log"
        n_failed=$((n_failed + 1))
        continue
    fi

    if cmp -s "$before_mid" "$after_mid"; then
        printf '%-42s %s\n' "$name" "IDENTICAL"
        n_identical=$((n_identical + 1))
    elif is_expected "$name"; then
        printf '%-42s %s\n' "$name" "DIFFERS (expected — second_melody)"
        n_differs_expected=$((n_differs_expected + 1))
    else
        printf '%-42s %s\n' "$name" "DIFFERS — UNEXPECTED, listen to this one"
        n_differs_unexpected=$((n_differs_unexpected + 1))
    fi
done

echo
echo "identical              : $n_identical"
echo "differs (expected)     : $n_differs_expected"
echo "differs (UNEXPECTED)   : $n_differs_unexpected"
echo "render failed           : $n_failed"
echo "no .bak / not migrated  : $n_skipped_no_bak"

if [ "$KEEP" = 1 ]; then
    echo
    echo "scratch output kept at: $SCRATCH"
else
    rm -rf "$SCRATCH"
fi

if [ "$n_differs_unexpected" -gt 0 ] || [ "$n_failed" -gt 0 ]; then
    exit 1
fi
exit 0
