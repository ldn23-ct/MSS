# 源项响应框架下的 X 射线背散射信号机制（修订版 V2）

## 0. 修订目的与框架边界

本版本用于替代原“源项响应框架”中的单索引响应模型，并与当前 Geant4 数据实际可观测量保持一致。

本次修订的核心变化为：

1. 将首次散射源项与首次散射后的输运过程明确分离；
2. 以首次散射位置索引 $j$ 表征源项空间，以路径变量 $\gamma$ 表征首次散射后的可能输运历史；
3. 不再把后续多重散射过程简单表示为独立体素响应的求和；
4. 明确当前 Geant4 中记录的 detected first-scatter distribution 是“源项经系统响应加权后的探测贡献”，而不是裸源项 $q_j$；
5. 将“目标区域多重散射携带局部结构响应”作为当前数据可直接支持的结论；
6. 将“小缺陷条件下响应变化主要由源项扰动驱动”降为基于现有结果提出的机制解释/推测，而非由当前数据严格证明的结论。

该框架的目的不是完整求解多重散射输运灵敏度问题，而是建立一种适合事件级蒙特卡罗分析的物理分解方式，用于区分散射阶次与首次散射源项归属对探测信号的共同作用。

---

# 1. 基本物理图景

在定向窄束照射条件下，初级光子在发生第一次散射前保持沿入射束方向传播，因此首次散射位置被限制在有限束流横截面穿过的空间范围内。理论表达中将该有限横截面窄束简写为 pencil-beam path，并以第 $j$ 个空间单元表示一个潜在的首次散射源项位置。

第一次散射发生以后，光子可能直接进入探测器，也可能继续发生第二次、第三次直至第 $n$ 次散射。此时后续相互作用位置可以扩展到远大于笔形束横截面的空间范围。对于一个已经在 $j$ 处形成的首次散射源项，后续输运历史可以表示为

$$
\gamma: j\rightarrow i_2\rightarrow i_3\rightarrow\cdots\rightarrow i_n\rightarrow D_k,
$$

其中 $D_k$ 表示第 $k$ 个探测/准直通道。

因此，本框架将完整探测过程分成两层：

$$
\text{directed primary beam}\rightarrow q_j\rightarrow \gamma\rightarrow D_k.
$$

其中，$q_j$ 负责描述首次散射源项的空间形成，$\gamma$ 负责描述该源项形成后的传播、再次散射、衰减、准直接受与最终探测过程。

---

# 2. 首次散射源项的定义

定义 $q_j$ 为单位入射历史数下，初级光子在位置 $j$ 形成首次散射源项的强度。其物理上由初级光子到达该位置的通量以及局部材料相互作用概率共同决定，可概念性写为

$$
q_j\propto \Phi_j\,\Sigma_{\mathrm{scat},j},
$$

其中 $\Phi_j$ 为到达位置 $j$ 的初级光子通量，$\Sigma_{\mathrm{scat},j}$ 为与首次散射形成相关的宏观相互作用量。

在本文所研究的 PMMA-空气缺陷条件下，当笔形束路径上的局部 PMMA 被空气替代时，该区域的首次散射形成能力显著降低，因此从物理上有

$$
q_j^{D}<q_j^{0},\qquad j\in D,
$$

其中上标 $0$ 表示均匀 PMMA 模体，上标 $D$ 表示含空气缺陷模体。

需要注意的是，本文现有 Geant4 数据并未统计所有初级光子的首次散射位置，因此 $q_j$ 本身并不是当前实验直接观测的量。本文对 $q_j$ 的使用主要作为理论中的源项变量。

---

# 3. 路径响应与单次/多重散射通道

## 3.1 路径权重

对于已经在 $j$ 处形成的首次散射源项，设其所有最终可被第 $k$ 个通道探测的可能输运路径集合为 $\Gamma_{j,k}$。对任一路径 $\gamma$，定义路径权重

