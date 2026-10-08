#!/usr/bin/env python3

from __future__ import annotations

import inspect
import math
import tempfile
import unittest
from pathlib import Path

import numpy as np
import pandas as pd
from PIL import Image
from scipy.optimize import linear_sum_assignment
from scipy.spatial.distance import cdist

from scripts.postprocessing.e3 import run_real_data_roi_cnr as roi


def synthetic_images() -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    rng = np.random.default_rng(7)
    y_grid, x_grid = np.indices((103, 101))
    D = 250.0 + 0.20 * y_grid - 0.15 * x_grid + rng.normal(0.0, 4.0, (103, 101))
    angle = math.radians(3.0)
    row_vector = np.asarray([-10.2 * math.sin(angle), 10.2 * math.cos(angle)])
    column_vector = np.asarray([11.0 * math.cos(angle), 11.0 * math.sin(angle)])
    origin = np.asarray([27.0, 30.0])
    centers = np.asarray(
        [
            origin + row * row_vector + column * column_vector
            for row in range(roi.GRID_SIZE)
            for column in range(roi.GRID_SIZE)
        ]
    )
    for x, y in centers:
        radius = np.hypot(x_grid - x, y_grid - y)
        D -= 50.0 * np.exp(-((radius / 2.3) ** 4))
    D[:4, :] = 5.0
    D[100:, :] = 2.0
    D[:, 0] = 10.0
    for x, y in ((3, 14), (92, 14), (3, 91), (92, 91)):
        D[y - 1 : y + 2, x - 1 : x + 2] = 5.0
    R = 0.72 * D - 20.0 + rng.normal(0.0, 2.0, D.shape)
    return D.astype(np.float64), R.astype(np.float64), centers


