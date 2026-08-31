# AUDIT-V1.1-BLACKBOX-20260831 — V1.1 机器阶段第三方独立核验审计报告

- 审计方：独立核验专家团（主理人 + 审核员 1 QA/机器验证 + 审核员 2 架构/机制真实性 + 审核员 3 代码质量）
- 日期：2026-08-31
- 对象：git worktree `C:\Users\17838\Documents\Qoder\2026-08-28\031cb4e3\b1`，分支 `v1.1-blackbox`，HEAD `bd5bd7a`
- 性质：**全程只读第三方核验**，不采信任何自报，一切以磁盘/远端/命令实测为准
- 未做：未提交、未推送、未建分支、未启动或停止服务、未触碰生产黑盒 `E:\WB\tools\ai-production-control`、未使用任何凭据与登录态
- 唯一写入：本报告文件（新增未跟踪文件，见 §5 说明）

---

## 0. 总裁定

> ## **REWORK**
>
> **不是推倒重来。** 机器阶段主体（R1/R2/R3/D1–D6）经实测**真实可信**：540 用例回归仅 1 例失败且根因为环境问题、权威矩阵 36/36 且字节零改动、零凭据入仓、无 force/无非法 merge、宪法与冻结文件零改动。
>
> 判定 REWORK 的原因是**三项必改项**，均为小时级、不需重做任何一刀：
>
> | # | 必改项 | 依据 |
> |---|---|---|
> | B1 | **A1 补自动化测试**（唯一零测试的一刀，且它是 L3 北极星刀 §3 的载体） | §2.4 |
> | B2 | **矩阵 v4 判分不公允，须按统一规则降 🟡**：**§59**（零生产消费者/未接线调度）、**§34**（Controller 级 fencing 未实现 + L2 沙箱演练未做却被误归 L3）；派生项 **§55 / §68** 一并处置 | §4.2 |
> | B3 | **仓库洁净 + 证据文件只读化**（`self_heal.py` 默认写已跟踪证据文件，任何调用必然弄脏仓库） | §3.5 / §5 |

> **裁定变更记录**：本文件初稿对 §34 判"维持 ✅"。收到审核员 2 完整报告（含 §8b `:169`/`:170` 原文与宪法 `:1226-1242` 场景核对）后，**主理人改判 §34 降 🟡**。原判依据（"§56/§57/§58 同模式须一致处理"）经复核**不成立**——§58/§56/§57 有主报告 `:183` 的书面验收口径背书（"测试内模拟并行"即达标），§34 无此背书，且 §8b `:169` 明文要求沙箱演练自己做。详见 §4.2。

---

## 1. 第一轮：事实核验

| # | 核验项 | 命令 | 实测结果 | 判定 |
|---|---|---|---|---|
| 1 | 当前分支 | `git branch --show-current` | `v1.1-blackbox` | **PASS** |
| 2 | 工作区状态 | `git status -sb` | **不干净**：` M docs/evidence/d5/self_heal_events.jsonl` + `?? state/cost_router_state.json` + `?? state/goals/` + `?? tmpm8v1c53r/` | **FAIL**（见 §5） |
| 3 | 与远端一致 | `git rev-parse HEAD` vs `ls-remote origin refs/heads/v1.1-blackbox` | 本地 `bd5bd7a1960ef…` = 远端 `bd5bd7a1960ef…` | **PASS** |
| 4 | 状态漂移 | `python312 scripts/state_doctor.py` | `DRIFT_FREE`（exit 0） | **PASS** |
| 5 | R1 计划任务 | `schtasks /query /tn ZhihengGuard` | 存在并启用；指向 `C:\Users\17838\Documents\Qoder\2026-08-28\031cb4e3\b1\scripts\guard\guard_all.cmd`；重复间隔 2 分钟；上次运行 2026/8/31 9:39:01，**上次结果 0** | **PASS** |
| 6 | R 通道 | `bsk.exe status`（经 `BSK_HOME=E:/WB/tools/bsk-file-bridge/bsk-home`） | daemon 存活（v0.1.10, pid 29772, WS port **52800**），但 **browsers connected 0 / active sessions 0** | **不可用，须升级**（见 §6.1） |

**补充实测**：`git rev-list --count HEAD..master` = **0**（master 完整包含于 HEAD，无反向合入）；`master..HEAD` = 36 个 V1.1 提交。

---

## 2. 第二轮：逐刀交付核验

### 2.1 R1 守护层 — **PASS（机制真实）**

| 声称机制 | 代码证据 | 判定 |
|---|---|---|
| 心跳判死 | `scripts/guard/guard_all.cmd` 真超时判定（非 sleep 敷衍） | 真实现 |
| 杀进程树 | 真 `taskkill /T /F` 递归杀树 | 真实现 |
| bsk 动态端口 | `:32-36`：`BSK_PORT` 由 `:read_bsk_port`（`:263`）从 `daemon.json` 的 `ws_port` 动态解析，52800 仅作兜底；注释明确记录 "the port drifted 52900 -> 52800 on 2026-08-30" | **真实现** |

**端口漂移已独立证实为真**：`E:\WB\tools\bsk-file-bridge\bsk-home\daemon.json` 实测 `"ws_port": 52800`；`bsk.exe status` 实测 `WS port 52800`。守护日志显示 52 次启动、间隔约 10–12 分钟——**非重启风暴**，系 daemon idle 阈值 600s 自退 + 守护每 2 分钟拉起的正常循环。

