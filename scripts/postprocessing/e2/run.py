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
    matched_slit,
    target_z_range,
)


CLASSES = ("total", "k1", "ms")
REGIONS = ("Front", "Target", "Behind")
SLIT_IDS = tuple(f"S{index}" for index in range(1, 7))
DEPTH_RANGE_MM = (0.0, 220.0)
DEFAULT_DEPTH_BIN_WIDTH_MM = 2.0
RESAMPLE_COUNT = 5000
DEFAULT_RESAMPLE_SEED = 20260814
BASELINE_COLOR = "#0072B2"
DEFECT_COLOR = "#D55E00"
CLASS_COLORS = {"total": "#333333", "k1": "#0072B2", "ms": "#D55E00"}
GRID_FIGURE_NAME = "E2-F1_matched_grid_total_counts.png"
T1_TABLE_NAME = "E2-T1_center_raw_count_decomposition.csv"
T3_TABLE_NAME = "E2-T3_center_source_region_fractions.csv"
ZERO_POSE_T1_TABLE_NAME = "E2-T1_zero_pose_raw_count_decomposition.csv"
ZERO_POSE_T3_TABLE_NAME = "E2-T3_zero_pose_source_region_fractions.csv"
SUMMARY_SOURCES = ("center", "grid-zero")
T1_COLUMNS = (
    "defect_phantom",
    "slit",
    "depth_mm",
    "scatter_class",
    "N0",
    "ND",
    "C",
    "C_ci_low",
    "C_ci_high",
    "C_n_effective",
)
T2_COLUMNS = (
    "baseline_phantom",
    "defect_phantom",
    "slit",
    "target_depth_mm",
    "scatter_class",
    "region",
    "N_r0",
    "N_rD",
    "C_r",
    "C_r_ci_low",
    "C_r_ci_high",
    "C_r_n_effective",
    "D_TV_r",
    "D_TV_r_ci_low",
    "D_TV_r_ci_high",
    "D_TV_r_n_effective",
)
T3_COLUMNS = (
    "defect_phantom",
    "slit",
    "target_depth_mm",
    "condition_role",
    "condition_phantom",
    "scatter_class",
    "region",
    "N_region",
    "N_total",
    "fraction",
    "fraction_ci_low",
    "fraction_ci_high",
    "fraction_n_effective",
)
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
            )
        )
    return tuple(names)


def t2_table_name(case: E2Case) -> str:
    return f"E2-T2_{case.comparison_slug}_source_region_quantitative.csv"


def summary_table_names(summary_source: str) -> tuple[str, str]:
    if summary_source == "center":
        return T1_TABLE_NAME, T3_TABLE_NAME
    if summary_source == "grid-zero":
        return ZERO_POSE_T1_TABLE_NAME, ZERO_POSE_T3_TABLE_NAME
    raise ValueError(f"summary_source must be one of {SUMMARY_SOURCES}: {summary_source!r}")


def table_names(
    cases: tuple[E2Case, ...], summary_source: str = "center"
) -> tuple[str, ...]:
    comparisons = dict.fromkeys(case.comparison_slug for case in cases)
    lookup = {case.comparison_slug: case for case in cases}
    t1_name, t3_name = summary_table_names(summary_source)
    return (
        t1_name,
        t3_name,
        *(t2_table_name(lookup[key]) for key in comparisons),
    )


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

    def summary_row(self, phantom: str, profile: str, summary_source: str) -> pd.Series:
        if summary_source == "center":
            return self.center_row(phantom, profile)
        if summary_source != "grid-zero":
            raise ValueError(
                f"summary_source must be one of {SUMMARY_SOURCES}: {summary_source!r}"
            )
        rows = self.condition_rows("grid", phantom, profile)
        rows = rows[
            np.isclose(rows.head_offset_x_mm.astype(float), 0)
            & np.isclose(rows.head_offset_y_mm.astype(float), 0)
        ]
        if len(rows) != 1:
            raise ValueError(
                f"expected one zero-pose grid run for {(phantom, profile)}, found {len(rows)}"
            )
        if rows.iloc[0]["status"] != "valid":
            raise ValueError(
                f"audit inventory marks zero-pose grid run invalid: {(phantom, profile)}"
            )
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


@dataclass(frozen=True)
class PairResample:
    case: E2Case
    atom_edges: np.ndarray
    observed: np.ndarray
    sampled: np.ndarray
    resample_count: int


