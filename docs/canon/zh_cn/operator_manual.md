# 04 · AI 操作手册（AI OPERATOR MANUAL）

> 对象：任何接入本项目的 AI。按「我要做什么」查对应小节，照命令执行。
> 总纪律：磁盘是唯一权威；不确定就停下报告，不要猜、不要自建第二套。

---

## Q1 · 我要调用 ChatGPT（审查/交付）怎么办？

**走 Runtime 黑盒，不碰桥底层。**（完整卡片见 03 注册表 R-1）

```powershell
# 1. 取 R-URL（唯一来源，不要猜、不要新建会话）
Get-Content "E:\执衡\05_资源\会话注册.json"   # 取 roles -> R-PROD -> url（https://chatgpt.com/c/ 开头）；E-LAB 的 url 是 null 属正常，勿用

# 2. 开工
& "E:\WB\tools\ai-production-control\runtime\run.cmd" work --goal-file "<UTF-8目标.txt>" --r-url "<R-PROD.url>" --worker-id "<随便一个能标识你的字符串，比如模型名+日期>"

# 3. 干完活，把结果写进 result.txt，交付裁决
& "E:\WB\tools\ai-production-control\runtime\run.cmd" report --run-id "<run_id>" --message-file "<result.txt>"

# 4. PASS→结束；REWORK→只改 R 要求的部分，再次 report；BLOCKED→停下上报
```

**两条安全注意**：① `work` / `report` 会真实发消息到生产 ChatGPT 审查会话——只在有真实任务要交付时使用，**严禁为了"试试命令"而运行**；只读安全的只有 `health` / `status` / `metrics`。② `会话注册.json` 只读引用，**不要修改它**（轮换 R 会话、指派 E-LAB 是主 Agent/用户的职责，见注册表内 rotation_policy）。

例外：只有「桥维护任务」才允许直接用 `chatgpt_bridge`（卡 B-1）。

## Q2 · 我要派并行 Worker 怎么办？

见卡 P-1。流程：写 tasks.json（各 worker working_directory 互不重叠）→ 在 **WorkBuddy 原生 PowerShell** 里调 `Invoke-WorkBuddyParallel.ps1 -Mode Run -TasksFile … -MaxWorkers N`→ 拿 manifest/RESULTS.md → 用 wb_agg/wb_index 汇聚。
默认模型 deepseek-v4-flash；视觉/取证类可 `-Model hy3`；数量按需，不超 10。

## Q3 · 我要 Reviewer 审查怎么办？

你不需要「调用」Reviewer——`report` 就是送审（Q1）。审查会话由 会话注册.json 管理：生产只用 R-PROD；实验 transport 需要 E-LAB，但当前 UNASSIGNED → **停下报告，等指派，不自建会话**。裁决格式：`===REVIEW_VERDICT=== PASS/REWORK`。

## Q4 · 我要跑实验怎么办？

