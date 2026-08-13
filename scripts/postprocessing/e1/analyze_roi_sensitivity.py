#!/usr/bin/env python3
"""Analyze detector-x ROI sensitivity inside frozen articlev2 slit channels."""

from __future__ import annotations

import argparse
import hashlib
import math
import os
import shutil
import sys
import tempfile
import uuid
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

os.environ.setdefault("MPLCONFIGDIR", "/tmp/mss_matplotlib")
try:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    import numpy as np
    import pandas as pd
    import yaml
    from matplotlib.lines import Line2D
except ModuleNotFoundError as error:  # pragma: no cover - CLI environment guard.
    raise RuntimeError(
        "articlev2 ROI sensitivity analysis requires pandas/numpy/matplotlib/PyYAML. "
        "Run `conda activate data` or use `conda run -n data python ...`."
    ) from error

from scripts.data_processing.common import (
    DETECTOR_Y_RANGE_ZERO_MM,
    PROFILE_SLITS,
    SLIT_GROUP_COLUMN,
    SLIT_LABEL_COLUMN,
    SLIT_PROFILE,
    SLIT_WINDOWS_ZERO_MM,
    RunMetadata,
    discover_event_files,
    metadata_for_events,
    read_yaml,
    to_builtin,
)
from scripts.data_processing.experiment_contract import SLIT_DESIGN_DEPTH_MM, TARGET_HALF_WIDTH_MM
from scripts.data_processing.estimate_slit_boundaries import BOUNDARY_CONFIG_NAME
from scripts.data_processing.slit_channels import load_boundary_config, profile_boundaries


EVENTS_NAME = "events_valid.csv"
VALID_MANIFEST_NAME = "valid_events_manifest.yaml"
METRICS_NAME = "roi_sensitivity_metrics.csv"
ANALYSIS_MANIFEST_NAME = "analysis_manifest.yaml"
LAMBDA_VALUES = (0.0, 0.2, 0.4, 0.6, 0.8, 1.0)
FIGURE_NAMES = (
    "ms_purity_vs_roi_expansion.png",
    "target_ms_capture_vs_roi_expansion.png",
    "ms_purity_capture_tradeoff.png",
    "ms_raw_counts_vs_roi_expansion.png",
    "incremental_ms_purity_vs_roi_expansion.png",
    "k1_purity_vs_roi_expansion.png",
)
METRIC_COLUMNS = (
    "run_group", "slit_label", "lambda",
    "roi_x_min", "roi_x_max", "roi_width", "roi_y_min", "roi_y_max",
    "N_ms_target", "N_ms_nontarget", "N_ms_total",
    "P_target_ms", "capture_eff_target_ms", "incremental_P_target_ms",
    "N_k1_target", "N_k1_total", "P_target_k1",
)
REQUIRED_EVENT_COLUMNS = {
    "det_x", "det_y", "scatter_count_total", "first_scatter_z",
    SLIT_GROUP_COLUMN, SLIT_LABEL_COLUMN,
}
COLORS = {
    "S1": "#0072B2", "S2": "#D55E00", "S3": "#009E73",
    "S4": "#CC79A7", "S5": "#E69F00", "S6": "#56B4E9",
}
LAMBDA_MARKERS = ("o", "s", "^", "D", "P", "X")


@dataclass(frozen=True)
class RoiBounds:
    slit_label: str
    lambda_value: float
    x_min_mm: float
    x_max_mm: float
    y_min_mm: float
    y_max_mm: float

    @property
    def width_mm(self) -> float:
        return self.x_max_mm - self.x_min_mm


@dataclass(frozen=True)
class RunInput:
    events_path: Path
    metadata: RunMetadata
    detector_x_range_mm: tuple[float, float]
    detector_y_range_mm: tuple[float, float]
    row_count: int


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def safe_ratio(numerator: int | float, denominator: int | float) -> float:
    return float(numerator / denominator) if denominator else math.nan


