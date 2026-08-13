#!/usr/bin/env python3
"""Create canonical valid Article V2 events with frozen slit-channel labels."""

from __future__ import annotations

import argparse
import csv
import hashlib
import math
import shutil
import sys
import tempfile
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml

from .common import (
    METADATA_NAME,
    PROFILE_SLITS,
    SLIT_GROUP_COLUMN,
    SLIT_LABEL_COLUMN,
    VALID_EVENT_DROP_COLUMNS,
    discover_event_files,
    metadata_for_events,
)
from .estimate_slit_boundaries import BOUNDARY_CONFIG_NAME, main as estimate_boundaries_main
from .slit_channels import load_boundary_config, profile_boundaries, slit_label_for_x


OUTPUT_NAME = "events_valid.csv"
SUMMARY_NAME = "valid_events_summary.csv"
MANIFEST_NAME = "valid_events_manifest.yaml"
REQUIRED_COLUMNS = {"det_x", "first_scatter_z", "last_scatter_z"}
ADDED_COLUMNS = (SLIT_GROUP_COLUMN, SLIT_LABEL_COLUMN)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def parse_float(value: str | None, field: str, source: Path, line: int) -> float:
    try:
        return float(value) if value is not None else math.nan
    except ValueError as error:
        raise ValueError(f"{field} must be numeric at {source}:{line}: {value!r}") from error


def output_fields(fieldnames: list[str] | None, source: Path) -> list[str]:
    if fieldnames is None:
        raise ValueError(f"events CSV has no header: {source}")
    missing = sorted(REQUIRED_COLUMNS.difference(fieldnames))
    if missing:
        raise ValueError(f"events CSV is missing required columns {missing}: {source}")
    conflicts = sorted(set(ADDED_COLUMNS).intersection(fieldnames))
    if conflicts:
        raise ValueError(f"raw events already contain derived columns {conflicts}: {source}")
    return [field for field in fieldnames if field not in VALID_EVENT_DROP_COLUMNS] + list(
        ADDED_COLUMNS
    )


def valid_output_path(input_root: Path, event_file: Path, staging_root: Path) -> Path:
    relative_dir = (
        Path()
        if input_root.is_file()
        else event_file.parent.resolve().relative_to(input_root.resolve())
    )
    return staging_root / relative_dir / OUTPUT_NAME


def clean_and_label_file(
    event_file: Path,
    output_file: Path,
    boundary_config: dict[str, Any],
) -> dict[str, Any]:
    """Filter only invalid depths, drop legacy columns, and append frozen labels."""
    metadata = metadata_for_events(event_file)
    profile_id = metadata.profile_id
    boundaries = profile_boundaries(boundary_config, profile_id)
    shifted_boundaries = tuple(value + metadata.head_offset_x_mm for value in boundaries)
    slit_counts = {slit: 0 for slit in PROFILE_SLITS[profile_id]}
    rows_read = 0
    rows_kept = 0
    rows_dropped_nonfinite_depth = 0
    rows_dropped_negative_depth = 0
    output_file.parent.mkdir(parents=True, exist_ok=True)

    with event_file.open("r", encoding="utf-8", newline="") as input_stream:
        reader = csv.DictReader(input_stream)
        fields = output_fields(reader.fieldnames, event_file)
        with output_file.open("w", encoding="utf-8", newline="") as output_stream:
            writer = csv.DictWriter(output_stream, fieldnames=fields)
            writer.writeheader()
            for line, row in enumerate(reader, start=2):
                rows_read += 1
                first_z = parse_float(row.get("first_scatter_z"), "first_scatter_z", event_file, line)
                last_z = parse_float(row.get("last_scatter_z"), "last_scatter_z", event_file, line)
                if not (math.isfinite(first_z) and math.isfinite(last_z)):
                    rows_dropped_nonfinite_depth += 1
                    continue
                if first_z < 0 or last_z < 0:
                    rows_dropped_negative_depth += 1
                    continue
                det_x = parse_float(row.get("det_x"), "det_x", event_file, line)
                if not math.isfinite(det_x):
                    raise ValueError(f"det_x must be finite at {event_file}:{line}: {row.get('det_x')!r}")
                slit_label = slit_label_for_x(
                    det_x, profile_id, boundaries, metadata.head_offset_x_mm
                )
                output_row = {
                    field: row.get(field, "")
                    for field in fields
                    if field not in ADDED_COLUMNS
                }
                output_row[SLIT_GROUP_COLUMN] = profile_id
                output_row[SLIT_LABEL_COLUMN] = slit_label
                writer.writerow(output_row)
                rows_kept += 1
                slit_counts[slit_label] += 1

    if rows_read != rows_kept + rows_dropped_nonfinite_depth + rows_dropped_negative_depth:
        raise AssertionError(f"valid-event row accounting failed: {event_file}")
    shutil.copy2(metadata.metadata_path, output_file.parent / METADATA_NAME)
    return {
        "input_file": event_file.as_posix(),
        "output_file": output_file.as_posix(),
        "scan_mode": metadata.scan_mode,
        "phantom_id": metadata.phantom_id,
        "profile_id": profile_id,
        "pose_id": metadata.pose_id,
        "head_offset_x_mm": metadata.head_offset_x_mm,
        "head_offset_y_mm": metadata.head_offset_y_mm,
        "energy_keV": metadata.energy_keV,
        "n_primary": metadata.n_primary,
        "boundary_1_zero_mm": boundaries[0],
        "boundary_2_zero_mm": boundaries[1],
        "boundary_1_applied_mm": shifted_boundaries[0],
        "boundary_2_applied_mm": shifted_boundaries[1],
        "rows_read": rows_read,
        "rows_kept": rows_kept,
        "rows_dropped_nonfinite_depth": rows_dropped_nonfinite_depth,
        "rows_dropped_negative_depth": rows_dropped_negative_depth,
        "kept_fraction": rows_kept / rows_read if rows_read else math.nan,
        "slit_counts": slit_counts,
    }


