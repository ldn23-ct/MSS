#!/usr/bin/env python3
"""Compare P4-S4 truth-front and slab-reference first-scatter depths."""

from __future__ import annotations

import argparse
import math
import os
import shutil
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

os.environ.setdefault("MPLCONFIGDIR", "/tmp/mss_matplotlib")
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from scripts.data_processing.common import RunMetadata, load_run_metadata
from scripts.postprocessing.e3 import run as e3


CENTER_OFFSETS_MM = (-2.5, 0.0, 2.5)
CENTER_POINTS = frozenset(
    (float(x), float(y)) for x in CENTER_OFFSETS_MM for y in CENTER_OFFSETS_MM
)
DEPTH_MIN_MM = 0.0
DEPTH_MAX_MM = 220.0
DEPTH_BIN_WIDTH_MM = 2.0
DEPTH_EDGES_MM = np.arange(
    DEPTH_MIN_MM, DEPTH_MAX_MM + DEPTH_BIN_WIDTH_MM, DEPTH_BIN_WIDTH_MM
)
FRONT_BOUNDARY_MM = 55.0
TARGET_INTERVAL_MM = (55.0, 65.0)
DEFAULT_SUBDIRECTORY = "center3x3_first_scatter_depth"

FIGURE_NAMES = (
    "E3_SF1_P4_S4_front_components_depth.png",
    "E3_SF2_P4_S4_truth_front_vs_slab_overlay.png",
    "E3_SF3_P4_S4_truth_front_roi_depth.png",
)
TABLE_NAME = "E3_ST1_P4_S4_front_source_summary.csv"
OUTPUT_NAMES = (*FIGURE_NAMES, TABLE_NAME)
SUMMARY_COLUMNS = (
    "p4_pooled_n_primary",
    "slab_pooled_n_primary",
    "alpha",
    "truth_front_total_count",
    "slab_front_total_count",
    "slab_to_truth_ratio",
    "slab_fraction_z_lt55",
    "pearson_r_z_lt55",
)


@dataclass(frozen=True)
class AnalysisInputs:
    p4_total_depths: np.ndarray
    truth_front_depths: np.ndarray
    slab_depths: np.ndarray
    truth_front_images: np.ndarray
    p4_pooled_n_primary: int
    slab_pooled_n_primary: int
    p4_out_of_domain_count: int
    slab_out_of_domain_count: int


def _point(x: Any, y: Any, label: str) -> tuple[float, float]:
    try:
        point = (float(x), float(y))
    except (TypeError, ValueError) as error:
        raise ValueError(f"{label} contains a non-numeric grid coordinate") from error
    if not all(math.isfinite(value) for value in point):
        raise ValueError(f"{label} contains a non-finite grid coordinate")
    return point


def select_center_rows(rows: pd.DataFrame, label: str) -> pd.DataFrame:
    required = {"head_offset_x_mm", "head_offset_y_mm"}
    missing = sorted(required.difference(rows.columns))
    if missing:
        raise ValueError(f"{label} rows are missing coordinate columns: {missing}")
    points = [
        _point(row.head_offset_x_mm, row.head_offset_y_mm, label)
        for row in rows.itertuples(index=False)
    ]
    indices = [index for index, point in enumerate(points) if point in CENTER_POINTS]
    selected = rows.iloc[indices].copy()
    found = [points[index] for index in indices]
    duplicates = sorted({point for point in found if found.count(point) > 1})
    missing_points = sorted(CENTER_POINTS.difference(found))
    if duplicates or missing_points or len(selected) != 9:
        raise ValueError(
            f"{label} center 3x3 must contain nine unique poses; "
            f"missing={missing_points}, duplicates={duplicates}"
        )
    return selected.sort_values(["head_offset_x_mm", "head_offset_y_mm"])


def select_center_slab_runs(
    runs: Iterable[tuple[Path, RunMetadata]],
) -> list[tuple[Path, RunMetadata]]:
    selected = [
        (path, metadata)
        for path, metadata in runs
        if (metadata.head_offset_x_mm, metadata.head_offset_y_mm) in CENTER_POINTS
    ]
    found = [
        (metadata.head_offset_x_mm, metadata.head_offset_y_mm)
        for _, metadata in selected
    ]
    duplicates = sorted({point for point in found if found.count(point) > 1})
    missing_points = sorted(CENTER_POINTS.difference(found))
    if duplicates or missing_points or len(selected) != 9:
        raise ValueError(
            "slab center 3x3 must contain nine unique poses; "
            f"missing={missing_points}, duplicates={duplicates}"
        )
    return sorted(
        selected,
        key=lambda item: (item[1].head_offset_x_mm, item[1].head_offset_y_mm),
    )


