"""
Ligand Topology Generation with Acpype/Antechamber
Generates GAFF/GAFF2 parameters for small molecules
"""
import subprocess
from pathlib import Path
from typing import Dict, Any, Optional
from langchain.tools import tool
import shutil


class LigandTopologyGenerator:
    """Generate ligand topology using acpype/antechamber."""
    
    def __init__(self):
        self.acpype_available = shutil.which("acpype") is not None
        self.antechamber_available = shutil.which("antechamber") is not None
        
    def check_dependencies(self) -> Dict[str, bool]:
        """Check which parameterization tools are available."""
        return {
            "acpype": self.acpype_available,
            "antechamber": self.antechamber_available
        }
    
    def generate_with_acpype(
        self,
        ligand_pdb: str,
        output_dir: str,
        charge_method: str = "bcc",
        net_charge: Optional[int] = None,
        atom_type: str = "gaff2"
    ) -> Dict[str, Any]:
        """
        Generate ligand topology using acpype.
        
        Args:
            ligand_pdb: Path to ligand PDB file
            output_dir: Output directory (if empty, uses ligand PDB's directory)
            charge_method: Charge calculation method (bcc, gas, etc.)
            net_charge: Net charge of molecule (auto-detect if None)
            atom_type: GAFF version (gaff, gaff2)
            
        Returns:
            Dict with generated files and status
        """
        # Handle empty output_dir
        if not output_dir or output_dir.strip() == "":
            output_dir = Path(ligand_pdb).parent
        else:
            output_dir = Path(output_dir)
        
        output_dir.mkdir(parents=True, exist_ok=True)
        
        # Resolve ligand_pdb to absolute path (acpype runs from output_dir)
        ligand_pdb_abs = str(Path(ligand_pdb).resolve())
        
        cmd = [
            "acpype",
            "-i", ligand_pdb_abs,
            "-a", atom_type,
            "-c", charge_method
        ]
        
        if net_charge is not None:
            cmd.extend(["-n", str(net_charge)])
        
        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=600,
                cwd=str(output_dir)
            )
            
            # Acpype creates subdirectory with ligand name
            ligand_name = Path(ligand_pdb).stem
            acpype_dir = output_dir / f"{ligand_name}.acpype"
            
            # Check for output files regardless of exit code —
            # acpype can return non-zero even on success (e.g. warnings)
            if acpype_dir.exists():
                topology_file = acpype_dir / f"{ligand_name}_GMX.itp"
                coordinate_file = acpype_dir / f"{ligand_name}_GMX.gro"
                
                if topology_file.exists():
                    # Copy output files to output_dir so callers get clean paths
                    # without the confusing .acpype suffix in the directory name
                    dest_itp = output_dir / topology_file.name
                    dest_gro = output_dir / coordinate_file.name if coordinate_file.exists() else None
                    shutil.copy2(str(topology_file), str(dest_itp))
                    if dest_gro:
                        shutil.copy2(str(coordinate_file), str(dest_gro))
                    return {
                        "success": True,
                        "topology": str(dest_itp),
                        "coordinates": str(dest_gro) if dest_gro else None,
                        "output_dir": str(output_dir),
                        "acpype_dir": str(acpype_dir),
                        "method": "acpype",
                        "atom_type": atom_type,
                        "charge_method": charge_method,
                        "stdout": result.stdout[-500:] if result.stdout else "",
                        "stderr": result.stderr[-500:] if result.stderr else ""
                    }
            
            # If we get here, acpype didn't produce expected output
            combined_output = (result.stdout or "") + "\n" + (result.stderr or "")
            return {
                "success": False,
                "error": f"Acpype finished (exit {result.returncode}) but did not produce expected files. Output: {combined_output[-800:]}"
            }
            
        except subprocess.TimeoutExpired:
            return {
                "success": False,
                "error": "Acpype execution timed out (>600s)"
            }
        except Exception as e:
            return {
                "success": False,
                "error": f"Unexpected error: {str(e)}"
            }
    
    def generate_with_antechamber(
        self,
        ligand_pdb: str,
        output_dir: str,
        charge_method: str = "bcc",
        net_charge: Optional[int] = None,
        atom_type: str = "gaff2"
    ) -> Dict[str, Any]:
        """
        Generate ligand topology using antechamber directly.
        
        Args:
            ligand_pdb: Path to ligand PDB file
            output_dir: Output directory (if empty, uses ligand PDB's directory)
            charge_method: Charge calculation method (bcc, gas, etc.)
            net_charge: Net charge of molecule (auto-detect if None)
            atom_type: GAFF version (gaff, gaff2)
            
        Returns:
            Dict with generated files and status
        """
        # Handle empty output_dir
        if not output_dir or output_dir.strip() == "":
            output_dir = Path(ligand_pdb).parent
        else:
            output_dir = Path(output_dir)
        
        output_dir.mkdir(parents=True, exist_ok=True)
        
        ligand_name = Path(ligand_pdb).stem
        mol2_file = output_dir / f"{ligand_name}.mol2"
        frcmod_file = output_dir / f"{ligand_name}.frcmod"
        
        # Step 1: Run antechamber
        cmd_ante = [
            "antechamber",
            "-i", str(ligand_pdb),
            "-fi", "pdb",
            "-o", str(mol2_file),
            "-fo", "mol2",
            "-c", charge_method,
            "-at", atom_type,
            "-pf", "y"
        ]
        
        if net_charge is not None:
            cmd_ante.extend(["-nc", str(net_charge)])
        
        try:
            result_ante = subprocess.run(
                cmd_ante,
                capture_output=True,
                text=True,
                timeout=600,
                check=True
            )
            
            # Step 2: Run parmchk2 to generate missing parameters
            cmd_parmchk = [
                "parmchk2",
                "-i", str(mol2_file),
                "-f", "mol2",
                "-o", str(frcmod_file),
                "-s", atom_type
            ]
            
            result_parmchk = subprocess.run(
                cmd_parmchk,
                capture_output=True,
                text=True,
                timeout=300,
                check=True
            )
            
            return {
                "success": True,
                "mol2_file": str(mol2_file),
                "frcmod_file": str(frcmod_file),
                "output_dir": str(output_dir),
                "method": "antechamber",
                "atom_type": atom_type,
                "charge_method": charge_method,
                "stdout": result_ante.stdout + "\n" + result_parmchk.stdout,
                "stderr": result_ante.stderr + "\n" + result_parmchk.stderr,
                "note": "Convert to GROMACS format with gmx x2top or acpype"
            }
            
        except subprocess.TimeoutExpired:
            return {
                "success": False,
                "error": "Antechamber execution timed out"
            }
        except subprocess.CalledProcessError as e:
            return {
                "success": False,
                "error": f"Antechamber failed: {e.stderr}"
            }
        except Exception as e:
            return {
                "success": False,
                "error": f"Unexpected error: {str(e)}"
            }
    
    def generate_ligand_topology(
        self,
        ligand_pdb: str,
        output_dir: str,
        charge_method: str = "bcc",
        net_charge: Optional[int] = None,
        atom_type: str = "gaff2",
        preferred_tool: str = "acpype"
    ) -> Dict[str, Any]:
        """
        Generate ligand topology with automatic tool selection.
        
        Args:
            ligand_pdb: Path to ligand PDB file
            output_dir: Output directory
            charge_method: Charge calculation method (bcc, gas, etc.)
            net_charge: Net charge of molecule (auto-detect if None)
            atom_type: GAFF version (gaff, gaff2)
            preferred_tool: Preferred tool (acpype or antechamber)
            
        Returns:
            Dict with generated files and status
        """
        deps = self.check_dependencies()
        
        if not deps["acpype"] and not deps["antechamber"]:
            return {
                "success": False,
                "error": "Neither acpype nor antechamber available",
                "dependencies": deps
            }
        
        # Try preferred tool first
        if preferred_tool == "acpype" and deps["acpype"]:
            return self.generate_with_acpype(
                ligand_pdb, output_dir, charge_method, net_charge, atom_type
            )
        elif preferred_tool == "antechamber" and deps["antechamber"]:
            return self.generate_with_antechamber(
                ligand_pdb, output_dir, charge_method, net_charge, atom_type
            )
        
        # Fallback to available tool
        if deps["acpype"]:
            return self.generate_with_acpype(
                ligand_pdb, output_dir, charge_method, net_charge, atom_type
            )
        else:
            return self.generate_with_antechamber(
                ligand_pdb, output_dir, charge_method, net_charge, atom_type
            )


