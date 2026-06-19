# MSS

`MSS` 是一个 Geant4 gamma 背散射 Monte Carlo 仿真项目。当前阶段是第二轮车辆侧向 ROI 重构：固定车辆 ROI，移动成像头，在每个离散 pose 下输出事件级 CSV 和 run-level `metadata.yaml`。

核心 v2 链路只生成事件级数据，不实现 pose-level summary、scan-level summary、统计图、图像重建或真实探测器响应。仓库另提供一个显式启用的诊断实验扩展，用于生成材料对照配置、独立 phase-space CSV 和执行理想虚拟狭缝几何筛选。

## 环境

| 项目 | 要求 |
|---|---|
| Geant4 | 11.2.0，构建时启用 `ui_all` / `vis_all` |
| 操作系统 | Ubuntu 24.04 |
| 构建系统 | CMake |
| C++ 标准 | C++17 |
| 可执行文件 | `MSS` |
| YAML 解析 | `yaml-cpp` |
| 诊断工具 / 测试 | Python 3 + PyYAML |

## 构建

从仓库根目录运行：

```bash
cmake -S . -B build
cmake --build build -j
```

当前运行命令假设工作目录是仓库根目录，这样 YAML 中的 `config/...` 和可视化宏 `macros/vis.mac` 可以直接解析。

## 运行入口

第二轮默认 batch 入口是 YAML 配置：

```bash
./build/MSS --config config/base/simulation_config_v2.yaml
```

也兼容位置参数形式：

```bash
./build/MSS config/base/simulation_config_v2.yaml
```

可视化入口通过 `--ui` 开启：

```bash
./build/MSS --config config/base/simulation_config_v2.yaml --ui
./build/MSS --config config/base/diagnostics_base.yaml --ui
```

`--ui` 也可以放在 `--config` 前：

```bash
./build/MSS --ui --config config/base/simulation_config_v2.yaml
```

默认样例 `config/base/simulation_config_v2.yaml` 是单 pose、可端到端运行的配置。它通过 `vehicle.geometry_file` 指定 VehicleROI-compatible YAML；当前工作区可使用：

- `config/geometry/pmma_box.yaml`：PMMA box control geometry，只用于 normal baseline 对照，要求 `model_type: normal` 且 `selected_target_component: null`。
- `config/geometry/vehicle_roi_v04.yaml`：车辆 ROI 几何配置，可用于 normal / abnormal 车辆模型运行。
- `config/collimator/collimator_profiles.csv`：狭缝准直器 profile 示例。
- `config/source/spectrum.csv`：spectrum 能量模式示例。

## 可视化模式

`--ui` 是第二轮正式可视化入口。它仍然从 YAML 读取 vehicle、pose、source、collimator、detector 等配置，但只用于几何和轨迹检查。

当前行为：

- 只显示 pose list 中的第一个 pose；多 pose 配置不会逐个打开窗口。
- 使用单线程 Geant4 visualization run，避免多线程轨迹显示和输出生命周期互相干扰。
- 执行 `macros/vis.mac`，默认自动 `/run/beamOn 20` 以显示少量 gamma 轨迹。
- 不写 `events.csv`、`events_debug.csv` 或 `metadata.yaml`。
- 不检查或创建 `results/{run_id}/`，因此不会因为已有输出目录而 fail fast。

`macros/vis.mac` 只包含 `/vis/...`、`/tracking/storeTrajectory` 和少量 `/run/beamOn` 命令。source、geometry、pose、output、seed、thread 等运行参数仍由 YAML 控制，不通过 macro 控制。

## 主要可调配置

所有正式运行参数来自 `config/base/simulation_config_v2.yaml` 或 `--config` 指定的等价 YAML。常用字段如下。

