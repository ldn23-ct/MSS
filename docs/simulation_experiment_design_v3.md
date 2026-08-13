# 源项响应框架下的 X 射线背散射仿真实验设计（V3）

## 0. 修订依据与总体定位

本文档在 `simulation_experiment_design_v2.md` 基础上，根据新版 source-response framework 与当前数据落地需求重新整理。

V3 不再维持原 E1–E6 的独立编号，而将实验合并为三个层级：

1. **E1：均匀 PMMA 下的系统响应基线与散射空间特征；**
2. **E2：缺陷可观测响应与 first-scatter source-region mechanism；**
3. **E3：基于 source truth 的成像作用/理想基准。**

新的组织原则为：

\[
\text{baseline}
\rightarrow
\text{observable defect response}
\rightarrow
\text{event/source decomposition}
\rightarrow
\text{imaging utility}.
\]

其中 E1 和 E2 是当前优先完成的数据分析任务；E3 保留为后续应用验证。

本文档规定实验的科学问题、比较关系和主要统计对象，不承担具体出图脚本和文件操作说明。执行细节由独立的实验指导文档规定。

---

# 1. 理论框架与可观测量

采用

\[
\text{primary pencil beam}
\rightarrow
q_j
\rightarrow
\gamma
\rightarrow
D_k
\]

的 source-response framework。

\(q_j\) 表示 primary-driven first-scatter source，\(\gamma\) 表示首次散射后的传播与再次相互作用历史，\(D_k\) 表示第 \(k\) 个探测狭缝。

理论上的主要探测计数为

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

当前 Monte Carlo 实现中，detected gamma track 是实际计数对象。Rayleigh 以及少量 secondary gamma contribution 保留在最终统计中，不单独建立新的理论源项。

因此，本文的 detected first-scatter histogram 统一解释为：

> 以最终被探测 gamma track 为条件的 first-scatter source-response distribution。

它不是裸 \(q_j\)，也不是独立的 \(K_k(j)\)。

---

# 2. 模体与狭缝对应关系

标准模体和匹配狭缝保持如下关系。

| 模体 | 缺陷中心深度 | 匹配狭缝 |
|---|---:|---|
| P0 | 无缺陷 | S1–S6 baseline |
| P1 | 15 mm | S1 |
| P2 | 30 mm | S2 |
| P3 | 45 mm | S3 |
| P4 | 60 mm | S4 |
| P5 | 75 mm | S5 |
| P6 | 90 mm | S6 |

标准空气缺陷尺寸为

\[
10\times10\times10\ \mathrm{mm^3}.
\]

P1–P6 中缺陷均位于中心照射时的初级束主路径上。

---

# 3. 当前事件分类

对每条 detected gamma track，定义

\[
n_s
=
n_{\mathrm{Compton}}
+
n_{\mathrm{Rayleigh}}.
\]

统计类别为：

\[
total:\ n_s\ge1,
\]

\[
k1:\ n_s=1,
\]

\[
ms:\ n_s\ge2.
\]

每条 gamma track 独立维护自身散射历史；secondary gamma 的散射次数不继承 parent track。

`first_scatter` 和 `last_scatter` 均指当前 gamma track 自身首次和末次 Compton 或 Rayleigh 相互作用。

因此，后续所有 total/k1/ms 和 first/last-scatter 统计均采用当前实现口径，不再使用旧的 primary-only / phantom-Compton-only 定义。

---

# 4. Source-region 统一定义

## 4.1 Center pose

对于缺陷中心深度 \(z_c\)，定义

\[
\Omega_F
=
\{
z_{\mathrm{first}}<z_c-5\ \mathrm{mm}
\},
\]

\[
\Omega_T
=
[
z_c-5\ \mathrm{mm},
z_c+5\ \mathrm{mm}
),
\]

\[
\Omega_B
=
\{
z_{\mathrm{first}}\ge z_c+5\ \mathrm{mm}
\}.
\]

P4 条件下：

\[
\Omega_T=[55,65)\ \mathrm{mm}.
\]

front / target / behind 只根据 first-scatter depth 定义。

## 4.2 Grid pose

grid 条件下，target 不再仅按深度层定义，而采用缺陷三维体积：

\[
V_D
=
[x_c-5,x_c+5)
\times
[y_c-5,y_c+5)
\times
[z_c-5,z_c+5).
\]

若 E3 或后续 grid truth analysis 使用 target-source classification，则

