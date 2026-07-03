"""Extract frames from MD trajectories as PDB for visualization."""
import os
import csv
import logging
import numpy as np
from pathlib import Path
from typing import Optional, Dict, List, Tuple

logger = logging.getLogger(__name__)


def extract_first_frame_pdb(
    working_dir: str,
    hpc_subdir: str = "hpc",
    output_filename: str = "system_frame0.pdb",
) -> Optional[str]:
    """
    Extract the first frame from available topology/trajectory files as PDB.

    Selects protein, ligands, and coordinated ions (excluding bulk
    Na/Cl/K counter-ions and water) to keep the file lightweight for
    embedding in an HTML viewer.

    Search order for topology: md.gro, processed.gro, md.tpr, \\*.gro
    Trajectory (optional):     md.xtc, \\*.xtc

    Args:
        working_dir:     Base working directory (e.g. ``working_dir``).
        hpc_subdir:      Sub-folder inside *working_dir* that holds simulation
                         output (default ``"hpc"``).
        output_filename: Name of the PDB file to write inside *working_dir/reporter/*.

    Returns:
        Absolute path to the written PDB file, or ``None`` on failure.
    """
    try:
        import MDAnalysis as mda
    except ImportError:
        logger.warning("MDAnalysis not available – cannot extract PDB frame")
        return None

    hpc_dir = Path(working_dir) / hpc_subdir
    if not hpc_dir.is_dir():
        logger.warning(f"HPC directory not found: {hpc_dir}")
        return None

    # --- locate topology ------------------------------------------------
    topology: Optional[Path] = None
    for candidate in ("md.gro", "processed.gro", "md.tpr"):
        p = hpc_dir / candidate
        if p.exists():
            topology = p
            break
    if topology is None:
        gro_files = sorted(hpc_dir.glob("*.gro"))
        if gro_files:
            topology = gro_files[0]
    if topology is None:
        logger.warning("No topology file (.gro/.tpr) found in %s", hpc_dir)
        return None

    # --- locate trajectory (optional) -----------------------------------
    # Prefer the PBC-wrapped trajectory when available (mdWrap.xtc),
    # then fall back to the raw trajectory files.
    trajectory: Optional[Path] = None
    for candidate in ("mdWrap.xtc", "md.xtc", "md.trr"):
        p = hpc_dir / candidate
        if p.exists():
            trajectory = p
            break
    if trajectory is None:
        xtc_files = sorted(hpc_dir.glob("*.xtc"))
        if xtc_files:
            trajectory = xtc_files[0]

    # --- load & write first frame ---------------------------------------
    try:
        if trajectory:
            u = mda.Universe(str(topology), str(trajectory))
        else:
            u = mda.Universe(str(topology))

        # Align all frames to the first frame on Cα / backbone so that
        # the 3D viewer shows a consistently oriented structure.
        if trajectory and u.trajectory.n_frames > 1:
            try:
                from MDAnalysis.analysis import align as _mda_align
                _ref = mda.Universe(str(topology), str(trajectory))
                _ref.trajectory[0]
                _align_sel = "backbone" if u.select_atoms("backbone").n_atoms > 0 else "name CA"
                if u.select_atoms(_align_sel).n_atoms > 0:
                    _mda_align.AlignTraj(u, _ref, select=_align_sel, in_memory=True).run()
                    logger.debug("extract_first_frame_pdb: aligned trajectory on '%s'", _align_sel)
            except Exception as _ae:
                logger.debug("extract_first_frame_pdb: alignment skipped (%s)", _ae)

        # Go to first frame
        u.trajectory[0]

        # Select protein + ligand + non-bulk ions (exclude water & Na/Cl/K counter-ions)
        # This keeps the PDB lightweight for HTML embedding
        _BULK_IONS = "resname NA NA+ CL CL- K K+ SOD CLA"
        _WATER     = "resname HOH WAT SOL TIP3 TIP4 SPC"

        sel_parts = []
        # Always include protein if present
        if len(u.select_atoms("protein")) > 0:
            sel_parts.append("protein")
        # Include nucleic acids if present
        if len(u.select_atoms("nucleic")) > 0:
            sel_parts.append("nucleic")
        # Include everything that is NOT protein, nucleic, water, or bulk ions (= ligands, cofactors, metals)
        other_sel = f"not protein and not nucleic and not ({_WATER}) and not ({_BULK_IONS})"
        if len(u.select_atoms(other_sel)) > 0:
            sel_parts.append(f"({other_sel})")

        if not sel_parts:
            # Fallback: just take everything minus water
            selection_str = f"not ({_WATER})"
        else:
            selection_str = " or ".join(sel_parts)

        selected = u.select_atoms(selection_str)

        reporter_dir = Path(working_dir) / "reporter"
        reporter_dir.mkdir(parents=True, exist_ok=True)
        output_path = reporter_dir / output_filename

        selected.write(str(output_path))

        logger.info(
            "Extracted first frame (%d atoms from %d total) → %s",
            len(selected), len(u.atoms), output_path,
        )
        return str(output_path)

    except Exception as exc:
        logger.error("Failed to extract PDB frame: %s", exc, exc_info=True)
        return None


