#!/usr/bin/env python3
"""Build articlev2 condition-level first/last scatter-position histograms."""

from __future__ import annotations

import argparse
import csv
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
    import yaml
except ModuleNotFoundError as error:  # pragma: no cover - CLI environment guard.
    raise RuntimeError(
        "articlev2 histogram plotting requires pandas/numpy/matplotlib/PyYAML. "
        "Run `conda activate data` or use `conda run -n data python ...`."
    ) from error

from _common import (
    PROFILE_SLITS,
    SLIT_COLUMN,
    RunMetadata,
    discover_event_files,
    metadata_for_events,
    nested,
    parse_slits,
    profiles_for_slits,
    to_builtin,
)


HISTOGRAM_CSV_NAME = "scatter_position_histogram.csv"
HISTOGRAM_PNG_NAME = "scatter_position_histogram.png"
MANIFEST_NAME = "analysis_manifest.yaml"
CSV_FIELDS = (
    "condition_id", "phantom_id", "profile_ids", "scatter_point", "axis",
    "coordinate_field", "selected_slits", "bin_index", "bin_left_mm", "bin_right_mm",
    "count_total", "count_k1", "count_ms", "n_primary_total",
)


@dataclass(frozen=True)
class RunInfo:
    events_path: Path
    metadata: RunMetadata


@dataclass(frozen=True)
class BinSpec:
    start_mm: float
    end_mm: float
    width_mm: float
    edges_mm: tuple[float, ...]


def coordinate_field(scatter_point: str, axis: str) -> str:
    if scatter_point not in {"first", "last"}:
        raise ValueError("scatter_point must be first or last")
    if axis not in {"x", "y", "z"}:
        raise ValueError("axis must be x, y, or z")
    return f"{scatter_point}_scatter_{axis}"


def _base_signature(metadata: RunMetadata) -> dict[str, Any]:
    raw = metadata.raw
    return {
        "phantom_id": metadata.phantom_id,
        "scan_mode": metadata.scan_mode,
        "vehicle_geometry_file": raw.get("vehicle_geometry_file"),
        "model_type": raw.get("model_type"),
        "selected_target_component": raw.get("selected_target_component"),
        "abnormal_material": raw.get("abnormal_material"),
        "pose_id": metadata.pose_id,
        "head_offset_x_mm": metadata.head_offset_x_mm,
        "head_offset_y_mm": metadata.head_offset_y_mm,
        "energy_keV": metadata.energy_keV,
        "source": raw.get("source"),
        "physics": raw.get("physics"),
    }


def _profile_signature(metadata: RunMetadata) -> dict[str, Any]:
    return {
        **_base_signature(metadata),
        "profile_id": metadata.profile_id,
        "collimator": metadata.raw.get("collimator"),
        "detector": metadata.raw.get("detector"),
    }


def select_runs(
    input_root: Path,
    phantom_id: str,
    selected_slits: tuple[str, ...],
    events_name: str = "events_clean.csv",
) -> list[RunInfo]:
    requested_profiles = profiles_for_slits(selected_slits)
    files = discover_event_files(input_root, events_name)
    runs = [RunInfo(path, metadata_for_events(path)) for path in files]
    selected = sorted(
        (
            run for run in runs
            if run.metadata.phantom_id == phantom_id
            and run.metadata.profile_id in requested_profiles
        ),
        key=lambda run: run.events_path,
    )
    if not selected:
        raise ValueError(f"no articlev2 runs found for phantom_id={phantom_id}")

    found_profiles = {run.metadata.profile_id for run in selected}
    missing_profiles = sorted(set(requested_profiles).difference(found_profiles))
    if missing_profiles:
        raise ValueError(
            f"no runs found for requested slit profile(s) {missing_profiles}, phantom_id={phantom_id}"
        )
    first_base = _base_signature(selected[0].metadata)
    for run in selected[1:]:
        if _base_signature(run.metadata) != first_base:
            raise ValueError(
                "selected runs do not share one cross-profile physical condition: "
                f"{selected[0].metadata.metadata_path} versus {run.metadata.metadata_path}"
            )
    for profile_id in requested_profiles:
        profile_runs = [run for run in selected if run.metadata.profile_id == profile_id]
        signature = _profile_signature(profile_runs[0].metadata)
        for run in profile_runs[1:]:
            if _profile_signature(run.metadata) != signature:
                raise ValueError(
                    f"selected {profile_id} runs do not share one physical condition: "
                    f"{profile_runs[0].metadata.metadata_path} versus {run.metadata.metadata_path}"
                )
    return selected


