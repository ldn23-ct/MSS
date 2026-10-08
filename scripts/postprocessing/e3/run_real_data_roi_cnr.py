#!/usr/bin/env python3
"""Locate the measured 5x5 hole array from D and compare frozen-ROI CNR in D/R."""

from __future__ import annotations

import argparse
import hashlib
import json
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
from matplotlib.patches import Circle
from scipy.ndimage import (
    binary_dilation,
    gaussian_filter,
    map_coordinates,
    maximum_filter,
    median_filter,
)
from scipy.optimize import linear_sum_assignment
from scipy.spatial.distance import cdist

from scripts.postprocessing.e3 import run as e3
from scripts.postprocessing.e3 import run_real_data_validation as real


DEFAULT_WINDOW_INDEX = 49
GRID_SIZE = 5
HOLE_COUNT = GRID_SIZE * GRID_SIZE
PEAK_LIMIT = 50
BOUNDARY_FRACTION = 0.75
BAD_PIXEL_MAD_MULTIPLIER = 8.0
PILOT_SMALL_SIGMA = 1.0
FINAL_SMALL_SPACING_FRACTION = 0.10
FINAL_BACKGROUND_SPACING_FRACTION = 0.75
REFINEMENT_RADIUS_FRACTION = 0.25
MAX_LATTICE_ERROR_FRACTION = 0.25
RADIAL_STEP_PX = 0.25
RADIAL_ANGLES = 180
CENTER_BASELINE_FRACTION = 0.075
BACKGROUND_BASELINE_INNER_FRACTION = 0.35
BACKGROUND_BASELINE_OUTER_FRACTION = 0.40
DEFECT_RECOVERY_THRESHOLD = 0.25
BACKGROUND_RECOVERY_THRESHOLD = 0.90
BACKGROUND_OUTER_FRACTION = 0.40
MIN_DEFECT_PIXELS = 5
MIN_BACKGROUND_PIXELS = 8
STD_DDOF = 1

FIGURE_NAMES = (
    "E3_RROI_F1_D_roi_overlay.png",
    "E3_RROI_F2_R_roi_overlay.png",
    "E3_RROI_F3_localization_diagnostics.png",
    "E3_RROI_F4_radial_profiles.png",
    "E3_RROI_F5_cnr_paired.png",
    "E3_RROI_F6_cnr_spatial_maps.png",
    "E3_RROI_F7_roi_sensitivity.png",
)
TABLE_NAMES = (
    "centers.csv",
    "roi_cnr_per_hole.csv",
    "radial_profiles.csv",
    "roi_sensitivity.csv",
    "summary.csv",
)
MASK_NAMES = ("defect_masks.npy", "background_masks.npy", "valid_mask.npy")
ARRAY_NAMES = (
    "D_selected.npy",
    "R_selected.npy",
    "D_smoothed.npy",
    "D_background.npy",
    "D_localization.npy",
)
TOP_LEVEL_NAMES = ("roi_parameters.json", "summary.md", "README.md")

CENTER_COLUMNS = (
    "hole_id",
    "row",
    "column",
    "x",
    "y",
    "lattice_x",
    "lattice_y",
    "center_residual_px",
    "localization_response",
    "quality_flag",
)

PER_HOLE_COLUMNS = (
    "hole_id",
    "row",
    "column",
    "center_x",
    "center_y",
    "r_defect",
    "r_bg_inner",
    "r_bg_outer",
    "n_defect_pixels",
    "n_background_pixels",
    "D_defect_mean",
    "D_background_mean",
    "D_background_std",
    "D_CNR",
    "R_defect_mean",
    "R_background_mean",
    "R_background_std",
    "R_CNR",
    "delta_CNR",
    "center_lattice_error",
    "quality_flag",
)

SENSITIVITY_COLUMNS = (
    "sensitivity_id",
    "varied_parameter",
    "multiplier",
    "r_defect",
    "r_bg_inner",
    "r_bg_outer",
    "defect_pixels_min",
    "defect_pixels_max",
    "background_pixels_min",
    "background_pixels_max",
    "mean_D_CNR",
    "median_D_CNR",
    "mean_R_CNR",
    "median_R_CNR",
    "mean_delta_CNR",
    "median_delta_CNR",
    "improved_hole_count",
    "improved_hole_fraction",
    "finite_hole_count",
)


@dataclass(frozen=True)
class RoiGeometry:
    centers: np.ndarray
    lattice_points: np.ndarray
    lattice_rows: np.ndarray
    lattice_columns: np.ndarray
    lattice_errors: np.ndarray
    localization_responses: np.ndarray
    candidate_points: np.ndarray
    boundary_mask: np.ndarray
    bad_pixel_mask: np.ndarray
    valid_mask: np.ndarray
    smoothed: np.ndarray
    background: np.ndarray
    localization: np.ndarray
    radial_radii: np.ndarray
    radial_profiles: np.ndarray
    radial_mean: np.ndarray
    radial_median: np.ndarray
    recovery_curve: np.ndarray
    nearest_neighbor_distance: float
    row_spacing: float
    column_spacing: float
    sigma_small: float
    sigma_background: float
    r_defect: float
    r_bg_inner: float
    r_bg_outer: float
    defect_masks: np.ndarray
    background_masks: np.ndarray


@dataclass(frozen=True)
class AnalysisResult:
    D: np.ndarray
    R: np.ndarray
    geometry: RoiGeometry
    centers_table: pd.DataFrame
    per_hole: pd.DataFrame
    radial_table: pd.DataFrame
    sensitivity: pd.DataFrame
    summary: pd.DataFrame
    sensitivity_stable: bool
    input_stats: dict[str, dict[str, Any]]
    parameters: dict[str, Any]


def _array_stats(values: np.ndarray) -> dict[str, Any]:
    array = np.asarray(values)
    finite = array[np.isfinite(array)]
    return {
        "shape": list(array.shape),
        "ndim": int(array.ndim),
        "dtype": str(array.dtype),
        "min": float(finite.min()) if finite.size else math.nan,
        "max": float(finite.max()) if finite.size else math.nan,
        "mean": float(finite.mean()) if finite.size else math.nan,
        "median": float(np.median(finite)) if finite.size else math.nan,
        "std_ddof0": float(finite.std(ddof=0)) if finite.size else math.nan,
        "nan_count": int(np.isnan(array).sum()),
        "inf_count": int(np.isinf(array).sum()),
    }


def _print_stats(label: str, values: np.ndarray) -> None:
    stats = _array_stats(values)
    print(
        f"{label}: shape={tuple(stats['shape'])}, ndim={stats['ndim']}, "
        f"dtype={stats['dtype']}, min={stats['min']:.6g}, max={stats['max']:.6g}, "
        f"mean={stats['mean']:.6g}, median={stats['median']:.6g}, "
        f"std={stats['std_ddof0']:.6g}, NaN={stats['nan_count']}, Inf={stats['inf_count']}"
    )


def load_selected_images(input_dir: Path, window_index: int) -> tuple[np.ndarray, np.ndarray, dict[str, Any]]:
    if window_index < 0:
        raise ValueError("window index must be non-negative")
    paths = {
        "D_volume": input_dir / real.ARRAY_NAMES[0],
        "R_volume": input_dir / real.ARRAY_NAMES[2],
    }
    volumes: dict[str, np.ndarray] = {}
    stats: dict[str, Any] = {}
    for label, path in paths.items():
        if not path.is_file():
            raise FileNotFoundError(f"ROI/CNR input is missing: {path}")
        values = np.load(path, allow_pickle=False)
        _print_stats(label, values)
        if values.ndim != 3 or not np.issubdtype(values.dtype, np.floating):
            raise ValueError(f"{label} must be a three-dimensional floating-point array")
        if not np.isfinite(values).all():
            raise ValueError(f"{label} must not contain NaN or Inf")
        if window_index >= values.shape[0]:
            raise ValueError(f"window index {window_index} is outside {label} shape {values.shape}")
        volumes[label] = np.asarray(values, dtype=np.float64)
        stats[label] = _array_stats(values)
        stats[label]["sha256"] = hashlib.sha256(path.read_bytes()).hexdigest()
        stats[label]["path"] = path.as_posix()
    if volumes["D_volume"].shape != volumes["R_volume"].shape:
        raise ValueError("windowed D and R volumes must have identical shapes")
    D = np.ascontiguousarray(volumes["D_volume"][window_index])
    R = np.ascontiguousarray(volumes["R_volume"][window_index])
    _print_stats("D_selected", D)
    _print_stats("R_selected", R)
    stats["D_selected"] = _array_stats(D)
    stats["R_selected"] = _array_stats(R)
    return D, R, stats


