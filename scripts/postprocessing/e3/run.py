#!/usr/bin/env python3
"""Generate the canonical Article V2 E3 paper figures and tables."""

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
import yaml
from matplotlib.colors import LinearSegmentedColormap, TwoSlopeNorm
from matplotlib.patches import Rectangle
from matplotlib.ticker import PercentFormatter, ScalarFormatter

from scripts.data_processing.common import (
    SLIT_PROFILE,
    DetectorAcceptanceRegion,
    RunMetadata,
    acceptance_regions_for_profile,
    load_run_metadata,
)
from scripts.data_processing.experiment_contract import (
    DEFECT_CENTER_Z_MM,
    EXPECTED_ENERGY_KEV,
    GRID_OFFSETS_MM,
    matched_slit,
    target_z_range,
)


RESAMPLE_COUNT = 5000
DEFAULT_RESAMPLE_SEED = 20260814
SLAB_THICKNESS_MM = 55.0
SLAB_REFERENCE_TYPE = "uniform_pmma_front_slab"
SLAB_MODEL_ID = "P4_front_slab_55mm"
SLAB_CAMPAIGN_ID = "articlev3_p4_front_slab_55mm_100m"
SLAB_N_PRIMARY = 100_000_000
SLAB_SEED_START = 11_000
SLAB_SEED_END = 11_080
SLAB_MANIFEST_NAME = "reference_manifest.yaml"
SUPPLEMENTARY_DIR_NAME = "supplementary"
BASE_CATEGORIES = ("k1_F", "k1_T", "k1_B", "ms_F", "ms_T", "ms_B")
METHODS = ("M0", "M1", "M2", "M3", "M4", "M5")
METHOD_LABELS = {
    "M0": "total",
    "M1": "k1-only",
    "M2": r"$k1_T$",
    "M3": r"$ms_T$",
    "M4": r"$k1_T+ms_T$",
    "M5": r"$T+B$",
}
METHOD_COLORS = {
    "M0": "#4D4D4D",
    "M1": "#0072B2",
    "M2": "#56B4E9",
    "M3": "#D55E00",
    "M4": "#009E73",
    "M5": "#CC79A7",
}
METHOD_MARKERS = {"M0": "o", "M1": "o", "M2": "^", "M3": "^", "M4": "o", "M5": "o"}
FIGURE_NAMES = (
    "E3_F1_P4_S4_M0_M5.png",
    "E3_F2_M1_M4_depth.png",
    "E3_F3_M0_M5_depth.png",
    "E3_F4_all_methods_CNR_depth.png",
    "E3_F5_all_methods_retention_depth.png",
    "E3_F6_front_removal_reference.png",
)
TABLE_NAMES = (
    "E3_T1_P4_S4_metrics.csv",
    "E3_T2_depth_method_metrics.csv",
    "E3_T3_depth_comparisons.csv",
    "E3_T4_front_removal_reference_metrics.csv",
)
OUTPUT_NAMES = (*FIGURE_NAMES, *TABLE_NAMES)
T1_COLUMNS = (
    "method",
    "total_count_N",
    "retention_eta",
    "retention_ci_low",
    "retention_ci_high",
    "retention_n_effective",
    "roi_mean",
    "background_mean",
    "background_std",
    "cnr",
    "cnr_ci_low",
    "cnr_ci_high",
    "cnr_n_effective",
)
T2_COLUMNS = (
    "phantom",
    "slit",
    "target_depth_mm",
    "method",
    "total_count_N",
    "retention_eta",
    "retention_ci_low",
    "retention_ci_high",
    "retention_n_effective",
    "roi_mean",
    "background_mean",
    "background_std",
    "cnr",
    "cnr_ci_low",
    "cnr_ci_high",
    "cnr_n_effective",
)
T3_COLUMNS = (
    "phantom",
    "slit",
    "target_depth_mm",
    "comparison",
    "from_method",
    "to_method",
    "from_cnr",
    "to_cnr",
    "g_cnr",
    "g_cnr_ci_low",
    "g_cnr_ci_high",
    "g_cnr_n_effective",
    "from_count_N",
    "to_count_N",
    "g_count",
    "g_count_ci_low",
    "g_count_ci_high",
    "g_count_n_effective",
)
T4_COLUMNS = (
    "image",
    "count_metric",
    "count_metric_kind",
    "roi_mean",
    "background_mean",
    "background_std",
    "cnr",
    "cnr_ci_low",
    "cnr_ci_high",
    "cnr_n_effective",
)
COMPARISONS = (
    ("M2_to_M4", "M2", "M4"),
    ("M1_to_M4", "M1", "M4"),
    ("M0_to_M5", "M0", "M5"),
)
EVENT_COLUMNS = (
    "det_x",
    "det_y",
    "scatter_count_total",
    "first_scatter_z",
    "slit_group",
    "slit_label",
)
GRID_EDGE_MM = np.r_[
    np.asarray(GRID_OFFSETS_MM, dtype=float) - 1.25,
    float(GRID_OFFSETS_MM[-1]) + 1.25,
]


class E3PreflightError(ValueError):
    """Raised when strict E3 inputs are incomplete or inconsistent."""

    def __init__(self, issues: Iterable[str], report: dict[str, Any]):
        self.issues = tuple(str(item) for item in issues)
        self.report = report
        super().__init__("E3 preflight failed: " + "; ".join(self.issues))


@dataclass(frozen=True)
class GridCondition:
    phantom: str
    slit: str
    base_counts: np.ndarray
    n_primary: int
    energy_keV: float


@dataclass(frozen=True)
class SlabCondition:
    image: np.ndarray
    n_primary: int
    energy_keV: float
    geometry_id: str


@dataclass(frozen=True)
class BootstrapResult:
    method_images: np.ndarray
    cnr: np.ndarray
    retention: np.ndarray
    total_counts: np.ndarray
    g_ms_cnr: np.ndarray
    g_ms_count: np.ndarray
    g_sr_cnr: np.ndarray
    g_sr_count: np.ndarray
    g_front_cnr: np.ndarray
    g_front_count: np.ndarray


def expected_offsets() -> set[tuple[float, float]]:
    return {(float(x), float(y)) for x in GRID_OFFSETS_MM for y in GRID_OFFSETS_MM}


def grid_position_indices(x: float, y: float) -> tuple[int, int]:
    """Return image indices in row=y, column=x order for a frozen E3 pose."""
    x_index = {float(value): index for index, value in enumerate(GRID_OFFSETS_MM)}
    y_index = {float(value): index for index, value in enumerate(GRID_OFFSETS_MM)}
    point = (float(x), float(y))
    if point[0] not in x_index or point[1] not in y_index:
        raise ValueError(f"unexpected E3 grid coordinate: {point}")
    return y_index[point[1]], x_index[point[0]]


def roi_masks() -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    x_grid, y_grid = np.meshgrid(GRID_OFFSETS_MM, GRID_OFFSETS_MM)
    radius = np.maximum(np.abs(x_grid), np.abs(y_grid))
    defect = (np.abs(x_grid) <= 5.0) & (np.abs(y_grid) <= 5.0)
    guard = np.isclose(radius, 7.5)
    background = np.isclose(radius, 10.0)
    if (int(defect.sum()), int(guard.sum()), int(background.sum())) != (25, 24, 32):
        raise AssertionError("E3 ROI partition must contain 25/24/32 grid points")
    if np.any(defect & guard) or np.any(defect & background) or np.any(guard & background):
        raise AssertionError("E3 ROI masks must be disjoint")
    return defect, guard, background


DEFECT_MASK, GUARD_MASK, BACKGROUND_MASK = roi_masks()


