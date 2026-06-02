"""
HPC Agent - Orchestrates job submission, monitoring, and result retrieval

Follows same sophisticated workflow pattern as preprocessing and setup agents:
LLM planning → Tool execution → Status monitoring → Result download
"""
import logging
import json
import yaml
import time
import os
from typing import Dict, Any, Optional, List
from pathlib import Path

from ..state import MDState
from ..llm import LLMClient
from ..utils import (
    log_agent_start, log_llm_interaction, log_agent_action,
    log_file_operation, log_agent_completion, log_error,
    log_supervisor_routing, SecureFileManager
)
from .tools import (
    copy_simulation_files, estimate_simulation_time, create_slurm_script,
    submit_job, check_job_status, download_results
)

logger = logging.getLogger(__name__)

try:
    import paramiko  # type: ignore
except Exception:
    paramiko = None


class MDHPCAgent:
    """
    LLM-powered HPC agent for job submission and monitoring.
    
    Workflow:
    1. Copy files from simsetup to working_dir/hpc
    2. Estimate simulation time and create SLURM script
    3. Submit job (with max 2 retry attempts)
    4. Monitor job status (hourly checks)
    5. Download results when complete
    """
    
    def __init__(self, llm_client: Optional[LLMClient] = None, config_path: Optional[str] = None):
        """
        Initialize HPC agent
        
        Args:
            llm_client: LLM client for intelligent planning
            config_path: Path to config.yaml
        """
        if llm_client is None:
            self.llm = LLMClient("gpt-oss:20b")
        else:
            self.llm = llm_client
        
        self.config = self._load_config(config_path)
        self.file_manager = None  # Initialized per execution for state-specific file registry
        logger.info("MD HPC Agent initialized")
        
    def _load_config(self, config_path: Optional[str] = None) -> Dict[str, Any]:
        """Load HPC configuration from YAML"""
        if config_path is None:
            config_path = Path(__file__).parent / "config.yaml"
        
        try:
            with open(config_path, 'r') as f:
                return yaml.safe_load(f)
        except Exception as e:
            logger.warning(f"Failed to load config from {config_path}: {e}")
            return self._default_config()
    
    def _default_config(self) -> Dict[str, Any]:
        """Fallback default configuration"""
        return {
            "ssh": {"host": None, "user": None, "port": 22, "key_path": None},
            "paths": {
                "remote_work_dir": "~/md_jobs",
                "local_hpc_dir": "./working_dir/hpc",
                "local_download_dir": "./working_dir/hpc/results"
            },
            "slurm_defaults": {
                "partition": "gpu_p",
                "cpus_per_task": 64,
                "memory": "40G",
                "gpu_count": 1,
                "gromacs_module": "GROMACS/2024.4-foss-2023b-CUDA-12.4.0-PLUMED-2.9.2"
            },
            "monitoring": {
                "check_interval": 3600,
                "max_checks": 48,
                "max_retries": 2
            }
        }
    
    def hpc_node(self, state: MDState) -> MDState:
        """
        Main HPC node - entry point from workflow.
        Orchestrates job submission, monitoring, and result download.
        """
        # Extract planner instructions if available
        execution_plan = state.get("execution_plan", {})
        has_planner_instructions = execution_plan.get("format") == "natural_language"
        
        input_summary = {
            "topology": state.get("topology"),
            "coordinates": state.get("coordinates"),
            "mdp_files": len(state.get("mdp_files", {})),
            "force_field": state.get("force_field"),
            "water_model": state.get("water_model")
        }
        
        if has_planner_instructions:
            # Prefer pre-extracted instructions from supervisor (avoids duplication)
            hpc_section = state.get("hpc_instructions")
            
            if not hpc_section:
                # Fallback: Extract from full plan if supervisor didn't provide it
                full_plan = execution_plan.get("full_plan", "")
                hpc_section = self._extract_agent_instructions(full_plan, "HPC Agent")
            
            if hpc_section:
                input_summary["planner_instructions"] = hpc_section
            else:
                input_summary["planner_instructions"] = "[Natural language plan from planner]"
        else:
            input_summary["user_goal"] = state.get("user_goal")
        
        log_agent_start("hpc", "HPC Job Submission and Monitoring", input_summary)
        
        hpc_dir = state.get("hpc_dir", "")
        try:
            # Initialize secure file manager
            working_dir = state.get("working_directory", "working_dir")
            file_registry = state.get("file_registry", {})
            
            self.file_manager = SecureFileManager(
                working_dir=working_dir,
                agent_name="hpc",
                file_registry=file_registry
            )
            
            logger.info(f"HPC agent directory: {self.file_manager.agent_dir}")
            
            # Get HPC directory from file manager (ensures consistency)
            hpc_dir = self.file_manager.agent_dir
            state["hpc_dir"] = hpc_dir
            state["hpc_directory"] = hpc_dir  # Backward compatibility
            state["hpc_output_directory"] = hpc_dir  # Also set this for analysis agent
            
            # Generate execution plan using LLM.
            # When human_recommendation is set, replan on top of the existing plan
            # so the recommendation is actually applied (not bypassed).
            exec_plan = state.get("execution_plan")
            human_rec = state.get("human_recommendation")
            if human_rec:
                logger.info("hpc: replanning with human guidance: %s", human_rec[:120])
                plan = self.replan_with_guidance(human_rec, state)
                if not plan:
                    # LLM unavailable — fall back to fresh plan
                    plan = self._create_execution_plan(state)
                    if not plan:
                        logger.warning("Failed to create execution plan, using fallback workflow")
                        plan = self._create_fallback_plan(state)
            else:
                plan = self._create_execution_plan(state)
                if not plan:
                    logger.warning("Failed to create execution plan, using fallback workflow")
                    plan = self._create_fallback_plan(state)

            # Persist structured plan to state for HITL inspection/modification
            if exec_plan is not None and plan:
                exec_plan.setdefault("structured_plans", {})["hpc"] = plan
            
            log_agent_action(
                "hpc",
                "Generated HPC execution plan",
                {
                    "steps": len(plan.get("steps", [])),
                    "reasoning": plan.get("reasoning", "N/A")[:200]
                }
            )
            
            # Execute plan steps
            success = self._execute_plan(state, plan, hpc_dir)
            
            # Log completion
            output_summary = {
                "job_id": state.get("job_id"),
                "job_status": state.get("job_status"),
                "job_script": state.get("job_script"),
                "trajectory_path": state.get("trajectory_path")
            }
            
            issues = state.get("errors", []) + [w for w in state.get("warnings", []) if "HPC" in w]
            if issues:
                output_summary["issues"] = issues
            
            log_agent_completion("hpc", "HPC Job Submission and Monitoring", state, success)
            
        except Exception as e:
            import traceback
            tb = traceback.format_exc()
            msg = f"HPC agent failed: {e}"
            logger.error(msg)
            logger.error(f"Traceback: {tb}")
            state["errors"].append(msg)
            log_error("hpc_agent.hpc_node", e, {"traceback": tb})
            success = False
        
        # Route — error-triggered HITL on failure, normal HITL if enabled
        if not success:
            state["next_node"] = "human_hpc_check"
            state["error_triggered_hitl"] = True
        else:
            # Clear any previous HPC-related errors from earlier retry attempts
            state["errors"] = [
                e for e in state.get("errors", [])
                if not (e.startswith("HPC agent failed:") or e.startswith("HPC execution failed"))
            ]
            if state.get("human_in_loop"):
                state["next_node"] = "human_hpc_check"
            else:
                state["next_node"] = "supervisor"
        reasoning = f"HPC agent completed - {'success' if success else 'with errors'}"
        log_supervisor_routing(state, state["next_node"], reasoning)
        
        return state
    
    def _extract_agent_instructions(self, full_plan: str, agent_name: str) -> str:
        """
        Extract agent-specific detailed instructions from planner's natural language plan.
        
        Args:
            full_plan: Complete natural language plan from planner
            agent_name: Name of the agent section to extract (e.g., "HPC Agent")
            
        Returns:
            Extracted instructions for this specific agent, or full plan as fallback
        """
        import re
        
        # Try multiple patterns to find the agent section (in priority order)
        patterns = [
            # New standardized format: **HPC Agent:**
            rf'\*\*HPC Agent:\*\*\s*\n(.*?)(?=\n\s*\*\*(?:Analysis Agent|Expected Outcomes):|$)',
            # With optional colon
            rf'\*\*{agent_name}\*\*:?\s*\n(.*?)(?=\n\s*\*\*[A-Z]|\Z)',
            # Markdown headings
            rf'###\s*{agent_name}.*?\n(.*?)(?=###|\Z)',
            rf'##\s*{agent_name}.*?\n(.*?)(?=##|\Z)',
            # Fuzzy match patterns
            rf'\*\*HPC.*?Agent\*\*:?\s*\n(.*?)(?=\n\s*\*\*[A-Z]|\Z)',
            rf'###\s*HPC.*?Agent.*?\n(.*?)(?=###|\Z)',
            rf'##\s*HPC.*?Agent.*?\n(.*?)(?=##|\Z)',
        ]
        
        for pattern in patterns:
            match = re.search(pattern, full_plan, re.DOTALL | re.IGNORECASE)
            if match:
                instructions = match.group(1).strip()
                if len(instructions) > 50:  # Ensure we got substantial content
                    return instructions
        
        # Fallback: Use full plan if no specific section found
        return full_plan
    
    def _create_execution_plan(self, state: MDState) -> Optional[Dict[str, Any]]:
        """Create HPC execution plan using LLM"""
        # Prefer pre-extracted instructions from supervisor
        planner_instructions = state.get("hpc_instructions", "")
        
        if not planner_instructions:
            # Fallback: Extract from execution_plan if supervisor didn't provide it
            execution_plan = state.get("execution_plan", {})
            if execution_plan.get("format") == "natural_language":
                full_plan = execution_plan.get("full_plan", "")
                hpc_section = self._extract_agent_instructions(full_plan, "HPC Agent")
                if hpc_section:
                    planner_instructions = hpc_section
        
        # Append human recommendation so the LLM sees it
        human_rec = state.get("human_recommendation")
        if human_rec:
            rec_block = (
                f"\n\n**HUMAN RECOMMENDATION (must be followed):**\n{human_rec}\n"
                "Adjust the HPC plan to incorporate this recommendation."
            )
            planner_instructions = (planner_instructions or "") + rec_block
        
        # Get system information
        mdp_files = state.get("mdp_files", {})
        
        # Calculate system size from coordinates if available
        system_size = self._estimate_system_size(state.get("coordinates"))
        
        # Build planning prompt
        prompt = self._build_planning_prompt(
            state,
            planner_instructions,
            system_size,
            mdp_files
        )
        
        # Check if LLM is available
        if not self.llm or not self.llm.available:
            logger.warning("LLM not available, skipping intelligent planning")
            return None
        
        # Call LLM
        try:
            response = self.llm.prompt(
                prompt,
                temperature=0.1
            )
            
            # Check if response is a mock
            is_mock = response.startswith("MOCK_LLM_RESPONSE") or response.startswith("LLM_ERROR")
            
            log_llm_interaction(
                "hpc.planning",
                prompt,
                response,
                is_mock=is_mock
            )
            
            # Skip parsing if mock response
            if is_mock:
                logger.warning("Received mock LLM response, skipping plan parsing")
                return None
            
            # Parse JSON response
            plan = json.loads(response)
            return plan
            
        except Exception as e:
            logger.error(f"LLM planning failed: {e}")
            return None
    
    def _build_planning_prompt(
        self,
        state: MDState,
        planner_instructions: str,
        system_size: int,
        mdp_files: Dict[str, str]
    ) -> str:
        """Build LLM prompt for execution planning"""
        
        # Get available tools
        tools_desc = self._get_tools_description()
        
        # Get configuration
        ssh_config = self.config.get("ssh", {})
        has_ssh = bool(ssh_config.get("host") and ssh_config.get("user"))

        # Resolve concrete directory paths so the LLM never has to guess them
        working_dir = state.get("working_directory", "working_dir")
        simsetup_dir = state.get("simsetup_dir", str(Path(working_dir) / "simsetup"))
        hpc_dir_path = state.get("hpc_dir", str(Path(working_dir) / "hpc"))

        # Derive a unique job name from the PDB file or working directory
        job_name = self._derive_job_name(state)

        prompt = f"""You are an HPC job submission and monitoring expert executing a detailed plan from the workflow planner.

**System Information:**
- Topology: {state.get("topology")}
- Coordinates: {state.get("coordinates")}
- System Size: ~{system_size} atoms
- Force Field: {state.get("force_field")}
- Water Model: {state.get("water_model")}
- MDP Files: {list(mdp_files.keys())}
- SLURM Job Name (use this EXACT value for job_name): {job_name}

**Working Directories (use these EXACT absolute paths — do NOT invent or modify):**
- Simsetup source directory (copy FROM): {simsetup_dir}
- HPC working directory (copy TO / run in): {hpc_dir_path}

**HPC Configuration:**
- Remote Access: {"SSH configured" if has_ssh else "Local submission only"}
- SSH Host: {ssh_config.get("host", "N/A")}
- Max Submission Retries: {self.config.get("monitoring", {}).get("max_retries", 2)}
- Monitoring Interval: {self.config.get("monitoring", {}).get("check_interval", 3600)} seconds

"""
        
        if planner_instructions:
            prompt += f"""**DETAILED INSTRUCTIONS FROM PLANNER:**
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
{planner_instructions}
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

"""
        
        prompt += f"""**Available Tools:**
{tools_desc}

**CRITICAL INSTRUCTIONS:**
- You MUST ONLY use the tools listed above
- Every "tool_name" must match exactly one of the tool names listed
- For copy_simulation_files: source_dir MUST be "{simsetup_dir}", dest_dir MUST be "{hpc_dir_path}"
- For create_slurm_script: job_name MUST be "{job_name}", working_dir MUST be "{hpc_dir_path}"
- For submit_job: remote_dir MUST be "{hpc_dir_path}"
- Tool execution order matters: copy files → estimate time → create script → submit → monitor → download
- Maximum 2 job submission attempts (if first fails, retry once)
- Monitor job hourly until completion
- Only download results after job completes successfully

**Your task:** Create a detailed execution plan that:
1. Copies simulation files from {simsetup_dir} → {hpc_dir_path}
2. Estimates simulation time based on system size and production length
3. Creates SLURM submission script with appropriate time limit (working_dir = {hpc_dir_path})
4. Submits job to HPC (with retry logic if needed)
5. Monitors job status periodically
6. Downloads results when job completes

Output as JSON with this structure:
{{
  "reasoning": "How you'll implement the planner's instructions",
  "overview": "High-level summary",
  "steps": [
    {{
      "name": "step name",
      "description": "what it does",
      "tool_name": "tool to call",
      "tool_params": {{"param": "value"}},
      "reason": "why it's needed",
      "retry_on_failure": true/false,
      "max_retries": 2
    }}
  ],
  "potential_issues": ["issue1"],
  "recommendations": ["rec1"]
}}
"""
        
        return prompt
    
    def _get_tools_description(self) -> str:
        """Generate description of available tools"""
        return """→ copy_simulation_files
  Copy simulation files from setup directory to HPC working directory.
  Parameters:
    • source_dir (required): No description
    • dest_dir (required): No description
    • file_patterns (optional): No description
    • create_dest (optional): No description

→ estimate_simulation_time
  Estimate simulation walltime based on system size and simulation length.
  Parameters:
    • production_ns (optional): No description
    • system_size (optional): No description
    • timestep_ps (optional): No description

→ create_slurm_script
  Create SLURM job submission script for GROMACS simulation.
  Parameters:
    • job_name (required): No description
    • working_dir (required): No description
    • topology_file (optional): No description
    • input_structure (optional): No description
    • simulation_phases (optional): No description
    • partition (optional): No description
    • cpus_per_task (optional): No description
    • memory (optional): No description
    • time_limit (optional): No description
    • gpu_count (optional): No description
    • email (optional): No description
    • gromacs_module (optional): No description

→ submit_job
  Submit SLURM job to HPC system.
  Parameters:
    • script_path (required): No description
    • remote_host (optional): No description
    • remote_user (optional): No description
    • remote_dir (optional): No description
    • ssh_key_path (optional): No description

→ check_job_status
  Check status of submitted SLURM job.
  Parameters:
    • job_id (required): No description
    • remote_host (optional): No description
    • remote_user (optional): No description
    • ssh_key_path (optional): No description

→ download_results
  Download simulation results from HPC system.
  Parameters:
    • remote_dir (required): No description
    • local_dir (required): No description
    • file_patterns (optional): No description
    • remote_host (optional): No description
    • remote_user (optional): No description
    • ssh_key_path (optional): No description
"""

    def replan_with_guidance(self, human_recommendation: str, state: dict) -> Optional[dict]:
        """Update the structured HPC plan by applying human guidance.

        If a current structured plan exists in state: sends it together with the human
        recommendation to the LLM so ONLY the requested changes are made (tool_params,
        steps, parameters).  Falls back to full re-planning via the normal prompt
        infrastructure when no current plan is available.

        Returns the updated plan dict, or None if the LLM call fails.
        """
        if not (self.llm and self.llm.available):
            return None

        import re as _re

        current_plan = (
            (state.get("execution_plan") or {})
            .get("structured_plans", {})
            .get("hpc")
        )

        if current_plan:
            # Modification mode: keep existing plan, apply targeted changes
            tools_str = self._get_tools_description()
            prompt = (
                f"You are updating an HPC SLURM job submission execution plan.\n\n"
                f"CURRENT PLAN (JSON):\n```json\n{json.dumps(current_plan, indent=2)}\n```\n\n"
                f"HUMAN GUIDANCE (apply ONLY these changes):\n{human_recommendation}\n\n"
                f"Available tools for reference (tool_name must match):\n{tools_str}\n\n"
                f"Rules:\n"
                f"- Apply ONLY the changes the human requested.\n"
                f"- Update tool_params values, add/remove/reorder steps as needed.\n"
                f"- Keep all other steps and fields exactly as they are.\n"
                f"- Preserve JSON structure: reasoning, overview, steps, potential_issues, recommendations.\n"
                f"- Each step must have: name, description, tool_name, tool_params, reason.\n"
                f"- Return ONLY valid JSON — no explanation, no markdown fences.\n"
            )
        else:
            # Fresh planning mode: build from planner NL instructions + human guidance
            nl_instructions = (
                (state.get("execution_plan") or {})
                .get("agent_plans", {})
                .get("hpc_agent", "")
            )
            augmented = (
                nl_instructions
                + "\n\n**HUMAN RECOMMENDATION (must be followed):**\n"
                + human_recommendation
                + "\nAdjust the HPC plan to incorporate this recommendation."
            ) if nl_instructions else (
                human_recommendation
                + "\nAdjust the HPC plan to incorporate this recommendation."
            )
            system_size = self._estimate_system_size(state.get("coordinates"))
            mdp_files = state.get("mdp_files", {})
            prompt = self._build_planning_prompt(state, augmented, system_size, mdp_files)

        try:
            resp = self.llm.prompt(prompt, temperature=0.1)
            m = _re.search(r'\{[\s\S]*\}', resp)
            return json.loads(m.group()) if m else None
        except Exception:
            return None

    def _derive_job_name(self, state: MDState) -> str:
        """Derive a unique SLURM job name for each simulation instance.

        Multi-simulation priority:
        1) current sim label from sim_prompts[current_sim_index] (e.g. p21860_ATP_MG)
        2) basename of per-sim working directory (e.g. p21860_ATP_MG)
        3) source structure stem (single-sim fallback)
        """
        import re
        # Priority 1: explicit per-sim label from master planner
        sim_prompts = state.get("sim_prompts") or []
        current_idx = state.get("current_sim_index")
        if isinstance(current_idx, int) and 0 <= current_idx < len(sim_prompts):
            label = (sim_prompts[current_idx] or {}).get("label")
            if label:
                safe = re.sub(r'[^A-Za-z0-9_\-]', '_', str(label))[:40]
                if safe:
                    return safe

        # Priority 2: basename of working directory (usually per-sim label)
        working_dir = state.get("working_directory", "")
        if working_dir:
            stem = Path(working_dir).name
            if stem and stem.lower() not in {"working_dir", "workdir", "tmp"}:
                safe = re.sub(r'[^A-Za-z0-9_\-]', '_', stem)[:40]
                if safe:
                    return safe

        # Priority 3: raw_pdb/cleaned/topology stem (single-sim fallback)
        for key in ("raw_pdb", "cleaned_pdb", "topology", "coordinates"):
            val = state.get(key)
            if val:
                stem = Path(val).stem
                # Strip common suffixes added during processing
                stem = re.sub(r'(_h|_clean|_processed|_solvated|_ions)$', '', stem, flags=re.IGNORECASE)
                if stem:
                    safe = re.sub(r'[^A-Za-z0-9_\-]', '_', stem)[:40]
                    return safe
        return "md_simulation"

    def _estimate_system_size(self, coordinates_file: Optional[str]) -> int:
        """Estimate number of atoms from coordinate file"""
        if not coordinates_file or not Path(coordinates_file).exists():
            return 50000  # Default estimate
        
        try:
            with open(coordinates_file, 'r') as f:
                lines = f.readlines()
                # Second line of GRO file contains atom count
                if len(lines) > 1:
                    return int(lines[1].strip())
        except Exception:
            pass
        
        return 50000
    
    def _create_fallback_plan(self, state: MDState) -> Dict[str, Any]:
        """Create basic fallback plan when LLM planning fails"""
        simsetup_dir = str(Path(state.get("working_directory", "working_dir")) / "simsetup")
        hpc_dir = state.get("hpc_directory", "working_dir/hpc")
        
        return {
            "reasoning": "Fallback plan: copy files, create script, submit job",
            "overview": "Basic HPC workflow without LLM guidance",
            "steps": [
                {
                    "name": "Copy simulation files",
                    "tool_name": "copy_simulation_files",
                    "tool_params": {
                        "source_dir": simsetup_dir,
                        "dest_dir": hpc_dir
                    },
                    "reason": "Prepare HPC working directory"
                },
                {
                    "name": "Estimate time",
                    "tool_name": "estimate_simulation_time",
                    "tool_params": {"production_ns": 10.0},
                    "reason": "Calculate appropriate time limit"
                },
                {
                    "name": "Create SLURM script",
                    "tool_name": "create_slurm_script",
                    "tool_params": {
                        "job_name": self._derive_job_name(state),
                        "working_dir": hpc_dir
                    },
                    "reason": "Generate submission script"
                },
                {
                    "name": "Submit job",
                    "tool_name": "submit_job",
                    "tool_params": {},
                    "reason": "Submit to HPC queue",
                    "retry_on_failure": True,
                    "max_retries": 2
                }
            ]
        }
    
    def _execute_plan(self, state: MDState, plan: Dict[str, Any], hpc_dir: str) -> bool:
        """Execute the HPC plan steps"""
        steps = plan.get("steps", [])
        success = True

        # Resolve correct paths once so every step shares them
        working_dir = state.get("working_directory", "working_dir")
        correct_simsetup = state.get("simsetup_dir", str(Path(working_dir) / "simsetup"))
        correct_hpc_dir  = hpc_dir or state.get("hpc_dir", str(Path(working_dir) / "hpc"))

        log_agent_action("hpc", "Generated HPC plan", {"steps": len(steps)})
        
        for i, step in enumerate(steps, 1):
            step_name = step.get("name", f"Step {i}")
            tool_name = step.get("tool_name")
            tool_params = step.get("tool_params", {})

            # Correct any hallucinated directory paths the LLM may have generated
            if tool_name == "copy_simulation_files":
                if tool_params.get("source_dir") != correct_simsetup:
                    logger.warning(
                        f"Correcting LLM-generated source_dir "
                        f"'{tool_params.get('source_dir')}' → '{correct_simsetup}'"
                    )
                    tool_params["source_dir"] = correct_simsetup
                if tool_params.get("dest_dir") != correct_hpc_dir:
                    logger.warning(
                        f"Correcting LLM-generated dest_dir "
                        f"'{tool_params.get('dest_dir')}' → '{correct_hpc_dir}'"
                    )
                    tool_params["dest_dir"] = correct_hpc_dir
            elif tool_name in ("create_slurm_script", "submit_job", "download_results"):
                # working_dir / remote_dir should always point at hpc_dir
                for key in ("working_dir", "remote_dir"):
                    if key in tool_params and tool_params[key] != correct_hpc_dir:
                        logger.warning(
                            f"Correcting LLM-generated {key} "
                            f"'{tool_params[key]}' → '{correct_hpc_dir}'"
                        )
                        tool_params[key] = correct_hpc_dir
            max_retries = max(step.get("max_retries", 1), 1)
            retry_on_failure = step.get("retry_on_failure", False)
            
            logger.info(f"Executing step {i}/{len(steps)}: {step_name}")
            log_agent_action("hpc", f"Executing step {i}/{len(steps)}", {
                "step": step_name,
                "tool": tool_name
            })
            
            # Execute with retry logic
            attempt = 0
            result = None
            
            while attempt < max_retries:
                attempt += 1
                result = self._execute_tool(tool_name, tool_params, state, hpc_dir)
                
                # Guard against None result from tool execution
                if result is None:
                    result = {"success": False, "error": f"Tool '{tool_name}' returned None"}
                
                if result.get("success"):
                    break
                elif retry_on_failure and attempt < max_retries:
                    logger.warning(f"Step failed, retrying ({attempt}/{max_retries}): {result.get('error')}")
                    time.sleep(5)  # Brief delay before retry
                else:
                    break
            
            # Log result
            if result is None:
                result = {"success": False, "error": f"Tool '{tool_name}' returned None"}
            if result.get("success"):
                log_agent_action("hpc", f"Step {i}/{len(steps)} completed", {
                    "step": step_name,
                    "tool": tool_name,
                    "status": "✅ SUCCESS"
                })
                
                # Update state with results
                self._update_state_from_result(state, tool_name, result)
                
            else:
                error_msg = f"{step_name}: {result.get('error', 'Unknown error')}"
                logger.error(f"Step failed: {error_msg}")
                log_agent_action("hpc", f"Step {i}/{len(steps)} failed", {
                    "step": step_name,
                    "tool": tool_name,
                    "status": "❌ FAILED",
                    "error": result.get("error")
                })
                
                state["errors"].append(error_msg)
                
                # For critical steps, stop execution
                if tool_name in ["copy_simulation_files", "create_slurm_script", "submit_job"]:
                    success = False
                    break
        
        return success
    
    def _execute_tool(
        self,
        tool_name: str,
        tool_params: Dict[str, Any],
        state: MDState,
        hpc_dir: str
    ) -> Dict[str, Any]:
        """Execute a specific tool with given parameters"""
        
        # Map tool names to functions
        tool_map = {
            "copy_simulation_files": copy_simulation_files,
            "estimate_simulation_time": estimate_simulation_time,
            "create_slurm_script": create_slurm_script,
            "submit_job": submit_job,
            "check_job_status": check_job_status,
            "download_results": download_results
        }
        
        tool_func = tool_map.get(tool_name)
        if not tool_func:
            return {"success": False, "error": f"Unknown tool: {tool_name}"}
        
        try:
            # Add configuration defaults if not specified
            tool_params = self._enrich_tool_params(tool_name, tool_params, state, hpc_dir)
            
            # Execute tool using .invoke() method for LangChain tools
            result = tool_func.invoke(tool_params)
            return result
            
        except Exception as e:
            logger.error(f"Tool execution failed: {tool_name} - {e}")
            return {"success": False, "error": str(e)}
    
    def _enrich_tool_params(
        self,
        tool_name: str,
        params: Dict[str, Any],
        state: MDState,
        hpc_dir: str
    ) -> Dict[str, Any]:
        """Add configuration defaults and state values to tool parameters"""
        enriched = params.copy()
        
        # Add SSH configuration if needed
        ssh_config = self.config.get("ssh", {})
        if tool_name in ["submit_job", "check_job_status", "download_results"]:
            if "remote_host" not in enriched:
                enriched["remote_host"] = ssh_config.get("host")
            if "remote_user" not in enriched:
                enriched["remote_user"] = ssh_config.get("user")
            if "ssh_key_path" not in enriched:
                enriched["ssh_key_path"] = ssh_config.get("key_path")
        
        # Add SLURM defaults for script creation
        if tool_name == "create_slurm_script":
            defaults = self.config.get("slurm_defaults", {})
            for key, value in defaults.items():
                if key not in enriched:
                    enriched[key] = value

            # Always override job_name with the PDB-derived name so every
            # simulation gets a unique, identifiable SLURM job name.
            enriched["job_name"] = self._derive_job_name(state)

            # Add email if available in state
            if "email" not in enriched and state.get("user_email"):
                enriched["email"] = state["user_email"]
        
        # Add state values for submit_job
        if tool_name == "submit_job":
            if "script_path" not in enriched:
                if state.get("job_script"):
                    # Use absolute path for script
                    script_path = Path(state["job_script"]).resolve()
                    enriched["script_path"] = str(script_path)
                else:
                    # Fallback: look for default script in hpc_dir
                    default_script = Path(hpc_dir) / "md_simulation_run.sh"
                    if default_script.exists():
                        enriched["script_path"] = str(default_script.resolve())
            
            remote_dir = self.config.get("paths", {}).get("remote_work_dir", "~/md_jobs")
            if "remote_dir" not in enriched:
                enriched["remote_dir"] = remote_dir
        
        # Add job_id for status check
        if tool_name == "check_job_status":
            if "job_id" not in enriched and state.get("job_id"):
                enriched["job_id"] = state["job_id"]
        
        # Add directories for download
        if tool_name == "download_results":
            if "remote_dir" not in enriched:
                enriched["remote_dir"] = self.config.get("paths", {}).get("remote_work_dir", "~/md_jobs")
            if "local_dir" not in enriched:
                enriched["local_dir"] = self.config.get("paths", {}).get("local_download_dir", f"{hpc_dir}/results")
        
        return enriched
    
    def _update_state_from_result(self, state: MDState, tool_name: str, result: Dict[str, Any]) -> None:
        """Update state based on tool execution results"""
        
        if tool_name == "copy_simulation_files":
            # Update state paths to point to hpc_dir copies so downstream
            # agents (analysis) use the staged files, not the simsetup originals.
            for file_info in result.get("copied_files", []):
                dest = file_info.get("destination")
                if not dest:
                    continue
                fname = Path(dest).name
                if fname.endswith(".top"):
                    state["topology"] = dest
                    logger.info(f"Updated topology path to hpc copy: {dest}")
                    self.file_manager.register_external_file(
                        file_path=dest,
                        file_type="topology",
                        description="Topology staged in HPC directory"
                    )
                elif fname.endswith(".tpr"):
                    self.file_manager.register_external_file(
                        file_path=dest,
                        file_type="topology",
                        description="TPR topology staged in HPC directory"
                    )
                elif fname.endswith(".gro"):
                    self.file_manager.register_external_file(
                        file_path=dest,
                        file_type="coordinates",
                        description="Coordinates staged in HPC directory"
                    )
        
        elif tool_name == "create_slurm_script":
            state["job_script"] = result.get("script_path")
            log_file_operation("hpc", "create", state["job_script"], True, "SLURM submission script")
        
        elif tool_name == "submit_job":
            state["job_id"] = result.get("job_id")
            state["job_status"] = result.get("status", "SUBMITTED")
        
        elif tool_name == "check_job_status":
            state["job_status"] = result.get("status")
        
        elif tool_name == "download_results":
            downloaded = result.get("downloaded_files", [])
            
            for file_info in downloaded:
                filename = file_info.get("filename", "")
                local_path = file_info.get("local_path")
                
                if not local_path:
                    continue
                
                # Register in file_registry using SecureFileManager based on file type
                if filename.endswith(".xtc"):
                    state["trajectory_path"] = local_path
                    log_file_operation("hpc", "download", local_path, True, "Trajectory file")
                    self.file_manager.register_external_file(
                        file_path=local_path,
                        file_type="trajectory",
                        description="MD production trajectory"
                    )
                elif filename.endswith(".gro"):
                    self.file_manager.register_external_file(
                        file_path=local_path,
                        file_type="coordinates",
                        description="Final MD coordinates"
                    )
                elif filename.endswith(".top"):
                    state["topology"] = local_path
                    logger.info(f"Updated topology path from downloaded .top: {local_path}")
                    self.file_manager.register_external_file(
                        file_path=local_path,
                        file_type="topology",
                        description="Downloaded GROMACS topology"
                    )
                elif filename.endswith(".tpr"):
                    self.file_manager.register_external_file(
                        file_path=local_path,
                        file_type="topology",
                        description="Processed topology"
                    )
                elif filename.endswith(".edr"):
                    state["energy_file"] = local_path
                    log_file_operation("hpc", "download", local_path, True, "Energy file")
                    self.file_manager.register_external_file(
                        file_path=local_path,
                        file_type="energy",
                        description="MD energy output"
                    )
                elif filename.endswith(".log"):
                    self.file_manager.register_external_file(
                        file_path=local_path,
                        file_type="log",
                        description="MD simulation log"
                    )
