# AGENTS.md

本文件面向 Codex，用于约束 `MSS` 项目的代码生成、修改和审查行为。

`MSS` 是一个 Geant4 gamma 背散射 Monte Carlo 仿真项目。当前项目已进入第二轮构建阶段，目标是围绕车辆侧向背散射 ROI 场景，建立固定车辆 ROI + 移动成像头条件下的事件级数据生成链路。

本轮项目目标固定为搭建 Geant4 仿真程序并输出事件级数据。位姿级数据、扫描级数据、summary、统计图、差异图、指标计算和后处理脚本不在本轮实现，留到下一轮项目迭代。

第一轮项目内容仅作为历史参考，不作为当前实现的硬性约束。

---

## 1. 当前项目阶段

当前阶段为：

```text
第二轮车辆侧向背散射 ROI 仿真重构
```

核心变化包括：

- 研究对象从基础 PMMA 模体转向车辆侧向 ROI 模型；
- 扫描方式从固定几何运行转向固定车辆 ROI、移动成像头；
- 成像头由射线源、狭缝准直器、虚拟探测器平面组成；
- 射线源采用斜入射有限焦点笔形束；
- 准直器由外部 CSV profile 定义，profile 内 jaw 数量可变；
- 探测器采用单个虚拟探测平面；
- 不再默认构建镜像准直器；
- 不再默认构建镜像探测器；
- 输出字段需要按车辆 ROI、成像头位姿和多重散射统计需求重新定义；
- 本轮 Geant4 基础程序只输出事件级 CSV 与每个 run 的 `metadata.yaml`；
- 本轮不实现位姿级 / 扫描级数据、summary、统计图或后处理脚本。

---

## 2. 必须先阅读的文档

在任何代码修改前，先阅读以下文件：

1. `docs/change.md`
2. `docs/spec.md`
3. `docs/architecture.md`
4. `docs/decisions.md`
5. `docs/milestones.md`
6. `docs/acceptance_checklist.md`

文档优先级如下：

```text
docs/spec.md
  > docs/decisions.md
  > docs/architecture.md
  > docs/milestones.md
  > docs/acceptance_checklist.md
  > existing code
```

`docs/change.md` 用于理解第二轮构建背景、第一轮与第二轮的差异、旧项目内容的参考边界。

如果第一轮文档、旧代码或旧实现与第二轮文档冲突，应以第二轮文档为准，并在总结中指出冲突。

如果本文件与 `docs/spec.md` 或 `docs/decisions.md` 冲突，应以 `docs/spec.md` 和 `docs/decisions.md` 为准，并优先修订本文件。

不得静默继承第一轮设计。

---

## 3. 历史文档规则

如果存在以下目录：

```text
docs/archive/v1/
```

其中内容仅作为历史参考。

不得把 `docs/archive/v1/` 下的文档作为当前实现依据，除非用户明确要求参考第一轮实现。

第一轮内容可以参考的部分包括：

- Geant4 项目结构；
- 事件级 CSV 输出链路；
- 多线程临时文件与 master 合并策略；
- 宏命令组织方式；
- 文档分层方式。

第一轮内容不得默认继承的部分包括：

- PMMA 模体作为主要研究对象；
- 空气缺陷模型；
- 三块固定 jaw；
- 镜像准直器；
- 镜像探测器；
- 旧探测器边界；
- 旧 CSV schema；
- 只统计 PMMA 内散射；
- 第一轮固定几何扫描方式。

---

## 4. 项目基本约束

| 项目 | 要求 |
|---|---|
| 项目名 | `MSS` |
| CMake project 名 | `MSS` |
| 可执行文件名 | `MSS` |
| 语言标准 | C++17 |
| Geant4 版本 | 11.2.0 |
| 目标系统 | Ubuntu 24.04 |
| 构建系统 | CMake |
| 输出格式 | CSV |

不得重新引入旧项目名 `BackscatterSim`。


### 4.1 World 基本约束

第二轮基础实现使用固定 World，不采用复杂的按 pose 自动扩展策略。

World 约定为：

