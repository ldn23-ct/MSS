#!/usr/bin/env python3
"""Validate front-source subtraction with the measured E3 voxel volumes."""

from __future__ import annotations

import argparse
import math
import os
import shutil
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any

os.environ.setdefault("MPLCONFIGDIR", "/tmp/mss_matplotlib")
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from matplotlib.colors import TwoSlopeNorm

from scripts.postprocessing.e3 import run as e3


DEFECT_FILE_NAME = "defect.npy"
FRONT_FILE_NAME = "front.npy"
FRONT_REBIN_Y = 2
FRONT_REBIN_X = 8
EXPECTED_Z_SLICES = 66
WINDOW_WIDTH = 3
WINDOW_STRIDE = 1
Z_MM_PER_SLICE = 1.0
ALPHA = 1.0
TARGET_SLICE_START = 46
TARGET_SLICE_END_INCLUSIVE = 55
TARGET_SLICE_END_EXCLUSIVE = TARGET_SLICE_END_INCLUSIVE + 1
DEFAULT_SUBDIRECTORY = "real_data_front_validation"
ROI_CNR_SUBDIRECTORY = "roi_cnr_analysis"

FIGURE_NAMES = (
    "E3_RF1_real_data_depth_metrics.png",
    "E3_RF2_real_data_peak_window.png",
)
TABLE_NAMES = (
    "E3_RT1_real_data_window_metrics.csv",
    "E3_RT2_real_data_summary.csv",
)
ARRAY_NAMES = (
    "E3_RN1_windowed_defect.npy",
    "E3_RN2_windowed_front.npy",
    "E3_RN3_windowed_residual.npy",
)
OUTPUT_NAMES = (*FIGURE_NAMES, *TABLE_NAMES, *ARRAY_NAMES)

WINDOW_COLUMNS = (
    "window_index",
    "window_start_index",
    "window_end_index_exclusive",
    "z_start_mm",
    "z_end_mm",
    "z_center_mm",
    "defect_count",
    "front_count",
    "residual_count",
    "front_fraction",
    "retained_fraction",
    "spatial_pearson_r",
    "inside_target_slice_range",
)

SUMMARY_COLUMNS = (
    "defect_input_z",
    "defect_input_y",
    "defect_input_x",
    "front_input_z",
    "front_input_y",
    "front_input_x",
    "front_rebin_y_factor",
    "front_rebin_x_factor",
    "window_width_slices",
    "window_stride_slices",
    "z_mm_per_slice",
    "alpha",
    "output_window_count",
    "output_y",
    "output_x",
    "target_slice_start",
    "target_slice_end_inclusive",
    "target_z_start_mm",
    "target_z_end_mm",
    "peak_window_index",
    "peak_window_start_index",
    "peak_window_end_index_exclusive",
    "peak_z_start_mm",
    "peak_z_end_mm",
    "peak_z_center_mm",
    "peak_defect_count",
    "peak_front_count",
    "peak_residual_count",
    "peak_front_fraction",
    "peak_retained_fraction",
    "peak_spatial_pearson_r",
)


@dataclass(frozen=True)
class AnalysisResult:
    defect_input_shape: tuple[int, int, int]
    front_input_shape: tuple[int, int, int]
    defect_windows: np.ndarray
    front_windows: np.ndarray
    residual_windows: np.ndarray
    metrics: pd.DataFrame
    summary: pd.DataFrame
    peak_window_index: int


def load_count_volume(path: Path, label: str) -> np.ndarray:
    if not path.is_file():
        raise FileNotFoundError(f"{label} NPY is missing: {path}")
    try:
        values = np.load(path, allow_pickle=False)
    except (OSError, ValueError) as error:
        raise ValueError(f"cannot load {label} NPY without pickle: {path}") from error
    if values.ndim != 3:
        raise ValueError(f"{label} volume must be three-dimensional, got {values.shape}")
    if not np.issubdtype(values.dtype, np.number):
        raise ValueError(f"{label} volume must contain numeric counts")
    values = np.asarray(values, dtype=np.float64)
    if not np.isfinite(values).all():
        raise ValueError(f"{label} volume must contain only finite counts")
    if (values < 0).any():
        raise ValueError(f"{label} volume must contain only non-negative counts")
    return values


