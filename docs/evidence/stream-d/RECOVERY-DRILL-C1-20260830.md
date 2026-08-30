# C-1 沙箱破坏演练 — 恢复案例升级至 FULL

- 依据：主脑裁决书 `MAINBRAIN_RULING_E1-E4_BATCH.md` C-1（V0.11"恢复"案例证据强度 PARTIAL → 补沙箱破坏演练 → FULL）
- 执行：recovery-controller（本批施工）· 2026-08-30 17:10（北京）
- 沙箱：`E:\WB\temp\sandbox-recovery-20260830\`（**任务级沙箱，生产状态根零触碰**）
- 工具：candidate_r14 runtime（唯一保留 state-verify/state-recover 命令的运行时），`APC_RUNTIME_STATE_ROOT` 环境变量覆盖 state root 指向沙箱

## 演练过程（4 步全记录）

| 步骤 | 动作 | 结果 | 证据 |
|---|---|---|---|
| 1 基线 | 沙箱内 `state-verify --run-id RUN-20260829-223254-b173` | `ok: true, integrity ok, revision 6` | runtime.py 输出（下附） |
| 2 损坏 | 篡改沙箱 state.json：`revision 6→999`、`status → CORRUPTED-BY-DRILL` | 损坏成功 | 篡改脚本输出 |
| 3 检测 | 沙箱内 `state-verify`（损坏后） | `ok: false, reason: integrity mismatch` | runtime.py 输出（下附） |
| 4 恢复 | 沙箱内 `state-recover` | `recovered: true, restored previous known-good revision, revision 5` | runtime.py 输出（下附） |
| 5 复验 | 沙箱内 `state-verify`（恢复后） | `ok: true, integrity ok, revision 5` | runtime.py 输出（下附） |

## 关键输出摘录（原始 stdout）

```
# 演练1 baseline
{ "ok": true, "reason": "integrity ok", "run_id": "RUN-20260829-223254-b173", "revision": 6, ... }

# 演练3 损坏检测
{ "ok": false, "reason": "integrity mismatch", "run_id": "RUN-20260829-223254-b173" }

# 演练4 恢复
{ "recovered": true, "reason": "restored previous known-good revision",
  "run_id": "RUN-20260829-223254-b173", "revision": 5 }

# 演练5 复验
{ "ok": true, "reason": "integrity ok", "run_id": "RUN-20260829-223254-b173", "revision": 5, "schema_version": 1 }
```

## 机制说明

- 状态完整性锚：`state.json` + `state.integrity.json`（SHA256 绑定 revision/schema_version）
- 可恢复性来源：每次有效写入前，旧的有效状态轮转至 `state.prev.json` + `state.prev.integrity.json`（known-good 保留）
- `recover_state()`：当前 integrity mismatch 且 prev 有效 → 用 prev 覆盖恢复（`restored previous known-good revision`）；prev 无效则报告 `no valid known-good revision`
- 本演练演示的是「有 known-good 可恢复」路径；无损坏时 recover 报 `current state already valid`（V0.11 原案例已演示）

## 红线合规

- **生产状态根零触碰**：生产 `E:\WB\state\ai-production-control\runtime-v1\runs\RUN-20260829-223254-b173\` 仅被只读复制到沙箱；所有损坏/恢复操作均在沙箱内完成
- 生产现役 runtime.py 不含 state-verify/recover 命令（简化版），本演练使用保留该机制的 candidate_r14（同源实现，`APC_RUNTIME_STATE_ROOT` 测试缝按设计使用）

## 结论

C-1 沙箱破坏演练**完成并全绿**：损坏可被检测（integrity mismatch）、可恢复（prev known-good 回滚 revision 6→5→复验 ok）。
**V0.11"恢复"案例证据强度由 PARTIAL 升级为 FULL。** 沙箱目录保留备查（不清理），生产状态不受任何影响。
