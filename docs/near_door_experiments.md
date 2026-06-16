# 近层车门能量扫描实验工具说明

## 1. 目的与边界

本文说明本次新增的 near-door 实验辅助工具如何使用。

新增工具包括：

- `scripts/generate_near_door_experiment_configs.py`
- `scripts/run_experiment_queue.py`
- `scripts/analyze_near_door_experiments.py`

它们用于生成和分析以下实验：

- Batch 1：近层车门异常可见性验证；
- Batch 2：近层车门多重散射机制分析。

本扩展仍使用 `schema_version: 2`，不升级到 v3，不修改正式 `events.csv` 或 `events_debug.csv` 的 header、字段顺序和语义。Geant4 程序仍只负责事件级输出；本文中的 summary CSV 由显式后处理脚本生成。

## 2. 新增能力概览

配置生成脚本会从一个 base YAML 复制配置，并批量替换以下维度：

| 维度 | 默认内容 |
|---|---|
| system | `open` / `collimated` |
| pose | `poseR` / `poseC` |
| model_state | `normal` / `cavityPE` / `cavityFlour` |
| energy_keV | `60, 160, 260, 360, 460, 560` |
| seed | 默认 `1234`，可传入多个 |

核心矩阵为：

```text
8 cases x 6 energies x seed_count
```

单 seed 默认生成：

```text
48 YAML configs
```

可选 `--include-high-z` 会额外加入 `cavityW`，用于高 Z 边界对照。

## 3. 前置条件

从仓库根目录执行命令。

需要 Python 3 和 PyYAML：

```bash
python3 -c "import yaml"
```

建议先确认 C++ 程序可构建：

```bash
cmake -S . -B build
cmake --build build -j
```

## 4. 生成实验 YAML

最小示例：

```bash
python3 scripts/generate_near_door_experiment_configs.py \
  --pose-r-offset 0,480 \
  --pose-c-offset 0,320 \
  --seeds 1234
```

默认输入和输出：

| 项 | 默认 |
|---|---|
| base config | `config/base/simulation_config_v2.yaml` |
| 输出目录 | `config/generated/near_door/` |
| target component | `near_rear_door_insert` |
| abnormal low-Z material | `G4_POLYETHYLENE` |
| flour material | `Vehicle_Flour` |

生成结果：

```text
config/generated/near_door/
├── manifest.yaml
└── configs/
    ├── near_door_open_poseR_normal_E60_seed1234.yaml
    ├── near_door_open_poseC_normal_E60_seed1234.yaml
    ├── near_door_open_poseC_cavityPE_E60_seed1234.yaml
    └── ...
```

每个生成 YAML 只包含一个 pose。脚本会设置：

- `pose.mode: list`
- `pose.list.head_offset_x_mm: [X]`
- `pose.list.head_offset_y_mm: [Y]`
- `source.energy_mode: mono`
- `source.mono_energy_keV: <energy>`
- `run.random_seed: <seed>`
- `output.existing_run_policy: overwrite`
- `diagnostics.case_id: near_door_<system>_<pose>_<model_state>_E<energy>_seed<seed>`

每个配置的输出根目录也会包含实验条件，例如：

```text
results/near_door/collimated/poseC/cavityPE/E160/seed1234
```

实际 run 目录仍由 C++ 程序追加。run_id 会包含 pose、system、model state、energy 和 seed：

```text
{pose_id}_{system}_{model_state}_{energy}_seed{seed}
```

完整输出示例：

```text
results/near_door/collimated/poseC/cavityPE/E160/seed1234/pose_x0_y320_collimated_abnormal_near_rear_door_insert_G4_POLYETHYLENE_E160keV_seed1234/
```

## 5. 常用生成参数

指定 base config：

```bash
python3 scripts/generate_near_door_experiment_configs.py \
  --base-config config/base/simulation_config_v2.yaml \
  --pose-r-offset 0,480 \
  --pose-c-offset 0,320
```

生成多 seed 正式矩阵：

```bash
python3 scripts/generate_near_door_experiment_configs.py \
  --pose-r-offset 0,480 \
  --pose-c-offset 0,320 \
  --seeds 1234,2234,3234
```

切换近层前门 insert：

