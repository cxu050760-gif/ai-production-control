# RED_ADJUDICATION_MATRIX — V0.9 十六例 RED 逐例裁决索引

裁决依据：V14-FROZEN（SHA256 6fe3bb79...954df6，见 SPEC_ANCHOR_REPORT §1）
测量对象：v0.9-b2 树 = v0.8 接受基座（未含 b1 升级核心）+ B2 测量件
测量方式：规划者会话实测复现（2026-08-28），CURRENT_RESULT 均为实测值
分级说明：A=真实语义缺口（必须修）｜B=能力缺失（需设计实现）｜C=期望需规范裁决
重要前提：以下"缺口"是对 v0.8 基座的测量；b1 升级核心对除自我授权类之外案例的
效果为 UNPROVEN（矩阵与 b1 核心的兼容适配是 V0.9 CLOSE 的前置工作）。

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

### CASE_ID: V09-R01
- EXPECTED_BEHAVIOR: 无授权时，运行时传输层 send 必须 DENY（HARD_BLOCKED，不外发）
- SPEC_CLAUSE: Human Gate Trust Root（授权只能来自用户正式受控入口确认后生成）；§31 闸门第1条 "latest durable authorization exists"；失败 = DO NOT EXECUTE EFFECT
- CURRENT_IMPLEMENTATION: `runtime/effect_safety_lite.py` install→gated_cmd_send→ensure_valid_authorization（L105-111：无有效授权时调用 grant_authorization 自我签发）
- CURRENT_RESULT: ALLOW（实测：runtime_rc=0，authorization_count=1，external_effect_count=1）
- CLASSIFICATION: A
- RATIONALE: 自我签发直接违反 Trust Root；模块 docstring 自认此为延迟加固项；b1 核心已实证封死此类（试跑返回 GateDenied: Controller self-grant is forbidden）——修复路径已知，属必须修的语义缺口。

### CASE_ID: V09-R04
- EXPECTED_BEHAVIOR: 授权绑定 destination-a/resource-a 后，intent 改为 destination-b/resource-b 必须 DENY
- SPEC_CLAUSE: §31 闸门第2条 "scope matches"；Authorization Replay Protection（授权记录含 scope/resource）；LOGICAL_EFFECT_SAFETY "authorization consumption"
- CURRENT_IMPLEMENTATION: `src/aicontrol` execute 链校验 provider/purpose/task（R02/R03/R05 因此 PASS），但未校验 destination/resource 与授权 scope 的匹配
- CURRENT_RESULT: ALLOW（实测：external_effect_count=1，authorization_identity=NONE 记录缺失）
- CLASSIFICATION: A
- RATIONALE: 闸门第2条要求 scope 完整匹配；resource 绑定缺失是明确语义缺口（R02 provider 被拦而 R04 resource 放行，证明校验只覆盖半集）。

### CASE_ID: V09-R06
- EXPECTED_BEHAVIOR: critical_params 携带 role=UNAUTHORIZED_ROLE 的效果必须 DENY
- SPEC_CLAUSE: §31 闸门第8条 "caller capability permits effect"；§A64 Privileged Worker External-Effect Bypass（REQUIRED）；INVOCATION RECEIPT（expected_actor_id/actor_type/trust class）
- CURRENT_IMPLEMENTATION: execute 链不校验 critical_params 内的调用者角色/身份
- CURRENT_RESULT: ALLOW（实测：external_effect_count=1）
- CLASSIFICATION: A
- RATIONALE: A64 是 REQUIRED 验收类别；特权绕过防护缺失。角色以何字段为载体属实现细节，但"未授权角色不得产生效果"的规范方向明确。

### CASE_ID: V09-R08
- EXPECTED_BEHAVIOR: 以伪造 execution_fence_token（"0"*64）调用 start_effect 必须 DENY
- SPEC_CLAUSE: §23 ACTION LEDGER（execution_fence_token 为法定字段）；§31 闸门第20条 "execution_fence_token current"；PART III Atomic Reservation（execution fence 在原子预留清单内）
- CURRENT_IMPLEMENTATION: `store.start_effect` 不校验 reservation 的 execution fence 完整性/现势性
- CURRENT_RESULT: ALLOW（实测：RESERVATION_COMMITTED，generation_fence=FORGED_EXECUTION_FENCE）
- CLASSIFICATION: A
- RATIONALE: 闸门第20条在规范中存在而实现未校验；伪造栅栏通过 = 明确语义缺口。