def detector_range(metadata: RunMetadata, field: str) -> tuple[float, float]:
    value = metadata.raw.get("detector", {}).get(field)
    if not isinstance(value, (list, tuple)) or len(value) != 2:
        raise ValueError(
            f"metadata detector.{field} must contain two values: {metadata.metadata_path}"
        )
    low, high = (float(item) for item in value)
    if not (math.isfinite(low) and math.isfinite(high) and low < high):
        raise ValueError(f"metadata detector.{field} is invalid: {metadata.metadata_path}")
    return low, high


def config_detector_x_range(
    boundary_config: dict[str, Any], profile_id: str,
) -> tuple[float, float]:
    value = boundary_config["profiles"][profile_id].get("detector_x_range_mm")
    if not isinstance(value, list) or len(value) != 2:
        raise ValueError(
            f"boundary config profile {profile_id} must contain detector_x_range_mm"
        )
    low, high = (float(item) for item in value)
    if not (math.isfinite(low) and math.isfinite(high) and low < high):
        raise ValueError(f"invalid detector_x_range_mm for {profile_id}: {value!r}")
    return low, high


def maximum_channel_range(
    boundary_config: dict[str, Any], profile_id: str, slit_label: str,
) -> tuple[float, float]:
    slits = PROFILE_SLITS[profile_id]
    if slit_label not in slits:
        raise ValueError(f"slit {slit_label} does not belong to {profile_id}")
    detector_min, detector_max = config_detector_x_range(boundary_config, profile_id)
    boundary_1, boundary_2 = profile_boundaries(boundary_config, profile_id)
    edges = (detector_min, boundary_1, boundary_2, detector_max)
    index = slits.index(slit_label)
    return edges[index], edges[index + 1]


def roi_bounds_for_slit(
    slit_label: str,
    channel_x_range_mm: tuple[float, float],
    lambda_values: tuple[float, ...] = LAMBDA_VALUES,
) -> tuple[RoiBounds, ...]:
    window = SLIT_WINDOWS_ZERO_MM[slit_label]
    channel_min, channel_max = channel_x_range_mm
    if not channel_min <= window.left_mm <= window.right_mm <= channel_max:
        raise ValueError(
            f"geometric ROI for {slit_label} is outside maximum channel "
            f"{channel_x_range_mm}: {(window.left_mm, window.right_mm)}"
        )
    left_distance = window.left_mm - channel_min
    right_distance = channel_max - window.right_mm
    maximum_distance = max(left_distance, right_distance)
    y_min, y_max = DETECTOR_Y_RANGE_ZERO_MM
    bounds: list[RoiBounds] = []
    for lambda_value in lambda_values:
        if not math.isfinite(lambda_value) or not 0.0 <= lambda_value <= 1.0:
            raise ValueError(f"lambda must be finite and within [0,1]: {lambda_value}")
        dilation = lambda_value * maximum_distance
        bounds.append(RoiBounds(
            slit_label=slit_label,
            lambda_value=lambda_value,
            x_min_mm=max(window.left_mm - dilation, channel_min),
            x_max_mm=min(window.right_mm + dilation, channel_max),
            y_min_mm=y_min,
            y_max_mm=y_max,
        ))
    first, last = bounds[0], bounds[-1]
    if not (
        math.isclose(first.x_min_mm, window.left_mm)
        and math.isclose(first.x_max_mm, window.right_mm)
        and math.isclose(last.x_min_mm, channel_min)
        and math.isclose(last.x_max_mm, channel_max)
    ):
        raise AssertionError(f"ROI endpoint contract failed for {slit_label}")
    return tuple(bounds)


def expected_slit_labels(
    detector_x: pd.Series, profile_id: str, boundaries: tuple[float, float],
) -> pd.Series:
    left, right = boundaries
    slits = PROFILE_SLITS[profile_id]
    values = np.where(detector_x < left, slits[0], np.where(detector_x < right, slits[1], slits[2]))
    return pd.Series(values, index=detector_x.index, dtype="object")


