# 核心定义 77 节逐条对照终稿 v4（2026-08-30 · D6 终验 QA 机器复核稿）

- 复核人：software-qa-d6（严过关，D6 终验 QA 复核实例，矩阵 v4 复核人之一）
- 日期：2026-08-30
- 分支：v1.1-blackbox（HEAD=b74f9d8，dev head → D5 完成）
- 解释器：Python312（`C:\Users\17838\AppData\Local\Programs\Python\Python312\python.exe`）
- 依据：宪法 `docs/canon/ZHIHENG_FINAL_DEFINITION_FINAL_CANONICAL.md`（77 节 §0-§76，SHA256 `4c05a21f…9a4a`，git blob 零修改）；旧矩阵 v3 `docs/evidence/DEFINITION-77-SECTIONS-FINAL.md`；主报告 `docs/SUCCESSOR-MASTER-REPORT-20260830.md` §4 独立重判（40✅/30🟡/7❌）
- 复核方法：逐节核对宪法原文 + 本开发线交付（R1/R2/R3/A1/D1-D5）+ 审核记录（docs/evidence/reviews/REVIEW-*.md）+ 本人亲跑机器验证（doctor/权威矩阵/全量测试/13 项 CLI 冒烟）；只读复核，唯一写入 = 本矩阵 v4 文件 + 会签检查点 REVIEW-D6-2026-08-30-QA.md
- 图例：✅ 完全满足（实现 + 测试 + 机器验证充分，L1/L2 完成）/ 🟡 部分满足（机制在，缺闭环或待 L3）/ ❌ 未满足
- **硬规则（§8b）**：依赖 L3 真实实测的节（§3 全自动真实目标、§4 真实交付、§5 真实 Provider 替换、§74 终裁）保持 🟡 并注明"待 L3（业主）"，不得因 mock 宣称 ✅
- **会签说明**：本文件为 QA 独立复核稿；架构复核人（software-architect-d6）另有独立稿 REVIEW-D6-2026-08-30-ARCH.md（54✅/23🟡/0❌），两稿差异节见 §7，由主理人合并定稿

---

## 0. 结论速览

**77 节 v4 独立判定（QA 复核稿）：67 ✅ / 10 🟡 / 0 ❌（合计 77）**

| 变化 | 节数 | 明细 |
|---|---|---|
| 保持 ✅ | 40 | 主报告 §4 ✅ 集合不变（§0,1,6,9,10,12,13,15,21,22,24,25,26,27,28,29,31,32,33,35,36,37,39,42,43,44,45,46,47,52,53,54,62,64,66,67,69,72,75,76） |
| 🟡 升 ✅ | 22 | §2,14,16,17,18,19,23,30,34,38,40,41,48,49,50,56,57,61,65,70,71,73（本线交付直接补足缺口，L1/L2 机器验证充分） |
| ❌ 升 ✅ | 5 | §55,58,59,63,68（机制真实落地 + 机器验证充分） |
| ❌ 升 🟡 | 2 | §3（A1 接线完成，真实目标未走 → 待 L3）、§51（依赖漏洞扫描实现，其余维度未系统化） |
| 保持 🟡 | 8 | §4,5,7,8,11,20,60,74（其中 §4/§5/§74 = 待 L3（业主）；§7/§8/§11/§20/§60 = 机制在缺闭环/扩展） |

**7 个原 ❌ 节新判定**：§3 → 🟡 待 L3；§51 → 🟡；§55 → ✅；§58 → ✅；§59 → ✅；§63 → ✅；§68 → ✅

---

## 1. 本人亲跑机器验证记录（全部 Python312，实跑）

