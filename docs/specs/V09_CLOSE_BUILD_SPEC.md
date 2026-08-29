# V09_CLOSE_BUILD_SPEC — V0.9 收口正式施工规格

地位：第二阶段唯一施工授权文件（交 Builder 执行；本规格本身不施工）
日期：2026-08-28
产出者：接管主脑（规划角色，不施工）
裁决依据（用户 2026-08-28 裁决，逐条遵守）：
1. b1 重测结果（24 MATCH / 12 RED）为 V0.9 CLOSE 新事实基线；
2. 禁止再用 v0.8 基座 16 RED 直接指导施工；
3. 裁决依据 = v0.9-b1 核心实际语义 + V14-FROZEN 规范；
4. R34 按真实语义处理（未知 effect_type 签发/执行双侧均未拒绝），不得收绿；
5. R22-R24 优先复用/提升现有 `reconcile_effect`，不得未经证明重写；
6. R08/R09/R26/R36 重点 = `store.start_effect` 栅栏/代际语义；
7. R20/R21 = 高优先级 UNKNOWN/静默重放；
8. R32/R06 按 b1 实际接线状态裁决。

规范锚：
- V14-FROZEN，SHA256 `6fe3bb7996a1f78a7d6584d08311c3ebc1aa2d9ffc56c27fc61e8d599e154df6`
  （工作区 `spec-anchor-pack/docs/specs/V14-FROZEN-EXECUTION-SPEC.txt`，T0 入库后为仓库 `docs/specs/` 同名文件）
- 事实基线：`chat-1/b1-remeasure/b1_remeasure_results.json`（协议 V09_B1_REMEASURE_1，
  被测核心 v0.9-b1/authority-effect-core@50cf8bd1，双轮确定性一致）

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
## §0 全局规则（对所有任务强制）

1. 总纪律：**KEEP > REPAIR > SIMPLIFY > REPLACE > REBUILD**。全部任务默认 KEEP/REPAIR：
   在既有函数/事务位点补校验，不新建子系统、不改表结构范式、不重写模块。
2. 只处理本规格列出的案例。**不允许"顺手优化"**：任何不在任务 ALLOWED_FILES 内
   的文件、任何与案例无关的格式/命名/结构调整，一律禁止。
3. 禁止结构性重构 `runtime/runtime.py`（大 ≠ 错；无证据表明阻塞 V0.9）。
4. 禁止开新版本线、禁止 merge、禁止删除分支、禁止推送未经本规格授权的提交。
5. C 类（R18）本规格不授权任何施工；见 `R18_SEMANTIC_ANALYSIS.md`（BLOCKED_BY_SPEC）。
6. D 类（R01/R04/R13）不得视为"已修复无需管理"：必须回归锁定并留证据（§3）。
7. TCB 影响：见 §1（全部代码任务均触碰 TCB，已按证据与规范单独论证）。
8. 施工线：`v0.9-b1/authority-effect-core`（registry 角色 ACTIVE，"work may continue"），
   在其 HEAD（50cf8bd1）上按序追加提交；不创建新分支。每任务一个（或一组紧密相关的）
   提交，提交信息引用 CASE_ID 与本规格文件名。

## §1 TCB_IMPACT（规则 6 要求的单独论证）

受影响 TCB 文件（项目 TCB 定义 = HANDOFF_FOR_GIT_OPERATOR P8：
`src/aicontrol/**`、`ai-control.cmd`、`scripts/ai_control.py`、`config/production.json`、`package-lock.json`）：

| 文件 | 触碰任务 | 必要性论证（规范 + 证据） |
|---|---|---|
| `src/aicontrol/store.py` | T1/T2/T3/T4/T5/T6 | §31 第 4/17/20/22 条为 UNIFIED EFFECT EXECUTION GATE 明列检查，任何失败=DO NOT EXECUTE；缺口实测位于 `store.start_effect` 与 `reserve_effect` 去重路径（b1 重测 R08/R09/R20/R21/R26/R36 = ALLOW 证据）。闸门必须在 canonical 存储层生效，任何旁路包装都可被绕过且违反"统一闸门"公理 |
| `src/aicontrol/controller.py` | T5/T6/T7/T8 | §31 第 8 条（caller capability）、§118 HIGH IMPACT HUMAN GATE、§29/§30 封闭效果模型要求执行链（`execute_effect`）前置校验；b1 已在本文件实现 `_require_existing_authorization` 前置（同构位点，KEEP） |
| `src/aicontrol/security.py` | T7/T8 | §A64（REQUIRED）、§118 判定函数 `human_gate_allowed` 已存在仅缺接线；新增判定须与既有 `authority_scope_allowed` 同层（项目既有布局） |
| `config/production.json` | T8/T9 | b1 已声明 `policy.authority_effect`（含 `high_risk_human_gate: REQUIRED`、`unknown_outcome_ordinary_retry: DENY`）；T9 增加封闭 effect_type 集合。配置是 b1 自己选择的策略载体，接线它=KEEP |

