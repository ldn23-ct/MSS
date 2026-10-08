#!/usr/bin/env python3
"""Rebuild the Article section 3.2 tables and figures from E2 raw events."""

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
import yaml
from matplotlib.patches import Patch

from scripts.data_processing.common import SLIT_PROFILE
from scripts.postprocessing.e2 import run as e2


CONDITIONS = tuple(
    (f"P{index}-S{index}", f"P{index}", f"S{index}", float(depth))
    for index, depth in enumerate((15, 30, 45, 60, 75, 90), 1)
)
DEFAULT_SUBDIRECTORY = "section_3_2"
DEPTH_BIN_WIDTH_MM = e2.DEFAULT_DEPTH_BIN_WIDTH_MM
TABLE6_NAME = "table6_region_contribution.csv"
DTV_NAME = "dtv_nonT_checks.csv"
COMPOSITION_NAME = "source_composition_total.csv"
MS_COMPOSITION_FIGURE_NAME = "fig_source_composition_ms.png"
FIG5_DATA_NAME = "fig5_first_scatter_depth_bins.csv"
VALIDATION_NAME = "validation_checks.csv"
COMPOSITION_FIGURE_NAME = "fig_source_composition_total.png"
MANIFEST_NAME = "analysis_manifest.yaml"
ACCEPTANCE_NAME = "acceptance_summary.yaml"
SUMMARY_NAME = "analysis_3_2_results.md"

FIG5_NAMES = {
    scatter_class: f"fig5_first_scatter_depth_{scatter_class}.png"
    for scatter_class in e2.CLASSES
}
OUTPUT_NAMES = (
    TABLE6_NAME,
    DTV_NAME,
    COMPOSITION_NAME,
    FIG5_DATA_NAME,
    VALIDATION_NAME,
    *FIG5_NAMES.values(),
    COMPOSITION_FIGURE_NAME,
    MANIFEST_NAME,
    ACCEPTANCE_NAME,
)

TABLE6_COLUMNS = (
    "condition",
    "depth_mm",
    "scatter_class",
    "N_T0",
    "N_TD",
    "C_T",
    "w_T",
    "C",
    "Gamma_T",
    "Gamma_nonT",
)
DTV_COLUMNS = (
    "condition",
    "depth_mm",
    "scatter_class",
    "N_F0",
    "N_FD",
    "N_B0",
    "N_BD",
    "N_nonT0",
    "N_nonTD",
    "D_TV_F",
    "D_TV_B",
    "D_TV_nonT",
)
COMPOSITION_COLUMNS = (
    "condition",
    "depth_mm",
    "N0_total",
    "N_F0",
    "N_T0",
    "N_B0",
    "w_F",
    "w_T",
    "w_B",
)
MS_COMPOSITION_COLUMNS = (
    "condition",
    "depth_mm",
    "N_ms",
    "N_F_ms",
    "N_T_ms",
    "N_B_ms",
    "w_F",
    "w_T",
    "w_B",
)
FIG5_DATA_COLUMNS = (
    "condition",
    "depth_mm",
    "scatter_class",
    "condition_role",
    "bin_left_mm",
    "bin_right_mm",
    "count",
)
VALIDATION_COLUMNS = (
    "condition",
    "depth_mm",
    "scatter_class",
    "N_F0",
    "N_T0",
    "N_B0",
    "N_FD",
    "N_TD",
    "N_BD",
    "N0",
    "ND",
    "region_sum_error_0",
    "region_sum_error_D",
    "Gamma_T_weighted",
    "Gamma_T_direct",
    "Gamma_T_identity_error",
    "Gamma_nonT_from_difference",
    "Gamma_nonT_direct",
    "Gamma_nonT_identity_error",
    "C_recomputed_from_regions",
    "C_decomposition_error",
    "C_formal",
    "C_formal_error",
    "C_rounded_percent",
    "C_table5_percent",
    "C_table5_rounding_match",
    "w_sum",
    "w_sum_error",
    "baseline_class_closure_error",
    "defect_class_closure_error",
    "abs_Gamma_T_gt_abs_Gamma_nonT",
    "nonT_direction",
)

TABLE5_PERCENT = {
    "total": (-55.5, -43.0, -26.1, -19.3, -15.7, -12.7),
    "k1": (-75.8, -72.4, -51.8, -51.0, -46.0, -48.2),
    "ms": (-28.4, -20.2, -12.7, -8.3, -8.8, -7.3),
}
REGION_SHORT = {"Front": "F", "Target": "T", "Behind": "B"}
REGION_COLORS = {"F": "#009E73", "T": "#0072B2", "B": "#CC79A7"}


def _require_columns(frame: pd.DataFrame, columns: tuple[str, ...], label: str) -> None:
    if tuple(frame.columns) != columns:
        raise ValueError(f"{label} schema does not match its fixed contract")


def _formal_t1(results_root: Path) -> pd.DataFrame:
    path = results_root / "postprocessing" / "E2" / "tables" / e2.ZERO_POSE_T1_TABLE_NAME
    if not path.is_file():
        raise FileNotFoundError(f"formal grid-zero E2-T1 is required for validation: {path}")
    table = pd.read_csv(path)
    _require_columns(table, e2.T1_COLUMNS, path.name)
    if (
        len(table) != 18
        or set(table.scatter_class) != set(e2.CLASSES)
        or table.groupby(["defect_phantom", "slit", "scatter_class"]).ngroups != 18
    ):
        raise ValueError("formal grid-zero E2-T1 does not contain the expected 18 rows")
    return table


