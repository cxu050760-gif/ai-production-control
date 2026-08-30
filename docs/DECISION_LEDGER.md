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

## D013 — T11b 出站许可机制落地；发现第二道 TCB 前置构成 §5 停止条件（actor=Builder）

- decision: 交付方案 B 的许可机制（契约派生 + 最小投影 + 哈希绑定 + fail-closed），
  不在本批改动 9 例验收件；就第二道阻塞触发 §5 上报。
- 实现（全部落在 §2 授权文件内）：
  - `goal_contract_lite.build_contract` 新增 `data_egress_policy` 字段，**不进入哈希核**
    （identity 仍为 sha256(goal,acceptance,constraints) → 既有契约哈希与 Slice A 冻结契约零影响）；
  - `persist_contract` 写入最小投影 `egress_policy_projection = {data_egress_policy, source_contract_hash}`，
    为**唯一写入者**（§3.6：Worker/模型输出通道不触达）；
  - `_extract_contract_options` 增加 `--egress-policy-file`（沿用 `--acceptance-file` 同款选项形态，
    非新增策略词汇；非 JSON object 直接拒绝）；
  - `effect_safety_lite._runtime_egress_permitted` 判定 **100% 委托** `security.egress_allowed`
    （零平行逻辑），投影缺失/哈希不匹配/策略空/要素缺失一律拒（§3.5 旧 state 兼容：可加载且表现为拒）。
- 实测（子进程端到端，同一 R_URL/purpose/provider）：
  无投影→rc=6 拒；空策略 {}→拒；`{"default":["PUBLIC","INTERNAL"]}`→egress 放行但被**第二道**
  前置拦截；`{"default":[...,"SECRET"]}` 仍拒（SECRET 由 egress_allowed 内部硬拒）；
  仅其它 destination 的策略→拒（目的地特定性成立）。投影 `hashbound=True` 全场景成立。
- 发现的阻塞：egress 打开后发送路径随即被 **TCB 未封印** 前置拒绝
  （`tcb_verified` 要求 state 携 `effect_tcb_verified` 或 `tcb_status==VERIFIED`）。
  这与收口清单第 1 项（封印由发布负责人执行、且推迟到独立审查之后）形成**先后环依赖**：
  若 9 例须在未封印状态下转绿，只能由测试场景声明 TCB 已验证——那属于 §3.4 AD-8 的
  "场景构造"还是"为翻绿放宽前置"，需主脑裁定；若是前者，请明确 AD-8 是否涵盖 tcb 声明。
- status: OPEN（§5(a)/(b) 待裁）

## D014 — AD-8 涵盖 TCB 场景声明；环依赖消解（actor=主脑，Builder 转录）

- decision（BUILDER_RULING_AD8TCB §2，SHA a32e14a4…d8da 已核验）：AD-8 的场景构造权限**涵盖**
  在 per-run state 声明 TCB 已验证；9 例转绿不必等待真实封印。
- reason：(1) 先例即规范——冻结 b2 矩阵夹具自身在 `test_v09_attack_matrix_offline.py:99-100`
  设 `tcb_status/authority_status=VERIFIED`，主脑复核确认；(2) 语义分层——TCB 验证是**部署态**
  （收口清单第 1 项，发布负责人审查后执行），场景模拟"已封印的健康世界"，二者不同层，
  场景声明既不替代也不构成生产封印；(3) 被测对象不变——9 例测发送路径与出站许可，
  须让非被测闸门满足才能行使被测闸门，此乃离线套件既有方法论。
- 四条纪律：声明仅限场景构造（不得触碰产品默认值/闸门逻辑/生产路径）；**必须补 TCB 闸门负例**
  （与 egress 四向负例并列入库，证第二门未被架空）；AD-8 登记册逐点位列出且注明"期望未改"；
  期望与断言一字不改，为翻绿放宽默认值维持 HARD STOP（T11B §5.c 继续有效）。

## D015 — 实测修正：发送路径为三道门串联，最终批据 §5 移交（actor=Builder）

- finding: AD8TCB §3 工单假设两门（egress + TCB）。实测为三门串联：
  ① egress（本会话已通，四向实测）；
  ② `Controller TCB is not VERIFIED for external effect` —— 场景声明
     `state["effect_tcb_verified"]=True` **可通过**；但改设 `tcb_status="VERIFIED"` 会转由
     EC_GATE 以 `lifecycle frozen: PAUSE/STOP`（rc=5）拒绝，属不同子系统，非合法声明路径；
  ③ `no authorization bound to effect` —— 需 run state 内与该 logical effect 绑定的有效授权
     （常规由 `ensure_valid_authorization` 建立）。**本会话未验证第③门能否纯 per-run state 声明**。
