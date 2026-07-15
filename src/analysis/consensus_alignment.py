"""
Consensus sequence alignment for cross-simulation coordinate mapping.

Builds a star multiple-sequence alignment (MSA) to a user-chosen reference
sequence, exports an inspectable residue map, and defines consensus columns
for reference-projected PCA on mapped Cα atoms.

Inputs (any one):
  * ``pdb_files`` + ``labels``
  * ``fasta_file``
  * ``sim_dirs`` + ``labels`` (PDB resolved like phylo_tree tools)

Outputs (under ``working_dir``):
  * ``reference_msa_alignment.fasta`` — reference row first, gapped MSA
  * ``reference_msa_residue_map.csv`` — per-column mappings for manual review
  * ``reference_msa_alignment.json`` — machine-readable alignment + consensus indices
"""
from __future__ import annotations

import csv
import json
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

import numpy as np
from langchain.tools import tool

from src.preprocess.structure_remodel.sequence_utils import (
    ChainSequence,
    extract_chain_sequences,
    pick_default_chain,
)

logger = logging.getLogger(__name__)

try:
    from Bio.Align import PairwiseAligner, substitution_matrices

    HAS_BIO = True
except Exception:  # pragma: no cover
    HAS_BIO = False

DEFAULT_ALIGNMENT_FASTA = "reference_msa_alignment.fasta"
DEFAULT_RESIDUE_MAP_CSV = "reference_msa_residue_map.csv"
DEFAULT_ALIGNMENT_JSON = "reference_msa_alignment.json"