def rebin_front(front: np.ndarray, defect_shape: tuple[int, int, int]) -> np.ndarray:
    values = np.asarray(front, dtype=np.float64)
    if values.ndim != 3 or len(defect_shape) != 3:
        raise ValueError("front and defect shapes must be three-dimensional")
    expected = (
        defect_shape[0],
        defect_shape[1] * FRONT_REBIN_Y,
        defect_shape[2] * FRONT_REBIN_X,
    )
    if values.shape != expected:
        raise ValueError(
            "front shape must equal defect shape with fixed y/x factors "
            f"{FRONT_REBIN_Y}x{FRONT_REBIN_X}: expected {expected}, got {values.shape}"
        )
    rebinned = values.reshape(
        defect_shape[0],
        defect_shape[1],
        FRONT_REBIN_Y,
        defect_shape[2],
        FRONT_REBIN_X,
    ).sum(axis=(2, 4), dtype=np.float64)
    if rebinned.shape != defect_shape:
        raise AssertionError("rebinned front shape does not match defect shape")
    if not math.isclose(
        float(rebinned.sum(dtype=np.float64)),
        float(values.sum(dtype=np.float64)),
        rel_tol=1e-12,
        abs_tol=1e-8,
    ):
        raise AssertionError("front rebinning did not conserve total counts")
    return rebinned


def sliding_count_windows(volume: np.ndarray) -> np.ndarray:
    values = np.asarray(volume, dtype=np.float64)
    if values.ndim != 3:
        raise ValueError("sliding-window input must be three-dimensional")
    if values.shape[0] < WINDOW_WIDTH:
        raise ValueError(f"z dimension must contain at least {WINDOW_WIDTH} slices")
    windows = np.lib.stride_tricks.sliding_window_view(
        values, window_shape=WINDOW_WIDTH, axis=0
    )[::WINDOW_STRIDE]
    result = windows.sum(axis=-1, dtype=np.float64)
    expected_z = (values.shape[0] - WINDOW_WIDTH) // WINDOW_STRIDE + 1
    if result.shape != (expected_z, values.shape[1], values.shape[2]):
        raise AssertionError("unexpected sliding-window output shape")
    return np.ascontiguousarray(result)


def _spatial_pearson(defect: np.ndarray, front: np.ndarray, index: int) -> float:
    left = np.asarray(defect, dtype=float).ravel()
    right = np.asarray(front, dtype=float).ravel()
    if math.isclose(float(left.std()), 0.0) or math.isclose(float(right.std()), 0.0):
        raise ValueError(f"spatial Pearson r is undefined for constant window {index}")
    value = float(np.corrcoef(left, right)[0, 1])
    if not math.isfinite(value):
        raise ValueError(f"spatial Pearson r is non-finite for window {index}")
    return value