def finite_interval(
    values: np.ndarray, label: str, *, allow_empty: bool = False
) -> tuple[float, float, int]:
    finite = np.asarray(values, dtype=float)
    finite = finite[np.isfinite(finite)]
    if not finite.size:
        if allow_empty:
            return math.nan, math.nan, 0
        raise ValueError(f"no valid Poisson resamples for {label}")
    low, high = np.percentile(finite, (2.5, 97.5))
    return float(low), float(high), int(finite.size)


def sampled_ratio(
    numerator: np.ndarray,
    denominator: np.ndarray,
    *,
    relative_change_value: bool,
) -> np.ndarray:
    top = np.asarray(numerator, dtype=float)
    bottom = np.asarray(denominator, dtype=float)
    if top.shape != bottom.shape:
        raise ValueError("sampled numerator and denominator shapes must match")
    result = np.full(top.shape, np.nan, dtype=float)
    valid = np.isfinite(top) & np.isfinite(bottom) & (bottom > 0)
    if relative_change_value:
        result[valid] = (top[valid] - bottom[valid]) / bottom[valid]
    else:
        result[valid] = top[valid] / bottom[valid]
    return result


def _class_index(scatter_class: str) -> int | None:
    if scatter_class == "k1":
        return 0
    if scatter_class == "ms":
        return 1
    if scatter_class == "total":
        return None
    raise ValueError(f"unknown scatter class: {scatter_class}")


def pair_class_counts(pair: PairResample, scatter_class: str) -> tuple[np.ndarray, np.ndarray]:
    index = _class_index(scatter_class)
    if index is None:
        return pair.observed.sum(axis=1), pair.sampled.sum(axis=2)
    return pair.observed[:, index, :], pair.sampled[:, :, index, :]


def _atomic_edges(
    target_range: tuple[float, float],
    depth_bin_width_mm: float,
) -> np.ndarray:
    parts = [depth_edges(depth_bin_width_mm)]
    parts.extend(
        region_edges(region, target_range, depth_bin_width_mm) for region in REGIONS
    )
    return np.unique(np.concatenate(parts))


def build_pair_resample(
    frames: dict[str, pd.DataFrame],
    case: E2Case,
    rng: np.random.Generator,
    *,
    resample_count: int = RESAMPLE_COUNT,
    depth_bin_width_mm: float = DEFAULT_DEPTH_BIN_WIDTH_MM,
) -> PairResample:
    if resample_count <= 0:
        raise ValueError("resample_count must be positive")
    target_range = case_target_range(case)
    atom_edges = _atomic_edges(target_range, depth_bin_width_mm)
    observed = np.zeros((2, 2, len(atom_edges) - 1), dtype=np.int64)
    for condition_index, condition in enumerate(("baseline", "defect")):
        frame = frames[condition]
        for class_index, scatter_class in enumerate(("k1", "ms")):
            depths = frame.loc[
                class_mask(frame, scatter_class), "first_scatter_z"
            ].to_numpy(dtype=float)
            counts, _ = np.histogram(depths, bins=atom_edges)
            if int(counts.sum()) != len(depths):
                raise AssertionError(f"{case.comparison_slug} atomic histogram loses events")
            observed[condition_index, class_index] = counts
    sampled = rng.poisson(observed, size=(resample_count, *observed.shape))
    if not np.array_equal(sampled.sum(axis=2), sampled[:, :, 0, :] + sampled[:, :, 1, :]):
        raise AssertionError("E2 sampled total does not equal k1 + ms")
    return PairResample(case, atom_edges, observed, sampled, resample_count)


def _region_atom_mask(pair: PairResample, region: str) -> np.ndarray:
    centers = 0.5 * (pair.atom_edges[:-1] + pair.atom_edges[1:])
    return region_mask(centers, region, case_target_range(pair.case))


def _aggregate_region_bins(
    counts: np.ndarray,
    pair: PairResample,
    region: str,
    depth_bin_width_mm: float,
) -> np.ndarray:
    region_values = region_edges(region, case_target_range(pair.case), depth_bin_width_mm)
    atom_mask = _region_atom_mask(pair, region)
    atom_centers = 0.5 * (pair.atom_edges[:-1] + pair.atom_edges[1:])
    selected_centers = atom_centers[atom_mask]
    indices = np.searchsorted(region_values, selected_centers, side="right") - 1
    indices = np.minimum(indices, len(region_values) - 2)
    selected = np.asarray(counts)[..., atom_mask]
    output = np.zeros((*selected.shape[:-1], len(region_values) - 1), dtype=selected.dtype)
    for index in range(len(region_values) - 1):
        output[..., index] = selected[..., indices == index].sum(axis=-1)
    return output


