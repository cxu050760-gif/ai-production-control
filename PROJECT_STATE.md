# PROJECT_STATE — 执衡 / ai-production-control

> 本文件与 `PROJECT_STATE.json` 是项目状态的**唯一权威**（二者必须一致，由
> `scripts/state_doctor.py` 校验）。其余文档（README/STATUS/Journal）均为派生视图。
> 断言证据等级：VERIFIED（有锚点且已复核）/ INFERRED（有依据未复核）/ UNVERIFIED（假设）。

## 状态（2026-08-30，PHASE_0 收束中）

- 发布状态：**PRODUCT_NOT_READY**（R4 约束：开发头裁决 RED 期间必须维持；晋升待业主裁决 E2）
- 路线：Phase 0 → V0.9 收口 → V0.10 单类真实 GOAL → V0.11 REWORK/RECOVERY → V1.0 硬化（用户已批准）
- 总纪律：KEEP > REPAIR > SIMPLIFY > REPLACE > REBUILD

## 四基线（不得互相画等号）

| 概念 | 值 | 等级 |
|---|---|---|
| 当前开发头 | `v0.9-b1/authority-effect-core@a7befcb`（2026-08-30，含 Brain/Capsule 激活、5 次真实 GOAL 证据、V1.0 收束报告） | VERIFIED |
| 当前被接受基线 | `v0.8-integrate/adapter-final-4@e8c53d4a`（v0.9 证据模块硬编码指认） | VERIFIED |
| 最后绿基线 | v0.9-b1（112+ 测试全绿 + 5 次真实 GOAL 全 PASS；正式封绿待业主裁决） | VERIFIED + 限定 |
| master | `@4cf41fd`，MERGED_BASELINE_STALE（落后开发头 90+ 提交）；**合并裁决暂缓（E3 待业主）** | VERIFIED |

## 当前阻塞（2026-08-30 状态）

1. **BLK-1** ~~完整 V0.9 规范未入库~~ → 已由流 Zero 入仓（docs/canon/），CLOSED
2. **BLK-2** ~~无通用 Goal Worker~~ → 5 次真实 GOAL 全 PASS（RUN-ff88/41b4/cfb5/c33e 等），CLOSED
3. **BLK-3** ~~权限闸门 16 例攻击案例应 DENY 却 ALLOW~~ → 流 A 三门构造后矩阵 36/36 red=0，CLOSED
4. **BLK-4** reconciliation API → 记录在案，待后续版本

**剩余待业主裁决**：E1 TCB 封印、E2 release_status 晋升、E3 master 汇合、E4 累积清单（见 docs/evidence/V1.0-CLOSE-OUT-REPORT-20260830.md）

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

登记依据：`docs/SPEC_ANCHOR_REPORT.md` §2/§3；条目内容 = `spec-anchor-pack/spec_registry.json`，status 由 `STAGED_NOT_COMMITTED` 置为 `COMMITTED`（T0 已入库）。交叉验证：与 `docs/BUILD_MISSION_JOURNAL.md` 的 `prompt_hash: sha256:6fe3bb79...` 同值。

该规范 `governs`：`runtime/fixtures/v09_authority_effect_attack_cases.json`、`runtime/test_v09_attack_matrix_offline.py`。

## 裁决记录入口

决策只写入 `DECISION_LEDGER.md`（追加式，含 actor）；施工日志在
`docs/BUILD_MISSION_JOURNAL.md`；新接手者从 `NEW_WORKER_START_HERE.md` 进入。
