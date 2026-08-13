#!/usr/bin/env python3
"""Plot reference star-MSA alignments (full + high-consensus / pocket columns).

Used by combined-analysis agents and manuscript Fig. S3 assets.
"""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

import numpy as np
from langchain.tools import tool

logger = logging.getLogger(__name__)

# Star-MSA parameters (must match src.analysis.consensus_alignment._build_aligner)
MSA_METHOD = (
    "Star MSA to reference: Biopython PairwiseAligner, global alignment, "
    "BLOSUM62, gap open/extend = −10 / −0.5 "
    "(one pairwise alignment per sequence vs the reference; columns indexed by reference residues)."
)

# Display-only column filter for MSA panels (not used to define the pocket).
# Framework MSA consensus uses min_coverage=0.85; pocket uses 15 Å ∩ consensus columns.
POCKET_MIN_OCCUPANCY = 0.90
POCKET_MIN_CONSERVATION = 0.40
POCKET_TARGET_N = 40


AA_COLORS = {
    "A": "#f5f0c8", "V": "#f5f0c8", "L": "#f5f0c8", "I": "#f5f0c8", "M": "#f5f0c8",
    "F": "#f4a6a6", "Y": "#f4a6a6", "W": "#f4a6a6",
    "S": "#a8d8a8", "T": "#a8d8a8", "N": "#a8d8a8", "Q": "#a8d8a8",
    "D": "#f08080", "E": "#f08080",
    "K": "#8eb4e0", "R": "#8eb4e0", "H": "#8eb4e0",
    "G": "#e8e070", "P": "#d4a574", "C": "#fff59d",
    "-": "#f2f2f2", "X": "#eeeeee",
}

C_BG = "#fbfafa"
C_INK = "#1c2429"
C_MUTED = "#5c6670"
C_LINE = "#c5ccd2"
C_FOCUS = "#1f4e5f"
C_POCKET = "#c45c26"


def _hex_rgb(hx: str):
    hx = hx.lstrip("#")
    return tuple(int(hx[i : i + 2], 16) / 255.0 for i in (0, 2, 4))


def _luminance(rgb) -> float:
    r, g, b = rgb
    return 0.299 * r + 0.587 * g + 0.114 * b


def load_msa_fasta(fasta_file: str) -> Tuple[List[str], np.ndarray]:
    from Bio import SeqIO

    recs = list(SeqIO.parse(fasta_file, "fasta"))
    if not recs:
        raise ValueError(f"No sequences in {fasta_file}")
    names = [r.id.split()[0] for r in recs]
    mat = np.array([list(str(r.seq)) for r in recs])
    return names, mat


def column_stats(mat: np.ndarray):
    n_rows, n_cols = mat.shape
    occ = np.zeros(n_cols)
    cons = np.zeros(n_cols)
    for j in range(n_cols):
        col = mat[:, j]
        mask = col != "-"
        occ[j] = mask.mean()
        if mask.any():
            vals, cnts = np.unique(col[mask], return_counts=True)
            cons[j] = cnts.max() / mask.sum()
    return occ, cons


def select_high_consensus_columns(
    mat: np.ndarray,
    preferred_cols: Optional[Sequence[int]] = None,
    *,
    min_occupancy: float = POCKET_MIN_OCCUPANCY,
    min_conservation: float = POCKET_MIN_CONSERVATION,
    target_n: int = POCKET_TARGET_N,
) -> np.ndarray:
    """Select well-occupied, high-modal-conservation columns for *display*.

    Only columns meeting ``min_occupancy`` and ``min_conservation`` are kept;
    results are ranked by conservation then occupancy and capped at ``target_n``.
    Sub-threshold columns are never padded in to fill the target.
    """
    occ, cons = column_stats(mat)
    if preferred_cols is not None:
        pool = [int(c) for c in preferred_cols if 0 <= int(c) < mat.shape[1]]
    else:
        pool = list(range(mat.shape[1]))

    scored = []
    for c in pool:
        if occ[c] < min_occupancy:
            continue
        if cons[c] < min_conservation:
            continue
        scored.append((c, float(cons[c]), float(occ[c])))
    scored.sort(key=lambda t: (-t[1], -t[2], t[0]))

    if target_n > 0:
        scored = scored[: int(target_n)]
    keep = [c for c, _, _ in scored]
    return np.asarray(sorted(keep), dtype=int)


