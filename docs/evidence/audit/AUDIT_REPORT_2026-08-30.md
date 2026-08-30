# 执衡 v0.9-b1 第二团独立审计报告

**日期**：2026-08-30
**工作流**：独立审计（章程 `SECOND_TEAM_AUDIT_PACK.md` §2 必审清单 16 项）
**审计对象**：`v0.9-b1/authority-effect-core` @ `52cbc614`（HEAD == `origin/v0.9-b1/authority-effect-core`，落后/领先 0/0）
**审计者**：第二团独立审计者（与施工团异源）
**权限**：只读；本次唯一写入 = 本报告 + 台账 D019 一行

---

## 📌 TL;DR（执行摘要）

- **整体结论**：16 项中 **15 项 PASS、1 项 REWORK、0 项 BLOCKED**。无锚点级问题，无越权改动，无状态造假嫌疑。
- **严重度分布**：🔴严重 0 项 / 🟠高 0 项 / 🟡中 2 项（真实 GOAL 计数口径不一致、R 审查轮次口径不一致）/ 🟢低 2 项（术语口径、陈旧记录）
- **阻塞 / 非阻塞**：唯一 REWORK 项（§2-8 真实 GOAL 计数）为**记录偏差**，**非实质缺陷**——点名的 5 个真实 GOAL 经实测**全部 DONE+PASS**，实质成立。
- **核心判断**：施工团的工程判据（矩阵 36/36、CLOSE 40 全绿、egress 11/11、doctor 零新增漂移）**经我亲手复跑全部为真**；77 节自评矩阵**未注水**（✅38/🟡34/❌1，非全绿）。
- **§74 签字建议**：**不建议直接签**，需先统一三处计数口径（详见文末）。

---

## 🎯 核心结论卡片

| 项目 | 内容 |
|------|------|
| 整体评级 | 🟡 **AUDIT_PASS_WITH_REWORK** |
| 阻塞项数量 | 0 |
| REWORK 项数量 | 1（§2-8 记录偏差） |
| 无法验证项 | 5 条（20 条自我攻击中的历史事件类，见 §2-10） |
| 总判定 | **AUDIT_PASS_WITH_REWORK** |
| 建议下一步 | 统一"真实 GOAL 次数"与"R 轮次"两处口径并回写 → 业主 §74 裁决 |

---

# 一、逐项审计结论（§2 必审清单 16 项）

## A. 完整性锚点

### §2-1 宪法与章程哈希复算 —— ✅ PASS

| 文件 | 期望值 | 实测值 | 结论 |
|---|---|---|---|
| 宪法 `docs/canon/ZHIHENG_FINAL_DEFINITION_FINAL_CANONICAL.md` | `4c05a21f...243f4a9a4` | `4c05a21fab1543a209cafd70fee48752e996cf3a77df2987f316dde243f4a9a4` | ✅ 一致（裸 SHA256） |
| 章程 v4.4 | `769c7c62...6c7440fe` | `769c7c62a2b0e09b206e0915fc8a49c5f9d77dd868fca8421b261fab6c7440fe` | ✅ 一致（按章程口径） |
| 主脑裁决书（附带核验） | D018 记 `4a98499b...afcc33fc` | `4a98499b4690dc79e0262afe1fd4b71190ba79430b0a8a2846d15758afcc33fc` | ✅ 一致 |

**⚠️ 审计方法学要点（防误判，务必保留）**：
章程对整文件取裸 SHA256 得 `1dec34570979915b46214d1b1825d09bfaa4440586ae7d989abd9b2224d6ad0c`，与身份行**不符**。
但章程 §0 明文规定统计口径为「**除去以 `章程身份行：` 开头的行**，CRLF 归一为 LF」。按其自带校验脚本复算即得 `769c7c62...`，**完全匹配**。
→ **此为口径差异，非篡改**。任何后续审计者若直接对文件取裸哈希将得出错误的 BLOCKED 结论，特此留痕。

附带核验：仓内裁决书与审计包原件 `cmp` 结果 **逐字节 IDENTICAL**，入仓无篡改。

### §2-2 `state_doctor.py` 实测 —— ✅ PASS