结论：**V0.9 的本质就是权限/效果控制平面的收口，缺口全部位于 TCB 内部；
规范明列检查项 + b1 实测缺口双重证明必须修改。** 后果（必须执行）：
按 STATUS.md 规则，本次全部提交使 TCB 处于 `UNVERIFIED_AFTER_CONTROLLER_CHANGE`，
CLOSE 候选线必须完成 §4 有界回归 + 重封（seal）后才可声明收口；
在此之前任何"可发布"主张无效。

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
## §2 任务清单（按依赖序）

### T0（前置，非代码）规范与测量件入库

- 内容：
  a. 按 `spec-anchor-pack/SPEC_ANCHOR_REPORT.md §2` 既定映射将
     `docs/specs/V14-FROZEN-EXECUTION-SPEC.txt`（逐字节）、两份报告入 `docs/`；
     `PROJECT_STATE.json.spec_registry` 按 `spec-anchor-pack/spec_registry.json` 登记；
     攻击矩阵夹具顶层增补 `spec_anchor`（spec_registry 已指定的唯一夹具改动，仅元数据）。
  b. 把测量件移植到施工线（零语义改动）：
     - `runtime/fixtures/v09_authority_effect_attack_cases.json`（b2@a0ce691 逐字节 + 上述 spec_anchor）
     - `runtime/test_v09_attack_matrix_offline.py`（b2@a0ce691 逐字节，冻结原件）
     - `runtime/test_v09_attack_matrix_on_b1_core.py`（适配运行器：
       现工作区 `b1-remeasure/run_matrix_on_b1.py` 的 AD-1..AD-3 适配，
       另加 T5 要求的 AD-4 重启模拟；适配声明必须写在文件头并逐条引用本规格编号）
- ALLOWED_FILES：`docs/specs/`、`docs/`（两份报告）、`PROJECT_STATE.json`、`PROJECT_STATE.md`、
  `runtime/fixtures/v09_authority_effect_attack_cases.json`、`runtime/test_v09_attack_matrix_offline.py`、
  `runtime/test_v09_attack_matrix_on_b1_core.py`
- FORBIDDEN：任何 `src/`、`runtime/` 其他文件、任何业务逻辑。
- EXIT：doctor 对 spec_registry 不再报 SPEC_NOT_ANCHORED；冻结原件与 b2@a0ce691 逐字节一致（哈希比对入证据）。

---

### TASK-1 栅栏族（T1-T4 同位点：`store.start_effect`，建议一个提交族）

#### CASE_ID: V09-R08（stale_fence）
- SPEC_CLAUSE：§31 第20条 "execution_fence_token current"；§23（execution_fence_token 法定字段）；
  PART III Atomic Reservation（execution fence 在原子清单）；EFFECT_START_COMMITTED "same fence"。
- CURRENT_B1_BEHAVIOR：`start_effect` 只把入参 `reservation.execution_fence_token` 写进 WAL，
  从不与持久化 reservation 行的令牌比对；伪造 "0"*64 → RESERVATION_COMMITTED 直通
  （实测 ALLOW，generation_fence=FORGED_EXECUTION_FENCE）。
- REQUIRED_BEHAVIOR：`start_effect` 必须将入参 execution_fence_token 与持久化
  reservation 行记录的令牌交叉比对；不一致 → `GateDenied`，不转状态、不落
  EFFECT_START_COMMITTED、不写 WAL 成功记录。
- ROOT_CAUSE：栅栏令牌"只记录、不校验"；校验是自洽的（信任入参信封）而非对照持久事实。
- ALLOWED_FILES：`src/aicontrol/store.py`（仅 `start_effect` 位点）、
  `tests/`（新增单测）。
- FORBIDDEN_FILES：`reserve_effect` 的令牌生成逻辑（除非 T2 必需且单独说明）、
  `controller.py`、`runtime/**`、schema 迁移。
- IMPLEMENTATION_BOUNDARY：在既有事务内、既有授权校验序列旁增加一次令牌比对；
  不得引入新表/新令牌体系；不得修改 `Reservation` 数据类。
- TEST_REQUIREMENTS：伪造令牌 → DENY；错配令牌 → DENY；正确令牌 → 正常通过
  （防过度拒绝的正例必须同批提交）。
- REGRESSION_REQUIREMENTS：R07/R14/R15/R16/R17/R25 全部维持原判；`tests/` 既有套件全绿。
- EVIDENCE_REQUIREMENTS：重测 JSONL 该例记录 + 单测运行记录，绑定候选 SHA 与规范 SHA，
  入 `docs/evidence/v09-close/`。
- EXIT_CRITERIA：R08 实测 DENY，且上述回归零破坏。