```text
shape = box
center_mm = [0, 0, 0]
size_mm = [4000, 4000, 4000]
material = G4_AIR
```

实现必须检查 VehicleROI 以及所有 pose 下的 source、collimator jaw、virtual detector plane 均位于 World 内。若任一组件超出 World，应在事件产生前 fail fast。

World 配置应写入每个 run 的 `metadata.yaml`。

---

## 5. 第二轮必须实现的方向

第二轮围绕以下系统构建：

```text
固定车辆 ROI 模型
+ 移动成像头组件
+ x-y 离散扫描位姿
+ 每个位姿独立 Monte Carlo 统计
+ 事件级 CSV 与 metadata 输出
```

当前实现应服务两条需求线。需要注意，本轮只生成事件级数据；下列需求中的位姿级统计、扫描级统计、二维响应图、差异图和论文指标不在本轮实现，只要求事件级输出为下一轮后处理保留必要信息。

当前实现应服务两条需求线：

### A 线：项目摸底

用于判断车辆侧向 ROI 场景下，不同成像头位姿是否能形成可解释、可比较的背散射统计响应。

关注：

- 探测计数；
- 探测效率；
- 探测能量分布；
- 探测面空间分布；
- 不同车辆结构区贡献；
- 有 / 无内部目标物对照。

### B 线：论文数据

用于分析被探测粒子的多重散射性质。

关注：

- 散射次数分布；
- 单次散射与多重散射比例；
- Compton / Rayleigh 等过程贡献；
- 探测能量与散射次数关系；
- first scatter / last scatter 空间位置；
- first / last scatter 所在 volume / material / region；
- 内部目标物对散射统计的影响。

---

## 6. 第二轮当前非目标

除非 `docs/spec.md` 或用户明确要求，不得主动实现：

- 整车 CAD 复现；
- 完整车辆扫描；
- 发动机舱详细建模；
- 底盘详细建模；
- 远侧车体完整遮挡建模；
- 大量金属机械结构建模；
- 真实探测器材料响应；
- 探测器能量沉积 scoring；
- 工程级图像重建；
- 连续运动扫描；
- 运动模糊；
- 自动完成大规模 scan campaign 的任务管理系统；
- 成像头旋转；
- 成像头 z 方向运动；
- 镜像准直器；
- 镜像探测器；
- 论文作图脚本；
- 完整 Python 后处理分析系统；
- 位姿级 summary 输出；
- 扫描级 summary 输出；
- 后处理脚本；
- 统计图、差异图、CNR 或论文指标计算。

---

## 7. 坐标系与扫描方式

项目使用统一 global 坐标系。

车辆 ROI 模型固定在 global 坐标系中，不通过整体平移表达扫描。

扫描通过移动成像头组件实现。

每个成像头位姿至少包含：

```text
pose_id
head_offset_x_mm
head_offset_y_mm
```

一次 run 对应一个 pose 和一个实际使用的 random seed。一次程序执行可以包含多个 pose，因此可以顺序产生多个 run。多线程只是单个 run 内部的并行执行方式，不改变 run 的定义。

成像头组件采用：

```text
零位姿 global 坐标 + 位姿 offset
```

即：

```text
x_actual = x_zero + head_offset_x_mm
y_actual = y_zero + head_offset_y_mm
z_actual = z_zero
```

第二轮默认不考虑：

- 成像头旋转；
- 成像头 z 方向位移；
- 连续运动；
- 运动模糊；
- 时间相关探测器积分。


### 7.1 run 与 seed 规则

本轮项目中：

```text
一个 run = 一个 pose + 一个实际使用的 random seed + 一组 model condition + n_primary
```

一个 run 可以使用多线程执行。线程是 run 内部的并行执行方式，不改变 run 与 pose / seed 的一一对应关系。

一次程序执行可以包含多个 pose，因此可以顺序执行多个 run。每个 pose run 必须使用一个新的 seed，并在该 run 的 `metadata.yaml` 中记录实际使用的 seed。

推荐默认规则为：

```text
pose_seed = base_random_seed + pose_index
```

