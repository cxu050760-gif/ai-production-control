# 执衡 V0.9 → V1.0 收口路线（ROADMAP）

角色：Project Architect / Release Planner（不施工）
日期：2026-08-28 | 状态：已获用户批准（批准裁决见 §0）
事实分级：〔FACT〕有直接证据 | 〔INFER〕多证据推导 | 〔REC〕设计建议

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
## 0. 裁决记录（2026-08-28，用户批准）

〔FACT〕收口路线获批准：Phase 0 → V0.9 收口 → V0.10 单类真实 GOAL →
        V0.11 REWORK/RECOVERY → V1.0 发布硬化。
〔FACT〕顺序修正（用户裁决，覆盖 §9 原建议）：**master 合并暂缓**。必须在
        Phase 0 完成（PROJECT_STATE / branch_registry / doctor 落地，四个基线概念
        明确）之后，再裁决 master 是否指向 v0.9-b2。理由：在状态语义落地前移动代码状态，
        等于重演本项目要解决的"先移动代码、后补语义"问题。
〔FACT〕KEEP > REPAIR > SIMPLIFY > REPLACE > REBUILD 升格为 V0.9→V1.0 全程总施工纪律。
〔FACT〕角色分工定调：设计/规划由当前主脑承担；施工交 Builder；终审用另一个模型。
〔FACT〕Phase 0 成品包已产出（工作区 phase0-pack/，待用户提交入库）：
        PROJECT_STATE.md/.json、branch_registry.json、state_doctor.py、入库清单。

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
## 1. 当前真实状态重建（仓库级）

〔FACT〕仓库 42 分支、0 Tag、0 Release、0 PR、0 Issue（API 实测，2026-08-28）。
〔FACT〕master @4cf41fd（08-23，Router V0.1 Slice A），tests/ 83 单测全绿，
        离线 55/55 + 40/40（本次实测）。
〔FACT〕v0.9-b2/authority-effect-evidence @da6d1e5（08-28 04:01 UTC），
        相对 master ahead 78 / behind 0（用户与 API 双向核实）。
〔FACT〕42 分支中无任何分支落后 master（全部 behind=0），演进为链式叠加。
〔FACT〕src/aicontrol（Controller TCB）自 Stage 0 后零改动；全部施工在 runtime/ 树。
〔FACT〕STATUS.md 自述：PRODUCT_NOT_READY；blocking gap = 无通用 Goal Worker/Adapter。

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
## 2. PROJECT_EVOLUTION（以仓库真实证据为准）

注意：用户提供的 V0.1–V0.9 阶梯与仓库实际命名不完全对应。
〔FACT〕仓库中不存在名为 V0.2/V0.3/V0.4 的分支或标签；实际演进如下表，
        早期以 master 上的 m1–m5 里程碑 + Slice 字母线实现，后期以版本分支线实现。

### Stage 0（Codex/TRAE/GLM 时代，≤08-17）
- GOAL：控制面公理落地（Canonical State / Effect WAL / Authority Journal / TCB / 验收 A01-A65）
- IMPLEMENTED：全部公理层 + 浏览器能力矩阵 + Release digest 链 〔FACT：代码在 src/〕
- TESTED：A01-A65 达 62/65，A08/A09 被 ChatGPT 登录态阻塞 〔FACT：交接报告+manifest〕
- EVIDENCED：有（acceptance-run-latest.json，仓库外 E:\WB\outputs）
- REVIEWED：独立 ChatGPT Reviewer 判 PASS（M0.5，commit 63217a8）〔FACT：STATUS〕
- KNOWN_GAPS：真实主脑链路从未跑通；验收用例与实现同源（自评）〔FACT：交接报告§4.0.5〕
- SURVIVED：全部公理层代码（src/aicontrol）至今零改动 = 地基可信 〔FACT〕

### V0.1（08-23，master）
- GOAL：单任务可靠闭环 + B/R 角色路由
- IMPLEMENTED：Router Slice A（router-start/step/run，GOAL→B、输出→R、REWORK 自动回传）
- TESTED：55/55 + 40/40 〔FACT：本次实测〕；另有 m1-m5 goal pipeline（83 单测全绿）
- KNOWN_GAPS：传输层依赖外部聊天会话；无通用执行器
- SURVIVED：router 阶段机、verdict 协议（===REVIEW_VERDICT===）、durable RUN state

