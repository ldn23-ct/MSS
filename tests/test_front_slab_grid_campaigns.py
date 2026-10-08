#!/usr/bin/env python3

from __future__ import annotations

import copy
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import yaml

from scripts.monte_carlo import generate_front_slab_grid_campaigns as batch
from scripts.monte_carlo import generate_front_slab_reference_configs as slab
from scripts.monte_carlo import run_experiment_queue as queue


REPO_ROOT = Path(__file__).resolve().parents[1]
EXPECTED = (
    ("P1", 10, "P002", "S1", 12000, 12080),
    ("P2", 25, "P001", "S2", 12081, 12161),
    ("P3", 40, "P002", "S3", 12162, 12242),
    ("P5", 70, "P002", "S5", 12243, 12323),
    ("P6", 85, "P001", "S6", 12324, 12404),
)


class FrontSlabGridCampaignTests(unittest.TestCase):
    def test_all_geometries_match_their_phantom_defect_front(self):
        for phantom, thickness, profile, slit, _, _ in EXPECTED:
            with self.subTest(phantom=phantom):
                geometry = slab.validate_reference_geometry(
                    REPO_ROOT / f"config/geometry/article_files/{phantom}_front_slab_{thickness}mm.yaml"
                )
                self.assertEqual([0.0, 0.0, thickness / 2], geometry["roi"]["center_mm"])
                self.assertEqual([1000.0, 1000.0, thickness], geometry["roi"]["size_mm"])
                self.assertEqual([0.0, thickness], geometry["components"][0]["aabb_mm"]["z"])
                self.assertIsNone(geometry["metadata"]["defect"])
                self.assertEqual(1, len(geometry["components"]))
                reference = geometry["metadata"]["reference"]
                self.assertEqual((profile, slit), (reference["matched_profile"], reference["matched_slit"]))

    def test_405_pose_contract_and_frozen_physics_are_queue_compatible(self):
        with tempfile.TemporaryDirectory() as tmp:
            manifests = batch.generate_campaigns(REPO_ROOT, Path(tmp))
            seeds, outputs, configs = set(), set(), set()
            total_primary = 0
            for manifest, (phantom, thickness, profile, slit, first, last) in zip(manifests, EXPECTED):
                identifier = f"articlev3_{phantom.lower()}_front_slab_{thickness}mm_100m"
                model = f"{phantom}_front_slab_{thickness}mm"
                self.assertEqual(identifier, manifest["campaign_id"])
                self.assertEqual("config/base/front_slab_grid_base.yaml", manifest["base_config"])
                self.assertEqual(81, manifest["summary"]["task_count"])
                self.assertEqual(8_100_000_000, manifest["summary"]["total_primary"])
                total_primary += manifest["summary"]["total_primary"]
                self.assertEqual(list(range(first, last + 1)), [case["seed"] for case in manifest["cases"]])
                self.assertEqual(
                    {(x, y) for x in (-10, -7.5, -5, -2.5, 0, 2.5, 5, 7.5, 10)
                     for y in (-10, -7.5, -5, -2.5, 0, 2.5, 5, 7.5, 10)},
                    {(case["head_offset_x_mm"], case["head_offset_y_mm"]) for case in manifest["cases"]},
                )
                reference = slab.load_yaml(Path(tmp) / identifier / "reference_manifest.yaml")
                self.assertEqual((model, thickness, profile, slit), (
                    reference["vehicle_model_id"], reference["thickness_mm"],
                    reference["profile_id"], reference["slit_id"],
                ))
                self.assertEqual((first, last), (reference["seed_start"], reference["seed_end"]))
                items = queue.load_manifest_cases(REPO_ROOT, Path(tmp) / identifier / "manifest.yaml")
                self.assertEqual(81, len(items))
                for case, item in zip(manifest["cases"], items):
                    config_path = Path(case["config_file"])
                    config = slab.load_yaml(config_path)
                    configs.add(config_path)
                    self.assertEqual("list", config["pose"]["mode"])
                    self.assertEqual(1, len(queue.generate_poses(config)))
                    self.assertEqual(7, config["run"]["number_of_threads"])
                    self.assertEqual(100_000_000, config["run"]["n_primary_per_pose"])
                    self.assertEqual(case["seed"], config["run"]["random_seed"])
                    self.assertEqual([0.0, 0.0, -20.0], config["source"]["source_pos_zero_mm"])
                    self.assertEqual("gamma", config["source"]["particle"])
                    self.assertEqual("mono", config["source"]["energy_mode"])
                    self.assertEqual(560.0, config["source"]["mono_energy_keV"])
                    self.assertEqual(5.0, config["source"]["focal_spot_diameter_mm"])
                    self.assertEqual(90.0, config["source"]["incident_theta_deg"])
                    self.assertEqual(1300.0, config["collimator"]["jaw_extrusion_length_y_mm"])
                    self.assertEqual(profile, config["collimator"]["profile_id"])
                    self.assertEqual([20.0, 127.0] if profile == "P001" else [11.0, 101.0],
                                     config["detector"]["detector_x_range_zero_mm"])
                    self.assertEqual(-73.0, config["detector"]["detector_z_zero_mm"])
                    self.assertEqual([-100.0, 100.0], config["detector"]["detector_y_range_zero_mm"])
                    self.assertEqual({"physics_list": "G4EmLivermorePhysics", "production_cut_mm": 0.1},
                                     config["physics"])
                    self.assertEqual("fail", config["output"]["existing_run_policy"])
                    self.assertEqual(f"config/geometry/article_files/{model}.yaml", config["vehicle"]["geometry_file"])
                    self.assertEqual(f"results/{identifier}/events/raw/grid/{model}/{profile}",
                                     config["output"]["output_directory"])
                    self.assertEqual(1, len(item["expected_runs"]))
                    seeds.add(case["seed"])
                    outputs.add(item["expected_run_dir"])
            self.assertEqual(5, len(manifests))
            self.assertEqual(40_500_000_000, total_primary)
            self.assertEqual(set(range(12000, 12405)), seeds)
            self.assertEqual(405, len(outputs))
            self.assertEqual(405, len(configs))

    def test_destination_preflight_prevents_partial_batch_and_silent_overwrite(self):
        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp) / "generated"
            occupied = output / "articlev3_p6_front_slab_85mm_100m"
            occupied.mkdir(parents=True)
            marker = occupied / "keep.txt"
            marker.write_text("keep", encoding="utf-8")
            with self.assertRaises(FileExistsError):
                batch.generate_campaigns(REPO_ROOT, output)
            self.assertEqual([occupied], list(output.iterdir()))
            self.assertEqual("keep", marker.read_text())
            manifests = batch.generate_campaigns(REPO_ROOT, output, overwrite=True)
            before = (output / manifests[0]["campaign_id"] / "manifest.yaml").read_bytes()
            with self.assertRaises(FileExistsError):
                batch.generate_campaigns(REPO_ROOT, output)
            self.assertEqual(before, (output / manifests[0]["campaign_id"] / "manifest.yaml").read_bytes())

    def test_invalid_reference_fields_and_mismatched_defect_front_are_rejected(self):
        original = slab.load_yaml(REPO_ROOT / "config/geometry/article_files/P1_front_slab_10mm.yaml")
        mutations = (
            (("metadata", "reference", "matched_profile"), "P001"),
            (("metadata", "reference", "matched_slit"), "S2"),
            (("metadata", "reference", "thickness_mm"), float("nan")),
            (("metadata", "defect"), {"id": "D1"}),
            (("roi", "bounds_mm", "x"), [-499, 500]),
            (("components", 0, "half_size_mm"), [500, 500, 4]),
            (("components", 0, "placement_center_in_host_mm"), [0, 0, 4]),
            (("components", 0, "is_insert"), True),
        )
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "P1_front_slab_10mm.yaml"
            for keys, value in mutations:
                with self.subTest(field=keys):
                    geometry = copy.deepcopy(original)
                    node = geometry
                    for key in keys[:-1]:
                        node = node[key]
                    node[keys[-1]] = value
                    path.write_text(yaml.safe_dump(geometry), encoding="utf-8")
                    with self.assertRaises(ValueError):
                        slab.validate_reference_geometry(path)
            path.write_text(yaml.safe_dump(original), encoding="utf-8")
            phantom = slab.load_yaml(REPO_ROOT / "config/geometry/article_files/P1.yaml")
            phantom["metadata"]["defect"]["z_range_mm"] = [11, 21]
            phantom["metadata"]["defect"]["center_mm"][2] = 16
            (path.parent / "P1.yaml").write_text(yaml.safe_dump(phantom), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "thickness must match P1 defect front"):
                slab.validate_reference_geometry(path)

    def test_five_workers_keep_independent_state_and_resume_only_failed_pose(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            manifests = batch.generate_campaigns(REPO_ROOT, root / "generated")
            arguments = []
            failed_case = manifests[2]["cases"][1]["case_id"]
            attempts = []
            fail_once = True

            def fake_run(binary, repo_root, item, log_path):
                nonlocal fail_once
                attempts.append(item["case_id"])
                expected = item["expected_runs"][0]
                run_dir = Path(expected["run_dir"])
                run_dir.mkdir(parents=True)
                Path(expected["csv"]).write_text("event_id\n0\n", encoding="utf-8")
                log_path.write_text(item["case_id"], encoding="utf-8")
                if item["case_id"] == failed_case and fail_once:
                    fail_once = False
                    return 7
                Path(expected["metadata"]).write_text(yaml.safe_dump({
                    "run_id": expected["run_id"], "n_primary": expected["n_primary"],
                }), encoding="utf-8")
                return 0

            for manifest in manifests:
                identifier = manifest["campaign_id"]
                for case in manifest["cases"][:2]:
                    config_path = Path(case["config_file"])
                    config = slab.load_yaml(config_path)
                    config["output"]["output_directory"] = str(root / "runs" / identifier)
                    config_path.write_text(yaml.safe_dump(config), encoding="utf-8")
                arguments.append(queue.parse_args([
                    "--manifest", str(root / "generated" / identifier / "manifest.yaml"),
                    "--state-file", str(root / "queues" / identifier / "state.json"),
                    "--log-dir", str(root / "queues" / identifier / "logs"),
                    "--limit", "2", "--allow-large-run",
                ]))
            with patch.object(queue, "run_item_process", side_effect=fake_run):
                for index, args in enumerate(arguments):
                    self.assertEqual(7 if index == 2 else 0, queue.run_queue(args))
                states = [json.loads(args.state_file.read_text()) for args in arguments]
                self.assertEqual(5, len({item["items"][0]["expected_run_dir"] for item in states}))
                failed_run = Path(states[2]["items"][1]["expected_run_dir"])
                self.assertFalse(queue.item_complete(states[2]["items"][1]))
                failed_run.rename(root / "quarantined_failed_pose")
                for args in arguments:
                    self.assertEqual(0, queue.run_queue(args))
            self.assertEqual(11, len(attempts))
            self.assertEqual(2, attempts.count(failed_case))
            for args in arguments:
                state = json.loads(args.state_file.read_text())
                self.assertTrue(all(queue.item_complete(item) for item in state["items"]))
                self.assertFalse(args.state_file.with_suffix(".json.lock").exists())


if __name__ == "__main__":
    unittest.main()
