# REVIEW-R1-2026-08-30-ARCH — R1 守护层 guard_all.cmd 独立架构审核（会签）

- 审核人：software-architect-r1（高见远，R1 会签 / 架构审查视角，与实现者上下文独立）
- 审核对象：`scripts/guard/guard_all.cmd`（唯一新增文件）+ 计划任务 `ZhihengGuard`（每 2 分钟）+ 账本 `E:\WB\state\ai-production-control\construction-relay\guard-actions.ndjson`
- 审核时间：2026-08-30 16:05Z – 16:12Z（本地 2026-08-31 00:05 – 00:12）
- 审核方式：全源码静态核对 + 实时亲跑（含计划任务自动触发现场观察）+ 进程/状态/日志取证
- 边界遵守：只读；未 kill 任何 watcher/guard；未 push；唯一写入为本检查点文件

---

## 结论速览

**判定：APPROVED（附条件）**

四项审核全部 PASS；核心架构意图（OS 级守护）实现正确且经亲跑验证。附带 **2 个必须跟进项（D1 bsk 端口不一致、D2 无单实例锁）** 与 **4 个建议项（D3–D6）**。**当前进程数 = 2（1 watcher + 1 guard），多次快照均未出现持续双 watcher**，但双 watcher 竞态窗口在架构上真实存在（详见 §4 专项结论）。

---

## 1. 四项 PASS/FAIL

| # | 审核项 | 结果 | 证据 |
|---|--------|------|------|
| 1 | 架构意图（心跳判死/命令行匹配/杀树/官方入口重启/bsk/Chrome 记账/state 记账/账本/幂等 九点） | **PASS** | §2 逐点核对；源码行号引用 |
| 2 | 亲跑复现（exit 0、输出合理、账本新增行、进程在跑、心跳新鲜、计划任务存在） | **PASS** | §3 实测记录 |
| 3 | 坑核查（EPERM FileShare / 无 tail-head 管道 / CRLF / MSYS） | **PASS**（残留 D3） | §3.3；xxd 0d0a；L65 显式 FileShare |
| 4 | 红线核查（git 只新增 guard_all.cmd / 无凭据 / 无 force-push） | **PASS** | §3.4 |

---

## 2. 架构意图逐点核对（guard_all.cmd 全源码，281 行）

1. **心跳判死（L63–85）**：PowerShell 以 `[System.IO.FileShare]::ReadWrite -bor Delete` 非阻塞读 `watcher-heartbeat.json`（L65，坑 4 修复在位），解析 `at` 为 UTC DateTime，`age > 300s` 或读失败（`-1`）→ `HB_STALE=1` → 判死。实测：age=2s → ALIVE；账本历史 602s → DEAD 触发杀+重启。**PASS**
2. **进程匹配（L95 / L126 / L139 / L164 / L177）**：一律 `Win32_Process.CommandLine` 正则 `review-relay\.js\s+watch` / `outer-guard\.js\s+watch`，**无任何 WINDOWTITLE 匹配**（规避 §48 tasklist WINDOWTITLE 误判教训）。实测：仅匹配到 2 个目标进程，codex-bridge/weixinpay-MCP 等其他 node 进程未被误伤。**PASS**
3. **杀树（L97）**：`taskkill /F /T /PID`（force+tree）。账本 kill_stale 事件与 16:05 周期实际清除 32424+29192 一致。**PASS**
4. **官方入口重启（L132–134 / L170–172）**：`pushd E:\WB\tools\Trae-Ralph` + `start "" /b "%NODE_BIN%" src\review-relay.js watch --config "%RELAY_CONFIG%"`；guard 同理 `src\relay\outer-guard.js watch --config <同>`。实测产物进程命令行与此一致（cwd 相对路径生效）。**PASS**
5. **bsk 探活（L197–226）**：先 `netstat -ano|findstr :52900|findstr LISTENING` 探活，仅当 DOWN 才 `start "" /b bsk-dev.exe daemon start`（无管道），重启后 3s 复探。探活幂等。**实现 PASS，但环境端口漂移致恢复失效 → D1**
6. **Chrome 只记账不拉起（L231–248）**：读 `daemon.log.<date>` 匹配 browser connected/disconnected，记录 CONNECTED/DISCONNECTED/NO_LOG/UNKNOWN + 人工提示，**绝不自动拉起 Chrome，非阻塞**。符合 §39 人工确认边界（详见 §4d）。**PASS**
7. **state 完整性（L253–273）**：control.db 非空 + runtime-v1/health.json 含 ready 字段，仅记账 + 升级提示，不自动恢复（state-recover 不在生产 runtime，符合冻结约束）。实测 control.db=OK health.json=OK。**PASS**
8. **每动作记账（L278–280）**：`Add-Content -LiteralPath %LEDGER% ($row|ConvertTo-Json -Compress) -Encoding ascii`，行格式 `{timestamp,action,detail,ok}`。实测 66 行全部合法 JSON。**PASS**
9. **幂等（L126–130 / L164–168 / L199）**：start_watcher/start_guard 先查已有 pid 再起；bsk 先探再起。实测心跳新鲜时手动执行 = 纯探活，未 kill 未重启。**PASS**

