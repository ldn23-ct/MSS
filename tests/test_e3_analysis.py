#!/usr/bin/env python3

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

import numpy as np
import pandas as pd
import yaml
from PIL import Image

from scripts.data_processing.common import SLIT_PROFILE
from scripts.data_processing.experiment_contract import DEFECT_CENTER_Z_MM, GRID_OFFSETS_MM
from scripts.postprocessing.e3 import run as analysis
from scripts.postprocessing.e3 import run_core as core


def synthetic_base(depth_index: int = 1) -> np.ndarray:
    y_index, x_index = np.indices((9, 9))
    spatial = 3 * x_index + 2 * y_index
    center = analysis.DEFECT_MASK.astype(int)
    categories = []
    for category in range(6):
        values = 700 + 90 * category + 10 * depth_index + spatial
        if category in (1, 4):
            values = values - (35 + 2 * depth_index) * center
        categories.append(values.astype(np.int64))
    return np.stack(categories)


def complete_inventory() -> pd.DataFrame:
    conditions = []
    for index in range(1, 7):
        slit = f"S{index}"
        profile = SLIT_PROFILE[slit]
        conditions.extend((("P0", profile), (f"P{index}", profile)))
    rows = []
    for phantom, profile in dict.fromkeys(conditions):
        for x in GRID_OFFSETS_MM:
            for y in GRID_OFFSETS_MM:
                rows.append(
                    {
                        "scan_mode": "grid",
                        "phantom_id": phantom,
                        "profile_id": profile,
                        "head_offset_x_mm": x,
                        "head_offset_y_mm": y,
                        "status": "valid",
                        "valid_file": f"grid/{phantom}/{profile}/{x}/{y}/events_valid.csv",
                    }
                )
    return pd.DataFrame(rows)


