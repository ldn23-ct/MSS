# Monte Carlo 自动化脚本

本目录只负责生成 Geant4 输入配置和调度现有 `MSS` 可执行文件，不修改 Geant4 物理实现，也不执行数据清洗或论文分析。

| 脚本 | 职责 | 输入文件/schema | 输出目录/文件 | 主要参数 | 失败条件 | 示例命令 |
|---|---|---|---|---|---|---|
| `generate_source_response_experiment_configs.py` | 展开 source-response center/grid 单 pose 配置及 manifest | `article_base.yaml`、P0–P9 geometry、P001/P002 profile | `config/generated/<campaign>/`；结果路径为 `results/<campaign>/events/raw/` | `--campaign-id`、`--n-primary-per-pose`、`--threads`、`--base-seed`、`--grid-only`、`--grid-condition`、`--overwrite` | geometry/profile 缺失、参数非法、grid 条件非法/重复、目标非空且未允许覆盖 | `python3 -m scripts.monte_carlo.generate_source_response_experiment_configs` |
| `generate_front_slab_reference_configs.py` | 展开 P4 55 mm 均匀 PMMA 前层参考的 81 个单 pose 配置 | `article_base.yaml`、`P4_front_slab_55mm.yaml`、P001 profile | `config/generated/articlev3_p4_front_slab_55mm_100m/` 与独立 raw campaign | `--campaign-id`、`--n-primary-per-pose`、`--threads`、`--base-seed`、`--overwrite` | slab geometry、profile、参数或覆盖策略非法 | `python3 -m scripts.monte_carlo.generate_front_slab_reference_configs` |
| `run_experiment_queue.py` | 串行执行 manifest，支持 dry-run、恢复、分片、范围和日志 | `source_response_simulation_campaign` manifest、`build/MSS` | raw event run、queue state/lock/log | `--dry-run`、`--state-file`、`--start-index`、`--end-index`、`--limit`、`--shard-*` | binary/manifest 缺失、live lock、输出不完整、large-run guard | `python3 -m scripts.monte_carlo.run_experiment_queue --manifest config/generated/articlev2/manifest.yaml --binary build/MSS --dry-run` |

常用命令：

```bash
python3 -m scripts.monte_carlo.generate_source_response_experiment_configs
python3 -m scripts.monte_carlo.run_experiment_queue \
  --manifest config/generated/articlev2/manifest.yaml \
  --binary build/MSS \
  --dry-run
```

article v1 的配置生成、batch merge、raw cleanup 和实验编号过滤接口已移除。

P4 55 mm slab 参考批次的远端 8 worker × 6 threads 正式运行手册见
[`docs/articlev2_analysis/E3_slab_remote_run.md`](../../docs/articlev2_analysis/E3_slab_remote_run.md)。该批次只生成 raw 数据，不改写主 `articlev3_merged` 数据层。

## 命令中的变量与参数

命令中存在两类容易混淆的值：Bash 变量和 Python 脚本参数。

### Bash 变量（语法说明；本次正式命令不使用）

下面是 Bash 变量语法示例。变量由操作者在当前终端定义，不来自 YAML、manifest 或
Python；为避免部署时需要替换，本次正式运行命令已经全部展开，不使用这些变量：

```bash
campaign_id=articlev3_grid_p001_add80m
shard_count=2
shard_index=0
```

赋值语句的等号两侧不能有空格。这些变量只存在于当前 shell；新开一个终端后需要重新
定义。命令中的 `${campaign_id}`、`${shard_count}` 和 `${shard_index}` 会在命令启动前由
Bash 替换成对应值，因此不需要 `export`。

| Bash 变量 | 本例值 | 含义 |
|---|---:|---|
| `campaign_id` | `articlev3_grid_p001_add80m` | 已生成 campaign 的目录名。它用于拼出 manifest、state file 等路径；不会在运行阶段重新生成或修改 campaign。P002 批次改为 `articlev3_grid_p002_100m`。 |
| `shard_count` | `2` | 将当前 campaign 的 manifest 分成两片。它不是单个 MSS 进程的 Geant4 线程数。 |
| `shard_index` | `0` | 当前 worker 负责哪一片，从 `0` 开始；两个 worker 分别使用 0 和 1。 |

