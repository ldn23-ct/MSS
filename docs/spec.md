# Geant4 背散射仿真项目规格书

## 0. 项目基本信息

| 项目 | 内容 |
|---|---|
| 项目名称 | BackscatterSim |
| 仿真类型 | gamma 背散射 Geant4 仿真 |
| Geant4 版本 | 11.2.0 |
| 操作系统 | Ubuntu 24.04 |
| 编译器 | Ubuntu 24.04 系统默认 GCC |
| 构建系统 | CMake |
| C++ 标准 | C++17 |
| 输出格式 | CSV |
| 主要用途 | 支持准直器开口 / 轮廓变化下的多重散射统计分析 |
| 主要使用者 | 用户本人 + Codex 代码生成系统 |

---

## 1. 项目目标

本项目用于搭建一个可运行、可调参、可扩展的 Geant4 背散射仿真程序。

核心目标是：

> 在背散射几何下，研究不同准直器轮廓 / 开口条件下，到达探测器的 primary gamma 中，PMMA 内 Compton / Rayleigh 多重散射计数占比及其空间分布。

第一阶段不进行图像重建，不进行真实探测器响应建模，仅生成可用于后处理分析的事件级 CSV 数据。

---

## 2. 坐标系定义

采用右手坐标系。

| 坐标轴 | 定义 |
|---|---|
| z 轴 | PMMA 模体深度方向；PMMA 前表面指向内部为 +z |
| x 轴 | 横向方向；对应准直器主要限束方向；也对应探测面上的后处理像素划分方向 |
| y 轴 | 准直器狭缝 / 钨板拉伸方向；本项目中不是主要分析维度 |

背散射几何关系：

```text
source and detector side: z < 0
PMMA front surface:      z = 0
PMMA interior:           z > 0
```

入射 gamma 从 `z < 0` 区域射向 PMMA，初始方向大体沿 `+z`。被探测 gamma 是在 PMMA 内发生散射后返回 `z < 0` 区域，并穿过探测面边界的 primary gamma。

---

## 3. 几何系统

### 3.1 World

| 参数 | 数值 |
|---|---:|
| 形状 | 立方体 |
| 尺寸 | 1000 mm × 1000 mm × 1000 mm |
| 中心 | `(0, 0, 0)` |
| x 范围 | `[-500, 500] mm` |
| y 范围 | `[-500, 500] mm` |
| z 范围 | `[-500, 500] mm` |
| 材料 | `G4_Galactic` |

World 材料使用 Geant4 NIST 内置真空材料：

```cpp
G4Material* worldMat = nist->FindOrBuildMaterial("G4_Galactic");
```

---

### 3.2 PMMA 模体

| 参数 | 数值 |
|---|---:|
| 材料 | `G4_PLEXIGLASS` |
| 形状 | 长方体 |
| x 尺寸 | 200 mm |
| y 尺寸 | 200 mm |
| z 厚度 | 65 mm |
| 前表面中心 | `(0, 0, 0)` |
| 模体中心 | `(0, 0, 32.5 mm)` |
| x 范围 | `[-100, 100] mm` |
| y 范围 | `[-100, 100] mm` |
| z 范围 | `[0, 65] mm` |

材料定义：

```cpp
G4Material* pmmaMat = nist->FindOrBuildMaterial("G4_PLEXIGLASS");
```

---

### 3.3 空气缺陷

空气缺陷用于模拟 PMMA 内部圆柱空气孔。

| 参数 | 数值 |
|---|---:|
| 材料 | `G4_AIR` |
| 形状 | 圆柱体 |
| 半径 | 5 mm |
| 直径 | 10 mm |
| 长度 | 10 mm |
| 轴向 | z 轴 |
| 中心 | `(0, 0, 55 mm)` |
| z 范围 | `[50, 60] mm` |

实现方式：

```text
World
└── PMMA box
    └── Air cylinder defect
```

即空气圆柱作为 PMMA 的 daughter volume 放入 PMMA 内部，不使用布尔减法。

