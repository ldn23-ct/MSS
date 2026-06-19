# 像素 bin 来源深度与能量扫描后处理说明

## 1. 目的与边界

本文说明像素 bin 来源深度分析与能量维度报告工具的能力、输入、输出和指标含义。

相关脚本包括：

- `scripts/analyze_pixel_depth_by_bin.py`
- `scripts/report_pixel_depth_energy.py`

本后处理用于回答以下核心问题：

```text
不同 detector pixel bin 接收到的 detected gamma hit，其来源深度分布是否不同；
这种 bin 对来源深度的区分能力是否随散射阶次增加而减弱；
不同 gamma 能量下，上述现象是否有稳定趋势。
```

本分析中的来源深度定义为：

```text
source_depth = last_scatter_z
```

即 detected gamma hit 对应 gamma track 的最后一次有效 Compton / Rayleigh 散射位置的 global `z` 坐标。

本扩展不修改 Geant4 C++ 核心，不修改正式 `events.csv` 或 `events_debug.csv` 的 header、字段顺序和语义。Geant4 程序仍只负责事件级输出；本文中的统计 CSV、PNG 和 Markdown 报告均由显式后处理脚本生成。

## 2. 新增能力概览

### 2.1 像素 bin 来源深度分析

`scripts/analyze_pixel_depth_by_bin.py` 从多个 run 的 `events.csv` 与 `metadata.yaml` 中读取 detected gamma hit，并按 detector bin 汇总 `last_scatter_z` 经验分布。

默认能力包括：

| 能力 | 默认行为 |
|---|---|
| run 发现 | 递归扫描输入路径下含 `events.csv` 的 run 目录 |
| metadata 读取 | 读取同目录 `metadata.yaml`，用于补充 run 条件和 detector 范围 |
| bin 轴 | `det_x` |
| bin 宽 | `1.0 mm` |
| 深度样本 | 有限 `last_scatter_z`，且 `scatter_count_total > 0` |
| region 过滤 | 同时输出 `all_valid` 与 `vehicle_only` |
| scatter class | `all`, `k1`, `k2`, `k3`, `kn`, `km` |
| bin 间比较 lag | `1, 2, 5, 10` |

### 2.2 能量维度报告

`scripts/report_pixel_depth_energy.py` 读取像素 bin 来源深度分析的输出，并按能量生成：

- 汇总 CSV；
- PNG 图；
- 中文 Markdown 报告。

默认主分析使用：

```text
region_filter = vehicle_only
```

`all_valid` 仅作为敏感性对照，避免把 `none`、`source`、`other` 或 world / 非车辆区域的散射误解释为车辆内部来源深度。

## 3. 前置条件

从仓库根目录执行命令。

推荐使用 conda 数据分析环境：

```bash
conda activate data
```

该环境应提供：

```text
pandas
numpy
scipy
matplotlib
PyYAML
```

也可以不激活 shell 环境，直接使用：

```bash
conda run -n data python <script> ...
```

## 4. 输入数据

### 4.1 仿真 run 输入

像素 bin 来源深度分析脚本的输入是一个或多个结果目录。当前 near-door 能量扫描示例为：

```text
results/near_door/
```

脚本会递归查找：

```text
*/events.csv
*/metadata.yaml
```

每个有效 run 目录至少需要：

```text
events.csv
metadata.yaml
```

若 metadata 缺失，脚本可降级使用父目录名作为 `run_id`，并从数据 min/max 推断 bin 范围；但正式分析建议保留 metadata。

### 4.2 `events.csv` 字段

核心必需字段：

| 字段 | 用途 |
|---|---|
| `det_x` | 默认 detector bin 坐标 |
| `scatter_count_total` | 构造散射阶次分组 |
| `last_scatter_z` | 来源深度样本 |

推荐存在的可选字段：

| 字段 | 用途 |
|---|---|
| `det_y` | 可切换为按 `det_y` 分 bin |
| `det_z` | detector crossing 位置检查 |
| `last_scatter_region_id` | 构造 `vehicle_only` region filter |
| `first_scatter_z` | 后续扩展 first-scatter 深度分析 |
| `first_scatter_region_id` | first-scatter region 对照 |
| `is_primary_gamma` | primary / secondary 对照 |
| `gamma_source_type` | gamma 来源类型对照 |
| `det_energy` | detector crossing 能量对照 |

