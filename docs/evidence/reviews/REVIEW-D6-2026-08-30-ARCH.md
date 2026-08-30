# REVIEW-D6-2026-08-30-ARCH — D6 终验：77 节定义矩阵 v4 机器复核（架构会签）

- 审核人：高见远（software-architect-d6，D6 终验架构复核实例，与 QA 复核人 software-qa-d6 并行独立复核）
- 日期：2026-08-30
- 分支：v1.1-blackbox（HEAD=b74f9d8，dev head → D5 完成）
- 解释器：Python312（`C:\Users\17838\AppData\Local\Programs\Python\Python312\python.exe`）
- 复核方法：架构视角"机制真实性 + 架构完整性"，全部亲跑复现（非采信记忆/测试绿）；只读复核，唯一写入 = 本检查点文件
- 依据：宪法 `docs/canon/ZHIHENG_FINAL_DEFINITION_FINAL_CANONICAL.md`（77 节零修改，SHA256 4c05a21f…9a4a）；旧矩阵 v3 `docs/evidence/DEFINITION-77-SECTIONS-FINAL.md`；主报告 §4 独立重判 40✅/30🟡/7❌
- 硬规则遵守：L3 依赖节（§3 真实目标、§4 真实交付、§5 真实 Provider、§74 终裁）保持 🟡 注"待 L3"，未因 mock/机制在宣称 ✅

---

## 0. 结论速览

**77 节 v4 独立判定（架构会签稿）：54 ✅ / 23 🟡 / 0 ❌（合计 77）**

| 变化 | 节数 | 明细 |
|---|---|---|
| 保持 ✅ | 40 | 主报告 ✅ 集合不变（§0,1,6,9,10,12,13,15,21,22,24,25,26,27,28,29,31,32,33,35,36,37,39,42,43,44,45,46,47,52,53,54,62,64,66,67,69,72,75,76） |
| 🟡 升 ✅ | 13 | §14,16,19,2,23,40,41,48,49,50,61,65,73（本线交付直接补足缺口） |
| ❌ 升 ✅ | 1 | §63（R2 registry 机器可读+被多模块真实消费） |
| ❌ 升 🟡 | 6 | §3,51,55,58,59,68（机制真实落地但缺 L3 闭环/端到端） |
| 保持 🟡 | 17 | §4,5,7,8,11,17,18,20,30,34,38,56,57,60,70,71,74 |

**对 QA 复核的独立性声明**：本判定完全独立做出（亲跑 + 读源码 + 读审核记录），未参考 QA 结论；差异节见 §6，最终 v4 由主理人合并两文件。

---

## 1. 机器复核亲跑记录（全部 Python312，本审核实跑）

| # | 验证项 | 命令 | 结果 |
|---|---|---|---|
| 1 | doctor 体检 | `python scripts/state_doctor.py` | **DRIFT_FREE** ✅ |
| 2 | 权威矩阵 | `python runtime/test_v09_attack_matrix_on_b1_core.py` | **36/36 MATCH（matched=36, red=0）**，R1-R36 + R34-FAITHFUL 全绿 ✅ |
| 3 | registry 校验 | `python docs/ops/registry-validate.py` | **PASS**（15/15 节/104 条/24 非阻断 warning）exit=0 ✅ |
| 4 | 黑箱 RESULT | `python runtime/blackbox_bridge.py result --run-id RUN-20260818-173304-7350` | verdict=PASS, final=true, 机械投影正确, exit=0 ✅ |
| 5 | 黑箱 HUMAN_GATE | `python runtime/blackbox_bridge.py human-gate` | total_scanned=118, waiting=12, 分类机械规则正确, exit=0 ✅ |
| 6 | 成本路由 | `python runtime/cost_router.py route --goal "机械读取配置文件并格式化输出" --rework-risk low` | ALLOWED, recommended=weak, ETC=0.05, exit=0 ✅ |
| 7 | 并行调度 | `python runtime/parallel_scheduler.py status` | ok=true, state_root=state/parallel-scheduler, exit=0 ✅ |
| 8 | Context Sufficiency | `python runtime/context_sufficiency.py route --context <json> --required sales_data` | SUFFICIENT（1/1 齐备）exit=0；补测缺 revenue → **SWITCH_LOCAL_BRAIN**（五分支真实触发）✅ |
| 9 | 自举 | `python runtime/self_heal.py list` | fixlets=[SH-001] 注册，exit=0 ✅ |
| 10 | A1 自动调度 | `python scripts/relay_autopilot.py status` | 2 runs WRAPPED（A1 L2 残留真实状态）、inbox_pending=0、exit=0 ✅ |
| 11 | Reuse 门禁 | `python scripts/reuse_gate.py check --task "成本路由" --search litellm cost router` | ok=true, 本地 registry + failed-ledger 搜索真实执行 ✅ |
| 12 | Supply Chain | `python scripts/supply_chain_check.py check` | pip_audit available=true, status=OK, vulns=0, deps=1 ✅ |
| 13 | Task Graph | `python runtime/task_graph.py build --goal-file <真实文件>` | valid=true, 拓扑/关键路径/并行组输出正确, exit=0 ✅ |
| 14 | R-Adapter | `python runtime/adapters/r_adapter.py health --config r_adapter.config.example.json` | 4 providers 全 UNCONFIGURED（无 key 正确短路，零网络副作用）, exit=0 ✅ |

