"""
Per-simulation PCA / FEL on consensus-mapped Cα — **without** reference projection.

Uses the consensus residue map so each protein is analysed on equivalent
(MSA-aligned) Cα positions, but fits a **local** PCA basis per trajectory
(aligned to that trajectory's own frame 0). Outputs mirror local FEL artifacts
and live under ``{base}/analysis/consensus_local_fel/{uniprot}/``.
"""
from __future__ import annotations

import csv
import json
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

import numpy as np

from src.analysis.combined_analysis import _find_sim_traj_topology
from src.analysis.pca_analyzer import (
    DEFAULT_MIN_BASIN_POPULATION,
    analyze_fel_landscape_core,
    _write_pca_tables,
    _write_fel_feature_tables,
    _compute_free_energy_grid,
)
from src.analysis.reference_landscape import (
    _kabsch_align_mobile_to_ref,
    _mapping_for_label,
    _resolve_chain_id_for_label,
    extract_consensus_ca_coords,
    load_consensus_alignment,
)

logger = logging.getLogger(__name__)

try:
    import MDAnalysis as mda

    HAS_MDA = True
except Exception:  # pragma: no cover
    HAS_MDA = False

DEFAULT_CONSENSUS_FEL_DIR = "consensus_local_fel"
DEFAULT_ALIGNMENT_JSON = "reference_msa_alignment.json"


def _trajectory_coord_matrix_self_aligned(
    topology_file: str,
    trajectory_file: str,
    mapping: Sequence[Optional[Dict[str, Any]]],
    *,
    frame_interval: int = 1,
    chain_id: Optional[str] = None,
) -> Tuple[np.ndarray, np.ndarray, np.ndarray, int]:
    """
    Flattened consensus Cα coords per frame, Kabsch-aligned to **this** traj frame 0.

    Only consensus columns mapped (finite) at frame 0 for this protein are kept —
    no fill from a reference structure and no shared PCA model.
    """
    u = mda.Universe(topology_file, trajectory_file)
    ref_coords = extract_consensus_ca_coords(u, 0, mapping, chain_id=chain_id)
    keep = np.isfinite(ref_coords).all(axis=1)
    n_atoms = int(keep.sum())
    if n_atoms < 3:
        return np.zeros((0, 0)), np.asarray([]), keep, n_atoms

    ref_k = ref_coords[keep]
    rows: List[np.ndarray] = []
    times_ps: List[float] = []
    step = max(1, int(frame_interval))
    for ts in u.trajectory[::step]:
        coords = extract_consensus_ca_coords(u, ts.frame, mapping, chain_id=chain_id)
        mobile = coords[keep]
        # Frames may briefly lose atoms; fill NaNs from frame-0 local coords after align attempt
        if not np.isfinite(mobile).all():
            finite = np.isfinite(mobile).all(axis=1)
            filled = mobile.copy()
            filled[~finite] = ref_k[~finite]
            mobile = filled
        aligned = _kabsch_align_mobile_to_ref(mobile, ref_k)
        rows.append(aligned.ravel())
        times_ps.append(float(ts.time))

    if not rows:
        return np.zeros((0, 0)), np.asarray(times_ps), keep, n_atoms
    return np.asarray(rows, dtype=float), np.asarray(times_ps), keep, n_atoms


