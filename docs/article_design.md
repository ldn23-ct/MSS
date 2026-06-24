# 多重散射成像潜力实验设计：实验分类与论文逻辑梳理

## 0. 文档定位

本文档用于梳理当前多重散射蒙卡模拟论文的实验分类、实验条件、图表编号和论文逻辑对应关系。

当前版本采用以下前提：

```text
S1, S2, S3 三组狭缝在同一次 run 中同时存在。
不再把 slit_id 作为仿真运行维度。
后处理时按 S1, S2, S3 分别统计。

S1 = 浅层敏感狭缝
S2 = 中层敏感狭缝
S3 = 深层敏感狭缝

D1 = 浅层缺陷
D2 = 中层缺陷
D3 = 深层缺陷

D1 matched S1
D2 matched S2
D3 matched S3
```

本文档中的实验数量均指物理条件数量。若每个物理条件拆分为多个 batch，则实际程序运行数量需要乘以 batch_count。

关于统计量：

```text
核心变量是独立 primary histories 总数，而不是 seed 标签数量。
每个实验条件需要达到足够的独立 primary histories。
这些 histories 可以来自一个大 run，也可以来自多个 batch 合并。
不同 batch 可使用不同 seed，或使用可证明不会重复的随机序列。
误差条可用 Poisson 计数误差或 batch 间波动估计。
```

---

# 一、实验分类与具体条件

## E0. PMMA 浅、中、深 air void 综合筛选实验

### E0.1 实验定位

E0 是 PMMA 主机制筛选实验，同时承担以下任务：

```text
1. 狭缝 S1, S2, S3 来源深度接受偏好分析
2. 60–560 keV 能量筛选
3. PMMA 浅、中、深 air void 缺陷机制比较
4. matched slit 判定
```

原先单独设置的 E1 机制确认实验删除，因为其所需数据可由 E0 获得。

### E0.2 实验条件

```text
模体材质 + 缺陷位置：

P0：
PMMA uniform，无缺陷

P1：
PMMA + air void + D1 浅层缺陷

P2：
PMMA + air void + D2 中层缺陷

P3：
PMMA + air void + D3 深层缺陷


射线能量：

60 keV
160 keV
260 keV
360 keV
460 keV
560 keV


扫描方式：

特定 pose
center pose


狭缝：

S1, S2, S3 同时存在


统计量：

每个条件达到目标独立 primary histories
不把 seed 作为论文主变量
如分 batch 运行，则后处理合并
```

### E0.3 条件数量

```text
4 个 PMMA 模体 × 6 个能量 × 1 个 center pose
= 24 个物理条件
```

如果每个物理条件拆成多个 batch：

```text
实际程序运行数 = 24 × batch_count
```

### E0.4 后处理拆分

每个物理条件后处理为：

```text
S1 response
S2 response
S3 response

k0
k1
k2
k3
ms = scatter_count_total >= 2
total
without_ms = k0 + k1
```

### E0.5 需要绘制的图或表

```text
Fig. 2
PMMA uniform 下 S1/S2/S3 的 last_scatter_z 分布
用途：说明三组狭缝具有不同 nominal depth-sensitive acceptance

Fig. 3
PMMA uniform 下 S1/S2/S3 的 median last_scatter_z 与 width90 随能量变化
用途：判断狭缝来源深度接受偏好是否随能量稳定

Fig. 4
P1/P2/P3 相对 P0 的 Delta_Y_ms(E, S1/S2/S3)
用途：筛选 E_star，并观察浅、中、深缺陷的多重散射产额变化

Fig. 5
P1/P2/P3 相对 P0 的 Delta_R_ms(E, S1/S2/S3)
用途：判断多重散射比例变化是否支持深度相关响应

Fig. 6
P1/P2/P3 在 E_star 候选能量下的 det_energy 分布
用途：解释不同能量与缺陷深度下的能量退化差异

Fig. 7
P1/P2/P3 在 E_star 候选能量下的 last_scatter_z 分布
用途：比较 shallow, middle, deep defect 的来源深度响应

Table 1
E0 实验条件表
内容：phantom, defect depth, energy, pose, slit configuration, target histories

Table 2
能量筛选指标汇总表
内容：energy, Y_ms, Delta_Y_ms, R_ms, Delta_R_ms, width90, det_energy median

Table 3
matched slit 判定表
内容：D1-S1, D2-S2, D3-S3 是否成立；是否存在明显 mismatched response
```

