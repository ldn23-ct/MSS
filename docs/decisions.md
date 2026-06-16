# 第二版设计决策记录

## 1. 文档目的

本文档记录第二版车辆侧向背散射 ROI 仿真项目中已经接受的关键设计决策，用于约束后续规格、架构、里程碑、验收清单和代码实现，避免在实现过程中发生设计漂移。

本文档不替代 `spec.md`。功能需求、字段定义、配置格式、物理参数、验收条件仍以 `spec.md` 为最高依据。

文档优先级：

1. `spec.md`
2. `decisions.md`
3. `architecture.md`
4. `milestones.md`
5. `acceptance_checklist.md`
6. 现有代码，但前提是不与上述文档冲突

若必须修改 Accepted 决策，应先更新本文档，再同步更新规格和实现。

本修订版用于与修订后的 `spec.md` 保持一致，重点固化以下容易漂移的边界：

- YAML parser 与 CLI 入口；
- VehicleROI YAML schema 与最小可用样例；
- collimator 的 `y` 向 placement 规则；
- 正式 CSV / Debug CSV 的字段边界；
- detector-hit 事件追踪模型与 per-gamma-track scatter history；
- pose-level / scan-level 数据、summary、图表、统计指标和后处理模块留到下一轮项目迭代；
- 一个 run 对应一个 pose 和一个实际 seed；
- 固定 World 策略和输出目录已存在时的处理策略。

---

## 2. 决策状态

| 状态 | 含义 |
|---|---|
| Accepted | 已接受，当前实现必须遵守。 |
| Proposed | 提案中，尚未成为实现约束。 |
| Superseded | 已被后续决策取代。 |
| Deferred | 有价值，但明确推迟；不得在基础实现中作为必须交付项。 |

---

## 3. 决策索引

| ID | 决策 | 状态 |
|---|---|---|
| D001 | 第二版是围绕车辆侧向 ROI 的重构项目，不直接继承第一版硬规格 | Accepted |
| D002 | 主配置入口采用两个 YAML 文件 | Accepted |
| D003 | 固定车辆 ROI，移动成像头组件 | Accepted |
| D004 | 使用 `head_offset_x/y`，废弃 `vehicle_shift_x/y` | Accepted |
| D005 | pose 支持 list / grid 两种生成模式，`pose_id` 自动生成 | Accepted |
| D006 | 成像头由 Source、SlitCollimator 和 VirtualDetectorPlane 组成 | Accepted |
| D007 | 射线源采用斜入射有限焦点笔形束 | Accepted |
| D008 | 能量模式保留 mono / spectrum | Accepted |
| D009 | 狭缝准直器沿用 CSV 表头，但 jaw 数量可变且不构建镜像 | Accepted |
| D010 | 探测器为单个理想虚拟平面，不模拟真实探测器响应 | Accepted |
| D011 | 探测器位于准直器之后，采用 `negative_z` 有效穿越方向 | Accepted |
| D012 | 旧 CSV 输出语义 | Superseded |
| D013 | 正式事件级 CSV 同时服务项目摸底线和论文数据线 | Accepted |
| D014 | 输出组织采用 `events.csv` + `metadata.yaml` | Accepted |
| D015 | 事件是否进入正式输出只由 detector hit 决定，不由散射发生位置决定 | Accepted |
| D016 | 散射 region 归属使用 preStep volume | Accepted |
| D017 | 车辆 ROI 几何由 YAML 构建，normal / abnormal 只替换 insert 材料和 region | Accepted |
| D018 | 使用 `G4EmLivermorePhysics`，默认 production cut 为 `0.1 mm` | Accepted |
| D019 | 多线程输出继承线程临时 CSV + master 合并策略 | Accepted |
| D020 | 本轮只输出事件级数据和 metadata，位姿级 / 扫描级与后处理留到下一轮 | Accepted |
| D021 | 样例源和探测器位置可使用第一版数值，但只作为链路验证默认值 | Accepted |
| D022 | 模块职责保持窄边界 | Accepted |
| D023 | 无效配置、非法几何、非法 profile 和输出错误必须 fail fast | Accepted |
| D024 | 第二版基础构建不包含真实探测器响应、图像重建和连续运动扫描 | Accepted |
| D025 | World 使用固定 4000 mm 立方体并进行边界检查 | Accepted |
| D026 | 一个 run 对应一个 pose 和一个实际 seed，可在 run 内使用多线程 | Accepted |
| D027 | 现有第一轮代码只允许机制级复用，不允许语义级继承 | Accepted |
| D028 | 正式 CSV 输出 detected gamma hit，debug CSV 输出 gamma track summary | Accepted |

