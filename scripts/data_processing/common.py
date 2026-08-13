#!/usr/bin/env python3
"""Shared articlev2 post-processing contracts and metadata parsing."""

from __future__ import annotations

import math
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

try:
    import yaml
except ModuleNotFoundError as error:  # pragma: no cover - CLI environment guard.
    raise RuntimeError(
        "articlev2 post-processing requires PyYAML. "
        "Run `conda activate data` or use `conda run -n data python ...`."
    ) from error


METADATA_NAME = "metadata.yaml"
SLIT_COLUMN = "slit_id"
SLIT_GROUP_COLUMN = "slit_group"
SLIT_LABEL_COLUMN = "slit_label"
ALL_SLIT_ID = "ALL"
VALID_EVENT_DROP_COLUMNS = frozenset({
    "event_id", "hit_id", "track_id", "parent_id", "is_primary_gamma",
    "gamma_source_type", "gamma_source_process", "gamma_source_region_id",
    "rayleigh_count",
})


@dataclass(frozen=True)
class SlitWindow:
    slit_id: str
    left_mm: float
    right_mm: float


@dataclass(frozen=True)
class DetectorAcceptanceRegion:
    slit_id: str
    x_min_mm: float
    x_max_mm: float
    y_min_mm: float
    y_max_mm: float

    def contains(self, det_x: float, det_y: float) -> bool:
        return (
            self.x_min_mm <= det_x <= self.x_max_mm
            and self.y_min_mm <= det_y <= self.y_max_mm
        )


SLIT_WINDOWS_ZERO_MM = {
    "S1": SlitWindow("S1", 42.11, 50.11),
    "S2": SlitWindow("S2", 55.02, 61.02),
    "S3": SlitWindow("S3", 68.08, 76.08),
    "S4": SlitWindow("S4", 78.98, 85.48),
    "S5": SlitWindow("S5", 89.97, 95.47),
    "S6": SlitWindow("S6", 116.23, 121.73),
}
DETECTOR_Y_RANGE_ZERO_MM = (-100.0, 100.0)
PROFILE_SLITS = {
    "P001": ("S2", "S4", "S6"),
    "P002": ("S1", "S3", "S5"),
}
SLIT_PROFILE = {
    slit_id: profile_id
    for profile_id, slit_ids in PROFILE_SLITS.items()
    for slit_id in slit_ids
}
ALL_SLIT_IDS = tuple(SLIT_WINDOWS_ZERO_MM)


@dataclass(frozen=True)
class RunMetadata:
    metadata_path: Path
    raw: dict[str, Any]
    profile_id: str
    phantom_id: str
    scan_mode: str
    pose_id: str
    head_offset_x_mm: float
    head_offset_y_mm: float
    energy_keV: float
    n_primary: int
    case_id: str
    run_id: str


def read_yaml(path: Path) -> dict[str, Any]:
    if not path.is_file():
        raise FileNotFoundError(f"metadata file not found: {path}")
    with path.open("r", encoding="utf-8") as stream:
        value = yaml.safe_load(stream)
    if not isinstance(value, dict):
        raise ValueError(f"metadata root must be a map: {path}")
    return value


def nested(mapping: dict[str, Any], *keys: str, default: Any = None) -> Any:
    value: Any = mapping
    for key in keys:
        if not isinstance(value, dict) or key not in value:
            return default
        value = value[key]
    return value


def finite_float(value: Any, field: str, source: Path) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError) as error:
        raise ValueError(f"metadata {field} must be numeric in {source}: {value!r}") from error
    if not math.isfinite(number):
        raise ValueError(f"metadata {field} must be finite in {source}: {value!r}")
    return number


def positive_int(value: Any, field: str, source: Path) -> int:
    try:
        number = float(value)
    except (TypeError, ValueError) as error:
        raise ValueError(f"metadata {field} must be a positive integer in {source}: {value!r}") from error
    if not math.isfinite(number) or number <= 0 or not number.is_integer():
        raise ValueError(f"metadata {field} must be a positive integer in {source}: {value!r}")
    return int(number)


