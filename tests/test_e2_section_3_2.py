#!/usr/bin/env python3

from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

os.environ.setdefault("MPLCONFIGDIR", "/tmp/mss_matplotlib")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from scripts.postprocessing.e2 import run as e2
from scripts.postprocessing.e2 import run_section_3_2 as section


def synthetic_frames() -> dict[str, dict[str, pd.DataFrame]]:
    output: dict[str, dict[str, pd.DataFrame]] = {}
    for condition, _, _, depth in section.CONDITIONS:
        baseline_rows: list[dict[str, float | int]] = []
        defect_rows: list[dict[str, float | int]] = []
        for scatter_count, target_count in ((1, 10), (2, 6)):
            front = [2.0, max(3.0, depth - 7.0)]
            behind = [depth + 6.0, depth + 12.0]
            target = np.linspace(depth - 4.0, depth + 4.0, target_count).tolist()
            baseline_rows.extend(
                {"scatter_count_total": scatter_count, "first_scatter_z": value}
                for value in (*front, *target, *behind)
            )
            defect_rows.extend(
                {"scatter_count_total": scatter_count, "first_scatter_z": value}
                for value in (*front, depth, *behind)
            )
        output[condition] = {
            "baseline": pd.DataFrame(baseline_rows),
            "defect": pd.DataFrame(defect_rows),
        }
    return output


def formal_from_frames(
    frames: dict[str, dict[str, pd.DataFrame]],
) -> pd.DataFrame:
    rows = []
    for condition_index, (condition, phantom, slit, depth) in enumerate(section.CONDITIONS):
        for scatter_class in e2.CLASSES:
            n0 = int(e2.class_mask(frames[condition]["baseline"], scatter_class).sum())
            nd = int(e2.class_mask(frames[condition]["defect"], scatter_class).sum())
            value = (nd - n0) / n0
            section.TABLE5_PERCENT[scatter_class] = tuple(
                round(
                    100.0
                    * (
                        int(e2.class_mask(frames[name]["defect"], scatter_class).sum())
                        - int(e2.class_mask(frames[name]["baseline"], scatter_class).sum())
                    )
                    / int(e2.class_mask(frames[name]["baseline"], scatter_class).sum()),
                    1,
                )
                for name, *_ in section.CONDITIONS
            )
            rows.append(
                {
                    "defect_phantom": phantom,
                    "slit": slit,
                    "depth_mm": depth,
                    "scatter_class": scatter_class,
                    "N0": n0,
                    "ND": nd,
                    "C": value,
                    "C_ci_low": value - 0.01,
                    "C_ci_high": value + 0.01,
                    "C_n_effective": 10,
                }
            )
    return pd.DataFrame(rows, columns=e2.T1_COLUMNS)


