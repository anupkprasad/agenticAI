#!/usr/bin/env python3
"""Regenerate reference-based pseudoKin combined outputs after label/residence fixes."""
from __future__ import annotations

import json
import os
import shutil
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

BASE = REPO / "pseudoKin"
AN = BASE / "analysis"
POCKET = AN / "reference_pocket"
from src.analysis.consensus_pocket import REFERENCE_POCKET_BOUND_DISTANCE_A

BOUND_A = REFERENCE_POCKET_BOUND_DISTANCE_A  # MLKL-calibrated COM envelope (15 Å)

# Ensure gmx is discoverable
_gmx = Path.home() / "conda_envs/ollama_env/bin/gmx"
if _gmx.is_file():
    os.environ["PATH"] = f"{_gmx.parent}:{os.environ.get('PATH', '')}"


def rename_legacy_outputs() -> None:
    pairs = [
        ("reference_fel_features_table.json", "ref_fel_features_table.json"),
        ("reference_fel_cluster_assignments.csv", "ref_fel_cluster_assignments.csv"),
        ("reference_fel_clusters.json", "ref_fel_clusters.json"),
        ("reference_fel_dendrogram.png", "ref_fel_dendrogram.png"),
        ("reference_fel_phylo_tree.png", "ref_fel_phylo_tree.png"),
        ("reference_grouping_features.csv", "ref_fel_pock_features.csv"),
        ("reference_grouping_features_zscore.csv", "ref_fel_pock_features_zscore.csv"),
        ("reference_grouping_features.json", "ref_fel_pock_features.json"),
        ("reference_grouping_features.xlsx", "ref_fel_pock_features.xlsx"),
        ("reference_cluster_assignments.csv", "ref_fel_pock_cluster_assignments.csv"),
        ("reference_clusters.json", "ref_fel_pock_clusters.json"),
        ("reference_clusters_pca.png", "ref_fel_pock_clusters_pca.png"),
        ("reference_clusters_dendrogram.png", "ref_fel_pock_dendrogram.png"),
        ("reference_clusters_phylo_tree.png", "ref_fel_pock_phylo_tree.png"),
        ("reference_clusters_features_heatmap.png", "ref_fel_pock_features_heatmap.png"),
        ("reference_pocket_com_distance_by_cluster.png", "ref_fel_pock_com_distance_by_cluster.png"),
        ("reference_pocket_hbonds_by_cluster.png", "ref_fel_pock_hbonds_by_cluster.png"),
        ("reference_pocket_sasa_by_cluster.png", "ref_fel_pock_sasa_by_cluster.png"),
        ("reference_pocket_ligand_residence_by_cluster.png", "ref_fel_pock_ligand_residence_by_cluster.png"),
        ("reference_pocket_rmsf_by_cluster.png", "ref_fel_pock_rmsf_by_cluster.png"),
    ]
    for old, new in pairs:
        src, dst = AN / old, AN / new
        if src.is_file() and not dst.is_file():
            shutil.copy2(src, dst)
            print(f"renamed {old} -> {new}")


def update_residence_and_manifest() -> None:
    from src.analysis.consensus_pocket import compute_consensus_residence_from_csvs
    from src.analysis.reference_labels import is_reference_pocket_usable

    manifest_path = AN / "reference_pocket_batch_manifest.json"
    manifest = {}
    if manifest_path.is_file():
        manifest = json.loads(manifest_path.read_text())
        manifest["usable_sim_ids"] = sorted(
            d.name for d in POCKET.iterdir()
            if d.is_dir()
            and is_reference_pocket_usable(d.name, manifest, base_analysis=AN)
        )
        manifest_path.write_text(json.dumps(manifest, indent=2))

    n = 0
    for sim_dir in sorted(POCKET.iterdir()):
        if not sim_dir.is_dir():
            continue
        dist = sim_dir / "reference_pocket_ligand_distance.csv"
        contacts = sim_dir / "reference_pocket_contacts.csv"
        metrics_path = sim_dir / "reference_pocket_metrics.json"
        if not dist.is_file() or not contacts.is_file():
            continue
        res = compute_consensus_residence_from_csvs(
            str(dist),
            str(contacts),
            bound_distance_A=BOUND_A,
            bound_mode="distance",
            output_file="reference_pocket_residence.csv",
            working_dir=str(sim_dir),
        )
        if res.get("success") and metrics_path.is_file():
            metrics = json.loads(metrics_path.read_text())
            metrics["fraction_bound"] = res.get("fraction_bound")
            metrics["bound_distance_A"] = BOUND_A
            metrics_path.write_text(json.dumps(metrics, indent=2))
            n += 1
    print(f"Updated residence (bound <= {BOUND_A} A) for {n} simulations")