---

## D001：第二版是围绕车辆侧向 ROI 的重构项目，不直接继承第一版硬规格

**状态：** Accepted  
**日期：** 2026-05-21

### 背景

第一版项目完成了基础背散射 Geant4 链路验证，包括源、准直器、简单模体、探测面、事件级 CSV 和多线程输出。第二版研究对象已经转为车辆侧向 ROI 成像摸底和多重散射统计分析。

### 决策

第二版不是第一版的小修补。第一版文件、代码和文档只作为历史参考。

第二版的几何对象、扫描方式、源模型、准直器规则、探测器定义、事件字段、输出组织和配置入口均以第二版文档为准。

### 影响

- 不默认继承第一版 PMMA 模体。
- 不默认继承第一版 CSV schema。
- 不默认继承第一版镜像准直器或镜像探测器。
- 可复用第一版的项目组织经验、线程输出经验和部分样例数值。

---

## D002：主配置入口采用两个 YAML 文件

**状态：** Accepted  
**日期：** 2026-05-21

### 背景

第二版参数数量明显增加，包括车辆 ROI 几何、normal / abnormal 模型、成像头位置、扫描 pose、源、准直器、探测器、线程和输出。仅用 Geant4 macro 不利于表达嵌套结构和批量 pose。

### 决策

第二版主配置入口为：

```text
config/base/simulation_config_v2.yaml
```

该入口 YAML 负责指定运行条件，并通过字段引用车辆 ROI YAML、collimator profile CSV 和 spectrum CSV。车辆 ROI、collimator profile 和能谱样例文件均放在 `config/` 目录下，但具体文件名不作为代码硬编码约束，应由入口 YAML 明确指定。

| 配置项 | 来源 |
|---|---|
| 运行条件、pose、source、collimator、detector、physics、output、model_type | `config/base/simulation_config_v2.yaml` |
| 车辆 ROI 几何、材料、host / daughter、insert、region_id | `vehicle.geometry_file` 指定的 YAML |
| collimator profile | `collimator.profile_file` 指定的 CSV |
| spectrum | `source.spectrum_file` 指定的 CSV |

宏命令仅保留指定或切换入口 YAML 文件路径的最小能力。凡是入口 YAML 可以表达的配置项，不再新增对应 macro。

### 影响

- 需要实现 YAML 配置读取和严格验证。
- 配置错误应在 Geant4 run 前报错停止。
- 输出 metadata 应记录实际入口 YAML、车辆 ROI 文件、collimator profile 文件和 spectrum 文件。
- C++ 代码不得写死具体车辆 ROI 或 collimator profile 文件名。

---

## D003：固定车辆 ROI，移动成像头组件

**状态：** Accepted  
**日期：** 2026-05-21

### 背景

第二版关注车辆侧向 ROI 场景下成像头位姿变化引起的探测响应。若平移车辆 ROI，会破坏车辆结构在全局坐标中的解释稳定性。

### 决策

扫描组织方式为：

```text
固定车辆 ROI
+ 移动成像头组件
+ 每个 pose 独立 Monte Carlo 统计
```

车辆 ROI 在所有 pose 中保持固定。成像头组件整体按 `head_offset_x/y` 平移。

### 影响

- `VehicleROIConstruction` 不负责扫描平移。
- `ImagingHeadConstruction` 统一接收当前 pose offset。
- first / last scatter 坐标始终位于稳定的全局车辆坐标系中。

---

## D004：使用 `head_offset_x/y`，废弃 `vehicle_shift_x/y`

**状态：** Accepted  
**日期：** 2026-05-21

### 背景

早期统计文档中出现过 `vehicle_shift_x/y`，但第二版扫描原则已经明确为车辆 ROI 固定、成像头移动。

### 决策

第二版统一使用：

```text
head_offset_x_mm
head_offset_y_mm
```

废弃：

```text
vehicle_shift_x
vehicle_shift_y
```

### 影响

- `metadata.yaml` 必须使用 `head_offset_x_mm` 和 `head_offset_y_mm`。
- CSV 中不写入 `vehicle_shift_x/y`。
- 架构、里程碑和验收文档不得再使用车辆平移语义描述扫描。

---

## D005：pose 支持 list / grid 两种生成模式，`pose_id` 自动生成