$$
w_k(\gamma|j),
$$

其综合表示该路径发生并最终被第 $k$ 个通道记录的概率权重。该权重包含首次散射后的方向变化、后续相互作用、能量变化、介质衰减、几何接受、准直条件以及探测效率等因素。

## 3.2 单次散射响应核

对于仅在 $j$ 处发生一次散射后直接到达第 $k$ 个探测通道的路径集合 $\Gamma_{j,k}^{(1)}$，定义

$$
K_k^{(1)}(j)
=
\sum_{\gamma\in\Gamma_{j,k}^{(1)}}w_k(\gamma|j).
$$

## 3.3 多重散射响应核

对于在 $j$ 处首次散射后，又发生一次或多次后续散射并最终到达第 $k$ 个探测通道的路径集合 $\Gamma_{j,k}^{(m)}$，定义

$$
K_k^{(m)}(j)
=
\sum_{\gamma\in\Gamma_{j,k}^{(m)}}w_k(\gamma|j).
$$

因此，$K_k^{(m)}(j)$ 是一个以首次散射源项位置 $j$ 为条件、对所有后续多重散射输运历史进行边缘化后的统计响应量。它并不对应某个单一后续散射体素，也不要求逐条解析后续路径。

---

# 4. 探测计数模型

在上述定义下，第 $k$ 个通道的期望探测 hit 计数写为

$$
N_k
=
\sum_j q_j
\left[
K_k^{(1)}(j)+K_k^{(m)}(j)
\right]
+\eta_k,
$$

其中 $\eta_k$ 表示统计涨落、未建模背景及其他非理想项。

该表达式的物理意义为：

- $q_j$ 决定笔形束路径上各首次散射位置能够产生多少源项；
- $K_k^{(1)}(j)$ 决定该源项通过单次散射路径进入探测器的概率权重；
- $K_k^{(m)}(j)$ 决定该源项通过所有可能多重散射路径进入探测器的综合概率权重。

单次散射与多重散射在该框架中不是“有效信号”和“背景”的先验划分，而是同一首次散射源项经不同传播历史到达探测器的两类通道。

---

# 5. 当前 Geant4 实际可观测量

## 5.1 事件与散射阶次的实现口径

当前 Geant4 实现采用 detector-hit 模型。每个模拟 event 产生一个 source primary gamma，但正式事件表中的一行表示一个 detected gamma hit，而不是一个唯一的 source primary gamma。所有到达虚拟探测面的 gamma track 均可被记录，包括 primary gamma 与 secondary gamma；同一模拟 event 因而可以产生零条、一条或多条 detected-hit 记录，每条 gamma track 最多记录第一次有效 detector crossing。

每条 gamma track 独立维护自身在整个 Geant4 world 中的 Compton/Rayleigh 散射历史，该记录不限定为 PMMA–空气模体内部。对于 secondary gamma，其散射阶次从该 track 产生时重新计数，不继承 parent track 的散射历史。定义

$$
n_{\mathrm{scat}}
=
n_{\mathrm{Compton}}+n_{\mathrm{Rayleigh}}
=\texttt{scatter\_count\_total}.
$$

当前事件分类为：

$$
\text{k1}: n_{\mathrm{scat}}=1,
\qquad
\text{MS}: n_{\mathrm{scat}}\ge2,
$$

而用于 total/k1/MS 分析的 total 计数仅包含 $n_{\mathrm{scat}}\ge1$ 的 detected gamma hits。`first_scatter_*` 与 `last_scatter_*` 分别表示当前 detected gamma track 自身第一次和最后一次 Compton 或 Rayleigh 相互作用的位置。因此，对 secondary gamma 而言，这些位置不是其 parent primary gamma 的首次/末次散射位置。

## 5.2 探测贡献与理论源项的关系

本文蒙特卡罗数据记录的是最终被探测 gamma track 的首次散射位置，而不是所有 source primary gamma 的首次散射位置。因此，按照首次散射位置 $j$ 统计得到的分布并不直接等于 $q_j$。

