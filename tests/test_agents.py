import os
import sys
import re
ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from typing import TypedDict
from agentic.llm import LLMClient
from langchain_core.tools import tool

##1️⃣ Core idea (mental model)
"""
User prompt
   ↓
LLM decides to call tool
   ↓
Python script runs (with PDB path)
   ↓
Result returned to LLM
   ↓
LLM explains / continues

"""

##3️⃣ Expose the function as an LLM tool
@tool
def run_simulation_setup(pdb_file: str, wdir: str) -> str:
    """
    Run simulation setup for a given PDB file.
    """
    from  src.python.setup.sim_setup  import call_simulation_setup
    result = call_simulation_setup(pdb_file, wdir=wdir)
    return result["message"]


##4️⃣ Create an LLM node with tool support
from agentic.llm import LLMClient
from langchain_core.messages import HumanMessage, ToolMessage

llm = LLMClient(
    model="gpt-oss:120b",
    base_url="http://172.22.149.139:11434",
    tools=[run_simulation_setup],  # expose tool
)

## 5️⃣ Define LangGraph state
from typing import TypedDict, NotRequired
import json as _json
from datetime import datetime

# load agent config for logging and max iterations
cfg_path = os.path.join(os.path.dirname(__file__), "..", "agentic", "config.json")
try:
    with open(cfg_path, "r", encoding="utf-8") as _fh:
        _CFG = _json.load(_fh)
except Exception:
    _CFG = {}

LOG_PATH = _CFG.get("log_path", os.path.join(os.path.dirname(__file__), "..", "agentic_agent.log"))
DEFAULT_MAX_ITERS = int(_CFG.get("max_iterations", 12))

def _append_log(kind: str, text: str, meta: dict | None = None):
    try:
        with open(LOG_PATH, "a", encoding="utf-8") as _log:
            ts = datetime.utcnow().isoformat() + "Z"
            _log.write(f"[{ts}] {kind}: {text}\n")
            if meta:
                try:
                    _log.write("    " + _json.dumps(meta, ensure_ascii=False) + "\n")
                except Exception:
                    _log.write("    META: " + str(meta) + "\n")
    except Exception:
        # never fail the workflow because logging failed
        pass

class GraphState(TypedDict, total=False):
    messages: list
    # track executed tool call ids to avoid re-running the same tool and
    # prevent infinite loops when the LLM keeps returning the same tool call
    executed_tool_ids: list
    # track executed tool signatures (fingerprints of name+args) so that
    # models that re-issue the same logical request with a fresh id don't
    # cause re-execution. Each signature is a deterministic JSON string.
    executed_tool_signatures: list
    # track loop iterations and configurable maximum to prevent infinite loops
    loop_count: int
    max_iterations: int

##6️⃣ LLM node that can call tools