- decision: 上下文极限，按 AD8TCB §5 移交续作；未改任何期望/断言/产品默认值/闸门逻辑。
  若第③门须产品侧签发位点方能满足，则触 D014 纪律 1 与 T11B §5.b，续作须停下上报而非自行扩写。
- evidence: `docs/evidence/v09-close/HANDOFF-T11b-final-batch.md`（含 7 处调用点位、
  探针复现步骤、`INVALID_R_URL` 前置、AD-8 登记册模板与出口判据）。
- status: OPEN —— 9 例仍红；全量"真正全绿"未达成，§4.3 原文判据待最终批。

## D016 — 最终批工单与第③门实证关闭；三门链 8 处落地（actor=主脑/BUILDER_RULING_FINALBATCH，Builder 转录）

- decision（BUILDER_RULING_FINALBATCH §1，2026-08-28）：第③门（授权）**可纯场景构造满足**——运行时 `grant_authorization` 本就按 V14 Human Gate Trust Root 设计（签发者必须是权威角色且与执行者分离），测试场景由夹具扮演权威签发者，与 AD-1 canonical 侧裁定同构，走产品正门非旁路。主脑实测探针关闭该未决问题，无需任何产品改动。
- 实现条目（actor=Builder 寇豆码，主理人齐活林接管验证收口）：8 处 start-like 调用配齐三门（send_guard 2 / ec_gate 2 / ec_telemetry 4，含 router-start）；新增 `runtime/test_v09_close_egress_wiring_offline.py`（11 例：egress 四向负例 + TCB 负例 + 授权缺失/自签/角色负例 + 正例 + 投影绑定 + 旧 state）；AD-8 登记册 `docs/evidence/v09-close/AD8-REGISTRY-final-batch.md`（逐点位，期望未改）。
- 验证（全量，2026-08-29）：矩阵 36/36 red=0 + R34/R34-FAITHFUL FAIL_CLOSED；tests/ 19 文件全绿；CLOSE 40 全绿；runtime 25/26 exit 0——唯一例外 test_harness_verify_offline.py 因宿主环境变量 ACC_PRODUCT_CONFIG_V3（515KB > Windows 32767 上限）致 mock 恢复 ValueError，进程内剔除后 11/11 OK，纯环境噪声零代码问题；doctor 零新增漂移（仅 §7.8 豁免项 registry b1-head 滞后 + 已知 journal WARN）。
- 冻结件：runtime/test_v09_attack_matrix_offline.py 未动（blob 对 a0ce691 IDENTICAL 保持），未运行入判据（§4.2 单独口径）。
- status: CLOSED —— 最终批出口判据达成（§4.3"真正全绿"首次达成）；推送 v0.9-b1 后待团内独立审查与封印记录（机械执行，不宣告有效性）。

## D017 — 恢复控制会话：中继恢复 + Brain/Capsule 非侵入激活（actor=DeepSeek-V4-Flash-20260829，业主全权授权）

- decision 1（中继）：construction-relay 从 8-27 停摆恢复运行（watcher PID 17360 + guard 5864），陈旧 relay.lock 移入 stale-locks（不删），V07-INTEGRATE-2（授权过期 3 天、里程碑历史化）移入 quarantine。
- reason：定义 §14「Agent 可以停，任务不能因为 Agent 停而停」；恢复生产循环是业主最初提示词的第一目标。
- evidence：relay.ndjson `RELAY_STARTED`、watcher-heartbeat.json 持续刷新、quarantine/V07-INTEGRATE-2.QUARANTINED-20260829.json。

- decision 2（Brain 激活）：写 brain_bridge.py 复用 strategic_brain_contract.build_proposal（V0.7 Brain，90 测试绿），Goal→Task Graph 自动拆解；非侵入（冻结 runtime.py 零改动），任务 inert（authority=NONE）。
- reason：定义 §7 Brain 需可自动拆 Goal；KEEP > REPAIR，复用已有 90 测试绿模块而非重写。
- evidence：commit b274b4f，brain_bridge 10 测试绿，真实 Goal 拆解出 proposal + Task Graph + human_view。