class ArticleV2E3AnalysisTests(unittest.TestCase):
    def test_source_regions_are_left_closed_right_open(self):
        front, target, behind = analysis.source_region_masks(
            np.asarray([54.9, 55.0, 64.999, 65.0]), (55.0, 65.0)
        )
        self.assertEqual([True, False, False, False], front.tolist())
        self.assertEqual([False, True, True, False], target.tolist())
        self.assertEqual([False, False, False, True], behind.tolist())

        frame = pd.DataFrame(
            {
                "scatter_count_total": [1, 1, 1, 2, 2, 2, 0],
                "first_scatter_z": [54.9, 55.0, 65.0, 54.9, 55.0, 65.0, np.nan],
            }
        )
        self.assertEqual([1, 1, 1, 1, 1, 1], analysis.category_counts(frame, (55.0, 65.0)).tolist())

    def test_method_identities_roi_and_metrics(self):
        base = synthetic_base()
        methods = analysis.methods_from_base(base)
        analysis.validate_identities(base, methods)
        self.assertEqual((6, 9, 9), methods.shape)
        self.assertTrue(np.array_equal(methods[4], methods[2] + methods[3]))
        self.assertEqual((25, 24, 32), tuple(int(item.sum()) for item in analysis.roi_masks()))
        stats = analysis.image_statistics(methods)
        self.assertEqual((6,), stats["cnr"].shape)
        self.assertTrue(np.isfinite(stats["cnr"]).all())
        with self.assertRaisesRegex(ValueError, "background standard deviation is zero"):
            analysis.image_statistics(np.ones((9, 9)))
        with self.assertRaisesRegex(ValueError, "denominator is non-positive"):
            analysis.relative_gain(np.asarray([2.0]), np.asarray([0.0]), "gain")

    def test_grid_coordinates_use_y_rows_and_x_columns(self):
        self.assertEqual((2, 7), analysis.grid_position_indices(7.5, -5.0))
        self.assertEqual((7, 2), analysis.grid_position_indices(-5.0, 7.5))
        with self.assertRaisesRegex(ValueError, "unexpected E3 grid coordinate"):
            analysis.grid_position_indices(12.5, 0.0)

    def test_scatter_validation_and_recorded_roi(self):
        for invalid in (-1, 1.5, np.nan):
            with self.subTest(invalid=invalid):
                with self.assertRaisesRegex(ValueError, "finite non-negative integers"):
                    analysis.scatter_counts(pd.DataFrame({"scatter_count_total": [invalid]}))
        metadata = type(
            "Metadata",
            (),
            {"profile_id": "P001", "head_offset_x_mm": 0.0, "head_offset_y_mm": 0.0, "metadata_path": Path("meta")},
        )()
        region = analysis.roi_for_slit("S4")
        frame = pd.DataFrame(
            {
                "det_x": [region.x_min_mm, region.x_max_mm, region.x_min_mm, region.x_min_mm - 0.01],
                "det_y": [region.y_min_mm, region.y_max_mm, 0.0, 0.0],
                "scatter_count_total": [1, 1, 1, 1],
                "first_scatter_z": [60.0] * 4,
                "slit_group": ["P001"] * 4,
                "slit_label": ["S4", "S4", "S2", "S4"],
            }
        )
        self.assertEqual(2, len(analysis.select_events(frame, metadata, "S4")))

    def test_bootstrap_is_deterministic_and_reconstructs_methods(self):
        base = synthetic_base()
        first = analysis.bootstrap_condition(base, np.random.default_rng(17), resample_count=120)
        second = analysis.bootstrap_condition(base, np.random.default_rng(17), resample_count=120)
        self.assertTrue(np.array_equal(first.method_images, second.method_images))
        self.assertTrue(np.array_equal(first.cnr, second.cnr))
        self.assertEqual((120, 6, 9, 9), first.method_images.shape)
        self.assertTrue(np.array_equal(first.method_images[:, 4], first.method_images[:, 2] + first.method_images[:, 3]))
        self.assertTrue(np.allclose(first.retention[:, 0], 1.0))

    def test_invalid_resamples_are_filtered_per_metric(self):
        zero_images = np.zeros((3, 6, 9, 9), dtype=float)
        stats = analysis.image_statistics(zero_images, allow_invalid=True)
        self.assertTrue(np.isnan(stats["cnr"]).all())
        gains = analysis.relative_gain(
            np.array([2.0, 3.0, 4.0]),
            np.array([1.0, 0.0, 2.0]),
            "filtered",
            allow_invalid=True,
        )
        self.assertTrue(np.isnan(gains[1]))
        self.assertEqual(2, analysis.effective_count(gains))
        self.assertEqual(2, len([value for value in gains if np.isfinite(value)]))

    def test_strict_inventory_rejects_missing_duplicate_and_extra_poses(self):
        inventory = complete_inventory()
        conditions, issues, missing = analysis.inspect_inventory(inventory)
        self.assertFalse(issues)
        self.assertEqual(0, missing)
        self.assertEqual(8, len(conditions))

        missing_inventory = inventory.iloc[1:].copy()
        _, issues, missing = analysis.inspect_inventory(missing_inventory)
        self.assertEqual(1, missing)
        self.assertTrue(any("missing poses" in item for item in issues))

        duplicate_inventory = pd.concat((inventory, inventory.iloc[[0]]), ignore_index=True)
        _, issues, _ = analysis.inspect_inventory(duplicate_inventory)
        self.assertTrue(any("duplicate poses" in item for item in issues))

        extra_inventory = inventory.copy()
        extra_inventory.loc[0, "head_offset_x_mm"] = 12.5
        _, issues, missing = analysis.inspect_inventory(extra_inventory)
        self.assertEqual(1, missing)
        self.assertTrue(any("unexpected poses" in item for item in issues))

    def test_slab_manifest_is_required_and_frozen(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _, issues, missing = analysis.inspect_slab_root(root)
            self.assertEqual(81, missing)
            self.assertTrue(any("provenance manifest" in item for item in issues))
            (root / analysis.SLAB_MANIFEST_NAME).write_text(
                yaml.safe_dump({"reference_type": "wrong", "thickness_mm": 54.0}),
                encoding="utf-8",
            )
            _, issues, _ = analysis.inspect_slab_root(root)
            self.assertTrue(any("reference_type" in item for item in issues))
            self.assertTrue(any("thickness_mm" in item for item in issues))

    def test_complete_synthetic_run_generates_exact_six_figures_and_four_tables(self):
        conditions = {
            phantom: analysis.GridCondition(
                phantom=phantom,
                slit=f"S{index}",
                base_counts=synthetic_base(index),
                n_primary=20_000_000,
                energy_keV=560.0,
            )
            for index, phantom in enumerate(DEFECT_CENTER_Z_MM, start=1)
        }
        slab_y, slab_x = np.indices((9, 9))
        slab = analysis.SlabCondition(
            image=(500 + slab_x + 2 * slab_y).astype(np.int64),
            n_primary=20_000_000,
            energy_keV=560.0,
            geometry_id="P4_front_slab_55mm.yaml",
        )
        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp) / "E3"
            summary = analysis.run_e3(
                conditions, slab, output, resample_seed=19, resample_count=150
            )
            self.assertTrue(summary["identities_passed"])
            self.assertEqual(set(analysis.OUTPUT_NAMES), {path.name for path in output.iterdir()})
            t1 = pd.read_csv(output / analysis.TABLE_NAMES[0])
            t2 = pd.read_csv(output / analysis.TABLE_NAMES[1])
            t3 = pd.read_csv(output / analysis.TABLE_NAMES[2])
            t4 = pd.read_csv(output / analysis.TABLE_NAMES[3])
            self.assertEqual(analysis.T1_COLUMNS, tuple(t1.columns))
            self.assertEqual(analysis.T2_COLUMNS, tuple(t2.columns))
            self.assertEqual(analysis.T3_COLUMNS, tuple(t3.columns))
            self.assertEqual(analysis.T4_COLUMNS, tuple(t4.columns))
            self.assertTrue(np.issubdtype(t1.total_count_N.dtype, np.integer))
            self.assertEqual((6, 36, 18, 3), (len(t1), len(t2), len(t3), len(t4)))
            self.assertEqual(set(analysis.METHODS), set(t2.method))
            self.assertIn("M3", set(t2.method))
            self.assertEqual(
                {item[0] for item in analysis.COMPARISONS}, set(t3.comparison)
            )
            self.assertFalse(
                t3.filter(regex="^g_")
                .astype(str)
                .apply(lambda col: col.str.contains("%").any())
                .any()
            )
            self.assertFalse(any("difference" in column.lower() for column in t4.columns))
            self.assertTrue((t1.filter(like="n_effective") > 0).all().all())
            self.assertTrue((t2.filter(like="n_effective") > 0).all().all())
            self.assertTrue((t3.filter(like="n_effective") > 0).all().all())
            self.assertTrue((t4.filter(like="n_effective") > 0).all().all())
            self.assertEqual(6, len(analysis.FIGURE_NAMES))
            with Image.open(output / analysis.FIGURE_NAMES[0]) as image:
                dpi = image.info.get("dpi")
                self.assertIsNotNone(dpi)
                self.assertGreater(dpi[0], 299.0)
                self.assertGreater(dpi[1], 299.0)

    def test_core_synthetic_run_generates_exact_five_figures_and_three_tables(self):
        conditions = {
            phantom: analysis.GridCondition(
                phantom=phantom,
                slit=f"S{index}",
                base_counts=synthetic_base(index),
                n_primary=100_000_000,
                energy_keV=560.0,
            )
            for index, phantom in enumerate(DEFECT_CENTER_Z_MM, start=1)
        }
        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp) / "E3"
            core.run_core(conditions, output, resample_seed=23, resample_count=120)
            self.assertEqual(set(core.CORE_OUTPUT_NAMES), {path.name for path in output.iterdir()})
            self.assertEqual(5, len(core.CORE_FIGURE_NAMES))
            self.assertEqual(3, len(core.CORE_TABLE_NAMES))
            self.assertFalse((output / analysis.FIGURE_NAMES[5]).exists())
            self.assertFalse((output / analysis.TABLE_NAMES[3]).exists())

    def test_publication_refuses_unexpected_existing_files(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            staging = root / "staging"
            output = root / "E3"
            staging.mkdir()
            output.mkdir()
            (output / "notes.txt").write_text("user file", encoding="utf-8")
            with self.assertRaisesRegex(FileExistsError, "unexpected files"):
                analysis.publish(staging, output, overwrite=True)
            self.assertTrue((output / "notes.txt").is_file())


if __name__ == "__main__":
    unittest.main()
