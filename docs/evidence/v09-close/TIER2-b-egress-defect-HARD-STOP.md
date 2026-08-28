# Tier 2(b) egress 归因 — 9 例判定为缺陷，HARD STOP 上报

绑定：SPEC_SHA `3deccf58…41fa` · V14 `6fe3bb79…154df6` · BASE `50cf8bd1`
裁决依据：`BUILDER_RULING_R3_R4` §2(b) 末段
（"若任何一例无法给出规范支撑（= b1 过度收紧），不得改测试，按 HARD STOP 上报——
那将按缺陷处理，不是期望问题"）；优先级链 规范原文 > 规格 > 裁决指令。

## 1. 涉及用例（9 例，全部同一失败签名）

| 套件 | 用例 | 观测 |
|---|---|---|
| `runtime/test_ec_gate_offline.py` | `test_s3_healthy_run_send_still_flows` | rc=6 `EFFECT_SAFETY_DENIED: data egress denied` |
| `runtime/test_ec_router_telemetry_offline.py` | `test_r1_router_pass_records_artifact` | 同上 |
|  | `test_r5_done_idempotent_no_double_count` | 同上 |
|  | `test_r6_unicode_cursor_boundary_preserves_counting` | 同上 |
|  | `test_r8_next_action_token_does_not_mask_send_failure` | 同上 |
| `runtime/test_ec_telemetry_offline.py` | `test_t3_send_ok_records_action` | 同上 |
| `runtime/test_send_guard_offline.py` | `test_j2_send_enforces_contract_and_effect_authorization` | 同上 |
|  | `test_j3_router_run_records_contract_and_router_send_effects` | 同上 |
|  | `test_j4_router_continue_preserves_contract_and_effect_across_processes` | 同上 |

## 2. 判定链条（全部实测，非推断）

1. **拒绝点唯一**：`runtime/effect_safety_lite.py:371/375/498` 抛
   `EffectDenied("data egress denied")`；驱动值是
   `effect_safety_lite.py:678`
   `"egress_permitted": bool(state.get("effect_egress_permitted", False))` —— **默认 False（拒绝）**。
2. **该 key 无任何生产者**：全仓检索
   `grep -rn "effect_egress_permitted" --include=*.py --include=*.cmd --include=*.json .`
   只有两处命中：上述读取处、以及 `runtime/test_effect_safety_offline.py:57`（单测自行注入）。
   `runtime/runtime.py` 中 `grep egress` **0 命中**；`ec_lite.py`/`send_guard_lite.py`/
   各 `test_*_offline.py` 亦无写入点。
3. **因此真实 Runtime 发送路径上的 `egress_permitted` 恒为 False**，任何一次外部发送必然
   被拒。这 9 例断言的是"健康发送仍然流动"（`test_s3_healthy_run_send_still_flows`、
   `test_j2/j3/j4` 断言 rc=0 且状态记录 effect），在该实现下**不可能成立**。
4. **排除"规范禁止发送"这一替解**：V14 §31 第 9 条是 **"Data Egress permits it"**——
   要求的是"由数据外发许可决定放行"，不是一律封禁；`DATA_EGRESS_POLICY.md` 明列
   许可为**目的/接收方/provider/Goal Contract/授权特定**（即存在"许可成立"的状态），
   b1 config 也携带 `policy.authority_effect` 与矩阵夹具的 `egress_permitted=True` 正例
   （`test_v09_attack_matrix_offline.py:208`，V09 侧经
   `src/aicontrol/security.egress_allowed` 判定，14 例 egress/scope 矩阵全绿）。
   即：**同一语义在 canonical 侧已正确接线（按内容判定并允许放行），
   在 runtime 侧却接成了一根恒假的线。**

## 3. 结论：缺陷，不是过时期望

- 规范/策略支撑"新行为正确、旧期望过时"这一说法**无法给出**：规范要求的是一条
  *可被许可打开* 的闸门，而现状是一条 *无生产者、永远打不开* 的闸门。
- 若按 AD-6 修订这 9 例期望为"发送被拒"，等于把一条永久性功能失效写进规格，
  并直接掩盖 §6 第 7 条"已有能力不因 V0.9 修复而回归"的违背。
  **本节因此不改任何测试、不改任何期望值。**

## 4. 范围声明：为何 Builder 不能自行修复

- 修复位点在 `runtime/runtime.py`（或 `effect_safety_lite._runtime_preconditions` 的取值来源），
  二者对全部 V0.9 CLOSE 任务均为 **FORBIDDEN_FILES**；
  且规格 §0.3 明令"禁止结构性重构 `runtime/runtime.py`"。
- 这 9 例**先于本施工线存在**（基线 `50cf8bd1` 即红，见
  `BASELINE-b1-50cf8bd1.md`），并非 TASK-1..TASK-5 引入：本次改动文件为
  `src/aicontrol/{store,controller,security}.py`、`config/production.json`、
  `tests/`、T0 测量件，均未触及该取值路径。

## 5. 需要的处置（不属 Builder 权限）

1. 将本缺陷单列为 **V0.9 收口清单阻塞项**（与 TCB 重封并列），裁决"按缺陷修复"还是
   "按已知红登记 + V0.10 待办"。
2. 若按缺陷修复：需要一个明确授权改动 `runtime/**` 的独立任务（含其在 §1 TCB_IMPACT
   的论证与配套回归），因为它会改变真实发送路径的行为面。
3. 审查口径建议：**除本 9 例之外**，Tier 2 的 (a)(c) 已使 `tests/` 全量 137 例转绿。
