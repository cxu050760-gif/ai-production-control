# BUILDER_RULING_R18 — R18 裁决落地指令

裁决人：总设计师 / 主脑（经用户 2026-08-28 明确委托）
执行对象：Builder（Qwen3.8 Flash 会话）
日期：2026-08-28
绑定规格：`V09_CLOSE_BUILD_SPEC.md` SPEC_SHA256 =
`3deccf581bdcdf11ba6a2edba4d3f28cee410c69f3182b7f41065031e1db41fa`
（本指令不修改规格正文，规格哈希不变；本指令是对规格"等用户裁决"
前置条件的正式交付，优先级链：规范原文 > 规格 > 裁决指令）

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
## §1 裁决内容（一句话）

R18 采用解读 B：**slot 是身份组成，不是唯一性容器；同 slot 不同 payload
是两个不同的逻辑效果，各自经完整闸门链合法执行，可以共存。**
完整论证见 `R18_SEMANTIC_ANALYSIS.md §5`（含授权链记录）。

## §2 对施工的影响（极小，且不是"施工"）

1. **闸门代码零改动**。TASK-1..TASK-5 的范围、文件、判据全部不变。
2. 规格 §4 回归要求第 1 条中"R18 记录为 BLOCKED_BY_SPEC 原样（不施工、不判定）"
   由本裁决替换为：**"R18 以裁决修订期望收口（不施工）"**。
3. 规格 §5 HARD STOP 中"任何 R18 施工请求必须先有用户裁决"继续有效——
   本裁决的结论就是**不施工**；任何对闸门代码的 R18 相关改动仍是 HARD STOP。

## §3 T0 适配运行器的 R18 覆盖（AD-5）

在 `runtime/test_v09_attack_matrix_on_b1_core.py`（T0 交付件）中，
以显式覆盖实现裁决期望，并在文件头适配声明中登记为 **AD-5**，
逐字引用 `R18_SEMANTIC_ANALYSIS.md §5` 与本指令编号：

```
AD-5: R18 裁决期望覆盖。裁决 = 解读 B（用户委托主脑裁决，2026-08-28）。
      裁决期望 = ALLOW_DISTINCT_EFFECT。
      匹配判据：观测 == ALLOW 且 external_effect_count == 2
      且两次执行为两个不同的 logical_effect_id、均为独立预留
      （断言独立身份与独立预留，防止"碰巧 ALLOW"收口）。
```

匹配判据中的"两个不同 logical_effect_id / 独立预留"断言允许在适配运行器
内通过查询 Fixture 的 actions 表实现（测量侧代码，不改产品代码）。
冻结夹具原件（`v09_authority_effect_attack_cases.json`）除规格 T0 已授权的
`spec_anchor` 元数据外，仍然逐字节不动。

## §4 记录义务（按 R1/R2 裁决白名单执行）

1. `docs/DECISION_LEDGER.md` 追加一条，要素：
   actor=主脑（用户委托，2026-08-28）；裁决=解读 B；
   依据=V14-FROZEN sha256:6fe3bb79...154df6 + R18_SEMANTIC_ANALYSIS.md §5；
   影响=矩阵该例期望修订为 ALLOW_DISTINCT_EFFECT，闸门代码零改动。
2. `docs/evidence/v09-close/` 裁决记录中，R18 条目绑定：规范 SHA、
   分析书 §5、本指令、重测观测值（ALLOW / count=2）。

## §5 收口口径更新

- 分类计数：A=9、B=3、**C=1（已裁决：期望修订，零施工）**、D=3。
- V0.9 CLOSE 的收口判据不变（四者语义闭合）；R18 自此不再是未决项。
