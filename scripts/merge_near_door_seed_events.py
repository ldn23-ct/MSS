#!/usr/bin/env python3
"""Merge near-door seed/batch event CSV files by physical condition."""

from __future__ import annotations

import argparse
import csv
import re
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

import yaml


CASE_RE = re.compile(
    r"^near_door_(?P<system>open|collimated)_(?P<pose>pose[RC])_"
    r"(?P<model_state>normal|cavityPE|cavityFlour|cavityW)_E(?P<energy>\d+)_seed"
    r"(?P<seed>-?\d+)$"
)


@dataclass(frozen=True, order=True)
class ConditionKey:
    system: str
    pose: str
    model_state: str
    energy_keV: int


@dataclass(frozen=True)
class RunRecord:
    key: ConditionKey
    run_dir: Path
    metadata: dict[str, Any]
    seed: int
    n_primary: int


@dataclass(frozen=True)
class MergeResult:
    key: ConditionKey
    output_dir: Path
    source_run_count: int
    seed_count: int
    n_primary: int
    event_rows: int


def read_yaml(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as stream:
        value = yaml.safe_load(stream)
    if not isinstance(value, dict):
        raise ValueError(f"metadata root must be a map: {path}")
    return value


def write_yaml(path: Path, value: dict[str, Any]) -> None:
    with path.open("w", encoding="utf-8") as stream:
        yaml.safe_dump(value, stream, sort_keys=False, allow_unicode=False, width=100)


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


def model_state_from_metadata(metadata: dict[str, Any]) -> str:
    model_type = str(metadata.get("model_type", "normal"))
    abnormal_material = metadata.get("abnormal_material")
    if model_type == "normal":
        return "normal"
    if abnormal_material == "Vehicle_Flour":
        return "cavityFlour"
    if abnormal_material == "G4_W":
        return "cavityW"
    return "cavityPE"


def infer_case(metadata: dict[str, Any], run_dir: Path) -> tuple[ConditionKey, int]:
    case_id = str(nested(metadata, "diagnostics", "case_id", default="") or "")
    match = CASE_RE.match(case_id)
    if match:
        return (
            ConditionKey(
                system=match.group("system"),
                pose=match.group("pose"),
                model_state=match.group("model_state"),
                energy_keV=int(match.group("energy")),
            ),
            int(match.group("seed")),
        )

    system = "collimated" if bool(nested(metadata, "collimator", "enable", default=True)) else "open"
    key = ConditionKey(
        system=system,
        pose=str(metadata.get("pose_id", "unknown_pose")),
        model_state=model_state_from_metadata(metadata),
        energy_keV=as_int(nested(metadata, "source", "mono_energy_keV", default=0)),
    )
    return key, as_int(metadata.get("random_seed"), 0)


def path_case(input_root: Path, run_dir: Path) -> tuple[ConditionKey, int] | None:
    try:
        rel = run_dir.resolve().relative_to(input_root.resolve())
    except ValueError:
        return None
    parts = rel.parts
    if len(parts) < 6:
        return None
    system, pose, model_state, energy_text, seed_text = parts[:5]
    if system not in {"open", "collimated"}:
        return None
    if not energy_text.startswith("E") or not seed_text.startswith("seed"):
        return None
    try:
        energy_keV = int(energy_text[1:])
        seed = int(seed_text[4:])
    except ValueError:
        return None
    return ConditionKey(system, pose, model_state, energy_keV), seed


def discover_run_dirs(input_root: Path, output_root: Path | None = None) -> list[Path]:
    if not input_root.exists():
        raise FileNotFoundError(f"input root does not exist: {input_root}")

    output_resolved = output_root.resolve() if output_root is not None and output_root.exists() else None
    run_dirs: list[Path] = []
    seen: set[Path] = set()
    for metadata_path in input_root.rglob("metadata.yaml"):
        run_dir = metadata_path.parent.resolve()
        if output_resolved is not None:
            try:
                run_dir.relative_to(output_resolved)
                continue
            except ValueError:
                pass
        if run_dir in seen or not (run_dir / "events.csv").is_file():
            continue
        seen.add(run_dir)
        run_dirs.append(run_dir)
    return sorted(run_dirs)


def collect_runs(input_root: Path, output_root: Path | None = None) -> list[RunRecord]:
    records: list[RunRecord] = []
    for run_dir in discover_run_dirs(input_root, output_root):
        metadata = read_yaml(run_dir / "metadata.yaml")
        key, seed = infer_case(metadata, run_dir)
        path_info = path_case(input_root, run_dir)
        if path_info is not None and path_info != (key, seed):
            path_key, path_seed = path_info
            raise ValueError(
                "metadata/path condition mismatch for "
                f"{run_dir}: metadata=({key}, seed={seed}), path=({path_key}, seed={path_seed})"
            )
        records.append(
            RunRecord(
                key=key,
                run_dir=run_dir,
                metadata=metadata,
                seed=seed,
                n_primary=as_int(metadata.get("n_primary"), 0),
            )
        )
    return records


def grouped(records: Iterable[RunRecord]) -> dict[ConditionKey, list[RunRecord]]:
    groups: dict[ConditionKey, list[RunRecord]] = {}
    for record in records:
        groups.setdefault(record.key, []).append(record)
    for group_records in groups.values():
        group_records.sort(key=lambda record: (record.seed, str(record.run_dir)))
    return dict(sorted(groups.items()))


def ensure_output_root(output_root: Path, overwrite: bool) -> None:
    if output_root.exists() and any(output_root.iterdir()):
        if not overwrite:
            raise FileExistsError(
                f"output root already exists and is non-empty: {output_root}; use --overwrite"
            )
        shutil.rmtree(output_root)
    output_root.mkdir(parents=True, exist_ok=True)


def output_dir_for(output_root: Path, key: ConditionKey) -> Path:
    return output_root / key.system / key.pose / key.model_state / f"E{key.energy_keV}"


def merge_events(records: list[RunRecord], output_csv: Path) -> int:
    expected_fields: list[str] | None = None
    event_rows = 0
    output_csv.parent.mkdir(parents=True, exist_ok=True)
    with output_csv.open("w", encoding="utf-8", newline="") as output_stream:
        writer: csv.DictWriter[str] | None = None
        for record in records:
            input_csv = record.run_dir / "events.csv"
            with input_csv.open("r", encoding="utf-8", newline="") as input_stream:
                reader = csv.DictReader(input_stream)
                if reader.fieldnames is None:
                    raise ValueError(f"events CSV has no header: {input_csv}")
                fieldnames = list(reader.fieldnames)
                if "event_id" not in fieldnames or "hit_id" not in fieldnames:
                    raise ValueError(f"events CSV must contain event_id and hit_id: {input_csv}")
                if expected_fields is None:
                    expected_fields = fieldnames
                    writer = csv.DictWriter(output_stream, fieldnames=expected_fields)
                    writer.writeheader()
                elif fieldnames != expected_fields:
                    raise ValueError(
                        f"events CSV header mismatch in {input_csv}: "
                        f"expected {expected_fields}, got {fieldnames}"
                    )
                assert writer is not None
                for row in reader:
                    row["event_id"] = str(event_rows)
                    row["hit_id"] = "0"
                    writer.writerow(row)
                    event_rows += 1
    return event_rows


def merged_metadata(key: ConditionKey, records: list[RunRecord], event_rows: int) -> dict[str, Any]:
    representative = records[0].metadata
    seeds = sorted({record.seed for record in records})
    total_n_primary = sum(record.n_primary for record in records)
    run_id = f"near_door_{key.system}_{key.pose}_{key.model_state}_E{key.energy_keV}_merged"
    return {
        "schema_version": 1,
        "merged_seed_events": True,
        "run_id": run_id,
        "output_csv": "events.csv",
        "model_type": representative.get("model_type"),
        "vehicle_model_id": representative.get("vehicle_model_id"),
        "vehicle_geometry_file": representative.get("vehicle_geometry_file"),
        "selected_target_component": representative.get("selected_target_component"),
        "abnormal_material": representative.get("abnormal_material"),
        "abnormal_target_type": representative.get("abnormal_target_type"),
        "abnormal_target_region": representative.get("abnormal_target_region"),
        "pose": key.pose,
        "pose_id": representative.get("pose_id"),
        "head_offset_x_mm": representative.get("head_offset_x_mm"),
        "head_offset_y_mm": representative.get("head_offset_y_mm"),
        "n_primary": total_n_primary,
        "random_seed": None,
        "number_of_threads": None,
        "debug": representative.get("debug"),
        "source": representative.get("source"),
        "collimator": representative.get("collimator"),
        "detector": representative.get("detector"),
        "diagnostics": {
            "configured": True,
            "case_id": run_id,
            "source_case_ids": [
                nested(record.metadata, "diagnostics", "case_id", default=record.run_dir.name)
                for record in records
            ],
        },
        "physics": representative.get("physics"),
        "world": representative.get("world"),
        "merge_condition": {
            "system": key.system,
            "pose": key.pose,
            "model_state": key.model_state,
            "energy_keV": key.energy_keV,
        },
        "merge": {
            "seed_count": len(seeds),
            "seeds": seeds,
            "source_run_count": len(records),
            "source_event_rows": event_rows,
            "source_n_primary_values": [record.n_primary for record in records],
            "source_run_dirs": [str(record.run_dir) for record in records],
        },
    }


def merge_seed_events(input_root: Path, output_root: Path, overwrite: bool = False) -> list[MergeResult]:
    records = collect_runs(input_root, output_root)
    if not records:
        raise ValueError(f"no near-door run directories with metadata.yaml and events.csv under {input_root}")

    groups = grouped(records)
    ensure_output_root(output_root, overwrite)

    results: list[MergeResult] = []
    for key, group_records in groups.items():
        group_output_dir = output_dir_for(output_root, key)
        event_rows = merge_events(group_records, group_output_dir / "events.csv")
        metadata = merged_metadata(key, group_records, event_rows)
        write_yaml(group_output_dir / "metadata.yaml", metadata)
        results.append(
            MergeResult(
                key=key,
                output_dir=group_output_dir,
                source_run_count=len(group_records),
                seed_count=len({record.seed for record in group_records}),
                n_primary=sum(record.n_primary for record in group_records),
                event_rows=event_rows,
            )
        )
    return results


def parse_args() -> argparse.Namespace:
    repo_root = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input-root", type=Path, default=repo_root / "results/near_door")
    parser.add_argument(
        "--output-root",
        type=Path,
        default=repo_root / "results/near_door_merged/by_condition",
    )
    parser.add_argument("--overwrite", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    results = merge_seed_events(args.input_root, args.output_root, args.overwrite)
    print(f"Merged {len(results)} near-door conditions into {args.output_root}")
    for result in results:
        key = result.key
        print(
            f"{key.system}/{key.pose}/{key.model_state}/E{key.energy_keV}: "
            f"{result.source_run_count} runs, {result.seed_count} seeds, "
            f"{result.n_primary} primaries, {result.event_rows} event rows"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
