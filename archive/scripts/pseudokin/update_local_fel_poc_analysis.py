#!/usr/bin/env python3
"""
Update local-FEL + reference-pocket PoC analysis (output_localFEL_poc).

Steps:
  1. Rebuild star MSA to MLKL including all holo+GT sims with mdWrap.xtc
  2. Redefine MLKL ATP pocket (15 Å) and remap residues
  3. Recompute reference-pocket metrics for selected / all usable sims
  4. Recompute local whole-protein PCA/FEL for selected sims
  5. Refresh usable manifest + local_fel_ref_pock clustering (k=5)
  6. Optionally regenerate docs/ment/output_localFEL_poc draft figures

Default targets for expensive recompute:
  - six 100→200 ns extensions
  - P25092 (GUC2C; previously failed MSA coverage)
  - Q58A45 (PAN3; missing local FEL)
  - any sim whose mapped pocket resids changed after MSA rebuild
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
import time
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Set

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

BASE = REPO / "pseudoKin"
AN = BASE / "analysis"
POCKET = AN / "reference_pocket"
DRAFT = REPO / "docs" / "ment" / "output_localFEL_poc"

EXTENDED = ["o60674", "p25092", "q05823", "q8tea7", "q92519", "q9nsy0"]
ALWAYS_FEL = sorted(set(EXTENDED + ["q58a45"]))
ALWAYS_POCKET = sorted(set(EXTENDED + ["p25092"]))

_GMX = Path.home() / "conda_envs" / "ollama_env" / "bin" / "gmx"
if _GMX.is_file():
    os.environ["PATH"] = f"{_GMX.parent}:{os.environ.get('PATH', '')}"


def _backup(path: Path, bak_dir: Path) -> None:
    if not path.exists():
        return
    bak_dir.mkdir(parents=True, exist_ok=True)
    dst = bak_dir / path.name
    if path.is_dir():
        if dst.exists():
            shutil.rmtree(dst)
        shutil.copytree(path, dst)
    else:
        shutil.copy2(path, dst)
    print(f"  backed up {path.name} -> {dst}")


def _sim_uids_with_wrap() -> List[str]:
    return sorted(
        p.name
        for p in BASE.iterdir()
        if p.is_dir() and (p / "hpc" / "mdWrap.xtc").is_file()
    )


def _topo_traj(uid: str) -> tuple[str, str]:
    hpc = BASE / uid / "hpc"
    tpr = hpc / "md.tpr"
    xtc = hpc / "mdWrap.xtc"
    if not xtc.is_file():
        raise FileNotFoundError(f"missing wrap: {xtc}")
    if tpr.is_file():
        return str(tpr), str(xtc)
    gro = next(hpc.glob("*.gro"), None)
    if gro is None:
        raise FileNotFoundError(f"no topology in {hpc}")
    return str(gro), str(xtc)


def _resolve_pdb(uid: str, display: str) -> Optional[str]:
    from src.analysis.phylo_tree import resolve_structure_pdb

    sim_dir = str(BASE / uid)
    for key in (display, uid, uid.upper(), display.upper()):
        pdb = resolve_structure_pdb(key, sim_dir, str(BASE))
        if pdb:
            return pdb
    # Fallbacks used by some campaign layouts
    for cand in [
        BASE / f"{uid}.pdb",
        BASE / f"{display}.pdb",
        BASE / uid / f"{uid}.pdb",
        BASE / uid / "reporter" / "system_frame_0ns.pdb",
    ]:
        if cand.is_file():
            return str(cand)
    return None


def rebuild_msa_and_pocket(
    *,
    reference_display: str = "MLKL",
    map_min_coverage: float = 0.4,
) -> Dict[str, Any]:
    from src.analysis.consensus_alignment import build_consensus_sequence_alignment
    from src.analysis.consensus_pocket import (
        define_reference_consensus_pocket,
        map_consensus_pocket_residues,
    )
    from src.analysis.reference_labels import build_uniprot_display_map

    uids = _sim_uids_with_wrap()
    dm = build_uniprot_display_map(AN)
    labels: List[str] = []
    pdb_files: List[str] = []
    used_uids: List[str] = []
    missing: List[str] = []
    for uid in uids:
        display = dm.get(uid, uid.upper())
        pdb = _resolve_pdb(uid, display)
        if not pdb:
            missing.append(f"{uid}/{display}")
            continue
        labels.append(display)
        pdb_files.append(pdb)
        used_uids.append(uid)
    if missing:
        print(f"WARNING: no PDB for {missing}")
    print(
        f"Rebuilding star MSA → {reference_display} for {len(labels)} sims "
        f"(pdb-resolved)"
    )

    msa = build_consensus_sequence_alignment.func(
        working_dir=str(AN),
        reference_label=reference_display,
        labels=labels,
        pdb_files=pdb_files,
        min_coverage=0.85,
    )
    print("MSA:", msa.get("message") or msa.get("error"))
    if not msa.get("success"):
        raise SystemExit(1)

    ref_uid = next((u for u, d in dm.items() if d == reference_display), "q8nb16")
    pocket = define_reference_consensus_pocket.func(
        working_dir=str(AN),
        reference_label=reference_display,
        sim_dir=str(BASE / ref_uid),
        consensus_json="reference_msa_alignment.json",
        ligand_selection="resname ATP",
        pocket_cutoff_A=15.0,
        output_json="reference_pocket_definition.json",
    )
    print("Pocket define:", pocket.get("message") or pocket.get("error"))
    if not pocket.get("success"):
        raise SystemExit(1)

    mapped = map_consensus_pocket_residues.func(
        working_dir=str(AN),
        definition_json="reference_pocket_definition.json",
        labels=labels,
        min_coverage=float(map_min_coverage),
    )
    print(
        "Pocket map:",
        mapped.get("message") or mapped.get("error"),
        "usable=",
        len(mapped.get("usable_labels") or []),
        "skipped=",
        mapped.get("skipped_labels"),
        f"(min_coverage={map_min_coverage})",
    )
    if not mapped.get("success"):
        raise SystemExit(1)
    return {
        "uids": used_uids,
        "labels": labels,
        "display_map": dm,
        "per_label_resids": mapped.get("per_label_resids") or {},
        "per_label_coverage": mapped.get("per_label_coverage") or {},
        "usable_labels": set(mapped.get("usable_labels") or []),
    }


def _load_old_pocket_resids() -> Dict[str, List[int]]:
    """Best-effort previous pocket resids keyed by display name."""
    path = AN / "reference_pocket_definition.json"
    if not path.is_file():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    out: Dict[str, List[int]] = {}
    for lab, resids in (data.get("per_label_resids") or {}).items():
        out[str(lab)] = [int(r) for r in resids]
    return out


def _pocket_worker(payload: Dict[str, Any]) -> Dict[str, Any]:
    """Subprocess worker: recompute reference-pocket metrics for one sim."""
    sys.path.insert(0, str(REPO))
    if _GMX.is_file():
        os.environ["PATH"] = f"{_GMX.parent}:{os.environ.get('PATH', '')}"
    from src.analysis.consensus_pocket import calculate_consensus_pocket_metrics

    uid = payload["uid"]
    label = payload["label"]
    resids = payload["resids"]
    t0 = time.time()
    try:
        res = calculate_consensus_pocket_metrics.func(
            sim_dir=str(BASE / uid),
            pocket_resids=resids,
            label=label,
            ligand_selection="resname ATP",
            frame_interval=int(payload.get("frame_interval", 1)),
            working_dir=str(POCKET / uid),
            output_prefix="reference_pocket",
        )
        return {
            "uid": uid,
            "label": label,
            "success": bool(res.get("success")),
            "error": res.get("error"),
            "elapsed_s": round(time.time() - t0, 1),
            "message": res.get("message"),
        }
    except Exception as exc:  # pragma: no cover
        return {
            "uid": uid,
            "label": label,
            "success": False,
            "error": str(exc),
            "elapsed_s": round(time.time() - t0, 1),
        }


def _fel_worker(payload: Dict[str, Any]) -> Dict[str, Any]:
    """Subprocess worker: local whole-protein PCA + FEL features."""
    sys.path.insert(0, str(REPO))
    os.environ.setdefault("MPLBACKEND", "Agg")
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    # Parent may have imported pca_analyzer under fork with HAS_MATPLOTLIB=False
    import importlib
    import src.analysis.pca_analyzer as pca_mod

    pca_mod.HAS_MATPLOTLIB = True
    pca_mod.plt = plt
    pca_mod.matplotlib = matplotlib

    from src.analysis.pca_analyzer import (
        analyze_fel_landscape_features,
        calculate_free_energy_landscape,
        calculate_trajectory_pca,
    )

    uid = payload["uid"]
    t0 = time.time()
    adir = BASE / uid / "analysis"
    adir.mkdir(parents=True, exist_ok=True)
    try:
        topo, traj = _topo_traj(uid)
        pca = calculate_trajectory_pca.func(
            topology_file=topo,
            trajectory_file=traj,
            selection="protein and name CA",
            n_components=10,
            frame_interval=int(payload.get("frame_interval", 1)),
            working_dir=str(adir),
        )
        if not pca.get("success"):
            return {
                "uid": uid,
                "success": False,
                "stage": "pca",
                "error": pca.get("error"),
                "elapsed_s": round(time.time() - t0, 1),
            }
        proj = str(adir / "pca_projections.dat")
        fel = calculate_free_energy_landscape.func(
            pca_projections_file=proj,
            temperature_k=310.0,
            bins=50,
            working_dir=str(adir),
        )
        if not fel.get("success"):
            return {
                "uid": uid,
                "success": False,
                "stage": "fel",
                "error": fel.get("error"),
                "elapsed_s": round(time.time() - t0, 1),
            }
        feat = analyze_fel_landscape_features.func(
            fel_grid_file=str(adir / "fel_pc1_pc2_grid.csv"),
            pca_projections_file=proj,
            temperature_k=310.0,
            working_dir=str(adir),
            output_json=str(adir / "fel_features.json"),
            output_csv=str(adir / "fel_features.csv"),
            output_basins_csv=str(adir / "fel_basins.csv"),
            output_plot=str(adir / "fel_basins.png"),
        )
        return {
            "uid": uid,
            "success": bool(feat.get("success")),
            "stage": "features",
            "error": feat.get("error"),
            "elapsed_s": round(time.time() - t0, 1),
            "message": feat.get("message"),
        }
    except Exception as exc:  # pragma: no cover
        return {
            "uid": uid,
            "success": False,
            "stage": "exception",
            "error": str(exc),
            "elapsed_s": round(time.time() - t0, 1),
        }


def _run_pool(fn, payloads: Sequence[Dict[str, Any]], max_workers: int) -> List[Dict[str, Any]]:
    if not payloads:
        return []
    workers = max(1, min(int(max_workers), len(payloads)))
    print(f"Running {len(payloads)} jobs with {workers} workers ({fn.__name__})")
    results: List[Dict[str, Any]] = []
    if workers == 1:
        for p in payloads:
            r = fn(p)
            print(f"  {r.get('uid')}: success={r.get('success')} {r.get('elapsed_s')}s {r.get('error') or ''}")
            results.append(r)
        return results
    import multiprocessing as mp

    # spawn avoids inheriting a parent HAS_MATPLOTLIB=False via fork
    ctx = mp.get_context("spawn")
    with ProcessPoolExecutor(max_workers=workers, mp_context=ctx) as ex:
        futs = {ex.submit(fn, p): p for p in payloads}
        for fut in as_completed(futs):
            r = fut.result()
            print(
                f"  {r.get('uid')}: success={r.get('success')} "
                f"{r.get('elapsed_s')}s {r.get('error') or ''}"
            )
            results.append(r)
    return results


def select_pocket_targets(
    *,
    uids: Sequence[str],
    display_map: Dict[str, str],
    per_label_resids: Dict[str, List[int]],
    usable_labels: Set[str],
    old_resids: Dict[str, List[int]],
    recompute_all_pocket: bool,
) -> List[str]:
    targets: Set[str] = set(ALWAYS_POCKET)
    if recompute_all_pocket:
        for uid in uids:
            lab = display_map.get(uid, uid)
            if lab in usable_labels:
                targets.add(uid)
        return sorted(targets)

    for uid in uids:
        lab = display_map.get(uid, uid)
        if lab not in usable_labels:
            continue
        new_r = [int(x) for x in (per_label_resids.get(lab) or [])]
        old_r = [int(x) for x in (old_resids.get(lab) or [])]
        if not old_r or new_r != old_r:
            targets.add(uid)
            continue
        # orientation missing → archetype incomplete
        orient = POCKET / uid / "reference_pocket_ligand_orientation.csv"
        if not orient.is_file():
            targets.add(uid)
    return sorted(targets)


def write_manifest(
    *,
    uids: Sequence[str],
    display_map: Dict[str, str],
    usable_labels: Set[str],
    per_label_coverage: Dict[str, Any],
    pocket_results: Sequence[Dict[str, Any]],
) -> Path:
    usable_sim_ids = sorted(
        u for u in uids if display_map.get(u, u) in usable_labels
    )
    failed = [r["label"] for r in pocket_results if not r.get("success")]
    # Also mark usable sims that still lack orientation after attempted recompute
    for uid in usable_sim_ids:
        orient = POCKET / uid / "reference_pocket_ligand_orientation.csv"
        dist = POCKET / uid / "reference_pocket_ligand_distance.csv"
        if not dist.is_file():
            lab = display_map.get(uid, uid)
            if lab not in failed:
                failed.append(lab)
    manifest = {
        "reference_label": "MLKL",
        "definition_json": str(AN / "reference_pocket_definition.json"),
        "residue_map_csv": str(AN / "reference_msa_residue_map.csv"),
        "output_root": str(POCKET),
        "n_processed": sum(1 for r in pocket_results if r.get("success")),
        "n_failed": len(failed),
        "failed_labels": failed,
        "usable_labels": sorted(usable_labels),
        "usable_sim_ids": usable_sim_ids,
        "per_label_coverage": per_label_coverage,
        "update_note": (
            "Updated for local_fel_poc: MLKL star MSA + 15A pocket; "
            "includes GUC2C/P25092; refreshed extended 200 ns sims"
        ),
    }
    path = AN / "reference_pocket_batch_manifest.json"
    path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    print(f"Wrote {path} (usable_sim_ids={len(usable_sim_ids)})")
    return path


def regenerate_clustering(n_clusters: int) -> None:
    import subprocess

    script = REPO / "scripts" / "regenerate_local_fel_ref_pock_clustering.py"
    cmd = [
        sys.executable,
        str(script),
        "--n-clusters",
        str(int(n_clusters)),
    ]
    print("+", " ".join(cmd))
    subprocess.check_call(cmd, cwd=str(REPO))


def regenerate_draft_figures() -> None:
    import subprocess

    script = DRAFT / "generate_all_draft_figures.py"
    cmd = [sys.executable, str(script)]
    print("+", " ".join(cmd))
    subprocess.check_call(cmd, cwd=str(DRAFT))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--skip-msa", action="store_true", help="Skip MSA/pocket redefine")
    parser.add_argument("--skip-pocket", action="store_true")
    parser.add_argument("--skip-fel", action="store_true")
    parser.add_argument("--skip-cluster", action="store_true")
    parser.add_argument("--skip-figures", action="store_true")
    parser.add_argument(
        "--recompute-all-pocket",
        action="store_true",
        help="Recompute pocket metrics for every usable sim (default: changed + targets)",
    )
    parser.add_argument("--n-clusters", type=int, default=5)
    parser.add_argument("--max-workers", type=int, default=4)
    parser.add_argument("--frame-interval", type=int, default=1)
    parser.add_argument(
        "--map-min-coverage",
        type=float,
        default=0.4,
        help="Minimum pocket mapping coverage to mark usable (default 0.4)",
    )
    parser.add_argument(
        "--fel-uids",
        nargs="*",
        default=None,
        help="Override FEL recompute list (default: extended + q58a45)",
    )
    args = parser.parse_args()

    bak = AN / f"_bak_local_fel_poc_{time.strftime('%Y%m%d_%H%M%S')}"
    print(f"Backup dir: {bak}")
    for name in [
        "reference_msa_alignment.fasta",
        "reference_msa_alignment.json",
        "reference_msa_residue_map.csv",
        "reference_pocket_definition.json",
        "reference_pocket_batch_manifest.json",
    ]:
        _backup(AN / name, bak)

    old_resids = _load_old_pocket_resids()

    if args.skip_msa:
        from src.analysis.reference_labels import build_uniprot_display_map

        uids = _sim_uids_with_wrap()
        dm = build_uniprot_display_map(AN)
        defn = json.loads((AN / "reference_pocket_definition.json").read_text())
        info = {
            "uids": uids,
            "labels": [dm.get(u, u) for u in uids],
            "display_map": dm,
            "per_label_resids": defn.get("per_label_resids") or {},
            "per_label_coverage": defn.get("per_label_coverage") or {},
            "usable_labels": set(defn.get("usable_labels") or []),
        }
    else:
        info = rebuild_msa_and_pocket(
            reference_display="MLKL",
            map_min_coverage=args.map_min_coverage,
        )

    dm = info["display_map"]
    usable = set(info["usable_labels"])
    print("Usable labels:", sorted(usable))
    print("GUC2C usable?", "GUC2C" in usable, "cov=", info["per_label_coverage"].get("GUC2C"))
    print("PAN3 usable?", "PAN3" in usable, "cov=", info["per_label_coverage"].get("PAN3"))

    pocket_results: List[Dict[str, Any]] = []
    if not args.skip_pocket:
        targets = select_pocket_targets(
            uids=info["uids"],
            display_map=dm,
            per_label_resids=info["per_label_resids"],
            usable_labels=usable,
            old_resids=old_resids,
            recompute_all_pocket=args.recompute_all_pocket,
        )
        payloads = []
        for uid in targets:
            lab = dm.get(uid, uid)
            if lab not in usable:
                print(f"  skip pocket {uid}/{lab}: not usable")
                continue
            resids = info["per_label_resids"].get(lab) or []
            if len(resids) < 3:
                print(f"  skip pocket {uid}/{lab}: <3 resids")
                continue
            payloads.append(
                {
                    "uid": uid,
                    "label": lab,
                    "resids": list(resids),
                    "frame_interval": args.frame_interval,
                }
            )
        print(f"Pocket recompute targets ({len(payloads)}): {[p['uid'] for p in payloads]}")
        pocket_results = _run_pool(_pocket_worker, payloads, args.max_workers)
        bad = [r for r in pocket_results if not r.get("success")]
        if bad:
            print("Pocket failures:", bad)

    write_manifest(
        uids=info["uids"],
        display_map=dm,
        usable_labels=usable,
        per_label_coverage=info["per_label_coverage"],
        pocket_results=pocket_results,
    )

    if not args.skip_fel:
        fel_uids = list(args.fel_uids) if args.fel_uids is not None else list(ALWAYS_FEL)
        payloads = [{"uid": u, "frame_interval": args.frame_interval} for u in fel_uids]
        print(f"FEL recompute targets: {fel_uids}")
        fel_results = _run_pool(_fel_worker, payloads, args.max_workers)
        bad = [r for r in fel_results if not r.get("success")]
        if bad:
            print("FEL failures:", bad)
            raise SystemExit(2)

    if not args.skip_cluster:
        print(f"Regenerating clustering k={args.n_clusters}")
        regenerate_clustering(args.n_clusters)

    if not args.skip_figures:
        regenerate_draft_figures()

    # Final counts
    assign = AN / "local_fel_ref_pock" / "local_fel_ref_pock_cluster_assignments.csv"
    if assign.is_file():
        n = sum(1 for _ in assign.open(encoding="utf-8")) - 1
        print(f"\nCluster assignments: {n} simulations -> {assign}")
    print("Done.")


if __name__ == "__main__":
    main()
