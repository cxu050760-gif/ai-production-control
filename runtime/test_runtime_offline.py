#!/usr/bin/env python3
"""Runtime V1 — offline acceptance tests (Batch 2).

Runs the real runtime.py CLI as subprocesses against an isolated state root
(APC_RUNTIME_STATE_ROOT) with the deterministic bridge-failure seam
(APC_RUNTIME_INJECT_BRIDGE_FAIL). No real bridge is ever touched here.

Covers: T1 R_URL policy, T2 single-entry semantics, T4 PAUSE durability across
fresh processes (restart simulation), T5 recovery fields, T7 failure chain up
to durable HARD_BLOCKED + denial of ordinary actions, dual-RUN isolation.
Real-bridge parts (T3/T6 + one real recoverable fault) run separately.
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


def run_cli(state_root: Path, argv: list, env_extra: dict = None) -> tuple[int, dict, str]:
    env = dict(os.environ)
    env["APC_RUNTIME_STATE_ROOT"] = str(state_root)
    env.pop("APC_RUNTIME_INJECT_BRIDGE_FAIL", None)
    env.pop("PYTHONIOENCODING", None)  # CLI must not depend on ambient encoding env
    if env_extra:
        env.update(env_extra)
    proc = subprocess.run([PY, str(RUNTIME), *argv], capture_output=True, text=True,
                          encoding="utf-8", errors="replace", env=env, timeout=120)
    try:
        out = json.loads(proc.stdout)
    except ValueError:
        out = {"_raw": proc.stdout}
    return proc.returncode, out, proc.stdout + proc.stderr


def main() -> int:
    tmp = Path(tempfile.mkdtemp(prefix="apc_rt_v1_test_"))
    print(f"TEST_STATE_ROOT={tmp}")

    # ---- T1: no R_URL -> MISSING_R_URL, invalid URL rejected ----
    code, out, _ = run_cli(tmp, ["start", "--goal", "g1"])
    check("T1a_missing_r_url", code == 3 and out.get("status") == "MISSING_R_URL", str(out))
    code, out, _ = run_cli(tmp, ["start", "--goal", "g1", "--r-url", "http://evil.example/c/x"])
    check("T1b_invalid_r_url", code == 3 and out.get("status") == "INVALID_R_URL", str(out))

    # ---- T1/T2: two RUNs, two different R_URLs, full isolation ----
    URL_A = "https://chatgpt.com/c/aaaaaaaa-1111-2222-3333-444444444444"
    URL_B = "https://chatgpt.com/c/bbbbbbbb-1111-2222-3333-555555555555"
    code, outA, _ = run_cli(tmp, ["start", "--goal", "goal-A", "--r-url", URL_A, "--worker-id", "wA"])
    run_a = outA.get("run_id", "")
    check("T1c_run_a_created", code == 0 and run_a.startswith("RUN-"), str(outA))
    code, outB, _ = run_cli(tmp, ["start", "--goal", "goal-B", "--r-url", URL_B, "--worker-id", "wB"])
    run_b = outB.get("run_id", "")
    check("T1d_run_b_created", code == 0 and run_b.startswith("RUN-"), str(outB))
    code, sA, _ = run_cli(tmp, ["status", "--run-id", run_a])
    code2, sB, _ = run_cli(tmp, ["status", "--run-id", run_b])
    check("T1e_no_inherit", sA.get("r_url") == URL_A and sB.get("r_url") == URL_B,
          f"A={sA.get('r_url')} B={sB.get('r_url')}")
    # state files must not contain the other RUN's URL
    stA = (tmp / "runs" / run_a / "state.json").read_text(encoding="utf-8")
    stB = (tmp / "runs" / run_b / "state.json").read_text(encoding="utf-8")
    check("T1f_no_cross_url", URL_B not in stA and URL_A not in stB, "cross contamination")

    # ---- step / directive routing is explicit --run-id only ----
    code, out, _ = run_cli(tmp, ["step", "--run-id", run_a, "--current", "did A1", "--next", "do A2"])
    check("T2a_step_A", code == 0 and out.get("current_step") == "did A1", str(out))
    _, sB2, _ = run_cli(tmp, ["status", "--run-id", run_b])
    check("T2b_B_untouched", sB2.get("current_step") == "RUN started", str(sB2.get("current_step")))

    # ---- T4: PAUSE durable-first; survives fresh processes (restart sim) ----
    code, out, _ = run_cli(tmp, ["directive", "--run-id", run_a, "PAUSE", "--note", "user pause"])
    check("T4a_pause_ok", code == 0 and out.get("run_status") == "PAUSED", str(out))
    # fresh process #1: state must still be PAUSED (durable, not in-memory)
    _, s, _ = run_cli(tmp, ["status", "--run-id", run_a])
    check("T4b_paused_after_restart", s.get("status") == "PAUSED", str(s.get("status")))
    # ordinary actions denied while paused
    code, out, _ = run_cli(tmp, ["step", "--run-id", run_a, "--current", "x", "--next", "y"])
    check("T4c_step_denied_paused", code == 5 and out.get("status") == "DENIED", str(out))
    code, out, _ = run_cli(tmp, ["send", "--run-id", run_a, "--message", "m"],
                           env_extra={"APC_RUNTIME_INJECT_BRIDGE_FAIL": "1"})
    check("T4d_send_denied_paused", code == 5 and out.get("status") == "RUN_PAUSED", str(out))
    # directive recorded durably
    check("T4e_directive_recorded", (s.get("last_user_directive") or {}).get("action") == "PAUSE",
          str(s.get("last_user_directive")))
    code, out, _ = run_cli(tmp, ["directive", "--run-id", run_a, "RESUME"])
    check("T4f_resume_ok", code == 0 and out.get("run_status") == "RUNNING", str(out))

    # ---- T5: recovery fields readable from state alone ----
    run_cli(tmp, ["step", "--run-id", run_a, "--current", "step-X done", "--next", "do step-Y",
                  "--checkpoint", "ckpt: evidence at /tmp/x"])
    _, s, _ = run_cli(tmp, ["status", "--run-id", run_a])
    needed = ["goal", "r_url", "status", "current_step", "next_action", "checkpoint",
              "last_user_directive", "review_epoch", "metrics"]
    check("T5a_recovery_fields", all(k in s for k in needed),
          "missing: " + ",".join(k for k in needed if k not in s))
    check("T5b_values", s["goal"] == "goal-A" and s["current_step"] == "step-X done"
          and s["checkpoint"]["text"].startswith("ckpt"), "wrong values")

    # ---- T7 failure chain (offline, deterministic seam) ----
    # health cache: seed a READY cache so the chain reaches the transport seam
    (tmp / "health.json").write_text(json.dumps(
        {"ready": True, "detail": "seeded", "checked_at": "x", "checked_epoch": 9e18}), encoding="utf-8")
    env_fail = {"APC_RUNTIME_INJECT_BRIDGE_FAIL": "1"}
    outcomes = []
    for i in range(6):
        code, out, _ = run_cli(tmp, ["send", "--run-id", run_b, "--message", f"attempt {i}"], env_extra=env_fail)
        outcomes.append((code, out.get("status")))
        if out.get("status") == "HARD_BLOCKED":
            break
    # expected: retries fail with BRIDGE_UNHEALTHY-ish status, then HARD_BLOCKED
    check("T7a_reached_hard_blocked", any(st == "HARD_BLOCKED" for _, st in outcomes), str(outcomes))
    # durable: fresh process sees HARD_BLOCKED
    _, sBh, _ = run_cli(tmp, ["status", "--run-id", run_b])
    check("T7b_durable_hard_blocked", sBh.get("status") == "HARD_BLOCKED", str(sBh.get("status")))
    check("T7c_budget_recorded", int(sBh["metrics"].get("bridge_retries", 0)) >= 3, str(sBh["metrics"]))
    # ordinary actions now denied
    code, out, _ = run_cli(tmp, ["step", "--run-id", run_b, "--current", "sneak", "--next", "in"])
    check("T7d_step_denied_blocked", code == 5 and out.get("status") == "DENIED", str(out))
    code, out, _ = run_cli(tmp, ["send", "--run-id", run_b, "--message", "sneak"], env_extra=env_fail)
    # machine-readable denial; run_status must surface HARD_BLOCKED, exit non-zero
    check("T7e_send_denied_blocked", code in (5, 6) and out.get("run_status") == "HARD_BLOCKED"
          and out.get("status") in ("DENIED", "HARD_BLOCKED"), str(out))
    # journal shows the whole chain
    jr = [json.loads(l) for l in (tmp / "runs" / run_b / "journal.jsonl").read_text(encoding="utf-8").splitlines()]
    events = [e["event"] for e in jr]
    check("T7f_journal_chain", "SEND_FAILURE" in events and "HARD_BLOCKED" in events, str(events))

    # ---- R_URL_CHANGE epoch isolation (offline semantics) ----
    URL_C = "https://chatgpt.com/c/cccccccc-1111-2222-3333-666666666666"
    code, out, _ = run_cli(tmp, ["directive", "--run-id", run_a, "R_URL_CHANGE", "--new-r-url", URL_C])
    _, s, _ = run_cli(tmp, ["status", "--run-id", run_a])
    check("T1g_r_url_change", code == 0 and s["r_url"] == URL_C and s["review_epoch"] == 2
          and s["last_r_verdict"] is None and str(2) not in s["evidence_ledger"], str(out))

    # ---- duplicate-send guard semantics (success seam records the fingerprint) ----
    URL_D = "https://chatgpt.com/c/dddddddd-1111-2222-3333-777777777777"
    _, outD, _ = run_cli(tmp, ["start", "--goal", "goal-D", "--r-url", URL_D, "--worker-id", "wD"])
    run_d = outD.get("run_id", "")
    code1, out1, _ = run_cli(tmp, ["send", "--run-id", run_d, "--message", "dup-msg"],
                             env_extra={"APC_RUNTIME_INJECT_BRIDGE_FAIL": "OK"})
    check("C1a_first_attempt_ok", code1 == 0 and out1.get("status") == "OK", str(out1))
    code2, out2, _ = run_cli(tmp, ["send", "--run-id", run_d, "--message", "dup-msg"],
                             env_extra={"APC_RUNTIME_INJECT_BRIDGE_FAIL": "OK"})
    check("C1_duplicate_guard", out2.get("status") == "DUPLICATE_ACTION" and code2 == 5,
          f"first={out1.get('status')} second={out2.get('status')}")
    # advancing the step must lift the guard (same content, new step => allowed)
    run_cli(tmp, ["step", "--run-id", run_d, "--current", "advanced", "--next", "onward"])
    code3, out3, _ = run_cli(tmp, ["send", "--run-id", run_d, "--message", "dup-msg"],
                             env_extra={"APC_RUNTIME_INJECT_BRIDGE_FAIL": "OK"})
    check("C1b_guard_lifted_after_step", code3 == 0 and out3.get("status") == "OK", str(out3))

    # ---- E1/E2/E3: encoding robustness (acceptance rework P0-1/P0-2) ----
    import importlib
    sys.path.insert(0, str(HERE))
    os.environ["APC_RUNTIME_STATE_ROOT"] = str(tmp)
    if "runtime" in sys.modules:
        del sys.modules["runtime"]
    rt = importlib.import_module("runtime")

    # E1: deterministic decoding of hostile byte streams
    wsl_noise = "wsl: 检测到 localhost 代理配置".encode("utf-16-le")
    d = rt.decode_robust(wsl_noise)
    check("E1a_utf16le_noise_decoded", d.startswith("wsl") and "\x00" not in d and "\ufffd" not in d, repr(d))
    d = rt.decode_robust("桥健康".encode("gbk"))
    check("E1b_gbk_chinese_decoded", d == "桥健康", repr(d))
    d = rt.decode_robust(b"Bridge: READY\n")
    check("E1c_ascii_passthrough", d == "Bridge: READY\n", repr(d))
    check("E1d_clean_text", rt.clean_text("a\ufffd\x00b\nc") == "a? b c", repr(rt.clean_text("a\ufffd\x00b\nc")))

    # E2: poisoned blocked_reason (legacy data) must not break status in any read mode
    URL_E2 = "https://chatgpt.com/c/eeeeeeee-1111-2222-3333-888888888888"
    _, outE2, _ = run_cli(tmp, ["start", "--goal", "encoding fixture", "--r-url", URL_E2, "--worker-id", "enc"])
    run_e2 = outE2.get("run_id", "")
    sp = tmp / "runs" / run_e2 / "state.json"
    st = json.loads(sp.read_text(encoding="utf-8"))
    st["status"] = "HARD_BLOCKED"
    st["blocked_reason"] = "桥检查失败\n包含中文、换行、\ufffd 与 \x00 控制符"
    sp.write_text(json.dumps(st, ensure_ascii=False, indent=2), encoding="utf-8")
    check("E2a_state_json_valid", json.loads(sp.read_text(encoding="utf-8"))["status"] == "HARD_BLOCKED", "state invalid")
    code, out, _ = run_cli(tmp, ["status", "--run-id", run_e2])
    check("E2b_status_piped_readable", code == 0 and out.get("run_id") == run_e2
          and out.get("status") == "HARD_BLOCKED" and "blocked_reason" in out, str(out)[:200])
    redir = tmp / "redir_status.json"
    env = dict(os.environ)
    env["APC_RUNTIME_STATE_ROOT"] = str(tmp)
    env.pop("PYTHONIOENCODING", None)
    with open(redir, "wb") as fh:
        subprocess.run([PY, str(RUNTIME), "status", "--run-id", run_e2], stdout=fh,
                       stderr=subprocess.DEVNULL, env=env, timeout=60)
    data = json.loads(redir.read_text(encoding="utf-8"))
    check("E2c_status_redirect_readable", data.get("run_id") == run_e2 and data.get("status") == "HARD_BLOCKED",
          str(data)[:200])
    # E3: fresh process reads metrics of the blocked RUN without error
    code, out, _ = run_cli(tmp, ["metrics", "--run-id", run_e2])
    check("E3_blocked_run_metrics_readable", code == 0 and out.get("run_status") == "HARD_BLOCKED", str(out)[:200])

    # ---- U4/U5: attachment failure semantics (acceptance rework 2) ----
    # U4a: UPLOAD_FAIL + dead session -> bounded replacements with recorded
    # reasons -> durable HARD_BLOCKED; ordinary actions denied afterwards.
    _, out4a, _ = run_cli(tmp, ["start", "--goal", "u4a", "--r-url", URL_D, "--worker-id", "u4a"])
    run_u4a = out4a.get("run_id", "")
    code, out, _ = run_cli(tmp, ["send", "--run-id", run_u4a, "--message", "u4a",
                                  "--file", str(HERE / "runtime.py")],
                           env_extra={"APC_RUNTIME_INJECT_BRIDGE_FAIL": "UPLOAD"})
    check("U4a_upload_chain_hard_blocked", out.get("status") == "HARD_BLOCKED" and code == 6, str(out)[:200])
    _, s4a, _ = run_cli(tmp, ["status", "--run-id", run_u4a])
    check("U4a_durable", s4a.get("status") == "HARD_BLOCKED"
          and int(s4a["metrics"].get("session_recoveries", 0)) >= 3
          and "SESSION_DEAD_DURING_UPLOAD" in str(s4a.get("blocked_reason")), str(s4a.get("blocked_reason"))[:160])
    jr4a = [json.loads(l) for l in (tmp / "runs" / run_u4a / "journal.jsonl").read_text(encoding="utf-8").splitlines()]
    repl = [e for e in jr4a if e["event"] == "SESSION_REPLACED"]
    check("U4a_replacement_reasons_recorded", len(repl) >= 2
          and all(e.get("reason", "").startswith("SESSION_DEAD_DURING_UPLOAD") for e in repl), str(repl)[:200])
    code, out, _ = run_cli(tmp, ["step", "--run-id", run_u4a, "--current", "x", "--next", "y"])
    check("U4a_step_denied_after_block", code == 5 and out.get("status") == "DENIED", str(out)[:120])

    # U4b: UPLOAD_FAIL + HEALTHY session -> bounded IN-PLACE retries, NO session
    # replacement, window never rebuilt; then durable HARD_BLOCKED.
    _, out4b, _ = run_cli(tmp, ["start", "--goal", "u4b", "--r-url", URL_D, "--worker-id", "u4b"])
    run_u4b = out4b.get("run_id", "")
    code, out, _ = run_cli(tmp, ["send", "--run-id", run_u4b, "--message", "u4b",
                                  "--file", str(HERE / "runtime.py")],
                           env_extra={"APC_RUNTIME_INJECT_BRIDGE_FAIL": "UPLOAD_HEALTHY"})
    check("U4b_upload_chain_hard_blocked", out.get("status") == "HARD_BLOCKED" and code == 6, str(out)[:200])
    _, s4b, _ = run_cli(tmp, ["status", "--run-id", run_u4b])
    check("U4b_no_rebuild", int(s4b["metrics"].get("session_recoveries", 0)) == 0
          and int(s4b["metrics"].get("upload_retries", 0)) >= 3
          and "no rebuild" in str(s4b.get("blocked_reason")), json.dumps(s4b["metrics"])[:200])
    jr4b = [json.loads(l) for l in (tmp / "runs" / run_u4b / "journal.jsonl").read_text(encoding="utf-8").splitlines()]
    inplace = [e for e in jr4b if e.get("action") == "IN_PLACE_RETRY" and e.get("kind") == "attachment"]
    check("U4b_inplace_retries_journaled", len(inplace) >= 3
          and not any(e["event"] == "SESSION_REPLACED" for e in jr4b), str(inplace)[:200])

    # U5: ordinary text-only review never triggers upload (explicit semantics).
    _, out5, _ = run_cli(tmp, ["start", "--goal", "u5", "--r-url", URL_D, "--worker-id", "u5"])
    run_u5 = out5.get("run_id", "")
    code, out, _ = run_cli(tmp, ["send", "--run-id", run_u5, "--message", "u5 text review"],
                           env_extra={"APC_RUNTIME_INJECT_BRIDGE_FAIL": "OK"})
    check("U5_text_only_no_upload", code == 0 and out.get("attachment_mode") == "text-only"
          and out.get("files_uploaded") == [], str(out)[:200])

    # ---- M1/M2: multiline message integrity (run.cmd newline-truncation bug) ----
    body = "ML_LINE_ONE header\n\nML_LINE_TWO body\nML_LINE_THREE closing"
    mfile = tmp / "ml_body.txt"
    mfile.write_text(body, encoding="utf-8")
    code, out, _ = run_cli(tmp, ["send", "--run-id", run_u5, "--message-file", str(mfile)],
                           env_extra={"APC_RUNTIME_INJECT_BRIDGE_FAIL": "OK"})
    sent_files = sorted((tmp / "runs" / run_u5).glob("msg_*"))
    delivered = [f.read_text(encoding="utf-8") for f in sent_files]
    check("M1_message_file_delivered_full", code == 0 and out.get("status") == "OK"
          and body in delivered, repr(delivered)[-200:])
    code, out, _ = run_cli(tmp, ["send", "--run-id", run_u5, "--message", "line1\nline2"],
                           env_extra={"APC_RUNTIME_INJECT_BRIDGE_FAIL": "OK"})
    check("M2_multiline_message_rejected", code == 2 and out.get("status") == "MULTILINE_MESSAGE_UNSAFE", str(out)[:160])

    # ---- PB: P0-A browser bootstrap + P0-B production entry (offline) ----
    def _msys(p) -> str:
        s = str(p).replace("\\", "/")
        return "/" + s[0].lower() + s[2:] if len(s) > 1 and s[1] == ":" else s

    # PB1: health self-bootstraps the canonical chain when wrapper says 'no browser'
    pb1 = Path(tempfile.mkdtemp(prefix="apc_rt_v1_pb1_"))
    mark1 = pb1 / "browser_registered.flag"
    wrap1 = pb1 / "stub_wrapper.sh"
    wrap1.write_text(
        "#!/bin/bash\ncase \"$1\" in status)\n"
        f"  if [ -f '{_msys(mark1)}' ]; then\n"
        "    echo 'Bridge: READY'; echo 'Browser: chrome'; echo 'Instance: deadbeef'; echo 'Upload: READY'; exit 0\n"
        "  else\n    echo 'Bridge: FAIL (no browser)'; exit 1\n  fi;; *) exit 2;; esac\n",
        encoding="utf-8")
    ensure_ok = pb1 / "stub_ensure_ok.sh"
    ensure_ok.write_text(f"touch '{_msys(mark1)}'\necho 'RUNTIME_BROWSER_INST=deadbeef'\n", encoding="utf-8")
    code, out, _ = run_cli(pb1, ["health", "--force"],
                           env_extra={"APC_RUNTIME_BRIDGE_WRAPPER": _msys(wrap1),
                                      "APC_RUNTIME_BROWSER_ENSURE": str(ensure_ok)})
    check("PB1_health_bootstraps_browser", code == 0 and out.get("ready") is True
          and out.get("browser_bootstrapped") is True, str(out)[:200])

    # PB2: genuine bootstrap failure -> stable RUNTIME_BROWSER_BLOCKED
    pb2 = Path(tempfile.mkdtemp(prefix="apc_rt_v1_pb2_"))
    wrap2 = pb2 / "stub_wrapper_fail.sh"
    wrap2.write_text("#!/bin/bash\ncase \"$1\" in status) echo 'Bridge: FAIL (no browser)'; exit 1;; *) exit 2;; esac\n",
                     encoding="utf-8")
    ensure_bl = pb2 / "stub_ensure_blocked.sh"
    ensure_bl.write_text("echo 'RUNTIME_BROWSER_ENSURE=BLOCKED:canonical browser dependency missing'\n", encoding="utf-8")
    code, out, _ = run_cli(pb2, ["health", "--force"],
                           env_extra={"APC_RUNTIME_BRIDGE_WRAPPER": _msys(wrap2),
                                      "APC_RUNTIME_BROWSER_ENSURE": _msys(ensure_bl)})
    check("PB2_browser_blocked_stable", code == 1 and out.get("status") == "BRIDGE_UNHEALTHY"
          and "RUNTIME_BROWSER_BLOCKED" in str(out.get("detail"))
          and out.get("browser_bootstrapped") is False, str(out)[:200])

    # PB3/PB4/PB5: production entry validations + blocked-bridge creates NO run
    pb3 = Path(tempfile.mkdtemp(prefix="apc_rt_v1_pb3_"))
    goal_f = pb3 / "goal.txt"
    goal_f.write_text("Count from 1 to 5 and write the answer.", encoding="utf-8")
    code, out, _ = run_cli(pb3, ["work", "--goal-file", str(goal_f)])
    check("PB3_work_requires_r_url", code == 3 and out.get("status") == "MISSING_R_URL", str(out)[:160])
    code, out, _ = run_cli(pb3, ["work", "--goal-file", str(pb3 / "nope.txt"), "--r-url", URL_D])
    check("PB4_work_goal_file_must_exist", code == 2 and out.get("status") == "FILE_NOT_FOUND", str(out)[:160])
    code, out, _ = run_cli(pb3, ["work", "--goal-file", str(goal_f), "--r-url", URL_D],
                           env_extra={"APC_RUNTIME_BRIDGE_WRAPPER": _msys(wrap2),
                                      "APC_RUNTIME_BROWSER_ENSURE": str(ensure_bl)})
    check("PB5_work_blocked_no_run", code == 1 and out.get("status") == "RUNTIME_BROWSER_BLOCKED"
          and not (pb3 / "runs").exists(), str(out)[:160])

    # PB6/PB7/PB8: work creates the RUN (goal durable, next_command printed);
    # report returns ONE clean JSON and closes the loop up to verdict parsing.
    pb4 = Path(tempfile.mkdtemp(prefix="apc_rt_v1_pb4_"))
    wrap_ok = pb4 / "stub_wrapper_ok.sh"
    wrap_ok.write_text("#!/bin/bash\ncase \"$1\" in status) echo 'Bridge: READY'; echo 'Browser: chrome'; "
                       "echo 'Instance: deadbeef'; echo 'Upload: READY'; exit 0;; *) exit 2;; esac\n",
                       encoding="utf-8")
    goal4 = pb4 / "goal.txt"
    goal4.write_text("Say hello to the reviewer.", encoding="utf-8")
    code, out, _ = run_cli(pb4, ["work", "--goal-file", str(goal4), "--r-url", URL_D, "--worker-id", "pw"],
                           env_extra={"APC_RUNTIME_BRIDGE_WRAPPER": _msys(wrap_ok)})
    rid4 = out.get("run_id", "")
    check("PB6_work_creates_run", code == 0 and rid4.startswith("RUN-")
          and "report --run-id" in str(out.get("next_command")), str(out)[:200])
    _, s4, _ = run_cli(pb4, ["status", "--run-id", rid4])
    check("PB7_work_goal_durable", s4.get("goal") == "Say hello to the reviewer."
          and s4.get("r_url") == URL_D and s4.get("worker_identity") == "pw", str(s4)[:200])
    rep = pb4 / "report1.txt"
    rep.write_text("hello done: 1 2 3 4 5", encoding="utf-8")
    code, out, _ = run_cli(pb4, ["report", "--run-id", rid4, "--message-file", str(rep)],
                           env_extra={"APC_RUNTIME_BRIDGE_WRAPPER": _msys(wrap_ok),
                                      "APC_RUNTIME_INJECT_BRIDGE_FAIL": "OK"})
    check("PB8_report_single_json_loop", code == 0 and out.get("status") == "REPORTED"
          and out.get("last_r_verdict") == "NO_VERDICT"
          and "report --run-id" in str(out.get("next_command"))
          and out.get("run_status") == "RUNNING", str(out)[:250])

    # PB9: ensure-script contract — explicit canonical port, warm-wake tab nudge
    # (tabs.onUpdated SW wake), chrome-running context + query-failure diagnostics.
    if "runtime" in sys.modules:
        del sys.modules["runtime"]
    os.environ["APC_RUNTIME_STATE_ROOT"] = str(tmp)
    os.environ.pop("APC_RUNTIME_BROWSER_ENSURE", None)
    rt9 = importlib.import_module("runtime")
    scr = rt9.ensure_browser_script()
    check("PB9_ensure_script_contract",
          "daemon start --port 52900" in scr and "tasklist.exe" in scr
          and "RUNTIME_BROWSER_CTX" in scr and "about:blank" in scr
          and "netstat.exe" in scr and "daemon stop" in scr
          and "--user-data-dir" not in scr and "--load-extension" not in scr, scr[:200])

    # PB10: host-PATH independence — the health probe must resolve the frozen
    # wrapper's bare awk/grep even when the dispatched environment's PATH has
    # no Git toolchain at all (real weak-worker counter-example: deterministic
    # "no browser" purely from a PATH-less host chain).
    pb5 = Path(tempfile.mkdtemp(prefix="apc_rt_v1_pb5_"))
    wrap_awk = pb5 / "stub_wrapper_awk.sh"
    wrap_awk.write_text("#!/bin/bash\ncase \"$1\" in status)\n"
                        "  X=$(printf 'INSTANCE  deadbeef  chrome  0.1.5  -  0\\n' | awk 'NR==1{print $2}')\n"
                        "  if [ \"$X\" = \"deadbeef\" ]; then\n"
                        "    echo 'Bridge: READY'; echo 'Browser: chrome'; echo 'Instance: deadbeef'; "
                        "echo 'Upload: READY'; exit 0\n"
                        "  else echo 'Bridge: FAIL (awk)'; exit 1\n  fi;; *) exit 2;; esac\n",
                        encoding="utf-8")
    code, out, _ = run_cli(pb5, ["health", "--force"],
                           env_extra={"APC_RUNTIME_BRIDGE_WRAPPER": _msys(wrap_awk),
                                      "PATH": r"C:\Windows\System32"})
    check("PB10_health_path_independent", code == 0 and out.get("ready") is True
          and out.get("cached") is False, str(out)[:200])
    # PB10b: contract — every bash script the Runtime builds embeds the PATH prologue
    check("PB10b_path_prologue_in_all_scripts",
          scr.count(rt9.PATH_PROLOGUE) >= 1 and "export PATH=" in rt9.PATH_PROLOGUE,
          rt9.PATH_PROLOGUE)

    print("\n".join(RESULTS))
    print(f"\nTOTAL={PASS_COUNT + FAIL_COUNT} PASS={PASS_COUNT} FAIL={FAIL_COUNT}")
    return 0 if FAIL_COUNT == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
