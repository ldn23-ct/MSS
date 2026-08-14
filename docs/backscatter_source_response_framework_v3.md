# 源项响应框架下的 X 射线背散射信号机制（V3.1）

## 0. 文档定位与本次修订

本文档在 `backscatter_source_response_framework_v3.md` 基础上修订，用于统一后续理论表述、事件级 Monte Carlo 分析和实验结果解释。

V3.1 保留 V3 的核心物理分解：

\[
\text{primary pencil beam}
\rightarrow
q_j
\rightarrow
\gamma
\rightarrow
D_k,
\]

其中 \(q_j\) 表示由初级束驱动的首次散射源项，\(\gamma\) 表示首次散射之后的传播与再次相互作用历史，\(D_k\) 表示第 \(k\) 个狭缝/探测通道。

本次修订主要完成以下调整：

1. 将原 E1–E6 的证据链压缩为三个实验层级：
   - **E1：均匀模体下的系统响应基线与散射空间特征；**
   - **E2：局部缺陷的可观测响应及首次散射源区机制分解；**
   - **E3：基于 source truth 的成像作用/理想基准。**
2. 将 first-scatter / last-scatter 空间对比并入 E1，不再作为独立实验；
3. 将原缺陷深度匹配、target-source MS 响应和 front/target/behind 分解合并到 E2；
4. 明确 grid 条件下的 target source 采用**缺陷三维几何区域**定义，而不是仅按目标深度层定义；
5. 保持理论中的 \(q_j\) 为 primary-driven source term，同时使事件统计口径与当前 Geant4 实际实现一致；
6. 继续区分“数据直接支持的结论”与“由结果提出的机制解释”，不尝试用现有数据严格分离 \(\Delta q\) 与 \(\Delta K\)。
7. 收敛 E2 的定量分析指标：E2-B 保留整体计数相对变化；E2-D 以 source-region 相对计数变化和区域内 total variation distance 为核心，source-region fraction 仅作为可选组成指标，深度质心不再作为常规指标。

本文档聚焦理论和框架边界，不规定具体绘图格式、文件名和数据处理脚本。执行层细节由实验指导文档统一规定。

---

# 1. 基本物理图景

在窄束/准笔形束照射条件下，初级光子在形成首次散射源项之前主要沿入射束路径传播，因此首次散射源项在空间上受到初级束照射区域的约束。

设初级束路径上的空间位置由索引 \(j\) 表示，则位置 \(j\) 可视为一个潜在的首次散射源项位置。首次散射发生之后，光子可能直接经准直结构进入探测器，也可能继续发生后续相互作用。对一个已经在 \(j\) 处形成的首次散射源项，其后续传播历史可概念性表示为

\[
\gamma:
j\rightarrow i_2\rightarrow i_3\rightarrow\cdots\rightarrow i_n\rightarrow D_k.
\]

因此，完整探测过程分为两层：

\[
\text{source formation}
\rightarrow
\text{post-first-scatter transport}.
\]

其中：

- \(q_j\) 描述首次散射源项的形成；
- \(\gamma\) 描述首次散射后的传播、再次散射、衰减和准直接受；
- \(D_k\) 表示第 \(k\) 个探测通道。

这一分解的核心作用是把“首次散射发生在哪里”与“首次散射之后如何到达探测器”区分开。

---

# 2. Primary-driven 首次散射源项

定义 \(q_j\) 为单位入射历史下，初级光子在位置 \(j\) 形成首次散射源项的强度。概念上可写为

\[
q_j\propto \Phi_j\,\Sigma_{\mathrm{scat},j},
\]

其中：

- \(\Phi_j\) 为到达位置 \(j\) 的初级光子通量；
- \(\Sigma_{\mathrm{scat},j}\) 为与首次散射形成相关的局部宏观相互作用量。

对于 PMMA–空气缺陷，当初级束路径上的局部 PMMA 被空气替代时，目标区域的首次散射形成能力会发生明显变化，因此从物理上可预期

\[
q_j^{D}<q_j^{0},
\qquad j\in D,
\]