补充取证：
- git log --all：R1(4157cb2)/R2(a35bced)/R3(4f151c4)/A1(ecd5cc9)/D1(f80613e)/D2(db4ac31)/D3(f0b9c6d)/D4(b5ffc9e)/D5(02d5c72) 提交全部存在；HEAD=b74f9d8（governance-only sync）✅
- registry 被真实消费：`cost_router.py` L132-141 `load_registry_costs` 读 registry costs 节；`context_sufficiency.py` L66-67/L216-217 读 registry brains/providers 节；`reuse_gate.py` local_registry_search 读 registry——**§63 机器可读可消费成立** ✅
- 既有核心模块存在：brain_bridge/capsule_bridge/ec_lite/effect_safety_lite/goal_contract_lite/strategic_correction/strategic_reuse_contract + src/aicontrol/ 15 文件；ec_lite `DEFAULT_NO_PROGRESS_ACTIONS=50` 真实 ✅
- R1 计划任务：`schtasks /query /tn ZhihengGuard` 存在（R1 ARCH 审核亲跑确认 2min 自动触发 + 账本 66+ 行合法 JSON）
- 交付物齐全：docs/ops/ 15 文件（blackbox-card/parallel-README/d5-README/registry-*/adapter-README 等）、docs/evidence/d5/ 7 文件（L1_goal/SH001_fix.diff/self_heal_events.jsonl/PRE_FIX 等）

---

## 2. 77 节 v4 判定表（架构会签稿）

图例：✅ 机制真实+验证充分 / 🟡 机制在，端到端或生产级未全量（含待 L3）/ ❌ 未满足

### §0-§10

| 节 | 内容 | v4 | 架构判定与证据 |
|---|---|---|---|
| §0 | 最高原则 | ✅ | fail-closed（ec_lite/effect_safety_lite + 矩阵 R31-R34） |
| §1 | 产品本质 | ✅ | 系统即此 |
| §2 | 成本感知 | ✅ 升 | D2 ETC 核算真实（几何级数数学正确、手算 3 例吻合、读 registry costs 节）；真实价目校准留 L3 |
| §3 | 最终体验 | 🟡 待L3 | A1 状态机接线真实（L2 全链重放 PASS）；但真实弱模型会话+真实目标全自动未跑——**硬规则保持 🟡 待L3**。架构确认：A1 是 §3 的接线基础，31 步中"理解真实目标→最终交付真实成果"依赖 L3 |
| §4 | 生产系统 | 🟡 待L3 | Artifact+Evidence 真实（8 次真实 GOAL/118 RUN）；Acceptance 真实用户级交付链未走——**硬规则保持 🟡 待L3** |
| §5 | Provider 独立 | 🟡 待L3 | D1 R-Adapter（LiteLLM）+ Worker-Adapter（CLI）骨架真实、mock 39 绿、health/pick/review mock 亲跑通过；真实 Provider 替换需 key（L3）——**硬规则保持 🟡 待L3** |
| §6 | 核心角色 | ✅ | O/B/C/R/EC/Runtime 全在案 |
| §7 | Brain | 🟡 | 规则式拆解 + brain-pick 选 Brain 真实（task_graph build/brain-pick 亲跑）；**选 Worker/选工具/重规划/判断何时调用强 AI（§7 后半）未实现** |
| §8/§9 | C 纠偏+独立性 | 🟡 | strategic_correction 契约 + 15 次真实判定（机制真实）；**"独立 C 常态化"（独立于执行链的常态化 C 检查流程）未建**——主报告判定维持 |
| §10 | Worker | ✅ | 累计 8 次真实 GOAL |

### §11-§20

