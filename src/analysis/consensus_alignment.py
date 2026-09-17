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
import os
import shutil
import subprocess
import tempfile
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
DEFAULT_MSA_METHOD = "mafft"
DEFAULT_CONSERVATION_METRIC = "similarity"
DEFAULT_MIN_CONSERVATION = 0.5
DEFAULT_MIN_COVERAGE = 0.5

_MAFFT_CANDIDATES = (
    "/apps/gb/multi-bacpipe/0.8.0/libexec/t-coffee-13.46.0.919e8c6b-4/plugins/linux/mafft",
    "/apps/gb/multi-bacpipe/0.8.0/lib/t_coffee-11.0.8/plugins/linux/mafft",
)


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
    min_coverage: float = DEFAULT_MIN_COVERAGE,
    require_reference: bool = True,
    conservation_metric: str = DEFAULT_CONSERVATION_METRIC,
    min_conservation: float = DEFAULT_MIN_CONSERVATION,
) -> List[Dict[str, Any]]:
    """
    Return consensus columns meeting coverage **and** conservation filters.

    ``conservation_metric``:
      * ``similarity`` — mean pairwise BLOSUM62 score normalized to ~[0, 1]
        (default; keep columns with score ≥ ``min_conservation``, default 0.5)
      * ``identity`` — fraction of non-gap residues matching the modal AA
      * ``coverage`` / ``none`` — coverage only (legacy)
    """
    labels: List[str] = msa.get("labels") or []
    n_labels = max(len(labels), 1)
    threshold = float(min_coverage) * n_labels
    metric = (conservation_metric or "similarity").strip().lower()
    consensus: List[Dict[str, Any]] = []
    blosum = None
    if metric == "similarity" and HAS_BIO:
        try:
            blosum = substitution_matrices.load("BLOSUM62")
        except Exception:
            blosum = None

    for col in msa.get("columns", []):
        if require_reference and col.get("reference_seq_index") is None:
            continue
        mappings = col.get("mappings") or {}
        present = [lab for lab in labels if lab in mappings]
        if len(present) < threshold:
            continue
        aas = [
            str((mappings[lab] or {}).get("aa") or "")[:1]
            for lab in present
            if (mappings.get(lab) or {}).get("aa")
        ]
        cons_score = _column_conservation(aas, metric=metric, blosum=blosum)
        if metric in ("similarity", "identity") and cons_score < float(min_conservation):
            continue
        entry = {
            "consensus_index": len(consensus),
            "msa_col": col.get("msa_col"),
            "reference_seq_index": col.get("reference_seq_index"),
            "reference_resid": col.get("reference_resid"),
            "reference_aa": col.get("reference_aa"),
            "coverage_fraction": len(present) / n_labels,
            "conservation": cons_score,
            "mappings": mappings,
        }
        consensus.append(entry)

    return consensus


def _column_conservation(
    aas: Sequence[str],
    *,
    metric: str,
    blosum: Any = None,
) -> float:
    letters = [a.upper() for a in aas if a and a != "-"]
    if not letters:
        return 0.0
    if metric in ("coverage", "none", ""):
        return 1.0
    if metric == "identity":
        from collections import Counter

        mode, count = Counter(letters).most_common(1)[0]
        return float(count) / float(len(letters))
    # similarity (default)
    if blosum is None or len(letters) == 1:
        from collections import Counter

        mode, count = Counter(letters).most_common(1)[0]
        return float(count) / float(len(letters))
    scores: List[float] = []
    norms: List[float] = []
    for i in range(len(letters)):
        for j in range(i + 1, len(letters)):
            a, b = letters[i], letters[j]
            try:
                s = float(blosum[a, b])
                na = float(blosum[a, a])
                nb = float(blosum[b, b])
            except Exception:
                continue
            denom = max(0.5 * (na + nb), 1e-6)
            scores.append(s / denom)
            norms.append(1.0)
    if not scores:
        return 0.0
    # Clamp to [0, 1]
    mean = float(np.mean(scores))
    return float(max(0.0, min(1.0, mean)))


def find_mafft_executable() -> Optional[str]:
    """Locate a usable ``mafft`` binary (sets MAFFT_BINARIES when needed)."""
    env_bin = os.environ.get("MAFFT") or os.environ.get("MAFFT_BIN")
    which = shutil.which("mafft")
    for cand in (env_bin, which, *_MAFFT_CANDIDATES):
        if not cand:
            continue
        p = Path(cand)
        if p.is_file() and os.access(p, os.X_OK):
            return str(p.resolve())
    return None


