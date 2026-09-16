"""
Phylogenetic tree tools for combined (multi-simulation) analysis.

Two cross-simulation trees, built on demand when the user asks for a
phylogenetic / sequence / structure tree:

  * ``build_sequence_phylo_tree`` — sequences are extracted from every input
    PDB, aligned pairwise, and turned into a % identity distance matrix. The
    matrix is clustered (UPGMA) and drawn as an unrooted phylogram.

  * ``build_structure_phylo_tree`` — CA coordinates are extracted from every
    input PDB; each pair is superposed on its sequence-aligned common residues
    (Kabsch) and the resulting CA-RMSD becomes the structural distance. The
    matrix is clustered and drawn the same way.

Both tools reuse the circular phylogram renderer from
``classification_clustering`` so the figures match the existing
``classification_phylo_tree.png`` style, and both emit a Newick file and a
distance-matrix CSV alongside the PNG.

Each function follows the same @tool convention used elsewhere in
src/analysis/ (returns a Dict[str, Any] with at least a ``success`` key).
"""
from __future__ import annotations

import csv
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

import numpy as np
from langchain.tools import tool

logger = logging.getLogger(__name__)

try:
    from scipy.cluster import hierarchy
    from scipy.spatial.distance import squareform

    HAS_SCIPY = True
except Exception:  # pragma: no cover
    HAS_SCIPY = False

try:
    import matplotlib

    matplotlib.use("Agg")
    HAS_MPL = True
except Exception:  # pragma: no cover
    HAS_MPL = False

try:
    from Bio.PDB import PDBParser, PPBuilder
    from Bio.Align import PairwiseAligner, substitution_matrices

    HAS_BIO = True
except Exception:  # pragma: no cover
    HAS_BIO = False


SEQUENCE_PHYLO_PLOT = "sequence_phylo_tree.png"
STRUCTURE_PHYLO_PLOT = "structure_phylo_tree.png"


# ── Structure / sequence extraction ──────────────────────────────────────────

def _structure_pdb_stems(label: str) -> List[str]:
    """Candidate basename stems for ``{stem}.pdb`` lookup.

    Campaign labels are often ``{uniprot}_ATP`` while the deposited structure is
    ``{uniprot}.pdb`` at the multi-sim base. Try the full label first, then
    peel common holo / ion suffixes.
    """
    stem = Path(str(label)).stem
    stems: List[str] = []
    seen: set = set()

    def _add(s: str) -> None:
        s = (s or "").strip()
        if s and s not in seen:
            seen.add(s)
            stems.append(s)

    _add(stem)
    # Peel trailing case suffixes one at a time (order matters).
    suffixes = (
        "_ATP_MG",
        "_ATP_2MG",
        "_2MG",
        "_MG",
        "_ATP",
        "_holo",
        "_apo",
    )
    cur = stem
    changed = True
    while changed:
        changed = False
        lower = cur.lower()
        for suf in suffixes:
            if lower.endswith(suf.lower()) and len(cur) > len(suf):
                cur = cur[: -len(suf)]
                _add(cur)
                changed = True
                break
    # Also try the sim folder name when label differs (caller may pass either).
    return stems


def resolve_structure_pdb(
    label: str,
    sim_dir: Optional[str],
    base_dir: Optional[str],
) -> Optional[str]:
    """
    Locate a PDB structure for *label*.

    Priority: user-provided base-level ``{base}/{stem}.pdb`` (including bare
    UniProt stems for ``*_ATP`` labels) → per-sim ``{sim}/{stem}.pdb`` → a
    representative reporter frame → a FEL basin PDB.
    """
    candidates: List[Path] = []
    stems = _structure_pdb_stems(label)
    if sim_dir:
        sd_name = Path(sim_dir).name
        for s in _structure_pdb_stems(sd_name):
            if s not in stems:
                stems.append(s)
    if base_dir:
        base = Path(base_dir)
        for stem in stems:
            candidates.append(base / f"{stem}.pdb")
    if sim_dir:
        sd = Path(sim_dir)
        for stem in stems:
            candidates.append(sd / f"{stem}.pdb")
        candidates.extend(sorted(sd.glob("reporter/*.pdb")))
        candidates.extend(sorted(sd.glob("analysis/basin_*.pdb")))
        candidates.extend(sorted(sd.glob("analysis/analysis/basin_*.pdb")))
    for c in candidates:
        if c.exists() and c.is_file():
            return str(c)
    return None