定义单次散射和多重散射的 detected source-response contribution：

$$
R_k^{(1)}(j)=q_jK_k^{(1)}(j),
$$

$$
R_k^{(m)}(j)=q_jK_k^{(m)}(j).
$$

则

$$
N_k
=
\sum_j\left[R_k^{(1)}(j)+R_k^{(m)}(j)\right]+\eta_k.
$$

因此，Geant4 中以 detected gamma hits 回溯得到的 `first_scatter_z` 分布，对应的是 $R_k^{(1)}(j)$、$R_k^{(m)}(j)$ 或二者之和，而不是裸源项 $q_j$。

理论中的 $q_j$ 仍用于描述由定向 primary beam 驱动的首次散射源项。当前数据中占比较小的 detected secondary-gamma contribution 不另设 source-type 索引，而作为未显式分离的附加探测贡献保留在 $N_k$ 与实际统计的 $R_k^{(s)}(j)$ 中。因此，$q_jK_k^{(s)}(j)$ 是本文采用的 primary-dominated source-response 模型；在解释 secondary gamma 的 track-local first scatter 时，应将这一处理视为模型近似边界，而不是严格的逐来源恒等分解。

这一点对后续论文表述具有约束：

- 可以直接讨论“某 first-scatter source region 对最终探测计数的贡献”；
- 可以比较不同模体中该贡献的变化；
- 不能仅凭 detected first-scatter distribution 直接定量分离 $q_j$ 与 $K_k(j)$ 的各自变化。

---

# 6. 目标区域/非目标区域与散射阶次的联合分解

将首次散射源项空间划分为目标敏感区域 $\Omega_T$ 与非目标区域 $\Omega_N$：

$$
\Omega=\Omega_T\cup\Omega_N.
$$

则探测计数可写为

$$
N_k
=
N_{T,k}^{(1)}
+N_{T,k}^{(m)}
+N_{N,k}^{(1)}
+N_{N,k}^{(m)}
+\eta_k,
$$

其中

$$
N_{T,k}^{(1)}
=
\sum_{j\in\Omega_T}q_jK_k^{(1)}(j),
$$

$$
N_{T,k}^{(m)}
=
\sum_{j\in\Omega_T}q_jK_k^{(m)}(j),
$$

$$
N_{N,k}^{(1)}
=
\sum_{j\in\Omega_N}q_jK_k^{(1)}(j),
$$

$$
N_{N,k}^{(m)}
=
\sum_{j\in\Omega_N}q_jK_k^{(m)}(j).
$$

这里“目标区域多重散射”在事件统计上特指：**detected gamma track 自身的第一次 Compton/Rayleigh 位于 $\Omega_T$，该 track 的总散射次数不少于 2，并最终被探测的 hit**。它并不要求后续所有散射位置均位于目标区域。对于占主导的 primary gamma，该分类对应理论中的首次散射源项归属；对于 secondary gamma，则对应 track-local first-scatter region。

这一分解同时保留两种信息：

1. 散射阶次：single / multiple；
2. 首次散射源项归属：target / non-target。

它是本文当前最核心、且可通过事件级蒙特卡罗数据直接实现的分析框架。

---

# 7. 对局部结构扰动的严格表达

设均匀模体状态为 $M_0$，含缺陷模体状态为 $M_D$。对象结构变化既可能改变首次散射源项，也可能改变后续路径集合及路径权重，因此

$$
q_j^0\rightarrow q_j^D=q_j^0+\Delta q_j,
$$

$$
K_k^0(j)\rightarrow K_k^D(j)=K_k^0(j)+\Delta K_k(j).
$$

为简化符号，令

$$
K_k(j)=K_k^{(1)}(j)+K_k^{(m)}(j).
$$

则严格的计数变化为