```bash
python3 scripts/generate_near_door_experiment_configs.py \
  --pose-r-offset 0,480 \
  --pose-c-offset 0,320 \
  --target-component near_front_door_insert
```

加入高 Z 对照：

```bash
python3 scripts/generate_near_door_experiment_configs.py \
  --pose-r-offset 0,480 \
  --pose-c-offset 0,320 \
  --include-high-z
```

为 open-panel 覆盖 detector 大平板范围：

```bash
python3 scripts/generate_near_door_experiment_configs.py \
  --pose-r-offset 0,480 \
  --pose-c-offset 0,320 \
  --open-detector-range -1000,1400,-750,750
```

如果不传 `--open-detector-range`，open-panel 使用 base config 中当前 detector 范围，只关闭准直器。

## 6. 串行队列运行

单个配置运行：

```bash
./build/MSS --config config/generated/near_door/configs/near_door_collimated_poseC_cavityPE_E160_seed1234.yaml
```

批量运行推荐使用串行队列脚本，不需要手动执行 48 条命令：

```bash
python3 scripts/run_experiment_queue.py \
  --manifest config/generated/near_door/manifest.yaml \
  --binary ./build/MSS
```

队列会按 `manifest.yaml` 中 `cases[].config_file` 的顺序逐个启动：

```bash
./build/MSS --config <yaml>
```

前一个 Geant4 子进程完全退出后，才会启动下一个配置。脚本不会并行启动多个 `MSS` 进程。

near-door 生成配置默认采用：

```yaml
output:
  existing_run_policy: overwrite
```

若当前目标 run 目录已存在，程序会删除并重建该 run 目录。删除范围只限最终 run 目录，不会删除 `results/near_door` 或更上层输出目录。若希望恢复旧的保护行为，可把生成 YAML 中的 `existing_run_policy` 改为 `fail`。

队列默认不保存 `queue_state.json`、lock file 或 per-case log。默认再次启动同一队列时，会直接检查每个 case 的预期 run 目录：

- `metadata.yaml` 必须存在；
- 非 debug run 必须存在 `events.csv`；
- debug run 必须存在 `events_debug.csv`；
- `metadata.yaml` 中的 `run_id` 必须与配置计算出的预期 `run_id` 一致。

满足这些条件的 case 会跳过。失败、中断或输出不完整的 case 会重新运行；由于生成 YAML 默认使用 `existing_run_policy: overwrite`，重新运行时会由 C++ 程序清理该 case 的旧 run 目录残留。

如需保留队列状态、lock file 和每个 case 的 stdout/stderr 日志，可加 `--save-queue`：

```bash
python3 scripts/run_experiment_queue.py \
  --manifest config/generated/near_door/manifest.yaml \
  --binary ./build/MSS \
  --save-queue
```

启用保存模式时，队列状态写入：

```text
results/queues/near_door/queue_state.json
```

日志写入：

```text
results/queues/near_door/queue_logs/<queue_id>/<index>_<case_id>.log
```

常用选项：

| 选项 | 作用 |
|---|---|
| `--dry-run` | 只打印将运行或跳过的 case，不启动 Geant4 |
| `--rerun-completed` | 忽略已有完整输出，重新运行全部 case |
| `--continue-on-failure` | 某个 case 失败后继续运行后续 case |
| `--save-queue` | 保存队列状态、lock 和每个 case 的日志 |
| `--state-file <path>` | 指定状态文件，并隐式启用保存模式 |
| `--log-dir <path>` | 指定日志根目录，并隐式启用保存模式 |
| `--force-unlock` | 保存模式下，人工确认旧队列已停止后清理遗留 lock |

保存模式下，队列启动时会创建 lock file，阻止两个队列同时操作同一份状态文件。如果上一次队列被强制杀死，可先确认没有 `MSS` 进程仍在运行，再使用 `--force-unlock`。

## 7. Metadata 追踪信息

每个 run 的 `metadata.yaml` 会记录：

- `run_id`
- `config_file`
- `model_type`
- `selected_target_component`
- `abnormal_material`
- `pose_id`
- `head_offset_x_mm`
- `head_offset_y_mm`
- `source.energy_mode`
- `source.mono_energy_keV`
- `collimator.enable`
- `collimator.profile_file`
- `collimator.profile_id`
- detector zero-pose range 和 actual range
- `n_primary`
- `base_random_seed`
- `random_seed`
- `number_of_threads`
- `diagnostics.case_id`