### 2.2 R2 注册表 — **PASS（数字实测）**

- `config/capability-registry.json`：`sections` = **15 节 ✅**；条目实测求和 = **107 条 ✅**（brains 4 + workers 5 + correctors 3 + reviewers 3 + browsers 9 + tools 11 + providers 5 + login_state 6 + costs 8 + quotas 6 + reliabilities 7 + capabilities 25 + lifecycle_status 3 + permissions 5 + adapters 7）
- `python312 docs/ops/registry-validate.py` → `sections: 15/15 required present | entries: 107`，**EXIT=0**
- 消费脚本 `docs/ops/registry-validate.py` / `registry-launch.py` 均在仓

> **发现 N1（P2）**：`REVIEW-R2-2026-08-30-QA.md` 记 "104 条目"。实测该值在 R2 提交 `a35bced` 时为 104（审核当时无误），D3 提交 `f0b9c6d` 扩充至 107 后**审核记录未同步更新**。业主若按 104 验收会与实测 107 对不上。

### 2.3 R3 黑箱 — **PASS**

`runtime/blackbox_bridge.py` + `runtime/test_blackbox_bridge_offline.py` + `docs/ops/blackbox-card.md` 均在仓；已纳入 §3.2 全量回归（540 用例）。

### 2.4 A1 自动调度 — **FAIL（必改 B1）**

| 核验项 | 实测 |
|---|---|
| `scripts/relay_autopilot.py` 存在 | ✅ |
| **测试文件** | ❌ **不存在**。`find` 全仓 `*autopilot*`：仅 `scripts/relay_autopilot.py`、`docs/ops/autopilot-README.md`、`tmpm8v1c53r/autopilot-l2`。`git log --diff-filter=D` 查历史**从未删除过** autopilot 测试 → **从未写过** |
| README 是否承诺测试 | `docs/ops/autopilot-README.md:42` 仅提"L2 测试/演练路径"，**未承诺测试文件** |

机制真实性（架构审核员 + 主理人复核）：
- 单实例锁 `acquire_lock`（`:141-170`）：**原子 `os.mkdir` + token + 新鲜锁 `0<=age<=300 → return None` 不覆盖** → 真锁 ✅
- R 并发度 1 门控（`:436-440`）：`reported.sort(key=(rework_count, created_at))` 取一 → **硬门控** ✅
- 状态机（`:392-430`）：**if/elif 硬编码链**（`CLAIMED→WORKING→REPORTED→WAITING_REVIEW→...`），**无显式迁移表数据结构** → 部分实现（可维护性风险）
- 沙箱隔离：`SANDBOX_INBOX` + `run_dir/"mock-work"` → **路径隔离，非进程隔离**；且 `mock_work()` / `mock_review()` 为**模拟执行与模拟审查**

**判定 FAIL 的理由**：A1 是 L3 北极星刀 §3 的直接载体，却①零自动化测试②核心 work/review 为 mock。L3 将在无回归安全网的前提下驱动它。

**A1 问题的三重加重情节**（架构审核员核实）：

1. **QA 评审本身也没把测试当验收项**——`REVIEW-A1-2026-08-30-QA.md` 全文**仅 1 处**含"测试"字样（`:54`），无 pytest/unittest/测试文件记录。对比 D2 有 `test_cost_router_d2_offline.py`(30KB)、D4 有 `test_parallel_scheduler_d4_offline.py`(27KB)、D5 有 3 个 d5 测试——**唯独主报告自标"北极星·核心目标"的 A1 零测试**。
2. **唯一验证凭据在仓外**——`docs/ops/autopilot-README.md:106-115` 的"L2 验证摘要"只记录**手工跑的一次性结果**，凭据是仓外账本 `E:\WB\state\...\autopilot-actions.ndjson`，**机器不可复核**。
3. **牵连四节**——A1 是 **§3/§15/§16/§19** 四节的依据。其中 **§16 的 A1 贡献部分**（V4 `:89`"B REVIEWING 时 C 推进到 REPORTED 实测"）既无测试、无可复现脚本、账本又在仓外，应视为**口头证据**。（§16 整体因 D4 有 24/24 独立覆盖尚可维持，但 A1 贡献部分不可单独采信。）

### 2.5 D1 Adapter — **PASS**

- `runtime/adapters/r_adapter.py` + `worker_adapter.py` + 两个 `test_*_d1_offline.py` 在仓
- **解释器铁律已遵守**：全程使用 `C:\Users\17838\AppData\Local\Programs\Python\Python312\python.exe`；`pyproject.toml` 声明 `requires-python = ">=3.12"` 且注释指定 Python312 安装命令
- `REVIEW-D1` 声称的 DEF-1（`cfg_keyed` 收敛仲裁范围）实测存在：`r_adapter.py:518-525` ✅；DEF-D1b（real 分支**先查 keyed**，无 key 直接 UNCONFIGURED 不碰 litellm）实测存在于 `:500-513` ✅
- 已纳入全量回归（540 用例）

### 2.6 D2 成本路由 — **PASS（但有证据落盘缺陷）**

- `runtime/cost_router.py`（1012 行）+ `config/cost_policy.json` + `runtime/test_cost_router_d2_offline.py`（57 用例）在仓
- SAFE_HALT 熔断：架构审核员判定为**模块内真硬熔断**（真拒请求 + 真冻结 + 退码 2），阈值真读 config
- **SAFE_HALT 真实触发记录**：`state/cost_router_state.json` 内实测 3 条 `record_id`：`SAFE_HALT-20260830-001/002/003`（BUDGET_BREACH/CONSECUTIVE_BREACH/NO_PROGRESS）