#### CASE_ID: V09-R09（stale_state_revision）
- SPEC_CLAUSE：§31 第4条 "current Canonical State Revision valid"；§20 STATE_HEAD；
  Atomic Reservation 清单含 "Canonical State"。
- CURRENT_B1_BEHAVIOR：reserve 后 Canonical State revision 变更，`start_effect`
  既不拒绝也不重验证（实测 ALLOW）。
- REQUIRED_BEHAVIOR：`start_effect` 必须校验"当前 Canonical State revision 仍然有效"：
  DENY，或执行显式重验证（重新核对资源/授权/前置条件并记录重验证事件）后放行。
  矩阵接受 `DENY_OR_REVALIDATE` 两者之一；**禁止既不拒绝也不重验证**。
- ROOT_CAUSE：reservation 不与任何 state revision 锚点绑定；执行时无现势性依据可比。
- ALLOWED_FILES：`src/aicontrol/store.py`（`start_effect`，及——仅当现有行无可用锚点字段时——
  `reserve_effect` 记录 state revision 的最小增量）、`tests/`。
- FORBIDDEN_FILES：`controller.py`、`runtime/**`；**schema 迁移仅在确无现有字段可承载时允许，
  且最多为 reservations/actions 增加一个字段，必须在提交说明中论证无替代**。
- IMPLEMENTATION_BOUNDARY：优先方案 = 复用现有记录位（如 WAL/行内已有 revision 信息）；
  重验证路径必须落可审计事件（沿用 `_append_wal`/authority event 既有机制，不新建日志体系）。
- TEST_REQUIREMENTS：revision 变更后 start → DENY 或记录显式重验证事件后放行（二选一，测试断言所选语义）；
  revision 未变 → 正常通过。
- REGRESSION_REQUIREMENTS：栅栏族其余案例与去重案例（R15-R17）不受影响。
- EVIDENCE_REQUIREMENTS：同 R08。
- EXIT_CRITERIA：R09 实测 ∈ {DENY, DENY_OR_REVALIDATE}，回归零破坏。

#### CASE_ID: V09-R26（generation_changes_before_execute）
- SPEC_CLAUSE：§31 第22条 "authorization_generation == latest durable generation"；
  §27A（authority 事件记录 previous_generation/new_generation）。
- CURRENT_B1_BEHAVIOR：`start_effect` 只比对本授权自身行的 generation（故 R07 被拦），
  不与任务级最新持久 generation 比对；新授权签发后旧 reservation 直通（实测 ALLOW，
  TASK_AUTH_GENERATION_ADVANCED）。
- REQUIRED_BEHAVIOR：`start_effect` 必须校验 reservation 绑定的 authorization_generation
  == 该任务最新持久授权 generation；落后 → `GateDenied`。
- ROOT_CAUSE：generation 校验是"自洽"的（与自己的行比），缺少"与任务最新事实比"。
- ALLOWED_FILES：`src/aicontrol/store.py`（`start_effect`）、`tests/`。
- FORBIDDEN_FILES：generation 分配逻辑（`_next_generation`）不得改动；`controller.py`、`runtime/**`。
- IMPLEMENTATION_BOUNDARY：在既有事务内查询任务最新 generation（authorizations 表或
  authority journal 重建，二者择一，与 `reconstruct_authority` 既有机制一致）后比对；
  不引入新表。
- TEST_REQUIREMENTS：任务级 generation 推进后旧 reservation → DENY；generation 未推进 → 通过；
  R07 的单授权篡改场景仍被拦（双重断言）。
- REGRESSION_REQUIREMENTS：R07/R10/R11/R12/R25 维持。
- EVIDENCE_REQUIREMENTS：同 R08。
- EXIT_CRITERIA：R26 实测 DENY，回归零破坏。

#### CASE_ID: V09-R36（stale_process_after_generation_takeover）
- SPEC_CLAUSE：§31 第19/20/22 条；§27A Authority Monotonic Recovery Rule
  （陈旧权威不得复活）。
- CURRENT_B1_BEHAVIOR：接管（新授权签发=世代推进）后，陈旧进程持原 reservation
  调 `start_effect` 直通（实测 ALLOW，STALE_PROCESS_AFTER_TAKEOVER）。
- REQUIRED_BEHAVIOR：接管发生后（以任务级授权世代推进为权威信号），
  陈旧世代的 reservation 不得再获得执行资格 → `GateDenied`。
- ROOT_CAUSE：与 R26 同根；接管场景是世代推进的变体（攻击夹具以新授权签发模拟接管）。
  T3 的任务级 generation 现势校验应同时覆盖本例——若实测仍未覆盖（例如存在不经
  generation 的接管路径），才允许补充进程现势校验，且必须在提交说明中给出实测证据。
