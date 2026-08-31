# Autopilot — A1 自动调度闭环接线 (执衡 v1.1-blackbox)

无人值守中继流转接线脚本。把 goal 文件转换为 BUILDER_READY 事件投入
inbox，然后由一个事件触发的状态机驱动全链：认领建 RUN → 执行(work) →
report → R 审查(PASS/REWORK) → 收尾。全程无需人工敲命令。

- 脚本：`scripts/relay_autopilot.py`（Python 3，单文件）
- 账本：`E:\WB\state\ai-production-control\construction-relay\autopilot-actions.ndjson`
  （与 `guard-actions.ndjson` 同格式：`timestamp/action/detail/ok`，追加）
- 沙箱：`E:\WB\state\ai-production-control\construction-relay\autopilot\`
  （inbox / runs / queue.json，只动 autopilot 目录，绝不触碰真实中继状态）

## 调用方式

```
python scripts/relay_autopilot.py submit --goal-file <goal.json> [--mode mock|relay] [--candidate-commit <40hex>]
python scripts/relay_autopilot.py drive  [--watch|--once] [--mock-review PASS|REWORK] [--max-reworks N]
python scripts/relay_autopilot.py status
python scripts/relay_autopilot.py validate-event --event-file <file.json>
python scripts/relay_autopilot.py reset-sandbox
```

goal 文件为 JSON，至少含 `objective` 或 `title`，可选
`goal_id / title / scope / acceptance / milestone / priority`：

```json
{
  "goal_id": "AUTO-001",
  "title": "示例 goal",
  "objective": "……",
  "scope": ["……"],
  "acceptance": ["……"],
  "milestone": "V0.7",
  "priority": 1
}
```

### 模式说明

- `--mode mock`（默认）：事件写入 **autopilot 沙箱 inbox**
  （`construction-relay/autopilot/inbox/`），运行中的真实 watcher 不可见，
  由本脚本 `drive` 状态机驱动（L2 测试/演练路径）。
- `--mode relay`：事件写入 **真实 inbox**
  （`construction-relay/inbox/`），运行中的 watcher（R1 守护拉起）会认领并走
  真实 R 审查（生产/L3 路径）。⚠ 使用前必须确认 R-PROD 通道可用
  （`chatgpt_bridge status` 实测；R-PROD last_verified=2026-08-19 已过期）。
  事件格式与 review-relay.js 的 `validateEvent` 完全一致（可用
  `validate-event` 复核）。

### drive 说明

- `--watch`（默认）：轮询直至队列收敛（inbox 空且无进行中 run），事件触发式
  自动推进，无人敲命令。
- `--once`：只推进一轮（用于逐步观察中间态）。
- `--mock-review PASS|REWORK`：L2 mock 审查判定（默认 PASS）。
- `--max-reworks N`：单 run 最大 rework 次数（默认 8，与 relay config 一致），
  超限 ABORTED。
- drive 自带单实例锁（autopilot/lock，mkdir+token），并发调用第二个实例
  SKIP_LOCKED。

## 状态机设计

run 级状态与流转：

```
inbox 事件 --claim--> CLAIMED --work--> WORKING --work done--> REPORTED
  --R 门--> WAITING_REVIEW --review--> REVIEWING
      --PASS--> WRAPPED（写 wrap-summary，收尾）
      --REWORK--> WORKING（rework_count+1，重排队；超 max-reworks -> ABORTED）