原始输出：
```
WARN: journal staleness | updated_at=2026-08-17 but latest commit=2026-08-30 (>7 days): docs lagging code
DRIFT: registered head mismatch | expected=v0.9-b1/authority-effect-core@c6d1a55b | actual=v0.9-b1/authority-effect-core@52cbc614
DRIFT_COUNT=1
```

核验过程（全部亲手执行）：
- `git rev-parse --short HEAD` = `52cbc61`；`origin/v0.9-b1/authority-effect-core` = `52cbc61`；`git rev-list --left-right --count` = `0  0` → **本地与远端完全一致**
- `git merge-base --is-ancestor c6d1a55b HEAD` → **YES** → registry 记录的是**更旧**的提交，确系「registry b1-head **滞后**」
- 豁免有**书面裁决**：`BUILDER_RULING_TIER2.md` §4「doctor registry 滞后 DRIFT：裁决定性」定性为「已裁决的预期漂移」；章程 §205-206「当前唯一豁免项 = registry b1-head 滞后……**不得"修复"该豁免项**」；`BUILDER_RULING_T11B.md` §5 同

→ 除豁免项外**零漂移**，符合要求。
附带说明：`WARN: journal staleness` 不计入 `DRIFT_COUNT`，属文档债（journal 停在 8-17 vs 最新提交 8-30），不构成漂移，但建议后续补齐。

### §2-3 PROJECT_STATE 关键字段 —— ✅ PASS

```
release_status                        = 'PRODUCT_NOT_READY'
evidence_registry[0].release_status   = 'PRODUCT_NOT_READY (unchanged)'
current_stage                         = 'PHASE_0'
generated_at                          = '2026-08-28'
```
- `git log -p --all -S"PRODUCT_READY" -- PROJECT_STATE.json` → **零命中** → **无任何未裁决晋升** ✅
- 工作树 `git status --porcelain -uall` 为空 → 无未提交的越权改动

---

## B. 测试真源（全部亲手复跑）

### §2-4 v09 攻击矩阵 —— ✅ PASS

命令：`python runtime/test_v09_attack_matrix_on_b1_core.py`（Python 3.12）

实测输出（关键行）：
```
"case_count": 36,
"matched": 36,
V09-R33   exp=FAIL_CLOSED  obs=FAIL_CLOSED  MATCH
V09-R34   exp=FAIL_CLOSED  obs=FAIL_CLOSED  MATCH  | AD-7 closed at issuance_side(store.grant_authorization): GateDenied: effect_type is outs...
V09-R35   exp=NO_BYPASS    obs=NO_BYPASS    MATCH
V09-R36   exp=DENY         obs=DENY         MATCH
V09-R34-FAITHFUL  exp=FAIL_CLOSED  obs=FAIL_CLOSED  MATCH  | closed at issuance_side(store.grant_authorization): GateDenied: effect_type is outside t...
```
- **36/36 全部 MATCH**，`MISMATCH` 行计数 = **0**
- **V09-R34 = FAIL_CLOSED** ✅；**V09-R34-FAITHFUL = FAIL_CLOSED** ✅（章程要求的双路径均达成）

**附加真实性核验**：审计中曾怀疑 R34-FAITHFUL 探针存在"硬编码 observed_outcome"。逐行审读 `runtime/test_v09_attack_matrix_on_b1_core.py:294-334` 后确认：该探针为**真实三分支执行**（① `grant_authorization` 抛异常 → FAIL_CLOSED；② `execute` 抛异常 → FAIL_CLOSED；③ 端到端放行 → ALLOW / matched=False）。**怀疑不成立，探针为真**，特此留痕。

### §2-5 CLOSE 五件套 + egress 四件套 —— ✅ PASS

**CLOSE 五件套**（`cd tests` 逐个运行，Python 3.12，无 pytest）：

| 文件 | 结果 |
|---|---|
| `test_v09_close_classification.py` | `Ran 9 tests ... OK` |
| `test_v09_close_fence.py` | `Ran 11 tests ... OK` |
| `test_v09_close_reconcile.py` | `Ran 8 tests ... OK` |
| `test_v09_close_role_binding.py` | `Ran 7 tests ... OK` |
| `test_v09_close_unknown_gate.py` | `Ran 5 tests ... OK` |

合计 **40 项全绿**，与台账「CLOSE 40 全绿」**数字吻合** ✅

