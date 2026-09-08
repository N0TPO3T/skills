# Research Agent LOOP v1 — Archival Source of Truth

> ARCHIVAL SOURCE OF TRUTH.
>
> Do not load this file during normal runtime.
> Runtime behavior is provided through the decomposed skill references and
> phase-specific prompts.

The verbatim foundational specification supplied for this repository follows.
# 任务：实现 Autonomous ML Research Agent Workflow

你是一名资深 AI Agent / ML Systems / Backend Engineer。

你的任务不是讨论方案，而是**直接在当前代码仓库中设计并实现一套可运行、可扩展、可测试的 Autonomous ML Research Agent Workflow**。

该系统面向机器学习、大模型算法、LLM reasoning、RL、multimodal、agent 等科研项目，支持从模糊研究方向开始，经由：

Literature Search
→ Research Landscape
→ Gap Mining
→ Gap Synthesis
→ Human Topic Selection
→ Idea Formation
→ Adversarial Review
→ Resource-aware Experiment Design
→ Baseline Reproduction
→ Experiment Loop
→ Failure Diagnosis
→ Pivot
→ Evidence Expansion
→ Paper Package
→ Paper Draft
→ Paper Review
→ Research Report

形成完整科研闭环。

重点不是构建一个“大 Prompt”，而是实现一个：

**Skill Interface + Deterministic Workflow Engine + Typed Research State + Modular Prompts + Tool Adapters + Artifact Store + Human Checkpoints**

的研究操作系统。

---

# 一、核心工程原则

必须遵循：

## 1. Prompt role != Agent process

逻辑上可以有很多科研角色，但 runtime 第一版不要启动几十个独立 Agent。

第一版使用以下五类逻辑执行器即可：

```text
Orchestrator
ResearchAgent
ReviewerAgent
ExperimentAgent
PaperAgent
```

不同任务通过加载不同 prompt profile 完成。

例如：

```python
research_agent.run(
    prompt_profile="gap_miner",
    context=context,
)
```

而不是为每种角色创建单独服务。

---

## 2. LLM 做 scientific decision，代码做 state transition

禁止让 LLM 自由控制整个 workflow。

LLM 只能输出结构化 action。

例如：

```json
{
  "action": "EXPAND_LITERATURE",
  "target": "adaptive inference compute",
  "reason": "insufficient evidence for root-cause hypothesis",
  "priority": 0.86
}
```

Workflow Engine 必须检查：

```python
action in ALLOWED_TRANSITIONS[current_phase]
```

非法 transition 必须拒绝。

---

## 3. Persistent State 必须 typed

不要依赖 chat history 作为科研状态。

使用 Pydantic / equivalent schema 建模：

* Project
* ResourceConstraints
* PaperReference
* ResearchGap
* Hypothesis
* MethodCandidate
* Experiment
* Evidence
* Claim
* Decision
* HumanCheckpoint

所有状态必须可：

* serialize
* reload
* validate
* version

推荐 JSON 作为 runtime persistence 格式。

YAML 可以用于 config。

---

## 4. Artifact 与 State 分离

Research State 只存结构化 metadata。

大量内容保存在 Artifact Store。

例如：

```text
artifacts/
├── literature/
├── gaps/
├── ideas/
├── experiments/
│   ├── EXP-0001/
│   │   ├── config.json
│   │   ├── stdout.log
│   │   ├── stderr.log
│   │   ├── metrics.json
│   │   └── analysis.md
├── reviews/
├── reports/
└── paper/
```

State 中只保存：

```json
{
  "experiment_id": "EXP-0001",
  "result_artifact": "artifacts/experiments/EXP-0001/metrics.json"
}
```

---

# 二、建议目录结构

创建：

