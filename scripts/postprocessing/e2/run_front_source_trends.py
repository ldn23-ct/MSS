#!/usr/bin/env python3
"""Build the supplementary E2 front-source trend and stability analysis."""

from __future__ import annotations

import argparse
import math
import os
import shutil
import sys
import tempfile
from pathlib import Path
from typing import Any

os.environ.setdefault("MPLCONFIGDIR", "/tmp/mss_matplotlib")
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from scripts.postprocessing.e2 import run as e2
from scripts.postprocessing.e2 import run_target_scatter_composition as formal
from scripts.postprocessing.e3 import run as e3


RESAMPLE_SEED = e2.DEFAULT_RESAMPLE_SEED
RESAMPLE_COUNT = e2.RESAMPLE_COUNT
DEFAULT_SUBDIRECTORY = "front_source_trends"
ST4_TABLE_NAME = "E2-ST4_P1-P6_source_region_fractions.csv"
ST5_TABLE_NAME = "E2-ST5_P1-P6_front_region_response_and_dtv.csv"
ST6_TABLE_NAME = "E2-ST6_P1-P6_E2_E3_front_weight_comparison.csv"
SF2_FIGURE_NAME = "E2-SF2_P1-P6_source_region_fraction_trends.png"
SF3_FIGURE_NAME = "E2-SF3_P1-P6_front_region_response_and_dtv.png"
TABLE_NAMES = (ST4_TABLE_NAME, ST5_TABLE_NAME, ST6_TABLE_NAME)
OUTPUT_NAMES = (*TABLE_NAMES, SF2_FIGURE_NAME, SF3_FIGURE_NAME)
CONDITIONS = formal.CONDITIONS

ST4_COLUMNS = (
    "condition", "defect_phantom", "slit", "depth_mm", "condition_role",
    "scatter_class", "region", "N_region", "N_total", "fraction",
    "fraction_ci_low", "fraction_ci_high", "fraction_n_effective",
)
ST5_COLUMNS = (
    "condition", "defect_phantom", "slit", "depth_mm", "scatter_class",
    "N_F0", "N_FD", "C_F", "C_F_ci_low", "C_F_ci_high", "C_F_n_effective",
    "D_TV_F", "D_TV_F_ci_low", "D_TV_F_ci_high", "D_TV_F_n_effective",
)
ST6_COLUMNS = (
    "condition", "defect_phantom", "slit", "depth_mm",
    "f_F0_total", "f_F0_total_ci_low", "f_F0_total_ci_high", "f_F0_total_n_effective",
    "M0_count", "M5_count", "eta_M5", "eta_M5_ci_low", "eta_M5_ci_high", "eta_M5_n_effective",
    "one_minus_eta_M5", "one_minus_eta_M5_ci_low", "one_minus_eta_M5_ci_high",
    "one_minus_eta_M5_n_effective",
)


def _require_columns(frame: pd.DataFrame, columns: tuple[str, ...], label: str) -> None:
    if tuple(frame.columns) != columns:
        raise ValueError(f"{label} schema does not match its frozen formal contract")


def _condition_rows(table: pd.DataFrame, phantom: str, slit: str) -> pd.DataFrame:
    return table[table.defect_phantom.eq(phantom) & table.slit.eq(slit)].copy()


def load_formal_tables(results_root: Path) -> tuple[dict[str, pd.DataFrame], pd.DataFrame, pd.DataFrame]:
    """Load frozen E2 formal tables and E3 M0/M5 metrics without recomputing either."""
    e2_root = results_root / "postprocessing" / "E2"
    t2_tables, t3, _ = formal.load_formal_tables(e2_root)
    e3_path = results_root / "postprocessing" / "E3" / "E3_T2_depth_method_metrics.csv"
    if not e3_path.is_file():
        raise FileNotFoundError("formal E3_T2_depth_method_metrics.csv is required")
    e3_metrics = pd.read_csv(e3_path)
    _require_columns(e3_metrics, e3.T2_COLUMNS, e3_path.name)
    if len(e3_metrics) != 36 or set(e3_metrics.method) != set(e3.METHODS):
        raise ValueError("formal E3 depth-method table does not match the six-depth M0--M5 contract")
    validate_e3_m5_metrics(e3_metrics)
    return t2_tables, t3, e3_metrics