| 节 | 内容 | v4 | 架构判定与证据 |
|---|---|---|---|
| §11 | EC 执行纠偏 | 🟡 | ec_lite 机制真实（NO_PROGRESS=50 + D2 SAFE_HALT NO_PROGRESS L2 触发）；真实执行现场触发案例少 |
| §12 | R 独立审查 | ✅ | 8 真实 GOAL 终审 PASS |
| §13 | 三纠错不混淆 | ✅ | EC≠C≠R 分置 |
| §14 | Lifecycle Controller | ✅ 升 | **R1 guard_all.cmd OS 级守护真实成立**：schtasks 计划任务（2min 周期、与 AI 会话无关）、心跳判死 300s、杀树重启、bsk 动态端口、单实例锁、账本；R1 ARCH 审核亲跑确认自动触发。§14 核心硬要求"非 AI 独立守护"已补。注：Controller 全量状态管理分散 src/aicontrol+各模块，未统一单一 Lifecycle API（架构观察，非缺口） |
| §15 | 跨回合自动继续 | ✅ | 多轮 REWORK 自动重交 + A1 状态机 |
| §16 | WAIT 是 Task State | ✅ 升 | 双机制 + L2 端到端实测：A1（B REVIEWING 时 C 推进到 REPORTED）、D4（LOCK_WAITING 不阻塞其余 READY）。"REVIEW FREEZES THE CANDIDATE, NOT THE BUILDER"语义真实成立 |
| §17 | Task Graph | 🟡 | task_graph.py 图结构机制真实（depends_on/parallel_with/Owner/动态 add/拓扑/环检测/关键路径，build 亲跑 valid）；**缺口：①运行中新发现（Bug/Gap/Failure）自动纳入 Task Graph 闭环缺（add 是手工命令，self_heal convert 未自动 add）；②规则式拆解粒度粗糙（同目标 QA 亲跑 5 节点、本审核亲跑 1 节点）** |
| §18 | Task Graph 双视图 | 🟡 | 单一真源成立 + status（human 可读）/build（AI 执行视图）投影真实；**AI Execution View 字段覆盖不全（缺 input/output/authority/locks/retry/next_action/evidence），Human View 缺"离完成还有啥"总结** |
| §19 | NO_PROGRESS | ✅ 升 | 双通道真实：ec_lite 计数器（DEFAULT=50）+ D2 simulate-rework 真实触发 SAFE_HALT NO_PROGRESS（3/3 L2 验证） |
| §20 | 浏览器通用面 | 🟡 | **download ❌ 已补齐**（Playwright 真实 download 559 字节，D3 smoke 证据在仓）；search/fetch 骨架真实；但通用网页操作（点击/表单/滚动等）仅 mock 未全面实测、登录态敏感站仍走 bsk 分工——机制在、真实网页操作面未全量 |

### §21-§30

| 节 | 内容 | v4 | 架构判定与证据 |
|---|---|---|---|
| §21 | 本地执行面 | ✅ | run.cmd + 手册 |
| §22 | Goal Contract | ✅ | goal_contract_lite |
| §23 | 目标变化失效旧权 | ✅ 升 | D4 STOP 端到端实测（directive STOP → REVOKED + REVOKED_EPOCH 拒收 + 旧结果保留证据），L2 充分 |
| §24 | AI 记忆非 Truth | ✅ | capsule 机械投影 |
| §25/§26 | 项目真源/当前进展 | ✅ | PROJECT_STATE 回写 |
| §27 | Context Capsule | ✅ | capsule_bridge |
| §28 | 决策理由保存 | ✅ | D001-D022 账本 |
| §29 | Canonical State Revision | ✅ | state revision + verify |
| §30 | Stale Result Safety | 🟡 | **执行单元级 stale 真实**（心跳超时→STALE 回收+STALE_HEARTBEAT 拒收+释放资源锁，D4 实测）；**§30 全角色通用绑定（Brain/C/R/Browser 结果绑定 revision/commit/hash）未全覆盖**——仅覆盖 Worker 执行结果 |

### §31-§40

| 节 | 内容 | v4 | 架构判定与证据 |
|---|---|---|---|
| §31 | State 可恢复 | ✅ | state.json + verify + candidate_r14 state-recover |
| §32 | Control Plane Trust | ✅ | scoped_authorization + src/aicontrol TCB |
| §33 | Authority 模型 | ✅ | scoped_authorization |
| §34 | Split Brain 防护 | 🟡 | **本线未交付双 Controller 竞争实测**。D4 epoch/STALE_EPOCH 是任务级授权代，非 Controller 级 Lease/Fencing Token；中继锁（relay.lock）存在但双 Controller 竞争未测。架构判断：**不能升 ✅**——§34 专指 Controller 级竞争，机制仅部分相关 |
| §35 | Identity Binding | ✅ | RUN 绑定（R3 审核实证 reply_epoch 命名/run_id 绑定） |
| §36 | Effect 追踪 | ✅ | effect_safety_lite |
| §37 | Effect Write-Ahead | ✅ | WAL + 矩阵 R19-R24 |
| §38 | OUTCOME_UNKNOWN | 🟡 | **机制前半真实**（OUTCOME_UNKNOWN + decision_entry=MANUAL_OR_RETRY 不自动判定成败，D4 实测）；**Reconcile→Inspect Reality→SUCCESS/FAILED→Decide Retry 全链未实现**；真实对账场景未发生 |
| §39 | 权限非聊天记忆 | ✅ | 效果闸门 + human gate 机制 |
| §40 | Revocation 单调性 | ✅ 升 | epoch 单调递增测试（1→2）+ STALE_EPOCH 拒收（D4 实测）；真实回滚复活场景未发生但机制 L2 充分 |

