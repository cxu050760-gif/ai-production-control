#!/usr/bin/env python3
"""Router V0.1 (Slice A) — offline role-routing acceptance tests.

Runs the real runtime.py CLI as subprocesses against isolated state roots
(APC_RUNTIME_STATE_ROOT) with the READY wrapper stub and the deterministic
SCRIPT transport seam (APC_RUNTIME_INJECT_BRIDGE_FAIL=SCRIPT). No real
bridge, browser or ChatGPT conversation is ever touched here.

Covers (offline semantics only — AC-3 real web E2E is executed separately
by the independent harness):
  S1  validation (missing/invalid B_URL/R_URL, same-conversation guard)
  S2  forced REWORK loop: B -> R -> REWORK -> SAME B -> PASS (AC-1/4/5/6)
  S3  two router RUNs, four conversations, no cross-talk (AC-2)
  S4  UNKNOWN verdict can never become PASS (AC-11)
  S5  transport timeout can never become PASS (AC-11)
  S6  max-rounds bound terminates without PASS (AC-11)
  S7  durable resume across fresh processes (restart simulation)
  S8  legacy single-R_URL compatibility + mode guards (AC-8)
  S9  router-continue same-RUN continuation (AC-T5/AC-T6): fresh-process
      resume of a RUNNING+pending-phase RUN, same role binding, terminal
      idempotency, fail-closed bounds, legacy/unknown-RUN guards
"""
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except (AttributeError, ValueError, OSError):
    pass

HERE = Path(__file__).resolve().parent
RUNTIME = HERE / "runtime.py"
PY = sys.executable

PASS_COUNT = 0
FAIL_COUNT = 0
RESULTS = []


def check(name: str, cond: bool, detail: str = "") -> None:
    global PASS_COUNT, FAIL_COUNT
    if cond:
        PASS_COUNT += 1
        RESULTS.append(f"PASS {name}")
    else:
        FAIL_COUNT += 1
        RESULTS.append(f"FAIL {name} :: {detail}")


def run_cli(state_root: Path, argv: list, env_extra: dict = None, timeout: int = 240) -> tuple[int, dict, str]:
    env = dict(os.environ)
    env["APC_RUNTIME_STATE_ROOT"] = str(state_root)
    env.pop("APC_RUNTIME_INJECT_BRIDGE_FAIL", None)
    env.pop("APC_RUNTIME_INJECT_SCRIPT_FILE", None)
    env.pop("PYTHONIOENCODING", None)  # CLI must not depend on ambient encoding env
    if env_extra:
        env.update(env_extra)
    proc = subprocess.run([PY, str(RUNTIME), *argv], capture_output=True, text=True,
                          encoding="utf-8", errors="replace", env=env, timeout=timeout)
    try:
        out = json.loads(proc.stdout)
    except ValueError:
        out = {"_raw": proc.stdout}
    return proc.returncode, out, proc.stdout + proc.stderr


def msys(p) -> str:
    s = str(p).replace("\\", "/")
    return "/" + s[0].lower() + s[2:] if len(s) > 1 and s[1] == ":" else s


def ready_wrapper(d: Path) -> str:
    w = d / "stub_wrapper_ready.sh"
    w.write_text(
        "#!/bin/bash\ncase \"$1\" in status) echo 'Bridge: READY'; echo 'Browser: chrome'; "
        "echo 'Instance: deadbeef'; echo 'Upload: READY'; exit 0;; *) exit 2;; esac\n",
        encoding="utf-8")
    return msys(w)


def write_script(d: Path, convs: dict) -> tuple[Path, Path]:
    log = d / "transport_log.jsonl"
    cfg = d / "script.json"
    cfg.write_text(json.dumps({"conversations": convs, "log": str(log)}, ensure_ascii=False),
                   encoding="utf-8")
    return cfg, log


def router_env(wrapper: str, cfg: Path) -> dict:
    return {"APC_RUNTIME_BRIDGE_WRAPPER": wrapper,
            "APC_RUNTIME_INJECT_BRIDGE_FAIL": "SCRIPT",
            "APC_RUNTIME_INJECT_SCRIPT_FILE": str(cfg)}


