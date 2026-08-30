# 执衡接手者主报告（SUCCESSOR MASTER REPORT）· **版本 v1.1**

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

**弱 AI 定义（业主口径）**：混元 3 / 豆包级模型——能读懂简单指令、能执行命令行、有基本常识，但效果差、易犯错。**不是**完全无法用工具的模型。黑箱设计原则由此推导：把弱 AI 的输入面压到极窄（读一页卡 → 给目标 → 跑一条命令 → 贴结果），中间复杂度全部由系统兜底——它的"傻"由控制层拦住，这正是执衡的主场景而非降级。

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
| 12 | worktree 根 `AGENTS.md` | Controller TCB 边界规则（哪些文件属于控制面、Worker 权限边界） |

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

**⚠ 双 runtime 警告（事故级，勿混淆）**：本机存在**两个 runtime**——①**生产黑盒** `E:\WB	oolsi-production-control
untime\`（run.cmd + runtime.py，现役、冻结，弱模型实测走它）；②**施工线副本** worktree 的 `runtime/`（brain_bridge/capsule_bridge 等新模块在此开发）。**写代码只写 worktree 副本；绝不动生产 runtime.py 的既有结构**（红线"不得结构性重构"；新增命令走独立模块+薄入口，参照 brain_bridge 模式）。R3 四动词补齐若发现必须改生产 runtime.py 结构 → 停下升级，不得硬改。

**分支现状**：`master`=当前主线（全部工作在此，HEAD=`3467bc0`）；`v0.9-b1/authority-effect-core`=ARCHIVE（已合入 master，勿再开发）；`v0.9-b2/authority-effect-evidence`=历史线（8-28 旧开发线，勿动）；`spec/*`=历史变体（勿动）。**一切新工作在 master 或从 master 切出的新分支**（新分支需业主/主脑裁决后创建）。

## 3. 状态快照（2026-08-30 22:30 实测）

- git：master=`3467bc0`（收尾后 HEAD，快照 23:30；22:30 时点为 0979c69），本地=远端，工作树干净
- 测试：runtime 6 模块 113 tests OK + tests 13 OK；矩阵 36/36（`test_v09_attack_matrix_on_b1_core.py`，**用这个**，不是 `_offline.py`）
- 中继：**停**（最后心跳 8-30 01:42；历史 32 次启动、29 个崩溃锁——根因=进程生命周期绑 AI 会话，非 bug）
- 桥/catpaw：**停**（52900/32177 无监听）
- doctor：⚠ 本报告提交（non-governance）曾致 DRIFT——修复见修订记录 22:58：dev head 已同步至最新治理提交，复验 DRIFT_FREE
- 封印：gen 1 VERIFIED（收口专用库，在产库未触碰）
- release_status：`READY_FOR_USER_ACCEPTANCE`（边界：北极星自动调度闭环未达成，"可自动生产"宣称不成立）

## 4. 77 节定义对照（独立重判 2026-08-30，比旧矩阵 v3 更严——以此为准）

**✅ 40 节**（略——明细见 `docs/evidence/DEFINITION-77-SECTIONS-FINAL.md` v3 的 ✅ 集合，本重判与其差异：§62 升 ✅）：
§0,1,6,9,10,12,13,15,21,22,24,25,26,27,28,29,31,32,33,35,36,37,39,42,43,44,45,46,47,52,53,54,62,64,66,67,69,72,75,76

**🟡 30 节**（机制在、缺闭环/实测——按修复依赖排序；含 §74 最终完成条件，见下）：

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

> **执行顺序原则（业主 2026-08-30 指令）**：①需要**人参与的实测**（弱模型会话、API key、真实目标）一律标 ⚠ **暂缓·等人**，排在机器可完成工作之后；②不需要人参与的（代码/脚本/registry/测试套件/文档）先全部做完；③"机器验证"（测试/矩阵/doctor）不算实测，每刀必须做；④每刀过 §17 审核硬门禁后才算完成。

| 阶段 | 内容 | 对应节 | 验收 |
|---|---|---|---|
| **R1 守护层** | **可执行规格**：①先查 Trae-Ralph 的中继启动入口（package.json scripts 或 relay start 命令）；**兜底命令（已实测可用）**：watcher=`node src/review-relay.js watch --config "E:\WB\state\ai-production-control\construction-relay\relay.config.json"`；guard=`node src/relay/outer-guard.js watch --config <同 config>`（工作目录 `E:\WB\tools\Trae-Ralph`）；都不得接 tail/head 管道（坑 4）。查到官方入口优先，查不到用兜底——**不得因入口不明而停**；②写 `scripts/guard/guard_all.cmd`：a) 读 `construction-relay/watcher-heartbeat.json` 的 `at`，**超 300 秒**视为死 → `taskkill /F /T` 进程树 → 重启 watcher+guard（**不得接 tail/head 管道**，坑 4）；b) 查 52900 无监听 → 拉 bsk daemon；c) 查 Chrome 扩展连接 → 断则**记录+提示**（不自动开 Chrome，避免触发人工确认边界，见 §39），此项**不阻塞其他自愈动作**；d) 查 state.json 完整性 → 坏则 state-recover；e) 每动作追加 `construction-relay/guard-actions.ndjson` 记账；③注册计划任务 `schtasks /create /tn "ZhihengGuard" /tr "<guard_all.cmd 全路径>" /sc minute /mo 2 /f`（开机自启、与 AI 会话无关）；④验证：人为改旧心跳时间戳触发一次自愈（快速验证，不必等 72h），确认账本有记录 | §14/§61 | 触发式自愈实测 1 次成功；账本有记录；`schtasks /query /tn ZhihengGuard` 存在 |
| **R2 注册表+资产接入** | §63 机器可读 capability registry（JSON：Brain/Worker/C/R/Browser/Tool/Provider×Cost/Quota/Reliability/Official|Experimental）+ catpaw/bsk 由 registry 驱动拉起 | §63/§20/§21 | registry 被运行时消费；桥自动拉起 |
| **R3 黑箱 v1** | run.cmd 四动词补齐（补 RESULT/HUMAN_GATE）+ 一页操作卡（3-5 步）。⚠ **弱模型实测部分暂缓（需业主开弱模型会话）**——四动词/操作卡先做完，实测条件就绪即验 | §65/§71 | 代码+卡完成（机器验证）；弱模型实测留待业主 |
| **D1 R-Adapter（最优先）** | LiteLLM 接入：安装+配置+适配层代码全部先做完（不需要 key 的部分：安装、config 骨架、健康探测代码、热切换逻辑、仲裁规则、测试用 mock Provider）。⚠ **真实 Provider 调用暂缓（需业主提供 API key）**；LiteLLM 兼容性 POC 用 mock 先行 | §5/§12/§73 | mock 全链测试绿；真实 Provider 实测留待业主给 key |
| **D2 成本路由+熔断** | Expected Total Cost 路由 v1（registry Cost 字段驱动）；SAFE_HALT 真实触发 1 次 | §59/§61/§2/§19 | 路由可解释；熔断证据入仓 |
| **D3 Reuse 门禁+Supply Chain** | 任务开工强制 Reuse Decision 工具化；pip-audit/检查清单接入；download 补齐评估。⚠ **pip 网络坑**：本机 pip 默认可能直连失败——安装依赖时若超时加 `--proxy http://127.0.0.1:7897` 或用清华镜像 `-i https://pypi.tuna.tsinghua.edu.cn/simple`；装不上就先跳过该工具（门禁脚本先做成，工具后补），**不得因网络问题停摆** | §48-51/§20 | 无 Decision 不得 BUILD（系统强制） |
| **D4 并行+隔离+失效权** | 多 Worker 并行的调度/锁/隔离代码+测试套件先写好并跑机器验证（测试内模拟并行）；STOP→旧权失效端到端测试。⚠ 真实多 Worker 生产并行暂缓至机器验证全绿后 | §56/§57/§58/§16/§23/§41 | 测试套件全绿；真实并行实测视条件 |
| **D5 自举+智能** | 自举 L1：Stable 执衡自动修复自身一个真实缺陷走完 §74 十二条（**首选候选缺陷**：`runtime/test_v09_attack_matrix_offline.py` 当前环境 FAILED——T0 既有实验文件、非审计权威矩阵，预置授权缺失是真实可修缺陷，且修复不影响 `_on_b1_core.py` 权威矩阵；备选：§38 真实断网对账场景补测）；Task Graph 依赖图；Brain 选型；**缺陷→任务自动转换器**（doctor/测试失败输出 → 自动生成 goal 文件，接通"自我发现"闭环，R1 完成后可提前做——小脚本） | §68/§17/§7/§8/§11/§60/§70 | 全链证据入仓；转换器实测 1 次 |
| **D6 终验** | 矩阵 v4 全量复核（77/77 机器复核先行）+ **业主给一个真实目标走 §3 全自动（暂缓·需业主）** + 提请终裁（暂缓·需业主） | §3/§4/§74 | 机器复核 77/77 后即备妥，终验等人 |

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
12. **429 频率限制（实测）**：并行多会话/高频模型调用会触发账户级 429（重置可能长达一天）→ 触发即按章程阻塞绕行（转 READY 工作），该成员任务排队；控制并行度与调用频率
13. **额度意识**：真实 GOAL/弱模型实测/强 AI 审查全部消耗真实额度——每次真实动作前自问"这个消耗有没有必要"，章程 §6 预算熔断对弱模型会话同样适用
14. **兜底**：遇到本清单之外的报错 → 先 `python scripts/state_doctor.py` + 查 §1 文档清单 → 仍无法解决 → 写升级块停下，**不猜着干**

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
- **改坏了第一时间怎么办**：①**代码/文档类** → `git revert <坏提交>` 或 `git checkout <文件>`（先 `git log --oneline` 定位）；②**RUN 状态类** → state-recover；③**不确定改了什么** → `git status`+`git diff` 看清再动，不确定就停下升级，**不要乱 revert 别人的提交**；④治理文件改错 → 按坑 9 重新同步 + doctor 复验

## 14. 已知未验证/存疑（诚实清单）

- R-PROD 会话健康：`last_verified=2026-08-19`（实测，11 天+未验证），登录态/会话可能失效——**用前必须 `chatgpt_bridge status` 实测确认**，失效则升级业主（R-Adapter 完成前这是单点故障）
- LiteLLM 与本系统兼容性（未实测，方案假设）
- 中继根因"生命周期绑会话"是推断，R1 落地时验证
- 本报告 77 节重判为单人判定，D6 矩阵 v4 需独立复核
- `E:\执衡\04_测试证据` 等资产已备份但未融入系统（§63 注册表 R2 落地时收编）

## 15. 新 AI 启动指令（你的第一步）

1. 读本报告全文（约 15 分钟）
2. 自检（**注意 cwd**：doctor 与矩阵脚本在 worktree 根跑；单测在 `runtime/` 目录跑——跑错目录会误判）：
   - `cd C:\Users\17838\Documents\Qoder\2026-08-28\031cb4e3\b1 && python scripts/state_doctor.py`（首跑期望 DRIFT_FREE；**若你刚提交过非治理提交而报 DRIFT，按坑 9 同步 dev head/registry 即可，不是环境坏**）
   - `git status -sb`（期望干净同步）
   - `chatgpt_bridge status`（R 通道健康，需 `BSK_HOME=E:/WB/tools/bsk-file-bridge/bsk-home`；**桥停 → 按 §13 拉起顺序恢复；R-PROD 会话失效 → 写升级块给业主，等待期间继续不需要 R 的 READY 工作，不得自行更换会话**）
   - ⚠ **R-PROD 陈旧风险（实测）**：`会话注册.json` 中 R-PROD 的 `last_verified = 2026-08-19`，到接手时可能已过期 11 天以上（登录态/会话可能失效）。**任何需要 R 审查的动作之前必须先 `chatgpt_bridge status` 实测确认**，不要默认它可用
3. 按 §8 方案认领阶段（默认从 R1 守护层开工；若 R1 已完成则顺延）
4. 开工前对你要做的事**先搜 GitHub**（§48 门禁）并留 Decision 记录
5. 每完成一刀：机器验证（测试/矩阵/doctor）→ 提交推送 → 结果入 evidence → 更新本报告的状态快照
6. 遇到与定义/章程冲突 → 停下写升级块，不猜着干

## 15b. 弱 AI 精简启动卡（混元3/豆包级可读性版）

> 你不需要理解执衡内部。只做三件事：**①读本卡 ②说目标 ③跑一条命令**。其余全部自动。

1. 进入目录：`cd C:\Users\17838\Documents\Qoder\2026-08-28\031cb4e3\b1`
2. 把目标写进 UTF-8 文本文件（如 `goal.txt`）：写清"要什么成果 + 怎么算做完了"。
3. 提交任务（`<...>` 换成你的真实路径）：
   `& "E:\WB\tools\ai-production-control\runtime\run.cmd" work --goal-file <目标文件> --r-url <R 会话 URL>`
   - R 会话 URL 从 `E:\执衡\05_资源\会话注册.json` 的 **`roles` → `R-PROD` → `url`** 读取（注意是嵌套三层，不是顶层 `R-PROD`），**不要猜、不要改这个文件**；取值后用 `chatgpt_bridge status` 确认该会话仍健康（见下条风险）
4. 干完活把结果写进文本文件回交：
   `& "E:\WB\tools\ai-production-control\runtime\run.cmd" report --run-id <RUN 号> --message-file <结果文件>`
5. 结果只有两种：`PASS`（通过）或 `REWORK`（审查方说哪里不行）→ 按它说的改 → 再回交，直到 PASS。
6. **禁止**：改 `E:\WB\tools\ai-production-control\runtime\` 下任何文件；碰任何凭据文件；自己宣布"完成了"（只有审查方 PASS 算数）；猜路径。

## 16. 持续推进协议（业主指令：不许中途停，做到终点）

- **终点定义**：矩阵 v4 = 77/77 全满足 + 弱模型黑箱实测通过 + 业主终裁 FINAL DONE。**到达终点前，完成一刀立即开下一刀（按 §8 顺序），禁止"阶段性汇报后原地等待指示"。**
- **唯一合法停止点**（白名单，此外一律继续）：
  1. 红线触发（§12）→ SAFE_HALT + 升级块；
  2. 与定义/章程冲突或发现报告错误 → 升级块（写完继续不受阻的 READY 工作）；
  3. 需要业主/主脑裁决的事项（merge、新分支、凭据、高危效果、预算熔断）→ 升级块，**等待期间继续其他 READY 工作**（§16 精神：冻结的是 Candidate 不是 Builder）；
  4. **上下文将尽** → 先落移交检查点到**独立文件** `docs/evidence/HANDOFF-CP-<日期>-<序号>.md`（含：完成项/进行中/下一步精确命令/踩坑/待确认），**主报告只追加修订记录一行**（避免每会话改主报告引发 drift 与冲突），新会话从检查点 + 本报告 §15 恢复——这是唯一"停了但不丢进度"的停止。
- **上下文省用纪律（为通宵续航）**：a) 每刀开工前先想清"最小执行路径"，不读无关文件、不做无产物搜索（§19）；b) 命令批量执行（一次 Bash 完成多步），不碎调用；c) 大文件输出用 tail/grep 截取，不整读；d) 文档只在需要时读相关节，不整篇重读；e) 检查点文件精炼（<60 行），新会话 5 分钟可接续。
  5. 业主 STOP/PAUSE（最高优先，立即生效）。
- **进度自证**：每刀完成 → 机器验证（测试/矩阵/doctor）→ 提交推送 → 本报告修订记录登记实际耗时与新状态。修订记录就是你持续推进的轨迹，任何会话断掉后接手者从它恢复。
- **并行**：能开多会话就开（按 §8 目录分工），主会话负责合并与治理文件。
- **并行 git 互斥（重要）**：多人**同时 push 会冲突**——纪律：①开工前 `git fetch`；②提交前 `git pull --rebase`；③**push 串行**（主会话协调，一个推完下一个）；④治理文件（PROJECT_STATE.*/branch_registry/本报告）**只由主会话写**；⑤冲突先沟通，不擅自强制解冲突（禁 force）。

