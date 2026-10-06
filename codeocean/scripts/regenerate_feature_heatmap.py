#!/usr/bin/env python3
"""Regenerate a simple feature heatmap from published classification CSV.

This is a lightweight Code Ocean demo: it does not re-run MD or LLM agents.
It only redraws a reviewer-facing figure from deposited feature tables.
"""
from __future__ import annotations

import argparse
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--csv",
        type=Path,
        required=True,
        help="Path to classification_features_zscore.csv (or raw features)",
    )
    parser.add_argument(
        "--out",
        type=Path,
        required=True,
        help="Output PNG path",
    )
    parser.add_argument(
        "--title",
        default="SimAgent feature matrix (z-scored)",
        help="Figure title",
    )
    args = parser.parse_args()

    df = pd.read_csv(args.csv)
    if "label" not in df.columns:
        raise SystemExit(f"CSV missing 'label' column: {args.csv}")

    labels = df["label"].astype(str).tolist()
    numeric = df.select_dtypes(include=[np.number])
    if numeric.empty:
        raise SystemExit(f"No numeric columns in {args.csv}")

    mat = numeric.to_numpy(dtype=float)
    # Replace non-finite with 0 for display
    mat = np.nan_to_num(mat, nan=0.0, posinf=0.0, neginf=0.0)

    fig_w = max(8.0, 0.55 * mat.shape[1] + 3.0)
    fig_h = max(3.5, 0.45 * mat.shape[0] + 2.0)
    fig, ax = plt.subplots(figsize=(fig_w, fig_h))
    im = ax.imshow(mat, aspect="auto", cmap="coolwarm", vmin=-3, vmax=3)
    ax.set_yticks(range(len(labels)))
    ax.set_yticklabels(labels, fontsize=9)
    ax.set_xticks(range(len(numeric.columns)))
    ax.set_xticklabels(list(numeric.columns), rotation=55, ha="right", fontsize=8)
    ax.set_title(args.title, fontsize=12)
    fig.colorbar(im, ax=ax, fraction=0.03, pad=0.02, label="z-score")
    fig.tight_layout()

    args.out.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(args.out, dpi=150)
    plt.close(fig)
    print(f"Wrote {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