class Section32Tests(unittest.TestCase):
    def setUp(self) -> None:
        self.original_table5 = {key: tuple(value) for key, value in section.TABLE5_PERCENT.items()}

    def tearDown(self) -> None:
        section.TABLE5_PERCENT.clear()
        section.TABLE5_PERCENT.update(self.original_table5)

    def test_raw_count_tables_and_all_identities(self):
        frames = synthetic_frames()
        tables = section.compute_tables(frames, formal_from_frames(frames))
        acceptance = section.validate_tables(tables)
        self.assertEqual("pass", acceptance["overall_status"])
        self.assertEqual(18, len(tables["table6"]))
        self.assertEqual(18, len(tables["dtv"]))
        self.assertEqual(6, len(tables["composition"]))
        self.assertNotIn("Gamma_T_over_C", tables["table6"].columns)
        validation = tables["validation"]
        self.assertTrue(validation.C_table5_rounding_match.all())
        self.assertTrue(validation.abs_Gamma_T_gt_abs_Gamma_nonT.all())
        self.assertTrue(np.allclose(validation.w_sum, 1.0, rtol=0.0, atol=1e-12))
        self.assertTrue(np.allclose(
            tables["table6"].C,
            tables["table6"].Gamma_T + tables["table6"].Gamma_nonT,
            rtol=0.0,
            atol=1e-12,
        ))

    def test_nonT_dtv_is_jointly_normalized_without_cross_gap_smoothing(self):
        front_0 = np.array([8, 2], dtype=int)
        front_d = np.array([5, 5], dtype=int)
        behind_0 = np.array([4, 16], dtype=int)
        behind_d = np.array([16, 4], dtype=int)
        combined_0 = np.concatenate((front_0, behind_0))
        combined_d = np.concatenate((front_d, behind_d))
        expected = 0.5 * np.abs(
            combined_d / combined_d.sum() - combined_0 / combined_0.sum()
        ).sum()
        self.assertAlmostEqual(expected, section._dtv(combined_0, combined_d))
        self.assertNotAlmostEqual(
            expected,
            0.5 * (section._dtv(front_0, front_d) + section._dtv(behind_0, behind_d)),
        )
        self.assertTrue(np.isnan(section._dtv(np.zeros(2), np.ones(2))))

    def test_boundary_membership_and_binwise_class_closure(self):
        target = (25.0, 35.0)
        values = np.array([24.999, 25.0, 34.999, 35.0])
        self.assertEqual([True, False, False, False], e2.region_mask(values, "Front", target).tolist())
        self.assertEqual([False, True, True, False], e2.region_mask(values, "Target", target).tolist())
        self.assertEqual([False, False, False, True], e2.region_mask(values, "Behind", target).tolist())
        frames = synthetic_frames()
        tables = section.compute_tables(frames, formal_from_frames(frames))
        data = tables["fig5"]
        for condition, *_ in section.CONDITIONS:
            for role in ("baseline", "defect"):
                selected = data[data.condition.eq(condition) & data.condition_role.eq(role)]
                total = selected[selected.scatter_class.eq("total")].sort_values("bin_left_mm")["count"].to_numpy()
                k1 = selected[selected.scatter_class.eq("k1")].sort_values("bin_left_mm")["count"].to_numpy()
                ms = selected[selected.scatter_class.eq("ms")].sort_values("bin_left_mm")["count"].to_numpy()
                np.testing.assert_array_equal(total, k1 + ms)

    def test_figure_layouts(self):
        frames = synthetic_frames()
        tables = section.compute_tables(frames, formal_from_frames(frames))
        captured = {}

        def capture(figure, path):
            captured[path.name] = figure

        with patch.object(section.e2, "_save_png", side_effect=capture):
            section.plot_fig5(tables["fig5"], "total", Path("/tmp/fig5.png"))
            section.plot_source_composition(tables["composition"], Path("/tmp/composition.png"))
        fig5 = captured["fig5.png"]
        composition = captured["composition.png"]
        self.assertEqual(6, len(fig5.axes))
        self.assertTrue(all(len(axis.patches) >= 3 for axis in fig5.axes))
        self.assertEqual(1, len(composition.axes))
        self.assertEqual(18, len(composition.axes[0].patches))
        plt.close(fig5)
        plt.close(composition)

    def test_output_contract_and_independent_summary(self):
        frames = synthetic_frames()
        tables = section.compute_tables(frames, formal_from_frames(frames))
        tables["dtv"].loc[0, "D_TV_F"] = np.nan
        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp) / "section_3_2"
            acceptance, summary = section.write_artifacts(
                output,
                tables,
                [],
                Path(tmp) / "results",
                Path(tmp) / "audit",
            )
            self.assertEqual("pass", acceptance["overall_status"])
            self.assertEqual(set(section.OUTPUT_NAMES), {path.name for path in output.iterdir()})
            self.assertIn("NA", (output / section.DTV_NAME).read_text(encoding="utf-8"))
            self.assertIn("18/18", summary)
            self.assertIn("D_TV,nonT", summary)
            self.assertIn("不构造贡献率列", summary)

    def test_atomic_publish_is_scoped_to_the_independent_directory(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            supplementary = root / "results" / "postprocessing" / "E2" / "supplementary"
            output = supplementary / "section_3_2"
            sibling = supplementary / "legacy_analysis"
            staging = supplementary / ".section_3_2.staging-test"
            output.mkdir(parents=True)
            sibling.mkdir()
            staging.mkdir()
            (output / "old.txt").write_text("old", encoding="utf-8")
            (sibling / "keep.txt").write_text("keep", encoding="utf-8")
            (staging / "new.txt").write_text("new", encoding="utf-8")

            section.publish(staging, output, overwrite=True)

            self.assertEqual({"new.txt"}, {path.name for path in output.iterdir()})
            self.assertEqual("keep", (sibling / "keep.txt").read_text(encoding="utf-8"))
            self.assertFalse((supplementary / ".section_3_2.backup").exists())

    def test_output_location_cannot_target_raw_or_formal_results(self):
        with tempfile.TemporaryDirectory() as tmp:
            results = Path(tmp) / "results"
            accepted = results / "postprocessing" / "E2" / "supplementary" / "section_3_2"
            section.validate_output_location(results, accepted)
            for unsafe in (
                results,
                results / "events" / "valid" / "section_3_2",
                results / "postprocessing" / "E2" / "tables" / "section_3_2",
                results / "postprocessing" / "E2" / "supplementary",
            ):
                with self.subTest(unsafe=unsafe):
                    with self.assertRaises(ValueError):
                        section.validate_output_location(results, unsafe)


if __name__ == "__main__":
    unittest.main()