$$
\Delta N_k
=
\sum_j
\left[
q_j^DK_k^D(j)-q_j^0K_k^0(j)
\right],
$$

展开得到

$$
\Delta N_k
=
\sum_j\Delta q_jK_k^0(j)
+
\sum_jq_j^0\Delta K_k(j)
+
\sum_j\Delta q_j\Delta K_k(j).
$$

三项分别表示：

- **source-term perturbation**：$\sum_j\Delta q_jK_k^0(j)$；
- **transport-response perturbation**：$\sum_jq_j^0\Delta K_k(j)$；
- **coupling term**：$\sum_j\Delta q_j\Delta K_k(j)$。

当前数据不能严格将三项分离，因此本文不应把“$\Delta q$ 主导”作为由实验直接证明的结论。

---

# 8. 空间体素变化与路径响应：理论解释边界

若对象中某一体素 $i$ 的材料或结构发生变化，它可能改变经过该区域的部分路径 $\gamma$ 的发生概率、能量、方向和后续输运过程，从而导致 $K_k(j)$ 发生变化。

但多重散射路径具有显著的顺序依赖性，一条完整路径通常为

$$
\gamma=(j,i_2,i_3,\ldots,i_n),
$$

因此不宜把 $K_k^{(m)}$ 简化为若干独立体素影响的线性求和。单一体素 $i$ 的变化会通过条件输运过程改变一组可能路径，而这些路径在均匀模体和缺陷模体之间也不存在严格的一一对应关系。

因此，本论文不尝试定量建立

$$
i\rightarrow\Delta\gamma\rightarrow\Delta K
$$

的灵敏度模型。路径变量 $\gamma$ 在本文中主要用于说明 $K_k^{(m)}(j)$ 的统计物理含义，而不是作为必须逐路径求解的实验变量。

---

# 9. “源项主导”作为机制推测，而非严格结论

虽然当前数据不能直接分离 $\Delta q$ 与 $\Delta K$，但对于本文的小尺寸低密度空气缺陷，可以提出如下机制推测：

> 局部空气缺陷直接作用于笔形束路径上的首次散射源项，而对多重散射响应核的影响则通过改变后续输运路径集合间接实现。因此，在当前缺陷尺度与几何条件下，探测响应变化可能具有较强的首次散射源项重分布特征，$\Delta q$ 可能是重要甚至主要贡献之一，而 $\Delta K$ 构成不可忽略但难以独立分离的输运修正。

该推测不能仅凭“小缺陷体积远小于多重散射空间”得到。严格来说，小体积并不必然意味着小 $\Delta K$，因为一个小区域也可能位于部分高权重路径上。

因此，本文对源项主导机制的支持应主要来自现有数据中的间接证据，而不是来自体积尺度的简单比较。

---

# 10. 使用现有数据可提供的辅助性论证

## 10.1 目标区 detected first-scatter contribution 的强烈下降

若在缺陷对应区域 $D$ 观察到

$$
R_{k,D}^{(m)}(j)\ll R_{k,0}^{(m)}(j),\qquad j\in D,
$$

则可直接说明：原本以该区域为首次散射源项、并通过多重散射路径进入探测器的贡献在材料替换后显著下降。

该结果直接支持“目标区域多重散射分量对局部结构变化具有响应”，并与局部首次散射源项显著减弱的物理解释一致，但不能单独证明 $\Delta q$ 在定量上占主导。

## 10.2 target-k1 与 target-ms 同方向变化

若缺陷出现后同时观察到

$$
\Delta N_{T,k}^{(1)}<0,
$$

$$
\Delta N_{T,k}^{(m)}<0,
$$

则单次与多重散射两类不同传播通道在同一首次散射源项区域表现出一致的结构响应。由于两者共享首次散射源项但具有不同后续传播历史，这一共同变化可以作为 first-scatter source modulation 的间接支持。

## 10.3 沿笔形束方向的 front-target-behind 空间模式