def validate_valid_manifest(valid_root: Path, boundary_path: Path) -> tuple[Path, dict[str, Any]]:
    manifest_path = valid_root / VALID_MANIFEST_NAME
    manifest = read_yaml(manifest_path)
    expected_hash = manifest.get("boundary_config_sha256")
    actual_hash = sha256_file(boundary_path)
    if expected_hash != actual_hash:
        raise ValueError(
            "valid-events boundary hash does not match the selected frozen config: "
            f"manifest={expected_hash!r}, actual={actual_hash!r}"
        )
    if manifest.get("output_name") != EVENTS_NAME:
        raise ValueError(f"valid-events manifest output_name must be {EVENTS_NAME}")
    return manifest_path, manifest


def discover_inputs(
    valid_root: Path, boundary_config: dict[str, Any],
) -> tuple[dict[str, RunInput], dict[str, pd.DataFrame]]:
    input_root = valid_root / "center" / "P0"
    files = discover_event_files(input_root, EVENTS_NAME)
    if len(files) != 2:
        raise ValueError(f"expected exactly two P0 center valid-event files, found {len(files)}")

    inputs: dict[str, RunInput] = {}
    frames: dict[str, pd.DataFrame] = {}
    for events_path in files:
        metadata = metadata_for_events(events_path)
        profile_id = metadata.profile_id
        if profile_id in inputs:
            raise ValueError(f"duplicate P0 center valid-event run for {profile_id}")
        if (
            metadata.scan_mode != "center" or metadata.phantom_id != "P0"
            or not math.isclose(metadata.energy_keV, 560.0)
            or not math.isclose(metadata.head_offset_x_mm, 0.0)
            or not math.isclose(metadata.head_offset_y_mm, 0.0)
        ):
            raise ValueError(f"unexpected ROI-sensitivity input metadata: {metadata.metadata_path}")
        x_range = detector_range(metadata, "actual_x_range_mm")
        y_range = detector_range(metadata, "actual_y_range_mm")
        if not np.allclose(x_range, config_detector_x_range(boundary_config, profile_id)):
            raise ValueError(f"metadata and boundary-config detector x ranges differ for {profile_id}")
        if not np.allclose(y_range, DETECTOR_Y_RANGE_ZERO_MM):
            raise ValueError(f"metadata detector y range differs from geometric ROI for {profile_id}")

        frame = pd.read_csv(events_path, low_memory=False)
        missing = sorted(REQUIRED_EVENT_COLUMNS.difference(frame.columns))
        if missing:
            raise ValueError(f"events CSV is missing required columns {missing}: {events_path}")
        frame = frame.copy()
        for column in ("det_x", "det_y", "scatter_count_total", "first_scatter_z"):
            frame[column] = pd.to_numeric(frame[column], errors="coerce")
        coordinates = frame[["det_x", "det_y", "first_scatter_z"]].to_numpy(dtype=float)
        if not np.isfinite(coordinates).all():
            raise ValueError(f"valid events contain non-finite coordinates: {events_path}")
        scatter = frame["scatter_count_total"].to_numpy(dtype=float)
        if not np.isfinite(scatter).all() or (scatter < 0).any() or not np.equal(scatter, np.floor(scatter)).all():
            raise ValueError(f"scatter_count_total must contain non-negative integers: {events_path}")
        if (frame["first_scatter_z"] < 0).any():
            raise ValueError(f"valid events contain negative first_scatter_z: {events_path}")
        if not frame["det_x"].between(*x_range, inclusive="both").all():
            raise ValueError(f"valid events contain detector x outside active area: {events_path}")
        if not frame["det_y"].between(*y_range, inclusive="both").all():
            raise ValueError(f"valid events contain detector y outside active area: {events_path}")
        if set(frame[SLIT_GROUP_COLUMN].astype(str)) != {profile_id}:
            raise ValueError(f"slit_group does not match metadata profile in {events_path}")
        actual_labels = frame[SLIT_LABEL_COLUMN].astype(str)
        invalid_labels = sorted(set(actual_labels).difference(PROFILE_SLITS[profile_id]))
        if invalid_labels:
            raise ValueError(f"invalid slit_label values {invalid_labels} in {events_path}")
        expected = expected_slit_labels(
            frame["det_x"], profile_id, profile_boundaries(boundary_config, profile_id)
        )
        mismatches = actual_labels != expected
        if mismatches.any():
            raise ValueError(
                f"frozen slit_label differs from boundary config for {int(mismatches.sum())} "
                f"hit(s): {events_path}"
            )
        frame[SLIT_LABEL_COLUMN] = actual_labels
        inputs[profile_id] = RunInput(events_path, metadata, x_range, y_range, len(frame))
        frames[profile_id] = frame

    if set(inputs) != set(PROFILE_SLITS):
        raise ValueError(f"P0 center inputs must cover exactly {tuple(PROFILE_SLITS)}")
    return inputs, frames