| 配置节 | 字段 | 作用 |
|---|---|---|
| `run` | `random_seed` | base seed；每个 pose 使用 `random_seed + pose_index`。 |
| `run` | `number_of_threads` | batch 模式线程数；`--ui` 模式固定单线程显示。 |
| `run` | `n_primary_per_pose` | batch 模式每个 pose 的 primary gamma 数。 |
| `run` | `debug` | `false` 输出 `events.csv`；`true` 输出 `events_debug.csv`。 |
| `vehicle` | `geometry_file` | VehicleROI-compatible YAML 路径，可指向车辆 ROI 或 PMMA control geometry。 |
| `vehicle` | `model_type` | `normal` 或 `abnormal`。 |
| `vehicle` | `selected_target_component` | abnormal 模型中被替换为 target 的 insert。 |
| `vehicle` | `abnormal_material` | abnormal target 使用的 Geant4 材料名。 |
| `pose` | `mode` | `list` 或 `grid`。 |
| `source` | `energy_mode` | `mono` 或 `spectrum`。 |
| `source` | `mono_energy_keV` | `mono` 模式下的固定 gamma 能量。 |
| `source` | `spectrum_file` | `spectrum` 模式下的 `energy_keV,weight` CSV。 |
| `source` | `source_pos_zero_mm` | 成像头零位姿 source global 坐标。 |
| `source` | `incident_theta_deg` | 入射方向角，方向为 `(cos(theta), 0, sin(theta))`。 |
| `source` | `focal_spot_diameter_mm` | 有限焦点圆面直径。 |
| `collimator` | `enable` | 是否构建狭缝准直器。 |
| `collimator` | `profile_file` / `profile_id` | 选择 CSV profile。 |
| `collimator` | `jaw_extrusion_length_y_mm` | jaw 沿 global `y` 方向全长。 |
| `detector` | `detector_z_zero_mm` | 虚拟探测平面 z 位置。 |
| `detector` | `detector_x_range_zero_mm` / `detector_y_range_zero_mm` | 零位姿接收范围。 |
| `output` | `output_directory` | batch 输出根目录。 |
| `output` | `events_csv_name` / `metadata_yaml_name` | formal CSV 与 metadata 文件名。 |
| `output` | `thread_tmp_directory` | 多线程临时 CSV 目录名。 |
| `diagnostics` | `case_id` | 可选诊断实验条件标识；不参与现有 run_id。 |
| `diagnostics.phase_space` | `enable` / `csv_name` | 可选独立 phase-space crossing CSV；不改变正式/debug CSV。 |

当前 `physics.physics_list` 和 `physics.production_cut_mm` 会被读取并写入 metadata；代码中的 `PhysicsList` 仍固定使用 `G4EmLivermorePhysics` 和 `0.1 mm` default cut。

## 能量模式

射线源支持两种 primary gamma 能量模式。

单能模式：

```yaml
source:
  energy_mode: mono
  mono_energy_keV: 160.0
```

能谱模式：

```yaml
source:
  energy_mode: spectrum
  spectrum_file: config/source/spectrum.csv
```

`spectrum_file` 的 CSV header 必须为：

```csv
energy_keV,weight
```

程序按 weight 构建 CDF 并采样能量；非法能量、负权重、空文件或权重和为 0 都会 fail fast。

## Pose 配置

`pose.mode` 支持：

- `list`：`head_offset_x_mm` 和 `head_offset_y_mm` 按相同下标配对。
- `grid`：`x_offsets_mm` 为外层、`y_offsets_mm` 为内层生成笛卡尔积。

每个 pose 会生成独立 run。默认 seed 规则是：

```text
pose_seed = run.random_seed + pose_index
```

默认 `pose_id_rule` 为：

```text
pose_x{encoded_x}_y{encoded_y}
```

负数 offset 用 `m` 编码，例如 `x=-10, y=-4` 对应 `pose_xm10_ym4`。

## 输出

每个 pose 输出到独立 run 目录：

```text
{output.output_directory}/{pose_id}_{vehicle.model_type}_seed{pose_seed}/
```

默认单 pose 示例会写入：

```text
results/pose_x0_y0_normal_seed12345/events.csv
results/pose_x0_y0_normal_seed12345/metadata.yaml
```

输出目录策略由 `output.existing_run_policy` 控制。默认 `fail` 会在目标 run 目录已存在且非空时报错停止；`overwrite` 会删除并重建当前目标 run 目录，不会删除上层输出目录。

正式模式 `run.debug: false` 输出 `events.csv`，语义为：

```text
1 row = 1 detected gamma hit
```

Debug 模式 `run.debug: true` 输出 `events_debug.csv`，语义为：

```text
1 row = 1 gamma track summary
```

多线程时每个 worker 先写入 run 目录下的 `tmp/` 临时 CSV，run end 后由 master 合并为最终 CSV。正式模式合并成功后删除线程临时 CSV；debug 模式合并成功后保留，便于排查。