def _longest_true_run(values: np.ndarray) -> tuple[int, int]:
    mask = np.asarray(values, dtype=bool)
    padded = np.r_[False, mask, False].astype(np.int8)
    changes = np.diff(padded)
    starts = np.flatnonzero(changes == 1)
    ends = np.flatnonzero(changes == -1)
    if not len(starts):
        raise ValueError("no valid contiguous image interval was found")
    lengths = ends - starts
    index = int(np.argmax(lengths))
    return int(starts[index]), int(ends[index])


def boundary_mask_from_D(D: np.ndarray) -> tuple[np.ndarray, tuple[int, int, int, int]]:
    values = np.asarray(D, dtype=float)
    positive = values[values > 0]
    if values.ndim != 2 or not positive.size:
        raise ValueError("D must be a non-empty two-dimensional count image")
    baseline = float(np.median(positive))
    row_ok = np.median(values, axis=1) >= BOUNDARY_FRACTION * baseline
    column_ok = np.median(values, axis=0) >= BOUNDARY_FRACTION * baseline
    y0, y1 = _longest_true_run(row_ok)
    x0, x1 = _longest_true_run(column_ok)
    mask = np.zeros(values.shape, dtype=bool)
    mask[y0:y1, x0:x1] = True
    if min(y1 - y0, x1 - x0) < 5 * GRID_SIZE:
        raise ValueError("automatically detected valid boundary is too small for a 5x5 array")
    return mask, (y0, y1, x0, x1)


def _odd_size(value: float, minimum: int = 3) -> int:
    size = max(minimum, int(round(value)))
    return size if size % 2 else size + 1


def localization_components(D: np.ndarray, sigma_small: float, sigma_background: float) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    if not (0 < sigma_small < sigma_background):
        raise ValueError("localization sigmas must satisfy 0 < small < background")
    smoothed = gaussian_filter(np.asarray(D, dtype=float), sigma=sigma_small, mode="reflect")
    background = gaussian_filter(np.asarray(D, dtype=float), sigma=sigma_background, mode="reflect")
    if (background <= 0).any() or not np.isfinite(background).all():
        raise ValueError("estimated D background must be finite and positive")
    localization = (background - smoothed) / background
    return smoothed, background, localization


def candidate_peaks(localization: np.ndarray, valid_mask: np.ndarray, footprint: int, limit: int = PEAK_LIMIT) -> tuple[np.ndarray, np.ndarray]:
    values = np.asarray(localization, dtype=float)
    maxima = maximum_filter(values, size=_odd_size(footprint), mode="nearest")
    y, x = np.where(valid_mask & np.isclose(values, maxima, rtol=0.0, atol=1e-14))
    scores = values[y, x]
    order = np.argsort(scores, kind="stable")[::-1][:limit]
    if len(order) < HOLE_COUNT:
        raise ValueError(f"only {len(order)} valid localization peaks were found")
    return np.column_stack((x[order], y[order])).astype(float), scores[order].astype(float)


def _spacing_mode(candidates: np.ndarray, scores: np.ndarray, horizontal: bool) -> float:
    points = np.asarray(candidates[: min(35, len(candidates))], dtype=float)
    weights = np.asarray(scores[: len(points)], dtype=float)
    lengths: list[float] = []
    pair_weights: list[float] = []
    limit = min(np.ptp(points, axis=0)) * 0.25
    low = max(5.0, limit * 0.25)
    high = max(low + 2.0, limit)
    for i in range(len(points)):
        for j in range(i + 1, len(points)):
            dx, dy = points[j] - points[i]
            primary, cross = (abs(dx), abs(dy)) if horizontal else (abs(dy), abs(dx))
            if low <= primary <= high and cross <= math.tan(math.radians(15.0)) * primary:
                lengths.append(float(primary))
                pair_weights.append(float(max(weights[i], 0.0) + max(weights[j], 0.0)))
    if not lengths:
        raise ValueError("could not estimate pilot lattice spacing from D-only peaks")
    bins = np.arange(low, high + 0.5, 0.5)
    histogram, edges = np.histogram(lengths, bins=bins, weights=pair_weights)
    index = int(np.argmax(histogram))
    return float((edges[index] + edges[index + 1]) / 2.0)


def _grid_points(origin: np.ndarray, sx: float, sy: float, angle_deg: float) -> np.ndarray:
    angle = math.radians(angle_deg)
    column_vector = np.asarray([sx * math.cos(angle), sx * math.sin(angle)])
    row_vector = np.asarray([-sy * math.sin(angle), sy * math.cos(angle)])
    return np.asarray(
        [origin + row * row_vector + column * column_vector for row in range(GRID_SIZE) for column in range(GRID_SIZE)]
    )


def fit_pilot_lattice(localization: np.ndarray, valid_mask: np.ndarray, candidates: np.ndarray, scores: np.ndarray) -> np.ndarray:
    sx0 = _spacing_mode(candidates, scores, horizontal=True)
    sy0 = _spacing_mode(candidates, scores, horizontal=False)
    sx_values = np.arange(sx0 - 1.0, sx0 + 1.01, 0.25)
    sy_values = np.arange(sy0 - 1.0, sy0 + 1.01, 0.25)
    angles = np.arange(-10.0, 10.01, 1.0)
    best: tuple[int, float, float, np.ndarray] | None = None
    height, width = localization.shape
    top_candidates = candidates[: min(35, len(candidates))]
    for anchor in top_candidates:
        for sx in sx_values:
            for sy in sy_values:
                if sx <= 0 or sy <= 0:
                    continue
                for angle in angles:
                    grid = _grid_points(anchor, float(sx), float(sy), float(angle))
                    if (
                        (grid[:, 0] < 0).any() or (grid[:, 0] > width - 1).any()
                        or (grid[:, 1] < 0).any() or (grid[:, 1] > height - 1).any()
                    ):
                        continue
                    rounded = np.rint(grid).astype(int)
                    if not valid_mask[rounded[:, 1], rounded[:, 0]].all():
                        continue
                    distances = cdist(grid, candidates)
                    nearest = distances.min(axis=1)
                    tolerance = 0.35 * min(sx, sy)
                    matched = int((nearest <= tolerance).sum())
                    response = float(
                        map_coordinates(
                            localization,
                            [grid[:, 1], grid[:, 0]],
                            order=1,
                            mode="nearest",
                        ).sum()
                    )
                    mean_distance = float(nearest[nearest <= tolerance].mean()) if matched else math.inf
                    key = (matched, -mean_distance, response)
                    if best is None or key > best[:3]:
                        best = (*key, grid)
    if best is None or best[0] != HOLE_COUNT:
        matched = 0 if best is None else best[0]
        raise ValueError(f"D-only lattice search matched {matched}/25 holes")
    initial = best[3]
    distances = cdist(initial, candidates)
    rows, columns = linear_sum_assignment(distances)
    assigned = np.empty_like(initial)
    assigned[rows] = candidates[columns]
    tolerance = 0.35 * min(sx0, sy0)
    if (np.linalg.norm(assigned - initial, axis=1) > tolerance).any():
        raise ValueError("pilot lattice candidate assignment exceeded its geometric tolerance")
    return assigned


def _fit_affine_lattice(points: np.ndarray) -> tuple[np.ndarray, np.ndarray, float, float]:
    indices = np.asarray([(row, column) for row in range(GRID_SIZE) for column in range(GRID_SIZE)])
    design = np.column_stack((np.ones(HOLE_COUNT), indices[:, 0], indices[:, 1]))
    beta_x = np.linalg.lstsq(design, points[:, 0], rcond=None)[0]
    beta_y = np.linalg.lstsq(design, points[:, 1], rcond=None)[0]
    predicted = np.column_stack((design @ beta_x, design @ beta_y))
    row_spacing = float(np.linalg.norm([beta_x[1], beta_y[1]]))
    column_spacing = float(np.linalg.norm([beta_x[2], beta_y[2]]))
    return predicted, np.column_stack((beta_x, beta_y)), row_spacing, column_spacing


def _disk(radius: float) -> np.ndarray:
    extent = int(math.ceil(radius))
    y, x = np.indices((2 * extent + 1, 2 * extent + 1)) - extent
    return x * x + y * y <= radius * radius


