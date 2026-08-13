#!/usr/bin/env python3
"""Generate profile-aware articlev2 grid response matrices and preview plots."""

from __future__ import annotations

import argparse
import math
import os
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

os.environ.setdefault("MPLCONFIGDIR", "/tmp/mss_matplotlib")
try:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    import numpy as np
    import pandas as pd
    import yaml
except ModuleNotFoundError as error:  # pragma: no cover - CLI environment guard.
    raise RuntimeError(
        "articlev2 grid plotting requires pandas/numpy/matplotlib/PyYAML. "
        "Run `conda activate data` or use `conda run -n data python ...`."
    ) from error

from _common import (
    PROFILE_SLITS,
    SLIT_COLUMN,
    RunMetadata,
    discover_event_files,
    metadata_for_events,
    to_builtin,
    windows_for_profile,
)
from articlev2_design import DEFECT_CENTER_Z_MM, TARGET_HALF_WIDTH_MM


FULL_MATRIX_CHANNELS = (
    "I_total", "I_k1", "I_ms",
    "Delta_I_total", "Delta_I_k1", "Delta_I_ms",
)
FILTERED_MATRIX_CHANNELS = ("I_total", "I_k1", "I_ms")
FULL_PANEL_CHANNELS = ("I_total", "I_k1", "I_ms", "Delta_I_ms")
DELTA_SOURCES = {
    "Delta_I_total": "I_total",
    "Delta_I_k1": "I_k1",
    "Delta_I_ms": "I_ms",
}
DEFAULT_DEFECT_CENTER_Z_MM = {
    **DEFECT_CENTER_Z_MM,
    # E7 size-series phantoms share P4's defect location.
    "P7": 60.0,
    "P8": 60.0,
    "P9": 60.0,
}
DEFAULT_TARGET_HALF_WIDTH_MM = TARGET_HALF_WIDTH_MM


@dataclass(frozen=True)
class RunInfo:
    run_dir: Path
    events_path: Path
    metadata_path: Path
    metadata: RunMetadata
    energy_token: str


def format_number_token(value: float | int) -> str:
    text = f"{float(value):.12g}"
    if "e" not in text.lower() and "." in text:
        text = text.rstrip("0").rstrip(".")
    return text.replace("-", "m").replace(".", "p")


def energy_token_from_value(value: float) -> str:
    return "E" + format_number_token(value)


def normalize_energy_filter(text: str) -> str:
    value = text.strip()
    if value.upper().startswith("E"):
        value = value[1:]
    try:
        return energy_token_from_value(float(value.replace("p", ".").replace("P", ".")))
    except ValueError as error:
        raise ValueError(f"energy must be numeric or an E-prefixed numeric token: {text!r}") from error


def validate_first_scatter_z_range(
    values: list[float] | tuple[float, float] | None,
) -> tuple[float, float] | None:
    if values is None:
        return None
    if len(values) != 2:
        raise ValueError("first_scatter_z range requires exactly two bounds")
    minimum, maximum = (float(value) for value in values)
    if not (math.isfinite(minimum) and math.isfinite(maximum)):
        raise ValueError("first_scatter_z range bounds must be finite")
    if minimum >= maximum:
        raise ValueError("first_scatter_z range requires MIN_MM < MAX_MM")
    return minimum, maximum


def first_scatter_z_filter_manifest(
    values: tuple[float, float] | None,
) -> dict[str, Any]:
    if values is None:
        return {"enabled": False, "min_mm": None, "max_mm": None, "interval_rule": "disabled"}
    return {
        "enabled": True, "min_mm": values[0], "max_mm": values[1],
        "interval_rule": "left-closed-right-open: min_mm <= first_scatter_z < max_mm",
    }


def default_target_z_range(phantom_id: str) -> tuple[float, float] | None:
    """Return the fixed center ±5 mm articlev2 target range for a phantom."""

    center = DEFAULT_DEFECT_CENTER_Z_MM.get(phantom_id)
    if center is None:
        return None
    return center - DEFAULT_TARGET_HALF_WIDTH_MM, center + DEFAULT_TARGET_HALF_WIDTH_MM


def range_token(values: tuple[float, float]) -> str:
    return f"z{format_number_token(values[0])}_{format_number_token(values[1])}"


