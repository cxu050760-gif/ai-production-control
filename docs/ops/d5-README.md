# D5 自举 L1 + 智能（Task Graph / Brain 选型）+ 缺陷→任务转换器 + Context Sufficiency — 设计说明（v1.1-blackbox）

> 执衡 v1.1-blackbox 开发线 · D5 任务 · 机器可完成部分（L0-L2）
> 交付：
> - `runtime/task_graph.py`（宪法 §17 Task Graph + §7 Brain 选型规则式）
> - `runtime/self_heal.py`（宪法 §68 自举：缺陷→goal 转换器 + 自愈管线 + fixlet SH-001）
> - `runtime/context_sufficiency.py`（宪法 §55 五分支自动路由）
> - `runtime/test_task_graph_d5_offline.py` / `test_self_heal_d5_offline.py` / `test_context_sufficiency_d5_offline.py`（40 单测）
> - `docs/evidence/d5/`（自举 L1 全链证据）
> - 本说明
>
> **⚠️ 解释器纪律（与 D1/D2/D3/D4 一致）**：运行与测试**必须用 Python312（生产 APC_PY）**：
> `C:\Users\17838\AppData\Local\Programs\Python\Python312\python.exe`。
> 本模块为纯标准库（无第三方依赖）；不发起任何真实 AI 调用（L3 之外）。

## 1. 定位

| 宪法条款 | 缺口（已实测确认） | D5 交付 |
|---|---|---|
| §68 自举 | 系统应能修复自身缺陷，无 L1 真实案例 | 缺陷→goal 转换器 + 自愈管线 + **L1 真实案例**（`test_v09_attack_matrix_offline.py` FAILED→36/36，权威矩阵零影响） |
| §17 Task Graph | 线性列表→依赖/并行标记/Owner/动态加任务未实现 | `task_graph.py`：节点(依赖/parallel_with/Owner/state) + 拓扑排序 + 关键路径 + DAG 环检测 + `add_subtask` 动态加任务 |
| §7 Brain | 契约级规则拆解→选 Worker/工具/重规划未实现 | `task_graph.py brain-pick`：按目标复杂度从 registry brains 节规则式选 Brain（简单→弱、复杂→强，参考 D2 路由语义） |
| §55 Context Sufficiency | 外部 Brain 信息不足→自动路由五选一未建 | `context_sufficiency.py`：①换本地 Brain ②换允许 Provider ③脱敏重试 ④Human Authorization ⑤BLOCKED（策略驱动阈值） |
| §60 升级梯 | 9 级阶梯未系统化 | 见 §6：本刀实现 L0-L2 对应项，L3-L9 映射留档 |
| §70 Trace | 缺"哪个 AI/Tool/为何 Retry/成本"字段 | 所有 D5 输出带 `trace: {model, ai, tool, reason_retry, cost}` |

**红线（本模块遵守）**：
- 输出为 inert 数据（`non_authority=True`）；任何 authority 词只作数据呈现，绝不代执行；
- 不改 `src/aicontrol/`（封印）、`config/production.json`、`runtime/runtime.py`、`runtime/adapters/` 既有、
  `config/capability-registry.json`、`scripts/relay_autopilot.py`、`runtime/parallel_scheduler.py` 等既有交付；
- 凭据不入仓；不改 TCB/冻结文件；不 push。

## 2. Task Graph（§17）— `runtime/task_graph.py`

### 2.1 数据模型
- `TaskNode`：`task_id` / `description` / `depends_on[]` / `parallel_with[]`（自动对称化）/ `owner` / `state`（PENDING/READY/RUNNING/DONE/BLOCKED）/ `est_cost` / `subtasks[]`
- `TaskGraph`：节点集 + DAG 校验 + 拓扑排序 + 关键路径 + JSON 输出

### 2.2 关键算法
- **DAG 校验（环检测）**：Kahn 拓扑；无法消去的节点集合即环成员（按 id 排序，确定性输出）；重复 id / 悬空依赖 / parallel 不对称均报错。
- **拓扑排序**：Kahn 稳定序（每层按 id 排序）。
- **关键路径**：est_cost 加权最长路径（拓扑序 DP，`dist[n]=est_cost(n)+max(dist[dep])`）；并列取 id 字典序较小者。
- **动态加任务**：`add_subtask(parent_id, ...)` → 新节点自动依赖 parent，parent.subtasks 挂载（§17 动态加任务）。

