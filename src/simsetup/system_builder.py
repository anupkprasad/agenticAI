"""
Complete System Builder
High-level orchestrator that builds complete GROMACS simulation systems.
Delegates to modular tools: topology_builder, pdb_to_gro_converter, gro_merger,
topology_editor, box_builder, solvator, ion_adder, mdp_generator, tpr_generator.

Handles three system scenarios:
  1. Protein only
  2. Protein + Ligand
  3. Protein + Ligand + Ions (crystal/cofactor ions)

Input can be .pdb or .gro; PDB files are converted via pdb_to_gro_converter.
"""
import logging
from pathlib import Path
from typing import Dict, Any, List, Optional
from langchain.tools import tool

from src.simsetup.pdb_to_gro_converter import PDBtoGROConverter
from src.simsetup.gro_merger import GROMerger
from src.simsetup.topology_editor import TopologyEditor
from src.simsetup.topology_builder import build_topology as _build_topology
from src.simsetup.box_builder import build_simulation_box as _build_box
from src.simsetup.solvator import solvate_system as _solvate
from src.simsetup.ion_adder import add_ions as _add_ions
from src.simsetup.mdp_generator import MDPGenerator
from src.simsetup.tpr_generator import generate_tpr_file as _generate_tpr

logger = logging.getLogger(__name__)


