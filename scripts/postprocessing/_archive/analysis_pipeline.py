#!/usr/bin/env python3
"""Paper-grade Article V2 post-processing for E1-E4, E5-A, and E6."""

from __future__ import annotations

import math
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

os.environ.setdefault("MPLCONFIGDIR", "/tmp/mss_matplotlib")
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import yaml
from matplotlib.patches import Rectangle

from _common import (
    PROFILE_SLITS,
    SLIT_PROFILE,
    DetectorAcceptanceRegion,
    RunMetadata,
    acceptance_regions_for_profile,
    load_run_metadata,
)
from articlev2_design import (
    DEFECT_CENTER_Z_MM,
    E6_TARGETS,
    GRID_OFFSETS_MM,
    SLIT_DESIGN_DEPTH_MM,
    target_z_range,
)


CLASSES = ("total", "k1", "ms")
REGIONS = ("front", "target", "behind")
E1_DEPTH_RANGE_MM = (0.0, 220.0)
E1_BIN_WIDTHS_MM = (2.0, 4.0)
E1_PLOT_CLASSES = ("k1", "total", "ms")
E3_DEPTH_EDGES = np.arange(0.0, 222.0, 2.0)
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
    _cache: dict[str, pd.DataFrame] = field(default_factory=dict)
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

    def events(self, row: pd.Series) -> pd.DataFrame:
        path = (self.results_root / row.clean_file).resolve()
        key = path.as_posix()
        if key not in self._cache:
            frame = pd.read_csv(path)
            numeric = [
                "det_energy", "scatter_count_total", "first_scatter_x", "first_scatter_y",
                "first_scatter_z", "last_scatter_x", "last_scatter_y", "last_scatter_z",
            ]
            for column in numeric:
                frame[column] = pd.to_numeric(frame[column], errors="raise")
            self._cache[key] = frame
        return self._cache[key]

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

    def slit_events(self, mode: str, phantom: str, slit: str, x: float = 0, y: float = 0) -> pd.DataFrame:
        row = self.run_row(mode, phantom, SLIT_PROFILE[slit], x, y)
        return self.events(row)[lambda data: data.slit_id == slit].copy()


def validate_audit(audit_dir: Path, experiments: tuple[str, ...]) -> tuple[dict[str, Any], pd.DataFrame]:
    summary_path = audit_dir / "audit_summary.yaml"
    inventory_path = audit_dir / "condition_inventory.csv"
    if not summary_path.is_file() or not inventory_path.is_file():
        raise FileNotFoundError("audit_summary.yaml and condition_inventory.csv are required")
    audit = yaml.safe_load(summary_path.read_text(encoding="utf-8"))
    if audit.get("overall_status") != "pass":
        raise ValueError("articlev2 audit must pass before analysis")
    for experiment in experiments:
        key = "E5" if experiment == "E5A" else experiment
        status = audit["experiments"][key]["status"]
        if experiment != "E5A" and status != "ready":
            raise ValueError(f"audit status for {experiment} is {status}, expected ready")
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


def region_labels(z: pd.Series, phantom: str) -> pd.Series:
    bounds = target_z_range(phantom)
    if bounds is None:
        raise ValueError(f"phantom has no target range: {phantom}")
    low, high = bounds
    return pd.Series(np.where(z < low, "front", np.where(z < high, "target", "behind")), index=z.index)


def safe_relative(defect: float, baseline: float, warnings: list[str], label: str) -> float:
    if baseline == 0:
        warnings.append(f"zero baseline: {label}")
        return math.nan
    return (defect - baseline) / baseline


def fwhm(bin_centers: np.ndarray, counts: np.ndarray) -> float:
    if len(counts) < 3 or np.max(counts) <= 0:
        return math.nan
    peak = int(np.argmax(counts)); half = counts[peak] / 2.0
    left = peak
    while left > 0 and counts[left] >= half:
        left -= 1
    right = peak
    while right < len(counts) - 1 and counts[right] >= half:
        right += 1
    if left == 0 and counts[left] >= half or right == len(counts) - 1 and counts[right] >= half:
        return math.nan
    def cross(i0: int, i1: int) -> float:
        x0, x1 = bin_centers[i0], bin_centers[i1]; y0, y1 = counts[i0], counts[i1]
        return float(x0 + (half - y0) * (x1 - x0) / (y1 - y0)) if y1 != y0 else float((x0 + x1) / 2)
    return cross(right, right - 1) - cross(left, left + 1)


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


def center_counts(ctx: AnalysisContext) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    for phantom in ("P0", "P1", "P2", "P3", "P4", "P5", "P6"):
        for slit_index in range(1, 7):
            slit = f"S{slit_index}"; frame = ctx.slit_events("center", phantom, slit)
            for category in CLASSES:
                count = int(class_mask(frame, category).sum())
                rows.append({"phantom_id": phantom, "slit_id": slit, "class": category,
                             "count": count, "sqrt_N": math.sqrt(count)})
    return pd.DataFrame(rows)