def _extract_sequence_and_ca(
    pdb_path: str,
) -> Tuple[str, np.ndarray]:
    """
    Return the concatenated one-letter sequence and matching CA coordinates
    (N x 3) for the polypeptide chains in *pdb_path*, in residue order.
    """
    parser = PDBParser(QUIET=True)
    structure = parser.get_structure("s", pdb_path)
    ppb = PPBuilder()
    seq_chars: List[str] = []
    ca_coords: List[np.ndarray] = []
    # Use only the first model (MD frame / static structure).
    model = next(iter(structure), None)
    if model is None:
        return "", np.zeros((0, 3))
    for pp in ppb.build_peptides(model):
        sequence = str(pp.get_sequence())
        residues = list(pp)
        for res, aa in zip(residues, sequence):
            if "CA" in res:
                seq_chars.append(aa)
                ca_coords.append(res["CA"].get_coord())
    if not ca_coords:
        return "", np.zeros((0, 3))
    return "".join(seq_chars), np.asarray(ca_coords, dtype=float)


def _build_aligner() -> "PairwiseAligner":
    aligner = PairwiseAligner()
    aligner.mode = "global"
    try:
        aligner.substitution_matrix = substitution_matrices.load("BLOSUM62")
    except Exception:
        pass
    aligner.open_gap_score = -10.0
    aligner.extend_gap_score = -0.5
    return aligner


def _matched_index_pairs(
    aligner: "PairwiseAligner", seq_a: str, seq_b: str
) -> List[Tuple[int, int]]:
    """Return aligned (non-gap) residue index pairs between two sequences."""
    if not seq_a or not seq_b:
        return []
    try:
        alignment = aligner.align(seq_a, seq_b)[0]
    except Exception:
        return []
    pairs: List[Tuple[int, int]] = []
    blocks_a, blocks_b = alignment.aligned
    for (a0, a1), (b0, b1) in zip(blocks_a, blocks_b):
        for k in range(a1 - a0):
            pairs.append((a0 + k, b0 + k))
    return pairs


def _sequence_identity(
    aligner: "PairwiseAligner", seq_a: str, seq_b: str
) -> float:
    """Fraction of identical residues among aligned positions (0..1)."""
    pairs = _matched_index_pairs(aligner, seq_a, seq_b)
    if not pairs:
        return 0.0
    identical = sum(1 for i, j in pairs if seq_a[i] == seq_b[j])
    denom = min(len(seq_a), len(seq_b)) or 1
    return identical / denom


def _kabsch_rmsd(coords_a: np.ndarray, coords_b: np.ndarray) -> float:
    """Optimal-superposition RMSD between two equal-length CA coordinate sets."""
    if coords_a.shape[0] < 3 or coords_a.shape != coords_b.shape:
        return float("nan")
    a = coords_a - coords_a.mean(axis=0)
    b = coords_b - coords_b.mean(axis=0)
    cov = a.T @ b
    v, _s, wt = np.linalg.svd(cov)
    d = np.sign(np.linalg.det(wt.T @ v.T))
    dmat = np.diag([1.0, 1.0, d])
    rot = wt.T @ dmat @ v.T
    a_rot = a @ rot
    diff = a_rot - b
    return float(np.sqrt((diff * diff).sum() / a.shape[0]))


# ── Tree drawing / export ────────────────────────────────────────────────────

def _linkage_to_newick(linkage_matrix: np.ndarray, leaf_names: Sequence[str]) -> str:
    """Convert a scipy linkage matrix to a Newick string."""
    tree = hierarchy.to_tree(linkage_matrix, rd=False)

    def _recurse(node, parent_dist: float) -> str:
        branch = max(parent_dist - node.dist, 0.0)
        if node.is_leaf():
            name = str(leaf_names[node.id]).replace(" ", "_").replace(",", "_")
            return f"{name}:{branch:.5f}"
        left = _recurse(node.get_left(), node.dist)
        right = _recurse(node.get_right(), node.dist)
        return f"({left},{right}):{branch:.5f}"

    return _recurse(tree, tree.dist) + ";"