**状态：** Accepted  
**日期：** 2026-05-21

### 背景

第二版需要支持手动指定若干离散偏置，也需要支持规则扫描网格。`pose_id` 若手写，容易与 offset 不一致。

### 决策

`simulation_config_v2.yaml` 中 pose 支持两种模式：

```text
list
grid
```

list mode：

```text
第 i 个 head_offset_x 与第 i 个 head_offset_y 配对。
```

grid mode：

```text
x_offsets 与 y_offsets 取笛卡尔积。
```

`pose_id` 不由用户直接设置，而是由整数 mm offset 自动生成。

编码规则：

```text
0      -> 0
正整数 -> 原始十进制数字
负整数 -> m + 绝对值
```

格式：

```text
pose_x{encoded_x}_y{encoded_y}
```

示例：

| offset | pose_id |
|---|---|
| `(0, 0)` | `pose_x0_y0` |
| `(2, 1)` | `pose_x2_y1` |
| `(-2, 1)` | `pose_xm2_y1` |
| `(1111, 0)` | `pose_x1111_y0` |

list mode 只生成成对 offset；grid mode 生成笛卡尔积。两种模式生成的 pose 均应进入同一 pose 列表结构，并由同一 `PoseRunController` 或等价模块顺序执行。

### 影响

- 第一阶段 offset 只支持整数 mm。
- 不支持小数 offset。
- list mode 中 x/y 数组长度不同必须报错。
- `pose_id` 不应由用户直接写入配置。
- CSV 中不写 `pose_id`；每个 pose 的 `pose_id` 写入对应 `metadata.yaml`。

---

## D006：成像头由 Source、SlitCollimator 和 VirtualDetectorPlane 组成

**状态：** Accepted  
**日期：** 2026-05-21

### 背景

第二版成像系统需要表达源、准直器和探测器的相对位置，并在扫描时保持相对位置不变。

### 决策

成像头为刚性组件组：

```text
ImagingHead = Source + SlitCollimator + VirtualDetectorPlane
```

成像头整体在 `x-y` 平面内平移，不旋转，不沿 `z` 方向运动。

### 影响

- source、collimator、detector 共享同一个 `head_offset`。
- 成像头内部相对位置在同一 pose 中保持不变。
- 成像头旋转、连续运动和运动模糊不属于基础构建。

---

## D007：射线源采用斜入射有限焦点笔形束

**状态：** Accepted  
**日期：** 2026-05-21

### 背景

第二版成像头不再采用第一版的点源锥束目标平面采样，而需要表达斜入射笔形束。

### 决策

每个 event 产生一个 primary gamma。源模型为：

```text
斜入射有限焦点笔形束
```

入射方向：

```text
incident_dir = (cos(theta), 0, sin(theta))
0° < theta <= 90°
```

焦点面为垂直于 `incident_dir` 的圆形平面，primary gamma 起点在该圆形焦点面内均匀采样，方向固定为 `incident_dir`。

### 影响

- 第一版锥束目标面采样不再使用。
- `source_pos_zero_mm`、`incident_theta_deg`、`focal_spot_diameter_mm` 从 YAML 读取。
- 样例值可为 `theta = 45°`、`focal_spot_diameter = 5 mm`。

---

## D008：能量模式保留 mono / spectrum

**状态：** Accepted  
**日期：** 2026-05-21

### 背景

mono 模式适合链路验证和可重复调试，spectrum 模式用于后续接入真实能谱。

### 决策

第二版继续支持：

```text
mono
spectrum
```

mono 模式使用 `mono_energy_keV`。spectrum 模式读取 `energy_keV,weight` CSV 并按权重采样。

### 影响

- 需要保留 `SpectrumSampler` 或等价模块。
- spectrum CSV 需严格验证能量和权重。
- 能量模式信息写入 `metadata.yaml`。

---

## D009：狭缝准直器沿用 CSV 表头，但 jaw 数量可变且不构建镜像

**状态：** Accepted  
**日期：** 2026-05-21

### 背景

第二版仍希望复用第一版外部 profile 文件组织方式，但斜入射破坏了第一版关于 `x=0` 的左右对称假设。

### 决策

准直器 profile 表头沿用：

```csv
profile_id,jaw_id,vertex_id,x_mm,z_mm
```

第二版规则：

```text
jaw 数量可变，M >= 1
jaw_id 必须连续为 jaw_0 ... jaw_{M-1}
每块 jaw 为凸多边形，N >= 3
不构建镜像准直器
```