当前 C++ `run_id` 已包含 energy / system / abnormal material。跨实验汇总时仍建议以 `metadata.yaml` 为准追踪实际配置。

## 8. 后处理分析

对一个或多个 run 根目录生成 summary：

```bash
python3 scripts/analyze_near_door_experiments.py \
  results/near_door \
  --output-dir results/analysis/near_door
```

也可以传入多个目录：

```bash
python3 scripts/analyze_near_door_experiments.py \
  results/near_door/open \
  results/near_door/collimated \
  --output-dir results/analysis/near_door
```

脚本会递归查找包含以下文件的 run 目录：

```text
metadata.yaml
events.csv
```

输出文件：

| 文件 | 作用 |
|---|---|
| `run_summary.csv` | 每个 run 的总产额、散射阶次计数、比例和 yield |
| `scatter_order_summary.csv` | 每个 run 按 `k=0,1,2,3,ge4` 展开的散射阶次表 |
| `energy_scan_summary.csv` | 按 system / pose / model_state / energy 聚合的能量扫描指标 |
| `visibility_summary.csv` | abnormal 与 normal 配对后的可见性指标 |
| `layer_attribution_summary.csv` | first / last scatter region 映射到 door layer 后的归因统计 |

字段名不会使用竖线字符。

## 9. 原始 detector x 响应图

对一个或多个 run 目录生成 detector x 方向 1 mm bin-count 响应：

```bash
MPLCONFIGDIR=/tmp/mss_matplotlib \
/home/ldn/miniforge3/bin/conda run -n data python scripts/plot_detector_response.py \
  results/near_door \
  --channels all,k0,k1,ms
```

也可以只处理单个 run 或某个子目录：

```bash
MPLCONFIGDIR=/tmp/mss_matplotlib \
/home/ldn/miniforge3/bin/conda run -n data python scripts/plot_detector_response.py \
  results/near_door/open/poseC/normal/E560/seed1234 \
  --output-dir results/analysis/detector_response_check \
  --channels all,k0,k1,ms
```

生成同一能量下的 open / collimated 系统对比图：

```bash
MPLCONFIGDIR=/tmp/mss_matplotlib \
/home/ldn/miniforge3/bin/conda run -n data python scripts/plot_detector_response.py \
  results/near_door \
  --channels all,k0,k1,ms \
  --comparison-grid
```

脚本会递归查找包含以下文件的 run 目录：

```text
metadata.yaml
events.csv
```

bin 规则：

- 默认 `--bin-width-mm 1.0`；
- 使用 `metadata.yaml` 中的 `detector.actual_x_range_mm` 作为响应范围；
- bin 为左闭右开 `[x_min, x_max)`，最后一个 bin 包含右边界；
- 零计数 bin 会保留在内部聚合结果中，保证不同 run 和不同状态的 bin 对齐。

支持的 channel：

| channel | 定义 |
|---|---|
| `all` | 全部 detected particles |
| `k0`, `k1`, `k2`, `k3` | `scatter_count_total` 分别等于 0、1、2、3 |
| `k_ge4` | `scatter_count_total >= 4` |
| `ms` | `scatter_count_total >= 2` |
| `single_or_zero` | `scatter_count_total <= 1` |

输出：

| 文件 | 作用 |
|---|---|
| `results/analysis/detector_response/<run_id>_<channel>.png` | 对应 run/channel 的 detector x bin-count 响应图 |
| `results/analysis/detector_response_comparison/comparison_E<energy>_<channel>.png` | 每张图固定一个 energy 和一个 channel，行是状态，列是 open / collimated |

默认不写 CSV。若需要检查中间 bin 表和对比图索引，可加 `--write-csv`，额外输出：

| 文件 | 作用 |
|---|---|
| `results/analysis/detector_response/detector_response_bins.csv` | 长表，每行一个 run + channel + x bin |
| `results/analysis/detector_response_comparison/detector_response_comparison_index.csv` | 对比图索引 |

