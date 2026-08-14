#!/usr/bin/env python3
"""Generate the canonical Article V2 E2 paper figures and tables."""

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
from matplotlib.colors import Normalize

from scripts.data_processing.common import (
    SLIT_PROFILE,
    DetectorAcceptanceRegion,
    RunMetadata,
    acceptance_regions_for_profile,
    load_run_metadata,
)
from scripts.data_processing.experiment_contract import (
    CENTER_PHANTOM_IDS,
    DEFECT_CENTER_Z_MM,
    GRID_OFFSETS_MM,
    SLIT_DESIGN_DEPTH_MM,
    matched_slit,
    target_z_range,
)


CLASSES = ("total", "k1", "ms")
REGIONS = ("Front", "Target", "Behind")
SLIT_IDS = tuple(f"S{index}" for index in range(1, 7))
DEPTH_RANGE_MM = (0.0, 220.0)
DEFAULT_DEPTH_BIN_WIDTH_MM = 2.0
BASELINE_COLOR = "#0072B2"
DEFECT_COLOR = "#D55E00"
CLASS_COLORS = {"total": "#333333", "k1": "#0072B2", "ms": "#D55E00"}
GRID_FIGURE_NAME = "E2-F1_matched_grid_total_counts.png"
T1_TABLE_NAME = "E2-T1_center_raw_count_decomposition.csv"
T1_COLUMNS = (
    "depth_mm",
    "N0_total",
    "ND_total",
    "C_total",
    "N0_k1",
    "ND_k1",
    "C_k1",
    "N0_ms",
    "ND_ms",
    "C_ms",
)
T2_COLUMNS = ("scatter_class", "region", "N_r0", "N_rD", "C_r", "D_TV_r")
EVENT_COLUMNS = (
    "det_x",
    "det_y",
    "scatter_count_total",
    "first_scatter_z",
    "slit_group",
    "slit_label",
)


@dataclass(frozen=True)
class E2Case:
    baseline_phantom: str
    defect_phantom: str
    slit: str
    scatter_class: str

    @property
    def comparison_slug(self) -> str:
        return f"{self.baseline_phantom}-{self.slit}_vs_{self.defect_phantom}-{self.slit}"

    @property
    def selection_slug(self) -> str:
        return f"{self.comparison_slug}_{self.scatter_class}"

    @property
    def comparison_label(self) -> str:
        return (
            f"{self.baseline_phantom}–{self.slit} versus "
            f"{self.defect_phantom}–{self.slit}"
        )

    def as_dict(self) -> dict[str, str]:
        return {
            "baseline_phantom": self.baseline_phantom,
            "defect_phantom": self.defect_phantom,
            "slit": self.slit,
            "scatter_class": self.scatter_class,
        }


DEFAULT_CASE = E2Case("P0", "P4", "S4", "total")


def parse_case(value: str) -> E2Case:
    parts = value.split(":")
    if len(parts) != 4:
        raise argparse.ArgumentTypeError(
            "case must use BASELINE:DEFECT:SLIT:SCATTER_CLASS, for example P0:P4:S4:total"
        )
    case = E2Case(*(part.strip() for part in parts))
    if case.baseline_phantom not in CENTER_PHANTOM_IDS:
        raise argparse.ArgumentTypeError(
            f"baseline phantom must be one of {', '.join(CENTER_PHANTOM_IDS)}"
        )
    if case.defect_phantom not in DEFECT_CENTER_Z_MM:
        raise argparse.ArgumentTypeError("defect phantom must be one of P1-P6")
    if case.baseline_phantom == case.defect_phantom:
        raise argparse.ArgumentTypeError("baseline and defect phantoms must differ")
    expected_slit = matched_slit(case.defect_phantom)
    if case.slit != expected_slit:
        raise argparse.ArgumentTypeError(
            f"{case.defect_phantom} must use its matched slit {expected_slit}, got {case.slit}"
        )
    if case.scatter_class not in CLASSES:
        raise argparse.ArgumentTypeError(
            f"scatter class must be one of {', '.join(CLASSES)}"
        )
    return case


def normalize_cases(cases: list[E2Case] | tuple[E2Case, ...] | None) -> tuple[E2Case, ...]:
    normalized = tuple(cases) if cases else (DEFAULT_CASE,)
    if len(set(normalized)) != len(normalized):
        raise ValueError("duplicate --case selections are not allowed")
    return normalized


def figure_names(cases: tuple[E2Case, ...]) -> tuple[str, ...]:
    names = [GRID_FIGURE_NAME]
    for case in cases:
        names.extend(
            (
                f"E2-F2_{case.selection_slug}_binwise_relative_response.png",
                f"E2-F3_{case.selection_slug}_raw_depth_counts.png",
                f"E2-F4_{case.selection_slug}_source_region_decomposition.png",
            )
        )
    return tuple(names)


def t2_table_name(case: E2Case) -> str:
    return f"E2-T2_{case.comparison_slug}_source_region_quantitative.csv"


def table_names(cases: tuple[E2Case, ...]) -> tuple[str, ...]:
    comparisons = dict.fromkeys(case.comparison_slug for case in cases)
    lookup = {case.comparison_slug: case for case in cases}
    return (T1_TABLE_NAME, *(t2_table_name(lookup[key]) for key in comparisons))


