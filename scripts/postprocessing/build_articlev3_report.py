#!/usr/bin/env python3
"""Build the filled Article V3 merged-data report from accepted E1--E3 outputs."""

from __future__ import annotations

import argparse
from pathlib import Path

import numpy as np
import pandas as pd
import yaml

from scripts.postprocessing.e2 import run_section_3_2 as section32


def pct(value: float, digits: int = 1) -> str:
    return f"{100.0 * float(value):.{digits}f}%"


def num(value: float, digits: int = 2) -> str:
    return f"{float(value):.{digits}f}"


def interval(row: pd.Series, low: str, high: str, *, percent: bool = False) -> str:
    if pd.isna(row[low]) or pd.isna(row[high]):
        return "NA"
    if percent:
        return f"[{pct(row[low])}, {pct(row[high])}]"
    return f"[{num(row[low])}, {num(row[high])}]"


def percent_interval_n(row: pd.Series, prefix: str, digits: int = 2) -> str:
    return (
        f"{pct(row[prefix], digits)} "
        f"({interval(row, prefix + '_ci_low', prefix + '_ci_high', percent=True)}; "
        f"n_effective={int(row[prefix + '_n_effective'])})"
    )


def method_value(table: pd.DataFrame, phantom: str, method: str) -> pd.Series:
    rows = table[table.phantom.eq(phantom) & table.method.eq(method)]
    if len(rows) != 1:
        raise ValueError(f"expected one E3 metric row for {phantom}/{method}")
    return rows.iloc[0]


def comparison_value(table: pd.DataFrame, phantom: str, comparison: str) -> pd.Series:
    rows = table[table.phantom.eq(phantom) & table.comparison.eq(comparison)]
    if len(rows) != 1:
        raise ValueError(f"expected one E3 comparison row for {phantom}/{comparison}")
    return rows.iloc[0]


