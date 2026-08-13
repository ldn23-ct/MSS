# 源项响应框架下的 X 射线背散射仿真实验设计（V2）

## 0. 修订依据与实验总体定位

本版本在原 `simulation_experiment_design.md` 的基础上，根据 `backscatter_source_response_framework_v2.md` 以及当前针对 E1–E8 的讨论结果重新整理。修订目标是使全部仿真实验围绕最新 source-response framework 形成一条一致的证据链，并明确区分：

1. **当前 Geant4 数据能够直接观测和证明的内容；**
2. **可由多组事件统计辅助支持的机制解释；**
3. **需要后续输运校正算法进一步验证的研究方向。**

当前框架采用：

\[
\text{directed primary beam}\rightarrow q_j\rightarrow \gamma\rightarrow D_k
\]

其中，\(q_j\) 表示初级光子在定向窄束覆盖的位置 \(j\) 形成的首次散射源项；\(\gamma\) 表示首次散射后的完整传播、再次散射、衰减和准直接受历史；\(D_k\) 表示第 \(k\) 个探测/狭缝通道。

探测计数写为：

\[
N_k=\sum_jq_j\left[K_k^{(1)}(j)+K_k^{(m)}(j)\right]+\eta_k.
\]

其中：

\[
K_k^{(1)}(j)=\sum_{\gamma\in\Gamma_{j,k}^{(1)}}w_k(\gamma|j),
\]

\[
K_k^{(m)}(j)=\sum_{\gamma\in\Gamma_{j,k}^{(m)}}w_k(\gamma|j).
\]

必须强调：当前 Geant4 数据按 detected gamma hit 记录对应 gamma track 自身的首次散射位置。primary 与 secondary gamma 均可贡献计数，因此直接统计得到的 `first_scatter_z` 分布对应：

\[
R_k^{(1)}(j)=q_jK_k^{(1)}(j),
\]

\[
R_k^{(m)}(j)=q_jK_k^{(m)}(j),
\]

而不是裸源项 \(q_j\) 或独立的 \(K_k(j)\)。理论中的 \(q_j\) 仍描述 primary-driven first-scatter source；占比较小的 secondary-gamma contribution 不单独扩展来源索引，而作为未显式分离的附加探测贡献保留在实际 \(N_k\) 与 \(R_k^{(s)}\) 统计中。

因此，本组实验的核心目标不是定量分离 \(\Delta q\) 与 \(\Delta K\)，而是利用事件级 Monte Carlo truth 完成以下论证：

- 狭缝系统具有可区分的 first-scatter depth selectivity；
- 局部缺陷能够改变探测器端 total、k1 和 MS 响应；
- 以目标区域为首次散射源项的 MS 分量能够对局部结构变化产生可测响应；
- 不同 first-scatter source regions 的 MS 具有不同的结构响应与成像作用；
- 给定局部首次散射源项后，后续 MS 输运仍具有显著非局域性；
- 基于 first-scatter source region 对 MS 进行选择性校正，在理想条件下是否具有实际图像质量收益，并据此为后续输运校正算法提供方向。

---

## 0.1 原实验 E1–E8 与 V2 实验 E1–E6 的关系

| 原编号 | 原实验 | V2 处理 | 新编号 |
|---|---|---|---|
| E1 | 均匀模体多狭缝深度响应核验证 | 保留为 baseline；不再将 detected profile 称为纯 \(K\)；删除不必要的核重叠等复杂参数 | E1 |
| E2 | 缺陷源项扰动验证 | 与原 E3 合并；由“直接验证 \(q\)”改为 detected source-response redistribution | E3 |
| E3 | 目标区多重散射结构响应验证 | 与原 E2 合并，成为核心机制实验 | E3 |
| E4 | 非目标多重散射背景来源分解 | 保留，但不预设 front/behind 为噪声或 non-target MS 为唯一主要背景 | E4 |
| E5 | 缺陷深度与狭缝响应匹配 | 前移至 baseline 之后，直接衔接 E1 | E2 |
| E6 | acceptance volume 边界验证 | 重构为固定 first-scatter source 后的非局域路径扩展与 P4_off 局部路径扰动实验 | E5 |
| E7 | 小缺陷条件下 \(\Delta q\)/\(\Delta K\) 相对贡献 | 删除；当前 framework 不要求严格证明 \(\Delta q\) 主导，尺寸变化也无法实现源项与输运的严格分离 | 删除 |
| E8 | 非目标源项抑制与图像质量提升 | 重构为基于 Geant4 first-scatter truth 的理想 MS 校正 benchmark | E6 |

---

# 1. 模体、狭缝与扫描模式统一约定

## 1.1 正式仿真与探测参数

全部正式仿真统一采用以下参数：

| 项目 | 正式设定 |
|---|---|
| Monte Carlo engine | Geant4 |
| physics list | `G4EmLivermorePhysics` |
| source particle / energy | mono gamma，560 keV |
| source spatial model | 直径 5 mm 的圆形源面内均匀采样 |
| incident direction | 固定方向，沿模体深度增加方向入射 |
| primary histories | 每个独立 pose 为 \(2.0\times10^7\) |
| PMMA phantom size | \(1000\times1000\times220\ \mathrm{mm^3}\) |
| PMMA / air material | `G4_PLEXIGLASS` / `G4_AIR` |
| standard air defect | \(10\times10\times10\ \mathrm{mm^3}\) |
| detector | 理想虚拟探测面 |
| detector response | 无能量阈值、无能窗，不模拟本征效率和能量分辨率 |
| hit recording | 每条 gamma track 最多记录第一次有效 detector crossing |

