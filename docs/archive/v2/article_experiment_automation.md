# 论文实验仿真自动化工具说明

> 文档状态：项目 v2 归档中已实现并冻结的 article v1 自动化链路。
> 职责：说明旧 article campaign 的生成、队列、batch 合并和三通道后处理。
> 上游：冻结的 `article_design.md` 与 Geant4 核心数据契约。
> 下游：article v1 结果复现和兼容性维护；项目级导航见 [`project_structure.md`](../../project_structure.md)。

## 1. 目的与边界

本文说明 `docs/archive/v2/article_design.md` 中论文实验所需仿真任务的自动化生成和队列执行方式。

相关工具包括：

- `scripts/generate_article_experiment_configs.py`
- `scripts/run_experiment_queue.py`
- `scripts/article/clean_events.py`
- `scripts/article/plot_grid_response.py`

其中生成器和队列脚本只负责仿真任务自动化：

- 生成 Geant4 主入口 YAML；
- 生成实验 manifest；
- 组织 generated geometry；
- 串行调用现有 `MSS` 程序执行队列；
- 支持 dry-run、smoke-run、batch 拆分、跳过已完成任务、按实验段或序号切分任务。

生成器、队列脚本和 Geant4 基础程序不做：

- 后处理；
- 绘图；
- 统计分析；
- CNR 或论文指标；
- 论文表格；
- slit-resolved 统计；
- 修改正式 `events.csv`、`events_debug.csv` 或 `metadata.yaml` 基础 schema。

`scripts/article/` 下的脚本是显式的派生后处理工具，只读取 `by_condition/` 下的 `events.csv` 与 `metadata.yaml`，输出清洗数据、响应矩阵和预览图，不修改 Geant4 原始输出 schema。

## 2. 与实验设计的对应关系

当前实现覆盖 `docs/archive/v2/article_design.md` 中需要新增仿真的实验：

| 实验 | 脚本支持 | 仿真条件 |
|---|---|---|
| E0 | 支持 | `P0/P1/P2/P3 × PMMA energy list × center pose` |
| E1 | 支持 | `P0/P1/P2/P3 × E_star × grid` |
| E2 | 不新增仿真 | 从 E1 grid 数据中选代表性 pose |
| E3 | 支持 | `M0/M1/M2/M3 × metal energy list × center/reference poses` |
| E4 | 支持 | `M0/M1/M2/M3 × E_star_metal × grid` |
| E5 | 暂不支持 | 金属厚度变量尚未定义为可生成 geometry |

模体命名固定为：

| 编号 | PMMA | 金属表层 |
|---:|---|---|
| 0 | `P0`，对照 | `M0`，对照 |
| 1 | `P1`，浅层 | `M1`，浅层 |
| 2 | `P2`，中层 | `M2`，中层 |
| 3 | `P3`，深层 | `M3`，深层 |

manifest 中记录：

- `phantom_id`
- `phantom_group`
- `defect_depth_id`
- `defect_depth_label`
- `defect_material`
- `experiment`
- `energy_keV`
- `pose`
- `batch_index`
- `seed`
- `threads`
- `n_primary_per_pose`

## 3. 当前修订约束

当前自动化实现采用用户确认后的修订约束：

```text
source incident_theta_deg = 90.0
source focal_spot_diameter_mm = 5.0
grid type = nonuniform local ROI sampling
grid offsets x/y = [-24, -18, -15, -8, 0, 8, 15, 18, 24] mm
```

注意：`docs/archive/v2/article_design.md` 中早期推荐的 `21 × 15`、`25 × 17`、`15 × 11` grid 是论文设计草案中的较大规模方案。当前脚本按本阶段确认的局部 ROI 非均匀小 grid 执行，即 x/y 两个方向均使用上述 9 个 offset，形成 `9 × 9` 个 pose。

`E_star` 和 `E_star_metal` 不自动选择，必须由用户显式传入：

