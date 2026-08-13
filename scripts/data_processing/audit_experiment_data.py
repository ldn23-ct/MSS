#!/usr/bin/env python3
"""Audit article V2 simulation data against the frozen experiment requirements."""

from __future__ import annotations

import argparse
import csv
import hashlib
import math
from collections import Counter, defaultdict
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Iterable

import yaml

from .common import (
    PROFILE_SLITS,
    SLIT_GROUP_COLUMN,
    SLIT_LABEL_COLUMN,
    VALID_EVENT_DROP_COLUMNS,
    RunMetadata,
    load_run_metadata,
    nested,
)
from .experiment_contract import (
    DEFECT_CENTER_Z_MM,
    E6_GRID_PHANTOM_IDS,
    E6_TARGETS,
    EXPECTED_ENERGY_KEV,
    EXPECTED_FOCAL_SPOT_DIAMETER_MM,
    EXPECTED_N_PRIMARY,
    EXPECTED_PARTICLE,
    EXPECTED_PHYSICS_LIST,
    EXTRA_PHANTOM_IDS,
    GRID_OFFSETS_MM,
    TARGET_INTERVAL_RULE,
    required_conditions,
    target_z_range,
)
from .slit_channels import load_boundary_config, profile_boundaries, slit_label_for_x


RAW_REQUIRED_COLUMNS = {
    "event_id", "hit_id", "track_id", "parent_id", "is_primary_gamma",
    "det_x", "det_y", "det_z", "det_energy", "scatter_count_total",
    "compton_count", "rayleigh_count", "first_scatter_x", "first_scatter_y",
    "first_scatter_z", "last_scatter_x", "last_scatter_y", "last_scatter_z",
}
VALID_REQUIRED_COLUMNS = {
    "det_x", "det_y", "det_z", "det_energy", "scatter_count_total",
    "compton_count", "first_scatter_x", "first_scatter_y", "first_scatter_z",
    "last_scatter_x", "last_scatter_y", "last_scatter_z",
    "first_scatter_region_id", "last_scatter_region_id",
    SLIT_GROUP_COLUMN, SLIT_LABEL_COLUMN,
}
OUTPUT_NAMES = ("audit_summary.yaml", "condition_inventory.csv", "audit_report.md")


@dataclass(frozen=True)
class Finding:
    level: str
    code: str
    message: str
    path: str = ""


@dataclass
class EventStats:
    rows: int = 0
    depth_valid_rows: int = 0
    n_total: int = 0
    n_k1: int = 0
    n_ms: int = 0
    slit_counts: Counter[str] = field(default_factory=Counter)


@dataclass
class RunEntry:
    key: tuple[str, str, str, float, float]
    metadata: RunMetadata
    seed: int | None
    raw_file: Path | None = None
    valid_file: Path | None = None
    raw_stats: EventStats | None = None
    valid_stats: EventStats | None = None
    findings: list[Finding] = field(default_factory=list)

    @property
    def valid(self) -> bool:
        return not any(item.level == "error" for item in self.findings)


def relative(path: Path | None, root: Path) -> str:
    if path is None:
        return ""
    try:
        return path.resolve().relative_to(root.resolve()).as_posix()
    except ValueError:
        return path.resolve().as_posix()


def metadata_key(metadata: RunMetadata) -> tuple[str, str, str, float, float]:
    return (
        metadata.scan_mode,
        metadata.phantom_id,
        metadata.profile_id,
        metadata.head_offset_x_mm,
        metadata.head_offset_y_mm,
    )


def parse_seed(metadata: RunMetadata, findings: list[Finding], root: Path) -> int | None:
    value = metadata.raw.get("random_seed", metadata.raw.get("base_random_seed"))
    try:
        seed = int(value)
    except (TypeError, ValueError):
        findings.append(Finding(
            "error", "invalid_seed", f"metadata random_seed must be an integer: {value!r}",
            relative(metadata.metadata_path, root),
        ))
        return None
    return seed


