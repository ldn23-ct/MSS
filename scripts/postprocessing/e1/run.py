#!/usr/bin/env python3
"""Run the canonical Article V2 E1 depth-response analysis."""

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
from matplotlib.patches import Rectangle

from scripts.data_processing.common import (
    PROFILE_SLITS,
    DetectorAcceptanceRegion,
    RunMetadata,
    acceptance_regions_for_profile,
    load_run_metadata,
)
from scripts.data_processing.experiment_contract import (
    SLIT_DESIGN_DEPTH_MM,
)


CLASSES = ("total", "k1", "ms")
E1_DEPTH_RANGE_MM = (0.0, 220.0)
E1_BIN_WIDTHS_MM = (2.0, 4.0)
E1_PLOT_CLASSES = ("k1", "total", "ms")
COLORS = ("#0072B2", "#D55E00", "#009E73", "#CC79A7", "#E69F00", "#56B4E9")
E1_VALID_REQUIRED_COLUMNS = {
    "det_x", "det_y", "scatter_count_total", "first_scatter_z", "slit_group", "slit_label",
}


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

    def run_row(self, mode: str, phantom: str, profile: str, x: float = 0, y: float = 0) -> pd.Series:
        rows = self.inventory[
            (self.inventory.scan_mode == mode) & (self.inventory.phantom_id == phantom)
            & (self.inventory.profile_id == profile)
            & np.isclose(self.inventory.head_offset_x_mm.astype(float), x)
            & np.isclose(self.inventory.head_offset_y_mm.astype(float), y)
        ]
        if len(rows) != 1:
            raise ValueError(f"expected one run for {(mode, phantom, profile, x, y)}, found {len(rows)}")
        if rows.iloc[0]["status"] != "valid":
            raise ValueError(f"audit inventory marks run invalid: {(mode, phantom, profile, x, y)}")
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
            for column in ("det_x", "det_y", "scatter_count_total", "first_scatter_z"):
                frame[column] = pd.to_numeric(frame[column], errors="raise")
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
        raise ValueError("articlev2 audit must pass before analysis")
    status = audit["experiments"]["E1"]["status"]
    if status != "ready":
        raise ValueError(f"audit status for E1 is {status}, expected ready")
    return audit, pd.read_csv(inventory_path)


def class_mask(frame: pd.DataFrame, category: str) -> pd.Series:
    scatter = frame.scatter_count_total
    if category == "total":
        return scatter >= 1
    if category == "k1":
        return scatter == 1
    if category == "ms":
        return scatter >= 2
    raise ValueError(f"unknown event class: {category}")


def ensure_dirs(root: Path) -> tuple[Path, Path]:
    tables, figures = root / "tables", root / "figures"
    tables.mkdir(parents=True, exist_ok=True); figures.mkdir(parents=True, exist_ok=True)
    return tables, figures


def save_figure(fig: plt.Figure, base: Path, include_pdf: bool = True) -> list[Path]:
    paths = [base.with_suffix(".png")]
    fig.savefig(paths[0], dpi=300, bbox_inches="tight")
    if include_pdf:
        paths.append(base.with_suffix(".pdf"))
        fig.savefig(paths[-1], bbox_inches="tight")
    plt.close(fig)
    return paths


def write_manifest(root: Path, experiment: str, parameters: dict[str, Any], warnings: list[str] | None = None) -> None:
    files = sorted(
        path.relative_to(root).as_posix() for path in root.rglob("*")
        if path.is_file() and path.name != "analysis_manifest.yaml"
    )
    data = {"experiment": experiment, "parameters": parameters, "warnings": warnings or [], "outputs": files}
    (root / "analysis_manifest.yaml").write_text(
        yaml.safe_dump(data, sort_keys=False, allow_unicode=True), encoding="utf-8"
    )


def e1_scatter_counts(frame: pd.DataFrame) -> pd.Series:
    if "scatter_count_total" not in frame:
        raise ValueError("E1 events are missing scatter_count_total")
    values = frame.scatter_count_total.to_numpy(dtype=float)
    if (
        not np.isfinite(values).all()
        or (values < 0).any()
        or not np.equal(values, np.floor(values)).all()
    ):
        raise ValueError("E1 scatter_count_total must contain finite non-negative integers")
    return frame.scatter_count_total.astype(np.int64)


