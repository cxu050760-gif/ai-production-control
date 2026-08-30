# 03 · 能力资产注册表（CAPABILITY REGISTRY）

> 生成：2026-08-20 21:00（接管审计实测）· **本文件是最高优先级文件，任何 AI 接手必须先读。**
> 原则：每张卡给的是「可直接执行的调用方式」，不是源码位置。
> **三条通用规则**：①命令里 `<尖括号>` 是占位符，替换后才能执行，严禁原样带尖括号运行；②命令分「只读安全」与「真实动作」两级——真实动作（run.cmd work/report/send、chatgpt_bridge send/upload/open、启动并行 Worker）会真实操作生产 ChatGPT 会话或消耗真实算力，**没有真实任务禁止试跑**；只读安全（health/status/metrics、chatgpt_bridge status、ai-control.cmd doctor、wb_agg/wb_index）可随时用；③`& "路径"` 是 PowerShell 语法，cmd 里直接运行即可；Python 一律用全路径 `C:\Users\17838\AppData\Local\Programs\Python\Python312\python.exe`。
> 状态词：VERIFIED=有真实成功证据；PARTIAL=部分验证；UNKNOWN=未验证；BROKEN=有失败证据。

---

## 卡 B-1 · ChatGPT Bridge（ChatGPT 网页自动化执行链）

- **能解决什么问题**：让本地程序自动操作真实 ChatGPT 网页会话——发消息、收回复、传文件、复用会话。
- **用户目标**：把 ChatGPT 变成本地系统可调用的审查/规划引擎。
- **当前状态**：VERIFIED（核心冻结）。注意：52900 daemon 空闲约 5-6 分钟自动停止，属已知行为；执行生产命令时 wrapper 会自动拉起。
- **实际调用入口**：
  - 启动方式：任意 shell 直接调用全局命令（已入 PATH 的 ~/.local/bin）
  - 命令：`chatgpt_bridge`（bash 脚本，7,550B）；Windows cmd 可经 `C:\Users\17838\.local\bin\chatgpt_bridge.cmd`
  - 子命令：`status` / `open <url>` / `upload <files>` / `send <text>` / `receive [--out]` / `close`
  - 参数：见各子命令；多行文本建议写文件后经 send 传入
  - 环境要求：`BSK_HOME=E:/WB/tools/bsk-file-bridge/bsk-home`（脚本内已硬编码 dev 路径与 BSK_HOME，一般无需手设）；生产 Chrome 默认 profile 已装 dev 扩展（实例 7da8483f）
- **底层组件**（正常不需要直接碰）：
  - dev bsk.exe：`E:\WB\tools\bsk-file-bridge\repo\target\release\bsk.exe`（9.5MB，2026-08-18，端口 52900）
  - 消费端库：`E:\WB\workspace\2026-08-16-21-49-32\work\yz_lib.sh`（22,456B，含 8/18 三补丁）
  - 发送模块：`C:\Users\17838\.local\bin\bridge_send.py`（ProseMirror 兼容）
  - 接手速查：`E:\WB\tools\bsk-file-bridge\reports\ENTRY_README.md`；验证记录：reports\HANDOFF.md
- **调用示例**（⚠ 仅 `status` 是只读自检；`send`/`upload`/`open`/`close` 是对生产 ChatGPT 的真实操作，只有桥维护任务可执行，普通 AI 禁止"试一试"）：
  ```bash
  chatgpt_bridge status                        # 自检（链路/会话健康）
  chatgpt_bridge send "<要发送的文本>"          # ⚠真实动作：发往当前绑定会话（可能就是生产审查会话！无演练模式，仅桥维护）
  chatgpt_bridge receive --out <输出文件路径>   # 读回复（路径自己定，别用不存在的目录）
  chatgpt_bridge upload "<文件的绝对路径>"      # ⚠真实动作：上传文件（仅桥维护）
  ```