- `--e-star-kev`
- `--e-star-metal-kev`

E0 与 E3 的能量扫描列表可以按材料类别显式设置：

- `--pmma-energies-kev` 控制 E0；
- `--metal-energies-kev` 控制 E3；
- 默认值均为 `60,160,260,360,460,560`。

## 4. 生成内容

默认输出目录为：

```text
config/generated/article/<campaign_id>/
├── manifest.yaml
└── configs/
    ├── E0/
    ├── E1/
    ├── E3/
    └── E4/
```

article geometry 源文件固定来自：

```text
config/geometry/phantom_yaml_files/P0.yaml ... M3.yaml
```

这些文件已经规范化为当前 C++ `VehicleROIConfigReader` 可直接读取的 VehicleROI-compatible YAML：

- 根 component 改为 `VehicleROI`；
- daughter 的 `host` 同步改为 `VehicleROI`；
- P/M 文件中已经显式存在的缺陷或 target 保持为普通几何组件；
- generated config 直接引用 `config/geometry/phantom_yaml_files/<phantom>.yaml`；
- 不再为每个 campaign 复制 `geometries/P0-M3.yaml`。

每个 generated YAML 只包含一个 pose。Geant4 原始 run 会先作为合并前临时产物写入：

```text
results/article/<campaign_id>/runs/<condition_id>/b<batch_index>/<run_id>/
```

其中 `<run_id>` 仍由 C++ 按 run-level 规则生成，并包含 seed。默认情况下，完整 article manifest 成功合并到 `by_condition/` 后，队列会删除这些 raw run 目录以节省空间。用户主要查看和后续分析的 batch 合并结果写入：

```text
results/article/<campaign_id>/by_condition/<experiment>/<phantom_id>/E<energy>/<pose>/
```

合并结果目录不包含 batch 或 seed，包含：

```text
events.csv
metadata.yaml
```

debug 模式仍按现有 C++ 逻辑输出：

```text
events_debug.csv
metadata.yaml
```

## 5. 生成实验 YAML

正式生成完整 E0/E1/E3/E4 矩阵示例：

```bash
python3 scripts/generate_article_experiment_configs.py \
  --campaign-id article_run01 \
  --threads 8 \
  --e-star-kev 260 \
  --e-star-metal-kev 360 \
  --n-primary-per-pose 1000000 \
  --batch-count 1
```

生成器结束时会打印本次 campaign 摘要，包括物理条件数、总 case 数、每 case 粒子数、batch 数、每物理条件总粒子数、线程数、PMMA 能量列表、金属能量列表和输出目录。

生成单个实验段：

```bash
python3 scripts/generate_article_experiment_configs.py \
  --campaign-id article_E0_run01 \
  --experiments E0 \
  --threads 8 \
  --pmma-energies-kev 60,160,260,360,460,560 \
  --n-primary-per-pose 1000000
```

生成 E1 时必须提供 `E_star`：

```bash
python3 scripts/generate_article_experiment_configs.py \
  --campaign-id article_E1_run01 \
  --experiments E1 \
  --threads 8 \
  --e-star-kev 260 \
  --n-primary-per-pose 1000000
```

生成 E4 时必须提供 `E_star_metal`：

```bash
python3 scripts/generate_article_experiment_configs.py \
  --campaign-id article_E4_run01 \
  --experiments E4 \
  --threads 8 \
  --e-star-metal-kev 360 \
  --n-primary-per-pose 1000000
```

为 PMMA 和金属分别指定能量扫描列表：

```bash
python3 scripts/generate_article_experiment_configs.py \
  --campaign-id article_custom_energy \
  --experiments E0,E3 \
  --threads 8 \
  --pmma-energies-kev 80,120,160 \
  --metal-energies-kev 100,200,300 \
  --n-primary-per-pose 1000000
```

E1 / E4 使用固定非均匀 `9 × 9` grid，不需要传 grid 参数：

