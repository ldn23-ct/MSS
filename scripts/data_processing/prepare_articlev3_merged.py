#!/usr/bin/env python3
"""Prepare the traceable, cleaned and merged Article V3 analysis campaign.

The source campaigns remain immutable.  The output campaign contains relative
links to all raw sources and one cleaned ``events_valid.csv`` per physical
condition/pose.  Independent P001 20M and 80M runs are concatenated only after
their run metadata have been checked, yielding the same 100M histories per grid
pixel as the new P002 runs.
"""

from __future__ import annotations

import argparse
import csv
import math
import os
import shutil
import sys
import tempfile
from collections import defaultdict
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

import yaml

from .clean_events import ADDED_COLUMNS, output_fields, parse_float, sha256_file
from .common import (
    PROFILE_SLITS,
    SLIT_GROUP_COLUMN,
    SLIT_LABEL_COLUMN,
    load_run_metadata,
)
from .experiment_contract import EXPECTED_ENERGY_KEV, GRID_OFFSETS_MM
from .slit_channels import load_boundary_config, profile_boundaries, slit_label_for_x


DEFAULT_OUTPUT = Path("results/articlev3_merged")
BOUNDARY_NAME = "slit_channel_boundaries.json"
EXPECTED_GRID_PRIMARY = 100_000_000
EXPECTED_GRID_PRIMARY_BY_CAMPAIGN = {
    "articlev2": 20_000_000,
    "articlev3_grid_p001_add80m": 80_000_000,
    "articlev3_grid_p002_100m": 100_000_000,
}
SOURCE_CAMPAIGNS = (
    "articlev2",
    "articlev3_grid_p001_add80m",
    "articlev3_grid_p002_100m",
)
EXPECTED_SOURCE_FILE_COUNTS = {
    "articlev2": 341,
    "articlev3_grid_p001_add80m": 324,
    "articlev3_grid_p002_100m": 324,
}
EXPECTED_GRID_CONDITIONS = {
    ("P0", "P001"),
    ("P2", "P001"),
    ("P4", "P001"),
    ("P6", "P001"),
    ("P0", "P002"),
    ("P1", "P002"),
    ("P3", "P002"),
    ("P5", "P002"),
}
REQUIRED_CENTER_CONDITIONS = {
    (f"P{index}", profile)
    for index in range(7)
    for profile in ("P001", "P002")
}
INVENTORY_COLUMNS = (
    "scan_mode",
    "phantom_id",
    "profile_id",
    "pose_id",
    "head_offset_x_mm",
    "head_offset_y_mm",
    "seed",
    "energy_keV",
    "n_primary",
    "experiments",
    "scope",
    "status",
    "raw_file",
    "valid_file",
    "raw_rows",
    "raw_depth_valid_rows",
    "valid_rows",
    "active_slits",
    "finding_codes",
)


@dataclass(frozen=True, order=True)
class ConditionKey:
    scan_mode: str
    phantom_id: str
    profile_id: str
    head_offset_x_mm: float
    head_offset_y_mm: float


@dataclass(frozen=True)
class SourceRun:
    campaign: str
    event_file: Path
    metadata_file: Path
    key: ConditionKey
    pose_id: str
    n_primary: int
    energy_keV: float
    seed: int


@dataclass
class MergeStats:
    rows_read: int = 0
    rows_kept: int = 0
    rows_dropped_nonfinite_depth: int = 0
    rows_dropped_negative_depth: int = 0


def source_run(campaign: str, event_file: Path) -> SourceRun:
    metadata = load_run_metadata(event_file.parent / "metadata.yaml")
    seed_value = metadata.raw.get("random_seed", metadata.raw.get("base_random_seed"))
    try:
        seed = int(seed_value)
    except (TypeError, ValueError) as error:
        raise ValueError(f"source random seed is not an integer: {event_file}") from error
    key = ConditionKey(
        metadata.scan_mode,
        metadata.phantom_id,
        metadata.profile_id,
        metadata.head_offset_x_mm,
        metadata.head_offset_y_mm,
    )
    return SourceRun(
        campaign=campaign,
        event_file=event_file.resolve(),
        metadata_file=metadata.metadata_path.resolve(),
        key=key,
        pose_id=metadata.pose_id,
        n_primary=metadata.n_primary,
        energy_keV=metadata.energy_keV,
        seed=seed,
    )


