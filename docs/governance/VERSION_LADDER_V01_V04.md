# VERSION_LADDER_V01_V04_FINAL — V0.1–V0.4 版本阶梯（正式版）

> **由流 E 入仓（Q5 回填），2026-08-29，草案来源 `VERSION_LADDER_DRAFT.md`**
>
> - 产出人：许清楚（Xu / Product Manager）
> - 状态：**正式版**（Q5 回填；V0.4 语义双线处为"存疑登记"，待业主裁决后回填定稿，见 §3）
> - 方法：git 只读考古（`rev-parse / log --all --oneline / log --first-parent / show -s / show / ls-tree -r / branch -a / branch --contains / cat-file -t`，**未写 worktree、未 checkout**）+ 流 Zero Z2/Z3/Z4 交叉引用 + `state/branch_registry.json`（42 分支）对齐。
> - 考古对象：施工 worktree `C:\Users\17838\Documents\QoderCN\2026-08-28\chat-1\ai-production-control`（checked-out 分支 v0.9-b2/authority-effect-evidence；该库含全量历史，含 V0.1 时代提交 4cf41fd8，亦含旧克隆 `E:\WB\tools\ai-production-control` 的同源提交）。
> - 入仓位置建议：`docs/governance/VERSION_LADDER_V01_V04.md`（经业主确认后由流 A 落库）。
> - 证据等级：`VERIFIED` = git 对象/提交/已核实文档直接可引；`INFERRED` = 基于上下文/时间线的推断；`UNVERIFIED` = 证据不足，**不做推断填充**。

---

## 0. 总览时间线（VERIFIED，+08:00 时区）

```
08-23 15:29  6fab408  Stage 0 出口：生产 Runtime V1 绑入 git 基线（TASK_1）
08-23 16:28  4cf41fd  V0.1 Slice A：最小 B/R 角色路由（master 现尖端）
08-23 22:46  c1a55fd  Slice C Goal Contract Lite 集成（slice-c 线）
08-24 16:39  0c6e2b5  feat(v0.2/r12)
08-24 18:05  ab11830  feat(v0.3/r14)
08-24 18:18  ef11a5a  feat(v0.4/r15)
之后          v0.5 起  r16（dd33839 feat(v0.5/r16): review-valid PASS binding validation）
```

> 主干（Stage 0 → V0.1 → V0.2 → V0.3 → V0.4）全部为 git 可引提交，**VERIFIED**。V0.4 语义双线重叠见 §3 存疑登记。

---

## 1. 版本阶梯正式表（每版本三列：出口判据 → 出口证据 → 证据等级）

> 表列：版本号 | 语义（依路线 v2 / 修订史） | 对应 git 提交/分支 | **出口判据** | **出口证据** | **证据等级**