def build_window_metrics(
    defect_windows: np.ndarray,
    front_windows: np.ndarray,
) -> pd.DataFrame:
    defect = np.asarray(defect_windows, dtype=np.float64)
    front = np.asarray(front_windows, dtype=np.float64)
    if defect.shape != front.shape or defect.ndim != 3:
        raise ValueError("windowed defect and front arrays must have the same 3D shape")
    residual = defect - ALPHA * front
    defect_totals = defect.sum(axis=(1, 2), dtype=np.float64)
    front_totals = front.sum(axis=(1, 2), dtype=np.float64)
    if not np.isfinite(defect_totals).all() or (defect_totals <= 0).any():
        raise ValueError("front/retained fractions require positive defect counts in every window")
    rows: list[dict[str, Any]] = []
    for index in range(defect.shape[0]):
        start = index * WINDOW_STRIDE
        end = start + WINDOW_WIDTH
        front_fraction = float(front_totals[index] / defect_totals[index])
        retained_fraction = float((defect_totals[index] - front_totals[index]) / defect_totals[index])
        rows.append(
            {
                "window_index": index,
                "window_start_index": start,
                "window_end_index_exclusive": end,
                "z_start_mm": start * Z_MM_PER_SLICE,
                "z_end_mm": end * Z_MM_PER_SLICE,
                "z_center_mm": (start + WINDOW_WIDTH / 2.0) * Z_MM_PER_SLICE,
                "defect_count": float(defect_totals[index]),
                "front_count": float(front_totals[index]),
                "residual_count": float(residual[index].sum(dtype=np.float64)),
                "front_fraction": front_fraction,
                "retained_fraction": retained_fraction,
                "spatial_pearson_r": _spatial_pearson(defect[index], front[index], index),
                "inside_target_slice_range": (
                    start >= TARGET_SLICE_START and end <= TARGET_SLICE_END_EXCLUSIVE
                ),
            }
        )
    frame = pd.DataFrame(rows, columns=WINDOW_COLUMNS)
    if not np.allclose(
        frame.front_fraction.to_numpy() + frame.retained_fraction.to_numpy(),
        1.0,
        rtol=1e-12,
        atol=1e-12,
    ):
        raise AssertionError("front and retained fractions must sum to one")
    return frame


def select_peak_window(metrics: pd.DataFrame) -> int:
    required = {"window_index", "residual_count", "inside_target_slice_range"}
    if not required.issubset(metrics.columns):
        raise ValueError(f"window metrics are missing columns: {sorted(required - set(metrics.columns))}")
    candidates = metrics.loc[metrics.inside_target_slice_range.astype(bool)].sort_values(
        "window_index"
    )
    if candidates.empty:
        raise ValueError("no complete three-slice window lies inside target slices 46--55")
    residuals = candidates.residual_count.to_numpy(dtype=float)
    if not np.isfinite(residuals).all():
        raise ValueError("target-window residual counts must be finite")
    return int(candidates.iloc[int(np.argmax(residuals))].window_index)


def build_summary(
    defect_shape: tuple[int, int, int],
    front_shape: tuple[int, int, int],
    output_shape: tuple[int, int, int],
    metrics: pd.DataFrame,
    peak_window_index: int,
) -> pd.DataFrame:
    matches = metrics.loc[metrics.window_index.eq(peak_window_index)]
    if len(matches) != 1:
        raise ValueError("peak window index must identify exactly one metrics row")
    peak = matches.iloc[0]
    row = {
        "defect_input_z": defect_shape[0],
        "defect_input_y": defect_shape[1],
        "defect_input_x": defect_shape[2],
        "front_input_z": front_shape[0],
        "front_input_y": front_shape[1],
        "front_input_x": front_shape[2],
        "front_rebin_y_factor": FRONT_REBIN_Y,
        "front_rebin_x_factor": FRONT_REBIN_X,
        "window_width_slices": WINDOW_WIDTH,
        "window_stride_slices": WINDOW_STRIDE,
        "z_mm_per_slice": Z_MM_PER_SLICE,
        "alpha": ALPHA,
        "output_window_count": output_shape[0],
        "output_y": output_shape[1],
        "output_x": output_shape[2],
        "target_slice_start": TARGET_SLICE_START,
        "target_slice_end_inclusive": TARGET_SLICE_END_INCLUSIVE,
        "target_z_start_mm": TARGET_SLICE_START * Z_MM_PER_SLICE,
        "target_z_end_mm": TARGET_SLICE_END_EXCLUSIVE * Z_MM_PER_SLICE,
        "peak_window_index": peak_window_index,
        "peak_window_start_index": int(peak.window_start_index),
        "peak_window_end_index_exclusive": int(peak.window_end_index_exclusive),
        "peak_z_start_mm": float(peak.z_start_mm),
        "peak_z_end_mm": float(peak.z_end_mm),
        "peak_z_center_mm": float(peak.z_center_mm),
        "peak_defect_count": float(peak.defect_count),
        "peak_front_count": float(peak.front_count),
        "peak_residual_count": float(peak.residual_count),
        "peak_front_fraction": float(peak.front_fraction),
        "peak_retained_fraction": float(peak.retained_fraction),
        "peak_spatial_pearson_r": float(peak.spatial_pearson_r),
    }
    return pd.DataFrame([row], columns=SUMMARY_COLUMNS)


