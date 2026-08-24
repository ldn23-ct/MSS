#!/usr/bin/env python3
"""Build the filled Article V3 merged-data report from accepted E1--E3 outputs."""

from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd
import yaml


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


def build_report(results_root: Path) -> str:
    e1 = results_root / "postprocessing" / "E1"
    e2 = results_root / "postprocessing" / "E2"
    e3 = results_root / "postprocessing" / "E3"
    required = (
        e1 / "acceptance_summary.yaml",
        e2 / "acceptance_summary.yaml",
        e2 / "tables" / "E2-T1_zero_pose_raw_count_decomposition.csv",
        e2 / "tables" / "E2-T2_P0-S4_vs_P4-S4_source_region_quantitative.csv",
        e2 / "tables" / "E2-T3_zero_pose_source_region_fractions.csv",
        e3 / "E3_T1_P4_S4_metrics.csv",
        e3 / "E3_T2_depth_method_metrics.csv",
        e3 / "E3_T3_depth_comparisons.csv",
    )
    missing = [path for path in required if not path.is_file()]
    if missing:
        raise FileNotFoundError("missing accepted report inputs: " + ", ".join(map(str, missing)))
    for acceptance in required[:2]:
        value = yaml.safe_load(acceptance.read_text(encoding="utf-8"))
        if value.get("overall_status") != "pass":
            raise ValueError(f"analysis acceptance is not pass: {acceptance}")

    t1 = pd.read_csv(required[2])
    regions = pd.read_csv(required[3])
    fractions = pd.read_csv(required[4])
    p4 = pd.read_csv(required[5])
    methods = pd.read_csv(required[6])
    comparisons = pd.read_csv(required[7])
    phantoms = [f"P{i}" for i in range(1, 7)]
    depths = dict(zip(phantoms, (15, 30, 45, 60, 75, 90), strict=True))

    base = "../../results/articlev3_merged/postprocessing"
    lines: list[str] = [
        "# PMMA–空气缺陷 X 射线背散射蒙特卡罗实验报告",
        "",
        "> 数据版本：`results/articlev3_merged`。更新日期：2026-08-24。E1、E2 及 E3 主网格结果已完成；E3 均匀前层参考实验因缺少独立 55 mm PMMA slab 数据而保留为唯一待完成项。",
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
        "- P4–S4 的 T 区 total 从 2152 降至 1，ms 从 811 降至 0；与此同时全深度 total 只下降 19.3%，说明局部目标深度响应会被其他深度来源计数稀释。",
        "- M0 CNR 从 P1 的 47.25 单调降至 P6 的 4.53。M3 在 P6 仍有 CNR 10.29，表明 T 区 ms 事件自身能够形成位置一致的二维响应。",
        "- M4 在六个深度均取得最高点估计 CNR，但只保留 M0 的 51.0% 到 10.0% 计数；CNR 增益必须与计数代价共同报告。",
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
            "基础检查全部通过：`total=k1+ms`、`F+T+B=total`、网格坐标无缺失/重复、全部 source seed 唯一，E1/E2 acceptance 均为 `pass`。主实验无缺失或异常 run，也无需重仿真。唯一缺项是第 6.6 节所需的 55 mm 均匀 PMMA slab 参考 81 pose。",
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
            "### 5.3 目标深度来源事件占比",
            "",
            "P0 baseline 的 total 目标区占比随匹配深度从 56.7% 单调降至 11.8%。空气缺陷条件的 T 区首次散射事件被压低到 0.23% 以下，因此其点估计不呈可靠的深度单调序列；这不影响 baseline 中目标深度统计权重随深度下降的观察。每个条件和类别的 F/T/B 分数均严格闭合为 1。",
            "",
            "| 条件 | baseline fT total (95% CI) | defect fT total (95% CI) | defect fT k1 | defect fT ms |",
            "|---|---|---|---:|---:|",
        ]
    )
    for phantom in phantoms:
        target = fractions[fractions.defect_phantom.eq(phantom) & fractions.region.eq("Target")]
        b = target[target.condition_role.eq("baseline") & target.scatter_class.eq("total")].iloc[0]
        d = target[target.condition_role.eq("defect") & target.scatter_class.eq("total")].iloc[0]
        dk1 = target[target.condition_role.eq("defect") & target.scatter_class.eq("k1")].iloc[0]
        dms = target[target.condition_role.eq("defect") & target.scatter_class.eq("ms")].iloc[0]
        lines.append(
            f"| {phantom}–S{phantom[1:]} | {pct(b.fraction, 2)} "
            f"({interval(b, 'fraction_ci_low', 'fraction_ci_high', percent=True)}) | "
            f"{pct(d.fraction, 3)} ({interval(d, 'fraction_ci_low', 'fraction_ci_high', percent=True)}) | "
            f"{pct(dk1.fraction, 3)} | {pct(dms.fraction, 3)} |"
        )
    lines.extend(
        [
            "",
            "### 5.4 P4–S4 代表性深度分布",
            "",
            f"![E2-F2 total relative response]({base}/E2/figures/E2-F2_P0-S4_vs_P4-S4_total_binwise_relative_response.png)",
            "",
            f"![E2-F2 k1 relative response]({base}/E2/figures/E2-F2_P0-S4_vs_P4-S4_k1_binwise_relative_response.png)",
            "",
            f"![E2-F2 ms relative response]({base}/E2/figures/E2-F2_P0-S4_vs_P4-S4_ms_binwise_relative_response.png)",
            "",
            f"![E2-F3 total depth]({base}/E2/figures/E2-F3_P0-S4_vs_P4-S4_total_raw_depth_counts.png)",
            "",
            f"![E2-F3 k1 depth]({base}/E2/figures/E2-F3_P0-S4_vs_P4-S4_k1_raw_depth_counts.png)",
            "",
            f"![E2-F3 ms depth]({base}/E2/figures/E2-F3_P0-S4_vs_P4-S4_ms_raw_depth_counts.png)",
            "",
            "P4 的 55–65 mm T 区出现接近完全的计数缺失：total 2152→1、k1 1341→1、ms 811→0。F 区曲线近似重合，B 区缺陷条件计数反而增加。该组合说明全深度 −19.3% 的 total 变化不能代表 T 区局部响应幅度。",
            "",
            "### 5.5 P4–S4 F/T/B 定量分解",
            "",
            "| 类别 | 区域 | N0→ND | Cr (95% CI) | DTV (95% CI) | n effective |",
            "|---|---|---:|---|---|---:|",
        ]
    )
    for _, row in regions.iterrows():
        dtv = "NA" if pd.isna(row.D_TV_r) else f"{num(row.D_TV_r, 3)} ({interval(row, 'D_TV_r_ci_low', 'D_TV_r_ci_high')})"
        lines.append(
            f"| {row.scatter_class} | {row.region} | {int(row.N_r0)}→{int(row.N_rD)} | "
            f"{pct(row.C_r)} ({interval(row, 'C_r_ci_low', 'C_r_ci_high', percent=True)}) | "
            f"{dtv} | {int(row.D_TV_r_n_effective)} |"
        )
    lines.extend(
        [
            "",
            "F 区三类 Cr 的区间均跨越 0；B 区三类计数均增加且区间高于 0。T 区 total/k1 的 DTV 很高，但缺陷直方图各只有 1 个事件，应谨慎解释；T 区 ms 的缺陷计数为 0，内部形态无法归一化，因此 DTV 按规则记为 NA。",
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
            "**状态：未完成。** 当前 `results/` 中没有独立的 P4–S4、55 mm 均匀 PMMA 前层 slab 9×9 数据，因此 E3-F6 和 E3-T4 未生成，也没有用其他数据替代。未来补充 81 pose 后，应使用冻结的严格 E3 入口计算参考作差并更新本节。",
            "",
            "## 7. E1–E3 综合证据链",
            "",
            "1. **系统选择特征：** 探测面通道可分，主要深度响应按 S1–S6 有序移动；末次散射位置比首次散射明显扩展。",
            "2. **原始响应随深度降低：** total 相对变化由 −55.5% 减弱至 −12.7%，M0 CNR 由 47.25 降至 4.53；P6 仍可辨识而非完全消失。",
            "3. **目标深度局部响应：** P4 T 区 total/k1/ms 分别接近完全损失，而 F 区变化不显著、B 区增加；局部 T 区响应显著大于全深度 total 响应。",
            "4. **事件组成：** P0 baseline fT total 从 56.7% 降至 11.8%；缺陷零位姿 T 区事件因空气替代而接近零。",
            "5. **目标深度 ms：** M3 在全部深度形成位置一致的二维响应，深部 P5/P6 点估计 CNR 高于 M0。",
            "6. **策略权衡：** M4 在六个深度具有最高点估计 CNR，但深部只保留约 10% 计数；M5 提高深部 CNR 的同时舍弃大量 F 区事件。",
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
            "| T 区是否保持局部响应 | P4 total 2152→1，ms 811→0 | 支持 |",
            "| baseline T 区占比是否随深度下降 | 56.7%→11.8%，单调下降 | 支持 |",
            "| T 区 ms 是否独立成像 | M3 全深度出现二维响应 | 支持 |",
            "| 加入 T 区 ms 是否增加计数 | M2→M4 +24.5% 至 +77.7% | 支持 |",
            "| 加入 T 区 ms 是否稳定提高 CNR | 仅 P2/P6 的增益 CI 高于 0 | 部分支持 |",
            "| M1→M4 完整策略 | P2–P6 CNR 增益 CI 高于 0，计数减少 | 支持但有代价 |",
            "| 去除 F 区事件 | P2–P6 CNR 增益 CI 高于 0，M5保留率随深度下降 | 支持统计关联 |",
            "| slab 参考近似 F 区 | 无独立 slab 数据 | 待完成 |",
            "",
            "## 9. 完成状态与结果边界",
            "",
            "- [x] 原始数据只读索引、清洗和 condition/pose 合并",
            "- [x] 完整 P001/P002 matched grid 与 100M/pose 验收",
            "- [x] E1 三图",
            "- [x] E2 完整网格、整体响应、F/T/B 占比和 P4 定量分解",
            "- [x] E2 5000 次 Poisson 重采样",
            "- [x] E3 M0–M5、M3、三类策略比较和深度趋势",
            "- [x] E3 core 5000 次 Poisson 重采样",
            "- [ ] 55 mm 均匀前层 slab 参考 81 pose、E3-F6 与 E3-T4",
            "",
            "本报告的数值结论限定于 560 keV、当前 PMMA/空气材料、模体尺寸、准直几何、理想探测面和蒙特卡罗首次散射真值。实际系统可实现性、能量/材料推广、source-truth 的可观测近似以及机制归因留待 Discussion。",
            "",
            "## 10. 正式产物索引",
            "",
            f"- E1：[`postprocessing/E1`]({base}/E1/)",
            f"- E2：[`postprocessing/E2`]({base}/E2/)",
            f"- E3 core：[`postprocessing/E3`]({base}/E3/)",
            "- 合并审计：`results/articlev3_merged/data_processing/audit/`",
            "- 合并来源与行数：`results/articlev3_merged/data_processing/merge/`",
            "",
        ]
    )
    return "\n".join(lines)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--results-root", type=Path, default=Path("results/articlev3_merged"))
    parser.add_argument(
        "--output", type=Path, default=Path("docs/articlev2_analysis/Report.md")
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    text = build_report(args.results_root.resolve())
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(text, encoding="utf-8")
    print(f"report: {args.output.resolve()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
