#!/usr/bin/env python3

from __future__ import annotations

import csv
import hashlib
import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import yaml


REPO_ROOT = Path(__file__).resolve().parents[1]

from scripts.data_processing import clean_events, slit_channels


RAW_FIELDS = [
    "event_id", "hit_id", "track_id", "parent_id", "is_primary_gamma",
    "gamma_source_type", "gamma_source_process", "gamma_source_region_id",
    "rayleigh_count", "det_x", "first_scatter_z", "last_scatter_z",
    "scatter_count_total", "physical_field",
]


def boundary_payload() -> dict:
    return {
        "schema_version": slit_channels.SCHEMA_VERSION,
        "algorithm_version": slit_channels.ALGORITHM_VERSION,
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


class ArticleV2CleanEventsTests(unittest.TestCase):
    def write_run(
        self, root: Path, profile: str, offset: float, rows: list[dict[str, str]],
    ) -> Path:
        run = root / "events" / "raw" / "center" / "P0" / profile / "run"
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
            "detector": {"actual_x_range_mm": [offset, 100 + offset]},
        }
        (run / "metadata.yaml").write_text(yaml.safe_dump(metadata), encoding="utf-8")
        events = run / "events.csv"
        with events.open("w", encoding="utf-8", newline="") as stream:
            writer = csv.DictWriter(stream, fieldnames=RAW_FIELDS)
            writer.writeheader()
            writer.writerows(rows)
        return events

    def row(self, index: int, det_x: str, first_z: str, last_z: str) -> dict[str, str]:
        return {
            "event_id": str(index), "hit_id": "0", "track_id": "1", "parent_id": "0",
            "is_primary_gamma": "1", "gamma_source_type": "primary",
            "gamma_source_process": "primary_generator", "gamma_source_region_id": "source",
            "rayleigh_count": "0", "det_x": det_x, "first_scatter_z": first_z,
            "last_scatter_z": last_z, "scatter_count_total": "1",
            "physical_field": f"v{index}",
        }

    def test_depth_filter_no_roi_and_schema_preservation(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            events = self.write_run(root, "P001", 5.0, [
                self.row(1, "-999", "0", "0"),
                self.row(2, "45", "1", "2"),
                self.row(3, "74.9", "2", "3"),
                self.row(4, "10000", "3", "4"),
                self.row(5, "50", "-0.1", "1"),
                self.row(6, "50", "NaN", "1"),
                self.row(7, "50", "1", "Inf"),
            ])
            output = root / "out" / "events_valid.csv"
            summary = clean_events.clean_and_label_file(events, output, boundary_payload())
            with output.open("r", encoding="utf-8", newline="") as stream:
                reader = csv.DictReader(stream)
                rows = list(reader)
                fields = reader.fieldnames or []
            self.assertEqual(7, summary["rows_read"])
            self.assertEqual(4, summary["rows_kept"])
            self.assertEqual(1, summary["rows_dropped_negative_depth"])
            self.assertEqual(2, summary["rows_dropped_nonfinite_depth"])
            self.assertEqual(["v1", "v2", "v3", "v4"], [row["physical_field"] for row in rows])
            self.assertEqual(["S2", "S4", "S4", "S6"], [row["slit_label"] for row in rows])
            self.assertEqual(["P001"] * 4, [row["slit_group"] for row in rows])
            for field in clean_events.VALID_EVENT_DROP_COLUMNS:
                self.assertNotIn(field, fields)
            self.assertEqual(["slit_group", "slit_label"], fields[-2:])
            self.assertTrue((output.parent / "metadata.yaml").is_file())

    def test_non_numeric_depth_and_nonfinite_detector_x_fail(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            bad_depth = self.write_run(root / "one", "P001", 0, [
                self.row(1, "20", "bad", "1")
            ])
            with self.assertRaisesRegex(ValueError, "first_scatter_z must be numeric"):
                clean_events.clean_and_label_file(
                    bad_depth, root / "out1/events_valid.csv", boundary_payload()
                )
            bad_x = self.write_run(root / "two", "P001", 0, [
                self.row(1, "NaN", "1", "1")
            ])
            with self.assertRaisesRegex(ValueError, "det_x must be finite"):
                clean_events.clean_and_label_file(
                    bad_x, root / "out2/events_valid.csv", boundary_payload()
                )

    def test_existing_boundary_is_reused_and_manifest_is_complete(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.write_run(root, "P002", 0, [self.row(1, "30", "0", "0")])
            config_path = root / "data_processing/slit_channels" / clean_events.BOUNDARY_CONFIG_NAME
            config_path.parent.mkdir(parents=True)
            config_path.write_text(json.dumps(boundary_payload()), encoding="utf-8")
            self.assertEqual(0, clean_events.main(["--results-root", str(root)]))
            output = root / "events/valid/center/P0/P002/run/events_valid.csv"
            with output.open("r", encoding="utf-8", newline="") as stream:
                row = next(csv.DictReader(stream))
            self.assertEqual("S3", row["slit_label"])
            manifest = yaml.safe_load(
                (root / "events/valid/valid_events_manifest.yaml").read_text(encoding="utf-8")
            )
            self.assertEqual("reused", manifest["boundary_action"])
            self.assertEqual(1, manifest["total_rows_read"])
            self.assertEqual(1, manifest["total_rows_kept"])
            self.assertEqual(
                hashlib.sha256(config_path.read_bytes()).hexdigest(),
                manifest["boundary_config_sha256"],
            )

    def test_missing_boundary_calibrates_once_and_invalid_config_does_not(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            config_path = root / "data_processing/slit_channels" / clean_events.BOUNDARY_CONFIG_NAME

            def fake_estimator(arguments: list[str]) -> int:
                config_path.parent.mkdir(parents=True, exist_ok=True)
                config_path.write_text(json.dumps(boundary_payload()), encoding="utf-8")
                return 0

            with mock.patch.object(
                clean_events, "estimate_boundaries_main", side_effect=fake_estimator
            ) as call:
                self.assertEqual("calibrated", clean_events.ensure_boundary_config(root, config_path))
                self.assertTrue(call.called)
            with mock.patch.object(clean_events, "estimate_boundaries_main") as call:
                self.assertEqual("reused", clean_events.ensure_boundary_config(root, config_path))
                call.assert_not_called()

            config_path.write_text("{bad json", encoding="utf-8")
            with mock.patch.object(clean_events, "estimate_boundaries_main") as call:
                with self.assertRaisesRegex(ValueError, "cannot read boundary config"):
                    clean_events.ensure_boundary_config(root, config_path)
                call.assert_not_called()


if __name__ == "__main__":
    unittest.main()
