# 核心定义 77 节逐条对照 POST-MERGE 复核稿 v5（2026-09-01 · 合并后新 HEAD 体检）

- 复核人：WA（执行 AI，RUN-20260901-225346-9633），只读体检，非开发
- 日期：2026-09-01
- 基线：`docs/evidence/DEFINITION-77-SECTIONS-V4.md`（采信口径 63✅/14🟡/0❌）
- 复核对象：合并后 master HEAD **33a5311**（含 hardening 合流 + DeepSeek 双通道 + d3 激活 + 今日全部实弹记录）
- 图例：✅ 完全满足 / 🟡 部分满足 / ❌ 未满足
- 硬规则 §8b：§3/§4/§5/§74 未经业主 L3 实测/签字，永远不得升 ✅
- 方法：14 条 🟡 逐条重审（今日证据）；63 条 ✅ 抽查 ≥15 条（门禁/adapter/goal contract/runtime 优先）；机器验证（49 离线套 + tests 219 + b1_core + doctor + CLI 冒烟 + grep 接线）

## 0. 结论速览

**POST-MERGE 判定：63 ✅ / 14 🟡 / 0 ❌（与 V4 基线完全一致，无升降）**

> 数字是量出来的：今日证据（两轮真实 RUN、d3 激活、合流后套件全绿）均不足以让任何 🟡 升 ✅——
> §3/§4/§5/§74 受 §8b 硬规则约束不得升；§20 的 d3 激活仅覆盖 search/fetch/download 子项，click/input 等通用操作未实现；
> §7/§8/§11/§34/§51/§55/§59/§60/§68 对照 HEAD 无实质新进展（各自缺闭环真实成立）。✅ 抽查 15+ 无回退。

## 1. 逐节判定表（§0-§76，POST-MERGE）

