"""
Deterministic filenames for preprocessing pipeline stages.

Intermediate files describe what happened; final clean protein is always
protein.pdb → protein_h.pdb for downstream setup.
"""
import logging
import re
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

# Staged / intermediate (describe the operation)
RAW = "raw.pdb"                          # copied user experimental structure
REFERENCE_AF3 = "reference_af3.pdb"      # copied AlphaFold / model reference
MERGED_MISSING = "merged_missing_from_model.pdb"  # after remodel_structure
PROTEIN_PHOSPHO_MAPPED = "protein_phospho_mapped.pdb"  # SEP/TPO/PTR → SP2/THP1/TP2
DONOR_ALIGNED = "reference_af3_aligned.pdb"
DOMAIN_EXTRACTED = "domain_extracted.pdb"

# Final canonical outputs (setup agent expects these)
PROTEIN = "protein.pdb"
LIGAND = "ligand.pdb"
IONS = "ions.pdb"
PROTEIN_H = "protein_h.pdb"

# Legacy aliases (backward compatibility)
INPUT_EXPERIMENTAL = RAW
INPUT_DONOR = REFERENCE_AF3
REMODELED = MERGED_MISSING

DONOR_NAME_HINTS = re.compile(r"af3|alphafold|model", re.IGNORECASE)
PATH_PARAM_KEYS = frozenset({
    "pdb_file",
    "target_pdb",
    "donor_pdb",
    "output_file",
    "output_dir",
    "protein_output",
    "ligand_output",
    "ion_output",
})


@dataclass
class StagedFiles:
    preprocess_dir: Path
    raw: Path
    reference_af3: Path
    merged_missing: Path
    protein_phospho_mapped: Path
    protein: Path
    ligand: Path
    ions: Path
    protein_h: Path


