#!/usr/bin/env python3
"""Build the supplementary E2 target-depth scatter-composition analysis."""

from __future__ import annotations

import argparse
import math
import os
import shutil
import sys
import tempfile
from pathlib import Path
from typing import Any

os.environ.setdefault("MPLCONFIGDIR", "/tmp/mss_matplotlib")
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import yaml

from scripts.postprocessing.e2 import run as e2


RESAMPLE_SEED = e2.DEFAULT_RESAMPLE_SEED
RESAMPLE_COUNT = e2.RESAMPLE_COUNT
DEFAULT_SUBDIRECTORY = "target_scatter_composition"
FIGURE_NAME = "E2-SF1_P1-P6_target_scatter_composition_and_source_fraction.png"
ST1_TABLE_NAME = "E2-ST1_P1-P6_target_region_response.csv"
ST2_TABLE_NAME = "E2-ST2_P1-P6_baseline_target_scatter_composition.csv"
ST3_TABLE_NAME = "E2-ST3_P1-P6_baseline_class_target_fractions.csv"
TABLE_NAMES = (ST1_TABLE_NAME, ST2_TABLE_NAME, ST3_TABLE_NAME)
OUTPUT_NAMES = (*TABLE_NAMES, FIGURE_NAME)

CONDITIONS = tuple((f"P{i}-S{i}", f"P{i}", f"S{i}", float(depth))
                   for i, depth in enumerate((15, 30, 45, 60, 75, 90), 1))

ST1_COLUMNS = (
    "condition", "defect_phantom", "slit", "depth_mm",
    *(column for scatter_class in e2.CLASSES for column in (
        f"N_T0_{scatter_class}", f"N_TD_{scatter_class}",
        f"C_T_{scatter_class}", f"C_T_{scatter_class}_ci_low",
        f"C_T_{scatter_class}_ci_high", f"C_T_{scatter_class}_n_effective",
    )),
)
ST2_COLUMNS = (
    "condition", "defect_phantom", "slit", "depth_mm",
    "N_T_total", "N_T_k1", "N_T_ms",
    "q_k1_given_T", "q_k1_given_T_ci_low", "q_k1_given_T_ci_high",
    "q_k1_given_T_n_effective",
    "q_ms_given_T", "q_ms_given_T_ci_low", "q_ms_given_T_ci_high",
    "q_ms_given_T_n_effective",
)
ST3_COLUMNS = (
    "condition", "defect_phantom", "slit", "depth_mm",
    *(column for scatter_class in e2.CLASSES for column in (
        f"f_T0_{scatter_class}", f"f_T0_{scatter_class}_ci_low",
        f"f_T0_{scatter_class}_ci_high", f"f_T0_{scatter_class}_n_effective",
    )),
)


def _require_columns(frame: pd.DataFrame, columns: tuple[str, ...], label: str) -> None:
    if tuple(frame.columns) != columns:
        raise ValueError(f"{label} schema does not match the frozen E2 contract")


def _same_or_nan(actual: Any, expected: float) -> bool:
    if math.isnan(expected):
        return pd.isna(actual)
    return math.isclose(float(actual), expected, rel_tol=0.0, abs_tol=1e-12)


def validate_formal_controls(e2_root: Path) -> None:
    acceptance_path = e2_root / "acceptance_summary.yaml"
    manifest_path = e2_root / "analysis_manifest.yaml"
    if not acceptance_path.is_file() or not manifest_path.is_file():
        raise FileNotFoundError("formal E2 acceptance_summary.yaml and analysis_manifest.yaml are required")
    acceptance = yaml.safe_load(acceptance_path.read_text(encoding="utf-8"))
    if acceptance.get("overall_status") != "pass" or not all(
        item.get("pass") is True for item in acceptance.get("checks", {}).values()
    ):
        raise ValueError("formal E2 acceptance must pass before supplementary analysis")
    manifest = yaml.safe_load(manifest_path.read_text(encoding="utf-8"))
    parameters = manifest.get("parameters", {})
    resampling = parameters.get("poisson_resampling", {})
    if (
        manifest.get("experiment") != "E2"
        or manifest.get("publication_status") != "complete"
        or parameters.get("input_layer") != "events/valid"
        or parameters.get("summary_source") != "grid-zero"
        or int(resampling.get("draw_count", -1)) != RESAMPLE_COUNT
        or int(resampling.get("seed", -1)) != RESAMPLE_SEED
    ):
        raise ValueError("formal E2 manifest does not match the frozen grid-zero/resampling contract")