### V0.2–V0.4（用户阶梯中的名称）
- 〔INFER〕仓库中无对应分支；其职能实际由 Slice 字母线承担（见下行）。
  若用户另有所指（如聊天中的规划版本），该历史未入库 = 对任何新 AI 不存在。
- 〔REC〕这正是要解决的"状态权威化"问题：版本阶梯必须与仓库引用一一对应。

### Slice 线（08-23→08-25，v0.5 之前的小切片，全部并入后续版本线）
- slice-b：入口规范化 / 无人值守 harness 隔离
- slice-c：Goal Contract Lite（router-continue 身份守卫，fail-closed）
- slice-i：Effect Safety Lite（授权身份+权限状态绑定到每个效果预留）
- slice-j2：Send Guard（review-valid PASS 绑定校验）
- review-result-return：R 裁决持久绑定进 Runtime state
- transport-recovery-lite：router-continue 同 RUN 续跑
- 〔FACT〕以上模块全部存活于 v0.9-b2 runtime/ 树（文件实测在位）

### V0.5（08-25）
- GOAL：Review 强化（PASS 失效 + 证据注册）
- IMPLEMENTED：b=pass-invalidation（REWORK4：裁决容器与 run_id 进身份闭包）；
  c=evidence-registry（fail-closed 单快照证据注册，禁读竞态/禁强制转换）
- TESTED：对应离线套件在 v0.9-b2 上全绿 〔FACT：本次实测〕
- SURVIVED：evidence registry 语义沿用至今

### V0.6（08-25）
- GOAL：EC（Effect Control）遥测与失败关闭
- IMPLEMENTED：b=EC fail-closed gate；c=telemetry replay（router 路径 EC 遥测，锁安全，
  含 JSON 门拒扫描与 SEND_FAILED-after-REWORK 对抗测试，REWORK 多达 5 轮）
- 〔INFER〕REWORK 轮次编号（r20/r22）表明这条线经历了真实审查-返工循环，流程在运转

### V0.7（08-26→27）
- GOAL：Strategic Brain（战略大脑：纠正/复用/集成）
- IMPLEMENTED：sb=战略大脑契约（fail-closed 上下文、确定性有界上下文、对抗测试）；
  sr=战略复用契约（咨询性 reuse-or-reject）；c=路线纠正；
  int=relay-merge 脚手架（惰性、默认禁用）→ 4 条 manual/ 整合与修正线
- TESTED：18+30+28+14+11+9 等离线套件在 v0.9-b2 全绿 〔FACT〕
- KNOWN_GAPS：〔FACT〕战略大脑至今为惰性脚手架，默认禁用（提交信息自述）
- WHAT_WAS_REPLACED：无；纯增量

### V0.8（08-27）
- GOAL：Adapter 体系（Worker/Builder 接入的合同化）
- IMPLEMENTED：b1=adapter-core；b2=adapter-registry（能力一致性加固）；
  b3=adapter-evidence（+recovery 修正：F01/F02 绑定 invocation provider mismatch）；
  integrate/final-3/4 合并；spec/v0.8-final-candidate-anchor 锚点
- TESTED：core 44/44、evidence 27/27、registry 36 攻击案例+1 正例 〔FACT：本次实测全绿〕
- REVIEWED：〔FACT〕v0.9-b1 提交信息称其 replay 于 "accepted v0.8 base"，
  且 v0.9 证据模块硬编码 EXPECTED_BASE=e8c53d4（=adapter-final-4 head）
  → V0.8 集成线是项目自己认定的 Accepted Base
- SURVIVED：成为 V0.9 的地基

### V0.9（08-27→28，当前）
- GOAL：Authority / Effect Core（授权与现实副作用控制）
- IMPLEMENTED：b1=核心（replay 到 accepted v0.8 base）；
  b2=正式发布攻击矩阵 RED 证据（36 案例）；
  spec/v0.9-b1=授权与效果执行分离版（平行方案）
- TESTED：23 套件中 22 绿；攻击矩阵 16/36 RED 〔FACT：本次实测〕
- RED 定性（已逐项取证，详见 §4）：已公示债务 + 语义缺口混合，非"16 个 bug"
- KNOWN_GAPS：reconciliation API 不存在；完整规范不在仓库内

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
## 3. 可信基线集（严格区分，不画等号）

