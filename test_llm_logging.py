"""
Test LLM logging improvements - full multiline prompts and responses
"""
from agentic.utils import log_llm_interaction

# Test with a multiline prompt and response
test_prompt = """Generate a GROMACS MDP file for energy minimization.

Configuration:
- Force Field: amber99sb-ildn
- Water Model: tip3p
- Engine: gromacs

Requirements:
1. Use steepest descent algorithm
2. Set maximum steps to 50000
3. Energy convergence criteria: 1000 kJ/mol/nm
4. Output frequency: 100 steps

Generate appropriate GROMACS MDP file content with proper settings."""

test_response = """; Energy Minimization MDP File
; Generated for GROMACS with AMBER99SB-ILDN force field

; Minimization settings
integrator  = steep
nsteps      = 50000
emtol       = 1000.0
emstep      = 0.01

; Output control
nstlog      = 100
nstenergy   = 100
nstxout     = 0
nstvout     = 0
nstfout     = 0

; Neighbor searching
cutoff-scheme = Verlet
ns_type     = grid
nstlist     = 10
rcoulomb    = 1.0
rvdw        = 1.0

; Electrostatics
coulombtype = PME
pme_order   = 4
fourierspacing = 0.16

; Temperature and pressure coupling - off for minimization
tcoupl      = no
pcoupl      = no

; Periodic boundary conditions
pbc         = xyz

; Generate velocities
gen_vel     = no
"""

print("Testing full LLM interaction logging...\n")
print("="*70)

log_llm_interaction(
    agent_name="test.energy_minimization",
    prompt=test_prompt,
    response=test_response,
    is_mock=False
)

print("\n✅ LLM logging test complete!")
print("   Check agent_conversation.log to see full multiline format")
print("   - Full prompt visible with all lines")
print("   - Full response visible with all lines")
print("   - Separated by visual dividers for readability")
