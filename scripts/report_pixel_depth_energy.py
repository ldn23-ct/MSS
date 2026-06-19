#!/usr/bin/env python3
"""Generate an energy-wise report for detector-bin source-depth analysis."""

from __future__ import annotations

import argparse
import math
import os
import re
import sys
from pathlib import Path
from typing import Any

try:
    os.environ.setdefault("MPLCONFIGDIR", "/tmp/mss_matplotlib")
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    import numpy as np
    import pandas as pd
    import yaml
except ModuleNotFoundError as error:  # pragma: no cover - exercised by CLI users.
    raise RuntimeError(
        "energy report generation requires the data environment. "
        "Run `conda activate data` or use `conda run -n data python ...`."
    ) from error


CASE_RE = re.compile(
    r"^near_door_(?P<system>open|collimated)_(?P<pose>[^_]+)_"
    r"(?P<model_state>[^_]+)_E(?P<energy>\d+)_seed(?P<seed>-?\d+)$"
)

SUMMARY_TABLE = "scatter_order_spatial_summary"
DEPTH_TABLE = "pixel_depth_summary_by_scatter_class"
LAG_TABLE = "bin_lag_distribution_metrics"
FRACTION_TABLE = "pixel_scatter_class_fraction"
MANIFEST_FILE = "analysis_manifest.yaml"
REGION_PRIMARY = "vehicle_only"
REGION_SENSITIVITY = "all_valid"
SCATTER_CLASSES = ("all", "k1", "k2", "k3", "kn", "km")
CONDITION_FIELDS = ["pose", "seed", "energy_keV", "collimator", "abnormal_present", "insert_name", "insert_material"]


