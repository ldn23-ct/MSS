#!/usr/bin/env python3

from __future__ import annotations

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
    def test_core_matrix_generates_48_configs_without_touching_base(self):
        base_path = REPO_ROOT / "config/base/simulation_config_v2.yaml"
        original_base = base_path.read_text(encoding="utf-8")
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
                    "run_summary",
                    "scatter_order_summary",
                    "energy_scan_summary",
                    "visibility_summary",
                    "layer_attribution_summary",
                },
                set(outputs),
            )
            for path in outputs.values():
                self.assertTrue(path.exists())
                with path.open("r", encoding="utf-8", newline="") as stream:
                    fieldnames = csv.DictReader(stream).fieldnames or []
                self.assertFalse(any("|" in field for field in fieldnames))

            run_summary = read_csv(outputs["run_summary"])
            normal = next(row for row in run_summary if row["model_state"] == "normal")
            self.assertEqual("2", normal["N_detected_total"])
            self.assertEqual("1", normal["N_detected_primary"])
            self.assertEqual("1", normal["N_detected_secondary"])
            self.assertEqual("1", normal["N_1"])
            self.assertEqual("1", normal["N_ms"])

            visibility = read_csv(outputs["visibility_summary"])
            self.assertEqual(1, len(visibility))
            self.assertEqual("NaN", visibility[0]["CNR_total"])
            self.assertEqual("0.01", visibility[0]["DeltaH_total"])

            layer_rows = read_csv(outputs["layer_attribution_summary"])
            self.assertIn("first_layer_given_k", layer_rows[0])
            self.assertIn("last_layer_given_channel", layer_rows[0])


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
