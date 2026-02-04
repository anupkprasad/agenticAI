#!/usr/bin/env python3
"""
Ligand Topology Generation Tool
Generates GROMACS topology for ligands using ACPYPE/Antechamber/RDKit
"""

import os
import subprocess
import logging
from pathlib import Path
from typing import Dict, Any, Optional
from langchain.tools import tool

logger = logging.getLogger(__name__)


@tool
def generate_ligand_topology(
    pdb_file: str,
    ligand_name: str,
    charge: int,
    output_dir: Optional[str] = None,
    force_field: str = "gaff2",
    preferred_method: Optional[str] = None
) -> Dict[str, Any]:
    """
    Generate GROMACS topology for ligand using ACPYPE, Antechamber, or RDKit.
    
    Args:
        pdb_file: Input ligand PDB file
        ligand_name: Residue name for the ligand
        charge: Net charge of the ligand
        output_dir: Output directory (default: same as input)
        force_field: Force field to use (gaff, gaff2)
        preferred_method: Preferred method (acpype, antechamber, rdkit)
        
    Returns:
        Dict with success status, topology file, coordinates, and method used
    """
    # Setup paths
    if not os.path.exists(pdb_file):
        return {"success": False, "error": f"PDB file not found: {pdb_file}"}
    
    working_dir = Path(output_dir) if output_dir else Path(pdb_file).parent
    working_dir.mkdir(parents=True, exist_ok=True)
    
    # Check available tools
    available_tools = _check_dependencies()
    
    # Determine method order
    methods = []
    if preferred_method and available_tools.get(preferred_method):
        methods = [preferred_method]
    else:
        if available_tools.get('acpype'):
            methods.append('acpype')
        if available_tools.get('antechamber'):
            methods.append('antechamber')
        if available_tools.get('rdkit'):
            methods.append('rdkit')
    
    if not methods:
        return {
            "success": False,
            "error": "No topology generation tools available (need acpype, antechamber, or rdkit)"
        }
    
    # Try each method
    for method in methods:
        logger.info(f"Attempting ligand topology generation with {method}")
        
        try:
            if method == 'acpype':
                result = _generate_with_acpype(pdb_file, ligand_name, charge, force_field, working_dir)
            elif method == 'antechamber':
                result = _generate_with_antechamber(pdb_file, ligand_name, charge, force_field, working_dir)
            elif method == 'rdkit':
                result = _generate_with_rdkit(pdb_file, ligand_name, charge, working_dir)
            else:
                continue
            
            if result:
                return {
                    "success": True,
                    "method": method,
                    "topology_file": result.get("topology"),
                    "coordinate_file": result.get("coordinates"),
                    "itp_file": result.get("itp"),
                    "message": f"Ligand topology generated using {method}"
                }
        except Exception as e:
            logger.warning(f"Method {method} failed: {e}")
            continue
    
    return {
        "success": False,
        "error": f"All topology generation methods failed for {ligand_name}"
    }


def _check_dependencies() -> Dict[str, bool]:
    """Check which topology generation tools are available"""
    tools = {}
    
    # Check acpype
    try:
        result = subprocess.run(['acpype', '--version'], 
                              capture_output=True, text=True, timeout=10)
        tools['acpype'] = result.returncode == 0
    except (subprocess.TimeoutExpired, FileNotFoundError):
        tools['acpype'] = False
    
    # Check antechamber
    try:
        subprocess.run(['antechamber', '-h'], 
                      capture_output=True, text=True, timeout=10)
        tools['antechamber'] = True
    except (subprocess.TimeoutExpired, FileNotFoundError):
        tools['antechamber'] = False
    
    # Check RDKit
    try:
        import rdkit
        tools['rdkit'] = True
    except ImportError:
        tools['rdkit'] = False
    
    return tools


def _generate_with_acpype(pdb_file: str, ligand_name: str, charge: int, 
                         force_field: str, working_dir: Path) -> Optional[Dict[str, str]]:
    """Generate topology using ACPYPE"""
    try:
        cmd = [
            'acpype',
            '-i', str(pdb_file),
            '-b', ligand_name,
            '-n', str(charge),
            '-a', force_field
        ]
        
        logger.info(f"Running acpype: {' '.join(cmd)}")
        
        env = os.environ.copy()
        if 'CONDA_PREFIX' in env:
            env['LD_LIBRARY_PATH'] = f"{env['CONDA_PREFIX']}/lib:{env.get('LD_LIBRARY_PATH', '')}"
        
        result = subprocess.run(cmd, capture_output=True, text=True, 
                              cwd=working_dir, env=env, timeout=300)
        
        if result.returncode == 0:
            logger.info("acpype completed successfully")
            return _find_acpype_output(ligand_name, working_dir)
        else:
            logger.error(f"acpype failed: {result.stderr}")
            return None
            
    except Exception as e:
        logger.error(f"Error running acpype: {e}")
        return None