def discover_sources(results_dir: Path) -> dict[ConditionKey, list[SourceRun]]:
    groups: dict[ConditionKey, list[SourceRun]] = defaultdict(list)
    seen_seeds: dict[int, Path] = {}
    for campaign in SOURCE_CAMPAIGNS:
        raw_root = results_dir / campaign / "events" / "raw"
        files = sorted(raw_root.rglob("events.csv"))
        expected = EXPECTED_SOURCE_FILE_COUNTS[campaign]
        if len(files) != expected:
            raise ValueError(f"{campaign} must contain {expected} raw event files, found {len(files)}")
        for event_file in files:
            run = source_run(campaign, event_file)
            if run.seed in seen_seeds:
                raise ValueError(
                    f"source seed {run.seed} is duplicated by {seen_seeds[run.seed]} and {event_file}"
                )
            seen_seeds[run.seed] = event_file
            groups[run.key].append(run)
    return groups


def validate_source_groups(groups: dict[ConditionKey, list[SourceRun]]) -> None:
    if len(groups) != 665 or sum(len(runs) for runs in groups.values()) != 989:
        raise ValueError("source inventory must contain 989 runs grouped into 665 condition/poses")
    for runs in groups.values():
        if any(not math.isclose(run.energy_keV, EXPECTED_ENERGY_KEV) for run in runs):
            raise ValueError(f"all source runs must use {EXPECTED_ENERGY_KEV:g} keV")
    center = {
        (key.phantom_id, key.profile_id)
        for key in groups
        if key.scan_mode == "center"
    }
    missing_center = sorted(REQUIRED_CENTER_CONDITIONS.difference(center))
    if missing_center:
        raise ValueError(f"required center conditions are missing: {missing_center}")
    for key, runs in groups.items():
        if key.scan_mode == "center" and len(runs) != 1:
            raise ValueError(f"center condition must have exactly one source run: {key}")

    grid_groups = {key: runs for key, runs in groups.items() if key.scan_mode == "grid"}
    found_conditions = {(key.phantom_id, key.profile_id) for key in grid_groups}
    if found_conditions != EXPECTED_GRID_CONDITIONS:
        raise ValueError(
            "grid condition mismatch: missing="
            f"{sorted(EXPECTED_GRID_CONDITIONS.difference(found_conditions))}, extra="
            f"{sorted(found_conditions.difference(EXPECTED_GRID_CONDITIONS))}"
        )
    expected_points = {
        (float(x), float(y)) for x in GRID_OFFSETS_MM for y in GRID_OFFSETS_MM
    }
    for phantom, profile in sorted(EXPECTED_GRID_CONDITIONS):
        condition = {
            (key.head_offset_x_mm, key.head_offset_y_mm): runs
            for key, runs in grid_groups.items()
            if (key.phantom_id, key.profile_id) == (phantom, profile)
        }
        if set(condition) != expected_points:
            raise ValueError(f"{phantom}/{profile} does not contain the exact 9x9 grid")
        for point, runs in condition.items():
            campaigns = {run.campaign for run in runs}
            if profile == "P001":
                expected_campaigns = {"articlev2", "articlev3_grid_p001_add80m"}
            else:
                expected_campaigns = {"articlev3_grid_p002_100m"}
            if campaigns != expected_campaigns:
                raise ValueError(
                    f"{phantom}/{profile}/{point} source campaigns are {sorted(campaigns)}, "
                    f"expected {sorted(expected_campaigns)}"
                )
            for run in runs:
                expected_primary = EXPECTED_GRID_PRIMARY_BY_CAMPAIGN[run.campaign]
                if run.n_primary != expected_primary:
                    raise ValueError(
                        f"{run.campaign} grid run must use {expected_primary} histories: "
                        f"{phantom}/{profile}/{point}"
                    )
            if sum(run.n_primary for run in runs) != EXPECTED_GRID_PRIMARY:
                raise ValueError(f"{phantom}/{profile}/{point} does not sum to 100M histories")