def load_raw_condition_frames(
    results_root: Path, audit_dir: Path
) -> tuple[dict[str, dict[str, pd.DataFrame]], list[dict[str, str]]]:
    """Load the twelve selected zero-pose valid-event files through the E2 selector."""
    audit, inventory = e2.validate_audit(audit_dir)
    ctx = e2.AnalysisContext(
        results_root,
        audit_dir,
        results_root / "postprocessing" / "E2",
        inventory,
        audit,
    )
    frames: dict[str, dict[str, pd.DataFrame]] = {}
    sources: list[dict[str, str]] = []
    for condition, phantom, slit, _ in CONDITIONS:
        case = e2.E2Case("P0", phantom, slit, "total")
        frames[condition] = e2._load_case_frames(ctx, case, "grid-zero")
        profile = SLIT_PROFILE[slit]
        for role, source_phantom in (("baseline", "P0"), ("defect", phantom)):
            row = ctx.summary_row(source_phantom, profile, "grid-zero")
            sources.append(
                {
                    "condition": condition,
                    "condition_role": role,
                    "phantom": source_phantom,
                    "profile": profile,
                    "slit": slit,
                    "valid_file": str(row.valid_file),
                }
            )
    return frames, sources


def compute_ms_source_composition(
    condition_frames: dict[str, dict[str, pd.DataFrame]],
) -> pd.DataFrame:
    """Compute F/T/B weights among baseline multiple-scatter detected events."""
    rows: list[dict[str, Any]] = []
    for condition, phantom, slit, depth in CONDITIONS:
        if condition not in condition_frames:
            raise ValueError(f"raw condition frames are missing: {condition}")
        frames = condition_frames[condition]
        if set(frames) != {"baseline", "defect"}:
            raise ValueError(f"{condition} must contain baseline and defect frames")

        baseline = frames["baseline"]
        ms_mask = e2.class_mask(baseline, "ms")
        ms_events = baseline.loc[ms_mask]
        scatter_order = e2.scatter_counts(ms_events).to_numpy(dtype=int)
        if len(ms_events) == 0 or (scatter_order < 2).any():
            raise ValueError(f"no valid n >= 2 baseline ms events for {condition}")
        depths = ms_events.first_scatter_z.to_numpy(dtype=float)
        target_range = e2.case_target_range(e2.E2Case("P0", phantom, slit, "ms"))
        counts = {
            region: int(e2.region_mask(depths, region, target_range).sum())
            for region in e2.REGIONS
        }
        n_ms = int(len(ms_events))
        if sum(counts.values()) != n_ms:
            raise AssertionError(f"F/T/B partition loses ms events: {condition}")
        weights = {
            "F": counts["Front"] / n_ms,
            "T": counts["Target"] / n_ms,
            "B": counts["Behind"] / n_ms,
        }
        if not np.isclose(sum(weights.values()), 1.0, rtol=0.0, atol=1e-12):
            raise AssertionError(f"ms source-composition weights do not close: {condition}")
        rows.append(
            {
                "condition": condition,
                "depth_mm": depth,
                "N_ms": n_ms,
                "N_F_ms": counts["Front"],
                "N_T_ms": counts["Target"],
                "N_B_ms": counts["Behind"],
                "w_F": weights["F"],
                "w_T": weights["T"],
                "w_B": weights["B"],
            }
        )
    return pd.DataFrame(rows, columns=MS_COMPOSITION_COLUMNS)


def _histogram(values: np.ndarray, edges: np.ndarray, label: str) -> np.ndarray:
    counts, _ = np.histogram(values, bins=edges)
    if int(counts.sum()) != len(values):
        raise AssertionError(f"depth histogram loses events: {label}")
    return counts


def _dtv(baseline: np.ndarray, defect: np.ndarray) -> float:
    baseline = np.asarray(baseline, dtype=float)
    defect = np.asarray(defect, dtype=float)
    if baseline.shape != defect.shape:
        raise ValueError("DTV histograms must have matching shapes")
    if (baseline < 0).any() or (defect < 0).any():
        raise ValueError("DTV histograms must be non-negative")
    n0, nd = baseline.sum(), defect.sum()
    if n0 <= 0 or nd <= 0:
        return math.nan
    return float(0.5 * np.abs(defect / nd - baseline / n0).sum())


def _formal_row(formal_t1: pd.DataFrame, phantom: str, slit: str, scatter_class: str) -> pd.Series:
    rows = formal_t1[
        formal_t1.defect_phantom.eq(phantom)
        & formal_t1.slit.eq(slit)
        & formal_t1.scatter_class.eq(scatter_class)
    ]
    if len(rows) != 1:
        raise ValueError(f"formal E2-T1 row is missing for {phantom}/{slit}/{scatter_class}")
    return rows.iloc[0]