| 节 | 内容 | V4 | V5 | 与 V4 差异 | 依据 |
|---|---|---|---|---|---|
| §0 | 最高原则（AI 会错，靠系统防错） | ✅ | ✅ | 保持 | fail-closed 机制 + 权威矩阵 R31-R34 实测 FAIL_CLOSED；test_v09_attack_matrix_offline PASS |
| §1 | 产品本质 | ✅ | ✅ | 保持 | 系统即此（目标驱动/成本感知/可替换生产系统） |
| §2 | Expected Total Cost | ✅ | ✅ | 保持 | cost_router ETC 核算（test_cost_router_d2_offline PASS） |
| §3 | 最终体验（给目标做完） | 🟡 | 🟡 | 保持 🟡 待 L3；注记进展 | 今日两轮真实弱模型 RUN 已完成（RUN-20260901-180051 DONE/rework=1/PASS、RUN-20260901-190029 DONE/rework=13/PASS，state+journal 在 E:\WB\state\...\runs\）——真实会话 + REWORK 迭代实证；但硬规则 §8b：业主真实目标走 §3 全自动前不得升 ✅ |
| §4 | 生产系统（Artifact+Evidence+Acceptance） | 🟡 | 🟡 | 保持 🟡 待 L3 | 今日两轮 RUN 为收尾/终局任务并留证据，但用户级真实交付 Acceptance 链未走；§8b 不升 ✅ |
| §5 | Provider 独立 | 🟡 | 🟡 | 保持 🟡 待 L3；注记豁免 | r_adapter L3 豁免四要素已落盘 wrapup-report（需业主注入真实 api_key_env，r_adapter.py 499-502 UNCONFIGURED 即正确）；test_worker_adapter PASS；待真实 Provider key |
| §6 | 核心角色 | ✅ | ✅ | 保持 | O/B/C/R/EC/Runtime 全在案 |
| §7 | Brain | 🟡 | 🟡 | 保持 🟡 | task_graph brain-pick 规则式仍；选 Worker/工具/重规划未实现；今日无新证据 |
| §8 | C 纠偏 | 🟡 | 🟡 | 保持 🟡 | strategic_correction 契约在；独立 C 常态化未建；今日无新证据 |
| §9 | C 的独立性 | ✅ | ✅ | 保持 | C 独立于执行链观察视角 |
| §10 | Worker | ✅ | ✅ | 保持 | 累计 8+ 次真实 GOAL + 今日 2 轮 RUN（真实弱模型执行） |
| §11 | EC 执行纠偏 | 🟡 | 🟡 | 保持 🟡；注记 | ec_lite NO_PROGRESS 机制在 + 今日两轮 RUN 各含 REWORK 迭代（共 14 次）为真实纠偏循环实证，但以 R 审查纠偏为主、EC NO_PROGRESS 专属触发案例仍少 |
| §12 | R 独立审查 | ✅ | ✅ | 保持 | 8+ 真实 GOAL 终审 PASS + 今日两轮 RUN 审查 PASS（RUN-180051/190029 各经 REWORK→PASS） |
| §13 | 三纠错不混淆 | ✅ | ✅ | 保持 | EC≠C≠R 分置 |
| §14 | Lifecycle Controller | ✅ | ✅ | 保持（抽查） | R1 guard_all.cmd 心跳判死/杀树重启；合流后 guard 相关套件 PASS |
| §15 | 跨回合自动继续 | ✅ | ✅ | 保持 | 多轮 REWORK 自动重交（今日两轮 RUN 实证） |
| §16 | WAIT 是 Task State | ✅ | ✅ | 保持 | A1/D4 WAITING_REVIEW 不阻塞队列（test_parallel_scheduler PASS） |
| §17 | Task Graph | ✅ | ✅ | 保持（抽查） | task_graph.py 依赖图/环检测/动态加任务（test_task_graph PASS） |
| §18 | Task Graph 双视图 | ✅ | ✅ | 保持 | _human_view 投影 + R3 用户视图 |
| §19 | NO_PROGRESS | ✅ | ✅ | 保持 | cost_router NO_PROGRESS SAFE_HALT + ec_lite 阈值（test_cost_router PASS） |
| §20 | 浏览器通用面 | 🟡 | 🟡 | 保持 🟡；注记 d3 激活 | 今日 d3 浏览器适配已激活（playwright 1.62.0 + chromium，browser_adapter.py status=PLAYWRIGHT_READY，search/fetch 实弹冒烟 mock=false 真返回，test_browser_adapter_d3_offline 29/29 无 skip）——search/fetch/download 子项已真实可用；但 click/input/form/upload 等通用操作仍未实现，故保持 🟡 |
| §21 | 本地执行面 | ✅ | ✅ | 保持 | run.cmd + registry capabilities 本地 |
| §22 | Goal Contract | ✅ | ✅ | 保持（抽查） | goal_contract_lite.py 三件套（egress/TCB/审查传输授权）合流后保留（test_goal_contract PASS） |
| §23 | 目标变化失效旧权 | ✅ | ✅ | 保持（抽查） | D4 STOP/REVOKE → REVOKED（test_parallel_scheduler PASS） |
| §24 | AI 记忆非 Truth | ✅ | ✅ | 保持 | capsule 机械投影 |
| §25 | 项目真源 | ✅ | ✅ | 保持 | PROJECT_STATE.* + doctor 校验（DRIFT_COUNT=1 预期态） |
| §26 | 当前进展 | ✅ | ✅ | 保持 | PROJECT_STATE 回写 |
| §27 | Context Capsule | ✅ | ✅ | 保持 | capsule_bridge |
| §28 | 决策理由保存 | ✅ | ✅ | 保持 | D001-D022+ 账本 |
| §29 | Canonical State Revision | ✅ | ✅ | 保持 | state revision 自增 + verify |
| §30 | Stale Result Safety | ✅ | ✅ | 保持（抽查） | D4 STALE 回收（test_parallel_scheduler PASS） |
| §31 | State 可恢复 | ✅ | ✅ | 保持 | state.json 唯一权威 |
| §32 | Control Plane Trust | ✅ | ✅ | 保持 | TCB 封印 gen1 VERIFIED |
| §33 | Authority 模型 | ✅ | ✅ | 保持 | scoped_authorization 只读查找（反自授权） |
| §34 | Split Brain 防护 | 🟡 | 🟡 | 保持 🟡 | D4 epoch 单调 + 单实例锁在；Controller 级 fencing（宪法 :1226-1242）仍未补；今日无新证据 |
| §35 | Identity Binding | ✅ | ✅ | 保持 | RUN 绑定 |
| §36 | Effect 追踪 | ✅ | ✅ | 保持 | effect_safety_lite（test_effect_safety PASS） |
| §37 | Effect Write-Ahead | ✅ | ✅ | 保持 | effect WAL |
| §38 | OUTCOME_UNKNOWN | ✅ | ✅ | 保持（抽查） | D4 显式 outcome + 不自动判定（test_effect_reconcile PASS） |
| §39 | 权限非聊天记忆 | ✅ | ✅ | 保持 | scoped_authorization 非记忆 |
| §40 | Revocation 单调性 | ✅ | ✅ | 保持（抽查） | epoch 单调 + STALE_EPOCH 拒收（test_parallel_scheduler PASS） |
| §41 | User Override 最高 | ✅ | ✅ | 保持 | D4 STOP/PAUSE/REVOKE 最优先 |
| §42 | 证据非自证 | ✅ | ✅ | 保持 | R 独立 + 机器验证 |
| §43 | Review 绑定 | ✅ | ✅ | 保持 | RUN↔commit（今日两轮 RUN 实弹） |
| §44 | 机器验证 | ✅ | ✅ | 保持 | 权威矩阵 + 今日 49 套件全绿 + tests 219 passed + b1_core 36+1 MATCH |
| §45 | 状态层级 | ✅ | ✅ | 保持 | DISCUSSED..PRODUCTION_VERIFIED 分级 |
| §46 | 外部内容 | ✅ | ✅ | 保持 | External Content = UNTRUSTED |
| §47 | Prompt Injection 防护 | ✅ | ✅ | 保持 | 实现 |
| §48 | Reuse Gate | ✅ | ✅ | 保持（抽查） | reuse_gate.py 四步 + BUILD_BLOCKED（test_reuse_gate PASS） |
| §49 | Reuse Decision | ✅ | ✅ | 保持 | record 结构化留痕 |
| §50 | Reuse 不等于 Trust | ✅ | ✅ | 保持 | decision 含 evidence + 失败衔接 |
| §51 | Supply Chain Gate | 🟡 | 🟡 | 保持 🟡 | supply_chain_check 依赖漏洞扫描在；十维度仍仅 2 覆盖；今日无新证据 |
| §52 | Secret Isolation | ✅ | ✅ | 保持 | 敏感清单零入仓 |
| §53 | Credential Store | ✅ | ✅ | 保持 | 凭据路径登记不复制 |
| §54 | Data Egress | ✅ | ✅ | 保持（抽查） | effect_safety_lite 最小出站（test_effect_safety PASS） |
| §55 | Context Sufficiency | 🟡 | 🟡 | 保持 🟡 | 五分支机制在 + 14/14 测试；全仓零生产消费者未变（未挂主链）；今日无新证据 |
| §56 | 多 Worker | ✅ | ✅ | 保持（抽查） | parallel_scheduler 并发分派（test_parallel_scheduler PASS） |
| §57 | Resource Lock | ✅ | ✅ | 保持（抽查） | ResourceLockManager + SingleInstanceLock（test_lease_atomicity PASS） |
| §58 | Project Isolation | ✅ | ✅ | 保持 | work_dir 隔离 + SANDBOX_VIOLATION |
| §59 | Cost Routing | 🟡 | 🟡 | 保持 🟡 | cost_router 三档 + ETC + 57/57 测试在；全仓零 .py import（零生产消费者）未变；今日无新证据（合流未接线） |
| §60 | Escalation Ladder | 🟡 | 🟡 | 保持 🟡 | L0-L2 落地，L3-L9 未实现；今日无新证据 |
| §61 | Hard Fuse | ✅ | ✅ | 保持（抽查） | SAFE_HALT 三条件真实触发（test_cost_router PASS） |
| §62 | Safety > Liveness | ✅ | ✅ | 保持（抽查） | fail-closed 矩阵 R31-R34（test_v09_attack_matrix PASS） |
| §63 | Capability Registry | ✅ | ✅ | 保持（抽查） | capability-registry.json 机器可读 + 被消费（test_v08_adapter_registry PASS） |
| §64 | Tool Manual | ✅ | ✅ | 保持 | operator_manual + README |
| §65 | 唯一入口 | ✅ | ✅ | 保持 | blackbox_bridge 四动词 + 一页卡 |
| §66 | Stable/Candidate | ✅ | ✅ | 保持 | StableLineage 测试绿 |
| §67 | Rollback | ✅ | ✅ | 保持 | lineage.rollback |
| §68 | 自举 | 🟡 | 🟡 | 保持 🟡 | self_heal 缺陷→goal 转换 + SH-001 L1 案例在；宪法 8 项能力仍仅覆盖约 2-4 项；今日无新证据 |
| §69 | 每阶段可用产品 | ✅ | ✅ | 保持 | 累计 8+ 次真实 GOAL + 今日 RUN 留证据产物 |
| §70 | Trace | ✅ | ✅ | 保持（抽查） | 输出带 trace 字段 + 各刀账本 |
| §71 | 简洁 UI | ✅ | ✅ | 保持 | blackbox-card 一页卡 + result/human-gate |
| §72 | 六个根 | ✅ | ✅ | 保持 | 全实现 |
| §73 | 最终可靠性原则 | ✅ | ✅ | 保持 | 15 行逐条对应（D3/D2/R1 补齐） |
| §74 | 最终完成条件 | 🟡 | 🟡 | 保持 🟡 待 L3 | 工程项达成（封印 gen1 + 签字 + master 汇合 + 今日合流/终局完成）；FINAL DONE 终裁仍待业主（§8b） |
| §75 | 定义治理 | ✅ | ✅ | 保持 | 宪法零修改 |
| §76 | 最终一句话 | ✅ | ✅ | 保持 | 系统即此 |

