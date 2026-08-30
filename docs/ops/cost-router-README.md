# D2 成本路由 + 安全熔断 — 操作说明（v1.1-blackbox）

> 执衡 v1.1-blackbox 开发线 · D2 任务 · 机器可完成部分
> 交付：`runtime/cost_router.py`（成本路由 + SAFE_HALT 熔断核心）、
> `config/cost_policy.json`（成本策略）、`runtime/test_cost_router_d2_offline.py`（单测）、
> `config/capability-registry.json` costs 节校准（D2 变更）、本说明。

> **⚠️ 解释器要求（与 D1 一致）**：运行与测试**必须用 Python312（生产 APC_PY）**：
> `C:\Users\17838\AppData\Local\Programs\Python\Python312\python.exe`。
> 本模块为纯标准库（无第三方依赖），不 import litellm；用默认 `python` 也能跑，
> 但为与其他模块一致仍建议 Python312。

## 1. 定位

宪法 §2 成本感知 / §59 成本路由 / §61 Hard Fuse（安全熔断 SAFE_HALT）的机器可完成部分：

| 宪法条款 | 缺口（已实测确认） | D2 交付 |
|---|---|---|
| §59 成本路由 | 无成本感知路由 | Expected Total Cost 路由 v1（`route`） |
| §2 成本感知 | 无 Expected Total Cost 核算 | ETC = Σ(各阶段 AI 调用成本 × 概率权重) |
| §61 Hard Fuse | SAFE_HALT 从未真实触发 | 熔断状态机 + **真实触发 1 次（BUDGET_BREACH）** |
| §19 NO_PROGRESS | 计数器未真实触发 | `simulate-rework` 连续 REWORK -> 熔断（NO_PROGRESS） |

**红线（本模块遵守）**：
- 输出为 inert 数据（`non_authority`）；任何 authority 词只作数据呈现，绝不代执行；
- 不发起任何真实 AI 调用（L2 用纯计算 / mock；真实额度消耗 = 留业主 L3）；
- 不改 `src/aicontrol/`、`config/production.json`、`runtime/runtime.py`、
  `runtime/adapters/` 既有文件（只读衔接 D1 r_adapter / worker_adapter）；
- 凭据不入仓；状态文件默认 `state/cost_router_state.json`（运行时工件）。

## 2. 数据来源

- **`config/cost_policy.json`（新）**：模型单价表（`unit_prices`）、路由选项（`route_options`）、
  REWORK 概率表、预算阈值、熔断参数、goal 分类关键字。
- **`config/capability-registry.json` costs 节（D2 校准）**：8 条 cost 全部补估算值
  （`source=估算/待实测`），引用 cost_policy.json 模型单价；其余节未动（registry-validate PASS）。
- **`config/production.json`（只读）**：`policy.max_review_cycles=3` 已镜像进 cost_policy.json。

模型 id 与 D1 Adapter 对齐（只读衔接）：
- 弱 Worker：`worker-workbuddy-cli`（worker_adapter id）
- 强 Worker：`worker-codex-cli`（worker_adapter id）
- 强 R：`r-prod-chatgpt-web`（r_adapter provider id）
- 弱 R：`r-deepseek-v4-flash`（r_adapter provider id）

## 3. 路由算法（Expected Total Cost v1）

```
ETC = Σ(各阶段 AI 调用成本 × 概率权重)

管道（hybrid/strong）：弱(强) Worker 执行 + 强 R 审查 + 可能的 REWORK 循环
  E[调用次数] = Σ_{i=0}^{max_review_cycles-1} p^i        （p = 单轮 REWORK 概率）
  worker_calls == review_calls（每次 REWORK 触发一次重新执行 + 一次重新审查）
  ETC = worker_unit × E[calls] × tokens_scale + r_unit × E[calls] × tokens_scale
  tokens_scale = tokens_est / reference_tokens（默认 2000，--tokens-est 可调）

路由选项：
  weak   = 弱 Worker 直接交付（无强审查，最低成本档）      —— 低价值/低风险
  hybrid = 弱 Worker 执行 + 强 R 审查（宪法默认管道）      —— 中价值
  strong = 强 Worker 执行 + 强 R 审查（最高成本档）        —— 高价值/高风险

推荐路由 v1（机械，按任务价值 + REWORK 风险）：
  goal_type=high                 -> strong
  goal_type=mid                  -> hybrid
  goal_type=low 且 rework 低/中   -> weak
  goal_type=low 且 rework=high    -> hybrid（重做风险高，仍需强审查兜底）
```

