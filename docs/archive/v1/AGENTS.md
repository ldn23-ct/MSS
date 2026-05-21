# AGENTS.md

本文件面向 Codex，用于约束 `MSS` 项目的代码生成、修改和审查行为。

`MSS` 是一个 Geant4 gamma 背散射 Monte Carlo 仿真项目。第一版目标是生成用于多重散射统计分析的事件级 CSV 数据，不实现图像重建、真实探测器响应或后处理分析。

---

## 1. 必须先阅读的文档

在任何代码修改前，先阅读以下文件：

1. `docs/spec.md`
2. `docs/decisions.md`
3. `docs/architecture.md`
4. `docs/milestones.md`

文档优先级如下：

```text
docs/spec.md
  > docs/decisions.md
  > docs/architecture.md
  > docs/milestones.md
  > existing code
```

如果现有代码与上述文档冲突，应以文档为准，并在总结中指出冲突。不得静默修改已接受的设计决策。

---

## 2. 项目基本约束

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

---

## 3. 第一版范围

### 必须实现

第一版只实现：

- gamma 背散射几何；
- PMMA 模体与可选空气缺陷；
- 外部 CSV 定义的三块钨准直器 jaw；
- 原始准直器与关于 `x = 0` 镜像的准直器；
- mono / spectrum 两种 primary gamma 能量模式；
- primary gamma 在 PMMA 内的 Compton / Rayleigh 散射计数；
- 理想探测平面穿越判断；
- 只输出到达探测器的 primary gamma；
- 单线程 debug CSV；
- 多线程 per-thread 临时 CSV 与 master 合并。

### 禁止主动实现

除非 `docs/spec.md` 或新的里程碑明确要求，不得实现：

- 图像重建；
- 真实探测器材料响应；
- 探测器能量沉积 scoring；
- source collimator；
- 自动遍历所有 collimator profile；
- 全散射轨迹输出；
- Python 后处理分析脚本；
- 会议论文作图脚本；
- 源位置宏命令；
- 探测器边界宏命令；
- PMMA 尺寸宏命令；
- 空气缺陷尺寸宏命令。

---

## 4. 坐标系与物理定义

必须使用固定右手坐标系：

| 坐标轴 | 定义 |
|---|---|
| `z` | PMMA 深度方向，PMMA 前表面指向内部为 `+z` |
| `x` | 横向方向，对应准直器主要限束方向和探测面后处理坐标 |
| `y` | 准直器狭缝 / 钨板拉伸方向 |

几何关系：

```text
source and detector side: z < 0
PMMA front surface:      z = 0
PMMA interior:           z > 0
```

被探测 gamma 是从 PMMA 返回 `z < 0`，并穿越探测平面的 primary gamma。

---

## 5. 固定几何参数

除非 `docs/spec.md` 更新，不得修改以下常量。

### PMMA

```text
material: G4_PLEXIGLASS
size:     200 mm × 200 mm × 65 mm
center:   (0, 0, 32.5 mm)
z range:  [0, 65] mm
```

### 空气缺陷

```text
material: G4_AIR
shape:    cylinder
radius:   5 mm
length:   10 mm
axis:     z
center:   (0, 0, 55 mm)
z range:  [50, 60] mm
```

空气缺陷作为 PMMA 的 daughter volume，不使用 Boolean subtraction。

### 源

```text
particle: gamma
position: (0, 0, -185 mm)
beam:     target-plane disk sampling
plane:    z = 0 mm
spot:     radius 1.5 mm
```

### 探测平面

```text
z = -73 mm
original x = [53, 161] mm
mirror   x = [-161, -53] mm
y = [-50, 50] mm
```

探测器是理想计数平面。可视化辅助体不能被实现为真实 detector response 或 sensitive detector。

---

## 6. 准直器约束

准直器由外部 CSV 定义。

```csv
profile_id,jaw_id,vertex_id,x_mm,z_mm
```

约束：

