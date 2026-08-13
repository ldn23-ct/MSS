#!/usr/bin/env python3
"""Summarize articlev2 total/k1/ms counts using each run's metadata profile."""

from __future__ import annotations

import argparse
import csv
import math
import sys
from pathlib import Path
from typing import Any

from _common import (
    ALL_SLIT_ID,
    PROFILE_SLITS,
    SLIT_COLUMN,
    discover_event_files,
    metadata_for_events,
    relative_file_for,
)


SCATTER_COLUMN = "scatter_count_total"
OUTPUT_FIELDS = (
    "input_file", "relative_file", "scan_mode", "phantom_id", "profile_id", "pose_id",
    "head_offset_x_mm", "head_offset_y_mm", "energy_keV", "n_primary", "slit_id",
    "N_total", "N_k1", "N_ms",
)


def parse_scatter_count(value: Any, source: Path, row_number: int) -> int:
    try:
        numeric = float(value)
    except (TypeError, ValueError) as error:
        raise ValueError(
            f"{SCATTER_COLUMN} must be a non-negative integer in {source} row {row_number}: {value!r}"
        ) from error
    if not math.isfinite(numeric) or numeric < 0 or not numeric.is_integer():
        raise ValueError(
            f"{SCATTER_COLUMN} must be a non-negative integer in {source} row {row_number}: {value!r}"
        )
    return int(numeric)


def count_scatter_by_slit(event_file: Path, profile_id: str) -> dict[str, dict[str, int]]:
    slit_ids = PROFILE_SLITS[profile_id]
    counts = {slit_id: {"N_total": 0, "N_k1": 0, "N_ms": 0} for slit_id in slit_ids}
    with event_file.open("r", encoding="utf-8", newline="") as stream:
        reader = csv.DictReader(stream)
        if reader.fieldnames is None:
            raise ValueError(f"events CSV has no header: {event_file}")
        missing = sorted({SLIT_COLUMN, SCATTER_COLUMN}.difference(reader.fieldnames))
        if missing:
            raise ValueError(f"events CSV is missing required columns {missing}: {event_file}")
        for row_number, row in enumerate(reader, start=2):
            slit_id = str(row.get(SLIT_COLUMN, "")).strip()
            if slit_id not in counts:
                raise ValueError(
                    f"{SLIT_COLUMN} must belong to metadata profile {profile_id} {slit_ids} "
                    f"in {event_file} row {row_number}: {slit_id!r}"
                )
            scatter_count = parse_scatter_count(row.get(SCATTER_COLUMN), event_file, row_number)
            if scatter_count == 0:
                continue
            counts[slit_id]["N_total"] += 1
            counts[slit_id]["N_k1" if scatter_count == 1 else "N_ms"] += 1
    for slit_id, values in counts.items():
        if values["N_total"] != values["N_k1"] + values["N_ms"]:
            raise AssertionError(f"count partition failed for {event_file} {slit_id}")
    return counts


def summarize_event_file(input_root: Path, event_file: Path) -> list[dict[str, Any]]:
    metadata = metadata_for_events(event_file)
    counts = count_scatter_by_slit(event_file, metadata.profile_id)
    combined = {
        field: sum(values[field] for values in counts.values())
        for field in ("N_total", "N_k1", "N_ms")
    }
    common = {
        "input_file": event_file.as_posix(),
        "relative_file": relative_file_for(input_root, event_file),
        "scan_mode": metadata.scan_mode,
        "phantom_id": metadata.phantom_id,
        "profile_id": metadata.profile_id,
        "pose_id": metadata.pose_id,
        "head_offset_x_mm": metadata.head_offset_x_mm,
        "head_offset_y_mm": metadata.head_offset_y_mm,
        "energy_keV": metadata.energy_keV,
        "n_primary": metadata.n_primary,
    }
    return [
        {**common, "slit_id": slit_id, **(combined if slit_id == ALL_SLIT_ID else counts[slit_id])}
        for slit_id in (*PROFILE_SLITS[metadata.profile_id], ALL_SLIT_ID)
    ]


def summarize_input(input_root: Path, events_name: str = "events_clean.csv") -> list[dict[str, Any]]:
    files = discover_event_files(input_root, events_name)
    if not files:
        raise FileNotFoundError(f"no {events_name} files found under {input_root}")
    return [row for event_file in files for row in summarize_event_file(input_root, event_file)]


def write_summary_csv(path: Path, rows: list[dict[str, Any]], overwrite: bool = False) -> None:
    if path.exists() and not overwrite:
        raise FileExistsError(f"summary output already exists: {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=OUTPUT_FIELDS)
        writer.writeheader()
        writer.writerows(rows)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input-root", type=Path, required=True)
    parser.add_argument("--output-csv", type=Path, required=True)
    parser.add_argument("--events-name", default="events_clean.csv")
    parser.add_argument("--overwrite", action="store_true")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    rows = summarize_input(args.input_root, args.events_name)
    resolved_output = args.output_csv.resolve()
    if resolved_output in discover_event_files(args.input_root, args.events_name):
        raise ValueError(f"output CSV must not overwrite an input events file: {args.output_csv}")
    write_summary_csv(args.output_csv, rows, args.overwrite)
    print(f"summarized {len(rows) // 4} file(s)")
    print(f"summary: {args.output_csv}")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as error:
        print(f"error: {error}", file=sys.stderr)
        raise SystemExit(1) from error
