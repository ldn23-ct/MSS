#!/usr/bin/env python3
"""Apply an ideal geometric slit acceptance filter to phase-space rows."""

from __future__ import annotations

import argparse
import csv
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Optional

import yaml


EPSILON = 1.0e-9
OUTPUT_FIELDS = ["virtual_slit_accept", "rejection_reason", "blocking_jaw_id"]


@dataclass(frozen=True)
class Jaw:
    jaw_id: str
    vertices_xz: tuple[tuple[float, float], ...]
    y_min: float
    y_max: float


def load_yaml(path: Path) -> dict:
    with path.open("r", encoding="utf-8") as stream:
        value = yaml.safe_load(stream)
    if not isinstance(value, dict):
        raise ValueError(f"YAML root must be a map: {path}")
    return value


def resolve_reference(reference: str, anchor: Path) -> Path:
    candidate = Path(reference)
    if candidate.is_absolute():
        return candidate
    cwd_candidate = Path.cwd() / candidate
    if cwd_candidate.exists():
        return cwd_candidate
    for parent in (anchor.parent, *anchor.parents):
        parent_candidate = parent / candidate
        if parent_candidate.exists():
            return parent_candidate
    raise FileNotFoundError(f"cannot resolve referenced file {reference!r} from {anchor}")


def load_jaws(
    profile_path: Path,
    profile_id: str,
    extrusion_length_y_mm: float,
    offset_x_mm: float,
    offset_y_mm: float,
) -> list[Jaw]:
    grouped: dict[str, list[tuple[int, float, float, float]]] = {}
    with profile_path.open("r", encoding="utf-8-sig", newline="") as stream:
        reader = csv.DictReader(stream)
        required = {"profile_id", "jaw_id", "vertex_id", "x_mm", "z_mm"}
        if reader.fieldnames is None or not required.issubset(reader.fieldnames):
            raise ValueError(f"invalid collimator profile header: {profile_path}")
        has_y = "y_mm" in reader.fieldnames
        for row in reader:
            if row["profile_id"] != profile_id:
                continue
            y_value = float(row["y_mm"]) if has_y and row.get("y_mm", "").strip() else 0.0
            grouped.setdefault(row["jaw_id"], []).append(
                (int(row["vertex_id"]), float(row["x_mm"]), float(row["z_mm"]), y_value)
            )

    if not grouped:
        raise ValueError(f"profile_id {profile_id!r} not found in {profile_path}")

    half_y = 0.5 * extrusion_length_y_mm
    jaws: list[Jaw] = []
    for jaw_id, rows in sorted(grouped.items()):
        rows.sort(key=lambda item: item[0])
        expected_ids = list(range(len(rows)))
        if [item[0] for item in rows] != expected_ids:
            raise ValueError(f"{jaw_id} vertex_id values must be contiguous from 0")
        y_values = {item[3] for item in rows}
        if len(y_values) != 1:
            raise ValueError(f"{jaw_id} has inconsistent y_mm values")
        y_center = next(iter(y_values)) + offset_y_mm
        jaws.append(
            Jaw(
                jaw_id=jaw_id,
                vertices_xz=tuple((item[1] + offset_x_mm, item[2]) for item in rows),
                y_min=y_center - half_y,
                y_max=y_center + half_y,
            )
        )
    return jaws


def _clip_greater_equal(a: float, b: float, low: float, high: float) -> Optional[tuple[float, float]]:
    """Clip an interval by a + b*t >= 0."""
    if abs(b) <= EPSILON:
        return (low, high) if a >= -EPSILON else None
    boundary = -a / b
    if b > 0.0:
        low = max(low, boundary)
    else:
        high = min(high, boundary)
    return (low, high) if low <= high + EPSILON else None


def ray_prism_entry(
    origin: tuple[float, float, float],
    reverse_direction: tuple[float, float, float],
    jaw: Jaw,
) -> Optional[float]:
    low = 0.0
    high = math.inf

    oy = origin[1]
    dy = reverse_direction[1]
    clipped = _clip_greater_equal(oy - jaw.y_min, dy, low, high)
    if clipped is None:
        return None
    low, high = clipped
    clipped = _clip_greater_equal(jaw.y_max - oy, -dy, low, high)
    if clipped is None:
        return None
    low, high = clipped

    vertices = jaw.vertices_xz
    area2 = sum(
        vertices[index][0] * vertices[(index + 1) % len(vertices)][1]
        - vertices[(index + 1) % len(vertices)][0] * vertices[index][1]
        for index in range(len(vertices))
    )
    if abs(area2) <= EPSILON:
        raise ValueError(f"{jaw.jaw_id} polygon area is zero")
    orientation = 1.0 if area2 > 0.0 else -1.0

    ox, _, oz = origin
    dx, _, dz = reverse_direction
    for index, (x1, z1) in enumerate(vertices):
        x2, z2 = vertices[(index + 1) % len(vertices)]
        edge_x = x2 - x1
        edge_z = z2 - z1
        a = orientation * (edge_x * (oz - z1) - edge_z * (ox - x1))
        b = orientation * (edge_x * dz - edge_z * dx)
        clipped = _clip_greater_equal(a, b, low, high)
        if clipped is None:
            return None
        low, high = clipped

    if high < -EPSILON:
        return None
    return max(low, 0.0)


