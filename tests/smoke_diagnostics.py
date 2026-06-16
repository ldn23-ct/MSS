#!/usr/bin/env python3

from __future__ import annotations

import argparse
import subprocess
import tempfile
from pathlib import Path

import yaml


FORMAL_HEADER = (
    "event_id,hit_id,track_id,parent_id,is_primary_gamma,gamma_source_type,gamma_source_process,"
    "gamma_source_x,gamma_source_y,gamma_source_z,gamma_source_region_id,det_x,det_y,det_z,"
    "det_energy,scatter_count_total,compton_count,rayleigh_count,first_scatter_x,first_scatter_y,"
    "first_scatter_z,last_scatter_x,last_scatter_y,last_scatter_z,first_scatter_region_id,"
    "last_scatter_region_id"
)

PHASE_HEADER = (
    "event_id,hit_id,track_id,parent_id,is_primary_gamma,particle,phase_x_mm,phase_y_mm,"
    "phase_z_mm,dir_x,dir_y,dir_z,kinetic_energy_keV,weight"
)


def run_config(
    binary: Path,
    repo_root: Path,
    source_config: Path,
    root: Path,
    case_id: str,
    number_of_threads: int = 1,
    n_primary: int = 1,
) -> None:
    config = yaml.safe_load(source_config.read_text(encoding="utf-8"))
    config["run"]["number_of_threads"] = number_of_threads
    config["run"]["n_primary_per_pose"] = n_primary
    config["output"]["output_directory"] = str(root / "results" / case_id)
    temp_config = root / f"{case_id}.yaml"
    temp_config.write_text(yaml.safe_dump(config, sort_keys=False), encoding="utf-8")

    completed = subprocess.run(
        [str(binary), "--config", str(temp_config)],
        cwd=repo_root,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        timeout=90,
        check=False,
    )
    if completed.returncode != 0:
        raise AssertionError(f"{case_id} failed:\n{completed.stdout[-8000:]}")

    run_dirs = list((root / "results" / case_id).glob("pose_*"))
    if len(run_dirs) != 1:
        raise AssertionError(f"{case_id} generated {len(run_dirs)} run directories")
    run_dir = run_dirs[0]
    events_path = run_dir / "events.csv"
    metadata_path = run_dir / "metadata.yaml"
    if not events_path.exists() or not metadata_path.exists():
        raise AssertionError(f"{case_id} is missing formal output files")
    if events_path.read_text(encoding="utf-8").splitlines()[0] != FORMAL_HEADER:
        raise AssertionError(f"{case_id} changed the formal events.csv header")

    phase_enabled = bool(config.get("diagnostics", {}).get("phase_space", {}).get("enable"))
    phase_path = run_dir / "phase_space.csv"
    if phase_enabled:
        if not phase_path.exists():
            raise AssertionError(f"{case_id} did not generate phase_space.csv")
        if phase_path.read_text(encoding="utf-8").splitlines()[0] != PHASE_HEADER:
            raise AssertionError(f"{case_id} generated an invalid phase-space header")
    elif phase_path.exists():
        raise AssertionError(f"{case_id} unexpectedly generated phase_space.csv")

    metadata = yaml.safe_load(metadata_path.read_text(encoding="utf-8"))
    if metadata["config_file"] != str(temp_config):
        raise AssertionError(f"{case_id} metadata did not record config_file")
    if phase_enabled != metadata["diagnostics"]["phase_space"]["enable"]:
        raise AssertionError(f"{case_id} metadata phase-space state mismatch")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--binary", type=Path, required=True)
    parser.add_argument("--repo-root", type=Path, required=True)
    args = parser.parse_args()

    manifest_path = args.repo_root / "config/generated/diagnostics/manifest.yaml"
    manifest = yaml.safe_load(manifest_path.read_text(encoding="utf-8"))
    cases = [
        (case["case_id"], args.repo_root / case["config_file"])
        for case in manifest["cases"]
    ]
    cases.append(("legacy_v2", args.repo_root / "config/base/simulation_config_v2.yaml"))
    cases.append(
        (
            "vehicle_open_mt",
            args.repo_root / "config/generated/diagnostics/configs/vehicle_open.yaml",
        )
    )

    with tempfile.TemporaryDirectory(prefix="mss_diagnostics_smoke_") as tmp:
        root = Path(tmp)
        for case_id, config_path in cases:
            if case_id == "vehicle_open_mt":
                run_config(
                    args.binary.resolve(),
                    args.repo_root.resolve(),
                    config_path,
                    root,
                    case_id,
                    number_of_threads=2,
                    n_primary=2,
                )
            else:
                run_config(args.binary.resolve(), args.repo_root.resolve(), config_path, root, case_id)
    print(f"Completed {len(cases)} one-primary diagnostic smoke runs")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
