# AD-8 REGISTRY — V0.9 CLOSE 最终批场景构造登记册

- 依据：BUILDER_RULING_FINALBATCH §3.3 / AD8TCB §2 纪律 3 / HANDOFF §3
- 执行：寇豆码（Builder，流 A）· 主理人（齐活林）接管验证与收口 · 2026-08-29
- 性质：**全部为测试场景构造（AD-8 授权范围），期望与断言一字未改**（逐文件 diff 核验：assert* 行零变更）
- 判据达成：矩阵 36/36（red=0，R34 忠实探针 FAIL_CLOSED）；tests/ 19 文件全绿（137 件口径）；CLOSE 40 全绿；runtime 25/26 exit 0（唯一例外 = test_harness_verify_offline.py 环境变量超长噪声，剔除宿主变量 ACC_PRODUCT_CONFIG_V3（515KB>32767）后 11/11 OK，零代码问题）；doctor 仅既有豁免项（registry b1-head 滞后）+ 已知 journal WARN

## 1. 场景构造通用配方（各点位一致）

| 门 | 构造方式 | 禁令 |
|---|---|---|
| ① egress | 场景策略文件 `SCENARIO_EGRESS_POLICY = {"default": ["PUBLIC", "INTERNAL"]}`（非恒真，SECRET 必拒），经 `--egress-policy-file` 随 Goal Contract 携带 | 不得塞全分级恒真 |
| ② TCB | `state["effect_tcb_verified"] = True` | 不得用 `tcb_status="VERIFIED"`（EC_GATE lifecycle 冻结 rc=5） |
| ③ 授权 | `effect_safety_lite.grant_authorization(issuer_role="HUMAN_AUTHORITY", issuer_identity="scenario-authority", holder="runtime-v1", scope 六要素, max_effect_count=3)` | 不得自签（API 拒绝）；不得手写绕过 API |

## 2. 逐点位登记（8 处 start-like 调用）

> 计数口径说明：HANDOFF（c0ed87e 时点）列 7 处；实际适配点位 8 处 = send_guard 2（start + router-start，router-start 为 HANDOFF 未单列处）+ ec_gate 2 + ec_telemetry 4。FINALBATCH "7 处"系 HANDOFF 口径，本册以实际 8 处为准并附差异说明。
> 行号基准：HEAD `c464190`（2026-08-29 第 1 轮独立审查实测值；此前版本曾登记 c0ed87e 基准旧行号，已按审查意见修正）。

| # | 文件:行号（HEAD c464190） | 调用形态 | egress 策略 | TCB 声明 | 授权签发 | 期望未改 |
|---|---|---|---|---|---|---|
| 1 | test_send_guard_offline.py:205 | ADAPTER `start` | ✅ :20/:91/:103 | ✅ :53 | ✅ :63 | ✅ |
| 2 | test_send_guard_offline.py:254 | ADAPTER `router-start` | ✅ :20/:91/:103 | ✅ :53 | ✅ :63 | ✅ |
| 3 | test_ec_gate_offline.py:155 | RUNTIME `start` | ✅ :27/:262/:274 | ✅ :61 | ✅ :71 | ✅ |
| 4 | test_ec_gate_offline.py:286 | ADAPTER `start` | ✅ 同上 | ✅ :61 | ✅ :71 | ✅ |
| 5 | test_ec_telemetry_offline.py:150 | RUNTIME `start` | ✅ :29/:114/:126 | ✅ :64 | ✅ :74 | ✅ |
| 6 | test_ec_telemetry_offline.py:190 | GC `start` | ✅ 同上（GC 经 --egress-policy-file） | ✅ :64 | ✅ :74 | ✅ |
| 7 | test_ec_telemetry_offline.py:219 | ADAPTER `start` | ✅ :29/:188 | ✅ :64 | ✅ :74 | ✅ |
| 8 | test_ec_telemetry_offline.py:235 | ADAPTER `start` | ✅ :29/:217 | ✅ :64 | ✅ :74 | ✅ |

（ec_router_telemetry_offline.py 亦含同配方场景构造 :25/:64/:65/:99/:124/:130，属既有套件适配延续，一并登记。）

## 3. 新增验收件 test_v09_close_egress_wiring_offline.py（11 例，FINALBATCH §3.2 全项）

| 用例 | 验证点 | 结果 |
|---|---|---|
| test_policy_absent_denies | 门①负例：无投影拒 | OK |
| test_empty_policy_denies | 门①负例：空策略拒 | OK |
| test_other_destination_policy_denies | 门①负例：他目的地策略拒 | OK |
| test_secret_class_denies_even_when_everything_else_permits | 门①负例：SECRET 恒拒 | OK |
| test_permitted_policy_allows_and_records | 正例：三门齐备放行 + 效果记录 + 非 HARD_BLOCKED | OK |
| test_tcb_not_declared_denies_despite_full_egress_permission | 门②负例：TCB 未声明拒（门未被架空） | OK |
| test_missing_authority_denies_despite_permission_and_tcb | 门③负例：无授权拒 | OK |
| test_self_grant_is_refused_by_the_api | 门③负例：自签被 API 拒 | OK |
| test_worker_issuer_role_is_refused_by_the_api | 门③负例：非权威角色签发拒 | OK |
| test_projection_bound_to_contract_hash_and_fail_closed_when_stale | 投影哈希绑定 + 失效关闭 | OK |
| test_legacy_state_without_projection_loads_and_denies | 旧 state 兼容且拒 | OK |

## 4. 验证证据

- 矩阵：`python runtime/test_v09_attack_matrix_on_b1_core.py` → case_count=36, matched=36, red=0；V09-R34 与 R34-FAITHFUL 均 FAIL_CLOSED MATCH
- 全量日志：全量套件输出文件（本批运行时 1UaRur，输出已核）；tests/ 19 文件 0 fail 0 error
- doctor：`python scripts/state_doctor.py` → DRIFT_COUNT=1（= registry b1-head 滞后，章程 §7.8 已裁决豁免项；expected c6d1a55b vs actual 665a73c5），WARN journal staleness（已知合法），零新增漂移
- 冻结件：runtime/test_v09_attack_matrix_offline.py 未运行入判据（§4.2 单独口径）、未改动（blob 对 a0ce691 IDENTICAL 保持）