def _domain_depths(values: np.ndarray, label: str) -> tuple[np.ndarray, int]:
    depths = np.asarray(values, dtype=float)
    if depths.ndim != 1 or not np.isfinite(depths).all():
        raise ValueError(f"{label} first_scatter_z must be a finite one-dimensional array")
    inside = (depths >= DEPTH_MIN_MM) & (depths <= DEPTH_MAX_MM)
    return depths[inside], int((~inside).sum())


def _histogram(values: np.ndarray) -> np.ndarray:
    return np.histogram(np.asarray(values, dtype=float), bins=DEPTH_EDGES_MM)[0]


def build_depth_table(
    p4_total_depths: np.ndarray,
    truth_front_depths: np.ndarray,
    slab_depths: np.ndarray,
    alpha: float,
) -> pd.DataFrame:
    truth_values = np.asarray(truth_front_depths, dtype=float)
    if (truth_values >= FRONT_BOUNDARY_MM).any():
        raise ValueError("truth-front events must satisfy first_scatter_z < 55 mm")
    if not math.isfinite(alpha) or alpha <= 0:
        raise ValueError("history-derived alpha must be finite and positive")
    total = _histogram(p4_total_depths).astype(np.int64)
    truth = _histogram(truth_values).astype(np.int64)
    slab = alpha * _histogram(slab_depths).astype(float)
    return pd.DataFrame(
        {
            "bin_left_mm": DEPTH_EDGES_MM[:-1],
            "bin_right_mm": DEPTH_EDGES_MM[1:],
            "bin_center_mm": (DEPTH_EDGES_MM[:-1] + DEPTH_EDGES_MM[1:]) / 2.0,
            "p4_total_count": total,
            "truth_front_count": truth,
            "slab_front_count": slab,
            "residual_count": truth.astype(float) - slab,
        }
    )


def roi_depth_statistics(images: np.ndarray) -> pd.DataFrame:
    values = np.asarray(images, dtype=float)
    if values.shape != (len(DEPTH_EDGES_MM) - 1, 9, 9):
        raise ValueError("truth-front depth images must have shape (110, 9, 9)")
    roi = values[:, e3.DEFECT_MASK].mean(axis=1)
    background = values[:, e3.BACKGROUND_MASK].mean(axis=1)
    return pd.DataFrame(
        {
            "bin_left_mm": DEPTH_EDGES_MM[:-1],
            "bin_right_mm": DEPTH_EDGES_MM[1:],
            "bin_center_mm": (DEPTH_EDGES_MM[:-1] + DEPTH_EDGES_MM[1:]) / 2.0,
            "background_mean": background,
            "defect_roi_mean": roi,
            "delta_background_minus_roi": background - roi,
        }
    )


def pearson_front_histograms(
    truth_front_depths: np.ndarray, slab_depths: np.ndarray
) -> float:
    truth = np.asarray(truth_front_depths, dtype=float)
    slab = np.asarray(slab_depths, dtype=float)
    truth = _histogram(truth[truth < FRONT_BOUNDARY_MM])
    slab = _histogram(slab[slab < FRONT_BOUNDARY_MM])
    front_bins = DEPTH_EDGES_MM[:-1] < FRONT_BOUNDARY_MM
    x = truth[front_bins].astype(float)
    y = slab[front_bins].astype(float)
    if math.isclose(float(x.std()), 0.0) or math.isclose(float(y.std()), 0.0):
        return math.nan
    return float(np.corrcoef(x, y)[0, 1])