每个模拟 event 产生一个 source primary gamma，但正式计数对象为 detected gamma hit。所有 gamma track 均可贡献探测记录，包括 primary 与 secondary gamma；因此同一模拟 event 可以产生零条、一条或多条 detected-hit 记录。

## 1.2 模体与缺陷编号

主实验统一采用 PMMA 均匀模体和空气缺陷模体。标准空气缺陷尺寸为：

\[
10\,\mathrm{mm}\times10\,\mathrm{mm}\times10\,\mathrm{mm}.
\]

缺陷中心位于当前系统重点探测厚度 \(0\sim100\ \mathrm{mm}\) 内。

| 模体编号 | 类型 | 缺陷中心深度 \(z_c\) | 横向位置 | 缺陷尺寸 | 主要用途 |
|---|---|---:|---|---|---|
| P0 | 均匀 PMMA | — | — | — | 全部实验 baseline |
| P1 | on-axis 空气缺陷 | 15 mm | \((x_0,y_0)\) | \(10\times10\times10\ \mathrm{mm^3}\) | 浅层缺陷 |
| P2 | on-axis 空气缺陷 | 30 mm | \((x_0,y_0)\) | 同上 | 浅中层缺陷 |
| P3 | on-axis 空气缺陷 | 45 mm | \((x_0,y_0)\) | 同上 | 中浅层缺陷 |
| P4 | on-axis 空气缺陷 | 60 mm | \((x_0,y_0)\) | 同上 | 中层代表缺陷；核心机制实验 |
| P5 | on-axis 空气缺陷 | 75 mm | \((x_0,y_0)\) | 同上 | 中深层缺陷 |
| P6 | on-axis 空气缺陷 | 90 mm | \((x_0,y_0)\) | 同上 | 深层代表缺陷 |
| P4_off | off-axis 空气扰动 | 由 E5-A 路径统计确定 | 偏离 directed primary beam | \(10\times10\times10\ \mathrm{mm^3}\) | E5 后续输运路径扰动 |

### P4_off 的位置选择原则

P4_off 不再预设为简单的固定横向偏移。其最终位置由 P0–S4 条件下 target-source MS 的 subsequent/last-scatter 空间分布确定，并满足：

1. 不与 directed primary beam 的主照射范围重合；
2. 位于 target-source MS 后续散射的相对高概率区域；
3. 尽量避开 target-source k1 的主要直达传播 corridor；
4. 位置必须在查看 P4_off 结果前确定；
5. 一旦确定，在 P0/P4_off 对照中保持不变。

---

## 1.3 狭缝编号与设计目标深度

狭缝编号与缺陷深度一一对应：

\[
S_j\leftrightarrow P_j.
\]

| 狭缝编号 | 设计目标深度 | 对应缺陷 | 说明 |
|---|---:|---|---|
| S1 | 15 mm 左右 | P1 | 浅层通道 |
| S2 | 30 mm 左右 | P2 | 浅中层通道 |
| S3 | 45 mm 左右 | P3 | 中浅层通道 |
| S4 | 60 mm 左右 | P4 | 中层通道 |
| S5 | 75 mm 左右 | P5 | 中深层通道 |
| S6 | 90 mm 左右 | P6 | 深层通道 |

E1 用于确认不同通道在 detected first-scatter depth response 上具有可区分的空间选择性，但不承担独立求取 \(K_k(j)\) 的任务。

---

## 1.4 First-scatter source region 的统一定义

全文中的 **front / target / behind 均只依据当前 detected gamma track 自身的 first scatter position 定义**，与 last scatter position 无关。这里的 first/last scatter 均指该 track 自身的 Compton 或 Rayleigh 相互作用；secondary gamma 不继承 parent track 的散射位置或散射阶次。

对于目标深度为 \(z_{c,j}\) 的 Pj–Sj 组合，标准 target source region 定义为：

\[
\Omega_{T,j}=\left[z_{c,j}-5\ \mathrm{mm},\ z_{c,j}+5\ \mathrm{mm}\right).
\]

对应：

\[
\Omega_{F,j}=\{z<z_{c,j}-5\ \mathrm{mm}\},
\]

\[
\Omega_{B,j}=\{z\ge z_{c,j}+5\ \mathrm{mm}\}.
\]

因此：

\[
\Omega=\Omega_F\cup\Omega_T\cup\Omega_B.
\]

对于 P4–S4：

\[
\Omega_T=\{55\le first\_scatter\_z<65\ \mathrm{mm}\}.
\]

该定义由模体几何预先确定，在 P0 与缺陷模体间保持完全一致，不根据缺陷后的响应峰值、FWHM 或结果重新划分。

---

## 1.5 事件分类

每条 gamma track 独立维护自身在整个 Geant4 world 中的 Compton/Rayleigh 散射历史；该记录不限定为 PMMA–空气模体内部。定义：

\[
\texttt{scatter\_count\_total}
=n_{\mathrm{Compton}}+n_{\mathrm{Rayleigh}}.
\]

清洗后的 detected gamma hits 统一分为：

- `total`：`scatter_count_total >= 1`；
- `k1`：`scatter_count_total == 1`；
- `ms`：`scatter_count_total >= 2`。

因此 `total = k1 + ms`。这里的计数单位是 detected gamma hit，不是唯一 source primary photon。对于 secondary gamma，散射次数从该 track 的产生点重新计数，不继承 parent track 的散射历史。

进一步根据 first scatter position：

\[
N_F^{(1)},\quad N_T^{(1)},\quad N_B^{(1)},
\]

\[
N_F^{(m)},\quad N_T^{(m)},\quad N_B^{(m)}.
\]

因此：