### §41-§50

| 节 | 内容 | v4 | 架构判定与证据 |
|---|---|---|---|
| §41 | User Override 最高 | ✅ 升 | D4 REVOKED_EPOCH 拒收被撤销代结果（STOP 端到端实测） |
| §42 | 证据非自证 | ✅ | R 独立 + 机器验证 |
| §43 | Review 绑定 | ✅ | RUN↔commit/artifact |
| §44 | 机器验证 | ✅ | 36/36 + 多套测试全绿（本审核亲跑） |
| §45 | 状态层级 | ✅ | DISCUSSED..PRODUCTION_VERIFIED |
| §46/§47 | 外部/Prompt 注入 | ✅ | 实现 |
| §48 | Reuse Gate | ✅ 升 | reuse_gate.py **门禁真实强制**：--require-decision 无记录 → BUILD_BLOCKED exit 1（QA 亲跑 + 本审核 check 亲跑）；record 留痕 → GATE_OK |
| §49 | Reuse Decision | ✅ 升 | record 结构化留痕（decision_id/task/decision/evidence/gate_check_summary/failed_approach_warning）+ reuse-decisions.ndjson |
| §50 | Reuse 不等于 Trust | ✅ 升 | decision 留痕含 evidence + failed_approach_warning；supply_chain 依赖检查补充（D3 同包） |

### §51-§60

| 节 | 内容 | v4 | 架构判定与证据 |
|---|---|---|---|
| §51 | Supply Chain Gate | 🟡 升 | **依赖漏洞扫描真实工具化**（supply_chain_check.py + pip-audit 真实扫描，本审核亲跑 vulns=0）；**缺口：§51 十项检查仅覆盖 Dependencies 维度，License/Source/Maintainer/Network Behavior/Suspicious Behavior 未自动化；"高风险资源→Sandbox/Human Gate/Reject"处置策略未实现** |
| §52/§53 | Secret/凭据 | ✅ | 敏感清单零入仓；registry 仅登记路径 |
| §54 | Data Egress | ✅ | effect_safety_lite + §55 脱敏机制 |
| §55 | Context Sufficiency | 🟡 升 | **五分支路由机制真实**（SWITCH_LOCAL_BRAIN/SWITCH_ALLOWED_PROVIDER/DESENSITIZE_RETRY/HUMAN_AUTHORIZATION/BLOCKED，策略驱动、读 registry、14 测试绿、本审核亲跑 SUFFICIENT + SWITCH_LOCAL_BRAIN）；**未端到端接入真实 Brain 执行链**（独立 CLI，未挂接 autopilot/runtime 主链） |
| §56 | 多 Worker | 🟡 | 调度机制真实（并发分派/资源声明/结果对应，24 测试绿 + 锁冲突场景 3 任务全 COMPLETED L2）；**真实多 Worker 生产并行未跑（L3）**——主报告 C-3 判定维持 |
| §57 | Resource Lock | 🟡 | 锁机制真实（mkdir 原子 + token/age stale 接管 + 冲突排队 LOCK_WAITING）；**真实多 Worker 冲突未发生**——与 §56 同步保持 🟡 |
| §58 | Project Isolation | 🟡 升 | **架构专项判断见 §4.1**：机制真实（每任务独立 work_dir + 越界写校验 + symlink 逃逸扫描 + SANDBOX_VIOLATION 实测）但为"验证式/事后检测"非"执行时强制"，且真实生产并行未跑——**部分满足** |
| §59 | Cost Routing | 🟡 升 | **架构专项判断见 §4.2**：ETC 核算 + 路由建议 + 熔断状态机真实；**路由决策未被调度消费（advisory 未接线）**——部分满足 |
| §60 | Escalation Ladder | 🟡 | L0-L2 机制真实（max-reworks 熔断 A1/D2 + Task Graph + §55 路由 + 转换器）；**L3-L9 自动升级链（换 Worker/换更强模型/Brain 直接处理/C 换路线/Human Gate）未实现**，仅 README 映射存档 |

### §61-§70

