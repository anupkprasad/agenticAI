#!/usr/bin/env python3
"""Quick validation of HITL recommendation fixes."""
import sys
sys.path.insert(0, ".")

from agentic.human_checkpoints import HumanCheckpoints
print("Import OK")

# Test 1: CHARMM force field
state = {"force_field": "amber99sb-ildn", "water_model": "tip3p"}
HumanCheckpoints._apply_parameter_overrides("use CHARMM force field", state)
assert state["force_field"] == "charmm27", f"Expected charmm27, got {state['force_field']}"
print(f"Test 1 OK: force_field -> {state['force_field']}")

# Test 2: Multi-param override
state2 = {"force_field": "amber99sb-ildn", "water_model": "tip3p"}
HumanCheckpoints._apply_parameter_overrides("switch to OPLS-AA and SPC/E water model at 310 K", state2)
assert state2["force_field"] == "oplsaa", f"Expected oplsaa, got {state2['force_field']}"
assert state2["water_model"] == "spce", f"Expected spce, got {state2['water_model']}"
assert state2["temperature"] == 310.0, f"Expected 310.0, got {state2.get('temperature')}"
print(f"Test 2 OK: ff={state2['force_field']}, wm={state2['water_model']}, T={state2['temperature']}")

# Test 3: No override when no keywords match
state3 = {"force_field": "amber99sb-ildn", "water_model": "tip3p"}
HumanCheckpoints._apply_parameter_overrides("please retry the build topology step", state3)
assert state3["force_field"] == "amber99sb-ildn"
assert state3["water_model"] == "tip3p"
print("Test 3 OK: no spurious override")

# Test 4: Pressure override
state4 = {}
HumanCheckpoints._apply_parameter_overrides("use pressure 1.5 bar", state4)
assert state4["pressure"] == 1.5, f"Expected 1.5, got {state4.get('pressure')}"
print(f"Test 4 OK: pressure={state4['pressure']}")

# Test 5: _process_feedback with recommend stores + overrides
state5 = {
    "force_field": "amber99sb-ildn",
    "water_model": "tip3p",
    "human_feedback": "",
    "warnings": [],
    "setup_issues": ["some issue"],
    "topology": "/path/topol.top",
    "coordinates": "/path/system.gro",
}
state5 = HumanCheckpoints._process_feedback(
    "recommend: use CHARMM force field and temperature 310 K",
    state5, "setup", "setup",
    clear_keys=["coordinates", "setup_report", "setup_issues"]
)
assert state5["human_recommendation"] == "use CHARMM force field and temperature 310 K"
assert state5["force_field"] == "charmm27"
assert state5["temperature"] == 310.0
assert state5["next_node"] == "setup"
assert state5["coordinates"] is None  # cleared for retry
print(f"Test 5 OK: recommend flow works, ff={state5['force_field']}, T={state5['temperature']}")

print("\nAll tests passed!")
