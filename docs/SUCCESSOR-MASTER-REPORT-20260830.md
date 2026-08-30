# 执衡接手者主报告（SUCCESSOR MASTER REPORT）

- 生成：2026-08-30 22:40（北京）· 生成者：接手控制会话
- 读者：**任何一个零上下文的新 AI 会话**（弱模型如混元3/豆包级即可）
- 性质：这是你接手执衡项目的**唯一入口文档**。读完本报告 + §15 的启动指令，你就有能力正确处理相关问题。
- 铁律：**本报告是快照。状态冲突时一律以 GitHub 远端（origin/master）+ 磁盘实测为准，不信任何会话记忆（包括本报告）。本报告每条事实均附验证方式（路径/命令/哈希），你可复核。**
- 修订机制：修改本报告必须在文末「修订记录」追加一行（时间+改动+原因）；状态快照更新属常规维护，判定变更属重大修订需留证据。

---

## 0. 90 秒版（先读这个）

**执衡是什么**：一个本地优先、目标驱动、成本感知、AI 可替换的个人 AI 自动生产系统。核心思想：弱 AI 便宜适合干活但会犯错，强 AI 贵适合审查判断——用外部控制层（状态权威、独立审查、纠偏、恢复、闸门）把一群不可靠的 AI 组织成可靠生产系统。**用户给目标，执衡负责真正做完。**

**当前在哪**：V1.0 **工程收口已完成**（封印 gen1 + §74 签字 + master 汇合 + doctor DRIFT_FREE，2026-08-30）。但这是"工程判据"收口，**不是产品完成**——77 节定义独立重判 = **40 ✅ / 30 🟡 / 7 ❌**。最大缺口：全自动体验（§3）、机器可读能力注册表（§63）、成本路由（§59）、自举（§68）等 7 节未满足。

**当前运行模式**：本地弱 AI（如 DeepSeek V4 flash）手动敲 `run.cmd work/report` + 网页强 AI（ChatGPT R-PROD 会话）独立审查。**全程人肉驱动**——这是当前最大痛点。⚠ 注意：一键黑箱是方案 R3 之后的产物，**当前接手仍需按 §5 的命令行方式操作**。

**你的任务**：按 §13 执行方案 v2，把 7 个 ❌ 和 30 个 🟡 补齐，把系统收束成"弱模型拿一页卡就能用"的傻瓜黑箱。

**你的第一步**：见 §15 启动指令。

---

## 1. 必读权威文件（按序，全部在仓）

| 序 | 文件 | 作用 |
|---|---|---|
| 1 | 本报告 | 唯一入口 |
| 2 | `docs/canon/ZHIHENG_FINAL_DEFINITION_FINAL_CANONICAL.md` | **宪法**（77 节，SHA256 `4c05a21f…9a4a`，零修改） |
| 3 | `PROJECT_STATE.md` + `PROJECT_STATE.json` | 当前状态真源（doctor DRIFT_FREE 校验） |
| 4 | `docs/governance/ZHIHENG_FULL_DELEGATION_CHARTER.md` | 施工纪律章程 v4.4（双哈希口径见 governance/README） |
| 5 | `docs/governance/GLOSSARY.md` | **计数口径唯一权威**（真实 GOAL=累计 8（3+5）；REWORK 轮次=reply 中判定计数） |
| 6 | `docs/evidence/DEFINITION-77-SECTIONS-FINAL.md` | 77 节矩阵（⚠ 本报告 §5 的独立重判更新它） |
| 7 | `docs/evidence/SUCCESSOR-TRUTH-AND-20-SELF-ATTACKS.md` | 前任 20 次自我攻击（防误导） |
| 8 | `docs/NEW_SESSION_KICKOFF.md` | 历史版接手指令（部分过时，以本报告为准） |
| 9 | `docs/evidence/audit/AUDIT_REPORT_2026-08-30.md` | 第二团审计（16 项 15 PASS/1 REWORK） |
| 10 | `E:\执衡\00_先看这里\能力操作手册_20260820\03_CAPABILITY_REGISTRY.md` | 桥/工具操作卡（⚠ 部分内容以仓库 docs/ops/ 为准） |
| 11 | `docs/FAILED_APPROACH_LEDGER.md` | 已失败路线账本（防止重新发明失败过的方案） |

