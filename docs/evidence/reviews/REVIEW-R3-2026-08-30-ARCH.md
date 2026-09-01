# REVIEW-R3-2026-08-30-ARCH — R3 黑箱 v1 架构独立审核（架构会签）

- 审核对象：v1.1-blackbox 开发线 R3（分支 `v1.1-blackbox`，worktree `b1`）
- 审核者：高见远（software-architect，独立审核，与实现者上下文隔离，全部亲跑验证）
- 审核日期：2026-08-30 23:5x
- 审核范围：
  - `runtime/blackbox_bridge.py`（新增：RESULT/HUMAN_GATE 只读命令）
  - `runtime/test_blackbox_bridge_offline.py`（新增：14 测试）
  - `docs/ops/blackbox-card.md`（新增：§71 一页操作卡）
- 审核方式：只读审核；未修改任何受审文件；未 push
- 交付物：本报告

---

## 0. 结论速览

| 项目 | 判定 | 证据 |
|---|---|---|
| 架构一致性 | **PASS** | 与 brain_bridge/capsule_bridge 同一 CLI 桥模式；JSON 输出统一；退出码约定不冲突；纯只读（grep 零写操作） |
| 状态根读取正确性 | **PASS** | 118 个真实 RUN 目录布局与代码路径拼接完全吻合；手动全量扫描与桥输出逐项一致 |
| 亲跑复现 | **PASS** | result(PASS/REWORK)、human-gate(全量/单RUN)、离线测试 14/14、边界用例全部复现通过 |
| 越权与红线 | **PASS** | R3 仅新增 3 文件；生产 runtime.py/run.cmd 未被触碰；worktree runtime/runtime.py 无改动；无凭据硬编码 |
| 可演进性 | **PASS（附建议）** | 判定规则已集中为常量；扩展点清晰（见 §5） |
| **最终判定** | **APPROVED（有条件）** | 1 个低危缺陷列入后续修复，不阻塞本次会签（见 §6.1） |

---

## 1. 架构一致性判定：PASS

### 1.1 与既有 CLI 桥模式的一致性（对照 brain_bridge.py / capsule_bridge.py）

| 模式要素 | brain_bridge | capsule_bridge | blackbox_bridge | 一致性 |
|---|---|---|---|---|
| 独立 CLI + argparse | ✅ 顶层参数 | ✅ 顶层参数 | ✅ 子命令（result/human-gate/work/report） | 一致（子命令是四动词语义的自然扩展） |
| 输出 JSON | ✅ `json.dumps(ensure_ascii=False)` | ✅ 同左 | ✅ `ensure_ascii=False, indent=2` | 一致 |
| stdout UTF-8 重配置 | 未显式（脚本内 ASCII） | 未显式 | ✅ `sys.stdout.reconfigure(encoding="utf-8")`（审计 P0-2 教训） | 增强，不冲突 |
| 退出码约定 | 0=正常 / 1=文件缺失 / 2=无效 | 0=正常 / 1=状态缺失 / 2=验证失败 | 0=正常 / 1=未找到 / 2=无结论 / 3=状态损坏 | 兼容扩展，不冲突 |
| `non_authority` 标记 | ✅ | ✅ | ✅ | 一致 |
| 只读红线（docstring 声明） | ✅ | ✅ | ✅ | 一致 |
| 状态根路径 | 不读状态 | `E:\WB\state\ai-production-control\runtime-v1\runs` | 同一路径（常量 `DEFAULT_STATE_ROOT`） | 一致 |

- 退出码语义核查：既有模块用 0/1/2；blackbox_bridge 新增 `3=STATE_UNREADABLE`（json 解析失败/编码损坏）——与既有取值无重叠冲突，且语义更细（1=确定性未找到，3=状态损坏需人工）。判定为合理扩展。
- 纯只读核查：`grep -E "write_text|open\(.*['\"]w|remove|unlink|mkdir|rename" runtime/blackbox_bridge.py` **零命中**。result/human-gate 只读 state.json 与 reply 文件；work/report 委托层只 `print` JSON 指引，不执行任何状态变更。判定：纯只读成立。