def comparable_metadata(run: SourceRun) -> dict[str, Any]:
    value = yaml.safe_load(run.metadata_file.read_text(encoding="utf-8"))
    return {
        "vehicle_model_id": value.get("vehicle_model_id"),
        "vehicle_geometry_file": value.get("vehicle_geometry_file"),
        "head_offset_x_mm": value.get("head_offset_x_mm"),
        "head_offset_y_mm": value.get("head_offset_y_mm"),
        "source": value.get("source"),
        "collimator": value.get("collimator"),
        "detector": value.get("detector"),
        "physics": value.get("physics"),
        "world": value.get("world"),
    }


def validate_compatible_runs(runs: list[SourceRun]) -> None:
    first = runs[0]
    if any(run.pose_id != first.pose_id for run in runs):
        raise ValueError(f"pose IDs disagree for merged condition {first.key}")
    if any(not math.isclose(run.energy_keV, first.energy_keV) for run in runs):
        raise ValueError(f"energies disagree for merged condition {first.key}")
    reference = comparable_metadata(first)
    for run in runs[1:]:
        if comparable_metadata(run) != reference:
            raise ValueError(f"physics/geometry metadata disagree for merged condition {first.key}")


def relative_source(path: Path, repo_root: Path) -> str:
    try:
        return path.resolve().relative_to(repo_root.resolve()).as_posix()
    except ValueError:
        return path.resolve().as_posix()


def output_run_dir(valid_root: Path, key: ConditionKey, pose_id: str, n_primary: int) -> Path:
    return (
        valid_root
        / key.scan_mode
        / key.phantom_id
        / key.profile_id
        / f"{pose_id}_E560keV_N{n_primary}_merged"
    )


def clean_and_merge_group(
    runs: list[SourceRun],
    output_dir: Path,
    boundary_config: dict[str, Any],
    repo_root: Path,
) -> tuple[MergeStats, dict[str, int], dict[str, Any]]:
    runs = sorted(runs, key=lambda item: (item.campaign, item.seed))
    validate_compatible_runs(runs)
    first = runs[0]
    profile = first.key.profile_id
    boundaries = profile_boundaries(boundary_config, profile)
    stats = MergeStats()
    slit_counts = {slit: 0 for slit in PROFILE_SLITS[profile]}
    output_dir.mkdir(parents=True, exist_ok=True)
    output_file = output_dir / "events_valid.csv"
    writer: csv.DictWriter[str] | None = None
    output_stream = output_file.open("w", encoding="utf-8", newline="")
    try:
        fields: list[str] | None = None
        for run in runs:
            with run.event_file.open("r", encoding="utf-8", newline="") as input_stream:
                reader = csv.DictReader(input_stream)
                current_fields = output_fields(reader.fieldnames, run.event_file)
                if fields is None:
                    fields = current_fields
                    writer = csv.DictWriter(output_stream, fieldnames=fields)
                    writer.writeheader()
                elif current_fields != fields:
                    raise ValueError(f"raw CSV schemas differ in merged condition {first.key}")
                assert writer is not None
                for line, row in enumerate(reader, start=2):
                    stats.rows_read += 1
                    first_z = parse_float(
                        row.get("first_scatter_z"), "first_scatter_z", run.event_file, line
                    )
                    last_z = parse_float(
                        row.get("last_scatter_z"), "last_scatter_z", run.event_file, line
                    )
                    if not (math.isfinite(first_z) and math.isfinite(last_z)):
                        stats.rows_dropped_nonfinite_depth += 1
                        continue
                    if first_z < 0 or last_z < 0:
                        stats.rows_dropped_negative_depth += 1
                        continue
                    det_x = parse_float(row.get("det_x"), "det_x", run.event_file, line)
                    if not math.isfinite(det_x):
                        raise ValueError(f"det_x must be finite at {run.event_file}:{line}")
                    slit = slit_label_for_x(
                        det_x, profile, boundaries, first.key.head_offset_x_mm
                    )
                    output_row = {
                        field: row.get(field, "")
                        for field in fields
                        if field not in ADDED_COLUMNS
                    }
                    output_row[SLIT_GROUP_COLUMN] = profile
                    output_row[SLIT_LABEL_COLUMN] = slit
                    writer.writerow(output_row)
                    stats.rows_kept += 1
                    slit_counts[slit] += 1
    finally:
        output_stream.close()
    if writer is None:
        raise ValueError(f"no CSV header was read for merged condition {first.key}")
    if stats.rows_read != (
        stats.rows_kept
        + stats.rows_dropped_nonfinite_depth
        + stats.rows_dropped_negative_depth
    ):
        raise AssertionError(f"row accounting failed for merged condition {first.key}")

    metadata = yaml.safe_load(first.metadata_file.read_text(encoding="utf-8"))
    n_primary = sum(run.n_primary for run in runs)
    slug = (
        f"merged_{first.key.scan_mode}_{first.key.phantom_id}_{first.key.profile_id}_"
        f"{first.pose_id}_N{n_primary}"
    )
    metadata.update(
        {
            "run_id": slug,
            "case_id": slug,
            "output_csv": "events_valid.csv",
            "scan_mode": first.key.scan_mode,
            "n_primary": n_primary,
            "random_seed": first.seed,
            "base_random_seed": first.seed,
            "merge_provenance": {
                "schema_version": 1,
                "operation": "clean_each_source_then_concatenate_independent_detected_events",
                "source_count": len(runs),
                "source_n_primary_sum": n_primary,
                "sources": [
                    {
                        "campaign": run.campaign,
                        "events": relative_source(run.event_file, repo_root),
                        "metadata": relative_source(run.metadata_file, repo_root),
                        "n_primary": run.n_primary,
                        "random_seed": run.seed,
                    }
                    for run in runs
                ],
            },
        }
    )
    (output_dir / "metadata.yaml").write_text(
        yaml.safe_dump(metadata, sort_keys=False, allow_unicode=True, width=110),
        encoding="utf-8",
    )
    return stats, slit_counts, metadata