def analyze(
    frames: dict[str, pd.DataFrame], boundary_config: dict[str, Any],
) -> tuple[pd.DataFrame, dict[str, Any], dict[str, tuple[RoiBounds, ...]]]:
    rows: list[dict[str, Any]] = []
    checks: dict[str, Any] = {}
    all_bounds: dict[str, tuple[RoiBounds, ...]] = {}

    for slit_label in sorted(SLIT_PROFILE, key=lambda value: int(value[1:])):
        profile_id = SLIT_PROFILE[slit_label]
        frame = frames[profile_id]
        channel_range = maximum_channel_range(boundary_config, profile_id, slit_label)
        bounds = roi_bounds_for_slit(slit_label, channel_range)
        all_bounds[slit_label] = bounds
        label_mask = frame[SLIT_LABEL_COLUMN] == slit_label
        scatter = frame["scatter_count_total"]
        target_center = SLIT_DESIGN_DEPTH_MM[slit_label]
        target_min = target_center - TARGET_HALF_WIDTH_MM
        target_max = target_center + TARGET_HALF_WIDTH_MM
        target_mask = (frame["first_scatter_z"] >= target_min) & (frame["first_scatter_z"] < target_max)
        ms_mask = scatter >= 2
        k1_mask = scatter == 1
        roi_masks: list[pd.Series] = []
        slit_rows: list[dict[str, Any]] = []

        for roi in bounds:
            roi_mask = (
                label_mask
                & frame["det_x"].between(roi.x_min_mm, roi.x_max_mm, inclusive="both")
                & frame["det_y"].between(roi.y_min_mm, roi.y_max_mm, inclusive="both")
            )
            roi_masks.append(roi_mask)
            n_ms_target = int((roi_mask & ms_mask & target_mask).sum())
            n_ms_total = int((roi_mask & ms_mask).sum())
            n_ms_nontarget = n_ms_total - n_ms_target
            n_k1_target = int((roi_mask & k1_mask & target_mask).sum())
            n_k1_total = int((roi_mask & k1_mask).sum())
            slit_rows.append({
                "run_group": profile_id,
                "slit_label": slit_label,
                "lambda": roi.lambda_value,
                "roi_x_min": roi.x_min_mm,
                "roi_x_max": roi.x_max_mm,
                "roi_width": roi.width_mm,
                "roi_y_min": roi.y_min_mm,
                "roi_y_max": roi.y_max_mm,
                "N_ms_target": n_ms_target,
                "N_ms_nontarget": n_ms_nontarget,
                "N_ms_total": n_ms_total,
                "P_target_ms": safe_ratio(n_ms_target, n_ms_total),
                "capture_eff_target_ms": math.nan,
                "incremental_P_target_ms": math.nan,
                "N_k1_target": n_k1_target,
                "N_k1_total": n_k1_total,
                "P_target_k1": safe_ratio(n_k1_target, n_k1_total),
            })

        reference_target = slit_rows[-1]["N_ms_target"]
        for index, row in enumerate(slit_rows):
            row["capture_eff_target_ms"] = safe_ratio(row["N_ms_target"], reference_target)
            if index:
                previous = slit_rows[index - 1]
                row["incremental_P_target_ms"] = safe_ratio(
                    row["N_ms_target"] - previous["N_ms_target"],
                    row["N_ms_total"] - previous["N_ms_total"],
                )

        roi_nested = all(
            current.x_min_mm <= previous.x_min_mm
            and current.x_max_mm >= previous.x_max_mm
            and current.y_min_mm <= previous.y_min_mm
            and current.y_max_mm >= previous.y_max_mm
            for previous, current in zip(bounds, bounds[1:])
        )
        mask_nested = all(
            not bool((previous & ~current).any())
            for previous, current in zip(roi_masks, roi_masks[1:])
        )
        target_counts = [row["N_ms_target"] for row in slit_rows]
        total_counts = [row["N_ms_total"] for row in slit_rows]
        partition = all(
            row["N_ms_target"] + row["N_ms_nontarget"] == row["N_ms_total"]
            for row in slit_rows
        )
        lambda1_coverage = bool((roi_masks[-1] == label_mask).all())
        lambda1_capture = (
            math.isnan(slit_rows[-1]["capture_eff_target_ms"])
            if reference_target == 0
            else math.isclose(slit_rows[-1]["capture_eff_target_ms"], 1.0)
        )
        slit_check = {
            "roi_nested": roi_nested,
            "mask_nested": mask_nested,
            "ms_target_monotonic": all(a <= b for a, b in zip(target_counts, target_counts[1:])),
            "ms_total_monotonic": all(a <= b for a, b in zip(total_counts, total_counts[1:])),
            "ms_partition": partition,
            "lambda1_channel_coverage": lambda1_coverage,
            "lambda1_capture": lambda1_capture,
            "capture_reference_target_count": reference_target,
            "slit_label_stable": True,
        }
        failed = [key for key, value in slit_check.items() if isinstance(value, bool) and not value]
        if failed:
            raise AssertionError(f"ROI sensitivity checks failed for {slit_label}: {failed}")
        checks[slit_label] = slit_check
        rows.extend(slit_rows)

    metrics = pd.DataFrame(rows, columns=METRIC_COLUMNS)
    if len(metrics) != len(SLIT_PROFILE) * len(LAMBDA_VALUES):
        raise AssertionError("ROI sensitivity output row-count contract failed")
    return metrics, checks, all_bounds