**egress 四件套 —— 口径澄清（重要）**：
仓库中**不存在 4 个独立的 egress 测试文件**。经查证，所谓"四件套"实为 **egress 四向负例**，集中于单一文件 `runtime/test_v09_close_egress_wiring_offline.py`（11 例）。
实测：`Ran 11 tests in 0.805s / OK`，四个负例方向均在内且通过：
- `test_policy_absent_denies`（策略缺失）
- `test_empty_policy_denies`（`{}` 空策略）
- `test_other_destination_policy_denies`（其他目的地）
- `test_projection_bound_to_contract_hash_and_fail_closed_when_stale`（契约哈希陈旧）
- 另有正例 `test_permitted_policy_allows_and_records`（**证明该闸门非"恒假"**）等共 11 项

→ 功能上**通过**。但建议后续将审计章程序列中的"egress 四件套"表述与仓库实际口径（1 文件 4 负例方向）对齐，避免审计歧义。（记为 🟢 低优先）

### §2-6 抽查 3 个新增特性套件 —— ✅ PASS

| 套件 | 文件 | 实测 | 台账声称 | 一致性 |
|---|---|---|---|---|
| brain_bridge | `runtime/test_brain_bridge_offline.py` | `Ran 10 tests ... OK` | "10 测试绿" | ✅ 一致 |
| capsule_bridge | `runtime/test_capsule_bridge_offline.py` | `Ran 13 tests ... OK` | "9 测试绿"（D017） | ⚠️ 实测 13（数量已增长） |
| taskgraph | `runtime/test_taskgraph_offline.py` | `Ran 2 tests ... OK` | — | ✅ |

三者均通过。capsule_bridge 计数从 9 增长至 13，属**陈旧记录**（非缺陷，通过数只增不减）。（记为 🟢 低优先）

---

## C. 真实 GOAL 证据链（防"纸面完工"）

### §2-7 抽 3 个 RUN 核对 —— ✅ PASS

