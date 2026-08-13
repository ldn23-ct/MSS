# MSS

`MSS` 是一个 Geant4 gamma 背散射 Monte Carlo 仿真项目。项目保留稳定的车辆 ROI 事件级仿真核心，并以 articlev2 作为当前唯一活跃的数据处理与实验后处理链路。

Geant4 核心只生成事件级数据，不实现 pose-level summary、scan-level summary、统计图、图像重建或真实探测器响应；显式 Python 后处理层负责清洗、审计与论文图表。

## 项目 v2 结构与归档入口

完整的文档、脚本、配置和结果目录归类见 [`docs/project_structure.md`](docs/project_structure.md)。当前项目分为：

| 层次 | 职责 | 当前定位 |
|---|---|---|
| Geant4 仿真核心 | 固定车辆 ROI、移动成像头、事件追踪与 `events.csv + metadata.yaml` | 稳定基础，供后续实验复用 |
| Monte Carlo 自动化 | manifest、逐 pose 配置、队列执行、状态恢复与分片 | `scripts/monte_carlo/` |
| 基础数据处理 | 有效深度筛选、slit 标签、边界校准和数据审计 | `scripts/data_processing/` |
| 实验后处理 | E1 正式分析；E2/E3 接口预留 | `scripts/postprocessing/` |

主要文档入口：

- Geant4 核心规格：[`docs/archive/v2/spec.md`](docs/archive/v2/spec.md)、[`docs/archive/v2/decisions.md`](docs/archive/v2/decisions.md)、[`docs/archive/v2/architecture.md`](docs/archive/v2/architecture.md)。
- Article v1：仅保留 [`docs/archive/v2/`](docs/archive/v2/) 历史文档，运行脚本和兼容入口已移除。
- Article V2：[`docs/articlev2_experiment_automation.md`](docs/articlev2_experiment_automation.md) 和 [`docs/articlev2_analysis/`](docs/articlev2_analysis/)。

下一项目版本尚未开始，版本号未定义。工作区中的预研草案或配套资产不属于项目 v2，也不代表相关能力已经实现。

## 环境

| 项目 | 要求 |
|---|---|
| Geant4 | 11.2.0，构建时启用 `ui_all` / `vis_all` |
| 操作系统 | Ubuntu 24.04 |
| 构建系统 | CMake |
| C++ 标准 | C++17 |
| 可执行文件 | `MSS` |
| YAML 解析 | `yaml-cpp` |
| 实验脚本 / 测试 | Python 3 + PyYAML |

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
./build/MSS --config config/base/article_base.yaml --ui
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
| root | `case_id` | 可选实验条件标识；缺省时使用 `run_id`。 |

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

offset 接受有限 mm 数值并支持最多六位小数。负号用 `m`、小数点用 `p` 编码，例如
`x=-10, y=-4` 对应 `pose_xm10_ym4`，`x=-7.5, y=2.5` 对应
`pose_xm7p5_y2p5`。超过六位小数、NaN 或 Inf 会 fail fast。

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

## Articlev2 自动化与后处理

生成配置并执行 dry-run：

```bash
python -m scripts.monte_carlo.generate_source_response_experiment_configs
python -m scripts.monte_carlo.run_experiment_queue \
  --manifest config/generated/articlev2/manifest.yaml \
  --binary ./build/MSS \
  --dry-run
```

权威结果链路固定为：

```text
results/articlev2/events/raw
  -> results/articlev2/events/valid
  -> results/articlev2/data_processing/audit
  -> results/articlev2/postprocessing/E1
```

清洗、审计和 E1 分析：

```bash
python -m scripts.data_processing.clean_events --results-root results/articlev2
python -m scripts.data_processing.audit_experiment_data \
  --results-root results/articlev2 --overwrite
python -m scripts.postprocessing.e1.run --results-root results/articlev2
```

各脚本的输入、输出和失败条件见对应子目录 README。article v1 batch merge、raw cleanup、实验编号过滤及旧脚本路径不再提供兼容入口。
结果分层与 provenance 约定见 [`results/README.md`](results/README.md)。

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
- Geant4 内部自动生成 Python 后处理统计或论文图表；
- 图像重建、连续运动扫描或运动模糊；
- 真实探测器材料响应或能量沉积 scoring；
- 整车 CAD 复现、镜像准直器或镜像探测器。

详细规格与验收见 `docs/archive/v2/spec.md`、`docs/archive/v2/decisions.md` 和 `docs/archive/v2/acceptance_checklist.md`。