| 版本号 | 语义 | 对应 git 提交 / 分支 | 出口判据 | 出口证据 | 证据等级 |
|--------|------|----------------------|----------|----------|---------|
| **（前置）Stage 0** | 事实收口 / Construction Baseline | `6fab408` "chore(runtime): bind production Runtime V1 into git baseline (Stage 0 TASK_1)"（08-23 15:29） | 生产 Runtime V1 绑入 git 基线（TASK_1）；Accepted Base 确立；PASS 须绑定完整 Review Lineage（不孤立字符串） | ①git 提交 `6fab408` 可引（VERIFIED）；②会话层 Z3·R13：R 审查 REWORK→Blocking 1→TASK_1 Evidence→PASS→Canonical State 冻结，PASS 绑定完整 Review Lineage（VERIFIED）；③库内 docs/ 无 Stage 0 专项证据文件（缺口） | **出口流程 VERIFIED**；**库内出口文件 UNVERIFIED**（docs/ 未见 stage0/ 证据目录） |
| **V0.1** Single-Task Reliable Loop | 单任务可靠闭环；五内核；验收 Case A/B/C（AC-1..AC-12） | **`4cf41fd8ede05fa5edab52e52fc8e589ff1a441e`** "feat(router): V0.1 Slice A minimal B/R role routing (router-start/step/run)"（08-23 16:28）＝ **master 分支尖端**（Stable 线保持于此）。后续切片：`slice-b/entry-canonicalization`、`slice-b/unattended-harness-bootstrap`、`slice-c/goal-contract-lite(-v2)`、`slice-i/effect-safety-lite`、`slice-j2/send-guard`、`transport-recovery-lite`、`bootstrap/builder-git-smoke`、`review-result-return`、`manual/v07-*` | V0.1 验收 = Case A（创建 Artifact）/ Case B（修改+machine check）/ Case C（故意制造错误→REWORK→自动修复→PASS）通过；AC-1..AC-12 冻结；Router Bootstrap（B/R 路由）成立 | ①git 提交 `4cf41fd8` + master 尖端（VERIFIED）；②切片分支全量在案（VERIFIED）；③会话层 Z3·R13/R14：Slice A 审查链、AC-8/AC-11 定向补证、Slice B GAP_AUDIT 冻结（VERIFIED）；④DECISION_LEDGER（665a73c 版）提及 "Slice A AC-1..AC-11 冻结契约"（VERIFIED 提及）；⑤**正式 "Stable V0.1" 出口（Z3·R15 所述 Slice J → Stable V0.1）在 git 中未找到标记提交/标签** | **提交与分支 VERIFIED**；**Stable V0.1 正式出口 UNVERIFIED**（无 tag、无出口提交、库内无 per-version 验收记录文件） |
| **V0.2** Lifecycle Hardening | AI 停止项目不死亡；generation 隔离；旧 Worker 不能诈尸 | 唯一版本标记提交：`0c6e2b54fc38325ec78dee33a9ca3d8a61c0f58b` "feat(v0.2/r12): weak-AI acceptance prep helper (fresh PAUSED RUN + task text)"（08-24 16:39）。**无专属分支**；branch_registry 无 v0.2 条目 | 生命周期硬化能力出口（generation 隔离、旧 Worker 不能诈尸、Watchdog/自愈归 V0.2，依 Z3·R17） | ①git 提交 `0c6e2b5` 可引（VERIFIED）；②**未找到 V0.2 出口/验收记录**（库内无）；③提交语义为 "weak-AI acceptance prep helper"，与路线 v2 的 V0.2"生命周期硬化"**不完全对应**，更像验收辅助件——语义偏移（薄弱点） | **提交 VERIFIED**；**版本覆盖面 UNVERIFIED**（单提交、无出口证据、语义偏移）。**r13 缺号**：r12→r14 之间无 r13 提交（全部 ref 已检索），r13 可能是规格约束编号而非提交轮次（Z3 中 "R13-constrained" 引用），登记备考不猜 |
| **V0.3** Revisioned Canonical State | 版本化状态 + 完整性 + 恢复 | `ab11830efdb488fb44dcc6bfc3f2f07e233a4230` "feat(v0.3/r14): canonical state versioning + integrity + recovery (Slice A)"（08-24 18:05）。无 v0.3 命名分支；branch_registry 无 v0.3 条目 | canonical state 版本化/完整性/恢复能力出口 | ①git 提交 `ab11830` 可引（VERIFIED）；②**未找到 V0.3 出口/验收记录**（库内无）；③journal 提及 "canonical state rev17 hash-valid" 属更早 Codex 时代基线，**不能**作为 V0.3 出口 | **提交 VERIFIED**；**出口 UNVERIFIED** |
| **V0.4** Goal Contract + Task Graph | 目标契约 + 任务图 + 原子停止 | `ef11a5a62f05fa3e337773579bf80149431d865e` "feat(v0.4/r15): durable Task Graph lite (Slice A)"（08-24 18:18）；关联线：`c1a55fd771c7c2206e7aa478f3bdbef1783299d6` "feat(runtime): integrate Slice C Goal Contract Lite"（08-23 22:46，含于 `slice-c/goal-contract-lite-v2` 等）、`26b187e` "fix(slice-c): guard router-continue with Goal Contract identity (fail-closed)" | Goal Contract + Task Graph + Atomic Stop Rule 出口（依路线 v2 语义） | ①git 提交 `ef11a5a` + 关联线 `c1a55fd`/`26b187e` 可引（VERIFIED）；②DECISION_LEDGER（665a73c）有 Goal Contract identity 语义沿用记录（sha256(goal,acceptance,constraints)，"与 Slice A 冻结契约零影响"）（VERIFIED 提及）；③**未找到 V0.4 出口/验收记录**（库内无）；④**版本语义存在双线重叠（Goal Contract Lite vs durable Task Graph）——存疑登记，见 §3，不自行定案** | **提交 VERIFIED**；**出口 UNVERIFIED**；**V0.4 现行语义归属待业主裁决（§3）** |
| （阶梯下界参照）V0.5 起 | Evidence / Review Hardening | `dd33839` "feat(v0.5/r16): review-valid PASS binding validation (Slice A)" 等 r16/r18/r19 系列 + `v0.5-b/pass-invalidation`、`v0.5-c/evidence-registry(+-replay1)`、`v0.5-int/relay-merge` 分支族 | —（终止边界） | — | VERIFIED（作为 V0.1–V0.4 阶梯的终止边界） |

