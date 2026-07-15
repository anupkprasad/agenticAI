#!/usr/bin/env python3
"""Batch consensus-mapped Cα PCA/FEL (local basis, no reference projection)."""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Per-sim PCA/FEL on consensus Cα residues without projecting onto "
            "a reference PCA model. Writes pseudoKin/analysis/consensus_local_fel/"
        )
    )
    parser.add_argument(
        "--base-dir",
        default=str(REPO / "pseudoKin"),
        help="Campaign root with per-UniProt simulation directories",
    )
    parser.add_argument(
        "--labels",
        nargs="*",
        default=None,
        help="Optional UniProt labels (default: all sims with hpc/)",
    )
    parser.add_argument(
        "--frame-interval",
        type=int,
        default=1,
        help="Trajectory stride (default 1)",
    )
    parser.add_argument(
        "--overwrite",
        action="store_true",
        help="Recompute even if fel_features.json exists",
    )
    parser.add_argument(
        "--max-workers",
        type=int,
        default=4,
        help="Parallel workers (default 4; use 1 to debug)",
    )
    args = parser.parse_args()

    from src.analysis.consensus_local_fel import run_consensus_local_fel_batch

    res = run_consensus_local_fel_batch(
        base_dir=args.base_dir,
        labels=args.labels,
        frame_interval=args.frame_interval,
        overwrite=args.overwrite,
        max_workers=args.max_workers,
    )
    print(res.get("message"), res.get("error"))
    man = res.get("manifest") or {}
    if man.get("failed"):
        print("Failures:")
        for f in man["failed"]:
            print(f"  {f}")
    if not res.get("success") and man.get("n_success", 0) == 0:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
