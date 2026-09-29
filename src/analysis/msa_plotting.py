#!/usr/bin/env python3
"""Plot MSA panels for global_consensus_msa and pocket_mapped columns.

Used by combined-analysis agents and manuscript Fig. S3 assets. Plots show
**filtered** columns only (consensus / pocket) — never the unfiltered MAFFT
width as the primary display.
"""
from __future__ import annotations

import json
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

# Legacy display-only filter used only when consensus/pocket JSON is missing.
POCKET_MIN_OCCUPANCY = 0.90
POCKET_MIN_CONSERVATION = 0.40
POCKET_TARGET_N = 40

DEFAULT_CONSENSUS_JSON = "global_consensus_msa.json"
DEFAULT_POCKET_DEFINITION_JSON = "pocket_mapped_definition.json"
DEFAULT_GLOBAL_PLOT = "global_consensus_msa.png"
DEFAULT_POCKET_PLOT = "pocket_mapped_msa.png"
DEFAULT_ALIGNMENT_FASTA = "global_msa.fasta"

CONSENSUS_JSON_CANDIDATES = (
    "global_consensus_msa.json",
    "global_mapped.json",
    "reference_msa_alignment.json",
    "consensus_residues.json",
)
FASTA_CANDIDATES = (
    "global_msa.fasta",
    "reference_msa_alignment.fasta",
    "consensus_msa.fasta",
)
POCKET_DEFINITION_CANDIDATES = (
    "pocket_mapped_definition.json",
    "reference_pocket_definition.json",
    "pocket_mapped.json",
)


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
    """Legacy display filter when consensus/pocket JSON is unavailable."""
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


def _valid_cols(cols: Sequence[int], n_width: int) -> np.ndarray:
    keep = sorted({int(c) for c in cols if c is not None and 0 <= int(c) < n_width})
    return np.asarray(keep, dtype=int)


def load_msa_cols_from_consensus_json(path: Path) -> List[int]:
    """Return MSA column indices from ``global_consensus_msa.json`` (or legacy)."""
    from src.analysis.cross_sim_artifacts import expand_consensus_positions

    data = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(data.get("msa_cols"), list) and data["msa_cols"]:
        return [int(c) for c in data["msa_cols"] if c is not None]
    positions = expand_consensus_positions(data) if isinstance(data, dict) else []
    cols: List[int] = []
    for pos in positions:
        c = pos.get("msa_col")
        if c is not None:
            cols.append(int(c))
    return cols


def load_msa_cols_from_pocket_definition(path: Path) -> List[int]:
    """Return pocket_mapped MSA column indices from pocket definition / map."""
    data = json.loads(path.read_text(encoding="utf-8"))
    cols: List[int] = []
    for key in (
        "consensus_pocket_positions",
        "pocket_positions",
        "consensus_positions",
    ):
        for pos in data.get(key) or []:
            if isinstance(pos, dict) and pos.get("msa_col") is not None:
                cols.append(int(pos["msa_col"]))
        if cols:
            return cols
    if isinstance(data.get("msa_cols"), list):
        return [int(c) for c in data["msa_cols"] if c is not None]
    return cols