Geant4 固体可使用：

```cpp
G4Tubs(
    "AirDefectSolid",
    0.0,
    5.0 * mm,
    5.0 * mm,
    0.0,
    360.0 * deg
);
```

空气缺陷支持宏命令开关：

```text
/geometry/enableAirDefect true
/geometry/enableAirDefect false
```

| 值 | 行为 |
|---|---|
| `true` | 构建空气圆柱缺陷 |
| `false` | 构建均匀 PMMA 模体 |

---

### 3.4 源几何

| 参数 | 数值 |
|---|---:|
| 源类型 | 点源 |
| 粒子类型 | gamma |
| 源位置 | `(0, 0, -185 mm)` |
| 束型 | 锥束 |
| 源准直器 | 不模拟 |
| 目标平面 | PMMA 前表面，`z = 0 mm` |
| 束斑形状 | 圆形 |
| 束斑直径 | 3 mm |
| 束斑半径 | 1.5 mm |

锥束采用目标平面采样法：

1. 在 `z = 0 mm` 平面内，以 `(0,0,0)` 为中心、半径 `1.5 mm` 的圆盘内均匀采样目标点：

```text
(x_target, y_target, 0)
```

2. primary gamma 初始方向为：

```text
normalize((x_target, y_target, 0) - (0, 0, -185))
```

源几何第一版固定写入代码，不提供宏命令修改。

---

### 3.5 探测器

探测器为理想计数面，不模拟真实探测器材料响应。

| 参数 | 数值 |
|---|---:|
| 类型 | 理想探测平面 |
| 探测面 z | `-73 mm` |
| x 边界 | `[53, 161] mm` |
| y 边界 | `[-50, 50] mm` |
| 是否分条带 | 否 |
| 是否真实模拟探测器材料 | 否 |

探测器边界第一版固定写入代码，不提供宏命令修改。

建议代码中集中定义：

```cpp
struct DetectorPlaneConfig {
    double z_mm = -73.0;
    double x_min_mm = 53.0;
    double x_max_mm = 161.0;
    double y_min_mm = -50.0;
    double y_max_mm = 50.0;
};
```

记录条件：

```text
particle == gamma
track_id == 1
parent_id == 0
preStep.z > detector_z
postStep.z <= detector_z
direction.z < 0
crossing point inside detector x-y bounds
```

穿越点使用 step 前后点线性插值得到。

---

## 4. 准直器几何

### 4.1 总体定义

准直器采用真实钨材料几何体，由两块凸五边形钨板组成。

| 项目 | 设定 |
|---|---|
| 材料 | `G4_W` |
| 钨板数量 | 2 |
| 每块钨板截面 | x-z 平面内凸五边形 |
| 每块钨板顶点数 | 5 |
| 拉伸方向 | 全局 y 方向 |
| y 尺寸 | 120 mm |
| y 范围 | `[-60, 60] mm` |
| 准直器开口 | 由两块钨板之间的空隙自然形成 |

材料定义：

```cpp
G4Material* tungstenMat = nist->FindOrBuildMaterial("G4_W");
```

---

### 4.2 外部 profile 文件

准直器几何由外部 CSV 文件定义。

文件内包含多组 profile。每一组 profile 对应一次仿真可选用的准直器几何。

每个 profile 包含：

| 项目 | 数量 |
|---|---:|
| profile ID | 1 |
| 钨板 | 2 |
| 每块钨板顶点 | 5 |
| 每个顶点坐标 | `(x_mm, z_mm)` |

CSV 格式：

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

字段定义：

| 字段 | 要求 |
|---|---|
| `profile_id` | 准直器数据组 ID，例如 `P001` |
| `jaw_id` | `jaw_0` 或 `jaw_1` |
| `vertex_id` | `0,1,2,3,4` |
| `x_mm` | 顶点 x 坐标，单位 mm |
| `z_mm` | 顶点 z 坐标，单位 mm |

注意：

