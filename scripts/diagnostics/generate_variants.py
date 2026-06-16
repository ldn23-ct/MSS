#!/usr/bin/env python3
"""Generate the eight v2 diagnostic experiment configurations."""

from __future__ import annotations

import argparse
import copy
from pathlib import Path
from typing import Any, Iterable

import yaml


ORIGINAL_DETECTOR = {
    "detector_z_zero_mm": -73.0,
    "detector_x_range_zero_mm": [-646.0, -404.0],
    "detector_y_range_zero_mm": [-50.0, 50.0],
    "accept_direction": "negative_z",
}

LARGE_SCORING_PLANE = {
    "detector_z_zero_mm": -73.0,
    "detector_x_range_zero_mm": [-1000.0, 1400.0],
    "detector_y_range_zero_mm": [-750.0, 750.0],
    "accept_direction": "negative_z",
}

PMMA_MATERIAL = "G4_PLEXIGLASS"
METAL_MATERIALS = {"G4_Fe", "G4_Al"}


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


def replace_material_value(value: Any, mode: str) -> Any:
    if isinstance(value, str):
        if mode == "metal_to_pmma" and value in METAL_MATERIALS:
            return PMMA_MATERIAL
        if mode == "nonair_to_pmma" and value != "G4_AIR":
            return PMMA_MATERIAL
        return value
    if isinstance(value, dict):
        return {key: replace_material_value(item, mode) for key, item in value.items()}
    raise ValueError(f"unsupported component material value: {value!r}")


def make_geometry_variant(source: dict[str, Any], mode: str) -> dict[str, Any]:
    if mode not in {"metal_to_pmma", "nonair_to_pmma"}:
        raise ValueError(f"unknown geometry variant mode: {mode}")

    variant = copy.deepcopy(source)
    metadata = variant.setdefault("metadata", {})
    metadata["variant_id"] = mode
    metadata["variant_source_model"] = source.get("metadata", {}).get("model_name", "unknown")
    metadata["variant_material"] = PMMA_MATERIAL
    if mode == "metal_to_pmma":
        metadata["variant_rule"] = "replace G4_Fe and G4_Al component materials with G4_PLEXIGLASS"
    else:
        metadata["variant_rule"] = "replace every non-G4_AIR component material with G4_PLEXIGLASS"
    metadata["model_name"] = f"{metadata.get('model_name', 'vehicle_roi')}_{mode}"

    materials = variant.setdefault("materials", {})
    materials.setdefault(
        PMMA_MATERIAL,
        {
            "type": "NIST",
            "built_in": True,
            "semantic": "PMMA diagnostic replacement material",
        },
    )

    components = variant.get("components")
    if not isinstance(components, list) or not components:
        raise ValueError("vehicle geometry must contain a non-empty components list")
    for component in components:
        if not isinstance(component, dict) or "material" not in component:
            raise ValueError("each component must be a map with a material field")
        component["material"] = replace_material_value(component["material"], mode)

    return variant


def validate_pmma_box(pmma_box: dict[str, Any]) -> None:
    components = pmma_box.get("components")
    if not isinstance(components, list) or len(components) != 1:
        raise ValueError("PMMA box control must contain exactly one component")
    component = components[0]
    if component.get("name") != "VehicleROI" or component.get("material") != PMMA_MATERIAL:
        raise ValueError("PMMA box control must be a single G4_PLEXIGLASS VehicleROI")
    if component.get("host") != "World" or component.get("is_insert") is not False:
        raise ValueError("PMMA box VehicleROI must be a non-insert World daughter")


def build_case_config(
    base_config: dict[str, Any],
    case_id: str,
    geometry_file: str,
    open_geometry: bool,
) -> dict[str, Any]:
    config = copy.deepcopy(base_config)
    config["schema_version"] = 2
    config["vehicle"]["geometry_file"] = geometry_file
    config["vehicle"]["model_type"] = "normal"
    config["vehicle"]["selected_target_component"] = None
    config["collimator"]["enable"] = not open_geometry
    config["detector"] = copy.deepcopy(LARGE_SCORING_PLANE if open_geometry else ORIGINAL_DETECTOR)
    config["output"]["output_directory"] = f"results/diagnostics/{case_id}"
    config["diagnostics"] = {
        "case_id": case_id,
        "phase_space": {
            "enable": open_geometry,
            "csv_name": "phase_space.csv",
        },
    }
    return config