| # | 验证项 | 命令 | 结果 |
|---|---|---|---|
| 1 | doctor 体检 | `python scripts/state_doctor.py` | **DRIFT_FREE** ✅ |
| 2 | 权威矩阵 | `python runtime/test_v09_attack_matrix_on_b1_core.py` | **36/36 MATCH**（R1-R36 + R34-FAITHFUL 全 MATCH）✅ |
| 3 | 自举矩阵 | `python runtime/test_v09_attack_matrix_offline.py`（D5 修复后） | **1 test OK（36/36 断言）** ✅ |
| 4 | 全量测试抽查 | `python -m unittest discover -s runtime -p "test_*.py"` | **Ran 540 tests, errors=8**（8 ERROR 为既有环境基线：test_harness_verify_offline 2 + test_v08_adapter_evidence_offline 5+1，均 T0/v0.8 遗留文件，本线零改动）✅ |
| 5 | R1 守护计划任务 | `schtasks /query /tn ZhihengGuard` | 存在，模式=就绪，下次运行 2:39 ✅ |
| 6 | R2 注册表校验 | `python docs/ops/registry-validate.py` | PASS（15/15 节/104 条/24 非阻断 warning）exit=0 ✅ |
| 7 | R2 注册表消费 | `python docs/ops/registry-launch.py` | summary 输出 + production.json cross-check ok:True ✅ |
| 8 | R3 黑箱 HUMAN_GATE | `python runtime/blackbox_bridge.py human-gate` | total_scanned=118, waiting_count=12, exit=0 ✅ |
| 9 | A1 自动调度 | `python scripts/relay_autopilot.py status` | 2 runs WRAPPED（A1 L2 残留真实状态）、inbox_pending=0、exit=0 ✅ |
| 10 | D1 R-Adapter | `python runtime/adapters/r_adapter.py health --config r_adapter.config.example.json` | 4 providers 全 UNCONFIGURED（无 key 正确短路，零网络副作用）exit=0 ✅ |
| 11 | D2 成本路由 | `python runtime/cost_router.py route --goal "机械读取配置文件并格式化输出" --rework-risk low` | ALLOWED, recommended=weak, ETC=0.05, exit=0 ✅ |
| 12 | D2 SAFE_HALT 证据 | `state/cost_router_state.json` | history=3（BUDGET_BREACH/CONSECUTIVE_BREACH/NO_PROGRESS）✅ |
| 13 | D3 Reuse 门禁 | `python scripts/reuse_gate.py check --task "浏览器自动化下载文件能力" --search playwright download` | ok=true, GATE_OK ✅ |
| 14 | D3 Supply Chain | `python scripts/supply_chain_check.py check` | ok=true, pip_audit available=true ✅ |
| 15 | D3 浏览器 | `python runtime/browser_adapter.py search --query test --mock` | ok=true, engine=mock, result_count=5 ✅ |
| 16 | D4 并行调度 | `python runtime/parallel_scheduler.py status` | ok=true, mode=mock, exit=0 ✅ |
| 17 | D5 自举 | `python runtime/self_heal.py list` | fixlets=[SH-001] 注册 ✅ |
| 18 | D5 Task Graph | `python runtime/task_graph.py build --goal-file <临时> ` | valid=true, 2 节点（拓扑/并行输出正确）✅ |
| 19 | D5 Context Sufficiency | `python runtime/context_sufficiency.py route --context <json> --required-file <json>` | decision=SWITCH_LOCAL_BRAIN, ratio=0.5（五分支真实触发）✅ |

补充取证：
- git log：R1(4157cb2)/R2(a35bced)/R3(4f151c4)/A1(ecd5cc9)/D1(f80613e)/D2(db4ac31)/D3(f0b9c6d)/D4(b5ffc9e)/D5(02d5c72) 提交全部存在；HEAD=b74f9d8（governance-only sync）✅
- 宪法零修改：`git show HEAD:docs/canon/…` SHA256 = 4c05a21f…9a4a ✅
- 8 ERROR 文件基线确认：`git log -- runtime/test_harness_verify_offline.py runtime/test_v08_adapter_evidence_offline.py` 最后一次改动在 v0.8/b3（59c3794），本线零改动 ✅

---

## 2. 逐节判定表（§0-§76）

### §0-§10

| 节 | 内容 | v4 | 依据（交付 + 测试/证据） | 待办 |
|---|---|---|---|---|
| §0 | 最高原则（AI 会错，靠系统防错） | ✅ | fail-closed 机制（ec_lite/effect_safety_lite）+ 权威矩阵 R31-R34 实测 FAIL_CLOSED | — |
| §1 | 产品本质 | ✅ | 系统即此（目标驱动/成本感知/可替换生产系统） | — |
| §2 | 为什么存在（成本感知） | ✅ | **D2**：cost_router.py Expected Total Cost 核算（57/57 测试 + ETC 手算 3 例吻合 + 亲跑 route ETC=0.05）；主报告缺口"无 ETC 核算"已补 | 生产阈值校准（L3 前置，见 §6-6） |
| §3 | 最终体验（给目标做完） | 🟡 待 L3 | **A1**：relay_autopilot.py 状态机接线完成（inbox→RUN→work→report→R→wrap，L2 沙箱全链 + 排队 + REWORK 公平性，REVIEW-A1 APPROVED）；**但真实弱模型会话 + 业主真实目标未走 §3 全自动** | **待 L3（业主）**：真实目标走 §3 全自动（前置见 §6-3） |
| §4 | 生产系统（Artifact+Evidence+Acceptance） | 🟡 待 L3 | Artifact/Evidence 机制在（RUN/state/reply/证据目录）；**真实用户级交付 Acceptance 链未走** | **待 L3（业主）**：真实交付 + 正式 Acceptance（§6-2） |
| §5 | Provider 独立 | 🟡 待 L3 | **D1**：R-Adapter（LiteLLM 多 Provider 仲裁/fallback）+ Worker-Adapter（CLI 泛化协议）实现，Python312 44/44 绿 + mock 全链（REVIEW-D1 APPROVED）；**真实 Provider 调用需 API key，未实测替换** | **待 L3（业主）**：真实 Provider 替换（§6-2）；r_adapter/worker_adapter 未 registry 驱动（对齐项） |
| §6 | 核心角色 | ✅ | O/B/C/R/EC/Runtime 全在案（V1.0 收口） | — |
| §7 | Brain | 🟡 | **D5**：task_graph.py brain-pick 规则式选 Brain（按复杂度）+ build_from_goal 规则式拆解；**选 Worker/选工具/重规划/处理复杂问题未实现** | 拆解粒度质量待真实目标校准（L3 观察 OBS-D6-1）；Worker/Tool 选择后续迭代 |
| §8 | C 纠偏 | 🟡 | strategic_correction 契约 PASS + 15 次判定（V1.0）；**独立 C 常态化未建**（D5 未覆盖） | 独立 C 常态化接线（后续） |
| §9 | C 的独立性 | ✅ | C 独立于执行链观察视角（strategic_correction 契约） | — |
| §10 | Worker | ✅ | 累计 8 次真实 GOAL（3+5，V1.0 收口） | — |