```text
research_agent/
│
├── README.md
├── pyproject.toml
├── .env.example
├── config/
│   ├── default.yaml
│   └── models.yaml
│
├── skills/research-agent/
│   └── SKILL.md
│
├── src/
│   └── research_agent/
│       │
│       ├── __init__.py
│       ├── cli.py
│       │
│       ├── core/
│       │   ├── orchestrator.py
│       │   ├── workflow.py
│       │   ├── transitions.py
│       │   ├── context_builder.py
│       │   └── ids.py
│       │
│       ├── schemas/
│       │   ├── project.py
│       │   ├── literature.py
│       │   ├── gap.py
│       │   ├── hypothesis.py
│       │   ├── experiment.py
│       │   ├── evidence.py
│       │   ├── claim.py
│       │   ├── decision.py
│       │   └── state.py
│       │
│       ├── agents/
│       │   ├── base.py
│       │   ├── research.py
│       │   ├── reviewer.py
│       │   ├── experiment.py
│       │   └── paper.py
│       │
│       ├── prompts/
│       │   ├── global_system.md
│       │   ├── orchestrator.md
│       │   │
│       │   ├── research/
│       │   │   ├── bootstrap.md
│       │   │   ├── horizon_scan.md
│       │   │   ├── literature_extract.md
│       │   │   ├── gap_miner.md
│       │   │   ├── gap_synthesizer.md
│       │   │   └── idea_designer.md
│       │   │
│       │   ├── review/
│       │   │   ├── idea_attack.md
│       │   │   ├── idea_defense.md
│       │   │   └── meta_review.md
│       │   │
│       │   ├── experiment/
│       │   │   ├── resource_planner.md
│       │   │   ├── baseline_reproduction.md
│       │   │   ├── experiment_designer.md
│       │   │   ├── result_analyzer.md
│       │   │   ├── failure_diagnosis.md
│       │   │   ├── pivot.md
│       │   │   └── evidence_expansion.md
│       │   │
│       │   └── paper/
│       │       ├── readiness_audit.md
│       │       ├── package_builder.md
│       │       ├── writer.md
│       │       └── reviewer.md
│       │
│       ├── policies/
│       │   ├── evidence.md
│       │   ├── citation.md
│       │   ├── experiment.md
│       │   ├── resource.md
│       │   └── stopping.md
│       │
│       ├── workflows/
│       │   ├── discovery.py
│       │   ├── idea.py
│       │   ├── experiment.py
│       │   └── paper.py
│       │
│       ├── tools/
│       │   ├── base.py
│       │   ├── search.py
│       │   ├── papers.py
│       │   ├── code_execution.py
│       │   ├── repository.py
│       │   └── registry.py
│       │
│       ├── llm/
│       │   ├── base.py
│       │   ├── client.py
│       │   ├── router.py
│       │   └── structured_output.py
│       │
│       ├── storage/
│       │   ├── state_store.py
│       │   ├── artifact_store.py
│       │   └── project_store.py
│       │
│       └── services/
│           ├── literature_service.py
│           ├── experiment_service.py
│           └── evidence_service.py
│
├── projects/
│   └── .gitkeep
│
└── tests/
    ├── test_state.py
    ├── test_transitions.py
    ├── test_orchestrator.py
    ├── test_context_builder.py
    ├── test_structured_output.py
    └── fixtures/
```

如果你认为有更合理的轻量级组织方式，可以调整，但必须保留上述职责分离。

---

# 三、Workflow State Machine

定义：

```python
class ResearchPhase(str, Enum):
    BOOTSTRAP = "bootstrap"
    HORIZON_SCAN = "horizon_scan"
    GAP_MINING = "gap_mining"
    GAP_SYNTHESIS = "gap_synthesis"
    TOPIC_SELECTION = "topic_selection"

    IDEA_FORMATION = "idea_formation"
    IDEA_REVIEW = "idea_review"

    RESOURCE_DESIGN = "resource_design"
    BASELINE_REPRODUCTION = "baseline_reproduction"

    CORE_EXPERIMENT = "core_experiment"
    DIAGNOSIS = "diagnosis"
    PIVOT = "pivot"

    EVIDENCE_EXPANSION = "evidence_expansion"

    PAPER_AUDIT = "paper_audit"
    PAPER_ASSEMBLY = "paper_assembly"
    PAPER_REVIEW = "paper_review"

    COMPLETE = "complete"
```

