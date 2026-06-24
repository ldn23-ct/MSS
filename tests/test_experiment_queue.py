#!/usr/bin/env python3

from __future__ import annotations

import json
import os
import sys
import tempfile
import textwrap
import unittest
from contextlib import redirect_stderr
from io import StringIO
from pathlib import Path

import yaml


REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "scripts"))

import run_experiment_queue as queue  # noqa: E402


def load_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


class ExperimentQueueTests(unittest.TestCase):
    def setUp(self):
        self._old_env = dict(os.environ)

    def tearDown(self):
        os.environ.clear()
        os.environ.update(self._old_env)

    def write_config(
        self,
        root: Path,
        case_id: str,
        energy_keV: int = 160,
        n_primary: int | None = None,
    ) -> Path:
        config_dir = root / "configs"
        config_dir.mkdir(parents=True, exist_ok=True)
        config_path = config_dir / f"{case_id}.yaml"
        config = {
            "diagnostics": {"case_id": case_id},
            "pose": {
                "mode": "list",
                "list": {
                    "head_offset_x_mm": [0],
                    "head_offset_y_mm": [320],
                },
            },
            "run": {
                "random_seed": 1234,
                "debug": False,
            },
            "source": {
                "energy_mode": "mono",
                "mono_energy_keV": energy_keV,
            },
            "collimator": {
                "enable": False,
            },
            "vehicle": {
                "model_type": "normal",
                "selected_target_component": None,
                "abnormal_material": None,
            },
            "output": {
                "output_directory": (root / "results" / case_id).as_posix(),
                "events_csv_name": "events.csv",
                "metadata_yaml_name": "metadata.yaml",
                "existing_run_policy": "overwrite",
            },
        }
        if n_primary is not None:
            config["run"]["n_primary_per_pose"] = n_primary
        config_path.write_text(yaml.safe_dump(config, sort_keys=False), encoding="utf-8")
        return config_path

    def write_manifest(
        self,
        root: Path,
        configs: list[Path],
        systems: list[str] | None = None,
        experiments: list[str] | None = None,
        run_safety: dict | None = None,
    ) -> Path:
        manifest = {
            "cases": [
                {
                    "case_id": config.stem,
                    "config_file": config.as_posix(),
                    **({"system": systems[index]} if systems is not None else {}),
                    **({"experiment": experiments[index]} if experiments is not None else {}),
                }
                for index, config in enumerate(configs)
            ]
        }
        if run_safety is not None:
            manifest["run_safety"] = run_safety
        manifest_path = root / "manifest.yaml"
        manifest_path.write_text(yaml.safe_dump(manifest, sort_keys=False), encoding="utf-8")
        return manifest_path

    def write_fake_binary(self, root: Path) -> Path:
        fake = root / "fake_mss.py"
        fake.write_text(
            textwrap.dedent(
                f"""\
                #!/usr/bin/env python3
                import argparse
                import os
                import sys
                import time
                from pathlib import Path

                import yaml

                sys.path.insert(0, {str(REPO_ROOT / "scripts")!r})
                import run_experiment_queue as queue

                parser = argparse.ArgumentParser()
                parser.add_argument("--config", required=True)
                args = parser.parse_args()

                config_path = Path(args.config)
                config = queue.load_yaml(config_path)
                case_id = config.get("diagnostics", {{}}).get("case_id", config_path.stem)
                order_log = os.environ.get("FAKE_MSS_ORDER_LOG")

                def append_order(line):
                    if order_log:
                        with open(order_log, "a", encoding="utf-8") as stream:
                            stream.write(line + "\\n")

                append_order("start:" + case_id)
                if os.environ.get("FAKE_MSS_FAIL_CASE") == case_id:
                    append_order("fail:" + case_id)
                    sys.exit(7)

                time.sleep(0.02)
                for expected in queue.expected_run_dirs(Path({str(REPO_ROOT)!r}), config_path, config):
                    run_dir = Path(expected["run_dir"])
                    run_dir.mkdir(parents=True, exist_ok=True)
                    Path(expected["metadata"]).write_text(
                        yaml.safe_dump(
                            {{
                                "run_id": expected["run_id"],
                                "n_primary": expected.get("n_primary", 0),
                            }},
                            sort_keys=False,
                        ),
                        encoding="utf-8",
                    )
                    if os.environ.get("FAKE_MSS_WRITE_EVENTS") == "1":
                        Path(expected["csv"]).write_text("event_id,hit_id\\n2,7\\n", encoding="utf-8")
                    else:
                        Path(expected["csv"]).write_text("event_id,hit_id\\n", encoding="utf-8")
                append_order("end:" + case_id)
                """
            ),
            encoding="utf-8",
        )
        fake.chmod(0o755)
        return fake

    def run_queue(
        self,
        root: Path,
        manifest: Path,
        binary: Path,
        *extra_args: str,
        save_paths: bool = True,
        with_logs: bool = False,
    ) -> int:
        argv = [
            "--repo-root",
            REPO_ROOT.as_posix(),
            "--manifest",
            manifest.as_posix(),
            "--binary",
            binary.as_posix(),
        ]
        if save_paths:
            argv.extend(
                [
                    "--state-file",
                    (root / "queue_state.json").as_posix(),
                ]
            )
            if with_logs:
                argv.extend(
                    [
                        "--log-dir",
                        (root / "queue_logs").as_posix(),
                    ]
                )
        argv.extend(extra_args)
        args = queue.parse_args(argv)
        return queue.run_queue(args)

    def test_default_successful_cases_run_strictly_serially_without_queue_files(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            configs = [self.write_config(root, "case_a"), self.write_config(root, "case_b")]
            manifest = self.write_manifest(root, configs)
            fake = self.write_fake_binary(root)
            order_log = root / "order.log"
            os.environ["FAKE_MSS_ORDER_LOG"] = order_log.as_posix()

            self.assertEqual(0, self.run_queue(root, manifest, fake, save_paths=False))

            self.assertEqual(
                ["start:case_a", "end:case_a", "start:case_b", "end:case_b"],
                order_log.read_text(encoding="utf-8").splitlines(),
            )
            self.assertFalse((root / "queue_state.json").exists())
            self.assertFalse((root / "queue_state.json.lock").exists())
            self.assertFalse((root / "queue_logs").exists())

    def test_default_resume_skips_already_complete_runs_without_state(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            configs = [self.write_config(root, "case_a")]
            manifest = self.write_manifest(root, configs)
            fake = self.write_fake_binary(root)
            order_log = root / "order.log"
            os.environ["FAKE_MSS_ORDER_LOG"] = order_log.as_posix()

            self.assertEqual(0, self.run_queue(root, manifest, fake, save_paths=False))
            order_log.unlink()
            self.assertEqual(0, self.run_queue(root, manifest, fake, save_paths=False))

            self.assertFalse(order_log.exists())
            self.assertFalse((root / "queue_state.json").exists())
            self.assertFalse((root / "queue_logs").exists())

    def test_saved_queue_successful_cases_run_strictly_serially_without_logs_by_default(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            configs = [self.write_config(root, "case_a"), self.write_config(root, "case_b")]
            manifest = self.write_manifest(root, configs)
            fake = self.write_fake_binary(root)
            order_log = root / "order.log"
            os.environ["FAKE_MSS_ORDER_LOG"] = order_log.as_posix()

            self.assertEqual(0, self.run_queue(root, manifest, fake))

            self.assertEqual(
                ["start:case_a", "end:case_a", "start:case_b", "end:case_b"],
                order_log.read_text(encoding="utf-8").splitlines(),
            )
            state = load_json(root / "queue_state.json")
            self.assertEqual(["completed", "completed"], [item["status"] for item in state["items"]])
            for item in state["items"]:
                self.assertIsNone(item["log_path"])
            self.assertFalse((root / "queue_logs").exists())

    def test_explicit_log_dir_writes_per_case_logs(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            configs = [self.write_config(root, "case_a")]
            manifest = self.write_manifest(root, configs)
            fake = self.write_fake_binary(root)

            self.assertEqual(0, self.run_queue(root, manifest, fake, with_logs=True))

            state = load_json(root / "queue_state.json")
            log_path = state["items"][0]["log_path"]
            self.assertIsNotNone(log_path)
            self.assertTrue((REPO_ROOT / log_path).is_file() or Path(log_path).is_file())

    def test_saved_queue_resume_skips_already_complete_runs(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            configs = [self.write_config(root, "case_a")]
            manifest = self.write_manifest(root, configs)
            fake = self.write_fake_binary(root)
            order_log = root / "order.log"
            os.environ["FAKE_MSS_ORDER_LOG"] = order_log.as_posix()

            self.assertEqual(0, self.run_queue(root, manifest, fake))
            order_log.unlink()
            self.assertEqual(0, self.run_queue(root, manifest, fake))

            self.assertFalse(order_log.exists())
            state = load_json(root / "queue_state.json")
            self.assertEqual("skipped", state["items"][0]["status"])

    def test_failure_stops_queue_by_default(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            configs = [self.write_config(root, "case_a"), self.write_config(root, "case_b")]
            manifest = self.write_manifest(root, configs)
            fake = self.write_fake_binary(root)
            order_log = root / "order.log"
            os.environ["FAKE_MSS_ORDER_LOG"] = order_log.as_posix()
            os.environ["FAKE_MSS_FAIL_CASE"] = "case_a"

            self.assertEqual(7, self.run_queue(root, manifest, fake))

            self.assertEqual(
                ["start:case_a", "fail:case_a"],
                order_log.read_text(encoding="utf-8").splitlines(),
            )
            state = load_json(root / "queue_state.json")
            self.assertEqual(["failed", "pending"], [item["status"] for item in state["items"]])

    def test_previous_running_state_is_resumable(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            config = self.write_config(root, "case_a")
            manifest = self.write_manifest(root, [config])
            fake = self.write_fake_binary(root)
            previous = {
                "schema_version": 1,
                "queue_id": "queue_previous",
                "created_at": "2026-01-01T00:00:00+00:00",
                "items": [
                    {
                        "config_file": config.as_posix(),
                        "status": "running",
                        "attempt_count": 2,
                    }
                ],
            }
            (root / "queue_state.json").write_text(
                json.dumps(previous), encoding="utf-8"
            )

            self.assertEqual(0, self.run_queue(root, manifest, fake))

            state = load_json(root / "queue_state.json")
            self.assertEqual("completed", state["items"][0]["status"])
            self.assertEqual(3, state["items"][0]["attempt_count"])

    def test_dry_run_does_not_create_state_or_outputs(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            manifest = self.write_manifest(root, [self.write_config(root, "case_a")])
            missing_binary = root / "missing_mss"

            self.assertEqual(0, self.run_queue(root, manifest, missing_binary, "--dry-run"))

            self.assertFalse((root / "queue_state.json").exists())
            self.assertFalse((root / "results" / "case_a").exists())

    def test_completion_requires_matching_n_primary_when_config_provides_it(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            config_path = self.write_config(root, "case_a", n_primary=25000000)
            config = queue.load_yaml(config_path)
            expected = queue.expected_run_dirs(REPO_ROOT, config_path, config)[0]
            run_dir = Path(expected["run_dir"])
            run_dir.mkdir(parents=True)
            Path(expected["metadata"]).write_text(
                yaml.safe_dump(
                    {
                        "run_id": expected["run_id"],
                        "n_primary": 10000000,
                    },
                    sort_keys=False,
                ),
                encoding="utf-8",
            )
            Path(expected["csv"]).write_text("event_id,hit_id\n", encoding="utf-8")

            self.assertFalse(queue.run_output_complete(expected))

            Path(expected["metadata"]).write_text(
                yaml.safe_dump(
                    {
                        "run_id": expected["run_id"],
                        "n_primary": 25000000,
                    },
                    sort_keys=False,
                ),
                encoding="utf-8",
            )
            self.assertTrue(queue.run_output_complete(expected))

    def test_system_filter_and_shard_run_only_selected_cases(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            configs = [
                self.write_config(root, "open_a"),
                self.write_config(root, "collimated_a"),
                self.write_config(root, "collimated_b"),
                self.write_config(root, "collimated_c"),
            ]
            manifest = self.write_manifest(
                root,
                configs,
                ["open", "collimated", "collimated", "collimated"],
            )
            fake = self.write_fake_binary(root)
            order_log = root / "order.log"
            os.environ["FAKE_MSS_ORDER_LOG"] = order_log.as_posix()

            self.assertEqual(
                0,
                self.run_queue(
                    root,
                    manifest,
                    fake,
                    "--system",
                    "collimated",
                    "--shard-count",
                    "2",
                    "--shard-index",
                    "1",
                    save_paths=False,
                ),
            )

            self.assertEqual(
                ["start:collimated_b", "end:collimated_b"],
                order_log.read_text(encoding="utf-8").splitlines(),
            )

    def test_default_manifest_path_uses_config_tree(self):
        args = queue.parse_args([])

        self.assertEqual(REPO_ROOT / "config/generated/near_door/manifest.yaml", args.manifest)
        self.assertFalse(args.save_queue)

    def test_state_file_or_log_dir_enables_saved_queue_mode(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)

            state_args = queue.parse_args(["--state-file", (root / "state.json").as_posix()])
            log_args = queue.parse_args(["--log-dir", (root / "logs").as_posix()])

            self.assertTrue(state_args.save_queue)
            self.assertTrue(log_args.save_queue)

    def test_force_unlock_requires_saved_queue_mode(self):
        with redirect_stderr(StringIO()):
            with self.assertRaises(SystemExit):
                queue.parse_args(["--force-unlock"])

    def test_stale_lock_is_removed_when_pid_is_gone(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            manifest = self.write_manifest(root, [self.write_config(root, "case_a")])
            fake = self.write_fake_binary(root)
            lock_path = root / "queue_state.json.lock"
            lock_path.write_text("pid: 999999999\ncreated_at: old\n", encoding="utf-8")

            self.assertEqual(0, self.run_queue(root, manifest, fake))

            self.assertFalse(lock_path.exists())
            state = load_json(root / "queue_state.json")
            self.assertEqual("completed", state["items"][0]["status"])

    def test_live_lock_still_fails_fast(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            manifest = self.write_manifest(root, [self.write_config(root, "case_a")])
            fake = self.write_fake_binary(root)
            lock_path = root / "queue_state.json.lock"
            lock_path.write_text(f"pid: {os.getpid()}\ncreated_at: now\n", encoding="utf-8")

            args = queue.parse_args(
                [
                    "--repo-root",
                    REPO_ROOT.as_posix(),
                    "--manifest",
                    manifest.as_posix(),
                    "--binary",
                    fake.as_posix(),
                    "--state-file",
                    (root / "queue_state.json").as_posix(),
                    "--log-dir",
                    (root / "queue_logs").as_posix(),
                ]
            )
            with self.assertRaisesRegex(RuntimeError, "queue lock already exists"):
                queue.run_queue(args)

            self.assertTrue(lock_path.exists())

    def test_experiment_range_index_and_limit_filters(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            configs = [
                self.write_config(root, "case_e0"),
                self.write_config(root, "case_e1"),
                self.write_config(root, "case_e3"),
                self.write_config(root, "case_e4"),
            ]
            manifest = self.write_manifest(root, configs, experiments=["E0", "E1", "E3", "E4"])
            fake = self.write_fake_binary(root)
            order_log = root / "order.log"
            os.environ["FAKE_MSS_ORDER_LOG"] = order_log.as_posix()

            self.assertEqual(
                0,
                self.run_queue(
                    root,
                    manifest,
                    fake,
                    "--from-experiment",
                    "E0",
                    "--to-experiment",
                    "E3",
                    "--start-index",
                    "1",
                    "--end-index",
                    "3",
                    "--limit",
                    "1",
                    save_paths=False,
                ),
            )

            self.assertEqual(
                ["start:case_e1", "end:case_e1"],
                order_log.read_text(encoding="utf-8").splitlines(),
            )

    def test_only_experiments_filter(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            configs = [
                self.write_config(root, "case_e0"),
                self.write_config(root, "case_e4"),
            ]
            manifest = self.write_manifest(root, configs, experiments=["E0", "E4"])
            fake = self.write_fake_binary(root)
            order_log = root / "order.log"
            os.environ["FAKE_MSS_ORDER_LOG"] = order_log.as_posix()

            self.assertEqual(
                0,
                self.run_queue(
                    root,
                    manifest,
                    fake,
                    "--only-experiments",
                    "E4",
                    save_paths=False,
                ),
            )

            self.assertEqual(
                ["start:case_e4", "end:case_e4"],
                order_log.read_text(encoding="utf-8").splitlines(),
            )

    def test_large_run_guard_blocks_execution_but_not_dry_run(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            configs = [self.write_config(root, "case_a"), self.write_config(root, "case_b")]
            manifest = self.write_manifest(
                root,
                configs,
                run_safety={
                    "large_run_case_threshold": 1,
                    "allow_large_run_required": True,
                },
            )
            missing_binary = root / "missing_mss"

            self.assertEqual(
                0,
                self.run_queue(root, manifest, missing_binary, "--dry-run", save_paths=False),
            )
            args = queue.parse_args(
                [
                    "--repo-root",
                    REPO_ROOT.as_posix(),
                    "--manifest",
                    manifest.as_posix(),
                    "--binary",
                    missing_binary.as_posix(),
                ]
            )
            with self.assertRaisesRegex(RuntimeError, "above manifest threshold"):
                queue.run_queue(args)

    def test_article_batches_auto_merge_after_all_manifest_cases_complete(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            configs = []
            cases = []
            for batch_index, seed in enumerate([9000, 9001, 9002]):
                case_id = f"article_E0_P0_E80_center_b{batch_index}_seed{seed}"
                config_path = self.write_config(root, case_id, energy_keV=80, n_primary=10)
                config = queue.load_yaml(config_path)
                config["run"]["random_seed"] = seed
                config["output"]["output_directory"] = (
                    root / "results/article/unit/runs/E0_P0_E80_center" / f"b{batch_index}"
                ).as_posix()
                config_path.write_text(yaml.safe_dump(config, sort_keys=False), encoding="utf-8")
                configs.append(config_path)
                cases.append(
                    {
                        "case_id": case_id,
                        "condition_id": "E0_P0_E80_center",
                        "config_file": config_path.as_posix(),
                        "experiment": "E0",
                        "phantom_id": "P0",
                        "phantom_group": "pmma",
                        "defect_depth_id": 0,
                        "defect_depth_label": "control",
                        "geometry_file": "config/geometry/phantom_yaml_files/P0.yaml",
                        "energy_keV": 80.0,
                        "pose": "center",
                        "head_offset_x_mm": 0,
                        "head_offset_y_mm": 0,
                        "batch_index": batch_index,
                        "batch_count": 3,
                        "seed": seed,
                        "n_primary_per_pose": 10,
                        "raw_output_directory": config["output"]["output_directory"],
                        "condition_output_directory": (
                            root / "results/article/unit/by_condition/E0/P0/E80/center"
                        ).as_posix(),
                    }
                )
            manifest = {
                "experiment": "article_simulation_campaign",
                "campaign_id": "unit",
                "condition_output_root": (root / "results/article/unit/by_condition").as_posix(),
                "cases": cases,
            }
            manifest_path = root / "manifest.yaml"
            manifest_path.write_text(yaml.safe_dump(manifest, sort_keys=False), encoding="utf-8")
            fake = self.write_fake_binary(root)
            os.environ["FAKE_MSS_WRITE_EVENTS"] = "1"

            self.assertEqual(0, self.run_queue(root, manifest_path, fake))

            merged_dir = root / "results/article/unit/by_condition/E0/P0/E80/center"
            self.assertTrue((merged_dir / "events.csv").is_file())
            self.assertTrue((merged_dir / "metadata.yaml").is_file())
            self.assertEqual(
                ["event_id,hit_id", "2,7", "12,7", "22,7"],
                (merged_dir / "events.csv").read_text(encoding="utf-8").splitlines(),
            )
            metadata = yaml.safe_load((merged_dir / "metadata.yaml").read_text(encoding="utf-8"))
            self.assertTrue(metadata["merged_article_batches"])
            self.assertEqual(30, metadata["n_primary"])
            self.assertEqual([9000, 9001, 9002], metadata["merge"]["seeds"])
            state = load_json(root / "queue_state.json")
            self.assertEqual("completed", state["merge"]["status"])
            self.assertEqual(1, state["merge"]["condition_count"])

    def test_article_merge_skips_when_full_manifest_is_incomplete(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            config_a = self.write_config(root, "case_a", n_primary=10)
            config_b = self.write_config(root, "case_b", n_primary=10)
            manifest = {
                "experiment": "article_simulation_campaign",
                "campaign_id": "unit",
                "condition_output_root": (root / "results/article/unit/by_condition").as_posix(),
                "cases": [
                    {
                        "case_id": "case_a",
                        "condition_id": "E0_P0_E80_center",
                        "config_file": config_a.as_posix(),
                        "experiment": "E0",
                        "phantom_id": "P0",
                        "energy_keV": 80.0,
                        "pose": "center",
                        "head_offset_x_mm": 0,
                        "head_offset_y_mm": 0,
                        "geometry_file": "config/geometry/phantom_yaml_files/P0.yaml",
                        "defect_depth_id": 0,
                        "batch_index": 0,
                        "seed": 9000,
                        "condition_output_directory": (
                            root / "results/article/unit/by_condition/E0/P0/E80/center"
                        ).as_posix(),
                    },
                    {
                        "case_id": "case_b",
                        "condition_id": "E0_P0_E80_center",
                        "config_file": config_b.as_posix(),
                        "experiment": "E0",
                        "phantom_id": "P0",
                        "energy_keV": 80.0,
                        "pose": "center",
                        "head_offset_x_mm": 0,
                        "head_offset_y_mm": 0,
                        "geometry_file": "config/geometry/phantom_yaml_files/P0.yaml",
                        "defect_depth_id": 0,
                        "batch_index": 1,
                        "seed": 9001,
                        "condition_output_directory": (
                            root / "results/article/unit/by_condition/E0/P0/E80/center"
                        ).as_posix(),
                    },
                ],
            }
            manifest_path = root / "manifest.yaml"
            manifest_path.write_text(yaml.safe_dump(manifest, sort_keys=False), encoding="utf-8")
            fake = self.write_fake_binary(root)

            self.assertEqual(0, self.run_queue(root, manifest_path, fake, "--limit", "1"))

            state = load_json(root / "queue_state.json")
            self.assertEqual("skipped", state["merge"]["status"])
            self.assertIn("incomplete", state["merge"]["message"])
            self.assertFalse((root / "results/article/unit/by_condition").exists())


if __name__ == "__main__":
    unittest.main()
