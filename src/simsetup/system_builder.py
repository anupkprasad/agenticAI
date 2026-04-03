"""
Complete System Builder
High-level orchestrator that builds complete GROMACS simulation systems
Handles protein + ligand + ion complexes with full topology setup
"""
import subprocess
import shutil
from pathlib import Path
from typing import Dict, Any, List, Optional
from langchain.tools import tool

from src.simsetup.pdb_to_gro_converter import PDBtoGROConverter
from src.simsetup.gro_merger import GROMerger
from src.simsetup.topology_editor import TopologyEditor


class ComplexSystemBuilder:
    """Build complete GROMACS simulation system from component PDB files."""
    
    # Supported metal ions with their charges and parameters
    METAL_IONS = {
        "MG": {"charge": 2, "name": "Magnesium"},
        "CA": {"charge": 2, "name": "Calcium"},
        "ZN": {"charge": 2, "name": "Zinc"},
        "MN": {"charge": 2, "name": "Manganese"},
        "FE": {"charge": 3, "name": "Iron(III)"},  # Can also be +2
        "FE2": {"charge": 2, "name": "Iron(II)"}
    }
    
    def __init__(self, working_dir: str = "working_dir/simsetup"):
        self.working_dir = Path(working_dir).resolve()  # Resolve to absolute path
        self.working_dir.mkdir(parents=True, exist_ok=True)
        
    def run_gmx_command(self, cmd: List[str], stdin_input: Optional[str] = None) -> Dict[str, Any]:
        """Execute GROMACS command safely."""
        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                input=stdin_input,
                check=True,
                cwd=str(self.working_dir)
            )
            return {
                "success": True,
                "stdout": result.stdout,
                "stderr": result.stderr
            }
        except subprocess.CalledProcessError as e:
            return {
                "success": False,
                "error": f"Command failed: {' '.join(cmd)}",
                "stdout": e.stdout,
                "stderr": e.stderr
            }
    
    def build_complex_system(
        self,
        protein_pdb: str,
        ligand_pdb: Optional[str] = None,
        ion_pdb: Optional[str] = None,
        ligand_resname: Optional[str] = None,
        ligand_itp: Optional[str] = None,
        ion_resname: Optional[str] = None,
        force_field: str = "amber99sb-ildn",
        water_model: str = "tip3p",
        box_type: str = "cubic",
        box_distance: float = 1.2,
        ion_concentration: float = 0.15,
        generate_tpr: bool = True,
        mdp_dir: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Build complete GROMACS system from component PDB files.
        
        Workflow:
        1. Convert PDB files to GRO format
        2. Run gmx pdb2gmx on protein
        3. Merge all GRO files
        4. Edit topology to include ligand/ions
        5. Build simulation box
        6. Solvate system
        7. Add neutralizing ions + salt
        8. Generate TPR file for minimization
        
        Args:
            protein_pdb: Protein PDB file (with hydrogens)
            ligand_pdb: Ligand PDB file (optional)
            ion_pdb: Ion PDB file (optional)
            ligand_resname: Ligand residue name (e.g., "ATP")
            ligand_itp: Ligand topology file (e.g., "ATP.itp")
            ion_resname: Ion residue name (e.g., "MG", "CA", "ZN")
            force_field: GROMACS force field (default: amber99sb-ildn)
            water_model: Water model (default: tip3p)
            box_type: Simulation box type (cubic, dodecahedron, octahedron)
            box_distance: Distance from solute to box edge (nm)
            ion_concentration: Salt concentration in M (default: 0.15)
            generate_tpr: Generate TPR file for minimization (default: True)
            mdp_dir: Directory containing MDP files (optional)
            
        Returns:
            Dict with all generated files and workflow status
        """
        results = {
            "success": True,
            "steps": [],
            "files": {}
        }
        
        # Resolve all input PDB paths relative to working_dir if not absolute
        def _resolve(path: Optional[str]) -> Optional[str]:
            if path is None:
                return None
            p = Path(path)
            if not p.is_absolute():
                resolved = self.working_dir / p
                if resolved.exists():
                    return str(resolved)
            return str(p)
        
        protein_pdb = _resolve(protein_pdb)
        ligand_pdb = _resolve(ligand_pdb)
        ion_pdb = _resolve(ion_pdb)
        if ligand_itp:
            ligand_itp = _resolve(ligand_itp)
        
        # Step 1: Convert protein PDB to GRO
        converter = PDBtoGROConverter(str(self.working_dir))
        protein_gro = str(self.working_dir / "protein.gro")
        
        result = converter.convert_pdb_to_gro(protein_pdb, protein_gro, "protein")
        if not result["success"]:
            return {"success": False, "error": f"Failed to convert protein: {result['error']}"}
        results["steps"].append("Converted protein PDB to GRO")
        results["files"]["protein_gro"] = protein_gro
        
        # Step 2: Convert ligand PDB to GRO (if provided)
        ligand_gro = None
        if ligand_pdb and ligand_resname:
            ligand_gro = str(self.working_dir / f"{ligand_resname}.gro")
            result = converter.convert_pdb_to_gro(
                ligand_pdb, ligand_gro, f"resname {ligand_resname}"
            )
            if not result["success"]:
                return {"success": False, "error": f"Failed to convert ligand: {result['error']}"}
            results["steps"].append(f"Converted ligand ({ligand_resname}) to GRO")
            results["files"]["ligand_gro"] = ligand_gro
        
        # Step 3: Convert ion PDB to GRO (if provided)
        ion_gro = None
        ion_count = 0
        if ion_pdb and ion_resname:
            ion_gro = str(self.working_dir / f"{ion_resname}.gro")
            result = converter.convert_pdb_to_gro(
                ion_pdb, ion_gro, f"resname {ion_resname}"
            )
            if not result["success"]:
                return {"success": False, "error": f"Failed to convert ion: {result['error']}"}
            
            # Count ions
            import MDAnalysis as mda
            u = mda.Universe(ion_gro)
            ion_count = len(u.select_atoms(f"resname {ion_resname}").residues)
            
            results["steps"].append(f"Converted ions ({ion_resname}) to GRO: {ion_count} ions")
            results["files"]["ion_gro"] = ion_gro
            results["ion_count"] = ion_count
        
        # Step 4: Run gmx pdb2gmx on protein
        protein_processed = str(self.working_dir / "protein_processed.gro")
        topology_file = str(self.working_dir / "topol.top")
        posre_file = str(self.working_dir / "posre.itp")
        
        cmd = [
            "gmx", "pdb2gmx",
            "-f", protein_gro,
            "-o", protein_processed,
            "-p", topology_file,
            "-i", posre_file,
            "-ff", force_field,
            "-water", water_model,
            "-ignh"  # Ignore input hydrogens (we already have them)
        ]
        
        result = self.run_gmx_command(cmd)
        if not result["success"]:
            return {"success": False, "error": f"gmx pdb2gmx failed: {result['stderr']}"}
        results["steps"].append("Generated protein topology with gmx pdb2gmx")
        results["files"]["protein_processed_gro"] = protein_processed
        results["files"]["topology"] = topology_file
        results["files"]["posre"] = posre_file
        
        # Step 5: Merge GRO files
        gro_files_to_merge = [protein_processed]
        if ligand_gro:
            gro_files_to_merge.append(ligand_gro)
        if ion_gro:
            gro_files_to_merge.append(ion_gro)
        
        complex_gro = str(self.working_dir / "complex.gro")
        merger = GROMerger()
        result = merger.merge_gro_files(gro_files_to_merge, complex_gro)
        if not result["success"]:
            return {"success": False, "error": f"Failed to merge GRO files: {result['error']}"}
        results["steps"].append(f"Merged {len(gro_files_to_merge)} GRO files into complex")
        results["files"]["complex_gro"] = complex_gro
        results["total_atoms"] = result["total_atoms"]
        
        # Step 6: Edit topology to include ligand and ions
        if ligand_itp or ion_resname:
            editor = TopologyEditor()
            result = editor.edit_topology(
                topology_file=topology_file,
                ligand_itp=ligand_itp,
                ligand_resname=ligand_resname,
                ligand_count=1 if ligand_resname else 0,
                ion_resname=ion_resname,
                ion_count=ion_count if ion_count > 0 else None
            )
            if not result["success"]:
                return {"success": False, "error": f"Failed to edit topology: {result['error']}"}
            results["steps"].append(f"Edited topology: {', '.join(result['modifications'])}")
        
        # Step 7: Build simulation box
        boxed_gro = str(self.working_dir / "boxed.gro")
        cmd = [
            "gmx", "editconf",
            "-f", complex_gro,
            "-o", boxed_gro,
            "-d", str(box_distance),
            "-bt", box_type
        ]
        result = self.run_gmx_command(cmd)
        if not result["success"]:
            return {"success": False, "error": f"gmx editconf failed: {result['stderr']}"}
        results["steps"].append(f"Created {box_type} simulation box (d={box_distance} nm)")
        results["files"]["boxed_gro"] = boxed_gro
        
        # Step 8: Solvate system
        solvated_gro = str(self.working_dir / "solvated.gro")
        cmd = [
            "gmx", "solvate",
            "-cp", boxed_gro,
            "-p", topology_file,
            "-o", solvated_gro
        ]
        result = self.run_gmx_command(cmd)
        if not result["success"]:
            return {"success": False, "error": f"gmx solvate failed: {result['stderr']}"}
        results["steps"].append("Solvated system with water")
        results["files"]["solvated_gro"] = solvated_gro
        
        # Step 9: Add ions (if mdp_dir provided or we can generate minimal mdp)
        if generate_tpr:
            # Create minimal ions.mdp
            ions_mdp = str(self.working_dir / "ions.mdp")
            with open(ions_mdp, "w") as f:
                f.write("; Minimal MDP for genion\n")
                f.write("integrator  = steep\n")
                f.write("nsteps      = 0\n")
            
            # Generate ions TPR
            ions_tpr = str(self.working_dir / "ions.tpr")
            cmd = [
                "gmx", "grompp",
                "-f", ions_mdp,
                "-c", solvated_gro,
                "-p", topology_file,
                "-o", ions_tpr,
                "-maxwarn", "3"
            ]
            result = self.run_gmx_command(cmd)
            if not result["success"]:
                return {"success": False, "error": f"gmx grompp (ions) failed: {result['stderr']}"}
            
            # Add ions
            ionized_gro = str(self.working_dir / "system.gro")
            cmd = [
                "gmx", "genion",
                "-s", ions_tpr,
                "-o", ionized_gro,
                "-p", topology_file,
                "-conc", str(ion_concentration),
                "-neutral",
                "-pname", "NA",
                "-nname", "CL"
            ]
            result = self.run_gmx_command(cmd, stdin_input="SOL\n")  # Select SOL group
            if not result["success"]:
                return {"success": False, "error": f"gmx genion failed: {result['stderr']}"}
            results["steps"].append(f"Added neutralizing ions + {ion_concentration}M salt")
            results["files"]["system_gro"] = ionized_gro
            results["files"]["ions_tpr"] = ions_tpr
        
        results["message"] = f"Successfully built system with {len(results['steps'])} steps"
        return results


@tool
def build_simulation_system(
    protein_pdb: str,
    output_dir: str,
    ligand_pdb: Optional[str] = None,
    ion_pdb: Optional[str] = None,
    ligand_resname: Optional[str] = None,
    ligand_itp: Optional[str] = None,
    ion_resname: Optional[str] = None,
    force_field: str = "amber99sb-ildn",
    water_model: str = "tip3p",
    box_distance: float = 1.2,
    ion_concentration: float = 0.15
) -> Dict[str, Any]:
    """
    Build complete GROMACS simulation system from component PDB files.
    Orchestrates entire workflow: topology generation → merging → solvation → ionization.
    
    Args:
        protein_pdb: Path to protein PDB file (with hydrogens from preprocessor)
        output_dir: Directory for all output files
        ligand_pdb: Path to ligand PDB file (optional)
        ion_pdb: Path to ion PDB file (optional, e.g., MG ions)
        ligand_resname: Ligand residue name (e.g., "ATP", "GTP", "ADP")
        ligand_itp: Ligand topology file path (e.g., "ATP.itp")
                   If not provided, will need to be generated separately
        ion_resname: Ion residue name (e.g., "MG", "CA", "ZN", "MN", "FE")
        force_field: GROMACS force field (default: amber99sb-ildn)
        water_model: Water model (default: tip3p)
        box_distance: Distance from solute to box edge in nm (default: 1.2)
        ion_concentration: Salt concentration in M (default: 0.15 = physiological)
    
    Returns:
        Dict with all generated files and workflow status
        
    Example:
        >>> build_simulation_system(
        ...     protein_pdb="working_dir/preprocess/protein_h.pdb",
        ...     output_dir="working_dir/simsetup",
        ...     ligand_pdb="working_dir/preprocess/ATP_h.pdb",
        ...     ion_pdb="working_dir/preprocess/MG.pdb",
        ...     ligand_resname="ATP",
        ...     ligand_itp="ATP.itp",
        ...     ion_resname="MG"
        ... )
        
    Generated files:
        - protein_processed.gro: Protein with GROMACS atom types
        - complex.gro: Merged protein + ligand + ions
        - boxed.gro: Complex in simulation box
        - solvated.gro: Solvated complex
        - system.gro: Final system with neutralizing ions + salt
        - topol.top: Complete topology file
        - posre.itp: Position restraints for protein
        - ions.tpr: TPR file for adding ions
    """
    builder = ComplexSystemBuilder(working_dir=output_dir)
    return builder.build_complex_system(
        protein_pdb=protein_pdb,
        ligand_pdb=ligand_pdb,
        ion_pdb=ion_pdb,
        ligand_resname=ligand_resname,
        ligand_itp=ligand_itp,
        ion_resname=ion_resname,
        force_field=force_field,
        water_model=water_model,
        box_distance=box_distance,
        ion_concentration=ion_concentration
    )
