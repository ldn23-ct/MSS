#!/usr/bin/env python3
"""Reusable detector-x slit-channel boundary estimation and labeling contracts."""

from __future__ import annotations

import csv
import json
import math
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Iterable, Mapping

import numpy as np
from scipy.ndimage import gaussian_filter1d
from scipy.signal import find_peaks

from .common import PROFILE_SLITS, RunMetadata, load_run_metadata


SCHEMA_VERSION = 1
ALGORITHM_VERSION = "slit_channel_boundaries_v1"
PROFILE_BOUNDARY_KEYS = {
    "P001": ("S2_S4", "S4_S6"),
    "P002": ("S1_S3", "S3_S5"),
}


@dataclass(frozen=True)
class BoundaryAlgorithmConfig:
    histogram_bin_width_mm: float = 0.25
    smoothing_sigma_mm: float = 1.0
    minimum_peak_height_fraction: float = 0.05
    minimum_peak_prominence_fraction: float = 0.05
    minimum_peak_distance_mm: float = 10.0
    valley_plateau_tolerance_fraction: float = 0.01
    maximum_valley_to_peak_ratio: float = 0.25
    stability_smoothing_factors: tuple[float, ...] = (0.75, 1.0, 1.25)
    stability_bin_origin_offsets: tuple[float, ...] = (-0.5, -0.25, 0.0, 0.25, 0.5)
    maximum_peak_shift_mm: float = 3.0
    maximum_boundary_shift_mm: float = 0.5

    def validate(self) -> None:
        positive = {
            "histogram_bin_width_mm": self.histogram_bin_width_mm,
            "smoothing_sigma_mm": self.smoothing_sigma_mm,
            "minimum_peak_distance_mm": self.minimum_peak_distance_mm,
            "maximum_peak_shift_mm": self.maximum_peak_shift_mm,
            "maximum_boundary_shift_mm": self.maximum_boundary_shift_mm,
        }
        for name, value in positive.items():
            if not math.isfinite(value) or value <= 0:
                raise ValueError(f"{name} must be finite and positive: {value!r}")
        fractions = {
            "minimum_peak_height_fraction": self.minimum_peak_height_fraction,
            "minimum_peak_prominence_fraction": self.minimum_peak_prominence_fraction,
            "valley_plateau_tolerance_fraction": self.valley_plateau_tolerance_fraction,
            "maximum_valley_to_peak_ratio": self.maximum_valley_to_peak_ratio,
        }
        for name, value in fractions.items():
            if not math.isfinite(value) or not 0 < value < 1:
                raise ValueError(f"{name} must be between zero and one: {value!r}")
        if not self.stability_smoothing_factors or not self.stability_bin_origin_offsets:
            raise ValueError("stability factor and bin-origin grids must be non-empty")
        if any(not math.isfinite(value) or value <= 0 for value in self.stability_smoothing_factors):
            raise ValueError("stability smoothing factors must be finite and positive")
        if any(not math.isfinite(value) for value in self.stability_bin_origin_offsets):
            raise ValueError("stability bin-origin offsets must be finite")


@dataclass(frozen=True)
class ValleyResult:
    left_peak_index: int
    right_peak_index: int
    minimum_index: int
    plateau_left_index: int
    plateau_right_index: int
    minimum_density: float
    lower_adjacent_peak_density: float
    valley_to_peak_ratio: float
    boundary_x_mm: float


@dataclass(frozen=True)
class DetectionResult:
    profile_id: str
    bin_origin_offset: float
    smoothing_sigma_mm: float
    bin_edges_mm: np.ndarray
    bin_centers_mm: np.ndarray
    raw_counts: np.ndarray
    smooth_density: np.ndarray
    candidate_peak_indices: np.ndarray
    candidate_peak_prominences: np.ndarray
    valleys: tuple[ValleyResult, ...]

    @property
    def peak_x_mm(self) -> np.ndarray:
        return self.bin_centers_mm[self.candidate_peak_indices]

    @property
    def boundary_x_mm(self) -> np.ndarray:
        return np.asarray([item.boundary_x_mm for item in self.valleys], dtype=float)


