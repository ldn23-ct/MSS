# MSS 里程碑实施计划

## 1. 文档目的

本文档定义 `MSS` 第一版 Geant4 项目的分阶段实现计划。

本文档不是科研时间表，也不是论文写作计划。它只约束第一版代码实现顺序、每阶段交付物和验收点。

使用优先级：

1. `docs/spec.md`：需求、物理参数、宏命令、CSV 字段和验收标准。
2. `docs/architecture.md`：模块边界、数据流和生命周期。
3. `docs/decisions.md`：已接受设计决策。
4. `docs/milestones.md`：分阶段实现顺序。

---

## 2. 与 Codex 配合方式

每次只实现一个里程碑。

建议流程：

1. 让 Codex 读取 `docs/spec.md`、`docs/architecture.md`、`docs/decisions.md`、`docs/milestones.md`。
2. 明确指定要实现的里程碑编号。
3. 明确要求不要实现后续里程碑。
4. 检查 Codex 修改过的文件。
5. 运行该里程碑对应检查。
6. 通过后再进入下一里程碑。

推荐 prompt 模板：

```text
Read docs/spec.md, docs/architecture.md, docs/decisions.md, and docs/milestones.md.
Implement Milestone N only.
Do not implement Milestone N+1 or later.
After implementation, summarize:
- changed files
- what was implemented
- how to test it
- what was intentionally left for later
```

---

## 3. 全局规则

### 3.1 Codex 必须遵守

- 以 `spec.md` 为最高依据。
- 以 `architecture.md` 保持模块边界。
- 以 `decisions.md` 保持已接受设计不漂移。
- 每次只实现指定里程碑。
- 保持代码简单、明确、可测试。
- 优先清晰报错，不做静默 fallback。
- 保持 `spec.md` 中的 CSV schema。
- 保持 `spec.md` 中的宏命令名称。
- 保持 `spec.md` 中的坐标系。
- 保持第一版范围。
- 每阶段结束后总结改动文件、测试方式和暂缓内容。

### 3.2 Codex 禁止行为

- 不得实现未请求的后续里程碑。
- 不得增加图像重建。
- 不得增加真实探测器材料响应。
- 不得增加探测器能量沉积 scoring。
- 不得自动扫描所有 collimator profile。
- 不得输出完整散射轨迹。
- 不得增加源位置宏命令。
- 不得增加探测器边界宏命令。
- 不得改变 CSV 字段，除非 `spec.md` 更新。
- 不得替换多线程输出策略。
- 不得让多个 worker 线程共享同一个 `std::ofstream`。
- 不得静默忽略非法 profile、spectrum、geometry 或 output 配置。
- 不得使用旧项目名 `BackscatterSim` 作为 project 名、target 名或可执行文件名。

---

## 4. 里程碑总览

| 里程碑 | 名称 | 主要交付物 |
|---:|---|---|
| M0 | 仓库骨架 | 可配置、可编译的最小 Geant4 项目结构 |
| M1 | 运行配置与宏命令 | 中央配置对象与 UI command 层 |
| M2 | 准直器 profile 读取器 | CSV reader 与 validator |
| M3 | 基础几何 | World、PMMA、空气缺陷、探测面辅助体 |
| M4 | 准直器几何 | 由 profile 构建两块钨五边形 jaw |
| M5 | primary generator 与 spectrum sampler | mono/spectrum gamma 源与锥束目标面采样 |
| M6 | event 状态模型 | 单 event 的散射与探测记录结构 |
| M7 | stepping 逻辑 | PMMA 散射计数与探测面穿越判断 |
| M8 | 单线程 CSV 输出 | debug/compact CSV 写出 |
| M9 | 多线程输出合并 | worker 临时 CSV + master 合并 |
| M10 | 宏文件、README 与验收 | 可运行宏、示例数据、README、验收清单 |

---

# M0：仓库骨架

## 目标

创建最小可编译的 Geant4 项目骨架。该阶段只建立目录、CMake、入口文件和占位类，不实现真实仿真行为。

## 创建或修改文件

创建：

- `CMakeLists.txt`
- `main.cc`
- `include/DetectorConstruction.hh`
- `src/DetectorConstruction.cc`
- `include/PhysicsList.hh`
- `src/PhysicsList.cc`
- `include/PrimaryGeneratorAction.hh`
- `src/PrimaryGeneratorAction.cc`
- `include/RunAction.hh`
- `src/RunAction.cc`
- `include/EventAction.hh`
- `src/EventAction.cc`
- `include/SteppingAction.hh`
- `src/SteppingAction.cc`
- `include/CollimatorProfileReader.hh`
- `src/CollimatorProfileReader.cc`
- `include/CollimatorBuilder.hh`
- `src/CollimatorBuilder.cc`
- `include/SpectrumSampler.hh`
- `src/SpectrumSampler.cc`
- `include/CsvWriter.hh`
- `src/CsvWriter.cc`
- `macros/.gitkeep`
- `data/.gitkeep`
- `results/.gitkeep`

