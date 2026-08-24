#!/usr/bin/env python3

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pandas as pd

from scripts.data_processing.common import PROFILE_SLITS, SLIT_WINDOWS_ZERO_MM
from scripts.postprocessing.e2 import run as analysis


def inventory_rows(grid_conditions: tuple[tuple[str, str], ...]) -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    center_conditions = {("P0", "P001"), ("P0", "P002")}
    center_conditions.update((f"P{i}", analysis.SLIT_PROFILE[f"S{i}"]) for i in range(1, 7))
    for phantom, profile in sorted(center_conditions):
        rows.append(
            {
                "key": f"center-{phantom}-{profile}",
                "scan_mode": "center",
                "phantom_id": phantom,
                "profile_id": profile,
                "head_offset_x_mm": 0.0,
                "head_offset_y_mm": 0.0,
                "status": "valid",
                "valid_file": f"center/{phantom}/{profile}/events_valid.csv",
            }
        )
    for phantom, profile in grid_conditions:
        for x in analysis.GRID_OFFSETS_MM:
            for y in analysis.GRID_OFFSETS_MM:
                rows.append(
                    {
                        "key": f"grid-{phantom}-{profile}-{x}-{y}",
                        "scan_mode": "grid",
                        "phantom_id": phantom,
                        "profile_id": profile,
                        "head_offset_x_mm": float(x),
                        "head_offset_y_mm": float(y),
                        "status": "valid",
                        "valid_file": f"grid/{phantom}/{profile}/{x}/{y}/events_valid.csv",
                    }
                )
    return pd.DataFrame(rows)


class FakeE2Context:
    def __init__(self, output_root: Path, grid_conditions: tuple[tuple[str, str], ...]):
        self.output_root = output_root
        self.results_root = output_root / "results"
        self.audit_dir = output_root / "audit"
        self.audit = {}
        self.warnings: list[str] = []
        self.inventory = inventory_rows(grid_conditions)

    def condition_rows(self, mode, phantom, profile):
        return self.inventory[
            (self.inventory.scan_mode == mode)
            & (self.inventory.phantom_id == phantom)
            & (self.inventory.profile_id == profile)
        ].copy()

    def center_row(self, phantom, profile):
        rows = self.condition_rows("center", phantom, profile)
        self.assert_one(rows)
        return rows.iloc[0]

    def summary_row(self, phantom, profile, summary_source):
        if summary_source == "center":
            return self.center_row(phantom, profile)
        if summary_source != "grid-zero":
            raise ValueError("invalid synthetic summary source")
        rows = self.condition_rows("grid", phantom, profile)
        rows = rows[
            np.isclose(rows.head_offset_x_mm.astype(float), 0)
            & np.isclose(rows.head_offset_y_mm.astype(float), 0)
        ]
        self.assert_one(rows)
        return rows.iloc[0]

    @staticmethod
    def assert_one(rows):
        if len(rows) != 1:
            raise ValueError("expected one synthetic center row")

    def metadata(self, row):
        return SimpleNamespace(
            profile_id=row.profile_id,
            phantom_id=row.phantom_id,
            scan_mode=row.scan_mode,
            head_offset_x_mm=float(row.head_offset_x_mm),
            head_offset_y_mm=float(row.head_offset_y_mm),
            metadata_path=Path(f"/{row.key}/metadata.yaml"),
        )

    def events(self, row, *, cache_center):
        records = []
        for slit in PROFILE_SLITS[row.profile_id]:
            window = SLIT_WINDOWS_ZERO_MM[slit]
            detector_x = (window.left_mm + window.right_mm) / 2 + float(row.head_offset_x_mm)
            detector_y = float(row.head_offset_y_mm)
            depths = (5.0, 15.0, 30.0, 45.0, 56.0, 58.0, 60.0, 70.0, 75.0, 90.0, 200.0)
            for scatter in (1, 2):
                for depth in depths:
                    records.append(
                        {
                            "det_x": detector_x,
                            "det_y": detector_y,
                            "scatter_count_total": scatter,
                            "first_scatter_z": depth,
                            "slit_group": row.profile_id,
                            "slit_label": slit,
                        }
                    )
        return pd.DataFrame(records)