### 2.3 规则式 Goal 拆解（`build_from_goal`）
机械、确定性、零 AI：
1. 按 `。；；\n` 拆句；
2. 每句生成一个任务（找不到动词也成任务）；
3. 验证类句子依赖前一个非验证任务；
4. 含「并行/同时/互不依赖/独立进行」提示词 → 与前任务 `parallel_with`（双向）且不依赖它；
5. 其余默认串行依赖前一个任务；
6. `owner:xxx` / `负责人:xxx` 从句尾提取 Owner。

### 2.4 输出对齐
JSON 结构对齐 `runtime/brain_bridge.py`：`schema` / `valid` / `goal` / `nodes` / `dependencies` /
`topological_order` / `critical_path` / `parallel_groups` / `human_view`（§18 派生投影）/ `non_authority` / `trace`。

### 2.5 CLI
```
python runtime/task_graph.py build --goal-file <F> [--out tg.json]   # 拆解任务
python runtime/task_graph.py add --parent T01 --task-id T01a --desc 子任务 --state tg.json   # 动态加任务
python runtime/task_graph.py status --state tg.json                   # 状态
python runtime/task_graph.py brain-pick --goal <F|文本>               # Brain 选型
```

## 3. 自举 L1（§68）— `runtime/self_heal.py`

### 3.1 缺陷→任务自动转换器（`convert`）
输入：doctor `DRIFT: ... | expected=... | actual=...` 输出 / 测试 `FAILED` 日志 / 报错文本。
解析优先级：**DRIFT 行 > FAILED 测试 > 异常行**；提取 `source_kind` / `defect_summary` / `affected_file` / `expected` / `actual` / `evidence`。
自动生成 goal 文件（含「要什么成果 + 怎么算做完 + 约束 + 缺陷摘要 + 证据节选」）+ 结构化结果 + 证据 JSONL（含 §70 trace）。

### 3.2 自愈管线（`run`）
`convert` →（可选）`--auto-fix` 应用注册 fixlet（最小修复，前置条件+幂等校验+py_compile 校验）→ `--verify` 验证命令 → 证据记录。
Fixlet 注册表：`FIXLETS`，当前内置 `SH-001`（见 §4）。

### 3.3 CLI
```
python runtime/self_heal.py convert --source <失败日志> [--goal-out F] [--evidence D]
python runtime/self_heal.py run --source <日志> --auto-fix --target <文件> --fixlet SH-001 --verify "<命令>" [--evidence D]
python runtime/self_heal.py list
```

## 4. 自举 L1 真实案例（全链证据）

### 4.1 缺陷（实测确认，报告 §8 D5）
`runtime/test_v09_attack_matrix_offline.py` 当前环境 FAILED：
```
aicontrol.store.GateDenied: pre-existing scoped authorization required; Controller self-grant is forbidden
```
根因：该文件是 T0 既有实验文件（非审计权威矩阵；权威矩阵是
`test_v09_attack_matrix_on_b1_core.py`，36/36）。其 `Fixture.authorization()` 调
`Controller.scoped_authorization()`——b1 核心语义**禁止 Controller 自授**（只返回既有授权），
故实验文件缺失「预置授权」路径，首个 Fixture 即抛 GateDenied。修复只落在该实验文件，
不影响权威矩阵（`test_v09_attack_matrix_on_b1_core.py` 零改动、零影响）。

### 4.2 转换器实测（证据）
用真实失败日志运行转换器：
```
python runtime/self_heal.py convert --source tmpm8v1c53r/v09_failed_log_before_fix.txt \
  --goal-out docs/evidence/d5/L1_goal_from_real_failure.goal.txt --evidence docs/evidence/d5
```
输出摘要：`source_kind=ERROR_TEXT`，
`summary="GateDenied: pre-existing scoped authorization required; Controller self-grant is forbidden"`，
goal 文件含「要什么成果 + 怎么算做完 + 约束」。
证据：`docs/evidence/d5/L1_goal_from_real_failure.goal.txt`、
`docs/evidence/d5/L1_pipeline_goal.goal.txt`、`docs/evidence/d5/self_heal_events.jsonl`。