def _bad_pixel_mask(
    D: np.ndarray,
    boundary_mask: np.ndarray,
    d_nn: float,
    protected_centers: np.ndarray,
) -> np.ndarray:
    size = _odd_size(0.5 * d_nn)
    residual = np.asarray(D, dtype=float) - median_filter(D, size=size, mode="reflect")
    center = float(np.median(residual[boundary_mask]))
    mad = float(np.median(np.abs(residual[boundary_mask] - center)))
    robust_sigma = 1.4826 * mad
    if not math.isfinite(robust_sigma) or robust_sigma <= 0:
        raise ValueError("bad-pixel MAD scale is undefined")
    y_grid, x_grid = np.indices(np.asarray(D).shape)
    protected = np.zeros(np.asarray(D).shape, dtype=bool)
    for x, y in np.asarray(protected_centers, dtype=float):
        protected |= (x_grid - x) ** 2 + (y_grid - y) ** 2 <= (0.35 * d_nn) ** 2
    bad = (
        boundary_mask
        & ~protected
        & (np.abs(residual - center) > BAD_PIXEL_MAD_MULTIPLIER * robust_sigma)
    )
    return binary_dilation(bad, structure=_disk(math.ceil(0.2 * d_nn)))


def _refine_centers(localization: np.ndarray, predicted: np.ndarray, radius: float, valid_mask: np.ndarray) -> np.ndarray:
    y_grid, x_grid = np.indices(localization.shape)
    refined: list[tuple[float, float]] = []
    for index, (x, y) in enumerate(predicted):
        patch = ((x_grid - x) ** 2 + (y_grid - y) ** 2 <= radius**2) & valid_mask
        if int(patch.sum()) < 5:
            raise ValueError(f"center {index + 1} has too few valid refinement pixels")
        values = localization[patch]
        weights = np.maximum(values - np.percentile(values, 10.0), 0.0)
        if not math.isfinite(float(weights.sum())) or math.isclose(float(weights.sum()), 0.0):
            raise ValueError(f"center {index + 1} has zero localization weight")
        refined.append(
            (
                float(np.sum(x_grid[patch] * weights) / weights.sum()),
                float(np.sum(y_grid[patch] * weights) / weights.sum()),
            )
        )
    return np.asarray(refined)


def _display_order(points: np.ndarray) -> np.ndarray:
    order: list[int] = []
    preliminary = np.argsort(points[:, 1])[::-1]
    for group in np.array_split(preliminary, GRID_SIZE):
        order.extend(group[np.argsort(points[group, 0])].tolist())
    return np.asarray(order, dtype=int)


def _first_crossing(radii: np.ndarray, values: np.ndarray, threshold: float) -> float:
    indices = np.flatnonzero(values >= threshold)
    if not len(indices):
        raise ValueError(f"radial recovery curve never reaches q={threshold:g}")
    index = int(indices[0])
    if index == 0:
        return float(radii[0])
    x0, x1 = float(radii[index - 1]), float(radii[index])
    y0, y1 = float(values[index - 1]), float(values[index])
    if math.isclose(y0, y1):
        return x1
    return x0 + (threshold - y0) * (x1 - x0) / (y1 - y0)


def radial_profiles(D: np.ndarray, centers: np.ndarray, d_nn: float) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    radii = np.arange(0.0, 0.5 * d_nn + RADIAL_STEP_PX * 0.5, RADIAL_STEP_PX)
    angles = np.linspace(0.0, 2.0 * math.pi, RADIAL_ANGLES, endpoint=False)
    profiles = np.empty((HOLE_COUNT, len(radii)), dtype=float)
    for index, (x, y) in enumerate(centers):
        for radius_index, radius in enumerate(radii):
            sample_y = y + radius * np.sin(angles)
            sample_x = x + radius * np.cos(angles)
            profiles[index, radius_index] = float(
                map_coordinates(D, [sample_y, sample_x], order=1, mode="nearest").mean()
            )
    mean = profiles.mean(axis=0)
    median = np.median(profiles, axis=0)
    center_values = median[radii <= CENTER_BASELINE_FRACTION * d_nn]
    background_values = median[
        (radii >= BACKGROUND_BASELINE_INNER_FRACTION * d_nn)
        & (radii <= BACKGROUND_BASELINE_OUTER_FRACTION * d_nn)
    ]
    if not center_values.size or not background_values.size:
        raise ValueError("radial profile baselines contain no samples")
    center_level = float(center_values.mean())
    background_level = float(background_values.mean())
    if not background_level > center_level:
        raise ValueError("median radial profile does not recover from a low center to background")
    recovery = (median - center_level) / (background_level - center_level)
    return radii, profiles, mean, recovery


def build_masks(
    shape: tuple[int, int],
    centers: np.ndarray,
    valid_mask: np.ndarray,
    r_defect: float,
    r_bg_inner: float,
    r_bg_outer: float,
) -> tuple[np.ndarray, np.ndarray]:
    if not (0 < r_defect < r_bg_inner < r_bg_outer):
        raise ValueError("ROI radii must satisfy 0 < defect < background inner < outer")
    y_grid, x_grid = np.indices(shape)
    distances = np.sqrt(
        (x_grid[None, :, :] - centers[:, 0, None, None]) ** 2
        + (y_grid[None, :, :] - centers[:, 1, None, None]) ** 2
    )
    nearest = np.argmin(distances, axis=0)
    defect = np.asarray(
        [valid_mask & (distances[index] <= r_defect) for index in range(HOLE_COUNT)]
    )
    background = np.zeros_like(defect)
    for index in range(HOLE_COUNT):
        other = np.arange(HOLE_COUNT) != index
        background[index] = (
            valid_mask
            & (distances[index] > r_bg_inner)
            & (distances[index] < r_bg_outer)
            & (nearest == index)
            & np.all(distances[other] > r_bg_inner, axis=0)
        )
    if np.any(defect & background):
        raise AssertionError("defect and background masks must be disjoint")
    return defect, background