| 节 | 内容 | v4 | 架构判定与证据 |
|---|---|---|---|
| §61 | Hard Fuse | ✅ 升 | **SAFE_HALT 真实触发 1 次**（BUDGET_BREACH/CONSECUTIVE_BREACH/NO_PROGRESS 三条件 + 冻结/reset + history 保留，QA+本审核亲跑）；生产阈值待 L3 校准（OBS-D2） |
| §62 | Safety > Liveness | ✅ | fail-closed 矩阵 R31-R34（主报告升 ✅ 维持） |
| §63 | Capability Registry | ✅ 升 | **架构专项判断见 §4.3**：registry 机器可读（15 节/104 条/schema 校验）+ **被多模块真实消费**（cost_router/context_sufficiency/reuse_gate 亲跑证实） |
| §64 | Tool Manual | ✅ | operator_manual + 用户指南 + 各包 README |
| §65 | 唯一入口 | ✅ 升 | **四动词真实**（work/report 生产 run.cmd + result/human-gate blackbox_bridge，本审核亲跑）+ blackbox-card 一页卡。注：R3 ARCH 已记录 work 委托层 r-url 参数忽略低危缺陷（不构成 §65 缺口） |
| §66 | Stable/Candidate | ✅ | StableLineage 8 测试绿 |
| §67 | Rollback | ✅ | lineage.rollback |
| §68 | 自举 | 🟡 升 | **架构专项判断见 §4.4**：L1 自举闭环真实（SH-001 修复 offline 测试、双矩阵 36/36、权威矩阵字节零改动、转换器 convert 亲跑生成 goal）；**§68 完整语义（Stable 全面参与开发 Candidate：创建任务/调度 Worker/搜索方案/调用独立 Review 全链）未达**——当前为"最小自举" |
| §69 | 每阶段可用产品 | ✅ | 累计 8 次真实 GOAL |
| §70 | Trace | 🟡 | **关键字段已补**（D5 trace:{model,ai,tool,reason_retry,cost} 亲跑确认 + 各账本 ndjson）；**统一可查询 Trace 接口缺**（"谁做了什么/为何换 Worker/为何换路线/为何最后 PASS"散落各模块，无单一命令回答） |

### §71-§76

| 节 | 内容 | v4 | 架构判定与证据 |
|---|---|---|---|
| §71 | 简洁 UI | 🟡 | **一页卡 + Human Gate/Result 视图真实**（blackbox-card + human-gate/result 亲跑）；**统一"当前状态/进度/离完成还有啥"用户视图未建**（与 §18 同源缺口） |
| §72 | 六个根 | ✅ | 全实现 |
| §73 | 最终可靠性原则 | ✅ 升 | **15 行逐条核对：3 个缺失行全部被本线补齐**——Supply Chain（D3）、成本调度（D2 ETC）、Lifecycle 守护（R1 guard）。第 9 行"Effect 不确定→WAL/Reconciliation"：WAL 有（§37 ✅）、Reconciliation 部分（§38 🟡）——机制对应成立，判 ✅ |
| §74 | 最终完成条件 | 🟡 待L3 | 工程项达成（36/36 + 审核会签 + doctor DRIFT_FREE）；**业主终裁待定——硬规则保持 🟡 待L3** |
| §75 | 定义治理 | ✅ | 宪法零修改 |
| §76 | 最终一句话 | ✅ | 系统即此 |

---

## 3. 汇总（架构会签稿 v4）

| 档位 | 节数 | 明细 |
|---|---|---|
| ✅ | **54** | §0,1,2,6,9,10,12,13,14,15,16,19,21,22,23,24,25,26,27,28,29,31,32,33,35,36,37,39,40,41,42,43,44,45,46,47,48,49,50,52,53,54,61,62,63,64,65,66,67,69,72,73,75,76 |
| 🟡 | **23** | §3,4,5,7,8,11,17,18,20,30,34,38,51,55,56,57,58,59,60,68,70,71,74 |
| ❌ | **0** | — |

**合计 77 节全覆盖（§0-§76）。** 注：本稿为架构复核独立判定，正式 v4 待主理人合并 QA 复核文件后定稿。

---

## 4. 边界节架构专项判断（任务指定）

### 4.1 §58 Project Isolation —— **🟡（部分满足，不能 ✅）**

**判断：parallel_scheduler 的 sandbox 是"报告 writes + symlink 扫描"近似，架构上算机制真实、算部分满足，但不算 §58 完整满足。**

理由（架构视角）：
1. **机制骨架真实非空壳**：每任务独立 work_dir（L718）+ 执行器报告写入路径越界校验（L1137-1142）+ work_dir 内 symlink 逃逸扫描（L1143-1149）+ SANDBOX_VIOLATION 拒绝结果（实测）。这是"防已报告的越界写 + 防 symlink 逃逸"。
2. **本质是"验证式/事后检测"，非"执行时强制"**：真实 CLI worker（任意命令）可在执行过程中写越界，调度器只能在 worker 报告后才检测。对不可信/有 bug 的 worker，**不能阻止污染，只能拒绝结果**。§58 语义"Project A 不得污染 Project B"需要执行时边界（OS 级沙箱：受限 token/Job Object/容器）。
3. **§58 完整清单（Goal/State/Browser/Auth/Worker/Reviewer/Evidence/Effect/Credential Scope/Run/Task Graph 独立）**：当前实现覆盖了"Worker 写文件不越界 + 独立 work_dir"，但 Browser/Auth/Credential Scope 的项目级隔离未在调度器内实现（依赖既有 bsk profile 隔离）。
4. **真实生产并行未跑（L3）**：L2 mock 验证充分，但"两个真实 Worker 同时生产"的隔离效果未实测。