| 概念 | 值 | 依据 |
|---|---|---|
| CURRENT_DEVELOPMENT_HEAD | v0.9-b2 @da6d1e5 | 〔FACT〕最新提交时间 |
| CURRENT_ACCEPTED_BASE | v0.8-integrate/adapter-final-4 @e8c53d4 | 〔FACT〕v0.9 证据模块硬编码该 SHA 为基座 |
| CURRENT_CANDIDATE | v0.9-b2（RED 候选） | 〔FACT〕最后提交即"发布正式 RED 证据" |
| LAST_GREEN_BASE | v0.8-integrate/adapter-final-4 @e8c53d4 | 〔FACT+限定〕本次实测其全部离线测试绿；"绿"指测试层面，项目语义下的正式封绿还需独立审查记录入库（见下） |
| LATEST_REVIEW | M0.5 独立审查（63217a8，PASS）| 〔FACT〕STATUS 记载；〔FACT〕此后 v0.5–v0.9 的审查记录零入库（0 PR/0 tag/无 review 证据文件） |
| LATEST_EVIDENCE | V0.9 攻击矩阵 RED 记录 | 〔FACT〕da6d1e5 |
| RELEASE_STATUS | PRODUCT_NOT_READY | 〔FACT〕STATUS 自述 |

关系解读：开发头（RED 候选）领先被接受的基线（V0.8）一个版本；
中间没有任何入库的审查/证据环节——〔INFER〕这是"多 AI 交替施工混乱"的制度性根因：
审查发生了（在外部聊天会话），但从未被锚定进仓库，因此对任何新 AI 不可复核。

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
## 4. V0.9 重审（16 个 RED ≠ 16 个 Bug）

〔FACT〕已取证案例分类：
A. 真语义缺口（违反项目公理，必须在 V0.9 内解决）：
   - 执行器自我授权（R13 类）：ensure_valid_authorization 无授权时自动自签
     ——直接违反"智力不得自我扩权"原则⑧；模块 docstring 自认是延迟加固项
   - 未知效果类型放行（R34）：闸门无 effect type 概念，应 fail-closed
   - 高危无 human gate（R32）、陈旧栅栏/世代接管（R08/R09/R26/R36）
B. 能力缺失（需建，形态待规范裁决）：
   - reconciliation/对账 API（R21-R24 探测 6 个方法名全不存在）
C. 需规范裁决（期望值正确性仓库内不可验证）：
   - same_slot 冲突语义（R18）、去重与重试边界（R20）等
   〔FACT〕完整 V0.9 规范在用户本机 .codex 附件、未入库 → 无法裁决
〔REC〕处理顺序：先规范入库（S4）→ 逐例裁决归入 A/B/C → A 立即修、B 定形态、C 定期望。
〔REC〕V0.9 的 EXIT 不是"36/36 绿"，而是：**每一例都有裁决记录（修好或修订期望），
且裁决绑定入库规范的 SHA**。

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
## 5. V1_GAP_ANALYSIS（V1.0 = 最小完整：可运行/可控/可审/可恢复/可证明）

CRITICAL_FOR_V1：
  1. 通用 Goal Worker/Adapter（STATUS 自认的 blocking gap；无它 V1.0 无法执行真实 GOAL）
  2. Authority/Effect 闸门 A 类语义缺口修复（权限面漏 = 控制平面不成立）
  3. reconciliation 最小可用（"结果未知"必须有确定出路，否则恢复语义不闭合）
  4. 规范入库 + PROJECT_STATE 权威化（否则每次换 AI 重新考古，V1.0 无法"可持续运行"）
  5. 审查/证据记录入库（当前 0 入库；无它"凭什么证明完成"无法自证）
HIGH：
  6. 真实 GOAL 端到端一次完整走通（含一次真实 REWORK 与一次真实恢复）
  7. 独立审查从外部会话升级为"异模型 + 入库绑定"（程序化验证器可晚一步）
MEDIUM：
  8. runtime.py 114KB monolith 化（〔FACT〕大；〔REC〕仅当证明阻塞维护时再拆，现在不动）
  9. 战略大脑从惰性脚手架转为可选启用（V0.11 再议）
NICE_TO_HAVE：多模型路由细节、遥测面板、信任评分
NOT_NEEDED_FOR_V1：分布式/多机、策略 DSL、Web UI、付费/公开发布类效果、
  全网页通用能力（V14 时代的"所有网页"目标应收窄为"目标类别内可靠"）

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
## 6. 架构审查（KEEP > REPAIR > SIMPLIFY > REPLACE > REBUILD）