\[
N_k=
N_{F,k}^{(1)}+N_{T,k}^{(1)}+N_{B,k}^{(1)}
+N_{F,k}^{(m)}+N_{T,k}^{(m)}+N_{B,k}^{(m)}+\eta_k.
\]

需要压缩为 target / non-target 时：

\[
N_{N,k}^{(s)}=N_{F,k}^{(s)}+N_{B,k}^{(s)},\qquad s\in\{1,m\}.
\]

---

## 1.6 扫描模式

### center 模式

入射束对准：

\[
p_0=(x_0,y_0).
\]

对于 on-axis 缺陷模体，缺陷中心与 directed primary beam 主轴重合。

center 主要用于：

- E1 深度响应 baseline；
- E2 缺陷深度–slit 匹配；
- E3 detected source-response redistribution；
- E4 MS source-region decomposition；
- E5 非局域输运机制分析。

### grid 模式

扫描位置：

\[
p_{ab}=(x_0+\Delta x_a,\ y_0+\Delta y_b).
\]

grid 扫描中模体保持固定，圆形源面、接收准直结构和虚拟探测面按照扫描 pose 整体移动。

形成二维计数图像：

\[
I_k(a,b)=N_{k,p_{ab}}.
\]

E6 统一采用：

| 项目 | 设定 |
|---|---|
| 主网格 | \(9\times9\) |
| x/y offset | \(\{-10,-7.5,-5,-2.5,0,2.5,5,7.5,10\}\ \mathrm{mm}\) |

E6 的 Raw、k1-only、front-MS-corrected 和 non-target-MS-corrected 图像均直接使用各 pose 的绝对 detected-hit 计数，不进行 P0 逐像素归一化。P0 只作为相同 slit 和 pose 下的均匀模体参考。

---

## 1.7 Monte Carlo 统计精度处理

本文不将 Poisson 显著性检验或不确定度分析作为独立研究内容，也不单独设置统计显著性实验。

所有成对比较应保持：

- 相同入射粒子历史数；
- 相同源与探测几何；
- 相同能量与物理过程设置；
- 相同统计 bin 和事件筛选规则。

关键实验应保证 Monte Carlo 相对统计波动明显小于待讨论的结构响应幅度。必要时仅使用：

\[
\sigma_N\approx\sqrt N
\]

估计有限 histories 的计数量级，不作为论文核心结果输出。

---

# 2. V2 仿真实验设计总表

| 编号 | 实验名称 | 核心问题 | 模体 / 条件 | 扫描模式 | 核心统计量 | 论文作用 |
|---|---|---|---|---|---|---|
| E1 | 均匀模体多狭缝深度响应基线 | 狭缝系统是否具有可区分的 first-scatter depth selectivity | P0；S1–S6 | center | total/k1/ms 的 detected `first_scatter_z` profiles；主要响应深度 | 系统 baseline；为后续缺陷实验提供无缺陷对照 |
| E2 | 缺陷深度–slit 通道匹配 | 不同深度结构变化是否由相应通道选择性观测；MS 是否同样表现深度选择特征 | P1–P6 × S1–S6；P0 同条件对照 | center 为主 | total/k1/ms 的 \(\Delta N/N_0\) 深度×通道矩阵 | 从系统选择性推进到结构响应选择性 |
| E3 | 缺陷诱导 detected source-response redistribution | MS 是否受局部结构变化调制；target-source MS 是否与缺陷位置对应地变化 | P1–P6 各自匹配 S1–S6，并以对应 P0 为对照；P4–S4 作详细展示 | center | total/k1/ms 总计数；k1/ms `first_scatter_z`；front/target/behind 分解 | 论文核心机制证据 |
| E4 | 多重散射 first-scatter source-region decomposition | front/target/behind 来源的 MS 是否表现不同的结构响应与潜在成像作用 | P1–P6 各自匹配 S1–S6，并以对应 P0 为对照；P4–S4 作详细展示 | center | \(N_F^{(m)},N_T^{(m)},N_B^{(m)}\)、占比、相对变化、事件特征 | 建立 source-region-dependent MS response |
| E5 | 目标源项 MS 的非局域输运与局部路径扰动 | 固定 source region 后后续路径是否扩展；局部 off-axis 结构如何影响部分路径集合 | E5-A：P0–S4 target-source MS；E5-B：P0 vs P4_off | center | first/last scatter spatial summary；density difference；整体 k1/ms 变化 | 辅助验证 \(\gamma\) 与 \(K^{(m)}\) 的非局域性 |
| E6 | 基于 first-scatter truth 的理想 MS 校正 | 理想去除不同 source-region MS 后图像收益如何；后续应优先发展浅层递推还是全局输运校正 | P2–S2、P4–S4、P6–S6；P0 同 grid baseline | grid | Raw、k1-only、front-MS-corrected、non-target-MS-corrected；MS composition；Contrast/CNR | future Boltzmann-based correction 的 oracle benchmark |

---

# 3. 各实验具体设计

## E1 均匀模体多狭缝深度响应基线

### 3.1.1 实验目的

E1 是全组仿真的 baseline。其主要作用为：

1. 验证当前狭缝/探测系统具有明确的深度空间选择性；
2. 建立 P0 下不同 slit 的无缺陷 detected first-scatter response；
3. 为 E2–E6 的缺陷响应提供统一对照。

E1 不单独承担 source-response framework 的核心机制论证。

### 3.1.2 条件

- 模体：P0；
- 狭缝：S1–S6；
- 扫描：center；
- 其他模拟参数保持一致。

### 3.1.3 统计对象

分别统计 total、k1、ms：

