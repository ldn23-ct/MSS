#!/usr/bin/env python3
"""Generate the canonical Article V2 E1 paper figures."""

from __future__ import annotations

import argparse
import math
import os
import shutil
import sys
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

os.environ.setdefault("MPLCONFIGDIR", "/tmp/mss_matplotlib")
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import yaml

from scripts.data_processing.common import (
    PROFILE_SLITS,
    DetectorAcceptanceRegion,
    RunMetadata,
    acceptance_regions_for_profile,
    load_run_metadata,
)
from scripts.data_processing.experiment_contract import SLIT_DESIGN_DEPTH_MM


E1_DEPTH_RANGE_MM = (0.0, 220.0)
E1_DEPTH_BIN_WIDTH_MM = 2.0
DEFAULT_SPATIAL_VIEW_QUANTILE = (0.005, 0.995)
VIEW_PADDING_FRACTION = 0.03
SLIT_IDS = tuple(f"S{index}" for index in range(1, 7))
SLIT_COLORS = {
    slit_id: plt.get_cmap("viridis")(value)
    for slit_id, value in zip(SLIT_IDS, np.linspace(0.08, 0.92, len(SLIT_IDS)), strict=True)
}
FIGURE_NAMES = (
    "E1-F1_detector_plane_roi.png",
    "E1-F2_roi_conditioned_total_depth_response.png",
    "E1-F3_first_last_spatial_comparison.png",
)
E1_VALID_REQUIRED_COLUMNS = {
    "det_x",
    "det_y",
    "scatter_count_total",
    "first_scatter_x",
    "first_scatter_y",
    "first_scatter_z",
    "last_scatter_x",
    "last_scatter_y",
    "last_scatter_z",
    "slit_group",
    "slit_label",
}
NUMERIC_COLUMNS = tuple(sorted(E1_VALID_REQUIRED_COLUMNS.difference({"slit_group", "slit_label"})))


@dataclass
class AnalysisContext:
    results_root: Path
    audit_dir: Path
    output_root: Path
    inventory: pd.DataFrame
    audit: dict[str, Any]
    warnings: list[str] = field(default_factory=list)
    _valid_cache: dict[str, pd.DataFrame] = field(default_factory=dict)
    _valid_metadata_cache: dict[str, RunMetadata] = field(default_factory=dict)

    def run_row(
        self, mode: str, phantom: str, profile: str, x: float = 0, y: float = 0
    ) -> pd.Series:
        rows = self.inventory[
            (self.inventory.scan_mode == mode)
            & (self.inventory.phantom_id == phantom)
            & (self.inventory.profile_id == profile)
            & np.isclose(self.inventory.head_offset_x_mm.astype(float), x)
            & np.isclose(self.inventory.head_offset_y_mm.astype(float), y)
        ]
        if len(rows) != 1:
            raise ValueError(
                f"expected one run for {(mode, phantom, profile, x, y)}, found {len(rows)}"
            )
        if rows.iloc[0]["status"] != "valid":
            raise ValueError(
                f"audit inventory marks run invalid: {(mode, phantom, profile, x, y)}"
            )
        return rows.iloc[0]

    def valid_event_path(self, row: pd.Series) -> Path:
        path = (self.results_root / row.valid_file).resolve()
        if not path.is_file():
            raise FileNotFoundError(f"valid event file not found: {path}")
        return path

    def valid_events(self, row: pd.Series) -> pd.DataFrame:
        path = self.valid_event_path(row)
        key = path.as_posix()
        if key not in self._valid_cache:
            frame = pd.read_csv(path)
            missing = sorted(E1_VALID_REQUIRED_COLUMNS.difference(frame.columns))
            if missing:
                raise ValueError(f"valid events are missing required E1 columns {missing}: {path}")
            for column in NUMERIC_COLUMNS:
                frame[column] = pd.to_numeric(frame[column], errors="raise")
            values = frame[list(NUMERIC_COLUMNS)].to_numpy(dtype=float)
            if not np.isfinite(values).all():
                raise ValueError(f"E1 numeric event columns must be finite: {path}")
            self._valid_cache[key] = frame
        return self._valid_cache[key]

    def valid_metadata(self, row: pd.Series) -> RunMetadata:
        path = self.valid_event_path(row).parent / "metadata.yaml"
        key = path.as_posix()
        if key not in self._valid_metadata_cache:
            self._valid_metadata_cache[key] = load_run_metadata(path)
        return self._valid_metadata_cache[key]