class E3RealDataRoiCnrTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.D, cls.R, cls.true_centers = synthetic_images()
        stats = {
            "D_volume": {"shape": [64, 103, 101], "dtype": "float64"},
            "R_volume": {"shape": [64, 103, 101], "dtype": "float64"},
        }
        cls.result = roi.analyze(cls.D, cls.R, roi.DEFAULT_WINDOW_INDEX, stats)

    def test_cli_contract(self):
        args = roi.parse_args(["--results-root", "custom-results", "--window-index", "12"])
        self.assertEqual(Path("custom-results"), args.results_root)
        self.assertIsNone(args.input_dir)
        self.assertEqual(12, args.window_index)

    def test_detects_rotated_5x5_lattice_and_excludes_edges_and_bad_pixels(self):
        geometry = self.result.geometry
        rows, columns = linear_sum_assignment(cdist(geometry.centers, self.true_centers))
        self.assertEqual(roi.HOLE_COUNT, len(geometry.centers))
        self.assertLess(float(cdist(geometry.centers, self.true_centers)[rows, columns].max()), 0.75)
        self.assertLess(float(geometry.lattice_errors.max()), 0.25 * geometry.nearest_neighbor_distance)
        self.assertFalse(geometry.valid_mask[0, 50])
        self.assertFalse(geometry.valid_mask[14, 3])
        rounded = np.rint(geometry.centers).astype(int)
        self.assertTrue(geometry.valid_mask[rounded[:, 1], rounded[:, 0]].all())
        self.assertEqual(list(range(1, 26)), self.result.centers_table.hole_id.tolist())

    def test_D_only_geometry_api_and_R_invariance(self):
        self.assertEqual(["D"], list(inspect.signature(roi.derive_roi_geometry).parameters))
        geometry = self.result.geometry
        altered_R = np.flipud(self.R) * -3.0 + 17.0
        altered = roi.analyze(
            self.D,
            altered_R,
            roi.DEFAULT_WINDOW_INDEX,
            self.result.input_stats,
        )
        self.assertTrue(np.array_equal(geometry.centers, altered.geometry.centers))
        self.assertTrue(np.array_equal(geometry.defect_masks, altered.geometry.defect_masks))
        self.assertTrue(np.array_equal(geometry.background_masks, altered.geometry.background_masks))
        self.assertFalse(np.array_equal(self.result.per_hole.R_CNR, altered.per_hole.R_CNR))

    def test_masks_are_shared_disjoint_voronoi_constrained_and_sized(self):
        geometry = self.result.geometry
        self.assertEqual((25, 103, 101), geometry.defect_masks.shape)
        self.assertEqual((25, 103, 101), geometry.background_masks.shape)
        self.assertFalse(np.any(geometry.defect_masks & geometry.background_masks))
        self.assertTrue((geometry.defect_masks.sum(axis=(1, 2)) >= roi.MIN_DEFECT_PIXELS).all())
        self.assertTrue((geometry.background_masks.sum(axis=(1, 2)) >= roi.MIN_BACKGROUND_PIXELS).all())
        y_grid, x_grid = np.indices(self.D.shape)
        distances = np.sqrt(
            (x_grid[None] - geometry.centers[:, 0, None, None]) ** 2
            + (y_grid[None] - geometry.centers[:, 1, None, None]) ** 2
        )
        nearest = np.argmin(distances, axis=0)
        for index, mask in enumerate(geometry.background_masks):
            self.assertTrue((nearest[mask] == index).all())
        full_defect_disks = distances <= geometry.r_defect
        self.assertFalse(np.any(full_defect_disks & ~geometry.valid_mask[None, :, :]))

    def test_profile_thresholds_and_signed_ddof1_cnr(self):
        geometry = self.result.geometry
        self.assertLess(geometry.r_defect, geometry.r_bg_inner)
        self.assertLess(geometry.r_bg_inner, geometry.r_bg_outer)
        self.assertLess(geometry.r_bg_outer, 0.5 * geometry.nearest_neighbor_distance)
        row = self.result.per_hole.iloc[0]
        d_mask = geometry.defect_masks[0]
        b_mask = geometry.background_masks[0]
        expected_std = float(self.D[b_mask].std(ddof=1))
        expected_cnr = float((self.D[b_mask].mean() - self.D[d_mask].mean()) / expected_std)
        self.assertAlmostEqual(expected_std, float(row.D_background_std))
        self.assertAlmostEqual(expected_cnr, float(row.D_CNR))
        self.assertFalse(np.isclose(self.D[b_mask].std(ddof=0), row.D_background_std))

    def test_sensitivity_is_fixed_nine_configuration_one_factor_design(self):
        sensitivity = self.result.sensitivity
        self.assertEqual(9, len(sensitivity))
        self.assertEqual(
            {"r_defect": 5, "r_bg_inner": 2, "r_bg_outer": 2},
            sensitivity.varied_parameter.value_counts().to_dict(),
        )
        self.assertTrue((sensitivity.finite_hole_count == 25).all())
        self.assertEqual(bool(self.result.summary.iloc[0].sensitivity_stable), self.result.sensitivity_stable)

    def test_output_contract_masks_tables_json_and_300dpi_figures(self):
        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp) / "roi_cnr_analysis"
            roi.write_outputs(self.result, output)
            roi.validate_outputs(output)
            saved_defect = np.load(output / "masks" / roi.MASK_NAMES[0], allow_pickle=False)
            saved_background = np.load(output / "masks" / roi.MASK_NAMES[1], allow_pickle=False)
            self.assertTrue(np.array_equal(saved_defect, self.result.geometry.defect_masks))
            self.assertTrue(np.array_equal(saved_background, self.result.geometry.background_masks))
            per_hole = pd.read_csv(output / "tables" / roi.TABLE_NAMES[1])
            self.assertEqual(roi.PER_HOLE_COLUMNS, tuple(per_hole.columns))
            for name in roi.FIGURE_NAMES:
                with Image.open(output / "figures" / name) as image:
                    dpi = image.info.get("dpi")
                    self.assertEqual("PNG", image.format)
                    self.assertIsNotNone(dpi)
                    self.assertGreater(dpi[0], 299.0)
                    self.assertGreater(dpi[1], 299.0)

    def test_publish_requires_overwrite_and_is_atomic(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            output = root / "output"
            output.mkdir()
            (output / "old.txt").write_text("old", encoding="utf-8")
            first = root / "first"
            first.mkdir()
            with self.assertRaisesRegex(FileExistsError, "--overwrite"):
                roi.publish(first, output, overwrite=False)
            second = root / "second"
            second.mkdir()
            (second / "new.txt").write_text("new", encoding="utf-8")
            roi.publish(second, output, overwrite=True)
            self.assertFalse((output / "old.txt").exists())
            self.assertEqual("new", (output / "new.txt").read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
