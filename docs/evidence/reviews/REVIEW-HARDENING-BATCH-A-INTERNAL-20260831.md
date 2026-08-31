# REVIEW — HARDENING BATCH A (INTERNAL, BLIND)

- 审核对象：git `9a31e2c..41e80e3`（5 commits：8e4f3e7 / d9ff266 / 5ec6d13 / b9de73f / 41e80e3）
- 审核方式：盲审。仅依据 diff 与本地实际执行的测试证据，不参考任何施工说明文档。
- 审核人：独立代码审核员（AI）
- 日期：2026-08-31
- 环境：Windows 10 / Python 3.12（`C:\Users\17838\AppData\Local\Programs\Python\Python312`）
- 证据：`PYTHONDONTWRITEBYTECODE=1` 下实跑新增/受改测试共 **138 例，0 失败**
  （concurrency/lease/relay-gate 23、effect-reconcile+hygiene+wiring+v08+self-heal 74、
  report-gate 4、V09 攻击矩阵 37）；跑毕 `git status --porcelain` 为空（未污染仓库）。

---

## 一、结论

**APPROVE-WITH-NITS**

核心修复全部真实生效、方向正确、无 fail-open 回归；新增测试绝大多数是"旧代码必红"的真断言。
存在 2 个 P2（陈旧锁接管 TOCTOU 仍有极窄双持有者窗口，与其自身宣称"消除双持有者窗口"不完全相符；
effect-reconcile 绕过 per-RUN RunLock）与若干 P3，不阻塞本批合入，但列入必改清单限期修复。

---

## 二、审核清单逐项结论

### 1. 每个修改是否真正修复对应缺陷、无新引入缺陷 —— 通过（附 2 个 P2）

| 修复 | 验证结论 |
|---|---|
| RunLock 空锁 age 判定（GATE-2#8） | 生效。`_break_if_stale` 不再对"刚创建的空锁"无条件 unlink；只有 age > LOCK_STALE_SEC(180s) 才回收（runtime/runtime.py:270-296）。N4a/N4b 双向断言验证。旧代码对空文件 `json.loads("")→ValueError→unlink` 会删掉他人新锁造成双持有者，已消除。 |
| `_unlink_quiet` 吞 unlink 竞态 OSError | 生效。Windows 下他进程持有句柄时的 PermissionError 不再伪装成 RUNTIME_ERROR 崩溃整条命令（runtime/runtime.py:258-268）。 |
| 调度器 `_acquire_resources` 全有或全无（GATE-2#7） | 生效。部分失败回滚全部已取锁（runtime/parallel_scheduler.py:924-935）；N1 断言 `held_by("r1") is None`，旧代码必红。回滚用 try/ValueError 兜底，`release` 实际不抛 ValueError，无害。 |
| `_stop_event` 消费者 + reap_stale 直接杀 CLI 子进程 | 生效。monitor 循环消费 `_stop_event` 并 `_terminate`（parallel_scheduler.py:530-545）；reap_stale 对 `hasattr(ex,"_terminate")` 的执行器直接终止（:1210-1215）。N2 实测 sleep-30 子进程在 reap 后 5s 内死亡，旧代码必红。 |
| `accept_external_result` 拒绝无 epoch 外部结果 | 生效（parallel_scheduler.py:1157-1161）。全仓 grep 确认仅测试调用该 API（d4 测试本就显式带 epoch），无误伤合法路径。§40 setdefault 绑定当前 epoch 的绕过已封死。 |
| relay 锁 O_EXCL 原子认领（GATE-2#9） | 认领路径原子性成立（`os.open(O_CREAT|O_EXCL)`，scripts/relay_autopilot.py:273）；**但陈旧锁接管路径仍有极窄双持有者窗口，见 P2-1**。 |
| controller_lease 原子化（GATE-2#6） | 生效。acquire/renew/revoke 全部在 `_lease_lock` 串行化；A1（4 线程并发 acquire 得到 generation 1..4 各异）实跑通过，旧代码必现重复 generation。fd 由三个调用点 try/finally 释放，无 fd 泄漏；LeaseLockTimeout fail-closed。 |
| save_lease fsync | 位置正确：先 fsync tmp 再 `os.replace`（controller_lease.py:139-146），断电不留残缺 lease。 |
| revoked 检查 + revoke API | 生效。`check_execute_right`（:233-237）与 `renew`（:170-175）均查 revoked；A2 验证"renew 不可复活已撤销权"。 |
| 畸形 expires_at fail-closed | 生效。`check_execute_right` 捕获 ValueError/TypeError → LEASE_EXPIRED（:249-256），A3 验证。调用方（relay lease 闸）不再 catch-and-skip 变 fail-open。 |
| effect-reconcile 出口（GATE-1#5） | 生效，语义 fail-closed 保持（--not-occurred 不解锁；--succeeded 解锁且留 EFFECT_RECONCILE_RESUME 审计）。X1-X4 全过。**但未持 per-RUN RunLock，见 P2-2**。 |
| report 接入三闸（GATE-1#1） | 生效。run.cmd `report → :send_guard`（run.cmd:29-36），send_guard_lite 依次 install gc/es/ec 后委托 `rt.main()`；`cmd_report` 内部以模块全局名调用 `cmd_send`（runtime.py:1762），install 的 monkeypatch（es:867）在调用时解析到 gated 版本，三闸真实生效。R1（无授权→HARD_BLOCKED+无传输）、R2（授权→DONE）、R3（PAUSED→EC 拒+无传输）实测通过。 |
| relay 禁伪造 commit + FROZEN 拦截 + require_gates（GATE-1#2/3/4） | 生效，详见第 3 项。C1-C4、F1-F4 全过。 |

