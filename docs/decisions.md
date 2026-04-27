# MSS 设计决策记录

## 1. 文档目的

本文档记录 `MSS` 第一版中已经接受的关键设计决策，用于避免 Codex 生成代码时发生设计漂移。

本文档不替代 `spec.md`。功能需求、物理参数、宏命令、CSV 字段和验收标准仍以 `spec.md` 为准。

文档优先级：

1. `docs/spec.md`
2. `docs/decisions.md`
3. `docs/architecture.md`
4. `docs/milestones.md`
5. 现有代码，但前提是不与上述文档冲突

Codex 不应静默修改本文档中的 Accepted 决策。若必须修改，应先修改文档，再修改实现。

---

## 2. 决策状态

| 状态 | 含义 |
|---|---|
| Accepted | 已接受，当前实现必须遵守。 |
| Proposed | 提案中，尚未成为约束。 |
| Superseded | 已被后续决策替代。 |
| Deferred | 有价值，但明确推迟。 |

---

## 3. 决策索引

| ID | 决策 | 状态 |
|---|---|---|
| D001 | 第一版只聚焦事件级 Monte Carlo 数据生成 | Accepted |
| D002 | 使用固定右手坐标系，PMMA 深度为 +z | Accepted |
| D003 | 探测器建模为理想计数平面 | Accepted |
| D004 | 准直器几何由外部 CSV profile 定义 | Accepted |
| D005 | 使用 `G4ExtrudedSolid` 构建两块钨准直器 jaw | Accepted |
| D006 | 使用 `G4EmLivermorePhysics`，全局 production cut 为 0.1 mm | Accepted |
| D007 | 定义 1 event = 1 primary gamma | Accepted |
| D008 | 支持 mono/spectrum 能量模式，但第一版固定源几何 | Accepted |
| D009 | 只追踪 primary gamma 在 PMMA 内的散射历史 | Accepted |
| D010 | CSV 只输出到达探测器的 primary gamma | Accepted |
| D011 | CSV schema 保持稳定，run 元数据写入文件名 | Accepted |
| D012 | 多线程输出采用线程临时 CSV + master 合并 | Accepted |
| D013 | 使用宏命令配置运行参数，但核心几何常量固定 | Accepted |
| D014 | 非法准直器 profile 必须 fail fast | Accepted |
| D015 | 模块职责保持窄边界 | Accepted |
| D016 | 按里程碑实现，不跨阶段扩展 | Accepted |
| D017 | 推迟重建、真实探测器响应和后处理分析 | Accepted |
| D018 | 项目名、CMake project 名和可执行文件名统一为 `MSS` | Accepted |
| D019 | `/output/debug` 需要区分“未设置”和“显式设置” | Accepted |

---

## D001：第一版只聚焦事件级 Monte Carlo 数据生成

**状态：** Accepted  
**日期：** 2026-04-27

### 背景

当前目标是支持 gamma 背散射几何下，不同准直器轮廓或开口条件的多重散射统计。第一版应先生成可靠的事件级 CSV 数据，而不是把完整分析流程写进 Geant4 程序。

### 决策

第一版只生成到达探测器的 primary gamma 的事件级 CSV。

第一版不包含：

- 图像重建；
- 真实探测器材料响应；
- 探测器能量沉积建模；
- Python 后处理分析脚本；
- 自动遍历所有 profile；
- 全散射轨迹输出。

### 理由

先确保事件生成、散射统计和输出链路正确，再扩展分析或重建模块。这样更容易检查错误，也便于用 Codex 分阶段实现。

### 影响

- CSV 是仿真程序与后处理分析之间的边界。
- 后续分析脚本应读取 CSV，而不是依赖 Geant4 运行时内部状态。
- Codex 不得在第一版中主动加入重建或探测器响应。

---

## D002：使用固定右手坐标系，PMMA 深度为 +z

**状态：** Accepted  
**日期：** 2026-04-27

### 背景