def analyze_volumes(defect: np.ndarray, front: np.ndarray) -> AnalysisResult:
    defect_values = np.asarray(defect, dtype=np.float64)
    front_values = np.asarray(front, dtype=np.float64)
    for values, label in ((defect_values, "defect"), (front_values, "front")):
        if values.ndim != 3 or not np.isfinite(values).all() or (values < 0).any():
            raise ValueError(f"{label} volume must be a finite, non-negative 3D array")
    if defect_values.shape[0] != EXPECTED_Z_SLICES:
        raise ValueError(
            f"defect volume must contain {EXPECTED_Z_SLICES} z slices, got {defect_values.shape[0]}"
        )
    rebinned_front = rebin_front(front_values, defect_values.shape)
    defect_windows = sliding_count_windows(defect_values)
    front_windows = sliding_count_windows(rebinned_front)
    residual_windows = defect_windows - ALPHA * front_windows
    if not np.array_equal(residual_windows, defect_windows - front_windows):
        raise AssertionError("windowed residual must equal defect minus front elementwise")
    metrics = build_window_metrics(defect_windows, front_windows)
    peak_window_index = select_peak_window(metrics)
    summary = build_summary(
        tuple(defect_values.shape),
        tuple(front_values.shape),
        tuple(defect_windows.shape),
        metrics,
        peak_window_index,
    )
    return AnalysisResult(
        defect_input_shape=tuple(defect_values.shape),
        front_input_shape=tuple(front_values.shape),
        defect_windows=defect_windows,
        front_windows=front_windows,
        residual_windows=residual_windows,
        metrics=metrics,
        summary=summary,
        peak_window_index=peak_window_index,
    )


def plot_depth_metrics(metrics: pd.DataFrame, peak_index: int, output: Path) -> None:
    peak = metrics.loc[metrics.window_index.eq(peak_index)].iloc[0]
    z = metrics.z_center_mm.to_numpy(dtype=float)
    fig, axes = plt.subplots(3, 1, figsize=(10.8, 10.4), sharex=True, constrained_layout=True)
    axes[0].plot(z, metrics.defect_count, color="#4D4D4D", label="D: defect")
    axes[0].plot(z, metrics.front_count, color="#D55E00", label="F: front")
    axes[0].plot(z, metrics.residual_count, color="#0072B2", label="R: D − F")
    axes[0].set(ylabel="Three-slice count", title="(a) Sliding-window count components")
    axes[0].legend(fontsize=9, ncol=3)
    axes[1].plot(z, metrics.front_fraction, color="#D55E00", label="Front fraction F/D")
    axes[1].plot(z, metrics.retained_fraction, color="#009E73", label="Retained fraction (D−F)/D")
    axes[1].set(ylabel="Fraction", title="(b) Count fractions")
    axes[1].legend(fontsize=9)
    axes[2].plot(z, metrics.spatial_pearson_r, color="#CC79A7", label="Spatial Pearson r")
    axes[2].set(
        xlabel="Window-center depth z (mm)",
        ylabel="Pearson r",
        title="(c) Full-plane D/F spatial correlation",
    )
    axes[2].legend(fontsize=9)
    for axis in axes:
        axis.axvspan(
            TARGET_SLICE_START * Z_MM_PER_SLICE,
            TARGET_SLICE_END_EXCLUSIVE * Z_MM_PER_SLICE,
            color="#BDBDBD",
            alpha=0.25,
            label="target slices 46–55",
        )
        axis.axvline(float(peak.z_center_mm), color="#222222", linestyle="--", linewidth=1.0)
        axis.grid(alpha=0.2)
    fig.suptitle(
        "Measured E3 front-source subtraction by depth\n"
        f"selected window [{int(peak.window_start_index)}, "
        f"{int(peak.window_end_index_exclusive)}) mm, center {peak.z_center_mm:g} mm"
    )
    e3._save_png(fig, output)


