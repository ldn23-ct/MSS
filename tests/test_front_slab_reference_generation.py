#!/usr/bin/env python3

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

import yaml

from scripts.monte_carlo import generate_front_slab_reference_configs as slab
from scripts.monte_carlo import run_experiment_queue as queue


REPO_ROOT = Path(__file__).resolve().parents[1]


def load_yaml(path: Path):
    return yaml.safe_load(path.read_text(encoding="utf-8"))


class FrontSlabReferenceGenerationTests(unittest.TestCase):
    def generate(self, output_dir: Path, **overrides):
        arguments = {
            "repo_root": REPO_ROOT,
            "base_config_path": REPO_ROOT / "config/base/article_base.yaml",
            "geometry_path": (
                REPO_ROOT / "config/geometry/article_files/P4_front_slab_55mm.yaml"
            ),
            "profile_file": (
                REPO_ROOT / "config/collimator/article_v2_collimator_profiles.csv"
            ),
            "output_dir": output_dir,
        }
        arguments.update(overrides)
        return slab.generate(**arguments)

    def test_geometry_is_exact_uniform_front_slab(self):
        path = REPO_ROOT / "config/geometry/article_files/P4_front_slab_55mm.yaml"
        geometry = slab.validate_reference_geometry(path)
        self.assertEqual("P4_front_slab_55mm", geometry["metadata"]["model_name"])
        self.assertEqual("uniform_pmma_front_slab", geometry["metadata"]["reference"]["type"])
        self.assertEqual(55.0, geometry["metadata"]["reference"]["thickness_mm"])
        self.assertIsNone(geometry["metadata"]["defect"])
        self.assertEqual([0.0, 0.0, 27.5], geometry["roi"]["center_mm"])
        self.assertEqual([1000.0, 1000.0, 55.0], geometry["roi"]["size_mm"])
        self.assertEqual("G4_PLEXIGLASS", geometry["roi"]["material"])
        self.assertEqual(1, len(geometry["components"]))
        self.assertFalse(geometry["components"][0]["is_insert"])
        self.assertEqual([0.0, 55.0], geometry["components"][0]["aabb_mm"]["z"])

    def test_generation_contract_is_81_pose_100m_and_seed_11000_to_11080(self):
        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp) / "generated"
            manifest = self.generate(output)
            reference = load_yaml(output / slab.REFERENCE_MANIFEST_NAME)
            self.assertEqual("front_slab_reference_simulation_campaign", manifest["experiment"])
            self.assertEqual(slab.DEFAULT_CAMPAIGN_ID, manifest["campaign_id"])
            self.assertEqual(81, manifest["summary"]["task_count"])
            self.assertEqual(81, manifest["summary"]["grid_config_count"])
            self.assertEqual(8_100_000_000, manifest["summary"]["total_primary"])
            self.assertEqual(11_000, manifest["summary"]["seed_start"])
            self.assertEqual(11_080, manifest["summary"]["seed_end"])
            self.assertEqual(
                list(range(11_000, 11_081)),
                [case["seed"] for case in manifest["cases"]],
            )
            self.assertEqual(
                [(x, y) for x in slab.GRID_OFFSETS_MM for y in slab.GRID_OFFSETS_MM],
                [
                    (case["head_offset_x_mm"], case["head_offset_y_mm"])
                    for case in manifest["cases"]
                ],
            )
            self.assertEqual("uniform_pmma_front_slab", reference["reference_type"])
            self.assertEqual(55.0, reference["thickness_mm"])
            self.assertEqual("P4_front_slab_55mm", reference["vehicle_model_id"])
            self.assertEqual("P001", reference["profile_id"])
            self.assertEqual("S4", reference["slit_id"])
            self.assertEqual(560.0, reference["energy_keV"])
            self.assertEqual(100_000_000, reference["n_primary_per_pose"])
            self.assertEqual(81, reference["pose_count"])

    def test_each_config_is_one_p001_pose_with_six_threads_and_fixed_output(self):
        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp) / "generated"
            manifest = self.generate(output)
            config_paths: set[str] = set()
            run_dirs: set[str] = set()
            for case in manifest["cases"]:
                config_path = Path(case["config_file"])
                config_paths.add(config_path.as_posix())
                config = load_yaml(config_path)
                self.assertEqual(
                    "config/geometry/article_files/P4_front_slab_55mm.yaml",
                    config["vehicle"]["geometry_file"],
                )
                self.assertEqual("P001", config["collimator"]["profile_id"])
                self.assertEqual([20.0, 127.0], config["detector"]["detector_x_range_zero_mm"])
                self.assertEqual(560.0, config["source"]["mono_energy_keV"])
                self.assertEqual(100_000_000, config["run"]["n_primary_per_pose"])
                self.assertEqual(6, config["run"]["number_of_threads"])
                self.assertEqual("list", config["pose"]["mode"])
                poses = queue.generate_poses(config)
                self.assertEqual(1, len(poses))
                self.assertEqual(case["pose_id"], poses[0]["pose_id"])
                expected = queue.expected_run_dirs(REPO_ROOT, config_path, config)
                self.assertEqual(1, len(expected))
                run_dirs.add(expected[0]["run_dir"])
                self.assertIn(
                    "results/articlev3_p4_front_slab_55mm_100m/events/raw/grid/"
                    "P4_front_slab_55mm/P001/",
                    expected[0]["run_dir"],
                )
            self.assertEqual(81, len(config_paths))
            self.assertEqual(81, len(run_dirs))

    def test_manifest_is_queue_compatible_and_splits_11_then_10_tasks(self):
        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp) / "generated"
            self.generate(output)
            items = queue.load_manifest_cases(REPO_ROOT, output / "manifest.yaml")
            self.assertEqual(81, len(items))
            shard_sizes = [
                len(queue.filter_items(items, None, None, 8, index, None))
                for index in range(8)
            ]
            self.assertEqual([11, 10, 10, 10, 10, 10, 10, 10], shard_sizes)

    def test_cli_defaults_and_overwrite_are_isolated_from_results(self):
        args = slab.parse_args([])
        self.assertEqual(slab.DEFAULT_CAMPAIGN_ID, args.campaign_id)
        self.assertEqual(100_000_000, args.n_primary_per_pose)
        self.assertEqual(6, args.threads)
        self.assertEqual(11_000, args.base_seed)
        self.assertEqual(
            REPO_ROOT / "config/generated" / slab.DEFAULT_CAMPAIGN_ID,
            args.output_dir,
        )

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            output = root / "generated"
            marker = root / "results" / "keep.txt"
            marker.parent.mkdir()
            marker.write_text("keep\n", encoding="utf-8")
            self.generate(output)
            (output / "manual.txt").write_text("replace\n", encoding="utf-8")
            manifest = self.generate(output, overwrite=True, threads=4)
            self.assertFalse((output / "manual.txt").exists())
            self.assertEqual({4}, {case["number_of_threads"] for case in manifest["cases"]})
            self.assertEqual("keep\n", marker.read_text(encoding="utf-8"))

    def test_invalid_geometry_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            geometry = load_yaml(
                REPO_ROOT / "config/geometry/article_files/P4_front_slab_55mm.yaml"
            )
            geometry["components"][0]["size_mm"][2] = 54.0
            path = root / "P4_front_slab_55mm.yaml"
            path.write_text(yaml.safe_dump(geometry, sort_keys=False), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "root size_mm"):
                slab.validate_reference_geometry(path)


if __name__ == "__main__":
    unittest.main()
