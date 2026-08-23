"""WEAK_WORKER_SIM — a fresh top-level worker process with ZERO knowledge of the
build session. It only ever reads:
  1) bootstrap.json (fixed resource registry)
  2) `run status --run-id <RID>` output
and then mechanically follows the state machine. Full transcript is written to
state/<RID>_weak_worker_transcript.txt for the 'no bridge internals' audit.

Usage: python weak_worker_sim.py <RUN_ID>
"""
import json, subprocess, sys, os
from datetime import datetime, timezone
from pathlib import Path

RUN = r"E:\WB\tools\ai-production-control\runtime\run.cmd"
BOOTSTRAP = Path(r"E:\WB\tools\ai-production-control\runtime\bootstrap.json")
FORBIDDEN = ["bsk", "daemon", "52900", "yz_", "session stop", "marker", "click", "navigate"]
TRANSCRIPT = []


def log(line: str) -> None:
    stamp = datetime.now(timezone.utc).isoformat(timespec="seconds")
    TRANSCRIPT.append(f"{stamp} {line}")
    print(line)


def run_cli(argv: list) -> tuple[int, dict]:
    cmd = [RUN, *argv]
    log("CALL: run " + " ".join(argv))
    proc = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace")
    try:
        out = json.loads(proc.stdout)
    except ValueError:
        out = {"_raw": proc.stdout[:500]}
    log(f"RC={proc.returncode} STATUS={out.get('status')} RUN_STATUS={out.get('run_status') or out.get('status')}")
    return proc.returncode, out


def main() -> int:
    rid = sys.argv[1]
    log(f"WEAK_WORKER_SIM start; input RUN_ID={rid} only. No chat history available.")

    # Step 1: read the fixed registry
    reg = json.loads(BOOTSTRAP.read_text(encoding="utf-8"))
    log(f"BOOTSTRAP read: entry={reg['runtime_entry']} state_root={reg['state_root']}")
    assert reg["runtime_entry"] == RUN, "registry entry mismatch"

    # Step 2: status is the only authority
    code, state = run_cli(["status", "--run-id", rid])
    if code != 0:
        log("FATAL: cannot read status; stop.")
        return 1
    rs = state.get("status")
    log(f"AUTHORITATIVE STATE: status={rs} goal={state.get('goal','')[:60]!r} "
        f"step={state.get('current_step','')[:60]!r}")
    log(f"NEXT_ACTION={state.get('next_action','')[:160]!r}")
    log(f"R_URL={state.get('r_url')} LAST_VERDICT={state.get('last_r_verdict')}")

    # Step 3: branch mechanically
    if rs == "PAUSED":
        log("STATE=PAUSED -> STOP. Do nothing. Wait for user RESUME directive. "
            "This sim refuses to continue (T5 requirement).")
        return 0
    if rs in ("STOPPED", "DONE", "HARD_BLOCKED"):
        log(f"STATE={rs} -> terminal/blocked; report to user, do nothing else.")
        return 0
    if rs != "RUNNING":
        log(f"UNKNOWN STATE {rs} -> stop.")
        return 1

    # Step 4: RUNNING with verdict PASS -> finalize
    if state.get("last_r_verdict") == "PASS":
        code, out = run_cli(["done", "--run-id", rid])
        log(f"FINALIZE result: {out.get('status')} run_status={out.get('run_status')}")
        if out.get("run_status") == "DONE":
            code2, m = run_cli(["metrics", "--run-id", rid])
            log(f"FINAL METRICS: {json.dumps(m.get('metrics', {}), ensure_ascii=False)}")
        return 0

    log("RUNNING without PASS -> a full worker would continue next_action work here; "
        "sim has no task capability, stopping cleanly.")
    return 0


if __name__ == "__main__":
    rid = sys.argv[1] if len(sys.argv) > 1 else ""
    rc = main() if rid else 2
    out_path = Path(rf"E:\WB\state\ai-production-control\runtime-v1\{rid or 'unknown'}_weak_worker_transcript.txt")
    out_path.write_text("\n".join(TRANSCRIPT) + "\n", encoding="utf-8")
    # self-audit: transcript must not show any bridge-internal operation by the worker
    bad = [w for w in FORBIDDEN if w.lower() in "\n".join(TRANSCRIPT).lower()]
    print(f"TRANSCRIPT={out_path}")
    print(f"BRIDGE_INTERNAL_TOUCHED={bad if bad else 'NONE'}")
    sys.exit(rc)
