#!/usr/bin/env python3
"""Frozen experiment requirements for the article V2 data campaign."""

from __future__ import annotations

from dataclasses import dataclass

from .common import PROFILE_SLITS, SLIT_PROFILE


EXPECTED_ENERGY_KEV = 560.0
EXPECTED_N_PRIMARY = 20_000_000
EXPECTED_PARTICLE = "gamma"
EXPECTED_FOCAL_SPOT_DIAMETER_MM = 5.0
EXPECTED_PHYSICS_LIST = "G4EmLivermorePhysics"

CENTER_PHANTOM_IDS = tuple(f"P{index}" for index in range(7))
CENTER_PROFILE_IDS = ("P001", "P002")

DEFECT_CENTER_Z_MM = {
    "P1": 15.0,
    "P2": 30.0,
    "P3": 45.0,
    "P4": 60.0,
    "P5": 75.0,
    "P6": 90.0,
}
SLIT_DESIGN_DEPTH_MM = {
    f"S{phantom_id[1:]}": depth_mm
    for phantom_id, depth_mm in DEFECT_CENTER_Z_MM.items()
}
TARGET_HALF_WIDTH_MM = 5.0
TARGET_INTERVAL_RULE = "left-closed-right-open"

GRID_OFFSETS_MM = (-10.0, -7.5, -5.0, -2.5, 0.0, 2.5, 5.0, 7.5, 10.0)
E6_TARGETS = (("P2", "S2"), ("P4", "S4"), ("P6", "S6"))
E6_PROFILE_ID = "P001"
E6_GRID_PHANTOM_IDS = ("P0", *(phantom_id for phantom_id, _ in E6_TARGETS))

EXTRA_PHANTOM_IDS = ("P7", "P8", "P9")


@dataclass(frozen=True)
class RequiredCondition:
    scan_mode: str
    phantom_id: str
    profile_id: str
    experiments: tuple[str, ...]


def target_z_range(phantom_id: str) -> tuple[float, float] | None:
    center = DEFECT_CENTER_Z_MM.get(phantom_id)
    if center is None:
        return None
    return center - TARGET_HALF_WIDTH_MM, center + TARGET_HALF_WIDTH_MM


def matched_slit(phantom_id: str) -> str:
    if phantom_id not in DEFECT_CENTER_Z_MM:
        raise ValueError(f"no matched slit for phantom {phantom_id!r}")
    return f"S{phantom_id[1:]}"


def required_center_conditions() -> tuple[RequiredCondition, ...]:
    conditions: list[RequiredCondition] = []
    for phantom_id in CENTER_PHANTOM_IDS:
        for profile_id in CENTER_PROFILE_IDS:
            experiments = ("E1",) if phantom_id == "P0" else ("E2", "E3", "E4")
            conditions.append(RequiredCondition("center", phantom_id, profile_id, experiments))
    return tuple(conditions)


def required_grid_conditions() -> tuple[RequiredCondition, ...]:
    return tuple(
        RequiredCondition("grid", phantom_id, E6_PROFILE_ID, ("E6",))
        for phantom_id in E6_GRID_PHANTOM_IDS
    )


def required_conditions() -> tuple[RequiredCondition, ...]:
    return required_center_conditions() + required_grid_conditions()


def validate_design() -> None:
    if set(CENTER_PROFILE_IDS) != set(PROFILE_SLITS):
        raise AssertionError("center profiles must cover all articlev2 profiles")
    if set(slit for _, slit in E6_TARGETS).difference(PROFILE_SLITS[E6_PROFILE_ID]):
        raise AssertionError("every E6 matched slit must belong to E6_PROFILE_ID")
    if set(SLIT_DESIGN_DEPTH_MM) != set(SLIT_PROFILE):
        raise AssertionError("every slit must have exactly one design depth")
    for phantom_id, slit_id in E6_TARGETS:
        if matched_slit(phantom_id) != slit_id:
            raise AssertionError(f"E6 target is not depth matched: {phantom_id}-{slit_id}")
        if SLIT_PROFILE[slit_id] != E6_PROFILE_ID:
            raise AssertionError(f"E6 slit uses unexpected profile: {slit_id}")


validate_design()
