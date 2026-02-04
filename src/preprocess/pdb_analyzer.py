"""
PDB/GRO Structure Analysis Tool
Comprehensive analysis using MDAnalysis for detailed structure information
"""
import os
from typing import Dict, Any, List
from langchain.tools import tool


@tool
def analyze_pdb(pdb_file: str) -> Dict[str, Any]:
    """
    Analyze PDB/GRO file structure and composition using MDAnalysis.
    Provides comprehensive information about proteins, ligands, heteroatoms, and missing atoms.
    
    Args:
        pdb_file: Path to PDB or GRO file to analyze
        
    Returns:
        Dict with detailed analysis including:
        - Protein info (chains, sequences, residue counts)
        - Ligand info (residue names, atom counts)
        - Heteroatom details
        - Missing hydrogens and protonation state
        - Water molecules
        - Ions
        - Alternate locations
    """
    if not os.path.exists(pdb_file):
        return {"success": False, "error": f"File not found: {pdb_file}"}
    
    try:
        import MDAnalysis as mda
    except ImportError:
        return {
            "success": False,
            "error": "MDAnalysis not installed. Install with: pip install MDAnalysis"
        }
    
    try:
        # Load structure
        u = mda.Universe(pdb_file)
        
        # Initialize analysis dictionary
        analysis = {
            "file_exists": True,
            "file_format": pdb_file.split('.')[-1].upper(),
            "total_atoms": len(u.atoms),
            "total_residues": len(u.residues),
        }
        
        # Analyze protein components
        protein = u.select_atoms("protein")
        if len(protein) > 0:
            protein_chains = {}
            for chain_id in set(protein.chainIDs):
                chain_atoms = protein.select_atoms(f"chainID {chain_id}")
                chain_residues = chain_atoms.residues
                protein_chains[chain_id] = {
                    "residue_count": len(chain_residues),
                    "atom_count": len(chain_atoms),
                    "sequence": "".join([_three_to_one(r.resname) for r in chain_residues]),
                    "residue_range": f"{chain_residues[0].resid}-{chain_residues[-1].resid}",
                    "residue_names": list(set(chain_residues.resnames))[:20]  # First 20 unique
                }
            
            analysis["protein"] = {
                "present": True,
                "total_atoms": len(protein),
                "total_residues": len(protein.residues),
                "chain_count": len(protein_chains),
                "chains": protein_chains
            }
        else:
            analysis["protein"] = {"present": False}
        
        # Analyze ligands (non-protein, non-water, non-ion heteroatoms)
        ligand = u.select_atoms("not protein and not resname HOH WAT TIP3 SOL and not ion")
        if len(ligand) > 0:
            ligand_residues = {}
            for resname in set(ligand.residues.resnames):
                lig_atoms = ligand.select_atoms(f"resname {resname}")
                ligand_residues[resname] = {
                    "atom_count": len(lig_atoms),
                    "residue_count": len(lig_atoms.residues),
                    "elements": list(set(lig_atoms.elements)) if hasattr(lig_atoms, 'elements') else [],
                    "chain_ids": list(set(lig_atoms.chainIDs))
                }
            
            analysis["ligands"] = {
                "present": True,
                "total_atoms": len(ligand),
                "residue_names": sorted(list(set(ligand.residues.resnames))),
                "residue_details": ligand_residues
            }
        else:
            analysis["ligands"] = {"present": False}
        
        # Analyze heteroatoms (all non-protein atoms)
        hetero = u.select_atoms("not protein")
        hetero_resnames = list(set(hetero.residues.resnames))
        analysis["heteroatoms"] = hetero_resnames if len(hetero_resnames) > 0 else []
        analysis["has_heteroatoms"] = len(hetero_resnames) > 0
        
        # Analyze water molecules
        water = u.select_atoms("resname HOH WAT TIP3 TIP3P TIP4P SPC SPCE SOL")
        analysis["water"] = {
            "present": len(water) > 0,
            "molecule_count": len(water.residues) if len(water) > 0 else 0,
            "atom_count": len(water)
        }
        analysis["has_waters"] = len(water) > 0
        
        # Analyze ions
        ions = u.select_atoms("ion or resname NA CL K CA MG ZN")
        if len(ions) > 0:
            ion_types = {}
            for resname in set(ions.residues.resnames):
                ion_atoms = ions.select_atoms(f"resname {resname}")
                ion_types[resname] = len(ion_atoms)
            
            analysis["ions"] = {
                "present": True,
                "total_count": len(ions),
                "types": ion_types
            }
        else:
            analysis["ions"] = {"present": False}
        
        # Check for missing hydrogens
        all_atoms = u.atoms
        hydrogen_count = len(u.select_atoms("name H* or element H"))
        heavy_atom_count = len(all_atoms) - hydrogen_count
        
        # Estimate expected hydrogens (rough approximation)
        # Proteins: ~1:1 ratio, ligands vary, but we check if ANY hydrogens present
        analysis["hydrogens"] = {
            "present": hydrogen_count > 0,
            "count": hydrogen_count,
            "heavy_atom_count": heavy_atom_count,
            "missing_hydrogens": hydrogen_count == 0 or (hydrogen_count < heavy_atom_count * 0.5)
        }
        analysis["missing_hydrogens"] = analysis["hydrogens"]["missing_hydrogens"]
        
        # Check for alternate locations (only works with PDB files)
        analysis["alternate_locations"] = False
        if pdb_file.endswith('.pdb'):
            try:
                with open(pdb_file, 'r') as f:
                    for line in f:
                        if line.startswith(("ATOM", "HETATM")):
                            if len(line) > 16 and line[16] not in [' ', 'A']:
                                analysis["alternate_locations"] = True
                                break
            except:
                pass
        
        # Chain information (summary)
        all_chains = list(set(u.atoms.chainIDs))
        analysis["chain_ids"] = sorted([c for c in all_chains if c.strip()])
        analysis["chain_count"] = len(analysis["chain_ids"])
        
        # Add summary section
        analysis["summary"] = {
            "has_protein": analysis["protein"]["present"],
            "has_ligand": analysis["ligands"]["present"],
            "has_water": analysis["water"]["present"],
            "has_ions": analysis["ions"]["present"],
            "needs_hydrogen_addition": analysis["missing_hydrogens"],
            "needs_alternate_location_fix": analysis["alternate_locations"]
        }
        
        return {
            "success": True,
            "analysis": analysis,
            "message": f"Analyzed {pdb_file}: {analysis['total_atoms']} atoms, {analysis['total_residues']} residues"
        }
        
    except Exception as e:
        return {
            "success": False,
            "error": f"Structure analysis failed: {str(e)}"
        }


def _three_to_one(resname: str) -> str:
    """Convert three-letter amino acid code to one-letter code."""
    aa_map = {
        'ALA': 'A', 'CYS': 'C', 'ASP': 'D', 'GLU': 'E', 'PHE': 'F',
        'GLY': 'G', 'HIS': 'H', 'ILE': 'I', 'LYS': 'K', 'LEU': 'L',
        'MET': 'M', 'ASN': 'N', 'PRO': 'P', 'GLN': 'Q', 'ARG': 'R',
        'SER': 'S', 'THR': 'T', 'VAL': 'V', 'TRP': 'W', 'TYR': 'Y'
    }
    return aa_map.get(resname.upper(), 'X')
