# Decision Ledger

## D001 — Stable placement

- decision: Place the Controller under `E:\WB\tools`, with separate `E:\WB\state` and `E:\WB\outputs` roots.
- reason: It is a reusable WorkBuddy-adjacent production tool, not a fourth workspace hierarchy or a timestamped build directory.
- evidence: Target paths were absent before creation; the existing three-layer workspace contract assigns WorkBuddy tooling to `E:\WB`.
- status: ACTIVE

## D002 — Controller runtime

- decision: Use Python 3.12 standard-library SQLite for the authoritative Controller and Node 20 plus pinned `playwright-core` only for the browser adapter.
- reason: SQLite supplies transactional durability and append-oriented journals without a server; the installed Python and Node versions are verified. Playwright supplies mature browser semantics without adding an Agent framework.
- evidence: Python 3.12.10, Node 20.18.1, npm 10.8.2; `playwright-core@1.62.1` requires Node >=20.
- status: ACTIVE

## D003 — Browser collision resolution

- decision: PRIMARY=`Playwright/CDP` with a dedicated persistent profile; FALLBACK=`BrowserSkill bsk 0.1.10` for authenticated/profile-aware operations and its verified upload extension.
- reason: Playwright gives broad navigation/input/tab/download/media coverage; BrowserSkill preserves existing logged-in-browser and upload assets. Chrome DevTools MCP is an agent-facing MCP/debug surface rather than the embedded Controller library, and browser-use adds an LLM Agent layer that this Controller already owns.
- evidence: local BrowserSkill 0.1.10 binary and extension 0.1.5 hashes recorded in inventory; its current daemon had zero connected browsers at inventory time, so it cannot be the sole backend.
- status: ACTIVE

## D004 — Existing Bridge reuse boundary

- decision: Do not replace or modify `ChatGPT_Codex_Bridge`; reuse its acceptance-gating and bounded-artifact lessons, while the new Controller remains a separate local runtime.
- reason: The Bridge is an 18-tool restricted MCP bridge with its own public contract and live-tunnel acceptance boundary, not a general effect/authority Controller.
- status: ACTIVE


## D005 — V0.9 CLOSE 治理文件移植源改定 f74d48e（R3）

- decision: 治理文件（PROJECT_STATE.json/.md、state/branch_registry.json、scripts/state_doctor.py、scripts/test_state_doctor_classification.py、docs/PHASE0_PACK_README.md）移植源 = 冻结线 b2 的最终状态 `f74d48e`，不是 `a0ce691`。
- reason: actor=主脑（BUILDER_RULING_R3_R4 §1）。主脑自认原裁决错误：`633daec`（registry 封印校准）与 `f74d48e`（doctor 增加 governance-ahead CASE 2）正是使治理包自洽可验的定稿动作；a0ce691 时刻 registry 仍为封印前状态（b2-head=da6d1e5e）且 doctor 无 CASE 2 规则，以其为源必然 DRIFT。
- evidence: Builder 对照实测——a0ce691 源 `DRIFT_COUNT=1`（b2 行 da6d1e5e vs 在位 f74d48e），f74d48e 源 `DRIFT_FREE`；`git cat-file blob a0ce691:scripts/state_doctor.py` 中 governance/CASE 2 零命中，f74d48e 版含 GOVERNANCE_PATHS/_classify_dev_head。裁决链：规范原文 > 规格 > 裁决指令。
- status: ACTIVE

## D006 — V0.9 CLOSE 回归判据两级化（R4）

- decision: actor=主脑（BUILDER_RULING_R3_R4 §2）。以两级判据替换规格 §4.3"全量离线套件全绿"原文表述：Tier 1（施工期，每批强制）= 相对已录基线 `50cf8bd1` 零新增失败 + 逐案矩阵回归；Tier 2（收口门）= 19 例基线红按 (a)(b)(c) 三类分治处置。
- reason: §4.3 在授权基线上不可达（基线先于本施工即红 19 例），属规格缺陷，由主脑承担；不得为让测试变绿而伪装结果。
- evidence: `docs/evidence/v09-close/BASELINE-b1-50cf8bd1.md`（97 例 tests/ 计 2 FAIL+8 ERR；runtime/ 4 文件 9 FAIL）。
- status: ACTIVE

## D007 — AD-6：R13 永久约束下的测试适配类别

- decision: actor=主脑（BUILDER_RULING_R3_R4 §2(a)）。设立 AD-6：允许修改**仅限测试文件**（`tests/**`、`runtime/test_*.py`），按 AD-1 同构模式为被测流程预置外部权威授权（decision nonce → grant），断言强度不降；禁止为让旧测试通过而改动任何产品代码。
- reason: 8 例 self-grant ERROR 依赖的"Controller 自签发"已被 V0.9 永久禁止（规格 §3 对 R13 的永久约束），修回产品代码即违宪。
- status: ACTIVE

## D008 — V09-R34 封闭 effect_type 集合（策略变更留痕）

- decision: actor=Builder（依据 V09_CLOSE_BUILD_SPEC.md T9 IMPLEMENTATION_BOUNDARY 第 2 条）。`config/production.json` 新增 `policy.authority_effect.known_effect_types = ["AI_MESSAGE","TEST","PUBLIC_TEST_INTERACTION"]`，签发侧（`store.grant_authorization`）与执行侧（`controller.execute_effect`）双侧强制成员判定。
- reason: T9 要求未知 effect_type 端到端 fail-closed；集合变更属策略变更，按项目制度在此留痕。
- 盘点清单（规格 T9 第 1 条要求"初始集合必须先盘点既有合法用法"）：
  - `AI_MESSAGE` — `src/aicontrol/controller.py:517/543/599`（`execute_workbuddy_fallback` 与 run_goal 路径）、`acceptance.py:326/394`、攻击矩阵 AD-2 默认类型；
  - `TEST` — `src/aicontrol/acceptance.py:174/183/806/809/862`（验收自测流程）；
  - `PUBLIC_TEST_INTERACTION` — `src/aicontrol/acceptance.py:264`；
  - 排除项：`SEND_AI_MESSAGE` 与 `EXTERNAL` 分别是 `operation` 与 `effect_scope` 字段值，不是 effect_type，未纳入；`TOTALLY_UNKNOWN_EFFECT_TYPE` 是攻击载荷，不得纳入。
- evidence: 集合内类型端到端正例通过；`test_v08_adapter_core_offline` 44/44、`test_v08_adapter_evidence_offline` 27/27、`test_v09_effect_core_offline` 13/13 均维持绿，未见既有绿色流程被打红。
- status: ACTIVE

## D009 — V0.9 CLOSE TCB 重封推迟（机械事实，非判定）

- decision: actor=Builder。不在本施工线运行 `seal_tcb`，TCB 维持 `UNVERIFIED_AFTER_CONTROLLER_CHANGE`。
- reason: 既有封印机制的目标根为 `E:\WB\tools\ai-production-control` + `E:\WB\state\ai-production-control`（config 明列，本机实测均存在且为在产状态）。从本 worktree 运行会（1）写入活的 Controller 状态，（2）产出的 manifest 描述的代码树并非本候选，二者均使证据失真。
- evidence: `config/production.json` code_root/state_root；`ls E:/WB/state/ai-production-control` 含 acceptance-fixtures/browser-auth-profile-* 等在产物；全新 store 的 `meta('tcb_status')` = `UNVERIFIED_AFTER_CONTROLLER_CHANGE`。
- status: ACTIVE —— 待发布负责人在权威配对上重封，判定权在独立审查者与用户（R1/R2 裁决书 §3.5）。