@dataclass(frozen=True)
class StabilityResult:
    smoothing_factor: float
    bin_origin_offset: float
    peak_x_mm: tuple[float, ...]
    boundary_x_mm: tuple[float, ...]
    maximum_peak_shift_mm: float
    maximum_boundary_shift_mm: float
    passed: bool
    error: str = ""


@dataclass(frozen=True)
class ProfileBoundaryEstimate:
    profile_id: str
    slit_order: tuple[str, ...]
    detector_x_range_mm: tuple[float, float]
    detected_hit_count: int
    baseline_file: Path
    detection: DetectionResult
    stability: tuple[StabilityResult, ...]


class BoundaryEstimationError(ValueError):
    """Fail-fast estimation error with optional partial detector-x diagnostics."""

    def __init__(self, message: str, profile_id: str, detection: DetectionResult | None = None):
        super().__init__(message)
        self.profile_id = profile_id
        self.detection = detection


def _finite_x(values: Iterable[float], profile_id: str) -> np.ndarray:
    x = np.asarray(list(values) if not isinstance(values, np.ndarray) else values, dtype=float)
    if x.ndim != 1 or not len(x):
        raise BoundaryEstimationError("detector-x input must be a non-empty vector", profile_id)
    bad = ~np.isfinite(x)
    if bad.any():
        raise BoundaryEstimationError(
            f"detector-x contains {int(bad.sum())} non-finite value(s)", profile_id
        )
    return x


