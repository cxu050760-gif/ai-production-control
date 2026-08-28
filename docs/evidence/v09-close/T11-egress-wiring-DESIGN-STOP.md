# TASK-6 / T11 — egress 接线设计上报（未实施，按 §3 边界停下）

绑定：SPEC_SHA `3deccf58…41fa` · V14 `6fe3bb79…154df6` · BASE `50cf8bd1` · 前候选 `caedf5f3`
授权：`BUILDER_RULING_EGRESS` §3（runtime/ 单任务单位点例外）
§2 追认确认：(c) 推翻裁决假设记功、m1 不同 goal 保真追认

## 1. 停下的触发条款（原文）

> IMPLEMENTATION_BOUNDARY：最小接线；若发现最小修复必须把 Goal Contract
> 持久化穿过多层才能成立（即超出"接线"量级），**停下上报设计方案**，不得自行扩大。

本报告即该上报。**未改动 `runtime/runtime.py`、`runtime/effect_safety_lite.py` 或任何测试。**

## 2. 取证：判定输入在 runtime 侧不存在

REQUIRED_BEHAVIOR 与 §3.4 要求复用 `src/aicontrol/security.egress_allowed`，其签名为

```python
egress_allowed(*, classification, destination, provider, purpose,
               goal_contract: dict, authorization_scope: dict | None) -> bool
# 内部：policy = goal_contract.get("data_egress_policy", {})
#      destination_policy = policy.get(destination) or policy.get(provider) or policy.get("default", [])
```

逐项核对 runtime 发送路径实际持有的输入（`effect_safety_lite.install → gated_cmd_send`）：

| 判定输入 | runtime 侧来源 | 结论 |
|---|---|---|
| `destination` | `state["r_url"]`（`gated_cmd_send`） | ✅ 有 |
| `provider` | `state.get("effect_provider") or "chatgpt-web"` | ✅ 有 |
| `purpose` | 常量 `"review transport"` | ✅ 有 |
| `classification` | `state.get("effect_data_classification") or "INTERNAL"` | ✅ 有 |
| **`goal_contract["data_egress_policy"]`** | **不存在** | ❌ **缺失** |
| `authorization_scope` | `state["effect_authorizations"][id]` 仅含 holder/issuer/generation/quota，无 scope | ⚠️ 不完整 |

关键实测：

```
$ grep -rn "data_egress_policy" runtime/
runtime/test_v09_attack_matrix_offline.py:395     ← 仅冻结矩阵夹具（V09 canonical 侧单测自造 dict）
runtime/__pycache__/*.pyc                          ← 同上的缓存
（runtime/runtime.py 与 effect_safety_lite.py 内 0 命中）
```

⇒ 若今日直接把 `egress_allowed` 接进 `_runtime_preconditions`，传入的 `goal_contract` 只能是
空 dict 或伪造 dict：`policy={}` → `allowed_classes=set()` → **恒 False**。
后果是两种都不可接受：
- 传空：**9 例仍红**，未满足 REQUIRED_BEHAVIOR 1（合法外发放行）；
- 为翻绿而塞入 `{"default": [所有分级]}`：即 §3.4 与裁决书明令禁止的**恒真接线**，
  会使 SECRET/UNKNOWN/scope 不匹配全部放行 —— 比现状更危险。

而要让 `data_egress_policy` 真实存在，必须把它从 run 创建点（`runtime.py:998` 的 state 构造）
穿到 `load_state/save_state` 的持久化结构里 —— 正是 §3 预判的"超出接线量级"。

## 3. 三个候选方案（含代价，供裁决；Builder 不自选）

### A. 委托 canonical 判定源（改动面最小，跨层耦合最高）
发送点直接取权威 Goal Contract：`ControlStore.latest_goal(task_id)["contract_hash"/policy]`，
配合 `aicontrol.security.egress_allowed`。
- 优点：不新增策略词汇；策略单一来源（§31 第 9 条的许可语义与矩阵 R27-R29 锚定完全同源）。
- 代价/风险：Runtime V1 从此依赖 Controller SQLite；离线/无 DB 场景（多个 runtime 套件）会
  取得到空契约 → 仍恒拒，需要 fallback 语义（而 fallback 一旦"默认放行"即违 §3.3）。
- 位点：`effect_safety_lite._runtime_preconditions` + 传入 `task_id`。约 1 个函数 + 参数改造。

### B. run 状态持久化外发许可（最贴近"应有形态"，结构性最强）
在 `runtime.py` 的 run 创建处写入 `goal_contract` / `data_egress_policy`，随 state 持久化，
`_runtime_preconditions` 调 `egress_allowed` 判定。
- 优点：runtime 自洽、离线可用；许可真正"可被打开"且可按目的/接收方收紧。
- 代价/风险：改 state schema（`runtime.py` 结构性改动，§3 FORBIDDEN 明确点名函数搬家/拆分/改名，
  schema 变更同属此量级）；影响 `router-continue` 跨进程一致性（j4 用例）与既有 state 兼容性；
  需 V0.10 级设计评审而非 CLOSE 级接线授权。