def parse_non_negative_integer(value: Any, source: Path, row_number: int) -> int:
    try:
        number = float(value)
    except (TypeError, ValueError) as error:
        raise ValueError(
            f"scatter_count_total must be a non-negative integer in {source} row {row_number}: {value!r}"
        ) from error
    if not math.isfinite(number) or number < 0 or not number.is_integer():
        raise ValueError(
            f"scatter_count_total must be a non-negative integer in {source} row {row_number}: {value!r}"
        )
    return int(number)


def _selected_for_run(selected_slits: tuple[str, ...], profile_id: str) -> set[str]:
    return set(selected_slits).intersection(PROFILE_SLITS[profile_id])


def scan_maximum(run: RunInfo, field: str, selected_slits: tuple[str, ...], start_mm: float) -> float | None:
    maximum: float | None = None
    valid_slits = _selected_for_run(selected_slits, run.metadata.profile_id)
    with run.events_path.open("r", encoding="utf-8", newline="") as stream:
        reader = csv.DictReader(stream)
        if reader.fieldnames is None:
            raise ValueError(f"events CSV has no header: {run.events_path}")
        missing = sorted({SLIT_COLUMN, "scatter_count_total", field}.difference(reader.fieldnames))
        if missing:
            raise ValueError(f"events CSV is missing required columns {missing}: {run.events_path}")
        for row_number, row in enumerate(reader, start=2):
            slit_id = str(row.get(SLIT_COLUMN, "")).strip()
            if slit_id not in PROFILE_SLITS[run.metadata.profile_id]:
                raise ValueError(
                    f"slit_id {slit_id!r} does not belong to metadata profile "
                    f"{run.metadata.profile_id} in {run.events_path} row {row_number}"
                )
            scatter = parse_non_negative_integer(row.get("scatter_count_total"), run.events_path, row_number)
            if slit_id not in valid_slits or scatter == 0:
                continue
            try:
                coordinate = float(row.get(field, ""))
            except ValueError:
                continue
            if math.isfinite(coordinate) and coordinate >= start_mm:
                maximum = coordinate if maximum is None else max(maximum, coordinate)
    return maximum


def make_bin_spec(
    runs: list[RunInfo], field: str, selected_slits: tuple[str, ...],
    start_mm: float, bin_width_mm: float, end_mm: float | None,
) -> BinSpec:
    if not math.isfinite(start_mm):
        raise ValueError("start_mm must be finite")
    if not math.isfinite(bin_width_mm) or bin_width_mm <= 0:
        raise ValueError("bin_width_mm must be finite and positive")
    if end_mm is None:
        maxima = [scan_maximum(run, field, selected_slits, start_mm) for run in runs]
        finite_maxima = [value for value in maxima if value is not None]
        if not finite_maxima:
            raise ValueError("no selected positive-scatter coordinates are available for automatic bin range")
        end_mm = start_mm + math.ceil((max(finite_maxima) - start_mm) / bin_width_mm) * bin_width_mm
        if end_mm <= start_mm:
            end_mm = start_mm + bin_width_mm
    if not math.isfinite(end_mm) or end_mm <= start_mm:
        raise ValueError("end_mm must be finite and greater than start_mm")
    count_float = (end_mm - start_mm) / bin_width_mm
    count = round(count_float)
    if not math.isclose(count_float, count, rel_tol=0.0, abs_tol=1.0e-9):
        raise ValueError("end_mm - start_mm must be an integer multiple of bin_width_mm")
    edges = tuple(start_mm + index * bin_width_mm for index in range(count + 1))
    return BinSpec(start_mm, end_mm, bin_width_mm, edges)