- **已验证证据**：文本收发、5 类文件上传×5 轮、会话复用、DONE marker、DONE_NO_MARKER 容错、尾部恢复、卡尾帧重 attach、IDLE gate、Runtime 生产 smoke R PASS→DONE（2026-08-16~18 全程记录于 reports\ 与 04_测试证据\）
- **禁止方式**：
  1. 生产 AI 日常**不要直接调桥**——走 Runtime 黑盒（卡 R-1），除非任务明确是桥维护
  2. 禁用 `chatgpt_bridge.ps1`（旧实现 BUG3 未修）、禁用旧 52800 bsk、禁用冷存档当现役
  3. 不要新建浏览器实例/新 profile；复用生产 Chrome 默认 profile
  4. 不要重写/重新设计桥；无新失败证据不改
  5. `yz_send_file` 类坐标 click 有被 overlay 截走的已知隐患（文本提交已改 JS click）
- **负责人角色**：桥维护员（仅故障时）；日常使用者=Runtime（自动代管）
- **已知边界**：download 方向（从 ChatGPT 下载文件）从未开发；CAPTURE 新鲜度校验为理论风险暂缓项；dev bsk 为 MinGW 构建（正式 MSVC 生产构建/发布流程未做，不影响当前使用）
- **实操坑（实测）**：①手动起 daemon 时 `bsk daemon start --port 52900` 后不得接 tail/head 管道（SIGPIPE 会致 WS 重置 os error 10054）；②`bsk-home\.bridge_state.json` 可能残留陈旧 session（如 zimc），open 前先 `chatgpt_bridge status` 自检，必要时 `close` 清状态；③桥硬规则文件在 `C:\Users\17838\.workbuddy\CORE_RULES.md` §10（强制走 chatgpt_bridge）

---

## 卡 R-1 · Runtime V1（生产审查运输 / 任务推进引擎）★ 普通 AI 的唯一 ChatGPT 通信入口

- **能解决什么问题**：给一个 GOAL，自动完成「开工→执行→交付 R 审查→REWORK 自动返工→PASS/DONE」，全程状态持久化、可恢复。
- **用户目标**：弱 AI 也能安全跑完需要强审查的真实任务。
- **当前状态**：VERIFIED（核心冻结）。43 个 RUN 记录；生产闭环已验证。
- **实际调用入口**：
  - 命令：`E:\WB\tools\ai-production-control\runtime\run.cmd`（下称 `run`）
  - 子命令（11 个，实测 runtime.py argparse）：**生产工作流**：`work`、`report`；**查看（只读安全）**：`status`、`health`、`metrics`；**底层/内部**：`start`、`step`、`directive`、`send`、`recv`、`done`（普通 Builder 禁止调用，由 Runtime 内部或特定受管流程使用）
  - 环境要求：规范 Python312（run.cmd 自动检查，缺失报 RUNTIME_ENV_BLOCKED exit 90）
  - 契约文档（必读）：`runtime\WEAK_WORKER_START_HERE.md`；恢复：`runtime\WEAK_WORKER_BOOTSTRAP.md`
  - RUN 状态：`E:\WB\state\ai-production-control\runtime-v1\runs\<RUN_ID>\state.json`
- **调用示例**（PowerShell）：
  ```powershell
  # 可选自检
  & "E:\WB\tools\ai-production-control\runtime\run.cmd" health
  # 开工（goal 为 UTF-8 文本文件；R-URL 从 会话注册.json 的 R-PROD.url 读取）
  & "E:\WB\tools\ai-production-control\runtime\run.cmd" work --goal-file "<goal.txt>" --r-url "<R-PROD.url>" --worker-id "<你的名字>"
  # 执行 GOAL，把结果写 result.txt 后交付裁决
  & "E:\WB\tools\ai-production-control\runtime\run.cmd" report --run-id "<run_id>" --message-file "<result.txt>"
  # 恢复/确认（换会话后第一件事）
  & "E:\WB\tools\ai-production-control\runtime\run.cmd" status --run-id "<run_id>"
  ```