单 run 图使用 raw count 作为 y 轴。对比图使用当前 run/channel 下的 bin yield，即 `bin_count / channel_total_count`；例如 `ms` 图的分母是该 run 中所有 `scatter_count_total >= 2` 的探测粒子数。每张对比图列固定为 `open` / `collimated`，行覆盖输入目录中发现的全部状态；已知 near-door 状态优先按 `Pose-R normal`、`Pose-C normal`、`Pose-C PE`、`Pose-C Flour` 排列，其他新增状态稳定追加。缺失条件会显示 `missing`。

当前绘图依赖 `matplotlib`，建议使用 conda 环境 `data`。设置 `MPLCONFIGDIR=/tmp/mss_matplotlib` 是为了避免 matplotlib 在只读 home config 目录下创建缓存失败。

## 10. 指标口径

基础计数：

| 指标 | 定义 |
|---|---|
| `N_detected_total` | `events.csv` 行数 |
| `N_detected_primary` | `is_primary_gamma == 1` |
| `N_detected_secondary` | `is_primary_gamma == 0` |
| `N_0` / `N_1` / `N_2` / `N_3` / `N_ge4` | 按 `scatter_count_total` 分箱 |
| `N_ms` | `N_2 + N_3 + N_ge4` |
| `R_*` | `N_* / N_detected_total` |
| `Y_*` | `N_* / n_primary` |

可见性指标：

- normal 与 abnormal 按 `system + pose + energy + seed` 配对；
- `DeltaH_* = H_abnormal - H_normal`；
- 单 seed 时 `CNR_*` 输出 `NaN`；
- 多 seed 时 `CNR_*` 使用 seed 间 delta 的均值与标准差计算；
- `P_pos` / `P_neg` 来自 detector bin 差异图中正 / 负 bin 比例。

层来源归因：

| region_id | layer_id |
|---|---|
| `near_door_outer_metal`, `far_door_outer_metal` | `door_outer_metal` |
| `near_door_cavity_air`, `far_door_cavity_air`, `target` | `door_cavity` |
| `near_door_reinforcement`, `far_door_reinforcement` | `door_reinforcement` |
| `near_door_inner_metal`, `far_door_inner_metal` | `door_inner_metal` |
| `near_door_trim`, `far_door_trim` | `door_trim` |
| 其他 | `other` |

## 11. 推荐工作流

1. 确认或修改 Pose-R / Pose-C offset。
2. 生成 YAML：

```bash
python3 scripts/generate_near_door_experiment_configs.py \
  --pose-r-offset 0,480 \
  --pose-c-offset 0,320 \
  --seeds 1234,2234,3234
```

3. 检查 `config/generated/near_door/manifest.yaml`。
4. 抽取 1-2 个 YAML 做小粒子数 smoke run。
5. 确认 `metadata.yaml` 中 energy、pose、collimator、target 信息正确。
6. 使用 `scripts/run_experiment_queue.py` 批量运行全部 configs。
7. 运行分析脚本生成 summary。
8. 用 `energy_scan_summary.csv` 和 `visibility_summary.csv` 选择后续重点能量点和统计量。

## 11. 测试

仅测试 near-door 脚本：

```bash
python3 -m unittest tests/test_near_door_experiments.py
```

同时测试现有诊断扩展和 near-door 工具：

```bash
python3 -m unittest tests/test_diagnostics.py tests/test_near_door_experiments.py
```

构建检查：

```bash
cmake --build build -j
```

## 12. 注意事项

- `Vehicle_Flour` 是近似面粉 / 低 Z 填充物材料，当前密度和元素比例用于实验对照；若后续有实测材料参数，应更新 C++ 材料定义并记录来源。
- 默认 `target_component` 为 `near_rear_door_insert`，只检测近层车门 insert，不检测 seat insert 或 trunk insert。
- `collimated` 条件保持 base config 的单一 `profile_file/profile_id`，不做多准直器结构扫描。
- open-panel 默认只设置 `collimator.enable=false`；是否扩大 detector 由 `--open-detector-range` 显式控制。
- summary CSV 是后处理结果，不是 Geant4 基础程序的自动输出。
- near-door 生成配置默认覆盖当前目标 run 目录；需要保留旧结果时，应更换 seed、输出目录或把 `existing_run_policy` 改回 `fail`。