**锁顺序/死锁专项**：scheduler `_guard → ResourceLocks._guard` 单向嵌套；lease 文件锁是叶子锁（锁内只做 load/mutate/save，不再取其他锁）；RunLock 是 per-run 独立锁。未发现反序持锁或循环等待。唯一阻塞点：reap_stale 持 `_guard` 期间 `_terminate` 内 `proc.wait` 最多 ~4s，属性能问题非死锁（P3-3）。

### 2. run.cmd 路由与子命令分发一致性 —— 通过

- `report` → `:send_guard` → send_guard_lite.py（gc+es+ec）→ runtime.py `report` 子命令（runtime.py:2324-2328 有定义）。参数经 `%*` 与 `_extract_contract_options` 透传，R2 实测全链路到 DONE。
- `effect-gate` 确为死入口：runtime.py 全文 grep 无 `effect-gate`/`effect-reconcile` 子命令，与注释诊断一致。新 `effect-reconcile` → `:effect_safety` → effect_safety_lite.py，`main()` 在 `install()` 之前拦截 `argv[0]=="effect-reconcile"`（effect_safety_lite.py:967-968），argparse 参数（`--run-id` 必填、`--succeeded|--not-occurred` 互斥必选、`--evidence-file` 必填，:924-930）与 run.cmd 透传完全匹配。X5 + v08 routing anchor + R4 三处文本锚点均已更新且断言 `effect-gate` 缺席。

### 3. admission_checks require_gates 语义 —— 通过

- 与 docstring 逐条对齐：判定性拒绝（cost SAFE_HALT/FROZEN、context BLOCKED/HUMAN_AUTHORIZATION、lease 失效）在 mock/relay 一律拒（:127-130、:146-149、:174-176）；require_gates=True（relay）时 wiring 不可用/配置损坏/闸内异常 fail-closed（:104-106、:134-136、:151-153、:178-180）；mock 保守放行只记 reason。
- `require_gates` 仅在 `cmd_submit` 接线（:420，`args.mode=="relay"`，choices mock|relay，default mock），无其他调用点绕过。
- FROZEN/SAFE_HALT 拦截完整性：`admission_checks` 调用的是 `do_route`（:120），其 verdict 空间 = ALLOWED / UNDETERMINED / SAFE_HALT / FROZEN（cost_router.py:462,548,585,592），拒绝性 verdict 恰为 SAFE_HALT+FROZEN，拦截完备（BLOCKED 仅出自未被调用的 `do_budget`，由 context 闸承担其语义）。UNDETERMINED 放行与 cost_router "不误伤" 设计一致，docstring 有声明。
- 残留观察（非本 diff 引入）：`cmd_drive` 内联 lease 检查仍 catch-and-skip（relay_autopilot.py:651-653），与 submit 侧 fail-closed 不对称，建议后续统一。