def validate_e3_m5_metrics(metrics: pd.DataFrame) -> None:
    for condition, phantom, slit, depth in CONDITIONS:
        rows = metrics[
            metrics.phantom.eq(phantom) & metrics.slit.eq(slit) & np.isclose(metrics.target_depth_mm, depth)
        ]
        if len(rows) != 6 or set(rows.method) != set(e3.METHODS):
            raise ValueError(f"formal E3 M0--M5 rows are incomplete for {condition}")
        m0 = rows[rows.method.eq("M0")].iloc[0]
        m5 = rows[rows.method.eq("M5")].iloc[0]
        if int(m0.total_count_N) <= 0 or int(m5.total_count_N) < 0:
            raise ValueError(f"formal E3 counts are invalid for {condition}")
        eta_from_counts = float(m5.total_count_N) / float(m0.total_count_N)
        if not math.isclose(float(m5.retention_eta), eta_from_counts, rel_tol=0.0, abs_tol=1e-12):
            raise ValueError(f"formal E3 M5 retention does not match M5/M0 counts for {condition}")
        if not (0.0 <= float(m5.retention_ci_low) <= float(m5.retention_ci_high) <= 1.0):
            raise ValueError(f"formal E3 M5 retention interval is invalid for {condition}")
        if int(m5.retention_n_effective) != RESAMPLE_COUNT:
            raise ValueError(f"formal E3 M5 effective draw count is invalid for {condition}")


def build_source_region_fractions(t3: pd.DataFrame) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    for condition, phantom, slit, depth in CONDITIONS:
        source = _condition_rows(t3, phantom, slit)
        if len(source) != 18:
            raise ValueError(f"formal E2-T3 rows are incomplete for {condition}")
        for role in ("baseline", "defect"):
            for scatter_class in e2.CLASSES:
                selected = source[
                    source.condition_role.eq(role) & source.scatter_class.eq(scatter_class)
                ].set_index("region")
                if set(selected.index) != set(e2.REGIONS) or len(selected) != 3:
                    raise ValueError(f"formal E2-T3 F/T/B rows are incomplete for {condition}/{role}/{scatter_class}")
                n_total = int(selected.N_total.iloc[0])
                if not selected.N_total.eq(n_total).all() or int(selected.N_region.sum()) != n_total:
                    raise ValueError(f"formal E2-T3 count closure failed for {condition}/{role}/{scatter_class}")
                for region in e2.REGIONS:
                    item = selected.loc[region]
                    rows.append({
                        "condition": condition, "defect_phantom": phantom, "slit": slit,
                        "depth_mm": depth, "condition_role": role,
                        "scatter_class": scatter_class, "region": region,
                        "N_region": int(item.N_region), "N_total": int(item.N_total),
                        "fraction": item.fraction, "fraction_ci_low": item.fraction_ci_low,
                        "fraction_ci_high": item.fraction_ci_high,
                        "fraction_n_effective": int(item.fraction_n_effective),
                    })
    return pd.DataFrame(rows, columns=ST4_COLUMNS)


def build_front_response_and_dtv(t2_tables: dict[str, pd.DataFrame]) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    for condition, phantom, slit, depth in CONDITIONS:
        front = t2_tables[condition][t2_tables[condition].region.eq("Front")].set_index("scatter_class")
        if set(front.index) != set(e2.CLASSES) or len(front) != 3:
            raise ValueError(f"formal E2-T2 front rows are incomplete for {condition}")
        for scatter_class in e2.CLASSES:
            item = front.loc[scatter_class]
            n0, nd = int(item.N_r0), int(item.N_rD)
            expected = (nd - n0) / n0 if n0 else math.nan
            if not (pd.isna(expected) and pd.isna(item.C_r)) and not math.isclose(
                float(item.C_r), expected, rel_tol=0.0, abs_tol=1e-12
            ):
                raise ValueError(f"formal E2-T2 C_F identity failed for {condition}/{scatter_class}")
            rows.append({
                "condition": condition, "defect_phantom": phantom, "slit": slit,
                "depth_mm": depth, "scatter_class": scatter_class,
                "N_F0": n0, "N_FD": nd, "C_F": item.C_r,
                "C_F_ci_low": item.C_r_ci_low, "C_F_ci_high": item.C_r_ci_high,
                "C_F_n_effective": int(item.C_r_n_effective),
                "D_TV_F": item.D_TV_r, "D_TV_F_ci_low": item.D_TV_r_ci_low,
                "D_TV_F_ci_high": item.D_TV_r_ci_high,
                "D_TV_F_n_effective": int(item.D_TV_r_n_effective),
            })
        if int(front.loc["total", "N_r0"]) != int(front.loc["k1", "N_r0"]) + int(front.loc["ms", "N_r0"]):
            raise ValueError(f"formal E2-T2 front baseline count closure failed for {condition}")
        if int(front.loc["total", "N_rD"]) != int(front.loc["k1", "N_rD"]) + int(front.loc["ms", "N_rD"]):
            raise ValueError(f"formal E2-T2 front defect count closure failed for {condition}")
    return pd.DataFrame(rows, columns=ST5_COLUMNS)