### C. 外发许可来自显式策略文件（折中，引入新配置面）
约定一个 Goal Contract 路径（如 `config/` 或 run 目录下 `goal_contract.json`），
发送点读取后喂给 `egress_allowed`。
- 优点：不改 runtime state schema，改动集中在一个取值函数。
- 代价/风险：**新增策略载体**（§3.4 禁"新增策略词汇"是否涵盖文件载体需裁决）；
  许可与 Goal Contract 的权威关系变松，存在"策略文件与契约漂移"风险；9 例夹具需自备该文件
  → 可能变相由测试自造许可，削弱验收件效力。

## 4. Q1 已实测回答：只有 B 可行

原拟请主脑回答的 Q1，已用取证关闭，无需等待：

```
$ sed -n '/def _script_env/,/return env/p' runtime/test_send_guard_offline.py
    env["APC_RUNTIME_STATE_ROOT"]      = str(root / "state")     ← 唯一状态载体：JSON 文件目录
    env["APC_RUNTIME_BRIDGE_WRAPPER"] / INJECT_*                  ← 脚本化 fake transport
    （无任何 Controller / control.db 环境变量）

$ grep -ln "control.db\|aicontrol\|ControlStore" \
      runtime/test_send_guard_offline.py runtime/test_ec_gate_offline.py \
      runtime/test_ec_telemetry_offline.py runtime/test_ec_router_telemetry_offline.py
NONE
```

四例套件均以**子进程**方式启动 `runtime.py`，其可见状态只有 `APC_RUNTIME_STATE_ROOT` 下的
JSON run state，**既无 Controller SQLite，也不 import `aicontrol`**。由此：

- **A（委托 canonical 判定源）被证据排除**：这些路径根本取不到 Controller 的 Goal Contract，
  `latest_goal` 无源可依 → 恒 fail-closed → **9 例仍红**，不满足 REQUIRED_BEHAVIOR 1。
- **C（策略文件）不成立**：许可将由测试夹具自行书写，验收件退化为"测试自证放行"，
  且引入 §3.4 疑似禁止的新策略载体。
- **B 是唯一可行路线**：把 `goal_contract` / `data_egress_policy` 写入 runtime 自身的
  持久化 run state（`runtime.py` run 创建处 + `load_state/save_state` 结构），
  再由 `_runtime_preconditions` 用 `egress_allowed` 判定。

**B 的必要组成 = `runtime.py` 的 state schema 变更**，属 §3 明令禁止的结构性改动量级，
不在本次"单任务单位点例外"范围内。Builder 不自行扩大，故：

### 请求：开设 T11b 并给出边界

1. 授权改动 `runtime/runtime.py` 的 run state（新增 `goal_contract` 相关字段）与
   `runtime/effect_safety_lite.py` 的 `_runtime_preconditions`，判定函数仍 100% 复用
   `security.egress_allowed`（零新词汇）。
2. 明确许可来源的权威关系：run state 中的外发许可必须**由 Goal Contract 派生**，
   不得成为独立可写策略面（否则违反 `DATA_EGRESS_POLICY.md` 的目的/接收方/provider 特定性）。
3. 随 T11b 一并规定的回归面：`test_state_recovery_offline`（state 兼容性）、
   `test_j4_router_continue_preserves_contract_and_effect_across_processes`（跨进程一致性）、
   `runtime.py` 的 Slice A 冻结行为契约 AC-1..AC-11。
4. 出口判据沿用 §3：9 例期望一字不改转绿 + 新增 SECRET/UNKNOWN/scope 不匹配负例
   （证明非恒真）+ 矩阵 36/36 + `tests/` 137 全绿。


## 5. 已满足与未满足的出口判据

| §3 出口 | 状态 |
|---|---|
| 9 例红转绿（期望一字不改） | ❌ 未做（未改产品，未改期望） |
| 新增负例（SECRET/UNKNOWN/scope 不匹配被拒） | ❌ 待判定源确定后随实现提交 |
| 新增正例（许可成立放行且记录效果） | ❌ 同上 |
| 矩阵 36/36 保持 | ✅ 本轮零改动，维持 36/36 + R34 忠实探针 FAIL_CLOSED |
| `tests/` 137 保持全绿 | ✅ 维持（0F+0E） |
| `runtime/` 其余套件保持 | ✅ 维持（除该 9 例缺陷外逐项同基线） |
| 选址论证 | ✅ 本报告 §2/§3 |
| 无新增漂移 | ✅ doctor 仍仅 §4 已裁决的 registry b1-head 滞后一项 |

全量离线套件"真正全绿"（§4.3 原文判据）因此仍被这 9 例阻塞，等待 Q1/Q2 裁决。
