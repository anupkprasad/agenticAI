"""Fast unit test to exercise the simulation setup function directly.

This bypasses the LangGraph runtime and LLM invocation so it runs quickly
and is suitable for iterative development. It mocks the heavy
`call_simulation_setup` implementation to avoid running GROMACS or shell
commands and measures elapsed time for a direct call.
"""
import time
import importlib, sys, types

# Inject a fake sim_setup module to avoid running heavy external commands
sim_mod = types.ModuleType('src.python.setup.sim_setup')
def fake_call(pdb_file, wdir):
    # simulate lightweight work
    start = time.time()
    # small sleep to emulate processing (not necessary, but realistic)
    time.sleep(0.01)
    elapsed = time.time() - start
    return {"status": "mocked", "output_dir": wdir, "message": f"MOCK setup for {pdb_file} in {wdir} (took {elapsed:.3f}s)"}

sim_mod.call_simulation_setup = fake_call
sys.modules['src.python.setup.sim_setup'] = sim_mod

def run_direct():
    from src.python.setup.sim_setup import call_simulation_setup
    start = time.time()
    res = call_simulation_setup('0.pdb', wdir='/tmp/mock_test')
    elapsed = time.time() - start
    print('Result:', res)
    print(f'Elapsed time (direct call): {elapsed:.3f}s')

if __name__ == '__main__':
    run_direct()
