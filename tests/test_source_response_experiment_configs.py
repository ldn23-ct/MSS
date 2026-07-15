#!/usr/bin/env python3

from __future__ import annotations

import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path

import yaml


REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "scripts"))

import generate_source_response_experiment_configs as source_response  # noqa: E402
import run_experiment_queue as experiment_queue  # noqa: E402


def load_yaml(path: Path):
    return yaml.safe_load(path.read_text(encoding="utf-8"))


class SourceResponseExperimentConfigTests(unittest.TestCase):
    def generate(self, output_dir: Path, **overrides):
        args = {
            "repo_root": REPO_ROOT,
            "base_config_path": REPO_ROOT / "config/base/article_base.yaml",
            "geometry_dir": REPO_ROOT / "config/geometry/article_files",
            "profile_file": (
                REPO_ROOT / "config/collimator/article_v2_collimator_profiles.csv"
            ),
            "output_dir": output_dir,
        }
        args.update(overrides)
        return source_response.generate(**args)

    def test_default_campaign_generates_expected_conditions_and_scale(self):
        with tempfile.TemporaryDirectory() as tmp:
            output_dir = Path(tmp) / "generated"
            manifest = self.generate(output_dir)

            self.assertEqual("articlev2", manifest["campaign_id"])
            self.assertEqual("one_pose_per_config", manifest["task_granularity"])
            self.assertEqual(21, manifest["summary"]["physical_condition_count"])
            self.assertEqual(341, manifest["summary"]["config_count"])
            self.assertEqual(341, manifest["summary"]["task_count"])
            self.assertEqual(17, manifest["summary"]["center_config_count"])
            self.assertEqual(4, manifest["summary"]["grid_condition_count"])
            self.assertEqual(324, manifest["summary"]["grid_config_count"])
            self.assertEqual(341, manifest["summary"]["total_pose_runs"])
            self.assertEqual(
                341 * source_response.DEFAULT_N_PRIMARY_PER_POSE,
                manifest["summary"]["total_primary"],
            )
            self.assertEqual(1234, manifest["summary"]["seed_start"])
            self.assertEqual(1574, manifest["summary"]["seed_end"])
            self.assertEqual(341, len(manifest["cases"]))

            center = [case for case in manifest["cases"] if case["scan_mode"] == "center"]
            grid = [case for case in manifest["cases"] if case["scan_mode"] == "grid"]
            self.assertEqual(
                {
                    (phantom, profile)
                    for phantom in source_response.STANDARD_PHANTOM_IDS
                    for profile in ("P001", "P002")
                }
                | {(phantom, "P001") for phantom in ("P7", "P8", "P9")},
                {(case["phantom_id"], case["profile_id"]) for case in center},
            )
            self.assertEqual(
                {(phantom, "P001") for phantom in ("P0", "P2", "P4", "P6")},
                {(case["phantom_id"], case["profile_id"]) for case in grid},
            )
            self.assertEqual({1}, {case["pose_count"] for case in center})
            self.assertEqual({1}, {case["pose_count"] for case in grid})
            self.assertEqual(
                {"one_pose_per_config"},
                {case["task_granularity"] for case in manifest["cases"]},
            )
            self.assertTrue(
                all(
                    case["output_directory"].startswith("results/articlev2/runs/")
                    for case in manifest["cases"]
                )
            )

    def test_profiles_grid_offsets_and_generated_yaml_are_exact(self):
        with tempfile.TemporaryDirectory() as tmp:
            output_dir = Path(tmp) / "generated"
            manifest = self.generate(output_dir)

            p001 = next(
                case
                for case in manifest["cases"]
                if (case["scan_mode"], case["phantom_id"], case["profile_id"])
                == ("center", "P0", "P001")
            )
            p002 = next(
                case
                for case in manifest["cases"]
                if (case["scan_mode"], case["phantom_id"], case["profile_id"])
                == ("center", "P0", "P002")
            )
            grid = next(
                case
                for case in manifest["cases"]
                if case["scan_mode"] == "grid"
                and case["phantom_id"] == "P4"
                and case["pose_id"] == "pose_xm7p5_y2p5"
            )

            p001_config = load_yaml(Path(p001["config_file"]))
            p002_config = load_yaml(Path(p002["config_file"]))
            grid_config = load_yaml(Path(grid["config_file"]))

            self.assertEqual(["S2", "S4", "S6"], p001["slit_ids"])
            self.assertEqual([20.0, 127.0], p001_config["detector"]["detector_x_range_zero_mm"])
            self.assertEqual(["S1", "S3", "S5"], p002["slit_ids"])
            self.assertEqual([11.0, 101.0], p002_config["detector"]["detector_x_range_zero_mm"])
            self.assertEqual("config/geometry/article_files/P4.yaml", grid_config["vehicle"]["geometry_file"])
            self.assertEqual("P001", grid_config["collimator"]["profile_id"])
            self.assertEqual("list", grid_config["pose"]["mode"])
            self.assertEqual([-7.5], grid_config["pose"]["list"]["head_offset_x_mm"])
            self.assertEqual([2.5], grid_config["pose"]["list"]["head_offset_y_mm"])
            self.assertEqual([], grid_config["pose"]["grid"]["x_offsets_mm"])
            self.assertEqual([], grid_config["pose"]["grid"]["y_offsets_mm"])
            poses = experiment_queue.generate_poses(grid_config)
            self.assertEqual(1, len(poses))
            self.assertEqual("pose_xm7p5_y2p5", poses[0]["pose_id"])
            self.assertTrue(
                str(grid["config_file"]).endswith(
                    "configs/grid/P4_P001/pose_xm7p5_y2p5.yaml"
                )
            )
            self.assertEqual(560.0, grid_config["source"]["mono_energy_keV"])
            self.assertEqual(
                source_response.DEFAULT_N_PRIMARY_PER_POSE,
                grid_config["run"]["n_primary_per_pose"],
            )
            self.assertEqual(8, grid_config["run"]["number_of_threads"])

    def test_each_grid_condition_expands_to_exact_81_pose_cartesian_product(self):
        with tempfile.TemporaryDirectory() as tmp:
            manifest = self.generate(Path(tmp) / "generated")
            expected_pairs = [
                (x_mm, y_mm)
                for x_mm in source_response.GRID_OFFSETS_MM
                for y_mm in source_response.GRID_OFFSETS_MM
            ]
            expected_seed_ranges = {
                "P0": range(1248, 1329),
                "P2": range(1329, 1410),
                "P4": range(1410, 1491),
                "P6": range(1491, 1572),
            }

            for phantom_id, expected_seeds in expected_seed_ranges.items():
                cases = [
                    case
                    for case in manifest["cases"]
                    if case["scan_mode"] == "grid" and case["phantom_id"] == phantom_id
                ]
                self.assertEqual(81, len(cases))
                self.assertEqual(list(range(81)), [case["pose_index"] for case in cases])
                self.assertEqual(
                    expected_pairs,
                    [
                        (case["head_offset_x_mm"], case["head_offset_y_mm"])
                        for case in cases
                    ],
                )
                self.assertEqual(list(expected_seeds), [case["seed"] for case in cases])
                self.assertEqual(
                    [
                        source_response.build_pose_id(x_mm, y_mm)
                        for x_mm, y_mm in expected_pairs
                    ],
                    [case["pose_id"] for case in cases],
                )

    def test_every_config_contains_one_pose_and_has_unique_paths_and_ids(self):
        with tempfile.TemporaryDirectory() as tmp:
            manifest = self.generate(Path(tmp) / "generated")
            case_ids: set[str] = set()
            config_paths: set[str] = set()
            run_dirs: set[str] = set()
            metadata_paths: set[str] = set()

            for case in manifest["cases"]:
                self.assertNotIn(case["case_id"], case_ids)
                self.assertNotIn(case["config_file"], config_paths)
                case_ids.add(case["case_id"])
                config_paths.add(case["config_file"])

                config_path = Path(case["config_file"])
                config = load_yaml(config_path)
                self.assertEqual("list", config["pose"]["mode"])
                poses = experiment_queue.generate_poses(config)
                self.assertEqual(1, len(poses))
                self.assertEqual(case["pose_id"], poses[0]["pose_id"])
                self.assertEqual(case["seed"], poses[0]["random_seed"])
                self.assertEqual(case["head_offset_x_mm"], poses[0]["head_offset_x_mm"])
                self.assertEqual(case["head_offset_y_mm"], poses[0]["head_offset_y_mm"])

                expected = experiment_queue.expected_run_dirs(
                    REPO_ROOT, config_path, config
                )
                self.assertEqual(1, len(expected))
                self.assertNotIn(expected[0]["run_dir"], run_dirs)
                self.assertNotIn(expected[0]["metadata"], metadata_paths)
                run_dirs.add(expected[0]["run_dir"])
                metadata_paths.add(expected[0]["metadata"])

            self.assertEqual(341, len(case_ids))
            self.assertEqual(341, len(config_paths))
            self.assertEqual(341, len(run_dirs))

    def test_e7_size_series_reuses_p4_and_adds_only_p7_p8_p9_center_p001(self):
        with tempfile.TemporaryDirectory() as tmp:
            output_dir = Path(tmp) / "generated"
            manifest = self.generate(output_dir)
            e7 = manifest["scan_design"]["e7_size_series"]

            self.assertEqual("E7", e7["experiment_id"])
            self.assertEqual("center", e7["scan_mode"])
            self.assertEqual("P001", e7["profile_id"])
            self.assertEqual("S4", e7["slit_id"])
            self.assertEqual("P0", e7["baseline"]["phantom_id"])
            self.assertEqual(
                ["P7", "P4", "P8", "P9"],
                [entry["phantom_id"] for entry in e7["series"]],
            )
            self.assertEqual(
                [
                    [5.0, 5.0, 5.0],
                    [10.0, 10.0, 10.0],
                    [15.0, 15.0, 10.0],
                    [20.0, 20.0, 10.0],
                ],
                [entry["defect_size_mm"] for entry in e7["series"]],
            )

            additions = manifest["cases"][-3:]
            self.assertEqual(["P7", "P8", "P9"], [case["phantom_id"] for case in additions])
            self.assertEqual({"center"}, {case["scan_mode"] for case in additions})
            self.assertEqual({"P001"}, {case["profile_id"] for case in additions})
            self.assertEqual([1572, 1573, 1574], [case["seed_start"] for case in additions])

            expected_sizes = {
                "P7": [5.0, 5.0, 5.0],
                "P8": [15.0, 15.0, 10.0],
                "P9": [20.0, 20.0, 10.0],
            }
            for case in additions:
                geometry = load_yaml(
                    REPO_ROOT
                    / f"config/geometry/article_files/{case['phantom_id']}.yaml"
                )
                config = load_yaml(Path(case["config_file"]))
                self.assertEqual(case["phantom_id"], geometry["metadata"]["model_name"])
                inserts = [
                    component
                    for component in geometry["components"]
                    if component["is_insert"]
                ]
                self.assertEqual(1, len(inserts))
                self.assertEqual(
                    {"normal": "G4_AIR", "abnormal": "G4_AIR"},
                    inserts[0]["material"],
                )
                self.assertEqual(
                    {"normal": "air_void", "abnormal": "air_void"},
                    inserts[0]["region_id"],
                )
                self.assertEqual(
                    f"config/geometry/article_files/{case['phantom_id']}.yaml",
                    config["vehicle"]["geometry_file"],
                )
                self.assertEqual(
                    expected_sizes[case["phantom_id"]], case["defect"]["size_mm"]
                )
                self.assertEqual(
                    [20.0, 127.0], config["detector"]["detector_x_range_zero_mm"]
                )
                self.assertEqual(560.0, config["source"]["mono_energy_keV"])
                self.assertEqual(
                    source_response.DEFAULT_N_PRIMARY_PER_POSE,
                    config["run"]["n_primary_per_pose"],
                )
                self.assertEqual(8, config["run"]["number_of_threads"])

    def test_seed_ranges_are_contiguous_and_do_not_overlap(self):
        with tempfile.TemporaryDirectory() as tmp:
            manifest = self.generate(Path(tmp) / "generated")
            expected_seed = 1234
            all_seeds: set[int] = set()
            for case in manifest["cases"]:
                self.assertEqual(expected_seed, case["seed"])
                self.assertEqual(case["seed"], case["seed_start"])
                self.assertEqual(case["seed"], case["seed_end"])
                seeds = set(range(case["seed_start"], case["seed_end"] + 1))
                self.assertEqual(case["pose_count"], len(seeds))
                self.assertTrue(all_seeds.isdisjoint(seeds))
                all_seeds.update(seeds)
                expected_seed = case["seed_end"] + 1
            self.assertEqual(set(range(1234, 1575)), all_seeds)

            self.assertEqual(
                [1248, 1329, 1410, 1491],
                [
                    case["seed"]
                    for case in manifest["cases"]
                    if case["scan_mode"] == "grid" and case["pose_index"] == 0
                ],
            )

    def test_partial_outputs_are_resumable_per_pose(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            manifest = self.generate(root / "generated")
            items = []
            for index, case in enumerate(manifest["cases"][:2]):
                config_path = Path(case["config_file"])
                config = load_yaml(config_path)
                config["output"]["output_directory"] = (root / f"runs/{index}").as_posix()
                expected = experiment_queue.expected_run_dirs(REPO_ROOT, config_path, config)
                items.append(
                    {
                        "index": index,
                        "case_id": case["case_id"],
                        "config_file": config_path.as_posix(),
                        "expected_runs": expected,
                        "status": "pending",
                    }
                )

            completed = items[0]["expected_runs"][0]
            Path(completed["run_dir"]).mkdir(parents=True)
            Path(completed["csv"]).write_text("event_id\n", encoding="utf-8")
            Path(completed["metadata"]).write_text(
                yaml.safe_dump(
                    {
                        "run_id": completed["run_id"],
                        "n_primary": completed["n_primary"],
                    }
                ),
                encoding="utf-8",
            )

            experiment_queue.normalize_resumable_items(items, rerun_completed=False)
            self.assertEqual("completed", items[0]["status"])
            self.assertEqual("pending", items[1]["status"])
            output = StringIO()
            with redirect_stdout(output):
                experiment_queue.print_dry_run(items, rerun_completed=False)
            self.assertIn("0000 skip-complete", output.getvalue())
            self.assertIn("0001 run", output.getvalue())

    def test_cli_defaults_to_articlev2_output_directory(self):
        args = source_response.parse_args([])
        self.assertEqual("articlev2", args.campaign_id)
        self.assertEqual(REPO_ROOT / "config/generated/articlev2", args.output_dir)
        self.assertFalse(args.overwrite)

    def test_cli_parses_explicit_overwrite(self):
        args = source_response.parse_args(["--overwrite"])
        self.assertTrue(args.overwrite)

    def test_nonempty_output_directory_fails_fast(self):
        with tempfile.TemporaryDirectory() as tmp:
            output_dir = Path(tmp) / "generated"
            output_dir.mkdir()
            (output_dir / "keep.txt").write_text("user data", encoding="utf-8")
            with self.assertRaisesRegex(FileExistsError, "not empty"):
                self.generate(output_dir)

    def test_overwrite_replaces_entire_generated_directory_without_touching_results(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            output_dir = root / "generated"
            first_manifest = self.generate(output_dir, campaign_id="old_campaign")
            old_config = Path(first_manifest["cases"][0]["config_file"])
            old_config.write_text("old config\n", encoding="utf-8")
            (output_dir / "manual.txt").write_text("discard me\n", encoding="utf-8")
            (output_dir / "obsolete" / "old.yaml").parent.mkdir()
            (output_dir / "obsolete" / "old.yaml").write_text("obsolete\n", encoding="utf-8")
            results_marker = root / "results" / "keep.txt"
            results_marker.parent.mkdir()
            results_marker.write_text("results stay\n", encoding="utf-8")

            manifest = self.generate(
                output_dir,
                campaign_id="new_campaign",
                energy_keV=570.0,
                overwrite=True,
            )

            self.assertEqual("new_campaign", manifest["campaign_id"])
            self.assertEqual(341, manifest["summary"]["config_count"])
            self.assertFalse((output_dir / "manual.txt").exists())
            self.assertFalse((output_dir / "obsolete").exists())
            self.assertEqual("results stay\n", results_marker.read_text(encoding="utf-8"))

            generated_manifest = load_yaml(output_dir / "manifest.yaml")
            self.assertEqual("new_campaign", generated_manifest["campaign_id"])
            config = load_yaml(Path(manifest["cases"][0]["config_file"]))
            self.assertEqual(570.0, config["source"]["mono_energy_keV"])
            self.assertEqual("fail", config["output"]["existing_run_policy"])
            self.assertTrue(
                config["output"]["output_directory"].startswith(
                    "results/new_campaign/runs/"
                )
            )

    def test_overwrite_failure_preserves_existing_generated_directory(self):
        with tempfile.TemporaryDirectory() as tmp:
            output_dir = Path(tmp) / "generated"
            output_dir.mkdir()
            marker = output_dir / "keep.txt"
            marker.write_text("preserve me\n", encoding="utf-8")

            with self.assertRaisesRegex(FileNotFoundError, "collimator profile file"):
                self.generate(
                    output_dir,
                    profile_file=Path(tmp) / "missing_profiles.csv",
                    overwrite=True,
                )

            self.assertEqual("preserve me\n", marker.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