def _scan_mode_candidates(metadata: dict[str, Any], metadata_path: Path) -> set[str]:
    candidates: set[str] = set()
    explicit = metadata.get("scan_mode")
    if explicit is not None:
        candidates.add(str(explicit).strip())

    config_file = str(metadata.get("config_file", ""))
    config_parts = Path(config_file).parts
    for marker in ("center", "grid"):
        if marker in config_parts:
            candidates.add(marker)

    case_id = str(metadata.get("case_id", ""))
    for marker in ("center", "grid"):
        if f"_{marker}_" in case_id:
            candidates.add(marker)

    for marker in ("center", "grid"):
        if marker in metadata_path.parts:
            candidates.add(marker)
    return {value for value in candidates if value}


def scan_mode_from_metadata(metadata: dict[str, Any], metadata_path: Path) -> str:
    candidates = _scan_mode_candidates(metadata, metadata_path)
    invalid = sorted(value for value in candidates if value not in {"center", "grid"})
    if invalid:
        raise ValueError(f"metadata scan_mode must be center or grid in {metadata_path}: {invalid}")
    if not candidates:
        raise ValueError(f"cannot determine center/grid scan mode from metadata: {metadata_path}")
    if len(candidates) != 1:
        raise ValueError(f"scan mode sources disagree in {metadata_path}: {sorted(candidates)}")
    return next(iter(candidates))


def load_run_metadata(metadata_path: Path) -> RunMetadata:
    metadata = read_yaml(metadata_path)
    profile_id = str(nested(metadata, "collimator", "profile_id", default="") or "").strip()
    if profile_id not in PROFILE_SLITS:
        raise ValueError(
            f"metadata collimator.profile_id must be one of {tuple(PROFILE_SLITS)} "
            f"in {metadata_path}: {profile_id!r}"
        )
    phantom_id = str(metadata.get("vehicle_model_id", "") or "").strip()
    if not phantom_id:
        raise ValueError(f"metadata vehicle_model_id is required: {metadata_path}")
    pose_id = str(metadata.get("pose_id", "") or "").strip()
    if not pose_id:
        raise ValueError(f"metadata pose_id is required: {metadata_path}")

    energy = finite_float(
        nested(metadata, "source", "mono_energy_keV"),
        "source.mono_energy_keV",
        metadata_path,
    )
    if energy <= 0:
        raise ValueError(f"metadata source.mono_energy_keV must be positive: {metadata_path}")

    return RunMetadata(
        metadata_path=metadata_path,
        raw=metadata,
        profile_id=profile_id,
        phantom_id=phantom_id,
        scan_mode=scan_mode_from_metadata(metadata, metadata_path),
        pose_id=pose_id,
        head_offset_x_mm=finite_float(
            metadata.get("head_offset_x_mm"), "head_offset_x_mm", metadata_path
        ),
        head_offset_y_mm=finite_float(
            metadata.get("head_offset_y_mm"), "head_offset_y_mm", metadata_path
        ),
        energy_keV=energy,
        n_primary=positive_int(metadata.get("n_primary"), "n_primary", metadata_path),
        case_id=str(metadata.get("case_id", "") or ""),
        run_id=str(metadata.get("run_id", "") or ""),
    )


def metadata_for_events(event_file: Path, metadata_name: str = METADATA_NAME) -> RunMetadata:
    return load_run_metadata(event_file.parent / metadata_name)


def windows_for_profile(profile_id: str, offset_x_mm: float = 0.0) -> tuple[SlitWindow, ...]:
    if profile_id not in PROFILE_SLITS:
        raise ValueError(f"unknown articlev2 profile_id: {profile_id!r}")
    return tuple(
        SlitWindow(
            slit_id,
            SLIT_WINDOWS_ZERO_MM[slit_id].left_mm + offset_x_mm,
            SLIT_WINDOWS_ZERO_MM[slit_id].right_mm + offset_x_mm,
        )
        for slit_id in PROFILE_SLITS[profile_id]
    )


