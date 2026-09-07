# Multiagent Work

一个面向科研与工程任务的 Codex 中台 skill。用户只需描述目标；主会话会判断直接执行还是分发子代理，并负责检查证据、整合结果与停止工作。

它特别适合：

- AI、具身智能、世界模型和强化学习研究；
- 论文与实验协议审查；
- 科研代码诊断、实现和验证；
- 客户项目与生产变更的安全门禁；
- 明确授权后的跨会话、长期或无人值守工作。

## 核心行为

- 默认直接执行，不为简单任务制造多智能体开销。
- 只在工作包相互独立、可单独验收且并行收益明确时分发子代理。
- 主会话检查关键证据，不把子代理自报完成或 PASS 当作最终验收。
- 研究任务按需加载证据与具身智能规则。
- 客户、敏感数据和 production 任务按需加载工业交付规则。
- 长期工作只有在用户明确要求时才创建独立任务或心跳。

## 安装

在 Codex 中直接要求安装：

```text
请从 https://github.com/N0TPO3T/multiagent-work 安装这个 skill。
```

也可以手动安装：

```bash
git clone https://github.com/N0TPO3T/multiagent-work.git \
  ~/.codex/skills/multiagent-work
```

安装后新建一个 Codex 任务；如果 skill 列表没有刷新，重启 Codex。

## 使用

最可靠的首次调用方式：

```text
$multiagent-work 中台执行：审计当前项目，判断训练失败的根因；可以自动分发子代理，先不要修改代码。
```

常用命令：

```text
中台执行：分析并完成这个任务。
并行审查：分别从代码、数据与实验协议审查当前项目。
只分析：诊断问题，不修改、不训练。
直接执行：完成这个小修改，不使用子代理。
长期中台：拆成独立任务并持续执行到指定时间。
中台状态
中台继续
中台暂停
中台验收
```

`中台执行` 不自动授权发布、推送、付费资源、生产写入、共享服务器高成本作业、独立应用任务或定时心跳。请在目标中明确授权相应动作。

## 结构

```text
multiagent-work/
├── SKILL.md
├── agents/
│   └── openai.yaml
└── references/
    ├── industrial-delivery.md
    ├── long-running.md
    └── research-evidence.md
```

`SKILL.md` 是入口。三个 reference 仅在相应任务出现时加载，避免普通任务携带无关规则。

## 能力边界

skill 提供决策和编排规则，不会为宿主增加原本不存在的子代理、独立任务、调度器、服务器或外部服务权限。实际能力取决于当前 Codex 客户端和可用工具。

## English

Multiagent Work is a Codex skill for coordinating research and engineering work from one main chat. It chooses between direct execution and bounded subagent delegation, verifies critical evidence, and loads additional rules only for research, production, or long-running workflows.

Invoke it with:

```text
$multiagent-work Coordinate this task, delegate independent work when useful, and verify the result.
```

## License

Apache License 2.0.
