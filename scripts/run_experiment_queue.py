#!/usr/bin/env python3
"""Run MSS experiment configs sequentially."""

from __future__ import annotations

import argparse
import csv
import json
import os
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml


STATE_SCHEMA_VERSION = 1
EXPERIMENT_ORDER = ("E0", "E1", "E2", "E3", "E4", "E5")


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def load_yaml(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as stream:
        value = yaml.safe_load(stream)
    if not isinstance(value, dict):
        raise ValueError(f"YAML root must be a map: {path}")
    return value


def load_json(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    with path.open("r", encoding="utf-8") as stream:
        value = json.load(stream)
    if not isinstance(value, dict):
        raise ValueError(f"queue state root must be an object: {path}")
    return value


def atomic_write_json(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = path.with_suffix(path.suffix + ".tmp")
    with tmp_path.open("w", encoding="utf-8") as stream:
        json.dump(value, stream, indent=2, sort_keys=True)
        stream.write("\n")
    tmp_path.replace(path)


def repo_relative(repo_root: Path, path: Path) -> str:
    try:
        return path.resolve().relative_to(repo_root.resolve()).as_posix()
    except ValueError:
        return path.resolve().as_posix()


def resolve_path(repo_root: Path, base_dir: Path, value: str) -> Path:
    path = Path(value)
    if path.is_absolute():
        return path
    repo_candidate = repo_root / path
    if repo_candidate.exists():
        return repo_candidate
    return base_dir / path


def sanitize_token(value: str) -> str:
    chars: list[str] = []
    for ch in value:
        if ch.isalnum() or ch == "_":
            chars.append(ch)
        elif ch == "-":
            chars.append("m")
        elif ch == ".":
            chars.append("p")
        else:
            chars.append("_")
    return "".join(chars) or "none"


def format_energy_value(value: Any) -> str:
    numeric = float(value)
    text = f"{numeric:.12g}"
    if "e" not in text.lower() and "." in text:
        text = text.rstrip("0").rstrip(".")
    return sanitize_token(text)


def encode_offset(value: int) -> str:
    if value == 0:
        return "0"
    if value > 0:
        return str(value)
    return "m" + str(abs(value))


def pose_id(x_mm: int, y_mm: int) -> str:
    return f"pose_x{encode_offset(x_mm)}_y{encode_offset(y_mm)}"


def generate_poses(config: dict[str, Any]) -> list[dict[str, Any]]:
    pose = config.get("pose", {})
    mode = pose.get("mode")
    run = config.get("run", {})
    base_seed = int(run.get("random_seed", 0))
    poses: list[dict[str, Any]] = []

    if mode == "list":
        xs = list(pose.get("list", {}).get("head_offset_x_mm", []))
        ys = list(pose.get("list", {}).get("head_offset_y_mm", []))
        if len(xs) != len(ys):
            raise ValueError("pose list x/y offsets must have the same length")
        for index, (x_mm, y_mm) in enumerate(zip(xs, ys)):
            x_int = int(x_mm)
            y_int = int(y_mm)
            poses.append(
                {
                    "pose_index": index,
                    "pose_id": pose_id(x_int, y_int),
                    "head_offset_x_mm": x_int,
                    "head_offset_y_mm": y_int,
                    "random_seed": base_seed + index,
                }
            )
        return poses

    if mode == "grid":
        xs = list(pose.get("grid", {}).get("x_offsets_mm", []))
        ys = list(pose.get("grid", {}).get("y_offsets_mm", []))
        index = 0
        for x_mm in xs:
            for y_mm in ys:
                x_int = int(x_mm)
                y_int = int(y_mm)
                poses.append(
                    {
                        "pose_index": index,
                        "pose_id": pose_id(x_int, y_int),
                        "head_offset_x_mm": x_int,
                        "head_offset_y_mm": y_int,
                        "random_seed": base_seed + index,
                    }
                )
                index += 1
        return poses

    raise ValueError("pose.mode must be list or grid")


def build_run_id(config: dict[str, Any], pose: dict[str, Any]) -> str:
    collimator = config.get("collimator", {})
    vehicle = config.get("vehicle", {})
    source = config.get("source", {})

    system = "collimated" if bool(collimator.get("enable", True)) else "open"
    model_type = str(vehicle.get("model_type", "normal"))
    if model_type == "normal":
        model_state = "normal"
    else:
        target = sanitize_token(str(vehicle.get("selected_target_component") or "unknown_target"))
        material = sanitize_token(str(vehicle.get("abnormal_material") or "unknown_material"))
        model_state = f"abnormal_{target}_{material}"

    if source.get("energy_mode") == "mono":
        energy = "E" + format_energy_value(source.get("mono_energy_keV", 0.0)) + "keV"
    else:
        energy = "spectrum"

    return f"{pose['pose_id']}_{system}_{model_state}_{energy}_seed{pose['random_seed']}"


def output_csv_name(config: dict[str, Any]) -> str:
    run = config.get("run", {})
    output = config.get("output", {})
    if bool(run.get("debug", False)):
        return "events_debug.csv"
    return str(output.get("events_csv_name", "events.csv"))


def expected_run_dirs(repo_root: Path, config_path: Path, config: dict[str, Any]) -> list[dict[str, Any]]:
    output = config.get("output", {})
    run = config.get("run", {})
    output_dir = Path(str(output.get("output_directory", "results")))
    if not output_dir.is_absolute():
        output_dir = repo_root / output_dir
    metadata_name = str(output.get("metadata_yaml_name", "metadata.yaml"))
    csv_name = output_csv_name(config)
    n_primary = int(run.get("n_primary_per_pose", 0) or 0)
    dirs: list[dict[str, Any]] = []
    for pose in generate_poses(config):
        run_id = build_run_id(config, pose)
        run_dir = output_dir / run_id
        dirs.append(
            {
                "run_id": run_id,
                "run_dir": run_dir.as_posix(),
                "metadata": (run_dir / metadata_name).as_posix(),
                "csv": (run_dir / csv_name).as_posix(),
                "n_primary": n_primary,
            }
        )
    if not dirs:
        raise ValueError(f"no poses generated for config: {config_path}")
    return dirs


def run_output_complete(expected: dict[str, Any]) -> bool:
    run_dir = Path(expected["run_dir"])
    metadata_path = Path(expected["metadata"])
    csv_path = Path(expected["csv"])
    if not run_dir.is_dir() or not metadata_path.is_file() or not csv_path.is_file():
        return False
    try:
        metadata = load_yaml(metadata_path)
    except Exception:
        return False
    if metadata.get("run_id") != expected["run_id"]:
        return False
    expected_n_primary = int(expected.get("n_primary") or 0)
    if expected_n_primary > 0:
        try:
            actual_n_primary = int(metadata.get("n_primary", 0))
        except (TypeError, ValueError):
            return False
        if actual_n_primary != expected_n_primary:
            return False
    return True


def scalar_equal(left: Any, right: Any) -> bool:
    return str(left) == str(right)


def article_merged_output_dir(item: dict[str, Any]) -> Path | None:
    value = item.get("condition_output_directory_resolved") or item.get("condition_output_directory")
    if not value:
        return None
    return Path(str(value))


def merged_article_item_complete(item: dict[str, Any]) -> bool:
    output_dir = article_merged_output_dir(item)
    if output_dir is None:
        return False

    csv_path = output_dir / "events.csv"
    metadata_path = output_dir / "metadata.yaml"
    if not csv_path.is_file() or not metadata_path.is_file():
        return False

    try:
        metadata = load_yaml(metadata_path)
    except Exception:
        return False
    if metadata.get("merged_article_batches") is not True:
        return False

    merge = metadata.get("merge")
    if not isinstance(merge, dict):
        return False
    source_cases = merge.get("source_cases")
    if not isinstance(source_cases, list):
        return False

    case_id = item.get("case_id")
    seed = item.get("seed")
    batch_index = item.get("batch_index")
    for source_case in source_cases:
        if not isinstance(source_case, dict):
            continue
        if (
            scalar_equal(source_case.get("case_id"), case_id)
            and scalar_equal(source_case.get("seed"), seed)
            and scalar_equal(source_case.get("batch_index"), batch_index)
        ):
            return True
    return False


def item_complete(item: dict[str, Any]) -> bool:
    return all(run_output_complete(expected) for expected in item["expected_runs"]) or merged_article_item_complete(item)


def raw_item_complete(item: dict[str, Any]) -> bool:
    return all(run_output_complete(expected) for expected in item["expected_runs"])


def case_id_from_config(config: dict[str, Any], config_path: Path, fallback: str) -> str:
    diagnostics = config.get("diagnostics", {})
    case_id = diagnostics.get("case_id") if isinstance(diagnostics, dict) else None
    if case_id:
        return str(case_id)
    return fallback or config_path.stem


def item_matches_system(item: dict[str, Any], system: str | None) -> bool:
    if system is None or system == "all":
        return True
    if item.get("system") == system:
        return True
    case_id = str(item.get("case_id", ""))
    return case_id.startswith(f"near_door_{system}_")


def parse_experiment_csv(text: str | None) -> set[str] | None:
    if text is None:
        return None
    values = {part.strip().upper() for part in text.split(",") if part.strip()}
    if not values:
        raise ValueError("experiment filter must contain at least one experiment")
    unknown = sorted(values.difference(EXPERIMENT_ORDER))
    if unknown:
        raise ValueError("unknown experiment(s): " + ", ".join(unknown))
    return values


def experiment_index(experiment: str) -> int:
    try:
        return EXPERIMENT_ORDER.index(experiment)
    except ValueError:
        return -1


def item_matches_experiment_filters(
    item: dict[str, Any],
    only_experiments: set[str] | None,
    from_experiment: str | None,
    to_experiment: str | None,
) -> bool:
    experiment = str(item.get("experiment") or "")
    if only_experiments is not None:
        return experiment in only_experiments
    if not from_experiment and not to_experiment:
        return True
    item_index = experiment_index(experiment)
    if item_index < 0:
        return False
    if from_experiment and item_index < experiment_index(from_experiment):
        return False
    if to_experiment and item_index > experiment_index(to_experiment):
        return False
    return True


def filter_items(
    items: list[dict[str, Any]],
    system: str | None,
    only_experiments: set[str] | None,
    from_experiment: str | None,
    to_experiment: str | None,
    start_index: int | None,
    end_index: int | None,
    shard_count: int,
    shard_index: int,
    limit: int | None,
) -> list[dict[str, Any]]:
    filtered = [
        item
        for item in items
        if item_matches_system(item, system)
        and item_matches_experiment_filters(item, only_experiments, from_experiment, to_experiment)
        and (start_index is None or int(item["index"]) >= start_index)
        and (end_index is None or int(item["index"]) < end_index)
    ]
    if shard_count > 1:
        filtered = [
            item
            for local_index, item in enumerate(filtered)
            if local_index % shard_count == shard_index
        ]
    if limit is not None:
        filtered = filtered[:limit]
    return filtered


def manifest_large_run_threshold(manifest: dict[str, Any]) -> int | None:
    run_safety = manifest.get("run_safety")
    if not isinstance(run_safety, dict):
        return None
    if run_safety.get("allow_large_run_required") is False:
        return None
    threshold = run_safety.get("large_run_case_threshold")
    if threshold is None:
        return None
    try:
        value = int(threshold)
    except (TypeError, ValueError) as error:
        raise ValueError("manifest run_safety.large_run_case_threshold must be an integer") from error
    if value < 0:
        raise ValueError("manifest run_safety.large_run_case_threshold must be non-negative")
    return value


def load_manifest_cases(repo_root: Path, manifest_path: Path) -> list[dict[str, Any]]:
    manifest = load_yaml(manifest_path)
    cases = manifest.get("cases")
    if not isinstance(cases, list) or not cases:
        raise ValueError("manifest must contain a non-empty cases list")

    items: list[dict[str, Any]] = []
    for index, case in enumerate(cases):
        if not isinstance(case, dict) or "config_file" not in case:
            raise ValueError(f"manifest cases[{index}] must contain config_file")
        config_path = resolve_path(repo_root, manifest_path.parent, str(case["config_file"]))
        config = load_yaml(config_path)
        expected = expected_run_dirs(repo_root, config_path, config)
        case_id = case_id_from_config(config, config_path, str(case.get("case_id", "")))
        condition_output_directory = case.get("condition_output_directory")
        condition_output_directory_resolved = None
        if condition_output_directory:
            condition_path = Path(str(condition_output_directory))
            if not condition_path.is_absolute():
                condition_path = repo_root / condition_path
            condition_output_directory_resolved = condition_path.as_posix()
        items.append(
            {
                "index": index,
                "case_id": case_id,
                "config_file": repo_relative(repo_root, config_path),
                "system": str(case.get("system", "")),
                "experiment": case.get("experiment"),
                "pose": case.get("pose"),
                "model_state": case.get("model_state"),
                "energy_keV": case.get("energy_keV"),
                "seed": case.get("seed"),
                "batch_index": case.get("batch_index"),
                "batch_count": case.get("batch_count"),
                "condition_id": case.get("condition_id"),
                "condition_output_directory": condition_output_directory,
                "condition_output_directory_resolved": condition_output_directory_resolved,
                "raw_output_directory": case.get("raw_output_directory"),
                "phantom_id": case.get("phantom_id"),
                "phantom_group": case.get("phantom_group"),
                "defect_depth_id": case.get("defect_depth_id"),
                "defect_depth_label": case.get("defect_depth_label"),
                "geometry_file": case.get("geometry_file"),
                "head_offset_x_mm": case.get("head_offset_x_mm"),
                "head_offset_y_mm": case.get("head_offset_y_mm"),
                "n_primary_per_pose": case.get("n_primary_per_pose"),
                "expected_runs": expected,
                "expected_run_dir": expected[0]["run_dir"],
                "status": "pending",
                "attempt_count": 0,
                "return_code": None,
                "log_path": None,
                "started_at": None,
                "ended_at": None,
                "message": "",
            }
        )
    return items


def merge_state_items(new_items: list[dict[str, Any]], previous: dict[str, Any] | None) -> list[dict[str, Any]]:
    if not previous:
        return new_items
    previous_items = {
        item.get("config_file"): item
        for item in previous.get("items", [])
        if isinstance(item, dict)
    }
    merged: list[dict[str, Any]] = []
    for item in new_items:
        old = previous_items.get(item["config_file"])
        if old:
            for key in ("status", "attempt_count", "return_code", "log_path", "started_at", "ended_at", "message"):
                item[key] = old.get(key, item.get(key))
        merged.append(item)
    return merged


def initial_state(
    repo_root: Path,
    manifest_path: Path,
    binary: Path,
    state_file: Path,
    items: list[dict[str, Any]],
    previous: dict[str, Any] | None,
    system: str,
    only_experiments: str,
    from_experiment: str,
    to_experiment: str,
    start_index: int | None,
    end_index: int | None,
    limit: int | None,
    shard_count: int,
    shard_index: int,
) -> dict[str, Any]:
    queue_id = None
    created_at = None
    if previous:
        queue_id = previous.get("queue_id")
        created_at = previous.get("created_at")
    if not queue_id:
        queue_id = "queue_" + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    if not created_at:
        created_at = utc_now()
    return {
        "schema_version": STATE_SCHEMA_VERSION,
        "queue_id": queue_id,
        "created_at": created_at,
        "updated_at": utc_now(),
        "repo_root": repo_root.as_posix(),
        "manifest": repo_relative(repo_root, manifest_path),
        "binary": binary.as_posix(),
        "state_file": state_file.as_posix(),
        "filters": {
            "system": system,
            "only_experiments": only_experiments,
            "from_experiment": from_experiment,
            "to_experiment": to_experiment,
            "start_index": start_index,
            "end_index": end_index,
            "limit": limit,
            "shard_count": shard_count,
            "shard_index": shard_index,
        },
        "items": items,
    }


def normalize_resumable_items(items: list[dict[str, Any]], rerun_completed: bool) -> None:
    for item in items:
        complete = item_complete(item)
        if complete and not rerun_completed:
            item["status"] = "completed"
            item["message"] = "output complete"
        elif item.get("status") == "running":
            item["status"] = "pending"
            item["message"] = "previous running item reset for resume"


def read_lock_pid(lock_path: Path) -> int | None:
    try:
        for line in lock_path.read_text(encoding="utf-8").splitlines():
            key, separator, value = line.partition(":")
            if separator and key.strip() == "pid":
                return int(value.strip())
    except (OSError, ValueError):
        return None
    return None


def process_is_alive(pid: int) -> bool:
    if pid <= 0:
        return False
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def remove_stale_lock_if_safe(lock_path: Path) -> bool:
    if not lock_path.exists():
        return False
    pid = read_lock_pid(lock_path)
    if pid is None or process_is_alive(pid):
        return False
    lock_path.unlink()
    return True


def create_lock(lock_path: Path, force_unlock: bool) -> None:
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    if force_unlock and lock_path.exists():
        lock_path.unlink()
    elif remove_stale_lock_if_safe(lock_path):
        print(f"removed stale queue lock: {lock_path}")
    try:
        fd = os.open(str(lock_path), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    except FileExistsError as error:
        pid = read_lock_pid(lock_path)
        detail = f" pid={pid}" if pid is not None else ""
        raise RuntimeError(f"queue lock already exists{detail}: {lock_path}") from error
    with os.fdopen(fd, "w", encoding="utf-8") as stream:
        stream.write(f"pid: {os.getpid()}\n")
        stream.write(f"created_at: {utc_now()}\n")


def remove_lock(lock_path: Path) -> None:
    try:
        lock_path.unlink()
    except FileNotFoundError:
        pass


def safe_log_name(index: int, case_id: str) -> str:
    return f"{index:04d}_{sanitize_token(case_id)}.log"


def print_dry_run(items: list[dict[str, Any]], rerun_completed: bool) -> None:
    for item in items:
        complete = item_complete(item)
        action = "run"
        if complete and not rerun_completed:
            action = "skip-complete"
        print(f"{item['index']:04d} {action} {item['case_id']} {item['config_file']}")


def run_item_process(binary: Path, repo_root: Path, item: dict[str, Any], log_path: Path | None) -> int:
    command = [binary.as_posix(), "--config", item["config_file"]]
    if log_path is None:
        completed = subprocess.run(command, cwd=repo_root, check=False)
        return completed.returncode

    with log_path.open("w", encoding="utf-8") as log_stream:
        log_stream.write(f"case_id: {item['case_id']}\n")
        log_stream.write(f"config_file: {item['config_file']}\n")
        log_stream.write(f"started_at: {item['started_at']}\n\n")
        log_stream.flush()
        completed = subprocess.run(
            command,
            cwd=repo_root,
            stdout=log_stream,
            stderr=subprocess.STDOUT,
            text=True,
            check=False,
        )
        log_stream.write(f"\nended_at: {utc_now()}\n")
        log_stream.write(f"return_code: {completed.returncode}\n")
    return completed.returncode


def is_article_manifest(manifest: dict[str, Any]) -> bool:
    return manifest.get("experiment") == "article_simulation_campaign"


def article_condition_key(item: dict[str, Any]) -> tuple[Any, ...]:
    return (
        item.get("experiment"),
        item.get("phantom_id"),
        item.get("energy_keV"),
        item.get("pose"),
        item.get("head_offset_x_mm"),
        item.get("head_offset_y_mm"),
        item.get("geometry_file"),
        item.get("defect_depth_id"),
    )


def article_condition_output_dir(repo_root: Path, item: dict[str, Any]) -> Path:
    value = item.get("condition_output_directory")
    if not value:
        raise ValueError(f"article case is missing condition_output_directory: {item.get('case_id')}")
    path = Path(str(value))
    if path.is_absolute():
        return path
    return repo_root / path


def read_metadata_for_expected(expected: dict[str, Any]) -> dict[str, Any]:
    return load_yaml(Path(expected["metadata"]))


def source_case_record(record: dict[str, Any], metadata: dict[str, Any]) -> dict[str, Any]:
    expected = record["expected_runs"][0]
    return {
        "case_id": record.get("case_id"),
        "batch_index": record.get("batch_index"),
        "seed": record.get("seed"),
        "source_run_id": metadata.get("run_id") or expected.get("run_id"),
        "n_primary": int(expected.get("n_primary") or 0),
    }


def merge_article_events(records: list[dict[str, Any]], output_csv: Path) -> int:
    expected_fields: list[str] | None = None
    event_rows = 0
    event_id_offset = 0
    output_csv.parent.mkdir(parents=True, exist_ok=True)
    with output_csv.open("w", encoding="utf-8", newline="") as output_stream:
        writer: csv.DictWriter[str] | None = None
        for record in records:
            expected = record["expected_runs"][0]
            input_csv = Path(expected["csv"])
            with input_csv.open("r", encoding="utf-8", newline="") as input_stream:
                reader = csv.DictReader(input_stream)
                if reader.fieldnames is None:
                    raise ValueError(f"events CSV has no header: {input_csv}")
                fieldnames = list(reader.fieldnames)
                if "event_id" not in fieldnames:
                    raise ValueError(f"events CSV must contain event_id: {input_csv}")
                if expected_fields is None:
                    expected_fields = fieldnames
                    writer = csv.DictWriter(output_stream, fieldnames=expected_fields)
                    writer.writeheader()
                elif fieldnames != expected_fields:
                    raise ValueError(
                        f"events CSV header mismatch in {input_csv}: expected {expected_fields}, got {fieldnames}"
                    )
                assert writer is not None
                for row in reader:
                    try:
                        row["event_id"] = str(int(row["event_id"]) + event_id_offset)
                    except (TypeError, ValueError) as error:
                        raise ValueError(f"event_id must be an integer in {input_csv}") from error
                    writer.writerow(row)
                    event_rows += 1
            event_id_offset += int(expected.get("n_primary") or 0)
    if expected_fields is None:
        raise ValueError("no article events CSV files were provided for merge")
    return event_rows


def merged_article_metadata(
    item: dict[str, Any],
    records: list[dict[str, Any]],
    event_rows: int,
    keep_raw_runs: bool,
) -> dict[str, Any]:
    representative = read_metadata_for_expected(records[0]["expected_runs"][0])
    source_metadata = [read_metadata_for_expected(record["expected_runs"][0]) for record in records]
    seeds = [record.get("seed") for record in records]
    source_run_dirs = [record["expected_runs"][0]["run_dir"] for record in records]
    total_n_primary = sum(int(record["expected_runs"][0].get("n_primary") or 0) for record in records)
    raw_cleanup_status = "preserved" if keep_raw_runs else "pending"
    return {
        "schema_version": 1,
        "merged_article_batches": True,
        "run_id": str(item.get("condition_id")),
        "output_csv": "events.csv",
        "raw_output_preserved": keep_raw_runs,
        "condition": {
            "condition_id": item.get("condition_id"),
            "experiment": item.get("experiment"),
            "phantom_id": item.get("phantom_id"),
            "phantom_group": item.get("phantom_group"),
            "defect_depth_id": item.get("defect_depth_id"),
            "defect_depth_label": item.get("defect_depth_label"),
            "geometry_file": item.get("geometry_file"),
            "energy_keV": item.get("energy_keV"),
            "pose": item.get("pose"),
            "head_offset_x_mm": item.get("head_offset_x_mm"),
            "head_offset_y_mm": item.get("head_offset_y_mm"),
        },
        "n_primary": total_n_primary,
        "source": representative.get("source"),
        "collimator": representative.get("collimator"),
        "detector": representative.get("detector"),
        "physics": representative.get("physics"),
        "world": representative.get("world"),
        "merge": {
            "source_run_count": len(records),
            "batch_count": len({record.get("batch_index") for record in records}),
            "batch_indices": [record.get("batch_index") for record in records],
            "seeds": seeds,
            "source_run_ids": [metadata.get("run_id") for metadata in source_metadata],
            "source_run_dirs": source_run_dirs,
            "source_cases": [
                source_case_record(record, metadata) for record, metadata in zip(records, source_metadata)
            ],
            "source_n_primary_values": [
                int(record["expected_runs"][0].get("n_primary") or 0) for record in records
            ],
            "event_rows": event_rows,
            "raw_output_preserved": keep_raw_runs,
            "raw_cleanup_status": raw_cleanup_status,
            "raw_run_dirs_removed": 0,
        },
    }


def write_yaml(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as stream:
        yaml.safe_dump(value, stream, sort_keys=False, allow_unicode=False, width=100)


def raw_output_root_for_item(repo_root: Path, item: dict[str, Any]) -> Path | None:
    value = item.get("raw_output_directory")
    if not value:
        return None
    path = Path(str(value))
    if not path.is_absolute():
        path = repo_root / path
    if path.name.startswith("b") and path.parent.name:
        return path.parent.parent
    return path


def validate_raw_run_dir_for_cleanup(expected: dict[str, Any]) -> Path:
    run_dir = Path(expected["run_dir"])
    metadata_path = Path(expected["metadata"])
    csv_path = Path(expected["csv"])
    if not run_dir.is_dir() or not metadata_path.is_file() or not csv_path.is_file():
        raise ValueError(f"raw run output is incomplete, refusing cleanup: {run_dir}")
    if metadata_path.parent != run_dir or csv_path.parent != run_dir:
        raise ValueError(f"raw run expected files are outside run dir, refusing cleanup: {run_dir}")
    return run_dir


def path_is_relative_to(path: Path, parent: Path) -> bool:
    try:
        path.resolve().relative_to(parent.resolve())
    except ValueError:
        return False
    return True


def remove_empty_parents(path: Path, stop_at: Path | None) -> None:
    current = path
    while current.exists():
        if stop_at is not None and not path_is_relative_to(current, stop_at):
            break
        try:
            current.rmdir()
        except OSError:
            break
        if stop_at is not None and current.resolve() == stop_at.resolve():
            break
        current = current.parent


def cleanup_article_raw_runs(repo_root: Path, records: list[dict[str, Any]]) -> int:
    targets: dict[Path, tuple[Path, Path | None]] = {}
    for record in records:
        expected = record["expected_runs"][0]
        run_dir = validate_raw_run_dir_for_cleanup(expected)
        raw_root = raw_output_root_for_item(repo_root, record)
        if raw_root is not None and not path_is_relative_to(run_dir, raw_root):
            raise ValueError(f"raw run dir is outside raw output root, refusing cleanup: {run_dir}")
        targets[run_dir] = (run_dir, raw_root)

    removed = 0
    for run_dir, raw_root in targets.values():
        if not run_dir.exists():
            continue
        shutil.rmtree(run_dir)
        removed += 1
        remove_empty_parents(run_dir.parent, raw_root)
    return removed


def update_article_raw_cleanup_metadata(
    metadata_path: Path,
    keep_raw_runs: bool,
    raw_run_dirs_removed: int,
    raw_cleanup_status: str,
) -> None:
    metadata = load_yaml(metadata_path)
    metadata["raw_output_preserved"] = keep_raw_runs
    merge = metadata.setdefault("merge", {})
    if not isinstance(merge, dict):
        raise ValueError(f"article metadata merge section must be a map: {metadata_path}")
    merge["raw_output_preserved"] = keep_raw_runs
    merge["raw_cleanup_status"] = raw_cleanup_status
    merge["raw_run_dirs_removed"] = raw_run_dirs_removed
    write_yaml(metadata_path, metadata)


def article_groups(items: list[dict[str, Any]]) -> dict[tuple[Any, ...], list[dict[str, Any]]]:
    groups: dict[tuple[Any, ...], list[dict[str, Any]]] = {}
    for item in items:
        groups.setdefault(article_condition_key(item), []).append(item)
    return groups


def merge_article_batches(
    repo_root: Path,
    manifest: dict[str, Any],
    manifest_path: Path,
    keep_raw_runs: bool = False,
) -> dict[str, Any]:
    if not is_article_manifest(manifest):
        return {
            "status": "skipped",
            "output_root": None,
            "condition_count": 0,
            "message": "not an article manifest",
        }

    items = load_manifest_cases(repo_root, manifest_path)
    incomplete = [item for item in items if not item_complete(item)]
    output_root_value = manifest.get("condition_output_root")
    output_root = repo_root / str(output_root_value or f"results/article/{manifest.get('campaign_id', 'article')}/by_condition")
    if incomplete:
        return {
            "status": "skipped",
            "output_root": repo_relative(repo_root, output_root),
            "condition_count": 0,
            "message": f"{len(incomplete)} manifest cases are incomplete",
            "raw_runs_preserved": True,
            "raw_cleanup_status": "skipped",
            "raw_run_dirs_removed": 0,
        }

    groups = article_groups(items)

    if any(not raw_item_complete(item) for item in items):
        if all(merged_article_item_complete(item) for item in items):
            return {
                "status": "completed",
                "output_root": repo_relative(repo_root, output_root),
                "condition_count": len(groups),
                "message": f"{len(groups)} article conditions already merged",
                "raw_runs_preserved": False,
                "raw_cleanup_status": "not_needed",
                "raw_run_dirs_removed": 0,
            }
        return {
            "status": "skipped",
            "output_root": repo_relative(repo_root, output_root),
            "condition_count": 0,
            "message": "raw runs are incomplete and merged article outputs are not complete",
            "raw_runs_preserved": True,
            "raw_cleanup_status": "skipped",
            "raw_run_dirs_removed": 0,
        }

    if output_root.exists():
        shutil.rmtree(output_root)
    output_root.mkdir(parents=True, exist_ok=True)

    merged_outputs: list[tuple[Path, list[dict[str, Any]]]] = []
    for records in groups.values():
        records.sort(key=lambda record: (int(record.get("batch_index") or 0), int(record.get("seed") or 0)))
        first = records[0]
        output_dir = article_condition_output_dir(repo_root, first)
        event_rows = merge_article_events(records, output_dir / "events.csv")
        metadata_path = output_dir / "metadata.yaml"
        write_yaml(metadata_path, merged_article_metadata(first, records, event_rows, keep_raw_runs))
        merged_outputs.append((metadata_path, records))

    raw_run_dirs_removed = 0
    raw_cleanup_status = "preserved"
    if not keep_raw_runs:
        raw_cleanup_status = "removed"
        for metadata_path, records in merged_outputs:
            removed_for_condition = cleanup_article_raw_runs(repo_root, records)
            raw_run_dirs_removed += removed_for_condition
            update_article_raw_cleanup_metadata(
                metadata_path,
                keep_raw_runs=False,
                raw_run_dirs_removed=removed_for_condition,
                raw_cleanup_status=raw_cleanup_status,
            )
    else:
        for metadata_path, _records in merged_outputs:
            update_article_raw_cleanup_metadata(
                metadata_path,
                keep_raw_runs=True,
                raw_run_dirs_removed=0,
                raw_cleanup_status=raw_cleanup_status,
            )

    return {
        "status": "completed",
        "output_root": repo_relative(repo_root, output_root),
        "condition_count": len(groups),
        "message": f"merged {len(groups)} article conditions",
        "raw_runs_preserved": keep_raw_runs,
        "raw_cleanup_status": raw_cleanup_status,
        "raw_run_dirs_removed": raw_run_dirs_removed,
    }


def run_queue(args: argparse.Namespace) -> int:
    repo_root = args.repo_root.resolve()
    manifest_path = args.manifest.resolve()
    binary = args.binary.resolve()
    save_queue = bool(args.save_queue)
    manifest = load_yaml(manifest_path)
    only_experiments = parse_experiment_csv(args.only_experiments)

    state_file = args.state_file or (repo_root / "results/queues/near_door/queue_state.json")
    log_root = args.log_dir
    state: dict[str, Any] | None = None
    log_dir: Path | None = None
    lock_path: Path | None = None

    if save_queue:
        lock_path = state_file.with_suffix(state_file.suffix + ".lock")
        previous = load_json(state_file)
        items = filter_items(
            load_manifest_cases(repo_root, manifest_path),
            args.system,
            only_experiments,
            args.from_experiment,
            args.to_experiment,
            args.start_index,
            args.end_index,
            args.shard_count,
            args.shard_index,
            args.limit,
        )
        items = merge_state_items(items, previous)
        state = initial_state(
            repo_root,
            manifest_path,
            binary,
            state_file,
            items,
            previous,
            args.system,
            args.only_experiments or "",
            args.from_experiment or "",
            args.to_experiment or "",
            args.start_index,
            args.end_index,
            args.limit,
            args.shard_count,
            args.shard_index,
        )
        queue_items = state["items"]
    else:
        queue_items = filter_items(
            load_manifest_cases(repo_root, manifest_path),
            args.system,
            only_experiments,
            args.from_experiment,
            args.to_experiment,
            args.start_index,
            args.end_index,
            args.shard_count,
            args.shard_index,
            args.limit,
        )

    normalize_resumable_items(queue_items, args.rerun_completed)

    if args.dry_run:
        print_dry_run(queue_items, args.rerun_completed)
        return 0

    threshold = manifest_large_run_threshold(manifest)
    pending_count = sum(
        1
        for item in queue_items
        if args.rerun_completed or not item_complete(item)
    )
    if threshold is not None and pending_count > threshold and not args.allow_large_run:
        raise RuntimeError(
            f"queue has {pending_count} pending cases, above manifest threshold {threshold}; "
            "run with --dry-run first or pass --allow-large-run"
        )

    if not binary.exists():
        raise FileNotFoundError(f"MSS binary does not exist: {binary}")

    if save_queue:
        assert state is not None
        assert lock_path is not None
        create_lock(lock_path, args.force_unlock)
        atomic_write_json(state_file, state)
        if log_root is not None:
            log_dir = log_root / state["queue_id"]
            log_dir.mkdir(parents=True, exist_ok=True)

    try:
        for item in queue_items:
            if item_complete(item) and not args.rerun_completed:
                item["status"] = "skipped"
                item["message"] = "already completed"
                item["ended_at"] = utc_now()
                if save_queue:
                    assert state is not None
                    state["updated_at"] = utc_now()
                    atomic_write_json(state_file, state)
                print(f"skip {item['index']:04d}: {item['case_id']}")
                continue

            item["status"] = "running"
            item["attempt_count"] = int(item.get("attempt_count") or 0) + 1
            item["started_at"] = utc_now()
            item["ended_at"] = None
            item["return_code"] = None
            log_path = None
            if save_queue and log_dir is not None:
                assert state is not None
                log_path = log_dir / safe_log_name(int(item["index"]), str(item["case_id"]))
                item["log_path"] = repo_relative(repo_root, log_path)
            item["message"] = "running"
            if save_queue:
                assert state is not None
                state["updated_at"] = utc_now()
                atomic_write_json(state_file, state)

            print(f"run {item['index']:04d}: {item['case_id']}")
            return_code = run_item_process(binary, repo_root, item, log_path)

            item["return_code"] = return_code
            item["ended_at"] = utc_now()
            if return_code == 0 and item_complete(item):
                item["status"] = "completed"
                item["message"] = "completed"
            else:
                item["status"] = "failed"
                item["message"] = "process failed or output incomplete"
                if save_queue:
                    assert state is not None
                    state["updated_at"] = utc_now()
                    atomic_write_json(state_file, state)
                print(f"failed {item['index']:04d}: {item['case_id']}")
                if args.stop_on_failure:
                    return return_code if return_code != 0 else 1
                continue

            if save_queue:
                assert state is not None
                state["updated_at"] = utc_now()
                atomic_write_json(state_file, state)
            print(f"done {item['index']:04d}: {item['case_id']}")

        if is_article_manifest(manifest):
            merge_result = merge_article_batches(
                repo_root,
                manifest,
                manifest_path,
                keep_raw_runs=bool(args.keep_raw_runs),
            )
            print(f"merge {merge_result['status']}: {merge_result['message']}")
            if save_queue:
                assert state is not None
                state["merge"] = merge_result
                state["updated_at"] = utc_now()
                atomic_write_json(state_file, state)
    finally:
        if save_queue:
            assert lock_path is not None
            remove_lock(lock_path)

    return 0


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    repo_root = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", type=Path, default=repo_root)
    parser.add_argument(
        "--manifest",
        type=Path,
        default=repo_root / "config/generated/near_door/manifest.yaml",
    )
    parser.add_argument("--binary", type=Path, default=repo_root / "build/MSS")
    parser.add_argument(
        "--save-queue",
        action="store_true",
        help="save queue state and lock file under results/queues",
    )
    parser.add_argument("--state-file", type=Path)
    parser.add_argument("--log-dir", type=Path)
    parser.add_argument("--rerun-completed", action="store_true")
    parser.add_argument("--continue-on-failure", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--force-unlock", action="store_true")
    parser.add_argument("--system", choices=("all", "open", "collimated"), default="all")
    parser.add_argument("--only-experiments", help="comma-separated experiment IDs, e.g. E0,E3")
    parser.add_argument("--from-experiment", choices=EXPERIMENT_ORDER)
    parser.add_argument("--to-experiment", choices=EXPERIMENT_ORDER)
    parser.add_argument("--start-index", type=int)
    parser.add_argument("--end-index", type=int)
    parser.add_argument("--limit", type=int)
    parser.add_argument("--allow-large-run", action="store_true")
    parser.add_argument(
        "--keep-raw-runs",
        action="store_true",
        help="preserve article raw runs after by_condition merge",
    )
    parser.add_argument("--shard-count", type=int, default=1)
    parser.add_argument("--shard-index", type=int, default=0)
    parser.set_defaults(stop_on_failure=True)
    args = parser.parse_args(argv)
    if args.shard_count < 1:
        parser.error("--shard-count must be >= 1")
    if args.shard_index < 0 or args.shard_index >= args.shard_count:
        parser.error("--shard-index must satisfy 0 <= index < shard-count")
    if args.start_index is not None and args.start_index < 0:
        parser.error("--start-index must be >= 0")
    if args.end_index is not None and args.end_index < 0:
        parser.error("--end-index must be >= 0")
    if args.start_index is not None and args.end_index is not None and args.start_index > args.end_index:
        parser.error("--start-index must be <= --end-index")
    if args.limit is not None and args.limit <= 0:
        parser.error("--limit must be > 0")
    if args.only_experiments and (args.from_experiment or args.to_experiment):
        parser.error("--only-experiments cannot be combined with --from-experiment or --to-experiment")
    if args.from_experiment and args.to_experiment:
        if experiment_index(args.from_experiment) > experiment_index(args.to_experiment):
            parser.error("--from-experiment must be earlier than or equal to --to-experiment")
    if args.only_experiments:
        try:
            parse_experiment_csv(args.only_experiments)
        except ValueError as error:
            parser.error(str(error))
    if args.state_file is not None or args.log_dir is not None:
        args.save_queue = True
    if args.force_unlock and not args.save_queue:
        parser.error("--force-unlock requires --save-queue, --state-file, or --log-dir")
    if args.continue_on_failure:
        args.stop_on_failure = False
    return args


def main(argv: list[str] | None = None) -> int:
    try:
        return run_queue(parse_args(argv))
    except Exception as error:
        print(f"queue error: {error}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