坐标系会影响几何构建、源方向、探测面穿越判断和后处理解释。若轴向不固定，后续结果容易失去可比性。

### 决策

采用右手坐标系：

- `+z`：从 PMMA 前表面指向 PMMA 内部；
- `x`：主要横向方向，与准直器限束方向和探测面后处理坐标相关；
- `y`：狭缝/钨板拉伸方向，不作为主要分析维度；
- source 和 detector 位于 `z < 0`；
- PMMA 前表面为 `z = 0`。

### 理由

该约定使深度定义清晰，并使背散射探测条件简洁：被探测 gamma 朝 `-z` 方向穿越 `z = -73 mm` 平面。

### 影响

- Codex 不得把深度方向改到其他轴。
- 后处理脚本应把 `z` 解释为 PMMA 深度。

---

## D003：探测器建模为理想计数平面

**状态：** Accepted  
**日期：** 2026-04-27

### 背景

当前问题关注 PMMA 内散射历史和探测面到达统计，不关注真实探测器响应。

### 决策

探测器定义为理想平面：

```text
z = -73 mm
x = [53, 161] mm
y = [-50, 50] mm
```

第一版不建模闪烁体、半导体、sensitive detector 或能量沉积响应。

### 理由

理想平面可隔离输运和散射问题，避免真实探测器响应影响第一阶段统计。

### 影响

- detector hit 来自几何穿越判断。
- `det_energy` 表示穿越探测面时 gamma 的能量，不是探测器沉积能量。
- Codex 不得加入真实探测器响应，除非规格更新。

---

## D004：准直器几何由外部 CSV profile 定义

**状态：** Accepted  
**日期：** 2026-04-27

### 背景

项目需要比较不同准直器轮廓或开口。如果将所有轮廓硬编码到 C++ 中，修改与复现实验都会变得困难。

### 决策

准直器由外部 CSV 定义。每个 profile 包含：

- 一个 `profile_id`；
- 两块 jaw：`jaw_0` 与 `jaw_1`；
- 每块 jaw 五个顶点；
- 每个顶点为全局 `(x_mm, z_mm)` 坐标。

第一版每次运行只选择一个 profile：

```text
/geometry/collimatorProfileFile data/collimator_profiles.csv
/geometry/collimatorProfileId P001
```

### 理由

外部 profile 允许不重新编译即可改变准直器几何。单次选择一个 profile 比自动批处理更适合第一版。

### 影响

- `CollimatorProfileReader` 负责解析和验证。
- `CollimatorBuilder` 只负责把已验证 profile 转成 Geant4 几何。
- CSV schema 不得被 Codex 随意修改。

---

## D005：使用 `G4ExtrudedSolid` 构建两块钨准直器 jaw

**状态：** Accepted  
**日期：** 2026-04-27

### 背景

每块准直器 jaw 是全局 x-z 平面内的凸五边形，并沿全局 y 方向拉伸。

### 决策

每块 jaw 使用 `G4ExtrudedSolid` 构建。

坐标映射：

| 物理坐标 | `G4ExtrudedSolid` local 坐标 |
|---|---|
| global `x` | local `x` |
| global `z` | local `y` |
| global `y` | local `z` 拉伸方向 |

构建后旋转，使 local z 拉伸方向对应 global y 方向。按 `spec.md`，绕 x 轴 `+90 deg` 可接受。

### 理由

`G4ExtrudedSolid` 直接对应“二维多边形 + 一维拉伸”的几何形式，避免使用布尔减法。

### 影响

- CSV 中的 `x_mm` 与 `z_mm` 是全局坐标。
- builder 不得额外叠加 `collimator_center_z`。
- Codex 不得把 `z_mm` 误当作 local extrusion 坐标。

---

## D006：使用 `G4EmLivermorePhysics`，全局 production cut 为 0.1 mm

**状态：** Accepted  
**日期：** 2026-04-27

### 背景

仿真关注低能 gamma 在 PMMA 中的 Compton 与 Rayleigh 散射。

