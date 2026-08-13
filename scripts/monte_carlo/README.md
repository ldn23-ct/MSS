# Monte Carlo 自动化脚本

本目录只负责生成 Geant4 输入配置和调度现有 `MSS` 可执行文件，不修改 Geant4 物理实现，也不执行数据清洗或论文分析。

| 脚本 | 职责 | 输入文件/schema | 输出目录/文件 | 主要参数 | 失败条件 | 示例命令 |
|---|---|---|---|---|---|---|
| `generate_source_response_experiment_configs.py` | 展开 source-response center/grid 单 pose 配置及 manifest | `article_base.yaml`、P0–P9 geometry、P001/P002 profile | `config/generated/<campaign>/`；结果路径为 `results/<campaign>/events/raw/` | `--campaign-id`、`--n-primary-per-pose`、`--threads`、`--base-seed`、`--grid-only`、`--grid-condition`、`--overwrite` | geometry/profile 缺失、参数非法、grid 条件非法/重复、目标非空且未允许覆盖 | `python -m scripts.monte_carlo.generate_source_response_experiment_configs` |
| `run_experiment_queue.py` | 串行执行 manifest，支持 dry-run、恢复、分片、范围和日志 | `source_response_simulation_campaign` manifest、`build/MSS` | raw event run、queue state/lock/log | `--dry-run`、`--state-file`、`--start-index`、`--end-index`、`--limit`、`--shard-*` | binary/manifest 缺失、live lock、输出不完整、large-run guard | `python -m scripts.monte_carlo.run_experiment_queue --manifest config/generated/articlev2/manifest.yaml --binary build/MSS --dry-run` |

常用命令：

```bash
python -m scripts.monte_carlo.generate_source_response_experiment_configs
python -m scripts.monte_carlo.run_experiment_queue \
  --manifest config/generated/articlev2/manifest.yaml \
  --binary build/MSS \
  --dry-run
```

article v1 的配置生成、batch merge、raw cleanup 和实验编号过滤接口已移除。

## V3 matched-grid 补充批次

`--grid-only` 只生成通过可重复参数 `--grid-condition PHANTOM:PROFILE` 显式选择的
P0–P6 grid 条件。每个条件仍展开为 81 份单 pose YAML；未使用这两个参数时，原
articlev2 的 341-task 默认设计保持不变。

已有 P001 grid 每点为 2000 万 primary。以下批次为 P0/P2/P4/P6 每点追加 8000 万，
使用 seed `10000–10323`：

```bash
python -m scripts.monte_carlo.generate_source_response_experiment_configs \
  --campaign-id articlev3_grid_p001_add80m \
  --grid-only \
  --grid-condition P0:P001 \
  --grid-condition P2:P001 \
  --grid-condition P4:P001 \
  --grid-condition P6:P001 \
  --n-primary-per-pose 80000000 \
  --threads 8 \
  --base-seed 10000
```

P002 当前没有 grid 数据。以下批次为 P0/P1/P3/P5 每点生成 1 亿 primary，使用 seed
`10324–10647`：

```bash
python -m scripts.monte_carlo.generate_source_response_experiment_configs \
  --campaign-id articlev3_grid_p002_100m \
  --grid-only \
  --grid-condition P0:P002 \
  --grid-condition P1:P002 \
  --grid-condition P3:P002 \
  --grid-condition P5:P002 \
  --n-primary-per-pose 100000000 \
  --threads 8 \
  --base-seed 10324
```

正式运行前分别对两个 manifest 使用 `--dry-run`。多 worker 部署时，每个 worker 使用
相同的 `shard_count` 和唯一的 `shard_index`，并使用独立的 state file。这里不传
`--log-dir`，因此不生成逐任务日志文件；MSS 输出仍直接显示在当前终端：

```bash
campaign_id=articlev3_grid_p001_add80m
shard_count=4
shard_index=0

python -m scripts.monte_carlo.run_experiment_queue \
  --manifest "config/generated/${campaign_id}/manifest.yaml" \
  --binary build/MSS \
  --shard-count "${shard_count}" \
  --shard-index "${shard_index}" \
  --state-file "results/queues/${campaign_id}/shard_${shard_index}_state.json" \
  --allow-large-run
```

P002 批次只需把 `campaign_id` 改为 `articlev3_grid_p002_100m`。中断恢复使用完全相同的
命令和同一个 state file，不使用 `--rerun-completed`。队列会重新读取 state，并以实际
`metadata.yaml`、`events.csv`、`run_id` 和 `n_primary` 的完整性检查作为最终完成判据；
完整任务会跳过，上次处于 `running` 的任务会恢复为 `pending`。恢复粒度是完整 pose，
不能从某个 pose 已发射的部分粒子数继续；若中断的 pose 留下了非空但不完整的 run 目录，
由于配置使用 `existing_run_policy: fail`，应先确认并移走该残留目录，再用原命令恢复。
当前 articlev2 audit 固定要求每 run 为 2000 万且不接收同一 grid cell 的多 seed；旧 P001
与新增 P001 的聚合属于后续 V3 数据处理，不对这两个补充 campaign 运行 V2 audit。