1. 先看是否影响冻结资产：桥/Runtime/审计证据/Trae-Ralph 补丁——**影响即先问主 Agent/用户**。
2. transport 类实验需要 E-LAB 会话：当前未指派 → 报告主 Agent，等 E-LAB 初始化为 VERIFIED_AVAILABLE 再做。
3. Controller 机制实验：在 `E:\WB\tools\ai-production-control` 分支内跑 tests（离线，不碰真桥）；`runtime\test_runtime_offline.py` 55 测试可全离线跑。
4. 任何实验结论落盘到 `E:\执衡\04_测试证据\<主题>\`，标日期。

## Q5 · 我要修改代码，应该先找谁？

| 改什么 | 归属 | 规则 |
|---|---|---|
| Controller 产品代码（src\aicontrol、tests） | E:\WB\tools\ai-production-control（git） | 可改（主 Builder 职责）；改后 TCB=UNVERIFIED_AFTER_CONTROLLER_CHANGE，跑全量回归（当前基线 75/75）+ compileall |
| runtime\（run.cmd/runtime.py） | 冻结资产 | **不改**。问题记录到 07_KNOWN_GAPS.md |
| 桥（bsk/yz_lib/chatgpt_bridge） | 冻结资产 | **不改**。除非有新失败证据并经主 Agent 授权 |
| Trae-Ralph | 隔离目录 E:\WB\tools\Trae-Ralph | 只允许目录内最小兼容修补；禁动执衡/Runtime/桥 |
| E:\执衡 文档/证据 | durable 仓库（git） | 可增补；**不得覆盖他人未提交改动**，不混入无关提交 |
| guardrail_g1/builder_state | PARK 历史样品 | 不改不恢复，等矛盾消除（07_KNOWN_GAPS G-6） |

## Q6 · 上下文被压缩 / 换会话 / 重启后怎么恢复？

不信记忆，按顺序：
1. `run status --run-id <ID>` → status/next_action/next_command 为唯一权威
2. 读 `E:\执衡\05_资源\会话注册.json` 取 R-PROD.url
3. 读本手册 02_CURRENT_STATE.md + 03 注册表
4. 涉及 Trae-Ralph 的恢复另走卡 C-1 的门禁（复述标记+git head 一致）

## Q7 · 环境与常见坑

- 规范 Python：`C:\Users\17838\AppData\Local\Programs\Python\Python312\python.exe`（run.cmd 硬绑定；缺失=RUNTIME_ENV_BLOCKED，不要换壳）
- WorkBuddy 相关必设：`$env:CODEBUDDY_CONFIG_DIR='C:\Users\17838\.workbuddy'`
- 52900 无监听≠故障：daemon idle 自停，生产命令自动拉起；勿手工常驻
- Windows Python 管道中文：喂 UTF-8 时设 `PYTHONUTF8=1`，否则 GBK 乱码
- bash 壳（git-bash）注意：`$_` 会被展开；PowerShell 逻辑写 .ps1 再执行；含中文的 API 查询用 node fetch + encodeURIComponent
- 文件占用检测：`[IO.File]::Open(path,'Open','Read','None')` 独占打开试错法
- PowerShell 语法：`& "路径\程序" 参数` 是运行带引号路径程序的写法（cmd 里直接运行即可）；Python 命令一律用 Python312 全路径 `C:\Users\17838\AppData\Local\Programs\Python\Python312\python.exe`，不要裸写 `python`
- 关键决策（付费/凭据/不可逆/发布/安全）才问用户；普通工程决策自行做

## Q8 · 什么时候必须停下找人？

BLOCKED/HARD_BLOCKED；会话注册.json 缺失或 R-PROD 非 ACTIVE；要动冻结资产；要永久删除任何东西；要新建 ChatGPT 会话；超出任务范围的想法——记录为 KNOWN_GAP，不执行。

## Q9 · 弱 Worker 易踩坑不变量（摘自 LEGACY_INVARIANTS_RECONCILIATION.md，8/20 定稿）

1. **显式任务绑定**：一切动作绑定 task/run-id 与 Goal；不依赖 active_run、当前会话或模型自报身份。
2. **RUN_DONE ≠ PROJECT_DONE**：局部 DONE、产物存在、单次 PASS 都不构成项目完成。
3. **UNKNOWN 不重试、不 fallback**：外部效果未知时必须先 reconcile；「强 AI 能人工看浏览器」不代表弱 Worker 可以安全重发。
4. **附件不能静默降级**：attachment-required（--file）失败必须显式失败，禁止只发文本后宣称审查覆盖了附件。
5. **恢复预算耗尽即 HARD_BLOCKED**：停止并上报，禁止弱 Worker 自行研究替代 Bridge 路线。
6. **同一 session/输出目录禁止并发写**：并行任务的 working_directory 必须互不重叠，恢复（resume）同一资源前先确认无第二个写者。
7. **宿主与路径独立**：曾发生 PowerShell→Python→bash 的 PATH 漂移导致失效；用固定规范入口（run.cmd 已内置 doctor 检查），不要自行诊断 shim/daemon。
