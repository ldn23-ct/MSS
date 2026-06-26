# 论文实验仿真自动化工具说明

## 1. 目的与边界

本文说明 `docs/article_design.md` 中论文实验所需仿真任务的自动化生成和队列执行方式。

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

当前实现覆盖 `docs/article_design.md` 中需要新增仿真的实验：

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

注意：`docs/article_design.md` 中早期推荐的 `21 × 15`、`25 × 17`、`15 × 11` grid 是论文设计草案中的较大规模方案。当前脚本按本阶段确认的局部 ROI 非均匀小 grid 执行，即 x/y 两个方向均使用上述 9 个 offset，形成 `9 × 9` 个 pose。

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
- `det_x` 落入脚本顶部 `DET_X_LEFT_EDGES_MM` 与 `DET_X_RIGHT_EDGES_MM` 定义的任一闭区间。

默认 `det_x` 区间在脚本顶部直接修改，不提供命令行参数：

```python
DET_X_LEFT_EDGES_MM = [9.0, 34.0, 100.0]
DET_X_RIGHT_EDGES_MM = [30.0, 96.0, 146.0]
```

第 `i` 个区间映射为 `S{i+1}`。区间端点必须有限、左端点不大于右端点，且闭区间之间不得重叠；非法配置会 fail fast。

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

### 12.2 `scripts/article/plot_grid_response.py`

功能：

- 读取 grid 模式下每个 pose 的事件文件和 `metadata.yaml`；
- 优先使用 `events_clean.csv` 中已有的 `slit_id`；
- 若通过 `--events-name events.csv` 直接读取原始事件文件，则按与清洗脚本相同的 `det_x` 区间临时生成 `slit_id`；
- 对每个 `phantom_id × slit_id × grid pose` 统计响应通道；
- 将非均匀采样 offset 按排序后的均匀矩阵索引显示，用于生成二维响应图。

输入：

```text
--input-root     clean_events.py 的输出根目录，或原始 by_condition 根目录
--events-name    输入事件文件名，默认 events_clean.csv
--experiment     E1 或 E4 等实验编号
--energy         能量筛选，如 E460 或 460
--metadata-name  metadata 文件名，默认 metadata.yaml
```

默认 control phantom：

```text
E1 -> P0
E4 -> M0
```

必要时可用 `--control-phantom` 覆盖。

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
  --output-dir results/article/article_run01/grid_response_E1_E460
```

示例，直接读取原始 `events.csv`：

```bash
conda run -n data python scripts/article/plot_grid_response.py \
  --input-root results/article/article_run01/by_condition \
  --events-name events.csv \
  --experiment E1 \
  --energy E460 \
  --output-dir results/article/article_run01/grid_response_E1_E460_raw
```

该脚本只生成二维响应矩阵和预览图，不计算 CNR、ROI 指标、论文表格或事件级解释图。

## 13. 测试

仅测试 article 生成器和队列扩展：

```bash
python3 -m unittest tests/test_article_experiment_configs.py tests/test_experiment_queue.py
```

同时确认 near-door 工具没有被队列扩展破坏：

```bash
python3 -m unittest tests/test_near_door_experiments.py
```

语法检查：

```bash
python3 -m py_compile \
  scripts/generate_article_experiment_configs.py \
  scripts/run_experiment_queue.py \
  scripts/article/clean_events.py \
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
