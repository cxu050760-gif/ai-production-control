# 06 · 新 AI 接班文件（NEW AI BOOTSTRAP）

> 你什么都不用翻。读完这一篇（10 分钟）+ 03_CAPABILITY_REGISTRY.md，就能开工。
> 生成：2026-08-20 21:00 接管审计。

---

## 0 · 读前必知（防误解四件事）

**A. 术语大白话表**（全文通用，先看懂再往下读）：

- **GOAL**＝一个真实任务目标，写在一个 UTF-8 文本文件里。
- **RUN / RUN_ID**＝一个 GOAL 的一次执行过程；ID 形如 `RUN-20260820-105229-b256`；它的状态存在磁盘 state.json 里，永远以磁盘为准。
- **R**＝网页审查者。**R-PROD**＝生产审查会话；它的 url 只能从 `E:\执衡\05_资源\会话注册.json` 里取——打开文件找 `roles` → `R-PROD` → `url` 字段（以 `https://chatgpt.com/c/` 开头，不要拿别的字段）；**E-LAB**＝实验会话，当前未指派，它的 url 是 null/UNASSIGNED 属于**正常现象**，不要慌、不要自己填一个、不要新建会话。
- **PASS / REWORK / BLOCKED**＝R 裁决的三种结果：通过／按它说的部分返工再交／停止并上报。
- **桥（Bridge）**＝自动操作网页 AI（ChatGPT 或 DeepSeek，由 RUN 的 R_URL 域名自动识别，调用方式完全相同）收发消息的整条链路；**bsk**＝桥的底层浏览器控制程序；**daemon**＝bsk 的后台服务（端口 52900，空闲会自己停，不用人工管）。
- **marker**＝R 回复末尾的完成标记 `===WB_DONE:...===`（2026-09-01 起的中立命名，适配 ChatGPT/DeepSeek 双通道；此前历史记录中为 `===CHATGPT_DONE:...===`，旧证据文件不改）；**DONE_NO_MARKER**＝回复完整但缺标记时的容错判定。
- **Runtime 黑盒**＝只用 run.cmd 的高层命令（work/report/status/health），底层桥的细节由它代管，你不用懂也不用碰；DeepSeek 的三模式（快速/专家/识图）也由它按任务自动选择，不是你的职责。
- **冻结**＝已验证并封存的资产：没有新失败证据 + 负责人授权，禁止修改。
- **canonical / stale**＝唯一权威版本／已作废禁止使用的版本。

**B. 占位符规则**：命令里所有 `<尖括号>` 包着的内容都是占位符，必须替换成真实值，**严禁带着尖括号原样执行**。

**C. 命令安全分级**（照字面执行前必看）：

- 只读安全（随时可跑）：`run.cmd health / status / metrics`、`chatgpt_bridge status`、`ai-control.cmd doctor`、wb_agg / wb_index。
- **真实动作（禁止"试跑"！）**：`run.cmd work / report / send`（会真实发消息到生产 ChatGPT 审查会话）、`chatgpt_bridge send / upload / open / close`（真实操作真实 ChatGPT 网页）、启动并行 Worker（真实消耗算力）。没有真实任务就不要执行这些命令。

**D. 执行壳说明**：示例里 `& "路径\xxx.cmd" 参数` 是 PowerShell 里运行带引号路径程序的写法；在 cmd 里直接运行 `"路径\xxx.cmd" 参数` 即可。本机命令统一用规范 Python 全路径（见 §3），不要裸写 `python`。

## 1 · 项目是什么（30 秒）

**执衡 = 个人 AI 自动生产环境**：用户只给一个真实目标，系统自主完成「理解→规划→执行→送审→返工→PASS→交付」。核心原则：AI/模型可换、任务状态不可丢；便宜 AI 干劳动、强 AI（ChatGPT）干审查。

## 2 · 现在什么状态（1 分钟）

- **已跑通并冻结**：ChatGPT Bridge（网页自动化收发）、Runtime V1（生产审查闭环，43 个 RUN）、WorkBuddy Parallel（2-10 路并行，19 条记录）。
- **建设中**：产品本体 Controller（M0.5~M3 本地测试 75/75 PASS，独立 R 累计审查=REWORK 返工中；对外诚实返回 PRODUCT_NOT_READY）。
- **在途未完成**：M4 WebModel 交付（RUN-20260820-105229-b256，REWORK）——**不要当 DONE**。
- 项目整体未到 PROJECT_DONE（A_GLOBAL_DONE=false）。

## 3 · 工具在哪里、怎么调用（3 分钟）

