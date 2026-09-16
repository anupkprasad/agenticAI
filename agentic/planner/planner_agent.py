"""
MD Workflow Planner Agent - LLM-Powered with Dynamic Tools & Knowledge

Creates execution plans with access to:
- Dynamic tool discovery from all agents
- Knowledge base (research papers, protocols, manuals)
- Field-specific expertise for detailed planning
"""
import logging
import json
import yaml
import os
import re
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, Optional, List
from ..state import MDState
from ..llm import LLMClient
from ..utils import log_supervisor_routing, log_llm_interaction
from ..utils.plan_persistence import save_plan_artifacts
from ..programmer import MDProgrammer
from .tools_registry import get_tools_registry
from .knowledge_loader import get_knowledge_loader
from .planning_guidelines import (
    detect_combined_only_metrics,
    detect_classification_requested,
    detect_requested_metrics,
    get_intent_preservation_block,
    get_planner_metric_tool_reference,
    get_standard_output_filenames_block,
    get_com_distance_tool_guide,
    get_proximity_tool_guide,
    get_family_scale_planning_guide,
    get_master_plan_tools_note,
    metric_covered_by_registry,
    partition_metrics_by_registry,
)
from src.supervisor.component_case_resolver import resolve_component_cases, resolve_sim_label_and_dir
from src.supervisor.component_parser import append_sim_case_requirement

logger = logging.getLogger(__name__)


