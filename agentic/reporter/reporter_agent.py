"""
Reporter Agent - Scientific Report Generation

LLM-driven agent that reads analysis summaries, searches literature,
and generates comprehensive HTML reports with scientific context.
"""
import os
import re
import json
import logging
from typing import Dict, Any, Optional, List
from pathlib import Path

from ..state import MDState
from ..llm import LLMClient
from ..utils import (
    log_agent_start, log_llm_interaction, log_agent_action,
    log_agent_completion, log_error, SecureFileManager
)
from .schemas import (
    ReporterPlan, ReporterStep, ReporterResult,
    ReporterAgentInput, ReporterAgentOutput, ReportType
)
from .tools import ReporterToolExecutor, get_tool_metadata

logger = logging.getLogger(__name__)


class ReporterAgent:
    """LLM-driven reporter agent that generates scientific reports"""
    
    def __init__(self, llm_client: LLMClient, config_path: Optional[str] = None):
        if llm_client is None:
            raise ValueError("llm_client is required")
        self.llm = llm_client
        self.config_path = config_path or os.path.join(os.path.dirname(__file__), "config.yaml")
        self.config = self._load_config()
        self.tool_executor = None  # Initialized per execution
        self.file_manager = None  # Initialized per execution
        logger.info("Reporter Agent initialized")
    
    def _load_config(self) -> Dict[str, Any]:
        """Load reporter configuration"""
        import yaml
        if os.path.exists(self.config_path):
            with open(self.config_path, "r") as f:
                return yaml.safe_load(f) or {}
        logger.warning(f"Reporter config {self.config_path} not found; using defaults")
        return self._default_config()
    
    def _default_config(self) -> Dict[str, Any]:
        """Default configuration"""
        return {
            "agent": {
                "working_directory": "working_dir/reporter",
                "input_from": "working_dir/analysis"
            },
            "report": {
                "default_type": "comprehensive"
            },
            "literature": {
                "pubmed": {
                    "enabled": True,
                    "max_results": 10
                }
            }
        }
    
    def reporter_node(self, state: MDState) -> MDState:
        """
        Main reporter node - entry point from workflow.

        In multi-sim combined_analysis phase: generates a cross-simulation
        comparison HTML report from combined analysis results.
        Otherwise: runs the regular per-simulation LLM-guided reporter.
        """
        import sys
        import traceback

        # ── Combined multi-sim report ─────────────────────────────────────
        # Support both initial combined analysis pass and resumed reporter pass.
        if state.get("multi_sim_phase") in {"combined_analysis", "combined_reporter"}:
            return self._run_combined_report(state)

        # ── Regular per-sim report ────────────────────────────────────────
        # Extract input
        execution_plan = state.get("execution_plan") or {}
        has_planner_instructions = execution_plan.get("format") == "natural_language"
        
        input_summary = {
            "analysis_directory": state.get("working_directory", "working_dir") + "/analysis",
            "report_type": state.get("report_type", "comprehensive")
        }
        
        if has_planner_instructions:
            # Get reporter instructions from planner
            reporter_section = state.get("reporter_instructions")
            
            if not reporter_section:
                # Fallback: extract from full plan
                full_plan = execution_plan.get("full_plan", "")
                reporter_section = self._extract_agent_instructions(full_plan, "Reporter Agent")
            
            if reporter_section:
                input_summary["planner_instructions"] = reporter_section
            else:
                input_summary["planner_instructions"] = "[Natural language plan from planner]"
        
        log_agent_start("reporter", "Scientific Report Generation", input_summary)
        
        try:
            # Initialize secure file manager
            base_working_dir = state.get("working_directory", "working_dir")
            file_registry = state.get("file_registry", {})
            
            self.file_manager = SecureFileManager(
                working_dir=base_working_dir,
                agent_name="reporter",
                file_registry=file_registry
            )
            
            logger.info(f"Reporter agent directory: {self.file_manager.agent_dir}")
            
            # Initialize tool executor
            self.tool_executor = ReporterToolExecutor(
                config={"working_directory": self.file_manager.agent_dir}
            )
            
            # Prepare agent input
            agent_input = self._prepare_agent_input(state)
            
            # Run reporter workflow
            agent_output = self._run_reporter_workflow(agent_input, state)
            
            # Update state with results
            self._update_state(state, agent_output)
            
            # Route to reporter checkpoint so the human can inspect results.
            state["next_node"] = "human_reporter_check"
            
            success = agent_output.success and len(agent_output.errors) == 0
            log_agent_completion("reporter", "Scientific Report Generation", state, success)
            
        except Exception as e:
            tb = traceback.format_exc()
            error_msg = f"Reporter agent failed: {type(e).__name__}: {e}"
            logger.error(error_msg)
            logger.error(f"Traceback: {tb}")
            
            log_error("reporter_agent.reporter_node", e, {
                "state": str(state),
                "traceback": tb
            })
            state["errors"].append(f"Reporter error: {str(e)}")
            state["next_node"] = "human_reporter_check"
        
        return state

    # ── Combined multi-sim report ─────────────────────────────────────────

    def _run_combined_report(self, state: MDState) -> MDState:
        """
        Generate a combined comparison HTML report for all simulations.

        Reads overlay plots from state["analysis_results"]["combined"] and
        the per-sim analysis summaries, then writes a self-contained HTML to
        ``{working_directory}/reporter/combined_report.html``.
        """
        from .tools import generate_combined_html_report

        import traceback

        working_dir = state.get("working_directory", "working_dir")
        reporter_dir = str(Path(working_dir) / "reporter")
        Path(reporter_dir).mkdir(parents=True, exist_ok=True)

        # Resolve per-sim dirs and labels
        completed = state.get("completed_sim_states") or []
        sim_dirs = [s["working_directory"] for s in completed if s.get("working_directory")]
        labels = [s.get("label", f"sim_{i}") for i, s in enumerate(completed)]

        # Overlay plots produced by combined analysis
        combined_info = (state.get("analysis_results") or {}).get("combined", {})
        overlay_plots = combined_info.get("overlay_plots", [])

        log_agent_start(
            "reporter",
            "Combined Multi-Simulation Report",
            {
                "sim_dirs": sim_dirs,
                "labels": labels,
                "overlay_plots": overlay_plots,
                "output_dir": reporter_dir,
            },
        )

        # Resolve protein name and build label → name map from user_goal
        # ---------------------------------------------------------------
        # Parse any "uniprotId: ProteinName" table the user may have provided.
        import re as _re2
        _user_goal_text = state.get("user_goal", "") or ""
        _enriched_text = state.get("enriched_prompt", "") or ""
        _combined_text = f"{_user_goal_text} {_enriched_text}"
        # Build raw label_name_map (will be used by combined_reporter internally)
        _label_name_map: Dict[str, str] = {}
        for _m in _re2.finditer(r'\b([A-Za-z0-9_\-]+)\s*:\s*([A-Za-z][A-Za-z0-9_\-]+)', _combined_text):
            _k, _v = _m.group(1).strip().lower(), _m.group(2).strip()
            if _v[0].isalpha() and len(_k) >= 3 and len(_v) >= 2:
                _label_name_map[_k] = _v

        # Apply name mapping: replace any UniProt-ID labels with human-readable
        # protein names so all downstream use (plots, report sections) shows names.
        if _label_name_map:
            labels = [_label_name_map.get(lbl.lower(), lbl) for lbl in labels]

        # Derive a human-readable protein name for the report title.
        # For multi-sim: try to map all labels; for single: the usual logic.
        protein_name: Optional[str] = None
        sys_info = state.get("system_info") or {}
        if isinstance(sys_info, dict):
            protein_name = (
                sys_info.get("protein_name")
                or sys_info.get("system_name")
            )
        if not protein_name and labels:
            # Use mapped names where available
            mapped = [_label_name_map.get(lbl.lower(), lbl) for lbl in labels[:3]]
            protein_name = ", ".join(mapped) if mapped else labels[0]

        # Dynamic title: use mapped protein names
        report_title = (
            f"Multi-Simulation Comparison Report — {protein_name}"
            if protein_name
            else "Multi-Simulation Comparison Report"
        )

        try:
            # Prefer master_enriched_prompt (supervisor's unified rephrased goal)
            # over enriched_prompt, which by the combined-analysis phase has been
            # overwritten with the planner's combined_analysis_plan text.
            _report_enriched = (
                state.get("master_enriched_prompt")
                or state.get("enriched_prompt")
            )
            result = generate_combined_html_report.func(
                sim_dirs=sim_dirs,
                labels=labels,
                overlay_plots=overlay_plots,
                working_dir=reporter_dir,
                output_file="combined_report.html",
                title=report_title,
                enriched_prompt=_report_enriched,
                user_goal=state.get("user_goal_original") or _user_goal_text,
                protein_name=protein_name,
            )

            if result.get("success"):
                report_path = result["output_path"]
                state["reporter_output"] = report_path
                log_agent_action(
                    agent_name="reporter",
                    action="Combined Report Generated",
                    details={"report_path": report_path},
                )
                log_agent_completion("reporter", "Combined Multi-Simulation Report", state, True)
            else:
                state["errors"].append(f"Combined report failed: {result.get('error', 'unknown')}")
                log_agent_completion("reporter", "Combined Multi-Simulation Report", state, False)

        except Exception as exc:
            logger.error(f"Combined report failed: {exc}\n{traceback.format_exc()}")
            state["errors"].append(f"Combined reporter error: {exc}")

        # Route to reporter checkpoint (not supervisor) so human can inspect
        state["next_node"] = "human_reporter_check"
        return state
    
    def _extract_agent_instructions(self, full_plan: str, agent_name: str) -> Optional[str]:
        """Extract agent-specific instructions from plan"""
        if not full_plan:
            return None
        
        # Look for reporter agent section
        patterns = [
            rf"{agent_name}[:\s]+(.+?)(?=\n\n|\n###|\Z)",
            r"Reporter[:\s]+(.+?)(?=\n\n|\n###|\Z)",
            r"Report Generation[:\s]+(.+?)(?=\n\n|\n###|\Z)",
        ]
        
        for pattern in patterns:
            match = re.search(pattern, full_plan, re.IGNORECASE | re.DOTALL)
            if match:
                return match.group(1).strip()
        
        return None
    
    def _prepare_agent_input(self, state: MDState) -> ReporterAgentInput:
        """Prepare reporter agent input from state"""
        
        working_dir = state.get("working_directory", "working_dir")
        analysis_dir = f"{working_dir}/analysis"
        summary_file = f"{analysis_dir}/analysis_summary.jsonl"
        
        # Get planner instructions
        execution_plan = state.get("execution_plan") or {}
        reporter_instructions = state.get("reporter_instructions")
        
        if not reporter_instructions:
            full_plan = execution_plan.get("full_plan", "")
            reporter_instructions = self._extract_agent_instructions(full_plan, "Reporter")
        
        # Determine report type
        report_type_str = state.get("report_type", "comprehensive")
        try:
            report_type = ReportType(report_type_str.lower())
        except ValueError:
            report_type = ReportType.COMPREHENSIVE
        
        return ReporterAgentInput(
            working_directory=working_dir,
            analysis_summary_file=summary_file,
            user_goal=state.get("enriched_prompt") or state.get("user_goal"),
            report_type=report_type,
            planner_instructions=reporter_instructions,
            literature_search=state.get("include_literature", True),
            literature_keywords=state.get("literature_keywords"),
            include_visualizations=state.get("include_visualizations", True),
            context={
                "force_field": state.get("force_field", "amber99sb-ildn"),
                "md_engine": state.get("md_engine", "gromacs"),
                "execution_plan": execution_plan
            }
        )
    
    def _run_reporter_workflow(
        self,
        agent_input: ReporterAgentInput,
        state: MDState
    ) -> ReporterAgentOutput:
        """
        Execute reporter workflow: plan → generate → validate
        """
        import sys
        import traceback
        
        try:
            # Step 1: Create execution plan using LLM
            logger.info("="*60)
            logger.info("REPORTER WORKFLOW START")
            logger.info("  User goal: %s", (agent_input.user_goal or 'N/A')[:120])
            logger.info("  Report type: %s", agent_input.report_type.value)
            logger.info("  Analysis file: %s", agent_input.analysis_summary_file)
            logger.info("="*60)

            plan = None
            if self.llm.available:
                logger.info("[1/4] Creating execution plan via LLM...")
                plan = self._create_llm_plan(agent_input, state)
            
            if not plan or not plan.steps:
                logger.info("[1/4] LLM plan empty or unavailable — using fallback plan")
                plan = self._create_fallback_plan(agent_input)
            
            logger.info("[1/4] Plan created: %d steps, focus=%s",
                        len(plan.steps),
                        plan.report_focus[:3] if plan.report_focus else [])
            log_agent_action(
                agent_name="reporter",
                action="Generated reporter plan",
                details={
                    "steps": len(plan.steps),
                    "report_focus": plan.report_focus[:3] if plan.report_focus else [],
                    "literature_queries": len(plan.literature_queries)
                }
            )
            
            # Save the execution plan to file
            self._save_execution_plan(plan, agent_input)
            
            # Step 2: Execute the plan
            logger.info("[2/4] Executing reporter plan...")
            result = self._execute_reporter_plan(agent_input, plan, state)
            
            # Step 3: Create final output
            logger.info("[3/4] Building final output (report=%s)",
                        result.report_file or 'None')
            output = ReporterAgentOutput(
                success=result.success and len(result.issues) == 0,
                result=result,
                errors=result.issues,
                next_actions=["Report available for review"],
                report_path=result.report_file,
                pdf_path=result.generated_files.get("pdf")
            )
            
            return output
            
        except Exception as e:
            tb_str = traceback.format_exc()
            logger.error(f"Reporter workflow failed: {type(e).__name__}: {e}")
            logger.error(f"Traceback: {tb_str}")
            
            return ReporterAgentOutput(
                success=False,
                result=ReporterResult(
                    success=False,
                    completed_steps=0,
                    total_steps=0,
                    report="Reporter workflow failed: " + str(e)
                ),
                errors=[str(e)]
            )
    
    def _create_llm_plan(
        self,
        agent_input: ReporterAgentInput,
        state: MDState
    ) -> Optional[ReporterPlan]:
        """Create execution plan using LLM"""
        
        # Get available tools
        tool_metadata = get_tool_metadata()
        tools_list = []
        for tool_name, tool_info in tool_metadata.items():
            tools_list.append(f"→ {tool_name}: {tool_info['description']}")
        tools_str = "\n".join(tools_list)
        
        prompt = self._build_planning_prompt(agent_input, tools_str)
        
        try:
            response = self.llm.prompt(prompt)
            
            log_llm_interaction(
                agent_name="reporter.planning",
                prompt=prompt,
                response=response,
                is_mock=not self.llm.available
            )
            
            # Parse JSON response
            plan_dict = self._extract_plan_json(response)
            
            if plan_dict is None:
                logger.warning("Failed to parse LLM response into plan JSON")
                return None
            
            # Build ReporterPlan from response
            return ReporterPlan(
                reasoning=plan_dict.get("reasoning", "LLM-generated plan"),
                overview=plan_dict.get("overview", "Report generation"),
                steps=[
                    ReporterStep(
                        name=step.get("name", "unknown"),
                        description=step.get("description", ""),
                        tool_name=step.get("tool_name", ""),
                        tool_params=step.get("tool_params", {}),
                        reason=step.get("reason", "")
                    )
                    for step in plan_dict.get("steps", [])
                ],
                report_focus=plan_dict.get("report_focus", []),
                literature_queries=plan_dict.get("literature_queries", []),
                estimated_complexity=plan_dict.get("estimated_complexity", "medium")
            )
            
        except Exception as e:
            logger.warning(f"LLM planning failed: {e}, using fallback")
            return None
    
    def _build_planning_prompt(
        self,
        agent_input: ReporterAgentInput,
        tools_str: str
    ) -> str:
        """Build LLM planning prompt"""
        
        prompt_template = """You are a scientific report generator creating reports from MD trajectory analysis.

**User Goal:**
{user_goal}

**Planner Instructions:**
{planner_instructions}

**Analysis Summary File:**
{summary_file}

**Report Type:**
{report_type}

**Literature Search:**
Enabled: {literature_enabled}
{keywords_section}

**Available Tools:**
{tools_str}

**Your Task:**
Create a plan to generate a scientific report by:
1. Reading the analysis_summary.jsonl file (contains analysis results, statistics, and image file paths)
2. Extracting key findings and statistics
3. Optionally searching scientific literature for context
4. Generating an HTML report with embedded visualizations and insights

**HTML REPORT FEATURES:**
The HTML report automatically includes:
- **Embedded Images**: Analysis plots (RMSD, RMSF, DSSP heatmaps, etc.) are embedded as base64
- **Key Statistics Cards**: Important values (mean, std, min, max) displayed prominently beneath images
- **Modern Layout**: Clean, professional styling with gradients and visual hierarchy
- **Organized Sections**: Each analysis type in its own section with dividers

The tool reads image file paths from analysis_summary.jsonl and embeds them automatically.
No need to specify image paths in tool_params - they're extracted from the analysis data.

**IMPORTANT PATH GUIDELINES:**
- The analysis_summary.jsonl file is typically in the "analysis/" subdirectory
- For read_analysis_summary: Use "analysis/analysis_summary.jsonl" or just "analysis_summary.jsonl" (tool will search)
- For generate_html_report: Use simple filename like "report.html" or "kinase_report.html" or "md_analysis_report.html"
- Do NOT include "working_dir" in tool_params - it will be automatically set to the reporter's output directory
- All files will be created in the reporter's dedicated directory (working_dir/reporter/)

**Output Format (JSON):**
{{
  "reasoning": "Why this approach",
  "overview": "High-level summary",
  "steps": [
    {{
      "name": "Read Analysis Summary",
      "description": "Parse analysis_summary.jsonl",
      "tool_name": "read_analysis_summary",
      "tool_params": {{
        "summary_file": "analysis_summary.jsonl"
      }},
      "reason": "Need to load analysis results"
    }},
    {{
      "name": "Generate HTML Report",
      "description": "Create comprehensive report",
      "tool_name": "generate_html_report",
      "tool_params": {{
        "analysis_data": {{}},
        "output_file": "report.html",
        "report_type": "comprehensive"
      }},
      "reason": "Produce final deliverable"
    }}
  ],
  "report_focus": ["Key topic 1", "Key topic 2"],
  "literature_queries": ["query 1", "query 2"],
  "estimated_complexity": "low|medium|high"
}}
"""
        
        keywords_section = ""
        if agent_input.literature_keywords:
            keywords_section = f"Keywords: {', '.join(agent_input.literature_keywords)}"
        else:
            keywords_section = "Auto-generate based on analysis types"
        
        return prompt_template.format(
            user_goal=agent_input.user_goal or "Generate scientific report",
            planner_instructions=agent_input.planner_instructions or "Create comprehensive report",
            summary_file=agent_input.analysis_summary_file,
            report_type=agent_input.report_type.value,
            literature_enabled="Yes" if agent_input.literature_search else "No",
            keywords_section=keywords_section,
            tools_str=tools_str
        )
    
    def _ensure_literature_search(
        self,
        analysis_data: Dict[str, Any],
        state: MDState
    ) -> List[Dict[str, Any]]:
        """Guaranteed literature search across PubMed, bioRxiv,
        and UniProt. Returns up to 15 deduplicated references."""
        literature_refs: List[Dict[str, Any]] = []
        MAX_REFS = 15
        try:
            from src.reporter.literature_search import (
                generate_literature_queries, search_pubmed,
                search_biorxiv, search_uniprot,
            )

            # --- Resolve analysis types ---
            analysis_types: list = []
            if isinstance(analysis_data, dict):
                at = analysis_data.get("analysis_types", {})
                if isinstance(at, dict):
                    analysis_types = list(at.keys())
                elif isinstance(at, list):
                    analysis_types = at
            if not analysis_types:
                analysis_types = ["RMSD", "RMSF"]

            user_goal = state.get("enriched_prompt") or state.get("user_goal", "MD simulation analysis")

            # ── Protein name extraction (best-effort, multiple sources) ──
            protein_name = None
            sys_info = state.get("system_info")
            if isinstance(sys_info, dict):
                protein_name = (
                    sys_info.get("system_name")
                    or sys_info.get("protein_name")
                    or sys_info.get("uniprot_id")
                )
            # Try PDB file stem if system_info didn't give a clean name
            if not protein_name or len(protein_name) < 3:
                for pdb_key in ("raw_pdb", "cleaned_pdb", "pdb_path"):
                    pdb_val = state.get(pdb_key)
                    if pdb_val and isinstance(pdb_val, str):
                        import os
                        stem = os.path.splitext(os.path.basename(pdb_val))[0]
                        if len(stem) >= 3:
                            protein_name = stem
                            break
            # Scan the user goal for the first capitalised word as protein name
            if not protein_name and user_goal:
                import re as _re
                match = _re.search(r'\b([A-Z]{2,}[0-9]*[A-Z]*|[A-Z][a-z]*[0-9]+)\b', user_goal)
                if match:
                    protein_name = match.group(1)

            # ── Collect analysis stats to drive result-specific queries ──
            analysis_stats: Dict[str, Any] = {}
            if isinstance(analysis_data, dict):
                results = analysis_data.get("results") or analysis_data.get("analysis_results") or {}
                if isinstance(results, dict):
                    for atype, aval in results.items():
                        if isinstance(aval, dict):
                            # Grab any numeric mean/max values present
                            astat = {}
                            for k, v in aval.items():
                                if any(x in k.lower() for x in ("mean", "max", "min", "avg")):
                                    try:
                                        astat[k] = float(v)
                                    except (TypeError, ValueError):
                                        pass
                            if astat:
                                analysis_stats[atype] = astat

            # --- Generate prioritised queries ---
            query_result = generate_literature_queries.invoke({
                "analysis_types": analysis_types,
                "user_goal": user_goal,
                "protein_name": protein_name or "",
                "analysis_stats": analysis_stats or None,
            })
            queries = {}
            resolved_name = ""
            if isinstance(query_result, dict) and query_result.get("success"):
                queries = query_result.get("queries", {})
                resolved_name = query_result.get("protein_name", "") or ""

            # Deduplication set (PMIDs + DOIs)
            seen_ids: set = set()

            def _add_ref(ref: Dict[str, Any]) -> bool:
                """Add ref if not duplicate. Returns True if added."""
                pmid = ref.get("pmid")
                doi = (ref.get("doi") or "").lower().strip()
                if pmid and pmid in seen_ids:
                    return False
                if doi and doi in seen_ids:
                    return False
                if pmid:
                    seen_ids.add(pmid)
                if doi:
                    seen_ids.add(doi)
                literature_refs.append(ref)
                return True

            # ── 1. PubMed (protein-priority queries) ──────────────
            for qkey, query_text in queries.items():
                if len(literature_refs) >= 10:
                    break
                if not query_text or qkey == "_fallback_general":
                    continue
                remaining = 10 - len(literature_refs)
                result = search_pubmed.invoke({
                    "query": query_text,
                    "max_results": min(5, remaining),
                    "include_abstracts": True,
                    "max_age_years": 10,
                })
                if isinstance(result, dict) and result.get("success"):
                    for ref in result.get("results", []):
                        if not _add_ref(ref):
                            continue
                        if len(literature_refs) >= 10:
                            break
            logger.info("After PubMed: %d refs", len(literature_refs))

            # ── 2. bioRxiv preprints (top protein query) ──────────
            if resolved_name and len(literature_refs) < MAX_REFS:
                bio_query = queries.get("protein_dynamics") or queries.get("protein_function") or f"{resolved_name} molecular dynamics"
                try:
                    bio_result = search_biorxiv.invoke({
                        "query": bio_query,
                        "max_results": min(5, MAX_REFS - len(literature_refs)),
                        "max_age_years": 5,
                    })
                    if isinstance(bio_result, dict) and bio_result.get("success"):
                        for ref in bio_result.get("results", []):
                            if not _add_ref(ref):
                                continue
                            if len(literature_refs) >= MAX_REFS:
                                break
                    logger.info("After bioRxiv: %d refs", len(literature_refs))
                except Exception as e:
                    logger.warning("bioRxiv search failed (non-fatal): %s", e)

            # ── 3. UniProt protein context ────────────────────────
            if resolved_name and len(literature_refs) < MAX_REFS:
                try:
                    uni_result = search_uniprot.invoke({
                        "query": resolved_name,
                        "max_results": 3,
                    })
                    if isinstance(uni_result, dict) and uni_result.get("success"):
                        for entry in uni_result.get("entries", []):
                            # Add a synthetic reference for the UniProt entry itself
                            func_text = entry.get("function") or ""
                            _add_ref({
                                "title": f"{entry.get('protein_name', resolved_name)} — UniProt functional annotation ({entry.get('organism', '')})",
                                "authors": ["UniProt Consortium"],
                                "journal": "UniProt Knowledgebase",
                                "year": 2025,
                                "pmid": None,
                                "doi": None,
                                "abstract": func_text[:400] if func_text else None,
                                "url": entry.get("url"),
                                "source": "UniProt",
                            })
                            # Also pull in key literature refs from the entry
                            for kref in entry.get("key_references", []):
                                if len(literature_refs) >= MAX_REFS:
                                    break
                                if kref.get("title"):
                                    _add_ref({
                                        "title": kref["title"],
                                        "authors": [],
                                        "journal": kref.get("journal", ""),
                                        "year": kref.get("year"),
                                        "pmid": kref.get("pmid"),
                                        "doi": kref.get("doi"),
                                        "abstract": None,
                                        "url": f"https://pubmed.ncbi.nlm.nih.gov/{kref['pmid']}/" if kref.get("pmid") else None,
                                        "source": "UniProt",
                                    })
                            if len(literature_refs) >= MAX_REFS:
                                break
                    logger.info("After UniProt: %d refs", len(literature_refs))
                except Exception as e:
                    logger.warning("UniProt search failed (non-fatal): %s", e)

            # ── Fallback if still empty ───────────────────────────
            if not literature_refs:
                logger.info("No results from any source; trying PubMed fallback")
                fallback_q = queries.get("_fallback_general", "molecular dynamics protein stability review")
                result = search_pubmed.invoke({
                    "query": fallback_q,
                    "max_results": 5,
                    "include_abstracts": True,
                    "max_age_years": 10,
                })
                if isinstance(result, dict) and result.get("success"):
                    for ref in result.get("results", []):
                        _add_ref(ref)

            logger.info("Literature search complete: %d references from PubMed + bioRxiv + UniProt", len(literature_refs))

        except Exception as e:
            logger.warning(f"Literature search failed: {e}", exc_info=True)

        return literature_refs[:MAX_REFS]
    
    def _extract_pdb_for_viewer(self, state: MDState, analysis_data: Dict[str, Any] = None) -> Optional[Dict[str, str]]:
        """Extract trajectory frames at analysis-driven time points for the 3D viewer.

        Reads RMSD / COM-distance data to pick up to 5 scientifically
        important timepoints (max RMSD, closest ligand approach, etc.)
        and returns a dict mapping descriptive labels → PDB text.

        Falls back to a single first frame if smart selection fails.
        """
        try:
            from src.reporter.structure_extractor import (
                identify_important_timepoints,
                extract_multi_frame_pdb,
                extract_first_frame_pdb,
                read_pdb_data,
            )

            working_dir = state.get("working_directory", "working_dir")

            # Resolve the HPC directory from state if available so that
            # extract_multi_frame_pdb looks in the right place for the
            # trajectory (md.xtc) regardless of session-specific nesting.
            from pathlib import Path as _Path
            hpc_raw = state.get("hpc_output_directory") or state.get("hpc_dir")
            if hpc_raw and _Path(hpc_raw).is_dir():
                _hpc_p = _Path(hpc_raw)
                hpc_parent = str(_hpc_p.parent)
                hpc_subdir_name = _hpc_p.name
            else:
                hpc_parent = working_dir
                hpc_subdir_name = "hpc"

            # --- Smart timepoint selection from analysis data ---
            if analysis_data:
                important = identify_important_timepoints(
                    analysis_data, working_dir, max_points=5
                )
                if important:
                    time_points = [t for t, _lbl in important]
                    labels_map = {t: lbl for t, lbl in important}
                    logger.info(
                        "Reporter: extracting PDB frames at %d analysis-driven timepoints: %s",
                        len(important),
                        ", ".join(f"{t} ns ({lbl})" for t, lbl in important),
                    )
                    log_agent_action(
                        "reporter",
                        f"Identified {len(important)} important timepoints from analysis data",
                        {"timepoints": [f"{t} ns ({lbl})" for t, lbl in important]},
                    )
                    frames = extract_multi_frame_pdb(
                        hpc_parent,
                        hpc_subdir=hpc_subdir_name,
                        time_points_ns=time_points,
                        labels=labels_map,
                    )
                    if frames:
                        logger.info(
                            "Reporter: extracted %d PDB frames for 3D viewer (%s)",
                            len(frames),
                            ", ".join(frames.keys()),
                        )
                        log_agent_action(
                            "reporter",
                            f"Extracted {len(frames)} multi-timepoint PDB frames for 3D viewer",
                            {"labels": list(frames.keys())},
                        )
                        return frames
                    logger.warning("Smart PDB extraction returned empty; falling back")

            # --- Fallback: first frame only ---
            pdb_path = extract_first_frame_pdb(hpc_parent, hpc_subdir=hpc_subdir_name)
            if pdb_path:
                pdb_text = read_pdb_data(pdb_path)
                if pdb_text:
                    logger.info("Extracted single first-frame PDB for 3D viewer (%d chars)", len(pdb_text))
                    log_agent_action("reporter", "Extracted first-frame PDB for 3D viewer (fallback)", {})
                    return {"0 ns — Start": pdb_text}

            logger.warning("Could not extract any PDB for 3D viewer")
        except Exception as e:
            logger.warning("PDB extraction for 3D viewer failed: %s", e, exc_info=True)
        return None

    def _generate_final_impression(
        self,
        analysis_data: Dict[str, Any],
        literature_refs: List[Dict[str, Any]],
        state: MDState
    ) -> Optional[str]:
        """Generate LLM-based final impression correlating analysis results with literature."""
        
        entries = analysis_data.get("entries", []) if isinstance(analysis_data, dict) else []
        if not entries:
            logger.info("No analysis entries; skipping final impression")
            return None

        if not self.llm.available:
            logger.info("LLM unavailable; generating rule-based final impression")
            lines = [
                "This molecular dynamics simulation was analysed with the following results:"
            ]
            for entry in entries:
                atype = entry.get("analysis_type", "Unknown")
                stats = entry.get("statistics", {})
                if isinstance(stats, dict) and stats:
                    stat_parts = [
                        f"{k}: {v}"
                        for k, v in stats.items()
                        if isinstance(v, (int, float, str)) and str(v).strip()
                    ]
                    lines.append(
                        f"**{atype}**: " + ("; ".join(stat_parts) if stat_parts else "completed")
                    )
                else:
                    lines.append(f"**{atype}**: Analysis completed")
            return "\n\n".join(lines)
        
        analysis_summary_parts = []
        for entry in entries:
            atype = entry.get("analysis_type", "Unknown")
            stats = entry.get("statistics", {})
            if isinstance(stats, dict) and stats:
                stat_lines = ", ".join(f"{k}: {v}" for k, v in stats.items() if isinstance(v, (int, float)))
                analysis_summary_parts.append(f"- {atype}: {stat_lines}")
            else:
                analysis_summary_parts.append(f"- {atype}: (no statistics)")
        analysis_text = "\n".join(analysis_summary_parts)
        
        # Build literature summary for LLM
        lit_text = "No literature references available."
        if literature_refs:
            lit_parts = []
            for i, ref in enumerate(literature_refs[:10], 1):
                title = ref.get("title", "Unknown")
                abstract = ref.get("abstract", "")
                abstract_snippet = abstract[:300] if abstract else "No abstract"
                lit_parts.append(f"[{i}] {title}\n    {abstract_snippet}")
            lit_text = "\n".join(lit_parts)
        
        user_goal = state.get("enriched_prompt") or state.get("user_goal", "MD simulation analysis")
        
        prompt = f"""You are a computational biophysics expert. Based on the analysis results and literature below, write a concise Final Impression section for a scientific MD simulation report.

**User Goal:** {user_goal}

**Analysis Results:**
{analysis_text}

**Literature References:**
{lit_text}

**Instructions:**
- Correlate the analysis results with findings from the literature
- Highlight key observations: Is the protein stable? Are there notable flexible regions?
- Put the results in context of what is known from published work
- Provide actionable insights or conclusions relevant to the user's question
- Keep it concise: 2-4 paragraphs, no bullet points
- Write in scientific prose, suitable for a report
- Cite relevant literature using bracket notation like [1], [2], [3] corresponding to the reference numbers above
- Do NOT include section headers or titles — just the text content"""

        try:
            response = self.llm.prompt(prompt)
            
            log_llm_interaction(
                agent_name="reporter.final_impression",
                prompt=prompt[:500] + "...",
                response=response[:500] + "..." if len(response) > 500 else response,
                is_mock=not self.llm.available
            )
            
            # Clean up response: remove markdown headers if LLM adds them
            cleaned = response.strip()
            cleaned = re.sub(r'^#{1,3}\s+.*\n?', '', cleaned, flags=re.MULTILINE).strip()
            
            if len(cleaned) < 50:
                logger.warning("Final impression too short, skipping")
                return None
            
            logger.info(f"Generated final impression ({len(cleaned)} chars)")
            return cleaned
            
        except Exception as e:
            logger.warning(f"Failed to generate final impression: {e}")
            return None
    
    def _extract_plan_json(self, content: str) -> Optional[Dict[str, Any]]:
        """Extract and parse JSON plan from LLM response.
        
        Returns parsed dict with 'steps' key, or None if parsing fails.
        """
        
        def _clean_json_text(text: str) -> str:
            """Strip JS-style comments and trailing commas that LLMs sometimes add."""
            # Remove single-line // comments (but not inside strings)
            cleaned = re.sub(r'(?<=[,\}\]\s])\s*//[^\n]*', '', text)
            # Remove trailing commas before } or ]
            cleaned = re.sub(r',(\s*[}\]])', r'\1', cleaned)
            return cleaned
        
        def _try_parse(text: str) -> Optional[Dict[str, Any]]:
            """Try to parse JSON, with and without comment stripping."""
            for candidate in [text, _clean_json_text(text)]:
                try:
                    result = json.loads(candidate)
                    if isinstance(result, dict) and "steps" in result:
                        return result
                except json.JSONDecodeError:
                    continue
            return None
        
        # Strategy 1: Strip outer markdown fences and parse directly
        content_cleaned = re.sub(r'^\s*```(?:json)?\s*\n', '', content)
        content_cleaned = re.sub(r'\n\s*```\s*$', '', content_cleaned)
        content_cleaned = content_cleaned.strip()
        
        result = _try_parse(content_cleaned)
        if result:
            return result
        
        # Strategy 2: The LLM sometimes wraps valid JSON inside a markdown
        # code block WITHIN the response text. Extract the ```json...``` block.
        fenced_match = re.search(r'```(?:json)?\s*\n(\{[\s\S]*?\})\s*\n```', content)
        if fenced_match:
            result = _try_parse(fenced_match.group(1))
            if result:
                return result
        
        # Strategy 3: Find the outermost JSON object via regex
        json_match = re.search(r'\{[\s\S]*\}', content_cleaned, re.DOTALL)
        if json_match:
            result = _try_parse(json_match.group())
            if result:
                return result
        
        # Strategy 4: Balanced-brace extraction around "steps" key
        inner_match = re.search(r'\{[^{}]*"steps"\s*:\s*\[', content)
        if inner_match:
            start = inner_match.start()
            depth = 0
            for i in range(start, len(content)):
                if content[i] == '{':
                    depth += 1
                elif content[i] == '}':
                    depth -= 1
                    if depth == 0:
                        result = _try_parse(content[start:i+1])
                        if result:
                            return result
                        break
        
        logger.error("Could not extract valid JSON plan from LLM response")
        logger.debug(f"Response content: {content[:500]}...")
        return None
    
    def _create_fallback_plan(self, agent_input: ReporterAgentInput) -> ReporterPlan:
        """Create fallback plan when LLM is unavailable"""
        
        steps = []
        
        # Step 1: Read analysis summary
        steps.append(ReporterStep(
            name="Read Analysis Summary",
            description="Parse analysis_summary.jsonl file",
            tool_name="read_analysis_summary",
            tool_params={
                "summary_file": agent_input.analysis_summary_file
            },
            reason="Load analysis results"
        ))
        
        # Step 2: Generate literature queries (if enabled)
        if agent_input.literature_search:
            steps.append(ReporterStep(
                name="Generate Literature Queries",
                description="Create PubMed search queries",
                tool_name="generate_literature_queries",
                tool_params={
                    "analysis_types": ["RMSD", "RMSF"],  # Will be updated based on actual analyses
                    "user_goal": agent_input.user_goal
                },
                reason="Prepare for literature search"
            ))
        
        # Step 3: Generate HTML report
        steps.append(ReporterStep(
            name="Generate HTML Report",
            description="Create HTML report from analysis data",
            tool_name="generate_html_report",
            tool_params={
                "analysis_data": {},  # Populated during execution
                "report_type": agent_input.report_type.value,
                "output_file": "analysis_report.html"
            },
            reason="Generate final report"
        ))
        
        return ReporterPlan(
            reasoning="Fallback plan: Basic report generation without LLM planning",
            overview="Read analysis, optionally search literature, generate HTML report",
            steps=steps,
            report_focus=["Analysis results", "Key statistics"],
            literature_queries=[],
            estimated_complexity="medium"
        )
    
    def _save_execution_plan(self, plan: ReporterPlan, agent_input: ReporterAgentInput) -> None:
        """Save execution plan with LLM reasoning to file"""
        try:
            plan_file = os.path.join(self.file_manager.agent_dir, "execution_plan.json")
            
            plan_data = {
                "timestamp": str(Path(plan_file).stat().st_mtime if os.path.exists(plan_file) else "N/A"),
                "reasoning": plan.reasoning,
                "overview": plan.overview,
                "report_focus": plan.report_focus,
                "literature_queries": plan.literature_queries,
                "estimated_complexity": plan.estimated_complexity,
                "steps": [
                    {
                        "name": step.name,
                        "description": step.description,
                        "tool_name": step.tool_name,
                        "tool_params": step.tool_params,
                        "reason": step.reason
                    }
                    for step in plan.steps
                ]
            }
            
            with open(plan_file, "w") as f:
                json.dump(plan_data, f, indent=2)
            
            logger.info(f"Saved execution plan to {plan_file}")
            
            # Also save a markdown version for readability
            md_file = os.path.join(self.file_manager.agent_dir, "execution_plan.md")
            with open(md_file, "w") as f:
                f.write("# Reporter Execution Plan\n\n")
                f.write(f"**Generated:** {plan_data['timestamp']}\n\n")
                f.write(f"## LLM Reasoning\n\n{plan.reasoning}\n\n")
                f.write(f"## Overview\n\n{plan.overview}\n\n")
                f.write(f"## Report Focus\n\n")
                for focus in plan.report_focus:
                    f.write(f"- {focus}\n")
                f.write(f"\n## Execution Steps ({len(plan.steps)} steps)\n\n")
                for i, step in enumerate(plan.steps, 1):
                    f.write(f"### Step {i}: {step.name}\n\n")
                    f.write(f"**Tool:** `{step.tool_name}`\n\n")
                    f.write(f"**Description:** {step.description}\n\n")
                    f.write(f"**Reason:** {step.reason}\n\n")
                    f.write(f"**Parameters:**\n```json\n{json.dumps(step.tool_params, indent=2)}\n```\n\n")
            
            logger.info(f"Saved execution plan (markdown) to {md_file}")
            
        except Exception as e:
            logger.warning(f"Failed to save execution plan: {e}")
    
    def _execute_reporter_plan(
        self,
        agent_input: ReporterAgentInput,
        plan: ReporterPlan,
        state: MDState
    ) -> ReporterResult:
        """Execute reporter plan step by step"""
        
        completed = 0
        issues = []
        warnings = []
        step_results = []
        
        # Shared data between steps
        analysis_data = {}
        literature_refs = []
        
        # --- Hardcoded: read analysis summary first so we know the types ---
        logger.info("  [exec] Reading analysis_summary.jsonl...")
        try:
            base_dir = str(Path(self.file_manager.agent_dir).parent)
            summary_result = self.tool_executor.execute_tool(
                "read_analysis_summary",
                {"summary_file": "analysis_summary.jsonl", "working_dir": base_dir}
            )
            if isinstance(summary_result, dict) and summary_result.get("entries"):
                analysis_data = summary_result
                logger.info("  [exec] Pre-loaded analysis summary (%d entries, types: %s)",
                            len(analysis_data.get("entries", [])),
                            ", ".join(analysis_data.get("analysis_types", {}).keys()
                                      if isinstance(analysis_data.get("analysis_types"), dict)
                                      else analysis_data.get("analysis_types", [])))
        except Exception as e:
            logger.warning("Pre-load of analysis summary failed: %s", e)

        # --- Hardcoded: always run literature search before report generation ---
        logger.info("  [exec] Running literature search (PubMed + bioRxiv + UniProt)...")
        literature_refs = self._ensure_literature_search(analysis_data, state)
        logger.info("  [exec] Literature search done: %d references collected", len(literature_refs))
        log_agent_action("reporter", f"Literature search completed: {len(literature_refs)} references found", {})
        
        total_steps = len(plan.steps)
        for i, step in enumerate(plan.steps):
            try:
                # Skip plan-based literature steps — _ensure_literature_search
                # already ran with protein-aware queries before the loop.
                if step.tool_name in ("search_pubmed", "generate_literature_queries", "search_biorxiv"):
                    logger.info("Skipping plan step '%s' (%s) — literature already collected",
                                step.name, step.tool_name)
                    log_agent_action("reporter", f"Step {i+1}/{total_steps} skipped (pre-handled)", {
                        "step": step.name,
                        "tool": step.tool_name,
                        "reason": f"Literature already collected by _ensure_literature_search ({len(literature_refs)} refs)",
                        "status": "⏭️ SKIPPED"
                    })
                    step_results.append({
                        "step_name": step.name,
                        "tool": step.tool_name,
                        "success": True,
                        "result": {"skipped": True, "reason": "literature handled by _ensure_literature_search"}
                    })
                    completed += 1
                    continue

                # Skip steps with no tool (virtual/narrative steps the LLM invented)
                if not step.tool_name:
                    logger.info("Skipping virtual plan step '%s' (no tool)", step.name)
                    log_agent_action("reporter", f"Step {i+1}/{total_steps} skipped (virtual step)", {
                        "step": step.name,
                        "reason": "No tool — handled internally (e.g. final impression generated during HTML report step)",
                        "status": "⏭️ SKIPPED"
                    })
                    step_results.append({
                        "step_name": step.name,
                        "tool": "",
                        "success": True,
                        "result": {"skipped": True, "reason": "no tool associated"}
                    })
                    completed += 1
                    continue

                log_agent_action("reporter", f"Executing step {i+1}/{total_steps}", {
                    "step": step.name,
                    "tool": step.tool_name
                })
                
                # Special handling for steps that need previous results
                params = step.tool_params.copy()
                
                # Override working_dir based on tool type:
                # - Output tools (generate_html_report): Use reporter's agent directory
                # - Input tools (read_analysis_summary): Use base working directory to find analysis files
                if step.tool_name == "generate_html_report":
                    # Output tool - use reporter directory  
                    params["working_dir"] = self.file_manager.agent_dir
                    logger.debug(f"Set working_dir to {self.file_manager.agent_dir} for output tool {step.tool_name}")
                elif step.tool_name == "read_analysis_summary":
                    # Input tool - use base directory to find analysis files
                    base_dir = Path(self.file_manager.agent_dir).parent
                    params["working_dir"] = str(base_dir)
                    logger.debug(f"Set working_dir to {base_dir} for input tool {step.tool_name}")
                
                if step.tool_name == "generate_html_report":
                    params["analysis_data"] = analysis_data
                    params["literature_refs"] = literature_refs
                    # Pass system info from state
                    params["system_info"] = state.get("system_info")
                    # Generate final impression using LLM
                    logger.info("  [exec] Generating LLM final impression...")
                    params["final_impression"] = self._generate_final_impression(
                        analysis_data, literature_refs, state
                    )
                    logger.info("  [exec] Final impression: %s",
                                "generated" if params["final_impression"] else "skipped/unavailable")
                    # Extract PDB frames at analysis-driven timepoints for 3D viewer
                    logger.info("  [exec] Extracting PDB frames for 3D viewer (analysis-driven)...")
                    pdb_frames = self._extract_pdb_for_viewer(state, analysis_data)
                    params["pdb_data"] = pdb_frames  # Dict[str, str] or None
                    logger.info("  [exec] PDB frames: %s",
                                f"{len(pdb_frames)} timepoints ({', '.join(pdb_frames.keys())})"
                                if pdb_frames else "none")
                    # Pass enriched prompt (supervisor-rephrased user goal)
                    params["enriched_prompt"] = state.get("enriched_prompt") or state.get("user_goal")
                
                # Execute tool
                result = self.tool_executor.execute_tool(step.tool_name, params)
                
                # Store results for next steps; only update if the new result has
                # entries — don't discard a good pre-loaded analysis_data with an
                # empty result from a duplicate plan step.
                if step.tool_name == "read_analysis_summary":
                    if isinstance(result, dict) and result.get("entries"):
                        analysis_data = result
                    else:
                        logger.warning(
                            "Plan-step read_analysis_summary returned no entries; "
                            "keeping pre-loaded analysis_data (%d entries)",
                            len(analysis_data.get("entries", [])),
                        )
                
                step_results.append({
                    "step_name": step.name,
                    "tool": step.tool_name,
                    "success": result.get("success", True),
                    "result": result
                })
                
                completed += 1
                
                log_agent_action("reporter", f"Step {i+1}/{total_steps} completed", {
                    "step": step.name,
                    "tool": step.tool_name,
                    "status": "✅ SUCCESS"
                })
                
            except Exception as e:
                logger.error(f"Step {step.name} failed: {e}", exc_info=True)
                issues.append(f"{step.name}: {str(e)}")
                step_results.append({
                    "step_name": step.name,
                    "tool": step.tool_name,
                    "success": False,
                    "error": str(e)
                })
                
                log_agent_action("reporter", f"Step {i+1}/{total_steps} failed", {
                    "step": step.name,
                    "tool": step.tool_name,
                    "status": "❌ FAILED",
                    "error": str(e)
                })
        
        # Guarantee literature search: if no refs collected, run searches now
        if not literature_refs and analysis_data:
            literature_refs = self._ensure_literature_search(analysis_data, state)
        
        # Build report
        report_lines = ["=" * 80, "REPORTER EXECUTION REPORT", "=" * 80, ""]
        report_lines.append(f"Completed: {completed}/{len(plan.steps)} steps")
        report_lines.append("")
        
        if step_results:
            report_lines.append("STEPS EXECUTED:")
            for result in step_results:
                status = "✅" if result.get("success") else "❌"
                report_lines.append(f"  {status} {result.get('step_name')}")
        
        if issues:
            report_lines.append("")
            report_lines.append("ISSUES:")
            for issue in issues:
                report_lines.append(f"  ❌ {issue}")
        
        report_lines.append("=" * 80)
        report = "\n".join(report_lines)
        
        logger.info(report)
        
        # Save execution report to files
        self._save_execution_report(plan, step_results, analysis_data, literature_refs, issues, warnings)
        
        # Extract report file path
        report_file = None
        for result in step_results:
            if result.get("tool") == "generate_html_report" and result.get("success"):
                report_file = result.get("result", {}).get("report_file")
        
        # Add comprehensive summary file to generated files
        comprehensive_file = os.path.join(self.file_manager.agent_dir, "comprehensive_summary.json")
        generated_files = {"html": report_file} if report_file else {}
        if os.path.exists(comprehensive_file):
            generated_files["comprehensive_summary"] = comprehensive_file
        
        return ReporterResult(
            success=len(issues) == 0,
            completed_steps=completed,
            total_steps=len(plan.steps),
            report_file=report_file,
            analysis_summaries=[],  # Populated from analysis_data if needed
            literature_references=literature_refs,
            report_sections=[],
            key_findings=[],
            recommendations=[],
            issues=issues,
            warnings=warnings,
            report=report,
            generated_files=generated_files,
            step_results=step_results
        )
    
    def _save_execution_report(
        self,
        plan: ReporterPlan,
        step_results: List[Dict[str, Any]],
        analysis_data: Dict[str, Any],
        literature_refs: List[Dict[str, Any]],
        issues: List[str],
        warnings: List[str]
    ) -> None:
        """Save comprehensive execution report with LLM reasoning and results"""
        try:
            import datetime
            
            timestamp = datetime.datetime.now().isoformat()
            
            # 1. Save comprehensive summary in JSON format
            comprehensive_data = {
                "timestamp": timestamp,
                "llm_plan": {
                    "reasoning": plan.reasoning,
                    "overview": plan.overview,
                    "report_focus": plan.report_focus,
                    "literature_queries": plan.literature_queries,
                    "estimated_complexity": plan.estimated_complexity
                },
                "execution": {
                    "total_steps": len(plan.steps),
                    "completed_steps": sum(1 for r in step_results if r.get("success")),
                    "failed_steps": sum(1 for r in step_results if not r.get("success")),
                    "success_rate": f"{sum(1 for r in step_results if r.get('success')) / len(step_results) * 100:.1f}%" if step_results else "0%"
                },
                "step_results": step_results,
                "analysis_data_summary": {
                    "entries_found": len(analysis_data.get("entries", [])) if isinstance(analysis_data, dict) else 0,
                    "analysis_types": analysis_data.get("analysis_types", []) if isinstance(analysis_data, dict) else []
                },
                "literature_references": len(literature_refs),
                "issues": issues,
                "warnings": warnings
            }
            
            json_file = os.path.join(self.file_manager.agent_dir, "comprehensive_summary.json")
            with open(json_file, "w") as f:
                json.dump(comprehensive_data, f, indent=2)
            
            logger.info(f"Saved comprehensive summary (JSON) to {json_file}")
            
            # 2. Save execution report in Markdown format
            md_file = os.path.join(self.file_manager.agent_dir, "execution_report.md")
            with open(md_file, "w") as f:
                f.write(f"# Reporter Execution Report\\n\\n")
                f.write(f"**Generated:** {timestamp}\\n\\n")
                f.write(f"---\\n\\n")
                
                # LLM Planning Section
                f.write(f"## LLM Planning\\n\\n")
                f.write(f"### Reasoning\\n\\n{plan.reasoning}\\n\\n")
                f.write(f"### Overview\\n\\n{plan.overview}\\n\\n")
                f.write(f"### Report Focus Areas\\n\\n")
                for focus in plan.report_focus:
                    f.write(f"- {focus}\\n")
                f.write("\\n")
                
                if plan.literature_queries:
                    f.write(f"### Literature Search Queries\\n\\n")
                    for query in plan.literature_queries:
                        f.write(f"- {query}\\n")
                    f.write("\\n")
                
                # Execution Summary
                f.write(f"## Execution Summary\\n\\n")
                f.write(f"- **Total Steps:** {len(plan.steps)}\\n")
                f.write(f"- **Completed:** {comprehensive_data['execution']['completed_steps']}\\n")
                f.write(f"- **Failed:** {comprehensive_data['execution']['failed_steps']}\\n")
                f.write(f"- **Success Rate:** {comprehensive_data['execution']['success_rate']}\\n\\n")
                
                # Step-by-step results
                f.write(f"## Step-by-Step Execution\\n\\n")
                for i, result in enumerate(step_results, 1):
                    status = "\u2705 SUCCESS" if result.get("success") else "\u274c FAILED"
                    f.write(f"### Step {i}: {result.get('step_name')} [{status}]\\n\\n")
                    f.write(f"**Tool:** `{result.get('tool')}`\\n\\n")
                    
                    if result.get("success"):
                        tool_result = result.get("result", {})
                        if isinstance(tool_result, dict):
                            if "entries" in tool_result:
                                f.write(f"- Entries found: {len(tool_result['entries'])}\\n")
                            if "analysis_types" in tool_result:
                                f.write(f"- Analysis types: {', '.join(tool_result['analysis_types'])}\\n")
                            if "results" in tool_result:
                                f.write(f"- Results: {len(tool_result.get('results', []))} items\\n")
                            if "report_file" in tool_result:
                                f.write(f"- Report file: `{tool_result['report_file']}`\\n")
                    else:
                        f.write(f"**Error:** {result.get('error', 'Unknown error')}\\n")
                    
                    f.write("\\n")
                
                # Analysis Data Summary
                if analysis_data:
                    f.write(f"## Analysis Data Summary\\n\\n")
                    if isinstance(analysis_data, dict):
                        f.write(f"- **Entries:** {len(analysis_data.get('entries', []))}\\n")
                        f.write(f"- **Analysis Types:** {', '.join(analysis_data.get('analysis_types', []))}\\n")
                        
                        if "statistics" in analysis_data:
                            f.write(f"\\n### Statistics\\n\\n")
                            stats = analysis_data["statistics"]
                            for key, value in stats.items():
                                f.write(f"- **{key}:** {value}\\n")
                    f.write("\\n")
                
                # Literature References
                if literature_refs:
                    f.write(f"## Literature References ({len(literature_refs)})\\n\\n")
                    for i, ref in enumerate(literature_refs[:10], 1):  # Show first 10
                        title = ref.get("title", "Unknown")
                        authors = ref.get("authors", "Unknown authors")
                        f.write(f"{i}. **{title}**\\n")
                        f.write(f"   - Authors: {authors}\\n")
                        if "journal" in ref:
                            f.write(f"   - Journal: {ref['journal']}\\n")
                        f.write("\\n")
                    
                    if len(literature_refs) > 10:
                        f.write(f"*...and {len(literature_refs) - 10} more references*\\n\\n")
                
                # Issues and Warnings
                if issues:
                    f.write(f"## Issues\\n\\n")
                    for issue in issues:
                        f.write(f"- \u274c {issue}\\n")
                    f.write("\\n")
                
                if warnings:
                    f.write(f"## Warnings\\n\\n")
                    for warning in warnings:
                        f.write(f"- \u26a0\ufe0f {warning}\\n")
                    f.write("\\n")
                
                f.write(f"---\\n\\n")
                f.write(f"*Report generated by Reporter Agent with LLM planning*\\n")
            
            logger.info(f"Saved execution report (Markdown) to {md_file}")
            
            # 3. Save plain text execution log
            txt_file = os.path.join(self.file_manager.agent_dir, "execution_log.txt")
            with open(txt_file, "w") as f:
                f.write("=" * 80 + "\\n")
                f.write("REPORTER AGENT EXECUTION LOG\\n")
                f.write("=" * 80 + "\\n\\n")
                f.write(f"Timestamp: {timestamp}\\n\\n")
                
                f.write("LLM REASONING:\\n")
                f.write("-" * 80 + "\\n")
                f.write(plan.reasoning + "\\n\\n")
                
                f.write("EXECUTION STEPS:\\n")
                f.write("-" * 80 + "\\n")
                for i, result in enumerate(step_results, 1):
                    status = "OK" if result.get("success") else "FAIL"
                    f.write(f"[{status}] Step {i}: {result.get('step_name')}\\n")
                
                f.write("\\n")
                f.write("=" * 80 + "\\n")
                f.write(f"Completed: {comprehensive_data['execution']['completed_steps']}/{len(plan.steps)} steps\\n")
                f.write("=" * 80 + "\\n")
            
            logger.info(f"Saved execution log (TXT) to {txt_file}")
            
        except Exception as e:
            logger.warning(f"Failed to save execution report: {e}", exc_info=True)
    
    def _update_state(self, state: MDState, output: ReporterAgentOutput) -> None:
        """Update workflow state with reporter results"""
        
        state["reporter_output"] = {
            "success": output.success,
            "report_path": output.report_path,
            "pdf_path": output.pdf_path,
            "key_findings": output.result.key_findings,
            "recommendations": output.result.recommendations,
            "generated_files": output.result.generated_files
        }
        
        # Register all generated files
        if output.report_path:
            self.file_manager.register_external_file(
                file_path=output.report_path,
                file_type="html_report",
                description="Scientific analysis report (HTML)"
            )
        
        # Register comprehensive summary and execution reports
        for file_type, file_path in output.result.generated_files.items():
            if file_type != "html" and os.path.exists(file_path):
                self.file_manager.register_external_file(
                    file_path=file_path,
                    file_type=f"reporter_{file_type}",
                    description=f"Reporter {file_type.replace('_', ' ').title()}"
                )
        
        # Also register execution plan and report files
        agent_dir = self.file_manager.agent_dir
        for filename, description in [
            ("execution_plan.json", "Execution plan with LLM reasoning (JSON)"),
            ("execution_plan.md", "Execution plan with LLM reasoning (Markdown)"),
            ("comprehensive_summary.json", "Comprehensive execution summary (JSON)"),
            ("execution_report.md", "Detailed execution report (Markdown)"),
            ("execution_log.txt", "Execution log (Text)")
        ]:
            file_path = os.path.join(agent_dir, filename)
            if os.path.exists(file_path):
                self.file_manager.register_external_file(
                    file_path=file_path,
                    file_type=f"reporter_{filename.replace('.', '_')}",
                    description=description
                )
        
        if output.pdf_path:
            self.file_manager.register_external_file(
                file_path=output.pdf_path,
                file_type="pdf_report",
                description="Scientific analysis report (PDF)"
            )
        
        # Add errors to state
        if output.errors:
            state["errors"].extend(output.errors)
