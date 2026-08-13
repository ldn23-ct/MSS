#!/usr/bin/env python3

from __future__ import annotations

import csv
import hashlib
import json
import tempfile
import unittest
from pathlib import Path

import yaml


REPO_ROOT = Path(__file__).resolve().parents[1]

from scripts.data_processing import audit_experiment_data as audit


class ArticleV2AuditExperimentDataTests(unittest.TestCase):
    def boundary_payload(self) -> dict:
        return {
            "schema_version": 1,
            "algorithm_version": "slit_channel_boundaries_v1",
            "profiles": {
                "P001": {
                    "slit_order": ["S2", "S4", "S6"],
                    "boundaries_mm": {"S2_S4": 70.0, "S4_S6": 102.0},
                },
                "P002": {
                    "slit_order": ["S1", "S3", "S5"],
                    "boundaries_mm": {"S1_S3": 57.0, "S3_S5": 82.75},
                },
            },
        }

    def metadata(
        self, mode: str, phantom: str, profile: str, x: float, y: float, seed: int,
        *, n_primary: int = audit.EXPECTED_N_PRIMARY,
    ) -> dict:
        token = f"x{x:g}_y{y:g}".replace("-", "m").replace(".", "p")
        return {
            "case_id": f"source_response_{mode}_{phantom}_{profile}_{token}_E560_seed{seed}",
            "run_id": f"pose_{token}_E560keV_seed{seed}",
            "config_file": f"config/generated/articlev2/configs/{mode}/{phantom}_{profile}.yaml",
            "vehicle_model_id": phantom,
            "pose_id": f"pose_{token}",
            "head_offset_x_mm": x,
            "head_offset_y_mm": y,
            "n_primary": n_primary,
            "random_seed": seed,
            "source": {
                "particle": "gamma", "mono_energy_keV": 560,
                "focal_spot_diameter_mm": 5,
            },
            "collimator": {"profile_id": profile},
            "physics": {"physics_list": "G4EmLivermorePhysics"},
        }

    def raw_rows(self, profile: str, x: float = 0.0) -> list[dict[str, str]]:
        det_x_values = {
            "P001": {"S2": 50.0, "S4": 80.0, "S6": 115.0},
            "P002": {"S1": 40.0, "S3": 70.0, "S5": 90.0},
        }
        rows = []
        for index, slit_label in enumerate(audit.PROFILE_SLITS[profile], start=1):
            rows.append({
                "event_id": str(index), "hit_id": "0", "track_id": str(index),
                "parent_id": "0", "is_primary_gamma": "1",
                "det_x": str(det_x_values[profile][slit_label] + x),
                "det_y": "0", "det_z": "-73", "det_energy": "100",
                "scatter_count_total": "1", "compton_count": "1", "rayleigh_count": "0",
                "first_scatter_x": "0", "first_scatter_y": "0", "first_scatter_z": "30",
                "last_scatter_x": "0", "last_scatter_y": "0", "last_scatter_z": "30",
                "first_scatter_region_id": "pmma_bulk",
                "last_scatter_region_id": "pmma_bulk",
                "slit_group": profile, "slit_label": slit_label,
            })
        return rows

    def write_run(
        self, root: Path, mode: str, phantom: str, profile: str, x: float, y: float,
        seed: int, *, raw_rows: list[dict[str, str]] | None = None,
        valid_rows: list[dict[str, str]] | None = None,
        n_primary: int = audit.EXPECTED_N_PRIMARY, suffix: str = "run",
    ) -> None:
        metadata = self.metadata(mode, phantom, profile, x, y, seed, n_primary=n_primary)
        raw_dir = root / "events/raw" / mode / phantom / profile / suffix
        valid_dir = root / "events/valid" / mode / phantom / profile / suffix
        raw_dir.mkdir(parents=True)
        valid_dir.mkdir(parents=True)
        text = yaml.safe_dump(metadata)
        (raw_dir / "metadata.yaml").write_text(text, encoding="utf-8")
        (valid_dir / "metadata.yaml").write_text(text, encoding="utf-8")
        source_rows = raw_rows if raw_rows is not None else self.raw_rows(profile, x)
        with (raw_dir / "events.csv").open("w", encoding="utf-8", newline="") as stream:
            raw_fields = sorted(
                set(source_rows[0]).difference({"slit_group", "slit_label"})
            )
            writer = csv.DictWriter(stream, fieldnames=raw_fields, extrasaction="ignore")
            writer.writeheader()
            writer.writerows(source_rows)
        selected = valid_rows if valid_rows is not None else source_rows
        with (valid_dir / "events_valid.csv").open("w", encoding="utf-8", newline="") as stream:
            valid_fields = [
                field for field in raw_fields if field not in audit.VALID_EVENT_DROP_COLUMNS
            ] + ["slit_group", "slit_label"]
            writer = csv.DictWriter(stream, fieldnames=valid_fields, extrasaction="ignore")
            writer.writeheader()
            writer.writerows(selected)

    def write_campaign(self, root: Path, *, skip: tuple | None = None) -> None:
        seed = 1
        for condition in audit.required_conditions():
            offsets = audit.expected_offsets(condition.scan_mode)
            for index, (x, y) in enumerate(sorted(offsets)):
                key = (condition.scan_mode, condition.phantom_id, condition.profile_id, x, y)
                if key == skip:
                    seed += 1
                    continue
                self.write_run(
                    root, condition.scan_mode, condition.phantom_id, condition.profile_id,
                    x, y, seed, suffix=f"run_{index}",
                )
                seed += 1
        for phantom in audit.EXTRA_PHANTOM_IDS:
            self.write_run(
                root, "center", phantom, "P001", 0.0, 0.0, seed, suffix="run_0",
            )
            seed += 1

    def write_generated_manifest(self, path: Path, n_primary: int) -> None:
        path.write_text(yaml.safe_dump({
            "parameters": {"n_primary_per_pose": n_primary},
        }), encoding="utf-8")

    def write_data_contract(self, root: Path, *, bad_hash: bool = False) -> None:
        boundary = root / "data_processing/slit_channels/slit_channel_boundaries.json"
        boundary.parent.mkdir(parents=True, exist_ok=True)
        boundary.write_text(json.dumps(self.boundary_payload()), encoding="utf-8")
        files = list((root / "events/valid").rglob("events_valid.csv"))
        rows = 0
        for path in files:
            with path.open("r", encoding="utf-8", newline="") as stream:
                rows += sum(1 for _ in csv.DictReader(stream))
        manifest = {
            "input_file_count": len(files),
            "total_rows_kept": rows,
            "output_name": "events_valid.csv",
            "boundary_config_sha256": (
                "bad" if bad_hash else hashlib.sha256(boundary.read_bytes()).hexdigest()
            ),
        }
        (root / "events/valid/valid_events_manifest.yaml").write_text(
            yaml.safe_dump(manifest), encoding="utf-8"
        )

    def test_complete_campaign_is_ready_and_writes_three_reports(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "results"
            self.write_campaign(root)
            self.write_data_contract(root)
            generated = Path(tmp) / "manifest.yaml"
            self.write_generated_manifest(generated, audit.EXPECTED_N_PRIMARY)
            summary, inventory = audit.audit_results(
                root, generated_manifest=generated, analysis_manifest=Path(tmp) / "no-analysis.yaml"
            )
            self.assertEqual("pass", summary["overall_status"])
            self.assertEqual(0, summary["counts"]["required_simulation_count_missing"])
            self.assertEqual(341, summary["counts"]["valid_run_count"])
            self.assertIn("valid_file", inventory[0])
            self.assertIn("raw_depth_valid_rows", inventory[0])
            output = Path(tmp) / "audit"
            audit.write_outputs(output, summary, inventory, overwrite=False)
            self.assertEqual(set(audit.OUTPUT_NAMES), {path.name for path in output.iterdir()})

    def test_missing_required_grid_pose_is_reported(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "results"
            self.write_campaign(root, skip=("grid", "P6", "P001", 10.0, 10.0))
            self.write_data_contract(root)
            generated = Path(tmp) / "manifest.yaml"
            self.write_generated_manifest(generated, audit.EXPECTED_N_PRIMARY)
            summary, _ = audit.audit_results(
                root, generated_manifest=generated, analysis_manifest=Path(tmp) / "none"
            )
            self.assertEqual(1, summary["counts"]["required_simulation_count_missing"])
            self.assertEqual("missing", summary["experiments"]["E6"]["status"])

    def test_duplicate_grid_pose_and_metadata_mismatch_are_errors(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.write_run(root, "grid", "P0", "P001", 0, 0, 1, suffix="a")
            self.write_run(root, "grid", "P0", "P001", 0, 0, 2, suffix="b")
            _, findings = audit.discover_entries(root, self.boundary_payload())
            codes = {item.code for item in findings}
            self.assertIn("duplicate_run", codes)
            self.assertIn("duplicate_valid_run", codes)

            root2 = Path(tmp) / "metadata"
            self.write_run(root2, "center", "P0", "P001", 0, 0, 1, n_primary=10)
            entries, _ = audit.discover_entries(root2, self.boundary_payload())
            self.assertIn("metadata_mismatch", {item.code for item in entries[0].findings})

    def test_wrong_label_and_row_count_mismatch_are_errors(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            rows = self.raw_rows("P001")
            wrong = [dict(row) for row in rows]
            wrong[0]["slit_label"] = "S1"
            self.write_run(
                root / "wrong", "center", "P0", "P001", 0, 0, 1,
                raw_rows=rows, valid_rows=wrong,
            )
            entries, _ = audit.discover_entries(root / "wrong", self.boundary_payload())
            self.assertIn("invalid_slit_label", {item.code for item in entries[0].findings})

            self.write_run(
                root / "count", "center", "P0", "P001", 0, 0, 1,
                raw_rows=rows, valid_rows=rows[:-1],
            )
            entries, _ = audit.discover_entries(root / "count", self.boundary_payload())
            self.assertIn("valid_row_count_mismatch", {item.code for item in entries[0].findings})

    def test_preserved_fields_order_and_metadata_copy_are_enforced(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            rows = self.raw_rows("P001")
            changed = [dict(row) for row in rows]
            changed[0]["det_energy"] = "999"
            self.write_run(
                root, "center", "P0", "P001", 0, 0, 1,
                raw_rows=rows, valid_rows=changed,
            )
            entries, _ = audit.discover_entries(root, self.boundary_payload())
            self.assertIn(
                "valid_field_or_order_mismatch",
                {item.code for item in entries[0].findings},
            )
            valid_metadata = entries[0].valid_file.parent / "metadata.yaml"
            valid_metadata.write_text(valid_metadata.read_text(encoding="utf-8") + "# changed\n")
            entries, _ = audit.discover_entries(root, self.boundary_payload())
            self.assertIn(
                "raw_valid_metadata_copy_mismatch",
                {item.code for item in entries[0].findings},
            )

    def test_missing_column_scatter_mismatch_and_forbidden_column(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "events.csv"
            path.write_text("event_id\n1\n", encoding="utf-8")
            _, findings = audit.inspect_raw_events(path, Path(tmp))
            self.assertEqual({"missing_event_columns"}, {item.code for item in findings})

            rows = self.raw_rows("P001")
            rows[0]["scatter_count_total"] = "2"
            with path.open("w", encoding="utf-8", newline="") as stream:
                writer = csv.DictWriter(
                    stream, fieldnames=sorted(audit.RAW_REQUIRED_COLUMNS), extrasaction="ignore"
                )
                writer.writeheader()
                writer.writerows(rows)
            _, findings = audit.inspect_raw_events(path, Path(tmp))
            self.assertIn("scatter_count_mismatch", {item.code for item in findings})

            valid = Path(tmp) / "events_valid.csv"
            with valid.open("w", encoding="utf-8", newline="") as stream:
                fields = sorted(audit.VALID_REQUIRED_COLUMNS | {"event_id"})
                writer = csv.DictWriter(stream, fieldnames=fields, extrasaction="ignore")
                writer.writeheader()
                writer.writerows(self.raw_rows("P001"))
            metadata_path = Path(tmp) / "metadata.yaml"
            metadata_path.write_text(
                yaml.safe_dump(self.metadata("center", "P0", "P001", 0, 0, 1)),
                encoding="utf-8",
            )
            metadata = audit.load_run_metadata(metadata_path)
            _, findings = audit.inspect_valid_events(
                valid, metadata, Path(tmp), self.boundary_payload()
            )
            self.assertIn("forbidden_valid_columns", {item.code for item in findings})

    def test_boundary_hash_mismatch_is_an_error(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "results"
            self.write_campaign(root)
            self.write_data_contract(root, bad_hash=True)
            generated = Path(tmp) / "manifest.yaml"
            self.write_generated_manifest(generated, audit.EXPECTED_N_PRIMARY)
            summary, _ = audit.audit_results(
                root, generated_manifest=generated, analysis_manifest=Path(tmp) / "none"
            )
            self.assertEqual("fail", summary["overall_status"])
            self.assertIn(
                "boundary_config_hash_mismatch",
                {item["code"] for item in summary["findings"]},
            )


if __name__ == "__main__":
    unittest.main()
