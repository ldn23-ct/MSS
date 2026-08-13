# articlev2 仿真实验自动化工具说明

> 文档状态：articlev2 当前仿真自动化与后处理运行说明。
> 职责：说明逐 pose 配置生成、队列执行、恢复、结果组织和 profile-aware 后处理链路。
> 上游：预研实验设计和项目 v2 的 Geant4 核心。
> 下游：articlev2 有效事件数据层、数据审计和 E1 后处理；项目级导航见 [`project_structure.md`](project_structure.md)。

## 1. 目的与边界

本文说明 `docs/simulation_experiment_design_v2.md` 中当前 articlev2 P0–P9 源项响应实验的配置生成、队列执行、数据清洗、审计和 E1 后处理方式。

核心工具为：

- `scripts/monte_carlo/generate_source_response_experiment_configs.py`
- `scripts/monte_carlo/run_experiment_queue.py`
- `scripts/data_processing/clean_events.py`
- `scripts/data_processing/estimate_slit_boundaries.py`
- `scripts/data_processing/slit_channels.py`
- `scripts/data_processing/audit_experiment_data.py`
- `scripts/postprocessing/e1/run.py`
- `scripts/postprocessing/e1/analyze_roi_sensitivity.py`

前者把固定的物理条件和扫描设计展开为逐 pose YAML，并生成统一的 `manifest.yaml`；后者读取 manifest，逐项调用现有 `MSS` 程序，并负责 dry-run、完成检测、状态保存和任务恢复。

本文覆盖：

- articlev2 配置和 manifest 的生成；
- 一份 YAML 对应一个 pose 的任务语义；
- 正式运行前的 dry-run；
- 队列状态保存、恢复、失败处理和分片；
- 每个 pose 的原始事件级输出组织；
- 有效深度事件清洗、固定 S1–S6 channel 标签和数据资格审计；
- E1 正式分析和 ROI 敏感性分析；
- E2/E3 预留接口和未迁移源码快照的边界。

本文不定义：

- 正式 Monte Carlo 结果的物理解释；
- 跨 pose CSV 合并；
- 尚未实现的 E2/E3 论文统计指标。

所有命令默认从仓库根目录执行。

## 2. 当前 articlev2 批次

默认生成批次为：

| 项目 | 默认值 |
|---|---|
| campaign | `articlev2` |
| energy | `560 keV` mono |
| primary | 每 pose `2e7`（以后处理时每个 run 的 metadata 为准） |
| threads | 每个 MSS 进程 `8` |
| base seed | `1234` |
| 标准 center | `P0–P6 × P001/P002`，14 个任务 |
| grid | `P0/P2/P4/P6 × P001`，4 个物理条件、324 个任务 |
| E7 补充 center | `P7/P8/P9 × P001`，3 个任务 |
| 物理条件数 | `21` |
| center 配置数 | `17` |
| grid 配置数 | `324` |
| 总配置/任务/pose run | `341` |
| 总 primary | `6.82×10^9` |
| seed 范围 | `1234–1574` |

profile 与探测范围映射为：

| profile | slit | `detector_x_range_zero_mm` |
|---|---|---|
| `P001` | `S2/S4/S6` | `[20,127] mm` |
| `P002` | `S1/S3/S5` | `[11,101] mm` |

grid 只生成 `P001`，offset 为：

```text
[-10, -7.5, -5, -2.5, 0, 2.5, 5, 7.5, 10] mm
```

x/y 取 `9×9` 笛卡尔积。生成顺序为 x-outer/y-inner，即固定一个 x 后依次遍历全部 y。grid 中的 `(0,0)` 使用独立 seed，不复用相同模体的 center 任务。

E7 尺寸序列在 manifest 中另外建立索引：

| 角色 | 模体 | 缺陷尺寸 |
|---|---|---|
| 无缺陷基线 | `P0` | 无缺陷 |
| E7 点 1 | `P7` | `5×5×5 mm³` |
| E7 点 2 | `P4` | `10×10×10 mm³` |
| E7 点 3 | `P8` | `15×15×10 mm³` |
| E7 点 4 | `P9` | `20×20×10 mm³` |