八层链（User→Strong AI→Worker→Runtime→Evidence→Reviewer→裁决→交付）：
〔REC〕KEEP。边界划分正确，与成熟生态（AGT/Temporal/Agent-as-a-Judge）同构。
已正确的边界：Worker 契约（自报不能授权副作用）；入口唯一化（run.cmd）；
  智力与权限分离（B/R 路由）。
职责重叠：〔INFER〕runtime.py 同时承担 状态机+传输+路由+闸门+遥测——
  当前可接受，V1.0 后按维护成本证据决定是否拆。
过度复杂：无实锤。战略脑三件套（契约/纠正/复用）在禁用态，不算复杂度负担。
缺真正实现：通用 Goal 执行器、reconciliation、入库审查器（见 §5）。
历史叠加物：ai-control.cmd/scripts（已降级，保留兼容即可，不投入）。

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
## 7. 真实 GOAL 闭环逐环状态（决定 V0.10/V0.11 范围）

| 环节 | 状态 | 依据 |
|---|---|---|
| GOAL 接收 | IMPLEMENTED | run/router 入口 〔FACT〕 |
| PLAN | MISSING | 无规划器；当前靠外部主脑人肉 |
| TASK 分解 | PARTIAL | task graph 桩（test_taskgraph 2 例）〔FACT〕 |
| WORKER 执行 | PARTIAL | adapter 合同完备，但仅能力探针/弱 Worker 〔FACT〕 |
| EXECUTION 持久化 | IMPLEMENTED | durable RUN state + journal 〔FACT〕 |
| TEST | PARTIAL | 离线测试强；任务级测试绑定存在但未经历真实任务 |
| EVIDENCE | PARTIAL | registry 存在；记录多落在仓库外 |
| REVIEW | PARTIAL | 协议在（verdict marker）；审查者外部化、记录不入库 |
| REWORK | IMPLEMENTED（传输层） | REWORK 自动回传同 B 会话 〔FACT〕 |
| RECOVERY | UNPROVEN | 崩溃恢复有单测（test_driver_restart 类），未经真实长跑 |
| FINAL DELIVERY | MISSING | 无通用交付路径（PRODUCT_NOT_READY 根因） |

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
## 8. 版本路线（对用户草案的独立裁决：REVISE）

用户草案 V0.9→V0.10→V0.11→V1.0 方向正确，但缺 Phase 0，且 V0.10 范围需收窄。
裁决：〔REC〕REVISE——插入 Phase 0，收紧各版出口。

### PHASE 0 — 状态权威化（新增，约 1 周量级）
PURPOSE：让任何 AI 接手不再考古；为后续一切提供可信状态底座
TASKS：① V0.9 完整规范入库（用户启动）② PROJECT_STATE+branch_registry 落盘
③ state_doctor 首跑达 DRIFT_FREE ④ 分支收敛裁决（分类见 §10）⑤ 主干策略裁决（见 §9）
EXIT：零历史新 AI 按恢复协议 v2 一次收敛，状态报告与 PROJECT_STATE 一致（对照实验）
EVIDENCE：doctor 输出 + 对照接管记录入库
REVIEW：异模型审查 PROJECT_STATE 断言锚点完备性

### PHASE 1 — V0.9 CLOSE（权限/效果红线收口）
MUST_HAVE：16 例逐例裁决记录（绑定规范 SHA）；A 类全修（DENY/FAIL_CLOSED）；
reconciliation 最小实现；批跑全绿
OUT_OF_SCOPE：通用执行器、战略脑启用、runtime 拆分
EXIT：攻击矩阵裁决覆盖率 100%（绿或修订期望）+ 独立审查记录首次入库
EVIDENCE：矩阵结果 JSONL 绑定 candidate SHA；审查记录文件入 evidence 目录

### PHASE 2 — V0.10 第一个真实 GOAL 闭环
SCOPE 收窄〔REC〕：只支持一类真实目标（建议：本地文件/代码类任务，单 Worker 适配器），
不追求通用性
MUST_HAVE：GOAL→TASK→WORKER→TEST→EVIDENCE→REVIEW→交付 走通一次真实实例；
审查记录入库；PLAN 环节允许外部主脑人肉介入但必须留痕
OUT_OF_SCOPE：多目标类并发、自愈
EXIT：一次真实实例完整走完且证据链可被 doctor 复核
EVIDENCE：该实例的全链路记录（每环锚定）

