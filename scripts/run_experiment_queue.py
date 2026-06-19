#!/usr/bin/env python3
"""Run MSS experiment configs sequentially."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml


STATE_SCHEMA_VERSION = 1


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


def item_complete(item: dict[str, Any]) -> bool:
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


def filter_items(
    items: list[dict[str, Any]],
    system: str | None,
    shard_count: int,
    shard_index: int,
) -> list[dict[str, Any]]:
    filtered = [item for item in items if item_matches_system(item, system)]
    if shard_count <= 1:
        return filtered
    return [
        item
        for local_index, item in enumerate(filtered)
        if local_index % shard_count == shard_index
    ]


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
        items.append(
            {
                "index": index,
                "case_id": case_id,
                "config_file": repo_relative(repo_root, config_path),
                "system": str(case.get("system", "")),
                "pose": case.get("pose"),
                "model_state": case.get("model_state"),
                "energy_keV": case.get("energy_keV"),
                "seed": case.get("seed"),
                "batch_index": case.get("batch_index"),
                "batch_count": case.get("batch_count"),
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


def run_queue(args: argparse.Namespace) -> int:
    repo_root = args.repo_root.resolve()
    manifest_path = args.manifest.resolve()
    binary = args.binary.resolve()
    save_queue = bool(args.save_queue)

    state_file = args.state_file or (repo_root / "results/queues/near_door/queue_state.json")
    log_root = args.log_dir or (repo_root / "results/queues/near_door/queue_logs")
    state: dict[str, Any] | None = None
    log_dir: Path | None = None
    lock_path: Path | None = None

    if save_queue:
        lock_path = state_file.with_suffix(state_file.suffix + ".lock")
        previous = load_json(state_file)
        items = filter_items(
            load_manifest_cases(repo_root, manifest_path),
            args.system,
            args.shard_count,
            args.shard_index,
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
            args.shard_count,
            args.shard_index,
        )
        queue_items = state["items"]
    else:
        queue_items = filter_items(
            load_manifest_cases(repo_root, manifest_path),
            args.system,
            args.shard_count,
            args.shard_index,
        )

    normalize_resumable_items(queue_items, args.rerun_completed)

    if args.dry_run:
        print_dry_run(queue_items, args.rerun_completed)
        return 0

    if not binary.exists():
        raise FileNotFoundError(f"MSS binary does not exist: {binary}")

    if save_queue:
        assert state is not None
        assert lock_path is not None
        create_lock(lock_path, args.force_unlock)
        atomic_write_json(state_file, state)
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
            if save_queue:
                assert state is not None
                assert log_dir is not None
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
        help="save queue state, lock file, and per-case logs under results/queues",
    )
    parser.add_argument("--state-file", type=Path)
    parser.add_argument("--log-dir", type=Path)
    parser.add_argument("--rerun-completed", action="store_true")
    parser.add_argument("--continue-on-failure", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--force-unlock", action="store_true")
    parser.add_argument("--system", choices=("all", "open", "collimated"), default="all")
    parser.add_argument("--shard-count", type=int, default=1)
    parser.add_argument("--shard-index", type=int, default=0)
    parser.set_defaults(stop_on_failure=True)
    args = parser.parse_args(argv)
    if args.shard_count < 1:
        parser.error("--shard-count must be >= 1")
    if args.shard_index < 0 or args.shard_index >= args.shard_count:
        parser.error("--shard-index must satisfy 0 <= index < shard-count")
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