def plot_lines(
    metrics: pd.DataFrame, column: str, ylabel: str, title: str, path: Path,
) -> None:
    fig, ax = plt.subplots(figsize=(9.2, 5.8), constrained_layout=True)
    for slit_label in sorted(SLIT_PROFILE, key=lambda value: int(value[1:])):
        data = metrics[metrics["slit_label"] == slit_label]
        ax.plot(data["lambda"], data[column], marker="o", linewidth=1.7,
                color=COLORS[slit_label], label=slit_label)
    ax.set(xlabel="ROI expansion λ", ylabel=ylabel, title=title)
    ax.set_xticks(LAMBDA_VALUES)
    ax.grid(alpha=0.25)
    ax.legend(ncol=3)
    fig.savefig(path, dpi=220)
    plt.close(fig)


def write_figures(metrics: pd.DataFrame, output_dir: Path) -> None:
    plot_lines(metrics, "P_target_ms", "Target-source MS purity",
               "MS purity versus ROI expansion", output_dir / FIGURE_NAMES[0])
    plot_lines(metrics, "capture_eff_target_ms", "Target-source MS capture efficiency",
               "Target-MS capture versus ROI expansion", output_dir / FIGURE_NAMES[1])

    fig, ax = plt.subplots(figsize=(9.2, 6.2), constrained_layout=True)
    for slit_label in sorted(SLIT_PROFILE, key=lambda value: int(value[1:])):
        data = metrics[metrics["slit_label"] == slit_label]
        ax.plot(data["capture_eff_target_ms"], data["P_target_ms"],
                linewidth=1.7, color=COLORS[slit_label], label=slit_label)
        for marker, (_, row) in zip(LAMBDA_MARKERS, data.iterrows(), strict=True):
            ax.scatter(row["capture_eff_target_ms"], row["P_target_ms"], marker=marker,
                       s=44, color=COLORS[slit_label], edgecolor="white", linewidth=0.45,
                       zorder=3)
    ax.set(xlabel="Target-source MS capture efficiency", ylabel="Target-source MS purity",
           title="MS purity–capture trade-off")
    ax.grid(alpha=0.25)
    slit_legend = ax.legend(ncol=3, loc="upper right", title="Slit")
    ax.add_artist(slit_legend)
    lambda_handles = [
        Line2D([0], [0], marker=marker, linestyle="none", markerfacecolor="#555555",
               markeredgecolor="white", markersize=7, label=f"{lambda_value:g}")
        for lambda_value, marker in zip(LAMBDA_VALUES, LAMBDA_MARKERS, strict=True)
    ]
    ax.legend(handles=lambda_handles, ncol=3, loc="lower left", title="λ")
    fig.savefig(output_dir / FIGURE_NAMES[2], dpi=220)
    plt.close(fig)

    fig, axes = plt.subplots(2, 3, figsize=(14.2, 8.4), constrained_layout=True, sharex=True)
    for ax, slit_label in zip(axes.ravel(), sorted(SLIT_PROFILE, key=lambda value: int(value[1:])), strict=True):
        data = metrics[metrics["slit_label"] == slit_label]
        ax.plot(data["lambda"], data["N_ms_target"], marker="o", label="target")
        ax.plot(data["lambda"], data["N_ms_nontarget"], marker="s", label="non-target")
        ax.plot(data["lambda"], data["N_ms_total"], marker="^", label="total")
        ax.set_title(slit_label)
        ax.set_xticks(LAMBDA_VALUES)
        ax.grid(alpha=0.25)
    axes[1, 0].set_xlabel("ROI expansion λ")
    axes[1, 1].set_xlabel("ROI expansion λ")
    axes[1, 2].set_xlabel("ROI expansion λ")
    axes[0, 0].set_ylabel("MS count")
    axes[1, 0].set_ylabel("MS count")
    axes[0, 0].legend()
    fig.suptitle("Target / non-target / total MS raw counts")
    fig.savefig(output_dir / FIGURE_NAMES[3], dpi=220)
    plt.close(fig)

    plot_lines(metrics, "incremental_P_target_ms", "Incremental target-source MS purity",
               "Incremental MS purity", output_dir / FIGURE_NAMES[4])
    plot_lines(metrics, "P_target_k1", "Target-source k1 purity",
               "k1 purity versus ROI expansion", output_dir / FIGURE_NAMES[5])