@dataclass
class AnalysisContext:
    results_root: Path
    audit_dir: Path
    output_root: Path
    inventory: pd.DataFrame
    audit: dict[str, Any]
    warnings: list[str] = field(default_factory=list)
    _center_cache: dict[str, pd.DataFrame] = field(default_factory=dict)
    _metadata_cache: dict[str, RunMetadata] = field(default_factory=dict)

    def condition_rows(self, mode: str, phantom: str, profile: str) -> pd.DataFrame:
        return self.inventory[
            (self.inventory.scan_mode == mode)
            & (self.inventory.phantom_id == phantom)
            & (self.inventory.profile_id == profile)
        ].copy()

    def center_row(self, phantom: str, profile: str) -> pd.Series:
        rows = self.condition_rows("center", phantom, profile)
        rows = rows[
            np.isclose(rows.head_offset_x_mm.astype(float), 0)
            & np.isclose(rows.head_offset_y_mm.astype(float), 0)
        ]
        if len(rows) != 1:
            raise ValueError(f"expected one center run for {(phantom, profile)}, found {len(rows)}")
        if rows.iloc[0]["status"] != "valid":
            raise ValueError(f"audit inventory marks center run invalid: {(phantom, profile)}")
        return rows.iloc[0]

    def valid_event_path(self, row: pd.Series) -> Path:
        path = (self.results_root / row.valid_file).resolve()
        if not path.is_file():
            raise FileNotFoundError(f"valid event file not found: {path}")
        return path

    def metadata(self, row: pd.Series) -> RunMetadata:
        path = self.valid_event_path(row).parent / "metadata.yaml"
        key = path.as_posix()
        if key not in self._metadata_cache:
            self._metadata_cache[key] = load_run_metadata(path)
        return self._metadata_cache[key]

    def events(self, row: pd.Series, *, cache_center: bool) -> pd.DataFrame:
        path = self.valid_event_path(row)
        key = path.as_posix()
        if cache_center and key in self._center_cache:
            return self._center_cache[key]
        try:
            frame = pd.read_csv(path, usecols=list(EVENT_COLUMNS))
        except ValueError as error:
            raise ValueError(f"valid events are missing required E2 columns: {path}") from error
        for column in ("det_x", "det_y", "scatter_count_total", "first_scatter_z"):
            frame[column] = pd.to_numeric(frame[column], errors="raise")
        numeric = frame[["det_x", "det_y", "scatter_count_total", "first_scatter_z"]].to_numpy(
            dtype=float
        )
        if not np.isfinite(numeric).all():
            raise ValueError(f"E2 numeric event columns must be finite: {path}")
        scatter_counts(frame)
        if cache_center:
            self._center_cache[key] = frame
        return frame


def validate_audit(audit_dir: Path) -> tuple[dict[str, Any], pd.DataFrame]:
    summary_path = audit_dir / "audit_summary.yaml"
    inventory_path = audit_dir / "condition_inventory.csv"
    if not summary_path.is_file() or not inventory_path.is_file():
        raise FileNotFoundError("audit_summary.yaml and condition_inventory.csv are required")
    audit = yaml.safe_load(summary_path.read_text(encoding="utf-8"))
    if audit.get("overall_status") != "pass":
        raise ValueError("articlev2 audit must pass before E2 analysis")
    status = audit.get("experiments", {}).get("E2", {}).get("status")
    if status != "ready":
        raise ValueError(f"audit status for E2 center inputs is {status}, expected ready")
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


def roi_for_slit(
    slit_id: str, offset_x_mm: float = 0.0, offset_y_mm: float = 0.0
) -> DetectorAcceptanceRegion:
    profile_id = SLIT_PROFILE[slit_id]
    matches = [
        region
        for region in acceptance_regions_for_profile(profile_id, offset_x_mm, offset_y_mm)
        if region.slit_id == slit_id
    ]
    if len(matches) != 1:
        raise AssertionError(f"expected one acceptance ROI for {slit_id}")
    return matches[0]


def roi_mask(frame: pd.DataFrame, region: DetectorAcceptanceRegion) -> pd.Series:
    return (
        frame.slit_label.astype(str).eq(region.slit_id)
        & frame.det_x.between(region.x_min_mm, region.x_max_mm, inclusive="both")
        & frame.det_y.between(region.y_min_mm, region.y_max_mm, inclusive="both")
    )


def selected_events(
    ctx: AnalysisContext,
    row: pd.Series,
    slit_id: str,
    *,
    cache_center: bool,
) -> pd.DataFrame:
    metadata = ctx.metadata(row)
    expected_profile = SLIT_PROFILE[slit_id]
    if metadata.profile_id != expected_profile:
        raise ValueError(
            f"{slit_id} requires {expected_profile}, got {metadata.profile_id}: {metadata.metadata_path}"
        )
    frame = ctx.events(row, cache_center=cache_center)
    if frame.slit_group.isna().any() or not frame.slit_group.astype(str).eq(expected_profile).all():
        raise ValueError(f"E2 slit_group must equal {expected_profile}: {metadata.metadata_path}")
    region = roi_for_slit(slit_id, metadata.head_offset_x_mm, metadata.head_offset_y_mm)
    selected = frame.loc[roi_mask(frame, region)].copy()
    if selected.empty:
        raise ValueError(f"E2 ROI selection is empty for {slit_id}: {metadata.metadata_path}")
    return selected


def count_classes(frame: pd.DataFrame) -> dict[str, int]:
    counts = {category: int(class_mask(frame, category).sum()) for category in CLASSES}
    if counts["total"] != counts["k1"] + counts["ms"]:
        raise AssertionError("E2 total != k1 + ms")
    return counts


def relative_change(defect_count: int, baseline_count: int, label: str) -> float:
    if baseline_count <= 0:
        raise ValueError(f"undefined relative response because baseline count is zero: {label}")
    return (defect_count - baseline_count) / baseline_count


def validate_depth_bin_width(depth_bin_width_mm: float) -> float:
    width = float(depth_bin_width_mm)
    if not (math.isfinite(width) and 0 < width <= DEPTH_RANGE_MM[1] - DEPTH_RANGE_MM[0]):
        raise ValueError("depth_bin_width_mm must be finite and satisfy 0 < width <= 220 mm")
    return width


def depth_edges(
    depth_bin_width_mm: float = DEFAULT_DEPTH_BIN_WIDTH_MM,
) -> np.ndarray:
    return anchored_edges(
        DEPTH_RANGE_MM[0], DEPTH_RANGE_MM[1], depth_bin_width_mm
    )