## 17. 审核硬门禁（业主指令：无审核通过不得推进）

- **每刀完成 → 必须经独立审核（专家团内 1-2 名以上审核者）通过后，才允许进入下一刀。** 审核者与实现者必须上下文独立（不同会话/不同成员），不得自审自过（§42/§50 精神）。
- 审核内容：a) 机器验证亲跑复现（测试/矩阵/doctor）；b) 红线核查（§12 清单）；c) 对应定义节的证据是否真实充分；d) 是否夹带越权改动。
- **关键阶段（R1 守护层 / R3 黑箱 / D1 R-Adapter / D6 终验）= ≥2 名审核者会签**，其余阶段 ≥1 名。
- 审核结论落仓（docs/evidence/reviews/），REWORK 必须修复后复审；审核记录计入修订轨迹。
- 审核者不可用（额度/429）→ **实现推进不被审核阻塞**：继续做下一刀的实现与机器验证（测试/矩阵/doctor 照跑），审核在可用后排队补签；**只有"宣布阶段完成/进入 D6 终验"才必须等审核**——今晚 429 高发期也能持续干活。
- **429 自我保护（重要）**：账户级 429 会阻止子会话/Agent 派发——触发后：a) 暂停派新 Agent；b) 主会话继续纯命令工作（bash/git/测试不受 429 影响）；c) 降低模型调用频率（避免连续快速调用）；d) 429 通常重置需数小时——按"先实现后补审"策略继续。

