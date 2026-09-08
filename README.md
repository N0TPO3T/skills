# Skills

集中维护的 Agent Skills：日报、信息海报、协作编排与研究工作流。各组件源码和历史从原独立仓库完整迁入，后续统一在本仓库维护。

## 技能目录

| Skill | 用途 | 可安装目录 | 许可证 |
| --- | --- | --- | --- |
| [daily-work-report](daily-work-report/README.md) | 从 OMP/Codex 会话按项目生成日报，记录问题、处理及验证结果 | `daily-work-report/daily-work-report/` | MIT |
| [insight-poster](insight-poster/README.md) | 将论文、会议记录或研究总结整理为单页 HTML 海报 | `insight-poster/` | MIT |
| [multiagent-work](multiagent-work/README.md) | 基于证据的研究与工程任务协作 | `multiagent-work/` | Apache-2.0 |
| [multi-session-workflow](multi-session-workflow/README.md) | 使用真实独立任务及 heartbeat 进行持续协作 | `multi-session-workflow/` | 原仓库未声明 |
| [research-agent](research-agent/README.md) | 文献、研究缺口、实验与论文的阶段化工作流 | `research-agent/skills/research-agent/` | Apache-2.0 |

**宿主能力不随安装而获得。** OMP 和 Codex 都能发现兼容目录，但具体 Skill 仍受宿主工具能力限制。尤其 `multi-session-workflow` 依赖真实的任务/线程及定时 heartbeat，不保证所有 CLI 或 OMP 环境均可执行。`research-agent` 的便携 Skill 不依赖 Python runtime；可选运行时见下方说明。

`multiagent-work` 和 `multi-session-workflow` 保留为两个独立 Skill，没有互相替代关系；同一任务使用两者时，应共用一个明确的状态入口，不建立相互冲突的协调记录。

## 安装

推荐 Python 3.11+。从仓库根目录运行统一安装入口：

```sh
git clone https://github.com/N0TPO3T/skills.git
cd skills
python install.py daily-work-report
```

也可以一次选择多个或全部 Skill：

```sh
python install.py daily-work-report insight-poster multiagent-work multi-session-workflow research-agent
```

默认复制到 `~/.agents/skills/<skill-name>/`，可由当前 OMP/Codex 的 Agents Skill 来源发现。`~` 为用户主目录；Windows 对应 `%USERPROFILE%`。指定其他宿主或项目级目录：

```sh
python install.py research-agent --dest "/path/to/project/.agents/skills"
```

安装器会复制完整资源包及已声明的许可证，不安装宿主、模型、研究运行时或调度器，也不自动授权读取个人会话。已存在同名 Skill 时拒绝覆盖。更新时先把旧安装移出 Skill 搜索目录，再运行安装命令；不要把同名备份留在搜索目录中。

不使用安装器也可以：按上表复制对应“可安装目录”，保持 `SKILL.md`、脚本、manifest、prompts、references 等资源的相对位置，并保留组件的许可证。**不要把整个仓库直接当作一个 Skill 安装。**

安装后重启或刷新宿主：

- OMP：请求读取 `skill://daily-work-report`，或在开启 Skill 命令时输入 `/skill:daily-work-report`。
- Codex：在 `/skills` 中查找，或在聊天中使用 `$daily-work-report` 等名称。

## 使用示例

以下是发送给宿主的提示，不是终端命令：

```text
使用 daily-work-report。日报保存到我指定的目录，按我的用户时区，生成今天的日报。
使用 insight-poster，把这份会议记录整理成一页离线 HTML 海报。
使用 multiagent-work，先划分可独立执行的任务，再按证据验收。
使用 research-agent，围绕这个研究方向开展文献与缺口分析。
```

具体授权、配置、限制与操作方式以各组件 README 和 `SKILL.md` 为准。

### 日报依赖

```sh
python -m pip install tzdata
```

日报还需配置保存目录、用户 IANA 时区及授权会话来源。脚本负责采集和保存，宿主模型负责摘要；不内置调度器。详见 [日报说明](daily-work-report/README.md)。

### 可选研究运行时

仅安装 `research-agent` Skill 无需安装下述运行时。需要其确定性状态持久化、CLI 或实验执行入口时：

```sh
cd research-agent
uv sync --extra dev --frozen
uv run research-agent --help
```

需要真实模型和外部工具的执行模式仍需单独配置；不得把离线 mock 结果当成真实研究成果。详见 [研究组件说明](research-agent/README.md)。

## 仓库布局与维护

每个顶层组件保留原仓库布局，避免相对路径、wheel 资源打包及已有测试失效：

```text
skills/
├── README.md
├── catalog.json                 # 安装目录、来源提交、许可证
├── install.py                   # 统一便携 Skill 安装入口
├── daily-work-report/           # 完整日报组件，内部含可安装子目录
├── insight-poster/
├── multiagent-work/
├── multi-session-workflow/
└── research-agent/              # 完整研究组件，含可选 Python runtime
```

迁移采用未压缩的 Git 历史导入；`catalog.json` 的 `source_commit` 标记迁移基线，原提交在本仓库历史中仍可达。`source_repository` 是历史来源标识，不是后续安装入口。

研究组件原 `v0.2.0` 发布保留为 [`research-agent/v0.2.0`](https://github.com/N0TPO3T/skills/releases/tag/research-agent%2Fv0.2.0)，包括原始附件。该历史 tag 指向原研究仓库的提交，源代码归档保持当时的独立仓库布局，不是当前集中布局。

组件采用各自许可证；本仓库不以一个总许可证覆盖所有组件。`multi-session-workflow` 的来源未声明许可证，本次迁移未擅自追加授权；使用和再分发前需确认许可。不要因其他组件使用 MIT/Apache-2.0 就推断它同样授权。

## 验证

在本仓库根目录验证日报：

```sh
python -m pip install tzdata
python -B -m unittest discover -s daily-work-report/daily-work-report/tests -v
```

研究组件从它自己的目录验证与构建：

```sh
cd research-agent
uv sync --extra dev --frozen
uv run pytest
uv build
```

其他三个 Skill 主要是指令与资源，不包含通用应用测试套件。`multi-session-workflow/tests/verify_smoke.py` 需要实际宿主任务生成的产物，不能用安装成功冒充其线程/heartbeat 验收。

GitHub Actions 分别运行安装检查、日报回归和研究组件离线测试/构建。不把真实会话、私有研究数据、模型凭据或个人日报提交到本仓库。