def count_value(counts: pd.DataFrame, phantom: str, slit: str, category: str) -> int:
    rows = counts[(counts.phantom_id == phantom) & (counts.slit_id == slit) & (counts["class"] == category)]
    if len(rows) != 1:
        raise ValueError(f"expected one count row for {phantom}-{slit}-{category}")
    return int(rows.iloc[0]["count"])


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
    root = ctx.output_root / "E1"
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
        input_files.append(ctx.valid_event_path(run).as_posix())
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
        "input_layer": "valid_events",
        "input_files": input_files,
        "valid_events_manifest": (
            ctx.results_root / "valid_events" / "valid_events_manifest.yaml"
        ).as_posix(),
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


def _heatmap(matrix: np.ndarray, title: str, path: Path) -> None:
    vmax = float(np.nanmax(np.abs(matrix))) if np.isfinite(matrix).any() else 1.0
    fig, ax = plt.subplots(figsize=(7, 5.5)); image = ax.imshow(matrix, cmap="RdBu_r", vmin=-vmax, vmax=vmax)
    ax.set_xticks(range(6), [f"S{i}" for i in range(1, 7)]); ax.set_yticks(range(6), [f"P{i}" for i in range(1, 7)])
    ax.set_xlabel("Slit channel"); ax.set_ylabel("Defect phantom") ; ax.set_title(title)
    for y in range(6):
        for x in range(6):
            text = "NA" if not np.isfinite(matrix[y, x]) else f"{matrix[y, x]:+.1%}"
            ax.text(x, y, text, ha="center", va="center", fontsize=8)
    fig.colorbar(image, ax=ax, label="Relative response")
    save_figure(fig, path)


def run_e2(ctx: AnalysisContext, counts: pd.DataFrame) -> None:
    root = ctx.output_root / "E2"; tables, figures = ensure_dirs(root); rows = []
    for p in range(1, 7):
        for s in range(1, 7):
            for category in CLASSES:
                n0 = count_value(counts, "P0", f"S{s}", category)
                nd = count_value(counts, f"P{p}", f"S{s}", category)
                rows.append({"phantom_id": f"P{p}", "slit_id": f"S{s}", "class": category,
                             "N_control": n0, "N_defect": nd, "sqrt_N_control": math.sqrt(n0),
                             "sqrt_N_defect": math.sqrt(nd), "relative_response": safe_relative(nd, n0, ctx.warnings, f"E2 P{p}-S{s}-{category}"),
                             "matched": p == s})
    response = pd.DataFrame(rows); response.to_csv(tables / "response_matrix_long.csv", index=False)
    representatives = response[(response.matched) | (((response.phantom_id == "P1") & (response.slit_id == "S6")) | ((response.phantom_id == "P6") & (response.slit_id == "S1")))]
    representatives.to_csv(tables / "representative_pairs.csv", index=False)
    for category in CLASSES:
        data = response[response["class"] == category]
        matrix = data.pivot(index="phantom_id", columns="slit_id", values="relative_response").reindex(index=[f"P{i}" for i in range(1,7)], columns=[f"S{i}" for i in range(1,7)]).to_numpy()
        _heatmap(matrix, f"E2 {category} defect response", figures / f"{category}_response_matrix")
    write_manifest(root, "E2", {"response": "(N_defect-N_control)/N_control", "matrix_cells": 108}, ctx.warnings)


def matched_region_data(ctx: AnalysisContext) -> tuple[pd.DataFrame, pd.DataFrame]:
    profile_rows: list[dict[str, Any]] = []; region_rows: list[dict[str, Any]] = []
    centers = (E3_DEPTH_EDGES[:-1] + E3_DEPTH_EDGES[1:]) / 2
    for p in range(1, 7):
        phantom, slit = f"P{p}", f"S{p}"
        for role, source in (("control", "P0"), ("defect", phantom)):
            frame = ctx.slit_events("center", source, slit); labels = region_labels(frame.first_scatter_z, phantom)
            for category in ("k1", "ms"):
                mask = class_mask(frame, category); values = frame.loc[mask, "first_scatter_z"].to_numpy()
                histogram, _ = np.histogram(values, bins=E3_DEPTH_EDGES)
                for index, count in enumerate(histogram):
                    profile_rows.append({"phantom_id": phantom, "slit_id": slit, "role": role,
                                         "class": category, "bin_left_mm": E3_DEPTH_EDGES[index],
                                         "bin_right_mm": E3_DEPTH_EDGES[index + 1], "bin_center_mm": centers[index],
                                         "count": int(count)})
                for region in REGIONS:
                    count = int((mask & (labels == region)).sum())
                    region_rows.append({"phantom_id": phantom, "slit_id": slit, "role": role,
                                        "class": category, "region": region, "count": count})
    profiles = pd.DataFrame(profile_rows); regions = pd.DataFrame(region_rows)
    enriched = []; zero_profile_baselines = 0
    for keys, group in profiles.groupby(["phantom_id", "slit_id", "class", "bin_left_mm", "bin_right_mm", "bin_center_mm"]):
        values = dict(zip(group.role, group["count"])); n0, nd = values["control"], values["defect"]
        if n0 == 0:
            zero_profile_baselines += 1
        enriched.append(dict(zip(["phantom_id", "slit_id", "class", "bin_left_mm", "bin_right_mm", "bin_center_mm"], keys),
                             N_control=n0, N_defect=nd, difference=nd-n0,
                             ratio=nd/n0 if n0 else math.nan))
    region_enriched = []
    for keys, group in regions.groupby(["phantom_id", "slit_id", "class", "region"]):
        values = dict(zip(group.role, group["count"])); n0, nd = values["control"], values["defect"]
        region_enriched.append(dict(zip(["phantom_id", "slit_id", "class", "region"], keys),
                                    N_control=n0, N_defect=nd,
                                    relative_response=safe_relative(nd, n0, ctx.warnings, f"E3 {keys}")))
    if zero_profile_baselines:
        ctx.warnings.append(
            f"E3 depth ratio is NA in {zero_profile_baselines} bin(s) with zero P0 baseline; differences remain available"
        )
    return pd.DataFrame(enriched), pd.DataFrame(region_enriched)