在空气缺陷位于笔形束路径的情况下，可比较缺陷前方、缺陷区域及缺陷后方的 detected first-scatter contribution。

若观察到近似模式

$$
\text{front: weak change}
\rightarrow
\text{target: strong decrease}
\rightarrow
\text{behind: increase},
$$

则该空间模式与初级束源项重分布具有一致性：缺陷前方初级光子尚未经过缺陷，目标区域的首次散射形成能力显著下降，而缺陷后方可能因前方衰减减弱而获得更多初级光子通量。

该模式不能排除 $K$ 的变化，但可作为源项重分布解释的辅助证据。

## 10.4 多重散射路径的非局域性

通过 `last_scatter_z`、末次散射点空间投影、`scatter_count_total` 或其他现有事件历史变量展示多重散射事件在首次散射后扩展至较大的空间范围，可以证明 $K_k^{(m)}(j)$ 是一个非局域统计响应量。当前数据只保留各 detected gamma track 的 first/last scatter summary，不据此声称重建了全部中间散射路径。

这一结果用于解释为什么“首次散射源项归属”与“后续散射位置”需要在理论上分开，但不能单独作为 $\Delta K$ 很小的证据。

---

# 11. 当前数据能够直接支持的核心结论

当前仿真最稳健的主张应限定为：

> 以目标敏感区域为首次散射源项的多重散射分量能够对局部材料结构变化产生可测响应。因此，多重散射事件并不因散射阶次增加而必然失去目标相关信息，其有效性还与首次散射源项的空间归属有关。

这一结论不依赖于证明

$$
|\Delta q|\gg|\Delta K|.
$$

只要通过事件级数据证明

$$
N_{T,k}^{(m),D}\neq N_{T,k}^{(m),0}
$$

且变化与缺陷空间位置和结构改变具有明确对应关系，即可成立。

---

# 12. 当前不能严格声称的内容

基于现有数据，论文不宜直接声称以下结论：

1. 多重散射响应变化完全由 $q_j$ 变化导致；
2. 小缺陷条件下 $K_k^{(m)}(j)$ 可以视为不变；
3. $|\Delta q|\gg|\Delta K|$ 已被当前仿真严格证明；
4. 所有非目标区域多重散射都是纯背景；
5. 非目标区域一定是多重散射背景的唯一或绝对主要来源；
6. detected first-scatter distribution 等价于裸源项 $q_j$；
7. 多重散射响应可以被简单表示为各后续空间体素独立贡献的线性和；
8. detected-hit 计数等价于唯一 source primary gamma 的计数；
9. secondary gamma 的 track-local first scatter 等价于 parent primary gamma 的首次散射源项位置。

这些表述若需要使用，应改成条件性、推测性或待进一步研究的表达。

---

# 13. 对“多重散射是噪声”的修订解释

传统处理中常写为

$$
N_k^{(1)}\rightarrow\text{signal},
$$

$$
N_k^{(m)}\rightarrow\text{background/noise}.
$$

本框架提出的修订是：散射阶次不足以单独判定事件是否携带目标结构信息。至少需要进一步考虑首次散射源项的空间归属。

| 首次散射源项归属 | 单次散射 | 多重散射 |
|---|---|---|
| 目标敏感区域 | 目标相关响应 | 可携带目标相关结构响应 |
| 非目标区域 | 可能构成非目标贡献 | 可能构成重要背景贡献 |

因此，本文更适合提出：

> 多重散射背景的形成与其非局域传播特征和首次散射源项空间混合有关。目标敏感区域产生的多重散射分量可保留局部结构变化信息，而非目标区域产生的多重散射分量可能降低目标响应的空间选择性和对比度。

该表述避免未经数据充分验证就把所有非目标多重散射定义为“主要背景来源”。

---

# 14. 图像质量优化思路的修订

原先“从剔除多重散射转向非目标源项抑制”的策略可以保留为研究方向，但应降低为由机制分析引出的后续方法思想。

