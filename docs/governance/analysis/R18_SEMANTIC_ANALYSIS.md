# R18_SEMANTIC_ANALYSIS — same_slot_different_payload 规范语义分析

地位：V0.9 CLOSE 施工规格的 C 类前置分析（不施工、不裁决、只呈现规范事实）
日期：2026-08-28
分析对象：V09-R18（同 `logical_effect_slot`、不同 payload 的第二次执行 → 矩阵期望
CONFLICT 或 DENY；b1 实测 ALLOW，两次执行均生效，external_effect_count=2）
规范依据：V14-FROZEN（SHA256 6fe3bb79...954df6）——对 66,931 字节全文做穷举检索，
`slot` 共出现 4 处（L937 / L3911 / L4411 / L4433），逐一核验如下。

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
## 1. 规范事实（逐处，无遗漏）

**〔F1〕L937 — §23 ACTION LEDGER**：`logical_effect_slot` 是每个 effect 的
法定账本字段之一（与 action_id / logical_effect_id / effect_intent_hash /
attempt_id / execution_fence_token 并列）。——仅定义"它是账本字段"，
无任何关于槽位容量/排他性的语义。

**〔F2〕L3911 — LOGICAL_EFFECT_SAFETY 组成清单**：`slot` 列为逻辑效果安全的
组成要素之一（与 logical_effect_id / intent hash / atomic reservation /
authorization consumption / execution fence / provider idempotency 并列）。
——仅列入清单，无语义定义。

**〔F3〕L4411 — PART III LOGICAL EFFECT IDENTITY**：身份组成 =
action_id / logical_effect_id / attempt_id / effect_intent_hash /
logical_effect_slot；并明言 **"action_id 不是 external-effect dedup authority"**。
——去重的权威是 logical_effect_id（不是 action_id）；slot 是身份组成之一，
但规范没有说"槽位本身是去重键"或"每槽一个意图"。

**〔F4〕L4433 — Effect Intent Hash 绑定清单**：effect_intent_hash 绑定
operation / provider / destination / expected account / resource /
**payload hash** / critical params / purpose / authorization / Goal Contract /
**logical effect slot**。——payload hash 与 slot 同为意图哈希的绑定材料：
**不同 payload ⇒ 不同 effect_intent_hash ⇒ 不同 logical_effect_id**。
这是规范给出的唯一可推导的身份规则。

**〔F5〕相关去重/冲突条款穷举**（检索 dedup/conflict/unresolved/in-flight/
exactly-once/one intent/single intent）：
- §31 第17条（L1486）："no unresolved/in-flight same **logical effect**" ——
  禁止的是同一**逻辑效果**（同一身份）的未决并存，措辞是 logical effect，
  不是 slot；
- §120 Selftest（L3434）列出 "Logical Effect Dedup" 为自测项，无定义增量；
- Atomic Reservation（L4456）要求 "logical effect dedup" 原子化，无定义增量；
- EXTERNAL_EFFECT_SEMANTICS（L3984）："不得说所有互联网 effect 绝对 exactly-once"
  ——对 exactly-once 是**限制性**表述，不构成"同槽必须冲突"的义务；
- **全文无任何条款规定"同一 slot 只允许一个意图"、"同 slot 异 payload 必须
  拒绝/冲突"、"不同 payload 不得共存"。**

## 2. 对四个问题的严格回答

**Q1："same slot" 在 V14-FROZEN 中是否定义为唯一意图槽位？**
否。规范仅将 slot 定义为账本字段〔F1〕、身份组成〔F3〕与意图哈希绑定材料〔F4〕。
"唯一意图槽位"（每槽至多一个意图）在全文中不存在明文，也无法从既有条款
有效推导：若规范意图如此，§31 第17条的措辞应是 "same slot" 而非
"same logical effect"〔F5〕。

**Q2：slot 是否只是去重/分区键？**
规范没有这样说。去重权威被明确指认为 logical_effect_id〔F3〕；slot 参与身份
构成〔F3〕〔F4〕，但"分区键"语义既无明文也不可推导。两种解读（身份组成之一
/ 分区键）在文本上都无法被排除或确认。

**Q3：不同 payload 是否允许共存？**
从规范可推导的部分：不同 payload ⇒ 不同 effect_intent_hash ⇒ 不同
logical_effect_id〔F4〕，因此它们是**两个不同的逻辑效果**；§31 第17条只对
"同一逻辑效果的未决并存"设禁〔F5〕，对两个不同逻辑效果的共存没有禁令。
即：**当前实现（两者均为合法新效果）与规范不冲突**；但规范同样没有
明文"允许共存"——它对此沉默。矩阵期望（必须冲突/拒绝）是规范文本
不支持的单方面解读。

**Q4：规范是否有明文定义？**
没有。4 处 slot 条款与全部去重/冲突条款穷举后，V14-FROZEN 对
"同 slot 异 payload"不存在明文规则，也不存在可排除歧义的有效推导。

