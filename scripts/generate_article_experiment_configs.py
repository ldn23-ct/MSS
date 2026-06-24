#!/usr/bin/env python3
"""Generate article experiment YAML configs for MSS simulation campaigns."""

from __future__ import annotations

import argparse
import copy
import sys
from pathlib import Path
from typing import Any

import yaml


DEFAULT_ENERGY_SCAN_KEV = (60, 160, 260, 360, 460, 560)
ARTICLE_GRID_OFFSETS_MM = (-24, -18, -15, -8, 0, 8, 15, 18, 24)
EXPERIMENT_ORDER = ("E0", "E1", "E3", "E4")
PHANTOMS_BY_GROUP = {
    "pmma": ("P0", "P1", "P2", "P3"),
    "metal": ("M0", "M1", "M2", "M3"),
}
DEPTH_LABELS = {
    0: "control",
    1: "shallow",
    2: "middle",
    3: "deep",
}


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


def format_energy(value: float | int) -> str:
    numeric = float(value)
    text = f"{numeric:.12g}"
    if "e" not in text.lower() and "." in text:
        text = text.rstrip("0").rstrip(".")
    return sanitize_token(text)


def format_energy_display(value: float | int) -> str:
    text = f"{float(value):.12g}"
    if "e" not in text.lower() and "." in text:
        text = text.rstrip("0").rstrip(".")
    return text


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
    if value <= 0.0:
        raise argparse.ArgumentTypeError("value must be positive")
    return value


def parse_positive_float_list(text: str) -> list[float]:
    parts = [part.strip() for part in text.split(",")]
    if not parts or any(part == "" for part in parts):
        raise argparse.ArgumentTypeError("energy list must be comma-separated positive numbers")
    values: list[float] = []
    for part in parts:
        try:
            value = float(part)
        except ValueError as error:
            raise argparse.ArgumentTypeError(
                "energy list must contain only numeric values"
            ) from error
        if value <= 0.0:
            raise argparse.ArgumentTypeError("energy values must be positive")
        values.append(value)
    return values


def parse_int_pair(text: str) -> tuple[int, int]:
    parts = [part.strip() for part in text.split(",")]
    if len(parts) != 2:
        raise argparse.ArgumentTypeError("offset must have form X,Y")
    try:
        return int(parts[0]), int(parts[1])
    except ValueError as error:
        raise argparse.ArgumentTypeError("offset values must be integers") from error


def parse_float_triplet(text: str) -> list[float]:
    parts = [part.strip() for part in text.split(",")]
    if len(parts) != 3:
        raise argparse.ArgumentTypeError("source position must have form X,Y,Z")
    try:
        return [float(part) for part in parts]
    except ValueError as error:
        raise argparse.ArgumentTypeError("source position values must be numeric") from error


def parse_experiment_list(text: str) -> list[str]:
    values = [part.strip().upper() for part in text.split(",") if part.strip()]
    if not values:
        raise argparse.ArgumentTypeError("at least one experiment is required")
    unknown = [value for value in values if value not in EXPERIMENT_ORDER]
    if unknown:
        raise argparse.ArgumentTypeError(
            "unknown experiment(s): " + ", ".join(unknown)
        )
    return values


def depth_id_from_phantom(phantom_id: str) -> int:
    if len(phantom_id) != 2 or phantom_id[0] not in {"P", "M"}:
        raise ValueError(f"invalid phantom id: {phantom_id}")
    try:
        value = int(phantom_id[1])
    except ValueError as error:
        raise ValueError(f"invalid phantom depth id: {phantom_id}") from error
    if value not in DEPTH_LABELS:
        raise ValueError(f"unsupported phantom depth id: {phantom_id}")
    return value


