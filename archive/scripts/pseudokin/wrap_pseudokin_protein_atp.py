#!/usr/bin/env python3
"""
PBC-wrap all pseudoKin trajectories centering Protein|ATP (conv_sim.sh style).

Writes ``pseudoKin/{uid}/hpc/mdWrap.xtc``. Skips when a non-stale wrap already
exists (unless ``--force``). Uses a process pool like other scripts/ launchers.
"""
from __future__ import annotations

import argparse
import os
import sys
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path
from typing import Any, Dict, List

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

BASE = REPO / "pseudoKin"

# Prefer conda gmx (same pattern as scripts/update_local_fel_poc_analysis.py).
_GMX = Path.home() / "conda_envs" / "ollama_env" / "bin" / "gmx"
if _GMX.is_file():
    os.environ["PATH"] = f"{_GMX.parent}:{os.environ.get('PATH', '')}"


def _uids_with_md_xtc() -> List[str]:
    return sorted(
        p.name
        for p in BASE.iterdir()
        if p.is_dir() and (p / "hpc" / "md.xtc").is_file() and (p / "hpc" / "md.tpr").is_file()
    )


def _wrap_one(payload: Dict[str, Any]) -> Dict[str, Any]:
    """Process-pool worker: wrap one simulation."""
    from src.analysis.trajectory_wrapper import _wrap_trajectory_impl

    uid = payload["uid"]
    hpc = BASE / uid / "hpc"
    try:
        result = _wrap_trajectory_impl(
            tpr_file=str(hpc / "md.tpr"),
            trajectory_file=str(hpc / "md.xtc"),
            output_file="mdWrap.xtc",
            ligand=payload.get("ligand") or "ATP",
            dt=int(payload.get("dt") or 100),
            working_dir=str(hpc),
            force=bool(payload.get("force")),
        )
        return {
            "uid": uid,
            "success": bool(result.get("success")),
            "skipped": bool(result.get("skipped")),
            "centering_group": result.get("centering_group"),
            "wrapped_trajectory": result.get("wrapped_trajectory"),
            "error": result.get("error"),
            "message": result.get("message"),
        }
    except Exception as exc:  # noqa: BLE001 — report per-sim failure
        return {"uid": uid, "success": False, "error": str(exc)}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--uids",
        nargs="*",
        default=None,
        help="Optional UniProt ids (default: all pseudoKin sims with md.tpr+md.xtc)",
    )
    parser.add_argument("--ligand", default="ATP", help="Ligand index name (default ATP)")
    parser.add_argument("--dt", type=int, default=100, help="Output frame spacing ps")
    parser.add_argument(
        "--max-workers",
        type=int,
        default=8,
        help="Parallel wrap workers (default 8; I/O heavy)",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Rebuild mdWrap.xtc even if it already exists",
    )
    args = parser.parse_args()

    uids = args.uids or _uids_with_md_xtc()
    if not uids:
        raise SystemExit(f"No sims with md.tpr+md.xtc under {BASE}")

    payloads = [
        {"uid": uid, "ligand": args.ligand, "dt": args.dt, "force": args.force}
        for uid in uids
    ]
    workers = max(1, min(int(args.max_workers), len(payloads)))
    print(
        f"Wrapping {len(payloads)} sims (ligand={args.ligand}, dt={args.dt}, "
        f"force={args.force}, workers={workers})"
    )

    ok = skip = fail = 0
    failures: List[Dict[str, Any]] = []
    with ProcessPoolExecutor(max_workers=workers) as ex:
        futs = {ex.submit(_wrap_one, p): p["uid"] for p in payloads}
        for fut in as_completed(futs):
            uid = futs[fut]
            try:
                r = fut.result()
            except Exception as exc:  # noqa: BLE001
                r = {"uid": uid, "success": False, "error": str(exc)}
            if r.get("success"):
                if r.get("skipped"):
                    skip += 1
                    print(f"  SKIP {uid}: existing mdWrap.xtc")
                else:
                    ok += 1
                    print(
                        f"  OK   {uid}: center={r.get('centering_group')} "
                        f"→ {Path(r.get('wrapped_trajectory') or '').name}"
                    )
            else:
                fail += 1
                failures.append(r)
                print(f"  FAIL {uid}: {r.get('error')}")

    print(f"Done: wrapped={ok} skipped={skip} failed={fail}/{len(payloads)}")
    if fail:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