- 每个 profile 必须包含 `jaw_0`、`jaw_1` 和 `jaw_2`；
- 每个 jaw 是凸多边形，至少有 3 个顶点；
- `vertex_id` 必须为 `0..N-1` 连续整数，不得缺失或重复；
- `x_mm` 和 `z_mm` 是全局坐标；
- 不得额外叠加 `collimator_center_z`；
- 不需要检查 `z_mm` 是否位于 `[-28, -20] mm`；
- 非法 profile 必须 fail fast，不得静默修复。

每块 jaw 必须使用 `G4ExtrudedSolid` 构建。

坐标映射：

| 输入物理坐标 | `G4ExtrudedSolid` local 坐标 |
|---|---|
| global `x` | local `x` |
| global `z` | local `y` |
| global `y` | local `z` extrusion direction |

挤出方向对应全局 `y`，总长度 `120 mm`，即 `y = [-60, 60] mm`。

程序必须同时构建原始准直器和关于 `x = 0` 镜像的准直器。镜像 jaw 使用 `x' = -x, z' = z`，不得改变 CSV 坐标语义。

---

## 7. 物理过程约束

必须使用：

```cpp
G4EmLivermorePhysics
```

全局 production cut：

```text
0.1 mm
```

只统计 primary gamma 在 PMMA 内发生的：

```text
compt
Rayl
```

不得统计：

- photoelectric effect；
- tungsten collimator 内相互作用；
- air defect 内相互作用；
- World 内相互作用；
- secondary gamma 或其他 secondary particle 相互作用。

primary gamma 判断条件：

```text
particle_name == gamma
track_id == 1
parent_id == 0
```

---

## 8. 输出规则

### 事件定义

```text
1 event = 1 primary gamma
1 CSV row = 1 detected primary gamma
```

未到达探测面的 event 不输出。

即使 `scatter_count_total = 0`，只要 primary gamma 到达探测面并落在探测器边界内，也应输出。
探测命中可来自原始探测器或镜像探测器；CSV schema 不变，镜像探测器命中时 `det_x` 保留负的全局 x 坐标。

### 多重散射定义

```text
is_multiple_scatter = scatter_count_total >= 2
```

若没有 PMMA 内散射，first / last scatter position 输出 `NaN`。

### CSV 单位

| 类型 | 单位 |
|---|---|
| 长度 | mm |
| 能量 | keV |

不得在 CSV 字段名中新增单位后缀，除非 `docs/spec.md` 更新。

---

## 9. CSV schema

### compact header

```csv
initial_energy,det_x,det_y,det_energy,scatter_count_total,compton_count,rayleigh_count,is_multiple_scatter,first_scatter_x,first_scatter_y,first_scatter_z,last_scatter_x,last_scatter_y,last_scatter_z
```

### debug header

```csv
event_id,track_id,parent_id,det_z,det_dir_x,det_dir_y,det_dir_z,initial_energy,initial_dir_x,initial_dir_y,initial_dir_z,det_x,det_y,det_energy,scatter_count_total,compton_count,rayleigh_count,is_multiple_scatter,first_scatter_x,first_scatter_y,first_scatter_z,last_scatter_x,last_scatter_y,last_scatter_z
```

compact header 不得更改。debug header 仅按 `docs/spec.md` 的明确修订更新。

不得新增、删除、重排字段。

run-level 元数据应写入文件名，不写入每一行 CSV。

---

## 10. 输出模式与多线程规则

`/output/debug` 需要区分：

- 用户未显式设置；
- 用户显式设置 `true`；
- 用户显式设置 `false`。

推荐实现：

```cpp
std::optional<bool> debug_override = std::nullopt;
```

默认解析规则：

| 情况 | 输出模式 |
|---|---|
| 单线程且未显式设置 `/output/debug` | debug |
| 多线程且未显式设置 `/output/debug` | compact |
| 显式设置 `/output/debug true` | debug |
| 显式设置 `/output/debug false` | compact |

多线程输出必须使用：

