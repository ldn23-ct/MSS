#!/usr/bin/env python3

from __future__ import annotations

import sys
import tempfile
import unittest
from contextlib import redirect_stderr
from io import StringIO
from pathlib import Path

import yaml


REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "scripts"))

import generate_article_experiment_configs as article  # noqa: E402


def load_yaml(path: Path):
    return yaml.safe_load(path.read_text(encoding="utf-8"))


class ArticleExperimentConfigTests(unittest.TestCase):
    def generate(self, output_dir: Path, **overrides):
        args = {
            "repo_root": REPO_ROOT,
            "base_config_path": REPO_ROOT / "config/base/simulation_config_v2.yaml",
            "phantom_dir": REPO_ROOT / "config/geometry/phantom_yaml_files",
            "output_dir": output_dir,
            "campaign_id": "unit",
            "experiments": ["E0"],
            "threads": 2,
            "e_star_kev": None,
            "e_star_metal_kev": None,
        }
        args.update(overrides)
        return article.generate(**args)

    def test_e0_generates_24_conditions_and_safe_yaml_fields(self):
        with tempfile.TemporaryDirectory() as tmp:
            output_dir = Path(tmp) / "article"
            manifest = self.generate(output_dir)

            self.assertEqual(24, len(manifest["cases"]))
            self.assertEqual(24, manifest["physical_condition_count"])
            self.assertEqual([60.0, 160.0, 260.0, 360.0, 460.0, 560.0], manifest["pmma_energies_keV"])
            self.assertEqual([60.0, 160.0, 260.0, 360.0, 460.0, 560.0], manifest["metal_energies_keV"])
            self.assertEqual({0, 1, 2, 3}, {case["defect_depth_id"] for case in manifest["cases"]})
            self.assertNotIn("slit_id", yaml.safe_dump(manifest))

            first_case = manifest["cases"][0]
            config = load_yaml(Path(first_case["config_file"]))
            self.assertEqual(90.0, config["source"]["incident_theta_deg"])
            self.assertEqual(5.0, config["source"]["focal_spot_diameter_mm"])
            self.assertEqual(2, config["run"]["number_of_threads"])
            self.assertEqual("fail", config["output"]["existing_run_policy"])
            self.assertTrue(config["collimator"]["enable"])
            self.assertEqual("normal", config["vehicle"]["model_type"])
            self.assertIsNone(config["vehicle"]["selected_target_component"])
            self.assertEqual(
                "config/geometry/phantom_yaml_files/P0.yaml",
                config["vehicle"]["geometry_file"],
            )
            self.assertFalse((output_dir / "geometries").exists())

    def test_grid_uses_fixed_nonuniform_offsets(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            manifest = self.generate(
                root / "e1",
                experiments=["E1"],
                e_star_kev=260.0,
            )

            expected_axis = [-24, -18, -15, -8, 0, 8, 15, 18, 24]
            expected_offsets = {(x, y) for x in expected_axis for y in expected_axis}
            self.assertEqual(4 * 81, len(manifest["cases"]))
            self.assertEqual("nonuniform_local_roi_sampling", manifest["grid"]["type"])
            self.assertEqual(expected_axis, manifest["grid"]["offsets_mm"])
            self.assertNotIn("step_mm", manifest["grid"])

            offsets = {
                (case["head_offset_x_mm"], case["head_offset_y_mm"])
                for case in manifest["cases"]
                if case["phantom_id"] == "P0"
            }
            self.assertEqual(expected_offsets, offsets)

    def test_e3_and_e4_counts(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            e3 = self.generate(root / "e3", experiments=["E3"])
            e4 = self.generate(
                root / "e4",
                experiments=["E4"],
                e_star_metal_kev=360.0,
            )

            self.assertEqual(4 * 6 * 2, len(e3["cases"]))
            self.assertEqual(4 * 81, len(e4["cases"]))
            self.assertEqual({"M0", "M1", "M2", "M3"}, {case["phantom_id"] for case in e3["cases"]})
            self.assertEqual({360.0}, {case["energy_keV"] for case in e4["cases"]})

    def test_custom_pmma_and_metal_energy_lists(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            e0 = self.generate(
                root / "e0_custom",
                experiments=["E0"],
                pmma_energies_kev=[80.0, 120.0],
            )
            e3 = self.generate(
                root / "e3_custom",
                experiments=["E3"],
                metal_energies_kev=[100.0, 200.0, 300.0],
            )

            self.assertEqual(4 * 2, len(e0["cases"]))
            self.assertEqual(4 * 3 * 2, len(e3["cases"]))
            self.assertEqual([80.0, 120.0], e0["pmma_energies_keV"])
            self.assertEqual([100.0, 200.0, 300.0], e3["metal_energies_keV"])
            self.assertEqual({80.0, 120.0}, {case["energy_keV"] for case in e0["cases"]})
            self.assertEqual({100.0, 200.0, 300.0}, {case["energy_keV"] for case in e3["cases"]})

    def test_batch_count_expands_cases_and_records_seed_parameters(self):
        with tempfile.TemporaryDirectory() as tmp:
            manifest = self.generate(
                Path(tmp) / "batched",
                experiments=["E0"],
                pmma_energies_kev=[80.0],
                batch_count=3,
                n_primary_per_pose=100,
                base_seed=9000,
            )

            self.assertEqual(4, manifest["physical_condition_count"])
            self.assertEqual(12, manifest["total_case_count"])
            self.assertEqual(3, manifest["batching"]["batch_count"])
            self.assertEqual(100, manifest["n_primary_per_pose"])
            first_three = manifest["cases"][:3]
            self.assertEqual([0, 1, 2], [case["batch_index"] for case in first_three])
            self.assertEqual([9000, 9001, 9002], [case["seed"] for case in first_three])
            self.assertEqual(
                ["E0_P0_E80_center", "E0_P0_E80_center", "E0_P0_E80_center"],
                [case["condition_id"] for case in first_three],
            )
            self.assertEqual({3}, {case["batch_count"] for case in manifest["cases"]})
            self.assertEqual({100}, {case["n_primary_per_pose"] for case in manifest["cases"]})
            self.assertEqual(
                {
                    "results/article/unit/runs/E0_P0_E80_center/b0",
                    "results/article/unit/runs/E0_P0_E80_center/b1",
                    "results/article/unit/runs/E0_P0_E80_center/b2",
                },
                {case["raw_output_directory"] for case in first_three},
            )
            self.assertEqual(
                {"results/article/unit/by_condition/E0/P0/E80/center"},
                {case["condition_output_directory"] for case in first_three},
            )

    def test_required_formal_parameters_fail_fast(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            with self.assertRaisesRegex(ValueError, "--threads is required"):
                self.generate(root / "missing_threads", threads=None)
            with self.assertRaisesRegex(ValueError, "E1 requires --e-star-kev"):
                self.generate(root / "missing_e_star", experiments=["E1"])
            with self.assertRaisesRegex(ValueError, "E4 requires --e-star-metal-kev"):
                self.generate(root / "missing_e_star_metal", experiments=["E4"])
            with self.assertRaisesRegex(ValueError, "pmma_energies_kev must contain positive values"):
                self.generate(root / "bad_pmma_energy", pmma_energies_kev=[80.0, -1.0])
            with self.assertRaisesRegex(ValueError, "metal_energies_kev must contain positive values"):
                self.generate(root / "bad_metal_energy", metal_energies_kev=[])

    def test_cli_energy_list_validation_fails_fast(self):
        bad_values = [
            ["--pmma-energies-kev", ""],
            ["--pmma-energies-kev", "80,-1"],
            ["--metal-energies-kev", "100,abc"],
        ]
        for args in bad_values:
            with self.subTest(args=args):
                with redirect_stderr(StringIO()):
                    with self.assertRaises(SystemExit):
                        article.parse_args(args)

    def test_canonical_geometry_is_referenced_without_campaign_copy(self):
        source_path = REPO_ROOT / "config/geometry/phantom_yaml_files/P1.yaml"
        with tempfile.TemporaryDirectory() as tmp:
            output_dir = Path(tmp) / "article"
            manifest = self.generate(output_dir)

            self.assertFalse((output_dir / "geometries").exists())
            self.assertEqual(
                "config/geometry/phantom_yaml_files/P1.yaml",
                manifest["phantoms"]["P1"]["geometry_file"],
            )
            self.assertEqual(
                "config/geometry/phantom_yaml_files/P1.yaml",
                manifest["phantoms"]["P1"]["source_geometry_file"],
            )
            canonical = load_yaml(source_path)
            components = canonical["components"]
            root = next(component for component in components if component["host"] == "World")
            defect = next(component for component in components if component["name"] == "D1_air_void")

            self.assertEqual("VehicleROI", canonical["roi"]["name"])
            self.assertEqual("VehicleROI", root["name"])
            self.assertEqual("VehicleROI", defect["host"])
            self.assertFalse(defect["is_insert"])
            self.assertEqual([], canonical["model_modes"]["abnormal"]["recommended_single_target_components"])


if __name__ == "__main__":
    unittest.main()