def _distance_matrix_to_tree(
    dmat: np.ndarray,
    labels: Sequence[str],
    out_dir: Path,
    plot_name: str,
    newick_name: str,
    csv_name: str,
    title: str,
) -> Dict[str, Any]:
    """Cluster a symmetric distance matrix (UPGMA) and write PNG/Newick/CSV."""
    n = len(labels)
    condensed = squareform(dmat, checks=False)
    linkage_matrix = hierarchy.linkage(condensed, method="average")

    # Color leaves by a small number of clusters for readability.
    k = max(2, min(6, n // 4)) if n >= 4 else 1
    if k > 1:
        cluster_ids = hierarchy.fcluster(linkage_matrix, t=k, criterion="maxclust")
    else:
        cluster_ids = np.ones(n, dtype=int)

    plot_path = out_dir / plot_name
    if HAS_MPL:
        from src.analysis.classification_clustering import _plot_unrooted_phylo_tree

        _plot_unrooted_phylo_tree(
            linkage_matrix,
            list(labels),
            list(int(c) for c in cluster_ids),
            plot_path,
            title=title,
        )

    newick_path = out_dir / newick_name
    newick_str = _linkage_to_newick(linkage_matrix, labels)
    newick_path.write_text(newick_str, encoding="utf-8")

    csv_path = out_dir / csv_name
    with csv_path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.writer(fh)
        writer.writerow(["label"] + list(labels))
        for i, lab in enumerate(labels):
            writer.writerow([lab] + [f"{dmat[i, j]:.4f}" for j in range(n)])

    return {
        "plot_path": str(plot_path) if plot_path.exists() else None,
        "newick_file": str(newick_path),
        "distance_matrix_csv": str(csv_path),
        "n_clusters": int(k),
    }


# ── Shared PDB resolution / name mapping ─────────────────────────────────────

def _resolve_pdbs_and_names(
    sim_dirs: List[str],
    labels: List[str],
    base_dir: str,
    label_name_map: Optional[Dict[str, str]],
    user_goal: str,
) -> Tuple[List[str], List[str], List[str], List[str]]:
    """Return (used_pdbs, used_labels, display_names, missing_labels)."""
    from src.reporter.combined_reporter import (
        _parse_label_name_map,
        resolve_display_label,
    )

    name_map = label_name_map or _parse_label_name_map(user_goal or "")
    used_pdbs: List[str] = []
    used_labels: List[str] = []
    display_names: List[str] = []
    missing: List[str] = []

    for i, label in enumerate(labels):
        sim_dir = sim_dirs[i] if i < len(sim_dirs) else None
        # ``labels`` may already have been mapped to display names upstream, so
        # derive the raw simulation id from the sim directory basename for file
        # resolution (e.g. .../pseudoKin/o15197 → o15197 → o15197.pdb).
        raw_label = Path(sim_dir).name if sim_dir else Path(str(label)).stem
        pdb = resolve_structure_pdb(raw_label, sim_dir, base_dir)
        if not pdb:
            missing.append(label)
            continue
        used_pdbs.append(pdb)
        used_labels.append(raw_label)
        display_names.append(resolve_display_label(raw_label, name_map) or str(label))
    return used_pdbs, used_labels, display_names, missing


# ── Public @tools ────────────────────────────────────────────────────────────

@tool
def build_sequence_phylo_tree(
    sim_dirs: List[str],
    labels: List[str],
    working_dir: str,
    base_dir: str = "",
    label_name_map: Optional[Dict[str, str]] = None,
    user_goal: str = "",
) -> Dict[str, Any]:
    """
    Build a sequence-based phylogenetic tree across simulations.

    Sequences are extracted from each simulation's PDB structure, aligned
    pairwise, and converted to a (1 - percent identity) distance matrix that is
    clustered (UPGMA) and rendered as an unrooted phylogram.

    Args:
        sim_dirs: Per-simulation working directories (parallel to ``labels``).
        labels: Simulation labels (e.g. UniProt-style ids).
        working_dir: Combined analysis output directory (base/analysis).
        base_dir: Base multi-sim directory that holds ``{label}.pdb`` inputs.
        label_name_map: Optional {label: protein_name} for display labels.
        user_goal: Goal text (used to parse a name map if none is supplied).

    Returns:
        Dict with ``success``, ``plot_path`` (sequence_phylo_tree.png),
        ``newick_file``, ``distance_matrix_csv``, ``n_sequences``, ``labels``.
    """
    if not HAS_BIO or not HAS_SCIPY:
        return {
            "success": False,
            "error": "Biopython and scipy are required for sequence phylo trees",
        }
    out_dir = Path(working_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    base = base_dir or str(Path(working_dir).parent)

    pdbs, used_labels, display_names, missing = _resolve_pdbs_and_names(
        sim_dirs, labels, base, label_name_map, user_goal
    )
    if len(pdbs) < 3:
        return {
            "success": False,
            "error": f"Need >=3 structures with sequences; found {len(pdbs)}",
            "missing": missing,
        }

    sequences: List[str] = []
    kept_labels: List[str] = []
    kept_display: List[str] = []
    for pdb, lab, disp in zip(pdbs, used_labels, display_names):
        try:
            seq, _ca = _extract_sequence_and_ca(pdb)
        except Exception as exc:
            logger.warning("Sequence extraction failed for %s: %s", lab, exc)
            seq = ""
        if len(seq) >= 20:
            sequences.append(seq)
            kept_labels.append(lab)
            kept_display.append(disp)
        else:
            missing.append(lab)

    n = len(sequences)
    if n < 3:
        return {
            "success": False,
            "error": f"Need >=3 usable sequences; found {n}",
            "missing": missing,
        }

    aligner = _build_aligner()
    dmat = np.zeros((n, n), dtype=float)
    for i in range(n):
        for j in range(i + 1, n):
            identity = _sequence_identity(aligner, sequences[i], sequences[j])
            dist = 1.0 - identity
            dmat[i, j] = dmat[j, i] = dist

    tree = _distance_matrix_to_tree(
        dmat,
        kept_display,
        out_dir,
        SEQUENCE_PHYLO_PLOT,
        "sequence_phylo_tree.nwk",
        "sequence_phylo_distance_matrix.csv",
        title=f"Sequence-based phylogenetic tree ({n} structures, % identity)",
    )

    try:
        from src.analysis.summary_logger import append_analysis_summary

        append_analysis_summary(
            working_dir=working_dir,
            analysis_type="Sequence_Phylogenetic_Tree",
            statistics={
                "n_sequences": n,
                "mean_pairwise_identity": float(1.0 - dmat[np.triu_indices(n, 1)].mean())
                if n > 1
                else 1.0,
                "n_clusters": tree.get("n_clusters"),
            },
            files={
                "tree_plot": tree.get("plot_path") or "",
                "newick": tree.get("newick_file") or "",
                "distance_matrix": tree.get("distance_matrix_csv") or "",
            },
            metadata={"simulations": kept_labels, "missing_simulations": missing},
        )
    except Exception as exc:  # pragma: no cover
        logger.warning("append_analysis_summary (sequence phylo) failed: %s", exc)

    return {
        "success": True,
        "message": f"Sequence phylogenetic tree built from {n} structures",
        "plot_path": tree.get("plot_path"),
        "newick_file": tree.get("newick_file"),
        "distance_matrix_csv": tree.get("distance_matrix_csv"),
        "n_sequences": n,
        "labels": kept_labels,
        "missing": missing,
    }


@tool
def build_structure_phylo_tree(
    sim_dirs: List[str],
    labels: List[str],
    working_dir: str,
    base_dir: str = "",
    label_name_map: Optional[Dict[str, str]] = None,
    user_goal: str = "",
) -> Dict[str, Any]:
    """
    Build a structure-based phylogenetic tree across simulations.

    CA coordinates are extracted from each simulation's PDB structure. For each
    pair, the sequence-aligned common residues are superposed (Kabsch) and the
    resulting CA-RMSD becomes the structural distance. The distance matrix is
    clustered (UPGMA) and rendered as an unrooted phylogram.

    Args:
        sim_dirs: Per-simulation working directories (parallel to ``labels``).
        labels: Simulation labels (e.g. UniProt-style ids).
        working_dir: Combined analysis output directory (base/analysis).
        base_dir: Base multi-sim directory that holds ``{label}.pdb`` inputs.
        label_name_map: Optional {label: protein_name} for display labels.
        user_goal: Goal text (used to parse a name map if none is supplied).

    Returns:
        Dict with ``success``, ``plot_path`` (structure_phylo_tree.png),
        ``newick_file``, ``distance_matrix_csv``, ``n_structures``, ``labels``.
    """
    if not HAS_BIO or not HAS_SCIPY:
        return {
            "success": False,
            "error": "Biopython and scipy are required for structure phylo trees",
        }
    out_dir = Path(working_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    base = base_dir or str(Path(working_dir).parent)

    pdbs, used_labels, display_names, missing = _resolve_pdbs_and_names(
        sim_dirs, labels, base, label_name_map, user_goal
    )

    seqs: List[str] = []
    cas: List[np.ndarray] = []
    kept_labels: List[str] = []
    kept_display: List[str] = []
    for pdb, lab, disp in zip(pdbs, used_labels, display_names):
        try:
            seq, ca = _extract_sequence_and_ca(pdb)
        except Exception as exc:
            logger.warning("Structure extraction failed for %s: %s", lab, exc)
            seq, ca = "", np.zeros((0, 3))
        if len(seq) >= 20 and ca.shape[0] == len(seq):
            seqs.append(seq)
            cas.append(ca)
            kept_labels.append(lab)
            kept_display.append(disp)
        else:
            missing.append(lab)

    n = len(seqs)
    if n < 3:
        return {
            "success": False,
            "error": f"Need >=3 usable structures; found {n}",
            "missing": missing,
        }

    aligner = _build_aligner()
    dmat = np.zeros((n, n), dtype=float)
    max_finite = 0.0
    for i in range(n):
        for j in range(i + 1, n):
            pairs = _matched_index_pairs(aligner, seqs[i], seqs[j])
            if len(pairs) >= 20:
                idx_a = np.fromiter((p[0] for p in pairs), dtype=int)
                idx_b = np.fromiter((p[1] for p in pairs), dtype=int)
                rmsd = _kabsch_rmsd(cas[i][idx_a], cas[j][idx_b])
            else:
                rmsd = float("nan")
            dmat[i, j] = dmat[j, i] = rmsd
            if np.isfinite(rmsd):
                max_finite = max(max_finite, rmsd)

    # Replace non-comparable pairs (too few common residues) with a large but
    # finite penalty so clustering still succeeds.
    penalty = (max_finite or 1.0) * 1.5
    dmat[~np.isfinite(dmat)] = penalty
    np.fill_diagonal(dmat, 0.0)

    tree = _distance_matrix_to_tree(
        dmat,
        kept_display,
        out_dir,
        STRUCTURE_PHYLO_PLOT,
        "structure_phylo_tree.nwk",
        "structure_phylo_distance_matrix.csv",
        title=f"Structure-based phylogenetic tree ({n} structures, CA-RMSD Å)",
    )

    try:
        from src.analysis.summary_logger import append_analysis_summary

        triu = dmat[np.triu_indices(n, 1)]
        append_analysis_summary(
            working_dir=working_dir,
            analysis_type="Structure_Phylogenetic_Tree",
            statistics={
                "n_structures": n,
                "mean_pairwise_ca_rmsd": float(triu.mean()) if triu.size else 0.0,
                "max_pairwise_ca_rmsd": float(triu.max()) if triu.size else 0.0,
                "n_clusters": tree.get("n_clusters"),
            },
            files={
                "tree_plot": tree.get("plot_path") or "",
                "newick": tree.get("newick_file") or "",
                "distance_matrix": tree.get("distance_matrix_csv") or "",
            },
            metadata={"simulations": kept_labels, "missing_simulations": missing},
        )
    except Exception as exc:  # pragma: no cover
        logger.warning("append_analysis_summary (structure phylo) failed: %s", exc)

    return {
        "success": True,
        "message": f"Structure phylogenetic tree built from {n} structures",
        "plot_path": tree.get("plot_path"),
        "newick_file": tree.get("newick_file"),
        "distance_matrix_csv": tree.get("distance_matrix_csv"),
        "n_structures": n,
        "labels": kept_labels,
        "missing": missing,
    }
