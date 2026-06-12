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
        
        # Log for debugging
        print(f"DEBUG: Loaded {pdb_file} with {len(u.atoms)} atoms, {len(u.residues)} residues")
        
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
        
        from src.preprocess.phospho_residues import (
            phospho_resname_mda_selection,
            select_phospho_protein_atoms,
        )

        # Analyze ligands (exclude protein, water, ions, phosphorylated amino acids)
        phospho_sel = phospho_resname_mda_selection()
        ligand = u.select_atoms(
            "not protein and not (resname HOH WAT TIP3 SOL NA CL K CA MG ZN FE CU "
            "ZN2 CA2 MG2 SOD CLA) and not ("
            + phospho_sel
            + ")"
        )
        phospho_atoms = select_phospho_protein_atoms(u)
        if len(phospho_atoms) > 0:
            ligand = ligand - phospho_atoms
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
        
        # Analyze ions (avoid 'ion' keyword which may not work in all MDAnalysis versions)
        try:
            # Try with 'ion' keyword first
            ions = u.select_atoms("ion or resname NA CL K CA MG ZN")
        except Exception:
            # Fallback: use only residue names
            ions = u.select_atoms("resname NA CL K CA MG ZN FE CU ZN2 CA2 MG2 SOD CLA")
        
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
        

        # Chain information (summary)
        all_chains = list(set(u.atoms.chainIDs))
        analysis["chain_ids"] = sorted([c for c in all_chains if c.strip()])
        analysis["chain_count"] = len(analysis["chain_ids"])
        
        # Add components available summary (simplified)
        analysis["components_available"] = {
            "protein": analysis["protein"]["present"],
            "ligand": analysis["ligands"]["present"],
            "water": analysis["water"]["present"],
            "ions": analysis["ions"]["present"],
            "hydrogens": not analysis["missing_hydrogens"]
        }
        
        # Generate detailed human-readable summary for planner context
        summary_parts = []
        
        # Protein details
        if analysis["protein"]["present"]:
            protein_info = analysis["protein"]
            chains_info = protein_info.get("chains", {})
            if chains_info:
                chain_details = []
                for chain_id, chain_data in sorted(chains_info.items()):
                    chain_details.append(
                        f"Chain {chain_id} ({chain_data['residue_count']} residues)"
                    )
                summary_parts.append(f"Protein: {', '.join(chain_details)}")
            else:
                summary_parts.append(f"Protein: {protein_info['total_residues']} residues")
        
        # Ligand details
        if analysis["ligands"]["present"]:
            ligand_info = analysis["ligands"]
            ligand_details = ligand_info.get("residue_details", {})
            if ligand_details:
                ligand_summary = []
                for lig_name, lig_data in sorted(ligand_details.items()):
                    count = lig_data.get("residue_count", 1)
                    ligand_summary.append(f"{lig_name} (×{count})" if count > 1 else lig_name)
                summary_parts.append(f"Ligands: {', '.join(ligand_summary)}")
            else:
                ligand_names = ligand_info.get("residue_names", [])
                summary_parts.append(f"Ligands: {', '.join(ligand_names)}")
        
        # Water details
        if analysis["water"]["present"]:
            water_count = analysis["water"]["molecule_count"]
            summary_parts.append(f"Water: {water_count} molecules")
        
        # Ion details
        if analysis["ions"]["present"]:
            ion_types = analysis["ions"].get("types", {})
            if ion_types:
                ion_summary = [f"{name} (×{count})" if count > 1 else name 
                              for name, count in sorted(ion_types.items())]
                summary_parts.append(f"Ions: {', '.join(ion_summary)}")
        
        # Preprocessing needs
        preprocessing_notes = []
        if analysis["missing_hydrogens"]:
            preprocessing_notes.append("missing hydrogens")
        if preprocessing_notes:
            summary_parts.append(f"Needs: {', '.join(preprocessing_notes)}")
        
        human_readable_summary = " | ".join(summary_parts)
        analysis["human_readable_summary"] = human_readable_summary
        
        return {
            "success": True,
            "analysis": analysis,
            "message": f"Analyzed {pdb_file}: {analysis['total_atoms']} atoms, {analysis['total_residues']} residues",
            "summary": human_readable_summary
        }
        
    except Exception as e:
        import traceback
        error_details = traceback.format_exc()
        print(f"ERROR in PDB analysis: {str(e)}")
        print(f"Traceback:\n{error_details}")
        return {
            "success": False,
            "error": f"Structure analysis failed: {str(e)}",
            "details": error_details
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