E7 使用 center、`P001` 和目标 slit `S4`。P4/P001 复用标准 center 条件，不重复生成任务。

## 3. 配置生成器

### 3.1 工具职责

`scripts/monte_carlo/generate_source_response_experiment_configs.py` 负责：

- 读取基础运行配置；
- 验证 P0–P9 geometry YAML；
- 验证准直器 CSV 中存在 `P001` 和 `P002`；
- 按固定条件顺序分配无重复 seed；
- 把每个 grid pose 展开为独立 YAML；
- 生成一个统一的 articlev2 manifest；
- 汇总任务数、物理条件数、primary 总数和 seed 范围。

默认输入为：

```text
config/base/article_base.yaml
config/geometry/article_files/P0.yaml ... P9.yaml
config/collimator/article_v2_collimator_profiles.csv
```

生成器不会运行 `MSS`，也不会生成仿真结果。

### 3.2 默认生成命令

```bash
python -m scripts.monte_carlo.generate_source_response_experiment_configs
```

默认输出：

```text
config/generated/articlev2/
├── manifest.yaml
└── configs/
    ├── center/
    │   ├── P0_P001.yaml
    │   ├── P0_P002.yaml
    │   └── ...
    └── grid/
        ├── P0_P001/
        │   ├── pose_xm10_ym10.yaml
        │   ├── ...
        │   └── pose_x10_y10.yaml
        ├── P2_P001/
        ├── P4_P001/
        └── P6_P001/
```

`center/` 中有 17 份 YAML；四个 grid 条件目录各有 81 份 YAML，共 324 份。

### 3.3 CLI 参数

生成器支持：

```text
--repo-root PATH
--base-config PATH
--geometry-dir PATH
--profile-file PATH
--campaign-id ID
--output-dir PATH
--overwrite
--energy-kev VALUE
--n-primary-per-pose N
--threads N
--base-seed N
```

例如生成一个低统计量、单线程的独立检查批次：

```bash
python -m scripts.monte_carlo.generate_source_response_experiment_configs \
  --campaign-id articlev2_check \
  --energy-kev 560 \
  --n-primary-per-pose 10 \
  --threads 1 \
  --base-seed 5000
```

未显式传 `--output-dir` 时，输出目录由 campaign 决定：

```text
config/generated/<campaign-id>/
```

生成 YAML 中的仿真结果根目录也使用 campaign：

```text
results/<campaign-id>/events/raw/...
```

仅覆盖 `--output-dir` 只改变 generated 配置保存位置，不改变配置内部的结果 campaign 路径；结果根目录由 `--campaign-id` 决定。需要隔离新结果时应同时使用新的 `--campaign-id`。

### 3.4 非空目录策略

默认情况下，生成器不会覆盖非空输出目录。如果目标目录中已有文件，会 fail fast：

```text
generated output directory is not empty
```

确认需要用新配置完全替换指定 generated 目录时，显式传入 `--overwrite`：

```bash
python -m scripts.monte_carlo.generate_source_response_experiment_configs \
  --campaign-id articlev2 \
  --output-dir config/generated/articlev2 \
  --overwrite
```

覆盖模式先在 `--output-dir` 的同级临时目录完成全部 YAML 和 `manifest.yaml` 生成；仅当生成成功后，才完整替换目标目录。因此目标目录中的任意手工文件、旧 manifest、旧 YAML 和过期子目录都会被舍弃；若生成校验失败，原目录保持不变。

`--overwrite` 只作用于 `--output-dir` 指定的 generated 配置目录。它不会删除或覆盖 `results/` 下的仿真 run 目录；生成 YAML 中的 `output.existing_run_policy` 仍为 `fail`。覆盖前应确认 `--output-dir` 正确；如需保留旧配置，请先使用新的 `--campaign-id`、新的 `--output-dir` 或手工备份。

## 4. 单 pose 配置语义

articlev2 的任务粒度固定为：

```text
一份 YAML = 一个 pose = 一个 seed = 一次 MSS 调用 = 一个 run
```

center 和 grid 生成 YAML 都使用单元素 list mode。例如 `pose_xm7p5_y2p5.yaml` 中：

