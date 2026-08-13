#!/usr/bin/env python3
"""Run the Article V2 paper-analysis pipeline."""

from __future__ import annotations

import argparse
import shutil
import tempfile
from pathlib import Path

import pandas as pd

from analysis_pipeline import run_pipeline


VALID = ("E1", "E2", "E3", "E4", "E5A", "E6")


def parse_experiments(text: str) -> tuple[str, ...]:
    values = tuple(item.strip().upper() for item in text.split(",") if item.strip())
    if not values or len(values) != len(set(values)):
        raise ValueError("experiments must be a non-empty list without duplicates")
    unknown = sorted(set(values).difference(VALID))
    if unknown:
        raise ValueError("unknown experiment(s): " + ", ".join(unknown))
    return values


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--results-root", type=Path, required=True)
    parser.add_argument("--audit-dir", type=Path, required=True)
    parser.add_argument("--output-root", type=Path, required=True)
    parser.add_argument("--experiments", default=",".join(VALID))
    parser.add_argument("--overwrite", action="store_true")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv); experiments = parse_experiments(args.experiments)
    output = args.output_root.resolve()
    if output.exists() and not args.overwrite:
        raise FileExistsError(f"output root exists; pass --overwrite to replace it: {output}")
    output.parent.mkdir(parents=True, exist_ok=True)
    staging = Path(tempfile.mkdtemp(prefix=f".{output.name}.staging-", dir=output.parent))
    try:
        run_pipeline(args.results_root.resolve(), args.audit_dir.resolve(), staging, experiments)
        if output.exists():
            shutil.rmtree(output)
        staging.replace(output)
    except Exception:
        shutil.rmtree(staging, ignore_errors=True)
        raise
    if "E1" in experiments:
        event_counts = pd.read_csv(output / "E1/tables/E1_event_counts.csv")
        print("E1 event counts:")
        print(event_counts.to_string(index=False))
    print(f"analysis complete: {output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
