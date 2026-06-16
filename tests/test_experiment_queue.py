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

    def write_config(self, root: Path, case_id: str, energy_keV: int = 160) -> Path:
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
        config_path.write_text(yaml.safe_dump(config, sort_keys=False), encoding="utf-8")
        return config_path

    def write_manifest(self, root: Path, configs: list[Path]) -> Path:
        manifest = {
            "cases": [
                {
                    "case_id": config.stem,
                    "config_file": config.as_posix(),
                }
                for config in configs
            ]
        }
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
                        yaml.safe_dump({{"run_id": expected["run_id"]}}, sort_keys=False),
                        encoding="utf-8",
                    )
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

    def test_saved_queue_successful_cases_run_strictly_serially(self):
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
                self.assertTrue(Path(item["log_path"]).is_file() or (REPO_ROOT / item["log_path"]).is_file())

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


if __name__ == "__main__":
    unittest.main()
