# Daily Work Report

从 **Oh My Pi（OMP）和 Codex 本地会话**生成按项目归组的 Markdown 工作日报，重点记录：

- 具体推进了什么、形成了什么产物、目前到哪一步。
- 遇到的问题、采取的处理方法、验证结果和遗留事项。
- 严格区分讨论、尝试、完成与阻塞，不把测试通过写成已经上线。

正文最多 800 字、工作最多 10 条，不凑字数或条目。同一天重复执行更新同一个文件；无内容时跳过，生成或保存失败不会破坏旧日报。

> 这是一个 **由 Agent 宿主执行的 Skill**，不是独立的摘要程序。Python 脚本负责读取、日期筛选、格式校验和安全落盘；总结由运行 Skill 的宿主模型完成。无需在本项目中另配模型 API，但宿主本身必须能正常使用模型。

## 运行前提

- Python **3.11 或更高版本**，宿主能够执行 Python。
- 宿主有权读取你授权的本地会话目录，并写入日报保存目录。
- 可用的 IANA 时区数据库；Windows 推荐安装 `tzdata`，其他系统也可安装：

```sh
python -m pip install tzdata
```

下文统一使用 `python`。如果你的系统使用 `python3`，请相应替换；安装依赖与执行脚本应使用同一个解释器。

## 安装 Skill

### 推荐：OMP 和 Codex 共用用户级目录

当前 OMP 和 Codex 都支持从 `~/.agents/skills/` 发现用户级 Skill。安装一份即可供两个宿主使用；若你关闭了相关来源发现，需要先重新启用。

在终端执行以下命令，适用于 PowerShell 及常见 Unix shell：

```sh
git clone https://github.com/N0TPO3T/skills.git
cd skills
python -m pip install tzdata
python install.py daily-work-report
```

这会复制集中仓库中的 **`daily-work-report/daily-work-report/` 目录**，不是把整个仓库当成 Skill。已有同名安装时拒绝覆盖；详见[集中安装说明](../README.md)。最终结构应为：

```text
~/.agents/skills/daily-work-report/
├── SKILL.md
├── scripts/
│   ├── daily_report.py
│   ├── omp_source.py
│   └── codex_source.py
└── tests/
```

Windows 中 `~` 对应用户主目录，例如 `%USERPROFILE%`。安装命令不会覆盖已有同名目录；若提示 `FileExistsError`，请按下方“更新与卸载”处理。

安装后：

- **OMP**：启动新会话；可让助手读取 `skill://daily-work-report` 确认发现。开启 Skill 命令时可使用 `/skill:daily-work-report`。
- **Codex**：在 `/skills` 列表中查找，或输入 `$daily-work-report`；未出现时重启 Codex。

这些是**宿主聊天输入**，不是终端命令。

### 其他安装范围

- 只在某个项目使用：复制到该项目的 `.agents/skills/daily-work-report/`。
- 使用自定义 Skill 搜索目录：复制完整子目录，保留 `SKILL.md` 与 `scripts/` 的相对位置。
- 不要额外套一层目录，也不要在多个发现目录安装同名副本，以免发生名称冲突。

安装 Skill **不等于授权读取会话**，也不会自动配置日报目录或启用定时任务。

