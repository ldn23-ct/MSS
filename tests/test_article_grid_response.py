#!/usr/bin/env python3

from __future__ import annotations

import csv
import math
import sys
import tempfile
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "scripts/article"))

import plot_grid_response as grid_response  # noqa: E402
from clean_events import RangeSpec  # noqa: E402


class ArticleGridResponseTests(unittest.TestCase):
    ranges = [RangeSpec("S1", 0.0, 1.0), RangeSpec("S2", 2.0, 3.0)]

    def write_events(
        self,
        path: Path,
        rows: list[dict[str, str]],
        fieldnames: list[str],
    ) -> None:
        with path.open("w", encoding="utf-8", newline="") as stream:
            writer = csv.DictWriter(stream, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(rows)

    def run_info(self, root: Path) -> grid_response.RunInfo:
        return grid_response.RunInfo(
            run_dir=root,
            events_path=root / "events_clean.csv",
            metadata_path=root / "metadata.yaml",
            experiment="E1",
            phantom_id="P3",
            energy_keV=460.0,
            energy_token="E460",
            pose="grid_x0_y0",
            head_offset_x_mm=0.0,
            head_offset_y_mm=0.0,
            n_primary=1000,
        )

    def test_closed_first_scatter_z_filter_precedes_response_counts(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            event_file = root / "events_clean.csv"
            rows = [
                {"slit_id": "S1", "scatter_count_total": "1", "first_scatter_z": "139.9"},
                {"slit_id": "S1", "scatter_count_total": "1", "first_scatter_z": "140"},
                {"slit_id": "S1", "scatter_count_total": "2", "first_scatter_z": "150"},
                {"slit_id": "S1", "scatter_count_total": "3", "first_scatter_z": "170"},
                {"slit_id": "S1", "scatter_count_total": "1", "first_scatter_z": "170.1"},
                {"slit_id": "S1", "scatter_count_total": "1", "first_scatter_z": "NaN"},
                {"slit_id": "S1", "scatter_count_total": "1", "first_scatter_z": "bad"},
                {"slit_id": "S2", "scatter_count_total": "1", "first_scatter_z": "155"},
            ]
            self.write_events(
                event_file, rows, ["slit_id", "scatter_count_total", "first_scatter_z"]
            )

            frame = grid_response.load_events(event_file, self.ranges, (140.0, 170.0))
            response = grid_response.aggregate_run(self.run_info(root), frame, self.ranges)
            s1 = next(row for row in response if row["slit_id"] == "S1")
            s2 = next(row for row in response if row["slit_id"] == "S2")

            self.assertEqual((3, 1, 1, 2, 1), (
                s1["N_total"], s1["N_k1"], s1["N_k2"], s1["N_ms"], s1["N_without_ms"]
            ))
            self.assertAlmostEqual(2.0 / 3.0, s1["F_ms"])
            self.assertEqual(1, s2["N_total"])
            self.assertEqual(1000, s1["n_primary"])

    def test_filter_disabled_preserves_inputs_without_first_scatter_z(self):
        with tempfile.TemporaryDirectory() as tmp:
            event_file = Path(tmp) / "events_clean.csv"
            self.write_events(
                event_file,
                [{"slit_id": "S1", "scatter_count_total": "1"}],
                ["slit_id", "scatter_count_total"],
            )
            frame = grid_response.load_events(event_file, self.ranges)
            self.assertEqual(1, len(frame))

    def test_filter_requires_column_and_valid_closed_bounds(self):
        with tempfile.TemporaryDirectory() as tmp:
            event_file = Path(tmp) / "events_clean.csv"
            self.write_events(
                event_file,
                [{"slit_id": "S1", "scatter_count_total": "1"}],
                ["slit_id", "scatter_count_total"],
            )
            with self.assertRaisesRegex(ValueError, "missing first_scatter_z"):
                grid_response.load_events(event_file, self.ranges, (140.0, 170.0))

        self.assertIsNone(grid_response.validate_first_scatter_z_range(None))
        self.assertEqual(
            (140.0, 170.0), grid_response.validate_first_scatter_z_range([140.0, 170.0])
        )
        self.assertEqual(
            (140.0, 140.0), grid_response.validate_first_scatter_z_range([140.0, 140.0])
        )
        with self.assertRaisesRegex(ValueError, "MIN_MM <= MAX_MM"):
            grid_response.validate_first_scatter_z_range([170.0, 140.0])
        for invalid in ([math.nan, 170.0], [140.0, math.inf]):
            with self.assertRaisesRegex(ValueError, "must be finite"):
                grid_response.validate_first_scatter_z_range(invalid)

    def test_filter_manifest_records_enabled_and_disabled_semantics(self):
        enabled = grid_response.first_scatter_z_filter_manifest((140.0, 170.0))
        disabled = grid_response.first_scatter_z_filter_manifest(None)
        self.assertEqual(
            {
                "enabled": True,
                "min_mm": 140.0,
                "max_mm": 170.0,
                "interval_rule": "closed: min_mm <= first_scatter_z <= max_mm",
            },
            enabled,
        )
        self.assertFalse(disabled["enabled"])
        self.assertIsNone(disabled["min_mm"])
        self.assertIsNone(disabled["max_mm"])


if __name__ == "__main__":
    unittest.main()