\[
H_k^{(s)}(z)=N(\text{detected gamma hits with track-local first scatter at }z),
\qquad s\in\{total,1,m\}.
\]

主要保留：

- depth profile；
- 峰值或主要响应深度；
- 必要时 FWHM 作为描述性参数。

不要求：

- 把该曲线直接称为纯 \(K_k(z)\)；
- 相邻核 overlap coefficient；
- 80% 积分区间；
- 围绕 E1 建立复杂的响应核参数体系。

### 3.1.4 预期输出

- S1–S6 detected first-scatter depth-response curves，使用 `[0,220)` 的 2 mm depth bins；
- 图中按 S1/S3/S5 与 S2/S4/S6 分为左右两组，total/k1/ms 分行展示；
- 主要响应深度与设计深度的对应关系；
- total/k1/ms 三类响应的基本差异。

### 3.1.5 论文表述边界

更适合使用：

- detected first-scatter depth response；
- effective depth-response profile；
- detected source-response profile。

不直接称为独立 \(K_k\) response kernel。

---

## E2 缺陷深度–slit 通道匹配实验

### 3.2.1 实验目的

在 E1 已证明系统具备深度选择性的基础上，进一步验证不同深度的局部结构变化能够被相应 slit 通道选择性观测，并观察 MS 分量是否同样表现出 slit-depth-dependent response。

### 3.2.2 条件

完整运行：

\[
P_j\times S_k,\qquad j,k=1,\ldots,6.
\]

每个 \(P_j-S_k\) 组合均以相同条件下的 P0–Sk 作为 baseline。

center 模式用于完成完整 \(6\times6\) 响应矩阵；二维图像仅在必要时选取代表组合补充。

### 3.2.3 指标

对于：

\[
s\in\{total,1,m\},
\]

定义：

\[
C_{jk}^{(s)}=
\frac{N_{jk}^{(s),D}-N_{jk}^{(s),0}}
{N_{jk}^{(s),0}}.
\]

### 3.2.4 核心输出

1. total 缺陷深度 × slit 响应矩阵；
2. k1 响应矩阵；
3. ms 响应矩阵；
4. P1–S1、P4–S4、P6–S6 等代表性匹配组合；
5. 1–2 组明显非匹配组合。

### 3.2.5 论证作用

若 \(P_j-S_j\) 的结构响应明显强于远离目标深度的 slit，可证明当前多狭缝系统不仅在 P0 中表现出 depth selectivity，而且这种空间选择性能够转化为实际缺陷响应。

若 MS 矩阵也表现出明显 slit-depth matching，可作为以下观点的辅助证据：

> MS detected contribution 并非完全与 first-scatter source depth 无关，其探测贡献同样受到深度选择通道调制。

E2 不用于独立分离 \(q\) 与 \(K\) 的变化。

---

## E3 缺陷诱导 detected source-response redistribution

### 3.3.1 实验目的

E3 合并原 E2 与 E3，构成本文最核心的机制实验之一。

目标是按照三个层级逐步建立证据：

1. 缺陷是否导致探测器端 total/k1/MS 可观测量变化；
2. 变化是否在 detected first-scatter depth coordinate 上与缺陷位置对应；
3. first scatter 位于 target region 的 MS contribution 是否对局部缺陷产生明显响应。

### 3.3.2 条件

- 正式分析：P1–P6 分别采用匹配狭缝 S1–S6，并以同一狭缝下的 P0 为对照；
- 详细机制展示：P0 vs P4、S4；
- center；
- Pj 的 target source region 固定为 \([z_{c,j}-5,z_{c,j}+5)\ \mathrm{mm}\)；P4 示例为：

\[
55\le z<65\ \mathrm{mm}.
\]

### 3.3.3 Level 1：探测器端直接可观测计数

比较：

\[
N^{total},\qquad N^{(1)},\qquad N^{(m)},
\]

以及：

\[
\frac{N_D-N_0}{N_0}.
\]

若 \(N^{(m)}\) 随缺陷发生稳定变化，可直接说明 MS 探测计数受到局部结构变化调制。

该结果本身尚不足以判定 MS 响应的空间来源。

### 3.3.4 Level 2：detected first-scatter depth response

分别统计：

\[
H^{(1)}(z),\qquad H^{(m)}(z).
\]

对每个 Pj–Sj 组合比较缺陷模体与 P0 在对应 target source region 内的变化；P4–S4 重点展示：

\[
55\le z<65\ \mathrm{mm}
\]

区域的变化。

若 MS profile 在该区域发生明显下降，可说明以该深度区域为 first-scatter source 的 MS contribution 对缺陷产生响应。

### 3.3.5 Level 3：front / target / behind 分区

分别统计：

\[
N_F^{(1)},\quad N_T^{(1)},\quad N_B^{(1)},
\]

\[
N_F^{(m)},\quad N_T^{(m)},\quad N_B^{(m)}.
\]

核心关注：

\[
\Delta N_T^{(1)},\qquad \Delta N_T^{(m)}.
\]

并辅助观察：

\[
\text{front: weak change}
\rightarrow
\text{target: decrease}
\rightarrow
\text{behind: increase}
\]

是否出现。

### 3.3.6 可直接支持的核心结论

E3 可直接支持：

> 首次散射源项位于目标区域的多重散射分量能够对该区域局部结构变化产生可测响应。

其基本实验条件为：

\[
N_T^{(m),D}\neq N_T^{(m),0},
\]

且变化在 first-scatter source coordinate 上与缺陷位置一致。

### 3.3.7 机制解释边界

任一 Pj/P0 detected first-scatter difference 均实际包含以下三项；P4–S4 的详细展示同样遵守该表达：