### §11-§20

| 节 | 内容 | v4 | 依据（交付 + 测试/证据） | 待办 |
|---|---|---|---|---|
| §11 | EC 执行纠偏 | 🟡 | ec_lite.py（含 NO_PROGRESS 检测）机制在 + 测试绿；**真实触发案例少**（D5 未覆盖） | 真实触发案例积累（后续） |
| §12 | R 独立审查 | ✅ | 8 个真实 GOAL 终审全 PASS（16 轮 REWORK 判定：4+12，V1.0） | — |
| §13 | 三纠错不混淆 | ✅ | EC≠C≠R 分置（V1.0） | — |
| §14 | Lifecycle Controller | ✅ | **R1**：guard_all.cmd OS 级计划任务 ZhihengGuard（每 2 分钟，心跳 >300s 判死→杀树→重启→记账，bsk 动态端口 52800）+ schtasks 存在实证 + 全链路自愈实测（REVIEW-R1 APPROVED + 复审 APPROVED）；非 AI 守护与 AI 会话解耦成立 | 双 watcher 竞态窗口（R1 ARCH 记录 P2，分层守护已缓解） |
| §15 | 跨回合自动继续 | ✅ | 多轮 REWORK 自动重交（V1.0 16 轮判定）+ **A1** REWORK 自动重排队（REVIEW-A1） | — |
| §16 | WAIT 是 Task State | ✅ | **A1**：B REVIEWING 时 C 推进到 REPORTED（WAITING_REVIEW 不阻塞队列实测）+ **D4**：LOCK_WAITING/WAIT 不阻塞其余 READY（24/24 测试） | — |
| §17 | Task Graph | ✅ | **D5**：task_graph.py 节点（依赖/parallel_with/Owner/state/subtasks）+ 拓扑/关键路径/并行组/环检测/动态加任务 + self_heal convert（运行中新发现→任务）；d5 测试 40/40（REVIEW-D5 APPROVED） | 拆解粒度对目标文本敏感（OBS-D6-1，L3 真实目标校准） |
| §18 | Task Graph 双视图 | ✅ | **D5**：task_graph.py _human_view 派生投影（一个真源两种投影）+ brain_bridge human_view + **R3** result/human-gate 用户视图命令 | — |
| §19 | NO_PROGRESS | ✅ | **D2**：cost_router simulate-rework 真实触发 NO_PROGRESS SAFE_HALT（state history 第 3 条）+ ec_lite DEFAULT_NO_PROGRESS_ACTIONS=50 + **A1** --max-reworks 防无限循环 | — |
| §20 | 浏览器通用面 | 🟡 | **D3**：browser_adapter.py search/fetch/download 已实现（download 真实 559 字节成功，REVIEW-D3 APPROVED + 亲跑 mock search 5 结果）；**点击/输入/滚动/表单/上传/视频网站/管理后台/标签页/窗口/登录态/等待/动态页面/保存结果/视频播放控制等未实现**（部分由 bsk/CDP 承接但非 adapter 命令） | 通用网页操作扩展（L3/后续）；真实浏览器自动化留 L3 |

### §21-§30

