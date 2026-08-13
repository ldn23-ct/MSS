#!/usr/bin/env python3
"""Estimate and freeze P001/P002 detector-x slit-channel boundaries."""

from __future__ import annotations

import argparse
import csv
import json
import os
import shutil
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

os.environ.setdefault("MPLCONFIGDIR", "/tmp/mss_matplotlib")
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from matplotlib.colors import LogNorm

from .slit_channels import (
    PROFILE_BOUNDARY_KEYS,
    BoundaryAlgorithmConfig,
    BoundaryEstimationError,
    DetectionResult,
    ProfileBoundaryEstimate,
    boundary_config_payload,
    discover_baseline_files,
    estimate_slit_boundaries,
    read_detector_coordinates,
)


BOUNDARY_CONFIG_NAME = "slit_channel_boundaries.json"


def save_figure(fig: plt.Figure, base: Path) -> None:
    fig.savefig(base.with_suffix(".png"), dpi=300, bbox_inches="tight")
    plt.close(fig)


def plot_detector_x(
    profile_id: str,
    slit_order: tuple[str, ...],
    detection: DetectionResult,
    output_dir: Path,
    *,
    failure_title: str = "",
) -> None:
    fig, axis = plt.subplots(figsize=(11, 5.8), constrained_layout=True)
    axis.stairs(
        detection.raw_counts,
        detection.bin_edges_mm,
        color="#737373",
        alpha=0.55,
        fill=True,
        label="Raw detector-x histogram",
    )
    axis.plot(
        detection.bin_centers_mm,
        detection.smooth_density,
        color="#0072B2",
        linewidth=1.8,
        label=f"Gaussian-smoothed density (sigma={detection.smoothing_sigma_mm:g} mm)",
    )
    if len(detection.candidate_peak_indices):
        axis.scatter(
            detection.peak_x_mm,
            detection.smooth_density[detection.candidate_peak_indices],
            marker="^",
            s=60,
            color="#D55E00",
            zorder=4,
            label=f"Candidate peaks ({len(detection.candidate_peak_indices)})",
        )
    for index, valley in enumerate(detection.valleys):
        left_slit, right_slit = slit_order[index : index + 2]
        axis.axvspan(
            detection.bin_centers_mm[valley.plateau_left_index],
            detection.bin_centers_mm[valley.plateau_right_index],
            color="#009E73",
            alpha=0.15,
        )
        axis.axvline(valley.boundary_x_mm, color="#009E73", linestyle="--", linewidth=1.6)
        axis.annotate(
            f"{left_slit}/{right_slit} boundary = {valley.boundary_x_mm:.2f} mm",
            (valley.boundary_x_mm, axis.get_ylim()[1] * (0.84 - index * 0.11)),
            xytext=(5, 0),
            textcoords="offset points",
            rotation=90,
            va="top",
            color="#006B4F",
            fontsize=9,
        )
    if len(detection.candidate_peak_indices) == len(slit_order):
        for slit, peak_x, peak_index in zip(
            slit_order, detection.peak_x_mm, detection.candidate_peak_indices
        ):
            axis.annotate(
                f"{slit}\n{peak_x:.2f} mm",
                (peak_x, detection.smooth_density[peak_index]),
                xytext=(0, 10),
                textcoords="offset points",
                ha="center",
                fontsize=9,
            )
    title = f"{profile_id} detector-x channel boundary diagnostic"
    if failure_title:
        title += f"\nFAILED: {failure_title}"
    axis.set(title=title, xlabel="Detector x (mm)", ylabel="Hits per bin / smoothed density")
    axis.grid(alpha=0.18)
    axis.legend(loc="upper right", fontsize=8)
    save_figure(fig, output_dir / f"{profile_id}_detector_x_distribution")