def case_target_range(case: E2Case) -> tuple[float, float]:
    value = target_z_range(case.defect_phantom)
    if value is None:
        raise ValueError(f"no target interval is defined for {case.defect_phantom}")
    return float(value[0]), float(value[1])


def region_mask(
    depths: pd.Series | np.ndarray,
    region: str,
    target_range: tuple[float, float] = (55.0, 65.0),
) -> np.ndarray:
    values = np.asarray(depths, dtype=float)
    target_low, target_high = target_range
    if region == "Front":
        return (values >= DEPTH_RANGE_MM[0]) & (values < target_low)
    if region == "Target":
        return (values >= target_low) & (values < target_high)
    if region == "Behind":
        return (values >= target_high) & (values <= DEPTH_RANGE_MM[1])
    raise ValueError(f"unknown source region: {region}")


def anchored_edges(
    start: float,
    end: float,
    depth_bin_width_mm: float = DEFAULT_DEPTH_BIN_WIDTH_MM,
) -> np.ndarray:
    if not (math.isfinite(start) and math.isfinite(end) and start < end):
        raise ValueError("region edge interval must satisfy finite start < end")
    width = validate_depth_bin_width(depth_bin_width_mm)
    edges = np.arange(start, end, width)
    if not edges.size or not math.isclose(float(edges[0]), start):
        edges = np.r_[start, edges]
    if math.isclose(float(edges[-1]), end):
        edges[-1] = end
    else:
        edges = np.r_[edges, end]
    return edges


def region_edges(
    region: str,
    target_range: tuple[float, float] = (55.0, 65.0),
    depth_bin_width_mm: float = DEFAULT_DEPTH_BIN_WIDTH_MM,
) -> np.ndarray:
    target_low, target_high = target_range
    if region == "Front":
        return anchored_edges(DEPTH_RANGE_MM[0], target_low, depth_bin_width_mm)
    if region == "Target":
        return anchored_edges(target_low, target_high, depth_bin_width_mm)
    if region == "Behind":
        return anchored_edges(target_high, DEPTH_RANGE_MM[1], depth_bin_width_mm)
    raise ValueError(f"unknown source region: {region}")


def within_region_tv_contributions(
    baseline_depths: np.ndarray,
    defect_depths: np.ndarray,
    region: str,
    label: str,
    target_range: tuple[float, float] = (55.0, 65.0),
    depth_bin_width_mm: float = DEFAULT_DEPTH_BIN_WIDTH_MM,
) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    edges = region_edges(region, target_range, depth_bin_width_mm)
    baseline_counts, _ = np.histogram(baseline_depths, bins=edges)
    defect_counts, _ = np.histogram(defect_depths, bins=edges)
    if baseline_counts.sum() != len(baseline_depths) or defect_counts.sum() != len(defect_depths):
        raise AssertionError(f"region histogram loses events: {label}")
    if baseline_counts.sum() == 0 or defect_counts.sum() == 0:
        raise ValueError(f"undefined within-region DTV because a histogram is empty: {label}")
    baseline_probability = baseline_counts / baseline_counts.sum()
    defect_probability = defect_counts / defect_counts.sum()
    contributions = 0.5 * np.abs(defect_probability - baseline_probability)
    return edges, baseline_counts, defect_counts, contributions


def within_region_tv(
    baseline_depths: np.ndarray,
    defect_depths: np.ndarray,
    region: str,
    label: str,
    target_range: tuple[float, float] = (55.0, 65.0),
    depth_bin_width_mm: float = DEFAULT_DEPTH_BIN_WIDTH_MM,
) -> float:
    _, _, _, contributions = within_region_tv_contributions(
        baseline_depths,
        defect_depths,
        region,
        label,
        target_range,
        depth_bin_width_mm,
    )
    return float(contributions.sum())


def binwise_relative_response(
    defect_counts: np.ndarray,
    baseline_counts: np.ndarray,
    *,
    min_baseline_count: int | None = None,
) -> np.ndarray:
    defect = np.asarray(defect_counts, dtype=float)
    baseline = np.asarray(baseline_counts, dtype=float)
    if defect.shape != baseline.shape:
        raise ValueError("baseline and defect histograms must have matching shapes")
    if not (np.isfinite(defect).all() and np.isfinite(baseline).all()):
        raise ValueError("bin counts must be finite")
    if (defect < 0).any() or (baseline < 0).any():
        raise ValueError("bin counts must be non-negative")
    if min_baseline_count is not None and min_baseline_count < 1:
        raise ValueError("min_baseline_count must be a positive integer")
    threshold = 1 if min_baseline_count is None else min_baseline_count
    response = np.full(baseline.shape, np.nan, dtype=float)
    valid = baseline >= threshold
    response[valid] = (defect[valid] - baseline[valid]) / baseline[valid]
    return response


def grid_edges() -> np.ndarray:
    offsets = np.asarray(GRID_OFFSETS_MM, dtype=float)
    half_step = (offsets[1] - offsets[0]) / 2
    return np.r_[offsets - half_step, offsets[-1] + half_step]


def expected_grid_conditions() -> tuple[tuple[str, str], ...]:
    conditions = {("P0", SLIT_PROFILE[slit_id]) for slit_id in SLIT_IDS}
    conditions.update((f"P{index}", SLIT_PROFILE[f"S{index}"]) for index in range(1, 7))
    return tuple(sorted(conditions))