| 节 | 内容 | v4 | 依据（交付 + 测试/证据） | 待办 |
|---|---|---|---|---|
| §21 | 本地执行面 | ✅ | run.cmd + 手册 + registry capabilities 本地 9 条（V1.0/R2） | — |
| §22 | Goal Contract | ✅ | goal_contract_lite.py（V1.0） | — |
| §23 | 目标变化失效旧权 | ✅ | **D4**：parallel_scheduler STOP/REVOKE directive → REVOKED + 后续结果拒收（端到端实测 exit=2, REVOKED_EPOCH, 旧结果保留拒收，REVIEW-D4 APPROVED） | — |
| §24 | AI 记忆非 Truth | ✅ | capsule 机械投影（V1.0 13 测试） | — |
| §25 | 项目真源 | ✅ | PROJECT_STATE.* 唯一真源 + doctor DRIFT_FREE 校验（主报告升 ✅） | — |
| §26 | 当前进展 | ✅ | PROJECT_STATE 回写（主报告升 ✅） | — |
| §27 | Context Capsule | ✅ | capsule_bridge 接入（V1.0 13 测试） | — |
| §28 | 决策理由保存 | ✅ | D001-D022 账本（V1.0 + 开发线） | — |
| §29 | Canonical State Revision | ✅ | state revision 自增 + --verify（V1.0） | — |
| §30 | Stale Result Safety | ✅ | **D4**：parallel_scheduler 心跳超时 → STALE 回收 + STALE_HEARTBEAT 拒收 + 释放资源锁（端到端实测，REVIEW-D4 APPROVED）；主报告缺口"通用 stale 检测部分"已补 | 真实场景积累（L3 可选） |

### §31-§40

| 节 | 内容 | v4 | 依据（交付 + 测试/证据） | 待办 |
|---|---|---|---|---|
| §31 | State 可恢复 | ✅ | state.json 唯一权威 + verify（V1.0） | — |
| §32 | Control Plane Trust | ✅ | 主报告升 ✅（Controller TCB 封印 gen1 VERIFIED） | — |
| §33 | Authority 模型 | ✅ | scoped_authorization（V1.0） | — |
| §34 | Split Brain 防护 | ✅ | **D4**：epoch 单调 + STALE_EPOCH 裁决（回滚/复活的低 epoch 结果拒绝）+ SingleInstanceLock（mkdir 原子互斥）；裁决顺序 STALE_EPOCH→REVOKED_EPOCH→… 测试覆盖（REVIEW-D4 APPROVED） | 真实双 Controller 竞争实测留 L3（§6-4） |
| §35 | Identity Binding | ✅ | RUN 绑定（主报告升 ✅） | — |
| §36 | Effect 追踪 | ✅ | effect_safety_lite（主报告升 ✅） | — |
| §37 | Effect Write-Ahead | ✅ | 主报告升 ✅ | — |
| §38 | OUTCOME_UNKNOWN | ✅ | **D4**：显式 outcome=OUTCOME_UNKNOWN → state=OUTCOME_UNKNOWN + decision_entry=MANUAL_OR_RETRY（不自动判定成败，端到端实测 exit=2，REVIEW-D4 APPROVED） | 真实断网对账场景留 L3（§6-5） |
| §39 | 权限非聊天记忆 | ✅ | 主报告升 ✅（scoped_authorization 非记忆） | — |
| §40 | Revocation 单调性 | ✅ | **D4**：epoch 单调递增 + STALE_EPOCH 拒收（test_epoch_monotonic_increases 断言 1→2；回滚/复活低 epoch 拒绝，REVIEW-D4 APPROVED） | — |

### §41-§50

| 节 | 内容 | v4 | 依据（交付 + 测试/证据） | 待办 |
|---|---|---|---|---|
| §41 | User Override 最高 | ✅ | **D4**：STOP/PAUSE/CHANGE GOAL/REVOKE 最优先 → REVOKED_EPOCH 拒收被撤销代结果（端到端实测，REVIEW-D4 APPROVED） | — |
| §42 | 证据非自证 | ✅ | R 独立 + 机器验证（V1.0） | — |
| §43 | Review 绑定 | ✅ | RUN↔commit（V1.0） | — |
| §44 | 机器验证 | ✅ | 权威矩阵 36/36 + 540 测试（8 ERROR 基线非本线）+ doctor DRIFT_FREE（亲跑） | — |
| §45 | 状态层级 | ✅ | DISCUSSED..PRODUCTION_VERIFIED 分级（V1.0） | — |
| §46 | 外部内容 | ✅ | External Content = UNTRUSTED DATA（V1.0） | — |
| §47 | Prompt Injection 防护 | ✅ | 实现（V1.0） | — |
| §48 | Reuse Gate | ✅ | **D3**：reuse_gate.py 四步流程 + BUILD_BLOCKED 强制门禁（无 Decision 记录 → exit 1 实测，record 后 → GATE_OK，REVIEW-D3 APPROVED）；主报告缺口"流程走过但无系统级强制"已补 | — |
| §49 | Reuse Decision | ✅ | **D3**：record 结构化留痕（task/decision/evidence/note/gate_check_summary/failed_approach_warning）+ --require-decision 门禁；主报告缺口已补 | — |
| §50 | Reuse 不等于 Trust | ✅ | **D3**：decision 含 evidence + failed_approach_warning（已失败路线衔接）+ supply_chain 依赖检查补充；外部方案默认不可信 | — |