def build_e2_e3_front_weight_comparison(fractions: pd.DataFrame, metrics: pd.DataFrame) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    for condition, phantom, slit, depth in CONDITIONS:
        e2_front = fractions[
            fractions.condition.eq(condition) & fractions.condition_role.eq("baseline")
            & fractions.scatter_class.eq("total") & fractions.region.eq("Front")
        ]
        if len(e2_front) != 1:
            raise ValueError(f"baseline total front fraction is missing for {condition}")
        m0_m5 = metrics[
            metrics.phantom.eq(phantom) & metrics.slit.eq(slit) & np.isclose(metrics.target_depth_mm, depth)
            & metrics.method.isin(("M0", "M5"))
        ].set_index("method")
        if set(m0_m5.index) != {"M0", "M5"}:
            raise ValueError(f"formal E3 M0/M5 metrics are incomplete for {condition}")
        m0, m5 = m0_m5.loc["M0"], m0_m5.loc["M5"]
        eta = float(m5.retention_eta)
        rows.append({
            "condition": condition, "defect_phantom": phantom, "slit": slit, "depth_mm": depth,
            "f_F0_total": e2_front.iloc[0].fraction,
            "f_F0_total_ci_low": e2_front.iloc[0].fraction_ci_low,
            "f_F0_total_ci_high": e2_front.iloc[0].fraction_ci_high,
            "f_F0_total_n_effective": int(e2_front.iloc[0].fraction_n_effective),
            "M0_count": int(m0.total_count_N), "M5_count": int(m5.total_count_N),
            "eta_M5": eta, "eta_M5_ci_low": m5.retention_ci_low,
            "eta_M5_ci_high": m5.retention_ci_high,
            "eta_M5_n_effective": int(m5.retention_n_effective),
            "one_minus_eta_M5": 1.0 - eta,
            "one_minus_eta_M5_ci_low": 1.0 - float(m5.retention_ci_high),
            "one_minus_eta_M5_ci_high": 1.0 - float(m5.retention_ci_low),
            "one_minus_eta_M5_n_effective": int(m5.retention_n_effective),
        })
    return pd.DataFrame(rows, columns=ST6_COLUMNS)


def _errorbar(axis: plt.Axes, x: np.ndarray, table: pd.DataFrame, column: str,
              *, label: str, color: str, marker: str, percent: bool = True) -> None:
    point = table[column].to_numpy(dtype=float)
    low = table[f"{column}_ci_low"].to_numpy(dtype=float)
    high = table[f"{column}_ci_high"].to_numpy(dtype=float)
    scale = 100.0 if percent else 1.0
    axis.errorbar(x, scale * point, yerr=np.vstack((scale * (point - low), scale * (high - point))),
                  color=color, marker=marker, linewidth=1.45, markersize=5.5,
                  capsize=3.0, label=label)


def _interval_and_points(axis: plt.Axes, x: np.ndarray, table: pd.DataFrame, column: str,
                         *, label: str, color: str, marker: str) -> None:
    """Plot raw nonlinear estimator points independently of its Poisson interval."""
    point = table[column].to_numpy(dtype=float)
    low = table[f"{column}_ci_low"].to_numpy(dtype=float)
    high = table[f"{column}_ci_high"].to_numpy(dtype=float)
    axis.vlines(x, low, high, color=color, linewidth=1.15, alpha=0.8)
    cap = 0.65
    axis.hlines(low, x - cap, x + cap, color=color, linewidth=1.15, alpha=0.8)
    axis.hlines(high, x - cap, x + cap, color=color, linewidth=1.15, alpha=0.8)
    axis.plot(x, point, color=color, marker=marker, linewidth=1.45, markersize=5.5, label=label)