```bash
python3 scripts/generate_article_experiment_configs.py \
  --campaign-id article_nonuniform_grid \
  --experiments E1,E4 \
  --threads 8 \
  --e-star-kev 260 \
  --e-star-metal-kev 360
```

覆盖 source 位置：

```bash
python3 scripts/generate_article_experiment_configs.py \
  --campaign-id article_source_override \
  --threads 8 \
  --e-star-kev 260 \
  --e-star-metal-kev 360 \
  --source-pos-zero-mm 0,0,-185
```

如果不传 `--source-pos-zero-mm`，source 位置继承 `config/base/simulation_config_v2.yaml`。

## 6. Smoke Run

smoke 模式只生成少量 case，用于检查配置链路和队列行为：

```bash
python3 scripts/generate_article_experiment_configs.py \
  --campaign-id article_smoke \
  --experiments E0 \
  --smoke \
  --n-primary-per-pose 10
```

`--smoke` 未显式传 `--threads` 时默认使用：

```text
threads = 1
```

建议先 dry-run：

```bash
python3 scripts/run_experiment_queue.py \
  --manifest config/generated/article/article_smoke/manifest.yaml \
  --dry-run
```

确认后再运行少量 smoke case：

```bash
python3 scripts/run_experiment_queue.py \
  --manifest config/generated/article/article_smoke/manifest.yaml \
  --binary ./build/MSS \
  --allow-large-run
```

## 7. 队列执行

队列脚本逐个启动：

```bash
./build/MSS --config <generated-yaml>
```

不会并行启动多个 `MSS` 进程。多线程只由单个 generated YAML 中的：

```yaml
run:
  number_of_threads: <threads>
```

控制。

正式运行建议先 dry-run：

```bash
python3 scripts/run_experiment_queue.py \
  --manifest config/generated/article/article_run01/manifest.yaml \
  --dry-run
```

实际运行完整队列：

```bash
python3 scripts/run_experiment_queue.py \
  --manifest config/generated/article/article_run01/manifest.yaml \
  --binary ./build/MSS \
  --allow-large-run
```

保存队列状态：

```bash
python3 scripts/run_experiment_queue.py \
  --manifest config/generated/article/article_run01/manifest.yaml \
  --binary ./build/MSS \
  --save-queue \
  --state-file results/queues/article_run01/queue_state.json \
  --allow-large-run
```

`queue_state.json` 记录每个 case 的 `status`、`return_code`、`started_at`、`ended_at`、`attempt_count` 和预期输出文件，足够用于检查队列完成、失败、跳过和恢复状态。

若需要排查 Geant4 原始 run 输出，可显式保留 `runs/`：

```bash
python3 scripts/run_experiment_queue.py \
  --manifest config/generated/article/article_run01/manifest.yaml \
  --binary ./build/MSS \
  --allow-large-run \
  --keep-raw-runs
```

逐 case 日志不是必须产物。只有需要保存 Geant4 stdout/stderr 以便排错时，才显式增加：

```bash
--log-dir results/queues/article_run01/logs
```

未传 `--log-dir` 时，Geant4 输出直接显示在终端；失败状态仍写入 `queue_state.json`。

队列会跳过已完成任务。完成判定沿用现有逻辑：

- run 目录存在；
- `metadata.yaml` 存在；
- `events.csv` 或 `events_debug.csv` 存在；
- metadata 中的 `run_id` 与预期一致；
- metadata 中的 `n_primary` 与 config 中 `run.n_primary_per_pose` 一致。

## 8. 多机器分段运行

不同机器硬件不同，因此线程数、batch 数和每 run 粒子数都应在生成 YAML 时显式设置。

推荐调参方式：

- CPU 核心少或内存紧张：降低 `--threads`，降低 `--n-primary-per-pose`，必要时增加 `--batch-count` 拆成更多短 run。
- CPU 核心多且内存充足：提高 `--threads`，但队列脚本仍一次只启动一个 `MSS` 进程。
- 多台机器分担：用 `--start-index/--end-index`、`--limit` 或 `--shard-count/--shard-index` 切片。
- 不建议两台机器同时写同一 manifest 切片到同一批 output directory。