def read_pdb_data(pdb_path: str) -> Optional[str]:
    """Read a PDB file and return its text content for embedding."""
    try:
        with open(pdb_path, "r") as f:
            return f.read()
    except Exception as exc:
        logger.error("Failed to read PDB file %s: %s", pdb_path, exc)
        return None


def _read_timeseries(
    filepath: str,
    y_col_name: Optional[str] = None,
) -> Optional[Tuple[np.ndarray, np.ndarray]]:
    """Read a 2-column time series from CSV or whitespace-delimited data.

    For CSV files uses the header row to locate time and value columns.
    *y_col_name* is a substring matched against header names (e.g. ``"distance"``,
    ``"contact"``).

    Returns (time_ns, values) numpy arrays, or None on failure.
    """
    p = Path(filepath)
    if not p.is_file():
        return None

    try:
        if p.suffix == ".csv":
            with open(p, "r", encoding="utf-8") as f:
                reader = csv.reader(f)
                header = next(reader, None)
                if header is None:
                    return None
                lower = [h.strip().lower() for h in header]
                t_idx = next(
                    (i for i, h in enumerate(lower) if h in ("time_ns", "time (ns)", "time")),
                    1 if len(header) >= 3 else 0,
                )
                y_idx = None
                if y_col_name:
                    for i, h in enumerate(lower):
                        if y_col_name in h:
                            y_idx = i
                            break
                if y_idx is None:
                    y_idx = next(
                        (
                            i
                            for i, h in enumerate(lower)
                            if any(
                                k in h
                                for k in (
                                    "distance",
                                    "contact",
                                    "rmsd",
                                    "value",
                                    "sasa",
                                    "rmsf",
                                )
                            )
                        ),
                        2 if len(header) >= 3 else 1,
                    )
                times, vals = [], []
                for row in reader:
                    if len(row) <= max(t_idx, y_idx):
                        continue
                    try:
                        t_val = float(row[t_idx])
                        v_val = float(row[y_idx])
                    except ValueError:
                        continue
                    times.append(t_val)
                    vals.append(v_val)
            if not times:
                return None
            t_arr = np.array(times)
            if "time_ns" not in lower[t_idx] and t_arr.max() > 500:
                t_arr = t_arr / 1000.0
            return t_arr, np.array(vals)
        else:
            # Whitespace-delimited: Time(ns)  Value
            data = np.loadtxt(str(p), comments="#")
            if data.ndim != 2 or data.shape[1] < 2:
                return None
            return data[:, 0], data[:, 1]
    except Exception as exc:
        logger.debug("Could not read timeseries %s: %s", filepath, exc)
        return None


def _resolve_analysis_path(fpath: str, working_dir: str) -> str:
    """Resolve a file path relative to *working_dir* or its analysis/ subfolder."""
    p = Path(fpath)
    if p.is_absolute() and p.is_file():
        return str(p)
    base = Path(working_dir)
    for base_dir in (base, base / "analysis"):
        candidate = base_dir / p.name
        if candidate.is_file():
            return str(candidate)
        candidate = base_dir / p
        if candidate.is_file():
            return str(candidate)
    return fpath