def plot_source_fraction_trends(fractions: pd.DataFrame, output: Path) -> None:
    baseline = fractions[fractions.condition_role.eq("baseline")]
    depths = np.asarray([item[3] for item in CONDITIONS], dtype=float)
    fig, axes = plt.subplots(1, 2, figsize=(13.2, 5.2), sharex=True, constrained_layout=True)
    total = baseline[baseline.scatter_class.eq("total")].sort_values(["depth_mm", "region"])
    for region, marker, color in (("Front", "o", "#009E73"), ("Target", "s", "#0072B2"), ("Behind", "^", "#CC79A7")):
        data = total[total.region.eq(region)].sort_values("depth_mm")
        _errorbar(axes[0], depths, data, "fraction", label=region, color=color, marker=marker)
    axes[0].set_title("(a) Baseline total source-region fractions")
    axes[0].set_ylabel("Fraction of detected events (%)")
    axes[0].legend(fontsize=9)
    front = baseline[baseline.region.eq("Front")]
    for scatter_class, marker in zip(e2.CLASSES, ("o", "s", "^"), strict=True):
        data = front[front.scatter_class.eq(scatter_class)].sort_values("depth_mm")
        _errorbar(axes[1], depths, data, "fraction", label=scatter_class,
                  color=e2.CLASS_COLORS[scatter_class], marker=marker)
    axes[1].set_title("(b) Baseline front fraction within each scatter class")
    axes[1].legend(fontsize=9)
    for axis in axes:
        axis.set(xlabel="Matched target depth (mm)", xlim=(12.0, 93.0), ylim=(0.0, 100.0))
        axis.set_xticks(depths)
        axis.grid(alpha=0.2)
    fig.suptitle("E2 supplementary front-source fraction trends (P0 baseline)")
    e2._save_png(fig, output)


def plot_front_response_and_dtv(response: pd.DataFrame, output: Path) -> None:
    depths = response[response.scatter_class.eq("total")].depth_mm.to_numpy(dtype=float)
    fig, axes = plt.subplots(1, 2, figsize=(13.2, 5.2), sharex=True, constrained_layout=True)
    for scatter_class, marker in zip(e2.CLASSES, ("o", "s", "^"), strict=True):
        data = response[response.scatter_class.eq(scatter_class)].sort_values("depth_mm")
        _errorbar(axes[0], depths, data, "C_F", label=scatter_class,
                  color=e2.CLASS_COLORS[scatter_class], marker=marker)
        _interval_and_points(axes[1], depths, data, "D_TV_F", label=scatter_class,
                             color=e2.CLASS_COLORS[scatter_class], marker=marker)
    axes[0].axhline(0.0, color="#666666", linewidth=1.0, linestyle="--", label="zero reference")
    axes[0].set_title("(a) Front-region relative response")
    axes[0].set_ylabel(r"$C_F$ (%)")
    axes[0].legend(fontsize=9)
    axes[1].set_title("(b) Front-region $D_{TV}$")
    axes[1].set_ylabel(r"$D_{TV,F}$")
    axes[1].legend(fontsize=9)
    for axis in axes:
        axis.set(xlabel="Matched target depth (mm)", xlim=(12.0, 93.0))
        axis.set_xticks(depths)
        axis.grid(alpha=0.2)
    fig.suptitle("E2 supplementary front-region response and distribution distance")
    e2._save_png(fig, output)


def validate_outputs(output_dir: Path) -> None:
    entries = list(output_dir.iterdir())
    actual = {path.name for path in entries if path.is_file()}
    if actual != set(OUTPUT_NAMES) or any(path.is_dir() for path in entries):
        raise AssertionError(f"supplementary E2 output mismatch: expected {sorted(OUTPUT_NAMES)}, got {sorted(actual)}")
    st4 = pd.read_csv(output_dir / ST4_TABLE_NAME)
    st5 = pd.read_csv(output_dir / ST5_TABLE_NAME)
    st6 = pd.read_csv(output_dir / ST6_TABLE_NAME)
    expected_conditions = tuple(item[0] for item in CONDITIONS)
    for table, columns, count, name in ((st4, ST4_COLUMNS, 108, ST4_TABLE_NAME), (st5, ST5_COLUMNS, 18, ST5_TABLE_NAME), (st6, ST6_COLUMNS, 6, ST6_TABLE_NAME)):
        if tuple(table.columns) != columns or len(table) != count:
            raise AssertionError(f"{name} schema or row contract failed")
        if set(table.condition) != set(expected_conditions):
            raise AssertionError(f"{name} condition contract failed")
    for _, group in st4.groupby(["condition", "condition_role", "scatter_class"]):
        if len(group) != 3 or int(group.N_region.sum()) != int(group.N_total.iloc[0]) or not np.isclose(group.fraction.sum(), 1.0):
            raise AssertionError("supplementary E2 F/T/B closure failed")
    for _, group in st5.groupby("condition"):
        indexed = group.set_index("scatter_class")
        for column in ("N_F0", "N_FD"):
            if int(indexed.loc["total", column]) != int(indexed.loc["k1", column]) + int(indexed.loc["ms", column]):
                raise AssertionError(f"supplementary E2 front count closure failed for {column}")
    if not np.allclose(st6.M5_count / st6.M0_count, st6.eta_M5, rtol=0.0, atol=1e-12):
        raise AssertionError("E3 M5 count-retention identity failed")
    if not np.allclose(st6.one_minus_eta_M5, 1.0 - st6.eta_M5, rtol=0.0, atol=1e-12):
        raise AssertionError("E3 front-weight transform failed")
    if not np.allclose(st6.one_minus_eta_M5_ci_low, 1.0 - st6.eta_M5_ci_high, rtol=0.0, atol=1e-12) or not np.allclose(st6.one_minus_eta_M5_ci_high, 1.0 - st6.eta_M5_ci_low, rtol=0.0, atol=1e-12):
        raise AssertionError("E3 front-weight interval endpoint transform failed")
    for figure in (SF2_FIGURE_NAME, SF3_FIGURE_NAME):
        if (output_dir / figure).read_bytes()[:8] != b"\x89PNG\r\n\x1a\n":
            raise AssertionError(f"{figure} is not a PNG")