`metadata.yaml` 记录 run-level 信息，包括 pose、seed、thread、vehicle/source/collimator/detector/physics/world/output policy 等配置快照。

## 后处理：像素 bin 来源深度分析

像素 bin 来源深度分析用于研究不同 detector bin 接收到的 detected gamma hit 的 `last_scatter_z` 经验分布，以及这种分布随散射阶次的变化。运行前启用数据分析环境：

```bash
conda activate data
python scripts/analyze_pixel_depth_by_bin.py \
  results/near_door \
  --output-dir results/analysis/pixel_depth
```

默认按 `det_x` 做 1 mm 一维 bin，递归发现包含 `events.csv` 与 `metadata.yaml` 的 run 目录，不依赖固定 run_id 或旧结果目录结构。核心输出包括：

```text
results/analysis/pixel_depth/
├── analysis_manifest.yaml
├── pixel_depth_summary_by_scatter_class/E*/<scatter_class>.csv
├── bin_lag_distribution_metrics/E*/<scatter_class>.csv
├── scatter_order_spatial_summary/E*/<scatter_class>.csv
└── pixel_scatter_class_fraction/E*/fractions.csv
```

普通分析 CSV 每行只保留 `pose, seed, energy_keV, collimator, abnormal_present, insert_name, insert_material` 等实际实验条件；完整 `run_id`、`case_id`、pose offset、model、collimator 和 `n_primary` 等 provenance 保存在 `analysis_manifest.yaml`。

可选绘图：

```bash
python scripts/analyze_pixel_depth_by_bin.py \
  results/near_door \
  --output-dir results/analysis/pixel_depth \
  --write-plots
```

该后处理只读取事件级 CSV 与 metadata，不修改 Geant4 仿真输出 schema，也不自动给出物理结论。

完整能力、输入输出和指标含义见 `docs/pixel_depth_energy_analysis.md`。

## 诊断实验扩展

生成车辆、金属替换 PMMA、全部非空气实体替换 PMMA、均匀 PMMA box 与有/无物理狭缝组合的八组配置：

```bash
python3 scripts/diagnostics/generate_variants.py
```

输出清单位于：

```text
config/generated/diagnostics/manifest.yaml
```

四个无狭缝条件使用固定大面积 scoring plane，并额外输出：

```text
phase_space.csv
```

该文件是独立 schema；`events.csv` 与 `events_debug.csv` 的字段和语义保持不变。对无狭缝 phase-space 应用原准直器的理想几何筛选：

```bash
python3 scripts/diagnostics/virtual_slit_filter.py \
  --phase-space results/diagnostics/vehicle_open/<run_id>/phase_space.csv \
  --metadata results/diagnostics/vehicle_open/<run_id>/metadata.yaml \
  --slit-config config/generated/diagnostics/configs/vehicle_slit.yaml \
  --output virtual_slit_audit.csv
```

添加 `--accepted-only` 只写通过虚拟狭缝的行。该筛选不会重现钨 jaw 中的吸收、散射或 secondary gamma，因此不能替代物理狭缝 Monte Carlo 对照。

完整实验定义、文件语义与测试命令见 `docs/diagnostics.md`。

## Near-Door 能量扫描脚本

近层车门异常实验使用独立脚本生成配置，不改变基础 v2 `events.csv` / `events_debug.csv` schema。生成 48-run 核心矩阵示例：

```bash
python3 scripts/generate_near_door_experiment_configs.py \
  --pose-r-offset 0,480 \
  --pose-c-offset 0,320 \
  --seeds 1234
```

输出位于 `config/generated/near_door/`，文件名和 `output.output_directory` 会包含 system、pose、model_state、energy 和 seed；生成配置默认使用 `output.existing_run_policy: overwrite`。`--include-high-z` 可额外生成 `V-C-W` 对照；`--open-detector-range XMIN,XMAX,YMIN,YMAX` 可覆盖 open-panel detector 范围。

当前推荐的高统计量生成方式是 open 每 case `200k`，collimated 每个物理 case 拆成 `20 x 25M = 500M`：

```bash
python3 scripts/generate_near_door_experiment_configs.py \
  --pose-r-offset 0,480 \
  --pose-c-offset 0,320 \
  --seeds 1234 \
  --open-n-primary 200000 \
  --collimated-batches 20 \
  --collimated-batch-n-primary 25000000
```

