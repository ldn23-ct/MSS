#!/usr/bin/env python3
"""Analyze last-scatter depth distributions by detector pixel bin."""

from __future__ import annotations

import argparse
import math
import re
import shutil
import sys
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

try:
    import numpy as np
    import pandas as pd
    import yaml
    from scipy import stats
except ModuleNotFoundError as error:  # pragma: no cover - exercised by CLI users.
    raise RuntimeError(
        "pixel-depth analysis requires the data environment. "
        "Run `conda activate data` or use `conda run -n data python ...`."
    ) from error


SCATTER_CLASSES = ("all", "k1", "k2", "k3", "kn", "km")
CASE_RE = re.compile(
    r"^near_door_(?P<collimator>open|collimated)_(?P<pose>[^_]+)_"
    r"(?P<model_state>[^_]+)_E(?P<energy>\d+)_seed(?P<seed>-?\d+)$"
)
NON_VEHICLE_REGION_IDS = {
    "",
    "none",
    "source",
    "other",
    "unknown",
    "world",
    "world_air",
    "detector",
    "collimator",
}

FIELD_ALIASES: dict[str, tuple[str, ...]] = {
    "det_x": ("det_x", "det_x_mm", "detector_x", "detector_x_mm"),
    "det_y": ("det_y", "det_y_mm", "detector_y", "detector_y_mm"),
    "det_z": ("det_z", "det_z_mm", "detector_z", "detector_z_mm"),
    "scatter_count_total": ("scatter_count_total", "scatter_count", "n_scatter"),
    "last_scatter_z": ("last_scatter_z", "last_scatter_z_mm", "source_depth"),
    "last_scatter_region_id": ("last_scatter_region_id", "last_scatter_region"),
    "first_scatter_z": ("first_scatter_z", "first_scatter_z_mm"),
    "first_scatter_region_id": ("first_scatter_region_id", "first_scatter_region"),
    "is_primary_gamma": ("is_primary_gamma", "is_primary"),
    "gamma_source_type": ("gamma_source_type", "source_type"),
    "det_energy": ("det_energy", "det_energy_keV", "detector_energy_keV"),
}

CONDITION_FIELDS = [
    "pose",
    "seed",
    "energy_keV",
    "collimator",
    "abnormal_present",
    "insert_name",
    "insert_material",
]

PROVENANCE_FIELDS = [
    "run_dir",
    "run_id",
    "case_id",
    "pose_id",
    "pose_index",
    "head_offset_x_mm",
    "head_offset_y_mm",
    "model_type",
    "selected_target_component",
    "abnormal_material",
    "collimator_enable",
    "n_primary",
]


class RunSkip(Exception):
    """Raised when one run cannot be analyzed but the full analysis can continue."""


@dataclass(frozen=True)
class RunFiles:
    run_dir: Path
    metadata_path: Path | None
    events_path: Path


@dataclass(frozen=True)
class BinSpec:
    axis: str
    value_min: float
    value_max: float
    width: float
    edges: list[tuple[float, float]]
    range_source: str


