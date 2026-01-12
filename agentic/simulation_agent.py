from __future__ import annotations

from typing import Optional
import asyncio
from dataclasses import dataclass
import logging

# We avoid importing the heavy simulation setup at module import time so the
# package remains importable in lightweight environments. The real
# `call_simulation_setup` will be imported lazily inside `plan_simulation` if
# available. If not available, the fallback below provides safe behavior.
def _fallback_call_simulation_setup(pdb_file: str, wdir: str = "/tmp/mock_run", **kwargs) -> dict:
    """
    Lightweight fallback that performs a minimal on-disk simulation setup so
    the rest of the workflow can exercise file creation and job script
    generation without depending on the full heavy toolchain.

    Behavior:
    - create `wdir` if missing
    - copy the provided pdb_file into `wdir` (preserve name)
    - create `jobs/run_sim.sh` containing a simple placeholder run command
    - return a dict with status, output_dir, job_script and files created
    """
    import os
    import shutil
    from pathlib import Path

    p = Path(wdir)
    try:
        p.mkdir(parents=True, exist_ok=True)
    except Exception:
        return {"status": "error", "message": f"Failed to create working dir {wdir}"}

    # Resolve pdb path
    pdb_src = Path(pdb_file)
    if not pdb_src.is_absolute():
        pdb_src = (Path.cwd() / pdb_src).resolve()

    if not pdb_src.exists():
        msg = f"Input PDB not found: {pdb_src}. Created skeleton setup in {wdir}"
        input_present = False
    else:
        input_present = True

    created = []
    # copy the pdb into wdir (if present) without mutating the original
    try:
        if input_present:
            dest = p / pdb_src.name
            # Avoid copying a file onto itself (can truncate). If src and
            # dest resolve to the same path, skip the copy.
            try:
                if dest.resolve() == pdb_src.resolve():
                    # already in place
                    created.append(str(dest))
                else:
                    try:
                        shutil.copy2(pdb_src, dest)
                        created.append(str(dest))
                    except Exception:
                        # fallback to symlink if copy fails
                        try:
                            if dest.exists():
                                dest.unlink()
                            os.symlink(str(pdb_src), str(dest))
                            created.append(str(dest))
                        except Exception:
                            pass
            except Exception:
                # If resolve() fails for some reason, attempt a safe copy
                try:
                    shutil.copy2(pdb_src, dest)
                    created.append(str(dest))
                except Exception:
                    pass
    except Exception:
        pass

    # create jobs directory and a simple run script
    jobs_dir = p / "jobs"
    try:
        jobs_dir.mkdir(parents=True, exist_ok=True)
    except Exception:
        pass

    job_script = jobs_dir / "run_sim.sh"
    try:
        with open(job_script, "w", encoding="utf-8") as fh:
            fh.write("#!/bin/bash\n")
            fh.write("# Placeholder simulation run script\n")
            fh.write("# Replace with your engine invocation, e.g.:\n")
            fh.write("# gmx mdrun -s topol.tpr -deffnm run\n")
            if input_present:
                fh.write(f"# Input PDB: {pdb_src}\n")
            else:
                fh.write(f"# Input PDB (missing): {pdb_src}\n")
        try:
            job_script.chmod(0o755)
        except Exception:
            pass
        created.append(str(job_script))
    except Exception:
        pass

    result = {
        "status": "mocked" if not input_present else "prepared",
        "output_dir": str(p.resolve()),
        "job_script": str(job_script),
        "files_created": created,
        "message": (msg if not input_present else f"Setup prepared for {pdb_src.name} in {wdir}"),
    }
    return result

from .async_utils import run_in_thread


@dataclass
class SimulationAgent:
    """Agent responsible for preparing and running simulation setup.

    The agent exposes async methods so callers can integrate it into an
    async orchestration pipeline. Blocking setup functions are executed in
    a threadpool.
    """
    name: str = "simulation_agent"

    async def plan_simulation(self, pdb_file: str, wdir: str, **kwargs) -> dict:
        """Plan and run a simulation setup. Returns a dict with metadata.

        Runs the blocking `call_simulation_setup` in a thread so it doesn't
        block the event loop.
        """
        from pathlib import Path
        import shutil
        import os

        # Ensure working directory exists
        wdir_path = Path(wdir)
        wdir_path.mkdir(parents=True, exist_ok=True)

        # Resolve and copy the input pdb into the working dir to avoid
        # mutating the original file when the underlying toolchain runs.
        src = Path(pdb_file)
        if not src.is_absolute():
            src = (Path.cwd() / src).resolve()

        if not src.exists():
            # Let the fallback handle missing input gracefully
            dest_pdb = str(wdir_path / Path(pdb_file).name)
        else:
            dest_pdb = str(wdir_path / src.name)
            try:
                dest_path = Path(dest_pdb)
                # If source and destination are the same file, skip copy to avoid corruption
                try:
                    if src.resolve() == dest_path.resolve():
                        pass
                    else:
                        shutil.copy2(src, dest_pdb)
                except Exception:
                    # If resolve failed or other issue, try a safe copy with overwrite
                    try:
                        shutil.copy2(src, dest_pdb)
                    except Exception:
                        # fallback to symlink if copy fails
                        try:
                            if os.path.exists(dest_pdb):
                                os.remove(dest_pdb)
                            os.symlink(str(src), dest_pdb)
                        except Exception:
                            pass
            except Exception:
                # ignore copy errors
                pass

        # Try to import the real setup implementation lazily
        real_call = None
        try:
            from src.python.setup.sim_setup import call_simulation_setup as real_call_fn

            real_call = real_call_fn
        except Exception:
            real_call = None

        if real_call is not None:
            logging.getLogger(__name__).info("Using real call_simulation_setup implementation from src.python.setup.sim_setup")
            # Normalize absolute paths
            dest_pdb_abs = os.path.abspath(dest_pdb)
            wdir_abs = os.path.abspath(str(wdir_path))

            def _call_real_in_cwd(fn, pdb_abs: str, wdir_abs: str, **kw):
                """Run the real setup function from inside the working dir so
                relative path handling in downstream tools works as expected.
                Pass the pdb filename (basename) to the real function.
                """
                import os as _os
                cwd = _os.getcwd()
                try:
                    _os.chdir(wdir_abs)
                    return fn(_os.path.basename(pdb_abs), wdir=wdir_abs, **kw)
                finally:
                    _os.chdir(cwd)

            try:
                return await run_in_thread(_call_real_in_cwd, real_call, dest_pdb_abs, wdir_abs, **kwargs)
            except Exception as e:
                # If the real call fails, fall back to the lightweight impl
                logging.getLogger(__name__).exception("Real call_simulation_setup raised an exception; falling back to lightweight implementation")
                return await run_in_thread(_fallback_call_simulation_setup, dest_pdb_abs, wdir=wdir_abs, error=str(e), **kwargs)
        # No real implementation available; use fallback
        logging.getLogger(__name__).info("No real call_simulation_setup found; using fallback implementation")
        return await run_in_thread(_fallback_call_simulation_setup, dest_pdb, wdir=wdir, **kwargs)

    async def prepare_and_validate(self, pdb_source: str, wdir: str) -> dict:
        """Higher-level helper that could fetch PDB from remote sources,
        validate it and then call plan_simulation. Currently a thin wrapper.
        """
        # In a real implementation we'd fetch from UniProt/AlphaFold here.
        return await self.plan_simulation(pdb_source, wdir)