其中上标 \(0\) 表示均匀 PMMA，上标 \(D\) 表示含空气缺陷的模体。

需要区分理论变量与 Monte Carlo 可观测量：

> 当前数据并未独立统计“所有入射 primary gamma 在每个位置形成的裸首次散射源项”，因此 \(q_j\) 不是当前实验直接观测的量。

本文中的 \(q_j\) 用于建立理论结构，不以 detected first-scatter histogram 直接替代。

---

# 3. 条件输运响应

## 3.1 路径集合

对已经在 \(j\) 处形成的首次散射源项，设其最终可被第 \(k\) 个通道探测的路径集合为

\[
\Gamma_{j,k}.
\]

对任一路径 \(\gamma\)，定义路径权重

\[
w_k(\gamma|j),
\]

其综合表示首次散射以后该路径发生并最终被第 \(k\) 个通道记录的统计权重。

## 3.2 单次与多重散射响应

将探测路径按散射阶次分为单次散射类和多重散射类。相应的条件响应写为

\[
K_k^{(1)}(j)
=
\sum_{\gamma\in\Gamma_{j,k}^{(1)}}
w_k(\gamma|j),
\]

\[
K_k^{(m)}(j)
=
\sum_{\gamma\in\Gamma_{j,k}^{(m)}}
w_k(\gamma|j).
\]

这里的 \(K_k^{(m)}(j)\) 表示：给定首次散射源项位置 \(j\) 后，对所有后续多重散射输运历史进行统计边缘化后的综合响应。

它不是：

- 某个单一后续散射体素的响应；
- 各后续体素独立贡献的简单线性求和；
- 可由 last-scatter distribution 单独恢复的完整路径概率。

---

# 4. 探测计数与实际 Monte Carlo 可观测量

## 4.1 理论计数模型

在 primary-driven source-response 框架下，第 \(k\) 个通道的主要探测贡献写为

\[
N_k^{\mathrm{prim}}
=
\sum_j
q_j
\left[
K_k^{(1)}(j)
+
K_k^{(m)}(j)
\right].
\]

考虑当前实现中保留的少量 secondary gamma、Rayleigh 相关事件及其他未独立分离的小贡献，可将实际探测计数概念性写为

\[
N_k
=
N_k^{\mathrm{prim}}
+
\varepsilon_k,
\]

其中 \(\varepsilon_k\) 表示当前论文不单独建模的附加探测贡献。

该项用于保持理论与当前实现之间的边界：

- 理论中的 \(q_j\) 仍描述由 primary gamma 驱动的首次散射源；
- secondary gamma 不额外建立独立源项理论；
- Rayleigh 与 secondary gamma 在当前统计中保留，但不改变本文的主要 source-response 分解。

## 4.2 当前事件级统计对象

当前执行层以 **detected gamma track / detected gamma hit** 为计数对象。

对每条最终满足探测条件的 gamma track：

- 每条 track 只记录第一次有效探测面穿越；
- primary 与 secondary gamma 均可形成 detected hit；
- 每条 gamma track 独立维护自身的散射历史；
- secondary gamma 的散射次数从其产生时重新计数，不继承 parent track；
- 散射阶次定义为

\[
n_s
=
n_{\mathrm{Compton}}
+
n_{\mathrm{Rayleigh}}.
\]

因此：

\[
k1:\ n_s=1,
\]

\[
ms:\ n_s\ge2,
\]

\[
total:\ n_s\ge1.
\]

`first_scatter` 与 `last_scatter` 均表示**当前 detected gamma track 自身**首次和末次 Compton 或 Rayleigh 相互作用位置。

当前实现中的散射历史记录不限于 PMMA–空气模体内部，因此执行层的 first/last scatter histogram 应按当前记录口径解释，不应重新表述为“仅模体内 primary-Compton 历史”。

## 4.3 Detected source-response profile

对最终被探测事件按首次散射位置统计得到的分布，本质上是经探测系统响应加权后的贡献，而不是裸源项 \(q_j\)。