\[
\Delta N_k=
\sum_j\Delta q_jK_k^0(j)
+
\sum_jq_j^0\Delta K_k(j)
+
\sum_j\Delta q_j\Delta K_k(j).
\]

因此 E3 不能直接证明：

\[
|\Delta q|\gg|\Delta K|,
\]

也不能把 target profile 的下降全部归因于 \(q_j\) 下降。

front/target/behind 的空间模式、target-k1 与 target-MS 同方向变化可作为 first-scatter source redistribution 的**辅助机制证据**。

### 3.3.8 输出

- P1–P6 与各自 P0 baseline 的 total/k1/MS 总计数；
- P1–P6 匹配通道的 k1/MS `first_scatter_z` curves；
- 各深度 front/target/behind 的 k1/MS 分区统计；
- P4–S4 的详细 depth-wise ratio 或 relative difference。

---

## E4 多重散射的 first-scatter source-region decomposition

### 3.4.1 实验目的

在 E3 已证明 target-source MS 能够对局部结构产生响应后，E4 进一步分析：

> 不同 first-scatter source regions 产生的 MS 分量，在结构敏感性、稳定性和潜在成像作用上是否存在系统差异。

### 3.4.2 条件

- P1–P6 分别采用匹配狭缝 S1–S6，并以同一狭缝下的 P0 为对照；
- P4–S4 作为详细 source-region decomposition 示例；
- center；
- 统一采用预定义 \(\Omega_F/\Omega_T/\Omega_B\)。

### 3.4.3 分量

\[
N^{(m)}=N_F^{(m)}+N_T^{(m)}+N_B^{(m)}.
\]

计算：

\[
f_r^{(m)}=\frac{N_r^{(m)}}{N^{(m)}},
\qquad r\in\{F,T,B\},
\]

以及：

\[
C_r^{(m)}=
\frac{N_{r,D}^{(m)}-N_{r,0}^{(m)}}{N_{r,0}^{(m)}}.
\]

### 3.4.4 辅助统计

必要时分析：

- `det_energy`；
- `scatter_count_total`；
- first/last-scatter depth 或末次散射点空间投影。

这些变量只用于解释事件物理特征，不用于改变 front/target/behind 的 source-region 定义。当前事件数据不保存中间每次散射位置，因此不据此声称重建了完整 trajectory。

### 3.4.5 判读原则

E4 不预设：

- front MS 必然是噪声；
- behind MS 必然是噪声；
- non-target MS 必然是唯一或绝对主要背景；
- target MS 必然提高图像质量。

E4 只回答：不同 source regions 的 MS 是否具有不同的结构响应行为。

其真正的“应保留 / 应抑制”价值由 E6 的二维图像实验决定。

### 3.4.6 输出

- P1–P6 匹配通道下 front/target/behind MS 堆叠计数；
- 各深度三类 MS 的相对变化；
- P4–S4 的详细分解图；
- 必要时能谱/散射阶次辅助图。

---

## E5 目标源项多重散射的非局域输运与局部路径扰动

E5 分为 E5-A 和 E5-B 两部分。该实验服务于 framework 中：

\[
K_k^{(m)}(j)=\sum_{\gamma\in\Gamma_{j,k}^{(m)}}w_k(\gamma|j)
\]

的路径集合解释。

## 3.5.1 E5-A：固定 first-scatter source region 后的后续空间扩展

### 目的

直接展示：即使 detected gamma track 自身的 first scatter 已经被限制在一个局部 target source region，其 last scatter 仍可扩展至远大于该区域的空间范围。

### 条件

- P0；
- S4；
- center；
- 只保留：

\[
first\ scatter\in\Omega_T,
\]

\[
\texttt{scatter\_count\_total}\ge2.
\]

### 统计对象

当前实现使用每条 detected gamma track 已记录的：

\[
\mathbf r_{first}=(x_{first},y_{first},z_{first}),
\qquad
\mathbf r_{last}=(x_{last},y_{last},z_{last}).
\]

同时使用 `scatter_count_total` 表示该 track 自身的 Compton+Rayleigh 总散射次数。当前数据不保存 second scatter 或全部中间散射位置，因此 E5 只比较 first/last scatter summary，不进行逐路径重建。

### 输出

1. target-source MS 的 3D last-scatter point cloud / density；
2. x–z、y–z 等二维投影；
3. first-scatter target region 与 last-scatter spatial spread 的对照。

### 直接结论

E5-A 可直接支持：

> 给定局部 first-scatter source region 后，后续多重散射传播仍具有明显空间扩展，因此 \(K^{(m)}\) 应理解为对非局域路径集合进行统计边缘化后的条件响应。

---

## 3.5.2 E5-B：P4_off 对后续路径集合的局部扰动

### 目的

利用 E5-A 的 last-scatter distribution 选择一个偏离 directed primary beam、但位于 target-source MS 高概率末次散射区域的局部结构扰动，观察其对统计路径集合的影响。

### 条件

- P0 vs P4_off；
- S4；
- center；
- 重点分析：

\[
first\ scatter\in\Omega_T.
\]

### P4_off 的物理作用

P4_off 不直接位于 directed primary beam 的主照射范围内，因此其主要目的不是改变 target first-scatter source formation，而是扰动部分满足：

\[
\gamma\cap V_{off}\neq\varnothing
\]

的后续传播路径。

同时必须承认：P4_off 仍可能改变部分 k1 直达传播的衰减，因此实验不预设：

\[
\Delta N_T^{(1)}=0.
\]

### 空间差异统计

在相同空间 bin 下定义：

\[
H_0(\mathbf r),\qquad H_{off}(\mathbf r),
\]

