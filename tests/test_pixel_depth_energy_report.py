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

import report_pixel_depth_energy as report_energy  # noqa: E402


def write_csv(path: Path, rows: list[dict[str, object]], fieldnames: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8", newline="") as stream:
        return list(csv.DictReader(stream))


class PixelDepthEnergyReportTests(unittest.TestCase):
    def write_inputs(self, root: Path) -> Path:
        input_dir = root / "pixel_depth"
        input_dir.mkdir()
        summary_fields = [
            "pose",
            "seed",
            "energy_keV",
            "collimator",
            "abnormal_present",
            "insert_name",
            "insert_material",
            "region_filter",
            "n_valid_hits",
            "n_valid_bins",
            "min_bin_samples",
            "min_valid_bins",
            "spearman_rho",
            "spearman_pvalue",
            "slope_depth_per_bin",
            "slope_pvalue",
            "median_width90",
            "median_wasserstein1_all_lags",
            "median_ks_all_lags",
            "median_separation_all_lags",
            "spatial_score",
            "width_inflation_vs_k1",
            "sep_retention_vs_k1",
            "spatial_score_retention_vs_k1",
        ]
        summary_by_file: dict[tuple[int, str], list[dict[str, object]]] = {}
        for energy in (160, 260):
            for region_filter in ("vehicle_only", "all_valid"):
                for scatter_class in ("k1", "km"):
                    is_k1 = scatter_class == "k1"
                    summary_by_file.setdefault((energy, scatter_class), []).append(
                        {
                            "pose": "poseC",
                            "seed": 1234,
                            "energy_keV": energy,
                            "collimator": "collimated",
                            "abnormal_present": False,
                            "insert_name": "",
                            "insert_material": "",
                            "region_filter": region_filter,
                            "n_valid_hits": 100 if is_k1 else 80,
                            "n_valid_bins": 4,
                            "min_bin_samples": 2,
                            "min_valid_bins": 3,
                            "spearman_rho": 0.8 if is_k1 else 0.4,
                            "spearman_pvalue": 0.01,
                            "slope_depth_per_bin": 1.0,
                            "slope_pvalue": 0.01,
                            "median_width90": 5.0 if is_k1 else 50.0,
                            "median_wasserstein1_all_lags": 10.0,
                            "median_ks_all_lags": 0.2,
                            "median_separation_all_lags": 1.0 if is_k1 else 0.2,
                            "spatial_score": 0.8 if is_k1 else 0.08,
                            "width_inflation_vs_k1": 1.0 if is_k1 else 10.0,
                            "sep_retention_vs_k1": 1.0 if is_k1 else 0.2,
                            "spatial_score_retention_vs_k1": 1.0 if is_k1 else 0.1,
                        }
                    )
        summary_by_file.setdefault((60, "k1"), []).append(
            {
                **summary_by_file[(160, "k1")][0],
                "energy_keV": 60,
                "n_valid_hits": 2,
                "n_valid_bins": 0,
                "spearman_rho": "NaN",
                "median_width90": "NaN",
                "median_separation_all_lags": "NaN",
                "spatial_score": "NaN",
            }
        )
        summary_files: dict[str, dict[str, str]] = {}
        for (energy, scatter_class), rows in summary_by_file.items():
            path = input_dir / "scatter_order_spatial_summary" / f"E{energy}" / f"{scatter_class}.csv"
            write_csv(path, rows, summary_fields)
            summary_files.setdefault(f"E{energy}", {})[scatter_class] = path.relative_to(input_dir).as_posix()

        depth_fields = [
            "pose",
            "seed",
            "energy_keV",
            "collimator",
            "abnormal_present",
            "insert_name",
            "insert_material",
            "region_filter",
            "bin_axis",
            "bin_index",
            "bin_min_mm",
            "bin_max_mm",
            "bin_center_mm",
            "count",
            "mean",
            "std",
            "q05",
            "q25",
            "median",
            "q75",
            "q95",
            "iqr",
            "width90",
        ]
        depth_by_file: dict[tuple[int, str], list[dict[str, object]]] = {}
        for energy in (160, 260):
            for scatter_class in ("k1", "km"):
                for index in range(4):
                    depth_by_file.setdefault((energy, scatter_class), []).append(
                        {
                            "pose": "poseC",
                            "seed": 1234,
                            "energy_keV": energy,
                            "collimator": "collimated",
                            "abnormal_present": False,
                            "insert_name": "",
                            "insert_material": "",
                            "region_filter": "vehicle_only",
                            "bin_axis": "det_x",
                            "bin_index": index,
                            "bin_min_mm": index,
                            "bin_max_mm": index + 1,
                            "bin_center_mm": index + 0.5,
                            "count": 10,
                            "mean": 10 * index,
                            "std": 1,
                            "q05": 10 * index - 1,
                            "q25": 10 * index - 0.5,
                            "median": 10 * index,
                            "q75": 10 * index + 0.5,
                            "q95": 10 * index + 1,
                            "iqr": 1,
                            "width90": 2 if scatter_class == "k1" else 20,
                        }
                    )
        depth_files: dict[str, dict[str, str]] = {}
        for (energy, scatter_class), rows in depth_by_file.items():
            path = input_dir / "pixel_depth_summary_by_scatter_class" / f"E{energy}" / f"{scatter_class}.csv"
            write_csv(path, rows, depth_fields)
            depth_files.setdefault(f"E{energy}", {})[scatter_class] = path.relative_to(input_dir).as_posix()

        lag_fields = ["pose", "seed", "energy_keV", "collimator", "abnormal_present", "insert_name", "insert_material", "region_filter", "lag"]
        lag_files: dict[str, dict[str, str]] = {}
        for energy in (160, 260):
            for scatter_class in ("k1", "km"):
                path = input_dir / "bin_lag_distribution_metrics" / f"E{energy}" / f"{scatter_class}.csv"
                write_csv(path, [], lag_fields)
                lag_files.setdefault(f"E{energy}", {})[scatter_class] = path.relative_to(input_dir).as_posix()

        fraction_fields = ["pose", "seed", "energy_keV", "collimator", "abnormal_present", "insert_name", "insert_material", "region_filter", "bin_index"]
        fraction_files: dict[str, str] = {}
        for energy in (160, 260):
            path = input_dir / "pixel_scatter_class_fraction" / f"E{energy}" / "fractions.csv"
            write_csv(path, [], fraction_fields)
            fraction_files[f"E{energy}"] = path.relative_to(input_dir).as_posix()
        (input_dir / "analysis_manifest.yaml").write_text(
            yaml.safe_dump(
                {
                    "format_version": 2,
                    "output_layout": "split_by_energy_and_scatter_class",
                    "output_dir": input_dir.as_posix(),
                    "discovered_run_count": 3,
                    "analyzed_run_count": 3,
                    "skipped_run_count": 0,
                    "axis": "det_x",
                    "bin_width_mm": 1.0,
                    "outputs": {
                        "scatter_order_spatial_summary": {"files": summary_files},
                        "pixel_depth_summary_by_scatter_class": {"files": depth_files},
                        "bin_lag_distribution_metrics": {"files": lag_files},
                        "pixel_scatter_class_fraction": {"files": fraction_files},
                    },
                },
                sort_keys=False,
            ),
            encoding="utf-8",
        )
        return input_dir

    def test_report_outputs_tables_markdown_and_plots(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            input_dir = self.write_inputs(root)
            output_dir = root / "energy_report"

            outputs = report_energy.generate_report(input_dir, output_dir)

            condition_dir = output_dir / "by_condition" / "collimated" / "poseC" / "normal"
            self.assertEqual(1, outputs["condition_count"])
            self.assertTrue(outputs["index"].exists())
            self.assertTrue((condition_dir / "report.md").exists())
            text = (condition_dir / "report.md").read_text(encoding="utf-8")
            self.assertIn("不同能量下像素 Bin 来源深度分析报告", text)
            self.assertIn("km 相对 k1 是否削弱空间区分", text)

            retention = read_csv(condition_dir / "energy_k1_vs_km_retention.csv")
            km_row = next(row for row in retention if row["energy_keV"] == "160")
            self.assertEqual("True", km_row["supports_ms_weakening"])
            self.assertEqual("10", km_row["width_inflation_vs_k1"])
            self.assertIn("collimator", km_row)
            self.assertIn("abnormal_present", km_row)
            self.assertNotIn("run_id", km_row)
            self.assertNotIn("case_id", km_row)

            sufficiency = read_csv(condition_dir / "energy_sample_sufficiency.csv")
            bad = next(row for row in sufficiency if row["energy_keV"] == "60")
            self.assertEqual("False", bad["sufficient"])
            self.assertIn("n_valid_bins", bad["sufficiency_reason"])

            for csv_path in (
                condition_dir / "energy_spatial_metrics.csv",
                condition_dir / "energy_k1_vs_km_retention.csv",
                condition_dir / "energy_sample_sufficiency.csv",
            ):
                with csv_path.open("r", encoding="utf-8", newline="") as stream:
                    fieldnames = csv.DictReader(stream).fieldnames or []
                self.assertFalse(any("|" in field for field in fieldnames))

            pngs = list((condition_dir / "plots").glob("*.png"))
            self.assertGreaterEqual(len(pngs), 3)


if __name__ == "__main__":
    unittest.main()