class ComplexSystemBuilder:
    """Build complete GROMACS simulation system from component files.

    Supports three system types:
      - protein_only: protein PDB/GRO → topology → box → solvate → ions → MDP → TPR
      - protein_ligand: adds ligand GRO merging + topology editing
      - protein_ligand_ion: adds crystal/cofactor ion merging + topology editing
    """

    def __init__(self, working_dir: str = "working_dir/simsetup"):
        self.working_dir = Path(working_dir).resolve()
        self.working_dir.mkdir(parents=True, exist_ok=True)

    # ------------------------------------------------------------------
    # Path helpers
    # ------------------------------------------------------------------
    def _resolve(self, path: Optional[str]) -> Optional[str]:
        """Resolve a path relative to working_dir if it is not absolute."""
        if path is None:
            return None
        p = Path(path)
        if not p.is_absolute():
            resolved = self.working_dir / p
            if resolved.exists():
                return str(resolved)
        return str(p)

    def _out(self, name: str) -> str:
        """Return an absolute output path inside working_dir."""
        return str(self.working_dir / name)

    @staticmethod
    def _is_pdb(path: str) -> bool:
        return Path(path).suffix.lower() == ".pdb"

    @staticmethod
    def _is_gro(path: str) -> bool:
        return Path(path).suffix.lower() == ".gro"

    # ------------------------------------------------------------------
    # Individual workflow steps (each delegates to a modular tool)
    # ------------------------------------------------------------------
    def _ensure_gro(self, input_file: str, output_gro: str, selection: str = "all") -> Dict[str, Any]:
        """Convert PDB → GRO if needed; if already .gro, just copy/return."""
        if self._is_gro(input_file):
            # Already GRO – copy to canonical location if different
            import shutil
            src = Path(input_file).resolve()
            dst = Path(output_gro).resolve()
            if src != dst:
                shutil.copy2(str(src), str(dst))
            return {"success": True, "output_file": str(dst), "note": "already GRO, copied"}
        # PDB → GRO via MDAnalysis-based converter
        converter = PDBtoGROConverter(str(self.working_dir))
        return converter.convert_pdb_to_gro(input_file, output_gro, selection)

    def _count_residues(self, gro_file: str, resname: str) -> int:
        """Count residues with a given name in a GRO file."""
        try:
            import MDAnalysis as mda
            u = mda.Universe(gro_file)
            return len(u.select_atoms(f"resname {resname}").residues)
        except Exception:
            return 0

    def _step_build_topology(
        self, protein_file: str, force_field: str, water_model: str
    ) -> Dict[str, Any]:
        """Step: generate protein topology via gmx pdb2gmx (delegates to topology_builder)."""
        return _build_topology(
            pdb_file=protein_file,
            force_field=force_field,
            water_model=water_model,
            output_file=self._out("protein_processed.gro"),
            topology_file=self._out("topol.top"),
            working_dir=str(self.working_dir),
        )

    def _step_merge_components(
        self, protein_gro: str, ligand_gro: Optional[str], ion_gro: Optional[str]
    ) -> Dict[str, Any]:
        """Step: merge protein + optional ligand + optional ions into complex.gro."""
        gro_files = [protein_gro]
        if ligand_gro:
            gro_files.append(ligand_gro)
        if ion_gro:
            gro_files.append(ion_gro)

        if len(gro_files) == 1:
            # Nothing to merge – just use protein GRO as complex
            import shutil
            complex_gro = self._out("complex.gro")
            shutil.copy2(protein_gro, complex_gro)
            return {"success": True, "output_file": complex_gro,
                    "total_atoms": 0, "n_components": 1}

        merger = GROMerger()
        return merger.merge_gro_files(gro_files, self._out("complex.gro"))

    def _step_edit_topology(
        self,
        topology_file: str,
        ligand_itp: Optional[str],
        ligand_resname: Optional[str],
        ion_resname: Optional[str],
        ion_count: int,
    ) -> Dict[str, Any]:
        """Step: edit topology to include ligand .itp and [ molecules ] entries."""
        editor = TopologyEditor()
        return editor.edit_topology(
            topology_file=topology_file,
            ligand_itp=ligand_itp,
            ligand_resname=ligand_resname,
            ligand_count=1 if ligand_resname else 0,
            ion_resname=ion_resname,
            ion_count=ion_count if ion_count > 0 else None,
        )

    def _step_build_box(
        self, coordinate_file: str, box_type: str, box_distance: float
    ) -> Dict[str, Any]:
        """Step: create simulation box via gmx editconf."""
        return _build_box(
            coordinate_file=coordinate_file,
            box_type=box_type,
            box_distance=box_distance,
            output_file=self._out("boxed.gro"),
            center_molecule=True,
            working_dir=str(self.working_dir),
        )

    def _step_solvate(self, coordinate_file: str, topology_file: str) -> Dict[str, Any]:
        """Step: solvate system via gmx solvate."""
        return _solvate(
            coordinate_file=coordinate_file,
            topology_file=topology_file,
            output_file=self._out("solvated.gro"),
            working_dir=str(self.working_dir),
        )

    def _step_add_ions(
        self, coordinate_file: str, topology_file: str,
        ions_mdp: str, concentration: float
    ) -> Dict[str, Any]:
        """Step: add neutralising counter-ions + salt via gmx genion."""
        return _add_ions(
            coordinate_file=coordinate_file,
            topology_file=topology_file,
            mdp_file=ions_mdp,
            positive_ion="NA",
            negative_ion="CL",
            neutral=True,
            concentration=concentration,
            output_file=self._out("system.gro"),
            working_dir=str(self.working_dir),
        )

    def _step_generate_mdp(
        self, force_field: str, has_ligand: bool, has_ions: bool,
        production_ns: float, temperature: float, pressure: float
    ) -> Dict[str, str]:
        """Step: generate all MDP files (ions, minim, nvt, npt, md)."""
        gen = MDPGenerator(force_field=force_field)
        return gen.generate_all_mdp_files(
            output_dir=str(self.working_dir),
            temperature=temperature,
            pressure=pressure,
            has_ligand=has_ligand,
            has_ions=has_ions,
            production_ns=production_ns,
        )

    def _step_generate_tpr(
        self, mdp_file: str, coordinate_file: str, topology_file: str, label: str
    ) -> Dict[str, Any]:
        """Step: generate TPR via gmx grompp."""
        return _generate_tpr(
            mdp_file=mdp_file,
            coordinate_file=coordinate_file,
            topology_file=topology_file,
            output_tpr=self._out(f"{label}.tpr"),
            working_dir=str(self.working_dir),
        )

    # ------------------------------------------------------------------
    # Main orchestrator
    # ------------------------------------------------------------------
    def build_complex_system(
        self,
        protein_file: str,
        ligand_file: Optional[str] = None,
        ion_file: Optional[str] = None,
        ligand_resname: Optional[str] = None,
        ligand_itp: Optional[str] = None,
        ion_resname: Optional[str] = None,
        force_field: str = "amber99sb-ildn",
        water_model: str = "tip3p",
        box_type: str = "cubic",
        box_distance: float = 1.2,
        ion_concentration: float = 0.15,
        production_ns: float = 200.0,
        temperature: float = 310.0,
        pressure: float = 1.0,
    ) -> Dict[str, Any]:
        """
        Build a complete GROMACS simulation system.

        Handles three scenarios:
          1. **Protein only** – protein_file only, no ligand/ion args.
          2. **Protein + Ligand** – protein_file + ligand_file/resname/itp.
          3. **Protein + Ligand + Ions** – all of the above + ion_file/resname.

        Input files may be .pdb or .gro.  PDB files are auto-converted to GRO.

        Returns:
            Dict with keys: success, steps (list[str]), files (dict), system_type, message
        """
        results: Dict[str, Any] = {"success": True, "steps": [], "files": {}}

        # --- Resolve paths ---------------------------------------------------
        protein_file = self._resolve(protein_file)
        ligand_file = self._resolve(ligand_file)
        ion_file = self._resolve(ion_file)
        ligand_itp = self._resolve(ligand_itp)

        # Sanitize water_model: reject "none"/empty → default to tip3p
        if not water_model or str(water_model).lower().strip() in ("none", "", "vacuum"):
            water_model = "tip3p"

        has_ligand = bool(ligand_file and ligand_resname)
        has_crystal_ions = bool(ion_file and ion_resname)
        system_type = "protein_only"
        if has_ligand and has_crystal_ions:
            system_type = "protein_ligand_ion"
        elif has_ligand:
            system_type = "protein_ligand"
        elif has_crystal_ions:
            system_type = "protein_ion"
        results["system_type"] = system_type
        logger.info(f"Building {system_type} system in {self.working_dir}")

        # =====================================================================
        # Step 1: Ensure all inputs are in GRO format
        # =====================================================================
        protein_gro = self._out("protein.gro")
        r = self._ensure_gro(protein_file, protein_gro, "protein")
        if not r.get("success"):
            return {"success": False, "error": f"Protein GRO conversion failed: {r.get('error')}"}
        results["steps"].append("Converted protein input to GRO")
        results["files"]["protein_gro"] = protein_gro

        ligand_gro = None
        if has_ligand:
            ligand_gro = self._out(f"{ligand_resname}.gro")
            r = self._ensure_gro(ligand_file, ligand_gro, f"resname {ligand_resname}")
            if not r.get("success"):
                return {"success": False, "error": f"Ligand GRO conversion failed: {r.get('error')}"}
            results["steps"].append(f"Converted ligand ({ligand_resname}) to GRO")
            results["files"]["ligand_gro"] = ligand_gro

        ion_gro = None
        ion_count = 0
        if has_crystal_ions:
            ion_gro = self._out(f"{ion_resname}.gro")
            r = self._ensure_gro(ion_file, ion_gro, f"resname {ion_resname}")
            if not r.get("success"):
                return {"success": False, "error": f"Ion GRO conversion failed: {r.get('error')}"}
            ion_count = self._count_residues(ion_gro, ion_resname)
            results["steps"].append(f"Converted ions ({ion_resname}) to GRO: {ion_count} ions")
            results["files"]["ion_gro"] = ion_gro
            results["ion_count"] = ion_count

        # =====================================================================
        # Step 2: Build protein topology (gmx pdb2gmx via topology_builder)
        # =====================================================================
        r = self._step_build_topology(protein_gro, force_field, water_model)
        if not r.get("success"):
            return {"success": False, "error": f"Topology build failed: {r.get('error', r.get('stderr', 'unknown'))}"}
        protein_processed = r["output_file"]
        topology_file = r["topology_file"]
        results["steps"].append(f"Generated protein topology ({force_field}/{water_model})")
        results["files"]["protein_processed_gro"] = protein_processed
        results["files"]["topology"] = topology_file

        # =====================================================================
        # Step 3: Merge all components into complex.gro (gro_merger)
        # =====================================================================
        r = self._step_merge_components(protein_processed, ligand_gro, ion_gro)
        if not r.get("success"):
            return {"success": False, "error": f"GRO merge failed: {r.get('error')}"}
        complex_gro = r["output_file"]
        results["steps"].append(f"Merged {r.get('n_components', 1)} component(s) into complex.gro")
        results["files"]["complex_gro"] = complex_gro

        # =====================================================================
        # Step 4: Edit topology for ligand/ions (topology_editor)
        # =====================================================================
        if has_ligand or has_crystal_ions:
            r = self._step_edit_topology(
                topology_file, ligand_itp, ligand_resname if has_ligand else None,
                ion_resname if has_crystal_ions else None, ion_count,
            )
            if not r.get("success"):
                return {"success": False, "error": f"Topology edit failed: {r.get('error')}"}
            results["steps"].append(f"Edited topology: {', '.join(r.get('modifications', []))}")

        # =====================================================================
        # Step 5: Build simulation box (box_builder)
        # =====================================================================
        r = self._step_build_box(complex_gro, box_type, box_distance)
        if not r.get("success"):
            return {"success": False, "error": f"Box build failed: {r.get('error', r.get('stderr', 'unknown'))}"}
        boxed_gro = r["output_file"]
        results["steps"].append(f"Created {box_type} box (d={box_distance} nm)")
        results["files"]["boxed_gro"] = boxed_gro

        # =====================================================================
        # Step 6: Solvate system (solvator)
        # =====================================================================
        r = self._step_solvate(boxed_gro, topology_file)
        if not r.get("success"):
            return {"success": False, "error": f"Solvation failed: {r.get('error', r.get('stderr', 'unknown'))}"}
        solvated_gro = r["output_file"]
        results["steps"].append(f"Solvated system ({r.get('water_molecules_added', '?')} waters)")
        results["files"]["solvated_gro"] = solvated_gro

        # =====================================================================
        # Step 7: Generate MDP files (mdp_generator)
        # =====================================================================
        mdp_files = self._step_generate_mdp(
            force_field, has_ligand, has_crystal_ions,
            production_ns, temperature, pressure,
        )
        ions_mdp = mdp_files["ions"]
        results["steps"].append("Generated MDP files (ions, minim, nvt, npt, md)")
        results["files"]["mdp_files"] = mdp_files

        # =====================================================================
        # Step 8: Add neutralising ions + salt (ion_adder)
        # =====================================================================
        r = self._step_add_ions(solvated_gro, topology_file, ions_mdp, ion_concentration)
        if not r.get("success"):
            return {"success": False, "error": f"Ion addition failed: {r.get('error', r.get('stderr', 'unknown'))}"}
        system_gro = r["output_file"]
        na_count = r.get("positive_ion_count", "?")
        cl_count = r.get("negative_ion_count", "?")
        results["steps"].append(f"Added counter-ions (NA:{na_count}, CL:{cl_count}, conc={ion_concentration}M)")
        results["files"]["system_gro"] = system_gro

        # =====================================================================
        # Step 9: Generate minimisation TPR (tpr_generator)
        # =====================================================================
        minim_mdp = mdp_files.get("minim")
        if minim_mdp:
            r = self._step_generate_tpr(minim_mdp, system_gro, topology_file, "minim")
            if not r.get("success"):
                logger.warning(f"Minim TPR generation failed: {r.get('error')}")
            else:
                results["steps"].append("Generated minimisation TPR")
                results["files"]["minim_tpr"] = r["output_tpr"]

        results["message"] = (
            f"Successfully built {system_type} system in {len(results['steps'])} steps"
        )
        return results