def run_info_for(event_file: Path) -> RunInfo:
    metadata = metadata_for_events(event_file)
    if metadata.scan_mode != "grid":
        raise ValueError(f"plot_grid_response only accepts grid runs: {metadata.metadata_path}")
    return RunInfo(
        run_dir=event_file.parent,
        events_path=event_file,
        metadata_path=metadata.metadata_path,
        metadata=metadata,
        energy_token=energy_token_from_value(metadata.energy_keV),
    )


def load_events(
    event_file: Path,
    profile_id: str,
    first_scatter_z_range_mm: tuple[float, float] | None = None,
) -> pd.DataFrame:
    frame = pd.read_csv(event_file, low_memory=False)
    missing = sorted({SLIT_COLUMN, "scatter_count_total"}.difference(frame.columns))
    if missing:
        raise ValueError(
            f"events CSV is missing required columns {missing}: {event_file}; "
            "run scripts/articlev2/clean_events.py first"
        )
    frame = frame.copy()
    frame[SLIT_COLUMN] = frame[SLIT_COLUMN].astype(str)
    valid_slits = set(PROFILE_SLITS[profile_id])
    invalid_slits = sorted(set(frame[SLIT_COLUMN]).difference(valid_slits))
    if invalid_slits:
        raise ValueError(
            f"events contain slit(s) {invalid_slits} that do not belong to metadata profile "
            f"{profile_id}: {event_file}"
        )
    frame["scatter_count_total"] = pd.to_numeric(frame["scatter_count_total"], errors="coerce")
    scatter = frame["scatter_count_total"]
    invalid_scatter = scatter.isna() | ~np.isfinite(scatter) | (scatter < 0) | (scatter % 1 != 0)
    if bool(invalid_scatter.any()):
        raise ValueError(f"scatter_count_total must contain non-negative integers: {event_file}")
    if first_scatter_z_range_mm is not None:
        if "first_scatter_z" not in frame.columns:
            raise ValueError(
                f"events CSV is missing first_scatter_z required by --first-scatter-z-range-mm: {event_file}"
            )
        minimum, maximum = first_scatter_z_range_mm
        frame["first_scatter_z"] = pd.to_numeric(frame["first_scatter_z"], errors="coerce")
        frame = frame[(frame["first_scatter_z"] >= minimum) & (frame["first_scatter_z"] < maximum)].copy()
    return frame


def aggregate_run(info: RunInfo, frame: pd.DataFrame) -> list[dict[str, Any]]:
    metadata = info.metadata
    rows: list[dict[str, Any]] = []
    for slit_id in PROFILE_SLITS[metadata.profile_id]:
        subset = frame[frame[SLIT_COLUMN] == slit_id]
        scatter = subset["scatter_count_total"]
        n_total = int(len(subset))
        n_k1 = int((scatter == 1).sum())
        n_ms = int((scatter >= 2).sum())
        rows.append({
            "scan_mode": metadata.scan_mode,
            "phantom_id": metadata.phantom_id,
            "profile_id": metadata.profile_id,
            "energy_keV": metadata.energy_keV,
            "energy_token": info.energy_token,
            "pose_id": metadata.pose_id,
            "head_offset_x_mm": metadata.head_offset_x_mm,
            "head_offset_y_mm": metadata.head_offset_y_mm,
            "slit_id": slit_id,
            "n_primary": metadata.n_primary,
            "N_total": n_total, "N_k1": n_k1, "N_ms": n_ms,
            "I_total": n_total, "I_k1": n_k1, "I_ms": n_ms,
            "case_id": metadata.case_id, "run_id": metadata.run_id,
            "run_dir": info.run_dir.as_posix(),
            "events_file": info.events_path.as_posix(),
            "metadata_file": info.metadata_path.as_posix(),
        })
    return rows


