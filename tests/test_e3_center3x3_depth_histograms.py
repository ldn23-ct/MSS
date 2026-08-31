#!/usr/bin/env python3

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

import numpy as np
import pandas as pd
from PIL import Image

from scripts.data_processing.experiment_contract import GRID_OFFSETS_MM
from scripts.postprocessing.e3 import run as e3
from scripts.postprocessing.e3 import run_center3x3_depth_histograms as depth


def synthetic_inputs() -> depth.AnalysisInputs:
    images = np.zeros((110, 9, 9), dtype=np.int64)
    images[0, e3.DEFECT_MASK] = 10
    images[0, e3.BACKGROUND_MASK] = 12
    return depth.AnalysisInputs(
        p4_total_depths=np.asarray([1.0, 3.0, 54.999, 55.0, 219.5]),
        truth_front_depths=np.asarray([1.0, 3.0, 54.999]),
        slab_depths=np.asarray([1.0, 3.0, 54.999, 55.0, 101.0]),
        truth_front_images=images,
        p4_pooled_n_primary=900,
        slab_pooled_n_primary=450,
        p4_out_of_domain_count=0,
        slab_out_of_domain_count=0,
    )


class Center3x3DepthHistogramTests(unittest.TestCase):
    def test_center_selection_is_exactly_nine_unique_poses(self):
        rows = pd.DataFrame(
            [
                {"head_offset_x_mm": x, "head_offset_y_mm": y}
                for x in GRID_OFFSETS_MM
                for y in GRID_OFFSETS_MM
            ]
        )
        selected = depth.select_center_rows(rows, "fixture")
        self.assertEqual(9, len(selected))
        self.assertEqual(
            depth.CENTER_POINTS,
            {
                (float(row.head_offset_x_mm), float(row.head_offset_y_mm))
                for row in selected.itertuples(index=False)
            },
        )
        missing = rows[
            ~(rows.head_offset_x_mm.eq(-2.5) & rows.head_offset_y_mm.eq(-2.5))
        ]
        with self.assertRaisesRegex(ValueError, "nine unique poses"):
            depth.select_center_rows(missing, "missing fixture")

    def test_truth_boundary_shared_bins_alpha_and_residual(self):
        inputs = synthetic_inputs()
        alpha = inputs.p4_pooled_n_primary / inputs.slab_pooled_n_primary
        table = depth.build_depth_table(
            inputs.p4_total_depths,
            inputs.truth_front_depths,
            inputs.slab_depths,
            alpha,
        )
        self.assertEqual(110, len(table))
        bin_54_56 = table[table.bin_left_mm.eq(54.0)].iloc[0]
        self.assertEqual(1, int(bin_54_56.truth_front_count))
        self.assertEqual(4.0, float(bin_54_56.slab_front_count))
        self.assertEqual(-3.0, float(bin_54_56.residual_count))
        self.assertTrue(
            np.allclose(
                table.residual_count,
                table.truth_front_count - table.slab_front_count,
            )
        )
        with self.assertRaisesRegex(ValueError, "z < 55"):
            depth.build_depth_table(
                inputs.p4_total_depths,
                np.asarray([55.0]),
                inputs.slab_depths,
                alpha,
            )

    def test_roi_means_use_frozen_25_and_32_pose_masks(self):
        roi = depth.roi_depth_statistics(synthetic_inputs().truth_front_images)
        self.assertEqual(10.0, float(roi.iloc[0].defect_roi_mean))
        self.assertEqual(12.0, float(roi.iloc[0].background_mean))
        self.assertEqual(2.0, float(roi.iloc[0].delta_background_minus_roi))
        self.assertEqual(0.0, float(roi.iloc[1].delta_background_minus_roi))

    def test_summary_uses_actual_histories_and_exact_front_boundary(self):
        inputs = synthetic_inputs()
        alpha = inputs.p4_pooled_n_primary / inputs.slab_pooled_n_primary
        summary = depth.build_summary(inputs, alpha).iloc[0]
        self.assertEqual(2.0, float(summary.alpha))
        self.assertEqual(3, int(summary.truth_front_total_count))
        self.assertEqual(10.0, float(summary.slab_front_total_count))
        self.assertAlmostEqual(10.0 / 3.0, float(summary.slab_to_truth_ratio))
        self.assertAlmostEqual(3.0 / 5.0, float(summary.slab_fraction_z_lt55))

        # The slab event at 55.0 mm must not affect the z<55 Pearson comparison.
        with_boundary = depth.pearson_front_histograms(
            inputs.truth_front_depths, inputs.slab_depths
        )
        without_boundary = depth.pearson_front_histograms(
            inputs.truth_front_depths,
            inputs.slab_depths[inputs.slab_depths < 55.0],
        )
        self.assertAlmostEqual(with_boundary, without_boundary)

    def test_outputs_replace_legacy_contract_and_are_300dpi(self):
        inputs = synthetic_inputs()
        alpha = inputs.p4_pooled_n_primary / inputs.slab_pooled_n_primary
        table = depth.build_depth_table(
            inputs.p4_total_depths,
            inputs.truth_front_depths,
            inputs.slab_depths,
            alpha,
        )
        roi = depth.roi_depth_statistics(inputs.truth_front_images)
        summary = depth.build_summary(inputs, alpha)
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            output = root / "center3x3"
            staging = root / "staging"
            output.mkdir()
            (output / "E3_SF1_center3x3_all_four_first_scatter_depth.png").write_text(
                "legacy", encoding="utf-8"
            )
            depth.write_outputs(table, roi, summary, staging)
            depth.publish(staging, output, overwrite=True)
            self.assertEqual(
                set(depth.OUTPUT_NAMES), {path.name for path in output.iterdir()}
            )
            saved = pd.read_csv(output / depth.TABLE_NAME)
            self.assertEqual(1, len(saved))
            self.assertEqual(tuple(saved.columns), depth.SUMMARY_COLUMNS)
            for name in depth.FIGURE_NAMES:
                with Image.open(output / name) as image:
                    dpi = image.info.get("dpi")
                    self.assertEqual("PNG", image.format)
                    self.assertIsNotNone(dpi)
                    self.assertGreater(dpi[0], 299.0)
                    self.assertGreater(dpi[1], 299.0)


if __name__ == "__main__":
    unittest.main()
