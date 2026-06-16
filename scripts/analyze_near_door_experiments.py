#!/usr/bin/env python3
"""Summarize near-door MSS energy-scan run directories."""

from __future__ import annotations

import argparse
import csv
import math
import re
import statistics
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Iterable

import yaml


SCATTER_BINS = ("0", "1", "2", "3", "ge4")
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


def read_events(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8", newline="") as stream:
        reader = csv.DictReader(stream)
        if reader.fieldnames is None:
            raise ValueError(f"events CSV has no header: {path}")
        bad_fields = [field for field in reader.fieldnames if "|" in field]
        if bad_fields:
            raise ValueError(f"events CSV contains unsupported field names: {bad_fields}")
        return list(reader)


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


def scatter_bin(row: dict[str, str]) -> str:
    count = as_int(row.get("scatter_count_total"), 0)
    if count <= 0:
        return "0"
    if count == 1:
        return "1"
    if count == 2:
        return "2"
    if count == 3:
        return "3"
    return "ge4"


def channel(row: dict[str, str]) -> str:
    return "ms" if as_int(row.get("scatter_count_total"), 0) >= 2 else "single_or_zero"


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
        "seed": as_int(metadata.get("random_seed"), 0),
    }


def summarize_run(run_dir: Path) -> dict[str, Any]:
    metadata = read_yaml(run_dir / "metadata.yaml")
    events = read_events(run_dir / "events.csv")
    case = infer_case(metadata, run_dir)
    n_primary = as_int(metadata.get("n_primary"), 0)
    counts = Counter(scatter_bin(row) for row in events)
    n_total = len(events)
    n_0 = counts["0"]
    n_1 = counts["1"]
    n_2 = counts["2"]
    n_3 = counts["3"]
    n_ge4 = counts["ge4"]
    n_ms = n_2 + n_3 + n_ge4
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
        "N_detected_primary": sum(as_int(row.get("is_primary_gamma"), 0) == 1 for row in events),
        "N_detected_secondary": sum(as_int(row.get("is_primary_gamma"), 0) == 0 for row in events),
        "N_0": n_0,
        "N_1": n_1,
        "N_2": n_2,
        "N_3": n_3,
        "N_ge4": n_ge4,
        "N_ms": n_ms,
        "R_0": safe_div(n_0, n_total),
        "R_1": safe_div(n_1, n_total),
        "R_2": safe_div(n_2, n_total),
        "R_3": safe_div(n_3, n_total),
        "R_ge4": safe_div(n_ge4, n_total),
        "R_ms": safe_div(n_ms, n_total),
        "Y_0": safe_div(n_0, n_primary),
        "Y_1": safe_div(n_1, n_primary),
        "Y_ms": safe_div(n_ms, n_primary),
        "H_total": safe_div(n_total, n_primary),
        "H_1": safe_div(n_1, n_primary),
        "H_ms": safe_div(n_ms, n_primary),
        "_events": events,
    }
    return row