综合：D4 把 §58 从"无系统实现"推进到"有真实机制 + L2 实测"，故从 ❌ 升 🟡；因执行时强制缺 + L3 未跑，不能 ✅。

### 4.2 §59 Cost Routing —— **🟡（部分满足，不能 ✅）**

**判断：cost_router 构成"成本路由决策器"（advisory），但不构成"成本路由调度链"（未接线）。**

理由：
1. **机制真实**：ETC = Σ(阶段成本×概率权重) 数学正确（几何级数体现 retry cost，手算 3 例吻合）、读 registry costs 节、输出 recommended_route（weak/strong/hybrid）+ 预算熔断 + SAFE_HALT 状态机。这是 §59 的核心算法机制。
2. **架构缺口：路由决策未被调度消费**。cost_router 输出"recommended_route"但没有任何调度器/autopilot 消费它去实际选 Worker/Brain/R。§59 明文"调度不能只比较哪个模型最便宜，应该综合……"——当前是"计算器"，不是"路由器"（无路由动作）。
3. **数据面部分真实**：registry costs/quotas 有数据（costs 8 条 + quotas 6 条），但 r_adapter/worker_adapter config 未带 cost_ref/quota_ref（D1 ARCH DEF-4 已记录），调度侧无成本维度。

综合：❌ → 🟡（算法机制真实、熔断真实触发），端到端"路由→调度→执行"接线留 D6/L3。

### 4.3 §63 Capability Registry —— **✅（升 ✅，架构判断成立）**

**判断：registry 机器可读 + 机器可消费 + 实际被多模块消费，满足 §63 字面与目的。**

理由：
1. **机器可读**：config/capability-registry.json（schema_version 1，15 节与 §63 15 项一一对应，104 条）+ registry-validate.py 校验（亲跑 PASS + 5 类负向拦截）。
2. **机器可消费（亲跑证实）**：cost_router.load_registry_costs（L132-141）读 costs 节；context_sufficiency._load_registry（L66-67/L216-217）读 brains/providers 节；reuse_gate local_registry_search 读 capabilities/tools。**不是"手册入仓"——是真实 JSON 数据面**。
3. **目的"资源可替换"部分达成**：registry 是 D2 成本路由数据面 + D5 五分支数据面 + R2 launch 探活消费；但 r_adapter/worker_adapter 仍用独立 config 而非 registry 驱动（主链未以 registry 为唯一真源——**残余观察，建议 D6/L3 前对齐，不构成 §63 缺口**）。

综合：从 ❌ 升 ✅（v3 C-3 降级理由"手册入仓≠机器可读注册表"已被 R2 消除）。

### 4.4 §68 自举 —— **🟡（升 🟡，不能 ✅）**

**判断：L1 自举闭环真实（有真实缺陷修复案例），但非 §68 完整语义。**

理由：
1. **L1 真实案例成立**：self_heal.py 转换器（DRIFT/FAILED/ERROR→goal 文件）+ fixlet SH-001（最小修复 offline 测试）+ 验证（双矩阵 36/36 + 权威矩阵字节零改动）+ 证据 JSONL——这是"Stable 执衡修复自身一个真实缺陷"的**真实闭环**，非 mock。
2. **架构缺口**：§68 完整语义"Stable 可以创建任务/调度 Worker/搜索成熟方案/修改 Candidate/运行测试/生成 Evidence/调用独立 Review/推进 Candidate"——当前只有"缺陷→goal 转换 + fixlet 修复测试"，无"Stable 调度 Worker 改 Candidate"全链（A1/D4 是独立模块未与 self_heal 接线）。

综合：❌ → 🟡（L1 自举真实，完整自举留 L3/后续迭代）。

### 4.5 §3 全自动（A1 接线架构是否支撑全自动闭环）—— **🟡 待L3（确认）**

**判断：A1 提供了全自动闭环的调度接线骨架，架构方向正确；但"全自动"的完整体验必须真实 Worker/R 会话 + 真实目标（L3）。**

- A1 relay_autopilot 状态机（submit/drive/status/validate-event/reset-sandbox）+ L2 沙箱全链重放（goal→BUILDER_READY→claim→work→report→R PASS/REWORK→wrap）+ R 单点排队（并发度=1）+ REWORK 自动重排队 + WAITING_REVIEW 不阻塞 + 单实例锁（DEF-A1 已修复）——**接线骨架真实**。
- 但 §3 的 31 步中"①理解真正目标→⑤恢复已有项目状态→⑩-⑬选 Brain/Worker/工具/分配成本→⑭执行浏览器和本地操作→⑮并行生产→⑳C 纠偏→㉗-㉙换 Worker/模型/工具→㉚换路线→㉛交付真实成果"多数环节在 autopilot 状态机中只有占位/未接线（真实 C 纠偏、真实成本分配、真实换 Worker 等未挂进状态机）。
- **架构结论**：A1 是 §3 的必要前置（自动流转接线完成），非充分（全自动体验需 L3 真实会话 + 状态机扩线）。**确认 🟡 待L3**。

