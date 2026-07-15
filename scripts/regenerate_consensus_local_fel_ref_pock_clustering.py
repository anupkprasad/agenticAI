#!/usr/bin/env python3
"""
Consensus-local FEL + reference-pocket archetype clustering.

Independent of:
  - local_fel_ref_pock/  (all-Cα local FEL + pocket)
  - ref_fel_pock_* / reference_fel/  (shared reference-projected FEL)

Writes:
  pseudoKin/analysis/consensus_local_fel_ref_pock/

Features (7):
  - 5× reference_pocket_archetype
  - 2× FEL archetype from analysis/consensus_local_fel/{uid}/fel_features.json
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

BASE = REPO / "pseudoKin"
AN = BASE / "analysis"
OUT = AN / "consensus_local_fel_ref_pock"
POCKET = AN / "reference_pocket"
CONSENSUS_FEL = AN / "consensus_local_fel"
DRAFT_DIR = REPO / "docs" / "ment" / "output_consensusFEL_poc"


def _has_consensus_fel(uid: str) -> bool:
    return (CONSENSUS_FEL / uid / "fel_features.json").is_file()


def _rename_traj_plots(out_dir: Path) -> None:
    for src in sorted(out_dir.glob("ref_fel_pock_*_by_cluster.png")):
        dst = out_dir / src.name.replace(
            "ref_fel_pock_", "consensus_local_fel_ref_pock_", 1
        )
        if dst.resolve() == src.resolve():
            continue
        if dst.is_file():
            dst.unlink()
        src.rename(dst)
        print(f"renamed {src.name} -> {dst.name}")


def _write_draft_representatives(cluster_summary: Path) -> None:
    """Refresh draft_representatives.py from cluster medoids (k=5 preferred)."""
    if not cluster_summary.is_file():
        return
    data = json.loads(cluster_summary.read_text(encoding="utf-8"))
    reps = data.get("cluster_representatives") or {}
    names = data.get("cluster_archetype_names") or {}
    if not reps:
        return

    default_short = {
        1: "Dissociated coupling",
        2: "Dominant-basin coupling",
        3: "Canonical coupling",
        4: "Loosely-bound coupling",
        5: "Restrained coupling",
    }
    short = {
        int(k): str(names.get(str(k)) or names.get(k) or default_short.get(int(k), f"Cluster {k}"))
        for k in reps
    }

    lines = [
        '"""Draft representatives for consensus-local-FEL + reference-pocket clustering."""',
        "",
        "from __future__ import annotations",
        "",
        "from typing import Dict",
        "",
        "DRAFT_REPRESENTATIVES: Dict[int, Dict[str, str]] = {",
    ]
    for cid in sorted(int(x) for x in reps):
        info = reps[str(cid)]
        lab = info["label"]
        dname = info.get("display_name") or lab
        comment = short.get(cid, "")
        lines.append(
            f'    {cid}: {{"label": "{lab}", "display_name": "{dname}"}},  # C{cid} {comment}'
        )
    lines.append("}")
    lines.append("")
    lines.append("CLUSTER_COLORS = {")
    colors = {1: "#E41A1C", 2: "#377EB8", 3: "#4DAF4A", 4: "#984EA3", 5: "#FF7F00"}
    for cid in sorted(int(x) for x in reps):
        lines.append(f'    {cid}: "{colors.get(cid, "#333333")}",')
    lines.append("}")
    lines.append("")
    lines.append("CLUSTER_SHORT = {")
    for cid in sorted(short):
        lines.append(f'    {cid}: "{short[cid]}",')
    lines.append("}")
    lines.append("")

    DRAFT_DIR.mkdir(parents=True, exist_ok=True)
    target = DRAFT_DIR / "draft_representatives.py"
    target.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"Wrote {target}")


def collect_and_cluster(n_clusters: int = 5) -> None:
    from src.analysis.classification_clustering import (
        CLUSTER_REFERENCE_POCKET_TRAJECTORY_METRIC_GROUPS,
        CONSENSUS_LOCAL_FEL_REF_POCK_CLUSTERING_OUTPUT_FILES,
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
        "# Consensus-local FEL + reference pocket clustering\n\n"
        "Independent of `local_fel_ref_pock/` and `ref_fel_pock_*`.\n\n"
        "| Feature set | Source |\n"
        "|-------------|--------|\n"
        "| Reference pocket (5 archetype metrics) | "
        "`../reference_pocket/{uniprot}/` |\n"
        "| Consensus-local FEL (`landscape_entropy`, "
        "`major_basin_population`) | "
        "`../consensus_local_fel/{uniprot}/fel_features.json` |\n\n"
        "PCA atoms = consensus-mapped Cα; PCA basis = **per-simulation** "
        "(no reference projection).\n\n"
        "Regenerate:\n"
        "```bash\n"
        "python3 scripts/run_consensus_local_fel_batch.py\n"
        "python3 scripts/regenerate_consensus_local_fel_ref_pock_clustering.py "
        "--n-clusters 5\n"
        "```\n",
        encoding="utf-8",
    )

    manifest = json.loads((AN / "reference_pocket_batch_manifest.json").read_text())
    allowed = sorted(
        d.name
        for d in POCKET.iterdir()
        if d.is_dir()
        and is_reference_pocket_usable(d.name, manifest, base_analysis=AN)
        and _has_consensus_fel(d.name)
    )
    skipped = sorted(
        d.name
        for d in POCKET.iterdir()
        if d.is_dir()
        and is_reference_pocket_usable(d.name, manifest, base_analysis=AN)
        and not _has_consensus_fel(d.name)
    )
    if skipped:
        print(f"Skipping (no consensus-local FEL): {skipped}")
    if not allowed:
        raise SystemExit(
            "No labels with both usable reference pocket and consensus-local FEL. "
            "Run scripts/run_consensus_local_fel_batch.py first."
        )

    out = CONSENSUS_LOCAL_FEL_REF_POCK_CLUSTERING_OUTPUT_FILES
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
        local_fel_root=str(CONSENSUS_FEL),
    )
    print("collect:", collect.get("message"), collect.get("error"))
    if not collect.get("success"):
        raise SystemExit(1)

    man_path = OUT / out["manifest_json"]
    if man_path.is_file():
        man = json.loads(man_path.read_text(encoding="utf-8"))
        man["hybrid_note"] = (
            "reference_pocket_archetype + consensus_local_fel archetype "
            "(consensus Cα PCA, no reference projection)"
        )
        man["output_directory"] = str(OUT)
        man["consensus_fel_root"] = str(CONSENSUS_FEL)
        man["skipped_no_consensus_fel"] = skipped
        man_path.write_text(json.dumps(man, indent=2), encoding="utf-8")

    n_sims = int(collect.get("n_simulations") or len(allowed))
    k = max(1, min(int(n_clusters), n_sims))
    print(f"Clustering with k={k} (n={n_sims})")

    archetype_names = None
    if k == 5:
        archetype_names = {
            1: "Dissociated coupling",
            2: "Dominant-basin coupling",
            3: "Canonical coupling",
            4: "Loosely-bound coupling",
            5: "Restrained coupling",
        }
        print(f"Using archetype names: {archetype_names}")

    cluster = cluster_classification_features.func(
        working_dir=str(OUT),
        features_file=out["zscore_csv"],
        method="hierarchical",
        n_clusters=k,
        label_name_map=name_map,
        cluster_archetype_names=archetype_names,
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
            title=f"MDS map — consensus-local FEL + reference pocket (k={k})",
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
    _write_draft_representatives(OUT / out["summary_json"])

    print(f"\nDone. Outputs in {OUT}")
    print(f"  Panel: {OUT / out['panel_png']}")


def main() -> None:
    import argparse

    parser = argparse.ArgumentParser(
        description="Consensus-local FEL + reference-pocket clustering."
    )
    parser.add_argument("--n-clusters", type=int, default=5)
    args = parser.parse_args()
    collect_and_cluster(n_clusters=args.n_clusters)


if __name__ == "__main__":
    main()