其中 `base_random_seed` 来自入口 YAML，`pose_index` 为程序生成 pose 列表中的顺序编号。若实现采用等价的简单策略，必须保证每个 pose run 的 seed 明确、可记录、可复现。

---

## 8. 车辆 ROI 模型规则

车辆 ROI 模型是车辆侧向背散射 ROI 近似模型，不追求整车 CAD 复现。

重点建模区域包括：

- 车门；
- 车窗；
- B 柱；
- 乘员舱空气；
- 座椅 / 内饰；
- 可选内部目标物。

暂不作为主要成像目标的区域包括：

- 底盘；
- 发动机舱；
- 远侧车体；
- 大量金属机械结构。

建模优先级：

1. 几何稳定；
2. 材料分区清楚；
3. 可视化可检查；
4. 易于修改；
5. 便于记录 volume / material / region；
6. 便于扫描位姿统计。

车辆 ROI 具体尺寸、材料和区域划分以 `docs/spec.md` 为准。

---

## 9. 成像头规则

成像头由以下部分组成：

```text
source
+ slit collimator
+ virtual detector plane
```

成像头内部组件在同一个 pose 内保持相对位置不变。

移动成像头时，应对成像头内所有组件统一施加 `head_offset_x_mm` 和 `head_offset_y_mm`。

---

## 10. 射线源规则

射线源采用斜入射有限焦点笔形束。

基本约束：

- 每个 event 产生一个 primary gamma；
- primary gamma 起点在圆形焦点面内均匀采样；
- 圆形焦点面垂直于入射方向；
- primary gamma 方向固定；
- 不再默认使用目标平面采样形成锥束；
- 入射方向位于 global `x-z` 平面；
- 入射角 `theta` 应可配置；
- 默认参考角度以 `docs/spec.md` 为准。

方向向量形式：

```text
incident_dir = (cos(theta), 0, sin(theta))
```

具体源位置、焦点尺寸和能量模式以 `docs/spec.md` 与入口 YAML 为准。除入口 YAML 文件路径外，不应为这些 YAML 已覆盖的参数新增宏命令。

---

## 11. 狭缝准直器规则

准直器由外部 CSV profile 定义。

CSV 基础必需列：

```csv
profile_id,jaw_id,vertex_id,x_mm,z_mm
```

CSV 可以包含可选列：

```csv
y_mm
```

基本规则：

- `x_mm` 和 `z_mm` 表示成像头零位姿下的 global `x-z` 坐标；
- `y_mm` 若存在，表示对应 jaw 的零位姿 global `y` 坐标；同一 jaw 内所有顶点的 `y_mm` 必须一致；
- 若 CSV 中不存在 `y_mm`，则该 jaw 的零位姿 `y` 坐标默认为 `0 mm`；
- 每个 profile 可包含可变数量的 jaw；
- 若某个 profile 包含 `M` 块 jaw，则 `jaw_id` 应连续编号为 `jaw_0 ... jaw_{M-1}`；
- 每块 jaw 是零位姿 global `x-z` 平面内的凸多边形；
- 每块 jaw 顶点数 `N >= 3`；
- 每块 jaw 使用 `G4ExtrudedSolid` 沿 global `y` 方向拉伸；
- `jaw_extrusion_length_y_mm` 表示沿 global `y` 方向的全长，不是 half length；
- pose 下 jaw 的 placement 满足 `x_actual = x_zero + head_offset_x_mm`、`y_actual = y_zero + head_offset_y_mm`、`z_actual = z_zero`；
- 同一次 run 默认只读取一个 profile；
- 几何在 run 内保持不变；
- 非法 profile 必须 fail fast，不得静默修复。

不得默认要求每个 profile 只有三块 jaw。

不得默认构建关于 `x = 0` 的镜像准直器。

---

## 12. 虚拟探测器规则

探测器采用单个理想虚拟平面。

基本规则：

- 不模拟真实探测器材料响应；
- 不实现真实 sensitive detector 能量沉积统计；
- 探测器首先以零位姿 global 坐标给出；
- 扫描时，探测器接收范围随成像头整体平移；
- 探测器几何位置需要与狭缝准直系统协同设计；
- 不构建镜像探测器。