- **裁决处理**：PASS→无需再动（自动 DONE）；REWORK→只做 R 要求部分，改完再次 `report`，直到 PASS；BLOCKED/HARD_BLOCKED→停止并上报 status 输出与 state 路径。
- **已验证证据**：RUN-20260818-173304-7350（REWORK×5→PASS→DONE 真实闭环）；08-19~08-20 多个 REAL GOAL PASS（见 01 时间线）；离线测试 55/55（test_runtime_offline.py，不碰真桥）
- **禁止方式**：
  1. 不要绕过 run 直接调 bsk/daemon/端口/yz_lib/session/marker/浏览器
  2. 不要自己猜 R_URL——只从 `E:\执衡\05_资源\会话注册.json` 读 R-PROD.url；缺失即停
  3. 不要用 RUN_DONE/REAL_GOAL_DONE 冒充 PROJECT_DONE
  4. 不修改 runtime.py（冻结资产）
- **负责人角色**：所有执行型 AI 的标准入口；主 Agent 负责给 GOAL 与恢复监督

---

## 卡 RV-1 · Reviewer 体系（ChatGPT 独立审查）

- **能解决什么问题**：所有关键交付由独立 ChatGPT 审查会话裁决（PASS/REWORK/BLOCKED），防止 AI 自审伪 PASS。
- **当前状态**：VERIFIED（生产 R-PROD 活跃；E-LAB 未指派）。
- **R 会话注册表（唯一权威）**：`E:\执衡\05_资源\会话注册.json`
  - R-PROD：`https://chatgpt.com/c/6a8597a2-4b2c-83ee-bf75-9523dfaf785a`（ACTIVE，2026-08-19 验证，RUN-20260819-212931-c1eb PASS）
  - E-LAB：UNASSIGNED（url=null）——实验会话未指派前，任何 transport 实验停止并报告，不要自建会话
  - 轮换政策：仅当出现真实污染/退化证据才轮换；轮换前向主 Agent 说明
- **裁决格式**：回复中的判定行 `===REVIEW_VERDICT=== PASS|REVISE/REWORK`（结构化 verdict）
- **调用方式**：Worker 不直接联系 R——由 Runtime `work/report` 代管运输（卡 R-1）。审查提交封套样例见 `04_测试证据\审计\*_to_reviewer.txt`、`接管定轨_20260820\R_review_request*.txt`
- **历史审查会话**（仅追溯用，勿当现役）：旧审查 6a81b611（已污染弃用）；接管定轨临时会话 6a86b0e1（独立审查）与 6a86d88d（临时累计审查 R）
- **禁止方式**：不得 self-review 冒充 PASS；不得把 E-LAB 用途混入生产；不得为形式新建会话
- **负责人角色**：主 Agent 维护注册表；Runtime 执行运输；ChatGPT R 只返回裁决，不改 canonical 事实

---

## 卡 P-1 · WorkBuddy Parallel（并行 Worker 体系）★ 重点能力

- **能解决什么问题**：把多个互相独立的子任务分给多个 AI Worker 同时干，每 Worker 独立会话/独立目录，主 Agent 边干主线边合并。
- **当前状态**：VERIFIED。19 条历史运行；已验证 2~10 路。
- **调用层（launcher）**：
  - 脚本：`C:\Users\17838\.workbuddy\skills\workbuddy-parallel\scripts\Invoke-WorkBuddyParallel.ps1`（2026-08-20 磁盘核对存在，43,729B）
  - Skill 定义：同目录上层 `SKILL.md`；纪律：`PARALLEL_RULES.md`
  - **启动方式：必须在 WorkBuddy 的原生 PowerShell 工具里执行**（从外部 Bash 起 powershell.exe 会被安全策略拦截）。**如果你不是 WorkBuddy 会话：你启动不了它，把并行需求交给主 Agent，不要反复尝试**
  - 参数（实测 param 块）：`-Mode Run|Resume`；`-TasksFile <绝对路径tasks.json>`；`-OutputRoot`（默认 `C:\Users\17838\.workbuddy\parallel-runs`）；`-MaxWorkers 1-10`（默认 5；≥8 需加 `-AllowLightweightBurst` 且 workload 仅 light）；`-TimeoutSeconds 5-86400`（默认 900）；`-Model`（默认 `deepseek-v4-flash`，可 `-Model hy3`）；续跑单 worker 用 `-SessionFile` + `-ResumePrompt`
