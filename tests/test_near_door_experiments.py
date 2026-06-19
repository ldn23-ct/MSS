#!/usr/bin/env python3

from __future__ import annotations

import argparse
import csv
import sys
import tempfile
import unittest
from pathlib import Path

import yaml


REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "scripts"))

import analyze_near_door_experiments as analyze_near_door  # noqa: E402
import generate_near_door_experiment_configs as generate_near_door  # noqa: E402
import merge_near_door_seed_events as merge_near_door  # noqa: E402


FORMAL_FIELDS = [
    "event_id",
    "hit_id",
    "track_id",
    "parent_id",
    "is_primary_gamma",
    "gamma_source_type",
    "gamma_source_process",
    "gamma_source_x",
    "gamma_source_y",
    "gamma_source_z",
    "gamma_source_region_id",
    "det_x",
    "det_y",
    "det_z",
    "det_energy",
    "scatter_count_total",
    "compton_count",
    "rayleigh_count",
    "first_scatter_x",
    "first_scatter_y",
    "first_scatter_z",
    "last_scatter_x",
    "last_scatter_y",
    "last_scatter_z",
    "first_scatter_region_id",
    "last_scatter_region_id",
]


def load_yaml(path: Path):
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8", newline="") as stream:
        return list(csv.DictReader(stream))


