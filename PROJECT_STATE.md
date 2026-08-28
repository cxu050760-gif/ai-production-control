# PROJECT_STATE — 执衡 / ai-production-control

> 本文件与 `PROJECT_STATE.json` 是项目状态的**唯一权威**（二者必须一致，由
> `scripts/state_doctor.py` 校验）。其余文档（README/STATUS/Journal）均为派生视图。
> 断言证据等级：VERIFIED（有锚点且已复核）/ INFERRED（有依据未复核）/ UNVERIFIED（假设）。

## 状态（2026-08-28，PHASE_0）

- 发布状态：**PRODUCT_NOT_READY**
- 路线：Phase 0 → V0.9 收口 → V0.10 单类真实 GOAL → V0.11 REWORK/RECOVERY → V1.0 硬化（用户已批准）
- 总纪律：KEEP > REPAIR > SIMPLIFY > REPLACE > REBUILD

## 四基线（不得互相画等号）

| 概念 | 值 | 等级 |
|---|---|---|
| 当前开发头 | `v0.9-b2/authority-effect-evidence@a0ce691`，裁决 = **CANDIDATE_RED** | VERIFIED |
| 当前被接受基线 | `v0.8-integrate/adapter-final-4@e8c53d4a`（v0.9 证据模块硬编码指认） | VERIFIED |
| 最后绿基线 | 同上（仓库侧测试实测全绿；正式封绿还差入库独立审查记录） | VERIFIED + 限定 |
| master | `@4cf41fd`，MERGED_BASELINE_STALE（落后开发头 78 提交）；**合并裁决暂缓至 Phase 0 后** | VERIFIED |

## 当前阻塞（全部带锚点，见 JSON）

1. **BLK-1** 完整 V0.9 规范未入库（在用户本机）→ 16 RED 无法裁决【解锁一切的第一动作】
2. **BLK-2** 无通用 Goal Worker/Adapter（STATUS 自认）→ 无法执行真实 GOAL
3. **BLK-3** 权限闸门 16 例攻击案例应 DENY 却 ALLOW（已实测复现）
4. **BLK-4** reconciliation API 不存在（测试探测 6 个候选方法名全缺失）

## 16 RED 分类（规划者裁决提案，最终以锚定规范为准）

- **A 语义缺口（V0.9 内必修）**：R01/R04/R06/R08/R09/R13/R26/R32/R34/R36
- **B 能力缺失（需建）**：R21–R24（reconciliation）
- **C 待规范裁决**：R18/R20

## 已知缺口（证据等级标注）

- v0.5–v0.9 的独立审查全部发生在仓库外；仓库 0 PR / 0 tag / 0 release / 0 审查证据文件（INFERRED→需补录机制）
- 战略大脑为惰性脚手架、默认禁用（VERIFIED，提交信息自述）
- 测试批跑密封性为未验证假设（此前误报已纠正；正式考验未做）

## 裁决记录入口

决策只写入 `DECISION_LEDGER.md`（追加式，含 actor）；施工日志在
`docs/BUILD_MISSION_JOURNAL.md`；新接手者从 `NEW_WORKER_START_HERE.md` 进入。