- decision 3（Capsule 接入）：写 capsule_bridge.py，RUN state.json→机械 Context Capsule（facts + resume instruction），复用 M2 Context Capsule 设计（机械投影、non_authority、§24 记忆不是 Truth）。
- reason：定义 §27 新 AI 接管应机械续跑；M2 只完成模块未接端到端，本会话补上接线。
- evidence：commit 6aeebe3，capsule_bridge 13 测试绿（计数 2026-08-30 口径批刷新 9→13，实测 Ran 13 tests OK），真实 RUN 演示 DONE 续跑指引。

- decision 4（V1.0 判定）：工程判据（§74 中机器验证/Evidence/R PASS/绑定）达成；FINAL DONE 按定义须业主裁决（§74 末条 + 章程 §10），本会话不擅自宣布完成。
- reason：定义明文「任何单一角色声称完成均无效」；防自封是系统灵魂。
- evidence：docs/evidence/V1.0-CLOSE-OUT-REPORT-20260830.md、V1.0-CLOSE-OUT-NOTES-BILINGUAL.md。
- status: ACTIVE（V1.0 收束待业主裁决 E1-E4）

## D018 — 主脑批量裁决 E1-E4 入仓与执行启动（actor=recovery-controller，依据=主脑裁决书 2026-08-30）

- 裁决书：`docs/governance/rulings/v09-close/MAINBRAIN_RULING_E1-E4_BATCH.md`（SHA256 = 4a98499b4690dc79e0262afe1fd4b71190ba79430b0a8a2846d15758afcc33fc，入仓前记录，复制后逐字节 MATCH）
- 裁决要点（E1-E4）：E1 TCB 封印维持后置（第二团审计通过+业主 §74 签字后）；E2 release_status 维持 PRODUCT_NOT_READY；E3 master 汇合原则批准、时点后移（第二团审计通过后按工单原子执行，本批不产生施工动作）；E4 累积清单逐项裁决（CR-1 确认、CR-2 无动作、CR-3 批准低优先级、CR-4 记台账、B-5 勘误、G-2 批准入仓、八vs九=8+GATE23、D-01~09 登记保持现状、F-08 不纳入、P0 备份批准优先、S-02/03/06 业主本人执行）
- 本批执行范围（裁决书 §E）：B-5 勘误 / G-2 ROADMAP 入仓 / P0 备份 / C-1 沙箱破坏演练（禁碰生产状态根）/ C-3 矩阵 v3（§63/§65/§56 降级）/ W-1 只出方案 / 凭据类只出操作清单 / E1/E2/E3 不施工
- 北极星（裁决书 §D）：**自动调度闭环**——至少 1 个真实任务由系统自身完成 提交→拆解→调度→执行→审查→REWORK/PASS→交付，全程无人手动敲 work/report；该目标达成前不得宣称"系统可自动生产"
- status: ACTIVE（本批执行中，完成后出结果块等待第二团审计）

## D019 — 第二团独立审计报告入仓（actor=第二团独立审计者，依据=审计章程 SECOND_TEAM_AUDIT_PACK.md §2）

