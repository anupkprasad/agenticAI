#!/usr/bin/env python3
"""
Utility helpers for pseudokinase analysis and plotting.
Move common helper functions here so other scripts can import them.
"""

from pathlib import Path

# Reusable high-contrast color palette for plotting across the project.
# Import this list in plotting scripts: from src.python.utilities.utilities import CONTRAST_COLORS, get_contrast_palette
CONTRAST_COLORS = [
    "#E63946", "#06FFA5", "#FFD60A", "#118AB2", "#FF006E",
    "#8338EC", "#FB5607", "#3A86FF", "#06D6A0", "#FF9E00",
    "#C1121F", "#00B4D8", "#7209B7", "#F72585", "#4CC9F0",
    "#F77F00", "#2A9D8F", "#E76F51", "#264653", "#9D4EDD",
]

def get_contrast_palette(n: int = None, cycle: bool = True):
    """Return a list of contrast colors.

    Args:
        n: number of colors to return. If None returns the full palette.
        cycle: if True and n > len(CONTRAST_COLORS), cycle through the palette to reach n.

    Returns:
        list of hex color strings
    """
    if n is None:
        return CONTRAST_COLORS.copy()

    if n <= len(CONTRAST_COLORS):
        return CONTRAST_COLORS[:n]

    # n larger than palette
    if cycle:
        out = []
        i = 0
        while len(out) < n:
            out.append(CONTRAST_COLORS[i % len(CONTRAST_COLORS)])
            i += 1
        return out
    else:
        # Return full palette if not cycling
        return CONTRAST_COLORS.copy()





def list_directories_in_path(path: str, pattern: str = None):
    """List all directories in the given path."""
    p = Path(path)
    if pattern:
        return [str(x.name) for x in p.glob(pattern) if x.is_dir()]
    return [str(x.name) for x in p.iterdir() if x.is_dir()]

def list_uniprots_in_path(path: str, pattern: str = None):
    """List all UniProt IDs found in directory names within the given path."""
    dirs = list_directories_in_path(path, pattern)
    uniprot_ids = []
    for d in dirs:
        uid = d.split('_')[1]
        if uid:
            uniprot_ids.append(uid)
    return uniprot_ids

def get_uid_from_fullpath_dir(dir_name: str):
    """Extract UniProt ID from a directory name."""
    dir_name = Path(dir_name).name
    return dir_name.split('_')[1].upper()




# Note: avoid executing I/O at import time. Use helper functions above from scripts.