def compute_missing_sasa() -> None:
    import MDAnalysis as mda
    from src.analysis.consensus_pocket import compute_consensus_pocket_sasa
    from src.analysis.combined_analysis import _find_sim_traj_topology

    for sim_dir in sorted(POCKET.iterdir()):
        if not sim_dir.is_dir():
            continue
        sasa_csv = sim_dir / "reference_pocket_sasa.csv"
        metrics_path = sim_dir / "reference_pocket_metrics.json"
        if sasa_csv.is_file():
            continue
        if not metrics_path.is_file():
            continue
        metrics = json.loads(metrics_path.read_text())
        resids = metrics.get("pocket_resids") or []
        uid = sim_dir.name
        sim_root = BASE / uid
        topo, traj = _find_sim_traj_topology(str(sim_root))
        if not topo or not str(topo).endswith(".tpr"):
            print(f"skip SASA {uid}: no tpr")
            continue
        u = mda.Universe(topo, traj)
        res = compute_consensus_pocket_sasa(
            u,
            topology_file=str(topo),
            trajectory_file=str(traj),
            pocket_resids=[int(r) for r in resids],
            output_file=str(sasa_csv),
        )
        if res.get("success"):
            metrics["mean_pocket_sasa_nm2"] = res.get("mean_pocket_sasa_nm2")
            metrics_path.write_text(json.dumps(metrics, indent=2))
            print(f"SASA computed for {uid}")
        else:
            print(f"SASA failed {uid}: {res.get('error')}")


def backfill_orientation_scalar_metrics() -> None:
    """Update metrics.json with COM/angle p95 and related scalars from orientation CSVs."""
    from src.analysis.consensus_pocket import summarize_ligand_orientation_csv
    from src.analysis.reference_labels import is_reference_pocket_usable

    manifest_path = AN / "reference_pocket_batch_manifest.json"
    manifest = json.loads(manifest_path.read_text()) if manifest_path.is_file() else {}

    n_ok = 0
    for sim_dir in sorted(POCKET.iterdir()):
        if not sim_dir.is_dir():
            continue
        uid = sim_dir.name
        if not is_reference_pocket_usable(uid, manifest, base_analysis=AN):
            continue
        orient_csv = sim_dir / "reference_pocket_ligand_orientation.csv"
        metrics_path = sim_dir / "reference_pocket_metrics.json"
        if not orient_csv.is_file() or not metrics_path.is_file():
            continue
        derived = summarize_ligand_orientation_csv(orient_csv)
        if not derived.get("success"):
            print(f"skip orientation scalars {uid}: {derived.get('error')}")
            continue
        metrics = json.loads(metrics_path.read_text())
        metrics["ligand_pocket_distance_p95_A"] = derived.get("p95_distance_A")
        metrics["ligand_pocket_distance_max_A"] = derived.get("max_distance_A")
        metrics["mean_axis_angle_deg"] = derived.get("mean_axis_angle_deg")
        metrics["std_axis_angle_deg"] = derived.get("std_axis_angle_deg")
        metrics["p95_axis_angle_deg"] = derived.get("p95_axis_angle_deg")
        metrics_path.write_text(json.dumps(metrics, indent=2), encoding="utf-8")
        n_ok += 1
    print(f"orientation scalar backfill complete: {n_ok} systems")


def backfill_reference_ligand_orientation() -> None:
    """Compute pocket–ligand COM + major-axis angle for existing reference_pocket dirs."""
    import MDAnalysis as mda
    from src.analysis.combined_analysis import _find_sim_traj_topology
    from src.analysis.consensus_pocket import compute_consensus_pocket_ligand_geometry
    from src.analysis.reference_labels import build_uniprot_display_map, is_reference_pocket_usable

    manifest_path = AN / "reference_pocket_batch_manifest.json"
    manifest = json.loads(manifest_path.read_text()) if manifest_path.is_file() else {}
    uid_to_disp = build_uniprot_display_map(AN)

    n_ok = 0
    for sim_dir in sorted(POCKET.iterdir()):
        if not sim_dir.is_dir():
            continue
        uid = sim_dir.name
        if not is_reference_pocket_usable(uid, manifest, base_analysis=AN):
            continue
        disp = uid_to_disp.get(uid.lower(), uid)
        metrics_path = sim_dir / "reference_pocket_metrics.json"
        if not metrics_path.is_file():
            continue
        metrics = json.loads(metrics_path.read_text())
        resids = metrics.get("pocket_resids") or []
        if len(resids) < 3:
            continue
        topo, traj = _find_sim_traj_topology(str(BASE / uid))
        if not topo or not traj:
            print(f"skip orientation {uid}: no trajectory")
            continue
        u = mda.Universe(topo, traj)
        res = compute_consensus_pocket_ligand_geometry(
            u,
            pocket_resids=[int(r) for r in resids],
            distance_output=str(sim_dir / "reference_pocket_ligand_distance.csv"),
            orientation_output=str(sim_dir / "reference_pocket_ligand_orientation.csv"),
            frame_interval=5,
        )
        if not res.get("success"):
            print(f"orientation failed {disp}: {res.get('error')}")
            continue
        metrics["ligand_pocket_distance_mean_A"] = res.get("mean_distance_A")
        metrics["ligand_pocket_distance_std_A"] = res.get("std_distance_A")
        metrics["ligand_pocket_distance_p95_A"] = res.get("p95_distance_A")
        metrics["ligand_pocket_distance_max_A"] = res.get("max_distance_A")
        metrics["mean_axis_angle_deg"] = res.get("mean_axis_angle_deg")
        metrics["std_axis_angle_deg"] = res.get("std_axis_angle_deg")
        metrics["p95_axis_angle_deg"] = res.get("p95_axis_angle_deg")
        metrics_path.write_text(json.dumps(metrics, indent=2), encoding="utf-8")
        n_ok += 1
        print(
            f"orientation {disp}: COM={res.get('mean_distance_A'):.2f} Å, "
            f"p95={res.get('p95_distance_A'):.2f} Å, "
            f"angle_p95={res.get('p95_axis_angle_deg'):.1f}°"
        )
    print(f"orientation backfill complete: {n_ok} systems")