在忽略小附加项的理论表达下，可写为

\[
R_k^{(1)}(j)
=
q_jK_k^{(1)}(j),
\]

\[
R_k^{(m)}(j)
=
q_jK_k^{(m)}(j).
\]

实际 Monte Carlo histogram 更准确地理解为以上 primary-driven contribution 与少量附加事件共同构成的 **detected first-scatter source-response profile**。

因此可以直接讨论：

- 某一 first-scatter source region 对最终探测计数的贡献；
- 不同模体间该贡献的变化；
- k1 与 ms 在 first-scatter coordinate 上的分布差异。

不能仅凭该分布直接定量分离 \(q_j\) 与 \(K_k(j)\) 的变化。

---

# 5. First scatter 与 post-first-scatter 非局域输运

首次散射位置与后续散射位置在本框架中承担不同作用。

## 5.1 First scatter

\[
\mathbf r_{\mathrm{first}}
=
(x_{\mathrm{first}},
y_{\mathrm{first}},
z_{\mathrm{first}})
\]

用于定义 detected event 的 source coordinate。

对于 primary-driven 事件，首次散射源形成受初级束照射区域限制，因此其空间分布应主要集中在束流经过的区域附近。

## 5.2 Last scatter

\[
\mathbf r_{\mathrm{last}}
=
(x_{\mathrm{last}},
y_{\mathrm{last}},
z_{\mathrm{last}})
\]

表示当前 detected gamma track 在进入探测器之前记录到的末次散射位置。

对 ms 事件，\(\mathbf r_{\mathrm{last}}\) 可以扩展到比 \(\mathbf r_{\mathrm{first}}\) 更大的空间范围，因此 first/last scatter 的空间对比可用于说明：

> 给定局部 first-scatter source 后，后续多重散射输运具有明显的空间非局域特征。

但当前数据没有保存全部中间散射点，因此 last-scatter distribution 只能描述**后续输运空间扩展的末端统计特征**，不能等同于完整 path density。

---

# 6. 局部结构扰动的严格表达

设均匀模体状态为 \(M_0\)，含缺陷模体状态为 \(M_D\)。对象结构变化既可能改变首次散射源项，也可能改变后续路径集合与路径权重：

\[
q_j^0
\rightarrow
q_j^D
=
q_j^0+\Delta q_j,
\]

\[
K_k^0(j)
\rightarrow
K_k^D(j)
=
K_k^0(j)+\Delta K_k(j).
\]

令

\[
K_k(j)
=
K_k^{(1)}(j)+K_k^{(m)}(j),
\]

则 primary-driven 探测计数变化为

\[
\Delta N_k
=
\sum_j
\left[
q_j^DK_k^D(j)
-
q_j^0K_k^0(j)
\right].
\]

展开得到

\[
\Delta N_k
=
\sum_j\Delta q_jK_k^0(j)
+
\sum_jq_j^0\Delta K_k(j)
+
\sum_j\Delta q_j\Delta K_k(j).
\]

三项分别对应：

1. source-term perturbation；
2. transport-response perturbation；
3. source–transport coupling。

当前数据不能严格将三项独立分离，因此 E2 中观察到的 target-source response 变化可以支持“局部结构改变了该源区的 detected contribution”，但不能独立证明变化完全由 \(\Delta q\) 导致。

---

# 7. Source-region 定义

## 7.1 Center pose：front / target / behind

对于 center pose 下的代表缺陷 \(P_n\)，其缺陷中心深度为 \(z_c\)，轴向厚度为 \(10\ \mathrm{mm}\)。

定义

\[
\Omega_T
=
[z_c-5\ \mathrm{mm},\,
z_c+5\ \mathrm{mm}),
\]

\[
\Omega_F
=
\{
z_{\mathrm{first}}
<
z_c-5\ \mathrm{mm}
\},
\]

\[
\Omega_B
=
\{
z_{\mathrm{first}}
\ge
z_c+5\ \mathrm{mm}
\}.
\]