def e1_roi_mask(frame: pd.DataFrame, region: DetectorAcceptanceRegion) -> pd.Series:
    """Select an existing slit label inside its fixed closed geometry ROI."""
    coordinates = frame[["det_x", "det_y"]].to_numpy(dtype=float)
    if not np.isfinite(coordinates).all():
        raise ValueError("E1 detector coordinates must be finite")
    return (
        frame.slit_label.eq(region.slit_id)
        & frame.det_x.between(region.x_min_mm, region.x_max_mm, inclusive="both")
        & frame.det_y.between(region.y_min_mm, region.y_max_mm, inclusive="both")
    )


def e1_depth_edges(bin_width_mm: float) -> np.ndarray:
    start, end = E1_DEPTH_RANGE_MM
    if not math.isfinite(bin_width_mm) or bin_width_mm <= 0:
        raise ValueError("E1 bin width must be finite and positive")
    bin_count = (end - start) / bin_width_mm
    rounded = round(bin_count)
    if not math.isclose(bin_count, rounded, rel_tol=0, abs_tol=1e-12):
        raise ValueError("E1 depth range must be an integer multiple of the bin width")
    return np.linspace(start, end, rounded + 1)


def e1_peak_depth(bin_centers: np.ndarray, counts: np.ndarray) -> float:
    if not len(counts) or counts.max(initial=0) <= 0:
        return math.nan
    peak_count = counts.max()
    return float(bin_centers[np.flatnonzero(counts == peak_count)[0]])


def _metadata_range(metadata: RunMetadata, field: str) -> tuple[float, float]:
    value = metadata.raw.get("detector", {}).get(field)
    if not isinstance(value, list) or len(value) != 2:
        raise ValueError(f"metadata detector.{field} must contain two values: {metadata.metadata_path}")
    low, high = (float(item) for item in value)
    if not (math.isfinite(low) and math.isfinite(high) and low < high):
        raise ValueError(f"metadata detector.{field} is invalid: {metadata.metadata_path}")
    return low, high