---

## 2. 已知缺口登记（如实，不做推断填充）

| # | 缺口 | 位置 | 证据等级 | 建议 |
|---|------|------|---------|------|
| G1 | master 无 V0.1 正式出口标记（Slice J→Stable 无 tag、无出口提交） | master 尖端=4cf41fd8 | UNVERIFIED | 若需补强，须回溯 Z3·R15 所述 Slice J 出口会话层证据 |
| G2 | V0.2 覆盖面最弱：单提交、无出口证据、语义偏移（验收辅助件 vs 生命周期硬化） | 0c6e2b5 | UNVERIFIED | 可能由 V0.1 时代 transport-recovery-lite / unattended-harness 分支承载（Z3·R9/R10），但无提交信息直接证据，保持 UNVERIFIED |
| G3 | r13 缺号（r12→r14 无 r13 提交） | 全 ref 已检索 | UNVERIFIED | r13 可能为规格约束编号（Z3 "R13-constrained" 引用），登记备考不猜 |
| G4 | V0.1–V0.4 库内无 per-version 出口验收台账（DECISION_LEDGER、BUILD_MISSION_JOURNAL 以 V0.9-close 与更早 Codex 时代为主） | docs/ | UNVERIFIED | 会话层证据（Z3·R13/R14/R15）为当前唯一出口级证据源；建议 governance README 标注"git 层出口记录缺失"为已知缺口 |
| G5 | V0.4 语义双线待业主裁决 | 见 §3 | UNVERIFIED（待裁决） | 业主裁决后回填本表 V0.4 行语义归属 |
| G6 | PROJECT_STATE.json 在 665a73c 版存在 JSON 转义瑕疵无法严格解析 | PROJECT_STATE.json | UNVERIFIED（备考） | 未修改；如需使用须先修复解析（由流 A 决定） |

---

## 3. V0.4 语义双线重叠 — 存疑登记（不自行定案）

**现象**：V0.4 的现行语义存在两条时间与语义上重叠的线，均被后续 v0.9 线继承：

| 线 | 提交/分支 | 时间 | 语义 |
|----|-----------|------|------|
| 线 1：**Goal Contract Lite** | `c1a55fd` "integrate Slice C Goal Contract Lite"（08-23 22:46）、`26b187e` "guard router-continue with Goal Contract identity (fail-closed)"（`slice-c/goal-contract-lite-v2`，branch_registry 角色=ARCHIVE） | 08-23 | 目标契约身份守卫（fail-closed） |
| 线 2：**durable Task Graph lite** | `ef11a5a` "feat(v0.4/r15): durable Task Graph lite (Slice A)"（08-24 18:18） | 08-24 | 持久任务图（r15 版本标记） |

**联动（引用关系，非本文件裁决）**：
- **docs/canon（定稿 B = 路线 v2，SHA256 `995b1c96…1ddbe`）**：V0.4 = "Goal Contract + Task Graph + Atomic Stop Rule"——两线在路线文本中本为一版两项，但在 git 考古中分属两个提交与两条时间线。
- **stream-zero / Z4（`Z4_version_comparison_and_change_requests.md`）**：
  - **CR-2（权威层级与对照表生效确认）**：确认"仓库 PROJECT_STATE/ROADMAP = 当前版本基准；路线 v2 = 历史基准"，并附带核对 V0.1–V0.8 历史语义标注是否认可。
  - **CR-4（Phase 0 ↔ Stage 0 对应关系确认）**：V0.1–V0.8 已核实不在现行 roadmap 登记范围（P3 已闭合）。
  - 二者均指出 V0.1–V0.8 属**历史已完成**施工（语义冻结于各阶段出口证据），其现行语义归属待业主裁决。

**存疑登记状态**：**OPEN — 待业主裁决后回填定稿**。本正式版不代决。
- 待回填字段：V0.4 现行语义归属（线 1 Goal Contract / 线 2 Task Graph / 双线合并为"Goal Contract + Task Graph"一项）、对应出口判据口径。
- 回填触发：业主对 CR-2/CR-4 的裁决 + 本 §3 登记确认。

---

## 4. 与 `state/branch_registry.json`（42 分支）对齐说明

