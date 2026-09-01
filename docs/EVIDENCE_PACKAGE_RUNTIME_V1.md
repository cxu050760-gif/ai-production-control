# Runtime V1 — Final Evidence Package (2026-08-18, assembled from real artifacts)

RUN under acceptance: RUN-20260818-173304-7350 (R_URL = user-provided conversation, epoch 1)

## T1 R_URL policy (offline suite + real)
- `start` without R_URL -> MISSING_R_URL, exit 3 (T1a); invalid URL rejected (T1b).
- Two RUNs with two different R_URLs: no inheritance, no cross-URL in state files (T1c-f).
- R_URL_CHANGE -> new review_epoch, old verdict/session/evidence invalidated (T1g).
- No default R_URL exists anywhere: bootstrap.json contains only fixed paths; runtime.py has no fallback URL constant.
Verbatim offline suite tail:
TEST_STATE_ROOT=C:\Users\17838\AppData\Local\Temp\apc_rt_v1_test_nvlvfomm
PASS T1a_missing_r_url
PASS T1b_invalid_r_url
PASS T1c_run_a_created
PASS T1d_run_b_created
PASS T1e_no_inherit
PASS T1f_no_cross_url
PASS T2a_step_A
PASS T2b_B_untouched
PASS T4a_pause_ok
PASS T4b_paused_after_restart
PASS T4c_step_denied_paused
PASS T4d_send_denied_paused
PASS T4e_directive_recorded
PASS T4f_resume_ok
PASS T5a_recovery_fields
PASS T5b_values
PASS T7a_reached_hard_blocked
PASS T7b_durable_hard_blocked
PASS T7c_budget_recorded
PASS T7d_step_denied_blocked
PASS T7e_send_denied_blocked
PASS T7f_journal_chain
PASS T1g_r_url_change
PASS C1a_first_attempt_ok
PASS C1_duplicate_guard
PASS C1b_guard_lifted_after_step

TOTAL=26 PASS=26 FAIL=0

## T2 single entry / no facade bypass
Contract: runtime/WEAK_WORKER_START_HERE.md (9 commands, all state-changing calls require explicit --run-id).
Weak-worker transcripts string-audited for bridge internals (bsk/daemon/52900/yz_/session stop/marker/click/navigate):
BRIDGE_INTERNAL_TOUCHED=NONE in every transcript (see T5 below). Runtime sanitizes internal strings in all outputs.

## T3 real R<->W loop via facade only (this RUN)
Round A: defective draft contract uploaded -> R returned REWORK -> runtime parsed verdict + next_action (rework_count=1).
Round B: W auto-reworked (draft_contract_v1.txt), resubmitted -> runtime parsed PASS. No user relay.
Reply files: RUN-20260818-173304-7350/reply_epoch1_*.txt in state root.

## T4 durable PAUSE (real, this RUN)
PAUSE committed durably -> send denied RUN_PAUSED -> fresh process `status` still PAUSED -> RESUME ok.
State excerpt: last_user_directive={"action": "RESUME", "note": "", "at": "2026-08-18T09:40:44+00:00"}

## T5 fresh-worker recovery (separate process, only bootstrap.json + RUN_ID)

--- RUN-20260818-174812-059b_weak_worker_transcript.txt ---
2026-08-18T09:48:12+00:00 WEAK_WORKER_SIM start; input RUN_ID=RUN-20260818-174812-059b only. No chat history available.
2026-08-18T09:48:12+00:00 BOOTSTRAP read: entry=E:\WB\tools\ai-production-control\runtime\run.cmd state_root=E:\WB\state\ai-production-control\runtime-v1
2026-08-18T09:48:12+00:00 CALL: run status --run-id RUN-20260818-174812-059b
2026-08-18T09:48:13+00:00 RC=0 STATUS=PAUSED RUN_STATUS=PAUSED
2026-08-18T09:48:13+00:00 AUTHORITATIVE STATE: status=PAUSED goal='T5 weak-worker recovery test (paused fixture)' step='fixture step'
2026-08-18T09:48:13+00:00 NEXT_ACTION='PAUSED by user directive. Do nothing until RESUME is committed.'
2026-08-18T09:48:13+00:00 R_URL=https://chatgpt.com/c/ffffffff-0000-0000-0000-000000000000 LAST_VERDICT=None
2026-08-18T09:48:13+00:00 STATE=PAUSED -> STOP. Do nothing. Wait for user RESUME directive. This sim refuses to continue (T5 requirement).


--- RUN-20260818-174813-867c_weak_worker_transcript.txt ---
2026-08-18T09:48:13+00:00 WEAK_WORKER_SIM start; input RUN_ID=RUN-20260818-174813-867c only. No chat history available.
2026-08-18T09:48:13+00:00 BOOTSTRAP read: entry=E:\WB\tools\ai-production-control\runtime\run.cmd state_root=E:\WB\state\ai-production-control\runtime-v1
2026-08-18T09:48:13+00:00 CALL: run status --run-id RUN-20260818-174813-867c
2026-08-18T09:48:13+00:00 RC=0 STATUS=RUNNING RUN_STATUS=RUNNING
2026-08-18T09:48:13+00:00 AUTHORITATIVE STATE: status=RUNNING goal='T5 weak-worker recovery test (running fixture)' step='impl step 3 done'
2026-08-18T09:48:13+00:00 NEXT_ACTION='impl step 4: wire tests'
2026-08-18T09:48:13+00:00 R_URL=https://chatgpt.com/c/ffffffff-0000-0000-0000-000000000000 LAST_VERDICT=None
2026-08-18T09:48:13+00:00 RUNNING without PASS -> a full worker would continue next_action work here; sim has no task capability, stopping cleanly.


