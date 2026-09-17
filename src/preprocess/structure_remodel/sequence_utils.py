"""
Sequence extraction and alignment utilities for structure remodeling.
Maps experimental and model PDB chains via one-letter sequence alignment.
"""
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

THREE_TO_ONE = {
    "ALA": "A", "CYS": "C", "ASP": "D", "GLU": "E", "PHE": "F",
    "GLY": "G", "HIS": "H", "ILE": "I", "LYS": "K", "LEU": "L",
    "MET": "M", "ASN": "N", "PRO": "P", "GLN": "Q", "ARG": "R",
    "SER": "S", "THR": "T", "VAL": "V", "TRP": "W", "TYR": "Y",
    # Phosphorylated / modified residues commonly seen in models
    "SEP": "S", "TPO": "T", "PTR": "Y", "HYP": "P",
}


def three_to_one(resname: str) -> str:
    return THREE_TO_ONE.get(resname.upper(), "X")


@dataclass
class ChainSequence:
    """One-letter sequence and PDB residue numbering for a protein chain."""

    chain_id: str
    sequence: str
    resids: List[int]
    resnames: List[str]

    def resid_at(self, seq_index: int) -> int:
        return self.resids[seq_index]

    def resname_at(self, seq_index: int) -> str:
        return self.resnames[seq_index]


def extract_chain_sequences(
    pdb_file: str,
    chain_id: Optional[str] = None,
) -> Dict[str, ChainSequence]:
    """
    Extract per-chain protein sequences from a PDB file.

    Uses CA atoms to define residue order; skips hetero residues (insertion codes
    with id[0] != ' ' are included when they have CA).

    Blank / missing PDB chain IDs (common after ``gmx editconf``) are treated as
    a single synthetic chain ``A`` — MDAnalysis cannot parse ``chainID`` with an
    empty token.
    """
    import MDAnalysis as mda

    # LLM / JSON often pass the literal strings "None" / "null".
    if chain_id is not None and str(chain_id).strip().lower() in ("", "none", "null"):
        chain_id = None

    u = mda.Universe(pdb_file)
    protein = u.select_atoms("protein")
    if len(protein) == 0:
        raise ValueError(f"No protein atoms found in {pdb_file}")

    raw_ids = sorted(set(protein.chainIDs))
    # MDAnalysis may report blank chain as '' ; never feed that to chainID …
    usable = [c for c in raw_ids if c is not None and str(c).strip() != ""]

    chains: Dict[str, ChainSequence] = {}

    def _chain_from_atoms(atoms, key: str) -> Optional[ChainSequence]:
        ca = atoms.select_atoms("name CA")
        if len(ca) == 0:
            return None
        ordered_residues = sorted(ca.residues, key=lambda r: r.resid)
        seq = "".join(three_to_one(r.resname) for r in ordered_residues)
        resids = [int(r.resid) for r in ordered_residues]
        resnames = [r.resname for r in ordered_residues]
        return ChainSequence(
            chain_id=key, sequence=seq, resids=resids, resnames=resnames,
        )

    if chain_id:
        if usable and chain_id not in usable and chain_id != "A":
            raise ValueError(
                f"Chain {chain_id} not found in {pdb_file}; available: {usable or ['(blank)']}"
            )
        if not usable:
            # Requested chain A (or any) on a blank-chain PDB → whole protein.
            cs = _chain_from_atoms(protein, chain_id)
            if cs is None:
                raise ValueError(f"No protein CA atoms found in {pdb_file}")
            return {chain_id: cs}
        chain_atoms = protein.select_atoms(f"chainID {chain_id}")
        cs = _chain_from_atoms(chain_atoms, chain_id)
        if cs is None:
            raise ValueError(f"No protein CA atoms for chain {chain_id} in {pdb_file}")
        return {chain_id: cs}

    if not usable:
        cs = _chain_from_atoms(protein, "A")
        if cs is None:
            raise ValueError(f"No protein CA atoms found in {pdb_file}")
        return {"A": cs}

    for cid in usable:
        chain_atoms = protein.select_atoms(f"chainID {cid}")
        cs = _chain_from_atoms(chain_atoms, str(cid))
        if cs is not None:
            chains[str(cid)] = cs

    if not chains:
        raise ValueError(f"No protein CA atoms found in {pdb_file}")

    return chains


def pick_default_chain(chains: Dict[str, ChainSequence]) -> str:
    """Return the chain with the longest sequence."""
    return max(chains.keys(), key=lambda c: len(chains[c].sequence))


def parse_residue_range(range_str: str) -> List[int]:
    """
  Parse residue range strings: '165-168', '165,166,167', or '165'.
    """
    resids: List[int] = []
    for part in range_str.replace(" ", "").split(","):
        if "-" in part:
            start, end = part.split("-", 1)
            resids.extend(range(int(start), int(end) + 1))
        else:
            resids.append(int(part))
    return sorted(set(resids))