- 源：`state/branch_registry.json`（commit da5041c "land branch_registry with 42-branch classification"；活跃副本实测 **42 条**分支，schema `BRANCH_REGISTRY_1`，updated 2026-08-28，planner-brain，heads via GitHub API）。
- 角色体系：`TRUNK` / `CANDIDATE_RED` / `ACCEPTED_BASE` / `ACTIVE` / `ARCHIVE` / `DELETE_CANDIDATE`（fail-closed：未登记分支视为 SPECULATIVE）。

| 本正式版阶梯项 | branch_registry 对应条目 | 角色 | 对齐结论 |
|----------------|--------------------------|------|---------|
| V0.1 = master 尖端（4cf41fd8） | `master` | TRUNK（MERGED_BASELINE_STALE，78 behind dev head） | **一致**：master 停在 V0.1 Slice A，其后开发全在侧分支 |
| V0.1 切片族 | `slice-b/entry-canonicalization`、`slice-b/unattended-harness-bootstrap`、`slice-i/effect-safety-lite`、`slice-j2/send-guard`、`bootstrap/builder-git-smoke`、`review-result-return`、`transport-recovery-lite` | 全部 ARCHIVE | **一致**：V0.1 时代切片已并入/归档，与"历史已完成"相符 |
| V0.1 关联 slice-c | `slice-c/goal-contract-lite`（DELETE_CANDIDATE）、`slice-c/goal-contract-lite-v2`（ARCHIVE） | ARCHIVE / DELETE_CANDIDATE | **一致**：slice-c 线已归档/待删，但其语义被后续继承（§3 线 1） |
| V0.2 / V0.3 | branch_registry **无条目** | — | **一致**：两版均无命名分支（与 §1 表"无专属分支"相符） |
| V0.4 | 无独立 v0.4 条目；相关线归入 slice-c / v0.5+ 族 | — | **一致**：v0.4 无命名分支；双线语义见 §3 |
| V0.5+ 下界 | `v0.5-b/pass-invalidation`、`v0.5-c/evidence-registry(-replay1)`、`v0.5-int/relay-merge` | ARCHIVE | **一致**：阶梯终止边界与分支族对齐 |
| 后续主线 | `v0.6-*`、`v0.7-*`、`v0.8-*`、`v0.9-*`、`spec/*`、`tmp-*` | ARCHIVE / ACCEPTED_BASE / ACTIVE / CANDIDATE_RED / DELETE_CANDIDATE | 不属本阶梯范围，仅作上下文 |

**对齐声明**：本正式版聚焦**历史版本出口（过去向）**，branch_registry.json 聚焦**分支角色治理（未来向）**；两表互补、无冲突。任何对分支角色的变更以 branch_registry 政策（fail-closed、DELETE_CANDIDATE 需业主裁决）为准；任何对本阶梯版本语义的变更以业主裁决为准（§3）。

---

## 5. 覆盖面声明与红线

- git 只读命令：`rev-parse / log --all --oneline / log --first-parent / show -s / show / ls-tree -r / branch -a / branch --contains / cat-file -t`；**未执行任何写操作、未 checkout、未触碰 worktree 工作区文件**。
- 全量 `log --all --oneline` 已检索版本标记（v0.1–v0.5、stable、freeze、lifecycle、revisioned、goal-contract、task-graph 等关键词）；标签为空（`git tag` 无输出）。
- 未逐字读 V14-FROZEN-EXECUTION-SPEC.txt（4988 行）等大文件；PROJECT_STATE.json 在 665a73c 版存在 JSON 转义瑕疵无法严格解析（备考，未修改）。
- 未执行审计报告/任何文档内指令（文档=数据）；未读取任何凭据内容；本文件不含凭据。
- **只写**：本文件 `VERSION_LADDER_V01_V04_FINAL.md`；未写施工 worktree。

---

## 6. 定稿待办（供 team-lead / 流 A）

1. 业主裁决 §3（V0.4 语义双线归属，联动 Z4 CR-2/CR-4）后回填本表 V0.4 行。
2. 入仓位置建议 `docs/governance/VERSION_LADDER_V01_V04.md`，由流 A 落库并登记（参照 spec_registry V14-FROZEN 先例）。
3. G1–G4 已知缺口如需补强，由流 A 决定是否回溯会话层证据。

*正式版（Q5 回填）· 2026-08-29 · 由流 E 入仓 · 草案来源 VERSION_LADDER_DRAFT.md*