def _histogram(
    x: np.ndarray,
    detector_x_range_mm: tuple[float, float],
    config: BoundaryAlgorithmConfig,
    bin_origin_offset: float,
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    low, high = detector_x_range_mm
    if not (math.isfinite(low) and math.isfinite(high) and low < high):
        raise ValueError(f"invalid detector-x range: {detector_x_range_mm}")
    tolerance = 1.0e-9
    if x.min() < low - tolerance or x.max() > high + tolerance:
        raise ValueError(
            f"detector-x data range [{x.min()}, {x.max()}] is outside metadata range [{low}, {high}]"
        )
    width = config.histogram_bin_width_mm
    start = low + bin_origin_offset * width
    while start > low:
        start -= width
    stop = max(high, float(x.max()))
    bin_count = int(math.ceil((stop - start) / width))
    edges = start + np.arange(bin_count + 1, dtype=float) * width
    if edges[-1] < stop - tolerance:
        edges = np.append(edges, edges[-1] + width)
    counts, edges = np.histogram(x, bins=edges)
    centers = (edges[:-1] + edges[1:]) / 2.0
    return counts.astype(np.int64), edges, centers


def _contiguous_groups(indices: np.ndarray) -> list[np.ndarray]:
    if not len(indices):
        return []
    return list(np.split(indices, np.flatnonzero(np.diff(indices) > 1) + 1))


def _find_valley(
    smooth: np.ndarray,
    centers: np.ndarray,
    left_peak: int,
    right_peak: int,
    config: BoundaryAlgorithmConfig,
    profile_id: str,
) -> ValleyResult:
    interior = np.arange(left_peak + 1, right_peak, dtype=int)
    if not len(interior):
        raise BoundaryEstimationError(
            "adjacent peaks have no histogram bin between them", profile_id
        )
    values = smooth[interior]
    minimum = float(values.min())
    exact_minima = interior[np.isclose(values, minimum, rtol=1.0e-12, atol=1.0e-12)]
    lower_peak = float(min(smooth[left_peak], smooth[right_peak]))
    threshold = minimum + config.valley_plateau_tolerance_fraction * lower_peak
    candidates = interior[values <= threshold + 1.0e-12]
    groups = _contiguous_groups(candidates)
    groups_with_minimum = [group for group in groups if np.intersect1d(group, exact_minima).size]
    if len(groups) != 1 or len(groups_with_minimum) != 1:
        raise BoundaryEstimationError(
            "valley has multiple disconnected near-minimum plateaus", profile_id
        )
    plateau = groups_with_minimum[0]
    if not np.all(np.isin(exact_minima, plateau)):
        raise BoundaryEstimationError("valley minimum is spatially ambiguous", profile_id)
    ratio = minimum / lower_peak if lower_peak > 0 else math.inf
    if not math.isfinite(ratio) or ratio > config.maximum_valley_to_peak_ratio:
        raise BoundaryEstimationError(
            f"valley-to-lower-peak ratio {ratio:.6g} exceeds "
            f"{config.maximum_valley_to_peak_ratio:.6g}",
            profile_id,
        )
    minimum_index = int(exact_minima[len(exact_minima) // 2])
    boundary = float((centers[plateau[0]] + centers[plateau[-1]]) / 2.0)
    return ValleyResult(
        left_peak_index=left_peak,
        right_peak_index=right_peak,
        minimum_index=minimum_index,
        plateau_left_index=int(plateau[0]),
        plateau_right_index=int(plateau[-1]),
        minimum_density=minimum,
        lower_adjacent_peak_density=lower_peak,
        valley_to_peak_ratio=ratio,
        boundary_x_mm=boundary,
    )


def detect_profile_boundaries(
    x_values: Iterable[float],
    detector_x_range_mm: tuple[float, float],
    profile_id: str,
    config: BoundaryAlgorithmConfig | None = None,
    *,
    smoothing_sigma_mm: float | None = None,
    bin_origin_offset: float = 0.0,
) -> DetectionResult:
    """Detect exactly three ordered detector-x bands and their two valleys."""
    if profile_id not in PROFILE_SLITS:
        raise ValueError(f"unknown profile_id: {profile_id!r}")
    config = config or BoundaryAlgorithmConfig()
    config.validate()
    x = _finite_x(x_values, profile_id)
    sigma_mm = config.smoothing_sigma_mm if smoothing_sigma_mm is None else smoothing_sigma_mm
    if not math.isfinite(sigma_mm) or sigma_mm <= 0:
        raise ValueError(f"smoothing sigma must be finite and positive: {sigma_mm!r}")
    try:
        counts, edges, centers = _histogram(
            x, detector_x_range_mm, config, bin_origin_offset
        )
    except ValueError as error:
        raise BoundaryEstimationError(str(error), profile_id) from error
    smooth = gaussian_filter1d(
        counts.astype(float), sigma=sigma_mm / config.histogram_bin_width_mm, mode="nearest"
    )
    maximum = float(smooth.max(initial=0.0))
    peaks, properties = find_peaks(
        smooth,
        height=config.minimum_peak_height_fraction * maximum,
        prominence=config.minimum_peak_prominence_fraction * maximum,
        distance=int(math.ceil(config.minimum_peak_distance_mm / config.histogram_bin_width_mm)),
    )
    prominences = np.asarray(properties.get("prominences", []), dtype=float)
    partial = DetectionResult(
        profile_id=profile_id,
        bin_origin_offset=bin_origin_offset,
        smoothing_sigma_mm=sigma_mm,
        bin_edges_mm=edges,
        bin_centers_mm=centers,
        raw_counts=counts,
        smooth_density=smooth,
        candidate_peak_indices=peaks,
        candidate_peak_prominences=prominences,
        valleys=(),
    )
    if len(peaks) != 3:
        raise BoundaryEstimationError(
            f"expected exactly three major peaks, detected {len(peaks)}", profile_id, partial
        )
    valleys: list[ValleyResult] = []
    try:
        for left, right in zip(peaks, peaks[1:]):
            valleys.append(_find_valley(smooth, centers, int(left), int(right), config, profile_id))
    except BoundaryEstimationError as error:
        error.detection = partial
        raise
    result = DetectionResult(
        **{**asdict(partial), "valleys": tuple(valleys)}  # type: ignore[arg-type]
    )
    ordered = [
        result.peak_x_mm[0], result.boundary_x_mm[0], result.peak_x_mm[1],
        result.boundary_x_mm[1], result.peak_x_mm[2],
    ]
    if not all(math.isfinite(float(value)) for value in ordered) or not all(
        left < right for left, right in zip(ordered, ordered[1:])
    ):
        raise BoundaryEstimationError(
            "peak/boundary order is invalid; expected p1 < b12 < p2 < b23 < p3",
            profile_id,
            result,
        )
    return result


def validate_stability(
    x_values: Iterable[float],
    detector_x_range_mm: tuple[float, float],
    profile_id: str,
    baseline: DetectionResult,
    config: BoundaryAlgorithmConfig | None = None,
) -> tuple[StabilityResult, ...]:
    """Require stable peak and boundary order over the configured perturbation grid."""
    config = config or BoundaryAlgorithmConfig()
    config.validate()
    x = _finite_x(x_values, profile_id)
    rows: list[StabilityResult] = []
    for factor in config.stability_smoothing_factors:
        for origin in config.stability_bin_origin_offsets:
            try:
                candidate = detect_profile_boundaries(
                    x,
                    detector_x_range_mm,
                    profile_id,
                    config,
                    smoothing_sigma_mm=config.smoothing_sigma_mm * factor,
                    bin_origin_offset=origin,
                )
                peak_shift = float(np.max(np.abs(candidate.peak_x_mm - baseline.peak_x_mm)))
                boundary_shift = float(
                    np.max(np.abs(candidate.boundary_x_mm - baseline.boundary_x_mm))
                )
                passed = (
                    peak_shift <= config.maximum_peak_shift_mm
                    and boundary_shift <= config.maximum_boundary_shift_mm
                )
                error = "" if passed else (
                    f"shift exceeds tolerance: peaks={peak_shift:.6g} mm, "
                    f"boundaries={boundary_shift:.6g} mm"
                )
                rows.append(StabilityResult(
                    smoothing_factor=factor,
                    bin_origin_offset=origin,
                    peak_x_mm=tuple(float(value) for value in candidate.peak_x_mm),
                    boundary_x_mm=tuple(float(value) for value in candidate.boundary_x_mm),
                    maximum_peak_shift_mm=peak_shift,
                    maximum_boundary_shift_mm=boundary_shift,
                    passed=passed,
                    error=error,
                ))
            except (BoundaryEstimationError, ValueError) as error:
                rows.append(StabilityResult(
                    smoothing_factor=factor,
                    bin_origin_offset=origin,
                    peak_x_mm=(),
                    boundary_x_mm=(),
                    maximum_peak_shift_mm=math.nan,
                    maximum_boundary_shift_mm=math.nan,
                    passed=False,
                    error=str(error),
                ))
    failures = [row for row in rows if not row.passed]
    if failures:
        details = "; ".join(
            f"sigma_factor={row.smoothing_factor}, origin={row.bin_origin_offset}: {row.error}"
            for row in failures
        )
        raise BoundaryEstimationError(
            f"peak/boundary stability validation failed: {details}", profile_id, baseline
        )
    return tuple(rows)


def detector_x_range(metadata: RunMetadata) -> tuple[float, float]:
    value = metadata.raw.get("detector", {}).get("actual_x_range_mm")
    if not isinstance(value, list) or len(value) != 2:
        raise ValueError(
            f"metadata detector.actual_x_range_mm must contain two values: {metadata.metadata_path}"
        )
    low, high = (float(item) for item in value)
    if not (math.isfinite(low) and math.isfinite(high) and low < high):
        raise ValueError(f"invalid detector.actual_x_range_mm: {metadata.metadata_path}")
    return low, high


def read_detector_coordinates(path: Path) -> tuple[np.ndarray, np.ndarray]:
    xs: list[float] = []
    ys: list[float] = []
    with path.open("r", encoding="utf-8", newline="") as stream:
        reader = csv.DictReader(stream)
        missing = sorted({"det_x", "det_y"}.difference(reader.fieldnames or ()))
        if missing:
            raise ValueError(f"events CSV is missing columns {missing}: {path}")
        for line, row in enumerate(reader, start=2):
            try:
                x = float(row["det_x"])
                y = float(row["det_y"])
            except (TypeError, ValueError) as error:
                raise ValueError(f"invalid detector coordinate at {path}:{line}") from error
            if not (math.isfinite(x) and math.isfinite(y)):
                raise ValueError(f"non-finite detector coordinate at {path}:{line}")
            xs.append(x)
            ys.append(y)
    if not xs:
        raise ValueError(f"events CSV has no detected hits: {path}")
    return np.asarray(xs), np.asarray(ys)


def validate_baseline_metadata(metadata: RunMetadata, expected_profile: str) -> None:
    problems = []
    if metadata.profile_id != expected_profile:
        problems.append(f"profile={metadata.profile_id}")
    if metadata.phantom_id != "P0":
        problems.append(f"phantom={metadata.phantom_id}")
    if metadata.scan_mode != "center":
        problems.append(f"scan_mode={metadata.scan_mode}")
    if metadata.head_offset_x_mm != 0 or metadata.head_offset_y_mm != 0:
        problems.append(
            f"head_offset=({metadata.head_offset_x_mm}, {metadata.head_offset_y_mm})"
        )
    if problems:
        raise ValueError(
            f"invalid boundary baseline metadata {metadata.metadata_path}: " + ", ".join(problems)
        )


def discover_baseline_files(results_root: Path, events_name: str = "events.csv") -> dict[str, Path]:
    files: dict[str, Path] = {}
    for profile_id in PROFILE_SLITS:
        directory = results_root / "events" / "raw" / "center" / "P0" / profile_id
        candidates = sorted(directory.rglob(events_name)) if directory.is_dir() else []
        if len(candidates) != 1:
            raise ValueError(
                f"expected exactly one E1/P0/center baseline for {profile_id}, found "
                f"{len(candidates)} under {directory}"
            )
        metadata = load_run_metadata(candidates[0].parent / "metadata.yaml")
        validate_baseline_metadata(metadata, profile_id)
        files[profile_id] = candidates[0].resolve()
    return files


def estimate_slit_boundaries(
    baseline_files: Mapping[str, Path],
    config: BoundaryAlgorithmConfig | None = None,
) -> tuple[dict[str, ProfileBoundaryEstimate], dict[str, tuple[np.ndarray, np.ndarray]]]:
    """Estimate and stability-check both profile boundaries from P0 center hits only."""
    config = config or BoundaryAlgorithmConfig()
    config.validate()
    if set(baseline_files) != set(PROFILE_SLITS):
        raise ValueError(f"baseline files must contain exactly {tuple(PROFILE_SLITS)}")
    estimates: dict[str, ProfileBoundaryEstimate] = {}
    coordinates: dict[str, tuple[np.ndarray, np.ndarray]] = {}
    for profile_id in PROFILE_SLITS:
        path = Path(baseline_files[profile_id]).resolve()
        metadata = load_run_metadata(path.parent / "metadata.yaml")
        validate_baseline_metadata(metadata, profile_id)
        x, y = read_detector_coordinates(path)
        x_range = detector_x_range(metadata)
        detection = detect_profile_boundaries(x, x_range, profile_id, config)
        stability = validate_stability(x, x_range, profile_id, detection, config)
        estimates[profile_id] = ProfileBoundaryEstimate(
            profile_id=profile_id,
            slit_order=PROFILE_SLITS[profile_id],
            detector_x_range_mm=x_range,
            detected_hit_count=len(x),
            baseline_file=path,
            detection=detection,
            stability=stability,
        )
        coordinates[profile_id] = (x, y)
    return estimates, coordinates


def boundary_config_payload(
    estimates: Mapping[str, ProfileBoundaryEstimate],
    config: BoundaryAlgorithmConfig,
    created_utc: str,
    results_root: Path | None = None,
) -> dict[str, Any]:
    profiles: dict[str, Any] = {}
    for profile_id, estimate in estimates.items():
        detection = estimate.detection
        peak_map = {
            slit: float(value) for slit, value in zip(estimate.slit_order, detection.peak_x_mm)
        }
        boundary_map = {
            key: float(value)
            for key, value in zip(PROFILE_BOUNDARY_KEYS[profile_id], detection.boundary_x_mm)
        }
        baseline_file = estimate.baseline_file.as_posix()
        if results_root is not None:
            try:
                baseline_file = estimate.baseline_file.resolve().relative_to(
                    results_root.resolve()
                ).as_posix()
            except ValueError:
                pass
        profiles[profile_id] = {
            "slit_order": list(estimate.slit_order),
            "peak_x_mm": peak_map,
            "boundaries_mm": boundary_map,
            "detector_x_range_mm": list(estimate.detector_x_range_mm),
            "detected_hit_count": estimate.detected_hit_count,
            "baseline_input_file": baseline_file,
            "valleys": [
                {
                    "left_slit": estimate.slit_order[index],
                    "right_slit": estimate.slit_order[index + 1],
                    "minimum_x_mm": float(detection.bin_centers_mm[valley.minimum_index]),
                    "plateau_x_min_mm": float(
                        detection.bin_centers_mm[valley.plateau_left_index]
                    ),
                    "plateau_x_max_mm": float(
                        detection.bin_centers_mm[valley.plateau_right_index]
                    ),
                    "boundary_x_mm": valley.boundary_x_mm,
                    "minimum_density": valley.minimum_density,
                    "lower_adjacent_peak_density": valley.lower_adjacent_peak_density,
                    "valley_to_peak_ratio": valley.valley_to_peak_ratio,
                }
                for index, valley in enumerate(detection.valleys)
            ],
            "validation": {
                "status": "pass",
                "stability_variant_count": len(estimate.stability),
                "maximum_observed_peak_shift_mm": max(
                    row.maximum_peak_shift_mm for row in estimate.stability
                ),
                "maximum_observed_boundary_shift_mm": max(
                    row.maximum_boundary_shift_mm for row in estimate.stability
                ),
            },
        }
    return {
        "schema_version": SCHEMA_VERSION,
        "algorithm_version": ALGORITHM_VERSION,
        "created_utc": created_utc,
        "coordinate_system": (
            "global detector x at zero head offset; add metadata head_offset_x_mm when labeling"
        ),
        "parameters": asdict(config),
        "profiles": profiles,
    }


def load_boundary_config(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise ValueError(f"cannot read boundary config {path}: {error}") from error
    if not isinstance(payload, dict) or payload.get("schema_version") != SCHEMA_VERSION:
        raise ValueError(f"unsupported slit boundary schema in {path}")
    if payload.get("algorithm_version") != ALGORITHM_VERSION:
        raise ValueError(f"unsupported slit boundary algorithm version in {path}")
    profiles = payload.get("profiles")
    if not isinstance(profiles, dict) or set(profiles) != set(PROFILE_SLITS):
        raise ValueError(f"boundary config must contain exactly {tuple(PROFILE_SLITS)}")
    for profile_id, slit_order in PROFILE_SLITS.items():
        data = profiles[profile_id]
        if not isinstance(data, dict) or tuple(data.get("slit_order", ())) != slit_order:
            raise ValueError(f"invalid slit order for {profile_id} in {path}")
        mapping = data.get("boundaries_mm")
        if not isinstance(mapping, dict) or set(mapping) != set(PROFILE_BOUNDARY_KEYS[profile_id]):
            raise ValueError(f"invalid boundary keys for {profile_id} in {path}")
        try:
            values = tuple(float(mapping[key]) for key in PROFILE_BOUNDARY_KEYS[profile_id])
        except (TypeError, ValueError) as error:
            raise ValueError(f"non-numeric boundary for {profile_id} in {path}") from error
        if not all(math.isfinite(value) for value in values) or not values[0] < values[1]:
            raise ValueError(f"invalid boundary order for {profile_id} in {path}")
    return payload


def profile_boundaries(config: Mapping[str, Any], profile_id: str) -> tuple[float, float]:
    if profile_id not in PROFILE_SLITS:
        raise ValueError(f"unknown profile_id: {profile_id!r}")
    mapping = config["profiles"][profile_id]["boundaries_mm"]
    return tuple(float(mapping[key]) for key in PROFILE_BOUNDARY_KEYS[profile_id])  # type: ignore[return-value]


def slit_label_for_x(
    det_x: float,
    profile_id: str,
    boundaries_zero_mm: tuple[float, float],
    head_offset_x_mm: float = 0.0,
) -> str:
    """Assign every finite detector x using left-open-ended channel partitions."""
    if profile_id not in PROFILE_SLITS:
        raise ValueError(f"unknown profile_id: {profile_id!r}")
    values = (det_x, *boundaries_zero_mm, head_offset_x_mm)
    if not all(math.isfinite(float(value)) for value in values):
        raise ValueError("detector x, boundaries, and head offset must be finite")
    left, right = (value + head_offset_x_mm for value in boundaries_zero_mm)
    if not left < right:
        raise ValueError(f"invalid shifted boundaries for {profile_id}: {(left, right)}")
    slits = PROFILE_SLITS[profile_id]
    if det_x < left:
        return slits[0]
    if det_x < right:
        return slits[1]
    return slits[2]
