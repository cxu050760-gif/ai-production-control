# D4 多 Worker 并行调度 + 资源锁 + 项目隔离 + 失效权 — 设计说明（v1.1-blackbox）

> 执衡 v1.1-blackbox 开发线 · D4 任务 · 机器可完成部分
> 交付：`runtime/parallel_scheduler.py`（并行调度核心）、
> `runtime/test_parallel_scheduler_d4_offline.py`（测试套件，测试内模拟并行）、
> 本说明。
>
> **⚠️ 解释器要求（与 D1/D2/D3 一致）**：运行与测试**必须用 Python312（生产 APC_PY）**：
> `C:\Users\17838\AppData\Local\Programs\Python\Python312\python.exe`。
> 本模块为纯标准库（无第三方依赖）。

## 1. 定位

宪法条款的机器可完成部分（**真实多 Worker 生产并行 = 业主 L3**；本模块测试内
模拟并行 + CLI 通道真实线程/子进程，零真实 AI 调用）：

| 宪法条款 | 缺口（已实测确认） | D4 交付 |
|---|---|---|
| §56 多 Worker | skill 在但真实并行 0 次 | 任务队列 -> 并发分派（`max_concurrent` 可配，默认 2） |
| §57 Resource Lock | 锁在但多 Worker 冲突未实测 | 每资源互斥锁（mkdir 原子 + token/age stale 接管）；冲突排队 `LOCK_WAITING` 不失败 |
| §58 Project Isolation | 项目隔离无实现（❌） | 每任务独立工作目录 + 越界写校验（sandbox 边界 + symlink 逃逸扫描） |
| §16 WAIT 局部性 | 等待时跑其他任务未验证 | 等待锁 / WAIT directive 的任务不阻塞其余 READY 任务 |
| §23/§41 失效权 | STOP→旧权失效端到端未测 | STOP/REVOKE directive -> 执行单元失效 -> 后续结果拒绝接受（端到端测试） |
| §40 Revocation 单调性 | epoch 在但回滚复活专项测试未确认 | 每任务递增 epoch；回滚/复活低 epoch 结果拒绝（`STALE_EPOCH`/`REVOKED_EPOCH`） |
| §30 Stale Safety | 通用 stale 检测部分 | 心跳超时 -> `STALE` -> 回收并释放资源锁 |
| §38 OUTCOME_UNKNOWN | 机制+单测，真实对账场景未发生 | 子进程被杀/超时无明确结果 -> `OUTCOME_UNKNOWN` + 人工/重试决策入口，不猜测 |

**红线（本模块遵守）**：
- 输出为 inert 数据（`non_authority`）；任何 authority 词只作数据呈现，绝不代执行；
- 不发起任何真实 AI 调用（mock 零消耗；cli 模式仅用于本地无害命令 / worker_adapter mock 通道）；
- 不改 `src/aicontrol/`、`config/production.json`、`runtime/runtime.py`、
  `config/capability-registry.json`、`runtime/adapters/` 既有文件（只读衔接 D1 worker_adapter）；
- 凭据不入仓；worker 只登记路径/命令，不携带 token；
- 状态文件默认 `state/parallel-scheduler/`（运行时工件；测试用 tmp 目录）。

## 2. 设计概述

### 2.1 模块结构

```
runtime/parallel_scheduler.py
├── 基础工具：utcnow / 原子 JSON / ensure_id / _path_within（sandbox 原语）
├── SingleInstanceLock   调度器单实例锁（mkdir 原子 + token/age stale 接管）
├── ResourceLockManager  每资源互斥锁（进程内快表 + 磁盘 mkdir 原子锁）
├── MockWorkerExecutor   内置假 Worker（sleep+心跳+预设结果，零 AI 调用）
├── CliWorkerExecutor    CLI 型 Worker（子进程；worker_adapter 协议概念；
│                        超时/被杀 -> OUTCOME_UNKNOWN）
└── ParallelScheduler    调度核心（队列/分派/锁/隔离/epoch/失效权/stale）
```

### 2.2 调度状态机（任务级）

```
PENDING -> READY -> RUNNING -> COMPLETED        （结果被接受）
                        |-> FAILED              （明确失败）
                        |-> OUTCOME_UNKNOWN     （§38：结果不明，人工/重试入口）
                        |-> LOCK_WAITING -> RUNNING（§57：锁冲突排队，不失败）
                        |-> WAITING -> READY    （§16：等待审查/人工，不阻塞队列）
                        |-> REVOKED             （§23/§41：STOP/REVOKE 失效旧权）
                        |-> STALE               （§30：心跳超时回收）
                        |-> SANDBOX_VIOLATION   （§58：越界写）
```

### 2.3 并发分派（§56）

