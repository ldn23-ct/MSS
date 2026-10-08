#!/usr/bin/env python3
"""Generate the baseline ms-only F/T/B source-composition figure."""

from __future__ import annotations

import argparse
from pathlib import Path

from scripts.postprocessing.e2 import run_section_3_2 as section_3_2


FIGURE_NAME = "fig_source_composition_ms.png"


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--results-root", type=Path, default=Path("results/articlev3_merged"))
    parser.add_argument("--audit-dir", type=Path)
    parser.add_argument("--output", type=Path)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    results_root = args.results_root.resolve()
    audit_dir = (args.audit_dir or results_root / "data_processing" / "audit").resolve()
    default_output = (
        results_root
        / "postprocessing"
        / "E2"
        / "supplementary"
        / section_3_2.DEFAULT_SUBDIRECTORY
        / FIGURE_NAME
    )
    output = (args.output or default_output).resolve()
    total_figure = (
        results_root
        / "postprocessing"
        / "E2"
        / "supplementary"
        / section_3_2.DEFAULT_SUBDIRECTORY
        / section_3_2.COMPOSITION_FIGURE_NAME
    ).resolve()
    if output == total_figure:
        raise ValueError("ms-only output must not overwrite the existing total composition figure")

    condition_frames, sources = section_3_2.load_raw_condition_frames(
        results_root, audit_dir
    )
    composition = section_3_2.compute_ms_source_composition(condition_frames)
    output.parent.mkdir(parents=True, exist_ok=True)
    section_3_2.plot_source_composition(composition, output, scatter_class="ms")

    print("Source: uniformly irradiated P0, grid-zero valid events, matched slit ROI.")
    baseline_sources = {
        source["condition"]: source["valid_file"]
        for source in sources
        if source["condition_role"] == "baseline"
    }
    for condition, valid_file in baseline_sources.items():
        print(f"  {condition}: {valid_file}")

    results = composition[
        ["condition", "w_F", "w_T", "w_B", "N_F_ms", "N_T_ms", "N_B_ms", "N_ms"]
    ].rename(columns={"w_F": "F_ms", "w_T": "T_ms", "w_B": "B_ms"})
    print("ms source fractions (0–1); N columns are event counts:")
    print(
        results.to_string(
            index=False,
            formatters={name: (lambda value: f"{value:.9f}") for name in ("F_ms", "T_ms", "B_ms")},
        )
    )
    print(f"Figure: {output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