### 1.2 四动词语义（§65）

- `work`/`report`：保留在生产 run.cmd（`E:\WB\tools\ai-production-control\runtime\run.cmd` 实测确认存在，转发 `%*` 给生产 runtime.py）——兼容路径成立。桥内 work/report 为委托层（只输出指引，不代执行）。
- `result`（RESULT）：新增，查 run 最终结果 PASS/REWORK + 结论。语义正确（见 §3）。
- `human-gate`（HUMAN_GATE）：新增，列出等待人类介入任务。语义正确（见 §3）。

### 1.3 work/report 委托层"只输出指引不代执行"的架构判断

**判断：架构上合理**。理由：
1. 双 runtime 红线要求生产 run.cmd 是唯一 state-changing 正式入口；若施工线桥直接调用生产 run.cmd，会在"谁执行状态变更"上产生二义性，且桥将不再是纯只读查询件。
2. 桥只输出 `delegate` + `invocation` 指引文档，弱 AI/用户据此走正式入口，职责单一、无副作用、可离线运行。
3. 风险点（见 §6.2-2）：`ok=True` 可能被弱 AI 误解为"命令已执行"——建议补一个显式 `executed:false` 字段。不构成架构缺陷，属可用性建议。

---

## 2. 状态根读取正确性：PASS

### 2.1 真实 RUN 目录布局抽查（亲查）

状态根 `E:\WB\state\ai-production-control\runtime-v1\runs` 实际存在 **118 个 RUN 目录**。抽查 3 个真实 RUN：

- `RUN-20260818-173304-7350`：`state.json` + `journal.jsonl` + `msg_*.txt` ×9 + `reply_epoch1_1787045760_*.txt` ×9（命名 `reply_epoch<N>_<epoch>_<hash>.txt`）
- `RUN-20260826-202012-c86e`：`state.json` + `journal.jsonl` + `msg_*.txt` + `reply_epoch1_*.txt` ×1
- `RUN-20260823-180728-eb46`：同布局

**与代码假设吻合性**：
- 路径拼接 `root / run_id / "state.json"` ✅（实际存在）
- `find_latest_reply` 的 glob `reply_epoch*_*.txt` ✅（真实命名 `reply_epoch1_<epoch>_<hash>.txt` 匹配）；`requery_reply_*.txt` 当前无实例，但 glob 不报错，可兼容未来
- `state.json` 字段：`status`/`last_r_verdict`/`last_reply_path`/`last_r_next_action`/`updated_at`/`blocked_reason`/`effect_human_gate_required` 全部存在且语义匹配 ✅

### 2.2 reply 文件机械解析验证（亲读真实文件）

- PASS 例：`===REVIEW_VERDICT=== PASS` + `===NEXT_ACTION===` + 正文 + `===CHATGPT_DONE:WB_...===` —— 与 `_VERDICT_RE`（`^===REVIEW_VERDICT===\s*([A-Za-z_]+)\s*$`）和正文提取逻辑吻合；`===CHATGPT_DONE:...===` 因带冒号不被 `_MARKER_RE` 误捕，且被 `parse_reply` 显式剔除 ✅
- REWORK 例：`===REVIEW_VERDICT=== REWORK` + 同行 `===NEXT_ACTION=== 返工并…` —— 提取正确 ✅
- 解析不到 verdict → `verdict=None`（不猜）—— 与"机械投影、不猜"原则一致 ✅

### 2.3 全量交叉核对（桥输出 vs 独立脚本扫描）

独立脚本扫描全部 118 个 state.json：
- HARD_BLOCKED=10、PAUSED=2 → **waiting=12**，与 `human-gate` 全量输出 `waiting_count=12` 逐项一致（10 HARD_BLOCKED + 2 PAUSED，run_id 完全吻合）
- STOPPED=6 → `terminal_count=6`，与桥输出一致 ✅
- 全量扫描与 `total_scanned=118` 一致 ✅

---

## 3. 亲跑复现（全部实测）