def _resolve_existing(base: Path, requested: str, candidates: Sequence[str]) -> Optional[Path]:
    if requested:
        p = Path(requested)
        if not p.is_file():
            p = base / requested
        if p.is_file():
            return p
    for name in candidates:
        cand = base / name
        if cand.is_file():
            return cand
    return None


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
    top_bar_values: Optional[Sequence[float]] = None,
    top_bar_label: str = "cons.",
    top_bar_vmax: Optional[float] = None,
    show_conservation_under_top_bar: bool = True,
    cons_bar_color: Optional[str] = None,
    column_groups: Optional[Sequence[Tuple[str, str]]] = None,
    xlabel_pad: float = 6.0,
    xtick_pad: float = 1.0,
    legend_y: float = -0.055,
    footer_y: Optional[float] = None,
    show_footer: bool = True,
):
    """Draw an MSA heatmap that spans the full axes width.

    Legend (line 1) and footer (line 2+) are placed in axes-fraction space below
    the grid so they never compete with column width or overlap each other.
    Optional ``label_colors`` colors y-tick labels in row order.
    Optional ``aa_colors`` / ``property_legend_items`` override the default scheme.
    Optional ``xtick_labels`` replaces MSA-column indices on the x-axis (same
    length as ``col_indices``); ``xlabel`` sets the axis label.
    Optional ``top_bar_values`` replaces the default conservation-only bar (e.g. mean
    RMSF). When ``top_bar_values`` is set, a modal-conservation track is still drawn
    immediately underneath that bar unless ``show_conservation_under_top_bar`` is False.
    Optional ``column_groups`` is a (label, color) pair per displayed column and
    draws a motif strip between the bars and the MSA.
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

    # Tracks above the MSA (appended bottom→top): motif → conservation → RMSF/cons.
    from mpl_toolkits.axes_grid1 import make_axes_locatable

    divider = make_axes_locatable(ax)
    ax_grp = None
    if column_groups is not None:
        if len(column_groups) != n_cols:
            raise ValueError("column_groups must match the number of displayed columns")
        ax_grp = divider.append_axes("top", size="3.25%", pad=0.02, sharex=ax)
        ax_grp.set_ylim(0.0, 1.0)
        ax_grp.set_yticks([])
        ax_grp.tick_params(bottom=False, labelbottom=False, left=False)
        for spine in ("top", "right", "bottom", "left"):
            ax_grp.spines[spine].set_visible(False)
        ax_grp.set_xlim(-0.5, n_cols - 0.5)
        ax_grp.set_facecolor(C_BG)
        j = 0
        while j < n_cols:
            lab, gcol = column_groups[j]
            k = j
            while k + 1 < n_cols and column_groups[k + 1][0] == lab:
                k += 1
            ax_grp.axvspan(j - 0.5, k + 0.5, color=gcol, alpha=0.92, lw=0, zorder=1)
            rgb_g = _hex_rgb(gcol)
            tc = "#ffffff" if _luminance(rgb_g) < 0.55 else "#1c2429"
            ax_grp.text(
                0.5 * (j + k),
                0.5,
                lab,
                ha="center",
                va="center",
                fontsize=max(4.6, cons_label_fs - 1.4),
                fontweight="bold",
                color=tc,
                clip_on=True,
                zorder=2,
            )
            j = k + 1
        ax_grp.set_ylabel(
            "motif",
            fontsize=cons_label_fs,
            color=C_MUTED,
            rotation=0,
            ha="right",
            va="center",
            labelpad=10,
        )

    def _style_bar_ax(ax_bar, *, ylab: str, vmax: float) -> None:
        ax_bar.set_ylim(0.0, vmax)
        ax_bar.set_yticks([])
        ax_bar.set_ylabel(
            ylab,
            fontsize=cons_label_fs,
            color=C_MUTED,
            rotation=0,
            ha="right",
            va="center",
            labelpad=10,
        )
        ax_bar.tick_params(bottom=False, labelbottom=False, left=False)
        for spine in ("top", "right", "bottom"):
            ax_bar.spines[spine].set_visible(False)
        ax_bar.spines["left"].set_color(C_LINE)
        ax_bar.set_facecolor(C_BG)
        ax_bar.set_xlim(-0.5, n_cols - 0.5)

    cons_vals = [float(cons[int(c)]) for c in col_indices]
    bar_face = cons_bar_color or C_FOCUS

    # Conservation under the custom top bar (e.g. RMSF), or as the only top track.
    if top_bar_values is not None and show_conservation_under_top_bar:
        ax_cons_under = divider.append_axes("top", size="7.5%", pad=0.04, sharex=ax)
        ax_cons_under.bar(
            np.arange(n_cols, dtype=float),
            cons_vals,
            width=0.92,
            color=bar_face,
            edgecolor="none",
            align="center",
            zorder=2,
        )
        _style_bar_ax(ax_cons_under, ylab="cons.", vmax=1.02)

    ax_cons = divider.append_axes("top", size="9%", pad=0.05, sharex=ax)
    if top_bar_values is not None:
        if len(top_bar_values) != n_cols:
            raise ValueError("top_bar_values must match the number of displayed columns")
        bar_vals = [float(v) if np.isfinite(v) else 0.0 for v in top_bar_values]
        vmax = float(top_bar_vmax) if top_bar_vmax is not None else max(bar_vals + [1e-6])
        ylab = top_bar_label
        bar_color = C_FOCUS
        ylim = vmax * 1.05
    else:
        bar_vals = cons_vals
        vmax = 1.02
        ylab = "cons."
        bar_color = bar_face
        ylim = vmax
    ax_cons.bar(
        np.arange(n_cols, dtype=float),
        bar_vals,
        width=0.92,
        color=bar_color,
        edgecolor="none",
        align="center",
        zorder=2,
    )
    _style_bar_ax(ax_cons, ylab=ylab, vmax=ylim)
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
        ax.set_xlabel(
            xlabel,
            fontsize=max(7.0, label_fs - 0.5),
            color=C_INK,
            labelpad=xlabel_pad,
            wrap=False,
        )
    ax.set_xlim(-0.5, n_cols - 0.5)
    ax.set_ylim(n_rows - 0.5, -0.5)
    ax.tick_params(axis="x", pad=xtick_pad, length=2)
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

    # Legend + footer sit below x-tick labels and the x-axis title.
    y_leg = float(legend_y)
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

    if show_footer and footer:
        y_foot = float(footer_y) if footer_y is not None else (
            y_leg - 0.045 if show_property_legend else -0.040
        )
        footer_wrapped = "\n".join(textwrap.wrap(footer, width=160, break_long_words=False, break_on_hyphens=False))
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
    if n_cols <= 120:
        return 4.8
    if n_cols <= 220:
        return 3.6
    return 2.8


def _msa_footer_consensus(
    *,
    n_selected: int,
    n_alignment: int,
    min_conservation: float = 0.5,
    min_coverage: float = 0.25,
) -> str:
    return (
        f"global_consensus_msa  ·  similarity ≥ {min_conservation:.2f}  ·  "
        f"occupancy ≥ {min_coverage:.2f}  ·  n={n_selected}/{n_alignment} cols"
    )


def _msa_footer_pocket(
    *,
    n_selected: int,
    n_consensus: int,
    pocket_cutoff_A: float = 15.0,
) -> str:
    return (
        f"pocket_mapped  ·  {pocket_cutoff_A:g} Å reference shell ∩ consensus  ·  "
        f"n={n_selected}/{n_consensus} cols"
    )


def _msa_footer_legacy(
    *,
    min_occupancy: float,
    min_conservation: float,
    n_selected: int,
    n_total: int,
    pocket: bool = False,
) -> str:
    """Fallback footer when consensus/pocket JSON is missing."""
    tag = "pocket cols" if pocket else "cols"
    return (
        f"occ ≥ {min_occupancy:.2f}  ·  cons ≥ {min_conservation:.2f}  ·  "
        f"n={n_selected}/{n_total} {tag}  ·  Star MSA, BLOSUM62, gaps −10/−0.5"
    )


def plot_msa_panels(
    fasta_file: str,
    output_dir: str,
    *,
    consensus_cols: Optional[Sequence[int]] = None,
    pocket_cols: Optional[Sequence[int]] = None,
    preferred_cols: Optional[Sequence[int]] = None,
    full_name: str = DEFAULT_GLOBAL_PLOT,
    focused_name: str = DEFAULT_POCKET_PLOT,
    min_occupancy: float = POCKET_MIN_OCCUPANCY,
    min_conservation: float = POCKET_MIN_CONSERVATION,
    target_n: int = POCKET_TARGET_N,
    highlight_rows: Optional[Sequence[str]] = None,
    consensus_min_conservation: float = 0.5,
    consensus_min_coverage: float = 0.25,
    pocket_cutoff_A: float = 15.0,
) -> Dict[str, Any]:
    """Write global_consensus_msa + pocket_mapped MSA PNGs.

    Column sets come from calculated artifacts when provided:
      * ``consensus_cols`` → global panel (all consensus columns)
      * ``pocket_cols`` → pocket panel (all pocket_mapped columns)

    The unfiltered MAFFT width is **not** plotted. ``preferred_cols`` is a
    legacy alias for ``pocket_cols``. Display occupancy/conservation filters
    apply only as a fallback when those JSON-derived column lists are absent.
    """
    import matplotlib.pyplot as plt

    names, mat = load_msa_fasta(fasta_file)
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    n_width = int(mat.shape[1])

    used_consensus = consensus_cols is not None and len(list(consensus_cols)) > 0
    if used_consensus:
        sel_full = _valid_cols(consensus_cols, n_width)
        full_footer = _msa_footer_consensus(
            n_selected=len(sel_full),
            n_alignment=n_width,
            min_conservation=consensus_min_conservation,
            min_coverage=consensus_min_coverage,
        )
        full_title = "Global consensus MSA"
    else:
        sel_full = select_high_consensus_columns(
            mat,
            None,
            min_occupancy=min_occupancy,
            min_conservation=min_conservation,
            target_n=target_n,
        )
        full_footer = _msa_footer_legacy(
            min_occupancy=min_occupancy,
            min_conservation=min_conservation,
            n_selected=len(sel_full),
            n_total=n_width,
            pocket=False,
        )
        full_title = "Multiple sequence alignment (display filter)"

    pocket_source = pocket_cols if pocket_cols is not None else preferred_cols
    used_pocket = pocket_source is not None and len(list(pocket_source)) > 0
    if used_pocket:
        sel = _valid_cols(pocket_source, n_width)
        focused_footer = _msa_footer_pocket(
            n_selected=len(sel),
            n_consensus=len(sel_full) if used_consensus else n_width,
            pocket_cutoff_A=pocket_cutoff_A,
        )
        focused_title = "Pocket-mapped MSA"
    else:
        sel = select_high_consensus_columns(
            mat,
            preferred_cols,
            min_occupancy=min_occupancy,
            min_conservation=min_conservation,
            target_n=target_n,
        )
        focused_footer = _msa_footer_legacy(
            min_occupancy=min_occupancy,
            min_conservation=min_conservation,
            n_selected=len(sel),
            n_total=n_width,
            pocket=True,
        )
        focused_title = "High-consensus alignment columns (filtered)"

    # Global consensus panel — wide horizontal
    fig_w = 22.0 if len(sel_full) <= 120 else min(36.0, 14.0 + 0.06 * len(sel_full))
    fig, ax = plt.subplots(figsize=(fig_w, 10.0), dpi=300, facecolor=C_BG)
    _draw_msa(
        ax,
        names,
        mat,
        col_indices=sel_full,
        title=full_title,
        footer=full_footer,
        draw_letters=True,
        letter_fs=_msa_letter_fs(len(sel_full)),
        label_fs=7.8,
        highlight_rows=None,
        mark_preferred=None,
    )
    full_path = out / full_name
    fig.subplots_adjust(left=0.07, right=0.995, top=0.94, bottom=0.08)
    fig.savefig(
        full_path,
        dpi=300,
        facecolor=fig.get_facecolor(),
        bbox_inches="tight",
        pad_inches=0.06,
    )
    plt.close(fig)

    # Pocket panel — widen when many columns
    fig_pw = 7.3 if len(sel) <= 50 else min(22.0, 6.0 + 0.08 * len(sel))
    fig, ax = plt.subplots(figsize=(fig_pw, 6.4), dpi=300, facecolor=C_BG)
    _draw_msa(
        ax,
        names,
        mat,
        col_indices=sel,
        title=focused_title,
        footer=focused_footer,
        draw_letters=True,
        letter_fs=max(3.2, _msa_letter_fs(len(sel)) * 0.85),
        label_fs=5.2,
        highlight_rows=highlight_rows,
        mark_preferred=None,
    )
    focused_path = out / focused_name
    fig.subplots_adjust(left=0.16, right=0.99, top=0.92, bottom=0.10)
    fig.savefig(
        focused_path,
        dpi=300,
        facecolor=fig.get_facecolor(),
        bbox_inches=None if fig_pw <= 7.5 else "tight",
        pad_inches=0 if fig_pw <= 7.5 else 0.04,
    )
    plt.close(fig)

    return {
        "success": True,
        "full_msa_plot": str(full_path),
        "focused_msa_plot": str(focused_path),
        "global_consensus_msa_plot": str(full_path),
        "pocket_mapped_msa_plot": str(focused_path),
        "n_sequences": len(names),
        "n_columns_alignment": n_width,
        "n_columns_global_consensus": int(len(sel_full)),
        "n_columns_pocket_mapped": int(len(sel)),
        "n_columns_full_display": int(len(sel_full)),
        "n_columns_focused": int(len(sel)),
        "n_columns_full": n_width,
        "used_consensus_json": bool(used_consensus),
        "used_pocket_definition": bool(used_pocket),
        "min_occupancy": float(min_occupancy),
        "min_conservation": float(min_conservation),
        "msa_method": MSA_METHOD,
        "selected_columns": [int(c) for c in sel],
        "full_display_columns": [int(c) for c in sel_full],
    }


@tool
def plot_reference_msa_alignment(
    working_dir: str,
    alignment_fasta: str = DEFAULT_ALIGNMENT_FASTA,
    consensus_json: str = DEFAULT_CONSENSUS_JSON,
    pocket_definition_json: str = DEFAULT_POCKET_DEFINITION_JSON,
    full_plot_file: str = DEFAULT_GLOBAL_PLOT,
    focused_plot_file: str = DEFAULT_POCKET_PLOT,
    min_occupancy: float = POCKET_MIN_OCCUPANCY,
    min_conservation: float = POCKET_MIN_CONSERVATION,
    target_n_columns: int = POCKET_TARGET_N,
) -> dict:
    """Plot ``global_consensus_msa`` and ``pocket_mapped`` MSA panels.

    Call after ``build_global_mapped_alignment`` / ``define_pocket_mapped_residues``.

    Panels (paper path):
      * Global: all columns in ``global_consensus_msa.json`` (similarity ≥ 0.5,
        occupancy ≥ 0.25) — **not** the unfiltered MAFFT width.
      * Pocket: all columns in ``pocket_mapped_definition.json``
        (15 Å reference shell ∩ consensus).

    ``alignment_fasta`` supplies AA letters for those columns only. Legacy
    occupancy/conservation display filters apply only if consensus/pocket JSON
    is missing.
    """
    try:
        base = Path(working_dir)
        fasta = _resolve_existing(base, alignment_fasta, FASTA_CANDIDATES)
        if fasta is None:
            return {
                "success": False,
                "error": f"Alignment FASTA not found: {alignment_fasta}",
            }

        cons_path = _resolve_existing(base, consensus_json, CONSENSUS_JSON_CANDIDATES)
        consensus_cols: Optional[List[int]] = None
        cons_min_cons = 0.5
        cons_min_cov = 0.25
        if cons_path is not None:
            try:
                consensus_cols = load_msa_cols_from_consensus_json(cons_path)
                meta = json.loads(cons_path.read_text(encoding="utf-8"))
                if meta.get("min_conservation") is not None:
                    cons_min_cons = float(meta["min_conservation"])
                if meta.get("min_coverage") is not None:
                    cons_min_cov = float(meta["min_coverage"])
            except Exception as exc:
                logger.warning("Could not load consensus cols from %s: %s", cons_path, exc)

        pocket_path = _resolve_existing(
            base, pocket_definition_json, POCKET_DEFINITION_CANDIDATES
        )
        pocket_cols: Optional[List[int]] = None
        pocket_cutoff = 15.0
        if pocket_path is not None:
            try:
                pocket_cols = load_msa_cols_from_pocket_definition(pocket_path)
                meta = json.loads(pocket_path.read_text(encoding="utf-8"))
                if meta.get("pocket_cutoff_A") is not None:
                    pocket_cutoff = float(meta["pocket_cutoff_A"])
            except Exception as exc:
                logger.warning("Could not load pocket cols from %s: %s", pocket_path, exc)

        result = plot_msa_panels(
            str(fasta),
            str(base),
            consensus_cols=consensus_cols,
            pocket_cols=pocket_cols,
            full_name=full_plot_file,
            focused_name=focused_plot_file,
            min_occupancy=float(min_occupancy),
            min_conservation=float(min_conservation),
            target_n=int(target_n_columns),
            highlight_rows=None,
            consensus_min_conservation=cons_min_cons,
            consensus_min_coverage=cons_min_cov,
            pocket_cutoff_A=pocket_cutoff,
        )
        result["target_n_columns"] = int(target_n_columns)
        result["consensus_json"] = str(cons_path) if cons_path else ""
        result["pocket_definition_json"] = str(pocket_path) if pocket_path else ""
        result["alignment_fasta"] = str(fasta)
        return result
    except Exception as exc:
        logger.exception("plot_reference_msa_alignment failed")
        return {"success": False, "error": str(exc)}


@tool
def plot_global_mapped_alignment(
    working_dir: str,
    alignment_fasta: str = DEFAULT_ALIGNMENT_FASTA,
    consensus_json: str = DEFAULT_CONSENSUS_JSON,
    pocket_definition_json: str = DEFAULT_POCKET_DEFINITION_JSON,
    full_plot_file: str = DEFAULT_GLOBAL_PLOT,
    focused_plot_file: str = DEFAULT_POCKET_PLOT,
    min_occupancy: float = POCKET_MIN_OCCUPANCY,
    min_conservation: float = POCKET_MIN_CONSERVATION,
    target_n_columns: int = POCKET_TARGET_N,
) -> dict:
    """Plot global_consensus_msa and pocket_mapped MSA panels (not unfiltered MSA)."""
    return plot_reference_msa_alignment.func(
        working_dir=working_dir,
        alignment_fasta=alignment_fasta,
        consensus_json=consensus_json,
        pocket_definition_json=pocket_definition_json,
        full_plot_file=full_plot_file,
        focused_plot_file=focused_plot_file,
        min_occupancy=min_occupancy,
        min_conservation=min_conservation,
        target_n_columns=target_n_columns,
    )