## 2. 汇总

| 档位 | V4 基线 | V5 POST-MERGE | 变化 |
|---|---|---|---|
| ✅ 完全满足 | 63 | 63 | 0 |
| 🟡 部分满足 | 14 | 14 | 0 |
| ❌ 未满足 | 0 | 0 | 0 |

## 3. 14 条 🟡 逐条重审记录（今日证据）

| 节 | 今日新证据 | 判定 | 理由 |
|---|---|---|---|
| §3 | 两轮真实弱模型 RUN 已完成（RUN-180051 DONE/rework=1/PASS、RUN-190029 DONE/rework=13/PASS，state+journal 在盘） | 保持 🟡 | §8b：业主真实目标走全自动前不得升 ✅，只注记进展 |
| §4 | 两轮 RUN 留证据产物 | 保持 🟡 | 用户级真实交付 Acceptance 链未走（§8b） |
| §5 | r_adapter L3 豁免四要素已落盘 | 保持 🟡 | 待业主注入真实 key（§8b） |
| §7 | 无新证据 | 保持 🟡 | Worker/Tool 选型未实现 |
| §8 | 无新证据 | 保持 🟡 | 独立 C 常态化未建 |
| §11 | 两轮 RUN 共 14 次 REWORK 迭代（真实纠偏循环） | 保持 🟡 | 以 R 审查纠偏为主，EC NO_PROGRESS 专属触发案例仍少 |
| §20 | d3 激活：playwright 1.62.0+chromium，status=PLAYWRIGHT_READY，search/fetch 实弹 mock=false 真返回，29/29 无 skip | 保持 🟡 | search/fetch/download 已真实可用，但 click/input/form 等通用操作未实现 |
| §34 | 无新证据 | 保持 🟡 | Controller 级 fencing 未补 |
| §51 | 无新证据 | 保持 🟡 | 十维度仍仅 2 覆盖 |
| §55 | 无新证据 | 保持 🟡 | 零生产消费者未变 |
| §59 | 无新证据 | 保持 🟡 | 零生产消费者/未接线调度未变 |
| §60 | 无新证据 | 保持 🟡 | L3-L9 未实现 |
| §68 | 无新证据 | 保持 🟡 | 8 项能力仍仅覆盖 2-4 项 |
| §74 | 今日合流/终局全部完成 | 保持 🟡 | FINAL DONE 终裁仍待业主（§8b） |