- ALLOWED_FILES：`src/aicontrol/store.py`（`start_effect`）、`tests/`。
- FORBIDDEN_FILES：租约/进程身份基础设施（`_lease`、process_start_identity 机制）不得重构。
- IMPLEMENTATION_BOUNDARY：优先复用 T3 校验（禁止为同一语义建两道重复闸门）；
  如补进程校验，仅限在既有 `_lease` 校验位点旁增加现势比对。
- TEST_REQUIREMENTS：接管后陈旧 reservation → DENY；接管前正常执行 → 通过。
- REGRESSION_REQUIREMENTS：R26 修复不得被本任务破坏；租约相关既有测试全绿。
- EVIDENCE_REQUIREMENTS：同 R08。
- EXIT_CRITERIA：R36 实测 DENY，回归零破坏。

---

### TASK-2 UNKNOWN 闸门（T5/T6，CROWN，高优先级）

#### CASE_ID: V09-R20（unknown_ordinary_retry）
- SPEC_CLAUSE：§23（OUTCOME_UNKNOWN 法定未决态）；§26（RECONCILE_REQUIRED/NEVER_AUTO_RETRY
  前置链）；§31 第17条 "no unresolved/in-flight same logical effect"；
  EXTERNAL_EFFECT_SEMANTICS（UNKNOWN outcome 边界）。
- CURRENT_B1_BEHAVIOR：OUTCOME_UNKNOWN 未决时普通重试走 `reserve_effect` 去重 →
  `execute_effect` L382-383 静默返回 `{"deduplicated": True}`（=静默重发语义），
  实测 ALLOW。b1 config 已声明 `unknown_outcome_ordinary_retry: DENY`——策略已声明、执行未落地。
- REQUIRED_BEHAVIOR：同一逻辑效果存在未决 OUTCOME_UNKNOWN（或 RECONCILING）动作时，
  **同一 Controller 实例**的再次执行必须 `GateDenied`（消息含 reconcile/unknown 语义），
  不得返回静默去重结果，不得触碰外部边界。
- ROOT_CAUSE：去重判定与动作状态解耦——dedup 路径不读前一动作的终局状态；
  `execute_effect` 对 deduplicated 无状态条件直接返回；config 策略无执行点。
  （对照先例：b1 `execute_workbuddy_fallback` L486-489 已对 dedup/unknown 抛
  `AuthorityStateUncertain`——同构处置已有项目内先例，KEEP 该模式。）
- ALLOWED_FILES：`src/aicontrol/store.py`（`reserve_effect` 去重分支）、
  `src/aicontrol/controller.py`（`execute_effect` dedup 返回路径）、`tests/`。
- FORBIDDEN_FILES：WAL/状态机既有状态集合不得改名；`runtime/**`；
  不得改动 R16/R17 的合法去重语义（仅对"前动作为 UNKNOWN/RECONCILING"增加闸门）。
- IMPLEMENTATION_BOUNDARY：在去重命中点读取前一动作状态；仅当前动作 ∈
  {OUTCOME_UNKNOWN, RECONCILING} 时拒绝；拒绝消息必须可被矩阵判据识别
  （GateDenied 或文本含 reconcile/unknown）。"同实例=普通重试"以
  controller_instance_id 判定（与既有行记录一致，不新建会话概念）。
- TEST_REQUIREMENTS：UNKNOWN 后同实例重试 → DENY；SUCCESS 终局后的同身份重放 →
  仍按 R16/R17 去重（正例，防过度拒绝）；UNKNOWN 已对账后（TASK-3）的受控路径不受影响。
- REGRESSION_REQUIREMENTS：R15/R16/R17/R19 维持；全量矩阵与套件按 §4。
- EVIDENCE_REQUIREMENTS：同 R08；CROWN 案例须单独在裁决记录中标注。
- EXIT_CRITERIA：R20 实测 DENY，R16/R17 不退化。

#### CASE_ID: V09-R21（restart_while_unknown，A 依赖 B）
- SPEC_CLAUSE：§27 WAL Crash Recovery 链（reconcile uncertain effects → resume safe actions）；
  §23（RECONCILING 法定态）；§27A（恢复后 only then permit new production effects）。
- CURRENT_B1_BEHAVIOR：UNKNOWN 未决、重启后重放 → 直接静默去重，
  无 `reconciliation_required` 标记（实测 DEDUPLICATED_WITHOUT_RECONCILE）。
- REQUIRED_BEHAVIOR：**不同 Controller 实例**（重启/恢复后的进程）重放同一逻辑效果时，
  不得静默去重、不得再次执行，必须返回/记录 `reconciliation_required=True`
  （外部效果计数保持 1）；实际重试只在 TASK-3 对账完成后以新显式授权进行。
