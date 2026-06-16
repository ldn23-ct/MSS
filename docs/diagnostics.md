# 车辆背散射诊断实验扩展

## 1. 边界

本扩展仍使用 `schema_version: 2`，不修改正式 `events.csv` 或 `events_debug.csv` 的 header、字段顺序和语义。

新增能力均为显式可选：

- 生成八组车辆材料与准直器对照配置；
- 无物理狭缝条件输出独立 `phase_space.csv`；
- 对 phase-space 执行理想虚拟狭缝几何筛选。

它不提供统计图、差异图、指标计算或图像重建。

## 2. 对照矩阵

运行以下命令重新生成全部输入：

```bash
python3 scripts/diagnostics/generate_variants.py
```

生成结果位于 `config/generated/diagnostics/`，清单为 `manifest.yaml`。

| Geometry | `*_slit` | `*_open` |
|---|---|---|
| 原车辆 | 原 P001 狭缝和原 detector | 无 jaw，大面积 scoring plane |
| `metal_to_pmma` | 仅 `G4_Fe` / `G4_Al` 替换为 PMMA | 同左 geometry，无 jaw |
| `nonair_to_pmma` | 所有非 `G4_AIR` component material 替换为 PMMA | 同左 geometry，无 jaw |
| 均匀 PMMA box | 复用 `config/geometry/pmma_box.yaml` | 同左 geometry，无 jaw |

所有派生车辆 geometry 保持 component 名称、host、形状、尺寸、位置、region 和 insert 结构不变。

原 detector：

```yaml
detector_z_zero_mm: -73.0
detector_x_range_zero_mm: [-646.0, -404.0]
detector_y_range_zero_mm: [-50.0, 50.0]
```

大面积 scoring plane：

```yaml
detector_z_zero_mm: -73.0
detector_x_range_zero_mm: [-1000.0, 1400.0]
detector_y_range_zero_mm: [-750.0, 750.0]
```

两者均按现有规则叠加 pose 的 x/y offset。

## 3. Phase-Space 输出

诊断配置使用以下可选节：

```yaml
diagnostics:
  case_id: vehicle_open
  phase_space:
    enable: true
    csv_name: phase_space.csv
```

缺少 `diagnostics` 时按原 v2 行为运行。八组配置中仅四个 `*_open` 条件默认启用 phase-space。

`phase_space.csv` 中每行表示某条 gamma track 第一次有效 negative-z scoring-plane crossing：

```csv
event_id,hit_id,track_id,parent_id,is_primary_gamma,particle,phase_x_mm,phase_y_mm,phase_z_mm,dir_x,dir_y,dir_z,kinetic_energy_keV,weight
```

其中 `event_id + hit_id` 与同一 run 的正式 hit 对齐。多线程运行使用独立 worker 文件并由 master 合并。

Metadata 额外记录：

- 实际入口 `config_file`；
- `diagnostics.case_id`；
- phase-space enable 和文件名；
- scoring plane 的 zero-pose 与 actual bounds。

## 4. 虚拟狭缝

示例：

```bash
python3 scripts/diagnostics/virtual_slit_filter.py \
  --phase-space results/diagnostics/vehicle_open/<run_id>/phase_space.csv \
  --metadata results/diagnostics/vehicle_open/<run_id>/metadata.yaml \
  --slit-config config/generated/diagnostics/configs/vehicle_slit.yaml \
  --output virtual_slit_audit.csv
```

工具先检查原 detector actual bounds，再沿 crossing 方向反向追踪，并测试射线与各 jaw 的有限 y 拉伸凸棱柱是否相交。输出追加：

```csv
virtual_slit_accept,rejection_reason,blocking_jaw_id
```

`rejection_reason` 为：

- `accepted`
- `outside_detector`
- `invalid_direction`
- `blocked_by_jaw`

默认保留所有行用于审计；`--accepted-only` 仅写接受行。jaw 边界相交按阻挡处理。

虚拟狭缝只计算理想几何接受关系，不模拟钨中的吸收、散射和 secondary gamma。物理狭缝组仍是解释 Monte Carlo 差异的正式基准。

## 5. 测试

```bash
cmake -S . -B build
cmake --build build -j
ctest --test-dir build --output-on-failure
```

测试包括 geometry 替换、八组配置矩阵、正式/debug schema 回归、虚拟狭缝边界情况，以及八组、旧 v2 配置和多线程 phase-space 合并的真实 Geant4 smoke run。