def run_e3(ctx: AnalysisContext, counts: pd.DataFrame, profiles: pd.DataFrame, regions: pd.DataFrame) -> None:
    root = ctx.output_root / "E3"; tables, figures = ensure_dirs(root)
    summary_rows = []
    for p in range(1, 7):
        for category in CLASSES:
            slit, phantom = f"S{p}", f"P{p}"
            n0 = count_value(counts, "P0", slit, category)
            nd = count_value(counts, phantom, slit, category)
            summary_rows.append({"phantom_id": phantom, "slit_id": slit, "class": category,
                                 "N_control": n0, "N_defect": nd,
                                 "relative_response": safe_relative(nd, n0, ctx.warnings, f"E3 {phantom}-{slit}-{category}")})
    summary = pd.DataFrame(summary_rows)
    summary.to_csv(tables / "matched_count_response.csv", index=False)
    profiles.to_csv(tables / "matched_depth_profiles.csv", index=False)
    regions.to_csv(tables / "source_region_counts.csv", index=False)
    # Conservation against direct matched k1/ms counts.
    for p in range(1, 7):
        for category in ("k1", "ms"):
            for role, source in (("control", "P0"), ("defect", f"P{p}")):
                regional = regions[(regions.phantom_id == f"P{p}") & (regions["class"] == category)]
                column = "N_control" if role == "control" else "N_defect"
                regional_total = int(regional[column].sum())
                direct = count_value(counts, source, f"S{p}", category)
                if regional_total != direct:
                    raise AssertionError(f"E3 region conservation failed for {source}-S{p}-{category}")
    fig, axes = plt.subplots(1, 3, figsize=(12, 4), sharex=True)
    for axis, category in zip(axes, CLASSES):
        data = summary[summary["class"] == category]
        axis.bar(range(1, 7), data.relative_response, color=COLORS[:6]); axis.axhline(0, color="black", lw=.8)
        axis.set_title(category); axis.set_xlabel("Matched depth index"); axis.set_ylabel("Relative response")
    save_figure(fig, figures / "matched_count_response")
    fig, axes = plt.subplots(2, 3, figsize=(13, 7), sharex=True)
    for p, axis in enumerate(axes.flat, start=1):
        for category, color in (("k1", COLORS[0]), ("ms", COLORS[1])):
            data = profiles[(profiles.phantom_id == f"P{p}") & (profiles["class"] == category)]
            axis.plot(data.bin_center_mm, data.difference, label=category, color=color)
        low, high = target_z_range(f"P{p}"); axis.axvspan(low, high, color="grey", alpha=.2)
        axis.axhline(0, color="black", lw=.6); axis.set_title(f"P{p}-S{p}"); axis.set_xlim(0, 110)
    axes[0,0].legend(); fig.supxlabel("First-scatter depth z (mm)"); fig.supylabel("Defect - control hits / 2 mm")
    save_figure(fig, figures / "matched_depth_difference")
    p4 = profiles[profiles.phantom_id == "P4"]
    fig, axes = plt.subplots(2, 2, figsize=(11, 7), sharex=True)
    for row, category in enumerate(("k1", "ms")):
        data = p4[p4["class"] == category]
        axes[row,0].plot(data.bin_center_mm, data.N_control, label="P0"); axes[row,0].plot(data.bin_center_mm, data.N_defect, label="P4")
        axes[row,1].plot(data.bin_center_mm, data.difference, color=COLORS[1]); axes[row,1].axhline(0,color="black",lw=.6)
        for axis in axes[row]: axis.axvspan(55,65,color="grey",alpha=.2); axis.set_xlim(40,80)
        axes[row,0].set_ylabel(f"{category} hits / 2 mm")
    axes[0,0].legend(); axes[0,0].set_title("Detected profiles"); axes[0,1].set_title("Defect - control")
    save_figure(fig, figures / "P4_S4_target_detail")
    write_manifest(root, "E3", {"matched_pairs": 6, "target_interval": "left-closed-right-open", "depth_bin_mm": 2}, ctx.warnings)