# LangChain tool wrapper
@tool
def generate_ligand_parameters(
    ligand_pdb: str,
    output_dir: Optional[str] = None,
    charge_method: str = "bcc",
    net_charge: Optional[int] = None,
    atom_type: str = "gaff2",
    preferred_tool: str = "acpype"
) -> Dict[str, Any]:
    """
    Generate missing ligand topology parameters using acpype or antechamber.
    Uses GAFF/GAFF2 force field for small molecules.
    
    Args:
        ligand_pdb: Path to ligand PDB file (e.g., ATP_cleaned.pdb)
        output_dir: Directory for output files (if None or empty, uses ligand PDB's directory)
        charge_method: Charge calculation method (bcc=AM1-BCC, gas=Gasteiger)
        net_charge: Net molecular charge (auto-detect if None)
        atom_type: GAFF version (gaff or gaff2, recommended: gaff2)
        preferred_tool: Preferred tool (acpype or antechamber)
        
    Returns:
        Dict with paths to generated topology files and success status
        
    Example:
        >>> result = generate_ligand_parameters(
        ...     ligand_pdb="working_dir/preprocess/ATP.pdb",
        ...     output_dir="working_dir/simsetup/ligand_params"
        ... )
        >>> print(result["topology"])  # ATP_GMX.itp
    """
    generator = LigandTopologyGenerator()
    
    # Handle empty or None output_dir
    if not output_dir or (isinstance(output_dir, str) and output_dir.strip() == ""):
        output_dir = str(Path(ligand_pdb).parent)
    
    result = generator.generate_ligand_topology(
        ligand_pdb=ligand_pdb,
        output_dir=output_dir,
        charge_method=charge_method,
        net_charge=net_charge,
        atom_type=atom_type,
        preferred_tool=preferred_tool
    )
    
    return result