可选：

- `include/ActionInitialization.hh`
- `src/ActionInitialization.cc`

## 任务

### M0.1 创建项目结构

目标结构：

```text
MSS/
├── CMakeLists.txt
├── main.cc
├── include/
├── src/
├── macros/
├── data/
└── results/
```

### M0.2 配置 CMake

要求：

- `project(MSS)`；
- C++17；
- 查找 Geant4；
- executable target 为 `MSS`；
- include 目录为 `include/`；
- source 文件来自 `src/`。

### M0.3 实现最小入口

`main.cc` 应：

- 使用 `G4RunManagerFactory::CreateRunManager(G4RunManagerType::Default)`；
- 注册占位 `DetectorConstruction`；
- 注册占位 `PhysicsList`；
- 注册占位 user actions 或 `ActionInitialization`；
- 支持从命令行参数执行宏文件；
- 无宏文件时可进入交互模式。

### M0.4 添加占位类

所有核心类应能编译。占位类只需最小行为。

## 完成标准

- `cmake ..` 成功。
- `make -j` 成功。
- 生成可执行文件 `MSS`。
- 无宏文件运行时不立即崩溃。
- 未实现真实几何、源、探测、CSV、profile 解析或 spectrum 采样。

## 不做

- 不实现 PMMA 几何。
- 不实现准直器。
- 不实现宏命令处理。
- 不实现 CSV 输出。
- 不实现散射追踪。
- 不实现 spectrum 采样。
- 不增加分析脚本。

## 推荐 Codex prompt

```text
Read docs/spec.md, docs/architecture.md, docs/decisions.md, and docs/milestones.md.
Implement Milestone 0 only: repository skeleton.
Create a minimal buildable Geant4 project named MSS with CMakeLists.txt, main.cc, and placeholder classes.
Do not implement geometry details, macro commands, CSV output, source sampling, scatter tracking, or multi-thread output.
After implementation, summarize changed files and exact build commands.
```

---

# M1：运行配置与宏命令

## 目标

创建中央运行配置层和宏命令接口。该阶段只接收、保存和基本验证配置，不使用配置构建完整几何或写出数据。

## 创建或修改文件

创建：

- `include/SimulationConfig.hh`
- `src/SimulationConfig.cc`
- `include/SimulationMessenger.hh`
- `src/SimulationMessenger.cc`

修改：

- `CMakeLists.txt`
- `main.cc`
- `include/DetectorConstruction.hh`
- `src/DetectorConstruction.cc`
- `include/PrimaryGeneratorAction.hh`
- `src/PrimaryGeneratorAction.cc`
- `include/RunAction.hh`
- `src/RunAction.cc`

## 任务

### M1.1 定义 `SimulationConfig`

建议结构：

```cpp
struct SimulationConfig {
    std::string collimatorProfileFile = "data/collimator_profiles.csv";
    std::string collimatorProfileId = "P001";
    bool enableAirDefect = true;

    std::string energyMode = "mono";
    double monoEnergy_keV = 160.0;
    std::string spectrumFile = "data/spectrum.csv";

    long randomSeed = 12345;
    int numberOfThreads = 1;

    std::string outputDirectory = "results";
    std::optional<bool> debugOutputOverride = std::nullopt;
};
```

说明：`debugOutputOverride` 用于区分 `/output/debug` 未设置和显式设置。最终模式在 `RunAction` 中根据线程数解析。

### M1.2 实现宏命令

必须支持：

```text
/geometry/collimatorProfileFile data/collimator_profiles.csv
/geometry/collimatorProfileId P001
/geometry/enableAirDefect true

/source/energyMode mono
/source/monoEnergy 160 keV
/source/spectrumFile data/spectrum.csv

/run/randomSeed 12345
/run/numberOfThreads 8

/output/directory results
/output/debug false
```

### M1.3 基本验证

报错条件：

- `energyMode` 不是 `mono` 或 `spectrum`；
- `monoEnergy` 非正；
- `numberOfThreads < 1`；
- `outputDirectory` 为空；
- `collimatorProfileId` 为空；
- `collimatorProfileFile` 为空；
- spectrum 模式下 `spectrumFile` 为空。

### M1.4 将 config 传给核心类

至少传给：

- `DetectorConstruction`
- `PrimaryGeneratorAction`
- `RunAction`

所有权应明确，避免悬空引用。

### M1.5 设置线程数

`/run/numberOfThreads` 应能配置 Geant4 多线程运行的线程数。不得写死单线程。

## 完成标准

- 所有宏命令存在。
- 宏命令能更新中央配置。
- 简单非法值能清晰报错。
- 项目仍能编译。
- 未引入完整仿真行为。

## 不做

- 不构建完整几何。
- 不读取准直器 profile CSV。
- 不读取 spectrum CSV。
- 不写 CSV。
- 不实现 scatter tracking。

