"""Selection policy helpers for trajectory analysis tools."""
from __future__ import annotations

import logging
import re
from typing import Optional

logger = logging.getLogger(__name__)

DEFAULT_CA_SELECTION = "protein and name CA"

# Atom-name tokens that already mean Cα (MDAnalysis / GROMACS style).
_CA_ATOM_RE = re.compile(
    r"(?:\bname\s+ca\b|\bcalpha\b|\bc-alpha\b|\bcα\b)",
    re.IGNORECASE,
)


def ensure_ca_selection(selection: Optional[str]) -> str:
    """Force whole-protein RMSF/DCCM selections onto Cα atoms.

    LLM plans often pass ``selection="protein"`` (all atoms). Plotting that as a
    residue line creates jagged "error-bar" artifacts. Preserve resid/segid
    filters by appending ``and name CA`` when Cα is not already requested.
    """
    sel = (selection or "").strip()
    if not sel:
        return DEFAULT_CA_SELECTION
    if _CA_ATOM_RE.search(sel):
        return sel
    # Ligand-only / non-protein selections are left alone.
    low = sel.lower()
    if "protein" not in low and "backbone" not in low and "resid" not in low:
        if "resname" in low or "name " in low:
            return sel
    if low in {"protein", "backbone", "all"}:
        return DEFAULT_CA_SELECTION
    coerced = f"({sel}) and name CA"
    if coerced != sel:
        logger.info("Coerced analysis selection %r → %r", sel, coerced)
    return coerced