def normalize_phantom_geometry(source: dict[str, Any]) -> dict[str, Any]:
    geometry = copy.deepcopy(source)
    components = geometry.get("components")
    if not isinstance(components, list) or not components:
        raise ValueError("phantom geometry must contain a non-empty components list")

    root_name = None
    for component in components:
        if isinstance(component, dict) and component.get("host") == "World":
            root_name = str(component.get("name", ""))
            break
    if not root_name:
        raise ValueError("phantom geometry must contain one World daughter root component")

    metadata = geometry.setdefault("metadata", {})
    metadata["normalized_for_mss_vehicle_roi"] = True
    metadata["source_root_component"] = root_name

    roi = geometry.setdefault("roi", {})
    roi["name"] = "VehicleROI"

    for component in components:
        if not isinstance(component, dict):
            raise ValueError("phantom geometry components must be maps")
        if component.get("name") == root_name:
            component["name"] = "VehicleROI"
        if component.get("host") == root_name:
            component["host"] = "VehicleROI"

        # The P/M phantom files already encode the defect as explicit geometry.
        # Convert these components to ordinary daughters so C++ normal mode can build them.
        if component.get("is_insert") is True:
            component["is_insert"] = False
            for field in ("material", "region_id"):
                value = component.get(field)
                if isinstance(value, dict):
                    component[field] = value.get("normal") or value.get("abnormal")

    model_modes = geometry.setdefault("model_modes", {})
    abnormal = model_modes.setdefault("abnormal", {})
    abnormal["selected_target_component"] = None
    abnormal["rule"] = "not used for normalized explicit-phantom article geometries"
    abnormal["default_abnormal_material"] = None
    abnormal["alternative_abnormal_materials"] = []
    abnormal["target_region_id"] = None
    abnormal["recommended_single_target_components"] = []
    return geometry


def collect_geometry_info(
    repo_root: Path,
    phantom_dir: Path,
) -> dict[str, dict[str, Any]]:
    result: dict[str, dict[str, Any]] = {}
    for phantom_group, phantom_ids in PHANTOMS_BY_GROUP.items():
        for phantom_id in phantom_ids:
            source_path = phantom_dir / f"{phantom_id}.yaml"
            if not source_path.is_file():
                raise FileNotFoundError(f"phantom geometry does not exist: {source_path}")
            source = load_yaml(source_path)
            roi_name = source.get("roi", {}).get("name")
            root_components = [
                component
                for component in source.get("components", [])
                if isinstance(component, dict) and component.get("host") == "World"
            ]
            if roi_name != "VehicleROI" or not any(
                component.get("name") == "VehicleROI" for component in root_components
            ):
                raise ValueError(
                    f"phantom geometry must be canonical VehicleROI-compatible YAML: {source_path}"
                )
            defect = source.get("metadata", {}).get("defect")
            depth_id = depth_id_from_phantom(phantom_id)
            result[phantom_id] = {
                "phantom_id": phantom_id,
                "phantom_group": phantom_group,
                "source_geometry_file": repo_relative(repo_root, source_path),
                "geometry_file": repo_relative(repo_root, source_path),
                "defect_depth_id": depth_id,
                "defect_depth_label": DEPTH_LABELS[depth_id],
                "defect_material": None if defect is None else defect.get("material"),
            }
    return result


def set_single_pose(config: dict[str, Any], offset: tuple[int, int]) -> None:
    config["pose"] = copy.deepcopy(config.get("pose", {}))
    config["pose"]["mode"] = "list"
    config["pose"]["list"] = {
        "head_offset_x_mm": [int(offset[0])],
        "head_offset_y_mm": [int(offset[1])],
    }
    config["pose"]["grid"] = {"x_offsets_mm": [], "y_offsets_mm": []}
    config["pose"].setdefault("pose_id_rule", "pose_x{encoded_x}_y{encoded_y}")


def set_article_diagnostics(config: dict[str, Any], case_id: str) -> None:
    config["diagnostics"] = {
        "case_id": case_id,
        "phase_space": {
            "enable": False,
            "csv_name": "phase_space.csv",
        },
    }


def build_config(
    base_config: dict[str, Any],
    *,
    geometry_file: str,
    energy_keV: float,
    pose_offset: tuple[int, int],
    seed: int,
    threads: int,
    n_primary_per_pose: int,
    output_directory: str,
    source_pos_zero_mm: list[float] | None,
    case_id: str,
) -> dict[str, Any]:
    config = copy.deepcopy(base_config)
    config["schema_version"] = 2

    config["run"] = copy.deepcopy(config["run"])
    config["run"]["random_seed"] = seed
    config["run"]["number_of_threads"] = threads
    config["run"]["n_primary_per_pose"] = n_primary_per_pose

    config["vehicle"] = copy.deepcopy(config["vehicle"])
    config["vehicle"]["geometry_file"] = geometry_file
    config["vehicle"]["model_type"] = "normal"
    config["vehicle"]["selected_target_component"] = None
    config["vehicle"]["abnormal_material"] = None

    set_single_pose(config, pose_offset)

    config["source"] = copy.deepcopy(config["source"])
    config["source"]["energy_mode"] = "mono"
    config["source"]["mono_energy_keV"] = float(energy_keV)
    config["source"]["incident_theta_deg"] = 90.0
    config["source"]["focal_spot_diameter_mm"] = 5.0
    if source_pos_zero_mm is not None:
        config["source"]["source_pos_zero_mm"] = list(source_pos_zero_mm)

    config["collimator"] = copy.deepcopy(config["collimator"])
    config["collimator"]["enable"] = True

    config["output"] = copy.deepcopy(config["output"])
    config["output"]["output_directory"] = output_directory
    config["output"]["existing_run_policy"] = "fail"

    set_article_diagnostics(config, case_id)
    return config


