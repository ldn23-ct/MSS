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

import plot_scatter_position_histogram as histogram  # noqa: E402


FIELDS = [
    "slit_id",
    "scatter_count_total",
    "first_scatter_x",
    "first_scatter_y",
    "first_scatter_z",
    "last_scatter_x",
    "last_scatter_y",
    "last_scatter_z",
]


class ArticleScatterPositionHistogramTests(unittest.TestCase):
    def write_run(
        self,
        root: Path,
        seed: int,
        rows: list[dict[str, str]],
        *,
        phantom_id: str = "P0",
        n_primary: int = 100,
        pose_id: str = "pose_x0_y0",
        fieldnames: list[str] | None = None,
    ) -> Path:
        run_dir = root / f"seed{seed}" / f"run_seed{seed}"
        run_dir.mkdir(parents=True)
        metadata = {
            "vehicle_model_id": phantom_id,
            "vehicle_geometry_file": f"config/geometry/{phantom_id}.yaml",
            "model_type": "normal",
            "selected_target_component": None,
            "abnormal_material": None,
            "pose_id": pose_id,
            "head_offset_x_mm": 0,
            "head_offset_y_mm": 0,
            "random_seed": seed,
            "n_primary": n_primary,
            "source": {"mono_energy_keV": 460},
            "collimator": {"enable": True},
            "detector": {"actual_x_range_mm": [9, 146]},
            "physics": {"physics_list": "G4EmLivermorePhysics"},
            "case_id": f"article_E1_{phantom_id}_E460_grid_x0_y0_seed{seed}",
        }
        (run_dir / "metadata.yaml").write_text(
            yaml.safe_dump(metadata, sort_keys=False), encoding="utf-8"
        )
        columns = fieldnames or FIELDS
        with (run_dir / "events_clean.csv").open("w", encoding="utf-8", newline="") as stream:
            writer = csv.DictWriter(stream, fieldnames=columns)
            writer.writeheader()
            for row in rows:
                writer.writerow({field: row.get(field, "") for field in columns})
        return run_dir

    def write_merged(
        self,
        root: Path,
        rows: list[dict[str, str]],
        *,
        phantom_id: str = "P0",
        n_primary: int = 300,
        pose: str = "grid_x0_y0",
        seeds: list[int] | None = None,
    ) -> Path:
        root.mkdir(parents=True, exist_ok=True)
        metadata = {
            "schema_version": 1,
            "merged_article_batches": True,
            "run_id": f"E1_{phantom_id}_E460_{pose}",
            "condition": {
                "condition_id": f"article_E1_{phantom_id}_E460_{pose}",
                "experiment": "E1",
                "phantom_id": phantom_id,
                "geometry_file": f"config/geometry/{phantom_id}.yaml",
                "defect_depth_id": 0,
                "energy_keV": 460,
                "pose": pose,
                "head_offset_x_mm": 0,
                "head_offset_y_mm": 0,
            },
            "n_primary": n_primary,
            "source": {"mono_energy_keV": 460},
            "collimator": {"enable": True},
            "detector": {"actual_x_range_mm": [9, 146]},
            "physics": {"physics_list": "G4EmLivermorePhysics"},
            "merge": {"seeds": seeds or [101, 102, 103]},
        }
        (root / "metadata.yaml").write_text(
            yaml.safe_dump(metadata, sort_keys=False), encoding="utf-8"
        )
        with (root / "events_clean.csv").open("w", encoding="utf-8", newline="") as stream:
            writer = csv.DictWriter(stream, fieldnames=FIELDS)
            writer.writeheader()
            writer.writerows(rows)
        return root

    def row(self, slit: str, scatter: str, z: str, *, first_x: str = "0", last_x: str = "0") -> dict[str, str]:
        return {
            "slit_id": slit,
            "scatter_count_total": scatter,
            "first_scatter_x": first_x,
            "first_scatter_y": "0",
            "first_scatter_z": z,
            "last_scatter_x": last_x,
            "last_scatter_y": "0",
            "last_scatter_z": z,
        }

    def test_input_aggregation_slit_filter_exclusions_and_final_right_edge(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.write_run(
                root,
                11,
                [
                    self.row("S1", "0", "1"),
                    self.row("S1", "1", "0"),
                    self.row("S2", "2", "2"),
                    self.row("S2", "1", "4"),
                    self.row("S1", "1", "-1"),
                    self.row("S2", "1", "5"),
                    self.row("S3", "1", "1"),
                ],
            )
            self.write_run(
                root,
                12,
                [self.row("S1", "1", "1"), self.row("S2", "2", "3"), self.row("S3", "1", "2")],
            )

            analysis = histogram.build_analysis(
                root,
                "P0",
                "first",
                "z",
                ("S1", "S2"),
                0.0,
                2.0,
                4.0,
            )

            self.assertEqual([2, 3], [row["count_total"] for row in analysis["rows"]])
            self.assertEqual([2, 1], [row["count_k1"] for row in analysis["rows"]])
            self.assertEqual([0, 2], [row["count_ms"] for row in analysis["rows"]])
            for row in analysis["rows"]:
                self.assertEqual(row["count_total"], row["count_k1"] + row["count_ms"])
            self.assertEqual(4.0, analysis["rows"][-1]["bin_right_mm"])
            first_run = analysis["run_results"][0]
            self.assertEqual(
                first_run["binned_count"],
                first_run["binned_k1_count"] + first_run["binned_ms_count"],
            )
            self.assertEqual(1, first_run["zero_scatter_excluded"])
            self.assertEqual(1, first_run["underflow"])
            self.assertEqual(1, first_run["overflow"])
            self.assertEqual(200, analysis["n_primary_total"])

    def test_auto_range_and_coordinate_selection(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.write_run(
                root,
                21,
                [self.row("S1", "1", "1", first_x="1", last_x="5")],
            )
            self.write_run(
                root,
                22,
                [self.row("S1", "1", "1", first_x="2", last_x="4")],
            )
            analysis = histogram.build_analysis(
                root, "P0", "last", "x", ("S1",), 0.0, 3.0
            )
            self.assertEqual("last_scatter_x", analysis["coordinate_field"])
            self.assertEqual(6.0, analysis["bin_spec"].end_mm)
            self.assertEqual([0, 2], [row["count_total"] for row in analysis["rows"]])

    def test_condition_counts_exact_csv_schema_and_manifest(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.write_run(
                root,
                23,
                [self.row("S2", "1", "1"), self.row("S2", "2", "1")],
            )
            analysis = histogram.build_analysis(
                root, "P0", "first", "z", ("S2",), 0.0, 2.0, 2.0
            )
            row = analysis["rows"][0]
            self.assertEqual(
                (2, 1, 1),
                (row["count_total"], row["count_k1"], row["count_ms"]),
            )

            output_dir = root / "output"
            output_dir.mkdir()
            csv_path = output_dir / histogram.HISTOGRAM_CSV_NAME
            manifest_path = output_dir / histogram.MANIFEST_NAME
            plot_path = output_dir / histogram.HISTOGRAM_PNG_NAME
            histogram.write_histogram_csv(csv_path, analysis["rows"])
            histogram.write_manifest(manifest_path, analysis, csv_path, plot_path)

            with csv_path.open("r", encoding="utf-8", newline="") as stream:
                reader = csv.DictReader(stream)
                written = next(reader)
                self.assertEqual(list(histogram.CSV_FIELDS), reader.fieldnames)
            self.assertEqual("1", written["count_k1"])
            self.assertEqual("1", written["count_ms"])
            self.assertNotIn("seed_count", written)
            self.assertNotIn("mean_count_per_seed", written)
            manifest = yaml.safe_load(manifest_path.read_text(encoding="utf-8"))
            self.assertEqual("condition_total", manifest["aggregation"]["mode"])
            self.assertNotIn("seed_aggregation", manifest)
            self.assertEqual("total = k1 + ms", manifest["count_classes"]["invariant"])
            self.assertEqual(1, manifest["inputs"][0]["binned_k1_count"])
            self.assertEqual(1, manifest["inputs"][0]["binned_ms_count"])

    def test_merged_metadata_without_top_level_vehicle_or_seed_is_supported(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.write_merged(
                root,
                [self.row("S3", "1", "1"), self.row("S3", "2", "3")],
                phantom_id="P3",
                n_primary=600,
                seeds=[1256, 1257],
            )
            analysis = histogram.build_analysis(
                root, "P3", "first", "z", ("S3",), 0.0, 2.0, 4.0
            )
            self.assertEqual("article_E1_P3_E460_grid_x0_y0", analysis["condition_id"])
            self.assertEqual(600, analysis["n_primary_total"])
            self.assertEqual([1, 1], [row["count_total"] for row in analysis["rows"]])
            self.assertEqual((1256, 1257), analysis["runs"][0].seeds)

    def test_missing_column_and_unknown_slit_fail_fast(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.write_run(
                root,
                31,
                [{"slit_id": "S1", "scatter_count_total": "1"}],
                fieldnames=["slit_id", "scatter_count_total"],
            )
            with self.assertRaisesRegex(ValueError, "missing required columns"):
                histogram.build_analysis(root, "P0", "first", "z", ("S1",), 0.0, 2.0)

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.write_run(root, 32, [self.row("S4", "1", "1")])
            with self.assertRaisesRegex(ValueError, "must be one of"):
                histogram.build_analysis(root, "P0", "first", "z", ("S1",), 0.0, 2.0)

    def test_different_primary_counts_sum_and_condition_mismatch_fails_fast(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.write_run(root, 44, [self.row("S1", "1", "1")], n_primary=100)
            self.write_run(root, 45, [self.row("S1", "1", "1")], n_primary=200)
            analysis = histogram.build_analysis(
                root, "P0", "first", "z", ("S1",), 0.0, 2.0, 2.0
            )
            self.assertEqual(300, analysis["n_primary_total"])
            self.assertEqual(2, analysis["rows"][0]["count_total"])

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.write_run(root, 42, [self.row("S1", "1", "1")])
            self.write_run(root, 43, [self.row("S1", "1", "1")], pose_id="pose_x1_y0")
            with self.assertRaisesRegex(ValueError, "one physical condition"):
                histogram.select_runs(root, "P0")

    def test_invalid_parameters_and_output_overwrite(self):
        with self.assertRaises(ValueError):
            histogram.parse_slits("S1,S1")
        with self.assertRaises(ValueError):
            histogram.coordinate_field("middle", "z")
        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp) / "output"
            histogram.ensure_output_dir(output, overwrite=False)
            (output / histogram.HISTOGRAM_CSV_NAME).write_text("existing", encoding="utf-8")
            with self.assertRaises(FileExistsError):
                histogram.ensure_output_dir(output, overwrite=False)
            histogram.ensure_output_dir(output, overwrite=True)


if __name__ == "__main__":
    unittest.main()