goal 类型由关键字分类（cost_policy.json `goal_type_keywords`）：命中 high 关键字 -> high；
否则 mid；否则 low；全不命中 -> mid（保守中间档，不猜高也不猜低）。

## 4. SAFE_HALT 熔断状态机（宪法 §61 Hard Fuse）

触发条件（cost_policy.json `circuit_breaker` 可配置）：

| 条件 | 触发方式 | reason |
|---|---|---|
| ① 期望成本超预算阈值 | `route` ETC > budget_threshold（--max-cost 或默认 0.5） | `BUDGET_BREACH` |
| ② NO_PROGRESS 计数器超限 | `simulate-rework` 连续 REWORK 无进展 >= no_progress_limit(3) | `NO_PROGRESS` |
| ③ 连续熔断标记超限 | `budget` 连续 BLOCKED >= consecutive_breach_limit(2) | `CONSECUTIVE_BREACH` |
| 受控触发（L2 实测通道） | `safe-halt --goal ... --reason-detail ...` | `MANUAL` |

触发后：
- 输出 **SAFE_HALT 记录**（结构化 JSON：`schema / record_id / triggered_at / reason /
  reason_detail / context / freeze / recovery`）；
- **冻结该任务**（goal_hash 记入 `frozen_tasks`）：同一任务再次 route/budget ->
  `FROZEN`（不自动重试）；
- 人工审查后 `reset` 解冻（可 `--goal` 指定只解冻该任务）；history 记录保留（证据留存）。

## 5. 命令

```bat
C:\Users\17838\AppData\Local\Programs\Python\Python312\python.exe runtime/cost_router.py route --goal "<简述或类型>" [--rework-risk low|mid|high] [--tokens-est N] [--max-cost N]
C:\Users\17838\AppData\Local\Programs\Python\Python312\python.exe runtime/cost_router.py budget --goal "<简述>" --max-cost N [--rework-risk ...] [--tokens-est N]
C:\Users\17838\AppData\Local\Programs\Python\Python312\python.exe runtime/cost_router.py simulate-rework --goal "<简述>" --cycles N [--no-progress-limit N]
C:\Users\17838\AppData\Local\Programs\Python\Python312\python.exe runtime/cost_router.py safe-halt --goal "<简述>" --reason-detail "<说明>"
C:\Users\17838\AppData\Local\Programs\Python\Python312\python.exe runtime/cost_router.py status
C:\Users\17838\AppData\Local\Programs\Python\Python312\python.exe runtime/cost_router.py reset [--goal "<简述>"]
```

退出码：`0`=成功；`1`=配置/输入错误；`2`=硬停（SAFE_HALT / BLOCKED / FROZEN）。

`route` 输出：成本分解表（阶段/模型/单价/期望次数/期望成本）+ 推荐路由 + 三档 ETC 对比
（`options`）+ 可解释说明（`explanations`）。单价缺失的模型（如 provider-catpaw、
provider-trae-solo-cn，unit_price=null）输出"待校准"并跳过其成本计算；全部待校准 ->
`UNDETERMINED`（跳过预算熔断检查，不误伤）。

`budget` 输出：ETC 超阈值 -> `BLOCKED`（`suggest_safe_halt=true`）；连续 BLOCKED 达上限 ->
升级为 `SAFE_HALT`（CONSECUTIVE_BREACH）。

## 6. registry costs 节校准（D2 变更，只动 costs 节 + 相关 note）