def grid_offsets() -> list[tuple[str, tuple[int, int]]]:
    poses: list[tuple[str, tuple[int, int]]] = []
    for x_mm in ARTICLE_GRID_OFFSETS_MM:
        for y_mm in ARTICLE_GRID_OFFSETS_MM:
            poses.append((f"grid_x{x_mm}_y{y_mm}", (x_mm, y_mm)))
    return poses


def physical_cases(
    experiments: list[str],
    e_star_kev: float | None,
    e_star_metal_kev: float | None,
    pmma_energies_kev: list[float],
    metal_energies_kev: list[float],
    center_pose_offset: tuple[int, int],
    reference_pose_offset: tuple[int, int],
) -> list[dict[str, Any]]:
    cases: list[dict[str, Any]] = []
    grid = grid_offsets()
    for experiment in EXPERIMENT_ORDER:
        if experiment not in experiments:
            continue
        if experiment == "E0":
            for phantom_id in PHANTOMS_BY_GROUP["pmma"]:
                for energy in pmma_energies_kev:
                    cases.append(
                        {
                            "experiment": experiment,
                            "phantom_id": phantom_id,
                            "energy_keV": float(energy),
                            "pose_label": "center",
                            "pose_offset": center_pose_offset,
                        }
                    )
        elif experiment == "E1":
            if e_star_kev is None:
                raise ValueError("E1 requires --e-star-kev")
            for phantom_id in PHANTOMS_BY_GROUP["pmma"]:
                for pose_label, pose_offset in grid:
                    cases.append(
                        {
                            "experiment": experiment,
                            "phantom_id": phantom_id,
                            "energy_keV": float(e_star_kev),
                            "pose_label": pose_label,
                            "pose_offset": pose_offset,
                        }
                    )
        elif experiment == "E3":
            for phantom_id in PHANTOMS_BY_GROUP["metal"]:
                for energy in metal_energies_kev:
                    for pose_label, pose_offset in (
                        ("center", center_pose_offset),
                        ("reference", reference_pose_offset),
                    ):
                        cases.append(
                            {
                                "experiment": experiment,
                                "phantom_id": phantom_id,
                                "energy_keV": float(energy),
                                "pose_label": pose_label,
                                "pose_offset": pose_offset,
                            }
                        )
        elif experiment == "E4":
            if e_star_metal_kev is None:
                raise ValueError("E4 requires --e-star-metal-kev")
            for phantom_id in PHANTOMS_BY_GROUP["metal"]:
                for pose_label, pose_offset in grid:
                    cases.append(
                        {
                            "experiment": experiment,
                            "phantom_id": phantom_id,
                            "energy_keV": float(e_star_metal_kev),
                            "pose_label": pose_label,
                            "pose_offset": pose_offset,
                        }
                    )
    return cases


def case_id_for(case: dict[str, Any], batch_index: int, seed: int) -> str:
    return f"article_{condition_id_for(case)}_b{batch_index}_seed{seed}"


def condition_id_for(case: dict[str, Any]) -> str:
    energy = format_energy(case["energy_keV"])
    return f"{case['experiment']}_{case['phantom_id']}_E{energy}_{sanitize_token(case['pose_label'])}"