class NearDoorConfigGeneratorTests(unittest.TestCase):
    def test_n_primary_parser_rejects_non_positive_values(self):
        self.assertEqual(1, generate_near_door.parse_positive_int("1"))
        with self.assertRaises(argparse.ArgumentTypeError):
            generate_near_door.parse_positive_int("0")
        with self.assertRaises(argparse.ArgumentTypeError):
            generate_near_door.parse_positive_int("-5")

    def test_core_matrix_generates_48_configs_without_touching_base(self):
        base_path = REPO_ROOT / "config/base/simulation_config_v2.yaml"
        original_base = base_path.read_text(encoding="utf-8")
        base_n_primary = load_yaml(base_path)["run"]["n_primary_per_pose"]
        with tempfile.TemporaryDirectory() as tmp:
            output_dir = Path(tmp) / "near_door"
            manifest = generate_near_door.generate(
                REPO_ROOT,
                base_path,
                output_dir,
                [1234],
                (0, 480),
                (0, 320),
                "near_rear_door_insert",
                False,
                None,
            )
            self.assertEqual(48, len(manifest["cases"]))
            self.assertEqual(original_base, base_path.read_text(encoding="utf-8"))
            self.assertEqual({60, 160, 260, 360, 460, 560}, set(manifest["energies_keV"]))
            self.assertEqual(
                {"open": base_n_primary, "collimated": base_n_primary},
                manifest["n_primary_per_pose"],
            )

            configs = [load_yaml(REPO_ROOT / case["config_file"]) for case in manifest["cases"]]
            normal_configs = [
                config for config in configs if config["vehicle"]["model_type"] == "normal"
            ]
            self.assertTrue(
                all(config["vehicle"]["abnormal_material"] is None for config in normal_configs)
            )
            self.assertEqual(
                24, sum(config["collimator"]["enable"] is False for config in configs)
            )
            self.assertEqual(
                24, sum(config["collimator"]["enable"] is True for config in configs)
            )
            energies = {int(config["source"]["mono_energy_keV"]) for config in configs}
            self.assertEqual({60, 160, 260, 360, 460, 560}, energies)
            self.assertTrue(all(config["source"]["energy_mode"] == "mono" for config in configs))
            self.assertTrue(
                all(config["run"]["n_primary_per_pose"] == base_n_primary for config in configs)
            )
            self.assertTrue(
                all(config["output"]["existing_run_policy"] == "overwrite" for config in configs)
            )

            pose_r = [
                config
                for config in configs
                if config["diagnostics"]["case_id"].split("_")[3] == "poseR"
            ][0]
            pose_c = [
                config
                for config in configs
                if config["diagnostics"]["case_id"].split("_")[3] == "poseC"
            ][0]
            self.assertEqual([0], pose_r["pose"]["list"]["head_offset_x_mm"])
            self.assertEqual([480], pose_r["pose"]["list"]["head_offset_y_mm"])
            self.assertEqual([0], pose_c["pose"]["list"]["head_offset_x_mm"])
            self.assertEqual([320], pose_c["pose"]["list"]["head_offset_y_mm"])

            for case in manifest["cases"]:
                path = Path(case["config_file"])
                self.assertIn(case["system"], path.name)
                self.assertIn(case["pose"], path.name)
                self.assertIn(case["model_state"], path.name)
                self.assertIn(f"E{case['energy_keV']}", path.name)
                self.assertIn(f"seed{case['seed']}", path.name)
                self.assertIn(case["system"], case["output_directory"])
                self.assertIn(case["pose"], case["output_directory"])
                self.assertIn(case["model_state"], case["output_directory"])
                self.assertIn(f"E{case['energy_keV']}", case["output_directory"])
                self.assertIn(f"seed{case['seed']}", case["output_directory"])
                self.assertEqual(base_n_primary, case["n_primary_per_pose"])

    def test_n_primary_overrides_are_applied_by_system(self):
        with tempfile.TemporaryDirectory() as tmp:
            manifest = generate_near_door.generate(
                REPO_ROOT,
                REPO_ROOT / "config/base/simulation_config_v2.yaml",
                Path(tmp) / "near_door",
                [1234],
                (0, 480),
                (0, 320),
                "near_rear_door_insert",
                False,
                None,
                open_n_primary=1000,
                collimated_n_primary=2000,
            )
            self.assertEqual(
                {"open": 1000, "collimated": 2000},
                manifest["n_primary_per_pose"],
            )

            open_case = next(case for case in manifest["cases"] if case["system"] == "open")
            collimated_case = next(
                case for case in manifest["cases"] if case["system"] == "collimated"
            )
            open_config = load_yaml(REPO_ROOT / open_case["config_file"])
            collimated_config = load_yaml(REPO_ROOT / collimated_case["config_file"])

            self.assertEqual(1000, open_case["n_primary_per_pose"])
            self.assertEqual(2000, collimated_case["n_primary_per_pose"])
            self.assertEqual(1000, open_config["run"]["n_primary_per_pose"])
            self.assertEqual(2000, collimated_config["run"]["n_primary_per_pose"])

    def test_collimated_batches_expand_only_collimated_cases(self):
        with tempfile.TemporaryDirectory() as tmp:
            manifest = generate_near_door.generate(
                REPO_ROOT,
                REPO_ROOT / "config/base/simulation_config_v2.yaml",
                Path(tmp) / "near_door",
                [1234],
                (0, 480),
                (0, 320),
                "near_rear_door_insert",
                False,
                None,
                open_n_primary=200000,
                collimated_batches=20,
                collimated_batch_n_primary=25000000,
            )

            open_cases = [case for case in manifest["cases"] if case["system"] == "open"]
            collimated_cases = [
                case for case in manifest["cases"] if case["system"] == "collimated"
            ]
            self.assertEqual(24, len(open_cases))
            self.assertEqual(480, len(collimated_cases))
            self.assertEqual(504, len(manifest["cases"]))
            self.assertEqual(1, manifest["batching"]["open"]["batches_per_base_seed"])
            self.assertEqual(20, manifest["batching"]["collimated"]["batches_per_base_seed"])
            self.assertEqual(
                500000000,
                manifest["batching"]["collimated"]["n_primary_total_per_base_seed"],
            )
            self.assertEqual({1234}, {case["seed"] for case in open_cases})
            self.assertEqual(set(range(1234, 1254)), {case["seed"] for case in collimated_cases})
            self.assertEqual({0}, {case["batch_index"] for case in open_cases})
            self.assertEqual(set(range(20)), {case["batch_index"] for case in collimated_cases})
            self.assertTrue(all(case["n_primary_per_pose"] == 200000 for case in open_cases))
            self.assertTrue(
                all(case["n_primary_per_pose"] == 25000000 for case in collimated_cases)
            )

            sample = next(
                case
                for case in collimated_cases
                if case["pose"] == "poseC"
                and case["model_state"] == "cavityFlour"
                and case["energy_keV"] == 160
                and case["seed"] == 1234
            )
            config = load_yaml(REPO_ROOT / sample["config_file"])
            self.assertEqual(25000000, config["run"]["n_primary_per_pose"])
            self.assertEqual(
                "near_door_collimated_poseC_cavityFlour_E160_seed1234",
                config["diagnostics"]["case_id"],
            )
            self.assertIn("seed1234", sample["output_directory"])

    def test_open_detector_override_applies_only_to_open_panel(self):
        with tempfile.TemporaryDirectory() as tmp:
            manifest = generate_near_door.generate(
                REPO_ROOT,
                REPO_ROOT / "config/base/simulation_config_v2.yaml",
                Path(tmp) / "near_door",
                [1234],
                (0, 480),
                (0, 320),
                "near_rear_door_insert",
                False,
                {
                    "detector_x_range_zero_mm": [-1000.0, 1400.0],
                    "detector_y_range_zero_mm": [-750.0, 750.0],
                },
            )
            open_case = next(case for case in manifest["cases"] if case["system"] == "open")
            collimated_case = next(
                case for case in manifest["cases"] if case["system"] == "collimated"
            )
            open_config = load_yaml(REPO_ROOT / open_case["config_file"])
            collimated_config = load_yaml(REPO_ROOT / collimated_case["config_file"])
            self.assertEqual([-1000.0, 1400.0], open_config["detector"]["detector_x_range_zero_mm"])
            self.assertEqual([-750.0, 750.0], open_config["detector"]["detector_y_range_zero_mm"])
            self.assertNotEqual(
                [-1000.0, 1400.0],
                collimated_config["detector"]["detector_x_range_zero_mm"],
            )


