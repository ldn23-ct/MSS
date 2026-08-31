# MSS 项目 v2 归档与交接导航

> 文档状态：项目级长期入口，记录稳定 Geant4 核心与当前 articlev2 数据链路。
> 职责：说明代码、数据、后处理、测试与归档文档的当前边界。
> 归档基线：`docs/archive/v2/`。
> 活跃实验链路：articlev2；article v1 仅保留历史文档。

## 1. 版本定位与阅读顺序

项目中的“版本”和实验名称必须分开理解。本文件只确认已经完成并归档的项目版本，不使用尚未正式启动的实验草案定义当前项目状态。

| 路径 | 定位 | 使用规则 |
|---|---|---|
| `docs/archive/v1/` | 第一轮历史资料 | 仅用于了解旧 PMMA、macro 和旧 CSV 实现，不作为当前代码依据。 |
| `docs/archive/v2/` | 项目 v2 正式归档基线 | 记录已完成 Geant4 核心及冻结 article v1 的规格、决策、架构、实施和验收。 |
| `docs/project_structure.md` | 跨版本导航与 v2 交接摘要 | 新任务和新接手人员的第一阅读入口。 |
| `docs/articlev2_analysis/` | Article V2 实验后处理规范 | 合并数据上的 E1/E2 与包含独立 slab 参考的严格 E3 均已完成。 |
| 根级其他预研文档及配套资产 | 预研或实验设计 | 是否进入正式主线由相应状态说明和 `articlev2_analysis/` 导航决定。 |

建议阅读顺序：

1. 先读本文件，确认任务属于 v2 维护还是未来新版本。
2. 维护 Geant4 核心时，依次阅读 `archive/v2/spec.md`、`decisions.md`、`architecture.md`。
3. 查询 article v1 历史时，阅读 `archive/v2/article_design.md` 和 `article_experiment_automation.md`；仓库不再提供其运行脚本。
4. 需要核对实现过程或验收范围时，再读 `milestones.md` 和 `acceptance_checklist.md`。
5. 未来新版本必须先建立新的正式需求和设计文档，不得直接把预研草案或 v1 历史规则写回 v2 核心。
6. 编写或查阅 Article V2 数据处理方法时，读取 `docs/articlev2_analysis/`。

## 2. 项目 v2 总结

### 2.1 目标与总体链路

项目 v2 建立了以下稳定的数据生成基础：

```text
入口 YAML
   │
   ├── VehicleROI-compatible geometry YAML
   ├── collimator profile CSV
   └── source spectrum CSV（可选）
   │
   ▼
MSS / Geant4
   │
   ├── 每个 pose 独立 run 和 seed
   ├── events.csv 或 events_debug.csv
   └── metadata.yaml
   │
   ▼
显式 Python Monte Carlo 自动化、基础数据处理与 E1/E2 后处理
```

Geant4 核心只负责事件级 Monte Carlo 数据。位姿级统计、扫描级统计、batch 合并、图表和报告不由 `MSS` 自动生成。

### 2.2 已完成的 Geant4 核心能力

- 使用 YAML 作为 batch 主入口，支持 `--config` 和兼容的位置参数形式。
- World 中固定 VehicleROI-compatible 几何，通过移动 source、collimator 和虚拟探测器组成的成像头实现扫描。
- Pose 支持 list/grid，遵守“一次 run = 一个 pose + 一个实际 seed + 一组模型条件 + n_primary”。
- 支持有限焦点斜入射 gamma、mono/spectrum 能量和每 event 一个 primary gamma。
- 使用外部 CSV 定义可变 jaw 数量的凸多边形狭缝准直器，不默认构建镜像准直器。
- 使用单个理想虚拟探测平面，不模拟真实探测器材料响应或能量沉积 scoring。
- 对每条 gamma track 独立记录 Compton/Rayleigh scatter history、first/last scatter 和 detector crossing。
- Formal 输出语义为 `1 row = 1 detected gamma hit`；debug 输出语义为 `1 row = 1 gamma track summary`。
- 支持多线程临时 CSV、master 合并、run-level metadata、输出目录保护和几何可视化。