实现显式 transition graph。

大体允许：

```text
BOOTSTRAP
→ HORIZON_SCAN

HORIZON_SCAN
→ HORIZON_SCAN
→ GAP_MINING

GAP_MINING
→ HORIZON_SCAN
→ GAP_SYNTHESIS

GAP_SYNTHESIS
→ HORIZON_SCAN
→ TOPIC_SELECTION

TOPIC_SELECTION
→ IDEA_FORMATION

IDEA_FORMATION
→ HORIZON_SCAN
→ IDEA_REVIEW

IDEA_REVIEW
→ IDEA_FORMATION
→ RESOURCE_DESIGN
→ HORIZON_SCAN

RESOURCE_DESIGN
→ BASELINE_REPRODUCTION

BASELINE_REPRODUCTION
→ RESOURCE_DESIGN
→ CORE_EXPERIMENT

CORE_EXPERIMENT
→ CORE_EXPERIMENT
→ DIAGNOSIS
→ EVIDENCE_EXPANSION

DIAGNOSIS
→ CORE_EXPERIMENT
→ PIVOT

PIVOT
→ IDEA_FORMATION
→ GAP_SYNTHESIS
→ CORE_EXPERIMENT

EVIDENCE_EXPANSION
→ CORE_EXPERIMENT
→ PAPER_AUDIT

PAPER_AUDIT
→ CORE_EXPERIMENT
→ PAPER_ASSEMBLY

PAPER_ASSEMBLY
→ PAPER_REVIEW

PAPER_REVIEW
→ CORE_EXPERIMENT
→ PAPER_ASSEMBLY
→ COMPLETE
```

必须提供：

```python
def validate_transition(
    current: ResearchPhase,
    proposed: ResearchPhase,
) -> bool:
    ...
```

---

# 四、Research State Schema

至少实现：

```python
class ResearchState(BaseModel):
    project: ProjectInfo

    phase: ResearchPhase

    constraints: ResourceConstraints

    literature: LiteratureState
    gaps: GapState
    hypotheses: HypothesisState
    ideas: IdeaState
    experiments: ExperimentState
    evidence: EvidenceState
    claims: ClaimState

    decisions: list[DecisionRecord]

    human_checkpoint: HumanCheckpoint | None

    next_actions: list[ResearchAction]

    iteration: int
    created_at: datetime
    updated_at: datetime
```

---

# 五、核心 Schema

## ResearchGap

```python
class ResearchGap(BaseModel):
    id: str

    title: str

    observed_phenomena: list[str]

    supporting_papers: list[str]

    common_limitation: str

    root_cause_hypothesis: str

    why_existing_methods_fail: str

    missing_capability: str

    potential_interventions: list[str]

    related_techniques: list[str]

    minimum_viable_experiment: str

    expected_signal: str

    falsification_criterion: str

    novelty_score: float
    feasibility_score: float
    research_value_score: float
    publication_score: float
    risk_score: float

    status: Literal[
        "candidate",
        "shortlisted",
        "selected",
        "rejected",
    ]
```

## Hypothesis

```python
class Hypothesis(BaseModel):
    id: str

    statement: str

    mechanism: str

    predicted_outcome: str

    falsification_criterion: str

    supporting_evidence: list[str]
    contradicting_evidence: list[str]

    status: Literal[
        "proposed",
        "active",
        "weakly_supported",
        "supported",
        "inconclusive",
        "weakly_rejected",
        "rejected",
    ]
```

## Experiment

```python
class Experiment(BaseModel):
    id: str

    hypothesis_id: str

    research_question: str

    baseline_ids: list[str]

    independent_variables: list[str]
    dependent_variables: list[str]
    control_variables: list[str]

    expected_outcome: str

    success_criterion: str

    falsification_criterion: str

    model: str | None
    dataset: str | None

    seeds: list[int]

    estimated_gpu_hours: float | None

    status: Literal[
        "planned",
        "approved",
        "running",
        "completed",
        "failed",
        "cancelled",
    ]

    metrics_artifact: str | None

    observation: str | None
    interpretation: str | None

    confounders: list[str]

    next_experiment_ids: list[str]
```