### 4.3 最小修复（fixlet SH-001，5 处替换，diff 见证据）
修复语义与权威 runner `test_v09_attack_matrix_on_b1_core.py` 记载的
AD-1/AD-2/AD-3/AD-4/AD-5/AD-7 完全一致（测量侧适配，非产品代码改动）：
1. **AD-1/AD-3 授权路径**：`scoped_authorization`（自授被禁）→ 外部权威路径
   `store.issue_decision_nonce` → `store.grant_authorization`（Human Gate Trust Root 受控入口），resource 绑定 `resource-a`；
2. **AD-2 intent 显式字段**：补 `effect_type="AI_MESSAGE"` / `data_classification="PUBLIC"`（b1 `execute_effect` 要求）；
3. **AD-7 R34 签发侧 FAIL_CLOSED**：R34 授权构造套 try，未知 effect_type 在签发侧关闭即记 FAIL_CLOSED（含 side 归因）；
4. **AD-5 R18 裁决期望**：R18 期望修订为 `ALLOW_DISTINCT_EFFECT`（同 slot 不同 payload = 两个独立逻辑效果，identity proof 入 detail）；
5. **AD-4 R21 重启语义**：R21 用同一 state root 上的新 Controller 实例模拟重启，重放前经外部权威路径重新授权。

证据：
- `docs/evidence/d5/SH001_fix.diff`（修复 diff，140 行）
- `docs/evidence/d5/test_v09_attack_matrix_offline_PRE_FIX.py`（修复前快照）

### 4.4 前后测试结果
| 文件 | 修复前 | 修复后 |
|---|---|---|
| `runtime/test_v09_attack_matrix_offline.py` | **FAILED**（GateDenied 崩溃） | **36/36 绿（matched_count=36, red=0）** |
| `runtime/test_v09_attack_matrix_on_b1_core.py`（权威矩阵） | 36/36 | **36/36 保持（零影响）** |

```
# 修复后验证（证据命令）
python runtime/test_v09_attack_matrix_offline.py --summary-only   # {"matched_count": 36, "red_baseline_count": 0}
python runtime/test_v09_attack_matrix_on_b1_core.py               # "case_count": 36, "matched": 36, "red": 0
```

### 4.5 自愈管线端到端演示
`self_heal.py run --source <失败日志> --auto-fix --target <沙箱副本> --fixlet SH-001 --verify py_compile`：
`steps=[convert ok, apply_fixlet:SH-001 ok (replacements=5, py_compile=ok), verify ok]`，`valid=true`，证据 JSONL 落盘。

## 5. Context Sufficiency（§55）— `runtime/context_sufficiency.py`

### 5.1 五分支自动路由
输入：任务上下文 `key -> {value, source, trust, sensitive}`、所需信息清单、registry（只读）、策略（阈值）。
`completeness = OK/总数`；`ratio >= completeness_threshold` 且无缺失/敏感 → `SUFFICIENT`，否则依次尝试：

| 分支 | 触发条件 | 动作 |
|---|---|---|
| ① `SWITCH_LOCAL_BRAIN` | 官方 API_MODEL Brain ≥ `min_fallback_brains`(2) 且有缺失项 | 选 fallback 链（registry brains 节）补齐缺失 key |
| ② `SWITCH_ALLOWED_PROVIDER` | 官方 Provider ≥ `min_alternate_providers`(2) 且有缺失项 | 选允许 Provider 切换 |
| ③ `DESENSITIZE_RETRY` | 存在敏感字段（手机/邮箱/身份证/Bearer/口令 key） | 脱敏打码（`mask_value`：`138****5678`、`u****@domain`、`******`）后重试 |
| ④ `HUMAN_AUTHORIZATION` | 策略 `allow_human_authorization=True` 且有未决项 | 输出授权请求（request_id + requested_keys + Human Gate 说明） |
| ⑤ `BLOCKED` | 以上均不可用/不允许 | 明确阻塞 + 原因（fail-closed） |

信任阈值：`trust < trust_threshold(0.5)` 视为不可用（LOW_TRUST → MISSING）。
输出：`decision` + `reason` + `completeness` + `branches_tried`（含每分支 skipped 原因=中间状态）+ `routing_action` + `authorization_request`/`blocked_reason` + `trace`。

