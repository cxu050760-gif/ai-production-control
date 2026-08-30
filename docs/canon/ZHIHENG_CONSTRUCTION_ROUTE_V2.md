# 执衡施工总路线 v2

先记住一个总原则：

```
```

```
不是：

V0.1 没安全
V0.5 才有 Evidence
V0.7 才有 Reuse
V0.9 才有 Authority

而是：

V0.1 有最低可信底线
↓
后续逐层强化
↓
最终形成完整系统
```

---

# Stage 0：事实收口 / Construction Baseline

## 唯一目标

不是“整理执衡全部历史”。

而是：

> **确认 V0.1 要依赖的现有资产，建立一个不再混乱的施工基线。**

## 范围硬限制

只考古：

-  Bridge； 
-  当前 Runtime； 
-  Reviewer 路径； 
-  Trae-Ralph / 自动续跑里真正需要复用的能力； 
-  Browser 当前正式入口； 
-  当前 Workspace / Git 状态； 
-  V0.1 必须依赖的脚本与组件。 

其他全部允许暂时：

```
```

```
UNKNOWN
ARCHIVED
DEPRECATED
EXPERIMENTAL
```

**禁止因为 Stage 0 又重新考古全部历史。**

---

## Stage 0.1 Truth Ownership

先定义谁说了算。

### `PROJECT_TRUTH`

长期治理真源：

```
```

```
产品是什么
最终 Goal
硬规则
关键用户决定
正式入口
废弃路线
关键限制
```

### `CAPABILITY_REGISTRY`

能力真源：

```
```

```
capability_id
status
implementation
entry
evidence
limitations
```

### `STABLE_MANIFEST`

当前可生产 Stable 真源：

```
```

```
version
commit/hash
entry
dependencies
known limitations
evidence
```

### `EVIDENCE_INDEX`

Append-only 证据索引。

### `CURRENT_PROGRESS`

**派生 View。**

禁止成为独立 Truth。

### `AI_CONTEXT`

**机械生成 View。**

禁止直接编辑。

这一点非常关键。

未来关系应该是：

```
```

```
Truth / State / Registry
        ↓
   mechanical derive
        ↓
Current Progress
        ↓
AI Context
```

绝不能反过来。

---

# Stage 0.2 Capability Audit

把现有能力逐个归类：

```
```

```
DISCUSSED
FOUND
LOCAL_EXISTS
IMPLEMENTED
LOCAL_TEST_PASS
R_REVIEW_PASS
E2E_PASS
PRODUCTION_VERIFIED
PARTIAL
BLOCKED
DEPRECATED
UNKNOWN
```

Canonical Definition 本身就明确要求不能把“实现过”直接等价成“产品完成”。

尤其是：

```
```

```
Bridge
Runtime
R loop
Conversation isolation
Continuation
Browser
```

只认 Evidence。

找不到：

> 降级状态。

不重新脑补。

---

# Stage 0.3 Critical-path Smoke

不是重测所有历史。

只跑 V0.1 必须依赖的链：

```
```

```
Runtime
→ Worker
→ Browser/Bridge
→ R
→ response back
```

确认今天还能跑。

---

# Stage 0.4 Reuse Gate Lite

从这里开始，**以后每开发一个新能力都必须先做。**

最小记录：

```
```

```
Need:
Searched:
Candidates:
Decision:
- REUSE
- ADAPT
- COMPOSE
- BUILD

Why:
Minimal custom boundary:
```

这是施工纪律。

以后 V0.7 才让执衡自己自动完成这件事。

定义明确将 `Reuse > Adapt > Compose > Build from scratch` 定义成进入实质自研前的硬门禁，而不是建议。

---

# Stage 0 EXIT

只有：

```
```

```
V0.1 所需旧资产确认
+
关键路径今天仍能运行
+
正式 Stable 基线明确
+
新 AI 能知道入口
```

才结束 Stage 0。

**时间上不允许无限整理。**

---

# V0.1：Single-Task Reliable Loop

这是第一个真正的执衡产品。

## 目标

用户提供：

```
```

```
GOAL
必要权限
```

系统完成：

```
```