- 外部文件中的 `x_mm` 和 `z_mm` 是全局坐标。
- 程序不额外叠加 `collimator_center_z`。
- 程序不检查 z 坐标是否落在 `[-28, -20] mm`。
- 外部文件完全决定准直器在 z 方向的位置和厚度。

---

### 4.3 profile 选择方式

第一版只实现单组选择：

```text
/geometry/collimatorProfileFile data/collimator_profiles.csv
/geometry/collimatorProfileId P001
```

暂不在程序内部自动遍历全部 profile。后续可通过 shell 脚本或程序扩展实现批量 profile 扫描。

---

### 4.4 profile 错误处理

如果出现以下情况，程序必须报错并停止：

| 错误类型 | 行为 |
|---|---|
| 找不到指定 `profile_id` | 停止 |
| 指定 profile 中不是 2 块钨板 | 停止 |
| 某块钨板顶点数不是 5 | 停止 |
| `vertex_id` 缺失或重复 | 停止 |
| 坐标为空、非数值、NaN、Inf | 停止 |
| 多边形面积为 0 | 停止 |
| 五边形非凸 | 停止 |

---

### 4.5 Geant4 实现方式

每块钨板使用 `G4ExtrudedSolid` 构建。

输入文件中的点为全局 x-z 坐标：

```text
(x_mm, z_mm)
```

`G4ExtrudedSolid` 的二维截面默认位于 local x-y 平面，拉伸方向为 local z。需要做坐标映射：

| 输入物理量 | G4ExtrudedSolid local 坐标 |
|---|---|
| global x | local x |
| global z | local y |
| global y | local z 拉伸方向 |

构建后需要旋转，使 local z 拉伸方向对应 global y 方向。可采用：

```text
local x -> global x
local y -> global z
local z -> global -y
```

这等价于绕 x 轴旋转 `+90 deg`。由于钨板沿 y 方向对称拉伸，local z 对应 global +y 或 -y 在几何覆盖上等价。

---

### 4.6 占位 profile

项目需要提供占位 profile，用于代码编译、可视化、输出流程测试。

占位 profile 不代表真实准直器几何。后续真实顶点确定后应替换。

建议 `data/collimator_profiles.csv` 中包含 `P001`：

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

---

## 5. 物理过程与 Physics List

### 5.1 Physics List

使用：

```cpp
G4EmLivermorePhysics
```

理由：本项目关注低能 gamma 在 PMMA 中的 Compton / Rayleigh 散射，Livermore 低能电磁模型适合该能区，并包含 Rayleigh 散射。

### 5.2 Production Cut

采用全局统一 production cut：

```text
0.1 mm
```

实现示例：

```cpp
SetDefaultCutValue(0.1 * mm);
```

---

## 6. Primary Generator

### 6.1 Event 定义

```text
1 event = 1 primary gamma
```

因此：

```text
/run/beamOn N
```

表示模拟 `N` 个入射 gamma。

### 6.2 能量模式

支持两种能量模式。

#### 单能模式

默认单能：

```text
160 keV
```

宏命令：

```text
/source/energyMode mono
/source/monoEnergy 160 keV
```

#### 能谱模式

宏命令：

```text
/source/energyMode spectrum
/source/spectrumFile data/spectrum.csv
```

能谱 CSV 格式：

```csv
energy_keV,weight
40,0.01
45,0.03
50,0.06
```

采样规则：

1. 读取 `energy_keV` 和 `weight`。
2. 将 `weight` 归一化。
3. 构造累积分布函数。
4. 每个 event 随机采样一个 primary gamma 初始能量。

---

## 7. 散射追踪逻辑

### 7.1 追踪对象

只追踪 primary gamma：

```text
particle_name == gamma
track_id == 1
parent_id == 0
```

非 primary gamma 不参与 PMMA 内散射历史统计。

### 7.2 统计范围

只统计 primary gamma 在 PMMA 内发生的散射。

| 过程 | 是否计入 |
|---|---|
| Compton scattering | 是 |
| Rayleigh scattering | 是 |
| Photoelectric effect | 否 |
| 准直器内相互作用 | 否 |
| 空气 / World 中相互作用 | 否 |

