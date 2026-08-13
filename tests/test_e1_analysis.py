#!/usr/bin/env python3

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pandas as pd


REPO_ROOT = Path(__file__).resolve().parents[1]

from scripts.postprocessing.e1 import run as analysis


class ArticleV2AnalysisPipelineTests(unittest.TestCase):
    def test_e1_depth_bins_and_design_depths(self):
        self.assertEqual((0.0, 220.0), analysis.E1_DEPTH_RANGE_MM)
        self.assertEqual((2.0, 4.0), analysis.E1_BIN_WIDTHS_MM)
        self.assertEqual(110, len(analysis.e1_depth_edges(2.0)) - 1)
        self.assertEqual(55, len(analysis.e1_depth_edges(4.0)) - 1)
        self.assertTrue(np.allclose(np.diff(analysis.e1_depth_edges(2.0)), 2.0))
        self.assertTrue(np.allclose(np.diff(analysis.e1_depth_edges(4.0)), 4.0))
        self.assertEqual(
            {f"S{index}": float(index * 15) for index in range(1, 7)},
            analysis.SLIT_DESIGN_DEPTH_MM,
        )

    def test_e1_valid_label_roi_outputs_and_statistics(self):
        class FakeContext:
            def __init__(self, output_root: Path):
                self.output_root = output_root
                self.results_root = output_root / "results"
                self.warnings = []
                self.profiles = {}
                for profile, slits in analysis.PROFILE_SLITS.items():
                    rows = []
                    for slit in slits:
                        region = next(
                            item for item in analysis.acceptance_regions_for_profile(profile)
                            if item.slit_id == slit
                        )
                        own_x = (region.x_min_mm + region.x_max_mm) / 2
                        other = next(item for item in analysis.acceptance_regions_for_profile(profile)
                                     if item.slit_id != slit)
                        other_x = (other.x_min_mm + other.x_max_mm) / 2
                        depth = analysis.SLIT_DESIGN_DEPTH_MM[slit]
                        rows.extend([
                            {"det_x": own_x, "det_y": 0, "scatter_count_total": 0,
                             "first_scatter_z": 1.0, "slit_group": profile, "slit_label": slit},
                            {"det_x": own_x, "det_y": 0, "scatter_count_total": 1,
                             "first_scatter_z": depth - 5.0, "slit_group": profile, "slit_label": slit},
                            {"det_x": own_x, "det_y": 0, "scatter_count_total": 2,
                             "first_scatter_z": depth + 5.0, "slit_group": profile, "slit_label": slit},
                            {"det_x": own_x, "det_y": 0, "scatter_count_total": 2,
                             "first_scatter_z": depth + 4.999, "slit_group": profile, "slit_label": slit},
                            {"det_x": other_x, "det_y": 0, "scatter_count_total": 1,
                             "first_scatter_z": depth, "slit_group": profile, "slit_label": slit},
                            {"det_x": own_x, "det_y": 0, "scatter_count_total": 1,
                             "first_scatter_z": 221.0, "slit_group": profile, "slit_label": slit},
                        ])
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
                    scan_mode="center", phantom_id="P0", profile_id=row,
                    head_offset_x_mm=0, head_offset_y_mm=0,
                    metadata_path=Path(f"/valid/{row}/metadata.yaml"),
                    raw={"detector": {
                        "actual_x_range_mm": x_range,
                        "actual_y_range_mm": [-100, 100],
                    }},
                )

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            analysis.run_e1(FakeContext(root))
            counts = pd.read_csv(root / "tables/E1_event_counts.csv")
            profiles_2mm = pd.read_csv(root / "tables/E1_depth_profiles_2mm.csv")
            profiles_4mm = pd.read_csv(root / "tables/E1_depth_profiles_4mm.csv")
            peaks = pd.read_csv(root / "tables/E1_peak_summary.csv")
            fractions = pd.read_csv(root / "tables/E1_design_depth_fraction.csv")
            comparison = pd.read_csv(root / "tables/E1_binning_comparison.csv")
            self.assertEqual(6, len(counts))
            self.assertTrue((counts.total_count == 4).all())
            self.assertTrue((counts.k1_count == 2).all())
            self.assertTrue((counts.ms_count == 2).all())
            self.assertTrue(np.allclose(counts.k1_fraction, .5))
            self.assertTrue(np.allclose(counts.ms_fraction, .5))
            self.assertEqual((1980, 990), (len(profiles_2mm), len(profiles_4mm)))
            self.assertEqual((36, 18, 18), (len(peaks), len(fractions), len(comparison)))
            for profiles in (profiles_2mm, profiles_4mm):
                sums = profiles.groupby(["slit", "scatter_class"]).normalized_count.sum()
                self.assertTrue(np.allclose(sums, 1.0))
                zero = profiles.raw_count == 0
                self.assertTrue(profiles.loc[zero, "relative_poisson_error"].isna().all())
                self.assertTrue(np.allclose(profiles.poisson_sigma, np.sqrt(profiles.raw_count)))
            sample = fractions[(fractions.slit == "S1") & (fractions.scatter_class == "k1")].iloc[0]
            self.assertEqual((10.0, 20.0, 1, 2), (
                sample.region_left_mm, sample.region_right_mm,
                sample.region_count, sample.class_total_count,
            ))
            self.assertAlmostEqual(.5, sample.region_fraction)
            analysis.write_report(root, [])
            acceptance = analysis.validate_generated_outputs(root)
            self.assertEqual("pass", acceptance["overall_status"])
            self.assertTrue((root / "report.md").is_file())
            expected_figures = {
                "E1_detector_plane_distribution.png",
                "E1_depth_response_2mm.png",
                "E1_depth_response_4mm.png",
            }
            self.assertEqual(expected_figures, {path.name for path in (root / "figures").iterdir()})

        for column, value, message in (
            ("slit_group", "P002", "slit_group must equal profile P001"),
            ("slit_label", "S1", "slit_label must be one of"),
        ):
            with self.subTest(column=column), tempfile.TemporaryDirectory() as tmp:
                context = FakeContext(Path(tmp))
                context.profiles["P001"].loc[0, column] = value
                with self.assertRaisesRegex(ValueError, message):
                    analysis.run_e1(context)

    def test_e1_roi_requires_existing_label_and_closed_boundaries(self):
        regions = analysis.acceptance_regions_for_profile("P002")
        first = regions[0]
        frame = pd.DataFrame({
            "det_x": [first.x_min_mm, first.x_max_mm, first.x_min_mm, first.x_min_mm - .01],
            "det_y": [first.y_min_mm, first.y_max_mm, 0, 0],
            "slit_label": [first.slit_id, first.slit_id, "S3", first.slit_id],
        })
        self.assertEqual([True, True, False, False], analysis.e1_roi_mask(frame, first).tolist())

    def test_e1_scatter_validation_and_peak_tie_rule(self):
        frame = pd.DataFrame({"scatter_count_total": [0, 1, 3]})
        self.assertEqual([0, 1, 3], analysis.e1_scatter_counts(frame).tolist())
        for invalid in (-1, 1.5, np.nan):
            with self.subTest(invalid=invalid):
                with self.assertRaisesRegex(ValueError, "finite non-negative integers"):
                    analysis.e1_scatter_counts(pd.DataFrame({"scatter_count_total": [invalid]}))
        self.assertEqual(
            1.0,
            analysis.e1_peak_depth(np.array([1., 3., 5.]), np.array([4, 4, 1])),
        )

    def test_e1_valid_reader_rejects_missing_and_nonnumeric_columns(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            context = analysis.AnalysisContext(root, root, root / "out", pd.DataFrame(), {})
            row = SimpleNamespace(valid_file="events_valid.csv")
            pd.DataFrame({"det_x": [1]}).to_csv(root / row.valid_file, index=False)
            with self.assertRaisesRegex(ValueError, "missing required E1 columns"):
                context.valid_events(row)
            pd.DataFrame({
                "det_x": ["bad"], "det_y": [0], "scatter_count_total": [1],
                "first_scatter_z": [1], "slit_group": ["P001"], "slit_label": ["S2"],
            }).to_csv(root / row.valid_file, index=False)
            context._valid_cache.clear()
            with self.assertRaises(ValueError):
                context.valid_events(row)

    def test_event_classes_partition_total(self):
        frame = pd.DataFrame({"scatter_count_total": [0, 1, 2, 5]})
        self.assertEqual(3, int(analysis.class_mask(frame, "total").sum()))
        self.assertEqual(1, int(analysis.class_mask(frame, "k1").sum()))
        self.assertEqual(2, int(analysis.class_mask(frame, "ms").sum()))

    def test_output_protection_and_auxiliary_preservation(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            existing = root / "E1"
            (existing / "roi_sensitivity").mkdir(parents=True)
            (existing / "roi_sensitivity/metrics.csv").write_text("x\n1\n", encoding="utf-8")
            with self.assertRaises(FileExistsError):
                analysis.main(["--results-root", str(root), "--output-dir", str(existing)])

            staging = root / "staging"
            staging.mkdir()
            (staging / "report.md").write_text("new", encoding="utf-8")
            analysis.publish(staging, existing, overwrite=True)
            self.assertEqual("new", (existing / "report.md").read_text(encoding="utf-8"))
            self.assertTrue((existing / "roi_sensitivity/metrics.csv").is_file())

if __name__ == "__main__":
    unittest.main()