def sampled_dtv(baseline_bins: np.ndarray, defect_bins: np.ndarray) -> np.ndarray:
    baseline = np.asarray(baseline_bins, dtype=float)
    defect = np.asarray(defect_bins, dtype=float)
    if baseline.shape != defect.shape or baseline.ndim != 2:
        raise ValueError("sampled DTV inputs must have matching (sample, bin) shapes")
    baseline_total = baseline.sum(axis=1)
    defect_total = defect.sum(axis=1)
    result = np.full(len(baseline), np.nan, dtype=float)
    valid = (baseline_total > 0) & (defect_total > 0)
    if np.any(valid):
        p0 = baseline[valid] / baseline_total[valid, None]
        pd = defect[valid] / defect_total[valid, None]
        result[valid] = 0.5 * np.abs(pd - p0).sum(axis=1)
    return result


def center_response_rows(pair: PairResample) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for scatter_class in CLASSES:
        observed, sampled = pair_class_counts(pair, scatter_class)
        n0, nd = (int(observed[index].sum()) for index in (0, 1))
        point = relative_change(nd, n0, f"{pair.case.comparison_slug}-{scatter_class}")
        samples = sampled_ratio(
            sampled[:, 1, :].sum(axis=1),
            sampled[:, 0, :].sum(axis=1),
            relative_change_value=True,
        )
        low, high, n_effective = finite_interval(
            samples, f"{pair.case.comparison_slug}-{scatter_class}-C"
        )
        rows.append(
            {
                "defect_phantom": pair.case.defect_phantom,
                "slit": pair.case.slit,
                "depth_mm": float(DEFECT_CENTER_Z_MM[pair.case.defect_phantom]),
                "scatter_class": scatter_class,
                "N0": n0,
                "ND": nd,
                "C": point,
                "C_ci_low": low,
                "C_ci_high": high,
                "C_n_effective": n_effective,
            }
        )
    return rows


def source_fraction_rows(pair: PairResample) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for scatter_class in CLASSES:
        observed, sampled = pair_class_counts(pair, scatter_class)
        for condition_index, (role, phantom) in enumerate(
            (("baseline", pair.case.baseline_phantom), ("defect", pair.case.defect_phantom))
        ):
            total = int(observed[condition_index].sum())
            if total <= 0:
                raise ValueError(f"zero total count for {pair.case.comparison_slug}-{role}-{scatter_class}")
            sampled_total = sampled[:, condition_index, :].sum(axis=1)
            fractions: list[float] = []
            for region in REGIONS:
                atom_mask = _region_atom_mask(pair, region)
                region_count = int(observed[condition_index, atom_mask].sum())
                fraction = region_count / total
                fractions.append(fraction)
                samples = sampled_ratio(
                    sampled[:, condition_index, atom_mask].sum(axis=1),
                    sampled_total,
                    relative_change_value=False,
                )
                low, high, n_effective = finite_interval(
                    samples,
                    f"{pair.case.comparison_slug}-{role}-{scatter_class}-{region}-fraction",
                )
                rows.append(
                    {
                        "defect_phantom": pair.case.defect_phantom,
                        "slit": pair.case.slit,
                        "target_depth_mm": float(DEFECT_CENTER_Z_MM[pair.case.defect_phantom]),
                        "condition_role": role,
                        "condition_phantom": phantom,
                        "scatter_class": scatter_class,
                        "region": region,
                        "N_region": region_count,
                        "N_total": total,
                        "fraction": fraction,
                        "fraction_ci_low": low,
                        "fraction_ci_high": high,
                        "fraction_n_effective": n_effective,
                    }
                )
            if not math.isclose(sum(fractions), 1.0, rel_tol=0, abs_tol=1e-12):
                raise AssertionError("E2 source-region fractions do not close to one")
    return rows