若缺少 `last_scatter_region_id`，脚本仍可输出 `all_valid`，但会跳过 `vehicle_only`。

### 4.3 后处理输入

能量报告脚本默认读取：

```text
results/analysis/pixel_depth/
```

该目录应包含：

```text
analysis_manifest.yaml
pixel_depth_summary_by_scatter_class/
bin_lag_distribution_metrics/
scatter_order_spatial_summary/
pixel_scatter_class_fraction/
```

普通分析 CSV 采用分层目录，不再把完整 run provenance 重复写入每一行。完整 run 追踪信息、字段映射和输出文件索引统一保存在 `analysis_manifest.yaml`。

## 5. 运行命令

### 5.1 生成像素 bin 来源深度统计

```bash
conda activate data
python scripts/analyze_pixel_depth_by_bin.py \
  results/near_door \
  --output-dir results/analysis/pixel_depth
```

常用参数：

| 参数 | 默认 | 作用 |
|---|---:|---|
| `--axis` | `det_x` | detector bin 轴，可选 `det_x` / `det_y` |
| `--bin-width-mm` | `1.0` | bin 宽度，单位 mm |
| `--lags` | `1,2,5,10` | bin 间分布比较的 lag |
| `--min-bin-samples` | `20` | 单个 bin 参与分布比较的最小样本数 |
| `--min-valid-bins` | `3` | run-level 指标所需最少有效 bin 数 |
| `--write-plots` | 关闭 | 输出基础 PNG |

### 5.2 生成能量维度报告

```bash
python scripts/report_pixel_depth_energy.py \
  --input-dir results/analysis/pixel_depth \
  --output-dir results/analysis/pixel_depth_energy
```

输出目录示例：

```text
results/analysis/pixel_depth_energy/
├── report.md
├── energy_spatial_metrics.csv
├── energy_k1_vs_km_retention.csv
├── energy_sample_sufficiency.csv
├── energy_aggregated_metrics.csv
├── energy_aggregated_retention.csv
└── plots/
    ├── k1_km_width90_vs_energy.png
    ├── k1_km_separation_vs_energy.png
    ├── spatial_score_retention_vs_energy.png
    └── median_depth_vs_bin_by_energy_*.png
```

## 6. Scatter class 定义

| class | 定义 | 说明 |
|---|---|---|
| `all` | `scatter_count_total > 0` | 所有有有效 last scatter 的 detected hit |
| `k1` | `scatter_count_total == 1` | 单次散射 |
| `k2` | `scatter_count_total == 2` | 二次散射 |
| `k3` | `scatter_count_total == 3` | 三次散射 |
| `kn` | `scatter_count_total >= 4` | 高阶多重散射 |
| `km` | `scatter_count_total >= 2` | 多重散射汇总组 |

需要注意：

```text
km = k2 + k3 + kn
```

因此 `km` 不是与 `k2/k3/kn` 互斥的新类别，而是多重散射的汇总视角。

`scatter_count_total = 0` 的 hit 没有有效 `last_scatter_z`，不进入来源深度分布；但会进入 `pixel_scatter_class_fraction/E*/fractions.csv` 的 `k0` 计数，用于查看无散射 detected hit 的空间比例。

## 7. Region filter 定义

| region_filter | 含义 | 推荐用途 |
|---|---|---|
| `all_valid` | 所有有限 `last_scatter_z` hit | 完整 detected hit 对照 |
| `vehicle_only` | last scatter region 属于车辆 ROI YAML 中的 region | 主要物理解释 |

`vehicle_only` 依赖：

```text
metadata.yaml: vehicle_geometry_file
events.csv: last_scatter_region_id
```

脚本会从车辆几何 YAML 的 `components[].region_id` 中收集车辆 region，并排除：

```text
none
source
other
world
detector
collimator
```

物理解释时应优先使用 `vehicle_only`。如果 `all_valid` 与 `vehicle_only` 趋势不同，通常说明非车辆或无法归因散射对统计有影响，应在报告中单独说明。

## 8. 像素 bin 来源深度输出

### 8.1 输出目录结构与 compact condition 字段

像素 bin 分析输出按能量和散射阶次拆分：