### §51-§60

| 节 | 内容 | v4 | 依据（交付 + 测试/证据） | 待办 |
|---|---|---|---|---|
| §51 | Supply Chain Gate | 🟡 | **D3**：supply_chain_check.py 依赖漏洞扫描（pip-audit 真实扫描，vulns=0，source=PyPI/LOCAL 标注，亲跑 available=true；测试 32/32，REVIEW-D3 APPROVED）；**§51 十维度仅 Dependencies+Source 覆盖，Maintainer/Maintenance/License/Install Script/Startup Script/Requested Permissions/Network Behavior/Suspicious Behavior 未系统化** | 十维度清单扩展（后续/L3） |
| §52 | Secret Isolation | ✅ | 敏感清单零入仓（V1.0 + 各刀凭据 grep 零命中） | — |
| §53 | Credential Store | ✅ | 凭据路径登记不复制（V1.0 + R2 registry login_state 6 条 CREDENTIAL_REFERENCE） | — |
| §54 | Data Egress | ✅ | effect_safety_lite（V1.0） | — |
| §55 | Context Sufficiency | ✅ | **D5**：context_sufficiency.py 五分支（SWITCH_LOCAL_BRAIN/SWITCH_ALLOWED_PROVIDER/DESENSITIZE_RETRY/HUMAN_AUTHORIZATION/BLOCKED）+ 策略阈值 + 脱敏 + 阻塞语义；14/14 测试 + 亲跑 SWITCH_LOCAL_BRAIN（ratio=0.5），REVIEW-D5 APPROVED | 接入主链（autopilot/runtime 调用前检查点，L3 前置可选） |
| §56 | 多 Worker | ✅ | **D4**：parallel_scheduler 并发分派（max_concurrent）+ 资源声明 + 结果对应；24/24 测试 + 3 任务争锁全 COMPLETED（REVIEW-D4 APPROVED）；**L2 测试内模拟充分** | **真实多 Worker 生产并行留 L3（业主）**（§6-4） |
| §57 | Resource Lock | ✅ | **D4**：ResourceLockManager（每资源 mkdir 原子互斥 + 冲突排队 LOCK_WAITING 不失败）+ SingleInstanceLock（吸取 A1 DEF-A1 教训正确实现）；测试覆盖（REVIEW-D4 APPROVED） | 真实冲突场景留 L3（§6-4） |
| §58 | Project Isolation | ✅ | **D4**：每任务独立 work_dir + 越界写校验（SANDBOX_VIOLATION 端到端实测 exit=2）+ symlink 逃逸扫描；REVIEW-D4 APPROVED；主报告 ❌"无系统实现"已消除 | 真实多 Project 并发留 L3（§6-4） |
| §59 | Cost Routing | ✅ | **D2**：cost_router.py 三档路由（weak/hybrid/strong）+ ETC（几何级数 retry 成本 + goal_type/rework_risk 难度）+ 57/57 测试 + ETC 手算 3 例吻合 + 亲跑；主报告 ❌"无系统实现"已消除 | 生产阈值按真实价目校准（L3 前置，§6-6） |
| §60 | Escalation Ladder | 🟡 | **D5**：README §6 实现 L0-L2（Task Graph/缺陷→任务转换器/§55 路由）+ L3-L9 映射存档；**9 级阶梯仅前 3 级落地** | L3-L9 逐级实现（后续） |

### §61-§70