def load_formal_tables(e2_root: Path) -> tuple[dict[str, pd.DataFrame], pd.DataFrame, pd.DataFrame]:
    validate_formal_controls(e2_root)
    tables_root = e2_root / "tables"
    t1_path = tables_root / e2.ZERO_POSE_T1_TABLE_NAME
    t3_path = tables_root / e2.ZERO_POSE_T3_TABLE_NAME
    if not t1_path.is_file() or not t3_path.is_file():
        raise FileNotFoundError("formal grid-zero E2-T1 and E2-T3 tables are required")
    t1 = pd.read_csv(t1_path)
    t3 = pd.read_csv(t3_path)
    _require_columns(t1, e2.T1_COLUMNS, t1_path.name)
    _require_columns(t3, e2.T3_COLUMNS, t3_path.name)
    if len(t1) != 18 or len(t3) != 108:
        raise ValueError("formal E2-T1/T3 row counts do not match the frozen contract")

    t2_tables: dict[str, pd.DataFrame] = {}
    for condition, phantom, slit, depth in CONDITIONS:
        path = tables_root / f"E2-T2_P0-{slit}_vs_{phantom}-{slit}_source_region_quantitative.csv"
        if not path.is_file():
            raise FileNotFoundError(f"formal E2-T2 table is missing: {path}")
        table = pd.read_csv(path)
        _require_columns(table, e2.T2_COLUMNS, path.name)
        if (
            len(table) != 9
            or set(table.scatter_class) != set(e2.CLASSES)
            or set(table.region) != set(e2.REGIONS)
            or table.groupby(["scatter_class", "region"]).ngroups != 9
            or set(table.baseline_phantom) != {"P0"}
            or set(table.defect_phantom) != {phantom}
            or set(table.slit) != {slit}
            or not np.allclose(table.target_depth_mm, depth)
        ):
            raise ValueError(f"{path.name} does not contain the expected {condition} 3x3 class/region rows")
        t2_tables[condition] = table

    validate_formal_closures(t1, t2_tables, t3)
    return t2_tables, t3, t1


def validate_formal_closures(
    t1: pd.DataFrame,
    t2_tables: dict[str, pd.DataFrame],
    t3: pd.DataFrame,
) -> None:
    expected_roles = {"baseline", "defect"}
    if set(t3.condition_role) != expected_roles:
        raise ValueError("formal E2-T3 must contain baseline and defect rows")
    groups = t3.groupby(
        ["defect_phantom", "slit", "condition_role", "scatter_class"], sort=False
    )
    if groups.ngroups != 36:
        raise ValueError("formal E2-T3 grouping is incomplete")
    for key, group in groups:
        if set(group.region) != set(e2.REGIONS) or len(group) != 3:
            raise ValueError(f"formal E2-T3 F/T/B partition is incomplete for {key}")
        total = int(group.N_total.iloc[0])
        if not group.N_total.eq(total).all() or int(group.N_region.sum()) != total:
            raise ValueError(f"formal E2-T3 regional counts do not close for {key}")
        expected = group.N_region.to_numpy(dtype=float) / total if total else np.full(3, np.nan)
        actual = group.fraction.to_numpy(dtype=float)
        if total and not np.allclose(actual, expected, rtol=0.0, atol=1e-12):
            raise ValueError(f"formal E2-T3 fractions do not match counts for {key}")
        if total and not math.isclose(float(actual.sum()), 1.0, rel_tol=0.0, abs_tol=1e-12):
            raise ValueError(f"formal E2-T3 fractions do not close to one for {key}")

    for condition, phantom, slit, _ in CONDITIONS:
        center = t1[(t1.defect_phantom == phantom) & (t1.slit == slit)].set_index("scatter_class")
        if set(center.index) != set(e2.CLASSES) or len(center) != 3:
            raise ValueError(f"formal E2-T1 rows are incomplete for {condition}")
        for role, count_column, t1_column in (
            ("baseline", "N_r0", "N0"), ("defect", "N_rD", "ND")
        ):
            totals = t3[
                (t3.defect_phantom == phantom)
                & (t3.slit == slit)
                & (t3.condition_role == role)
            ].groupby("scatter_class").N_total.first()
            for scatter_class in e2.CLASSES:
                if int(totals.loc[scatter_class]) != int(center.loc[scatter_class, t1_column]):
                    raise ValueError(f"formal E2-T1/T3 total mismatch for {condition}/{role}/{scatter_class}")

        target = t2_tables[condition][t2_tables[condition].region == "Target"].set_index("scatter_class")
        for count_column, role in (("N_r0", "baseline"), ("N_rD", "defect")):
            source = t3[
                (t3.defect_phantom == phantom)
                & (t3.slit == slit)
                & (t3.condition_role == role)
                & (t3.region == "Target")
            ].set_index("scatter_class")
            for scatter_class in e2.CLASSES:
                if int(target.loc[scatter_class, count_column]) != int(source.loc[scatter_class, "N_region"]):
                    raise ValueError(f"formal E2-T2/T3 target count mismatch for {condition}/{role}/{scatter_class}")
        for count_column in ("N_r0", "N_rD"):
            if int(target.loc["total", count_column]) != int(target.loc["k1", count_column]) + int(
                target.loc["ms", count_column]
            ):
                raise ValueError(f"formal E2 target count closure failed for {condition}/{count_column}")
        for scatter_class, row in target.iterrows():
            n0, nd = int(row.N_r0), int(row.N_rD)
            expected_c = (nd - n0) / n0 if n0 else math.nan
            if not _same_or_nan(row.C_r, expected_c):
                raise ValueError(f"formal E2-T2 C_T mismatch for {condition}/{scatter_class}")