探测器 `z` 位置、接收范围和命中判定逻辑以 `docs/spec.md` 为准。

---

## 13. 物理过程与事件记录

必须使用 Geant4 EM physics，具体 physics list 以 `docs/spec.md` 为准。

事件定义：

```text
1 event = 1 primary gamma
```

输出事件范围以 `docs/spec.md` 为准。

不得默认沿用第一轮“只输出到达探测器的 primary gamma”的完整 schema，除非第二轮规格明确要求。

事件级记录应围绕以下信息设计：

- 初始能量；
- 初始位置；
- 初始方向；
- 入射角 `theta`；
- `pose_id`；
- `head_offset_x_mm`；
- `head_offset_y_mm`;
- 探测位置；
- 探测能量；
- 探测方向；
- 散射次数；
- 不同物理过程次数；
- first scatter 位置；
- last scatter 位置；
- first / last scatter 所在 volume / material / region；
- 各车辆材料区内散射次数；
- 是否与内部目标物发生过相互作用。

字段的最小集合、扩展集合、顺序和单位以 `docs/spec.md` 为准。

---

## 14. 输出规则

CSV 输出必须保持可追踪性。

输出至少应能区分：

- run；
- pose；
- profile；
- source setting；
- detector setting；
- vehicle ROI setting；
- target present / absent；
- random seed；
- thread setting。

run-level 元数据写入文件名和 `metadata.yaml`。本轮不输出独立 pose-level summary 或 scan-level summary。是否写入每一行 CSV 以 `docs/spec.md` 为准。

正式 `events.csv` 只记录 detected primary gamma。Debug `events_debug.csv` 记录 detected 与 undetected primary gamma，并且只比正式 CSV 增加 `detected` 字段。

长度单位默认使用 `mm`。

能量单位默认使用 `keV`。

不得在没有文档依据的情况下随意重排 CSV 字段。

默认输出目录策略为 fail fast。若 `results/{run_id}/` 已存在且非空，程序应报错停止，不得覆盖、追加或自动生成新 run_id，除非后续文档明确修改该策略。

---

## 15. 模块边界

应保持职责分离。

建议模块边界如下：

| 模块 | 职责 |
|---|---|
| `DetectorConstruction` / `GeometryAssembly` | 组织固定 World、车辆 ROI、当前 pose 成像头组件和可视化辅助体 |
| `SimulationConfigReader` | 读取并验证入口 YAML `simulation_config_v2.yaml` 或用户通过 `--config` 指定的等价入口文件 |
| `VehicleROIConfigReader` | 读取并验证 `vehicle_roi_v03.yaml` 或入口 YAML 指定的 vehicle ROI 文件 |
| `SimulationConfig` | 保存运行配置、pose 原始配置、source、collimator、detector、physics、output 等参数 |
| `VehicleROIConstruction` | 构建车门、车窗、B 柱、乘员舱、座椅、目标物等 ROI 几何 |
| `ImagingHeadConstruction` | 构建射线源参考几何、准直器、虚拟探测器平面，并统一应用当前 pose offset |
| `SlitCollimatorProfileReader` | 读取并验证 collimator profile CSV |
| `SlitCollimatorBuilder` | 将已验证 profile 转换为 Geant4 tungsten jaw 几何 |
| `VirtualDetectorPlane` | 保存 detector zero/actual bounds，并提供 detector crossing 所需配置 |
| `ScanPose` / `PoseList` | 保存 `pose_id`、`head_offset_x_mm`、`head_offset_y_mm` 等扫描位姿 |
| `ScanPoseManager` | 根据 list / grid 配置生成 pose 列表和自动 `pose_id` |
| `PoseRunController` | 按 pose 顺序执行多个 run；每个 run 对应一个 pose 和一个 seed |
| `PrimaryGeneratorAction` | 每个 event 生成一个 primary gamma |
| `EventAction` | 保存单个 event 的散射摘要、探测命中信息，并在 event end 触发写出 |
| `SteppingAction` | 记录散射、volume / material / region、探测平面穿越 |
| `CsvWriter` | 写 CSV，管理 thread-local 文件与合并 |
| `RunAction` | 管理当前 run 的 seed、输出模式、文件命名、writer 生命周期和 run-end merge |
| `MetadataWriter` | 为每个 run 写出 `metadata.yaml` |
| `SimulationMessenger` | 仅保留必要的入口 YAML 路径指定 / 调试兼容能力，不作为主配置系统 |