### 2.3 Article v1 历史状态

Article v1 曾形成完整实验链路，但活跃脚本、专属队列逻辑和测试已在项目整改中移除。其设计与验收说明仅保存在 `docs/archive/v2/`，不再构成可执行接口。

- 不提供 `scripts/article/`、article v1 配置生成器或 batch merge。
- 不提供旧脚本路径兼容 wrapper。
- 历史文档中的命令只用于理解旧实现，不保证可运行。

### 2.4 v2 结果边界与后续扩展

- 真实探测器材料响应和能量沉积 scoring。
- Pose-level/scan-level summary 作为 Geant4 自动输出。
- 连续运动、运动模糊、成像头旋转或 z 向扫描。
- 图像重建、完整车辆 CAD 和论文指标自动闭环。
- 任何属于下一版本的新实验设计、配置矩阵或正式分析链路。

## 3. 仓库分层与职责

| 层次 | 路径 | 职责 |
|---|---|---|
| 构建与入口 | `CMakeLists.txt`, `main.cc` | 构建 `MSS`，读取配置并进入 batch 或可视化控制流程。 |
| Geant4 核心 | `include/`, `src/` | 配置、几何、source、tracking、输出和 run 生命周期。 |
| 手工维护配置 | `config/base/`, `config/geometry/`, `config/collimator/`, `config/source/` | 提供基础运行和实验输入。 |
| 生成配置 | `config/generated/` | 由实验生成器产生，不作为手工规格源，通常不提交。 |
| Monte Carlo 自动化 | `scripts/monte_carlo/` | Articlev2 配置生成、共享队列、恢复与分片。 |
| 基础数据处理 | `scripts/data_processing/` | 有效事件、slit 边界/标签和数据资格审计。 |
| 实验后处理 | `scripts/postprocessing/` | E1/E2/E3 正式实现、数据驱动 Report 生成器和旧 schema 源码快照。 |
| 测试 | `tests/` | 核心契约及三个活跃 Python 层的回归。 |
| 运行产物 | `results/` | raw/valid 事件、数据处理、队列状态、日志和 E1–E3 后处理输出，不属于源码。 |
| 文档 | `docs/` | 跨版本导航、历史归档和未启动预研草案。 |

## 4. 根级关键文件

| 文件 | 含义与功能 |
|---|---|
| `CMakeLists.txt` | 定义 `MSS` C++17 可执行文件、Geant4/yaml-cpp 依赖和 CTest 注册。CMake source 列表也是判断当前实际编译模块的直接依据。 |
| `main.cc` | 程序入口；解析 `--config`/位置参数和 `--ui`，读取配置与几何，并交给 batch pose controller 或 visualization controller。 |
| `README.md` | 面向使用者的构建、基础运行和项目导航入口。 |
| `AGENTS.md` | 面向 Codex 的修改规则、文档优先级和 v2 兼容约束。 |
| `.gitignore` | 排除 build、generated config、results、Python cache 和图表等生成产物。 |
| `.env.example` | 环境变量示例，不保存本地密钥或机器专属值。 |

## 5. C++ 模块导航

除单独注明外，下表中的模块由同名 `include/*.hh` 与 `src/*.cc` 组成。

### 5.1 配置、位姿与标识

| 模块 | 职责 |
|---|---|
| `SimulationConfig` | 保存 run、vehicle、pose、source、collimator、detector、physics、output 和 world 配置。 |
| `SimulationConfigReader` | 读取并验证入口 YAML，解析相对路径和必需字段。 |
| `SimulationMessenger` | 保留必要的 Geant4 UI/配置入口兼容能力，不是主配置系统。 |
| `VehicleROIConfig` | 定义 VehicleROI-compatible YAML 的 AABB、box component、material 和 region 数据结构。 |
| `VehicleROIConfigReader` | 读取并验证车辆或模体 geometry YAML。 |
| `ScanPoseManager` | 将 list/grid 原始配置展开为有序 pose，并生成 pose ID、offset 和实际 seed。 |
| `RunIdBuilder` | 根据 pose、collimator、model、energy 和 seed 生成可追踪 run ID。 |