def build_target_response_table(t2_tables: dict[str, pd.DataFrame]) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    for condition, phantom, slit, depth in CONDITIONS:
        target = t2_tables[condition][t2_tables[condition].region == "Target"].set_index("scatter_class")
        output: dict[str, Any] = {
            "condition": condition,
            "defect_phantom": phantom,
            "slit": slit,
            "depth_mm": depth,
        }
        for scatter_class in e2.CLASSES:
            source = target.loc[scatter_class]
            output.update({
                f"N_T0_{scatter_class}": int(source.N_r0),
                f"N_TD_{scatter_class}": int(source.N_rD),
                f"C_T_{scatter_class}": source.C_r,
                f"C_T_{scatter_class}_ci_low": source.C_r_ci_low,
                f"C_T_{scatter_class}_ci_high": source.C_r_ci_high,
                f"C_T_{scatter_class}_n_effective": int(source.C_r_n_effective),
            })
        rows.append(output)
    return pd.DataFrame(rows, columns=ST1_COLUMNS)


def poisson_target_composition(
    n_k1: int,
    n_ms: int,
    rng: np.random.Generator,
    *,
    resample_count: int = RESAMPLE_COUNT,
) -> dict[str, float | int]:
    if n_k1 < 0 or n_ms < 0 or resample_count <= 0:
        raise ValueError("target counts must be non-negative and resample_count must be positive")
    total = n_k1 + n_ms
    q_k1 = n_k1 / total if total else math.nan
    q_ms = n_ms / total if total else math.nan
    draws = rng.poisson(np.array([n_k1, n_ms], dtype=float), size=(resample_count, 2))
    denominators = draws.sum(axis=1)
    valid = denominators > 0
    sampled_k1 = np.full(resample_count, np.nan, dtype=float)
    sampled_ms = np.full(resample_count, np.nan, dtype=float)
    sampled_k1[valid] = draws[valid, 0] / denominators[valid]
    sampled_ms[valid] = draws[valid, 1] / denominators[valid]
    if np.any(valid) and not np.allclose(
        sampled_k1[valid] + sampled_ms[valid], 1.0, rtol=0.0, atol=1e-12
    ):
        raise AssertionError("sampled target composition does not close to one")
    k1_low, k1_high, k1_n = e2.finite_interval(
        sampled_k1, "q(k1|T)", allow_empty=True
    )
    ms_low, ms_high, ms_n = e2.finite_interval(
        sampled_ms, "q(ms|T)", allow_empty=True
    )
    return {
        "q_k1_given_T": q_k1,
        "q_k1_given_T_ci_low": k1_low,
        "q_k1_given_T_ci_high": k1_high,
        "q_k1_given_T_n_effective": k1_n,
        "q_ms_given_T": q_ms,
        "q_ms_given_T_ci_low": ms_low,
        "q_ms_given_T_ci_high": ms_high,
        "q_ms_given_T_n_effective": ms_n,
    }