center pose 中，front / target / behind 始终按照 first-scatter depth 定义，与 last scatter 无关。

对于 P4：

\[
\Omega_T
=
[55,65)\ \mathrm{mm}.
\]

这一分区服务于 E2 的机制分析，用于比较缺陷前方、缺陷区域和缺陷后方 detected source-response 的变化。

## 7.2 Grid：target 定义为缺陷三维体积

grid 扫描时，射束横向位置随 pose 改变，因此“目标深度层”与“真实缺陷区域”不再等价。

对中心位置为 \((x_c,y_c,z_c)\)、尺寸为 \(10\times10\times10\ \mathrm{mm^3}\) 的标准缺陷，定义三维缺陷体积

\[
V_D
=
[x_c-5,x_c+5)
\times
[y_c-5,y_c+5)
\times
[z_c-5,z_c+5).
\]

grid 条件下若需要使用 source truth，则定义

\[
\text{target-source event}
\iff
\mathbf r_{\mathrm{first}}\in V_D.
\]

因此：

- center 的 \(\Omega_T\) 是一维 depth-source region；
- grid 的 \(V_D\) 是三维 defect-volume source region。

两者在中心照射时可近似对应，但在横向扫描 pose 下不应混用。

---

# 8. 三实验框架

## E1：均匀模体系统响应基线与散射空间特征

E1 使用 P0 作为统一 baseline，从探测端出发建立系统响应的基本物理图景。

逻辑顺序为：

\[
\text{detector-plane observable separation}
\rightarrow
\text{first-scatter depth selectivity}
\rightarrow
\text{first/last scatter spatial characteristics}.
\]

E1 主要回答：

1. 多狭缝系统在探测端是否形成可区分的接受区域；
2. 不同狭缝所接收事件是否具有不同的 detected first-scatter depth distribution；
3. first-scatter source 的空间约束与 ms 后续输运的空间扩展是否同时存在。

E1 不涉及缺陷响应，不承担局部结构机制证明。

---

## E2：局部缺陷的可观测响应与 source-region mechanism

E2 是本文主要的结构响应与机制解释实验。

其证据链为：

\[
\text{grid total-count image}
\rightarrow
\text{center total/k1/ms count change}
\rightarrow
\text{representative depth-source redistribution}
\rightarrow
\text{front/target/behind decomposition}.
\]

### 第一层：缺陷可观测性

对 P1–P6 与对应 S1–S6 进行匹配 grid 扫描，首先仅使用 total detected count 构建探测响应图。

这一层回答：

> 局部低密度结构能否直接在探测端 total-count image 中形成可观测响应。

### 第二层：散射阶次计数分解

对 center pose，比较 P0–Sn 与 Pn–Sn 下的

\[
N^{total},
\qquad
N^{k1},
\qquad
N^{ms}.
\]

这一层回答：

> total count 的结构响应由哪些散射阶次共同构成，以及 k1 与 ms 是否均发生变化。

### 第三层：代表性 depth-source response

选择代表性组合 P4–S4，并与 P0–S4 比较 detected first-scatter depth histogram。

主图保留原始计数，不用归一化图替代实际计数响应。

对

\[
s\in\{total,k1,ms\}
\]

分别分析

\[
H_0^{(s)}(z)
\quad\text{与}\quad
H_D^{(s)}(z).
\]

图像用于直接展示不同深度位置的计数差异；分布形态变化由后续指标计算完成。

### 第四层：front / target / behind 分解

对 P0–S4 与 P4–S4，按照 \(\Omega_F/\Omega_T/\Omega_B\) 对 first-scatter source region 进行积分分解。

比较

\[
N_F^{(s)},
\quad
N_T^{(s)},
\quad
N_B^{(s)},
\qquad
s\in\{total,k1,ms\}.
\]

该层用于回答：

- 缺陷对应 target region 的 detected source-response 是否发生明显变化；
- front、target、behind 的整体计数变化是否具有不同幅度或方向；
- 去除区域整体计数差异后，各区域内部的 depth-source shape 是否发生明显变化；
- k1 与 ms 是否表现出相似或不同的 source redistribution。

