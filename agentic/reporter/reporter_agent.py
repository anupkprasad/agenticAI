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
        Generates scientific reports from analysis summaries.
        """
        import sys
        import traceback
        
        # Extract input
        execution_plan = state.get("execution_plan", {})
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
            
            # Set next node
            state["next_node"] = "END"  # Reporter is typically the final step
            
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
            state["next_node"] = "END"
        
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
        execution_plan = state.get("execution_plan", {})
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
            user_goal=state.get("user_goal"),
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
            plan = None
            if self.llm.available:
                logger.info("Creating reporter execution plan with LLM")
                plan = self._create_llm_plan(agent_input, state)
            
            if not plan:
                logger.info("Using fallback plan generation")
                plan = self._create_fallback_plan(agent_input)
            
            log_agent_action(
                agent_name="reporter",
                action="Generated reporter plan",
                details={
                    "steps": len(plan.steps),
                    "report_focus": plan.report_focus[:3] if plan.report_focus else [],
                    "literature_queries": len(plan.literature_queries)
                }
            )
            
            # Step 2: Execute the plan
            result = self._execute_reporter_plan(agent_input, plan, state)
            
            # Step 3: Create final output
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
1. Reading the analysis_summary.jsonl file
2. Extracting key findings and statistics
3. Optionally searching scientific literature for context
4. Generating an HTML report with insights

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
    
    def _extract_plan_json(self, content: str) -> Dict[str, Any]:
        """Extract and parse JSON plan from LLM response"""
        json_match = re.search(r'\{[\s\S]*\}', content)
        if json_match:
            try:
                return json.loads(json_match.group())
            except json.JSONDecodeError:
                pass
        
        return {
            "reasoning": content,
            "overview": "Fallback plan",
            "steps": [],
            "estimated_complexity": "medium"
        }
    
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
        
        for step in plan.steps:
            try:
                logger.info(f"Executing step: {step.name}")
                
                # Special handling for steps that need previous results
                params = step.tool_params.copy()
                
                if step.tool_name == "generate_html_report":
                    params["analysis_data"] = analysis_data
                    params["literature_refs"] = literature_refs
                
                # Execute tool
                result = self.tool_executor.execute_tool(step.tool_name, params)
                
                # Store results for next steps
                if step.tool_name == "read_analysis_summary":
                    analysis_data = result
                elif step.tool_name == "search_pubmed":
                    if result.get("success"):
                        literature_refs.extend(result.get("results", []))
                
                step_results.append({
                    "step_name": step.name,
                    "tool": step.tool_name,
                    "success": result.get("success", True),
                    "result": result
                })
                
                completed += 1
                
            except Exception as e:
                logger.error(f"Step {step.name} failed: {e}", exc_info=True)
                issues.append(f"{step.name}: {str(e)}")
                step_results.append({
                    "step_name": step.name,
                    "tool": step.tool_name,
                    "success": False,
                    "error": str(e)
                })
        
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
        
        # Extract report file path
        report_file = None
        for result in step_results:
            if result.get("tool") == "generate_html_report" and result.get("success"):
                report_file = result.get("result", {}).get("report_file")
        
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
            generated_files={"html": report_file} if report_file else {},
            step_results=step_results
        )
    
    def _update_state(self, state: MDState, output: ReporterAgentOutput) -> None:
        """Update workflow state with reporter results"""
        
        state["reporter_output"] = {
            "success": output.success,
            "report_path": output.report_path,
            "pdf_path": output.pdf_path,
            "key_findings": output.result.key_findings,
            "recommendations": output.result.recommendations
        }
        
        # Register generated files
        if output.report_path:
            self.file_manager.register_external_file(
                file_path=output.report_path,
                file_type="html_report",
                description="Scientific analysis report"
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