def bin_run(run: RunInfo, field: str, selected_slits: tuple[str, ...], spec: BinSpec) -> dict[str, Any]:
    bin_count = len(spec.edges_mm) - 1
    total = [0] * bin_count
    k1 = [0] * bin_count
    ms = [0] * bin_count
    stats = {"zero_scatter_excluded": 0, "underflow": 0, "overflow": 0, "nonfinite_excluded": 0}
    valid_slits = _selected_for_run(selected_slits, run.metadata.profile_id)
    with run.events_path.open("r", encoding="utf-8", newline="") as stream:
        reader = csv.DictReader(stream)
        if reader.fieldnames is None:
            raise ValueError(f"events CSV has no header: {run.events_path}")
        missing = sorted({SLIT_COLUMN, "scatter_count_total", field}.difference(reader.fieldnames))
        if missing:
            raise ValueError(f"events CSV is missing required columns {missing}: {run.events_path}")
        for row_number, row in enumerate(reader, start=2):
            slit_id = str(row.get(SLIT_COLUMN, "")).strip()
            if slit_id not in PROFILE_SLITS[run.metadata.profile_id]:
                raise ValueError(
                    f"slit_id {slit_id!r} does not belong to metadata profile "
                    f"{run.metadata.profile_id} in {run.events_path} row {row_number}"
                )
            if slit_id not in valid_slits:
                continue
            scatter = parse_non_negative_integer(row.get("scatter_count_total"), run.events_path, row_number)
            if scatter == 0:
                stats["zero_scatter_excluded"] += 1
                continue
            try:
                coordinate = float(row.get(field, ""))
            except ValueError:
                coordinate = math.nan
            if not math.isfinite(coordinate):
                stats["nonfinite_excluded"] += 1
            elif coordinate < spec.start_mm:
                stats["underflow"] += 1
            elif coordinate > spec.end_mm:
                stats["overflow"] += 1
            else:
                index = min(int((coordinate - spec.start_mm) / spec.width_mm), bin_count - 1)
                total[index] += 1
                (k1 if scatter == 1 else ms)[index] += 1
    return {
        "run": run, "count_total": total, "count_k1": k1, "count_ms": ms,
        "binned_count": sum(total), "binned_k1_count": sum(k1), "binned_ms_count": sum(ms),
        **stats,
    }


def build_analysis(
    input_root: Path, phantom_id: str, scatter_point: str, axis: str,
    selected_slits: tuple[str, ...], start_mm: float, bin_width_mm: float,
    end_mm: float | None = None, events_name: str = "events_clean.csv",
) -> dict[str, Any]:
    field = coordinate_field(scatter_point, axis)
    runs = select_runs(input_root, phantom_id, selected_slits, events_name)
    spec = make_bin_spec(runs, field, selected_slits, start_mm, bin_width_mm, end_mm)
    run_results = [bin_run(run, field, selected_slits, spec) for run in runs]
    profiles = profiles_for_slits(selected_slits)
    n_primary_total = sum(run.metadata.n_primary for run in runs)
    first = runs[0].metadata
    condition_id = (
        f"articlev2_{first.scan_mode}_{phantom_id}_{'-'.join(profiles)}_"
        f"E{first.energy_keV:g}_{first.pose_id}"
    )
    rows: list[dict[str, Any]] = []
    for index, (left, right) in enumerate(zip(spec.edges_mm, spec.edges_mm[1:])):
        total = sum(result["count_total"][index] for result in run_results)
        k1 = sum(result["count_k1"][index] for result in run_results)
        ms = sum(result["count_ms"][index] for result in run_results)
        if total != k1 + ms:
            raise AssertionError("histogram count partition failed")
        rows.append({
            "condition_id": condition_id, "phantom_id": phantom_id,
            "profile_ids": ",".join(profiles), "scatter_point": scatter_point,
            "axis": axis, "coordinate_field": field,
            "selected_slits": ",".join(selected_slits), "bin_index": index,
            "bin_left_mm": left, "bin_right_mm": right,
            "count_total": total, "count_k1": k1, "count_ms": ms,
            "n_primary_total": n_primary_total,
        })
    return {
        "input_root": input_root, "phantom_id": phantom_id, "profile_ids": profiles,
        "scatter_point": scatter_point, "axis": axis, "coordinate_field": field,
        "selected_slits": selected_slits, "condition_id": condition_id,
        "bin_spec": spec, "runs": runs, "run_results": run_results,
        "n_primary_total": n_primary_total, "rows": rows,
    }


def write_histogram_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    with path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=CSV_FIELDS)
        writer.writeheader()
        writer.writerows(rows)