---

## 3. 亲跑复现与坑核查

### 3.1 手动执行（按 schtasks 同方式 `cmd /c guard_all.cmd`）
```
[2026-08-30T16:11:07.595Z] ZhihengGuard run start
[OK] heartbeat_check: age=2s - watcher ALIVE
[ACTION] bsk_check: port 52900 DOWN - starting daemon
[WARN] bsk_start: daemon start issued but port 52900 still not listening
[WARN] chrome_check: NO_LOG - record + manual hint only, non-blocking
[OK] state_check: control.db=OK runtime-v1\health.json=OK
[2026-08-30T16:11:07.595Z] ZhihengGuard run end
=== EXIT CODE: 0 ===
```
- 账本新增 4 行（heartbeat_check / bsk_start / chrome_check / state_check），58 → 66 行。**PASS**
- 全程未 kill（心跳新鲜 → HB_STALE=0），幂等安全。**PASS**

### 3.2 计划任务与进程现状（多次快照 16:05–16:12Z）
- `schtasks /query /tn ZhihengGuard`：存在、启用、每 2 分钟（0:01 起）、上次结果 0、命令 `cmd /c C:\Users\17838\...\b1\scripts\guard\guard_all.cmd`。**PASS**
- 计划任务确实在自动触发：账本在 16:03/16:05/16:07/16:09/16:11 均有整点 2 分钟节奏的新行（16:03:03、16:05:03、16:07:03、16:09:03、16:11:09），并伴随 zhg-watcher/zhg-guard-20260831000505 等运行日志。
- 进程（多次快照）：**始终恰好 1 watcher（review-relay.js watch）+ 1 outer-guard（outer-guard.js watch）= 2 个，无第三个**。审核期间 watcher 身份更迭：33460→32424→2716→25828→28872，均为外层 guard 或 guard_all 重启产物，未出现双 watcher。
- watcher-heartbeat.json `at` 新鲜（审核期 16:07:51 / 16:11:06），pid 字段与在跑 watcher 一致（25828 存活时 pid=25828；28872 起后 relay.lock pid=28872）。

### 3.3 坑核查
- **坑 4（EPERM FileShare）**：守卫读侧修复在位（L65 显式 ReadWrite|Delete）。但**watcher 自身写侧仍发生 EPERM**：`zhg-watcher-20260830235839.err.log`（tmp-24616）与 `zhg-watcher-20260831000505.err.log`（tmp-2716）均为 `atomicReplaceJson` rename 被拒——说明仍有第三方读者（如 outer-guard 的 `fs.readFileSync`，outer-guard.js L196）默认共享模式不含 Delete，可致 watcher 心跳写入失败并（因 review-relay.js L789/793/796 写调用在 try/catch 之外）**直接崩溃**。→ D3
- **坑 2（无 tail/head 管道）**：watcher/guard 重启命令（L134/L172）与 bsk daemon 启动命令（L206）均为 `>> log 2>> log`/`2>&1` 重定向，**无管道**；`netstat|findstr` 仅用于探活本身。**PASS**
- **坑 1（MSYS 路径转换）**：不适用。schtasks 为 cmd 上下文，脚本内无 `/c/...` 风格 URL 参数；即便从 Git Bash 调用，解释器仍是 cmd.exe，内部 Windows 路径不受 MSYS 转换。**PASS**
- **CRLF**：xxd 确认全文件 `0d0a`。**PASS**