def derive_roi_geometry(D: np.ndarray) -> RoiGeometry:
    values = np.asarray(D, dtype=np.float64)
    if values.ndim != 2 or not np.isfinite(values).all():
        raise ValueError("D-only ROI derivation requires one finite two-dimensional image")
    boundary_mask, boundary = boundary_mask_from_D(values)
    pilot_background_sigma = min(values.shape) / (2.0 * GRID_SIZE)
    _, _, pilot_localization = localization_components(
        values, PILOT_SMALL_SIGMA, pilot_background_sigma
    )
    pilot_candidates, pilot_scores = candidate_peaks(
        pilot_localization,
        boundary_mask,
        footprint=_odd_size(min(values.shape) / (4.0 * GRID_SIZE)),
    )
    assigned = fit_pilot_lattice(
        pilot_localization, boundary_mask, pilot_candidates, pilot_scores
    )
    predicted, _, row_spacing, column_spacing = _fit_affine_lattice(assigned)
    pilot_d_nn = min(row_spacing, column_spacing)
    bad_pixel_mask = _bad_pixel_mask(values, boundary_mask, pilot_d_nn, predicted)
    valid_mask = boundary_mask & ~bad_pixel_mask
    sigma_small = FINAL_SMALL_SPACING_FRACTION * pilot_d_nn
    sigma_background = FINAL_BACKGROUND_SPACING_FRACTION * pilot_d_nn
    smoothed, background, localization = localization_components(
        values, sigma_small, sigma_background
    )
    candidates, _ = candidate_peaks(
        localization, valid_mask, footprint=_odd_size(0.5 * pilot_d_nn)
    )
    refined = _refine_centers(
        localization,
        predicted,
        max(2.0, REFINEMENT_RADIUS_FRACTION * pilot_d_nn),
        valid_mask,
    )
    lattice_points, _, row_spacing, column_spacing = _fit_affine_lattice(refined)
    errors = np.linalg.norm(refined - lattice_points, axis=1)
    pairwise = cdist(refined, refined)
    pairwise[pairwise == 0] = np.inf
    d_nn = float(pairwise.min())
    if not d_nn > 0 or float(errors.max()) > MAX_LATTICE_ERROR_FRACTION * d_nn:
        raise ValueError(
            f"refined lattice error is too large: max={errors.max():.6g}, d_nn={d_nn:.6g}"
        )
    order = _display_order(refined)
    refined = refined[order]
    lattice_points = lattice_points[order]
    errors = errors[order]
    responses = map_coordinates(
        localization,
        [refined[:, 1], refined[:, 0]],
        order=1,
        mode="nearest",
    )
    # origin=lower and top-to-bottom numbering means the first row has the largest y.
    rows = np.repeat(np.arange(1, GRID_SIZE + 1), GRID_SIZE)
    columns = np.tile(np.arange(1, GRID_SIZE + 1), GRID_SIZE)
    radii, profiles, profile_mean, recovery = radial_profiles(values, refined, d_nn)
    profile_median = np.median(profiles, axis=0)
    r_defect = _first_crossing(radii, recovery, DEFECT_RECOVERY_THRESHOLD)
    r_bg_inner = _first_crossing(radii, recovery, BACKGROUND_RECOVERY_THRESHOLD)
    r_bg_outer = BACKGROUND_OUTER_FRACTION * d_nn
    if not r_bg_outer < 0.5 * d_nn:
        raise AssertionError("background outer radius must be below half the nearest-neighbor distance")
    defect_masks, background_masks = build_masks(
        values.shape, refined, valid_mask, r_defect, r_bg_inner, r_bg_outer
    )
    y_grid, x_grid = np.indices(values.shape)
    full_defect_disks = np.asarray(
        [
            (x_grid - x) ** 2 + (y_grid - y) ** 2 <= r_defect**2
            for x, y in refined
        ]
    )
    if np.any(full_defect_disks & ~valid_mask[None, :, :]):
        raise ValueError("one or more complete defect ROIs extend outside valid_mask")
    center_pixels = np.rint(refined).astype(int)
    if not valid_mask[center_pixels[:, 1], center_pixels[:, 0]].all():
        raise ValueError("one or more refined centers lie outside valid_mask")
    if (defect_masks.sum(axis=(1, 2)) < MIN_DEFECT_PIXELS).any():
        raise ValueError("one or more defect masks contain too few pixels")
    if (background_masks.sum(axis=(1, 2)) < MIN_BACKGROUND_PIXELS).any():
        raise ValueError("one or more background masks contain too few pixels")
    print(
        f"valid boundary: y=[{boundary[0]},{boundary[1]}), "
        f"x=[{boundary[2]},{boundary[3]}), excluded bad pixels={int(bad_pixel_mask.sum())}"
    )
    print(
        f"lattice: centers=25, row spacing={row_spacing:.6g}px, "
        f"column spacing={column_spacing:.6g}px, d_nn={d_nn:.6g}px, "
        f"max error={errors.max():.6g}px"
    )
    print(
        f"ROI radii: r_defect={r_defect:.6g}px, "
        f"r_bg_inner={r_bg_inner:.6g}px, r_bg_outer={r_bg_outer:.6g}px"
    )
    return RoiGeometry(
        centers=refined,
        lattice_points=lattice_points,
        lattice_rows=rows,
        lattice_columns=columns,
        lattice_errors=errors,
        localization_responses=np.asarray(responses),
        candidate_points=candidates,
        boundary_mask=boundary_mask,
        bad_pixel_mask=bad_pixel_mask,
        valid_mask=valid_mask,
        smoothed=smoothed,
        background=background,
        localization=localization,
        radial_radii=radii,
        radial_profiles=profiles,
        radial_mean=profile_mean,
        radial_median=profile_median,
        recovery_curve=recovery,
        nearest_neighbor_distance=d_nn,
        row_spacing=row_spacing,
        column_spacing=column_spacing,
        sigma_small=sigma_small,
        sigma_background=sigma_background,
        r_defect=r_defect,
        r_bg_inner=r_bg_inner,
        r_bg_outer=r_bg_outer,
        defect_masks=defect_masks,
        background_masks=background_masks,
    )


def _quality_flags(geometry: RoiGeometry, index: int, n_defect: int, n_background: int, stds: Iterable[float]) -> str:
    flags: list[str] = []
    if geometry.lattice_errors[index] > MAX_LATTICE_ERROR_FRACTION * geometry.nearest_neighbor_distance:
        flags.append("large_lattice_error")
    if n_defect < MIN_DEFECT_PIXELS:
        flags.append("few_defect_pixels")
    if n_background < MIN_BACKGROUND_PIXELS:
        flags.append("few_background_pixels")
    if any(not math.isfinite(value) or value <= 0 for value in stds):
        flags.append("nonpositive_background_std")
    return "ok" if not flags else ";".join(flags)


def evaluate_cnr(
    D: np.ndarray,
    R: np.ndarray,
    geometry: RoiGeometry,
    *,
    defect_masks: np.ndarray | None = None,
    background_masks: np.ndarray | None = None,
) -> pd.DataFrame:
    left = np.asarray(D, dtype=np.float64)
    right = np.asarray(R, dtype=np.float64)
    if left.shape != right.shape or left.shape != geometry.valid_mask.shape:
        raise ValueError("D, R, and frozen ROI masks must have the same two-dimensional shape")
    d_masks = geometry.defect_masks if defect_masks is None else np.asarray(defect_masks, dtype=bool)
    b_masks = geometry.background_masks if background_masks is None else np.asarray(background_masks, dtype=bool)
    if d_masks.shape != (HOLE_COUNT, *left.shape) or b_masks.shape != d_masks.shape:
        raise ValueError("frozen ROI masks must have shape (25,H,W)")
    rows: list[dict[str, Any]] = []
    for index in range(HOLE_COUNT):
        d_mask, b_mask = d_masks[index], b_masks[index]
        n_defect, n_background = int(d_mask.sum()), int(b_mask.sum())
        metrics: dict[str, float] = {}
        stds: list[float] = []
        for label, image in (("D", left), ("R", right)):
            defect_mean = float(image[d_mask].mean()) if n_defect else math.nan
            background_mean = float(image[b_mask].mean()) if n_background else math.nan
            background_std = (
                float(image[b_mask].std(ddof=STD_DDOF))
                if n_background > STD_DDOF
                else math.nan
            )
            cnr = (
                (background_mean - defect_mean) / background_std
                if math.isfinite(background_std) and background_std > 0
                else math.nan
            )
            metrics.update(
                {
                    f"{label}_defect_mean": defect_mean,
                    f"{label}_background_mean": background_mean,
                    f"{label}_background_std": background_std,
                    f"{label}_CNR": cnr,
                }
            )
            stds.append(background_std)
        quality = _quality_flags(geometry, index, n_defect, n_background, stds)
        rows.append(
            {
                "hole_id": index + 1,
                "row": int(geometry.lattice_rows[index]),
                "column": int(geometry.lattice_columns[index]),
                "center_x": float(geometry.centers[index, 0]),
                "center_y": float(geometry.centers[index, 1]),
                "r_defect": geometry.r_defect,
                "r_bg_inner": geometry.r_bg_inner,
                "r_bg_outer": geometry.r_bg_outer,
                "n_defect_pixels": n_defect,
                "n_background_pixels": n_background,
                **metrics,
                "delta_CNR": metrics["R_CNR"] - metrics["D_CNR"],
                "center_lattice_error": float(geometry.lattice_errors[index]),
                "quality_flag": quality,
            }
        )
    return pd.DataFrame(rows, columns=PER_HOLE_COLUMNS)