def load_fel_basin_structures(
    analysis_data: Dict,
    working_dir: str,
) -> Dict[str, str]:
    """Load FEL basin representative PDBs from the analysis summary.

    Prefers the manifest CSV (rich labels with population and time) and falls
    back to the ``basin_pdbs`` file list.
    """
    import ast

    frames: Dict[str, str] = {}
    entries = analysis_data.get("entries", []) if isinstance(analysis_data, dict) else []

    for entry in entries:
        if (entry.get("analysis_type") or "") != "FELBasinStructures":
            continue
        files = entry.get("files", {}) or {}

        manifest = files.get("manifest_csv")
        if manifest:
            mpath = _resolve_analysis_path(str(manifest), working_dir)
            if Path(mpath).is_file():
                try:
                    with open(mpath, newline="", encoding="utf-8") as fh:
                        for row in csv.DictReader(fh):
                            pdb = row.get("pdb_file") or row.get("pdb")
                            if not pdb:
                                continue
                            pdb = _resolve_analysis_path(str(pdb), working_dir)
                            txt = read_pdb_data(pdb)
                            if not txt:
                                continue
                            bid = row.get("basin_id", "?")
                            try:
                                pop = float(row.get("population", 0)) * 100
                                pop_str = f"{pop:.0f}%"
                            except (TypeError, ValueError):
                                pop_str = "?"
                            t_ns = row.get("time_ns", "")
                            label = f"FEL Basin {bid} ({pop_str}, {t_ns} ns)"
                            frames[label] = txt
                except Exception as exc:
                    logger.warning("Could not read FEL basin manifest %s: %s", mpath, exc)
                if frames:
                    return frames

        basin_pdbs = files.get("basin_pdbs")
        pdb_list: List[str] = []
        if isinstance(basin_pdbs, list):
            pdb_list = [str(x) for x in basin_pdbs]
        elif isinstance(basin_pdbs, str):
            try:
                parsed = ast.literal_eval(basin_pdbs)
                if isinstance(parsed, list):
                    pdb_list = [str(x) for x in parsed]
                elif basin_pdbs.endswith(".pdb"):
                    pdb_list = [basin_pdbs]
            except (ValueError, SyntaxError):
                if basin_pdbs.endswith(".pdb"):
                    pdb_list = [basin_pdbs]

        for i, pdb in enumerate(pdb_list, 1):
            ppath = _resolve_analysis_path(pdb, working_dir)
            txt = read_pdb_data(ppath)
            if txt:
                frames[f"FEL Basin {i}"] = txt

    return frames


def collect_significant_structures(
    analysis_data: Dict,
    working_dir: str,
    hpc_parent: str,
    hpc_subdir: str = "hpc",
    max_total: int = 8,
) -> Dict[str, str]:
    """Collect all scientifically important structures for the 3D viewer.

    Priority:
      1. FEL basin representative PDBs (pre-exported by analysis)
      2. Trajectory frames at analysis-driven time points (COM extrema,
         contact extrema, RMSD peaks, unbinding events, start/end)
    """
    frames: Dict[str, str] = {}

    # --- FEL basins (highest priority) ------------------------------------
    basin_frames = load_fel_basin_structures(analysis_data, working_dir)
    for label, pdb_text in basin_frames.items():
        if len(frames) >= max_total:
            break
        frames[label] = pdb_text

    if len(frames) >= max_total:
        logger.info("Collected %d FEL basin structures for 3D viewer", len(frames))
        return frames

    # --- Trajectory-derived frames ----------------------------------------
    if analysis_data:
        important = identify_important_timepoints(
            analysis_data, working_dir, max_points=max(5, max_total - len(frames))
        )
        if important:
            time_points = [t for t, _ in important]
            labels_map = {t: lbl for t, lbl in important}
            traj_frames = extract_multi_frame_pdb(
                hpc_parent,
                hpc_subdir=hpc_subdir,
                time_points_ns=time_points,
                labels=labels_map,
            )
            for label, pdb_text in traj_frames.items():
                if len(frames) >= max_total:
                    break
                if label not in frames:
                    frames[label] = pdb_text

    logger.info(
        "Collected %d significant structure(s) for 3D viewer: %s",
        len(frames),
        ", ".join(frames.keys()) if frames else "none",
    )
    return frames