```
Submit
↓
Run
↓
Worker
↓
Artifact
↓
Machine Check
↓
Reviewer
↓
REWORK / PASS
↓
自动继续
↓
RESULT
```

---

# V0.1 必须同时存在五个最小内核

这是修正版最大的变化。

## A. Canonical Run State Lite

从第一版就只能存在**一个 Run State 真源**。

例如：

```
```

```
project_id
run_id
goal
current_status
current_task
worker
candidate_id
review_status
next_action
paused
stopped
```

V0.3 不是再造第二套 Canonical State。

而是：

> 把这套 State 升级成 Revisioned State。

---

# B. Evidence Binding Lite

第一版 Reviewer 就不能审“某个大概的结果”。

Candidate 必须拥有：

```
```

```
run_id
candidate_id
artifact_hash
evidence_id
```

Reviewer 请求绑定：

```
```

```
RUN
CANDIDATE
ARTIFACT HASH
EVIDENCE
ACCEPTANCE
```

R PASS 对应的只能是：

> **这个 Candidate。**

如果 Artifact 改了：

```
```

```
old PASS != current Candidate
```

即使 V0.1 暂时没有完整自动失效系统，也必须明确拒绝复用。

---

# C. Minimum Safety Kernel

V0.1 就有：

```
```

```
project_id
run_id
workspace boundary
run ownership
candidate ownership
allowed effect boundary
STOP
PAUSE
```

Worker 不能：

```
```

```
跑出 workspace
偷偷换 project
修改 Control State
无视 STOP
```

完整权限系统以后再做。

但底线从第一天存在。

Canonical Definition 把 Worker 与 Control Plane 的权限分开，并明确 Worker 不能自己修改成绩、Authority、Acceptance 和 Canonical State。

---

# D. Baseline Execution Capability

V0.1 已经正式承认它需要：

```
```

```
Filesystem
minimal Shell
existing Browser Bridge
Git（任务需要时）
```

这不是 V0.11 才出现。

V0.11 是**生产能力扩展**。

---

# E. Adapter Seam

V0.1 不造完整 Provider Registry。

但内部代码不能写成：

```
```

```
if chatgpt:
...
if workbuddy:
...
```

核心调用至少经过：

```
```

```
BrainPort
WorkerPort
ReviewPort
BrowserPort
```

哪怕当前只有：

```
```

```
ChatGPTReviewAdapter
CurrentWorkerAdapter
```

也行。

这样 V0.8 是“产品化 Adapter”，不是“大重构救火”。

---

# V0.1 验收

不是三个 TXT。

要三种路径：

### Case A — Create

```
```

```
创建一个 Artifact
→ machine check
→ PASS
```

### Case B — Modify

```
```

```
读取已有 Artifact
→ 修改
→ machine check
→ R PASS
```

### Case C — Rework

```
```

```
制造错误 Candidate
→ R REWORK
→ Runtime 自动继续
→ Worker 修复
→ 新 candidate/hash
→ R PASS
```

三个全部满足：

-  Cold Start； 
-  无人工搬 Reviewer 信息； 
-  无用户发送“继续”； 
-  Artifact 真实存在； 
-  PASS 与 Candidate 绑定； 
-  最终 RESULT 可读取。 

通过以后：

> **Stable V0.1**

---

# V0.2：Lifecycle Hardening

这一版只解决：

> **AI 会停，但项目不能跟着死。**

Canonical Definition 直接规定：Agent 可以停，任务不能因为 Agent 停而停；AI 回合结束也不等于项目结束。 

增加：

```
```

```
continuation
heartbeat
watchdog
invocation state
retry policy
worker recovery
browser recovery
resume
```

以及非常重要的：

```
```

```
generation
fencing token
```

---

## V0.2 必须解决

旧 Worker：

```
```

```
Generation 4
```

Controller 已经：

```
```

```
Generation 5
```

旧 Worker 即使突然恢复：

```
```

```
Effect denied
```

不能诈尸。

---

# V0.2 验收

故意：

-  杀 Worker； 
-  重启 Runtime； 
-  让模型输出 Final； 
-  Browser 会话断开； 
-  Pause/Resume； 
-  让旧 Worker 恢复。 