## 推荐 Codex prompt

```text
Read docs/spec.md, docs/architecture.md, docs/decisions.md, and docs/milestones.md.
Implement Milestone 1 only: runtime configuration and macro commands.
Create SimulationConfig and SimulationMessenger for all required first-version macro commands.
Use an optional debug override so single-thread default debug and multi-thread default compact remain possible.
Do not implement geometry, profile reading, spectrum reading, CSV output, scatter tracking, or file merging.
After implementation, summarize changed files and how to test macro parsing.
```

---

# M2：准直器 profile 读取器

## 目标

实现外部准直器 profile CSV 的独立读取与验证。该阶段只返回结构化数据，不构建 Geant4 solid。

## 修改文件

- `include/CollimatorProfileReader.hh`
- `src/CollimatorProfileReader.cc`
- `CMakeLists.txt` 如有需要

可选：

- `data/collimator_profiles.csv`
- 手工测试用非法 CSV 样例

## 任务

### M2.1 定义数据结构

```cpp
struct XZPoint {
    double x_mm;
    double z_mm;
};

struct PentagonJawProfile {
    std::string jaw_id;
    std::array<XZPoint, 5> vertices;
};

struct CollimatorProfile {
    std::string profile_id;
    PentagonJawProfile jaw0;
    PentagonJawProfile jaw1;
};
```

### M2.2 解析 CSV

读取列：

```text
profile_id,jaw_id,vertex_id,x_mm,z_mm
```

只处理匹配目标 `profile_id` 的行。

### M2.3 验证 profile 存在与列合法

报错条件：

- 文件无法打开；
- 指定 `profile_id` 不存在；
- 必要列缺失；
- 必要字段为空。

### M2.4 验证 jaw 与 vertex

报错条件：

- 不是恰好两块 jaw；
- jaw ID 不是 `jaw_0` 和 `jaw_1`；
- 某 jaw 不是五个顶点；
- `vertex_id` 缺失；
- `vertex_id` 重复；
- `vertex_id` 超出 `0..4`。

### M2.5 验证数值

报错条件：

- `x_mm` 或 `z_mm` 非数值；
- NaN；
- Inf。

### M2.6 验证多边形

对每个 jaw：

- 计算有符号面积；
- 拒绝零面积；
- 验证凸性；
- 拒绝非凸五边形。

不需要检查 z 坐标是否落在 `[-28, -20] mm`。

## 完成标准

- 合法 `P001` 可读取。
- 错误 profile ID 有清晰错误。
- 缺失/重复 vertex ID 有清晰错误。
- 非有限坐标有清晰错误。
- 零面积和非凸五边形有清晰错误。
- 不构建 Geant4 geometry。

## 不做

- 不创建 `G4ExtrudedSolid`。
- 不创建钨 logical volume。
- 不自动批量扫描 profile。
- 不修改 CSV 格式。
- 不静默修复非法 profile。

## 推荐 Codex prompt

```text
Read docs/spec.md, docs/architecture.md, docs/decisions.md, and docs/milestones.md.
Implement Milestone 2 only: collimator profile reader.
Implement CollimatorProfileReader as a standalone CSV reader and validator for one selected profile_id.
Validate jaw count, jaw IDs, vertex IDs, finite coordinates, polygon area, and convexity.
Do not construct Geant4 solids, tungsten volumes, or profile batch scanning.
After implementation, summarize changed files and manual valid/invalid test cases.
```

---

# M3：基础几何

## 目标

构建除钨准直器外的基础 Geant4 几何：World、PMMA、可选空气缺陷、探测面辅助体和探测器边界配置。

## 修改文件

- `include/DetectorConstruction.hh`
- `src/DetectorConstruction.cc`
- `include/SimulationData.hh` 或 `include/SimulationConfig.hh` 如需要

## 任务

### M3.1 World

- 立方体；
- `1000 mm × 1000 mm × 1000 mm`；
- 中心 `(0, 0, 0)`；
- 材料 `G4_Galactic`。

### M3.2 PMMA 模体

- 材料 `G4_PLEXIGLASS`；
- box；
- 尺寸 `200 mm × 200 mm × 65 mm`；
- 中心 `(0, 0, 32.5 mm)`；
- z 范围 `[0, 65] mm`。

### M3.3 空气缺陷

当 `enableAirDefect == true`：

- 材料 `G4_AIR`；
- cylinder；
- 半径 `5 mm`；
- 全长 `10 mm`；
- 轴向 z；
- 全局中心 `(0, 0, 55 mm)`；
- z 范围 `[50, 60] mm`；
- 作为 PMMA daughter volume 放置，不使用布尔减法。

### M3.4 探测器边界配置

定义或暴露：

```cpp
struct DetectorPlaneConfig {
    double z_mm = -73.0;
    double x_min_mm = 53.0;
    double x_max_mm = 161.0;
    double y_min_mm = -50.0;
    double y_max_mm = 50.0;
};
```