---

# 六、Evidence Model

必须实现显式 Evidence Level。

```python
class EvidenceLevel(str, Enum):
    E0_SPECULATION = "E0"
    E1_LITERATURE = "E1"
    E2_SINGLE_EXPERIMENT = "E2"
    E3_REPLICATED = "E3"
    E4_ROBUST = "E4"
```

约定：

```text
E0
仅 hypothesis/speculation

E1
有可靠文献支持

E2
单实验支持

E3
多 seed / replicated 支持

E4
跨 setting / model / dataset 等稳定支持
```

实现 `Claim`：

```python
class Claim(BaseModel):
    id: str

    statement: str

    evidence_level: EvidenceLevel

    supporting_papers: list[str]
    supporting_experiments: list[str]

    contradicting_evidence: list[str]

    confidence: float

    allowed_language_strength: str
```

Paper Writer 必须遵守 Claim Evidence。

---

# 七、Action Schema

Orchestrator 不允许输出自由文本 action。

定义：

```python
class ActionType(str, Enum):
    SEARCH_LITERATURE = "search_literature"
    EXPAND_LITERATURE = "expand_literature"

    MINE_GAPS = "mine_gaps"
    SYNTHESIZE_GAPS = "synthesize_gaps"

    REQUEST_TOPIC_SELECTION = "request_topic_selection"

    FORM_IDEA = "form_idea"
    REVIEW_IDEA = "review_idea"

    REQUEST_RESOURCES = "request_resources"

    DESIGN_EXPERIMENT = "design_experiment"
    REPRODUCE_BASELINE = "reproduce_baseline"
    RUN_EXPERIMENT = "run_experiment"

    ANALYZE_RESULT = "analyze_result"
    DIAGNOSE_FAILURE = "diagnose_failure"

    PIVOT = "pivot"

    EXPAND_EVIDENCE = "expand_evidence"

    AUDIT_PAPER = "audit_paper"
    WRITE_PAPER = "write_paper"
    REVIEW_PAPER = "review_paper"

    COMPLETE_PROJECT = "complete_project"
```

然后：

```python
class ResearchAction(BaseModel):
    action: ActionType

    target: str | None

    reason: str

    priority: float

    estimated_cost: float | None

    expected_information_gain: float | None
```

---

# 八、Orchestrator 工作机制

每轮：

```python
state = state_store.load(project_id)

context = context_builder.build_for_orchestrator(state)

decision = orchestrator.decide(context)

validate_action(decision)

workflow.execute(decision)

state_store.save(state)
```

Orchestrator context 不允许包含整个项目所有原始内容。

只提供：

* 当前 phase
* active hypotheses
* 最近 decisions
* 当前最大 uncertainty
* 最近实验摘要
* 当前 GAP
* resource budget
* next candidates
* human checkpoint 状态

---

# 九、Context Builder

这是核心组件。

实现：

```python
class ContextBuilder:
    def for_orchestrator(...)
    def for_literature(...)
    def for_gap_mining(...)
    def for_idea_review(...)
    def for_experiment(...)
    def for_diagnosis(...)
    def for_paper(...)
```

原则：

只注入当前任务需要的信息。

例如实验诊断上下文：

```text
Current Experiment
Parent Hypothesis
Relevant Previous Experiments
Baseline
Method Version
Resource Constraints
Observed Logs
Relevant Literature
```

不要注入 300 篇论文全文。

---

# 十、Prompt Loader

所有 Prompt 都从文件加载。

支持自动拼装：

```text
GLOBAL_SYSTEM

+

GLOBAL_POLICY

+

ROLE_PROMPT

+

TASK_CONTEXT
```

例如：

```python
prompt = prompt_loader.compose(
    role="failure_diagnosis",
    policies=[
        "evidence",
        "experiment",
        "resource",
    ],
)
```

不要把 Prompt 硬编码在 Python 源码。

---

# 十一、LLM 抽象层

不要把系统绑定到单一厂商。

定义：