**路径澄清**：RUN 实际位于 `E:\WB\state\ai-production-control\runtime-v1\runs\`，审计章程所写 `E:\WB\state\...\runs\` 省略了 `runtime-v1` 一层。此处无异常，仅口径注明。

**重点 RUN：`RUN-20260830-000926-cfb5`**（章程点名，多轮 REWORK）

| 校验项 | 实测值 | 判定 |
|---|---|---|
| `status` | `DONE` | ✅ |
| `last_r_verdict` | `PASS` | ✅ |
| `metrics` 存在 | 存在（`r_roundtrips=9`, `r_wait_time_sec=707.7`, `started_at`/`finished_at` 俱全） | ✅ |
| reply 文件含 `===REVIEW_VERDICT===` | **9/9 个 reply 文件全部命中** | ✅ |

- `revision = 12`，`review_epoch = 1`，目录下含 9 组 `msg_/report_/reply_` 三件套 → **确为真实多轮 REWORK 闭环**
- 末次 reply 全文：`===REVIEW_VERDICT=== PASS` + `===CHATGPT_DONE:WB_20260830_002614_2595727491===`
- 中途 reply 示例：`===REVIEW_VERDICT=== REWORK` + `===NEXT_ACTION=== 修订报告：严格按四类分别覆盖 3–5 个项目……`（真实纠偏指令，非空转）

**另核 4 个真实 GOAL RUN**（全部 DONE + PASS）：

| RUN | status | verdict | r_roundtrips | revision | reply 中 REWORK / PASS |
|---|---|---|---|---|---|
| `RUN-20260829-235240-ff88` | DONE | PASS | 1 | 4 | 0 / 1 |
| `RUN-20260830-000149-41b4` | DONE | PASS | 5 | 8 | 4 / 1 |
| `RUN-20260830-000926-cfb5` | DONE | PASS | 9 | 12 | 8 / 1 |
| `RUN-20260830-004944-c33e` | DONE | PASS | 1 | 4 | 0 / 1 |
| `RUN-20260830-010247-37d9` | DONE | PASS | 1 | 4 | 0 / 1 |

→ **三环齐全，证据链完整。PASS。**

### §2-8 "8 个真实 GOAL 全 PASS" 与 RUN 实际数量核对 —— ⚠️ REWORK（记录偏差）

**实测（`runtime-v1/runs/` 全量扫描）**：
- RUN 目录总数：**118**；其中含 `state.json`：**117**（`RUN-20260818-rtv1` 为 8-18 早期冒烟目录，仅 2 个 txt，无 state.json，不计入 GOAL 口径）
- `status` 分布：`DONE 63` / `RUNNING 36` / `HARD_BLOCKED 10` / `STOPPED 6` / `PAUSED 2`
- `last_r_verdict` 分布：`PASS 84` / `REWORK 8` / `BLOCKED 4` / `None 21`
- **DONE 且 PASS = 63**

**声称数字四处不一致**：

| 来源 | 声称 |
|---|---|
| 审计章程 §2-8 | **8** 个真实 GOAL |
| `PROJECT_STATE.md:19` | **5** 次真实 GOAL 全 PASS |
| `PROJECT_STATE.md:25` | **5** 次真实 GOAL 全 PASS（RUN-ff88/41b4/cfb5/c33e 等） |
| `docs/evidence/V1.0-CLOSE-OUT-REPORT-20260830.md:35` | **4** 次真实 GOAL 全 PASS（§69） |
| `docs/evidence/stream-d/MATURITY_REPORT.md` | 连续 **3** 次真实 GOAL 全绿 |

**实质核验**：点名的 5 个真实 GOAL（ff88 / 41b4 / cfb5 / c33e / 37d9）经实测 **全部 DONE + PASS** → **"5 次"这一说法的实质成立**。

**判定**：按章程「数字不符 = 记录偏差，不猜原因」，判 **REWORK**。
- 偏差性质：**记录层**，非实质层——被测对象本身真实且通过。
- **不推测成因**（章程明令）。仅陈述：实际可点名的真实 GOAL PASS 数为 **5**；章程所述 **8** 与仓库各处 **5/4/3** 互不一致。
- 附带：`RUNNING 36` 与 `HARD_BLOCKED 10` 表明状态根中存在大量未收敛 RUN，若"真实 GOAL"口径指向全量 RUN，则与"全 PASS"相差更远。**建议业主明确"真实 GOAL"的定义边界**（是否限定为某批次/某时间窗/某 worker_identity）。

---

## D. 自评矩阵复核（抠水分）

### §2-9 77 节自评矩阵自选复核 —— ✅ PASS（矩阵诚实，未注水）

**原件定位（澄清）**：`docs/evidence/DEFINITION-77-SECTIONS-FINAL.md`（v3，2026-08-30，§0-§76 全覆盖，73 数据行，含合并行如 `§8/§9`、`§46/§47`、`§52/§53`）。
注：该文件并非以 `## §N` 标题组织，而是**表格行**（`| §N | ... |`）；以标题数统计会误判为"仅 8 节"，特此留痕。

**实测评级分布（Python 精确统计，非 grep）**：
```
✅ 完全满足    38
🟡 部分满足    34
❌ 未满足       1
（数据行 73；节号覆盖 §0-§76，无缺失——§9/§26/§47/§53 均以合并行形式覆盖）
```
→ **并非"全绿"**。自评矩阵整体**诚实**，未发现系统性注水。

**章程硬性指定的四节**：

| 节 | 自评 | 实测证据 | 判定 |
|---|---|---|---|
| **§56** 多 Worker | 🟡 | 「parallel skill 存在（2-10 路验证）但**未真实并行跑过生产任务**（C-3 降级）」 | ✅ 诚实，未注水 |
| **§63** Capability Registry | 🟡 | 「手册入仓 ≠ 机器可读注册表（C-3 降级）」 | ✅ 诚实 |
| **§65** 唯一入口 | 🟡 | 「run.cmd 四动词不齐（C-3 降级）」 | ✅ 诚实 |
| **§68** 自举 | 🟡 | 「V1.0 后启动」 | ✅ 与章程"预期应为未满足"一致，**未**虚标为 ✅ |

**关键节 §74**：**❌**「工程项达成，业主裁决待定」——这是本次审计最重要的锚点：
> 工程判据（矩阵/CLOSE/egress/doctor）的达成，**本身不等于 §74 FINAL DONE**。§74 需业主裁决。

**自选补充复核（共 10 节，超出章程要求的下限）**：