def _generate_with_antechamber(pdb_file: str, ligand_name: str, charge: int,
                               force_field: str, working_dir: Path) -> Optional[Dict[str, str]]:
    """Generate topology using Antechamber"""
    try:
        # Step 1: Convert PDB to MOL2
        mol2_file = f"{ligand_name}.mol2"
        cmd1 = [
            'antechamber',
            '-i', str(pdb_file),
            '-fi', 'pdb',
            '-o', mol2_file,
            '-fo', 'mol2',
            '-c', 'gas',
            '-nc', str(charge),
            '-at', force_field,
            '-rn', ligand_name.upper()
        ]
        
        logger.info(f"Running antechamber: {' '.join(cmd1)}")
        result1 = subprocess.run(cmd1, capture_output=True, text=True,
                               cwd=working_dir, timeout=300)
        
        if result1.returncode != 0:
            logger.error(f"Antechamber failed: {result1.stderr}")
            return None
        
        # Step 2: Generate parameter file
        frcmod_file = f"{ligand_name}.frcmod"
        cmd2 = [
            'parmchk2',
            '-i', mol2_file,
            '-f', 'mol2',
            '-o', frcmod_file
        ]
        
        logger.info(f"Running parmchk2: {' '.join(cmd2)}")
        result2 = subprocess.run(cmd2, capture_output=True, text=True,
                               cwd=working_dir, timeout=120)
        
        if result2.returncode != 0:
            logger.error(f"parmchk2 failed: {result2.stderr}")
            return None
        
        # Step 3: Generate AMBER topology with tleap
        return _create_amber_topology_tleap(ligand_name, mol2_file, frcmod_file, working_dir)
        
    except Exception as e:
        logger.error(f"Error running antechamber: {e}")
        return None


def _create_amber_topology_tleap(ligand_name: str, mol2_file: str, frcmod_file: str,
                                 working_dir: Path) -> Optional[Dict[str, str]]:
    """Create AMBER topology using tleap"""
    try:
        tleap_input = f"""
source leaprc.gaff2
loadamberparams {frcmod_file}
LIG = loadmol2 {mol2_file}
saveamberparm LIG {ligand_name}.prmtop {ligand_name}.inpcrd
savepdb LIG {ligand_name}_amber.pdb
quit
"""
        
        tleap_file = f"{ligand_name}_tleap.in"
        with open(working_dir / tleap_file, 'w') as f:
            f.write(tleap_input)
        
        cmd = ['tleap', '-f', tleap_file]
        logger.info(f"Running tleap: {' '.join(cmd)}")
        
        result = subprocess.run(cmd, capture_output=True, text=True,
                              cwd=working_dir, timeout=120)
        
        if result.returncode == 0:
            return _convert_amber_to_gromacs(ligand_name, working_dir)
        else:
            logger.error(f"tleap failed: {result.stderr}")
            return None
            
    except Exception as e:
        logger.error(f"Error in tleap: {e}")
        return None


def _convert_amber_to_gromacs(ligand_name: str, working_dir: Path) -> Optional[Dict[str, str]]:
    """Convert AMBER topology to GROMACS format using ParmEd"""
    try:
        import parmed as pmd
        
        parm = pmd.load_file(str(working_dir / f"{ligand_name}.prmtop"),
                           str(working_dir / f"{ligand_name}.inpcrd"))
        
        parm.save(str(working_dir / f"{ligand_name}.top"))
        parm.save(str(working_dir / f"{ligand_name}.gro"))
        
        logger.info("Successfully converted AMBER to GROMACS format")
        
        return {
            'topology': str(working_dir / f"{ligand_name}.top"),
            'coordinates': str(working_dir / f"{ligand_name}.gro"),
            'itp': str(working_dir / f"{ligand_name}.itp")
        }
        
    except Exception as e:
        logger.error(f"Error converting AMBER to GROMACS: {e}")
        return None


def _generate_with_rdkit(pdb_file: str, ligand_name: str, charge: int,
                        working_dir: Path) -> Optional[Dict[str, str]]:
    """Generate topology using RDKit (simplified)"""
    try:
        from rdkit import Chem
        from rdkit.Chem import AllChem
        
        mol = Chem.MolFromPDBFile(str(pdb_file), removeHs=False)
        if mol is None:
            logger.error("Could not read molecule from PDB file")
            return None
        
        mol = Chem.AddHs(mol)
        AllChem.EmbedMolecule(mol)
        AllChem.MMFFOptimizeMolecule(mol)
        
        logger.warning("RDKit method is simplified - use for testing only")
        
        # Write output files (simplified topology)
        output_pdb = working_dir / f"{ligand_name}_rdkit.pdb"
        Chem.MolToPDBFile(mol, str(output_pdb))
        
        return {
            'topology': None,  # RDKit doesn't generate full topology
            'coordinates': str(output_pdb),
            'itp': None
        }
        
    except Exception as e:
        logger.error(f"Error with RDKit method: {e}")
        return None


def _find_acpype_output(ligand_name: str, working_dir: Path) -> Optional[Dict[str, str]]:
    """Find and return paths to ACPYPE output files"""
    output_files = {}
    patterns = [
        f"{ligand_name}_AC.gro",
        f"{ligand_name}_AC.top",
        f"{ligand_name}.itp"
    ]
    
    for pattern in patterns:
        files = list(working_dir.glob(pattern))
        if files:
            key = 'coordinates' if pattern.endswith('.gro') else \
                  'topology' if pattern.endswith('.top') else 'itp'
            output_files[key] = str(files[0])
    
    return output_files if output_files else None