def build_summary(inputs: AnalysisInputs, alpha: float) -> pd.DataFrame:
    truth_total = int(len(inputs.truth_front_depths))
    slab_total = float(alpha * len(inputs.slab_depths))
    ratio = slab_total / truth_total if truth_total else math.nan
    slab_fraction = (
        float(np.count_nonzero(inputs.slab_depths < FRONT_BOUNDARY_MM))
        / len(inputs.slab_depths)
        if len(inputs.slab_depths)
        else math.nan
    )
    pearson = pearson_front_histograms(
        inputs.truth_front_depths, inputs.slab_depths
    )
    return pd.DataFrame(
        [{
            "p4_pooled_n_primary": inputs.p4_pooled_n_primary,
            "slab_pooled_n_primary": inputs.slab_pooled_n_primary,
            "alpha": alpha,
            "truth_front_total_count": truth_total,
            "slab_front_total_count": slab_total,
            "slab_to_truth_ratio": ratio,
            "slab_fraction_z_lt55": slab_fraction,
            "pearson_r_z_lt55": pearson,
        }],
        columns=SUMMARY_COLUMNS,
    )


def _decorate_depth_axis(axis: plt.Axes, *, zero_line: bool = False) -> None:
    axis.axvspan(*TARGET_INTERVAL_MM, color="#BDBDBD", alpha=0.28, zorder=0)
    axis.axvline(FRONT_BOUNDARY_MM, color="#555555", linestyle="--", linewidth=1.0)
    if zero_line:
        axis.axhline(0.0, color="#222222", linestyle=":", linewidth=1.0)
    axis.set_xlim(DEPTH_MIN_MM, DEPTH_MAX_MM)
    axis.grid(axis="y", alpha=0.18)


def plot_front_components(table: pd.DataFrame, output: Path) -> None:
    fig, axes = plt.subplots(2, 2, figsize=(13.0, 8.8), sharex=True, constrained_layout=True)
    panels = (
        ("p4_total_count", "(a) P4 Total", "#4D4D4D"),
        ("truth_front_count", "(b) Truth front: $z_1<55$ mm", "#0072B2"),
        ("slab_front_count", r"(c) Slab-estimated front: $\alpha H_{slab}$", "#D55E00"),
        ("residual_count", "(d) Truth front − slab front", "#009E73"),
    )
    for axis, (column, title, color) in zip(axes.flat, panels, strict=True):
        axis.stairs(table[column], DEPTH_EDGES_MM, color=color, linewidth=1.45)
        _decorate_depth_axis(axis, zero_line=column == "residual_count")
        axis.set_title(title)
        axis.set_ylabel("Pooled bin count")
    shared_max = 1.05 * max(
        float(table.truth_front_count.max()), float(table.slab_front_count.max()), 1.0
    )
    axes[0, 1].set_ylim(0.0, shared_max)
    axes[1, 0].set_ylim(0.0, shared_max)
    residual_limit = max(float(np.abs(table.residual_count).max()) * 1.05, 1.0)
    axes[1, 1].set_ylim(-residual_limit, residual_limit)
    for axis in axes[1, :]:
        axis.set_xlabel("First-scatter depth z (mm)")
    fig.suptitle("P4-S4 center 3×3 front-source depth components")
    e3._save_png(fig, output)


def plot_front_overlay(table: pd.DataFrame, output: Path) -> None:
    fig, axis = plt.subplots(figsize=(10.5, 6.2), constrained_layout=True)
    axis.stairs(table.truth_front_count, DEPTH_EDGES_MM, color="#0072B2", linewidth=1.55,
                label=r"Truth front: P4 $z_1<55$ mm")
    axis.stairs(table.slab_front_count, DEPTH_EDGES_MM, color="#D55E00", linewidth=1.55,
                label=r"Slab front estimate: $\alpha H_{slab}$")
    _decorate_depth_axis(axis)
    axis.set(xlabel="First-scatter depth z (mm)", ylabel="Pooled bin count",
             title="P4-S4 truth front versus slab-estimated front")
    axis.set_ylim(bottom=0.0)
    axis.legend(fontsize=9)
    e3._save_png(fig, output)