def read_yaml(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as stream:
        value = yaml.safe_load(stream)
    if value is None:
        return {}
    if not isinstance(value, dict):
        raise ValueError(f"metadata root must be a map: {path}")
    return value


def nested(mapping: dict[str, Any], *keys: str, default: Any = None) -> Any:
    value: Any = mapping
    for key in keys:
        if not isinstance(value, dict) or key not in value:
            return default
        value = value[key]
    return value


def as_float(value: Any, default: float = math.nan) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def as_int(value: Any, default: int = 0) -> int:
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return default


def finite_or_nan(value: float) -> float:
    return float(value) if math.isfinite(value) else math.nan


def safe_div(numerator: float, denominator: float) -> float:
    if denominator == 0 or math.isnan(denominator):
        return math.nan
    return numerator / denominator


def safe_median(values: Iterable[float]) -> float:
    clean = [float(value) for value in values if not math.isnan(float(value))]
    if not clean:
        return math.nan
    return float(np.median(np.asarray(clean, dtype=float)))


def lag_metric_values(values: np.ndarray, max_samples: int) -> np.ndarray:
    values = values[np.isfinite(values)]
    if max_samples <= 0 or values.size <= max_samples:
        return values
    sorted_values = np.sort(values)
    indices = np.linspace(0, sorted_values.size - 1, max_samples)
    return sorted_values[np.rint(indices).astype(int)]


def format_for_csv(value: Any) -> Any:
    if isinstance(value, (np.floating, float)):
        value = float(value)
        if math.isnan(value):
            return "NaN"
        return f"{value:.12g}"
    if isinstance(value, (np.integer, int)):
        return int(value)
    if isinstance(value, (np.bool_, bool)):
        return bool(value)
    return value


def to_builtin(value: Any) -> Any:
    if isinstance(value, Path):
        return value.as_posix()
    if isinstance(value, dict):
        return {str(key): to_builtin(item) for key, item in value.items()}
    if isinstance(value, list):
        return [to_builtin(item) for item in value]
    if isinstance(value, tuple):
        return [to_builtin(item) for item in value]
    if isinstance(value, np.generic):
        return value.item()
    if isinstance(value, float) and math.isnan(value):
        return "NaN"
    return value


def write_csv(path: Path, rows: list[dict[str, Any]], fieldnames: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    frame = pd.DataFrame(rows)
    if frame.empty:
        frame = pd.DataFrame(columns=fieldnames)
    else:
        for field in fieldnames:
            if field not in frame.columns:
                frame[field] = math.nan
        frame = frame[fieldnames]
    if hasattr(frame, "map"):
        frame = frame.map(format_for_csv)
    else:
        frame = frame.applymap(format_for_csv)
    frame.to_csv(path, index=False)


def energy_dir_name(value: Any) -> str:
    numeric = as_float(value)
    if math.isfinite(numeric):
        if numeric.is_integer():
            return f"E{int(numeric)}"
        return "E" + str(numeric).replace(".", "p")
    return "Eunknown"


def model_state_from_condition(row: dict[str, Any]) -> str:
    if not bool(row.get("abnormal_present", False)):
        return "normal"
    material = str(row.get("insert_material", "") or "")
    if material == "Vehicle_Flour":
        return "cavityFlour"
    if material == "G4_W":
        return "cavityW"
    return "cavityPE"


def condition_dir(row: dict[str, Any], *, include_energy: bool = True) -> Path:
    parts = [
        "by_condition",
        safe_name(str(row.get("collimator", "unknown"))),
        safe_name(str(row.get("pose", "unknown_pose"))),
        safe_name(model_state_from_condition(row)),
    ]
    if include_energy:
        parts.append(energy_dir_name(row.get("energy_keV")))
    return Path(*parts)


def clean_owned_outputs(output_dir: Path) -> None:
    owned = [
        "by_condition",
        "pixel_depth_summary_by_scatter_class",
        "bin_lag_distribution_metrics",
        "scatter_order_spatial_summary",
        "pixel_scatter_class_fraction",
    ]
    for name in owned:
        csv_path = output_dir / f"{name}.csv"
        if csv_path.exists():
            csv_path.unlink()
        directory = output_dir / name
        if directory.exists():
            shutil.rmtree(directory)


def relative_path(path: Path, base: Path) -> str:
    try:
        return path.relative_to(base).as_posix()
    except ValueError:
        return path.as_posix()


def write_split_by_energy_and_class(
    output_dir: Path,
    table_name: str,
    rows: list[dict[str, Any]],
    fieldnames: list[str],
) -> dict[str, Any]:
    table_dir = output_dir / table_name
    index: dict[str, dict[str, str]] = {}
    grouped: dict[tuple[str, str], list[dict[str, Any]]] = {}
    for row in rows:
        energy = energy_dir_name(row.get("energy_keV"))
        scatter_class = safe_name(str(row.get("scatter_class", "unknown")))
        grouped.setdefault((energy, scatter_class), []).append(row)
    for (energy, scatter_class), group_rows in sorted(grouped.items()):
        path = table_dir / energy / f"{scatter_class}.csv"
        write_csv(path, group_rows, fieldnames)
        index.setdefault(energy, {})[scatter_class] = relative_path(path, output_dir)
    return {
        "directory": relative_path(table_dir, output_dir),
        "split_by": ["energy_keV", "scatter_class"],
        "files": index,
    }


def write_split_by_condition_and_class(
    output_dir: Path,
    table_name: str,
    rows: list[dict[str, Any]],
    fieldnames: list[str],
) -> dict[str, Any]:
    index_rows: list[dict[str, Any]] = []
    grouped: dict[tuple[str, str], list[dict[str, Any]]] = {}
    for row in rows:
        rel_dir = condition_dir(row)
        scatter_class = safe_name(str(row.get("scatter_class", "unknown")))
        grouped.setdefault((rel_dir.as_posix(), scatter_class), []).append(row)
    for (rel_dir_text, scatter_class), group_rows in sorted(grouped.items()):
        path = output_dir / rel_dir_text / table_name / f"{scatter_class}.csv"
        write_csv(path, group_rows, fieldnames)
        first = group_rows[0]
        index_rows.append(
            {
                "system": first.get("collimator"),
                "pose": first.get("pose"),
                "model_state": model_state_from_condition(first),
                "energy_keV": first.get("energy_keV"),
                "scatter_class": scatter_class,
                "path": relative_path(path, output_dir),
            }
        )
    return {
        "directory": "by_condition",
        "layout": "by_condition/{system}/{pose}/{model_state}/E{energy}/" + table_name + "/{scatter_class}.csv",
        "split_by": ["collimator", "pose", "model_state", "energy_keV", "scatter_class"],
        "files": index_rows,
    }


def write_split_by_energy(
    output_dir: Path,
    table_name: str,
    rows: list[dict[str, Any]],
    filename: str,
    fieldnames: list[str],
) -> dict[str, Any]:
    table_dir = output_dir / table_name
    index: dict[str, str] = {}
    grouped: dict[str, list[dict[str, Any]]] = {}
    for row in rows:
        grouped.setdefault(energy_dir_name(row.get("energy_keV")), []).append(row)
    for energy, group_rows in sorted(grouped.items()):
        path = table_dir / energy / filename
        write_csv(path, group_rows, fieldnames)
        index[energy] = relative_path(path, output_dir)
    return {
        "directory": relative_path(table_dir, output_dir),
        "split_by": ["energy_keV"],
        "files": index,
    }


def write_split_by_condition(
    output_dir: Path,
    table_name: str,
    rows: list[dict[str, Any]],
    filename: str,
    fieldnames: list[str],
) -> dict[str, Any]:
    index_rows: list[dict[str, Any]] = []
    grouped: dict[str, list[dict[str, Any]]] = {}
    for row in rows:
        grouped.setdefault(condition_dir(row).as_posix(), []).append(row)
    for rel_dir_text, group_rows in sorted(grouped.items()):
        path = output_dir / rel_dir_text / table_name / filename
        write_csv(path, group_rows, fieldnames)
        first = group_rows[0]
        index_rows.append(
            {
                "system": first.get("collimator"),
                "pose": first.get("pose"),
                "model_state": model_state_from_condition(first),
                "energy_keV": first.get("energy_keV"),
                "path": relative_path(path, output_dir),
            }
        )
    return {
        "directory": "by_condition",
        "layout": "by_condition/{system}/{pose}/{model_state}/E{energy}/" + table_name + "/" + filename,
        "split_by": ["collimator", "pose", "model_state", "energy_keV"],
        "files": index_rows,
    }


def write_yaml(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as stream:
        yaml.safe_dump(to_builtin(data), stream, sort_keys=False, allow_unicode=False)


def discover_run_files(paths: Iterable[Path]) -> list[RunFiles]:
    discovered: list[RunFiles] = []
    seen: set[Path] = set()
    for raw_path in paths:
        path = raw_path.expanduser()
        candidates: list[Path] = []
        if path.is_file():
            if path.name in {"events.csv", "metadata.yaml"}:
                candidates.append(path.parent)
        elif path.is_dir():
            if (path / "events.csv").is_file():
                candidates.append(path)
            candidates.extend(metadata.parent for metadata in path.rglob("metadata.yaml"))
        for candidate in candidates:
            run_dir = candidate.resolve()
            if run_dir in seen:
                continue
            metadata_path = run_dir / "metadata.yaml"
            events_path = run_dir / "events.csv"
            if events_path.is_file():
                seen.add(run_dir)
                discovered.append(
                    RunFiles(
                        run_dir=run_dir,
                        metadata_path=metadata_path if metadata_path.is_file() else None,
                        events_path=events_path,
                    )
                )
    return sorted(discovered, key=lambda item: item.run_dir.as_posix())


def csv_header(path: Path) -> list[str]:
    with path.open("r", encoding="utf-8", newline="") as stream:
        first_line = stream.readline().strip()
    if not first_line:
        raise RunSkip(f"events CSV has no header: {path}")
    return first_line.split(",")


def field_mapping(header: list[str]) -> dict[str, str]:
    fields = set(header)
    mapping: dict[str, str] = {}
    for standard, aliases in FIELD_ALIASES.items():
        for alias in aliases:
            if alias in fields:
                mapping[standard] = alias
                break
    return mapping


def require_fields(mapping: dict[str, str], required: Iterable[str], path: Path) -> None:
    missing = [field for field in required if field not in mapping]
    if missing:
        raise RunSkip(f"events CSV missing required field(s) {', '.join(missing)}: {path}")


def load_events(path: Path, mapping: dict[str, str]) -> pd.DataFrame:
    usecols = sorted(set(mapping.values()))
    frame = pd.read_csv(path, usecols=usecols)
    reverse = {actual: standard for standard, actual in mapping.items()}
    frame = frame.rename(columns=reverse)
    for field in ("det_x", "det_y", "det_z", "scatter_count_total", "last_scatter_z", "first_scatter_z", "det_energy"):
        if field in frame.columns:
            frame[field] = pd.to_numeric(frame[field], errors="coerce")
    return frame


def model_state_from_material(material: Any, model_type: Any) -> str:
    if str(model_type or "normal") == "normal" or material in (None, ""):
        return "normal"
    material_text = str(material)
    if material_text == "Vehicle_Flour":
        return "cavityFlour"
    if material_text == "G4_W":
        return "cavityW"
    return "cavityPE"


def experiment_condition(metadata: dict[str, Any]) -> dict[str, Any]:
    case_id = str(nested(metadata, "diagnostics", "case_id", default="") or "")
    merge_condition = metadata.get("merge_condition")
    match = CASE_RE.match(case_id)
    if isinstance(merge_condition, dict):
        pose = str(merge_condition.get("pose", metadata.get("pose_id", "unknown_pose")))
        seed: Any = "merged"
        energy: Any = merge_condition.get("energy_keV", nested(metadata, "source", "mono_energy_keV", default=""))
        collimator = str(merge_condition.get("system", ""))
    elif match:
        pose = match.group("pose")
        seed: Any = int(match.group("seed"))
        energy: Any = int(match.group("energy"))
        collimator = match.group("collimator")
    else:
        pose = str(metadata.get("pose_id", "") or "unknown_pose")
        seed = metadata.get("random_seed", "")
        if seed is None:
            seed = "merged"
        energy = nested(metadata, "source", "mono_energy_keV", default="")
        collimator = "collimated" if bool(nested(metadata, "collimator", "enable", default=False)) else "open"

    model_type = str(metadata.get("model_type", "normal") or "normal")
    abnormal_present = model_type != "normal"
    insert_name = metadata.get("selected_target_component", "") if abnormal_present else ""
    insert_material = metadata.get("abnormal_material", "") if abnormal_present else ""
    return {
        "pose": pose,
        "seed": seed,
        "energy_keV": energy,
        "collimator": collimator,
        "abnormal_present": abnormal_present,
        "insert_name": insert_name,
        "insert_material": insert_material,
    }


def run_provenance(run_files: RunFiles, metadata: dict[str, Any]) -> dict[str, Any]:
    seed = metadata.get("random_seed", "")
    if seed is None:
        seed = "merged"
    return {
        "run_dir": run_files.run_dir.as_posix(),
        "run_id": metadata.get("run_id", run_files.run_dir.name),
        "case_id": nested(metadata, "diagnostics", "case_id", default=""),
        "pose_id": metadata.get("pose_id", ""),
        "pose_index": metadata.get("pose_index", ""),
        "head_offset_x_mm": metadata.get("head_offset_x_mm", ""),
        "head_offset_y_mm": metadata.get("head_offset_y_mm", ""),
        "model_type": metadata.get("model_type", ""),
        "selected_target_component": metadata.get("selected_target_component", ""),
        "abnormal_material": metadata.get("abnormal_material", ""),
        "collimator_enable": nested(metadata, "collimator", "enable", default=""),
        "energy_keV": nested(metadata, "source", "mono_energy_keV", default=""),
        "seed": seed,
        "n_primary": metadata.get("n_primary", ""),
        "model_state": model_state_from_material(metadata.get("abnormal_material"), metadata.get("model_type")),
    }


def detector_range_from_metadata(metadata: dict[str, Any], axis: str) -> tuple[float, float, str] | None:
    axis_name = "x" if axis == "det_x" else "y"
    detector = metadata.get("detector", {})
    if not isinstance(detector, dict):
        return None
    actual = detector.get(f"actual_{axis_name}_range_mm")
    if isinstance(actual, list) and len(actual) == 2:
        low, high = as_float(actual[0]), as_float(actual[1])
        if math.isfinite(low) and math.isfinite(high) and low < high:
            return low, high, f"metadata.detector.actual_{axis_name}_range_mm"
    zero = detector.get(f"detector_{axis_name}_range_zero_mm")
    offset = as_float(metadata.get(f"head_offset_{axis_name}_mm"), 0.0)
    if isinstance(zero, list) and len(zero) == 2:
        low, high = as_float(zero[0]), as_float(zero[1])
        if math.isfinite(low) and math.isfinite(high) and low < high:
            return low + offset, high + offset, f"metadata.detector.detector_{axis_name}_range_zero_mm+head_offset"
    return None


def make_bin_spec(
    frame: pd.DataFrame,
    metadata: dict[str, Any],
    axis: str,
    bin_width_mm: float,
) -> BinSpec:
    if bin_width_mm <= 0:
        raise ValueError("bin_width_mm must be > 0")
    detected_range = detector_range_from_metadata(metadata, axis)
    if detected_range is None:
        values = pd.to_numeric(frame[axis], errors="coerce")
        clean = values[np.isfinite(values)]
        if clean.empty:
            raise RunSkip(f"no finite detector {axis} values are available")
        value_min = float(clean.min())
        value_max = float(clean.max())
        if value_min == value_max:
            value_max = value_min + bin_width_mm
        range_source = "events_csv_minmax"
    else:
        value_min, value_max, range_source = detected_range
    bin_count = int(math.ceil((value_max - value_min) / bin_width_mm))
    if bin_count <= 0:
        raise RunSkip(f"detector {axis} range produced no bins")
    edges = [
        (
            value_min + index * bin_width_mm,
            min(value_min + (index + 1) * bin_width_mm, value_max),
        )
        for index in range(bin_count)
    ]
    return BinSpec(axis=axis, value_min=value_min, value_max=value_max, width=bin_width_mm, edges=edges, range_source=range_source)


def assign_bins(values: pd.Series, spec: BinSpec) -> pd.Series:
    numeric = pd.to_numeric(values, errors="coerce").to_numpy(dtype=float)
    bin_count = len(spec.edges)
    indices = np.full(len(numeric), -1, dtype=int)
    finite = np.isfinite(numeric)
    inside = finite & (numeric >= spec.value_min) & (numeric <= spec.value_max)
    raw = np.floor((numeric[inside] - spec.value_min) / spec.width).astype(int)
    raw = np.minimum(np.maximum(raw, 0), bin_count - 1)
    indices[inside] = raw
    return pd.Series(indices, index=values.index)


def region_values(value: Any) -> set[str]:
    found: set[str] = set()
    if isinstance(value, str):
        found.add(value)
    elif isinstance(value, dict):
        for item in value.values():
            found.update(region_values(item))
    elif isinstance(value, list):
        for item in value:
            found.update(region_values(item))
    return found


def resolve_path(path_text: Any, run_dir: Path) -> Path | None:
    if not isinstance(path_text, str) or not path_text:
        return None
    path = Path(path_text)
    candidates = [path] if path.is_absolute() else [Path.cwd() / path, run_dir / path]
    for candidate in candidates:
        if candidate.is_file():
            return candidate
    return candidates[0]


def vehicle_regions_from_metadata(metadata: dict[str, Any], run_dir: Path) -> tuple[set[str] | None, str | None]:
    geometry_path = resolve_path(metadata.get("vehicle_geometry_file"), run_dir)
    if geometry_path is None:
        return None, "metadata has no vehicle_geometry_file"
    if not geometry_path.is_file():
        return None, f"vehicle geometry file not found: {geometry_path}"
    geometry = read_yaml(geometry_path)
    regions: set[str] = set()
    for component in geometry.get("components", []) if isinstance(geometry.get("components"), list) else []:
        if isinstance(component, dict):
            regions.update(region_values(component.get("region_id")))
    regions.update(region_values(metadata.get("abnormal_target_region")))
    cleaned = {region for region in regions if region not in NON_VEHICLE_REGION_IDS}
    if not cleaned:
        return None, f"no vehicle region ids found in {geometry_path}"
    return cleaned, None


def scatter_masks(frame: pd.DataFrame) -> dict[str, pd.Series]:
    scatter = pd.to_numeric(frame["scatter_count_total"], errors="coerce")
    return {
        "all": scatter > 0,
        "k1": scatter == 1,
        "k2": scatter == 2,
        "k3": scatter == 3,
        "kn": scatter >= 4,
        "km": scatter >= 2,
    }


def depth_stats(values: np.ndarray) -> dict[str, float | int]:
    values = values[np.isfinite(values)]
    count = int(values.size)
    if count == 0:
        return {
            "count": 0,
            "mean": math.nan,
            "std": math.nan,
            "q05": math.nan,
            "q25": math.nan,
            "median": math.nan,
            "q75": math.nan,
            "q95": math.nan,
            "iqr": math.nan,
            "width90": math.nan,
        }
    q05, q25, median, q75, q95 = np.quantile(values, [0.05, 0.25, 0.5, 0.75, 0.95])
    return {
        "count": count,
        "mean": float(np.mean(values)),
        "std": float(np.std(values, ddof=1)) if count > 1 else math.nan,
        "q05": float(q05),
        "q25": float(q25),
        "median": float(median),
        "q75": float(q75),
        "q95": float(q95),
        "iqr": float(q75 - q25),
        "width90": float(q95 - q05),
    }


def class_depth_rows(
    info: dict[str, Any],
    frame: pd.DataFrame,
    spec: BinSpec,
    region_filter: str,
    scatter_class: str,
) -> tuple[list[dict[str, Any]], dict[int, np.ndarray]]:
    masks = scatter_masks(frame)
    selected = frame[masks[scatter_class]]
    grouped_values = {
        int(index): group["source_depth"].to_numpy(dtype=float)
        for index, group in selected.groupby("bin_index", sort=False)
    }
    values_by_bin: dict[int, np.ndarray] = {}
    rows: list[dict[str, Any]] = []
    for index, (left, right) in enumerate(spec.edges):
        values = grouped_values.get(index, np.asarray([], dtype=float))
        values = values[np.isfinite(values)]
        values_by_bin[index] = values
        row = {
            **info,
            "region_filter": region_filter,
            "scatter_class": scatter_class,
            "bin_axis": spec.axis,
            "bin_index": index,
            "bin_min_mm": left,
            "bin_max_mm": right,
            "bin_center_mm": (left + right) * 0.5,
            **depth_stats(values),
        }
        rows.append(row)
    return rows, values_by_bin


def lag_metric_rows(
    info: dict[str, Any],
    spec: BinSpec,
    region_filter: str,
    scatter_class: str,
    values_by_bin: dict[int, np.ndarray],
    stats_by_bin: dict[int, dict[str, Any]],
    lags: list[int],
    min_bin_samples: int,
    max_lag_samples_per_bin: int,
) -> tuple[list[dict[str, Any]], list[str]]:
    rows: list[dict[str, Any]] = []
    warnings: list[str] = []
    bin_count = len(spec.edges)
    metric_values_by_bin = {
        index: lag_metric_values(values, max_lag_samples_per_bin)
        for index, values in values_by_bin.items()
    }
    for lag in lags:
        if lag <= 0:
            warnings.append(f"ignored non-positive lag {lag}")
            continue
        if lag >= bin_count:
            warnings.append(f"lag {lag} skipped because bin_count is {bin_count}")
            continue
        for left_index in range(0, bin_count - lag):
            right_index = left_index + lag
            left_count = values_by_bin[left_index].size
            right_count = values_by_bin[right_index].size
            if left_count < min_bin_samples or right_count < min_bin_samples:
                continue
            left_values = metric_values_by_bin[left_index]
            right_values = metric_values_by_bin[right_index]
            w1 = float(stats.wasserstein_distance(left_values, right_values))
            ks = float(stats.ks_2samp(left_values, right_values).statistic)
            left_width = as_float(stats_by_bin[left_index].get("width90"))
            right_width = as_float(stats_by_bin[right_index].get("width90"))
            mean_width = float(np.nanmean([left_width, right_width]))
            separation = safe_div(w1, mean_width)
            rows.append(
                {
                    **info,
                    "region_filter": region_filter,
                    "scatter_class": scatter_class,
                    "lag": lag,
                    "bin_index_a": left_index,
                    "bin_index_b": right_index,
                    "bin_center_a_mm": (spec.edges[left_index][0] + spec.edges[left_index][1]) * 0.5,
                    "bin_center_b_mm": (spec.edges[right_index][0] + spec.edges[right_index][1]) * 0.5,
                    "count_a": int(left_count),
                    "count_b": int(right_count),
                    "metric_count_a": int(left_values.size),
                    "metric_count_b": int(right_values.size),
                    "wasserstein1": w1,
                    "ks_statistic": ks,
                    "mean_width90": mean_width,
                    "separation_score": separation,
                }
            )
    return rows, warnings


def summary_row(
    info: dict[str, Any],
    region_filter: str,
    scatter_class: str,
    bin_rows: list[dict[str, Any]],
    lag_rows: list[dict[str, Any]],
    lags: list[int],
    min_bin_samples: int,
    min_valid_bins: int,
) -> dict[str, Any]:
    valid_bins = [
        row
        for row in bin_rows
        if int(row["count"]) >= min_bin_samples and not math.isnan(as_float(row.get("median")))
    ]
    n_valid_hits = int(sum(int(row["count"]) for row in bin_rows))
    n_valid_bins = len(valid_bins)
    spearman_rho = math.nan
    spearman_p = math.nan
    slope = math.nan
    slope_p = math.nan
    if n_valid_bins >= min_valid_bins:
        x = np.asarray([int(row["bin_index"]) for row in valid_bins], dtype=float)
        y = np.asarray([float(row["median"]) for row in valid_bins], dtype=float)
        if np.unique(y).size > 1 and np.unique(x).size > 1:
            rho_result = stats.spearmanr(x, y)
            spearman_rho = finite_or_nan(float(rho_result.statistic))
            spearman_p = finite_or_nan(float(rho_result.pvalue))
            slope_result = stats.linregress(x, y)
            slope = finite_or_nan(float(slope_result.slope))
            slope_p = finite_or_nan(float(slope_result.pvalue))
    width90 = safe_median(row["width90"] for row in valid_bins)
    row: dict[str, Any] = {
        **info,
        "region_filter": region_filter,
        "scatter_class": scatter_class,
        "n_valid_hits": n_valid_hits,
        "n_valid_bins": n_valid_bins,
        "min_bin_samples": min_bin_samples,
        "min_valid_bins": min_valid_bins,
        "spearman_rho": spearman_rho,
        "spearman_pvalue": spearman_p,
        "slope_depth_per_bin": slope,
        "slope_pvalue": slope_p,
        "median_width90": width90,
        "median_wasserstein1_all_lags": safe_median(item["wasserstein1"] for item in lag_rows),
        "median_ks_all_lags": safe_median(item["ks_statistic"] for item in lag_rows),
        "median_separation_all_lags": safe_median(item["separation_score"] for item in lag_rows),
        "spatial_score": math.nan,
        "rho_retention_vs_k1": math.nan,
        "width_inflation_vs_k1": math.nan,
        "sep_retention_vs_k1": math.nan,
        "spatial_score_retention_vs_k1": math.nan,
    }
    if not math.isnan(row["spearman_rho"]) and not math.isnan(row["median_separation_all_lags"]):
        row["spatial_score"] = abs(float(row["spearman_rho"])) * float(row["median_separation_all_lags"])
    for lag in lags:
        lag_items = [item for item in lag_rows if int(item["lag"]) == lag]
        row[f"median_wasserstein1_lag{lag}"] = safe_median(item["wasserstein1"] for item in lag_items)
        row[f"median_ks_lag{lag}"] = safe_median(item["ks_statistic"] for item in lag_items)
        row[f"median_separation_lag{lag}"] = safe_median(item["separation_score"] for item in lag_items)
    return row


def add_relative_to_k1(summary_rows: list[dict[str, Any]]) -> None:
    by_key: dict[tuple[str, str], dict[str, Any]] = {}
    for row in summary_rows:
        by_key[(str(row["region_filter"]), str(row["scatter_class"]))] = row
    baseline_by_filter = {
        region_filter: row
        for (region_filter, scatter_class), row in by_key.items()
        if scatter_class == "k1"
    }
    for row in summary_rows:
        baseline = baseline_by_filter.get(str(row["region_filter"]))
        if baseline is None:
            continue
        row["rho_retention_vs_k1"] = safe_div(
            abs(as_float(row.get("spearman_rho"))),
            abs(as_float(baseline.get("spearman_rho"))),
        )
        row["width_inflation_vs_k1"] = safe_div(
            as_float(row.get("median_width90")),
            as_float(baseline.get("median_width90")),
        )
        row["sep_retention_vs_k1"] = safe_div(
            as_float(row.get("median_separation_all_lags")),
            as_float(baseline.get("median_separation_all_lags")),
        )
        row["spatial_score_retention_vs_k1"] = safe_div(
            as_float(row.get("spatial_score")),
            as_float(baseline.get("spatial_score")),
        )


def fraction_rows(
    info: dict[str, Any],
    frame: pd.DataFrame,
    spec: BinSpec,
    region_filter: str,
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    counts_by_bin: dict[int, dict[str, int]] = {
        index: {"k0": 0, "k1": 0, "k2": 0, "k3": 0, "kn": 0, "km": 0, "total": 0}
        for index in range(len(spec.edges))
    }
    if not frame.empty:
        scatter = pd.to_numeric(frame["scatter_count_total"], errors="coerce")
        count_frame = pd.DataFrame({"bin_index": frame["bin_index"].to_numpy(), "scatter": scatter})
        count_frame = count_frame[count_frame["scatter"].notna()]
        for index, group in count_frame.groupby("bin_index", sort=False):
            index_int = int(index)
            if index_int not in counts_by_bin:
                continue
            group_scatter = group["scatter"]
            counts_by_bin[index_int] = {
                "k0": int((group_scatter == 0).sum()),
                "k1": int((group_scatter == 1).sum()),
                "k2": int((group_scatter == 2).sum()),
                "k3": int((group_scatter == 3).sum()),
                "kn": int((group_scatter >= 4).sum()),
                "km": int((group_scatter >= 2).sum()),
                "total": int(group_scatter.size),
            }
    for index, (left, right) in enumerate(spec.edges):
        count_group = counts_by_bin[index]
        counts = {key: count_group[key] for key in ("k0", "k1", "k2", "k3", "kn", "km")}
        total = count_group["total"]
        row = {
            **info,
            "region_filter": region_filter,
            "bin_axis": spec.axis,
            "bin_index": index,
            "bin_min_mm": left,
            "bin_max_mm": right,
            "bin_center_mm": (left + right) * 0.5,
            "count_all": total,
            **{f"count_{key}": value for key, value in counts.items()},
        }
        for key, value in counts.items():
            row[f"fraction_{key}"] = safe_div(value, total)
        rows.append(row)
    return rows


def analyze_run(
    run_files: RunFiles,
    axis: str,
    bin_width_mm: float,
    lags: list[int],
    min_bin_samples: int,
    min_valid_bins: int,
    max_lag_samples_per_bin: int,
) -> tuple[
    list[dict[str, Any]],
    list[dict[str, Any]],
    list[dict[str, Any]],
    list[dict[str, Any]],
    dict[str, Any],
]:
    metadata = read_yaml(run_files.metadata_path) if run_files.metadata_path else {}
    header = csv_header(run_files.events_path)
    mapping = field_mapping(header)
    require_fields(mapping, (axis, "scatter_count_total", "last_scatter_z"), run_files.events_path)
    frame = load_events(run_files.events_path, mapping)
    info = experiment_condition(metadata)
    provenance = run_provenance(run_files, metadata)
    spec = make_bin_spec(frame, metadata, axis, bin_width_mm)
    frame["bin_index"] = assign_bins(frame[axis], spec)
    frame = frame[frame["bin_index"] >= 0].copy()
    if frame.empty:
        raise RunSkip(f"no hits fell inside the detector {axis} bin range: {run_files.events_path}")
    frame["source_depth"] = pd.to_numeric(frame["last_scatter_z"], errors="coerce")
    frame["scatter_count_total"] = pd.to_numeric(frame["scatter_count_total"], errors="coerce")

    vehicle_regions, vehicle_region_warning = vehicle_regions_from_metadata(metadata, run_files.run_dir)
    has_region_column = "last_scatter_region_id" in frame.columns
    run_warnings: list[str] = []
    if vehicle_region_warning:
        run_warnings.append(vehicle_region_warning)
    if not has_region_column:
        run_warnings.append("events CSV has no last_scatter_region_id; vehicle_only filter skipped")

    valid_depth = frame[(frame["source_depth"].notna()) & (frame["scatter_count_total"] > 0)].copy()
    if valid_depth.empty:
        raise RunSkip(f"no finite last_scatter_z samples are available: {run_files.events_path}")

    region_frames: dict[str, pd.DataFrame] = {"all_valid": valid_depth}
    fraction_frames: dict[str, pd.DataFrame] = {
        "all_valid": frame[frame["scatter_count_total"].notna()].copy()
    }
    if vehicle_regions is not None and has_region_column:
        region_mask = valid_depth["last_scatter_region_id"].astype(str).isin(vehicle_regions)
        fraction_region_mask = frame["last_scatter_region_id"].astype(str).isin(vehicle_regions)
        region_frames["vehicle_only"] = valid_depth[region_mask].copy()
        fraction_frames["vehicle_only"] = frame[fraction_region_mask & frame["scatter_count_total"].notna()].copy()

    depth_rows: list[dict[str, Any]] = []
    lag_rows: list[dict[str, Any]] = []
    summary_rows: list[dict[str, Any]] = []
    scatter_fraction_rows: list[dict[str, Any]] = []

    for region_filter, region_frame in region_frames.items():
        run_summary_rows: list[dict[str, Any]] = []
        for scatter_class in SCATTER_CLASSES:
            class_rows, values_by_bin = class_depth_rows(info, region_frame, spec, region_filter, scatter_class)
            stats_by_bin = {int(row["bin_index"]): row for row in class_rows}
            class_lag_rows, warnings = lag_metric_rows(
                info,
                spec,
                region_filter,
                scatter_class,
                values_by_bin,
                stats_by_bin,
                lags,
                min_bin_samples,
                max_lag_samples_per_bin,
            )
            run_warnings.extend(warnings)
            depth_rows.extend(class_rows)
            lag_rows.extend(class_lag_rows)
            run_summary_rows.append(
                summary_row(
                    info,
                    region_filter,
                    scatter_class,
                    class_rows,
                    class_lag_rows,
                    lags,
                    min_bin_samples,
                    min_valid_bins,
                )
            )
        add_relative_to_k1(run_summary_rows)
        summary_rows.extend(run_summary_rows)
    for region_filter, fraction_frame in fraction_frames.items():
        scatter_fraction_rows.extend(fraction_rows(info, fraction_frame, spec, region_filter))

    run_manifest = {
        "run_dir": run_files.run_dir.as_posix(),
        "run_id": provenance["run_id"],
        "condition": info,
        "provenance": provenance,
        "events_csv": run_files.events_path.as_posix(),
        "metadata_yaml": run_files.metadata_path.as_posix() if run_files.metadata_path else None,
        "field_mapping": mapping,
        "bin_axis": spec.axis,
        "bin_width_mm": spec.width,
        "bin_count": len(spec.edges),
        "bin_range_mm": [spec.value_min, spec.value_max],
        "bin_range_source": spec.range_source,
        "vehicle_only_enabled": "vehicle_only" in region_frames,
        "vehicle_region_count": len(vehicle_regions) if vehicle_regions else 0,
        "warnings": sorted(set(run_warnings)),
    }
    return depth_rows, lag_rows, summary_rows, scatter_fraction_rows, run_manifest


def output_fieldnames(lags: list[int]) -> dict[str, list[str]]:
    bin_fields = [
        *CONDITION_FIELDS,
        "region_filter",
        "bin_axis",
        "bin_index",
        "bin_min_mm",
        "bin_max_mm",
        "bin_center_mm",
        "count",
        "mean",
        "std",
        "q05",
        "q25",
        "median",
        "q75",
        "q95",
        "iqr",
        "width90",
    ]
    lag_fields = [
        *CONDITION_FIELDS,
        "region_filter",
        "lag",
        "bin_index_a",
        "bin_index_b",
        "bin_center_a_mm",
        "bin_center_b_mm",
        "count_a",
        "count_b",
        "metric_count_a",
        "metric_count_b",
        "wasserstein1",
        "ks_statistic",
        "mean_width90",
        "separation_score",
    ]
    summary_fields = [
        *CONDITION_FIELDS,
        "region_filter",
        "n_valid_hits",
        "n_valid_bins",
        "min_bin_samples",
        "min_valid_bins",
        "spearman_rho",
        "spearman_pvalue",
        "slope_depth_per_bin",
        "slope_pvalue",
        "median_width90",
        "median_wasserstein1_all_lags",
        "median_ks_all_lags",
        "median_separation_all_lags",
        "spatial_score",
    ]
    for lag in lags:
        summary_fields.extend(
            [
                f"median_wasserstein1_lag{lag}",
                f"median_ks_lag{lag}",
                f"median_separation_lag{lag}",
            ]
        )
    summary_fields.extend(
        [
            "rho_retention_vs_k1",
            "width_inflation_vs_k1",
            "sep_retention_vs_k1",
            "spatial_score_retention_vs_k1",
        ]
    )
    fraction_fields = [
        *CONDITION_FIELDS,
        "region_filter",
        "bin_axis",
        "bin_index",
        "bin_min_mm",
        "bin_max_mm",
        "bin_center_mm",
        "count_all",
        "count_k0",
        "count_k1",
        "count_k2",
        "count_k3",
        "count_kn",
        "count_km",
        "fraction_k0",
        "fraction_k1",
        "fraction_k2",
        "fraction_k3",
        "fraction_kn",
        "fraction_km",
    ]
    return {
        "depth": bin_fields,
        "lag": lag_fields,
        "summary": summary_fields,
        "fraction": fraction_fields,
    }


def safe_name(text: str) -> str:
    return re.sub(r"[^A-Za-z0-9_.-]+", "_", text).strip("_") or "run"


def write_plots(output_dir: Path, depth_rows: list[dict[str, Any]], fraction_rows_: list[dict[str, Any]], summary_rows_: list[dict[str, Any]]) -> list[Path]:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    plot_dir = output_dir / "plots"
    plot_dir.mkdir(parents=True, exist_ok=True)
    paths: list[Path] = []
    depth_frame = pd.DataFrame(depth_rows)
    fraction_frame = pd.DataFrame(fraction_rows_)
    summary_frame = pd.DataFrame(summary_rows_)

    group_fields = ["collimator", "pose", "abnormal_present", "insert_name", "insert_material", "energy_keV", "seed", "region_filter"]
    for group_key, group in depth_frame.groupby(group_fields, dropna=False):
        key_parts = dict(zip(group_fields, group_key))
        condition_name = "_".join(
            safe_name(str(key_parts[field]))
            for field in ("collimator", "pose", "abnormal_present", "insert_name", "insert_material", "energy_keV", "seed")
            if str(key_parts[field]) not in {"", "nan"}
        )
        region_filter = str(key_parts["region_filter"])
        for metric, ylabel in (("median", "median last scatter z (mm)"), ("width90", "width90 last scatter z (mm)")):
            fig, ax = plt.subplots(figsize=(10, 4.5), constrained_layout=True)
            for scatter_class in ("all", "k1", "km"):
                part = group[group["scatter_class"] == scatter_class]
                if part.empty:
                    continue
                ax.plot(part["bin_center_mm"], part[metric], label=scatter_class, linewidth=1.2)
            ax.set_xlabel(str(group["bin_axis"].iloc[0]))
            ax.set_ylabel(ylabel)
            ax.set_title(f"{condition_name} | {region_filter} | {metric}")
            ax.grid(True, alpha=0.25)
            ax.legend()
            path = plot_dir / f"{condition_name}_{safe_name(str(region_filter))}_{metric}.png"
            fig.savefig(path, dpi=150)
            plt.close(fig)
            paths.append(path)

    for group_key, group in fraction_frame.groupby(group_fields, dropna=False):
        key_parts = dict(zip(group_fields, group_key))
        condition_name = "_".join(
            safe_name(str(key_parts[field]))
            for field in ("collimator", "pose", "abnormal_present", "insert_name", "insert_material", "energy_keV", "seed")
            if str(key_parts[field]) not in {"", "nan"}
        )
        region_filter = str(key_parts["region_filter"])
        fig, ax = plt.subplots(figsize=(10, 4.5), constrained_layout=True)
        for column, label in (("fraction_k1", "k1"), ("fraction_km", "km")):
            if column in group:
                ax.plot(group["bin_center_mm"], group[column], label=label, linewidth=1.2)
        ax.set_xlabel(str(group["bin_axis"].iloc[0]))
        ax.set_ylabel("fraction by detector bin")
        ax.set_title(f"{condition_name} | {region_filter} | scatter class fraction")
        ax.grid(True, alpha=0.25)
        ax.legend()
        path = plot_dir / f"{condition_name}_{safe_name(str(region_filter))}_scatter_fraction.png"
        fig.savefig(path, dpi=150)
        plt.close(fig)
        paths.append(path)

    if not summary_frame.empty:
        fig, ax = plt.subplots(figsize=(10, 4.5), constrained_layout=True)
        grouped = summary_frame.groupby("scatter_class")["spatial_score"].median(numeric_only=True)
        grouped.reindex(SCATTER_CLASSES).plot(kind="bar", ax=ax)
        ax.set_xlabel("scatter class")
        ax.set_ylabel("median spatial score")
        ax.set_title("Spatial score by scatter class")
        ax.grid(True, axis="y", alpha=0.25)
        path = plot_dir / "spatial_score_by_scatter_class.png"
        fig.savefig(path, dpi=150)
        plt.close(fig)
        paths.append(path)
    return paths


def analyze(
    input_paths: list[Path],
    output_dir: Path,
    *,
    axis: str = "det_x",
    bin_width_mm: float = 1.0,
    lags: list[int] | None = None,
    min_bin_samples: int = 20,
    min_valid_bins: int = 3,
    max_lag_samples_per_bin: int = 1000,
    write_plot_files: bool = False,
) -> dict[str, Any]:
    if axis not in {"det_x", "det_y"}:
        raise ValueError("axis must be det_x or det_y")
    if min_bin_samples < 1:
        raise ValueError("min_bin_samples must be >= 1")
    if min_valid_bins < 2:
        raise ValueError("min_valid_bins must be >= 2")
    if max_lag_samples_per_bin < 0:
        raise ValueError("max_lag_samples_per_bin must be >= 0")
    lags = lags or [1, 2, 5, 10]
    run_files = discover_run_files(input_paths)
    if not run_files:
        raise ValueError("no run directories containing events.csv were found")

    output_dir.mkdir(parents=True, exist_ok=True)
    clean_owned_outputs(output_dir)
    depth_rows: list[dict[str, Any]] = []
    lag_rows: list[dict[str, Any]] = []
    summary_rows: list[dict[str, Any]] = []
    fraction_rows_: list[dict[str, Any]] = []
    run_manifests: list[dict[str, Any]] = []
    skipped_runs: list[dict[str, str]] = []

    for files in run_files:
        try:
            run_depth, run_lag, run_summary, run_fraction, run_manifest = analyze_run(
                files,
                axis,
                bin_width_mm,
                lags,
                min_bin_samples,
                min_valid_bins,
                max_lag_samples_per_bin,
            )
        except RunSkip as error:
            skipped_runs.append({"run_dir": files.run_dir.as_posix(), "reason": str(error)})
            continue
        depth_rows.extend(run_depth)
        lag_rows.extend(run_lag)
        summary_rows.extend(run_summary)
        fraction_rows_.extend(run_fraction)
        run_manifests.append(run_manifest)

    if not run_manifests:
        raise ValueError("no analyzable runs were found; see skipped run reasons in the error context")

    fields = output_fieldnames(lags)
    manifest_path = output_dir / "analysis_manifest.yaml"
    output_index = {
        "pixel_depth_summary_by_scatter_class": write_split_by_condition_and_class(
            output_dir,
            "pixel_depth_summary_by_scatter_class",
            depth_rows,
            fields["depth"],
        ),
        "bin_lag_distribution_metrics": write_split_by_condition_and_class(
            output_dir,
            "bin_lag_distribution_metrics",
            lag_rows,
            fields["lag"],
        ),
        "scatter_order_spatial_summary": write_split_by_condition_and_class(
            output_dir,
            "scatter_order_spatial_summary",
            summary_rows,
            fields["summary"],
        ),
        "pixel_scatter_class_fraction": write_split_by_condition(
            output_dir,
            "pixel_scatter_class_fraction",
            fraction_rows_,
            "fractions.csv",
            fields["fraction"],
        ),
    }

    plot_paths: list[Path] = []
    if write_plot_files:
        plot_paths = write_plots(output_dir, depth_rows, fraction_rows_, summary_rows)
    output_index["plots"] = [relative_path(path, output_dir) for path in plot_paths]

    manifest = {
        "analysis": "pixel_depth_by_detector_bin",
        "format_version": 3,
        "output_layout": "by_condition",
        "source_depth_definition": "last_scatter_z",
        "scatter_class_all_definition": "scatter_count_total > 0 with finite last_scatter_z",
        "input_paths": [path.as_posix() for path in input_paths],
        "output_dir": output_dir.as_posix(),
        "condition_fields": CONDITION_FIELDS,
        "provenance_fields": PROVENANCE_FIELDS,
        "axis": axis,
        "bin_width_mm": bin_width_mm,
        "lags": lags,
        "min_bin_samples": min_bin_samples,
        "min_valid_bins": min_valid_bins,
        "max_lag_samples_per_bin": max_lag_samples_per_bin,
        "lag_metric_sampling": "full" if max_lag_samples_per_bin == 0 else "deterministic_quantile_cap",
        "discovered_run_count": len(run_files),
        "analyzed_run_count": len(run_manifests),
        "skipped_run_count": len(skipped_runs),
        "skipped_runs": skipped_runs,
        "runs": run_manifests,
        "outputs": output_index,
    }
    write_yaml(manifest_path, manifest)
    return {
        "by_condition_dir": output_dir / "by_condition",
        "depth_dir": output_dir / "by_condition",
        "lag_dir": output_dir / "by_condition",
        "summary_dir": output_dir / "by_condition",
        "fraction_dir": output_dir / "by_condition",
        "outputs": output_index,
        "manifest": manifest_path,
        "plots": plot_paths,
        "discovered_run_count": len(run_files),
        "analyzed_run_count": len(run_manifests),
        "skipped_run_count": len(skipped_runs),
    }


def parse_lags(text: str) -> list[int]:
    try:
        values = [int(item.strip()) for item in text.split(",") if item.strip()]
    except ValueError as error:
        raise argparse.ArgumentTypeError("expected comma-separated integer lags") from error
    if not values:
        raise argparse.ArgumentTypeError("at least one lag is required")
    if any(value <= 0 for value in values):
        raise argparse.ArgumentTypeError("lags must be positive integers")
    return values


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input_paths", type=Path, nargs="+")
    parser.add_argument("--output-dir", type=Path, default=Path("results/analysis/pixel_depth"))
    parser.add_argument("--axis", choices=("det_x", "det_y"), default="det_x")
    parser.add_argument("--bin-width-mm", type=float, default=1.0)
    parser.add_argument("--lags", type=parse_lags, default=[1, 2, 5, 10])
    parser.add_argument("--min-bin-samples", type=int, default=20)
    parser.add_argument("--min-valid-bins", type=int, default=3)
    parser.add_argument(
        "--max-lag-samples-per-bin",
        type=int,
        default=1000,
        help="cap per-bin samples used only for lag distribution metrics; 0 keeps all samples",
    )
    parser.add_argument("--write-plots", action="store_true")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        outputs = analyze(
            args.input_paths,
            args.output_dir,
            axis=args.axis,
            bin_width_mm=args.bin_width_mm,
            lags=args.lags,
            min_bin_samples=args.min_bin_samples,
            min_valid_bins=args.min_valid_bins,
            max_lag_samples_per_bin=args.max_lag_samples_per_bin,
            write_plot_files=args.write_plots,
        )
    except Exception as error:
        print(f"pixel depth analysis error: {error}", file=sys.stderr)
        return 2
    print(f"Discovered {outputs['discovered_run_count']} run(s)")
    print(f"Analyzed {outputs['analyzed_run_count']} run(s)")
    print(f"Skipped {outputs['skipped_run_count']} run(s)")
    print(f"Depth summary dir: {outputs['depth_dir']}")
    print(f"Lag metrics dir: {outputs['lag_dir']}")
    print(f"Spatial summary dir: {outputs['summary_dir']}")
    print(f"Scatter fractions dir: {outputs['fraction_dir']}")
    print(f"Manifest: {outputs['manifest']}")
    if args.write_plots:
        print(f"Plot count: {len(outputs['plots'])}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