- 任务队列按提交顺序分派；同时 `RUNNING` 数量 <= `max_concurrent`（默认 2，`--max-concurrent N` 可配）。
- 执行器两型：
  - **mock**（默认）：线程池内 sleep+返回预设结果，**测试内模拟并行**；
  - **cli**：子进程调用 Worker CLI（复用 `worker_adapter` 协议概念：goal 文件写入
    隔离 work_dir、stdout 收 JSON、stderr 收日志、退出码 0/1/2）。

### 2.4 Resource Lock（§57）

- 每资源一个锁目录 `state/locks/<resource>/lock.json`（`{resource, task_id, token, at}`）。
- **mkdir 原子占用**：`os.mkdir` 失败即已占用；`age` 在 `[0, ttl]` 视为新鲜（他人持有）
  -> 冲突方进入 `LOCK_WAITING` **排队不失败**（锁释放后自动重试分派）。
- **stale 接管**：`age > ttl` 或损坏/未来时间 -> 回收重建（与 relay_autopilot / D2 同源模式）。
- 任务结束后释放全部资源锁；stale 回收也释放锁（排队任务可继续）。

### 2.5 Project Isolation（§58）

- 每任务独立工作目录 `state/tasks/<task_id>/epoch-<epoch>/work/`。
- Worker 只能写自己的 work_dir；goal 文件也写在自己的 work_dir 内。
- **越界写校验**（结果裁决时）：
  1. 执行器报告的 `writes` 路径逐一 `_path_within(work_dir)` 检查；
  2. work_dir 内任何 symlink 目标必须在 work_dir 内（逃逸扫描）；
  3. 违规 -> `SANDBOX_VIOLATION` + 结果拒绝。

### 2.6 WAIT 局部性（§16）

- 任务 A 处于 `LOCK_WAITING` / `WAITING` 时，调度循环**照常分派其余 READY 任务**（不睡死）。
- `WAIT` directive 置 `WAITING`（等待审查/人工）；`RESUME` 置回 `READY`。

### 2.7 失效权端到端（§23/§41/§40/§30/§38）

- **STOP directive**：任务 -> `REVOKED`，`revoked_epoch = 当前 epoch`；
  执行单元可能已产出结果，但**后续结果一律拒绝**（`REVOKED_EPOCH`），
  CLI 子进程被立即 terminate；mock 跑完以产生可拒绝的"旧结果"（证据）。
- **REVOKE directive**：同 STOP + 立即 kill 执行单元（mock 提前退出 -> 结果不明也被拒）。
- **epoch 单调（§40）**：每任务/授权有递增 epoch；同 task_id 重新授权 epoch+1；
  回滚/复活的低 epoch 结果 -> `STALE_EPOCH`；被撤销代结果 -> `REVOKED_EPOCH`。
- **stale 回收（§30）**：`RUNNING` 任务心跳超 `stale_after_sec`（默认 120s）-> `STALE`，
  置停止事件 kill 执行单元、释放资源锁、结果拒绝（`STALE_HEARTBEAT`）。
- **OUTCOME_UNKNOWN（§38）**：子进程被杀 / 超时无明确结果 / 执行器异常 ->
  `OUTCOME_UNKNOWN` + `decision_entry=MANUAL_OR_RETRY`，**不自动判定成功或失败**。

### 2.8 裁决规则（结果接受顺序）

```
1) 结果 epoch != 任务当前 epoch         -> STALE_EPOCH（§40）
2) 结果 epoch <= revoked_epoch          -> REVOKED_EPOCH（§41）
3) 任务已被 stale 回收                  -> STALE_HEARTBEAT（§30）
4) 任务已失效/终态                      -> TASK_NOT_ACTIVE（旧结果拒绝）
5) sandbox 越界写                       -> SANDBOX_VIOLATION（§58）
否则 ACCEPTED
```

## 3. CLI 用法

```
# 运行调度直至收敛（tasks 文件 schema=PARALLEL_SCHEDULER_TASKS）
python runtime/parallel_scheduler.py run --tasks-file tasks.json \
        [--max-concurrent 2] [--mode mock|cli] [--state-root state/parallel-scheduler] \
        [--timeout 300] [--stale-after 120] [--lock-ttl 300] \
        [--stop-task TASK_ID] [--directives-file dir.json] [--worker-config F]

# 状态视图（只读）
python runtime/parallel_scheduler.py status [--state-root DIR]

# 对运行中的调度施加 directive
python runtime/parallel_scheduler.py directive --task-id T1 --action STOP [--reason ...]

# 清空调度状态（只动 state-root）
python runtime/parallel_scheduler.py reset [--state-root DIR]
```

tasks 文件示例：