def ensure_boundary_config(results_root: Path, boundary_config_path: Path) -> str:
    """Reuse a valid frozen config, or calibrate once from unfiltered raw baseline hits."""
    if boundary_config_path.is_file():
        load_boundary_config(boundary_config_path)
        return "reused"
    if boundary_config_path.name != BOUNDARY_CONFIG_NAME:
        raise ValueError(
            f"missing custom boundary config cannot be auto-calibrated; expected filename "
            f"{BOUNDARY_CONFIG_NAME}: {boundary_config_path}"
        )
    arguments = [
        "--results-root", str(results_root),
        "--output-dir", str(boundary_config_path.parent),
    ]
    if boundary_config_path.parent.exists():
        arguments.append("--overwrite")
    estimate_boundaries_main(arguments)
    load_boundary_config(boundary_config_path)
    return "calibrated"


def relative_to_campaign(path: Path, results_root: Path) -> str:
    try:
        return path.resolve().relative_to(results_root.resolve()).as_posix()
    except ValueError:
        return path.resolve().as_posix()


def write_summary(
    path: Path,
    summaries: list[dict[str, Any]],
    staging_root: Path,
    results_root: Path,
) -> None:
    fields = [
        "input_file", "output_file", "scan_mode", "phantom_id", "profile_id", "pose_id",
        "head_offset_x_mm", "head_offset_y_mm", "energy_keV", "n_primary",
        "boundary_1_zero_mm", "boundary_2_zero_mm", "boundary_1_applied_mm",
        "boundary_2_applied_mm", "rows_read", "rows_kept",
        "rows_dropped_nonfinite_depth", "rows_dropped_negative_depth", "kept_fraction",
        "S1_count", "S2_count", "S3_count", "S4_count", "S5_count", "S6_count",
    ]
    with path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        for summary in summaries:
            row = {
                **summary,
                "input_file": relative_to_campaign(Path(summary["input_file"]), results_root),
                "output_file": Path(summary["output_file"]).relative_to(staging_root).as_posix(),
                **{
                    f"S{index}_count": summary["slit_counts"].get(f"S{index}", 0)
                    for index in range(1, 7)
                },
            }
            writer.writerow({field: row.get(field, "") for field in fields})


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--results-root", type=Path, required=True)
    parser.add_argument("--input-root", type=Path)
    parser.add_argument("--output-root", type=Path)
    parser.add_argument("--boundary-config", type=Path)
    parser.add_argument("--events-name", default="events.csv")
    parser.add_argument("--overwrite", action="store_true")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    results_root = args.results_root.resolve()
    input_root = (args.input_root or results_root / "events" / "raw").resolve()
    output_root = (args.output_root or results_root / "events" / "valid").resolve()
    boundary_path = (
        args.boundary_config
        or results_root / "data_processing" / "slit_channels" / BOUNDARY_CONFIG_NAME
    ).resolve()
    if output_root in {results_root, input_root}:
        raise ValueError("output root must differ from results root and raw input root")
    if output_root.exists() and not args.overwrite:
        raise FileExistsError(f"output root exists; pass --overwrite: {output_root}")
    boundary_action = ensure_boundary_config(results_root, boundary_path)
    boundary_config = load_boundary_config(boundary_path)
    files = discover_event_files(input_root, args.events_name)
    if not files:
        raise FileNotFoundError(f"no {args.events_name} files found under {input_root}")

    output_root.parent.mkdir(parents=True, exist_ok=True)
    staging = Path(
        tempfile.mkdtemp(prefix=f".{output_root.name}.staging-", dir=output_root.parent)
    )
    try:
        summaries: list[dict[str, Any]] = []
        for index, event_file in enumerate(files, start=1):
            summary = clean_and_label_file(
                event_file,
                valid_output_path(input_root, event_file, staging),
                boundary_config,
            )
            summaries.append(summary)
            if index % 25 == 0 or index == len(files):
                print(f"prepared {index}/{len(files)} files", flush=True)
        write_summary(staging / SUMMARY_NAME, summaries, staging, results_root)
        slit_totals = {f"S{index}": 0 for index in range(1, 7)}
        for summary in summaries:
            for slit, count in summary["slit_counts"].items():
                slit_totals[slit] += int(count)
        manifest = {
            "schema_version": 1,
            "created_utc": datetime.now(timezone.utc).isoformat(),
            "input_root": relative_to_campaign(input_root, results_root),
            "output_root": relative_to_campaign(output_root, results_root),
            "events_name": args.events_name,
            "output_name": OUTPUT_NAME,
            "boundary_config": relative_to_campaign(boundary_path, results_root),
            "boundary_config_sha256": sha256_file(boundary_path),
            "boundary_action": boundary_action,
            "depth_filter": (
                "keep iff first_scatter_z and last_scatter_z are finite and both >= 0"
            ),
            "detector_roi_filter": "none",
            "coordinate_rule": (
                "apply frozen zero-offset boundaries plus metadata head_offset_x_mm"
            ),
            "interval_rule": "left: x < b1; middle: b1 <= x < b2; right: x >= b2",
            "drop_columns": sorted(VALID_EVENT_DROP_COLUMNS),
            "added_columns": list(ADDED_COLUMNS),
            "input_file_count": len(files),
            "total_rows_read": sum(item["rows_read"] for item in summaries),
            "total_rows_kept": sum(item["rows_kept"] for item in summaries),
            "total_rows_dropped_nonfinite_depth": sum(
                item["rows_dropped_nonfinite_depth"] for item in summaries
            ),
            "total_rows_dropped_negative_depth": sum(
                item["rows_dropped_negative_depth"] for item in summaries
            ),
            "slit_counts": slit_totals,
            "summary_csv": SUMMARY_NAME,
            "files": [
                {
                    **{
                        key: value
                        for key, value in summary.items()
                        if key not in {"slit_counts", "input_file", "output_file"}
                    },
                    "input_file": relative_to_campaign(
                        Path(summary["input_file"]), results_root
                    ),
                    "output_file": Path(summary["output_file"]).relative_to(staging).as_posix(),
                    "slit_counts": summary["slit_counts"],
                }
                for summary in summaries
            ],
        }
        (staging / MANIFEST_NAME).write_text(
            yaml.safe_dump(manifest, sort_keys=False, allow_unicode=True, width=110),
            encoding="utf-8",
        )
        if output_root.exists():
            if not args.overwrite:
                raise FileExistsError(f"output root exists; pass --overwrite: {output_root}")
            backup = output_root.parent / f".{output_root.name}.backup-{uuid.uuid4().hex}"
            output_root.replace(backup)
            try:
                staging.replace(output_root)
            except Exception:
                backup.replace(output_root)
                raise
            shutil.rmtree(backup)
        else:
            staging.replace(output_root)
    except Exception:
        shutil.rmtree(staging, ignore_errors=True)
        raise

    print(f"valid files: {manifest['input_file_count']}")
    print(f"rows read: {manifest['total_rows_read']}")
    print(f"rows kept: {manifest['total_rows_kept']}")
    print(f"boundary config: {boundary_path} ({boundary_action})")
    print(f"summary: {output_root / SUMMARY_NAME}")
    print(f"manifest: {output_root / MANIFEST_NAME}")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as error:
        print(f"error: {error}", file=sys.stderr)
        raise SystemExit(1) from error