class PreprocessStageManager:
    """Stage inputs and apply deterministic paths per tool."""

    def __init__(self, preprocess_dir: str):
        self.preprocess_dir = Path(preprocess_dir).resolve()
        self.preprocess_dir.mkdir(parents=True, exist_ok=True)
        self.files = StagedFiles(
            preprocess_dir=self.preprocess_dir,
            raw=self.preprocess_dir / RAW,
            reference_af3=self.preprocess_dir / REFERENCE_AF3,
            merged_missing=self.preprocess_dir / MERGED_MISSING,
            protein_phospho_mapped=self.preprocess_dir / PROTEIN_PHOSPHO_MAPPED,
            protein=self.preprocess_dir / PROTEIN,
            ligand=self.preprocess_dir / LIGAND,
            ions=self.preprocess_dir / IONS,
            protein_h=self.preprocess_dir / PROTEIN_H,
        )
        self._raw_staged = False
        self._reference_staged = False

    def initialize(
        self,
        experimental_source: Optional[str],
        goal_text: str = "",
        search_dirs: Optional[List[str]] = None,
    ) -> str:
        """Copy user PDB and optional AF3 reference into preprocess/."""
        search_dirs = search_dirs or []
        roots = [self.preprocess_dir.parent, *search_dirs, Path.cwd()]

        if experimental_source and Path(experimental_source).is_file():
            shutil.copy2(experimental_source, self.files.raw)
            self._raw_staged = True
            logger.info("Staged raw structure → %s", self.files.raw)

        donor_src = self._find_donor_source(goal_text, roots)
        if donor_src:
            shutil.copy2(donor_src, self.files.reference_af3)
            self._reference_staged = True
            logger.info("Staged AF3 reference %s → %s", donor_src, self.files.reference_af3)

        return str(self.files.raw if self._raw_staged else experimental_source or "")

    def _find_donor_source(self, goal_text: str, roots: List[Path]) -> Optional[Path]:
        candidates: List[str] = []
        for match in re.findall(r"[\w./\\-]+\.pdb", goal_text, re.IGNORECASE):
            if DONOR_NAME_HINTS.search(match):
                candidates.append(match)

        for root in roots:
            root = Path(root)
            for name in ("AF3model.pdb", "af3model.pdb", "alphafold.pdb", "model.pdb"):
                path = root / name
                if path.is_file():
                    candidates.append(str(path))
            staged = root / "preprocess" / REFERENCE_AF3
            if staged.is_file():
                candidates.append(str(staged))

        seen: set[str] = set()
        for cand in candidates:
            path = Path(cand)
            for candidate in [path, *[Path(r) / path.name for r in roots]]:
                key = str(candidate.resolve()) if candidate.is_file() else str(candidate)
                if key in seen:
                    continue
                seen.add(key)
                if candidate.is_file():
                    return candidate.resolve()
        return None

    def working_protein_path(self, current_pdb: Optional[str]) -> str:
        """Current best protein structure for the next tool step."""
        if current_pdb and Path(current_pdb).is_file():
            return str(Path(current_pdb).resolve())
        for candidate in (
            self.files.protein,
            self.files.protein_phospho_mapped,
            self.files.merged_missing,
            self.files.raw,
        ):
            if candidate.is_file():
                return str(candidate.resolve())
        return str(self.files.protein)

    def reference_af3_path(self) -> Optional[str]:
        if self.files.reference_af3.is_file():
            return str(self.files.reference_af3.resolve())
        return None

    def apply_tool_params(
        self,
        tool_name: str,
        llm_params: Dict[str, Any],
        current_pdb: Optional[str],
    ) -> Dict[str, Any]:
        """Keep LLM non-path settings; assign all file paths here."""
        params = {k: v for k, v in (llm_params or {}).items() if k not in PATH_PARAM_KEYS}
        f = self.files
        working = self.working_protein_path(current_pdb)

        if tool_name == "analyze_pdb":
            params["pdb_file"] = working

        elif tool_name == "separate_complex_components":
            params["pdb_file"] = working
            params["output_dir"] = str(self.preprocess_dir)
            params["protein_output"] = str(f.protein)
            params["ligand_output"] = str(f.ligand)
            params["ion_output"] = str(f.ions)

        elif tool_name == "detect_missing_structure_elements":
            params["target_pdb"] = working
            ref = self.reference_af3_path()
            if ref:
                params["donor_pdb"] = ref

        elif tool_name == "remodel_structure":
            params["target_pdb"] = working
            ref = self.reference_af3_path()
            if ref:
                params["donor_pdb"] = ref
            params["output_file"] = str(f.merged_missing)
            if llm_params.get("mode"):
                params["mode"] = llm_params["mode"]

        elif tool_name == "align_model_to_experimental":
            params["target_pdb"] = working
            ref = self.reference_af3_path()
            if ref:
                params["donor_pdb"] = ref
            params["output_file"] = str(self.preprocess_dir / DONOR_ALIGNED)

        elif tool_name == "normalize_phosphorylation_for_gromacs":
            params["pdb_file"] = (
                str(f.protein.resolve()) if f.protein.is_file() else working
            )
            params["output_file"] = str(f.protein_phospho_mapped)
            params["copy_to_protein"] = True

        elif tool_name == "validate_structure":
            params["pdb_file"] = working

        elif tool_name == "add_hydrogens":
            params["pdb_file"] = working
            params["output_file"] = str(f.protein_h)

        elif tool_name == "extract_domain":
            params["pdb_file"] = working
            params["output_file"] = str(self.preprocess_dir / DOMAIN_EXTRACTED)

        elif tool_name == "download_structure":
            if not params.get("output_file"):
                uid = (params.get("uniprot_id") or "structure").lower()
                params["output_file"] = str(self.preprocess_dir / f"{uid}.pdb")

        elif tool_name == "acquire_protein_structure":
            params["output_dir"] = str(self.preprocess_dir)

        else:
            params["pdb_file"] = working

        return params

    def register_aliases(self) -> Dict[str, str]:
        aliases: Dict[str, str] = {}
        if self.files.protein.is_file():
            protein = str(self.files.protein.resolve())
            for name in (
                PROTEIN,
                "protein_only.pdb",
                "protein_clean.pdb",
                "experimental.pdb",
                "target.pdb",
            ):
                aliases[name] = protein
        if self.files.raw.is_file():
            aliases[RAW] = str(self.files.raw.resolve())
            aliases[INPUT_EXPERIMENTAL] = aliases[RAW]
        if self.files.reference_af3.is_file():
            ref = str(self.files.reference_af3.resolve())
            aliases[REFERENCE_AF3] = ref
            aliases[INPUT_DONOR] = ref
            aliases["AF3model.pdb"] = ref
        if self.files.merged_missing.is_file():
            aliases[MERGED_MISSING] = str(self.files.merged_missing.resolve())
            aliases[REMODELED] = aliases[MERGED_MISSING]
        if self.files.protein_phospho_mapped.is_file():
            aliases[PROTEIN_PHOSPHO_MAPPED] = str(self.files.protein_phospho_mapped.resolve())
        if self.files.protein_h.is_file():
            aliases[PROTEIN_H] = str(self.files.protein_h.resolve())
        return aliases

    def summary(self) -> str:
        parts = []
        if self._raw_staged:
            parts.append(RAW)
        if self._reference_staged:
            parts.append(REFERENCE_AF3)
        return ", ".join(parts) if parts else "no new staging"