def validate_grid_runs(infos: list[RunInfo], control_phantom: str) -> None:
    if not infos:
        raise ValueError("no matching grid runs")
    by_profile: dict[str, list[RunInfo]] = {}
    for info in infos:
        by_profile.setdefault(info.metadata.profile_id, []).append(info)
    for profile_id, profile_infos in by_profile.items():
        by_phantom: dict[str, list[RunInfo]] = {}
        seen: dict[tuple[str, float, float], Path] = {}
        for info in profile_infos:
            metadata = info.metadata
            key = (metadata.phantom_id, metadata.head_offset_x_mm, metadata.head_offset_y_mm)
            if key in seen:
                raise ValueError(
                    f"duplicate grid cell for profile={profile_id}, phantom/offset={key}: "
                    f"{seen[key]} and {info.metadata_path}"
                )
            seen[key] = info.metadata_path
            by_phantom.setdefault(metadata.phantom_id, []).append(info)
        if control_phantom not in by_phantom:
            raise ValueError(f"control phantom {control_phantom} is missing for profile {profile_id}")

        control = by_phantom[control_phantom]
        control_offsets = {
            (info.metadata.head_offset_x_mm, info.metadata.head_offset_y_mm): info
            for info in control
        }
        x_values = {offset[0] for offset in control_offsets}
        y_values = {offset[1] for offset in control_offsets}
        expected_offsets = {(x, y) for x in x_values for y in y_values}
        if set(control_offsets) != expected_offsets:
            missing = sorted(expected_offsets.difference(control_offsets))
            raise ValueError(f"control grid is incomplete for profile {profile_id}; missing offsets: {missing}")

        for phantom_id, phantom_infos in by_phantom.items():
            offsets = {
                (info.metadata.head_offset_x_mm, info.metadata.head_offset_y_mm): info
                for info in phantom_infos
            }
            if set(offsets) != expected_offsets:
                missing = sorted(expected_offsets.difference(offsets))
                extra = sorted(set(offsets).difference(expected_offsets))
                raise ValueError(
                    f"grid offsets differ from control for profile={profile_id}, phantom={phantom_id}; "
                    f"missing={missing}, extra={extra}"
                )
            for offset, info in offsets.items():
                control_info = control_offsets[offset]
                if info.metadata.n_primary != control_info.metadata.n_primary:
                    raise ValueError(
                        f"n_primary differs from control for profile={profile_id}, phantom={phantom_id}, "
                        f"offset={offset}: {info.metadata.n_primary} != {control_info.metadata.n_primary}"
                    )


def add_delta_columns(frame: pd.DataFrame, control_phantom: str) -> pd.DataFrame:
    keys = [
        "profile_id", "slit_id", "head_offset_x_mm", "head_offset_y_mm", "energy_token"
    ]
    control = frame[frame["phantom_id"] == control_phantom][[*keys, *DELTA_SOURCES.values()]].copy()
    if control.empty:
        raise ValueError(f"control phantom {control_phantom} has no response rows")
    if bool(control.duplicated(keys).any()):
        raise ValueError("control response contains duplicate profile/slit/pose rows")
    rename = {source: f"{source}_control" for source in DELTA_SOURCES.values()}
    merged = frame.merge(control.rename(columns=rename), on=keys, how="left", validate="many_to_one")
    missing_control = merged[next(iter(rename.values()))].isna()
    if bool(missing_control.any()):
        raise ValueError("one or more grid response rows have no paired control pose")
    for delta_name, source_name in DELTA_SOURCES.items():
        merged[delta_name] = merged[source_name] - merged[f"{source_name}_control"]
    return merged.drop(columns=list(rename.values()))


def response_long_columns(include_delta: bool) -> list[str]:
    channels = FULL_MATRIX_CHANNELS if include_delta else FILTERED_MATRIX_CHANNELS
    return [
        "scan_mode", "phantom_id", "profile_id", "energy_keV", "energy_token", "pose_id",
        "head_offset_x_mm", "head_offset_y_mm", "slit_id", "n_primary",
        "N_total", "N_k1", "N_ms", *channels,
        "case_id", "run_id", "run_dir", "events_file", "metadata_file",
    ]


def sorted_numeric(values: pd.Series) -> list[float]:
    return sorted(float(value) for value in values.dropna().unique())


def matrix_for(
    frame: pd.DataFrame, profile_id: str, phantom_id: str, slit_id: str,
    channel: str, x_values: list[float], y_values: list[float],
) -> pd.DataFrame:
    subset = frame[
        (frame["profile_id"] == profile_id)
        & (frame["phantom_id"] == phantom_id)
        & (frame["slit_id"] == slit_id)
    ]
    pivot = subset.pivot(
        index="head_offset_y_mm", columns="head_offset_x_mm", values=channel
    )
    matrix = pivot.reindex(index=y_values, columns=x_values)
    matrix.index.name = "head_offset_y_mm"
    return matrix