---

## E1. PMMA 浅、中、深 air void 正式 grid 成像实验

### E1.1 实验定位

E1 是论文的 PMMA 主成像实验。

浅、中、深三个层面都进入正式比较。

### E1.2 实验条件

```text
模体材质 + 缺陷位置：

P0：
PMMA uniform，无缺陷

P1：
PMMA + air void + D1 浅层缺陷

P2：
PMMA + air void + D2 中层缺陷

P3：
PMMA + air void + D3 深层缺陷


射线能量：

E_star
由 E0 筛选得到


扫描方式：

grid

推荐 grid：
21 × 15，压缩正式版
25 × 17，高分辨正式版


狭缝：

S1, S2, S3 同时存在


统计量：

每个 grid pose 达到目标独立 primary histories
可以单次大统计运行
也可以多 batch 合并
```

### E1.3 条件数量

以 21 × 15 grid 为例：

```text
4 个 PMMA 模体 × 315 个 poses × 1 个能量
= 1260 个物理条件
```

以 25 × 17 grid 为例：

```text
4 个 PMMA 模体 × 425 个 poses × 1 个能量
= 1700 个物理条件
```

### E1.4 图像通道

每个模体、每个 slit_id 生成：

```text
I_total
I_k1
I_k2
I_ms
I_without_ms
Delta_I_total
Delta_I_k1
Delta_I_ms
F_ms
```

灰度定义建议统一为：

```text
I_channel = N_channel / N_incident
```

差异图定义：

```text
Delta_I_channel = I_abnormal_channel - I_uniform_channel
```

需要注意：

```text
I_k1、I_k2、I_ms 是基于 Monte Carlo scatter history 的通道分解图像。
它们用于评估不同散射阶次的成像信号潜力。
它们不等价于真实探测器中可直接测得的独立图像通道。
```

### E1.5 需要绘制的图或表

```text
Fig. 8
PMMA D1 浅层缺陷 grid 图像
内容：S1/S2/S3 下的 I_total, I_k1, I_ms, Delta_I_ms
用途：展示浅层缺陷图像响应

Fig. 9
PMMA D2 中层缺陷 grid 图像
内容：S1/S2/S3 下的 I_total, I_k1, I_ms, Delta_I_ms
用途：展示中层缺陷图像响应

Fig. 10
PMMA D3 深层缺陷 grid 图像
内容：S1/S2/S3 下的 I_total, I_k1, I_ms, Delta_I_ms
用途：展示深层缺陷图像响应

Fig. 11
PMMA matched slit 图像比较
内容：D1-S1, D2-S2, D3-S3 的 Delta_I_ms
用途：直接比较浅、中、深缺陷在 matched slit 下的多重散射可见性

Fig. 12
PMMA matched vs mismatched 图像比较
内容：D1 下 S1/S2/S3 对比；D2 下 S1/S2/S3 对比；D3 下 S1/S2/S3 对比
用途：判断 slit_id 与缺陷深度的响应对应关系

Fig. 13
PMMA CNR_channel 对比图
内容：CNR_total, CNR_k1, CNR_ms, CNR_without_ms
条件：D1/D2/D3 × S1/S2/S3
用途：量化多重散射通道的二维异常可见性

Fig. 14
PMMA Delta_C_ms 对比图
内容：CNR_total - CNR_without_ms
条件：D1/D2/D3 × S1/S2/S3
用途：判断多重散射对 total 图像 CNR 的贡献方向

Table 4
E1 PMMA grid 实验条件表
内容：phantom, defect depth, energy, grid size, target histories

Table 5
PMMA grid ROI 指标表
内容：D1/D2/D3, S1/S2/S3, CNR_total, CNR_k1, CNR_ms, CNR_without_ms, Delta_C_ms

Table 6
PMMA matched/mismatched 判定表
内容：每个缺陷深度下 matched slit 是否具有更高 Delta_I_ms 或 CNR_ms
```

---

## E2. PMMA grid 中代表性 pose 事件级解释

### E2.1 实验定位

E2 不新增仿真。

从 E1 的 grid 数据中选取代表性 pose。

### E2.2 pose 选择规则

每个缺陷深度选择：

```text
background pose
edge pose
center pose
```

优先选择：

```text
D1-S1 matched
D2-S2 matched
D3-S3 matched
```

必要时补充：

```text
D1-S3 mismatched
D2-S1 或 D2-S3 mismatched
D3-S1 mismatched
```

