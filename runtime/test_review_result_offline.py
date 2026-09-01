#!/usr/bin/env python3
"""Review Result Return (V0.1-FIX-REVIEW-RESULT-RETURN) — offline acceptance tests.

Runs the real runtime.py CLI as subprocesses against isolated state roots
(APC_RUNTIME_STATE_ROOT) with the READY wrapper stub and the deterministic
SCRIPT transport seam (APC_RUNTIME_INJECT_BRIDGE_FAIL=SCRIPT). No real bridge,
browser or ChatGPT conversation is ever touched here.

Covers:
  RR1  PASS verdict returns into durable state with RUN_ID/CANDIDATE_COMMIT/
       EVIDENCE_ID/REVIEW_ID binding (structured review_result + journal event)
  RR2  restart/reload: LAST_R_VERDICT + bindings survive a fresh process
  RR3  REWORK verdict: verdict + NEXT_ACTION + rework_count + binding durable
  RR4  BLOCKED verdict: HARD_BLOCKED, structured result still recorded
  RR5  fail-closed: invalid --candidate-commit rejected, nothing transported
  RR6  NO_VERDICT never upgrades to PASS; binding retained
  RR7  legacy compatibility: unbound send still returns a structured result
  RR8  recv path: late/continued receipt returns the verdict with binding kept
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

SHA_A = "a" * 40
R1 = "https://chatgpt.com/c/1e1ebbbb-1111-2222-3333-000000000002"


def check(name: str, cond: bool, detail: str = "") -> None:
    global PASS_COUNT, FAIL_COUNT
    if cond:
        PASS_COUNT += 1
        RESULTS.append(f"PASS {name}")
    else:
        FAIL_COUNT += 1
        RESULTS.append(f"FAIL {name} :: {detail}")


def run_cli(state_root: Path, argv: list, env_extra: dict = None, timeout: int = 120) -> tuple[int, dict, str]:
    env = dict(os.environ)
    env["APC_RUNTIME_STATE_ROOT"] = str(state_root)
    env.pop("APC_RUNTIME_INJECT_BRIDGE_FAIL", None)
    env.pop("APC_RUNTIME_INJECT_SCRIPT_FILE", None)
    env.pop("PYTHONIOENCODING", None)
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


def seam_env(wrapper: str, cfg: Path) -> dict:
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


def start_run(root: Path, env: dict, goal: str = "Review this candidate.") -> str:
    code, out, raw = run_cli(root, ["start", "--goal", goal, "--r-url", R1,
                                    "--worker-id", "rr-offline"], env)
    assert code == 0 and out.get("run_id"), raw
    return out["run_id"]


def main() -> int:
    work = Path(tempfile.mkdtemp(prefix="apc_review_result_"))
    print(f"TEST_WORK_ROOT={work}")
    wrap = ready_wrapper(work)

    # ---- RR1: PASS verdict returns into durable state with full binding ----
    rr1 = work / "rr1"
    rr1.mkdir()
    convs1 = {R1: {"sid": "rsid-rr1", "replies": ["===REVIEW_VERDICT=== PASS\n===WB_DONE:rr1==="]}}
    cfg1, log1 = write_script(rr1, convs1)
    env1 = seam_env(wrap, cfg1)
    rid1 = start_run(rr1, env1)
    code, out, raw = run_cli(rr1, ["send", "--run-id", rid1, "--message", "review packet for candidate",
                                   "--candidate-commit", SHA_A.upper(),
                                   "--evidence-id", "HE-rr1unit", "--review-id", "RV-TEST-1"], env1)
    check("RR1a_send_exit_ok", code == 0 and out.get("status") == "OK", raw[-300:])
    check("RR1b_last_r_verdict_pass", out.get("last_r_verdict") == "PASS", str(out)[:200])
    rr = out.get("review_result") or {}
    check("RR1c_review_result_bound", rr.get("run_id") == rid1 and rr.get("verdict") == "PASS"
          and rr.get("candidate_commit") == SHA_A and rr.get("evidence_id") == "HE-rr1unit"
          and rr.get("review_id") == "RV-TEST-1" and rr.get("returned_at"), str(rr)[:300])
    st1 = state_of(rr1, rid1)
    check("RR1d_state_durable_binding", st1.get("candidate_commit") == SHA_A
          and st1.get("evidence_id") == "HE-rr1unit" and st1.get("review_id") == "RV-TEST-1"
          and st1.get("last_r_verdict") == "PASS", str(st1.get("review_result"))[:300])
    ev1 = [e for e in journal_of(rr1, rid1) if e.get("event") == "REVIEW_RESULT_RETURN"]
    check("RR1e_journal_review_result_return", len(ev1) == 1 and ev1[0].get("verdict") == "PASS"
          and ev1[0].get("candidate_commit") == SHA_A and ev1[0].get("evidence_id") == "HE-rr1unit"
          and ev1[0].get("review_id") == "RV-TEST-1", str(ev1)[:300])

    # ---- RR2: restart/reload — fresh process reads the same durable result ----
    code, out2, _ = run_cli(rr1, ["status", "--run-id", rid1])
    check("RR2a_reload_verdict_survives", code == 0 and out2.get("last_r_verdict") == "PASS", str(out2)[:200])
    rr2 = out2.get("review_result") or {}
    check("RR2b_reload_binding_survives", rr2.get("candidate_commit") == SHA_A
          and rr2.get("evidence_id") == "HE-rr1unit" and rr2.get("review_id") == "RV-TEST-1"
          and rr2.get("verdict") == "PASS", str(rr2)[:300])

    # ---- RR3: REWORK verdict with NEXT_ACTION stays RUNNING, binding durable ----
    rr3 = work / "rr3"
    rr3.mkdir()
    convs3 = {R1: {"sid": "rsid-rr3",
                   "replies": ["===REVIEW_VERDICT=== REWORK\n===NEXT_ACTION=== Fix the header spelling."]}}
    cfg3, log3 = write_script(rr3, convs3)
    env3 = seam_env(wrap, cfg3)
    rid3 = start_run(rr3, env3)
    code, out, raw = run_cli(rr3, ["send", "--run-id", rid3, "--message", "review packet rework case",
                                   "--candidate-commit", SHA_A, "--evidence-id", "HE-rr3unit"], env3)
    st3 = state_of(rr3, rid3)
    check("RR3a_rework_verdict", code == 0 and out.get("last_r_verdict") == "REWORK", raw[-300:])
    check("RR3b_rework_next_action", st3.get("last_r_next_action") == "Fix the header spelling."
          and int(st3["metrics"].get("rework_count", 0)) == 1, str(st3.get("last_r_next_action"))[:200])
    check("RR3c_rework_binding_durable", (st3.get("review_result") or {}).get("verdict") == "REWORK"
          and st3.get("candidate_commit") == SHA_A and st3.get("status") == "RUNNING",
          str(st3.get("review_result"))[:300])

    # ---- RR4: BLOCKED verdict hard-blocks but still records structured result ----
    rr4 = work / "rr4"
    rr4.mkdir()
    convs4 = {R1: {"sid": "rsid-rr4",
                   "replies": ["===REVIEW_VERDICT=== BLOCKED\n===NEXT_ACTION=== Missing evidence."]}}
    cfg4, log4 = write_script(rr4, convs4)
    env4 = seam_env(wrap, cfg4)
    rid4 = start_run(rr4, env4)
    code, out, raw = run_cli(rr4, ["send", "--run-id", rid4, "--message", "review packet blocked case",
                                   "--candidate-commit", SHA_A, "--evidence-id", "HE-rr4unit"], env4)
    st4 = state_of(rr4, rid4)
    check("RR4a_blocked_hard_blocks", out.get("run_status") == "HARD_BLOCKED"
          and st4.get("status") == "HARD_BLOCKED", raw[-300:])
    check("RR4b_blocked_result_recorded", (st4.get("review_result") or {}).get("verdict") == "BLOCKED"
          and st4.get("candidate_commit") == SHA_A, str(st4.get("review_result"))[:300])
    ev4 = [e for e in journal_of(rr4, rid4) if e.get("event") == "REVIEW_RESULT_RETURN"]
    check("RR4c_blocked_journal_event", len(ev4) == 1 and ev4[0].get("verdict") == "BLOCKED", str(ev4)[:200])

    # ---- RR5: fail-closed validation, nothing transported, nothing persisted ----
    rr5 = work / "rr5"
    rr5.mkdir()
    convs5 = {R1: {"sid": "rsid-rr5", "replies": ["===REVIEW_VERDICT=== PASS"]}}
    cfg5, log5 = write_script(rr5, convs5)
    env5 = seam_env(wrap, cfg5)
    rid5 = start_run(rr5, env5)
    code, out, raw = run_cli(rr5, ["send", "--run-id", rid5, "--message", "review packet invalid sha",
                                   "--candidate-commit", "not-a-sha", "--evidence-id", "HE-rr5unit"], env5)
    st5 = state_of(rr5, rid5)
    check("RR5a_invalid_sha_rejected", code == 2 and out.get("status") == "INVALID_CANDIDATE_COMMIT", raw[-300:])
    check("RR5b_nothing_persisted", st5.get("candidate_commit") is None
          and st5.get("review_result") is None and st5.get("last_r_verdict") is None,
          str({k: st5.get(k) for k in ("candidate_commit", "review_result")})[:200])
    check("RR5c_nothing_transported", len(read_log(log5)) == 0, str(read_log(log5))[:200])

    # ---- RR6: NO_VERDICT never becomes PASS; binding retained ----
    rr6 = work / "rr6"
    rr6.mkdir()
    convs6 = {R1: {"sid": "rsid-rr6",
                   "replies": ["just prose, no token", "still nothing", "nothing at all"]}}
    cfg6, log6 = write_script(rr6, convs6)
    env6 = seam_env(wrap, cfg6)
    rid6 = start_run(rr6, env6)
    code, out, raw = run_cli(rr6, ["send", "--run-id", rid6, "--message", "review packet no verdict",
                                   "--candidate-commit", SHA_A, "--evidence-id", "HE-rr6unit"], env6)
    st6 = state_of(rr6, rid6)
    check("RR6a_no_verdict_never_pass", out.get("last_r_verdict") == "NO_VERDICT"
          and out.get("last_r_verdict") != "PASS", raw[-300:])
    check("RR6b_binding_retained", st6.get("candidate_commit") == SHA_A
          and (st6.get("review_result") or {}).get("verdict") == "NO_VERDICT",
          str(st6.get("review_result"))[:300])

    # ---- RR7: legacy compatibility — unbound send still returns structured result ----
    rr7 = work / "rr7"
    rr7.mkdir()
    convs7 = {R1: {"sid": "rsid-rr7", "replies": ["===REVIEW_VERDICT=== PASS"]}}
    cfg7, log7 = write_script(rr7, convs7)
    env7 = seam_env(wrap, cfg7)
    rid7 = start_run(rr7, env7)
    code, out, raw = run_cli(rr7, ["send", "--run-id", rid7, "--message", "legacy unbound review"], env7)
    st7 = state_of(rr7, rid7)
    check("RR7a_unbound_still_works", code == 0 and out.get("last_r_verdict") == "PASS", raw[-300:])
    check("RR7b_unbound_result_null_candidate", (st7.get("review_result") or {}).get("verdict") == "PASS"
          and (st7.get("review_result") or {}).get("candidate_commit") is None
          and (st7.get("review_result") or {}).get("run_id") == rid7,
          str(st7.get("review_result"))[:300])

    # ---- RR8: recv path returns a continued verdict with binding kept ----
    convs8 = {R1: {"sid": "rsid-rr8",
                   "replies": ["===REVIEW_VERDICT=== REWORK\n===NEXT_ACTION=== add evidence.",
                               "===REVIEW_VERDICT=== PASS"]}}
    rr8 = work / "rr8"
    rr8.mkdir()
    cfg8, log8 = write_script(rr8, convs8)
    env8 = seam_env(wrap, cfg8)
    rid8 = start_run(rr8, env8)
    code, out, raw = run_cli(rr8, ["send", "--run-id", rid8, "--message", "review packet recv case",
                                   "--candidate-commit", SHA_A, "--evidence-id", "HE-rr8unit"], env8)
    check("RR8a_first_verdict_rework", code == 0 and out.get("last_r_verdict") == "REWORK", raw[-300:])
    code, out, raw = run_cli(rr8, ["recv", "--run-id", rid8], env8)
    st8 = state_of(rr8, rid8)
    check("RR8b_recv_returns_pass", code == 0 and st8.get("last_r_verdict") == "PASS", raw[-300:])
    check("RR8c_recv_binding_kept", (st8.get("review_result") or {}).get("verdict") == "PASS"
          and st8.get("candidate_commit") == SHA_A and st8.get("evidence_id") == "HE-rr8unit",
          str(st8.get("review_result"))[:300])

    print("\n".join(RESULTS))
    print(f"\nTOTAL={PASS_COUNT + FAIL_COUNT} PASS={PASS_COUNT} FAIL={FAIL_COUNT}")
    return 0 if FAIL_COUNT == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