- **任务输入格式**（UTF-8 JSON）：
  ```json
  {
    "common_context": "共享背景说明",
    "workload": "heavy|normal|light",
    "tasks": [
      {"id": "t1", "working_directory": "E:\\...（各 worker 必须互不重叠）",
       "task": "任务描述", "inputs": [], "acceptance": "验收标准",
       "tools": ["read","glob","grep","bash","write","edit","websearch","webfetch"]}
    ]
  }
  ```
- **结果输出格式**：launcher 打印 JSON receipt → 指向 `manifest_path`。每个 job 目录：`manifest.json`（status/并发统计/每 worker session_id/PID/exit_code/路径）、`RESULTS.md`、`workers/<task_id>/`（prompt.md、worker.json、session.json、result.txt、stdout.json、stderr.log）
- **调用示例**（WorkBuddy 原生 PS）：
  ```powershell
  $env:CODEBUDDY_CONFIG_DIR = 'C:\Users\17838\.workbuddy'
  & "C:\Users\17838\.workbuddy\skills\workbuddy-parallel\scripts\Invoke-WorkBuddyParallel.ps1" -Mode Run -TasksFile "E:\WB\tools\bsk-file-bridge\test\parallel_test.json" -OutputRoot "C:\Users\17838\.workbuddy\parallel-runs" -MaxWorkers 3 -TimeoutSeconds 900
  ```
- **结果汇聚（配套工具，R PASS 交付；Python 一律用全路径，不要裸写 python）**：
  ```powershell
  & "C:\Users\17838\AppData\Local\Programs\Python\Python312\python.exe" "E:\执衡\02_正在开发\wb_agg\wb_agg.py" <某job目录> [--out <dir>] [--tasks <tasks.json>] [--max-chars <N>]
  & "C:\Users\17838\AppData\Local\Programs\Python\Python312\python.exe" "E:\执衡\02_正在开发\wb_index\wb_index.py" <parallel-runs根> [--out <dir>] [--recursive]
  ```
  （wb_agg 出 summary.json+report.md；wb_index 出 index.json+index.md；分类规则 OK/TIMEOUT/FAILED/PARTIAL/MISSING）
- **已验证成功案例**：
  1. `job_20260816_212115_112_66ace1ec`：3 任务 3/3 succeeded，parallel_observed=true（输入 E:\WB\tools\bsk-file-bridge\test\parallel_test.json）
  2. `E:\执衡\04_测试证据\家底盘点\runs\job_20260819_192013_111_59e68b8f`：5 路并行产出 5 份盘点文档（tasks.json 在同目录）
  3. 2026-08-13《万界门》5 路 hy3 并行写作：交付 50 章 / 105,967 汉字，补 Bash 工具后 86 秒 2/2 确认真并行（`E:\WB\workspace\2026-08-13-14-54-50\hy3_parallel_novel_test_20260813\91_过程问题报告.md`）