def run_consensus_local_pca_fel(
    *,
    sim_dir: str,
    label: str,
    display_name: str,
    consensus_json: str,
    output_dir: str,
    base_dir: str = "",
    n_components: int = 10,
    frame_interval: int = 1,
    bins: int = 50,
    temperature_k: float = 310.0,
    smooth_sigma: float = 2.0,
    min_basin_population: float = DEFAULT_MIN_BASIN_POPULATION,
    min_prominence_kj_mol: float = 1.5,
    chain_id: Optional[str] = None,
    overwrite: bool = False,
) -> Dict[str, Any]:
    """
    Fit local PCA on consensus-mapped Cα and build FEL for one simulation.

    Writes into ``output_dir``:
      pca_projections.dat, pca_variance.dat, fel_pc1_pc2_grid.csv, fel_pc1_pc2.png,
      fel_features.json / .csv, fel_basins.csv, consensus_local_fel_meta.json
    """
    if not HAS_MDA:
        return {"success": False, "error": "MDAnalysis is required"}

    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    feat_path = out / "fel_features.json"
    if feat_path.is_file() and not overwrite:
        return {
            "success": True,
            "skipped": True,
            "label": label,
            "message": f"Already exists: {feat_path}",
            "output_dir": str(out.resolve()),
        }

    loaded = load_consensus_alignment(consensus_json)
    if not loaded.get("success"):
        return loaded

    mapping = _mapping_for_label(loaded["consensus_positions"], display_name)
    if sum(1 for m in mapping if m) < 3:
        # Fall back to UniProt label key if MSA stores that form
        mapping = _mapping_for_label(loaded["consensus_positions"], label)
    if sum(1 for m in mapping if m) < 3:
        return {
            "success": False,
            "error": (
                f"{label}/{display_name}: <3 mapped consensus residues in MSA"
            ),
            "label": label,
        }

    topo, traj = _find_sim_traj_topology(sim_dir)
    if not topo or not traj:
        return {"success": False, "error": f"No topology/trajectory under {sim_dir}"}

    cid = _resolve_chain_id_for_label(
        display_name, sim_dir, base_dir or str(Path(sim_dir).parent), chain_id
    )

    try:
        from src.analysis.reference_landscape import _fit_pca_model, _project_coords

        X, times_ps, keep_mask, n_atoms = _trajectory_coord_matrix_self_aligned(
            topo,
            traj,
            mapping,
            frame_interval=frame_interval,
            chain_id=cid,
        )
        if X.shape[0] < 2 or n_atoms < 3:
            return {
                "success": False,
                "error": (
                    f"{label}: need ≥2 frames and ≥3 consensus Cα; "
                    f"got frames={X.shape[0]}, n_atoms={n_atoms}"
                ),
            }

        model = _fit_pca_model(X, n_components)
        projections = _project_coords(X, model)

        proj_file = str(out / "pca_projections.dat")
        var_file = str(out / "pca_variance.dat")
        # Write absolute paths temporarily from out cwd via explicit paths
        _write_pca_tables(
            projections,
            model["variance"],
            model["cumulative_variance"],
            times_ps,
            projections_file=proj_file,
            variance_file=var_file,
        )

        meta = {
            "label": label,
            "display_name": display_name,
            "mode": "consensus_local_pca_fel",
            "note": (
                "PCA fitted per simulation on consensus-mapped Cα; "
                "aligned to frame 0 of the same trajectory — "
                "no projection onto a reference PCA model."
            ),
            "consensus_json": str(Path(consensus_json).resolve()),
            "n_consensus_positions_total": len(mapping),
            "n_consensus_atoms_used": n_atoms,
            "n_frames": int(X.shape[0]),
            "topology_file": topo,
            "trajectory_file": traj,
            "chain_id": cid,
            "n_components": int(model["n_components"]),
            "variance": model["variance"].tolist(),
            "cumulative_variance": model["cumulative_variance"].tolist(),
            "pc1_variance_fraction": float(model["cumulative_variance"][0])
            if len(model["cumulative_variance"])
            else None,
        }
        (out / "consensus_local_fel_meta.json").write_text(
            json.dumps(meta, indent=2), encoding="utf-8"
        )

        # Build FEL without tools that chdir (not thread-safe in batch mode).
        grid = _compute_free_energy_grid(
            projections[:, 0],
            projections[:, 1],
            bins=bins,
            temperature_k=temperature_k,
        )
        if not grid.get("success"):
            return {
                "success": False,
                "error": grid.get("error"),
                "label": label,
            }

        grid_out = out / "fel_pc1_pc2_grid.csv"
        F = grid["free_energy"]
        P = grid["probability"]
        with open(grid_out, "w", newline="", encoding="utf-8") as fh:
            writer = csv.writer(fh)
            writer.writerow(["PC1", "PC2", "free_energy_kJ_mol", "probability"])
            for j in range(F.shape[0]):
                for i in range(F.shape[1]):
                    writer.writerow([
                        f"{grid['x_centers'][i]:.6f}",
                        f"{grid['y_centers'][j]:.6f}",
                        f"{F[j, i]:.6f}",
                        f"{P[j, i]:.6e}",
                    ])

        features = analyze_fel_landscape_core(
            F,
            P,
            smooth_sigma=smooth_sigma,
            min_basin_population=min_basin_population,
            min_prominence_kj_mol=min_prominence_kj_mol,
        )
        _write_fel_feature_tables(
            features,
            output_json=str(out / "fel_features.json"),
            output_csv=str(out / "fel_features.csv"),
            output_basins_csv=str(out / "fel_basins.csv"),
        )

        # Optional FEL plot (best-effort; skip quietly if matplotlib missing)
        try:
            import matplotlib

            matplotlib.use("Agg")
            import matplotlib.pyplot as plt
            from src.analysis.pca_analyzer import (
                FEL_BASIN_CMAP,
                FEL_ENERGY_CONTOUR_KJ,
                _fel_surface_levels,
            )

            Xg, Yg = np.meshgrid(grid["x_centers"], grid["y_centers"])
            F_plot = F.astype(float).copy()
            F_plot[P <= 0] = np.nan
            finite = F_plot[np.isfinite(F_plot)]
            if finite.size:
                F_plot = F_plot - float(np.nanmin(finite))
            levels, vmin, vmax = _fel_surface_levels(F_plot, P)
            fig, ax = plt.subplots(figsize=(7.5, 6))
            cf = ax.contourf(
                Xg, Yg, F_plot, levels=levels, cmap=FEL_BASIN_CMAP,
                vmin=vmin, vmax=vmax, extend="max",
            )
            iso = [lv for lv in FEL_ENERGY_CONTOUR_KJ if vmin < lv < vmax]
            if iso:
                ax.contour(
                    Xg, Yg, F_plot, levels=iso, colors="0.15", linewidths=0.45, alpha=0.55
                )
            ax.set_facecolor("0.97")
            fig.colorbar(cf, ax=ax, label="Relative free energy (kJ/mol)")
            ax.set_xlabel("PC1 (Å)")
            ax.set_ylabel("PC2 (Å)")
            ax.set_title(
                f"Consensus-local FEL — {display_name} (T={temperature_k:.0f} K)"
            )
            fig.tight_layout()
            fig.savefig(out / "fel_pc1_pc2.png", dpi=150, bbox_inches="tight")
            plt.close(fig)
        except Exception as plot_exc:
            logger.debug("FEL plot skipped for %s: %s", label, plot_exc)

        return {
            "success": True,
            "label": label,
            "display_name": display_name,
            "n_consensus_atoms": n_atoms,
            "output_dir": str(out.resolve()),
            "fel_features": str((out / "fel_features.json").resolve()),
        }
    except Exception as exc:
        logger.exception("consensus local FEL failed for %s", label)
        return {"success": False, "error": str(exc), "label": label}