### M3.5 探测面辅助体

在 `z = -73 mm` 添加可视化辅助体，范围为：

```text
x = [53, 161] mm
y = [-50, 50] mm
```

该辅助体不作为真实探测器响应，不应设置为 sensitive detector。

### M3.6 可视化属性

- World 可不可见。
- PMMA 可见或半透明。
- 空气缺陷启用时可见。
- 探测面辅助体可见。

## 完成标准

- 可视化中能看到 PMMA、空气缺陷和探测面辅助体。
- 空气缺陷开关有效。
- 探测面位置与范围正确。
- 未构建钨准直器。

## 不做

- 不构建 collimator jaws。
- 不实现源产生。
- 不实现 stepping logic。
- 不写 CSV。
- 不添加探测器材料响应。

## 推荐 Codex prompt

```text
Read docs/spec.md, docs/architecture.md, docs/decisions.md, and docs/milestones.md.
Implement Milestone 3 only: basic geometry construction.
Build World, PMMA, optional air defect, detector plane config, and a visualization helper plane.
Do not build tungsten collimator, source generation, stepping logic, detector response, or CSV output.
After implementation, summarize changed files and visual checks.
```

---

# M4：准直器几何

## 目标

把 M2 的 profile reader 与 M3 的 DetectorConstruction 连接起来，使用 `G4ExtrudedSolid` 构建两块钨准直器 jaw。

## 修改文件

- `include/CollimatorBuilder.hh`
- `src/CollimatorBuilder.cc`
- `include/DetectorConstruction.hh`
- `src/DetectorConstruction.cc`
- 必要时小幅调整 `CollimatorProfileReader`

## 任务

### M4.1 定义 `CollimatorBuilder` 接口

接口应接受：

- 已验证 `CollimatorProfile`；
- parent/world logical volume；
- tungsten material 或 NIST manager。

### M4.2 使用 `G4ExtrudedSolid`

每块 jaw 使用 `G4ExtrudedSolid`。

输入 profile 点是全局 `(x_mm, z_mm)`。

映射：

| 输入 | local 坐标 |
|---|---|
| global x | local x |
| global z | local y |

### M4.3 旋转到全局 y 拉伸

local z 是 extrusion 方向，应旋转到 global y。

目标映射：

```text
local x -> global x
local y -> global z
local z -> global -y
```

绕 x 轴 `+90 deg` 可接受。由于 jaw 沿 y 对称，映射到 global +y 或 -y 的几何覆盖等价。

### M4.4 y 向长度

- 全长 `120 mm`；
- global y 范围 `[-60, 60] mm`。

### M4.5 材料

使用：

```cpp
G4_W
```

### M4.6 集成到 `DetectorConstruction`

- 从 config 读取 profile 文件路径。
- 从 config 读取 profile ID。
- 用 `CollimatorProfileReader` 读取并验证。
- 用 `CollimatorBuilder` 构建两块 jaw。

## 完成标准

- 合法 `P001` 生成两块钨 jaw。
- 非法 profile 仍在 reader 阶段报错停止。
- 可视化中可见两块五边形钨板。
- 使用 CSV 全局 x-z 坐标，不额外加 z 偏移。
- 未实现探测面穿越或输出逻辑。

## 不做

- 不修改 profile CSV 格式。
- 不自动批量扫描 profile。
- 不添加额外坐标偏移。
- 不检查 z 是否落在 `[-28, -20] mm`。
- 不写 CSV。

## 推荐 Codex prompt

```text
Read docs/spec.md, docs/architecture.md, docs/decisions.md, and docs/milestones.md.
Implement Milestone 4 only: collimator geometry construction.
Use CollimatorProfileReader output to build two tungsten jaws with G4ExtrudedSolid.
Preserve global x-z coordinates and rotate extrusion so each jaw extends along global y.
Do not modify CSV format, add offsets, implement batch scanning, stepping, or output logic.
After implementation, summarize changed files and visual verification steps.
```

---

# M5：Primary generator 与 Spectrum sampler

## 目标

实现 primary gamma 源：每个 event 产生一个 gamma，支持 mono 与 spectrum 能量模式，并使用目标平面圆盘采样生成锥束方向。

## 修改文件

- `include/PrimaryGeneratorAction.hh`
- `src/PrimaryGeneratorAction.cc`
- `include/SpectrumSampler.hh`
- `src/SpectrumSampler.cc`
- 必要时调整 `SimulationConfig`

## 任务

### M5.1 点源 gamma

每个 event：

- 粒子：gamma；
- 源位置：`(0, 0, -185 mm)`；
- primary 数量：1。

### M5.2 mono 模式

当：

```text
/source/energyMode mono
```

使用配置的 mono energy，默认 `160 keV`。

### M5.3 spectrum sampler

读取 CSV：

```csv
energy_keV,weight
40,0.01
45,0.03
50,0.06
```