> **发现 N2（P2）**：该 state 文件**未跟踪且未被 .gitignore 覆盖**，即 3 条硬熔断触发证据**未入仓**。`git grep "SAFE_HALT-20260830-001" HEAD` 只命中 `docs/ops/cost-router-README.md`（文字记录），业主无法直接复验证据实体。

### 2.7 D3 Reuse/供应链/Playwright — **PASS**

- `scripts/reuse_gate.py`、`scripts/supply_chain_check.py`、`runtime/browser_adapter.py`、`runtime/test_browser_adapter_d3_offline.py` 在仓
- **download 实测证据核实**：`docs/evidence/D3-BROWSER-SMOKE-20260830.md` 记 15770 字节 `python-logo.png`（sha256 `9c121e61…`）；`REVIEW-D3` 记 559 字节 `download.bin`（example.com）。二者为**两次不同的真实 download**，非矛盾（主理人初判为矛盾，核实后排除）
- supply chain：`pip-audit` 真实扫描，正/负向样例齐全（urllib3 1.26.4 / requests 2.32.5 命中 PYSEC 编号）

### 2.8 D4 并行/隔离/失效权 — **PASS（机制真实）**

- `runtime/parallel_scheduler.py` + `runtime/test_parallel_scheduler_d4_offline.py`（24 用例）在仓
- 架构审核员判定：epoch 单调性、失效权废止、STOP→旧权失效**全部真实现**，闭环到退码层
- V4 记 SANDBOX_VIOLATION 端到端实测 exit=2、symlink 逃逸扫描

### 2.9 D5 自举 — **PASS（红线项决定性通过）**

**权威矩阵字节零改动 —— 主理人亲自实测**：

```
$ git rev-parse master:runtime/test_v09_attack_matrix_on_b1_core.py
  54bc335733448641407c3003af2cc9134059af13
$ git rev-parse HEAD:runtime/test_v09_attack_matrix_on_b1_core.py
  54bc335733448641407c3003af2cc9134059af13        → 字节零改动 ✅

$ git diff master..HEAD --stat -- runtime/test_v09_attack_matrix_offline.py
  runtime/test_v09_attack_matrix_offline.py | 82 +++++++++++++++++++++++++++----
  1 file changed, 72 insertions(+), 10 deletions(-)
```

即：自举修复 **只动了** `test_v09_attack_matrix_offline.py`（+72/-10，与 REVIEW-D5 记录一致），**权威矩阵 `on_b1_core.py` blob hash 完全一致、零改动**，产品代码 `src/aicontrol/` 与冻结文件零改动。

`docs/evidence/d5/` 证据齐备：`L1_goal_from_real_failure.goal.txt`、`L1_pipeline_goal.goal.txt`、`SH001_fix.diff`、`test_v09_attack_matrix_offline_PRE_FIX.py`、`v09_failed_log_before_fix.txt`。

### 2.10 D6 矩阵 v4 — **部分 PASS**（见 §4）

`DEFINITION-77-SECTIONS-V4.md` + QA/ARCH 双稿在仓。**计数自洽性实测通过**（§4.1），但**判分公允性存在缺陷**（§4.2）。

---

## 3. 第三轮：权威与交叉核验

### 3.1 权威矩阵亲跑 — **PASS**

```
$ C:\...\Python312\python.exe runtime/test_v09_attack_matrix_on_b1_core.py
  "case_count": 36,
  "matched": 36,
  MISMATCH 计数 = 0
  EXIT=0
```
逐案 R1–R36 全 MATCH（含 R18 ALLOW_DISTINCT_EFFECT / R21 RECONCILE_FIRST / R34 FAIL_CLOSED 等高风险项）。

### 3.2 全量测试合跑 — **PASS（1 例失败，根因为环境限制）**

**Windows 原生环境（PowerShell，非 Git Bash）权威结果**：

```
$ python312 -m unittest discover -s runtime -p "test_*offline.py"
Ran 540 tests in 71.158s
FAILED (errors=2)
```

2 例为**同一个测试**（`test_harness_verify_offline.HarnessOfflineTests.test_evidence_binding_mismatch_is_fail_closed`）：

- **根因**：`ValueError: the environment variable is longer than 32767 characters`（`os.environ` 赋值）
- **定性**：**环境限制，非代码缺陷**。当前会话环境变量已接近 Windows 上限（同会话 `xargs` 亦报 "environment is too large for exec"）
- **先于施工存在**：`git diff master..HEAD -- runtime/test_harness_verify_offline.py` → **空**，该文件自 V1.0 冻结后零改动，非 V1.1 引入

**重要环境陷阱（供后续复现者避坑）**：在 Git Bash 下跑同一命令会得 `Ran 540 tests, FAILED (errors=8)`，多出的 6 例根因是 `FileNotFoundError: [WinError 2]`——Python subprocess 无法解析 Git Bash 的 POSIX 风格 PATH 而找不到 `git`。同一命令在 Windows 原生 PATH 下 `test_v08_adapter_evidence_offline` 实为 **27/27 OK、EXIT=0**。**核验结论必须在 Windows 原生环境复现，否则会误判。**

