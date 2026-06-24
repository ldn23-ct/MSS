# 论文实验仿真自动化工具说明

## 1. 目的与边界

本文说明 `docs/article_design.md` 中论文实验所需仿真任务的自动化生成和队列执行方式。

相关工具包括：

- `scripts/generate_article_experiment_configs.py`
- `scripts/run_experiment_queue.py`

本工具只负责仿真任务自动化：

- 生成 Geant4 主入口 YAML；
- 生成实验 manifest；
- 组织 generated geometry；
- 串行调用现有 `MSS` 程序执行队列；
- 支持 dry-run、smoke-run、batch 拆分、跳过已完成任务、按实验段或序号切分任务。

本工具不做：

- 后处理；
- 绘图；
- 统计分析；
- CNR 或论文指标；
- 论文表格；
- slit-resolved 统计；
- 修改正式 `events.csv`、`events_debug.csv` 或 `metadata.yaml` 基础 schema。

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

每个 generated YAML 只包含一个 pose。Geant4 原始 run 作为可追溯中间产物写入：

```text
results/article/<campaign_id>/runs/<condition_id>/b<batch_index>/<run_id>/
```

其中 `<run_id>` 仍由 C++ 按 run-level 规则生成，并包含 seed。用户主要查看的 batch 合并结果写入：

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

`batch-count` 的语义是把同一物理条件拆成多个独立 Geant4 run。每个 batch 使用独立 seed，并保留在 `runs/<condition_id>/b<batch_index>/<run_id>/` 作为可追溯 raw 输出；队列完成完整 manifest 后会自动生成 `by_condition/` 合并结果。本阶段只做 batch CSV 拼接整理，不做统计分析。

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

合并产物是仿真自动化整理结果，不属于统计分析、绘图、CNR 或论文表格生成。

## 11. 输出与重跑策略

article generated YAML 默认使用：

```yaml
output:
  existing_run_policy: fail
```

这样可以避免误覆盖已有仿真结果。若需要重跑，推荐：

1. 换新的 `--campaign-id`；
2. 或换新的 `--base-seed`；
3. 或手动确认后修改 generated YAML 的 `existing_run_policy`。

不要让多台机器同时运行同一个 manifest 切片到同一批 output directory。

## 12. 测试

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
  scripts/run_experiment_queue.py
```

## 13. 注意事项

- `S1/S2/S3` 不作为仿真 run 维度。
- `slit_id` 不写入 manifest case，也不写入 generated YAML。
- `E_star` 和 `E_star_metal` 必须由用户显式给出。
- E2 不新增仿真，应从 E1 输出中选 pose。
- E5 当前没有自动化，因为金属厚度变体 geometry 尚未定义。
- 本阶段不生成任何后处理 summary、图、指标或论文表格。
