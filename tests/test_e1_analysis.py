#!/usr/bin/env python3

from __future__ import annotations

import tempfile
import unittest
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pandas as pd

from scripts.postprocessing.e1 import run as analysis


class FakeE1Context:
    def __init__(self, output_root: Path):
        self.output_root = output_root
        self.results_root = output_root / "results"
        self.warnings: list[str] = []
        self.profiles: dict[str, pd.DataFrame] = {}
        for profile, slits in analysis.PROFILE_SLITS.items():
            rows = []
            for slit in slits:
                region = next(
                    item
                    for item in analysis.acceptance_regions_for_profile(profile)
                    if item.slit_id == slit
                )
                detector_x = (region.x_min_mm + region.x_max_mm) / 2
                depth = analysis.SLIT_DESIGN_DEPTH_MM[slit]
                for scatter, delta in ((1, -1.0), (2, 1.0), (3, 3.0)):
                    rows.append(
                        {
                            "det_x": detector_x,
                            "det_y": float(scatter),
                            "scatter_count_total": scatter,
                            "first_scatter_x": float(scatter),
                            "first_scatter_y": float(-scatter),
                            "first_scatter_z": depth + delta,
                            "last_scatter_x": float(scatter * 4),
                            "last_scatter_y": float(-scatter * 5),
                            "last_scatter_z": depth + delta + 10,
                            "slit_group": profile,
                            "slit_label": slit,
                        }
                    )
            self.profiles[profile] = pd.DataFrame(rows)

    def run_row(self, mode, phantom, profile, x=0, y=0):
        return profile

    def valid_events(self, row):
        return self.profiles[row].copy()

    def valid_event_path(self, row):
        return self.results_root / f"events/valid/{row}/events_valid.csv"

    def valid_metadata(self, row):
        x_range = [20, 127] if row == "P001" else [11, 101]
        return SimpleNamespace(
            scan_mode="center",
            phantom_id="P0",
            profile_id=row,
            head_offset_x_mm=0,
            head_offset_y_mm=0,
            metadata_path=Path(f"/valid/{row}/metadata.yaml"),
            raw={
                "detector": {
                    "actual_x_range_mm": x_range,
                    "actual_y_range_mm": [-100, 100],
                }
            },
        )


