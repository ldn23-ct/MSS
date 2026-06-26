#!/usr/bin/env python3
"""Generate 2D article grid response maps from cleaned events files."""

from __future__ import annotations

import argparse
import math
import os
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

try:
    os.environ.setdefault("MPLCONFIGDIR", "/tmp/mss_matplotlib")
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    import numpy as np
    import pandas as pd
    import yaml
except ModuleNotFoundError as error:  # pragma: no cover - exercised by CLI users.
    raise RuntimeError(
        "article grid plotting requires the data environment. "
        "Run `conda activate data` or use `conda run -n data python ...`."
    ) from error

from clean_events import SLIT_COLUMN, RangeSpec, slit_for_det_x, validate_det_x_ranges


GRID_POSE_RE = re.compile(r"^grid_x(?P<x>m?\d+(?:p\d+)?)_y(?P<y>m?\d+(?:p\d+)?)$")
EXPERIMENT_TOKENS = {"E0", "E1", "E3", "E4"}
MATRIX_CHANNELS = (
    "I_total",
    "I_k1",
    "I_k2",
    "I_ms",
    "I_without_ms",
    "F_ms",
    "Delta_I_total",
    "Delta_I_k1",
    "Delta_I_ms",
)
PANEL_CHANNELS = ("I_total", "I_k1", "I_ms", "Delta_I_ms")
DELTA_SOURCES = {
    "Delta_I_total": "I_total",
    "Delta_I_k1": "I_k1",
    "Delta_I_ms": "I_ms",
}


@dataclass(frozen=True)
class RunInfo:
    run_dir: Path
    events_path: Path
    metadata_path: Path
    experiment: str
    phantom_id: str
    energy_keV: float
    energy_token: str
    pose: str
    head_offset_x_mm: float
    head_offset_y_mm: float
    n_primary: int


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


def format_number_token(value: float | int) -> str:
    numeric = float(value)
    text = f"{numeric:.12g}"
    if "e" not in text.lower() and "." in text:
        text = text.rstrip("0").rstrip(".")
    return text.replace("-", "m").replace(".", "p")


def energy_token_from_value(value: Any) -> str:
    numeric = as_float(value)
    if not math.isfinite(numeric):
        return "Eunknown"
    return "E" + format_number_token(numeric)


def normalize_energy_filter(text: str) -> str:
    value = text.strip()
    if value.upper().startswith("E"):
        value = value[1:]
    numeric_text = value.replace("p", ".").replace("P", ".")
    try:
        return energy_token_from_value(float(numeric_text))
    except ValueError:
        return "E" + value


def parse_pose_number(token: str) -> float:
    normalized = token.replace("p", ".")
    sign = -1.0 if normalized.startswith("m") else 1.0
    if normalized.startswith("m"):
        normalized = normalized[1:]
    return sign * float(normalized)


def pose_offsets_from_name(pose: str) -> tuple[float, float] | None:
    match = GRID_POSE_RE.match(pose)
    if match is None:
        return None
    return parse_pose_number(match.group("x")), parse_pose_number(match.group("y"))


def condition_from_path(run_dir: Path) -> dict[str, str]:
    parts = list(run_dir.parts)
    for index, part in enumerate(parts):
        if part in EXPERIMENT_TOKENS and index + 3 < len(parts):
            return {
                "experiment": part,
                "phantom_id": parts[index + 1],
                "energy_token": parts[index + 2],
                "pose": parts[index + 3],
            }
    return {}


def discover_event_files(input_root: Path, events_name: str) -> list[Path]:
    if input_root.is_file():
        if input_root.name != events_name:
            raise ValueError(f"input file must be named {events_name}: {input_root}")
        return [input_root.resolve()]
    if not input_root.is_dir():
        raise FileNotFoundError(f"input root does not exist: {input_root}")
    discovered = sorted(path.resolve() for path in input_root.rglob(events_name) if path.is_file())
    direct = input_root / events_name
    if direct.is_file():
        direct_resolved = direct.resolve()
        discovered = [direct_resolved] + [path for path in discovered if path != direct_resolved]
    return discovered