def run_consensus_local_fel_batch(
    *,
    base_dir: str,
    analysis_dir: Optional[str] = None,
    consensus_json: Optional[str] = None,
    output_subdir: str = DEFAULT_CONSENSUS_FEL_DIR,
    labels: Optional[Sequence[str]] = None,
    frame_interval: int = 1,
    overwrite: bool = False,
    max_workers: int = 1,
) -> Dict[str, Any]:
    """Run consensus-local PCA/FEL for all (or selected) UniProt simulation dirs."""
    from src.analysis.reference_labels import build_uniprot_display_map

    base = Path(base_dir).resolve()
    an = Path(analysis_dir).resolve() if analysis_dir else base / "analysis"
    cjson = Path(consensus_json) if consensus_json else an / DEFAULT_ALIGNMENT_JSON
    if not cjson.is_file():
        return {"success": False, "error": f"Consensus MSA not found: {cjson}"}

    out_root = an / output_subdir
    out_root.mkdir(parents=True, exist_ok=True)
    name_map = build_uniprot_display_map(an)

    if labels:
        uids = [str(x).lower() for x in labels]
    else:
        # Prefer UniProt-like campaign dirs that appear in the display map /
        # reference-pocket set; skip stray leftover folders (ROP2, RYK, …).
        name_map_preview = build_uniprot_display_map(an)
        uids = sorted(
            d.name
            for d in base.iterdir()
            if d.is_dir()
            and (d / "hpc").is_dir()
            and d.name.lower() in name_map_preview
            and d.name not in {"analysis", "planner", "reporter", "supervisor"}
        )
        if not uids:
            uids = sorted(
                d.name
                for d in base.iterdir()
                if d.is_dir()
                and (d / "hpc").is_dir()
                and d.name not in {"analysis", "planner", "reporter", "supervisor"}
            )

    jobs = []
    for uid in uids:
        sim = base / uid
        if not sim.is_dir():
            continue
        display = name_map.get(uid, name_map.get(uid.lower(), uid.upper()))
        # Prefer map value; build_uniprot_display_map returns display names
        jobs.append((uid, display, sim))

    results: List[Dict[str, Any]] = []

    def _one(job: Tuple[str, str, Path]) -> Dict[str, Any]:
        uid, display, sim = job
        return run_consensus_local_pca_fel(
            sim_dir=str(sim),
            label=uid,
            display_name=display,
            consensus_json=str(cjson),
            output_dir=str(out_root / uid),
            base_dir=str(base),
            frame_interval=frame_interval,
            overwrite=overwrite,
        )

    if max_workers and max_workers > 1:
        from concurrent.futures import ThreadPoolExecutor, as_completed

        with ThreadPoolExecutor(max_workers=int(max_workers)) as ex:
            futs = {ex.submit(_one, j): j[0] for j in jobs}
            for fut in as_completed(futs):
                try:
                    results.append(fut.result())
                except Exception as exc:
                    results.append(
                        {"success": False, "error": str(exc), "label": futs[fut]}
                    )
    else:
        for j in jobs:
            results.append(_one(j))

    ok = [r for r in results if r.get("success")]
    fail = [r for r in results if not r.get("success")]
    manifest = {
        "output_root": str(out_root.resolve()),
        "consensus_json": str(cjson.resolve()),
        "n_requested": len(jobs),
        "n_success": len(ok),
        "n_failed": len(fail),
        "failed": [{"label": r.get("label"), "error": r.get("error")} for r in fail],
        "mode": "consensus_local_pca_fel_no_reference_projection",
    }
    (out_root / "batch_manifest.json").write_text(
        json.dumps(manifest, indent=2), encoding="utf-8"
    )
    (out_root / "README.md").write_text(
        "# Consensus-local FEL (no reference PCA projection)\n\n"
        "Per-simulation PCA/FEL on **consensus-mapped Cα** residues from "
        f"`{cjson.name}`. Each trajectory is aligned to its **own frame 0** "
        "and fitted with a **local** PCA basis (not projected onto MLKL/EPHB6).\n\n"
        "Regenerate:\n"
        "```bash\n"
        "python3 scripts/run_consensus_local_fel_batch.py\n"
        "```\n",
        encoding="utf-8",
    )
    return {
        "success": len(fail) == 0,
        "message": f"Consensus-local FEL: {len(ok)}/{len(jobs)} ok → {out_root}",
        "manifest": manifest,
        "output_root": str(out_root.resolve()),
        "results": results,
    }
