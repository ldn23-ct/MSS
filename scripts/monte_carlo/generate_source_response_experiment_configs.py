#!/usr/bin/env python3
"""Generate source-response experiment configs for MSS."""

from __future__ import annotations

import argparse
import copy
import csv
import math
import shutil
import sys
import tempfile
from pathlib import Path
from typing import Any

import yaml


STANDARD_PHANTOM_IDS = tuple(f"P{index}" for index in range(7))
E7_ADDITIONAL_PHANTOM_IDS = ("P7", "P8", "P9")
PHANTOM_IDS = STANDARD_PHANTOM_IDS + E7_ADDITIONAL_PHANTOM_IDS
CENTER_PROFILE_IDS = ("P001", "P002")
GRID_PHANTOM_IDS = ("P0", "P2", "P4", "P6")
DEFAULT_GRID_CONDITIONS = tuple((phantom_id, "P001") for phantom_id in GRID_PHANTOM_IDS)
GRID_OFFSETS_MM = (-10.0, -7.5, -5.0, -2.5, 0.0, 2.5, 5.0, 7.5, 10.0)
E7_SIZE_SERIES: tuple[tuple[str, tuple[float, float, float]], ...] = (
    ("P7", (5.0, 5.0, 5.0)),
    ("P4", (10.0, 10.0, 10.0)),
    ("P8", (15.0, 15.0, 10.0)),
    ("P9", (20.0, 20.0, 10.0)),
)
PROFILE_SETTINGS: dict[str, dict[str, Any]] = {
    "P001": {
        "slit_ids": ["S2", "S4", "S6"],
        "detector_x_range_zero_mm": [20.0, 127.0],
    },
    "P002": {
        "slit_ids": ["S1", "S3", "S5"],
        "detector_x_range_zero_mm": [11.0, 101.0],
    },
}
DEFAULT_CAMPAIGN_ID = "articlev2"
DEFAULT_ENERGY_KEV = 560.0
DEFAULT_N_PRIMARY_PER_POSE = 20_000_000
DEFAULT_THREADS = 8
DEFAULT_BASE_SEED = 1234


