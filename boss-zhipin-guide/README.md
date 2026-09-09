# boss-zhipin-guide · BOSS直聘（Windows 桌面客户端）牛人自动筛选 + 打招呼

> 一套可复现的 GUI 自动化流程：按目标 JD 在 BOSS直聘「牛人推荐流」筛选候选人、核对简历、
> 对符合条件者打招呼，并以 **10 个招呼为一批** 写入 Excel 记录。

## 内容

```
.omp/skills/boss-zhipin-guide/SKILL.md   ← 流程 skill（锚点表/判定标准/批次规则/岗位可替换）
tools/                                    ← 自动化工具（PowerShell + Python）
  wrect.ps1 shot.ps1 click.ps1 keys.ps1 scroll.ps1 snap.ps1 zoom.ps1 invert.ps1
  append_batch.py                         ← Excel 分批写入（每 10 个招呼一批）
BOSS直聘自动化经验纪要.md                  ← 实跑经验与坑
README.md                                 ← 本文件
```

## 核心特性

- **锚点表**：界面固定坐标（打招呼按钮 / 「知道了」/ 关闭 X / 侧栏入口），比视觉读数更可靠。
- **JD 可替换**：SKILL.md 第 0 节为 JD 配置区，换岗位只需更新配置 + 判定标准，其余流程不变。
- **分批记录**：每成功发出 10 个招呼写入一次 Excel；一张表多岗位（按「岗位」列区分）。
- **红线**：遇到付费/推销弹窗绝不购买；用户暂停即停手。

## 使用

1. BOSS直聘桌面客户端（招聘者账号）登录并保持窗口可见。
2. 在 omp（Coding Agent）中让模型加载 `skill://boss-zhipin-guide` 并给出目标 JD。
3. 模型按 skill 流程自动：定位 → 预筛 → 核对 → 招呼 → 分批落盘。

## 环境

- Windows 11 / 100% DPI / BOSS直聘桌面客户端（Electron）
- Python 3.12 + openpyxl（`pip install openpyxl`）

> 本仓库不包含候选人个人信息（记录文件运行在本地，未随仓库分发）。
