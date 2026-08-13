#!/usr/bin/env python3

from __future__ import annotations

import csv
import hashlib
import json
import math
import tempfile
import unittest
from pathlib import Path

import pandas as pd
import yaml


REPO_ROOT = Path(__file__).resolve().parents[1]

from scripts.data_processing import slit_channels
from scripts.postprocessing.e1 import analyze_roi_sensitivity as roi


EVENT_FIELDS = (
    "det_x", "det_y", "scatter_count_total", "first_scatter_z",
    "slit_group", "slit_label",
)


class ArticleV2RoiSensitivityTests(unittest.TestCase):
    def boundary_payload(self) -> dict:
        return {
            "schema_version": slit_channels.SCHEMA_VERSION,
            "algorithm_version": slit_channels.ALGORITHM_VERSION,
            "profiles": {
                "P001": {
                    "slit_order": ["S2", "S4", "S6"],
                    "boundaries_mm": {"S2_S4": 70.0, "S4_S6": 102.0},
                    "detector_x_range_mm": [20.0, 127.0],
                },
                "P002": {
                    "slit_order": ["S1", "S3", "S5"],
                    "boundaries_mm": {"S1_S3": 57.0, "S3_S5": 82.75},
                    "detector_x_range_mm": [11.0, 101.0],
                },
            },
        }

    def write_fixture(self, root: Path, *, bad_label: bool = False) -> None:
        boundary = root / "data_processing/slit_channels/slit_channel_boundaries.json"
        boundary.parent.mkdir(parents=True)
        boundary.write_text(json.dumps(self.boundary_payload()), encoding="utf-8")
        valid_root = root / "events/valid"
        manifest = {
            "schema_version": 1,
            "output_name": "events_valid.csv",
            "depth_filter": "keep iff first_scatter_z and last_scatter_z are finite and both >= 0",
            "boundary_config_sha256": hashlib.sha256(boundary.read_bytes()).hexdigest(),
        }
        valid_root.mkdir(parents=True)
        (valid_root / "valid_events_manifest.yaml").write_text(
            yaml.safe_dump(manifest), encoding="utf-8"
        )

        definitions = {
            "P001": {
                "x_range": [20.0, 127.0],
                "slits": {
                    "S2": (58.0, 21.0, 30.0),
                    "S4": (82.0, 101.0, 60.0),
                    "S6": (119.0, 126.0, 90.0),
                },
            },
            "P002": {
                "x_range": [11.0, 101.0],
                "slits": {
                    "S1": (46.0, 12.0, 15.0),
                    "S3": (72.0, 58.0, 45.0),
                    "S5": (92.0, 100.0, 75.0),
                },
            },
        }
        for profile, definition in definitions.items():
            run = valid_root / "center/P0" / profile / "run"
            run.mkdir(parents=True)
            metadata = {
                "case_id": f"source_response_center_P0_{profile}_E560_seed1",
                "run_id": "pose_x0_y0_E560keV_seed1",
                "config_file": f"config/generated/articlev2/configs/center/P0_{profile}.yaml",
                "vehicle_model_id": "P0",
                "pose_id": "pose_x0_y0",
                "head_offset_x_mm": 0,
                "head_offset_y_mm": 0,
                "n_primary": 100,
                "source": {"mono_energy_keV": 560},
                "collimator": {"profile_id": profile},
                "detector": {
                    "actual_x_range_mm": definition["x_range"],
                    "actual_y_range_mm": [-100.0, 100.0],
                },
            }
            (run / "metadata.yaml").write_text(yaml.safe_dump(metadata), encoding="utf-8")
            rows = []
            for slit, (geo_x, edge_x, depth) in definition["slits"].items():
                rows.extend([
                    {"det_x": geo_x, "det_y": 0, "scatter_count_total": 2,
                     "first_scatter_z": depth, "slit_group": profile, "slit_label": slit},
                    {"det_x": edge_x, "det_y": 0, "scatter_count_total": 3,
                     "first_scatter_z": depth, "slit_group": profile, "slit_label": slit},
                    {"det_x": geo_x, "det_y": 0, "scatter_count_total": 2,
                     "first_scatter_z": 5, "slit_group": profile, "slit_label": slit},
                    {"det_x": geo_x, "det_y": 0, "scatter_count_total": 1,
                     "first_scatter_z": depth, "slit_group": profile, "slit_label": slit},
                ])
            if bad_label and profile == "P001":
                rows[0]["slit_label"] = "S4"
            with (run / "events_valid.csv").open("w", encoding="utf-8", newline="") as stream:
                writer = csv.DictWriter(stream, fieldnames=EVENT_FIELDS)
                writer.writeheader()
                writer.writerows(rows)

    def test_outward_dilation_and_boundary_label_rules(self):
        bounds = roi.roi_bounds_for_slit("S4", (70.0, 102.0))
        self.assertEqual(
            [(78.98, 85.48), (75.676, 88.784), (72.372, 92.088),
             (70.0, 95.392), (70.0, 98.696), (70.0, 102.0)],
            [(round(item.x_min_mm, 3), round(item.x_max_mm, 3)) for item in bounds],
        )
        labels = roi.expected_slit_labels(
            pd.Series([69.999, 70.0, 101.999, 102.0]), "P001", (70.0, 102.0)
        )
        self.assertEqual(["S2", "S4", "S4", "S6"], labels.tolist())
        self.assertTrue(math.isnan(roi.safe_ratio(1, 0)))

    def test_metrics_use_frozen_labels_and_required_ratios(self):
        payload = self.boundary_payload()
        frames = {}
        for profile, slits in roi.PROFILE_SLITS.items():
            rows = []
            for slit in slits:
                window = roi.SLIT_WINDOWS_ZERO_MM[slit]
                depth = roi.SLIT_DESIGN_DEPTH_MM[slit]
                rows.extend([
                    {"det_x": (window.left_mm + window.right_mm) / 2, "det_y": 0,
                     "scatter_count_total": 2, "first_scatter_z": depth, "slit_label": slit},
                    {"det_x": (window.left_mm + window.right_mm) / 2, "det_y": 0,
                     "scatter_count_total": 2, "first_scatter_z": 5, "slit_label": slit},
                    {"det_x": (window.left_mm + window.right_mm) / 2, "det_y": 0,
                     "scatter_count_total": 1, "first_scatter_z": depth, "slit_label": slit},
                ])
            frames[profile] = pd.DataFrame(rows)
        metrics, checks, _ = roi.analyze(frames, payload)
        self.assertEqual(36, len(metrics))
        first = metrics[(metrics.slit_label == "S4") & (metrics["lambda"] == 0)].iloc[0]
        self.assertEqual((1, 1, 2), (first.N_ms_target, first.N_ms_nontarget, first.N_ms_total))
        self.assertEqual(0.5, first.P_target_ms)
        self.assertEqual(1.0, first.P_target_k1)
        self.assertTrue(math.isnan(first.incremental_P_target_ms))
        self.assertTrue(all(value["roi_nested"] for value in checks.values()))

    def test_cli_writes_complete_atomic_output_and_rejects_bad_labels(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "results"
            self.write_fixture(root)
            output = root / "analysis/roi_sensitivity"
            self.assertEqual(0, roi.main([
                "--results-root", str(root), "--output-dir", str(output),
            ]))
            metrics = pd.read_csv(output / roi.METRICS_NAME)
            self.assertEqual(36, len(metrics))
            self.assertEqual(set(roi.LAMBDA_VALUES), set(metrics["lambda"]))
            self.assertEqual(
                {roi.METRICS_NAME, roi.ANALYSIS_MANIFEST_NAME, *roi.FIGURE_NAMES},
                {path.name for path in output.iterdir()},
            )
            manifest = yaml.safe_load((output / roi.ANALYSIS_MANIFEST_NAME).read_text(encoding="utf-8"))
            self.assertTrue(manifest["quality_checks"]["all_passed"])
            with self.assertRaises(FileExistsError):
                roi.main(["--results-root", str(root), "--output-dir", str(output)])

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "results"
            self.write_fixture(root, bad_label=True)
            with self.assertRaisesRegex(ValueError, "frozen slit_label differs"):
                roi.main([
                    "--results-root", str(root),
                    "--output-dir", str(root / "analysis/roi_sensitivity"),
                ])


if __name__ == "__main__":
    unittest.main()