### 4.6 §34 Split Brain —— **🟡（保持，本线未交付）**

- 任务指示明确"本线未交付，应保持 🟡/❌ 并注明"。架构确认：D4 epoch 是任务级授权代（STALE_EPOCH 拒收），非 §34 要求的 Controller 级 Lease/Generation/Fencing Token；中继锁（relay.lock）存在但"旧 Controller 未死、新 Controller 接管"的双写竞争实测缺失。**判定 🟡（不升 ✅），L3 前置：双 Controller 竞争沙箱演练**。

---

## 5. 本线覆盖升 ✅ 清单（13 节 + 1 节 ❌→✅）与理由摘要

| 节 | 升 ✅ 理由 | 归属交付 |
|---|---|---|
| §14 | OS 级非 AI 守护真实（计划任务/心跳/杀树重启/单实例锁/动态端口） | R1 |
| §16 | WAIT 局部性双机制 + L2 端到端实测 | A1+D4 |
| §19 | NO_PROGRESS 双通道真实（计数器 + SAFE_HALT 触发） | ec_lite+D2 |
| §2 | ETC 核算机制真实（数学验证 + registry 数据面） | D2 |
| §23 | STOP→REVOKED→拒收旧结果端到端实测 | D4 |
| §40 | epoch 单调 + STALE_EPOCH 拒收 | D4 |
| §41 | User Override 最高优先级端到端实测 | D4 |
| §48 | Reuse 门禁强制（BUILD_BLOCKED exit 1 实测） | D3 |
| §49 | Reuse Decision 结构化留痕 + ndjson | D3 |
| §50 | Reuse≠Trust（evidence + failed_approach_warning + supply_chain） | D3 |
| §61 | SAFE_HALT 真实触发 1 次（三条件状态机） | D2 |
| §65 | 四动词唯一入口真实 + 一页卡 | R3 |
| §73 | 3 缺失行全补齐（Supply Chain/成本调度/Lifecycle 守护） | R1+D2+D3 |
| §63 | registry 机器可读 + 被多模块真实消费（❌→✅） | R2+D2+D5 |

---

## 6. 与 QA 复核可能的差异节（预判，供主理人合并参考）

| 节 | 我的判定 | 可能的 QA 判定 | 差异原因（架构 vs 机器视角） |
|---|---|---|---|
| §63 | ✅ | 可能 ✅ | registry 被真实消费（grep + 亲跑证实）是硬证据，应一致 |
| §58 | 🟡 | 可能 ✅ 或 🟡 | 我强调"验证式非执行时强制"——若 QA 以"机制存在+L2 实测"判 ✅，需合并讨论：§58 生产级隔离是否必须在 v4 内达成 |
| §17 | 🟡 | QA 已 APPROVED D5，可能 ✅ | 我强调"运行中新发现自动纳入 Task Graph"闭环缺 + 拆解粒度不稳定（本审核亲跑 1 节点 vs QA 5 节点） |
| §18 | 🟡 | 可能 ✅ | 我强调 AI Execution View 字段覆盖不全（缺 locks/retry/next_action/evidence） |
| §70 | 🟡 | 可能 ✅ | 我强调"统一可查询 Trace 接口"缺，QA 可能以字段已补判 ✅ |
| §30 | 🟡 | 可能 ✅ | 我强调全角色 stale 绑定未全覆盖（仅 Worker 执行结果） |
| §38 | 🟡 | 可能 ✅ | 我强调 Reconcile/Inspect Reality 全链未实现（仅"标记+决策入口"） |
| §7 | 🟡 | 可能 ✅ 或 🟡 | 我强调选 Worker/工具/重规划未实现（brain-pick 只选 Brain） |
| §60 | 🟡 | 可能 ✅ 或 🟡 | 我强调 L3-L9 自动升级链未实现（仅 README 映射） |
| §71 | 🟡 | 可能 ✅ 或 🟡 | 一页卡+视图真实但统一进度视图缺（与 §18 同源） |

合并原则建议：**判定以"机制真实性 + 完整性 + L2 证据"为准**；凡缺口是"真实闭环未接线/未实现"而非"未触发"，应保持 🟡；凡缺口仅是"L3 真实环境未跑"，按硬规则保持 🟡 待L3。两文件若有冲突，以较严判定为准（主报告 §4 原则）。

---

## 7. L3 清单（架构视角补充，与 QA 对照）

### 7.1 主报告已列 4 项（§3 真实目标、§4 真实交付、§5 真实 Provider、§74 终裁）
- §3：真实弱模型会话（混元3/豆包）走 A1 全自动 1 次（含真实目标）——**需要：弱模型会话 + 真实目标文本 + 额度**
- §4：真实用户级交付链（真实目标→Artifact→Evidence→Acceptance）1 次
- §5：真实 Provider 替换（LiteLLM→DeepSeek/OpenAI key 注入）——**需要：API key + 环境变量配置步骤**
- §74：业主终裁（12 条全满足声明）