```text
worker thread CSV files + master merge
```

禁止多个 worker threads 共享同一个 `std::ofstream`。

compact 模式下，合并成功后删除对应临时 CSV。debug 模式下，合并成功后保留对应临时 CSV。合并失败时保留所有临时文件并报错。

---

## 11. 必须支持的宏命令

```text
/geometry/collimatorProfileFile data/collimator_profiles.csv
/geometry/collimatorProfileId P001
/geometry/enableCollimator true
/geometry/enableAirDefect true

/source/energyMode mono
/source/monoEnergy 160 keV
/source/spectrumFile data/spectrum.csv

/run/randomSeed 12345
/run/numberOfThreads 8

/output/directory results
/output/debug false
```

不得改名。不得新增第一版范围外的几何宏命令。`/geometry/enableCollimator false` 时不得读取 collimator profile，也不得构建 tungsten jaw。

---

## 12. 模块边界

应保持以下职责分离：

| 模块 | 职责 |
|---|---|
| `DetectorConstruction` | 构建 World、PMMA、空气缺陷、探测面可视化辅助体，并按配置调用准直器构建模块 |
| `CollimatorProfileReader` | 读取并验证 collimator profile CSV |
| `CollimatorBuilder` | 将已验证 profile 转换为 Geant4 tungsten jaw 几何 |
| `PhysicsList` | 注册 Livermore EM physics 和 production cut |
| `PrimaryGeneratorAction` | 每个 event 生成一个 primary gamma |
| `SpectrumSampler` | 读取 spectrum CSV 并按 CDF 采样能量 |
| `EventAction` | 保存单个 event 的初始能量、散射摘要和探测命中信息 |
| `SteppingAction` | 判断 PMMA 内散射和探测平面穿越 |
| `CsvWriter` | 写 CSV、管理 thread-local 文件、执行合并 |
| `RunAction` | 管理 seed、输出模式、文件命名、writer 生命周期和 run-end merge |
| `SimulationConfig` | 保存运行配置 |
| `SimulationMessenger` | 提供宏命令接口 |

禁止把 CSV 写入逻辑放进 `SteppingAction`。禁止把 profile CSV 解析逻辑直接塞进 `CollimatorBuilder`。

---

## 13. 里程碑执行规则

按 `docs/milestones.md` 分阶段实现。

Codex 每次只能实现用户指定的一个 milestone。不得主动实现后续 milestone。

每次完成后必须总结：

```text
- changed files
- implemented behavior
- build/test commands used or recommended
- intentionally deferred work
```

如果发现前一 milestone 的实现有问题，应先说明问题，再进行最小必要修改。

---

## 14. 构建与运行命令

典型构建命令：

```bash
mkdir -p build
cd build
cmake ..
make -j
```

单线程测试：

```bash
./MSS macros/run.mac
```

多线程测试：

```bash
./MSS macros/run_mt.mac
```

可视化测试：

```bash
./MSS macros/vis.mac
```

若实际运行目录要求从 repository root 调用，应在 README 中明确说明。

---

## 15. Git 与生成文件规则

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
data/collimator_profiles.csv
data/spectrum.csv
macros/*.mac
```

`data/collimator_profiles.csv` 和 `data/spectrum.csv` 若只是占位数据，必须在 README 或注释中明确标注为 placeholder。

---

## 16. Codex 输出要求

修改代码时：

- 保持改动最小；
- 不要重排无关代码；
- 不要格式化整个仓库；
- 不要改动 compact CSV schema；debug CSV schema 只能随 `docs/spec.md` 明确修订；
- 不要改变物理常量；
- 不要把中文文档翻译成英文，除非用户明确要求；
- 类名、文件名、宏命令、CSV 字段名保持英文；
- 说明文字和文档可以使用中文。

如果遇到歧义：

1. 先查 `docs/spec.md`；
2. 再查 `docs/decisions.md`；
3. 若仍无法判断，暂停并列出阻塞点；
4. 不要自行扩大第一版范围。