例如，`${campaign_id}` 展开后：

```text
config/generated/${campaign_id}/manifest.yaml
```

实际变成：

```text
config/generated/articlev3_grid_p001_add80m/manifest.yaml
```

也可以完全不用 Bash 变量，直接把值写进命令；变量只是为了减少重复和输错路径的概率。

命令中的其他 shell 语法含义如下：

- 行末 `\` 表示命令尚未结束，下一行仍属于同一条命令；反斜杠后不要再添加空格。
- 双引号保留路径为一个完整参数，并允许 `${...}` 变量展开。
- `python3 -m scripts.monte_carlo.run_experiment_queue` 表示按 Python module 方式运行仓库中的
  `scripts/monte_carlo/run_experiment_queue.py`，命令应从仓库根目录执行。
- `--name value` 是一个带值的 CLI 参数；`--dry-run`、`--allow-large-run` 等是不带值的开关。

### 配置生成器参数

以下参数属于 `generate_source_response_experiment_configs.py`，作用是生成 manifest 和每个
pose 的 YAML，不会启动 Geant4：

| 参数 | 是否必需/默认值 | 含义 |
|---|---|---|
| `--repo-root PATH` | 默认仓库根目录 | 用于解析输入文件及生成仓库相对路径。通常不需要显式设置。 |
| `--base-config PATH` | 默认 `config/base/article_base.yaml` | 基础 MSS YAML 模板。生成器在其副本中写入 geometry、profile、pose、seed、primary 数等批次参数。 |
| `--geometry-dir PATH` | 默认 `config/geometry/article_files` | P0–P9 geometry YAML 所在目录。 |
| `--profile-file PATH` | 默认 `config/collimator/article_v2_collimator_profiles.csv` | 包含 P001/P002 的准直器定义文件。 |
| `--campaign-id ID` | 默认 `articlev2` | 批次唯一名称，同时决定默认配置目录 `config/generated/<ID>/` 和结果目录 `results/<ID>/`。补充数据必须使用新 ID，以免与已有结果混在一起。 |
| `--output-dir PATH` | 默认 `config/generated/<campaign-id>` | 生成的 manifest 和逐 pose YAML 保存位置。只改变此参数不会改变 YAML 内部的结果 campaign 路径。 |
| `--energy-kev VALUE` | 默认 `560` | 单能 gamma 能量，单位 keV。 |
| `--n-primary-per-pose N` | 默认 `20000000` | 每一份 pose YAML 发射的 primary 粒子数。本次 P001 补充批次为 8000 万，P002 批次为 1 亿。 |
| `--threads N` | 默认 `8` | 每次启动的一个 MSS/Geant4 进程内部使用的线程数。若同时运行 W 个 worker，理论上最多占用约 `W × N` 个计算线程。 |
| `--base-seed N` | 默认 `1234` | 第一份配置的 seed；后续逐 pose 配置按生成顺序递增 1。不同 campaign 的 seed 区间也应避免重叠。 |
| `--grid-only` | 默认关闭 | 只生成显式指定的 grid 条件，不生成 center 和 E7 条件。 |
| `--grid-condition PHANTOM:PROFILE` | grid-only 时至少一个 | 指定一个 grid 条件，可重复使用。只接受 P0–P6 与 P001/P002，例如 `P1:P002`；相同条件不能重复。 |
| `--overwrite` | 默认关闭 | 原子替换非空的 generated 配置目录。不会覆盖 `results/`；使用前应确认目标目录。 |

### 队列脚本参数

以下参数属于 `run_experiment_queue.py`。脚本读取现有 manifest，选择任务并逐个调用
`build/MSS --config <pose-yaml>`：

| 参数 | 是否必需/默认值 | 含义 |
|---|---|---|
| `--manifest PATH` | 必需 | 配置生成器产生的任务清单。队列按其中的 case 顺序读取逐 pose YAML。 |
| `--binary PATH` | 默认 `build/MSS` | 要执行的 MSS 可执行文件。 |
| `--repo-root PATH` | 默认仓库根目录 | MSS 的运行工作目录，以及相对配置/结果路径的解析基准。通常无需设置。 |
| `--state-file PATH` | 保存/恢复时必需 | 队列状态 JSON。传入后会自动启用 `--save-queue`；每个 campaign、每个 shard 必须使用不同文件。恢复时必须复用原文件。 |
| `--save-queue` | 默认关闭 | 开启状态保存。单独使用时仍必须提供 `--state-file`，所以通常只写 `--state-file` 即可。 |
| `--log-dir PATH` | 默认不启用 | 将每个 pose 的 stdout/stderr 写入独立日志。当前补充仿真不需要，因此命令中不传；输出直接显示在终端。若传入该参数，也必须提供 `--state-file`。 |
| `--dry-run` | 默认关闭 | 读取并检查任务，只打印 `run`/`skip-complete`，不启动 MSS，也不创建 state file。正式运行前建议执行。 |
| `--allow-large-run` | 默认关闭 | 显式确认允许运行超过 manifest 安全阈值的任务数。本项目 manifest 阈值为 0，正式队列必须传入；它不改变粒子数。 |
| `--shard-count N` | 默认 `1` | 将筛选后的任务分成 N 片。一个 worker 只串行执行自己的一片，不会在进程内部并行启动多个 MSS。 |
| `--shard-index I` | 默认 `0` | 当前 worker 的分片编号，范围为 `0..N-1`。不同 worker 不得使用相同编号。 |
| `--start-index N` | 默认无限制 | 只选择 manifest index 大于等于 N 的任务。 |
| `--end-index N` | 默认无限制 | 只选择 manifest index 小于 N 的任务，即结束值不包含在内。 |
| `--limit N` | 默认无限制 | 完成区间和分片筛选后，最多取前 N 个任务，适合小规模试运行。 |
| `--continue-on-failure` | 默认关闭 | 某个 pose 失败后继续后续任务；默认行为是在首次失败时停止，以便先检查问题。 |
| `--rerun-completed` | 默认关闭 | 强制重新调度已经完整的任务。本批次不应使用，因为输出策略为 `fail`，且正常恢复应跳过完整结果。 |
| `--force-unlock` | 默认关闭 | 强制删除对应 state file 的锁。只有确认没有另一个队列进程正在使用该 state file 时才能使用。 |

任务筛选顺序为：先应用 `[start-index, end-index)`，再按 shard 分配，最后应用 `limit`。

### worker、线程和 pose 的关系

一个 worker 就是一个 `run_experiment_queue.py` 进程，通常对应一个终端。每个 worker 在
自己的分片内逐个执行 pose；一个 pose 完成后才启动下一个。真正的计算并行度来自两个层次：

- worker 数：同时运行多少个独立 MSS 进程；
- `--threads`：生成 YAML 时写入的每个 MSS 进程内部线程数。

本次生成的每个 MSS 配置固定使用 4 个线程，而可用线程总数为 16，因此同时运行 4 个
worker：`4 workers × 4 threads = 16 threads`。P001 和 P002 各拆为两个 shard，每个
worker 负责 162 个任务。四个 campaign shard 从一开始同时运行，不需要等待或后续切换。
由于两个 campaign 的 manifest 不同，并且四个 worker 使用不同 state file，它们不会选择
或写入彼此的任务。

## V3 matched-grid 补充批次

`--grid-only` 只生成通过可重复参数 `--grid-condition PHANTOM:PROFILE` 显式选择的
P0–P6 grid 条件。每个条件仍展开为 81 份单 pose YAML；未使用这两个参数时，原
articlev2 的 341-task 默认设计保持不变。

已有 P001 grid 每点为 2000 万 primary。以下批次为 P0/P2/P4/P6 每点追加 8000 万，
使用 seed `10000–10323`：

```bash
python3 -m scripts.monte_carlo.generate_source_response_experiment_configs \
  --campaign-id articlev3_grid_p001_add80m \
  --grid-only \
  --grid-condition P0:P001 \
  --grid-condition P2:P001 \
  --grid-condition P4:P001 \
  --grid-condition P6:P001 \
  --n-primary-per-pose 80000000 \
  --threads 4 \
  --base-seed 10000