### 决策

使用：

```cpp
G4EmLivermorePhysics
```

全局 production cut：

```text
0.1 mm
```

### 理由

Livermore 电磁模型适合低能电磁相互作用，并包含 Rayleigh 散射。

### 影响

- `PhysicsList` 应保持简单明确。
- Codex 不得替换为其他 physics list，除非决策更新。

---

## D007：定义 1 event = 1 primary gamma

**状态：** Accepted  
**日期：** 2026-04-27

### 背景

CSV 每行表示一个到达探测器的 primary gamma 的历史摘要。

### 决策

```text
1 event = 1 primary gamma
```

因此：

```text
/run/beamOn N
```

表示模拟 `N` 个入射 gamma。

### 理由

该定义使 event 统计、散射计数和探测 hit 一一对应。

### 影响

- `EventAction` 每个 event 只维护一份散射摘要。
- Codex 不得在单个 event 中产生多个 primary gamma。

---

## D008：支持 mono/spectrum 能量模式，但第一版固定源几何

**状态：** Accepted  
**日期：** 2026-04-27

### 背景

需要 mono 模式用于调试，也需要 spectrum 模式用于后续接入真实能谱。但源几何已由规格固定。

### 决策

支持：

```text
/source/energyMode mono
/source/energyMode spectrum
```

源为 `(0, 0, -185 mm)` 点源，方向通过 z = 0 平面半径 `1.5 mm` 圆形束斑采样得到。

第一版不支持源位置、束斑大小的宏命令。

### 理由

只开放能量模式，固定源几何，可以减少第一版变量数量。

### 影响

- `PrimaryGeneratorAction` 实现固定源几何。
- `SpectrumSampler` 只处理能谱采样。
- Codex 不得增加源位置或束斑宏命令。

---

## D009：只追踪 primary gamma 在 PMMA 内的散射历史

**状态：** Accepted  
**日期：** 2026-04-27

### 背景

目标统计对象是“最终到达探测器的 primary gamma 在 PMMA 内经历了多少 Compton/Rayleigh 散射”。次级粒子或非 PMMA 相互作用会改变字段含义。

### 决策

只处理：

```text
particle_name == gamma
track_id == 1
parent_id == 0
```

只计入 PMMA 内过程：

```text
compt
Rayl
```

不计入：

- photoelectric effect；
- 钨准直器内相互作用；
- 空气或 World 中相互作用；
- secondary gamma 相互作用。

### 理由

这样 `scatter_count_total`、`compton_count`、`rayleigh_count` 的物理含义稳定。

### 影响

- `SteppingAction` 必须先过滤 primary gamma。
- 必须检查相互作用发生在 PMMA 内。
- Codex 不得把次级 gamma 或钨内相互作用计入 PMMA 散射。

---

## D010：CSV 只输出到达探测器的 primary gamma

**状态：** Accepted  
**日期：** 2026-04-27

### 背景

输出数据用于探测器侧统计。未到达探测面的 event 写出会显著增加文件体积，并改变数据集含义。

### 决策

CSV 只包含穿越探测面且落入探测器边界内的 primary gamma。

不输出：

- 未到达探测器的 event；
- 非 primary gamma；
- 非 gamma 粒子。

若 primary gamma 没有 PMMA 散射但到达探测器，仍应输出。

### 理由

输出聚焦于“探测器可见信号”的事件摘要。

### 影响

- `EventAction` 只在 hit 标记为 true 时写 CSV。
- Codex 不得改为输出所有 event。

---

## D011：CSV schema 保持稳定，run 元数据写入文件名

**状态：** Accepted  
**日期：** 2026-04-27

### 背景

后处理脚本依赖 CSV 字段。如果 Codex 任意增加字段，会破坏下游分析。

### 决策

保持两套 schema：

- compact：正式统计；
- debug：额外包含 event、track、方向等调试字段。