class NearDoorAnalyzerTests(unittest.TestCase):
    def write_run(
        self,
        root: Path,
        name: str,
        case_id: str,
        model_type: str,
        abnormal_material: str,
        rows: list[dict[str, str]],
    ) -> Path:
        run_dir = root / name
        run_dir.mkdir(parents=True)
        metadata = {
            "run_id": name,
            "model_type": model_type,
            "selected_target_component": None if model_type == "normal" else "near_rear_door_insert",
            "abnormal_material": abnormal_material,
            "pose_id": "pose_x0_y320",
            "n_primary": 100,
            "random_seed": 1234,
            "source": {"mono_energy_keV": 160},
            "collimator": {"enable": False},
            "diagnostics": {"case_id": case_id},
        }
        (run_dir / "metadata.yaml").write_text(
            yaml.safe_dump(metadata, sort_keys=False), encoding="utf-8"
        )
        with (run_dir / "events.csv").open("w", encoding="utf-8", newline="") as stream:
            writer = csv.DictWriter(stream, fieldnames=FORMAL_FIELDS)
            writer.writeheader()
            for row in rows:
                full = {field: "0" for field in FORMAL_FIELDS}
                full.update(row)
                writer.writerow(full)
        return run_dir

    def test_analyzer_writes_all_summaries_without_pipe_fields(self):
        normal_rows = [
            {
                "event_id": "1",
                "hit_id": "0",
                "track_id": "1",
                "parent_id": "0",
                "is_primary_gamma": "1",
                "det_x": "1",
                "det_y": "1",
                "scatter_count_total": "1",
                "first_scatter_region_id": "near_door_cavity_air",
                "last_scatter_region_id": "near_door_cavity_air",
            },
            {
                "event_id": "2",
                "hit_id": "0",
                "track_id": "2",
                "parent_id": "1",
                "is_primary_gamma": "0",
                "det_x": "2",
                "det_y": "1",
                "scatter_count_total": "2",
                "first_scatter_region_id": "near_door_reinforcement",
                "last_scatter_region_id": "near_door_inner_metal",
            },
        ]
        abnormal_rows = normal_rows + [
            {
                "event_id": "3",
                "hit_id": "0",
                "track_id": "1",
                "parent_id": "0",
                "is_primary_gamma": "1",
                "det_x": "3",
                "det_y": "1",
                "scatter_count_total": "4",
                "first_scatter_region_id": "target",
                "last_scatter_region_id": "near_door_trim",
            }
        ]
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.write_run(
                root,
                "normal",
                "near_door_open_poseC_normal_E160_seed1234",
                "normal",
                "G4_POLYETHYLENE",
                normal_rows,
            )
            self.write_run(
                root,
                "cavityPE",
                "near_door_open_poseC_cavityPE_E160_seed1234",
                "abnormal",
                "G4_POLYETHYLENE",
                abnormal_rows,
            )
            output_dir = root / "analysis"
            outputs = analyze_near_door.analyze([root], output_dir)
            self.assertEqual(
                {
                    "manifest",
                    "index",
                    "by_condition_dir",
                    "comparisons_dir",
                },
                set(outputs),
            )
            for path in outputs.values():
                self.assertTrue(path.exists())
            index_rows = read_csv(outputs["index"])
            for row in index_rows:
                path = output_dir / row["path"]
                self.assertTrue(path.exists(), path)
                with path.open("r", encoding="utf-8", newline="") as stream:
                    fieldnames = csv.DictReader(stream).fieldnames or []
                self.assertFalse(any("|" in field for field in fieldnames))

            normal_dir = output_dir / "by_condition" / "open" / "poseC" / "normal" / "E160"
            abnormal_dir = output_dir / "by_condition" / "open" / "poseC" / "cavityPE" / "E160"
            run_summary = read_csv(normal_dir / "run_summary.csv") + read_csv(abnormal_dir / "run_summary.csv")
            normal = next(row for row in run_summary if row["model_state"] == "normal")
            self.assertEqual("2", normal["N_detected_total"])
            self.assertEqual("1", normal["N_detected_primary"])
            self.assertEqual("1", normal["N_detected_secondary"])
            self.assertEqual("2", normal["N_all"])
            self.assertEqual("1", normal["N_k1"])
            self.assertEqual("1", normal["N_km"])
            self.assertEqual("1", normal["N_k2"])
            self.assertEqual("0", normal["N_kn"])

            scatter_rows = read_csv(normal_dir / "scatter_order_summary.csv")
            normal_km = next(
                row
                for row in scatter_rows
                if row["model_state"] == "normal" and row["scatter_class"] == "km"
            )
            self.assertEqual("1", normal_km["N"])

            energy_rows = read_csv(normal_dir / "det_energy_summary.csv")
            self.assertIn("det_energy_median", energy_rows[0])

            process_rows = read_csv(normal_dir / "process_count_summary.csv")
            self.assertIn("compton_count_mean", process_rows[0])

            region_rows = read_csv(normal_dir / "region_attribution_summary.csv")
            self.assertTrue(
                any(
                    row["scatter_class"] == "k1"
                    and row["scatter_stage"] == "first"
                    and row["region_id"] == "near_door_cavity_air"
                    for row in region_rows
                )
            )

            visibility = read_csv(output_dir / "comparisons" / "open" / "poseC" / "E160" / "visibility_summary.csv")
            self.assertEqual(1, len(visibility))
            self.assertEqual("NaN", visibility[0]["CNR_total"])
            self.assertEqual("0.01", visibility[0]["DeltaH_total"])

            layer_rows = read_csv(normal_dir / "layer_attribution_summary.csv")
            self.assertIn("first_layer_given_class", layer_rows[0])
            self.assertIn("last_layer_given_channel", layer_rows[0])


