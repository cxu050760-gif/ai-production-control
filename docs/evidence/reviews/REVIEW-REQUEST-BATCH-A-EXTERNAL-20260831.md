# REVIEW-REQUEST — HARDENING 批次 A 外部独立审核（业主授权双层审核之外层）

## 审核任务
对执衡 `hardening/p0-gates-20260831` 分支的批次 A（P0 门禁加固+并发原子性+测试还账+治理清账）做独立外部审核，给出 APPROVE / APPROVE-WITH-NITS / REWORK 裁决。

## 审核材料（全部在仓库内）
- 仓库：`C:\Users\17838\Documents\Qoder\2026-08-28\031cb4e3\b1`（分支 hardening/p0-gates-20260831）
- 提交范围：`9a31e2c..HEAD`（`git log --format="%h %s" 9a31e2c..HEAD` + `git diff 9a31e2c..HEAD --stat`）
- 施工总纲（验收标准）：`docs/evidence/HARDENING-PLAN-20260831.md`
- 内部盲审报告：`docs/evidence/reviews/REVIEW-HARDENING-BATCH-A-INTERNAL-20260831.md`（结论 APPROVE-WITH-NITS，3 P2+6 P3）
- P2 修复对照：relay 锁 rename-steal / effect-reconcile 持 RunLock / lease 回收 rename-steal（见 HEAD 提交 diff）

## 请重点独立验证（不要只看内审报告，要亲自看 diff）
1. `runtime/run.cmd`：report 是否真正接入三闸链；`effect-reconcile` 是否替换了死入口 effect-gate
2. `scripts/relay_autopilot.py`：relay 模式是否还存在任何伪造/占位 commit 路径；FROZEN 是否与 SAFE_HALT 同等拦截；三闸 require_gates 的 fail-closed 是否有遗漏的 except
3. `runtime/controller_lease.py` + `runtime/parallel_scheduler.py`：并发修复是否有新引入的死锁/竞态（重点看锁的获取顺序与 rename-steal 的失败路径）
4. 测试真实性抽查：`runtime/test_v09_attack_matrix_on_b1_core.py`（恒绿→真断言）、`runtime/test_state_hygiene_sentinel_offline.py`（哨兵能否变红）

## 已知残余（内审 P3，未在本批修）
- reap_stale 持锁杀进程可能阻塞 ~4s；N3 断言同义反复；guard 残留接管窗口（.stolen 墓碑崩溃残留）；relay submit 裸 traceback

## 输出要求
裁决 + 逐项发现（file:line + P0-P3）写入 `E:\WB\outputs\ai-production-control\review-batch-a-external-<RUNID>.txt`；若 REWORK，列出必改清单与验收标准。
