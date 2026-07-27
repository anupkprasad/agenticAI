#!/usr/bin/env python3
"""
Local FEL + reference-pocket archetype clustering (parallel to ref_fel_pock).

Keeps existing ``pseudoKin/analysis/ref_fel_pock_*`` / ``reference_fel/`` outputs
untouched. Writes a sibling tree under:

  pseudoKin/analysis/local_fel_ref_pock/

Features (7 columns, same roles as reference archetype clustering):
  - 5× reference_pocket_archetype (from analysis/reference_pocket/{uid}/)
  - 2× fel_archetype: landscape_entropy, major_basin_population
    (from {uid}/analysis/fel_features.json — local PCA/FEL, not shared-grid)

Usage:
  PATH=.../ollama_env/bin:$PATH python3 scripts/regenerate_local_fel_ref_pock_clustering.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

BASE = REPO / "pseudoKin"
AN = BASE / "analysis"
OUT = AN / "local_fel_ref_pock"
POCKET = AN / "reference_pocket"


def _has_local_fel(uid: str) -> bool:
    return (BASE / uid / "analysis" / "fel_features.json").is_file()


def _rename_traj_plots(out_dir: Path) -> None:
    """Trajectory helpers hard-code ref_fel_pock_* names; rename into this tree."""
    for src in sorted(out_dir.glob("ref_fel_pock_*_by_cluster.png")):
        dst = out_dir / src.name.replace("ref_fel_pock_", "local_fel_ref_pock_", 1)
        if dst.resolve() == src.resolve():
            continue
        if dst.is_file():
            dst.unlink()
        src.rename(dst)
        print(f"renamed {src.name} -> {dst.name}")


def collect_and_cluster(n_clusters: int = 4) -> None:
    from src.analysis.classification_clustering import (
        CLUSTER_REFERENCE_POCKET_TRAJECTORY_METRIC_GROUPS,
        LOCAL_FEL_REF_POCK_CLUSTERING_OUTPUT_FILES,
        cluster_classification_features,
        plot_cluster_feature_trajectories,
        plot_cluster_rmsf_profiles,
        _plot_mds_cluster_map,
        _load_feature_matrix,
        _filter_usable_feature_columns,
        _impute_column_means,
        _apply_display_names,
    )
    from src.analysis.classification_collector import collect_classification_features_table
    from src.analysis.reference_labels import (
        build_uniprot_display_map,
        is_reference_pocket_usable,
    )
    import csv

    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "README.md").write_text(
        "# Local FEL + reference pocket clustering\n\n"
        "This directory is **independent** of `ref_fel_pock_*` (shared-grid/"
        "reference FEL + reference pocket).\n\n"
        "| Feature set | Source |\n"
        "|-------------|--------|\n"
        "| Reference pocket (5 archetype metrics) | "
        "`../reference_pocket/{uniprot}/` |\n"
        "| Local FEL (`landscape_entropy`, `major_basin_population`) | "
        "`../../{uniprot}/analysis/fel_features.json` |\n\n"
        "Regenerate with:\n"
        "```bash\n"
        "python3 scripts/regenerate_local_fel_ref_pock_clustering.py\n"
        "```\n",
        encoding="utf-8",
    )

    manifest = json.loads((AN / "reference_pocket_batch_manifest.json").read_text())
    allowed = sorted(
        d.name
        for d in POCKET.iterdir()
        if d.is_dir()
        and is_reference_pocket_usable(d.name, manifest, base_analysis=AN)
        and _has_local_fel(d.name)
    )
    skipped_no_local = sorted(
        d.name
        for d in POCKET.iterdir()
        if d.is_dir()
        and is_reference_pocket_usable(d.name, manifest, base_analysis=AN)
        and not _has_local_fel(d.name)
    )
    if skipped_no_local:
        print(f"Skipping (no local FEL): {skipped_no_local}")

    out = LOCAL_FEL_REF_POCK_CLUSTERING_OUTPUT_FILES
    metric_groups = ["reference_pocket_archetype", "fel_archetype"]
    name_map = build_uniprot_display_map(AN)

    collect = collect_classification_features_table.func(
        base_directory=str(BASE),
        working_dir=str(OUT),
        requested_metric_groups=metric_groups,
        allowed_labels=allowed,
        output_file=out["features_csv"],
        zscore_output_file=out["zscore_csv"],
        manifest_file=out["manifest_json"],
        xlsx_output_file=out["xlsx"],
    )
    print("collect:", collect.get("message"), collect.get("error"))
    if not collect.get("success"):
        raise SystemExit(1)

    # Annotate manifest so hybrid provenance is explicit
    man_path = OUT / out["manifest_json"]
    if man_path.is_file():
        man = json.loads(man_path.read_text(encoding="utf-8"))
        man["hybrid_note"] = (
            "reference_pocket_archetype + local fel_archetype "
            "(not reference_fel / shared MLKL PC grid)"
        )
        man["output_directory"] = str(OUT)
        man["skipped_no_local_fel"] = skipped_no_local
        man_path.write_text(json.dumps(man, indent=2), encoding="utf-8")

    n_sims = int(collect.get("n_simulations") or len(allowed))
    k = max(1, min(int(n_clusters), n_sims))
    print(f"Clustering with k={k} (n={n_sims})")

    archetype_names = None
    highlight_names = None
    draft_rep = (
        REPO / "docs" / "ment" / "output_localFEL_poc" / "draft_representatives.py"
    )
    if draft_rep.is_file():
        import importlib.util

        spec = importlib.util.spec_from_file_location("local_fel_draft_reps", draft_rep)
        mod = importlib.util.module_from_spec(spec)
        assert spec.loader is not None
        spec.loader.exec_module(mod)
        if k == 5 and hasattr(mod, "CLUSTER_SHORT"):
            archetype_names = {
                int(cid): str(name) for cid, name in mod.CLUSTER_SHORT.items()
            }
            print(f"Using draft archetype names: {archetype_names}")
        highlight_names = list(getattr(mod, "GROUND_TRUTH_DISPLAY_NAMES", ()) or ())
        if highlight_names:
            print(f"Highlighting ground-truth labels: {highlight_names}")

    cluster = cluster_classification_features.func(
        working_dir=str(OUT),
        features_file=out["zscore_csv"],
        method="hierarchical",
        n_clusters=k,
        label_name_map=name_map,
        cluster_archetype_names=archetype_names,
        highlight_display_names=highlight_names,
        legend_ncol=3 if k >= 5 else None,
        assignments_file=out["assignments_csv"],
        scatter_plot_file=out["pca_png"],
        dendrogram_file=out["dendrogram_png"],
        phylo_tree_file=out["phylo_png"],
        heatmap_file=out["heatmap_png"],
        panel_file=out["panel_png"],
        summary_file=out["summary_json"],
    )
    print("cluster:", cluster.get("message"), cluster.get("error"))
    if not cluster.get("success"):
        raise SystemExit(1)

    # MDS map (same helper used elsewhere; not wired into cluster tool by default)
    try:
        feat_path = OUT / out["zscore_csv"]
        labels, display_names, _sim_dirs, X_raw, feature_cols = _load_feature_matrix(
            feat_path, min_features_present=1
        )
        display_names = _apply_display_names(
            labels, label_name_map=name_map, base_analysis_dir=AN
        )
        X_f, feature_cols, _ = _filter_usable_feature_columns(X_raw, feature_cols)
        X, _ = _impute_column_means(X_f)
        assign_path = OUT / out["assignments_csv"]
        cid_by_label = {}
        with assign_path.open(newline="", encoding="utf-8") as fh:
            for row in csv.DictReader(fh):
                cid_by_label[row["label"]] = int(row["cluster_id"])
        cluster_ids = [cid_by_label[lbl] for lbl in labels]
        _plot_mds_cluster_map(
            X,
            display_names,
            cluster_ids,
            OUT / out["mds_png"],
            title=f"MDS map — local FEL + reference pocket (k={k})",
        )
        print(f"MDS map -> {OUT / out['mds_png']}")
    except Exception as exc:
        print(f"MDS map skipped: {exc}")

    assign = out["assignments_csv"]
    traj = plot_cluster_feature_trajectories.func(
        working_dir=str(OUT),
        assignments_file=assign,
        metric_groups=list(CLUSTER_REFERENCE_POCKET_TRAJECTORY_METRIC_GROUPS),
    )
    print("traj plots:", traj.get("plots"), traj.get("skipped_metrics"), traj.get("error"))
    rmsf = plot_cluster_rmsf_profiles.func(
        working_dir=str(OUT),
        assignments_file=assign,
        profile_types=["reference_pocket_rmsf"],
    )
    print("rmsf plots:", rmsf.get("plots"), rmsf.get("error"))
    _rename_traj_plots(OUT)

    print(f"\nDone. Outputs in {OUT}")
    print(f"  Panel: {OUT / out['panel_png']}")


def main() -> None:
    import argparse

    parser = argparse.ArgumentParser(
        description="Local FEL + reference-pocket clustering (separate from ref_fel_pock)."
    )
    parser.add_argument(
        "--n-clusters",
        type=int,
        default=4,
        help="Number of hierarchical clusters (default: 4).",
    )
    args = parser.parse_args()
    collect_and_cluster(n_clusters=args.n_clusters)


if __name__ == "__main__":
    main()