### E2.3 需要绘制的图或表

```text
Fig. 15
D1-S1 代表性 pose 事件级解释图
内容：background, edge, center 的 scatter count histogram, det_energy distribution, last_scatter_z distribution
用途：解释浅层缺陷图像对比来源

Fig. 16
D2-S2 代表性 pose 事件级解释图
内容同上
用途：解释中层缺陷图像对比来源

Fig. 17
D3-S3 代表性 pose 事件级解释图
内容同上
用途：解释深层缺陷图像对比来源

Fig. 18
matched 与 mismatched pose 机制对照图
内容：last_scatter_z, det_energy, scatter order fraction
用途：说明 matched slit 的图像优势是否有散射历史支撑

Table 7
代表性 pose 选择表
内容：defect depth, slit_id, pose type, grid coordinate, selection reason

Table 8
代表性 pose 事件级指标表
内容：R_ms, Y_ms, k1 fraction, ms fraction, median last_scatter_z, width90, median det_energy
```

---

## E3. 金属表层复杂结构浅、中、深机制补充实验

### E3.1 实验定位

E3 是补充实验的主线，替代原先考虑的 PMMA 低 Z 填充物补充实验。

逻辑对应关系为：

```text
PMMA + air void：
较高散射 PMMA 背景 + 较低散射 air void 异常

Metal layered + flour：
复杂金属表层背景 + 低 Z / 低密度异常
```

金属部分的作用是：

```text
验证 PMMA 中发现的多重散射响应，
在更接近车辆安检的复杂高衰减结构中是否仍可观察。
```

金属实验不承担 PMMA 主规律证明，只作为复杂结构下的应用补充和边界验证。

### E3.2 实验条件

```text
模体材质 + 缺陷位置：

M0：
Metal layered normal，无缺陷

M1：
Metal layered + flour target + D1 浅层缺陷

M2：
Metal layered + flour target + D2 中层缺陷

M3：
Metal layered + flour target + D3 深层缺陷


射线能量：

60 keV
160 keV
260 keV
360 keV
460 keV
560 keV


扫描方式：

特定 pose

target center pose
reference pose


狭缝：

S1, S2, S3 同时存在


统计量：

每个条件达到目标独立 primary histories
可按 batch 合并
```

### E3.3 条件数量

```text
4 个金属模体 × 6 个能量 × 2 个 poses
= 48 个物理条件
```

### E3.4 需要绘制的图或表

```text
Fig. 19
金属结构 D1/D2/D3 的 Delta_Y_ms(E, S1/S2/S3)
用途：判断复杂金属结构中浅、中、深 flour 异常是否有多重散射产额响应

Fig. 20
金属结构 D1/D2/D3 的 Delta_R_ms(E, S1/S2/S3)
用途：判断多重散射比例变化是否仍可观察

Fig. 21
金属结构 D1/D2/D3 的 Y_ms(E)
用途：判断金属衰减下统计产额是否足够

Fig. 22
金属结构 D1/D2/D3 的 det_energy 分布
用途：解释金属结构导致的能量退化与统计限制

Fig. 23
金属结构 D1/D2/D3 的 last_scatter_z 分布
用途：判断复杂结构下来源深度是否明显混杂

Table 9
E3 金属机制实验条件表
内容：metal phantom, defect depth, energy, pose, target histories

Table 10
金属深度响应指标表
内容：D1/D2/D3, S1/S2/S3, Y_ms, Delta_Y_ms, R_ms, Delta_R_ms, width90, det_energy median

Table 11
E_star_metal 选择表
内容：energy, Y_ms, Delta_Y_ms, width90, det_energy, matched response
```

---

## E4. 金属表层复杂结构浅、中、深 grid 成像补充实验

### E4.1 实验定位

E4 是金属结构下的二维图像补充。

它不承担 PMMA 主规律证明，但用于说明复杂车辆近似结构中仍有异常可观测响应。

### E4.2 实验条件

```text
模体材质 + 缺陷位置：

M0：
Metal layered normal，无缺陷

M1：
Metal layered + flour target + D1 浅层缺陷

M2：
Metal layered + flour target + D2 中层缺陷

M3：
Metal layered + flour target + D3 深层缺陷


射线能量：

E_star_metal
由 E3 选择


扫描方式：

grid

推荐 grid：
15 × 11，补充图
21 × 15，较完整补充图


狭缝：

S1, S2, S3 同时存在


统计量：

每个 grid pose 达到目标独立 primary histories
可以多 batch 合并
```