```python
class LLMClient(Protocol):

    async def generate(
        self,
        messages: list[Message],
        *,
        model: str,
        temperature: float,
    ) -> str:
        ...

    async def generate_structured(
        self,
        messages: list[Message],
        schema: type[BaseModel],
        *,
        model: str,
    ) -> BaseModel:
        ...
```

第一版可以提供：

```text
MockLLMClient
OpenAICompatibleClient
```

重点是接口稳定。

模型 routing 独立实现，例如：

```yaml
orchestrator:
  model: reasoning-model

literature:
  model: search-capable-model

reviewer:
  model: reasoning-model

paper:
  model: writing-model
```

---

# 十二、Tool abstraction

定义统一工具协议：

```python
class Tool(Protocol):
    name: str

    async def run(
        self,
        input: BaseModel,
    ) -> BaseModel:
        ...
```

先提供 interface / mock：

```text
SearchTool
PaperSearchTool
CodeExecutionTool
RepositoryTool
```

第一版即使某些工具暂未接真实 API，也必须有 mock adapter 和清晰 TODO。

Research workflow 不得直接依赖具体搜索 API。

---

# 十三、Literature Workflow

实现：

```text
broad topic
↓
search queries
↓
paper candidates
↓
paper extraction
↓
paper matrix
↓
research clusters
↓
gap miner
↓
gap candidates
↓
gap synthesis
↓
3-5 shortlisted GAPs
↓
human checkpoint
```

重要：

PaperReference 必须保存：

```text
title
authors
year
venue
url / identifier
verified
main claim
method
limitations_claimed
limitations_inferred
open_source
relevance
```

`verified=False` 的论文不能被用于“已有工作证明...”这种强事实陈述。

---

# 十四、Human Checkpoint

系统必须支持暂停。

```python
class HumanCheckpoint(BaseModel):
    required: bool

    type: Literal[
        "topic_selection",
        "resource_input",
        "major_pivot",
    ]

    prompt: str

    options: list[str]

    resume_phase: ResearchPhase
```

当 checkpoint.required=True：

workflow 不继续自动推进。

CLI 显示问题，并等待下一次用户输入。

不要把 minor decision 都升级成 checkpoint。

---

# 十五、Idea Review Loop

实现：

```text
Idea Designer
↓
Attack Reviewer
↓
Defense
↓
Attack Reviewer
↓
Defense
↓
Meta Reviewer
```

默认最多：

```python
MAX_IDEA_REVIEW_ROUNDS = 3
```

Meta Reviewer 输出：

```text
PROCEED
PROCEED_WITH_MODIFICATIONS
RETURN_TO_LITERATURE
SIMPLIFY
PIVOT
```

必须结构化。

---

# 十六、Experiment Workflow

实验设计按层级：

```text
L0 sanity check
L1 minimum viable experiment
L2 core experiment
L3 ablation / mechanism validation
L4 generalization / scaling
L5 final paper evidence
```

默认禁止：

```text
L1 没 signal
→ 直接跑 L4
```

Experiment Planner 应最大化：

```text
Expected Information Gain / Compute Cost
```

而不是最大化：

```text
Probability of Positive Result
```

---

# 十七、Baseline Reproduction Gate

核心 baseline 没复现时，默认不能进入主实验。

状态：

```text
PENDING
PASS
MARGINAL
FAIL
```

FAIL 时必须进入 diagnosis。

保存：

```text
reported_result
reproduced_result
difference
variance
environment_diff
diagnosis
```

---

# 十八、Experiment Runner

第一版不要实现复杂 cluster scheduler。

实现最小可用接口：

```python
class ExperimentRunner:

    async def run_shell_experiment(
        self,
        command: str,
        cwd: Path,
        env: dict[str, str],
    ) -> ExperimentExecutionResult:
        ...
```

必须：

* 捕获 stdout/stderr
* 保存 return code
* 保存开始/结束时间
* 保存 git commit
* 保存 command
* 保存 environment snapshot
* 保存 artifact 路径

不允许 LLM 自己声称实验结果。

