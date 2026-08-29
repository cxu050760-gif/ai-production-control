# BUILDER_RULING_GATE23 — 发送路径 ②③ 门零生产者：定性、裁定与交底

裁决人：主脑（本会话，非 Builder）
对象：续作 Builder（当前在 `031cb4e3/b1` 施工 `test_send_guard_offline.py`）
日期：2026-08-28
裁决链：SPEC `3deccf58…41fa` → R1/R2 → R18 → R3/R4 → TIER2 → EGRESS → T11B →
AD8TCB（`a32e14a4…d8da`）→ FINALBATCH（`1987b91e…5313`）→ **本裁决**
候选：v0.9-b1/authority-effect-core@a18d0d2

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
## §1 裁决摘要（先看这里）

1. **最终批继续准行**。7 例（多进程：`start→send`、`router-start→router-continue`）
   的场景适配是合法的测试场景构造，按 FINALBATCH §2 配方执行。
2. **但本批的"全绿"不得被读成产品可用**。实测确认：Runtime Lite 发送路径的
   ②③ 门**在产品侧是零生产者状态键**——产品自身永远无法自行满足它们。
   详见 §2。这与 egress 回归同属 §6.7 缺陷类。
3. **2 例（router-run）不在本批翻绿**。`router-run` 单进程内建 run 并立即驱动，
   无注入点，②③ 门不可达。触达 FINALBATCH §4 停止阀 → **登记为已知缺陷，
   不得为翻绿自行扩写产品路径**。详见 §5。

RELEASE_STATUS 维持 `PRODUCT_NOT_READY`。本裁决不解除收口清单第 1 项（TCB 封印）。

## §2 取证 F-02：②③ 门零生产者（可复现）

在 `a18d0d2` 原地执行：

```
[E1] grep -rn "effect_tcb_verified" --include=*.py . | grep -v test_
     → ./runtime/effect_safety_lite.py:716   （唯一出现：读取）
[E2] grep -rn "grant_authorization" --include=*.py . | grep -v test_
     → 仅 src/aicontrol/acceptance.py:176/809/863
       —— 是 ControlStore 的 store.grant_authorization（签名含 effect_type/nonce，
          冻结矩阵 R34 报错文本可证），与 Runtime Lite
          effect_safety_lite.grant_authorization 是两个不同子系统的不同 API。
[E3] Runtime Lite CLI 全部动词：
     directive done health metrics recv report router-continue router-run
     router-start router-step send start state-recover state-verify status
     step task-add task-list task-update work
     —— 无授权签发动词、无 TCB 验证动词。
```

结论（三条互证）：

- **② TCB**：`effect_tcb_verified` 全仓库只有 `effect_safety_lite.py:716` 一处
  **读取**，无任何写入者。
- **③ 授权**：`effect_authorizations` 的唯一写入点是
  `effect_safety_lite.grant_authorization`（:181），而该函数**无任何产品调用方**，
  也**无任何 CLI 入口**。

⇒ **Runtime Lite 发送路径在生产中永远无法自行通过 ②③ 门。**
该路径的对外发送能力在产品侧是结构性死锁的，不只是"没测到"。

## §3 定性

与 egress 回归（b1 replay `50cf8bd1` 把 egress 由参数式重写为状态键式、
默认 False、零生产者）**完全同类**：状态键式闸门 + 零生产者。
按规格 §6.7 属必须在 CLOSE 内修的缺陷类。

**关键区分（勿混淆）**：

- FINALBATCH §1 主脑实证回答的是**测试可行性**问题——"夹具能否满足③门？"
  答案是能，且走产品正门（自签被 API 拒）。
- 本裁决回答的是**产品可行性**问题——"产品自己能否满足③门？" 答案是**不能**。

两者都成立。前者的成立**不能**推出后者。
项目纪律原文：「不要把测试 PASS 自动当成 Release Ready」。本批正是该陷阱的实例。

## §4 对 7 例的裁定：准行（附义务）

准行 FINALBATCH §2 三门配方于 7 处多进程位点：

| 文件 | 位点 | 说明 |
|---|---|---|
| `test_send_guard_offline.py` | j2（`start`→`send`）、j4（`router-start`→`router-continue`） | j4 双目的地，见 §6 |
| `test_ec_gate_offline.py` | s3（SendPathComposeTests.start→send） | s1/s2 由 EC 外层闸门拒绝，注入不影响 |
| `test_ec_telemetry_offline.py` | t3（`start`→`send`） | |
| `test_ec_router_telemetry_offline.py` | r5 / r6 / r8（`router-start`→`router-continue`） | 双目的地，见 §6 |