class ArticleV2E1AnalysisTests(unittest.TestCase):
    def test_depth_and_spatial_view_contracts(self):
        self.assertEqual((0.0, 220.0), analysis.E1_DEPTH_RANGE_MM)
        self.assertEqual(2.0, analysis.E1_DEPTH_BIN_WIDTH_MM)
        self.assertEqual(110, len(analysis.depth_edges()) - 1)
        self.assertTrue(np.allclose(np.diff(analysis.depth_edges()), 2.0))
        self.assertTrue(
            np.allclose(
                analysis.padded_quantile_range(np.array([0.0, 10.0]), (0.0, 1.0)),
                (-0.3, 10.3),
            )
        )
        self.assertEqual((0.005, 0.995), analysis.validate_quantile((0.005, 0.995)))
        with self.assertRaisesRegex(ValueError, "0 <= LOW"):
            analysis.validate_quantile((0.9, 0.1))
        with self.assertRaisesRegex(ValueError, "LOW < HIGH"):
            analysis.validate_limit("x", (1.0, 1.0))

    def test_e1_three_figure_contract_and_statistics(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            context = FakeE1Context(root)
            console = StringIO()
            with redirect_stdout(console):
                summary = analysis.run_e1(
                    context,
                    spatial_xlim=(0.0, 5.0),
                    spatial_ylim=(-5.0, 0.0),
                    spatial_zlim=(0.0, 100.0),
                )
            analysis.write_report(root, summary, [])
            acceptance = analysis.validate_generated_outputs(root, summary)
            self.assertEqual("pass", acceptance["overall_status"])
            self.assertEqual(18, summary["all_valid_event_count"])
            self.assertEqual({slit: 3 for slit in analysis.SLIT_IDS}, summary["roi_total_counts"])
            self.assertTrue(
                all(np.isclose(value, 1.0) for value in summary["profile_normalized_sums"].values())
            )
            self.assertEqual(
                {"P002": ["S1", "S3", "S5"], "P001": ["S2", "S4", "S6"]},
                summary["acquisition_groups"],
            )
            for profile_id in ("P002", "P001"):
                self.assertEqual(
                    [0.0, 5.0], summary["spatial_view_ranges_mm"][profile_id]["x_mm"]
                )
                self.assertEqual(
                    [-5.0, 0.0], summary["spatial_view_ranges_mm"][profile_id]["y_mm"]
                )
                self.assertEqual(
                    [0.0, 100.0], summary["spatial_view_ranges_mm"][profile_id]["z_mm"]
                )
                self.assertEqual(9, summary["spatial_profile_event_counts"][profile_id])
                self.assertTrue(
                    all(
                        value == 9
                        for value in summary["spatial_point_counts"][profile_id].values()
                    )
                )
            self.assertIn("outside displayed view", console.getvalue())
            self.assertFalse((root / "tables").exists())
            self.assertEqual(
                set(analysis.FIGURE_NAMES),
                {path.name for path in (root / "figures").iterdir()},
            )
            self.assertFalse(any(path.suffix == ".pdf" for path in root.rglob("*")))

    def test_e1_f3_uses_independent_group_quantile_ranges(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            context = FakeE1Context(root)
            with redirect_stdout(StringIO()):
                summary = analysis.run_e1(context)
            ranges = summary["spatial_view_ranges_mm"]
            self.assertNotEqual(ranges["P002"]["z_mm"], ranges["P001"]["z_mm"])
            self.assertEqual(
                {"P002": 9, "P001": 9}, summary["spatial_profile_event_counts"]
            )
            self.assertEqual(
                {"first_xz", "last_xz", "first_yz", "last_yz"},
                set(summary["spatial_outside_view_counts"]["P002"]),
            )

    def test_roi_requires_recorded_label_and_closed_boundaries(self):
        first = analysis.acceptance_regions_for_profile("P002")[0]
        frame = pd.DataFrame(
            {
                "det_x": [first.x_min_mm, first.x_max_mm, first.x_min_mm, first.x_min_mm - 0.01],
                "det_y": [first.y_min_mm, first.y_max_mm, 0, 0],
                "slit_label": [first.slit_id, first.slit_id, "S3", first.slit_id],
            }
        )
        self.assertEqual(
            [True, True, False, False], analysis.e1_roi_mask(frame, first).tolist()
        )

    def test_scatter_validation_and_classes(self):
        frame = pd.DataFrame({"scatter_count_total": [0, 1, 2, 5]})
        self.assertEqual(3, int(analysis.class_mask(frame, "total").sum()))
        self.assertEqual(1, int(analysis.class_mask(frame, "k1").sum()))
        self.assertEqual(2, int(analysis.class_mask(frame, "ms").sum()))
        for invalid in (-1, 1.5, np.nan):
            with self.subTest(invalid=invalid):
                with self.assertRaisesRegex(ValueError, "finite non-negative integers"):
                    analysis.scatter_counts(pd.DataFrame({"scatter_count_total": [invalid]}))

    def test_output_protection_and_auxiliary_preservation(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            existing = root / "E1"
            (existing / "roi_sensitivity").mkdir(parents=True)
            (existing / "archive").mkdir()
            (existing / "tables").mkdir()
            (existing / "roi_sensitivity/metrics.csv").write_text("x\n1\n", encoding="utf-8")
            (existing / "archive/old.pdf").write_bytes(b"old")
            (existing / "tables/obsolete.csv").write_text("old\n", encoding="utf-8")
            staging = root / "staging"
            staging.mkdir()
            (staging / "report.md").write_text("new", encoding="utf-8")
            analysis.publish(staging, existing, overwrite=True)
            self.assertEqual("new", (existing / "report.md").read_text(encoding="utf-8"))
            self.assertTrue((existing / "roi_sensitivity/metrics.csv").is_file())
            self.assertTrue((existing / "archive/old.pdf").is_file())
            self.assertFalse((existing / "tables").exists())


if __name__ == "__main__":
    unittest.main()