def llm_node(state: GraphState):
    # iteration guard and primary LLM call
    loop_count = int(state.get("loop_count", 0)) + 1
    max_iters = int(state.get("max_iterations", DEFAULT_MAX_ITERS))

    if loop_count > max_iters:
        stop_msg = HumanMessage(content=f"STOP: max iterations ({max_iters}) reached")
        _append_log("SYSTEM", f"Max iterations reached: {max_iters}")
        return {"messages": state.get("messages", []) + [stop_msg], "loop_count": loop_count, "max_iterations": max_iters}

    response = llm.invoke(state["messages"])
    # log LLM response human-readable
    try:
        rv_content = getattr(response, "content", str(response))
        rv_tcs = getattr(response, "tool_calls", None)
        rv_errs = getattr(response, "validation_errors", None)
        _append_log("LLM", rv_content, {"tool_calls": rv_tcs, "validation_errors": rv_errs})
    except Exception:
        pass

    # If the model returned tool_calls, filter out any tool_calls whose
    # logical signature we have already executed. This covers the case
    # where the model issues a new unique id each loop but the requested
    # action is identical.
    def _signature_for(tc: dict) -> str:
        # deterministic JSON string of [name, sorted args]
        try:
            import json

            name = tc.get("name")
            args = tc.get("args") or {}
            return json.dumps([name, args], sort_keys=True)
        except Exception:
            return str((tc.get("name"), tuple(sorted((tc.get("args") or {}).items()))))

    executed_signatures = list(state.get("executed_tool_signatures", []))
    if getattr(response, "tool_calls", None):
        filtered = []
        for tc in response.tool_calls:
            sig = _signature_for(tc)
            if sig not in executed_signatures:
                filtered.append(tc)
        # attach filtered list back to response (mutate for graph use)
        try:
            response.tool_calls = filtered
        except Exception:
            # If the response object is immutable, wrap a tiny container
            class _R:
                pass

            newr = _R()
            for k, v in response.__dict__.items():
                setattr(newr, k, v)
            newr.tool_calls = filtered
            response = newr

    # If the model returned (remaining) tool_calls, proceed normally
    if getattr(response, "tool_calls", None):
        return {"messages": state["messages"] + [response], "loop_count": loop_count, "max_iterations": max_iters}

    # If the model only returned a human-readable plan (no tool_calls),
    # ask a single follow-up requesting a compact JSON action. This helps
    # LLMs that prefer to explain first then provide a machine-readable
    # instruction. We only retry once here to avoid loops.
    last_human = None
    # Try to extract the last human message content from the state
    for m in reversed(state.get("messages", [])):
        try:
            txt = getattr(m, "content", None)
        except Exception:
            txt = None
        if txt:
            last_human = txt
            break

    follow_up = (
        "You previously returned a human-readable plan. If you intend the assistant to call a tool, "
        "reply ONLY with a single compact JSON object with two keys: \"action\" and \"params\". "
        "Example: {\"action\":\"run_simulation_setup\",\"params\":{\"pdb_file\":\"0.pdb\",\"wdir\":\"/path/to/dir\"}}. "
    )
    if last_human:
        follow_up = follow_up + " Now produce that JSON for the instruction: \"" + last_human + "\""

    # invoke the LLM one more time with the explicit follow-up prompt
    follow_resp = llm.invoke([follow_up])

    # If the follow-up produced tool_calls, return it so the graph can run tools
    if getattr(follow_resp, "tool_calls", None):
        # append both responses for traceability
        return {"messages": state["messages"] + [response, follow_resp], "loop_count": loop_count, "max_iterations": max_iters}

    # otherwise append both responses (original explanation + follow-up) and stop
    return {"messages": state["messages"] + [response, follow_resp], "loop_count": loop_count, "max_iterations": max_iters}


##7️⃣ Tool execution node