def sanitize_token(value: Any) -> str:
    text = str(value)
    return "".join(char if char.isalnum() or char in "_-" else "p" if char == "." else "_" for char in text).strip("_") or "none"


def finite_limits(values: np.ndarray, channel: str) -> tuple[float, float, str]:
    finite = values[np.isfinite(values)]
    if finite.size == 0:
        return 0.0, 1.0, "viridis"
    if channel.startswith("Delta_"):
        bound = float(np.nanmax(np.abs(finite))) or 1.0e-12
        return -bound, bound, "RdBu_r"
    vmin, vmax = float(np.nanmin(finite)), float(np.nanmax(finite))
    if vmin == vmax:
        pad = abs(vmin) * 0.05 if vmin else 1.0e-12
        vmin, vmax = vmin - pad, vmax + pad
    return vmin, vmax, "viridis"


def plot_matrix_on_axis(ax: Any, matrix: pd.DataFrame, channel: str, title: str) -> Any:
    values = matrix.to_numpy(dtype=float)
    vmin, vmax, cmap = finite_limits(values, channel)
    image = ax.imshow(values, origin="lower", aspect="equal", cmap=cmap, vmin=vmin, vmax=vmax)
    ax.set_title(title, fontsize=10)
    ax.set_xlabel("head_offset_x_mm")
    ax.set_ylabel("head_offset_y_mm")
    ax.set_xticks(np.arange(len(matrix.columns)))
    ax.set_xticklabels([f"{float(value):g}" for value in matrix.columns], rotation=45, ha="right", fontsize=8)
    ax.set_yticks(np.arange(len(matrix.index)))
    ax.set_yticklabels([f"{float(value):g}" for value in matrix.index], fontsize=8)
    return image