def validate_runtime_metadata(metadata: RunMetadata, root: Path) -> list[Finding]:
    findings: list[Finding] = []
    source = relative(metadata.metadata_path, root)
    expected = (
        (metadata.energy_keV, EXPECTED_ENERGY_KEV, "source.mono_energy_keV"),
        (metadata.n_primary, EXPECTED_N_PRIMARY, "n_primary"),
        (nested(metadata.raw, "source", "particle"), EXPECTED_PARTICLE, "source.particle"),
        (
            nested(metadata.raw, "source", "focal_spot_diameter_mm"),
            EXPECTED_FOCAL_SPOT_DIAMETER_MM,
            "source.focal_spot_diameter_mm",
        ),
        (
            nested(metadata.raw, "physics", "physics_list"),
            EXPECTED_PHYSICS_LIST,
            "physics.physics_list",
        ),
    )
    for actual, wanted, name in expected:
        equal = actual == wanted
        if isinstance(wanted, float):
            try:
                equal = math.isclose(float(actual), wanted, rel_tol=0.0, abs_tol=1e-9)
            except (TypeError, ValueError):
                equal = False
        if not equal:
            findings.append(Finding(
                "error", "metadata_mismatch", f"{name}={actual!r}; expected {wanted!r}", source,
            ))
    if metadata.scan_mode == "center" and (
        metadata.head_offset_x_mm != 0.0 or metadata.head_offset_y_mm != 0.0
    ):
        findings.append(Finding(
            "error", "invalid_center_pose", "center run must use offset (0, 0)", source,
        ))
    return findings


def _missing_columns(
    fieldnames: Iterable[str] | None, required: set[str], path: Path, root: Path
) -> list[Finding]:
    missing = sorted(required.difference(fieldnames or ()))
    if not missing:
        return []
    return [Finding(
        "error", "missing_event_columns", "missing columns: " + ", ".join(missing),
        relative(path, root),
    )]


def _number(
    row: dict[str, str], column: str, line: int, path: Path, root: Path,
    findings: list[Finding], *, integer: bool = False,
) -> float | int | None:
    try:
        value = int(row[column]) if integer else float(row[column])
    except (KeyError, TypeError, ValueError):
        findings.append(Finding(
            "error", "invalid_event_value", f"line {line}: {column}={row.get(column)!r}",
            relative(path, root),
        ))
        return None
    if not integer and not math.isfinite(value):
        findings.append(Finding(
            "error", "invalid_event_value", f"line {line}: {column} must be finite",
            relative(path, root),
        ))
        return None
    return value


def inspect_raw_events(path: Path, root: Path) -> tuple[EventStats, list[Finding]]:
    stats = EventStats()
    findings: list[Finding] = []
    seen_tracks: set[tuple[str, str]] = set()
    with path.open("r", encoding="utf-8", newline="") as stream:
        reader = csv.DictReader(stream)
        findings.extend(_missing_columns(reader.fieldnames, RAW_REQUIRED_COLUMNS, path, root))
        if findings:
            return stats, findings
        for line, row in enumerate(reader, start=2):
            stats.rows += 1
            try:
                first_z = float(row["first_scatter_z"])
                last_z = float(row["last_scatter_z"])
            except (KeyError, TypeError, ValueError):
                findings.append(Finding(
                    "error", "invalid_event_value",
                    f"line {line}: first/last scatter depth must be numeric",
                    relative(path, root),
                ))
            else:
                if (
                    math.isfinite(first_z) and math.isfinite(last_z)
                    and first_z >= 0 and last_z >= 0
                ):
                    stats.depth_valid_rows += 1
            scatter = _number(row, "scatter_count_total", line, path, root, findings, integer=True)
            compton = _number(row, "compton_count", line, path, root, findings, integer=True)
            rayleigh = _number(row, "rayleigh_count", line, path, root, findings, integer=True)
            if scatter is not None:
                if scatter >= 1:
                    stats.n_total += 1
                    if scatter == 1:
                        stats.n_k1 += 1
                    else:
                        stats.n_ms += 1
                if compton is not None and rayleigh is not None and scatter != compton + rayleigh:
                    findings.append(Finding(
                        "error", "scatter_count_mismatch",
                        f"line {line}: scatter_count_total != compton_count + rayleigh_count",
                        relative(path, root),
                    ))
            track_key = (row["event_id"], row["track_id"])
            if track_key in seen_tracks:
                findings.append(Finding(
                    "error", "duplicate_detector_crossing",
                    f"line {line}: duplicate event_id/track_id {track_key}", relative(path, root),
                ))
            seen_tracks.add(track_key)
    if stats.rows == 0:
        findings.append(Finding("error", "empty_events", "raw events file is empty", relative(path, root)))
    if stats.n_total != stats.n_k1 + stats.n_ms:
        findings.append(Finding("error", "count_partition", "N_total != N_k1 + N_ms", relative(path, root)))
    return stats, findings