def tool_node(state: GraphState):
    last_msg = state["messages"][-1]

    tool_messages = []

    executed = list(state.get("executed_tool_ids", []))
    for call in getattr(last_msg, "tool_calls", []) or []:
        # Compute a deterministic signature for the logical tool call. We
        # use name + args (sorted) so that re-issued calls with different
        # LLM-assigned ids still map to the same signature and won't be
        # re-executed.
        try:
            import json

            sig = json.dumps([call.get("name"), call.get("args") or {}], sort_keys=True)
        except Exception:
            sig = str((call.get("name"), tuple(sorted((call.get("args") or {}).items()))))

        # Skip if we've already executed this logical request
        executed_signatures = list(state.get("executed_tool_signatures", []))
        if sig in executed_signatures:
            continue
        # Skip if we've already executed this tool_call id
        if call.get("id") in executed:
            # still add signature to executed_signatures to be safe
            executed_signatures.append(sig)
            continue
        if call["name"] == "run_simulation_setup":
            # Normalize args (map pdb/pdb_file and sanitize tokenized paths)
            args_map = dict(call.get("args", {}) or {})
            # accept either key names
            pdb_key = args_map.get("pdb") or args_map.get("pdb_file")
            wdir_key = args_map.get("wdir") or args_map.get("workdir") or args_map.get("working_dir")

            def _compact_text(t: str) -> str:
                if not isinstance(t, str):
                    return t
                # remove backticks and zero-width spaces
                t = t.replace('`', ' ')
                t = t.replace('\u200b', '')
                # remove spaces around slashes, dots and underscores which tokenized streams often introduce
                t = re.sub(r"\s*/\s*", "/", t)
                t = re.sub(r"\s*\.\s*", ".", t)
                t = re.sub(r"\s*_\s*", "_", t)
                # collapse long runs of whitespace
                t = re.sub(r"\s+", " ", t)
                # Additionally, for path-like strings remove accidental spaces
                # inside path segments such as 'my drive' -> 'mydrive'. We only
                # do this when the string looks like a path (contains '/').
                s = t.strip()
                if '/' in s:
                    parts = s.split('/')
                    new_parts = []
                    for p in parts:
                        # if the segment contains spaces and is not clearly a
                        # filename with an extension, remove internal spaces.
                        if ' ' in p:
                            # preserve dots (extensions) but remove spaces in the
                            # base name portion
                            if '.' in p:
                                base, _, rest = p.partition('.')
                                base = base.replace(' ', '')
                                p = base + ('.' + rest if rest else '')
                            else:
                                p = p.replace(' ', '')
                        new_parts.append(p)
                    s = '/'.join(new_parts)
                return s

            if pdb_key:
                pdb_val = _compact_text(pdb_key)
            else:
                pdb_val = None

            if wdir_key:
                wdir_val = _compact_text(wdir_key)
            else:
                wdir_val = None

            # If path looks like it was tokenized (contains spaces near /), compacting should fix it.
            # Validate existence and provide a clearer error if missing.
            if wdir_val:
                wdir_norm = os.path.normpath(wdir_val)
                if not os.path.exists(wdir_norm):
                    # try one more aggressive compaction removing spaces entirely around words
                    wdir_try = re.sub(r"\s+", "", wdir_val)
                    wdir_try = os.path.normpath(wdir_try)
                    if os.path.exists(wdir_try):
                        wdir_norm = wdir_try
                    else:
                        # Do not create directories automatically in this test; raise informative error
                        raise FileNotFoundError(
                            f"Working directory not found after normalization: '{wdir_val}' -> '{wdir_norm}'.\n"
                            "Check the path in your prompt (avoid tokenized spaces).\n"
                            "You can run the test with a mock LLM or create the directory manually."
                        )
            else:
                wdir_norm = None

            # Build normalized args to pass to the tool
            tool_args = {}
            if pdb_val:
                tool_args['pdb_file'] = pdb_val
            if wdir_norm:
                tool_args['wdir'] = wdir_norm

            result = run_simulation_setup.invoke(tool_args)
            # Log tool execution in human-readable form
            try:
                _append_log("TOOL", f"Executed {call.get('name')} with args={tool_args} -> result={result}")
            except Exception:
                pass
            tool_messages.append(
                ToolMessage(
                    content=result,
                    tool_call_id=call["id"]
                )
            )
            executed.append(call.get("id"))
            executed_signatures.append(sig)

    # return updated messages and record executed ids and signatures in state
    return {
        "messages": state["messages"] + tool_messages,
        "executed_tool_ids": executed,
        "executed_tool_signatures": executed_signatures,
        "loop_count": state.get("loop_count", 0),
        "max_iterations": state.get("max_iterations", DEFAULT_MAX_ITERS),
    }

##8️⃣ Build the workflow graph
from langgraph.graph import StateGraph, END
workflow = StateGraph(GraphState)
workflow.add_node("llm", llm_node)
workflow.add_node("tools", tool_node)

workflow.set_entry_point("llm")

workflow.add_conditional_edges(
    "llm",
    # only go to tools if the last LLM response contains at least one
    # tool_call whose id hasn't already been executed
    lambda s: (
        "tools"
        if any(
            (tc.get("id") not in s.get("executed_tool_ids", []))
            for tc in (getattr(s["messages"][-1], "tool_calls", []) or [])
        )
        else END
    )
)

workflow.add_edge("tools", "llm")

app = workflow.compile()

##9️⃣ Invoke the graph with a prompt

result = app.invoke({
    "messages": [
        HumanMessage(
            content="Prepare a simulation setup for a pdb file name 0.pdb and  the working directory: wdir = /mnt/mydrive/pseudokinase/pseudoNcontrol_AF3/0_MD_simulation/batch_sim_6/test/"
        )
    ]
})

for m in result["messages"]:
    print(m.content)