def compute_tables(
    condition_frames: dict[str, dict[str, pd.DataFrame]],
    formal_t1: pd.DataFrame,
) -> dict[str, pd.DataFrame]:
    """Compute all section 3.2 point estimates directly from selected event rows."""
    _require_columns(formal_t1, e2.T1_COLUMNS, "formal E2-T1")
    table6_rows: list[dict[str, Any]] = []
    dtv_rows: list[dict[str, Any]] = []
    composition_rows: list[dict[str, Any]] = []
    fig5_rows: list[dict[str, Any]] = []
    validation_rows: list[dict[str, Any]] = []
    global_edges = e2.depth_edges(DEPTH_BIN_WIDTH_MM)

    for condition_index, (condition, phantom, slit, depth) in enumerate(CONDITIONS):
        if condition not in condition_frames:
            raise ValueError(f"raw condition frames are missing: {condition}")
        frames = condition_frames[condition]
        if set(frames) != {"baseline", "defect"}:
            raise ValueError(f"{condition} must contain baseline and defect frames")
        case = e2.E2Case("P0", phantom, slit, "total")
        target_range = e2.case_target_range(case)
        class_records: dict[str, dict[str, Any]] = {}

        for scatter_class in e2.CLASSES:
            depths_by_role: dict[str, np.ndarray] = {}
            global_bins: dict[str, np.ndarray] = {}
            region_counts: dict[str, dict[str, int]] = {}
            region_bins: dict[str, dict[str, np.ndarray]] = {}
            for role in ("baseline", "defect"):
                frame = frames[role]
                depths = frame.loc[
                    e2.class_mask(frame, scatter_class), "first_scatter_z"
                ].to_numpy(dtype=float)
                depths_by_role[role] = depths
                global_bins[role] = _histogram(
                    depths, global_edges, f"{condition}/{role}/{scatter_class}/global"
                )
                region_counts[role] = {}
                region_bins[role] = {}
                for region in e2.REGIONS:
                    selected = depths[e2.region_mask(depths, region, target_range)]
                    bins = _histogram(
                        selected,
                        e2.region_edges(region, target_range, DEPTH_BIN_WIDTH_MM),
                        f"{condition}/{role}/{scatter_class}/{region}",
                    )
                    region_counts[role][region] = int(len(selected))
                    region_bins[role][region] = bins
                if sum(region_counts[role].values()) != len(depths):
                    raise AssertionError(f"F/T/B partition loses events: {condition}/{role}/{scatter_class}")
                for left, right, count in zip(
                    global_edges[:-1], global_edges[1:], global_bins[role], strict=True
                ):
                    fig5_rows.append(
                        {
                            "condition": condition,
                            "depth_mm": depth,
                            "scatter_class": scatter_class,
                            "condition_role": role,
                            "bin_left_mm": float(left),
                            "bin_right_mm": float(right),
                            "count": int(count),
                        }
                    )

            n0 = len(depths_by_role["baseline"])
            nd = len(depths_by_role["defect"])
            if n0 <= 0:
                raise ValueError(f"baseline total is zero: {condition}/{scatter_class}")
            n_t0 = region_counts["baseline"]["Target"]
            n_td = region_counts["defect"]["Target"]
            if n_t0 <= 0:
                raise ValueError(f"baseline T count is zero: {condition}/{scatter_class}")
            c_t = (n_td - n_t0) / n_t0
            w_t = n_t0 / n0
            c_value = (nd - n0) / n0
            gamma_t_weighted = w_t * c_t
            gamma_t_direct = (n_td - n_t0) / n0
            gamma_non_t = c_value - gamma_t_direct
            gamma_non_t_direct = (
                (region_counts["defect"]["Front"] - region_counts["baseline"]["Front"])
                + (region_counts["defect"]["Behind"] - region_counts["baseline"]["Behind"])
            ) / n0
            weights = {
                region: region_counts["baseline"][region] / n0 for region in e2.REGIONS
            }
            formal = _formal_row(formal_t1, phantom, slit, scatter_class)
            published_percent = TABLE5_PERCENT[scatter_class][condition_index]
            rounded_percent = round(100.0 * c_value, 1)
            non_t_0 = np.concatenate(
                (region_bins["baseline"]["Front"], region_bins["baseline"]["Behind"])
            )
            non_t_d = np.concatenate(
                (region_bins["defect"]["Front"], region_bins["defect"]["Behind"])
            )

            table6_rows.append(
                {
                    "condition": condition,
                    "depth_mm": depth,
                    "scatter_class": scatter_class,
                    "N_T0": n_t0,
                    "N_TD": n_td,
                    "C_T": c_t,
                    "w_T": w_t,
                    "C": c_value,
                    "Gamma_T": gamma_t_direct,
                    "Gamma_nonT": gamma_non_t,
                }
            )
            dtv_rows.append(
                {
                    "condition": condition,
                    "depth_mm": depth,
                    "scatter_class": scatter_class,
                    "N_F0": region_counts["baseline"]["Front"],
                    "N_FD": region_counts["defect"]["Front"],
                    "N_B0": region_counts["baseline"]["Behind"],
                    "N_BD": region_counts["defect"]["Behind"],
                    "N_nonT0": int(non_t_0.sum()),
                    "N_nonTD": int(non_t_d.sum()),
                    "D_TV_F": _dtv(
                        region_bins["baseline"]["Front"], region_bins["defect"]["Front"]
                    ),
                    "D_TV_B": _dtv(
                        region_bins["baseline"]["Behind"], region_bins["defect"]["Behind"]
                    ),
                    "D_TV_nonT": _dtv(non_t_0, non_t_d),
                }
            )
            class_records[scatter_class] = {
                "n0": n0,
                "nd": nd,
                "global_bins": global_bins,
                "region_counts": region_counts,
            }
            validation_rows.append(
                {
                    "condition": condition,
                    "depth_mm": depth,
                    "scatter_class": scatter_class,
                    "N_F0": region_counts["baseline"]["Front"],
                    "N_T0": n_t0,
                    "N_B0": region_counts["baseline"]["Behind"],
                    "N_FD": region_counts["defect"]["Front"],
                    "N_TD": n_td,
                    "N_BD": region_counts["defect"]["Behind"],
                    "N0": n0,
                    "ND": nd,
                    "region_sum_error_0": sum(region_counts["baseline"].values()) - n0,
                    "region_sum_error_D": sum(region_counts["defect"].values()) - nd,
                    "Gamma_T_weighted": gamma_t_weighted,
                    "Gamma_T_direct": gamma_t_direct,
                    "Gamma_T_identity_error": gamma_t_weighted - gamma_t_direct,
                    "Gamma_nonT_from_difference": gamma_non_t,
                    "Gamma_nonT_direct": gamma_non_t_direct,
                    "Gamma_nonT_identity_error": gamma_non_t - gamma_non_t_direct,
                    "C_recomputed_from_regions": gamma_t_direct + gamma_non_t_direct,
                    "C_decomposition_error": c_value - gamma_t_direct - gamma_non_t_direct,
                    "C_formal": float(formal.C),
                    "C_formal_error": c_value - float(formal.C),
                    "C_rounded_percent": rounded_percent,
                    "C_table5_percent": published_percent,
                    "C_table5_rounding_match": math.isclose(
                        rounded_percent, published_percent, rel_tol=0.0, abs_tol=1e-12
                    ),
                    "w_sum": sum(weights.values()),
                    "w_sum_error": sum(weights.values()) - 1.0,
                    "baseline_class_closure_error": 0,
                    "defect_class_closure_error": 0,
                    "abs_Gamma_T_gt_abs_Gamma_nonT": abs(gamma_t_direct) > abs(gamma_non_t),
                    "nonT_direction": (
                        "opposes_T" if gamma_t_direct * gamma_non_t < 0 else "same_as_T"
                    ),
                }
            )

        for role, column in (("baseline", "baseline_class_closure_error"), ("defect", "defect_class_closure_error")):
            closure = (
                class_records["total"]["n0" if role == "baseline" else "nd"]
                - class_records["k1"]["n0" if role == "baseline" else "nd"]
                - class_records["ms"]["n0" if role == "baseline" else "nd"]
            )
            for row in validation_rows[-len(e2.CLASSES) :]:
                row[column] = int(closure)
            total_bins = class_records["total"]["global_bins"][role]
            component_bins = (
                class_records["k1"]["global_bins"][role]
                + class_records["ms"]["global_bins"][role]
            )
            if not np.array_equal(total_bins, component_bins):
                raise AssertionError(f"bin-wise total != k1 + ms: {condition}/{role}")

        total_regions = class_records["total"]["region_counts"]["baseline"]
        n_total = class_records["total"]["n0"]
        composition_rows.append(
            {
                "condition": condition,
                "depth_mm": depth,
                "N0_total": n_total,
                "N_F0": total_regions["Front"],
                "N_T0": total_regions["Target"],
                "N_B0": total_regions["Behind"],
                "w_F": total_regions["Front"] / n_total,
                "w_T": total_regions["Target"] / n_total,
                "w_B": total_regions["Behind"] / n_total,
            }
        )

    tables = {
        "table6": pd.DataFrame(table6_rows, columns=TABLE6_COLUMNS),
        "dtv": pd.DataFrame(dtv_rows, columns=DTV_COLUMNS),
        "composition": pd.DataFrame(composition_rows, columns=COMPOSITION_COLUMNS),
        "fig5": pd.DataFrame(fig5_rows, columns=FIG5_DATA_COLUMNS),
        "validation": pd.DataFrame(validation_rows, columns=VALIDATION_COLUMNS),
    }
    return tables