profile ID、energy mode、mono energy、random seed、debug 状态写入文件名，而不是重复写入每一行。

### 理由

稳定字段顺序可降低后处理复杂度。run 级信息放入文件名即可。

### 影响

- Codex 不得新增 CSV 列，除非 `spec.md` 更新。
- 输出文件名是数据契约的一部分。

---

## D012：多线程输出采用线程临时 CSV + master 合并

**状态：** Accepted  
**日期：** 2026-04-27

### 背景

Geant4 多线程运行中，多个 worker 共享一个输出流容易造成竞争和文件损坏。

### 决策

采用：

1. 每个 worker 写自己的临时 CSV。
2. worker 之间不共享 `std::ofstream`。
3. run 结束后由 master 合并。
4. 最终文件只保留一个 header。
5. compact 模式合并成功后删除临时文件。
6. debug 模式合并成功后保留临时文件。
7. 合并失败时保留所有临时文件并报错。

### 理由

线程独立文件比共享流加锁更容易实现和调试。

### 影响

- `CsvWriter` 必须线程感知。
- `RunAction` 触发合并。
- Codex 不得使用共享输出流替代该策略。

---

## D013：使用宏命令配置运行参数，但核心几何常量固定

**状态：** Accepted  
**日期：** 2026-04-27

### 背景

部分参数需要运行时切换，但几何常量若全部开放，第一版会失去稳定解释基础。

### 决策

第一版支持宏命令配置：

- collimator profile file；
- collimator profile ID；
- 是否启用空气缺陷；
- energy mode；
- mono energy；
- spectrum file；
- random seed；
- number of threads；
- output directory；
- debug mode。

第一版不支持宏命令配置：

- 源位置；
- 探测器边界；
- 探测面 z；
- 束斑大小；
- PMMA 尺寸；
- 空气缺陷尺寸。

### 理由

现有宏命令覆盖第一版实验变量，同时保持输出语义稳定。

### 影响

- `SimulationConfig` 集中保存运行配置。
- 固定几何常量应集中定义并易于检查。
- Codex 不得新增额外宏命令。

---

## D014：非法准直器 profile 必须 fail fast

**状态：** Accepted  
**日期：** 2026-04-27

### 背景

错误 profile 可能生成看似合理但实际错误的准直器几何。

### 决策

以下情况必须报错并停止：

- 找不到 `profile_id`；
- profile 中不是两块 jaw；
- jaw 不是五个顶点；
- `vertex_id` 缺失、重复或越界；
- 坐标为空、非数值、NaN 或 Inf；
- 多边形面积为 0；
- 五边形非凸。

### 理由

宁可早期失败，也不能产生误导性结果。

### 影响

- 验证逻辑属于 `CollimatorProfileReader`。
- Codex 不得静默修复非法 profile。

---

## D015：模块职责保持窄边界

**状态：** Accepted  
**日期：** 2026-04-27

### 背景

Codex 分阶段开发时，清晰边界可以降低耦合和误改概率。

### 决策

模块职责如下：

| 模块 | 职责 |
|---|---|
| `DetectorConstruction` | 构建 World、PMMA、空气缺陷、探测面辅助体，并调用准直器构建。 |
| `CollimatorProfileReader` | 读取和验证 profile CSV。 |
| `CollimatorBuilder` | 将 profile 转为钨准直器 Geant4 几何。 |
| `PrimaryGeneratorAction` | 每 event 产生一个 primary gamma。 |
| `SpectrumSampler` | 读取能谱 CSV 并采样初始能量。 |
| `EventAction` | 保存当前 event 的初始能量、散射摘要和 hit。 |
| `SteppingAction` | 判断 PMMA 散射与探测面穿越。 |
| `CsvWriter` | 写线程本地 CSV 并合并。 |
| `RunAction` | 管理随机种子、输出生命周期和合并。 |

### 影响

- CSV 写入不应放在 `SteppingAction`。
- profile 解析不应散落在 `DetectorConstruction` 中。
- spectrum 解析不应直接混入过多源几何逻辑。