def plot_roi_depth(roi: pd.DataFrame, output: Path) -> None:
    fig, axes = plt.subplots(2, 1, figsize=(10.5, 8.2), sharex=True, constrained_layout=True)
    axes[0].stairs(roi.background_mean, DEPTH_EDGES_MM, color="#4D4D4D", linewidth=1.5,
                   label=r"Background mean $\mu_{BG}$ (32 poses)")
    axes[0].stairs(roi.defect_roi_mean, DEPTH_EDGES_MM, color="#0072B2", linewidth=1.5,
                   label=r"Defect ROI mean $\mu_{ROI}$ (25 poses)")
    axes[0].set(ylabel="Mean count per pose", title="(a) Truth-front count level")
    axes[0].legend(fontsize=9)
    axes[1].stairs(roi.delta_background_minus_roi, DEPTH_EDGES_MM, color="#009E73",
                   linewidth=1.5, label=r"$\Delta=\mu_{BG}-\mu_{ROI}$")
    axes[1].axhline(0.0, color="#222222", linestyle=":", linewidth=1.0)
    axes[1].set(xlabel="First-scatter depth z (mm)", ylabel="Mean-count difference",
                title="(b) Defect/background difference")
    axes[1].legend(fontsize=9)
    for axis in axes:
        axis.axvline(FRONT_BOUNDARY_MM, color="#555555", linestyle="--", linewidth=1.0)
        axis.set_xlim(DEPTH_MIN_MM, FRONT_BOUNDARY_MM)
        axis.grid(axis="y", alpha=0.18)
    fig.suptitle("P4-S4 truth-front response by first-scatter depth")
    e3._save_png(fig, output)


def _selected_total_depths(event_path: Path, metadata: RunMetadata,
                           loader: e3.EventLoader) -> tuple[np.ndarray, int]:
    frame = e3.select_events(loader.read(event_path), metadata, "S4")
    raw = frame.loc[e3.scatter_counts(frame) >= 1, "first_scatter_z"].to_numpy(dtype=float)
    return _domain_depths(raw, metadata.pose_id)


def load_inputs(results_root: Path, p4_rows: pd.DataFrame,
                slab_runs: list[tuple[Path, RunMetadata]],
                loader: e3.EventLoader) -> AnalysisInputs:
    select_center_rows(p4_rows, "P4/P001")
    p4_total: list[np.ndarray] = []
    truth_front: list[np.ndarray] = []
    truth_images = np.zeros((len(DEPTH_EDGES_MM) - 1, 9, 9), dtype=np.int64)
    p4_histories = 0
    p4_excluded = 0
    for row in p4_rows.itertuples(index=False):
        x, y = float(row.head_offset_x_mm), float(row.head_offset_y_mm)
        event_path = (results_root / str(row.valid_file)).resolve()
        metadata = load_run_metadata(event_path.parent / "metadata.yaml")
        e3._validate_run_metadata(metadata, phantom="P4", profile="P001", x=x, y=y)
        depths, excluded = _selected_total_depths(event_path, metadata, loader)
        p4_excluded += excluded
        front = depths[depths < FRONT_BOUNDARY_MM]
        image_y, image_x = e3.grid_position_indices(x, y)
        truth_images[:, image_y, image_x] = _histogram(front)
        if (x, y) in CENTER_POINTS:
            p4_total.append(depths)
            truth_front.append(front)
            p4_histories += metadata.n_primary

    slab_depths: list[np.ndarray] = []
    slab_histories = 0
    slab_excluded = 0
    for event_path, metadata in select_center_slab_runs(slab_runs):
        e3._validate_run_metadata(metadata, phantom=None, profile="P001",
                                  x=metadata.head_offset_x_mm,
                                  y=metadata.head_offset_y_mm)
        depths, excluded = _selected_total_depths(event_path, metadata, loader)
        slab_depths.append(depths)
        slab_histories += metadata.n_primary
        slab_excluded += excluded
    if p4_histories <= 0 or slab_histories <= 0:
        raise ValueError("actual pooled primary histories must be positive")
    return AnalysisInputs(
        p4_total_depths=np.concatenate(p4_total),
        truth_front_depths=np.concatenate(truth_front),
        slab_depths=np.concatenate(slab_depths),
        truth_front_images=truth_images,
        p4_pooled_n_primary=p4_histories,
        slab_pooled_n_primary=slab_histories,
        p4_out_of_domain_count=p4_excluded,
        slab_out_of_domain_count=slab_excluded,
    )


def write_outputs(depth_table: pd.DataFrame, roi_table: pd.DataFrame,
                  summary: pd.DataFrame, output_dir: Path) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    plot_front_components(depth_table, output_dir / FIGURE_NAMES[0])
    plot_front_overlay(depth_table, output_dir / FIGURE_NAMES[1])
    plot_roi_depth(roi_table, output_dir / FIGURE_NAMES[2])
    summary.to_csv(output_dir / TABLE_NAME, index=False)
    validate_outputs(output_dir)