### 4. controller_lease 锁实现 —— 有条件通过（P2-3 / P3 项）

- **stale 回收竞态**：`stat→stale→os.remove` 之间无身份复核（controller_lease.py:100-106）。Windows 上临界区全程持 fd，打开中的文件不可删除，基本封住；**POSIX 上 unlink 对打开文件同样成功**，慢临界区（>STALE_LOCK_SECONDS=10s）或双接管者交错可获得两把 fencing。见 P2-3。
- fsync 位置正确（fsync → os.replace）；无目录 fsync（Windows 不可移植，可接受）。
- renew 检查顺序 generation→holder→revoked：无绕过路径（gen 不匹配/holder 不匹配/revoked 任一命中都拒绝；同代同 holder 的 revoked 命中 LEASE_REVOKED）。check_execute_right 把 revoked 放在 generation 之前，旧代+已撤销时报 LEASE_REVOKED，同为 fail-closed。
- revoke 不校验 generation/holder 属操作员 API 语义，合理；revoke 后 acquire 开新代清 revoked，A2 验证 fencing 仍完整。
- `_release_lease_lock` 先 close 再 remove：remove 前存在极小窗口他者拿锁等 5s 超时，可忽略。
- busy 锁 LeaseLockTimeout fail-closed、stale 自愈，A4 验证。

### 5. reap_stale 直接 _terminate 的副作用 —— 通过

- `MockWorkerExecutor` 无 `_terminate` 方法（类体 378-476 确认），`hasattr` 保护正确跳过；mock 在 run 循环里自行消费 `_stop_event`（:425）→ 结果 OUTCOME_UNKNOWN，被 `_adjudicate` 以 REJECT_STALE_HEARTBEAT 拒收（:1110-1113），双通道无冲突。
- REVOKE 路径（:832-836）set `_stop_event` + `_terminate_running_cli`，与新 monitor 消费者叠加：`_terminate` 幂等（poll 前置 + OSError 兜底），无重复杀风险。
- 迟到结果（STALE 后 executor 线程完成）一律被拒，不会把已回收资源的任务"复活"为完成态。
- P3-3：`_terminate` 在持 `_guard` 时执行，最多 ~4s 阻塞全部调度线程。

### 6. 测试质量 —— 通过（附 P3-4 磨光项）

- **哨兵测试（state hygiene）**：真断言。探针强制要求 cost/lease 闸真实执行（checks 非空即拒"空探针"），前后指纹（mtime_ns+size）比对真实 `state/controller_lease.json`、`state/cost_router_state.json`；创建/删除/更新任一即红。另附 5 条 .gitignore 覆盖锚点。
- **矩阵真断言**：36 例 + R34 忠实探针全部转为真实 `unittest.TestCase`，`_assert_case` 同时断言 `harness=="ok"` 与 `matched`（任一 HARNESS_ERROR/MISMATCH 即红）；setUpClass 硬校验 36 例（数量漂移即类级错误）；CLI `main()` 退出码改为反映结果（41e80e3 之前恒 0）。实跑 37/37 绿。
- **wiring 隔离**：彻底。cost_router 四个 IO 点全 patch（save_state 重定向 tmp），controller_lease 全 patch，context_sufficiency 只读（文件内无写点，已核实）；do_route 不 patch（真逻辑跑假数据）。hygiene 哨兵与"跑完测试 git status 干净"双重印证。
- **能否变红**：N1/N2/N3(前半)/N4a/N4b/A1-A5/C1-C4/F1-F4/X1-X5/R1-R4 逐个按旧实现推演均必红；N5a/N5b/N5c 在旧实现下也绿（语义锚点性质），真正的判别测试是 N5d（并发恰好一个赢家）。见 P3-4。
- **fixture 泄漏教训已固化**：effect_reconcile fixture "先设 seam 再 load 模块" 有注释存证（test_effect_reconcile_offline.py `_make_run`），X 套件全程 tmp state root。