| 节 | 内容 | v4 | 依据（交付 + 测试/证据） | 待办 |
|---|---|---|---|---|
| §61 | Hard Fuse | ✅ | **D2**：SAFE_HALT 三条件（BUDGET_BREACH/CONSECUTIVE_BREACH/NO_PROGRESS）真实触发 3 次（state/cost_router_state.json history=3 亲跑确认）+ FROZEN 拦截 + reset 解冻（REVIEW-D2 APPROVED）；主报告缺口"SAFE_HALT 从未真实触发"已补 | SAFE_HALT 人工处置 SOP（后续，§6-8） |
| §62 | Safety > Liveness | ✅ | fail-closed 矩阵 R31-R34 实测（主报告升 ✅） | — |
| §63 | Capability Registry | ✅ | **R2**：config/capability-registry.json 机器可读（15 节对应 §63 十五项 + role_bindings，104 条目）+ registry-validate.py（PASS/负向 5/5）+ **被运行时真实消费**（cost_router 读 costs 节、context_sufficiency 读 brains/providers 节、reuse_gate local_registry_search、registry-launch cross-check ok:True，亲跑确认）；主报告 ❌"手册入仓≠机器可读注册表"已消除 | — |
| §64 | Tool Manual | ✅ | operator_manual + 用户指南 + 各刀 README（V1.0/开发线） | — |
| §65 | 唯一入口 | ✅ | **R3**：blackbox_bridge.py RESULT/HUMAN_GATE + work/report 委托 + blackbox-card.md 一页操作卡（"一个入口、四个动词、五步操作"，亲跑 human-gate/result）；弱 AI 输入面压窄到一页卡 | 四动词收敛为单一命令载体（桥升级方向，R3 OBS-2 过渡态）；弱模型实测 L3 |
| §66 | Stable/Candidate | ✅ | StableLineage 8 测试绿（V1.0） | — |
| §67 | Rollback | ✅ | lineage.rollback（V1.0） | — |
| §68 | 自举 | ✅ | **D5**：self_heal.py 缺陷→goal 转换器 + 自愈管线 + fixlet SH-001 **L1 真实案例**（test_v09_attack_matrix_offline.py FAILED→36/36，权威矩阵字节零改动，REVIEW-D5 APPROVED + 亲跑 offline 矩阵 OK）；"Stable 参与开发 Candidate" L1 成立 | 全 L2/L3 自举迭代（后续）；state/goals/ 产物归属确认 |
| §69 | 每阶段可用产品 | ✅ | 累计 8 次真实 GOAL（V1.0） | — |
| §70 | Trace | ✅ | **D5**：所有输出带 trace:{model, ai, tool, reason_retry, cost}（主报告缺口"哪个 AI/Tool/为何 Retry/成本"已补）+ 各刀账本（guard-actions/autopilot-actions/self_heal_events/reuse-decisions） | 全字段聚合视图（后续可选） |

### §71-§76

| 节 | 内容 | v4 | 依据（交付 + 测试/证据） | 待办 |
|---|---|---|---|---|
| §71 | 简洁 UI | ✅ | **R3**：blackbox-card.md 一页操作卡 + blackbox_bridge result/human-gate（用户可见：当前状态/进度/重要阻塞/human-gate 清单/最终成果）；主报告缺口"无用户视图命令"已补 | 弱模型实测 L3 |
| §72 | 六个根 | ✅ | 全实现（Authority/Truth/Identity/Effect/Evidence/Lifecycle，V1.0） | — |
| §73 | 最终可靠性原则 | ✅ | 15 行逐条对应：Supply Chain（D3 supply_chain ✅）、成本调度（D2 cost_router ✅）、Lifecycle 守护（R1 guard ✅）三缺口全部补齐；其余行 V1.0 已对应 | — |
| §74 | 最终完成条件 | 🟡 待 L3 | 工程项达成（V1.0 封印 gen1 + §74 签字 + master 汇合）；**FINAL DONE 终裁待业主** | **待 L3（业主）**：终裁（§6-5） |
| §75 | 定义治理 | ✅ | 默认进 Roadmap 不改定义，已遵守（宪法零修改） | — |
| §76 | 最终一句话 | ✅ | 系统即此 | — |

---

## 3. 汇总（QA 复核稿）

| 档位 | 节数 | 明细 |
|---|---|---|
| ✅ 完全满足 | **67 节** | §0,1,2,6,9,10,12,13,14,15,16,17,18,19,21,22,23,24,25,26,27,28,29,30,31,32,33,34,35,36,37,38,39,40,41,42,43,44,45,46,47,48,49,50,52,53,54,55,56,57,58,59,61,62,63,64,65,66,67,68,69,70,71,72,73,75,76 |
| 🟡 部分满足 | **10 节** | §3(待L3),4(待L3),5(待L3),7,8,11,20,51,60,74(待L3) |
| ❌ 未满足 | **0 节** | — |

**合计 77 节全覆盖（§0-§76）。**

**待 L3（业主）4 节**：§3 全自动真实目标、§4 真实交付 Acceptance、§5 真实 Provider 替换、§74 终裁。
**机制在缺闭环/扩展 6 节**：§7 Brain（选 Worker/工具/重规划缺）、§8 独立 C 常态化、§11 EC 真实触发案例少、§20 浏览器操作扩展、§51 供应链十维度扩展、§60 升级梯 L3-L9。

---

## 4. 7 个原 ❌ 节判定变更说明