- ROOT_CAUSE：恢复路径与普通重试路径在去重点未分化；缺少"实例身份变化 =
  恢复场景"的判据。判据选择依据 §27A 进程/世代语义：重启 ⇒ 新
  controller_instance_id/process_start_identity（既有持久字段，无需新基础设施）。
- ALLOWED_FILES：`src/aicontrol/store.py`（去重分支）、`src/aicontrol/controller.py`
  （`execute_effect`）、`tests/`、`runtime/test_v09_attack_matrix_on_b1_core.py`
  （AD-4：以同一 state root 新建 Controller 实例模拟重启——测量侧适配，必须在
  适配声明中登记）。
- FORBIDDEN_FILES：崩溃恢复既有驱动（`runtime/runtime.py` 恢复流程）不得改动；
  不得在本任务实现完整对账（对账 = TASK-3，防止范围蔓延）。
- IMPLEMENTATION_BOUNDARY：去重命中且前动作 UNKNOWN/RECONCILING 时：
  请求方实例 == 记录实例 → 按 T5 拒绝（R20）；请求方实例 ≠ 记录实例 →
  返回带 `reconciliation_required=True` 的结果（不执行、不重复计数）。
- TEST_REQUIREMENTS：单测显式构造"新实例重放"场景断言标记与零重复执行；
  矩阵重测该例 = RECONCILE_FIRST。
- REGRESSION_REQUIREMENTS：R19/R20 不受影响；恢复相关既有测试全绿。
- EVIDENCE_REQUIREMENTS：同 R08。
- EXIT_CRITERIA：R21 实测 RECONCILE_FIRST，零重复外部效果。

---

### TASK-3 canonical 对账最小实现（T7 = R22/R23/R24，B 类最小必要能力）

复用约束（用户裁决 5）：语义规则必须复用/对齐 `runtime/effect_safety_lite.reconcile_effect`
已实现的保守语义——仅允许对 OUTCOME_UNKNOWN 对账、evidence 必填且非空、
`ordinary_retry_permitted=False`、负向观察不产生重放权限（"受控重试需新显式授权"）。
禁止另起状态机、禁止新存储后端（§27A 明令"不要求新的大型基础设施"）。
事件命名沿用运行时层既有名（EFFECT_RECONCILED_SUCCESS / EFFECT_RECONCILED_NOT_OCCURRED）。

#### CASE_ID: V09-R22（reconcile_already_succeeded，CROWN）
- SPEC_CLAUSE：§23 ACTION LEDGER（RECONCILING→OUTCOME_OBSERVED→ACTION_COMMITTED）；§27 恢复链。
- CURRENT_B1_BEHAVIOR：canonical 层（controller/store）无任何对账方法
  （矩阵探测 6 候选名全缺失，实测 UNSUPPORTED / NO_RECONCILIATION_API）。
- REQUIRED_BEHAVIOR：提供 `Controller.reconcile_effect`（命名命中矩阵候选探测）：
  对账证据表明外部已发生 → 动作置为 §23 链终态 `ACTION_COMMITTED`
  （经 OUTCOME_OBSERVED），**不得再次执行**（外部效果计数保持 1）。
- ROOT_CAUSE：canonical 对账子系统缺失（能力缺失，非闸门漏洞）。
- ALLOWED_FILES：`src/aicontrol/controller.py`（新方法）、`src/aicontrol/store.py`
  （对账状态推进的存储助手）、`tests/`。
- FORBIDDEN_FILES：`runtime/**` 既有 reconcile_effect 不得改写（它是复用参照物）；
  不得引入新表（使用 actions/WAL/authority event 既有结构）。
- IMPLEMENTATION_BOUNDARY：前置校验 = 动作状态必须为 OUTCOME_UNKNOWN（否则拒绝）；
  evidence 必填非空；状态推进经既有事务与 WAL/authority 事件；返回结构化结果
  （含状态与 "COMMITTED/NO_EXECUTE" 语义，供矩阵判据识别）。
- TEST_REQUIREMENTS：已发生 → ACTION_COMMITTED 且零再执行；非 UNKNOWN 状态调用 → 拒绝；
  空证据 → 拒绝。
- REGRESSION_REQUIREMENTS：R19-R21 不受影响。
- EVIDENCE_REQUIREMENTS：同 R08。
- EXIT_CRITERIA：R22 实测 COMMIT_SUCCESS_NO_EXECUTE。

#### CASE_ID: V09-R23（reconcile_definitely_not_occurred，CROWN）
- SPEC_CLAUSE：§23/§27；EXTERNAL_EFFECT_SEMANTICS（provider-idempotent effects 边界）。
- CURRENT_B1_BEHAVIOR：同 R22（UNSUPPORTED）。
- REQUIRED_BEHAVIOR：对账确认确定未发生 → 仅允许**受控重试**：
  返回受控重试语义结果（不自动重试、本次零外部效果）；任何后续重试必须走
  新显式授权 + 新 attempt（与运行时层"负向观察非重放权限"语义一致）。