def validate_audit(audit_dir: Path) -> tuple[dict[str, Any], pd.DataFrame]:
    summary_path = audit_dir / "audit_summary.yaml"
    inventory_path = audit_dir / "condition_inventory.csv"
    if not summary_path.is_file() or not inventory_path.is_file():
        raise FileNotFoundError("audit_summary.yaml and condition_inventory.csv are required")
    audit = yaml.safe_load(summary_path.read_text(encoding="utf-8"))
    if audit.get("overall_status") != "pass":
        raise ValueError("articlev2 audit must pass before E1 analysis")
    status = audit.get("experiments", {}).get("E1", {}).get("status")
    if status != "ready":
        raise ValueError(f"audit status for E1 is {status}, expected ready")
    return audit, pd.read_csv(inventory_path)


def scatter_counts(frame: pd.DataFrame) -> pd.Series:
    values = frame.scatter_count_total.to_numpy(dtype=float)
    if (
        not np.isfinite(values).all()
        or (values < 0).any()
        or not np.equal(values, np.floor(values)).all()
    ):
        raise ValueError("scatter_count_total must contain finite non-negative integers")
    return frame.scatter_count_total.astype(np.int64)


def class_mask(frame: pd.DataFrame, category: str) -> pd.Series:
    scatter = scatter_counts(frame)
    if category == "total":
        return scatter >= 1
    if category == "k1":
        return scatter == 1
    if category == "ms":
        return scatter >= 2
    raise ValueError(f"unknown event class: {category}")


def e1_roi_mask(frame: pd.DataFrame, region: DetectorAcceptanceRegion) -> pd.Series:
    """Select the recorded slit channel inside its fixed closed detector ROI."""
    coordinates = frame[["det_x", "det_y"]].to_numpy(dtype=float)
    if not np.isfinite(coordinates).all():
        raise ValueError("E1 detector coordinates must be finite")
    return (
        frame.slit_label.astype(str).eq(region.slit_id)
        & frame.det_x.between(region.x_min_mm, region.x_max_mm, inclusive="both")
        & frame.det_y.between(region.y_min_mm, region.y_max_mm, inclusive="both")
    )


def depth_edges() -> np.ndarray:
    start, end = E1_DEPTH_RANGE_MM
    return np.arange(start, end + E1_DEPTH_BIN_WIDTH_MM, E1_DEPTH_BIN_WIDTH_MM)


def padded_quantile_range(
    values: np.ndarray,
    quantile: tuple[float, float] = DEFAULT_SPATIAL_VIEW_QUANTILE,
    *,
    padding_fraction: float = VIEW_PADDING_FRACTION,
) -> tuple[float, float]:
    values = np.asarray(values, dtype=float)
    if not values.size or not np.isfinite(values).all():
        raise ValueError("view-range values must be finite and non-empty")
    low_q, high_q = validate_quantile(quantile)
    low, high = (float(value) for value in np.quantile(values, (low_q, high_q)))
    if math.isclose(low, high):
        scale = max(abs(low), 1.0)
        low -= scale * padding_fraction
        high += scale * padding_fraction
    else:
        padding = (high - low) * padding_fraction
        low -= padding
        high += padding
    return low, high


def validate_quantile(value: tuple[float, float]) -> tuple[float, float]:
    low, high = (float(item) for item in value)
    if not (math.isfinite(low) and math.isfinite(high) and 0 <= low < high <= 1):
        raise ValueError("spatial view quantiles must satisfy 0 <= LOW < HIGH <= 1")
    return low, high


def validate_limit(name: str, value: tuple[float, float] | None) -> tuple[float, float] | None:
    if value is None:
        return None
    low, high = (float(item) for item in value)
    if not (math.isfinite(low) and math.isfinite(high) and low < high):
        raise ValueError(f"{name} must contain finite LOW < HIGH")
    return low, high


def _metadata_range(metadata: RunMetadata, field: str) -> tuple[float, float]:
    value = metadata.raw.get("detector", {}).get(field)
    if not isinstance(value, list) or len(value) != 2:
        raise ValueError(f"metadata detector.{field} must contain two values: {metadata.metadata_path}")
    low, high = (float(item) for item in value)
    if not (math.isfinite(low) and math.isfinite(high) and low < high):
        raise ValueError(f"metadata detector.{field} is invalid: {metadata.metadata_path}")
    return low, high


