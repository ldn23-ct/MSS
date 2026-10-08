#!/usr/bin/env python3

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import yaml

from scripts.postprocessing.e2 import run as e2
from scripts.postprocessing.e2 import run_target_scatter_composition as supplement


def write_formal_fixture(results_root: Path) -> Path:
    e2_root = results_root / "postprocessing" / "E2"
    tables = e2_root / "tables"
    tables.mkdir(parents=True)
    (e2_root / "acceptance_summary.yaml").write_text(
        yaml.safe_dump({"overall_status": "pass", "checks": {"fixture": {"pass": True}}}),
        encoding="utf-8",
    )
    (e2_root / "analysis_manifest.yaml").write_text(
        yaml.safe_dump({
            "experiment": "E2",
            "publication_status": "complete",
            "parameters": {
                "input_layer": "events/valid",
                "summary_source": "grid-zero",
                "poisson_resampling": {
                    "draw_count": supplement.RESAMPLE_COUNT,
                    "seed": supplement.RESAMPLE_SEED,
                },
            },
        }),
        encoding="utf-8",
    )

    t1_rows = []
    t3_rows = []
    for index, (condition, phantom, slit, depth) in enumerate(supplement.CONDITIONS, 1):
        baseline_regions = {
            "k1": {"Front": 10, "Target": 12 - index, "Behind": 4},
            "ms": {"Front": 5, "Target": 7 - index, "Behind": 3},
        }
        defect_regions = {
            "k1": {"Front": 9, "Target": 1, "Behind": 5},
            "ms": {"Front": 4, "Target": 0, "Behind": 4},
        }
        for regions in (baseline_regions, defect_regions):
            regions["total"] = {
                region: regions["k1"][region] + regions["ms"][region]
                for region in e2.REGIONS
            }

        t2_rows = []
        for scatter_class in e2.CLASSES:
            n0_total = sum(baseline_regions[scatter_class].values())
            nd_total = sum(defect_regions[scatter_class].values())
            t1_rows.append({
                "defect_phantom": phantom,
                "slit": slit,
                "depth_mm": depth,
                "scatter_class": scatter_class,
                "N0": n0_total,
                "ND": nd_total,
                "C": (nd_total - n0_total) / n0_total,
                "C_ci_low": -0.9,
                "C_ci_high": 0.1,
                "C_n_effective": supplement.RESAMPLE_COUNT,
            })
            for region in e2.REGIONS:
                n0 = baseline_regions[scatter_class][region]
                nd = defect_regions[scatter_class][region]
                c_value = (nd - n0) / n0
                t2_rows.append({
                    "baseline_phantom": "P0",
                    "defect_phantom": phantom,
                    "slit": slit,
                    "target_depth_mm": depth,
                    "scatter_class": scatter_class,
                    "region": region,
                    "N_r0": n0,
                    "N_rD": nd,
                    "C_r": c_value,
                    "C_r_ci_low": max(-1.0, c_value - 0.1),
                    "C_r_ci_high": min(1.0, c_value + 0.1),
                    "C_r_n_effective": supplement.RESAMPLE_COUNT,
                    "D_TV_r": np.nan if nd == 0 else 0.0,
                    "D_TV_r_ci_low": np.nan if nd == 0 else 0.0,
                    "D_TV_r_ci_high": np.nan if nd == 0 else 0.0,
                    "D_TV_r_n_effective": 0 if nd == 0 else supplement.RESAMPLE_COUNT,
                })
                for role, phantom_id, counts, total in (
                    ("baseline", "P0", baseline_regions[scatter_class], n0_total),
                    ("defect", phantom, defect_regions[scatter_class], nd_total),
                ):
                    count = counts[region]
                    fraction = count / total
                    t3_rows.append({
                        "defect_phantom": phantom,
                        "slit": slit,
                        "target_depth_mm": depth,
                        "condition_role": role,
                        "condition_phantom": phantom_id,
                        "scatter_class": scatter_class,
                        "region": region,
                        "N_region": count,
                        "N_total": total,
                        "fraction": fraction,
                        "fraction_ci_low": max(0.0, fraction - 0.01),
                        "fraction_ci_high": min(1.0, fraction + 0.01),
                        "fraction_n_effective": supplement.RESAMPLE_COUNT,
                    })
        pd.DataFrame(t2_rows, columns=e2.T2_COLUMNS).to_csv(
            tables / f"E2-T2_P0-{slit}_vs_{phantom}-{slit}_source_region_quantitative.csv",
            index=False,
        )
    pd.DataFrame(t1_rows, columns=e2.T1_COLUMNS).to_csv(
        tables / e2.ZERO_POSE_T1_TABLE_NAME, index=False
    )
    pd.DataFrame(t3_rows, columns=e2.T3_COLUMNS).to_csv(
        tables / e2.ZERO_POSE_T3_TABLE_NAME, index=False
    )
    return e2_root