### CASE_ID: V09-R09
- EXPECTED_BEHAVIOR: reserve 后 Canonical State revision 发生变化，start_effect 必须 DENY 或显式重验证
- SPEC_CLAUSE: §31 闸门第4条 "current Canonical State Revision valid"；§20 STATE_HEAD 原子推进
- CURRENT_IMPLEMENTATION: start_effect 不与当前 state revision 比对
- CURRENT_RESULT: ALLOW（期望为 DENY_OR_REVALIDATE，实测两者皆无）
- CLASSIFICATION: A
- RATIONALE: 闸门第4条未实现；期望已容忍"重验证"替代拒绝，但实现既不拒绝也不重验证。

### CASE_ID: V09-R13
- EXPECTED_BEHAVIOR: 执行器在无外部授予时调用授权接口必须 DENY
- SPEC_CLAUSE: Human Gate Trust Root（"用户通过正式受控入口确认后，才能生成 Authorization"）；Authorization Replay Protection（decision_nonce 要求）
- CURRENT_IMPLEMENTATION: `runtime/effect_safety_lite.py:ensure_valid_authorization`（L105-111）空授权表时自动签发，holder=executor 亦被接受
- CURRENT_RESULT: ALLOW（实测：授权成功生成）
- CLASSIFICATION: A
- RATIONALE: 与 R01 同根（自我签发）；规范条文直接禁止；b1 核心已实现该禁令（实证），修复路径已知。

### CASE_ID: V09-R18
- EXPECTED_BEHAVIOR: 同一 logical_effect_slot 携带不同 payload 的第二次执行 → CONFLICT 或 DENY（矩阵期望）
- SPEC_CLAUSE: LOGICAL EFFECT IDENTITY（slot 为身份组成）；Effect Intent Hash 绑定 slot；§31 闸门第17条 "no unresolved/in-flight same logical effect"。注意：V14 未明文规定"同 slot 异 payload 必须拒绝"
- CURRENT_IMPLEMENTATION: 去重身份 = hash(run_id, slot, payload_hash)——payload 不同则身份不同，两次执行均为合法新效果
- CURRENT_RESULT: ALLOW（实测：external_effect_count=2，无冲突检测）
- CLASSIFICATION: C
- RATIONALE: 规范存在两种合法解读：slot=每槽一个意图（应冲突）或 slot=去重分区键（当前行为合法）。矩阵期望是单方面解读而非规范引文——必须由规范裁决（用户/设计师拍板）后才能定性，禁止按 A 施工。

### CASE_ID: V09-R20（CROWN）
- EXPECTED_BEHAVIOR: OUTCOME_UNKNOWN 之后对同一效果的普通重试必须 DENY（须先走对账/显式处理）
- SPEC_CLAUSE: §23 ACTION LEDGER（OUTCOME_UNKNOWN 为法定未决态）；§31 闸门第17条；§26 RECONCILE_REQUIRED 前置链；§30（网页 AI message = RECONCILE_REQUIRED）；EXTERNAL_EFFECT_SEMANTICS（UNKNOWN outcome 边界）
- CURRENT_IMPLEMENTATION: 重放按 logical_effect_id 直接去重（deduplicated=True）返回，无 UNKNOWN 态闸门
- CURRENT_RESULT: ALLOW（实测：detail="ordinary retry returned deduplicated=True"）
- CLASSIFICATION: A
- RATIONALE: UNKNOWN 是法定未决态，第17条禁止未决同效果再执行；静默去重=静默重发，违反 RECONCILE_REQUIRED 语义。Crown 案例，最高优先。