\[
\mathbf r_{\mathrm{first}}\in V_D
\]

才定义为 target-source event。

E2 的首层 grid 图只使用 total count，不需要在图像构建阶段依赖 source truth。

---

# 5. 三项实验总表

| 编号 | 实验名称 | 核心问题 | 主要条件 | 主要分析层级 |
|---|---|---|---|---|
| E1 | 均匀模体系统响应基线与散射空间特征 | 系统在探测端是否具有可区分狭缝接受区域；不同狭缝是否具有 detected first-scatter depth selectivity；first 与 last scatter 的空间特征如何 | P0；center；S1–S6；代表性 S4 | detector-plane → depth source → first/last spatial comparison |
| E2 | 缺陷可观测响应与 source-region mechanism | 匹配狭缝能否观测不同深度缺陷；total 响应由哪些散射阶次构成；代表性缺陷如何改变 first-scatter depth contribution；front/target/behind 如何重分布 | P1–P6 × matched S1–S6；P0 baseline；grid + center；代表 P4–S4 | grid image → center counts → depth-source profile → F/T/B decomposition |
| E3 | 基于 source truth 的成像作用/理想基准 | 理想识别不同 source-region contribution 时，保留或去除不同 ms 对二维成像的作用如何 | grid；source truth；target=\(V_D\) | 后续补充 |

---

# 6. E1：均匀模体系统响应基线与散射空间特征

## 6.1 实验定位

E1 使用 P0 作为无缺陷 baseline，从探测端可观测量出发，再进入事件空间分析。

整体证据链为

\[
\text{detector-plane slit separation}
\rightarrow
\text{detected first-scatter depth selectivity}
\rightarrow
\text{post-first-scatter spatial spread}.
\]

E1 只建立系统与事件输运的基线，不讨论缺陷响应。

---

## 6.2 E1-A：探测端空间选择

### 条件

- P0；
- center pose；
- 两组狭缝运行覆盖 S1–S6；
- 使用 detected gamma hit 的探测面位置和实际记录 slit label。

### 分析

比较不同 slit label 对应的探测面 hit positions。

该层用于确认：

> 不同狭缝在 detector plane 上对应可区分的空间接受区域。

几何 ROI 可用于辅助可视化和数据质量检查，但 slit identity 以实际记录 label 为准，不由二维位置重新推断。

---

## 6.3 E1-B：Detected first-scatter depth selectivity

### 条件

- P0；
- center；
- S1–S6。

### 统计

对

\[
s\in\{total,k1,ms\}
\]

统计各狭缝的

\[
H_k^{(s)}(z).
\]

为比较不同狭缝的深度响应形态，可在 E1 中对每条 slit profile 独立积分归一化：

\[
p_k^{(s)}(z)
=
\frac{
H_k^{(s)}(z)
}{
\sum_z H_k^{(s)}(z)
}.
\]

### 分析内容

主要考察：

- S1–S6 主要响应深度是否依次变化；
- 主要响应深度与设计深度的对应关系；
- total、k1、ms 的 depth selectivity 是否存在差异。

E1-B 的 profile 统一称为：

- detected first-scatter depth response；
- effective depth-response profile；
- detected source-response profile。

不称为独立的纯 \(K_k(z)\) kernel。

---

## 6.4 E1-C：First/last scatter 空间特征

### 条件

- P0；
- center；
- 选择代表性中间深度狭缝 S4；
- 重点分析 ms。

### 统计

比较

\[
\mathbf r_{\mathrm{first}}
\]

与

\[
\mathbf r_{\mathrm{last}}
\]

的空间分布。

优先采用 \(x-z\) 和 \(y-z\) 投影。

### 作用

E1-C 用于说明：

1. first-scatter locations 主要受初级束照射范围约束；
2. ms last-scatter locations 分布在更大的空间范围内；
3. first-scatter source coordinate 与后续非局域输运需要在理论上区分。

该实验不把 last-scatter distribution 解释为完整多重散射 path density。

---

## 6.5 E1 的输出层级

E1 的结果应能够形成以下逻辑：

\[
\boxed{
\text{detector plane 上狭缝可分}
}
\]

\[
\downarrow
\]

\[
\boxed{
\text{狭缝对应不同 first-scatter depth profiles}
}
\]

\[
\downarrow
\]

\[
\boxed{
\text{first scatter 局域，ms 后续输运呈空间扩展}
}
\]

E1 完成后，后续 E2 可直接使用 slit identity、first-scatter source 和 ms 非局域输运的既定物理含义。

