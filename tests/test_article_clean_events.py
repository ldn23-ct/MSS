#!/usr/bin/env python3

from __future__ import annotations

import csv
import sys
import tempfile
import unittest
from pathlib import Path

import yaml


REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "scripts/article"))

import clean_events  # noqa: E402


def write_yaml(path: Path, value: dict) -> None:
    path.write_text(yaml.safe_dump(value, sort_keys=False), encoding="utf-8")


class ArticleCleanEventsTests(unittest.TestCase):
    def test_top_level_head_offset_is_used(self):
        metadata = {"head_offset_x_mm": 8}
        self.assertEqual(
            8.0,
            clean_events.head_offset_x_from_metadata(metadata, Path("metadata.yaml")),
        )

    def test_condition_head_offset_is_used(self):
        metadata = {"condition": {"head_offset_x_mm": "8"}}
        self.assertEqual(
            8.0,
            clean_events.head_offset_x_from_metadata(metadata, Path("metadata.yaml")),
        )

    def test_matching_top_level_and_condition_offsets_are_allowed(self):
        metadata = {"head_offset_x_mm": 8, "condition": {"head_offset_x_mm": 8.0}}
        self.assertEqual(
            8.0,
            clean_events.head_offset_x_from_metadata(metadata, Path("metadata.yaml")),
        )

    def test_conflicting_top_level_and_condition_offsets_fail_fast(self):
        metadata = {"head_offset_x_mm": 8, "condition": {"head_offset_x_mm": 9}}
        with self.assertRaisesRegex(ValueError, "values disagree"):
            clean_events.head_offset_x_from_metadata(metadata, Path("metadata.yaml"))

    def test_clean_one_file_shifts_slit_ranges_by_head_offset(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            run_dir = root / "input"
            run_dir.mkdir()
            event_file = run_dir / "events.csv"
            metadata_file = run_dir / "metadata.yaml"
            output_file = root / "output" / "events_clean.csv"

            write_yaml(metadata_file, {"condition": {"head_offset_x_mm": 5}})
            fieldnames = [
                "event_id",
                "hit_id",
                "track_id",
                "parent_id",
                "is_primary_gamma",
                "gamma_source_type",
                "gamma_source_process",
                "gamma_source_region_id",
                "rayleigh_count",
                "det_x",
                "first_scatter_z",
                "last_scatter_z",
                "scatter_count_total",
            ]
            rows = [
                # Would match the zero-pose S1 range, but must be rejected after +5 mm shift.
                {"det_x": "10", "first_scatter_z": "1", "last_scatter_z": "1", "scatter_count_total": "1"},
                {"det_x": "15", "first_scatter_z": "1", "last_scatter_z": "1", "scatter_count_total": "1"},
                {"det_x": "35", "first_scatter_z": "1", "last_scatter_z": "1", "scatter_count_total": "2"},
                {"det_x": "36", "first_scatter_z": "-1", "last_scatter_z": "1", "scatter_count_total": "2"},
            ]
            with event_file.open("w", encoding="utf-8", newline="") as stream:
                writer = csv.DictWriter(stream, fieldnames=fieldnames)
                writer.writeheader()
                for index, row in enumerate(rows):
                    full_row = {field: "" for field in fieldnames}
                    full_row.update(
                        {
                            "event_id": str(index),
                            "hit_id": "0",
                            "track_id": "1",
                            "parent_id": "0",
                            "is_primary_gamma": "1",
                            "gamma_source_type": "primary",
                            "gamma_source_process": "primary_generator",
                            "gamma_source_region_id": "source",
                            "rayleigh_count": "0",
                        }
                    )
                    full_row.update(row)
                    writer.writerow(full_row)

            ranges = [
                clean_events.RangeSpec("S1", 10.0, 20.0),
                clean_events.RangeSpec("S2", 30.0, 40.0),
            ]
            summary = clean_events.clean_one_file(event_file, output_file, ranges, overwrite=True)

            self.assertEqual(4, summary["rows_read"])
            self.assertEqual(2, summary["rows_kept"])
            self.assertEqual(5.0, summary["head_offset_x_mm"])
            self.assertEqual(15.0, summary["S1_left_mm"])
            self.assertEqual(25.0, summary["S1_right_mm"])
            self.assertEqual(35.0, summary["S2_left_mm"])
            self.assertEqual(45.0, summary["S2_right_mm"])
            self.assertEqual(1, summary["S1_rows_kept"])
            self.assertEqual(1, summary["S2_rows_kept"])

            with output_file.open("r", encoding="utf-8", newline="") as stream:
                cleaned_rows = list(csv.DictReader(stream))
            self.assertEqual(["S1", "S2"], [row["slit_id"] for row in cleaned_rows])
            self.assertNotIn("event_id", cleaned_rows[0])
            self.assertNotIn("rayleigh_count", cleaned_rows[0])


if __name__ == "__main__":
    unittest.main()
