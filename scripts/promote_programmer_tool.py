#!/usr/bin/env python3
"""
Promote a programmer-generated @tool into the standard analysis toolbox.

Copies a Python file from {working_dir}/programmer/ into src/analysis/ and
prints the import line to add in agentic/analysis/tools.py + tool_buckets.py.

Does NOT auto-edit the registry — review the tool, then register it.
"""
from __future__ import annotations

import argparse
import shutil
from pathlib import Path


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("source", help="Path to generated tool .py under programmer/")
    p.add_argument(
        "--name",
        default=None,
        help="Destination basename under src/analysis/ (default: source name)",
    )
    p.add_argument(
        "--repo",
        default=None,
        help="Repo root (default: parent of this scripts/ tree)",
    )
    args = p.parse_args()
    src = Path(args.source).resolve()
    if not src.is_file():
        print(f"ERROR: not a file: {src}")
        return 1
    repo = Path(args.repo).resolve() if args.repo else Path(__file__).resolve().parents[1]
    dest_name = args.name or src.name
    if not dest_name.endswith(".py"):
        dest_name += ".py"
    dest = repo / "src" / "analysis" / dest_name
    if dest.exists():
        print(f"ERROR: destination exists: {dest}")
        return 1
    shutil.copy2(src, dest)
    print(f"Copied → {dest}")
    print("Next:")
    print(f"  1. Review {dest}")
    print("  2. Import the @tool in agentic/analysis/tools.py")
    print("  3. Add the tool name to agentic/analysis/tool_buckets.py (per_sim/combined/shared)")
    print("  4. Document in docs/CLEAN_AND_OPT.md / ANALYSIS_TOOLS.md")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