```

P002 当前没有 grid 数据。以下批次为 P0/P1/P3/P5 每点生成 1 亿 primary，使用 seed
`10324–10647`：

```bash
python3 -m scripts.monte_carlo.generate_source_response_experiment_configs \
  --campaign-id articlev3_grid_p002_100m \
  --grid-only \
  --grid-condition P0:P002 \
  --grid-condition P1:P002 \
  --grid-condition P3:P002 \
  --grid-condition P5:P002 \
  --n-primary-per-pose 100000000 \
  --threads 4 \
  --base-seed 10324
```

正式运行前分别复制执行下面两条 dry-run 命令：

```bash
python3 -m scripts.monte_carlo.run_experiment_queue \
  --manifest config/generated/articlev3_grid_p001_add80m/manifest.yaml \
  --binary build/MSS \
  --dry-run
```

```bash
python3 -m scripts.monte_carlo.run_experiment_queue \
  --manifest config/generated/articlev3_grid_p002_100m/manifest.yaml \
  --binary build/MSS \
  --dry-run
```

两条命令都应打印 324 个任务。dry-run 不需要 state file，也不需要
`--allow-large-run`。

### P001 与 P002 同时正式运行

打开四个终端，同时分别复制下面四条命令。每个 worker 启动的 MSS 内部使用 4 个线程，
因此同时运行合计使用 16 个线程。命令不使用 Bash 变量。每个 campaign 使用两个 shard，
并为每个 shard 保存独立 state file。这里不传 `--log-dir`，因此只保存队列 state，MSS
输出显示在各自终端。

终端 1：P001 shard 0（162 个任务）：

```bash
python3 -m scripts.monte_carlo.run_experiment_queue \
  --manifest config/generated/articlev3_grid_p001_add80m/manifest.yaml \
  --binary build/MSS \
  --shard-count 2 \
  --shard-index 0 \
  --state-file results/queues/articlev3_grid_p001_add80m/shard_0_state.json \
  --allow-large-run