def source_region_rows(
    pair: PairResample,
    depth_bin_width_mm: float,
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for scatter_class in CLASSES:
        observed, sampled = pair_class_counts(pair, scatter_class)
        for region in REGIONS:
            atom_mask = _region_atom_mask(pair, region)
            n0 = int(observed[0, atom_mask].sum())
            nd = int(observed[1, atom_mask].sum())
            c_point = relative_change(
                nd, n0, f"{pair.case.comparison_slug}-{scatter_class}-{region}"
            )
            c_samples = sampled_ratio(
                sampled[:, 1, atom_mask].sum(axis=1),
                sampled[:, 0, atom_mask].sum(axis=1),
                relative_change_value=True,
            )
            c_low, c_high, c_n = finite_interval(
                c_samples, f"{pair.case.comparison_slug}-{scatter_class}-{region}-C"
            )
            point_bins_0 = _aggregate_region_bins(
                observed[0], pair, region, depth_bin_width_mm
            )
            point_bins_d = _aggregate_region_bins(
                observed[1], pair, region, depth_bin_width_mm
            )
            if point_bins_0.sum() <= 0 or point_bins_d.sum() <= 0:
                dtv_point = math.nan
            else:
                dtv_point = float(
                    0.5
                    * np.abs(
                        point_bins_d / point_bins_d.sum() - point_bins_0 / point_bins_0.sum()
                    ).sum()
                )
            sampled_bins_0 = _aggregate_region_bins(
                sampled[:, 0], pair, region, depth_bin_width_mm
            )
            sampled_bins_d = _aggregate_region_bins(
                sampled[:, 1], pair, region, depth_bin_width_mm
            )
            dtv_samples = sampled_dtv(sampled_bins_0, sampled_bins_d)
            dtv_low, dtv_high, dtv_n = finite_interval(
                dtv_samples,
                f"{pair.case.comparison_slug}-{scatter_class}-{region}-DTV",
                allow_empty=True,
            )
            rows.append(
                {
                    "baseline_phantom": pair.case.baseline_phantom,
                    "defect_phantom": pair.case.defect_phantom,
                    "slit": pair.case.slit,
                    "target_depth_mm": float(DEFECT_CENTER_Z_MM[pair.case.defect_phantom]),
                    "scatter_class": scatter_class,
                    "region": region,
                    "N_r0": n0,
                    "N_rD": nd,
                    "C_r": c_point,
                    "C_r_ci_low": c_low,
                    "C_r_ci_high": c_high,
                    "C_r_n_effective": c_n,
                    "D_TV_r": dtv_point,
                    "D_TV_r_ci_low": dtv_low,
                    "D_TV_r_ci_high": dtv_high,
                    "D_TV_r_n_effective": dtv_n,
                }
            )
    return rows


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


def _load_case_frames(
    ctx: AnalysisContext, case: E2Case, summary_source: str = "center"
) -> dict[str, pd.DataFrame]:
    profile_id = SLIT_PROFILE[case.slit]
    frames = {
        "baseline": selected_events(
            ctx,
            ctx.summary_row(case.baseline_phantom, profile_id, summary_source),
            case.slit,
            cache_center=True,
        ),
        "defect": selected_events(
            ctx,
            ctx.summary_row(case.defect_phantom, profile_id, summary_source),
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


def run_e2(
    ctx: AnalysisContext,
    *,
    allow_partial_grid: bool,
    cases: tuple[E2Case, ...] | list[E2Case] | None = None,
    min_baseline_count: int | None = None,
    depth_bin_width_mm: float = DEFAULT_DEPTH_BIN_WIDTH_MM,
    resample_seed: int = DEFAULT_RESAMPLE_SEED,
    resample_count: int = RESAMPLE_COUNT,
    summary_source: str = "center",
) -> dict[str, Any]:
    selected_cases = normalize_cases(cases)
    t1_name, t3_name = summary_table_names(summary_source)
    depth_bin_width_mm = validate_depth_bin_width(depth_bin_width_mm)
    if min_baseline_count is not None and min_baseline_count < 1:
        raise ValueError("min_baseline_count must be a positive integer")
    figures = ctx.output_root / "figures"
    tables = ctx.output_root / "tables"
    figures.mkdir(parents=True, exist_ok=True)
    tables.mkdir(parents=True, exist_ok=True)
    rng = np.random.default_rng(resample_seed)

    readiness = grid_readiness(ctx)
    if not readiness["complete"] and not allow_partial_grid:
        raise ValueError(
            "E2 grid inputs are incomplete; pass --allow-partial-grid for a clearly marked preview: "
            f"{readiness['missing_pose_count']} poses missing"
        )
    if allow_partial_grid and not readiness["complete_pairs"]:
        raise ValueError("partial E2-F1 requires at least one complete baseline/defect grid pair")

    grid_ranges = _plot_grid_figure(ctx, readiness, figures)
    selected_comparisons = {
        case.comparison_slug: case for case in selected_cases
    }
    pair_cache: dict[str, PairResample] = {}
    frame_cache: dict[str, dict[str, pd.DataFrame]] = {}
    center_rows: list[dict[str, Any]] = []
    fraction_rows: list[dict[str, Any]] = []
    for index in range(1, 7):
        global_case = E2Case("P0", f"P{index}", f"S{index}", "total")
        frames = _load_case_frames(ctx, global_case, summary_source)
        pair = build_pair_resample(
            frames,
            global_case,
            rng,
            resample_count=resample_count,
            depth_bin_width_mm=depth_bin_width_mm,
        )
        center_rows.extend(center_response_rows(pair))
        fraction_rows.extend(source_fraction_rows(pair))
        if global_case.comparison_slug in selected_comparisons:
            pair_cache[global_case.comparison_slug] = pair
            frame_cache[global_case.comparison_slug] = frames

    center_table = pd.DataFrame(center_rows, columns=T1_COLUMNS)
    fraction_table = pd.DataFrame(fraction_rows, columns=T3_COLUMNS)
    center_table.to_csv(tables / t1_name, index=False)
    fraction_table.to_csv(tables / t3_name, index=False)

    region_tables: dict[str, pd.DataFrame] = {}
    for comparison_slug, case in selected_comparisons.items():
        if comparison_slug not in pair_cache:
            frames = _load_case_frames(ctx, case, summary_source)
            frame_cache[comparison_slug] = frames
            pair_cache[comparison_slug] = build_pair_resample(
                frames,
                case,
                rng,
                resample_count=resample_count,
                depth_bin_width_mm=depth_bin_width_mm,
            )
        region_table = pd.DataFrame(
            source_region_rows(pair_cache[comparison_slug], depth_bin_width_mm),
            columns=T2_COLUMNS,
        )
        region_table.to_csv(tables / t2_table_name(case), index=False)
        region_tables[comparison_slug] = region_table

    case_results: list[dict[str, Any]] = []
    for case in selected_cases:
        frames = frame_cache[case.comparison_slug]
        region_table = region_tables[case.comparison_slug]
        depth_bin_edges, histograms = _case_depth_histograms(
            frames, case, depth_bin_width_mm
        )
        f2_masked = _plot_case_f2(
            case, histograms, depth_bin_edges, figures, min_baseline_count
        )
        _plot_case_f3(case, histograms, depth_bin_edges, figures)
        selected_region_rows = (
            region_table[region_table.scatter_class == case.scatter_class]
            .set_index("region")
            .loc[list(REGIONS)]
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
                "source_region_metrics": {
                    region: {
                        "C_r": float(selected_region_rows.loc[region, "C_r"]),
                        "D_TV_r": (
                            None
                            if pd.isna(selected_region_rows.loc[region, "D_TV_r"])
                            else float(selected_region_rows.loc[region, "D_TV_r"])
                        ),
                    }
                    for region in REGIONS
                },
            }
        )

    for _, group in center_table.groupby(["defect_phantom", "slit"], sort=False):
        indexed = group.set_index("scatter_class")
        if int(indexed.loc["total", "N0"]) != int(indexed.loc["k1", "N0"]) + int(
            indexed.loc["ms", "N0"]
        ) or int(indexed.loc["total", "ND"]) != int(indexed.loc["k1", "ND"]) + int(
            indexed.loc["ms", "ND"]
        ):
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
        "resample_seed": int(resample_seed),
        "resample_count": int(resample_count),
        "summary_source": summary_source,
        "summary_table_names": [t1_name, t3_name],
        "expected_figure_names": list(figure_names(selected_cases)),
        "expected_table_names": list(table_names(selected_cases, summary_source)),
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
        f"- Single-pose summary source: {summary['summary_source']}",
        f"- Depth bin width: {summary['depth_bin_width_mm']} mm",
        f"- Minimum baseline bin count: {summary['min_baseline_count']}",
        f"- Poisson resampling: {summary['resample_count']} draws, seed {summary['resample_seed']}.",
        "- E2-F2/F3 are depth-bin resolved and contain one selected scatter class per file.",
        "- Zero or explicitly under-threshold baseline bins are gaps, never fabricated zeros.",
        "- Figures are PNG only; E2-T1/T3 are global and E2-T2 is emitted once per unique case.",
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
    t1_name, t3_name = summary["summary_table_names"]
    center = pd.read_csv(root / "tables" / t1_name)
    center_partition = len(center) == 18 and tuple(center.columns) == T1_COLUMNS
    if center_partition:
        center_partition = bool(
            set(center.scatter_class) == set(CLASSES)
            and center.groupby(["defect_phantom", "slit"]).ngroups == 6
            and np.isfinite(
                center[["C", "C_ci_low", "C_ci_high"]].to_numpy(dtype=float)
            ).all()
            and center.C_n_effective.between(1, summary["resample_count"]).all()
        )
        for _, group in center.groupby(["defect_phantom", "slit"], sort=False):
            indexed = group.set_index("scatter_class")
            center_partition = center_partition and bool(
                indexed.loc["total", "N0"]
                == indexed.loc["k1", "N0"] + indexed.loc["ms", "N0"]
                and indexed.loc["total", "ND"]
                == indexed.loc["k1", "ND"] + indexed.loc["ms", "ND"]
            )

    fractions = pd.read_csv(root / "tables" / t3_name)
    fraction_contract = len(fractions) == 108 and tuple(fractions.columns) == T3_COLUMNS
    if fraction_contract:
        grouped_fractions = fractions.groupby(
            ["defect_phantom", "slit", "condition_role", "scatter_class"], sort=False
        )
        fraction_contract = bool(
            grouped_fractions.ngroups == 36
            and set(fractions.condition_role) == {"baseline", "defect"}
            and set(fractions.region) == set(REGIONS)
            and np.allclose(grouped_fractions.fraction.sum().to_numpy(dtype=float), 1.0)
            and np.allclose(
                grouped_fractions.N_region.sum().to_numpy(dtype=float),
                grouped_fractions.N_total.first().to_numpy(dtype=float),
            )
            and fractions.fraction.between(0, 1, inclusive="both").all()
            and fractions.fraction_n_effective.between(1, summary["resample_count"]).all()
        )
    region_contract = True
    for table_name in sorted(expected_tables.difference({t1_name, t3_name})):
        regions = pd.read_csv(root / "tables" / table_name)
        dtv_defined = (
            regions.D_TV_r.notna()
            & regions.D_TV_r_ci_low.notna()
            & regions.D_TV_r_ci_high.notna()
            & regions.D_TV_r_n_effective.between(1, summary["resample_count"])
        )
        dtv_undefined = (
            regions.D_TV_r.isna()
            & regions.D_TV_r_ci_low.isna()
            & regions.D_TV_r_ci_high.isna()
            & regions.D_TV_r_n_effective.eq(0)
        )
        region_contract = region_contract and bool(
            len(regions) == 9
            and tuple(regions.columns) == T2_COLUMNS
            and set(regions.scatter_class) == set(CLASSES)
            and set(regions.region) == set(REGIONS)
            and (dtv_defined | dtv_undefined).all()
            and regions.loc[dtv_defined, "D_TV_r"].between(0, 1, inclusive="both").all()
            and np.isfinite(
                regions[
                    [
                        "C_r",
                        "C_r_ci_low",
                        "C_r_ci_high",
                    ]
                ].to_numpy(dtype=float)
            ).all()
            and regions.C_r_n_effective.between(1, summary["resample_count"]).all()
        )
    no_pdf = not any(path.suffix.lower() == ".pdf" for path in root.rglob("*"))
    functional_checks = {
        "E2_figure_contract": figures == expected_figures,
        "E2_table_contract": tables == expected_tables,
        "E2_png_only": no_pdf,
        "E2_center_accounting": center_partition,
        "E2_source_fraction_contract": fraction_contract,
        "E2_region_metrics": region_contract,
        "E2_no_source_region_figures": not any("E2-F4" in name for name in figures),
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
            "summary_source": summary["summary_source"],
            "min_baseline_count": summary["min_baseline_count"],
            "poisson_resampling": {
                "draw_count": summary["resample_count"],
                "seed": summary["resample_seed"],
                "interval_percentiles": [2.5, 97.5],
                "invalid_denominator_rule": "exclude for the affected metric and report n_effective",
                "undefined_point_DTV_rule": "store NA and n_effective=0 when either observed regional histogram is empty",
                "total_reconstruction": "same-draw k1 + ms",
            },
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
    resample_seed: int = DEFAULT_RESAMPLE_SEED,
    summary_source: str = "center",
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
        resample_seed=resample_seed,
        resample_count=RESAMPLE_COUNT,
        summary_source=summary_source,
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
    parser.add_argument(
        "--summary-source",
        choices=SUMMARY_SOURCES,
        default="center",
        help="single-pose source for E2-T1/T3 and selected depth/source-region cases",
    )
    parser.add_argument("--resample-seed", type=int, default=DEFAULT_RESAMPLE_SEED)
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
            resample_seed=args.resample_seed,
            summary_source=args.summary_source,
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
