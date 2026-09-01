# 执衡 v1.1-blackbox 开发线交付总结（2026-08-31）

## 一句话
V1.1 blackbox 开发线机器阶段**全部完成**：R1/R2/R3/A1/D1-D6 十刀交付、全部通过 §17 审核门禁（关键阶段双会签）、矩阵 v4 机器复核 **67✅/10🟡/0❌**（7 个原 ❌ 全消除），已推送远端 HEAD=bd5bd7a、DRIFT_FREE。**L3 真实测试（8 项）留给业主。**

## 交付物（分支 v1.1-blackbox，全部已审核推送）
| 刀 | 内容 | 宪法节 |
|---|---|---|
| R1 | guard_all.cmd 守护（心跳判死/杀树重启/bsk 动态端口/单实例锁）+ ZhihengGuard 计划任务 | §14/§61 |
| R2 | capability-registry.json（15 节 107 条目）+ validator/launch/README | §63/§20/§21 |
| R3 | blackbox_bridge（RESULT/HUMAN_GATE）+ 一页操作卡 | §65/§71/§18 |
| A1 | relay_autopilot 无人值守状态机（R 并发度 1 + WAITING_REVIEW 不阻塞 + 公平重排队） | §3 前置/§16/§19 |
| D1 | r_adapter（LiteLLM 仲裁/热切换/mock）+ worker_adapter（CLI 协议） | §5/§12/§73 |
| D2 | cost_router（ETC 成本路由）+ SAFE_HALT 真实触发 3 次 + cost_policy | §59/§61/§2/§19 |
| D3 | reuse_gate（无 Decision 不得 BUILD）+ supply_chain + Playwright download | §48-51/§20 |
| D4 | parallel_scheduler（多 Worker/资源锁/隔离/失效权/epoch/stale/UNKNOWN） | §56/§57/§58/§16/§23/§41/§40/§30/§38 |
| D5 | self_heal 自举 L1（offline 矩阵修复 36/36，权威矩阵零影响）+ task_graph + context_sufficiency 五分支 | §68/§17/§7/§55/§60/§70 |
| D6 | 矩阵 v4 机器复核 67✅/10🟡/0❌ + L3 清单 | 全部 77 节 |

## 关键决策（DECISION_LEDGER D022/D023）
- §48 Reuse 门禁逐刀执行：LiteLLM/Playwright/pip-audit=Reuse；守护层/门禁工具/调度=Compose（无现成）；禁 WINDOWTITLE 探活等教训入档
- 双 runtime 红线全程遵守：生产黑盒 runtime.py 零改动；新增走独立模块+薄入口
- 凭据纪律：api_key 一律 env 变量名；会话注册只登记路径

## L3 待业主（8 项，唯一剩余）
①真实弱模型会话（§3/§4/§65/§71）②真实 Provider key（§5）③真实目标走 §3 全自动 ④真实多 Worker 并行 ⑤真实断网对账（§38）⑥cost_policy 真实价目校准（§59）⑦§55 挂真实 Brain 检查点 ⑧§74 终裁
> 前置提醒：R-PROD 通道用前必 `chatgpt_bridge status` 实测（last_verified=2026-08-19 已过期）；弱模型会话需业主开。

## 主要文件
- 矩阵 v4：`docs/evidence/DEFINITION-77-SECTIONS-V4.md`
- 审核记录：`docs/evidence/reviews/REVIEW-{R1,R2,R3,A1,D1-D6}-*.md`
- 交接：`docs/evidence/HANDOFF-INDEX.md`
- 决策：`docs/DECISION_LEDGER.md`（D022/D023）
- 提交链：4157cb2→bd5bd7a（13 个功能/文档提交 + 治理同步，全部推送 origin/v1.1-blackbox）

## 后续建议
1. 业主按 L3 清单逐项实测（R 通道 health 先行）
2. 已知待清理：state/goals/（D6 复核转换产物，untracked 未入仓）
3. 全量测试 8 ERROR 基线（harness env patch 污染）建议后续独立清理