def build_target_composition_table(
    response: pd.DataFrame,
    *,
    resample_seed: int = RESAMPLE_SEED,
    resample_count: int = RESAMPLE_COUNT,
) -> pd.DataFrame:
    rng = np.random.default_rng(resample_seed)
    rows: list[dict[str, Any]] = []
    for source in response.itertuples(index=False):
        n_total = int(source.N_T0_total)
        n_k1 = int(source.N_T0_k1)
        n_ms = int(source.N_T0_ms)
        if n_total != n_k1 + n_ms:
            raise ValueError(f"baseline target count closure failed for {source.condition}")
        rows.append({
            "condition": source.condition,
            "defect_phantom": source.defect_phantom,
            "slit": source.slit,
            "depth_mm": float(source.depth_mm),
            "N_T_total": n_total,
            "N_T_k1": n_k1,
            "N_T_ms": n_ms,
            **poisson_target_composition(
                n_k1, n_ms, rng, resample_count=resample_count
            ),
        })
    return pd.DataFrame(rows, columns=ST2_COLUMNS)


def build_target_fraction_table(t3: pd.DataFrame) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    for condition, phantom, slit, depth in CONDITIONS:
        target = t3[
            (t3.defect_phantom == phantom)
            & (t3.slit == slit)
            & (t3.condition_role == "baseline")
            & (t3.region == "Target")
        ].set_index("scatter_class")
        if set(target.index) != set(e2.CLASSES) or len(target) != 3:
            raise ValueError(f"formal baseline target fractions are incomplete for {condition}")
        output: dict[str, Any] = {
            "condition": condition,
            "defect_phantom": phantom,
            "slit": slit,
            "depth_mm": depth,
        }
        for scatter_class in e2.CLASSES:
            source = target.loc[scatter_class]
            output.update({
                f"f_T0_{scatter_class}": source.fraction,
                f"f_T0_{scatter_class}_ci_low": source.fraction_ci_low,
                f"f_T0_{scatter_class}_ci_high": source.fraction_ci_high,
                f"f_T0_{scatter_class}_n_effective": int(source.fraction_n_effective),
            })
        rows.append(output)
    return pd.DataFrame(rows, columns=ST3_COLUMNS)


def _errorbar(axis: plt.Axes, x: np.ndarray, table: pd.DataFrame, column: str,
              *, label: str, color: str, marker: str) -> None:
    point = table[column].to_numpy(dtype=float)
    low = table[f"{column}_ci_low"].to_numpy(dtype=float)
    high = table[f"{column}_ci_high"].to_numpy(dtype=float)
    axis.errorbar(
        x, 100.0 * point,
        yerr=np.vstack((100.0 * (point - low), 100.0 * (high - point))),
        color=color, marker=marker, linewidth=1.45, markersize=5.5,
        capsize=3.0, label=label,
    )


def plot_trends(composition: pd.DataFrame, fractions: pd.DataFrame, output: Path) -> None:
    depths = composition.depth_mm.to_numpy(dtype=float)
    if not np.array_equal(depths, fractions.depth_mm.to_numpy(dtype=float)):
        raise ValueError("composition and source-fraction depths do not match")
    fig, axes = plt.subplots(1, 2, figsize=(13.2, 5.2), sharex=True, sharey=True,
                             constrained_layout=True)
    _errorbar(axes[0], depths, composition, "q_k1_given_T", label=r"$q_{k1|T}$",
              color=e2.CLASS_COLORS["k1"], marker="o")
    _errorbar(axes[0], depths, composition, "q_ms_given_T", label=r"$q_{ms|T}$",
              color=e2.CLASS_COLORS["ms"], marker="s")
    axes[0].set_title("(a) Scatter-class composition within target-origin events")
    axes[0].set_ylabel("Fraction of detected events (%)")
    axes[0].legend(fontsize=9)

    for scatter_class, marker in zip(e2.CLASSES, ("o", "s", "^"), strict=True):
        _errorbar(
            axes[1], depths, fractions, f"f_T0_{scatter_class}",
            label=rf"$f_{{T,0}}^{{{scatter_class}}}$",
            color=e2.CLASS_COLORS[scatter_class], marker=marker,
        )
    axes[1].set_title("(b) Target-origin fraction within each scatter class")
    axes[1].legend(fontsize=9)
    for axis in axes:
        axis.set(xlabel="Matched target depth (mm)", xlim=(12.0, 93.0), ylim=(0.0, 100.0))
        axis.set_xticks(depths)
        axis.grid(alpha=0.2)
    fig.suptitle("E2 supplementary target-depth scatter composition (P0 baseline)")
    e2._save_png(fig, output)