E2 可直接支持“target-source ms 对局部结构变化产生可测响应”，但不能独立证明 \(\Delta q\) 在定量上主导 \(\Delta K\)。

---

## E3：基于 source truth 的成像作用与理想基准

E3 用于评价 source-region information 的成像价值，而不是再次证明 source-response framework 本身。

其总体问题为：

> 当不同 source-region 的 detected contributions 能够通过 Monte Carlo truth 被理想识别时，保留或去除不同类别的 ms 对最终二维图像有何影响。

grid 条件下，target source 应按照缺陷三维体积 \(V_D\) 定义。

E3 仍属于 ideal / oracle level analysis，不等同于已经提出实际可部署的输运校正算法。其具体执行方案与图表设计在后续实验阶段另行补充。

---

# 9. E2 中的定量分析指标

E2 的定量分析只保留与当前科学问题直接对应的指标，并按照分析层级使用。核心上区分两类变化：

\[
\text{count-amplitude change}
\]

与

\[
\text{within-region shape change}.
\]

前者描述某一统计范围内的 detected contribution 整体增加或减少多少；后者描述去除整体幅值差异后，各 depth bins 之间的相对关系是否发生改变。

## 9.1 E2-B：整体计数相对变化

对 center pose 下的匹配组合，定义

\[
C^{(s)}
=
\frac{
N_D^{(s)}-N_0^{(s)}
}{
N_0^{(s)}
},
\qquad
s\in\{total,k1,ms\}.
\]

该指标用于 E2-B，表征整个匹配狭缝内对应散射类别的整体计数响应。进入 front / target / behind 分解后，不再用该全局指标替代区域级比较。

## 9.2 E2-D：Source-region count response

对

\[
r\in\{F,T,B\}
\]

定义

\[
C_r^{(s)}
=
\frac{
N_{r,D}^{(s)}-N_{r,0}^{(s)}
}{
N_{r,0}^{(s)}
}.
\]

该指标表征不同 first-scatter source regions 的整体 detected contribution 对缺陷的相对响应，用于回答各区域主要发生了多大的计数幅值变化。

## 9.3 E2-D：Within-region total variation distance

为区分区域整体幅值变化与区域内部形态变化，对 baseline 与 defect histogram 在每个 source region 内分别归一化。

对于 \(z_i\in r\)，定义

\[
p_{0,r}^{(s)}(z_i)
=
\frac{
H_0^{(s)}(z_i)
}{
\sum_{j\in r}H_0^{(s)}(z_j)
},
\]

\[
p_{D,r}^{(s)}(z_i)
=
\frac{
H_D^{(s)}(z_i)
}{
\sum_{j\in r}H_D^{(s)}(z_j)
}.
\]

进一步定义区域内 total variation distance

\[
D_{\mathrm{TV},r}^{(s)}
=
\frac{1}{2}
\sum_{i\in r}
\left|
p_{D,r}^{(s)}(z_i)
-
p_{0,r}^{(s)}(z_i)
\right|.
\]

其范围为

\[
0\le D_{\mathrm{TV},r}^{(s)}\le1.
\]

如果某一区域的 defect histogram 主要是 baseline histogram 的整体幅值缩放，即

\[
H_D^{(s)}(z_i)
\approx
\alpha_r^{(s)}H_0^{(s)}(z_i),
\qquad z_i\in r,
\]

则区域内归一化后两者形态接近，\(D_{\mathrm{TV},r}^{(s)}\) 接近 0。随着区域内部 bin-to-bin 相对关系发生更明显变化，\(D_{\mathrm{TV},r}^{(s)}\) 增大。

因此，\(D_{\mathrm{TV},r}^{(s)}\) 只用于描述**区域内部形态差异**，不替代原始计数或 \(C_r^{(s)}\) 所描述的幅值变化。

## 9.4 Optional source-region fraction

当需要讨论 front / target / behind 在全部 detected contribution 中的组成变化时，可定义