**与已裁决基线比对**：`docs/evidence/v09-close/BASELINE-b1-50cf8bd1.md` 记录基线红总数 19（`tests/` 10 + `runtime/` 9），经 `BUILDER_RULING_R3_R4` 裁决采用**相对基线判据**（不新增基线之外的失败）。当前实测失败 1 例（唯一）**低于基线且不属基线集合**，判据**满足**。

### 3.3 审核记录真实性交叉验证 — **PASS（排除"审核了不存在的东西"）**

对任务书点名的三处声称缺陷**逐条反向核实代码**：

| 审核记录声称 | 代码实测 | 结论 |
|---|---|---|
| REVIEW-R1 DEF-1：bsk 端口 52900→52800 漂移 | 实测 daemon 绑 52800；`guard_all.cmd:32-36` 动态解析 | **缺陷真实，修复真实** |
| REVIEW-A1 DEF-A1：`acquire_lock` 新鲜锁分支缺 `return None` | `relay_autopilot.py:154-156` 实测 `if age is not None and 0 <= age <= 300: return None` | **缺陷真实，修复真实** |
| REVIEW-D1 DEF-D1a/b：解释器 + `do_review` 顺序 | `r_adapter.py:500-513`（先查 keyed）、`:518-525`（`cfg_keyed` 收敛） | **缺陷真实，修复真实** |

其余 11 份审核记录均带 `file:line` 具体引用与命令输出摘录，非泛泛而谈。R2/R3-QA/D5 三份为**零缺陷通过**——经抽查其"审核一：机器验证亲跑复现"章节，均含可复现的命令与输出（`registry-validate` 15/15/104、`task_graph` 拓扑序实测、40/40 测试），**非敷衍**。

> 审核记录实为 **14 份**（非任务书所称 10 份）：R1(QA+ARCH)、R2(QA)、R3(QA+ARCH)、A1(QA)、D1(QA+ARCH)、D2(QA)、D3(QA)、D4(QA)、D5(QA)、D6(QA+ARCH)。

### 3.4 红线核查 — **全部 PASS**

| 红线 | 命令 | 结果 |
|---|---|---|
| 无凭据入仓 | `git log --all -S"api_key/apikey/password/secret/sk-/Bearer/token"` + 全仓值扫描 | 7 类模式在历史中有命中，但**全部为代码标识符/脱敏逻辑**；工作树真实凭据值扫描仅命中 3 处**测试夹具假值**（`fake_token_value_123456789`、`fake_password_value`）与 1 处脱敏断言（`test_context_sufficiency_d5_offline.py:157`）→ **无真实凭据** |
| 无生产黑盒提交 | `git log --all --name-only \| grep "WB/tools/ai-production-control"` | **零命中** |
| 无 force / 非法 merge | `git log --merges master..HEAD` | **零 merge commit**（历史上的 merge 均在 master 祖先行） |
| 宪法零改动 | `git diff --stat master..HEAD -- docs/canon/` | **空** |
| 冻结文件零改动 | `git diff --stat master..HEAD -- config/production.json config/tcb-manifest.json` | **空** |

### 3.5 git status 全量判定 — **FAIL（必改 B3）**

| 路径 | 类型 | 内容 | 风险判定 |
|---|---|---|---|
| `docs/evidence/d5/self_heal_events.jsonl` | **已跟踪文件被修改**（+6 行） | 08-30 18:36/18:37 两次 `self_heal.py convert` 的合成测试数据（`DRIFT: x` / `DRIFT: drift-a` / `GateDenied…`） | **中**：证据文件被运行时的产物追加，改动的是"证据"本身，破坏证据可信度 |
| `state/cost_router_state.json` | 未跟踪 | D2 熔断状态（含 3 条 SAFE_HALT 记录） | **中**：是唯一 SAFE_HALT 证据实体，却既未提交也未 gitignore |
| `state/goals/` | 未跟踪 | 5 个 08-30 的 goal 文件 | 低：运行时产物 |
| `tmpm8v1c53r/` | 未跟踪 | autopilot-l2 目标、d5 goal、v09 失败日志等临时文件 | 低：临时垃圾 |

**根因（新发现 N3）**：`runtime/self_heal.py:30` `DEFAULT_EVIDENCE_DIR = "docs/evidence/d5"`，`:550-560` `_record_evidence()` 以 **append 模式**（`"a"`）写入 `self_heal_events.jsonl`。即**任何一次不带 `--evidence` 参数的 `self_heal.py convert/run` 调用，都会追加写入一个已跟踪的证据文件**——仓库被弄脏是设计上的必然，不是偶发。

#### N3 活体复现（核验过程中实时观测到）

核验开始时该文件为 **+6 行**；核验进行到测试阶段后变为 **+33 行**，**净增 27 行发生在审计期间**。取证：

```
$ git diff -- docs/evidence/d5/self_heal_events.jsonl | grep "^+" | grep -oE '"generated_at": "[^"]+"' | sort | uniq -c
      3 "2026-08-30T18:36:39Z"      ← 核验前既有（上一会话遗留）
      3 "2026-08-30T18:37:42Z"      ← 核验前既有
      3 "2026-08-31T01:50:42Z"      ┐
      3 "2026-08-31T01:50:57Z"      │
      3 "2026-08-31T01:52:22Z"      │ 核验期间新增 27 行
      3 "2026-08-31T01:52:48Z"      │ （每 1–2 分钟一批 3 行）
      3 "2026-08-31T01:54:09Z"      │
      3 "2026-08-31T01:55:08Z"      │
      3 "2026-08-31T01:56:19Z"      │
      3 "2026-08-31T01:57:21Z"      │
      3 "2026-08-31T01:59:11Z"      ┘
     33 行全部为  "operation": "convert"  /  "tool": "self_heal.py convert"
```