只有 Runner 真实产生的结果可以标记为：

```text
experiment-backed evidence
```

---

# 十九、Experiment Diagnosis Loop

实验结果不符合预期时，默认考虑：

```text
implementation bug
optimization failure
hyperparameter regime
insufficient training
false hypothesis
subset-specific effect
bad metric
baseline unfairness
statistical noise
hidden compute tradeoff
```

每个 explanation 都要：

```text
EvidenceFor
EvidenceAgainst
Probability
CheapestDiagnosticExperiment
```

然后选择最高：

```text
information_gain / cost
```

的诊断实验。

一次不要改很多变量。

---

# 二十、Stopping / Pivot Policy

配置：

```yaml
loops:
  max_idea_review_rounds: 3
  max_consecutive_diagnostic_experiments: 5
  max_failed_variants_per_hypothesis: 3
  max_major_method_revisions: 3
```

但硬次数只是 fallback。

优先根据：

```text
ExpectedValueOfNextExperiment
```

判断。

如果：

```text
remaining uncertainty low
AND
probability experiment changes decision low
AND
experiment cost high
```

则停止该方向。

---

# 二十一、Paper Workflow

禁止 PaperWriter 直接读所有聊天记录。

必须：

```text
Research State
+
Evidence
+
Experiment Ledger
+
Literature
↓
PaperPackageBuilder
↓
PaperPackage
↓
PaperWriter
```

PaperPackage 至少包含：

```text
problem
gap
root cause
hypothesis
method
contributions
related work positioning
experimental setup
main results
ablations
analysis
failure cases
limitations
claim-evidence matrix
tables
figure requirements
citations
do-not-claim list
```

每个实验数字必须映射至：

```text
EXP-ID
```

---

# 二十二、Research Skill

创建：

```text
skills/research-agent/SKILL.md
```

它只作为入口和 capability contract。

不要把所有 prompt 写进去。

内容包括：

```text
What this skill does

Inputs

Persistent state

Research phases

Human checkpoints

Artifacts produced

Scientific evidence requirements

How to resume a project
```

---

# 二十三、CLI

实现至少：

```bash
research-agent init my_project

research-agent status my_project

research-agent run my_project

research-agent resume my_project

research-agent inspect my_project state

research-agent inspect my_project gaps

research-agent inspect my_project experiments
```

例如：

```bash
research-agent init adaptive_reasoning
```

创建：

```text
projects/adaptive_reasoning/
├── state.json
├── project.yaml
└── artifacts/
```

---

# 二十四、MVP Workflow

第一版必须实际跑通：

```text
INIT
↓
BOOTSTRAP
↓
HORIZON_SCAN
↓
GAP_MINING
↓
GAP_SYNTHESIS
↓
TOPIC_SELECTION CHECKPOINT
↓
IDEA_FORMATION
↓
IDEA_REVIEW
↓
RESOURCE CHECKPOINT
↓
EXPERIMENT_PLAN
```

实验 runner 和 paper loop 可以提供可工作的简单实现，但架构必须完整。

---

# 二十五、Mock Mode

必须支持：

```bash
research-agent run demo --mock
```

不访问真实 LLM / web / GPU。

Mock 模式自动生成：

* 伪 paper data
* gap output
* orchestrator decision
* idea review
* experiment plan

用于 CI 验证 workflow。

Mock 数据必须明确标记为：

```text
synthetic_test_data
```

绝不能混入真实科研结果。

---

# 二十六、测试要求

至少实现：

### State

```text
serialization roundtrip
schema validation
state version
```

### Workflow

```text
valid transition passes
invalid transition rejected
checkpoint pauses execution
checkpoint resume works
```

### Evidence

```text
unexecuted experiment cannot become E2
unsupported claim rejected
```

### Context

```text
context builder excludes unrelated artifacts
```

### Orchestrator

```text
structured action parsing
illegal action rejection
```

### Mock E2E

```text
project init
→ literature
→ gaps
→ checkpoint
→ user choice
→ idea
→ review
→ experiment plan
```

完整通过。

---

# 二十七、Logging