def plot_fig5(fig5: pd.DataFrame, scatter_class: str, output: Path) -> None:
    if scatter_class not in e2.CLASSES:
        raise ValueError(f"unknown scatter class: {scatter_class}")
    fig, axes = plt.subplots(2, 3, figsize=(16.0, 9.2), sharex=True)
    for axis, (condition, _, _, depth) in zip(axes.flat, CONDITIONS, strict=True):
        data = fig5[
            fig5.condition.eq(condition) & fig5.scatter_class.eq(scatter_class)
        ]
        edges: np.ndarray | None = None
        for role, color, linestyle, label in (
            ("baseline", e2.BASELINE_COLOR, "-", "Uniform phantom"),
            ("defect", e2.DEFECT_COLOR, "--", "Defect phantom"),
        ):
            selected = data[data.condition_role.eq(role)].sort_values("bin_left_mm")
            counts = selected["count"].to_numpy(dtype=float)
            role_edges = np.r_[
                selected.bin_left_mm.to_numpy(dtype=float),
                float(selected.bin_right_mm.iloc[-1]),
            ]
            edges = role_edges if edges is None else edges
            if not np.array_equal(edges, role_edges):
                raise AssertionError(f"Figure 5 edges differ by role: {condition}/{scatter_class}")
            axis.stairs(
                counts,
                role_edges,
                color=color,
                linestyle=linestyle,
                linewidth=1.45,
                label=label,
            )
        target = (depth - 5.0, depth + 5.0)
        axis.axvspan(*target, color="#9E9E9E", alpha=0.20, zorder=0)
        maximum = float(data["count"].max())
        axis.set(
            xlim=e2.DEPTH_RANGE_MM,
            ylim=(0.0, maximum * 1.08 if maximum > 0 else 1.0),
            title=f"{condition} ({depth:g} mm)",
        )
        axis.grid(axis="y", alpha=0.16)
    for axis in axes[:, 0]:
        axis.set_ylabel("Raw detected counts")
    for axis in axes[1, :]:
        axis.set_xlabel("First-scatter depth z (mm)")
    handles, labels = axes[0, 0].get_legend_handles_labels()
    handles.append(Patch(facecolor="#9E9E9E", alpha=0.20, label="Target region T"))
    labels.append("Target region T")
    fig.subplots_adjust(left=0.065, right=0.985, bottom=0.085, top=0.855, wspace=0.23, hspace=0.27)
    fig.legend(
        handles,
        labels,
        loc="upper center",
        bbox_to_anchor=(0.5, 0.935),
        ncol=3,
        frameon=False,
    )
    fig.suptitle(f"First-scatter depth distributions — {scatter_class}", y=0.985)
    e2._save_png(fig, output)