### 3.4 红线核查
- git status（分支 v1.1-blackbox）：`scripts/guard/` 下**仅 guard_all.cmd**；其余 untracked/modified（capability-registry.json、blackbox_bridge.py、blackbox-card.md、docs/evidence/reviews/ 等）为 R2/R3/主会话/检查点产物，按任务约定忽略。**PASS**
- guard_all.cmd 全源码无凭据/密钥/token。**PASS**
- 无 git push/force 操作（脚本本身不含 git 操作；审核未 push）。**PASS**

---

## 4. 双 watcher 风险专项结论（关键架构点）

### 4.1 双重启者架构事实
- **outer-guard.js 独立重启 watcher**：`decideGuardAction` 在 watcherPids 为空/超时未活动时返回 RESTART_DEAD/RESTART_STALE/SELF_HEAL，随后 `startWatcher`（outer-guard.js L204）直接 spawn 新 watcher；检查间隔默认 15s。
- **guard_all.cmd 也重启 watcher**：HB_STALE=1 时 kill_stale + start_watcher + start_guard（L48–52）。
- **实测 outer-guard 独立重启事件**：15:59:17（33460）、16:04:52（32424）、16:07:32（25828）、16:11:25（28872）——均在 guard_all 周期之间发生。

### 4.2 当前运行结论
**多次进程快照（16:05–16:12Z）恒为 1 watcher + 1 guard，未观察到持续双 watcher。** 最近似双启证据：relay.ndjson 中 `RELAY_STARTED pid=32424`（16:04:52.737）与 `RELAY_STARTED pid=2716`（16:05:09.102）相隔 17s 两次启动，但 32424 无 RELAY_STOPPED 记录（被强杀），重叠未证实。

### 4.3 竞态窗口（架构上存在，需工程缓解）
1. **无单实例锁**：guard_all.cmd 可被并发调用（计划任务 + 手动），两次调用可同时通过"无 watcher"检查并各自 spawn → 双 watcher。实测 16:11:07 手动与 16:11:09 计划任务确实并发写账本；另有 16:05:05 产生 zhg 日志与进程但账本无对应行的无法解释缺口（疑似并发/中断调用）。→ D2
2. **guard_all kill 与 outer-guard 15s 检查窗口**：guard_all 杀树后到新 watcher 出现在 watcherPids 之前（最多 8s 确认窗），outer-guard 若恰好检查会误判空 → 自行 spawn 第二个 watcher。guard_all 已做缓解（先起 watcher 后起 guard，新 guard 首轮即可见存活 watcher → HEALTHY）；但窗口仍存在。

### 4.4 分层建议
明确分层：**outer-guard = 快速重启（15s 粒度）；guard_all = 全重置兜底（心跳 300s + 2min 周期）**，并给外层 guard 增加"spawn 纪元"防旧实例补拉。

---

## 5. 架构评估（a–d）

- **a) 2 分钟周期 vs 300s 判死时间窗**：合理。最坏检测延迟 ≈ 300s 心跳过期 + ≤120s 下一周期 ≈ 7min，慢于 outer-guard 的 15s 快速层——作为兜底层可接受；阈值与周期无冲突（账本实测心跳新鲜时纯探活）。
- **b) watcher 自杀式异常（心跳文件被删/损坏）**：`-1` → 判死 → kill_stale + 重启。对"心跳坏但进程活"的 watcher 会误杀后重启（fail-safe 优先），方向正确；但若心跳写路径本身损坏（如 D3 的 EPERM），会与 outer-guard 一起放大 churn（当前现场即处于 watcher 每 3–5 分钟自退出 + 外层 guard 重启的循环中）。
- **c) 双 watcher（见 §4）**：**当前无持续双 watcher；架构竞态窗口存在**；建议单实例锁 + 分层 + spawn 纪元。
- **d) Chrome 断连只记账不拉起**：**符合 §39 人工确认边界**。扩展连接属于用户侧动作，自动拉起 Chrome 会越界；实测记账 ok=false + 非阻塞提示，正确。

---

## 6. 缺陷清单（含行号）

