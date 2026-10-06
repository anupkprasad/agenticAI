#!/usr/bin/env python3
"""Regenerate apo/holo overlay summary bar charts from deposited stats CSVs.

Source tables are taken from example/pseudo_apo_holo/analysis/*_stats.csv
(already-completed SimAgent campaign). This does not re-run MD or LLM agents.
"""
from __future__ import annotations

import argparse
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd


def _plot_stats(csv_path: Path, out_path: Path, ylabel: str, title: str) -> None:
    df = pd.read_csv(csv_path)
    if "simulation" not in df.columns or "mean" not in df.columns:
        raise SystemExit(f"Unexpected columns in {csv_path}: {list(df.columns)}")

    labels = df["simulation"].astype(str).tolist()
    means = df["mean"].astype(float).tolist()
    stds = (
        df["std"].astype(float).tolist()
        if "std" in df.columns
        else [0.0] * len(means)
    )

    fig, ax = plt.subplots(figsize=(max(8.0, 0.7 * len(labels) + 2), 4.2))
    x = range(len(labels))
    ax.bar(x, means, yerr=stds, capsize=3, color="#4C72B0", alpha=0.9, ecolor="#333333")
    ax.set_xticks(list(x))
    ax.set_xticklabels(labels, rotation=40, ha="right", fontsize=8)
    ax.set_ylabel(ylabel)
    ax.set_title(title)
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    fig.tight_layout()
    out_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out_path, dpi=150)
    plt.close(fig)
    print(f"Wrote {out_path}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--data-dir",
        type=Path,
        required=True,
        help="Directory with rmsd_stats.csv, rmsf_stats.csv, rg_stats.csv",
    )
    parser.add_argument("--out-dir", type=Path, required=True)
    args = parser.parse_args()

    specs = (
        ("rmsd_stats.csv", "rmsd_stats_bar.png", "RMSD mean (nm)", "Backbone RMSD (deposited example)"),
        ("rmsf_stats.csv", "rmsf_stats_bar.png", "RMSF mean (nm)", "Cα RMSF (deposited example)"),
        ("rg_stats.csv", "rg_stats_bar.png", "Rg mean (Å)", "Radius of gyration (deposited example)"),
    )
    for fname, out_name, ylabel, title in specs:
        src = args.data_dir / fname
        if not src.is_file():
            raise SystemExit(f"Missing {src}")
        _plot_stats(src, args.out_dir / out_name, ylabel, title)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
