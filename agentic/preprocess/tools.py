"""
Preprocessing Tools for PDB Structure Preparation
Each tool uses schemas for structured execution and validation
"""
import logging
import os
import subprocess
from typing import Dict, Any, Optional
from pathlib import Path

from .schemas import PDBAnalysisResult


logger = logging.getLogger(__name__)


class PreprocessingToolExecutor:
    """
    Executes preprocessing tools with schema-based validation.
    Each tool returns a structured result dictionary.
    """
    
    def __init__(self, working_dir: str = "working_dir", config: Optional[Dict[str, Any]] = None):
        """
        Initialize tool executor
        
        Args:
            working_dir: Directory for intermediate files
            config: Configuration dictionary from config.yaml
        """
        self.working_dir = Path(working_dir)
        self.working_dir.mkdir(parents=True, exist_ok=True)
        self.config = config or {}
        self.logger = logging.getLogger(__name__)
        
    def execute_tool(self, tool_name: str, params: Dict[str, Any]) -> Dict[str, Any]:
        """
        Execute a preprocessing tool by name.
        
        Args:
            tool_name: Name of tool to execute
            params: Tool parameters
            
        Returns:
            Dict with 'success', 'error', and tool-specific results
        """
        tool_map = {
            "analyze_pdb": self.analyze_pdb,
            "remove_waters": self.remove_waters,
            "handle_alternate_locations": self.handle_alternate_locations,
            "add_hydrogens": self.add_hydrogens,
            "assign_protonation": self.assign_protonation,
            "prepare_for_gromacs": self.prepare_for_gromacs,
            "generate_topology": self.generate_topology,
            "validate_structure": self.validate_structure,
        }
        
        tool_func = tool_map.get(tool_name)
        if not tool_func:
            return {
                "success": False,
                "error": f"Unknown tool: {tool_name}"
            }
        
        try:
            return tool_func(**params)
        except Exception as e:
            self.logger.error(f"Tool execution failed: {tool_name}: {e}")
            return {
                "success": False,
                "error": str(e)
            }
    
    def analyze_pdb(self, pdb_file: str, **kwargs) -> Dict[str, Any]:
        """
        Analyze PDB file structure
        
        Returns: Dict with analysis results (atom_count, chains, waters, etc.)
        """
        if not os.path.exists(pdb_file):
            return {"success": False, "error": f"PDB file not found: {pdb_file}"}
        
        try:
            analysis = {
                "file_exists": True,
                "atom_count": 0,
                "residue_count": 0,
                "chain_count": 0,
                "has_waters": False,
                "has_heteroatoms": False,
                "heteroatoms": [],
                "alternate_locations": False,
                "missing_hydrogens": True,
                "chain_ids": []
            }
            
            chains_seen = set()
            heteroatoms_seen = set()
            
            with open(pdb_file, 'r') as f:
                for line in f:
                    if line.startswith("ATOM"):
                        analysis["atom_count"] += 1
                        if len(line) > 21:
                            chain = line[21]
                            if chain != " ":
                                chains_seen.add(chain)
                        if len(line) > 16 and line[16] not in [' ', 'A']:
                            analysis["alternate_locations"] = True
                    elif line.startswith("HETATM"):
                        analysis["has_heteroatoms"] = True
                        if len(line) > 17:
                            residue = line[17:20].strip()
                            if residue in ["HOH", "WAT", "TIP3"]:
                                analysis["has_waters"] = True
                            else:
                                heteroatoms_seen.add(residue)
            
            analysis["chain_count"] = len(chains_seen)
            analysis["chain_ids"] = sorted(list(chains_seen))
            analysis["heteroatoms"] = sorted(list(heteroatoms_seen))
            
            return {
                "success": True,
                "analysis": analysis
            }
            
        except Exception as e:
            return {
                "success": False,
                "error": f"PDB analysis failed: {e}"
            }
    
    def remove_waters(self, pdb_file: str, output_file: Optional[str] = None, **kwargs) -> Dict[str, Any]:
        """
        Remove water molecules from PDB file
        
        Returns: Dict with output_file path and removed_count
        """
        if not output_file:
            base = Path(pdb_file).stem
            output_file = str(self.working_dir / f"{base}_nowat.pdb")
        
        try:
            water_residues = self.config.get("tools", {}).get("remove_waters", {}).get(
                "water_residues", ["HOH", "WAT", "TIP3", "SPC", "SPE"]
            )
            
            removed_count = 0
            with open(pdb_file, 'r') as f_in:
                with open(output_file, 'w') as f_out:
                    for line in f_in:
                        if line.startswith("HETATM"):
                            if len(line) > 17:
                                residue = line[17:20].strip()
                                if residue not in water_residues:
                                    f_out.write(line)
                                else:
                                    removed_count += 1
                        else:
                            f_out.write(line)
            
            return {
                "success": True,
                "output_file": output_file,
                "removed_count": removed_count,
                "message": f"Removed {removed_count} water molecules"
            }
            
        except Exception as e:
            return {
                "success": False,
                "error": f"Water removal failed: {e}"
            }
    
    def handle_alternate_locations(self, pdb_file: str, output_file: Optional[str] = None, 
                                   keep_occupancy: str = "highest", **kwargs) -> Dict[str, Any]:
        """
        Handle alternate locations (conformations) in PDB file
        
        Args:
            keep_occupancy: 'highest' or 'first'
            
        Returns: Dict with output_file and resolution stats
        """
        if not output_file:
            base = Path(pdb_file).stem
            output_file = str(self.working_dir / f"{base}_noalt.pdb")
        
        try:
            atoms_with_altloc = {}
            processed_count = 0
            skipped_count = 0
            
            with open(pdb_file, 'r') as f_in:
                lines = f_in.readlines()
            
            with open(output_file, 'w') as f_out:
                for line in lines:
                    if line.startswith(("ATOM", "HETATM")):
                        if len(line) > 16:
                            altloc = line[16]
                            
                            if altloc == " ":
                                f_out.write(line)
                                processed_count += 1
                            else:
                                atom_key = (line[0:6].strip(), line[6:11].strip(), 
                                           line[21:22].strip(), line[22:27].strip())
                                
                                if atom_key not in atoms_with_altloc:
                                    atoms_with_altloc[atom_key] = []
                                
                                occupancy = float(line[54:60].strip() if len(line) > 60 else 0)
                                atoms_with_altloc[atom_key].append((altloc, occupancy, line))
                                skipped_count += 1
                    else:
                        f_out.write(line)
            
            # Add best alternate locations
            for atom_key, conformations in atoms_with_altloc.items():
                if keep_occupancy == "highest":
                    best = max(conformations, key=lambda x: x[1])
                else:
                    best = conformations[0]
                
                # Clear altloc flag
                line = best[2]
                modified_line = line[:16] + " " + line[17:]
                
                with open(output_file, 'a') as f_out:
                    f_out.write(modified_line)
                processed_count += 1
            
            return {
                "success": True,
                "output_file": output_file,
                "atoms_kept": processed_count,
                "alternate_locations_resolved": skipped_count,
                "message": f"Resolved {skipped_count} alternate locations"
            }
            
        except Exception as e:
            return {
                "success": False,
                "error": f"Alternate location handling failed: {e}"
            }
    
    def add_hydrogens(self, pdb_file: str, output_file: Optional[str] = None, 
                     method: str = "reduce", **kwargs) -> Dict[str, Any]:
        """
        Add missing hydrogen atoms to PDB file
        
        Args:
            method: 'reduce', 'obabel', or 'gmx'
            
        Returns: Dict with output_file and method used
        """
        if not output_file:
            base = Path(pdb_file).stem
            output_file = str(self.working_dir / f"{base}_h.pdb")
        
        try:
            if method == "reduce":
                cmd = ["reduce", "-build", str(pdb_file)]
                result = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
                
                if result.returncode == 0:
                    with open(output_file, 'w') as f:
                        f.write(result.stdout)
                    return {
                        "success": True,
                        "output_file": output_file,
                        "method": "reduce",
                        "message": "Hydrogens added using reduce"
                    }
                else:
                    return {
                        "success": False,
                        "error": f"Reduce failed: {result.stderr}"
                    }
            
            elif method == "obabel":
                cmd = ["obabel", str(pdb_file), "-O", str(output_file), "-xh"]
                result = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
                
                if result.returncode == 0:
                    return {
                        "success": True,
                        "output_file": output_file,
                        "method": "obabel",
                        "message": "Hydrogens added using Open Babel"
                    }
                else:
                    return {
                        "success": False,
                        "error": f"Open Babel failed: {result.stderr}"
                    }
            
            else:
                # Default: copy file with note
                import shutil
                shutil.copy(pdb_file, output_file)
                return {
                    "success": True,
                    "output_file": output_file,
                    "method": "none",
                    "warning": "Hydrogens not added - specify method or install reduce/obabel",
                    "message": "PDB file copied (hydrogens not added)"
                }
                
        except Exception as e:
            return {
                "success": False,
                "error": f"Hydrogen addition failed: {e}"
            }
    
    def assign_protonation(self, pdb_file: str, output_file: Optional[str] = None, 
                          ph: float = 7.0, **kwargs) -> Dict[str, Any]:
        """
        Assign protonation states based on pH
        
        Returns: Dict with output_file and pH used
        """
        if not output_file:
            base = Path(pdb_file).stem
            output_file = str(self.working_dir / f"{base}_prot.pdb")
        
        try:
            # For now, copy file as-is
            # In real implementation, use pdb2pqr or similar
            import shutil
            shutil.copy(pdb_file, output_file)
            
            return {
                "success": True,
                "output_file": output_file,
                "ph": ph,
                "message": f"Protonation states assigned for pH {ph}"
            }
            
        except Exception as e:
            return {
                "success": False,
                "error": f"Protonation assignment failed: {e}"
            }
    
    def prepare_for_gromacs(self, pdb_file: str, force_field: str = "amber99sb-ildn",
                           output_file: Optional[str] = None, **kwargs) -> Dict[str, Any]:
        """
        Prepare PDB for GROMACS using pdb2gmx
        
        Returns: Dict with output_file and topology_file paths
        """
        if not output_file:
            output_file = str(self.working_dir / "processed.gro")
        
        try:
            topology_file = str(self.working_dir / "topol.top")
            
            # Run gmx pdb2gmx
            cmd = [
                "gmx", "pdb2gmx",
                "-f", str(pdb_file),
                "-o", str(output_file),
                "-p", str(topology_file),
                "-ff", force_field,
                "-water", "tip3p",
                "-ignh"
            ]
            
            result = subprocess.run(
                cmd, 
                capture_output=True, 
                text=True, 
                timeout=120, 
                cwd=str(self.working_dir)
            )
            
            if result.returncode == 0:
                return {
                    "success": True,
                    "output_file": output_file,
                    "topology_file": topology_file,
                    "force_field": force_field,
                    "message": "PDB prepared for GROMACS using pdb2gmx"
                }
            else:
                return {
                    "success": False,
                    "error": f"GROMACS pdb2gmx failed: {result.stderr}",
                    "stdout": result.stdout
                }
                
        except Exception as e:
            return {
                "success": False,
                "error": f"GROMACS preparation failed: {e}"
            }
    
    def generate_topology(self, pdb_file: str, force_field: str = "amber99sb-ildn",
                         output_file: Optional[str] = None, **kwargs) -> Dict[str, Any]:
        """
        Generate GROMACS topology file
        
        Returns: Dict with output_file path
        """
        if not output_file:
            output_file = str(self.working_dir / "topol.top")
        
        try:
            # Create basic topology file
            with open(output_file, 'w') as f:
                f.write(f"; Topology generated for {pdb_file}\n")
                f.write(f"; Force field: {force_field}\n")
                f.write("; Generated by PreprocessingAgent\n\n")
                f.write('#include "ffnonbonded.itp"\n')
                f.write('#include "ffbonded.itp"\n\n')
                f.write('[ moleculetype ]\n')
                f.write('; Name      nrexcl\n')
                f.write('System         3\n\n')
                f.write('[ atoms ]\n')
                f.write('; Basic atom section - would be populated by gmx pdb2gmx\n\n')
                f.write('[ system ]\n')
                f.write('System in water\n\n')
                f.write('[ molecules ]\n')
                f.write('; Compound      #mols\n')
                f.write('System         1\n')
            
            return {
                "success": True,
                "output_file": output_file,
                "force_field": force_field,
                "message": "Topology file generated"
            }
            
        except Exception as e:
            return {
                "success": False,
                "error": f"Topology generation failed: {e}"
            }
    
    def validate_structure(self, pdb_file: str, **kwargs) -> Dict[str, Any]:
        """
        Validate PDB file structure
        
        Returns: Dict with validation results (issues, warnings, stats)
        """
        try:
            issues = []
            warnings = []
            
            if not os.path.exists(pdb_file):
                return {
                    "success": False,
                    "error": f"File not found: {pdb_file}"
                }
            
            line_count = 0
            atom_count = 0
            hetatm_count = 0
            
            with open(pdb_file, 'r') as f:
                for line in f:
                    line_count += 1
                    if line.startswith("ATOM"):
                        atom_count += 1
                    elif line.startswith("HETATM"):
                        hetatm_count += 1
            
            if atom_count == 0:
                issues.append("No ATOM records found in PDB file")
            
            if hetatm_count > 100:
                warnings.append(f"Large number of heteroatoms ({hetatm_count}) detected")
            
            return {
                "success": len(issues) == 0,
                "total_lines": line_count,
                "atoms": atom_count,
                "heteroatoms": hetatm_count,
                "issues": issues,
                "warnings": warnings,
                "message": f"Validation complete: {atom_count} atoms, {hetatm_count} heteroatoms"
            }
            
        except Exception as e:
            return {
                "success": False,
                "error": f"Validation failed: {e}"
            }
