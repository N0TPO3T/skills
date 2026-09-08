# 研究证据规则

只在研究 Idea、论文审查、实验设计/执行、具身智能、世界模型或 RL 任务中读取本文件。

## 证据分级

明确标记事实、推断、假设、建议和未知。论文摘要、作者叙事、工具输出、可视化、单次观察和旧记忆都不能自动成为事实。涉及近期论文、代码、模型、checkpoint、benchmark、数据集或会议政策时优先核查一手来源；无法核查时说明不确定性。

实验只能支持与设计相匹配的结论。不得默认：

- correlation 等于 causation；
- offline metric 提升等于 closed-loop performance 提升；
- 单 benchmark 等于泛化；
- 单 seed 等于稳定；
- ablation 下降等于机制得到证明；
- visualization 合理等于内部表征具有该语义。

## Idea 与机制门禁

证据不足时保留 2-3 个机制上不同的竞争假设。每个候选至少给出：可证伪命题、最强简单 baseline、最小验证、主要混杂、支持/反驳/不可区分结果和 Go/Kill 条件。

提出 token、gate、memory、routing、attention、adapter、selector、predictor 或 auxiliary loss 前，先说明：

1. 真实失败发生在数据、表征、优化、决策还是评测；
2. 为什么简单方法不能解决；
3. 新机制改变哪条信息流、梯度路径或决策过程；
4. 哪个区分性实验能支持或推翻机制；
5. 哪个强简单 baseline 可能获得同样收益。

昂贵实验前优先使用 oracle、rule-based baseline、linear probe、frozen feature、shuffle/permutation control、小规模 rollout 或单任务 smoke test。先审计数据、schema、split、label 来源、时间可用性和 metric，再决定是否训练；不得伪造标签或用不合法样本补规模。

涉及人类视频、现场机器人数据、用户/客户数据或可识别信息时，还要核对数据许可、知情同意/伦理审批、PII 去标识、允许用途、保存期限和共享边界。缺少证据时保持未知，不把技术可访问性当作研究或训练授权；涉及客户或生产数据时同时加载工业交付规则。

## 具身智能与世界模型

任何序列、预测或控制方案都要明确：

- 时刻 `t` 实际可获得的 observation、state、action 和 history；
- 预测在何时生成、预测哪个时间步、被哪个动作使用；
- train 与 inference 使用真实未来还是预测未来；
- action-observation alignment、控制延迟、坐标系、单位和归一化；
- teacher forcing、exposure bias、off-policy mismatch、covariate shift 与误差累积；
- simulator、Oracle、人工轨迹、offline 指标与真实部署证据之间的边界。

Oracle 必须命名具体协议和 estimand。Oracle feasibility 不是方法有效性证据；Best-of-K/Pass@K 只表示给定候选池和协议下的 headroom，不是部署时 Top-1 成功率。

predictive-state 或模型生成的 future-shaped representation 不等于实际未来。若多个候选共享同一 future，不能自动构成 candidate-specific consequence evidence。需要确认候选特异的 action-future binding，并确保推理输入在部署时可获得。

评估 selector 前确认候选池有足够 mixed outcomes 和 Oracle-minus-Random headroom。低 headroom 时结论是当前协议下 selector efficacy 不可评估；先诊断 proposal coverage、候选多样性或 intervention timing，不用扩大 selector 掩盖问题。

数据按环境、场景或独立因果单元划分。不得把同一 parent 的派生轨迹跨 train/test，也不得把实际未来、后验 outcome、Oracle 轨迹或其他部署时不可用信息泄漏给 selector。

## 实验决策

- Diagnostic/smoke：回答一个局部问题，明确 question、minimal intervention、observable outcome 和 decision rule。
- Feasibility：至少明确 hypothesis、matched baseline/control、metric、major confounder 和 Go/Kill。
- Formal experiment：再补齐 sample unit、data split、randomness、统计要求、成本、代码/配置/数据版本和停止标准。

用于正式结论的运行至少绑定：代码 commit 或不可变 diff、dataset/protocol version、完整配置、seed、环境/硬件、checkpoint、artifact path、metric 实现与执行命令。探索性 smoke test 可以明确豁免不影响其诊断问题的字段，但不能将其提升为正式结论。

重要否定结果可以构成完成，只要它回答了预先定义的问题。结果不可识别时报告 `INCONCLUSIVE` 或对应的不可评估原因，不把实现失败误写成研究命题失败。
