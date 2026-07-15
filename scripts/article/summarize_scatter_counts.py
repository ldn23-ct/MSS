#!/usr/bin/env python3
"""Summarize valid scatter counts in cleaned article event files."""

from __future__ import annotations

import argparse
import csv
import math
import sys
from pathlib import Path
from typing import Any


SLIT_IDS = ("S1", "S2", "S3")
ALL_SLIT_ID = "ALL"
SLIT_COLUMN = "slit_id"
SCATTER_COLUMN = "scatter_count_total"
OUTPUT_FIELDS = ("input_file", "relative_file", "slit_id", "N_total", "N_k1", "N_ms")


def discover_event_files(input_root: Path, events_name: str) -> list[Path]:
    if input_root.is_file():
        if input_root.name != events_name:
            raise ValueError(f"input file must be named {events_name}: {input_root}")
        return [input_root.resolve()]
    if not input_root.is_dir():
        raise FileNotFoundError(f"input root does not exist: {input_root}")

    return sorted(path.resolve() for path in input_root.rglob(events_name) if path.is_file())


def parse_scatter_count(value: Any, source: Path, row_number: int) -> int:
    try:
        numeric = float(value)
    except (TypeError, ValueError) as error:
        raise ValueError(
            f"{SCATTER_COLUMN} must be a non-negative integer in {source} row {row_number}: {value!r}"
        ) from error
    if not math.isfinite(numeric) or numeric < 0.0 or not numeric.is_integer():
        raise ValueError(
            f"{SCATTER_COLUMN} must be a non-negative integer in {source} row {row_number}: {value!r}"
        )
    return int(numeric)


def count_scatter_by_slit(event_file: Path) -> dict[str, dict[str, int]]:
    counts = {
        slit_id: {"N_total": 0, "N_k1": 0, "N_ms": 0}
        for slit_id in SLIT_IDS
    }
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
                    f"{SLIT_COLUMN} must be one of {SLIT_IDS} in {event_file} "
                    f"row {row_number}: {slit_id!r}"
                )
            scatter_count = parse_scatter_count(row.get(SCATTER_COLUMN), event_file, row_number)
            if scatter_count == 0:
                continue

            counts[slit_id]["N_total"] += 1
            if scatter_count == 1:
                counts[slit_id]["N_k1"] += 1
            else:
                counts[slit_id]["N_ms"] += 1

    for slit_id, values in counts.items():
        if values["N_total"] != values["N_k1"] + values["N_ms"]:
            raise AssertionError(f"count partition failed for {event_file} {slit_id}")
    return counts


def relative_file_for(input_root: Path, event_file: Path) -> str:
    if input_root.is_file():
        return event_file.name
    return event_file.resolve().relative_to(input_root.resolve()).as_posix()


def summarize_event_file(input_root: Path, event_file: Path) -> list[dict[str, Any]]:
    counts = count_scatter_by_slit(event_file)
    combined = {
        field: sum(counts[slit_id][field] for slit_id in SLIT_IDS)
        for field in ("N_total", "N_k1", "N_ms")
    }
    if combined["N_total"] != combined["N_k1"] + combined["N_ms"]:
        raise AssertionError(f"combined count partition failed for {event_file}")

    input_file = event_file.resolve().as_posix()
    relative_file = relative_file_for(input_root, event_file)
    rows: list[dict[str, Any]] = []
    for slit_id in (*SLIT_IDS, ALL_SLIT_ID):
        values = combined if slit_id == ALL_SLIT_ID else counts[slit_id]
        rows.append(
            {
                "input_file": input_file,
                "relative_file": relative_file,
                "slit_id": slit_id,
                **values,
            }
        )
    return rows


def summarize_input(input_root: Path, events_name: str = "events_clean.csv") -> list[dict[str, Any]]:
    event_files = discover_event_files(input_root, events_name)
    if not event_files:
        raise FileNotFoundError(f"no {events_name} files found under {input_root}")

    rows: list[dict[str, Any]] = []
    for event_file in event_files:
        rows.extend(summarize_event_file(input_root, event_file))
    return rows


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
    event_files = discover_event_files(args.input_root, args.events_name)
    if not event_files:
        raise FileNotFoundError(f"no {args.events_name} files found under {args.input_root}")
    resolved_output = args.output_csv.resolve()
    if resolved_output in event_files:
        raise ValueError(f"output CSV must not overwrite an input events file: {args.output_csv}")

    rows: list[dict[str, Any]] = []
    for event_file in event_files:
        rows.extend(summarize_event_file(args.input_root, event_file))
    write_summary_csv(args.output_csv, rows, args.overwrite)
    print(f"summarized {len(event_files)} file(s)")
    print(f"summary: {args.output_csv}")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as error:
        print(f"error: {error}", file=sys.stderr)
        raise SystemExit(1) from error