### PHASE 3 — V0.11 REVIEW/REWORK/RECOVERY 真闭环
MUST_HAVE：真实 REWORK 一次（审查驳回→返工→通过）；真实恢复一次（中断/崩溃续跑）；
独立审查升级为异模型+程序化绑定；战略脑可选启用评估
EXIT：三个真实案例（成功/返工/恢复）各一，全证据入库
EVIDENCE：三案例记录 + 异模型审查裁决文件

### PHASE 4 — V1.0 RELEASE HARDENING
MUST_HAVE：连续 3 次真实 GOAL 全绿；TCB 重封；release digest 链
（tested=reviewed=release=delivered 四 digest 一致）；最终独立终审；限制条款书面化
EXIT：final_status=READY_FOR_USER_ACCEPTANCE + Release Candidate 产出
EVIDENCE：digest 链 + 终审记录 + 局限清单（真实、不粉饰）

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
## 9. master 与主干策略（四角度裁决）

选项评估：
A（主线留 v0.9-b2）：Git 干净，但考古成本永久化——本次接管实测已被它坑过 〔排除〕
C（另选分支）：无更优候选（v0.9-b2 线性包含一切）〔排除〕
D（回最后绿基线重来）：丢弃 78 提交中大量绿测试工作，代价不成比例 〔排除〕
B（v0.9-b2 进 master，显式标 RED/PRODUCT_NOT_READY）：
  Git 语义：快进，零冲突 〔FACT〕
  Release 语义：必须附带——master ≠ release ready；LAST_GREEN_BASE 单独登记
  （=e8c53d4），RED 标签 + PROJECT_STATE 注记 + branch_registry 角色=CANDIDATE_RED
  Evidence 语义：合并本身不污染证据链，前提是标签与裁决记录同时入库
  AI 接管成本：从根源消除"猜分支"
〔REC〕选 B（加固版），但执行时点已由用户裁决后移：**必须等 Phase 0 落地后再执行**，
在此之前一切合并动作冻结。合并与标签必须原子完成，禁止"先合并后补标签"。

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
## 10. 分支收敛策略（只分类，不删除）

ACTIVE（4）：v0.9-b2（候选主干）、v0.9-b1（核心来源）、
  spec/v0.9-b1（分离方案，待裁决取舍）、v0.8-integrate/adapter-final-4（Accepted Base）
HISTORICAL（永久保留）：master@4cf41fd、374073f（Codex 中断基线）、
  08-17 全部文档提交（交接史）
ARCHIVE（约 32）：全部 slice-*、v0.5-*、v0.6-*、v0.7-*（含 4 条 manual）、
  v0.8-b1/b2/b3（已并入 integrate）、v0.6-int/v0.7-int/v0.5-int relay-merge、
  review-result-return、transport-recovery-lite、bootstrap/builder-git-smoke、
  spec/v0.8-final-candidate-anchor、spec/v0.9-b2
DELETE_CANDIDATES（5，需用户明确裁决后才可删）：
  tmp-unused、tmp-unused2、tmp-v09-ignore、slice-c/goal-contract-lite（被 v2 取代）
  、v0.8-integrate/adapter-final-3（被 final-4 取代）
〔REC〕归档方式=打 archive/ 前缀标签或统一列表登记，物理删除永不自动执行。

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
## 11. 模型角色策略（模型可换，状态不丢）

| 角色 | 承担者 | 约束 |
|---|---|---|
| PRIMARY_BRAIN | 轮换强模型（现任：本会话脑；常用：GLM-5.3） | 只战略/裁决；产出必须落仓库文件，禁止只留在聊天 |
| DESIGNER | 同主脑或指定 | 只出设计稿（DESIGN_* 文件），不碰实现 |
| BUILDER | 编码代理（Codex 类） | 受 WORKER_CONTRACT 约束；只写任务工作区 |
| WORKER | 弱模型 | 机械合同（WEAK_WORKER_START_HERE），PAUSED 必须停 |
| REVIEWER | 与 BUILDER 不同的模型（现：外部 ChatGPT 会话→目标：异模型+入库） | 裁决绑定 candidate hash + evidence |
| RESEARCHER | 任一可联网模型 | 外部扫描，结论入 docs 才算数 |
| LOCAL_EXECUTOR | runtime/run.cmd（确定性，无 LLM） | 永不赋模型自由度 |
MODEL_HANDOFF：任何角色换模型时，离任者必须在 DECISION_LEDGER 留下
actor+decision+evidence 三元组；接任者只读仓库恢复，不读聊天记录。
STATE_HANDOFF：= PROJECT_STATE + doctor + 恢复协议 v2（见 §12）。

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
## 12. AI_HANDOFF_PROTOCOL + CANONICAL_HANDOFF_LAYOUT

