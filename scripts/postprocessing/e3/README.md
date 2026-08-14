# E3：基于 source truth 的成像作用与理想基准（待设计）

本目录当前没有可执行入口。E3 将在 E1/E2 结果基础上评价 source-conditioned contribution 的二维成像价值，不重复 E2 的 center front/target/behind 分解。

未来 grid target-source classification 必须使用 first-scatter position 是否落入缺陷三维体积的 truth 定义。具体图像组合、oracle 选择、Contrast/CNR 指标和验收合同尚未冻结。

不得直接启用 `_archive/` 中依赖 `events_clean/slit_id` 的历史实现。