def plot_hit_map(
    profile_id: str,
    slit_order: tuple[str, ...],
    x: np.ndarray,
    y: np.ndarray,
    detection: DetectionResult | None,
    output_dir: Path,
    *,
    failure_title: str = "",
) -> None:
    fig, axis = plt.subplots(figsize=(9.5, 6.5), constrained_layout=True)
    histogram = axis.hist2d(x, y, bins=(220, 180), cmap="viridis", norm=LogNorm())
    fig.colorbar(histogram[3], ax=axis, label="Detected hits per 2D bin")
    if detection is not None and len(detection.valleys) == 2:
        edges = [float(x.min()), *detection.boundary_x_mm, float(x.max())]
        for index, boundary in enumerate(detection.boundary_x_mm):
            left_slit, right_slit = slit_order[index : index + 2]
            axis.axvline(boundary, color="#D55E00", linestyle="--", linewidth=2.0)
            axis.text(
                boundary,
                float(y.max()) - 0.025 * float(np.ptp(y)),
                f" {left_slit}/{right_slit}\n {boundary:.2f} mm",
                color="#9B3F00",
                va="top",
                fontsize=9,
                bbox={"facecolor": "white", "edgecolor": "none", "alpha": 0.82, "pad": 1.5},
            )
        for slit, left, right in zip(slit_order, edges, edges[1:]):
            axis.text(
                (left + right) / 2,
                float(y.max()) - 0.08 * float(np.ptp(y)),
                slit,
                color="black",
                ha="center",
                fontsize=11,
                weight="bold",
                bbox={"facecolor": "white", "edgecolor": "none", "alpha": 0.78, "pad": 1.5},
            )
    title = f"{profile_id} raw detector hit density"
    if failure_title:
        title += f"\nFAILED: {failure_title}"
    axis.set(title=title, xlabel="Detector x (mm)", ylabel="Detector y (mm)")
    save_figure(fig, output_dir / f"{profile_id}_detector_hit_map")


def write_histogram_csv(path: Path, estimates: Mapping[str, ProfileBoundaryEstimate]) -> None:
    fields = [
        "group", "bin_left_mm", "bin_right_mm", "bin_center_mm", "raw_count",
        "smooth_density", "is_peak", "is_valley_plateau",
    ]
    with path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        for profile_id, estimate in estimates.items():
            detection = estimate.detection
            peak_indices = set(int(value) for value in detection.candidate_peak_indices)
            plateau_indices = {
                index
                for valley in detection.valleys
                for index in range(valley.plateau_left_index, valley.plateau_right_index + 1)
            }
            for index, center in enumerate(detection.bin_centers_mm):
                writer.writerow({
                    "group": profile_id,
                    "bin_left_mm": detection.bin_edges_mm[index],
                    "bin_right_mm": detection.bin_edges_mm[index + 1],
                    "bin_center_mm": center,
                    "raw_count": int(detection.raw_counts[index]),
                    "smooth_density": detection.smooth_density[index],
                    "is_peak": index in peak_indices,
                    "is_valley_plateau": index in plateau_indices,
                })


def write_boundary_csv(path: Path, estimates: Mapping[str, ProfileBoundaryEstimate]) -> None:
    fields = [
        "group", "left_slit", "right_slit", "boundary_x_mm", "left_peak_x_mm",
        "right_peak_x_mm", "plateau_x_min_mm", "plateau_x_max_mm",
        "minimum_density", "valley_to_peak_ratio",
    ]
    with path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        for profile_id, estimate in estimates.items():
            detection = estimate.detection
            for index, valley in enumerate(detection.valleys):
                writer.writerow({
                    "group": profile_id,
                    "left_slit": estimate.slit_order[index],
                    "right_slit": estimate.slit_order[index + 1],
                    "boundary_x_mm": valley.boundary_x_mm,
                    "left_peak_x_mm": detection.peak_x_mm[index],
                    "right_peak_x_mm": detection.peak_x_mm[index + 1],
                    "plateau_x_min_mm": detection.bin_centers_mm[valley.plateau_left_index],
                    "plateau_x_max_mm": detection.bin_centers_mm[valley.plateau_right_index],
                    "minimum_density": valley.minimum_density,
                    "valley_to_peak_ratio": valley.valley_to_peak_ratio,
                })