---

# 7. E2：缺陷可观测响应与 source-region mechanism

## 7.1 实验定位

E2 是全文主要的结构响应与机制分析实验。

其组织顺序固定为：

\[
\text{grid total images}
\rightarrow
\text{center total/k1/ms counts}
\rightarrow
\text{representative raw depth-source profiles}
\rightarrow
\text{front/target/behind decomposition}.
\]

这一顺序坚持从探测端可观测现象逐步进入 Monte Carlo truth。

---

## 7.2 E2-A：S1–S6 匹配 grid 缺陷图像

### 条件

对匹配组合

\[
P1-S1,\,
P2-S2,\,
P3-S3,\,
P4-S4,\,
P5-S5,\,
P6-S6
\]

进行 grid 扫描。

P0–S1 至 P0–S6 保留为对应 baseline 数据。

### 主要统计量

每个 pose 的

\[
N^{total}(x,y).
\]

首层结果只使用 total detected count，不拆分 k1/ms。

### 科学问题

该层回答：

> 不同目标深度的局部空气缺陷是否能够通过与其匹配的狭缝，在 detector-side total-count grid image 中形成可观测响应。

E2-A 主要展示“现象”，不在该层进行 source-region 机制解释。

---

## 7.3 E2-B：Center pose 的 total/k1/ms 计数分解

### 条件

对每个匹配组合比较：

\[
P0-S_n
\quad\text{vs}\quad
P_n-S_n,
\qquad n=1,\ldots,6.
\]

统一使用 center pose。

### 统计

对

\[
s\in\{total,k1,ms\}
\]

统计 baseline 与缺陷模体的 raw count：

\[
N_{0,n}^{(s)},
\qquad
N_{D,n}^{(s)}.
\]

并计算

\[
\Delta N_n^{(s)}
=
N_{D,n}^{(s)}
-
N_{0,n}^{(s)},
\]

\[
C_n^{(s)}
=
\frac{
N_{D,n}^{(s)}-N_{0,n}^{(s)}
}{
N_{0,n}^{(s)}
}.
\]

### 科学问题

该层回答：

- grid 图中可观测的 total response 在 center representative condition 下具有多大计数变化；
- k1 与 ms 分量是否均参与结构响应；
- 不同深度匹配组合的 total/k1/ms 响应量级如何。

grid 图和 center table 的职责应在正文中明确区分：

- grid：展示空间成像现象；
- center：进行具有代表性的事件计数分解。

---

## 7.4 E2-C：P4–S4 representative depth-source comparison

### 选择理由

P4–S4 位于当前 15–90 mm 深度序列的中间区域，适合作为 representative condition 进行机制分析。

比较：

\[
P0-S4
\quad\text{vs}\quad
P4-S4.
\]

均使用 center pose。

### 统计

分别统计

\[
H_0^{total}(z),
\quad
H_D^{total}(z),
\]

\[
H_0^{k1}(z),
\quad
H_D^{k1}(z),
\]

\[
H_0^{ms}(z),
\quad
H_D^{ms}(z).
\]

### 图像原则

主图统一使用**原始计数**。

不通过归一化图直接展示形态变化。

baseline 与 defect profile 使用：

- 相同 depth bin；
- 相同 depth range；
- 对应 panel 相同纵轴尺度。

这样原始计数差异与局部 profile 变化可以直接比较。

### 科学问题

该层回答：

- total/k1/ms 的 detected first-scatter contribution 在哪些深度发生变化；
- target depth 附近是否存在明显的局部计数改变；
- 缺陷前后是否伴随更广泛的 source-response redistribution。

---

# 8. E2-D：Front / target / behind source-region decomposition

对 P0–S4 与 P4–S4，按照

\[
\Omega_F,\quad
\Omega_T,\quad
\Omega_B
\]

对 E2-C 的 depth-source histogram 进一步积分。

对每个

\[
s\in\{total,k1,ms\}
\]

得到

\[
N_F^{(s)},
\quad
N_T^{(s)},
\quad
N_B^{(s)}.
\]

计算：

\[
C_r^{(s)}
=
\frac{
N_{r,D}^{(s)}
-
N_{r,0}^{(s)}
}{
N_{r,0}^{(s)}
},
\qquad
r\in\{F,T,B\},
\]

以及

\[
f_r^{(s)}
=
\frac{
N_r^{(s)}
}{
N^{(s)}
}.
\]

