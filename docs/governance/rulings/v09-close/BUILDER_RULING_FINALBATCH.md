# BUILDER_RULING_FINALBATCH — 最终批工单（新会话续作用，三门链已闭环）

裁决人：总设计师 / 主脑
执行对象：**续作 Builder 会话**（前会话上下文耗尽，按 AD8TCB §5 移交）
日期：2026-08-28
裁决链：SPEC `3deccf58…41fa` → R1/R2 → R18 → R3/R4 → TIER2 → EGRESS → T11B →
AD8TCB（`a32e14a4…d8da`）→ 本工单
续作入口（必读）：`docs/evidence/v09-close/HANDOFF-T11b-final-batch.md`
（现场/代理/解释器/调用规范/已落地清单/逐点位行号）
当前候选：v0.9-b1/authority-effect-core@a18d0d2（15 提交）

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
## §1 主脑已替你关闭的关键问题：第三道门可纯场景构造满足（实证）

前会话遗留的唯一未决问题（"第③门是否须产品侧签发位点"）由主脑
**实测关闭**，结论：**不需要任何产品改动**。

探针（主脑 2026-08-28 在 worktree 原地执行，可复现）：

```python
import effect_safety_lite as es
scope = {"provider": "chatgpt-web", "resource": "fake://review",
         "purpose": "review transport", "identity": "runtime-v1",
         "destination": "https://chatgpt.com/c/probe",
         "data_classes": ["PUBLIC", "INTERNAL"]}
rec = es.grant_authorization(rt, state,
        issuer_role="HUMAN_AUTHORITY",          # ∈ AUTHORIZED_ISSUER_ROLES
        issuer_identity="scenario-authority",   # 必须 ≠ holder
        holder="runtime-v1", scope=scope, max_effect_count=3)
# → state["effect_authorizations"] 建立有效授权
es.ensure_valid_authorization(rt, state, holder="runtime-v1", scope=...)
# → GATE-3 SATISFIED BY SCENARIO DECLARATION: True
```

同探针的负向实证（闸门活性）：
- `issuer_identity == holder` → `executor self-grant is forbidden`（自签仍禁）
- `issuer_role="WORKER"` → `authorization issuer is not an Authority role`

定性：运行时层的 `grant_authorization` 本就按 V14 Human Gate Trust Root
设计——"签发者必须是权威角色且与执行者分离"。测试场景里由夹具扮演
权威签发者，与 AD-1 在 canonical 侧的裁定**完全同构**（先例一致性成立）。
场景构造走的是产品自己的正门，不是旁路。

## §2 三门场景配方（最终批的唯一语义依据）

| 门 | 场景构造方式 | 禁令 |
|---|---|---|
| ① egress | `--egress-policy-file`（策略随场景契约，JSON object） | 不得塞全分级恒真 |
| ② TCB | `state["effect_tcb_verified"] = True` | **不得**用 `tcb_status="VERIFIED"`（EC_GATE lifecycle 冻结，rc=5，D015 已记） |
| ③ 授权 | 场景以 `effect_safety_lite.grant_authorization` 签发：`issuer_role ∈ {AUTHORITY, HUMAN_AUTHORITY, CONTROLLER_AUTHORITY}`、`issuer_identity ≠ holder`、scope 六要素齐备 | 不得自签（API 本身拒绝）；不得手写绕过 API 的状态记录 |

## §3 工单（穷举）

1. **7 处 start 调用**（行号以 HANDOFF §3 为准，续作先重新 grep 确认）：
   每处按 §2 配齐三门；期望与断言**一字不改**。
2. **新增 `runtime/test_v09_close_egress_wiring_offline.py`（不得跳过）**：
   - egress 四向负例（HANDOFF §1 表末，已实测，落文件即可）；
   - TCB 负例：策略+授权齐备、未声明 `effect_tcb_verified` → 拒；
   - 授权负例：策略+TCB 齐备、无授权 → 拒；自签尝试 → 拒（API 层）；
   - 正例：三门齐备 → 放行、效果被记录、状态非 HARD_BLOCKED。
3. **AD-8 登记册**入 `docs/evidence/v09-close/`：egress 策略 7 处 +
   TCB 声明 7 处 + 授权签发各处，逐点位，每条注明"场景构造，期望未改"。
4. **台账**：D016（主脑：本工单与第③门实证）、实现条目（actor=Builder）。
5. **出口判据**：全量离线套件真正全绿（§4.3 原文判据首次达成；
   冻结原件运行器按 §4.2 单独口径）+ 矩阵 36/36（含 R34 忠实探针）+
   `tests/` 137 + CLOSE 40 + doctor 无新增漂移（已裁决项除外）。
6. 完成后推送（仅 `v0.9-b1`，代理 127.0.0.1:7897），返回结果块
   （格式沿用 R1/R2 裁决书 §5），等待独立审查。

## §4 边界（本批性质 = 纯测试场景适配）

- ALLOWED：四个套件的场景构造、新增负例文件、证据与台账文档。
- FORBIDDEN：其余一切。本批**不应有任何产品代码改动**——若实施中
  发现必须改产品才能让某例转绿，立即停下上报（T11B §5 继续有效）。
- 不得为翻绿放宽任何默认值；不得改任何期望/断言；不得动冻结件。
- 审查权重标注：出站接线 + AD-8 登记册 + 三门负例 = 独立审查最高权重区。