### CASE_ID: V09-R21（CROWN，A/B 混合，主分类 A）
- EXPECTED_BEHAVIOR: UNKNOWN 未决时重启后重放同效果 → 必须先对账（RECONCILE_FIRST），不得直接去重
- SPEC_CLAUSE: §27 WAL Crash Recovery 链（"reconcile uncertain effects → resume safe actions"）；§23 RECONCILING 法定态
- CURRENT_IMPLEMENTATION: 重放无 reconciliation_required 标记，直接去重放行
- CURRENT_RESULT: DEDUPLICATED_WITHOUT_RECONCILE（实测：reconciliation_result=REQUIRED）
- CLASSIFICATION: A（依赖 B）
- RATIONALE: 恢复链明确要求先对账后恢复安全动作——闸门语义缺失为 A；落地依赖对账能力（B）。

### CASE_ID: V09-R22（CROWN）
- EXPECTED_BEHAVIOR: 对账确认外部已发生 → 直接置 ACTION_COMMITTED，不得再次执行（COMMIT_SUCCESS_NO_EXECUTE）
- SPEC_CLAUSE: §23 ACTION LEDGER（RECONCILING→OUTCOME_OBSERVED→ACTION_COMMITTED）；§27 恢复链
- CURRENT_IMPLEMENTATION: 对账接口不存在——测试探测 6 个候选方法名（controller/store × reconcile_effect/unknown_effect/outcome）全部缺失
- CURRENT_RESULT: UNSUPPORTED（实测：reconciliation_result=NO_RECONCILIATION_API）
- CLASSIFICATION: B
- RATIONALE: 非闸门漏洞，是整个对账子系统未实现；需要设计（探测形态、状态机、证据记录）后实现。

### CASE_ID: V09-R23（CROWN）
- EXPECTED_BEHAVIOR: 对账确认确定未发生 → 仅允许受控重试（CONTROLLED_RETRY_ONLY）
- SPEC_CLAUSE: 同 R22（§27/§23）；EXTERNAL_EFFECT_SEMANTICS（provider-idempotent effects 边界）
- CURRENT_IMPLEMENTATION: 同 R22，NO_RECONCILIATION_API
- CURRENT_RESULT: UNSUPPORTED
- CLASSIFICATION: B
- RATIONALE: 同 R22——对账能力缺失，需设计实现。

### CASE_ID: V09-R24（CROWN）
- EXPECTED_BEHAVIOR: 外部现实无法判定 → 停留 OUTCOME_UNKNOWN 或升级 Human Gate
- SPEC_CLAUSE: §105/§118 Human Gate；EXTERNAL_EFFECT_SEMANTICS（"UNKNOWN outcome boundaries"、不得宣称所有互联网效果 exactly-once）；§31 第17条
- CURRENT_IMPLEMENTATION: 同 R22，NO_RECONCILIATION_API
- CURRENT_RESULT: UNSUPPORTED
- CLASSIFICATION: B
- RATIONALE: 同 R22；"无法判定→不自动升级动作"是规范明令的保守语义。

### CASE_ID: V09-R26
- EXPECTED_BEHAVIOR: reserve 后任务授权世代推进（新授权签发），旧 reservation 的 start_effect 必须 DENY
- SPEC_CLAUSE: §31 闸门第22条 "authorization_generation == latest durable generation"；§27A（authority 事件记录 previous_generation/new_generation）
- CURRENT_IMPLEMENTATION: start_effect 不校验 reservation 绑定的 generation 现势性（对照：R07 单授权 generation 被篡改时 DENY——generation 概念存在，但"任务级世代推进"未校验）
- CURRENT_RESULT: ALLOW（实测：RESERVATION_COMMITTED，generation_fence=TASK_AUTH_GENERATION_ADVANCED）
- CLASSIFICATION: A
- RATIONALE: 闸门第22条规范明确；R07 与 R26 的 PASS/FAIL 对比精确定位缺口在任务级 generation 校验。