def inspect_valid_events(
    path: Path, metadata: RunMetadata, root: Path, boundary_config: dict[str, Any],
) -> tuple[EventStats, list[Finding]]:
    stats = EventStats()
    findings: list[Finding] = []
    boundaries = profile_boundaries(boundary_config, metadata.profile_id)
    with path.open("r", encoding="utf-8", newline="") as stream:
        reader = csv.DictReader(stream)
        findings.extend(_missing_columns(reader.fieldnames, VALID_REQUIRED_COLUMNS, path, root))
        forbidden = sorted(VALID_EVENT_DROP_COLUMNS.intersection(reader.fieldnames or ()))
        if forbidden:
            findings.append(Finding(
                "error", "forbidden_valid_columns",
                "valid events retain dropped columns: " + ", ".join(forbidden),
                relative(path, root),
            ))
        if findings:
            return stats, findings
        for line, row in enumerate(reader, start=2):
            stats.rows += 1
            slit_group = row[SLIT_GROUP_COLUMN]
            slit_label = row[SLIT_LABEL_COLUMN]
            if slit_group != metadata.profile_id:
                findings.append(Finding(
                    "error", "invalid_slit_group",
                    f"line {line}: slit_group={slit_group!r}; expected {metadata.profile_id}",
                    relative(path, root),
                ))
            if slit_label not in PROFILE_SLITS[metadata.profile_id]:
                findings.append(Finding(
                    "error", "invalid_slit_label",
                    f"line {line}: slit_label {slit_label!r} does not belong to "
                    f"{metadata.profile_id}", relative(path, root),
                ))
            else:
                stats.slit_counts[slit_label] += 1
            scatter = _number(row, "scatter_count_total", line, path, root, findings, integer=True)
            first_z = _number(row, "first_scatter_z", line, path, root, findings)
            last_z = _number(row, "last_scatter_z", line, path, root, findings)
            det_x = _number(row, "det_x", line, path, root, findings)
            if scatter is not None:
                if scatter >= 1:
                    stats.n_total += 1
                    if scatter == 1:
                        stats.n_k1 += 1
                    else:
                        stats.n_ms += 1
            if first_z is not None and last_z is not None:
                if first_z < 0 or last_z < 0:
                    findings.append(Finding(
                        "error", "invalid_valid_depth",
                        f"line {line}: valid event has negative first/last scatter depth",
                        relative(path, root),
                    ))
                else:
                    stats.depth_valid_rows += 1
            if slit_label in PROFILE_SLITS[metadata.profile_id] and det_x is not None:
                expected = slit_label_for_x(
                    float(det_x), metadata.profile_id, boundaries, metadata.head_offset_x_mm
                )
                if slit_label != expected:
                    findings.append(Finding(
                        "error", "slit_label_mismatch",
                        f"line {line}: det_x={det_x} maps to {expected}, found {slit_label}",
                        relative(path, root),
                    ))
    if stats.rows == 0:
        findings.append(Finding("error", "empty_events", "valid events file is empty", relative(path, root)))
    for slit_label in PROFILE_SLITS[metadata.profile_id]:
        if stats.slit_counts[slit_label] == 0:
            findings.append(Finding(
                "error", "empty_slit", f"valid run contains no events for {slit_label}",
                relative(path, root),
            ))
    if stats.n_total != stats.n_k1 + stats.n_ms:
        findings.append(Finding("error", "count_partition", "N_total != N_k1 + N_ms", relative(path, root)))
    return stats, findings