推荐使用串行队列运行生成的 manifest，队列会保证一个 Geant4 子进程完全结束后才启动下一个。默认不保存队列状态和日志，进度直接打印到终端；再次运行时，脚本会根据已生成的 `metadata.yaml` 和 `events.csv` / `events_debug.csv` 跳过完整 case：

```bash
python3 scripts/run_experiment_queue.py \
  --manifest config/generated/near_door/manifest.yaml \
  --binary ./build/MSS
```

如需保存队列状态、lock 和每个 case 的运行日志，可显式启用：

```bash
python3 scripts/run_experiment_queue.py \
  --manifest config/generated/near_door/manifest.yaml \
  --binary ./build/MSS \
  --save-queue
```

高统计量 collimated 推荐开两个终端并行跑两个 shard，并为每个 shard 使用独立 state/log 路径：

```bash
python3 scripts/run_experiment_queue.py \
  --manifest config/generated/near_door/manifest.yaml \
  --binary ./build/MSS \
  --system collimated \
  --shard-count 2 \
  --shard-index 0 \
  --save-queue \
  --state-file results/queues/near_door/collimated_shard0_state.json \
  --log-dir results/queues/near_door/collimated_shard0_logs
```

第二个终端把 `--shard-index` 和路径中的 `shard0` 改为 `shard1`。open case 可用 `--system open` 单独顺序跑完。队列会检查 `metadata.yaml` 中的 `n_primary`，旧的低统计量输出不会被误判为当前批次已完成。

运行完成后，可对一个或多个 run 目录生成实验 summary：

```bash
python3 scripts/analyze_near_door_experiments.py \
  results/near_door \
  --output-dir results/analysis/near_door
```

该分析脚本输出 `run_summary.csv`、`scatter_order_summary.csv`、`energy_scan_summary.csv`、`visibility_summary.csv` 和 `layer_attribution_summary.csv`，属于显式后处理辅助脚本，不由 Geant4 程序自动生成。

查看 detector x 方向 1 mm bin-count 原始响应图：

```bash
MPLCONFIGDIR=/tmp/mss_matplotlib \
/home/ldn/miniforge3/bin/conda run -n data python scripts/plot_detector_response.py \
  results/near_door \
  --channels all,k0,k1,ms \
  --comparison-grid
```

该脚本默认只输出 PNG；加 `--write-csv` 时才额外写 detector bin 长表和 comparison index。`--comparison-grid` 会按输入目录中发现的全部状态生成行，列固定为 `open` / `collimated`。

详细用法见 `docs/near_door_experiments.md`。

## 输入数据说明

当前 `config/collimator/collimator_profiles.csv`、`config/source/spectrum.csv` 和默认几何参数用于第二轮链路检查、可视化和样例运行。它们不代表最终工程准直器、真实能谱或完整车辆 CAD。

第二轮准直器 profile 允许每个 profile 包含可变数量 jaw，不默认构建镜像准直器。探测器是单个理想虚拟探测平面，不模拟真实探测器材料响应。

## Legacy Macros

`macros/run.mac` 和 `macros/run_mt.mac` 保留为第一版 macro 语法参考，不是第二轮默认运行入口。第二轮配置应通过 `--config config/base/simulation_config_v2.yaml` 或等价 YAML 文件提供。

`macros/vis.mac` 当前是第二轮 `--ui` 使用的可视化宏，但它不提供运行参数配置能力，只负责 viewer、轨迹和少量事件显示。

legacy macro 中出现的 PMMA、空气缺陷、镜像准直器、镜像探测器和旧 CSV 命名不属于第二轮默认设计约束。

## 本轮非目标

当前 Geant4 基础程序仍不实现：

- pose-level summary 或 scan-level summary；
- 通用 Python 后处理分析、统计图、差异图或论文指标计算；诊断扩展仅包含理想几何虚拟狭缝筛选；
- 图像重建、连续运动扫描或运动模糊；
- 真实探测器材料响应或能量沉积 scoring；
- 整车 CAD 复现、镜像准直器或镜像探测器。

详细规格与验收见 `docs/spec.md`、`docs/decisions.md` 和 `docs/acceptance_checklist.md`。