def grid_readiness(ctx: AnalysisContext) -> dict[str, Any]:
    expected_offsets = {(float(x), float(y)) for x in GRID_OFFSETS_MM for y in GRID_OFFSETS_MM}
    condition_details: dict[tuple[str, str], dict[str, Any]] = {}
    for phantom_id, profile_id in expected_grid_conditions():
        rows = ctx.condition_rows("grid", phantom_id, profile_id)
        valid_rows = rows[rows.status == "valid"]
        found_offsets = {
            (float(row.head_offset_x_mm), float(row.head_offset_y_mm))
            for row in valid_rows.itertuples(index=False)
        }
        missing = sorted(expected_offsets.difference(found_offsets))
        extra = sorted(found_offsets.difference(expected_offsets))
        condition_details[(phantom_id, profile_id)] = {
            "rows": valid_rows,
            "missing_offsets": missing,
            "extra_offsets": extra,
            "complete": not missing and not extra and len(valid_rows) == len(expected_offsets),
        }
    complete_pairs: list[str] = []
    missing_pairs: list[str] = []
    for index in range(1, 7):
        slit_id = f"S{index}"
        profile_id = SLIT_PROFILE[slit_id]
        if (
            condition_details[("P0", profile_id)]["complete"]
            and condition_details[(f"P{index}", profile_id)]["complete"]
        ):
            complete_pairs.append(f"P{index}-{slit_id}")
        else:
            missing_pairs.append(f"P{index}-{slit_id}")
    missing_conditions = [
        {
            "phantom_id": phantom_id,
            "profile_id": profile_id,
            "missing_pose_count": len(details["missing_offsets"]),
        }
        for (phantom_id, profile_id), details in condition_details.items()
        if not details["complete"]
    ]
    return {
        "conditions": condition_details,
        "complete_pairs": complete_pairs,
        "missing_pairs": missing_pairs,
        "missing_conditions": missing_conditions,
        "missing_pose_count": sum(item["missing_pose_count"] for item in missing_conditions),
        "complete": not missing_conditions,
    }


def _save_png(fig: plt.Figure, path: Path) -> None:
    if path.suffix != ".png":
        raise ValueError(f"E2 figures must use PNG: {path}")
    fig.savefig(path, dpi=300, bbox_inches="tight")
    plt.close(fig)


def _grid_image(
    ctx: AnalysisContext,
    rows: pd.DataFrame,
    slit_id: str,
) -> np.ndarray:
    offsets = tuple(float(value) for value in GRID_OFFSETS_MM)
    x_index = {value: index for index, value in enumerate(offsets)}
    y_index = {value: index for index, value in enumerate(offsets)}
    image = np.full((len(offsets), len(offsets)), np.nan)
    for _, row in rows.iterrows():
        x = float(row.head_offset_x_mm)
        y = float(row.head_offset_y_mm)
        if x not in x_index or y not in y_index:
            raise ValueError(f"unexpected E2 grid offset {(x, y)}")
        selected = selected_events(ctx, row, slit_id, cache_center=False)
        image[y_index[y], x_index[x]] = count_classes(selected)["total"]
    if np.isnan(image).any():
        raise AssertionError(f"E2 complete grid pair contains missing cells: {slit_id}")
    return image


def _plot_grid_figure(
    ctx: AnalysisContext,
    readiness: dict[str, Any],
    figures: Path,
) -> dict[str, dict[str, int]]:
    fig, axes = plt.subplots(3, 4, figsize=(16, 11.2), constrained_layout=True)
    edges = grid_edges()
    grid_ranges: dict[str, dict[str, int]] = {}
    for index in range(1, 7):
        slit_id = f"S{index}"
        phantom_id = f"P{index}"
        profile_id = SLIT_PROFILE[slit_id]
        row_index = (index - 1) // 2
        column_index = 0 if index % 2 else 2
        pair_axes = (axes[row_index, column_index], axes[row_index, column_index + 1])
        pair_name = f"{phantom_id}-{slit_id}"
        if pair_name not in readiness["complete_pairs"]:
            for axis, title in zip(
                pair_axes, (f"P0–{slit_id} baseline", f"{phantom_id}–{slit_id} defect"), strict=True
            ):
                axis.set_facecolor("#F2F2F2")
                axis.text(
                    0.5,
                    0.5,
                    "Unavailable\nmissing grid data",
                    transform=axis.transAxes,
                    ha="center",
                    va="center",
                    color="#555555",
                )
                axis.set_title(title)
                axis.set_xticks([])
                axis.set_yticks([])
            continue

        baseline_rows = readiness["conditions"][("P0", profile_id)]["rows"]
        defect_rows = readiness["conditions"][(phantom_id, profile_id)]["rows"]
        baseline_image = _grid_image(ctx, baseline_rows, slit_id)
        defect_image = _grid_image(ctx, defect_rows, slit_id)
        minimum = float(min(baseline_image.min(), defect_image.min()))
        maximum = float(max(baseline_image.max(), defect_image.max()))
        if math.isclose(minimum, maximum):
            maximum = minimum + 1.0
        norm = Normalize(vmin=minimum, vmax=maximum)
        meshes = []
        for axis, data, title in zip(
            pair_axes,
            (baseline_image, defect_image),
            (f"P0–{slit_id} baseline", f"{phantom_id}–{slit_id} defect"),
            strict=True,
        ):
            mesh = axis.pcolormesh(
                edges, edges, data, cmap="viridis", norm=norm, shading="flat", rasterized=True
            )
            meshes.append(mesh)
            axis.set(
                aspect="equal",
                xlim=(edges[0], edges[-1]),
                ylim=(edges[0], edges[-1]),
                xticks=GRID_OFFSETS_MM,
                yticks=GRID_OFFSETS_MM,
                xlabel="Grid x (mm)",
                ylabel="Grid y (mm)",
                title=title,
            )
            axis.tick_params(labelsize=6)
        fig.colorbar(meshes[-1], ax=pair_axes, shrink=0.72, pad=0.015, label="Raw total count")
        grid_ranges[pair_name] = {
            "minimum": int(minimum),
            "maximum": int(maximum),
        }
    fig.suptitle("E2-F1  Matched 9×9 grid total-count images")
    _save_png(fig, figures / GRID_FIGURE_NAME)
    return grid_ranges