def build_mafft_msa_to_reference(
    chains: Dict[str, ChainSequence],
    reference_label: str,
    *,
    mafft_bin: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Run MAFFT on all sequences and index columns by the reference row.

    Falls back to Biopython star pairwise if MAFFT is unavailable.
    """
    if reference_label not in chains:
        raise KeyError(f"Reference label {reference_label!r} not in chain set")

    exe = mafft_bin or find_mafft_executable()
    if not exe:
        logger.warning("MAFFT not found — falling back to Biopython star pairwise MSA")
        msa = build_star_msa_to_reference(chains, reference_label)
        msa["msa_method"] = "star_pairwise"
        return msa

    other_labels = [k for k in sorted(chains.keys()) if k != reference_label]
    labels = [reference_label] + other_labels

    with tempfile.TemporaryDirectory(prefix="mafft_msa_") as tmp:
        tmp_path = Path(tmp)
        in_fa = tmp_path / "input.fasta"
        out_fa = tmp_path / "aligned.fasta"
        with open(in_fa, "w", encoding="utf-8") as fh:
            for lab in labels:
                fh.write(f">{lab}\n")
                seq = chains[lab].sequence
                for i in range(0, len(seq), 80):
                    fh.write(seq[i : i + 80] + "\n")

        env = os.environ.copy()
        # Older mafft wrappers require sibling binaries via MAFFT_BINARIES.
        env.setdefault("MAFFT_BINARIES", str(Path(exe).resolve().parent))
        cmd = [exe, "--auto", "--quiet", str(in_fa)]
        try:
            proc = subprocess.run(
                cmd,
                check=False,
                capture_output=True,
                text=True,
                env=env,
                timeout=600,
            )
        except Exception as exc:
            logger.warning("MAFFT failed (%s) — star pairwise fallback", exc)
            msa = build_star_msa_to_reference(chains, reference_label)
            msa["msa_method"] = "star_pairwise"
            return msa
        if proc.returncode != 0 or not (proc.stdout or "").strip():
            logger.warning(
                "MAFFT exit=%s stderr=%s — star pairwise fallback",
                proc.returncode,
                (proc.stderr or "")[:300],
            )
            msa = build_star_msa_to_reference(chains, reference_label)
            msa["msa_method"] = "star_pairwise"
            return msa
        out_fa.write_text(proc.stdout, encoding="utf-8")
        aligned = _read_fasta_rows(out_fa)

    if reference_label not in aligned:
        # Case-insensitive header match
        for k in list(aligned.keys()):
            if k.lower() == reference_label.lower():
                aligned[reference_label] = aligned.pop(k)
                break
    if reference_label not in aligned:
        logger.warning("MAFFT output missing reference — star pairwise fallback")
        msa = build_star_msa_to_reference(chains, reference_label)
        msa["msa_method"] = "star_pairwise"
        return msa

    ref_row = aligned[reference_label]
    width = len(ref_row)
    # Ensure equal width
    for lab in labels:
        row = aligned.get(lab, "-" * width)
        if len(row) < width:
            row = row + "-" * (width - len(row))
        elif len(row) > width:
            row = row[:width]
        aligned[lab] = row

    # Map MSA columns → ungapped sequence indices
    ungapped_idx: Dict[str, List[Optional[int]]] = {}
    for lab in labels:
        idxs: List[Optional[int]] = []
        si = 0
        for ch in aligned[lab]:
            if ch == "-":
                idxs.append(None)
            else:
                idxs.append(si)
                si += 1
        ungapped_idx[lab] = idxs

    columns: List[Dict[str, Any]] = []
    rows: Dict[str, str] = {}
    # Reference-indexed rows (collapse MSA onto reference non-gap columns)
    ref_keep = [i for i, ch in enumerate(ref_row) if ch != "-"]
    for lab in labels:
        rows[lab] = "".join(
            aligned[lab][i] if aligned[lab][i] != "-" else "-" for i in ref_keep
        )

    for new_col, msa_i in enumerate(ref_keep):
        ref_seq_i = ungapped_idx[reference_label][msa_i]
        assert ref_seq_i is not None
        ref_chain = chains[reference_label]
        col: Dict[str, Any] = {
            "msa_col": new_col,
            "mafft_col": msa_i,
            "reference_seq_index": int(ref_seq_i),
            "reference_resid": int(ref_chain.resids[ref_seq_i]),
            "reference_aa": ref_chain.sequence[ref_seq_i],
            "mappings": {
                reference_label: {
                    "seq_index": int(ref_seq_i),
                    "resid": int(ref_chain.resids[ref_seq_i]),
                    "aa": ref_chain.sequence[ref_seq_i],
                }
            },
        }
        for lab in other_labels:
            oth_i = ungapped_idx[lab][msa_i]
            if oth_i is None:
                continue
            oth = chains[lab]
            col["mappings"][lab] = {
                "seq_index": int(oth_i),
                "resid": int(oth.resids[oth_i]),
                "aa": oth.sequence[oth_i],
            }
        columns.append(col)

    return {
        "reference_label": reference_label,
        "msa_width": len(ref_keep),
        "mafft_width": width,
        "rows": rows,
        "columns": columns,
        "labels": labels,
        "msa_method": "mafft",
        "full_msa_rows": {lab: aligned[lab] for lab in labels},
    }


def _read_fasta_rows(path: Path) -> Dict[str, str]:
    rows: Dict[str, str] = {}
    label = None
    chunks: List[str] = []
    with open(path, encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            if line.startswith(">"):
                if label is not None:
                    rows[label] = "".join(chunks)
                label = line[1:].split()[0]
                chunks = []
            else:
                chunks.append(line.replace(" ", ""))
        if label is not None:
            rows[label] = "".join(chunks)
    return rows


def write_consensus_outputs(
    msa: Dict[str, Any],
    consensus: List[Dict[str, Any]],
    out_dir: Path,
    *,
    fasta_name: str = DEFAULT_ALIGNMENT_FASTA,
    csv_name: str = DEFAULT_RESIDUE_MAP_CSV,
    json_name: str = DEFAULT_ALIGNMENT_JSON,
    chains: Optional[Dict[str, ChainSequence]] = None,
    conservation_metric: str = DEFAULT_CONSERVATION_METRIC,
    min_conservation: float = DEFAULT_MIN_CONSERVATION,
    min_coverage: float = DEFAULT_MIN_COVERAGE,
) -> Dict[str, str]:
    """Write FASTA, CSV, and compact consensus JSON artifacts."""
    from src.analysis.cross_sim_artifacts import (
        compact_consensus_from_positions,
        write_json_compact,
    )

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
        "conservation",
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
                f"{float(pos.get('conservation') or 0):.4f}",
            ]
            mappings = pos.get("mappings") or {}
            for lab in labels:
                m = mappings.get(lab)
                if m:
                    row.extend([m["seq_index"], m["resid"], m["aa"]])
                else:
                    row.extend(["", "", ""])
            writer.writerow(row)

    payload = compact_consensus_from_positions(
        reference_label=ref_label,
        labels=labels,
        consensus_positions=consensus,
        msa_width=msa.get("msa_width"),
        msa_method=str(msa.get("msa_method") or DEFAULT_MSA_METHOD),
        conservation_metric=conservation_metric,
        min_conservation=min_conservation,
        min_coverage=min_coverage,
        extra={
            "fasta_file": fasta_name,
            "residue_map_csv": csv_name,
        },
    )
    # Keep expanded positions available in-memory consumers that read the file
    # via expand_consensus_positions; compact is the on-disk form.
    write_json_compact(json_path, payload)

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
    min_coverage: float = DEFAULT_MIN_COVERAGE,
    alignment_fasta: str = DEFAULT_ALIGNMENT_FASTA,
    residue_map_csv: str = DEFAULT_RESIDUE_MAP_CSV,
    alignment_json: str = DEFAULT_ALIGNMENT_JSON,
    consensus_json: str = "",
    msa_method: str = DEFAULT_MSA_METHOD,
    conservation_metric: str = DEFAULT_CONSERVATION_METRIC,
    min_conservation: float = DEFAULT_MIN_CONSERVATION,
) -> Dict[str, Any]:
    """
    Build a consensus MSA to a reference and export residue maps.

    Default alignment engine is **MAFFT** (falls back to Biopython star
    pairwise if MAFFT is unavailable). Consensus columns require both
    ``min_coverage`` presence and ``conservation_metric`` ≥ ``min_conservation``.

    ``conservation_metric``: ``similarity`` (default, BLOSUM62-based, threshold
    0.5) or ``identity`` (modal AA fraction). Pass either explicitly when the
    user requests it.

    Provide sequences via **one** of:
      * ``pdb_files`` + ``labels``
      * ``fasta_file`` (headers become labels; reference must appear in FASTA)
      * ``sim_dirs`` + ``labels`` (PDBs resolved from ``base_dir`` / sim folders)

    Args:
        working_dir: Output directory (e.g. ``{base}/analysis``).
        reference_label: Label of the reference sequence.
        labels: Sequence/simulation labels (required unless only ``fasta_file``).
        pdb_files: Optional list of PDB paths (parallel to ``labels``).
        fasta_file: Optional FASTA path instead of PDBs.
        sim_dirs: Optional per-simulation directories for PDB resolution.
        base_dir: Base multi-simulation directory for ``{label}.pdb`` lookup.
        chain_id: Optional protein chain ID when reading PDBs.
        min_coverage: Min fraction of sequences mapped in a column (default 0.5).
        alignment_fasta: Output MSA FASTA filename.
        residue_map_csv: Output mapping table for manual inspection.
        alignment_json: Output compact consensus JSON.
        consensus_json: Optional alias for ``alignment_json``.
        msa_method: ``mafft`` (default) or ``star_pairwise``.
        conservation_metric: ``similarity`` (default) or ``identity``.
        min_conservation: Threshold for conservation_metric (default 0.5).

    Returns:
        Dict with ``success``, output paths, ``n_sequences``, ``n_consensus_positions``.
    """
    if not HAS_BIO:
        return {"success": False, "error": "Biopython is required for consensus alignment"}

    # LLM plans often pass consensus_json instead of alignment_json.
    if consensus_json and (
        not alignment_json or alignment_json == DEFAULT_ALIGNMENT_JSON
    ):
        alignment_json = consensus_json

    # Sanitize chain_id from JSON null / "None" / blank.
    if chain_id is not None and str(chain_id).strip().lower() in ("", "none", "null"):
        chain_id = None

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
            # Drop hallucinated / missing PDB paths and fall back to sim_dirs.
            valid_pairs = [
                (p, lab)
                for p, lab in zip(pdb_files, labels)
                if p and Path(p).is_file()
            ]
            if len(valid_pairs) >= 2:
                pdb_files = [p for p, _ in valid_pairs]
                labels = [lab for _, lab in valid_pairs]
                chains = load_sequences_from_pdbs(pdb_files, labels, chain_id=chain_id)
            elif sim_dirs and labels:
                base = base_dir or str(out_dir.parent)
                pdbs, used_labels, missing = _resolve_pdbs_from_sims(
                    sim_dirs, labels, base
                )
                if len(pdbs) < 2:
                    return {
                        "success": False,
                        "error": "Need >=2 structures for alignment",
                        "missing": missing,
                        "invalid_pdb_files": [
                            p for p in (pdb_files or []) if not Path(p).is_file()
                        ],
                    }
                chains = load_sequences_from_pdbs(pdbs, used_labels, chain_id=chain_id)
                labels = used_labels
            else:
                return {
                    "success": False,
                    "error": (
                        "pdb_files were missing on disk and no sim_dirs were "
                        "provided for fallback resolution"
                    ),
                    "invalid_pdb_files": list(pdb_files or []),
                }
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
            resolved_ref = None
            ref_l = str(reference_label).lower()
            for key in chains:
                k = str(key).lower()
                if (
                    k == ref_l
                    or k.startswith(ref_l + "_")
                    or ref_l.startswith(k + "_")
                    or ref_l in k
                    or k in ref_l
                ):
                    resolved_ref = key
                    break
            if resolved_ref is None:
                return {
                    "success": False,
                    "error": (
                        f"Reference label {reference_label!r} not found; "
                        f"available: {sorted(chains.keys())}"
                    ),
                }
            reference_label = resolved_ref

        if len(chains) < 2:
            return {"success": False, "error": "Need at least two sequences to align"}

        method = (msa_method or DEFAULT_MSA_METHOD).strip().lower()
        if method in ("star", "star_pairwise", "pairwise", "biopython"):
            msa = build_star_msa_to_reference(chains, reference_label)
            msa["msa_method"] = "star_pairwise"
        else:
            msa = build_mafft_msa_to_reference(chains, reference_label)

        metric = (conservation_metric or DEFAULT_CONSERVATION_METRIC).strip().lower()
        if metric not in ("similarity", "identity", "coverage", "none"):
            metric = DEFAULT_CONSERVATION_METRIC

        consensus = select_consensus_positions(
            msa,
            min_coverage=min_coverage,
            conservation_metric=metric,
            min_conservation=min_conservation,
        )
        if len(consensus) < 3:
            return {
                "success": False,
                "error": (
                    f"Only {len(consensus)} consensus positions at "
                    f"min_coverage={min_coverage}, "
                    f"{metric}>={min_conservation}; need >=3"
                ),
                "msa_method": msa.get("msa_method"),
            }

        paths = write_consensus_outputs(
            msa,
            consensus,
            out_dir,
            fasta_name=alignment_fasta,
            csv_name=residue_map_csv,
            json_name=alignment_json,
            chains=chains,
            conservation_metric=metric,
            min_conservation=min_conservation,
            min_coverage=min_coverage,
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
                    "min_conservation": min_conservation,
                    "conservation_metric": metric,
                    "msa_method": msa.get("msa_method"),
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
                f"Consensus alignment ({msa.get('msa_method')}): {len(chains)} sequences, "
                f"{len(consensus)} consensus positions "
                f"({metric}>={min_conservation})"
            ),
            "reference_label": reference_label,
            "n_sequences": len(chains),
            "n_consensus_positions": len(consensus),
            "msa_method": msa.get("msa_method"),
            "conservation_metric": metric,
            "min_conservation": min_conservation,
            "labels": list(chains.keys()),
            **paths,
        }
    except Exception as exc:
        logger.exception("build_consensus_sequence_alignment failed")
        return {"success": False, "error": str(exc)}