```

核心规则：

1. **R 并发度 = 1**：同时仅 1 个 run 处于 `WAITING_REVIEW/REVIEWING`（R 门，
   防 R-PROD 限流/睡死）。
2. **WAITING_REVIEW 不阻塞队列**（§16/§11 精神）：任务 A 在 R 门等待/审查时，
   其余 run 仍可 `CLAIMED -> WORKING -> REPORTED` 并行推进。
3. **公平重排队**：REWORK 后回到 WORKING 再 REPORTED，重新排队；门控准入
   按 `(rework_count, created_at)` 排序——rework 少的任务优先，防止单个任务
   反复 REWORK 饿死队列。
4. **事件触发**：所有推进由文件出现/状态变化驱动（inbox 新事件、run 目录
   产物、queue.json 状态），`drive --watch` 自动收敛。

## 与真实中继的关系（复用机制）

- 事件格式与 review-relay.js `validateEvent` 一致（builder 身份取自真实
  `bindings/builder.json`；路径受 config allowed roots 约束），由
  `validate-event` 用 Trae-Ralph 真实 protocol 复核。
- 生产执行（真实弱模型 work/report、真实 R 审查）由真实 watcher + builder +
  R-PROD 完成；本脚本的 `mock_work`/`mock_review` 是 L2 沙箱接缝，不消耗
  真实 R 额度、不触发真实弱模型。
- 本脚本不改 Trae-Ralph 代码、不改 runtime/、不改 config、不重启 watcher
  （watcher 由 R1 守护负责）。

## 文件域与纪律

- 写入：`scripts/relay_autopilot.py`（本脚本）、`docs/ops/autopilot-README.md`、
  `construction-relay/autopilot/**`（沙箱）、
  `construction-relay/autopilot-actions.ndjson`（账本）、
  `--mode relay` 时 `construction-relay/inbox/`（显式）。
- 只读：`construction-relay/` 其余内容、`E:\WB\tools\Trae-Ralph\src\relay\*`、
  `E:\WB\tools\ai-production-control\runtime\*`。
- 禁止：改 runtime/、src/、config/、PROJECT_STATE.*、DECISION_LEDGER.md；
  凭据只读不外传。

## L2 验证摘要（2026-08-30，账本 autopilot-actions.ndjson）

1. **全链 1 次**（goal-A）：submit → validate_event(真实 protocol PASS) →
   claim → work_start → work_done → review_enter(WAITING_REVIEW) →
   review_start → review_pass → WRAPPED；`drive --watch` 3 轮收敛。
2. **排队/不阻塞/REWORK**（goal-B、goal-C）：
   - B 先认领先入 R 门；B 在 REVIEWING 时 C 已推进到 REPORTED（不阻塞）；
   - B REWORK → 重排队；C（rework 0）公平优先于 B（rework 1）再入 R 门；
   - C REWORK → 重排队；最终 PASS 模式收敛，双 run WRAPPED（各 rework=1）；
   - 全程同时最多 1 个 REVIEWING/WAITING_REVIEW（R 并发度 1）。

## mock_work / mock_review 边界与替换计划（B1）

- `mock_work`（`relay_autopilot.py` `mock_work()`）：沙箱接缝，只生成合成
  `evidence.json`/`report.json`，**不触发真实弱模型、不消耗额度**。L2 用它
  验证状态机关联行为（claim -> work -> report 产物链）。
- `mock_review`（`mock_review()`）：产出与真实 `validateReviewResult` 形状一致
  的 `review-result.json`，判定由 `--mock-review PASS|REWORK` 驱动。L2 用它
  验证 R 门控、REWORK 重排队、ABORTED 分支，**不消耗 R 审查额度**。
- 替换计划（L3）：生产链关闭两个 mock——真实 watcher（R1 守护拉起）从真实
  inbox 认领事件后由 builder 执行真实 work/report；真实 R 审查由 R-PROD 通道
  （`--mode relay` + 可用 `chatgpt_bridge`）完成。本脚本的 mock 与 relay 两条
  路径共享同一状态机，替换只换 work/review 实现，不换流转逻辑。
- 沙箱越界：`claim_inbox` 校验 `run_id` 必须匹配 `ID_RE`
  （`^[A-Za-z0-9][A-Za-z0-9._-]{2,119}$`），含 `../`、`\` 等路径逃逸字符的
  `run_id` 直接拒绝（`claim_skip` 记账），避免在 `RUNS_DIR` 之外建目录。
  测试：`runtime/test_relay_autopilot_offline.py`（13 用例，覆盖单实例锁三态 /
  状态机全迁移 / R 并发度 1 / 沙箱越界拦截）。

## 调度准入三闸门（接线 §59/§55/§34，2026-08-31）

`submit` 与 `drive` 已接入三闸门（`admission_checks()`，见 relay_autopilot.py 顶部）：

1. **§59 成本路由闸**：submit 前调 `cost_router.do_route`——SAFE_HALT（预算熔断）拒绝提交；
   UNDETERMINED（全部待校准）不误拦；ALLOWED 放行并把 recommended_route / expected_total_cost
   记入账本。
2. **§55 Context Sufficiency 闸**：submit 前调 `context_sufficiency.route`——决策记录到准入结果；
   BLOCKED / HUMAN_AUTHORIZATION（需人授权，无人值守下不得自动入队）拒绝自动提交；
   SWITCH_* / SUFFICIENT 放行。
3. **§34 Controller lease 闸**：`drive` 执行前检查 `controller_lease`（state/controller_lease.json，
   generation+holder+ttl）——无 lease 自动 acquire（gen=1）；generation 不匹配 / holder 为他人 /
   已过期 → 老权失效（§34），drive 退码 2 拒执行。新增独立模块 `runtime/controller_lease.py`
   实现 Lease/Generation/Fencing Token（宪法 :1226-1242 的 Controller 级 fencing，D4 的互斥锁
   与任务级 epoch 不覆盖此场景）。

测试：`runtime/test_relay_autopilot_wiring_offline.py`（8 用例）+ `runtime/test_controller_lease_offline.py`（7 用例）。

## 已知边界

- `--mode relay` 提交的真实 inbox 事件由真实 watcher 认领后走真实 R 审查；
  当前 Chrome/CDP 9223 未监听时，web-bridge review 会 ECONNREFUSED（事件进入
  EXTERNAL_BLOCKED 而非消耗 R 额度），属既有环境状态，不是本脚本问题。
- mock 事件携带 `_goal` 扩展字段，真实 `validateEvent` 会忽略（normalized
  仅取标准字段），不影响格式一致性。
