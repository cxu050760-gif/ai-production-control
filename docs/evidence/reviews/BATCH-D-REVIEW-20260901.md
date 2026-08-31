# 批次 D 盲审记录 — §45 状态层级 + §71 human_view 产品化（20260901）

## 范围

- `runtime/state_level.py`（新增，Canonical §45 状态层级代码枚举强制）
- `runtime/test_state_level_offline.py`（新增，25 例）
- `runtime/human_view.py`（新增，Canonical §71 简洁 UI 投影产品化）
- `runtime/test_human_view_offline.py`（新增，14 例）
- `docs/evidence/V1.0-ACHIEVEMENT-MATRIX-20260901.md`（§45/§71 部分→满足）

## 第一轮盲审（R-D，独立子代理，仅给文件清单+canonical 原文）

结论：**REWORK**。

- [P1] state_level.py — check_claim 证据子串匹配可被词面逃逸
  （"untested" 含 "test"、"preview" 含 "review"、"preproduction" 含
  "production"），§45 索证机判 fail-open。
- [P2] 异常态无 rank：PRODUCTION_VERIFIED→FAILED→PRODUCTION_VERIFIED
  全程不触发 LEVEL_REGRESSION，倒退可经异常态隧道绕过检测。
- [P2] human_view.py CLI 仅捕获 ValueError/JSONDecodeError，tasks 含
  非对象元素时以 traceback+exit 1 泄漏，违背 fail-closed（exit 2）契约。
- [P2] is_completion_claim 与 check_claim 双口径：无证据的
  LOCAL_TEST_PASS 前者判"完成"、后者报问题。

（同时确认：测试无恒真断言、无 mock 掩盖，CLI 均真实子进程执行；
矩阵指针与实际代码相符。）

## 处置（全部采纳）

1. P1：`_evidence_matched` 改字母级 lookaround `(?<![A-Za-z])kind s?(?![A-Za-z])`
   ——伪装词拒绝、snake_case（test_report.json）与复数（tests/reviews/）命中。
2. P2 隧道：`check_progression` 增加 `evidence` 参数；异常态→完成层级视为
   全新声明，无证据报 `REENTRY_EVIDERENCE_REQUIRED`，垃圾证据报
   `REENTRY_CLAIM_EVIDENCE_MISSING:*`；落入异常态（E2E_PASS→FAILED）
   仍视为真实事件放行。
3. P2 fail-open：human_view CLI 改 `except Exception → exit 2` 无 traceback；
   `build_view` 对 tasks 非对象元素 raise `GRAPH_TASKS_MUST_BE_OBJECTS`。
4. P2 双口径：`is_completion_claim` 单一口径——无证据一律 False，
   证据经 check_claim 充分才 True（等级判定与完成判定不再混用）。

## 复审终裁（R-D resume，逐文件读回+实跑）

- P1 → 已修复（S3:107-120 通过）
- P2 隧道 → 已修复（S4:144-160 通过）
- P2 双口径 → 已修复（S5:178-187 通过）
- P2 fail-open → 已修复（H5:177-187 通过）
- 实跑：state_level 25 例 OK；human_view 14 例 OK。

终裁：**PASS**（20260901）。

## 回归直录

| 轮 | RUNTIME | TESTS | STATE | 说明 |
|----|---------|-------|-------|------|
| batchD_r1 | 709 OK (75s) | 219 OK | CLEAN | 修复前基线 |
| batchD_r2 | （被 r3 取代口径） | — | — | 修复中途，不计 |
| batchD_r3 | 712 OK (79s) | 219 OK | CLEAN | R-D 修复后 |
| batchD_r4 | 712 OK (86s) | 219 OK | CLEAN | 复跑定性 |

712 = 673（批次 A 基线）+ 23+2（§45）+ 13+1（§71）。
