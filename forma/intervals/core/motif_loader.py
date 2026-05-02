"""
motif_loader.py — Intervals Engine
Standalone motif library management.

Motifs are atomic musical DNA stored in individual JSON files.
Themes reference motifs by name, allowing reuse across multiple themes.

Motif file structure:
  compositions/motifs/motif_<name>.json
  {
    "motif": {
      "name": "rebecca",
      "intervals": [2, -1, 3, -2],
      "rhythm": [1.0, 0.5, 0.5, 1.0],
      "transform_pool": ["inversion", "retrograde", ...]
    }
  }

Usage:
  from intervals.core.motif_loader import load_motif
  motif = load_motif("rebecca", motifs_dir="./compositions/motifs")
"""

import json
import os
from pathlib import Path
from typing import Optional

from intervals.music.motif import Motif, from_dict as motif_from_dict


def load_motif(name: str, motifs_dir: Optional[str] = None) -> Motif:
    """
    Load a motif by name from the motif library.

    Args:
        name:        Motif name (without 'motif_' prefix or '.json' extension)
        motifs_dir:  Directory containing motif files (default: ./compositions/motifs)

    Returns:
        Motif object

    Raises:
        FileNotFoundError: If motif file doesn't exist
        ValueError: If motif JSON is malformed
    """
    if motifs_dir is None:
        # Default to compositions/motifs relative to current working directory
        motifs_dir = os.path.join("compositions", "motifs")

    # Build filename: motif_<name>.json
    filename = f"motif_{name}.json"
    filepath = os.path.join(motifs_dir, filename)

    if not os.path.exists(filepath):
        raise FileNotFoundError(
            f"Motif '{name}' not found at {filepath}. "
            f"Available motifs: {list_available_motifs(motifs_dir)}"
        )

    with open(filepath) as f:
        data = json.load(f)

    # Unwrap if wrapped in "motif" key
    motif_dict = data.get("motif", data)

    if "intervals" not in motif_dict:
        raise ValueError(
            f"Motif file {filepath} is missing 'intervals' key. "
            f"Expected structure: {{'motif': {{'intervals': [...], 'rhythm': [...]}}}}"
        )

    return motif_from_dict(motif_dict)


def list_available_motifs(motifs_dir: Optional[str] = None) -> list[str]:
    """
    List all available motif names in the library.

    Args:
        motifs_dir: Directory containing motif files (default: ./compositions/motifs)

    Returns:
        List of motif names (without 'motif_' prefix or '.json' extension)
    """
    if motifs_dir is None:
        motifs_dir = os.path.join("compositions", "motifs")

    if not os.path.exists(motifs_dir):
        return []

    motif_files = [
        f for f in os.listdir(motifs_dir)
        if f.startswith("motif_") and f.endswith(".json")
    ]

    # Extract names: "motif_rebecca.json" → "rebecca"
    return [f[6:-5] for f in motif_files]


def save_motif(motif: Motif, motifs_dir: Optional[str] = None) -> str:
    """
    Save a motif to the library.

    Args:
        motif:      Motif object to save
        motifs_dir: Directory for motif files (default: ./compositions/motifs)

    Returns:
        Path to saved file
    """
    if motifs_dir is None:
        motifs_dir = os.path.join("compositions", "motifs")

    os.makedirs(motifs_dir, exist_ok=True)

    filename = f"motif_{motif.name}.json"
    filepath = os.path.join(motifs_dir, filename)

    # Wrap in "motif" key for consistency with theme/piece format
    from intervals.music.motif import to_dict
    data = {"motif": to_dict(motif)}

    with open(filepath, "w") as f:
        json.dump(data, f, indent=2)

    return filepath


# ---------------------------------------------------------------------------
# Backward compatibility helper
# ---------------------------------------------------------------------------

def resolve_motif_from_theme(theme: dict, motifs_dir: Optional[str] = None) -> Optional[Motif]:
    """
    Resolve a motif from a theme dict, supporting both old and new formats.

    Old format (embedded motif):
      theme = {
        "motif": { "intervals": [...], "rhythm": [...] }
      }

    New format (motif reference):
      theme = {
        "motif": "rebecca"  # References motifs/motif_rebecca.json
      }

    Args:
        theme:      Theme dictionary
        motifs_dir: Motif library directory

    Returns:
        Motif object, or None if no motif defined
    """

    # Priority 1: Explicit motif (embedded dict or name reference)
    if "motif" in theme:
        motif_value = theme["motif"]

        # New format: string reference to motif library
        if isinstance(motif_value, str):
            return load_motif(motif_value, motifs_dir)

        # Old format: embedded dict
        elif isinstance(motif_value, dict):
            return motif_from_dict(motif_value)

    return None


def resolve_motif_pool_from_theme(theme: dict, motifs_dir: Optional[str] = None) -> list:
    """
    Resolve the motif pool from a theme dict.

    If theme has a 'motifs' array, returns all motifs in it as a list of
    dicts (ready for use in generation). The first motif in the array is
    the primary — it anchors the rhythm for the section.

    If theme has only a single 'motif', returns a one-element list so
    callers can always treat the result as a pool.

    Returns [] if no motif is defined.
    """
    from intervals.music.motif import to_dict as motif_to_dict

    # 'motifs' array takes precedence
    motifs_raw = theme.get("motifs")
    if motifs_raw and isinstance(motifs_raw, list):
        pool = []
        for m in motifs_raw:
            if isinstance(m, str):
                pool.append(motif_to_dict(load_motif(m, motifs_dir)))
            elif isinstance(m, dict):
                pool.append(m)
        return pool

    # Fall back to single motif
    single = resolve_motif_from_theme(theme, motifs_dir)
    if single:
        return [motif_to_dict(single)]
    return []

if __name__ == "__main__":
    print("=== Intervals Engine — motif_loader.py demo ===\n")

    # List available motifs
    motifs = list_available_motifs()
    print(f"Available motifs: {motifs}")

    if motifs:
        # Load first motif
        motif = load_motif(motifs[0])
        print(f"\nLoaded motif: {motif}")
        print(f"  Intervals: {motif.intervals}")
        print(f"  Rhythm: {motif.rhythm}")
        print(f"  Contour: {''.join(motif.contour())}")

# ---------------------------------------------------------------------------
# Quick test / demo
# ---------------------------------------------------------------------------