def inspect_raw_valid_preservation(
    raw_path: Path, valid_path: Path, root: Path,
) -> list[Finding]:
    """Prove that valid rows are the ordered depth-valid raw subsequence."""
    with raw_path.open("r", encoding="utf-8", newline="") as raw_stream, valid_path.open(
        "r", encoding="utf-8", newline=""
    ) as valid_stream:
        raw_reader = csv.DictReader(raw_stream)
        valid_reader = csv.DictReader(valid_stream)
        raw_fields = raw_reader.fieldnames or []
        expected_fields = [
            field for field in raw_fields if field not in VALID_EVENT_DROP_COLUMNS
        ] + [SLIT_GROUP_COLUMN, SLIT_LABEL_COLUMN]
        if valid_reader.fieldnames != expected_fields:
            return [Finding(
                "error", "valid_schema_order_mismatch",
                "valid columns must equal ordered raw columns minus the nine dropped fields, "
                "followed by slit_group and slit_label",
                relative(valid_path, root),
            )]

        valid_line = 1
        for raw_line, raw_row in enumerate(raw_reader, start=2):
            try:
                first_z = float(raw_row["first_scatter_z"])
                last_z = float(raw_row["last_scatter_z"])
            except (KeyError, TypeError, ValueError):
                continue
            if not (
                math.isfinite(first_z) and math.isfinite(last_z)
                and first_z >= 0 and last_z >= 0
            ):
                continue
            valid_row = next(valid_reader, None)
            valid_line += 1
            if valid_row is None:
                return [Finding(
                    "error", "missing_valid_row",
                    f"raw line {raw_line} is depth-valid but has no matching valid row",
                    relative(valid_path, root),
                )]
            for field in expected_fields[:-2]:
                if valid_row[field] != raw_row[field]:
                    return [Finding(
                        "error", "valid_field_or_order_mismatch",
                        f"valid line {valid_line} does not preserve raw line {raw_line} "
                        f"field {field}: {valid_row[field]!r} != {raw_row[field]!r}",
                        relative(valid_path, root),
                    )]
        if next(valid_reader, None) is not None:
            return [Finding(
                "error", "extra_valid_row",
                "valid events contain a row after the last depth-valid raw row",
                relative(valid_path, root),
            )]
    return []


def discover_entries(
    results_root: Path, boundary_config: dict[str, Any],
) -> tuple[list[RunEntry], list[Finding]]:
    findings: list[Finding] = []
    entries_by_key: dict[tuple[str, str, str, float, float], RunEntry] = {}
    raw_files = sorted((results_root / "events" / "raw").rglob("events.csv"))
    valid_files = sorted((results_root / "events" / "valid").rglob("events_valid.csv"))

    def metadata_for(path: Path) -> RunMetadata | None:
        metadata_path = path.parent / "metadata.yaml"
        try:
            return load_run_metadata(metadata_path)
        except (FileNotFoundError, ValueError) as error:
            findings.append(Finding(
                "error", "invalid_metadata", str(error), relative(metadata_path, results_root),
            ))
            return None

    for path in raw_files:
        metadata = metadata_for(path)
        if metadata is None:
            continue
        key = metadata_key(metadata)
        if key in entries_by_key:
            findings.append(Finding(
                "error", "duplicate_run", f"duplicate raw run for condition {key}",
                relative(path, results_root),
            ))
            continue
        entry = RunEntry(key=key, metadata=metadata, seed=None, raw_file=path)
        entry.findings.extend(validate_runtime_metadata(metadata, results_root))
        entry.seed = parse_seed(metadata, entry.findings, results_root)
        entry.raw_stats, event_findings = inspect_raw_events(path, results_root)
        entry.findings.extend(event_findings)
        entries_by_key[key] = entry

    valid_seen: set[tuple[str, str, str, float, float]] = set()
    for path in valid_files:
        metadata = metadata_for(path)
        if metadata is None:
            continue
        key = metadata_key(metadata)
        if key in valid_seen:
            findings.append(Finding(
                "error", "duplicate_valid_run", f"duplicate valid run for condition {key}",
                relative(path, results_root),
            ))
            continue
        valid_seen.add(key)
        entry = entries_by_key.get(key)
        if entry is None:
            entry = RunEntry(key=key, metadata=metadata, seed=None)
            entry.findings.append(Finding(
                "error", "missing_raw_run", "valid run has no matching raw run",
                relative(path, results_root),
            ))
            entries_by_key[key] = entry
        elif (
            metadata.n_primary != entry.metadata.n_primary
            or metadata.energy_keV != entry.metadata.energy_keV
            or metadata.pose_id != entry.metadata.pose_id
            or metadata.raw.get("random_seed", metadata.raw.get("base_random_seed"))
            != entry.seed
            or metadata.raw.get("source") != entry.metadata.raw.get("source")
            or metadata.raw.get("physics") != entry.metadata.raw.get("physics")
        ):
            entry.findings.append(Finding(
                "error", "raw_valid_metadata_mismatch",
                "raw and valid metadata disagree on pose, seed, source, physics, energy, or n_primary",
                relative(path.parent / "metadata.yaml", results_root),
            ))
        entry.valid_file = path
        entry.valid_stats, event_findings = inspect_valid_events(
            path, metadata, results_root, boundary_config
        )
        entry.findings.extend(event_findings)
        if entry.raw_file is not None:
            entry.findings.extend(inspect_raw_valid_preservation(
                entry.raw_file, path, results_root
            ))
            raw_metadata = entry.raw_file.parent / "metadata.yaml"
            valid_metadata = path.parent / "metadata.yaml"
            if raw_metadata.read_bytes() != valid_metadata.read_bytes():
                entry.findings.append(Finding(
                    "error", "raw_valid_metadata_copy_mismatch",
                    "valid metadata.yaml is not an exact copy of raw metadata.yaml",
                    relative(valid_metadata, results_root),
                ))
        if (
            entry.raw_stats is not None and entry.valid_stats is not None
            and entry.raw_stats.depth_valid_rows != entry.valid_stats.rows
        ):
            entry.findings.append(Finding(
                "error", "valid_row_count_mismatch",
                f"raw depth-valid rows={entry.raw_stats.depth_valid_rows}; "
                f"valid rows={entry.valid_stats.rows}", relative(path, results_root),
            ))

    for entry in entries_by_key.values():
        if entry.valid_file is None:
            entry.findings.append(Finding(
                "error", "missing_valid_run", "raw run has no matching valid run",
                relative(entry.raw_file, results_root),
            ))
        findings.extend(entry.findings)
    return sorted(entries_by_key.values(), key=lambda item: item.key), findings


