#!/usr/bin/env python3

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

import numpy as np
import pandas as pd
from PIL import Image

from scripts.postprocessing.e3 import run_real_data_validation as real


def synthetic_volumes(y_size: int = 4, x_size: int = 3) -> tuple[np.ndarray, np.ndarray]:
    z, y, x = np.indices((real.EXPECTED_Z_SLICES, y_size, x_size))
    defect = 20.0 + z + 2.0 * y + 3.0 * x
    defect[50:53] += 25.0
    rebinned_front = 12.0 + 0.5 * z + y + 2.0 * x
    front = np.repeat(
        np.repeat(rebinned_front / (real.FRONT_REBIN_Y * real.FRONT_REBIN_X),
                  real.FRONT_REBIN_Y, axis=1),
        real.FRONT_REBIN_X, axis=2,
    )
    return defect.astype(np.float64), front.astype(np.float64)


class E3RealDataValidationTests(unittest.TestCase):
    def test_front_rebin_preserves_layout_shape_and_counts(self):
        defect = np.zeros((2, 2, 2), dtype=float)
        front = np.arange(2 * 4 * 16, dtype=float).reshape(2, 4, 16)
        rebinned = real.rebin_front(front, defect.shape)
        expected = front.reshape(2, 2, 2, 2, 8).sum(axis=(2, 4))
        self.assertTrue(np.array_equal(expected, rebinned))
        self.assertEqual(defect.shape, rebinned.shape)
        self.assertEqual(float(front.sum()), float(rebinned.sum()))

    def test_sliding_windows_are_three_slice_sums_with_unit_stride(self):
        values = np.arange(5 * 2 * 2, dtype=float).reshape(5, 2, 2)
        windows = real.sliding_count_windows(values)
        self.assertEqual((3, 2, 2), windows.shape)
        self.assertTrue(np.array_equal(windows[0], values[0:3].sum(axis=0)))
        self.assertTrue(np.array_equal(windows[1], values[1:4].sum(axis=0)))
        self.assertTrue(np.array_equal(windows[2], values[2:5].sum(axis=0)))

    def test_metrics_identities_and_target_peak_selection(self):
        defect, front = synthetic_volumes()
        result = real.analyze_volumes(defect, front)
        self.assertEqual((64, 4, 3), result.defect_windows.shape)
        self.assertTrue(
            np.array_equal(
                result.residual_windows,
                result.defect_windows - result.front_windows,
            )
        )
        metrics = result.metrics
        self.assertTrue(
            np.allclose(metrics.front_fraction + metrics.retained_fraction, 1.0)
        )
        target = metrics[metrics.inside_target_slice_range]
        self.assertEqual(list(range(46, 54)), target.window_index.tolist())
        self.assertEqual(
            int(target.loc[target.residual_count.idxmax(), "window_index"]),
            result.peak_window_index,
        )
        first = metrics.iloc[0]
        self.assertEqual((0, 3), (first.window_start_index, first.window_end_index_exclusive))
        self.assertEqual((0.0, 3.0, 1.5), (first.z_start_mm, first.z_end_mm, first.z_center_mm))

    def test_peak_tie_prefers_shallower_window(self):
        frame = pd.DataFrame(
            {
                "window_index": [46, 47, 48],
                "residual_count": [3.0, 9.0, 9.0],
                "inside_target_slice_range": [True, True, True],
            }
        )
        self.assertEqual(47, real.select_peak_window(frame))

    def test_invalid_inputs_and_zero_denominator_fail(self):
        defect, front = synthetic_volumes()
        with self.assertRaisesRegex(ValueError, "66 z slices"):
            real.analyze_volumes(defect[:-1], front[:-1])
        with self.assertRaisesRegex(ValueError, "fixed y/x factors"):
            real.rebin_front(front[:, :-1], defect.shape)
        invalid = defect.copy()
        invalid[0, 0, 0] = -1.0
        with self.assertRaisesRegex(ValueError, "finite, non-negative"):
            real.analyze_volumes(invalid, front)
        invalid = defect.copy()
        invalid[0, 0, 0] = np.nan
        with self.assertRaisesRegex(ValueError, "finite, non-negative"):
            real.analyze_volumes(invalid, front)
        zeros = np.zeros((64, 2, 2), dtype=float)
        nonconstant = np.broadcast_to(np.arange(4, dtype=float).reshape(1, 2, 2), zeros.shape)
        with self.assertRaisesRegex(ValueError, "positive defect counts"):
            real.build_window_metrics(zeros, nonconstant)

    def test_loader_rejects_non_3d_and_non_finite_npy(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            two_dimensional = root / "two.npy"
            non_finite = root / "nan.npy"
            np.save(two_dimensional, np.ones((2, 2)))
            np.save(non_finite, np.asarray([[[np.inf]]]))
            with self.assertRaisesRegex(ValueError, "three-dimensional"):
                real.load_count_volume(two_dimensional, "fixture")
            with self.assertRaisesRegex(ValueError, "finite counts"):
                real.load_count_volume(non_finite, "fixture")

    def test_output_contract_npy_contents_and_png_resolution(self):
        defect, front = synthetic_volumes()
        result = real.analyze_volumes(defect, front)
        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp) / "real_data"
            real.write_outputs(result, output)
            self.assertEqual(set(real.OUTPUT_NAMES), {path.name for path in output.iterdir()})
            saved = [np.load(output / name, allow_pickle=False) for name in real.ARRAY_NAMES]
            self.assertTrue(np.array_equal(saved[0], result.defect_windows))
            self.assertTrue(np.array_equal(saved[1], result.front_windows))
            self.assertTrue(np.array_equal(saved[2], saved[0] - saved[1]))
            self.assertEqual((64, 4, 3), saved[0].shape)
            for name in real.FIGURE_NAMES:
                with Image.open(output / name) as image:
                    dpi = image.info.get("dpi")
                    self.assertEqual("PNG", image.format)
                    self.assertIsNotNone(dpi)
                    self.assertGreater(dpi[0], 299.0)
                    self.assertGreater(dpi[1], 299.0)

            owned = output / real.ROI_CNR_SUBDIRECTORY
            owned.mkdir()
            (owned / "marker.txt").write_text("preserve", encoding="utf-8")
            real.validate_outputs(output)

            staging = Path(tmp) / "staging"
            real.write_outputs(result, staging)
            real.publish(staging, output, overwrite=True)
            self.assertEqual(
                "preserve",
                (output / real.ROI_CNR_SUBDIRECTORY / "marker.txt").read_text(encoding="utf-8"),
            )
            real.validate_outputs(output)

    def test_publish_requires_overwrite_and_replaces_atomically(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            output = root / "output"
            output.mkdir()
            (output / "old.txt").write_text("old", encoding="utf-8")
            first_staging = root / "first"
            first_staging.mkdir()
            with self.assertRaisesRegex(FileExistsError, "--overwrite"):
                real.publish(first_staging, output, overwrite=False)
            self.assertTrue((output / "old.txt").is_file())

            second_staging = root / "second"
            second_staging.mkdir()
            (second_staging / "new.txt").write_text("new", encoding="utf-8")
            real.publish(second_staging, output, overwrite=True)
            self.assertFalse((output / "old.txt").exists())
            self.assertEqual("new", (output / "new.txt").read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