### 5.2 几何与材料

| 模块 | 职责 |
|---|---|
| `DetectorConstruction` | 构建 World，协调 VehicleROI、成像头、region registry 和 World 边界检查。 |
| `VehicleROIConstruction` | 按 geometry YAML 构建车辆 ROI、PMMA/分层模体及可替换 target component。 |
| `ImagingHeadConstruction` | 将 source 参考位置、slit collimator 和 detector plane 作为同一成像头按 pose 平移。 |
| `SlitCollimatorProfileReader` | 读取并严格验证外部 profile CSV、jaw 编号和凸多边形顶点。 |
| `SlitCollimatorBuilder` | 使用 `G4ExtrudedSolid` 构建当前 profile 的 tungsten jaw。 |
| `VirtualDetectorPlane` | 保存零位姿和实际 detector bounds，并构建理想虚拟探测平面。 |
| `MaterialManager` | 解析 Geant4 内置材料和 geometry YAML 中使用的自定义材料。 |
| `RegionRegistry` | 建立 physical volume 到稳定 region ID 的注册关系。 |
| `RegionResolver` | 在 tracking 时从 volume 解析 region ID。 |

### 5.3 Source 与 physics

| 模块 | 职责 |
|---|---|
| `SpectrumSampler` | 读取 `energy_keV,weight` CSV，验证并构建能量采样 CDF。 |
| `SourceModel` | 计算当前 pose 的有限焦点 primary 位置、方向和能量。 |
| `PrimaryGeneratorAction` | 每个 event 产生一个 primary gamma。 |
| `PhysicsList` | 注册项目 v2 使用的 Geant4 EM physics 和 production cut。 |

### 5.4 事件追踪与输出

| 模块 | 职责 |
|---|---|
| `EventRecord.hh` | 定义 scatter summary、detector hit、gamma track summary 和 event record 数据结构。 |
| `EventAction` | 在 event 内维护 per-gamma-track 状态、hit 顺序，并在 event end 交给 writer。 |
| `SteppingAction` | 识别 `compt`/`Rayl`、记录 first/last scatter，并判断第一次有效 detector crossing。 |
| `CsvWriter` | 写 formal/debug CSV，管理 thread-local 文件和 master merge。 |
| `MetadataWriter` | 输出 run-level `metadata.yaml`，保存配置、geometry、pose、seed 和 provenance。 |
| `RunAction` | 管理单个 run 的输出目录、writer 生命周期、线程文件和 run-end merge。 |

### 5.5 执行与可视化

| 模块 | 职责 |
|---|---|
| `ActionInitialization` | 为 master/worker 注册 primary、run、event 和 stepping actions。 |
| `PoseRunController` | 按 pose 顺序创建并执行独立 Geant4 run。 |
| `VisualizationController` | 在 `--ui` 模式构建第一个 pose，执行 `macros/vis.mac`，且不写正式结果。 |

### 5.6 Legacy-isolated 文件

`include/CollimatorBuilder.hh`、`src/CollimatorBuilder.cc`、`include/CollimatorProfileReader.hh` 和 `src/CollimatorProfileReader.cc` 是早期隔离占位实现，未列入当前 CMake target。项目 v2 的正式路径是 `SlitCollimatorBuilder` 和 `SlitCollimatorProfileReader`，后续不得误用旧类。

## 6. 配置与数据文件导航

