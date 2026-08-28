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

## D010 — Tier 2(b) 9 例 egress：判定为缺陷并 HARD STOP（未改测试）

- decision: actor=Builder（依 BUILDER_RULING_R3_R4 §2(b) 末段与 BUILDER_RULING_TIER2 §5）。不修订这 9 例期望，按缺陷上报。
- reason: `effect_safety_lite.py:678` 以 `state.get("effect_egress_permitted", False)` 取值，而全仓**无任何生产者**写入该 key（`runtime/runtime.py` 内 `egress` 0 命中）→ 真实发送路径的 egress 许可恒假。V14 §31 第 9 条与 `DATA_EGRESS_POLICY.md` 要求的是一条"可被许可打开"的闸门，故无法给出"新行为正确、旧期望过时"的规范支撑。
- evidence: `docs/evidence/v09-close/TIER2-b-egress-defect-HARD-STOP.md`（含检索命令、拒绝点行号、9 例清单，以及 canonical 侧 egress 已正确接线的对照：V09 矩阵 egress/scope 例全绿）。
- 范围: 该路径对全部 CLOSE 任务为 FORBIDDEN_FILES（且规格 §0.3 禁改 runtime.py）；9 例先于基线 50cf8bd1 即红，非本施工引入。
- status: OPEN —— 待裁决为缺陷修复（需独立授权任务）或登记为已知红 + V0.10 待办。

## D011 — T11 授权、归因修正与 runtime/ 例外边界（actor=主脑，经 Builder 转录）

- 归因修正（BUILDER_RULING_EGRESS §1）：9 例 egress 红**不是历史遗留**，而是 b1 核心升级提交
  `50cf8bd1` 自身引入的能力回归。基座 `e8c53d4` 的 `effect_safety_lite.py:131` 为
  `capability_permitted: bool = True, egress_permitted: bool = True`（参数式、默认放行，
  且基座全仓不存在 `effect_egress_permitted` 状态键）；b1 重写为状态键读取
  `state.get("effect_egress_permitted", False)` 且未建生产者。
  故依规格 §6 第 7 条**必须本轮修复，不得推迟至 V0.10**。
  Builder 前一份证据（TIER2-b）中"先于基线即红"一句据此勘误；其结论（缺陷、禁改期望）不变且更强。
- 追认（§2）：(c) 以实测推翻裁决预设（根因为夹具陈旧、胶囊逻辑完好、改产品反破 R33）——追认并记功；
  m1 适配为保真令两次 probe 使用不同 goal——追认。
- T11 授权与边界（§3）：对 `runtime/` 开出**单任务、单位点例外**，
  ALLOWED 仅 `runtime/runtime.py`（发送路径接线）、`runtime/effect_safety_lite.py`
  （仅 `_runtime_preconditions` 取值来源，二选一并论证选址）、新增测试文件；
  判定函数必须复用 `security.egress_allowed`；9 例期望一字不改作为验收件；
  须补 SECRET/UNKNOWN/scope 不匹配负例以防恒真；
  矩阵件、冻结件、`src/**`、`config/**` 及 runtime.py 任何结构性改动仍为 FORBIDDEN。

## D012 — T11 触发 §3 停止条款，上报设计方案并请求 T11b（actor=Builder）

- decision: 不在本授权内实施；停下上报设计方案。
- reason: REQUIRED_BEHAVIOR 要求合法外发放行，而 `egress_allowed` 的必需输入
  `goal_contract["data_egress_policy"]` 在 runtime 侧**完全不存在**
  （`grep -rn "data_egress_policy" runtime/` 仅命中冻结矩阵夹具）。直接接线只能传空 dict →
  恒 False（9 例仍红），或塞入全分级 → 恒真（§3.4 明令禁止，且比现状更危险）。
  真实许可须把 Goal Contract 持久化穿过多层 —— 正是 §3 IMPLEMENTATION_BOUNDARY 的停止条件。
- 取证补充：4 个失败套件均以子进程启动 `runtime.py`，状态仅 `APC_RUNTIME_STATE_ROOT` 下的
  JSON run state，无 control.db、不 import aicontrol（`grep -ln "control.db|aicontrol|ControlStore"` → NONE），
  故"委托 canonical 判定源"方案被排除，唯一可行路线为 runtime state schema 变更（结构性，超出本例外）。
- evidence: `docs/evidence/v09-close/T11-egress-wiring-DESIGN-STOP.md`
- 请求: 开设 T11b（授权 runtime state schema 变更 + 单列回归面：state 恢复兼容性、
  j4 跨进程一致性、Slice A AC-1..AC-11 冻结契约）。
- status: OPEN