def write_stability_csv(path: Path, estimates: Mapping[str, ProfileBoundaryEstimate]) -> None:
    fields = [
        "group", "smoothing_factor", "smoothing_sigma_mm", "bin_origin_offset_bins",
        "peak_1_x_mm", "peak_2_x_mm", "peak_3_x_mm", "boundary_1_x_mm",
        "boundary_2_x_mm", "maximum_peak_shift_mm", "maximum_boundary_shift_mm",
        "passed", "error",
    ]
    with path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        for profile_id, estimate in estimates.items():
            base_sigma = estimate.detection.smoothing_sigma_mm
            for row in estimate.stability:
                peaks = list(row.peak_x_mm) + [""] * (3 - len(row.peak_x_mm))
                boundaries = list(row.boundary_x_mm) + [""] * (2 - len(row.boundary_x_mm))
                writer.writerow({
                    "group": profile_id,
                    "smoothing_factor": row.smoothing_factor,
                    "smoothing_sigma_mm": base_sigma * row.smoothing_factor,
                    "bin_origin_offset_bins": row.bin_origin_offset,
                    "peak_1_x_mm": peaks[0],
                    "peak_2_x_mm": peaks[1],
                    "peak_3_x_mm": peaks[2],
                    "boundary_1_x_mm": boundaries[0],
                    "boundary_2_x_mm": boundaries[1],
                    "maximum_peak_shift_mm": row.maximum_peak_shift_mm,
                    "maximum_boundary_shift_mm": row.maximum_boundary_shift_mm,
                    "passed": row.passed,
                    "error": row.error,
                })


def baseline_labels(
    x: np.ndarray, estimate: ProfileBoundaryEstimate
) -> np.ndarray:
    left, right = estimate.detection.boundary_x_mm
    return np.where(
        x < left,
        estimate.slit_order[0],
        np.where(x < right, estimate.slit_order[1], estimate.slit_order[2]),
    )


def write_channel_summary_csv(
    path: Path,
    estimates: Mapping[str, ProfileBoundaryEstimate],
    coordinates: Mapping[str, tuple[np.ndarray, np.ndarray]],
) -> None:
    fields = ["group", "slit", "x_min_mm", "x_max_mm", "hit_count", "fraction"]
    with path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        for profile_id, estimate in estimates.items():
            x = coordinates[profile_id][0]
            labels = baseline_labels(x, estimate)
            boundaries = estimate.detection.boundary_x_mm
            limits = [estimate.detector_x_range_mm[0], *boundaries, estimate.detector_x_range_mm[1]]
            for index, slit in enumerate(estimate.slit_order):
                count = int(np.count_nonzero(labels == slit))
                writer.writerow({
                    "group": profile_id,
                    "slit": slit,
                    "x_min_mm": limits[index],
                    "x_max_mm": limits[index + 1],
                    "hit_count": count,
                    "fraction": count / len(x),
                })


