#!/usr/bin/env python3
"""Fast Code Ocean smoke checks for the SimAgent manuscript freeze.

Verifies imports, CLI entry, demo inputs, and that --no-llm is accepted.
Does not submit HPC jobs or call a live LLM.
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path


def _ok(msg: str) -> None:
    print(f"[OK] {msg}")


def _fail(msg: str) -> None:
    print(f"[FAIL] {msg}", file=sys.stderr)
    raise SystemExit(1)


def main() -> int:
    # codeocean/scripts -> codeocean -> repo root
    repo = Path(__file__).resolve().parents[2]
    demo = repo / "codeocean" / "data" / "demo"
    features = repo / "codeocean" / "data" / "features"

    sys.path.insert(0, str(repo))

    # 1) Core imports
    try:
        import agentic  # noqa: F401
        from agentic.llm import LLMClient  # noqa: F401
        import MDAnalysis  # noqa: F401
        import numpy  # noqa: F401
        import pandas  # noqa: F401
        import matplotlib  # noqa: F401
    except Exception as exc:
        _fail(f"import error: {exc}")
    _ok("Python package imports")

    # 2) CLI help
    help_proc = subprocess.run(
        [sys.executable, str(repo / "SimAgent.py"), "--help"],
        cwd=str(repo),
        capture_output=True,
        text=True,
        timeout=120,
    )
    if help_proc.returncode != 0:
        _fail(f"SimAgent.py --help failed:\n{help_proc.stderr}")
    if "--no-llm" not in help_proc.stdout and "--no-llm" not in help_proc.stderr:
        # argparse help may go to stdout
        _fail("SimAgent.py --help missing --no-llm flag")
    _ok("SimAgent.py --help")

    # 3) Demo inputs present
    pdbs = sorted(demo.glob("*.pdb"))
    if len(pdbs) < 4:
        _fail(f"expected >=4 demo PDBs in {demo}, found {len(pdbs)}")
    _ok(f"demo PDBs ({len(pdbs)})")

    zcsv = features / "classification_features_zscore.csv"
    if not zcsv.is_file():
        _fail(f"missing {zcsv}")
    _ok("feature CSV present")

    # 4) Confirm --no-llm path is selectable (dry: help already checked;
    #    also ensure LLMClient can be constructed without network for offline mode)
    client = LLMClient(model="gpt-oss:20b", base_url=None, provider="ollama")
    _ok(f"LLMClient constructible for offline use (available={client.available})")

    print("\nSmoke test passed.")
    print("Note: full MD / Ollama / SLURM campaigns are not executed in this capsule.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
