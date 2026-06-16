#!/usr/bin/env python3

from __future__ import annotations

import csv
import re
import sys
import tempfile
import unittest
from pathlib import Path

import yaml


REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "scripts/diagnostics"))

import generate_variants  # noqa: E402
import virtual_slit_filter  # noqa: E402


FORMAL_HEADER = (
    "event_id,hit_id,track_id,parent_id,is_primary_gamma,gamma_source_type,gamma_source_process,"
    "gamma_source_x,gamma_source_y,gamma_source_z,gamma_source_region_id,det_x,det_y,det_z,"
    "det_energy,scatter_count_total,compton_count,rayleigh_count,first_scatter_x,first_scatter_y,"
    "first_scatter_z,last_scatter_x,last_scatter_y,last_scatter_z,first_scatter_region_id,"
    "last_scatter_region_id"
)

DEBUG_HEADER = (
    "event_id,track_id,parent_id,is_primary_gamma,gamma_source_type,gamma_source_process,"
    "gamma_source_x,gamma_source_y,gamma_source_z,gamma_source_region_id,detected,hit_id,det_x,"
    "det_y,det_z,det_energy,scatter_count_total,compton_count,rayleigh_count,first_scatter_x,"
    "first_scatter_y,first_scatter_z,last_scatter_x,last_scatter_y,last_scatter_z,"
    "first_scatter_region_id,last_scatter_region_id"
)

PHASE_HEADER = (
    "event_id,hit_id,track_id,parent_id,is_primary_gamma,particle,phase_x_mm,phase_y_mm,"
    "phase_z_mm,dir_x,dir_y,dir_z,kinetic_energy_keV,weight"
)


def material_values(value):
    if isinstance(value, str):
        yield value
    elif isinstance(value, dict):
        for item in value.values():
            yield from material_values(item)


def read_cpp_string_constant(path: Path, name: str) -> str:
    source = path.read_text(encoding="utf-8")
    match = re.search(
        rf"constexpr const char\* {name}\s*=\s*((?:\"[^\"]*\"\s*)+);",
        source,
        flags=re.MULTILINE,
    )
    if match is None:
        raise AssertionError(f"constant {name} not found in {path}")
    return "".join(re.findall(r'"([^"]*)"', match.group(1)))


class GeometryVariantTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.original = generate_variants.load_yaml(REPO_ROOT / "config/geometry/vehicle_roi_v04.yaml")

    def assert_geometry_unchanged(self, variant):
        keys = (
            "name",
            "host",
            "shape",
            "role",
            "center_mm",
            "size_mm",
            "half_size_mm",
            "placement_center_in_host_mm",
            "aabb_mm",
            "region_id",
            "is_insert",
        )
        self.assertEqual(len(self.original["components"]), len(variant["components"]))
        for original_component, variant_component in zip(
            self.original["components"], variant["components"]
        ):
            for key in keys:
                self.assertEqual(original_component[key], variant_component[key])

    def test_metal_variant_only_replaces_fe_and_al(self):
        variant = generate_variants.make_geometry_variant(self.original, "metal_to_pmma")
        self.assert_geometry_unchanged(variant)
        for original_component, variant_component in zip(
            self.original["components"], variant["components"]
        ):
            original_values = list(material_values(original_component["material"]))
            variant_values = list(material_values(variant_component["material"]))
            expected = [
                generate_variants.PMMA_MATERIAL
                if value in generate_variants.METAL_MATERIALS
                else value
                for value in original_values
            ]
            self.assertEqual(expected, variant_values)

    def test_nonair_variant_replaces_all_nonair_materials(self):
        variant = generate_variants.make_geometry_variant(self.original, "nonair_to_pmma")
        self.assert_geometry_unchanged(variant)
        for component in variant["components"]:
            self.assertTrue(
                all(
                    value in {"G4_AIR", generate_variants.PMMA_MATERIAL}
                    for value in material_values(component["material"])
                )
            )

    def test_eight_case_matrix(self):
        with tempfile.TemporaryDirectory() as tmp:
            manifest = generate_variants.generate(
                REPO_ROOT,
                REPO_ROOT / "config/base/diagnostics_base.yaml",
                REPO_ROOT / "config/geometry/vehicle_roi_v04.yaml",
                REPO_ROOT / "config/geometry/pmma_box.yaml",
                Path(tmp) / "generated",
            )
            self.assertEqual(8, len(manifest["cases"]))
            self.assertEqual(4, sum(case["phase_space_enable"] for case in manifest["cases"]))
            self.assertEqual(
                4, sum(case["collimator_enable"] for case in manifest["cases"])
            )
            for case in manifest["cases"]:
                config = generate_variants.load_yaml(Path(case["config_file"]))
                is_open = case["case_id"].endswith("_open")
                self.assertEqual(is_open, config["diagnostics"]["phase_space"]["enable"])
                self.assertEqual(not is_open, config["collimator"]["enable"])
                expected_detector = (
                    generate_variants.LARGE_SCORING_PLANE
                    if is_open
                    else generate_variants.ORIGINAL_DETECTOR
                )
                self.assertEqual(expected_detector, config["detector"])