| 节 | 自评 | 独立核验 | 判定 |
|---|---|---|---|
| §7 Brain | ✅ | 实测 `test_brain_bridge_offline.py` = 10 tests OK，与"brain_bridge 10 测试"一致 | ✅ 属实 |
| §10 Worker | ✅ | 实测 5 个真实 GOAL 均 DONE+PASS，与"5 次真实 GOAL"一致 | ✅ 属实 |
| §12 R 独立审查 | ✅ | 记「6 次真实 R 审查（**11 轮 REWORK**）」；实测 5 个真实 GOAL 共 **17 次 R 往返 / 12 次 REWORK 判定 / 5 次 PASS** | ⚠️ **数字不符**（见下） |
| §48-§51 | 🟡×4 | 自评"只有雏形/评估"，与自我攻击 #19 一致 | ✅ 诚实 |
| §59-§62 | 🟡×4 | 同上 | ✅ 诚实 |

**§12 子发现（🟡 中优先）**：矩阵记「11 轮 REWORK」，`MATURITY_REPORT` 亦记「11 轮 REWORK 全部整改后 PASS」；实测 5 个真实 GOAL 的 reply 中 REWORK 判定共 **12** 次（0+4+8+0+0）。**数字不符**，与 §2-8 同属计数口径问题。不推测成因（可能口径为"整改完成轮次"或快照时点不同）。

### §2-10 20 条自我攻击逐条对账

原件：`docs/evidence/SUCCESSOR-TRUTH-AND-20-SELF-ATTACKS.md` 第四部分（§59-§91）

| # | 攻击内容摘要 | 判定 | 依据 |
|---|---|---|---|
| 1 | "V1.0 判据达成"夸大，两套标准混用 | **属实（已整改）** | B-5 勘误已落地，commit `98a70a0`，6 处加注 |
| 2 | "44 节完全满足"有水分；§56 非真实并行 | **属实（已整改）** | C-3 降级；实测 §56=🟡；当前分布 38✅/34🟡/1❌ |
| 3 | §68 自举完全没做 | **属实（已如实标注）** | 实测 §68=🟡「V1.0 后启动」，未虚标 |
| 4 | 真实 GOAL 全手动驱动、中继无自动调度 | **属实** | `active_run.txt`=37d9（已 DONE）；`watcher-heartbeat.json` `phase_state=COMPLETED`、mtime `2026-08-30 01:42`（审计时 17:18，陈旧 ≈15.6h） |
| 5 | Brain 拆解只是正则规则 | **无法验证** | 未逐行审计拆解算法；间接证据 §17=🟡「依赖图未完整」 |
| 6 | 只验证 2 类目标且都是单轮 | **部分不属实** | "单轮"被证伪：cfb5 实测 9 轮、41b4 实测 5 轮多轮 REWORK。"多步大目标未测"部分仍成立（§3=🟡） |
| 7 | 本地资产只登记未融入 | **无法验证** | 未逐项核对 `docs/ops/` 调用索引与实际接线 |
| 8 | 能力手册入仓是说明书不是接入 | **属实（已整改）** | §63 经 C-3 降为 🟡 |
| 9 | 本地链恢复是表面恢复，无 Worker 挂上去跑生产 | **属实** | 同 #4：心跳 COMPLETED 且陈旧，无活跃生产任务 |
| 10 | 丢过上下文，§26 会话隔离未执行 | **无法验证** | 历史会话事件，无原件可查 |
| 11 | 一度误判"项目没开发过" | **无法验证** | 历史，无原件 |
| 12 | 漏了 7 节定义（v1 只有 70 节） | **已整改** | v3 矩阵 §0-§76 全覆盖（§46/§47、§52/§53 等为合并行），无缺失节 |
| 13 | "32 节完全满足"数字不一致，汇报数字不可全信 | **属实，且本次审计再次证实** | 本次实测又发现：真实 GOAL 次数 8/5/4/3 四处不一致；REWORK 轮次记 11 vs 实测 12 |
| 14 | 恢复中继时未做完整 §11 自检 | **无法验证** | 历史，无原件 |
| 15 | PROJECT_STATE 曾漂移；registry b1-head 豁免 | **属实** | 实测 `DRIFT_COUNT=1`；registry=`c6d1a55b` vs HEAD=`52cbc614`；祖先关系已确认；豁免有 `BUILDER_RULING_TIER2` §4 书面裁决 |
| 16 | TCB 封印未执行，无权威完整性锚点 | **属实** | E1 裁决封印后置；实测 `release_status=PRODUCT_NOT_READY` |
| 17 | egress 恒假缺陷、修复在 runtime/ 未动、真问题还在 | **不属实（已解决）** | `src/aicontrol/security.py:190-220` `egress_allowed` 为**真实策略判定**，末行 `return True`（非恒假）；egress 11/11 OK，含正例 `test_permitted_policy_allows_and_records`；`runtime/effect_safety_lite.py` 委托该函数 |
| 18 | 多 Worker、Stable/Candidate 端到端从未真实跑过 | **属实** | §56=🟡，与 #2 同一问题 |
| 19 | Supply Chain/Cost Routing/Hard Fuse 只有雏形 | **属实** | 实测 §48/49/50/51/59/60/61/62 全为 🟡，与自评一致 |
| 20 | 本报告本身也可能误导，须复核 | **属实（元命题成立）** | 本次独立审计确在第 13 条同类问题上再次发现记录偏差 |