该层用于比较：

1. target region 的 total/k1/ms 变化；
2. front 与 behind region 是否出现不同方向或不同幅度的变化；
3. 各 source regions 在总 detected contribution 中的占比是否发生重分布。

---

# 9. E2 分布形态指标

E2-C 的主图使用 raw counts。分布形态由指标计算，不要求另画归一化 profile。

## 9.1 深度质心

由 raw histogram 得到归一化分布

\[
p^{(s)}(z_i)
=
\frac{H^{(s)}(z_i)}
{\sum_i H^{(s)}(z_i)}.
\]

定义

\[
\mu_z^{(s)}
=
\sum_i z_i p^{(s)}(z_i),
\]

并比较

\[
\Delta\mu_z^{(s)}
=
\mu_{z,D}^{(s)}
-
\mu_{z,0}^{(s)}.
\]

该指标描述 detected first-scatter distribution 的整体深度偏移。

## 9.2 Total variation distance

定义

\[
D_{\mathrm{TV}}^{(s)}
=
\frac12
\sum_i
\left|
p_D^{(s)}(z_i)
-
p_0^{(s)}(z_i)
\right|.
\]

用于量化 baseline 与 defect depth-source distribution 的整体形态差异。

## 9.3 Source-region fraction

\[
f_F^{(s)},\quad
f_T^{(s)},\quad
f_B^{(s)}
\]

本身也是一种具有直接物理意义的分布形态描述，用于表征 front-target-behind source composition 的变化。

因此，E2 不需要额外引入复杂的 histogram overlap coefficient 或大量相似形态指标。

---

# 10. E2 的证据边界

E2 若观察到

\[
N_{T,D}^{(ms)}
\ne
N_{T,0}^{(ms)},
\]

且该变化与 P4 的目标深度对应，可直接支持：

> 以目标区域为 first-scatter source 的 ms detected contribution 对局部材料结构变化产生响应。

如果同时观察到：

- target k1 与 target ms 同方向变化；
- front 变化较弱；
- target 明显下降；
- behind 出现相对重分布；

则这些现象与 first-scatter source redistribution 的机制图景一致。

但 E2 仍不用于严格证明：

\[
|\Delta q|\gg|\Delta K|.
\]

---

# 11. E3：基于 source truth 的成像作用/理想基准

## 11.1 当前定位

E3 用于回答：

> source-region information 在二维成像中是否具有实际价值。

其分析将基于 grid 条件下的 Monte Carlo truth，并使用三维缺陷区域

\[
V_D
\]

定义 target source。

E3 不重复 E2 的机制证明，而是在 E2 基础上比较不同 source-conditioned event contributions 对图像质量的作用。

## 11.2 当前保留边界

E3 的具体内容包括：

- 具体图像组合；
- 事件选择策略；
- oracle / ideal correction 定义；
- Contrast、CNR 或其他图像质量指标；
- 与未来输运校正算法的对应关系；

暂不在 V3 执行层展开，待 E1、E2 数据处理完成后根据实际结果进一步确定。

---

# 12. 三项实验的证据链

\[
\boxed{
E1:\ \text{system baseline + first/last scatter physics}
}
\]

\[
\downarrow
\]

\[
\boxed{
E2:\ \text{defect visibility + source-region mechanism}
}
\]

\[
\downarrow
\]

\[
\boxed{
E3:\ \text{source-conditioned imaging utility}
}
\]

其中：

- E1 说明系统“能选择什么”以及 ms 后续输运为什么不能简单理解为局域响应；
- E2 说明局部结构“如何在探测端被看见”以及该变化如何映射到 first-scatter source region；
- E3 进一步判断这些 source-region-dependent contributions 是否应在成像中保留、抑制或校正。

---

# 13. 当前优先执行顺序

当前只优先完成 E1 和 E2。

建议顺序为：

1. 整理 P0 center 两组狭缝数据；
2. 完成 E1 detector-plane separation；
3. 完成 E1 S1–S6 depth-response；
4. 完成 E1 representative first/last spatial comparison；
5. 整理 P1–P6 matched grid total images；
6. 整理 P0–Sn 与 Pn–Sn center count table；
7. 完成 P0–S4 / P4–S4 raw depth-source comparison；
8. 完成 front/target/behind decomposition 与形态指标；
9. 根据 E1、E2 实际结果再冻结 E3 的应用级设计。

具体文件、图表和数据质量检查见独立实验指导文档。