def _coerce_pdb_analysis(pdb_analysis: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    """Return a dict for PDB analysis; state may store explicit ``None``."""
    return pdb_analysis if isinstance(pdb_analysis, dict) else {}


_SIMULATION_STAGE_AGENTS = frozenset({"preprocess", "simsetup", "hpcjob"})


def _coerce_bool(value: Any, default: bool = False) -> bool:
    """Normalize LLM JSON boolean fields."""
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    if isinstance(value, str):
        lowered = value.strip().lower()
        if lowered in ("true", "yes", "1"):
            return True
        if lowered in ("false", "no", "0"):
            return False
    return default


def _coerce_plan_text(value: Any, default: str = "") -> str:
    """Normalize LLM plan fields (str, list, or dict) to a markdown-safe string."""
    if value is None:
        return default
    if isinstance(value, str):
        return value.strip() or default
    if isinstance(value, list):
        parts = [_coerce_plan_text(item, default="") for item in value]
        parts = [p for p in parts if p]
        return "\n".join(parts) if parts else default
    if isinstance(value, dict):
        for key in ("prompt", "goal", "text", "description", "plan"):
            if key in value and value[key]:
                return _coerce_plan_text(value[key], default=default)
        return json.dumps(value, indent=2, default=str)
    return str(value).strip() or default


def _is_post_simulation_subtask(state: Dict[str, Any]) -> bool:
    """True when only analysis and/or reporting should run on completed data."""
    subtask_type = state.get("subtask_type")
    if subtask_type in ("analysis_only", "reporter_only"):
        return True
    if subtask_type == "multi_agent":
        agents = set(state.get("agent_list") or [])
        return not bool(agents & _SIMULATION_STAGE_AGENTS)
    return False


def _goal_requests_combined_analysis(goal: str, agent_list: List[str], subtask_type: Optional[str]) -> bool:
    """Conservative intent detector for *post* cross-simulation analysis."""
    if subtask_type == "multi_agent" and not (set(agent_list or []) & {"analysis", "reporter"}):
        return False

    text = (goal or "").lower()
    text = (
        text.replace("\u2011", "-")
        .replace("\u2012", "-")
        .replace("\u2013", "-")
        .replace("\u2014", "-")
        .replace("\u2212", "-")
    )

    negative_patterns = [
        r"\bno\s+(combined|cross[-\s]?simulation|comparative|comparison)\b",
        r"\bdo\s+not\s+(compare|combine|aggregate)\b",
        r"\bwithout\s+(combined|comparison|comparative)\b",
        r"\bonly\s+per[-\s]?simulation\b",
        r"\beach\s+simulation\s+separately\b",
    ]
    if any(re.search(p, text) for p in negative_patterns):
        return False

    positive_patterns = [
        r"\bcombined\s+(analysis|report|comparison)\b",
        r"\bcross[-\s]?simulation\b",
        r"\bcomparative\s+(analysis|report|study|plots?)\b",
        r"\bcompare\s+(the\s+)?(simulations|proteins|systems|cases|conditions)\b",
        r"\bcomparison\s+(between|across|of)\b",
        r"\bacross\s+(all\s+)?(simulations|proteins|systems|cases|conditions)\b",
        r"\baggregate(d)?\s+(results|metrics|analysis)\b",
        r"\bclassif(y|ication)\b",
        r"\bcluster(ing|ed|s)?\b",
        r"\bunsupervised\b",
        r"\boverlay\b",
        r"\bcommon\s+(trends|patterns|flexible regions|motions)\b",
        r"\bconserved\s+(flexible regions|motions|dynamic patterns)\b",
        r"\bapo\s*(/|vs|versus|and)\s*holo\b",
        r"\bcase\s*(comparison|vs|versus)\b",
        r"\bward\b",
        r"\bfeature\s+table\b",
        r"\bdendrogram\b",
        r"\bheatmap\b",
    ]
    return any(re.search(p, text) for p in positive_patterns)


def _goal_requests_pre_combined(goal: str, agent_list: List[str], subtask_type: Optional[str]) -> bool:
    """True when the goal needs shared pre-traj cross-sim setup (pocket/MSA/consensus)."""
    if subtask_type == "multi_agent" and not (set(agent_list or []) & {"analysis", "reporter"}):
        return False

    text = (goal or "").lower()
    text = (
        text.replace("\u2011", "-")
        .replace("\u2012", "-")
        .replace("\u2013", "-")
        .replace("\u2014", "-")
        .replace("\u2212", "-")
    )
    if re.search(r"\bno\s+(pocket\s+map|consensus|msa|pre[-\s]?combined)\b", text):
        return False

    positive_patterns = [
        r"\bpocket\b",
        r"\bconsensus\b",
        r"\bmsa\b",
        r"\bsequence\s+alignment\b",
        r"\bglobal\s+sequence\s+alignment\b",
        r"\breference.*(pocket|map|align)",
        r"\bmap(ped)?\s+(that\s+)?pocket\b",
        r"\bdefine\s+(the\s+)?(atp\s+)?pocket\b",
        r"\bshared\s+reference\b",
        r"\bc[-\s]?alpha\b.*\b(consensus|align)",
        r"\bconsensus\s+c",
    ]
    return any(re.search(p, text) for p in positive_patterns)


def _build_pre_combined_plan_fallback(
    state: Dict[str, Any],
    expanded_entries: List[Dict[str, Any]],
) -> str:
    """Fallback pre-combined plan: pocket/MSA/consensus → base/cross_sim/."""
    original = (state.get("user_goal_original") or state.get("user_goal") or "").strip()
    labels = ", ".join(e.get("label", "") for e in expanded_entries)
    parts = [
        "Before any per-simulation trajectory analysis, run pre-combined "
        f"(cross-simulation) setup across: {labels}.",
        "Build a consensus sequence alignment (MSA) across systems when needed, "
        "define a reference consensus pocket (or reference-system pocket), and "
        "map pocket / consensus residues onto each simulation. "
        "Also plot the global MSA and the pocket/high-consensus MSA panels "
        "(``plot_reference_msa_alignment`` → reference_msa_full.png + "
        "reference_msa_pocket.png).",
        "Write artifacts under `{base}/cross_sim/` including at least "
        "`pocket_map.json` (reference label + per-sim mapped residues/selections) "
        "and consensus residue / MSA files so per-sim analysis can auto-discover them.",
        "Do not run per-sim RMSD/RMSF/DCCM overlays here — only shared mapping "
        "inputs for later traj analysis.",
    ]
    if original:
        return f"{' '.join(parts)}\n\nOriginal study goal for reference:\n{original}"
    return " ".join(parts)


def sync_combined_planner_flags(state: Dict[str, Any]) -> None:
    """Keep legacy ``run_combined_analysis`` in sync with ``run_post_combined``."""
    n = len(state.get("sim_prompts") or [])
    if n <= 1:
        state["run_pre_combined"] = False
        state["pre_combined_plan"] = ""
        state["run_post_combined"] = False
        state["post_combined_plan"] = ""
        state["run_combined_analysis"] = False
        state["combined_analysis_plan"] = ""
        return

    # Prefer explicit post flags; fall back to legacy combined_*
    if state.get("run_post_combined") is None and state.get("run_combined_analysis") is not None:
        state["run_post_combined"] = bool(state.get("run_combined_analysis"))
    if not (state.get("post_combined_plan") or "").strip() and (
        state.get("combined_analysis_plan") or ""
    ).strip():
        state["post_combined_plan"] = state.get("combined_analysis_plan")

    if state.get("run_post_combined") is None:
        state["run_post_combined"] = False
    if state.get("run_pre_combined") is None:
        state["run_pre_combined"] = False

    state["run_combined_analysis"] = bool(state.get("run_post_combined"))
    state["combined_analysis_plan"] = (
        state.get("post_combined_plan") or state.get("combined_analysis_plan") or ""
    )
    if not state.get("run_pre_combined"):
        state["pre_combined_plan"] = state.get("pre_combined_plan") or ""
    if not state.get("run_post_combined"):
        state["post_combined_plan"] = ""
        state["combined_analysis_plan"] = ""



def _llm_sim_prompts_collapsed_per_pdb(
    sim_prompts_list: List[str],
    pdb_list: List[str],
    expanded_entries: List[Dict[str, Any]],
) -> bool:
    """True when LLM merged multiple cases (e.g. apo+holo) into one prompt per PDB."""
    if len(sim_prompts_list) != len(pdb_list):
        return False
    if len(expanded_entries) <= len(pdb_list):
        return False
    multi_case_re = re.compile(
        r"\b(?:both|two)\s+(?:the\s+)?(?:protein[\-\s]?only|apo|holo|systems?|cases?)\b"
        r"|\bapo\s*(?:and|&|\+)\s*holo\b"
        r"|\bboth\s+(?:apo|holo|systems|cases)\b",
        re.IGNORECASE,
    )
    hits = sum(
        1 for text in sim_prompts_list if multi_case_re.search(_coerce_plan_text(text))
    )
    return hits >= max(1, len(sim_prompts_list) // 2)


def _normalize_prompt_template(text: str) -> str:
    """Strip per-sim identity tokens so copy-paste LLM templates compare equal."""
    s = re.sub(r"\s+", " ", (_coerce_plan_text(text) or "").strip().lower())
    # Paths and UniProt-like accession labels / pdb stems
    s = re.sub(r"/home/\S+", "<path>", s)
    s = re.sub(r"(?:^|[\s/])[a-z][0-9][a-z0-9]{4,}(?:\.pdb)?\b", " <id>", s)
    s = re.sub(r"\blabel\s*[:=]?\s*\S+", "label=<id>", s)
    s = re.sub(r"\b[pqo]\d{4,}\b", "<id>", s)
    return s.strip()


def _llm_sim_prompts_are_template_duplicates(sim_prompts_list: List[str]) -> bool:
    """True when prompts differ only by label/path (human-looking copy-paste)."""
    if len(sim_prompts_list) < 2:
        return False
    norms = [_normalize_prompt_template(t) for t in sim_prompts_list]
    norms = [n for n in norms if n]
    if len(norms) < 2:
        return False
    # Majority share one template skeleton
    from collections import Counter

    counts = Counter(norms)
    top_n = counts.most_common(1)[0][1]
    return top_n >= max(2, (len(norms) + 1) // 2)


def _build_shared_per_sim_intent(
    *,
    original_goal: str,
    enriched_prompt: str,
    agents_desc: str,
    post_sim_subtask: bool,
) -> str:
    """One shared scientific intent applied to every simulation entry."""
    per_sim_metrics = detect_requested_metrics(original_goal or enriched_prompt or "")
    if per_sim_metrics:
        metrics_text = ", ".join(
            _METRIC_PHRASES.get(m, m) for m in sorted(per_sim_metrics)
        )
        analyses_clause = f"Run these analyses: {metrics_text}."
    else:
        analyses_clause = (
            "Run the per-simulation analyses named in the project goal for this system."
        )
    stage = (
        "Trajectory and topology are already staged under {working_dir}/hpc/ "
        "(md.tpr, mdWrap.xtc). Do not re-run preprocessing, setup, or HPC submission."
        if post_sim_subtask
        else f"Workflow steps: {agents_desc}."
    )
    return (
        f"Shared per-simulation workflow intent: {analyses_clause} {stage} "
        "Write outputs under {working_dir}/analysis/ using standard basenames "
        "(no label prefix). After analysis, prepare a concise HTML report for this "
        "simulation under {working_dir}/reporter/."
    )


def _build_compact_per_sim_prompt(
    entry: Dict[str, Any],
    *,
    shared_intent: str,
) -> str:
    """Identity stanza + shared intent (avoids N near-duplicate essay prompts)."""
    protein = entry.get("protein_name") or entry.get("label", "system")
    label = entry.get("label", "simulation")
    case = entry.get("case_description", "default system")
    case_id = entry.get("case_id") or ""
    directive = (entry.get("case_directive") or "").strip()
    wdir = entry.get("working_dir", "")
    pdb_name = Path(entry.get("pdb", "")).name or f"{label}.pdb"
    intent = shared_intent.replace("{working_dir}", wdir)
    case_bits = case
    if case_id:
        case_bits = f"{case}; case_id={case_id}"
    directive_bit = f" {directive}" if directive else ""
    return (
        f"Simulation {label} ({protein}; {case_bits}; source {pdb_name}; "
        f"working directory {wdir}).{directive_bit} {intent}"
    ).strip()


_METRIC_PHRASES: Dict[str, str] = {
    "com": "ligand pocket distance",
    "contacts": "protein–ATP contacts",
    "pocket_sasa": "pocket SASA",
    "residence": "ligand residence and unbinding",
    "pocket_rmsf": "pocket RMSF",
    "ligand_rmsf": "ligand RMSF",
    "pca": "PCA on Cα",
    "fel": "free-energy landscape at 310 K and FEL basin features",
    "rmsd": "RMSD",
    "rmsf": "protein RMSF",
    "rg": "radius of gyration",
    "sasa": "SASA",
    "energy": "energy",
    "dccm": "DCCM",
    "dssp": "secondary structure (DSSP)",
}


def _strip_markdown_json_fence(text: str) -> str:
    text = (text or "").strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text)
        text = re.sub(r"\s*```$", "", text).strip()
    return text


def _salvage_sim_prompts_from_response(response: str) -> Optional[List[str]]:
    """Extract sim_prompt strings from truncated or malformed LLM JSON."""
    text = _strip_markdown_json_fence(response)
    match = re.search(r'"sim_prompts"\s*:\s*\[', text, re.IGNORECASE)
    if not match:
        return None
    tail = text[match.end():]
    prompts: List[str] = []
    for item_match in re.finditer(r'"((?:[^"\\]|\\.)*)"', tail):
        try:
            prompt = json.loads(f'"{item_match.group(1)}"')
        except json.JSONDecodeError:
            continue
        if len(prompt.strip()) > 40:
            prompts.append(prompt)
    return prompts if prompts else None


def _enrich_protein_name_from_goal(uid: str, current_name: str, *goal_texts: str) -> str:
    """Resolve gene name from goal text when master plan only has UniProt accession."""
    try:
        from src.reporter.protein_identity import (
            _gene_from_goal,
            _looks_like_uniprot,
            _parse_id_name_map,
        )
    except ImportError:
        return current_name

    combined = " ".join(t for t in goal_texts if t)
    id_map = _parse_id_name_map(combined)
    if uid.lower() in id_map:
        return id_map[uid.lower()]
    if current_name and not _looks_like_uniprot(current_name) and current_name.upper() != uid.upper():
        return current_name
    gene = _gene_from_goal(uid, combined)
    if gene:
        return gene
    return current_name


def _build_per_sim_analysis_prompt(
    entry: Dict[str, Any],
    *,
    original_goal: str,
    enriched_prompt: str,
    agents_desc: str,
) -> str:
    """Deterministic per-simulation prompt for post-simulation analysis/reporter runs."""
    shared = _build_shared_per_sim_intent(
        original_goal=original_goal,
        enriched_prompt=enriched_prompt,
        agents_desc=agents_desc,
        post_sim_subtask=True,
    )
    return _build_compact_per_sim_prompt(entry, shared_intent=shared)


def _is_mock_or_error_llm_response(text: str) -> bool:
    """Return True when the LLM response is a mock/error sentinel string."""
    msg = (text or "").strip().lower()
    if not msg:
        return True
    return (
        msg.startswith("mock_llm_response:")
        or "http_error" in msg
        or "no reachable llm endpoints" in msg
        or msg.startswith("llm_error:")
        or msg.startswith("http_llm_error:")
    )


def _build_combined_analysis_plan_fallback(
    state: Dict[str, Any],
    expanded_entries: List[Dict[str, Any]],
) -> str:
    """Fallback combined plan when LLM decomposition is unavailable."""
    original = (state.get("user_goal_original") or state.get("user_goal") or "").strip()
    labels = ", ".join(e.get("label", "") for e in expanded_entries)
    parts = [
        "Perform cross-simulation analysis across these completed simulations: "
        f"{labels}.",
    ]
    if detect_classification_requested(original):
        parts.append(
            "Build an unsupervised classification feature table (raw CSV + z-score CSV) "
            "from per-simulation outputs, then cluster with hierarchical clustering "
            "(Ward linkage, default) on the z-score matrix. Plot clusters labeled with "
            "protein names using the id:name map from the user goal."
        )
    if original and re.search(
        r"overlay|compare|across simulations|cross[-\s]?sim",
        original,
        re.IGNORECASE,
    ):
        parts.append(
            "Overlay or compare requested metrics across simulations "
            "(e.g. ligand pocket distance and protein RMSF when named in the goal)."
        )
    parts.append(
        "Generate a combined HTML report summarizing shared trends, differences, "
        "and limitations. Do not add analyses outside the user goal."
    )
    if original:
        return f"{' '.join(parts)}\n\nOriginal study goal for reference:\n{original}"
    return " ".join(parts)


class MDPlanner:
    """
    LLM-powered planner with dynamic tools and knowledge access.
    
    Creates detailed execution plans by:
    1. Discovering available tools from all agents dynamically
    2. Loading relevant knowledge from knowledge base
    3. Using LLM to create context-aware execution plans
    4. Providing high-level plans for field agents to structure
    """
    
    def __init__(self, llm_client: LLMClient, config_path: Optional[str] = None):
        if llm_client is None:
            raise ValueError("llm_client is required")
        
        self.llm = llm_client
        self.config_path = config_path or os.path.join(
            os.path.dirname(__file__), "config.yaml"
        )
        
        # Load configuration
        self.config = self._load_config()
        
        # Initialize programmer as internal component
        self.programmer = MDProgrammer(llm_client=self.llm)
        
        # Initialize tools registry (dynamic tool discovery)
        logger.info("Initializing tools registry...")
        self.tools_registry = get_tools_registry()
        
        # Initialize knowledge loader
        logger.info("Loading knowledge base...")
        self.knowledge_loader = get_knowledge_loader()
        
        logger.info(f"MD Planner initialized with {len(self.tools_registry.tools)} tools and "
                   f"{len(self.knowledge_loader.knowledge_docs)} knowledge documents")
    
    def _should_exclude_combined_tools(self, state: MDState) -> bool:
        """Exclude combined tools unless we are in a combined (pre/post) phase."""
        phase = state.get("multi_sim_phase")
        if phase in (
            "combined_analysis",
            "post_combined",
            "pre_combined",
            "combined_reporter",
        ):
            return False
        return True

    def _get_per_sim_scope_note(self, state: MDState) -> str:
        """Planning-scope reminder for individual simulation workflows."""
        if not self._should_exclude_combined_tools(state):
            return ""

        parts = [
            "**SCOPE — INDIVIDUAL SIMULATION ONLY (CRITICAL):**",
            "- Plan analysis for THIS simulation's trajectory only.",
            "- Do NOT plan cross-simulation comparisons, overlay plots across multiple sim_dirs,",
            "  or any run_combined_* / plot_combined_overlay / collect_metric_files steps.",
            "- Cross-simulation combined analysis is handled automatically in a later workflow phase",
            "  after all individual simulations complete.",
        ]
        if state.get("is_multi_simulation"):
            idx = state.get("current_sim_index", 0)
            sim_prompts = state.get("sim_prompts") or []
            label = ""
            if 0 <= idx < len(sim_prompts):
                label = sim_prompts[idx].get("label", "")
            if label:
                parts.insert(1, f"- Current simulation label: {label}")
            parts.append(
                "- Focus the Analysis Agent instructions on metrics and plots for this label only."
            )
        return "\n".join(parts) + "\n"

    def _get_tools_context(
        self,
        agent_name: Optional[str] = None,
        exclude_combined_tools: bool = False,
    ) -> str:
        """
        Get formatted tools context for LLM.
        
        Args:
            agent_name: If specified, only get tools for this agent
            exclude_combined_tools: Omit cross-simulation combined-analysis tools
            
        Returns:
            Formatted tools description string
        """
        return self.tools_registry.get_tools_for_planner(
            agent_name,
            exclude_combined_tools=exclude_combined_tools,
        )
    
    def _get_knowledge_context(self, 
                               category: Optional[str] = None,
                               max_chars: int = 8000) -> str:
        """
        Get formatted knowledge context for LLM.
        
        Args:
            category: If specified, only get knowledge from this category
            max_chars: Maximum characters to include in context
            
        Returns:
            Formatted knowledge string
        """
        return self.knowledge_loader.get_knowledge_for_planner(category, max_chars)
    
    def _get_knowledge_summary(self) -> str:
        """Get knowledge files summary (for logging only, not full content)."""
        return self.knowledge_loader.get_knowledge_files_summary()

    def _get_combined_tools_context(
        self,
        agent_list: List[str],
        exclude_combined_tools: bool = False,
    ) -> str:
        """
        Get tools context for a list of agents combined, preserving workflow order.

        CLI agent names are mapped to the registry names used by ToolsRegistry.
        Falls back to all tools if agent_list is empty.

        Args:
            agent_list: Ordered list of CLI agent names (e.g. ["analysis", "reporter"])
            exclude_combined_tools: Omit cross-simulation combined-analysis tools from analysis

        Returns:
            Formatted tools description string covering all listed agents
        """
        _cli_to_registry = {
            "preprocess": "preprocess",
            "simsetup": "simsetup",
            "hpcjob": "hpc",
            "analysis": "analysis",
            "reporter": "reporter",
        }
        
        logger.info(f"PLANNER: _get_combined_tools_context called with agent_list={agent_list}")
        
        if not agent_list:
            logger.warning("PLANNER: agent_list is empty, returning all tools")
            return self._get_tools_context(exclude_combined_tools=exclude_combined_tools)

        parts = []
        seen = set()
        for cli_name in agent_list:
            registry_name = _cli_to_registry.get(cli_name, cli_name)
            logger.info(f"PLANNER: Getting tools for agent '{cli_name}' (registry_name='{registry_name}')")
            if registry_name in seen:
                logger.debug(f"PLANNER: Skipping duplicate agent '{registry_name}'")
                continue
            seen.add(registry_name)
            ctx = self._get_tools_context(
                agent_name=registry_name,
                exclude_combined_tools=exclude_combined_tools,
            )
            if ctx.strip():
                logger.info(f"PLANNER: Added tools context for '{registry_name}' ({len(ctx)} chars)")
                parts.append(ctx)
            else:
                logger.warning(f"PLANNER: No tools found for agent '{registry_name}'")

        if not parts:
            logger.error(f"PLANNER: No tools found for any agent in {agent_list}, falling back to ALL tools")
            return self._get_tools_context(exclude_combined_tools=exclude_combined_tools)
        
        logger.info(f"PLANNER: Returning combined tools context for {len(parts)} agents")
        return "\n".join(parts)
    
    def _load_config(self) -> Dict[str, Any]:
        """Load planner configuration from YAML."""
        if os.path.exists(self.config_path):
            with open(self.config_path, 'r') as f:
                config = yaml.safe_load(f) or {}
                logger.info(f"Loaded planner config from {self.config_path}")
                return config
        else:
            logger.warning(f"Config not found: {self.config_path}, using defaults")
            return {"planner": {"templates": {}}}

    def create_multi_sim_master_plan(self, state: MDState) -> MDState:
        """Build per-sim prompts and optional combined analysis plan with planner tools context."""
        from src.utils.pdb_paths import unique_pdb_paths
        from ..utils import log_agent_action

        enriched_prompt = state.get("enriched_prompt") or state.get("user_goal", "")
        original_goal = (
            state.get("user_goal_original")
            or state.get("user_goal")
            or enriched_prompt
        )
        pdb_list = unique_pdb_paths(state.get("pdb_list") or [])
        state["pdb_list"] = pdb_list
        agent_list = state.get("agent_list") or []
        subtask_type = state.get("subtask_type")
        post_sim_subtask = _is_post_simulation_subtask(state)

        if not pdb_list:
            logger.warning("PLANNER [multi-sim]: No pdb_list - cannot create master plan")
            return state

        base_working_dir = str(
            Path(state.get("multi_sim_base_dir") or state.get("working_directory", "working_dir")).resolve()
        )
        state["multi_sim_base_dir"] = base_working_dir
        # Campaign-level master plan summary only (not per-sim preprocess/setup detail).
        from ..utils.conversation_logger import set_log_file
        set_log_file(str(Path(base_working_dir) / "agent_conversation.log"))

        self.tools_registry = get_tools_registry(refresh=True, working_directory=base_working_dir)
        per_sim_tools_context = self.tools_registry.get_master_plan_per_sim_tools_context(
            agent_list,
        ) if agent_list else self.tools_registry.get_master_plan_per_sim_tools_context(
            ["analysis", "reporter"],
        )
        combined_tools_context = self.tools_registry.get_combined_only_tools_context()
        tools_note = get_master_plan_tools_note(agent_list)
        intent_block = get_intent_preservation_block(original_goal)
        filenames_block = get_standard_output_filenames_block()

        protein_name_map: Dict[str, str] = {}
        for match in re.finditer(
            r'\b([A-Za-z0-9]{4,12})\s*:\s*([A-Za-z][A-Za-z0-9_\-]{1,30})',
            enriched_prompt,
        ):
            key, value = match.group(1).lower(), match.group(2).strip()
            if any(c.isdigit() for c in key) and value[0].isupper():
                protein_name_map[key] = value
        if protein_name_map:
            logger.info(f"PLANNER [multi-sim]: Protein name map: {protein_name_map}")

        all_pdb_analyses = state.get("all_pdb_analyses") or []
        pdb_analysis_map: Dict[str, Dict[str, Any]] = {}
        for idx, pdb in enumerate(pdb_list):
            if idx < len(all_pdb_analyses):
                pdb_analysis_map[Path(pdb).name] = all_pdb_analyses[idx]

        pdb_summary_lines: List[str] = []
        for pdb in pdb_list:
            pdb_name = Path(pdb).name
            analysis = pdb_analysis_map.get(pdb_name) or {}
            comps = analysis.get("components_available", {})
            comp_desc = []
            if comps.get("protein"):
                comp_desc.append("protein")
            if comps.get("ligand"):
                ligands = analysis.get("ligand", {}).get("residue_names", [])
                comp_desc.append(f"ligand({','.join(ligands[:2])})" if ligands else "ligand")
            if comps.get("ions"):
                comp_desc.append("ions")
            line = f"  - {pdb_name}"
            if comp_desc:
                line += f": {','.join(comp_desc)}"
            pdb_summary_lines.append(line)

        component_cases = resolve_component_cases(
            original_goal,
            enriched_prompt,
            pdb_count=len(pdb_list),
            pdb_summaries=pdb_summary_lines,
            llm_client=self.llm,
            is_error_response=_is_mock_or_error_llm_response,
            prefer_llm=bool(state.get("use_llm", True)),
        )
        # Absolute guard: component cases are templates applied to every PDB, never
        # one entry per structure. Cap protects against future LLM pathologies.
        if len(component_cases) > 4:
            logger.warning(
                "PLANNER [multi-sim]: truncating %d component cases to 4",
                len(component_cases),
            )
            component_cases = component_cases[:4]
        logger.info(
            "PLANNER [multi-sim]: Component cases resolved: %s",
            [c.get("description") for c in component_cases],
        )

        expanded_entries: List[Dict[str, Any]] = []
        multi_component_cases = len(component_cases) > 1
        for pdb in pdb_list:
            uid = Path(pdb).stem
            protein_name = protein_name_map.get(uid.lower(), uid.upper())
            protein_name = _enrich_protein_name_from_goal(
                uid, protein_name, original_goal, enriched_prompt,
            )
            for case in component_cases:
                suffix = case.get("suffix", "")
                sim_label, sim_dir = resolve_sim_label_and_dir(
                    uid, suffix, base_working_dir,
                    multi_component_cases=multi_component_cases,
                )
                expanded_entries.append(
                    {
                        "pdb": pdb,
                        "uid": uid,
                        "protein_name": protein_name,
                        "label": sim_label,
                        "working_dir": sim_dir,
                        "case_id": case.get("case_id"),
                        "case_description": case.get("description", "default system"),
                        "case_directive": case.get("directive", "Use full system from PDB."),
                    }
                )

        state["sim_working_dirs"] = [e["working_dir"] for e in expanded_entries]

        sim_context_lines: List[str] = []
        for i, entry in enumerate(expanded_entries, 1):
            pdb_name = Path(entry["pdb"]).name
            line = (
                f"  {i}. label={entry['label']} | source={pdb_name} | "
                f"case={entry['case_description']} | dir={entry['working_dir']}"
            )
            analysis = pdb_analysis_map.get(pdb_name)
            if analysis:
                comps = analysis.get("components_available", {})
                comp_desc = []
                if comps.get("protein"):
                    comp_desc.append("protein")
                if comps.get("ligand"):
                    ligands = analysis.get("ligand", {}).get("residue_names", [])
                    comp_desc.append(f"ligand({','.join(ligands[:2])})" if ligands else "ligand")
                if comps.get("ions"):
                    comp_desc.append("ions")
                if comp_desc:
                    line += f" | source_components={','.join(comp_desc)}"
                if analysis.get("total_atoms"):
                    line += f" | atoms={analysis['total_atoms']}"
            sim_context_lines.append(line)

        agents_desc = " -> ".join(agent_list) if agent_list else (subtask_type or "full pipeline")
        name_map_lines = ""
        if protein_name_map:
            name_map_lines = (
                "PROTEIN MAPPINGS:\n"
                + "\n".join(f"  {uid}: {name}" for uid, name in protein_name_map.items())
                + "\n\n"
            )

        default_combined = _goal_requests_combined_analysis(original_goal, agent_list, subtask_type)
        default_pre = _goal_requests_pre_combined(original_goal, agent_list, subtask_type)
        decomposition_prompt = (
            "You are the MD workflow Planner. Create the multi-simulation master plan using the "
            "available per-simulation and combined-analysis tools below.\n\n"
            f"OVERALL USER GOAL:\n{original_goal}\n\n"
            f"ENRICHED CONTEXT:\n{enriched_prompt}\n\n"
            f"SIMULATION ENTRIES ({len(expanded_entries)} total):\n"
            + "\n".join(sim_context_lines)
            + "\n\n"
            + name_map_lines
            + f"WORKFLOW PIPELINE FOR EACH SIMULATION: {agents_desc}\n\n"
            + f"{tools_note}\n\n"
            + f"PER-SIMULATION TOOLS (one section per workflow agent; excludes cross-sim tools):\n"
            + f"{per_sim_tools_context}\n\n"
            + f"CROSS-SIMULATION TOOLS ONLY (base-level; do NOT repeat per-sim tool lists):\n"
            + f"{combined_tools_context}\n\n"
            + f"{intent_block}\n\n"
            + f"{filenames_block}\n\n"
            + f"{get_com_distance_tool_guide()}\n\n"
            + f"{get_proximity_tool_guide()}\n\n"
            + f"{get_family_scale_planning_guide()}\n\n"
            "TASK: Return only valid JSON with keys:\n"
            f"1) sim_prompts: list of {len(expanded_entries)} complete natural-language prompts, same order as entries.\n"
            "2) run_pre_combined: boolean; true only when shared cross-sim setup is needed BEFORE "
            "per-sim trajectory analysis (pocket mapping, MSA, consensus residues, reference "
            "alignment). Requires multiple simulations. Write artifacts to base/cross_sim/.\n"
            "3) pre_combined_plan: natural-language plan when run_pre_combined is true; else \"\".\n"
            "4) run_post_combined: boolean; true when comparison/aggregation/Ward/overlays/combined "
            "report is needed AFTER all per-sim analysis+reporter finish. Requires multiple simulations.\n"
            "5) post_combined_plan: natural-language plan when run_post_combined is true; else \"\".\n"
            "Legacy aliases (optional): run_combined_analysis / combined_analysis_plan map to "
            "run_post_combined / post_combined_plan.\n\n"
            "CRITICAL prompt requirements for sim_prompts:\n"
            "- Each prompt must target exactly ONE simulation entry (one label, one case). Never merge apo and holo (or multiple component cases) into a single sim_prompt.\n"
            "- Prefer a short identity stanza (label, protein, source, working directory, case) plus the shared scientific intent — do NOT write eight near-identical essay prompts that only swap the accession/path.\n"
            "- Preserve user intent exactly. If the user names specific analyses such as RMSF only, request only those analyses plus directly required plots/tables. Do not add RMSD, Rg, COM distance, DCCM, DSSP, SASA, or literature unless requested.\n"
            "- If the user asks broadly for protein dynamics without naming metrics, choose a small justified set of dynamics analyses supported by the tools, such as RMSD/RMSF/Rg/DCCM or interaction distances when relevant to the biological question.\n"
            "- For post-simulation workflows, do not mention preprocessing, system setup, force-field choice, box size, HPC submission, or simulation length because those stages are finished.\n"
            "- Avoid comma-separated key=value prompt strings because downstream agents treat them as metadata stubs; write complete sentences with enough context for analysis and reporting.\n"
            "- Do not copy and paste the same prompt for every entry. If the protocol is shared, keep the science wording identical and only change identity fields (label/path/protein).\n"
            f"- Mention only these workflow steps: {agents_desc}.\n"
            "- Keep each sim_prompt concise (under ~80 words) so all entries and combined fields fit in one JSON response.\n\n"
            "For run_pre_combined / run_post_combined, use the user goal as the source of truth. "
            f"Heuristics before this call: pre={default_pre}, post={default_combined}; "
            "override only if the goal text clearly supports a different choice.\n"
            "Return only valid JSON."
        )

        sim_prompts_list = None
        prompt_source = "deterministic_fallback"
        combined_plan = ""
        pre_combined_plan = ""
        post_combined_plan = ""
        run_combined_analysis = default_combined
        run_pre_combined = default_pre
        run_post_combined = default_combined
        decomposition_complete = False
        parsed = None
        # Always ask the LLM for the master plan (incl. pre/post flags + plans).
        # Deterministic prompts are only a fallback when the LLM fails or returns
        # unusable copy-paste sim_prompts.
        _use_llm_decomp = True
        try:
            if not _use_llm_decomp:
                raise RuntimeError("skip_llm_decomp_disabled")
            response = self.llm.prompt_raw(
                decomposition_prompt, temperature=0.35, max_tokens=12288, format="json"
            )
            log_llm_interaction("planner.multi_sim_master", decomposition_prompt, response)
            if _is_mock_or_error_llm_response(response):
                logger.warning(
                    "PLANNER [multi-sim]: LLM decomposition returned mock/error response; "
                    "using deterministic prompt decomposition"
                )
                parsed = None
            else:
                parsed = self._extract_json_from_response(response)
            if parsed and "sim_prompts" in parsed:
                sim_prompts_list = [
                    _coerce_plan_text(item, default="")
                    for item in parsed["sim_prompts"]
                ]
                prompt_source = "llm"
                # Prefer explicit pre/post; legacy combined_* → post
                run_post_combined = _coerce_bool(
                    parsed.get("run_post_combined", parsed.get("run_combined_analysis")),
                    default=default_combined,
                )
                post_combined_plan = _coerce_plan_text(
                    parsed.get(
                        "post_combined_plan",
                        parsed.get("combined_analysis_plan", ""),
                    ),
                    default="",
                )
                run_pre_combined = _coerce_bool(
                    parsed.get("run_pre_combined"),
                    default=default_pre,
                )
                pre_combined_plan = _coerce_plan_text(
                    parsed.get("pre_combined_plan", ""),
                    default="",
                )
                run_combined_analysis = run_post_combined
                combined_plan = post_combined_plan
                logger.info(
                    f"PLANNER [multi-sim]: LLM generated {len(sim_prompts_list)} per-sim prompts; "
                    f"run_pre_combined={run_pre_combined} "
                    f"run_post_combined={run_post_combined}"
                )

                if len(sim_prompts_list) > 1:
                    normalized = [
                        re.sub(r"\s+", " ", (_coerce_plan_text(text) or "").strip().lower())
                        for text in sim_prompts_list
                    ]
                    if len(set(normalized)) == 1 or _llm_sim_prompts_are_template_duplicates(
                        sim_prompts_list
                    ):
                        logger.warning(
                            "PLANNER [multi-sim]: LLM sim_prompts are copy-paste "
                            "templates (identical or label/path-only variants); "
                            "using compact deterministic per-sim prompts but "
                            "keeping LLM pre/post combined flags and plans"
                        )
                        sim_prompts_list = None
                        prompt_source = "llm_pre_post_deterministic_prompts"

                if sim_prompts_list and len(sim_prompts_list) != len(expanded_entries):
                    if _llm_sim_prompts_collapsed_per_pdb(
                        sim_prompts_list, pdb_list, expanded_entries
                    ):
                        logger.warning(
                            "PLANNER [multi-sim]: LLM merged multiple cases into one prompt "
                            "per PDB; using deterministic per-entry prompts "
                            "(keeping LLM pre/post plans)"
                        )
                    else:
                        logger.warning(
                            "PLANNER [multi-sim]: LLM returned %d/%d sim_prompts; "
                            "using deterministic per-entry prompts "
                            "(keeping LLM pre/post plans)",
                            len(sim_prompts_list),
                            len(expanded_entries),
                        )
                    sim_prompts_list = None
                    prompt_source = "llm_pre_post_deterministic_prompts"

                decomposition_complete = False
                if parsed and prompt_source == "llm":
                    decomposition_complete = (
                        len(sim_prompts_list or []) == len(expanded_entries)
                        and _strip_markdown_json_fence(response).rstrip().endswith("}")
                    )
                elif parsed and prompt_source == "llm_pre_post_deterministic_prompts":
                    # LLM supplied pre/post fields; per-sim prompts use compact fallback.
                    decomposition_complete = True
        except Exception as exc:
            logger.warning(f"PLANNER [multi-sim]: LLM decomposition failed: {exc}")

        # Truncated JSON often omits combined fields; never drop combined work when
        # the user goal clearly requested it unless a complete JSON says otherwise.
        if default_combined:
            if decomposition_complete and parsed and (
                parsed.get("run_post_combined") is False
                or (
                    parsed.get("run_post_combined") is None
                    and parsed.get("run_combined_analysis") is False
                )
            ):
                run_post_combined = False
                run_combined_analysis = False
            else:
                run_post_combined = True
                run_combined_analysis = True
                if not post_combined_plan and not combined_plan:
                    post_combined_plan = _build_combined_analysis_plan_fallback(
                        state, expanded_entries
                    )
                    combined_plan = post_combined_plan
                    logger.info(
                        "PLANNER [multi-sim]: using post_combined fallback plan "
                        "(decomposition_complete=%s)",
                        decomposition_complete,
                    )

        if default_pre:
            if decomposition_complete and parsed and parsed.get("run_pre_combined") is False:
                run_pre_combined = False
            else:
                run_pre_combined = True
                if not pre_combined_plan:
                    pre_combined_plan = _build_pre_combined_plan_fallback(
                        state, expanded_entries
                    )
                    logger.info(
                        "PLANNER [multi-sim]: using pre_combined fallback plan "
                        "(decomposition_complete=%s)",
                        decomposition_complete,
                    )

        if not sim_prompts_list or len(sim_prompts_list) != len(expanded_entries):
            logger.info(
                "PLANNER [multi-sim]: Using compact deterministic prompt decomposition "
                f"(post_sim_subtask={post_sim_subtask}, n={len(expanded_entries)})"
            )
            shared_intent = _build_shared_per_sim_intent(
                original_goal=original_goal,
                enriched_prompt=enriched_prompt,
                agents_desc=agents_desc,
                post_sim_subtask=post_sim_subtask,
            )
            sim_prompts_list = []
            prompt_source = "deterministic_fallback"
            if post_sim_subtask:
                for entry in expanded_entries:
                    sim_prompts_list.append(
                        _build_compact_per_sim_prompt(
                            entry, shared_intent=shared_intent
                        )
                    )
            else:
                for entry in expanded_entries:
                    pdb_name = Path(entry["pdb"]).name
                    uniprot_hint = ""
                    structure_requests = state.get("structure_requests") or {}
                    uid_key = Path(entry["pdb"]).stem.lower()
                    req = structure_requests.get(uid_key)
                    if req and req.get("uniprot_id"):
                        src = req.get("structure_source", "auto")
                        uniprot_hint = (
                            f" Download structure from {src} for UniProt "
                            f"{req['uniprot_id']} if {pdb_name} is not present."
                        )
                    sim_prompts_list.append(
                        (
                            f"Simulation {entry['label']} ({entry['protein_name']}; "
                            f"{entry['case_description']}; source {pdb_name}; "
                            f"working directory {entry['working_dir']}). "
                            f"{entry['case_directive']}{uniprot_hint} "
                            f"{shared_intent.replace('{working_dir}', entry['working_dir'])}"
                        ).strip()
                    )

        if run_post_combined and not post_combined_plan:
            post_combined_plan = _build_combined_analysis_plan_fallback(
                state, expanded_entries
            )
        if run_pre_combined and not pre_combined_plan:
            pre_combined_plan = _build_pre_combined_plan_fallback(
                state, expanded_entries
            )
        if not run_post_combined:
            post_combined_plan = ""
        if not run_pre_combined:
            pre_combined_plan = ""
        combined_plan = post_combined_plan
        run_combined_analysis = run_post_combined

        sim_prompts = []
        for entry, prompt_text in zip(expanded_entries, sim_prompts_list):
            pdb = entry["pdb"]
            prompt_body = _coerce_plan_text(prompt_text, default="")
            if post_sim_subtask and not prompt_body.strip():
                prompt_body = _build_per_sim_analysis_prompt(
                    entry,
                    original_goal=original_goal,
                    enriched_prompt=enriched_prompt,
                    agents_desc=agents_desc,
                )
            prompt_body = append_sim_case_requirement(prompt_body, entry)
            sim_prompts.append(
                {
                    "pdb": str(Path(pdb).resolve()) if Path(pdb).exists() else pdb,
                    "label": entry["label"],
                    "prompt": prompt_body,
                    "analysis_prompt": prompt_body if post_sim_subtask else None,
                    "task_scope": "analysis_reporter" if post_sim_subtask else "full_pipeline",
                    "working_dir": entry["working_dir"],
                    "case_id": entry.get("case_id"),
                    "case_description": entry["case_description"],
                    "case_directive": entry.get("case_directive"),
                    "protein_name": entry.get("protein_name"),
                }
            )

        state["sim_prompts"] = sim_prompts
        # One simulation cannot have a meaningful cross-sim combined stage.
        if len(sim_prompts) <= 1:
            run_combined_analysis = False
            run_pre_combined = False
            run_post_combined = False
            combined_plan = ""
            pre_combined_plan = ""
            post_combined_plan = ""
        state["run_pre_combined"] = bool(run_pre_combined)
        state["pre_combined_plan"] = _coerce_plan_text(pre_combined_plan, default="")
        state["run_post_combined"] = bool(run_post_combined)
        state["post_combined_plan"] = _coerce_plan_text(post_combined_plan, default="")
        state["run_combined_analysis"] = bool(run_post_combined)
        state["combined_analysis_plan"] = _coerce_plan_text(post_combined_plan, default="")
        sync_combined_planner_flags(state)

        logger.info(
            f"PLANNER [multi-sim]: Master plan ready - {len(sim_prompts)} simulations, "
            f"labels: {[s['label'] for s in sim_prompts]}, "
            f"run_pre_combined={state.get('run_pre_combined')} "
            f"run_post_combined={state.get('run_post_combined')}"
        )
        log_agent_action(
            agent_name="planner",
            action="Generated Multi-Simulation Master Plan",
            details={
                "num_simulations": len(sim_prompts),
                "num_combined_prompts": 1 if state.get("run_post_combined") else 0,
                "labels": [s["label"] for s in sim_prompts],
                "prompt_source": prompt_source,
                "master_plan_path": str(
                    Path(base_working_dir) / "planner" / "master_plan.json"
                ),
                "component_cases": [c.get("description") for c in component_cases],
                "agents": agents_desc,
                "run_pre_combined": state.get("run_pre_combined"),
                "run_post_combined": state.get("run_post_combined"),
                "run_combined_analysis": state.get("run_combined_analysis"),
                "pre_combined_plan_chars": len(state.get("pre_combined_plan") or ""),
                "post_combined_plan_chars": len(state.get("post_combined_plan") or ""),
                "combined_plan_preview": (state.get("post_combined_plan") or "")[:500],
            },
        )
        self._save_multi_sim_master_plan(
            base_working_dir=base_working_dir,
            sim_prompts=sim_prompts,
            combined_plan=state.get("post_combined_plan") or "",
            enriched_prompt=enriched_prompt,
            agents_desc=agents_desc,
            run_combined_analysis=bool(state.get("run_post_combined")),
            run_pre_combined=bool(state.get("run_pre_combined")),
            pre_combined_plan=state.get("pre_combined_plan") or "",
            run_post_combined=bool(state.get("run_post_combined")),
            post_combined_plan=state.get("post_combined_plan") or "",
        )
        return state

    def _save_multi_sim_master_plan(
        self,
        *,
        base_working_dir: str,
        sim_prompts: List[Dict[str, Any]],
        combined_plan: str,
        enriched_prompt: str,
        agents_desc: str,
        run_combined_analysis: bool,
        run_pre_combined: bool = False,
        pre_combined_plan: str = "",
        run_post_combined: Optional[bool] = None,
        post_combined_plan: str = "",
    ) -> None:
        """Persist overall multi-simulation master plan to {base}/planner/."""
        if run_post_combined is None:
            run_post_combined = run_combined_analysis
        if not post_combined_plan:
            post_combined_plan = combined_plan or ""
        plan_data = {
            "title": "Multi-Simulation Master Plan",
            "format": "master_plan",
            "phase": "master",
            "workflow_pipeline": agents_desc,
            "task_scope": (
                "analysis_reporter"
                if any(s.get("task_scope") == "analysis_reporter" for s in sim_prompts)
                else "full_pipeline"
            ),
            "enriched_prompt": enriched_prompt,
            "shared_per_sim_intent": (
                (sim_prompts[0].get("prompt") or "").split("Shared per-simulation", 1)[-1]
                if sim_prompts and "Shared per-simulation" in (sim_prompts[0].get("prompt") or "")
                else None
            ),
            "sim_entries": [
                {
                    "label": s.get("label"),
                    "protein_name": s.get("protein_name"),
                    "pdb": s.get("pdb"),
                    "working_dir": s.get("working_dir"),
                    "case_description": s.get("case_description"),
                    "prompt_preview": ((s.get("prompt") or "")[:160]),
                }
                for s in sim_prompts
            ],
            "sim_prompts": sim_prompts,
            "run_pre_combined": bool(run_pre_combined),
            "pre_combined_plan": pre_combined_plan or "",
            "run_post_combined": bool(run_post_combined),
            "post_combined_plan": post_combined_plan or "",
            "run_combined_analysis": bool(run_post_combined),
            "num_combined_prompts": 1 if run_post_combined else 0,
            "combined_prompt": post_combined_plan or "",
            "combined_analysis_plan": post_combined_plan or "",
            "num_simulations": len(sim_prompts),
            "labels": [s.get("label") for s in sim_prompts],
        }

        ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        # Compact master plan: one shared intent + table of sims (avoid N× copy-paste).
        case_descs = sorted(
            {
                str(s.get("case_description") or "default")
                for s in sim_prompts
            }
        )
        shared_template = ""
        if sim_prompts:
            sample = _coerce_plan_text(sim_prompts[0].get("prompt"), default="")
            # Prefer a short shared synopsis over repeating full prompts.
            shared_template = (
                f"For each simulation label below, run the same pipeline ({agents_desc}) "
                f"using that label's PDB / working directory and case directive. "
                f"Cases in this campaign: {', '.join(case_descs)}."
            )
            if len(sim_prompts) <= 12 and sample:
                shared_template += f"\n\nExample per-sim wording:\n{sample}"

        md_lines = [
            "# Multi-Simulation Master Plan",
            "",
            f"**Generated:** {ts}",
            f"**Simulations:** {len(sim_prompts)}",
            f"**Pipeline:** {agents_desc}",
            f"**Task scope:** {plan_data.get('task_scope', 'full_pipeline')}",
            f"**Pre-combined (before traj):** {'yes' if run_pre_combined else 'no'}",
            f"**Post-combined (after all sims):** {'yes' if run_post_combined else 'no'}",
            f"**Combined analysis requested (legacy=post):** {'yes' if run_post_combined else 'no'}",
            "",
            "## Overall Goal",
            "",
            enriched_prompt or "_N/A_",
            "",
            "## Shared per-simulation intent",
            "",
            shared_template or "_N/A_",
            "",
            "## Simulation inventory",
            "",
            "| # | Label | Protein | PDB | Case | Directory |",
            "|---|-------|---------|-----|------|-----------|",
        ]
        for idx, sim in enumerate(sim_prompts, 1):
            pdb_name = Path(str(sim.get("pdb") or "")).name or str(sim.get("pdb") or "N/A")
            md_lines.append(
                "| {idx} | {label} | {protein} | {pdb} | {case} | `{dir}` |".format(
                    idx=idx,
                    label=sim.get("label", f"sim_{idx}"),
                    protein=sim.get("protein_name") or "",
                    pdb=pdb_name,
                    case=sim.get("case_description", "N/A"),
                    dir=sim.get("working_dir", "N/A"),
                )
            )
        md_lines += [
            "",
            "## Pre-Combined Plan (before per-sim traj analysis)",
            "",
            _coerce_plan_text(
                pre_combined_plan,
                default="_Not requested — skip pre_combined stage._",
            ),
            "",
            "## Post-Combined Plan (after all per-sim analysis+reporter)",
            "",
            _coerce_plan_text(
                post_combined_plan or combined_plan,
                default="_Not requested by the user goal._",
            ),
        ]

        save_plan_artifacts(
            base_working_dir,
            "planner",
            json_filename="master_plan.json",
            md_filename="master_plan.md",
            history_filename="execution_plans.jsonl",
            plan_data=plan_data,
            md_content="\n".join(md_lines),
            phase="master",
            label="overall",
        )

    def _extract_json_from_response(self, response: str) -> Optional[Dict[str, Any]]:
        """Extract JSON from an LLM response; salvage truncated multi-sim decomposition."""
        text = _strip_markdown_json_fence(response)
        start = text.find("{")
        if start != -1:
            depth = 0
            for idx, char in enumerate(text[start:], start):
                if char == "{":
                    depth += 1
                elif char == "}":
                    depth -= 1
                    if depth == 0:
                        try:
                            return json.loads(text[start: idx + 1])
                        except json.JSONDecodeError:
                            break

        salvaged_prompts = _salvage_sim_prompts_from_response(response)
        if not salvaged_prompts:
            return None

        text_lower = text.lower()
        run_combined = None
        if re.search(r'"run_combined_analysis"\s*:\s*true', text_lower):
            run_combined = True
        elif re.search(r'"run_combined_analysis"\s*:\s*false', text_lower):
            run_combined = False
        combined_plan = ""
        plan_match = re.search(
            r'"combined_analysis_plan"\s*:\s*"((?:[^"\\]|\\.)*)"',
            text,
            re.DOTALL,
        )
        if plan_match:
            try:
                combined_plan = json.loads(f'"{plan_match.group(1)}"')
            except json.JSONDecodeError:
                combined_plan = plan_match.group(1)

        logger.info(
            "PLANNER: salvaged %d sim_prompts from truncated LLM JSON",
            len(salvaged_prompts),
        )
        return {
            "sim_prompts": salvaged_prompts,
            "run_combined_analysis": run_combined,
            "combined_analysis_plan": combined_plan,
        }
    
    def planner_node(self, state: MDState) -> MDState:
        """Main planner node - creates execution plan from structured prompt.
        
        In multi-simulation mode on the first call (sim_prompts not yet set),
        this generates a *master plan* that includes per-simulation prompts
        and a combined analysis plan.  Subsequent per-sim calls proceed normally.
        """
        
        logger.info("=" * 60)
        logger.info("PLANNER: Creating execution plan from structured prompt")
        logger.info("=" * 60)

        # Per-sim execution plans belong in {label}/agent_conversation.log.
        # Master-plan creation (create_multi_sim_master_plan) stays on the base log.
        base = state.get("multi_sim_base_dir")
        wd = state.get("working_directory")
        if (
            state.get("is_multi_simulation")
            and state.get("sim_prompts")
            and base
            and wd
            and Path(wd).resolve() != Path(base).resolve()
        ):
            from ..utils.conversation_logger import set_log_file

            Path(wd).mkdir(parents=True, exist_ok=True)
            set_log_file(str(Path(wd) / "agent_conversation.log"))
        
        # CRITICAL: Refresh tools registry to pick up any newly generated programmer tools
        working_dir = state.get("working_directory")
        self.tools_registry = get_tools_registry(refresh=True, working_directory=working_dir)
        logger.info(f"PLANNER: Refreshed tools registry - now {len(self.tools_registry.tools)} tools available")
        
        # Use structured prompt if available, otherwise fall back to rephrased/original goal
        structured_prompt = state.get("enriched_prompt") or state.get("rephrased_goal") or state.get("user_goal", "")
        pdb_path = state.get("raw_pdb", "")
        pdb_analysis = _coerce_pdb_analysis(state.get("pdb_analysis"))
        component_selection = state.get("component_selection") or {}
        
        logger.info(f"PLANNER: Using structured prompt: {structured_prompt[:100]}...")

        # Create plan from structured prompt and PDB analysis
        plan = self._create_plan_from_analysis(
            structured_prompt, 
            pdb_path, 
            pdb_analysis,
            component_selection,
            state
        )
        
        # Store in state
        state["execution_plan"] = plan
        state["current_step"] = 0  # Initialize step counter
        state["next_node"] = "supervisor"
        
        # All plans are now natural language format
        agent_sequence = plan.get("agent_sequence", [])
        num_agents = len(agent_sequence)
        logger.info(f"PLANNER: Created natural language plan with {num_agents} agents: {agent_sequence}")
        
        # Log detailed plan to conversation log
        from ..utils import log_agent_action
        
        plan_preview = plan.get("full_plan", "")[:500]
        plan_details = {
            "format": "natural_language",
            "title": plan.get("title", "N/A"),
            "agent_sequence": agent_sequence,
            "total_agents": num_agents,
            "plan_preview": plan_preview + ("..." if len(plan.get("full_plan", "")) > 500 else ""),
            "method": plan.get("method", "llm_generated")
        }
        
        log_agent_action(
            agent_name="planner",
            action="Generated Natural Language Execution Plan",
            details=plan_details
        )
        
        # Log routing
        log_supervisor_routing(
            state, 
            "supervisor",
            f"Planner: Created natural language plan with {num_agents} agents. Returning to supervisor."
        )

        self._save_execution_plan(plan, state)
        
        return state

    def _save_execution_plan(self, plan: Dict[str, Any], state: MDState) -> None:
        """Persist execution plan under {working_directory}/planner/."""
        working_dir = state.get("working_directory") or "working_dir"
        phase = self._resolve_plan_phase(state)
        label = self._resolve_plan_label(state)

        plan_data = {
            "title": plan.get("title", "Execution Plan"),
            "format": plan.get("format", "natural_language"),
            "method": plan.get("method"),
            "subtask_type": state.get("subtask_type"),
            "agent_sequence": plan.get("agent_sequence", []),
            "agent_plans": plan.get("agent_plans", {}),
            "steps": plan.get("steps", []),
            "full_plan": plan.get("full_plan", ""),
            "user_goal": state.get("user_goal"),
            "enriched_prompt": state.get("enriched_prompt") or state.get("rephrased_goal"),
            "is_multi_simulation": state.get("is_multi_simulation", False),
            "multi_sim_phase": state.get("multi_sim_phase"),
            "multi_sim_base_dir": state.get("multi_sim_base_dir"),
        }

        full_plan = plan.get("full_plan", "")
        agent_seq = plan.get("agent_sequence", [])
        ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        md_lines = [
            "# Planner Execution Plan",
            "",
            f"**Generated:** {ts}",
            f"**Phase:** {phase or 'single'}",
        ]
        if label:
            md_lines.append(f"**Simulation:** {label}")
        md_lines += [
            "",
            f"## Overview",
            "",
            f"**Title:** {plan_data['title']}",
            f"**Agent sequence:** {' → '.join(agent_seq) if agent_seq else 'N/A'}",
            f"**Subtask:** {state.get('subtask_type') or 'full_task'}",
            "",
            "## Full Plan",
            "",
            full_plan or "_No plan text available._",
        ]

        save_plan_artifacts(
            working_dir,
            "planner",
            json_filename="execution_plan.json",
            md_filename="execution_plan.md",
            history_filename="execution_plans.jsonl",
            plan_data=plan_data,
            md_content="\n".join(md_lines),
            phase=phase,
            label=label,
        )

    def _resolve_plan_phase(self, state: MDState) -> Optional[str]:
        """Classify which planning phase produced this plan."""
        if not state.get("is_multi_simulation"):
            return "single"
        multi_phase = state.get("multi_sim_phase")
        if multi_phase == "pre_combined":
            return "pre_combined"
        if multi_phase in ("combined_analysis", "post_combined"):
            return "combined_analysis"
        if multi_phase == "executing_sims":
            return "per_simulation"
        if (
            state.get("post_combined_plan")
            or state.get("combined_analysis_plan")
        ) and not state.get("execution_plan"):
            return "combined_analysis"
        return "per_simulation"

    def _resolve_plan_label(self, state: MDState) -> Optional[str]:
        """Return per-simulation label when running inside the multi-sim loop."""
        if not state.get("is_multi_simulation"):
            return None
        phase = state.get("multi_sim_phase")
        if phase in ("combined_analysis", "post_combined", "pre_combined", "combined_reporter"):
            return "combined"
        sim_prompts = state.get("sim_prompts") or []
        current_idx = state.get("current_sim_index", 0)
        if 0 <= current_idx < len(sim_prompts):
            return sim_prompts[current_idx].get("label")
        return Path(state.get("working_directory", "")).name or None
    
    def _create_plan_from_analysis(
        self,
        structured_prompt: str,
        pdb_path: str,
        pdb_analysis: Dict[str, Any],
        component_selection: Dict[str, Any],
        state: MDState
    ) -> Dict[str, Any]:
        """
        Create detailed execution plan based on PDB analysis and component selection.
        
        CRITICAL: Respects subtask-specific workflows (analysis-only, setup-only, etc.)
        Uses dynamic tools knowledge and domain knowledge to create comprehensive plans.
        """
        pdb_analysis = _coerce_pdb_analysis(pdb_analysis)
        component_selection = component_selection or {}
        logger.info("PLANNER: Creating plan with dynamic tools and knowledge")
        
        # HPC pool prep: preprocess + simsetup only — never analysis/HPC/programmer tools.
        if state.get("hpc_pool_prep_only"):
            subtask_type = "multi_agent"
            state["subtask_type"] = subtask_type
            state["agent_list"] = ["preprocess", "simsetup"]
            logger.info("PLANNER [hpc_pool]: Forcing prep-only plan (preprocess + simsetup)")
        else:
            subtask_type = state.get("subtask_type")
        if subtask_type:
            logger.info(f"PLANNER: Planning for subtask type: {subtask_type}")
        
        # Get available tools context - agent-specific for subtask workflows
        exclude_combined = self._should_exclude_combined_tools(state)
        if subtask_type == "analysis_only":
            logger.info("PLANNER: Getting analysis agent tools for analysis-only workflow")
            tools_context = self._get_tools_context(
                agent_name="analysis",
                exclude_combined_tools=exclude_combined,
            )
        elif subtask_type == "setup_only":
            logger.info("PLANNER: Getting setup agent tools for setup-only workflow")
            tools_context = self._get_tools_context(agent_name="simsetup")
        elif subtask_type == "preprocess_only":
            logger.info("PLANNER: Getting preprocessing agent tools for preprocess-only workflow")
            tools_context = self._get_tools_context(agent_name="preprocess")
        elif subtask_type == "reporter_only":
            logger.info("PLANNER: Getting reporter agent tools for reporter-only workflow")
            tools_context = self._get_tools_context(agent_name="reporter")
        elif subtask_type == "multi_agent":
            agent_list = state.get("agent_list") or []
            logger.info(f"PLANNER: Getting combined tools for multi-agent workflow: {agent_list}")
            logger.info(f"PLANNER: DEBUG - subtask_type={subtask_type}, agent_list from state={agent_list}")
            tools_context = self._get_combined_tools_context(
                agent_list,
                exclude_combined_tools=exclude_combined,
            )
            logger.info(f"PLANNER: DEBUG - tools_context length: {len(tools_context)} chars")
            # Log first few lines to see what agents are included
            tools_lines = tools_context.split('\n')[:10]
            logger.info(f"PLANNER: DEBUG - First 10 lines of tools_context:\n" + "\n".join(tools_lines))
        else:
            # Full workflow - get all tools
            tools_context = self._get_tools_context(exclude_combined_tools=exclude_combined)
        
        # Get relevant knowledge (protocols and force fields)
        knowledge_context = self._get_knowledge_context(max_chars=6000)
        
        # Build LLM prompt with all context - INCLUDE subtask type info
        planning_prompt = self._build_planning_prompt(
            structured_prompt,
            pdb_path,
            pdb_analysis,
            component_selection,
            state,
            tools_context,
            knowledge_context,
            subtask_type=subtask_type  # Pass subtask type to prompt
        )
        
        # Call LLM to create plan (with potential tool creation iteration)
        plan = self._create_plan_with_tool_creation(
            planning_prompt,
            structured_prompt,
            pdb_path,
            pdb_analysis,
            component_selection,
            state,
            tools_context,
            knowledge_context,
            subtask_type
        )
        
        return plan
    
    def _create_plan_with_tool_creation(
        self,
        initial_prompt: str,
        structured_prompt: str,
        pdb_path: str,
        pdb_analysis: Dict[str, Any],
        component_selection: Dict[str, Any],
        state: MDState,
        tools_context: str,
        knowledge_context: str,
        subtask_type: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Create plan with automatic tool creation if LLM indicates tools are missing.
        
        Workflow:
        1. Ask LLM to create plan
        2. Check if LLM indicates missing tools
        3. If missing: Generate tool specs → Invoke programmer → Retry planning
        4. Return final plan
        
        Args:
            initial_prompt: Initial planning prompt
            structured_prompt: User's structured goal
            pdb_path: Path to PDB file
            pdb_analysis: PDB analysis results
            component_selection: Component selection
            state: Current workflow state
            tools_context: Available tools context
            knowledge_context: Knowledge base context
            subtask_type: Type of subtask (if any)
            
        Returns:
            Complete execution plan
        """
        tool_creation_enabled = (
            self.config.get("planner", {}).get("behavior", {}).get("enable_tool_creation", True)
            and not state.get("hpc_pool_prep_only")
        )
        max_iterations = self.config.get("planner", {}).get("behavior", {}).get("max_tool_creation_iterations", 2)
        
        current_prompt = initial_prompt
        current_tools_context = tools_context
        
        for iteration in range(max_iterations + 1):  # +1 for initial attempt
            # Call LLM to create plan
            try:
                logger.info(f"PLANNER: Creating execution plan (iteration {iteration + 1}/{max_iterations + 1})...")
                response = self.llm.prompt_raw(
                    prompt=current_prompt,
                    temperature=0.2,
                    max_tokens=2000
                )
                
                log_llm_interaction(
                    agent_name="planner.execution_planning",
                    prompt=current_prompt,
                    response=response
                )

                if _is_mock_or_error_llm_response(response):
                    logger.warning(
                        "PLANNER: LLM returned mock/error during execution planning; "
                        "using fallback natural-language plan"
                    )
                    return self._create_fallback_plan(
                        structured_prompt, pdb_path, pdb_analysis, component_selection, state
                    )
                
                # Check if LLM indicates missing tools
                if tool_creation_enabled and iteration < max_iterations:
                    missing_tools_detected, tool_needs = self._detect_missing_tools_in_response(response)
                    
                    if missing_tools_detected:
                        existing_names = self._get_existing_tool_names(state)
                        claimed_metrics = detect_requested_metrics(tool_needs) or frozenset()
                        covered, genuinely_missing = partition_metrics_by_registry(
                            claimed_metrics, existing_names
                        )

                        if claimed_metrics and not genuinely_missing:
                            from ..utils import log_agent_action
                            logger.info(
                                "PLANNER: LLM claimed missing tools for %s but registry "
                                "already covers them (%s); skipping programmer",
                                sorted(claimed_metrics),
                                sorted(covered),
                            )
                            log_agent_action(
                                agent_name="planner",
                                action="Skipped Programmer (tools already in registry)",
                                details={
                                    "claimed_metrics": sorted(claimed_metrics),
                                    "covered_by": sorted(covered),
                                },
                            )
                            metric_ref = get_planner_metric_tool_reference(claimed_metrics)
                            current_prompt = (
                                current_prompt
                                + "\n\nIMPORTANT: The following metrics ARE already covered "
                                "by built-in tools in the registry. Do NOT declare them "
                                "missing or request programmer tool creation:\n"
                                + metric_ref
                                + "\n\nOutput the execution plan ONLY — no missing-tool "
                                "declarations for the metrics above."
                            )
                            continue

                        logger.info(f"PLANNER: LLM indicates missing tools: {tool_needs}")
                        if genuinely_missing:
                            logger.info(
                                "PLANNER: Genuinely missing metrics (registry): %s",
                                sorted(genuinely_missing),
                            )
                        logger.info("PLANNER: Invoking programmer to create needed tools...")
                        
                        # Generate tool specifications via LLM
                        tool_specs = self._generate_tool_specifications(tool_needs, state)
                        
                        if not tool_specs:
                            from ..utils import log_agent_action
                            logger.info(
                                "PLANNER: Tool specification returned empty — no new tools "
                                "needed; retrying plan with registry confirmation"
                            )
                            log_agent_action(
                                agent_name="planner",
                                action="Skipped Programmer (empty tool specs)",
                                details={"tool_needs_excerpt": (tool_needs or "")[:300]},
                            )
                            current_prompt = (
                                current_prompt
                                + "\n\nIMPORTANT: Tool specification confirmed all required "
                                "capabilities already exist in the tools list above. "
                                "Do NOT declare missing tools. Output the execution plan only."
                            )
                            continue

                        # Invoke programmer directly (not through supervisor)
                        programmer_result = self._invoke_programmer_for_tools(tool_specs, state)
                        
                        if programmer_result.get("success"):
                            logger.info("PLANNER: Programmer successfully created tools. Recreating tools context...")
                            
                            # Refresh tools registry to include new tools
                            self.tools_registry.discover_all_tools()
                            
                            # Rebuild tools context with new tools
                            exclude_combined = self._should_exclude_combined_tools(state)
                            if subtask_type == "analysis_only":
                                current_tools_context = self._get_tools_context(
                                    agent_name="analysis",
                                    exclude_combined_tools=exclude_combined,
                                )
                            elif subtask_type == "setup_only":
                                current_tools_context = self._get_tools_context(agent_name="simsetup")
                            elif subtask_type == "preprocess_only":
                                current_tools_context = self._get_tools_context(agent_name="preprocess")
                            elif subtask_type == "reporter_only":
                                current_tools_context = self._get_tools_context(agent_name="reporter")
                            elif subtask_type == "multi_agent":
                                # Get combined tools context for multi-agent workflow
                                agent_list = state.get("agent_list") or []
                                logger.info(f"PLANNER: Rebuilding tools context for multi-agent workflow: {agent_list}")
                                current_tools_context = self._get_combined_tools_context(
                                    agent_list,
                                    exclude_combined_tools=exclude_combined,
                                )
                            else:
                                # Full workflow - get all tools
                                current_tools_context = self._get_tools_context(
                                    exclude_combined_tools=exclude_combined,
                                )
                            
                            # Rebuild prompt with updated tools
                            current_prompt = self._build_planning_prompt(
                                structured_prompt,
                                pdb_path,
                                pdb_analysis,
                                component_selection,
                                state,
                                current_tools_context,
                                knowledge_context,
                                subtask_type=subtask_type,
                                include_new_tools_note=True
                            )
                            
                            logger.info("PLANNER: Retrying plan creation with new tools...")
                            continue  # Retry planning with new tools
                        else:
                            logger.warning("PLANNER: Programmer failed to create tools. Proceeding with available tools.")
                
                # Parse LLM response into structured plan
                plan = self._parse_llm_plan_response(response, state)
                
                # If LLM response was not a valid plan, use fallback
                if plan is None:
                    logger.warning("PLANNER: LLM response not suitable - using fallback plan")
                    plan = self._create_fallback_plan(
                        structured_prompt, pdb_path, pdb_analysis, component_selection, state
                    )
                
                return plan
                
            except Exception as e:
                logger.error(f"PLANNER: LLM planning failed: {e}", exc_info=True)
                if iteration == max_iterations:
                    logger.warning("PLANNER: Max iterations reached. Falling back to template-based planning")
                    return self._create_fallback_plan(
                        structured_prompt, pdb_path, pdb_analysis, component_selection, state
                    )
        
        # Should not reach here, but return fallback just in case
        return self._create_fallback_plan(
            structured_prompt, pdb_path, pdb_analysis, component_selection, state
        )

    def _detect_missing_tools_in_response(self, llm_response: str) -> tuple[bool, str]:
        """
        Detect if LLM response indicates missing tools.
        
        Looks for keywords like "missing tool", "need to create", etc.
        
        Args:
            llm_response: LLM's planning response
            
        Returns:
            Tuple of (missing_detected: bool, tool_needs: str)
        """
        indicators = self.config.get("planner", {}).get("tool_creation", {}).get("missing_tool_indicators", [
            "missing tool",
            "tool not available",
            "need to create",
            "require custom tool",
            "no existing tool",
            "should generate",
            "programmer should create"
        ])
        
        response_lower = llm_response.lower()
        
        for indicator in indicators:
            if indicator.lower() in response_lower:
                # Extract context around the indicator
                import re
                # Find sentences containing the indicator
                sentences = re.split(r'[.!?]\s+', llm_response)
                relevant_sentences = [s for s in sentences if indicator.lower() in s.lower()]
                
                tool_needs = " ".join(relevant_sentences) if relevant_sentences else llm_response[:500]
                
                logger.info(f"PLANNER: Detected missing tool indicator: '{indicator}'")
                logger.debug(f"PLANNER: Tool needs context: {tool_needs}")
                
                return True, tool_needs
        
        return False, ""
    
    def _get_existing_tool_names(self, state: MDState) -> set:
        """
        Collect names of all tools already available to the relevant agents.
        
        Returns:
            Set of existing tool names (lowercase for comparison)
        """
        existing = set()
        
        # Determine which agents are involved
        agent_list = state.get("agent_list") or []
        subtask_type = state.get("subtask_type", "")
        
        if not agent_list:
            # Infer from subtask_type
            type_to_agent = {
                "analysis_only": ["analysis"],
                "setup_only": ["simsetup"],
                "preprocess_only": ["preprocess"],
                "hpc_only": ["hpc"],
                "reporter_only": ["reporter"],
            }
            agent_list = type_to_agent.get(subtask_type, [])
        
        # Collect tool names from all relevant agents
        for agent_name in agent_list:
            tools = self.tools_registry.get_tools_for_agent(agent_name)
            for tool in tools:
                existing.add(tool["name"].lower())
        
        # Also include all tools across registry as a safety net
        for tool_key, tool_meta in self.tools_registry.tools.items():
            existing.add(tool_meta["name"].lower())
        
        return existing

    def _generate_tool_specifications(self, tool_needs: str, state: MDState) -> List[Dict[str, Any]]:
        """
        Generate detailed tool specifications via LLM for programmer.
        Only generates specs for tools NOT already available in the agent tool registry.
        
        Args:
            tool_needs: Description of what tools are needed
            state: Current workflow state
            
        Returns:
            List of tool specifications (filtered to exclude existing tools)
        """
        if not self.llm.available:
            logger.warning("PLANNER: LLM unavailable for tool specification generation")
            return []
        
        logger.info("PLANNER: Generating tool specifications via LLM...")
        
        # Collect existing tool names to prevent redundant specs
        existing_tool_names = self._get_existing_tool_names(state)
        existing_tools_list = ", ".join(sorted(existing_tool_names)) if existing_tool_names else "None"
        logger.info(f"PLANNER: Existing tools ({len(existing_tool_names)}): {existing_tools_list}")
        
        spec_prompt = f"""You are a molecular dynamics workflow expert tasked with specifying custom tools that need to be created.

**CONTEXT:**
The planner has identified that existing tools are insufficient. Here's what's needed:

{tool_needs}

**WORKFLOW CONTEXT:**
- User Goal: {state.get('user_goal', 'Not specified')}
- Force Field: {state.get('force_field', 'amber99sb-ildn')}
- MD Engine: {state.get('md_engine', 'gromacs')}

**ALREADY AVAILABLE TOOLS (DO NOT CREATE SPECS FOR THESE):**
{existing_tools_list}

**CRITICAL RULE:**
- ONLY create specifications for tools that are genuinely MISSING
- Do NOT create specs for any tool listed above as already available
- If a tool like calculate_rmsd, calculate_rmsf, plot_md_data etc. already exists, do NOT include it
- Only spec the specific missing functionality described in the CONTEXT above

**YOUR TASK:**
Create detailed specifications ONLY for the missing tools/scripts. For each tool, specify:

1. **name**: A descriptive function/script name (snake_case)
2. **description**: Brief one-line description of what the tool does
3. **language**: python or tcl
4. **purpose**: Detailed explanation of what problem this tool solves and how
5. **parameters**: What inputs does it need? (name, type, description, default)
6. **return_type**: What type of value it returns (default: "Dict[str, Any]")
7. **dependencies**: Required imports/modules (list of strings)
8. **examples**: Optional usage examples

**OUTPUT FORMAT (JSON array):**
```json
[
  {{
    "name": "custom_analysis_function",
    "description": "Calculate specific metric from trajectory",
    "language": "python",
    "purpose": "This tool analyzes MD trajectories to compute a specific metric over time. It processes each frame, calculates the metric, and saves results to a file for plotting and analysis.",
    "parameters": {{
      "trajectory": {{"type": "str", "description": "Path to .xtc trajectory file"}},
      "topology": {{"type": "str", "description": "Path to .tpr/.gro topology file"}},
      "output_file": {{"type": "str", "description": "Output CSV/DAT file path"}}
    }},
    "return_type": "Dict[str, Any]",
    "dependencies": ["MDAnalysis", "numpy", "pandas"],
    "examples": "result = custom_analysis_function('traj.xtc', 'topol.gro', 'output.csv')\\n# Result contains path to output file"
  }}
]
```

**IMPORTANT:** The "examples" field should be a single string (not an array). Use \\n for multiple lines if needed.
**IMPORTANT:** Return an EMPTY array [] if all needed tools already exist.

Generate tool specifications now (ONLY for missing tools):"""
        
        try:
            response = self.llm.prompt_raw(spec_prompt, temperature=0.1, max_tokens=1500, format="json")
            
            log_llm_interaction(
                agent_name="planner.tool_specification",
                prompt=spec_prompt,
                response=response
            )
            
            # Parse JSON response
            import json
            import re
            
            # Extract JSON array
            json_match = re.search(r'\[[\s\S]*\]', response)
            if json_match:
                specs = json.loads(json_match.group())
                logger.info(f"PLANNER: LLM generated {len(specs)} tool specifications")
                
                # Post-filter: remove any specs that match existing tool names
                filtered_specs = []
                for spec in specs:
                    spec_name = spec.get("name", "").lower()
                    if spec_name in existing_tool_names:
                        logger.info(f"PLANNER: Filtered out redundant tool spec '{spec.get('name')}' - already exists")
                    else:
                        filtered_specs.append(spec)
                
                if len(filtered_specs) < len(specs):
                    logger.info(f"PLANNER: Filtered {len(specs) - len(filtered_specs)} redundant specs, "
                              f"keeping {len(filtered_specs)} genuinely missing tools")
                
                return filtered_specs
            else:
                logger.warning("PLANNER: Could not parse tool specifications from LLM response")
                return []
                
        except Exception as e:
            logger.error(f"PLANNER: Tool specification generation failed: {e}")
            return []
    
    def _invoke_programmer_for_tools(
        self, 
        tool_specs: List[Dict[str, Any]], 
        state: MDState
    ) -> Dict[str, Any]:
        """
        Directly invoke programmer agent to create specified tools.
        
        This bypasses the supervisor and directly calls programmer.programmer_node().
        
        Args:
            tool_specs: List of tool specifications from LLM
            state: Current workflow state
            
        Returns:
            Programmer result with success status and created tools
        """
        if not tool_specs:
            logger.warning("PLANNER: No tool specifications provided to programmer")
            return {"success": False, "error": "No specifications"}
        
        logger.info(f"PLANNER: Invoking programmer to create {len(tool_specs)} tools...")
        
        # Prepare programmer instructions from tool specs
        instructions_parts = []
        for spec in tool_specs:
            tool_name = spec.get("name", "unknown_tool")
            language = spec.get("language", "python")
            description = spec.get("description", "")
            purpose = spec.get("purpose", "")
            params = spec.get("parameters", {})
            
            instructions_parts.append(
                f"**Tool: {tool_name} ({language})**\n"
                f"Description: {description}\n"
                f"Purpose: {purpose}\n"
                f"Parameters: {', '.join(params.keys()) if params else 'None'}\n"
            )
        
        programmer_instructions = "\n\n".join(instructions_parts)
        
        # Normalize tool specifications - convert examples from list to string
        # The programmer expects examples as a string, but LLM often returns it as a list
        normalized_specs = []
        for spec in tool_specs:
            spec_copy = spec.copy()
            if "examples" in spec_copy and isinstance(spec_copy["examples"], list):
                # Join list examples with newlines
                spec_copy["examples"] = "\n".join(spec_copy["examples"])
                logger.debug(f"PLANNER: Converted examples list to string for tool '{spec_copy.get('name')}'")
            normalized_specs.append(spec_copy)
        
        # Store in state for programmer
        state["programmer_instructions"] = programmer_instructions
        state["tool_specifications"] = normalized_specs
        
        # Log programmer invocation
        from ..utils import log_agent_action
        log_agent_action(
            agent_name="planner",
            action="Invoking Programmer Agent",
            details={
                "tool_count": len(tool_specs),
                "tools": [spec.get("name") for spec in tool_specs],
                "bypass_supervisor": True
            }
        )
        
        try:
            # Directly call programmer node (bypass supervisor)
            updated_state = self.programmer.programmer_node(state)
            
            # Extract programmer result
            programmer_output = updated_state.get("programmer_output", {})
            
            result = {
                "success": programmer_output.get("success", False),
                "generated_tools": programmer_output.get("generated_tools", []),
                "tools_available": programmer_output.get("tools_available", {}),
                "output_directory": programmer_output.get("output_directory", ""),
                "errors": programmer_output.get("errors", [])
            }
            
            if result["success"]:
                logger.info(f"PLANNER: Programmer created {len(result['generated_tools'])} tools successfully")
                log_agent_action(
                    agent_name="planner",
                    action="Programmer Completed",
                    details={
                        "tools_created": [t.get("name") for t in result["generated_tools"]],
                        "status": "✅ SUCCESS"
                    }
                )
            else:
                logger.warning(f"PLANNER: Programmer failed or incomplete: {result['errors']}")
                log_agent_action(
                    agent_name="planner",
                    action="Programmer Failed",
                    details={
                        "errors": result["errors"],
                        "status": "❌ FAILED"
                    }
                )
            
            return result
            
        except Exception as e:
            logger.error(f"PLANNER: Programmer invocation failed: {e}", exc_info=True)
            return {
                "success": False,
                "error": str(e),
                "generated_tools": [],
                "tools_available": {}
            }
    
    def _get_nl_format_instructions(
        self,
        subtask_type: Optional[str],
        state: MDState,
        user_goal: str = "",
    ) -> str:
        """Natural-language plan format rules; analysis workflows add intent preservation."""
        goal_text = user_goal or state.get("user_goal_original") or state.get("user_goal") or ""
        agent_list = state.get("agent_list") or []
        analysis_in_scope = (
            subtask_type == "analysis_only"
            or (
                subtask_type == "multi_agent"
                and "analysis" in agent_list
            )
        )

        scope_line = (
            "- Match the USER GOAL scope exactly — do not add unrequested analyses or agents"
            if analysis_in_scope
            else "- Be comprehensive and explanatory"
        )
        closing = (
            "Provide a minimal natural language plan that matches the USER GOAL scope exactly."
            if analysis_in_scope
            else "Provide a comprehensive natural language plan explaining the workflow."
        )

        instructions = f"""**OUTPUT FORMAT - MANDATORY:**

You MUST provide your execution plan in NATURAL LANGUAGE format ONLY.

✓ DO:
- Write a detailed prose description of the execution plan
- Organize into clear sections (Goal, Analysis, Execution Sequence, Expected Outcomes)
- Explain which agents to use and why (use agent names explicitly!)
- Describe what each agent should do in detail
- Reference specific tools agents should consider using
- Write in complete sentences and paragraphs
{scope_line}

✗ DO NOT:
- Use JSON format (CRITICAL: No curly braces {{}}, no key-value pairs)
- Use YAML format
- Use structured data formats
- Create step-by-step numbered lists without context
- Write bullet points without explanation
- Use schemas or templates
- Output command sequences or file contents directly
- Invoke run_complete_analysis or wrap_trajectory unless the USER GOAL explicitly requires them

Write your plan as if explaining the workflow to another expert in molecular dynamics.
Be thorough, clear, and provide reasoning for your decisions.

CRITICAL: If you output JSON, YAML, or any structured format, the plan will be rejected and the workflow will fail.

{closing}"""

        if analysis_in_scope:
            instructions += (
                "\n\n"
                + get_intent_preservation_block(goal_text)
                + "\n\n"
                + get_standard_output_filenames_block()
                + "\n\n"
                + get_com_distance_tool_guide()
                + "\n\n"
                + get_proximity_tool_guide()
            )
        return instructions

    def _build_planning_prompt(
        self,
        structured_prompt: str,
        pdb_path: str,
        pdb_analysis: Dict[str, Any],
        component_selection: Dict[str, Any],
        state: MDState,
        tools_context: str,
        knowledge_context: str,
        subtask_type: Optional[str] = None,
        include_new_tools_note: bool = False
    ) -> str:
        """Build planning prompt for execution plan creation."""
        pdb_analysis = _coerce_pdb_analysis(pdb_analysis)
        component_selection = component_selection or {}
        
        per_sim_scope_note = self._get_per_sim_scope_note(state)
        user_goal_text = structured_prompt or state.get("user_goal") or ""
        if state.get("hpc_pool_prep_only"):
            working_dir = state.get("working_directory", ".")
            return f"""Create a detailed natural language execution plan for MD preprocessing and simulation setup ONLY.

USER GOAL:
{structured_prompt}

PDB File: {pdb_path}
Working Directory: {working_dir}

TASK: HPC-pool prep phase — run ONLY Preprocessing Agent then Setup Agent.
DO NOT include HPC, Analysis, or Reporter agents.
DO NOT plan trajectory analysis, RMSF, SASA, DCCM, or any post-simulation metrics.
DO NOT reference other simulations or their trajectories.
DO NOT request programmer tool creation.

**Available Preprocessing Agent Tools:**
{self._get_tools_context(agent_name="preprocess")}

**Available Setup Agent Tools:**
{self._get_tools_context(agent_name="simsetup")}

{per_sim_scope_note}

**CRITICAL:**
- All outputs must be written under {working_dir}/preprocess/ and {working_dir}/simsetup/
- End with simsetup producing system.gro, topol.top, and production MDP files
- No SLURM submission

{self._get_nl_format_instructions("multi_agent", state, user_goal=user_goal_text)}"""

        nl_format_instructions = self._get_nl_format_instructions(
            subtask_type, state, user_goal=user_goal_text
        )
        
        if subtask_type == "analysis_only":
            working_dir = state.get("working_directory", ".")
            return f"""Create a detailed natural language execution plan for trajectory analysis.

USER GOAL:
{structured_prompt}

**Available Files:**
Topology: {working_dir}/hpc/md.gro
Trajectory: {working_dir}/hpc/md.xtc
Energy: {working_dir}/hpc/md.edr
HPC Output Directory: {working_dir}/hpc

TASK: Analysis-only - perform trajectory analysis on existing simulation data.
DO NOT include preprocessing, setup, or HPC agents.
ONLY create execution plan for Analysis Agent.

File Structure:
- Working Directory: {working_dir}
- Trajectory/Topology Location: {working_dir}/hpc/ (auto-discovery)
- Analysis Output Directory: {working_dir}/analysis/

**Available Analysis Agent Tools:**
{tools_context}

{per_sim_scope_note}{self._get_tool_creation_instructions(include_new_tools_note)}

**CRITICAL INSTRUCTIONS:**
- FIRST: Check if the requested analysis is available in the tools list above
- Plan ONLY the analyses explicitly requested in USER GOAL — do not add RMSD, Rg, SASA, DCCM, etc. unless requested
- If a required analysis tool is missing (e.g., DSSP, SASA, hydrogen bonds, distance calculations, etc.), you MUST state "Missing tool for [analysis type]" explicitly
- Use the analysis agent's Python tools listed above (calculate_rmsd, calculate_rmsf, etc.) when available
- Do NOT assume tools exist - check the list carefully
- Do NOT use bash/shell commands or GROMACS CLI tools (gmx rmsf, etc.)
- Do NOT plan wrap_trajectory or run_complete_analysis unless USER GOAL explicitly requires them
- The analysis agent will handle file discovery and tool execution
- Specify WHICH tools to use and what analysis to perform
- Let the analysis agent handle the implementation details

**ANALYSIS TYPES (only include if USER GOAL requests them):**
If the user requests any of these analyses, verify a tool exists:
- Secondary structure (DSSP)
- Solvent accessible surface area (SASA)
- Hydrogen bonds
- Salt bridges
- Protein-ligand contacts
- Distance measurements
- Angle calculations
- Dihedral angles
- Principal component analysis (PCA)
- Clustering
- Free energy calculations

If any requested analysis is NOT in the available tools, state it clearly.

{nl_format_instructions}"""

        elif subtask_type == "setup_only":
            return f"""Create a detailed natural language execution plan for MD simulation setup.

USER GOAL:
{structured_prompt}

TASK: Setup-only - generate topology and coordinate files for simulation.
Only include Setup Agent. Do NOT include preprocessing (unless explicitly requested), HPC, or analysis.

PDB File: {pdb_path or 'Not specified'}
Force Field: {state.get('force_field', 'amber99sb-ildn')}
Water Model: {state.get('water_model', 'tip3p')}

**Available Setup Agent Tools:**
{tools_context}

**CRITICAL INSTRUCTIONS:**
- Use the setup agent's tools listed above (generate_topology, create_solvation_box, etc.)
- Specify which setup tools to use and their parameters
- Focus on topology generation and system preparation

{nl_format_instructions}

Provide a comprehensive natural language plan explaining how the Setup Agent should prepare the simulation system."""

        elif subtask_type == "preprocess_only":
            return f"""Create a detailed natural language execution plan for structure preprocessing.

USER GOAL:
{structured_prompt}

TASK: Preprocessing-only - clean and validate protein structure.
Only include Preprocessing Agent. Do NOT include setup, HPC, or analysis.

PDB File: {pdb_path or 'Not specified'}

**Available Preprocessing Agent Tools:**
{tools_context}

**CRITICAL INSTRUCTIONS:**
- Use the preprocessing agent's tools listed above (remove_waters, fix_residues, add_hydrogens, etc.)
- Specify which preprocessing tools to use
- Focus on structure cleanup and validation

{nl_format_instructions}

Provide a comprehensive natural language plan explaining how the Preprocessing Agent should clean and prepare the structure."""

        elif subtask_type == "reporter_only":
            working_dir = state.get("working_directory", ".")
            return f"""Create a detailed natural language execution plan for generating a scientific report.

USER GOAL:
{structured_prompt}

TASK: Reporter-only - generate comprehensive reports from ALREADY COMPLETED analysis results.
Only include Reporter Agent. Do NOT include preprocessing, setup, HPC, or analysis agents.

**CRITICAL UNDERSTANDING:**
This is a REPORTING task, NOT an analysis task. The user wants to:
- Summarize and document results that have ALREADY been analyzed
- Create formatted HTML/markdown reports from existing data
- Generate visualizations and tables from completed analysis outputs
- Compile findings into a scientific document

Do NOT:
- Perform new trajectory analysis (RMSD, RMSF, DSSP, etc.)
- Calculate new metrics or properties
- Invoke the Analysis Agent
- Request tools for analysis calculations (rmsd_calculate.py, rmsf_calculate.py, etc.)

DO:
- Use reporter tools to format and document existing results
- Create summary reports from analysis_summary.jsonl
- Generate HTML/markdown documents
- Embed existing plots and data
- Compile findings into readable format

File Structure:
- Working Directory: {working_dir}
- Analysis Results: {working_dir}/analysis/ (contains completed analysis outputs)
- Analysis Summary: {working_dir}/analysis/analysis_summary.jsonl (metadata about completed analyses)
- Report Output: {working_dir}/reports/ (where to save generated reports)

**Available Reporter Agent Tools:**
{tools_context}

{self._get_tool_creation_instructions(include_new_tools_note)}

**IMPORTANT:**
If the user's request mentions specific analyses (RMSD, RMSF, secondary structure, etc.), they want those results DOCUMENTED in the report, NOT recalculated. The analysis should already be complete in the analysis directory.

If analysis results are missing, the reporter should note what's missing in the report, not invoke the programmer to create analysis tools.

{nl_format_instructions}

Provide a comprehensive natural language plan explaining how the Reporter Agent should compile and format the scientific report from existing analysis results."""

        elif subtask_type == "multi_agent":
            working_dir = state.get("working_directory", ".")
            agent_list = state.get("agent_list") or []
            _agent_names = {
                "preprocess": "Preprocessing Agent",
                "simsetup":   "Simulation Setup Agent",
                "hpcjob":     "HPC Agent",
                "analysis":   "Analysis Agent",
                "reporter":   "Reporter Agent",
            }
            agents_str = " → ".join(_agent_names.get(a, a) for a in agent_list)
            
            # Build example structure showing required agent section headers
            example_sections = []
            for a in agent_list:
                agent_display = _agent_names.get(a, a)
                example_sections.append(
                    f"**{agent_display}:**\n"
                    f"The {agent_display} will ... [detailed instructions for this agent including "
                    f"which tools to use, what inputs it needs, what outputs it produces, "
                    f"and step-by-step execution details] ..."
                )
            example_structure = "\n\n".join(example_sections)
            
            # Format component selection for multi-agent prompt
            comp_sel_str = ""
            if component_selection:
                sel_parts = []
                if component_selection.get("protein"):
                    sel_parts.append("protein")
                if component_selection.get("ligand"):
                    sel_parts.append("ligand")
                if component_selection.get("ions"):
                    sel_parts.append("crystallographic ions")
                if component_selection.get("water"):
                    sel_parts.append("crystallographic water")
                comp_sel_str = (
                    f"\n**User's Component Selection (from PDB):** {', '.join(sel_parts) if sel_parts else 'all available'}"
                    f"\n- Protein: {'Include' if component_selection.get('protein', True) else 'EXCLUDE'}"
                    f"\n- Ligand: {'Include' if component_selection.get('ligand') else 'EXCLUDE'}"
                    f"\n- Crystallographic Ions: {'Include' if component_selection.get('ions') else 'EXCLUDE'}"
                    f"\n- Crystallographic Water: {'Keep' if component_selection.get('water') else 'Remove from PDB'}"
                    f"\nCRITICAL: Only process PDB components marked 'Include'. Excluded components must not be parameterized or included in simulation setup."
                    f"\n\nIMPORTANT: The component selection above refers to components FROM THE PDB FILE."
                    f"\n  'Crystallographic Water: Remove from PDB' does NOT mean build a vacuum system."
                    f"\n  Solvation with tip3p water is ALWAYS part of standard simulation setup (handled by build_simulation_system)."
                    f"\n  Do NOT instruct the setup agent to skip solvation or use water_model='none'."
                )
            
            return f"""Create a detailed natural language execution plan for a MULTI-AGENT workflow.

USER GOAL:
{structured_prompt}

PDB File: {pdb_path or 'Not specified'}
TASK: Run ONLY these agents in order: {agents_str}
{comp_sel_str}

Do NOT add any agents that are not listed above.

**SCOPE BOUNDARY (CRITICAL):**
- "Preprocessing" means: clean PDB, separate components, add hydrogens, validate. Outputs: cleaned PDB files ONLY (.pdb).
  Preprocessing does NOT generate topology (.itp), parameter files, or force-field data. Those are the Setup Agent's job.
- "Simulation setup" means: generate ligand parameters (if ligand present), generate protein topology, build box, SOLVATE with tip3p water, add counter-ions + 0.15M NaCl, generate MDP files, generate TPR file. Outputs: topology (.top), coordinates (.gro), ligand parameters (.itp), MDP files, TPR file.
  Ligand parameterization (generate_ligand_parameters) is ALWAYS done by the Simulation Setup Agent, never by Preprocessing.
- Solvation and ion addition are ALWAYS part of standard simulation setup. Do NOT create vacuum/unsolvated systems unless the user explicitly says "in vacuum" or "gas phase".
- "Simulation setup" does NOT mean running the simulation (no mdrun, no equilibration, no production run, no trajectory generation).
- Only plan for the agents listed above. Do NOT plan steps that belong to agents not in the list (e.g., HPC submission, simulation execution, analysis).
- Do NOT request creation of tools for running simulations (e.g., run_gromacs_simulation) unless an HPC agent is in the agent list.
- Do NOT assume any .itp or topology files exist from preprocessing. The Setup Agent must generate all topology and parameter files from scratch.

**Default Simulation Conditions (DO NOT CHANGE unless user explicitly states otherwise):**
- Force field: {state.get('force_field', 'amber99sb-ildn')}
- Water model: {state.get('water_model', 'tip3p')} (solvated system, NOT vacuum)
- Temperature: 310 K, Pressure: 1 bar
- NaCl concentration: 0.15 M (physiological)
- Box type: cubic, distance: 1.2 nm
These are the defaults already built into the pipeline tools. Do not override them unless the user explicitly requests different values.

Working Directory: {working_dir}

**Available Tools (for the listed agents only):**
{tools_context}

{per_sim_scope_note}{self._get_tool_creation_instructions(include_new_tools_note, agent_list)}

**CRITICAL INSTRUCTIONS:**
- Your plan MUST cover ONLY the agents listed: {agents_str}
- Use the EXACT agent name phrases (e.g., "Preprocessing Agent", "Analysis Agent") so routing works
- Each agent section should describe what it needs as input and what it will produce as output
- The agents run in order: first agent's outputs become next agent's inputs
- Analysis Agent: plan ONLY metrics explicitly requested in USER GOAL; Reporter Agent documents those results only

{nl_format_instructions}

**REQUIRED PLAN STRUCTURE:**

You MUST organize your plan into agent-specific sections. Each section MUST use an
exact agent name header with ** markers. ALL detailed instructions for an agent
(tools to use, parameters, input/output files, execution order) MUST go under that
agent's section header. Do NOT scatter an agent's instructions across multiple sections.

**Goal:**
[Brief summary of what the workflow will accomplish]

{example_structure}

**Expected Outcomes:**
[Final deliverables]

CRITICAL: Use the section headers EXACTLY as shown above with ** markers
(e.g., {', '.join(f'"**{_agent_names.get(a, a)}:**"' for a in agent_list)}).
This allows each agent to extract ONLY its relevant instructions.
Put ALL detailed steps, tool references, and execution logic under the correct agent header.

Follow the OUTPUT FORMAT closing instruction above."""

        else:
            components = pdb_analysis.get("components_available", {})
            
            # Format component selection for LLM context
            comp_sel_lines = ""
            if component_selection:
                sel_parts = []
                if component_selection.get("protein"):
                    sel_parts.append("protein")
                if component_selection.get("ligand"):
                    sel_parts.append("ligand")
                if component_selection.get("ions"):
                    sel_parts.append("crystallographic ions")
                if component_selection.get("water"):
                    sel_parts.append("crystallographic water")
                comp_sel_lines = (
                    f"\n**User's Component Selection (from PDB):** {', '.join(sel_parts) if sel_parts else 'all available'}"
                    f"\n- Protein: {'Include' if component_selection.get('protein', True) else 'EXCLUDE'}"
                    f"\n- Ligand: {'Include' if component_selection.get('ligand') else 'EXCLUDE'}"
                    f"\n- Crystallographic Ions: {'Include' if component_selection.get('ions') else 'EXCLUDE'}"
                    f"\n- Crystallographic Water: {'Keep' if component_selection.get('water') else 'Remove from PDB during preprocessing'}"
                    f"\n\nCRITICAL: The preprocessing agent should only extract PDB components marked 'Include'."
                    f"\nThe setup agent should only generate topology and parameters for included components."
                    f"\nDo NOT include excluded components in the simulation setup."
                    f"\n\nIMPORTANT: 'Remove Crystallographic Water from PDB' does NOT mean build a vacuum system."
                    f"\n  Solvation with tip3p water is ALWAYS part of standard simulation setup."
                )
            
            return f"""Create a detailed natural language execution plan for the complete MD workflow.

USER GOAL:
{structured_prompt}

PDB File: {pdb_path}
Atoms: {pdb_analysis.get('total_atoms', '?')} | Residues: {pdb_analysis.get('total_residues', '?')}
Components in PDB: Protein={components.get('protein', False)} Ligand={components.get('ligand', False)} Water={components.get('water', False)}
{comp_sel_lines}

Force Field: {state.get('force_field', 'amber99sb-ildn')}
Water Model: {state.get('water_model', 'tip3p')}

**Default Simulation Conditions (DO NOT CHANGE unless user explicitly states otherwise):**
- Force field: {state.get('force_field', 'amber99sb-ildn')} (do NOT switch to CHARMM or other force fields)
- Water model: {state.get('water_model', 'tip3p')} (solvated system, NOT vacuum)
- Temperature: 310 K, Pressure: 1 bar, NaCl concentration: 0.15 M
- These are the defaults built into the pipeline tools. Only change if user explicitly requests it.

**SCOPE BOUNDARY (CRITICAL):**
- "Preprocessing" means: clean PDB, separate components, add hydrogens, validate. Outputs: cleaned PDB files ONLY (.pdb).
  Preprocessing does NOT generate topology (.itp), parameter files, or force-field data.
- "Simulation setup" means: generate ligand parameters (if ligand present), generate protein topology, build box, solvate, add ions, generate MDP files, generate TPR.
  Ligand parameterization (generate_ligand_parameters) is ALWAYS done by the Simulation Setup Agent, never by Preprocessing.
- Do NOT assume any .itp or topology files exist from preprocessing. The Setup Agent must generate all topology and parameter files from scratch.

**Available Agents and Their Tools:**
{tools_context}

{per_sim_scope_note}{self._get_tool_creation_instructions(include_new_tools_note)}

**CRITICAL INSTRUCTIONS FOR TOOL CHECKING:**
- BEFORE creating your plan, verify that all required tools are available in the lists above
- If any preprocessing, setup, simulation, or analysis capability is missing, explicitly state "Missing tool for [functionality]"
- Do NOT assume capabilities exist - check the actual tools list
- Examples of specialized tools that may need creation:
  * Custom analysis (DSSP, SASA, hydrogen bonds, contacts, etc.)
  * Specialized structure modifications
  * Custom force field parameters
  * Non-standard MD parameters or protocols

**CRITICAL INSTRUCTIONS FOR AGENT NAMING:**
You MUST explicitly name each agent involved in your plan using these EXACT phrases:
- "Preprocessing Agent" or "preprocessing agent" - for structure cleaning
- "Simulation Setup Agent" or "setup agent" - for topology and system building
- "HPC Agent" or "hpc agent" - for job submission
- "Analysis Agent" or "analysis agent" - for trajectory analysis

Write complete sentences like:
"The Preprocessing Agent will first clean the PDB structure by..."
"Next, the Simulation Setup Agent generates topology files using..."
"The HPC Agent then submits the simulation job with..."

{nl_format_instructions}

**EXAMPLE STRUCTURE:**

**Goal:**
[Summarize what needs to be accomplished in 2-3 sentences]

**Workflow Execution:**

**Preprocessing Agent:**
The Preprocessing Agent will handle structure preparation. It will use the separate_complex_components tool to split the complex into protein, ligand, and ion PDB files. The add_hydrogens tool will then ensure complete protonation of the protein (reduce method) and ligand (obabel method) at neutral pH. The agent outputs cleaned PDB files only — no topology or parameter files.

**Simulation Setup Agent:**
The Simulation Setup Agent will prepare the simulation system. First, it will use generate_ligand_parameters to create the ligand topology (.itp) from the ligand PDB provided by preprocessing. Then, using build_simulation_system, it generates AMBER99SB-ILDN topology files for the protein, merges all components, places the system in a cubic simulation box, solvates with TIP3P water, and neutralizes with appropriate ions. MDP parameter files will be created for all simulation phases.

**HPC Agent:**
The HPC Agent will handle job submission to the compute cluster. It will use create_slurm_script to generate an appropriate job submission script, then submit_job to initiate the simulation on the HPC system.

**Expected Outcomes:**
[Describe final deliverables and verification steps]

CRITICAL: Use the section headers exactly as shown above with ** markers (e.g., **Preprocessing Agent:**, **Simulation Setup Agent:**, **HPC Agent:**, **Analysis Agent:**). This allows each agent to extract only its relevant instructions.

Provide a comprehensive natural language plan following this structure. DO NOT output JSON, YAML, or any structured data format."""
    
    def _get_tool_creation_instructions(self, include_new_tools_note: bool = False,
                                        agent_list: Optional[list] = None) -> str:
        """
        Get instructions about tool creation capability for LLM prompt.
        
        Tool creation is only relevant when agents that might need custom tools
        are involved (e.g., analysis, hpc). For preprocess + simsetup only workflows,
        all required tools are already available.
        
        Args:
            include_new_tools_note: Whether to note that new tools were just created
            agent_list: List of agents in the workflow (used to decide if tool creation applies)
            
        Returns:
            Formatted instructions string
        """
        tool_creation_enabled = self.config.get("planner", {}).get("behavior", {}).get("enable_tool_creation", True)
        
        if not tool_creation_enabled:
            return ""
        
        # Tool creation is NOT needed for preprocess + simsetup only workflows.
        # All required tools (build_topology, solvate_system, etc.) already exist.
        if agent_list:
            agents_needing_custom_tools = {"analysis", "hpc", "hpcjob", "reporter"}
            if not agents_needing_custom_tools.intersection(set(agent_list)):
                return """
**NOTE ON TOOLS:**
All required tools for preprocessing and simulation setup are already available in the tools list above.
Do NOT request creation of new tools. Use ONLY the existing tools listed above.
Do NOT plan steps that require tools not in the list (e.g., running simulations with gmx mdrun).
"""
        
        if include_new_tools_note:
            return """
**NOTE ON NEW TOOLS:**
Custom tools have just been created by the Programmer Agent and are now available.
These new tools are included in the tools list above. Please create your execution plan
using both the original tools and the newly created tools.
"""
        else:
            metric_ref = get_planner_metric_tool_reference()
            return f"""
**CRITICAL: TOOL AVAILABILITY CHECK**

BEFORE creating your execution plan, you MUST:

1. **Review the requested task** - Identify what specific analyses, calculations, or operations are needed

2. **Check available tools** - Carefully examine the tools list above to see if they can accomplish the task

3. **Use the metric → tool map below** - Common analyses map to existing tools; only request
   programmer creation when NO tool in the list covers the capability.

{metric_ref}

4. **Identify genuinely missing capabilities** - Only if the required functionality is NOT
   available in existing tools AND not in the map above, state this explicitly.

**HOW TO REQUEST MISSING TOOLS (only when genuinely absent from the tools list):**

If you identify that a tool is truly missing, include a clear statement using one of these phrases:
- "Missing tool for [specific functionality]"
- "Need to create custom tool for [specific purpose]"  
- "No existing tool available for [task]"

**EXAMPLE (genuine gap — after checking the metric map):**
"Missing tool for hydrogen-bond lifetime autocorrelation. Need to create custom tool for
 time-correlation of intermittent H-bonds between ligand and pocket residues."

**DO NOT declare missing** for metrics covered in the map above (e.g. FEL uses
`calculate_free_energy_landscape`, pocket SASA uses `calculate_pocket_sasa`,
residence uses `analyze_ligand_residence`, ligand RMSD uses `calculate_ligand_rmsd`,
native contacts / φψ use `calculate_native_contacts` / `calculate_backbone_dihedrals`).

**WHAT HAPPENS NEXT:**
When you indicate genuinely missing tools, the Programmer Agent creates them under
`{{working_dir}}/programmer/` before the execution plan is finalized. Prefer that path
over skipping the analysis. After a successful campaign, humans may promote useful
tools into `src/analysis/` via `scripts/promote_programmer_tool.py`.

**IMPORTANT:**
- DO match metric names to the tool map and tools list before claiming anything is missing
- DO be specific about what functionality is missing
- DO NOT request tools that already exist under a different name
- DO prefer automatic tool creation (up to the configured iteration limit) over omitting requested science
"""
    
    def _parse_llm_plan_response(self, response: str, state: MDState) -> Optional[Dict[str, Any]]:
        """Parse LLM response. Return None if response is just asking questions."""
        import re
        
        logger.info("PLANNER: Processing LLM response")
        
        if not response:
            logger.warning("PLANNER: Empty LLM response - triggering fallback")
            return None
        
        # Detect if LLM is asking for clarification instead of providing a plan
        question_indicators = [
            r'what.*goal\s*\?',
            r'i\s+(need|require)\s+.*information',
            r'can\s+you\s+(clarify|specify)',
            r'do\s+you\s+want',
            r'are\s+there\s+any',
        ]
        
        response_lower = response.lower()
        question_count = sum(1 for pattern in question_indicators if re.search(pattern, response_lower))
        question_mark_count = response.count('?')
        
        if question_count >= 2 or question_mark_count >= 3:
            logger.warning("PLANNER: LLM response is asking questions instead of creating plan - triggering fallback")
            return None  # Signal to use fallback
        
        # CRITICAL: For subtask-specific workflows, automatically infer agent from subtask type
        # This ensures the correct agent is included even if not explicitly mentioned in prose
        subtask_type = state.get("subtask_type")
        
        if state.get("hpc_pool_prep_only"):
            agent_mentions = {"preprocessing_agent": True, "setup_agent": True}
        elif subtask_type == "analysis_only":
            # Analysis-only workflow - only analysis agent
            agent_mentions = {"analysis_agent": True}
        elif subtask_type == "setup_only":
            # Setup-only workflow - only setup agent
            agent_mentions = {"setup_agent": True}
        elif subtask_type == "preprocess_only":
            # Preprocess-only workflow - only preprocessing agent
            agent_mentions = {"preprocessing_agent": True}
        elif subtask_type == "reporter_only":
            # Reporter-only workflow - only reporter agent
            agent_mentions = {"reporter_agent": True}
        elif subtask_type == "multi_agent":
            # Multi-agent workflow - build agent_mentions from the declared agent_list
            _cli_to_registry = {
                "preprocess": "preprocessing_agent",
                "simsetup": "setup_agent",
                "hpcjob": "hpc_agent",
                "analysis": "analysis_agent",
                "reporter": "reporter_agent",
            }
            agent_list = state.get("agent_list") or []
            agent_mentions = {_cli_to_registry[a]: True for a in agent_list if a in _cli_to_registry}
            logger.info(f"PLANNER: multi_agent plan steps → {list(agent_mentions.keys())}")
        else:
            # Full workflow - extract which agents are mentioned in the plan
            agent_mentions = {
                "preprocessing_agent": bool(re.search(r'(?i)preprocessing\s+agent', response)),
                "setup_agent": bool(re.search(r'(?i)(setup|simsetup|simulation\s+setup)\s+agent', response)),
                "hpc_agent": bool(re.search(r'(?i)hpc\s+agent', response)),
                "analysis_agent": bool(re.search(r'(?i)analysis\s+agent', response))
            }
            
            # FALLBACK: If LLM didn't mention agents (e.g., returned JSON), infer from user goal
            num_agents_mentioned = sum(agent_mentions.values())
            if num_agents_mentioned == 0:
                logger.warning("PLANNER: LLM response doesn't mention any agents. Inferring from user goal.")
                user_goal = state.get("user_goal", "").lower()
                structured_prompt = state.get("structured_prompt", "").lower()
                goal_text = user_goal + " " + structured_prompt
                
                # Infer which agents are needed based on keywords in goal
                needs_preprocess = bool(re.search(r'(preprocess|clean|extract|protein)', goal_text))
                needs_setup = bool(re.search(r'(setup|simulation|topology|system|solvate|box)', goal_text))
                needs_hpc = bool(re.search(r'(hpc|submit|run|execute|cluster)', goal_text))
                needs_analysis = bool(re.search(r'analysis|analyze|rmsd|rmsf', goal_text))
                
                # Default to full workflow if can't determine
                if not any([needs_preprocess, needs_setup, needs_hpc, needs_analysis]):
                    logger.info("PLANNER: Cannot determine workflow from goal, defaulting to full workflow")
                    needs_preprocess = needs_setup = needs_hpc = True
                    needs_analysis = False  # Only if explicitly requested
                
                agent_mentions = {
                    "preprocessing_agent": needs_preprocess,
                    "setup_agent": needs_setup,
                    "hpc_agent": needs_hpc,
                    "analysis_agent": needs_analysis
                }
                
                logger.info(f"PLANNER: Inferred agents from goal: {[k for k, v in agent_mentions.items() if v]}")
        
        # Build lightweight plan structure for routing
        steps = []
        step_num = 1
        
        for agent_name, is_mentioned in agent_mentions.items():
            if is_mentioned:
                steps.append({
                    "step_number": step_num,
                    "agent": agent_name,
                    "type": "natural_language",
                    "dependencies": [step_num - 1] if step_num > 1 else []
                })
                step_num += 1
        
        plan = {
            "title": "Detailed Natural Language Execution Plan",
            "format": "natural_language",
            "full_plan": response,
            "agent_sequence": [s["agent"] for s in steps],
            "agent_plans": self._extract_agent_plans(response, [s["agent"] for s in steps]),
            "steps": steps
        }
        
        logger.info(f"PLANNER: Detected {len(steps)} agents in execution sequence: {plan['agent_sequence']}")
        agent_plans_summary = {k: len(v) for k, v in plan["agent_plans"].items()}
        logger.info(f"PLANNER: Extracted agent plans (chars): {agent_plans_summary}")
        return plan
    
    def _extract_agent_plans(self, full_plan: str, agent_sequence: list) -> Dict[str, str]:
        """
        Extract agent-specific instruction sections from the full natural language plan.
        
        Uses the agent section headers (e.g., **Analysis Agent:**) that the LLM prompt
        requires. Each agent gets the prose between its header and the next header.
        
        Args:
            full_plan: Complete natural language plan text from LLM
            agent_sequence: List of agent registry names (e.g., ["analysis_agent", "reporter_agent"])
            
        Returns:
            Dict mapping agent registry names to their instruction sections.
            Falls back to full_plan for any agent whose section can't be extracted.
        """
        import re
        
        # Map registry names to display names used in plan headers
        _registry_to_display = {
            "preprocessing_agent": ["Preprocessing Agent", "PDB Preprocessing Agent", "Preprocess Agent"],
            "setup_agent": ["Simulation Setup Agent", "SimSetup Agent", "Setup Agent"],
            "hpc_agent": ["HPC Agent", "HPC Submission Agent", "Job Submission Agent"],
            "analysis_agent": ["Analysis Agent", "MD Analysis Agent", "Trajectory Analysis Agent"],
            "reporter_agent": ["Reporter Agent", "Report Generation Agent", "Scientific Reporter Agent"],
        }
        
        agent_plans = {}
        
        # Minimum chars for a meaningful agent section (avoids grabbing brief summaries)
        min_chars = max(200, len(full_plan) // 10)
        
        for agent_key in agent_sequence:
            display_names = _registry_to_display.get(agent_key, [agent_key])
            extracted = None
            
            for display_name in display_names:
                # Strategy 1: Bold header with colon at line start — **Agent Name:** ...
                # Capture until next line-start bold header (e.g., **Reporter Agent:** or **Expected Outcomes:**)
                pattern = (
                    rf'^\*\*{re.escape(display_name)}(?:\s*:?\s*\*\*|:\*\*)\s*\n'
                    rf'(.*?)'
                    rf'(?=^\*\*[A-Z]|\Z)'
                )
                match = re.search(pattern, full_plan, re.DOTALL | re.IGNORECASE | re.MULTILINE)
                if match:
                    text = match.group(1).strip()
                    if len(text) > 50:
                        extracted = text
                        logger.info(
                            f"PLANNER: Extracted {len(text)} chars for {agent_key} "
                            f"(strategy 1: bold header '{display_name}')"
                        )
                        break
                
                # Strategy 2: Numbered section at line start — 1. **Agent Name** ...
                # Use higher threshold to avoid grabbing brief summary bullets
                pattern2 = (
                    rf'^\d+\.\s*\*\*{re.escape(display_name)}\*\*.*?\n'
                    rf'(.*?)'
                    rf'(?=^\d+\.\s*\*\*|^\*\*[A-Z]|\Z)'
                )
                match = re.search(pattern2, full_plan, re.DOTALL | re.IGNORECASE | re.MULTILINE)
                if match:
                    text = match.group(1).strip()
                    if len(text) > min_chars:
                        extracted = text
                        logger.info(
                            f"PLANNER: Extracted {len(text)} chars for {agent_key} "
                            f"(strategy 2: numbered section '{display_name}')"
                        )
                        break
            
            if extracted:
                agent_plans[agent_key] = extracted
            else:
                # Fallback: give this agent the entire plan
                logger.warning(
                    f"PLANNER: Could not extract section for {agent_key}, "
                    f"will provide full plan as fallback"
                )
                agent_plans[agent_key] = full_plan
        
        return agent_plans
    
    def _create_fallback_plan(
        self,
        structured_prompt: str,
        pdb_path: str,
        pdb_analysis: Dict[str, Any],
        component_selection: Dict[str, Any],
        state: MDState
    ) -> Dict[str, Any]:
        """
        Fallback template-based planning when LLM is unavailable.
        
        CRITICAL: Always generates NATURAL LANGUAGE plans, never structured JSON.
        Respects subtask_type to focus only on requested workflow stages.
        """
        logger.info("PLANNER: Creating fallback natural language plan from PDB analysis")
        
        pdb_analysis = _coerce_pdb_analysis(pdb_analysis)
        component_selection = component_selection or {}
        subtask_type = state.get("subtask_type")
        summary = pdb_analysis.get("summary") or {}
        working_dir = state.get("working_directory", ".")
        
        # Build natural language plan prose
        plan_sections = []
        agents_involved = []
        
        # Section 1: Goal Understanding
        plan_sections.append(f"**GOAL INTERPRETATION:**\n\n{structured_prompt}\n")
        
        # Section 2: PDB Analysis Summary (if not analysis-only)
        if subtask_type != "analysis_only":
            pdb_info = []
            pdb_info.append(f"PDB File: {pdb_path}")
            pdb_info.append(f"Total Atoms: {pdb_analysis.get('total_atoms', 'Unknown')}")
            if pdb_analysis.get('protein', {}).get('present'):
                pdb_info.append(f"Protein: Present ({pdb_analysis.get('total_residues', '?')} residues)")
            if pdb_analysis.get('ligands', {}).get('present'):
                ligands = pdb_analysis.get('ligands', {}).get('residue_names', [])
                pdb_info.append(f"Ligands: {', '.join(ligands)}")
            if pdb_analysis.get('water', {}).get('present'):
                pdb_info.append(f"Water: Present ({pdb_analysis.get('water', {}).get('molecule_count', '?')} molecules)")
            
            plan_sections.append(f"**PDB STRUCTURE ANALYSIS:**\n\n" + "\n".join(pdb_info) + "\n")
        
        # Section 3: Execution Sequence (detailed prose for each agent)
        execution_prose = []
        
        # === ANALYSIS-ONLY WORKFLOW ===
        if subtask_type == "analysis_only":
            agents_involved.append("analysis_agent")
            execution_prose.append(
                f"**Analysis Agent Responsibilities:**\n\n"
                f"The Analysis Agent will perform trajectory analysis on existing simulation data located "
                f"in {working_dir}/hpc/. The agent will auto-discover topology and trajectory files "
                f"(looking for .gro, .pdb, .tpr for topology and .xtc, .trr for trajectories).\n\n"
                f"Analysis tasks to perform:\n"
                f"- Calculate structural metrics (RMSD, RMSF) as requested\n"
                f"- Generate energy profiles if energy files (.edr) are available\n"
                f"- Create visualization plots for all analyses\n"
                f"- Save all results to {working_dir}/analysis/\n\n"
                f"The agent will use Python-based analysis tools (MDAnalysis, matplotlib) rather than "
                f"command-line GROMACS tools for better integration and flexibility."
            )
        
        # === REPORTER-ONLY WORKFLOW ===
        elif subtask_type == "reporter_only":
            agents_involved.append("reporter_agent")
            execution_prose.append(
                f"**Reporter Agent Responsibilities:**\n\n"
                f"The Reporter Agent will generate a comprehensive scientific report from ALREADY COMPLETED "
                f"analysis results located in {working_dir}/analysis/.\n\n"
                f"IMPORTANT: This is a REPORTING task, not an analysis task. The Reporter will:\n"
                f"- Load existing analysis results from {working_dir}/analysis/\n"
                f"- Read analysis metadata from analysis_summary.jsonl\n"
                f"- Compile findings into a formatted HTML or markdown report\n"
                f"- Embed existing plots and visualizations\n"
                f"- Create summary tables and statistics from completed analyses\n"
                f"- Save the final report to {working_dir}/reports/\n\n"
                f"The Reporter will NOT:\n"
                f"- Perform new trajectory analyses (RMSD, RMSF, secondary structure, etc.)\n"
                f"- Calculate new metrics or properties\n"
                f"- Invoke analysis tools or the Analysis Agent\n\n"
                f"Tools to use: HTML/markdown generation, plot embedding, data formatting, "
                f"summary statistics compilation.\n\n"
                f"Expected output: Comprehensive scientific report documenting completed simulation analyses"
            )

        # === MULTI-AGENT WORKFLOW ===
        elif subtask_type == "multi_agent":
            agent_list = state.get("agent_list") or []
            
            # Build component description for fallback plans
            comp_desc = ""
            if component_selection:
                sel_parts = [k for k in ["protein", "ligand", "ions"] if component_selection.get(k)]
                if sel_parts:
                    comp_desc = f" for {'+'.join(sel_parts)} components"
            
            _cli_agent_descriptions = {
                "preprocess": (
                    "preprocessing_agent",
                    f"**Preprocessing Agent Responsibilities:**\n\n"
                    f"Clean and prepare the PDB structure{comp_desc}: separate components, remove waters, fix residues, add hydrogens.\n"
                    f"Only extract and pass downstream the components the user requested.\n"
                    f"Expected output: cleaned .pdb files for each requested component."
                ),
                "simsetup": (
                    "setup_agent",
                    f"**Setup Agent Responsibilities:**\n\n"
                    f"Generate the simulation system{comp_desc} using {state.get('force_field', 'amber99sb-ildn')} "
                    f"force field and {state.get('water_model', 'tip3p')} water model. "
                    f"Only build topology and parameters for components provided by preprocessing.\n"
                    f"Produce topology, solvated coordinates, ions, and MDP files."
                ),
                "hpcjob": (
                    "hpc_agent",
                    f"**HPC Agent Responsibilities:**\n\n"
                    f"Submit prepared simulation files to the HPC cluster via SLURM. "
                    f"Do not download results unless the user explicitly requests a "
                    f"remote transfer; analysis reads trajectories from {working_dir}/hpc/."
                ),
                "analysis": (
                    "analysis_agent",
                    f"**Analysis Agent Responsibilities:**\n\n"
                    f"Perform trajectory analysis on simulation data in {working_dir}/hpc/. "
                    f"Calculate RMSD, RMSF, and other requested metrics. "
                    f"Save results to {working_dir}/analysis/."
                ),
                "reporter": (
                    "reporter_agent",
                    f"**Reporter Agent Responsibilities:**\n\n"
                    f"Compile already-completed analysis results from {working_dir}/analysis/ into "
                    f"a comprehensive HTML scientific report. Write report to {working_dir}/reporter/. "
                    f"DO NOT run new analyses."
                ),
            }
            for cli_name in agent_list:
                if cli_name in _cli_agent_descriptions:
                    registry_name, prose = _cli_agent_descriptions[cli_name]
                    agents_involved.append(registry_name)
                    execution_prose.append(prose)
        
        # === FULL OR PARTIAL WORKFLOWS ===
        else:
            # Preprocessing
            if subtask_type != "setup_only":
                preprocessing_needed = []
                if summary.get("needs_hydrogen_addition"):
                    preprocessing_needed.append("adding missing hydrogens with correct protonation states")
                if pdb_analysis.get("water", {}).get("present"):
                    preprocessing_needed.append("removing water molecules")
                if component_selection.get("ligand") is False and pdb_analysis.get("ligands", {}).get("present"):
                    preprocessing_needed.append("removing ligand molecules")
                
                if preprocessing_needed or not state.get("cleaned_pdb"):
                    agents_involved.append("preprocessing_agent")
                    tasks_str = ", ".join(preprocessing_needed) if preprocessing_needed else "structure validation"
                    execution_prose.append(
                        f"**Preprocessing Agent Responsibilities:**\n\n"
                        f"The Preprocessing Agent will clean and prepare the PDB structure by {tasks_str}. "
                        f"This agent focuses solely on structure preparation and does NOT handle topology "
                        f"generation or force field assignment (those are handled by the Setup Agent).\n\n"
                        f"Tools to use: reduce (hydrogens), pdbfixer (missing atoms/residues), "
                        f"Bio.PDB (structure manipulation)\n\n"
                        f"Expected output: cleaned_pdb file ready for topology generation"
                    )
            
            # Setup
            if subtask_type not in ["analysis_only", "preprocess_only"]:
                agents_involved.append("setup_agent")
                ff = state.get('force_field', 'amber99sb-ildn')
                wm = state.get('water_model', 'tip3p')
                execution_prose.append(
                    f"\n\n**Setup Agent Responsibilities:**\n\n"
                    f"The Setup Agent will generate the complete simulation system using {ff} "
                    f"force field and {wm} water model. This includes:\n\n"
                    f"1. Topology generation (gmx pdb2gmx) for protein components\n"
                    f"2. Ligand parameterization using acpype or CGenFF if ligands are present and requested\n"
                    f"3. Defining the simulation box (gmx editconf)\n"
                    f"4. System solvation (gmx solvate)\n"
                    f"5. Adding neutralizing ions (gmx genion)\n"
                    f"6. Generating MDP parameter files for energy minimization, equilibration, and production runs\n\n"
                    f"Expected outputs: topology files (.top, .itp), coordinate files (.gro), "
                    f"and parameter files (.mdp)"
                )
            
            # HPC
            if subtask_type not in ["analysis_only", "setup_only", "preprocess_only"]:
                goal_lower = structured_prompt.lower() + state.get("user_goal", "").lower()
                hpc_excluded = any(phrase in goal_lower for phrase in [
                    "no hpc", "skip hpc", "do not submit", "don't submit", "setup only", "without hpc"
                ])
                
                if ("run" in goal_lower or "execute" in goal_lower or "simulate" in goal_lower) and not hpc_excluded:
                    agents_involved.append("hpc_agent")
                    execution_prose.append(
                        f"\n\n**HPC Agent Responsibilities:**\n\n"
                        f"The HPC Agent will submit the simulation to a compute cluster using SLURM. "
                        f"The agent will:\n\n"
                        f"1. Generate appropriate SLURM job scripts with resource requests\n"
                        f"2. Submit minimization, equilibration, and production MD as one job script\n"
                        f"3. Record the SLURM job id (waiting for completion is handled by the HPC pool "
                        f"when preprocess/setup/HPC/analysis run together)\n\n"
                        f"Do NOT download results unless the user explicitly requests a remote transfer; "
                        f"analysis reads trajectories in place from the hpc directory.\n\n"
                        f"Expected outputs: job_id, job script under working_dir/hpc/, and later "
                        f"trajectory (.xtc) / energy (.edr) files written by the running job"
                    )
                elif hpc_excluded:
                    execution_prose.append(
                        f"\n\n**HPC Submission: SKIPPED**\n\n"
                        f"User explicitly requested to skip HPC job submission. Simulation files will be "
                        f"prepared but not executed."
                    )
            
            # Analysis (for full workflows)
            if subtask_type not in ["preprocess_only", "setup_only"]:
                goal_lower = structured_prompt.lower()
                if "analyz" in goal_lower or "rmsd" in goal_lower or "rmsf" in goal_lower:
                    agents_involved.append("analysis_agent")
                    execution_prose.append(
                        f"\n\n**Analysis Agent Responsibilities:**\n\n"
                        f"After simulation completion, the Analysis Agent will perform trajectory analysis "
                        f"including RMSD (structural deviation), RMSF (per-residue flexibility), and other "
                        f"requested analyses. Results will be saved to {working_dir}/analysis/ with both "
                        f"data files and visualization plots."
                    )
        
        # Combine sections
        plan_sections.append("**EXECUTION SEQUENCE:**\n\n" + "\n".join(execution_prose))
        
        # Section 4: Expected Outcomes
        outcomes = []
        if "preprocessing_agent" in agents_involved:
            outcomes.append("- Cleaned PDB structure ready for topology generation")
        if "setup_agent" in agents_involved:
            outcomes.append("- Complete simulation system (topology, coordinates, parameters)")
        if "hpc_agent" in agents_involved:
            outcomes.append("- Completed simulation trajectory and energy data")
        if "analysis_agent" in agents_involved:
            outcomes.append("- Analysis results with plots and data files")
        
        if outcomes:
            plan_sections.append(f"\n\n**EXPECTED OUTCOMES:**\n\n" + "\n".join(outcomes))
        
        # Build complete natural language plan
        full_plan_text = "\n".join(plan_sections)
        
        # Create minimal step structure for routing (supervisor needs to know agent sequence)
        steps = []
        for i, agent_name in enumerate(agents_involved, 1):
            steps.append({
                "step_number": i,
                "agent": agent_name,
                "type": "natural_language",
                "dependencies": [i - 1] if i > 1 else []
            })
        
        plan = {
            "title": f"Fallback Natural Language Execution Plan: {subtask_type or 'full_pipeline'}",
            "format": "natural_language",
            "full_plan": full_plan_text,
            "agent_sequence": agents_involved,
            "agent_plans": self._extract_agent_plans(full_plan_text, agents_involved),
            "steps": steps,
            "method": "fallback",
            "subtask_type": subtask_type
        }
        
        logger.info(f"PLANNER: Fallback natural language plan complete with {len(agents_involved)} agents: {agents_involved}")
        return plan
    
    def _create_plan_from_templates(
        self, 
        user_goal: str, 
        validated_pdb: str,
        state: MDState
    ) -> Dict[str, Any]:
        """
        DEPRECATED: Create plan using keyword-based templates.
        
        This method is no longer used as all plans are now generated in natural language format.
        Kept for reference only. Use _create_fallback_plan() instead which generates NL plans.
        """
        logger.warning("PLANNER: _create_plan_from_templates is deprecated. Use _create_fallback_plan instead.")
        
        # Redirect to fallback plan which generates natural language
        return self._create_fallback_plan(
            structured_prompt=user_goal,
            pdb_path=validated_pdb,
            pdb_analysis=_coerce_pdb_analysis(state.get("pdb_analysis")),
            component_selection=state.get("component_selection") or {},
            state=state
        )