## 4. 63 条 ✅ 抽查记录（≥15 条，门禁/adapter/goal contract/runtime 优先）

| 节 | 抽查依据（机器验证，今日实测） |
|---|---|
| §0 | test_v09_attack_matrix_offline PASS（FAIL_CLOSED 实测） |
| §14 | guard/守护相关套件合流后 PASS |
| §17 | test_task_graph_d5_offline PASS |
| §22 | test_goal_contract_offline PASS（三件套保留） |
| §23 | test_parallel_scheduler_d4_offline PASS |
| §30 | test_parallel_scheduler_d4_offline PASS |
| §36 | test_effect_safety_offline PASS |
| §38 | test_effect_reconcile_offline PASS |
| §40 | test_parallel_scheduler_d4_offline PASS |
| §48 | test_reuse_gate_d3_offline PASS |
| §54 | test_effect_safety_offline PASS |
| §56 | test_parallel_scheduler_d4_offline PASS |
| §57 | test_lease_atomicity_offline PASS |
| §61 | test_cost_router_d2_offline PASS |
| §62 | test_v09_attack_matrix_offline PASS |
| §63 | test_v08_adapter_registry_offline PASS |
| §70 | trace 字段 + 各刀账本 grep 在位 |
全部抽查节无回退（合流未破坏门禁/适配/合同/运行）。

## 5. 机器验证基线（POST-MERGE 实测）

- 顶层 runtime 离线套件：49/49 PASSED
- tests/ 目录：219 passed, 2 subtests passed
- test_v09_attack_matrix_on_b1_core.py：36 用例 + V09-R34-FAITHFUL 全 MATCH，red=0
- state_doctor：DRIFT_COUNT=1（development head 记录里程碑 vs 物理 HEAD 超前，预期态）
- grep 接线：route_ds_mode(140)/WB_DONE(1031)/RECONCILE(457,1314,1377) 在位；run.cmd report→send_guard 在位
- CLI 冒烟：browser_adapter status=PLAYWRIGHT_READY；search/fetch 实弹 mock=false 真返回

## 6. 结论

合并后新 HEAD 33a5311 的 77 节定义矩阵与 V4 基线一致（63✅/14🟡/0❌）：
合流未造成任何 ✅ 回退（抽查 17 节全 PASS）；14 条 🟡 无升无降——真实进展（两轮 RUN、d3 激活）均不足以越过硬规则 §8b 或补足各节缺失闭环。
数字如实：量出来的，非凑出来的。

*复核记录：WA（RUN-20260901-225346-9633），2026-09-01。只读复核，唯一写入 = 本矩阵 v5 文件 + PROJECT_STATE.md 口径段。*