```text
results/analysis/pixel_depth/
├── analysis_manifest.yaml
├── pixel_depth_summary_by_scatter_class/
│   ├── E60/k1.csv
│   ├── E60/km.csv
│   └── E160/k1.csv
├── bin_lag_distribution_metrics/
│   └── E160/km.csv
├── scatter_order_spatial_summary/
│   └── E160/k1.csv
└── pixel_scatter_class_fraction/
    └── E160/fractions.csv
```

其中 `pixel_scatter_class_fraction` 本身同时包含 `k0/k1/k2/k3/kn/km` 的计数和占比，因此只按能量拆分，不再按散射阶次拆分。

普通 CSV 每行只保留实际实验条件字段：

| 字段 | 含义 |
|---|---|
| `pose` | 扫描位姿；near-door 数据优先取 `case_id` 中的 `poseC` / `poseR`，否则取 `pose_id` |
| `seed` | 该 run 实际使用的 random seed |
| `energy_keV` | source mono gamma 能量 |
| `collimator` | `open` 或 `collimated` |
| `abnormal_present` | 是否存在 abnormal insert |
| `insert_name` | abnormal 时的 insert 组件名；normal 时为空 |
| `insert_material` | abnormal 时的 insert 材料；normal 时为空 |

以下字段不再进入普通分析 CSV：`run_dir`、`run_id`、`case_id`、`pose_id`、`pose_index`、`head_offset_x_mm`、`head_offset_y_mm`、`model_type`、`selected_target_component`、`abnormal_material`、`collimator_enable`、`n_primary`。这些信息保存在 `analysis_manifest.yaml` 的 `runs[].provenance` 中。

### 8.2 `pixel_depth_summary_by_scatter_class/E*/<scatter_class>.csv`

粒度：

```text
compact condition + region_filter + pixel_bin
```

核心字段：

| 字段 | 含义 | 物理 / 统计意义 |
|---|---|---|
| `bin_axis` | 分 bin 使用的 detector 坐标 | 默认 `det_x` |
| `bin_index` | bin 序号 | detector pixel bin 的离散编号 |
| `bin_min_mm`, `bin_max_mm` | bin 左右边界 | 左闭右开，最后一个 bin 包含右边界 |
| `bin_center_mm` | bin 中心坐标 | 画 median depth 曲线的横轴 |
| `count` | 该 bin 的有效深度样本数 | 样本数不足时分位数不稳定 |
| `mean` | 平均 `last_scatter_z` | 对长尾敏感 |
| `std` | 标准差 | 深度分布离散程度 |
| `q05`, `q25`, `median`, `q75`, `q95` | 分位数 | 经验分布的稳健摘要 |
| `iqr` | `q75 - q25` | 中间 50% 深度宽度 |
| `width90` | `q95 - q05` | 中间 90% 深度宽度 |

物理解释：

- `median` 随 bin 有系统变化，说明 detector bin 可能携带来源深度信息；
- `width90` 越大，说明同一 bin 接收的 hit 来源深度越混杂；
- `k1` 的 `width90` 若远小于 `km`，说明单次散射更接近局部来源，多重散射更容易混合不同深度来源。

文件路径中的 `<scatter_class>` 已经编码散射阶次，因此该 CSV 内不再重复写 `scatter_class` 列。

### 8.3 `bin_lag_distribution_metrics/E*/<scatter_class>.csv`

粒度：

```text
compact condition + region_filter + lag + bin_pair
```

核心字段：

| 字段 | 含义 | 物理 / 统计意义 |
|---|---|---|
| `lag` | bin 间隔 | 例如 lag=5 表示比较第 b 和 b+5 个 bin |
| `bin_index_a`, `bin_index_b` | 被比较的两个 bin | 空间上分离的 detector bin |
| `count_a`, `count_b` | 两个 bin 的样本数 | 小于阈值时不输出该 pair |
| `wasserstein1` | 两个深度分布的 Wasserstein-1 距离 | 深度分布整体平移 / 分离程度，单位近似 mm |
| `ks_statistic` | 两样本 KS 统计量 | 两个经验 CDF 最大差异，范围 0 到 1 |
| `mean_width90` | 两个 bin 的平均 width90 | 用于归一化分布内宽度 |
| `separation_score` | `wasserstein1 / mean_width90` | bin 间分离相对 bin 内混杂宽度的强弱 |

物理解释：