- ROOT_CAUSE：同 R22。
- ALLOWED_FILES / FORBIDDEN_FILES / IMPLEMENTATION_BOUNDARY：同 R22（同一方法的状态分支）。
- TEST_REQUIREMENTS：未发生 → 零执行 + 受控重试语义；断言无自动重试发生。
- REGRESSION_REQUIREMENTS：同 R22。
- EVIDENCE_REQUIREMENTS：同 R08。
- EXIT_CRITERIA：R23 实测 CONTROLLED_RETRY_ONLY。

#### CASE_ID: V09-R24（reality_indeterminate，CROWN）
- SPEC_CLAUSE：§105/§118 Human Gate；EXTERNAL_EFFECT_SEMANTICS（UNKNOWN outcome boundaries、
  不得宣称所有互联网效果 exactly-once）；§31 第17条。
- CURRENT_B1_BEHAVIOR：同 R22（UNSUPPORTED）。
- REQUIRED_BEHAVIOR：外部现实无法判定 → 动作**停留 OUTCOME_UNKNOWN**（或升级 Human Gate
  语义记录），返回含 human/unknown/indeterminate 语义的结果；不得自动升级任何执行动作。
- ROOT_CAUSE：同 R22。
- ALLOWED_FILES / FORBIDDEN_FILES / IMPLEMENTATION_BOUNDARY：同 R22（同一方法的状态分支）。
- TEST_REQUIREMENTS：无法判定 → 状态不变（仍 OUTCOME_UNKNOWN）+ 保守结果；零执行。
- REGRESSION_REQUIREMENTS：同 R22。
- EVIDENCE_REQUIREMENTS：同 R08。
- EXIT_CRITERIA：R24 实测 STAY_UNKNOWN_OR_HUMAN_GATE。

---

### TASK-4 分类闸门接线（T8 = R32；T9 = R34）

#### CASE_ID: V09-R32（high_risk_without_human_gate）
- SPEC_CLAUSE：§118 HIGH IMPACT HUMAN GATE（付款/公开发布/高风险不可逆…必须 Gate）；
  §30（付款 = NEVER_AUTO_RETRY/HIGH/IRREVERSIBLE）；§105。
- CURRENT_B1_BEHAVIOR：`security.human_gate_allowed` 已实现且 b1 自测通过，
  但 `execute_effect` 完全未接线；HIGH+IRREVERSIBLE 无令牌直通（实测 ALLOW）。
  config 已声明 `high_risk_human_gate: REQUIRED`——策略已声明、执行未落地。
- REQUIRED_BEHAVIOR：intent 标记 `impact=HIGH` 或 `reversibility=IRREVERSIBLE` 时，
  `execute_effect` 必须以 `human_gate_allowed(required=True, reference=<intent 携带的
  human_gate_reference>)` 前置校验；引用缺失/空白 → `GateDenied`。
  LOW/可逆效果不受影响（不得扩大打击面）。
- ROOT_CAUSE：判定函数存在但未接入执行链；高危分类直通。
- ALLOWED_FILES：`src/aicontrol/controller.py`（`execute_effect` 前置，
  与 `_require_existing_authorization` 同层）、`tests/`。
- FORBIDDEN_FILES：`security.py` 的 `human_gate_allowed` 语义不得改动（已测通过）；
  `runtime/**`。
- IMPLEMENTATION_BOUNDARY：仅在既有前置序列增加一个判定调用；引用来源 =
  intent 显式字段（缺失视为未提供）；不在本任务重设授权签发流程
  （高危授权与 human gate 的深度绑定若需要，另行立项，防范围蔓延）。
- TEST_REQUIREMENTS：HIGH+IRREVERSIBLE 无引用 → DENY；携带非空引用 → 通过；
  LOW+REVERSIBLE 无引用 → 通过（正例防过度拒绝）。
- REGRESSION_REQUIREMENTS：既有矩阵全部 LOW 案例不受影响；b1 自测套件全绿。
- EVIDENCE_REQUIREMENTS：同 R08。
- EXIT_CRITERIA：R32 实测 DENY，正例通过。

#### CASE_ID: V09-R34（unknown_effect_type）
- SPEC_CLAUSE：§29/§30 EFFECT MODEL（封闭分类）；Authorization Replay Protection
  （effect_type 为法定记录字段）；项目级 fail-closed 宣言（STATUS：malformed inputs fail closed）。
- CURRENT_B1_BEHAVIOR（用户裁决 4 指定的真实语义）：
  矩阵原走法因"授权与 intent 类型不一致"碰巧被拒（表面匹配）；
  忠实探针证明**未知 effect_type 在签发侧（grant）与执行侧（execute）均被接受**
  （授权与 intent 同为 TOTALLY_UNKNOWN_EFFECT_TYPE 时端到端 ALLOW，实测证据在
  b1_remeasure_results.json extra_probes）。不得收绿。
