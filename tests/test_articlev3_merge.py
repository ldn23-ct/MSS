#!/usr/bin/env python3

from __future__ import annotations

import csv
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import yaml

from scripts.data_processing import prepare_articlev3_merged as merge


def boundary_config() -> dict:
    return {
        "profiles": {
            "P001": {
                "slit_order": ["S2", "S4", "S6"],
                "boundaries_mm": {"S2_S4": 70.0, "S4_S6": 102.0},
            },
            "P002": {
                "slit_order": ["S1", "S3", "S5"],
                "boundaries_mm": {"S1_S3": 57.0, "S3_S5": 82.75},
            },
        }
    }


def metadata(
    seed: int,
    n_primary: int,
    *,
    geometry: str = "P0.yaml",
    profile: str = "P001",
) -> dict:
    return {
        "run_id": f"run_{seed}",
        "case_id": f"case_{seed}",
        "config_file": "config/generated/test/grid/P0_P001/pose_x0_y0.yaml",
        "scan_mode": "grid",
        "vehicle_model_id": "P0",
        "vehicle_geometry_file": geometry,
        "pose_id": "pose_x0_y0",
        "head_offset_x_mm": 0,
        "head_offset_y_mm": 0,
        "n_primary": n_primary,
        "random_seed": seed,
        "source": {"mono_energy_keV": 560, "focal_spot_diameter_mm": 5},
        "collimator": {"profile_id": profile},
        "detector": {"actual_x_range_mm": [20, 127]},
        "physics": {"physics_list": "G4EmLivermorePhysics"},
        "world": {"material": "G4_AIR"},
    }