def write_heatmap(
    path: Path, matrix: pd.DataFrame, profile_id: str, phantom_id: str,
    slit_id: str, channel: str,
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fig, ax = plt.subplots(figsize=(6.8, 5.8), constrained_layout=True)
    image = plot_matrix_on_axis(ax, matrix, channel, f"{profile_id} {phantom_id} {slit_id} {channel}")
    fig.colorbar(image, ax=ax, shrink=0.82)
    fig.savefig(path, dpi=180)
    plt.close(fig)


def write_panel(
    path: Path, frame: pd.DataFrame, profile_id: str, phantom_id: str,
    slit_id: str, x_values: list[float], y_values: list[float], channels: tuple[str, ...],
    title_suffix: str,
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if len(channels) == 4:
        fig, axes = plt.subplots(2, 2, figsize=(10.5, 9.0), constrained_layout=True)
    elif len(channels) == 3:
        fig, axes = plt.subplots(1, 3, figsize=(14.0, 4.6), constrained_layout=True)
    else:  # Defensive guard for future channel-set edits.
        raise ValueError(f"panel requires three or four channels, got: {channels}")
    for ax, channel in zip(np.asarray(axes).ravel(), channels, strict=True):
        matrix = matrix_for(frame, profile_id, phantom_id, slit_id, channel, x_values, y_values)
        image = plot_matrix_on_axis(ax, matrix, channel, channel)
        fig.colorbar(image, ax=ax, shrink=0.8)
    fig.suptitle(
        f"articlev2 grid {profile_id} {phantom_id} {slit_id} | {title_suffix}", fontsize=13
    )
    fig.savefig(path, dpi=180)
    plt.close(fig)


def ensure_output_dir(path: Path, overwrite: bool) -> None:
    if path.exists() and any(path.iterdir()) and not overwrite:
        raise FileExistsError(f"output directory is not empty; use --overwrite: {path}")
    path.mkdir(parents=True, exist_ok=True)


def write_outputs(
    frame: pd.DataFrame,
    output_dir: Path,
    input_root: Path,
    events_name: str,
    first_scatter_z_range_mm: tuple[float, float] | None,
    *,
    analysis_id: str,
    matrix_channels: tuple[str, ...],
    panel_channels: tuple[str, ...],
    control_phantom: str | None,
    target_phantom: str | None,
    write_manifest_file: bool,
) -> dict[str, Any]:
    output_dir.mkdir(parents=True, exist_ok=True)
    response_csv = output_dir / "grid_response_long.csv"
    ordered = frame.reindex(columns=response_long_columns(include_delta=control_phantom is not None))
    ordered.to_csv(response_csv, index=False)
    outputs = {"matrix_files": [], "heatmap_files": [], "panel_files": []}
    profile_summary: dict[str, Any] = {}
    for profile_id in sorted(frame["profile_id"].unique()):
        profile_frame = frame[frame["profile_id"] == profile_id]
        x_values = sorted_numeric(profile_frame["head_offset_x_mm"])
        y_values = sorted_numeric(profile_frame["head_offset_y_mm"])
        phantom_ids = sorted(str(value) for value in profile_frame["phantom_id"].unique())
        slit_ids = list(PROFILE_SLITS[profile_id])
        profile_summary[profile_id] = {
            "phantom_ids": phantom_ids, "slit_ids": slit_ids,
            "x_offsets_mm": x_values, "y_offsets_mm": y_values,
        }
        for phantom_id in phantom_ids:
            for slit_id in slit_ids:
                for channel in matrix_channels:
                    matrix = matrix_for(
                        frame, profile_id, phantom_id, slit_id, channel, x_values, y_values
                    )
                    matrix_path = output_dir / "matrices" / profile_id / phantom_id / slit_id / f"{channel}.csv"
                    matrix_path.parent.mkdir(parents=True, exist_ok=True)
                    matrix.to_csv(matrix_path)
                    outputs["matrix_files"].append(matrix_path.as_posix())
                    heatmap_path = output_dir / "figures" / profile_id / phantom_id / slit_id / f"{channel}.png"
                    write_heatmap(heatmap_path, matrix, profile_id, phantom_id, slit_id, channel)
                    outputs["heatmap_files"].append(heatmap_path.as_posix())
                panel_path = (
                    output_dir / "figures" / "panels" / profile_id / f"{phantom_id}_{slit_id}_panel.png"
                )
                write_panel(
                    panel_path,
                    frame,
                    profile_id,
                    phantom_id,
                    slit_id,
                    x_values,
                    y_values,
                    panel_channels,
                    analysis_id,
                )
                outputs["panel_files"].append(panel_path.as_posix())
    manifest = {
        "script": Path(__file__), "input_root": input_root, "events_name": events_name,
        "output_dir": output_dir, "analysis_id": analysis_id,
        "control_phantom": control_phantom,
        "target_phantom": target_phantom,
        "profile_groups": profile_summary,
        "det_x_ranges_zero_pose_mm": {
            profile_id: windows_for_profile(profile_id) for profile_id in profile_summary
        },
        "event_filters": {"first_scatter_z": first_scatter_z_filter_manifest(first_scatter_z_range_mm)},
        "response_csv": response_csv, "matrix_channels": matrix_channels,
        "row_count": len(frame), "outputs": outputs,
    }
    manifest_path = output_dir / "analysis_manifest.yaml"
    if write_manifest_file:
        with manifest_path.open("w", encoding="utf-8") as stream:
            yaml.safe_dump(to_builtin(manifest), stream, sort_keys=False, allow_unicode=False, width=100)
    return {
        "response_csv": response_csv,
        "manifest": manifest_path if write_manifest_file else None,
        "manifest_data": manifest,
        **{f"{key[:-1]}_count": len(value) for key, value in outputs.items()},
    }


def build_response(
    infos: list[RunInfo],
    first_scatter_z_range_mm: tuple[float, float] | None,
    *,
    control_phantom: str | None,
) -> pd.DataFrame:
    rows = [
        row
        for info in infos
        for row in aggregate_run(
            info, load_events(info.events_path, info.metadata.profile_id, first_scatter_z_range_mm)
        )
    ]
    response = pd.DataFrame(rows)
    return add_delta_columns(response, control_phantom) if control_phantom is not None else response


def default_target_analyses(infos: list[RunInfo]) -> list[tuple[str, list[RunInfo], tuple[float, float]]]:
    phantoms = sorted({info.metadata.phantom_id for info in infos if info.metadata.phantom_id != "P0"})
    analyses: list[tuple[str, list[RunInfo], tuple[float, float]]] = []
    for phantom_id in phantoms:
        z_range = default_target_z_range(phantom_id)
        if z_range is None:
            continue
        analyses.append((
            f"default_{phantom_id}_{range_token(z_range)}",
            [info for info in infos if info.metadata.phantom_id == phantom_id],
            z_range,
        ))
    return analyses


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input-root", type=Path, required=True)
    parser.add_argument("--energy", required=True, help="energy token such as E560 or numeric 560")
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--events-name", default="events_clean.csv")
    parser.add_argument("--control-phantom", default="P0")
    parser.add_argument(
        "--first-scatter-z-range-mm", nargs=2, type=float,
        metavar=("MIN_MM", "MAX_MM"),
        help=(
            "optional left-closed/right-open first_scatter_z interval for one manual filtered "
            "analysis; when omitted, each grid defect phantom uses its default center ±5 mm range"
        ),
    )
    parser.add_argument("--overwrite", action="store_true")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    energy_filter = normalize_energy_filter(args.energy)
    z_range = validate_first_scatter_z_range(args.first_scatter_z_range_mm)
    files = discover_event_files(args.input_root, args.events_name)
    if not files:
        raise FileNotFoundError(f"no {args.events_name} files found under {args.input_root}")
    infos: list[RunInfo] = []
    for event_file in files:
        info = run_info_for(event_file)
        if info.energy_token == energy_filter:
            infos.append(info)
    if not infos:
        raise ValueError(f"no grid runs found for energy={energy_filter} under {args.input_root}")
    validate_grid_runs(infos, args.control_phantom)
    ensure_output_dir(args.output_dir, args.overwrite)
    full_response = build_response(infos, None, control_phantom=args.control_phantom)
    full_output = write_outputs(
        full_response,
        args.output_dir,
        args.input_root,
        args.events_name,
        None,
        analysis_id="full",
        matrix_channels=FULL_MATRIX_CHANNELS,
        panel_channels=FULL_PANEL_CHANNELS,
        control_phantom=args.control_phantom,
        target_phantom=None,
        write_manifest_file=False,
    )

    filtered_outputs: list[dict[str, Any]] = []
    if z_range is not None:
        analysis_id = f"manual_{range_token(z_range)}"
        filtered_dir = args.output_dir / "filtered" / f"manual_{range_token(z_range)}"
        filtered_response = build_response(infos, z_range, control_phantom=None)
        filtered_outputs.append(write_outputs(
            filtered_response,
            filtered_dir,
            args.input_root,
            args.events_name,
            z_range,
            analysis_id=analysis_id,
            matrix_channels=FILTERED_MATRIX_CHANNELS,
            panel_channels=FILTERED_MATRIX_CHANNELS,
            control_phantom=None,
            target_phantom=None,
            write_manifest_file=True,
        ))
    else:
        for analysis_id, target_infos, default_range in default_target_analyses(infos):
            target_phantom = target_infos[0].metadata.phantom_id
            filtered_dir = args.output_dir / "filtered" / "default" / (
                f"{target_phantom}_{range_token(default_range)}"
            )
            filtered_response = build_response(target_infos, default_range, control_phantom=None)
            filtered_outputs.append(write_outputs(
                filtered_response,
                filtered_dir,
                args.input_root,
                args.events_name,
                default_range,
                analysis_id=analysis_id,
                matrix_channels=FILTERED_MATRIX_CHANNELS,
                panel_channels=FILTERED_MATRIX_CHANNELS,
                control_phantom=None,
                target_phantom=target_phantom,
                write_manifest_file=True,
            ))

    manifest = {
        "script": Path(__file__),
        "input_root": args.input_root,
        "events_name": args.events_name,
        "output_dir": args.output_dir,
        "energy_filter": energy_filter,
        "full_analysis": full_output["manifest_data"],
        "filtered_analyses": [item["manifest_data"] for item in filtered_outputs],
        "manual_first_scatter_z_range_mm": z_range,
        "default_target_half_width_mm": DEFAULT_TARGET_HALF_WIDTH_MM,
        "default_defect_center_z_mm": DEFAULT_DEFECT_CENTER_Z_MM,
    }
    manifest_path = args.output_dir / "analysis_manifest.yaml"
    with manifest_path.open("w", encoding="utf-8") as stream:
        yaml.safe_dump(to_builtin(manifest), stream, sort_keys=False, allow_unicode=False, width=100)
    print(f"processed {len(infos)} run(s) across {full_response['profile_id'].nunique()} profile(s)")
    print(f"full response: {full_output['response_csv']}")
    print(f"filtered analyses: {len(filtered_outputs)}")
    print(f"manifest: {manifest_path}")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as error:
        print(f"error: {error}", file=sys.stderr)
        raise SystemExit(1) from error