- `wasserstein1` 大表示两个 bin 的来源深度分布相距更远；
- `ks_statistic` 大表示两个 bin 的经验分布形状差异更强；
- `separation_score > 1` 表示 bin 间距离大于典型 bin 内 90% 宽度，空间区分较强；
- `separation_score < 1` 表示 bin 内深度混杂可能掩盖 bin 间差异。

文件路径中的 `<scatter_class>` 已经编码散射阶次，因此该 CSV 内不再重复写 `scatter_class` 列。

### 8.4 `scatter_order_spatial_summary/E*/<scatter_class>.csv`

粒度：

```text
compact condition + region_filter
```

核心字段：

| 字段 | 含义 | 物理 / 统计意义 |
|---|---|---|
| `n_valid_hits` | 参与该 scatter class 分析的 hit 数 | 总样本量 |
| `n_valid_bins` | 满足最小样本数阈值的 bin 数 | 空间趋势是否可判断 |
| `spearman_rho` | bin index 与 median depth 的 Spearman 相关 | 单调空间深度趋势 |
| `slope_depth_per_bin` | median depth 对 bin index 的线性斜率 | 每移动一个 bin，median depth 的平均变化量 |
| `median_width90` | 有效 bin 的 median width90 | 该 class 的典型来源深度混杂宽度 |
| `median_wasserstein1_*` | 不同 lag 的 W1 中位数 | 典型 bin 间深度距离 |
| `median_ks_*` | 不同 lag 的 KS 中位数 | 典型 bin 间分布差异 |
| `median_separation_*` | 不同 lag 的 separation 中位数 | bin 间分离相对 bin 内混杂强度 |
| `spatial_score` | `abs(spearman_rho) * median_separation_all_lags` | 粗略空间区分能力综合指标 |
| `rho_retention_vs_k1` | `abs(rho_c) / abs(rho_k1)` | 相对 k1 的单调趋势保留 |
| `width_inflation_vs_k1` | `median_width90_c / median_width90_k1` | 相对 k1 的深度分布增宽 |
| `sep_retention_vs_k1` | `median_separation_c / median_separation_k1` | 相对 k1 的分布分离保留 |
| `spatial_score_retention_vs_k1` | `spatial_score_c / spatial_score_k1` | 相对 k1 的综合空间区分保留 |

物理解释：

- `width_inflation_vs_k1 > 1`：该散射阶次的来源深度分布比单次散射更宽；
- `sep_retention_vs_k1 < 1`：该散射阶次的 bin 间分布区分弱于单次散射；
- `spatial_score_retention_vs_k1 < 1`：综合意义上，该散射阶次保留的空间区分能力弱于单次散射；
- 对 `km` 同时满足上述三个条件时，可记为统计上支持“多重散射削弱 bin 对来源深度的区分作用”。

文件路径中的 `<scatter_class>` 已经编码散射阶次，因此该 CSV 内不再重复写 `scatter_class` 列。

### 8.5 `pixel_scatter_class_fraction/E*/fractions.csv`

粒度：

```text
compact condition + region_filter + pixel_bin
```

核心字段：

| 字段 | 含义 | 物理 / 统计意义 |
|---|---|---|
| `count_all` | 该 bin 中有 scatter_count 的 hit 总数 | detector bin 总统计量 |
| `count_k0` | 无有效散射 hit 数 | 可能来自未散射穿越或无记录散射 |
| `count_k1` | 单次散射 hit 数 | 单散射贡献 |
| `count_k2`, `count_k3`, `count_kn` | 二次、三次、高阶散射 hit 数 | 多重散射阶次结构 |
| `count_km` | 多重散射 hit 数 | `k2+k3+kn` |
| `fraction_k*` | 对应 count 除以 `count_all` | 不同 bin 的散射阶次组成 |

物理解释：

- `fraction_k1` 高的 bin 可能更接近局部、低混杂的来源；
- `fraction_km` 高的 bin 表明多重散射贡献较大，来源深度解释更容易变宽或混合；
- `fraction_k0` 需要谨慎解释，因为它没有有效 `last_scatter_z`，不进入深度分布。

### 8.6 `analysis_manifest.yaml`

记录分析运行条件和可追踪信息：