### 5.2 §55 五分支测试（每分支 ≥1 次 + 默认策略）
`runtime/test_context_sufficiency_d5_offline.py` 覆盖：
①`test_t01_switch_local_brain` ②`test_t02_switch_allowed_provider` ③`test_t03_desensitize_retry`
④`test_t04_human_authorization` ⑤`test_t05_blocked_when_human_disallowed` ⑥`test_t06_sufficient_default_policy`
+ 策略文件覆盖/脱敏/敏感检测/CLI（`test_t07..t14`）。**全绿（Python312）**。

### 5.3 CLI
```
python runtime/context_sufficiency.py route --context ctx.json --required a,b [--registry ...] [--policy ...]
```

## 6. 升级梯（§60）映射与 L0-L2 落实

| 级别 | 含义 | 本刀落实 |
|---|---|---|
| L0 机器 | 规则/脚本/纯机械 | ✅ Task Graph 规则拆解、环检测/关键路径、转换器规则解析、五分支规则路由、fixlet 机械替换 |
| L1 自举 | 系统修复自身缺陷 | ✅ 缺陷→goal 转换器 + 自愈管线 + L1 真实案例（§4 全链证据） |
| L2 弱 AI | 本地弱模型辅助（规则锚定） | ✅ `task_graph.py brain-pick` 规则式选 Brain（low→弱模型、mid→中、high→主脑，读 registry costs 节），输出含 §70 trace |
| L3 真实 AI | 真实模型调用（需凭据/授权） | ⛔ 不做（纪律：真实 AI 调用不做） |
| L4-L9 | 更强模型 / 多模型 / 审计 / 终裁等 | ⛔ 留档（业主 L3 之后） |

## 7. Trace 字段补强（§70）

所有 D5 输出携带：
```json
"trace": {"model": ..., "ai": "rule-based-...", "tool": "task_graph.py/self_heal.py/context_sufficiency.py <cmd>",
          "reason_retry": null, "cost": <registry cost_per_call 若有>}
```
`model` 取 Brain 选型结果（如 `brain-chatgpt-web`），`cost` 从 `capability-registry.json costs` 节只读取（无则 null）。

## 8. 测试与验证（机器验证，Python312）

```
# 1) D5 单测全绿（40 tests OK）
python -m unittest runtime/test_task_graph_d5_offline.py runtime/test_self_heal_d5_offline.py runtime/test_context_sufficiency_d5_offline.py

# 2) 转换器实测 1 次（真实失败日志 -> goal 文件）
python runtime/self_heal.py convert --source tmpm8v1c53r/v09_failed_log_before_fix.txt --goal-out docs/evidence/d5/L1_goal_from_real_failure.goal.txt

# 3) 自举 L1 全链：修复后离线矩阵绿 + 权威矩阵 36/36
python runtime/test_v09_attack_matrix_offline.py --summary-only   # matched_count=36
python runtime/test_v09_attack_matrix_on_b1_core.py               # matched=36

# 4) §55 五分支测试绿（见 §5.2）
# 5) 与既有测试合跑不破坏：runtime/ discover 共 540 tests，errors=8
#    （全部为既有基线：test_harness_verify_offline env patch tearDown 在 Windows
#    上失败（env var >32767）→ 污染其后 test_v08_adapter_evidence_offline 5 例；
#    D5 新增 40 测试零 ERROR/FAIL；D5 CLI 测试对污染做了防御性 clean_env）
# 6) py_compile + import 自检（本模块全部通过）
```

## 9. 遗留 / 边界

- **R18 期望修订**：离线实验文件按权威 runner 已记载的裁决（AD-5）修订期望为 `ALLOW_DISTINCT_EFFECT`，非产品代码改动；
- **R21 重启语义**：测量侧用新 Controller 实例模拟（AD-4），权威矩阵文件本身零改动；
- **自动修复范围**：fixlet 仅覆盖已注册的简单缺陷（当前 SH-001）；更复杂缺陷需 L3 真实 AI + Human 审阅；
- **Context Sufficiency 的"换 Brain/Provider"**：本刀输出路由决策+动作建议，不真实调用外部服务（L3）；真实切换由调用方按 `routing_action` 执行；
- **§8 C 纠偏 / §11 EC**：本刀未新建（D5 范围外，机制已在）；`reason_retry` 字段为后续 EC 触发案例预留。
