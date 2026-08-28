# V0.9 CLOSE 逐案裁决记录 — candidate `c6d1a55b`

协议: `V09_ATTACK_RESULT_JSONL_1` · candidate SHA `c6d1a55bc9d8f9bf48e8c2787c41370baa9a325f` · 规范锚 `sha256:6fe3bb7996a1f78a7d6584d08311c3ebc1aa2d9ffc56c27fc61e8d599e154df6`
SPEC_SHA `3deccf581bdcdf11ba6a2edba4d3f28cee410c69f3182b7f41065031e1db41fa` · BASE `50cf8bd1d1d36b4ebe8518b35a62a68204c4e39f`
运行器: 适配运行器（AD-1..AD-5, AD-7）；`36` 例 matched=`36` red=`0`

裁决来源: 用户 2026-08-28 裁决 + 主脑规格 V09_CLOSE_BUILD_SPEC + 裁决书 R1/R2、R18、R3/R4。
Builder 只记录实测与分类，不作验收裁决；`RELEASE_STATUS` 维持 `PRODUCT_NOT_READY`。

| CASE | 类 | 期望 | 实测 | 匹配 | 施工批次 | 观测摘要 |
|---|---|---|---|---|---|---|
| V09-R01 | D | `DENY` | `DENY` | ✅ | D 类锁定 | runtime_rc=86; authorization_count=0 |
| V09-R02 | — | `DENY` | `DENY` | ✅ | b1 既有绿（回归维持） | GateDenied: authorization provider/resource/purpose/identity/data bind |
| V09-R03 | — | `DENY` | `DENY` | ✅ | b1 既有绿（回归维持） | GateDenied: authorization provider/resource/purpose/identity/data bind |
| V09-R04 | D | `DENY` | `DENY` | ✅ | D 类锁定 | GateDenied: authorization provider/resource/purpose/identity/data bind |
| V09-R05 | — | `DENY` | `DENY` | ✅ | b1 既有绿（回归维持） | GateDenied: pre-existing authorization missing or wrong task |
| V09-R06 | A | `DENY` | `DENY` | ✅ | TASK-5 c6d1a55b | GateDenied: caller role is not permitted by the authorization scope |
| V09-R07 | — | `DENY` | `DENY` | ✅ | b1 既有绿（回归维持） | GateDenied: stale execution fence after authority generation change |
| V09-R08 | A | `DENY` | `DENY` | ✅ | TASK-1 26014c06 | GateDenied: execution fence token does not match the durable reservati |
| V09-R09 | A | `DENY_OR_REVALIDATE` | `DENY_OR_REVALIDATE` | ✅ | TASK-1 26014c06 | GateDenied: canonical state revision is no longer current |
| V09-R10 | — | `DENY` | `DENY` | ✅ | b1 既有绿（回归维持） | GateDenied: authorization revoked or inactive |
| V09-R11 | — | `DENY` | `DENY` | ✅ | b1 既有绿（回归维持） | GateDenied: authorization expired |
| V09-R12 | — | `DENY` | `DENY` | ✅ | b1 既有绿（回归维持） | GateDenied: authorization effect count exhausted |
| V09-R13 | D | `DENY` | `DENY` | ✅ | D 类锁定 | EffectDenied: no authorization bound to effect |
| V09-R14 | — | `NO_EXECUTE` | `NO_EXECUTE` | ✅ | b1 既有绿（回归维持） | GateDenied: reservation not executable |
| V09-R15 | — | `NO_DUPLICATE` | `NO_DUPLICATE` | ✅ | b1 既有绿（回归维持） |  |
| V09-R16 | — | `EXACTLY_ONCE` | `EXACTLY_ONCE` | ✅ | b1 既有绿（回归维持） |  |
| V09-R17 | — | `DEDUPLICATE` | `DEDUPLICATE` | ✅ | b1 既有绿（回归维持） |  |
| V09-R18 | C(已裁决) | `ALLOW_DISTINCT_EFFECT` | `ALLOW_DISTINCT_EFFECT` | ✅ | R18 裁决：不施工 | AD-5 identity proof: slots=['same-slot-diff'] logical_effect_ids=2 int |
| V09-R19 | — | `OUTCOME_UNKNOWN` | `OUTCOME_UNKNOWN` | ✅ | b1 既有绿（回归维持） |  |
| V09-R20 | A | `DENY` | `DENY` | ✅ | TASK-2 3e67f261 | ordinary retry denied: the same logical effect has an unresolved OUTCO |
| V09-R21 | A | `RECONCILE_FIRST` | `RECONCILE_FIRST` | ✅ | TASK-2 3e67f261 | AD-4: replay issued by a new Controller instance over the same state r |
| V09-R22 | B | `COMMIT_SUCCESS_NO_EXECUTE` | `COMMIT_SUCCESS_NO_EXECUTE` | ✅ | TASK-3 df6492b5 |  |
| V09-R23 | B | `CONTROLLED_RETRY_ONLY` | `CONTROLLED_RETRY_ONLY` | ✅ | TASK-3 df6492b5 |  |
| V09-R24 | B | `STAY_UNKNOWN_OR_HUMAN_GATE` | `STAY_UNKNOWN_OR_HUMAN_GATE` | ✅ | TASK-3 df6492b5 |  |
| V09-R25 | — | `DENY` | `DENY` | ✅ | b1 既有绿（回归维持） | GateDenied: authorization revoked before effect start |
| V09-R26 | A | `DENY` | `DENY` | ✅ | TASK-1 26014c06 | GateDenied: authorization generation is not the latest durable task ge |
| V09-R27 | — | `DENY` | `DENY` | ✅ | b1 既有绿（回归维持） |  |
| V09-R28 | — | `DENY` | `DENY` | ✅ | b1 既有绿（回归维持） |  |
| V09-R29 | — | `DENY` | `DENY` | ✅ | b1 既有绿（回归维持） |  |
| V09-R30 | — | `DENY_OR_REDACT` | `DENY_OR_REDACT` | ✅ | b1 既有绿（回归维持） | {"candidates": 1, "findings": [{"finding": "credential-like material", |
| V09-R31 | — | `DENY` | `DENY` | ✅ | b1 既有绿（回归维持） | GateDenied: Controller TCB is not VERIFIED |
| V09-R32 | A | `DENY` | `DENY` | ✅ | TASK-4 6cb04b05 | GateDenied: high-impact effect requires an explicit Human Gate referen |
| V09-R33 | — | `FAIL_CLOSED` | `FAIL_CLOSED` | ✅ | b1 既有绿（回归维持） | GateDenied: incomplete effect intent: ['effect_scope'] |
| V09-R34 | — | `FAIL_CLOSED` | `FAIL_CLOSED` | ✅ | TASK-4 6cb04b05 | AD-7 closed at issuance_side(store.grant_authorization): GateDenied: e |
| V09-R35 | — | `NO_BYPASS` | `NO_BYPASS` | ✅ | b1 既有绿（回归维持） |  |
| V09-R36 | A | `DENY` | `DENY` | ✅ | TASK-1 26014c06 | GateDenied: authorization generation is not the latest durable task ge |

## 忠实探针（R34 第二路径）

- `V09-R34-FAITHFUL` 期望 `FAIL_CLOSED` / 实测 `FAIL_CLOSED` / matched=✅ / external_effect_count=`0`
- 观测: `closed at issuance_side(store.grant_authorization): GateDenied: effect_type is outside the closed effect model`

**表面匹配 vs 忠实探针（任务简报 §14）**：收口前该例矩阵原走法曾以 `authorization effect type mismatch` **表面上** MATCH，而忠实探针证明未知类型端到端 ALLOW。两者冲突时以忠实探针为准，故 T9 实现为签发侧+执行侧双侧封闭；现两路径均在 `store.grant_authorization` 处 fail-closed，external_effect_count=0。

## D 类回归锁定（规格 §3）

- `V09-R01` 实测 `DENY`（期望 `DENY`）— 锚点：§31 check 1 + Human Gate Trust Root
- `V09-R04` 实测 `DENY`（期望 `DENY`）— 锚点：§31 check 2 + Authorization Replay Protection
- `V09-R13` 实测 `DENY`（期望 `DENY`）— 锚点：Controller self-grant forbidden（永久约束，本施工未恢复任何签发能力）

## R18（C 类，已裁决）

- 期望由裁决修订为 `ALLOW_DISTINCT_EFFECT`，**闸门代码零改动**；AD-5 判据要求同时成立：观测 ALLOW、external_effect_count=2、两次执行为两个不同 `logical_effect_id`、均为独立预留（非去重命中）。
- 本候选实测身份证明：`slots=['same-slot-diff'] logical_effect_ids=2 intent_hashes=2 action_rows=2 independent_reservations=True` → 非"碰巧 ALLOW"。