可定义目标相关探测响应占比

$$
R_k^{T}
=
\frac{
N_{T,k}^{(1)}+N_{T,k}^{(m)}
}{
N_k
}.
$$

或者定义目标/非目标响应比

$$
\mathcal{R}_k
=
\frac{
N_{T,k}^{(1)}+N_{T,k}^{(m)}
}{
N_{N,k}^{(1)}+N_{N,k}^{(m)}+\eta_k
}.
$$

后续优化目标可表述为：提高目标首次散射源项相关响应在总探测计数中的占比，同时降低非目标区域贡献造成的空间混合，而不是仅依据散射次数对事件进行整体剔除。

这一策略需要通过后续校正或重建实验验证，不能由当前机制分析直接视为已经成立的性能结论。

---

# 15. 对现有 E1-E8 实验设计的影响

## E1：均匀模体多狭缝深度响应

原“深度响应核 $K_k$”的表述应收紧。由于当前统计的是被探测事件的 first-scatter distribution，直接得到的是

$$
R_k(j)=q_jK_k(j),
$$

更适合称为：

- detected first-scatter depth response；
- effective depth-response profile；
- detected source-response profile。

除非另行获得独立 $q_j$ 分布，否则不宜把该曲线直接称为纯 $K_k(j)$。

## E2：局部结构引起的 source-response perturbation

E2 不再定位为“直接验证 $q_j$ 下降”，而应分析 P0/P4 的 detected first-scatter contribution 在 front/target/behind 区域的变化，并讨论其与 source redistribution 机制的一致性。

## E3：目标区域多重散射结构响应

E3 仍是核心实验。通过 first-scatter location 定义 $\Omega_T$，直接比较

$$
N_T^{(1)},\quad N_T^{(m)},\quad N_N^{(1)},\quad N_N^{(m)}
$$

在 P0/P4 间的变化，用于直接证明 target-source multiple scattering 对局部结构变化具有响应。

## E4：非目标多重散射来源分解

E4 可继续比较 ms_front、ms_target、ms_behind，但结论应由数据决定。不能预设“ms_non-target 是主要背景来源”；应分析各分量的缺陷敏感性、稳定性及对图像对比度的影响。

## E5：缺陷深度与 slit 匹配

E5 可用于说明不同准直通道对不同 first-scatter source depth 的探测选择性。这里同样优先使用 effective/detected response，而不是未经修正的纯 $K$。

## E6：acceptance volume 边界

E6 仍可用于限定“acceptance volume 内任意结构均能直接投影到多重散射计数”的过强解释，但应避免把结果扩大为一般性的路径灵敏度结论。

## E7：小缺陷条件下的机制辅助分析

E7 不再承担“严格证明 $\Delta q$ 主导、$\Delta K$ 可忽略”的任务。更合适的作用是：通过缺陷尺寸变化，观察 source-response perturbation 的线性程度、front/target/behind 重分布以及不同散射阶次响应是否保持一致，由此经验性讨论源项主导解释的适用范围。

## E8：非目标响应抑制

E8 属于框架的应用验证。其目标应写为检验：基于 source-region information 的权重或校正是否能够在保留 target-related multiple-scattering response 的同时降低非目标贡献。

---

# 16. 修订后的论文核心主张

## 16.1 最稳健的主张

> 本文提出一种基于首次散射源项归属的 X 射线背散射信号分析框架，将首次散射源项的空间形成与其后的单次/多重散射输运过程进行分离。事件级蒙特卡罗结果表明，以目标敏感区域为首次散射源项的多重散射分量能够对局部材料结构变化产生可测响应，说明散射阶次本身不足以判定背散射事件是否携带目标相关信息。

## 16.2 关于机制的谨慎扩展