### E4.3 条件数量

15 × 11 grid：

```text
4 个金属模体 × 165 poses × 1 个能量
= 660 个物理条件
```

21 × 15 grid：

```text
4 个金属模体 × 315 poses × 1 个能量
= 1260 个物理条件
```

### E4.4 需要绘制的图或表

```text
Fig. 24
金属 D1 浅层 flour 异常 grid 图像
内容：S1/S2/S3 下 I_total, I_k1, I_ms, Delta_I_ms
用途：展示复杂金属结构中浅层异常图像响应

Fig. 25
金属 D2 中层 flour 异常 grid 图像
内容同上
用途：展示复杂金属结构中中层异常图像响应

Fig. 26
金属 D3 深层 flour 异常 grid 图像
内容同上
用途：展示复杂金属结构中深层异常图像响应

Fig. 27
金属 matched slit Delta_I_ms 对比图
内容：D1-S1, D2-S2, D3-S3
用途：判断复杂金属结构中是否仍保留深度相关图像响应

Fig. 28
金属 PMMA 对照图
内容：PMMA D1/D2/D3 matched Delta_I_ms vs Metal D1/D2/D3 matched Delta_I_ms
用途：比较理想 PMMA 与复杂金属结构下的响应退化

Table 12
E4 金属 grid 实验条件表
内容：metal phantom, defect depth, E_star_metal, grid size, target histories

Table 13
金属 grid ROI 指标表
内容：D1/D2/D3, S1/S2/S3, CNR_total, CNR_k1, CNR_ms, CNR_without_ms, Delta_C_ms
```

---

## E5. 金属复杂结构边界分析，可选

### E5.1 实验定位

如果 E3/E4 中金属深层响应明显衰减，可以增加边界实验。

这一组不是必做。

### E5.2 可选变量

```text
金属前层厚度：
thin
medium
thick

异常深度：
D1
D2
D3

射线能量：
E_star_metal

扫描方式：
target center pose

狭缝：
S1, S2, S3 同时存在
```

### E5.3 需要绘制的图或表

```text
Fig. 29
金属厚度对 Y_ms 和 Delta_Y_ms 的影响
用途：说明金属衰减边界

Fig. 30
金属厚度对 CNR_ms 的影响
用途：说明复杂结构下成像可见性的退化边界

Table 14
金属边界实验指标表
内容：metal thickness, defect depth, Y_ms, Delta_Y_ms, CNR_ms, width90
```

---

# 二、修订后的完整实验规模

不把 S1/S2/S3 作为 run 维度。

```text
E0 PMMA 综合筛选：
24 个物理条件

E1 PMMA 浅中深 grid 成像：
1260 个物理条件，21 × 15 grid
或 1700 个物理条件，25 × 17 grid

E2 代表性 pose 解释：
不新增仿真

E3 金属复杂结构机制补充：
48 个物理条件

E4 金属复杂结构 grid 补充：
660 个物理条件，15 × 11 grid
或 1260 个物理条件，21 × 15 grid

E5 金属边界实验：
可选
```

若采用：

```text
PMMA 21 × 15 grid
金属 15 × 11 grid
不做 E5
```

总物理条件数为：

```text
24 + 1260 + 48 + 660 = 1992
```

如果每个条件拆成 `B` 个 batch，则实际程序运行数为：

```text
1992 × B
```

---

# 三、论文逻辑与图表对应关系

## 1. Introduction

### 对应问题

```text
多重散射在背散射成像中通常被视为背景或退化来源。
但在笔形束 + 三狭缝准直几何下，它可能保留与异常深度和结构相关的统计信息。
```

### 使用图表

```text
Fig. 1
系统几何与事件级数据链路图
```

---

## 2. Methods

### 2.1 Monte Carlo system and event-level recording

回答：

```text
系统几何如何定义？
事件级数据如何记录？
scatter class 如何定义？
```

使用：

```text
Fig. 1
Table 1
Table 4
Table 9
Table 12
```

### 2.2 Slit-resolved post-processing

回答：

```text
S1/S2/S3 如何在同一次 run 中区分？
为什么 slit_id 是后处理分类维度？
```

使用：

```text
Fig. 2
Fig. 3
```

核心表述：

```text
S1/S2/S3 表示 nominal depth-sensitive acceptance。
不声称它们是精确深度切片。
```