```yaml
pose:
  mode: list
  list:
    head_offset_x_mm: [-7.5]
    head_offset_y_mm: [2.5]
  grid:
    x_offsets_mm: []
    y_offsets_mm: []
```

因此，manifest 中的 grid 只表示扫描设计和条件分类；任何 articlev2 YAML 都不会在一次 MSS 进程中顺序执行 81 个 pose。

小数 pose ID 使用规范化编码：

```text
-7.5 -> m7p5
-2.5 -> m2p5
 2.5 -> 2p5
 7.5 -> 7p5
```

例如：

```text
(-7.5, 2.5) -> pose_xm7p5_y2p5
```

默认 seed 顺序为：

| 任务段 | seed |
|---|---|
| P0–P6 标准 center | `1234–1247` |
| P0 grid | `1248–1328` |
| P2 grid | `1329–1409` |
| P4 grid | `1410–1490` |
| P6 grid | `1491–1571` |
| P7/P8/P9 center | `1572–1574` |

每份配置只有一个 pose，其 `pose_index` 在 MSS 配置内部为 `0`，所以该 run 的实际 seed 等于 YAML 中的 `run.random_seed`。manifest 中 grid case 的 `pose_index` 是该 pose 在所属 `9×9` 物理条件中的扫描序号，用于任务追踪，不改变 MSS 内部的单 pose 索引。

## 5. Manifest

统一入口为：

```text
config/generated/articlev2/manifest.yaml
```

顶层主要字段包括：

```text
experiment
campaign_id
task_granularity
parameters
profile_settings
scan_design
run_safety
summary
cases
```

其中：

```yaml
experiment: source_response_simulation_campaign
task_granularity: one_pose_per_config
```

每个 `cases[]` 条目至少记录：

- 唯一 `case_id` 和物理 `condition_id`；
- generated YAML 路径；
- center/grid 分类；
- phantom、geometry 和 defect 信息；
- profile 和对应 slit 列表；
- detector x 范围；
- energy、primary 和 thread；
- pose ID、offset、条件内 pose index；
- 单 pose seed；
- 预期结果根目录。

manifest 中的 `summary` 是生成结果的快速完整性检查入口。正式默认值应为：

```yaml
physical_condition_count: 21
config_count: 341
task_count: 341
center_config_count: 17
grid_condition_count: 4
grid_config_count: 324
total_pose_runs: 341
total_primary: 6820000000
seed_start: 1234
seed_end: 1574
```

## 6. Dry-run

正式计算前先运行：

```bash
python -m scripts.monte_carlo.run_experiment_queue \
  --manifest config/generated/articlev2/manifest.yaml \
  --binary build/MSS \
  --dry-run
```

dry-run 会：

- 读取 manifest 和每份 generated YAML；
- 用与 C++ 一致的规则计算 pose ID、seed 和预期 run 目录；
- 标记每个任务为 `run` 或 `skip-complete`；
- 打印 341 个任务条目；
- 不启动 `MSS`；
- 不受 large-run guard 限制。

每行格式为：

```text
<manifest-index> <run|skip-complete> <case-id> <config-file>
```

dry-run 中出现 `skip-complete`，表示预期输出已经通过队列的完成检查，不表示该任务从 manifest 中消失。

## 7. 正式队列执行

推荐使用单一总 manifest，并显式保存 articlev2 队列状态：

```bash
python -m scripts.monte_carlo.run_experiment_queue \
  --manifest config/generated/articlev2/manifest.yaml \
  --binary build/MSS \
  --save-queue \
  --state-file results/queues/articlev2/queue_state.json \
  --allow-large-run
```

队列对每个待运行任务依次启动：

```bash
build/MSS --config <generated-yaml>
```

队列本身不会并行启动多个 MSS 进程。每个 MSS 进程内部的线程数来自 YAML：

```yaml
run:
  number_of_threads: 8
```

articlev2 manifest 把 large-run threshold 设为 `0`，因此任何非空正式队列都必须显式传 `--allow-large-run`。该参数只解除队列保护，不改变 primary 数量或物理参数。