def plot_source_composition(
    composition: pd.DataFrame,
    output: Path,
    *,
    scatter_class: str = "total",
) -> None:
    if scatter_class not in ("total", "ms"):
        raise ValueError(f"unsupported source-composition class: {scatter_class}")
    ordered = composition.set_index("condition").loc[[item[0] for item in CONDITIONS]].reset_index()
    weights = ordered[["w_F", "w_T", "w_B"]].to_numpy(dtype=float)
    if not np.allclose(weights.sum(axis=1), 1.0, rtol=0.0, atol=1e-12):
        raise AssertionError("source-composition weights do not close to one")
    x = np.arange(len(ordered), dtype=float)
    bottom = np.zeros(len(ordered), dtype=float)
    fig, axis = plt.subplots(figsize=(9.5, 5.8), constrained_layout=True)
    for region in ("F", "T", "B"):
        values = 100.0 * ordered[f"w_{region}"].to_numpy(dtype=float)
        axis.bar(
            x,
            values,
            bottom=bottom,
            width=0.68,
            color=REGION_COLORS[region],
            edgecolor="white",
            linewidth=0.8,
            label=region,
        )
        bottom += values
    labels = [f"{condition}\n{depth:g} mm" for condition, _, _, depth in CONDITIONS]
    axis.set(
        xticks=x,
        xticklabels=labels,
        ylim=(0.0, 100.0),
        ylabel=f"Fraction of baseline {scatter_class} events (%)",
        xlabel="Matched condition and target-center depth",
        title=f"Baseline {scatter_class} first-scatter source composition",
    )
    axis.grid(axis="y", alpha=0.18)
    axis.legend(
        title="Source region",
        ncol=1,
        loc="center left",
        bbox_to_anchor=(1.01, 0.5),
        frameon=False,
    )
    e2._save_png(fig, output)


def _max_abs(values: pd.Series) -> float:
    array = values.to_numpy(dtype=float)
    return float(np.nanmax(np.abs(array)))


def validate_tables(tables: dict[str, pd.DataFrame]) -> dict[str, Any]:
    table6 = tables["table6"]
    dtv = tables["dtv"]
    composition = tables["composition"]
    fig5 = tables["fig5"]
    validation = tables["validation"]
    schemas = bool(
        tuple(table6.columns) == TABLE6_COLUMNS
        and tuple(dtv.columns) == DTV_COLUMNS
        and tuple(composition.columns) == COMPOSITION_COLUMNS
        and tuple(fig5.columns) == FIG5_DATA_COLUMNS
        and tuple(validation.columns) == VALIDATION_COLUMNS
    )
    row_counts = bool(
        len(table6) == 18
        and len(dtv) == 18
        and len(composition) == 6
        and len(fig5) == 6 * 3 * 2 * (len(e2.depth_edges(DEPTH_BIN_WIDTH_MM)) - 1)
        and len(validation) == 18
    )
    dtv_values = dtv[["D_TV_F", "D_TV_B", "D_TV_nonT"]].to_numpy(dtype=float)
    dtv_valid = bool(np.all(np.isnan(dtv_values) | ((dtv_values >= 0.0) & (dtv_values <= 1.0))))
    checks = {
        "schemas": schemas,
        "row_counts": row_counts,
        "no_contribution_rate_column": not any("Gamma_T_over_C" in column for column in table6.columns),
        "region_count_closure": bool(
            validation.region_sum_error_0.eq(0).all()
            and validation.region_sum_error_D.eq(0).all()
        ),
        "class_count_closure": bool(
            validation.baseline_class_closure_error.eq(0).all()
            and validation.defect_class_closure_error.eq(0).all()
        ),
        "gamma_T_identity": _max_abs(validation.Gamma_T_identity_error) <= 1e-12,
        "gamma_nonT_identity": _max_abs(validation.Gamma_nonT_identity_error) <= 1e-12,
        "response_decomposition": _max_abs(validation.C_decomposition_error) <= 1e-12,
        "formal_table5_source_match": _max_abs(validation.C_formal_error) <= 1e-12,
        "published_table5_rounding_match": bool(validation.C_table5_rounding_match.all()),
        "source_weight_closure": _max_abs(validation.w_sum_error) <= 1e-12,
        "dtv_range_or_na": dtv_valid,
        "all_target_terms_larger_than_nonT": bool(
            validation.abs_Gamma_T_gt_abs_Gamma_nonT.all()
        ),
    }
    result = {
        "overall_status": "pass" if all(checks.values()) else "fail",
        "checks": {
            name: {"actual": passed, "expected": True, "pass": passed}
            for name, passed in checks.items()
        },
        "maximum_absolute_errors": {
            "Gamma_T_identity": _max_abs(validation.Gamma_T_identity_error),
            "Gamma_nonT_identity": _max_abs(validation.Gamma_nonT_identity_error),
            "C_decomposition": _max_abs(validation.C_decomposition_error),
            "formal_C_match": _max_abs(validation.C_formal_error),
            "source_weight_closure": _max_abs(validation.w_sum_error),
        },
    }
    if result["overall_status"] != "pass":
        failed = [name for name, item in result["checks"].items() if not item["pass"]]
        raise AssertionError("section 3.2 acceptance failed: " + ", ".join(failed))
    return result


def _pct(value: float, digits: int = 4) -> str:
    return f"{100.0 * float(value):.{digits}f}%"


def _num_or_na(value: float, digits: int = 6) -> str:
    return "NA" if pd.isna(value) else f"{float(value):.{digits}f}"