def validate_outputs(output_dir: Path) -> None:
    actual = {path.name for path in output_dir.iterdir() if path.is_file()}
    if actual != set(OUTPUT_NAMES) or any(path.is_dir() for path in output_dir.iterdir()):
        raise AssertionError(
            f"supplementary E3 output mismatch: expected {sorted(OUTPUT_NAMES)}, got {sorted(actual)}"
        )
    summary = pd.read_csv(output_dir / TABLE_NAME)
    if tuple(summary.columns) != SUMMARY_COLUMNS or len(summary) != 1:
        raise AssertionError("front-source summary CSV contract failed")
    for name in FIGURE_NAMES:
        if (output_dir / name).read_bytes()[:8] != b"\x89PNG\r\n\x1a\n":
            raise AssertionError(f"supplementary E3 figure is not a PNG: {name}")


def publish(staging: Path, output_dir: Path, overwrite: bool) -> None:
    if output_dir.exists():
        if not overwrite:
            raise FileExistsError(f"supplementary E3 output exists; pass --overwrite: {output_dir}")
        backup = output_dir.parent / f".{output_dir.name}.backup"
        if backup.exists():
            raise FileExistsError(f"stale supplementary backup blocks overwrite: {backup}")
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


def run_analysis(results_root: Path, slab_root: Path,
                 output_dir: Path) -> tuple[pd.DataFrame, AnalysisInputs]:
    _, rows_by_condition, slab_runs, _ = e3.preflight(results_root, slab_root)
    inputs = load_inputs(results_root, rows_by_condition[("P4", "P001")], slab_runs,
                         e3.EventLoader())
    alpha = inputs.p4_pooled_n_primary / inputs.slab_pooled_n_primary
    depth_table = build_depth_table(inputs.p4_total_depths, inputs.truth_front_depths,
                                    inputs.slab_depths, alpha)
    roi_table = roi_depth_statistics(inputs.truth_front_images)
    summary = build_summary(inputs, alpha)
    write_outputs(depth_table, roi_table, summary, output_dir)
    return summary, inputs


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--results-root", type=Path, default=Path("results/articlev3_merged"))
    parser.add_argument("--slab-grid-root", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path)
    parser.add_argument("--overwrite", action="store_true")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    results_root = args.results_root.resolve()
    slab_root = args.slab_grid_root.resolve()
    e3_root = (results_root / "postprocessing" / "E3").resolve()
    supplementary_root = (e3_root / e3.SUPPLEMENTARY_DIR_NAME).resolve()
    output_dir = args.output_dir.resolve() if args.output_dir is not None else supplementary_root / DEFAULT_SUBDIRECTORY
    protected = {
        results_root, (results_root / "events").resolve(),
        (results_root / "events" / "raw").resolve(),
        (results_root / "events" / "valid").resolve(), slab_root,
        (slab_root / "events").resolve(), e3_root, supplementary_root,
    }
    if output_dir in protected:
        raise ValueError("supplementary output directory must not replace data or an E3 root")
    output_dir.parent.mkdir(parents=True, exist_ok=True)
    staging = Path(tempfile.mkdtemp(prefix=f".{output_dir.name}.staging-", dir=output_dir.parent))
    try:
        summary, inputs = run_analysis(results_root, slab_root, staging)
        publish(staging, output_dir, args.overwrite)
    except Exception:
        shutil.rmtree(staging, ignore_errors=True)
        raise

    values = summary.iloc[0]
    pearson_text = "undefined" if pd.isna(values.pearson_r_z_lt55) else f"{values.pearson_r_z_lt55:.6f}"
    print(f"supplementary E3 output: {output_dir}")
    print(f"pooled histories: P4={int(values.p4_pooled_n_primary)}, "
          f"slab={int(values.slab_pooled_n_primary)}, alpha={values.alpha:.6g}")
    print(f"truth front={int(values.truth_front_total_count)}, "
          f"slab front={values.slab_front_total_count:.6g}, "
          f"slab/truth={values.slab_to_truth_ratio:.6f}")
    print(f"P_slab,F={values.slab_fraction_z_lt55:.6f}, "
          f"Pearson r (z<55 mm)={pearson_text}")
    print("out-of-domain events: "
          f"P4(all 81 poses)={inputs.p4_out_of_domain_count}, "
          f"slab(center 3x3)={inputs.slab_out_of_domain_count}")
    print("files: 3 PNG + 1 CSV")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as error:
        print(f"front-source depth analysis error: {error}", file=sys.stderr)
        raise SystemExit(1) from error