任务仍继续。

旧 Generation 不允许写入。

---

# V0.3：Revisioned Canonical State

现在才开始强化 State。

不是创建第二套。

而是：

```
```

```
Run State Lite
↓
Revisioned Canonical State
```

---

## 增加

```
```

```
rev-0001
rev-0002
rev-0003
HEAD
previous_known_good
schema_version
integrity hash
```

写入流程：

```
```

```
Create revision
↓
Validate
↓
Commit
↓
Atomic HEAD Switch
```

Canonical Definition 要求 Canonical State 具有 revision、known-good revision、hash、schema 和 atomic HEAD switch。

---

## 同时加入

```
```

```
Project Truth
Decision Log
Failed Route Log
Current Progress
Context Capsule
```

但记住：

```
```

```
Current Progress = derived
Context Capsule = derived
```

---

# V0.3 验收

故意：

```
```

```
损坏 newest revision
↓
kill Runtime
↓
新 AI 接管
↓
recover previous known-good
↓
继续 Task
```

成功才算 PASS。

---

# V0.4：Goal Contract + Task Graph

到这一步，执衡开始正式解决：

> **大目标如何可靠地不断拆。**

---

# Goal Contract

完整版加入：

```
```

```
Goal
Deliverables
Acceptance Criteria
Non-goals
Constraints
Quality Expectations
Resource Budget
Permissions
Data Egress
Effect Policy
Parallelism
Human Gate policy
```

这正对应定义中的正式 Goal Contract。

---

# Task Graph

正式建立：

```
```

```
task_id
parent
dependencies
state
input
output
owner
locks
artifact
evidence
retry
next_action
```

状态：

```
```

```
READY
RUNNING
WAITING
BLOCKED
DONE
```

运行中新发现问题：

```
```

```
Issue
↓
evaluate
↓
Task Graph
```

不能 Worker 偷偷扩大 Scope。

定义要求系统维护正式 Task Graph，而不是只有“下一步”，并采用一个真源、AI/Human 两种视图。

---

# Atomic Stop Rule

以后“无限细化”正式改名：

> **Recursive Decomposition with Atomic Stop Rule**

每个 Task 如果同时满足：

1.  只有一个主要结果； 
2.  Input 明确； 
3.  Dependencies 明确； 
4.  Scope 明确； 
5.  Non-goal 明确； 
6.  成功/失败可判定； 
7.  有 machine check 或确定性验收； 
8.  可以独立 retry / rollback； 
9.  Worker 不需要重新规划整个项目； 

则：

> **STOP SPLITTING**

禁止继续微拆。

反之才继续：

```
```

```
Version
→ Milestone
→ Slice
→ Task
→ Action
→ Check
```

所以“无限细化”其实意味着：

> **细化能力无硬层数上限，但实际 Task 必须在 Atomic 条件满足时停止。**

这个区别非常重要。

---

# V0.5：Evidence / Review Hardening

V0.1 已经有可信底线。

这里做的是工业化。

增加：

```
```

```
state_revision
review_id
evidence provenance
independent evidence collector
Review Bundle
automatic invalidation
material-change detection
```

---

## Review Bundle

例如：

```
```

```
goal_contract
candidate_id
artifact hash
state revision
machine evidence
external evidence
known limitations
review request
```

Reviewer PASS：

```
```

```
PASS(
 candidate_id,
 artifact_hash,
 state_revision,
 evidence_set,
 review_id
)
```

Artifact 变化：

```
```

```
PASS → STALE
```

Definition 明确要求 Reviewer PASS 绑定 commit/artifact hash/state revision/evidence/review identity，Material Change 后旧 PASS 自动失效。

---

# V0.6：EC / Execution Correction

现在正式解决你碰到很多次的：

> 弱 AI 很勤奋，但越干越偏。

优先做确定性规则。

---

## 第一批规则

```
```

```
MAX_RETRY
SAME_FAILURE
NO_PROGRESS
SCOPE_GROWTH
REPEATED_SEARCH
DUPLICATE_WORKER
UNNECESSARY_INFRA
OFFICIAL_ENTRY_BYPASS
WAIT_WITH_READY_WORK
```