def validate_unique_seeds(entries: list[RunEntry], root: Path) -> list[Finding]:
    by_seed: defaultdict[int, list[RunEntry]] = defaultdict(list)
    for entry in entries:
        if entry.seed is not None:
            by_seed[entry.seed].append(entry)
    return [
        Finding(
            "error", "duplicate_seed", f"seed {seed} is used by {len(items)} runs",
            ", ".join(relative(item.raw_file, root) for item in items),
        )
        for seed, items in sorted(by_seed.items()) if len(items) > 1
    ]


def expected_offsets(scan_mode: str) -> set[tuple[float, float]]:
    if scan_mode == "center":
        return {(0.0, 0.0)}
    return {(x, y) for x in GRID_OFFSETS_MM for y in GRID_OFFSETS_MM}


def requirement_status(
    entries: list[RunEntry],
) -> tuple[dict[str, dict[str, Any]], int, dict[tuple[str, str, str], tuple[str, ...]]]:
    grouped: defaultdict[tuple[str, str, str], list[RunEntry]] = defaultdict(list)
    for entry in entries:
        grouped[entry.key[:3]].append(entry)
    experiment_conditions: defaultdict[str, list[tuple[str, str, str]]] = defaultdict(list)
    required_by: dict[tuple[str, str, str], tuple[str, ...]] = {}
    missing_pose_count = 0
    invalid_by_experiment: defaultdict[str, list[str]] = defaultdict(list)
    missing_by_experiment: defaultdict[str, list[str]] = defaultdict(list)

    for condition in required_conditions():
        key = (condition.scan_mode, condition.phantom_id, condition.profile_id)
        required_by[key] = condition.experiments
        actual = grouped.get(key, [])
        actual_offsets = {(item.key[3], item.key[4]) for item in actual}
        wanted_offsets = expected_offsets(condition.scan_mode)
        missing = wanted_offsets.difference(actual_offsets)
        missing_pose_count += len(missing)
        label = f"{condition.scan_mode}/{condition.phantom_id}/{condition.profile_id}"
        for experiment in condition.experiments:
            experiment_conditions[experiment].append(key)
            if missing:
                missing_by_experiment[experiment].append(f"{label}: {len(missing)} pose(s) missing")
            invalid = [item for item in actual if not item.valid]
            if invalid:
                invalid_by_experiment[experiment].append(
                    f"{label}: {len(invalid)} invalid run(s)"
                )

    statuses: dict[str, dict[str, Any]] = {}
    for experiment in ("E1", "E2", "E3", "E4", "E6"):
        problems = missing_by_experiment[experiment] + invalid_by_experiment[experiment]
        statuses[experiment] = {
            "status": "missing" if problems else "ready",
            "condition_count": len(experiment_conditions[experiment]),
            "problems": problems,
        }
    statuses["E5"] = {
        "status": "deferred",
        "condition_count": 0,
        "problems": [
            "E5-A input P0-S4 center is available",
            "E5-B P4_off-S4 center simulation is unavailable",
        ],
    }
    return statuses, missing_pose_count, required_by


