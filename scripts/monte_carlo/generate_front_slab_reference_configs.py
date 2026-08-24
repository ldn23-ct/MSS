#!/usr/bin/env python3
"""Generate the dedicated P4 55 mm uniform-PMMA front-slab grid campaign."""

from __future__ import annotations

import argparse
import math
import shutil
import sys
import tempfile
from pathlib import Path
from typing import Any

from .generate_source_response_experiment_configs import (
    GRID_OFFSETS_MM,
    PROFILE_SETTINGS,
    build_config,
    build_pose_id,
    format_number_token,
    load_yaml,
    parse_non_negative_int,
    parse_positive_float,
    parse_positive_int,
    repo_relative,
    validate_geometry,
    validate_profile_file,
    write_yaml,
)


REFERENCE_MODEL_ID = "P4_front_slab_55mm"
REFERENCE_TYPE = "uniform_pmma_front_slab"
REFERENCE_THICKNESS_MM = 55.0
REFERENCE_PROFILE_ID = "P001"
REFERENCE_SLIT_ID = "S4"
DEFAULT_CAMPAIGN_ID = "articlev3_p4_front_slab_55mm_100m"
DEFAULT_ENERGY_KEV = 560.0
DEFAULT_N_PRIMARY_PER_POSE = 100_000_000
DEFAULT_THREADS = 6
DEFAULT_BASE_SEED = 11_000
REFERENCE_MANIFEST_NAME = "reference_manifest.yaml"


def validate_reference_geometry(path: Path) -> dict[str, Any]:
    """Validate the exact geometry needed by the frozen E3 slab comparison."""
    validate_geometry(path, REFERENCE_MODEL_ID)
    geometry = load_yaml(path)
    metadata = geometry.get("metadata", {})
    reference = metadata.get("reference", {})
    roi = geometry.get("roi", {})
    components = geometry.get("components", [])
    if not isinstance(reference, dict) or reference.get("type") != REFERENCE_TYPE:
        raise ValueError(f"geometry metadata.reference.type must be {REFERENCE_TYPE}: {path}")
    try:
        thickness = float(reference.get("thickness_mm"))
    except (TypeError, ValueError) as error:
        raise ValueError(f"geometry reference thickness must be numeric: {path}") from error
    if not math.isclose(thickness, REFERENCE_THICKNESS_MM):
        raise ValueError(f"geometry reference thickness must be 55 mm: {path}")
    if roi.get("center_mm") != [0.0, 0.0, 27.5]:
        raise ValueError(f"front-slab roi.center_mm must equal [0, 0, 27.5]: {path}")
    if roi.get("size_mm") != [1000.0, 1000.0, 55.0]:
        raise ValueError(f"front-slab roi.size_mm must equal [1000, 1000, 55]: {path}")
    if roi.get("material") != "G4_PLEXIGLASS":
        raise ValueError(f"front-slab material must be G4_PLEXIGLASS: {path}")
    if len(components) != 1 or not isinstance(components[0], dict):
        raise ValueError(f"front-slab geometry must contain exactly one component: {path}")
    root = components[0]
    expected_root = {
        "name": "VehicleROI",
        "host": "World",
        "center_mm": [0.0, 0.0, 27.5],
        "size_mm": [1000.0, 1000.0, 55.0],
        "material": "G4_PLEXIGLASS",
        "is_insert": False,
        "half_size_mm": [500.0, 500.0, 27.5],
    }
    for field, expected in expected_root.items():
        if root.get(field) != expected:
            raise ValueError(
                f"front-slab root {field} must equal {expected!r}, got {root.get(field)!r}: {path}"
            )
    if root.get("aabb_mm", {}).get("z") != [0.0, 55.0]:
        raise ValueError(f"front-slab root must occupy 0 <= z <= 55 mm: {path}")
    if any(bool(item.get("is_insert")) for item in components if isinstance(item, dict)):
        raise ValueError(f"front-slab geometry must not contain an insert: {path}")
    return geometry


def grid_points() -> list[tuple[float, float]]:
    return [(x, y) for x in GRID_OFFSETS_MM for y in GRID_OFFSETS_MM]