def build_centers_table(geometry: RoiGeometry, per_hole: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for index in range(HOLE_COUNT):
        rows.append(
            {
                "hole_id": index + 1,
                "row": int(geometry.lattice_rows[index]),
                "column": int(geometry.lattice_columns[index]),
                "x": float(geometry.centers[index, 0]),
                "y": float(geometry.centers[index, 1]),
                "lattice_x": float(geometry.lattice_points[index, 0]),
                "lattice_y": float(geometry.lattice_points[index, 1]),
                "center_residual_px": float(geometry.lattice_errors[index]),
                "localization_response": float(geometry.localization_responses[index]),
                "quality_flag": str(per_hole.iloc[index].quality_flag),
            }
        )
    return pd.DataFrame(rows, columns=CENTER_COLUMNS)


def build_radial_table(geometry: RoiGeometry) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    for radius_index, radius in enumerate(geometry.radial_radii):
        for hole_index in range(HOLE_COUNT):
            rows.append(
                {
                    "radius_px": float(radius),
                    "hole_id": hole_index + 1,
                    "D_radial_mean": float(geometry.radial_profiles[hole_index, radius_index]),
                    "group_mean": float(geometry.radial_mean[radius_index]),
                    "group_median": float(geometry.radial_median[radius_index]),
                    "recovery_q": float(geometry.recovery_curve[radius_index]),
                }
            )
    return pd.DataFrame(rows)


def _summary_values(values: pd.Series) -> dict[str, float]:
    finite = values.to_numpy(dtype=float)
    finite = finite[np.isfinite(finite)]
    if not len(finite):
        return {key: math.nan for key in ("mean", "median", "std", "min", "max")}
    return {
        "mean": float(finite.mean()),
        "median": float(np.median(finite)),
        "std": float(finite.std(ddof=1)) if len(finite) > 1 else math.nan,
        "min": float(finite.min()),
        "max": float(finite.max()),
    }


def sensitivity_analysis(D: np.ndarray, R: np.ndarray, geometry: RoiGeometry) -> tuple[pd.DataFrame, bool]:
    configurations: list[tuple[str, float, float, float, float]] = []
    for multiplier in (0.8, 0.9, 1.0, 1.1, 1.2):
        configurations.append(
            ("r_defect", multiplier, geometry.r_defect * multiplier, geometry.r_bg_inner, geometry.r_bg_outer)
        )
    for multiplier in (0.9, 1.1):
        configurations.append(
            ("r_bg_inner", multiplier, geometry.r_defect, geometry.r_bg_inner * multiplier, geometry.r_bg_outer)
        )
    for multiplier in (0.9, 1.1):
        configurations.append(
            ("r_bg_outer", multiplier, geometry.r_defect, geometry.r_bg_inner, geometry.r_bg_outer * multiplier)
        )
    rows: list[dict[str, Any]] = []
    for index, (parameter, multiplier, r_defect, r_inner, r_outer) in enumerate(configurations, start=1):
        if not r_outer < 0.5 * geometry.nearest_neighbor_distance:
            raise ValueError("sensitivity background outer radius violates the half-spacing limit")
        d_masks, b_masks = build_masks(
            D.shape, geometry.centers, geometry.valid_mask, r_defect, r_inner, r_outer
        )
        if (d_masks.sum(axis=(1, 2)) <= STD_DDOF).any() or (
            b_masks.sum(axis=(1, 2)) <= STD_DDOF
        ).any():
            raise ValueError(
                f"sensitivity configuration {index} lacks enough pixels for ddof={STD_DDOF}"
            )
        values = evaluate_cnr(D, R, geometry, defect_masks=d_masks, background_masks=b_masks)
        d_stats = _summary_values(values.D_CNR)
        r_stats = _summary_values(values.R_CNR)
        delta_stats = _summary_values(values.delta_CNR)
        finite = np.isfinite(values.D_CNR) & np.isfinite(values.R_CNR)
        improved = int((values.loc[finite, "R_CNR"] > values.loc[finite, "D_CNR"]).sum())
        rows.append(
            {
                "sensitivity_id": index,
                "varied_parameter": parameter,
                "multiplier": multiplier,
                "r_defect": r_defect,
                "r_bg_inner": r_inner,
                "r_bg_outer": r_outer,
                "defect_pixels_min": int(d_masks.sum(axis=(1, 2)).min()),
                "defect_pixels_max": int(d_masks.sum(axis=(1, 2)).max()),
                "background_pixels_min": int(b_masks.sum(axis=(1, 2)).min()),
                "background_pixels_max": int(b_masks.sum(axis=(1, 2)).max()),
                "mean_D_CNR": d_stats["mean"],
                "median_D_CNR": d_stats["median"],
                "mean_R_CNR": r_stats["mean"],
                "median_R_CNR": r_stats["median"],
                "mean_delta_CNR": delta_stats["mean"],
                "median_delta_CNR": delta_stats["median"],
                "improved_hole_count": improved,
                "improved_hole_fraction": improved / int(finite.sum()) if finite.any() else math.nan,
                "finite_hole_count": int(finite.sum()),
            }
        )
    frame = pd.DataFrame(rows, columns=SENSITIVITY_COLUMNS)
    nominal = frame[(frame.varied_parameter == "r_defect") & np.isclose(frame.multiplier, 1.0)].iloc[0]
    mean_sign = np.sign(float(nominal.mean_delta_CNR))
    median_sign = np.sign(float(nominal.median_delta_CNR))
    sign_stable = bool(
        (np.sign(frame.mean_delta_CNR.to_numpy(dtype=float)) == mean_sign).all()
        and (np.sign(frame.median_delta_CNR.to_numpy(dtype=float)) == median_sign).all()
    )
    fraction_range = float(frame.improved_hole_fraction.max() - frame.improved_hole_fraction.min())
    return frame, bool(sign_stable and fraction_range <= 0.20 + 1e-12)


def build_summary(
    window_index: int,
    geometry: RoiGeometry,
    per_hole: pd.DataFrame,
    sensitivity: pd.DataFrame,
    sensitivity_stable: bool,
) -> pd.DataFrame:
    data: dict[str, Any] = {
        "window_index": window_index,
        "z_start_mm": float(window_index),
        "z_end_mm": float(window_index + real.WINDOW_WIDTH),
        "z_center_mm": float(window_index + real.WINDOW_WIDTH / 2.0),
        "hole_count": HOLE_COUNT,
        "row_spacing_px": geometry.row_spacing,
        "column_spacing_px": geometry.column_spacing,
        "nearest_neighbor_distance_px": geometry.nearest_neighbor_distance,
        "lattice_error_mean_px": float(geometry.lattice_errors.mean()),
        "lattice_error_median_px": float(np.median(geometry.lattice_errors)),
        "lattice_error_max_px": float(geometry.lattice_errors.max()),
        "r_defect": geometry.r_defect,
        "r_bg_inner": geometry.r_bg_inner,
        "r_bg_outer": geometry.r_bg_outer,
        "defect_pixels_min": int(per_hole.n_defect_pixels.min()),
        "defect_pixels_max": int(per_hole.n_defect_pixels.max()),
        "background_pixels_min": int(per_hole.n_background_pixels.min()),
        "background_pixels_max": int(per_hole.n_background_pixels.max()),
    }
    for prefix, column in (("D_CNR", "D_CNR"), ("R_CNR", "R_CNR"), ("delta_CNR", "delta_CNR")):
        for statistic, value in _summary_values(per_hole[column]).items():
            data[f"{prefix}_{statistic}"] = value
    improved = int((per_hole.R_CNR > per_hole.D_CNR).sum())
    nominal_sensitivity = sensitivity[
        (sensitivity.varied_parameter == "r_defect")
        & np.isclose(sensitivity.multiplier, 1.0)
    ].iloc[0]
    sensitivity_sign_stable = bool(
        (
            np.sign(sensitivity.mean_delta_CNR.to_numpy(dtype=float))
            == np.sign(float(nominal_sensitivity.mean_delta_CNR))
        ).all()
        and (
            np.sign(sensitivity.median_delta_CNR.to_numpy(dtype=float))
            == np.sign(float(nominal_sensitivity.median_delta_CNR))
        ).all()
    )
    sensitivity_fraction_range = float(
        sensitivity.improved_hole_fraction.max()
        - sensitivity.improved_hole_fraction.min()
    )
    data.update(
        {
            "R_CNR_gt_D_CNR_count": improved,
            "R_CNR_le_D_CNR_count": HOLE_COUNT - improved,
            "quality_flagged_hole_count": int(per_hole.quality_flag.ne("ok").sum()),
            "sensitivity_configuration_count": len(sensitivity),
            "sensitivity_stable": sensitivity_stable,
            "sensitivity_delta_sign_stable": sensitivity_sign_stable,
            "sensitivity_improved_fraction_range": sensitivity_fraction_range,
            "sensitivity_improved_fraction_min": float(sensitivity.improved_hole_fraction.min()),
            "sensitivity_improved_fraction_max": float(sensitivity.improved_hole_fraction.max()),
        }
    )
    return pd.DataFrame([data])


def analyze(D: np.ndarray, R: np.ndarray, window_index: int, input_stats: dict[str, Any]) -> AnalysisResult:
    # Stage A is intentionally called before R is passed to any ROI-related function.
    geometry = derive_roi_geometry(D)
    per_hole = evaluate_cnr(D, R, geometry)
    if not np.isfinite(per_hole[["D_CNR", "R_CNR", "delta_CNR"]].to_numpy(dtype=float)).all():
        raise ValueError("actual D/R analysis requires finite CNR for all 25 holes")
    centers = build_centers_table(geometry, per_hole)
    radial = build_radial_table(geometry)
    sensitivity, stable = sensitivity_analysis(D, R, geometry)
    summary = build_summary(window_index, geometry, per_hole, sensitivity, stable)
    parameters = {
        "schema_version": 1,
        "window": {
            "index": window_index,
            "start_mm": float(window_index),
            "end_mm": float(window_index + real.WINDOW_WIDTH),
            "center_mm": float(window_index + real.WINDOW_WIDTH / 2.0),
        },
        "phase_separation": "ROI geometry derived from D only; frozen masks then applied unchanged to D and R",
        "valid_mask": {
            "boundary_fraction": BOUNDARY_FRACTION,
            "median_filter_width_fraction_d_nn": 0.5,
            "bad_pixel_mad_multiplier": BAD_PIXEL_MAD_MULTIPLIER,
            "bad_pixel_dilation_radius": "ceil(0.2*d_nn)",
            "protected_hole_radius_fraction_d_nn": 0.35,
        },
        "localization": {
            "formula": "(B-D_s)/B",
            "grid_shape": [GRID_SIZE, GRID_SIZE],
            "pilot_sigma_small_px": PILOT_SMALL_SIGMA,
            "pilot_sigma_background_formula": "min(image_shape)/(2*grid_size)",
            "pilot_angle_range_deg": [-10.0, 10.0],
            "pilot_angle_step_deg": 1.0,
            "pilot_spacing_half_range_px": 1.0,
            "pilot_spacing_step_px": 0.25,
            "pilot_match_tolerance_fraction_spacing": 0.35,
            "sigma_small_px": geometry.sigma_small,
            "sigma_background_px": geometry.sigma_background,
            "sigma_small_fraction_d_nn": FINAL_SMALL_SPACING_FRACTION,
            "sigma_background_fraction_d_nn": FINAL_BACKGROUND_SPACING_FRACTION,
            "candidate_limit": PEAK_LIMIT,
            "refinement_radius_fraction_d_nn": REFINEMENT_RADIUS_FRACTION,
            "max_lattice_error_fraction_d_nn": MAX_LATTICE_ERROR_FRACTION,
        },
        "radial_profile": {
            "step_px": RADIAL_STEP_PX,
            "angular_samples": RADIAL_ANGLES,
            "center_baseline_fraction_d_nn": CENTER_BASELINE_FRACTION,
            "background_baseline_fraction_d_nn": [
                BACKGROUND_BASELINE_INNER_FRACTION,
                BACKGROUND_BASELINE_OUTER_FRACTION,
            ],
            "defect_q_threshold": DEFECT_RECOVERY_THRESHOLD,
            "background_q_threshold": BACKGROUND_RECOVERY_THRESHOLD,
            "background_outer_fraction_d_nn": BACKGROUND_OUTER_FRACTION,
        },
        "cnr": {
            "formula": "(mu_background-mu_defect)/sigma_background",
            "absolute_value": False,
            "std_ddof": STD_DDOF,
        },
        "masks": {
            "voronoi_constrained": True,
            "exclude_other_holes_through_r_bg_inner": True,
            "minimum_nominal_defect_pixels": MIN_DEFECT_PIXELS,
            "minimum_nominal_background_pixels": MIN_BACKGROUND_PIXELS,
        },
        "sensitivity": {
            "design": "one-factor-at-a-time",
            "r_defect_multipliers": [0.8, 0.9, 1.0, 1.1, 1.2],
            "r_bg_inner_multipliers": [0.9, 1.0, 1.1],
            "r_bg_outer_multipliers": [0.9, 1.0, 1.1],
            "stability_rule": "mean and median delta signs preserved; improved-hole fraction range <= 0.20",
        },
        "inputs": input_stats,
    }
    return AnalysisResult(
        D=np.asarray(D),
        R=np.asarray(R),
        geometry=geometry,
        centers_table=centers,
        per_hole=per_hole,
        radial_table=radial,
        sensitivity=sensitivity,
        summary=summary,
        sensitivity_stable=stable,
        input_stats=input_stats,
        parameters=parameters,
    )


def _overlay_plot(image: np.ndarray, geometry: RoiGeometry, title: str, output: Path, cmap: str) -> None:
    fig, axis = plt.subplots(figsize=(8.4, 7.4), constrained_layout=True)
    view = axis.imshow(image, origin="lower", cmap=cmap, aspect="equal")
    axis.contour(geometry.valid_mask.astype(float), levels=[0.5], colors="white", linewidths=0.7, origin="lower")
    for index, (x, y) in enumerate(geometry.centers):
        axis.add_patch(Circle((x, y), geometry.r_defect, fill=False, color="#00FFFF", lw=1.0))
        axis.add_patch(Circle((x, y), geometry.r_bg_inner, fill=False, color="#FFFFFF", lw=0.7, ls="--"))
        axis.add_patch(Circle((x, y), geometry.r_bg_outer, fill=False, color="#FF00FF", lw=0.8))
        axis.text(x, y + geometry.r_bg_outer + 0.8, str(index + 1), color="black", fontsize=6, ha="center",
                  bbox={"facecolor": "white", "alpha": 0.65, "edgecolor": "none", "pad": 0.5})
    axis.set(xlabel="x pixel index", ylabel="y pixel index", title=title)
    fig.colorbar(view, ax=axis, shrink=0.82, label="Raw three-slice count")
    e3._save_png(fig, output)


def plot_localization(result: AnalysisResult, output: Path) -> None:
    g = result.geometry
    fig, axes = plt.subplots(2, 3, figsize=(14.0, 9.0), constrained_layout=True)
    panels = (
        (result.D, "(a) Raw D", "viridis"),
        (g.smoothed, "(b) Small-scale smoothed D", "viridis"),
        (g.background, "(c) Estimated background B", "viridis"),
        (g.localization, "(d) Localization L=(B−D_s)/B", "magma"),
        (g.valid_mask.astype(float), "(e) valid_mask", "gray"),
        (g.localization, "(f) Candidates, lattice, refined centers", "magma"),
    )
    for axis, (image, title, cmap) in zip(axes.flat, panels, strict=True):
        view = axis.imshow(image, origin="lower", cmap=cmap, aspect="equal")
        axis.set(title=title, xlabel="x", ylabel="y")
        fig.colorbar(view, ax=axis, shrink=0.72)
    axes[1, 1].imshow(g.bad_pixel_mask, origin="lower", cmap="Reds", alpha=0.65)
    axes[1, 2].scatter(g.candidate_points[:, 0], g.candidate_points[:, 1], s=14, facecolors="none",
                       edgecolors="#00FFFF", linewidths=0.6, label="candidate")
    axes[1, 2].scatter(g.lattice_points[:, 0], g.lattice_points[:, 1], marker="+", color="white",
                       s=36, label="lattice")
    axes[1, 2].scatter(g.centers[:, 0], g.centers[:, 1], marker="x", color="#00FF00",
                       s=28, label="refined")
    axes[1, 2].legend(fontsize=7)
    fig.suptitle("D-only valid-region and 5×5 lattice localization diagnostics")
    e3._save_png(fig, output)


def plot_radial_profiles(geometry: RoiGeometry, output: Path) -> None:
    fig, axes = plt.subplots(1, 2, figsize=(13.0, 5.4), constrained_layout=True)
    for profile in geometry.radial_profiles:
        axes[0].plot(geometry.radial_radii, profile, color="#999999", alpha=0.35, lw=0.7)
    axes[0].plot(geometry.radial_radii, geometry.radial_mean, color="#0072B2", lw=2.0, label="mean")
    axes[0].plot(geometry.radial_radii, geometry.radial_median, color="#D55E00", lw=2.0, label="median")
    axes[1].plot(geometry.radial_radii, geometry.recovery_curve, color="#009E73", lw=2.0)
    axes[1].axhline(DEFECT_RECOVERY_THRESHOLD, color="#555555", ls=":", lw=1.0)
    axes[1].axhline(BACKGROUND_RECOVERY_THRESHOLD, color="#555555", ls=":", lw=1.0)
    for axis in axes:
        axis.axvline(geometry.r_defect, color="#00A6D6", ls="--", label="r_defect")
        axis.axvline(geometry.r_bg_inner, color="#7A7A7A", ls="--", label="r_bg_inner")
        axis.axvline(geometry.r_bg_outer, color="#CC79A7", ls="--", label="r_bg_outer")
        axis.set_xlabel("Radius (pixel)")
        axis.grid(alpha=0.2)
    axes[0].set(ylabel="Interpolated D ring mean", title="(a) 25 D-only radial profiles")
    axes[1].set(ylabel="Normalized recovery q", title="(b) Median-profile recovery")
    axes[0].legend(fontsize=8)
    axes[1].legend(fontsize=8)
    fig.suptitle("Shared measured-hole radial response and frozen ROI radii")
    e3._save_png(fig, output)


def plot_cnr_paired(per_hole: pd.DataFrame, output: Path) -> None:
    fig, axis = plt.subplots(figsize=(11.0, 6.0), constrained_layout=True)
    x = per_hole.hole_id.to_numpy()
    for hole, d_value, r_value in zip(x, per_hole.D_CNR, per_hole.R_CNR, strict=True):
        axis.plot([hole, hole], [d_value, r_value], color="#AAAAAA", lw=0.8)
    axis.scatter(x, per_hole.D_CNR, color="#4D4D4D", label="D CNR", s=28)
    axis.scatter(x, per_hole.R_CNR, color="#D55E00", label="R CNR", s=28)
    axis.axhline(0.0, color="#777777", ls="--", lw=0.8)
    axis.set(xlabel="Hole ID (top-to-bottom, left-to-right)", ylabel="Signed CNR",
             title="Paired CNR with identical frozen ROI masks")
    axis.set_xticks(x)
    axis.grid(axis="y", alpha=0.2)
    axis.legend()
    e3._save_png(fig, output)


def plot_cnr_maps(per_hole: pd.DataFrame, output: Path) -> None:
    images = (
        per_hole.D_CNR.to_numpy().reshape(GRID_SIZE, GRID_SIZE),
        per_hole.R_CNR.to_numpy().reshape(GRID_SIZE, GRID_SIZE),
        per_hole.delta_CNR.to_numpy().reshape(GRID_SIZE, GRID_SIZE),
    )
    titles = ("(a) D CNR", "(b) R CNR", "(c) ΔCNR=R−D")
    fig, axes = plt.subplots(1, 3, figsize=(13.0, 4.5), constrained_layout=True)
    shared_min = min(float(images[0].min()), float(images[1].min()))
    shared_max = max(float(images[0].max()), float(images[1].max()))
    delta_limit = max(float(np.abs(images[2]).max()), np.finfo(float).eps)
    for index, (axis, image, title) in enumerate(zip(axes, images, titles, strict=True)):
        if index < 2:
            view = axis.imshow(image, origin="upper", cmap="viridis", vmin=shared_min, vmax=shared_max)
        else:
            view = axis.imshow(image, origin="upper", cmap="coolwarm", vmin=-delta_limit, vmax=delta_limit)
        for row in range(GRID_SIZE):
            for column in range(GRID_SIZE):
                axis.text(column, row, f"{image[row, column]:.2f}", ha="center", va="center", fontsize=7)
        axis.set(title=title, xlabel="Lattice column", ylabel="Lattice row")
        axis.set_xticks(range(GRID_SIZE), range(1, GRID_SIZE + 1))
        axis.set_yticks(range(GRID_SIZE), range(1, GRID_SIZE + 1))
        fig.colorbar(view, ax=axis, shrink=0.8)
    fig.suptitle("5×5 spatial distribution of signed CNR")
    e3._save_png(fig, output)


def plot_sensitivity(sensitivity: pd.DataFrame, stable: bool, output: Path) -> None:
    x = sensitivity.sensitivity_id.to_numpy()
    labels = [f"{p}\n×{m:g}" for p, m in zip(sensitivity.varied_parameter, sensitivity.multiplier, strict=True)]
    fig, axes = plt.subplots(3, 1, figsize=(11.5, 10.0), sharex=True, constrained_layout=True)
    axes[0].plot(x, sensitivity.mean_D_CNR, marker="o", label="mean D")
    axes[0].plot(x, sensitivity.mean_R_CNR, marker="o", label="mean R")
    axes[0].plot(x, sensitivity.median_D_CNR, marker="s", ls="--", label="median D")
    axes[0].plot(x, sensitivity.median_R_CNR, marker="s", ls="--", label="median R")
    axes[1].plot(x, sensitivity.mean_delta_CNR, marker="o", label="mean ΔCNR")
    axes[1].plot(x, sensitivity.median_delta_CNR, marker="s", label="median ΔCNR")
    axes[1].axhline(0.0, color="#777777", ls="--", lw=0.8)
    axes[2].plot(x, sensitivity.improved_hole_fraction, marker="o", color="#009E73")
    axes[2].set_ylim(-0.02, 1.02)
    axes[0].set(ylabel="Aggregate CNR", title="(a) D/R aggregate CNR")
    axes[1].set(ylabel="ΔCNR", title="(b) Aggregate paired change")
    axes[2].set(ylabel="Fraction R>D", title="(c) Improved-hole fraction", xlabel="One-factor configuration")
    axes[2].set_xticks(x, labels, rotation=30, ha="right")
    for axis in axes:
        axis.grid(alpha=0.2)
    axes[0].legend(fontsize=8, ncol=2)
    axes[1].legend(fontsize=8)
    fig.suptitle(f"Frozen-geometry ROI sensitivity (stable={str(stable).lower()})")
    e3._save_png(fig, output)


def _summary_markdown(result: AnalysisResult) -> str:
    row = result.summary.iloc[0]
    flagged = result.per_hole[result.per_hole.quality_flag.ne("ok")]
    flags = "none" if flagged.empty else ", ".join(
        f"hole {int(item.hole_id)}: {item.quality_flag}" for item in flagged.itertuples()
    )
    return f"""# E3 measured-hole ROI/CNR summary

- D/R selected shape: `{result.D.shape}`
- Window: index {int(row.window_index)}, `[{row.z_start_mm:g},{row.z_end_mm:g}) mm`, center {row.z_center_mm:g} mm
- Detected centers: {int(row.hole_count)}/25
- Row/column spacing: {row.row_spacing_px:.6f}/{row.column_spacing_px:.6f} px
- Maximum lattice error: {row.lattice_error_max_px:.6f} px
- Frozen radii: r_defect={row.r_defect:.6f}, r_bg_inner={row.r_bg_inner:.6f}, r_bg_outer={row.r_bg_outer:.6f} px
- Defect pixels per hole: {int(row.defect_pixels_min)}–{int(row.defect_pixels_max)}
- Background pixels per hole: {int(row.background_pixels_min)}–{int(row.background_pixels_max)}
- D CNR mean/median/std/min/max: {row.D_CNR_mean:.6f}/{row.D_CNR_median:.6f}/{row.D_CNR_std:.6f}/{row.D_CNR_min:.6f}/{row.D_CNR_max:.6f}
- R CNR mean/median/std/min/max: {row.R_CNR_mean:.6f}/{row.R_CNR_median:.6f}/{row.R_CNR_std:.6f}/{row.R_CNR_min:.6f}/{row.R_CNR_max:.6f}
- Delta CNR mean/median/std/min/max: {row.delta_CNR_mean:.6f}/{row.delta_CNR_median:.6f}/{row.delta_CNR_std:.6f}/{row.delta_CNR_min:.6f}/{row.delta_CNR_max:.6f}
- Holes with R_CNR > D_CNR: {int(row.R_CNR_gt_D_CNR_count)}; R_CNR <= D_CNR: {int(row.R_CNR_le_D_CNR_count)}
- One-factor sensitivity stable: `{str(bool(row.sensitivity_stable)).lower()}`
- Sensitivity delta sign stable: `{str(bool(row.sensitivity_delta_sign_stable)).lower()}`; improved-hole fraction range: {row.sensitivity_improved_fraction_range:.6f}
- Quality flags: {flags}

ROI geometry was determined from D only. R was evaluated only after centers, radii, and masks were frozen. CNR uses raw selected images, the signed formula `(mu_background-mu_defect)/sigma_background`, and `ddof=1`.
"""


def write_outputs(result: AnalysisResult, output_dir: Path) -> None:
    figures = output_dir / "figures"
    tables = output_dir / "tables"
    masks = output_dir / "masks"
    arrays = output_dir / "arrays"
    for path in (figures, tables, masks, arrays):
        path.mkdir(parents=True, exist_ok=True)
    _overlay_plot(result.D, result.geometry, "D with D-only frozen defect/background ROI", figures / FIGURE_NAMES[0], "viridis")
    _overlay_plot(result.R, result.geometry, "R with the identical frozen ROI", figures / FIGURE_NAMES[1], "coolwarm")
    plot_localization(result, figures / FIGURE_NAMES[2])
    plot_radial_profiles(result.geometry, figures / FIGURE_NAMES[3])
    plot_cnr_paired(result.per_hole, figures / FIGURE_NAMES[4])
    plot_cnr_maps(result.per_hole, figures / FIGURE_NAMES[5])
    plot_sensitivity(result.sensitivity, result.sensitivity_stable, figures / FIGURE_NAMES[6])
    frames = (
        result.centers_table,
        result.per_hole,
        result.radial_table,
        result.sensitivity,
        result.summary,
    )
    for name, frame in zip(TABLE_NAMES, frames, strict=True):
        frame.to_csv(tables / name, index=False)
    for name, values in zip(
        MASK_NAMES,
        (result.geometry.defect_masks, result.geometry.background_masks, result.geometry.valid_mask),
        strict=True,
    ):
        np.save(masks / name, np.asarray(values, dtype=bool), allow_pickle=False)
    for name, values in zip(
        ARRAY_NAMES,
        (result.D, result.R, result.geometry.smoothed, result.geometry.background, result.geometry.localization),
        strict=True,
    ):
        np.save(arrays / name, np.asarray(values, dtype=np.float64), allow_pickle=False)
    (output_dir / TOP_LEVEL_NAMES[0]).write_text(
        json.dumps(result.parameters, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    (output_dir / TOP_LEVEL_NAMES[1]).write_text(_summary_markdown(result), encoding="utf-8")
    (output_dir / TOP_LEVEL_NAMES[2]).write_text(
        "# Reproducible measured-hole ROI/CNR outputs\n\n"
        "Generated by `python -m scripts.postprocessing.e3.run_real_data_roi_cnr`. "
        "ROI geometry is derived from D only; the saved masks are then applied unchanged to D and R.\n\n"
        "- `figures/`: seven 300 dpi diagnostic and result plots.\n"
        "- `tables/`: centers, per-hole CNR, radial profiles, nine sensitivity configurations, and summary.\n"
        "- `masks/`: the 25 frozen defect/background masks and shared valid mask.\n"
        "- `arrays/`: selected raw D/R plus the three D-only localization arrays.\n"
        "- `roi_parameters.json`: input hashes, window mapping, and fixed algorithm parameters.\n"
        "- `summary.md`: compact numerical findings and quality status.\n\n"
        "CNR is evaluated on the saved raw `D_selected.npy` and `R_selected.npy`, not on the "
        "smoothed or normalized localization arrays. Reproduce the default analysis with:\n\n"
        "```bash\n"
        "conda run -n data python -m scripts.postprocessing.e3.run_real_data_roi_cnr --overwrite\n"
        "```\n",
        encoding="utf-8",
    )
    validate_outputs(output_dir)


def validate_outputs(output_dir: Path) -> None:
    expected_dirs = {"figures", "tables", "masks", "arrays"}
    actual_dirs = {path.name for path in output_dir.iterdir() if path.is_dir()}
    actual_files = {path.name for path in output_dir.iterdir() if path.is_file()}
    if actual_dirs != expected_dirs or actual_files != set(TOP_LEVEL_NAMES):
        raise AssertionError("ROI/CNR top-level output contract failed")
    contracts = {
        "figures": set(FIGURE_NAMES),
        "tables": set(TABLE_NAMES),
        "masks": set(MASK_NAMES),
        "arrays": set(ARRAY_NAMES),
    }
    for directory, expected in contracts.items():
        actual = {path.name for path in (output_dir / directory).iterdir() if path.is_file()}
        if actual != expected or any(path.is_dir() for path in (output_dir / directory).iterdir()):
            raise AssertionError(f"ROI/CNR {directory} output contract failed")
    centers = pd.read_csv(output_dir / "tables" / TABLE_NAMES[0])
    per_hole = pd.read_csv(output_dir / "tables" / TABLE_NAMES[1])
    sensitivity = pd.read_csv(output_dir / "tables" / TABLE_NAMES[3])
    summary = pd.read_csv(output_dir / "tables" / TABLE_NAMES[4])
    if tuple(centers.columns) != CENTER_COLUMNS or len(centers) != HOLE_COUNT:
        raise AssertionError("centers table contract failed")
    if tuple(per_hole.columns) != PER_HOLE_COLUMNS or len(per_hole) != HOLE_COUNT:
        raise AssertionError("per-hole CNR table contract failed")
    if tuple(sensitivity.columns) != SENSITIVITY_COLUMNS or len(sensitivity) != 9:
        raise AssertionError("ROI sensitivity table contract failed")
    if len(summary) != 1 or int(summary.iloc[0].hole_count) != HOLE_COUNT:
        raise AssertionError("ROI/CNR summary table contract failed")
    defect_masks = np.load(output_dir / "masks" / MASK_NAMES[0], allow_pickle=False)
    background_masks = np.load(output_dir / "masks" / MASK_NAMES[1], allow_pickle=False)
    valid_mask = np.load(output_dir / "masks" / MASK_NAMES[2], allow_pickle=False)
    if defect_masks.shape != (HOLE_COUNT, 103, 101) or background_masks.shape != defect_masks.shape:
        raise AssertionError("saved ROI mask shape contract failed")
    if valid_mask.shape != (103, 101) or any(x.dtype != np.bool_ for x in (defect_masks, background_masks, valid_mask)):
        raise AssertionError("saved valid/ROI mask dtype contract failed")
    if np.any(defect_masks & background_masks):
        raise AssertionError("saved defect/background masks overlap")
    D = np.load(output_dir / "arrays" / ARRAY_NAMES[0], allow_pickle=False)
    R = np.load(output_dir / "arrays" / ARRAY_NAMES[1], allow_pickle=False)
    if D.shape != (103, 101) or R.shape != D.shape:
        raise AssertionError("saved selected D/R shape contract failed")
    parameters = json.loads((output_dir / TOP_LEVEL_NAMES[0]).read_text(encoding="utf-8"))
    if parameters["cnr"] != {
        "absolute_value": False,
        "formula": "(mu_background-mu_defect)/sigma_background",
        "std_ddof": 1,
    }:
        raise AssertionError("saved CNR parameter contract failed")
    for name in FIGURE_NAMES:
        if (output_dir / "figures" / name).read_bytes()[:8] != b"\x89PNG\r\n\x1a\n":
            raise AssertionError(f"ROI/CNR figure is not a PNG: {name}")


def publish(staging: Path, output_dir: Path, overwrite: bool) -> None:
    if output_dir.exists():
        if not overwrite:
            raise FileExistsError(f"ROI/CNR output exists; pass --overwrite: {output_dir}")
        backup = output_dir.parent / f".{output_dir.name}.backup"
        if backup.exists():
            raise FileExistsError(f"stale ROI/CNR backup blocks overwrite: {backup}")
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


def run_analysis(input_dir: Path, output_dir: Path, window_index: int) -> AnalysisResult:
    D, R, input_stats = load_selected_images(input_dir, window_index)
    result = analyze(D, R, window_index, input_stats)
    write_outputs(result, output_dir)
    return result


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--results-root", type=Path, default=Path("results/articlev3_merged"))
    parser.add_argument(
        "--input-dir",
        type=Path,
        help="Direct windowed-NPY directory override; otherwise derived from --results-root.",
    )
    parser.add_argument("--window-index", type=int, default=DEFAULT_WINDOW_INDEX)
    parser.add_argument("--output-dir", type=Path)
    parser.add_argument("--overwrite", action="store_true")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    input_dir = (
        args.input_dir.resolve()
        if args.input_dir is not None
        else (
            args.results_root.resolve()
            / "postprocessing"
            / "E3"
            / "supplementary"
            / "real_data_front_validation"
        )
    )
    output_dir = (
        args.output_dir.resolve()
        if args.output_dir is not None
        else input_dir / real.ROI_CNR_SUBDIRECTORY
    )
    if output_dir == input_dir or input_dir in output_dir.parents and output_dir.name != real.ROI_CNR_SUBDIRECTORY:
        raise ValueError("ROI/CNR output must be the owned roi_cnr_analysis subdirectory or an independent path")
    output_dir.parent.mkdir(parents=True, exist_ok=True)
    staging = Path(tempfile.mkdtemp(prefix=f".{output_dir.name}.staging-", dir=output_dir.parent))
    try:
        result = run_analysis(input_dir, staging, args.window_index)
        publish(staging, output_dir, args.overwrite)
    except Exception:
        shutil.rmtree(staging, ignore_errors=True)
        raise
    row = result.summary.iloc[0]
    print(f"ROI/CNR output: {output_dir}")
    print(
        f"D/R shape={result.D.shape}, centers={int(row.hole_count)}, "
        f"spacing(row/column)={row.row_spacing_px:.6g}/{row.column_spacing_px:.6g}px, "
        f"max lattice error={row.lattice_error_max_px:.6g}px"
    )
    print(
        f"D CNR mean/median={row.D_CNR_mean:.6g}/{row.D_CNR_median:.6g}; "
        f"R CNR mean/median={row.R_CNR_mean:.6g}/{row.R_CNR_median:.6g}; "
        f"Delta mean/median={row.delta_CNR_mean:.6g}/{row.delta_CNR_median:.6g}"
    )
    print(
        f"R>D holes={int(row.R_CNR_gt_D_CNR_count)}/25; "
        f"sensitivity stable={str(bool(row.sensitivity_stable)).lower()}; "
        f"quality flags={int(row.quality_flagged_hole_count)}"
    )
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as error:
        print(f"real-data ROI/CNR analysis error: {error}", file=sys.stderr)
        raise SystemExit(1) from error