--- RUN-20260818-rtv1_weak_worker_transcript.txt ---
2026-08-18T09:46:58+00:00 WEAK_WORKER_SIM start; input RUN_ID=RUN-20260818-rtv1 only. No chat history available.
2026-08-18T09:46:58+00:00 BOOTSTRAP read: entry=E:\WB\tools\ai-production-control\runtime\run.cmd state_root=E:\WB\state\ai-production-control\runtime-v1
2026-08-18T09:46:58+00:00 CALL: run status --run-id RUN-20260818-rtv1
2026-08-18T09:46:59+00:00 RC=2 STATUS=INVALID_RUN_ID RUN_STATUS=INVALID_RUN_ID
2026-08-18T09:46:59+00:00 FATAL: cannot read status; stop.


Real weak-model (membership-3/HY3) acceptance pending: entry prepared (runtime/WEAK_WORKER_BOOTSTRAP.md).

## T6 resources do not grow per round (real census)
CENSUS tag=t3_before sessions=0 agent_tabs=0
CENSUS tag=t6_after sessions=1 agent_tabs=1
CENSUS tag=e_before sessions=0 agent_tabs=0
CENSUS tag=e_after sessions=3 agent_tabs=3
CENSUS tag=e_after6 sessions=1 agent_tabs=1

Interpretation: E conversation carried 7 facade rounds; runtime sessions bounded (steady state sessions=1 agent_tabs=1);
one runtime session per distinct conversation; killed session replaced exactly once (pukf->eyue), no accumulation.

## T7 failure chain
Offline deterministic seam (facade boundary, real bridge untouched): inject fail -> bounded recovery -> budget exhaustion
-> durable HARD_BLOCKED -> subsequent step DENIED / send HARD_BLOCKED; journal chain:
temp_root=C:\Users\17838\AppData\Local\Temp\apc_rt_v1_test_nvlvfomm
2026-08-18T10:06:02+00:00 RUN_CREATED
2026-08-18T10:06:05+00:00 SEND_FAILURE result=NO_RESULT
2026-08-18T10:06:07+00:00 SEND_FAILURE result=NO_RESULT
2026-08-18T10:06:09+00:00 SEND_FAILURE result=NO_RESULT
2026-08-18T10:06:11+00:00 SEND_FAILURE result=NO_RESULT
2026-08-18T10:06:11+00:00 HARD_BLOCKED
Real recoverable fault: runtime-managed session killed externally; next facade send recovered transparently
(SID pukf -> eyue, RECOVERIES/RETRIES budgets intact, R replied PASS).

## Final metrics (RUN-C, real)
{
 "started_at": "2026-08-18T09:33:04+00:00",
 "finished_at": null,
 "r_roundtrips": 5,
 "r_wait_time_sec": 167.2,
 "bridge_retries": 0,
 "session_recoveries": 0,
 "verdict_requeries_used": 0,
 "duplicate_actions_blocked": 1,
 "rework_count": 2,
 "health_checks_skipped": 3,
 "evidence_skipped_unchanged": 1
}

## Journal excerpt (RUN-C)
2026-08-18T09:33:04+00:00 RUN_CREATED
2026-08-18T09:36:47+00:00 SEND_OK result=DONE
2026-08-18T09:38:11+00:00 STEP
2026-08-18T09:38:46+00:00 SEND_OK result=DONE
2026-08-18T09:40:43+00:00 DIRECTIVE_COMMIT
2026-08-18T09:40:43+00:00 DIRECTIVE_APPLIED
2026-08-18T09:40:44+00:00 DIRECTIVE_COMMIT
2026-08-18T09:40:44+00:00 DIRECTIVE_APPLIED
2026-08-18T09:40:56+00:00 SEND_OK result=DONE
2026-08-18T09:42:14+00:00 DUPLICATE_ACTION_BLOCKED
2026-08-18T09:43:22+00:00 STEP
2026-08-18T09:43:48+00:00 SEND_OK result=DONE
2026-08-18T10:03:54+00:00 STEP
2026-08-18T10:04:45+00:00 SEND_OK result=DONE

## Artifact hashes (SHA-256, deployed files)
d5b46bca8c09cfa903ef169cf9ce7821e9e9f3a53a3ccff262810178f2567438  runtime.py
a5022fd803333197f7c38f62a82bf39d797451e8a71fc7f195e778922eaf6152  run.cmd
f017f2a18f79918dd8d2118aeb2ffc044734acf2ed7dfb35f56cf8e2dafb717e  bootstrap.json
d1ec95bd8fdaaca5de8ac2af96c1ba189bee57aa0d067f0e5154906460be3e81  WEAK_WORKER_START_HERE.md
b519658396e3f58389b9ed1a832fb7e9dedffc27ff5d8e45fd4e6ab373de7ef7  WEAK_WORKER_BOOTSTRAP.md
56125bb7e9a70b8a77ff0c8555c69960cf0a677f569f9e5285b722bedf3cda18  test_runtime_offline.py
Note: git commit intentionally NOT created (repo policy: commit requires explicit user authorization);
hashes above pin the deployed state; project root E:\WB\tools\ai-production-control, runtime/ + docs/ + lab/ untracked.

## DEFERRED (non-blocking)
CAPTURE freshness task-binding; yz_send_file coordinate click; daemon idle auto-exit (design).
