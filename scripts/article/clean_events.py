#!/usr/bin/env python3
"""Clean article experiment events.csv files and assign slit channels."""

from __future__ import annotations

import argparse
import csv
import math
import shutil
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

try:
    import yaml
except ModuleNotFoundError as error:  # pragma: no cover - exercised by CLI users.
    raise RuntimeError(
        "article event cleaning requires PyYAML. "
        "Run `conda activate data` or use `conda run -n data python ...`."
    ) from error


# Edit these two lists directly when the detector-x slit windows change.
# The i-th [left, right] interval is written as slit_id S{i + 1}.
DET_X_LEFT_EDGES_MM = [17.24, 84.21, 126.44]
DET_X_RIGHT_EDGES_MM = [27.10, 94.54, 136.04]

SLIT_COLUMN = "slit_id"
SUMMARY_CSV_NAME = "clean_summary.csv"
MANIFEST_YAML_NAME = "clean_manifest.yaml"
METADATA_NAME = "metadata.yaml"

DROP_COLUMNS = {
    "event_id",
    "hit_id",
    "track_id",
    "parent_id",
    "is_primary_gamma",
    "gamma_source_type",
    "gamma_source_process",
    "gamma_source_region_id",
    "rayleigh_count",
}

REQUIRED_COLUMNS = {
    "det_x",
    "first_scatter_z",
    "last_scatter_z",
}


@dataclass(frozen=True)
class RangeSpec:
    slit_id: str
    left_mm: float
    right_mm: float


def shifted_det_x_ranges(ranges: list[RangeSpec], head_offset_x_mm: float) -> list[RangeSpec]:
    return [
        RangeSpec(item.slit_id, item.left_mm + head_offset_x_mm, item.right_mm + head_offset_x_mm)
        for item in ranges
    ]


def validate_det_x_ranges(
    left_edges: list[float] | tuple[float, ...] = DET_X_LEFT_EDGES_MM,
    right_edges: list[float] | tuple[float, ...] = DET_X_RIGHT_EDGES_MM,
) -> list[RangeSpec]:
    if len(left_edges) != len(right_edges):
        raise ValueError("DET_X_LEFT_EDGES_MM and DET_X_RIGHT_EDGES_MM must have the same length")
    if not left_edges:
        raise ValueError("at least one det_x interval is required")

    ranges: list[RangeSpec] = []
    for index, (left, right) in enumerate(zip(left_edges, right_edges, strict=True), start=1):
        left_value = float(left)
        right_value = float(right)
        if not math.isfinite(left_value) or not math.isfinite(right_value):
            raise ValueError("det_x interval endpoints must be finite")
        if left_value > right_value:
            raise ValueError(f"invalid det_x interval for S{index}: left > right")
        ranges.append(RangeSpec(f"S{index}", left_value, right_value))

    sorted_ranges = sorted(ranges, key=lambda item: item.left_mm)
    for previous, current in zip(sorted_ranges, sorted_ranges[1:]):
        if current.left_mm <= previous.right_mm:
            raise ValueError(
                "det_x intervals must not overlap because endpoints are inclusive: "
                f"{previous.slit_id}=[{previous.left_mm}, {previous.right_mm}], "
                f"{current.slit_id}=[{current.left_mm}, {current.right_mm}]"
            )
    return ranges


def slit_for_det_x(det_x: float, ranges: list[RangeSpec]) -> str | None:
    matches = [item.slit_id for item in ranges if item.left_mm <= det_x <= item.right_mm]
    if not matches:
        return None
    if len(matches) > 1:
        raise ValueError(f"det_x={det_x} matched multiple slit intervals: {matches}")
    return matches[0]


def read_metadata_for_events(event_file: Path) -> dict[str, Any]:
    metadata_path = event_file.parent / METADATA_NAME
    if not metadata_path.is_file():
        raise FileNotFoundError(f"metadata file not found beside events file: {metadata_path}")
    with metadata_path.open("r", encoding="utf-8") as stream:
        metadata = yaml.safe_load(stream)
    if not isinstance(metadata, dict):
        raise ValueError(f"metadata root must be a map: {metadata_path}")
    return metadata