```json
{
  "schema": "PARALLEL_SCHEDULER_TASKS",
  "schema_version": 1,
  "tasks": [
    {"task_id": "T1", "goal": "目标文本", "resources": ["repo-main"],
     "mock": {"sleep_sec": 0.05, "result": {"value": 1}}},
    {"task_id": "T2", "goal": "目标文本", "resources": ["repo-main"],
     "mock": {"sleep_sec": 0.05, "result": {"value": 2}}}
  ]
}
```

directives 文件示例（`when=after_start`，任务启动 `delay_sec` 秒后触发）：

```json
{
  "schema": "PARALLEL_SCHEDULER_DIRECTIVES",
  "directives": [
    {"when": "after_start", "task_id": "T1", "action": "STOP",
     "reason": "人工发现 T1 方向错误", "delay_sec": 0.1}
  ]
}
```

**退出码约定（与 D2 cost_router 一致）**：
- `0` = 成功（全部结果被接受，无失效拒绝、无 OUTCOME_UNKNOWN）；
- `1` = 配置/输入错误；
- `2` = 硬停（存在被拒绝的旧结果 / OUTCOME_UNKNOWN 需人工决策 / directive 失效）。

## 4. 测试套件（测试内模拟并行，全绿）

`runtime/test_parallel_scheduler_d4_offline.py`（24 用例，Python312）：

| 覆盖 | 用例 |
|---|---|
| §56 并发分派 | `test_concurrent_dispatch_2_workers`（3 任务 2 worker，断言都完成且结果正确 + 耗时体现并发） |
| §57 锁冲突排队 | `test_lock_conflict_queues_not_fails`、`test_distinct_resources_run_parallel` |
| §58 隔离 | `test_isolation_no_cross_contamination`、`test_sandbox_violation_detected`、`test_symlink_escape_detected` |
| §16 WAIT 局部性 | `test_wait_lock_does_not_block_others`、`test_wait_directive_does_not_block_others` |
| §23/§41 STOP 端到端 | `test_stop_revokes_old_result_end_to_end`、`test_revoke_kills_executor_unknown_outcome` |
| §40 epoch/回滚复活 | `test_epoch_monotonic_increases`、`test_rollback_revive_rejected` |
| §30 stale 回收 | `test_stale_heartbeat_reaped`、`test_stale_releases_resource_lock` |
| §38 OUTCOME_UNKNOWN | `test_outcome_unknown_no_guess`、`test_unknown_not_counted_as_success_or_failure`、`test_cli_executor_timeout_unknown` |
| CLI 子进程 | `test_cli_executor_subprocess_mock` |
| 单实例锁 | `test_single_instance_lock`、`test_stale_lock_takeover` |
| CLI 集成 | `test_cli_run_exit0`、`test_cli_run_stop_exit2`、`test_cli_config_error_exit1`、`test_reset_status` |

运行：

```bat
C:\Users\17838\AppData\Local\Programs\Python\Python312\python.exe -m unittest runtime.test_parallel_scheduler_d4_offline -v
```

## 5. L2 端到端证据（真实 CLI 进程/线程）

含 STOP 场景（`run --stop-task L2-STOP`，mock sleep 0.30s）：

```
exit_code = 2
summary.rejected = 1
summary.revocations = [{"task_id": "L2-STOP", "revoked_epoch": 1,
                        "revoke_reason": "CLI --stop-task", "rejected_count": 1}]
task.state = REVOKED
task.accepted = False
task.rejected[0].reason = REVOKED_EPOCH
task.rejected[0].detail = 结果 epoch=1 <= revoked_epoch=1 （§41 失效权/§40 回滚复活）：被撤销代的结果拒绝。
rejected old result value = old-result-42
```

多 Worker + 锁冲突场景（`--max-concurrent 2`，A/B 争 `l2-shared`，C 无锁）：
3 任务全部 `COMPLETED`、`accepted=3`、`rejected=0`、exit 0（冲突排队不失败）。

## 6. 遗留（留业主 L3）

1. **真实多 Worker 生产并行**：本模块并发分派经 mock/CLI 通道验证；接真实 AI worker
   （codebuddy/codex 等）消耗真实额度，属 L3 业主（配置 worker entry + 额度审计）。
2. **directive 跨进程协调**：`directive` 子命令当前加载持久化任务记录做离线裁决；
   运行中调度器的实时 directive 注入建议 L3 做 IPC/事件通道。
3. **隔离强度**：sandbox 校验为"报告 writes + symlink 扫描"的机械近似；生产建议叠加
   OS 级沙箱（容器/受限账户），属 L3。
4. **epoch 对账**：`OUTCOME_UNKNOWN` 的真实对账场景（如 straggler 子进程晚到报告）
   已提供 `accept_external_result` 入口；与真实 relay 账本对账接线留 L3。