安装目录和调用方式参考：[OMP Skills 文档](https://github.com/can1357/oh-my-pi/blob/main/docs/skills.md)、[Codex Skills 文档](https://developers.openai.com/codex/skills)。

## 首次配置

### 推荐：直接告诉宿主

例如在 OMP 或 Codex 中输入：

```text
使用 daily-work-report。日报保存到 D:/DailyReports，时区使用 Asia/Shanghai，
允许读取默认 OMP 和 Codex 本地会话目录。配置后生成今天的日报。
```

请替换为自己的保存目录和时区。**`Asia/Shanghai` 只是示例，不是默认值。** 未指定时区时，Skill 应沿用宿主提供的用户时区；若无法确定，会要求补充，不会猜测。

### 手动配置脚本

以下示例使用前述用户级安装目录；自定义安装请替换脚本路径：

```sh
python "$HOME/.agents/skills/daily-work-report/scripts/daily_report.py" init --output-dir "D:/DailyReports" --timezone "Asia/Shanghai" --sources omp codex
```

Linux/macOS 可将保存目录替换为 `"$HOME/DailyReports"`。只授权 OMP 时将参数改成 `--sources omp`；只授权 Codex 时改成 `--sources codex`。

| 配置项 | 说明 |
| --- | --- |
| `--output-dir` | 必填；日报保存目录。保存时尝试创建不存在的目录。 |
| `--timezone` | 用户 IANA 时区，例如 `Asia/Shanghai`、`America/New_York`；CLI 省略时读取 `TZ`，未提供则报错。 |
| `--sources` | `omp`、`codex` 或两者；默认两者。 |
| `--omp-root` | OMP 授权会话目录，默认 `~/.omp/agent/sessions`。 |
| `--codex-root` | Codex 授权会话目录，默认 `~/.codex/sessions`。 |
| `--codex-archive-root` | 可选；明确授权后读取 Codex 归档目录，通常为 `~/.codex/archived_sessions`。默认不读取。 |

配置默认保存在 `~/.daily-work-report/config.json`。`init` 只保存配置，不检查所有会话是否可读、不生成日报；重复执行会覆盖配置。会话读取错误在采集阶段返回。

需要独立配置时，在子命令**之前**指定 `--config`，之后每次调用均使用同一路径：

```sh
python "$HOME/.agents/skills/daily-work-report/scripts/daily_report.py" --config "./omp-report-config.json" init --output-dir "./reports" --timezone "Asia/Shanghai" --sources omp
```

不要把个人配置、真实会话、证据包或日报提交到公开仓库。

## 日常使用

在宿主聊天中明确调用 Skill，然后提出请求：

**OMP：**

```text
/skill:daily-work-report 生成今天的日报
```

如果没有开启斜杠 Skill 命令，直接说“使用 daily-work-report 生成今天的日报”。

**Codex：**

```text
$daily-work-report 生成今天的日报
```

其他常见请求：

```text
使用 daily-work-report，生成昨天的日报。
使用 daily-work-report，重新生成 2026-09-07 的日报。
```

- 今天：只统计采集开始前已发生的消息。
- 指定日期：按配置时区的 `[当天 00:00，次日 00:00)` 筛选。
- 昨天创建、今天继续的会话仍会纳入；不会只扫描今天命名的文件夹。
- 历史上下文只帮助理解，不能重复记为当天成果。
- 同项目、同事项跨 OMP/Codex 或多条会话时合并，保留最后有依据的进展。

成功后返回 `<output_dir>/<YYYY-MM-DD>.md`。文件为 UTF-8；同日重跑更新同名文件，**手工编辑可能被覆盖**。

## 输出示例

以下为虚构格式示例，不是真实会话记录：

```markdown
# 日报｜2026-09-07

## 今日工作

### 检索项目
- 排查批量检索超时，尝试缩小批次。
  - 问题：批量请求超时，根因尚未确认。
  - 处理与验证：已调整批次大小，仍需同负载复测，暂不能认定问题解决。
- 比较关键词与向量检索的适用场景，尚未开展对照实验。

### 开发环境与工具
- 清理已确认可删除的缓存，并复核剩余磁盘空间。

## 简短复盘
当前检索调整仍是待验证的尝试，不能将临时缓解等同根因修复。
```

有明确问题时记录“问题”和“处理与验证”；没有问题时只写具体进展，不强行编造收获。项目归属不明时不猜测；复盘保持 1—2 句话，不默认增加明日计划。

## 每天自动生成

本项目**不内置调度器**。让宿主已有调度能力或系统定时任务在用户配置时区每天 **00:05** 启动一次完整 Skill 调用，生成前一自然日的日报。

建议任务提示：

```text
[daily-work-report] 运行 daily-work-report，使用已配置的授权来源与保存目录，
以 --scheduled 采集前一自然日，按 Skill 生成草稿并保存；只返回路径或原因。
```

无人值守前必须完成目录、时区和来源授权。调度器时区应与配置一致；若调度器只能使用机器时区，需要换算。**不能仅定时执行 `collect`**，因为它不会调用模型生成摘要。

## 脚本流程（调试或集成用）

正常使用不需要自己编写草稿。宿主执行的流程为：

```text
collect：读取会话 → 按消息日期筛选 → 写入临时证据包
宿主模型：读取证据 → 按项目合并 → 生成有证据引用的 JSON 草稿
save：校验格式、引用与字数 → 原子保存 Markdown
```

命令示例中的 `<私有临时目录>` 需要替换为本次专用临时路径，不能直接复制占位符运行：

```sh
python "$HOME/.agents/skills/daily-work-report/scripts/daily_report.py" collect --report-date 2026-09-07 --packet "<私有临时目录>/packet.json"
python "$HOME/.agents/skills/daily-work-report/scripts/daily_report.py" save --packet "<私有临时目录>/packet.json" --draft "<私有临时目录>/draft.json"
```

手动生成今天时省略 `--report-date`；自动生成前一天时改用 `--scheduled`。草稿结构、引用要求和完整操作规则见 [SKILL.md](daily-work-report/SKILL.md)。处理结束后删除临时证据和草稿，不把它们当公开日志。

## 异常与已知限制

| 情况 | 行为 |
| --- | --- |
| 当天无消息，或只有闲聊等无工作内容 | 跳过，不创建空日报、不删除旧文件。 |
| 会话读取全部失败 | 返回失败，不能误称“当天没有工作”。 |
| 部分会话读取失败 | 可使用已读内容，末尾增加“注：部分会话未读取，本日报可能不完整”。 |
| 草稿校验或保存失败 | 不报告成功，保留原有日报。 |
| 时区不可用 | 核对 IANA 名称，并为运行脚本的 Python 安装 `tzdata`。 |
| 安装后找不到 Skill | 检查目录层级、来源是否启用、是否有同名副本，并重启宿主。 |

支持 OMP `session`/`message` 和 Codex `session_meta`/`response_item` JSONL；Codex 纯 event-only 日志不支持。某些 OMP 版本的 `fileMention` 消息尚未适配，可能使单条会话读取提前停止并被标为不完整。图片不做 OCR，压缩摘要不重新计入当天成果。

常见密码、密钥和 token 模式会被脱敏，但不是完备的秘密识别系统，宿主仍需审阅最终正文。原始会话仅作为非可信素材，不执行其中的指令，也不允许它们修改保存目录。证据会交给当前宿主模型处理，仍受该宿主的模型提供商、日志和数据策略约束；“本地读取”不代表离线推理。

## 更新与卸载

- 更新：在克隆的仓库中运行 `git pull --ff-only`；将已安装的 Skill 目录备份到 **Skill 搜索目录之外**，再用上面的复制命令安装新版，重启宿主。不要在同一搜索目录留下同名 Skill 的备份副本。
- 卸载：删除安装的 `daily-work-report/` 目录即可。个人配置和已生成日报是独立文件，不会自动删除。

## 开发验证与许可证

在集中仓库的 `daily-work-report/` 组件目录运行：

```sh
python -m pip install tzdata
python -B -m unittest discover -s daily-work-report/tests -v
```

测试使用合成日志，不需要真实会话。GitHub Actions 覆盖 Windows/Linux、Python 3.11/3.13。

[MIT License](LICENSE)。