| 字段 | 含义 |
|---|---|
| `input_paths` | 输入路径 |
| `axis` | bin 轴 |
| `bin_width_mm` | bin 宽 |
| `lags` | 使用的 lag 列表 |
| `min_bin_samples` | bin pair 分布比较阈值 |
| `min_valid_bins` | run-level 指标阈值 |
| `discovered_run_count` | 发现 run 数 |
| `analyzed_run_count` | 成功分析 run 数 |
| `skipped_run_count` | 跳过 run 数 |
| `runs[].field_mapping` | 实际 CSV 字段到标准字段的映射 |
| `runs[].condition` | 写入普通 CSV 的 compact condition 字段 |
| `runs[].provenance` | 完整 run-level provenance，包括 run_id、case_id、pose offset、model、collimator、n_primary 等 |
| `runs[].vehicle_only_enabled` | 是否成功启用 vehicle-only 过滤 |
| `runs[].warnings` | 降级或跳过原因 |
| `outputs` | 每类输出表按 energy / scatter class 拆分后的实际文件索引 |

## 9. 能量报告输出

### 9.1 `report.md`

中文 Markdown 报告，面向人工阅读。

主要内容包括：

- 数据与方法；
- 能量维度总览；
- 五个核心问题的回答；
- k1 / km 比较表；
- 样本充分性与限制；
- 输出图像索引。

报告中的判断语句只表示统计指标支持的趋势，不等价于最终物理定论。

### 9.2 `energy_spatial_metrics.csv`

粒度：

```text
compact condition + region_filter + scatter_class
```

该表是 `scatter_order_spatial_summary/E*/<scatter_class>.csv` 的能量报告用整理版，额外加入样本充分性判断和人类可读标签。

基础实验条件字段与第 8.1 节相同：

```text
pose, seed, energy_keV, collimator, abnormal_present, insert_name, insert_material
```

额外字段：

| 字段 | 含义 |
|---|---|
| `condition_id` | 由 collimator、pose、abnormal / material 状态组成的条件 id |
| `condition_label` | 人类可读条件标签 |
| `sufficient` | 该行是否满足样本充分性要求 |
| `sufficiency_reason` | 不充分原因或 `ok` |

### 9.3 `energy_k1_vs_km_retention.csv`

粒度：

```text
compact condition + region_filter
```

每一行把同一实验条件下的 `k1` baseline 与 `km` 多重散射汇总组配对。配对键使用 `pose, seed, energy_keV, collimator, abnormal_present, insert_name, insert_material, region_filter`，不依赖 `run_id` 或 `case_id`。

核心字段：

| 字段 | 含义 |
|---|---|
| `k1_n_valid_hits`, `km_n_valid_hits` | k1 / km hit 数 |
| `k1_n_valid_bins`, `km_n_valid_bins` | k1 / km 有效 bin 数 |
| `both_sufficient` | k1 与 km 是否都满足样本充分性 |
| `k1_spearman_rho`, `km_spearman_rho` | k1 / km 的深度单调趋势 |
| `k1_median_width90`, `km_median_width90` | k1 / km 的典型深度宽度 |
| `width_inflation_vs_k1` | km 相对 k1 的 width90 增大倍数 |
| `k1_median_separation`, `km_median_separation` | k1 / km 的典型 bin 间分离 |
| `sep_retention_vs_k1` | km 相对 k1 的分离保留比例 |
| `k1_spatial_score`, `km_spatial_score` | k1 / km 综合空间区分指标 |
| `spatial_score_retention_vs_k1` | km 相对 k1 的综合空间区分保留 |
| `supports_ms_weakening` | 是否满足多重散射弱化组合判据 |

组合判据为：

```text
width_inflation_vs_k1 > 1
sep_retention_vs_k1 < 1
spatial_score_retention_vs_k1 < 1
```

### 9.4 `energy_sample_sufficiency.csv`

粒度：

```text
compact condition + region_filter + scatter_class
```

用于检查哪些能量 / 条件 / scatter class 不足以支撑趋势判断。

主要不充分原因包括：

- `n_valid_bins < threshold`
- `spearman_rho is NaN`
- `median_width90 is NaN`
- `median_separation_all_lags is NaN`
- `spatial_score is NaN`

### 9.5 `energy_aggregated_metrics.csv`

粒度：

```text
energy + scatter_class
```

默认只聚合 `vehicle_only` 且样本充分的 `k1` / `km`。