def run_e4(ctx: AnalysisContext, regions: pd.DataFrame) -> None:
    root = ctx.output_root / "E4"; tables, figures = ensure_dirs(root)
    ms = regions[regions["class"] == "ms"].copy(); rows = []
    for phantom, group in ms.groupby("phantom_id"):
        for role, column in (("control", "N_control"), ("defect", "N_defect")):
            total = float(group[column].sum())
            for _, item in group.iterrows():
                rows.append({"phantom_id": phantom, "slit_id": item.slit_id, "role": role,
                             "region": item.region, "count": int(item[column]),
                             "fraction": item[column] / total if total else math.nan,
                             "relative_response": item.relative_response if role == "defect" else math.nan})
    composition = pd.DataFrame(rows); composition.to_csv(tables / "ms_region_composition.csv", index=False)
    # P4 event features.
    feature_rows = []; order_rows = []
    for role, source in (("control", "P0"), ("defect", "P4")):
        frame = ctx.slit_events("center", source, "S4"); frame = frame[class_mask(frame, "ms")].copy()
        frame["region"] = region_labels(frame.first_scatter_z, "P4")
        for region in REGIONS:
            selected = frame[frame.region == region]
            hist, edges = np.histogram(selected.det_energy, bins=np.arange(0, 570, 10))
            for i, count in enumerate(hist):
                feature_rows.append({"role": role, "region": region, "energy_left_keV": edges[i],
                                     "energy_right_keV": edges[i+1], "count": int(count)})
            labels = selected.scatter_count_total.map(lambda value: str(int(value)) if value <= 5 else "6+")
            counts = labels.value_counts()
            for order in ("2", "3", "4", "5", "6+"):
                order_rows.append({"role": role, "region": region, "scatter_order": order,
                                   "count": int(counts.get(order, 0))})
    energy = pd.DataFrame(feature_rows); orders = pd.DataFrame(order_rows)
    energy.to_csv(tables / "P4_S4_ms_energy_histogram.csv", index=False); orders.to_csv(tables / "P4_S4_ms_scatter_order.csv", index=False)
    fig, axes = plt.subplots(1, 2, figsize=(12, 4.5))
    defect = composition[composition.role == "defect"]
    bottom = np.zeros(6)
    for idx, region in enumerate(REGIONS):
        data = defect[defect.region == region].set_index("phantom_id").reindex([f"P{i}" for i in range(1,7)])
        axes[0].bar(range(1,7), data.fraction, bottom=bottom, label=region, color=COLORS[idx]); bottom += data.fraction.to_numpy()
        axes[1].plot(range(1,7), data.relative_response, marker="o", label=region, color=COLORS[idx])
    axes[0].set_ylabel("MS source fraction"); axes[1].set_ylabel("Relative response"); axes[1].axhline(0,color="black",lw=.7)
    for axis in axes: axis.set_xlabel("Matched depth index"); axis.set_xticks(range(1,7))
    axes[0].legend(); save_figure(fig, figures / "ms_source_region_response")
    fig, axes = plt.subplots(1, 2, figsize=(12, 4.5))
    for idx, region in enumerate(REGIONS):
        data = energy[(energy.role == "defect") & (energy.region == region)]
        axes[0].step(data.energy_left_keV, data["count"], where="post", label=region, color=COLORS[idx])
    pivot = orders[orders.role == "defect"].pivot(index="scatter_order", columns="region", values="count").reindex(["2","3","4","5","6+"])
    pivot.plot.bar(ax=axes[1], color=COLORS[:3]); axes[0].set_xlabel("Detected energy (keV)"); axes[0].set_ylabel("MS hits / 10 keV"); axes[0].legend()
    axes[1].set_xlabel("Track-local scatter order"); axes[1].set_ylabel("MS hits")
    save_figure(fig, figures / "P4_S4_ms_event_features")
    write_manifest(root, "E4", {"regions": list(REGIONS), "energy_bin_keV": 10, "scatter_order_bins": ["2","3","4","5","6+"]})