def _center_analysis(ctx: AnalysisContext) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    for index in range(1, 7):
        slit_id = f"S{index}"
        phantom_id = f"P{index}"
        profile_id = SLIT_PROFILE[slit_id]
        baseline = selected_events(
            ctx, ctx.center_row("P0", profile_id), slit_id, cache_center=True
        )
        defect = selected_events(
            ctx, ctx.center_row(phantom_id, profile_id), slit_id, cache_center=True
        )
        if (baseline.first_scatter_z < DEPTH_RANGE_MM[0]).any() or (
            baseline.first_scatter_z > DEPTH_RANGE_MM[1]
        ).any():
            raise ValueError(f"P0-{slit_id} contains depth outside 0-220 mm")
        if (defect.first_scatter_z < DEPTH_RANGE_MM[0]).any() or (
            defect.first_scatter_z > DEPTH_RANGE_MM[1]
        ).any():
            raise ValueError(f"{phantom_id}-{slit_id} contains depth outside 0-220 mm")
        baseline_counts = count_classes(baseline)
        defect_counts = count_classes(defect)
        row: dict[str, Any] = {"depth_mm": SLIT_DESIGN_DEPTH_MM[slit_id]}
        for category in CLASSES:
            row[f"N0_{category}"] = baseline_counts[category]
            row[f"ND_{category}"] = defect_counts[category]
            row[f"C_{category}"] = relative_change(
                defect_counts[category], baseline_counts[category], f"{phantom_id}-{slit_id}-{category}"
            )
        rows.append(row)
    return pd.DataFrame(rows, columns=T1_COLUMNS)


def _load_case_frames(ctx: AnalysisContext, case: E2Case) -> dict[str, pd.DataFrame]:
    profile_id = SLIT_PROFILE[case.slit]
    frames = {
        "baseline": selected_events(
            ctx,
            ctx.center_row(case.baseline_phantom, profile_id),
            case.slit,
            cache_center=True,
        ),
        "defect": selected_events(
            ctx,
            ctx.center_row(case.defect_phantom, profile_id),
            case.slit,
            cache_center=True,
        ),
    }
    for condition, frame in frames.items():
        if (frame.first_scatter_z < DEPTH_RANGE_MM[0]).any() or (
            frame.first_scatter_z > DEPTH_RANGE_MM[1]
        ).any():
            raise ValueError(
                f"{case.selection_slug} {condition} contains depth outside 0-220 mm"
            )
    return frames


def _case_depth_histograms(
    frames: dict[str, pd.DataFrame],
    case: E2Case,
    depth_bin_width_mm: float = DEFAULT_DEPTH_BIN_WIDTH_MM,
) -> tuple[np.ndarray, dict[str, np.ndarray]]:
    edges = depth_edges(depth_bin_width_mm)
    histograms: dict[str, np.ndarray] = {}
    for condition in ("baseline", "defect"):
        frame = frames[condition]
        values = frame.loc[
            class_mask(frame, case.scatter_class), "first_scatter_z"
        ].to_numpy(dtype=float)
        counts, _ = np.histogram(values, bins=edges)
        if counts.sum() != len(values):
            raise AssertionError(
                f"{case.selection_slug} {condition} depth histogram loses events"
            )
        histograms[condition] = counts
    return edges, histograms


def _plot_case_f2(
    case: E2Case,
    histograms: dict[str, np.ndarray],
    edges: np.ndarray,
    figures: Path,
    min_baseline_count: int | None,
) -> int:
    response = binwise_relative_response(
        histograms["defect"],
        histograms["baseline"],
        min_baseline_count=min_baseline_count,
    )
    fig, axis = plt.subplots(figsize=(10.5, 6.2), constrained_layout=True)
    axis.stairs(
        100.0 * response,
        edges,
        color=CLASS_COLORS[case.scatter_class],
        linewidth=1.5,
    )
    axis.axhline(0, color="#222222", linestyle="--", linewidth=1.0)
    axis.set(
        xlim=DEPTH_RANGE_MM,
        xlabel="First-scatter depth z (mm)",
        ylabel="Bin-wise relative response (%)",
        title=f"E2-F2  {case.comparison_label} — {case.scatter_class}",
    )
    name = f"E2-F2_{case.selection_slug}_binwise_relative_response.png"
    _save_png(fig, figures / name)
    return int(np.isnan(response).sum())


def _plot_case_f3(
    case: E2Case,
    histograms: dict[str, np.ndarray],
    edges: np.ndarray,
    figures: Path,
) -> None:
    fig, axis = plt.subplots(figsize=(10.5, 6.2), constrained_layout=True)
    axis.stairs(
        histograms["baseline"],
        edges,
        color=BASELINE_COLOR,
        label=f"{case.baseline_phantom}–{case.slit}",
        linewidth=1.5,
    )
    axis.stairs(
        histograms["defect"],
        edges,
        color=DEFECT_COLOR,
        label=f"{case.defect_phantom}–{case.slit}",
        linewidth=1.5,
    )
    axis.axvspan(*case_target_range(case), color="#BDBDBD", alpha=0.28, zorder=0)
    maximum = max(
        int(histograms["baseline"].max(initial=0)),
        int(histograms["defect"].max(initial=0)),
    )
    axis.set(
        xlim=DEPTH_RANGE_MM,
        ylim=(0, maximum * 1.08 if maximum else 1),
        xlabel="First-scatter depth z (mm)",
        ylabel="Raw detected counts",
        title=f"E2-F3  {case.comparison_label} — {case.scatter_class}",
    )
    axis.legend()
    name = f"E2-F3_{case.selection_slug}_raw_depth_counts.png"
    _save_png(fig, figures / name)