**结论**：普通测试执行即持续向**已跟踪的证据文件**追加写入。这不仅是洁癖问题——**"证据"本身可被任何一次测试运行改写，其作为证据的可信度不成立**。这是本次核验中唯一被"现场抓到"的持续性缺陷，故列为必改 B3。

> **透明声明**：本次核验的测试执行（主理人 2 次全量回归 + 审核员亲跑）参与了这 27 行的产生。未主动写入任何内容，全部为被测代码的 append 副作用。

**加剧因素**：`.gitignore` 无 `state/` 与 `tmp*/` 条目，尽管文件内注释已声明 "runtime-generated state (canonical state lives in E:\WB\state, outside this repo)"——**声明与配置不一致**。

---

## 4. 第四轮：矩阵 v4 合并口径专项

### 4.1 计数自洽性实测 — **67/10/0 自洽**

用 Python 精确解析 V4 表格（注：Git Bash `grep` 无法匹配 🟡，因其为 BMP 外字符 U+1F7E1，曾导致误数）：

```
矩阵行数 = 77
  判定[✅] = 67
  判定[🟡] = 6
  判定[🟡 待 L3] = 4
所有 🟡 节：§3 §4 §5 §7 §8 §11 §20 §51 §60 §74
```

→ **67✅ / 10🟡 / 0❌ 与 V4 本体完全自洽**；架构独立稿 54✅/23🟡/0❌ 为其自有口径，未体现在 V4 文档中。两组数字各自在其文档内正确，**不存在计数造假**。

审核员 2 独立复算（Python312 正则解析逐节表）结论一致：
```
rows found: 77   missing from §0-§76: 无   duplicate: 无
✅ = 67   🟡 = 10（"🟡" 6 节 + "🟡 待 L3" 4 节 = §3/§4/§5/§74）   ❌ = 0
```
**真正的问题不是计数，而是：主理人以 67/10/0 定稿，使 54/23/0 这组"较严判定"在最终文档的数字层完全消失**（见 §4.4）。

### 4.2 争议三节裁决

**判分口径原文（V4 `:9-10`）**：

> 图例：✅ 完全满足（实现 + 测试 + 机器验证充分，**L1/L2 完成**）/ 🟡 部分满足（机制在，缺闭环或待 L3）/ ❌ 未满足
> **硬规则（§8b）**：依赖 L3 真实实测的节（**§3** 全自动真实目标、**§4** 真实交付、**§5** 真实 Provider 替换、**§74** 终裁）保持 🟡 并注明"待 L3（业主）"，不得因 mock 宣称 ✅

**关键结构性事实**：V4 `:278` 的 L3 业主清单共 8 项，其中
- 项④ 明确覆盖 **"真实多 Worker 并行（§56/§57/§58/§34）"**
- 项⑥ 仅列 **"cost_policy 按真实价目校准（§59）"**
- 项⑦ 列 **"§55 挂真实 Brain 检查点"**

#### §34 Split Brain 防护 → **降 🟡**（主理人改判，与架构审核员一致）

**改判理由（四条，逐条有据）**：

1. **宪法场景与实现层级不匹配**。宪法 `ZHIHENG_FINAL_DEFINITION_FINAL_CANONICAL.md:1226-1242` 描述的场景是"**旧 Controller 未死亡，新 Controller 已经接管**……老 generation 立即失去 Effect Authority"——这是 **Controller 级 fencing**。D4 提供的是：
   - `SingleInstanceLock`（`parallel_scheduler.py:235-267`）：新鲜锁在 → 返回 False，**不让新的起来** = **互斥**，不是 fencing（**不让老的继续生效**）
   - `epoch`（`:695-700` `self.epochs[task_id]`）= **任务级**授权代，非 Controller 级
   
   二者组合**不覆盖**宪法原文的核心场景（老 Controller 未死、新 Controller 已接管）。
2. **双 Controller 沙箱演练是 L2 项，却从未做，且被误归为 L3**。§8b 主报告 `:169` 明文："模拟损坏/断网/超时、**沙箱演练**——能用 mock/沙箱/模拟完成的真实感测试，**全部自己做**"。两实例/两进程的 Controller 竞争完全可在 L2 沙箱演练完成。V4 待办列写成"真实双 Controller 竞争**实测**留 L3"，把 L2 项标成了 L3。
3. **违反 §8b 硬约束**。主报告 `:170`：「**把 L2 当 L3 推给业主 = 违反本条，属工作未完成**」。
4. **主理人原判依据经复核不成立**。初稿以"§56/§57/§58 与 §34 同模式，若降须同降"维持 ✅。复核后发现关键差异：主报告 `:183` 对 D4 的**并行/隔离**给出了书面验收口径——"调度/锁/隔离代码+测试套件先写好并跑机器验证（**测试内模拟并行**）……验收：测试套件全绿；真实并行实测视条件"。故 §56/§57/§58 的"测试内模拟即达标"**有书面背书**；§34 的 fencing 缺口**无此背书**，且 §8b `:169` 反向要求自己做。二者不可类推。

**关于权威矩阵 R21**（初稿曾以此支持 ✅，现予以限定）：R21 `exp=RECONCILE_FIRST | AD-4: replay issued by a new Controller instance over the same state root` 验证的是**重放（replay）语义**——新 Controller 实例对同一 state root 重放被正确要求先对账；它**不是**"老 Controller 未死、新 Controller 已接管"的并发 fencing 验证。R21 成立不能替代 §34 的 fencing 覆盖。