def run_info_for(event_file: Path, metadata_name: str) -> RunInfo:
    run_dir = event_file.parent
    metadata_path = run_dir / metadata_name
    if not metadata_path.is_file():
        raise FileNotFoundError(f"metadata file not found beside events file: {metadata_path}")
    metadata = read_yaml(metadata_path)
    condition = metadata.get("condition") if isinstance(metadata.get("condition"), dict) else {}
    path_condition = condition_from_path(run_dir)

    experiment = str(condition.get("experiment") or path_condition.get("experiment") or "")
    phantom_id = str(condition.get("phantom_id") or path_condition.get("phantom_id") or "")
    pose = str(condition.get("pose") or path_condition.get("pose") or metadata.get("pose_id") or run_dir.name)

    energy_value = condition.get("energy_keV", nested(metadata, "source", "mono_energy_keV", default=math.nan))
    energy_keV = as_float(energy_value)
    if not math.isfinite(energy_keV):
        energy_token = path_condition.get("energy_token", "Eunknown")
        energy_keV = as_float(energy_token.lstrip("E").replace("p", "."))
    else:
        energy_token = energy_token_from_value(energy_keV)

    offset_x = as_float(condition.get("head_offset_x_mm", metadata.get("head_offset_x_mm", math.nan)))
    offset_y = as_float(condition.get("head_offset_y_mm", metadata.get("head_offset_y_mm", math.nan)))
    if not (math.isfinite(offset_x) and math.isfinite(offset_y)):
        parsed_offsets = pose_offsets_from_name(pose)
        if parsed_offsets is None:
            raise ValueError(f"cannot determine grid offsets for pose {pose!r}: {metadata_path}")
        offset_x, offset_y = parsed_offsets

    n_primary = as_int(metadata.get("n_primary"), 0)
    if n_primary <= 0:
        raise ValueError(f"metadata n_primary must be positive: {metadata_path}")
    if not experiment or not phantom_id:
        raise ValueError(f"cannot determine experiment and phantom_id: {metadata_path}")

    return RunInfo(
        run_dir=run_dir,
        events_path=event_file,
        metadata_path=metadata_path,
        experiment=experiment,
        phantom_id=phantom_id,
        energy_keV=energy_keV,
        energy_token=energy_token,
        pose=pose,
        head_offset_x_mm=offset_x,
        head_offset_y_mm=offset_y,
        n_primary=n_primary,
    )


def assign_slit_ids(frame: pd.DataFrame, ranges: list[RangeSpec], source: Path) -> pd.DataFrame:
    required = {"det_x", "first_scatter_z", "last_scatter_z"}
    missing = sorted(required.difference(frame.columns))
    if missing:
        raise ValueError(f"raw events CSV is missing required columns {missing}: {source}")

    working = frame.copy()
    for column in ("det_x", "first_scatter_z", "last_scatter_z"):
        working[column] = pd.to_numeric(working[column], errors="coerce")
    valid_rows = (
        working["det_x"].notna()
        & working["first_scatter_z"].notna()
        & working["last_scatter_z"].notna()
        & np.isfinite(working["det_x"])
        & np.isfinite(working["first_scatter_z"])
        & np.isfinite(working["last_scatter_z"])
        & (working["first_scatter_z"] >= 0.0)
        & (working["last_scatter_z"] >= 0.0)
    )
    working = working[valid_rows].copy()
    working[SLIT_COLUMN] = working["det_x"].apply(lambda value: slit_for_det_x(float(value), ranges))
    return working[working[SLIT_COLUMN].notna()].copy()


def load_events(event_file: Path, ranges: list[RangeSpec]) -> pd.DataFrame:
    frame = pd.read_csv(event_file, low_memory=False)
    if "scatter_count_total" not in frame.columns:
        raise ValueError(f"events CSV is missing scatter_count_total: {event_file}")
    if SLIT_COLUMN not in frame.columns:
        frame = assign_slit_ids(frame, ranges, event_file)
    else:
        frame = frame.copy()
        frame[SLIT_COLUMN] = frame[SLIT_COLUMN].astype(str)

    valid_slits = {item.slit_id for item in ranges}
    frame = frame[frame[SLIT_COLUMN].isin(valid_slits)].copy()
    frame["scatter_count_total"] = pd.to_numeric(frame["scatter_count_total"], errors="coerce")
    frame = frame[frame["scatter_count_total"].notna()].copy()
    return frame