| 路径或文件 | 含义与功能 |
|---|---|
| `config/base/simulation_config_v2.yaml` | 车辆 ROI 核心的可运行入口样例，展示多 pose、source、collimator、detector 和输出配置。 |
| `config/base/article_base.yaml` | Articlev2 配置生成器使用的基础 YAML；具体物理条件由当前生成器覆盖。 |
| `config/geometry/vehicle_roi_v04.yaml` | 车辆侧向 ROI 几何、材料、region 和可替换 target component。 |
| `config/geometry/pmma_box.yaml` | 使用同一 VehicleROI-compatible schema 的均匀 PMMA control geometry。 |
| `config/geometry/phantom_yaml_files/` | Article v1 使用的 P0–P3/P5 PMMA 缺陷模体和 M0–M3 简化金属层模体。 |
| `config/collimator/collimator_profiles.csv` | 早期/对照准直器 profile 数据。 |
| `config/collimator/collimator_profiles1.csv` | `simulation_config_v2.yaml` 当前样例使用的车辆 ROI profile。 |
| `config/collimator/article_collimator_profiles.csv` | Article v1 三通道实验使用的 profile。 |
| `config/source/spectrum.csv` | Spectrum energy mode 的示例能谱。 |
| `config/generated/` | 生成器输出的 manifest 和逐 case YAML；可重新生成，不是正式规格。 |
| `results/` | 仿真事件、清洗/审计、队列和实验后处理产物；分层合同见 `results/README.md`。 |

Article V2 原始 campaign 的有效数据路径是
`results/articlev2/events/valid/**/events_valid.csv`。补充数据不改写该目录，而由
`scripts/data_processing/prepare_articlev3_merged.py` 汇入 `results/articlev3_merged/`：raw 层使用相对符号链接索引三个 campaign，valid 层保存清洗合并后的事件。E1/E2 与严格 E3 正式输出位于该合并层的 `postprocessing/`；E3 严格入口从 `results/articlev3_p4_front_slab_55mm_100m/` 独立读取 55 mm slab，并已发布固定六图四表。

工作区中可能存在为未来研究准备的额外 geometry、profile 或 generated config。除非未来正式文档明确纳入，它们不属于项目 v2 交付物。

## 7. Python 脚本导航

### 7.1 Monte Carlo 自动化

| 脚本 | 职责 |
|---|---|
| `scripts/monte_carlo/generate_source_response_experiment_configs.py` | 展开 articlev2 的 341 个单 pose 配置，输出路径固定到 `events/raw`。 |
| `scripts/monte_carlo/run_experiment_queue.py` | 按 manifest 串行执行 `MSS --config`，检测完成状态、保存 state/lock/log、支持范围和分片。 |

共享队列的最小 manifest 契约为：

```yaml
cases:
  - config_file: path/to/config.yaml
```

队列不再包含 article v1 batch merge、raw cleanup 或实验编号过滤特例。

### 7.2 基础数据处理

| 脚本 | 职责 |
|---|---|
| `scripts/data_processing/clean_events.py` | 过滤非法深度，删除九个 legacy 字段，追加 `slit_group/slit_label` 并原子发布 `events/valid`。 |
| `scripts/data_processing/estimate_slit_boundaries.py` | 使用 P0 center raw hits 校准边界，输出 JSON、CSV 和 PNG diagnostics。 |
| `scripts/data_processing/slit_channels.py` | 边界估计、稳定性、profile mapping 和固定标签分配。 |
| `scripts/data_processing/audit_experiment_data.py` | 审计 raw/valid 配对、行守恒、schema、标签、seed、条件和 boundary hash。 |

### 7.3 E1–E3 后处理

| 路径 | 职责 |
|---|---|
| `scripts/postprocessing/e1/run.py` | 生成 E1 三张正式 PNG；F3 按 P002/P001 acquisition groups 形成 2×2 overlay。 |
| `scripts/postprocessing/e1/analyze_roi_sensitivity.py` | E1 detector ROI sensitivity 辅助分析。 |
| `scripts/postprocessing/e2/run.py` | 默认生成 E2 四张 PNG、两张 CSV；支持多 case/class、函数级自定义 bin width 和显式 partial grid 预览。 |
| `scripts/postprocessing/e3/` | 后续 source-truth imaging utility 接口，尚未实现。 |
| `scripts/postprocessing/_archive/` | 不可执行、无回归支持的旧 schema 源码快照。 |

## 8. 测试与宏文件导航