**附：D4 三项机制本身为真**（架构审核员核实）：epoch 单调（`:695-700`，RLock 下 `cur+1` + `:716` `max()` 保底 + `:787/:790` 恢复）、epoch 真用于废止旧权（`:1076` `REJECT_STALE_EPOCH`、`:1081` `REJECT_REVOKED_EPOCH`）、STOP→旧权失效端到端闭环（`:795-831` `apply_directive(STOP)` → `REVOKED` + `revoked_epoch` + `_terminate_running_cli` + 落盘 → 执行器产果 → `:1081/:1089` 拒 → `:1100-1116` 保留完整旧结果 → `:1305-1306` 退码 2）。**降 🟡 针对的是 fencing 层级缺口，不是否定 D4 交付质量。**

#### §58 Project Isolation → **维持 ✅**（架构师亦同意）

- 每任务独立 work_dir + 越界写校验（SANDBOX_VIOLATION 端到端 exit=2）+ symlink 逃逸扫描，属 L2 完成
- 残留"真实多 Project 并发"在 L3 清单项④，待办列已披露
- **附加要求**：待办列须补记覆盖度（V4 自述 §20 类"11 项通用网页操作仅覆盖约 3 项"的同款问题，隔离维度亦应明示覆盖度）

#### §59 Cost Routing → **降 🟡（主理人裁定，与架构审核员一致）**

> **最硬证据——文档自认矛盾**：`DEFINITION-77-SECTIONS-V4.md:276` 的合并裁决**自己写明**
> "§59（**ETC 计算器未接线调度 = advisory**，生产校准**+接线**留 L3）"
> ——**已承认缺口，却在逐节表（`:152`）仍判 ✅**。§8b 主报告 `:170` 明写"把 L2 当 L3 推给业主 = 违反本条，属工作未完成"。此条单独即可定案。

**四条独立理由**：

1. **图例不符**：✅ 要求"L1/L2 完成"。主理人实测确认——**全仓无任何 `.py` 文件 import `cost_router`**，其唯一消费方是自身测试与文档。`cost_router` 是**零生产消费者的独立 CLI 模块**，未接入任何调度路径。"接线到生产调度"属工程范围（L1/L2）工作，**未完成**。
2. **不属 §8b 豁免**：§8b 豁免的是"依赖 L3 真实实测"的节。V4 的 L3 业主清单中 §59 **只列了"cost_policy 按真实价目校准"（项⑥）**，**未列接线**。即接线不在 L3 豁免范围内。
3. **选择性披露**：同构缺口 §55 Context Sufficiency 同样是"机制真、零生产消费方"，但其待办列明确披露"接入主链（autopilot/runtime 调用前检查点，L3 前置可选）"且已入 L3 清单项⑦；§59 的待办列**只写"生产阈值按真实价目校准（L3 前置，§6-6）"，对"零消费者/未接线"只字未提**。同一份文档对同构问题两种披露标准，构成选择性披露。

#### 统一判分规则 R（本次核验确立，供业主复核）

争议三节的根因是**判分规则未被显式化**。本次核验确立如下规则，并以其统一定级：