class VirtualSlitTests(unittest.TestCase):
    def setUp(self):
        self.jaw = virtual_slit_filter.Jaw(
            jaw_id="jaw_0",
            vertices_xz=((-0.5, -1.0), (0.5, -1.0), (0.5, 1.0), (-0.5, 1.0)),
            y_min=-0.5,
            y_max=0.5,
        )
        self.bounds = (-1.0, 1.0, -1.0, 1.0)

    @staticmethod
    def row(x=0.0, y=0.0, z=-2.0, dx=0.0, dy=0.0, dz=-1.0):
        return {
            "phase_x_mm": str(x),
            "phase_y_mm": str(y),
            "phase_z_mm": str(z),
            "dir_x": str(dx),
            "dir_y": str(dy),
            "dir_z": str(dz),
        }

    def test_blocked_by_jaw(self):
        accepted, reason, jaw_id = virtual_slit_filter.classify_row(
            self.row(), self.bounds, [self.jaw]
        )
        self.assertFalse(accepted)
        self.assertEqual("blocked_by_jaw", reason)
        self.assertEqual("jaw_0", jaw_id)

    def test_polygon_boundary_is_blocked(self):
        accepted, reason, _ = virtual_slit_filter.classify_row(
            self.row(x=0.5), self.bounds, [self.jaw]
        )
        self.assertFalse(accepted)
        self.assertEqual("blocked_by_jaw", reason)

    def test_outside_jaw_y_extrusion_is_accepted(self):
        accepted, reason, _ = virtual_slit_filter.classify_row(
            self.row(y=0.8), self.bounds, [self.jaw]
        )
        self.assertTrue(accepted)
        self.assertEqual("accepted", reason)

    def test_clear_x_path_is_accepted(self):
        accepted, reason, _ = virtual_slit_filter.classify_row(
            self.row(x=0.8), self.bounds, [self.jaw]
        )
        self.assertTrue(accepted)
        self.assertEqual("accepted", reason)

    def test_outside_detector_and_invalid_direction(self):
        self.assertEqual(
            "outside_detector",
            virtual_slit_filter.classify_row(
                self.row(x=2.0), self.bounds, [self.jaw]
            )[1],
        )
        self.assertEqual(
            "invalid_direction",
            virtual_slit_filter.classify_row(
                self.row(dz=1.0), self.bounds, [self.jaw]
            )[1],
        )

    def test_filter_writes_auditable_and_accepted_only_outputs(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            profile = tmp_path / "profile.csv"
            profile.write_text(
                "profile_id,jaw_id,vertex_id,x_mm,z_mm,y_mm\n"
                "P,jaw_0,0,-0.5,-1,-0.0\n"
                "P,jaw_0,1,0.5,-1,-0.0\n"
                "P,jaw_0,2,0.5,1,-0.0\n"
                "P,jaw_0,3,-0.5,1,-0.0\n",
                encoding="utf-8",
            )
            config = {
                "collimator": {
                    "enable": True,
                    "profile_file": str(profile),
                    "profile_id": "P",
                    "jaw_extrusion_length_y_mm": 1.0,
                },
                "detector": {
                    "detector_x_range_zero_mm": [-1.0, 1.0],
                    "detector_y_range_zero_mm": [-1.0, 1.0],
                },
            }
            metadata = {"head_offset_x_mm": 0, "head_offset_y_mm": 0}
            config_path = tmp_path / "slit.yaml"
            metadata_path = tmp_path / "metadata.yaml"
            config_path.write_text(yaml.safe_dump(config), encoding="utf-8")
            metadata_path.write_text(yaml.safe_dump(metadata), encoding="utf-8")

            phase_path = tmp_path / "phase.csv"
            fields = PHASE_HEADER.split(",")
            rows = []
            for index, x in enumerate((0.0, 0.8)):
                row = {field: "0" for field in fields}
                row.update(
                    {
                        "event_id": str(index),
                        "hit_id": "0",
                        "track_id": "1",
                        "parent_id": "0",
                        "is_primary_gamma": "1",
                        "particle": "gamma",
                        "phase_x_mm": str(x),
                        "phase_y_mm": "0",
                        "phase_z_mm": "-2",
                        "dir_x": "0",
                        "dir_y": "0",
                        "dir_z": "-1",
                        "kinetic_energy_keV": "160",
                        "weight": "1",
                    }
                )
                rows.append(row)
            with phase_path.open("w", encoding="utf-8", newline="") as stream:
                writer = csv.DictWriter(stream, fieldnames=fields)
                writer.writeheader()
                writer.writerows(rows)

            audited = tmp_path / "audited.csv"
            total, accepted = virtual_slit_filter.filter_phase_space(
                phase_path, metadata_path, config_path, audited
            )
            self.assertEqual((2, 1), (total, accepted))
            with audited.open("r", encoding="utf-8", newline="") as stream:
                audited_rows = list(csv.DictReader(stream))
            self.assertEqual(["0", "1"], [row["virtual_slit_accept"] for row in audited_rows])

            accepted_path = tmp_path / "accepted.csv"
            virtual_slit_filter.filter_phase_space(
                phase_path, metadata_path, config_path, accepted_path, accepted_only=True
            )
            with accepted_path.open("r", encoding="utf-8", newline="") as stream:
                accepted_rows = list(csv.DictReader(stream))
            self.assertEqual(1, len(accepted_rows))
            self.assertEqual("1", accepted_rows[0]["virtual_slit_accept"])


class SchemaRegressionTests(unittest.TestCase):
    def test_existing_headers_are_unchanged(self):
        source = REPO_ROOT / "src/CsvWriter.cc"
        self.assertEqual(FORMAL_HEADER, read_cpp_string_constant(source, "kFormalHeader"))
        self.assertEqual(DEBUG_HEADER, read_cpp_string_constant(source, "kDebugHeader"))

    def test_phase_space_header(self):
        self.assertEqual(
            PHASE_HEADER,
            read_cpp_string_constant(REPO_ROOT / "src/PhaseSpaceCsvWriter.cc", "kHeader"),
        )


if __name__ == "__main__":
    unittest.main()