CSV 中的 `x_mm,z_mm` 表示零位姿 global `x-z` 坐标。

### 影响

- 第一版固定三块 jaw 的读取逻辑需要改写。
- 第一版镜像 jaw 构建逻辑不得进入第二版。
- 可暂用第一版 `P001` 作为链路验证占位 profile。

---

## D010：探测器为单个理想虚拟平面，不模拟真实探测器响应

**状态：** Accepted  
**日期：** 2026-05-21

### 背景

当前阶段只需要采集事件级统计量，不需要真实探测器材料响应或能量沉积 scoring。

### 决策

第二版探测器为单个理想虚拟探测平面。

不包含：

- 真实探测器材料；
- sensitive detector；
- 能量沉积 scoring；
- 镜像探测器。

探测记录来自几何穿越判定。

### 影响

- `det_energy` 表示 gamma track 穿越虚拟探测平面时的能量。
- detector region mapping 和 depth mapping 留到下一轮后处理项目迭代。

---

## D011：探测器位于准直器之后，采用 `negative_z` 有效穿越方向

**状态：** Accepted  
**日期：** 2026-05-21

### 背景

第二版仍为背散射结构。探测器和准直器的相对位置按第一版链路验证关系组织：准直器夹在车辆 ROI 与探测平面之间。

### 决策

几何关系：

```text
VehicleROI
→ SlitCollimator
→ VirtualDetectorPlane
```

探测器有效穿越方向采用：

```yaml
accept_direction: negative_z
```

对应判定：

```text
preStep.z > detector_z
postStep.z <= detector_z
direction.z < 0
```

### 影响

- 探测器位置和接收范围仍由 YAML 配置。
- 样例配置可使用第一版链路验证数值。
- 同一 gamma track 只记录第一次有效 detector crossing；同一 event 内不同 gamma track 可分别形成 detected gamma hit。

---

## D012：旧 CSV 输出语义

**状态：** Superseded
**日期：** 2026-05-21
**取代：** D028

### 背景

该决策曾定义第二版早期 CSV 输出语义。随着 `spec.md` 改为 detector-hit 模型，该旧输出语义不再适用。

### 决策

本决策已被 D028 取代。当前正式 CSV / debug CSV schema、detector crossing 对象、hit 记录规则和 scatter history 语义均以 `spec.md` 与 D028 为准。

### 影响

- 实现阶段不得再依据 D012 的旧输出语义设计 `EventRecord`、`SteppingAction` 或 `CsvWriter`。

### 取代原因

真实探测器不区分 gamma 是否为 source primary。第二版事件追踪模型已从 primary-history 改为 detector-hit 模型，正式 CSV 和 debug CSV 语义由 D028 重新定义。

---

## D013：正式事件级 CSV 同时服务项目摸底线和论文数据线

**状态：** Accepted  
**日期：** 2026-05-21

### 背景

项目摸底需要探测面二维响应、能量和 first / last scatter 来源。论文数据需要散射阶次和过程计数。

### 决策

正式 `events.csv` 采用统一 schema，同时包含：

- hit、track 和 gamma 来源信息；
- 探测位置；
- 探测能量；
- 当前 gamma track 自身的 scatter_count_total；
- 当前 gamma track 自身的 compton_count；
- 当前 gamma track 自身的 rayleigh_count；
- first / last scatter 坐标；
- first / last scatter region_id。

formal CSV 保持最小事件级 schema。论文线需要的 pose-level summary、scan-level summary、多区域贡献统计、target interaction 分类等派生结果不由 Geant4 在基础实现中直接输出。

### 影响

- 不再拆分“摸底版 CSV”和“论文版 CSV”。
- 下一轮后处理可从同一个 `events.csv` 计算 A 线和 B 线指标。
- 位姿级 / 扫描级图表和指标属于下一轮后处理产物，不作为本轮 Geant4 基础程序输出。

---

## D014：输出组织采用 `events.csv` + `metadata.yaml`

**状态：** Accepted  
**日期：** 2026-05-21

### 背景

run-level 条件不应重复写入每个事件行，否则 CSV 冗余且不利于保持事件字段稳定。

### 决策

每个 pose 输出：

```text
events.csv 或 events_debug.csv
metadata.yaml
```

`metadata.yaml` 记录：

- run_id；
- model_type；
- pose_id；
- head_offset_x/y；
- n_primary；
- random_seed；
- source；
- collimator；
- detector；
- physics；
- vehicle geometry file。