def generate(
    repo_root: Path,
    base_config_path: Path,
    geometry_path: Path,
    profile_file: Path,
    output_dir: Path,
    *,
    campaign_id: str = DEFAULT_CAMPAIGN_ID,
    energy_keV: float = DEFAULT_ENERGY_KEV,
    n_primary_per_pose: int = DEFAULT_N_PRIMARY_PER_POSE,
    threads: int = DEFAULT_THREADS,
    base_seed: int = DEFAULT_BASE_SEED,
    overwrite: bool = False,
) -> dict[str, Any]:
    if output_dir.is_symlink() or (output_dir.exists() and not output_dir.is_dir()):
        raise ValueError(f"generated output path must be a directory: {output_dir}")
    if output_dir.exists() and any(output_dir.iterdir()) and not overwrite:
        raise FileExistsError(
            f"generated output directory is not empty: {output_dir}; use --overwrite to replace it"
        )
    if not campaign_id.strip():
        raise ValueError("campaign_id must be non-empty")
    if not math.isfinite(energy_keV) or energy_keV <= 0.0:
        raise ValueError("energy_keV must be finite and positive")
    if n_primary_per_pose <= 0 or threads <= 0 or base_seed < 0:
        raise ValueError("n_primary_per_pose/threads must be positive and base_seed non-negative")

    validate_reference_geometry(geometry_path)
    validate_profile_file(profile_file)
    base_config = load_yaml(base_config_path)
    geometry_file_text = repo_relative(repo_root, geometry_path)
    profile_file_text = repo_relative(repo_root, profile_file)
    energy_token = format_number_token(energy_keV)
    output_directory = (
        f"results/{campaign_id}/events/raw/grid/{REFERENCE_MODEL_ID}/{REFERENCE_PROFILE_ID}"
    )
    points = grid_points()

    staging: Path | None = None
    write_root = output_dir
    if overwrite:
        output_dir.parent.mkdir(parents=True, exist_ok=True)
        staging = Path(
            tempfile.mkdtemp(prefix=f".{output_dir.name}.staging-", dir=output_dir.parent)
        )
        write_root = staging

    manifest: dict[str, Any] = {
        "schema_version": 1,
        "experiment": "front_slab_reference_simulation_campaign",
        "campaign_id": campaign_id,
        "task_granularity": "one_pose_per_config",
        "base_config": repo_relative(repo_root, base_config_path),
        "reference": {
            "reference_type": REFERENCE_TYPE,
            "vehicle_model_id": REFERENCE_MODEL_ID,
            "vehicle_geometry_file": geometry_file_text,
            "thickness_mm": REFERENCE_THICKNESS_MM,
            "matched_phantom": "P4",
            "profile_id": REFERENCE_PROFILE_ID,
            "slit_id": REFERENCE_SLIT_ID,
        },
        "parameters": {
            "energy_keV": float(energy_keV),
            "n_primary_per_pose": n_primary_per_pose,
            "number_of_threads": threads,
            "base_seed": base_seed,
        },
        "scan_design": {
            "scan_mode": "grid",
            "x_offsets_mm": list(GRID_OFFSETS_MM),
            "y_offsets_mm": list(GRID_OFFSETS_MM),
            "pose_count": len(points),
            "includes_center": True,
        },
        "run_safety": {
            "large_run_case_threshold": 0,
            "allow_large_run_required": True,
        },
        "cases": [],
    }

    try:
        for pose_index, (x_mm, y_mm) in enumerate(points):
            seed = base_seed + pose_index
            pose_id = build_pose_id(x_mm, y_mm)
            case_id = (
                f"front_slab_reference_grid_{REFERENCE_MODEL_ID}_{REFERENCE_PROFILE_ID}_"
                f"{pose_id}_E{energy_token}_seed{seed}"
            )
            config_path = (
                output_dir
                / "configs"
                / "grid"
                / f"{REFERENCE_MODEL_ID}_{REFERENCE_PROFILE_ID}"
                / f"{pose_id}.yaml"
            )
            config = build_config(
                base_config,
                case_id=case_id,
                geometry_file=geometry_file_text,
                profile_file=profile_file_text,
                profile_id=REFERENCE_PROFILE_ID,
                head_offset_x_mm=x_mm,
                head_offset_y_mm=y_mm,
                energy_keV=energy_keV,
                n_primary_per_pose=n_primary_per_pose,
                threads=threads,
                base_seed=seed,
                output_directory=output_directory,
            )
            write_yaml(write_root / config_path.relative_to(output_dir), config)
            manifest["cases"].append(
                {
                    "case_id": case_id,
                    "condition_id": (
                        f"front_slab_reference_grid_{REFERENCE_MODEL_ID}_"
                        f"{REFERENCE_PROFILE_ID}_E{energy_token}"
                    ),
                    "config_file": repo_relative(repo_root, config_path),
                    "task_granularity": "one_pose_per_config",
                    "scan_mode": "grid",
                    "phantom_id": REFERENCE_MODEL_ID,
                    "geometry_file": geometry_file_text,
                    "profile_id": REFERENCE_PROFILE_ID,
                    "slit_ids": list(PROFILE_SETTINGS[REFERENCE_PROFILE_ID]["slit_ids"]),
                    "detector_x_range_zero_mm": list(
                        PROFILE_SETTINGS[REFERENCE_PROFILE_ID]["detector_x_range_zero_mm"]
                    ),
                    "energy_keV": float(energy_keV),
                    "pose_index": pose_index,
                    "pose_id": pose_id,
                    "head_offset_x_mm": float(x_mm),
                    "head_offset_y_mm": float(y_mm),
                    "pose_count": 1,
                    "seed": seed,
                    "seed_start": seed,
                    "seed_end": seed,
                    "n_primary_per_pose": n_primary_per_pose,
                    "number_of_threads": threads,
                    "output_directory": output_directory,
                }
            )

        manifest["summary"] = {
            "physical_condition_count": 1,
            "config_count": len(points),
            "task_count": len(points),
            "grid_config_count": len(points),
            "total_pose_runs": len(points),
            "total_primary": len(points) * n_primary_per_pose,
            "seed_start": base_seed,
            "seed_end": base_seed + len(points) - 1,
        }
        reference_manifest = {
            "schema_version": 1,
            "reference_type": REFERENCE_TYPE,
            "thickness_mm": REFERENCE_THICKNESS_MM,
            "vehicle_geometry_file": geometry_file_text,
            "vehicle_model_id": REFERENCE_MODEL_ID,
            "campaign_id": campaign_id,
            "profile_id": REFERENCE_PROFILE_ID,
            "slit_id": REFERENCE_SLIT_ID,
            "energy_keV": float(energy_keV),
            "n_primary_per_pose": n_primary_per_pose,
            "pose_count": len(points),
            "x_offsets_mm": list(GRID_OFFSETS_MM),
            "y_offsets_mm": list(GRID_OFFSETS_MM),
            "seed_start": base_seed,
            "seed_end": base_seed + len(points) - 1,
            "generated_manifest": repo_relative(repo_root, output_dir / "manifest.yaml"),
        }
        write_yaml(write_root / "manifest.yaml", manifest)
        write_yaml(write_root / REFERENCE_MANIFEST_NAME, reference_manifest)

        if staging is not None:
            backup = output_dir.parent / f".{output_dir.name}.backup"
            if backup.exists():
                raise FileExistsError(f"stale generated-output backup blocks overwrite: {backup}")
            if output_dir.exists():
                output_dir.replace(backup)
            try:
                staging.replace(output_dir)
            except Exception:
                if backup.exists():
                    backup.replace(output_dir)
                raise
            if backup.exists():
                shutil.rmtree(backup)
            staging = None
        return manifest
    except Exception:
        if staging is not None and staging.exists():
            shutil.rmtree(staging)
        raise


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    repo_root = Path(__file__).resolve().parents[2]
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", type=Path, default=repo_root)
    parser.add_argument(
        "--base-config", type=Path, default=repo_root / "config/base/article_base.yaml"
    )
    parser.add_argument(
        "--geometry",
        type=Path,
        default=repo_root / "config/geometry/article_files/P4_front_slab_55mm.yaml",
    )
    parser.add_argument(
        "--profile-file",
        type=Path,
        default=repo_root / "config/collimator/article_v2_collimator_profiles.csv",
    )
    parser.add_argument("--campaign-id", default=DEFAULT_CAMPAIGN_ID)
    parser.add_argument("--output-dir", type=Path)
    parser.add_argument("--energy-kev", type=parse_positive_float, default=DEFAULT_ENERGY_KEV)
    parser.add_argument(
        "--n-primary-per-pose",
        type=parse_positive_int,
        default=DEFAULT_N_PRIMARY_PER_POSE,
    )
    parser.add_argument("--threads", type=parse_positive_int, default=DEFAULT_THREADS)
    parser.add_argument("--base-seed", type=parse_non_negative_int, default=DEFAULT_BASE_SEED)
    parser.add_argument("--overwrite", action="store_true")
    args = parser.parse_args(argv)
    if args.output_dir is None:
        args.output_dir = args.repo_root / "config/generated" / args.campaign_id
    return args


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        manifest = generate(
            repo_root=args.repo_root.resolve(),
            base_config_path=args.base_config.resolve(),
            geometry_path=args.geometry.resolve(),
            profile_file=args.profile_file.resolve(),
            output_dir=args.output_dir.resolve(),
            campaign_id=args.campaign_id,
            energy_keV=args.energy_kev,
            n_primary_per_pose=args.n_primary_per_pose,
            threads=args.threads,
            base_seed=args.base_seed,
            overwrite=args.overwrite,
        )
    except Exception as error:
        print(f"front-slab config generation error: {error}", file=sys.stderr)
        return 2
    summary = manifest["summary"]
    print(f"Generated {summary['config_count']} front-slab configs in {args.output_dir}")
    print(f"  task_count: {summary['task_count']}")
    print(f"  total_primary: {summary['total_primary']}")
    print(f"  threads_per_task: {args.threads}")
    print(f"  seed_range: {summary['seed_start']}..{summary['seed_end']}")
    print(f"  reference_manifest: {args.output_dir / REFERENCE_MANIFEST_NAME}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