def validate_outputs(output_dir: Path, *, resample_count: int = RESAMPLE_COUNT) -> None:
    entries = list(output_dir.iterdir())
    actual = {path.name for path in entries if path.is_file()}
    if actual != set(OUTPUT_NAMES) or any(path.is_dir() for path in entries):
        raise AssertionError(
            f"supplementary E2 output mismatch: expected {sorted(OUTPUT_NAMES)}, got {sorted(actual)}"
        )
    st1 = pd.read_csv(output_dir / ST1_TABLE_NAME)
    st2 = pd.read_csv(output_dir / ST2_TABLE_NAME)
    st3 = pd.read_csv(output_dir / ST3_TABLE_NAME)
    for table, columns, name in (
        (st1, ST1_COLUMNS, ST1_TABLE_NAME),
        (st2, ST2_COLUMNS, ST2_TABLE_NAME),
        (st3, ST3_COLUMNS, ST3_TABLE_NAME),
    ):
        if tuple(table.columns) != columns or len(table) != 6:
            raise AssertionError(f"{name} schema or row contract failed")
        if tuple(table.condition) != tuple(item[0] for item in CONDITIONS):
            raise AssertionError(f"{name} condition order contract failed")

    for role in ("T0", "TD"):
        if not np.array_equal(
            st1[f"N_{role}_total"].to_numpy(dtype=int),
            st1[f"N_{role}_k1"].to_numpy(dtype=int) + st1[f"N_{role}_ms"].to_numpy(dtype=int),
        ):
            raise AssertionError(f"supplementary E2 {role} target count closure failed")
    for scatter_class in e2.CLASSES:
        n0 = st1[f"N_T0_{scatter_class}"].to_numpy(dtype=float)
        nd = st1[f"N_TD_{scatter_class}"].to_numpy(dtype=float)
        expected = np.full(len(st1), np.nan, dtype=float)
        valid = n0 > 0
        expected[valid] = (nd[valid] - n0[valid]) / n0[valid]
        if not np.allclose(st1[f"C_T_{scatter_class}"], expected, equal_nan=True):
            raise AssertionError(f"supplementary E2 C_T count identity failed for {scatter_class}")
        if not st1[f"C_T_{scatter_class}_n_effective"].between(0, RESAMPLE_COUNT).all():
            raise AssertionError(f"supplementary E2 C_T effective draw count is invalid for {scatter_class}")

    defined = st2.N_T_total > 0
    undefined = ~defined
    if not (
        np.allclose(
            st2.loc[defined, "q_k1_given_T"] + st2.loc[defined, "q_ms_given_T"],
            1.0, rtol=0.0, atol=1e-12,
        )
        and st2.loc[undefined, ["q_k1_given_T", "q_ms_given_T"]].isna().all().all()
    ):
        raise AssertionError("supplementary E2 point composition does not close to one")
    if not st2.q_k1_given_T_n_effective.equals(st2.q_ms_given_T_n_effective):
        raise AssertionError("supplementary E2 q effective draw counts differ")
    if not st2.q_k1_given_T_n_effective.between(0, resample_count).all():
        raise AssertionError("supplementary E2 q effective draw count is invalid")
    for scatter_class in e2.CLASSES:
        if not st3[f"f_T0_{scatter_class}_n_effective"].between(0, RESAMPLE_COUNT).all():
            raise AssertionError(
                f"supplementary E2 source-fraction effective draw count is invalid for {scatter_class}"
            )
    ratio_columns = [
        column for table in (st2, st3) for column in table.columns
        if column.startswith(("q_", "f_T0_")) and not column.endswith("n_effective")
    ]
    values = pd.concat([
        st2[[column for column in ratio_columns if column in st2]],
        st3[[column for column in ratio_columns if column in st3]],
    ], axis=1)
    if not values.stack().between(0.0, 1.0, inclusive="both").all():
        raise AssertionError("supplementary E2 fraction or interval is outside [0,1]")
    if (output_dir / FIGURE_NAME).read_bytes()[:8] != b"\x89PNG\r\n\x1a\n":
        raise AssertionError("supplementary E2 trend figure is not a PNG")