def source_region_masks(
    depths: pd.Series | np.ndarray, target_interval: tuple[float, float]
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    values = np.asarray(depths, dtype=float)
    low, high = target_interval
    return values < low, (values >= low) & (values < high), values >= high


def scatter_counts(frame: pd.DataFrame) -> np.ndarray:
    values = frame.scatter_count_total.to_numpy(dtype=float)
    if (
        not np.isfinite(values).all()
        or (values < 0).any()
        or not np.equal(values, np.floor(values)).all()
    ):
        raise ValueError("scatter_count_total must contain finite non-negative integers")
    return values.astype(np.int64)


def category_counts(frame: pd.DataFrame, target_interval: tuple[float, float]) -> np.ndarray:
    scatter = scatter_counts(frame)
    depth = frame.first_scatter_z.to_numpy(dtype=float)
    total = scatter >= 1
    if not np.isfinite(depth[total]).all():
        raise ValueError("first_scatter_z must be finite for every detected scattered track")
    front, target, behind = source_region_masks(depth, target_interval)
    masks = (
        (scatter == 1) & front,
        (scatter == 1) & target,
        (scatter == 1) & behind,
        (scatter >= 2) & front,
        (scatter >= 2) & target,
        (scatter >= 2) & behind,
    )
    counts = np.asarray([int(mask.sum()) for mask in masks], dtype=np.int64)
    if int(counts.sum()) != int(total.sum()):
        raise AssertionError("F+T+B must partition all k1/ms events")
    return counts


def methods_from_base(base_counts: np.ndarray) -> np.ndarray:
    values = np.asarray(base_counts)
    if values.shape[-3] != len(BASE_CATEGORIES) or values.shape[-2:] != (9, 9):
        raise ValueError("base counts must end with shape (6, 9, 9)")
    k1_f, k1_t, k1_b, ms_f, ms_t, ms_b = np.moveaxis(values, -3, 0)
    m0 = k1_f + k1_t + k1_b + ms_f + ms_t + ms_b
    m1 = k1_f + k1_t + k1_b
    m2 = k1_t
    m3 = ms_t
    m4 = k1_t + ms_t
    m5 = k1_t + k1_b + ms_t + ms_b
    return np.stack((m0, m1, m2, m3, m4, m5), axis=-3)


def validate_identities(base_counts: np.ndarray, methods: np.ndarray) -> None:
    values = np.asarray(base_counts)
    images = np.asarray(methods)
    k1_all = values[..., 0, :, :] + values[..., 1, :, :] + values[..., 2, :, :]
    ms_all = values[..., 3, :, :] + values[..., 4, :, :] + values[..., 5, :, :]
    front = values[..., 0, :, :] + values[..., 3, :, :]
    checks = (
        np.array_equal(images[..., 0, :, :], k1_all + ms_all),
        np.array_equal(images[..., 4, :, :], images[..., 2, :, :] + images[..., 3, :, :]),
        np.array_equal(images[..., 5, :, :], images[..., 0, :, :] - front),
    )
    if not all(checks):
        raise AssertionError("one or more M0/M4/M5 pixelwise identities failed")


def image_statistics(
    images: np.ndarray,
    *,
    allow_invalid: bool = False,
) -> dict[str, np.ndarray]:
    values = np.asarray(images, dtype=float)
    if values.shape[-2:] != (9, 9) or not np.isfinite(values).all():
        raise ValueError("E3 images must be finite and end with shape (9, 9)")
    roi_mean = values[..., DEFECT_MASK].mean(axis=-1)
    background_values = values[..., BACKGROUND_MASK]
    background_mean = background_values.mean(axis=-1)
    background_std = background_values.std(axis=-1, ddof=1)
    valid = np.isfinite(background_std) & (background_std > 0)
    cnr = np.full(background_std.shape, np.nan, dtype=float)
    cnr[valid] = np.abs(roi_mean[valid] - background_mean[valid]) / background_std[valid]
    if not allow_invalid and not valid.all():
        raise ValueError("CNR is undefined because background standard deviation is zero")
    if not allow_invalid and not np.isfinite(cnr).all():
        raise ValueError("CNR calculation produced a non-finite value")
    return {
        "roi_mean": roi_mean,
        "background_mean": background_mean,
        "background_std": background_std,
        "cnr": cnr,
    }


def relative_gain(
    numerator: np.ndarray,
    denominator: np.ndarray,
    label: str,
    *,
    allow_invalid: bool = False,
) -> np.ndarray:
    top = np.asarray(numerator, dtype=float)
    bottom = np.asarray(denominator, dtype=float)
    valid = np.isfinite(top) & np.isfinite(bottom) & (bottom > 0)
    if not allow_invalid and not valid.all():
        raise ValueError(f"{label} is undefined because its denominator is non-positive")
    result = np.full(np.broadcast_shapes(top.shape, bottom.shape), np.nan, dtype=float)
    top, bottom = np.broadcast_arrays(top, bottom)
    valid = np.broadcast_to(valid, result.shape)
    result[valid] = (top[valid] - bottom[valid]) / bottom[valid]
    if not allow_invalid and not np.isfinite(result).all():
        raise ValueError(f"{label} calculation produced a non-finite value")
    return result


def bootstrap_condition(
    base_counts: np.ndarray,
    rng: np.random.Generator,
    *,
    resample_count: int = RESAMPLE_COUNT,
) -> BootstrapResult:
    if resample_count <= 0:
        raise ValueError("resample_count must be positive")
    sampled_base = rng.poisson(np.asarray(base_counts, dtype=float), size=(resample_count, 6, 9, 9))
    sampled_methods = methods_from_base(sampled_base)
    validate_identities(sampled_base, sampled_methods)
    stats = image_statistics(sampled_methods, allow_invalid=True)
    totals = sampled_methods.sum(axis=(-2, -1), dtype=np.int64)
    retention = np.full(totals.shape, np.nan, dtype=float)
    valid_total = totals[:, 0] > 0
    retention[valid_total] = totals[valid_total] / totals[valid_total, 0][:, None]
    cnr = stats["cnr"]
    return BootstrapResult(
        method_images=sampled_methods,
        cnr=cnr,
        retention=retention,
        total_counts=totals,
        g_ms_cnr=relative_gain(cnr[:, 4], cnr[:, 2], "G_MS^CNR", allow_invalid=True),
        g_ms_count=relative_gain(totals[:, 4], totals[:, 2], "G_MS^N", allow_invalid=True),
        g_sr_cnr=relative_gain(cnr[:, 4], cnr[:, 1], "G_SR^CNR", allow_invalid=True),
        g_sr_count=relative_gain(totals[:, 4], totals[:, 1], "G_SR^N", allow_invalid=True),
        g_front_cnr=relative_gain(cnr[:, 5], cnr[:, 0], "G_FRONT^CNR", allow_invalid=True),
        g_front_count=relative_gain(totals[:, 5], totals[:, 0], "G_FRONT^N", allow_invalid=True),
    )


def percentile_interval(values: np.ndarray) -> tuple[float, float]:
    finite = np.asarray(values, dtype=float)
    finite = finite[np.isfinite(finite)]
    if not finite.size:
        raise ValueError("no valid Poisson resamples are available for an interval")
    low, high = np.percentile(finite, (2.5, 97.5))
    return float(low), float(high)


def effective_count(values: np.ndarray) -> int:
    return int(np.isfinite(np.asarray(values, dtype=float)).sum())


def roi_for_slit(
    slit_id: str, offset_x_mm: float = 0.0, offset_y_mm: float = 0.0
) -> DetectorAcceptanceRegion:
    matches = [
        item
        for item in acceptance_regions_for_profile(
            SLIT_PROFILE[slit_id], offset_x_mm, offset_y_mm
        )
        if item.slit_id == slit_id
    ]
    if len(matches) != 1:
        raise AssertionError(f"expected one detector acceptance region for {slit_id}")
    return matches[0]


def select_events(frame: pd.DataFrame, metadata: RunMetadata, slit_id: str) -> pd.DataFrame:
    expected_profile = SLIT_PROFILE[slit_id]
    if metadata.profile_id != expected_profile:
        raise ValueError(f"{slit_id} requires {expected_profile}: {metadata.metadata_path}")
    if frame.slit_group.isna().any() or not frame.slit_group.astype(str).eq(expected_profile).all():
        raise ValueError(f"slit_group must equal {expected_profile}: {metadata.metadata_path}")
    region = roi_for_slit(slit_id, metadata.head_offset_x_mm, metadata.head_offset_y_mm)
    mask = (
        frame.slit_label.astype(str).eq(slit_id)
        & frame.det_x.between(region.x_min_mm, region.x_max_mm, inclusive="both")
        & frame.det_y.between(region.y_min_mm, region.y_max_mm, inclusive="both")
    )
    selected = frame.loc[mask].copy()
    if selected.empty:
        raise ValueError(f"detector ROI selection is empty for {slit_id}: {metadata.metadata_path}")
    return selected


class EventLoader:
    def __init__(self) -> None:
        self._cache: dict[str, pd.DataFrame] = {}

    def read(self, path: Path) -> pd.DataFrame:
        key = path.resolve().as_posix()
        if key in self._cache:
            return self._cache[key]
        try:
            frame = pd.read_csv(path, usecols=list(EVENT_COLUMNS))
        except ValueError as error:
            raise ValueError(f"valid events are missing required E3 columns: {path}") from error
        for column in ("det_x", "det_y", "scatter_count_total", "first_scatter_z"):
            frame[column] = pd.to_numeric(frame[column], errors="raise")
        numeric = frame[["det_x", "det_y", "scatter_count_total"]].to_numpy(dtype=float)
        if not np.isfinite(numeric).all():
            raise ValueError(f"E3 numeric event columns must be finite: {path}")
        scatter_counts(frame)
        self._cache[key] = frame
        return frame


def validate_audit(results_root: Path) -> tuple[dict[str, Any], pd.DataFrame]:
    audit_dir = results_root / "data_processing" / "audit"
    summary_path = audit_dir / "audit_summary.yaml"
    inventory_path = audit_dir / "condition_inventory.csv"
    if not summary_path.is_file() or not inventory_path.is_file():
        raise FileNotFoundError("audit_summary.yaml and condition_inventory.csv are required")
    audit = yaml.safe_load(summary_path.read_text(encoding="utf-8"))
    if not isinstance(audit, dict) or audit.get("overall_status") != "pass":
        raise ValueError("articlev2 audit must pass before E3 analysis")
    return audit, pd.read_csv(inventory_path)


def inspect_inventory(inventory: pd.DataFrame) -> tuple[dict[tuple[str, str], pd.DataFrame], list[str], int]:
    required_columns = {
        "scan_mode",
        "phantom_id",
        "profile_id",
        "head_offset_x_mm",
        "head_offset_y_mm",
        "status",
        "valid_file",
    }
    missing_columns = sorted(required_columns.difference(inventory.columns))
    if missing_columns:
        return {}, ["condition inventory is missing columns: " + ", ".join(missing_columns)], 648
    required: list[tuple[str, str]] = []
    for index in range(1, 7):
        slit = f"S{index}"
        profile = SLIT_PROFILE[slit]
        required.extend((("P0", profile), (f"P{index}", profile)))
    required = list(dict.fromkeys(required))
    expected = expected_offsets()
    rows_by_condition: dict[tuple[str, str], pd.DataFrame] = {}
    issues: list[str] = []
    missing_pose_count = 0
    for phantom, profile in required:
        rows = inventory[
            inventory.scan_mode.astype(str).eq("grid")
            & inventory.phantom_id.astype(str).eq(phantom)
            & inventory.profile_id.astype(str).eq(profile)
            & inventory.status.astype(str).eq("valid")
        ].copy()
        found: list[tuple[float, float]] = []
        for row in rows.itertuples(index=False):
            try:
                point = (float(row.head_offset_x_mm), float(row.head_offset_y_mm))
            except (TypeError, ValueError):
                issues.append(f"{phantom}/{profile} contains a non-numeric grid coordinate")
                continue
            if not all(math.isfinite(value) for value in point):
                issues.append(f"{phantom}/{profile} contains a non-finite grid coordinate")
                continue
            found.append(point)
        duplicates = sorted({point for point in found if found.count(point) > 1})
        missing = sorted(expected.difference(found))
        extra = sorted(set(found).difference(expected))
        missing_pose_count += len(missing)
        if missing:
            issues.append(f"{phantom}/{profile}: {len(missing)} missing poses")
        if duplicates:
            issues.append(f"{phantom}/{profile}: duplicate poses {duplicates}")
        if extra:
            issues.append(f"{phantom}/{profile}: unexpected poses {extra}")
        if not missing and not duplicates and not extra and len(rows) == 81:
            rows_by_condition[(phantom, profile)] = rows
    return rows_by_condition, issues, missing_pose_count


def inspect_slab_root(slab_root: Path | None) -> tuple[list[tuple[Path, RunMetadata]], list[str], int]:
    if slab_root is None or not slab_root.is_dir():
        location = "not provided" if slab_root is None else slab_root.as_posix()
        return [], [f"P4 55 mm slab grid is missing: {location}"], 81
    manifest_path = slab_root / SLAB_MANIFEST_NAME
    issues: list[str] = []
    expected_geometry = ""
    expected_model = ""
    expected_n_primary = 0
    expected_seed_start = 0
    expected_seed_end = -1
    if not manifest_path.is_file():
        issues.append(f"slab provenance manifest is missing: {manifest_path}")
    else:
        value = yaml.safe_load(manifest_path.read_text(encoding="utf-8"))
        if not isinstance(value, dict):
            issues.append(f"slab provenance manifest must be a map: {manifest_path}")
        else:
            if value.get("schema_version") != 1:
                issues.append("slab provenance schema_version must be 1")
            if value.get("reference_type") != SLAB_REFERENCE_TYPE:
                issues.append(f"slab reference_type must be {SLAB_REFERENCE_TYPE}")
            if value.get("campaign_id") != SLAB_CAMPAIGN_ID:
                issues.append(f"slab campaign_id must be {SLAB_CAMPAIGN_ID}")
            try:
                thickness = float(value.get("thickness_mm"))
            except (TypeError, ValueError):
                thickness = math.nan
            if not math.isclose(thickness, SLAB_THICKNESS_MM):
                issues.append(f"slab thickness_mm must equal {SLAB_THICKNESS_MM:g}")
            expected_geometry = str(value.get("vehicle_geometry_file", "")).strip()
            if not expected_geometry:
                issues.append("slab vehicle_geometry_file must be declared")
            expected_model = str(value.get("vehicle_model_id", "")).strip()
            if expected_model != SLAB_MODEL_ID:
                issues.append(f"slab vehicle_model_id must be {SLAB_MODEL_ID}")
            if value.get("profile_id") != SLIT_PROFILE["S4"]:
                issues.append(f"slab profile_id must be {SLIT_PROFILE['S4']}")
            if value.get("slit_id") != "S4":
                issues.append("slab slit_id must be S4")
            try:
                manifest_energy = float(value.get("energy_keV"))
            except (TypeError, ValueError):
                manifest_energy = math.nan
            if not math.isclose(manifest_energy, EXPECTED_ENERGY_KEV):
                issues.append(f"slab manifest energy_keV must be {EXPECTED_ENERGY_KEV:g}")
            try:
                raw_n_primary = value.get("n_primary_per_pose")
                expected_n_primary = int(raw_n_primary)
                if float(raw_n_primary) != expected_n_primary:
                    raise ValueError
            except (TypeError, ValueError):
                expected_n_primary = 0
            if expected_n_primary != SLAB_N_PRIMARY:
                issues.append(f"slab n_primary_per_pose must be {SLAB_N_PRIMARY}")
            try:
                raw_pose_count = value.get("pose_count")
                pose_count = int(raw_pose_count)
                if float(raw_pose_count) != pose_count:
                    raise ValueError
            except (TypeError, ValueError):
                pose_count = 0
            if pose_count != 81:
                issues.append("slab manifest pose_count must be 81")
            for axis in ("x", "y"):
                try:
                    offsets = tuple(float(item) for item in value.get(f"{axis}_offsets_mm", ()))
                except (TypeError, ValueError):
                    offsets = ()
                if offsets != tuple(float(item) for item in GRID_OFFSETS_MM):
                    issues.append(f"slab manifest {axis}_offsets_mm must equal the frozen 9-point grid")
            try:
                raw_seed_start = value.get("seed_start")
                raw_seed_end = value.get("seed_end")
                expected_seed_start = int(raw_seed_start)
                expected_seed_end = int(raw_seed_end)
                if (
                    float(raw_seed_start) != expected_seed_start
                    or float(raw_seed_end) != expected_seed_end
                ):
                    raise ValueError
            except (TypeError, ValueError):
                expected_seed_start, expected_seed_end = 0, -1
            if (expected_seed_start, expected_seed_end) != (SLAB_SEED_START, SLAB_SEED_END):
                issues.append(
                    f"slab seed range must be {SLAB_SEED_START}--{SLAB_SEED_END}"
                )
    runs: list[tuple[Path, RunMetadata]] = []
    for event_path in sorted(slab_root.rglob("events_valid.csv")):
        try:
            runs.append((event_path, load_run_metadata(event_path.parent / "metadata.yaml")))
        except (FileNotFoundError, ValueError) as error:
            issues.append(str(error))
    found = [(item.head_offset_x_mm, item.head_offset_y_mm) for _, item in runs]
    duplicates = sorted({point for point in found if found.count(point) > 1})
    missing = sorted(expected_offsets().difference(found))
    extra = sorted(set(found).difference(expected_offsets()))
    if missing:
        issues.append(f"P4 slab/P001: {len(missing)} missing poses")
    if duplicates:
        issues.append(f"P4 slab/P001: duplicate poses {duplicates}")
    if extra:
        issues.append(f"P4 slab/P001: unexpected poses {extra}")
    if runs:
        profiles = {item.profile_id for _, item in runs}
        modes = {item.scan_mode for _, item in runs}
        energies = {item.energy_keV for _, item in runs}
        histories = {item.n_primary for _, item in runs}
        phantom_ids = {item.phantom_id for _, item in runs}
        geometry_ids = {
            str(item.raw.get("vehicle_geometry_file", "")).strip() for _, item in runs
        }
        seeds: list[int] = []
        seed_parse_failed = False
        for _, item in runs:
            raw_seed = item.raw.get("random_seed")
            raw_base_seed = item.raw.get("base_random_seed")
            try:
                seed = int(raw_seed)
                base_seed = int(raw_base_seed)
                if float(raw_seed) != seed or float(raw_base_seed) != base_seed:
                    raise ValueError
            except (TypeError, ValueError):
                seed_parse_failed = True
                continue
            if seed != base_seed:
                issues.append(f"slab random_seed/base_random_seed mismatch: {item.metadata_path}")
            seeds.append(seed)
        if profiles != {SLIT_PROFILE["S4"]}:
            issues.append(f"slab grid must use P001 for S4, found {sorted(profiles)}")
        if modes != {"grid"}:
            issues.append(f"slab runs must all use grid mode, found {sorted(modes)}")
        if len(energies) != 1 or not math.isclose(next(iter(energies)), EXPECTED_ENERGY_KEV):
            issues.append(f"slab energy must be {EXPECTED_ENERGY_KEV:g} keV")
        if len(histories) != 1:
            issues.append("slab runs must use one common n_primary")
        elif histories != {expected_n_primary} or histories != {SLAB_N_PRIMARY}:
            issues.append(f"slab metadata n_primary must be {SLAB_N_PRIMARY}")
        if len(phantom_ids) != 1:
            issues.append("slab runs must use one common vehicle_model_id")
        elif phantom_ids != {expected_model} or phantom_ids != {SLAB_MODEL_ID}:
            issues.append(f"slab metadata vehicle_model_id must be {SLAB_MODEL_ID}")
        if len(geometry_ids) != 1 or not next(iter(geometry_ids), ""):
            issues.append("slab runs must share one non-empty vehicle_geometry_file")
        elif expected_geometry and geometry_ids != {expected_geometry}:
            issues.append(
                "slab metadata vehicle_geometry_file does not match reference_manifest.yaml"
            )
        if seed_parse_failed:
            issues.append("slab metadata random_seed/base_random_seed must be finite integers")
        elif len(seeds) != len(set(seeds)):
            issues.append("slab metadata seeds must be unique")
        elif set(seeds) != set(range(expected_seed_start, expected_seed_end + 1)):
            issues.append(
                f"slab metadata seeds must cover {SLAB_SEED_START}--{SLAB_SEED_END} exactly"
            )
    return runs, issues, len(missing)


def preflight(
    results_root: Path, slab_root: Path | None
) -> tuple[pd.DataFrame, dict[tuple[str, str], pd.DataFrame], list[tuple[Path, RunMetadata]], dict[str, Any]]:
    _, inventory = validate_audit(results_root)
    conditions, main_issues, main_missing = inspect_inventory(inventory)
    slab_runs, slab_issues, slab_missing = inspect_slab_root(slab_root)
    report = {
        "main_data_dir": (results_root / "events" / "valid" / "grid").resolve(),
        "slab_data_dir": slab_root.resolve() if slab_root is not None else None,
        "main_missing_pose_count": main_missing,
        "slab_missing_pose_count": slab_missing,
        "complete": not main_issues and not slab_issues,
    }
    issues = [*main_issues, *slab_issues]
    if issues:
        raise E3PreflightError(issues, report)
    return inventory, conditions, slab_runs, report


def _validate_run_metadata(
    metadata: RunMetadata,
    *,
    phantom: str | None,
    profile: str,
    x: float,
    y: float,
) -> None:
    if metadata.scan_mode != "grid" or metadata.profile_id != profile:
        raise ValueError(f"metadata mode/profile mismatch: {metadata.metadata_path}")
    if phantom is not None and metadata.phantom_id != phantom:
        raise ValueError(f"metadata phantom mismatch: {metadata.metadata_path}")
    if not (math.isclose(metadata.head_offset_x_mm, x) and math.isclose(metadata.head_offset_y_mm, y)):
        raise ValueError(f"metadata grid coordinate mismatch: {metadata.metadata_path}")
    if not math.isclose(metadata.energy_keV, EXPECTED_ENERGY_KEV):
        raise ValueError(f"metadata energy must be {EXPECTED_ENERGY_KEV:g} keV: {metadata.metadata_path}")


def load_grid_condition(
    results_root: Path,
    rows: pd.DataFrame,
    phantom: str,
    slit: str,
    loader: EventLoader,
) -> GridCondition:
    profile = SLIT_PROFILE[slit]
    interval = target_z_range(f"P{slit[1:]}")
    if interval is None:
        raise AssertionError(f"missing target interval for {slit}")
    base = np.zeros((6, 9, 9), dtype=np.int64)
    histories: set[int] = set()
    energies: set[float] = set()
    for row in rows.itertuples(index=False):
        x, y = float(row.head_offset_x_mm), float(row.head_offset_y_mm)
        event_path = (results_root / str(row.valid_file)).resolve()
        if not event_path.is_file():
            raise FileNotFoundError(f"valid event file not found: {event_path}")
        metadata = load_run_metadata(event_path.parent / "metadata.yaml")
        _validate_run_metadata(metadata, phantom=phantom, profile=profile, x=x, y=y)
        frame = select_events(loader.read(event_path), metadata, slit)
        row_index, column_index = grid_position_indices(x, y)
        base[:, row_index, column_index] = category_counts(frame, interval)
        histories.add(metadata.n_primary)
        energies.add(metadata.energy_keV)
    if len(histories) != 1 or len(energies) != 1:
        raise ValueError(f"{phantom}-{slit} must use one common energy and n_primary")
    methods = methods_from_base(base)
    validate_identities(base, methods)
    return GridCondition(phantom, slit, base, histories.pop(), energies.pop())


def load_slab_condition(
    runs: list[tuple[Path, RunMetadata]], loader: EventLoader
) -> SlabCondition:
    image = np.zeros((9, 9), dtype=np.int64)
    histories: set[int] = set()
    energies: set[float] = set()
    geometry_ids: set[str] = set()
    for event_path, metadata in runs:
        x, y = metadata.head_offset_x_mm, metadata.head_offset_y_mm
        _validate_run_metadata(metadata, phantom=None, profile=SLIT_PROFILE["S4"], x=x, y=y)
        selected = select_events(loader.read(event_path), metadata, "S4")
        row_index, column_index = grid_position_indices(x, y)
        image[row_index, column_index] = int((scatter_counts(selected) >= 1).sum())
        histories.add(metadata.n_primary)
        energies.add(metadata.energy_keV)
        geometry_ids.add(str(metadata.raw.get("vehicle_geometry_file", "")).strip())
    if len(histories) != 1 or len(energies) != 1 or len(geometry_ids) != 1:
        raise ValueError("slab grid metadata are not internally consistent")
    return SlabCondition(image, histories.pop(), energies.pop(), geometry_ids.pop())


def condition_point_estimates(condition: GridCondition) -> dict[str, np.ndarray]:
    methods = methods_from_base(condition.base_counts)
    validate_identities(condition.base_counts, methods)
    stats = image_statistics(methods)
    totals = methods.sum(axis=(-2, -1), dtype=np.int64)
    if totals[0] <= 0:
        raise ValueError(f"{condition.phantom}-{condition.slit} has zero M0 count")
    retention = totals / totals[0]
    cnr = stats["cnr"]
    return {
        "methods": methods,
        "totals": totals,
        "retention": retention,
        **stats,
        "g_ms_cnr": relative_gain(cnr[4], cnr[2], "G_MS^CNR"),
        "g_ms_count": relative_gain(totals[4], totals[2], "G_MS^N"),
        "g_sr_cnr": relative_gain(cnr[4], cnr[1], "G_SR^CNR"),
        "g_sr_count": relative_gain(totals[4], totals[1], "G_SR^N"),
        "g_front_cnr": relative_gain(cnr[5], cnr[0], "G_FRONT^CNR"),
        "g_front_count": relative_gain(totals[5], totals[0], "G_FRONT^N"),
    }


def _save_png(fig: plt.Figure, path: Path) -> None:
    if path.suffix.lower() != ".png":
        raise ValueError(f"E3 figures must use PNG: {path}")
    fig.savefig(path, dpi=300, facecolor="white", bbox_inches="tight")
    plt.close(fig)


def _heatmap(
    axis: plt.Axes,
    image: np.ndarray,
    *,
    title: str,
    cmap: Any,
    norm: Any = None,
    colorbar_label: str,
) -> Any:
    mesh = axis.pcolormesh(GRID_EDGE_MM, GRID_EDGE_MM, image, cmap=cmap, norm=norm, shading="flat")
    axis.add_patch(Rectangle((-6.25, -6.25), 12.5, 12.5, fill=False, edgecolor="black", linewidth=1.1))
    axis.set(
        title=title,
        xlabel="Scan x (mm)",
        ylabel="Scan y (mm)",
        xticks=(-10, -5, 0, 5, 10),
        yticks=(-10, -5, 0, 5, 10),
    )
    axis.set_aspect("equal")
    colorbar = axis.figure.colorbar(mesh, ax=axis, shrink=0.82, pad=0.03)
    colorbar.set_label(colorbar_label)
    return colorbar


def plot_f1(methods: np.ndarray, output: Path) -> None:
    cmap = LinearSegmentedColormap.from_list("e3_blues", ("#F7FBFF", "#6BAED6", "#08306B"))
    fig, axes = plt.subplots(2, 3, figsize=(13.4, 8.2), constrained_layout=True)
    layout = ((0, 2, 4), (1, 3, 5))
    for row_index, row in enumerate(layout):
        for column_index, method_index in enumerate(row):
            method = METHODS[method_index]
            colorbar = _heatmap(
                axes[row_index, column_index],
                methods[method_index],
                title=f"{method}: {METHOD_LABELS[method]}",
                cmap=cmap,
                colorbar_label="Raw detected count",
            )
            formatter = ScalarFormatter(useMathText=True)
            formatter.set_powerlimits((-2, 3))
            colorbar.formatter = formatter
            colorbar.update_ticks()
    fig.suptitle("E3-F1  P4–S4 source-conditioned raw-count images")
    _save_png(fig, output)


def _series_with_ci(
    axis: plt.Axes,
    x: np.ndarray,
    y: np.ndarray,
    intervals: np.ndarray,
    *,
    label: str,
    color: str,
    marker: str,
) -> None:
    errors = np.vstack(
        (np.maximum(y - intervals[:, 0], 0.0), np.maximum(intervals[:, 1] - y, 0.0))
    )
    axis.errorbar(x, y, yerr=errors, color=color, marker=marker, lw=1.0, capsize=2.5, label=label)


def _depth_values() -> tuple[tuple[str, ...], np.ndarray]:
    phantoms = tuple(DEFECT_CENTER_Z_MM)
    return phantoms, np.asarray([DEFECT_CENTER_Z_MM[item] for item in phantoms], dtype=float)


def _method_depth_series(
    points: dict[str, dict[str, np.ndarray]],
    boots: dict[str, BootstrapResult],
    method: str,
    metric: str,
) -> tuple[np.ndarray, np.ndarray]:
    phantoms, _ = _depth_values()
    index = METHODS.index(method)
    point_values = np.asarray([points[item][metric][index] for item in phantoms], dtype=float)
    boot_values = np.asarray(
        [percentile_interval(getattr(boots[item], metric)[:, index]) for item in phantoms]
    )
    return point_values, boot_values


def _format_depth_axis(axis: plt.Axes, depths: np.ndarray, *, percent: bool = False) -> None:
    axis.set_xticks(depths)
    axis.set_xticklabels([f"{depth:g}\nP{index}" for index, depth in enumerate(depths, start=1)])
    axis.grid(alpha=0.2)
    if percent:
        axis.yaxis.set_major_formatter(PercentFormatter(1.0))


def plot_f2(
    points: dict[str, dict[str, np.ndarray]],
    boots: dict[str, BootstrapResult],
    output: Path,
) -> None:
    _, depths = _depth_values()
    fig, axes = plt.subplots(1, 2, figsize=(12.4, 5.0), constrained_layout=True)
    for method in ("M1", "M4"):
        for axis, metric in zip(axes, ("cnr", "retention"), strict=True):
            values, intervals = _method_depth_series(points, boots, method, metric)
            _series_with_ci(
                axis, depths, values, intervals,
                label=f"{method} {METHOD_LABELS[method]}",
                color=METHOD_COLORS[method], marker=METHOD_MARKERS[method],
            )
    axes[0].set(xlabel="Target depth (mm)", ylabel="CNR", title="(a) M1/M4 CNR")
    axes[1].set(xlabel="Target depth (mm)", ylabel="Count retention", title="(b) M1/M4 retention")
    for axis in axes:
        _format_depth_axis(axis, depths, percent=axis is axes[1])
        axis.legend(fontsize=8)
    fig.suptitle("E3-F2  M1 versus M4 across target depth")
    _save_png(fig, output)


def plot_f3(
    points: dict[str, dict[str, np.ndarray]],
    boots: dict[str, BootstrapResult],
    output: Path,
) -> None:
    phantoms, depths = _depth_values()
    fig, axes = plt.subplots(1, 3, figsize=(16.0, 5.0), constrained_layout=True)
    for method in ("M0", "M5"):
        values, intervals = _method_depth_series(points, boots, method, "cnr")
        _series_with_ci(
            axes[0], depths, values, intervals,
            label=f"{method} {METHOD_LABELS[method]}",
            color=METHOD_COLORS[method], marker=METHOD_MARKERS[method],
        )
    gain = np.asarray([points[item]["g_front_cnr"] for item in phantoms], dtype=float)
    gain_ci = np.asarray([percentile_interval(boots[item].g_front_cnr) for item in phantoms])
    _series_with_ci(
        axes[1], depths, gain, gain_ci, label="M0→M5 CNR",
        color=METHOD_COLORS["M5"], marker=METHOD_MARKERS["M5"],
    )
    retention, retention_ci = _method_depth_series(points, boots, "M5", "retention")
    _series_with_ci(
        axes[2], depths, retention, retention_ci, label="M5",
        color=METHOD_COLORS["M5"], marker=METHOD_MARKERS["M5"],
    )
    specs = (
        (axes[0], "(a) M0/M5 CNR", "CNR", False),
        (axes[1], "(b) M0→M5 relative CNR change", "Relative change", True),
        (axes[2], "(c) M5 count retention", "Retention", True),
    )
    for axis, title, ylabel, percent in specs:
        axis.set(xlabel="Target depth (mm)", ylabel=ylabel, title=title)
        _format_depth_axis(axis, depths, percent=percent)
        axis.legend(fontsize=8)
    axes[1].axhline(0.0, color="#777777", lw=0.9, ls="--")
    fig.suptitle("E3-F3  Effect of removing front-source events")
    _save_png(fig, output)


def plot_f4(
    points: dict[str, dict[str, np.ndarray]],
    boots: dict[str, BootstrapResult],
    output: Path,
) -> None:
    _, depths = _depth_values()
    fig, axis = plt.subplots(figsize=(10.5, 6.4), constrained_layout=True)
    for method in METHODS:
        values, intervals = _method_depth_series(points, boots, method, "cnr")
        _series_with_ci(
            axis, depths, values, intervals,
            label=f"{method} {METHOD_LABELS[method]}",
            color=METHOD_COLORS[method], marker=METHOD_MARKERS[method],
        )
    axis.set(xlabel="Target depth (mm)", ylabel="CNR", title="E3-F4  M0–M5 CNR by target depth")
    _format_depth_axis(axis, depths)
    axis.legend(fontsize=8, ncol=2)
    _save_png(fig, output)


def plot_f5(
    points: dict[str, dict[str, np.ndarray]],
    boots: dict[str, BootstrapResult],
    output: Path,
) -> None:
    _, depths = _depth_values()
    fig, axis = plt.subplots(figsize=(10.5, 6.4), constrained_layout=True)
    for method in METHODS:
        values, intervals = _method_depth_series(points, boots, method, "retention")
        _series_with_ci(
            axis, depths, values, intervals,
            label=f"{method} {METHOD_LABELS[method]}",
            color=METHOD_COLORS[method], marker=METHOD_MARKERS[method],
        )
    axis.set(
        xlabel="Target depth (mm)", ylabel="Count retention",
        title="E3-F5  M0–M5 count retention by target depth",
    )
    _format_depth_axis(axis, depths, percent=True)
    axis.legend(fontsize=8, ncol=2)
    _save_png(fig, output)


def relative_background_response(image: np.ndarray) -> np.ndarray:
    values = np.asarray(image, dtype=float)
    mean = float(values[BACKGROUND_MASK].mean())
    if not math.isfinite(mean) or math.isclose(mean, 0.0):
        raise ValueError("background-relative response is undefined because background mean is zero")
    result = (values - mean) / mean
    if not np.isfinite(result).all():
        raise ValueError("background-relative response produced a non-finite value")
    return result


def plot_f6(
    p4_point: dict[str, np.ndarray],
    p4_boot: BootstrapResult,
    slab: SlabCondition,
    rng: np.random.Generator,
    output: Path,
    *,
    resample_count: int,
) -> dict[str, Any]:
    alpha = p4_point["n_primary"] / slab.n_primary
    total = p4_point["methods"][0].astype(float)
    ideal = p4_point["methods"][5].astype(float)
    reference = total - alpha * slab.image
    images = (total, ideal, reference)
    deltas = tuple(relative_background_response(item) for item in images)
    limit = max(float(np.max(np.abs(item))) for item in deltas)
    if not math.isfinite(limit) or limit <= 0:
        raise ValueError("F4 shared symmetric color limit is undefined")
    cmap = LinearSegmentedColormap.from_list("e3_diverging", ("#2166AC", "#FFFFFF", "#E66101"))
    norm = TwoSlopeNorm(vmin=-limit, vcenter=0.0, vmax=limit)
    fig, axes = plt.subplots(1, 3, figsize=(13.0, 4.5), constrained_layout=True)
    titles = ("(a) Total", "(b) Truth: remove front", "(c) Slab-reference subtraction")
    for axis, delta, title in zip(axes, deltas, titles, strict=True):
        _heatmap(axis, delta, title=title, cmap=cmap, norm=norm, colorbar_label=r"Background-relative response $\delta$")
    slab_samples = rng.poisson(slab.image, size=(resample_count, 9, 9))
    reference_samples = p4_boot.method_images[:, 0].astype(float) - alpha * slab_samples
    reference_cnr = image_statistics(reference_samples, allow_invalid=True)["cnr"]
    ref_stats = image_statistics(reference[None, :, :])
    fig.suptitle("E3-F6  P4–S4 front-source removal and reference subtraction")
    _save_png(fig, output)
    return {
        "alpha": float(alpha),
        "reference_image": reference,
        "reference_samples": reference_samples,
        "reference_stats": {key: float(value[0]) for key, value in ref_stats.items()},
        "reference_cnr_samples": reference_cnr,
    }


def write_tables(
    points: dict[str, dict[str, np.ndarray]],
    boots: dict[str, BootstrapResult],
    reference_result: dict[str, Any] | None,
    output_dir: Path,
) -> None:
    p4 = points["P4"]
    p4_boot = boots["P4"]
    t1_rows: list[dict[str, Any]] = []
    for index, method in enumerate(METHODS):
        retention_ci = percentile_interval(p4_boot.retention[:, index])
        cnr_ci = percentile_interval(p4_boot.cnr[:, index])
        t1_rows.append(
            {
                "method": method,
                "total_count_N": int(p4["totals"][index]),
                "retention_eta": float(p4["retention"][index]),
                "retention_ci_low": retention_ci[0],
                "retention_ci_high": retention_ci[1],
                "retention_n_effective": effective_count(p4_boot.retention[:, index]),
                "roi_mean": float(p4["roi_mean"][index]),
                "background_mean": float(p4["background_mean"][index]),
                "background_std": float(p4["background_std"][index]),
                "cnr": float(p4["cnr"][index]),
                "cnr_ci_low": cnr_ci[0],
                "cnr_ci_high": cnr_ci[1],
                "cnr_n_effective": effective_count(p4_boot.cnr[:, index]),
            }
        )
    pd.DataFrame(t1_rows, columns=T1_COLUMNS).to_csv(output_dir / TABLE_NAMES[0], index=False)

    t2_rows: list[dict[str, Any]] = []
    for phantom, depth in DEFECT_CENTER_Z_MM.items():
        point, boot = points[phantom], boots[phantom]
        for index, method in enumerate(METHODS):
            retention_ci = percentile_interval(boot.retention[:, index])
            cnr_ci = percentile_interval(boot.cnr[:, index])
            t2_rows.append(
                {
                    "phantom": phantom,
                    "slit": matched_slit(phantom),
                    "target_depth_mm": float(depth),
                    "method": method,
                    "total_count_N": int(point["totals"][index]),
                    "retention_eta": float(point["retention"][index]),
                    "retention_ci_low": retention_ci[0],
                    "retention_ci_high": retention_ci[1],
                    "retention_n_effective": effective_count(boot.retention[:, index]),
                    "roi_mean": float(point["roi_mean"][index]),
                    "background_mean": float(point["background_mean"][index]),
                    "background_std": float(point["background_std"][index]),
                    "cnr": float(point["cnr"][index]),
                    "cnr_ci_low": cnr_ci[0],
                    "cnr_ci_high": cnr_ci[1],
                    "cnr_n_effective": effective_count(boot.cnr[:, index]),
                }
            )
    pd.DataFrame(t2_rows, columns=T2_COLUMNS).to_csv(output_dir / TABLE_NAMES[1], index=False)

    t3_rows: list[dict[str, Any]] = []
    for phantom, depth in DEFECT_CENTER_Z_MM.items():
        point, boot = points[phantom], boots[phantom]
        for comparison, from_method, to_method in COMPARISONS:
            from_index = METHODS.index(from_method)
            to_index = METHODS.index(to_method)
            g_cnr = relative_gain(
                point["cnr"][to_index], point["cnr"][from_index], f"{comparison}-CNR"
            )
            g_count = relative_gain(
                point["totals"][to_index], point["totals"][from_index], f"{comparison}-count"
            )
            g_cnr_samples = relative_gain(
                boot.cnr[:, to_index], boot.cnr[:, from_index], f"{comparison}-CNR",
                allow_invalid=True,
            )
            g_count_samples = relative_gain(
                boot.total_counts[:, to_index], boot.total_counts[:, from_index],
                f"{comparison}-count", allow_invalid=True,
            )
            cnr_ci = percentile_interval(g_cnr_samples)
            count_ci = percentile_interval(g_count_samples)
            t3_rows.append(
                {
                    "phantom": phantom,
                    "slit": matched_slit(phantom),
                    "target_depth_mm": float(depth),
                    "comparison": comparison,
                    "from_method": from_method,
                    "to_method": to_method,
                    "from_cnr": float(point["cnr"][from_index]),
                    "to_cnr": float(point["cnr"][to_index]),
                    "g_cnr": float(g_cnr),
                    "g_cnr_ci_low": cnr_ci[0],
                    "g_cnr_ci_high": cnr_ci[1],
                    "g_cnr_n_effective": effective_count(g_cnr_samples),
                    "from_count_N": int(point["totals"][from_index]),
                    "to_count_N": int(point["totals"][to_index]),
                    "g_count": float(g_count),
                    "g_count_ci_low": count_ci[0],
                    "g_count_ci_high": count_ci[1],
                    "g_count_n_effective": effective_count(g_count_samples),
                }
            )
    pd.DataFrame(t3_rows, columns=T3_COLUMNS).to_csv(output_dir / TABLE_NAMES[2], index=False)

    # The first three tables depend only on the complete matched P0/P1--P6
    # grids.  Keeping this boundary explicit lets the separately documented
    # core runner publish M0--M5 results when the optional slab acquisition is
    # unavailable, without inventing E3-T4 values.
    if reference_result is None:
        return

    t4_rows: list[dict[str, Any]] = []
    for image_name, method_index in (("M0", 0), ("M5", 5)):
        cnr_samples = p4_boot.cnr[:, method_index]
        cnr_ci = percentile_interval(cnr_samples)
        t4_rows.append(
            {
                "image": image_name,
                "count_metric": float(p4["totals"][method_index]),
                "count_metric_kind": "raw_count",
                "roi_mean": float(p4["roi_mean"][method_index]),
                "background_mean": float(p4["background_mean"][method_index]),
                "background_std": float(p4["background_std"][method_index]),
                "cnr": float(p4["cnr"][method_index]),
                "cnr_ci_low": cnr_ci[0],
                "cnr_ci_high": cnr_ci[1],
                "cnr_n_effective": effective_count(cnr_samples),
            }
        )
    reference_cnr_samples = reference_result["reference_cnr_samples"]
    reference_cnr_ci = percentile_interval(reference_cnr_samples)
    reference_stats = reference_result["reference_stats"]
    t4_rows.append(
        {
            "image": "reference_subtracted",
            "count_metric": float(np.asarray(reference_result["reference_image"]).sum()),
            "count_metric_kind": "signed_equivalent_count",
            "roi_mean": reference_stats["roi_mean"],
            "background_mean": reference_stats["background_mean"],
            "background_std": reference_stats["background_std"],
            "cnr": reference_stats["cnr"],
            "cnr_ci_low": reference_cnr_ci[0],
            "cnr_ci_high": reference_cnr_ci[1],
            "cnr_n_effective": effective_count(reference_cnr_samples),
        }
    )
    pd.DataFrame(t4_rows, columns=T4_COLUMNS).to_csv(output_dir / TABLE_NAMES[3], index=False)


def validate_outputs(output_dir: Path) -> None:
    entries = list(output_dir.iterdir())
    actual = {path.name for path in entries if path.is_file()}
    unexpected = sorted(
        path.name
        for path in entries
        if path.name not in OUTPUT_NAMES and path.name != SUPPLEMENTARY_DIR_NAME
    )
    supplementary = output_dir / SUPPLEMENTARY_DIR_NAME
    if supplementary.exists() and not supplementary.is_dir():
        unexpected.append(SUPPLEMENTARY_DIR_NAME)
    if actual != set(OUTPUT_NAMES) or unexpected:
        raise AssertionError(
            f"E3 output contract mismatch: expected formal files {sorted(OUTPUT_NAMES)} "
            f"and optional {SUPPLEMENTARY_DIR_NAME}/, got files {sorted(actual)} "
            f"and unexpected entries {sorted(set(unexpected))}"
        )
    t1 = pd.read_csv(output_dir / TABLE_NAMES[0])
    t2 = pd.read_csv(output_dir / TABLE_NAMES[1])
    t3 = pd.read_csv(output_dir / TABLE_NAMES[2])
    t4 = pd.read_csv(output_dir / TABLE_NAMES[3])
    if tuple(t1.columns) != T1_COLUMNS or len(t1) != 6 or tuple(t1.method) != METHODS:
        raise AssertionError("E3-T1 schema or row contract failed")
    if (
        tuple(t2.columns) != T2_COLUMNS
        or len(t2) != 36
        or set(t2.method) != set(METHODS)
        or set(t2.phantom) != set(DEFECT_CENTER_Z_MM)
        or not (t2.groupby("phantom").size() == 6).all()
    ):
        raise AssertionError("E3-T2 schema or row contract failed")
    if (
        tuple(t3.columns) != T3_COLUMNS
        or len(t3) != 18
        or set(t3.comparison) != {item[0] for item in COMPARISONS}
        or not (t3.groupby("phantom").size() == 3).all()
    ):
        raise AssertionError("E3-T3 schema or row contract failed")
    if (
        tuple(t4.columns) != T4_COLUMNS
        or len(t4) != 3
        or tuple(t4.image) != ("M0", "M5", "reference_subtracted")
        or any("difference" in column.lower() for column in t4.columns)
    ):
        raise AssertionError("E3-T4 schema or row contract failed")
    if not np.issubdtype(t1.total_count_N.dtype, np.integer):
        raise AssertionError("E3-T1 total_count_N must be stored as integers")
    if not np.issubdtype(t2.total_count_N.dtype, np.integer):
        raise AssertionError("E3-T2 total_count_N must be stored as integers")
    t1_numeric = t1.drop(columns="method").to_numpy(dtype=float)
    t2_numeric = t2.drop(columns=["phantom", "slit", "method"]).to_numpy(dtype=float)
    t3_numeric = t3.drop(
        columns=["phantom", "slit", "comparison", "from_method", "to_method"]
    ).to_numpy(dtype=float)
    t4_numeric = t4.drop(columns=["image", "count_metric_kind"]).to_numpy(dtype=float)
    if not all(
        np.isfinite(values).all()
        for values in (t1_numeric, t2_numeric, t3_numeric, t4_numeric)
    ):
        raise AssertionError("E3 CSV outputs contain non-finite values")
    n_effective_columns = [
        column
        for frame in (t1, t2, t3, t4)
        for column in frame.columns
        if column.endswith("_n_effective")
    ]
    if not n_effective_columns:
        raise AssertionError("E3 outputs do not report effective resample counts")
    for frame in (t1, t2, t3, t4):
        for column in frame.columns:
            if column.endswith("_n_effective") and not (frame[column] > 0).all():
                raise AssertionError(f"E3 effective resample count is non-positive: {column}")
    for name in FIGURE_NAMES:
        path = output_dir / name
        if path.read_bytes()[:8] != b"\x89PNG\r\n\x1a\n":
            raise AssertionError(f"E3 figure is not a valid PNG: {path}")


def run_e3(
    conditions: dict[str, GridCondition],
    slab: SlabCondition,
    output_dir: Path,
    *,
    resample_seed: int = DEFAULT_RESAMPLE_SEED,
    resample_count: int = RESAMPLE_COUNT,
) -> dict[str, Any]:
    expected = set(DEFECT_CENTER_Z_MM)
    if set(conditions) != expected:
        raise ValueError(f"E3 requires conditions {sorted(expected)}, got {sorted(conditions)}")
    output_dir.mkdir(parents=True, exist_ok=True)
    rng = np.random.default_rng(resample_seed)
    points: dict[str, dict[str, np.ndarray]] = {}
    boots: dict[str, BootstrapResult] = {}
    for phantom in DEFECT_CENTER_Z_MM:
        condition = conditions[phantom]
        point = condition_point_estimates(condition)
        point["n_primary"] = condition.n_primary
        points[phantom] = point
        boots[phantom] = bootstrap_condition(
            condition.base_counts, rng, resample_count=resample_count
        )
    if not math.isclose(conditions["P4"].energy_keV, slab.energy_keV):
        raise ValueError("P4 and slab energies must match")
    plot_f1(points["P4"]["methods"], output_dir / FIGURE_NAMES[0])
    plot_f2(points, boots, output_dir / FIGURE_NAMES[1])
    plot_f3(points, boots, output_dir / FIGURE_NAMES[2])
    plot_f4(points, boots, output_dir / FIGURE_NAMES[3])
    plot_f5(points, boots, output_dir / FIGURE_NAMES[4])
    reference_result = plot_f6(
        points["P4"], boots["P4"], slab, rng, output_dir / FIGURE_NAMES[5],
        resample_count=resample_count,
    )
    write_tables(points, boots, reference_result, output_dir)
    validate_outputs(output_dir)
    return {"identities_passed": True, "alpha": reference_result["alpha"]}


def run_analysis(
    results_root: Path,
    slab_root: Path | None,
    output_dir: Path,
    *,
    resample_seed: int = DEFAULT_RESAMPLE_SEED,
) -> dict[str, Any]:
    _, rows_by_condition, slab_runs, report = preflight(results_root, slab_root)
    loader = EventLoader()
    defect_conditions: dict[str, GridCondition] = {}
    for index in range(1, 7):
        phantom, slit = f"P{index}", f"S{index}"
        profile = SLIT_PROFILE[slit]
        load_grid_condition(results_root, rows_by_condition[("P0", profile)], "P0", slit, loader)
        defect_conditions[phantom] = load_grid_condition(
            results_root, rows_by_condition[(phantom, profile)], phantom, slit, loader
        )
    slab = load_slab_condition(slab_runs, loader)
    result = run_e3(
        defect_conditions,
        slab,
        output_dir,
        resample_seed=resample_seed,
        resample_count=RESAMPLE_COUNT,
    )
    return {**report, **result}


def publish(staging: Path, output_dir: Path, overwrite: bool) -> None:
    if output_dir.exists():
        existing = list(output_dir.iterdir())
        unexpected = sorted(
            path.name
            for path in existing
            if path.name not in OUTPUT_NAMES and path.name != SUPPLEMENTARY_DIR_NAME
        )
        supplementary = output_dir / SUPPLEMENTARY_DIR_NAME
        if supplementary.exists() and not supplementary.is_dir():
            unexpected.append(SUPPLEMENTARY_DIR_NAME)
        if unexpected:
            raise FileExistsError(f"unexpected files block E3 publication: {unexpected}")
        if existing and not overwrite:
            raise FileExistsError(f"E3 outputs exist; pass --overwrite: {output_dir}")
        backup = output_dir.parent / f".{output_dir.name}.backup"
        if backup.exists():
            raise FileExistsError(f"stale E3 backup blocks overwrite: {backup}")
        if supplementary.is_dir():
            shutil.copytree(supplementary, staging / SUPPLEMENTARY_DIR_NAME)
        validate_outputs(staging)
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


def target_output_paths(output_dir: Path) -> tuple[Path, ...]:
    return tuple(output_dir / name for name in OUTPUT_NAMES)


def print_report(
    *,
    results_root: Path,
    slab_root: Path | None,
    output_dir: Path,
    complete: bool,
    identities: str,
    issues: Iterable[str],
) -> None:
    print(f"main data directory: {(results_root / 'events' / 'valid' / 'grid').resolve()}")
    print(f"slab data directory: {slab_root.resolve() if slab_root is not None else 'not provided'}")
    print(f"81-pose completeness: {'pass' if complete else 'fail'}")
    print(f"M0/M4/M5 pixelwise identities: {identities}")
    print("final files:")
    for path in target_output_paths(output_dir):
        status = "saved" if path.is_file() else "not generated"
        print(f"  {path.resolve()} [{status}]")
    issue_list = tuple(issues)
    print("data issues: " + ("none" if not issue_list else "; ".join(issue_list)))


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--results-root", type=Path, default=Path("results/articlev2"))
    parser.add_argument("--output-dir", type=Path)
    parser.add_argument("--slab-grid-root", type=Path)
    parser.add_argument("--resample-seed", type=int, default=DEFAULT_RESAMPLE_SEED)
    parser.add_argument("--overwrite", action="store_true")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    results_root = args.results_root.resolve()
    output_dir = (args.output_dir or results_root / "postprocessing" / "E3").resolve()
    slab_root = args.slab_grid_root.resolve() if args.slab_grid_root is not None else None
    protected = {
        results_root,
        (results_root / "events").resolve(),
        (results_root / "events" / "raw").resolve(),
        (results_root / "events" / "valid").resolve(),
    }
    if output_dir in protected:
        raise ValueError("E3 output directory must not replace event data or results root")
    output_dir.parent.mkdir(parents=True, exist_ok=True)
    staging: Path | None = None
    try:
        preflight(results_root, slab_root)
        staging = Path(tempfile.mkdtemp(prefix=f".{output_dir.name}.staging-", dir=output_dir.parent))
        summary = run_analysis(
            results_root,
            slab_root,
            staging,
            resample_seed=args.resample_seed,
        )
        publish(staging, output_dir, args.overwrite)
        staging = None
    except E3PreflightError as error:
        print_report(
            results_root=results_root,
            slab_root=slab_root,
            output_dir=output_dir,
            complete=False,
            identities="not run",
            issues=error.issues,
        )
        return 2
    finally:
        if staging is not None:
            shutil.rmtree(staging, ignore_errors=True)
    print_report(
        results_root=results_root,
        slab_root=slab_root,
        output_dir=output_dir,
        complete=True,
        identities="pass",
        issues=(),
    )
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as error:
        print(f"E3 analysis error: {error}", file=sys.stderr)
        raise SystemExit(1) from error