def _save_png(fig: plt.Figure, path: Path) -> None:
    if path.suffix != ".png":
        raise ValueError(f"E1 figures must use PNG: {path}")
    fig.savefig(path, dpi=300, bbox_inches="tight")
    plt.close(fig)


def _load_inputs(
    ctx: AnalysisContext,
) -> tuple[
    pd.DataFrame,
    dict[str, pd.DataFrame],
    dict[str, pd.DataFrame],
    dict[str, DetectorAcceptanceRegion],
    list[str],
    tuple[float, float],
]:
    frames: list[pd.DataFrame] = []
    frames_by_profile: dict[str, pd.DataFrame] = {}
    selected_by_slit: dict[str, pd.DataFrame] = {}
    regions_by_slit: dict[str, DetectorAcceptanceRegion] = {}
    input_files: list[str] = []
    y_ranges: list[tuple[float, float]] = []

    for profile_id, slit_ids in PROFILE_SLITS.items():
        run = ctx.run_row("center", "P0", profile_id)
        metadata = ctx.valid_metadata(run)
        if (
            metadata.scan_mode != "center"
            or metadata.phantom_id != "P0"
            or metadata.profile_id != profile_id
            or metadata.head_offset_x_mm != 0
            or metadata.head_offset_y_mm != 0
        ):
            raise ValueError(f"unexpected E1 valid-run metadata: {metadata.metadata_path}")
        frame = ctx.valid_events(run).copy()
        scatter_counts(frame)
        if (frame.first_scatter_z < E1_DEPTH_RANGE_MM[0]).any() or (
            frame.first_scatter_z > E1_DEPTH_RANGE_MM[1]
        ).any():
            raise ValueError(f"E1 first-scatter depth falls outside 0-220 mm: {metadata.metadata_path}")
        if frame.slit_group.isna().any() or not frame.slit_group.astype(str).eq(profile_id).all():
            raise ValueError(f"E1 slit_group must equal profile {profile_id}: {metadata.metadata_path}")
        frame["slit_label"] = frame.slit_label.astype(str)
        invalid_labels = sorted(set(frame.slit_label).difference(slit_ids))
        if invalid_labels:
            raise ValueError(f"E1 slit_label must be one of {slit_ids}: {invalid_labels}")

        regions = acceptance_regions_for_profile(profile_id)
        x_range = _metadata_range(metadata, "actual_x_range_mm")
        y_range = _metadata_range(metadata, "actual_y_range_mm")
        for region in regions:
            if (
                region.x_min_mm < x_range[0]
                or region.x_max_mm > x_range[1]
                or region.y_min_mm < y_range[0]
                or region.y_max_mm > y_range[1]
            ):
                raise ValueError(f"E1 acceptance region is outside detector bounds: {region}")
            regions_by_slit[region.slit_id] = region
            selected_by_slit[region.slit_id] = frame.loc[e1_roi_mask(frame, region)].copy()

        frames.append(frame)
        frames_by_profile[profile_id] = frame
        y_ranges.append(y_range)
        input_files.append(ctx.valid_event_path(run).relative_to(ctx.results_root).as_posix())

    if set(selected_by_slit) != set(SLIT_IDS):
        raise AssertionError("E1 input profiles do not cover S1-S6")
    return (
        pd.concat(frames, ignore_index=True),
        frames_by_profile,
        selected_by_slit,
        regions_by_slit,
        input_files,
        (min(item[0] for item in y_ranges), max(item[1] for item in y_ranges)),
    )