验证：

- 文件存在；
- 必要列存在；
- energy 为正且有限；
- weight 非负且有限；
- 至少一个 weight 大于 0。

采样：

- 内部归一化；
- 构建 CDF；
- 每个 event 采样一次能量。

### M5.4 目标平面圆盘采样

每个 event：

1. 在 `z = 0 mm` 平面半径 `1.5 mm` 的圆盘内均匀采样目标点；
2. 圆心 `(0, 0, 0)`；
3. 初始方向：

```text
normalize((x_target, y_target, 0) - (0, 0, -185))
```

### M5.5 初始能量交给 event state

为 M6 提供接口，把 `initial_energy_keV` 写入 `EventAction`。

## 完成标准

- 每 event 一个 primary gamma。
- mono 默认 `160 keV` 可用。
- spectrum 模式可读取并采样 `data/spectrum.csv`。
- 方向指向 z = 0 圆盘采样点。
- 不模拟源准直器。

## 不做

- 不添加源位置或束斑半径宏命令。
- 不实现 detector crossing。
- 不实现 scatter counting。
- 不写 CSV。

## 推荐 Codex prompt

```text
Read docs/spec.md, docs/architecture.md, docs/decisions.md, and docs/milestones.md.
Implement Milestone 5 only: primary generator and spectrum sampler.
Generate one primary gamma per event from (0,0,-185 mm), using target-plane disk sampling at z=0 with radius 1.5 mm.
Support mono and spectrum modes with strict spectrum CSV validation and CDF sampling.
Do not simulate source collimator, detector crossing, scatter tracking, CSV output, or post-processing.
After implementation, summarize changed files and mono/spectrum tests.
```

---

# M6：Event 状态模型

## 目标

创建单 event 状态模型，用于保存 primary gamma 的初始能量、PMMA 散射摘要和探测面 hit 信息。该阶段只定义和维护状态，不实现 step 判断。

## 修改文件

- `include/EventAction.hh`
- `src/EventAction.cc`
- `include/PrimaryGeneratorAction.hh`
- `src/PrimaryGeneratorAction.cc`
- 可选 `include/SimulationData.hh` 或 `include/EventRecord.hh`

## 任务

### M6.1 散射状态

每个 event 保存：

- `initial_energy`；
- `scatter_count_total`；
- `compton_count`；
- `rayleigh_count`；
- `first_scatter_x/y/z`；
- `last_scatter_x/y/z`。

无散射时 first/last scatter 坐标为 NaN。

### M6.2 detector hit 状态

保存是否被探测。若被探测，保存：

- `det_x`；
- `det_y`；
- `det_z`；
- `det_energy`；
- `det_dir_x/y/z`。

### M6.3 event reset

每个 event 开始时：

- 散射计数置 0；
- first/last scatter 置 NaN；
- detector hit flag 置 false；
- detector hit 数据重置；
- 准备接收初始能量。

### M6.4 状态更新接口

提供清晰方法，例如：

- `SetInitialEnergy(...)`
- `RecordComptonScatter(position)`
- `RecordRayleighScatter(position)`
- `RecordDetectorHit(...)`
- `HasDetectorHit()`
- `GetRecord()`

### M6.5 multiple scatter 标记

定义：

```text
is_multiple_scatter = scatter_count_total >= 2
```

可作为派生值计算。

## 完成标准

- event start 能正确重置状态。
- 初始能量可写入。
- Compton/Rayleigh 计数可通过显式方法更新。
- detector hit 可通过显式方法记录。
- `is_multiple_scatter` 可获取。
- 未写 CSV。

## 不做

- 不实现 step-level process detection。
- 不实现 detector plane crossing。
- 不写 CSV。
- 不实现多线程合并。
- 不输出未命中 event。

## 推荐 Codex prompt

```text
Read docs/spec.md, docs/architecture.md, docs/decisions.md, and docs/milestones.md.
Implement Milestone 6 only: event-level state model.
Create per-event state for initial energy, Compton/Rayleigh counts, first/last scatter positions, detector hit information, and is_multiple_scatter.
Implement reset and update methods, but do not implement step-level process detection, detector crossing, CSV writing, or multi-thread output.
After implementation, summarize changed files and state update flow.
```

---

# M7：Stepping 逻辑

## 目标

实现 primary gamma 的 step-level 散射统计和探测面穿越判断，并把结果写入 `EventAction`。

## 修改文件

- `include/SteppingAction.hh`
- `src/SteppingAction.cc`
- 必要时调整 `EventAction`
- 必要时调整 `DetectorConstruction` 以暴露 detector config

## 任务

### M7.1 过滤 primary gamma

只处理：

```text
particle_name == gamma
track_id == 1
parent_id == 0
```

所有其他粒子和 secondary gamma 均忽略。

### M7.2 判断 PMMA 内散射

只计数：

```text
compt
Rayl
```

