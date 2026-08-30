# BUILDER_RULING_TIER2 — 施工结果核验、追认与 Tier 2 收口指令

裁决人：总设计师 / 主脑
执行对象：Builder（Qwen3.8 Flash 会话）
日期：2026-08-28
绑定规格：`V09_CLOSE_BUILD_SPEC.md` SPEC_SHA256 = `3deccf58…41fa`（施工后复验未变）
候选：v0.9-b1/authority-effect-core@6dd22954（代码头 c6d1a55b）

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
## §1 主脑独立核验（信任但验证，全部实测）

以下各项为主脑在推送后独立复验，非转述：
1. 远端核对：origin/v0.9-b1 = 6dd22954（8 提交，与结果块逐一对应）；
   origin/v0.9-b2 = f74d48e 冻结未触。
2. 范围核对：50cf8bd1..6dd22954 全量改动 29 文件（+8817/-6）；
   `src/` 仅 store/controller/security 三文件；`runtime/runtime.py` 与
   `runtime/effect_safety_lite.py` 零改动；无白名单外文件。
   （与你报告的 27 文件/+8696 之差 = EVID 提交中 ledger/journal 的追加，
   计数口径差异，非范围越界。）
3. 状态核对：`release_status=PRODUCT_NOT_READY`、`current_stage=PHASE_0`、
   开发头仍 b2@a0ce691（未晋升）、`spec_registry` 1 条——全部未越权。
4. **矩阵复跑（主脑亲自执行，候选树原地）**：36/36 matched，red=0，
   另 R34-FAITHFUL 匹配；拒绝消息逐案指向具体闸门语义
   （如 R08 "fence token does not match the durable reservation"、
   R20/R21 UNKNOWN 闸门、R26/R36 世代现势、R32 human gate、
   R34 issuance-side 闭合）。
5. CLOSE 单测复跑：**40/40 OK**（见 §7 调用方式说明）。
6. doctor 复跑：1 WARN（journal staleness，已预告）+ 1 DRIFT
   （registry b1-head 滞后，见 §4 裁决）——与你披露完全一致，无隐瞒项。

**结论：结果块属实。核心施工（TASK-1..5 + T0 + 证据）予以验收。**

## §2 追认（你自行认定的两项适配）

1. **AD-7（R34 签发侧归类）：追认。** 冻结案例体的签发调用位于其 try 之外，
   签发侧 fail-closed 会使原走法在冻结体内不可观测；测量侧归类为
   `FAIL_CLOSED (issuance_side)` 保全了 T9"双路径均测"的出口判据，
   未削弱攻击、未改冻结件。记录入裁决记录。
2. **`test_v09_authority_store.py` 角色绑定（1 行）：追认。**
   R06/A64 的正确语义是"角色绑定由外部签发者承担"；产品代码未为迁就
   旧测试而降格，改由 b1 自测的 `_preauthorize` 补 `roles:["FALLBACK"]`，
   方向正确。其生产含义（真实 WorkBuddy fallback 签发必须绑定该角色）
   已如实披露，作为 V0.10 真实 GOAL 阶段的前置条件登记。

## §3 封印推迟（D009）：批准，处置如下

你拒绝从候选 worktree 执行 `seal_tcb` 是**正确裁决**：既有封印的目标根
指向在产 Controller 状态（E:\WB\state）与旧 code_root，从候选树封印
既写活状态又描述错误的树。处置：
1. 封印列为 **CLOSE 收口清单第 1 项**，执行人 = 发布负责人（用户指定），
   执行时机 = 独立审查通过之后；必须在"候选树 ↔ 其配套状态根"的
   权威配对上执行，封印前后状态入证据。
2. `config/production.json` 的 `allowed_roots`/code_root 仍指旧现场
   （E:\WB\tools）= 遗留配置事实，**不在 V0.9 范围内**，记入开放问题
   （V0.10 前置），本次不动。

## §4 doctor registry 滞后 DRIFT：裁决定性

该 DRIFT 为**结构性引导期滞后**，定性为"已裁决的预期漂移"：
1. 语义：施工期 `branch_registry` 的 head 字段记录"最近一次被裁决的代码头"
   （现为 c6d1a55b），物理 HEAD 因治理/证据提交（6dd2295）领先之——
   与 Phase 0 对 b2 的引导期滞后同构。
2. 不改 doctor、不把 b1 伪装成 dev_branch、不修改 b2 行——你的三不处置批准。
3. 永久解在收口状态更新中：用户裁决将 `current_development_head` 移至
   收口线后，doctor 的 CASE-2 容忍自然适用。**该更新不属于 Builder，
   属于收口审查后的主脑+用户流程。**
4. 审查者须知：此项为已知已裁决漂移，审查对象是"除它之外零 DRIFT"。

## §5 Tier 2 收口门：继续执行（审查在 Tier 2 之后，一次审全量）

施工顺序裁决：**先完成 Tier 2，再进独立审查**（避免二次审查与
(a)(b)(c) 可能引出的产品修复交叠）。执行规则沿用 R3/R4 裁决书 §2，要点：

- **(a) 其余 7 例 self-grant ERROR**：AD-6 模式适配（仅测试文件、
  外部权威预置授权、断言强度不降、逐提交注明编号）。
- **(b) 9 例 egress**：逐案规范支撑备忘（引用到条款级：§31 第9条 /
  §29-30 / `DATA_EGRESS_POLICY.md` / b1 config），修订期望逐例记录；
  **任何一例无规范支撑 = HARD STOP 上报（按缺陷处理），不得改测试了事。**
- **(c) 2 例 capsule**：对 `e8c53d4` 只读归因（可 `git archive` 导出）。
  基座绿、b1 红 = b1 引入的能力回归 → 预授权最小修复（引用规格 §6 第7条）；
  基座同红 = 登记已知红 + 开放问题，不修、不掩盖。
- 每小批：相对基线零新增失败复验 + 提交；全部完成后产出**结果块 v2**
  （沿用 §5 格式，另附 (a)(b)(c) 处置记录路径与 Tier 2 前后套件对照表）。

## §6 附带发现（非阻塞，记入证据供审查）

主脑核验时发现：4 个 CLOSE 套件以裸导入共享 `Harness`
（`from test_v09_close_fence import Harness`），要求 `tests/` 在 sys.path——
从仓库根 `python -m unittest tests.X` 会 ImportError；规范调用 =
`cd tests && python test_v09_close_*.py`（或等价路径设置）。
不要求返工（项目既有套件本就混合调用风格），但**审查包中将注明
40 例 CLOSE 单测的规范调用方式**，防止审查者误判。

## §7 记录义务

`docs/DECISION_LEDGER.md` 追加（actor=主脑）：本裁决 §2 两项追认、
§3 封印推迟与责任归属、§4 滞后漂移定性、§5 审查顺序裁决。