---

## D016：按里程碑实现，不跨阶段扩展

**状态：** Accepted  
**日期：** 2026-04-27

### 背景

一次性生成完整项目会让错误难以定位。

### 决策

Codex 应按 `milestones.md` 一次实现一个里程碑。未经明确要求，不得实现后续里程碑。

### 理由

阶段式实现便于编译、可视化、验证和回滚。

### 影响

- 每次 Codex prompt 应明确目标 milestone。
- Codex 应总结改动文件、测试方法和暂缓内容。

---

## D017：推迟重建、真实探测器响应和后处理分析

**状态：** Accepted  
**日期：** 2026-04-27

### 背景

后续研究可能需要重建、真实探测器响应、批处理和绘图，但它们不是第一版可运行仿真的必要条件。

### 决策

推迟：

- 图像重建；
- 真实探测器材料响应；
- 探测器能量沉积统计；
- Python 后处理脚本；
- profile 批量扫描；
- 完整散射轨迹输出；
- 源位置宏命令；
- 探测器边界宏命令；
- 真实准直器 profile 生成逻辑。

### 影响

- 第一版验收目标是事件级仿真和 CSV 输出链路。
- Codex 不得把 deferred work 当成当前实现范围。

---

## D018：项目名、CMake project 名和可执行文件名统一为 `MSS`

**状态：** Accepted  
**日期：** 2026-04-27

### 背景

原文档中存在旧项目名 `BackscatterSim`。如果规划文档、CMake target、README 命令和宏运行命令不一致，Codex 容易生成旧名称或混合名称。

### 决策

第一版统一使用：

```text
项目名：MSS
CMake project：MSS
可执行文件：MSS
仓库根目录示例：MSS/
```

运行命令示例应使用：

```bash
./MSS macros/run.mac
./MSS macros/run_mt.mac
./MSS macros/vis.mac
```

### 理由

统一命名可以减少构建脚本、README 和 Codex prompt 中的歧义。

### 影响

- `spec.md`、`architecture.md`、`milestones.md`、`README.md`、`CMakeLists.txt` 应同步使用 `MSS`。
- 除非另有说明，Codex 不应再创建 `BackscatterSim` 可执行文件。

---

## D019：`/output/debug` 需要区分“未设置”和“显式设置”

**状态：** Accepted  
**日期：** 2026-04-27

### 背景

`spec.md` 定义默认规则：单线程默认 debug，多线程默认 compact。同时宏命令 `/output/debug true/false` 可以显式覆盖默认值。若配置中只有一个 `bool debugOutput`，则无法判断该值来自默认值还是用户显式设置。

### 决策

实现中应区分：

- 用户未设置 `/output/debug`；
- 用户显式设置 `/output/debug true`；
- 用户显式设置 `/output/debug false`。

推荐使用：

```cpp
std::optional<bool> debug_override;
```

或等价设计。

### 理由

该设计同时满足默认规则和显式覆盖规则。

### 影响

- `RunAction` 需要根据线程数和 `debug_override` 解析最终输出模式。
- `SimulationConfig` 不宜只用一个默认 bool 表示输出模式。

---

## 4. 新增决策模板

```md
## DXXX：简短标题

**状态：** Proposed | Accepted | Superseded | Deferred  
**日期：** YYYY-MM-DD

### 背景

需要决策的问题或歧义是什么？

### 决策

已经决定采用什么方案？

### 理由

为什么选择该方案？

### 备选方案

| 方案 | 未选择原因 |
|---|---|
| ... | ... |

### 影响

该决策影响哪些实现、测试或后续扩展？
```

---

## 5. 变更控制

修改 Accepted 决策时应：

1. 将旧决策标记为 `Superseded`。
2. 添加新的决策 ID。
3. 说明变化内容和原因。
4. 若影响需求、架构或实施顺序，同步更新 `spec.md`、`architecture.md` 或 `milestones.md`。