def _draw_msa(
    ax,
    names: List[str],
    mat: np.ndarray,
    *,
    col_indices: Optional[np.ndarray] = None,
    title: str,
    footer: str,
    draw_letters: bool = True,
    letter_fs: float = 5.5,
    label_fs: float = 7.8,
    highlight_rows: Optional[Sequence[str]] = None,
    mark_preferred: Optional[Sequence[int]] = None,
    show_property_legend: bool = True,
    label_colors: Optional[Sequence[str]] = None,
    aa_colors: Optional[Dict[str, str]] = None,
    property_legend_items: Optional[Sequence[Tuple[str, str]]] = None,
    xtick_labels: Optional[Sequence[str]] = None,
    xlabel: Optional[str] = None,
    cons_label_fs: float = 6.0,
    legend_fs: float = 6.4,
    footer_fs: float = 6.6,
):
    """Draw an MSA heatmap that spans the full axes width.

    Legend (line 1) and footer (line 2+) are placed in axes-fraction space below
    the grid so they never compete with column width or overlap each other.
    Optional ``label_colors`` colors y-tick labels in row order.
    Optional ``aa_colors`` / ``property_legend_items`` override the default scheme.
    Optional ``xtick_labels`` replaces MSA-column indices on the x-axis (same
    length as ``col_indices``); ``xlabel`` sets the axis label.
    """
    import textwrap

    from matplotlib.patches import Rectangle

    color_map = aa_colors if aa_colors is not None else AA_COLORS

    if col_indices is None:
        col_indices = np.arange(mat.shape[1])
    col_indices = np.asarray(col_indices, dtype=int)
    if col_indices.size == 0:
        ax.axis("off")
        ax.set_title(title, fontsize=10, fontweight="bold", color=C_INK, loc="left", pad=8)
        ax.text(0.5, 0.5, "No columns passed the display filter", ha="center", va="center",
                transform=ax.transAxes, color=C_MUTED)
        return

    sub = mat[:, col_indices]
    n_rows, n_cols = sub.shape
    occ, cons = column_stats(mat)

    rgb = np.ones((n_rows, n_cols, 3))
    for i in range(n_rows):
        for j in range(n_cols):
            rgb[i, j] = _hex_rgb(color_map.get(sub[i, j], "#eeeeee"))

    ax.imshow(
        rgb, aspect="auto", interpolation="nearest",
        extent=(-0.5, n_cols - 0.5, n_rows - 0.5, -0.5),
        zorder=1,
    )

    if draw_letters:
        for i in range(n_rows):
            for j in range(n_cols):
                aa = sub[i, j]
                if aa == "-":
                    continue
                tc = "#1a1a1a" if _luminance(rgb[i, j]) > 0.55 else "#ffffff"
                ax.text(
                    j, i, aa, ha="center", va="center",
                    fontsize=letter_fs, fontweight="bold", color=tc,
                    family="DejaVu Sans Mono", zorder=5,
                )

    # Conservation as a normal upward bar chart in a slim axes above the MSA.
    from mpl_toolkits.axes_grid1 import make_axes_locatable

    divider = make_axes_locatable(ax)
    ax_cons = divider.append_axes("top", size="9%", pad=0.06, sharex=ax)
    cons_vals = [float(cons[int(c)]) for c in col_indices]
    ax_cons.bar(
        np.arange(n_cols, dtype=float),
        cons_vals,
        width=0.92,
        color=C_FOCUS,
        edgecolor="none",
        align="center",
        zorder=2,
    )
    ax_cons.set_ylim(0.0, 1.02)
    ax_cons.set_yticks([])
    ax_cons.set_ylabel(
        "cons.",
        fontsize=cons_label_fs,
        color=C_MUTED,
        rotation=0,
        ha="right",
        va="center",
        labelpad=10,
    )
    ax_cons.tick_params(bottom=False, labelbottom=False, left=False)
    for spine in ("top", "right", "bottom"):
        ax_cons.spines[spine].set_visible(False)
    ax_cons.spines["left"].set_color(C_LINE)
    ax_cons.set_facecolor(C_BG)
    ax_cons.set_xlim(-0.5, n_cols - 0.5)
    # Selection track intentionally omitted unless mark_preferred is set below
    # on the main axes (legacy); pocket MSA passes mark_preferred=None.

    preferred_set = set(int(c) for c in (mark_preferred or []))
    if preferred_set:
        ax_sel = divider.append_axes("top", size="3.5%", pad=0.02, sharex=ax)
        for j, c in enumerate(col_indices):
            if int(c) in preferred_set:
                ax_sel.axvspan(j - 0.5, j + 0.5, color=C_POCKET, lw=0)
        ax_sel.set_yticks([])
        ax_sel.set_ylabel(
            "sel.",
            fontsize=6.0,
            color=C_POCKET,
            rotation=0,
            ha="right",
            va="center",
            labelpad=10,
        )
        ax_sel.tick_params(bottom=False, labelbottom=False, left=False)
        for spine in ("top", "right", "bottom", "left"):
            ax_sel.spines[spine].set_visible(False)
        ax_sel.set_xlim(-0.5, n_cols - 0.5)
        ax_sel.set_facecolor(C_BG)

    # Thin boundaries between (and around) cluster blocks.
    if label_colors is not None and len(label_colors) == n_rows:
        boundaries = [0]
        for i in range(1, n_rows):
            if label_colors[i] != label_colors[i - 1]:
                boundaries.append(i)
        boundaries.append(n_rows)
        for b in boundaries:
            y = b - 0.5
            ax.plot(
                [-0.5, n_cols - 0.5],
                [y, y],
                color="0.12",
                lw=0.85,
                solid_capstyle="butt",
                zorder=6,
                clip_on=False,
            )
        for a, b in zip(boundaries[:-1], boundaries[1:]):
            ax.add_patch(
                Rectangle(
                    (-0.5, a - 0.5),
                    0.12,
                    float(b - a),
                    facecolor=label_colors[a],
                    edgecolor="none",
                    alpha=0.95,
                    clip_on=False,
                    zorder=6,
                )
            )

    if highlight_rows:
        name_to_i = {n.lstrip("*"): i for i, n in enumerate(names)}
        name_to_i.update({n: i for i, n in enumerate(names)})
        for label in highlight_rows:
            key = str(label).lstrip("*")
            if key in name_to_i:
                i = name_to_i[key]
                ax.axhline(i - 0.5, color=C_INK, lw=0.9, alpha=0.85, zorder=6)
                ax.axhline(i + 0.5, color=C_INK, lw=0.9, alpha=0.85, zorder=6)

    ax.set_yticks(range(n_rows))
    ax.set_yticklabels(names, fontsize=label_fs, family="DejaVu Sans Mono")
    if label_colors is not None and len(label_colors) == n_rows:
        for tick, color in zip(ax.get_yticklabels(), label_colors):
            tick.set_color(color)
            tick.set_fontweight("bold")
    tick_step = max(1, n_cols // 12)
    xt = list(range(0, n_cols, tick_step))
    if xt[-1] != n_cols - 1:
        xt.append(n_cols - 1)
    ax.set_xticks(xt)
    if xtick_labels is not None:
        if len(xtick_labels) != len(col_indices):
            raise ValueError("xtick_labels must match col_indices length")
        xlabels = [str(xtick_labels[j]) for j in xt]
    else:
        xlabels = [str(int(col_indices[j])) for j in xt]
    ax.set_xticklabels(xlabels, fontsize=max(5.5, label_fs - 0.8))
    if xlabel:
        ax.set_xlabel(xlabel, fontsize=max(7.0, label_fs - 0.5), color=C_INK, labelpad=3)
    ax.set_xlim(-0.5, n_cols - 0.5)
    ax.set_ylim(n_rows - 0.5, -0.5)
    ax.tick_params(axis="x", pad=1, length=2)
    ax.tick_params(axis="y", length=0)
    for spine in ("top", "right"):
        ax.spines[spine].set_visible(False)
    ax.spines["left"].set_visible(False)
    ax.spines["bottom"].set_color(C_LINE)
    # Title on the uppermost track so it sits above cons / sel.
    title_ax = ax_sel if preferred_set else ax_cons
    title_ax.set_title(
        title,
        fontsize=max(9.0, label_fs + 2.5),
        fontweight="bold",
        color=C_INK,
        loc="left",
        pad=6,
    )

    # Legend + footer packed tightly under the axes (axes-fraction coords)
    y_leg = -0.042
    if show_property_legend:
        items = list(
            property_legend_items
            if property_legend_items is not None
            else (
                ("hydrophobic", "#f5f0c8"),
                ("aromatic", "#f4a6a6"),
                ("polar", "#a8d8a8"),
                ("acidic", "#f08080"),
                ("basic", "#8eb4e0"),
                ("G/P/C", "#e8e070"),
                ("gap", "#f2f2f2"),
            )
        )
        x = 0.0
        swatch_w = 0.014
        gap_after_swatch = 0.020
        gap_between = 0.045
        for lab, col in items:
            ax.add_patch(
                Rectangle(
                    (x, y_leg - 0.011),
                    swatch_w,
                    0.022,
                    facecolor=col,
                    edgecolor=C_LINE,
                    lw=0.5,
                    clip_on=False,
                    transform=ax.transAxes,
                    zorder=10,
                )
            )
            ax.text(
                x + swatch_w + gap_after_swatch,
                y_leg,
                lab,
                fontsize=legend_fs,
                color=C_INK,
                va="center",
                ha="left",
                transform=ax.transAxes,
                clip_on=False,
            )
            # Advance by swatch + estimated label width (axes fraction).
            x += swatch_w + gap_after_swatch + 0.0105 * max(len(lab), 1) + gap_between

    y_foot = -0.072 if show_property_legend else -0.038
    footer_wrapped = "\n".join(textwrap.wrap(footer, width=110))
    ax.text(
        0.0, y_foot, footer_wrapped,
        fontsize=footer_fs, color=C_INK, va="top", ha="left",
        transform=ax.transAxes, clip_on=False, linespacing=1.1,
    )


def _msa_letter_fs(n_cols: int) -> float:
    if n_cols <= 20:
        return 10.5
    if n_cols <= 30:
        return 9.5
    if n_cols <= 45:
        return 8.2
    if n_cols <= 70:
        return 6.5
    return 4.8


def _msa_footer(
    *,
    min_occupancy: float,
    min_conservation: float,
    n_selected: int,
    n_total: int,
    pocket: bool = False,
) -> str:
    """One-line footer with display parameters only."""
    tag = "pocket cols" if pocket else "cols"
    return (
        f"occ ≥ {min_occupancy:.2f}  ·  cons ≥ {min_conservation:.2f}  ·  "
        f"n={n_selected}/{n_total} {tag}  ·  Star MSA, BLOSUM62, gaps −10/−0.5"
    )


def plot_msa_panels(
    fasta_file: str,
    output_dir: str,
    *,
    preferred_cols: Optional[Sequence[int]] = None,
    full_name: str = "reference_msa_full.png",
    focused_name: str = "reference_msa_high_consensus.png",
    min_occupancy: float = POCKET_MIN_OCCUPANCY,
    min_conservation: float = POCKET_MIN_CONSERVATION,
    target_n: int = POCKET_TARGET_N,
    highlight_rows: Optional[Sequence[str]] = None,
) -> Dict[str, Any]:
    """Write filtered full + pocket/high-consensus MSA PNGs."""
    import matplotlib.pyplot as plt

    names, mat = load_msa_fasta(fasta_file)
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)

    # Full MSA (display-filtered across all columns — not pocket-restricted)
    sel_full = select_high_consensus_columns(
        mat, None,
        min_occupancy=min_occupancy,
        min_conservation=min_conservation,
        target_n=target_n,
    )
    # Full MSA — wide horizontal panel (2× prior width)
    fig, ax = plt.subplots(figsize=(22.0, 10.0), dpi=300, facecolor=C_BG)
    _draw_msa(
        ax, names, mat,
        col_indices=sel_full,
        title="Multiple sequence alignment",
        footer=_msa_footer(
            min_occupancy=min_occupancy,
            min_conservation=min_conservation,
            n_selected=len(sel_full),
            n_total=mat.shape[1],
            pocket=False,
        ),
        draw_letters=True,
        letter_fs=_msa_letter_fs(len(sel_full)),
        label_fs=7.8,
        highlight_rows=None,
        mark_preferred=None,
    )
    full_path = out / full_name
    fig.subplots_adjust(left=0.07, right=0.995, top=0.94, bottom=0.08)
    fig.savefig(full_path, dpi=300, facecolor=fig.get_facecolor(), bbox_inches="tight", pad_inches=0.06)
    plt.close(fig)

    # Focused pocket / high-consensus panel — fixed size for compositing
    sel = select_high_consensus_columns(
        mat, preferred_cols,
        min_occupancy=min_occupancy,
        min_conservation=min_conservation,
        target_n=target_n,
    )
    fig, ax = plt.subplots(figsize=(7.3, 6.4), dpi=300, facecolor=C_BG)
    _draw_msa(
        ax, names, mat,
        col_indices=sel,
        title="High-consensus alignment columns (filtered)",
        footer=_msa_footer(
            min_occupancy=min_occupancy,
            min_conservation=min_conservation,
            n_selected=len(sel),
            n_total=mat.shape[1],
            pocket=True,
        ),
        draw_letters=True,
        letter_fs=max(4.5, _msa_letter_fs(len(sel)) * 0.72),
        label_fs=5.2,
        highlight_rows=highlight_rows,
        mark_preferred=preferred_cols,
    )
    focused_path = out / focused_name
    fig.subplots_adjust(left=0.16, right=0.99, top=0.92, bottom=0.10)
    # Keep exact (7.3, 6.4) in for Inkscape composites
    fig.savefig(focused_path, dpi=300, facecolor=fig.get_facecolor(), bbox_inches=None, pad_inches=0)
    plt.close(fig)

    return {
        "success": True,
        "full_msa_plot": str(full_path),
        "focused_msa_plot": str(focused_path),
        "n_sequences": len(names),
        "n_columns_alignment": int(mat.shape[1]),
        "n_columns_full_display": int(len(sel_full)),
        "n_columns_focused": int(len(sel)),
        "n_columns_full": int(mat.shape[1]),  # backward-compatible key
        "min_occupancy": float(min_occupancy),
        "min_conservation": float(min_conservation),
        "msa_method": MSA_METHOD,
        "selected_columns": [int(c) for c in sel],
        "full_display_columns": [int(c) for c in sel_full],
    }