### 影响

- CSV 中不重复写入 `pose_id`、`model_type`、`head_offset_x/y`。
- 下一轮后处理可通过 metadata 建立 run 条件与事件文件的关系。

---

## D015：事件是否进入正式输出只由 detector hit 决定，不由散射发生位置决定

**状态：** Accepted  
**日期：** 2026-05-21

### 背景

事件保留条件应反映探测器是否观察到 gamma track，而不是预先根据散射发生在哪种材料或 region 过滤事件。

### 决策

正式事件输出条件为：

```text
detected gamma hit
```

对于 detected gamma hit，记录该 gamma track 自身的 Compton / Rayleigh 散射历史。散射发生在哪个 region 只用于归因解释，不用于决定该 gamma track 是否输出。

### 影响

- 不使用“只统计实体车辆材料区”作为事件保留条件。
- region_id 是解释字段，不是事件筛选字段。
- `vehicle_background_air`、`cabin_air` 等 region 可以作为散射归属结果出现，若 gamma track 在相应区域发生有效 Compton / Rayleigh。

---

## D016：散射 region 归属使用 preStep volume

**状态：** Accepted  
**日期：** 2026-05-21

### 背景

Geant4 step 的 post point 可能位于边界或进入下一 volume。若用 postStep volume 做 region 归属，贴边事件容易归入下一个体积。

### 决策

散射坐标使用：

```text
postStep position
```

散射 region 归属使用：

```text
preStep volume 对应的 region_id
```

规则：

| 情况 | region 归属 |
|---|---|
| step 起点位于子 volume | 子 volume 的 region_id |
| step 起点位于 VehicleROI 空气母体 | `vehicle_background_air` |
| step 起点位于未注册区域 | `other` |
| 无有效散射 | `none` |

### 影响

- `SteppingAction` 需要同时取 postStep position 和 preStep volume。
- `RegionResolver` 必须支持 volume 到 region_id 的映射。

---

## D017：车辆 ROI 几何由 YAML 构建，normal / abnormal 只替换 insert 材料和 region

**状态：** Accepted  
**日期：** 2026-05-21

### 背景

第二版车辆 ROI 需要表达 normal / abnormal 配对，但不希望 normal 与 abnormal 几何尺寸不同，否则差异图难以解释。

### 决策

车辆 ROI 几何由 `vehicle_roi_v03.yaml` 构建。

normal / abnormal 规则：

```text
normal:
  insert material = host material
  insert region_id = host region_id

abnormal:
  selected_target_component:
    material = abnormal_material
    region_id = target
  other inserts:
    material = host material
    region_id = host region_id
```

第一阶段每个 abnormal run 只启用一个 selected target component。

`vehicle_roi_v03.yaml` 的 schema、组件清单、host / daughter 关系、insert 标记、AABB 表达、placement 规则和 overlap 元数据以 `spec.md` 的 VehicleROI 章节为准。实现阶段必须先提供最小可读样例，以免 M2 / M4 被样例文件缺失阻塞。

### 影响

- abnormal 模式下 `selected_target_component` 不能为空。
- 指定 target component 必须存在且必须是 insert。
- normal / abnormal 几何形状完全一致。
- VehicleROI reader 应验证 component name 唯一、host 存在、insert 位于唯一宿主内、region_id 非空。
- sample `vehicle_roi_v03.yaml` 应在早期里程碑提供，而不是推迟到最终整合阶段。

---

## D018：使用 `G4EmLivermorePhysics`，默认 production cut 为 `0.1 mm`

**状态：** Accepted  
**日期：** 2026-05-21

### 背景

第二版关注低能 gamma 背散射和 Compton / Rayleigh 过程统计。第一版中该物理列表已作为可用基础。

### 决策

默认使用：

```text
G4EmLivermorePhysics
```

默认 production cut：

```text
0.1 mm
```

### 影响

- `PhysicsList` 不应包含几何、输出或事件记录逻辑。
- 后续若更换 physics list，应先更新本文档和 `spec.md`。

---

## D019：多线程输出继承线程临时 CSV + master 合并策略

**状态：** Accepted  
**日期：** 2026-05-21

### 背景

Geant4 多线程中多个 worker 共享同一个输出流容易产生竞争和文件损坏。第一版已经验证线程临时 CSV + master 合并策略可行。

### 决策

第二版继承该策略：