def read_log(log: Path) -> list:
    if not log.exists():
        return []
    return [json.loads(l) for l in log.read_text(encoding="utf-8").splitlines()]


def state_of(root: Path, run_id: str) -> dict:
    return json.loads((root / "runs" / run_id / "state.json").read_text(encoding="utf-8"))


def journal_of(root: Path, run_id: str) -> list:
    p = root / "runs" / run_id / "journal.jsonl"
    return [json.loads(l) for l in p.read_text(encoding="utf-8").splitlines()] if p.exists() else []


B1 = "https://chatgpt.com/c/b0b0aaaa-1111-2222-3333-000000000001"
R1 = "https://chatgpt.com/c/1e1ebbbb-1111-2222-3333-000000000002"
B2 = "https://chatgpt.com/c/b2b2cccc-1111-2222-3333-000000000003"
R2 = "https://chatgpt.com/c/2e2edddd-1111-2222-3333-000000000004"


def main() -> int:
    work = Path(tempfile.mkdtemp(prefix="apc_router_v01_"))
    print(f"TEST_WORK_ROOT={work}")
    wrap = ready_wrapper(work)

    # ---- S1: validation — bad/missing URLs never create a RUN ----
    s1 = work / "s1"
    s1.mkdir()
    goal_f = s1 / "goal.txt"
    goal_f.write_text("Build a page whose header is spelled correctly.", encoding="utf-8")
    code, out, _ = run_cli(s1, ["router-run", "--goal-file", str(goal_f)])
    check("S1a_missing_b_url", code == 3 and out.get("status") == "MISSING_B_URL", str(out)[:160])
    code, out, _ = run_cli(s1, ["router-run", "--goal-file", str(goal_f),
                                "--b-url", "http://evil.example/c/x"])
    check("S1b_invalid_b_url", code == 3 and out.get("status") == "INVALID_B_URL", str(out)[:160])
    code, out, _ = run_cli(s1, ["router-run", "--goal-file", str(goal_f), "--b-url", B1])
    check("S1c_missing_r_url", code == 3 and out.get("status") == "MISSING_R_URL", str(out)[:160])
    code, out, _ = run_cli(s1, ["router-run", "--goal-file", str(goal_f),
                                "--b-url", B1, "--r-url", "not-a-url"])
    check("S1d_invalid_r_url", code == 3 and out.get("status") == "INVALID_R_URL", str(out)[:160])
    code, out, _ = run_cli(s1, ["router-run", "--goal-file", str(goal_f), "--b-url", B1, "--r-url", B1])
    check("S1e_same_conversation_guard", code == 2 and out.get("status") == "ROUTER_SAME_CONVERSATION",
          str(out)[:160])
    code, out, _ = run_cli(s1, ["router-run", "--goal-file", str(s1 / "nope.txt"),
                                "--b-url", B1, "--r-url", R1])
    check("S1f_goal_file_must_exist", code == 2 and out.get("status") == "FILE_NOT_FOUND", str(out)[:160])
    check("S1g_no_run_created", not (s1 / "runs").exists() or
          not any((s1 / "runs").iterdir()), "RUN leaked from failed validation")

    # ---- S2: forced REWORK loop -> SAME builder -> PASS (core AC chain) ----
    s2 = work / "s2"
    s2.mkdir()
    goal2 = s2 / "goal.txt"
    goal2.write_text("Build a page whose header is spelled correctly.", encoding="utf-8")
    convs2 = {
        B1: {"sid": "bsid-0001",
             "replies": ["candidate v1: header spelled 'Heder' (wrong)",
                         "candidate v2: header fixed to 'Header'"]},
        R1: {"sid": "rsid-0001",
             "replies": ["===REVIEW_VERDICT=== REWORK\n===NEXT_ACTION=== Fix the header spelling.",
                         "===REVIEW_VERDICT=== PASS\n===CHATGPT_DONE:round2==="]},
    }
    cfg2, log2 = write_script(s2, convs2)
    code, out, raw = run_cli(s2, ["router-run", "--goal-file", str(goal2), "--b-url", B1, "--r-url", R1,
                                  "--worker-id", "slice-a-offline", "--max-rounds", "2", "--timeout", "30"],
                             router_env(wrap, cfg2))
    check("S2a_routed_pass", code == 0 and out.get("status") == "ROUTED_PASS"
          and out.get("last_r_verdict") == "PASS" and out.get("rounds") == 1, raw[-400:])
    rid2 = out.get("run_id", "")
    entries = read_log(log2)
    urls = [e["url"] for e in entries]
    check("S2b_route_sequence_B_R_B_R", urls == [B1, R1, B1, R1], str(urls))
    check("S2c_goal_dispatched_to_B", entries and entries[0]["message"] == goal2.read_text(encoding="utf-8").strip()
          and entries[0]["url"] == B1, str(entries[:1])[:200])
    check("S2d_envelope_carries_builder_v1", len(entries) > 1
          and "candidate v1" in entries[1]["message"]
          and "===REVIEW_VERDICT===" in entries[1]["message"]
          and entries[1]["url"] == R1, str(entries[1:2])[:240])
    check("S2e_rework_auto_built_from_NEXT_ACTION", len(entries) > 2
          and "Fix the header spelling" in entries[2]["message"]
          and "REWORK" in entries[2]["message"], str(entries[2:3])[:240])
    check("S2f_same_builder_identity", len(entries) > 2 and entries[2]["url"] == B1
          and entries[2]["reattach"] is True and entries[2]["stored_sid"] == "bsid-0001"
          and entries[2]["sid"] == "bsid-0001", str(entries[2:3])[:240])
    check("S2g_second_review_carries_builder_v2", len(entries) > 3
          and "candidate v2" in entries[3]["message"], str(entries[3:4])[:240])
    st2 = state_of(s2, rid2)
    check("S2h_role_binding_answerable", st2["mode"] == "router-v0.1"
          and st2["role_urls"]["builder"] == B1 and st2["role_urls"]["reviewer"] == R1
          and st2["role_sessions"]["builder"]["sid"] == "bsid-0001"
          and st2["role_sessions"]["reviewer"]["sid"] == "rsid-0001", str(st2.get("role_urls")))
    ev2 = [e["event"] for e in journal_of(s2, rid2)]
    check("S2i_journal_chain", "ROUTER_RUN_CREATED" in ev2 and ev2.count("ROUTER_SEND") == 4
          and "ROUTER_REWORK" in ev2 and "ROUTER_DONE" in ev2, str(ev2))

    # ---- S3: two concurrent router RUNs — no cross-talk (AC-2) ----
    s3 = work / "s3"
    s3a = s3 / "a"
    s3b = s3 / "b"
    s3a.mkdir(parents=True)
    s3b.mkdir(parents=True)
    gA = s3 / "goalA.txt"
    gA.write_text("Task A: output ALPHA.", encoding="utf-8")
    gB = s3 / "goalB.txt"
    gB.write_text("Task B: output BETA.", encoding="utf-8")
    convsA = {B1: {"sid": "bsid-A", "replies": ["ALPHA done"]},
              R1: {"sid": "rsid-A", "replies": ["===REVIEW_VERDICT=== PASS"]}}
    convsB = {B2: {"sid": "bsid-B", "replies": ["BETA done"]},
              R2: {"sid": "rsid-B", "replies": ["===REVIEW_VERDICT=== PASS"]}}
    cfgA, logA = write_script(s3a, convsA)
    cfgB, logB = write_script(s3b, convsB)
    codeA, outA, _ = run_cli(s3, ["router-run", "--goal-file", str(gA), "--b-url", B1, "--r-url", R1,
                                  "--timeout", "30"], router_env(wrap, cfgA))
    codeB, outB, _ = run_cli(s3, ["router-run", "--goal-file", str(gB), "--b-url", B2, "--r-url", R2,
                                  "--timeout", "30"], router_env(wrap, cfgB))
    check("S3a_both_routed_pass", codeA == 0 and outA.get("status") == "ROUTED_PASS"
          and codeB == 0 and outB.get("status") == "ROUTED_PASS",
          f"A={outA.get('status')} B={outB.get('status')}")
    urlsA = {e["url"] for e in read_log(logA)}
    urlsB = {e["url"] for e in read_log(logB)}
    check("S3b_no_crosstalk_urls", urlsA == {B1, R1} and urlsB == {B2, R2},
          f"A={sorted(urlsA)} B={sorted(urlsB)}")
    stA = state_of(s3, outA["run_id"])
    stB = state_of(s3, outB["run_id"])
    rawA = json.dumps(stA)
    rawB = json.dumps(stB)
    check("S3c_no_cross_url_in_state", B2 not in rawA and R2 not in rawA
          and B1 not in rawB and R1 not in rawB, "cross URL contamination")
    check("S3d_run_ids_distinct", stA["run_id"] != stB["run_id"], "RUN ids collided")

    # ---- S4: UNKNOWN (unparseable reviewer) can never become PASS (AC-11) ----
    s4 = work / "s4"
    s4.mkdir()
    g4 = s4 / "goal.txt"
    g4.write_text("Task needing a verdict.", encoding="utf-8")
    convs4 = {B1: {"sid": "bsid-0001", "replies": ["some output"]},
              R1: {"sid": "rsid-0001",
                   "replies": ["just prose, no token", "still nothing", "nothing at all"]}}
    cfg4, log4 = write_script(s4, convs4)
    code, out, raw = run_cli(s4, ["router-run", "--goal-file", str(g4), "--b-url", B1, "--r-url", R1,
                                  "--timeout", "30"], router_env(wrap, cfg4))
    check("S4a_no_verdict_never_pass", code == 6 and out.get("status") == "HARD_BLOCKED", raw[-300:])
    rid4 = out.get("run_id", "")
    st4 = state_of(s4, rid4)
    check("S4b_durable_no_verdict", st4["status"] == "HARD_BLOCKED"
          and st4["last_r_verdict"] == "NO_VERDICT"
          and "ROUTER_NO_VERDICT" in str(st4.get("blocked_reason")), str(st4.get("blocked_reason"))[:160])
    code, out, _ = run_cli(s4, ["router-step", "--run-id", rid4])
    check("S4c_terminal_step_reports_blocked", code == 6 and out.get("status") == "HARD_BLOCKED", str(out)[:160])

    # ---- S5: transport timeout can never become PASS (AC-11) ----
    s5 = work / "s5"
    s5.mkdir()
    g5 = s5 / "goal.txt"
    g5.write_text("Task that times out.", encoding="utf-8")
    convs5 = {B1: {"sid": "bsid-0001", "replies": ["never delivered"],
                   "failures": ["RUNTIME_TIMEOUT"] * 6},
              R1: {"sid": "rsid-0001", "replies": ["===REVIEW_VERDICT=== PASS"]}}
    cfg5, log5 = write_script(s5, convs5)
    code, out, raw = run_cli(s5, ["router-run", "--goal-file", str(g5), "--b-url", B1, "--r-url", R1,
                                  "--timeout", "30"], router_env(wrap, cfg5))
    check("S5a_timeout_never_pass", code == 6 and out.get("status") == "HARD_BLOCKED", raw[-300:])
    st5 = state_of(s5, out.get("run_id", ""))
    check("S5b_budget_recorded_durable", st5["status"] == "HARD_BLOCKED"
          and st5["status"] != "DONE"
          and int(st5["metrics"].get("bridge_retries", 0)) >= 4
          and "beyond budget" in str(st5.get("blocked_reason")), str(st5.get("blocked_reason"))[:160])

    # ---- S6: max-rounds bound terminates without PASS (AC-11) ----
    s6 = work / "s6"
    s6.mkdir()
    g6 = s6 / "goal.txt"
    g6.write_text("Task that never satisfies the reviewer.", encoding="utf-8")
    convs6 = {B1: {"sid": "bsid-0001", "replies": ["try 1", "try 2", "try 3"]},
              R1: {"sid": "rsid-0001",
                   "replies": ["===REVIEW_VERDICT=== REWORK\n===NEXT_ACTION=== again",
                               "===REVIEW_VERDICT=== REWORK\n===NEXT_ACTION=== again",
                               "===REVIEW_VERDICT=== REWORK\n===NEXT_ACTION=== again"]}}
    cfg6, log6 = write_script(s6, convs6)
    code, out, raw = run_cli(s6, ["router-run", "--goal-file", str(g6), "--b-url", B1, "--r-url", R1,
                                  "--max-rounds", "1", "--timeout", "30"], router_env(wrap, cfg6))
    check("S6a_max_rounds_hard_blocked", code == 6 and out.get("status") == "HARD_BLOCKED"
          and out.get("last_r_verdict") == "REWORK", raw[-300:])
    urls6 = [e["url"] for e in read_log(log6)]
    check("S6b_bounded_exchange_B_R_B_R", urls6 == [B1, R1, B1, R1], str(urls6))
    st6 = state_of(s6, out.get("run_id", ""))
    check("S6c_not_done", st6["status"] == "HARD_BLOCKED" and st6["status"] != "DONE"
          and "ROUTER_MAX_ROUNDS_EXCEEDED" in str(st6.get("blocked_reason")),
          str(st6.get("blocked_reason"))[:160])

    # ---- S7: durable resume across fresh processes (restart simulation) ----
    s7 = work / "s7"
    s7.mkdir()
    g7 = s7 / "goal.txt"
    g7.write_text("Build a page whose header is spelled correctly.", encoding="utf-8")
    convs7 = {B1: {"sid": "bsid-0001",
                   "replies": ["candidate v1 (bad header)", "candidate v2 (fixed)"]},
              R1: {"sid": "rsid-0001",
                   "replies": ["===REVIEW_VERDICT=== REWORK\n===NEXT_ACTION=== Fix the header spelling.",
                               "===REVIEW_VERDICT=== PASS"]}}
    cfg7, log7 = write_script(s7, convs7)
    env7 = router_env(wrap, cfg7)
    code, out, _ = run_cli(s7, ["router-start", "--goal-file", str(g7), "--b-url", B1, "--r-url", R1,
                                "--max-rounds", "2", "--worker-id", "resume-probe"], env7)
    rid7 = out.get("run_id", "")
    check("S7a_start_creates_phase0", code == 0 and out.get("status") == "OK"
          and out.get("phase") == "SEND_GOAL_TO_BUILDER" and rid7.startswith("RUN-"), str(out)[:200])
    code, o1, _ = run_cli(s7, ["router-step", "--run-id", rid7, "--timeout", "30"], env7)
    check("S7b_step1_builder", code == 0 and o1.get("stepped") is True and o1.get("role") == "builder"
          and o1.get("phase") == "SEND_TO_REVIEWER", str(o1)[:200])
    code, o2, _ = run_cli(s7, ["router-step", "--run-id", rid7, "--timeout", "30"], env7)
    check("S7c_step2_reviewer_rework", code == 0 and o2.get("role") == "reviewer"
          and o2.get("verdict") == "REWORK" and o2.get("phase") == "SEND_REWORK_TO_BUILDER"
          and o2.get("run_status") == "RUNNING", str(o2)[:200])
    st_mid = state_of(s7, rid7)
    check("S7d_durable_round_after_restart", st_mid["router"]["round"] == 1
          and st_mid["router"]["phase"] == "SEND_REWORK_TO_BUILDER"
          and st_mid["router"]["pending_rework"] == "Fix the header spelling.",
          str(st_mid["router"])[:200])
    code, o3, _ = run_cli(s7, ["router-step", "--run-id", rid7, "--timeout", "30"], env7)
    check("S7e_step3_rework_to_same_builder", code == 0 and o3.get("role") == "builder"
          and o3.get("phase") == "SEND_TO_REVIEWER", str(o3)[:200])
    code, o4, _ = run_cli(s7, ["router-step", "--run-id", rid7, "--timeout", "30"], env7)
    check("S7f_step4_pass_done", code == 0 and o4.get("verdict") == "PASS"
          and o4.get("phase") == "ROUTED_PASS" and o4.get("run_status") == "DONE", str(o4)[:200])
    e7 = read_log(log7)
    check("S7g_cross_process_route_sequence", [e["url"] for e in e7] == [B1, R1, B1, R1],
          str([e["url"] for e in e7]))
    check("S7h_same_builder_after_restart", len(e7) == 4 and e7[2]["reattach"] is True
          and e7[2]["stored_sid"] == "bsid-0001" and e7[2]["sid"] == "bsid-0001", str(e7[2:3])[:240])

    # ---- S8: legacy compatibility + mode guards (AC-8) ----
    s8 = work / "s8"
    s8.mkdir()
    code, outL, _ = run_cli(s8, ["start", "--goal", "legacy goal", "--r-url", R1, "--worker-id", "legacy"])
    legacy_rid = outL.get("run_id", "")
    check("S8a_legacy_start_still_works", code == 0 and legacy_rid.startswith("RUN-"), str(outL)[:160])
    code, out, _ = run_cli(s8, ["router-step", "--run-id", legacy_rid])
    check("S8b_router_step_denied_on_legacy", code == 5 and out.get("status") == "DENIED", str(out)[:160])
    code, sR2, _ = run_cli(s2, ["status", "--run-id", rid2])
    check("S8c_legacy_status_reads_router_run", code == 0 and sR2.get("mode") == "router-v0.1"
          and sR2.get("status") == "DONE" and "role_urls" in sR2, str(sR2)[:200])
    n_before = len(read_log(log2))
    code, out, _ = run_cli(s2, ["router-step", "--run-id", rid2, "--timeout", "30"], router_env(wrap, cfg2))
    check("S8d_terminal_step_no_transport", code == 0 and out.get("stepped") is False
          and len(read_log(log2)) == n_before, str(out)[:160])

    # ---- S9: router-continue — same-RUN continuation (AC-T5 / AC-T6) ----
    s9 = work / "s9"
    s9.mkdir()
    g9 = s9 / "goal.txt"
    g9.write_text("Build a page whose header is spelled correctly.", encoding="utf-8")
    convs9 = {B1: {"sid": "bsid-0001",
                   "replies": ["candidate v1 (bad header)", "candidate v2 (fixed)"]},
              R1: {"sid": "rsid-0001",
                   "replies": ["===REVIEW_VERDICT=== REWORK\n===NEXT_ACTION=== Fix the header spelling.",
                               "===REVIEW_VERDICT=== PASS"]}}
    cfg9, log9 = write_script(s9, convs9)
    env9 = router_env(wrap, cfg9)
    code, out, _ = run_cli(s9, ["router-start", "--goal-file", str(g9), "--b-url", B1, "--r-url", R1,
                                "--max-rounds", "2", "--worker-id", "continue-probe"], env9)
    rid9 = out.get("run_id", "")
    check("S9a_start_creates_run", code == 0 and rid9.startswith("RUN-"), str(out)[:200])
    # One bounded step: builder phase completes, driver process then exits
    # (simulated crash) leaving RUNNING + pending phase (the observed zombie case).
    code, o1, _ = run_cli(s9, ["router-step", "--run-id", rid9, "--timeout", "30"], env9)
    check("S9b_step_builder_then_driver_exit", code == 0 and o1.get("role") == "builder"
          and o1.get("phase") == "SEND_TO_REVIEWER", str(o1)[:200])
    st_stuck = state_of(s9, rid9)
    check("S9c_zombie_running_pending_phase", st_stuck["status"] == "RUNNING"
          and st_stuck["router"]["phase"] == "SEND_TO_REVIEWER", str(st_stuck["router"])[:160])
    # A FRESH process continues the SAME RUN deterministically (AC-T5).
    code, oc, raw = run_cli(s9, ["router-continue", "--run-id", rid9, "--timeout", "30"], env9)
    check("S9d_continue_to_routed_pass", code == 0 and oc.get("status") == "ROUTED_PASS"
          and oc.get("continued") is True and oc.get("run_id") == rid9
          and oc.get("run_status") == "DONE" and oc.get("last_r_verdict") == "PASS", raw[-400:])
    check("S9e_same_run_same_role_binding", oc.get("role_urls") == {"builder": B1, "reviewer": R1}
          and oc.get("builder_session") == "bsid-0001"
          and oc.get("reviewer_session") == "rsid-0001", str(oc.get("role_urls"))[:200])
    e9 = read_log(log9)
    check("S9f_continued_route_sequence_B_R_B_R", [e["url"] for e in e9] == [B1, R1, B1, R1],
          str([e["url"] for e in e9]))
    check("S9g_continued_same_builder_reattach", len(e9) == 4 and e9[2]["reattach"] is True
          and e9[2]["stored_sid"] == "bsid-0001", str(e9[2:3])[:240])
    ev9 = [e["event"] for e in journal_of(s9, rid9)]
    check("S9h_journal_continuation_chain", "ROUTER_CONTINUE" in ev9 and "ROUTER_DONE" in ev9
          and ev9.count("ROUTER_SEND") == 4, str(ev9))
    # Terminal idempotency: continuing a DONE RUN adds no transport (AC-T6 clarity).
    n_before9 = len(read_log(log9))
    code, oc2, _ = run_cli(s9, ["router-continue", "--run-id", rid9, "--timeout", "30"], env9)
    check("S9i_terminal_continue_no_transport", code == 0 and oc2.get("continued") is False
          and oc2.get("status") == "DONE" and len(read_log(log9)) == n_before9, str(oc2)[:200])

    # ---- S9j-l: continuation of an endless REWORK loop stays fail-closed ----
    s9m = work / "s9m"
    s9m.mkdir()
    g9m = s9m / "goal.txt"
    g9m.write_text("Task that never satisfies the reviewer.", encoding="utf-8")
    convs9m = {B1: {"sid": "bsid-0001", "replies": ["try 1", "try 2", "try 3"]},
               R1: {"sid": "rsid-0001",
                    "replies": ["===REVIEW_VERDICT=== REWORK\n===NEXT_ACTION=== again",
                                "===REVIEW_VERDICT=== REWORK\n===NEXT_ACTION=== again",
                                "===REVIEW_VERDICT=== REWORK\n===NEXT_ACTION=== again"]}}
    cfg9m, log9m = write_script(s9m, convs9m)
    env9m = router_env(wrap, cfg9m)
    code, out, _ = run_cli(s9m, ["router-start", "--goal-file", str(g9m), "--b-url", B1, "--r-url", R1,
                                 "--max-rounds", "1", "--worker-id", "continue-guard"], env9m)
    rid9m = out.get("run_id", "")
    code, o1, _ = run_cli(s9m, ["router-step", "--run-id", rid9m, "--timeout", "30"], env9m)
    check("S9j_pre_continue_builder_step", code == 0 and o1.get("role") == "builder", str(o1)[:160])
    code, oc, raw = run_cli(s9m, ["router-continue", "--run-id", rid9m, "--timeout", "30"], env9m)
    check("S9k_continue_max_rounds_hard_blocked", code == 6 and oc.get("status") == "HARD_BLOCKED"
          and oc.get("last_r_verdict") == "REWORK", raw[-300:])
    st9m = state_of(s9m, rid9m)
    check("S9l_durable_blocked_not_zombie", st9m["status"] == "HARD_BLOCKED"
          and "ROUTER_MAX_ROUNDS_EXCEEDED" in str(st9m.get("blocked_reason")),
          str(st9m.get("blocked_reason"))[:160])

    # ---- S9m-n: continuation guards ----
    code, out, _ = run_cli(s8, ["router-continue", "--run-id", legacy_rid])
    check("S9m_continue_denied_on_legacy", code == 5 and out.get("status") == "DENIED", str(out)[:160])
    code, out, _ = run_cli(s9, ["router-continue", "--run-id", "RUN-19700101-000000-0000"])
    check("S9n_continue_unknown_run", code == 4 and out.get("status") == "RUN_NOT_FOUND", str(out)[:160])

    print("\n".join(RESULTS))
    print(f"\nTOTAL={PASS_COUNT + FAIL_COUNT} PASS={PASS_COUNT} FAIL={FAIL_COUNT}")
    return 0 if FAIL_COUNT == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