## 3. 结论

```
R18 = BLOCKED_BY_SPEC
```

- 规范存在两种合法解读且无法从文本裁决：
  解读 A（矩阵期望）：slot = 每槽一个意图，异 payload 应冲突/拒绝；
  解读 B（当前实现）：身份 = slot + payload 等全量哈希，异 payload 为
  不同逻辑效果，可各自合法执行。
- 按项目纪律（C 类不得自行拍脑袋；裁决必须绑定规范条文），**本分析不构成
  裁决，不授权任何施工**。V09_CLOSE_BUILD_SPEC 已将 R18 排除在施工范围外，
  并设 HARD STOP：任何 R18 施工请求必须先有用户裁决。
- 提交用户裁决的决策输入（权衡，非建议）：
  - 选 A（冲突语义）：需在 reserve 阶段对"同 slot 未终局/已存在的异载荷意图"
    增加冲突判定；影响面 = 一切以固定 slot 重放但载荷合法变化的流程
    （例如重规划产生的同槽位修正载荷将被拒，需要显式新 slot 约定）。
  - 选 B（维持现状）：需修订矩阵该例期望值（CONFLICT_OR_DENY →
    与规范推导一致的表述），并把裁决记录绑定本分析；实现零改动。
  - 无论选哪边：裁决必须写入 DECISION_LEDGER（含 actor），矩阵期望值与
    裁决记录绑定规范 SHA 后方可收口该例。

## 4. 方法声明

检索为穷举式（全文关键词扫描 + 逐处上下文核验），非抽样；本文件所有
行号指向 `docs/specs/V14-FROZEN-EXECUTION-SPEC.txt`（入库后路径；当前为
工作区 `spec-anchor-pack/docs/specs/` 逐字节副本，66,931 bytes，SHA256
6fe3bb7996a1f78a7d6584d08311c3ebc1aa2d9ffc56c27fc61e8d599e154df6）。
未引用任何规范之外的来源；未改动任何代码与测量件。

## 5. 裁决（2026-08-28，用户授权委托）

〔授权事实〕用户 2026-08-28 将 R18 裁决权明确委托主脑
（原话："这个R18是怎么了吗？我不太明白，都交给你了，你想干什么就干什么"）。
规格设定的前置条件（"必须先有用户裁决"）由此满足；授权链：用户 → 主脑
（本会话）→ 本裁决。本节即该裁决的正式记录。

**裁决：采用解读 B —— slot 是身份组成，不是唯一性容器。**

1. 语义定性：同 slot、不同 payload = **两个不同的逻辑效果**
   （不同 effect_intent_hash ⇒ 不同 logical_effect_id，依据〔F4〕），
   各自经完整闸门链（授权、配额、scope、WAL）独立通过后合法执行，可以共存。
2. 矩阵原期望 `CONFLICT_OR_DENY` 为规范不支持的单方面解读，予以**修订**；
   修订以裁决记录绑定规范 SHA，属裁决收口，不是静默改动，也不是"收绿"。
3. 理由（逐条可复核）：
   a. 规范依据：V14 的去重权威是 logical_effect_id〔F3〕；§31 第17条只禁
      "同一逻辑效果"的未决并存〔F5〕——不同身份的效果不在其约束范围；
      规范无任何条款要求同 slot 排他（§2 结论）。
   b. 攻击面分析：异 payload 的第二效果**不绕过任何闸门**——它是全新效果，
      重新通过全部检查（授权消耗、配额、scope 一个不少）。"偷换载荷"攻击
      只能作用于同一身份内部，而意图哈希已绑定 payload，该面在现有机制下闭合。
      即：解读 A 想防的攻击，现有机制已经防住；解读 A 不增加安全性。
   c. 代价分析：解读 A 会阻断合法的 REWORK 纠正场景（同一逻辑位置发送
      纠正后的载荷），并诱发"换槽位绕过"的形式化对策，反而削弱槽位可审计性。
   d. 纪律对齐：KEEP > REPAIR——解读 B 零代码改动；解读 A 需新建无规范
      依据的冲突机制，违反"规范没要求的不建"。
4. 处置：R18 以"**期望修订 + 裁决记录**"收口，**不施工**（闸门代码零改动）。
   施工线适配运行器将 R18 的裁决期望设为 `ALLOW_DISTINCT_EFFECT`，
   匹配判据 = 观测 ALLOW 且 external_effect_count=2 且两次执行为两个不同的
   logical_effect_id、均为独立预留（而非去重命中）——防止用"碰巧 ALLOW"收口。
   冻结夹具原件不动；期望覆盖只存在于适配运行器并逐字引用本节。
5. 本裁决不改变其余任何案例的分类与处置；A 类 9 例、B 类 3 例的施工
   与验收判据维持规格原文。