@dataclass
class ResiduePair:
    """Aligned residue pair between target and donor chains."""

    target_seq_index: int
    donor_seq_index: int
    target_resid: int
    donor_resid: int
    target_resname: str
    donor_resname: str


@dataclass
class SequenceAlignmentResult:
    target_chain: ChainSequence
    donor_chain: ChainSequence
    aligned_pairs: List[ResiduePair]
    target_only_indices: List[int]
    donor_only_indices: List[int]
    score: float


def align_chain_sequences(
    target: ChainSequence,
    donor: ChainSequence,
) -> SequenceAlignmentResult:
    """
    Align two chain sequences and return residue-level mapping.

    Uses Biopython PairwiseAligner (global alignment).
    """
    from Bio.Align import PairwiseAligner

    aligner = PairwiseAligner()
    aligner.mode = "global"
    alignments = aligner.align(target.sequence, donor.sequence)
    if not alignments:
        raise ValueError("Sequence alignment produced no results")

    best = alignments[0]
    score = float(best.score)
    indices = best.indices
    if indices is None or len(indices) != 2:
        raise ValueError("Alignment indices missing from PairwiseAligner result")

    t_path, d_path = indices[0], indices[1]
    aligned_pairs: List[ResiduePair] = []
    target_only: List[int] = []
    donor_only: List[int] = []

    for ti, di in zip(t_path, d_path):
        if ti != -1 and di != -1:
            aligned_pairs.append(
                ResiduePair(
                    target_seq_index=ti,
                    donor_seq_index=di,
                    target_resid=target.resid_at(ti),
                    donor_resid=donor.resid_at(di),
                    target_resname=target.resname_at(ti),
                    donor_resname=donor.resname_at(di),
                )
            )
        elif ti != -1:
            target_only.append(ti)
        else:
            donor_only.append(di)

    return SequenceAlignmentResult(
        target_chain=target,
        donor_chain=donor,
        aligned_pairs=aligned_pairs,
        target_only_indices=target_only,
        donor_only_indices=donor_only,
        score=score,
    )


def flanking_residue_pairs(
    target: ChainSequence,
    donor: ChainSequence,
    insert_resids: List[int],
) -> List[ResiduePair]:
    """
    Build anchor pairs using residues flanking an insert region (same PDB numbering).
    """
    if not insert_resids:
        return []

    lo, hi = min(insert_resids), max(insert_resids)
    pairs: List[ResiduePair] = []
    donor_resid_set = set(donor.resids)
    target_resid_to_idx = {r: i for i, r in enumerate(target.resids)}
    donor_resid_to_idx = {r: i for i, r in enumerate(donor.resids)}

    before = [r for r in target.resids if r < lo]
    after = [r for r in target.resids if r > hi]

    if before:
        t_res = max(before)
        d_res = t_res
        if d_res in donor_resid_set:
            pairs.append(
                ResiduePair(
                    target_seq_index=target_resid_to_idx[t_res],
                    donor_seq_index=donor_resid_to_idx[d_res],
                    target_resid=t_res,
                    donor_resid=d_res,
                    target_resname=target.resname_at(target_resid_to_idx[t_res]),
                    donor_resname=donor.resname_at(donor_resid_to_idx[d_res]),
                )
            )

    if after:
        t_res = min(after)
        d_res = t_res
        if d_res in donor_resid_set:
            pairs.append(
                ResiduePair(
                    target_seq_index=target_resid_to_idx[t_res],
                    donor_seq_index=donor_resid_to_idx[d_res],
                    target_resid=t_res,
                    donor_resid=d_res,
                    target_resname=target.resname_at(target_resid_to_idx[t_res]),
                    donor_resname=donor.resname_at(donor_resid_to_idx[d_res]),
                )
            )

    return pairs


def donor_resids_for_missing_segments(
    alignment: SequenceAlignmentResult,
) -> List[int]:
    """Return donor PDB resids that align to gaps in the target sequence."""
    missing: List[int] = []
    for d_idx in alignment.donor_only_indices:
        missing.append(alignment.donor_chain.resid_at(d_idx))
    return sorted(missing)


def format_gaps(resids: List[int]) -> str:
    if not resids:
        return ""
    ranges: List[str] = []
    start = resids[0]
    prev = resids[0]
    for r in resids[1:]:
        if r == prev + 1:
            prev = r
        else:
            ranges.append(f"{start}-{prev}" if start != prev else str(start))
            start = prev = r
    ranges.append(f"{start}-{prev}" if start != prev else str(start))
    return ", ".join(ranges)