def build_summary_markdown(tables: dict[str, pd.DataFrame], acceptance: dict[str, Any]) -> str:
    table6 = tables["table6"]
    dtv = tables["dtv"]
    composition = tables["composition"]
    validation = tables["validation"]
    lines = [
        "# 第 3.2 节原始 Monte Carlo 数据重分析",
        "",
        "本文件由 `scripts.postprocessing.e2.run_section_3_2` 从 matched-grid `(0,0)` 的 `events/valid` 原始事件自动生成。所有指标均为观测点估计；未使用 Poisson 重采样、置信区间、显著性检验或旧图读数。",
        "",
        "## 定义与计算口径",
        "",
        r"- $C_T=(N_{T,D}-N_{T,0})/N_{T,0}$。",
        r"- $w_T=N_{T,0}/N_0$。",
        r"- $C=(N_D-N_0)/N_0$。",
        r"- $\Gamma_T=w_TC_T=(N_{T,D}-N_{T,0})/N_0$。",
        r"- $\Gamma_{\mathrm{nonT}}=C-\Gamma_T=[(N_{F,D}-N_{F,0})+(N_{B,D}-N_{B,0})]/N_0$。",
        r"- F、T、B 分别为 $z_1<z_c-5$、$z_c-5\le z_1<z_c+5$、$z_1\ge z_c+5$ mm。",
        "- DTV 使用 2 mm、按区域真实边界锚定的深度 bin。`nonT` 将保留深度身份的 F 与 B bin 拼接后联合归一化，不跨 T 区平滑。",
        "",
        "## 新表 6：T 区对整体相对计数变化的贡献",
        "",
        "CSV 中保存全精度无量纲值；下表将相对量显示为百分比，`Gamma` 为相对于 baseline 总计数的百分点贡献。",
    ]
    for panel, scatter_class in zip(("A", "B", "C"), e2.CLASSES, strict=True):
        lines.extend(
            [
                "",
                f"### Panel {panel} — `{scatter_class}`",
                "",
                "| 条件 | N_T,0→N_T,D | C_T | w_T | C | Gamma_T | Gamma_nonT |",
                "|---|---:|---:|---:|---:|---:|---:|",
            ]
        )
        for _, row in table6[table6.scatter_class.eq(scatter_class)].iterrows():
            lines.append(
                f"| {row.condition} | {int(row.N_T0):,}→{int(row.N_TD):,} | "
                f"{_pct(row.C_T)} | {_pct(row.w_T)} | {_pct(row.C)} | "
                f"{_pct(row.Gamma_T)} | {_pct(row.Gamma_nonT)} |"
            )

    opposite = validation[validation.nonT_direction.eq("opposes_T")]
    same = validation[validation.nonT_direction.eq("same_as_T")]
    dominant_count = int(validation.abs_Gamma_T_gt_abs_Gamma_nonT.sum())
    largest_non_t = validation.reindex(
        validation.Gamma_nonT_direct.abs().sort_values(ascending=False).index
    ).head(5)
    lines.extend(
        [
            "",
            "## 贡献分解验证与主导关系",
            "",
            f"- {dominant_count}/{len(validation)} 个条件满足 `abs(Gamma_T) > abs(Gamma_nonT)`。non-T 与 T 方向相反并部分抵消的条件有 {len(opposite)} 个，同向叠加的条件有 {len(same)} 个。",
            "- 最大闭合误差如下；全部低于 `1e-12`。",
            "",
            "| 检查 | 最大绝对误差 |",
            "|---|---:|",
        ]
    )
    for label, value in acceptance["maximum_absolute_errors"].items():
        lines.append(f"| {label} | {float(value):.3e} |")
    lines.extend(
        [
            "",
            "绝对值最大的五个 non-T 项如下。这里直接报告百分点，不构造贡献率列。",
            "",
            "| 条件 | 类别 | Gamma_T | Gamma_nonT | 方向 |",
            "|---|---|---:|---:|---|",
        ]
    )
    for _, row in largest_non_t.iterrows():
        direction = "抵消 T" if row.nonT_direction == "opposes_T" else "与 T 同向"
        lines.append(
            f"| {row.condition} | {row.scatter_class} | {_pct(row.Gamma_T_direct)} | "
            f"{_pct(row.Gamma_nonT_direct)} | {direction} |"
        )

    lines.extend(
        [
            "",
            "## non-T 形态差异",
            "",
            "| 条件 | 类别 | N_nonT,0→N_nonT,D | D_TV,F | D_TV,B | D_TV,nonT |",
            "|---|---|---:|---:|---:|---:|",
        ]
    )
    for _, row in dtv.iterrows():
        lines.append(
            f"| {row.condition} | {row.scatter_class} | {int(row.N_nonT0):,}→{int(row.N_nonTD):,} | "
            f"{_num_or_na(row.D_TV_F)} | {_num_or_na(row.D_TV_B)} | {_num_or_na(row.D_TV_nonT)} |"
        )
    lines.extend(
        [
            "",
            "| 类别 | min | max | range | 最小条件 | 最大条件 | 客观趋势 |",
            "|---|---:|---:|---:|---|---|---|",
        ]
    )
    dtv_observations: list[tuple[str, str, str]] = []
    for scatter_class in e2.CLASSES:
        selected = dtv[dtv.scatter_class.eq(scatter_class)].set_index("condition").D_TV_nonT
        finite = selected.dropna()
        if finite.empty:
            minimum = maximum = value_range = "NA"
            minimum_condition = maximum_condition = "NA"
            trend = "全部为 NA，无法判定"
        else:
            values = finite.to_numpy(dtype=float)
            minimum = f"{values.min():.6f}"
            maximum = f"{values.max():.6f}"
            value_range = f"{values.max() - values.min():.6f}"
            minimum_condition = str(finite.idxmin())
            maximum_condition = str(finite.idxmax())
            if len(finite) != len(selected):
                trend = "含 NA，无法判定完整序列单调性"
            elif np.all(np.diff(values) > 0):
                trend = "严格增加"
            elif np.all(np.diff(values) < 0):
                trend = "严格下降"
            else:
                trend = "存在下降或起伏，不是单调增加"
        dtv_observations.append((scatter_class, maximum_condition, trend))
        lines.append(
            f"| {scatter_class} | {minimum} | {maximum} | {value_range} | "
            f"{minimum_condition} | {maximum_condition} | {trend} |"
        )

    lines.extend(
        [
            "",
            "## baseline total 的 F/T/B 来源组成",
            "",
            "| 条件 | N0 | N_F,0 | N_T,0 | N_B,0 | w_F | w_T | w_B |",
            "|---|---:|---:|---:|---:|---:|---:|---:|",
        ]
    )
    for _, row in composition.iterrows():
        lines.append(
            f"| {row.condition} | {int(row.N0_total):,} | {int(row.N_F0):,} | "
            f"{int(row.N_T0):,} | {int(row.N_B0):,} | {_pct(row.w_F, 6)} | "
            f"{_pct(row.w_T, 6)} | {_pct(row.w_B, 6)} |"
        )

    undefined = int(dtv[["D_TV_F", "D_TV_B", "D_TV_nonT"]].isna().sum().sum())
    peak_conditions = {condition for _, condition, _ in dtv_observations}
    if len(peak_conditions) == 1:
        dtv_peak_text = f"三类 `D_TV,nonT` 均在 {next(iter(peak_conditions))} 达到最大值"
    else:
        dtv_peak_text = "各类 `D_TV,nonT` 最大值条件为 " + "、".join(
            f"{scatter_class}: {condition}"
            for scatter_class, condition, _ in dtv_observations
        )
    dtv_trend_text = "；".join(
        f"{scatter_class}：{trend}" for scatter_class, _, trend in dtv_observations
    )
    ordered_composition = composition.sort_values("depth_mm")
    composition_trends = []
    for region in ("F", "T", "B"):
        values = ordered_composition[f"w_{region}"].to_numpy(dtype=float)
        if np.all(np.diff(values) > 0):
            trend = "严格增加"
        elif np.all(np.diff(values) < 0):
            trend = "严格下降"
        else:
            trend = "存在起伏"
        composition_trends.append(f"{region} {trend}")
    if len(opposite) and len(same):
        direction_text = "non-T 的方向随条件变化"
    elif len(opposite):
        direction_text = "全部 non-T 项均抵消 T 项"
    else:
        direction_text = "全部 non-T 项均与 T 项同向"
    lines.extend(
        [
            "",
            "## 图形数据来源与异常记录",
            "",
            f"- 图 5 的全部 2 mm 原始计数位于 `{FIG5_DATA_NAME}`，三张图分别为 "
            + "、".join(f"`{name}`" for name in FIG5_NAMES.values())
            + "。每个 panel 使用独立纵轴。",
            f"- stacked bar 使用 `{COMPOSITION_NAME}` 的精确 baseline total 权重，输出为 `{COMPOSITION_FIGURE_NAME}`；每根柱的权重和均为 1。",
            "- baseline total 的来源组成趋势为 " + "、".join(composition_trends) + "。",
            f"- 本数据中 DTV 空直方图数量为 {undefined}；若其他数据集出现空区域，脚本写为 `NA`，不会写成零。",
            f"- {dtv_peak_text}；{dtv_trend_text}。",
            f"- 当前有 {dominant_count}/{len(validation)} 个条件满足 T 项绝对值占优；{direction_text}。",
            "",
        ]
    )
    return "\n".join(lines)