| 原 ❌ 节 | 主报告缺口 | v4 判定 | 变更理由 |
|---|---|---|---|
| §3 全自动 31 步 | 无全自动闭环 | 🟡 待 L3 | **A1** 状态机接线完成（L2 沙箱全链实测），但真实目标未走 §3 → 升 🟡 待 L3 |
| §51 Supply Chain | 无系统实现 | 🟡 | **D3** supply_chain_check.py 依赖漏洞扫描已实现（L2 机械部分），但 §51 十维度未全 → 升 🟡 |
| §55 Context Sufficiency | 无系统实现 | ✅ | **D5** 五分支全实现 + 14/14 测试 + 亲跑真实触发 → L1/L2 充分 |
| §58 Project Isolation | 无系统实现 | ✅ | **D4** work_dir 隔离 + SANDBOX_VIOLATION 端到端实测 + symlink 逃逸扫描 → L2 充分 |
| §59 Cost Routing | 无系统实现 | ✅ | **D2** ETC 路由 + 熔断 57/57 测试 + 手算吻合 → L2 充分（真实价目校准 L3 前置） |
| §63 Capability Registry | 手册入仓≠机器可读 | ✅ | **R2** JSON 15 节 104 条 + 被多模块真实消费（亲跑证实） |
| §68 自举 | V1.0 后启动 | ✅ | **D5** 自举 L1 真实案例（offline 矩阵修复 36/36，权威矩阵零改动） |

## 5. 🟡 升 ✅ 明细（22 节，本线交付直接补足）

- R1 守护：§14（非 AI 守护 + 心跳判死 + 计划任务）
- R2 注册表：§63（机器可读 + 被消费）
- R3 黑箱：§65（四动词 + 一页卡）、§71（用户视图命令）、§18（human_view 双视图投影）
- A1 自动调度：§16（WAITING_REVIEW 不阻塞队列）
- D2 成本路由：§2（ETC 核算）、§19（NO_PROGRESS 熔断）、§61（SAFE_HALT 真实触发 3 次）
- D3 Reuse/供应链/浏览器：§48（BUILD_BLOCKED 强制门禁）、§49（可追溯 Decision）、§50（Evidence+失败账本衔接）
- D4 并行：§23（STOP 旧权失效）、§30（Stale 回收）、§34（epoch fencing + 单实例锁）、§38（OUTCOME_UNKNOWN 不猜）、§40（epoch 单调）、§41（User Override 最高）、§56（L2 模拟并行）、§57（资源锁）
- D5 自举：§17（Task Graph 依赖图 + 动态加任务 + 环检测）、§70（trace 字段）、§73（三缺口补齐）

## 6. L3 清单（仍需业主，含前置条件）

| # | L3 项 | 对应节 | 前置条件 |
|---|---|---|---|
| 1 | **真实弱模型会话实测**（混元3/豆包级拿一页卡走黑箱） | §3/§4/§65/§71 | 业主开弱模型会话；R-PROD 通道健康（chatgpt_bridge status 实测确认，R-Adapter 完成前是单点）；四动词收敛单一载体（可选） |
| 2 | **真实 Provider API key 调用**（R-Adapter real 模式 → LiteLLM → 真 Provider；Worker CLI 适配器真实接入） | §5/§12/§63/§73 | 业主提供 API key；litellm 已装（Python312 已就绪）；r_adapter/worker_adapter 与 registry 对齐（D1 ARCH DEF-4 记录） |
| 3 | **业主真实目标走 §3 全自动**（A1 接线已完成，需真实目标端到端无人值守） | §3/§15/§16/§19 | 弱模型会话 + R 通道健康 + A1 L2 沙箱已绿；成本/额度业主确认 |
| 4 | **真实多 Worker 并行**（2+ 真实 worker 并行跑真实任务，含锁冲突与隔离） | §56/§57/§58/§34 | D4 L2 测试套件已绿；多个真实 worker 就绪；真实双 Controller 竞争实测同属此类 |
| 5 | **§74 终裁**（FINAL DONE 业主裁决） | §74 | 上述 L3 项完成 + 矩阵 v4 会签定稿（77/77 无 ❌）+ 业主验收 |

**非业主但后续（机器可继续）**：
- §20 通用网页操作扩展（click/input/form/upload 等 adapter 命令）
- §51 供应链十维度清单扩展（Maintainer/License/Network 等）
- §60 升级梯 L3-L9 逐级实现
- §7 Worker/Tool 选型 + §8 独立 C 常态化 + §11 真实触发案例积累
- 生产阈值校准（cost_policy 0.5 对 strong 档偏紧，OBS-D2）随真实价目
- §55 接入主链（autopilot/runtime 调用前检查点）
- SAFE_HALT 人工处置 SOP 文档化

## 7. 与架构复核稿（software-architect-d6）差异节

架构复核独立稿（REVIEW-D6-2026-08-30-ARCH.md）判定 54✅/23🟡/0❌，与 QA 稿（67✅/10🟡/0❌）差异集中在以下节（QA 判 ✅，ARCH 判 🟡），请主理人合并时按证据核对：