def run_e5a(ctx: AnalysisContext) -> None:
    root = ctx.output_root / "E5A"; tables, figures = ensure_dirs(root)
    frame = ctx.slit_events("center", "P0", "S4")
    selected = select_e5a(frame)
    if selected.empty:
        raise ValueError("E5-A selection is empty")
    selected["dx_mm"] = selected.last_scatter_x - selected.first_scatter_x
    selected["dy_mm"] = selected.last_scatter_y - selected.first_scatter_y
    selected["dz_mm"] = selected.last_scatter_z - selected.first_scatter_z
    selected["displacement_mm"] = np.sqrt(selected.dx_mm**2 + selected.dy_mm**2 + selected.dz_mm**2)
    columns = ["first_scatter_x","first_scatter_y","first_scatter_z","last_scatter_x","last_scatter_y","last_scatter_z",
               "dx_mm","dy_mm","dz_mm","displacement_mm","det_energy","scatter_count_total"]
    selected[columns].to_csv(tables / "target_source_ms_points.csv", index=False)
    quantities = ["first_scatter_x","first_scatter_y","first_scatter_z","last_scatter_x","last_scatter_y","last_scatter_z","displacement_mm"]
    summary = []
    for quantity in quantities:
        values = selected[quantity]
        row = {"quantity": quantity, "min": values.min(), "max": values.max()}
        row.update({f"q{q:02d}": values.quantile(q/100) for q in (5,25,50,75,95)})
        summary.append(row)
    pd.DataFrame(summary).to_csv(tables / "spatial_summary.csv", index=False)
    fig = plt.figure(figsize=(9,7)); ax = fig.add_subplot(111, projection="3d")
    ax.scatter(selected.last_scatter_x, selected.last_scatter_y, selected.last_scatter_z, s=12, alpha=.65, label="last scatter", color=COLORS[1])
    ax.scatter(selected.first_scatter_x, selected.first_scatter_y, selected.first_scatter_z, s=8, alpha=.5, label="first scatter", color=COLORS[0])
    ax.set(xlabel="x (mm)", ylabel="y (mm)", zlabel="z (mm)", xlim=(-500,500), ylim=(-500,500), zlim=(0,220)); ax.legend()
    save_figure(fig, figures / "first_last_scatter_3d")
    for axes_names in (("x","z"),("y","z")):
        a,b=axes_names; fig, ax=plt.subplots(figsize=(8,5.5))
        ax.scatter(selected[f"last_scatter_{a}"], selected[f"last_scatter_{b}"], s=16, alpha=.65, color=COLORS[1], label="last scatter")
        ax.scatter(selected[f"first_scatter_{a}"], selected[f"first_scatter_{b}"], s=10, alpha=.5, color=COLORS[0], label="first scatter")
        ax.axhspan(55,65,color="grey",alpha=.15); ax.set_xlabel(f"{a} (mm)"); ax.set_ylabel(f"{b} (mm)"); ax.legend()
        save_figure(fig, figures / f"{a}_{b}_projection")
    fig, axes = plt.subplots(1,2,figsize=(13,5))
    for axis, coordinate in zip(axes,("x","y")):
        image=axis.hist2d(selected[f"last_scatter_{coordinate}"], selected.last_scatter_z,
                          bins=[np.arange(-500,510,10),np.arange(0,230,10)], cmap="viridis")
        axis.axhspan(55,65,color="white",alpha=.15); axis.set_xlabel(f"last-scatter {coordinate} (mm)"); axis.set_ylabel("last-scatter z (mm)")
        fig.colorbar(image[3],ax=axis,label="hits / 10 mm bin")
    save_figure(fig, figures / "last_scatter_density")
    write_manifest(root, "E5A", {"phantom":"P0","slit":"S4","target_z_mm":[55,65],"spatial_bin_mm":10,"selected_events":len(selected),"outlier_filter":None})


def select_e5a(frame: pd.DataFrame) -> pd.DataFrame:
    return frame[(frame.scatter_count_total >= 2) & (frame.first_scatter_z >= 55) & (frame.first_scatter_z < 65)].copy()


def e6_image_values(k1: int, front: int, target: int, behind: int) -> dict[str, int]:
    raw = k1 + front + target + behind
    return {"raw": raw, "k1_only": k1, "front_corrected": raw - front,
            "non_target_corrected": k1 + target}


def _grid_components(ctx: AnalysisContext, phantom: str, slit: str, target_phantom: str) -> pd.DataFrame:
    rows=[]
    for x in GRID_OFFSETS_MM:
        for y in GRID_OFFSETS_MM:
            frame=ctx.slit_events("grid",phantom,slit,x,y); labels=region_labels(frame.first_scatter_z,target_phantom)
            k1=int((frame.scatter_count_total==1).sum()); ms=frame.scatter_count_total>=2
            comp={region:int((ms & (labels==region)).sum()) for region in REGIONS}
            images=e6_image_values(k1,comp["front"],comp["target"],comp["behind"])
            raw=images["raw"]; front_corrected=images["front_corrected"]; non_target=images["non_target_corrected"]
            if raw != len(frame) or front_corrected != k1+comp["target"]+comp["behind"]:
                raise AssertionError(f"E6 decomposition failed for {phantom}-{slit}-{x}-{y}")
            rows.append({"phantom_id":phantom,"target_phantom":target_phantom,"slit_id":slit,
                         "head_offset_x_mm":x,"head_offset_y_mm":y,"k1":k1,
                         "ms_front":comp["front"],"ms_target":comp["target"],"ms_behind":comp["behind"],
                         "raw":raw,"k1_only":k1,"front_corrected":front_corrected,
                         "non_target_corrected":non_target,"target_oracle":int(((frame.scatter_count_total>=1)&(labels=="target")).sum())})
    return pd.DataFrame(rows)