- **实测坑（派活前必读）**：①任务 tools 缺 Bash 时 Worker CLI 会静默 exit 0 无产出——tools 列表务必含 bash；②前台+最大超时会自动转后台继续跑（TaskOutput），可跨 10 分钟单次上限（实测 34 分钟 5/5）
- **Worker 底层启动事实**（排障用，正常不碰）：每 worker 经 cmd.exe ShellExecute 启动 `node …\codebuddy -p --session-id wbp-… --model … --permission-mode bypassPermissions --tools …`（CreateProcess 直起会触发 CSPRNG 崩溃 exit 134，勿改）
- **禁止方式**：不要重写 launcher；不要 overlapping working_directory；不要超 10 路；不要在外部 Bash 里起 powershell 调它
- **HOST CALLABILITY（2026-08-20 磁盘+历史文档核对）**：
  - **WorkBuddy 内部调用**（WorkBuddy 会话 → 原生 PowerShell → `Invoke-WorkBuddyParallel.ps1`）：VERIFIED（SKILL.md 设计要求如此）。
  - **Codex 主 Agent 调用 WorkBuddy CLI**（node + `codebuddy` 脚本派 hy3/其他 Worker）：VERIFIED。历史证据 `E:\ChatGPT\00_HOME\WORKBUDDY_CLI_GUIDE.md` 记载 "Codex → 三个 WorkBuddy Worker" 实测 3/3 成功（session `WBMIX_worker_a/b/c_11033*`）。即 **Codex → WorkBuddy CLI → 启动 WorkBuddy Worker** 这条调用链成立；实测命令见该历史指南（本轮不复制进执衡）。
  - **Codex 主 Agent 调用 WorkBuddy Parallel 正式 launcher（`Invoke-WorkBuddyParallel.ps1`）**：UNKNOWN——无历史证据；该 launcher 设计要求 WorkBuddy 原生 PowerShell，外部 Bash→powershell.exe 被安全策略拦截，需实测才能升级。
  - **其他宿主**：UNKNOWN。
  - 历史备注：Codex 自身并行能力曾验证（多 Codex CLI Session / Subagent，见 `E:\ChatGPT\00_HOME\CODEX_PARALLEL_GUIDE.md`），但不属于当前执衡 WorkBuddy Parallel 标准入口，本轮不迁移。
- **负责人角色**：主 Agent（派活+合并）；Worker 只干分内任务

---

## 卡 W-1 · WorkBuddy 本机能力（宿主产品）