义务：

1. AD-8 登记册须逐点位写明"场景构造，期望未改"，并**额外**写明一句：
   「②③ 门由夹具场景满足，非产品能力（F-02）」。
2. 台账 D016 须引本裁决，使取证链闭合。
3. 负例文件 `test_v09_close_egress_wiring_offline.py` 不得跳过。

## §5 对 2 例的裁定：停止阀，登记已知缺陷

`test_send_guard_offline.py::test_j3_router_run_records_contract_and_router_send_effects`
`test_ec_router_telemetry_offline.py::test_r1_router_pass_records_artifact`

依据：`cmd_router_run`（runtime.py:2132）在同一进程内 `_router_create(...)`
后**立即** `_router_drive(rid, ...)`；不接受 `--run-id`，无进程间注入窗口。
实测：`router-run --egress-policy-file` 后投影已写入（①门开），
仍 `rc=6 HARD_BLOCKED`，state 中 `effect_tcb_verified=None`、
`effect_authorizations=0` —— ②③ 门不可达。

裁定：**本批不翻绿**。禁止为此给产品加注入钩子或签发位点
（FINALBATCH §4 / T11B §5.b / AD8TCB §2 纪律 1）。
处置：登记为已知缺陷，进台账，随 F-02 一并交产品裁决（§7）。

## §6 给 Builder 的关键交底（防止卡住）

**generation 约束**：`_valid_authorization` 只接受
`rec["generation"] == state["effect_authorization_generation"]`（当前值）。
而 `grant_authorization` 每次调用都会 `_next_authority_generation(state)` 自增。
⇒ **同一 run 内无法并存两枚窄授权**：签第二枚会让第一枚立即变成
`authorization generation stale`。

因此 `router-start→router-continue` 这类**一次注入、两次发送**
（builder 一次 + reviewer 一次，目的地不同）的流程，**必须**用产品自带的
`*` 通配符：`authority_scope_allowed` 对 provider/resource/destination
支持显式 `*` 通配（`security.py:74 _matches_authorized`，wildcard=True）。

```
单目的地 → destination/resource 精确绑定
多目的地 → destination="*", resource="*"
purpose / identity / data_classes 一律精确绑定（不支持通配，保持收紧）
```

参考实现（本会话已验证可用，纯测试件，未入库以免与你的工作树冲突）：
`v09-close-pack/_collision_snapshot_2249/effect_scenario_fixture.py`
—— 同目录另有 `test_ec_gate_offline.py.WORKBUDDY`、
`test_ec_telemetry_offline.py.WORKBUDDY`（已实测 18/18、10/10 全绿）。
**采用或整体替换均可，但不要混用两套写法。**

## §7 待产品裁决（新议题，非本批）

②③ 门需要 in-band 生产者才能称为可用。待裁决项：

1. TCB 验证的**产品侧写入点**在哪（谁、在何时、凭什么把
   `effect_tcb_verified` 置真）；当前答案是"无人"。
2. Runtime Lite 的授权签发**产品侧入口**是什么（CLI 动词？运行前配置？）；
   当前答案是"无"。
3. 二者与收口清单第 1 项（TCB `UNVERIFIED_AFTER_CONTROLLER_CHANGE`，
   属发布负责人）的先后关系。

在此之前，任何"发送路径已打通"的表述均不成立。

## §8 审查提示

- **最高权重区**：出站接线 + AD-8 登记册 + 三门负例 + **②③ 门由夹具满足这一事实是否被如实登记**。
- **`test_ec_telemetry_offline.py::test_t2` 为假绿**：其断言
  `assertNotIn(code,(0,5))` 因 egress 拒绝返回 6 而通过，
  并非它本意要验证的传输失败。本批未改动它。建议审查时一并处理
  （armed 后它才真正测到传输失败链）。

## §9 本裁决边界

本裁决**未**改动任何产品代码、测试、期望或断言；未提交、未推送。
本会话在确认存在并发施工后已撤销自身对 `test_ec_gate_offline.py`、
`test_ec_telemetry_offline.py` 的编辑并移出 `effect_scenario_fixture.py`，
worktree 中仅保留 Builder 的 `test_send_guard_offline.py` 改动。
