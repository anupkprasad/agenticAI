"""
Hydrogen Addition Tool
Adds missing hydrogen atoms with separate handling for proteins and ligands
- Reduce for proteins (Amber-compatible)
- Open Babel for ligands (pH-aware protonation)
"""
import subprocess
import shutil
import os
from pathlib import Path
from typing import Dict, Any, Optional
from langchain.tools import tool


@tool
def add_hydrogens(
    pdb_file: str,
    output_file: Optional[str] = None,
    method: str = "auto",
    ph: float = 7.4,
    molecule_type: str = "auto"
) -> Dict[str, Any]:
    """
    Add missing hydrogen atoms to PDB file with appropriate tool based on molecule type.
    
    Args:
        pdb_file: Input PDB file path
        output_file: Output PDB file path (optional)
        method: Tool to use:
            - 'auto': Auto-detect (reduce for protein, obabel for ligand)
            - 'reduce': Reduce (protein, neutral pH)
            - 'pdb2pqr': PDB2PQR (protein, pH-dependent with PropKa)
            - 'obabel': Open Babel (ligand, pH-dependent)
            - 'none': No hydrogen addition
        ph: pH value for protonation (used with pdb2pqr and obabel)
        molecule_type: 'auto' (detect), 'protein', 'ligand', or 'complex'
        
    Returns:
        Dict with success status, output_file, method used, and molecule type
    """
    if not os.path.exists(pdb_file):
        return {"success": False, "error": f"PDB file not found: {pdb_file}"}
    
    if not output_file:
        base = Path(pdb_file).stem
        working_dir = Path(pdb_file).parent
        output_file = str(working_dir / f"{base}_h.pdb")
    
    try:
        # Auto-detect molecule type if needed
        if molecule_type == "auto":
            molecule_type = _detect_molecule_type(pdb_file)
        
        # Auto-select method based on molecule type
        if method == "auto":
            if molecule_type == "protein":
                method = "reduce"  # Default to reduce for proteins
            elif molecule_type == "ligand":
                method = "obabel"
            else:  # complex
                return {
                    "success": False,
                    "error": "Complex structures should be separated first using separate_protein_ligand tool",
                    "recommendation": "Use separate_protein_ligand, then add hydrogens to each component separately"
                }
        
        # Execute appropriate method
        if method == "reduce":
            return _add_hydrogens_reduce(pdb_file, output_file)
        elif method == "pdb2pqr":
            return _add_hydrogens_pdb2pqr(pdb_file, output_file, ph)
        elif method == "obabel":
            return _add_hydrogens_obabel(pdb_file, output_file, ph)
        elif method == "none":
            shutil.copy(pdb_file, output_file)
            return {
                "success": True,
                "output_file": output_file,
                "method": "none",
                "message": "No hydrogen addition (file copied)"
            }
        else:
            return {
                "success": False,
                "error": f"Unknown method: {method}. Use 'auto', 'reduce', 'pdb2pqr', 'obabel', or 'none'"
            }
            
    except Exception as e:
        return {
            "success": False,
            "error": f"Hydrogen addition failed: {str(e)}"
        }


def _detect_molecule_type(pdb_file: str) -> str:
    """Detect if file contains protein, ligand, or complex."""
    try:
        import MDAnalysis as mda
        u = mda.Universe(pdb_file)
        
        protein = u.select_atoms("protein")
        ligand = u.select_atoms("not protein and not resname HOH WAT TIP3 SOL and not ion")
        
        has_protein = len(protein) > 0
        has_ligand = len(ligand) > 0
        
        if has_protein and has_ligand:
            return "complex"
        elif has_protein:
            return "protein"
        elif has_ligand:
            return "ligand"
        else:
            return "unknown"
    except:
        # Fallback: simple text-based detection
        with open(pdb_file, 'r') as f:
            content = f.read()
            if any(aa in content for aa in ['GLY', 'ALA', 'VAL', 'LEU', 'ILE']):
                return "protein"
            else:
                return "ligand"


def _add_hydrogens_reduce(pdb_file: str, output_file: str) -> Dict[str, Any]:
    """Add hydrogens using reduce (good for proteins)."""
    if not shutil.which("reduce"):
        return {
            "success": False,
            "error": "reduce not found. Install from: http://kinemage.biochem.duke.edu/software/reduce.php"
        }
    
    try:
        cmd = ["reduce", "-build", str(pdb_file)]
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
        
        if result.returncode == 0:
            with open(output_file, 'w') as f:
                f.write(result.stdout)
            return {
                "success": True,
                "output_file": output_file,
                "method": "reduce",
                "molecule_type": "protein",
                "message": "Hydrogens added using reduce (protein optimized)"
            }
        else:
            return {
                "success": False,
                "error": f"reduce failed: {result.stderr}",
                "warning": "Try obabel method instead"
            }
    except subprocess.TimeoutExpired:
        return {"success": False, "error": "reduce timed out (>60s)"}
    except Exception as e:
        return {"success": False, "error": f"reduce execution failed: {str(e)}"}