`batch-count` 的语义是把同一物理条件拆成多个独立 Geant4 run。每个 batch 使用独立 seed，并先写入 `runs/<condition_id>/b<batch_index>/<run_id>/` 作为合并输入；队列完成完整 manifest 后会自动生成 `by_condition/` 合并结果。默认合并成功后删除 `runs/` 下对应 raw run；需要排查时传 `--keep-raw-runs` 保留。本阶段只做 batch CSV 拼接整理，不做统计分析。

按实验段运行：

```bash
python3 scripts/run_experiment_queue.py \
  --manifest config/generated/article/article_run01/manifest.yaml \
  --from-experiment E0 \
  --to-experiment E3 \
  --binary ./build/MSS \
  --allow-large-run
```

另一台机器从 E4 开始：

```bash
python3 scripts/run_experiment_queue.py \
  --manifest config/generated/article/article_run01/manifest.yaml \
  --from-experiment E4 \
  --binary ./build/MSS \
  --allow-large-run
```

只运行指定实验：

```bash
python3 scripts/run_experiment_queue.py \
  --manifest config/generated/article/article_run01/manifest.yaml \
  --only-experiments E4 \
  --binary ./build/MSS \
  --allow-large-run
```

按 manifest 序号切分：

```bash
python3 scripts/run_experiment_queue.py \
  --manifest config/generated/article/article_run01/manifest.yaml \
  --start-index 0 \
  --end-index 200 \
  --binary ./build/MSS \
  --allow-large-run
```

继续运行下一段：

```bash
python3 scripts/run_experiment_queue.py \
  --manifest config/generated/article/article_run01/manifest.yaml \
  --start-index 200 \
  --end-index 400 \
  --binary ./build/MSS \
  --allow-large-run
```

按均匀分片运行：

```bash
python3 scripts/run_experiment_queue.py \
  --manifest config/generated/article/article_run01/manifest.yaml \
  --shard-count 4 \
  --shard-index 0 \
  --binary ./build/MSS \
  --allow-large-run
```

限制本次最多启动 N 个 case：

```bash
python3 scripts/run_experiment_queue.py \
  --manifest config/generated/article/article_run01/manifest.yaml \
  --limit 10 \
  --binary ./build/MSS \
  --allow-large-run
```

## 9. 大规模运行保护

article manifest 默认写入：

```yaml
run_safety:
  large_run_case_threshold: 100
  allow_large_run_required: true
```

如果待运行 case 数超过阈值，队列脚本会拒绝实际启动，除非显式传：

```bash
--allow-large-run
```

`--dry-run` 不受该限制，推荐每次正式运行前先 dry-run 检查 case 列表。

## 10. Batch 合并输出

article manifest 中同一物理条件的多个 batch 会在队列结束后自动合并。合并条件为：

```text
experiment + phantom_id + energy_keV + pose + head_offset_x/y + geometry_file + defect_depth_id
```

合并规则：

- 只合并已完整完成的 Geant4 run；
- 若 manifest 中仍有未完成 case，则跳过合并，并在 `queue_state.json` 的 `merge` 节记录原因；
- `events.csv` header 保持与 source run 完全一致，不新增列；
- `event_id` 按各 batch 的 `n_primary` 做 offset，避免不同 batch 之间重复；
- `hit_id` 原样保留；
- 合并 `metadata.yaml` 记录 `merged_article_batches: true`、总 `n_primary`、source run 数、batch index、seed 和 source run dirs。
- 合并 metadata 额外记录 `merge.source_cases`，用于 raw run 删除后的可追溯性与恢复跳过判断；
- 默认合并成功后删除参与本次合并的 raw run leaf directories，并清理空的 batch / condition / `runs` 父目录；
- 若传 `--keep-raw-runs`，保留 raw run 目录，metadata 中记录 `raw_output_preserved: true`。