def manifest_findings(path: Path, entries: list[RunEntry], root: Path) -> list[Finding]:
    if not path.is_file():
        return [Finding(
            "warning", "generated_manifest_missing",
            "generated manifest is unavailable; runtime metadata remains authoritative",
            relative(path, root),
        )]
    try:
        manifest = yaml.safe_load(path.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError) as error:
        return [Finding("warning", "generated_manifest_invalid", str(error), relative(path, root))]
    manifest_primary = nested(manifest, "parameters", "n_primary_per_pose")
    runtime_primary = sorted({item.metadata.n_primary for item in entries if item.raw_file is not None})
    if manifest_primary not in runtime_primary or len(runtime_primary) != 1:
        return [Finding(
            "warning", "generated_manifest_provenance_mismatch",
            f"generated manifest n_primary_per_pose={manifest_primary!r}; "
            f"runtime metadata values={runtime_primary}; runtime metadata is authoritative",
            relative(path, root),
        )]
    return []


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def valid_manifest_findings(
    path: Path, boundary_path: Path, entries: list[RunEntry], root: Path,
) -> list[Finding]:
    if not path.is_file():
        return [Finding(
            "error", "valid_manifest_missing", "valid-events manifest is required",
            relative(path, root),
        )]
    try:
        manifest = yaml.safe_load(path.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError) as error:
        return [Finding("error", "valid_manifest_invalid", str(error), relative(path, root))]
    if not isinstance(manifest, dict):
        return [Finding(
            "error", "valid_manifest_invalid", "valid-events manifest root must be a map",
            relative(path, root),
        )]
    findings: list[Finding] = []
    actual_hash = sha256_file(boundary_path)
    if manifest.get("boundary_config_sha256") != actual_hash:
        findings.append(Finding(
            "error", "boundary_config_hash_mismatch",
            f"manifest hash={manifest.get('boundary_config_sha256')!r}; actual={actual_hash}",
            relative(path, root),
        ))
    valid_entries = [entry for entry in entries if entry.valid_file is not None]
    valid_rows = sum(entry.valid_stats.rows for entry in valid_entries if entry.valid_stats)
    expected = (
        (manifest.get("input_file_count"), len(valid_entries), "input_file_count"),
        (manifest.get("total_rows_kept"), valid_rows, "total_rows_kept"),
        (manifest.get("output_name"), "events_valid.csv", "output_name"),
    )
    for actual, wanted, field in expected:
        if actual != wanted:
            findings.append(Finding(
                "error", "valid_manifest_count_mismatch",
                f"{field}={actual!r}; expected {wanted!r}", relative(path, root),
            ))
    return findings


def analysis_findings(path: Path, root: Path) -> list[Finding]:
    if not path.is_file():
        return []
    try:
        manifest = yaml.safe_load(path.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError) as error:
        return [Finding("warning", "analysis_manifest_invalid", str(error), relative(path, root))]
    stale: list[str] = []
    analyses = manifest.get("filtered_analyses", []) if isinstance(manifest, dict) else []
    found: set[str] = set()
    for item in analyses:
        phantom_id = item.get("target_phantom")
        if phantom_id not in E6_GRID_PHANTOM_IDS or phantom_id == "P0":
            continue
        found.add(phantom_id)
        event_filter = nested(item, "event_filters", "first_scatter_z", default={})
        actual = (event_filter.get("min_mm"), event_filter.get("max_mm"))
        expected = target_z_range(phantom_id)
        rule = str(event_filter.get("interval_rule", ""))
        if actual != expected or "left-closed-right-open" not in rule:
            stale.append(f"{phantom_id}: range={actual}, rule={rule!r}")
    expected_targets = {phantom for phantom, _ in E6_TARGETS}
    if found != expected_targets:
        stale.append(f"target phantoms={sorted(found)}; expected={sorted(expected_targets)}")
    if not stale:
        return []
    return [Finding(
        "warning", "stale_analysis_outputs",
        "existing grid analysis predates the frozen V2 target contract: " + "; ".join(stale),
        relative(path, root),
    )]


