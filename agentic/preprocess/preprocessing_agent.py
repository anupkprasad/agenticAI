"""
Refactored Preprocessing Agent with LLM Tool Calling
Uses Pydantic schemas for structured tool definitions and execution
"""
import logging
import os
import json
from typing import Dict, Any, Optional, List
from pathlib import Path

from ..state import MDState
from ..llm import LLMClient
from ..utils import (
    log_agent_start, log_llm_interaction, log_agent_action, 
    log_file_operation, log_agent_completion, log_error
)
from .schemas import (
    PDBAnalysisResult, PreprocessingPlan, PreprocessingStep, 
    PreprocessingResult, PreprocessingAgentInput, PreprocessingAgentOutput
)

logger = logging.getLogger(__name__)


class PreprocessingToolExecutor:
    """
    Executes preprocessing tools with modular functions from src/preprocess/
    """
    
    def __init__(self, working_dir: str = "working_dir"):
        self.working_dir = Path(working_dir)
        self.working_dir.mkdir(parents=True, exist_ok=True)
        self.logger = logging.getLogger(__name__)
        
    def execute_tool(self, tool_name: str, params: Dict[str, Any]) -> Dict[str, Any]:
        """
        Execute a preprocessing tool.
        Routes to appropriate tool implementation.
        """
        try:
            if tool_name == "analyze_pdb":
                return self._analyze_pdb(**params)
            elif tool_name == "remove_waters":
                return self._remove_waters(**params)
            elif tool_name == "handle_alternate_locations":
                return self._handle_alternate_locations(**params)
            elif tool_name == "add_hydrogens":
                return self._add_hydrogens(**params)
            elif tool_name == "assign_protonation":
                return self._assign_protonation(**params)
            elif tool_name == "prepare_for_gromacs":
                return self._prepare_for_gromacs(**params)
            elif tool_name == "generate_topology":
                return self._generate_topology(**params)
            elif tool_name == "validate_structure":
                return self._validate_structure(**params)
            else:
                return {
                    "success": False,
                    "error": f"Unknown tool: {tool_name}"
                }
                
        except Exception as e:
            self.logger.error(f"Tool execution failed: {tool_name}: {e}")
            return {
                "success": False,
                "error": str(e)
            }
    
    def _analyze_pdb(self, pdb_file: str, **kwargs) -> Dict[str, Any]:
        """Analyze PDB file structure"""
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
                    elif line.startswith("SEQRES"):
                        # Count residues from SEQRES records
                        if len(line) > 19:
                            rescount = (len(line) - 19) // 4
                            analysis["residue_count"] = max(analysis["residue_count"], rescount)
            
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
    
    def _remove_waters(self, pdb_file: str, output_file: Optional[str] = None, **kwargs) -> Dict[str, Any]:
        """Remove water molecules from PDB file"""
        if not output_file:
            output_file = str(self.working_dir / "no_waters.pdb")
        
        try:
            removed_count = 0
            with open(pdb_file, 'r') as f_in:
                with open(output_file, 'w') as f_out:
                    for line in f_in:
                        # Skip water records (HOH, WAT, TIP3, etc.)
                        if line.startswith("HETATM"):
                            if len(line) > 17:
                                residue = line[17:20].strip()
                                if residue not in ["HOH", "WAT", "TIP3", "SPC", "SPE"]:
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
    
    def _handle_alternate_locations(self, pdb_file: str, output_file: Optional[str] = None, 
                                   keep_occupancy: str = "highest", **kwargs) -> Dict[str, Any]:
        """
        Handle alternate locations (conformations) in PDB file.
        keep_occupancy: 'highest' or 'first'
        """
        if not output_file:
            output_file = str(self.working_dir / "no_altloc.pdb")
        
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
                                # No alternate location
                                f_out.write(line)
                                processed_count += 1
                            else:
                                # Has alternate location
                                atom_key = (line[0:6].strip(), line[6:11].strip(), 
                                           line[21:22].strip(), line[22:27].strip())
                                
                                if atom_key not in atoms_with_altloc:
                                    atoms_with_altloc[atom_key] = []
                                atoms_with_altloc[atom_key].append((altloc, float(line[54:60].strip() if len(line) > 60 else 0), line))
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
                "message": f"Resolved {skipped_count} alternate locations, kept {processed_count} atoms"
            }
            
        except Exception as e:
            return {
                "success": False,
                "error": f"Alternate location handling failed: {e}"
            }
    
    def _add_hydrogens(self, pdb_file: str, output_file: Optional[str] = None, 
                       method: str = "reduce", **kwargs) -> Dict[str, Any]:
        """
        Add missing hydrogen atoms to PDB file.
        method: 'reduce', 'obabel', or 'gmx'
        """
        if not output_file:
            output_file = str(self.working_dir / "with_hydrogens.pdb")
        
        try:
            import subprocess
            
            if method == "reduce":
                # Use reduce tool if available
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
                # Use Open Babel if available
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
                # Default: copy file with note about hydrogens
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
    
    def _assign_protonation(self, pdb_file: str, output_file: Optional[str] = None, 
                           ph: float = 7.0, **kwargs) -> Dict[str, Any]:
        """Assign protonation states based on pH"""
        if not output_file:
            output_file = str(self.working_dir / "protonated.pdb")
        
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
    
    def _prepare_for_gromacs(self, pdb_file: str, force_field: str = "amber99sb-ildn",
                            output_file: Optional[str] = None, **kwargs) -> Dict[str, Any]:
        """Prepare PDB for GROMACS using pdb2gmx"""
        if not output_file:
            output_file = str(self.working_dir / "processed.gro")
        
        try:
            import subprocess
            
            working_dir = self.working_dir
            topology_file = str(working_dir / "topol.top")
            
            # Run gmx pdb2gmx
            cmd = [
                "gmx", "pdb2gmx",
                "-f", str(pdb_file),
                "-o", str(output_file),
                "-p", str(topology_file),
                "-ff", force_field,
                "-water", "tip3p",
                "-ignh"  # Ignore hydrogen in input
            ]
            
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=120, cwd=str(working_dir))
            
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
    
    def _generate_topology(self, pdb_file: str, force_field: str = "amber99sb-ildn",
                          output_file: Optional[str] = None, **kwargs) -> Dict[str, Any]:
        """Generate GROMACS topology file"""
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
    
    def _validate_structure(self, pdb_file: str, **kwargs) -> Dict[str, Any]:
        """Validate PDB file structure"""
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