### 7. guard_all.cmd del/rmdir 非递归改动 —— 通过

- LOCK_DIR（`%STATE_ROOT%\.zhg-lock`，guard_all.cmd:48）内容假设成立：guard 只写 `LOCK_INFO`（lock.json）一个文件（:333、:367）。
- `del /q lock.json` + `rmdir`（无 /s）+ `mkdir` + errorlevel 检查：目录内有任何意外内容时 `rmdir`/`mkdir` 失败 → `LOCK_HELD=0`（SKIP_LOCKED），**失败方向安全**；且不再像 `rmdir /s /q` 那样连带摧毁并发接管者刚重建的锁目录。
- 残留（先存缺陷，非本 diff 引入，P3-6）：`mkdir` 成功与 `Add-Content` 写 lock.json 之间的窗口，若被并发接管者 `rmdir`，双方都可能认为自己持锁。窄窗口 + 需双进程同时接管陈旧锁，建议后续以"重命名抢占"消除。

---

## 三、发现明细

### P2（必改，限期下一个批次）

- **P2-1 陈旧锁接管 TOCTOU（双持有者窗口未完全消除）** — `scripts/relay_autopilot.py:275-298`
  时序：A 读到 stale 内容(:275) → B `os.remove`(:295) + O_EXCL 认领(:273) + 写 token + 关闭 fd(:300-304) → A 的 `os.remove`(:295) 删除 B **已关闭的新鲜 lock.json**（Windows 关闭后即可删）→ A 认领成功 → A、B 双持有者。窗口毫秒级、需 stale 锁 + 近同时接管，但 commit 宣称"消除双持有者窗口"，与实现不完全相符。
  建议：接管改为 rename-steal（把 lock.json `os.rename` 到 per-pid 墓碑，rename 唯一成功者再 O_EXCL 认领），或 remove 前重读并比对身份（token/mtime）。

- **P2-2 effect-reconcile 绕过 per-RUN RunLock** — `runtime/effect_safety_lite.py:932-961`
  runtime.py 所有改状态命令都持 `with RunLock(args.run_id)`（:1196,1227,1339,1581,1628,2099,2138），而 `cmd_effect_reconcile` 的 load→reconcile→save→resume（含两次 `save_state`，:946-955）全程无锁。两个并发 reconcile 都能通过 :934 的 OUTCOME_UNKNOWN 预检 → 双重 SUCCESS 提交/双重 resume/revision 连跳两次；与并发 directive/report 交错时 `save_state` 的 prev 轮换（runtime.py:360-379）可能丢更新。
  建议：`state = rt.load_state(...)` 起至 resume 结束包进 `with rt.RunLock(args.run_id):`（load 移入锁内）。

- **P2-3 controller_lease stale 回收同样缺身份复核** — `runtime/controller_lease.py:100-106`
  与 P2-1 同型。Windows 上由"临界区全程持 fd + 打开文件不可删"基本封住；POSIX 上 unlink 打开文件同样成功，慢临界区（>10s）或双接管者交错可破坏 fencing。建议与 P2-1 同一修复（rename-steal 或 remove 前重读身份），并在文档标注跨平台差异。

### P3（建议修复 / 记录）

- **P3-1 RunLock 对"合法 JSON 但非对象/异常 ts 类型"崩溃** — `runtime/runtime.py:281-286`
  lock 内容为 `[...]`/`"str"`/`123` → `data.get` 抛 AttributeError；`{"ts":null}` → `float(None)` TypeError；均不在 `except (OSError, ValueError)` 内 → `__enter__` 裸 traceback 而非等待/干净 RUNTIME_ERROR。方向仍 fail-closed，但部分重新引入"坏锁崩命令"。建议补 `TypeError/AttributeError` 或 `isinstance(data, dict)` 校验。