---

## 3. Results I：PMMA 中的狭缝接受偏好与能量筛选

### 对应问题 Q1

```text
S1/S2/S3 是否具有不同来源深度接受偏好？
```

使用：

```text
Fig. 2
Fig. 3
Table 3
```

### 对应问题 Q2

```text
哪个能量适合作为 PMMA 主成像能量 E_star？
```

使用：

```text
Fig. 4
Fig. 5
Fig. 6
Table 2
```

---

## 4. Results II：PMMA 浅、中、深缺陷的多重散射响应

### 对应问题 Q3

```text
多重散射事件是否对浅、中、深 air void 缺陷有系统响应？
```

使用：

```text
Fig. 4
Fig. 5
Fig. 7
Table 2
Table 3
```

逻辑：

```text
比较 P0, P1, P2, P3。
若 D1/D2/D3 分别在 S1/S2/S3 下响应更强，
则说明多重散射响应具有深度相关性。
```

---

## 5. Results III：PMMA 浅、中、深正式 grid 成像

### 对应问题 Q4

```text
多重散射通道是否能形成二维异常可见性？
```

使用：

```text
Fig. 8
Fig. 9
Fig. 10
Fig. 11
Table 5
```

### 对应问题 Q5

```text
matched slit 是否比 mismatched slit 更突出对应深度缺陷？
```

使用：

```text
Fig. 12
Fig. 13
Table 6
```

### 对应问题 Q6

```text
多重散射对 total 图像是增强还是稀释？
```

使用：

```text
Fig. 14
Table 5
```

---

## 6. Results IV：代表性 pose 的事件级解释

### 对应问题 Q7

```text
图像中的亮暗变化来自什么散射机制？
```

使用：

```text
Fig. 15
Fig. 16
Fig. 17
Fig. 18
Table 7
Table 8
```

逻辑：

```text
从 grid 中选 background、edge、center。
比较 scatter count histogram、det_energy、last_scatter_z。
解释图像对比背后的事件级来源。
```

---

## 7. Results V：金属表层复杂结构中的补充验证

### 对应问题 Q8

```text
PMMA 中观察到的多重散射响应，
在复杂金属表层结构中是否仍可观察？
```

使用：

```text
Fig. 19
Fig. 20
Fig. 21
Fig. 22
Fig. 23
Table 10
Table 11
```

逻辑：

```text
金属结构不承担主规律证明。
它用于验证复杂高衰减背景下，低 Z flour 异常是否仍能产生可观测多重散射响应。
```

---

## 8. Results VI：金属复杂结构中的 grid 图像补充

### 对应问题 Q9

```text
复杂金属结构下是否仍能形成二维异常可见性？
```

使用：

```text
Fig. 24
Fig. 25
Fig. 26
Fig. 27
Fig. 28
Table 13
```

逻辑：

```text
先展示金属 D1/D2/D3 的 grid 图像。
再比较 matched slit 图像。
最后与 PMMA matched 图像对照，说明复杂结构造成的响应退化。
```

---

## 9. Discussion

### 需要讨论的问题

```text
1. 为什么多重散射不能简单视为无结构噪声
2. 为什么 S1/S2/S3 只能称为 nominal depth-sensitive acceptance
3. 为什么 I_ms 是 Monte Carlo scatter-history 分解通道
4. 多重散射何时增强 total 图像，何时稀释 total 图像
5. 金属复杂结构下响应退化来自哪些因素
6. 后续真实系统如何考虑通道分离、编码或重建
```

主要引用：

```text
Fig. 11
Fig. 12
Fig. 13
Fig. 14
Fig. 18
Fig. 27
Fig. 28

Table 5
Table 6
Table 10
Table 13
```

---

## 10. Conclusion

### 建议结论边界

```text
在笔形束 + 三狭缝准直 baseline 几何中，
多重散射事件在 PMMA 浅、中、深 air void 缺陷中表现出可量化的深度相关响应。

S1/S2/S3 可作为 nominal depth-sensitive acceptance，
matched slit 下的多重散射分解通道可以形成二维异常对比。

金属表层复杂结构中的 flour 异常验证说明，
该响应在更接近车辆安检的高衰减背景下仍可能可观察，
但其可用性受到金属衰减、缺陷深度、射线能量和统计量限制。

本文证明的是多重散射事件的成像信号潜力，
不等价于已经实现真实探测器中的多重散射通道直接分离。
```