def _region_analysis(
    frames: dict[str, pd.DataFrame],
    case: E2Case,
    depth_bin_width_mm: float = DEFAULT_DEPTH_BIN_WIDTH_MM,
) -> tuple[pd.DataFrame, dict[str, dict[str, dict[str, np.ndarray]]]]:
    output_rows: list[dict[str, Any]] = []
    details: dict[str, dict[str, dict[str, np.ndarray]]] = {}
    target_range = case_target_range(case)
    for category in CLASSES:
        details[category] = {}
        baseline_all = frames["baseline"].loc[class_mask(frames["baseline"], category)]
        defect_all = frames["defect"].loc[class_mask(frames["defect"], category)]
        for region in REGIONS:
            baseline_depths = baseline_all.loc[
                region_mask(baseline_all.first_scatter_z, region, target_range),
                "first_scatter_z",
            ].to_numpy(dtype=float)
            defect_depths = defect_all.loc[
                region_mask(defect_all.first_scatter_z, region, target_range),
                "first_scatter_z",
            ].to_numpy(dtype=float)
            baseline_count = len(baseline_depths)
            defect_count = len(defect_depths)
            label = f"{case.comparison_slug}-{category}-{region}"
            edges, baseline_bins, defect_bins, contributions = within_region_tv_contributions(
                baseline_depths,
                defect_depths,
                region,
                label,
                target_range,
                depth_bin_width_mm,
            )
            details[category][region] = {
                "edges": edges,
                "baseline_counts": baseline_bins,
                "defect_counts": defect_bins,
                "tv_contributions": contributions,
            }
            output_rows.append(
                {
                    "scatter_class": category,
                    "region": region,
                    "N_r0": baseline_count,
                    "N_rD": defect_count,
                    "C_r": relative_change(defect_count, baseline_count, label),
                    "D_TV_r": float(contributions.sum()),
                }
            )
    return pd.DataFrame(output_rows, columns=T2_COLUMNS), details


def _annotate_source_regions(
    axes: np.ndarray,
    target_range: tuple[float, float],
) -> None:
    boundaries = (DEPTH_RANGE_MM[0], *target_range, DEPTH_RANGE_MM[1])
    for axis in axes:
        axis.axvspan(*target_range, color="#BDBDBD", alpha=0.18, zorder=0)
        for boundary in target_range:
            axis.axvline(boundary, color="#555555", linestyle="--", linewidth=0.9)
        for region, low, high in zip(REGIONS, boundaries[:-1], boundaries[1:], strict=True):
            axis.text(
                (low + high) / 2,
                0.975,
                region,
                transform=axis.get_xaxis_transform(),
                ha="center",
                va="top",
                fontsize=9,
                bbox={"facecolor": "white", "edgecolor": "none", "alpha": 0.72, "pad": 1},
            )


def _plot_case_f4(
    case: E2Case,
    details: dict[str, dict[str, dict[str, np.ndarray]]],
    figures: Path,
    min_baseline_count: int | None,
) -> dict[str, float | int]:
    fig, axes = plt.subplots(2, 1, figsize=(10.5, 9.2), sharex=True, constrained_layout=True)
    masked_bin_count = 0
    tv_sums: dict[str, float] = {}
    for region in REGIONS:
        values = details[case.scatter_class][region]
        response = binwise_relative_response(
            values["defect_counts"],
            values["baseline_counts"],
            min_baseline_count=min_baseline_count,
        )
        masked_bin_count += int(np.isnan(response).sum())
        axes[0].stairs(
            100.0 * response,
            values["edges"],
            color=CLASS_COLORS[case.scatter_class],
            linewidth=1.45,
        )
        axes[1].stairs(
            values["tv_contributions"],
            values["edges"],
            color=CLASS_COLORS[case.scatter_class],
            linewidth=1.45,
        )
        tv_sums[region] = float(values["tv_contributions"].sum())
    _annotate_source_regions(axes, case_target_range(case))
    axes[0].axhline(0, color="#222222", linestyle="--", linewidth=1.0)
    axes[0].set(
        ylabel="Bin-wise count response (%)",
        title="(a) Count-amplitude response by depth bin",
    )
    axes[1].set(
        xlim=DEPTH_RANGE_MM,
        xlabel="First-scatter depth z (mm)",
        ylabel=r"Per-bin $D_{TV,r}^{(s)}$ contribution",
        title="(b) Within-region shape-difference contribution",
    )
    fig.suptitle(f"E2-F4  {case.comparison_label} — {case.scatter_class}")
    name = f"E2-F4_{case.selection_slug}_source_region_decomposition.png"
    _save_png(fig, figures / name)
    return {"masked_bin_count": masked_bin_count, **{f"D_TV_{key}": value for key, value in tv_sums.items()}}