并计算：

\[
\Delta H(\mathbf r)=H_{off}(\mathbf r)-H_0(\mathbf r),
\]

或：

\[
R_H(\mathbf r)=\frac{H_{off}(\mathbf r)}{H_0(\mathbf r)}.
\]

主要判断 P4_off 附近是否出现局部 density deficit / redistribution。

不以聚类算法作为正式结论依据。聚类可用于前期探索，但最终论文优先使用空间密度差分或统一 bin 的统计结果。

### 整体计数

比较：

\[
N_T^{(1)},\qquad N_T^{(m)},\qquad N^{total}
\]

在 P0/P4_off 中的变化。

### 预期物理解释

如果 P4_off 仅造成局部路径 density 明显变化，而整体 \(N_T^{(m)}\) 改变相对有限，可理解为：

\[
\Gamma_{affected}^{(m)}\subset\Gamma_T^{(m)},
\]

局部结构仅改变完整非局域路径集合的一部分，积分 MS 响应受到整体路径集合的统计稀释。

### E5 输出

- target-source MS 3D/2D last-scatter distribution；
- P4_off 几何位置与 path cloud 关系；
- P0/P4_off density difference；
- P0/P4_off target-source k1/MS/total 计数表。

---

## E6 基于 first-scatter source truth 的理想多重散射校正实验

### 3.6.1 实验定位

E6 是全文最重要的应用验证实验。

E6 **不提出实际可部署的校正算法**，也不在本文中求解线性 Boltzmann 方程，而是利用 Geant4 event truth 构造一个 ideal / oracle source-region-dependent MS correction benchmark。

其目的为：

1. 判断不同 first-scatter source-region MS 对二维图像分别产生怎样的作用；
2. 判断仅校正 front-source MS 是否已经具有明显收益；
3. 判断完整去除 non-target MS 是否显著优于仅去除 front MS；
4. 判断保留 target-source MS 相比完全去除所有 MS 是否具有净成像价值；
5. 为后续“浅层递推校正”与“粗重建 + 全局输运校正”两条算法路线提供选择依据。

---

### 3.6.2 代表深度

采用三个代表组合：

\[
P2-S2,\qquad P4-S4,\qquad P6-S6,
\]

分别代表浅中层、中层和深层，并与当前已完成的 P001 grid 批次保持一致。

每组缺陷模体均配套运行相同 grid 下的 P0–Sk baseline。

---

### 3.6.3 Grid

统一：

\[
9\times9,
\]

offset：

\[
\{-10,-7.5,-5,-2.5,0,2.5,5,7.5,10\}\ \mathrm{mm}.
\]

扫描时模体保持固定，圆形源面、接收准直结构和虚拟探测面随 pose 整体移动。每个 pose 使用 \(2.0\times10^7\) primary histories。

---

### 3.6.4 Event decomposition

对于每个扫描 pose \(p\)：

\[
N(p)=N^{(1)}(p)+N_F^{(m)}(p)+N_T^{(m)}(p)+N_B^{(m)}(p),
\]

其中：

\[
N^{(1)}(p)=N_F^{(1)}(p)+N_T^{(1)}(p)+N_B^{(1)}(p).
\]

E6 的主要校正对象是 **multi-scatter contribution**。一次散射事件整体保留，从而与未来基于输运模型估计 MS contribution 的方法方向保持一致。

---

### 3.6.5 Image A：Raw image

\[
I_{raw}(p)=N^{(1)}(p)+N_F^{(m)}(p)+N_T^{(m)}(p)+N_B^{(m)}(p).
\]

表示探测器原始 detected-hit total count image。

---

### 3.6.6 Image B：k1-only image

\[
I_{k1}(p)=N^{(1)}(p).
\]

用于构造“理想去除全部 MS”的传统方法上限。

---

### 3.6.7 Image C：Front-MS-corrected image

\[
I_F(p)=I_{raw}(p)-N_F^{(m)}(p),
\]

即：

\[
I_F(p)=N^{(1)}(p)+N_T^{(m)}(p)+N_B^{(m)}(p).
\]

该结果对应未来的**浅层递推路线**：已经重建的浅层 source region 可通过输运模型估计其向更深通道产生的 MS contribution，并逐层扣除。

对于第 \(l\) 层，可概念性写为：

\[
I_l^{seq}=I_l^{raw}-\sum_{r<l}\hat M_{r\rightarrow l}^{(m)}.
\]

当前 E6 不求解 \(\hat M\)，而直接以 Geant4 truth 中的 \(N_F^{(m)}\) 作为理想估计值。

---

### 3.6.8 Image D：Non-target-MS-corrected image

\[
I_{NT}(p)=I_{raw}(p)-N_F^{(m)}(p)-N_B^{(m)}(p),
\]

即：

\[
I_{NT}(p)=N^{(1)}(p)+N_T^{(m)}(p).
\]

该结果对应未来的**粗重建 + 全局输运校正路线**：

\[
\text{coarse reconstruction}
\rightarrow
\text{global transport estimation}
\rightarrow
\text{MS correction}.
\]

当前论文只利用 MC truth 给出该路线在理想估计条件下的性能上限。

---

### 3.6.9 可选：Target-source oracle image

辅助构造：

\[
I_T^{oracle}(p)=N_T^{(1)}(p)+N_T^{(m)}(p).
\]

该图像表示如果能够按照 first-scatter source region 对所有 detected gamma hits 完全选择时的理想 target-source image。

它同时删除了 non-target k1，因此不作为未来 MS correction 的直接对应方案，只作为 framework theoretical oracle。

---

### 3.6.10 MS source composition

