# PROJECT_STATE — 执衡 / ai-production-control

> 本文件与 `PROJECT_STATE.json` 是项目状态的**唯一权威**（二者必须一致，由
> `scripts/state_doctor.py` 校验）。其余文档（README/STATUS/Journal）均为派生视图。
> 断言证据等级：VERIFIED（有锚点且已复核）/ INFERRED（有依据未复核）/ UNVERIFIED（假设）。

## 状态（2026-09-01，V1_ENGINEERING_CLOSED）

- 发布状态：**READY_FOR_USER_ACCEPTANCE**（V1.0 工程收口签字后晋升；边界注记见 `docs/governance/SIGNING-V1-ENGINEERING-CLOSE.md`——**北极星"自动调度闭环"未达成，"执衡可自动生产"宣称不成立**，达成前不得再晋升）
- 路线：Phase 0 → V0.9 收口 → V0.10 单类真实 GOAL → V0.11 REWORK/RECOVERY → V1.0 硬化（用户已批准）→ **V1.0 工程收口（2026-08-30 执行完毕）**
- 总纪律：KEEP > REPAIR > SIMPLIFY > REPLACE > REBUILD

## 四基线（不得互相画等号）

| 概念 | 值 | 等级 |
|---|---|---|
| 当前开发头 | `master@2f1188a`（实际 HEAD，2026-09-01 17:25:54 +0800；上一权威 9407f49 并入其历史） | VERIFIED |
| 当前被接受基线 | `v0.8-integrate/adapter-final-4@e8c53d4a`（v0.9 证据模块硬编码指认） | VERIFIED |
| 最后绿基线 | `master@2f1188a`（112+ 测试全绿 + 累计 8 次真实 GOAL（3+5）全 PASS + 封印 manifest + 2026-09-01 能力合并） | VERIFIED |
| master | `@2f1188a`，**CURRENT**（2026-09-01 能力合并：DeepSeek 双通道三模式 + WB_DONE 中立协议 + 效果安全三件套接线；历史：V1.0 工程收口时合并 v0.9-b1/authority-effect-core） | VERIFIED |

## 2026-09-01 能力变更（git verified，全部并入 master）

1. **DeepSeek 双通道三模式**：R_URL 支持 `chatgpt.com/c/<id>` 与 `chat.deepseek.com/a/chat/s/<id>`，调用方式一致；DeepSeek 三模式（快速/专家/识图）由 runtime 按任务内容自动路由并按会话锁定。提交 `9e1f99c`（双通道 + 桥加固）、`fffd0d3`（三模式路由 + 模式绑定会话）、`63208d5`（文档告知 worker）。
2. **WB_DONE 中立协议**：完成标记由 CHATGPT_DONE 更名中立 ===WB_DONE===（双通道统一）。提交 `8525138`。
3. **效果安全三件套接线**：RUN start 落合同（`runtime/goal_contract_lite.py`，提交 `2f1188a`，2026-09-01 17:25:54）——① egress 最小出站策略默认仅 INTERNAL（CLI 显式传入优先）；② TCB per-run 声明（BUILDER_RULING_AD8TCB §2 背书；seal_tcb 仍为部署态动作）；③ 审查传输授权（grant_authorization：issuer=CONTROLLER_AUTHORITY、holder=runtime-v1、purpose=review transport、data_classes=INTERNAL、TTL 604800s），journal 记 EFFECT_REVIEW_TRANSPORT_AUTHORIZED。
4. **种子会话优先续用**：review 上下文在种子会话中，`runtime/lib/yz_ds_lib.sh` 模式请求路径优先续用健康种子会话（双采样防误判），种子不可达/模式不符/非空闲才另开新对话。

## 当前阻塞（2026-09-01 状态）

1. **BLK-1** ~~完整 V0.9 规范未入库~~ → 已由流 Zero 入仓（docs/canon/），CLOSED
2. **BLK-2** ~~无通用 Goal Worker~~ → 累计 8 次真实 GOAL（3+5）全 PASS（第二批含 RUN-ff88/41b4/cfb5/c33e/37d9），CLOSED
3. **BLK-3** ~~权限闸门 16 例攻击案例应 DENY 却 ALLOW~~ → 流 A 三门构造后矩阵 36/36 red=0，CLOSED
4. **BLK-4** reconciliation API → 记录在案，待后续版本

**V1.0 工程收口（2026-08-30）已完成**：E1 TCB 封印已执行（收口专用库，gen 1）、E2 release_status 已晋升 READY_FOR_USER_ACCEPTANCE（带边界注记）、E3 master 已汇合（793fa41 + tag v1.0-engineering-close）、E4 累积清单已全部裁决。施工团任务结束，进入"业主验收 + 北极星（自动调度闭环）"新阶段。

## 16 RED 分类（规划者裁决提案，最终以锚定规范为准）

- **A 语义缺口（V0.9 内必修）**：R01/R04/R06/R08/R09/R13/R26/R32/R34/R36
- **B 能力缺失（需建）**：R21–R24（reconciliation）
- **C 待规范裁决**：R18/R20

## 已知缺口（证据等级标注）

- v0.5–v0.9 的独立审查已由流 Zero/E 补录入仓（docs/evidence/）；仓库 0 PR / 0 tag / 0 release 待业主裁决
- 战略大脑：已激活（brain_bridge，复用 strategic_brain_contract，90 测试绿；2026-08-30 提交 b274b4f）
- Context Capsule：已接入恢复流程（capsule_bridge，2026-08-30 提交 6aeebe3）
- 测试批跑密封性为未验证假设（此前误报已纠正；正式考验未做）

## 规范锚（spec_registry，T0 入库）

| spec_id | path | sha256 | status |
|---|---|---|---|
| `V14-FROZEN` | `docs/specs/V14-FROZEN-EXECUTION-SPEC.txt` | `6fe3bb7996a1f78a7d6584d08311c3ebc1aa2d9ffc56c27fc61e8d599e154df6` | COMMITTED |
| `FINAL-CANONICAL` | `docs/canon/ZHIHENG_FINAL_DEFINITION_FINAL_CANONICAL.md` | `4c05a21fab1543a209cafd70fee48752e996cf3a77df2987f316dde243f4a9a4` | COMMITTED |
| `CONSTRUCTION-ROUTE-V2` | `docs/canon/ZHIHENG_CONSTRUCTION_ROUTE_V2.md` | `995b1c9679a96b51f4e884aaa8fd8d69e959b27bac6db11afe0ab23583b1ddbe` | COMMITTED |
| `ROADMAP-V0.9-CLOSE` | `docs/governance/ROADMAP-V0.9到V1.0收口路线.md` | `597100f0f5cae53597af56c69788ad42fc197afdcf0c03e7e483db4f653cfc08` | COMMITTED |

登记依据：`docs/SPEC_ANCHOR_REPORT.md` §2/§3；条目内容 = `spec-anchor-pack/spec_registry.json`，status 由 `STAGED_NOT_COMMITTED` 置为 `COMMITTED`（T0 已入库）。交叉验证：与 `docs/BUILD_MISSION_JOURNAL.md` 的 `prompt_hash: sha256:6fe3bb79...` 同值。

该规范 `governs`：`runtime/fixtures/v09_authority_effect_attack_cases.json`、`runtime/test_v09_attack_matrix_offline.py`。

## 裁决记录入口

决策只写入 `DECISION_LEDGER.md`（追加式，含 actor）；施工日志在
`docs/BUILD_MISSION_JOURNAL.md`；新接手者从 `NEW_WORKER_START_HERE.md` 进入。