禁止把 CSV 写入逻辑直接塞进 `SteppingAction`。

禁止把 profile CSV 解析逻辑直接塞进 `CollimatorBuilder`。

禁止把车辆 ROI 几何、成像头几何和输出统计逻辑混在同一个类中。

`StatisticsAccumulator`、`ScanSummaryWriter`、pose-level summary、scan-level summary 和后处理指标计算不属于本轮 Geant4 基础程序模块。

---

## 16. 宏命令规则

第二轮宏命令以 `docs/spec.md` 为准。

不得因为第一轮存在某些宏命令，就强制第二轮继续沿用。

可以保留兼容性宏命令，但前提是：

- 不与第二轮设计冲突；
- 不误导当前实现；
- 在 README 或文档中明确其用途；
- 不把第一轮参数变成第二轮硬约束。

新增宏命令时应优先覆盖以下配置：

- collimator profile file；
- collimator profile id；
- source energy mode；
- source mono energy；
- source spectrum file；
- source theta；
- source focus diameter；
- scan pose id；
- head offset x；
- head offset y；
- output directory；
- output mode；
- random seed；
- number of threads；
- target present / absent。

具体命名以 `docs/spec.md` 为准。

---

## 17. 里程碑执行规则

按 `docs/milestones.md` 分阶段实现。

Codex 每次只能实现用户指定的一个 milestone。

不得主动实现后续 milestone。

如果用户要求实现某个 milestone，应先确认该 milestone 的输入文档是否足够明确。

如果发现文档缺失、互相冲突或参数未定义，应暂停并列出阻塞点，不要自行补全关键物理参数。

每次完成后必须总结：

```text
- changed files
- implemented behavior
- build/test commands used or recommended
- intentionally deferred work
- unresolved questions or assumptions
```

如果发现前一 milestone 的实现有问题，应先说明问题，再进行最小必要修改。

---

## 18. 构建与运行命令

典型构建命令：

```bash
mkdir -p build
cd build
cmake ..
make -j
```

单线程测试示例：

```bash
./MSS macros/run.mac
```

多线程测试示例：

```bash
./MSS macros/run_mt.mac
```

可视化测试示例：

```bash
./MSS macros/vis.mac
```

如果实际运行目录要求从 repository root 调用，应在 README 中明确说明。

---

## 19. Git 与生成文件规则

不得把以下内容提交到 git：

```text
build/
results/*.csv
results/tmp/
*.root
*.o
*.so
*.dylib
*.dll
.DS_Store
```

可以保留：

```text
results/.gitkeep
data/*.csv
data/*.yaml
macros/*.mac
```

`data/*.csv` 若只是占位数据，必须在 README 或注释中明确标注为 placeholder。

---

## 20. Codex 输出要求

修改代码时：

- 保持改动最小；
- 不要重排无关代码；
- 不要格式化整个仓库；
- 不要主动重构无关模块；
- 不要把中文文档翻译成英文，除非用户明确要求；
- 类名、文件名、宏命令、CSV 字段名保持英文；
- 说明文字和文档可以使用中文；
- 不要自行扩大第二轮范围；
- 不要把第一轮常量当作第二轮物理约束；
- 不要把旧 CSV schema 当作第二轮固定 schema；
- 不要主动实现真实探测器响应或图像重建。

如果遇到歧义：

1. 先查 `docs/spec.md`；
2. 再查专项文档；
3. 再查 `docs/decisions.md`；
4. 再查 `docs/change.md`；
5. 若仍无法判断，暂停并列出阻塞点；
6. 不要自行替用户决定关键物理建模参数。