def run_e1(ctx: AnalysisContext) -> None:
    root = ctx.output_root
    tables, figures = ensure_dirs(root)
    event_count_rows: list[dict[str, Any]] = []
    design_fraction_rows: list[dict[str, Any]] = []
    peak_rows: list[dict[str, Any]] = []
    peak_lookup: dict[tuple[str, str, float], float] = {}
    histogram_frames: dict[float, pd.DataFrame] = {}
    selected_by_slit: dict[str, pd.DataFrame] = {}
    plot_data: dict[str, tuple[pd.DataFrame, RunMetadata, tuple[DetectorAcceptanceRegion, ...]]] = {}
    input_files: list[str] = []

    for profile_id, slit_ids in PROFILE_SLITS.items():
        run = ctx.run_row("center", "P0", profile_id)
        metadata = ctx.valid_metadata(run)
        if (
            metadata.scan_mode != "center" or metadata.phantom_id != "P0"
            or metadata.profile_id != profile_id
            or metadata.head_offset_x_mm != 0 or metadata.head_offset_y_mm != 0
        ):
            raise ValueError(f"unexpected E1 valid-run metadata: {metadata.metadata_path}")
        frame = ctx.valid_events(run).copy()
        frame["_scatter_count"] = e1_scatter_counts(frame)
        depths = frame.first_scatter_z.to_numpy(dtype=float)
        if not np.isfinite(depths).all() or (depths < 0).any():
            raise ValueError(f"E1 valid first_scatter_z must be finite and non-negative: {metadata.metadata_path}")
        if frame.slit_group.isna().any() or not frame.slit_group.astype(str).eq(profile_id).all():
            raise ValueError(f"E1 slit_group must equal profile {profile_id}: {metadata.metadata_path}")
        labels = frame.slit_label.astype(str)
        invalid_labels = sorted(set(labels).difference(slit_ids))
        if invalid_labels:
            raise ValueError(
                f"E1 slit_label must be one of {slit_ids} for {profile_id}: {invalid_labels}"
            )
        frame["slit_label"] = labels
        regions = acceptance_regions_for_profile(
            profile_id, metadata.head_offset_x_mm, metadata.head_offset_y_mm
        )
        detector_x_range = _metadata_range(metadata, "actual_x_range_mm")
        detector_y_range = _metadata_range(metadata, "actual_y_range_mm")
        for region in regions:
            if (
                region.x_min_mm < detector_x_range[0] or region.x_max_mm > detector_x_range[1]
                or region.y_min_mm < detector_y_range[0] or region.y_max_mm > detector_y_range[1]
            ):
                raise ValueError(f"E1 acceptance region is outside detector bounds: {region}")
        plot_data[profile_id] = (frame, metadata, regions)
        input_files.append(
            ctx.valid_event_path(run).relative_to(ctx.results_root).as_posix()
        )
        by_slit = {region.slit_id: region for region in regions}
        for slit_id in slit_ids:
            selected_by_slit[slit_id] = frame.loc[e1_roi_mask(frame, by_slit[slit_id])].copy()

    for slit_index in range(1, 7):
        slit_id = f"S{slit_index}"
        design_depth = SLIT_DESIGN_DEPTH_MM[slit_id]
        selected = selected_by_slit[slit_id]
        scatter = selected._scatter_count
        total_count = int((scatter >= 1).sum())
        k1_count = int((scatter == 1).sum())
        ms_count = int((scatter >= 2).sum())
        if total_count != k1_count + ms_count:
            raise AssertionError(f"E1 total != k1 + ms for {slit_id}")
        event_count_rows.append({
            "slit": slit_id,
            "design_depth_mm": design_depth,
            "total_count": total_count,
            "k1_count": k1_count,
            "ms_count": ms_count,
            "k1_fraction": k1_count / total_count if total_count else math.nan,
            "ms_fraction": ms_count / total_count if total_count else math.nan,
        })
        for category in CLASSES:
            category_mask = class_mask(
                pd.DataFrame({"scatter_count_total": scatter}, index=selected.index), category
            )
            category_depths = selected.loc[category_mask, "first_scatter_z"]
            region_left = design_depth - 5.0
            region_right = design_depth + 5.0
            region_count = int(((category_depths >= region_left) & (category_depths < region_right)).sum())
            class_total = len(category_depths)
            design_fraction_rows.append({
                "slit": slit_id,
                "design_depth_mm": design_depth,
                "scatter_class": category,
                "region_left_mm": region_left,
                "region_right_mm": region_right,
                "region_count": region_count,
                "class_total_count": class_total,
                "region_fraction": region_count / class_total if class_total else math.nan,
            })

    outside_range_counts: dict[str, int] = {}
    for bin_width in E1_BIN_WIDTHS_MM:
        edges = e1_depth_edges(bin_width)
        centers = (edges[:-1] + edges[1:]) / 2
        depth_rows: list[dict[str, Any]] = []
        for slit_index in range(1, 7):
            slit_id = f"S{slit_index}"
            design_depth = SLIT_DESIGN_DEPTH_MM[slit_id]
            selected = selected_by_slit[slit_id]
            for category in CLASSES:
                category_mask = class_mask(selected, category)
                values = selected.loc[category_mask, "first_scatter_z"].to_numpy(dtype=float)
                counts, _ = np.histogram(values, bins=edges)
                histogram_count = int(counts.sum())
                outside_range_counts[f"{slit_id}.{category}"] = int(len(values) - histogram_count)
                if histogram_count == 0:
                    ctx.warnings.append(f"E1 empty {bin_width:g} mm histogram: {slit_id}-{category}")
                normalized = (
                    counts.astype(float) / histogram_count
                    if histogram_count else np.full(len(counts), math.nan)
                )
                poisson_sigma = np.sqrt(counts.astype(float))
                relative_error = np.divide(
                    1.0,
                    poisson_sigma,
                    out=np.full(len(counts), math.nan),
                    where=counts > 0,
                )
                for index, count in enumerate(counts):
                    depth_rows.append({
                        "slit": slit_id,
                        "design_depth_mm": design_depth,
                        "scatter_class": category,
                        "bin_left_mm": edges[index],
                        "bin_right_mm": edges[index + 1],
                        "bin_center_mm": centers[index],
                        "raw_count": int(count),
                        "normalized_count": normalized[index],
                        "poisson_sigma": poisson_sigma[index],
                        "relative_poisson_error": relative_error[index],
                    })
                peak_depth = e1_peak_depth(centers, counts)
                peak_lookup[(slit_id, category, bin_width)] = peak_depth
                peak_rows.append({
                    "slit": slit_id,
                    "design_depth_mm": design_depth,
                    "scatter_class": category,
                    "bin_width_mm": bin_width,
                    "peak_depth_mm": peak_depth,
                    "peak_raw_count": int(counts.max()) if histogram_count else 0,
                })
        histogram_frames[bin_width] = pd.DataFrame(depth_rows)

    comparison_rows = [
        {
            "slit": f"S{slit_index}",
            "scatter_class": category,
            "peak_2mm": peak_lookup[(f"S{slit_index}", category, 2.0)],
            "peak_4mm": peak_lookup[(f"S{slit_index}", category, 4.0)],
            "peak_shift_mm": (
                peak_lookup[(f"S{slit_index}", category, 4.0)]
                - peak_lookup[(f"S{slit_index}", category, 2.0)]
            ),
        }
        for slit_index in range(1, 7)
        for category in CLASSES
    ]

    event_counts = pd.DataFrame(event_count_rows)
    design_fractions = pd.DataFrame(design_fraction_rows)
    peak_summary = pd.DataFrame(peak_rows)
    binning_comparison = pd.DataFrame(comparison_rows)
    if not (event_counts.total_count == event_counts.k1_count + event_counts.ms_count).all():
        raise AssertionError("E1 classification partition failed")
    if (
        len(event_counts) != 6
        or len(histogram_frames[2.0]) != 1980
        or len(histogram_frames[4.0]) != 990
        or len(peak_summary) != 36
        or len(design_fractions) != 18
        or len(binning_comparison) != 18
    ):
        raise AssertionError("E1 output row count contract failed")

    event_counts.to_csv(tables / "E1_event_counts.csv", index=False, na_rep="NaN")
    histogram_frames[2.0].to_csv(
        tables / "E1_depth_profiles_2mm.csv", index=False, na_rep="NaN"
    )
    histogram_frames[4.0].to_csv(
        tables / "E1_depth_profiles_4mm.csv", index=False, na_rep="NaN"
    )
    peak_summary.to_csv(tables / "E1_peak_summary.csv", index=False, na_rep="NaN")
    design_fractions.to_csv(
        tables / "E1_design_depth_fraction.csv", index=False, na_rep="NaN"
    )
    binning_comparison.to_csv(
        tables / "E1_binning_comparison.csv", index=False, na_rep="NaN"
    )

    fig, axes = plt.subplots(1, 2, figsize=(14, 6), constrained_layout=True)
    for axis, profile_id in zip(axes, PROFILE_SLITS):
        frame, metadata, regions = plot_data[profile_id]
        for region in regions:
            color = COLORS[int(region.slit_id[1:]) - 1]
            hits = frame[frame.slit_label == region.slit_id]
            axis.scatter(
                hits.det_x, hits.det_y, s=2, alpha=.18, color=color,
                label=region.slit_id, rasterized=True,
            )
            axis.add_patch(Rectangle(
                (region.x_min_mm, region.y_min_mm),
                region.x_max_mm - region.x_min_mm,
                region.y_max_mm - region.y_min_mm,
                fill=False, linewidth=1.6, edgecolor=color,
            ))
            axis.text(
                (region.x_min_mm + region.x_max_mm) / 2,
                region.y_max_mm - 5,
                region.slit_id,
                color=color, ha="center", va="top", fontsize=9,
                bbox={"facecolor": "white", "edgecolor": "none", "alpha": .7, "pad": 1},
            )
        x_range = _metadata_range(metadata, "actual_x_range_mm")
        y_range = _metadata_range(metadata, "actual_y_range_mm")
        axis.set(xlim=x_range, ylim=y_range, xlabel="Detector x (mm)", ylabel="Detector y (mm)")
        axis.set_title(f"{profile_id}: {' / '.join(PROFILE_SLITS[profile_id])}")
        axis.grid(alpha=.15)
        axis.legend(loc="lower right", ncol=3, fontsize=8)
    save_figure(fig, figures / "E1_detector_plane_distribution", include_pdf=False)

    for bin_width in E1_BIN_WIDTHS_MM:
        depth_response = histogram_frames[bin_width]
        fig, axes = plt.subplots(3, 1, figsize=(11, 11), sharex=True, constrained_layout=True)
        for panel_index, (axis, category) in enumerate(zip(axes, E1_PLOT_CLASSES)):
            for slit_index in range(1, 7):
                slit_id = f"S{slit_index}"
                data = depth_response[
                    (depth_response.slit == slit_id)
                    & (depth_response.scatter_class == category)
                ]
                color = COLORS[slit_index - 1]
                plot_edges = np.r_[data.bin_left_mm.to_numpy(), data.bin_right_mm.iloc[-1]]
                axis.stairs(
                    data.normalized_count.to_numpy(), plot_edges, label=slit_id, color=color
                )
                axis.axvline(
                    SLIT_DESIGN_DEPTH_MM[slit_id], color=color,
                    linestyle="--", linewidth=.9, alpha=.55,
                )
            axis.set_ylabel("Normalized count")
            axis.set_title(f"({chr(ord('a') + panel_index)}) {category}")
            axis.grid(alpha=.2)
        axes[0].legend(ncol=6, loc="upper right")
        axes[-1].set(
            xlabel="Track-local first-scatter depth z (mm)", xlim=E1_DEPTH_RANGE_MM
        )
        save_figure(
            fig,
            figures / f"E1_depth_response_{int(bin_width)}mm",
            include_pdf=False,
        )

    fixed_regions = {
        profile_id: [
            {
                "slit_id": region.slit_id,
                "x_range_mm": [region.x_min_mm, region.x_max_mm],
                "y_range_mm": [region.y_min_mm, region.y_max_mm],
            }
            for region in acceptance_regions_for_profile(profile_id)
        ]
        for profile_id in PROFILE_SLITS
    }
    write_manifest(root, "E1", {
        "input_source": "audited valid-event CSV selected by condition inventory",
        "input_layer": "events/valid",
        "input_files": input_files,
        "valid_events_manifest": "events/valid/valid_events_manifest.yaml",
        "phantom_id": "P0",
        "scan_mode": "center",
        "slit_identity_column": "slit_label",
        "slit_identity_rule": "use existing slit_label; never derive or reassign from detector position",
        "depth_bin_widths_mm": list(E1_BIN_WIDTHS_MM),
        "depth_range_mm": list(E1_DEPTH_RANGE_MM),
        "depth_interval_rule": "left-closed-right-open",
        "normalization": "independent integral normalization within each slit and scatter class",
        "zero_denominator_rule": "NaN",
        "poisson_statistics": {
            "sigma": "sqrt(raw_count)",
            "relative_error": "1/sqrt(raw_count); NaN when raw_count is zero",
        },
        "peak_tie_rule": "shallowest maximum bin center",
        "roi_interval_rule": "closed in detector x and y",
        "roi_selection_rule": "existing slit_label AND fixed geometry ROI",
        "fixed_acceptance_regions": fixed_regions,
        "design_depth_mm": SLIT_DESIGN_DEPTH_MM,
        "design_depth_region_rule": "left-closed-right-open: depth-5 <= first_scatter_z < depth+5",
        "count_unit": "detected gamma hit",
        "scatter_classes": {
            "total": "scatter_count_total >= 1",
            "k1": "scatter_count_total == 1",
            "ms": "scatter_count_total >= 2",
        },
        "scatter_history": "track-local; secondary gamma does not inherit parent history",
        "figure_formats": ["png"],
        "data_quality": {
            "total_equals_k1_plus_ms": True,
            "slit_group_and_label_validation": True,
            "histogram_outside_range_count_by_slit_class": outside_range_counts,
        },
    }, ctx.warnings)


