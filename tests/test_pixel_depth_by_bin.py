#!/usr/bin/env python3

from __future__ import annotations

import csv
import math
import sys
import tempfile
import unittest
from pathlib import Path

import yaml


REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "scripts"))

import analyze_pixel_depth_by_bin as pixel_depth  # noqa: E402


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8", newline="") as stream:
        return list(csv.DictReader(stream))


def read_yaml(path: Path):
    with path.open("r", encoding="utf-8") as stream:
        return yaml.safe_load(stream)


class PixelDepthByBinTests(unittest.TestCase):
    def write_geometry(self, root: Path) -> Path:
        path = root / "vehicle_roi.yaml"
        path.write_text(
            yaml.safe_dump(
                {
                    "components": [
                        {"name": "VehicleROI", "region_id": "vehicle_background_air"},
                        {"name": "target_insert", "region_id": {"normal": "cabin_air", "abnormal": "target"}},
                    ]
                },
                sort_keys=False,
            ),
            encoding="utf-8",
        )
        return path

    def write_run(
        self,
        root: Path,
        name: str,
        rows: list[dict[str, str]],
        *,
        include_region: bool = True,
        include_depth: bool = True,
        geometry_path: Path | None = None,
        actual_x_range: list[float] | None = None,
    ) -> Path:
        run_dir = root / name
        run_dir.mkdir(parents=True)
        metadata = {
            "run_id": name,
            "pose_id": "pose_x0_y0",
            "pose_index": 0,
            "head_offset_x_mm": 0,
            "head_offset_y_mm": 0,
            "model_type": "normal",
            "vehicle_geometry_file": geometry_path.as_posix() if geometry_path else "",
            "n_primary": 1000,
            "random_seed": 123,
            "source": {"mono_energy_keV": 160},
            "collimator": {"enable": True},
            "detector": {"actual_x_range_mm": actual_x_range or [0.0, 4.0]},
            "diagnostics": {"case_id": name},
        }
        (run_dir / "metadata.yaml").write_text(
            yaml.safe_dump(metadata, sort_keys=False),
            encoding="utf-8",
        )
        fieldnames = ["det_x", "scatter_count_total"]
        if include_depth:
            fieldnames.append("last_scatter_z")
        if include_region:
            fieldnames.append("last_scatter_region_id")
        with (run_dir / "events.csv").open("w", encoding="utf-8", newline="") as stream:
            writer = csv.DictWriter(stream, fieldnames=fieldnames)
            writer.writeheader()
            for row in rows:
                writer.writerow({field: row.get(field, "") for field in fieldnames})
        return run_dir

    def synthetic_rows(self) -> list[dict[str, str]]:
        rows: list[dict[str, str]] = []
        for bin_index in range(4):
            x = bin_index + 0.2
            base_depth = 10.0 + 10.0 * bin_index
            for depth in (base_depth - 1.0, base_depth, base_depth + 1.0):
                rows.append(
                    {
                        "det_x": str(x),
                        "scatter_count_total": "1",
                        "last_scatter_z": str(depth),
                        "last_scatter_region_id": "target",
                    }
                )
            for depth in (base_depth - 20.0, base_depth, base_depth + 20.0):
                rows.append(
                    {
                        "det_x": str(x + 0.1),
                        "scatter_count_total": "2",
                        "last_scatter_z": str(depth),
                        "last_scatter_region_id": "target",
                    }
                )
        rows.append(
            {
                "det_x": "4.0",
                "scatter_count_total": "0",
                "last_scatter_z": "NaN",
                "last_scatter_region_id": "none",
            }
        )
        return rows

    def test_depth_metrics_scatter_classes_and_right_edge_bin(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            geometry = self.write_geometry(root)
            run_dir = self.write_run(root, "run_a", self.synthetic_rows(), geometry_path=geometry)
            output_dir = root / "analysis"

            outputs = pixel_depth.analyze(
                [run_dir],
                output_dir,
                bin_width_mm=1.0,
                lags=[1, 2],
                min_bin_samples=2,
                min_valid_bins=3,
            )

            self.assertEqual(1, outputs["analyzed_run_count"])
            self.assertTrue(Path(outputs["manifest"]).exists())
            condition_dir = output_dir / "by_condition" / "collimated" / "pose_x0_y0" / "normal" / "E160"
            depth_path = condition_dir / "pixel_depth_summary_by_scatter_class" / "k1.csv"
            summary_k1_path = condition_dir / "scatter_order_spatial_summary" / "k1.csv"
            summary_km_path = condition_dir / "scatter_order_spatial_summary" / "km.csv"
            lag_path = condition_dir / "bin_lag_distribution_metrics" / "k1.csv"
            fraction_path = condition_dir / "pixel_scatter_class_fraction" / "fractions.csv"
            for path in (depth_path, summary_k1_path, summary_km_path, lag_path, fraction_path):
                self.assertTrue(path.exists(), path)

            depth_rows = read_csv(depth_path)
            k1_rows = [row for row in depth_rows if row["region_filter"] == "all_valid"]
            medians = [float(row["median"]) for row in k1_rows[:4]]
            self.assertEqual([10.0, 20.0, 30.0, 40.0], medians)
            self.assertFalse(any("|" in field for field in k1_rows[0].keys()))
            redundant = {
                "run_dir",
                "run_id",
                "case_id",
                "pose_id",
                "pose_index",
                "head_offset_x_mm",
                "head_offset_y_mm",
                "model_type",
                "selected_target_component",
                "abnormal_material",
                "collimator_enable",
                "n_primary",
                "scatter_class",
            }
            self.assertFalse(redundant.intersection(k1_rows[0].keys()))
            for field in ("pose", "seed", "energy_keV", "collimator", "abnormal_present", "insert_name", "insert_material"):
                self.assertIn(field, k1_rows[0])

            k1_summary = next(row for row in read_csv(summary_k1_path) if row["region_filter"] == "all_valid")
            km_summary = next(row for row in read_csv(summary_km_path) if row["region_filter"] == "all_valid")
            self.assertAlmostEqual(1.0, float(k1_summary["spearman_rho"]))
            self.assertGreater(float(km_summary["width_inflation_vs_k1"]), 1.0)
            self.assertFalse(math.isnan(float(km_summary["spatial_score_retention_vs_k1"])))

            lag_rows = read_csv(lag_path)
            self.assertTrue(any(row["lag"] == "1" for row in lag_rows))

            fraction_rows = read_csv(fraction_path)
            last_bin = next(
                row
                for row in fraction_rows
                if row["region_filter"] == "all_valid" and row["bin_index"] == "3"
            )
            self.assertEqual("1", last_bin["count_k0"])

            manifest = read_yaml(outputs["manifest"])
            self.assertEqual(1, manifest["discovered_run_count"])
            self.assertTrue(manifest["runs"][0]["vehicle_only_enabled"])
            self.assertIn("provenance", manifest["runs"][0])
            self.assertEqual("run_a", manifest["runs"][0]["provenance"]["case_id"])
            self.assertIn("pixel_depth_summary_by_scatter_class", manifest["outputs"])
            self.assertEqual("by_condition", manifest["output_layout"])
            file_paths = {
                item["path"] for item in manifest["outputs"]["pixel_depth_summary_by_scatter_class"]["files"]
            }
            self.assertIn(
                "by_condition/collimated/pose_x0_y0/normal/E160/pixel_depth_summary_by_scatter_class/k1.csv",
                file_paths,
            )

    def test_vehicle_filter_is_skipped_without_region_field(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            geometry = self.write_geometry(root)
            rows = [
                {
                    "det_x": "0.2",
                    "scatter_count_total": "1",
                    "last_scatter_z": "10",
                },
                {
                    "det_x": "1.2",
                    "scatter_count_total": "1",
                    "last_scatter_z": "20",
                },
            ]
            run_dir = self.write_run(root, "no_region", rows, include_region=False, geometry_path=geometry)
            outputs = pixel_depth.analyze(
                [run_dir],
                root / "analysis",
                bin_width_mm=1.0,
                lags=[1],
                min_bin_samples=1,
                min_valid_bins=2,
            )

            depth_filters = {
                row["region_filter"]
                for row in read_csv(
                    root
                    / "analysis"
                    / "by_condition"
                    / "collimated"
                    / "pose_x0_y0"
                    / "normal"
                    / "E160"
                    / "pixel_depth_summary_by_scatter_class"
                    / "k1.csv"
                )
            }
            self.assertEqual({"all_valid"}, depth_filters)
            manifest = read_yaml(outputs["manifest"])
            warnings = manifest["runs"][0]["warnings"]
            self.assertTrue(any("last_scatter_region_id" in warning for warning in warnings))

    def test_missing_core_field_skips_bad_run_but_keeps_good_run(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            geometry = self.write_geometry(root)
            good = self.write_run(root, "good", self.synthetic_rows(), geometry_path=geometry)
            self.write_run(
                root,
                "missing_depth",
                [{"det_x": "0.2", "scatter_count_total": "1", "last_scatter_region_id": "target"}],
                include_depth=False,
                geometry_path=geometry,
            )

            outputs = pixel_depth.analyze(
                [root],
                root / "analysis",
                bin_width_mm=1.0,
                lags=[1],
                min_bin_samples=2,
                min_valid_bins=3,
            )

            manifest = read_yaml(outputs["manifest"])
            self.assertEqual(2, manifest["discovered_run_count"])
            self.assertEqual(1, manifest["analyzed_run_count"])
            self.assertEqual(1, manifest["skipped_run_count"])
            self.assertIn(good.as_posix(), manifest["runs"][0]["run_dir"])
            self.assertIn("last_scatter_z", manifest["skipped_runs"][0]["reason"])


if __name__ == "__main__":
    unittest.main()