离任者必须留下（缺一视为未完成交接）：
  ① PROJECT_STATE 更新至当前（含每条断言的锚点与证据等级）
  ② branch_registry 角色更新 ③ Journal 追加 checkpoint
  ④ 未决问题写入 OPEN_QUESTIONS（不留在聊天里）
接任者必须验证：doctor 全绿 → 锚点抽查 ≥3 条 → 按 registry 检出 → 才开始工作。
必须以仓库文件存在：状态/决策/日志/规范/证据。
必须来自 Canonical State：主干判定、版本判定、阻塞清单。
绝不能依赖聊天历史：任何裁决、任何"上次说到哪"。

文件布局（不新增冗余，复用现有 5 文件体系）：
| 文件 | 地位 | 修改规则 |
|---|---|---|
| PROJECT_STATE.md/.json（新增，唯一权威） | 权威 | 人工裁决+doctor 验证后改 |
| STATUS.md（现有） | 派生摘要 | 必须与 PROJECT_STATE 一致，doctor 检查 |
| DECISION_LEDGER.md（现有） | 决策权威（追加式） | 只增不改，含 actor 字段 |
| BUILD_MISSION_JOURNAL.md（现有） | 施工日志（追加式） | 每 slice 收口必更 |
| NEW_WORKER_START_HERE.md（现有） | 恢复协议入口 | 内容=恢复协议 v2 |
MASTER_STATE.md：聊天域产物，定位为"由 PROJECT_STATE 生成的便携快照"，
不再作为独立权威（避免双权威漂移）。

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
## 13. DO_NOT_BUILD_YET（防诱惑清单）

| 禁止项 | 原因 |
|---|---|
| 新版本线（V0.12+ 预研、新协议） | V0.9 未收口，开新线=重演 42 分支混乱 |
| 分布式/多机 | 单机语义都没收口；引入只会放大未验证面 |
| 策略 DSL（Cedar/OPA 类） | 当前闸门规则量级用硬编码+测试足够；DSL 是 V1 后优化 |
| Web UI / 仪表盘 | 无真实用户，做了即债 |
| 大规模 runtime 重构 | 大≠错；无证据表明阻塞 V1.0，先冻结表面 |
| 战略脑启用 | 禁用态是正确状态；先让它旁观（产咨询建议）再谈接入 |
| 过早泛化执行器（全目标类） | V0.10 只做一类；泛化是 V1 后主题 |
| 程序化验证器完整形态 | 先"异模型+入库绑定"够用；验证器放 V0.11 后 |
| 修复 16 RED 之外的"顺手优化" | 收口期任何顺手改动都是漂移源 |

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
## 14. NEXT 3 ACTIONS（依赖序，全部直指 V1.0）

NEXT_ACTION_1【用户启动，最小，解锁一切】
  V0.9 完整规范入库：提交至 docs/specs/，登记 SHA256 进（即将建立的）spec_registry；
  攻击矩阵 fixture 增加 spec_anchor 引用。
  没有它：16 RED 无法裁决，V0.9 永远收不了口。
NEXT_ACTION_2【依赖 A1 之前可并行启动，裁决+底座】
  Phase 0 落地：主干策略裁决（建议加固版 B）+ 分支分类裁决 +
  PROJECT_STATE/branch_registry/state_doctor 首次落盘达 DRIFT_FREE。
  没有它：后续每次换 AI 都在重复本次考古。
NEXT_ACTION_3【依赖 A1+A2】
  16 RED 逐例裁决（按 §4 的 A/B/C 归类），产出裁决记录入库，
  随后由 Builder 在 V0.9 分支内只修 A 类 + 建 reconciliation 最小实现。
  禁止无裁决直接打补丁。

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
## 15. 一句话路线

先把"状态"变成权威（Phase 0），再把"权限闸门"收绿（V0.9），
然后让系统第一次真实走完一个 GOAL（V0.10），
再证明它挨过驳回与崩溃（V0.11），最后连续三次全绿才谈发布（V1.0）。
每个阶段一个核心目标，每个出口可被任何新 AI 复核。