def write_report(root: Path, warnings: list[str]) -> None:
    counts = pd.read_csv(root / "tables" / "E1_event_counts.csv")
    lines = [
        "# Article V2 E1 Analysis Results",
        "",
        "## Outputs",
        "",
        "| Design item | Artifact |",
        "|---|---|",
        "| Detector plane distribution | `figures/E1_detector_plane_distribution.png` |",
        "| Normalized depth response (2 mm) | `figures/E1_depth_response_2mm.png` |",
        "| Normalized depth response (4 mm) | `figures/E1_depth_response_4mm.png` |",
        "",
        "## Event counts",
        "",
        "| Slit | Design depth (mm) | total | k1 | MS | k1 fraction | MS fraction |",
        "|---|---:|---:|---:|---:|---:|---:|",
    ]
    for row in counts.itertuples(index=False):
        lines.append(
            f"| {row.slit} | {row.design_depth_mm:g} | {row.total_count} | "
            f"{row.k1_count} | {row.ms_count} | {row.k1_fraction:.6g} | "
            f"{row.ms_fraction:.6g} |"
        )
    valid = bool((counts.total_count == counts.k1_count + counts.ms_count).all())
    lines.extend([
        "",
        f"E1 event-accounting checks: **{'pass' if valid else 'fail'}**.",
        "",
        "## Warnings",
        "",
    ])
    lines.extend([f"- {item}" for item in warnings] if warnings else ["- None."])
    lines.append("")
    (root / "report.md").write_text("\n".join(lines), encoding="utf-8")