def read_yaml(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as stream:
        value = yaml.safe_load(stream)
    if value is None:
        return {}
    if not isinstance(value, dict):
        raise ValueError(f"YAML root must be a map: {path}")
    return value


def format_value(value: Any) -> Any:
    if isinstance(value, (np.bool_, bool)):
        return bool(value)
    if isinstance(value, (np.floating, float)):
        value = float(value)
        if math.isnan(value):
            return "NaN"
        return f"{value:.12g}"
    if isinstance(value, (np.integer, int)):
        return int(value)
    return value


def write_csv(path: Path, frame: pd.DataFrame, columns: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    output = frame.copy()
    for column in columns:
        if column not in output.columns:
            output[column] = np.nan
    output = output[columns]
    if hasattr(output, "map"):
        output = output.map(format_value)
    else:
        output = output.applymap(format_value)
    output.to_csv(path, index=False)


def load_table(path: Path) -> pd.DataFrame:
    if not path.is_file():
        raise FileNotFoundError(f"required analysis file not found: {path}")
    frame = pd.read_csv(path, low_memory=False)
    bad_fields = [field for field in frame.columns if "|" in field]
    if bad_fields:
        raise ValueError(f"unsupported field names in {path}: {bad_fields}")
    return frame


def resolve_output_path(input_dir: Path, value: str) -> Path:
    path = Path(value)
    if path.is_absolute():
        return path
    return input_dir / path


def load_output_table(input_dir: Path, manifest: dict[str, Any], table_name: str, *, split_by_class: bool) -> pd.DataFrame:
    output_spec = manifest.get("outputs", {}).get(table_name)
    frames: list[pd.DataFrame] = []
    if isinstance(output_spec, dict) and isinstance(output_spec.get("files"), list):
        for item in output_spec["files"]:
            if not isinstance(item, dict) or "path" not in item:
                continue
            frame = load_table(resolve_output_path(input_dir, str(item["path"])))
            for column in ("energy_keV", "pose"):
                if column not in frame.columns and column in item:
                    frame[column] = item[column]
            if "collimator" not in frame.columns and "system" in item:
                frame["collimator"] = item["system"]
            if split_by_class and "scatter_class" not in frame.columns and "scatter_class" in item:
                frame["scatter_class"] = item["scatter_class"]
            frames.append(frame)
        return pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()

    if isinstance(output_spec, dict) and isinstance(output_spec.get("files"), dict):
        files = output_spec["files"]
        if split_by_class:
            for energy, class_map in files.items():
                if not isinstance(class_map, dict):
                    continue
                for scatter_class, path_text in class_map.items():
                    frame = load_table(resolve_output_path(input_dir, str(path_text)))
                    if "scatter_class" not in frame.columns:
                        frame["scatter_class"] = scatter_class
                    if "energy_keV" not in frame.columns:
                        frame["energy_keV"] = str(energy).lstrip("E").replace("p", ".")
                    frames.append(frame)
        else:
            for energy, path_text in files.items():
                frame = load_table(resolve_output_path(input_dir, str(path_text)))
                if "energy_keV" not in frame.columns:
                    frame["energy_keV"] = str(energy).lstrip("E").replace("p", ".")
                frames.append(frame)
        return pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()

    flat_path = input_dir / f"{table_name}.csv"
    return load_table(flat_path)


def as_bool(value: Any) -> bool:
    if isinstance(value, (bool, np.bool_)):
        return bool(value)
    text = str(value).strip().lower()
    if text in {"true", "1", "yes", "y"}:
        return True
    if text in {"false", "0", "no", "n", "", "nan", "none"}:
        return False
    return bool(value)


def model_state_from_compact(row: pd.Series) -> str:
    if not as_bool(row.get("abnormal_present", False)):
        return "normal"
    material = str(row.get("insert_material", "") or "")
    if material == "Vehicle_Flour":
        return "cavityFlour"
    if material == "G4_W":
        return "cavityW"
    if material:
        return "cavityPE"
    return "abnormal"


def parse_case(row: pd.Series) -> dict[str, Any]:
    case_id = str(row.get("case_id", "") or "")
    match = CASE_RE.match(case_id)
    if match:
        return {
            "system": match.group("system"),
            "pose": match.group("pose"),
            "model_state": match.group("model_state"),
            "seed": int(match.group("seed")),
        }
    system = "collimated" if int(float(row.get("collimator_enable", 0) or 0)) == 1 else "open"
    pose = str(row.get("pose_id", "") or "unknown_pose")
    model_type = str(row.get("model_type", "normal") or "normal")
    material = row.get("abnormal_material")
    if model_type == "normal" or pd.isna(material):
        model_state = "normal"
    elif str(material) == "Vehicle_Flour":
        model_state = "cavityFlour"
    elif str(material) == "G4_W":
        model_state = "cavityW"
    else:
        model_state = "cavityPE"
    return {
        "system": system,
        "pose": pose,
        "model_state": model_state,
        "seed": int(float(row.get("seed", 0) or 0)),
    }


def normalize_conditions(frame: pd.DataFrame) -> pd.DataFrame:
    normalized = frame.copy()
    if {"collimator", "pose", "abnormal_present"}.issubset(normalized.columns):
        normalized["system"] = normalized["collimator"].astype(str)
        normalized["pose"] = normalized["pose"].astype(str)
        normalized["model_state"] = normalized.apply(model_state_from_compact, axis=1)
        normalized["seed"] = pd.to_numeric(normalized.get("seed", 0), errors="coerce").fillna(0).astype(int)
        if "insert_name" not in normalized.columns:
            normalized["insert_name"] = ""
        if "insert_material" not in normalized.columns:
            normalized["insert_material"] = ""
        normalized["abnormal_present"] = normalized["abnormal_present"].apply(as_bool)
    else:
        parsed = normalized.apply(parse_case, axis=1, result_type="expand")
        for column in ("system", "pose", "model_state", "seed"):
            normalized[column] = parsed[column]
        normalized["collimator"] = normalized["system"]
        normalized["abnormal_present"] = normalized["model_state"].astype(str) != "normal"
        normalized["insert_name"] = normalized.get("selected_target_component", "")
        normalized["insert_material"] = normalized.get("abnormal_material", "")
    normalized["energy_keV"] = pd.to_numeric(normalized["energy_keV"], errors="coerce").astype("Int64")
    normalized["condition_id"] = (
        normalized["system"].astype(str)
        + "_"
        + normalized["pose"].astype(str)
        + "_"
        + normalized["model_state"].astype(str)
    )
    normalized["condition_label"] = normalized.apply(condition_label, axis=1)
    return normalized


def condition_label(row: pd.Series) -> str:
    system = str(row.get("system", ""))
    pose = str(row.get("pose", ""))
    state = str(row.get("model_state", ""))
    system_label = "准直" if system == "collimated" else "开口"
    pose_label = {"poseC": "Pose-C", "poseR": "Pose-R"}.get(pose, pose)
    state_label = {
        "normal": "normal",
        "cavityPE": "PE target",
        "cavityFlour": "Flour target",
        "cavityW": "W target",
    }.get(state, state)
    return f"{system_label} / {pose_label} / {state_label}"


def safe_name(text: str) -> str:
    return re.sub(r"[^A-Za-z0-9_.-]+", "_", text).strip("_") or "unknown"


def condition_output_dir(output_dir: Path, row: pd.Series | dict[str, Any]) -> Path:
    return (
        output_dir
        / "by_condition"
        / safe_name(str(row.get("system", "unknown")))
        / safe_name(str(row.get("pose", "unknown_pose")))
        / safe_name(str(row.get("model_state", "unknown")))
    )


def finite(series: pd.Series) -> pd.Series:
    values = pd.to_numeric(series, errors="coerce")
    return np.isfinite(values)


def add_sufficiency(frame: pd.DataFrame, min_valid_bins: int) -> pd.DataFrame:
    output = frame.copy()
    required = (
        (pd.to_numeric(output["n_valid_bins"], errors="coerce") >= min_valid_bins)
        & finite(output["spearman_rho"])
        & finite(output["median_width90"])
        & finite(output["median_separation_all_lags"])
        & finite(output["spatial_score"])
    )
    output["sufficient"] = required
    reasons: list[str] = []
    for _, row in output.iterrows():
        row_reasons: list[str] = []
        if pd.to_numeric(pd.Series([row.get("n_valid_bins")]), errors="coerce").iloc[0] < min_valid_bins:
            row_reasons.append("n_valid_bins < threshold")
        for field in ("spearman_rho", "median_width90", "median_separation_all_lags", "spatial_score"):
            value = pd.to_numeric(pd.Series([row.get(field)]), errors="coerce").iloc[0]
            if not math.isfinite(float(value)):
                row_reasons.append(f"{field} is NaN")
        reasons.append("; ".join(row_reasons) if row_reasons else "ok")
    output["sufficiency_reason"] = reasons
    return output


def build_spatial_metrics(summary: pd.DataFrame, min_valid_bins: int) -> pd.DataFrame:
    normalized = normalize_conditions(summary)
    normalized = add_sufficiency(normalized, min_valid_bins)
    keep = [
        "system",
        "model_state",
        *CONDITION_FIELDS,
        "condition_id",
        "condition_label",
        "region_filter",
        "scatter_class",
        "n_valid_hits",
        "n_valid_bins",
        "sufficient",
        "sufficiency_reason",
        "spearman_rho",
        "slope_depth_per_bin",
        "median_width90",
        "median_separation_all_lags",
        "spatial_score",
        "width_inflation_vs_k1",
        "sep_retention_vs_k1",
        "spatial_score_retention_vs_k1",
    ]
    return normalized[keep].sort_values(["region_filter", "condition_id", "energy_keV", "scatter_class"])


def build_retention(spatial: pd.DataFrame) -> pd.DataFrame:
    km = spatial[spatial["scatter_class"] == "km"].copy()
    k1 = spatial[spatial["scatter_class"] == "k1"].copy()
    key = [*CONDITION_FIELDS, "region_filter", "condition_id"]
    baseline = k1[
        [
            *key,
            "n_valid_hits",
            "n_valid_bins",
            "sufficient",
            "spearman_rho",
            "median_width90",
            "median_separation_all_lags",
            "spatial_score",
        ]
    ].rename(
        columns={
            "n_valid_hits": "k1_n_valid_hits",
            "n_valid_bins": "k1_n_valid_bins",
            "sufficient": "k1_sufficient",
            "spearman_rho": "k1_spearman_rho",
            "median_width90": "k1_median_width90",
            "median_separation_all_lags": "k1_median_separation",
            "spatial_score": "k1_spatial_score",
        }
    )
    output = km.merge(baseline, on=key, how="left")
    output = output.rename(
        columns={
            "n_valid_hits": "km_n_valid_hits",
            "n_valid_bins": "km_n_valid_bins",
            "sufficient": "km_sufficient",
            "spearman_rho": "km_spearman_rho",
            "median_width90": "km_median_width90",
            "median_separation_all_lags": "km_median_separation",
            "spatial_score": "km_spatial_score",
        }
    )
    output["both_sufficient"] = output["k1_sufficient"].fillna(False) & output["km_sufficient"].fillna(False)
    output["supports_ms_weakening"] = (
        output["both_sufficient"]
        & (pd.to_numeric(output["width_inflation_vs_k1"], errors="coerce") > 1.0)
        & (pd.to_numeric(output["sep_retention_vs_k1"], errors="coerce") < 1.0)
        & (pd.to_numeric(output["spatial_score_retention_vs_k1"], errors="coerce") < 1.0)
    )
    keep = [
        "system",
        "model_state",
        *CONDITION_FIELDS,
        "condition_id",
        "condition_label",
        "region_filter",
        "k1_n_valid_hits",
        "k1_n_valid_bins",
        "k1_sufficient",
        "km_n_valid_hits",
        "km_n_valid_bins",
        "km_sufficient",
        "both_sufficient",
        "k1_spearman_rho",
        "km_spearman_rho",
        "k1_median_width90",
        "km_median_width90",
        "width_inflation_vs_k1",
        "k1_median_separation",
        "km_median_separation",
        "sep_retention_vs_k1",
        "k1_spatial_score",
        "km_spatial_score",
        "spatial_score_retention_vs_k1",
        "supports_ms_weakening",
    ]
    return output[keep].sort_values(["region_filter", "condition_id", "energy_keV"])


def build_sufficiency(spatial: pd.DataFrame) -> pd.DataFrame:
    keep = [
        "system",
        "model_state",
        *CONDITION_FIELDS,
        "condition_id",
        "condition_label",
        "region_filter",
        "scatter_class",
        "n_valid_hits",
        "n_valid_bins",
        "sufficient",
        "sufficiency_reason",
    ]
    return spatial[keep].sort_values(["region_filter", "condition_id", "energy_keV", "scatter_class"])


def aggregate_by_energy(spatial: pd.DataFrame, retention: pd.DataFrame, region_filter: str) -> tuple[pd.DataFrame, pd.DataFrame]:
    sub = spatial[(spatial["region_filter"] == region_filter) & (spatial["scatter_class"].isin(["k1", "km"]))].copy()
    sufficient = sub[sub["sufficient"]].copy()
    metrics = (
        sufficient.groupby(["energy_keV", "scatter_class"], dropna=False)
        .agg(
            sufficient_conditions=("condition_id", "nunique"),
            median_abs_spearman=("spearman_rho", lambda s: float(np.nanmedian(np.abs(pd.to_numeric(s, errors="coerce"))))),
            median_width90=("median_width90", "median"),
            median_separation=("median_separation_all_lags", "median"),
            median_spatial_score=("spatial_score", "median"),
        )
        .reset_index()
    )
    ret = retention[(retention["region_filter"] == region_filter) & (retention["both_sufficient"])].copy()
    if ret.empty:
        retention_energy = pd.DataFrame(
            columns=[
                "energy_keV",
                "sufficient_pairs",
                "median_width_inflation_vs_k1",
                "median_sep_retention_vs_k1",
                "median_spatial_score_retention_vs_k1",
                "weakening_support_fraction",
            ]
        )
    else:
        retention_energy = (
            ret.groupby("energy_keV", dropna=False)
            .agg(
                sufficient_pairs=("condition_id", "nunique"),
                median_width_inflation_vs_k1=("width_inflation_vs_k1", "median"),
                median_sep_retention_vs_k1=("sep_retention_vs_k1", "median"),
                median_spatial_score_retention_vs_k1=("spatial_score_retention_vs_k1", "median"),
                weakening_support_fraction=("supports_ms_weakening", "mean"),
            )
            .reset_index()
        )
    return metrics, retention_energy


def plot_k1_km_metric(
    output_dir: Path,
    energy_metrics: pd.DataFrame,
    metric: str,
    ylabel: str,
    filename: str,
) -> Path:
    path = output_dir / filename
    fig, ax = plt.subplots(figsize=(8.5, 4.5), constrained_layout=True)
    for scatter_class, label in (("k1", "k1"), ("km", "km")):
        part = energy_metrics[energy_metrics["scatter_class"] == scatter_class].sort_values("energy_keV")
        if part.empty:
            continue
        ax.plot(part["energy_keV"], part[metric], marker="o", linewidth=1.4, label=label)
    ax.set_xlabel("energy (keV)")
    ax.set_ylabel(ylabel)
    ax.set_title(ylabel + " vs energy")
    ax.grid(True, alpha=0.25)
    ax.legend()
    fig.savefig(path, dpi=150)
    plt.close(fig)
    return path


def plot_retention(output_dir: Path, retention_energy: pd.DataFrame) -> Path:
    path = output_dir / "spatial_score_retention_vs_energy.png"
    fig, ax = plt.subplots(figsize=(8.5, 4.5), constrained_layout=True)
    part = retention_energy.sort_values("energy_keV")
    ax.plot(
        part["energy_keV"],
        part["median_spatial_score_retention_vs_k1"],
        marker="o",
        linewidth=1.4,
        label="median km/k1 spatial score",
    )
    ax.axhline(1.0, color="0.35", linestyle="--", linewidth=1.0)
    ax.set_xlabel("energy (keV)")
    ax.set_ylabel("spatial score retention vs k1")
    ax.set_title("km spatial score retention vs energy")
    ax.grid(True, alpha=0.25)
    ax.legend()
    fig.savefig(path, dpi=150)
    plt.close(fig)
    return path


def representative_conditions(spatial: pd.DataFrame, max_count: int = 3) -> list[str]:
    candidates = spatial[
        (spatial["region_filter"] == REGION_PRIMARY)
        & (spatial["scatter_class"] == "k1")
        & (spatial["sufficient"])
    ]
    preferred = [
        "collimated_poseC_normal",
        "collimated_poseC_cavityPE",
        "collimated_poseC_cavityFlour",
    ]
    found: list[str] = []
    available = set(candidates["condition_id"])
    for item in preferred:
        if item in available:
            found.append(item)
    for item in sorted(available):
        if item not in found:
            found.append(item)
        if len(found) >= max_count:
            break
    return found[:max_count]


def plot_median_depth_by_energy(output_dir: Path, depth: pd.DataFrame, conditions: list[str]) -> list[Path]:
    paths: list[Path] = []
    normalized = normalize_conditions(depth)
    for condition in conditions:
        part = normalized[
            (normalized["condition_id"] == condition)
            & (normalized["region_filter"] == REGION_PRIMARY)
            & (normalized["scatter_class"].isin(["k1", "km"]))
        ].copy()
        if part.empty:
            continue
        energies = sorted(int(value) for value in part["energy_keV"].dropna().unique())
        fig, axes = plt.subplots(
            len(energies),
            1,
            figsize=(9.0, max(2.2, 1.9 * len(energies))),
            sharex=True,
            constrained_layout=True,
        )
        if len(energies) == 1:
            axes = [axes]
        for ax, energy in zip(axes, energies):
            energy_part = part[part["energy_keV"] == energy]
            for scatter_class in ("k1", "km"):
                curve = energy_part[energy_part["scatter_class"] == scatter_class]
                curve = curve[pd.to_numeric(curve["count"], errors="coerce") > 0]
                if curve.empty:
                    continue
                ax.plot(curve["bin_center_mm"], curve["median"], linewidth=1.1, label=scatter_class)
            ax.set_ylabel(f"{energy} keV")
            ax.grid(True, alpha=0.25)
        axes[0].legend(loc="best")
        axes[-1].set_xlabel("detector x bin center (mm)")
        fig.supylabel("median last_scatter_z (mm)")
        fig.suptitle(f"Median source depth by energy | {condition}")
        path = output_dir / f"median_depth_vs_bin_by_energy_{condition}.png"
        fig.savefig(path, dpi=150)
        plt.close(fig)
        paths.append(path)
    return paths


def markdown_table(frame: pd.DataFrame, columns: list[str], max_rows: int | None = None) -> str:
    data = frame[columns].copy()
    if max_rows is not None:
        data = data.head(max_rows)
    if data.empty:
        return "_无可用数据_"
    headers = [str(column) for column in data.columns]
    rows: list[list[str]] = []
    for _, row in data.iterrows():
        rows.append([str(format_value(row[column])) for column in data.columns])
    lines = [
        "| " + " | ".join(headers) + " |",
        "| " + " | ".join("---" for _ in headers) + " |",
    ]
    lines.extend("| " + " | ".join(row) + " |" for row in rows)
    return "\n".join(lines)


def sentence_for_energy(retention_energy: pd.DataFrame) -> str:
    if retention_energy.empty:
        return "没有足够的 k1/km 配对条件支持能量趋势判断。"
    valid = retention_energy.sort_values("energy_keV")
    support = valid[valid["weakening_support_fraction"] >= 0.5]
    if support.empty:
        return "在当前充分样本条件下，多重散射弱化判据未形成稳定多数支持。"
    energies = ", ".join(str(int(value)) for value in support["energy_keV"])
    return f"在 {energies} keV 的充分样本条件中，至少半数条件满足 width 增大、separation 降低和 spatial score retention < 1 的组合判据。"


def build_report(
    output_dir: Path,
    manifest: dict[str, Any],
    spatial: pd.DataFrame,
    retention: pd.DataFrame,
    sufficiency: pd.DataFrame,
    energy_metrics: pd.DataFrame,
    retention_energy: pd.DataFrame,
    plots: list[Path],
) -> str:
    energies = sorted(int(value) for value in spatial["energy_keV"].dropna().unique())
    primary = spatial[spatial["region_filter"] == REGION_PRIMARY]
    sufficient_primary = primary[primary["sufficient"]]
    insufficient_energies = sorted(
        int(value)
        for value in primary.loc[~primary["sufficient"], "energy_keV"].dropna().unique()
    )
    k1 = energy_metrics[energy_metrics["scatter_class"] == "k1"]
    km = energy_metrics[energy_metrics["scatter_class"] == "km"]
    k1km = k1.merge(km, on="energy_keV", how="outer", suffixes=("_k1", "_km")).sort_values("energy_keV")
    overview_columns = [
        "energy_keV",
        "sufficient_conditions_k1",
        "median_width90_k1",
        "median_width90_km",
        "median_separation_k1",
        "median_separation_km",
        "median_spatial_score_k1",
        "median_spatial_score_km",
    ]
    retention_columns = [
        "energy_keV",
        "sufficient_pairs",
        "median_width_inflation_vs_k1",
        "median_sep_retention_vs_k1",
        "median_spatial_score_retention_vs_k1",
        "weakening_support_fraction",
    ]
    lines = [
        "# 不同能量下像素 Bin 来源深度分析报告",
        "",
        "## 数据与方法",
        "",
        f"- 输入后处理目录：`{manifest.get('output_dir', 'results/analysis/pixel_depth')}`。",
        f"- 发现 run 数：{manifest.get('discovered_run_count', 'unknown')}；分析 run 数：{manifest.get('analyzed_run_count', 'unknown')}；跳过 run 数：{manifest.get('skipped_run_count', 'unknown')}。",
        f"- 能量点：{', '.join(str(value) for value in energies)} keV。",
        f"- detector bin：`{manifest.get('axis', 'det_x')}`，bin 宽度 `{manifest.get('bin_width_mm', 1.0)} mm`。",
        "- 深度定义：`source_depth = last_scatter_z`。",
        "- 主分析 region filter：`vehicle_only`；`all_valid` 只作为敏感性对照。",
        "- scatter class：`all`, `k1`, `k2`, `k3`, `kn (>=4)`, `km (>=2)`；`km` 是多重散射汇总组。",
        "",
        "## 能量维度总览",
        "",
        markdown_table(k1km, overview_columns),
        "",
        "## 核心问题回答",
        "",
        "### 1. 每个 detector bin 的粒子来源深度如何表征？",
        "",
        "每个 bin 使用 `last_scatter_z` 的经验分布表征，并输出 count、mean、std、q05、q25、median、q75、q95、IQR 与 width90。报告中的能量趋势主要使用每个 bin 的 median depth 和 width90；完整逐 bin 数值见 `pixel_depth_summary_by_scatter_class/E*/<scatter_class>.csv`。",
        "",
        "### 2. 不同 bin 之间的来源深度分布是否不同？",
        "",
        "使用 bin index 与 median depth 的 Spearman 相关、median depth slope、不同 lag 下的 Wasserstein-1 / KS，以及归一化 separation score 衡量。当前充分样本条件数为 "
        f"{len(sufficient_primary)} / {len(primary)}（vehicle_only）。",
        "",
        "### 3. 不同散射阶次下区分能力如何变化？",
        "",
        "k1 与 km 的能量聚合对比如上表。通常需要同时看 width90、separation 和 spatial score：width90 越大表示来源深度分布越宽；separation 越低表示相邻或间隔 bin 的分布差异相对变小；spatial score 将相关性和 separation 合并为一个粗略空间区分指标。",
        "",
        "### 4. km 相对 k1 是否削弱空间区分？",
        "",
        markdown_table(retention_energy, retention_columns),
        "",
        sentence_for_energy(retention_energy),
        "",
        "判据只作为统计比较：`width_inflation_vs_k1 > 1`、`sep_retention_vs_k1 < 1`、`spatial_score_retention_vs_k1 < 1` 同时满足时，记为支持多重散射削弱 bin 对来源深度的区分作用。",
        "",
        "### 5. region 过滤对解释有什么影响？",
        "",
        "`vehicle_only` 是主结论来源，因为它排除了非车辆或无法归因的 last scatter region。`all_valid` 保留全部有限 last scatter hit，可用于检查非车辆 region 是否改变趋势；若二者趋势不一致，应优先报告 vehicle_only，同时把 all_valid 作为敏感性差异。",
        "",
        "## 样本充分性与限制",
        "",
        f"- insufficient energy 条件中出现的能量点：{', '.join(str(value) for value in insufficient_energies) if insufficient_energies else '无'}。",
        "- `n_valid_bins < 3` 或关键指标为 NaN 的条件不参与趋势判断。",
        "- 本报告不重新运行 Geant4，不改变事件级 CSV，不自动给出最终物理定论。",
        "",
        "## 输出图像",
        "",
    ]
    lines.extend(f"- `{path.as_posix()}`" for path in plots)
    lines.extend(
        [
            "",
            "## 配套输出",
            "",
            "- `energy_spatial_metrics.csv`",
            "- `energy_k1_vs_km_retention.csv`",
            "- `energy_sample_sufficiency.csv`",
        ]
    )
    return "\n".join(lines) + "\n"


def generate_report(input_dir: Path, output_dir: Path, min_valid_bins: int = 3) -> dict[str, Any]:
    manifest = read_yaml(input_dir / MANIFEST_FILE)
    summary = load_output_table(input_dir, manifest, SUMMARY_TABLE, split_by_class=True)
    depth = load_output_table(input_dir, manifest, DEPTH_TABLE, split_by_class=True)
    _lag = load_output_table(input_dir, manifest, LAG_TABLE, split_by_class=True)
    _fraction = load_output_table(input_dir, manifest, FRACTION_TABLE, split_by_class=False)

    output_dir.mkdir(parents=True, exist_ok=True)
    spatial_all = build_spatial_metrics(summary, min_valid_bins)
    retention_all = build_retention(spatial_all)
    sufficiency_all = build_sufficiency(spatial_all)
    depth_all = normalize_conditions(depth)

    condition_keys = (
        spatial_all[["system", "pose", "model_state"]]
        .drop_duplicates()
        .sort_values(["system", "pose", "model_state"])
    )
    index_rows: list[dict[str, Any]] = []
    report_paths: list[Path] = []
    for _, condition in condition_keys.iterrows():
        mask = (
            (spatial_all["system"].astype(str) == str(condition["system"]))
            & (spatial_all["pose"].astype(str) == str(condition["pose"]))
            & (spatial_all["model_state"].astype(str) == str(condition["model_state"]))
        )
        spatial = spatial_all[mask].copy()
        retention = retention_all[
            (retention_all["system"].astype(str) == str(condition["system"]))
            & (retention_all["pose"].astype(str) == str(condition["pose"]))
            & (retention_all["model_state"].astype(str) == str(condition["model_state"]))
        ].copy()
        sufficiency = sufficiency_all[
            (sufficiency_all["system"].astype(str) == str(condition["system"]))
            & (sufficiency_all["pose"].astype(str) == str(condition["pose"]))
            & (sufficiency_all["model_state"].astype(str) == str(condition["model_state"]))
        ].copy()
        depth_part = depth_all[
            (depth_all["system"].astype(str) == str(condition["system"]))
            & (depth_all["pose"].astype(str) == str(condition["pose"]))
            & (depth_all["model_state"].astype(str) == str(condition["model_state"]))
        ].copy()
        condition_dir = condition_output_dir(output_dir, condition)
        condition_dir.mkdir(parents=True, exist_ok=True)
        plots_dir = condition_dir / "plots"
        plots_dir.mkdir(parents=True, exist_ok=True)

        energy_metrics, retention_energy = aggregate_by_energy(spatial, retention, REGION_PRIMARY)
        spatial_path = condition_dir / "energy_spatial_metrics.csv"
        retention_path = condition_dir / "energy_k1_vs_km_retention.csv"
        sufficiency_path = condition_dir / "energy_sample_sufficiency.csv"
        energy_metrics_path = condition_dir / "energy_aggregated_metrics.csv"
        retention_energy_path = condition_dir / "energy_aggregated_retention.csv"

        write_csv(spatial_path, spatial, list(spatial.columns))
        write_csv(retention_path, retention, list(retention.columns))
        write_csv(sufficiency_path, sufficiency, list(sufficiency.columns))
        write_csv(energy_metrics_path, energy_metrics, list(energy_metrics.columns))
        write_csv(retention_energy_path, retention_energy, list(retention_energy.columns))

        plots = [
            plot_k1_km_metric(
                plots_dir,
                energy_metrics,
                "median_width90",
                "median width90 (mm)",
                "k1_km_width90_vs_energy.png",
            ),
            plot_k1_km_metric(
                plots_dir,
                energy_metrics,
                "median_separation",
                "median separation score",
                "k1_km_separation_vs_energy.png",
            ),
            plot_retention(plots_dir, retention_energy),
        ]
        conditions = representative_conditions(spatial)
        plots.extend(plot_median_depth_by_energy(plots_dir, depth_part, conditions))

        report_text = build_report(
            condition_dir,
            manifest,
            spatial,
            retention,
            sufficiency,
            energy_metrics,
            retention_energy,
            plots,
        )
        report_path = condition_dir / "report.md"
        report_path.write_text(report_text, encoding="utf-8")
        report_paths.append(report_path)
        index_rows.append(
            {
                "system": condition["system"],
                "pose": condition["pose"],
                "model_state": condition["model_state"],
                "condition_dir": condition_dir.relative_to(output_dir).as_posix(),
                "report": report_path.as_posix(),
                "energy_spatial_metrics": spatial_path.as_posix(),
                "energy_k1_vs_km_retention": retention_path.as_posix(),
                "energy_sample_sufficiency": sufficiency_path.as_posix(),
                "energy_aggregated_metrics": energy_metrics_path.as_posix(),
                "energy_aggregated_retention": retention_energy_path.as_posix(),
                "plots_dir": plots_dir.as_posix(),
            }
        )

    index_path = output_dir / "energy_report_index.csv"
    write_csv(index_path, pd.DataFrame(index_rows), list(index_rows[0].keys()) if index_rows else [
        "system",
        "pose",
        "model_state",
        "condition_dir",
        "report",
        "energy_spatial_metrics",
        "energy_k1_vs_km_retention",
        "energy_sample_sufficiency",
        "energy_aggregated_metrics",
        "energy_aggregated_retention",
        "plots_dir",
    ])

    return {
        "index": index_path,
        "reports_dir": output_dir / "by_condition",
        "condition_reports": report_paths,
        "condition_count": len(report_paths),
        "report": report_paths[0] if report_paths else index_path,
    }


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input-dir", type=Path, default=Path("results/analysis/pixel_depth"))
    parser.add_argument("--output-dir", type=Path, default=Path("results/analysis/pixel_depth_energy"))
    parser.add_argument("--min-valid-bins", type=int, default=3)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        outputs = generate_report(args.input_dir, args.output_dir, args.min_valid_bins)
    except Exception as error:
        print(f"pixel-depth energy report error: {error}", file=sys.stderr)
        return 2
    print(f"Report index: {outputs['index']}")
    print(f"Condition report count: {outputs['condition_count']}")
    print(f"Reports dir: {outputs['reports_dir']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