建议通过 Geant4 process name 判断：

```cpp
processName == "compt" || processName == "Rayl"
```

同时要求 step 所在体积或 interaction point 位于 PMMA 内。

### 7.3 散射位置定义

若某一步末端发生 Compton 或 Rayleigh 散射，则散射位置取：

```cpp
step->GetPostStepPoint()->GetPosition()
```

### 7.4 记录变量

对每个 primary gamma event 记录：

| 字段 | 含义 |
|---|---|
| `scatter_count_total` | PMMA 内 Compton + Rayleigh 总次数 |
| `compton_count` | PMMA 内 Compton 次数 |
| `rayleigh_count` | PMMA 内 Rayleigh 次数 |
| `first_scatter_x/y/z` | PMMA 内第一次散射位置 |
| `last_scatter_x/y/z` | PMMA 内最后一次散射位置 |

多重散射定义：

```text
is_multiple_scatter = scatter_count_total >= 2
```

若 `scatter_count_total = 0`：

```text
first_scatter_x/y/z = NaN
last_scatter_x/y/z = NaN
is_multiple_scatter = 0
```

---

## 8. 探测记录逻辑

### 8.1 输出对象

CSV 只输出到达探测器的 primary gamma。

不输出：

```text
未到达探测器的 event
非 primary gamma
非 gamma 粒子
```

即使 `scatter_count_total = 0`，只要 primary gamma 到达探测面并落在探测器边界内，也应输出。

### 8.2 探测面穿越条件

探测面：

```text
z = -73 mm
```

穿越方向：

```text
preStep.z > detector_z
postStep.z <= detector_z
direction.z < 0
```

边界条件：

```text
53 mm <= det_x <= 161 mm
-50 mm <= det_y <= 50 mm
```

穿越点通过 step 前后位置线性插值得到。

---

## 9. CSV 输出规格

### 9.1 单位约定

CSV 字段名不强制写单位后缀。

统一约定：

| 类型 | 默认单位 |
|---|---|
| 长度 | mm |
| 能量 | keV |

---

### 9.2 输出模式

程序支持两种输出模式。

| 模式 | 默认场景 | 用途 |
|---|---|---|
| debug | 单线程默认 | 检查事件、轨迹、散射绑定是否正确 |
| compact | 多线程默认 | 正式统计分析 |

宏命令：

```text
/output/debug true
/output/debug false
```

### 9.3 compact CSV 字段

每一行表示一个到达探测器的 primary gamma。

```csv
initial_energy,det_x,det_y,det_energy,scatter_count_total,compton_count,rayleigh_count,is_multiple_scatter,first_scatter_x,first_scatter_y,first_scatter_z,last_scatter_x,last_scatter_y,last_scatter_z
```

字段含义：

| 字段 | 含义 |
|---|---|
| `initial_energy` | 入射 primary gamma 初始能量 |
| `det_x` | 探测面穿越点 x |
| `det_y` | 探测面穿越点 y |
| `det_energy` | 到达探测面时 gamma 能量 |
| `scatter_count_total` | PMMA 内 Compton + Rayleigh 总次数 |
| `compton_count` | PMMA 内 Compton 次数 |
| `rayleigh_count` | PMMA 内 Rayleigh 次数 |
| `is_multiple_scatter` | 是否多重散射，`scatter_count_total >= 2` |
| `first_scatter_x/y/z` | PMMA 内第一次散射位置 |
| `last_scatter_x/y/z` | PMMA 内最后一次散射位置 |

### 9.4 debug CSV 字段

debug 模式在 compact 字段前增加：

```csv
event_id,track_id,parent_id,det_z,det_dir_x,det_dir_y,det_dir_z
```

完整字段：

```csv
event_id,track_id,parent_id,det_z,det_dir_x,det_dir_y,det_dir_z,initial_energy,det_x,det_y,det_energy,scatter_count_total,compton_count,rayleigh_count,is_multiple_scatter,first_scatter_x,first_scatter_y,first_scatter_z,last_scatter_x,last_scatter_y,last_scatter_z
```