并且相互作用发生在 PMMA 内。

不计数：

- photoelectric effect；
- tungsten collimator；
- air；
- World；
- secondary particle interactions。

### M7.3 记录散射位置

使用：

```cpp
step->GetPostStepPoint()->GetPosition()
```

更新：

- total scatter count；
- Compton 或 Rayleigh count；
- first scatter position；
- last scatter position。

### M7.4 判断探测面穿越

探测面：

```text
z = -73 mm
```

条件：

```text
preStep.z > detector_z
postStep.z <= detector_z
direction.z < 0
```

### M7.5 线性插值穿越点

```text
t = (detector_z - pre_z) / (post_z - pre_z)
det_x = pre_x + t * (post_x - pre_x)
det_y = pre_y + t * (post_y - pre_y)
```

接受范围：

```text
53 mm <= det_x <= 161 mm
-50 mm <= det_y <= 50 mm
```

### M7.6 记录 detector hit

记录：

- `det_x`
- `det_y`
- `det_z`
- `det_energy`
- `det_dir_x/y/z`

同一 event 只允许记录一次有效 hit。

## 完成标准

- 只有 primary gamma 更新 event record。
- PMMA 内 Compton/Rayleigh 计数正确。
- first/last scatter 更新正确。
- detector hit 只在有效穿越且落入边界时记录。
- 未到达探测器的 event 保持 unhit。
- 不写 CSV，除非 M8 已另行实现。

## 不做

- 不统计 secondary gamma。
- 不统计 tungsten、air、world 相互作用。
- 不把 photoelectric effect 算作散射。
- 不输出完整轨迹。
- 不添加探测器响应。

## 推荐 Codex prompt

```text
Read docs/spec.md, docs/architecture.md, docs/decisions.md, and docs/milestones.md.
Implement Milestone 7 only: stepping logic.
Only process primary gamma tracks. Count PMMA-internal Compton and Rayleigh scatters using post-step positions, and detect detector plane crossing at z=-73 mm using linear interpolation and detector bounds.
Do not count secondary particles, tungsten interactions, air/world interactions, or photoelectric effect.
Do not change CSV schema, add detector response, or output full trajectories.
After implementation, summarize changed files and how to inspect event state.
```

---

# M8：单线程 CSV 输出

## 目标

实现单线程 CSV 输出。该阶段创建输出目录、写 header，并对每个被探测 primary gamma 写一行。多线程临时文件与合并推迟到 M9。

## 修改文件

- `include/CsvWriter.hh`
- `src/CsvWriter.cc`
- `include/RunAction.hh`
- `src/RunAction.cc`
- `include/EventAction.hh`
- `src/EventAction.cc`
- 必要时调整 `SimulationConfig`

## 任务

### M8.1 创建输出目录

使用：

```text
/output/directory results
```

默认 `results/`。目录不存在时创建；失败时报错停止。

### M8.2 单线程文件命名

mono compact：

```text
results/hits_profile_{profile_id}_mono_{energy}keV_seed{seed}.csv
```

mono debug：

```text
results/hits_profile_{profile_id}_mono_{energy}keV_seed{seed}_debug.csv
```

spectrum compact：

```text
results/hits_profile_{profile_id}_spectrum_seed{seed}.csv
```

spectrum debug：

```text
results/hits_profile_{profile_id}_spectrum_seed{seed}_debug.csv
```

### M8.3 compact header

```csv
initial_energy,det_x,det_y,det_energy,scatter_count_total,compton_count,rayleigh_count,is_multiple_scatter,first_scatter_x,first_scatter_y,first_scatter_z,last_scatter_x,last_scatter_y,last_scatter_z
```

### M8.4 debug header

```csv
event_id,track_id,parent_id,det_z,det_dir_x,det_dir_y,det_dir_z,initial_energy,det_x,det_y,det_energy,scatter_count_total,compton_count,rayleigh_count,is_multiple_scatter,first_scatter_x,first_scatter_y,first_scatter_z,last_scatter_x,last_scatter_y,last_scatter_z
```

### M8.5 只写被探测 event

- hit 为 true：写一行；
- hit 为 false：不写。

### M8.6 writer 生命周期

`RunAction`：

- run begin 打开 writer；
- run end 关闭 writer。

`EventAction` 通过受控接口写行。

## 完成标准

- 单线程 debug 模式写出 debug header。
- 单线程 compact 模式写出 compact header。
- 只写 detected primary gamma。
- 字段顺序完全符合 `spec.md`。
- 单位为 mm 和 keV。
- 未实现多线程合并。

## 不做

- 不实现 multi-thread merge。
- 不让多个线程共享一个 `std::ofstream`。
- 不增加 CSV 列。
- 不输出未探测 event。

## 推荐 Codex prompt