def write_success_outputs(
    output_dir: Path,
    estimates: Mapping[str, ProfileBoundaryEstimate],
    coordinates: Mapping[str, tuple[np.ndarray, np.ndarray]],
    config: BoundaryAlgorithmConfig,
    results_root: Path,
) -> None:
    created = datetime.now(timezone.utc).isoformat()
    payload = boundary_config_payload(estimates, config, created, results_root)
    (output_dir / BOUNDARY_CONFIG_NAME).write_text(
        json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    write_histogram_csv(output_dir / "detector_x_histogram.csv", estimates)
    write_boundary_csv(output_dir / "boundary_summary.csv", estimates)
    write_stability_csv(output_dir / "stability_summary.csv", estimates)
    write_channel_summary_csv(output_dir / "slit_channel_summary.csv", estimates, coordinates)
    for profile_id, estimate in estimates.items():
        x, y = coordinates[profile_id]
        plot_detector_x(profile_id, estimate.slit_order, estimate.detection, output_dir)
        plot_hit_map(profile_id, estimate.slit_order, x, y, estimate.detection, output_dir)


def replace_output(staging: Path, output: Path, overwrite: bool) -> None:
    if output.exists():
        if not overwrite:
            raise FileExistsError(f"output directory exists; pass --overwrite: {output}")
        shutil.rmtree(output)
    staging.replace(output)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    defaults = BoundaryAlgorithmConfig()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--results-root", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path)
    parser.add_argument("--events-name", default="events.csv")
    parser.add_argument("--bin-width-mm", type=float, default=defaults.histogram_bin_width_mm)
    parser.add_argument("--smoothing-sigma-mm", type=float, default=defaults.smoothing_sigma_mm)
    parser.add_argument(
        "--minimum-peak-height-fraction",
        type=float,
        default=defaults.minimum_peak_height_fraction,
    )
    parser.add_argument(
        "--minimum-peak-prominence-fraction",
        type=float,
        default=defaults.minimum_peak_prominence_fraction,
    )
    parser.add_argument(
        "--minimum-peak-distance-mm", type=float, default=defaults.minimum_peak_distance_mm
    )
    parser.add_argument(
        "--valley-plateau-tolerance-fraction",
        type=float,
        default=defaults.valley_plateau_tolerance_fraction,
    )
    parser.add_argument(
        "--maximum-valley-to-peak-ratio",
        type=float,
        default=defaults.maximum_valley_to_peak_ratio,
    )
    parser.add_argument("--overwrite", action="store_true")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    results_root = args.results_root.resolve()
    output = (
        args.output_dir
        or results_root / "data_processing" / "slit_channels"
    ).resolve()
    if output.exists() and not args.overwrite:
        raise FileExistsError(f"output directory exists; pass --overwrite: {output}")
    output.parent.mkdir(parents=True, exist_ok=True)
    staging = Path(tempfile.mkdtemp(prefix=f".{output.name}.staging-", dir=output.parent))
    config = BoundaryAlgorithmConfig(
        histogram_bin_width_mm=args.bin_width_mm,
        smoothing_sigma_mm=args.smoothing_sigma_mm,
        minimum_peak_height_fraction=args.minimum_peak_height_fraction,
        minimum_peak_prominence_fraction=args.minimum_peak_prominence_fraction,
        minimum_peak_distance_mm=args.minimum_peak_distance_mm,
        valley_plateau_tolerance_fraction=args.valley_plateau_tolerance_fraction,
        maximum_valley_to_peak_ratio=args.maximum_valley_to_peak_ratio,
    )
    config.validate()
    baselines = discover_baseline_files(results_root, args.events_name)
    try:
        estimates, coordinates = estimate_slit_boundaries(baselines, config)
        write_success_outputs(staging, estimates, coordinates, config, results_root)
        replace_output(staging, output, args.overwrite)
    except Exception as error:
        # Preserve machine-readable failure state. If a partial detection exists, also
        # preserve the diagnostic plot, but never emit a valid boundary config.
        failure: dict[str, Any] = {
            "status": "failed",
            "error_type": type(error).__name__,
            "message": str(error),
            "created_utc": datetime.now(timezone.utc).isoformat(),
            "parameters": config.__dict__,
            "baseline_input_files": {
                key: value.as_posix() for key, value in baselines.items()
            },
        }
        if isinstance(error, BoundaryEstimationError):
            failure["profile_id"] = error.profile_id
            if error.detection is not None:
                failure["candidate_peak_x_mm"] = [
                    float(value) for value in error.detection.peak_x_mm
                ]
                plot_detector_x(
                    error.profile_id,
                    tuple(f"band_{index}" for index in range(1, 4)),
                    error.detection,
                    staging,
                    failure_title=str(error),
                )
                failed_x, failed_y = read_detector_coordinates(baselines[error.profile_id])
                plot_hit_map(
                    error.profile_id,
                    tuple(f"band_{index}" for index in range(1, 4)),
                    failed_x,
                    failed_y,
                    error.detection,
                    staging,
                    failure_title=str(error),
                )
        (staging / "boundary_estimation_failure.json").write_text(
            json.dumps(failure, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
        )
        replace_output(staging, output, args.overwrite)
        raise

    print(f"boundary config: {output / BOUNDARY_CONFIG_NAME}")
    for profile_id, estimate in estimates.items():
        print(f"{profile_id}:")
        for index, boundary in enumerate(estimate.detection.boundary_x_mm):
            print(
                f"  {estimate.slit_order[index]}/{estimate.slit_order[index + 1]} = "
                f"{boundary:.6g} mm"
            )
        labels = baseline_labels(coordinates[profile_id][0], estimate)
        for slit in estimate.slit_order:
            print(f"  {slit}: {int(np.count_nonzero(labels == slit))} hits")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as error:
        print(f"error: {error}", file=sys.stderr)
        raise SystemExit(1) from error