合并产物是仿真自动化整理结果，不属于统计分析、绘图、CNR 或论文表格生成。

## 11. 输出与重跑策略

article generated YAML 默认使用：

```yaml
output:
  existing_run_policy: fail
```

这样可以避免误覆盖已有仿真结果。article 队列默认在成功合并后删除 raw `runs/`，因此同一 manifest 再次运行时会优先根据 `by_condition/metadata.yaml` 中的 `merge.source_cases` 跳过已完成 case。若需要重跑，推荐：

1. 换新的 `--campaign-id`；
2. 或换新的 `--base-seed`；
3. 或手动确认后修改 generated YAML 的 `existing_run_policy`。

不要让多台机器同时运行同一个 manifest 切片到同一批 output directory。

## 12. Article 后处理脚本

`scripts/article/` 目录用于保存论文实验相关的派生数据处理脚本。这些脚本不属于 Geant4 基础事件生成链路，不会改写原始 `events.csv` 或 `metadata.yaml`；推荐把输出写到新的 `results/article/<campaign_id>/...` 派生目录。

运行绘图脚本前需要启用带有 `pandas`、`numpy`、`matplotlib` 和 `PyYAML` 的数据环境，例如：

```bash
conda activate data
```

### 12.1 `scripts/article/clean_events.py`

功能：

- 递归发现输入目录下的 `events.csv`；
- 按事件级条件清洗 detected gamma hit；
- 根据 `det_x` 所在区间新增 `slit_id` 列，取值为 `S1/S2/S3...`；
- 删除不需要进入清洗文件的事件追踪列；
- 将同目录 `metadata.yaml` 复制到镜像输出目录，便于后续绘图脚本直接读取 `n_primary`、pose offset 和条件信息。

清洗条件：

- `first_scatter_z >= 0`；
- `last_scatter_z >= 0`；
- `det_x` 落入脚本顶部 `DET_X_LEFT_EDGES_MM` 与 `DET_X_RIGHT_EDGES_MM` 定义的任一闭区间；该区间表示 `head_offset_x_mm = 0` 时的零偏置通道窗口，脚本会按每个 run 的 `head_offset_x_mm` 整体平移后再筛选。

默认 `det_x` 区间在脚本顶部直接修改，不提供命令行参数：

```python
DET_X_LEFT_EDGES_MM = [17.24, 84.21, 126.44]
DET_X_RIGHT_EDGES_MM = [27.10, 94.54, 136.04]
```

第 `i` 个区间映射为 `S{i+1}`。区间端点必须有限、左端点不大于右端点，且闭区间之间不得重叠；非法配置会 fail fast。

偏置读取规则：

- 普通 run metadata 使用顶层 `head_offset_x_mm`；
- article 合并后的 by-condition metadata 使用 `condition.head_offset_x_mm`；
- 若两处同时存在但数值不一致，脚本会 fail fast。

输入：

```text
--input-root   原始或合并后的 article 结果目录，可为单个 run 目录或 by_condition 根目录
--events-name  输入事件文件名，默认 events.csv
```

输出：

```text
--output-root  清洗结果根目录
--output-name  输出事件文件名，默认 events_clean.csv
```

输出目录会保留输入目录的相对层级。核心输出包括：

```text
<output-root>/
├── clean_manifest.yaml
├── clean_summary.csv
└── .../events_clean.csv
```

`events_clean.csv` 保留原始字段顺序，并追加 `slit_id`，但删除：

```text
event_id, hit_id, track_id, parent_id, is_primary_gamma,
gamma_source_type, gamma_source_process, gamma_source_region_id,
rayleigh_count
```

示例：

```bash
python3 scripts/article/clean_events.py \
  --input-root results/article/article_run01/by_condition \
  --output-root results/article/article_run01/cleaned_by_condition
```