**统计**：属实 11（其中 #1/#2/#3/#8/#12 已整改）、不属实 1（#17）、部分不属实 1（#6）、无法验证 5（#5/#7/#10/#11/#14）。

---

## E. 主脑裁决执行情况

### §2-11 B-5 勘误 —— ✅ PASS

- 提交 `98a70a0` 真实存在：「docs(b-5): errata — annotate V1.0 criteria claims as engineering criteria (§10), not §74 FINAL DONE」
- 加注措辞为「**工程判据（章程 §10），非定义 §74 FINAL DONE**」（注：直接检索"工程判据非 §74"会零命中，须用实际措辞检索）
- **实测落地 6 处**，与声称的「stream-d ×5 + CLOSE-OUT ×1」**精确吻合**：
  - `docs/evidence/stream-d/MATURITY_REPORT.md` × 3（第 9、47、59 行）
  - `docs/evidence/stream-d/RESULT_BLOCK.md` × 2（第 13、38 行）
  - `docs/evidence/V1.0-CLOSE-OUT-REPORT-20260830.md` × 1（第 63 行）

### §2-12 G-2 ROADMAP 详版入仓 —— ✅ PASS

- 提交 `d0fb3bd`：「docs(g-2): ingest ROADMAP detail version (MAINBRAIN B6 approved) + PROJECT_STATE registry」
- 文件：`docs/governance/ROADMAP-V0.9到V1.0收口路线.md` —— **346 行 / 24,196 字节**，确为详版（非概要/存根）

### §2-13 C-1 沙箱破坏演练 —— ✅ PASS

- 提交 `6b82db8`；证据文档 `docs/evidence/stream-d/RECOVERY-DRILL-C1-20260830.md`
- 沙箱 `E:\WB\temp\sandbox-recovery-20260830\` **实存**（含 `cli_log.jsonl` + `runs/`，创建于 8-30 16:54-16:55）
- **生产状态根未被触碰 —— 硬证据**：
  ```
  find "E:/WB/state/ai-production-control" -newermt "2026-08-30 16:00"   →  返回空
  ```
  状态根内最新 mtime 为 `2026-08-30 01:02`（`runtime-v1/runs`），**远早于**演练时点 16:54。→ 演练确在沙箱内进行，符合「禁碰生产状态根」裁决。

### §2-14 C-3 矩阵 v3 把 §63/§65/§56 降为 🟡 —— ✅ PASS

- 文件头明示：「**v3 修正**（主脑裁决 C-3，继任者自攻 #2 成立）：§56、§63、§65 由 ✅ 降为 🟡」
- 实测三节当前评级：
  ```
  | §56 | 多 Worker          | 🟡 | parallel skill 存在（2-10 路验证）但未真实并行跑过生产任务（C-3 降级） |
  | §63 | Capability Registry| 🟡 | 手册入仓 ≠ 机器可读注册表（C-3 降级） |
  | §65 | 唯一入口           | 🟡 | run.cmd 四动词不齐（C-3 降级） |
  ```
- 三节**均已降为 🟡**，确为 v3 版。**PASS。**

### §2-15 P0 备份落地 —— ✅ PASS

```
E:\WB\backups\
  drwxr-xr-x  ai-production-control-P0_BACKUP-20260830-1700    2026-08-30 16:52
  drwxr-xr-x  ai-production-control-PRE_TAKEOVER_BACKUP-20260817-1750   2026-08-17 19:11