| 文件 | 覆盖内容 |
|---|---|
| `tests/test_core_experiment_contract.py` | `abnormal_material`、自定义材料、run ID 和输出覆盖策略等共享 C++ 契约。 |
| `tests/test_monte_carlo_config_generation.py` | 341 个配置、路径、seed、覆盖和规模合同。 |
| `tests/test_monte_carlo_queue.py` | 队列执行、恢复、分片、范围、完成检测、lock 和 large-run guard。 |
| `tests/test_data_cleaning.py` | 有效深度过滤、字段删除、边界复用、标签、metadata 和 manifest。 |
| `tests/test_slit_channels.py` | 三峰/谷算法、稳定性、profile 标签、grid offset 和 diagnostics。 |
| `tests/test_data_audit.py` | raw/valid 配对、计数守恒、schema/标签和 boundary hash。 |
| `tests/test_e1_analysis.py` | E1 acquisition groups、ROI、quantile/manual view、计数、输出和覆盖保护。 |
| `tests/test_e2_analysis.py` | E2 case 解析、bin-wise response、region/DTV、动态输出、grid partial/strict 和原子覆盖。 |
| `tests/test_e1_roi_sensitivity.py` | E1 ROI sensitivity 指标、图表和原子输出。 |
| `macros/vis.mac` | 当前 `--ui` 可视化命令。 |
| `macros/run.mac`, `macros/run_mt.mac` | 第一轮 legacy macro 参考，不是 v2 batch 主入口。 |

未启动预研资产可能带有独立测试，但这些测试的存在不表示相应功能已经进入 v2 或下一版本正式范围。

## 9. V2 归档文档地图

| 文档 | 职责 | 归档状态 |
|---|---|---|
| `docs/archive/v2/change.md` | 解释 v1 到 v2 的车辆 ROI 重构背景。 | 历史背景基线 |
| `docs/archive/v2/spec.md` | 定义 v2 配置、几何、事件追踪、CSV 和 metadata 的最高优先级契约。 | 稳定规格基线 |
| `docs/archive/v2/decisions.md` | 固化 v2 已接受、取代或推迟的设计决策。 | 稳定决策基线 |
| `docs/archive/v2/architecture.md` | 描述 C++ 模块边界、数据流和 run/pose 生命周期。 | 稳定架构基线 |
| `docs/archive/v2/milestones.md` | 记录 v2 核心的实施顺序和已完成里程碑。 | 实施历史 |
| `docs/archive/v2/acceptance_checklist.md` | 记录构建、几何、事件输出、多线程和错误处理验收。 | 回归基线 |
| `docs/archive/v2/article_design.md` | Article v1 的 E0–E5 实验分类、条件和论文逻辑。 | 冻结实验设计 |
| `docs/archive/v2/article_experiment_automation.md` | Article v1 配置、队列、batch 合并和后处理操作说明。 | 冻结复现说明 |

V2 核心维护时的文档优先级为：

```text
docs/archive/v2/spec.md
  > docs/archive/v2/decisions.md
  > docs/archive/v2/architecture.md
  > docs/archive/v2/milestones.md
  > docs/archive/v2/acceptance_checklist.md
  > existing code
```

未来新版本的正式用户需求和新规格可以修改 v2 行为，但必须显式说明兼容性影响，不能静默把预研假设当作既有契约。

## 10. 稳定接口与交接边界

后续工作默认必须保护以下 v2 接口：

- Formal/debug CSV header、字段单位和事件行语义。
- `metadata.yaml` 的 run-level provenance。
- 一个 run 与 pose、实际 seed、model condition、n_primary 的对应关系。
- Pose ID、run ID 和输出目录的可复现性。
- `cases[].config_file` manifest 基础契约。
- VehicleROI-compatible geometry YAML、collimator CSV 和 spectrum CSV 的输入边界。
- Geant4 核心只输出事件级数据，统计与绘图属于显式 Python 层。

工作区中出现设计稿、配置草案、生成器或测试，只能证明存在预研资产，不能证明下一版本已经立项或完成。启动下一版本前，应先创建新的正式需求、设计、自动化和验收文档，并在本导航中登记其状态。