核心字段：

| 字段 | 含义 |
|---|---|
| `sufficient_conditions` | 该能量下满足样本充分性的条件数 |
| `median_abs_spearman` | `abs(spearman_rho)` 的中位数 |
| `median_width90` | width90 中位数 |
| `median_separation` | separation score 中位数 |
| `median_spatial_score` | spatial score 中位数 |

### 9.6 `energy_aggregated_retention.csv`

粒度：

```text
energy
```

默认只聚合 `vehicle_only` 且 k1 / km 都样本充分的配对条件。

核心字段：

| 字段 | 含义 |
|---|---|
| `sufficient_pairs` | k1/km 都充分的配对条件数 |
| `median_width_inflation_vs_k1` | km 相对 k1 的 width90 增大中位数 |
| `median_sep_retention_vs_k1` | km 相对 k1 的 separation 保留中位数 |
| `median_spatial_score_retention_vs_k1` | km 相对 k1 的 spatial score 保留中位数 |
| `weakening_support_fraction` | 满足多重散射弱化组合判据的配对比例 |

## 10. 图片输出含义

图片默认写入：

```text
results/analysis/pixel_depth_energy/plots/
```

### 10.1 `k1_km_width90_vs_energy.png`

横轴为 energy，纵轴为 `median_width90`。

物理含义：

- k1 曲线表示单次散射 hit 的典型来源深度宽度；
- km 曲线表示多重散射 hit 的典型来源深度宽度；
- km 曲线显著高于 k1，表示多重散射使同一 detector bin 对应的来源深度分布变宽。

### 10.2 `k1_km_separation_vs_energy.png`

横轴为 energy，纵轴为 `median_separation`。

物理含义：

- 数值越大，说明不同 detector bin 的来源深度分布相对更容易区分；
- km 曲线低于 k1，表示多重散射下 bin 间分布差异被削弱。

### 10.3 `spatial_score_retention_vs_energy.png`

横轴为 energy，纵轴为：

```text
km_spatial_score / k1_spatial_score
```

物理含义：

- `1` 附近表示 km 保留了接近 k1 的综合空间区分能力；
- 小于 `1` 表示多重散射降低了综合空间区分能力；
- 越低说明削弱越明显。

### 10.4 `median_depth_vs_bin_by_energy_*.png`

每张图对应一个代表性条件，例如：

```text
collimated_poseC_normal
collimated_poseC_cavityPE
collimated_poseC_cavityFlour
```

纵向子图按能量排列，横轴为 detector bin center，纵轴为 median `last_scatter_z`。

物理含义：

- 若 median depth 随 bin center 呈系统变化，说明 detector bin 对来源深度有空间编码能力；
- k1 曲线通常更窄、更局部；
- km 曲线若更平缓或更混杂，说明多重散射降低深度定位能力。

## 11. 如何解读当前报告中的核心判断

当前报告的主要判断流程为：

1. 先检查 `energy_sample_sufficiency.csv`，剔除样本不足条件；
2. 以 `vehicle_only` 为主分析；
3. 对每个能量比较 `k1` 与 `km`；
4. 查看 `width_inflation_vs_k1` 是否大于 1；
5. 查看 `sep_retention_vs_k1` 是否小于 1；
6. 查看 `spatial_score_retention_vs_k1` 是否小于 1；
7. 若三者同时满足，则该条件记为支持“多重散射弱化 detector bin 对来源深度的空间区分能力”。

若某个能量的 `weakening_support_fraction` 较高，表示该能量下有较多实验条件支持上述判断。若某个能量的 `sufficient_pairs` 很少，则该能量的趋势判断应降级为“统计不足”。

## 12. 注意事项

- `source_depth = last_scatter_z` 是当前后处理定义，不是唯一可能的来源深度定义。
- `last_scatter_z` 是 detected gamma track 自身最后一次有效散射位置，不继承 parent track 的散射历史。
- `km` 是汇总组，不能与 `k2/k3/kn` 相加后再作为独立总数重复解释。
- `all_valid` 中可能包含非车辆或无法归因区域，正式物理解释优先使用 `vehicle_only`。
- `spatial_score` 是比较指标，不是经过物理标定的成像性能指标。
- 报告中的“支持”“倾向”均指统计指标层面的支持，不代表最终物理结论。