@tool
def plot_reference_msa_alignment(
    working_dir: str,
    alignment_fasta: str = "reference_msa_alignment.fasta",
    pocket_definition_json: str = "",
    full_plot_file: str = "reference_msa_full.png",
    focused_plot_file: str = "reference_msa_high_consensus.png",
    min_occupancy: float = POCKET_MIN_OCCUPANCY,
    min_conservation: float = POCKET_MIN_CONSERVATION,
    target_n_columns: int = POCKET_TARGET_N,
) -> dict:
    """Plot star-MSA alignment as (1) full MSA and (2) filtered high-consensus / pocket columns.

    Call after ``build_consensus_sequence_alignment``. If ``pocket_definition_json``
    is provided (e.g. reference_pocket_definition.json), the focused panel prefers
    those consensus-pocket MSA columns, then applies the display filters below.

    Display column selection (focused panel only; does not redefine the pocket):
      * ``min_occupancy`` — fraction of sequences non-gap in the column (default 0.90)
      * ``min_conservation`` — modal amino-acid fraction among non-gaps (default 0.40)
      * ``target_n_columns`` — hard cap after ranking by conservation (default 40)

    The star MSA itself (used for pocket mapping and reference PCA) is built by
    ``build_consensus_sequence_alignment`` (framework ``min_coverage`` default 0.85).
    """
    try:
        base = Path(working_dir)
        fasta = Path(alignment_fasta)
        if not fasta.is_file():
            fasta = base / alignment_fasta
        if not fasta.is_file():
            return {"success": False, "error": f"Alignment FASTA not found: {alignment_fasta}"}

        preferred = None
        if pocket_definition_json:
            import json

            pdef = Path(pocket_definition_json)
            if not pdef.is_file():
                pdef = base / pocket_definition_json
            if pdef.is_file():
                defn = json.loads(pdef.read_text())
                preferred = [
                    int(p["msa_col"])
                    for p in defn.get("consensus_pocket_positions", [])
                    if "msa_col" in p
                ]

        result = plot_msa_panels(
            str(fasta),
            str(base),
            preferred_cols=preferred,
            full_name=full_plot_file,
            focused_name=focused_plot_file,
            min_occupancy=float(min_occupancy),
            min_conservation=float(min_conservation),
            target_n=int(target_n_columns),
            highlight_rows=None,
        )
        result["target_n_columns"] = int(target_n_columns)
        return result
    except Exception as exc:
        logger.exception("plot_reference_msa_alignment failed")
        return {"success": False, "error": str(exc)}