class E2TargetScatterCompositionTests(unittest.TestCase):
    def test_formal_extraction_and_fixed_seed_composition(self):
        with tempfile.TemporaryDirectory() as tmp:
            results_root = Path(tmp)
            e2_root = write_formal_fixture(results_root)
            t2_tables, t3, _ = supplement.load_formal_tables(e2_root)
            response = supplement.build_target_response_table(t2_tables)
            first = supplement.build_target_composition_table(
                response, resample_count=120
            )
            second = supplement.build_target_composition_table(
                response, resample_count=120
            )
            fractions = supplement.build_target_fraction_table(t3)

            pd.testing.assert_frame_equal(first, second)
            self.assertEqual(supplement.ST1_COLUMNS, tuple(response.columns))
            self.assertEqual(supplement.ST2_COLUMNS, tuple(first.columns))
            self.assertEqual(supplement.ST3_COLUMNS, tuple(fractions.columns))
            self.assertTrue((response.N_T0_total == response.N_T0_k1 + response.N_T0_ms).all())
            self.assertTrue((response.N_TD_total == response.N_TD_k1 + response.N_TD_ms).all())
            self.assertTrue(np.allclose(first.q_k1_given_T + first.q_ms_given_T, 1.0))
            self.assertTrue(first.q_k1_given_T_n_effective.eq(120).all())
            self.assertEqual(11, int(response.iloc[0].N_T0_k1))
            self.assertAlmostEqual(11 / 17, first.iloc[0].q_k1_given_T)
            self.assertAlmostEqual(11 / 25, fractions.iloc[0].f_T0_k1)

    def test_zero_target_denominator_stays_undefined(self):
        result = supplement.poisson_target_composition(
            0, 0, np.random.default_rng(4), resample_count=30
        )
        self.assertTrue(np.isnan(result["q_k1_given_T"]))
        self.assertTrue(np.isnan(result["q_ms_given_T_ci_low"]))
        self.assertEqual(0, result["q_k1_given_T_n_effective"])
        self.assertEqual(0, result["q_ms_given_T_n_effective"])

    def test_trend_figure_has_two_panels_and_six_unmodified_depths(self):
        depths = np.array([15, 30, 45, 60, 75, 90], dtype=float)
        composition = pd.DataFrame({
            "depth_mm": depths,
            "q_k1_given_T": np.linspace(0.8, 0.55, 6),
            "q_k1_given_T_ci_low": np.linspace(0.78, 0.53, 6),
            "q_k1_given_T_ci_high": np.linspace(0.82, 0.57, 6),
            "q_ms_given_T": np.linspace(0.2, 0.45, 6),
            "q_ms_given_T_ci_low": np.linspace(0.18, 0.43, 6),
            "q_ms_given_T_ci_high": np.linspace(0.22, 0.47, 6),
        })
        fractions = pd.DataFrame({"depth_mm": depths})
        for scatter_class, values in (
            ("total", np.linspace(0.6, 0.1, 6)),
            ("k1", np.linspace(0.8, 0.5, 6)),
            ("ms", np.linspace(0.3, 0.05, 6)),
        ):
            fractions[f"f_T0_{scatter_class}"] = values
            fractions[f"f_T0_{scatter_class}_ci_low"] = values - 0.01
            fractions[f"f_T0_{scatter_class}_ci_high"] = values + 0.01
        captured = {}

        def capture(figure, path):
            captured[path.name] = figure

        with patch.object(supplement.e2, "_save_png", side_effect=capture):
            supplement.plot_trends(composition, fractions, Path("/tmp/candidate.png"))
        figure = captured["candidate.png"]
        self.assertEqual(2, len(figure.axes))
        for axis, expected_line_count in zip(figure.axes, (2, 3), strict=True):
            six_point_lines = [
                line for line in axis.lines
                if len(line.get_xdata()) == 6 and line.get_marker() in {"o", "s", "^"}
            ]
            self.assertEqual(expected_line_count, len(six_point_lines))
            for line in six_point_lines:
                np.testing.assert_array_equal(depths, line.get_xdata())
        plt.close(figure)

    def test_full_supplementary_output_contract(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            e2_root = write_formal_fixture(root)
            t2_tables, t3, _ = supplement.load_formal_tables(e2_root)
            response = supplement.build_target_response_table(t2_tables)
            composition = supplement.build_target_composition_table(
                response, resample_count=80
            )
            fractions = supplement.build_target_fraction_table(t3)
            output = root / "output"
            supplement.write_outputs(
                response, composition, fractions, output, resample_count=80
            )
            self.assertEqual(
                set(supplement.OUTPUT_NAMES),
                {path.name for path in output.iterdir()},
            )


if __name__ == "__main__":
    unittest.main()