---

## EC 动作

```
```

```
STOP_RETRY
REDIRECT
REQUEUE
SPLIT_TASK
CHANGE_TOOL
ESCALATE_BRAIN
ESCALATE_C
```

EC 尽量不需要强 AI。

这与定义中“能通过规则、状态机、计数器判断的事情，不浪费强 AI”一致。

---

# V0.7：Brain + Strategic C + Strategic Reuse

到这里才真正把“方向判断”自动化。

此前已经存在：

> Reuse Gate Lite 施工纪律。

现在升级成：

> **系统自身能力。**

---

## Brain

负责：

```
```

```
planning
task graph changes
route selection
tool selection
escalation
```

## C

监控：

```
```

```
Goal distance
scope growth
infrastructure drift
wrong assumptions
cost explosion
repeated branch failures
low progress
unnecessary build
```

输出：

```
```

```
ON_COURSE
CORRECT
REPLAN
STOP_BRANCH
ESCALATE
```

Definition 对 C 的职责就是审路线，而 EC 审执行现场，R 审成果。 

---

# V0.8：Provider / Agent Adapter Productization

这时候才把接口体系完整产品化。

增加正式：

```
```

```
Capability Interface
Provider Adapter
Brain Adapter
Worker Adapter
Reviewer Adapter
Browser Adapter
```

再加入：

```
```

```
Capability Registry
availability
quota
cost
reliability
permissions
status
```

真正达到：

```
```

```
ChatGPT down
→ replace

Worker A down
→ Worker B

Provider gone
→ project survives
```

这正是产品定义里的 Provider Independence。

---

# V0.9：Authority / External Effect Safety Hardening

注意名字。

不是：

> Authority 第一次出现。

而是：

> **完整安全系统。**

---

## 完整化

```
```

```
Authority Matrix
Identity Binding
Generation
Fencing
Effect Ledger
Write-Ahead Intent
OUTCOME_UNKNOWN
Reconciliation
Authorization Revocation
Credential Isolation
Data Egress
Supply Chain Gate
Human Gate
```

---

## 一个典型动作

```
```

```
Prepare Effect
↓
write intent
↓
capture precondition
↓
check authority
↓
execute
↓
observe
↓
commit
```

如果：

```
```

```
execute
↓
network dies
```

进入：

```
```

```
OUTCOME_UNKNOWN
↓
RECONCILE
↓
inspect reality
↓
SUCCESS / FAILED
```

而不是直接 retry。

这是定义对真实副作用控制的核心要求。

---

# V0.10：Multi-Worker

这时候才值得真正并行。

增加：

```
```

```
scheduler
ready queue
resource locks
worker ownership
branch/worktree isolation
browser isolation
conflict detection
parallel ROI
```

关键原则：

```
```

```
Task A = WAITING_REVIEW
Task B = READY
Task C = READY

→ B/C continue
```

而不是全系统睡觉。

定义也明确规定 Review 冻结 Candidate，而不是冻结整个 Builder。

---

# V0.11：Production Capability Expansion

现在名字改掉。

不是：

> 第一次接生产工具。

而是：

> **扩大已经存在的生产能力表面。**

---

## Baseline 已经存在

V0.1：

```
```

```
Filesystem
Shell Lite
Browser Bridge
Git when needed
```

---

## V0.11 逐 Slice 扩展

```
```

```
V0.11.1 Browser Read Hardening

V0.11.2 Browser Write

V0.11.3 Upload / Download

V0.11.4 API

V0.11.5 GitHub

V0.11.6 Docker

V0.11.7 Local App

V0.11.8 Media

V0.11.9 Automation

V0.11.10 Other production tools
```

**每一个都是独立 Candidate。**

绝对不做：

> “万能电脑 Agent V0.11”。

---

# V1.0：Self-hosted Iteration

最终才到这里。

结构：

```
```

```
       Stable Zhiheng
             │
     ┌───────┴────────┐
     │                │
 Candidate        Production Work
     │
     ▼
Reuse Gate
     ↓
Brain
     ↓
Task Graph
     ↓
Worker
     ↓
EC
     ↓
Test / Evidence
     ↓
R
     ↓
C when needed
     ↓
Acceptance
     ↓
Candidate Release
```

