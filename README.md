# Insight Poster

把“读完一份文档”变成“看懂一件事”。

一个只有 [SKILL.md](SKILL.md) 的轻量 skill：让 coding agent 先提炼信息，再把论文、会议纪要、调研综述、方案、复盘或长文档做成便于扫读的**单页 HTML 信息海报**。不是 Markdown 分卡器，也不限于学术会议海报。

**English:** A lightweight, single-file skill for turning papers, meeting notes, research reviews, and other documents into readable, self-contained HTML posters. It guides a coding agent's information design; it is not a rendering framework or service.

## 看一个例子

![明确为虚构会议示例](examples/meeting-summary.png)

[查看示例 HTML 源文件](examples/meeting-summary.html) · [阅读虚构会议输入](examples/meeting-notes.txt)

下载后在浏览器打开 HTML，即可体验页面操作；GitHub 文件页展示的是源码。示例输入明确为虚构，不来自真实会议或私人对话。它展示一种材料的处理方式，**不是适用于所有材料的质量基准**；不同 agent、系统字体和浏览器可能产生不同的内容取舍与排版。

此示例采用 1920 × 1200 画布，对应 508 × 317.5mm 单页打印。skill 的默认值为 1920 × 1320，但允许按内容调整比例；打印尺寸须跟随实际画布换算。

## 它强调什么

- **先理解，再排版**：围绕读者应带走的主张组织内容，不照搬原文目录。
- **上方抓重点，下方有顺序**：标题与一句话主张 → 关键理解条 → 上半部核心视觉；下方沿统一网格安排证据、解释、边界或行动。
- **图形表达真实关系**：有比较才做对照，有时序才画时间线；无数据不硬凑 KPI，不编造数字、责任人、期限或结论。
- **保留必要限定**：区分事实、主张、建议、已定事项与待决问题；不能为了好看省略分歧和边界。
- **配色有理由**：根据内容或品牌选择冷静技术、温暖编辑、清晰决策等气质；保持语义同色，不给每张卡片随机上色。
- **交付轻量**：核心只是一份指令文件，无框架、包依赖、CI 或专用渲染服务。

## 获取与使用

从 [GitHub 仓库](https://github.com/N0TPO3T/insight-poster) 下载 ZIP，或克隆：

```sh
git clone https://github.com/N0TPO3T/insight-poster.git
```

也可以只下载 [SKILL.md](https://raw.githubusercontent.com/N0TPO3T/insight-poster/main/SKILL.md)。

1. 在能读取文件、编写 HTML 的 coding agent 中打开项目，或把 `SKILL.md` 提供给它。
2. 明确让 agent 先阅读并遵循这份 skill，再提供材料与用途。
3. 下载或打开生成的 HTML；有浏览器工具时，让 agent 检查实际显示与打印效果。

如果你的 agent 支持本地 skill，可按**该 agent 的文档**把 `SKILL.md` 放入其支持的 skill 目录。目录布局、发现方式与启用步骤由 agent 决定；本项目不提供安装器，也不承诺复制后自动注册。

克隆或下载完整仓库后，可直接试用以下提示词；若只下载了 `SKILL.md`，请将示例输入路径换成自己的材料路径：

```text
请先阅读并遵循 SKILL.md，再读取 examples/meeting-notes.txt。
面向未参会的协作成员，制作一张中文单页信息海报：
突出已定事项、尚有分歧的问题，以及有明确依据的后续行动。
保留虚构示例标识，不补造数字、责任人或期限。
输出为 meeting-poster.html，只交付这一个可离线打开的 HTML。
如果有浏览器工具，请打开成品检查适应窗口、原尺寸和打印效果；
没有实际检查的部分，请明确说明。
```

用于自己的材料时，替换输入文件、读者与用途即可；有品牌色、纸张或语言要求时一并说明。

## 输出与运行边界

- 默认只输出**一个离线 HTML**：内联样式、必要的 SVG/脚本和图片，使用系统字体；不依赖 CDN、远程字体或网络请求。
- 页面提供“**适应窗口 / 原尺寸**”与“**打印 / 保存 PDF**”操作。默认固定横向画布、整体等比缩放；小屏不是另做一套移动端布局。
- 默认不附带策划稿、配置文件、多版本、PNG 或 PDF。需要额外导出时再明确提出；仓库截图是公开演示材料，不代表每次生成都会附带截图。
- skill 本身不指定模型，也不负责调用外部模型、解析 PDF 或维护渲染引擎。**源文件读取、PDF 解析与图像提取、HTML 生成、浏览器渲染及可选导出，均取决于所用 agent 的能力和可用工具。**
- 没有浏览器工具时只能进行可用的结构检查，视觉效果应标为未验证；没有实际检查打印或导出的 PDF，也不能声称其分页、裁切已通过检查。
- 海报是原始材料的阅读入口，不替代完整记录。生成内容与重要数据仍需核对，打印结果也受浏览器和纸张设置影响。

## 隐私与公开分享

“离线 HTML”指成品无需联网展示，**不代表 agent 处理材料时一定在本地运行**；提交敏感材料前请了解所用工具的数据政策。

默认不得把完整原文、私人对话、本机绝对路径或敏感信息藏入 HTML 注释、脚本或元数据。公开分享前检查可见与隐藏内容，未经明确授权不上传原始材料或生成物。本仓库的公开会议示例为虚构内容，不包含真实会议信息。

## 来源、贡献与许可

流程借鉴 [Paper2Poster 官方轻量 skill](https://github.com/Paper2Poster/Paper2Poster/blob/424809d4bf041b26cd9dc1efc660ba559bee2f3c/skills/SKILL.md) 的源文优先、文案压缩、主图优先与质量检查原则；固定版本引用也保留在 [SKILL.md](SKILL.md) 中。本项目**不依赖或调用 PosterAgent 后端**，不复现其完整流水线，也不宣称性能或质量优于其他工具。

欢迎通过提交和 Pull Request 改进 `SKILL.md` 或示例，说明希望改善的实际使用问题即可；请勿提交未经授权的真实材料。

采用 [MIT License](LICENSE)。