class NearDoorSeedMergeTests(unittest.TestCase):
    def write_run(
        self,
        root: Path,
        system: str,
        pose: str,
        model_state: str,
        energy_keV: int,
        seed: int,
        n_primary: int,
        rows: list[dict[str, str]],
        fieldnames: list[str] | None = None,
    ) -> Path:
        material_by_state = {
            "normal": None,
            "cavityPE": "G4_POLYETHYLENE",
            "cavityFlour": "Vehicle_Flour",
            "cavityW": "G4_W",
        }
        material = material_by_state[model_state]
        model_type = "normal" if model_state == "normal" else "abnormal"
        run_id = f"pose_x0_y320_{system}_{model_state}_E{energy_keV}keV_seed{seed}"
        run_dir = root / system / pose / model_state / f"E{energy_keV}" / f"seed{seed}" / run_id
        run_dir.mkdir(parents=True)
        metadata = {
            "run_id": run_id,
            "model_type": model_type,
            "selected_target_component": None if model_type == "normal" else "near_rear_door_insert",
            "abnormal_material": material,
            "pose_id": "pose_x0_y320",
            "head_offset_x_mm": 0,
            "head_offset_y_mm": 320,
            "n_primary": n_primary,
            "random_seed": seed,
            "source": {"mono_energy_keV": energy_keV},
            "collimator": {"enable": system == "collimated"},
            "diagnostics": {
                "case_id": f"near_door_{system}_{pose}_{model_state}_E{energy_keV}_seed{seed}"
            },
        }
        (run_dir / "metadata.yaml").write_text(
            yaml.safe_dump(metadata, sort_keys=False), encoding="utf-8"
        )
        fields = fieldnames or FORMAL_FIELDS
        with (run_dir / "events.csv").open("w", encoding="utf-8", newline="") as stream:
            writer = csv.DictWriter(stream, fieldnames=fields)
            writer.writeheader()
            for row in rows:
                full = {field: "0" for field in fields}
                full.update(row)
                writer.writerow(full)
        return run_dir

    def test_merges_seed_runs_by_physical_condition(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "near_door"
            self.write_run(
                root,
                "collimated",
                "poseC",
                "cavityFlour",
                160,
                1234,
                25,
                [
                    {"event_id": "100", "hit_id": "7", "det_x": "1"},
                    {"event_id": "200", "hit_id": "9", "det_x": "2"},
                ],
            )
            self.write_run(
                root,
                "collimated",
                "poseC",
                "cavityFlour",
                160,
                1235,
                25,
                [{"event_id": "300", "hit_id": "4", "det_x": "3"}],
            )

            output_root = Path(tmp) / "merged"
            results = merge_near_door.merge_seed_events(root, output_root)

            self.assertEqual(1, len(results))
            self.assertEqual(50, results[0].n_primary)
            merged_dir = output_root / "collimated" / "poseC" / "cavityFlour" / "E160"
            rows = read_csv(merged_dir / "events.csv")
            self.assertEqual(3, len(rows))
            self.assertEqual(["0", "1", "2"], [row["event_id"] for row in rows])
            self.assertEqual(["0", "0", "0"], [row["hit_id"] for row in rows])
            self.assertEqual(["1", "2", "3"], [row["det_x"] for row in rows])

            metadata = load_yaml(merged_dir / "metadata.yaml")
            self.assertTrue(metadata["merged_seed_events"])
            self.assertEqual(50, metadata["n_primary"])
            self.assertEqual(
                {
                    "system": "collimated",
                    "pose": "poseC",
                    "model_state": "cavityFlour",
                    "energy_keV": 160,
                },
                metadata["merge_condition"],
            )
            self.assertEqual([1234, 1235], metadata["merge"]["seeds"])
            self.assertEqual(2, metadata["merge"]["source_run_count"])
            self.assertEqual(3, metadata["merge"]["source_event_rows"])

    def test_keeps_different_conditions_separate(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "near_door"
            self.write_run(root, "open", "poseC", "normal", 160, 1234, 10, [])
            self.write_run(root, "collimated", "poseC", "normal", 160, 1234, 20, [])
            self.write_run(root, "open", "poseC", "normal", 260, 1234, 30, [])

            output_root = Path(tmp) / "merged"
            results = merge_near_door.merge_seed_events(root, output_root)

            keys = {(result.key.system, result.key.pose, result.key.model_state, result.key.energy_keV) for result in results}
            self.assertEqual(
                {
                    ("open", "poseC", "normal", 160),
                    ("collimated", "poseC", "normal", 160),
                    ("open", "poseC", "normal", 260),
                },
                keys,
            )
            self.assertTrue((output_root / "open" / "poseC" / "normal" / "E160" / "events.csv").is_file())
            self.assertTrue(
                (output_root / "collimated" / "poseC" / "normal" / "E160" / "events.csv").is_file()
            )

    def test_rejects_header_mismatch(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "near_door"
            self.write_run(root, "open", "poseC", "normal", 160, 1234, 10, [])
            self.write_run(
                root,
                "open",
                "poseC",
                "normal",
                160,
                1235,
                10,
                [],
                FORMAL_FIELDS + ["extra_field"],
            )

            with self.assertRaisesRegex(ValueError, "header mismatch"):
                merge_near_door.merge_seed_events(root, Path(tmp) / "merged")

    def test_rejects_non_empty_output_without_overwrite(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "near_door"
            self.write_run(root, "open", "poseC", "normal", 160, 1234, 10, [])
            output_root = Path(tmp) / "merged"
            output_root.mkdir()
            (output_root / "old.txt").write_text("old", encoding="utf-8")

            with self.assertRaisesRegex(FileExistsError, "--overwrite"):
                merge_near_door.merge_seed_events(root, output_root)


class NearDoorCppSupportTests(unittest.TestCase):
    def test_metadata_and_flour_support_are_present(self):
        metadata_source = (REPO_ROOT / "src/MetadataWriter.cc").read_text(encoding="utf-8")
        material_source = (REPO_ROOT / "src/MaterialManager.cc").read_text(encoding="utf-8")
        self.assertIn("abnormal_material", metadata_source)
        self.assertIn("Vehicle_Flour", material_source)

    def test_run_id_builder_and_overwrite_policy_are_wired(self):
        run_id_header = (REPO_ROOT / "include/RunIdBuilder.hh").read_text(encoding="utf-8")
        run_id_source = (REPO_ROOT / "src/RunIdBuilder.cc").read_text(encoding="utf-8")
        pose_controller = (REPO_ROOT / "src/PoseRunController.cc").read_text(encoding="utf-8")
        run_action = (REPO_ROOT / "src/RunAction.cc").read_text(encoding="utf-8")
        config_source = (REPO_ROOT / "src/SimulationConfig.cc").read_text(encoding="utf-8")

        self.assertIn("std::string BuildRunId", run_id_header)
        self.assertIn("SystemId(config)", run_id_source)
        self.assertIn("ModelState(config)", run_id_source)
        self.assertIn("EnergyId(config)", run_id_source)
        self.assertIn("config.source.mono_energy_keV", run_id_source)
        self.assertIn("config.collimator.enable", run_id_source)
        self.assertIn("config.vehicle.abnormal_material", run_id_source)
        self.assertIn("mss::BuildRunId(config, pose)", pose_controller)
        self.assertIn("mss::BuildRunId(config_, pose_)", run_action)
        self.assertIn('existing_run_policy == "overwrite"', run_action)
        self.assertIn("fs::remove_all(runDir", run_action)
        self.assertIn("must be fail or overwrite", config_source)


if __name__ == "__main__":
    unittest.main()