1. 每个 worker 写独立临时 CSV；
2. worker 之间不共享 `std::ofstream`；
3. master 在 run end 合并临时 CSV；
4. 最终 CSV 只保留一个 header；
5. 正式模式合并成功后删除临时文件；
6. debug 模式合并成功后保留临时文件；
7. 合并失败时保留所有临时文件并报错。

### 影响

- `CsvWriter` 必须线程本地化。
- `RunAction` 或 `PoseRunController` 负责触发合并。
- 不允许 worker 直接写最终 CSV。

---

## D020：本轮只输出事件级数据和 metadata，位姿级 / 扫描级与后处理留到下一轮

**状态：** Accepted  
**日期：** 2026-05-21

### 背景

第二版当前项目固定为搭建 Geant4 仿真程序并输出事件级数据。位姿级数据、扫描级数据、summary、统计图、差异图、指标计算和后处理脚本不在本轮实现。

### 决策

本轮程序只输出：

```text
events.csv / events_debug.csv
metadata.yaml
```

本轮不输出：

```text
pose_summary.csv
scan_summary.csv
pose-level image
scan-level image
normal-abnormal difference image
region contribution table
```

以下内容留到下一轮后处理项目迭代：

- 二维响应图；
- normal / abnormal 差异图；
- CNR；
- detector region mapping；
- depth region mapping；
- `M_RJ`；
- `H_k`；
- `H_ms`；
- `F_ms`；
- `D_JS`；
- SVD / effective rank。

### 影响

- Geant4 不输出 detector region ID。
- Geant4 不输出 depth region ID。
- 本轮只保证事件级 CSV 与 metadata 足以支持下一轮后处理开发。
- AGENTS 或其他历史文档若提到“事件级 / 位姿级 / 扫描级输出”，在本轮项目语境中应理解为：本轮只实现事件级输出，位姿级 / 扫描级输出留到下一轮。

---

## D021：样例源和探测器位置可使用第一版数值，但只作为链路验证默认值

**状态：** Accepted  
**日期：** 2026-05-21

### 背景

第二版成像头真实几何仍可通过 YAML 调整。为了尽快完成链路验证，需要提供可运行默认值。

### 决策

样例配置可使用：

```yaml
source_pos_zero_mm: [0.0, 0.0, -185.0]
detector_z_zero_mm: -73.0
detector_x_range_zero_mm: [53.0, 161.0]
detector_y_range_zero_mm: [-50.0, 50.0]
```

这些值只作为第二版程序构建、可视化和端到端输出测试的默认样例，不是第二版最终成像头几何的不可修改物理常量。

### 影响

- 文档中必须标注这些值的样例性质。
- 后续可以只修改 YAML，不改代码。
- 实现不得将这些数值写死在 C++ 源码中。
- 端到端测试可使用这些值，但物理结论不得依赖“第一版样例值即最终成像头设计”的假设。

---

## D022：模块职责保持窄边界

**状态：** Accepted  
**日期：** 2026-05-21

### 背景

第二版模块更多，若职责不清，后续用 Codex 分阶段实现时容易出现跨模块污染。

### 决策

模块边界应保持明确：

| 模块 | 职责 |
|---|---|
| YAML reader | 读取和验证配置。 |
| Vehicle ROI construction | 构建车辆 ROI，不处理 pose offset。 |
| Imaging head construction | 构建 source 辅助体、准直器和探测器辅助体，统一应用 pose offset。 |
| Source model | 生成 primary gamma。 |
| Stepping action | 记录 gamma track 散射和探测穿越。 |
| Event action | 维护单 event 内的 per-track summary，控制 event 写出。 |
| Csv writer | 写线程本地 CSV 并合并。 |
| Metadata writer | 写 run-level metadata。 |
| DetectorConstruction / GeometryAssembly | 在 Geant4 生命周期内总装 World、VehicleROI、ImagingHead 和 virtual detector。 |
| ScanPoseManager / PoseRunController | 生成 pose 列表、应用 head_offset、调度每个 pose 的 run。 |

### 影响

- CSV 写入不放在 `SteppingAction`。
- 准直器 CSV 解析不散落在几何构建代码中。
- 后处理指标不进入本轮 Geant4 主程序。

---

## D023：无效配置、非法几何、非法 profile 和输出错误必须 fail fast

**状态：** Accepted  
**日期：** 2026-05-21

### 背景

车辆 ROI、pose、source、detector、collimator 和输出路径中任一错误都可能生成看似合理但实际不可解释的数据。

### 决策

以下错误必须在事件产生前或出错点立即报错停止：

