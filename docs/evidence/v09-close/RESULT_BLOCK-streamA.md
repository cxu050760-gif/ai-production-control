# RESULT BLOCK — 流 A｜V0.9 CLOSE 代码收口（收口结果块）

- 收口时间：2026-08-29 · 主理人：齐活林（Qi）· 团队：software-zhiheng
- 依据：章程 v4.4 §4 流 A / §9 汇报协议；BUILDER_RULING_FINALBATCH（三门链已闭环）
- 主提交：`c464190fae2d5a5e166bb5c7380a6f642359b14b`（已推送 origin/v0.9-b1/authority-effect-core）
- 本块随收口更新提交（AD-8 行号修正 + PROJECT_STATE evidence_registry 登记）

## 1. 提交清单

| 提交 | 内容 | 执行 |
|---|---|---|
| `c464190` | 三门场景构造 8 处（send_guard 2 / ec_gate 2 / ec_telemetry 4）+ 新增 `test_v09_close_egress_wiring_offline.py`（11 例）+ AD-8 登记册 + D016 + journal 检查点；8 文件 +665/-18 | Builder 寇豆码（主理人接管验证收口） |
| （本块提交） | AD-8 登记册行号列按 HEAD 修正（第 1 轮审查缺陷修复）+ PROJECT_STATE.json evidence_registry 登记收口条目 + 本结果块 | 主理人 |

## 2. 判据达成表（FINALBATCH §3.5 出口判据）

| 判据 | 达成 | 证据 |
|---|---|---|
| 全量离线套件真正全绿（§4.3 首次） | ✅ | runtime 25/26 exit 0（唯一例外 harness_verify 环境噪声，剔除宿主变量 ACC_PRODUCT_CONFIG_V3 515KB>32767 后 11/11 OK）；tests/ 19 文件全绿；CLOSE 40 全绿 |
| 矩阵 36/36 | ✅ | case_count=36, matched=36, red=0；R34 与 R34-FAITHFUL 均 FAIL_CLOSED MATCH |
| tests/ 137 | ✅ | 19 文件 0 fail 0 error |
| doctor 无新增漂移（已裁决项除外） | ✅ | DRIFT_COUNT=1 = §7.8 豁免项（registry b1-head 滞后 expected c6d1a55b vs actual c464190）+ WARN journal staleness（已知合法） |
| 冻结原件不动 | ✅ | blob cb0cc306… 在 c464190/a0ce691/c0ed87e 三处 IDENTICAL |
| 期望与断言零变更 | ✅ | git diff c0ed87e..c464190 assert 行 0 命中（QA 逐行核验注释除外） |
| 产品代码零改动 | ✅ | 提交仅 docs + runtime/test_*，无 src/ config/ |

## 3. 证据路径

- 提交：`c464190`；登记册 `docs/evidence/v09-close/AD8-REGISTRY-final-batch.md`；D016 `docs/DECISION_LEDGER.md:164`（status CLOSED）
- 验证日志：全量套件输出 + QA 独立重跑记录
- PROJECT_STATE：evidence_registry 收口条目（V09-CLOSE-FINAL-BATCH）

## 4. 团内独立审查（§6 流放口 ≥2 轮）

- 第 1 轮（严过关，上下文/证据双独立）：**PASS**，7 项全过；发现 1 项文档缺陷（AD-8 登记册行号列基于旧基线）→ 已按审查意见修正（本提交）
- 第 2 轮：对本收口更新提交会签（进行中）

## 5. 封印记录（机械执行，不宣告有效性）

- TCB 封印：**未执行**。按 T0 先例，`security.seal_tcb` 目标 code_root/state_root 指向 E:\WB（另一检出与在产状态），封印须由发布负责人在权威 code_root/state_root 配对上执行；本线 TCB 状态维持 `UNVERIFIED_AFTER_CONTROLLER_CHANGE`（AGENTS.md 要求），"封印是否成立"不属本团判定。
- release_status：维持 `PRODUCT_NOT_READY`（章程流 A 明示不变）。

## 6. 团自裁事项（供业主事后审阅）

1. 工程师 429 中断后主理人接管流 A 剩余执行（验证/文档/提交），接管记录于台账。
2. ec_router_telemetry_offline.py 为工单清单（7 处）外补充适配（同配方场景构造，HANDOFF 未单列），已全绿、断言未改、登记册已涵盖；判定属 AD-8 既有套件场景构造范围。
3. harness_verify 环境噪声（宿主变量超长）处置：进程内剔除验证 11/11 OK，判定非代码问题，不修测试不修环境。
4. AD-8 登记册行号基准统一为 HEAD c464190（第 1 轮审查缺陷闭环）。

## 7. 消耗与保险丝

外部效果：git push ×1（c464190，流 A 主提交）；未触任何保险丝；无 NO_PROGRESS。

## 8. 下一动作

流 E 治理文档入仓（PM 方案已备，章程逐字节 + 裁决书集 + Q5 回填）→ 流 B 正式收束（盘点草案已备）→ 流 C V0.10 单类真实 GOAL。