---

## 10. 输出文件与多线程

### 10.1 输出目录

支持宏命令设置输出目录：

```text
/output/directory results
```

默认：

```text
results/
```

若输出目录不存在，程序应自动创建。若创建失败，应报错并停止。

线程临时文件放在：

```text
results/tmp/
```

---

### 10.2 文件命名

由于 CSV 内不记录 profile、energy mode、seed，这些信息必须体现在文件名中。

#### 单能 compact

```text
results/hits_profile_{profile_id}_mono_{energy}keV_seed{seed}.csv
```

示例：

```text
results/hits_profile_P001_mono_160keV_seed12345.csv
```

#### 单能 debug

```text
results/hits_profile_{profile_id}_mono_{energy}keV_seed{seed}_debug.csv
```

#### 能谱 compact

```text
results/hits_profile_{profile_id}_spectrum_seed{seed}.csv
```

#### 能谱 debug

```text
results/hits_profile_{profile_id}_spectrum_seed{seed}_debug.csv
```

---

### 10.3 多线程输出策略

采用 M1：每个 worker 线程写独立 CSV，run 结束后由 master 合并。

规则：

1. 每个线程只写自己的临时 CSV。
2. 不允许多个线程共享同一个 `std::ofstream`。
3. run 结束后由 master 合并所有线程文件。
4. 合并时只保留一个 header。
5. compact 模式下，合并成功后删除线程临时文件。
6. debug 模式下，合并成功后保留线程临时文件。
7. 合并失败时，保留所有临时文件并报错。

临时文件命名示例：

```text
results/tmp/hits_profile_P001_mono_160keV_seed12345_thread0.csv
results/tmp/hits_profile_P001_mono_160keV_seed12345_thread1.csv
```

Debug 模式：

```text
results/tmp/hits_profile_P001_mono_160keV_seed12345_debug_thread0.csv
```

---

## 11. 随机种子与线程

支持宏命令设置随机种子：

```text
/run/randomSeed 12345
```

支持宏命令设置线程数：

```text
/run/numberOfThreads 8
```

默认规则：

| 运行模式 | 默认输出模式 |
|---|---|
| 单线程 | debug |
| 多线程 | compact |

建议使用 Geant4 run manager factory，避免写死单线程或多线程：

```cpp
auto* runManager = G4RunManagerFactory::CreateRunManager(G4RunManagerType::Default);
```

---

## 12. 宏命令接口

第一版需要支持以下宏命令：

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

宏命令含义：

| 命令 | 作用 |
|---|---|
| `/geometry/collimatorProfileFile` | 指定准直器轮廓 CSV |
| `/geometry/collimatorProfileId` | 指定本次使用的数据组 |
| `/geometry/enableAirDefect` | 控制空气缺陷是否启用 |
| `/source/energyMode` | `mono` 或 `spectrum` |
| `/source/monoEnergy` | 单能模式能量，默认 `160 keV` |
| `/source/spectrumFile` | 能谱 CSV 文件 |
| `/run/randomSeed` | 设置随机种子 |
| `/run/numberOfThreads` | 设置线程数 |
| `/output/directory` | 输出目录，默认 `results/` |
| `/output/debug` | 是否启用 debug 输出 |

---

## 13. 项目代码结构

建议项目结构：

```text
BackscatterSim/
├── CMakeLists.txt
├── README.md
├── include/
│   ├── DetectorConstruction.hh
│   ├── PhysicsList.hh
│   ├── PrimaryGeneratorAction.hh
│   ├── RunAction.hh
│   ├── EventAction.hh
│   ├── SteppingAction.hh
│   ├── CollimatorProfileReader.hh
│   ├── CollimatorBuilder.hh
│   ├── SpectrumSampler.hh
│   └── CsvWriter.hh
├── src/
│   ├── DetectorConstruction.cc
│   ├── PhysicsList.cc
│   ├── PrimaryGeneratorAction.cc
│   ├── RunAction.cc
│   ├── EventAction.cc
│   ├── SteppingAction.cc
│   ├── CollimatorProfileReader.cc
│   ├── CollimatorBuilder.cc
│   ├── SpectrumSampler.cc
│   └── CsvWriter.cc
├── macros/
│   ├── vis.mac
│   ├── run.mac
│   └── run_mt.mac
├── data/
│   ├── collimator_profiles.csv
│   └── spectrum.csv
└── results/
```

