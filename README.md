# MSS

`MSS` 是一个 Geant4 gamma 背散射 Monte Carlo 仿真项目。当前阶段是第二轮车辆侧向 ROI 重构：固定车辆 ROI，移动成像头，在每个离散 pose 下输出事件级 CSV 和 run-level `metadata.yaml`。

本轮只生成事件级数据，不实现 pose-level summary、scan-level summary、后处理脚本、统计图、图像重建或真实探测器响应。

## 环境

| 项目 | 要求 |
|---|---|
| Geant4 | 11.2.0 |
| 操作系统 | Ubuntu 24.04 |
| 构建系统 | CMake |
| C++ 标准 | C++17 |
| 可执行文件 | `MSS` |

## 构建

从仓库根目录运行：

```bash
cmake -S . -B build
cmake --build build -j
```

当前运行命令假设工作目录是仓库根目录，这样 YAML 中的 `data/...` 相对路径可以直接解析。

## 运行入口

第二轮默认入口是 YAML 配置：

```bash
./build/MSS --config data/simulation_config_v2.yaml
```

也兼容位置参数形式：

```bash
./build/MSS data/simulation_config_v2.yaml
```

默认样例 `data/simulation_config_v2.yaml` 是单 pose、可端到端运行的配置。它引用：

- `data/vehicle_roi_v03.yaml`：默认车辆 ROI 几何配置。
- `data/collimator_profiles.csv`：狭缝准直器 profile 示例。
- `data/spectrum.csv`：spectrum 能量模式示例。

`data/vehicle_roi_v04.yaml` 保留为额外数据文件，不是默认样例入口。

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

输出目录采用 fail-fast 策略。如果目标 run 目录已经存在且非空，程序会报错停止，不覆盖、不追加，也不会自动生成替代目录名。

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

## 输入数据说明

当前 `data/collimator_profiles.csv`、`data/spectrum.csv` 和默认几何参数用于第二轮链路检查与样例运行。它们不代表最终工程准直器、真实能谱或完整车辆 CAD。

第二轮准直器 profile 允许每个 profile 包含可变数量 jaw，不默认构建镜像准直器。探测器是单个理想虚拟探测平面，不模拟真实探测器材料响应。

## Legacy Macros

`macros/*.mac` 保留为第一版 macro 语法和可视化兼容参考，不是第二轮默认运行入口。第二轮配置应通过 `--config data/simulation_config_v2.yaml` 或等价 YAML 文件提供。

这些 legacy macro 中出现的 PMMA、空气缺陷、镜像准直器、镜像探测器和旧 CSV 命名不属于第二轮默认设计约束。

## 本轮非目标

当前 Geant4 基础程序不实现：

- pose-level summary 或 scan-level summary；
- Python 后处理分析、统计图、差异图或论文指标计算；
- 图像重建、连续运动扫描或运动模糊；
- 真实探测器材料响应或能量沉积 scoring；
- 整车 CAD 复现、镜像准直器或镜像探测器。

详细规格与验收见 `docs/spec.md`、`docs/decisions.md` 和 `docs/acceptance_checklist.md`。