若输出文件已存在，默认报错；确认覆盖时使用：

```bash
--overwrite
```

### 12.2 `scripts/article/summarize_scatter_counts.py`

功能：

- 递归发现输入目录下所有 `events_clean.csv`；
- 对每个文件分别统计 `S1`、`S2`、`S3`；
- 额外输出一行 `ALL`，表示同一文件中三个 slit 的合并计数；
- 使用流式 CSV 读取，不把大型事件文件整体载入内存。

输入文件必须包含：

```text
slit_id
scatter_count_total
```

`slit_id` 只允许为 `S1`、`S2` 或 `S3`。散射次数必须为非负整数；缺列、未知 slit、负数、非整数或非数值均会 fail fast。

统计口径：

```text
scatter_count_total == 0  -> 无效事件，不计入任何 N
N_total                   = N(scatter_count_total >= 1)
N_k1                      = N(scatter_count_total == 1)
N_ms                      = N(scatter_count_total >= 2)
N_total                   = N_k1 + N_ms
```

`ALL` 行的 `N_total`、`N_k1` 和 `N_ms` 分别等于同一文件中 `S1 + S2 + S3` 的对应计数。

输出为长表 CSV，每个输入文件固定输出 `S1`、`S2`、`S3`、`ALL` 四行：

```text
input_file,relative_file,slit_id,N_total,N_k1,N_ms
```

示例：

```bash
python3 scripts/article/summarize_scatter_counts.py \
  --input-root results/article/article_run01/cleaned_by_condition \
  --output-csv results/article/article_run01/scatter_counts.csv
```

可用 `--events-name` 修改递归查找的文件名，默认值为 `events_clean.csv`。若输出文件已存在，默认报错；确认覆盖时使用 `--overwrite`。

该脚本不读取原始 `events.csv` 来重新划分 slit，不生成图表、差异值或跨文件合并统计。输入应先经过 `clean_events.py`。

### 12.3 `scripts/article/plot_scatter_position_histogram.py`

功能：

- 递归读取 `clean_events.py` 生成的 `events_clean.csv` 和相邻 `metadata.yaml`；
- 统计 first / last scatter 在 global `x/y/z` 轴上的位置分布；
- 支持选择一个或多个 `S1/S2/S3`，先合并所选 slit，再生成一套 histogram；
- 将同一物理条件下的所有匹配输入作为条件级数据汇总，不计算逐 seed 统计量；
- 每个 bin 分别统计 total、k1 和 ms，其中 `total = k1 + ms`；
- 同时生成计数 CSV、条件级 count 柱状图和分析 manifest。

输入 CSV 必须包含：

```text
slit_id
scatter_count_total
<first|last>_scatter_<x|y|z>
```

相邻 metadata 必须包含正整数 `n_primary`，并使用以下任一格式提供 phantom 和物理条件：

- 原始 run metadata：顶层 `vehicle_model_id`、`vehicle_geometry_file`、`pose_id` 等字段；
- batch 合并 metadata：`merged_article_batches: true`，并在 `condition.phantom_id`、`condition.geometry_file`、`condition.pose` 等字段记录条件。

顶层 `random_seed` 或 `merge.seeds` 仅作为 manifest 溯源信息，不参与统计。脚本会验证筛选后的输入属于同一物理条件，并将各输入的 `n_primary` 和 bin count 直接求和，避免静默混合不兼容数据。

主要参数：

```text
--input-root      清洗结果根目录或单个 events_clean.csv
--phantom-id      需要统计的 phantom，例如 P0
--scatter-point   first 或 last
--axis            x、y 或 z
--slits           逗号分隔的 S1/S2/S3，默认 S1,S2,S3
--start-mm        histogram 起点
--bin-width-mm    bin 宽度，必须大于 0
--end-mm          可选终点；未提供时按最大有效坐标向上对齐到完整 bin
--output-dir      分析输出目录
--overwrite       允许覆盖已有的本脚本输出
```