def run_e2(
    ctx: AnalysisContext,
    *,
    allow_partial_grid: bool,
    cases: tuple[E2Case, ...] | list[E2Case] | None = None,
    min_baseline_count: int | None = None,
    depth_bin_width_mm: float = DEFAULT_DEPTH_BIN_WIDTH_MM,
) -> dict[str, Any]:
    selected_cases = normalize_cases(cases)
    depth_bin_width_mm = validate_depth_bin_width(depth_bin_width_mm)
    if min_baseline_count is not None and min_baseline_count < 1:
        raise ValueError("min_baseline_count must be a positive integer")
    figures = ctx.output_root / "figures"
    tables = ctx.output_root / "tables"
    figures.mkdir(parents=True, exist_ok=True)
    tables.mkdir(parents=True, exist_ok=True)

    readiness = grid_readiness(ctx)
    if not readiness["complete"] and not allow_partial_grid:
        raise ValueError(
            "E2 grid inputs are incomplete; pass --allow-partial-grid for a clearly marked preview: "
            f"{readiness['missing_pose_count']} poses missing"
        )
    if allow_partial_grid and not readiness["complete_pairs"]:
        raise ValueError("partial E2-F1 requires at least one complete baseline/defect grid pair")

    grid_ranges = _plot_grid_figure(ctx, readiness, figures)
    center_table = _center_analysis(ctx)
    center_table.to_csv(tables / T1_TABLE_NAME, index=False)

    comparison_cache: dict[
        str,
        tuple[
            dict[str, pd.DataFrame],
            pd.DataFrame,
            dict[str, dict[str, dict[str, np.ndarray]]],
        ],
    ] = {}
    case_results: list[dict[str, Any]] = []
    for case in selected_cases:
        if case.comparison_slug not in comparison_cache:
            frames = _load_case_frames(ctx, case)
            region_table, region_details = _region_analysis(
                frames, case, depth_bin_width_mm
            )
            region_table.to_csv(tables / t2_table_name(case), index=False)
            comparison_cache[case.comparison_slug] = (frames, region_table, region_details)
        frames, region_table, region_details = comparison_cache[case.comparison_slug]
        depth_bin_edges, histograms = _case_depth_histograms(
            frames, case, depth_bin_width_mm
        )
        f2_masked = _plot_case_f2(
            case, histograms, depth_bin_edges, figures, min_baseline_count
        )
        _plot_case_f3(case, histograms, depth_bin_edges, figures)
        f4_metrics = _plot_case_f4(
            case, region_details, figures, min_baseline_count
        )
        selected_region_rows = (
            region_table[region_table.scatter_class == case.scatter_class]
            .set_index("region")
            .loc[list(REGIONS)]
        )
        tv_consistent = all(
            math.isclose(
                float(selected_region_rows.loc[region, "D_TV_r"]),
                float(f4_metrics[f"D_TV_{region}"]),
                rel_tol=0,
                abs_tol=1e-12,
            )
            for region in REGIONS
        )
        case_results.append(
            {
                **case.as_dict(),
                "comparison_slug": case.comparison_slug,
                "target_interval_mm": list(case_target_range(case)),
                "depth_histogram_totals": {
                    condition: int(counts.sum())
                    for condition, counts in histograms.items()
                },
                "f2_masked_bin_count": f2_masked,
                "f4_masked_bin_count": int(f4_metrics["masked_bin_count"]),
                "f4_dtv_sums": {
                    region: float(f4_metrics[f"D_TV_{region}"]) for region in REGIONS
                },
                "f4_dtv_matches_t2": tv_consistent,
            }
        )

    if not np.allclose(
        center_table.N0_total, center_table.N0_k1 + center_table.N0_ms
    ) or not np.allclose(center_table.ND_total, center_table.ND_k1 + center_table.ND_ms):
        raise AssertionError("E2 center table violates total = k1 + ms")
    return {
        "publication_status": "complete" if readiness["complete"] else "partial",
        "allow_partial_grid": allow_partial_grid,
        "complete_grid_pairs": readiness["complete_pairs"],
        "missing_grid_pairs": readiness["missing_pairs"],
        "missing_grid_conditions": readiness["missing_conditions"],
        "missing_grid_pose_count": readiness["missing_pose_count"],
        "grid_count_ranges": grid_ranges,
        "selected_cases": [case.as_dict() for case in selected_cases],
        "case_results": case_results,
        "min_baseline_count": min_baseline_count,
        "depth_bin_width_mm": depth_bin_width_mm,
        "expected_figure_names": list(figure_names(selected_cases)),
        "expected_table_names": list(table_names(selected_cases)),
    }


def write_report(root: Path, summary: dict[str, Any], warnings: list[str]) -> None:
    status = summary["publication_status"]
    lines = [
        "# Article V2 E2 Analysis Results",
        "",
        f"Publication status: **{status}**.",
        "",
        f"- Complete grid pairs: {', '.join(summary['complete_grid_pairs']) or 'none'}",
        f"- Missing grid pairs: {', '.join(summary['missing_grid_pairs']) or 'none'}",
        f"- Missing grid poses: {summary['missing_grid_pose_count']}",
        f"- Selected cases: {summary['selected_cases']}",
        f"- Depth bin width: {summary['depth_bin_width_mm']} mm",
        f"- Minimum baseline bin count: {summary['min_baseline_count']}",
        "- E2-F2/F3/F4 are depth-bin resolved and contain one selected scatter class per file.",
        "- Zero or explicitly under-threshold baseline bins are gaps, never fabricated zeros.",
        "- Figures are PNG only; E2-T1 is global and E2-T2 is emitted once per unique case.",
    ]
    if status == "partial":
        lines.extend(
            [
                "",
                "The current E2-F1 is a preview and is not a paper-complete six-pair result. ",
                "Unavailable panels represent missing simulations, not zero response.",
            ]
        )
    lines.extend(["", "## Warnings", ""])
    lines.extend([f"- {item}" for item in warnings] if warnings else ["- None."])
    lines.append("")
    (root / "report.md").write_text("\n".join(lines), encoding="utf-8")


