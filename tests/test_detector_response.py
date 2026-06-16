#!/usr/bin/env python3

from __future__ import annotations

import builtins
import csv
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import yaml


REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "scripts"))

import plot_detector_response as response  # noqa: E402


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8", newline="") as stream:
        return list(csv.DictReader(stream))


class DetectorResponseTests(unittest.TestCase):
    def write_run(
        self,
        root: Path,
        name: str = "run_a",
        *,
        system: str = "open",
        pose: str = "poseC",
        model_state: str = "normal",
        material: str | None = None,
        energy_keV: int = 160,
        seed: int = 1234,
        rows: list[dict[str, str]] | None = None,
    ) -> Path:
        run_dir = root / "nested" / name
        run_dir.mkdir(parents=True)
        model_type = "normal" if model_state == "normal" else "abnormal"
        run_id = f"{name}_seed{seed}"
        metadata = {
            "run_id": run_id,
            "pose_id": "pose_x0_y320",
            "model_type": model_type,
            "abnormal_material": material,
            "random_seed": seed,
            "source": {"mono_energy_keV": energy_keV},
            "collimator": {"enable": system == "collimated"},
            "detector": {"actual_x_range_mm": [0.0, 3.0]},
            "diagnostics": {
                "case_id": f"near_door_{system}_{pose}_{model_state}_E{energy_keV}_seed{seed}"
            },
        }
        (run_dir / "metadata.yaml").write_text(
            yaml.safe_dump(metadata, sort_keys=False),
            encoding="utf-8",
        )
        rows = rows or [
            {"det_x": "0.0", "scatter_count_total": "0"},
            {"det_x": "0.999", "scatter_count_total": "1"},
            {"det_x": "1.0", "scatter_count_total": "2"},
            {"det_x": "2.2", "scatter_count_total": "4"},
            {"det_x": "3.0", "scatter_count_total": "5"},
        ]
        with (run_dir / "events.csv").open("w", encoding="utf-8", newline="") as stream:
            writer = csv.DictWriter(stream, fieldnames=["det_x", "scatter_count_total"])
            writer.writeheader()
            writer.writerows(rows)
        return run_dir

    def test_bin_counts_and_scatter_channels(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            run_dir = self.write_run(root)
            output_dir = root / "analysis"

            result = response.plot_detector_response(
                [run_dir],
                output_dir,
                ["all", "k0", "k1", "ms", "k_ge4"],
                1.0,
                write_plots=False,
                write_csv_files=True,
            )

            self.assertEqual(1, result["run_count"])
            self.assertEqual([], result["pngs"])
            rows = read_csv(output_dir / "detector_response_bins.csv")
            self.assertEqual(15, len(rows))
            self.assertFalse(any("|" in field for field in rows[0].keys()))

            counts = {
                (row["channel"], int(row["bin_index"])): int(row["count"])
                for row in rows
            }
            self.assertEqual([2, 1, 2], [counts[("all", index)] for index in range(3)])
            self.assertEqual([1, 0, 0], [counts[("k0", index)] for index in range(3)])
            self.assertEqual([1, 0, 0], [counts[("k1", index)] for index in range(3)])
            self.assertEqual([0, 1, 2], [counts[("ms", index)] for index in range(3)])
            self.assertEqual([0, 0, 2], [counts[("k_ge4", index)] for index in range(3)])
            all_rows = [row for row in rows if row["channel"] == "all"]
            self.assertTrue(all(row["channel_total_count"] == "5" for row in all_rows))
            self.assertEqual([0.4, 0.2, 0.4], [float(row["yield"]) for row in all_rows])

    def test_recursive_discovery_finds_run_dirs(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            run_dir = self.write_run(root)

            discovered = response.discover_run_dirs([root])

            self.assertEqual([run_dir.resolve()], discovered)

    def test_missing_matplotlib_has_clear_error(self):
        original_import = builtins.__import__

        def fake_import(name, *args, **kwargs):
            if name == "matplotlib":
                raise ModuleNotFoundError("No module named 'matplotlib'")
            return original_import(name, *args, **kwargs)

        with mock.patch("builtins.__import__", side_effect=fake_import):
            with self.assertRaisesRegex(RuntimeError, "python3 -m pip install matplotlib"):
                response.ensure_matplotlib_available()

    def test_invalid_channel_is_rejected(self):
        with self.assertRaises(Exception):
            response.parse_channels("all,bad")

    def test_default_output_directories(self):
        args = response.parse_args(["results/near_door"])

        self.assertEqual(Path("results/analysis/detector_response"), args.output_dir)
        self.assertEqual(
            Path("results/analysis/detector_response_comparison"),
            args.comparison_output_dir,
        )
        self.assertFalse(args.write_csv)

        args = response.parse_args(["results/near_door", "--write-csv"])
        self.assertTrue(args.write_csv)

    def test_csv_is_not_written_by_default(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            run_dir = self.write_run(root)
            output_dir = root / "analysis"

            result = response.plot_detector_response(
                [run_dir],
                output_dir,
                ["all"],
                1.0,
                write_plots=False,
            )

            self.assertEqual(output_dir / "detector_response_bins.csv", result["csv"])
            self.assertFalse((output_dir / "detector_response_bins.csv").exists())

    def test_comparison_index_and_missing_panel_without_plots(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            open_run = self.write_run(root, "open_normal", system="open", pose="poseC")
            collimated_run = self.write_run(
                root,
                "collimated_normal",
                system="collimated",
                pose="poseC",
                rows=[{"det_x": "0.2", "scatter_count_total": "0"}],
            )
            output_dir = root / "single"
            comparison_dir = root / "comparison"

            result = response.plot_detector_response(
                [open_run, collimated_run],
                output_dir,
                ["all"],
                1.0,
                write_plots=False,
                comparison_grid=True,
                comparison_output_dir=comparison_dir,
                write_csv_files=True,
            )

            self.assertEqual(output_dir / "detector_response_bins.csv", result["csv"])
            index_path = comparison_dir / "detector_response_comparison_index.csv"
            self.assertEqual(index_path, result["comparison"]["index"])
            rows = read_csv(index_path)
            self.assertEqual(1, len(rows))
            self.assertEqual("160", rows[0]["energy_keV"])
            self.assertEqual("all", rows[0]["channel"])
            self.assertEqual((comparison_dir / "comparison_E160_all.png").as_posix(), rows[0]["png_file"])
            self.assertEqual("yield_by_channel_total", rows[0]["response_scale"])
            self.assertGreaterEqual(int(rows[0]["missing_panel_count"]), 0)
            self.assertFalse(any("|" in field for field in rows[0].keys()))

    def test_comparison_uses_all_discovered_states_for_each_figure(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            open_normal = self.write_run(root, "open_normal", system="open", pose="poseC")
            collimated_normal = self.write_run(root, "collimated_normal", system="collimated", pose="poseC")
            pe_other_energy = self.write_run(
                root,
                "open_pe_e260",
                system="open",
                pose="poseC",
                model_state="cavityPE",
                material="G4_POLYETHYLENE",
                energy_keV=260,
            )
            comparison_dir = root / "comparison"

            result = response.plot_detector_response(
                [open_normal, collimated_normal, pe_other_energy],
                root / "single",
                ["all"],
                1.0,
                write_plots=False,
                comparison_grid=True,
                comparison_output_dir=comparison_dir,
                write_csv_files=True,
            )

            rows = read_csv(result["comparison"]["index"])
            by_energy = {int(row["energy_keV"]): row for row in rows}
            self.assertEqual("2", by_energy[160]["state_count"])
            self.assertEqual("4", by_energy[160]["panel_count"])
            self.assertEqual("2", by_energy[160]["missing_panel_count"])
            self.assertEqual("Pose-C normal; Pose-C PE", by_energy[160]["states"])

    def test_comparison_includes_unknown_new_state(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            normal = self.write_run(root, "open_normal", system="open", pose="poseC")
            unknown = self.write_run(
                root,
                "open_pose_z_lead",
                system="open",
                pose="poseZ",
                model_state="cavityLead",
                material="G4_Pb",
            )
            comparison_dir = root / "comparison"

            result = response.plot_detector_response(
                [normal, unknown],
                root / "single",
                ["all"],
                1.0,
                write_plots=False,
                comparison_grid=True,
                comparison_output_dir=comparison_dir,
                write_csv_files=True,
            )

            rows = read_csv(result["comparison"]["index"])
            self.assertEqual("2", rows[0]["state_count"])
            self.assertIn("poseZ abnormal G4_Pb", rows[0]["states"])

    def test_comparison_yield_sums_multiple_seeds(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            run_a = self.write_run(
                root,
                "open_normal_a",
                system="open",
                seed=1234,
                rows=[
                    {"det_x": "0.2", "scatter_count_total": "0"},
                    {"det_x": "0.3", "scatter_count_total": "0"},
                ],
            )
            run_b = self.write_run(
                root,
                "open_normal_b",
                system="open",
                seed=2234,
                rows=[
                    {"det_x": "0.4", "scatter_count_total": "0"},
                    {"det_x": "1.2", "scatter_count_total": "0"},
                ],
            )
            all_rows = []
            for run_dir in [run_a, run_b]:
                rows, _counts = response.aggregate_run(run_dir, ["all"], 1.0)
                all_rows.extend(rows)

            panels = response.comparison_panel_data(all_rows)
            panel_rows = panels[(160, "all")][(("poseC", "normal", ""), "open")]
            counts = {int(row["bin_index"]): int(row["count"]) for row in panel_rows}
            yields = {int(row["bin_index"]): float(row["yield"]) for row in panel_rows}
            totals = {int(row["bin_index"]): int(row["channel_total_count"]) for row in panel_rows}
            seeds = {
                seed
                for row in panel_rows
                for seed in row.get("seed_values", {int(row["seed"])})
            }

            self.assertEqual(3, counts[0])
            self.assertEqual(1, counts[1])
            self.assertEqual(4, totals[0])
            self.assertEqual(0.75, yields[0])
            self.assertEqual(0.25, yields[1])
            self.assertEqual({1234, 2234}, seeds)

    def test_state_order_and_labels_match_comparison_layout(self):
        rows = [
            {"pose": "poseR", "model_state": "normal", "abnormal_material": None},
            {"pose": "poseC", "model_state": "cavityFlour", "abnormal_material": "Vehicle_Flour"},
            {"pose": "poseC", "model_state": "normal", "abnormal_material": None},
            {"pose": "poseC", "model_state": "cavityPE", "abnormal_material": "G4_POLYETHYLENE"},
        ]

        ordered = response.ordered_state_keys(rows)
        labels = [response.state_label(key) for key in ordered]

        self.assertEqual(
            ["Pose-R normal", "Pose-C normal", "Pose-C PE", "Pose-C Flour"],
            labels,
        )


if __name__ == "__main__":
    unittest.main()