def case_definitions(geometry_paths: dict[str, str]) -> Iterable[tuple[str, str, bool]]:
    for geometry_id in ("vehicle", "metal_to_pmma", "nonair_to_pmma", "pmma_box"):
        yield f"{geometry_id}_slit", geometry_paths[geometry_id], False
        yield f"{geometry_id}_open", geometry_paths[geometry_id], True


def generate(
    repo_root: Path,
    base_config_path: Path,
    vehicle_geometry_path: Path,
    pmma_box_path: Path,
    output_dir: Path,
) -> dict[str, Any]:
    base_config = load_yaml(base_config_path)
    vehicle_geometry = load_yaml(vehicle_geometry_path)
    pmma_box = load_yaml(pmma_box_path)
    validate_pmma_box(pmma_box)

    geometry_dir = output_dir / "geometries"
    config_dir = output_dir / "configs"
    metal_path = geometry_dir / "vehicle_roi_v04_metal_to_pmma.yaml"
    nonair_path = geometry_dir / "vehicle_roi_v04_nonair_to_pmma.yaml"
    write_yaml(metal_path, make_geometry_variant(vehicle_geometry, "metal_to_pmma"))
    write_yaml(nonair_path, make_geometry_variant(vehicle_geometry, "nonair_to_pmma"))

    def repo_relative(path: Path) -> str:
        try:
            return path.resolve().relative_to(repo_root.resolve()).as_posix()
        except ValueError:
            return path.resolve().as_posix()

    geometry_paths = {
        "vehicle": repo_relative(vehicle_geometry_path),
        "metal_to_pmma": repo_relative(metal_path),
        "nonair_to_pmma": repo_relative(nonair_path),
        "pmma_box": repo_relative(pmma_box_path),
    }

    manifest: dict[str, Any] = {
        "schema_version": 2,
        "experiment": "vehicle_backscatter_diagnostics",
        "base_config": repo_relative(base_config_path),
        "geometry_variants": geometry_paths,
        "detector_presets": {
            "original": ORIGINAL_DETECTOR,
            "large_scoring_plane": LARGE_SCORING_PLANE,
        },
        "cases": [],
    }

    for case_id, geometry_file, open_geometry in case_definitions(geometry_paths):
        config = build_case_config(base_config, case_id, geometry_file, open_geometry)
        config_path = config_dir / f"{case_id}.yaml"
        write_yaml(config_path, config)
        manifest["cases"].append(
            {
                "case_id": case_id,
                "config_file": repo_relative(config_path),
                "geometry_file": geometry_file,
                "collimator_enable": not open_geometry,
                "phase_space_enable": open_geometry,
            }
        )

    write_yaml(output_dir / "manifest.yaml", manifest)
    return manifest


def parse_args() -> argparse.Namespace:
    repo_root = Path(__file__).resolve().parents[2]
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", type=Path, default=repo_root)
    parser.add_argument(
        "--base-config",
        type=Path,
        default=repo_root / "config/base/diagnostics_base.yaml",
    )
    parser.add_argument(
        "--vehicle-geometry",
        type=Path,
        default=repo_root / "config/geometry/vehicle_roi_v04.yaml",
    )
    parser.add_argument("--pmma-box", type=Path, default=repo_root / "config/geometry/pmma_box.yaml")
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=repo_root / "config/generated/diagnostics",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    manifest = generate(
        args.repo_root,
        args.base_config,
        args.vehicle_geometry,
        args.pmma_box,
        args.output_dir,
    )
    print(f"Generated {len(manifest['cases'])} diagnostic cases in {args.output_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