**文档新旧关系**：本报告 > 2026-08-30 文件 > 2026-08-29 文件 > 8-28 及更早（8-20 手册中桥操作仍有效，状态类描述已过时）。冲突时取最新+远端。

## 2. 关键路径地图（全部实测存在）

| 资产 | 路径 | 说明 |
|---|---|---|
| 施工 worktree（当前主工作区） | `C:\Users\17838\Documents\Qoder\2026-08-28\031cb4e3\b1` | 分支 master（0979c69）；git 操作需代理 `http://127.0.0.1:7897` |
| GitHub 远端 | `github.com/cxu050760-gif/ai-production-control`（私有） | **进度唯一真源**；tag `v1.0-engineering-close`=793fa41 |
| 生产 Runtime V1（黑盒入口） | `E:\WB\tools\ai-production-control\runtime\run.cmd` | work/status/report/health/router 命令；**冻结核心勿改** |
| 施工线 runtime 模块 | worktree `runtime/`（brain_bridge/capsule_bridge/effect_safety_lite/ec_lite/strategic_*） | 112+ 测试 |
| 控制层核心 | worktree `src/aicontrol/`（controller/store/security/lineage…） | Controller TCB，已封印（gen1） |
| 运行状态基座 | `E:\WB\state\ai-production-control\` | control.db、runtime-v1\runs（110+ RUN）、construction-relay、browser-auth-profile |
| 中继（construction-relay） | `E:\WB\state\...\construction-relay\` + 代码 `E:\WB\tools\Trae-Ralph\` | **当前停摆**（心跳停 8-30 01:42）；Trae-Ralph 上游归档禁 push，修复只在本地 git |
| 桥 | `C:\Users\17838\.local\bin\chatgpt_bridge(.cmd)` + `E:\WB\tools\bsk-file-bridge\`（bsk.exe，端口 52900） | **当前停**；ChatGPT 网页通道；download 方向未开发 |
| catpaw 反代 | `E:\WB\tools\catpaw-longcat-proxy\`（端口 32177） | 网页 AI 备用通道；**当前停** |
| 会话注册表 | `E:\执衡\05_资源\会话注册.json` | R-PROD 会话 URL 唯一来源（**凭据文件：只读 URL 字段，不外传**） |
| 资产根 | `E:\执衡\`（手册/证据）、`E:\WB\outputs\ai-production-control\` | 测试证据 1022 文件已备份至 `E:\WB\backups\ai-production-control-P0_BACKUP-20260830-1700\` |
| 收口专用库 | `E:\WB\state\ai-production-control\v1-close\` | 封印用隔离库（gen 1，manifest `2dff958d…`） |
| 冻结定义 | `D:\下载\chatgpt原始会话内容\执衡_最终定义_FINAL_CANONICAL.md` | 宪法原始副本 |

**分支现状**：`master`=当前主线（全部工作在此）；`v0.9-b1/authority-effect-core`=ARCHIVE（已合入 master，勿再开发）；`v0.9-b2/authority-effect-evidence`=历史线（8-28 旧开发线，勿动）；`spec/*`=历史变体（勿动）。**一切新工作在 master 或从 master 切出的新分支**（新分支需业主/主脑裁决后创建）。

## 3. 状态快照（2026-08-30 22:30 实测）

- git：master=`e52945c`（本报告提交；快照 22:30 时为 0979c69），本地=远端，工作树干净
- 测试：runtime 6 模块 113 tests OK + tests 13 OK；矩阵 36/36（`test_v09_attack_matrix_on_b1_core.py`，**用这个**，不是 `_offline.py`）
- 中继：**停**（最后心跳 8-30 01:42；历史 32 次启动、29 个崩溃锁——根因=进程生命周期绑 AI 会话，非 bug）
- 桥/catpaw：**停**（52900/32177 无监听）
- doctor：⚠ 本报告提交（non-governance）曾致 DRIFT——修复见修订记录 22:58：dev head 已同步至最新治理提交，复验 DRIFT_FREE
- 封印：gen 1 VERIFIED（收口专用库，在产库未触碰）
- release_status：`READY_FOR_USER_ACCEPTANCE`（边界：北极星自动调度闭环未达成，"可自动生产"宣称不成立）

## 4. 77 节定义对照（独立重判 2026-08-30，比旧矩阵 v3 更严——以此为准）

**✅ 40 节**（略——明细见 `docs/evidence/DEFINITION-77-SECTIONS-FINAL.md` v3 的 ✅ 集合，本重判与其差异：§62 升 ✅）：
§0,1,6,9,10,12,13,15,21,22,24,25,26,27,28,29,31,32,33,35,36,37,39,42,43,44,45,46,47,52,53,54,62,64,66,67,69,72,75,76

**🟡 30 节**（机制在、缺闭环/实测——按修复依赖排序）：

| 节 | 缺什么 | 归属阶段 |
|---|---|---|
| §14 Lifecycle | 非 AI 独立守护缺失（guard 绑 AI 会话） | R1 |
| §20 浏览器面 | download ❌；通用网页操作（非 ChatGPT 站）未开发 | R2/D3 |
| §65 唯一入口 | 四动词不齐（无 RESULT/HUMAN_GATE 响应） | R3 |
| §48/49/50 Reuse 门禁 | 流程走过但无系统级强制 | D3 |
| §5 Provider 独立 | Worker 有 Adapter；**R/Brain 无**（R 硬绑 ChatGPT） | D1 |
| §61 Hard Fuse | 计数器在；SAFE_HALT 从未真实触发 | D2 |
| §56 多 Worker | skill 在；真实并行 0 次 | D4 |
| §57 Resource Lock | 锁在；多 Worker 冲突未实测 | D4 |
| §16 WAIT 局部性 | 等待时跑其他任务未验证 | D4 |
| §34 Split Brain | 双 Controller 竞争未实测 | D4 |
| §23/§41 | directive 在；STOP→旧权失效端到端未测 | D4 |
| §40 Revocation 单调性 | epoch 在；回滚复活专项测试未确认 | D4 |
| §30 Stale Safety | 通用 stale 检测部分 | D4 |
| §38 OUTCOME_UNKNOWN | 机制+单测；真实对账场景未发生 | D4 |
| §17 Task Graph | 线性列表；依赖/并行标记/Owner/动态加任务未实现 | D5 |
| §7 Brain | 契约级规则拆解；选 Worker/工具/重规划未实现 | D5 |
| §8 C 纠偏 | 契约+15 次；独立 C 常态化未建 | D5 |
| §11 EC | 机制在；真实触发案例少 | D5 |
| §18 双视图 | Human View 无正式查看命令 | R3 |
| §19 NO_PROGRESS | 计数器在，未真实触发 | D2 |
| §2 成本感知 | 无 Expected Total Cost 核算 | D2 |
| §4 生产系统 | 真实用户级交付 Acceptance 链未走 | D6 |
| §60 升级梯 | 9 级阶梯未系统化 | D5 |
| §70 Trace | 缺"哪个 AI/Tool/为何 Retry/成本"字段 | D5 |
| §71 简洁 UI | 无用户视图命令 | R3 |
| §73 可靠性原则 | 15 行中 3 行缺（Supply Chain/成本调度/Lifecycle 守护） | 跟随各包 |

**❌ 7 节**：
§3 全自动 31 步体验（灵魂条款）· §51 Supply Chain Gate · §55 Context Sufficiency · §58 Project Isolation · §59 Cost Routing · §63 Capability Registry · §68 自举

> 与旧矩阵 v3（41/35/1）的差异说明：本重判更严——§62 升 ✅（fail-closed 有矩阵 R31-R34 实测证据）；§51/§55/§58/§59/§63 从 🟡 降 ❌（"机制在"不等于"有实现"，逐节核对后确认无系统实现）；§74 保持 🟡（工程收口已签，FINAL DONE 待终裁）。**本重判为准**，D6 矩阵 v4 需独立复核。

## 5. 已验证能力（你能直接用的）

1. **Runtime 黑盒闭环**（实测 8 GOAL）：`run.cmd work --goal-file <文件> --r-url <R-PROD>` → 弱 AI 执行 → `run.cmd report --run-id <ID> --message-file <结果>` → 强 AI 审查 PASS/REWORK → PASS 为止。REWORK 循环自动可重交（实测 16 轮判定）
2. **Brain 拆解**：`python runtime/brain_bridge.py --goal-file <文件>` → proposal + Task Graph + human_view（规则式，简单目标可用）
3. **Capsule 续跑**：`python runtime/capsule_bridge.py --run-id <ID> [--verify]` → 机械投影续跑指引
4. **状态恢复**：candidate_r14 runtime 的 `state-verify/state-recover`（沙箱演练 FULL）；生产 runtime 简化版无此命令
5. **体检**：`python scripts/state_doctor.py`（DRIFT_FREE=健康）；矩阵 `python runtime/test_v09_attack_matrix_on_b1_core.py`（36/36）
6. **中继**（若已由守护拉起）：inbox 投任务 → 自动流转（wake/review/verdict）；历史 32 次启动证明可用但不稳定
7. **R-PROD 审查质量**：实测不放水（4/7 轮真实 REWORK）

## 6. 用户真实需求翻译（你做任何决策的对准点）

1. **傻瓜黑箱**：弱模型（混元3/豆包级，能执行命令行）拿一页操作卡，只给目标文本，就能走通全链到 PASS
2. **弱+强组合，性价比**：弱模型执行、强模型只做高价值判断（审查/规划）——成本路由是机制目标
3. **都不可靠、随时换、不中断**：AI 是资源（§5），换模型/换会话/换 Provider 项目不死
4. **拿来主义是硬门禁**（§48）：先搜 GitHub（Reuse>Adapt>Compose>Build），Decision 留痕，禁止重复造轮子
5. **77 节定义一条不能漏**（用户原话）——最终验收 = 矩阵 v4 77/77 + 业主终裁
6. **用户偏好**：少废话给结论；优先复用禁止重复开发；不擅自扩大范围；改完必须实际验证；不猜测用户心理；高风险操作先确认

## 7. GitHub 复用映射（已调研，接入即可）

| 缺口 | 方案 | 拿法 |
|---|---|---|
| §59 成本路由 + §5 R-Adapter | **LiteLLM**（57K★ MIT Python） | 直接复用：100+ Provider 统一接口、cost 追踪、fallback、健康检查 |
| §51 Supply Chain | pip-audit / osv-scanner | 直接复用 + 检查清单脚本 |
| §20 通用网页（含 download） | **Playwright**（微软官方） | 与 bsk 互补：登录态敏感站走 bsk，通用网页/下载走 Playwright |
| §71 UI（可选） | 轻量 CLI 视图优先 | 后置 |
| §14 守护 / §68 自举 / §3 调度 | **无现成方案** | Build（Control Plane 灵魂，不自外） |

**禁止拿来替换的**：Control Plane 核心（状态权威/审查分权/Effect 闸门）——已建成已验证，外部框架（n8n/Dify 类）替换=违反 §50。

## 8. 执行方案 v2（九阶段，每阶段可独立验收/中断/回退）

| 阶段 | 内容 | 对应节 | 验收 |
|---|---|---|---|
| **R1 守护层** | Windows 计划任务 guard-all（每 2min：心跳超时→重启中继；52900 检查→拉桥；Chrome 连接检查；state 完整性；全部记账本）。纯确定性、非 AI、开机自启 | §14/§61 | 心跳连续 72h；自愈动作入账本 |
| **R2 注册表+资产接入** | §63 机器可读 capability registry（JSON：Brain/Worker/C/R/Browser/Tool/Provider×Cost/Quota/Reliability/Official|Experimental）+ catpaw/bsk 由 registry 驱动拉起 | §63/§20/§21 | registry 被运行时消费；桥自动拉起 |
| **R3 黑箱 v1** | run.cmd 四动词补齐（补 RESULT/HUMAN_GATE）+ 一页操作卡（3-5 步） | §65/§71 | **新弱模型会话按卡操作走通，R-PROD 独立判 PASS（不自判）** |
| **D1 R-Adapter（最优先）** | LiteLLM 接入：R 可插拔 MVP（先 1 个 API 类强模型）+ 健康探测+热切换 + 多 R 仲裁规则。⚠ LiteLLM 与本系统兼容性未实测，**先做 1 天 POC**（一个 R 调用走通 LiteLLM→任意 Provider）再全量接入 | §5/§12/§73 | POC 通过后：拔 ChatGPT 换 Provider，任务照常 PASS |
| **D2 成本路由+熔断** | Expected Total Cost 路由 v1（registry Cost 字段驱动）；SAFE_HALT 真实触发 1 次 | §59/§61/§2/§19 | 路由可解释；熔断证据入仓 |
| **D3 Reuse 门禁+Supply Chain** | 任务开工强制 Reuse Decision 工具化；pip-audit/检查清单接入；download 补齐评估 | §48-51/§20 | 无 Decision 不得 BUILD（系统强制） |
| **D4 并行+隔离+失效权** | 多 Worker 真实并行 1 次（带锁）；第二项目隔离验证；STOP→旧权失效端到端 | §56/§57/§58/§16/§23/§41 | 并行无冲突；A/B 项目互不污染 |
| **D5 自举+智能** | 自举 L1：Stable 执衡自动修复自身一个真实缺陷走完 §74 十二条；Task Graph 依赖图；Brain 选型 | §68/§17/§7/§8/§11/§60/§70 | 全链证据入仓 |
| **D6 终验** | 矩阵 v4 全量复核（77/77）+ **业主给一个真实目标走 §3 全自动** + 提请终裁 | §3/§4/§74 | FINAL DONE 候选 |

> 耗时纪律：**不做预先天数承诺**（前任多次估错）。每阶段完成后在修订记录报**实际耗时**，供后续阶段估算。弱模型实测每次消耗真实任务+R 审查额度，控制迭代轮数。

并行纪律：R1（系统脚本）与 R2（registry+接入）与 R3（入口+卡）可三路并行；**D 阶段串行为主**（依赖 R 完成+彼此有依赖）。并行写文件按 §57 分工：**R1 只写 `scripts/guard/` + 计划任务；R2 只写 `config/capability-registry.json` + `docs/ops/registry-*`；R3 只写 `runtime/` 新命令文件 + `docs/ops/blackbox-card*`**——`docs/DECISION_LEDGER.md`/`PROJECT_STATE.*`/本报告由主会话统一写，避免冲突。

## 9. 环境坑清单（实测踩过，新 AI 必读）

1. **MSYS 路径转换**：Git Bash 里 URL 参数含 `/c/` 会被转成盘符 → 命令前加 `MSYS_NO_PATHCONV=1`
2. **Git Bash /tmp 对 Windows Python 不可见** → 临时文件用真实 Windows 路径（如 `E:\WB\outputs\...`）
3. **环境变量 `ACC_PRODUCT_CONFIG_V3` 长达 515KB**，超 Windows 32767 上限 → 个别测试（harness_verify 类）需进程内删除该变量再跑
4. **bsk daemon 不得接 tail/head 管道**（SIGPIPE 致 WS 重置 os error 10054）
5. **`.gitignore` 陷阱**：`*credential*` 规则会拦凭据字样文件名（轮换清单改名规避）；`config/tcb-manifest.json` 被显式忽略（封印 manifest 入仓需 `-f`，原因已记 D021）
6. **矩阵测试有两个**：权威 = `test_v09_attack_matrix_on_b1_core.py`；`_offline.py` 是 T0 既有实验文件，当前环境失败（预置授权缺失），**勿误跑误判**
7. **中继起进程**：`bsk daemon start` 后台跑时不得接管道；watcher/guard 用 run_in_background 且**会随 AI 会话死**——根治靠 R1 计划任务
8. **凭据纪律**：会话注册.json/proxy-key.dpapi/browser-profile 只登记路径或读必要字段（R_URL），内容不外传不入仓不复制（P0 备份到本地盘除外——那是磁盘备份非入仓）
9. **doctor 的 GOVERNANCE_PATHS 白名单**只有 6 个文件——master 上新提交若含其他路径会被判 dev-head drift；文档提交后需同步更新 `PROJECT_STATE.json` 的 dev head 或走 b1 分支
10. **git 全程代理**：`git -c http.proxy=http://127.0.0.1:7897 -c https.proxy=... `；**禁 force**
11. **持续补充机制**：你踩到本清单之外的新坑，必须追加到本节（带日期），这是集体记忆
12. **兜底**：遇到本清单之外的报错 → 先 `python scripts/state_doctor.py` + 查 §1 文档清单 → 仍无法解决 → 写升级块停下，**不猜着干**

## 10. 中继病历（收口 R1 的输入）

- RELAY_STARTED 32 次（按精确 type 计；QA 全文计数 35，差异疑含跨文件重复，口径待查）；8-25 单日 15 个崩溃锁、8-26 单日 14 个；WATCHDOG 自救 14 次
- 应用层修复已完成（Trae-Ralph git 历史 15+ 条 fix：TRAE 风控中断/watcher 中断/verdict 恢复/幂等授权/Windows 路径…）
- **结构性根因（推断，待 R1 验证）**：进程以 AI 会话后台进程方式运行，会话结束/睡眠=被杀；无 OS 级守护
- 修复方向：R1 计划任务守护（心跳超时检测→杀树→重启→记账），非修 bug

## 11. 历史决策索引（D001-D021，详见 `docs/DECISION_LEDGER.md`）

关键不可重开裁决：V14 锚定 / R18 解读 B / D 类锁定 / Phase 0 / 42 分支分类 / E1-E4 批（封印后置→已执行） / 口径批（真实 GOAL=累计 8） / 签署包（封印+签字+汇合）。**禁止重开任何冻结裁决**（章程 §7.1）。

## 12. 红线速查（违反=立即停止升级）

宪法零修改；不重开冻结裁决；**未经业主/主脑裁决不得执行任何 merge**（master 汇合已由签署包合法完成，后续 merge 须新工单）；禁 force；大文件/二进制不入 git；无关项目零触碰；生产在用设施零改动；期望与断言不削弱；不改 state_doctor 逻辑；PROJECT_STATE 语义字段仅按出口更新；凭据不入仓；未满足 §74+审查+业主裁决不得自称 FINAL DONE；上下文将尽先落检查点；当前施工与推送分支=master（签署包后主线），新分支创建须裁决。

## 13. 灾备路径

- 状态坏：candidate_r14 `state-recover`（沙箱先演练过的机制）
- 仓库坏：远端为真源，重新 clone + 代理
- 证据丢：P0 备份 `E:\WB\backups\ai-production-control-P0_BACKUP-20260830-1700\`（260MB 全校验）
- R 会话死：临时用会话注册.json 里其他会话或升级业主（R-Adapter 完成前这是单点）
- 全环境坏：按 §2 路径地图逐个拉起（start 顺序：catpaw→bsk daemon→Chrome→中继→验证 doctor）

## 14. 已知未验证/存疑（诚实清单）

- R-PROD 会话健康（8-30 之后未使用，登录态可能过期）——用前先 `chatgpt_bridge status`
- LiteLLM 与本系统兼容性（未实测，方案假设）
- 中继根因"生命周期绑会话"是推断，R1 落地时验证
- 本报告 77 节重判为单人判定，D6 矩阵 v4 需独立复核
- `E:\执衡\04_测试证据` 等资产已备份但未融入系统（§63 注册表 R2 落地时收编）

## 15. 新 AI 启动指令（你的第一步）

1. 读本报告全文（约 15 分钟）
2. 自检：`cd <worktree> && python scripts/state_doctor.py`（期望 DRIFT_FREE）+ `git status -sb`（期望干净同步）
3. 按 §8 方案认领阶段（默认从 R1 守护层开工；若 R1 已完成则顺延）
4. 开工前对你要做的事**先搜 GitHub**（§48 门禁）并留 Decision 记录
5. 每完成一刀：机器验证（测试/矩阵/doctor）→ 提交推送 → 结果入 evidence → 更新本报告的状态快照
6. 遇到与定义/章程冲突 → 停下写升级块，不猜着干

---

## 修订记录

| 时间 | 改动 | 原因 |
|---|---|---|
| 2026-08-30 22:40 | 初版 | 接手者主报告 |
| 2026-08-30 22:52 | 补齐剩余 2 处（merge 措辞/失败账本路径） | 自我攻击 25 轮收尾 |
| 2026-08-30 22:50 | 自我攻击 25 轮后修正 | 差异说明/耗时纪律/POC 先行/并行目录/坑 11-12/分支地图/merge 措辞/失败账本路径/修订机制 |