def write_manifest(
    path: Path,
    results_root: Path,
    valid_manifest_path: Path,
    valid_manifest: dict[str, Any],
    boundary_path: Path,
    inputs: dict[str, RunInput],
    bounds: dict[str, tuple[RoiBounds, ...]],
    checks: dict[str, Any],
) -> None:
    def campaign_path(value: Path) -> str:
        try:
            return value.resolve().relative_to(results_root.resolve()).as_posix()
        except ValueError:
            return value.resolve().as_posix()

    manifest = {
        "schema_version": 1,
        "analysis": "fixed_slit_channel_roi_sensitivity",
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "results_root": ".",
        "input_layer": "valid_events",
        "valid_events_manifest": campaign_path(valid_manifest_path),
        "valid_events_manifest_sha256": sha256_file(valid_manifest_path),
        "valid_events_depth_filter": valid_manifest.get("depth_filter"),
        "boundary_config": campaign_path(boundary_path),
        "boundary_config_sha256": sha256_file(boundary_path),
        "slit_identity_rule": "use existing slit_label; boundary-derived labels are validation only",
        "lambda_values": LAMBDA_VALUES,
        "roi_interval_rule": "closed in detector x and y",
        "target_interval_rule": "left-closed-right-open: center-5 <= first_scatter_z < center+5",
        "scatter_classes": {"k1": "scatter_count_total == 1", "ms": "scatter_count_total >= 2"},
        "zero_denominator_rule": "NaN",
        "inputs": {
            profile_id: {
                "events_file": campaign_path(item.events_path),
                "metadata_file": campaign_path(item.metadata.metadata_path),
                "row_count": item.row_count,
                "n_primary": item.metadata.n_primary,
                "detector_x_range_mm": item.detector_x_range_mm,
                "detector_y_range_mm": item.detector_y_range_mm,
            }
            for profile_id, item in inputs.items()
        },
        "roi_bounds": {
            slit_label: [asdict(item) for item in slit_bounds]
            for slit_label, slit_bounds in bounds.items()
        },
        "quality_checks": {"all_passed": True, "by_slit": checks},
        "outputs": [METRICS_NAME, *FIGURE_NAMES, ANALYSIS_MANIFEST_NAME],
    }
    path.write_text(
        yaml.safe_dump(to_builtin(manifest), sort_keys=False, allow_unicode=True, width=110),
        encoding="utf-8",
    )