def run_e1(
    ctx: AnalysisContext,
    *,
    spatial_view_quantile: tuple[float, float] = DEFAULT_SPATIAL_VIEW_QUANTILE,
    spatial_xlim: tuple[float, float] | None = None,
    spatial_ylim: tuple[float, float] | None = None,
    spatial_zlim: tuple[float, float] | None = None,
) -> dict[str, Any]:
    spatial_view_quantile = validate_quantile(spatial_view_quantile)
    spatial_xlim = validate_limit("spatial_xlim", spatial_xlim)
    spatial_ylim = validate_limit("spatial_ylim", spatial_ylim)
    spatial_zlim = validate_limit("spatial_zlim", spatial_zlim)
    figures = ctx.output_root / "figures"
    figures.mkdir(parents=True, exist_ok=True)
    (
        all_events,
        frames_by_profile,
        selected_by_slit,
        regions_by_slit,
        input_files,
        detector_y_range,
    ) = _load_inputs(ctx)

    # E1-F1: the two real acquisition configurations are shown independently.
    acquisition_groups = (("P002", ("S1", "S3", "S5")), ("P001", ("S2", "S4", "S6")))
    detector_group_x_ranges: dict[str, list[float]] = {}
    fig, axes = plt.subplots(
        1, 2, figsize=(13.5, 6.2), sharey=True, constrained_layout=True
    )
    for index, (axis, (profile_id, slit_ids)) in enumerate(
        zip(axes, acquisition_groups, strict=True)
    ):
        frame = frames_by_profile[profile_id]
        event_low, event_high = (
            float(value)
            for value in np.quantile(
                frame.det_x.to_numpy(dtype=float), DEFAULT_SPATIAL_VIEW_QUANTILE
            )
        )
        roi_low = min(regions_by_slit[slit_id].x_min_mm for slit_id in slit_ids)
        roi_high = max(regions_by_slit[slit_id].x_max_mm for slit_id in slit_ids)
        core_low, core_high = min(event_low, roi_low), max(event_high, roi_high)
        padding = (core_high - core_low) * VIEW_PADDING_FRACTION
        x_range = (core_low - padding, core_high + padding)
        detector_group_x_ranges[profile_id] = [float(x_range[0]), float(x_range[1])]
        for slit_id in slit_ids:
            region = regions_by_slit[slit_id]
            axis.axvspan(
                region.x_min_mm, region.x_max_mm, color="#BDBDBD", alpha=0.18, zorder=0
            )
            axis.axvline(
                region.x_min_mm, color="#333333", linestyle="--", linewidth=0.9, zorder=1
            )
            axis.axvline(
                region.x_max_mm, color="#333333", linestyle="--", linewidth=0.9, zorder=1
            )
            hits = frame[frame.slit_label == slit_id]
            axis.scatter(
                hits.det_x,
                hits.det_y,
                s=2,
                alpha=0.28,
                color=SLIT_COLORS[slit_id],
                label=slit_id,
                rasterized=True,
            )
            axis.text(
                (region.x_min_mm + region.x_max_mm) / 2,
                0.975,
                f"{slit_id} ROI",
                transform=axis.get_xaxis_transform(),
                ha="center",
                va="top",
                fontsize=8,
                color="#222222",
                bbox={"facecolor": "white", "edgecolor": "none", "alpha": 0.65, "pad": 1},
            )
        axis.set(
            xlim=x_range,
            ylim=detector_y_range,
            xlabel="Detector-plane x (mm)",
            title=f"({chr(ord('a') + index)}) {' / '.join(slit_ids)} group ({profile_id})",
        )
        axis.legend(ncol=3, loc="lower center", fontsize=8)
    axes[0].set_ylabel("Detector-plane y (mm)")
    fig.suptitle("E1-F1  Detector-plane valid events and acquisition-group slit ROIs")
    _save_png(fig, figures / FIGURE_NAMES[0])

    # E1-F2: one independently normalized total profile per ROI.
    edges = depth_edges()
    profile_counts: dict[str, np.ndarray] = {}
    roi_counts: dict[str, int] = {}
    fig, axis = plt.subplots(figsize=(11.5, 6.4), constrained_layout=True)
    for slit_id in SLIT_IDS:
        selected = selected_by_slit[slit_id]
        selected = selected.loc[class_mask(selected, "total")]
        counts, _ = np.histogram(selected.first_scatter_z.to_numpy(dtype=float), bins=edges)
        if counts.sum() != len(selected) or counts.sum() == 0:
            raise ValueError(f"E1 {slit_id} total depth histogram is empty or loses events")
        normalized = counts.astype(float) / counts.sum()
        profile_counts[slit_id] = counts
        roi_counts[slit_id] = int(counts.sum())
        axis.stairs(normalized, edges, color=SLIT_COLORS[slit_id], label=slit_id, linewidth=1.6)
        design_depth = SLIT_DESIGN_DEPTH_MM[slit_id]
        axis.plot(
            [design_depth, design_depth],
            [-0.028, 0],
            transform=axis.get_xaxis_transform(),
            clip_on=False,
            color=SLIT_COLORS[slit_id],
            linewidth=1.0,
        )
        axis.text(
            design_depth,
            -0.045,
            f"{design_depth:g}",
            transform=axis.get_xaxis_transform(),
            clip_on=False,
            ha="center",
            va="top",
            fontsize=8,
            color=SLIT_COLORS[slit_id],
        )
    axis.set(
        xlim=E1_DEPTH_RANGE_MM,
        ylabel="Normalized detected contribution",
        title="E1-F2  ROI-conditioned total first-scatter depth response",
    )
    axis.set_xlabel("First-scatter depth z (mm)", labelpad=38)
    axis.legend(ncol=6, loc="upper right")
    _save_png(fig, figures / FIGURE_NAMES[1])

    # E1-F3: preserve the two real acquisition configurations in a 2x2 overlay.
    spatial_ranges: dict[str, dict[str, tuple[float, float]]] = {}
    spatial_outside_counts: dict[str, dict[str, int]] = {}
    spatial_point_counts: dict[str, dict[str, int]] = {}
    spatial_profile_event_counts: dict[str, int] = {}
    fig, axes = plt.subplots(2, 2, figsize=(13.5, 10), constrained_layout=True)
    panel_index = 0
    for row_index, (profile_id, slit_ids) in enumerate(acquisition_groups):
        frame = frames_by_profile[profile_id]
        pooled_coordinates = {
            coordinate: np.concatenate(
                [
                    frame[f"first_scatter_{coordinate}"].to_numpy(dtype=float),
                    frame[f"last_scatter_{coordinate}"].to_numpy(dtype=float),
                ]
            )
            for coordinate in ("x", "y", "z")
        }
        group_ranges = {
            "x": spatial_xlim
            or padded_quantile_range(pooled_coordinates["x"], spatial_view_quantile),
            "y": spatial_ylim
            or padded_quantile_range(pooled_coordinates["y"], spatial_view_quantile),
            "z": spatial_zlim
            or padded_quantile_range(pooled_coordinates["z"], spatial_view_quantile),
        }
        spatial_ranges[profile_id] = group_ranges
        spatial_outside_counts[profile_id] = {}
        spatial_point_counts[profile_id] = {}
        spatial_profile_event_counts[profile_id] = int(len(frame))
        group_label = "/".join(slit_ids)
        for column_index, (horizontal, projection) in enumerate((('x', 'xz'), ('y', 'yz'))):
            axis = axes[row_index, column_index]
            horizontal_range = group_ranges[horizontal]
            z_range = group_ranges["z"]
            for scatter_name, color, zorder in (
                ("first", "#0072B2", 1),
                ("last", "#D55E00", 2),
            ):
                horizontal_values = frame[
                    f"{scatter_name}_scatter_{horizontal}"
                ].to_numpy(dtype=float)
                z_values = frame[f"{scatter_name}_scatter_z"].to_numpy(dtype=float)
                outside = ~(
                    (horizontal_values >= horizontal_range[0])
                    & (horizontal_values <= horizontal_range[1])
                    & (z_values >= z_range[0])
                    & (z_values <= z_range[1])
                )
                key = f"{scatter_name}_{projection}"
                spatial_outside_counts[profile_id][key] = int(outside.sum())
                spatial_point_counts[profile_id][key] = int(len(horizontal_values))
                axis.scatter(
                    horizontal_values,
                    z_values,
                    s=2,
                    alpha=0.12,
                    color=color,
                    label=f"{scatter_name.capitalize()} scatter",
                    zorder=zorder,
                    rasterized=True,
                )
            axis.set(
                xlim=horizontal_range,
                ylim=z_range,
                xlabel=f"{horizontal} (mm)",
                ylabel="z (mm)",
                title=(
                    f"({chr(ord('a') + panel_index)}) {group_label} ({profile_id}) "
                    f"{horizontal}-z"
                ),
            )
            axis.legend(loc="upper right", fontsize=8, markerscale=2.5)
            panel_index += 1
    fig.suptitle("E1-F3  All-valid-events first/last scatter overlay")
    _save_png(fig, figures / FIGURE_NAMES[2])

    for profile_id, slit_ids in acquisition_groups:
        for projection in ("xz", "yz"):
            print(
                f"E1-F3 {profile_id} {'/'.join(slit_ids)} {projection} outside displayed view: "
                f"first={spatial_outside_counts[profile_id][f'first_{projection}']}, "
                f"last={spatial_outside_counts[profile_id][f'last_{projection}']}"
            )

    return {
        "input_files": input_files,
        "all_valid_event_count": int(len(all_events)),
        "roi_total_counts": roi_counts,
        "acquisition_groups": {
            profile_id: list(slit_ids) for profile_id, slit_ids in acquisition_groups
        },
        "profile_normalized_sums": {
            slit_id: float((counts / counts.sum()).sum()) for slit_id, counts in profile_counts.items()
        },
        "detector_group_x_ranges_mm": detector_group_x_ranges,
        "spatial_view_quantile": [float(value) for value in spatial_view_quantile],
        "spatial_manual_limits": {
            "x_mm": list(spatial_xlim) if spatial_xlim is not None else None,
            "y_mm": list(spatial_ylim) if spatial_ylim is not None else None,
            "z_mm": list(spatial_zlim) if spatial_zlim is not None else None,
        },
        "spatial_view_ranges_mm": {
            profile_id: {
                f"{coordinate}_mm": [float(value) for value in group_ranges[coordinate]]
                for coordinate in ("x", "y", "z")
            }
            for profile_id, group_ranges in spatial_ranges.items()
        },
        "spatial_profile_event_counts": spatial_profile_event_counts,
        "spatial_point_counts": spatial_point_counts,
        "spatial_outside_view_counts": spatial_outside_counts,
        "fixed_regions": {
            slit_id: {
                "x_range_mm": [region.x_min_mm, region.x_max_mm],
                "y_range_mm": [region.y_min_mm, region.y_max_mm],
            }
            for slit_id, region in regions_by_slit.items()
        },
    }