- REQUIRED_BEHAVIOR：**双侧 fail-closed**——
  签发侧：`store.grant_authorization` 对不在封闭集合内的 effect_type 拒绝；
  执行侧：`execute_effect`（或其前置授权校验）再次校验，未知类型拒绝
  （防策略收紧前签发的旧授权复活，§27A 单调性方向一致）。
- ROOT_CAUSE：effect_type 无封闭集合概念，任意字符串被接受。
- ALLOWED_FILES：`src/aicontrol/store.py`（`grant_authorization`）、
  `src/aicontrol/controller.py`（执行侧校验）、`src/aicontrol/security.py`
  （如需集中放置封闭集合判定函数）、`config/production.json`
  （`policy.authority_effect.known_effect_types` 封闭集合）、`tests/`。
- FORBIDDEN_FILES：`runtime/**`；既有合法类型的语义不得改变。
- IMPLEMENTATION_BOUNDARY：
  1) 封闭集合以 config 承载，**初始集合必须先盘点既有合法用法**（至少包含
     b1 `execute_workbuddy_fallback` 使用的 `AI_MESSAGE` 与矩阵夹具所用类型；
     盘点清单写入提交说明），防止把既有绿色流程打成 RED；
  2) 集合变更属于策略变更，须在 DECISION_LEDGER 留痕（沿用项目制度）；
  3) 不得借此引入效果分类学重构（只加封闭性，不动分类语义）。
- TEST_REQUIREMENTS：未知类型签发 → DENY；未知类型执行（持旧式授权模拟）→ DENY；
  集合内类型端到端 → 通过（含 fallback 流程正例）。
- REGRESSION_REQUIREMENTS：b1 fallback Brain 流程（使用 AI_MESSAGE）必须保持绿；
  矩阵 R34 原走法与忠实探针双路径实测均 = FAIL_CLOSED。
- EVIDENCE_REQUIREMENTS：同 R08；裁决记录必须同时引用"表面匹配"与"忠实探针"两条证据，
  说明为何按真实语义定性。
- EXIT_CRITERIA：R34 及忠实探针均实测拒绝，既有类型零回归。

---

### TASK-5 调用者角色绑定（T10 = R06）

#### CASE_ID: V09-R06（worker_role_mismatch）
- SPEC_CLAUSE：§31 第8条 "caller capability permits effect"；§A64 Privileged Worker
  External-Effect Bypass（REQUIRED）；INVOCATION RECEIPT（expected_actor_id/actor_type/trust class）。
- CURRENT_B1_BEHAVIOR：intent.critical_params 携带 `role=UNAUTHORIZED_ROLE` 直通执行
  （实测 ALLOW，external_effect_count=1）。
- REQUIRED_BEHAVIOR：效果声明了调用者角色（critical_params.role 存在）时，
  该角色必须被授权 scope 显式允许，否则 `GateDenied`；
  效果声明了角色而授权无角色绑定 → `GateDenied`（fail-closed）。
  未声明角色的效果不受影响（最小打击面）。
- ROOT_CAUSE：执行链不校验调用者角色载体；§A64 防护缺失。
- ALLOWED_FILES：`src/aicontrol/controller.py`（`execute_effect` 前置）、
  `src/aicontrol/security.py`（新增最小判定函数，与 `authority_scope_allowed` 同层）、
  `tests/`。
- FORBIDDEN_FILES：`store.py`（本案例不改存储）；`runtime/**`；
  不得在本任务建立完整信任分类体系（§A64 的最小闭环即可，体系化属后续版本）。
- IMPLEMENTATION_BOUNDARY：角色载体 = `critical_params.role`（矩阵攻击的既有载体，
  不另造字段）；授权侧载体 = scope 内显式允许角色列表（新增可选字段，
  缺省 = 不允许任何声明角色 = fail-closed）；判定为纯函数，便于测试与复用。
- TEST_REQUIREMENTS：未授权角色 → DENY；授权允许的角色 → 通过；
  未声明角色 → 通过（正例，保护既有绿色案例）。
- REGRESSION_REQUIREMENTS：R02-R05（scope 族）不受影响；全量矩阵按 §4。
- EVIDENCE_REQUIREMENTS：同 R08。
- EXIT_CRITERIA：R06 实测 DENY，正例通过。

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
## §3 D 类：b1 已关闭案例的回归锁定（不施工，只锁证据）

| CASE_ID | b1 实测 | 锁定要求 |
|---|---|---|
| V09-R01 no_authorization | DENY（rc=86，零签发） | CLOSE 线重测必须保持；裁决记录绑定 Human Gate Trust Root + §31 第1条 |
| V09-R04 resource_mismatch | DENY（scope 全集绑定） | 同上；绑定 §31 第2条 + Authorization Replay Protection |
| V09-R13 executor_self_grant | DENY（Controller self-grant is forbidden） | 同上；且任何任务不得恢复 `scoped_authorization` 的签发能力（本条为永久约束，写入裁决记录） |

