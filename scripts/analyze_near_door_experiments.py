#!/usr/bin/env python3
"""Summarize near-door MSS energy-scan run directories."""

from __future__ import annotations

import argparse
import csv
import math
import random
import shutil
import re
import statistics
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Iterable

import yaml


SCATTER_CLASSES = ("all", "k1", "k2", "k3", "kn", "km")
RUN_SCATTER_CLASSES = ("k0", *SCATTER_CLASSES)
LAYER_IDS = (
    "door_outer_metal",
    "door_cavity",
    "door_reinforcement",
    "door_inner_metal",
    "door_trim",
    "other",
)


def read_yaml(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as stream:
        value = yaml.safe_load(stream)
    if not isinstance(value, dict):
        raise ValueError(f"metadata root must be a map: {path}")
    return value


def write_csv(path: Path, rows: list[dict[str, Any]], fieldnames: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow({field: format_value(row.get(field)) for field in fieldnames})


def format_value(value: Any) -> Any:
    if isinstance(value, float):
        if math.isnan(value):
            return "NaN"
        return f"{value:.12g}"
    return value


def nested(metadata: dict[str, Any], *keys: str, default: Any = None) -> Any:
    value: Any = metadata
    for key in keys:
        if not isinstance(value, dict) or key not in value:
            return default
        value = value[key]
    return value


def as_int(value: Any, default: int = 0) -> int:
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return default


def as_float(value: Any, default: float = math.nan) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def safe_div(numerator: float, denominator: float) -> float:
    if denominator == 0:
        return math.nan
    return numerator / denominator


def safe_name(text: str) -> str:
    return re.sub(r"[^A-Za-z0-9_.-]+", "_", text).strip("_") or "unknown"


def energy_dir_name(value: Any) -> str:
    numeric = as_int(value, 0)
    return f"E{numeric}" if numeric else "Eunknown"


def condition_dir(row: dict[str, Any], *, include_energy: bool = True) -> Path:
    path = Path(
        "by_condition",
        safe_name(str(row.get("system", "unknown"))),
        safe_name(str(row.get("pose", "unknown_pose"))),
        safe_name(str(row.get("model_state", "unknown"))),
    )
    if include_energy:
        path = path / energy_dir_name(row.get("energy_keV"))
    return path


def comparison_dir(row: dict[str, Any]) -> Path:
    return Path(
        "comparisons",
        safe_name(str(row.get("system", "unknown"))),
        safe_name(str(row.get("pose", "unknown_pose"))),
        energy_dir_name(row.get("energy_keV")),
    )


def relative_path(path: Path, base: Path) -> str:
    try:
        return path.relative_to(base).as_posix()
    except ValueError:
        return path.as_posix()


def clean_owned_outputs(output_dir: Path) -> None:
    for name in ("by_condition", "comparisons"):
        directory = output_dir / name
        if directory.exists():
            shutil.rmtree(directory)
    for name in ("analysis_manifest.yaml", "near_door_analysis_index.csv"):
        path = output_dir / name
        if path.exists():
            path.unlink()


class NumericSummary:
    def __init__(self, sample_limit: int = 10000) -> None:
        self.count = 0
        self.mean = 0.0
        self.m2 = 0.0
        self.min = math.nan
        self.max = math.nan
        self.sample_limit = sample_limit
        self.sample: list[float] = []
        self.rng = random.Random(12345)

    def add(self, value: Any) -> None:
        numeric = as_float(value)
        if math.isnan(numeric):
            return
        self.count += 1
        if self.count == 1:
            self.mean = numeric
            self.min = numeric
            self.max = numeric
        else:
            delta = numeric - self.mean
            self.mean += delta / self.count
            self.m2 += delta * (numeric - self.mean)
            self.min = min(self.min, numeric)
            self.max = max(self.max, numeric)
        if len(self.sample) < self.sample_limit:
            self.sample.append(numeric)
        elif self.sample_limit > 0:
            index = self.rng.randrange(self.count)
            if index < self.sample_limit:
                self.sample[index] = numeric

    def as_fields(self) -> dict[str, float | int]:
        if self.count == 0:
            return {
                "count": 0,
                "mean": math.nan,
                "std": math.nan,
                "min": math.nan,
                "q25": math.nan,
                "median": math.nan,
                "q75": math.nan,
                "max": math.nan,
            }
        sample = sorted(self.sample)
        return {
            "count": self.count,
            "mean": self.mean,
            "std": math.sqrt(self.m2 / (self.count - 1)) if self.count > 1 else math.nan,
            "min": self.min,
            "q25": quantile(sample, 0.25),
            "median": quantile(sample, 0.5),
            "q75": quantile(sample, 0.75),
            "max": self.max,
        }


def scatter_count(row: dict[str, str]) -> int:
    return as_int(row.get("scatter_count_total"), 0)


def in_scatter_class(row: dict[str, str], scatter_class: str) -> bool:
    count = scatter_count(row)
    if scatter_class == "k0":
        return count <= 0
    if scatter_class == "all":
        return True
    if scatter_class == "k1":
        return count == 1
    if scatter_class == "k2":
        return count == 2
    if scatter_class == "k3":
        return count == 3
    if scatter_class == "kn":
        return count >= 4
    if scatter_class == "km":
        return count >= 2
    raise ValueError(f"unknown scatter class: {scatter_class}")


def channel(row: dict[str, str]) -> str:
    return "km" if scatter_count(row) >= 2 else "single_or_zero"


def layer_for_region(region_id: str) -> str:
    if region_id in {"near_door_outer_metal", "far_door_outer_metal"}:
        return "door_outer_metal"
    if region_id in {"near_door_cavity_air", "far_door_cavity_air", "target"}:
        return "door_cavity"
    if region_id in {"near_door_reinforcement", "far_door_reinforcement"}:
        return "door_reinforcement"
    if region_id in {"near_door_inner_metal", "far_door_inner_metal"}:
        return "door_inner_metal"
    if region_id in {"near_door_trim", "far_door_trim"}:
        return "door_trim"
    return "other"


def discover_run_dirs(paths: Iterable[Path]) -> list[Path]:
    run_dirs: list[Path] = []
    seen: set[Path] = set()
    for path in paths:
        if path.is_file():
            candidate = path.parent
            if path.name != "metadata.yaml":
                continue
            metadata_files = [path]
        else:
            metadata_files = list(path.rglob("metadata.yaml")) if path.exists() else []
            if (path / "metadata.yaml").is_file():
                metadata_files = [path / "metadata.yaml"]
        for metadata_path in metadata_files:
            candidate = metadata_path.parent.resolve()
            if candidate not in seen and (candidate / "events.csv").is_file():
                seen.add(candidate)
                run_dirs.append(candidate)
    return sorted(run_dirs)


CASE_RE = re.compile(
    r"^near_door_(?P<system>open|collimated)_(?P<pose>pose[RC])_"
    r"(?P<model_state>normal|cavityPE|cavityFlour|cavityW)_E(?P<energy>\d+)_seed(?P<seed>-?\d+)$"
)


def infer_case(metadata: dict[str, Any], run_dir: Path) -> dict[str, Any]:
    case_id = nested(metadata, "diagnostics", "case_id", default="")
    merge_condition = metadata.get("merge_condition")
    if isinstance(merge_condition, dict):
        return {
            "case_id": case_id or metadata.get("run_id", run_dir.name),
            "system": str(merge_condition.get("system", "unknown")),
            "pose": str(merge_condition.get("pose", metadata.get("pose_id", "unknown_pose"))),
            "model_state": str(merge_condition.get("model_state", "unknown")),
            "energy_keV": as_int(merge_condition.get("energy_keV"), 0),
            "seed": "merged",
        }

    match = CASE_RE.match(case_id or "")
    if match:
        return {
            "case_id": case_id,
            "system": match.group("system"),
            "pose": match.group("pose"),
            "model_state": match.group("model_state"),
            "energy_keV": int(match.group("energy")),
            "seed": int(match.group("seed")),
        }

    model_type = str(metadata.get("model_type", "normal"))
    abnormal_material = str(metadata.get("abnormal_material", "G4_POLYETHYLENE"))
    if model_type == "normal":
        model_state = "normal"
    elif abnormal_material == "Vehicle_Flour":
        model_state = "cavityFlour"
    elif abnormal_material == "G4_W":
        model_state = "cavityW"
    else:
        model_state = "cavityPE"

    system = "collimated" if bool(nested(metadata, "collimator", "enable", default=True)) else "open"
    return {
        "case_id": case_id or run_dir.name,
        "system": system,
        "pose": str(metadata.get("pose_id", "unknown_pose")),
        "model_state": model_state,
        "energy_keV": as_int(nested(metadata, "source", "mono_energy_keV", default=0)),
        "seed": as_int(metadata.get("random_seed"), 0)
        if metadata.get("random_seed") is not None
        else "merged",
    }


def summarize_run(run_dir: Path) -> dict[str, Any]:
    metadata = read_yaml(run_dir / "metadata.yaml")
    case = infer_case(metadata, run_dir)
    n_primary = as_int(metadata.get("n_primary"), 0)
    events_path = run_dir / "events.csv"
    counts = {scatter_class: 0 for scatter_class in RUN_SCATTER_CLASSES}
    n_total = 0
    n_primary_detected = 0
    n_secondary_detected = 0
    energy_stats = {scatter_class: NumericSummary() for scatter_class in SCATTER_CLASSES}
    compton_stats = {scatter_class: NumericSummary() for scatter_class in SCATTER_CLASSES}
    rayleigh_stats = {scatter_class: NumericSummary() for scatter_class in SCATTER_CLASSES}
    region_counts: Counter[tuple[str, str, str]] = Counter()
    layer_counts: Counter[tuple[str, str, str]] = Counter()
    channel_layer_counts: Counter[tuple[str, str, str]] = Counter()
    channel_totals: Counter[str] = Counter()
    detector_hist: Counter[tuple[int, int]] = Counter()

    with events_path.open("r", encoding="utf-8", newline="") as stream:
        reader = csv.DictReader(stream)
        if reader.fieldnames is None:
            raise ValueError(f"events CSV has no header: {events_path}")
        bad_fields = [field for field in reader.fieldnames if "|" in field]
        if bad_fields:
            raise ValueError(f"events CSV contains unsupported field names: {bad_fields}")
        for event_row in reader:
            n_total += 1
            if as_int(event_row.get("is_primary_gamma"), 0) == 1:
                n_primary_detected += 1
            else:
                n_secondary_detected += 1
            hist_bin = detector_histogram_bin(event_row, metadata)
            if hist_bin is not None:
                detector_hist[hist_bin] += 1
            for scatter_class in RUN_SCATTER_CLASSES:
                if in_scatter_class(event_row, scatter_class):
                    counts[scatter_class] += 1
            for scatter_class in SCATTER_CLASSES:
                if not in_scatter_class(event_row, scatter_class):
                    continue
                energy_stats[scatter_class].add(event_row.get("det_energy"))
                compton_stats[scatter_class].add(event_row.get("compton_count"))
                rayleigh_stats[scatter_class].add(event_row.get("rayleigh_count"))
                for stage, field in (
                    ("first", "first_scatter_region_id"),
                    ("last", "last_scatter_region_id"),
                ):
                    region_id = str(event_row.get(field, "none") or "none")
                    region_counts[(scatter_class, stage, region_id)] += 1
                first_layer = layer_for_region(event_row.get("first_scatter_region_id", "none"))
                last_layer = layer_for_region(event_row.get("last_scatter_region_id", "none"))
                layer_counts[(scatter_class, "first", first_layer)] += 1
                layer_counts[(scatter_class, "last", last_layer)] += 1
            ch = channel(event_row)
            channel_totals[ch] += 1
            channel_layer_counts[(ch, "first", layer_for_region(event_row.get("first_scatter_region_id", "none")))] += 1
            channel_layer_counts[(ch, "last", layer_for_region(event_row.get("last_scatter_region_id", "none")))] += 1

    row = {
        "run_dir": str(run_dir),
        "run_id": metadata.get("run_id", run_dir.name),
        "case_id": case["case_id"],
        "system": case["system"],
        "pose": case["pose"],
        "model_state": case["model_state"],
        "energy_keV": case["energy_keV"],
        "seed": case["seed"],
        "n_primary": n_primary,
        "collimator_enable": nested(metadata, "collimator", "enable", default=""),
        "N_detected_total": n_total,
        "N_detected_primary": n_primary_detected,
        "N_detected_secondary": n_secondary_detected,
        "H_total": safe_div(n_total, n_primary),
        "_detector_hist": detector_hist,
        "_energy_stats": energy_stats,
        "_compton_stats": compton_stats,
        "_rayleigh_stats": rayleigh_stats,
        "_region_counts": region_counts,
        "_layer_counts": layer_counts,
        "_channel_layer_counts": channel_layer_counts,
        "_channel_totals": channel_totals,
    }
    for scatter_class in RUN_SCATTER_CLASSES:
        n_value = counts[scatter_class]
        row[f"N_{scatter_class}"] = n_value
        row[f"R_{scatter_class}"] = safe_div(n_value, n_total)
        row[f"Y_{scatter_class}"] = safe_div(n_value, n_primary)
    row["H_k1"] = row["Y_k1"]
    row["H_km"] = row["Y_km"]
    return row


def scatter_order_rows(run_rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for run in run_rows:
        for scatter_class in SCATTER_CLASSES:
            n_value = run[f"N_{scatter_class}"]
            rows.append(
                {
                    "run_id": run["run_id"],
                    "system": run["system"],
                    "pose": run["pose"],
                    "model_state": run["model_state"],
                    "energy_keV": run["energy_keV"],
                    "seed": run["seed"],
                    "scatter_class": scatter_class,
                    "N": n_value,
                    "R": safe_div(n_value, run["N_detected_total"]),
                    "Y": safe_div(n_value, run["n_primary"]),
                }
            )
    return rows


def mean(values: Iterable[float]) -> float:
    clean = [value for value in values if not math.isnan(value)]
    if not clean:
        return math.nan
    return sum(clean) / len(clean)


def quantile(sorted_values: list[float], probability: float) -> float:
    if not sorted_values:
        return math.nan
    if len(sorted_values) == 1:
        return sorted_values[0]
    position = (len(sorted_values) - 1) * probability
    lower = math.floor(position)
    upper = math.ceil(position)
    if lower == upper:
        return sorted_values[int(position)]
    weight = position - lower
    return sorted_values[lower] * (1.0 - weight) + sorted_values[upper] * weight


def condition_fields(run: dict[str, Any]) -> dict[str, Any]:
    return {
        "run_id": run["run_id"],
        "system": run["system"],
        "pose": run["pose"],
        "model_state": run["model_state"],
        "energy_keV": run["energy_keV"],
        "seed": run["seed"],
    }


def cnr_from_deltas(deltas: list[float]) -> float:
    if len(deltas) < 2:
        return math.nan
    std = statistics.stdev(deltas)
    if std == 0:
        return math.nan
    return mean(deltas) / std


def detector_histogram_bin(
    row: dict[str, str],
    metadata: dict[str, Any],
    x_bins: int = 20,
    y_bins: int = 20,
) -> tuple[int, int] | None:
    detector = metadata.get("detector", {})
    if not isinstance(detector, dict):
        return None
    x_range = detector.get("actual_x_range_mm") or detector.get("detector_x_range_zero_mm")
    y_range = detector.get("actual_y_range_mm") or detector.get("detector_y_range_zero_mm")
    if not (
        isinstance(x_range, list)
        and len(x_range) == 2
        and isinstance(y_range, list)
        and len(y_range) == 2
    ):
        return None
    x_min, x_max = as_float(x_range[0]), as_float(x_range[1])
    y_min, y_max = as_float(y_range[0]), as_float(y_range[1])
    x_value, y_value = as_float(row.get("det_x")), as_float(row.get("det_y"))
    if (
        math.isnan(x_min)
        or math.isnan(x_max)
        or math.isnan(y_min)
        or math.isnan(y_max)
        or math.isnan(x_value)
        or math.isnan(y_value)
        or x_min >= x_max
        or y_min >= y_max
    ):
        return None
    x_index = min(x_bins - 1, max(0, int((x_value - x_min) / (x_max - x_min) * x_bins)))
    y_index = min(y_bins - 1, max(0, int((y_value - y_min) / (y_max - y_min) * y_bins)))
    return x_index, y_index


def p_pos_neg(normal_hist: Counter[tuple[int, int]], abnormal_hist: Counter[tuple[int, int]]) -> tuple[float, float]:
    keys = set(normal_hist) | set(abnormal_hist)
    if not keys:
        return math.nan, math.nan
    positive = 0
    negative = 0
    nonzero = 0
    for key in keys:
        delta = abnormal_hist[key] - normal_hist[key]
        if delta == 0:
            continue
        nonzero += 1
        if delta > 0:
            positive += 1
        else:
            negative += 1
    return safe_div(positive, nonzero), safe_div(negative, nonzero)


def visibility_rows(run_rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    by_key = {(r["system"], r["pose"], r["energy_keV"], r["model_state"], r["seed"]): r for r in run_rows}
    abnormal_states = sorted({r["model_state"] for r in run_rows if r["model_state"] != "normal"})
    rows: list[dict[str, Any]] = []
    for system, pose, energy, model_state in sorted(
        {
            (r["system"], r["pose"], r["energy_keV"], state)
            for r in run_rows
            for state in abnormal_states
        }
    ):
        paired: list[tuple[dict[str, Any], dict[str, Any]]] = []
        for seed in sorted({r["seed"] for r in run_rows}):
            normal = by_key.get((system, pose, energy, "normal", seed))
            abnormal = by_key.get((system, pose, energy, model_state, seed))
            if normal is not None and abnormal is not None:
                paired.append((normal, abnormal))
        if not paired:
            continue
        delta_total = [ab["H_total"] - norm["H_total"] for norm, ab in paired]
        delta_1 = [ab["H_k1"] - norm["H_k1"] for norm, ab in paired]
        delta_km = [ab["H_km"] - norm["H_km"] for norm, ab in paired]
        p_values = [p_pos_neg(norm["_detector_hist"], ab["_detector_hist"]) for norm, ab in paired]
        rows.append(
            {
                "system": system,
                "pose": pose,
                "model_state": model_state,
                "energy_keV": energy,
                "seed_count": len(paired),
                "DeltaH_total": mean(delta_total),
                "DeltaH_1": mean(delta_1),
                "DeltaH_km": mean(delta_km),
                "CNR_total": cnr_from_deltas(delta_total),
                "CNR_1": cnr_from_deltas(delta_1),
                "CNR_km": cnr_from_deltas(delta_km),
                "DeltaC_km": mean([ab["R_km"] - norm["R_km"] for norm, ab in paired]),
                "P_pos": mean([value[0] for value in p_values]),
                "P_neg": mean([value[1] for value in p_values]),
            }
        )
    return rows


def energy_scan_rows(run_rows: list[dict[str, Any]], visibility: list[dict[str, Any]]) -> list[dict[str, Any]]:
    vis_by_key = {
        (row["system"], row["pose"], row["model_state"], row["energy_keV"]): row for row in visibility
    }
    grouped: dict[tuple[str, str, str, int], list[dict[str, Any]]] = defaultdict(list)
    for row in run_rows:
        grouped[(row["system"], row["pose"], row["model_state"], row["energy_keV"])].append(row)

    base_rows: list[dict[str, Any]] = []
    cnr_by_system: dict[tuple[str, str, str, int], dict[str, float]] = {}
    for (system, pose, model_state, energy), rows in sorted(grouped.items()):
        vis = vis_by_key.get((system, pose, model_state, energy), {})
        item = {
            "system": system,
            "pose": pose,
            "model_state": model_state,
            "energy_keV": energy,
            "seed_count": len(rows),
            "R_km_E": mean(row["R_km"] for row in rows),
            "Y_km_E": mean(row["Y_km"] for row in rows),
            "Y_k1_E": mean(row["Y_k1"] for row in rows),
            "CNR_total_E": vis.get("CNR_total", math.nan),
            "CNR_1_E": vis.get("CNR_1", math.nan),
            "CNR_km_E": vis.get("CNR_km", math.nan),
            "Gain_CNR_total_E": math.nan,
            "Gain_CNR_1_E": math.nan,
            "Gain_CNR_km_E": math.nan,
        }
        cnr_by_system[(system, pose, model_state, energy)] = {
            "total": item["CNR_total_E"],
            "1": item["CNR_1_E"],
            "km": item["CNR_km_E"],
        }
        base_rows.append(item)

    for row in base_rows:
        if row["system"] != "collimated":
            continue
        open_cnr = cnr_by_system.get(("open", row["pose"], row["model_state"], row["energy_keV"]))
        if not open_cnr:
            continue
        for key, suffix in (("total", "total"), ("1", "1"), ("km", "km")):
            row[f"Gain_CNR_{suffix}_E"] = safe_div(
                row[f"CNR_{suffix}_E"] if suffix != "1" else row["CNR_1_E"],
                open_cnr[key],
            )
    return base_rows


def det_energy_rows(run_rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for run in run_rows:
        for scatter_class in SCATTER_CLASSES:
            stats = run["_energy_stats"][scatter_class].as_fields()
            rows.append(
                {
                    **condition_fields(run),
                    "scatter_class": scatter_class,
                    "count": stats["count"],
                    "det_energy_mean": stats["mean"],
                    "det_energy_std": stats["std"],
                    "det_energy_min": stats["min"],
                    "det_energy_q25": stats["q25"],
                    "det_energy_median": stats["median"],
                    "det_energy_q75": stats["q75"],
                    "det_energy_max": stats["max"],
                }
            )
    return rows


def process_count_rows(run_rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for run in run_rows:
        for scatter_class in SCATTER_CLASSES:
            compton = run["_compton_stats"][scatter_class].as_fields()
            rayleigh = run["_rayleigh_stats"][scatter_class].as_fields()
            rows.append(
                {
                    **condition_fields(run),
                    "scatter_class": scatter_class,
                    "count": run[f"N_{scatter_class}"],
                    "compton_count_mean": compton["mean"],
                    "compton_count_median": compton["median"],
                    "compton_count_max": compton["max"],
                    "rayleigh_count_mean": rayleigh["mean"],
                    "rayleigh_count_median": rayleigh["median"],
                    "rayleigh_count_max": rayleigh["max"],
                }
            )
    return rows


def region_attribution_rows(run_rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for run in run_rows:
        region_counts = run["_region_counts"]
        for scatter_class in SCATTER_CLASSES:
            total = run[f"N_{scatter_class}"]
            for stage in ("first", "last"):
                stage_items = [
                    (region_id, n_value)
                    for (class_id, stage_id, region_id), n_value in region_counts.items()
                    if class_id == scatter_class and stage_id == stage
                ]
                for region_id, n_value in sorted(stage_items):
                    rows.append(
                        {
                            **condition_fields(run),
                            "scatter_class": scatter_class,
                            "scatter_stage": stage,
                            "region_id": region_id,
                            "N": n_value,
                            "fraction_given_class": safe_div(n_value, total),
                        }
                    )
    return rows


def layer_attribution_rows(run_rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for run in run_rows:
        totals_by_class = {scatter_class: run[f"N_{scatter_class}"] for scatter_class in SCATTER_CLASSES}
        totals_by_channel = run["_channel_totals"]
        layer_counts = run["_layer_counts"]
        channel_layer_counts = run["_channel_layer_counts"]
        for scatter_class in SCATTER_CLASSES:
            for layer_id in LAYER_IDS:
                rows.append(
                    {
                        **condition_fields(run),
                        "scatter_class": scatter_class,
                        "channel": "",
                        "layer_id": layer_id,
                        "first_layer_given_class": safe_div(layer_counts[(scatter_class, "first", layer_id)], totals_by_class[scatter_class]),
                        "last_layer_given_class": safe_div(layer_counts[(scatter_class, "last", layer_id)], totals_by_class[scatter_class]),
                        "first_layer_given_channel": "",
                        "last_layer_given_channel": "",
                    }
                )
        for ch in ("single_or_zero", "km"):
            for layer_id in LAYER_IDS:
                rows.append(
                    {
                        **condition_fields(run),
                        "scatter_class": "",
                        "channel": ch,
                        "layer_id": layer_id,
                        "first_layer_given_class": "",
                        "last_layer_given_class": "",
                        "first_layer_given_channel": safe_div(
                            channel_layer_counts[(ch, "first", layer_id)], totals_by_channel[ch]
                        ),
                        "last_layer_given_channel": safe_div(
                            channel_layer_counts[(ch, "last", layer_id)], totals_by_channel[ch]
                        ),
                    }
                )
    return rows


def public_run_rows(run_rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [{key: value for key, value in row.items() if not key.startswith("_")} for row in run_rows]


def write_yaml(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as stream:
        yaml.safe_dump(data, stream, sort_keys=False, allow_unicode=False)


def write_by_condition_energy(
    output_dir: Path,
    table_name: str,
    rows: list[dict[str, Any]],
    fieldnames: list[str],
) -> list[dict[str, Any]]:
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        grouped[condition_dir(row, include_energy=True).as_posix()].append(row)
    index_rows: list[dict[str, Any]] = []
    for rel_dir_text, group_rows in sorted(grouped.items()):
        path = output_dir / rel_dir_text / f"{table_name}.csv"
        write_csv(path, group_rows, fieldnames)
        first = group_rows[0]
        index_rows.append(
            {
                "table": table_name,
                "system": first.get("system"),
                "pose": first.get("pose"),
                "model_state": first.get("model_state"),
                "energy_keV": first.get("energy_keV"),
                "path": relative_path(path, output_dir),
                "row_count": len(group_rows),
            }
        )
    return index_rows


def write_by_condition(
    output_dir: Path,
    table_name: str,
    rows: list[dict[str, Any]],
    fieldnames: list[str],
) -> list[dict[str, Any]]:
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        grouped[condition_dir(row, include_energy=False).as_posix()].append(row)
    index_rows: list[dict[str, Any]] = []
    for rel_dir_text, group_rows in sorted(grouped.items()):
        path = output_dir / rel_dir_text / f"{table_name}.csv"
        write_csv(path, group_rows, fieldnames)
        first = group_rows[0]
        index_rows.append(
            {
                "table": table_name,
                "system": first.get("system"),
                "pose": first.get("pose"),
                "model_state": first.get("model_state"),
                "energy_keV": "",
                "path": relative_path(path, output_dir),
                "row_count": len(group_rows),
            }
        )
    return index_rows


def write_by_comparison(
    output_dir: Path,
    table_name: str,
    rows: list[dict[str, Any]],
    fieldnames: list[str],
) -> list[dict[str, Any]]:
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        grouped[comparison_dir(row).as_posix()].append(row)
    index_rows: list[dict[str, Any]] = []
    for rel_dir_text, group_rows in sorted(grouped.items()):
        path = output_dir / rel_dir_text / f"{table_name}.csv"
        write_csv(path, group_rows, fieldnames)
        first = group_rows[0]
        index_rows.append(
            {
                "table": table_name,
                "system": first.get("system"),
                "pose": first.get("pose"),
                "model_state": "comparison",
                "energy_keV": first.get("energy_keV"),
                "path": relative_path(path, output_dir),
                "row_count": len(group_rows),
            }
        )
    return index_rows


def analyze(paths: list[Path], output_dir: Path) -> dict[str, Path]:
    run_dirs = discover_run_dirs(paths)
    if not run_dirs:
        raise ValueError("no run directories containing metadata.yaml and events.csv were found")
    output_dir.mkdir(parents=True, exist_ok=True)
    clean_owned_outputs(output_dir)
    run_rows = [summarize_run(path) for path in run_dirs]
    visibility = visibility_rows(run_rows)
    run_fields = [
        "run_dir",
        "run_id",
        "case_id",
        "system",
        "pose",
        "model_state",
        "energy_keV",
        "seed",
        "n_primary",
        "collimator_enable",
        "N_detected_total",
        "N_detected_primary",
        "N_detected_secondary",
        "N_k0",
        "N_all",
        "N_k1",
        "N_k2",
        "N_k3",
        "N_kn",
        "N_km",
        "R_k0",
        "R_all",
        "R_k1",
        "R_k2",
        "R_k3",
        "R_kn",
        "R_km",
        "Y_k0",
        "Y_all",
        "Y_k1",
        "Y_k2",
        "Y_k3",
        "Y_kn",
        "Y_km",
        "H_total",
        "H_k1",
        "H_km",
    ]
    scatter_order_fields = [
        "run_id",
        "system",
        "pose",
        "model_state",
        "energy_keV",
        "seed",
        "scatter_class",
        "N",
        "R",
        "Y",
    ]
    det_energy_fields = [
        "run_id",
        "system",
        "pose",
        "model_state",
        "energy_keV",
        "seed",
        "scatter_class",
        "count",
        "det_energy_mean",
        "det_energy_std",
        "det_energy_min",
        "det_energy_q25",
        "det_energy_median",
        "det_energy_q75",
        "det_energy_max",
    ]
    process_fields = [
        "run_id",
        "system",
        "pose",
        "model_state",
        "energy_keV",
        "seed",
        "scatter_class",
        "count",
        "compton_count_mean",
        "compton_count_median",
        "compton_count_max",
        "rayleigh_count_mean",
        "rayleigh_count_median",
        "rayleigh_count_max",
    ]
    region_fields = [
        "run_id",
        "system",
        "pose",
        "model_state",
        "energy_keV",
        "seed",
        "scatter_class",
        "scatter_stage",
        "region_id",
        "N",
        "fraction_given_class",
    ]
    energy_scan_fields = [
        "system",
        "pose",
        "model_state",
        "energy_keV",
        "seed_count",
        "R_km_E",
        "Y_km_E",
        "Y_k1_E",
        "CNR_total_E",
        "CNR_1_E",
        "CNR_km_E",
        "Gain_CNR_total_E",
        "Gain_CNR_1_E",
        "Gain_CNR_km_E",
    ]
    visibility_fields = [
        "system",
        "pose",
        "model_state",
        "energy_keV",
        "seed_count",
        "DeltaH_total",
        "DeltaH_1",
        "DeltaH_km",
        "CNR_total",
        "CNR_1",
        "CNR_km",
        "DeltaC_km",
        "P_pos",
        "P_neg",
    ]
    layer_fields = [
        "run_id",
        "system",
        "pose",
        "model_state",
        "energy_keV",
        "seed",
        "scatter_class",
        "channel",
        "layer_id",
        "first_layer_given_class",
        "last_layer_given_class",
        "first_layer_given_channel",
        "last_layer_given_channel",
    ]

    index_rows: list[dict[str, Any]] = []
    index_rows.extend(write_by_condition_energy(output_dir, "run_summary", public_run_rows(run_rows), run_fields))
    index_rows.extend(write_by_condition_energy(output_dir, "scatter_order_summary", scatter_order_rows(run_rows), scatter_order_fields))
    index_rows.extend(write_by_condition_energy(output_dir, "det_energy_summary", det_energy_rows(run_rows), det_energy_fields))
    index_rows.extend(write_by_condition_energy(output_dir, "process_count_summary", process_count_rows(run_rows), process_fields))
    index_rows.extend(write_by_condition_energy(output_dir, "region_attribution_summary", region_attribution_rows(run_rows), region_fields))
    index_rows.extend(write_by_condition_energy(output_dir, "layer_attribution_summary", layer_attribution_rows(run_rows), layer_fields))
    index_rows.extend(write_by_condition(output_dir, "energy_scan_summary", energy_scan_rows(run_rows, visibility), energy_scan_fields))
    index_rows.extend(write_by_comparison(output_dir, "visibility_summary", visibility, visibility_fields))

    index_path = output_dir / "near_door_analysis_index.csv"
    write_csv(
        index_path,
        index_rows,
        ["table", "system", "pose", "model_state", "energy_keV", "path", "row_count"],
    )
    manifest_path = output_dir / "analysis_manifest.yaml"
    write_yaml(
        manifest_path,
        {
            "analysis": "near_door_scatter_order",
            "format_version": 2,
            "output_layout": "by_condition",
            "input_paths": [path.as_posix() for path in paths],
            "output_dir": output_dir.as_posix(),
            "discovered_run_count": len(run_dirs),
            "analyzed_run_count": len(run_rows),
            "scatter_classes": list(SCATTER_CLASSES),
            "scatter_class_definitions": {
                "all": "all detected hits",
                "k1": "scatter_count_total == 1",
                "k2": "scatter_count_total == 2",
                "k3": "scatter_count_total == 3",
                "kn": "scatter_count_total >= 4",
                "km": "scatter_count_total >= 2",
            },
            "outputs": index_rows,
        },
    )
    return {
        "manifest": manifest_path,
        "index": index_path,
        "by_condition_dir": output_dir / "by_condition",
        "comparisons_dir": output_dir / "comparisons",
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("run_dirs", type=Path, nargs="+")
    parser.add_argument("--output-dir", type=Path, default=Path("results/analysis/near_door"))
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    outputs = analyze(args.run_dirs, args.output_dir)
    print(f"Analyzed near-door runs into {args.output_dir}")
    for name, path in outputs.items():
        print(f"{name}: {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
