#!/usr/bin/env python3
"""Generate the five supplemental slab campaigns (5 workers x 7 threads)."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Any

from . import generate_front_slab_reference_configs as slab


SLAB_SPECS = (("P1", 10), ("P2", 25), ("P3", 40), ("P5", 70), ("P6", 85))
BASE_SEED = 12_000
THREADS = 7
N_PRIMARY_PER_POSE = 100_000_000
ENERGY_KEV = 560.0


def campaign_id(phantom_id: str, thickness_mm: int) -> str:
    return f"articlev3_{phantom_id.lower()}_front_slab_{thickness_mm}mm_100m"


def generate_campaigns(
    repo_root: Path,
    output_root: Path | None = None,
    *,
    overwrite: bool = False,
) -> list[dict[str, Any]]:
    repo_root = repo_root.resolve()
    output_root = (output_root or repo_root / "config/generated").resolve()
    base_config = repo_root / "config/base/front_slab_grid_base.yaml"
    profile_file = repo_root / "config/collimator/article_v2_collimator_profiles.csv"
    geometry_dir = repo_root / "config/geometry/article_files"
    slab.load_yaml(base_config)
    slab.validate_profile_file(profile_file)

    # Check every input and destination before writing any of the five campaigns.
    jobs = []
    for phantom_id, thickness in SLAB_SPECS:
        identifier = campaign_id(phantom_id, thickness)
        geometry = geometry_dir / f"{phantom_id}_front_slab_{thickness}mm.yaml"
        output = output_root / identifier
        slab.validate_reference_geometry(geometry)
        if output.is_symlink() or (output.exists() and not output.is_dir()):
            raise ValueError(f"generated output path must be a directory: {output}")
        if output.exists() and any(output.iterdir()) and not overwrite:
            raise FileExistsError(
                f"generated output directory is not empty: {output}; "
                "reuse the existing manifests, or use --overwrite to replace configs"
            )
        if overwrite and (output.parent / f".{output.name}.backup").exists():
            raise FileExistsError(f"stale generated-output backup blocks overwrite: {output}")
        jobs.append((identifier, geometry, output))

    manifests = []
    pose_count = len(slab.grid_points())
    for index, (identifier, geometry, output) in enumerate(jobs):
        manifests.append(
            slab.generate(
                repo_root=repo_root,
                base_config_path=base_config,
                geometry_path=geometry,
                profile_file=profile_file,
                output_dir=output,
                campaign_id=identifier,
                energy_keV=ENERGY_KEV,
                n_primary_per_pose=N_PRIMARY_PER_POSE,
                threads=THREADS,
                base_seed=BASE_SEED + index * pose_count,
                overwrite=overwrite,
            )
        )
    return manifests


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", type=Path, default=Path(__file__).resolve().parents[2])
    parser.add_argument("--output-root", type=Path, help="default: <repo-root>/config/generated")
    parser.add_argument("--overwrite", action="store_true", help="explicitly replace generated configs only")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        manifests = generate_campaigns(args.repo_root, args.output_root, overwrite=args.overwrite)
    except Exception as error:
        print(f"front-slab batch generation error: {error}", file=sys.stderr)
        return 2
    output_root = args.output_root or args.repo_root / "config/generated"
    for manifest in manifests:
        summary = manifest["summary"]
        reference = manifest["reference"]
        print(
            f"{manifest['campaign_id']}: {summary['task_count']} tasks, "
            f"{reference['profile_id']}/{reference['slit_id']}, "
            f"seeds {summary['seed_start']}..{summary['seed_end']}, {THREADS} threads"
        )
        print(f"  manifest: {output_root / manifest['campaign_id'] / 'manifest.yaml'}")
    print(f"Total: {sum(item['summary']['task_count'] for item in manifests)} tasks, "
          f"{sum(item['summary']['total_primary'] for item in manifests)} primary")
    print("Configs are ready. Build MSS separately, then dry-run and start one queue per slab.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