def identify_important_timepoints(
    analysis_data: Dict,
    working_dir: str,
    max_points: int = 5,
) -> List[Tuple[float, str]]:
    """Identify scientifically important time points from analysis results.

    Reads RMSD and COM-distance data files referenced in *analysis_data*
    and picks up to *max_points* notable moments:

    * Start frame (0 ns)
    * Maximum RMSD (largest structural deviation)
    * Minimum RMSD after equilibration (most stable)
    * Maximum COM distance (farthest ligand position), if available
    * Minimum COM distance (closest ligand approach), if available
    * Final frame

    Returns a list of ``(time_ns, label)`` tuples sorted by time.
    """
    # Collect candidate (time, label) pairs; deduplicate later
    candidates: Dict[float, str] = {}
    base = Path(working_dir)
    rmsd_found = False

    # Helper: resolve possibly-absolute path relative to working_dir
    def _resolve(fpath: str) -> str:
        p = Path(fpath)
        if p.is_absolute() and p.is_file():
            return str(p)
        # Try relative to working_dir, then analysis subdir
        for base_dir in [base, base / "analysis"]:
            candidate = base_dir / p.name
            if candidate.is_file():
                return str(candidate)
        return fpath  # Return as-is (will fail gracefully)

    total_time_ns: Optional[float] = None

    # --- Parse RMSD data ------------------------------------------------
    entries = analysis_data.get("entries", []) if isinstance(analysis_data, dict) else []
    for entry in entries:
        atype = (entry.get("analysis_type") or "").upper()
        files = entry.get("files", {})

        if "RMSD" in atype and "RMSF" not in atype and not rmsd_found:
            dat_path = files.get("data") or files.get("output_file")
            if dat_path:
                ts = _read_timeseries(_resolve(dat_path))
                if ts is not None:
                    t, v = ts
                    if len(t) > 0:
                        total_time_ns = t[-1]
                        # Start
                        candidates[0.0] = "Start"
                        # Max RMSD
                        idx_max = int(np.argmax(v))
                        candidates[round(float(t[idx_max]), 1)] = f"Max RMSD ({v[idx_max]:.1f} Å)"
                        # Min RMSD after first 10% of trajectory (post-equilibration)
                        eq_start = max(1, len(t) // 10)
                        idx_min = eq_start + int(np.argmin(v[eq_start:]))
                        candidates[round(float(t[idx_min]), 1)] = f"Min RMSD ({v[idx_min]:.1f} Å)"
                        # Final frame
                        candidates[round(float(t[-1]), 1)] = "End"
                        rmsd_found = True

        # Ligand–pocket COM distance (per-simulation holo metric)
        if ("COM" in atype and "DISTANCE" in atype) or "LIGAND_POCKET" in atype:
            dat_path = (
                files.get("data")
                or files.get("csv")
                or files.get("output")
                or files.get("output_file")
            )
            if dat_path:
                ts = _read_timeseries(_resolve(dat_path), y_col_name="distance")
                if ts is not None:
                    t, v = ts
                    if len(t) > 0:
                        if total_time_ns is None:
                            total_time_ns = t[-1]
                        idx_max = int(np.argmax(v))
                        candidates[round(float(t[idx_max]), 1)] = (
                            f"Max pocket COM dist ({v[idx_max]:.1f} Å)"
                        )
                        idx_min = int(np.argmin(v))
                        candidates[round(float(t[idx_min]), 1)] = (
                            f"Min pocket COM dist ({v[idx_min]:.1f} Å)"
                        )

        # Protein–ligand contacts — pick frames with strongest/weakest contact counts
        if "CONTACT" in atype:
            dat_path = files.get("csv") or files.get("data") or files.get("output_file")
            if dat_path:
                ts = _read_timeseries(_resolve(dat_path), y_col_name="contact")
                if ts is not None:
                    t, v = ts
                    if len(t) > 0:
                        if total_time_ns is None:
                            total_time_ns = t[-1]
                        idx_max = int(np.argmax(v))
                        candidates[round(float(t[idx_max]), 1)] = (
                            f"Max contacts ({int(v[idx_max])})"
                        )
                        idx_min = int(np.argmin(v))
                        candidates[round(float(t[idx_min]), 1)] = (
                            f"Min contacts ({int(v[idx_min])})"
                        )

        # Ligand residence — first unbinding event (bound → unbound)
        if "RESIDENCE" in atype:
            dat_path = files.get("csv") or files.get("data") or files.get("output_file")
            resolved = _resolve(dat_path) if dat_path else None
            if resolved and Path(resolved).is_file():
                try:
                    with open(resolved, newline="", encoding="utf-8") as fh:
                        reader = csv.DictReader(fh)
                        prev_bound = None
                        for row in reader:
                            t_ns = float(row.get("time_ns", row.get("Time", 0)))
                            bound_raw = row.get("bound", row.get("is_bound", "1"))
                            bound = str(bound_raw).strip() in ("1", "True", "true")
                            if prev_bound is True and not bound:
                                candidates[round(t_ns, 1)] = "Ligand unbinding"
                                break
                            prev_bound = bound
                        if total_time_ns is None:
                            # last row time
                            with open(resolved, newline="", encoding="utf-8") as fh2:
                                rows = list(csv.DictReader(fh2))
                                if rows:
                                    total_time_ns = float(
                                        rows[-1].get("time_ns", rows[-1].get("Time", 0))
                                    )
                except Exception as exc:
                    logger.debug("Could not parse residence CSV %s: %s", resolved, exc)

        if ("INTER" in atype and "COM" in atype) or ("INTER" in atype and "DISTANCE" in atype):
            # Only match inter-molecular COM distance, not single-group COM coordinates
            dat_path = files.get("output") or files.get("output_file")
            if dat_path:
                ts = _read_timeseries(_resolve(dat_path))
                if ts is not None:
                    t, v = ts
                    if len(t) > 0:
                        if total_time_ns is None:
                            total_time_ns = t[-1]
                        # Max COM distance (farthest ligand position)
                        idx_max = int(np.argmax(v))
                        candidates[round(float(t[idx_max]), 1)] = f"Max COM dist ({v[idx_max]:.1f} Å)"
                        # Min COM distance (closest approach)
                        idx_min = int(np.argmin(v))
                        candidates[round(float(t[idx_min]), 1)] = f"Min COM dist ({v[idx_min]:.1f} Å)"

    # Always include start and end if trajectory time is known
    if total_time_ns is not None:
        candidates.setdefault(0.0, "Start")
        candidates.setdefault(round(total_time_ns, 1), "End")

    if not candidates:
        logger.info("No analysis data files found for smart timepoint selection")
        return []

    # Sort by time and prune to max_points
    sorted_pts = sorted(candidates.items(), key=lambda x: x[0])

    if len(sorted_pts) <= max_points:
        result = [(t, label) for t, label in sorted_pts]
    else:
        # Always keep first and last; pick most interesting middle points
        first = sorted_pts[0]
        last = sorted_pts[-1]
        middle = sorted_pts[1:-1]
        # Prefer RMSD/COM extremes over generic labels
        priority_keywords = ["Max RMSD", "Min RMSD", "Max COM", "Min COM"]
        middle_sorted = sorted(
            middle,
            key=lambda x: (0 if any(kw in x[1] for kw in priority_keywords) else 1, x[0]),
        )
        selected_middle = middle_sorted[: max_points - 2]
        result = sorted([first] + selected_middle + [last], key=lambda x: x[0])

    logger.info(
        "Identified %d important timepoints: %s",
        len(result),
        ", ".join(f"{t} ns ({lbl})" for t, lbl in result),
    )
    return result


def extract_multi_frame_pdb(
    working_dir: str,
    hpc_subdir: str = "hpc",
    time_points_ns: Optional[List[float]] = None,
    n_points: int = 3,
    labels: Optional[Dict[float, str]] = None,
) -> Dict[str, str]:
    """Extract PDB frames at multiple time points for the 3D viewer.

    If *time_points_ns* is not provided, ``n_points`` evenly-spaced
    time points are chosen automatically (including first and last frame).

    If *labels* is given (mapping ``time_ns → descriptive string``),
    those are used as dict keys instead of plain ``"<time> ns"``.

    Returns:
        Ordered dict mapping label → PDB text.  Empty dict on failure.
    """
    try:
        import MDAnalysis as mda
    except ImportError:
        logger.warning("MDAnalysis not available – cannot extract PDB frames")
        return {}

    hpc_dir = Path(working_dir) / hpc_subdir
    if not hpc_dir.is_dir():
        logger.warning("HPC directory not found: %s", hpc_dir)
        return {}

    # --- locate topology ------------------------------------------------
    topology: Optional[Path] = None
    for candidate in ("md.gro", "processed.gro", "md.tpr"):
        p = hpc_dir / candidate
        if p.exists():
            topology = p
            break
    if topology is None:
        gro_files = sorted(hpc_dir.glob("*.gro"))
        if gro_files:
            topology = gro_files[0]
    if topology is None:
        logger.warning("No topology file found in %s", hpc_dir)
        return {}

    # --- locate trajectory (optional) -----------------------------------
    # Prefer the PBC-wrapped trajectory when available (mdWrap.xtc),
    # then fall back to the raw trajectory files.
    trajectory: Optional[Path] = None
    for candidate in ("mdWrap.xtc", "md.xtc", "md.trr"):
        p = hpc_dir / candidate
        if p.exists():
            trajectory = p
            break
    if trajectory is None:
        xtc_files = sorted(hpc_dir.glob("*.xtc"))
        if xtc_files:
            trajectory = xtc_files[0]

    if not trajectory:
        # No trajectory → can only provide a single static frame
        single = extract_first_frame_pdb(working_dir, hpc_subdir)
        if single:
            txt = read_pdb_data(single)
            if txt:
                return {"0 ns": txt}
        return {}

    # --- load universe --------------------------------------------------
    try:
        u = mda.Universe(str(topology), str(trajectory))
    except Exception as exc:
        logger.error("Failed to load universe: %s", exc)
        return {}

    # Align all frames to frame 0 on backbone/Cα so that frames extracted
    # at different time points are superimposed in the 3D viewer.
    if u.trajectory.n_frames > 1:
        try:
            from MDAnalysis.analysis import align as _mda_align
            _ref = mda.Universe(str(topology), str(trajectory))
            _ref.trajectory[0]
            _align_sel = "backbone" if u.select_atoms("backbone").n_atoms > 0 else "name CA"
            if u.select_atoms(_align_sel).n_atoms > 0:
                _mda_align.AlignTraj(u, _ref, select=_align_sel, in_memory=True).run()
                logger.info("extract_multi_frame_pdb: aligned trajectory on '%s'", _align_sel)
        except Exception as _ae:
            logger.warning("extract_multi_frame_pdb: alignment skipped (%s)", _ae)

    total_time_ns = u.trajectory.totaltime / 1000.0  # ps → ns

    # --- determine requested time points --------------------------------
    if time_points_ns is None:
        if total_time_ns <= 0 or u.trajectory.n_frames < 2:
            time_points_ns = [0.0]
        else:
            step = total_time_ns / max(n_points - 1, 1)
            time_points_ns = [round(i * step, 1) for i in range(n_points)]

    # Clamp to trajectory range
    time_points_ns = sorted(set(
        min(max(t, 0.0), total_time_ns) for t in time_points_ns
    ))

    # --- build atom selection string ------------------------------------
    _BULK_IONS = "resname NA NA+ CL CL- K K+ SOD CLA"
    _WATER = "resname HOH WAT SOL TIP3 TIP4 SPC"
    sel_parts = []
    if len(u.select_atoms("protein")) > 0:
        sel_parts.append("protein")
    if len(u.select_atoms("nucleic")) > 0:
        sel_parts.append("nucleic")
    other_sel = f"not protein and not nucleic and not ({_WATER}) and not ({_BULK_IONS})"
    if len(u.select_atoms(other_sel)) > 0:
        sel_parts.append(f"({other_sel})")
    selection_str = " or ".join(sel_parts) if sel_parts else f"not ({_WATER})"
    selected = u.select_atoms(selection_str)

    reporter_dir = Path(working_dir) / "reporter"
    reporter_dir.mkdir(parents=True, exist_ok=True)

    result: Dict[str, str] = {}
    dt_ps = u.trajectory.dt if u.trajectory.dt > 0 else 1.0
    labels = labels or {}

    for t_ns in time_points_ns:
        t_ps = t_ns * 1000.0
        frame_idx = int(round(t_ps / dt_ps))
        frame_idx = min(frame_idx, u.trajectory.n_frames - 1)

        u.trajectory[frame_idx]
        actual_ns = round(u.trajectory.time / 1000.0, 1)

        # Use descriptive label if available, else plain time
        if t_ns in labels:
            label = f"{actual_ns} ns — {labels[t_ns]}"
        elif actual_ns in labels:
            label = f"{actual_ns} ns — {labels[actual_ns]}"
        else:
            label = f"{actual_ns} ns"

        fname = f"system_frame_{actual_ns:.0f}ns.pdb"
        out_path = reporter_dir / fname
        try:
            selected.write(str(out_path))
            txt = read_pdb_data(str(out_path))
            if txt:
                result[label] = txt
                logger.info("Extracted frame at %s (%d atoms) → %s",
                            label, len(selected), out_path)
        except Exception as exc:
            logger.error("Failed to write frame at %s: %s", label, exc)

    return result