def scatter_order_rows(run_rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for run in run_rows:
        for bin_id in SCATTER_BINS:
            n_value = run["N_ge4"] if bin_id == "ge4" else run[f"N_{bin_id}"]
            rows.append(
                {
                    "run_id": run["run_id"],
                    "system": run["system"],
                    "pose": run["pose"],
                    "model_state": run["model_state"],
                    "energy_keV": run["energy_keV"],
                    "seed": run["seed"],
                    "scatter_order": bin_id,
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


def cnr_from_deltas(deltas: list[float]) -> float:
    if len(deltas) < 2:
        return math.nan
    std = statistics.stdev(deltas)
    if std == 0:
        return math.nan
    return mean(deltas) / std


def histogram(rows: list[dict[str, str]], x_bins: int = 20, y_bins: int = 20) -> Counter[tuple[int, int]]:
    xs = [as_float(row.get("det_x")) for row in rows]
    ys = [as_float(row.get("det_y")) for row in rows]
    clean = [(x, y) for x, y in zip(xs, ys) if not math.isnan(x) and not math.isnan(y)]
    if not clean:
        return Counter()
    x_min = min(x for x, _ in clean)
    x_max = max(x for x, _ in clean)
    y_min = min(y for _, y in clean)
    y_max = max(y for _, y in clean)
    if x_min == x_max:
        x_max = x_min + 1.0
    if y_min == y_max:
        y_max = y_min + 1.0
    hist: Counter[tuple[int, int]] = Counter()
    for x, y in clean:
        xi = min(x_bins - 1, max(0, int((x - x_min) / (x_max - x_min) * x_bins)))
        yi = min(y_bins - 1, max(0, int((y - y_min) / (y_max - y_min) * y_bins)))
        hist[(xi, yi)] += 1
    return hist


def p_pos_neg(normal_events: list[dict[str, str]], abnormal_events: list[dict[str, str]]) -> tuple[float, float]:
    normal_hist = histogram(normal_events)
    abnormal_hist = histogram(abnormal_events)
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
        delta_1 = [ab["H_1"] - norm["H_1"] for norm, ab in paired]
        delta_ms = [ab["H_ms"] - norm["H_ms"] for norm, ab in paired]
        p_values = [p_pos_neg(norm["_events"], ab["_events"]) for norm, ab in paired]
        rows.append(
            {
                "system": system,
                "pose": pose,
                "model_state": model_state,
                "energy_keV": energy,
                "seed_count": len(paired),
                "DeltaH_total": mean(delta_total),
                "DeltaH_1": mean(delta_1),
                "DeltaH_ms": mean(delta_ms),
                "CNR_total": cnr_from_deltas(delta_total),
                "CNR_1": cnr_from_deltas(delta_1),
                "CNR_ms": cnr_from_deltas(delta_ms),
                "DeltaC_ms": mean([ab["R_ms"] - norm["R_ms"] for norm, ab in paired]),
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
            "R_ms_E": mean(row["R_ms"] for row in rows),
            "Y_ms_E": mean(row["Y_ms"] for row in rows),
            "Y_1_E": mean(row["Y_1"] for row in rows),
            "CNR_total_E": vis.get("CNR_total", math.nan),
            "CNR_1_E": vis.get("CNR_1", math.nan),
            "CNR_ms_E": vis.get("CNR_ms", math.nan),
            "Gain_CNR_total_E": math.nan,
            "Gain_CNR_1_E": math.nan,
            "Gain_CNR_ms_E": math.nan,
        }
        cnr_by_system[(system, pose, model_state, energy)] = {
            "total": item["CNR_total_E"],
            "1": item["CNR_1_E"],
            "ms": item["CNR_ms_E"],
        }
        base_rows.append(item)

    for row in base_rows:
        if row["system"] != "collimated":
            continue
        open_cnr = cnr_by_system.get(("open", row["pose"], row["model_state"], row["energy_keV"]))
        if not open_cnr:
            continue
        for key, suffix in (("total", "total"), ("1", "1"), ("ms", "ms")):
            row[f"Gain_CNR_{suffix}_E"] = safe_div(
                row[f"CNR_{suffix}_E"] if suffix != "1" else row["CNR_1_E"],
                open_cnr[key],
            )
    return base_rows


def layer_attribution_rows(run_rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for run in run_rows:
        events = run["_events"]
        totals_by_k = Counter(scatter_bin(row) for row in events)
        totals_by_channel = Counter(channel(row) for row in events)
        first_by_k: Counter[tuple[str, str]] = Counter()
        last_by_k: Counter[tuple[str, str]] = Counter()
        first_by_channel: Counter[tuple[str, str]] = Counter()
        last_by_channel: Counter[tuple[str, str]] = Counter()
        for row in events:
            k = scatter_bin(row)
            ch = channel(row)
            first_layer = layer_for_region(row.get("first_scatter_region_id", "none"))
            last_layer = layer_for_region(row.get("last_scatter_region_id", "none"))
            first_by_k[(k, first_layer)] += 1
            last_by_k[(k, last_layer)] += 1
            first_by_channel[(ch, first_layer)] += 1
            last_by_channel[(ch, last_layer)] += 1
        for k in SCATTER_BINS:
            for layer_id in LAYER_IDS:
                rows.append(
                    {
                        "run_id": run["run_id"],
                        "system": run["system"],
                        "pose": run["pose"],
                        "model_state": run["model_state"],
                        "energy_keV": run["energy_keV"],
                        "seed": run["seed"],
                        "k": k,
                        "channel": "",
                        "layer_id": layer_id,
                        "first_layer_given_k": safe_div(first_by_k[(k, layer_id)], totals_by_k[k]),
                        "last_layer_given_k": safe_div(last_by_k[(k, layer_id)], totals_by_k[k]),
                        "first_layer_given_channel": "",
                        "last_layer_given_channel": "",
                    }
                )
        for ch in ("single_or_zero", "ms"):
            for layer_id in LAYER_IDS:
                rows.append(
                    {
                        "run_id": run["run_id"],
                        "system": run["system"],
                        "pose": run["pose"],
                        "model_state": run["model_state"],
                        "energy_keV": run["energy_keV"],
                        "seed": run["seed"],
                        "k": "",
                        "channel": ch,
                        "layer_id": layer_id,
                        "first_layer_given_k": "",
                        "last_layer_given_k": "",
                        "first_layer_given_channel": safe_div(
                            first_by_channel[(ch, layer_id)], totals_by_channel[ch]
                        ),
                        "last_layer_given_channel": safe_div(
                            last_by_channel[(ch, layer_id)], totals_by_channel[ch]
                        ),
                    }
                )
    return rows


def public_run_rows(run_rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [{key: value for key, value in row.items() if not key.startswith("_")} for row in run_rows]


def analyze(paths: list[Path], output_dir: Path) -> dict[str, Path]:
    run_dirs = discover_run_dirs(paths)
    if not run_dirs:
        raise ValueError("no run directories containing metadata.yaml and events.csv were found")
    run_rows = [summarize_run(path) for path in run_dirs]
    visibility = visibility_rows(run_rows)
    outputs = {
        "run_summary": output_dir / "run_summary.csv",
        "scatter_order_summary": output_dir / "scatter_order_summary.csv",
        "energy_scan_summary": output_dir / "energy_scan_summary.csv",
        "visibility_summary": output_dir / "visibility_summary.csv",
        "layer_attribution_summary": output_dir / "layer_attribution_summary.csv",
    }
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
        "N_0",
        "N_1",
        "N_2",
        "N_3",
        "N_ge4",
        "N_ms",
        "R_0",
        "R_1",
        "R_2",
        "R_3",
        "R_ge4",
        "R_ms",
        "Y_0",
        "Y_1",
        "Y_ms",
        "H_total",
        "H_1",
        "H_ms",
    ]
    write_csv(outputs["run_summary"], public_run_rows(run_rows), run_fields)
    write_csv(
        outputs["scatter_order_summary"],
        scatter_order_rows(run_rows),
        ["run_id", "system", "pose", "model_state", "energy_keV", "seed", "scatter_order", "N", "R", "Y"],
    )
    write_csv(
        outputs["energy_scan_summary"],
        energy_scan_rows(run_rows, visibility),
        [
            "system",
            "pose",
            "model_state",
            "energy_keV",
            "seed_count",
            "R_ms_E",
            "Y_ms_E",
            "Y_1_E",
            "CNR_total_E",
            "CNR_1_E",
            "CNR_ms_E",
            "Gain_CNR_total_E",
            "Gain_CNR_1_E",
            "Gain_CNR_ms_E",
        ],
    )
    write_csv(
        outputs["visibility_summary"],
        visibility,
        [
            "system",
            "pose",
            "model_state",
            "energy_keV",
            "seed_count",
            "DeltaH_total",
            "DeltaH_1",
            "DeltaH_ms",
            "CNR_total",
            "CNR_1",
            "CNR_ms",
            "DeltaC_ms",
            "P_pos",
            "P_neg",
        ],
    )
    write_csv(
        outputs["layer_attribution_summary"],
        layer_attribution_rows(run_rows),
        [
            "run_id",
            "system",
            "pose",
            "model_state",
            "energy_keV",
            "seed",
            "k",
            "channel",
            "layer_id",
            "first_layer_given_k",
            "last_layer_given_k",
            "first_layer_given_channel",
            "last_layer_given_channel",
        ],
    )
    return outputs


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