def _add_hydrogens_obabel(pdb_file: str, output_file: str, ph: float = 7.4) -> Dict[str, Any]:
    """Add hydrogens using Open Babel (good for ligands with pH-aware protonation)."""
    if not shutil.which("obabel"):
        return {
            "success": False,
            "error": "obabel not found. Install with: conda install -c conda-forge openbabel"
        }
    
    try:
        # Open Babel with pH-aware protonation
        # Convert to mol2 format for better handling of small molecules
        temp_mol2 = str(Path(output_file).with_suffix('.mol2'))
        
        cmd = ["obabel", pdb_file, "-O", temp_mol2, "-p", str(ph)]
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
        
        if result.returncode == 0:
            # Convert back to PDB
            cmd2 = ["obabel", temp_mol2, "-O", output_file]
            result2 = subprocess.run(cmd2, capture_output=True, text=True, timeout=60)
            
            # Clean up temp file
            if os.path.exists(temp_mol2):
                os.remove(temp_mol2)
            
            if result2.returncode == 0:
                return {
                    "success": True,
                    "output_file": output_file,
                    "method": "obabel",
                    "molecule_type": "ligand",
                    "ph": ph,
                    "message": f"Hydrogens added using Open Babel at pH {ph} (ligand optimized)"
                }
            else:
                return {
                    "success": False,
                    "error": f"obabel PDB conversion failed: {result2.stderr}"
                }
        else:
            return {
                "success": False,
                "error": f"obabel failed: {result.stderr}",
                "warning": "Try reduce method for proteins"
            }
    except subprocess.TimeoutExpired:
        return {"success": False, "error": "obabel timed out (>60s)"}
    except Exception as e:
        return {"success": False, "error": f"obabel execution failed: {str(e)}"}


def _add_hydrogens_pdb2pqr(pdb_file: str, output_file: str, ph: float = 7.0) -> Dict[str, Any]:
    """Add hydrogens using PDB2PQR with pH-dependent protonation (good for proteins at specific pH)."""
    try:
        # Try pdb2pqr30 (newer version) first, then fall back to pdb2pqr
        pdb2pqr_cmd = None
        for cmd in ['pdb2pqr30', 'pdb2pqr']:
            if shutil.which(cmd):
                pdb2pqr_cmd = cmd
                break
        
        if not pdb2pqr_cmd:
            return {
                "success": False,
                "error": "pdb2pqr not found. Install with: pip install pdb2pqr",
                "recommendation": "Use 'reduce' method as fallback for proteins"
            }
        
        # Create temporary PQR file (pdb2pqr outputs PQR format)
        pqr_file = output_file.replace('.pdb', '.pqr')
        
        # Run pdb2pqr with PropKa for pKa calculations
        cmd = [
            pdb2pqr_cmd,
            '--ff=AMBER',  # Use AMBER force field
            f'--with-ph={ph}',  # Set pH
            '--titration-state-method=propka',  # Use PropKa for pKa calculation
            '--drop-water',  # Remove water molecules
            pdb_file,
            pqr_file
        ]
        
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
        
        if result.returncode == 0 and os.path.exists(pqr_file):
            # Convert PQR back to PDB format
            _convert_pqr_to_pdb(pqr_file, output_file)
            
            # Parse protonation info from output
            protonation_changes = _parse_pdb2pqr_output(result.stdout)
            
            return {
                "success": True,
                "output_file": output_file,
                "pqr_file": pqr_file,
                "method": "pdb2pqr",
                "molecule_type": "protein",
                "ph": ph,
                "protonation_changes": protonation_changes,
                "message": f"Hydrogens added using pdb2pqr at pH {ph} with PropKa pKa predictions (protein optimized)"
            }
        else:
            return {
                "success": False,
                "error": f"pdb2pqr failed: {result.stderr}",
                "recommendation": "Try 'reduce' method as fallback"
            }
            
    except subprocess.TimeoutExpired:
        return {"success": False, "error": "pdb2pqr timed out after 120 seconds"}
    except Exception as e:
        return {"success": False, "error": f"pdb2pqr execution failed: {str(e)}"}


def _convert_pqr_to_pdb(pqr_file: str, pdb_file: str):
    """Convert PQR format to PDB format (simplified)."""
    with open(pqr_file, 'r') as f_in:
        with open(pdb_file, 'w') as f_out:
            for line in f_in:
                if line.startswith(('ATOM', 'HETATM')):
                    # PQR format has extra columns (charge, radius)
                    # Convert back to PDB format by truncating
                    pdb_line = line[:66].ljust(80) + '\n'
                    f_out.write(pdb_line)
                else:
                    f_out.write(line)


def _parse_pdb2pqr_output(stdout: str) -> list:
    """Parse pdb2pqr output for protonation changes."""
    changes = []
    for line in stdout.split('\n'):
        if 'protonation' in line.lower() or 'titration' in line.lower():
            changes.append(line.strip())
    return changes