def _json_safe(obj: Any) -> Any:
    """Convert numpy scalars to native Python types for JSON export."""
    if isinstance(obj, dict):
        return {k: _json_safe(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_json_safe(v) for v in obj]
    if isinstance(obj, (np.integer,)):
        return int(obj)
    if isinstance(obj, (np.floating,)):
        return float(obj)
    return obj


# ── Sequence loading ──────────────────────────────────────────────────────────


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


def load_sequences_from_fasta(fasta_file: str) -> Dict[str, ChainSequence]:
    """Parse a FASTA file into label → ChainSequence (1-based pseudo resids)."""
    path = Path(fasta_file)
    if not path.is_file():
        raise FileNotFoundError(f"FASTA file not found: {fasta_file}")

    chains: Dict[str, ChainSequence] = {}
    label: Optional[str] = None
    chunks: List[str] = []

    with open(path, encoding="utf-8") as fh:
        for raw in fh:
            line = raw.strip()
            if not line:
                continue
            if line.startswith(">"):
                if label and chunks:
                    seq = "".join(chunks)
                    chains[label] = ChainSequence(
                        chain_id="A",
                        sequence=seq,
                        resids=list(range(1, len(seq) + 1)),
                        resnames=["UNK"] * len(seq),
                    )
                label = line[1:].split()[0]
                chunks = []
            else:
                chunks.append(line.replace(" ", "").upper())

    if label and chunks:
        seq = "".join(chunks)
        chains[label] = ChainSequence(
            chain_id="A",
            sequence=seq,
            resids=list(range(1, len(seq) + 1)),
            resnames=["UNK"] * len(seq),
        )

    if not chains:
        raise ValueError(f"No sequences parsed from {fasta_file}")
    return chains


def load_sequences_from_pdbs(
    pdb_files: Sequence[str],
    labels: Sequence[str],
    chain_id: Optional[str] = None,
) -> Dict[str, ChainSequence]:
    """Extract the longest (or chosen) protein chain from each PDB."""
    if len(pdb_files) != len(labels):
        raise ValueError("pdb_files and labels must have the same length")

    chains: Dict[str, ChainSequence] = {}
    for pdb, label in zip(pdb_files, labels):
        all_chains = extract_chain_sequences(pdb, chain_id=chain_id)
        cid = chain_id or pick_default_chain(all_chains)
        chains[str(label)] = all_chains[cid]
    return chains


def _resolve_pdbs_from_sims(
    sim_dirs: Sequence[str],
    labels: Sequence[str],
    base_dir: str,
) -> Tuple[List[str], List[str], List[str]]:
    from src.analysis.phylo_tree import resolve_structure_pdb

    pdbs: List[str] = []
    used_labels: List[str] = []
    missing: List[str] = []
    for sim_dir, label in zip(sim_dirs, labels):
        pdb = resolve_structure_pdb(str(label), str(sim_dir), base_dir)
        if pdb:
            pdbs.append(pdb)
            used_labels.append(str(label))
        else:
            missing.append(str(label))
    return pdbs, used_labels, missing


# ── Star MSA to reference ─────────────────────────────────────────────────────


def _pairwise_gapped_strings(
    ref: ChainSequence,
    other: ChainSequence,
    aligner: "PairwiseAligner",
) -> Tuple[str, str, List[Tuple[Optional[int], Optional[int]]]]:
    """Return gapped strings and (ref_idx, other_idx) pairs per alignment column."""
    if not ref.sequence or not other.sequence:
        return "", "", []

    aln = aligner.align(ref.sequence, other.sequence)[0]
    indices = aln.indices
    if indices is None or len(indices) != 2:
        return "", "", []

    ref_path, oth_path = indices[0], indices[1]
    ref_chars: List[str] = []
    oth_chars: List[str] = []
    pairs: List[Tuple[Optional[int], Optional[int]]] = []

    for ri, oi in zip(ref_path, oth_path):
        if ri != -1:
            ref_chars.append(ref.sequence[ri])
        else:
            ref_chars.append("-")
        if oi != -1:
            oth_chars.append(other.sequence[oi])
        else:
            oth_chars.append("-")
        pairs.append(
            (ri if ri != -1 else None, oi if oi != -1 else None)
        )

    return "".join(ref_chars), "".join(oth_chars), pairs


def _reference_indexed_row(
    ref: ChainSequence,
    other: ChainSequence,
    pairs: List[Tuple[Optional[int], Optional[int]]],
) -> str:
    """Pad ``other`` to reference length using matched residue pairs (gaps elsewhere)."""
    chars = ["-"] * len(ref.sequence)
    for ref_idx, oth_idx in pairs:
        if ref_idx is not None and oth_idx is not None:
            chars[ref_idx] = other.sequence[oth_idx]
    return "".join(chars)


def build_star_msa_to_reference(
    chains: Dict[str, ChainSequence],
    reference_label: str,
) -> Dict[str, Any]:
    """
    Build a star alignment anchored on ``reference_label``.

    Each sequence is globally aligned to the reference independently.
    Consensus columns are keyed by **reference residue index** (one column per
    reference residue). FASTA rows are reference-length strings (gap = no
    aligned residue in that protein).
    """
    if reference_label not in chains:
        raise KeyError(f"Reference label {reference_label!r} not in chain set")

    aligner = _build_aligner()
    ref = chains[reference_label]
    other_labels = [k for k in sorted(chains.keys()) if k != reference_label]
    labels = [reference_label] + other_labels

    columns: List[Dict[str, Any]] = []
    for i in range(len(ref.sequence)):
        columns.append({
            "msa_col": i,
            "reference_seq_index": i,
            "reference_resid": ref.resids[i],
            "reference_aa": ref.sequence[i],
            "mappings": {
                reference_label: {
                    "seq_index": i,
                    "resid": ref.resids[i],
                    "aa": ref.sequence[i],
                }
            },
        })

    rows: Dict[str, str] = {reference_label: ref.sequence}

    for label in other_labels:
        other = chains[label]
        ref_gapped, oth_gapped, pairs = _pairwise_gapped_strings(ref, other, aligner)
        if not pairs:
            logger.warning("Empty alignment for %s vs reference", label)
            rows[label] = "-" * len(ref.sequence)
            continue

        rows[label] = _reference_indexed_row(ref, other, pairs)
        for ref_idx, oth_idx in pairs:
            if ref_idx is None or oth_idx is None:
                continue
            columns[ref_idx]["mappings"][label] = {
                "seq_index": int(oth_idx),
                "resid": int(other.resids[oth_idx]),
                "aa": other.sequence[oth_idx],
            }

        # Store full gapped pairwise alignment width for optional inspection
        rows[f"{label}__pairwise_gapped"] = oth_gapped

    width = len(ref.sequence)
    return {
        "reference_label": reference_label,
        "msa_width": width,
        "rows": {k: v for k, v in rows.items() if not k.endswith("__pairwise_gapped")},
        "pairwise_gapped_rows": {k: v for k, v in rows.items() if k.endswith("__pairwise_gapped")},
        "columns": columns,
        "labels": labels,
    }


def select_consensus_positions(
    msa: Dict[str, Any],
    *,
    min_coverage: float = 0.85,
    require_reference: bool = True,
) -> List[Dict[str, Any]]:
    """
    Return consensus columns where mapped sequences meet ``min_coverage``.

    Only columns with a reference residue are considered when
    ``require_reference`` is True (default).
    """
    labels: List[str] = msa.get("labels") or []
    n_labels = max(len(labels), 1)
    threshold = float(min_coverage) * n_labels
    consensus: List[Dict[str, Any]] = []

    for col in msa.get("columns", []):
        if require_reference and col.get("reference_seq_index") is None:
            continue
        mappings = col.get("mappings") or {}
        present = [lab for lab in labels if lab in mappings]
        if len(present) < threshold:
            continue
        entry = {
            "consensus_index": len(consensus),
            "msa_col": col.get("msa_col"),
            "reference_seq_index": col.get("reference_seq_index"),
            "reference_resid": col.get("reference_resid"),
            "reference_aa": col.get("reference_aa"),
            "coverage_fraction": len(present) / n_labels,
            "mappings": mappings,
        }
        consensus.append(entry)

    return consensus


def write_consensus_outputs(
    msa: Dict[str, Any],
    consensus: List[Dict[str, Any]],
    out_dir: Path,
    *,
    fasta_name: str = DEFAULT_ALIGNMENT_FASTA,
    csv_name: str = DEFAULT_RESIDUE_MAP_CSV,
    json_name: str = DEFAULT_ALIGNMENT_JSON,
    chains: Optional[Dict[str, ChainSequence]] = None,
) -> Dict[str, str]:
    """Write FASTA, CSV, and JSON artifacts."""
    out_dir.mkdir(parents=True, exist_ok=True)
    fasta_path = out_dir / fasta_name
    csv_path = out_dir / csv_name
    json_path = out_dir / json_name

    ref_label = msa["reference_label"]
    row_order = [ref_label] + [l for l in msa.get("labels", []) if l != ref_label]
    with open(fasta_path, "w", encoding="utf-8") as fh:
        for label in row_order:
            seq = msa["rows"].get(label, "")
            if chains and label in chains:
                cid = chains[label].chain_id
                fh.write(f">{label} chain={cid} length={len(seq)}\n")
            else:
                fh.write(f">{label} length={len(seq)}\n")
            for i in range(0, len(seq), 80):
                fh.write(seq[i : i + 80] + "\n")

    labels = msa.get("labels") or []
    header = [
        "consensus_index",
        "msa_col",
        "reference_label",
        "reference_seq_index",
        "reference_resid",
        "reference_aa",
        "coverage_fraction",
    ]
    for lab in labels:
        header.extend([f"{lab}_seq_index", f"{lab}_resid", f"{lab}_aa"])

    with open(csv_path, "w", newline="", encoding="utf-8") as fh:
        writer = csv.writer(fh)
        writer.writerow(header)
        for pos in consensus:
            row = [
                pos["consensus_index"],
                pos.get("msa_col"),
                ref_label,
                pos.get("reference_seq_index"),
                pos.get("reference_resid"),
                pos.get("reference_aa"),
                f"{pos.get('coverage_fraction', 0):.4f}",
            ]
            mappings = pos.get("mappings") or {}
            for lab in labels:
                m = mappings.get(lab)
                if m:
                    row.extend([m["seq_index"], m["resid"], m["aa"]])
                else:
                    row.extend(["", "", ""])
            writer.writerow(row)

    payload = {
        "reference_label": ref_label,
        "labels": labels,
        "msa_width": msa.get("msa_width"),
        "n_consensus_positions": len(consensus),
        "consensus_positions": _json_safe(consensus),
        "fasta_file": fasta_name,
        "residue_map_csv": csv_name,
    }
    with open(json_path, "w", encoding="utf-8") as fh:
        json.dump(payload, fh, indent=2)

    return {
        "fasta_file": str(fasta_path),
        "residue_map_csv": str(csv_path),
        "json_file": str(json_path),
    }


# ── Public tool ───────────────────────────────────────────────────────────────


@tool
def build_consensus_sequence_alignment(
    working_dir: str,
    reference_label: str,
    labels: Optional[List[str]] = None,
    pdb_files: Optional[List[str]] = None,
    fasta_file: str = "",
    sim_dirs: Optional[List[str]] = None,
    base_dir: str = "",
    chain_id: Optional[str] = None,
    min_coverage: float = 0.85,
    alignment_fasta: str = DEFAULT_ALIGNMENT_FASTA,
    residue_map_csv: str = DEFAULT_RESIDUE_MAP_CSV,
    alignment_json: str = DEFAULT_ALIGNMENT_JSON,
) -> Dict[str, Any]:
    """
    Build a star sequence alignment to a reference and export consensus residue maps.

    Provide sequences via **one** of:
      * ``pdb_files`` + ``labels``
      * ``fasta_file`` (headers become labels; reference must appear in FASTA)
      * ``sim_dirs`` + ``labels`` (PDBs resolved from ``base_dir`` / sim folders)

    The reference sequence is listed **first** in the output FASTA. Consensus
    columns are reference residues mapped in at least ``min_coverage`` fraction
    of sequences (default 0.85). Use ``consensus_residue_map.csv`` to verify
    residue mappings before reference-projected PCA.

    Args:
        working_dir: Output directory (e.g. ``{base}/analysis``).
        reference_label: Label of the reference sequence (e.g. ``q8nb16`` for MLKL).
        labels: Sequence/simulation labels (required unless only ``fasta_file``).
        pdb_files: Optional list of PDB paths (parallel to ``labels``).
        fasta_file: Optional FASTA path instead of PDBs.
        sim_dirs: Optional per-simulation directories for PDB resolution.
        base_dir: Base multi-simulation directory for ``{label}.pdb`` lookup.
        chain_id: Optional protein chain ID when reading PDBs.
        min_coverage: Minimum fraction of sequences that must map to a column.
        alignment_fasta: Output MSA FASTA filename.
        residue_map_csv: Output mapping table for manual inspection.
        alignment_json: Output JSON consumed by reference-projected PCA tools.

    Returns:
        Dict with ``success``, output paths, ``n_sequences``, ``n_consensus_positions``.
    """
    if not HAS_BIO:
        return {"success": False, "error": "Biopython is required for consensus alignment"}

    out_dir = Path(working_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    try:
        chains: Dict[str, ChainSequence] = {}

        if fasta_file:
            chains = load_sequences_from_fasta(fasta_file)
            if labels:
                missing = [l for l in labels if l not in chains]
                if missing:
                    return {
                        "success": False,
                        "error": f"Labels not found in FASTA: {missing}",
                    }
                chains = {l: chains[l] for l in labels}
        elif pdb_files and labels:
            chains = load_sequences_from_pdbs(pdb_files, labels, chain_id=chain_id)
        elif sim_dirs and labels:
            base = base_dir or str(out_dir.parent)
            pdbs, used_labels, missing = _resolve_pdbs_from_sims(sim_dirs, labels, base)
            if len(pdbs) < 2:
                return {
                    "success": False,
                    "error": "Need >=2 structures for alignment",
                    "missing": missing,
                }
            chains = load_sequences_from_pdbs(pdbs, used_labels, chain_id=chain_id)
            labels = used_labels
        else:
            return {
                "success": False,
                "error": (
                    "Provide fasta_file, or pdb_files+labels, or sim_dirs+labels"
                ),
            }

        if reference_label not in chains:
            return {
                "success": False,
                "error": (
                    f"Reference label {reference_label!r} not found; "
                    f"available: {sorted(chains.keys())}"
                ),
            }

        if len(chains) < 2:
            return {"success": False, "error": "Need at least two sequences to align"}

        msa = build_star_msa_to_reference(chains, reference_label)
        consensus = select_consensus_positions(msa, min_coverage=min_coverage)
        if len(consensus) < 3:
            return {
                "success": False,
                "error": (
                    f"Only {len(consensus)} consensus positions at "
                    f"min_coverage={min_coverage}; need >=3 for PCA"
                ),
            }

        paths = write_consensus_outputs(
            msa,
            consensus,
            out_dir,
            fasta_name=alignment_fasta,
            csv_name=residue_map_csv,
            json_name=alignment_json,
            chains=chains,
        )

        try:
            from src.analysis.summary_logger import append_analysis_summary

            append_analysis_summary(
                working_dir=str(out_dir),
                analysis_type="ConsensusSequenceAlignment",
                statistics={
                    "n_sequences": len(chains),
                    "n_consensus_positions": len(consensus),
                    "min_coverage": min_coverage,
                    "reference_label": reference_label,
                },
                files=paths,
                metadata={"labels": list(chains.keys())},
            )
        except Exception as exc:  # pragma: no cover
            logger.warning("append_analysis_summary failed: %s", exc)

        return {
            "success": True,
            "message": (
                f"Consensus alignment: {len(chains)} sequences, "
                f"{len(consensus)} consensus positions"
            ),
            "reference_label": reference_label,
            "n_sequences": len(chains),
            "n_consensus_positions": len(consensus),
            "labels": list(chains.keys()),
            **paths,
        }
    except Exception as exc:
        logger.exception("build_consensus_sequence_alignment failed")
        return {"success": False, "error": str(exc)}