```text
Read docs/spec.md, docs/architecture.md, docs/decisions.md, and docs/milestones.md.
Implement Milestone 8 only: single-thread CSV output.
Create CsvWriter, write exact debug and compact headers, generate file names from profile_id, energy mode, mono energy, seed, and debug mode, and write one row only for detected primary gamma events.
Do not implement multi-thread merging, share ofstream across threads, or add CSV columns.
After implementation, summarize changed files and single-thread output tests.
```

---

# M9：多线程输出合并

## 目标

实现多线程安全 CSV 输出。每个 worker 线程写独立临时 CSV，master 在 run 结束合并。

## 修改文件

- `include/CsvWriter.hh`
- `src/CsvWriter.cc`
- `include/RunAction.hh`
- `src/RunAction.cc`
- 必要时调整 `EventAction` 与 `SimulationConfig`

## 任务

### M9.1 创建临时目录

线程临时文件放在：

```text
{outputDirectory}/tmp/
```

默认：

```text
results/tmp/
```

创建失败时报错停止。

### M9.2 临时文件命名

示例：

```text
results/tmp/hits_profile_P001_mono_160keV_seed12345_thread0.csv
results/tmp/hits_profile_P001_mono_160keV_seed12345_thread1.csv
results/tmp/hits_profile_P001_mono_160keV_seed12345_debug_thread0.csv
```

文件名应包含：

- profile ID；
- energy mode；
- mono energy，若 mono；
- seed；
- debug suffix，若 debug；
- thread ID。

### M9.3 每个 worker 独立写入

每个 worker 只写自己的文件。不得多个 worker 共享同一个 `std::ofstream`。

### M9.4 master 合并

run end 时 master 合并临时文件到最终 CSV。

规则：

- 最终文件只保留一个 header；
- 保留全部数据行；
- 任一临时文件无法读取时报错；
- 最终文件无法写入时报错。

### M9.5 临时文件处理

合并成功后：

- compact：删除对应临时文件；
- debug：保留对应临时文件。

合并失败：

- 保留所有临时文件；
- 报错。

### M9.6 保持单线程行为

单线程输出仍应可用。实现可以内部也使用 thread0 临时文件再合并，但用户可见最终文件名必须符合 `spec.md`。

## 完成标准

- 多线程 compact 运行产生线程临时 CSV。
- master 合并出最终 compact CSV。
- 最终文件只有一个 header。
- compact 合并成功后删除临时文件。
- debug 合并成功后保留临时文件。
- 合并失败保留临时文件并报错。
- 无共享输出流。

## 不做

- worker 不直接写最终文件。
- worker 不执行合并。
- merge failure 不删除临时文件。
- 不在 compact 输出中添加 thread ID 列。
- 不改变 CSV schema。

## 推荐 Codex prompt

```text
Read docs/spec.md, docs/architecture.md, docs/decisions.md, and docs/milestones.md.
Implement Milestone 9 only: multi-thread output merge.
Each worker thread must write an independent temporary CSV under results/tmp, and the master must merge them at run end with only one header.
Compact mode should delete temp files after successful merge; debug mode should preserve temp files. Merge failure must preserve temp files and report an error.
Do not let multiple threads share an ofstream, workers write directly to final output, or change CSV schema.
After implementation, summarize changed files and single-/multi-thread test commands.
```

---

# M10：宏文件、README 与验收

## 目标

补齐第一版可用性材料：运行宏、可视化宏、示例数据、README 和验收清单。

## 创建或修改文件

- `macros/run.mac`
- `macros/run_mt.mac`
- `macros/vis.mac`
- `data/collimator_profiles.csv`
- `data/spectrum.csv`
- `README.md`
- 可选 `docs/acceptance_checklist.md`

## 任务

### M10.1 `macros/run.mac`

单线程最小测试：

```text
/run/numberOfThreads 1
/run/randomSeed 12345

/geometry/collimatorProfileFile data/collimator_profiles.csv
/geometry/collimatorProfileId P001
/geometry/enableAirDefect true

/source/energyMode mono
/source/monoEnergy 160 keV

/output/directory results
/output/debug true

/run/initialize
/run/beamOn 1000
```

期望输出：

```text
results/hits_profile_P001_mono_160keV_seed12345_debug.csv
```

### M10.2 `macros/run_mt.mac`

多线程正式运行测试：

```text
/run/numberOfThreads 8
/run/randomSeed 12345

/geometry/collimatorProfileFile data/collimator_profiles.csv
/geometry/collimatorProfileId P001
/geometry/enableAirDefect true

/source/energyMode mono
/source/monoEnergy 160 keV

/output/directory results
/output/debug false

/run/initialize
/run/beamOn 100000
```

期望输出：

```text
results/hits_profile_P001_mono_160keV_seed12345.csv
```

### M10.3 `macros/vis.mac`

可视化宏应支持检查：

- PMMA 模体；
- 空气缺陷开关；
- 两块五边形钨准直器 jaw；
- 探测面辅助体；
- 源位置；
- 少量 gamma 轨迹。

### M10.4 占位准直器 profile