| cost id | capability_id | cost_per_call | source |
|---|---|---|---|
| cost-chatgpt-web | brain-chatgpt-web | 0.30 | 估算 |
| cost-workbuddy-deepseek-v4-flash | brain-workbuddy-deepseek-v4-flash | 0.05 | 估算 |
| cost-codex-local | brain-codex-local | 0.20 | 估算 |
| cost-catpaw | provider-catpaw | 0.10（占位） | 待实测 |
| cost-trae-solo-cn | provider-trae-solo-cn | 0.10（占位） | 待实测 |
| cost-worker-workbuddy-cli | worker-workbuddy-cli | 0.05 | 估算 |
| cost-worker-codex-cli | worker-codex-cli | 0.20 | 估算 |
| cost-r-chatgpt-web | r-prod-chatgpt-web | 0.30 | 估算 |

单位：元/次调用（估算）。catpaw/trae 在 cost_policy.json 中 unit_price=null
（路由输出"待校准"并跳过成本计算），registry 中保留占位 0.1 仅作数据面完整性。
真实价目 = L3 业主实测后回填。

## 7. 机器验证记录（D2 已执行，Python312）

| 项 | 命令 | 结果 |
|---|---|---|
| D2 单测 | `python -m unittest discover -s runtime -p "test_cost_router_d2_offline.py"` | ✅ 56/56 |
| 语法/导入 | `py_compile` + `import cost_router` | ✅ |
| registry 复验 | `python docs/ops/registry-validate.py` | ✅ PASS |
| L2 route 低风险 | `route --goal "机械读取配置文件并格式化输出" --rework-risk low` | ✅ weak 推荐 + 成本分解 0.05，exit 0 |
| L2 route 高风险（**SAFE_HALT 真实触发 1 次**） | `route --goal "high-risk production 安全发布任务（需强审查）" --rework-risk high` | ✅ SAFE_HALT（BUDGET_BREACH，record SAFE_HALT-20260830-001，ETC 0.98 > 0.5），exit 2 |
| L2 冻结验证 | 同一任务再次 route | ✅ FROZEN（不自动重试） |
| L2 budget 超限 | `budget --goal "high-risk 金融交易外部接入" --max-cost 0.3 --rework-risk high` | ✅ BLOCKED（SAFE_HALT 建议）；第 2 次 -> SAFE_HALT（CONSECUTIVE_BREACH） |
| L2 NO_PROGRESS | `simulate-rework --goal "重构任务连续失败" --cycles 3` | ✅ SAFE_HALT（NO_PROGRESS，3/3） |
| L2 reset | `reset` | ✅ 解冻全部，history 保留 3 条记录 |
| 既有测试合跑 | `python -m unittest discover -s runtime -p "test_*.py"` | ✅ 446 测试；9 个 error 为**基线既有**（Windows env 变量超长 32767，与 D2 无关；基线 390 测试同样 9 error，D2 净增 56 测试全绿） |

**SAFE_HALT 触发证据**：`state/cost_router_state.json`（运行时工件）history 保留 3 条真实记录：
1. `SAFE_HALT-20260830-001` BUDGET_BREACH（route 高风险触发）
2. `SAFE_HALT-20260830-002` CONSECUTIVE_BREACH（budget 连续 BLOCKED 升级）
3. `SAFE_HALT-20260830-003` NO_PROGRESS（simulate-rework 触发）

## 8. 遗留（真实接入 = L3 业主）

1. **单价校准**：cost_policy.json 估算值（估算/待实测）需按真实价目回填（L3）；
   之后 `budget.default_budget_threshold` 按真实预算调整。
2. **与 Controller 接线**：`route` 的推荐路由 / `budget` 的 BLOCKED / SAFE_HALT 记录
   接入调度层（autopilot / Controller）作为前置门；当前为独立 CLI 模块。
3. **多 R 热切换衔接**：成本表 model id 已对齐 D1 r_adapter provider 结构；
   真实审查走 `r_adapter.py review --mode real`（需 key，L3）。
4. **NO_PROGRESS 真实计数器**：当前 `simulate-rework` 为 L2 mock；
   生产侧 REWORK 循环接入 §19 计数器后，连续 REWORK 无进展即真实触发熔断。
