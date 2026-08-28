# SPEC_ANCHOR_REPORT — V0.9 规范锚定报告

模式：V0.9 规范锚定（Project Architect，未施工）
日期：2026-08-28
分级：〔FACT〕直接证据｜〔INFER〕推导｜〔REC〕建议

---

## 1. 规范定位结果

〔FACT〕对用户本机全部可能位置做了穷举检索：
- `C:\Users\17838\.codex\attachments\` 全部 7 个含文本附件的目录（关键词扫描：
  V0.9 / authority / effect / reconcile / DENY）
- `E:\WB\docs`、`E:\WB\tools\ai-production-control`（08-23 后全部 .md/.txt）、
  `E:\AI_Projects`、`C:\Users\17838\.workbuddy`（全文头部特征扫描）

〔FACT〕结论：**不存在独立的"V0.9 Authority/Effect 专项规范"文件。**
唯一包含 Authority/Effect 完整条款（授权回滚安全、单调恢复、效果模型、
25 条统一执行闸门、HIGH IMPACT HUMAN GATE、ACTION LEDGER 含 RECONCILING 态、
A60/A64 验收）的在盘规范是：

```
V14-FROZEN CONSOLIDATED EXECUTION SPEC
源文件: C:\Users\17838\.codex\attachments\c33ac6a6-82c9-4ebb-8783-abc6ace36301\pasted-text.txt
大小:   66,931 bytes（3,515+ 行）
SHA256: 6fe3bb7996a1f78a7d6584d08311c3ebc1aa2d9ffc56c27fc61e8d599e154df6
```

〔FACT〕该 SHA256 与仓库 `docs/BUILD_MISSION_JOURNAL.md` 登记的
`prompt_hash: sha256:6fe3bb79...` **完全一致**——独立交叉验证成立，
这就是项目历史指认的 V14-FROZEN 规格，权威性双重确认。

〔INFER〕V0.9 攻击矩阵的期望值 = V14-FROZEN 条款的可测投影（矩阵无独立规范来源）。
这改变了此前的判断："完整规范在别处"修正为"规范即 V14，V0.9 无独立增量规范"。

## 2. 锚定包内容（待入库，本轮未提交）

```
spec-anchor-pack/
├── docs/specs/V14-FROZEN-EXECUTION-SPEC.txt   ← 原样副本（未改一字节，66,931 bytes）
├── v14-extracts.txt                            ← 裁决用关键条款摘录（辅助件，可不入库）
├── spec_registry.json                          ← 登记条目（见 §3）
├── SPEC_ANCHOR_REPORT.md                       ← 本报告
└── RED_ADJUDICATION_MATRIX.md                  ← 16 RED 逐例裁决索引
```

入库映射（供 Git Operator）：
- `docs/specs/V14-FROZEN-EXECUTION-SPEC.txt` → 仓库 `docs/specs/` 同名
- `spec_registry.json` 内容 → 并入（已落库或将落库的）`PROJECT_STATE.json.spec_registry`
- 攻击矩阵 fixture 顶层增补（建议由 Operator 执行）：
  `"spec_anchor": "sha256:6fe3bb7996a1f78a7d6584d08311c3ebc1aa2d9ffc56c27fc61e8d599e154df6"`
- 两份报告 → `docs/`（或用户指定位置）

## 3. spec_registry 条目

```json
{
  "spec_id": "V14-FROZEN",
  "title": "CODEX ONE-SHOT FINAL V14 FROZEN CONSOLIDATED EXECUTION SPEC",
  "path": "docs/specs/V14-FROZEN-EXECUTION-SPEC.txt",
  "sha256": "6fe3bb7996a1f78a7d6584d08311c3ebc1aa2d9ffc56c27fc61e8d599e154df6",
  "cross_verified_by": "docs/BUILD_MISSION_JOURNAL.md prompt_hash (identical)",
  "governs": [
    "runtime/fixtures/v09_authority_effect_attack_cases.json",
    "runtime/test_v09_attack_matrix_offline.py"
  ],
  "governing_clauses_for_v09": [
    "§23 ACTION LEDGER (含 OUTCOME_UNKNOWN / RECONCILING 法定态)",
    "§26 RECONCILE_REQUIRED/NEVER_AUTO_RETRY 前置链",
    "§27/§27A WAL 崩溃恢复与 AUTHORITY_COMMIT_JOURNAL",
    "§29-31 EFFECT MODEL 与 UNIFIED EFFECT EXECUTION GATE (25 条, 失败=DO NOT EXECUTE)",
    "§118 HIGH IMPACT HUMAN GATE",
    "Human Gate Trust Root (授权只能来自用户正式受控入口确认)",
    "Authorization Replay Protection (effect_type/generation/max_effect_count 记录)",
    "§A60 Logical Effect Identity / Atomic Reservation",
    "§A64 Privileged Worker External-Effect Bypass",
    "EXTERNAL_EFFECT_SEMANTICS (UNKNOWN outcome 边界)"
  ]
}
```

## 4. 裁决过程中纠正的三个事实错误（自我反证）

1. 〔已纠正〕"v0.9-b2 与 master 的 src 存在实质差异"——初测 15 个文件哈希全不同，
   复测为**纯行尾符差异（CRLF/LF）**，规范化哈希 15/15 相同。结论维持：
   v0.9-b2 的 src/aicontrol 与 master 语义相同。
2. 〔已纠正〕"16 RED 证明当前最新核心漏防"——**不精确**。见 §5 双基座结构：
   RED 是对"未升级 v0.8 基座"的测量，不是对 b1 升级核心的测量。
3. 〔已纠正〕"完整规范缺失且不可知"——规范并未缺失，即 V14-FROZEN；
   缺失的是"入库锚定"，本轮已补齐锚定材料。

## 5. 重大结构发现：V0.9 是双基座结构（裁决依据）

〔FACT〕对 b1→b2 与 base→b1 做了 GitHub compare 取证：

- **v0.9-b1（50cf8bd1）= 核心升级**：单提交改动 7 文件——
  `src/aicontrol/controller.py`(+142/-29)、`src/aicontrol/security.py`(+119)、
  `runtime/effect_safety_lite.py`(+737/-95)、`tests/test_v09_authority_store.py`(+324 新增)等。
- **v0.9-b2（da6d1e5e）= 红线测量**：仅新增 4 文件（CI workflow + 攻击矩阵 +
  测试 + 证据生成器），**不含 b1 核心**。其 CI 以所有权白名单强制此结构：
  允许文件恰为那 4 个；且显式断言 `SPECULATIVE_BASE(b65a5126) 不得是祖先`。
- 〔FACT〕实测验证：把攻击矩阵搬到 spec/v0.9-b1（含升级核心）上运行，
  **立即被升级核心拒绝**——`GateDenied: pre-existing scoped authorization
  required; Controller self-grant is forbidden`。即升级核心已封死 R13 类自我授权，
  但矩阵夹具的授权方式与升级核心的新约束不兼容，需要适配后才能测量。

〔INFER〕因此 16 RED 的准确语义是：
**"v0.8 接受基座（未升级）面对 36 例攻击的防线缺口清单"**——
这是 b1 核心的待办输入，不是 b1 核心的失败记录。
b1 核心已至少修复自我授权类（实测证据），其余案例对 b1 的通过情况**未经测量（UNPROVEN）**。

## 6. 对裁决矩阵的影响

见 `RED_ADJUDICATION_MATRIX.md`。分类统计：
- A（真实语义缺口，v0.9 内必修，以 V14 条款为据）：12 例
- B（能力缺失=对账体系，需设计实现）：3 例（R22/R23/R24）
- C（期望需规范裁决）：1 例（R18）
- 另 R21 为 A+B 混合（静默去重缺口 + 对账缺失），主分类 A。

## 7. 本轮未做 / 禁止事项遵守声明

未改 runtime、未改业务代码、未创建分支、未修 RED、未 merge、未 push。
对 spec-v09b1 本地副本的矩阵试跑属于**只读取证**（临时拷贝到已下载副本，
未触碰用户仓库；该副本不是仓库工作树）。