def generate(
    repo_root: Path,
    base_config_path: Path,
    phantom_dir: Path,
    output_dir: Path,
    campaign_id: str,
    experiments: list[str],
    threads: int | None,
    e_star_kev: float | None,
    e_star_metal_kev: float | None,
    pmma_energies_kev: list[float] | None = None,
    metal_energies_kev: list[float] | None = None,
    grid_size: str | None = None,
    grid_step_mm: int | None = None,
    center_pose_offset: tuple[int, int] = (0, 0),
    reference_pose_offset: tuple[int, int] = (40, 0),
    base_seed: int = 1234,
    batch_count: int = 1,
    n_primary_per_pose: int | None = None,
    source_pos_zero_mm: list[float] | None = None,
    smoke: bool = False,
) -> dict[str, Any]:
    if threads is None:
        if smoke:
            threads = 1
        else:
            raise ValueError("--threads is required for formal article config generation")
    if threads <= 0:
        raise ValueError("threads must be positive")
    if batch_count <= 0:
        raise ValueError("batch_count must be positive")
    if pmma_energies_kev is None:
        pmma_energies_kev = [float(value) for value in DEFAULT_ENERGY_SCAN_KEV]
    if metal_energies_kev is None:
        metal_energies_kev = [float(value) for value in DEFAULT_ENERGY_SCAN_KEV]
    if not pmma_energies_kev or any(value <= 0.0 for value in pmma_energies_kev):
        raise ValueError("pmma_energies_kev must contain positive values")
    if not metal_energies_kev or any(value <= 0.0 for value in metal_energies_kev):
        raise ValueError("metal_energies_kev must contain positive values")

    base_config = load_yaml(base_config_path)
    base_n_primary = int(base_config.get("run", {}).get("n_primary_per_pose", 0))
    if base_n_primary <= 0 and n_primary_per_pose is None:
        raise ValueError("base config run.n_primary_per_pose must be positive")
    if n_primary_per_pose is None:
        n_primary_per_pose = 1000 if smoke else base_n_primary

    geometry_info = collect_geometry_info(repo_root, phantom_dir)
    cases = physical_cases(
        experiments,
        e_star_kev,
        e_star_metal_kev,
        pmma_energies_kev,
        metal_energies_kev,
        center_pose_offset,
        reference_pose_offset,
    )
    if smoke:
        cases = cases[: min(len(cases), 4)]

    config_dir = output_dir / "configs"
    manifest: dict[str, Any] = {
        "schema_version": 1,
        "experiment": "article_simulation_campaign",
        "campaign_id": campaign_id,
        "base_config": repo_relative(repo_root, base_config_path),
        "phantom_source_dir": repo_relative(repo_root, phantom_dir),
        "raw_output_root": f"results/article/{campaign_id}/runs",
        "condition_output_root": f"results/article/{campaign_id}/by_condition",
        "experiments": experiments,
        "pmma_energies_keV": list(pmma_energies_kev),
        "metal_energies_keV": list(metal_energies_kev),
        "e_star_keV": e_star_kev,
        "e_star_metal_keV": e_star_metal_kev,
        "grid": {
            "type": "nonuniform_local_roi_sampling",
            "offsets_mm": list(ARTICLE_GRID_OFFSETS_MM),
        },
        "source": {
            "incident_theta_deg": 90.0,
            "focal_spot_diameter_mm": 5.0,
            "source_pos_zero_mm_override": source_pos_zero_mm,
        },
        "threading": {
            "threads": threads,
            "policy": "explicit_cli_required",
        },
        "batching": {
            "batch_count": batch_count,
            "base_seed": base_seed,
        },
        "n_primary_per_pose": n_primary_per_pose,
        "slit_run_dimension": False,
        "phantoms": geometry_info,
        "run_safety": {
            "large_run_case_threshold": 100,
            "allow_large_run_required": True,
        },
        "cases": [],
    }

    for case_index, case in enumerate(cases):
        phantom = geometry_info[str(case["phantom_id"])]
        condition_id = condition_id_for(case)
        energy_text = format_energy(case["energy_keV"])
        condition_output_directory = (
            f"results/article/{campaign_id}/by_condition/{case['experiment']}/{case['phantom_id']}/"
            f"E{energy_text}/{sanitize_token(case['pose_label'])}"
        )
        for batch_index in range(batch_count):
            seed = base_seed + case_index * batch_count + batch_index
            case_id = case_id_for(case, batch_index, seed)
            raw_output_directory = f"results/article/{campaign_id}/runs/{condition_id}/b{batch_index}"
            config = build_config(
                base_config,
                geometry_file=phantom["geometry_file"],
                energy_keV=case["energy_keV"],
                pose_offset=case["pose_offset"],
                seed=seed,
                threads=threads,
                n_primary_per_pose=n_primary_per_pose,
                output_directory=raw_output_directory,
                source_pos_zero_mm=source_pos_zero_mm,
                case_id=case_id,
            )
            config_path = config_dir / str(case["experiment"]) / f"{case_id}.yaml"
            write_yaml(config_path, config)
            manifest["cases"].append(
                {
                    "case_id": case_id,
                    "condition_id": condition_id,
                    "config_file": repo_relative(repo_root, config_path),
                    "experiment": case["experiment"],
                    "phantom_id": case["phantom_id"],
                    "phantom_group": phantom["phantom_group"],
                    "defect_depth_id": phantom["defect_depth_id"],
                    "defect_depth_label": phantom["defect_depth_label"],
                    "defect_material": phantom["defect_material"],
                    "geometry_file": phantom["geometry_file"],
                    "energy_keV": case["energy_keV"],
                    "pose": case["pose_label"],
                    "head_offset_x_mm": case["pose_offset"][0],
                    "head_offset_y_mm": case["pose_offset"][1],
                    "batch_index": batch_index,
                    "batch_count": batch_count,
                    "case_index": case_index,
                    "seed": seed,
                    "threads": threads,
                    "n_primary_per_pose": n_primary_per_pose,
                    "raw_output_directory": raw_output_directory,
                    "condition_output_directory": condition_output_directory,
                    "output_directory": raw_output_directory,
                    "collimator_enable": True,
                }
            )

    manifest["physical_condition_count"] = len(cases)
    manifest["total_case_count"] = len(manifest["cases"])
    write_yaml(output_dir / "manifest.yaml", manifest)
    return manifest


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    repo_root = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", type=Path, default=repo_root)
    parser.add_argument(
        "--base-config",
        type=Path,
        default=repo_root / "config/base/article_base.yaml",
    )
    parser.add_argument(
        "--phantom-dir",
        type=Path,
        default=repo_root / "config/geometry/phantom_yaml_files",
    )
    parser.add_argument("--campaign-id", default="article")
    parser.add_argument("--output-dir", type=Path)
    parser.add_argument("--experiments", type=parse_experiment_list, default=list(EXPERIMENT_ORDER))
    parser.add_argument("--threads", type=parse_positive_int)
    parser.add_argument("--e-star-kev", type=parse_positive_float)
    parser.add_argument("--e-star-metal-kev", type=parse_positive_float)
    parser.add_argument(
        "--pmma-energies-kev",
        type=parse_positive_float_list,
        default=[float(value) for value in DEFAULT_ENERGY_SCAN_KEV],
        help="comma-separated mono energies for E0 PMMA scan, e.g. 60,160,260",
    )
    parser.add_argument(
        "--metal-energies-kev",
        type=parse_positive_float_list,
        default=[float(value) for value in DEFAULT_ENERGY_SCAN_KEV],
        help="comma-separated mono energies for E3 metal scan, e.g. 60,160,260",
    )
    parser.add_argument(
        "--grid-size",
        help="deprecated; article grid uses fixed nonuniform offsets",
    )
    parser.add_argument(
        "--grid-step-mm",
        type=parse_positive_int,
        help="deprecated; article grid uses fixed nonuniform offsets",
    )
    parser.add_argument("--center-pose-offset", type=parse_int_pair, default=(0, 0))
    parser.add_argument("--reference-pose-offset", type=parse_int_pair, default=(40, 0))
    parser.add_argument("--base-seed", type=parse_non_negative_int, default=1234)
    parser.add_argument("--batch-count", type=parse_positive_int, default=1)
    parser.add_argument("--n-primary-per-pose", type=parse_positive_int)
    parser.add_argument("--source-pos-zero-mm", type=parse_float_triplet)
    parser.add_argument("--smoke", action="store_true")
    args = parser.parse_args(argv)
    if args.output_dir is None:
        args.output_dir = args.repo_root / "config/generated/article" / args.campaign_id
    return args


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        manifest = generate(
            args.repo_root,
            args.base_config,
            args.phantom_dir,
            args.output_dir,
            args.campaign_id,
            args.experiments,
            args.threads,
            args.e_star_kev,
            args.e_star_metal_kev,
            args.pmma_energies_kev,
            args.metal_energies_kev,
            args.grid_size,
            args.grid_step_mm,
            args.center_pose_offset,
            args.reference_pose_offset,
            args.base_seed,
            args.batch_count,
            args.n_primary_per_pose,
            args.source_pos_zero_mm,
            args.smoke,
        )
    except Exception as error:
        print(f"article config generation error: {error}", file=sys.stderr)
        return 2
    print(f"Generated {len(manifest['cases'])} article configs in {args.output_dir}")
    print(f"  physical_conditions: {manifest['physical_condition_count']}")
    print(f"  total_cases: {manifest['total_case_count']}")
    print(f"  n_primary_per_case: {manifest['n_primary_per_pose']}")
    print(f"  batch_count: {manifest['batching']['batch_count']}")
    print(
        "  n_primary_per_physical_condition: "
        f"{manifest['n_primary_per_pose'] * manifest['batching']['batch_count']}"
    )
    print(f"  threads: {manifest['threading']['threads']}")
    print(
        "  pmma_energies_keV: "
        + ",".join(format_energy_display(value) for value in manifest["pmma_energies_keV"])
    )
    print(
        "  metal_energies_keV: "
        + ",".join(format_energy_display(value) for value in manifest["metal_energies_keV"])
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