@tool
def build_simulation_system(
    protein_file: str,
    output_dir: str,
    ligand_file: Optional[str] = None,
    ion_file: Optional[str] = None,
    ligand_resname: Optional[str] = None,
    ligand_itp: Optional[str] = None,
    ion_resname: Optional[str] = None,
    force_field: str = "amber99sb-ildn",
    water_model: str = "tip3p",
    box_type: str = "cubic",
    box_distance: float = 1.2,
    ion_concentration: float = 0.15,
    production_ns: float = 200.0,
    temperature: float = 310.0,
    pressure: float = 1.0,
) -> Dict[str, Any]:
    """
    Build complete GROMACS simulation system from component PDB or GRO files.
    Orchestrates the full pipeline by delegating to modular tools:
      topology_builder → gro_merger → topology_editor → box_builder →
      solvator → mdp_generator → ion_adder → tpr_generator

    Handles three scenarios:
      1. Protein only        – provide protein_file only
      2. Protein + Ligand    – add ligand_file, ligand_resname, ligand_itp
      3. Protein + Ligand + Ions – add ion_file, ion_resname

    Input files can be .pdb or .gro (PDB is auto-converted to GRO).

    Args:
        protein_file: Path to protein PDB or GRO file
        output_dir: Directory for all output files
        ligand_file: Path to ligand PDB or GRO file (optional)
        ion_file: Path to ion PDB or GRO file (optional, e.g. MG ions)
        ligand_resname: Ligand residue name (e.g. "ATP", "GTP")
        ligand_itp: Ligand topology .itp file path
        ion_resname: Ion residue name (e.g. "MG", "CA", "ZN")
        force_field: GROMACS force field (default: amber99sb-ildn)
        water_model: Water model (default: tip3p)
        box_type: Box geometry: cubic, dodecahedron, octahedron
        box_distance: Solute-to-box-edge distance in nm (default: 1.2)
        ion_concentration: Salt concentration in M (default: 0.15)
        production_ns: Production run length in ns (default: 200)
        temperature: System temperature in K (default: 310)
        pressure: System pressure in bar (default: 1.0)

    Returns:
        Dict with keys: success, steps, files, system_type, message
    """
    builder = ComplexSystemBuilder(working_dir=output_dir)
    return builder.build_complex_system(
        protein_file=protein_file,
        ligand_file=ligand_file,
        ion_file=ion_file,
        ligand_resname=ligand_resname,
        ligand_itp=ligand_itp,
        ion_resname=ion_resname,
        force_field=force_field,
        water_model=water_model,
        box_type=box_type,
        box_distance=box_distance,
        ion_concentration=ion_concentration,
        production_ns=production_ns,
        temperature=temperature,
        pressure=pressure,
    )
