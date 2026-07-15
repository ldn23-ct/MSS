#!/usr/bin/env python3
"""Regression checks for experiment-facing C++ contracts shared across campaigns."""

from __future__ import annotations

import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]


class CoreExperimentContractTests(unittest.TestCase):
    def test_metadata_and_flour_support_are_present(self):
        metadata_source = (REPO_ROOT / "src/MetadataWriter.cc").read_text(encoding="utf-8")
        material_source = (REPO_ROOT / "src/MaterialManager.cc").read_text(encoding="utf-8")

        self.assertIn("abnormal_material", metadata_source)
        self.assertIn("Vehicle_Flour", material_source)

    def test_run_id_builder_and_overwrite_policy_are_wired(self):
        run_id_header = (REPO_ROOT / "include/RunIdBuilder.hh").read_text(encoding="utf-8")
        run_id_source = (REPO_ROOT / "src/RunIdBuilder.cc").read_text(encoding="utf-8")
        pose_controller = (REPO_ROOT / "src/PoseRunController.cc").read_text(encoding="utf-8")
        run_action = (REPO_ROOT / "src/RunAction.cc").read_text(encoding="utf-8")
        config_source = (REPO_ROOT / "src/SimulationConfig.cc").read_text(encoding="utf-8")

        self.assertIn("std::string BuildRunId", run_id_header)
        self.assertIn("SystemId(config)", run_id_source)
        self.assertIn("ModelState(config)", run_id_source)
        self.assertIn("EnergyId(config)", run_id_source)
        self.assertIn("config.source.mono_energy_keV", run_id_source)
        self.assertIn("config.collimator.enable", run_id_source)
        self.assertIn("config.vehicle.abnormal_material", run_id_source)
        self.assertIn("mss::BuildRunId(config, pose)", pose_controller)
        self.assertIn("mss::BuildRunId(config_, pose_)", run_action)
        self.assertIn('existing_run_policy == "overwrite"', run_action)
        self.assertIn("fs::remove_all(runDir", run_action)
        self.assertIn("must be fail or overwrite", config_source)


if __name__ == "__main__":
    unittest.main()