class ArticleV3MergeTests(unittest.TestCase):
    def write_run(
        self,
        root: Path,
        campaign: str,
        seed: int,
        n_primary: int,
        rows: list[dict[str, object]],
        *,
        profile: str = "P001",
    ) -> merge.SourceRun:
        run_dir = root / campaign / f"run_{seed}"
        run_dir.mkdir(parents=True)
        event_file = run_dir / "events.csv"
        fields = ["det_x", "first_scatter_z", "last_scatter_z", "scatter_count_total"]
        with event_file.open("w", encoding="utf-8", newline="") as stream:
            writer = csv.DictWriter(stream, fieldnames=fields)
            writer.writeheader()
            writer.writerows(rows)
        (run_dir / "metadata.yaml").write_text(
            yaml.safe_dump(metadata(seed, n_primary, profile=profile), sort_keys=False),
            encoding="utf-8",
        )
        return merge.source_run(campaign, event_file)

    @staticmethod
    def complete_source_groups() -> dict[merge.ConditionKey, list[merge.SourceRun]]:
        groups: dict[merge.ConditionKey, list[merge.SourceRun]] = {}
        seed = 1

        def add(key: merge.ConditionKey, campaign: str, n_primary: int) -> None:
            nonlocal seed
            pose_id = f"pose_x{key.head_offset_x_mm:g}_y{key.head_offset_y_mm:g}"
            run = merge.SourceRun(
                campaign=campaign,
                event_file=Path(f"source_{seed}/events.csv"),
                metadata_file=Path(f"source_{seed}/metadata.yaml"),
                key=key,
                pose_id=pose_id,
                n_primary=n_primary,
                energy_keV=560.0,
                seed=seed,
            )
            groups.setdefault(key, []).append(run)
            seed += 1

        center_conditions = sorted(merge.REQUIRED_CENTER_CONDITIONS) + [
            ("P7", "P001"),
            ("P7", "P002"),
            ("P8", "P001"),
        ]
        for phantom, profile in center_conditions:
            add(merge.ConditionKey("center", phantom, profile, 0.0, 0.0), "articlev2", 20_000_000)
        for phantom, profile in sorted(merge.EXPECTED_GRID_CONDITIONS):
            for x in merge.GRID_OFFSETS_MM:
                for y in merge.GRID_OFFSETS_MM:
                    key = merge.ConditionKey("grid", phantom, profile, float(x), float(y))
                    if profile == "P001":
                        add(key, "articlev2", 20_000_000)
                        add(key, "articlev3_grid_p001_add80m", 80_000_000)
                    else:
                        add(key, "articlev3_grid_p002_100m", 100_000_000)
        return groups

    def test_clean_merge_tracks_sources_and_filters_invalid_depths(self):
        rows_a = [
            {"det_x": 60, "first_scatter_z": 10, "last_scatter_z": 12, "scatter_count_total": 1},
            {"det_x": 80, "first_scatter_z": -1, "last_scatter_z": 12, "scatter_count_total": 2},
        ]
        rows_b = [
            {"det_x": 80, "first_scatter_z": 20, "last_scatter_z": 22, "scatter_count_total": 2},
            {"det_x": 110, "first_scatter_z": "nan", "last_scatter_z": 22, "scatter_count_total": 1},
        ]
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            runs = [
                self.write_run(root, "articlev2", 1, 20_000_000, rows_a),
                self.write_run(
                    root, "articlev3_grid_p001_add80m", 2, 80_000_000, rows_b
                ),
            ]
            output = root / "valid"
            stats, slit_counts, merged = merge.clean_and_merge_group(
                runs, output, boundary_config(), root
            )
            self.assertEqual((4, 2, 1, 1), (
                stats.rows_read,
                stats.rows_kept,
                stats.rows_dropped_nonfinite_depth,
                stats.rows_dropped_negative_depth,
            ))
            self.assertEqual(100_000_000, merged["n_primary"])
            self.assertEqual(2, merged["merge_provenance"]["source_count"])
            self.assertEqual(2, sum(slit_counts.values()))
            with (output / "events_valid.csv").open(encoding="utf-8") as stream:
                valid = list(csv.DictReader(stream))
            self.assertEqual(["S2", "S4"], [row["slit_label"] for row in valid])

    def test_metadata_mismatch_and_csv_schema_conflict_fail(self):
        row = {"det_x": 60, "first_scatter_z": 10, "last_scatter_z": 12, "scatter_count_total": 1}
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            first = self.write_run(root, "articlev2", 1, 20_000_000, [row])
            second = self.write_run(
                root, "articlev3_grid_p001_add80m", 2, 80_000_000, [row]
            )
            value = yaml.safe_load(second.metadata_file.read_text(encoding="utf-8"))
            value["vehicle_geometry_file"] = "different.yaml"
            second.metadata_file.write_text(yaml.safe_dump(value), encoding="utf-8")
            second = merge.source_run(second.campaign, second.event_file)
            with self.assertRaisesRegex(ValueError, "metadata disagree"):
                merge.clean_and_merge_group(
                    [first, second], root / "bad-metadata", boundary_config(), root
                )

            value["vehicle_geometry_file"] = "P0.yaml"
            second.metadata_file.write_text(yaml.safe_dump(value), encoding="utf-8")
            with second.event_file.open("a", encoding="utf-8") as stream:
                stream.write("")
            # Recreate the second CSV with one extra column.
            with second.event_file.open("w", encoding="utf-8", newline="") as stream:
                writer = csv.DictWriter(
                    stream,
                    fieldnames=[
                        "det_x", "first_scatter_z", "last_scatter_z",
                        "scatter_count_total", "extra",
                    ],
                )
                writer.writeheader()
                writer.writerow({**row, "extra": 1})
            second = merge.source_run(second.campaign, second.event_file)
            with self.assertRaisesRegex(ValueError, "schemas differ"):
                merge.clean_and_merge_group(
                    [first, second], root / "bad-schema", boundary_config(), root
                )

    def test_p002_single_source_preserves_100m_histories(self):
        row = {"det_x": 50, "first_scatter_z": 10, "last_scatter_z": 12, "scatter_count_total": 1}
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            run = self.write_run(
                root,
                "articlev3_grid_p002_100m",
                9,
                100_000_000,
                [row],
                profile="P002",
            )
            stats, slit_counts, merged = merge.clean_and_merge_group(
                [run], root / "valid-p002", boundary_config(), root
            )
            self.assertEqual(1, stats.rows_kept)
            self.assertEqual(100_000_000, merged["n_primary"])
            self.assertEqual(1, merged["merge_provenance"]["source_count"])
            self.assertEqual(1, slit_counts["S1"])

    def test_discovery_rejects_duplicate_seed(self):
        row = {"det_x": 60, "first_scatter_z": 10, "last_scatter_z": 12, "scatter_count_total": 1}
        with tempfile.TemporaryDirectory() as tmp:
            results = Path(tmp) / "results"
            seeds = (7, 7, 8)
            for campaign, seed in zip(merge.SOURCE_CAMPAIGNS, seeds, strict=True):
                self.write_run(
                    results / campaign / "events" / "raw",
                    "source",
                    seed,
                    20_000_000,
                    [row],
                )
            expected = {campaign: 1 for campaign in merge.SOURCE_CAMPAIGNS}
            with mock.patch.dict(merge.EXPECTED_SOURCE_FILE_COUNTS, expected, clear=True):
                with self.assertRaisesRegex(ValueError, "duplicated"):
                    merge.discover_sources(results)

    def test_source_group_validation_rejects_missing_grid_pose(self):
        groups = self.complete_source_groups()
        merge.validate_source_groups(groups)
        missing_key = merge.ConditionKey("grid", "P5", "P002", -10.0, -10.0)
        removed = groups.pop(missing_key)
        replacement = merge.ConditionKey("center", "P9", "P002", 0.0, 0.0)
        groups[replacement] = [
            merge.SourceRun(
                campaign="articlev2",
                event_file=Path("replacement/events.csv"),
                metadata_file=Path("replacement/metadata.yaml"),
                key=replacement,
                pose_id="pose_x0_y0",
                n_primary=removed[0].n_primary,
                energy_keV=560.0,
                seed=max(run.seed for runs in groups.values() for run in runs) + 1,
            )
        ]
        with self.assertRaisesRegex(ValueError, "exact 9x9 grid"):
            merge.validate_source_groups(groups)

    def test_raw_links_are_relative_and_preserve_sources(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            results = root / "results"
            for campaign in merge.SOURCE_CAMPAIGNS:
                (results / campaign / "events" / "raw").mkdir(parents=True)
            raw_index = results / "articlev3_merged" / "events" / "raw"
            merge.create_raw_source_links(raw_index, results)
            for campaign in merge.SOURCE_CAMPAIGNS:
                link = raw_index / campaign
                self.assertTrue(link.is_symlink())
                self.assertFalse(link.readlink().is_absolute())
                self.assertEqual(
                    (results / campaign / "events" / "raw").resolve(), link.resolve()
                )


if __name__ == "__main__":
    unittest.main()