共享队列不提供默认 state 路径。articlev2 启用队列保存、日志或解锁时必须显式传入独立的 `--state-file`，避免不同 campaign 或 shard 共用状态文件。

### 7.1 状态与日志

`queue_state.json` 记录：

- manifest 和 binary；
- 本次任务筛选参数；
- 每个 case 的状态；
- 预期 run、CSV 和 metadata 路径；
- attempt count、return code；
- start/end 时间和错误信息。

状态文件旁会创建运行锁：

```text
queue_state.json.lock
```

正常结束时锁会删除。脚本能自动清理进程已不存在的陈旧锁；只有确认没有队列进程仍在使用该 state file 时，才可将 `--force-unlock` 与对应的 `--state-file` 一起使用。

默认情况下 MSS 的 stdout/stderr 直接输出到终端。如需保存每个任务的日志：

```bash
python -m scripts.monte_carlo.run_experiment_queue \
  --manifest config/generated/articlev2/manifest.yaml \
  --binary build/MSS \
  --state-file results/queues/articlev2/queue_state.json \
  --log-dir results/queues/articlev2/logs \
  --allow-large-run
```

传入 `--state-file` 会自动启用 `--save-queue`；`--log-dir` 必须与 `--state-file` 一起使用。日志实际保存在 `--log-dir` 下的 queue ID 子目录中。

### 7.2 失败策略

默认遇到第一个失败任务即停止。若希望记录失败并继续后续 pose：

```bash
--continue-on-failure
```

任务进程返回非零，或进程结束后预期输出不完整，都会被记为 `failed`。

## 8. 输出目录与完成判定

center 结果写入：

```text
results/articlev2/events/raw/center/<phantom>/<profile>/<run-id>/
```

grid 结果写入：

```text
results/articlev2/events/raw/grid/<phantom>/<profile>/<run-id>/
```

每个正式 run 目录包含：

```text
events.csv
metadata.yaml
tmp/
```

run ID 由 MSS 生成，当前格式为：

```text
<pose-id>_<energy>_seed<seed>
```

collimator 和 model-state 仍记录在配置及 metadata 中，但不再进入 run ID。articlev2 默认能量为 `560 keV`，例如：

```text
pose_xm7p5_y2p5_E560keV_seed1262
```

队列把任务判定为完成需要同时满足：

- 预期 run 目录存在；
- `metadata.yaml` 存在；
- `events.csv` 存在；
- metadata 中 `run_id` 与预期值一致；
- metadata 中 `n_primary` 与 YAML 的 `run.n_primary_per_pose` 一致。

即使 `events.csv` 只有 header，只要 MSS 正常完成且上述 metadata 一致，也属于完整输出。

## 9. 中断恢复与重跑

### 9.1 恢复同一队列

中断后使用与首次运行相同的 manifest、state file 和筛选参数重新执行命令：

```bash
python -m scripts.monte_carlo.run_experiment_queue \
  --manifest config/generated/articlev2/manifest.yaml \
  --binary build/MSS \
  --state-file results/queues/articlev2/queue_state.json \
  --allow-large-run
```

恢复时：

- 输出完整的 pose 标记为 completed 并跳过；
- 上次停在 `running`、但未形成完整输出的任务重置为 pending；
- failed 或 pending 任务重新进入执行；
- 完成判定以实际 `events.csv` 和 `metadata.yaml` 为准，不只依赖 state 中的旧状态。

### 9.2 主动重跑完成任务

`--rerun-completed` 会让队列再次启动已完成任务，但 generated YAML 默认使用：

```yaml
output:
  existing_run_policy: fail
```

因此，如果原 run 目录仍然非空，直接使用 `--rerun-completed` 会被 MSS 的输出保护拒绝。需要重跑时应先人工确认并移动原 run 目录，或者使用新的 campaign 和 seed 重新生成配置。不要依靠队列覆盖现有结果。

## 10. 分段与分片

articlev2 队列统一使用 manifest index、数量上限或 shard 选择任务；旧 article 实验编号筛选接口已经移除。

### 10.1 按 index 区间