---

## 14. 推荐核心类职责

### 14.1 `DetectorConstruction`

职责：

- 构建 World。
- 构建 PMMA 模体。
- 根据 `/geometry/enableAirDefect` 构建或不构建空气缺陷。
- 调用 `CollimatorProfileReader` 和 `CollimatorBuilder` 构建准直器。
- 构建用于可视化的探测面辅助几何。
- 保存探测器边界配置，供 `SteppingAction` 使用。

### 14.2 `CollimatorProfileReader`

职责：

- 读取外部 CSV。
- 筛选指定 `profile_id`。
- 检查 jaw 数量、顶点数量、顶点 ID、坐标合法性、面积、凸性。
- 返回 `CollimatorProfile`。

建议数据结构：

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

### 14.3 `CollimatorBuilder`

职责：

- 将 `CollimatorProfile` 转换为 Geant4 几何。
- 使用 `G4ExtrudedSolid` 构建每块凸五边形钨板。
- 沿全局 y 方向拉伸 120 mm。

### 14.4 `PrimaryGeneratorAction`

职责：

- 每个 event 发射一个 primary gamma。
- 支持 mono / spectrum 两种能量模式。
- 根据目标平面采样法生成锥束方向。
- 将当前 event 的初始能量传递给 `EventAction`。

### 14.5 `SpectrumSampler`

职责：

- 读取能谱 CSV。
- 检查 `energy_keV` 和 `weight` 合法性。
- 构建 CDF。
- 每个 event 随机采样能量。

### 14.6 `EventAction`

职责：

- 在 event 开始时初始化当前 primary gamma 的散射摘要。
- 保存初始能量。
- 保存 first / last scatter 位置和散射计数。
- 保存 detector crossing 记录。
- event 结束时，如果 primary gamma 被探测到，则调用 `CsvWriter` 写一行。

### 14.7 `SteppingAction`

职责：

- 对每个 step 判断是否是 primary gamma。
- 判断 PMMA 内 Compton / Rayleigh 散射。
- 更新散射计数、第一次散射位置和最后一次散射位置。
- 判断是否穿过探测面，并计算穿越点。
- 若穿越点在探测器边界内，则记录探测信息。

### 14.8 `CsvWriter`

职责：

- 根据 debug / compact 模式生成 header。
- 每线程写独立临时 CSV。
- run 结束时由 master 合并文件。
- 根据模式决定是否删除线程临时文件。
- 自动创建输出目录和 `tmp/` 目录。

### 14.9 `RunAction`

职责：

- 初始化随机种子。
- 初始化输出文件名。
- 管理 run 开始 / 结束时的 CSV writer 生命周期。
- 在 run 结束时触发多线程临时文件合并。

---

## 15. 宏文件要求

### 15.1 `macros/run.mac`

用途：单线程最小测试。

应包含：

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

预期输出：

```text
results/hits_profile_P001_mono_160keV_seed12345_debug.csv
```

---

### 15.2 `macros/run_mt.mac`

用途：多线程正式运行测试。

应包含：

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

预期输出：

```text
results/hits_profile_P001_mono_160keV_seed12345.csv
```

compact 模式下，合并成功后应删除 `results/tmp/` 中对应线程临时 CSV。

---

### 15.3 `macros/vis.mac`

用途：几何与轨迹可视化。

应支持检查：

- PMMA 模体位置与尺寸。
- 空气缺陷开关。
- 准直器两块五边形钨板。
- 探测面位置和范围。
- 源位置。
- 少量 gamma 轨迹。