def write_report(root: Path, summary: dict[str, Any], warnings: list[str]) -> None:
    lines = [
        "# Article V2 E1 Analysis Results",
        "",
        "E1 completed with the frozen three-figure paper contract.",
        "",
        f"- All valid P0 center events: {summary['all_valid_event_count']}",
        f"- ROI-selected total counts: {summary['roi_total_counts']}",
        "- Depth profiles: 2 mm bins over 0–220 mm, independently normalized by slit.",
        "- Detector plane: P002 S1/S3/S5 and P001 S2/S4/S6 are shown in separate panels.",
        "- Spatial overlay: the same two acquisition groups form the rows of a 2×2 figure.",
        f"- Spatial view ranges (mm): {summary['spatial_view_ranges_mm']}",
        f"- Spatial points outside displayed views: {summary['spatial_outside_view_counts']}",
        "- Spatial limits affect display only; every valid first/last point is retained.",
        "- Figures: PNG only; no E1 result tables are produced.",
        "",
        "## Warnings",
        "",
    ]
    lines.extend([f"- {item}" for item in warnings] if warnings else ["- None."])
    lines.append("")
    (root / "report.md").write_text("\n".join(lines), encoding="utf-8")


def validate_generated_outputs(root: Path, summary: dict[str, Any]) -> dict[str, Any]:
    figure_dir = root / "figures"
    actual_figures = {path.name for path in figure_dir.iterdir() if path.is_file()}
    expected_figures = set(FIGURE_NAMES)
    normalized = all(
        math.isclose(value, 1.0, rel_tol=0, abs_tol=1e-12)
        for value in summary["profile_normalized_sums"].values()
    )
    spatial_counts = summary["spatial_point_counts"]
    profile_event_counts = summary["spatial_profile_event_counts"]
    spatial_accounting = bool(spatial_counts) and set(spatial_counts) == set(profile_event_counts)
    if spatial_accounting:
        spatial_accounting = all(
            set(counts) == {"first_xz", "last_xz", "first_yz", "last_yz"}
            and all(value == profile_event_counts[profile_id] for value in counts.values())
            for profile_id, counts in spatial_counts.items()
        )
    checks = {
        "E1_figure_contract": {
            "actual": sorted(actual_figures),
            "expected": sorted(expected_figures),
            "pass": actual_figures == expected_figures,
        },
        "E1_png_only": {
            "actual": not any(path.suffix.lower() == ".pdf" for path in root.rglob("*")),
            "expected": True,
            "pass": not any(path.suffix.lower() == ".pdf" for path in root.rglob("*")),
        },
        "E1_no_result_tables": {
            "actual": not (root / "tables").exists(),
            "expected": True,
            "pass": not (root / "tables").exists(),
        },
        "E1_six_roi_profiles": {
            "actual": sorted(summary["roi_total_counts"]),
            "expected": list(SLIT_IDS),
            "pass": set(summary["roi_total_counts"]) == set(SLIT_IDS)
            and all(value > 0 for value in summary["roi_total_counts"].values()),
        },
        "E1_profile_normalization": {
            "actual": summary["profile_normalized_sums"],
            "expected": {slit_id: 1.0 for slit_id in SLIT_IDS},
            "pass": normalized,
        },
        "E1_spatial_event_accounting": {
            "actual": spatial_counts,
            "expected": {
                profile_id: {
                    key: event_count
                    for key in ("first_xz", "last_xz", "first_yz", "last_yz")
                }
                for profile_id, event_count in profile_event_counts.items()
            },
            "pass": spatial_accounting,
        },
        "E1_acquisition_group_panels": {
            "actual": summary["acquisition_groups"],
            "expected": {"P002": ["S1", "S3", "S5"], "P001": ["S2", "S4", "S6"]},
            "pass": summary["acquisition_groups"]
            == {"P002": ["S1", "S3", "S5"], "P001": ["S2", "S4", "S6"]},
        },
    }
    passed = all(item["pass"] for item in checks.values())
    result = {"overall_status": "pass" if passed else "fail", "checks": checks}
    (root / "acceptance_summary.yaml").write_text(
        yaml.safe_dump(result, sort_keys=False, allow_unicode=True), encoding="utf-8"
    )
    if not passed:
        raise AssertionError("generated E1 analysis failed acceptance checks")
    return result


