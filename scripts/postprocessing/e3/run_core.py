#!/usr/bin/env python3
"""Publish E3 M0--M5 grid results without the unavailable slab reference.

This runner is intentionally narrower than :mod:`scripts.postprocessing.e3.run`.
It requires the complete matched 9x9 main grid and produces E3-F1--F5 and
E3-T1--T3.  It never creates E3-F6/E3-T4, which require an independently
simulated 55 mm uniform-PMMA front-slab grid.
"""

from __future__ import annotations

import argparse
import math
import shutil
import sys
import tempfile
from pathlib import Path

import numpy as np
import pandas as pd

from scripts.data_processing.common import SLIT_PROFILE
from scripts.data_processing.experiment_contract import DEFECT_CENTER_Z_MM
from scripts.postprocessing.e3 import run as e3


CORE_FIGURE_NAMES = e3.FIGURE_NAMES[:5]
CORE_TABLE_NAMES = e3.TABLE_NAMES[:3]
CORE_OUTPUT_NAMES = (*CORE_FIGURE_NAMES, *CORE_TABLE_NAMES)


def validate_core_outputs(output_dir: Path) -> None:
    actual = {path.name for path in output_dir.iterdir() if path.is_file()}
    if actual != set(CORE_OUTPUT_NAMES) or any(path.is_dir() for path in output_dir.iterdir()):
        raise AssertionError(
            f"E3 core output contract mismatch: expected {sorted(CORE_OUTPUT_NAMES)}, "
            f"got {sorted(actual)}"
        )
    t1 = pd.read_csv(output_dir / CORE_TABLE_NAMES[0])
    t2 = pd.read_csv(output_dir / CORE_TABLE_NAMES[1])
    t3 = pd.read_csv(output_dir / CORE_TABLE_NAMES[2])
    if tuple(t1.columns) != e3.T1_COLUMNS or len(t1) != 6 or tuple(t1.method) != e3.METHODS:
        raise AssertionError("E3 core T1 schema or row contract failed")
    if (
        tuple(t2.columns) != e3.T2_COLUMNS
        or len(t2) != 36
        or set(t2.method) != set(e3.METHODS)
        or set(t2.phantom) != set(DEFECT_CENTER_Z_MM)
    ):
        raise AssertionError("E3 core T2 schema or row contract failed")
    if (
        tuple(t3.columns) != e3.T3_COLUMNS
        or len(t3) != 18
        or set(t3.comparison) != {item[0] for item in e3.COMPARISONS}
    ):
        raise AssertionError("E3 core T3 schema or row contract failed")
    numeric_frames = (
        t1.drop(columns="method"),
        t2.drop(columns=["phantom", "slit", "method"]),
        t3.drop(columns=["phantom", "slit", "comparison", "from_method", "to_method"]),
    )
    if not all(np.isfinite(frame.to_numpy(dtype=float)).all() for frame in numeric_frames):
        raise AssertionError("E3 core tables contain non-finite values")
    for frame in (t1, t2, t3):
        for column in frame.columns:
            if column.endswith("_n_effective") and not (frame[column] > 0).all():
                raise AssertionError(f"E3 core effective sample count is non-positive: {column}")
    for name in CORE_FIGURE_NAMES:
        if (output_dir / name).read_bytes()[:8] != b"\x89PNG\r\n\x1a\n":
            raise AssertionError(f"E3 core figure is not a PNG: {name}")


def load_conditions(results_root: Path) -> dict[str, e3.GridCondition]:
    _, inventory = e3.validate_audit(results_root)
    rows_by_condition, issues, missing = e3.inspect_inventory(inventory)
    if issues:
        raise ValueError(
            f"E3 main-grid preflight failed ({missing} missing poses): " + "; ".join(issues)
        )
    loader = e3.EventLoader()
    conditions: dict[str, e3.GridCondition] = {}
    for index in range(1, 7):
        phantom, slit = f"P{index}", f"S{index}"
        profile = SLIT_PROFILE[slit]
        e3.load_grid_condition(
            results_root, rows_by_condition[("P0", profile)], "P0", slit, loader
        )
        conditions[phantom] = e3.load_grid_condition(
            results_root, rows_by_condition[(phantom, profile)], phantom, slit, loader
        )
    return conditions