def write_manifest(
    output_dir: Path,
    results_root: Path,
    audit_dir: Path,
    sources: list[dict[str, str]],
    acceptance: dict[str, Any],
) -> None:
    data = {
        "schema_version": 1,
        "analysis": "article_section_3_2_raw_event_reanalysis",
        "experiment": "E2",
        "publication_status": "complete",
        "results_root": str(results_root),
        "audit_summary": str(audit_dir / "audit_summary.yaml"),
        "parameters": {
            "input_layer": "events/valid",
            "summary_source": "grid-zero",
            "event_selection": "matched profile and recorded slit_label inside zero-pose closed detector ROI",
            "scatter_classes": {
                "total": "scatter_count_total >= 1",
                "k1": "scatter_count_total == 1",
                "ms": "scatter_count_total >= 2",
            },
            "source_regions": {
                "F": "z1 < zc - 5 mm",
                "T": "zc - 5 mm <= z1 < zc + 5 mm",
                "B": "z1 >= zc + 5 mm",
            },
            "depth_range_mm": list(e2.DEPTH_RANGE_MM),
            "depth_bin_width_mm": DEPTH_BIN_WIDTH_MM,
            "nonT_DTV_rule": "concatenate labeled F and B region-anchored bins, normalize jointly, and do not smooth across T",
            "resampling": "none",
            "confidence_intervals": "none",
            "significance_tests": "none",
        },
        "input_files": sources,
        "maximum_absolute_errors": acceptance["maximum_absolute_errors"],
        "outputs": sorted(name for name in OUTPUT_NAMES if name != MANIFEST_NAME),
    }
    (output_dir / MANIFEST_NAME).write_text(
        yaml.safe_dump(data, sort_keys=False, allow_unicode=True), encoding="utf-8"
    )