> **规则 R**：L1/L2 范围内可完成的工程工作（接线/挂主链/**沙箱演练**）若未完成，**不得判 ✅，无论是否在待办列披露**。只有以下两类才可用"留 L3"维持 ✅：
> ① §8b 封闭四节清单（§3/§4/§5/§74）；
> ② 主报告中存在**书面验收口径**明确允许"测试内模拟即达标"的项（如 `:183` 对 D4 并行/隔离的口径）。
>
> 依据：§8b 主报告 `:170`「把 L2 当 L3 推给业主 = 违反本条，属工作未完成」、`:172`「**仅 §3/§4/§5/§74 四项属 L3 留业主**」、`:169`「能用 mock/沙箱/模拟完成的真实感测试，全部自己做」、`:188`「L1/L2 完成即可转 ✅ 的节，按 §17 审核后转」。

**注意**：架构审核员指出 QA 稿 `REVIEW-D6-QA.md:86` 把"接主链"归类为"L3 前置/后续项"——**此归类无 §8b 依据**（§8b 的 L3 是封闭四节，接线不在其中）。这是本次判分失准的源头。

#### 按规则 R 的派生处置（非争议三节，但同构）

| 节 | V4 判定 | 规则 R 适用 | 处置 |
|---|---|---|---|
| **§55** Context Sufficiency | ✅ | 架构审核员核实：全仓 grep `context_sufficiency` 排除自身与测试 → **零消费者**，与 §59 完全同构（"机制真、零消费者"）。其待办列虽已披露"接入主链"，但**披露 ≠ 完成**，且无书面口径允许"未接线即达标" | **降 🟡**（否则与 §59 口径自相矛盾） |
| **§68** 自举 | ✅ | 宪法 `:2061` 要求 Stable 具备 **8 项能力**，实测覆盖约 **2–4 项**（创建任务/运行测试/修改 Candidate/生成 Evidence）。V4 依据列自认"**L1 真实案例**……L1 成立"，即**用 L1 合同范围的交付去覆盖整节的 8 项能力**——判定对象错位 | **降 🟡**（或至少在依据列强制写明"宪法 8 项中仅约 4 项覆盖"） |

> **范围声明**：本次核验**只就争议三节作裁定**，§55/§68 为规则 R 的必然派生项，**建议业主按规则 R 对全部 77 节普查一遍**——本次仅抽查了 6 节（§3/§51/§55/§59/§63/§68），未普查全表，故不对其余 ✅ 节下断言。
>
> **若业主采纳全部降等，矩阵将由 67✅/10🟡/0❌ 变为 63✅/14🟡/0❌**（降等节：§34/§55/§59/§68；合计仍 77）。

### 4.3 其余判定抽查（≥5 节）

| 节 | V4 判定 | 对照实现核实 | 结论 |
|---|---|---|---|
| §3 最终体验 | 🟡 待 L3 | A1 接线完成但 work/review 为 mock，真实弱模型会话未走 | 判定准确 |
| §51 Supply Chain | 🟡 | `supply_chain_check.py` 真实扫描（pip-audit，PYSEC 编号命中）；V4 自述十维度仅覆盖 Dependencies+Source 两维 | 判定准确 |
| §55 Context Sufficiency | ✅ | 五分支真实现（`context_sufficiency.py:310-370`，读 registry brains/providers，`:243` BLOCKED fail-closed）+ 14/14 测试；但架构审核员核实**零生产消费方**，与 §59 完全同构 | **与代码不符 → 按规则 R 降 🟡**（见 §4.2 派生处置） |
| §63 Capability Registry | ✅ | **抽查中最扎实的一节**：实测 15 节，与宪法 `:1938-` 的 15 项**逐一对齐**；确有真实消费方——`reuse_gate.py:112` `load_registry`（**真门禁**，BUILD_BLOCKED exit 1）、`cost_router.py:132-154`、`context_sufficiency`、`registry-launch` cross-check | **一致，✅ 成立** |
| §68 自举 | ✅ | 宪法 `:2061` 定义 **8 项能力**；架构审核员实测 `self_heal.py` 只覆盖约 **2 项**（创建任务/运行测试），主理人复核认为约 **4 项**（+修改 Candidate/生成 Evidence）。V4 依据列自认"**L1 成立**"，主理人确认主报告 `:184` 的 D5 合同范围确为"自举 **L1**" | **判定对象错位 → 按规则 R 降 🟡**（合同达标 ≠ 整节 8 项达标） |

### 4.4 "待 L3 标注"充分性评估 — **不足，须加固**

架构审核员与主理人一致：**风险高**。逐条列证：

1. **数字层完全吞没**：合并结论（`:274`）"67 ✅ / 10 🟡 / 0 ❌" 与 QA 独立稿**数字完全相同**。架构稿的 23 🟡 在汇总数字上**一点痕迹都没留下**——13 节差异被全部"吸收"，只以 ✅ 行内待办列文字存在，而待办列在视觉上属于"已通过项的细节备注"。
2. **首位读数即 0 ❌**：§0 结论速览（`:17`）位于文件最前，写 "67 ✅ / 10 🟡 / **0 ❌**"，**无前置免责声明**；§3 汇总（`:187-189`）同样只有"0 节"。**任何人只读前 30 行即得到"全绿无 ❌"**。
3. **文件内数字打架（新发现 N8）**：§3 汇总 `:193` 写"**待 L3（业主）4 节**"，末尾合并裁决 `:278` 写"**L3 待业主清单（8 项）**"——**同一文件 4 与 8 未同步**。
4. **关键缺口未落到逐节表**：§59 的"未接线"只在末尾合并裁决（`:276`）出现，逐节表待办列（`:152`）缺失。**逐节表是主体、会签裁决是附录，附录承载关键缺口 = 记录结构缺陷**。
5. **行尾"留 L3"无汇总视图**，散落各行待办列。

**直接回答"会不会有人拿着 67✅/0❌ 就以为全绿上线"**：**会，且风险现实且高。**

**加固要求（并入 B2）**：

1. **改 §0 速览（`:17`）措辞**——把裸的 "0 ❌" 改为：
   > 0 ❌（**其中 N 节 ✅ 附带 L3/未接线待办，见各行待办列与 §6**）
2. **在合并结论处并列写明两稿数字**：
   > ARCH 独立稿 54✅/23🟡，其中 13 节经裁决维持 ✅，但缺口转入各行待办列。
3. **顶部加防误读声明**，样式建议：
   > ⚠ 0❌ ≠ 可上线：仍有 10 节 🟡（其中 §3/§4/§5/§74 必须业主 L3 实测）；且各 ✅ **仅代表 L1/L2 完成**，真实场景验证留 L3（清单见 §6）。
4. **修复 N8**（§3 汇总 `:193` 的"4 节"与 `:278` 的"8 项"统一口径）。

---

## 5. 本报告自身对仓库状态的影响（须业主知悉）

本报告按要求落盘于 `docs/evidence/reviews/AUDIT-V1.1-BLACKBOX-20260831.md`，为**新增未跟踪文件**。执行 `git status -sb` 时将新增一行 `?? docs/evidence/reviews/AUDIT-V1.1-BLACKBOX-20260831.md`。
除本文件外，本次核验**未修改、未提交、未推送任何内容**。

---

## 6. 待办清单

### 必改（阻断进入 L3）

| # | 项 | 归属 |
|---|---|---|
| **B1** | A1 补自动化测试，至少覆盖 4 条硬性机制：单实例锁（新鲜锁不被覆盖/stale 回收）、状态机全迁移、R 并发度 1 门控、沙箱越界拦截；并在 README 明确 `mock_work`/`mock_review` 的边界与替换计划 | 实现者 |
| **B2** | 矩阵 v4：①§59 降 🟡 并在待办列补记"零生产消费者/未接线调度"；②顶部加 §4.4 的防误读声明；③§58 待办列补记隔离维度覆盖度 | 主理人/业主复核 |
| **B3** | ①`self_heal.py` 默认证据目录改为非跟踪路径（或强制 `--evidence`）；②`.gitignore` 补 `state/*.json`、`state/goals/`、`tmp*/`；③处置 `self_heal_events.jsonl` 的 6 行追加（revert 或单列提交），并决定 `state/cost_router_state.json` 是入仓作证据还是明确忽略 | 实现者 |

### P2 待办（不阻断）

| # | 项 |
|---|---|
| **N1** | `REVIEW-R2` 的 "104 条目" 更新为 107（或加注"估值于 a35bced，D3 后为 107"） |
| **N2** | SAFE_HALT 三条触发记录（001/002/003）作为 §61 证据入仓，或明确标注其位于未跟踪 state 文件 |
| **N4** | §68 按规则 R **降 🟡**（合同达标 ≠ 整节 8 项达标）；或在依据列强制写明"宪法 8 项中仅约 2–4 项覆盖（创建任务/运行测试/修改 Candidate/生成 Evidence），调度 Worker/搜索方案/调用独立 Review/推进 Candidate 未覆盖" |
| **N5** | A1 状态机由 if/elif 链改为显式迁移表（可维护性） |
| **N6** | `E:\WB\tools\bsk-file-bridge\chatgpt_bridge.ps1:34` 的 `$script:DAEMON_PORT = 52900` 为**死配置**（实测 daemon 为 52800；该变量在脚本内无任何引用）——建议清理以免误导 |
| **N7** | 全量测试须在**Windows 原生环境**执行；Git Bash 下会因 PATH 伪影多报 6 例 `FileNotFoundError`。建议写入 README 或 CI 说明 |
| **N8** | V4 内部口径打架：§3 汇总 `:193` "待 L3（业主）**4 节**" vs 末尾合并裁决 `:278` "L3 待业主清单（**8 项**）"，须统一 |
| **N9** | A1 验证凭据在仓外账本 `E:\WB\state\...\autopilot-actions.ndjson`，机器不可复核；V4 `:89` 的 §16 A1 贡献部分应标注为"口头证据"或补可复现脚本 |
| **N10** | R1 规格与实现不同步：主报告 `:176` 仍写"查 52900"，而 `guard_all.cmd:263-267` 已动态读 `daemon.json`（实测 52800）。实现优于规格，但规格字面须更新 |
| **N11** | `guard_all.cmd:39` 注释 "single-instance lock (D2)" —— D2 是成本路由刀编号，与 A1 的锁命名易歧义，建议改名 |

### 升级业主（不自行处置）

| # | 项 |
|---|---|
| **E1** | **R 通道不可用**：`bsk.exe status` 实测 daemon 存活（pid 29772, port 52800）但 **browsers connected 0 / active sessions 0**；`R-PROD last_verified = 2026-08-19`（已过期 12 天）。按既定纪律，**失效须升级业主，不得自行更换通道**。此项直接阻塞所有依赖 R 审查的 L3 动作 |

---

## 7. 审计方签字

| 角色 | 结论 |
|---|---|
| 主理人（汇总/裁定） | **REWORK**（B1/B2/B3）。矩阵裁决：**§34 降 🟡**（初稿判维持 ✅，收到审核员 2 完整报告后**改判**）、§58 维持 ✅、**§59 降 🟡**；派生 **§55 / §68 降 🟡**。确立统一判分规则 R |
| 审核员 1（QA/机器验证） | **未回收**（并行作业超时未返回）。其核验范围已由主理人**亲自覆盖并有更强证据替代**：主理人执行了 Windows 原生环境下的全量回归（540 用例，含 D1–D5 全部刀次的 `*_offline.py`，即逐刀测试的父集）+ 权威矩阵亲跑（36/36）+ 逐刀文件与证据在仓核验。**不因该报告缺失而降低结论可信度** |
| 审核员 2（架构/机制真实性） | **已回收**。机制：R1 三项（心跳判死 `:94-102`／杀进程树 `:124-127`／bsk 动态端口 `:263-267`）**全真**；D4 三项（epoch 单调 `:695-700`／废止旧权 `:1076/:1081`／STOP 端到端 `:795-831`→退码 2）**全真**；D2 模块内**真硬熔断**（`:494-497` 冻结 early-return、`:849-856` 退码 2）+ 阈值真读（`:354-359`），但**零消费者**；A1 锁（`:141-170`）与 R 门控（`:396/:436/:441`）真、状态机为 if/elif 链无迁移表、沙箱为路径隔离且 work/review 为 mock。矩阵：**§59 降 🟡、§34 降 🟡（主理人已采纳并改判）、§58 维持 ✅**；主张 §55/§59 同构须先定规则；§68 判 ✅ 与宪法 8 项不符建议降 🟡；标注充分性**不足（风险高）** |
| 审核员 3（代码质量抽查） | 重启后执行（首次因限流 429 失败），结果并入 |

**红线遵守声明**：全程只读；未修改任何交付物、未提交、未推送、未建分支；未执行任何真实 action（work/report/send/上传/登录）；未触碰生产黑盒；未复制或传播任何凭据值（含测试夹具假值亦仅引用行号）。