| ID | 级别 | 位置 | 缺陷 | 建议 |
|----|------|------|------|------|
| D1 | P1 | guard_all.cmd L32 | `BSK_PORT=52900`，而当前 bsk daemon（v0.1.10）绑定 `ws_port=52800`（bsk-home/daemon.json + daemon.log.2026-08-30 16:08:55）。实测每 2min bsk_check 报 DOWN 并触发 bsk_start，但重启失败（CLI 报 "no valid daemon.json"），恢复无效；而 daemon 进程 16556 实际在 52800 运行。 | 端口改为从 `bsk-home/daemon.json` 读取（或探 52800/52900 双端口 / 用 `bsk status`）；核查 daemon 端口漂移根因与 bsk CLI 配置路径（CWD 为 E:\WB\tools\bsk-file-bridge 而 daemon.json 在 bsk-home） |
| D2 | P1 | guard_all.cmd 全程 | 无单实例锁；并发调用可双 spawn watcher（双 watcher 直接通道），且已出现"有运行产物无账本行"的并发缺口 | 脚本顶部加互斥（lockfile + `if exist ... exit`，或用 `flock`/临时目录原子创建） |
| D3 | P2 | L65（读侧修复）/ watcher 写侧 | 守卫读侧已修，但 watcher 自身 atomicReplaceJson 写心跳仍可 EPERM（实测 tmp-24616、tmp-2716 两次），写调用在 review-relay.js try/catch 外 → watcher 直接崩溃；其他读者（outer-guard.js L196 readFileSync）默认共享不含 Delete | watcher 心跳写加重试/容错；或所有读者统一 Delete share |
| D4 | P2 | guard_all L48–52 + outer-guard.js L204 | 双重启者竞态窗口存在（§4.3） | 分层文档化 + spawn 纪元防旧 guard 补拉 |
| D5 | P2 | guard_all L236 | chrome_check 在 16:11:13 返回 NO_LOG，而相同逻辑直跑返回 MATCH（browser disconnected）——守护进程重启/日志轮转期间偶发误读（仅监控保真度问题，非阻塞） | 增加文件存在/可读重试 |
| D6 | P3 | 计划任务指向 | 脚本位于开发仓库 b1 内，运行时在 E:\WB\tools\Trae-Ralph；仓库移动/清理会使守护静默失效 | 复制到稳定位置（如 E:\WB\tools\Trae-Ralph\scripts\guard\）并更新任务 |

---

## 7. 现场观察（非缺陷，供主理人知悉）

- 审核期间运行时处于 **watcher 每 3–5 分钟自退出循环**（24616/33460/32424/2716/25828/28872 快速更迭），根因包括：stale relay.lock（watcher-stderr.log：`RELAY_LOCKED: pid=17360`，8-29 遗留死锁）、心跳 rename EPERM、phase 退出。guard 层按设计"守护非修 bug"在持续兜底，但**该 churn 属于 §10 中继病历所述既有运行时缺陷，建议后续单独修复**（非本交付范围）。
- outer-guard 每次 SELF_HEAL 会调用 codex（outer-guard.js L136，超时 45min），实测 3 次均 SELF_HEAL_CODEX_FAILED（~10s 内失败），未观察到 codex 进程堆积；属无效重试开销。
- 计划任务"只使用交互方式"（登录状态）——无用户会话时不运行；对本机可接受，若需真 OS 级守护可改"无论用户是否登录都运行"。

---

## 8. 审核证据索引

- `scripts/guard/guard_all.cmd`（281 行，CRLF 经 xxd 确认）
- `E:\WB\state\...\construction-relay\guard-actions.ndjson`（66 行，含 16:03–16:11 计划任务行与本次手动行）
- `watcher-heartbeat.json`、`relay.lock`、`relay.ndjson`、`outer-guard.ndjson`、`outer-guard.json`、`supervisor.json`、`zhg-watcher/zhg-guard-*.err.log`、`watcher-stderr.log`
- `E:\WB\tools\Trae-Ralph\src\review-relay.js`（心跳写循环 L785–800）、`src\relay\outer-guard.js`（L33–44 watcherPids、L67–73 decideGuardAction、L75–90 stopPids/startWatcher、L204 startWatcher）
- `E:\WB\tools\bsk-file-bridge\bsk-home\daemon.json`（ws_port 52800）、`daemon.log.2026-08-30`（16:08:55 listening 52800）
- `schtasks /query /tn ZhihengGuard /v`（2 分钟周期，上次结果 0）

---

## 9. 复审记录（D2 单实例锁，2026-08-30 16:26Z–16:30Z）

### 9.1 复审判定：**APPROVED（D2 修复通过；D1 bsk 端口修复同版顺带复核通过）**

实现者针对 D2 的修复方案（guard_all.cmd 新增 mkdir 原子锁）经源码核对 + 亲跑 + 生产并发证据三重验证，**正确性成立，无需 REWORK**。

### 9.2 锁机制核对结论（逐点）