def _roi_metrics(frame: pd.DataFrame, strategy: str) -> dict[str, Any]:
    roi=(frame.head_offset_x_mm.between(-7.5,7.5,inclusive="both") & frame.head_offset_y_mm.between(-7.5,7.5,inclusive="both"))
    defect=frame.loc[roi,strategy]; background=frame.loc[~roi,strategy]
    if len(defect)!=49 or len(background)!=32: raise AssertionError("E6 ROI must contain 49/32 pixels")
    mu_d=float(defect.mean()); mu_b=float(background.mean()); sd=float(defect.std(ddof=1)); sb=float(background.std(ddof=1))
    contrast=(mu_b-mu_d)/mu_b if mu_b else math.nan; denominator=math.sqrt(sd*sd+sb*sb)
    return {"strategy":strategy,"roi_pixels":len(defect),"background_pixels":len(background),"mu_D":mu_d,"mu_B":mu_b,
            "sigma_D":sd,"sigma_B":sb,"contrast":contrast,"cnr":abs(mu_d-mu_b)/denominator if denominator else math.nan}


def run_e6(ctx: AnalysisContext) -> None:
    root=ctx.output_root/"E6"; tables,figures=ensure_dirs(root); all_components=[]; metric_rows=[]; composition_rows=[]
    strategies=("raw","k1_only","front_corrected","non_target_corrected","target_oracle")
    defect_frames={}
    for target,slit in E6_TARGETS:
        frames=[]
        for phantom in ("P0",target):
            data=_grid_components(ctx,phantom,slit,target); frames.append(data); all_components.append(data)
            total_ms=float(data[["ms_front","ms_target","ms_behind"]].to_numpy().sum())
            for region,column in (("front","ms_front"),("target","ms_target"),("behind","ms_behind")):
                count=int(data[column].sum()); composition_rows.append({"target_phantom":target,"slit_id":slit,"phantom_id":phantom,
                                                                       "region":region,"count":count,"fraction":count/total_ms if total_ms else math.nan})
        defect=frames[1]; defect_frames[target]=defect
        metrics=[{"target_phantom":target,"slit_id":slit,**_roi_metrics(defect,s)} for s in strategies]
        by={item["strategy"]:item for item in metrics}; raw_cnr=by["raw"]["cnr"]; k1_cnr=by["k1_only"]["cnr"]
        for item in metrics:
            item["cnr_change_vs_raw"]=(item["cnr"]-raw_cnr)/raw_cnr if raw_cnr else math.nan
            item["G_MS"] = by["non_target_corrected"]["cnr"]/k1_cnr if item["strategy"]=="non_target_corrected" and k1_cnr else math.nan
        metric_rows.extend(metrics)
        core=("raw","k1_only","front_corrected","non_target_corrected"); vmin=min(float(defect[s].min()) for s in core); vmax=max(float(defect[s].max()) for s in core)
        fig,axes=plt.subplots(2,2,figsize=(10,8),sharex=True,sharey=True)
        for axis,strategy in zip(axes.flat,core):
            matrix=defect.pivot(index="head_offset_y_mm",columns="head_offset_x_mm",values=strategy).reindex(index=GRID_OFFSETS_MM,columns=GRID_OFFSETS_MM)
            im=axis.imshow(matrix.to_numpy(),origin="lower",extent=(-11.25,11.25,-11.25,11.25),vmin=vmin,vmax=vmax,cmap="viridis",interpolation="none")
            axis.set_title(strategy.replace("_"," ")); axis.set_xlabel("x offset (mm)"); axis.set_ylabel("y offset (mm)")
        fig.colorbar(im,ax=axes.ravel().tolist(),label="Detected hits"); fig.suptitle(f"{target}-{slit} oracle MS correction")
        save_figure(fig,figures/f"{target}_{slit}_core_images")
        fig,ax=plt.subplots(figsize=(5.5,5)); matrix=defect.pivot(index="head_offset_y_mm",columns="head_offset_x_mm",values="target_oracle").reindex(index=GRID_OFFSETS_MM,columns=GRID_OFFSETS_MM)
        im=ax.imshow(matrix.to_numpy(),origin="lower",extent=(-11.25,11.25,-11.25,11.25),cmap="viridis",interpolation="none"); fig.colorbar(im,ax=ax,label="Detected hits")
        ax.set(title=f"{target}-{slit} target-source oracle",xlabel="x offset (mm)",ylabel="y offset (mm)"); save_figure(fig,figures/f"{target}_{slit}_target_oracle")
    components=pd.concat(all_components,ignore_index=True); metrics=pd.DataFrame(metric_rows); composition=pd.DataFrame(composition_rows)
    components.to_csv(tables/"pose_decomposition_and_images.csv",index=False); metrics.to_csv(tables/"image_quality_metrics.csv",index=False); composition.to_csv(tables/"ms_source_composition.csv",index=False)
    fig,axes=plt.subplots(1,2,figsize=(12,4.5)); core=("raw","k1_only","front_corrected","non_target_corrected")
    x=np.arange(3); width=.18
    for i,strategy in enumerate(core):
        data=metrics[metrics.strategy==strategy].set_index("target_phantom").reindex(["P2","P4","P6"])
        axes[0].bar(x+(i-1.5)*width,data.cnr,width,label=strategy); axes[1].bar(x+(i-1.5)*width,data.contrast,width,label=strategy)
    for axis,title in zip(axes,("CNR","Contrast")): axis.set_xticks(x,["P2-S2","P4-S4","P6-S6"]); axis.set_title(title); axis.grid(axis="y",alpha=.2)
    axes[0].legend(fontsize=8); save_figure(fig,figures/"quality_metrics")
    fig,ax=plt.subplots(figsize=(9,5)); p0=composition[composition.phantom_id=="P0"]; positions=np.arange(3); bottom=np.zeros(3)
    for i,region in enumerate(REGIONS):
        data=p0[p0.region==region].set_index("target_phantom").reindex(["P2","P4","P6"]); ax.bar(positions,data.fraction,bottom=bottom,label=region,color=COLORS[i]); bottom+=data.fraction.to_numpy()
    ax.set_xticks(positions,["S2","S4","S6"]); ax.set(ylabel="P0 MS source fraction",xlabel="Matched slit"); ax.legend(); save_figure(fig,figures/"P0_ms_source_composition")
    write_manifest(root,"E6",{"targets":[f"{p}-{s}" for p,s in E6_TARGETS],"grid_shape":[9,9],"roi_pixels":49,"background_pixels":32,"std_ddof":1,"interpolation":None})


