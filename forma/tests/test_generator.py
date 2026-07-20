import subprocess
import sys

from intervals.core.generator import derive_seed


def test_derive_seed_same_process_reproducible():
    """Calling derive_seed with the same inputs in the same process always
    returns the identical int."""
    a = derive_seed(42, 0, 3)
    b = derive_seed(42, 0, 3)
    assert a == b


def test_derive_seed_cross_process_reproducible():
    """derive_seed must not depend on PYTHONHASHSEED or any other
    per-process salt. This is the whole reason hash() was rejected in
    favor of hashlib.blake2b — verify a fresh subprocess with a different
    PYTHONHASHSEED produces the exact same value as this process."""
    in_process = derive_seed(42, 0, 3)

    env = _repo_env()
    env["PYTHONHASHSEED"] = "999"  # deliberately different from this process

    result = subprocess.run(
        [sys.executable, "-c",
         "from intervals.core.generator import derive_seed; print(derive_seed(42, 0, 3))"],
        capture_output=True,
        text=True,
        check=True,
        env=env,
    )
    subprocess_value = int(result.stdout.strip())

    assert subprocess_value == in_process


def test_derive_seed_varies_with_each_argument():
    """Sanity check that base_seed, form_index, and each axis actually
    participate in the hash — none of them silently ignored."""
    base = derive_seed(42, 0, 3)

    assert derive_seed(43, 0, 3) != base       # base_seed varies
    assert derive_seed(42, 1, 3) != base       # form_index varies
    assert derive_seed(42, 0, 4) != base       # axis varies
    assert derive_seed(42, 0, 3, 1) != base    # extra axis changes result


def test_derive_seed_returns_nonnegative_int():
    value = derive_seed(42, 0, 3)
    assert isinstance(value, int)
    assert 0 <= value < 2**63


def _repo_env():
    """Environment for the subprocess: inherit PATH etc., but make sure the
    repo root is importable (so `intervals.core.generator` resolves) and
    strip any inherited PYTHONHASHSEED so the caller can set its own."""
    import os
    from pathlib import Path

    repo_root = str(Path(__file__).resolve().parents[2])
    env = dict(os.environ)
    env.pop("PYTHONHASHSEED", None)
    existing_path = env.get("PYTHONPATH", "")
    env["PYTHONPATH"] = repo_root if not existing_path else f"{repo_root}{os.pathsep}{existing_path}"
    return env