def aggregate_run(info: RunInfo, frame: pd.DataFrame, ranges: list[RangeSpec]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for range_spec in ranges:
        subset = frame[frame[SLIT_COLUMN] == range_spec.slit_id]
        scatter = subset["scatter_count_total"]
        n_total = int(len(subset))
        n_k1 = int((scatter == 1).sum())
        n_k2 = int((scatter == 2).sum())
        n_ms = int((scatter >= 2).sum())
        n_without_ms = int((scatter <= 1).sum())
        rows.append(
            {
                "experiment": info.experiment,
                "phantom_id": info.phantom_id,
                "energy_keV": info.energy_keV,
                "energy_token": info.energy_token,
                "pose": info.pose,
                "head_offset_x_mm": info.head_offset_x_mm,
                "head_offset_y_mm": info.head_offset_y_mm,
                "slit_id": range_spec.slit_id,
                "n_primary": info.n_primary,
                "N_total": n_total,
                "N_k1": n_k1,
                "N_k2": n_k2,
                "N_ms": n_ms,
                "N_without_ms": n_without_ms,
                "I_total": n_total / info.n_primary,
                "I_k1": n_k1 / info.n_primary,
                "I_k2": n_k2 / info.n_primary,
                "I_ms": n_ms / info.n_primary,
                "I_without_ms": n_without_ms / info.n_primary,
                "F_ms": n_ms / n_total if n_total else math.nan,
                "run_dir": info.run_dir.as_posix(),
                "events_file": info.events_path.as_posix(),
                "metadata_file": info.metadata_path.as_posix(),
            }
        )
    return rows


def control_phantom_for(experiment: str, explicit: str | None) -> str:
    if explicit:
        return explicit
    if experiment == "E4":
        return "M0"
    return "P0"


def add_delta_columns(frame: pd.DataFrame, control_phantom: str) -> pd.DataFrame:
    keys = ["slit_id", "head_offset_x_mm", "head_offset_y_mm", "energy_token"]
    control = frame[frame["phantom_id"] == control_phantom][[*keys, *DELTA_SOURCES.values()]].copy()
    if control.empty:
        for delta_name in DELTA_SOURCES:
            frame[delta_name] = math.nan
        return frame

    rename_map = {source: f"{source}_control" for source in DELTA_SOURCES.values()}
    control = control.rename(columns=rename_map)
    merged = frame.merge(control, on=keys, how="left")
    for delta_name, source_name in DELTA_SOURCES.items():
        merged[delta_name] = merged[source_name] - merged[f"{source_name}_control"]
    return merged.drop(columns=list(rename_map.values()))


def response_long_columns() -> list[str]:
    return [
        "experiment",
        "phantom_id",
        "energy_keV",
        "energy_token",
        "pose",
        "head_offset_x_mm",
        "head_offset_y_mm",
        "slit_id",
        "n_primary",
        "N_total",
        "N_k1",
        "N_k2",
        "N_ms",
        "N_without_ms",
        *MATRIX_CHANNELS,
        "run_dir",
        "events_file",
        "metadata_file",
    ]


def sanitize_token(value: Any) -> str:
    text = str(value)
    chars: list[str] = []
    for char in text:
        if char.isalnum() or char in {"_", "-"}:
            chars.append(char)
        elif char == ".":
            chars.append("p")
        else:
            chars.append("_")
    return "".join(chars).strip("_") or "none"


def sorted_numeric(values: pd.Series) -> list[float]:
    return sorted(float(value) for value in values.dropna().unique())


def matrix_for(
    frame: pd.DataFrame,
    phantom_id: str,
    slit_id: str,
    channel: str,
    x_values: list[float],
    y_values: list[float],
) -> pd.DataFrame:
    subset = frame[(frame["phantom_id"] == phantom_id) & (frame["slit_id"] == slit_id)]
    pivot = subset.pivot_table(
        index="head_offset_y_mm",
        columns="head_offset_x_mm",
        values=channel,
        aggfunc="first",
    )
    matrix = pivot.reindex(index=y_values, columns=x_values)
    matrix.index.name = "head_offset_y_mm"
    return matrix


def write_matrix_csv(path: Path, matrix: pd.DataFrame) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    matrix.to_csv(path)


def finite_limits(values: np.ndarray, channel: str) -> tuple[float, float, str]:
    finite = values[np.isfinite(values)]
    if finite.size == 0:
        return 0.0, 1.0, "viridis"
    if channel.startswith("Delta_"):
        bound = float(np.nanmax(np.abs(finite)))
        if bound == 0.0:
            bound = 1.0e-12
        return -bound, bound, "RdBu_r"
    vmin = float(np.nanmin(finite))
    vmax = float(np.nanmax(finite))
    if vmin == vmax:
        pad = abs(vmin) * 0.05 if vmin else 1.0e-12
        vmin -= pad
        vmax += pad
    return vmin, vmax, "viridis"


def label_number(value: float) -> str:
    if float(value).is_integer():
        return str(int(value))
    return f"{value:.6g}"


def plot_matrix_on_axis(
    ax: Any,
    matrix: pd.DataFrame,
    channel: str,
    title: str,
) -> Any:
    values = matrix.to_numpy(dtype=float)
    vmin, vmax, cmap = finite_limits(values, channel)
    image = ax.imshow(values, origin="lower", aspect="equal", cmap=cmap, vmin=vmin, vmax=vmax)
    ax.set_title(title, fontsize=10)
    ax.set_xlabel("head_offset_x_mm")
    ax.set_ylabel("head_offset_y_mm")
    ax.set_xticks(np.arange(len(matrix.columns)))
    ax.set_xticklabels([label_number(float(value)) for value in matrix.columns], rotation=45, ha="right", fontsize=8)
    ax.set_yticks(np.arange(len(matrix.index)))
    ax.set_yticklabels([label_number(float(value)) for value in matrix.index], fontsize=8)
    return image


def write_heatmap(path: Path, matrix: pd.DataFrame, phantom_id: str, slit_id: str, channel: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fig, ax = plt.subplots(figsize=(6.8, 5.8), constrained_layout=True)
    image = plot_matrix_on_axis(ax, matrix, channel, f"{phantom_id} {slit_id} {channel}")
    fig.colorbar(image, ax=ax, shrink=0.82)
    fig.savefig(path, dpi=180)
    plt.close(fig)


def write_panel(
    path: Path,
    frame: pd.DataFrame,
    phantom_id: str,
    slit_id: str,
    x_values: list[float],
    y_values: list[float],
    experiment: str,
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fig, axes = plt.subplots(2, 2, figsize=(10.5, 9.0), constrained_layout=True)
    for ax, channel in zip(axes.ravel(), PANEL_CHANNELS, strict=True):
        matrix = matrix_for(frame, phantom_id, slit_id, channel, x_values, y_values)
        image = plot_matrix_on_axis(ax, matrix, channel, channel)
        fig.colorbar(image, ax=ax, shrink=0.8)
    fig.suptitle(f"{experiment} {phantom_id} {slit_id}", fontsize=13)
    fig.savefig(path, dpi=180)
    plt.close(fig)


def ensure_output_dir(path: Path, overwrite: bool) -> None:
    if path.exists() and any(path.iterdir()) and not overwrite:
        raise FileExistsError(f"output directory is not empty; use --overwrite to replace files: {path}")
    path.mkdir(parents=True, exist_ok=True)


def to_builtin(value: Any) -> Any:
    if isinstance(value, Path):
        return value.as_posix()
    if isinstance(value, np.generic):
        return value.item()
    if isinstance(value, dict):
        return {str(key): to_builtin(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [to_builtin(item) for item in value]
    if isinstance(value, float) and math.isnan(value):
        return "NaN"
    return value


def write_outputs(
    frame: pd.DataFrame,
    output_dir: Path,
    experiment: str,
    control_phantom: str,
    ranges: list[RangeSpec],
    input_root: Path,
    events_name: str,
) -> dict[str, Any]:
    response_csv = output_dir / "grid_response_long.csv"
    ordered = frame.copy()
    for column in response_long_columns():
        if column not in ordered.columns:
            ordered[column] = math.nan
    ordered = ordered[response_long_columns()]
    ordered.to_csv(response_csv, index=False)

    x_values = sorted_numeric(frame["head_offset_x_mm"])
    y_values = sorted_numeric(frame["head_offset_y_mm"])
    phantom_ids = sorted(str(value) for value in frame["phantom_id"].dropna().unique())
    slit_ids = [item.slit_id for item in ranges]

    matrix_files: list[str] = []
    heatmap_files: list[str] = []
    panel_files: list[str] = []
    for phantom_id in phantom_ids:
        for slit_id in slit_ids:
            for channel in MATRIX_CHANNELS:
                matrix = matrix_for(frame, phantom_id, slit_id, channel, x_values, y_values)
                matrix_path = (
                    output_dir
                    / "matrices"
                    / sanitize_token(phantom_id)
                    / sanitize_token(slit_id)
                    / f"{sanitize_token(channel)}.csv"
                )
                write_matrix_csv(matrix_path, matrix)
                matrix_files.append(matrix_path.as_posix())

                heatmap_path = (
                    output_dir
                    / "figures"
                    / sanitize_token(phantom_id)
                    / sanitize_token(slit_id)
                    / f"{sanitize_token(channel)}.png"
                )
                write_heatmap(heatmap_path, matrix, phantom_id, slit_id, channel)
                heatmap_files.append(heatmap_path.as_posix())

            panel_path = (
                output_dir
                / "figures"
                / "panels"
                / f"{sanitize_token(phantom_id)}_{sanitize_token(slit_id)}_{sanitize_token(experiment)}_panel.png"
            )
            write_panel(panel_path, frame, phantom_id, slit_id, x_values, y_values, experiment)
            panel_files.append(panel_path.as_posix())

    manifest = {
        "script": Path(__file__).as_posix(),
        "input_root": input_root,
        "events_name": events_name,
        "output_dir": output_dir,
        "experiment": experiment,
        "control_phantom": control_phantom,
        "det_x_ranges_mm": [
            {"slit_id": item.slit_id, "left_mm": item.left_mm, "right_mm": item.right_mm}
            for item in ranges
        ],
        "response_csv": response_csv,
        "matrix_channels": list(MATRIX_CHANNELS),
        "phantom_ids": phantom_ids,
        "slit_ids": slit_ids,
        "x_offsets_mm": x_values,
        "y_offsets_mm": y_values,
        "row_count": int(len(frame)),
        "outputs": {
            "matrix_files": matrix_files,
            "heatmap_files": heatmap_files,
            "panel_files": panel_files,
        },
    }
    manifest_path = output_dir / "analysis_manifest.yaml"
    with manifest_path.open("w", encoding="utf-8") as stream:
        yaml.safe_dump(to_builtin(manifest), stream, sort_keys=False, allow_unicode=False, width=100)
    return {
        "response_csv": response_csv,
        "manifest": manifest_path,
        "matrix_file_count": len(matrix_files),
        "heatmap_file_count": len(heatmap_files),
        "panel_file_count": len(panel_files),
    }


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input-root", type=Path, required=True)
    parser.add_argument("--experiment", required=True)
    parser.add_argument("--energy", required=True, help="energy token such as E460 or numeric value such as 460")
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--events-name", default="events_clean.csv")
    parser.add_argument("--metadata-name", default="metadata.yaml")
    parser.add_argument("--control-phantom")
    parser.add_argument("--overwrite", action="store_true")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    ranges = validate_det_x_ranges()
    energy_filter = normalize_energy_filter(args.energy)
    control_phantom = control_phantom_for(args.experiment, args.control_phantom)
    ensure_output_dir(args.output_dir, args.overwrite)

    event_files = discover_event_files(args.input_root, args.events_name)
    if not event_files:
        raise FileNotFoundError(f"no {args.events_name} files found under {args.input_root}")

    rows: list[dict[str, Any]] = []
    matched_runs = 0
    for event_file in event_files:
        info = run_info_for(event_file, args.metadata_name)
        if info.experiment != args.experiment or info.energy_token != energy_filter:
            continue
        frame = load_events(event_file, ranges)
        rows.extend(aggregate_run(info, frame, ranges))
        matched_runs += 1

    if not rows:
        raise ValueError(
            f"no matching runs found for experiment={args.experiment}, energy={energy_filter} "
            f"under {args.input_root}"
        )

    response = pd.DataFrame(rows)
    response = add_delta_columns(response, control_phantom)
    output_info = write_outputs(
        response,
        args.output_dir,
        args.experiment,
        control_phantom,
        ranges,
        args.input_root,
        args.events_name,
    )
    print(f"processed {matched_runs} run(s)")
    print(f"response: {output_info['response_csv']}")
    print(f"manifest: {output_info['manifest']}")
    print(
        "wrote "
        f"{output_info['matrix_file_count']} matrix CSV, "
        f"{output_info['heatmap_file_count']} heatmap PNG, "
        f"{output_info['panel_file_count']} panel PNG"
    )
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as error:
        print(f"error: {error}", file=sys.stderr)
        raise SystemExit(1) from error