Candidate 永远不能未经 Acceptance 直接替代 Stable。

Definition 对 Self-hosted Iteration 的要求就是 Stable 可以参与开发 Candidate，但 Candidate 在正式验收前不得替换 Stable。

---

# 最终版本依赖关系

现在路线已经不应该理解成：

```
```

```
0 → 1 → 2 → 3
```

而应该理解成可靠性逐层叠加：

```
```

```
                     ┌─ Evidence Lite ───────── Evidence Hardening
                     │
Stage 0 ─ V0.1 ──────┼─ Safety Lite ─ Generation ─ Authority Hardening
                     │
                     ├─ Run State ─ Revisioned State
                     │
                     ├─ Reuse Discipline ─ Strategic Reuse
                     │
                     └─ Adapter Seam ─ Adapter Productization
```

这个图非常重要。

它意味着：

**V0.5/V0.7/V0.8/V0.9 不是凭空引入新概念。**

它们是在把早期存在的最低机制逐渐升级。

这比上一版稳很多。

---

# 每个版本统一施工流程

以后所有 V0.x 都用同一套流程：

```
```

```
① Define Slice
↓
② External Reuse Check
↓
③ Freeze Acceptance
↓
④ Atomic Decomposition
↓
⑤ Build Candidate
↓
⑥ Machine Check
↓
⑦ Evidence
↓
⑧ Independent Review
↓
⑨ REWORK
↓
⑩ Acceptance
↓
⑪ Freeze Stable
↓
⑫ Update Registry / Truth
↓
⑬ Start next Candidate
```

这样开发“执衡”本身，也开始遵守“执衡”的原则。

---

# Task 的最终原子模板

以后一个 Task 最好统一成：

```
```

```
TASK_ID

OBJECTIVE
唯一主要结果

WHY
为什么现在必须做

INPUT
已知输入

DEPENDENCIES
依赖

SCOPE
允许修改

NON_GOALS
明确不做

AUTHORITY
允许什么 Effect

ACTION
具体任务

OUTPUT
必须产生什么

MACHINE_CHECK
程序如何验证

EVIDENCE
留下什么证据

ROLLBACK
失败怎么恢复

DONE
什么条件下才能 Done
```

如果 Worker 看完以后仍然需要回答：

> “所以我到底应该先干什么？”

说明 Task 还不够原子。

如果已经满足 Atomic Stop Rule：

> 禁止继续拆。

---

# 现在真正的近期施工队列

你现在脑子里其实不用装 V0.3～V1.0。

**真正 Active 的只有：**

```
```

```
ACTIVE
│
├── Stage 0
│   ├── Truth ownership
│   ├── V0.1 asset inventory
│   ├── capability status
│   ├── stable manifest
│   ├── evidence index
│   ├── critical-path smoke
│   └── Reuse Gate Lite
│
└── V0.1 Candidate
    ├── single Run State
    ├── one official entry
    ├── Goal Contract Lite
    ├── Worker loop
    ├── baseline FS/Shell/Browser
    ├── Candidate identity
    ├── Evidence Binding Lite
    ├── Reviewer loop
    ├── automatic REWORK
    ├── Minimum Safety Kernel
    ├── Adapter seam
    └── 3-path acceptance
```

**其他版本全部只有 Roadmap 权，不具有 Execution 权。**

这句话我甚至建议以后直接变成施工规则。

因为这能防止又出现：

> 做 V0.1 的时候突然想到 V0.7 很重要，于是跑去造战略 Router。

---

现在这版我认为已经可以作为**执衡正式施工路线的 Canonical Roadmap v1**：终局 Canonical Definition 不动，施工 Roadmap 独立存在；以后发现实现顺序需要调整，只改 Roadmap，不重新撬动产品定义。

而你现在下一步其实已经非常明确了：

> **不再继续设计 V0.2～V1.0。先把 Stage 0 压缩完成，然后正式开** **`V0.1 Candidate`****。**

这一次确实应该开始往“东西越来越能用”走了，而不是“定义越来越完整”。