def write_outputs(fractions: pd.DataFrame, response: pd.DataFrame, comparison: pd.DataFrame, output_dir: Path) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    fractions.to_csv(output_dir / ST4_TABLE_NAME, index=False)
    response.to_csv(output_dir / ST5_TABLE_NAME, index=False)
    comparison.to_csv(output_dir / ST6_TABLE_NAME, index=False)
    plot_source_fraction_trends(fractions, output_dir / SF2_FIGURE_NAME)
    plot_front_response_and_dtv(response, output_dir / SF3_FIGURE_NAME)
    validate_outputs(output_dir)


def run_analysis(results_root: Path, output_dir: Path) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    t2_tables, t3, e3_metrics = load_formal_tables(results_root)
    fractions = build_source_region_fractions(t3)
    response = build_front_response_and_dtv(t2_tables)
    comparison = build_e2_e3_front_weight_comparison(fractions, e3_metrics)
    write_outputs(fractions, response, comparison, output_dir)
    return fractions, response, comparison


def publish(staging: Path, output_dir: Path, overwrite: bool) -> None:
    if output_dir.exists():
        if not overwrite:
            raise FileExistsError(f"supplementary E2 output exists; pass --overwrite: {output_dir}")
        backup = output_dir.parent / f".{output_dir.name}.backup"
        if backup.exists():
            raise FileExistsError(f"stale supplementary E2 backup blocks overwrite: {backup}")
        output_dir.replace(backup)
        try:
            staging.replace(output_dir)
        except Exception:
            if output_dir.exists():
                shutil.rmtree(output_dir)
            backup.replace(output_dir)
            raise
        shutil.rmtree(backup)
    else:
        staging.replace(output_dir)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--results-root", type=Path, default=Path("results/articlev3_merged"))
    parser.add_argument("--output-dir", type=Path)
    parser.add_argument("--overwrite", action="store_true")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    results_root = args.results_root.resolve()
    e2_root = (results_root / "postprocessing" / "E2").resolve()
    supplementary_root = (e2_root / e2.SUPPLEMENTARY_DIR_NAME).resolve()
    output_dir = args.output_dir.resolve() if args.output_dir else supplementary_root / DEFAULT_SUBDIRECTORY
    protected = {results_root, (results_root / "events").resolve(), e2_root,
                 (e2_root / "figures").resolve(), (e2_root / "tables").resolve(), supplementary_root}
    if output_dir in protected or output_dir.is_relative_to((results_root / "events").resolve()) or (output_dir.is_relative_to(e2_root) and not output_dir.is_relative_to(supplementary_root)):
        raise ValueError("supplementary output directory must not replace formal E2 data or outputs")
    output_dir.parent.mkdir(parents=True, exist_ok=True)
    staging = Path(tempfile.mkdtemp(prefix=f".{output_dir.name}.staging-", dir=output_dir.parent))
    try:
        fractions, response, comparison = run_analysis(results_root, staging)
        publish(staging, output_dir, args.overwrite)
    except Exception:
        shutil.rmtree(staging, ignore_errors=True)
        raise
    print(f"supplementary E2 output: {output_dir}")
    print(f"formal extraction: {ST4_TABLE_NAME}, {ST5_TABLE_NAME}; E3 transform: {ST6_TABLE_NAME}")
    print(f"draws={RESAMPLE_COUNT}, seed={RESAMPLE_SEED}; F/T/B closure: pass; M5 count/retention: pass")
    print(f"files: {len(TABLE_NAMES)} CSV + 2 PNG")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as error:
        print(f"front-source trends analysis error: {error}", file=sys.stderr)
        raise SystemExit(1) from error
