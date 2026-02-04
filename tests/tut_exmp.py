##basics of LangGraph

## Step 1: you need to create a state
from typing import TypedDict, Optional, Dict, Any, List

class MDState(TypedDict):
    user_goal: str

    # Metadata
    md_engine: str                 # "gromacs"
    force_field: str               # "amber99sb-ildn"
    human_in_loop: bool

    # Preprocessing
    raw_pdb: Optional[str]
    cleaned_pdb: Optional[str]
    preprocessing_report: Optional[str]
    preprocessing_issues: List[str]

    # Setup
    topology: Optional[str]
    coordinates: Optional[str]
    mdp_files: Dict[str, str]
    setup_report: Optional[str]
    setup_issues: List[str]

    # HPC
    job_script: Optional[str]
    job_id: Optional[str]
    job_status: Optional[str]
    trajectory_path: Optional[str]

    # Analysis
    analysis_results: Dict[str, Any]
    figures: List[str]
    conclusions: Optional[str]

    # Control flags
    next_node: Optional[str]
    human_feedback: Optional[str]

### step 2: you need to create a graph that uses the state object

from langgraph.graph import StateGraph
graph = StateGraph(MDState)

### ## Step 3: you need to create functions that will be used as nodes

def supervisor_node(state: MDState) -> MDState:
    state["md_engine"] = "gromacs"
    state["force_field"] = "amber99sb-ildn"
    state["human_in_loop"] = True

    if state.get("cleaned_pdb") is None:
        state["next_node"] = "preprocess"
    elif state.get("topology") is None:
        state["next_node"] = "setup"
    elif state.get("job_id") is None:
        state["next_node"] = "hpc"
    elif not state.get("analysis_results"):
        state["next_node"] = "analysis"
    else:
        state["next_node"] = "end"

    return state

def preprocess_node(state: MDState) -> MDState:
    # LLM planner decides steps
    # Tool execution happens here

    state["cleaned_pdb"] = "protein_processed.gro"
    state["preprocessing_report"] = "Removed altlocs, protonated at pH 7"
    state["preprocessing_issues"] = []

    state["next_node"] = "human_preprocess_check" \
        if state["human_in_loop"] else "supervisor"

    return state


def human_preprocess_check(state: MDState) -> MDState:
    if state.get("human_feedback"):
        # feed feedback back into preprocessing agent
        state["preprocessing_report"] += f"\nHuman feedback: {state['human_feedback']}"
        state["next_node"] = "preprocess"
    else:
        state["next_node"] = "supervisor"
    return state


def setup_node(state: MDState) -> MDState:
    state["topology"] = "topol.top"
    state["coordinates"] = "solvated.gro"
    state["mdp_files"] = {
        "minim": "minim.mdp",
        "nvt": "nvt.mdp",
        "npt": "npt.mdp",
        "md": "md.mdp"
    }
    state["setup_report"] = "AMBER force field, TIP3P water, 1.0 nm box"

    state["next_node"] = "human_setup_check" \
        if state["human_in_loop"] else "supervisor"

    return state

def hpc_node(state: MDState) -> MDState:
    state["job_script"] = "run_md.slurm"
    state["job_id"] = "123456"
    state["job_status"] = "RUNNING"

    state["next_node"] = "analysis"
    return state


def analysis_node(state: MDState) -> MDState:
    state["analysis_results"] = {
        "rmsd": "rmsd.xvg",
        "rmsf": "rmsf.xvg",
        "contacts": "contacts.npy"
    }
    state["conclusions"] = "System stabilized after 50 ns"

    state["next_node"] = "end"
    return state


### ## Step 4: you need to create nodes and edges that operate on the graph

### step 4.1: create nodes
graph.add_node("supervisor", supervisor_node)
graph.add_node("preprocess", preprocess_node)
graph.add_node("human_preprocess_check", human_preprocess_check)
graph.add_node("setup", setup_node)
graph.add_node("human_setup_check", human_setup_check)
graph.add_node("hpc", hpc_node)
graph.add_node("analysis", analysis_node)

### step 4.2: create edges
graph.set_entry_point("supervisor")


graph.add_conditional_edges(
"supervisor",
lambda s: s["next_node"],
)


graph.add_conditional_edges(
"preprocess",
lambda s: s["next_node"],
)


graph.add_conditional_edges(
"setup",
lambda s: s["next_node"],
)


### step 5: you need to create a workflow that runs the graph

from langgraph.workflow import Workflow
workflow = Workflow(graph)

def run_md_workflow(goal: str, config: Dict[str, Any]) -> MDState:
    # Initialize state
     # Run the workflow
    final_state = workflow.run(MDState)
    return final_state