def run_core(
    conditions: dict[str, e3.GridCondition],
    output_dir: Path,
    *,
    resample_seed: int = e3.DEFAULT_RESAMPLE_SEED,
    resample_count: int = e3.RESAMPLE_COUNT,
) -> None:
    if set(conditions) != set(DEFECT_CENTER_Z_MM):
        raise ValueError("E3 core requires P1--P6 matched conditions")
    output_dir.mkdir(parents=True, exist_ok=True)
    rng = np.random.default_rng(resample_seed)
    points: dict[str, dict[str, np.ndarray]] = {}
    boots: dict[str, e3.BootstrapResult] = {}
    for phantom in DEFECT_CENTER_Z_MM:
        condition = conditions[phantom]
        point = e3.condition_point_estimates(condition)
        point["n_primary"] = condition.n_primary
        points[phantom] = point
        boots[phantom] = e3.bootstrap_condition(
            condition.base_counts, rng, resample_count=resample_count
        )
    e3.plot_f1(points["P4"]["methods"], output_dir / CORE_FIGURE_NAMES[0])
    e3.plot_f2(points, boots, output_dir / CORE_FIGURE_NAMES[1])
    e3.plot_f3(points, boots, output_dir / CORE_FIGURE_NAMES[2])
    e3.plot_f4(points, boots, output_dir / CORE_FIGURE_NAMES[3])
    e3.plot_f5(points, boots, output_dir / CORE_FIGURE_NAMES[4])
    e3.write_tables(points, boots, None, output_dir)
    validate_core_outputs(output_dir)


def publish(staging: Path, output_dir: Path, overwrite: bool) -> None:
    if output_dir.exists():
        unexpected = sorted(
            path.name for path in output_dir.iterdir() if path.name not in CORE_OUTPUT_NAMES
        )
        if unexpected:
            raise FileExistsError(f"unexpected files block E3 core publication: {unexpected}")
        if any(output_dir.iterdir()) and not overwrite:
            raise FileExistsError(f"E3 core outputs exist; pass --overwrite: {output_dir}")
        backup = output_dir.parent / f".{output_dir.name}.backup"
        if backup.exists():
            raise FileExistsError(f"stale E3 core backup blocks overwrite: {backup}")
        output_dir.replace(backup)
        try:
            staging.replace(output_dir)
        except Exception:
            backup.replace(output_dir)
            raise
        shutil.rmtree(backup)
    else:
        staging.replace(output_dir)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--results-root", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path)
    parser.add_argument("--resample-seed", type=int, default=e3.DEFAULT_RESAMPLE_SEED)
    parser.add_argument("--overwrite", action="store_true")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    results_root = args.results_root.resolve()
    output_dir = (args.output_dir or results_root / "postprocessing" / "E3").resolve()
    protected = {
        results_root,
        (results_root / "events").resolve(),
        (results_root / "events" / "raw").resolve(),
        (results_root / "events" / "valid").resolve(),
    }
    if output_dir in protected:
        raise ValueError("E3 core output directory must not replace event data or results root")
    output_dir.parent.mkdir(parents=True, exist_ok=True)
    staging = Path(tempfile.mkdtemp(prefix=f".{output_dir.name}.staging-", dir=output_dir.parent))
    try:
        conditions = load_conditions(results_root)
        if any(not math.isclose(item.n_primary, 100_000_000) for item in conditions.values()):
            raise ValueError("E3 core matched grids must all use 100M histories per pose")
        run_core(conditions, staging, resample_seed=args.resample_seed)
        publish(staging, output_dir, args.overwrite)
    except Exception:
        shutil.rmtree(staging, ignore_errors=True)
        raise
    print(f"E3 core outputs: {output_dir}")
    print("slab-dependent E3-F6/E3-T4: not generated")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as error:
        print(f"E3 core analysis error: {error}", file=sys.stderr)
        raise SystemExit(1) from error