对于 P0 baseline，并在必要时对缺陷模体同步统计：

\[
f_F^{(m)}=\frac{N_F^{(m)}}{N^{(m)}},
\]

\[
f_T^{(m)}=\frac{N_T^{(m)}}{N^{(m)}},
\]

\[
f_B^{(m)}=\frac{N_B^{(m)}}{N^{(m)}}.
\]

重点比较 S2、S4、S6。

其目的不是预先证明 front contribution 随深度增加，而是检验：

- 深层探测是否更容易受到浅层 first-scatter source MS 的累积影响；
- behind-source MS 是否同样重要；
- 只校正 front MS 是否足以接近完整 non-target correction。

---

### 3.6.11 图像质量指标

四类核心图像全部使用各 pose 的绝对 detected-hit 计数，不进行 P0 逐像素归一化。在 \(9\times9\) 网格中，缺陷 ROI 统一定义为：

\[
-7.5\ \mathrm{mm}\le\Delta x\le7.5\ \mathrm{mm},
\qquad
-7.5\ \mathrm{mm}\le\Delta y\le7.5\ \mathrm{mm}.
\]

边界点包含在缺陷 ROI 内；同一图像中其余扫描位置作为背景 ROI。不同缺陷深度及 Raw、k1-only、front-MS-corrected、non-target-MS-corrected 图像均使用完全相同的 ROI 划分。

#### Contrast

\[
Contrast=\frac{\mu_B-\mu_D}{\mu_B}.
\]

#### CNR

\[
CNR=\frac{|\mu_D-\mu_B|}{\sqrt{\sigma_D^2+\sigma_B^2}}.
\]

其中 \(\mu_D,\sigma_D\) 为缺陷 ROI 的均值和标准差，\(\mu_B,\sigma_B\) 为背景 ROI 的均值和标准差。

#### Target-MS retention gain

定义：

\[
G_{MS}=\frac{CNR(I_{NT})}{CNR(I_{k1})}.
\]

比较：

\[
I_{NT}=N^{(1)}+N_T^{(m)}
\]

与：

\[
I_{k1}=N^{(1)}.
\]

若：

\[
G_{MS}>1,
\]

说明在理想去除 non-target MS 后，保留 target-source MS 相比完全去除所有 MS 提供额外净成像收益。

若：

\[
G_{MS}\le1,
\]

则说明 target-source MS 虽然具有结构响应，但在当前系统几何与统计条件下未必转化为正的图像质量收益。该结果同样需要接受。

---

### 3.6.12 对未来算法路线的判读

#### 情况 A：front correction 已接近完整 correction

若：

\[
I_F\approx I_{NT},
\]

且深层条件下 front-source MS 占比较高，则优先支持：

\[
\text{shallow reconstruction}
\rightarrow
\text{front-source MS forward estimation}
\rightarrow
\text{progressive deeper-layer correction}.
\]

#### 情况 B：behind contribution 不可忽略

若 \(I_F\) 改善有限，而 \(I_{NT}\) 明显改善，则仅利用已重建浅层结构不足，更支持：

\[
\text{coarse global reconstruction}
\rightarrow
\text{global transport estimation}
\rightarrow
\text{iterative correction}.
\]

#### 情况 C：k1-only 不劣于保留 target MS

若：

\[
CNR(I_{k1})\ge CNR(I_{NT}),
\]

则论文应明确限制后续外推：target-source MS 能够携带结构响应，但当前系统条件下未形成额外的净成像收益。

---

# 4. 六项实验的证据链

\[
\boxed{E1:\ \text{system depth-response baseline}}
\]

\[
\downarrow
\]

\[
\boxed{E2:\ \text{defect depth--slit matching}}
\]

\[
\downarrow
\]

\[
\boxed{E3:\ \text{target-source MS responds to local structure}}
\]

\[
\downarrow
\]

\[
\boxed{E4:\ \text{MS response depends on first-scatter source region}}
\]

\[
\downarrow
\]

\[
\boxed{E5:\ \text{post-first-scatter transport is nonlocal}}
\]

\[
\downarrow
\]

\[
\boxed{E6:\ \text{source-conditioned MS correction benchmark}}
\]

对应论文结构可归纳为：

- **E1–E2：成像系统与深度选择性基础；**
- **E3–E5：source-response framework 的机制实验；**
- **E6：framework 对后续输运校正算法的应用指导。**

---

# 5. 建议图表安排

| 图表 | 实验 | 建议内容 | 主要作用 |
|---|---|---|---|
| 图 1 | Framework | \(q_j\rightarrow\gamma\rightarrow D_k\)；single/MS；first-scatter source regions | 理论变量与实验分类总图 |
| 图 2 | E1 | P0 下 S1–S6 detected `first_scatter_z` 2 mm profiles；S1/S3/S5 与 S2/S4/S6 双列展示 | 系统深度选择 baseline |
| 图 3 | E2 | P1–P6 × S1–S6 total/k1/MS response matrices | 缺陷深度与 slit 匹配 |
| 图 4 | E3 | P1–P6 匹配通道的 total/k1/MS 总计数 + k1/MS first-scatter depth profiles；P4–S4 详细展示 | 结构变化对 detected response 的作用 |
| 图 5 | E3/E4 | 各深度 front/target/behind 的 k1/MS 分区响应 | source-region-dependent response |
| 图 6 | E5-A | target-source MS last-scatter 3D/2D distribution | 非局域后续输运 |
| 图 7 | E5-B | P4_off 位置与 P0/P4_off density difference | 局部结构对路径子集的扰动 |
| 图 8 | E6 | Raw / k1-only / front-MS-corrected / non-target-MS-corrected images | 理想校正直观对比 |
| 图 9 | E6 | S2/S4/S6 的 \(f_F^{(m)},f_T^{(m)},f_B^{(m)}\) | 不同深度 MS source composition |
| 图 10 | E6 | 各策略 Contrast/CNR 与 \(G_{MS}\) | 未来算法方向 benchmark |
| 表 1 | 全部 | P0–P6、P4_off 与 S1–S6 定义 | 统一实验条件 |
| 表 2 | 全部 | total/k1/MS 与 \(\Omega_F/\Omega_T/\Omega_B\) 事件分类规则 | 统一统计口径 |
| 表 3 | E2 | depth × slit 的 total/k1/MS 相对响应矩阵 | 深度匹配定量结果 |
| 表 4 | E3/E4 | front/target/behind 的 k1/MS 计数、占比、相对变化 | 核心机制统计 |
| 表 5 | E5 | P0/P4_off target-source k1/MS/total 对比 | 路径局部扰动的积分响应 |
| 表 6 | E6 | Raw、k1-only、front-corrected、non-target-corrected 的 Contrast/CNR/\(G_{MS}\) | 理想校正性能 |