def detector_actual_bounds(slit_config: dict, metadata: dict) -> tuple[float, float, float, float]:
    detector = slit_config["detector"]
    offset_x = float(metadata["head_offset_x_mm"])
    offset_y = float(metadata["head_offset_y_mm"])
    return (
        float(detector["detector_x_range_zero_mm"][0]) + offset_x,
        float(detector["detector_x_range_zero_mm"][1]) + offset_x,
        float(detector["detector_y_range_zero_mm"][0]) + offset_y,
        float(detector["detector_y_range_zero_mm"][1]) + offset_y,
    )


def classify_row(
    row: dict[str, str],
    detector_bounds: tuple[float, float, float, float],
    jaws: Iterable[Jaw],
) -> tuple[bool, str, str]:
    x = float(row["phase_x_mm"])
    y = float(row["phase_y_mm"])
    z = float(row["phase_z_mm"])
    direction = (float(row["dir_x"]), float(row["dir_y"]), float(row["dir_z"]))
    x_min, x_max, y_min, y_max = detector_bounds

    if not (x_min <= x <= x_max and y_min <= y <= y_max):
        return False, "outside_detector", ""
    if direction[2] >= 0.0:
        return False, "invalid_direction", ""

    norm = math.sqrt(sum(component * component for component in direction))
    if norm <= EPSILON:
        return False, "invalid_direction", ""
    reverse = tuple(-component / norm for component in direction)

    blocking: list[tuple[float, str]] = []
    for jaw in jaws:
        entry = ray_prism_entry((x, y, z), reverse, jaw)
        if entry is not None:
            blocking.append((entry, jaw.jaw_id))
    if blocking:
        _, jaw_id = min(blocking)
        return False, "blocked_by_jaw", jaw_id
    return True, "accepted", ""


def filter_phase_space(
    phase_space_path: Path,
    metadata_path: Path,
    slit_config_path: Path,
    output_path: Path,
    accepted_only: bool = False,
) -> tuple[int, int]:
    metadata = load_yaml(metadata_path)
    slit_config = load_yaml(slit_config_path)
    collimator = slit_config["collimator"]
    if not collimator.get("enable", False):
        raise ValueError("paired slit config must have collimator.enable=true")

    profile_path = resolve_reference(str(collimator["profile_file"]), slit_config_path)
    offset_x = float(metadata["head_offset_x_mm"])
    offset_y = float(metadata["head_offset_y_mm"])
    jaws = load_jaws(
        profile_path,
        str(collimator["profile_id"]),
        float(collimator["jaw_extrusion_length_y_mm"]),
        offset_x,
        offset_y,
    )
    detector_bounds = detector_actual_bounds(slit_config, metadata)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    total = 0
    accepted = 0
    with phase_space_path.open("r", encoding="utf-8", newline="") as input_stream:
        reader = csv.DictReader(input_stream)
        if reader.fieldnames is None:
            raise ValueError(f"phase-space CSV has no header: {phase_space_path}")
        required = {
            "phase_x_mm",
            "phase_y_mm",
            "phase_z_mm",
            "dir_x",
            "dir_y",
            "dir_z",
        }
        if not required.issubset(reader.fieldnames):
            raise ValueError(f"phase-space CSV is missing required fields: {phase_space_path}")

        with output_path.open("w", encoding="utf-8", newline="") as output_stream:
            writer = csv.DictWriter(output_stream, fieldnames=reader.fieldnames + OUTPUT_FIELDS)
            writer.writeheader()
            for row in reader:
                total += 1
                is_accepted, reason, jaw_id = classify_row(row, detector_bounds, jaws)
                if is_accepted:
                    accepted += 1
                if accepted_only and not is_accepted:
                    continue
                row["virtual_slit_accept"] = "1" if is_accepted else "0"
                row["rejection_reason"] = reason
                row["blocking_jaw_id"] = jaw_id
                writer.writerow(row)
    return total, accepted


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--phase-space", type=Path, required=True)
    parser.add_argument("--metadata", type=Path, required=True)
    parser.add_argument("--slit-config", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--accepted-only", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    total, accepted = filter_phase_space(
        args.phase_space,
        args.metadata,
        args.slit_config,
        args.output,
        args.accepted_only,
    )
    print(f"Virtual slit accepted {accepted}/{total} phase-space rows")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
