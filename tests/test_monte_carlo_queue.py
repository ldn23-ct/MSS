#!/usr/bin/env python3

from __future__ import annotations

import json
import os
import tempfile
import textwrap
import unittest
from contextlib import redirect_stderr
from io import StringIO
from pathlib import Path

import yaml


REPO_ROOT = Path(__file__).resolve().parents[1]

from scripts.monte_carlo import run_experiment_queue as queue


def load_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


class ExperimentQueueTests(unittest.TestCase):
    def setUp(self):
        self._old_env = dict(os.environ)

    def tearDown(self):
        os.environ.clear()
        os.environ.update(self._old_env)

    def test_fractional_pose_ids_and_seed_order_match_mss(self):
        config = {
            "pose": {
                "mode": "grid",
                "grid": {
                    "x_offsets_mm": [-7.5, -2.5, 2.5, 7.5],
                    "y_offsets_mm": [2.5],
                },
            },
            "run": {"random_seed": 1234},
            "vehicle": {"model_type": "normal"},
            "collimator": {"enable": True},
            "source": {"energy_mode": "mono", "mono_energy_keV": 560},
            "output": {
                "output_directory": "/tmp/source_response_queue_unit",
                "metadata_yaml_name": "metadata.yaml",
                "events_csv_name": "events.csv",
            },
        }

        poses = queue.generate_poses(config)

        self.assertEqual(
            [
                "pose_xm7p5_y2p5",
                "pose_xm2p5_y2p5",
                "pose_x2p5_y2p5",
                "pose_x7p5_y2p5",
            ],
            [pose["pose_id"] for pose in poses],
        )
        self.assertEqual([1234, 1235, 1236, 1237], [pose["random_seed"] for pose in poses])
        self.assertEqual([-7.5, -2.5, 2.5, 7.5], [pose["head_offset_x_mm"] for pose in poses])

        expected = queue.expected_run_dirs(REPO_ROOT, Path("/tmp/fractional.yaml"), config)
        self.assertEqual(
            [
                "/tmp/source_response_queue_unit/"
                "pose_xm7p5_y2p5_E560keV_seed1234/metadata.yaml",
                "/tmp/source_response_queue_unit/"
                "pose_xm2p5_y2p5_E560keV_seed1235/metadata.yaml",
                "/tmp/source_response_queue_unit/"
                "pose_x2p5_y2p5_E560keV_seed1236/metadata.yaml",
                "/tmp/source_response_queue_unit/"
                "pose_x7p5_y2p5_E560keV_seed1237/metadata.yaml",
            ],
            [item["metadata"] for item in expected],
        )

    def test_fractional_pose_precision_fails_fast(self):
        config = {
            "pose": {
                "mode": "list",
                "list": {
                    "head_offset_x_mm": [0.0000001],
                    "head_offset_y_mm": [0],
                },
            },
            "run": {"random_seed": 1234},
        }
        with self.assertRaisesRegex(ValueError, "six decimal places"):
            queue.generate_poses(config)

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
            "case_id": case_id,
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
        run_safety: dict | None = None,
    ) -> Path:
        manifest = {
            "cases": [
                {
                    "case_id": config.stem,
                    "config_file": config.as_posix(),
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

                sys.path.insert(0, {str(REPO_ROOT)!r})
                from scripts.monte_carlo import run_experiment_queue as queue

                parser = argparse.ArgumentParser()
                parser.add_argument("--config", required=True)
                args = parser.parse_args()

                config_path = Path(args.config)
                config = queue.load_yaml(config_path)
                case_id = config.get("case_id", config_path.stem)
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
                "filters": {"system": "collimated"},
                "items": [
                    {
                        "config_file": config.as_posix(),
                        "system": "collimated",
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
            self.assertEqual(2, state["schema_version"])
            self.assertEqual("completed", state["items"][0]["status"])
            self.assertEqual(3, state["items"][0]["attempt_count"])
            self.assertNotIn("system", state["filters"])
            self.assertNotIn("system", state["items"][0])

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

    def test_shard_runs_only_selected_cases(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            configs = [
                self.write_config(root, "case_a"),
                self.write_config(root, "case_b"),
                self.write_config(root, "case_c"),
                self.write_config(root, "case_d"),
            ]
            manifest = self.write_manifest(root, configs)
            fake = self.write_fake_binary(root)
            order_log = root / "order.log"
            os.environ["FAKE_MSS_ORDER_LOG"] = order_log.as_posix()

            self.assertEqual(
                0,
                self.run_queue(
                    root,
                    manifest,
                    fake,
                    "--shard-count",
                    "2",
                    "--shard-index",
                    "1",
                    save_paths=False,
                ),
            )

            self.assertEqual(
                ["start:case_b", "end:case_b", "start:case_d", "end:case_d"],
                order_log.read_text(encoding="utf-8").splitlines(),
            )

    def test_manifest_is_required(self):
        with redirect_stderr(StringIO()):
            with self.assertRaises(SystemExit):
                queue.parse_args([])

    def test_state_file_enables_saved_queue_mode(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            manifest_args = ["--manifest", (root / "manifest.yaml").as_posix()]

            state_args = queue.parse_args(
                manifest_args + ["--state-file", (root / "state.json").as_posix()]
            )
            log_args = queue.parse_args(
                manifest_args
                + [
                    "--state-file",
                    (root / "state.json").as_posix(),
                    "--log-dir",
                    (root / "logs").as_posix(),
                ]
            )

            self.assertTrue(state_args.save_queue)
            self.assertTrue(log_args.save_queue)

    def test_saved_queue_options_require_explicit_state_file(self):
        manifest_args = ["--manifest", "/tmp/manifest.yaml"]
        with redirect_stderr(StringIO()):
            for extra_args in (["--save-queue"], ["--log-dir", "/tmp/logs"], ["--force-unlock"]):
                with self.subTest(extra_args=extra_args), self.assertRaises(SystemExit):
                    queue.parse_args(manifest_args + extra_args)

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

    def test_index_range_and_limit_filters(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            configs = [
                self.write_config(root, "case_0"),
                self.write_config(root, "case_1"),
                self.write_config(root, "case_2"),
                self.write_config(root, "case_3"),
            ]
            manifest = self.write_manifest(root, configs)
            fake = self.write_fake_binary(root)
            order_log = root / "order.log"
            os.environ["FAKE_MSS_ORDER_LOG"] = order_log.as_posix()

            self.assertEqual(
                0,
                self.run_queue(
                    root,
                    manifest,
                    fake,
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
                ["start:case_1", "end:case_1"],
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

if __name__ == "__main__":
    unittest.main()