| 核对点 | 结论 |
|--------|------|
| mkdir 原子性 / "mkdir 失败=已被锁" 分支 | **正确**。L325 `mkdir "%LOCK_DIR%" 2>nul`；L326 `if not errorlevel 1` 为"创建成功=我持锁"分支；失败即进入读 lock.json + stale 判定（L336–346）。Windows 上对已存在目录 mkdir 必然失败，互斥信号处理正确。 |
| token 匹配释放 | **正确**。L368–376 `:release_lock` 仅当 lock.json 内 token == 本实例 `LOCK_TOKEN` 才 `del lock.json + rmdir`；SKIP 路径（L67–74）不释放（非持有者）。 |
| stale 接管安全性 | **正确**。stale 判据 = lock.json MISSING / 不可读(-1) / 锁龄>300s（L343–346）；接管 = `rmdir /s /q` + `mkdir`，若 rmdir 后 mkdir 失败（接管竞态败北）→ LOCK_HELD=0 → SKIP（L351–355）。 |
| 故意不用 pid 判活 | **合理**。L42–45 注释准确：for /f 内 powershell 父进程是临时 cmd，存 pid 会立即误判 stale 破坏互斥。token 仅用于释放匹配，正确。 |
| 主流程集成 | **正确**。L66 acquire → L67 非持锁即 SKIP_LOCKED 记账退出（不跑 body）→ L75–83 body → L85 release。 |
| 释放失败路径 | 进程被杀/断电时锁残留 → 下一实例 300s 后 stale 接管，自愈。 |

### 9.3 亲跑验证（16:29:29Z，`cmd /c guard_all.cmd` 经 PowerShell Start-Process 稳定执行）
```
[OK] guard_lock: lock acquired token=20260831002929-1424829301
[OK] heartbeat_check: age=1s - watcher ALIVE
[OK] bsk_check: port 52800 listening - bsk OK      ← D1 动态端口修复生效
[WARN] chrome_check: NO_LOG（D5 未修，仅保真度）
[OK] state_check: control.db=OK runtime-v1\health.json=OK
=== EXIT=0 ===
```
- 账本新增 guard_lock 行（action=guard_lock ok=true）；**跑后 .zhg-lock 目录不存在 = 释放成功**；watcher+guard 进程数仍 = 2，未误杀。

### 9.4 生产并发证据（账本 guard-actions.ndjson）
- **16:24:10.806** `guard_lock SKIP_LOCKED owner_token=OWNER-A age=2s`：合成新鲜锁（age=2s）→ 正确 SKIP 且不动他人锁（随后 16:24:15+ 持锁者正常完成 heartbeat/bsk/chrome/state）。✓
- **16:25:03.734** `guard_lock SKIP_LOCKED owner_token=20260831002458-1336022086 age=5s`：**真实并发**——16:24:58 实例持锁运行中（其 state_check 16:25:04.496 才完成），并发调用 16:25:03.734 正确 SKIP 并退出，未双跑 body。✓
- 16:27:02 / 16:29:02 / 16:29:29 均单实例 acquire 正常。✓

### 9.5 双 watcher 问题解决情况
- **guard_all 侧并发双 spawn：已解决**（单实例锁串行化 body；16:25:03 并发 SKIP 实证）。
- **outer-guard 侧独立重启：按"分层守护"设计保留**——outer-guard.js 未改（快速重启 15s 层），guard_all 为全重置兜底层（心跳 300s + 2min 周期）；脚本 L185–188 注释与 L40–45 注释体现了该分层意图。D4（kill 与 outer-guard 15s 检查窗竞态）仍为 P2 架构性残余，非本修复范围。

### 9.6 残留（P3，不阻塞）
- :acquire_lock 读 lock.json（L338/L341）用 `Get-Content` 未加 FileShare Delete——持锁者 Add-Content 瞬间读失败 → 误判 MISSING → 误接管新鲜锁的窗口理论存在（毫秒级，未观测到）。
- release 未记账（静默）——acquire 行已证明锁周期，可接受。

### 9.7 本次复审同时复核的 D1（bsk 端口）
实现者同版修复：L32–36 注释说明 52900→52800 漂移；`:read_bsk_port`（L262–267）以 FileShare 非阻塞读 daemon.json `ws_port`（fallback 52800），bsk_check/bsk_start 均在探活前动态取端口（L231/L243）。**实测 16:23 起账本全部 `port 52800 listening ok:true`，D1 关闭**（此前每 2min bsk_start 空转失败）。