def relative_to_campaign(path: Path, results_root: Path) -> str:
    try:
        return path.resolve().relative_to(results_root.resolve()).as_posix()
    except ValueError:
        return path.resolve().as_posix()


def write_manifest(
    root: Path,
    results_root: Path,
    audit_dir: Path,
    summary: dict[str, Any],
    warnings: list[str],
) -> None:
    outputs = sorted(
        path.relative_to(root).as_posix()
        for path in root.rglob("*")
        if path.is_file() and path.name != "analysis_manifest.yaml"
    )
    data = {
        "schema_version": 2,
        "analysis": "articlev2_e1_paper_figures",
        "experiment": "E1",
        "results_root": ".",
        "audit_summary": relative_to_campaign(audit_dir / "audit_summary.yaml", results_root),
        "parameters": {
            "input_layer": "events/valid",
            "input_files": summary["input_files"],
            "phantom_id": "P0",
            "scan_mode": "center",
            "slit_identity_rule": "validate recorded slit_label; select inside fixed closed detector ROI",
            "depth_bin_width_mm": E1_DEPTH_BIN_WIDTH_MM,
            "depth_range_mm": list(E1_DEPTH_RANGE_MM),
            "depth_normalization": "independent integral normalization for each slit total profile",
            "detector_group_view_rule": "pooled central 99 percent plus every group ROI and 3 percent padding",
            "acquisition_groups": summary["acquisition_groups"],
            "detector_group_x_ranges_mm": summary["detector_group_x_ranges_mm"],
            "spatial_rendering": "rasterized first/last scatter overlay",
            "spatial_view_quantile": summary["spatial_view_quantile"],
            "spatial_manual_limits": summary["spatial_manual_limits"],
            "spatial_view_ranges_mm": summary["spatial_view_ranges_mm"],
            "spatial_view_padding_fraction": VIEW_PADDING_FRACTION,
            "fixed_acceptance_regions": summary["fixed_regions"],
            "figure_formats": ["png"],
            "formal_figure_count": len(FIGURE_NAMES),
            "formal_table_count": 0,
        },
        "data_quality": {
            "all_valid_event_count": summary["all_valid_event_count"],
            "roi_total_counts": summary["roi_total_counts"],
            "profile_normalized_sums": summary["profile_normalized_sums"],
            "spatial_profile_event_counts": summary["spatial_profile_event_counts"],
            "spatial_point_counts": summary["spatial_point_counts"],
            "spatial_outside_view_counts": summary["spatial_outside_view_counts"],
        },
        "warnings": warnings,
        "outputs": outputs,
    }
    (root / "analysis_manifest.yaml").write_text(
        yaml.safe_dump(data, sort_keys=False, allow_unicode=True), encoding="utf-8"
    )