bin 使用左闭右开区间 `[left, right)`，仅最后一个 bin 包含全局右端点。散射次数 `0` 表示没有有效散射来源，不进入 histogram。低于起点、超过显式终点或坐标非有限的事件不会进入 bin，其数量按输入文件记录在 manifest。

条件级计数定义为：

```text
total = N(scatter_count_total >= 1)
k1    = N(scatter_count_total == 1)
ms    = N(scatter_count_total >= 2)

对所有兼容输入文件分别分箱后求和：
count_total = sum(input_total_count)
count_k1    = sum(input_k1_count)
count_ms    = sum(input_ms_count)
```

脚本不计算逐 seed 均值、样本标准差或 SEM，也不拼接事件文件；合并只发生在 histogram 计数层。

输出：

```text
<output-dir>/
├── scatter_position_histogram.csv
├── scatter_position_histogram.png
└── analysis_manifest.yaml
```

P0、first-scatter z、2 mm bin 示例：

```bash
conda run -n data python scripts/article/plot_scatter_position_histogram.py \
  --input-root results/article/test_E1_P0_P5_E460_grid_x0_y0/cleaned \
  --phantom-id P0 \
  --scatter-point first \
  --axis z \
  --slits S2 \
  --start-mm 0 \
  --bin-width-mm 2 \
  --output-dir results/article/test_E1_P0_P5_E460_grid_x0_y0/first_scatter_z_P0
```

CSV 每个 bin 一行，计数字段为 `count_total`、`count_k1`、`count_ms` 和 `n_primary_total`。每行满足 `count_total = count_k1 + count_ms`。PNG 绘制条件级 `count_total`；manifest 的 `aggregation.mode` 为 `condition_total`，并逐输入文件记录路径、seed 溯源和排除计数。

### 12.4 `scripts/article/plot_grid_response.py`

功能：

- 读取 grid 模式下每个 pose 的事件文件和 `metadata.yaml`；
- 使用 `events_clean.csv` 中已有的 `slit_id`；
- 对每个 `phantom_id × slit_id × grid pose` 统计响应通道；
- 将非均匀采样 offset 按排序后的均匀矩阵索引显示，用于生成二维响应图。

输入：

```text
--input-root     clean_events.py 的输出根目录
--events-name    输入事件文件名，默认 events_clean.csv
--experiment     E1 或 E4 等实验编号
--energy         能量筛选，如 E460 或 460
--metadata-name  metadata 文件名，默认 metadata.yaml
--first-scatter-z-range-mm MIN_MM MAX_MM
                 可选的 first_scatter_z 闭区间筛选，单位 mm
```

默认 control phantom：

```text
E1 -> P0
E4 -> M0
```

必要时可用 `--control-phantom` 覆盖。

可选的 first-scatter 深度筛选在所有响应通道和 control phantom 差异计算之前执行。例如：

```bash
--first-scatter-z-range-mm 140 170
```

表示只保留满足 `140 <= first_scatter_z <= 170` 的事件。两个端点均包含；上下限必须有限且满足 `MIN_MM <= MAX_MM`。启用筛选时输入 CSV 必须包含 `first_scatter_z`，无法转换为数值、非有限或区间外的值均被排除。不传该参数时不执行深度筛选，也不额外要求该列。`n_primary` 保持原始值，`F_ms` 使用筛选后的 `N_ms / N_total`。

统计通道：

```text
I_total       = N_total
I_k1          = N(scatter_count_total == 1)
I_k2          = N(scatter_count_total == 2)
I_ms          = N(scatter_count_total >= 2)
I_without_ms  = N(scatter_count_total <= 1)
F_ms          = N_ms / N_total
```

差异图通道：

```text
Delta_I_total = N_total - N_total(control)
Delta_I_k1    = N_k1 - N_k1(control)
Delta_I_ms    = N_ms - N_ms(control)
```