- YAML 字段缺失或类型错误；
- 非法 pose；
- detector range 非法；
- abnormal target 无效；
- host / daughter 不合法；
- overlap；
- 非法 collimator profile；
- spectrum 文件非法；
- 输出目录或 CSV 无法创建；
- 多线程合并失败；
- 输出 run 目录已存在且未显式允许覆盖；
- pose run 实际 random_seed 无法确定或无法写入 metadata；
- 固定 World 无法覆盖 VehicleROI 或任一 pose 下成像头组件。

### 影响

- 不做静默 fallback。
- 不自动修复非法 profile 或几何。
- 错误信息应指出字段、文件或组件名。
- 默认输出目录策略为 fail if exists：若 `results/{run_id}` 已存在，程序应报错停止；后续若支持覆盖或自动新建 run_id，需另行决策。
- `random_seed` 应作为该 pose run 的实际 seed 写入 metadata；多 pose 程序执行时还应记录 `base_random_seed` 和 `pose_index`。

---

## D024：第二版基础构建不包含真实探测器响应、图像重建和连续运动扫描

**状态：** Accepted  
**日期：** 2026-05-21

### 背景

第二版当前目标是搭建车辆侧向 ROI 背散射事件级数据生成链路，而不是完整工程成像系统。

### 决策

第二版基础构建不包含：

- 整车 CAD 复现；
- 真实探测器材料响应；
- sensitive detector 能量沉积；
- 图像重建；
- 后处理绘图；
- pose-level summary；
- scan-level summary；
- 后处理脚本；
- 连续运动扫描；
- 运动模糊；
- 时间相关积分；
- 成像头旋转；
- 成像头 z 方向运动；
- 镜像准直器；
- 镜像探测器。

### 影响

- 所有这些内容进入 deferred work。
- Codex 不得在基础构建中主动实现这些功能。
- 若某项 deferred work 变为基础交付项，必须新增或修订决策，并同步更新 `spec.md`、`architecture.md`、`milestones.md` 和 `acceptance_checklist.md`。

---

## D025：World 使用固定 4000 mm 立方体并进行边界检查

**状态：** Accepted  
**日期：** 2026-05-21

### 背景

第二版基础实现不需要复杂的按 pose 自动扩展 World。为降低实现复杂度并保持几何检查直观，本轮采用足够大的固定 World。

### 决策

World 固定为：

```text
shape = box
center_mm = [0.0, 0.0, 0.0]
size_mm = [4000.0, 4000.0, 4000.0]
material = G4_AIR
```

程序必须检查 VehicleROI 以及所有 pose 下的 source、collimator jaw 和 virtual detector plane 均位于该 World 内。若任一组件超出 World，应在事件产生前 fail fast。

### 影响

- 不实现 all-pose World auto sizing。
- metadata 必须记录固定 World 的 shape、center、size 和 material。
- 后续若需要更大 World 或自动扩展策略，应更新本文档和 `spec.md`。

---

## D026：一个 run 对应一个 pose 和一个实际 seed，可在 run 内使用多线程

**状态：** Accepted  
**日期：** 2026-05-21

### 背景

第二版需要对多个离散成像头位姿分别运行 Monte Carlo 统计，同时允许每个位姿使用 Geant4 多线程提升计算速度。

### 决策

一个 run 的语义固定为：

```text
run = one pose + one actual random_seed + one model condition + n_primary
```

一个 run 可以使用多个 worker thread 执行。线程是 run 内部的并行执行细节，不改变 run 与 pose / seed 的一一对应关系。

一次程序执行可以包含多个 pose run。多 pose 默认 seed 策略为：

```text
base_random_seed = run.random_seed
pose_seed = base_random_seed + pose_index
```

若实现采用等价简单策略，必须保证每个 pose run 的 seed 明确、可记录、可复现。每个 pose run 的 metadata 必须记录 `base_random_seed`、`pose_index` 和该 pose 实际使用的 `random_seed`。

### 影响

- `run_id` 应包含 pose 与实际 seed 信息。
- 多线程输出仍采用 worker 临时 CSV + master 合并。
- 不要求跨线程数逐事件 bitwise identical。
- 不采用复杂 hash seed 派生策略作为本轮硬要求。

---

## D027：现有第一轮代码只允许机制级复用，不允许语义级继承

**状态：** Accepted  
**日期：** 2026-05-21

### 背景