def acceptance_regions_for_profile(
    profile_id: str,
    offset_x_mm: float = 0.0,
    offset_y_mm: float = 0.0,
) -> tuple[DetectorAcceptanceRegion, ...]:
    y_min, y_max = DETECTOR_Y_RANGE_ZERO_MM
    return tuple(
        DetectorAcceptanceRegion(
            slit_id=window.slit_id,
            x_min_mm=window.left_mm,
            x_max_mm=window.right_mm,
            y_min_mm=y_min + offset_y_mm,
            y_max_mm=y_max + offset_y_mm,
        )
        for window in windows_for_profile(profile_id, offset_x_mm)
    )


def validate_contract() -> None:
    if set(SLIT_PROFILE) != set(SLIT_WINDOWS_ZERO_MM):
        raise AssertionError("every articlev2 slit must belong to exactly one profile")
    ordered = sorted(SLIT_WINDOWS_ZERO_MM.values(), key=lambda item: item.left_mm)
    for item in ordered:
        if not (
            math.isfinite(item.left_mm)
            and math.isfinite(item.right_mm)
            and item.left_mm <= item.right_mm
        ):
            raise AssertionError(f"invalid slit window: {item}")
    for previous, current in zip(ordered, ordered[1:]):
        if current.left_mm <= previous.right_mm:
            raise AssertionError(f"overlapping closed slit windows: {previous}, {current}")
    y_min, y_max = DETECTOR_Y_RANGE_ZERO_MM
    if not (math.isfinite(y_min) and math.isfinite(y_max) and y_min < y_max):
        raise AssertionError(f"invalid detector y range: {DETECTOR_Y_RANGE_ZERO_MM}")


def slit_for_det_x(det_x: float, windows: Iterable[SlitWindow]) -> str | None:
    matches = [item.slit_id for item in windows if item.left_mm <= det_x <= item.right_mm]
    if len(matches) > 1:
        raise ValueError(f"det_x={det_x} matched multiple slit windows: {matches}")
    return matches[0] if matches else None


def parse_slits(text: str) -> tuple[str, ...]:
    slit_ids = tuple(item.strip().upper() for item in text.split(",") if item.strip())
    if not slit_ids:
        raise ValueError("at least one slit must be selected")
    if len(set(slit_ids)) != len(slit_ids):
        raise ValueError("selected slits must not contain duplicates")
    unknown = sorted(set(slit_ids).difference(ALL_SLIT_IDS))
    if unknown:
        raise ValueError("unknown slit(s): " + ", ".join(unknown))
    return slit_ids


def profiles_for_slits(slit_ids: Iterable[str]) -> tuple[str, ...]:
    return tuple(dict.fromkeys(SLIT_PROFILE[slit_id] for slit_id in slit_ids))


def discover_event_files(input_root: Path, events_name: str) -> list[Path]:
    if input_root.is_file():
        if input_root.name != events_name:
            raise ValueError(f"input file must be named {events_name}: {input_root}")
        return [input_root.resolve()]
    if not input_root.is_dir():
        raise FileNotFoundError(f"input root does not exist: {input_root}")
    return sorted(path.resolve() for path in input_root.rglob(events_name) if path.is_file())


def relative_file_for(input_root: Path, event_file: Path) -> str:
    if input_root.is_file():
        return event_file.name
    return event_file.resolve().relative_to(input_root.resolve()).as_posix()


def to_builtin(value: Any) -> Any:
    if isinstance(value, Path):
        return value.as_posix()
    if isinstance(value, SlitWindow):
        return {
            "slit_id": value.slit_id,
            "left_mm": value.left_mm,
            "right_mm": value.right_mm,
        }
    if isinstance(value, DetectorAcceptanceRegion):
        return {
            "slit_id": value.slit_id,
            "x_min_mm": value.x_min_mm,
            "x_max_mm": value.x_max_mm,
            "y_min_mm": value.y_min_mm,
            "y_max_mm": value.y_max_mm,
        }
    if isinstance(value, dict):
        return {str(key): to_builtin(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [to_builtin(item) for item in value]
    if isinstance(value, float) and math.isnan(value):
        return "NaN"
    return value


validate_contract()