def validate_generated_outputs(root: Path) -> dict[str, Any]:
    expected_files = {
        "analysis_manifest.yaml",
        "report.md",
        "tables/E1_event_counts.csv",
        "tables/E1_depth_profiles_2mm.csv",
        "tables/E1_depth_profiles_4mm.csv",
        "tables/E1_peak_summary.csv",
        "tables/E1_design_depth_fraction.csv",
        "tables/E1_binning_comparison.csv",
        "figures/E1_detector_plane_distribution.png",
        "figures/E1_depth_response_2mm.png",
        "figures/E1_depth_response_4mm.png",
    }
    actual_files = {
        path.relative_to(root).as_posix()
        for path in root.rglob("*")
        if path.is_file()
    }
    checks: dict[str, Any] = {
        "E1_output_contract": {
            "actual": sorted(actual_files),
            "expected": sorted(expected_files),
            "pass": actual_files == expected_files,
        }
    }

    counts = pd.read_csv(root / "tables" / "E1_event_counts.csv")
    fractions = counts.k1_fraction + counts.ms_fraction
    conservation = bool(
        len(counts) == 6
        and set(counts.slit) == {f"S{index}" for index in range(1, 7)}
        and (counts.total_count == counts.k1_count + counts.ms_count).all()
        and np.allclose(fractions[counts.total_count > 0], 1.0)
    )
    checks["E1_event_accounting"] = {
        "actual": conservation,
        "expected": True,
        "pass": conservation,
    }

    for width, expected_rows, expected_bins in ((2, 1980, 110), (4, 990, 55)):
        data = pd.read_csv(root / f"tables/E1_depth_profiles_{width}mm.csv")
        bins = data[["bin_left_mm", "bin_right_mm"]].drop_duplicates().sort_values(
            "bin_left_mm"
        )
        groups = data.groupby(["slit", "scatter_class"], sort=False)
        group_totals = groups.raw_count.sum()
        normalized_sums = groups.normalized_count.sum(min_count=1)
        histogram_valid = bool(
            len(data) == expected_rows
            and len(bins) == expected_bins
            and bins.bin_left_mm.iloc[0] == E1_DEPTH_RANGE_MM[0]
            and bins.bin_right_mm.iloc[-1] == E1_DEPTH_RANGE_MM[1]
            and np.allclose((bins.bin_right_mm - bins.bin_left_mm).to_numpy(), width)
        )
        normalized = bool(
            len(group_totals) == 18
            and (group_totals > 0).all()
            and np.allclose(normalized_sums.to_numpy(), 1.0)
        )
        positive = data.raw_count > 0
        poisson = bool(
            np.allclose(data.poisson_sigma, np.sqrt(data.raw_count))
            and data.loc[~positive, "relative_poisson_error"].isna().all()
            and np.allclose(
                data.loc[positive, "relative_poisson_error"],
                1.0 / np.sqrt(data.loc[positive, "raw_count"]),
            )
        )
        checks[f"E1_{width}mm_histogram"] = {
            "actual": {"rows": len(data), "bins": len(bins)},
            "expected": {"rows": expected_rows, "bins": expected_bins},
            "pass": histogram_valid,
        }
        checks[f"E1_{width}mm_normalization"] = {
            "actual": normalized,
            "expected": True,
            "pass": normalized,
        }
        checks[f"E1_{width}mm_poisson"] = {
            "actual": poisson,
            "expected": True,
            "pass": poisson,
        }

    peaks = pd.read_csv(root / "tables" / "E1_peak_summary.csv")
    design = pd.read_csv(root / "tables" / "E1_design_depth_fraction.csv")
    comparison = pd.read_csv(root / "tables" / "E1_binning_comparison.csv")
    summary_valid = bool(
        len(peaks) == 36
        and set(peaks.bin_width_mm) == {2.0, 4.0}
        and len(design) == 18
        and np.allclose(design.region_left_mm, design.design_depth_mm - 5.0)
        and np.allclose(design.region_right_mm, design.design_depth_mm + 5.0)
        and len(comparison) == 18
        and np.allclose(
            comparison.peak_shift_mm,
            comparison.peak_4mm - comparison.peak_2mm,
            equal_nan=True,
        )
    )
    checks["E1_summary_contract"] = {
        "actual": summary_valid,
        "expected": True,
        "pass": summary_valid,
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


def run_analysis(results_root: Path, audit_dir: Path, output_dir: Path) -> None:
    audit, inventory = validate_audit(audit_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    context = AnalysisContext(results_root, audit_dir, output_dir, inventory, audit)
    run_e1(context)
    write_report(output_dir, context.warnings)
    validate_generated_outputs(output_dir)
    manifest_path = output_dir / "analysis_manifest.yaml"
    manifest = yaml.safe_load(manifest_path.read_text(encoding="utf-8"))
    manifest.update({
        "schema_version": 1,
        "analysis": "articlev2_e1_depth_response",
        "results_root": ".",
        "audit_summary": relative_to_campaign(
            audit_dir / "audit_summary.yaml", results_root
        ),
        "outputs": sorted(
            path.relative_to(output_dir).as_posix()
            for path in output_dir.rglob("*")
            if path.is_file() and path != manifest_path
        ),
    })
    manifest_path.write_text(
        yaml.safe_dump(manifest, sort_keys=False, allow_unicode=True), encoding="utf-8"
    )


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
    parser.add_argument("--overwrite", action="store_true")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    results_root = args.results_root.resolve()
    audit_dir = (
        args.audit_dir or results_root / "data_processing" / "audit"
    ).resolve()
    output_dir = (
        args.output_dir or results_root / "postprocessing" / "E1"
    ).resolve()
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
    staging = Path(
        tempfile.mkdtemp(prefix=f".{output_dir.name}.staging-", dir=output_dir.parent)
    )
    try:
        run_analysis(results_root, audit_dir, staging)
        publish(staging, output_dir, args.overwrite)
    except Exception:
        shutil.rmtree(staging, ignore_errors=True)
        raise
    event_counts = pd.read_csv(output_dir / "tables" / "E1_event_counts.csv")
    print(event_counts.to_string(index=False))
    print(f"report: {output_dir / 'report.md'}")
    print(f"acceptance: {output_dir / 'acceptance_summary.yaml'}")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as error:
        print(f"E1 analysis error: {error}", file=sys.stderr)
        raise SystemExit(1) from error