D 类不是"已修复无需管理"：若 CLOSE 线重测出现任何 D 类退化，视同施工事故，
立即停止并按 §5 HARD STOP 上报。

## §4 全局回归与证据要求（对整条 CLOSE 线）

REGRESSION_REQUIREMENTS（每批次提交后 + 最终收口各跑一次）：
1. 36 例攻击矩阵（适配运行器，AD-1..AD-4）：A 类 9 例全部匹配期望；
   B 类 3 例达到最小语义；D 类 3 例保持；R18 记录为 BLOCKED_BY_SPEC 原样（不施工、不判定）。
2. 冻结原件运行器（逐字节版）允许继续报告其固有失配（它是 v0.8 时代测量件），
   但**收口判定以适配运行器 + 逐案裁决记录为准**。
3. 施工线全量离线套件：`runtime/` 与 `tests/` 下既有全部离线测试
   （含 b1 自测 14+13、effect_safety 套件、v0.8 三件套 44/44、27/27、36+1 对应件）全绿。
4. `python scripts/state_doctor.py` = DRIFT_FREE（PROJECT_STATE 更新后）。

EVIDENCE_REQUIREMENTS（入 `docs/evidence/v09-close/`，新建目录，追加式）：
1. `v09-close-remeasure-<candidate-sha8>.jsonl`：协议 V09_ATTACK_RESULT_JSONL_1，
   逐案绑定 candidate SHA 与规范 SHA（`sha256:6fe3bb79...954df6`）。
2. `v09-close-adjudication-<candidate-sha8>.md`：36 案逐案裁决记录
   （CASE_ID / SPEC_CLAUSE 引文 / 实测值 / 分类 / 裁决人=用户裁决日期）。
3. 独立审查记录（**首次入库**，PHASE 1 EXIT 要求）：审查者必须与 Builder 不同模型，
   裁决绑定 candidate SHA + 证据路径。
4. PROJECT_STATE / branch_registry / DECISION_LEDGER / BUILD_MISSION_JOURNAL
   同步更新（状态权威化纪律，延续 Phase 0 模式；PROJECT_STATE.current_stage
   推进与 release_status 维持按既有规则）。

## §5 HARD STOP（Builder 遇下列任一情况立即停止上报，不得变通）

- 任一任务需要触碰其 FORBIDDEN_FILES 才能完成；
- 需要 schema 迁移且超出 T2 声明的"单字段上限"；
- D 类（R01/R04/R13）出现退化；
- 矩阵适配（AD-1..AD-4）之外需要改动冻结测量件语义；
- 任何案例的修复需要扩大本规格声明的语义边界（例如给 R32 增加授权签发流程改造）；
- R18 收到任何施工请求（无论来源）——必须先有用户对 `R18_SEMANTIC_ANALYSIS.md` 的裁决；
- 发现本规格与 V14-FROZEN 原文冲突——以规范原文为准，停下上报。

## §6 全局 EXIT_CRITERIA（V0.9 CLOSE 收口判据）

不是"所有测试变绿"，而是**规范、实现、测试、Evidence 四者语义闭合**，可逐项证明：
1. 权限不能自我扩权（R01/R13 锁定 + `scoped_authorization` 永不签发的永久约束入记录）；
2. 未知 effect_type 在签发与执行**两侧**都 fail-closed（R34 双路径证据）；
3. 高危副作用需要正确的 human gate（R32 证据 + 正例）；
4. stale / old generation 不能重新获得有效副作用资格（R07/R08/R09/R26/R36 证据）；
5. UNKNOWN 副作用有明确 reconciliation 语义（R19-R24 证据，含受控重试与保守停留）；
6. 角色与资源绑定有效（R04/R06 证据）；
7. 已有能力不因 V0.9 修复而回归（§4.3 全量套件 + D 类锁定 + R16/R17 去重正例）；
8. TCB 重封完成（有界回归 + seal 记录；`UNVERIFIED_AFTER_CONTROLLER_CHANGE` 解除）；
9. 独立审查记录首次入库；
10. `RELEASE_STATUS` 维持 `PRODUCT_NOT_READY`（CLOSE 收口 ≠ 发布就绪；
    谁也不得因本规格的执行宣称可发布）。

任务依赖序：T0 → TASK-1（T1-T4）→ TASK-2（T5/T6）→ TASK-3（T7）→ TASK-4（T8/T9）→ TASK-5（T10）→ §4 全局验证。
（TASK-1..TASK-5 之间无硬依赖的可用并行提交序，但每批必须过当批回归。）