def validate_generated_outputs(root: Path, summary: dict[str, Any]) -> dict[str, Any]:
    figures = {path.name for path in (root / "figures").iterdir() if path.is_file()}
    tables = {path.name for path in (root / "tables").iterdir() if path.is_file()}
    expected_figures = set(summary["expected_figure_names"])
    expected_tables = set(summary["expected_table_names"])
    center = pd.read_csv(root / "tables" / T1_TABLE_NAME)
    center_partition = bool(
        len(center) == 6
        and tuple(center.columns) == T1_COLUMNS
        and np.allclose(center.N0_total, center.N0_k1 + center.N0_ms)
        and np.allclose(center.ND_total, center.ND_k1 + center.ND_ms)
    )
    region_contract = True
    for table_name in sorted(expected_tables.difference({T1_TABLE_NAME})):
        regions = pd.read_csv(root / "tables" / table_name)
        region_contract = region_contract and bool(
            len(regions) == 9
            and tuple(regions.columns) == T2_COLUMNS
            and set(regions.scatter_class) == set(CLASSES)
            and set(regions.region) == set(REGIONS)
            and regions.D_TV_r.between(0, 1, inclusive="both").all()
            and np.isfinite(regions[["C_r", "D_TV_r"]].to_numpy(dtype=float)).all()
        )
    no_pdf = not any(path.suffix.lower() == ".pdf" for path in root.rglob("*"))
    functional_checks = {
        "E2_figure_contract": figures == expected_figures,
        "E2_table_contract": tables == expected_tables,
        "E2_png_only": no_pdf,
        "E2_center_accounting": center_partition,
        "E2_region_metrics": region_contract,
        "E2_f4_contributions_match_t2": all(
            item["f4_dtv_matches_t2"] for item in summary["case_results"]
        ),
        "E2_partial_has_complete_pair": bool(summary["complete_grid_pairs"]),
    }
    checks: dict[str, Any] = {
        name: {"actual": passed, "expected": True, "pass": passed}
        for name, passed in functional_checks.items()
    }
    grid_complete = summary["publication_status"] == "complete"
    checks["E2_grid_completeness"] = {
        "actual": {
            "complete_pairs": summary["complete_grid_pairs"],
            "missing_pairs": summary["missing_grid_pairs"],
            "missing_pose_count": summary["missing_grid_pose_count"],
        },
        "expected": {"complete_pairs": [f"P{i}-S{i}" for i in range(1, 7)], "missing_pose_count": 0},
        "pass": grid_complete,
        "waived_for_partial_preview": bool(summary["allow_partial_grid"] and not grid_complete),
    }
    functional_pass = all(functional_checks.values())
    if functional_pass and grid_complete:
        overall_status = "pass"
    elif functional_pass and summary["allow_partial_grid"]:
        overall_status = "partial"
    else:
        overall_status = "fail"
    result = {"overall_status": overall_status, "checks": checks}
    (root / "acceptance_summary.yaml").write_text(
        yaml.safe_dump(result, sort_keys=False, allow_unicode=True), encoding="utf-8"
    )
    if overall_status == "fail":
        raise AssertionError("generated E2 analysis failed acceptance checks")
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
        "analysis": "articlev2_e2_paper_figures_and_tables",
        "experiment": "E2",
        "publication_status": summary["publication_status"],
        "results_root": ".",
        "audit_summary": relative_to_campaign(audit_dir / "audit_summary.yaml", results_root),
        "parameters": {
            "input_layer": "events/valid",
            "event_selection": "matched profile and recorded slit_label inside pose-shifted closed ROI",
            "scatter_classes": {
                "total": "scatter_count_total >= 1",
                "k1": "scatter_count_total == 1",
                "ms": "scatter_count_total >= 2",
            },
            "grid_offsets_mm": list(GRID_OFFSETS_MM),
            "grid_interpolation": "none",
            "depth_range_mm": list(DEPTH_RANGE_MM),
            "depth_bin_width_mm": summary["depth_bin_width_mm"],
            "selected_cases": summary["selected_cases"],
            "min_baseline_count": summary["min_baseline_count"],
            "zero_baseline_bin_rule": "NaN and unplotted",
            "target_intervals_mm": {
                item["comparison_slug"]: list(item["target_interval_mm"])
                for item in summary["case_results"]
            },
            "target_interval_rule": "left-closed-right-open",
            "region_histogram_rule": "partition raw depths first; anchor selected-width bins at region boundaries; append an exact residual bin when needed",
            "relative_response_storage": "fraction in CSV; percent in figures",
            "figure_formats": ["png"],
            "figure_count": len(summary["expected_figure_names"]),
            "table_count": len(summary["expected_table_names"]),
            "allow_partial_grid": summary["allow_partial_grid"],
        },
        "grid_readiness": {
            "complete_pairs": summary["complete_grid_pairs"],
            "missing_pairs": summary["missing_grid_pairs"],
            "missing_conditions": summary["missing_grid_conditions"],
            "missing_pose_count": summary["missing_grid_pose_count"],
        },
        "data_quality": {
            "grid_count_ranges": summary["grid_count_ranges"],
            "case_results": summary["case_results"],
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
    allow_partial_grid: bool,
    cases: tuple[E2Case, ...] | list[E2Case] | None = None,
    min_baseline_count: int | None = None,
    depth_bin_width_mm: float = DEFAULT_DEPTH_BIN_WIDTH_MM,
) -> None:
    audit, inventory = validate_audit(audit_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    context = AnalysisContext(results_root, audit_dir, output_dir, inventory, audit)
    summary = run_e2(
        context,
        allow_partial_grid=allow_partial_grid,
        cases=cases,
        min_baseline_count=min_baseline_count,
        depth_bin_width_mm=depth_bin_width_mm,
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
        raise FileExistsError(f"stale E2 backup blocks overwrite: {backup}")
    output_dir.replace(backup)
    try:
        staging.replace(output_dir)
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
        "--case",
        dest="cases",
        action="append",
        type=parse_case,
        metavar="BASELINE:DEFECT:SLIT:SCATTER_CLASS",
        help="repeat to generate explicitly selected cases; default: P0:P4:S4:total",
    )
    parser.add_argument(
        "--min-baseline-count",
        type=int,
        help="mask response bins with fewer baseline counts; default masks only zero",
    )
    parser.add_argument("--allow-partial-grid", action="store_true")
    parser.add_argument("--overwrite", action="store_true")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    results_root = args.results_root.resolve()
    audit_dir = (args.audit_dir or results_root / "data_processing" / "audit").resolve()
    output_dir = (args.output_dir or results_root / "postprocessing" / "E2").resolve()
    protected = {
        results_root,
        (results_root / "events").resolve(),
        (results_root / "events" / "raw").resolve(),
        (results_root / "events" / "valid").resolve(),
    }
    if output_dir in protected:
        raise ValueError("E2 output directory must not replace event data or results root")
    if output_dir.exists() and not args.overwrite:
        raise FileExistsError(f"output directory exists; pass --overwrite: {output_dir}")
    output_dir.parent.mkdir(parents=True, exist_ok=True)
    staging = Path(tempfile.mkdtemp(prefix=f".{output_dir.name}.staging-", dir=output_dir.parent))
    try:
        run_analysis(
            results_root,
            audit_dir,
            staging,
            allow_partial_grid=args.allow_partial_grid,
            cases=args.cases,
            min_baseline_count=args.min_baseline_count,
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
        print(f"E2 analysis error: {error}", file=sys.stderr)
        raise SystemExit(1) from error
