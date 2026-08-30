# BUILDER_RULING_R3_R4 — 对 Builder 阻塞点 R3/R4 的正式裁决

裁决人：总设计师 / 主脑
执行对象：Builder（Qwen3.8 Flash 会话）
日期：2026-08-28
绑定规格：`V09_CLOSE_BUILD_SPEC.md` SPEC_SHA256 =
`3deccf581bdcdf11ba6a2edba4d3f28cee410c69f3182b7f41065031e1db41fa`（不变）
前置裁决：BUILDER_RULING_R1_R2（dd9b89e5…b083）、BUILDER_RULING_R18（7e1a714d…467a）

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
## §0 对 Builder 的确认

你再次按 HARD STOP 停下并用对照实验取证——正确。以下裁决解决 R3 与 R4。
**R3 的矛盾源于主脑裁决书自身的错误，责任在主脑，不在施工侧。**
你的现场保全方式（未跟踪新增、可回滚、双源对照、基线证据落盘）予以确认，
沿用不改。

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
## §1 R3 裁决：移植源改定 **b2@f74d48e**（采纳你的选项 1）

**裁决：治理文件移植源 = 冻结线 b2 的最终状态 `f74d48e`。
R1/R2 裁决书 §2 中"（不是 f74d48e；取 a0ce691 的文件内容）"一句正式撤销。**

错误说明（写入裁决记录，供审查追溯）：主脑原以"最后一个开发提交"为由
指定 a0ce691，忽略了 governance 提交本身就是治理文件的**定稿动作**——
`633daec` 封印（registry b2-head 校准至 a0ce691）与 `f74d48e`
（doctor 增加 governance-ahead 规则）正是使"治理包自洽可验"的那一对。
a0ce691 时刻的 registry 仍是封印前状态（b2-head=da6d1e5e）、doctor 无
CASE-2 规则，以其为源必然 DRIFT。你的实测对照（b2 原检出 DRIFT_FREE vs
a0ce691 源必 DRIFT）即为裁决依据。

执行细则：
1. 重取 6 个治理文件于 `f74d48e`（其中 5 个与已移植的 a0ce691 版不同，
   全部以 f74d48e blob 为准；逐字节证明改对 f74d48e 的 blob ID 记录）。
2. `spec_registry` 写入目标 = **f74d48e 版** `PROJECT_STATE.json` /
   `PROJECT_STATE.md`（孪生同步）；写入内容仍为
   `spec-anchor-pack/spec_registry.json` 条目（status 置已入库语义）。
   顺序：先重取定源，再写 registry（你已正确坚持此顺序）。
3. doctor 预期修正声明：施工线 doctor = f74d48e 版；对 b2 行适用
   governance-ahead（CASE 2）；对 b1 行适用 §3.3 机械同步。
   T0 完成点必须实测 `DRIFT_FREE`（WARN 允许）——该出口判据恢复可达。
4. 已移植的 2 个测量件（夹具 +1 行 spec_anchor / 冻结运行器）与 V14 副本、
   两份报告：来源与内容不受本裁决影响，无需重做（夹具的 spec_anchor
   补丁继续有效）。

## §2 R4 裁决：基线红的处置——两级判据 + 三类分治

**追认**：`docs/evidence/v09-close/BASELINE-b1-50cf8bd1.md` 为授权基线记录；
你提出的"相对基线零新增失败"予以采纳，但**只作为施工期判据（Tier 1）**。
规格 §4.3"全量套件全绿"在授权基线上不可达属实——主脑承担该规格缺陷；
CLOSE 收口判据按下述 Tier 2 执行，由本裁决替换规格 §4.3 的原文表述。

**Tier 1（施工期间，每批提交强制）**：相对已录基线零新增失败 +
逐案矩阵回归（适配运行器）。任何新增失败 = 立即停、上报。

**Tier 2（CLOSE 收口门，19 例基线红三类分治）**：

**(a) 8 例 self-grant ERROR —— 授权为"测试适配"（编号 AD-6）**
这些旧测试依赖的行为（Controller 自签发）已被 V0.9 永久禁止（规格 §3
对 R13 的永久约束；修回去即违宪）。处置：允许修改**仅限测试文件**
（`tests/**`、`runtime/test_*.py`），按 AD-1 同构模式为被测流程预置
外部权威授权（decision nonce → grant），断言强度不降
（外部效果计数/终态断言不得削弱）。每个适配的提交信息注明
"AD-6: R13 permanent constraint test adaptation + 本裁决编号"。
禁止为让旧测试通过而改动任何产品代码。

**(b) 9 例 egress FAIL —— 逐案裁决后适配，不许打包处理**
每一例必须先给出规范支撑（V14 §31 第9条 "Data Egress permits it" /
§29-30 / 仓库 `DATA_EGRESS_POLICY.md` / b1 config egress 条款，引用到条款级），
证明"新行为正确、旧期望过时"后方可修订期望；修订记录入
`docs/evidence/v09-close/`（逐例：旧期望/新行为/规范条款/裁决）。
**若任何一例无法给出规范支撑（= b1 过度收紧），不得改测试，
按 HARD STOP 上报**——那将按缺陷处理，不是期望问题。

**(c) 2 例 context capsule FAIL —— 先归因，后分叉**
不属于任何 CASE_ID，不允许顺手修。执行**只读归因**：
在授权基座 `e8c53d4`（可 `git archive` 只读导出）上运行同组测试对照——
- 若基座上通过、b1 上失败 = b1 核心变更引入的能力回归：
  预授权最小修复（目标=恢复 capsule 对 OUTCOME_UNKNOWN 的传播；
  文件范围以归因结论为准，若涉 `controller.py` 则已在规格 §1 TCB_IMPACT
  覆盖；修复提交引用规格 §6 第 7 条"已有能力不回归"）；
- 若基座上同样失败 = 先于 b1 存在：不修，记入
  `docs/evidence/v09-close/` 的已知红登记 + PROJECT_STATE 开放问题
  （V0.10 待办），如实写入收口报告，不得掩盖。

**Tier 2 完成后**，"全量套件"的合法终态 = 全绿，或仅剩 (c) 第二分支
登记在册的已知红（带用户可见声明）。审查者对 (a)(b)(c) 逐条追认。

## §3 现场与恢复

1. 施工位点确认为你的 worktree
   `C:/Users/17838/Documents/Qoder/2026-08-28/031cb4e3/b1`（既有线检出，
   非新版本线，批准）；`chat-1` 克隆保持冻结 b2 检出，不动。
2. 恢复步骤：按 §1 重取 5 个治理文件（f74d48e 源）→ 重验字节级一致 →
   写 spec_registry（孪生）→ `python scripts/state_doctor.py` 实测
   DRIFT_FREE → T0 提交 → TASK-1 起按规格依赖序推进。
3. 结果块格式沿用 R1/R2 裁决书 §5；另在 EVIDENCE 段附 (a)(b)(c)
   处置记录路径。

## §4 记录义务

`docs/DECISION_LEDGER.md` 追加（actor=主脑）：
- R3 裁决与主脑错误自认（a0ce691→f74d48e 换源）；
- R4 两级判据替换规格 §4.3 原文；
- AD-6 类别设立（R13 永久约束下的测试适配）。
优先级链不变：规范原文 > 规格 > 裁决指令；本裁决仅解决 R3/R4，
不扩大其余任何语义边界。
