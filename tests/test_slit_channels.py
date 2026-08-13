#!/usr/bin/env python3

from __future__ import annotations

import csv
import json
import math
import tempfile
import unittest
from pathlib import Path

import numpy as np
import yaml


REPO_ROOT = Path(__file__).resolve().parents[1]

from scripts.data_processing import clean_events as cleaner
from scripts.data_processing import estimate_slit_boundaries as estimator
from scripts.data_processing import slit_channels as channels


class SlitBoundaryAlgorithmTests(unittest.TestCase):
    def setUp(self):
        self.config = channels.BoundaryAlgorithmConfig()

    def test_detects_exactly_three_ordered_bands(self):
        rng = np.random.default_rng(7)
        x = np.concatenate([
            rng.normal(20, 1.7, 10000),
            rng.normal(50, 1.9, 8500),
            rng.normal(80, 1.6, 7000),
        ])
        result = channels.detect_profile_boundaries(x, (0, 100), "P001", self.config)
        self.assertEqual(3, len(result.peak_x_mm))
        self.assertEqual(2, len(result.boundary_x_mm))
        self.assertTrue(
            result.peak_x_mm[0]
            < result.boundary_x_mm[0]
            < result.peak_x_mm[1]
            < result.boundary_x_mm[1]
            < result.peak_x_mm[2]
        )

    def test_valley_plateau_uses_spatial_center(self):
        smooth = np.asarray([10.0, 2.0, 0.0, 0.0, 2.0, 10.0])
        centers = np.arange(6, dtype=float)
        valley = channels._find_valley(smooth, centers, 0, 5, self.config, "P001")
        self.assertEqual(2, valley.plateau_left_index)
        self.assertEqual(3, valley.plateau_right_index)
        self.assertEqual(2.5, valley.boundary_x_mm)

    def test_wrong_peak_count_stops(self):
        rng = np.random.default_rng(11)
        x = np.concatenate([rng.normal(25, 2, 6000), rng.normal(75, 2, 6000)])
        with self.assertRaisesRegex(channels.BoundaryEstimationError, "exactly three"):
            channels.detect_profile_boundaries(x, (0, 100), "P001", self.config)

    def test_shallow_or_disconnected_valley_stops(self):
        centers = np.arange(7, dtype=float)
        with self.assertRaisesRegex(channels.BoundaryEstimationError, "ratio"):
            channels._find_valley(
                np.asarray([10.0, 9.0, 8.0, 7.0, 8.0, 9.0, 10.0]),
                centers,
                0,
                6,
                self.config,
                "P001",
            )
        with self.assertRaisesRegex(channels.BoundaryEstimationError, "disconnected"):
            channels._find_valley(
                np.asarray([10.0, 2.0, 0.0, 2.0, 0.0, 2.0, 10.0]),
                centers,
                0,
                6,
                self.config,
                "P001",
            )

    def test_non_finite_x_stops(self):
        with self.assertRaisesRegex(channels.BoundaryEstimationError, "non-finite"):
            channels.detect_profile_boundaries(
                np.asarray([1.0, 2.0, math.nan]), (0, 10), "P001", self.config
            )

    def test_stability_tolerance_failure_stops(self):
        rng = np.random.default_rng(13)
        x = np.concatenate([
            rng.normal(20, 1.7, 6000),
            rng.normal(50, 1.7, 6000),
            rng.normal(80, 1.7, 6000),
        ])
        baseline = channels.detect_profile_boundaries(x, (0, 100), "P001", self.config)
        strict = channels.BoundaryAlgorithmConfig(
            maximum_peak_shift_mm=1.0e-12,
            maximum_boundary_shift_mm=1.0e-12,
        )
        with self.assertRaisesRegex(channels.BoundaryEstimationError, "stability"):
            channels.validate_stability(x, (0, 100), "P001", baseline, strict)

    def test_diagnostic_writer_is_png_only(self):
        with tempfile.TemporaryDirectory() as tmp:
            fig, axis = estimator.plt.subplots()
            axis.plot([0, 1], [0, 1])
            base = Path(tmp) / "diagnostic"
            estimator.save_figure(fig, base)
            self.assertTrue(base.with_suffix(".png").is_file())
            self.assertFalse(base.with_suffix(".pdf").exists())