def plot_peak_window(result: AnalysisResult, output: Path) -> None:
    index = result.peak_window_index
    defect = result.defect_windows[index]
    front = result.front_windows[index]
    residual = result.residual_windows[index]
    peak = result.metrics.loc[result.metrics.window_index.eq(index)].iloc[0]
    count_min = min(float(defect.min()), float(front.min()))
    count_max = max(float(defect.max()), float(front.max()))
    if not math.isfinite(count_max) or count_max <= count_min:
        raise ValueError("shared defect/front color range is undefined")
    residual_limit = max(float(np.abs(residual).max()), np.finfo(float).eps)
    residual_norm = TwoSlopeNorm(vmin=-residual_limit, vcenter=0.0, vmax=residual_limit)
    fig, axes = plt.subplots(1, 3, figsize=(14.2, 4.8), constrained_layout=True)
    panels = (
        (defect, "(a) D: defect", "viridis", None),
        (front, "(b) F: rebinned front", "viridis", None),
        (residual, "(c) R: D − F", "coolwarm", residual_norm),
    )
    for axis, (image, title, cmap, norm) in zip(axes, panels, strict=True):
        kwargs: dict[str, Any] = {"origin": "lower", "aspect": "equal", "cmap": cmap}
        if norm is None:
            kwargs.update(vmin=count_min, vmax=count_max)
        else:
            kwargs["norm"] = norm
        view = axis.imshow(image, **kwargs)
        axis.set(xlabel="x pixel index", ylabel="y pixel index", title=title)
        label = "Three-slice count" if norm is None else "Signed residual count"
        fig.colorbar(view, ax=axis, shrink=0.82, pad=0.03, label=label)
    fig.suptitle(
        f"Measured E3 selected window [{int(peak.window_start_index)}, "
        f"{int(peak.window_end_index_exclusive)}) mm (center {peak.z_center_mm:g} mm)"
    )
    e3._save_png(fig, output)


def write_outputs(result: AnalysisResult, output_dir: Path) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    plot_depth_metrics(result.metrics, result.peak_window_index, output_dir / FIGURE_NAMES[0])
    plot_peak_window(result, output_dir / FIGURE_NAMES[1])
    result.metrics.to_csv(output_dir / TABLE_NAMES[0], index=False)
    result.summary.to_csv(output_dir / TABLE_NAMES[1], index=False)
    for name, values in zip(
        ARRAY_NAMES,
        (result.defect_windows, result.front_windows, result.residual_windows),
        strict=True,
    ):
        np.save(output_dir / name, np.asarray(values, dtype=np.float64), allow_pickle=False)
    validate_outputs(output_dir)


def validate_outputs(output_dir: Path) -> None:
    actual = {path.name for path in output_dir.iterdir() if path.is_file()}
    directories = {path.name for path in output_dir.iterdir() if path.is_dir()}
    if actual != set(OUTPUT_NAMES) or not directories.issubset({ROI_CNR_SUBDIRECTORY}):
        raise AssertionError(
            "real-data E3 output mismatch: expected the frozen files and optional "
            f"{ROI_CNR_SUBDIRECTORY}/; files={sorted(actual)}, directories={sorted(directories)}"
        )
    metrics = pd.read_csv(output_dir / TABLE_NAMES[0])
    summary = pd.read_csv(output_dir / TABLE_NAMES[1])
    if tuple(metrics.columns) != WINDOW_COLUMNS or len(metrics) != 64:
        raise AssertionError("real-data window metrics schema or row contract failed")
    if tuple(summary.columns) != SUMMARY_COLUMNS or len(summary) != 1:
        raise AssertionError("real-data summary schema or row contract failed")
    numeric_metrics = metrics.drop(columns="inside_target_slice_range").to_numpy(dtype=float)
    if not np.isfinite(numeric_metrics).all():
        raise AssertionError("real-data window metrics contain non-finite values")
    output_shape = (
        int(summary.iloc[0].output_window_count),
        int(summary.iloc[0].output_y),
        int(summary.iloc[0].output_x),
    )
    arrays = [np.load(output_dir / name, allow_pickle=False) for name in ARRAY_NAMES]
    if any(values.shape != output_shape or values.dtype != np.float64 for values in arrays):
        raise AssertionError("real-data NPY shape or dtype contract failed")
    if not np.array_equal(arrays[2], arrays[0] - arrays[1]):
        raise AssertionError("saved residual NPY does not equal defect minus front")
    if not np.allclose(
        metrics.residual_count.to_numpy(dtype=float),
        arrays[2].sum(axis=(1, 2), dtype=np.float64),
        rtol=1e-12,
        atol=1e-8,
    ):
        raise AssertionError("residual NPY totals do not match the metrics table")
    for name in FIGURE_NAMES:
        if (output_dir / name).read_bytes()[:8] != b"\x89PNG\r\n\x1a\n":
            raise AssertionError(f"real-data E3 figure is not a PNG: {name}")


