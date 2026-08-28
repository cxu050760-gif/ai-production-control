# BASELINE_TEST_RESULT — v0.9-b1/authority-effect-core@50cf8bd1

BASE_SHA: `50cf8bd1d1d36b4ebe8518b35a62a68204c4e39f` (施工线物理基线，未改动)
记录时点: T0 施工**之前**，工作树 `git status --short` 为空
环境: win32, Python 3.12.10 @ `C:\Users\17838\AppData\Local\Programs\Python\Python312\python.exe`
（`runtime/run.cmd` 指认的 canonical 解释器）；`pytest` 不可用（`No module named pytest`），
故全部套件以 `unittest` / 脚本自带 `main()` 方式直接执行，未安装任何依赖。

## 1. `tests/`（`python -m unittest discover -s tests -t tests`）

`Ran 97 tests` → **failures=2, errors=8**（rc=1，非绿）

| 类型 | 用例 | 根因 |
|---|---|---|
| ERROR ×6 | `test_m05_hardening.M05ControllerFixture`（canonical_acceptance_and_review_chain / empty_review_set / forged_review_result / malformed_adapter_result / primary_exception_no_fallback / workbuddy_fallback_own_authorization_and_effect_wal） | `controller.py:318 scoped_authorization` → `GateDenied("pre-existing scoped authorization required; Controller self-grant is forbidden")` |
| ERROR ×2 | `test_m1_adapters.M1Fixture.test_primary_timeout_unknown_status_never_falls_back`（TIMEOUT / UNKNOWN 两参数化） | 同上（`controller.py:510 run_goal` → `:318`） |
| FAIL ×2 | `test_context.MechanicalCapsuleTests.test_unknown_effect_is_preserved_not_dropped`、`test_unknown_not_rewritten_as_completed` | OUTCOME_UNKNOWN 效果未进入 capsule；`completed_facts` 含 `unresolved_effects=0` |

〔定性〕8 个 ERROR 的共同根因**正是规格 §3 明文规定的永久约束**
（"任何任务不得恢复 `scoped_authorization` 的签发能力"）。这些 v0.8 时代遗留测试依赖
已被 b1 移除的自签能力，因此在基线上必然红。修复它们 = 违反永久约束 + 超出全部 CASE 范围。
2 个 `test_context` FAIL 位于 UNKNOWN 语义邻域，但**不属于任何 CASE_ID**，本Builder 不动。

## 2. `runtime/` 离线套件（逐文件直接执行）

**绿（19 个文件）**：ec_lite 10/10、effect_safety 5/5、goal_contract 19/19、
harness_verify 11/11、review_result 23/23、router 54/54、runtime 55/55、
state_recovery 2/2、strategic_brain_contract 18/18、strategic_correction 28/28、
strategic_integration 14/14、strategic_reuse_contract 30/30、taskgraph 2/2、
v07_integration_candidate 11/11、v07_integration_contract_matrix 9/9、
**v08_adapter_core 44/44**、**v08_adapter_evidence 27/27**、v08_adapter_registry 7/7、
**v09_effect_core 13/13**、weak_ai_acceptance 1/1。

〔对照规格 §4.3 点名的套件〕b1 自测 13（`test_v09_effect_core_offline`）✓绿、
44/44 ✓绿、27/27 ✓绿；"14" 对应 `tests/test_v09_authority_store.py`，在 §1 的 97 例中绿。

**红（4 个文件，9 例）**：ec_gate 1/18、ec_router_telemetry 4/9、ec_telemetry 1/10、
send_guard 3/3。共同根因 = 退出码 6 / `EFFECT_SAFETY_DENIED: data egress denied`
（`runtime/effect_safety_lite.py:371/375/498`，由 `goal_contract["data_egress_policy"]`
默认拒绝驱动）。属 b1 收紧 egress 闸门后的遗留期望，非环境问题、非 Builder 引入。

## 3. 汇总与回归判据

基线红总数 = **19**（`tests/` 10 + `runtime/` 9），全部在 50cf8bd1 上**先于本施工存在**。

规格 §4.3 要求"施工线全量离线套件全绿"，§6.7 把它列为收口判据之一。
该判据在**本施工线授权基线上不可达**，除非进行超出全部 CASE_ID 的修复或违反 R13 永久约束。

〔Builder 采用的判据，待审查者确认〕回归判定改为**相对基线**：
（a）不新增任何基线之外的失败；（b）各任务 REGRESSION_REQUIREMENTS 点名的
R07/R14/R15/R16/R17/R19/R25/D 类逐案维持；（c）R18 裁决期望
（ALLOW 且 external_effect_count=2，两不同 logical_effect_id）每批不破。
此替代解释记录于此，不作自我验收；`RELEASE_STATUS` 维持 `PRODUCT_NOT_READY`。