def collect_cluster_plot() -> None:
    from agentic.analysis.tools import (
        collect_classification_features_table,
        cluster_classification_features,
    )
    from src.analysis.classification_clustering import (
        CLUSTER_REFERENCE_POCKET_TRAJECTORY_METRIC_GROUPS,
        CLUSTER_RMSF_PROFILE_GROUPS,
        REFERENCE_CLUSTERING_OUTPUT_FILES,
        cluster_classification_features,
        plot_cluster_feature_trajectories,
        plot_cluster_rmsf_profiles,
        reference_archetype_metric_groups,
        resolve_n_clusters_for_goal,
    )
    from src.analysis.reference_labels import is_reference_pocket_usable

    manifest = json.loads((AN / "reference_pocket_batch_manifest.json").read_text())
    allowed = sorted(
        d.name for d in POCKET.iterdir()
        if d.is_dir() and is_reference_pocket_usable(d.name, manifest, base_analysis=AN)
    )

    out = REFERENCE_CLUSTERING_OUTPUT_FILES
    metric_groups = list(reference_archetype_metric_groups(["reference_pocket", "reference_fel"]))
    collect = collect_classification_features_table.func(
        base_directory=str(BASE),
        working_dir=str(AN),
        requested_metric_groups=metric_groups,
        allowed_labels=allowed,
        output_file=out["features_csv"],
        zscore_output_file=out["zscore_csv"],
        manifest_file=out["manifest_json"],
        xlsx_output_file=out["xlsx"],
    )
    print("collect:", collect.get("message"), collect.get("error"))

    zscore = AN / out["zscore_csv"]
    n_sims = int(collect.get("n_simulations") or len(allowed))
    k = resolve_n_clusters_for_goal(n_sims, "k=4 reference pocket fel", reference_based=True)
    cluster = cluster_classification_features.func(
        working_dir=str(AN),
        features_file=zscore.name,
        method="hierarchical",
        n_clusters=k,
        assignments_file=out["assignments_csv"],
        scatter_plot_file=out["pca_png"],
        dendrogram_file=out["dendrogram_png"],
        phylo_tree_file=out["phylo_png"],
        heatmap_file=out["heatmap_png"],
        panel_file=out.get("panel_png"),
        summary_file=out["summary_json"],
    )
    print("cluster:", cluster.get("message"), cluster.get("error"))

    assign = out["assignments_csv"]
    traj = plot_cluster_feature_trajectories.func(
        working_dir=str(AN),
        assignments_file=assign,
        metric_groups=list(CLUSTER_REFERENCE_POCKET_TRAJECTORY_METRIC_GROUPS),
    )
    print("traj plots:", traj.get("plots"), traj.get("skipped_metrics"))
    rmsf = plot_cluster_rmsf_profiles.func(
        working_dir=str(AN),
        assignments_file=assign,
        profile_types=["reference_pocket_rmsf"],
    )
    print("rmsf plots:", rmsf.get("plots"))


def regenerate_report() -> None:
    from src.reporter.combined_reporter import generate_combined_html_report

    sim_dirs = sorted(
        str(p) for p in BASE.iterdir()
        if p.is_dir() and (p / "analysis").is_dir() and p.name not in {"analysis", "reporter"}
    )
    labels = [Path(d).name for d in sim_dirs]
    plots = []
    for pat in ("ref_fel_pock_*.png", "ref_fel_*.png", "*overlay.png"):
        plots.extend(str(p) for p in AN.glob(pat))
    plots = sorted(set(plots))

    goal_path = REPO / "README.md"
    user_goal = goal_path.read_text()[:4000] if goal_path.is_file() else ""

    res = generate_combined_html_report.func(
        sim_dirs=sim_dirs,
        labels=labels,
        overlay_plots=plots,
        working_dir=str(BASE / "reporter"),
        user_goal=user_goal,
    )
    print("report:", res.get("output_path"), res.get("error"))


def main() -> None:
    rename_legacy_outputs()
    update_residence_and_manifest()
    compute_missing_sasa()
    backfill_orientation_scalar_metrics()
    collect_cluster_plot()
    regenerate_report()


if __name__ == "__main__":
    main()