```

终端 2：P001 shard 1（162 个任务）：

```bash
python3 -m scripts.monte_carlo.run_experiment_queue \
  --manifest config/generated/articlev3_grid_p001_add80m/manifest.yaml \
  --binary build/MSS \
  --shard-count 2 \
  --shard-index 1 \
  --state-file results/queues/articlev3_grid_p001_add80m/shard_1_state.json \
  --allow-large-run
```

终端 3：P002 shard 0（162 个任务）：

```bash
python3 -m scripts.monte_carlo.run_experiment_queue \
  --manifest config/generated/articlev3_grid_p002_100m/manifest.yaml \
  --binary build/MSS \
  --shard-count 2 \
  --shard-index 0 \
  --state-file results/queues/articlev3_grid_p002_100m/shard_0_state.json \
  --allow-large-run
```

终端 4：P002 shard 1（162 个任务）：

```bash
python3 -m scripts.monte_carlo.run_experiment_queue \
  --manifest config/generated/articlev3_grid_p002_100m/manifest.yaml \
  --binary build/MSS \
  --shard-count 2 \
  --shard-index 1 \
  --state-file results/queues/articlev3_grid_p002_100m/shard_1_state.json \
  --allow-large-run
```

### 中断恢复

哪个 worker/shard 中断，就原样再次复制该 worker 对应的完整命令。不要修改参数，也不要添加
`--rerun-completed`。队列会重新读取同一个 state file，并以实际 `metadata.yaml`、
`events.csv`、`run_id` 和 `n_primary` 的完整性检查作为最终完成判据；完整任务会跳过，
上次处于 `running` 的任务会恢复为 `pending`。恢复粒度是完整 pose，不能从某个 pose 已
发射的部分粒子数继续；若中断的 pose 留下了非空但不完整的 run 目录，由于配置使用
`existing_run_policy: fail`，应先确认并移走该残留目录，再用原命令恢复。

当前 articlev2 audit 固定要求每 run 为 2000 万且不接收同一 grid cell 的多 seed；旧 P001
与新增 P001 的聚合属于后续 V3 数据处理，不对这两个补充 campaign 运行 V2 audit。

恢复某个 worker 时，下列项目必须与首次运行一致：

| 项目 | 原因 |
|---|---|
| `campaign_id` / `--manifest` | 必须继续读取同一批任务及同一组逐 pose YAML。 |
| `--shard-count` / `--shard-index` | 必须继续读取原 worker 负责的同一片任务。 |
| `--state-file` | 必须读取该 shard 已记录的状态、尝试次数和预期输出路径。 |