def build_outputs(
    results_root: Path, boundary_path: Path, staging: Path,
) -> pd.DataFrame:
    valid_root = results_root / "events" / "valid"
    valid_manifest_path, valid_manifest = validate_valid_manifest(valid_root, boundary_path)
    boundary_config = load_boundary_config(boundary_path)
    inputs, frames = discover_inputs(valid_root, boundary_config)
    metrics, checks, bounds = analyze(frames, boundary_config)
    metrics.to_csv(staging / METRICS_NAME, index=False, columns=METRIC_COLUMNS, na_rep="NaN")
    write_figures(metrics, staging)
    write_manifest(
        staging / ANALYSIS_MANIFEST_NAME, results_root, valid_manifest_path, valid_manifest,
        boundary_path, inputs, bounds, checks,
    )
    expected = {METRICS_NAME, ANALYSIS_MANIFEST_NAME, *FIGURE_NAMES}
    actual = {path.name for path in staging.iterdir() if path.is_file()}
    if actual != expected:
        raise AssertionError(f"ROI sensitivity output contract failed: {sorted(actual)}")
    return metrics


def publish(staging: Path, output_dir: Path, overwrite: bool) -> None:
    if output_dir.exists():
        if not overwrite:
            raise FileExistsError(f"output directory exists; pass --overwrite: {output_dir}")
        backup = output_dir.parent / f".{output_dir.name}.backup-{uuid.uuid4().hex}"
        output_dir.replace(backup)
        try:
            staging.replace(output_dir)
        except Exception:
            backup.replace(output_dir)
            raise
        shutil.rmtree(backup)
    else:
        staging.replace(output_dir)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--results-root", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path)
    parser.add_argument("--boundary-config", type=Path)
    parser.add_argument("--overwrite", action="store_true")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    results_root = args.results_root.resolve()
    output_dir = (
        args.output_dir or results_root / "postprocessing" / "E1" / "roi_sensitivity"
    ).resolve()
    boundary_path = (
        args.boundary_config
        or results_root / "data_processing" / "slit_channels" / BOUNDARY_CONFIG_NAME
    ).resolve()
    valid_root = (results_root / "events" / "valid").resolve()
    if output_dir in {results_root, valid_root}:
        raise ValueError("output directory must not replace results_root or valid_events")
    if output_dir.exists() and not args.overwrite:
        raise FileExistsError(f"output directory exists; pass --overwrite: {output_dir}")
    output_dir.parent.mkdir(parents=True, exist_ok=True)
    staging = Path(tempfile.mkdtemp(prefix=f".{output_dir.name}.staging-", dir=output_dir.parent))
    try:
        metrics = build_outputs(results_root, boundary_path, staging)
        publish(staging, output_dir, args.overwrite)
    except Exception:
        shutil.rmtree(staging, ignore_errors=True)
        raise
    print(f"ROI sensitivity rows: {len(metrics)}")
    print(f"metrics: {output_dir / METRICS_NAME}")
    print(f"manifest: {output_dir / ANALYSIS_MANIFEST_NAME}")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as error:
        print(f"error: {error}", file=sys.stderr)
        raise SystemExit(1) from error