def publish(staging: Path, output_dir: Path, overwrite: bool) -> None:
    if output_dir.exists():
        if not overwrite:
            raise FileExistsError(f"real-data E3 output exists; pass --overwrite: {output_dir}")
        backup = output_dir.parent / f".{output_dir.name}.backup"
        if backup.exists():
            raise FileExistsError(f"stale real-data E3 backup blocks overwrite: {backup}")
        owned_analysis = output_dir / ROI_CNR_SUBDIRECTORY
        if owned_analysis.is_dir():
            shutil.copytree(owned_analysis, staging / ROI_CNR_SUBDIRECTORY)
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


def run_analysis(real_data_root: Path, output_dir: Path) -> AnalysisResult:
    defect = load_count_volume(real_data_root / DEFECT_FILE_NAME, "defect")
    front = load_count_volume(real_data_root / FRONT_FILE_NAME, "front")
    result = analyze_volumes(defect, front)
    write_outputs(result, output_dir)
    return result


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--real-data-root", type=Path, default=Path("results/real_data"))
    parser.add_argument("--results-root", type=Path, default=Path("results/articlev3_merged"))
    parser.add_argument("--output-dir", type=Path)
    parser.add_argument("--overwrite", action="store_true")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    real_data_root = args.real_data_root.resolve()
    results_root = args.results_root.resolve()
    e3_root = (results_root / "postprocessing" / "E3").resolve()
    supplementary_root = (e3_root / e3.SUPPLEMENTARY_DIR_NAME).resolve()
    output_dir = (
        args.output_dir.resolve()
        if args.output_dir is not None
        else supplementary_root / DEFAULT_SUBDIRECTORY
    )
    protected = {real_data_root, results_root, e3_root, supplementary_root}
    if output_dir in protected:
        raise ValueError("real-data output directory must not replace an input or E3 root")
    output_dir.parent.mkdir(parents=True, exist_ok=True)
    staging = Path(tempfile.mkdtemp(prefix=f".{output_dir.name}.staging-", dir=output_dir.parent))
    try:
        result = run_analysis(real_data_root, staging)
        publish(staging, output_dir, args.overwrite)
    except Exception:
        shutil.rmtree(staging, ignore_errors=True)
        raise

    peak = result.summary.iloc[0]
    print(f"real-data E3 output: {output_dir}")
    print(f"input shapes: defect={result.defect_input_shape}, front={result.front_input_shape}")
    print(f"windowed shape: {result.defect_windows.shape}")
    print(
        "selected target window: "
        f"[{int(peak.peak_window_start_index)}, {int(peak.peak_window_end_index_exclusive)}) mm, "
        f"center={peak.peak_z_center_mm:g} mm"
    )
    print(
        f"selected counts: D={peak.peak_defect_count:.6g}, "
        f"F={peak.peak_front_count:.6g}, R={peak.peak_residual_count:.6g}"
    )
    print("files: 2 PNG + 2 CSV + 3 NPY")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as error:
        print(f"real-data E3 analysis error: {error}", file=sys.stderr)
        raise SystemExit(1) from error
