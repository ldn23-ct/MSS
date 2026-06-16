#!/usr/bin/env python3
"""Plot detector-x 1D bin-count responses from MSS events.csv files."""

from __future__ import annotations

import argparse
import csv
import math
import re
import sys
from collections.abc import Iterable
from pathlib import Path
from typing import Any

import yaml


VALID_CHANNELS = ("all", "k0", "k1", "k2", "k3", "k_ge4", "ms", "single_or_zero")
SYSTEM_ORDER = ("open", "collimated")
PREFERRED_STATE_ORDER = (
    ("poseR", "normal", ""),
    ("poseC", "normal", ""),
    ("poseC", "cavityPE", "G4_POLYETHYLENE"),
    ("poseC", "cavityFlour", "Vehicle_Flour"),
)
CASE_RE = re.compile(
    r"^near_door_(?P<system>open|collimated)_(?P<pose>[^_]+)_"
    r"(?P<model_state>[^_]+)_E(?P<energy>\d+)_seed(?P<seed>-?\d+)$"
)


def read_yaml(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as stream:
        value = yaml.safe_load(stream)
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


def as_float(value: Any) -> float:
    try:
        return float(value)
    except (TypeError, ValueError) as error:
        raise ValueError(f"expected numeric value, got {value!r}") from error


def as_int(value: Any, default: int = 0) -> int:
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return default


def format_value(value: Any) -> Any:
    if isinstance(value, float):
        if math.isnan(value):
            return "NaN"
        return f"{value:.12g}"
    return value


def discover_run_dirs(paths: Iterable[Path]) -> list[Path]:
    run_dirs: list[Path] = []
    seen: set[Path] = set()
    for path in paths:
        if path.is_file():
            metadata_files = [path] if path.name == "metadata.yaml" else []
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


def parse_channels(text: str) -> list[str]:
    channels = [item.strip() for item in text.split(",") if item.strip()]
    if not channels:
        raise argparse.ArgumentTypeError("at least one channel is required")
    unknown = [channel for channel in channels if channel not in VALID_CHANNELS]
    if unknown:
        raise argparse.ArgumentTypeError(
            "unknown channel(s): " + ", ".join(unknown) + "; valid channels: " + ", ".join(VALID_CHANNELS)
        )
    return channels


def parse_int_list(text: str) -> list[int]:
    try:
        values = [int(item.strip()) for item in text.split(",") if item.strip()]
    except ValueError as error:
        raise argparse.ArgumentTypeError("expected comma-separated integers") from error
    if not values:
        raise argparse.ArgumentTypeError("at least one value is required")
    return values


def channel_accepts(channel: str, scatter_count: int) -> bool:
    if channel == "all":
        return True
    if channel == "k0":
        return scatter_count == 0
    if channel == "k1":
        return scatter_count == 1
    if channel == "k2":
        return scatter_count == 2
    if channel == "k3":
        return scatter_count == 3
    if channel == "k_ge4":
        return scatter_count >= 4
    if channel == "ms":
        return scatter_count >= 2
    if channel == "single_or_zero":
        return scatter_count <= 1
    raise ValueError(f"unsupported channel: {channel}")


def detector_x_range(metadata: dict[str, Any], run_dir: Path) -> tuple[float, float]:
    values = nested(metadata, "detector", "actual_x_range_mm")
    if not isinstance(values, list) or len(values) != 2:
        raise ValueError(f"metadata detector.actual_x_range_mm is required: {run_dir / 'metadata.yaml'}")
    x_min = as_float(values[0])
    x_max = as_float(values[1])
    if not x_min < x_max:
        raise ValueError(f"detector.actual_x_range_mm must have min < max: {run_dir / 'metadata.yaml'}")
    return x_min, x_max


def bin_edges(x_min: float, x_max: float, bin_width: float) -> list[tuple[float, float]]:
    if bin_width <= 0:
        raise ValueError("bin_width_mm must be > 0")
    count = int(math.ceil((x_max - x_min) / bin_width))
    if count <= 0:
        raise ValueError("detector x range produced no bins")
    edges: list[tuple[float, float]] = []
    for index in range(count):
        left = x_min + index * bin_width
        right = min(x_min + (index + 1) * bin_width, x_max)
        edges.append((left, right))
    return edges


def bin_index_for_x(x: float, x_min: float, x_max: float, bin_width: float, bin_count: int) -> int | None:
    if x < x_min or x > x_max:
        return None
    if x == x_max:
        return bin_count - 1
    index = int(math.floor((x - x_min) / bin_width))
    if index < 0 or index >= bin_count:
        return None
    return index


def case_info(metadata: dict[str, Any], run_dir: Path) -> dict[str, Any]:
    case_id = nested(metadata, "diagnostics", "case_id", default="")
    match = CASE_RE.match(case_id or "")
    if match:
        system = match.group("system")
        pose = match.group("pose")
        model_state = match.group("model_state")
        energy = int(match.group("energy"))
        seed = int(match.group("seed"))
    else:
        system = "collimated" if bool(nested(metadata, "collimator", "enable", default=True)) else "open"
        pose = str(metadata.get("pose_id", "unknown_pose"))
        model_state = model_state_from_metadata(metadata)
        energy = as_int(nested(metadata, "source", "mono_energy_keV", default=0))
        seed = as_int(metadata.get("random_seed"), 0)
    return {
        "run_dir": str(run_dir),
        "run_id": metadata.get("run_id", run_dir.name),
        "case_id": case_id or run_dir.name,
        "system": system,
        "pose": pose,
        "pose_id": metadata.get("pose_id", ""),
        "model_type": metadata.get("model_type", ""),
        "abnormal_material": metadata.get("abnormal_material"),
        "model_state": model_state,
        "energy_keV": energy,
        "seed": seed,
        "seed_count": 1,
    }


def model_state_from_metadata(metadata: dict[str, Any]) -> str:
    model_type = str(metadata.get("model_type", "normal"))
    material = metadata.get("abnormal_material")
    if model_type == "normal":
        return "normal"
    if material == "Vehicle_Flour":
        return "cavityFlour"
    if material == "G4_W":
        return "cavityW"
    return "cavityPE"


def aggregate_run(
    run_dir: Path,
    channels: list[str],
    bin_width_mm: float,
) -> tuple[list[dict[str, Any]], dict[str, list[int]]]:
    metadata = read_yaml(run_dir / "metadata.yaml")
    x_min, x_max = detector_x_range(metadata, run_dir)
    edges = bin_edges(x_min, x_max, bin_width_mm)
    counts = {channel: [0] * len(edges) for channel in channels}

    events_path = run_dir / "events.csv"
    with events_path.open("r", encoding="utf-8", newline="") as stream:
        reader = csv.DictReader(stream)
        if reader.fieldnames is None:
            raise ValueError(f"events CSV has no header: {events_path}")
        for required in ("det_x", "scatter_count_total"):
            if required not in reader.fieldnames:
                raise ValueError(f"events CSV missing required field {required}: {events_path}")
        bad_fields = [field for field in reader.fieldnames if "|" in field]
        if bad_fields:
            raise ValueError(f"events CSV contains unsupported field names: {bad_fields}")

        for row in reader:
            try:
                x = float(row.get("det_x", ""))
            except ValueError:
                continue
            index = bin_index_for_x(x, x_min, x_max, bin_width_mm, len(edges))
            if index is None:
                continue
            scatter_count = as_int(row.get("scatter_count_total"), 0)
            for channel in channels:
                if channel_accepts(channel, scatter_count):
                    counts[channel][index] += 1

    info = case_info(metadata, run_dir)
    rows: list[dict[str, Any]] = []
    for channel in channels:
        channel_total = sum(counts[channel])
        for index, (left, right) in enumerate(edges):
            count = counts[channel][index]
            rows.append(
                {
                    **info,
                    "channel": channel,
                    "bin_index": index,
                    "x_min_mm": left,
                    "x_max_mm": right,
                    "x_center_mm": (left + right) / 2.0,
                    "count": count,
                    "channel_total_count": channel_total,
                    "yield": count / channel_total if channel_total > 0 else 0.0,
                }
            )
    return rows, counts


def png_name(run_id: str, channel: str) -> str:
    safe = re.sub(r"[^A-Za-z0-9_.-]+", "_", f"{run_id}_{channel}")
    return safe + ".png"


def comparison_png_name(energy_keV: int, channel: str) -> str:
    safe_channel = re.sub(r"[^A-Za-z0-9_.-]+", "_", channel)
    return f"comparison_E{energy_keV}_{safe_channel}.png"


def ensure_matplotlib_available() -> None:
    try:
        import matplotlib  # noqa: F401
    except ModuleNotFoundError as error:
        raise RuntimeError(
            "matplotlib is required for PNG output. Install it with: python3 -m pip install matplotlib"
        ) from error


def write_png(output_dir: Path, run_id: str, channel: str, rows: list[dict[str, Any]]) -> Path:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    x_centers = [float(row["x_center_mm"]) for row in rows]
    counts = [int(row["count"]) for row in rows]
    title = f"{rows[0]['case_id']} | {channel} | E{rows[0]['energy_keV']} keV | seed {rows[0]['seed']}"

    path = output_dir / png_name(run_id, channel)
    fig, ax = plt.subplots(figsize=(10, 4.5), constrained_layout=True)
    ax.step(x_centers, counts, where="mid", linewidth=1.4)
    ax.set_xlabel("detector x position (mm)")
    ax.set_ylabel("raw count per bin")
    ax.set_title(title)
    ax.grid(True, alpha=0.25)
    fig.savefig(path, dpi=150)
    plt.close(fig)
    return path


def state_key(row: dict[str, Any]) -> tuple[str, str, str]:
    material = row.get("abnormal_material")
    return (str(row.get("pose", "")), str(row.get("model_state", "")), "" if material is None else str(material))


def state_label(key: tuple[str, str, str]) -> str:
    pose, model_state, material = key
    pose_label = {"poseC": "Pose-C", "poseR": "Pose-R"}.get(pose, pose)
    if model_state == "normal":
        return f"{pose_label} normal"
    if material == "G4_POLYETHYLENE":
        return f"{pose_label} PE"
    if material == "Vehicle_Flour":
        return f"{pose_label} Flour"
    return f"{pose_label} abnormal {material or model_state}"


def ordered_state_keys(rows: list[dict[str, Any]]) -> list[tuple[str, str, str]]:
    found = {state_key(row) for row in rows}
    ordered: list[tuple[str, str, str]] = []
    for preferred in PREFERRED_STATE_ORDER:
        if preferred in found:
            ordered.append(preferred)
            found.remove(preferred)
    ordered.extend(sorted(found, key=state_label))
    return ordered


def row_matches_filters(row: dict[str, Any], energies: list[int] | None, seed: int | None) -> bool:
    if energies is not None and int(row["energy_keV"]) not in set(energies):
        return False
    if seed is not None and int(row["seed"]) != seed:
        return False
    return True


def comparison_panel_data(rows: list[dict[str, Any]]) -> dict[tuple[int, str], dict[tuple[tuple[str, str, str], str], list[dict[str, Any]]]]:
    grouped: dict[tuple[int, str], dict[tuple[tuple[str, str, str], str], dict[str, Any]]] = {}
    for row in rows:
        figure_key = (int(row["energy_keV"]), str(row["channel"]))
        panel_key = (state_key(row), str(row["system"]))
        panel = grouped.setdefault(figure_key, {}).setdefault(
            panel_key,
            {"bins": {}, "channel_total_by_run": {}, "seed_values": set()},
        )
        bins = panel["bins"]
        index = int(row["bin_index"])
        if index not in bins:
            bins[index] = dict(row)
            bins[index]["count"] = 0
        bins[index]["count"] = int(bins[index]["count"]) + int(row["count"])
        panel["channel_total_by_run"][str(row["run_id"])] = int(row["channel_total_count"])
        panel["seed_values"].add(int(row["seed"]))

    finalized: dict[tuple[int, str], dict[tuple[tuple[str, str, str], str], list[dict[str, Any]]]] = {}
    for figure_key, panels in grouped.items():
        finalized[figure_key] = {}
        for panel_key, panel in panels.items():
            bins = panel["bins"]
            panel_total = sum(panel["channel_total_by_run"].values())
            for row in bins.values():
                row["channel_total_count"] = panel_total
                row["yield"] = int(row["count"]) / panel_total if panel_total > 0 else 0.0
                row["seed_values"] = set(panel["seed_values"])
            finalized[figure_key][panel_key] = [bins[index] for index in sorted(bins)]
    return finalized


def write_comparison_png(
    output_dir: Path,
    energy_keV: int,
    channel: str,
    state_keys: list[tuple[str, str, str]],
    panels: dict[tuple[tuple[str, str, str], str], list[dict[str, Any]]],
) -> Path:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    output_dir.mkdir(parents=True, exist_ok=True)
    path = output_dir / comparison_png_name(energy_keV, channel)
    n_rows = max(1, len(state_keys))
    fig, axes = plt.subplots(
        n_rows,
        len(SYSTEM_ORDER),
        figsize=(12, max(2.6, 2.25 * n_rows)),
        sharex=True,
        sharey=True,
        squeeze=False,
        constrained_layout=True,
    )
    y_max = 0
    for panel_rows in panels.values():
        if panel_rows:
            y_max = max(y_max, max(float(row["yield"]) for row in panel_rows))

    for row_index, key in enumerate(state_keys):
        for column_index, system in enumerate(SYSTEM_ORDER):
            ax = axes[row_index][column_index]
            panel_rows = panels.get((key, system), [])
            if panel_rows:
                x_centers = [float(row["x_center_mm"]) for row in panel_rows]
                yields = [float(row["yield"]) for row in panel_rows]
                ax.step(x_centers, yields, where="mid", linewidth=1.2)
            else:
                ax.text(0.5, 0.5, "missing", ha="center", va="center", transform=ax.transAxes)
            if row_index == 0:
                ax.set_title(system)
            if column_index == 0:
                ax.set_ylabel(state_label(key))
            ax.grid(True, alpha=0.25)
            if y_max > 0:
                ax.set_ylim(bottom=0, top=y_max * 1.08)
    fig.supxlabel("detector x position (mm)")
    fig.supylabel("yield per detector-x bin")
    fig.suptitle(f"Detector response comparison | E{energy_keV} keV | {channel}")
    fig.savefig(path, dpi=150)
    plt.close(fig)
    return path


def write_comparison_outputs(
    output_dir: Path,
    rows: list[dict[str, Any]],
    channels: list[str],
    energies: list[int] | None,
    seed: int | None,
    write_plots: bool,
    write_csv_files: bool,
) -> dict[str, Any]:
    filtered_rows = [
        row
        for row in rows
        if str(row["channel"]) in channels and row_matches_filters(row, energies, seed)
    ]
    output_dir.mkdir(parents=True, exist_ok=True)
    panels_by_figure = comparison_panel_data(filtered_rows)
    all_state_keys = ordered_state_keys(filtered_rows)
    index_rows: list[dict[str, Any]] = []
    png_paths: list[Path] = []

    for energy_keV, channel in sorted(panels_by_figure):
        panels = panels_by_figure[(energy_keV, channel)]
        state_keys_for_figure = all_state_keys
        expected_panel_count = len(state_keys_for_figure) * len(SYSTEM_ORDER)
        present_panel_count = sum(
            1
            for state in state_keys_for_figure
            for system in SYSTEM_ORDER
            if (state, system) in panels
        )
        png_path = output_dir / comparison_png_name(energy_keV, channel)
        if write_plots:
            png_path = write_comparison_png(output_dir, energy_keV, channel, state_keys_for_figure, panels)
            png_paths.append(png_path)
        seed_values = {
            seed
            for panel_rows in panels.values()
            for row in panel_rows
            for seed in row.get("seed_values", {int(row["seed"])})
        }
        index_rows.append(
            {
                "png_file": png_path.as_posix(),
                "energy_keV": energy_keV,
                "channel": channel,
                "state_count": len(state_keys_for_figure),
                "panel_count": expected_panel_count,
                "missing_panel_count": expected_panel_count - present_panel_count,
                "response_scale": "yield_by_channel_total",
                "systems": ",".join(SYSTEM_ORDER),
                "states": "; ".join(state_label(key) for key in state_keys_for_figure),
                "seed_count": len(seed_values),
            }
        )

    index_path = output_dir / "detector_response_comparison_index.csv"
    if write_csv_files:
        write_csv(
            index_path,
            index_rows,
            [
                "png_file",
                "energy_keV",
                "channel",
                "state_count",
                "panel_count",
                "missing_panel_count",
                "response_scale",
                "systems",
                "states",
                "seed_count",
            ],
        )
    return {"index": index_path, "pngs": png_paths, "figure_count": len(index_rows)}


def write_csv(path: Path, rows: list[dict[str, Any]], fieldnames: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow({field: format_value(row.get(field)) for field in fieldnames})


def plot_detector_response(
    input_paths: list[Path],
    output_dir: Path,
    channels: list[str],
    bin_width_mm: float = 1.0,
    write_plots: bool = True,
    comparison_grid: bool = False,
    comparison_output_dir: Path | None = None,
    energies: list[int] | None = None,
    seed: int | None = None,
    write_csv_files: bool = False,
) -> dict[str, Any]:
    if write_plots:
        ensure_matplotlib_available()

    run_dirs = discover_run_dirs(input_paths)
    if not run_dirs:
        raise ValueError("no run directories containing metadata.yaml and events.csv were found")

    output_dir.mkdir(parents=True, exist_ok=True)
    all_rows: list[dict[str, Any]] = []
    png_paths: list[Path] = []
    for run_dir in run_dirs:
        rows, _counts = aggregate_run(run_dir, channels, bin_width_mm)
        rows = [row for row in rows if row_matches_filters(row, energies, seed)]
        if not rows:
            continue
        all_rows.extend(rows)
        if write_plots:
            by_channel: dict[str, list[dict[str, Any]]] = {channel: [] for channel in channels}
            for row in rows:
                by_channel[str(row["channel"])].append(row)
            run_id = str(rows[0]["run_id"])
            for channel in channels:
                png_paths.append(write_png(output_dir, run_id, channel, by_channel[channel]))

    csv_path = output_dir / "detector_response_bins.csv"
    fieldnames = [
        "run_dir",
        "run_id",
            "case_id",
            "system",
            "pose",
            "pose_id",
            "model_type",
            "model_state",
            "abnormal_material",
            "energy_keV",
            "seed",
            "seed_count",
            "channel",
            "bin_index",
        "x_min_mm",
        "x_max_mm",
        "x_center_mm",
        "count",
        "channel_total_count",
        "yield",
    ]
    if write_csv_files:
        write_csv(csv_path, all_rows, fieldnames)
    comparison: dict[str, Any] | None = None
    if comparison_grid:
        comparison = write_comparison_outputs(
            comparison_output_dir or Path("results/analysis/detector_response_comparison"),
            all_rows,
            channels,
            energies,
            seed,
            write_plots,
            write_csv_files,
        )
    return {
        "csv": csv_path,
        "pngs": png_paths,
        "run_count": len(run_dirs),
        "row_count": len(all_rows),
        "comparison": comparison,
    }


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("run_dirs", type=Path, nargs="+")
    parser.add_argument("--output-dir", type=Path, default=Path("results/analysis/detector_response"))
    parser.add_argument(
        "--comparison-output-dir",
        type=Path,
        default=Path("results/analysis/detector_response_comparison"),
    )
    parser.add_argument("--bin-width-mm", type=float, default=1.0)
    parser.add_argument("--channels", type=parse_channels, default=parse_channels("all"))
    parser.add_argument("--comparison-grid", action="store_true")
    parser.add_argument("--energies", type=parse_int_list)
    parser.add_argument("--seed", type=int)
    parser.add_argument("--write-csv", action="store_true")
    return parser.parse_args(argv)


def main() -> int:
    args = parse_args()
    try:
        outputs = plot_detector_response(
            args.run_dirs,
            args.output_dir,
            args.channels,
            args.bin_width_mm,
            write_plots=True,
            comparison_grid=args.comparison_grid,
            comparison_output_dir=args.comparison_output_dir,
            energies=args.energies,
            seed=args.seed,
            write_csv_files=args.write_csv,
        )
    except Exception as error:
        print(f"detector response error: {error}", file=sys.stderr)
        return 2
    print(f"Processed {outputs['run_count']} run(s)")
    if args.write_csv:
        print(f"CSV: {outputs['csv']}")
    print(f"PNG count: {len(outputs['pngs'])}")
    if outputs.get("comparison"):
        comparison = outputs["comparison"]
        if args.write_csv:
            print(f"Comparison index: {comparison['index']}")
        print(f"Comparison PNG count: {len(comparison['pngs'])}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