```
P0 备份目录**实存**，时间戳与本批执行时点吻合。

### §2-16 W-1 生产接线方案 —— ✅ PASS

- 文件：`docs/ops/W1-MINIMAL-WIRING-PLAN.md`（69 行 / 5,068 字节），标题即声明「（只出方案，不施工）」
- **"只方案未施工"硬证据** —— 提交 `467d2a9` 改动范围：
  ```
  docs/ops/ROTATION-CHECKLIST-S02-S03-S06.md | 66 ++++++++++
  docs/ops/W1-MINIMAL-WIRING-PLAN.md         | 69 ++++++++++
  2 files changed, 135 insertions(+)
  ```
  **仅新增 2 个 md 文件，零代码改动、零删除** → 确未施工 ✅
- **Reuse Gate**：方案 §3 标题即「方案骨架（**Reuse Gate 先行**——逐项复用已有资产，零重造）」，并明列「**Reuse Decision**：R=Reuse（复用已实现的 grant_authorization 函数 + 既有效力存储结构）」
- 附注：方案本身标注「待主脑审」，且列有 3 点待裁决项（tcb-verify/grant-auth 动词形态、tcb_verified 落点、config 自哈希）——**未自裁定案**，符合裁决要求。

---

# 二、汇总

## ✅ 行动清单（按优先级）

| # | 行动 | 负责角色 | 紧急度 | 预期产出 |
|---|------|---------|--------|---------|
| 1 | **统一"真实 GOAL 次数"口径并回写**：当前 8（章程）/5（PROJECT_STATE×2）/4（CLOSE-OUT）/3（MATURITY）四处不一致；实测点名 GOAL 为 5 个且全 PASS | 施工团 + 业主确认口径 | **P0** | 一处权威数字 + 其余文件引用该数字 |
| 2 | **统一 R 审查 / REWORK 轮次口径**：矩阵与 MATURITY_REPORT 记 11，实测 5 个真实 GOAL 的 reply 中 REWORK 判定为 12 | 施工团 | **P0** | 明确"轮次"定义（R 往返数 / REWORK 判定数 / 整改完成数）后回写 |
| 3 | **补齐 journal staleness**：`state_doctor` 持续 WARN（journal 停 8-17 vs 最新提交 8-30） | 施工团 | P1 | WARN 消除或登记为已知豁免 |
| 4 | 对齐审计术语："egress 四件套" 实际为 1 文件内 4 个负例方向 | 业主/主脑 | P2 | 章程与仓库口径一致，避免后续审计歧义 |
| 5 | 更新 capsule_bridge 测试计数（D017 记 9，实测 13） | 施工团 | P2 | 台账数字刷新 |
| 6 | 明确"真实 GOAL"定义边界（按批次/时间窗/worker_identity），以便与状态根 118 个 RUN 中的 RUNNING 36 / HARD_BLOCKED 10 区分 | 业主 | P1 | 书面口径定义 |

## ⚠️ 待完善 / 已知局限

1. **20 条自我攻击中有 5 条无法验证**（#5/#7/#10/#11/#14）：均为历史事件或需逐行代码审计的项，无原件可查或超出本次审计范围。**未做任何推测**，如实标注。
2. **未审计范围之外的内容**：严格限定于章程 §2 的 16 项，未扩大。
3. **未验证项**：`docs/ops/` 本地资产调用索引的实际接线程度（自我攻击 #7）、`brain_bridge.py` 拆解算法的智能程度（自我攻击 #5）。
4. **观察项（非缺陷）**：施工 worktree 根目录存在未跟踪残留目录 `tmpm8v1c53r/`（8-28 20:08，含 `s/c.db` + `s/snapshots/revision-00000001.json`）。工作树 `git status` 干净，该目录内容被 `.gitignore` 的 `*.db` 等规则覆盖，**不影响任何跟踪文件，不构成越权改动**。仅提示清理。
5. **方法论留痕（供后续审计者）**：
   - 章程哈希**必须**按其 §0 自述口径（剔除身份行 + LF 归一）复算，裸哈希会误判 BLOCKED；
   - 77 节矩阵为**表格行**结构，按 `## §N` 标题统计会误判；
   - RUN 真实路径为 `...\runtime-v1\runs\`，非 `...\runs\`；
   - B-5 加注实际措辞为「工程判据（章程 §10），非定义 §74 FINAL DONE」，检索"工程判据非 §74"零命中；
   - egress "四件套" = 1 文件内 4 个负例方向，非 4 个文件。

## 📚 数据来源 & 成员产出索引

本次审计 **16 项结论全部由审计者亲手复跑/原件核验得出**，未采信施工团任何自述结论。

- 施工 worktree：`C:\Users\17838\Documents\Qoder\2026-08-28\031cb4e3\b1` @ `52cbc614`
- 状态根原件：`E:\WB\state\ai-production-control\runtime-v1\runs\`（118 个 RUN 目录全量扫描）
- 备份原件：`E:\WB\backups\ai-production-control-P0_BACKUP-20260830-1700`
- 沙箱原件：`E:\WB\temp\sandbox-recovery-20260830\`
- 关键核验提交：`98a70a0`(B-5) / `d0fb3bd`(G-2) / `6b82db8`(C-1) / `467d2a9`(W-1)
- 环境：Python 3.12（`C:\Users\17838\AppData\Local\Programs\Python\Python312\python.exe`），无 pytest；`cd tests` / `runtime` 下脚本方式运行

---

# 三、总判定与 §74 签字建议

## 总判定：**AUDIT_PASS_WITH_REWORK**

- 无 🔴 BLOCKED 项（哈希全符、无越权改动、无状态造假嫌疑）
- 15/16 项 PASS，实测证据充分（矩阵 36/36、CLOSE 40/40、egress 11/11、特性套件 25/25、doctor 零新增漂移）
- 1 项 REWORK（§2-8 真实 GOAL 计数记录偏差），+ 1 项同类子发现（§12 REWORK 轮次计数）
- 两者**均为记录层偏差，非实质缺陷**：被测对象真实且通过

## §74 签字建议：**暂不建议签字 —— 补两项计数口径后可签**

**可以签字的理由**（已由我亲手验证为真）：
- 工程判据（矩阵 36/36、CLOSE 40 全绿、egress 四向负例 + 正例、三特性套件全绿、doctor 除豁免项零漂移）**全部实测通过**
- 主脑裁决 B-5/G-2/C-1/C-3/P0/W-1 **六项全部执行且有硬证据**（提交号 + 文件 + 时点）
- 77 节自评矩阵**未注水**：✅38/🟡34/❌1，§56/§63/§65 已按 C-3 降级，§68 自举如实标 🟡
- 真实 GOAL 证据链**完整**：cfb5 等 5 个 RUN 均 DONE+PASS，reply marker 9/9 齐全，多轮 REWORK 为真实闭环
- release_status 维持 `PRODUCT_NOT_READY`，**无未裁决晋升**

**建议先补的两项（均为 P0，工作量极小，纯文档口径统一）**：
1. 统一"真实 GOAL 次数"（8/5/4/3 → 一处权威数字）
2. 统一"R 审查 / REWORK 轮次"（11 vs 实测 12 → 明确定义后回写）

**补完即建议签字。**

**签字时须同时明确的边界**（矩阵 §74 已如实标 ❌「工程项达成，业主裁决待定」）：
> 本次审计通过的是**工程判据**（章程 §10 口径）。按定义 §74，**FINAL DONE 必须由业主裁决**，且"任何单一角色声称完成均无效"。本报告不构成有效性宣告。
>
> 另需注意北极星未达成：D018 记载的「自动调度闭环——至少 1 个真实任务由系统自身完成 提交→拆解→调度→执行→审查→REWORK/PASS→交付，全程无人手动敲 work/report」——实测 `active_run.txt` 指向已完成的 37d9、`watcher-heartbeat.json` `phase_state=COMPLETED` 且陈旧约 15.6 小时，**自动调度闭环尚未达成**，与该目标相关的"系统可自动生产"宣称不应成立。

---

> 本报告由第二团独立审计者生成，全部结论基于亲手复跑与原件核验。
> 关键决策请由业主（人类）复核后裁决。
