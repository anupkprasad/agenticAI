#!/usr/bin/env python3
import sys; sys.path.insert(0, ".")
from run_agenticAIWork import _is_action, _normalize_action

tests = [
    ("please redo simulation setup with the updated execution plan", True, "recommend:"),
    ("redo setup", True, "retry"),
    ("redo", True, "redo"),
    ("retry", True, "retry"),
    ("approved", True, "approved"),
    ("looks good", True, "approved"),
    ("please redo", True, "retry"),
    ("rerun the simulation", True, "retry"),
    ("please rerun setup with CHARMM", True, "recommend:"),
    ("what files were generated?", False, ""),
    ("show me the topology", False, ""),
    ("how many residues?", False, ""),
    ("recommend: use CHARMM", True, "recommend:"),
    ("go ahead", True, "approved"),
    ("stop the workflow", True, "exit"),
    ("run it again", True, "retry"),
    ("run setup again with updated plan", True, "recommend:"),
]

passed = 0
for text, expect_action, expect_prefix in tests:
    is_act = _is_action(text)
    norm = _normalize_action(text.lower().strip())
    ok_action = is_act == expect_action
    ok_prefix = norm.startswith(expect_prefix) if expect_prefix else not norm
    status = "OK" if (ok_action and ok_prefix) else "FAIL"
    if status == "FAIL":
        print(f'{status}: "{text}" -> is_action={is_act}(expect={expect_action}), norm="{norm}"(expect prefix="{expect_prefix}")')
    else:
        passed += 1

print(f"{passed}/{len(tests)} passed")