| 用例 | 命令 | 结果 | 退出码 |
|---|---|---|---|
| result PASS | `python runtime\blackbox_bridge.py result --run-id RUN-20260818-173304-7350` | verdict=PASS, final=true, conclusion=审查原文, reply_path 正确 | 0 ✅ |
| result REWORK | `python runtime\blackbox_bridge.py result --run-id RUN-20260826-202012-c86e` | verdict=REWORK, final=false（status=RUNNING 未闭环）, user_line=返工指引 | 0 ✅ |
| human-gate 全量 | `python runtime\blackbox_bridge.py human-gate` | waiting=12 / terminal=6 / total_scanned=118 | 0 ✅ |
| human-gate 单 RUN(PAUSED) | `--run-id RUN-20260824-165334-0e33` | waiting=1, need=等待 RESUME | 0 ✅ |
| human-gate 单 RUN(HARD_BLOCKED) | `--run-id RUN-20260823-175137-725a` | waiting=1, reason 原文呈现 | 0 ✅ |
| 离线测试 | `python runtime\test_blackbox_bridge_offline.py -v`（runtime/ 下） | **Ran 14 tests, OK**（与声称一致） | 0 ✅ |
| 边界：RUN 不存在 | `result --run-id RUN-NOPE-9999` | RUN_NOT_FOUND, instruction 正确 | 1 ✅ |
| 边界：include-terminal | `human-gate --include-terminal --run-id RUN-20260818-163305-79b7` | terminal 正确输出 | 0 ✅ |
| work 委托 | `work --goal-file goal.txt --r-url https://example.invalid/session` | 输出 delegate 指引文档（不执行） | 0 ✅ |
| report 委托 | `report --run-id RUN-X --message-file result.txt` | 输出 delegate 指引文档（不执行） | 0 ✅ |

与实现者声称全部一致。

---

## 4. 越权与红线核查：PASS

### 4.1 git 层面（worktree `b1`，分支 v1.1-blackbox）

- `git status`：R3 交付 3 文件均为 **untracked（新增，非修改）**：`runtime/blackbox_bridge.py`、`runtime/test_blackbox_bridge_offline.py`、`docs/ops/blackbox-card.md` ✅
- 其余 untracked（`config/capability-registry.json`、`docs/evidence/HANDOFF-INDEX.md`、`docs/ops/registry-validate.py`）经内容头核验为 **R2（software-engineer-r2）/主会话产物**，非 R3 新增；`docs/DECISION_LEDGER.md` 的 modified 为 **R1 D022 未提交条目**（内容核验为 R1 开工记录），非 R3 改动 ✅
- worktree `runtime/runtime.py` 无 git modified（未被 R3 触碰）✅

### 4.2 生产 runtime 目录（E:\WB\tools\ai-production-control\runtime\）

- `runtime.py` mtime = **2026-08-23 16:23**，早于 R3 施工（2026-08-30 23:5x）；未被触碰 ✅
- `run.cmd` mtime = 2026-08-18；未被触碰 ✅
- **结论：R3 未触发"必须改生产 runtime.py 结构"红线** ✅

### 4.3 凭据硬编码核查

- `grep -iE "credential|session|token|api_key|secret|password|r_url" runtime/blackbox_bridge.py`：仅 docstring 用法示例（L11）、委托占位符（L312）、参数定义（L357）三处**字面引用**，无任何真实 URL/凭据内容复制 ✅
- `docs/ops/blackbox-card.md`：无 credential/token/secret/password 字样；仅**路径引用** `E:\执衡\05_资源\会话注册.json`（该路径实测存在），且明确"只读 URL 字段；不要复制" ✅
- **结论：允许路径引用、无内容复制，符合红线** ✅

---

## 5. 可演进性：PASS（附建议）

### 5.1 human-gate 机械判定规则合理性

规则（`_classify_run`，L201-239）：
- `HARD_BLOCKED`/`PAUSED` → waiting ✅
- `effect_human_gate_required=true` → waiting ✅
- `STOPPED` → terminal（不计 waiting）✅
- 其余（DONE/RUNNING）→ 不介入 ✅