---

## 修订记录

| 时间 | 改动 | 原因 |
|---|---|---|
| 2026-08-30 22:40 | 初版 | 接手者主报告 |
| 2026-08-30 22:50 | 自我攻击 25 轮后修正 9 处 | 差异说明/耗时纪律/POC 先行/并行目录/坑 11-12/分支地图/merge 措辞/失败账本路径/修订机制 |
| 2026-08-30 22:52 | 补齐剩余 2 处（merge 措辞/失败账本路径） | 自我攻击 25 轮收尾 |
| 2026-08-30 22:56 | 第二轮挑刺 6 处：双 runtime 混淆警告（事故级）、AGENTS.md 入清单、缺陷→任务转换器入 D5、弱 AI 能力边界定义、429/额度坑、启动自检补 R 通道 | 业主连续追问榨出的缺口 |
| 2026-08-30 22:58 | QA 独立审核 REWORK 修正：§4 删 §59/§63 重复行（自洽 40/30/7）；RELAY_STARTED 口径注；§3 快照更新；§17 审核硬门禁 + §8 重排（需人实测项暂缓） | 独立 QA 实测发现 + 业主指令 |
| 2026-08-30 23:02 | §16 持续推进协议（终点定义 + 停止点白名单） | 业主指令：不许中途停 |
| 2026-08-30 23:05 | doctor DRIFT 修复（报告提交后 dev head/registry 同步，恢复 DRIFT_FREE）；修订记录重排 | 遵守本报告坑 9 |
| 2026-08-30 23:08 | 第三轮挑刺 7 处：R1 可执行规格、并行 git 互斥、检查点独立文件、§15b 弱 AI 精简卡、回滚指引、cwd/R-PROD 细节；报告版本 v1.1（正文冻结 + 三类可维护区） | 换角度攻击（使用者视角） |
| 2026-08-30 23:12 | 机械验证抓到真缺陷：§15b 弱 AI 卡的 R 会话 URL 路径写错（应为 roles→R-PROD→url 三层嵌套，非顶层 R-PROD）；补 R-PROD last_verified=2026-08-19 陈旧风险 | 逐条命令实测（非主观攻击） |
| 2026-08-30 23:15 | 修订记录重建为规范 10 行（修乱序、补缺失行、去嵌入换行） | 接手前收尾（DeepSeek V4 flash） |
| 2026-08-30 23:33 | 通宵续航补丁 6 处：429 不阻塞实现推进+自我保护、上下文省用纪律、pip 代理/镜像兜底、Chrome 检查降级不阻塞、中继兜底命令、自举候选缺陷 | 业主指令：今晚不停顿推进 |

、修乱序、补缺失行）；清理临时脚本 | 接手前收尾（DeepSeek V4 flash） |