def build_report(results_root: Path, slab_root: Path) -> str:
    e1 = results_root / "postprocessing" / "E1"
    e2 = results_root / "postprocessing" / "E2"
    e3 = results_root / "postprocessing" / "E3"
    e2_section32 = e2 / "supplementary" / section32.DEFAULT_SUBDIRECTORY
    e2_section32_acceptance = e2_section32 / section32.ACCEPTANCE_NAME
    e2_table6_path = e2_section32 / section32.TABLE6_NAME
    e2_dtv_path = e2_section32 / section32.DTV_NAME
    e2_composition_path = e2_section32 / section32.COMPOSITION_NAME
    e2_validation_path = e2_section32 / section32.VALIDATION_NAME
    e3_supplementary = e3 / "supplementary" / "center3x3_first_scatter_depth"
    required = (
        e1 / "acceptance_summary.yaml",
        e2 / "acceptance_summary.yaml",
        e2_section32_acceptance,
        e2 / "tables" / "E2-T1_zero_pose_raw_count_decomposition.csv",
        e3 / "E3_T1_P4_S4_metrics.csv",
        e3 / "E3_T2_depth_method_metrics.csv",
        e3 / "E3_T3_depth_comparisons.csv",
        e3 / "E3_T4_front_removal_reference_metrics.csv",
        e3 / "E3_F6_front_removal_reference.png",
        slab_root / "reference_manifest.yaml",
        slab_root / "events" / "valid" / "valid_events_manifest.yaml",
        slab_root / "events" / "valid" / "valid_events_summary.csv",
        e2_table6_path,
        e2_dtv_path,
        e2_composition_path,
        e2_validation_path,
        *(e2_section32 / name for name in section32.FIG5_NAMES.values()),
        e2_section32 / section32.COMPOSITION_FIGURE_NAME,
        *(e3_supplementary / name for name in (
            "E3_SF1_P4_S4_front_components_depth.png",
            "E3_SF2_P4_S4_truth_front_vs_slab_overlay.png",
            "E3_SF3_P4_S4_truth_front_roi_depth.png",
            "E3_ST1_P4_S4_front_source_summary.csv",
        )),
    )
    missing = [path for path in required if not path.is_file()]
    if missing:
        raise FileNotFoundError("missing accepted report inputs: " + ", ".join(map(str, missing)))
    for acceptance in (required[0], required[1], e2_section32_acceptance):
        value = yaml.safe_load(acceptance.read_text(encoding="utf-8"))
        if value.get("overall_status") != "pass":
            raise ValueError(f"analysis acceptance is not pass: {acceptance}")

    t1 = pd.read_csv(e2 / "tables" / "E2-T1_zero_pose_raw_count_decomposition.csv")
    table6 = pd.read_csv(e2_table6_path)
    dtv_non_t = pd.read_csv(e2_dtv_path)
    source_composition = pd.read_csv(e2_composition_path)
    section32_validation = pd.read_csv(e2_validation_path)
    p4 = pd.read_csv(e3 / "E3_T1_P4_S4_metrics.csv")
    methods = pd.read_csv(e3 / "E3_T2_depth_method_metrics.csv")
    comparisons = pd.read_csv(e3 / "E3_T3_depth_comparisons.csv")
    reference = pd.read_csv(e3 / "E3_T4_front_removal_reference_metrics.csv")
    reference_manifest = yaml.safe_load(
        (slab_root / "reference_manifest.yaml").read_text(encoding="utf-8")
    )
    slab_valid_manifest = yaml.safe_load(
        (slab_root / "events" / "valid" / "valid_events_manifest.yaml").read_text(
            encoding="utf-8"
        )
    )
    slab_valid_summary = pd.read_csv(
        slab_root / "events" / "valid" / "valid_events_summary.csv"
    )
    supplementary = pd.read_csv(
        e3_supplementary / "E3_ST1_P4_S4_front_source_summary.csv"
    )
    if (
        tuple(reference.image) != ("M0", "M5", "reference_subtracted")
        or reference.cnr_n_effective.le(0).any()
    ):
        raise ValueError("E3-T4 front-removal reference table failed its report contract")
    if (
        reference_manifest.get("reference_type") != "uniform_pmma_front_slab"
        or float(reference_manifest.get("thickness_mm", 0)) != 55.0
        or reference_manifest.get("vehicle_model_id") != "P4_front_slab_55mm"
        or reference_manifest.get("campaign_id")
        != "articlev3_p4_front_slab_55mm_100m"
        or int(reference_manifest.get("pose_count", 0)) != 81
        or int(reference_manifest.get("n_primary_per_pose", 0)) != 100_000_000
        or int(reference_manifest.get("seed_start", 0)) != 11_000
        or int(reference_manifest.get("seed_end", 0)) != 11_080
    ):
        raise ValueError("slab reference manifest failed its report contract")
    if (
        int(slab_valid_manifest.get("input_file_count", 0)) != 81
        or len(slab_valid_summary) != 81
        or int(slab_valid_summary.rows_read.sum())
        != int(slab_valid_manifest.get("total_rows_read", -1))
        or int(slab_valid_summary.rows_kept.sum())
        != int(slab_valid_manifest.get("total_rows_kept", -1))
    ):
        raise ValueError("slab valid-event manifest failed its report contract")
    if (
        len(supplementary) != 1
        or not {"alpha", "truth_front_total_count", "slab_front_total_count",
                "slab_to_truth_ratio", "slab_fraction_z_lt55", "pearson_r_z_lt55"}
        .issubset(supplementary.columns)
    ):
        raise ValueError("E3 supplementary front-source summary failed its report contract")
    supplementary_row = supplementary.iloc[0]
    if not (
        float(supplementary_row.alpha) > 0
        and float(supplementary_row.truth_front_total_count) > 0
        and float(supplementary_row.slab_front_total_count) > 0
        and 0 <= float(supplementary_row.slab_fraction_z_lt55) <= 1
        and -1 <= float(supplementary_row.pearson_r_z_lt55) <= 1
    ):
        raise ValueError("E3 supplementary front-source metrics are invalid")
    phantoms = [f"P{i}" for i in range(1, 7)]
    depths = dict(zip(phantoms, (15, 30, 45, 60, 75, 90), strict=True))
    expected_conditions = tuple(f"P{i}-S{i}" for i in range(1, 7))
    expected_depths = tuple(depths[phantom] for phantom in phantoms)
    for table, columns, count, label in (
        (table6, section32.TABLE6_COLUMNS, 18, "section 3.2 contribution table"),
        (dtv_non_t, section32.DTV_COLUMNS, 18, "section 3.2 DTV table"),
        (source_composition, section32.COMPOSITION_COLUMNS, 6, "section 3.2 source composition"),
        (section32_validation, section32.VALIDATION_COLUMNS, 18, "section 3.2 validation"),
    ):
        if (
            tuple(table.columns) != columns
            or len(table) != count
            or set(table.condition) != set(expected_conditions)
        ):
            raise ValueError(f"{label} failed its report contract")
    if (
        not np.allclose(
            table6.C, table6.Gamma_T + table6.Gamma_nonT, rtol=0.0, atol=1e-12
        )
        or not section32_validation.abs_Gamma_T_gt_abs_Gamma_nonT.all()
        or not section32_validation.C_table5_rounding_match.all()
        or not np.allclose(
            source_composition[["w_F", "w_T", "w_B"]].sum(axis=1),
            1.0,
            rtol=0.0,
            atol=1e-12,
        )
    ):
        raise ValueError("section 3.2 numerical identities failed its report contract")
    dtv_values = dtv_non_t[["D_TV_F", "D_TV_B", "D_TV_nonT"]].to_numpy(dtype=float)
    if not np.all(np.isnan(dtv_values) | ((dtv_values >= 0.0) & (dtv_values <= 1.0))):
        raise ValueError("section 3.2 DTV values fall outside [0, 1]")
    reference_by_image = reference.set_index("image")
    slab_rows_read = int(slab_valid_manifest["total_rows_read"])
    slab_rows_kept = int(slab_valid_manifest["total_rows_kept"])
    slab_rows_dropped = slab_rows_read - slab_rows_kept
    slab_rows_dropped_nonfinite = int(
        slab_valid_manifest["total_rows_dropped_nonfinite_depth"]
    )
    slab_rows_dropped_negative = int(
        slab_valid_manifest["total_rows_dropped_negative_depth"]
    )
    slab_image_count = int(
        reference_by_image.loc["M0", "count_metric"]
        - reference_by_image.loc["reference_subtracted", "count_metric"]
    )

    t_dominant_count = int(section32_validation.abs_Gamma_T_gt_abs_Gamma_nonT.sum())
    opposite_count = int(section32_validation.nonT_direction.eq("opposes_T").sum())
    composition_by_condition = source_composition.set_index("condition")
    first_composition = composition_by_condition.loc["P1-S1"]
    last_composition = composition_by_condition.loc["P6-S6"]
    ordered_composition = source_composition.sort_values("depth_mm")
    composition_trends: dict[str, str] = {}
    for region in ("F", "T", "B"):
        values = ordered_composition[f"w_{region}"].to_numpy(dtype=float)
        if np.all(np.diff(values) > 0):
            composition_trends[region] = "严格增加"
        elif np.all(np.diff(values) < 0):
            composition_trends[region] = "严格下降"
        else:
            composition_trends[region] = "存在起伏"
    dtv_summaries: dict[str, dict[str, str]] = {}
    for scatter_class in ("total", "k1", "ms"):
        selected = dtv_non_t[dtv_non_t.scatter_class.eq(scatter_class)].set_index(
            "condition"
        ).D_TV_nonT
        finite = selected.dropna()
        if finite.empty:
            dtv_summaries[scatter_class] = {
                "minimum": "NA",
                "maximum": "NA",
                "range": "NA",
                "minimum_condition": "NA",
                "maximum_condition": "NA",
                "trend": "全部为 NA，无法判定",
            }
            continue
        values = finite.to_numpy(dtype=float)
        if len(finite) != len(selected):
            trend = "含 NA，无法判定完整序列单调性"
        elif np.all(np.diff(values) > 0):
            trend = "严格增加"
        elif np.all(np.diff(values) < 0):
            trend = "严格下降"
        else:
            trend = "存在下降或起伏，不是单调增加"
        dtv_summaries[scatter_class] = {
            "minimum": f"{values.min():.3f}",
            "maximum": f"{values.max():.3f}",
            "range": f"{values.max() - values.min():.3f}",
            "minimum_condition": str(finite.idxmin()).replace("-", "–"),
            "maximum_condition": str(finite.idxmax()).replace("-", "–"),
            "trend": trend,
        }

    base = "../../results/articlev3_merged/postprocessing"
    lines: list[str] = [
        "# PMMA–空气缺陷 X 射线背散射蒙特卡罗实验报告",
        "",
        "> 数据版本：`results/articlev3_merged` + `results/articlev3_p4_front_slab_55mm_100m`。更新日期：2026-09-11。E1、E2 与包含 55 mm PMMA 前层参考的严格 E3 均已完成。",
        "",
        "## 1. 实验目的与结论摘要",
        "",
        "本实验使用 Geant4 蒙特卡罗真值研究多狭缝背散射系统的深度选择响应、局部空气缺陷响应，以及按首次散射深度和散射阶次选择事件后的二维成像表现。证据链按照 E1 系统基线、E2 缺陷响应分解和 E3 source-truth 成像比较组织。",
        "",
        "主要数据层结论如下：",
        "",
        "- S1–S6 在探测面形成可分离接受区域，独立归一化的主要首次散射深度随狭缝编号有序向深部移动。",
        "- 100M histories/pose 的完整网格中，P1–P6 原始 total 图像均呈现与 10×10 mm² 缺陷位置一致的低计数区；可见性随深度降低，但 P6 仍可辨识。",
        "- 零位姿 total 相对计数变化从 P1 的 −55.5% 单调减弱至 P6 的 −12.7%；k1 和 ms 在全部深度均显示统计可测的负响应。",
        f"- 第 3.2 节的原始事件重算显示，{t_dominant_count}/18 个条件均有 $|\\Gamma_T|>|\\Gamma_{{nonT}}|$；其中 {opposite_count} 个 non-T 项反向抵消 T 项，{18 - opposite_count} 个同向叠加。",
        f"- baseline total 的 F 占比由 {pct(first_composition.w_F)} 增至 {pct(last_composition.w_F)}，T 占比由 {pct(first_composition.w_T)} 降至 {pct(last_composition.w_T)}；来源组成随目标深度系统变化。",
        "- M0 CNR 从 P1 的 47.25 单调降至 P6 的 4.53。M3 在 P6 仍有 CNR 10.29，表明 T 区 ms 事件自身能够形成位置一致的二维响应。",
        "- M4 在六个深度均取得最高点估计 CNR，但只保留 M0 的 51.0% 到 10.0% 计数；CNR 增益必须与计数代价共同报告。",
        "- P4–S4 中，独立 55 mm slab 作差仍保留中心低响应，但点估计 CNR 为 9.80，低于 M0 的 11.37 和理想 truth 去前层 M5 的 18.26；该参考不能视为 M5 的等价替代。",
        f"- P4–S4 的直接深度比较显示 slab 与 truth front 的浅层 histogram 形状高度一致（Pearson r={num(supplementary_row.pearson_r_z_lt55, 6)}），但 slab 只覆盖 truth-front 计数的 {pct(supplementary_row.slab_to_truth_ratio)}。",
        "",
        "上述结论描述统计关系，不将某一首次散射源区直接表述为图像变化的独立因果来源。",
        "",
        "## 2. 仿真条件与统一分析定义",
        "",
        "| 参数 | 最终值 |",
        "|---|---|",
        "| 入射光子能量 | 560 keV 单能 gamma |",
        "| 圆形焦斑直径 | 5 mm |",
        "| 入射历史数 | center：20M/run；正式 grid：100M/pose |",
        "| P001 grid 合并 | 旧 20M + 独立补充 80M |",
        "| P002 grid | 独立 100M |",
        "| 55 mm slab 参考 | 独立 P001/S4，100M/pose，81 pose，seed 11000–11080 |",
        "| PMMA 模体 | 1000×1000×220 mm³ |",
        "| 空气缺陷 | 10×10×10 mm³，横向中心 (0,0) |",
        "| P1–P6 中心深度 | 15、30、45、60、75、90 mm |",
        "| 二维扫描 | x/y 均为 −10 至 10 mm，步长 2.5 mm |",
        "| 扫描网格 | 9×9，81 pose/condition |",
        "| 电磁物理模型 | `G4EmLivermorePhysics`，production cut 0.1 mm |",
        "| 探测面 | z=−73 mm，负 z 接受；P001 x=[20,127] mm，P002 x=[11,101] mm，y=[−100,100] mm |",
        "",
        "P002 覆盖 S1/S3/S5，P001 覆盖 S2/S4/S6。E1 使用 P0 center；E2 单位姿统计使用合并 grid 的 `(0,0)`，E2-F1 和 E3 使用完整 9×9 grid。",
        "",
        r"首次散射深度区域按目标中心深度 \(z_c\) 定义为：",
        "",
        r"\[F:z_1<z_c-5,\qquad T:z_c-5\le z_1<z_c+5,\qquad B:z_1\ge z_c+5.\]",
        "",
        "散射类别为 total (`scatter_count_total>=1`)、k1 (`==1`) 和 ms (`>=2`)。所有核心区间使用固定 seed `20260814` 的 5000 次 Poisson 重采样；无效分母只排除对应 draw。表中区间是 plug-in Poisson 重采样的 2.5%/97.5% 分位区间；CNR、DTV 等非线性指标存在重采样偏倚，观测点估计不要求落在该分位区间内。若观测区域直方图为空，区域内部 DTV 写为 NA，`n_effective=0`，不填造数值。",
        "",
        "## 3. 数据整理、完整性与质量检查",
        "",
        "### 3.1 原始层与清洗合并层",
        "",
        "- `events/raw/` 通过三个相对符号链接索引原始 campaign，原文件未移动、未改写。",
        "- 共核对 989 个原始 run，按物理 condition/pose 合并为 665 个 valid 单元：17 个 center 和 648 个 grid pose。",
        "- 原始事件 63,521,299 行；深度清洗后保留 58,796,025 行。",
        "- 八组 grid 条件均有 81 pose；全部合并 grid metadata 为 100M histories/pose。",
        "- P001 的每个网格点保存 20M 与 80M 两个来源 seed；P002 保存独立 100M 来源 seed。",
        f"- 独立 slab campaign 的 81 个 raw pose 共 {slab_rows_read:,} 行；按同一冻结边界和深度规则清洗后保留 {slab_rows_kept:,} 行（{pct(slab_rows_kept / slab_rows_read, 2)}）。",
        f"- slab 共丢弃 {slab_rows_dropped:,} 行，其中非有限深度 {slab_rows_dropped_nonfinite:,} 行、负深度 {slab_rows_dropped_negative:,} 行；逐文件行数守恒全部通过。",
        "",
        "### 3.2 条件完成情况",
        "",
        "| 条件 | Center P0 | Center defect | Grid P0 | Grid defect | 状态 |",
        "|---|---:|---:|---:|---:|---|",
    ]
    for index in range(1, 7):
        lines.append(f"| P{index}–S{index} | 1 | 1 | 81 | 81 | 完整 |")
    lines.extend(
        [
            "",
            "基础检查全部通过：`total=k1+ms`、`F+T+B=total`、网格坐标无缺失/重复、全部 source seed 唯一，E1/E2 acceptance 均为 `pass`。slab 的 81 pose、100M histories/pose、seed 11000–11080、560 keV、P001 和 geometry provenance 均通过严格 E3 预检；当前无缺失或异常 run。",
            "",
            "## 4. E1：均匀模体系统响应基线",
            "",
            "### 4.1 探测面接受区域",
            "",
            f"![E1-F1 detector plane]({base}/E1/figures/E1-F1_detector_plane_roi.png)",
            "",
            "P002 的 S1/S3/S5 与 P001 的 S2/S4/S6 在 detector x 上形成六个有序且可分离的带状事件群。固定 ROI 位于各自事件群内部，未观察到相邻通道接受区的异常合并；接受区顺序与几何设计一致。",
            "",
            "### 4.2 S1–S6 首次散射深度响应",
            "",
            f"![E1-F2 depth response]({base}/E1/figures/E1-F2_roi_conditioned_total_depth_response.png)",
            "",
            "六条曲线分别归一化后，主要响应范围按 S1→S6 从浅层向深层有序移动，并与 15–90 mm 设计深度序列一致。响应均存在重叠和长深度尾部；独立归一化曲线不用于比较不同狭缝的绝对计数。",
            "",
            "### 4.3 首次与末次散射空间分布",
            "",
            f"![E1-F3 first and last scatter]({base}/E1/figures/E1-F3_first_last_spatial_comparison.png)",
            "",
            "首次散射点在 x/y 方向集中于入射束附近，而末次散射点在 x–z 和 y–z 投影中均明显扩展。该图只证明空间分布不同，不单独判断多重散射对成像性能的利弊。",
            "",
            "## 5. E2：局部缺陷响应与首次散射源区分解",
            "",
            "### 5.1 P1–P6 原始 total 图像",
            "",
            f"![E2-F1 matched grids]({base}/E2/figures/E2-F1_matched_grid_total_counts.png)",
            "",
            "100M/pose 后，六个缺陷图像均出现与实际横向缺陷范围一致的中心低计数区。随深度增加，绝对计数和中心—背景差异共同下降，P5/P6 的像素噪声相对更明显；但 P6 中心低计数区仍可辨识。M0 定量结果如下。",
            "",
            "| 条件 | 深度/mm | ROI 均值 | 背景均值 | M0 CNR | 95% CI | 视觉记录 |",
            "|---|---:|---:|---:|---:|---|---|",
        ]
    )
    visual = {"P1": "强", "P2": "强", "P3": "清晰", "P4": "清晰", "P5": "可见", "P6": "较弱但可辨"}
    for phantom in phantoms:
        row = method_value(methods, phantom, "M0")
        lines.append(
            f"| {phantom}–S{phantom[1:]} | {depths[phantom]} | {num(row.roi_mean)} | "
            f"{num(row.background_mean)} | {num(row.cnr)} | "
            f"{interval(row, 'cnr_ci_low', 'cnr_ci_high')} | {visual[phantom]} |"
        )
    lines.extend(
        [
            "",
            "### 5.2 total/k1/ms 整体相对计数变化",
            "",
            "下表读取每个 matched grid 的 `(0,0)` 高统计位姿。三个散射类别在全部深度的 95% CI 均低于 0。total 响应幅度随深度单调减弱；k1 整体变化大于 ms，但 P5/P6 的细小起伏不支持把各类别写成严格单调。",
            "",
            "| 条件 | total C (95% CI) | k1 C (95% CI) | ms C (95% CI) |",
            "|---|---|---|---|",
        ]
    )
    for phantom in phantoms:
        rows = t1[t1.defect_phantom.eq(phantom)].set_index("scatter_class")
        cells = []
        for scatter_class in ("total", "k1", "ms"):
            row = rows.loc[scatter_class]
            cells.append(
                f"{pct(row.C)} ({interval(row, 'C_ci_low', 'C_ci_high', percent=True)})"
            )
        lines.append(f"| {phantom}–S{phantom[1:]} | " + " | ".join(cells) + " |")
    lines.extend(
        [
            "",
            "### 5.3 P1–P6 首次散射深度分布（新版图 5）",
            "",
            f"![Figure 5 total]({base}/E2/supplementary/section_3_2/fig5_first_scatter_depth_total.png)",
            "",
            f"![Figure 5 k1]({base}/E2/supplementary/section_3_2/fig5_first_scatter_depth_k1.png)",
            "",
            f"![Figure 5 ms]({base}/E2/supplementary/section_3_2/fig5_first_scatter_depth_ms.png)",
            "",
            "三张 2×3 小倍图分别给出 total、k1 和 ms。每个 panel 使用该条件自身的原始计数纵轴，实线为均匀模体，虚线为缺陷模体，灰色阴影为对应 T 区。主要计数凹陷随目标深度移动并集中在 T 区；T 区之外两条曲线总体较接近，但并非处处相同。",
            "",
            "### 5.4 新表 6：T 区对整体计数变化的贡献",
            "",
            "下表各项直接从零位姿原始事件计数计算，不使用重采样区间。$\\Gamma_T=w_TC_T=(N_{T,D}-N_{T,0})/N_0$，$\\Gamma_{nonT}=C-\\Gamma_T$；二者均表示相对于 baseline 总计数的百分点贡献。",
        ]
    )
    for panel, scatter_class in zip(("A", "B", "C"), ("total", "k1", "ms"), strict=True):
        lines.extend(
            [
                "",
                f"#### Panel {panel} — `{scatter_class}`",
                "",
                "| 条件 | N_T,0→N_T,D | C_T | w_T | C | Gamma_T | Gamma_nonT |",
                "|---|---:|---:|---:|---:|---:|---:|",
            ]
        )
        for _, row in table6[table6.scatter_class.eq(scatter_class)].iterrows():
            lines.append(
                f"| {row.condition.replace('-', '–')} | {int(row.N_T0):,}→{int(row.N_TD):,} | "
                f"{pct(row.C_T, 2)} | {pct(row.w_T, 2)} | {pct(row.C, 2)} | "
                f"{pct(row.Gamma_T, 2)} | {pct(row.Gamma_nonT, 2)} |"
            )

    largest_non_t = section32_validation.reindex(
        section32_validation.Gamma_nonT_direct.abs().sort_values(ascending=False).index
    ).head(5)
    lines.extend(
        [
            "",
            f"18 个条件均满足 $|\\Gamma_T|>|\\Gamma_{{nonT}}|$，因此当前原始数据支持“整体计数下降主要来自 T 区”。其中 "
            f"{opposite_count} 个 non-T 项与 T 项方向相反并部分抵消，"
            f"{18 - opposite_count} 个同向叠加；不能假定 non-T 在全部条件中方向相同。绝对值最大的 non-T 项列于下表。",
            "",
            "| 条件 | 类别 | Gamma_T | Gamma_nonT | 方向 |",
            "|---|---|---:|---:|---|",
        ]
    )
    for _, row in largest_non_t.iterrows():
        direction = "抵消 T" if row.nonT_direction == "opposes_T" else "与 T 同向"
        lines.append(
            f"| {row.condition.replace('-', '–')} | {row.scatter_class} | "
            f"{pct(row.Gamma_T_direct, 2)} | {pct(row.Gamma_nonT_direct, 2)} | {direction} |"
        )
    lines.extend(
        [
            "",
            "### 5.5 non-T 首次散射深度形态检查",
            "",
            "F 与 B 保持各自原始深度 bin 身份，排除 T 后拼接并联合归一化。下表只给出观测点估计，不绘制 DTV 折线图。",
            "",
            "| 条件 | 类别 | N_nonT,0→N_nonT,D | D_TV,F | D_TV,B | D_TV,nonT |",
            "|---|---|---:|---:|---:|---:|",
        ]
    )
    for _, row in dtv_non_t.iterrows():
        lines.append(
            f"| {row.condition.replace('-', '–')} | {row.scatter_class} | "
            f"{int(row.N_nonT0):,}→{int(row.N_nonTD):,} | {num(row.D_TV_F, 3)} | "
            f"{num(row.D_TV_B, 3)} | {num(row.D_TV_nonT, 3)} |"
        )

    lines.extend(
        [
            "",
            "| 类别 | min | max | range | 最小条件 | 最大条件 | 趋势 |",
            "|---|---:|---:|---:|---|---|---|",
        ]
    )
    for scatter_class in ("total", "k1", "ms"):
        summary = dtv_summaries[scatter_class]
        lines.append(
            f"| {scatter_class} | {summary['minimum']} | {summary['maximum']} | "
            f"{summary['range']} | {summary['minimum_condition']} | "
            f"{summary['maximum_condition']} | {summary['trend']} |"
        )
    dtv_peaks = {summary["maximum_condition"] for summary in dtv_summaries.values()}
    if len(dtv_peaks) == 1:
        dtv_peak_sentence = f"三类 $D_{{TV,nonT}}$ 均在 {next(iter(dtv_peaks))} 达到最大值"
    else:
        dtv_peak_sentence = "各类 $D_{TV,nonT}$ 最大值条件为 " + "、".join(
            f"{scatter_class}: {summary['maximum_condition']}"
            for scatter_class, summary in dtv_summaries.items()
        )
    dtv_trend_sentence = "；".join(
        f"{scatter_class}：{summary['trend']}"
        for scatter_class, summary in dtv_summaries.items()
    )
    lines.extend(
        [
            "",
            f"{dtv_peak_sentence}；{dtv_trend_sentence}。因此这里只记录数值和起伏，不依据非零值或端点差异扩展结论。",
            "",
            "### 5.6 baseline total 的 F/T/B 来源组成",
            "",
            f"![Baseline total F/T/B composition]({base}/E2/supplementary/section_3_2/fig_source_composition_total.png)",
            "",
            "100% 堆叠柱仅使用均匀模体 total 事件。来源组成趋势为 "
            + "、".join(
                f"{region} {composition_trends[region]}" for region in ("F", "T", "B")
            )
            + "；每根柱严格闭合为 100%。",
            "",
            "| 条件 | N0 | N_F,0 | N_T,0 | N_B,0 | w_F | w_T | w_B |",
            "|---|---:|---:|---:|---:|---:|---:|---:|",
        ]
    )
    for _, row in source_composition.iterrows():
        lines.append(
            f"| {row.condition.replace('-', '–')} | {int(row.N0_total):,} | "
            f"{int(row.N_F0):,} | {int(row.N_T0):,} | {int(row.N_B0):,} | "
            f"{pct(row.w_F, 2)} | {pct(row.w_T, 2)} | {pct(row.w_B, 2)} |"
        )
    lines.extend(
        [
            "",
            "数值验收中，$C=\\Gamma_T+\\Gamma_{nonT}$、两种 $\\Gamma_T$ 算法、F/T/B 与 total/k1/ms 计数闭合、表 5 的全精度 C 复核以及每柱权重闭合均通过；最大浮点误差不超过 $1.11\\times10^{-16}$。本节不引入重采样、置信区间或显著性判断。",
        ]
    )
    lines.extend(
        [
            "",
            "## 6. E3：首次散射真值条件下的二维成像作用",
            "",
            "### 6.1 M0–M5 定义",
            "",
            "| 方法 | 事件组成 |",
            "|---|---|",
            "| M0 | 全部 total |",
            "| M1 | 全部 k1 |",
            "| M2 | T 区 k1 |",
            "| M3 | T 区 ms |",
            "| M4 | T 区 k1+ms |",
            "| M5 | T+B 区 k1+ms |",
            "",
            "所有像素均通过 `M0=k1_all+ms_all`、`M4=M2+M3` 及 F/T/B 闭合检查。",
            "",
            "### 6.2 P4–S4 代表性图像与指标",
            "",
            f"![E3-F1 P4 methods]({base}/E3/E3_F1_P4_S4_M0_M5.png)",
            "",
            "| 方法 | CNR (95% CI) | 总计数 | 保留率 (95% CI) |",
            "|---|---|---:|---|",
        ]
    )
    for _, row in p4.iterrows():
        lines.append(
            f"| {row.method} | {num(row.cnr)} ({interval(row, 'cnr_ci_low', 'cnr_ci_high')}) | "
            f"{int(row.total_count_N):,} | {pct(row.retention_eta)} "
            f"({interval(row, 'retention_ci_low', 'retention_ci_high', percent=True)}) |"
        )
    lines.extend(
        [
            "",
            "六种方法均显示与缺陷位置一致的低计数区。P4 中 M4 点估计 CNR 29.70，为 M0 的 2.61 倍，但只保留 17.9% 计数；M3 单独使用 6.4% 计数仍得到 CNR 14.05。",
            "",
            "### 6.3 M3 独立响应和深度趋势",
            "",
            f"![E3-F4 all CNR]({base}/E3/E3_F4_all_methods_CNR_depth.png)",
            "",
            f"![E3-F5 retention]({base}/E3/E3_F5_all_methods_retention_depth.png)",
            "",
            "M3 在 P1–P6 的点估计 CNR 分别为 25.41、29.68、21.66、14.05、10.54 和 10.29；计数保留率从 10.0% 降至 4.4%。P3–P6 的 M3 点估计 CNR 高于对应 M0，P6 中 M0=4.53 而 M3=10.29。该结果支持“T 区 ms 自身能够形成二维缺陷响应”，但不意味着 M3 在实际系统中可直接观测或总是优于其他选择。",
            "",
            "### 6.4 目标深度 ms 的增量作用：M2→M4",
            "",
            "| 条件 | M2 CNR→M4 CNR | CNR相对变化 (95% CI) | 计数相对变化 |",
            "|---|---:|---|---:|",
        ]
    )
    for phantom in phantoms:
        row = comparison_value(comparisons, phantom, "M2_to_M4")
        lines.append(
            f"| {phantom} | {num(row.from_cnr)}→{num(row.to_cnr)} | {pct(row.g_cnr)} "
            f"({interval(row, 'g_cnr_ci_low', 'g_cnr_ci_high', percent=True)}) | {pct(row.g_count)} |"
        )
    lines.extend(
        [
            "",
            "加入 T 区 ms 后六个深度的计数均增加，增幅从 24.5% 扩大到 77.7%。CNR 点估计均增加，但 95% CI 只在 P2 和 P6 完全高于 0；P1、P3、P4、P5 不能据该区间断言 CNR 增益。",
            "",
            "### 6.5 完整策略 M1→M4 与前方区去除 M0→M5",
            "",
            f"![E3-F2 M1 M4]({base}/E3/E3_F2_M1_M4_depth.png)",
            "",
            f"![E3-F3 M0 M5]({base}/E3/E3_F3_M0_M5_depth.png)",
            "",
            "| 条件 | M1→M4 CNR变化 (95% CI) | M1→M4 计数变化 | M0→M5 CNR变化 (95% CI) | M5保留率 |",
            "|---|---|---:|---|---:|",
        ]
    )
    for phantom in phantoms:
        sr = comparison_value(comparisons, phantom, "M1_to_M4")
        front = comparison_value(comparisons, phantom, "M0_to_M5")
        m5 = method_value(methods, phantom, "M5")
        lines.append(
            f"| {phantom} | {pct(sr.g_cnr)} ({interval(sr, 'g_cnr_ci_low', 'g_cnr_ci_high', percent=True)}) | "
            f"{pct(sr.g_count)} | {pct(front.g_cnr)} "
            f"({interval(front, 'g_cnr_ci_low', 'g_cnr_ci_high', percent=True)}) | {pct(m5.retention_eta)} |"
        )
    lines.extend(
        [
            "",
            "M1→M4 的 CNR 区间在 P2–P6 高于 0，P1 跨越 0；M4 计数比 M1 少 6.3%–30.1%，因此这是一项完整策略比较，不能把全部变化单独归因于 ms。M0→M5 的 CNR 区间同样在 P2–P6 高于 0，而 M5 保留率从 81.7% 降至 24.1%。随深度增加，去除 F 区所需舍弃的计数比例总体增大；这与 baseline fT 下降共同出现，但这里只记录关联。",
            "",
            "### 6.6 均匀前层参考辅助比较",
            "",
            f"![E3-F6 front removal reference]({base}/E3/E3_F6_front_removal_reference.png)",
            "",
            "P4 与均匀 slab 均为 100M histories/pose，因此参考作差的历史数归一化系数为 `alpha=1`。E3-T4 的计数、图像统计量和重采样区间如下。",
            "",
            "| 图像 | 计数指标 | 指标类型 | ROI 均值 | 背景均值 | 背景标准差 | CNR (95% CI) | n effective |",
            "|---|---:|---|---:|---:|---:|---|---:|",
        ]
    )
    reference_labels = {
        "M0": "M0 total",
        "M5": "M5 truth 去除 F 区",
        "reference_subtracted": "独立 slab 参考作差",
    }
    metric_labels = {
        "raw_count": "raw count",
        "signed_equivalent_count": "signed-equivalent count",
    }
    for image_name in ("M0", "M5", "reference_subtracted"):
        row = reference_by_image.loc[image_name]
        lines.append(
            f"| {reference_labels[image_name]} | {int(row.count_metric):,} | "
            f"{metric_labels[str(row.count_metric_kind)]} | {num(row.roi_mean)} | "
            f"{num(row.background_mean)} | {num(row.background_std)} | {num(row.cnr)} "
            f"({interval(row, 'cnr_ci_low', 'cnr_ci_high')}) | {int(row.cnr_n_effective)} |"
        )
    lines.extend(
        [
            "",
            f"独立 slab 图像提供 {slab_image_count:,} 个 S4 接受事件；从 M0 逐像素作差后的总和为 429,432。该值是允许像素出现正负贡献的 signed-equivalent count，不是实际探测事件数，也不定义为 M0 的保留率。",
            "",
            "E3-F6 中，slab 作差图仍显示与缺陷位置一致的中心低响应，但点估计 CNR 的顺序为 M5 18.26、M0 11.37、slab 作差 9.80。作差图的背景标准差为 133.47，高于 M0 的 114.09 和 M5 的 68.00，因此它没有复现理想 source-truth 去除 F 区后的图像质量。E3-T4 只给出各图像自身的重采样区间，没有定义配对 CNR 差值或收益区间；这里不据区间重叠作显著性判断。",
            "",
            "### 6.7 P4–S4 truth front 与 slab reference 的直接深度验证",
            "",
            f"![E3 supplementary front components]({base}/E3/supplementary/center3x3_first_scatter_depth/E3_SF1_P4_S4_front_components_depth.png)",
            "",
            f"![E3 supplementary truth-slab overlay]({base}/E3/supplementary/center3x3_first_scatter_depth/E3_SF2_P4_S4_truth_front_vs_slab_overlay.png)",
            "",
            f"![E3 supplementary ROI-depth response]({base}/E3/supplementary/center3x3_first_scatter_depth/E3_SF3_P4_S4_truth_front_roi_depth.png)",
            "",
            "这里不以 CNR 或全图计数间接反推 front source，而是直接使用 P4–S4 first-scatter depth。第一张图依次显示中心 3×3 的 P4 Total、truth front (`z<55 mm`)、按实际 histories 缩放的 slab front，以及 signed residual；第二张图把 truth/slab 放在同一幅原始计数坐标上以比较浅层范围、峰位、宽度和尾部；第三张图以完整 9×9 truth-front 图像按深度计算 background/defect ROI 均值与其差值。",
            "",
            "| 指标 | 结果 |",
            "|---|---:|",
            f"| P4/slab pooled histories | {int(supplementary_row.p4_pooled_n_primary):,} / {int(supplementary_row.slab_pooled_n_primary):,} |",
            f"| alpha | {num(supplementary_row.alpha, 3)} |",
            f"| truth front total | {int(supplementary_row.truth_front_total_count):,} |",
            f"| slab front total | {num(supplementary_row.slab_front_total_count, 0)} |",
            f"| slab/truth | {pct(supplementary_row.slab_to_truth_ratio, 2)} |",
            f"| slab 的 z<55 mm 比例 | {pct(supplementary_row.slab_fraction_z_lt55, 4)} |",
            f"| 浅层 Pearson r | {num(supplementary_row.pearson_r_z_lt55, 6)} |",
            "",
            f"两侧 histories 相同，故 `alpha={num(supplementary_row.alpha, 1)}`。slab 的 {pct(supplementary_row.slab_fraction_z_lt55, 4)} 位于 55 mm 前，且与 truth front 的浅层 histogram 形状高度一致（r={num(supplementary_row.pearson_r_z_lt55, 6)}）；但 slab 只覆盖 truth-front 幅值的 {pct(supplementary_row.slab_to_truth_ratio, 2)}，不能把它当作逐 bin 完整 truth front。余下约 {pct(1.0 - supplementary_row.slab_fraction_z_lt55, 4)} 是 55 mm 后的 slab 尾部。ROI 图显示高计数浅层 bin 的 background/defect 均值接近、Delta 相对较小，但不同 bin 的 Delta 有正有负，因此这里只记录该局部观察，不将其推广为所有浅层来源的普遍机制。",
            "",
            "## 7. E1–E3 综合证据链",
            "",
            "1. **系统选择特征：** 探测面通道可分，主要深度响应按 S1–S6 有序移动；末次散射位置比首次散射明显扩展。",
            "2. **原始响应随深度降低：** total 相对变化由 −55.5% 减弱至 −12.7%，M0 CNR 由 47.25 降至 4.53；P6 仍可辨识而非完全消失。",
            f"3. **目标区贡献分解：** {t_dominant_count}/18 个条件均满足 $|\\Gamma_T|>|\\Gamma_{{nonT}}|$；{opposite_count} 个 non-T 项反向抵消，{18 - opposite_count} 个同向叠加。",
            f"4. **事件组成：** baseline total 的 F 占比由 {pct(first_composition.w_F)} 增至 {pct(last_composition.w_F)}，T 占比由 {pct(first_composition.w_T)} 降至 {pct(last_composition.w_T)}，且各柱 F/T/B 严格闭合。",
            "5. **目标深度 ms：** M3 在全部深度形成位置一致的二维响应，深部 P5/P6 点估计 CNR 高于 M0。",
            "6. **策略权衡：** M4 在六个深度具有最高点估计 CNR，但深部只保留约 10% 计数；M5 提高深部 CNR 的同时舍弃大量 F 区事件。",
            "7. **独立参考边界：** 55 mm slab 作差保留中心缺陷响应，但 CNR 点估计低于 M0，且明显低于 truth M5；本配置不支持把均匀 slab 作差视为理想 F 区去除的等价实现。",
            "8. **直接深度对应：** slab front 的 99.9245% 位于 F 区且与 truth front 形状高度相关，但其幅值仅为 truth front 的 74.1%；这支持其为浅层参考，而不支持其为完整 truth-front 幅值替代。",
            "",
            "## 8. 核心结果总表",
            "",
            "| 研究问题 | 最终结果 | 判断 |",
            "|---|---|---|",
            "| 狭缝接受区域是否可分 | 六个 detector-x 带状区域可分 | 支持 |",
            "| 深度响应是否有序 | S1→S6 主要响应向深部移动 | 支持 |",
            "| 首次/末次空间分布是否不同 | 末次散射横向扩展明显更大 | 支持 |",
            "| 原始缺陷可见性是否随深度下降 | M0 CNR 47.25→4.53，但 P6 仍可辨 | 支持下降，不支持“完全不可见” |",
            "| 整体计数响应是否随深度减弱 | total C −55.5%→−12.7% | 支持 |",
            f"| T 区是否主导整体变化 | {t_dominant_count}/18 个条件均有 `abs(Gamma_T) > abs(Gamma_nonT)` | 支持 |",
            f"| non-T 项方向是否固定 | {opposite_count} 个抵消、{18 - opposite_count} 个同向 | 不支持固定方向 |",
            f"| baseline 来源组成是否随深度变化 | w_F {pct(first_composition.w_F)}→{pct(last_composition.w_F)}；w_T {pct(first_composition.w_T)}→{pct(last_composition.w_T)} | 支持 |",
            "| T 区 ms 是否独立成像 | M3 全深度出现二维响应 | 支持 |",
            "| 加入 T 区 ms 是否增加计数 | M2→M4 +24.5% 至 +77.7% | 支持 |",
            "| 加入 T 区 ms 是否稳定提高 CNR | 仅 P2/P6 的增益 CI 高于 0 | 部分支持 |",
            "| M1→M4 完整策略 | P2–P6 CNR 增益 CI 高于 0，计数减少 | 支持但有代价 |",
            "| 去除 F 区事件 | P2–P6 CNR 增益 CI 高于 0，M5保留率随深度下降 | 支持统计关联 |",
            "| slab 参考近似 F 区 | 作差 CNR 9.80，M0 11.37，truth M5 18.26 | 保留响应，但不支持与理想去除等价 |",
            "| slab 是否对应 truth front 深度来源 | F 区占 99.9245%，Pearson r=0.995753，幅值比 74.1% | 支持形状对应，不支持完整幅值等价 |",
            "",
            "## 9. 完成状态与结果边界",
            "",
            "- [x] 原始数据只读索引、清洗和 condition/pose 合并",
            "- [x] 完整 P001/P002 matched grid 与 100M/pose 验收",
            "- [x] E1 三图",
            "- [x] E2 完整网格、整体响应、F/T/B 占比和 P4 定量分解",
            "- [x] E2 5000 次 Poisson 重采样",
            "- [x] E2 第 3.2 节原始事件重算：新版图 5、表 6、non-T DTV 与 baseline F/T/B 组成",
            "- [x] E3 M0–M5、M3、三类策略比较和深度趋势",
            "- [x] E3 严格入口 5000 次 Poisson 重采样",
            "- [x] 55 mm 均匀前层 slab 参考 81 pose、E3-F6 与 E3-T4",
            "- [x] P4–S4 truth-front/slab 直接深度比较与 9×9 ROI-depth 辅助分析",
            "",
            "本报告的数值结论限定于 560 keV、当前 PMMA/空气材料、模体尺寸、准直几何、理想探测面和蒙特卡罗首次散射真值。实际系统可实现性、能量/材料推广、source-truth 的可观测近似以及机制归因留待 Discussion。",
            "",
            "## 10. 正式产物索引",
            "",
            f"- E1：[`postprocessing/E1`]({base}/E1/)",
            f"- E2：[`postprocessing/E2`]({base}/E2/)",
            f"- E2 第 3.2 节原始事件重算：[`section_3_2`]({base}/E2/supplementary/section_3_2/)",
            "- E2 第 3.2 节独立结果说明：[analysis_3_2_results.md](analysis_3_2_results.md)",
            f"- E3 完整六图四表：[`postprocessing/E3`]({base}/E3/)",
            f"- E3 truth-front/slab 补充结果：[`postprocessing/E3/supplementary/center3x3_first_scatter_depth`]({base}/E3/supplementary/center3x3_first_scatter_depth/)",
            "- 合并审计：`results/articlev3_merged/data_processing/audit/`",
            "- 合并来源与行数：`results/articlev3_merged/data_processing/merge/`",
            "- slab provenance 与清洗审计：[`reference_manifest.yaml`](../../results/articlev3_p4_front_slab_55mm_100m/reference_manifest.yaml)、[`valid_events_manifest.yaml`](../../results/articlev3_p4_front_slab_55mm_100m/events/valid/valid_events_manifest.yaml)",
            "",
        ]
    )
    return "\n".join(lines)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--results-root", type=Path, default=Path("results/articlev3_merged"))
    parser.add_argument(
        "--slab-root",
        type=Path,
        default=Path("results/articlev3_p4_front_slab_55mm_100m"),
    )
    parser.add_argument(
        "--output", type=Path, default=Path("docs/articlev2_analysis/Report.md")
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    text = build_report(args.results_root.resolve(), args.slab_root.resolve())
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(text, encoding="utf-8")
    print(f"report: {args.output.resolve()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