### Basics
"""
########################################################################
1. Sytex for conditional edges has two forms:

Form 1: Direct return (no mapping)
workflow.add_conditional_edges(
    "setup",
    lambda state: state["next_node"]
)

here function returns → node_name (string)


Form 2: Return + explicit routing map (your example)
workflow.add_conditional_edges(
    "input_validation",
    lambda state: state["next_node"],
    {"supervisor": "supervisor"}
)

here function returns → key
then that key → lookup in mapping → then got actual node

########################################################################

2. Pydentic Schema:
from pydantic import BaseModel
from typing import Literal

class NextStep(BaseModel):
    next_node: Literal["human", "hpc", "preprocess", "supervisor"]
    reason: str

Here LLMs can:
    Produce text
    Hallucinate fields
    Misspell keys
    Return wrong types
    but Pydantic will validate and enforce the schema (plan)

Pydantic automatically:
    Reads type hints (int, str)
    Intercepts object creation
    Validates inputs
    Converts when safe
    Raises errors when unsafe

Your LangGraph MDState is a state container.
Pydantic models are validation gates between:
    LLM output
    Graph state mutation

LLM → Pydantic → MDState → LangGraph

Pydantic schema = structured data contract
BaseModel = class that enforces that contract
########################################################################

LLM + Tool Fusion

Let’s walk through a real MD preprocessing example, aligned with your system.

Step 1: Define a STRICT schema (Pydantic)
from pydantic import BaseModel
from typing import List

class PreprocessReport(BaseModel):
    cleaned_pdb: str
    missing_residues: List[str]
    net_charge: int
    issues_found: bool

This schema defines what must exist — not who produces it.


Step 2: Let the LLM do ONLY what it’s good at

LLM responsibilities:
    Interpret logs
    Decide if issues exist
    Summarize missing residues
    Decide next action
    LLM prompt (example):
    You are analyzing GROMACS preprocessing logs.

    Return JSON with:
    - cleaned_pdb (string)
    - missing_residues (list of residue IDs)
    - issues_found (true/false)

    Do NOT guess net charge.

    
Step 3: Tool computes deterministic values
Now a tool (not the LLM) computes charge:

def compute_net_charge(topology_file: str) -> int:
    # parse topol.top or use gmx grompp output
    return -2

    
Step 4: Fuse LLM + Tool output BEFORE validation
import json

llm_data = json.loads(llm_output)
llm_data["net_charge"] = compute_net_charge("topol.top")
report = PreprocessReport(**llm_data)


✅ Validation passes
✅ No hallucination
✅ Deterministic science


Step 5: Update LangGraph state
state["preprocessing_report"] = report
state["next_node"] = "human" if report.issues_found else "supervisor"



Why This Pattern Is So Powerful
Aspect	Benefit
LLM	Reasoning & interpretation
Tools	Numerical correctness
Schema	Guarantees integrity
Graph	Controlled execution

This is research-grade agentic AI, not automation scripts.
########################################################################

1️⃣ What does “expose a function to the LLM” actually mean?

Exposing ≠ executing

To expose a function means:
you tell the LLM that a capability exists, with a name, description, and schema, so it can decide when to ask for it.
The LLM never runs the function.
It only learns:
What the tool is called
What it does (description)
What inputs it accepts (schema)
What output to expect (optional)

Example: Exposing a GROMACS-related tool
from langchain.tools import tool
from pydantic import BaseModel


class NetChargeInput(BaseModel):
    pdb_file: str
    ph: float


@tool(args_schema=NetChargeInput)
def compute_net_charge(pdb_file: str, ph: float) -> int:
    '''Compute net charge of a protein at given pH'''.
    ...

What this decorator does:

✔ Registers the function as a tool
✔ Attaches name + docstring + schema
✔ Makes it serializable to LLM function-calling format


3️⃣ What the LLM actually sees

The LLM receives something like this (conceptually):

{
  "name": "compute_net_charge",
  "description": "Compute net charge of a protein at given pH.",
  "parameters": {
    "pdb_file": { "type": "string" },
    "ph": { "type": "number" }
  }
}

👉 This is instructional, not executable.



4️⃣ What advantage does exposing tools give?
🔥 Advantage #1: Intent → Action bridge

Without tools:

LLM writes explanation of how to compute charge

With tools:

LLM says: "Call compute_net_charge with pdb_file=..., ph=7.4"

This bridges:

Reasoning → Real computation




########################################################################
Who does what (clear separation of powers)

Using your (excellent) framing:

LLM = thinks
Tool = measures
Schema = enforces
Graph = controls

Let’s map capability vs authority 👇

Component	Can decide to use tool?	Can execute tool?	Why
LLM	⚠️ Suggests	❌ No	Text-only, no side effects
Pydantic Schema	❌ No	❌ No	Validation only
LangGraph / Agent runtime	✅ Yes	✅ Yes	Owns control flow & code execution
Tool (Python fn / API)	❌ No	✅ Yes	Executes deterministic logic




"""