| 我要 | 用什么 | 一句话命令 |
|---|---|---|
| 确认链路健康（只读安全） | Runtime | `& "E:\WB\tools\ai-production-control\runtime\run.cmd" health` |
| 交付任务给 ChatGPT 审查（**真实动作**） | **Runtime**（唯一生产入口） | 把 GOAL 写成 UTF-8 的 goal.txt 后：`& "E:\WB\tools\ai-production-control\runtime\run.cmd" work --goal-file goal.txt --r-url <R-PROD.url> --worker-id <随便一个能标识你的字符串，比如模型名+日期>`，返回 run_id；干完活把结果写进 result.txt，再跑 `& "E:\WB\tools\ai-production-control\runtime\run.cmd" report --run-id <run_id> --message-file result.txt` |
| 查任务状态/恢复（只读安全） | Runtime | `& "E:\WB\tools\ai-production-control\runtime\run.cmd" status --run-id <run_id>`（state 是唯一权威） |
| 派多个 AI 并行干活（**真实动作**） | **WorkBuddy Parallel** | 只能在 WorkBuddy 原生 PowerShell 里启动：先 `$env:CODEBUDDY_CONFIG_DIR='C:\Users\17838\.workbuddy'`，再 `& "C:\Users\17838\.workbuddy\skills\workbuddy-parallel\scripts\Invoke-WorkBuddyParallel.ps1" -Mode Run -TasksFile <tasks.json> -MaxWorkers <路数，默认5，上限10>`。**如果你不是 WorkBuddy 会话：你启动不了（会被安全策略拦截），把需求交给主 Agent** |
| 汇聚并行结果（本地读写，安全） | wb_agg / wb_index | `& "C:\Users\17838\AppData\Local\Programs\Python\Python312\python.exe" "E:\执衡\02_正在开发\wb_agg\wb_agg.py" <job目录>`（wb_index.py 同理，参数换 parallel-runs 根目录） |
| 直接操作 ChatGPT 网页（仅桥维护；send/upload 是**真实动作**） | chatgpt_bridge | 只读自检：`chatgpt_bridge status`；其余子命令见 03 卡 B-1，普通任务禁用 |
| TRAE 会话自动续跑 | Trae-Ralph | 见 03 卡 C-1 门禁流程（用 inject:cn，勿用 start:cn） |
| 体检产品本体（只读安全） | Controller | `& "E:\WB\tools\ai-production-control\ai-control.cmd" doctor` |

**详细参数、证据、禁令 → 03_CAPABILITY_REGISTRY.md 对应卡片。**

## 4 · 铁律（违反即任务失败）

1. 日常 ChatGPT 通信只走 Runtime 黑盒；不碰 bsk/daemon/端口/marker/浏览器实例。
2. R_URL 只从 `E:\执衡\05_资源\会话注册.json` 读；不自建会话、不猜 URL。
3. 冻结资产不改：桥、Runtime、审计证据、Trae-Ralph 补丁、冷存档（冷存档严禁当现役）。
4. builder_state.json 是 stale，不作恢复源。
5. 换会话/压缩后不信记忆：`run status` + 磁盘为准。
6. 不永久删除任何用户文件；不覆盖 E:\执衡 他人未提交改动。
7. RUN_DONE ≠ PROJECT_DONE；局部测试 PASS ≠ FINAL_PRODUCT_ACCEPTED。
8. BLOCKED、缺 R-URL、要动冻结资产、超范围想法 → 停下报告，记 KNOWN_GAP。
9. 你自己的临时文件（goal.txt、result.txt 等）放在**你自己的工作区临时目录**，命令里一律用绝对路径；**不要写进 E:\执衡、E:\WB\tools 等项目目录**（那里有别人的未提交改动和冻结资产）。E:\执衡、E:\WB、C:\Users\17838\.workbuddy 都是现役目录：不清理、不删除、不移动。
10. 任何环境报错（如 `RUNTIME_ENV_BLOCKED`、命令找不到）：停下，把完整报错原样报告给用户/主 Agent；**不要自己安装软件、改 PATH、换解释器**。

## 5 · 下一步候选（按 02_CURRENT_STATE.md 复核后再动手）

**注意：以下是给主 Builder / 接班 AI 的任务候选。如果你只是被派来干具体活的普通 Worker，请等待明确指派，不要看到清单就自行开工。**

1. 收口 M4 WebModel：按 RUN-105229-b256 的 next_action 补全→重测→`report` 重交 R。
2. 完成 M1~M3 累计审查的开放返工项②（Stable/Candidate 晋级+回滚 lineage）。
3. M1 独立 REVIEW：等待/建设「自动创建隔离 R 会话」能力（缺口 G-2）。
4. 回 PROJECT 级：每完成一个 REAL GOAL → 持久化→冻结→git 提交→扫下一项最高价值真实工作。

## 6 · 文件地图（只列必读）

```
E:\执衡\00_先看这里\能力操作手册_20260820\   ← 本手册（你现在在这）
E:\执衡\00_先看这里\CODEX_接管状态.md        ← 接管全景导航（结论回磁盘复核）
E:\执衡\交接.md                              ← 上一任 Builder 交接（2026-08-20）
E:\执衡\05_资源\会话注册.json                ← R-PROD url 唯一来源
E:\执衡\04_测试证据\                         ← 所有验证证据（审计/接管定轨/家底盘点）
E:\WB\tools\ai-production-control\           ← Controller 仓库 + runtime（生产入口在 runtime\run.cmd）
E:\WB\state\ai-production-control\           ← RUN state + control.db（Tier 0 事实）
E:\WB\tools\bsk-file-bridge\                 ← 桥（冻结）；reports\ 有接手文档
E:\WB\tools\Trae-Ralph\                      ← 自动续跑工具（隔离，冻结补丁）
C:\Users\17838\.workbuddy\                   ← WorkBuddy 配置/skills/parallel-runs
```