---

## 16. README.md 要求

README.md 至少包含：

1. 项目简介。
2. 软件环境：Geant4 11.2.0、Ubuntu 24.04、CMake、GCC。
3. 编译方式：

```bash
mkdir build
cd build
cmake ..
make -j
```

4. 单线程测试运行方式：

```bash
./BackscatterSim macros/run.mac
```

5. 多线程运行方式：

```bash
./BackscatterSim macros/run_mt.mac
```

6. 可视化运行方式：

```bash
./BackscatterSim macros/vis.mac
```

7. 宏命令说明。
8. 准直器 profile CSV 格式。
9. 能谱 CSV 格式。
10. 输出 CSV 字段说明。
11. Debug / compact 模式区别。
12. 占位准直器 profile 的说明：仅用于测试，不代表真实准直器几何。

---

## 17. 验收标准

### 17.1 几何可视化验收

`vis.mac` 应能显示：

| 对象 | 验收要求 |
|---|---|
| PMMA 模体 | 可见，位置为 `z=[0,65] mm` |
| 空气缺陷 | 开启时可见，关闭时不存在 |
| 准直器 | 从外部 CSV 指定 profile 正确生成两块凸五边形钨板 |
| 探测面 | 可见，位置为 `z=-73 mm`，范围为 `x=[53,161] mm, y=[-50,50] mm` |
| 源位置 | 位于 `(0,0,-185 mm)` |
| 少量粒子轨迹 | 可用于检查锥束方向和背散射路径 |

### 17.2 最小运行测试

命令：

```bash
./BackscatterSim macros/run.mac
```

要求：

- 程序正常结束。
- 生成 debug CSV：

```text
results/hits_profile_P001_mono_160keV_seed12345_debug.csv
```

- CSV header 与 debug 字段定义一致。

### 17.3 多线程运行测试

命令：

```bash
./BackscatterSim macros/run_mt.mac
```

要求：

- 程序正常结束。
- 生成 compact CSV：

```text
results/hits_profile_P001_mono_160keV_seed12345.csv
```

- compact 模式下线程临时文件合并成功后自动删除。
- CSV header 与 compact 字段定义一致。

### 17.4 错误 profile 测试

程序必须对以下错误明确报错并停止：

| 错误 | 期望行为 |
|---|---|
| 找不到 profile_id | 停止 |
| 某个 jaw 少于 5 个顶点 | 停止 |
| vertex_id 重复 | 停止 |
| 五边形非凸 | 停止 |
| 坐标非数值 | 停止 |

---

## 18. 第一版不包含的内容

第一版不要求实现：

- 图像重建。
- 真实探测器材料响应。
- 探测器能量沉积统计。
- 自动遍历所有准直器 profile。
- 所有散射点完整轨迹输出。
- 源位置和探测器边界宏命令调节。
- 准直器真实顶点坐标生成逻辑。

这些可作为后续版本扩展。

---

## 19. 当前 ToDo

| ToDo | 说明 |
|---|---|
| 真实准直器 profile | 需要后续填写真实两块凸五边形钨板顶点坐标 |
| 能谱文件 | 若使用 spectrum 模式，需要提供真实能谱 CSV |
| 后处理脚本 | 可后续补充 Python 分析脚本，用于统计多重散射占比、能谱分布、探测面 x 分布 |
| profile 批处理 | 后续可扩展为遍历多个 profile 自动运行 |

---

## 20. 规格闭合状态

当前规格已经闭合到可以指导 Codex 生成第一版 Geant4 项目代码。

关键已定项：

- 背散射几何。
- PMMA、空气缺陷、源、探测器、准直器定义。
- 准直器外部 CSV 输入。
- 单能 / 能谱模式。
- primary gamma 散射历史统计。
- 只输出到达探测器的 primary gamma。
- 单线程 debug、多线程 compact。
- 多线程每线程临时 CSV + master 合并。
- Ubuntu 24.04 + Geant4 11.2.0 + CMake + C++17。

