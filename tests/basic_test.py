import os
import sys
ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from typing import TypedDict
from agentic.llm import LLMClient

## define the graph state type
class GraphState(TypedDict):
    prompt: str
    response: str
    token_count: int

def llm_node(state: GraphState) -> dict:
    model = LLMClient(
        model="gpt-oss:120b",
        base_url="http://172.22.149.139:11434"
    )
    response = model.prompt(state["prompt"])
    return {"response": response}


def token_counter_node(state: GraphState) -> dict:
    tokens = state["response"].split()
    return {"token_count": len(tokens)}



## build the workflow graph
from langgraph.graph import StateGraph, END

workflow = StateGraph(GraphState)

workflow.add_node("LLM_Model", llm_node)
workflow.add_node("Get_Token_Counter", token_counter_node)

workflow.add_edge("LLM_Model", "Get_Token_Counter")
workflow.set_entry_point("LLM_Model")
workflow.add_edge("Get_Token_Counter", END)

app = workflow.compile()

result = app.invoke({
    "prompt": "What is an AI agent?"
})

print(result["response"])
print("Tokens:", result["token_count"])