- **能解决什么问题**：本地 Agent 执行宿主——提供 Worker 运行、Skill 体系、MCP、文件/视觉能力。
- **当前状态**：VERIFIED（5.3.14 在装，25 天审计日志，380 次会话 traces）。
- **关键路径**：
  - 桌面程序：`C:\Program Files\WorkBuddy\WorkBuddy.exe`（5.3.14）
  - CLI：`C:\Program Files\WorkBuddy\resources\app.asar.unpacked\cli\bin\codebuddy`（runtime=codebuddy.js bundled）
  - 配置目录：`C:\Users\17838\.workbuddy\`（settings.json / audit-log\ / logs\ / traces\ / reviewer-registry.json / skills\）
  - **必须环境变量**：`$env:CODEBUDDY_CONFIG_DIR = 'C:\Users\17838\.workbuddy'`
- **已装 Skill（部分）**：workbuddy-parallel、browser-skill、desktop-skill、novel-crawler-workflow、openwrite-executor-models、westockdata、前端开发 等（ls `C:\Users\17838\.workbuddy\skills`）
- **视觉路由（实测规则）**：DeepSeek-V4-Flash 收到截图→自动派 vision-agent 子代理（hy3 读图）回传；hy3 直接处理多模态，不套娃
- **模型选择机制（实测）**：子任务 model:"default"/"inherit"→继承父模型；CLI `--model` 可单次覆盖；默认链 CODEBUDDY_MODEL>settings>账号首个未禁用模型
- **调用示例**：见卡 P-1（并行）；单 worker CLI 由 launcher 代管，不建议手起
- **Vision Agent**：`C:\Users\17838\.workbuddy\agents\vision-agent.md`（绑定 hy3，视觉事实初筛专用）
- **异构模型审计结论（2026-08-10 只读审计）**：手动切模型=可用；自动异构协作（frontmatter 写死视觉 sub-agent）=底层可用；专家团不同模型=不可用；auto 路由器=不可用
- **reviewer-registry.json**：云端审查会话记录（ChatGPT 总审查 001，last_verdict=PASS 2026-08-17，rotate_at=50）；旧审查会话因污染已于 8/19 切换（见会话注册 caveat）；存在记录≠云端算力已验证
- **顶层会话恢复闭环（8/18 实测）**：旧会话半途→新顶层 WorkBuddy 会话接手→经 chatgpt_bridge 回同一 R→接收裁决继续（`E:\WB\workspace\2026-08-18-14-07-08\recovery_test_log.md` 测试三）
- **禁止方式**：不要改 C:\Program Files\WorkBuddy 内文件；不要绕过 CODEBUDDY_CONFIG_DIR
- **负责人角色**：并行 Worker 宿主；日常由 WorkBuddy 会话自管

---

## 卡 D-1 · DesktopSkill（Windows 桌面执行层）

- **能解决什么问题**：操作 Windows 本地 GUI 软件——启动/枚举窗口、读 UIA 控件树、点击/输入/读回、窗口截图。定位是「手」：只执行，不推理不决策。
- **当前状态**：PARTIAL（脚本就位；端到端桌面自动化未重测，见 07 缺口 G-7）
- **实际调用入口**：
  - Skill：`C:\Users\17838\.workbuddy\skills\desktop-skill\`（SKILL.md + scripts\desktop.py，UIA/Win32）
  - 启动方式：由 WorkBuddy 主模型按 SKILL.md 规则调用（非手敲首选）
  - 环境要求：Windows UIA 可用；仅用于非敏感操作
- **调用优先级（SKILL.md 铁律，禁止反过来）**：Level 1 原生 CLI/API/文件操作 → 不可行才 Level 2 DesktopSkill（UIA/Win32）→ 仅自绘控件等 UIA 覆盖不到时 Level 3 截图+视觉+坐标 click_at
- **已验证证据**：历史脚本与视觉测试脚本就位（2026-08-19 盘点记录）；本轮未重测 E2E
- **禁止方式**：有 CLI/API 可达时不得用桌面自动化绕路；敏感操作禁用
- **负责人角色**：WorkBuddy 主模型按需调用

---

## 卡 C-1 · Continuation / Trae-Ralph（自动续跑工具）

- **它是什么**：**第三方工具接入，不是产品能力，更不是最终自主系统**。作用：TRAE SOLO CN 会话停止时，经 CDP 自动点「继续」，实现无人值守续跑。
- **当前状态**：VERIFIED。`CODE_FIX=PASS`、`R_PROD=PASS`、`DEPLOYED=TRUE`、`INJECTED=TRUE`、`REAL_SMOKE=PASS`；conversation/session 强绑定、A→B fail closed、A→B→A 保持 blocked、300ms race fail closed、UI 显式恢复、SPA UI 重挂载、UI/watchdog/binding 状态统一。既有审查 RUN-20260820-195652-1051 REWORK×3→PASS；真实部署发现的隐藏缓存根 adapter 修复经 RUN-20260820-224610-8ba3 首轮 PASS。`CURRENTLY_RUNNING=FALSE`（测试 watchdog 已安全停止；TRAE/CDP 9223 与注入控件仍在，后续只在目标会话通过 UI 显式开启）。
- **工具位置**：`E:\WB\tools\Trae-Ralph`（git clone 隔离安装；冻结兼容 commit `2711c89`；conversation isolation 基线 `1fcdda7b…`；当前最终 HEAD `9a82a00bb858b880274105afdd18c699b472706d`，WORKTREE=CLEAN；上游 cda24c3；最终证据见 `接管定轨_20260820\Trae-Ralph_conversation_isolation_closeout_20260820.md`）
- **配置文件**：`C:\Users\17838\.trae-ralph\config.json`（trae.china.path / port=9223 / defaultVersion=china；注意必须无 UTF-8 BOM）
- **已验证的启用流程**（最终实证见 Trae-Ralph_conversation_isolation_closeout_20260820.md）：
  1. 磁盘持久化确认（git 已提交）+ 落盘随机续跑标记
  2. 由 TRAE 外部 supervisor 使用 cmd `start "" "E:\traework\TRAE SOLO CN\TRAE SOLO CN.exe" --remote-debugging-port=9223 --user-data-dir="C:\Users\17838\AppData\Roaming\TRAE SOLO CN" "E:\执衡"`（**不加** `--disable-restore-windows`，不开新 profile，workspace 最后；PowerShell 调 cmd 时整条 start 语句必须作为一个 `/c` 参数）
  3. 恢复门禁：界面仍是原会话 + 能复述标记 + git head 一致，三者全过才继续
  4. `cd E:\WB\tools\Trae-Ralph && npm run inject:cn`（= node src/injector.js --version china）
  5. `开启 Ralph` 会捕获当前 conversation identity；切换其他会话立即 fail closed，返回原会话仍保持 blocked，只有控件显示 `确认恢复 Ralph` 后由用户显式点击才恢复；后台状态与按钮必须一致
- **禁止方式**：禁用 `start:cn`（开空白新窗）；禁 setup-trae / rules:inject / Ralph rules / skills / RALPH_STATE；恢复门禁不过→立即停止不注入；补丁只允许改 Trae-Ralph 目录内副本
- **负责人角色**：会话守护者（主 Agent 决定何时启用）；不是决策者

---

## 卡 CT-1 · Controller（ai-production-control 产品本体，建设中）

- **能解决什么问题**：最终产品形态——用户只给一个真实 Goal，Controller 统一负责规划/状态/授权/Evidence/审查/交付，Brain/Worker/Reviewer/Provider 全可换。
- **当前状态**：**PARTIAL（PRODUCT_NOT_READY，诚实门禁，不得伪装完成）**。M0.5~M3 本地测试 75/75；TCB=UNVERIFIED_AFTER_CONTROLLER_CHANGE。
- **入口**：`E:\WB\tools\ai-production-control\ai-control.cmd run "<goal>"`（当前只返回安全骨架探针/PRODUCT_NOT_READY——这是诚实门禁的**正确行为**，不是 bug。收到 PRODUCT_NOT_READY 或非零退出码：如实上报即可，**不要当成故障去修、不要试图绕过**）
- **关键路径**：源码 `src\aicontrol\`；canonical DB `E:\WB\state\ai-production-control\control.db`（SQLite）；占位 Worker `scripts\local_worker.py`；真实 worker fixture `scripts\fixture_worker.py`；体检 `ai-control.cmd doctor`
- **里程碑事实**（git 实证）：M0.5=63217a8（独立复审 PASS）；M1=b8d0994 Adapter 契约（WAITING_REVIEW）；M2=7e553bf/773ceeb/54097d7/546eacc；M3=048301b/c0981f6/5e71b4b/efd1743/076ae54/33b92e8
- **调用示例**：`ai-control.cmd doctor`（体检）；单元测试见 tests\（75/75 回归）
- **禁止方式**：不得据局部测试宣布 Stable Candidate/FINAL_PRODUCT_ACCEPTED；不得让 Worker claim 直接晋级 canonical 完成；Runtime V1 是冻结资产，将来经 M1 Adapter 接入，不改成第二控制面
- **负责人角色**：主 Builder（当前 DeepSeek-V4-Flash 持续施工）；强 AI 只做架构决策与独立审查

---

## 卡 X-1 · 外部参考项目（全部未接入，复用决策是红线）

- **能解决什么问题**：为将来「解除 ChatGPT Provider 硬绑定」提供候选判断。**全部停留在候选阶段，没有一个接入生产链。**
- **决策全文**：`E:\执衡\03_参考项目\复用判断.md`（2026-08-19 DeepSeek 源码级审计 + ChatGPT R 复核）

| 项目 | 许可证 | 决策 | 当前状态 |
|---|---|---|---|
| WebModel | MIT | 优先候选（Provider 层） | 已隔离 clone 至 `03_参考项目\upstream\WebModel`；最小验证实测：npm install + doctor + launch OK，`/webmodel/providers` 返回 11 家 provider（全部 authenticated:false）；任一 Provider 真实推理需先在其独立 Chrome 登录；证据 `04_测试证据\webmodel_lab\` |
| 10x-chat | MIT | REUSE 接口形状（Provider 五动作+registry）/ ADAPT 传输 | 未 clone（网络重置），raw 抓取于 `upstream\dl\10x_*` |
| ChatGPT-Web2API | MIT | 仅参考；韧性设施（限速重试/熔断/完成检测/诊断）值得 ADAPT | raw 源码于 `upstream\dl\` |
| Joshua Agent | MIT | 编排设计/代码复用候选 | 已 clone 至 `upstream\joshua-agent`；ADAPT 目标 `store.py`（fenced lease/retry/recover_stale）与 `watcher.py`（熔断） |
| Proxima | 自定义非商用许可 | **仅设计参考，禁止复制代码** | 合规红线，不得并入产品；商用须合规审查 |

- **禁止方式**：不得把任何项目说成「已接入」；不得复制 Proxima 代码；复用 MIT 代码须保留版权声明
- **负责人角色**：主 Agent 决定何时启用；启用前必须最小验证并经用户批准

---

## 卡 M-1 · 模型路由（谁干什么）

| 模型/角色 | 适合 | 限制 | 状态 |
|---|---|---|---|
| DeepSeek-V4-Flash | 施工/主 Builder：常规实现、测试、机械任务、审计 | 不做架构决策；读图需经 vision-agent | VERIFIED（现役主 Builder） |
| hy3 | 通用 Worker：读文件/搜索/整理/独立取证/测试/机械任务；视觉直接处理 | 不承担决策 | VERIFIED |
| ChatGPT（经桥） | 主规划 / 总审查 R / 最终路线判断 | 经 Runtime 运输，不直连 | VERIFIED |
| Codex CLI 0.145.0 | 稀缺强力专家：疑难 bug、高难重构、独立专家审查 | 贵，省着用；`codex exec`（C:\Users\17838\AppData\Roaming\npm\codex.cmd） | VERIFIED |
| vision-agent | 视觉事实初筛（DeepSeek 会话的截图代理） | 只初筛不决策 | VERIFIED |
| TRAE Work + Seed-Code | 近期主开发 IDE 环境（接管定轨施工宿主） | IDE/会话级环境，不是可派发 Worker；配置 `C:\Users\17838\.trae-cn` | VERIFIED |
| 豆包 Cloud / CNB | 补充资源 | 当前可用状态待验证；配置目录 .doubao / .cnb 存在 | UNKNOWN |
| Qoder / 千问办公 | 补充资源 | 本机路径未取证 | UNKNOWN |

---

## 卡 A-1 · 审计链（三层独立，勿混淆）

| 层 | 工具/位置 | 证明什么 | 怎么调用 |
|---|---|---|---|
| ①方法/现场硬门 | `04_测试证据\审计\self_verify.py` | closure/gitlink/audit 前缀等现场自检 | `& "C:\Users\17838\AppData\Local\Programs\Python\Python312\python.exe" "E:\执衡\04_测试证据\审计\self_verify.py"` → 应输出 VERIFIED |
| ②字节封包（历史快照） | `04_测试证据\审计\manifest.json` | 2026-08-20 12:11 审计 PASS 时的核心文件 size+sha256 绑定（HEAD 34d98b0） | 只读核对；**当前 builder_state 哈希≠manifest 是预期差异**（12:19 有意变更） |
| ③外部独立审查 | ChatGPT R | AUDIT_CHAIN_FINAL_CLOSURE=R_REVIEW_PASS | 证据=RUN-20260820-114102-1e14 最后 reply（首行 PASS） |

**重要**：跑 self_verify 得 VERIFIED ≠ 重新证明外部 R PASS。三层独立取证。