> 目标区域单次与多重散射分量的共同响应，以及沿笔形束方向出现的 first-scatter contribution 重分布，与局部首次散射源项变化驱动探测响应的物理图景一致。由于当前数据无法独立分离源项扰动与后续输运核扰动，该解释应视为基于现有结果的机制推测，而非严格的定量归因。

## 16.3 关于背景来源的表述

> 非目标区域首次散射源项经复杂多重散射路径进入探测器，会增加测量信号的空间混合并降低目标响应选择性。不同非目标多重散射分量对图像背景的实际贡献需要通过事件分解和图像指标进一步定量评价。

---

# 17. 修订后的创新点

## 创新点 1：建立首次散射源项与后续输运路径分离的分析框架

将探测计数描述为首次散射源项 $q_j$ 与以该源项为条件的单次/多重散射响应核 $K_k^{(1)}(j)$、$K_k^{(m)}(j)$ 的共同作用，并用路径集合 $\Gamma_{j,k}$ 明确后续多重散射响应的非局域统计性质。

## 创新点 2：建立源项归属与散射阶次的联合事件分解

将探测信号划分为目标单次散射、目标多重散射、非目标单次散射和非目标多重散射四类，使“散射阶次”与“首次散射源项空间归属”成为相互独立的两个分析维度。

## 创新点 3：证明目标源项多重散射分量具有局部结构响应

利用事件级蒙特卡罗 first-scatter history，直接比较含/不含缺陷条件下 $N_{T,k}^{(m)}$ 的变化，验证首次散射源项位于目标区域的多重散射事件并非纯随机背景，而能够反映局部结构变化。

## 创新点 4：提出 source redistribution 机制解释并明确证据边界

结合 target-k1/target-ms 的共同变化以及 front-target-behind 的空间响应模式，提出局部首次散射源项重分布可能是当前小缺陷响应的重要机制，同时明确当前数据不能严格分离 $\Delta q$ 与 $\Delta K$。

## 创新点 5：为基于源项归属的信息保留与背景抑制提供物理依据

基于目标/非目标源项分解，提出后续校正与重建不应仅按照散射次数整体剔除事件，而应进一步评估不同首次散射源项区域对目标结构响应和背景形成的贡献。

---

# 18. 推荐用于 Methods 的理论层次

后续正式论文 Methods 中，理论部分建议只保留以下四层，不需要把本内部 framework 的全部讨论写入正文：

### Layer 1：源项定义

$$
q_j
$$

首次散射源项及其受笔形束几何约束的空间含义。

### Layer 2：条件输运响应

$$
K_k^{(s)}(j)
=
\sum_{\gamma\in\Gamma_{j,k}^{(s)}}w_k(\gamma|j),
\qquad s\in\{1,m\}.
$$

说明后续路径被统计边缘化进响应核。

### Layer 3：探测计数与可观测贡献

$$
N_k
=
\sum_jq_j\left[K_k^{(1)}(j)+K_k^{(m)}(j)\right]+\eta_k,
$$

以及

$$
R_k^{(s)}(j)=q_jK_k^{(s)}(j).
$$

明确 MC 中实际统计的是 detected gamma-hit contribution $R$ 而不是裸 $q$，并说明 primary/secondary gamma 共存时采用 primary-dominated 模型近似。

### Layer 4：target/non-target decomposition

$$
N_k
=
N_{T,k}^{(1)}+N_{T,k}^{(m)}+N_{N,k}^{(1)}+N_{N,k}^{(m)}+\eta_k.
$$

这四项直接对应后续事件分类和 Results。

关于 $\Delta q$ 与 $\Delta K$ 的展开，更适合在 Methods 末尾或 Discussion 中作为机制解释的数学辅助，而不应成为核心模型成立的必要前提。

---

# 19. 一句话题眼（修订）

> X 射线背散射中的多重散射响应具有非局域传播特征，但其探测贡献仍可按照首次散射源项的空间归属进行分解；目标区域源项产生的多重散射分量能够保留局部结构响应。
