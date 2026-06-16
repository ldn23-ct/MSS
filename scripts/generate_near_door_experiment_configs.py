#!/usr/bin/env python3
"""Generate near-door energy-scan YAML configs for v2 MSS runs."""

from __future__ import annotations

import argparse
import copy
from pathlib import Path
from typing import Any

import yaml


ENERGIES_KEV = (60, 160, 260, 360, 460, 560)
DEFAULT_TARGET_COMPONENT = "near_rear_door_insert"
PE_MATERIAL = "G4_POLYETHYLENE"
FLOUR_MATERIAL = "Vehicle_Flour"
HIGH_Z_MATERIAL = "G4_W"


def load_yaml(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as stream:
        value = yaml.safe_load(stream)
    if not isinstance(value, dict):
        raise ValueError(f"YAML root must be a map: {path}")
    return value


def write_yaml(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as stream:
        yaml.safe_dump(value, stream, sort_keys=False, allow_unicode=False, width=100)


def repo_relative(repo_root: Path, path: Path) -> str:
    try:
        return path.resolve().relative_to(repo_root.resolve()).as_posix()
    except ValueError:
        return path.resolve().as_posix()


def parse_int_pair(text: str) -> tuple[int, int]:
    parts = [part.strip() for part in text.split(",")]
    if len(parts) != 2:
        raise argparse.ArgumentTypeError("offset must have form X,Y")
    try:
        return int(parts[0]), int(parts[1])
    except ValueError as error:
        raise argparse.ArgumentTypeError("offset values must be integers") from error


def parse_int_list(text: str) -> list[int]:
    values: list[int] = []
    for part in text.split(","):
        stripped = part.strip()
        if not stripped:
            continue
        try:
            values.append(int(stripped))
        except ValueError as error:
            raise argparse.ArgumentTypeError("seed values must be integers") from error
    if not values:
        raise argparse.ArgumentTypeError("at least one seed is required")
    return values


def parse_detector_range(text: str) -> dict[str, list[float]]:
    parts = [part.strip() for part in text.split(",")]
    if len(parts) != 4:
        raise argparse.ArgumentTypeError(
            "open detector range must have form XMIN,XMAX,YMIN,YMAX"
        )
    try:
        x_min, x_max, y_min, y_max = [float(part) for part in parts]
    except ValueError as error:
        raise argparse.ArgumentTypeError("open detector range values must be numeric") from error
    if x_min >= x_max or y_min >= y_max:
        raise argparse.ArgumentTypeError("open detector range min values must be < max values")
    return {
        "detector_x_range_zero_mm": [x_min, x_max],
        "detector_y_range_zero_mm": [y_min, y_max],
    }


def validate_target_component(
    repo_root: Path,
    base_config_path: Path,
    base_config: dict[str, Any],
    target_component: str,
) -> None:
    geometry_file = base_config.get("vehicle", {}).get("geometry_file")
    if not isinstance(geometry_file, str) or not geometry_file:
        raise ValueError("base config vehicle.geometry_file must be a non-empty string")

    geometry_path = Path(geometry_file)
    if not geometry_path.is_absolute():
        repo_candidate = repo_root / geometry_path
        base_candidate = base_config_path.parent / geometry_path
        geometry_path = repo_candidate if repo_candidate.is_file() else base_candidate
    if not geometry_path.is_file():
        return

    geometry = load_yaml(geometry_path)
    components = geometry.get("components")
    if not isinstance(components, list):
        raise ValueError(f"vehicle geometry components must be a list: {geometry_path}")
    for component in components:
        if isinstance(component, dict) and component.get("name") == target_component:
            if component.get("is_insert") is not True:
                raise ValueError(f"target component is not an insert: {target_component}")
            return
    raise ValueError(f"target component does not exist in geometry: {target_component}")


def set_single_pose(config: dict[str, Any], offset: tuple[int, int]) -> None:
    config["pose"] = copy.deepcopy(config.get("pose", {}))
    config["pose"]["mode"] = "list"
    config["pose"]["list"] = {
        "head_offset_x_mm": [offset[0]],
        "head_offset_y_mm": [offset[1]],
    }
    config["pose"]["grid"] = {"x_offsets_mm": [], "y_offsets_mm": []}
    config["pose"].setdefault("pose_id_rule", "pose_x{encoded_x}_y{encoded_y}")


def set_model_state(
    config: dict[str, Any],
    model_state: str,
    target_component: str,
    material: str | None,
) -> None:
    config["vehicle"] = copy.deepcopy(config["vehicle"])
    if material is None:
        config["vehicle"]["model_type"] = "normal"
        config["vehicle"]["selected_target_component"] = None
        config["vehicle"]["abnormal_material"] = None
        return
    config["vehicle"]["model_type"] = "abnormal"
    config["vehicle"]["selected_target_component"] = target_component
    config["vehicle"]["abnormal_material"] = material


def set_diagnostics(config: dict[str, Any], case_id: str) -> None:
    config["diagnostics"] = {
        "case_id": case_id,
        "phase_space": {
            "enable": False,
            "csv_name": "phase_space.csv",
        },
    }


def build_config(
    base_config: dict[str, Any],
    system_id: str,
    pose_label: str,
    pose_offset: tuple[int, int],
    model_state: str,
    material: str | None,
    energy_keV: int,
    seed: int,
    output_directory: str,
    target_component: str,
    open_detector_range: dict[str, list[float]] | None,
) -> dict[str, Any]:
    config = copy.deepcopy(base_config)
    config["schema_version"] = 2
    config["run"] = copy.deepcopy(config["run"])
    config["run"]["random_seed"] = seed
    set_single_pose(config, pose_offset)
    set_model_state(config, model_state, target_component, material)

    config["source"] = copy.deepcopy(config["source"])
    config["source"]["energy_mode"] = "mono"
    config["source"]["mono_energy_keV"] = float(energy_keV)

    config["collimator"] = copy.deepcopy(config["collimator"])
    config["collimator"]["enable"] = system_id == "collimated"

    if system_id == "open" and open_detector_range is not None:
        config["detector"] = copy.deepcopy(config["detector"])
        config["detector"]["detector_x_range_zero_mm"] = open_detector_range[
            "detector_x_range_zero_mm"
        ]
        config["detector"]["detector_y_range_zero_mm"] = open_detector_range[
            "detector_y_range_zero_mm"
        ]

    config["output"] = copy.deepcopy(config["output"])
    config["output"]["output_directory"] = output_directory
    config["output"]["existing_run_policy"] = "overwrite"
    set_diagnostics(
        config,
        f"near_door_{system_id}_{pose_label}_{model_state}_E{energy_keV}_seed{seed}",
    )
    return config


def core_cases(include_high_z: bool) -> list[tuple[str, str, str, str | None]]:
    cases = [
        ("open", "poseR", "normal", None),
        ("open", "poseC", "normal", None),
        ("open", "poseC", "cavityPE", PE_MATERIAL),
        ("open", "poseC", "cavityFlour", FLOUR_MATERIAL),
        ("collimated", "poseR", "normal", None),
        ("collimated", "poseC", "normal", None),
        ("collimated", "poseC", "cavityPE", PE_MATERIAL),
        ("collimated", "poseC", "cavityFlour", FLOUR_MATERIAL),
    ]
    if include_high_z:
        cases.extend(
            [
                ("open", "poseC", "cavityW", HIGH_Z_MATERIAL),
                ("collimated", "poseC", "cavityW", HIGH_Z_MATERIAL),
            ]
        )
    return cases


def generate(
    repo_root: Path,
    base_config_path: Path,
    output_dir: Path,
    seeds: list[int],
    pose_r_offset: tuple[int, int],
    pose_c_offset: tuple[int, int],
    target_component: str,
    include_high_z: bool,
    open_detector_range: dict[str, list[float]] | None,
) -> dict[str, Any]:
    base_config = load_yaml(base_config_path)
    validate_target_component(repo_root, base_config_path, base_config, target_component)

    manifest: dict[str, Any] = {
        "schema_version": 2,
        "experiment": "near_door_energy_scan",
        "base_config": repo_relative(repo_root, base_config_path),
        "target_component": target_component,
        "energies_keV": list(ENERGIES_KEV),
        "seeds": seeds,
        "pose_offsets": {
            "poseR": {
                "head_offset_x_mm": pose_r_offset[0],
                "head_offset_y_mm": pose_r_offset[1],
            },
            "poseC": {
                "head_offset_x_mm": pose_c_offset[0],
                "head_offset_y_mm": pose_c_offset[1],
            },
        },
        "open_detector_range_override": open_detector_range,
        "cases": [],
    }

    pose_offsets = {"poseR": pose_r_offset, "poseC": pose_c_offset}
    config_dir = output_dir / "configs"
    for system_id, pose_label, model_state, material in core_cases(include_high_z):
        for energy_keV in ENERGIES_KEV:
            for seed in seeds:
                file_name = (
                    f"near_door_{system_id}_{pose_label}_{model_state}_"
                    f"E{energy_keV}_seed{seed}.yaml"
                )
                run_output_dir = (
                    f"results/near_door/{system_id}/{pose_label}/"
                    f"{model_state}/E{energy_keV}/seed{seed}"
                )
                config = build_config(
                    base_config,
                    system_id,
                    pose_label,
                    pose_offsets[pose_label],
                    model_state,
                    material,
                    energy_keV,
                    seed,
                    run_output_dir,
                    target_component,
                    open_detector_range,
                )
                config_path = config_dir / file_name
                write_yaml(config_path, config)
                manifest["cases"].append(
                    {
                        "config_file": repo_relative(repo_root, config_path),
                        "system": system_id,
                        "pose": pose_label,
                        "model_state": model_state,
                        "energy_keV": energy_keV,
                        "seed": seed,
                        "collimator_enable": config["collimator"]["enable"],
                        "output_directory": run_output_dir,
                    }
                )

    write_yaml(output_dir / "manifest.yaml", manifest)
    return manifest


def parse_args() -> argparse.Namespace:
    repo_root = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", type=Path, default=repo_root)
    parser.add_argument(
        "--base-config",
        type=Path,
        default=repo_root / "config/base/simulation_config_v2.yaml",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=repo_root / "config/generated/near_door",
    )
    parser.add_argument("--seeds", type=parse_int_list, default=[1234])
    parser.add_argument("--pose-r-offset", type=parse_int_pair, required=True)
    parser.add_argument("--pose-c-offset", type=parse_int_pair, required=True)
    parser.add_argument("--target-component", default=DEFAULT_TARGET_COMPONENT)
    parser.add_argument("--include-high-z", action="store_true")
    parser.add_argument("--open-detector-range", type=parse_detector_range)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    manifest = generate(
        args.repo_root,
        args.base_config,
        args.output_dir,
        args.seeds,
        args.pose_r_offset,
        args.pose_c_offset,
        args.target_component,
        args.include_high_z,
        args.open_detector_range,
    )
    print(f"Generated {len(manifest['cases'])} near-door configs in {args.output_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