---

# 6. 建议仿真执行顺序

为减少重复运行并优先确认核心假设，建议按以下顺序执行：

### 第一阶段：系统 baseline 与深度匹配

1. P0 × S1–S6 center：完成 E1；
2. P1–P6 × S1–S6 center：完成 E2。

### 第二阶段：核心机制

3. 复用 P1–P6 × S1–S6 center 及对应 P0 数据，完成各深度匹配通道的 E3；
4. 基于同一批数据完成 E4 的 front/target/behind MS decomposition，并以 P4–S4 作为详细展示。

E3 和 E4 应复用 E1/E2 已生成的 event-level data，而不是重复仿真。

### 第三阶段：非局域路径实验

5. 先使用 P0–S4 target-source MS 完成 E5-A；
6. 根据 E5-A truth 确定 P4_off；
7. 运行 P4_off–S4，并与 P0 对照完成 E5-B。

### 第四阶段：二维 oracle correction benchmark

8. P2–S2、P4–S4、P6–S6 分别完成 9×9 grid；
9. 对应运行 P0–S2、P0–S4、P0–S6 同 grid baseline；
10. 使用 event truth 生成 E6 四类核心图像及 source composition / CNR / Contrast 结果。

---

# 7. 全文必须保持的论证边界

1. **E1 的 detected `first_scatter_z` profile 是 \(qK\) 型 detected source-response，不直接称为独立 \(K\) kernel。**
2. **当前 Geant4 first-scatter distribution 只覆盖 detected gamma hits，且同时包含 primary 与少量 secondary gamma，因此不能直接等同于裸源项 \(q_j\)。**
3. **E3 可证明 target-source MS 对局部结构变化产生响应，但不能单独证明变化全部来自 \(\Delta q\)。**
4. **“source redistribution”在当前论文中属于由多组空间和散射阶次统计支持的机制解释，而不是 \(q/K\) 的严格定量分解。**
5. **front / target / behind 始终按照当前 detected gamma track 自身的 first Compton/Rayleigh position 定义。**
6. **当前数据只保存每条 gamma track 的 first/last Compton/Rayleigh summary；last scatter 主要用于 E5 解释后续输运 \(\gamma\) 的非局域性，不用于重新定义 source region，也不代表已重建全部中间路径。**
7. **E4 不预设 non-target MS 必然是噪声或绝对主要背景，其实际成像影响由 E6 判断。**
8. **E5 不把 P4_off 解释为 acceptance volume 内结构的直接投影，而是用于研究局部结构对非局域 path ensemble 的扰动。**
9. **E7 原缺陷尺寸实验删除，不再尝试通过尺寸变化严格证明 \(\Delta q\) 主导或 \(\Delta K\) 可忽略。**
10. **E6 是基于 Monte Carlo truth 的 oracle benchmark，不等同于已经提出实际可部署的校正算法。**
11. **E6 的主要校正对象是 MS contribution；未来方法不以简单删除所有 non-target k1 为目标。**
12. **后续若引入线性 Boltzmann 方程，其角色应是根据已知/估计结构计算不同 first-scatter source regions 对探测器的 MS contribution；E6 提供该估计在理想准确情况下的性能上限和算法方向判据。**
13. **`scatter_count_total` 是当前 detected gamma track 自身的 Compton+Rayleigh 总次数；secondary gamma 不继承 parent track 的散射历史。**
14. **理论 \(q_j\) 保持 primary-driven source 含义；secondary-gamma detected contribution 作为未显式分离的小比例附加贡献保留在计数中。**

---

# 8. 当前实验设计最终定位

V2 实验设计不再试图通过单个实验完整解释所有多重散射路径变化，而是形成以下层次：

\[
\text{system selectivity}
\rightarrow
\text{structure selectivity}
\rightarrow
\text{source-region-dependent MS response}
\rightarrow
\text{nonlocal transport interpretation}
\rightarrow
\text{ideal source-conditioned correction}.
\]

其中论文最稳健的实验主张仍为：

> 以目标敏感区域为首次散射源项的多重散射分量能够对局部材料结构变化产生可测响应。多重散射事件是否具有目标相关性不能仅由散射阶次决定，还与首次散射源项的空间归属及后续非局域输运共同相关。

E6 则进一步回答该框架的工程意义：当不同 first-scatter source-region MS contributions 能够被理想估计时，选择性保留 target-source MS、校正 non-target MS 是否能够改善成像，并由实验结果判断后续更适合发展浅层递推校正还是基于粗重建的全局输运校正。