def create_raw_source_links(raw_root: Path, results_dir: Path) -> None:
    raw_root.mkdir(parents=True, exist_ok=True)
    for campaign in SOURCE_CAMPAIGNS:
        source = results_dir / campaign / "events" / "raw"
        target = raw_root / campaign
        relative_target = os.path.relpath(source, raw_root)
        target.symlink_to(relative_target, target_is_directory=True)
    (raw_root / "README.md").write_text(
        "# 原始数据索引\n\n"
        "本目录中的三个相对符号链接是只读来源索引；原始 `events.csv` 和 "
        "`metadata.yaml` 保持在各自 campaign 中且未被改写。清洗并按 condition/pose "
        "合并的数据位于 `../valid/`。\n",
        encoding="utf-8",
    )


def experiment_labels(key: ConditionKey) -> str:
    labels: list[str] = []
    if key.scan_mode == "center" and key.phantom_id == "P0":
        labels.append("E1")
    if key.scan_mode == "center" and key.phantom_id in {f"P{i}" for i in range(7)}:
        labels.append("E2")
    if key.scan_mode == "grid" and (key.phantom_id, key.profile_id) in EXPECTED_GRID_CONDITIONS:
        labels.extend(("E2", "E3"))
    return ",".join(dict.fromkeys(labels))