\[
f_r^{(s)}
=
\frac{
N_r^{(s)}
}{
N^{(s)}
}.
\]

比较 P0 与缺陷模体的 \(f_F,f_T,f_B\)，可描述 source-region composition 的相对重分布。该指标属于可选补充量，不作为 E2-D 的常规核心指标。

## 9.5 指标层级与统计边界

E2 的核心指标按层级统一为：

- E2-B：\(C^{(s)}\)，描述整个匹配狭缝的整体计数响应；
- E2-D：\(C_r^{(s)}\)，描述 front / target / behind 的区域计数响应；
- E2-D：\(D_{\mathrm{TV},r}^{(s)}\)，描述去除区域幅值差异后的内部形态响应；
- 可选：\(f_r^{(s)}\)，仅在需要讨论 source-region composition 时使用。

深度质心 \(\Delta\mu_z^{(s)}\) 不再作为常规指标。它只对整体深度平移敏感，而 E2 当前关注的是区域内是否保持近似比例缩放或出现更一般的 bin-to-bin 形态改变。

\(D_{\mathrm{TV},r}^{(s)}\) 不设置统一经验阈值。有限 Monte Carlo histories 会产生非零的样本形态差异，因此较小的 \(D_{\mathrm{TV},r}^{(s)}\) 应结合对应区域的计数统计与 Monte Carlo 涨落水平解释；必要时可通过独立重复运行或计数重采样估计其波动范围。

---

# 10. 当前数据能够支持的结论层级

## 10.1 E1 可支持

- 不同狭缝在探测端形成可区分的接受区域；
- 不同狭缝的 detected first-scatter depth profiles 具有不同主要响应深度；
- ms 事件的 first-scatter locations 受束流范围约束，而 last-scatter locations 表现出更大的空间扩展。

## 10.2 E2 可支持

- 匹配狭缝的 total-count grid image 能对局部缺陷形成可观测响应；
- center pose 下 total、k1 与 ms 均可定量比较其结构响应；
- representative depth-source profile 的变化可在 first-scatter coordinate 上与缺陷深度联系；
- target-source ms contribution 对局部结构变化具有可测响应；
- front / target / behind 的 detected source-response 可分别表现区域计数幅值变化和区域内部形态变化；其中后者需在区域内归一化后评价。

## 10.3 当前仍不能严格声称

- detected first-scatter histogram 等价于裸 \(q_j\)；
- 结构响应完全由 \(\Delta q\) 导致；
- \(K_k^{(m)}(j)\) 在缺陷前后保持不变；
- last-scatter distribution 等价于完整多重散射 path density；
- 所有 non-target ms 都是噪声；
- target-source ms 在实际成像中一定提供正净收益。

最后一项由 E3 的应用级 ideal benchmark 进一步评价。

---

# 11. 三实验总体证据链

\[
\boxed{
E1:\ \text{system baseline and transport characteristics}
}
\]

\[
\downarrow
\]

\[
\boxed{
E2:\ \text{defect observability and source-region mechanism}
}
\]

\[
\downarrow
\]

\[
\boxed{
E3:\ \text{source-conditioned imaging utility benchmark}
}
\]

其中：

- E1 建立系统和事件空间基础；
- E2 完成本文主要缺陷响应与机制证据；
- E3 评价 source-region information 的潜在成像价值。

论文最稳健的核心物理主张仍为：

> X 射线背散射中的多重散射具有非局域后续输运特征，但其 detected contribution 仍可按照首次散射源区进行分析；首次散射来源位于目标区域的多重散射分量能够对局部结构变化产生可测响应。

---

# 12. 理论与执行层的职责边界

本文档只规定：

- 理论变量；
- 可观测量的物理含义；
- source-region 定义；
- 三实验的证据层级；
- 指标的物理用途；
- 结论强度边界。

具体内容如：

- 需要读取哪些数据文件；
- histogram bin；
- 图的 panel 数量；
- 坐标范围；
- 表格列；
- 文件命名；
- 数据质量检查；

统一放入实验执行指导文档，不在 framework 中重复展开。