`data/collimator_profiles.csv` 包含占位 `P001`：

```csv
profile_id,jaw_id,vertex_id,x_mm,z_mm
P001,jaw_0,0,50,-28
P001,jaw_0,1,105,-28
P001,jaw_0,2,106,-24
P001,jaw_0,3,105,-20
P001,jaw_0,4,50,-20
P001,jaw_1,0,108,-24
P001,jaw_1,1,109,-28
P001,jaw_1,2,164,-28
P001,jaw_1,3,164,-20
P001,jaw_1,4,109,-20
```

必须说明：该 profile 只是编译、可视化和输出流程测试用占位几何，不代表真实准直器。

### M10.5 示例 spectrum

`data/spectrum.csv` 提供一个合法示例。除非后续替换为真实能谱，否则仅用于测试 spectrum 模式。

### M10.6 README

README 至少包含：

1. 项目简介；
2. 软件环境；
3. 编译命令；
4. 单线程运行命令；
5. 多线程运行命令；
6. 可视化运行命令；
7. 宏命令说明；
8. 准直器 profile CSV 格式；
9. spectrum CSV 格式；
10. 输出 CSV 字段；
11. debug 与 compact 模式区别；
12. 占位 profile 警告；
13. 第一版限制。

编译命令示例：

```bash
mkdir build
cd build
cmake ..
make -j
```

运行命令示例：

```bash
./MSS macros/run.mac
./MSS macros/run_mt.mac
./MSS macros/vis.mac
```

若从 `build/` 目录运行，需要 README 说明宏路径是否为 `../macros/run.mac`，或者在构建后复制宏文件到运行目录。该点必须与实际 CMake 行为一致。

### M10.7 验收清单

记录检查项：

- 几何可视化；
- 单线程 debug 输出；
- 多线程 compact 输出；
- 非法 profile 报错；
- CSV header 正确；
- 临时文件清理行为正确。

## 完成标准

- `./MSS macros/run.mac` 或 README 中指定的等价路径生成预期 debug CSV。
- `./MSS macros/run_mt.mac` 或 README 中指定的等价路径生成预期 compact CSV。
- `macros/vis.mac` 可用于几何和轨迹检查。
- README 命令与实际行为一致。
- 占位数据文件存在。
- 验收清单与 `spec.md` 一致。

## 不做

- 不添加 Python 后处理脚本。
- 不添加图像重建。
- 不添加真实探测器响应。
- 不添加 profile 批处理。
- 不声称占位 profile 是真实准直器几何。

## 推荐 Codex prompt

```text
Read docs/spec.md, docs/architecture.md, docs/decisions.md, and docs/milestones.md.
Implement Milestone 10 only: macros, README alignment, and acceptance tests.
Create run.mac, run_mt.mac, vis.mac, placeholder collimator_profiles.csv, sample spectrum.csv, and update README with build/run instructions, macro commands, CSV schemas, debug/compact distinction, and first-version limitations.
Use project/executable name MSS. Do not add post-processing scripts, reconstruction, detector response, or profile batch scanning.
After implementation, summarize changed files and acceptance tests.
```

---

# 5. Deferred work

以下内容明确不属于第一版实现序列。除非未来 `spec.md` 或新的里程碑明确要求，Codex 不得实现。

## 5.1 延后仿真功能

- 图像重建；
- 真实探测器材料响应；
- 探测器能量沉积 scoring；
- 源准直器建模；
- 源位置宏命令；
- 探测器边界宏命令；
- 全散射轨迹输出；
- 自动扫描所有 collimator profile；
- 真实准直器 profile 生成逻辑。

## 5.2 延后数据与分析功能

- 真实测量能谱文件；
- 真实准直器 profile 坐标；
- Python 后处理脚本；
- 多重散射比例图；
- 能谱分布图；
- 探测面 x 分布图；
- profile 对比图；
- 会议论文图表生成。

## 5.3 延后工程功能

- 单元测试框架；
- CI 配置；
- 容器化构建环境；
- 性能基准；
- 大规模批运行管理；
- 仿真 campaign 元数据数据库。

---

# 6. 总体 Codex 工作流

规划文件就绪后，建议先让 Codex 做一次只读检查：

```text
Read docs/spec.md, docs/architecture.md, docs/decisions.md, and docs/milestones.md.
Do not write code yet.
Summarize the implementation order and identify ambiguities that block Milestone 0.
```

然后逐阶段推进：

```text
Read docs/spec.md, docs/architecture.md, docs/decisions.md, and docs/milestones.md.
Implement Milestone 0 only.
Do not implement Milestone 1 or later.
After implementation, summarize changed files, how to build, and deferred work.
```

每个里程碑完成后：

```text
Review the previous implementation against docs/milestones.md.
Check whether it implemented anything beyond the requested milestone.
If yes, identify the extra changes and suggest whether to revert them.
Do not write new code unless asked.
```