def run_analysis(
    results_root: Path,
    audit_dir: Path,
    output_dir: Path,
    *,
    spatial_view_quantile: tuple[float, float] = DEFAULT_SPATIAL_VIEW_QUANTILE,
    spatial_xlim: tuple[float, float] | None = None,
    spatial_ylim: tuple[float, float] | None = None,
    spatial_zlim: tuple[float, float] | None = None,
) -> None:
    audit, inventory = validate_audit(audit_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    context = AnalysisContext(results_root, audit_dir, output_dir, inventory, audit)
    summary = run_e1(
        context,
        spatial_view_quantile=spatial_view_quantile,
        spatial_xlim=spatial_xlim,
        spatial_ylim=spatial_ylim,
        spatial_zlim=spatial_zlim,
    )
    write_report(output_dir, summary, context.warnings)
    validate_generated_outputs(output_dir, summary)
    write_manifest(output_dir, results_root, audit_dir, summary, context.warnings)


def publish(staging: Path, output_dir: Path, overwrite: bool) -> None:
    if not output_dir.exists():
        staging.replace(output_dir)
        return
    if not overwrite:
        raise FileExistsError(f"output directory exists; pass --overwrite: {output_dir}")
    backup = output_dir.parent / f".{output_dir.name}.backup"
    if backup.exists():
        raise FileExistsError(f"stale E1 backup blocks overwrite: {backup}")
    output_dir.replace(backup)
    try:
        staging.replace(output_dir)
        for name in ("roi_sensitivity", "archive"):
            preserved = backup / name
            if preserved.exists():
                preserved.replace(output_dir / name)
    except Exception:
        if output_dir.exists():
            shutil.rmtree(output_dir)
        backup.replace(output_dir)
        raise
    shutil.rmtree(backup)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--results-root", type=Path, required=True)
    parser.add_argument("--audit-dir", type=Path)
    parser.add_argument("--output-dir", type=Path)
    parser.add_argument(
        "--spatial-view-quantile",
        nargs=2,
        type=float,
        metavar=("LOW", "HIGH"),
        default=DEFAULT_SPATIAL_VIEW_QUANTILE,
    )
    parser.add_argument("--spatial-xlim", nargs=2, type=float, metavar=("LOW", "HIGH"))
    parser.add_argument("--spatial-ylim", nargs=2, type=float, metavar=("LOW", "HIGH"))
    parser.add_argument("--spatial-zlim", nargs=2, type=float, metavar=("LOW", "HIGH"))
    parser.add_argument("--overwrite", action="store_true")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    results_root = args.results_root.resolve()
    audit_dir = (args.audit_dir or results_root / "data_processing" / "audit").resolve()
    output_dir = (args.output_dir or results_root / "postprocessing" / "E1").resolve()
    protected = {
        results_root,
        (results_root / "events").resolve(),
        (results_root / "events" / "raw").resolve(),
        (results_root / "events" / "valid").resolve(),
    }
    if output_dir in protected:
        raise ValueError("E1 output directory must not replace event data or results root")
    if output_dir.exists() and not args.overwrite:
        raise FileExistsError(f"output directory exists; pass --overwrite: {output_dir}")
    output_dir.parent.mkdir(parents=True, exist_ok=True)
    staging = Path(tempfile.mkdtemp(prefix=f".{output_dir.name}.staging-", dir=output_dir.parent))
    try:
        run_analysis(
            results_root,
            audit_dir,
            staging,
            spatial_view_quantile=tuple(args.spatial_view_quantile),
            spatial_xlim=tuple(args.spatial_xlim) if args.spatial_xlim else None,
            spatial_ylim=tuple(args.spatial_ylim) if args.spatial_ylim else None,
            spatial_zlim=tuple(args.spatial_zlim) if args.spatial_zlim else None,
        )
        publish(staging, output_dir, args.overwrite)
    except Exception:
        shutil.rmtree(staging, ignore_errors=True)
        raise
    print(f"report: {output_dir / 'report.md'}")
    print(f"acceptance: {output_dir / 'acceptance_summary.yaml'}")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as error:
        print(f"E1 analysis error: {error}", file=sys.stderr)
        raise SystemExit(1) from error