def head_offset_x_from_metadata(metadata: dict[str, Any], source: Path) -> float:
    value = metadata.get("head_offset_x_mm")
    try:
        offset_x = float(value)
    except (TypeError, ValueError) as error:
        raise ValueError(f"metadata head_offset_x_mm must be numeric in {source}: {value!r}") from error
    if not math.isfinite(offset_x):
        raise ValueError(f"metadata head_offset_x_mm must be finite in {source}: {value!r}")
    return offset_x


def parse_required_float(row: dict[str, str], field: str, source: Path) -> float:
    value = row.get(field)
    try:
        number = float(value) if value is not None else math.nan
    except ValueError as error:
        raise ValueError(f"{field} must be numeric in {source}: {value!r}") from error
    return number


def format_value(value: Any) -> Any:
    if isinstance(value, float):
        if math.isnan(value):
            return "NaN"
        return f"{value:.12g}"
    return value


def to_builtin(value: Any) -> Any:
    if isinstance(value, Path):
        return value.as_posix()
    if isinstance(value, RangeSpec):
        return {
            "slit_id": value.slit_id,
            "left_mm": value.left_mm,
            "right_mm": value.right_mm,
        }
    if isinstance(value, dict):
        return {str(key): to_builtin(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [to_builtin(item) for item in value]
    return value


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


def output_path_for(input_root: Path, event_file: Path, output_root: Path, output_name: str) -> Path:
    if input_root.is_file():
        relative_dir = Path()
    else:
        relative_dir = event_file.parent.resolve().relative_to(input_root.resolve())
    return output_root / relative_dir / output_name


def check_header(fieldnames: list[str] | None, source: Path) -> list[str]:
    if fieldnames is None:
        raise ValueError(f"events CSV has no header: {source}")
    missing = sorted(REQUIRED_COLUMNS.difference(fieldnames))
    if missing:
        raise ValueError(f"events CSV is missing required columns {missing}: {source}")
    output_fields = [field for field in fieldnames if field not in DROP_COLUMNS and field != SLIT_COLUMN]
    output_fields.append(SLIT_COLUMN)
    return output_fields


def copy_metadata_if_present(event_file: Path, output_file: Path, overwrite: bool) -> bool:
    source = event_file.parent / METADATA_NAME
    if not source.is_file():
        return False
    destination = output_file.parent / METADATA_NAME
    if destination.exists() and not overwrite:
        raise FileExistsError(f"metadata output already exists: {destination}")
    shutil.copy2(source, destination)
    return True


def clean_one_file(
    event_file: Path,
    output_file: Path,
    ranges: list[RangeSpec],
    overwrite: bool,
) -> dict[str, Any]:
    if output_file.exists() and not overwrite:
        raise FileExistsError(f"output already exists: {output_file}")
    metadata = read_metadata_for_events(event_file)
    metadata_path = event_file.parent / METADATA_NAME
    head_offset_x_mm = head_offset_x_from_metadata(metadata, metadata_path)
    actual_ranges = shifted_det_x_ranges(ranges, head_offset_x_mm)
    output_file.parent.mkdir(parents=True, exist_ok=True)

    rows_read = 0
    rows_kept = 0
    slit_counts = {item.slit_id: 0 for item in actual_ranges}

    with event_file.open("r", encoding="utf-8", newline="") as input_stream:
        reader = csv.DictReader(input_stream)
        output_fields = check_header(reader.fieldnames, event_file)
        with output_file.open("w", encoding="utf-8", newline="") as output_stream:
            writer = csv.DictWriter(output_stream, fieldnames=output_fields)
            writer.writeheader()

            for row in reader:
                rows_read += 1
                first_z = parse_required_float(row, "first_scatter_z", event_file)
                last_z = parse_required_float(row, "last_scatter_z", event_file)
                det_x = parse_required_float(row, "det_x", event_file)
                if not (math.isfinite(first_z) and math.isfinite(last_z) and math.isfinite(det_x)):
                    continue
                if first_z < 0.0 or last_z < 0.0:
                    continue
                slit_id = slit_for_det_x(det_x, actual_ranges)
                if slit_id is None:
                    continue

                output_row = {field: row.get(field, "") for field in output_fields if field != SLIT_COLUMN}
                output_row[SLIT_COLUMN] = slit_id
                writer.writerow(output_row)
                rows_kept += 1
                slit_counts[slit_id] += 1

    copied_metadata = copy_metadata_if_present(event_file, output_file, overwrite)
    kept_fraction = rows_kept / rows_read if rows_read else math.nan
    summary: dict[str, Any] = {
        "input_file": event_file.as_posix(),
        "output_file": output_file.as_posix(),
        "rows_read": rows_read,
        "rows_kept": rows_kept,
        "kept_fraction": kept_fraction,
        "metadata_copied": copied_metadata,
        "head_offset_x_mm": head_offset_x_mm,
        "shifted_det_x_ranges_mm": actual_ranges,
    }
    for range_spec in actual_ranges:
        slit_id = range_spec.slit_id
        summary[f"{slit_id}_left_mm"] = range_spec.left_mm
        summary[f"{slit_id}_right_mm"] = range_spec.right_mm
        summary[f"{slit_id}_rows_kept"] = slit_counts[slit_id]
    return summary


def write_summary_csv(path: Path, rows: list[dict[str, Any]], ranges: list[RangeSpec], overwrite: bool) -> None:
    if path.exists() and not overwrite:
        raise FileExistsError(f"summary output already exists: {path}")
    fieldnames = [
        "input_file",
        "output_file",
        "rows_read",
        "rows_kept",
        "kept_fraction",
        "metadata_copied",
        "head_offset_x_mm",
        *[field for item in ranges for field in (f"{item.slit_id}_left_mm", f"{item.slit_id}_right_mm")],
        *[f"{item.slit_id}_rows_kept" for item in ranges],
    ]
    with path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow({field: format_value(row.get(field, "")) for field in fieldnames})


def write_manifest(path: Path, manifest: dict[str, Any], overwrite: bool) -> None:
    if path.exists() and not overwrite:
        raise FileExistsError(f"manifest output already exists: {path}")
    with path.open("w", encoding="utf-8") as stream:
        yaml.safe_dump(to_builtin(manifest), stream, sort_keys=False, allow_unicode=False, width=100)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input-root", type=Path, required=True)
    parser.add_argument("--output-root", type=Path, required=True)
    parser.add_argument("--events-name", default="events.csv")
    parser.add_argument("--output-name", default="events_clean.csv")
    parser.add_argument("--overwrite", action="store_true")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    ranges = validate_det_x_ranges()
    event_files = discover_event_files(args.input_root, args.events_name)
    if not event_files:
        raise FileNotFoundError(f"no {args.events_name} files found under {args.input_root}")

    args.output_root.mkdir(parents=True, exist_ok=True)
    summaries: list[dict[str, Any]] = []
    for event_file in event_files:
        output_file = output_path_for(args.input_root, event_file, args.output_root, args.output_name)
        summaries.append(clean_one_file(event_file, output_file, ranges, args.overwrite))

    summary_path = args.output_root / SUMMARY_CSV_NAME
    write_summary_csv(summary_path, summaries, ranges, args.overwrite)
    manifest_path = args.output_root / MANIFEST_YAML_NAME
    write_manifest(
        manifest_path,
        {
            "script": Path(__file__).as_posix(),
            "input_root": args.input_root,
            "output_root": args.output_root,
            "events_name": args.events_name,
            "output_name": args.output_name,
            "det_x_ranges_mm": ranges,
            "det_x_ranges_zero_pose_mm": ranges,
            "drop_columns": sorted(DROP_COLUMNS),
            "input_file_count": len(event_files),
            "summary_csv": summary_path,
            "files": summaries,
        },
        args.overwrite,
    )
    print(f"cleaned {len(event_files)} file(s)")
    print(f"summary: {summary_path}")
    print(f"manifest: {manifest_path}")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as error:
        print(f"error: {error}", file=sys.stderr)
        raise SystemExit(1) from error