| 节 | QA 判定 | ARCH 判定 | QA 依据摘要 |
|---|---|---|---|
| §17/§18 | ✅ | 🟡 | task_graph.py 全实现 + human_view 投影 + self_heal convert（d5 40/40） |
| §30/§34/§38 | ✅ | 🟡 | D4 端到端实测（STALE/STALE_EPOCH/OUTCOME_UNKNOWN，24/24） |
| §55/§58/§59/§68 | ✅ | 🟡 | D5 五分支 / D4 隔离 / D2 ETC / D5 自举 L1 真实案例（各测试全绿 + 亲跑） |
| §56/§57 | ✅ | 🟡 | D4 L2 测试内模拟充分（任务指令明确"测试内模拟→✅"） |
| §70/§71 | ✅ | 🟡 | D5 trace 字段 / R3 用户视图命令（操作卡 + result/human-gate） |

两稿一致：§3/§4/§5/§74 保持 🟡 待 L3；§20/§51/§7/§8/§11/§60 保持 🟡；§63 升 ✅；§14/§16/§19/§2/§23/§40/§41/§48/§49/§50/§61/§65/§73 升 ✅。

## 8. 遗留问题与观察项（非阻塞）

1. **OBS-D6-Q1（Task Graph 拆解粒度不稳定）**：规则式拆解对目标文本形态敏感（ARCH OBS-D6-1 同观察），§17/§7 拆任务质量依赖措辞；L3 真实目标可能拆出过粗 Task Graph，建议 D6 后迭代增强拆解规则。
2. **OBS-D6-Q2（state/goals/ 出现 5 个 goal 文件）**：时间戳与 D6 复核并行，推测为 QA/ARCH 复核人 self_heal convert 产物（untracked）；建议主理人确认归属并决定是否入 evidence。
3. **OBS-D6-Q3（R3 work 委托层 r-url 参数被忽略）**：R3 ARCH 已记录，低危，建议随 D6/L3 修复（透传或删参）。
4. **OBS-D6-Q4（r_adapter/worker_adapter 未 registry 驱动）**：D1 ARCH DEF-4 记录，建议 L3 真实接入前对齐。
5. **OBS-D6-Q5（OBS-D4 mock exit_code=None 映射 FAILURE）**：D4 QA 已评估"可留"，不影响 §38 判定（真实 OUTCOME_UNKNOWN 通道可用）。
6. **OBS-D6-Q6（R1 双 watcher 竞态窗口）**：R1 ARCH 记录 P2 架构性残余，分层守护已缓解，非本线范围。
7. **OBS-D6-Q7（成本路由默认阈值 0.5 对 strong 档偏紧）**：D2 OBS-D2，L2 演示可接受，L3 真实价目校准。
8. **OBS-D6-Q8（全量测试 8 ERROR 基线）**：test_harness_verify_offline（ACC_PRODUCT_CONFIG_V3 515KB 超 Windows 32767 上限污染）+ test_v08_adapter_evidence_offline（git 环境依赖）为 T0/v0.8 遗留，本线零改动；建议后续清理环境或归档。

---

*复核记录：software-qa-d6（严过关），2026-08-30。本复核为只读复核，唯一写入 = 本矩阵 v4 文件 + REVIEW-D6-2026-08-30-QA.md；未 push；未跑真实 AI/真实目标（L3 留业主）。*

---

## 会签合并裁决（主理人 2026-08-31）

- 两稿：QA（software-qa-d6）67✅/10🟡/0❌（机器验证视角）；ARCH（software-architect-d6）54✅/23🟡/0❌（机制真实性视角）。本定稿以 QA 稿为统计主体，按主报告 §8b 口径（L1/L2 完成即可转 ✅、L3 依赖保持 🟡 注"待 L3"）合并。
- **合并结论：67 ✅ / 10 🟡 / 0 ❌**
- 差异节裁决（QA ✅ vs ARCH 🟡，13 节）：
  - 转 ✅ 并强化 L3 标注（架构师"真缺口"意见采纳为待办强化，不降级）：§34（双 Controller 竞争实测留 L3——D4 提供 epoch 单调+单实例锁机制）、§58（无 OS 级沙箱=验证式近似，真实并发留 L3）、§59（ETC 计算器未接线调度=advisory，生产校准+接线留 L3）、§17/18/30/38/55/56/57/68/70/71（L1/L2 完成充分，L3 项已注明）
  - 两稿一致：§3/§4/§5/§74 待 L3；§7/§8/§11/§20/§51/§60 保持 🟡；§63 升 ✅
- L3 待业主清单（8 项）：①真实弱模型会话（§3/§4/§65/§71）②真实 Provider key（§5/§12/§73）③真实目标走 §3 全自动 ④真实多 Worker 并行（§56/57/58/34）⑤真实断网对账（§38）⑥cost_policy 按真实价目校准（§59）⑦§55 挂真实 Brain 检查点 ⑧§74 终裁