class SlitLabelTests(unittest.TestCase):
    def boundary_payload(self) -> dict:
        return {
            "schema_version": channels.SCHEMA_VERSION,
            "algorithm_version": channels.ALGORITHM_VERSION,
            "profiles": {
                "P001": {
                    "slit_order": ["S2", "S4", "S6"],
                    "boundaries_mm": {"S2_S4": 40.0, "S4_S6": 70.0},
                },
                "P002": {
                    "slit_order": ["S1", "S3", "S5"],
                    "boundaries_mm": {"S1_S3": 30.0, "S3_S5": 60.0},
                },
            },
        }

    def write_run(self, root: Path, profile: str, offset: float, values: list[str]) -> Path:
        run = root / "center" / "P0" / profile / "run"
        run.mkdir(parents=True)
        metadata = {
            "case_id": f"source_response_center_P0_{profile}_E560_seed1",
            "run_id": "pose_x0_y0_E560keV_seed1",
            "config_file": f"config/generated/articlev2/configs/center/P0_{profile}.yaml",
            "vehicle_model_id": "P0",
            "pose_id": "pose_x0_y0",
            "head_offset_x_mm": offset,
            "head_offset_y_mm": 0,
            "n_primary": 100,
            "source": {"mono_energy_keV": 560},
            "collimator": {"profile_id": profile},
            "detector": {"actual_x_range_mm": [0 + offset, 100 + offset]},
        }
        (run / "metadata.yaml").write_text(yaml.safe_dump(metadata), encoding="utf-8")
        events = run / "events.csv"
        with events.open("w", encoding="utf-8", newline="") as stream:
            writer = csv.DictWriter(
                stream,
                fieldnames=["event_id", "det_x", "first_scatter_z", "last_scatter_z", "physical_field"],
            )
            writer.writeheader()
            for index, value in enumerate(values):
                writer.writerow({
                    "event_id": index, "det_x": value, "first_scatter_z": "1",
                    "last_scatter_z": "1", "physical_field": f"v{index}",
                })
        return events

    def test_boundary_equality_extremes_and_profile_mapping(self):
        self.assertEqual("S2", channels.slit_label_for_x(-1e9, "P001", (40, 70)))
        self.assertEqual("S4", channels.slit_label_for_x(40, "P001", (40, 70)))
        self.assertEqual("S6", channels.slit_label_for_x(70, "P001", (40, 70)))
        self.assertEqual("S1", channels.slit_label_for_x(29.9, "P002", (30, 60)))
        self.assertEqual("S3", channels.slit_label_for_x(30, "P002", (30, 60)))
        self.assertEqual("S5", channels.slit_label_for_x(1e9, "P002", (30, 60)))

    def test_grid_offset_and_raw_row_preservation(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            events = self.write_run(root, "P001", 5.0, ["44.9", "45", "74.9", "75"])
            output = root / "out" / "events_valid.csv"
            summary = cleaner.clean_and_label_file(events, output, self.boundary_payload())
            with output.open("r", encoding="utf-8", newline="") as stream:
                reader = csv.DictReader(stream)
                rows = list(reader)
                self.assertEqual(
                    [
                        "det_x", "first_scatter_z", "last_scatter_z", "physical_field",
                        "slit_group", "slit_label",
                    ],
                    reader.fieldnames,
                )
            self.assertEqual(["v0", "v1", "v2", "v3"], [row["physical_field"] for row in rows])
            self.assertEqual(["S2", "S4", "S4", "S6"], [row["slit_label"] for row in rows])
            self.assertEqual(["P001"] * 4, [row["slit_group"] for row in rows])
            self.assertEqual(4, summary["rows_kept"])
            self.assertTrue((output.parent / "metadata.yaml").is_file())

    def test_non_finite_det_x_and_unknown_profile_stop(self):
        with self.assertRaisesRegex(ValueError, "finite"):
            channels.slit_label_for_x(math.nan, "P001", (40, 70))
        with self.assertRaisesRegex(ValueError, "unknown profile"):
            channels.slit_label_for_x(1, "P999", (40, 70))
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            events = self.write_run(root, "P001", 0.0, ["NaN"])
            with self.assertRaisesRegex(ValueError, "finite"):
                cleaner.clean_and_label_file(
                    events, root / "out" / "events_valid.csv", self.boundary_payload()
                )

    def test_boundary_config_schema_validation(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "boundaries.json"
            path.write_text(json.dumps(self.boundary_payload()), encoding="utf-8")
            loaded = channels.load_boundary_config(path)
            self.assertEqual((40.0, 70.0), channels.profile_boundaries(loaded, "P001"))
            invalid = self.boundary_payload()
            invalid["profiles"]["P002"]["boundaries_mm"] = {"S1_S3": 61, "S3_S5": 60}
            path.write_text(json.dumps(invalid), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "boundary order"):
                channels.load_boundary_config(path)


if __name__ == "__main__":
    unittest.main()