**判定：合理**。全部依据 state.json 机械事实，不猜；真实数据验证（12 waiting / 6 terminal 与独立扫描一致）；STOPPED 单列 terminal 避免"用户已裁决仍催办"的误报；`blocked_reason`/`next_action` 作为 reason 原文呈现，弱 AI 可原样转发。

### 5.2 显式 HUMAN_GATE 状态的可扩展性建议（1-2 句）

判定集合已集中为 `_GATE_STATUSES`/`_TERMINAL_STATUSES` 模块级常量，扩展点清晰：未来宪法若要求显式 `HUMAN_GATE` 状态，**只需在 `_GATE_STATUSES` 增加一项**（或复用 `effect_human_gate_required` 布尔字段的语义扩展），CLI/输出结构无需改动。建议把"need 文案生成"进一步抽成独立映射函数，使状态→文案与状态→分类解耦，便于后续新增状态时一处维护。

---

## 6. 缺陷清单与观察项

### 6.1 缺陷（低危，不阻塞会签，列入后续修复）

**[D1] work 委托层忽略用户传入的 `--r-url`，输出硬编码占位符**
- 位置：`runtime/blackbox_bridge.py` L310-312（`if sub == "work": parts.append("--r-url <R会话URL>")`）；参数定义 L357（`p_work.add_argument("--r-url", ...)`）
- 复现：`python runtime\blackbox_bridge.py work --goal-file goal.txt --r-url https://example.invalid/session` → invocation 输出 `--r-url <R会话URL>`，**用户真实 r-url 被丢弃**
- 影响：弱 AI 若经桥委托 work，会拿到字面占位符命令，触发 run.cmd `MISSING_R_URL`/`INVALID_R_URL`。缓解：blackbox-card.md 教弱 AI 直接调 run.cmd（不经桥），实际主路径未受影响
- 修复建议：透传 `args.r_url`（且加引号包裹），或直接删除该参数避免误导

### 6.2 观察项与建议（不阻塞）

1. **[观察] worktree runtime/runtime.py 与生产 runtime.py 哈希不同**（worktree=0a7ea257… 对应 git 提交 fd99281 v0.6/r22；生产=1def0118…，diff 443 行）。为**既有差异**（worktree 副本停留在 v0.6/r22 提交，生产为后续部署版本），非 R3 引入；不影响桥的正确性（桥只读状态根、不读 runtime.py 代码），但提示：后续若需对齐生产 runtime.py 行为，应以生产版本为准
2. **[建议] delegate 输出 `ok=True` 可能被弱 AI 误解为"命令已执行"**（实测输出 `ok: true` + `command: WORK`，仅 instruction 说明"由生产 run.cmd 执行"）。建议增加 `"executed": false` / `"action": "INSTRUCTION_ONLY"` 显式字段，消除语义陷阱
3. **[小瑕疵] `cmd_result` L165 `final` 表达式第二条件冗余**：`(effective_verdict == "PASS" and status == "DONE")` 已被 `status in ("DONE", "STOPPED")` 覆盖；不影响结果正确性（实测 PASS/REWORK 输出正确）
4. **[小瑕疵] `_delegate` invocation 拼接未给路径加引号**（如 `--goal-file {args.goal_file}`），路径含空格时会碎；因是指引字符串非执行语句，弱 AI 可自行处理，低危

---

## 7. 最终判定

# APPROVED（有条件）

- 核心交付（RESULT / HUMAN_GATE 只读查询 + 14 离线测试 + §71 一页操作卡）架构正确：与既有桥模式一致、纯只读、退出码约定兼容、状态根读取与真实布局吻合、亲跑全部复现通过
- 双 runtime 红线未触发：生产 runtime.py/run.cmd 未被触碰，R3 仅新增 3 文件，无凭据硬编码
- 附带条件：缺陷 **D1（work 委托层 r-url 参数被忽略）** 列入后续修复清单；建议项（executed 显式标记、文案映射解耦）在后续迭代采纳
- 审核者确认：本审核为只读，未修改受审文件，未 push

---

*审核记录：高见远（software-architect），2026-08-30。会签后由主理人汇总；本报告存于 docs/evidence/reviews/REVIEW-R3-2026-08-30-ARCH.md。*