使用结构化 logging。

每个 workflow step 至少记录：

```text
project_id
phase
iteration
agent_role
prompt_profile
action
duration
status
artifact_ids
```

不要打印完整 API key 或敏感环境变量。

---

# 二十八、Configuration

创建：

```yaml
project:
  default_target_venue: null

models:
  orchestrator: default
  research: default
  reviewer: default
  experiment: default
  paper: default

loops:
  max_idea_review_rounds: 3
  max_diagnostic_experiments: 5

research:
  max_shortlisted_gaps: 5

artifacts:
  root: ./projects

execution:
  allow_shell: false
  timeout_seconds: 3600
```

Shell execution 默认关闭。

必须显式开启。

---

# 二十九、README

README 必须真正让开发者可以运行。

包含：

```text
Architecture
Installation
Configuration
Quickstart
Mock Demo
Project Lifecycle
Directory Layout
How to add a prompt
How to add a tool
How to add a workflow phase
How to add an LLM provider
Human checkpoint behavior
Scientific evidence model
Security considerations
Roadmap
```

---

# 三十、工程质量要求

代码必须：

* Python 3.11+
* type hints
* Pydantic v2
* asyncio-compatible
* minimal coupling
* dependency inversion
* no giant god class
* no giant workflow prompt
* unit-testable
* formatter/linter friendly

优先简单清晰，不要过早引入：

* Kubernetes
* Redis
* distributed queue
* microservices
* vector DB
* complex frontend

第一版使用：

```text
local JSON state
local filesystem artifacts
single-process async runtime
```

即可。

后续存储层必须可替换。

---

# 三十一、实现顺序

不要一次性随意写大量代码。

按以下顺序执行：

## Milestone 1

完成：

```text
schemas
state store
phase enum
transition graph
tests
```

确保测试通过。

## Milestone 2

完成：

```text
LLM abstraction
prompt loader
structured output
mock LLM
```

确保测试通过。

## Milestone 3

完成：

```text
Orchestrator
Context Builder
Workflow Engine
```

确保测试通过。

## Milestone 4

完成：

```text
Bootstrap
Literature
Gap Mining
Gap Synthesis
Human Checkpoint A
```

完成一次 mock E2E。

## Milestone 5

完成：

```text
Idea Formation
Reviewer Loop
Resource Checkpoint
Experiment Planner
```

完成 MVP E2E。

## Milestone 6

完成：

```text
Experiment Runner
Diagnosis
Pivot
Evidence
Paper pipeline
```

---

# 三十二、你的工作方式

从现在开始：

1. 先检查当前 repository。

2. 如果 repository 为空，直接初始化项目。

3. 如果已有代码，先理解现有架构，尽量兼容。

4. 给出简短实现计划后开始修改代码。

5. 不要停留在建议层。

6. 不要每完成一个文件就询问用户。

7. 遇到非关键设计选择时自行决定，并记录到 README / ADR。

8. 每个 milestone 后运行测试。

9. 如果测试失败，先修复再继续。

10. 不要伪造测试成功。

---

# 三十三、最终验收标准

任务完成时必须至少满足：

```text
[ ] package 可安装
[ ] CLI 可运行
[ ] project 可初始化
[ ] state 可持久化
[ ] transition 有校验
[ ] prompts 模块化
[ ] LLM provider 可替换
[ ] mock provider 可运行
[ ] context builder 存在
[ ] human checkpoint 可暂停/恢复
[ ] gap workflow 可跑通
[ ] idea-review workflow 可跑通
[ ] experiment planning 可跑通
[ ] artifact store 可用
[ ] evidence schema 可用
[ ] tests 全部通过
[ ] mock end-to-end demo 通过
[ ] README 完整
```

完成后输出：

```text
IMPLEMENTATION SUMMARY

ARCHITECTURE DECISIONS

FILES CREATED/MODIFIED

HOW TO RUN

TEST RESULTS

CURRENT LIMITATIONS

NEXT RECOMMENDED MILESTONE
```

不要只输出架构设计文档。

**直接实现。**