def write_outputs(response: pd.DataFrame, composition: pd.DataFrame,
                  fractions: pd.DataFrame, output_dir: Path,
                  *, resample_count: int = RESAMPLE_COUNT) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    response.to_csv(output_dir / ST1_TABLE_NAME, index=False)
    composition.to_csv(output_dir / ST2_TABLE_NAME, index=False)
    fractions.to_csv(output_dir / ST3_TABLE_NAME, index=False)
    plot_trends(composition, fractions, output_dir / FIGURE_NAME)
    validate_outputs(output_dir, resample_count=resample_count)


def run_analysis(results_root: Path, output_dir: Path,
                 *, resample_count: int = RESAMPLE_COUNT) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    e2_root = results_root / "postprocessing" / "E2"
    t2_tables, t3, _ = load_formal_tables(e2_root)
    response = build_target_response_table(t2_tables)
    composition = build_target_composition_table(response, resample_count=resample_count)
    fractions = build_target_fraction_table(t3)
    write_outputs(response, composition, fractions, output_dir, resample_count=resample_count)
    return response, composition, fractions


def publish(staging: Path, output_dir: Path, overwrite: bool) -> None:
    if output_dir.exists():
        if not overwrite:
            raise FileExistsError(f"supplementary E2 output exists; pass --overwrite: {output_dir}")
        backup = output_dir.parent / f".{output_dir.name}.backup"
        if backup.exists():
            raise FileExistsError(f"stale supplementary E2 backup blocks overwrite: {backup}")
        output_dir.replace(backup)
        try:
            staging.replace(output_dir)
        except Exception:
            if output_dir.exists():
                shutil.rmtree(output_dir)
            backup.replace(output_dir)
            raise
        shutil.rmtree(backup)
    else:
        staging.replace(output_dir)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--results-root", type=Path, default=Path("results/articlev3_merged"))
    parser.add_argument("--output-dir", type=Path)
    parser.add_argument("--overwrite", action="store_true")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    results_root = args.results_root.resolve()
    e2_root = (results_root / "postprocessing" / "E2").resolve()
    supplementary_root = (e2_root / e2.SUPPLEMENTARY_DIR_NAME).resolve()
    output_dir = (
        args.output_dir.resolve()
        if args.output_dir is not None
        else supplementary_root / DEFAULT_SUBDIRECTORY
    )
    protected = {
        results_root, (results_root / "events").resolve(), e2_root,
        (e2_root / "figures").resolve(), (e2_root / "tables").resolve(), supplementary_root,
    }
    inside_protected_data = output_dir.is_relative_to((results_root / "events").resolve())
    inside_e2_outside_supplementary = (
        output_dir.is_relative_to(e2_root)
        and not output_dir.is_relative_to(supplementary_root)
    )
    if output_dir in protected or inside_protected_data or inside_e2_outside_supplementary:
        raise ValueError("supplementary output directory must not replace formal E2 data or outputs")
    output_dir.parent.mkdir(parents=True, exist_ok=True)
    staging = Path(tempfile.mkdtemp(prefix=f".{output_dir.name}.staging-", dir=output_dir.parent))
    try:
        response, composition, fractions = run_analysis(results_root, staging)
        publish(staging, output_dir, args.overwrite)
    except Exception:
        shutil.rmtree(staging, ignore_errors=True)
        raise

    print(f"supplementary E2 output: {output_dir}")
    print(f"formal extraction: {ST1_TABLE_NAME}, {ST3_TABLE_NAME}")
    print(f"new Poisson composition: {ST2_TABLE_NAME}; draws={RESAMPLE_COUNT}, seed={RESAMPLE_SEED}")
    print("target count closure: pass; q(k1|T)+q(ms|T): pass; formal F/T/B closure: pass")
    print(
        "q(k1|T): " + ", ".join(f"{100.0 * value:.2f}%" for value in composition.q_k1_given_T)
    )
    print(
        "q(ms|T): " + ", ".join(f"{100.0 * value:.2f}%" for value in composition.q_ms_given_T)
    )
    print(f"files: {len(TABLE_NAMES)} CSV + 1 PNG")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as error:
        print(f"target-scatter composition analysis error: {error}", file=sys.stderr)
        raise SystemExit(1) from error