输出：

```text
<output-dir>/
├── analysis_manifest.yaml
├── grid_response_long.csv
├── matrices/<phantom_id>/<slit_id>/<channel>.csv
├── figures/<phantom_id>/<slit_id>/<channel>.png
└── figures/panels/<phantom_id>_<slit_id>_<experiment>_panel.png
```

示例，读取清洗后的数据：

```bash
conda run -n data python scripts/article/plot_grid_response.py \
  --input-root results/article/article_run01/cleaned_by_condition \
  --experiment E1 \
  --energy E460 \
  --first-scatter-z-range-mm 140 170 \
  --output-dir results/article/article_run01/grid_response_E1_E460
```

`analysis_manifest.yaml` 的 `event_filters.first_scatter_z` 会记录筛选是否启用、实际上下限和闭区间规则。筛选对输入中的所有 slit、phantom、pose 和 control phantom 统一生效。

`plot_grid_response.py` 不直接支持原始 `events.csv` 的通道分配；若输入文件缺少 `slit_id`，应先运行 `clean_events.py` 生成 `events_clean.csv`。

该脚本只生成二维响应矩阵和预览图，不计算 CNR、ROI 指标、论文表格或事件级解释图。

## 13. 测试

仅测试 article 生成器和队列扩展：

```bash
python3 -m unittest tests/test_article_experiment_configs.py tests/test_experiment_queue.py
```

Article 事件清洗与散射计数测试：

```bash
python3 -m unittest tests/test_article_clean_events.py tests/test_article_scatter_counts.py
```

Scatter 位置 histogram 测试：

```bash
python3 -m unittest tests/test_article_scatter_position_histogram.py
```

Grid response 深度筛选测试：

```bash
python3 -m unittest tests/test_article_grid_response.py
```

语法检查：

```bash
python3 -m py_compile \
  scripts/generate_article_experiment_configs.py \
  scripts/run_experiment_queue.py \
  scripts/article/clean_events.py \
  scripts/article/summarize_scatter_counts.py \
  scripts/article/plot_scatter_position_histogram.py \
  scripts/article/plot_grid_response.py
```

后处理脚本 smoke 示例：

```bash
python3 scripts/article/clean_events.py \
  --input-root results/article/article_run01/by_condition/E1/P0/E460/grid_x0_y0 \
  --output-root /tmp/mss_article_clean_smoke \
  --overwrite
```

```bash
python3 scripts/article/summarize_scatter_counts.py \
  --input-root /tmp/mss_article_clean_smoke \
  --output-csv /tmp/mss_article_scatter_counts.csv \
  --overwrite
```

```bash
conda run -n data python scripts/article/plot_scatter_position_histogram.py \
  --input-root results/article/test_E1_P0_P5_E460_grid_x0_y0/cleaned \
  --phantom-id P0 \
  --scatter-point first \
  --axis z \
  --slits S2 \
  --start-mm 0 \
  --bin-width-mm 2 \
  --output-dir /tmp/mss_article_scatter_position_smoke \
  --overwrite
```

```bash
conda run -n data python scripts/article/plot_grid_response.py \
  --input-root /tmp/mss_article_clean_smoke \
  --experiment E1 \
  --energy E460 \
  --output-dir /tmp/mss_article_grid_response_smoke \
  --overwrite
```

## 14. 注意事项

- `S1/S2/S3` 不作为仿真 run 维度。
- `slit_id` 不写入 manifest case，也不写入 generated YAML；它只由后处理清洗脚本写入 `events_clean.csv`。
- `E_star` 和 `E_star_metal` 必须由用户显式给出。
- E2 不新增仿真，应从 E1 输出中选 pose。
- E5 当前没有自动化，因为金属厚度变体 geometry 尚未定义。
- 仿真自动化阶段不生成任何后处理 summary、图、指标或论文表格；`scripts/article/` 中的脚本属于用户显式调用的派生后处理工具。