当前仓库仍保留第一轮 PMMA 背散射实现。该实现验证了 Geant4 项目结构、事件级 CSV 输出、多线程临时文件合并、spectrum sampling 和部分 action 链路，但其物理对象、配置入口和输出 schema 与第二版目标不一致。

### 决策

第二版实现可以复用第一轮的工程机制，但不得继承第一轮语义作为第二版默认行为。

允许机制级复用：

- Geant4 项目组织和 action 注册经验；
- spectrum CSV 读取和 sampling；
- CSV writer 的文件打开、格式化和线程临时文件合并思路；
- gamma track 过滤和 detector crossing 插值思路；
- collimator CSV 基础解析和 `G4ExtrudedSolid` 构建经验。

禁止语义级继承：

- PMMA 主模型；
- air defect；
- 固定三块 jaw；
- mirror collimator；
- mirror detector；
- macro 主配置入口；
- 旧 formal / debug / compact CSV schema；
- `hits_profile_*` 输出命名；
- 只统计 `PMMALogical` 内散射。

### 影响

- 后续里程碑应优先隔离 legacy 语义，再逐步迁移可复用机制。
- 若复用旧类名，必须保证其职责已符合第二版文档；否则应重命名或替换为第二版模块。
- README 和 `macros/*.mac` 在完成第二版主链路前只能视为 legacy 参考，不得作为第二版验收入口。

---

## D028：正式 CSV 输出 detected gamma hit，debug CSV 输出 gamma track summary

**状态：** Accepted
**日期：** 2026-05-26
**取代：** D012

### 背景

真实探测器不会区分 gamma 是否为 source primary。第二版论文数据目标需要分析探测器能探测到的 gamma，而不是只分析 `track_id == 1 && parent_id == 0` 的 primary gamma。

### 决策

事件追踪模型采用：

```text
detector-hit 模型 + per-gamma-track scatter history
```

基本定义：

```text
1 event = 1 source primary gamma
1 row in events.csv = 1 detected gamma hit
```

探测器记录对象为所有 gamma track。有效 detector crossing 条件不包含 `track_id == 1` 或 `parent_id == 0` 限制。同一 gamma track 只记录第一次有效 detector crossing；同一 event 内不同 gamma track 可分别记录为不同 hit。

正式 `events.csv` 输出所有 detected gamma hit，并使用 `event_id + hit_id` 唯一标识每个 hit。`hit_id` 在同一 event 内从 `0` 开始。

Debug CSV 采用：

```text
1 row = 1 gamma track summary
```

Debug CSV 使用 `detected` 字段区分该 gamma track 是否至少一次有效穿越探测平面。由于所有 gamma track 都可能被记录，debug CSV 文件会明显大于正式 CSV。

每条 gamma track 必须维护自身的 `compt` / `Rayl` 散射历史。secondary gamma 的散射阶次从自身产生时从 `0` 开始，不继承 parent track 的散射阶次。

正式 CSV 和 debug CSV 必须包含 `gamma_source_*` 字段；primary gamma 的 `gamma_source_x/y/z` 为焦点面随机采样后的实际 `gamma_start`，secondary gamma 的 `gamma_source_x/y/z` 为 track vertex position。

### 影响

- D012 被取代，不再使用 primary-only CSV 语义。
- `events.csv` 可在同一 event 中输出 0 行、1 行或多行。
- Formal CSV 不包含 `detected` 字段，但包含 `hit_id`、`track_id`、`parent_id`、`is_primary_gamma` 和 `gamma_source_*` 字段。
- Debug CSV 不再只是 formal CSV 加一个 `detected` 字段，而是 gamma track summary schema。
- 仍不输出 pose-level / scan-level summary、后处理图表、detector region ID、depth region ID、target interaction boolean 或 per-region scatter counts。

---

## 4. 变更控制

修改 Accepted 决策时应：

1. 将旧决策标记为 `Superseded`；
2. 新增决策 ID；
3. 说明变化内容和原因；
4. 同步更新 `spec.md`、`architecture.md`、`milestones.md` 和 `acceptance_checklist.md` 中受影响的内容。

以下变更必须视为设计决策变更，而不是局部实现细节：

- formal CSV 或 debug CSV header 变化；
- 本轮是否实现 pose-level / scan-level summary 或后处理模块；
- YAML parser、CLI 主入口或默认入口路径变化；
- VehicleROI schema 变化；
- collimator profile 或 placement 规则变化；
- 输出目录覆盖 / 追加 / 自动重命名策略变化；
- run / pose / seed 对应关系变化。