RUNNERS: dict[str, Callable[..., None]] = {"E1":run_e1,"E2":run_e2,"E3":run_e3,"E4":run_e4,"E5A":run_e5a,"E6":run_e6}


def write_root_report(root: Path, experiments: tuple[str,...], warnings: list[str]) -> None:
    mapping={
        "E1 detector plane":"E1/figures/E1_detector_plane_distribution.png",
        "E1 normalized depth response (2 mm)":"E1/figures/E1_depth_response_2mm.png",
        "E1 normalized depth response (4 mm)":"E1/figures/E1_depth_response_4mm.png",
        "Figure 3 / Table 3 (E2)":"E2/figures/total_response_matrix.png; E2/tables/response_matrix_long.csv",
        "Figure 4 (E3)":"E3/figures/matched_depth_difference.png",
        "Figure 5 / Table 4 (E3/E4)":"E4/figures/ms_source_region_response.png; E4/tables/ms_region_composition.csv",
        "Figure 6 (E5-A)":"E5A/figures/first_last_scatter_3d.png",
        "Figure 7 / full Table 5":"unavailable: P4_off / E5-B data are missing",
        "Figure 8 (E6)":"E6/figures/P2_S2_core_images.png (plus P4/P6)",
        "Figure 9 (E6)":"E6/figures/P0_ms_source_composition.png",
        "Figure 10 / Table 6 (E6)":"E6/figures/quality_metrics.png; E6/tables/image_quality_metrics.csv",
    }
    lines=["# Article V2 Analysis Results","",f"Completed experiments: {', '.join(experiments)}","","## Design-output map","","| Design item | Artifact |","|---|---|"]
    lines += [f"| {key} | `{value}` |" for key,value in mapping.items()]
    counts_path = root / "E1" / "tables" / "E1_event_counts.csv"
    if "E1" in experiments and counts_path.is_file():
        counts = pd.read_csv(counts_path)
        lines += [
            "", "## E1 event counts", "",
            "The 2 mm and 4 mm profiles are independently normalized within each slit and "
            "scatter class. Absolute geometry-ROI counts are retained below.", "",
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
        lines += ["", f"E1 event-accounting checks: **{'pass' if valid else 'fail'}**."]
    lines += ["","## Warnings",""] + ([f"- {item}" for item in warnings] if warnings else ["- None."]) + [""]
    (root/"report.md").write_text("\n".join(lines),encoding="utf-8")


def validate_generated_outputs(root: Path, experiments: tuple[str,...]) -> dict[str, Any]:
    checks: dict[str, Any] = {}
    if "E1" in experiments:
        e1_root = root / "E1"
        expected_files = {
            "analysis_manifest.yaml",
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
            path.relative_to(e1_root).as_posix()
            for path in e1_root.rglob("*")
            if path.is_file()
        }
        output_contract = actual_files == expected_files
        checks["E1_output_contract"] = {
            "actual": sorted(actual_files), "expected": sorted(expected_files),
            "pass": output_contract,
        }

        counts = pd.read_csv(e1_root / "tables/E1_event_counts.csv")
        fractions = counts.k1_fraction + counts.ms_fraction
        conservation = bool(
            len(counts) == 6
            and set(counts.slit) == {f"S{index}" for index in range(1, 7)}
            and (counts.total_count == counts.k1_count + counts.ms_count).all()
            and np.allclose(fractions[counts.total_count > 0], 1.0)
        )
        checks["E1_event_accounting"] = {
            "actual": conservation, "expected": True, "pass": conservation,
        }

        for width, expected_rows, expected_bins in ((2, 1980, 110), (4, 990, 55)):
            data = pd.read_csv(e1_root / f"tables/E1_depth_profiles_{width}mm.csv")
            bins = data[["bin_left_mm", "bin_right_mm"]].drop_duplicates().sort_values("bin_left_mm")
            groups = data.groupby(["slit", "scatter_class"], sort=False)
            group_totals = groups.raw_count.sum()
            normalized_sums = groups.normalized_count.sum(min_count=1)
            bin_contract = bool(
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
                "pass": bin_contract,
            }
            checks[f"E1_{width}mm_normalization"] = {
                "actual": normalized, "expected": True, "pass": normalized,
            }
            checks[f"E1_{width}mm_poisson"] = {
                "actual": poisson, "expected": True, "pass": poisson,
            }

        peaks = pd.read_csv(e1_root / "tables/E1_peak_summary.csv")
        design = pd.read_csv(e1_root / "tables/E1_design_depth_fraction.csv")
        comparison = pd.read_csv(e1_root / "tables/E1_binning_comparison.csv")
        summary_contract = bool(
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
            "actual": summary_contract, "expected": True, "pass": summary_contract,
        }
    if "E2" in experiments:
        data=pd.read_csv(root/"E2/tables/response_matrix_long.csv"); checks["E2_rows"]={"actual":len(data),"expected":108,"pass":len(data)==108}
    if "E3" in experiments:
        data=pd.read_csv(root/"E3/tables/source_region_counts.csv")
        checks["E3_region_rows"]={"actual":len(data),"expected":36,"pass":len(data)==36}
    if "E4" in experiments:
        data=pd.read_csv(root/"E4/tables/ms_region_composition.csv")
        sums=data.groupby(["phantom_id","role"])["fraction"].sum()
        valid=bool(np.allclose(sums.to_numpy(),1.0,rtol=0,atol=1e-12))
        checks["E4_fraction_conservation"]={"actual":valid,"expected":True,"pass":valid}
    if "E5A" in experiments:
        data=pd.read_csv(root/"E5A/tables/target_source_ms_points.csv"); valid=bool(len(data)>0 and (data.scatter_count_total>=2).all() and (data.first_scatter_z>=55).all() and (data.first_scatter_z<65).all())
        checks["E5A_selection"]={"actual":len(data),"expected":">0 and all filters true","pass":valid}
    if "E6" in experiments:
        data=pd.read_csv(root/"E6/tables/pose_decomposition_and_images.csv"); defect=data[data.phantom_id==data.target_phantom]
        algebra=((data.raw==data.k1+data.ms_front+data.ms_target+data.ms_behind)&(data.front_corrected==data.raw-data.ms_front)&(data.non_target_corrected==data.k1+data.ms_target)).all()
        checks["E6_defect_poses"]={"actual":len(defect),"expected":243,"pass":len(defect)==243}
        checks["E6_algebra"]={"actual":bool(algebra),"expected":True,"pass":bool(algebra)}
        metrics=pd.read_csv(root/"E6/tables/image_quality_metrics.csv"); roi=bool((metrics.roi_pixels==49).all() and (metrics.background_pixels==32).all())
        checks["E6_roi"]={"actual":roi,"expected":True,"pass":roi}
    passed=all(item["pass"] for item in checks.values()); result={"overall_status":"pass" if passed else "fail","checks":checks}
    (root/"acceptance_summary.yaml").write_text(yaml.safe_dump(result,sort_keys=False,allow_unicode=True),encoding="utf-8")
    if not passed: raise AssertionError("generated analysis failed acceptance checks")
    return result


def run_pipeline(results_root: Path,audit_dir: Path,output_root: Path,experiments: tuple[str,...]) -> None:
    audit,inventory=validate_audit(audit_dir,experiments); output_root.mkdir(parents=True,exist_ok=True)
    ctx=AnalysisContext(results_root,audit_dir,output_root,inventory,audit); counts=None; profiles=None; regions=None
    if any(e in experiments for e in ("E2","E3","E4")): counts=center_counts(ctx)
    if any(e in experiments for e in ("E3","E4")): profiles,regions=matched_region_data(ctx)
    for experiment in experiments:
        if experiment=="E1": run_e1(ctx)
        elif experiment=="E2": run_e2(ctx,counts)
        elif experiment=="E3": run_e3(ctx,counts,profiles,regions)
        elif experiment=="E4": run_e4(ctx,regions)
        elif experiment=="E5A": run_e5a(ctx)
        elif experiment=="E6": run_e6(ctx)
    write_root_report(output_root,experiments,ctx.warnings)
    validate_generated_outputs(output_root,experiments)
    manifest={"analysis":"articlev2_paper_analysis","experiments":list(experiments),"results_root":results_root.as_posix(),
              "audit_summary":(audit_dir/"audit_summary.yaml").as_posix(),"warnings":ctx.warnings,
              "outputs":sorted(path.relative_to(output_root).as_posix() for path in output_root.rglob("*") if path.is_file() and path.name!="analysis_manifest.yaml")}
    (output_root/"analysis_manifest.yaml").write_text(yaml.safe_dump(manifest,sort_keys=False,allow_unicode=True),encoding="utf-8")
