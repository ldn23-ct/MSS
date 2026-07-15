#!/usr/bin/env python3

from __future__ import annotations

import csv
import sys
import tempfile
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "scripts/article"))

import summarize_scatter_counts as scatter_counts  # noqa: E402


def write_events(path: Path, rows: list[dict[str, str]], fieldnames: list[str] | None = None) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    columns = fieldnames or ["slit_id", "scatter_count_total"]
    with path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=columns)
        writer.writeheader()
        writer.writerows(rows)


class ArticleScatterCountTests(unittest.TestCase):
    def test_recursive_summary_excludes_zero_and_writes_all_channel(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            first = root / "a" / "events_clean.csv"
            second = root / "nested" / "b" / "events_clean.csv"
            write_events(
                first,
                [
                    {"slit_id": "S1", "scatter_count_total": "0"},
                    {"slit_id": "S1", "scatter_count_total": "1"},
                    {"slit_id": "S1", "scatter_count_total": "2"},
                    {"slit_id": "S2", "scatter_count_total": "3"},
                    {"slit_id": "S3", "scatter_count_total": "1"},
                ],
            )
            write_events(second, [])

            rows = scatter_counts.summarize_input(root)
            self.assertEqual(8, len(rows))
            first_rows = {
                row["slit_id"]: row
                for row in rows
                if row["relative_file"] == "a/events_clean.csv"
            }
            expected = {
                "S1": (2, 1, 1),
                "S2": (1, 0, 1),
                "S3": (1, 1, 0),
                "ALL": (4, 2, 2),
            }
            for slit_id, values in expected.items():
                row = first_rows[slit_id]
                self.assertEqual(values, (row["N_total"], row["N_k1"], row["N_ms"]))
                self.assertEqual(row["N_total"], row["N_k1"] + row["N_ms"])

            empty_rows = [row for row in rows if row["relative_file"] == "nested/b/events_clean.csv"]
            self.assertEqual(4, len(empty_rows))
            self.assertTrue(all(row["N_total"] == row["N_k1"] == row["N_ms"] == 0 for row in empty_rows))

    def test_missing_required_column_fails_fast(self):
        with tempfile.TemporaryDirectory() as tmp:
            event_file = Path(tmp) / "events_clean.csv"
            write_events(event_file, [{"slit_id": "S1"}], ["slit_id"])
            with self.assertRaisesRegex(ValueError, "missing required columns"):
                scatter_counts.count_scatter_by_slit(event_file)

    def test_unknown_slit_fails_fast(self):
        with tempfile.TemporaryDirectory() as tmp:
            event_file = Path(tmp) / "events_clean.csv"
            write_events(event_file, [{"slit_id": "S4", "scatter_count_total": "1"}])
            with self.assertRaisesRegex(ValueError, "must be one of"):
                scatter_counts.count_scatter_by_slit(event_file)

    def test_invalid_scatter_counts_fail_fast(self):
        for value in ("-1", "1.5", "nan", "not-a-number", ""):
            with self.subTest(value=value), tempfile.TemporaryDirectory() as tmp:
                event_file = Path(tmp) / "events_clean.csv"
                write_events(event_file, [{"slit_id": "S1", "scatter_count_total": value}])
                with self.assertRaisesRegex(ValueError, "non-negative integer"):
                    scatter_counts.count_scatter_by_slit(event_file)

    def test_write_summary_requires_overwrite(self):
        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp) / "summary.csv"
            rows = [
                {
                    "input_file": "/tmp/events_clean.csv",
                    "relative_file": "events_clean.csv",
                    "slit_id": "ALL",
                    "N_total": 1,
                    "N_k1": 1,
                    "N_ms": 0,
                }
            ]
            scatter_counts.write_summary_csv(output, rows)
            with self.assertRaises(FileExistsError):
                scatter_counts.write_summary_csv(output, rows)
            scatter_counts.write_summary_csv(output, rows, overwrite=True)


if __name__ == "__main__":
    unittest.main()