```bash
python -m scripts.monte_carlo.run_experiment_queue \
  --manifest config/generated/articlev2/manifest.yaml \
  --binary build/MSS \
  --start-index 0 \
  --end-index 100 \
  --state-file results/queues/articlev2/part_000_100_state.json \
  --allow-large-run
```

`--start-index` 包含起点，`--end-index` 不包含终点；上例运行 manifest index `[0,100)`。

继续下一段：

```bash
--start-index 100 --end-index 200
```

临时限制本次最多选择 N 个任务可使用：

```bash
--limit 10
```

### 10.2 均匀 shard

四个 shard 中的第 0 个：

```bash
python -m scripts.monte_carlo.run_experiment_queue \
  --manifest config/generated/articlev2/manifest.yaml \
  --binary build/MSS \
  --shard-count 4 \
  --shard-index 0 \
  --state-file results/queues/articlev2/shard0_state.json \
  --log-dir results/queues/articlev2/shard0_logs \
  --allow-large-run
```

其他进程或机器把 `--shard-index` 改为 `1`、`2`、`3`，并为每个 shard 使用独立的 state 和 log 路径。所有 shard 必须使用同一份未修改 manifest；不要让两个 shard 选择到同一个 index。

若先使用 `--start-index/--end-index`，shard 会在该区间过滤结果上分配任务；`--limit` 最后生效。

## 11. article v1 的历史边界

旧 article v1 配置生成器、专属 batch merge、raw cleanup 和实验编号筛选已经从活跃代码中移除。历史说明仍可在 `docs/archive/` 查阅，但不能作为当前运行入口。articlev2 的每个配置只对应一个 pose，队列始终保留 `events/raw/` 中的原始事件与 metadata，也不会创建 `by_condition/`。

## 12. 结果目录契约

```text
results/articlev2/
├── events/
│   ├── raw/
│   └── valid/
├── data_processing/
│   ├── slit_channels/
│   └── audit/
└── postprocessing/
    ├── E1/
    │   ├── figures/
    │   ├── tables/
    │   ├── roi_sensitivity/
    │   └── archive/analysis_v2/
    ├── E2/
    └── E3/
```

`events/raw/` 是不可原地改写的仿真事实层，`events/valid/` 是带固定 `slit_group/slit_label` 的清洗层；数据处理产物与论文后处理产物分别进入 `data_processing/` 和 `postprocessing/`。完整契约见 `results/README.md`。

## 13. 数据清洗与审计

清洗全部 raw run：

```bash
python -m scripts.data_processing.clean_events \
  --results-root results/articlev2
```

审计 raw/valid 配对、schema、行数守恒、边界 hash 和标签：

```bash
python -m scripts.data_processing.audit_experiment_data \
  --results-root results/articlev2
```

默认输出分别位于 `events/valid/` 和 `data_processing/audit/`。目标目录已有内容时必须显式传入 `--overwrite`，发布过程使用临时目录和原子替换，避免留下半成品。

## 14. E1 后处理与预留实验

E1 默认读取审计结果，只处理当前正式 E1 数据：

```bash
python -m scripts.postprocessing.e1.run \
  --results-root results/articlev2
```

结果写入 `postprocessing/E1/`，包含 figures、tables、manifest、report 和 acceptance summary。覆盖已有正式输出时使用 `--overwrite`；同目录中的 `roi_sensitivity/` 和 `archive/` 会被保留。

ROI 敏感性分析独立运行：

```bash
python -m scripts.postprocessing.e1.analyze_roi_sensitivity \
  --results-root results/articlev2
```

E2/E3 当前只有目录、README 和输入输出约定，后续必须基于 `events/valid/` 与 `slit_label` 实现。`scripts/postprocessing/_archive/` 仅保存未迁移旧 schema 源码，不是正式入口，也不维护测试。

## 15. 测试与验收

使用 data conda 环境运行精简后的完整测试：

```bash
conda run -n data python -m unittest discover -s tests -p 'test_*.py'
```

正式验收还应确认生成器得到 341 个唯一任务、seed 为 1234–1574，审计 `error_count = 0`，以及 E1 acceptance 为 pass。本轮代码与数据结构整改不要求重新运行昂贵的 Geant4 正式仿真。