### CASE_ID: V09-R32
- EXPECTED_BEHAVIOR: impact=HIGH + reversibility=IRREVERSIBLE 且无 human gate 令牌 → DENY
- SPEC_CLAUSE: §118 HIGH IMPACT HUMAN GATE（"没有 scoped durable authorization：必须 Gate——付款/公开发布/高风险不可逆动作…"）；§30（付款=NEVER_AUTO_RETRY/HIGH/IRREVERSIBLE）
- CURRENT_IMPLEMENTATION: execute 链不按影响分级设闸；高危分类直通
- CURRENT_RESULT: ALLOW（实测：external_effect_count=1，detail="no explicit Human Gate token supplied"）
- CLASSIFICATION: A
- RATIONALE: §118 是明列规范义务。附带观察（不影响本例定性）：矩阵夹具的授权本身经 "fake-human-reference" 签发，严格 Trust Root 下应在授权签发环节即被拒——那属 R13 类；本例测点（高危闸门）独立缺失。

### CASE_ID: V09-R34
- EXPECTED_BEHAVIOR: 以 effect_type=TOTALLY_UNKNOWN_EFFECT_TYPE 签发授权/执行 → fail-closed 拒绝
- SPEC_CLAUSE: §29/§30 EFFECT MODEL（封闭分类：SAFE_RETRY/RECONCILE_REQUIRED/NEVER_AUTO_RETRY × impact × scope）；Authorization Replay Protection（effect_type 为法定记录字段）；项目级 fail-closed 宣言（README/STATUS：malformed inputs fail closed）
- CURRENT_IMPLEMENTATION: scoped_authorization 接受任意 effect_type 字符串；execute 链无分类闸门
- CURRENT_RESULT: ALLOW（实测：external_effect_count=1）
- CLASSIFICATION: A
- RATIONALE: 封闭分类 + "未知即拒绝"是规范与项目双重宣言。校验放授权签发处还是闸门处是实现选择，但"未知类型不得放行"无争议。

### CASE_ID: V09-R36
- EXPECTED_BEHAVIOR: generation 接管（takeover）后，陈旧进程持有的 reservation 调 start_effect → DENY
- SPEC_CLAUSE: §31 闸门第19条 "controller lease/fence current"、第20条、第22条；§27A Authority Monotonic Recovery Rule
- CURRENT_IMPLEMENTATION: start_effect 沿用原 controller_instance/lease，不校验接管后的世代/进程现势性
- CURRENT_RESULT: ALLOW（实测：RESERVATION_COMMITTED，generation_fence=STALE_PROCESS_AFTER_TAKEOVER）
- CLASSIFICATION: A
- RATIONALE: 与 R26 同族（generation fence 未校验）的接管场景变体；单调恢复规则明确陈旧权威不得复活。

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

## 汇总

| 分类 | 案例 | 数量 |
|---|---|---|
| A 真实语义缺口（V0.9 内必修） | R01 R04 R06 R08 R09 R13 R20 R21 R26 R32 R34 R36 | 12 |
| B 能力缺失（需设计实现=对账体系） | R22 R23 R24 | 3 |
| C 期望需规范裁决 | R18 | 1 |

## 施工优先级建议（供裁决，非指令）

1. R13/R01（自我签发）：b1 核心已含修复，路径 = 核心合流而非打补丁。
2. R20/R21（crown，UNKNOWN 静默重放）：项目价值观核心，紧随其后。
3. R26/R36/R08/R09（fencing 族）：同一 generation/fence 校验机制可一并覆盖。
4. R32/R34（分类闸门）、R04（resource scope）、R06（角色校验）。
5. R22-R24：先出对账设计稿（B 类，设计先行）。
6. R18：等规范裁决，禁止先动。

## 前置工作（V0.9 CLOSE 的真正第一步）

〔FACT〕攻击矩阵当前无法测量 b1 升级核心（夹具授权方式被升级核心拒绝，实证）。
因此：① 矩阵夹具适配升级核心的授权约束 → ② 在 b1 核心上重测 36 例 →
③ 用重测结果刷新本矩阵（预计 A 类数量将下降）。
在完成该重测之前，本矩阵的 A 类清单是"对 v0.8 基座的缺口"，
不是"对 b1 核心的最终结论"。
