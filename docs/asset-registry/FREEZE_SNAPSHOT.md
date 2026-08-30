# FREEZE_SNAPSHOT — 系统资产冻结快照（流 B · B-1）

> 生成：2026-08-29（会话日）· 产出人：许清楚（PM，流 B）
> **取数时间：2026-08-29 22:03（+08:00）**
> 依据：审计报告陷阱 9（"整理的对象一直在动；先冻结再整理"）——本快照为 B-1 整理的**事实冻结基线**。
> 方法：只读 `ls / find / du / stat`；未触碰任何被盘点资产；大目录仅列。
> 说明：文件数= `find -type f` 实测；大小= `du -sh` 实测；最新 mtime= 目录内最新文件（`find -printf %T@` 排序首项）。

---

## 1. 系统资产主要根（四大根）

| 根 | 文件数 | 总大小 | 最新文件（mtime） | 备注 |
|----|-------|--------|-------------------|------|
| `E:\执衡` | 7625 | 323 MB | `_quarantine\20260826-1230\_v07sr_packet.txt`（2026-08-26 20:23） | 主目录；含自有 .git、根级脚本、_quarantine |
| `E:\WB\state\ai-production-control` | 10881 | 418 MB | `construction-relay\watcher-heartbeat.json`（2026-08-27 00:04:38） | 运行状态基座；含 browser profile（敏感） |
| `E:\WB\outputs\ai-production-control` | 98 | 7.4 MB | `stream-e\VERSION_LADDER_V01_V04_FINAL.md`（2026-08-29 22:00） | 输出根；本批产出所在 |
| `E:\WB\tools\catpaw-longcat-proxy` | 121 | 1.2 MB | `logs\proxy-20260829-165253.stdout.log`（2026-08-29 16:52） | 生产反代（LIVE_PASS，端口 32177）；零改动 |

## 2. 关键子集计数

| 子集 | 文件数 | 大小 | 条目计数 | 最新文件（mtime） | 备注 |
|------|-------|------|---------|-------------------|------|
| `E:\执衡\04_测试证据` | 1022 | 200 MB | 15 子目录 | `接管定轨_20260820\M5d_source_binding_PARTIAL_声明.md`（2026-08-20 23:52） | 测试证据库（证据唯一副本） |
| `E:\WB\state\...\runtime-v1` | 3841 | 32 MB | — | `cli_log.jsonl`（2026-08-26 23:47） | Runtime V1 运行事实源 |
| └ `runtime-v1\runs` | 645 | 2.4 MB | **110 个 RUN 目录** | — | 与审计 109 差异登记（D-03，复核关闭） |
| `E:\WB\state\...\construction-relay` | 1691 | 23 MB | 98 顶层条目 | `watcher-heartbeat.json`（2026-08-27 00:04:38） | 中继层 O/C 记录 |
| └ `construction-relay\role-runs` | — | 6.0 MB | **65 个 ROLE 目录** | — | 与审计 66 差异登记（D-03，复核关闭） |
| `E:\WB\state\...\acceptance-fixtures` | 9 目录 | 小 | 9 task-* | — | 验收夹具 |
| `E:\WB\state\...\snapshots` | 30 | 小 | 30 revision-*.json | — | 状态快照 |
| `E:\WB\state\...\browser-auth-profile-v1/v2` | 各 17~18 项 | 小 | 2 目录 | — | **敏感（登录态），未读内容** |

## 3. 04_测试证据 分项（大小/文件数）

| 子目录 | 文件数 | 大小 | 备注 |
|--------|-------|------|------|
| webmodel_delivery | 606 | 170 MB | 占比最大（webmodel 交付物） |
| webmodel_lab | 243 | 28 MB | webmodel 实验 |
| 家底盘点 | 54 | 1.9 MB | 8-19 真实多 worker 证据 |
| 接管定轨_20260820 | 47 | 293 KB | M5 系列审查记录（最新 mtime 在此） |
| 纠错取证 | 24 | 98 KB | — |
| 审计 | 19 | 560 KB | — |
| wb_agg / wb_index_output | 各 5 | 28 KB / 21 KB | — |
| Bridge提交 | 4 | 20 KB | — |
| non_blocking_dogfood / nudge_e2e / supervisor_free_e2e / autonomy_ledger / real_goal | 各 1~4 | ≤6 KB | 小项 |

## 4. 冻结基线用途

1. **B-1 正式盘点转正**的取数基准（ASSET_INVENTORY_FINAL.md 以本快照为准）。
2. **差异复核依据**：D-03 计数差异（审计 109/66 vs 实测 110/65）以本快照两次实测一致关闭。
3. 后续任何流（B-2 起）若发现资产变化，应回到本快照对比，而非重跑全量。
4. 快照自身随整理可能过时（依陷阱 9），如需新的冻结点应重新取数并注明时间。

*冻结快照 · 2026-08-29 22:03（+08:00）· 流 B B-1*