def write_csv(path: Path, columns: Iterable[str], rows: Iterable[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(columns))
        writer.writeheader()
        writer.writerows(rows)


def prepare_campaign(
    repo_root: Path,
    output_root: Path,
    boundary_source: Path,
    *,
    overwrite: bool,
) -> dict[str, Any]:
    results_dir = repo_root / "results"
    groups = discover_sources(results_dir)
    validate_source_groups(groups)
    boundary_config = load_boundary_config(boundary_source)

    if output_root.exists() and not overwrite:
        raise FileExistsError(f"output campaign exists; pass --overwrite: {output_root}")
    output_root.parent.mkdir(parents=True, exist_ok=True)
    staging = Path(tempfile.mkdtemp(prefix=f".{output_root.name}.staging-", dir=output_root.parent))
    try:
        create_raw_source_links(staging / "events" / "raw", results_dir)
        boundary_dir = staging / "data_processing" / "slit_channels"
        boundary_dir.mkdir(parents=True, exist_ok=True)
        shutil.copy2(boundary_source, boundary_dir / BOUNDARY_NAME)

        inventory_rows: list[dict[str, Any]] = []
        summary_rows: list[dict[str, Any]] = []
        valid_root = staging / "events" / "valid"
        ordered_groups = sorted(
            groups.items(),
            key=lambda item: (
                0 if item[0].scan_mode == "center" else 1,
                item[0].phantom_id,
                item[0].profile_id,
                item[0].head_offset_x_mm,
                item[0].head_offset_y_mm,
            ),
        )
        for index, (key, runs) in enumerate(ordered_groups, start=1):
            n_primary = sum(run.n_primary for run in runs)
            run_dir = output_run_dir(valid_root, key, runs[0].pose_id, n_primary)
            stats, slit_counts, _ = clean_and_merge_group(
                runs, run_dir, boundary_config, repo_root
            )
            valid_file = run_dir / "events_valid.csv"
            source_files = ";".join(relative_source(run.event_file, repo_root) for run in runs)
            valid_relative = valid_file.relative_to(staging).as_posix()
            row = {
                "scan_mode": key.scan_mode,
                "phantom_id": key.phantom_id,
                "profile_id": key.profile_id,
                "pose_id": runs[0].pose_id,
                "head_offset_x_mm": key.head_offset_x_mm,
                "head_offset_y_mm": key.head_offset_y_mm,
                "seed": runs[0].seed,
                "energy_keV": runs[0].energy_keV,
                "n_primary": n_primary,
                "experiments": experiment_labels(key),
                "scope": "required" if experiment_labels(key) else "extra",
                "status": "valid",
                "raw_file": source_files,
                "valid_file": valid_relative,
                "raw_rows": stats.rows_read,
                "raw_depth_valid_rows": stats.rows_kept,
                "valid_rows": stats.rows_kept,
                "active_slits": ",".join(PROFILE_SLITS[key.profile_id]),
                "finding_codes": "",
            }
            inventory_rows.append(row)
            summary_rows.append(
                {
                    **asdict(key),
                    "pose_id": runs[0].pose_id,
                    "source_campaigns": ",".join(run.campaign for run in runs),
                    "source_random_seeds": ",".join(str(run.seed) for run in runs),
                    "source_n_primary": "+".join(str(run.n_primary) for run in runs),
                    "merged_n_primary": n_primary,
                    **asdict(stats),
                    **{f"{slit}_count": slit_counts.get(slit, 0) for slit in PROFILE_SLITS[key.profile_id]},
                    "valid_file": valid_relative,
                }
            )
            if index % 25 == 0 or index == len(ordered_groups):
                print(f"prepared {index}/{len(ordered_groups)} merged conditions", flush=True)

        write_csv(
            staging / "data_processing" / "audit" / "condition_inventory.csv",
            INVENTORY_COLUMNS,
            inventory_rows,
        )
        summary_columns = tuple(dict.fromkeys(key for row in summary_rows for key in row))
        write_csv(
            staging / "data_processing" / "merge" / "merge_summary.csv",
            summary_columns,
            summary_rows,
        )
        valid_manifest = {
            "schema_version": 1,
            "created_utc": datetime.now(timezone.utc).isoformat(),
            "input_layer": "events/raw source links",
            "output_layer": "events/valid",
            "operation": "metadata-validated cleaning and condition/pose merge",
            "depth_filter": "first_scatter_z and last_scatter_z finite and both >= 0",
            "boundary_config": f"data_processing/slit_channels/{BOUNDARY_NAME}",
            "boundary_config_sha256": sha256_file(boundary_source),
            "merged_condition_count": len(inventory_rows),
            "source_run_count": sum(len(runs) for runs in groups.values()),
            "rows_read": sum(row["rows_read"] for row in summary_rows),
            "rows_kept": sum(row["rows_kept"] for row in summary_rows),
            "grid_n_primary_per_pose": EXPECTED_GRID_PRIMARY,
            "summary_csv": "data_processing/merge/merge_summary.csv",
        }
        (valid_root / "valid_events_manifest.yaml").write_text(
            yaml.safe_dump(valid_manifest, sort_keys=False, allow_unicode=True), encoding="utf-8"
        )
        merge_manifest = {
            **valid_manifest,
            "source_campaigns": [
                {
                    "campaign": campaign,
                    "raw_root": f"results/{campaign}/events/raw",
                    "event_file_count": EXPECTED_SOURCE_FILE_COUNTS[campaign],
                }
                for campaign in SOURCE_CAMPAIGNS
            ],
            "p001_grid_merge": "20,000,000 + 80,000,000 histories per pose",
            "p002_grid_merge": "100,000,000 histories per pose (single source run)",
        }
        merge_dir = staging / "data_processing" / "merge"
        (merge_dir / "merge_manifest.yaml").write_text(
            yaml.safe_dump(merge_manifest, sort_keys=False, allow_unicode=True), encoding="utf-8"
        )

        audit = {
            "schema_version": 1,
            "audit": "articlev3_merged_analysis_data",
            "results_root": ".",
            "authoritative_source": "merged run metadata with per-source provenance",
            "contract": {
                "energy_keV": EXPECTED_ENERGY_KEV,
                "grid_n_primary_per_pose": EXPECTED_GRID_PRIMARY,
                "profile_slits": {key: list(value) for key, value in PROFILE_SLITS.items()},
                "boundary_config": f"data_processing/slit_channels/{BOUNDARY_NAME}",
                "boundary_config_sha256": sha256_file(boundary_source),
                "grid_offsets_mm": list(GRID_OFFSETS_MM),
            },
            "counts": {
                "source_raw_run_count": sum(len(runs) for runs in groups.values()),
                "valid_condition_pose_count": len(inventory_rows),
                "center_condition_count": sum(row["scan_mode"] == "center" for row in inventory_rows),
                "grid_condition_pose_count": sum(row["scan_mode"] == "grid" for row in inventory_rows),
                "required_simulation_count_missing": 0,
                "error_count": 0,
                "warning_count": 0,
            },
            "experiments": {
                "E1": {"status": "ready", "problems": []},
                "E2": {"status": "ready", "problems": []},
                "E3": {
                    "status": "main_grid_ready",
                    "problems": [],
                    "scope_note": (
                        "the independently managed 55 mm front-slab campaign is validated "
                        "by the strict E3 preflight, outside this merged-data audit"
                    ),
                },
            },
            "overall_status": "pass",
            "findings": [],
        }
        audit_dir = staging / "data_processing" / "audit"
        (audit_dir / "audit_summary.yaml").write_text(
            yaml.safe_dump(audit, sort_keys=False, allow_unicode=True), encoding="utf-8"
        )
        (audit_dir / "audit_report.md").write_text(
            "# Article V3 合并数据资格审计\n\n"
            "- 总体状态：`pass`\n"
            f"- 原始 source run：{audit['counts']['source_raw_run_count']}\n"
            f"- 清洗合并后的 condition/pose：{len(inventory_rows)}\n"
            "- matched grid：P0/P1–P6 全部 9×9 完整，每点 1 亿 histories。\n"
            "- E3 主 M0–M5 grid 数据完整；独立 55 mm slab campaign 由严格 E3 入口另行预检。\n",
            encoding="utf-8",
        )

        if output_root.exists():
            backup = output_root.parent / f".{output_root.name}.backup"
            if backup.exists():
                raise FileExistsError(f"stale backup blocks overwrite: {backup}")
            output_root.replace(backup)
            try:
                staging.replace(output_root)
            except Exception:
                backup.replace(output_root)
                raise
            shutil.rmtree(backup)
        else:
            staging.replace(output_root)
        return audit
    except Exception:
        shutil.rmtree(staging, ignore_errors=True)
        raise


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", type=Path, default=Path(__file__).resolve().parents[2])
    parser.add_argument("--output-root", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--boundary-config", type=Path)
    parser.add_argument("--overwrite", action="store_true")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    repo_root = args.repo_root.resolve()
    output_root = (
        args.output_root if args.output_root.is_absolute() else repo_root / args.output_root
    ).resolve()
    boundary_source = (
        args.boundary_config
        or repo_root
        / "results"
        / "articlev2"
        / "data_processing"
        / "slit_channels"
        / BOUNDARY_NAME
    ).resolve()
    if output_root in {repo_root, repo_root / "results"}:
        raise ValueError("output root must be a dedicated campaign directory")
    audit = prepare_campaign(
        repo_root, output_root, boundary_source, overwrite=args.overwrite
    )
    print(f"merged campaign: {output_root}")
    print(f"audit status: {audit['overall_status']}")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as error:
        print(f"articlev3 merge error: {error}", file=sys.stderr)
        raise SystemExit(1) from error