### 7.2 架构视角补充的 L3 前置条件
| # | 前置 | 说明 | 归属节 |
|---|---|---|---|
| 1 | **autopilot 状态机扩线** | A1 当前只接线 goal→work→report→R→wrap；需挂接真实 C 纠偏（strategic_correction）、成本分配（cost_router route 消费）、换 Worker（worker_adapter fallback）后才算 §3 全自动 | §3 |
| 2 | **registry 主链驱动** | r_adapter/worker_adapter 改由 capability-registry.json 驱动（或至少 provider 条目加 cost_ref/quota_ref 引用），使 §59 路由决策可被调度消费 | §59/§63 |
| 3 | **双 Controller 竞争沙箱演练** | §34 需真实/沙箱双 Controller 并发场景（旧 Controller 未死+新接管）验证 Fencing | §34 |
| 4 | **真实多 Worker 生产并行** | §56/§57/§58 需 2+ 真实 worker 并行跑真实任务（含锁冲突与隔离） | §56/§57/§58 |
| 5 | **真实断网对账场景** | §38 需真实 OUTCOME_UNKNOWN（如点击发布后断网）走 Reconcile 流程 | §38 |
| 6 | **生产阈值校准** | cost_policy.json 预算阈值（当前 0.5 对 strong 档偏紧，OBS-D2）按真实价目校准 | §59/§61/§2 |
| 7 | **§55 接入主链** | context_sufficiency 五分支路由挂到真实 Brain 调用前检查点（autopilot/runtime） | §55 |
| 8 | **SAFE_HALT 人工处置 SOP** | 真实 SAFE_HALT 触发后的人工 reset 流程文档化（含预算调整） | §61 |

---

## 8. 遗留问题与观察项（非阻塞）

1. **OBS-D6-1（Task Graph 拆解粒度不稳定）**：本审核亲跑 `build --goal-file "完成季度报告：收集销售数据、制作演示材料、撰写总结文档"` 仅产出 1 节点（T01 整目标），而 QA 亲跑 D5 报告 5 节点——规则式拆解对文本形态敏感，粒度不可控。**影响**：§17/§7 的"拆任务"质量依赖目标文本措辞，L3 真实目标可能拆出过粗 Task Graph。建议 D6 后迭代增强拆解规则（并列连词/动作识别）。
2. **OBS-D6-2（state/goals/ 目录出现 5 个 goal 文件）**：`state/goals/` 时间戳 18:28-18:37 与本次复核并行——推测为 QA 复核人（software-qa-d6）self_heal convert 产物（untracked）。非本人操作，建议主理人确认归属并决定是否入 evidence。
3. **OBS-D6-3（r_adapter/worker_adapter 未 registry 驱动）**：见 §7.2-2，D1 ARCH 已记录 DEF-4，建议 L3 前对齐。
4. **OBS-D6-4（R3 work 委托层 r-url 参数被忽略）**：R3 ARCH D1 已记录，低危，建议随 D6/L3 修复（透传或删参）。
5. **OBS-D6-5（OBS-D4 mock exit_code=None 映射 FAILURE）**：D4 QA 已评估"可留"，不影响 §38 判定（真实 OUTCOME_UNKNOWN 通道可用）。
6. **OBS-D6-6（R1 双 watcher 竞态窗口）**：R1 ARCH D4 已记录（P2 架构性残余，分层守护已缓解），非本线范围。

---

## 9. 会签结论

**判定：APPROVED（会签通过，附 L3 前置清单）**

- 机器复核亲跑全绿：doctor DRIFT_FREE、权威矩阵 36/36、14 项 CLI 冒烟全部通过；
- 77 节独立判定：**54 ✅ / 23 🟡 / 0 ❌**（与主报告 §4 重判 40/30/7 相比：+14 升 ✅（13🟡+1❌）、7 个 ❌ 全部消除（6 升 🟡 + 1 升 ✅））；
- 硬规则遵守：§3/§4/§5/§74 保持 🟡 待 L3，未因 mock 宣称 ✅；
- 边界节架构判断：§58/§59/§68 判 🟡（机制真实但闭环缺）、§63 判 ✅（机器可读可消费亲跑证实）、§34 保持 🟡（本线未交付）；
- 本文件为架构复核独立稿，正式 v4 由主理人合并 QA 文件（软件-qa-d6）后定稿；若 QA 已产 DEFINITION-77-SECTIONS-V4.md，请主理人按 §6 差异节核对后合并。

*审核记录：高见远（software-architect-d6），2026-08-30。本审核为只读复核，唯一写入=本检查点文件；未 push；未跑真实 AI/真实目标。*