def write_histogram_plot(path: Path, analysis: dict[str, Any]) -> None:
    rows = analysis["rows"]
    centers = np.array([(row["bin_left_mm"] + row["bin_right_mm"]) / 2 for row in rows])
    width = analysis["bin_spec"].width_mm * 0.82
    k1 = np.array([row["count_k1"] for row in rows])
    ms = np.array([row["count_ms"] for row in rows])
    fig, ax = plt.subplots(figsize=(9.2, 5.6), constrained_layout=True)
    ax.bar(centers, k1, width=width, label="k1", color="#4C78A8")
    ax.bar(centers, ms, width=width, bottom=k1, label="ms", color="#F58518")
    ax.set_xlabel(f"{analysis['coordinate_field']} [mm]")
    ax.set_ylabel("count")
    ax.set_title(
        f"{analysis['phantom_id']} | slits={','.join(analysis['selected_slits'])} | "
        f"profiles={','.join(analysis['profile_ids'])}"
    )
    ax.legend()
    fig.savefig(path, dpi=180)
    plt.close(fig)


def write_manifest(path: Path, analysis: dict[str, Any], csv_path: Path, plot_path: Path) -> None:
    manifest = {
        "script": Path(__file__), "input_root": analysis["input_root"],
        "condition_id": analysis["condition_id"], "phantom_id": analysis["phantom_id"],
        "profile_ids": analysis["profile_ids"], "selected_slits": analysis["selected_slits"],
        "scatter_point": analysis["scatter_point"], "axis": analysis["axis"],
        "coordinate_field": analysis["coordinate_field"],
        "binning": {
            "start_mm": analysis["bin_spec"].start_mm,
            "end_mm": analysis["bin_spec"].end_mm,
            "width_mm": analysis["bin_spec"].width_mm,
            "final_right_edge_inclusive": True,
        },
        "aggregation": {"mode": "condition_total", "n_primary_total": analysis["n_primary_total"]},
        "inputs": [
            {
                "events_file": run.events_path, "metadata_file": run.metadata.metadata_path,
                "profile_id": run.metadata.profile_id, "case_id": run.metadata.case_id,
                "run_id": run.metadata.run_id, "n_primary": run.metadata.n_primary,
            }
            for run in analysis["runs"]
        ],
        "exclusions": [
            {key: result[key] for key in (
                "zero_scatter_excluded", "underflow", "overflow", "nonfinite_excluded"
            )}
            for result in analysis["run_results"]
        ],
        "outputs": {"histogram_csv": csv_path, "histogram_png": plot_path},
    }
    with path.open("w", encoding="utf-8") as stream:
        yaml.safe_dump(to_builtin(manifest), stream, sort_keys=False, allow_unicode=False, width=100)


def ensure_output_dir(path: Path, overwrite: bool) -> None:
    products = (HISTOGRAM_CSV_NAME, HISTOGRAM_PNG_NAME, MANIFEST_NAME)
    existing = [path / name for name in products if (path / name).exists()]
    if existing and not overwrite:
        raise FileExistsError(f"analysis output already exists; use --overwrite: {existing[0]}")
    path.mkdir(parents=True, exist_ok=True)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input-root", type=Path, required=True)
    parser.add_argument("--phantom-id", required=True)
    parser.add_argument("--scatter-point", choices=("first", "last"), required=True)
    parser.add_argument("--axis", choices=("x", "y", "z"), required=True)
    parser.add_argument("--slits", required=True, help="comma-separated S1-S6 selection")
    parser.add_argument("--start-mm", type=float, default=0.0)
    parser.add_argument("--bin-width-mm", type=float, default=2.0)
    parser.add_argument("--end-mm", type=float)
    parser.add_argument("--events-name", default="events_clean.csv")
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--overwrite", action="store_true")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    selected_slits = parse_slits(args.slits)
    ensure_output_dir(args.output_dir, args.overwrite)
    analysis = build_analysis(
        args.input_root, args.phantom_id, args.scatter_point, args.axis, selected_slits,
        args.start_mm, args.bin_width_mm, args.end_mm, args.events_name,
    )
    csv_path = args.output_dir / HISTOGRAM_CSV_NAME
    plot_path = args.output_dir / HISTOGRAM_PNG_NAME
    manifest_path = args.output_dir / MANIFEST_NAME
    write_histogram_csv(csv_path, analysis["rows"])
    write_histogram_plot(plot_path, analysis)
    write_manifest(manifest_path, analysis, csv_path, plot_path)
    print(f"processed {len(analysis['runs'])} run(s)")
    print(f"histogram: {csv_path}")
    print(f"plot: {plot_path}")
    print(f"manifest: {manifest_path}")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as error:
        print(f"error: {error}", file=sys.stderr)
        raise SystemExit(1) from error
