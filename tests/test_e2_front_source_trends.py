#!/usr/bin/env python3

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from scripts.postprocessing.e2 import run as e2
from scripts.postprocessing.e2 import run_front_source_trends as supplement
from tests.test_e2_target_scatter_composition import write_formal_fixture
from scripts.postprocessing.e3 import run as e3


def write_e3_fixture(results_root: Path) -> None:
    output = results_root / "postprocessing" / "E3"
    output.mkdir(parents=True, exist_ok=True)
    rows = []
    for _, phantom, slit, depth in supplement.CONDITIONS:
        m0_count = 1000 + int(depth)
        for index, method in enumerate(e3.METHODS):
            count = m0_count if method == "M0" else m0_count - (50 + 10 * index)
            eta = count / m0_count
            rows.append({
                "phantom": phantom, "slit": slit, "target_depth_mm": depth,
                "method": method, "total_count_N": count, "retention_eta": eta,
                "retention_ci_low": max(0.0, eta - 0.01),
                "retention_ci_high": min(1.0, eta + 0.01),
                "retention_n_effective": supplement.RESAMPLE_COUNT,
                "roi_mean": 1.0, "background_mean": 2.0, "background_std": 1.0,
                "cnr": 1.0, "cnr_ci_low": 0.5, "cnr_ci_high": 1.5,
                "cnr_n_effective": supplement.RESAMPLE_COUNT,
            })
    pd.DataFrame(rows, columns=e3.T2_COLUMNS).to_csv(
        output / "E3_T2_depth_method_metrics.csv", index=False
    )


class E2FrontSourceTrendsTests(unittest.TestCase):
    def test_direct_formal_extraction_and_e3_interval_transform(self):
        with tempfile.TemporaryDirectory() as tmp:
            results_root = Path(tmp)
            write_formal_fixture(results_root)
            write_e3_fixture(results_root)
            t2, t3, metrics = supplement.load_formal_tables(results_root)
            fractions = supplement.build_source_region_fractions(t3)
            response = supplement.build_front_response_and_dtv(t2)
            comparison = supplement.build_e2_e3_front_weight_comparison(fractions, metrics)
            self.assertEqual(108, len(fractions))
            self.assertEqual(18, len(response))
            self.assertEqual(6, len(comparison))
            formal_front = t2["P1-S1"].query("scatter_class == 'k1' and region == 'Front'").iloc[0]
            extracted = response.query("condition == 'P1-S1' and scatter_class == 'k1'").iloc[0]
            self.assertEqual(int(formal_front.N_r0), int(extracted.N_F0))
            self.assertEqual(int(formal_front.N_rD), int(extracted.N_FD))
            self.assertEqual(float(formal_front.D_TV_r), float(extracted.D_TV_F))
            self.assertTrue((response.groupby("condition").apply(
                lambda group: int(group.set_index("scatter_class").loc["total", "N_F0"])
                == int(group.set_index("scatter_class").loc["k1", "N_F0"])
                + int(group.set_index("scatter_class").loc["ms", "N_F0"])
            )).all())
            self.assertTrue(np.allclose(comparison.M5_count / comparison.M0_count, comparison.eta_M5))
            self.assertTrue(np.allclose(comparison.one_minus_eta_M5, 1.0 - comparison.eta_M5))
            self.assertTrue(np.allclose(comparison.one_minus_eta_M5_ci_low, 1.0 - comparison.eta_M5_ci_high))
            self.assertTrue(np.allclose(comparison.one_minus_eta_M5_ci_high, 1.0 - comparison.eta_M5_ci_low))

    def test_figures_have_two_panels_and_six_depth_points(self):
        with tempfile.TemporaryDirectory() as tmp:
            results_root = Path(tmp)
            write_formal_fixture(results_root)
            write_e3_fixture(results_root)
            t2, t3, _ = supplement.load_formal_tables(results_root)
            fractions = supplement.build_source_region_fractions(t3)
            response = supplement.build_front_response_and_dtv(t2)
            captured = {}
            def capture(figure, path):
                captured[path.name] = figure
            with patch.object(supplement.e2, "_save_png", side_effect=capture):
                supplement.plot_source_fraction_trends(fractions, Path("/tmp/source.png"))
                supplement.plot_front_response_and_dtv(response, Path("/tmp/response.png"))
            depths = np.array([15, 30, 45, 60, 75, 90], dtype=float)
            for figure in captured.values():
                self.assertEqual(2, len(figure.axes))
                for axis in figure.axes:
                    self.assertTrue(any(np.array_equal(line.get_xdata(), depths) for line in axis.lines))
                plt.close(figure)

    def test_atomic_output_contract_and_dtv_point_may_lie_outside_interval(self):
        with tempfile.TemporaryDirectory() as tmp:
            results_root = Path(tmp)
            write_formal_fixture(results_root)
            write_e3_fixture(results_root)
            output = results_root / "out"
            fractions, response, comparison = supplement.run_analysis(results_root, output)
            self.assertEqual(set(supplement.OUTPUT_NAMES), {path.name for path in output.iterdir()})
            self.assertEqual(supplement.ST4_COLUMNS, tuple(fractions.columns))
            self.assertEqual(supplement.ST5_COLUMNS, tuple(response.columns))
            self.assertEqual(supplement.ST6_COLUMNS, tuple(comparison.columns))
            altered = response.copy()
            altered.loc[0, ["D_TV_F", "D_TV_F_ci_low", "D_TV_F_ci_high"]] = (0.9, 0.1, 0.2)
            with patch.object(supplement.e2, "_save_png"):
                supplement.plot_front_response_and_dtv(altered, Path("/tmp/point-outside-ci.png"))


if __name__ == "__main__":
    unittest.main()
