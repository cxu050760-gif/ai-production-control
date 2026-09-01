# BATCH-A 外审投递留痕补录（TRANSCRIPT SUPPLEMENT，2026-08-31）

- 目的：修复 SELF-AUDIT-HARDENING-20260831 **P1-6**——原 acceptance_transcript.txt
  （隔离区 `E:\WB\state\ai-production-control\quarantine-agent-20260831\harness-quarantined\HE-BATCHA-HARDENING-20260831\`，冻结不动）仅记至 EV-160150，
  缺 2 次 UPLOAD_FAIL 投递事件，投递留痕不完整。
- 权威事实源：`E:\WB\state\ai-production-control\construction-relay\autopilot-actions.ndjson`
  与 `...\construction-relay\relay.ndjson`（账本原文，可随时重放核对）。
- 本文件为**派生补录**，不改写任何隔离区材料；账本与隔离区原件效力高于本文件。

## 缺记事件 1：EV-AUTO-20260831161509-9435

| 字段 | 值（自账本转录） |
|---|---|
| submit | 2026-08-31T08:15:09.437Z mode=relay task=AUTOPILOT-REVIEW-BATCH-A-EXTERNAL |
| EVENT_CLAIMED | 08:15:11.224Z candidate_commit=9655c967bb30982d0e74c8e0c068ebe86a68719a |
| WEB_REVIEW_STARTED | 08:15:11.869Z attempts\ATTEMPT-20260831081511-654ac156cbeaa702 |
| WEB_REVIEW_EVIDENCE | 08:15:11.874Z evidence_dir=HE-BATCHA-HARDENING-20260831 upload_count=5 |
| EVENT_FAILED | 08:17:05.622Z code=WEB_BRIDGE_SEND_FAILED → runtime send status=**HARD_BLOCKED**：`attachment upload failed beyond budget (UPLOAD_FAIL:manifest_check.py stage=attach_wait kw=manifest_check raw=ATTACHMENT_NOT_READY); session stayed healthy, no rebuild` |

## 缺记事件 2：EV-AUTO-20260831163849-29006

| 字段 | 值（自账本转录） |
|---|---|
| submit | 2026-08-31T08:38:49.008Z mode=relay task=AUTOPILOT-REVIEW-BATCH-A-EXTERNAL |
| EVENT_CLAIMED | 08:41:54.089Z candidate_commit=9655c967bb30982d0e74c8e0c068ebe86a68719a |
| WEB_REVIEW_STARTED | 08:41:54.330Z attempts\ATTEMPT-20260831084154-2677c1f8427a755f |
| WEB_REVIEW_EVIDENCE | 08:41:54.340Z evidence_dir=HE-BATCHA-HARDENING-20260831 upload_count=5 |
| EVENT_FAILED | 08:44:23.683Z code=WEB_BRIDGE_SEND_FAILED → 同上 HARD_BLOCKED（同一 UPLOAD_FAIL 根因） |

## 口径对齐

- 两事件计入 SELF-AUDIT 第三节"事实链 1"所述 **8 次投递**之内（此前 transcript 仅列至 160150，
  即 6 次可见 + 本补录 2 次 = 8 次，账本口径一致）。
- 根因归类同教训表 #11：基础设施故障（桥侧附件管线 ATTACHMENT_NOT_READY），非会话/材料问题。
- 补录人：FINAL_PROMPT v16 收官会话（CatPaw 施工主代理），2026-08-31。