- 报告：`docs/evidence/audit/AUDIT_REPORT_2026-08-30.md`（本次唯一允许的写；审计全程只读，未修任何东西）
- 审计对象：`v0.9-b1/authority-effect-core @ 52cbc614`（HEAD == origin 同分支，落后/领先 0/0）
- 总判定：**AUDIT_PASS_WITH_REWORK** —— 16 项中 15 PASS / 1 REWORK / 0 BLOCKED；无锚点级问题、无越权改动、无状态造假嫌疑
- REWORK 项（§2-8）：真实 GOAL 计数记录偏差——审计章程称 8 / PROJECT_STATE.md 称 5（两处）/ V1.0-CLOSE-OUT-REPORT 称 4 / MATURITY_REPORT 称 3，四处互不一致；实测点名的 5 个真实 GOAL（ff88/41b4/cfb5/c33e/37d9）**全部 DONE+PASS，实质成立**
- 同类子发现（§2-9 §12）：R 审查/REWORK 轮次记 11，实测 5 个真实 GOAL 的 reply 中 REWORK 判定为 12
- 复核为真的关键判据（全部亲手复跑）：矩阵 36/36 MATCH（MISMATCH=0），R34 与 R34-FAITHFUL 均 FAIL_CLOSED；CLOSE 五件套 40/40 全绿；egress 四向负例 11/11 OK；brain_bridge 10 / capsule_bridge 13 / taskgraph 2 全绿；state_doctor DRIFT_COUNT=1（仅豁免项 registry b1-head 滞后，c6d1a55b→52cbc614 祖先关系已确认）
- 主脑裁决执行六项全部 PASS 且有硬证据：B-5(`98a70a0`, 加注 6 处) / G-2(`d0fb3bd`, 346 行 24196 字节) / C-1(`6b82db8`, 沙箱实存且 `find 状态根 -newermt 16:00` 为空→未碰生产状态根) / C-3(§56/§63/§65 实测均 🟡) / P0 备份(`E:\WB\backups\...P0_BACKUP-20260830-1700` 实存) / W-1(`467d2a9` 仅新增 2 个 md、零代码改动→只方案未施工；Reuse Decision=R=Reuse)
- 77 节自评矩阵未注水：实测 ✅38 / 🟡34 / ❌1（非全绿）；§74 = ❌「工程项达成，业主裁决待定」
- §74 签字建议：**暂不建议签字——补两项计数口径（真实 GOAL 次数、R/REWORK 轮次）后可签**。签字时须明确边界：通过的是工程判据（章程 §10 口径），FINAL DONE 仍须业主裁决（定义 §74 末条，"任何单一角色声称完成均无效"）
- 北极星未达成（实测）：`active_run.txt` 指向已完成的 37d9；`watcher-heartbeat.json` phase_state=COMPLETED 且 mtime 2026-08-30 01:42（审计时 17:18）→ 自动调度闭环尚未达成，相关"系统可自动生产"宣称不应成立
- 方法论留痕（防后续审计误判）：① 章程哈希须按其 §0 口径（剔除"章程身份行："行 + LF 归一）复算，裸哈希=1dec3457…会误判 BLOCKED；② 77 节矩阵为表格行结构，按 `## §N` 标题统计会误判为 8 节；③ RUN 真实路径为 `E:\WB\state\ai-production-control\runtime-v1\runs\`；④ B-5 加注实际措辞为「工程判据（章程 §10），非定义 §74 FINAL DONE」，检索"工程判据非 §74"零命中；⑤ egress"四件套"= 1 文件内 4 个负例方向，非 4 个文件
- status: CLOSED（审计完成入仓，等待业主对 §74 签字与两项计数口径的处置；审计者按章程停止，不修任何东西）

## D020 — 主脑裁决：计数口径统一 + §74 签字路线图入仓（actor=recovery-controller，依据=第二份主脑裁决书 2026-08-30）

- 裁决书：`docs/governance/rulings/v09-close/MAINBRAIN_RULING_COUNT_CALIBRATION_AND_SIGN_ROADMAP.md`（SHA256 = 10045466cf08b92245d16599aa002c8ff7c73d00cf9a81f0616728e919c49679，入仓前记录，复制后逐字节 MATCH）
- 背景：第二团审计 16 项 15 PASS/1 REWORK/0 BLOCKED（D019 已入仓 5e4f86d）；REWORK 项 = 记录层计数口径不一致，非实质缺陷
- B-1：真实 GOAL 权威口径 = 累计 8 次（第一批 3：b173/b718/7cfe + 第二批 5：ff88/41b4/cfb5/c33e/37d9）全部 DONE+PASS；8=累计/5=第二批/4=快照少计/3=连续三次判据；全部回写并保留口径说明，禁止裸数字；真实 GOAL 定义边界（经 Runtime 黑盒真实执行+完整 RUN 目录+R-PROD 终审 PASS）记入 governance 术语表
- B-2：返工轮次 = reply 文件中 ===REVIEW_VERDICT=== REWORK 判定计数；按此重数全部 8 个真实 GOAL 的 reply 并列表回写，替换"11 轮"类旧表述
- B-3：BUILD_MISSION_JOURNAL 补记 8-28~8-30 收束大事更新 updated_at（消 WARN）；capsule_bridge 测试计数台账 9→13 刷新
- §74 签字路线图：口径批（本批）→ 封印（发布负责人=业主或其指定者，施工团不得代封）→ §74 签字（业主；边界=工程判据+十二条件核验，北极星未达成列为 V1.0 后第一目标）→ master 汇合（E3，签字后原子执行）→ v0.9-b1 转 ARCHIVE
- status: ACTIVE（本批=口径批纯文档，完成后停止等业主封印签字）