- **P3-2 effect-reconcile / relay submit 错误路径裸 traceback** — `runtime/effect_safety_lite.py:932`（run 不存在 → FileNotFoundError）、`:946` 镜像记录与 log 不匹配 → `_find_effect` EffectDenied（:323）未转 DENIED JSON；`scripts/relay_autopilot.py:430` relay 模式缺 `--candidate-commit` → `_resolve_commit` ValueError（:353-356）未捕获，走 ledger 干净拒绝的通道被绕过。均 fail-closed，仅体验/可审计性问题。
- **P3-3 reap_stale 持 `_guard` 调 `_terminate`** — `runtime/parallel_scheduler.py:1210-1215`，`proc.wait` 最多 ~4s 阻塞全部调度线程。建议移出锁外，或优先依赖 monitor 消费 `_stop_event`（已具备），reaper 兜底终止放到 `_release_resources` 之后。
- **P3-4 测试磨光** — `runtime/test_concurrency_hardening_offline.py:114` N3 第二断言 OR 链部分同义反复（`res2.get("ok", False) or "error" not in res2 or res2.get("ok") is True`），未真正钉住"显式 epoch 正常接受"路径；N5a/N5b/N5c 为语义锚点而非判别测试（旧实现亦绿）。
- **P3-5 STATUS.md 时点失真** — `STATUS.md:7` "2 wiring tests fail due to lease pollution; fix in progress under GATE-3" 在同一提交内已修复却仍表述为 in progress（实测 wiring 套件全绿）。建议刷新一行。
- **P3-6 guard 接管残留窗口（先存）** — `scripts/guard/guard_all.cmd:353-369`，`LOCK_HELD=1` 设置于 mkdir 之后、Add-Content 之前，并发接管者可在此间 rmdir；`rmdir /s /q` 时代即存在，本 diff 未加重。建议后续 rename-steal 或 mkdir 后立刻写文件并复核。

### 未发现 P0/P1

无 fail-open 回归、无锁顺序/死锁缺陷、无 fd 泄漏、无误伤合法路径（epoch 必填、commit 必填均只影响外部 straggler/relay 提交契约，已有测试与错误信息明示新契约）。

---

## 四、必改清单

1. 【P2-2】`cmd_effect_reconcile` 全程包 `rt.RunLock(args.run_id)`（load 移入锁内）。
2. 【P2-1】`relay_autopilot.acquire_lock` 陈旧/损坏锁接管改为身份复核或 rename-steal，使"消除双持有者窗口"的宣称在接管路径同样成立。
3. 【P2-3】`controller_lease._lease_lock` 同一接管模式修复（可与 2 同批）；文档标注 Windows/POSIX 差异。
4. 【P3-1】`RunLock._break_if_stale` 增补 TypeError/AttributeError 处理（或 isinstance 校验）。
5. 【P3-2】effect-reconcile 的 run 不存在 / EffectDenied、relay submit 的缺 commit：转结构化 DENIED/ledger 拒绝，不裸 traceback。
6. 【P3-3】reap_stale 的 `_terminate` 移出 `_guard`（monitor 已是第一消费者）。
7. 【P3-5】刷新 STATUS.md 的 known-issue 行。

（1-3 为必改；4-7 建议随下批顺带。）

---

## 五、测试证据（本次审核实跑）

| 套件 | 结果 |
|---|---|
| test_concurrency_hardening_offline + test_lease_atomicity_offline + test_relay_gate_failclosed_offline | 23/23 OK |
| test_effect_reconcile_offline + test_state_hygiene_sentinel_offline + test_relay_autopilot_wiring_offline + test_v08_adapter_core_offline + test_self_heal_d5_offline | 74/74 OK |
| test_report_gate_offline | 4/4 OK |
| test_v09_attack_matrix_on_b1_core（36 例 + R34 忠实探针） | 37/37 OK |
| 跑后 `git status --porcelain` | 空（仓库未污染） |

合计 138 例、0 失败（Python 3.12，PYTHONDONTWRITEBYTECODE=1，全部离线 tmp/沙箱根）。
