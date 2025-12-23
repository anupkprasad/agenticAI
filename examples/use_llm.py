"""Example script showing how to instantiate LLMClient and call agents.

This script uses the wrapper in `agentic/llm.py` and the agents.
It will run in mock mode if the real ChatOllama client isn't installed.
"""
from agentic.llm import LLMClient
from agentic.agents import SimulationSetupAgent, AnalysisAgent


def main():
    llm = LLMClient(model="gpt-oss:120b", base_url="http://172.22.149.139:11434")
    setup = SimulationSetupAgent(llm_client=llm)
    plan = setup.plan_simulation("example.pdb", params={"use_llm": True})
    print("Plan with LLM suggestion:\n", plan.get("llm_suggestion"))

    ana = AnalysisAgent(llm_client=llm)
    summary = ana.analyze_simulation("results/")
    print("LLM analysis summary:\n", summary.get("llm_summary"))


if __name__ == "__main__":
    main()