def load_yaml(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as stream:
        value = yaml.safe_load(stream)
    if not isinstance(value, dict):
        raise ValueError(f"YAML root must be a map: {path}")
    return value


def write_yaml(path: Path, value: dict[str, Any]) -> None:
    if path.exists():
        raise FileExistsError(f"generated output already exists: {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as stream:
        yaml.safe_dump(value, stream, sort_keys=False, allow_unicode=False, width=100)


def repo_relative(repo_root: Path, path: Path) -> str:
    try:
        return path.resolve().relative_to(repo_root.resolve()).as_posix()
    except ValueError:
        return path.resolve().as_posix()


def format_number_token(value: float) -> str:
    if float(value) == 0.0:
        return "0"
    text = f"{float(value):.12g}"
    if "e" not in text.lower() and "." in text:
        text = text.rstrip("0").rstrip(".")
    return text.replace("-", "m").replace(".", "p")


def parse_positive_int(text: str) -> int:
    try:
        value = int(text)
    except ValueError as error:
        raise argparse.ArgumentTypeError("value must be an integer") from error
    if value <= 0:
        raise argparse.ArgumentTypeError("value must be positive")
    return value


def parse_non_negative_int(text: str) -> int:
    try:
        value = int(text)
    except ValueError as error:
        raise argparse.ArgumentTypeError("value must be an integer") from error
    if value < 0:
        raise argparse.ArgumentTypeError("value must be non-negative")
    return value


def parse_positive_float(text: str) -> float:
    try:
        value = float(text)
    except ValueError as error:
        raise argparse.ArgumentTypeError("value must be numeric") from error
    if not math.isfinite(value) or value <= 0.0:
        raise argparse.ArgumentTypeError("value must be finite and positive")
    return value


def parse_grid_condition(text: str) -> tuple[str, str]:
    parts = [part.strip() for part in text.split(":")]
    if len(parts) != 2 or not all(parts):
        raise argparse.ArgumentTypeError(
            "grid condition must use PHANTOM:PROFILE, for example P1:P002"
        )
    phantom_id, profile_id = parts
    if phantom_id not in STANDARD_PHANTOM_IDS:
        raise argparse.ArgumentTypeError(
            f"grid phantom must be one of {', '.join(STANDARD_PHANTOM_IDS)}"
        )
    if profile_id not in CENTER_PROFILE_IDS:
        raise argparse.ArgumentTypeError(
            f"grid profile must be one of {', '.join(CENTER_PROFILE_IDS)}"
        )
    return phantom_id, profile_id


def validate_geometry(path: Path, phantom_id: str) -> dict[str, Any]:
    if not path.is_file():
        raise FileNotFoundError(f"phantom geometry does not exist: {path}")
    geometry = load_yaml(path)
    if geometry.get("roi", {}).get("name") != "VehicleROI":
        raise ValueError(f"phantom roi.name must be VehicleROI: {path}")
    roots = [
        component
        for component in geometry.get("components", [])
        if isinstance(component, dict) and component.get("host") == "World"
    ]
    if len(roots) != 1 or roots[0].get("name") != "VehicleROI":
        raise ValueError(f"phantom must contain exactly one VehicleROI World daughter: {path}")
    for index, component in enumerate(geometry.get("components", [])):
        if not isinstance(component, dict) or not component.get("is_insert", False):
            continue
        for field in ("material", "region_id"):
            value = component.get(field)
            if not isinstance(value, dict) or not value.get("normal") or not value.get("abnormal"):
                raise ValueError(
                    f"phantom components[{index}].{field} must define normal/abnormal: {path}"
                )
    model_name = str(geometry.get("metadata", {}).get("model_name", ""))
    if model_name != phantom_id:
        raise ValueError(
            f"phantom metadata.model_name mismatch in {path}: expected {phantom_id}, got {model_name}"
        )
    defect = geometry.get("metadata", {}).get("defect")
    return {
        "phantom_id": phantom_id,
        "geometry_file": path,
        "defect": defect,
    }


def collect_phantoms(repo_root: Path, geometry_dir: Path) -> dict[str, dict[str, Any]]:
    phantoms: dict[str, dict[str, Any]] = {}
    for phantom_id in PHANTOM_IDS:
        info = validate_geometry(geometry_dir / f"{phantom_id}.yaml", phantom_id)
        info["geometry_file"] = repo_relative(repo_root, Path(info["geometry_file"]))
        phantoms[phantom_id] = info

    for phantom_id, expected_size in E7_SIZE_SERIES:
        defect = phantoms[phantom_id].get("defect")
        if not isinstance(defect, dict):
            raise ValueError(f"{phantom_id} must define metadata.defect for E7")
        if phantom_id in E7_ADDITIONAL_PHANTOM_IDS and defect.get("experiment") != "E7":
            raise ValueError(f"{phantom_id} metadata.defect.experiment must be E7")
        size = tuple(float(value) for value in defect.get("size_mm", []))
        if size != expected_size:
            raise ValueError(
                f"{phantom_id} metadata.defect.size_mm mismatch: "
                f"expected {expected_size}, got {size}"
            )
    return phantoms


def validate_profile_file(profile_file: Path) -> None:
    if not profile_file.is_file():
        raise FileNotFoundError(f"collimator profile file does not exist: {profile_file}")
    with profile_file.open("r", encoding="utf-8-sig", newline="") as stream:
        reader = csv.DictReader(stream)
        if reader.fieldnames is None or "profile_id" not in reader.fieldnames:
            raise ValueError(f"collimator CSV must contain profile_id: {profile_file}")
        found = {str(row.get("profile_id", "")).strip() for row in reader}
    missing = sorted(set(CENTER_PROFILE_IDS).difference(found))
    if missing:
        raise ValueError(f"collimator profile file is missing profiles {missing}: {profile_file}")


def build_pose_id(x_mm: float, y_mm: float) -> str:
    return f"pose_x{format_number_token(x_mm)}_y{format_number_token(y_mm)}"


def set_single_pose(config: dict[str, Any], x_mm: float, y_mm: float) -> None:
    config["pose"] = copy.deepcopy(config.get("pose", {}))
    config["pose"]["mode"] = "list"
    config["pose"]["list"] = {
        "head_offset_x_mm": [float(x_mm)],
        "head_offset_y_mm": [float(y_mm)],
    }
    config["pose"]["grid"] = {"x_offsets_mm": [], "y_offsets_mm": []}
    config["pose"].setdefault("pose_id_rule", "pose_x{encoded_x}_y{encoded_y}")


def build_config(
    base_config: dict[str, Any],
    *,
    case_id: str,
    geometry_file: str,
    profile_file: str,
    profile_id: str,
    head_offset_x_mm: float,
    head_offset_y_mm: float,
    energy_keV: float,
    n_primary_per_pose: int,
    threads: int,
    base_seed: int,
    output_directory: str,
) -> dict[str, Any]:
    config = copy.deepcopy(base_config)
    config["schema_version"] = 2
    config["case_id"] = case_id

    config["run"] = copy.deepcopy(config["run"])
    config["run"]["random_seed"] = base_seed
    config["run"]["number_of_threads"] = threads
    config["run"]["n_primary_per_pose"] = n_primary_per_pose
    config["run"]["debug"] = False

    config["vehicle"] = copy.deepcopy(config["vehicle"])
    config["vehicle"]["geometry_file"] = geometry_file
    config["vehicle"]["model_type"] = "normal"
    config["vehicle"]["selected_target_component"] = None

    set_single_pose(config, head_offset_x_mm, head_offset_y_mm)

    config["source"] = copy.deepcopy(config["source"])
    config["source"]["energy_mode"] = "mono"
    config["source"]["mono_energy_keV"] = float(energy_keV)

    config["collimator"] = copy.deepcopy(config["collimator"])
    config["collimator"]["enable"] = True
    config["collimator"]["profile_file"] = profile_file
    config["collimator"]["profile_id"] = profile_id

    config["detector"] = copy.deepcopy(config["detector"])
    config["detector"]["detector_x_range_zero_mm"] = list(
        PROFILE_SETTINGS[profile_id]["detector_x_range_zero_mm"]
    )

    config["output"] = copy.deepcopy(config["output"])
    config["output"]["output_directory"] = output_directory
    config["output"]["existing_run_policy"] = "fail"
    return config


def selected_grid_conditions(
    *,
    grid_only: bool,
    grid_conditions: tuple[tuple[str, str], ...] | list[tuple[str, str]] | None,
) -> tuple[tuple[str, str], ...]:
    if not grid_only:
        if grid_conditions is not None:
            raise ValueError("grid_conditions may only be supplied when grid_only is true")
        return DEFAULT_GRID_CONDITIONS
    if not grid_conditions:
        raise ValueError("grid_only requires at least one grid condition")

    selected = tuple(grid_conditions)
    for phantom_id, profile_id in selected:
        if phantom_id not in STANDARD_PHANTOM_IDS:
            raise ValueError(f"unsupported grid phantom: {phantom_id}")
        if profile_id not in CENTER_PROFILE_IDS:
            raise ValueError(f"unsupported grid profile: {profile_id}")
    if len(set(selected)) != len(selected):
        raise ValueError("grid conditions must be unique")
    return selected


def condition_specs(
    *,
    grid_only: bool = False,
    grid_conditions: tuple[tuple[str, str], ...] | list[tuple[str, str]] | None = None,
) -> list[tuple[str, str, str]]:
    selected_grid = selected_grid_conditions(
        grid_only=grid_only,
        grid_conditions=grid_conditions,
    )
    if grid_only:
        return [("grid", phantom_id, profile_id) for phantom_id, profile_id in selected_grid]

    specs: list[tuple[str, str, str]] = []
    for phantom_id in STANDARD_PHANTOM_IDS:
        for profile_id in CENTER_PROFILE_IDS:
            specs.append(("center", phantom_id, profile_id))
    for phantom_id, profile_id in selected_grid:
        specs.append(("grid", phantom_id, profile_id))
    for phantom_id in E7_ADDITIONAL_PHANTOM_IDS:
        specs.append(("center", phantom_id, "P001"))
    return specs


def offsets_for_condition(scan_mode: str) -> list[tuple[float, float]]:
    if scan_mode == "center":
        return [(0.0, 0.0)]
    if scan_mode == "grid":
        return [(x_mm, y_mm) for x_mm in GRID_OFFSETS_MM for y_mm in GRID_OFFSETS_MM]
    raise ValueError(f"unknown scan mode: {scan_mode}")


def generate(
    repo_root: Path,
    base_config_path: Path,
    geometry_dir: Path,
    profile_file: Path,
    output_dir: Path,
    campaign_id: str = DEFAULT_CAMPAIGN_ID,
    energy_keV: float = DEFAULT_ENERGY_KEV,
    n_primary_per_pose: int = DEFAULT_N_PRIMARY_PER_POSE,
    threads: int = DEFAULT_THREADS,
    base_seed: int = DEFAULT_BASE_SEED,
    grid_only: bool = False,
    grid_conditions: tuple[tuple[str, str], ...] | list[tuple[str, str]] | None = None,
    overwrite: bool = False,
) -> dict[str, Any]:
    if output_dir.is_symlink() or (output_dir.exists() and not output_dir.is_dir()):
        raise ValueError(f"generated output path must be a directory, not a file or symlink: {output_dir}")
    if output_dir.exists() and any(output_dir.iterdir()) and not overwrite:
        raise FileExistsError(
            f"generated output directory is not empty: {output_dir}; use --overwrite to replace it"
        )
    if not campaign_id.strip():
        raise ValueError("campaign_id must be non-empty")
    if not math.isfinite(energy_keV) or energy_keV <= 0.0:
        raise ValueError("energy_keV must be finite and positive")
    if n_primary_per_pose <= 0:
        raise ValueError("n_primary_per_pose must be positive")
    if threads <= 0:
        raise ValueError("threads must be positive")
    if base_seed < 0:
        raise ValueError("base_seed must be non-negative")

    selected_grid = selected_grid_conditions(
        grid_only=grid_only,
        grid_conditions=grid_conditions,
    )
    specs = condition_specs(grid_only=grid_only, grid_conditions=grid_conditions)

    base_config = load_yaml(base_config_path)
    phantoms = collect_phantoms(repo_root, geometry_dir)
    validate_profile_file(profile_file)
    profile_file_text = repo_relative(repo_root, profile_file)
    energy_token = format_number_token(energy_keV)

    staging_dir: Path | None = None
    write_root = output_dir
    if overwrite:
        output_dir.parent.mkdir(parents=True, exist_ok=True)
        staging_dir = Path(
            tempfile.mkdtemp(prefix=f".{output_dir.name}.staging-", dir=output_dir.parent)
        )
        write_root = staging_dir

    manifest: dict[str, Any] = {
        "schema_version": 1,
        "experiment": "source_response_simulation_campaign",
        "campaign_id": campaign_id,
        "task_granularity": "one_pose_per_config",
        "base_config": repo_relative(repo_root, base_config_path),
        "geometry_directory": repo_relative(repo_root, geometry_dir),
        "collimator_profile_file": profile_file_text,
        "parameters": {
            "energy_keV": float(energy_keV),
            "n_primary_per_pose": n_primary_per_pose,
            "number_of_threads": threads,
            "base_seed": base_seed,
        },
        "profile_settings": copy.deepcopy(PROFILE_SETTINGS),
        "scan_design": {
            "center": {
                "phantom_ids": [] if grid_only else list(STANDARD_PHANTOM_IDS),
                "profile_ids": [] if grid_only else list(CENTER_PROFILE_IDS),
                "pose_count_per_config": 1,
                "condition_count": (
                    0 if grid_only else len(STANDARD_PHANTOM_IDS) * len(CENTER_PROFILE_IDS)
                ),
            },
            "grid": {
                "phantom_ids": list(dict.fromkeys(item[0] for item in selected_grid)),
                "profile_ids": list(dict.fromkeys(item[1] for item in selected_grid)),
                "conditions": [
                    {
                        "phantom_id": phantom_id,
                        "profile_id": profile_id,
                        "n_primary_per_pose": n_primary_per_pose,
                    }
                    for phantom_id, profile_id in selected_grid
                ],
                "x_offsets_mm": list(GRID_OFFSETS_MM),
                "y_offsets_mm": list(GRID_OFFSETS_MM),
                "condition_count": len(selected_grid),
                "pose_count_per_condition": len(GRID_OFFSETS_MM) ** 2,
                "config_count_per_condition": len(GRID_OFFSETS_MM) ** 2,
                "pose_count_per_config": 1,
                "includes_center": True,
            },
        },
        "run_safety": {
            "large_run_case_threshold": 0,
            "allow_large_run_required": True,
        },
        "cases": [],
    }
    if not grid_only:
        manifest["scan_design"]["e7_size_series"] = {
            "experiment_id": "E7",
            "scan_mode": "center",
            "profile_id": "P001",
            "slit_id": "S4",
            "baseline": None,
            "series": [],
        }

    try:
        seed_cursor = base_seed
        for scan_mode, phantom_id, profile_id in specs:
            geometry_file = str(phantoms[phantom_id]["geometry_file"])
            output_directory = (
                f"results/{campaign_id}/events/raw/{scan_mode}/{phantom_id}/{profile_id}"
            )
            condition_id = (
                f"source_response_{scan_mode}_{phantom_id}_{profile_id}_E{energy_token}"
            )
            for pose_index, (x_mm, y_mm) in enumerate(offsets_for_condition(scan_mode)):
                pose_id = build_pose_id(x_mm, y_mm)
                if scan_mode == "grid":
                    case_id = (
                        f"source_response_grid_{phantom_id}_{profile_id}_{pose_id}_"
                        f"E{energy_token}_seed{seed_cursor}"
                    )
                    config_path = (
                        output_dir
                        / "configs"
                        / "grid"
                        / f"{phantom_id}_{profile_id}"
                        / f"{pose_id}.yaml"
                    )
                else:
                    case_id = (
                        f"source_response_center_{phantom_id}_{profile_id}_"
                        f"E{energy_token}_seed{seed_cursor}"
                    )
                    config_path = (
                        output_dir / "configs" / "center" / f"{phantom_id}_{profile_id}.yaml"
                    )

                config = build_config(
                    base_config,
                    case_id=case_id,
                    geometry_file=geometry_file,
                    profile_file=profile_file_text,
                    profile_id=profile_id,
                    head_offset_x_mm=x_mm,
                    head_offset_y_mm=y_mm,
                    energy_keV=energy_keV,
                    n_primary_per_pose=n_primary_per_pose,
                    threads=threads,
                    base_seed=seed_cursor,
                    output_directory=output_directory,
                )
                write_yaml(write_root / config_path.relative_to(output_dir), config)
                manifest["cases"].append(
                    {
                        "case_id": case_id,
                        "condition_id": condition_id,
                        "config_file": repo_relative(repo_root, config_path),
                        "task_granularity": "one_pose_per_config",
                        "scan_mode": scan_mode,
                        "phantom_id": phantom_id,
                        "geometry_file": geometry_file,
                        "defect": copy.deepcopy(phantoms[phantom_id]["defect"]),
                        "profile_id": profile_id,
                        "slit_ids": list(PROFILE_SETTINGS[profile_id]["slit_ids"]),
                        "detector_x_range_zero_mm": list(
                            PROFILE_SETTINGS[profile_id]["detector_x_range_zero_mm"]
                        ),
                        "energy_keV": float(energy_keV),
                        "pose_index": pose_index,
                        "pose_id": pose_id,
                        "head_offset_x_mm": float(x_mm),
                        "head_offset_y_mm": float(y_mm),
                        "pose_count": 1,
                        "seed": seed_cursor,
                        "seed_start": seed_cursor,
                        "seed_end": seed_cursor,
                        "n_primary_per_pose": n_primary_per_pose,
                        "number_of_threads": threads,
                        "output_directory": output_directory,
                    }
                )
                seed_cursor += 1

        if not grid_only:
            cases_by_condition = {
                (case["scan_mode"], case["phantom_id"], case["profile_id"]): case
                for case in manifest["cases"]
                if case["scan_mode"] == "center"
            }

            def e7_case_reference(
                phantom_id: str, defect_size_mm: tuple[float, float, float] | None
            ) -> dict[str, Any]:
                case = cases_by_condition[("center", phantom_id, "P001")]
                reference = {
                    "phantom_id": phantom_id,
                    "case_id": case["case_id"],
                    "config_file": case["config_file"],
                }
                if defect_size_mm is not None:
                    reference["defect_size_mm"] = list(defect_size_mm)
                return reference

            e7_design = manifest["scan_design"]["e7_size_series"]
            e7_design["baseline"] = e7_case_reference("P0", None)
            e7_design["series"] = [
                e7_case_reference(phantom_id, defect_size_mm)
                for phantom_id, defect_size_mm in E7_SIZE_SERIES
            ]

        total_pose_runs = len(manifest["cases"])
        manifest["summary"] = {
            "physical_condition_count": len(specs),
            "config_count": len(manifest["cases"]),
            "task_count": len(manifest["cases"]),
            "center_config_count": sum(
                case["scan_mode"] == "center" for case in manifest["cases"]
            ),
            "grid_condition_count": len(selected_grid),
            "grid_config_count": sum(
                case["scan_mode"] == "grid" for case in manifest["cases"]),
            "total_pose_runs": total_pose_runs,
            "total_primary": total_pose_runs * n_primary_per_pose,
            "seed_start": base_seed,
            "seed_end": seed_cursor - 1,
        }
        write_yaml(write_root / "manifest.yaml", manifest)

        if staging_dir is not None:
            if output_dir.exists():
                shutil.rmtree(output_dir)
            staging_dir.replace(output_dir)
        return manifest
    except Exception:
        if staging_dir is not None and staging_dir.exists():
            shutil.rmtree(staging_dir)
        raise


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    repo_root = Path(__file__).resolve().parents[2]
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", type=Path, default=repo_root)
    parser.add_argument(
        "--base-config",
        type=Path,
        default=repo_root / "config/base/article_base.yaml",
    )
    parser.add_argument(
        "--geometry-dir",
        type=Path,
        default=repo_root / "config/geometry/article_files",
    )
    parser.add_argument(
        "--profile-file",
        type=Path,
        default=repo_root / "config/collimator/article_v2_collimator_profiles.csv",
    )
    parser.add_argument("--campaign-id", default=DEFAULT_CAMPAIGN_ID)
    parser.add_argument("--output-dir", type=Path)
    parser.add_argument(
        "--overwrite",
        action="store_true",
        help="replace the entire generated output directory after successful generation",
    )
    parser.add_argument("--energy-kev", type=parse_positive_float, default=DEFAULT_ENERGY_KEV)
    parser.add_argument(
        "--n-primary-per-pose",
        type=parse_positive_int,
        default=DEFAULT_N_PRIMARY_PER_POSE,
    )
    parser.add_argument("--threads", type=parse_positive_int, default=DEFAULT_THREADS)
    parser.add_argument("--base-seed", type=parse_non_negative_int, default=DEFAULT_BASE_SEED)
    parser.add_argument(
        "--grid-only",
        action="store_true",
        help="generate only explicitly selected grid conditions",
    )
    parser.add_argument(
        "--grid-condition",
        action="append",
        type=parse_grid_condition,
        help="grid condition in PHANTOM:PROFILE form; repeat for multiple conditions",
    )
    args = parser.parse_args(argv)
    if args.grid_only and not args.grid_condition:
        parser.error("--grid-only requires at least one --grid-condition")
    if args.grid_condition and not args.grid_only:
        parser.error("--grid-condition requires --grid-only")
    if args.grid_condition and len(set(args.grid_condition)) != len(args.grid_condition):
        parser.error("--grid-condition values must be unique")
    if args.output_dir is None:
        args.output_dir = args.repo_root / "config/generated" / args.campaign_id
    return args


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        manifest = generate(
            repo_root=args.repo_root,
            base_config_path=args.base_config,
            geometry_dir=args.geometry_dir,
            profile_file=args.profile_file,
            output_dir=args.output_dir,
            campaign_id=args.campaign_id,
            energy_keV=args.energy_kev,
            n_primary_per_pose=args.n_primary_per_pose,
            threads=args.threads,
            base_seed=args.base_seed,
            grid_only=args.grid_only,
            grid_conditions=args.grid_condition,
            overwrite=args.overwrite,
        )
    except Exception as error:
        print(f"source-response config generation error: {error}", file=sys.stderr)
        return 2

    summary = manifest["summary"]
    print(f"Generated {summary['config_count']} configs in {args.output_dir}")
    print(f"  physical_conditions: {summary['physical_condition_count']}")
    print(f"  task_count: {summary['task_count']}")
    print(f"  center_configs: {summary['center_config_count']}")
    print(f"  grid_configs: {summary['grid_config_count']}")
    print(f"  total_pose_runs: {summary['total_pose_runs']}")
    print(f"  total_primary: {summary['total_primary']}")
    print(f"  seed_range: {summary['seed_start']}..{summary['seed_end']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