def write_artifacts(
    output_dir: Path,
    tables: dict[str, pd.DataFrame],
    sources: list[dict[str, str]],
    results_root: Path,
    audit_dir: Path,
) -> tuple[dict[str, Any], str]:
    output_dir.mkdir(parents=True, exist_ok=True)
    tables["table6"].to_csv(output_dir / TABLE6_NAME, index=False, float_format="%.17g")
    tables["dtv"].to_csv(
        output_dir / DTV_NAME,
        index=False,
        float_format="%.17g",
        na_rep="NA",
    )
    tables["composition"].to_csv(
        output_dir / COMPOSITION_NAME, index=False, float_format="%.17g"
    )
    tables["fig5"].to_csv(output_dir / FIG5_DATA_NAME, index=False, float_format="%.17g")
    tables["validation"].to_csv(
        output_dir / VALIDATION_NAME, index=False, float_format="%.17g"
    )
    for scatter_class, name in FIG5_NAMES.items():
        plot_fig5(tables["fig5"], scatter_class, output_dir / name)
    plot_source_composition(tables["composition"], output_dir / COMPOSITION_FIGURE_NAME)
    acceptance = validate_tables(tables)
    (output_dir / ACCEPTANCE_NAME).write_text(
        yaml.safe_dump(acceptance, sort_keys=False, allow_unicode=True), encoding="utf-8"
    )
    write_manifest(output_dir, results_root, audit_dir, sources, acceptance)
    actual = {path.name for path in output_dir.iterdir() if path.is_file()}
    if actual != set(OUTPUT_NAMES):
        raise AssertionError(
            f"section 3.2 output contract mismatch: expected {sorted(OUTPUT_NAMES)}, got {sorted(actual)}"
        )
    return acceptance, build_summary_markdown(tables, acceptance)


def run_analysis(
    results_root: Path,
    audit_dir: Path,
    output_dir: Path,
) -> tuple[dict[str, pd.DataFrame], dict[str, Any], str]:
    frames, sources = load_raw_condition_frames(results_root, audit_dir)
    tables = compute_tables(frames, _formal_t1(results_root))
    acceptance, summary = write_artifacts(
        output_dir, tables, sources, results_root, audit_dir
    )
    return tables, acceptance, summary


def publish(staging: Path, output_dir: Path, overwrite: bool) -> None:
    if not output_dir.exists():
        staging.replace(output_dir)
        return
    if not overwrite:
        raise FileExistsError(f"output directory exists; pass --overwrite: {output_dir}")
    backup = output_dir.parent / f".{output_dir.name}.backup"
    if backup.exists():
        raise FileExistsError(f"stale section 3.2 backup blocks overwrite: {backup}")
    output_dir.replace(backup)
    try:
        staging.replace(output_dir)
    except Exception:
        if output_dir.exists():
            shutil.rmtree(output_dir)
        backup.replace(output_dir)
        raise
    shutil.rmtree(backup)


def _atomic_write_text(path: Path, value: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    os.close(descriptor)
    temporary = Path(temporary_name)
    try:
        temporary.write_text(value, encoding="utf-8")
        temporary.replace(path)
    except Exception:
        temporary.unlink(missing_ok=True)
        raise


def validate_output_location(results_root: Path, output_dir: Path) -> None:
    """Keep custom publication targets away from source and formal E2 directories."""
    results_root = results_root.resolve()
    output_dir = output_dir.resolve()
    if output_dir == results_root or output_dir in results_root.parents:
        raise ValueError("section 3.2 output cannot be the results root or its ancestor")
    try:
        output_dir.relative_to(results_root)
    except ValueError:
        return
    supplementary = (
        results_root / "postprocessing" / "E2" / "supplementary"
    ).resolve()
    if output_dir == supplementary or supplementary not in output_dir.parents:
        raise ValueError(
            "an output inside results-root must be an independent E2 supplementary directory"
        )


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--results-root", type=Path, required=True)
    parser.add_argument("--audit-dir", type=Path)
    parser.add_argument("--output-dir", type=Path)
    parser.add_argument(
        "--summary-output",
        type=Path,
        default=Path("docs/articlev2_analysis") / SUMMARY_NAME,
    )
    parser.add_argument("--overwrite", action="store_true")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    results_root = args.results_root.resolve()
    audit_dir = (args.audit_dir or results_root / "data_processing" / "audit").resolve()
    output_dir = (
        args.output_dir
        or results_root / "postprocessing" / "E2" / "supplementary" / DEFAULT_SUBDIRECTORY
    ).resolve()
    summary_output = args.summary_output.resolve()
    validate_output_location(results_root, output_dir)
    if output_dir == summary_output or output_dir in summary_output.parents:
        raise ValueError("summary output must remain outside the atomic artifact directory")
    if output_dir.exists() and not args.overwrite:
        raise FileExistsError(f"output directory exists; pass --overwrite: {output_dir}")
    output_dir.parent.mkdir(parents=True, exist_ok=True)
    staging = Path(tempfile.mkdtemp(prefix=f".{output_dir.name}.staging-", dir=output_dir.parent))
    try:
        _, acceptance, summary = run_analysis(results_root, audit_dir, staging)
        publish(staging, output_dir, args.overwrite)
        _atomic_write_text(summary_output, summary)
    except Exception:
        shutil.rmtree(staging, ignore_errors=True)
        raise
    print(f"output: {output_dir}")
    print(f"summary: {summary_output}")
    print(f"acceptance: {acceptance['overall_status']}")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as error:
        print(f"section 3.2 analysis error: {error}", file=sys.stderr)
        raise SystemExit(1) from error