def inventory_rows(
    entries: list[RunEntry], required_by: dict[tuple[str, str, str], tuple[str, ...]], root: Path,
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for entry in entries:
        mode, phantom, profile, x_offset, y_offset = entry.key
        experiments = required_by.get((mode, phantom, profile), ())
        scope = "required" if experiments else (
            "extra" if phantom in EXTRA_PHANTOM_IDS else "unplanned"
        )
        rows.append({
            "scan_mode": mode,
            "phantom_id": phantom,
            "profile_id": profile,
            "pose_id": entry.metadata.pose_id,
            "head_offset_x_mm": x_offset,
            "head_offset_y_mm": y_offset,
            "seed": entry.seed if entry.seed is not None else "",
            "energy_keV": entry.metadata.energy_keV,
            "n_primary": entry.metadata.n_primary,
            "experiments": ",".join(experiments),
            "scope": scope,
            "status": "valid" if entry.valid else "invalid",
            "raw_file": relative(entry.raw_file, root),
            "valid_file": relative(entry.valid_file, root),
            "raw_rows": entry.raw_stats.rows if entry.raw_stats else "",
            "raw_depth_valid_rows": entry.raw_stats.depth_valid_rows if entry.raw_stats else "",
            "valid_rows": entry.valid_stats.rows if entry.valid_stats else "",
            "active_slits": ",".join(PROFILE_SLITS[profile]),
            "finding_codes": ",".join(sorted({item.code for item in entry.findings})),
        })
    return rows


def build_summary(
    results_root: Path, entries: list[RunEntry], findings: list[Finding],
    experiments: dict[str, dict[str, Any]], missing_count: int,
    boundary_path: Path, boundary_hash: str,
) -> dict[str, Any]:
    levels = Counter(item.level for item in findings)
    raw_count = sum(item.raw_file is not None for item in entries)
    valid_count = sum(item.valid_file is not None for item in entries)
    extras = sorted({item.metadata.phantom_id for item in entries if item.metadata.phantom_id in EXTRA_PHANTOM_IDS})
    return {
        "schema_version": 1,
        "audit": "articlev2_experiment_data",
        "results_root": ".",
        "authoritative_source": "run-level metadata.yaml",
        "contract": {
            "energy_keV": EXPECTED_ENERGY_KEV,
            "n_primary_per_pose": EXPECTED_N_PRIMARY,
            "particle": EXPECTED_PARTICLE,
            "focal_spot_diameter_mm": EXPECTED_FOCAL_SPOT_DIAMETER_MM,
            "physics_list": EXPECTED_PHYSICS_LIST,
            "profile_slits": {key: list(value) for key, value in PROFILE_SLITS.items()},
            "boundary_config": relative(boundary_path, results_root),
            "boundary_config_sha256": boundary_hash,
            "valid_depth_filter": (
                "first_scatter_z and last_scatter_z finite and both >= 0"
            ),
            "valid_event_columns": {
                "slit_group": SLIT_GROUP_COLUMN,
                "slit_label": SLIT_LABEL_COLUMN,
                "dropped": sorted(VALID_EVENT_DROP_COLUMNS),
            },
            "defect_center_z_mm": DEFECT_CENTER_Z_MM,
            "target_interval_rule": TARGET_INTERVAL_RULE,
            "target_z_ranges_mm": {
                key: list(target_z_range(key) or ()) for key in DEFECT_CENTER_Z_MM
            },
            "grid_offsets_mm": list(GRID_OFFSETS_MM),
            "e6_targets": [f"{phantom}-{slit}" for phantom, slit in E6_TARGETS],
        },
        "counts": {
            "discovered_runs": len(entries),
            "raw_run_count": raw_count,
            "valid_run_count": valid_count,
            "required_simulation_count_missing": missing_count,
            "error_count": levels["error"],
            "warning_count": levels["warning"],
        },
        "experiments": experiments,
        "extra_phantoms": extras,
        "overall_status": "pass" if levels["error"] == 0 and missing_count == 0 else "fail",
        "findings": [asdict(item) for item in findings],
    }


def markdown_report(summary: dict[str, Any]) -> str:
    counts = summary["counts"]
    lines = [
        "# Article V2 数据资格审计", "",
        f"- 总体状态：`{summary['overall_status']}`",
        f"- 发现 run：{counts['discovered_runs']}（raw {counts['raw_run_count']} / valid {counts['valid_run_count']}）",
        f"- 缺少必需仿真 pose：{counts['required_simulation_count_missing']}",
        f"- 错误 / 警告：{counts['error_count']} / {counts['warning_count']}",
        "- 仿真条件事实来源：run-level `metadata.yaml`", "",
        "## 实验状态", "", "| 实验 | 状态 | 说明 |", "|---|---|---|",
    ]
    for experiment in ("E1", "E2", "E3", "E4", "E5", "E6"):
        item = summary["experiments"][experiment]
        detail = "；".join(item["problems"]) if item["problems"] else "所需条件完整且通过校验"
        lines.append(f"| {experiment} | `{item['status']}` | {detail} |")
    lines.extend(["", "## 数据范围", ""])
    extras = ", ".join(summary["extra_phantoms"]) or "无"
    lines.extend([
        "- E1–E4 使用 P0–P6 center 数据；P001/P002 合计覆盖 S1–S6。",
        "- E6 使用 P2–S2、P4–S4、P6–S6 以及相同 grid 下的 P0 baseline。",
        "- E5-A 的 P0–S4 数据存在；E5-B 因 P4_off 缺失而暂缓。",
        f"- V2 范围外额外模体：{extras}。", "",
    ])
    warnings = [item for item in summary["findings"] if item["level"] == "warning"]
    errors = [item for item in summary["findings"] if item["level"] == "error"]
    lines.extend(["## 警告", ""])
    lines.extend(
        f"- `{item['code']}`：{item['message']}（{item['path']}）" for item in warnings
    )
    if not warnings:
        lines.append("- 无。")
    lines.extend(["", "## 错误", ""])
    lines.extend(
        f"- `{item['code']}`：{item['message']}（{item['path']}）" for item in errors
    )
    if not errors:
        lines.append("- 无。")
    lines.append("")
    return "\n".join(lines)


def write_outputs(
    output_dir: Path, summary: dict[str, Any], inventory: list[dict[str, Any]], *, overwrite: bool,
) -> None:
    existing = [output_dir / name for name in OUTPUT_NAMES if (output_dir / name).exists()]
    if existing and not overwrite:
        raise FileExistsError(
            "audit output already exists; pass --overwrite to replace only audit report files: "
            + ", ".join(str(path) for path in existing)
        )
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "audit_summary.yaml").write_text(
        yaml.safe_dump(summary, sort_keys=False, allow_unicode=True), encoding="utf-8"
    )
    fieldnames = list(inventory[0]) if inventory else [
        "scan_mode", "phantom_id", "profile_id", "pose_id", "status"
    ]
    with (output_dir / "condition_inventory.csv").open(
        "w", encoding="utf-8", newline=""
    ) as stream:
        writer = csv.DictWriter(stream, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(inventory)
    (output_dir / "audit_report.md").write_text(markdown_report(summary), encoding="utf-8")


def audit_results(
    results_root: Path,
    *,
    generated_manifest: Path | None = None,
    analysis_manifest: Path | None = None,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    results_root = results_root.resolve()
    repo_root = Path(__file__).resolve().parents[2]
    generated_manifest = generated_manifest or repo_root / "config/generated/articlev2/manifest.yaml"
    boundary_path = results_root / "data_processing/slit_channels/slit_channel_boundaries.json"
    boundary_config = load_boundary_config(boundary_path)
    boundary_hash = sha256_file(boundary_path)
    entries, findings = discover_entries(results_root, boundary_config)
    seed_findings = validate_unique_seeds(entries, results_root)
    findings.extend(seed_findings)
    experiments, missing_count, required_by = requirement_status(entries)
    findings.extend(manifest_findings(generated_manifest, entries, results_root))
    findings.extend(valid_manifest_findings(
        results_root / "events/valid/valid_events_manifest.yaml",
        boundary_path,
        entries,
        results_root,
    ))
    if analysis_manifest is not None:
        findings.extend(analysis_findings(analysis_manifest, results_root))
    findings.sort(key=lambda item: (item.level, item.code, item.path, item.message))
    summary = build_summary(
        results_root, entries, findings, experiments, missing_count,
        boundary_path, boundary_hash,
    )
    return summary, inventory_rows(entries, required_by, results_root)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--results-root", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path)
    parser.add_argument("--generated-manifest", type=Path)
    parser.add_argument("--analysis-manifest", type=Path)
    parser.add_argument("--overwrite", action="store_true")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    results_root = args.results_root.resolve()
    output_dir = (
        args.output_dir or results_root / "data_processing" / "audit"
    ).resolve()
    summary, inventory = audit_results(
        results_root,
        generated_manifest=args.generated_manifest,
        analysis_manifest=args.analysis_manifest,
    )
    write_outputs(output_dir, summary, inventory, overwrite=args.overwrite)
    counts = summary["counts"]
    print(f"audit status: {summary['overall_status']}")
    print(f"runs: {counts['discovered_runs']}")
    print(f"missing required simulations: {counts['required_simulation_count_missing']}")
    print(f"errors: {counts['error_count']}; warnings: {counts['warning_count']}")
    print(f"report: {output_dir / 'audit_report.md'}")
    return 0 if summary["overall_status"] == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())