class ArticleV2E2AnalysisTests(unittest.TestCase):
    def test_depth_region_and_dtv_contracts(self):
        self.assertEqual(2.0, analysis.DEFAULT_DEPTH_BIN_WIDTH_MM)
        self.assertEqual(110, len(analysis.depth_edges()) - 1)
        self.assertEqual([False, True, True, False], analysis.region_mask([54.9, 55, 64.9, 65], "Target").tolist())
        self.assertEqual([False, False, False, True], analysis.region_mask([54.9, 55, 64.9, 65], "Behind").tolist())
        self.assertTrue(np.allclose(np.diff(analysis.region_edges("Target")), 2.0))
        self.assertEqual(1.0, np.diff(analysis.region_edges("Front"))[-1])
        self.assertEqual(1.0, np.diff(analysis.region_edges("Behind"))[-1])
        self.assertAlmostEqual(
            0.0,
            analysis.within_region_tv(
                np.array([55.2, 57.2]), np.array([55.3, 57.3]), "Target", "scaled"
            ),
        )
        self.assertAlmostEqual(
            0.5,
            analysis.within_region_tv(
                np.array([55.2, 57.2]), np.array([55.2, 55.3]), "Target", "changed"
            ),
        )
        with self.assertRaisesRegex(ValueError, "histogram is empty"):
            analysis.within_region_tv(np.array([]), np.array([55.2]), "Target", "empty")
        with self.assertRaisesRegex(ValueError, "baseline count is zero"):
            analysis.relative_change(1, 0, "zero")
        edges, _, _, contributions = analysis.within_region_tv_contributions(
            np.array([55.2, 57.2]), np.array([55.2, 55.3]), "Target", "expanded"
        )
        self.assertAlmostEqual(0.5, contributions.sum())
        self.assertTrue(np.allclose(edges, analysis.region_edges("Target")))

        p2_range = analysis.case_target_range(analysis.E2Case("P0", "P2", "S2", "total"))
        self.assertEqual((25.0, 35.0), p2_range)
        self.assertEqual(
            [False, True, True, False],
            analysis.region_mask([24.9, 25.0, 34.9, 35.0], "Target", p2_range).tolist(),
        )
        self.assertEqual(1.0, np.diff(analysis.region_edges("Front", p2_range))[-1])
        self.assertEqual(1.0, np.diff(analysis.region_edges("Behind", p2_range))[-1])

    def test_custom_depth_bin_widths_cover_exact_ranges(self):
        expected_bins = {1.0: 220, 2.0: 110, 2.5: 88, 3.0: 74}
        for width, bin_count in expected_bins.items():
            with self.subTest(width=width):
                edges = analysis.depth_edges(width)
                self.assertEqual((0.0, 220.0), (edges[0], edges[-1]))
                self.assertEqual(bin_count, len(edges) - 1)
                self.assertTrue((np.diff(edges) > 0).all())
                self.assertTrue((np.diff(edges) <= width).all())
                for region in analysis.REGIONS:
                    region_values = analysis.region_edges(
                        region, (55.0, 65.0), width
                    )
                    self.assertTrue((np.diff(region_values) > 0).all())
                    self.assertTrue((np.diff(region_values) <= width).all())
        self.assertEqual(1.0, np.diff(analysis.depth_edges(3.0))[-1])
        self.assertEqual(1.0, np.diff(analysis.region_edges("Front", (55.0, 65.0), 3.0))[-1])

        frame = pd.DataFrame(
            {
                "scatter_count_total": [1, 1, 2, 2],
                "first_scatter_z": [0.0, 54.9, 65.0, 220.0],
            }
        )
        case = analysis.E2Case("P0", "P4", "S4", "total")
        edges, histograms = analysis._case_depth_histograms(
            {"baseline": frame, "defect": frame.copy()}, case, 3.0
        )
        self.assertEqual((0.0, 220.0), (edges[0], edges[-1]))
        self.assertEqual(4, int(histograms["baseline"].sum()))
        self.assertEqual(4, int(histograms["defect"].sum()))

        for invalid in (0, -1, np.nan, np.inf, 221):
            with self.subTest(invalid=invalid):
                with self.assertRaisesRegex(ValueError, "0 < width <= 220"):
                    analysis.validate_depth_bin_width(invalid)

    def test_case_parser_and_binwise_response(self):
        case = analysis.parse_case("P0:P4:S4:ms")
        self.assertEqual("P0-S4_vs_P4-S4_ms", case.selection_slug)
        self.assertEqual((analysis.DEFAULT_CASE,), analysis.normalize_cases(None))
        with self.assertRaisesRegex(ValueError, "duplicate"):
            analysis.normalize_cases([case, case])
        with self.assertRaisesRegex(Exception, "matched slit"):
            analysis.parse_case("P0:P4:S2:total")
        with self.assertRaisesRegex(Exception, "P1-P6"):
            analysis.parse_case("P0:P0:S1:total")

        response = analysis.binwise_relative_response(
            np.array([2, 3, 8]), np.array([1, 0, 4])
        )
        self.assertTrue(np.allclose(response[[0, 2]], [1.0, 1.0]))
        self.assertTrue(np.isnan(response[1]))
        thresholded = analysis.binwise_relative_response(
            np.array([2, 3, 8]), np.array([1, 2, 4]), min_baseline_count=3
        )
        self.assertTrue(np.isnan(thresholded[:2]).all())
        self.assertAlmostEqual(1.0, thresholded[2])
        with self.assertRaisesRegex(ValueError, "positive integer"):
            analysis.binwise_relative_response(
                np.array([1]), np.array([1]), min_baseline_count=0
            )

    def test_poisson_resampling_is_deterministic_and_preserves_partitions(self):
        case = analysis.E2Case("P0", "P4", "S4", "total")
        frame = pd.DataFrame(
            {
                "scatter_count_total": [1, 1, 2, 2, 2, 1],
                "first_scatter_z": [5.0, 56.0, 58.0, 70.0, 90.0, 200.0],
            }
        )
        frames = {"baseline": frame, "defect": frame.copy()}
        first = analysis.build_pair_resample(
            frames, case, np.random.default_rng(17), resample_count=120
        )
        second = analysis.build_pair_resample(
            frames, case, np.random.default_rng(17), resample_count=120
        )
        self.assertTrue(np.array_equal(first.sampled, second.sampled))
        _, sampled_total = analysis.pair_class_counts(first, "total")
        _, sampled_k1 = analysis.pair_class_counts(first, "k1")
        _, sampled_ms = analysis.pair_class_counts(first, "ms")
        self.assertTrue(np.array_equal(sampled_total, sampled_k1 + sampled_ms))
        rows = analysis.source_fraction_rows(first)
        table = pd.DataFrame(rows)
        sums = table.groupby(
            ["condition_role", "scatter_class"], sort=False
        ).fraction.sum()
        self.assertTrue(np.allclose(sums, 1.0))
        values = analysis.sampled_ratio(
            np.array([1, 2, 3]), np.array([1, 0, 2]), relative_change_value=False
        )
        self.assertEqual(2, analysis.finite_interval(values, "ratio")[2])
        low, high, count = analysis.finite_interval(
            np.array([np.nan, np.nan]), "undefined", allow_empty=True
        )
        self.assertTrue(np.isnan(low) and np.isnan(high))
        self.assertEqual(0, count)

    def test_empty_defect_region_reports_undefined_dtv_without_fabrication(self):
        baseline = pd.DataFrame(
            {
                "scatter_count_total": [1, 2, 1, 2, 1, 2],
                "first_scatter_z": [10.0, 10.0, 60.0, 60.0, 100.0, 100.0],
            }
        )
        defect = pd.DataFrame(
            {
                "scatter_count_total": [1, 2, 1, 1, 2],
                "first_scatter_z": [10.0, 10.0, 60.0, 100.0, 100.0],
            }
        )
        case = analysis.E2Case("P0", "P4", "S4", "total")
        pair = analysis.build_pair_resample(
            {"baseline": baseline, "defect": defect},
            case,
            np.random.default_rng(9),
            resample_count=50,
        )
        table = pd.DataFrame(
            analysis.source_region_rows(pair, analysis.DEFAULT_DEPTH_BIN_WIDTH_MM)
        )
        target_ms = table[
            table.scatter_class.eq("ms") & table.region.eq("Target")
        ].iloc[0]
        self.assertEqual(-1.0, target_ms.C_r)
        self.assertTrue(np.isnan(target_ms.D_TV_r))
        self.assertEqual(0, target_ms.D_TV_r_n_effective)

    def test_grid_readiness_partial_and_full(self):
        partial = FakeE2Context(Path("/tmp/fake"), (("P0", "P001"), ("P2", "P001")))
        readiness = analysis.grid_readiness(partial)
        self.assertFalse(readiness["complete"])
        self.assertEqual(["P2-S2"], readiness["complete_pairs"])
        full = FakeE2Context(Path("/tmp/fake"), analysis.expected_grid_conditions())
        readiness = analysis.grid_readiness(full)
        self.assertTrue(readiness["complete"])
        self.assertEqual([f"P{i}-S{i}" for i in range(1, 7)], readiness["complete_pairs"])
        self.assertEqual(0, readiness["missing_pose_count"])

    def test_partial_pipeline_publishes_exact_contract(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            context = FakeE2Context(root, (("P0", "P001"), ("P2", "P001")))
            summary = analysis.run_e2(
                context, allow_partial_grid=True, resample_count=120
            )
            self.assertEqual("partial", summary["publication_status"])
            analysis.write_report(root, summary, [])
            acceptance = analysis.validate_generated_outputs(root, summary)
            self.assertEqual("partial", acceptance["overall_status"])
            self.assertEqual(set(summary["expected_figure_names"]), {path.name for path in (root / "figures").iterdir()})
            self.assertEqual(set(summary["expected_table_names"]), {path.name for path in (root / "tables").iterdir()})
            center = pd.read_csv(root / "tables" / analysis.T1_TABLE_NAME)
            regions = pd.read_csv(root / "tables" / analysis.t2_table_name(analysis.DEFAULT_CASE))
            fractions = pd.read_csv(root / "tables" / analysis.T3_TABLE_NAME)
            self.assertEqual(analysis.T1_COLUMNS, tuple(center.columns))
            self.assertEqual(analysis.T2_COLUMNS, tuple(regions.columns))
            self.assertEqual(analysis.T3_COLUMNS, tuple(fractions.columns))
            self.assertEqual((18, 9, 108), (len(center), len(regions), len(fractions)))
            self.assertEqual((3, 3), (len(summary["expected_figure_names"]), len(summary["expected_table_names"])))
            self.assertTrue(center.C_n_effective.between(1, 120).all())
            self.assertTrue(regions.C_r_n_effective.between(1, 120).all())
            self.assertTrue(regions.D_TV_r_n_effective.between(1, 120).all())
            self.assertTrue(fractions.fraction_n_effective.between(1, 120).all())
            self.assertFalse(any("E2-F4" in path.name for path in (root / "figures").iterdir()))
            self.assertFalse(any(path.suffix == ".pdf" for path in root.rglob("*")))

    def test_grid_zero_summary_uses_source_specific_names_and_rows(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            context = FakeE2Context(root, analysis.expected_grid_conditions())
            summary = analysis.run_e2(
                context,
                allow_partial_grid=False,
                summary_source="grid-zero",
                resample_count=80,
            )
            self.assertEqual("grid-zero", summary["summary_source"])
            self.assertIn(
                analysis.ZERO_POSE_T1_TABLE_NAME, summary["expected_table_names"]
            )
            self.assertIn(
                analysis.ZERO_POSE_T3_TABLE_NAME, summary["expected_table_names"]
            )
            self.assertNotIn(analysis.T1_TABLE_NAME, summary["expected_table_names"])
            acceptance = analysis.validate_generated_outputs(root, summary)
            self.assertEqual("pass", acceptance["overall_status"])

    def test_summary_source_validation_and_missing_zero_pose(self):
        with self.assertRaisesRegex(ValueError, "summary_source"):
            analysis.summary_table_names("invalid")
        context = analysis.AnalysisContext(
            Path("/tmp/fake"),
            Path("/tmp/fake/audit"),
            Path("/tmp/fake/output"),
            inventory_rows((("P0", "P001"),)),
            {},
        )
        with self.assertRaisesRegex(ValueError, "zero-pose grid"):
            context.summary_row("P4", "P001", "grid-zero")

    def test_multi_case_outputs_are_distinct_and_t2_is_deduplicated(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            context = FakeE2Context(root, (("P0", "P001"), ("P2", "P001")))
            cases = (
                analysis.E2Case("P0", "P4", "S4", "total"),
                analysis.E2Case("P0", "P4", "S4", "ms"),
                analysis.E2Case("P0", "P2", "S2", "k1"),
            )
            summary = analysis.run_e2(
                context,
                allow_partial_grid=True,
                cases=cases,
                min_baseline_count=2,
                depth_bin_width_mm=2.5,
                resample_count=120,
            )
            self.assertEqual(2.5, summary["depth_bin_width_mm"])
            self.assertEqual(7, len(summary["expected_figure_names"]))
            self.assertEqual(4, len(summary["expected_table_names"]))
            self.assertEqual(len(cases), len(summary["case_results"]))
            self.assertEqual(
                set(summary["expected_figure_names"]),
                {path.name for path in (root / "figures").iterdir()},
            )
            self.assertEqual(
                set(summary["expected_table_names"]),
                {path.name for path in (root / "tables").iterdir()},
            )
            self.assertEqual(
                1,
                sum("P0-S4_vs_P4-S4_source_region" in name for name in summary["expected_table_names"]),
            )
            self.assertFalse(any("E2-F4" in name for name in summary["expected_figure_names"]))

    def test_strict_pipeline_rejects_missing_grid_before_publication(self):
        with tempfile.TemporaryDirectory() as tmp:
            context = FakeE2Context(Path(tmp), (("P0", "P001"), ("P2", "P001")))
            with self.assertRaisesRegex(ValueError, "--allow-partial-grid"):
                analysis.run_e2(context, allow_partial_grid=False)

    def test_grid_image_uses_y_rows_and_x_columns(self):
        rows = inventory_rows((("P0", "P001"),))
        rows = rows[rows.scan_mode == "grid"].copy()

        class GridContext(FakeE2Context):
            def events(self, row, *, cache_center):
                x_index = list(analysis.GRID_OFFSETS_MM).index(float(row.head_offset_x_mm))
                y_index = list(analysis.GRID_OFFSETS_MM).index(float(row.head_offset_y_mm))
                count = y_index * 9 + x_index + 1
                window = SLIT_WINDOWS_ZERO_MM["S2"]
                return pd.DataFrame(
                    {
                        "det_x": [(window.left_mm + window.right_mm) / 2 + float(row.head_offset_x_mm)] * count,
                        "det_y": [float(row.head_offset_y_mm)] * count,
                        "scatter_count_total": [1] * count,
                        "first_scatter_z": [30.0] * count,
                        "slit_group": ["P001"] * count,
                        "slit_label": ["S2"] * count,
                    }
                )

        context = GridContext(Path("/tmp/fake"), (("P0", "P001"),))
        image = analysis._grid_image(context, rows, "S2")
        self.assertEqual((1, 9, 73, 81), (image[0, 0], image[0, 8], image[8, 0], image[8, 8]))

    def test_atomic_publish_removes_obsolete_case_outputs(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            existing = root / "E2"
            (existing / "figures").mkdir(parents=True)
            (existing / "figures/old_fixed_case.png").write_bytes(b"old")
            staging = root / "staging"
            (staging / "figures").mkdir(parents=True)
            (staging / "figures/new_dynamic_case.png").write_bytes(b"new")
            analysis.publish(staging, existing, overwrite=True)
            self.assertFalse((existing / "figures/old_fixed_case.png").exists())
            self.assertEqual(b"new", (existing / "figures/new_dynamic_case.png").read_bytes())


if __name__ == "__main__":
    unittest.main()