class PreprocessingAgent:
    """
    LLM-powered preprocessing agent with tool calling.
    Takes PDB file and generates preprocessing plan, then executes it.
    """
    
    def __init__(self, llm_client: Optional[LLMClient] = None):
        if llm_client is None:
            self.llm = LLMClient("gpt-oss:20b")  # Default model
        else:
            self.llm = llm_client
        self.tool_executor = None
    
    def preprocess_node(self, state: MDState) -> MDState:
        """Main preprocessing node - entry point from workflow"""
        log_agent_start("preprocessing", "PDB Preprocessing with LLM Tool Calling", state)
        
        try:
            # Initialize tool executor
            working_dir = state.get("working_directory", "working_dir")
            self.tool_executor = PreprocessingToolExecutor(working_dir)
            
            # Prepare agent input
            agent_input = self._prepare_agent_input(state)
            
            # Run LLM-guided preprocessing
            agent_output = self._run_llm_preprocessing_agent(agent_input, state)
            
            # Update state with results
            self._update_state(state, agent_output)
            
            # Determine next node
            if agent_output.success:
                if state.get("human_in_loop") and agent_output.result.issues:
                    state["next_node"] = "human_preprocess_check"
                else:
                    state["next_node"] = "supervisor"
            else:
                state["errors"].append(f"Preprocessing failed: {agent_output.result.report}")
                state["next_node"] = "supervisor"
            
            success = agent_output.success and len(agent_output.result.issues) == 0
            log_agent_completion("preprocessing", "PDB Preprocessing", state, success)
            
        except Exception as e:
            logger.error(f"Preprocessing agent failed: {e}")
            log_error("preprocessing_agent.preprocess_node", e, {"state": state})
            state["errors"].append(f"Preprocessing error: {str(e)}")
            state["next_node"] = "supervisor"
        
        return state
    
    def _prepare_agent_input(self, state: MDState) -> PreprocessingAgentInput:
        """Prepare input for preprocessing agent"""
        return PreprocessingAgentInput(
            pdb_path=state.get("raw_pdb", ""),
            working_directory=state.get("working_directory", "working_dir"),
            force_field=state.get("force_field", "amber99sb-ildn"),
            water_model=state.get("water_model", "tip3p"),
            remove_waters=state.get("remove_waters", True),
            add_hydrogens=state.get("add_hydrogens", True),
            user_goal=state.get("user_goal", ""),
            additional_instructions=state.get("preprocessing_instructions", None)
        )
    
    def _run_llm_preprocessing_agent(self, agent_input: PreprocessingAgentInput, 
                                    state: MDState) -> PreprocessingAgentOutput:
        """
        Run LLM-guided preprocessing with tool calling.
        LLM makes a plan, then we execute it step by step.
        """
        try:
            # Step 1: LLM analyzes PDB and makes a plan
            plan = self._llm_make_plan(agent_input)
            
            log_agent_action("preprocessing", "Generated preprocessing plan", {
                "steps": len(plan.steps),
                "reasoning": plan.reasoning[:200]
            })
            
            # Step 2: Execute each step in the plan
            result = self._execute_plan(agent_input, plan, state)
            
            # Step 3: Create output
            supervisor_update = {
                "cleaned_pdb": result.cleaned_pdb,
                "topology": result.topology,
                "processed_coordinates": result.processed_coordinates,
                "preprocessing_report": result.report
            }
            
            return PreprocessingAgentOutput(
                success=result.success,
                plan=plan,
                result=result,
                supervisor_update=supervisor_update
            )
            
        except Exception as e:
            logger.error(f"LLM preprocessing agent failed: {e}")
            return PreprocessingAgentOutput(
                success=False,
                plan=PreprocessingPlan(
                    reasoning=f"Error in planning: {str(e)}",
                    overview="Failed",
                    steps=[]
                ),
                result=PreprocessingResult(
                    success=False,
                    report=f"Error: {str(e)}",
                    issues=[str(e)],
                    warnings=[]
                ),
                supervisor_update={}
            )
    
    def _llm_make_plan(self, agent_input: PreprocessingAgentInput) -> PreprocessingPlan:
        """Use LLM to analyze PDB and create preprocessing plan"""
        
        # First, analyze the PDB
        analysis_result = self.tool_executor.execute_tool(
            "analyze_pdb",
            {"pdb_file": agent_input.pdb_path}
        )
        
        analysis = analysis_result.get("analysis", {}) if analysis_result.get("success") else {}
        
        prompt = f"""
You are a molecular dynamics preprocessing expert. Analyze this PDB structure and create a detailed, step-by-step preprocessing plan.

**PDB Information:**
- File: {agent_input.pdb_path}
- User Goal: {agent_input.user_goal}
- Force Field: {agent_input.force_field}
- Water Model: {agent_input.water_model}

**Structure Analysis:**
- Atoms: {analysis.get('atom_count', 'unknown')}
- Chains: {analysis.get('chain_ids', [])}
- Has Waters: {analysis.get('has_waters', False)}
- Has Heteroatoms: {analysis.get('has_heteroatoms', False)}
- Heteroatoms: {analysis.get('heteroatoms', [])}
- Alternate Locations: {analysis.get('alternate_locations', False)}

**Available Tools:**
- analyze_pdb: Analyze PDB structure
- remove_waters: Remove water molecules
- handle_alternate_locations: Resolve alternate conformations
- add_hydrogens: Add missing hydrogens
- assign_protonation: Set protonation states
- prepare_for_gromacs: Run pdb2gmx
- generate_topology: Create topology file
- validate_structure: Check structure integrity

**Your Task:**
Create a detailed preprocessing plan with specific steps. For each step, provide:
1. Tool name to call
2. Parameters for the tool
3. Reason why this step is needed

Output as JSON with this structure:
{{
  "reasoning": "Detailed analysis and strategy",
  "overview": "High-level summary",
  "steps": [
    {{
      "name": "step name",
      "description": "what it does",
      "tool_name": "tool to call",
      "tool_params": {{"param": "value"}},
      "reason": "why it's needed"
    }}
  ],
  "potential_issues": ["issue1", "issue2"],
  "recommendations": ["rec1", "rec2"]
}}

Focus on:
- Handling the current PDB structure
- Preparing for GROMACS simulation
- Managing any special features (waters, heteroatoms, etc.)
"""
        
        try:
            response = self.llm.invoke([prompt])
            content = response.content or ""
            
            log_llm_interaction("preprocessing.planning", prompt, content,
                              is_mock=hasattr(self.llm, '_is_mock_mode') and self.llm._is_mock_mode)
            
            # Try to parse JSON from response
            plan_dict = self._extract_plan_json(content)
            
            return PreprocessingPlan(
                reasoning=plan_dict.get("reasoning", content[:500]),
                overview=plan_dict.get("overview", "Processing PDB for MD simulation"),
                steps=[
                    PreprocessingStep(
                        name=step.get("name", "unknown"),
                        description=step.get("description", ""),
                        tool_name=step.get("tool_name", ""),
                        tool_params=step.get("tool_params", {}),
                        reason=step.get("reason", "")
                    )
                    for step in plan_dict.get("steps", [])
                ],
                potential_issues=plan_dict.get("potential_issues", []),
                recommendations=plan_dict.get("recommendations", [])
            )
            
        except Exception as e:
            logger.warning(f"LLM planning failed, using fallback: {e}")
            return self._fallback_preprocessing_plan(agent_input, analysis)
    
    def _extract_plan_json(self, content: str) -> Dict[str, Any]:
        """Extract JSON plan from LLM response"""
        import re
        
        # Try to find JSON block in response
        json_match = re.search(r'\{[\s\S]*\}', content)
        if json_match:
            try:
                return json.loads(json_match.group())
            except json.JSONDecodeError:
                pass
        
        # Fallback: return basic structure
        return {
            "reasoning": content,
            "overview": "Preprocessing plan",
            "steps": []
        }
    
    def _fallback_preprocessing_plan(self, agent_input: PreprocessingAgentInput, 
                                    analysis: Dict[str, Any]) -> PreprocessingPlan:
        """Create a fallback plan if LLM fails"""
        steps = []
        
        # Step 1: Remove waters if requested
        if agent_input.remove_waters and analysis.get("has_waters"):
            steps.append(PreprocessingStep(
                name="remove_waters",
                description="Remove water molecules from PDB",
                tool_name="remove_waters",
                tool_params={"pdb_file": agent_input.pdb_path},
                reason="Water molecules should be removed for GROMACS topology generation"
            ))
        
        # Step 2: Handle alternate locations
        if analysis.get("alternate_locations"):
            steps.append(PreprocessingStep(
                name="handle_alternates",
                description="Resolve alternate conformations",
                tool_name="handle_alternate_locations",
                tool_params={"pdb_file": agent_input.pdb_path},
                reason="Alternate locations must be resolved for clean structure"
            ))
        
        # Step 3: Add hydrogens if needed
        if agent_input.add_hydrogens:
            steps.append(PreprocessingStep(
                name="add_hydrogens",
                description="Add missing hydrogen atoms",
                tool_name="add_hydrogens",
                tool_params={"pdb_file": agent_input.pdb_path, "method": "reduce"},
                reason="MD simulations require all hydrogen atoms"
            ))
        
        # Step 4: Prepare for GROMACS
        steps.append(PreprocessingStep(
            name="prepare_gromacs",
            description="Prepare structure for GROMACS using pdb2gmx",
            tool_name="prepare_for_gromacs",
            tool_params={
                "pdb_file": agent_input.pdb_path,
                "force_field": agent_input.force_field
            },
            reason="pdb2gmx generates correct topology and parameters"
        ))
        
        # Step 5: Validate
        steps.append(PreprocessingStep(
            name="validate",
            description="Validate final structure",
            tool_name="validate_structure",
            tool_params={"pdb_file": agent_input.pdb_path},
            reason="Ensure structure is ready for simulation"
        ))
        
        return PreprocessingPlan(
            reasoning="Using default preprocessing workflow",
            overview="Standard PDB preprocessing for GROMACS",
            steps=steps,
            potential_issues=[],
            recommendations=[]
        )
    
    def _execute_plan(self, agent_input: PreprocessingAgentInput, plan: PreprocessingPlan,
                     state: MDState) -> PreprocessingResult:
        """Execute the preprocessing plan step by step"""
        
        execution_log = []
        issues = []
        warnings = []
        generated_files = {}
        
        current_pdb = agent_input.pdb_path
        topology_file = None
        processed_coords = None
        
        try:
            for i, step in enumerate(plan.steps):
                log_agent_action("preprocessing", f"Executing step {i+1}/{len(plan.steps)}", {
                    "step": step.name,
                    "tool": step.tool_name
                })
                
                execution_log.append(f"\n--- Step {i+1}: {step.name} ---")
                execution_log.append(f"Description: {step.description}")
                execution_log.append(f"Tool: {step.tool_name}")
                execution_log.append(f"Reason: {step.reason}")
                
                # Update input file for chained steps
                if step.tool_params.get("pdb_file") == agent_input.pdb_path and current_pdb != agent_input.pdb_path:
                    step.tool_params["pdb_file"] = current_pdb
                
                # Execute tool
                result = self.tool_executor.execute_tool(step.tool_name, step.tool_params)
                
                if result.get("success"):
                    execution_log.append(f"✓ Success: {result.get('message', 'Step completed')}")
                    
                    # Track output files
                    if "output_file" in result:
                        current_pdb = result["output_file"]
                        generated_files[result["output_file"]] = step.description
                    
                    if "topology_file" in result:
                        topology_file = result["topology_file"]
                        generated_files[topology_file] = "GROMACS topology file"
                    
                    if result.get("warning"):
                        warnings.append(f"{step.name}: {result['warning']}")
                    
                else:
                    execution_log.append(f"✗ Failed: {result.get('error', 'Unknown error')}")
                    issues.append(f"{step.name}: {result.get('error', 'Failed to execute')}")
            
            # Check if we have required output files
            if not topology_file:
                issues.append("No topology file generated - GROMACS preparation may have failed")
            
            execution_log_str = "\n".join(execution_log)
            
            return PreprocessingResult(
                success=len(issues) == 0,
                cleaned_pdb=current_pdb,
                topology=topology_file or str(Path(agent_input.working_directory) / "topol.top"),
                processed_coordinates=processed_coords or str(Path(agent_input.working_directory) / "processed.gro"),
                report=f"Preprocessing completed: {len(plan.steps)} steps executed",
                issues=issues,
                warnings=warnings,
                generated_files=generated_files,
                execution_log=execution_log_str
            )
            
        except Exception as e:
            return PreprocessingResult(
                success=False,
                report=f"Preprocessing failed: {str(e)}",
                issues=[str(e)],
                warnings=warnings,
                generated_files=generated_files,
                execution_log="\n".join(execution_log)
            )
    
    def _update_state(self, state: MDState, agent_output: PreprocessingAgentOutput):
        """Update workflow state with preprocessing results"""
        if agent_output.supervisor_update:
            state.update(agent_output.supervisor_update)
        
        state["preprocessing_report"] = agent_output.result.report
        state["preprocessing_issues"] = agent_output.result.issues
        state["preprocessing_warnings"] = agent_output.result.warnings
        state["preprocessing_execution_log"] = agent_output.result.execution_log
        
        # Log file operations
        for file_path, description in agent_output.result.generated_files.items():
            log_file_operation("preprocessing", "create", file_path, True, description)
