#!/usr/bin/env python3
"""weak-runtime-v1 — Production Runtime Facade for frozen ChatGPT Bridge.

Single production entry for weak Workers. Internals (browser daemon, session
machinery, marker protocol, recovery) are fully encapsulated here; weak
Workers only see the CLI commands below and the durable RUN state.

Commands (all state-changing/R-touching commands require explicit --run-id):
  start     --goal G --r-url URL [--worker-id ID]   create a RUN (R_URL mandatory)
  status    --run-id ID                             print durable state
  step      --run-id ID --current T --next T [--checkpoint T]
  directive --run-id ID ACTION [--new-r-url URL] [--note T]
            ACTION in PAUSE|RESUME|STOP|R_URL_CHANGE|CHANGE_SCOPE|USER_OVERRIDE
  send      --run-id ID --message T [--file P ...] [--timeout N]
  recv      --run-id ID                             recapture last reply, reparse verdict
  done      --run-id ID                             finalize (only after R verdict PASS)
  metrics   --run-id ID                             print runtime metrics
  health    [--force]                               cached bridge health check

Durable state: STATE_ROOT/runs/<RUN_ID>/state.json is the ONLY recovery
authority; journal.jsonl is append-only audit. All control directives are
committed durably BEFORE any transition is applied.
"""
from __future__ import annotations

import argparse
import contextlib
import hashlib
import io
import json
import os
import re
import subprocess
import sys
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path

# ---------------------------------------------------------------------------
# Fixed environment (hidden internals — weak Workers never need these)
# ---------------------------------------------------------------------------
# APC_RUNTIME_STATE_ROOT / APC_RUNTIME_YZ_LIB / APC_RUNTIME_BRIDGE_WRAPPER are
# test seams only (Batch3 acceptance, deterministic offline failure chain).
# Production defaults always point at the frozen bridge; weak Workers never set these.
STATE_ROOT = Path(os.environ.get("APC_RUNTIME_STATE_ROOT", r"E:\WB\state\ai-production-control\runtime-v1"))
RUNS_ROOT = STATE_ROOT / "runs"
HEALTH_FILE = STATE_ROOT / "health.json"
GLOBAL_LOG = STATE_ROOT / "cli_log.jsonl"

BASH = r"C:\Program Files\Git\bin\bash.exe"
YZ_LIB = os.environ.get("APC_RUNTIME_YZ_LIB", "/e/WB/workspace/2026-08-16-21-49-32/work/yz_lib.sh")
BRIDGE_WRAPPER = os.environ.get("APC_RUNTIME_BRIDGE_WRAPPER", "/c/Users/17838/.local/bin/chatgpt_bridge")

# Canonical browser bootstrap chain (P0-A). Per the frozen Bridge handover
# (§1: production Chrome default profile, dev extension instance 7da8483f —
# the only one, never create a second instance), the canonical browser is the
# production Chrome whose DEFAULT profile already carries the dev extension
# installed; the extension auto-connects to the baked ws://127.0.0.1:52900 and
# registers with its persistent instance id. Cold start therefore launches the
# default-profile Chrome with NO --user-data-dir/--load-extension flags (those
# would create a second dev instance and are forbidden). The Runtime owns this
# chain; weak Workers never see or set any of it. APC_RUNTIME_* overrides are
# offline test seams only.
BSK_EXE = os.environ.get("APC_RUNTIME_BSK_EXE", "/e/WB/tools/bsk-file-bridge/repo/target/release/bsk.exe")
BSK_HOME_DIR = os.environ.get("APC_RUNTIME_BSK_HOME", "/e/WB/tools/bsk-file-bridge/bsk-home")
CHROME_BIN = os.environ.get("APC_RUNTIME_CHROME", "/c/Program Files/Google/Chrome/Application/chrome.exe")
CHROME_EXT = os.environ.get("APC_RUNTIME_CHROME_EXT", "/e/WB/tools/bsk-file-bridge/repo/apps/extension/dist/chrome-mv3")
BROWSER_BOOTSTRAP_WAIT_SEC = 90

# Host-PATH independence (real counter-example 2026-08-18 23:5x: weak worker's
# PowerShell→run.cmd→python→bash -c chain lost Git's /usr/bin, so the frozen
# wrapper's bare `awk` failed -> permanent "no browser" -> deterministic
# RUNTIME_BROWSER_BLOCKED, while the identical manual chain was READY). Every
# bash script the Runtime builds embeds this authoritative PATH prologue, so
# awk/grep/tr/date (Git /usr/bin) and tasklist/netstat (System32) resolve
# regardless of what PATH the host dispatched with.
PATH_PROLOGUE = 'export PATH="/usr/bin:/mingw64/bin:$PATH:/c/Windows/System32"'

HEALTH_TTL_SEC = 300
MAX_BRIDGE_RETRIES = 3
MAX_SESSION_RECOVERIES = 2
MAX_UPLOAD_RETRIES = 2
MAX_VERDICT_REQUERIES = 2
DEFAULT_SEND_TIMEOUT = 300
LOCK_STALE_SEC = 180

R_URL_RE = re.compile(r"^https://chatgpt\.com/c/[A-Za-z0-9-]{8,}$")
RUN_ID_RE = re.compile(r"^RUN-[0-9]{8}-[0-9]{6}-[0-9a-f]{4}$")
CONV_ID_RE = re.compile(r"/c/([A-Za-z0-9-]+)")

INTERNAL_STRINGS = [
    YZ_LIB,
    BRIDGE_WRAPPER,
    "bsk-file-bridge",
    "bsk.exe",
    "BSK_HOME",
    "52900",
    "yz_",
    "daemon",
]

EXIT_OK = 0
EXIT_ERR = 1
EXIT_USAGE = 2
EXIT_MISSING_R_URL = 3
EXIT_RUN_NOT_FOUND = 4
EXIT_DENIED = 5
EXIT_HARD_BLOCKED = 6

RUN_STATUSES = ("RUNNING", "PAUSED", "STOPPED", "HARD_BLOCKED", "DONE")


# ---------------------------------------------------------------------------
# Small utilities
# ---------------------------------------------------------------------------
def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def sanitize(text: str) -> str:
    for s in INTERNAL_STRINGS:
        text = text.replace(s, "<bridge-internal>")
    return clean_text(text)[:2000]


def clean_text(text: str) -> str:
    """Deterministic text hygiene: no U+FFFD, no NUL/control chars, single-line.
    Guarantees anything persisted into durable state or emitted on stdout stays
    valid Unicode/JSON regardless of source encoding accidents."""
    text = text.replace("\ufffd", "?")
    text = "".join(ch if (ch >= " " or ch in "\n\t") else " " for ch in text)
    return " ".join(text.split())


def decode_robust(raw: bytes) -> str:
    """Decode subprocess bytes without poisoning: UTF-16 (WSL/console API noise)
    detected via NUL bytes, then UTF-8, then GBK (Windows console), replace only
    as the last resort."""
    if not raw:
        return ""
    if b"\x00" in raw:
        for enc in ("utf-16-le", "utf-16-be", "utf-16"):
            try:
                return raw.decode(enc)
            except (UnicodeDecodeError, UnicodeError):
                continue
    for enc in ("utf-8", "gbk"):
        try:
            return raw.decode(enc)
        except (UnicodeDecodeError, UnicodeError):
            continue
    return raw.decode("utf-8", errors="replace")


def force_utf8_stdio() -> None:
    """CLI stdout/stderr are ALWAYS UTF-8, independent of the console codepage.
    Without this, non-GBK-representable chars crash piped/redirected reads."""
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError, OSError):
            pass


def emit(obj: dict) -> None:
    print(json.dumps(obj, ensure_ascii=False, indent=2, default=str))


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def atomic_write_text(path: Path, text: str) -> None:
    """Durable write: tmp file + flush + fsync + atomic replace."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + f".tmp.{uuid.uuid4().hex[:8]}")
    with open(tmp, "w", encoding="utf-8") as fh:
        fh.write(text)
        fh.flush()
        os.fsync(fh.fileno())
    os.replace(tmp, path)


def append_jsonl(path: Path, obj: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "a", encoding="utf-8") as fh:
        fh.write(json.dumps(obj, ensure_ascii=False, default=str) + "\n")
        fh.flush()
        os.fsync(fh.fileno())


def to_posix(win_path: str) -> str:
    p = win_path.replace("\\", "/")
    if len(p) >= 2 and p[1] == ":":
        p = "/" + p[0].lower() + p[2:]
    return p


def cli_log(argv: list[str], run_id: str | None, status: str, exit_code: int) -> None:
    try:
        append_jsonl(
            GLOBAL_LOG,
            {"ts": utc_now(), "entry": "RUNTIME_ENTRY_REACHED", "argv": argv, "run_id": run_id,
             "status": status, "exit_code": exit_code},
        )
    except OSError:
        pass


# ---------------------------------------------------------------------------
# Per-RUN lock (serializes every write; stale break after LOCK_STALE_SEC)
# ---------------------------------------------------------------------------
class RunLock:
    def __init__(self, run_id: str):
        self.lock_path = RUNS_ROOT / run_id / ".lock"
        self.acquired = False

    def _try_acquire(self) -> bool:
        try:
            fd = os.open(self.lock_path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        except FileExistsError:
            return False
        with os.fdopen(fd, "w") as fh:
            fh.write(json.dumps({"pid": os.getpid(), "ts": time.time()}))
        self.acquired = True
        return True

    def _break_if_stale(self) -> None:
        try:
            data = json.loads(self.lock_path.read_text(encoding="utf-8"))
            if time.time() - float(data.get("ts", 0)) > LOCK_STALE_SEC:
                self.lock_path.unlink(missing_ok=True)
        except (OSError, ValueError):
            self.lock_path.unlink(missing_ok=True)

    def __enter__(self) -> "RunLock":
        deadline = time.time() + 30
        while time.time() < deadline:
            if self._try_acquire():
                return self
            self._break_if_stale()
            time.sleep(0.5)
        raise RuntimeError("run lock busy for more than 30s")

    def __exit__(self, *exc) -> None:
        if self.acquired:
            self.lock_path.unlink(missing_ok=True)


# ---------------------------------------------------------------------------
# State management (state.json = sole recovery authority)
# ---------------------------------------------------------------------------
def run_dir(run_id: str) -> Path:
    if not RUN_ID_RE.match(run_id or ""):
        raise ValueError(f"invalid run id: {run_id!r}")
    return RUNS_ROOT / run_id


def load_state(run_id: str) -> dict:
    path = run_dir(run_id) / "state.json"
    if not path.exists():
        raise FileNotFoundError(run_id)
    return json.loads(path.read_text(encoding="utf-8"))


def save_state(state: dict) -> None:
    state["revision"] = int(state.get("revision", 0)) + 1
    state["updated_at"] = utc_now()
    atomic_write_text(run_dir(state["run_id"]) / "state.json",
                      json.dumps(state, ensure_ascii=False, indent=2, default=str))


def journal(run_id: str, event: str, **kw) -> None:
    append_jsonl(run_dir(run_id) / "journal.jsonl", {"ts": utc_now(), "event": event, **kw})


def require_status(state: dict, allowed: tuple[str, ...]) -> None:
    if state["status"] not in allowed:
        raise PermissionError(state["status"])


def allowed_actions(state: dict) -> list[str]:
    s = state["status"]
    if s == "RUNNING":
        return ["step", "send", "report", "recv",
                "directive(PAUSE|STOP|R_URL_CHANGE|CHANGE_SCOPE|USER_OVERRIDE)", "done(if verdict=PASS)"]
    if s == "PAUSED":
        return ["status", "directive(RESUME|STOP|USER_OVERRIDE)"]
    if s == "HARD_BLOCKED":
        return ["status", "metrics", "directive(USER_OVERRIDE)"]
    if s == "STOPPED":
        return ["status", "metrics", "directive(USER_OVERRIDE)"]
    return ["status", "metrics"]


def hard_block(state: dict, reason: str) -> None:
    state["status"] = "HARD_BLOCKED"
    state["blocked_reason"] = sanitize(reason)
    state["next_action"] = "HARD_BLOCKED: stop and report to user with this state file. Do NOT attempt alternative bridge routes."
    sid = (state.get("session") or {}).get("sid") or ""
    if sid:
        # Release the runtime-managed session so a blocked RUN leaks no resources.
        try:
            bash_run(session_cleanup_script(sid, state.get("r_url", "")), timeout=60)
        except (subprocess.TimeoutExpired, OSError):
            pass
        state["session"] = {"sid": None, "epoch": state["review_epoch"]}
    journal(state["run_id"], "HARD_BLOCKED", reason=state["blocked_reason"])
    save_state(state)


# ---------------------------------------------------------------------------
# Bridge health (cached fast path)
# ---------------------------------------------------------------------------
def bash_run(script: str, timeout: float) -> subprocess.CompletedProcess:
    seam = os.environ.get("APC_RUNTIME_INJECT_BRIDGE_FAIL", "")
    if seam == "1":
        # Deterministic failure seam (Batch3 T7): every bridge call fails at the
        # facade boundary so the full failure chain can be proven offline without
        # ever touching the real bridge.
        return subprocess.CompletedProcess([BASH], 1, "", "RUNTIME_INJECTED_BRIDGE_FAIL")
    if seam == "OK":
        # Deterministic success seam: transport "succeeds" but produces no reply
        # content, so verdict parsing yields NO_VERDICT. Real bridge untouched.
        return subprocess.CompletedProcess([BASH], 0, "RUNTIME_SID=seam\nRUNTIME_SEND=DONE\n", "")
    if seam in ("UPLOAD", "UPLOAD_HEALTHY"):
        # Deterministic attachment-failure seams (U4): every transport attempt
        # reports UPLOAD_FAIL at the upload stage. The session-health probe
        # reports ABSENT (UPLOAD) or healthy (UPLOAD_HEALTHY, matched to the
        # offline test's fixture R_URL) so both recovery branches are provable
        # offline. Real bridge untouched.
        if "SESS_HEALTH" in script:
            if seam == "UPLOAD_HEALTHY":
                return subprocess.CompletedProcess(
                    [BASH], 0,
                    "SESS_HEALTH=URL=https://chatgpt.com/c/dddddddd-1111-2222-3333-777777777777 GEN=IDLE\n", "")
            return subprocess.CompletedProcess([BASH], 0, "SESS_HEALTH=ABSENT\n", "")
        return subprocess.CompletedProcess(
            [BASH], 0,
            "RUNTIME_SID=seam\nRUNTIME_UPLOAD_FAIL=probe.txt stage=upload raw=injected\n", "")
    return subprocess.run(
        [BASH, "-c", script],
        capture_output=True, text=True, encoding="utf-8", errors="replace",
        timeout=timeout,
    )


def bridge_health(force: bool = False) -> dict:
    cache = {}
    if HEALTH_FILE.exists():
        try:
            cache = json.loads(HEALTH_FILE.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            cache = {}
    age = time.time() - float(cache.get("checked_epoch", 0))
    if not force and cache.get("ready") and age < HEALTH_TTL_SEC:
        return {"ready": True, "cached": True, "age_sec": round(age, 1), "detail": cache.get("detail", "")}
    if not Path(BASH).exists():
        detail = ("RUNTIME_ENV_BLOCKED: canonical dependency missing: " + BASH +
                  " (Runtime owns its launcher; do not substitute shells or edit PATH)")
        atomic_write_text(HEALTH_FILE, json.dumps(
            {"ready": False, "detail": sanitize(detail), "checked_at": utc_now(), "checked_epoch": time.time()}))
        return {"ready": False, "cached": False, "detail": sanitize(detail)}
    try:
        # Byte-mode probe: stdout/stderr decoded separately and robustly so that
        # environment noise (e.g. UTF-16LE WSL proxy warnings) can never be
        # mistaken for the bridge health root cause.
        # No second shell hop: the wrapper is sourced inside the already-absolute
        # Git bash, so there is zero PATH-based launcher resolution.
        proc = subprocess.run([BASH, "-c", f"set -u\n{PATH_PROLOGUE}\nsource {BRIDGE_WRAPPER} status"],
                              capture_output=True, timeout=60)
        stdout = clean_text(decode_robust(proc.stdout))
        stderr = clean_text(decode_robust(proc.stderr))
        ready = proc.returncode == 0 and "Bridge: READY" in stdout
        status_lines = [l.strip() for l in stdout.splitlines()
                        if re.match(r"^(Bridge|Browser|Instance|Upload):", l.strip())]
        if ready and status_lines:
            detail = "; ".join(status_lines)
        elif status_lines:
            detail = "wrapper reported not-ready: " + "; ".join(status_lines) + f" (exit={proc.returncode})"
        elif stdout:
            detail = "wrapper stdout without status line: " + stdout[:300]
        else:
            tail = (" | stderr tail: " + stderr[-200:]) if stderr else ""
            detail = ("ENV_NOISE_ONLY: wrapper produced no status output; environment warning "
                      "suppressed as non-root-cause" + tail)
    except subprocess.TimeoutExpired:
        ready, detail = False, "health check timeout"
    except OSError as exc:
        ready, detail = False, f"health check error: {exc}"
    atomic_write_text(HEALTH_FILE, json.dumps(
        {"ready": ready, "detail": sanitize(detail), "checked_at": utc_now(), "checked_epoch": time.time()}))
    return {"ready": ready, "cached": False, "detail": sanitize(detail)}


# ---------------------------------------------------------------------------
# Browser bootstrap (P0-A): the Runtime owns the prerequisite chain
#   daemon -> browser instance -> extension registration
# and never assumes a browser pre-exists. Only the canonical, historically
# proven chrome-up path is used; there is no second bridge/browser design.
# ---------------------------------------------------------------------------
def ensure_browser_script() -> str:
    seam = os.environ.get("APC_RUNTIME_BROWSER_ENSURE", "")
    if seam:
        # Offline test seam: replace the bootstrap script wholesale.
        return Path(seam).read_text(encoding="utf-8", errors="replace")
    return f"""set -u
{PATH_PROLOGUE}
export BSK_HOME="{BSK_HOME_DIR}"
DEV="{BSK_EXE}"
CHROME_WS=0   # 1 = a chrome.exe process holds an ESTABLISHED conn to 52900
DRESTART=0    # 1 = daemon-view desync recovery was executed
LASTOUT=""

chrome_count() {{ tasklist.exe /FI "IMAGENAME eq chrome.exe" /FO CSV /NH 2>/dev/null | grep -c '"chrome.exe"'; }}
chrome_holds_ws() {{
  # any ESTABLISHED conn to the canonical port owned by a chrome.exe pid
  for pid in $(netstat.exe -ano 2>/dev/null | awk '$3 ~ /:52900$/ && $4 == "ESTABLISHED" {{print $5}}' | sort -u); do
    tasklist.exe /FI "PID eq $pid" /FO CSV /NH 2>/dev/null | grep -q '"chrome.exe"' && return 0
  done
  return 1
}}
poll_inst() {{
  OUT=$("$DEV" browsers 2>&1)
  LASTOUT=$(printf '%s' "$OUT" | tr -d '\\r' | tail -1)
  printf '%s' "$OUT" | awk 'NR==2{{print $1}}'
}}

# prerequisite 1: canonical daemon, explicit port (idempotent; the exact form
# dev_env.sh daemon-up uses, so the port can never drift)
"$DEV" daemon start --port 52900 >/dev/null 2>&1 || true

# prerequisite 2+3: browser instance registered by the extension handshake?
INST=$(poll_inst)

# ---- W1: canonical launch/nudge + bounded poll ----
# Chrome OFF -> fresh default-profile launch (onStartup fast path, proven ~23s).
# Chrome ON  -> process-reuse opens one new tab; the extension SW's top-level
# tabs.onUpdated/onActivated listeners wake the suspended worker, whose
# top-level attach() reconnects. Non-destructive: no window close, no second
# profile, no second extension.
if [ -z "$INST" ]; then
  if [ ! -f "{CHROME_BIN}" ] || [ ! -d "{CHROME_EXT}" ]; then
    echo "RUNTIME_BROWSER_ENSURE=BLOCKED:canonical browser dependency missing"
    exit 0
  fi
  CHR=$(chrome_count)
  "{CHROME_BIN}" --no-first-run --no-default-browser-check about:blank >/dev/null 2>&1 &
  DL=$(( $(date +%s) + 45 ))
  while [ "$(date +%s)" -lt "$DL" ]; do
    INST=$(poll_inst)
    [ -n "$INST" ] && break
    sleep 3
  done
fi

# ---- W2: daemon-view desync recovery ----
# Real-world counter-example (2026-08-18 23:24-23:26): Chrome alive, its WS to
# 52900 ESTABLISHED the whole window, yet `bsk browsers` returned no
# registration for 90s. When the transport is provably up but the registry
# view is empty, rebuild the handshake via the documented daemon lifecycle:
# stop + start; a connected extension reconnects in <1s (proven twice today).
# CLI-only, no bridge internals, no browser touched.
if [ -z "$INST" ] && chrome_holds_ws; then
  CHROME_WS=1
  "$DEV" daemon stop >/dev/null 2>&1 || true
  sleep 1
  "$DEV" daemon start --port 52900 >/dev/null 2>&1 || true
  DRESTART=1
  DL=$(( $(date +%s) + 30 ))
  while [ "$(date +%s)" -lt "$DL" ]; do
    INST=$(poll_inst)
    [ -n "$INST" ] && break
    sleep 2
  done
fi

# ---- W3: final re-nudge (covers SW woke late / first nudge raced) ----
if [ -z "$INST" ] && [ -f "{CHROME_BIN}" ]; then
  "{CHROME_BIN}" --no-first-run --no-default-browser-check about:blank >/dev/null 2>&1 &
  DL=$(( $(date +%s) + 30 ))
  while [ "$(date +%s)" -lt "$DL" ]; do
    INST=$(poll_inst)
    [ -n "$INST" ] && break
    sleep 3
  done
fi

if [ -z "$INST" ]; then
  echo "RUNTIME_BROWSER_CTX=chrome_procs=${{CHR:-$(chrome_count)}} after=$(chrome_count) ws=${{CHROME_WS}} drestart=${{DRESTART}} last=[${{LASTOUT:0:60}}]"
  exit 0
fi
echo "RUNTIME_BROWSER_INST=$INST"
"""


def ensure_bridge_ready(force: bool = False) -> dict:
    """Bridge health + Runtime-owned bootstrap of the canonical prerequisite
    chain (daemon -> browser instance -> extension registration). Triggers on
    the two self-healable failure signatures ('no browser', 'daemon
    unreachable'); environment noise (ENV_NOISE_ONLY) is host-side and never
    triggers a bootstrap. One bounded attempt per call; a genuine bootstrap
    failure yields RUNTIME_BROWSER_BLOCKED; callers never touch internals."""
    health = bridge_health(force=force)
    detail = str(health.get("detail", ""))
    healable = ("no browser" in detail) or ("daemon unreachable" in detail)
    if health.get("ready") or not healable:
        return health
    try:
        proc = bash_run(ensure_browser_script(), timeout=BROWSER_BOOTSTRAP_WAIT_SEC + 90)
        markers = parse_markers(proc.stdout)
    except (subprocess.TimeoutExpired, OSError):
        markers = {}
    inst = markers.get("RUNTIME_BROWSER_INST", "")
    blocked = markers.get("RUNTIME_BROWSER_ENSURE", "")
    ctx = markers.get("RUNTIME_BROWSER_CTX", "")
    if inst:
        health = bridge_health(force=True)
        health["browser_bootstrapped"] = True
        return health
    detail = sanitize("RUNTIME_BROWSER_BLOCKED: " +
                      (blocked or "browser bootstrap finished without instance registration" +
                       (f" ({ctx})" if ctx else "")))
    atomic_write_text(HEALTH_FILE, json.dumps(
        {"ready": False, "detail": detail, "checked_at": utc_now(), "checked_epoch": time.time()}))
    return {"ready": False, "cached": False, "detail": detail, "browser_bootstrapped": False}


# ---------------------------------------------------------------------------
# Transport scripts (encapsulated bridge access)
# ---------------------------------------------------------------------------
def send_script(r_url: str, msg_file_posix: str, files: list[str], reply_out_posix: str, timeout: int,
                stored_sid: str = "") -> str:
    uploads = []
    for f in files:
        leaf = Path(f).name
        stem = Path(f).stem
        # ChatGPT composer chips truncate long file names, so an exact long-stem
        # keyword can fail to match even when the attachment is present. Match on
        # a short sanitized prefix instead (adapter-side; canonical lib untouched).
        kw = re.sub(r"[^A-Za-z0-9_.-]", "", stem)[:16] or re.sub(r"[^A-Za-z0-9_.-]", "", leaf)[:8]
        uploads.append(
            f'UPERR=$("$DEV" upload --session "$SID" --selector "$FILEINPUT" --file "{to_posix(f)}" 2>&1) '
            f'|| {{ echo "RUNTIME_UPLOAD_FAIL={leaf} stage=upload raw=$(printf %s "$UPERR" | tr -d \'\\r\\n\' | tail -c 160)"; exit 0; }}'
        )
        if kw != stem:
            # full-stem first (diagnostic + exact), short prefix fallback (truncation)
            uploads.append(
                f'WAITRES=$(yz_wait_attachment "$SID" "{stem}" 30 2>&1) '
                f'|| WAITRES=$(yz_wait_attachment "$SID" "{kw}" 15 2>&1) '
                f'|| {{ echo "RUNTIME_UPLOAD_FAIL={leaf} stage=attach_wait kw_tried={stem}+{kw} raw=$WAITRES"; exit 0; }}'
            )
        else:
            uploads.append(
                f'WAITRES=$(yz_wait_attachment "$SID" "{kw}" 30 2>&1) '
                f'|| {{ echo "RUNTIME_UPLOAD_FAIL={leaf} stage=attach_wait kw={kw} raw=$WAITRES"; exit 0; }}'
            )
    upload_block = "\n".join(uploads)
    if stored_sid:
        # Reattach-first: reuse the RUN's stored session when alive and IDLE on the
        # exact R_URL; otherwise fall back to canonical acquire. Never opens a new
        # visible window while a healthy reattach exists. Comparisons are hardened
        # against trailing CR/whitespace so a healthy session is never abandoned.
        acquire = f"""SID='{stored_sid}'
ACQ_MODE=reattach
SU=$("$DEV" evaluate --session "$SID" "location.href" 2>/dev/null | tr -d '\\r\\n ')
G=$(yz_gen_state "$SID" 2>/dev/null | tr -d '\\r\\n ')
if [ "$SU" = "$RURL" ] && [ "$G" = "GEN" ]; then
  # Page still generating (e.g. fast reply tail): wait bounded IDLE instead of
  # abandoning a healthy session. No resend, no reload, no new window.
  WDL=$(( $(date +%s) + 45 ))
  while [ "$(date +%s)" -lt "$WDL" ]; do
    G=$(yz_gen_state "$SID" 2>/dev/null | tr -d '\\r\\n ')
    [ "$G" = "IDLE" ] && break
    sleep 1
  done
  ACQ_MODE=reattach_waited
fi
RURLT=$(printf %s "$RURL" | tr -d ' ')
if [ "$SU" != "$RURLT" ] || [ "$G" != "IDLE" ]; then
  SID=$(yz_acquire_conv "$RURL")
  ACQ_MODE=acquire
fi
echo "RUNTIME_ACQ_MODE=$ACQ_MODE"
echo "RUNTIME_DBG=su=$SU g=$G"
"""
    else:
        acquire = ('SID=$(yz_acquire_conv "$RURL")\n'
                   'echo "RUNTIME_ACQ_MODE=acquire"\n'
                   'echo "RUNTIME_DBG=su=- g=-"\n')
    return f"""set -u
{PATH_PROLOGUE}
source {YZ_LIB} >/dev/null 2>&1
RURL='{r_url}'
{acquire}echo "RUNTIME_SID=$SID"
if [ -z "$SID" ]; then echo "RUNTIME_SEND=ACQUIRE_FAILED"; exit 0; fi
{upload_block}
MSG=$(cat "{msg_file_posix}")
RES=$(yz_send_text "$SID" "$MSG" {timeout})
echo "RUNTIME_SEND=$RES"
case "$RES" in DONE|DONE_NO_MARKER)
  yz_recv_last "$SID" "{reply_out_posix}"
  echo "RUNTIME_RECV_SID=$YZ_SID"
;; esac
exit 0
"""


def recv_script(sid: str, r_url: str, reply_out_posix: str) -> str:
    return f"""set -u
{PATH_PROLOGUE}
source {YZ_LIB} >/dev/null 2>&1
SID='{sid}'
if [ -z "$SID" ]; then
  SID=$(yz_acquire_conv '{r_url}')
  echo "RUNTIME_SID=$SID"
fi
if [ -z "$SID" ]; then echo "RUNTIME_RECV=ACQUIRE_FAILED"; exit 0; fi
yz_recv_last "$SID" "{reply_out_posix}"
echo "RUNTIME_RECV_SID=$YZ_SID"
echo "RUNTIME_RECV=OK"
exit 0
"""


def session_cleanup_script(sid: str, r_url: str) -> str:
    conv = CONV_ID_RE.search(r_url)
    conv_id = conv.group(1) if conv else "unknown"
    stop = f'"$DEV" session stop "{sid}" >/dev/null 2>&1' if sid else "true"
    return f"""set -u
{PATH_PROLOGUE}
source {YZ_LIB} >/dev/null 2>&1
{stop}
rm -f "/tmp/yz_conv_sid_{conv_id}.txt"
echo "CLEANUP_OK"
"""


def session_is_healthy(sid: str, r_url: str) -> bool:
    """Precise session liveness check: registered, on the exact R_URL, IDLE.
    Used to separate attachment failures (keep the window, retry in place) from
    real session/page death (exactly one precise replacement, reason recorded)."""
    if not sid:
        return False
    script = f"""set -u
{PATH_PROLOGUE}
source {YZ_LIB} >/dev/null 2>&1
"$DEV" session list 2>/dev/null | grep -qE "^{sid}[[:space:]]" || {{ echo "SESS_HEALTH=ABSENT"; exit 0; }}
SU=$("$DEV" evaluate --session "{sid}" "location.href" 2>/dev/null | tr -d '\\r\\n')
G=$(yz_gen_state "{sid}")
echo "SESS_HEALTH=URL=$SU GEN=$G"
"""
    try:
        proc = bash_run(script, timeout=30)
    except (subprocess.TimeoutExpired, OSError):
        return False
    for line in proc.stdout.splitlines():
        if line.startswith("SESS_HEALTH="):
            if "ABSENT" in line:
                return False
            return f"URL={r_url}" in line and "GEN=IDLE" in line
    return False


def session_hygiene_script(keep_sid: str, r_url: str) -> str:
    """Conversation-scoped reap: stop every session on THIS conversation except
    the one we keep, then point the canonical mapfile at the keeper. Only fires
    when the bridge's own short-reply fallback spawned extra sessions, so the
    steady-state fast path pays nothing. Never touches other conversations."""
    conv = CONV_ID_RE.search(r_url)
    conv_id = conv.group(1) if conv else ""
    return f"""set -u
{PATH_PROLOGUE}
source {YZ_LIB} >/dev/null 2>&1
for s in $("$DEV" session list 2>/dev/null | grep -oE '^[a-z]{{4}}'); do
  u=$("$DEV" evaluate --session "$s" "location.href" 2>/dev/null | tr -d '\\r\\n')
  case "$u" in
    *{conv_id}*)
      if [ "$s" != "{keep_sid}" ]; then "$DEV" session stop "$s" >/dev/null 2>&1; echo "RUNTIME_REAPED=$s"; fi
    ;;
  esac
done
echo "{keep_sid}" > "/tmp/yz_conv_sid_{conv_id}.txt"
echo "HYGIENE_OK"
"""


def parse_markers(stdout: str) -> dict:
    out: dict = {}
    for line in stdout.splitlines():
        if line.startswith("RUNTIME_"):
            key, _, val = line.partition("=")
            out[key] = val.strip()
    return out


# ---------------------------------------------------------------------------
# Verdict protocol (machine-parseable; weak Worker never interprets prose)
# ---------------------------------------------------------------------------
REQUERY_TEXT = ("The previous reply did not contain a parseable ===REVIEW_VERDICT=== token. "
                "Please reply ONLY with the final verdict line: ===REVIEW_VERDICT=== PASS or REWORK or BLOCKED, "
                "then ===NEXT_ACTION=== and one short sentence.")


def parse_verdict(text: str) -> tuple[str | None, str]:
    verdict = None
    m = re.search(r"===\s*REVIEW_VERDICT\s*===\s*([A-Za-z_]+)", text)
    if m:
        v = m.group(1).upper()
        if v == "REVISE":
            v = "REWORK"
        if v in ("PASS", "REWORK", "BLOCKED"):
            verdict = v
    next_action = ""
    m2 = re.search(r"===\s*NEXT_ACTION\s*===([\s\S]*?)(?:===CHATGPT_DONE|$)", text)
    if m2:
        next_action = m2.group(1).strip()[:4000]
    return verdict, next_action


def apply_verdict(state: dict, verdict: str | None, next_action: str, reply_path: Path, reply_bytes: int) -> None:
    state["last_r_verdict"] = verdict or "NO_VERDICT"
    state["last_reply_path"] = str(reply_path)
    state["last_reply_bytes"] = reply_bytes
    if verdict == "PASS":
        state["next_action"] = "R verdict PASS. Finalize: run `done --run-id %s` after final acceptance items are complete." % state["run_id"]
    elif verdict == "REWORK":
        state["metrics"]["rework_count"] = int(state["metrics"].get("rework_count", 0)) + 1
        state["next_action"] = ("R verdict REWORK — auto-rework required. " + next_action)[:4000]
    elif verdict == "BLOCKED":
        hard_block(state, "R verdict BLOCKED: " + next_action[:500])
        return
    else:
        state["next_action"] = ("NO_VERDICT: verdict unparseable after bounded requeries. "
                                "Next: send a fresh small evidence delta and explicitly request the final verdict token.")
    if next_action and verdict in ("PASS", "REWORK"):
        state["last_r_next_action"] = next_action


# ---------------------------------------------------------------------------
# Commands
# ---------------------------------------------------------------------------
def _new_run(goal: str, r_url: str, worker_id: str) -> dict:
    """Create + durably persist a new RUN (shared by start and the production
    work entry). Returns the fresh state dict."""
    run_id = "RUN-%s-%s" % (datetime.now().strftime("%Y%m%d-%H%M%S"), uuid.uuid4().hex[:4])
    rd = run_dir(run_id)
    rd.mkdir(parents=True, exist_ok=False)
    state = {
        "schema_version": 1,
        "run_id": run_id,
        "revision": 0,
        "created_at": utc_now(),
        "updated_at": utc_now(),
        "worker_identity": worker_id or "unknown-worker",
        "goal": goal.strip(),
        "r_url": r_url,
        "r_url_history": [],
        "review_epoch": 1,
        "status": "RUNNING",
        "current_step": "RUN started",
        "next_action": "Proceed with the goal. Use only runtime commands; send evidence to R when a review is needed.",
        "last_r_verdict": None,
        "last_r_next_action": "",
        "last_reply_path": None,
        "last_reply_bytes": 0,
        "paused": False,
        "last_user_directive": None,
        "user_override": None,
        "checkpoint": None,
        "scope_notes": [],
        "session": {"sid": None, "epoch": 1},
        "evidence_ledger": {},
        "last_action_fingerprint": None,
        "last_action_context": None,
        "blocked_reason": None,
        "metrics": {
            "started_at": utc_now(),
            "finished_at": None,
            "r_roundtrips": 0,
            "r_wait_time_sec": 0,
            "bridge_retries": 0,
            "session_recoveries": 0,
            "upload_retries": 0,
            "verdict_requeries_used": 0,
            "duplicate_actions_blocked": 0,
            "rework_count": 0,
            "health_checks_skipped": 0,
        },
    }
    save_state(state)
    journal(run_id, "RUN_CREATED", goal=state["goal"], r_url=r_url, worker=state["worker_identity"])
    # active_run is a convenience pointer ONLY; it never routes commands.
    atomic_write_text(STATE_ROOT / "active_run.txt", run_id + "\n")
    return state


def cmd_start(args) -> int:
    if not args.r_url:
        emit({"status": "MISSING_R_URL",
              "instruction": "Stop. Every new RUN requires an explicit R_URL from the user. "
                             "Do not inherit, guess, or create one. Ask the user for the R_URL."})
        return EXIT_MISSING_R_URL
    if not R_URL_RE.match(args.r_url):
        emit({"status": "INVALID_R_URL", "r_url": args.r_url,
              "instruction": "R_URL must look like https://chatgpt.com/c/<id>. Stop and ask the user."})
        return EXIT_MISSING_R_URL
    if not args.goal or not args.goal.strip():
        emit({"status": "MISSING_GOAL", "instruction": "start requires --goal."})
        return EXIT_USAGE
    state = _new_run(args.goal, args.r_url, args.worker_id)
    emit({"status": "OK", "run_id": state["run_id"], "run_status": "RUNNING",
          "state_path": str(run_dir(state["run_id"]) / "state.json"),
          "contract": str(Path(__file__).resolve().parent / "WEAK_WORKER_START_HERE.md")})
    return EXIT_OK


def _load_or_fail(run_id: str) -> tuple[dict | None, int]:
    try:
        return load_state(run_id), EXIT_OK
    except FileNotFoundError:
        emit({"status": "RUN_NOT_FOUND", "run_id": run_id})
        return None, EXIT_RUN_NOT_FOUND
    except ValueError:
        emit({"status": "INVALID_RUN_ID", "run_id": run_id})
        return None, EXIT_USAGE


def cmd_status(args) -> int:
    state, code = _load_or_fail(args.run_id)
    if state is None:
        return code
    out = dict(state)
    out["allowed_actions"] = allowed_actions(state)
    emit(out)
    return EXIT_OK


def cmd_step(args) -> int:
    state, code = _load_or_fail(args.run_id)
    if state is None:
        return code
    with RunLock(args.run_id):
        state = load_state(args.run_id)
        try:
            require_status(state, ("RUNNING",))
        except PermissionError as exc:
            emit({"status": "DENIED", "reason": f"run is {exc}; step requires RUNNING", "run_status": state["status"]})
            return EXIT_DENIED
        state["current_step"] = args.current.strip()
        state["next_action"] = args.next.strip()
        if args.checkpoint:
            state["checkpoint"] = {"text": args.checkpoint.strip(), "at": utc_now()}
        journal(args.run_id, "STEP", current_step=state["current_step"], next_action=state["next_action"])
        save_state(state)
    emit({"status": "OK", "run_id": args.run_id, "current_step": state["current_step"], "next_action": state["next_action"]})
    return EXIT_OK


def cmd_directive(args) -> int:
    action = args.action.upper()
    if action not in ("PAUSE", "RESUME", "STOP", "R_URL_CHANGE", "CHANGE_SCOPE", "USER_OVERRIDE"):
        emit({"status": "INVALID_DIRECTIVE", "action": args.action})
        return EXIT_USAGE
    state, code = _load_or_fail(args.run_id)
    if state is None:
        return code
    if action == "R_URL_CHANGE" and not args.new_r_url:
        emit({"status": "MISSING_R_URL", "instruction": "R_URL_CHANGE requires --new-r-url (explicitly provided by the user)."})
        return EXIT_MISSING_R_URL
    if args.new_r_url and not R_URL_RE.match(args.new_r_url):
        emit({"status": "INVALID_R_URL", "r_url": args.new_r_url})
        return EXIT_MISSING_R_URL
    with RunLock(args.run_id):
        state = load_state(args.run_id)
        # --- durable commit FIRST, transition second ---
        state["last_user_directive"] = {"action": action, "note": args.note or "", "at": utc_now()}
        if action == "USER_OVERRIDE":
            state["user_override"] = {"note": args.note or "", "at": utc_now()}
        journal(args.run_id, "DIRECTIVE_COMMIT", action=action, note=args.note or "", new_r_url=args.new_r_url)
        save_state(state)
        # --- apply transition ---
        s = state["status"]
        if action == "PAUSE":
            if s != "RUNNING":
                emit({"status": "DENIED", "reason": f"PAUSE requires RUNNING, run is {s}"})
                return EXIT_DENIED
            state["status"] = "PAUSED"
            state["paused"] = True
            state["next_action"] = "PAUSED by user directive. Do nothing until RESUME is committed."
        elif action == "RESUME":
            if s != "PAUSED":
                emit({"status": "DENIED", "reason": f"RESUME requires PAUSED, run is {s}"})
                return EXIT_DENIED
            state["status"] = "RUNNING"
            state["paused"] = False
            state["next_action"] = "RESUMED. Continue from current_step."
        elif action == "STOP":
            if s not in ("RUNNING", "PAUSED"):
                emit({"status": "DENIED", "reason": f"STOP requires RUNNING|PAUSED, run is {s}"})
                return EXIT_DENIED
            state["status"] = "STOPPED"
            state["paused"] = False
            state["next_action"] = "STOPPED by user directive. Terminal; do not resume automatically."
        elif action == "R_URL_CHANGE":
            if s != "RUNNING":
                emit({"status": "DENIED", "reason": f"R_URL_CHANGE requires RUNNING, run is {s}"})
                return EXIT_DENIED
            old = state["r_url"]
            state["r_url_history"].append({"r_url": old, "epoch": state["review_epoch"], "until": utc_now()})
            state["r_url"] = args.new_r_url
            state["review_epoch"] = int(state["review_epoch"]) + 1
            # invalidate everything bound to the old reviewer epoch
            state["session"] = {"sid": None, "epoch": state["review_epoch"]}
            state["last_r_verdict"] = None
            state["last_r_next_action"] = ""
            state["last_reply_path"] = None
            state["last_action_fingerprint"] = None
            state["metrics"]["verdict_requeries_used"] = 0
            state["next_action"] = ("R_URL changed (new review epoch %d). Old verdict invalidated; "
                                    "re-send the current evidence summary to the new R." % state["review_epoch"])
        elif action == "CHANGE_SCOPE":
            state["scope_notes"].append({"note": args.note or "", "at": utc_now()})
            state["next_action"] = "Scope changed by user directive; re-read goal + scope_notes before acting."
        elif action == "USER_OVERRIDE":
            if s in ("HARD_BLOCKED", "STOPPED"):
                state["status"] = "RUNNING"
                state["paused"] = False
                state["blocked_reason"] = None
                state["next_action"] = "USER_OVERRIDE accepted; continue carefully from current_step."
            elif s == "DONE":
                emit({"status": "DENIED", "reason": "DONE is terminal; start a new RUN instead"})
                return EXIT_DENIED
        journal(args.run_id, "DIRECTIVE_APPLIED", action=action, new_status=state["status"],
                review_epoch=state["review_epoch"])
        save_state(state)
    emit({"status": "OK", "directive": action, "run_status": state["status"],
          "review_epoch": state["review_epoch"], "r_url": state["r_url"]})
    return EXIT_OK


def _check_duplicate(state: dict, fingerprint: str) -> bool:
    ctx = f"{state['review_epoch']}::{state['current_step']}"
    if state.get("last_action_fingerprint") == fingerprint and state.get("last_action_context") == ctx:
        state["metrics"]["duplicate_actions_blocked"] = int(state["metrics"].get("duplicate_actions_blocked", 0)) + 1
        return True
    return False


def _record_action(state: dict, fingerprint: str) -> None:
    state["last_action_fingerprint"] = fingerprint
    state["last_action_context"] = f"{state['review_epoch']}::{state['current_step']}"


def cmd_send(args) -> int:
    state, code = _load_or_fail(args.run_id)
    if state is None:
        return code
    # cmd.exe (%*) breaks arguments on newlines: multiline --message would be
    # silently truncated. Multiline bodies must go through --message-file.
    if args.message_file:
        mf = Path(args.message_file)
        if not mf.exists():
            emit({"status": "FILE_NOT_FOUND", "file": str(mf)})
            return EXIT_USAGE
        args.message = mf.read_text(encoding="utf-8", errors="replace")
    elif "\n" in (args.message or "").strip("\n"):
        # cmd.exe (%*) breaks arguments on newlines: multiline --message would be
        # silently truncated, so reject it loudly. Multiline bodies are exactly
        # what --message-file is for.
        emit({"status": "MULTILINE_MESSAGE_UNSAFE",
              "instruction": "Multiline --message is truncated by the shell entry. "
                             "Write the body to a file and use --message-file instead."})
        return EXIT_USAGE
    if not args.message or not args.message.strip():
        emit({"status": "MISSING_MESSAGE",
              "instruction": "send needs --message (single line) or --message-file (multiline body)."})
        return EXIT_USAGE
    files = args.file or []
    for f in files:
        if not Path(f).exists():
            emit({"status": "FILE_NOT_FOUND", "file": f})
            return EXIT_USAGE
    fingerprint = sha256_text(json.dumps({
        "message": args.message, "files": {f: sha256_file(Path(f)) for f in files}}, sort_keys=True))
    with RunLock(args.run_id):
        state = load_state(args.run_id)
        if state["status"] == "PAUSED":
            emit({"status": "RUN_PAUSED", "run_status": "PAUSED",
                  "instruction": "Run is paused (durable). Do nothing until user RESUME."})
            return EXIT_DENIED
        if state["status"] != "RUNNING":
            emit({"status": "DENIED", "run_status": state["status"],
                  "reason": f"send requires RUNNING; run is {state['status']}",
                  "blocked_reason": state.get("blocked_reason")})
            return EXIT_DENIED if state["status"] != "HARD_BLOCKED" else EXIT_HARD_BLOCKED
        if _check_duplicate(state, fingerprint):
            journal(args.run_id, "DUPLICATE_ACTION_BLOCKED")
            save_state(state)
            emit({"status": "DUPLICATE_ACTION",
                  "instruction": "Identical send (same step+epoch+content) was already attempted. "
                                 "Do NOT repeat mechanically. Change content or advance the step first."})
            return EXIT_DENIED

        # Fast path: cached health
        health = bridge_health(force=args.force_health)
        if health.get("cached"):
            state["metrics"]["health_checks_skipped"] = int(state["metrics"].get("health_checks_skipped", 0)) + 1
        if not health.get("ready"):
            state["metrics"]["bridge_retries"] = int(state["metrics"].get("bridge_retries", 0)) + 1
            if state["metrics"]["bridge_retries"] > MAX_BRIDGE_RETRIES:
                hard_block(state, "bridge health failed beyond retry budget: " + health.get("detail", ""))
                emit({"status": "HARD_BLOCKED", "reason": state["blocked_reason"]})
                return EXIT_HARD_BLOCKED
            save_state(state)
            emit({"status": "BRIDGE_UNHEALTHY", "detail": health.get("detail", ""),
                  "bridge_retries": state["metrics"]["bridge_retries"],
                  "instruction": "Bridge unhealthy. Retry the same command later (budget limited); do not open the bridge internals."})
            return EXIT_ERR

        # evidence delta: only upload new/changed files for this epoch
        epoch_key = str(state["review_epoch"])
        ledger = state["evidence_ledger"].setdefault(epoch_key, {})
        delta_files = []
        for f in files:
            digest = sha256_file(Path(f))
            known = ledger.get(str(Path(f).resolve()))
            if not known or known.get("sha256") != digest:
                delta_files.append((f, digest))
        skipped = len(files) - len(delta_files)

        rd = run_dir(args.run_id)
        msg_file = rd / f"msg_{int(time.time())}_{uuid.uuid4().hex[:6]}.txt"
        atomic_write_text(msg_file, args.message)
        reply_file = rd / f"reply_epoch{state['review_epoch']}_{int(time.time())}_{uuid.uuid4().hex[:6]}.txt"

        send_attempts = 0
        send_result = None
        markers: dict = {}
        stored_sid = (state.get("session") or {}).get("sid") or ""
        while True:
            script = send_script(state["r_url"], to_posix(str(msg_file)),
                                 [f for f, _ in delta_files], to_posix(str(reply_file)), args.timeout,
                                 stored_sid=stored_sid)
            t0 = time.time()
            try:
                proc = bash_run(script, timeout=args.timeout + 240)
                markers = parse_markers(proc.stdout)
                send_result = markers.get("RUNTIME_SEND", "NO_RESULT")
                if markers.get("RUNTIME_UPLOAD_FAIL"):
                    send_result = "UPLOAD_FAIL:" + markers["RUNTIME_UPLOAD_FAIL"]
            except subprocess.TimeoutExpired:
                send_result = "RUNTIME_TIMEOUT"
            except OSError as exc:
                send_result = f"RUNTIME_ERROR:{exc}"
            state["metrics"]["r_wait_time_sec"] = round(
                float(state["metrics"].get("r_wait_time_sec", 0)) + (time.time() - t0), 1)
            if send_result in ("DONE", "DONE_NO_MARKER"):
                break
            # failure path: classify FIRST, then choose the minimal recovery.
            # Attachment failure with a healthy session NEVER rebuilds the window;
            # session replacement happens only with explicit evidence, and every
            # replacement records its exact reason.
            sid = markers.get("RUNTIME_SID") or stored_sid or (state.get("session") or {}).get("sid") or ""
            stage = str(send_result).split("stage=", 1)[1].split()[0] if "stage=" in str(send_result) else ""

            if "UPLOAD_FAIL" in send_result and session_is_healthy(sid, state["r_url"]):
                # attachment/file operation failure, page/session fine: bounded
                # in-place retry within the SAME session; no close/reopen.
                state["metrics"]["upload_retries"] = int(state["metrics"].get("upload_retries", 0)) + 1
                journal(args.run_id, "SEND_FAILURE", result=sanitize(str(send_result)),
                        kind="attachment", stage=stage, action="IN_PLACE_RETRY",
                        upload_retries=state["metrics"]["upload_retries"], sid=sid)
                if state["metrics"]["upload_retries"] > MAX_UPLOAD_RETRIES:
                    hard_block(state, ("attachment upload failed beyond budget "
                                       f"({send_result}); session stayed healthy, no rebuild"))
                    emit({"status": "HARD_BLOCKED", "reason": state["blocked_reason"],
                          "instruction": "Stop. Report to user with this state. Do not research alternative bridge routes."})
                    return EXIT_HARD_BLOCKED
                save_state(state)
                stored_sid = sid
                send_attempts += 1
                time.sleep(1)
                continue

            if "UPLOAD_FAIL" in send_result:
                replace_reason = f"SESSION_DEAD_DURING_UPLOAD({stage or 'unknown'})"
                state["metrics"]["session_recoveries"] = int(state["metrics"].get("session_recoveries", 0)) + 1
                over = state["metrics"]["session_recoveries"] > MAX_SESSION_RECOVERIES
            elif send_result in ("ACQUIRE_FAILED", "SEND_FAILED"):
                replace_reason = ("ACQUIRE_FAILED" if send_result == "ACQUIRE_FAILED"
                                  else "SEND_FAILED_PAGE_STUCK")
                state["metrics"]["session_recoveries"] = int(state["metrics"].get("session_recoveries", 0)) + 1
                over = state["metrics"]["session_recoveries"] > MAX_SESSION_RECOVERIES
            else:
                # TIMEOUT / transport noise: retry in place; do NOT rebuild the
                # session without evidence it is dead.
                state["metrics"]["bridge_retries"] = int(state["metrics"].get("bridge_retries", 0)) + 1
                journal(args.run_id, "SEND_FAILURE", result=sanitize(str(send_result)),
                        kind="transport", action="IN_PLACE_RETRY",
                        bridge_retries=state["metrics"]["bridge_retries"])
                if state["metrics"]["bridge_retries"] > MAX_BRIDGE_RETRIES:
                    hard_block(state, f"transport failure beyond retry budget ({send_result})")
                    emit({"status": "HARD_BLOCKED", "reason": state["blocked_reason"],
                          "instruction": "Stop. Report to user with this state. Do not research alternative bridge routes."})
                    return EXIT_HARD_BLOCKED
                save_state(state)
                stored_sid = sid or stored_sid
                send_attempts += 1
                time.sleep(2)
                continue

            journal(args.run_id, "SEND_FAILURE", result=sanitize(str(send_result)),
                    kind="session", replace_reason=replace_reason,
                    session_recoveries=state["metrics"]["session_recoveries"])
            if over:
                hard_block(state, (f"transport failure beyond retry budget ({send_result}); "
                                   f"replacement_reason={replace_reason}"))
                emit({"status": "HARD_BLOCKED", "reason": state["blocked_reason"],
                      "instruction": "Stop. Report to user with this state. Do not research alternative bridge routes."})
                return EXIT_HARD_BLOCKED
            try:
                bash_run(session_cleanup_script(sid, state["r_url"]), timeout=60)
            except (subprocess.TimeoutExpired, OSError):
                pass
            journal(args.run_id, "SESSION_REPLACED", reason=replace_reason, old_sid=sid)
            state["session"] = {"sid": None, "epoch": state["review_epoch"]}
            save_state(state)
            stored_sid = ""
            send_attempts += 1
            time.sleep(2)

        # success bookkeeping: track the session the bridge actually ended on.
        # The bridge's short-reply fallback can hand back a different session or
        # leave intermediate orphan sessions; consolidation happens once at the
        # end (after requeries) so a conversation never accumulates sessions.
        main_sid = markers.get("RUNTIME_SID", "")
        recv_sid = markers.get("RUNTIME_RECV_SID", "")
        final_sid = recv_sid or main_sid
        fallback_seen = bool(recv_sid) and recv_sid != main_sid
        old_sid = (state.get("session") or {}).get("sid") or ""
        for f, digest in delta_files:
            ledger[str(Path(f).resolve())] = {"sha256": digest, "uploaded_at": utc_now(), "name": Path(f).name}
        state["metrics"]["r_roundtrips"] = int(state["metrics"].get("r_roundtrips", 0)) + 1
        state["metrics"]["evidence_skipped_unchanged"] = int(state["metrics"].get("evidence_skipped_unchanged", 0)) + skipped
        _record_action(state, fingerprint)
        journal(args.run_id, "SEND_OK", result=send_result, files_uploaded=[Path(f).name for f, _ in delta_files],
                files_skipped=skipped, sid=final_sid, acq_mode=markers.get("RUNTIME_ACQ_MODE", ""),
                dbg=markers.get("RUNTIME_DBG", ""), recv_sid=recv_sid)

        # verdict parsing with bounded auto-requery (weak Worker never guesses)
        reply_text = reply_file.read_text(encoding="utf-8", errors="replace") if reply_file.exists() else ""
        verdict, next_action = parse_verdict(reply_text)
        requeries = 0
        while verdict is None and requeries < MAX_VERDICT_REQUERIES:
            requeries += 1
            state["metrics"]["verdict_requeries_used"] = int(state["metrics"].get("verdict_requeries_used", 0)) + 1
            save_state(state)
            rq_msg = rd / f"requery_{int(time.time())}_{uuid.uuid4().hex[:6]}.txt"
            atomic_write_text(rq_msg, REQUERY_TEXT)
            rq_reply = rd / f"requery_reply_{int(time.time())}_{uuid.uuid4().hex[:6]}.txt"
            try:
                rq_t0 = time.time()
                proc = bash_run(send_script(state["r_url"], to_posix(str(rq_msg)), [], to_posix(str(rq_reply)), 180,
                                            stored_sid=final_sid),
                                timeout=420)
                state["metrics"]["r_wait_time_sec"] = round(
                    float(state["metrics"].get("r_wait_time_sec", 0)) + (time.time() - rq_t0), 1)
                mk = parse_markers(proc.stdout)
                rq_recv = mk.get("RUNTIME_RECV_SID", "")
                rq_sid = mk.get("RUNTIME_SID", "")
                if rq_recv and rq_recv != final_sid:
                    final_sid = rq_recv
                    fallback_seen = True
                elif rq_sid and not rq_recv and rq_sid != final_sid:
                    final_sid = rq_sid
                if mk.get("RUNTIME_SEND") in ("DONE", "DONE_NO_MARKER") and rq_reply.exists():
                    reply_file = rq_reply
                    reply_text = rq_reply.read_text(encoding="utf-8", errors="replace")
                    state["metrics"]["r_roundtrips"] = int(state["metrics"].get("r_roundtrips", 0)) + 1
                    verdict, next_action = parse_verdict(reply_text)
            except (subprocess.TimeoutExpired, OSError):
                break
        reply_bytes = len(reply_text.encode("utf-8", errors="replace"))
        apply_verdict(state, verdict, next_action, reply_file, reply_bytes)
        # one-time session consolidation for this conversation (skip if the
        # verdict path hard-blocked the RUN; hard_block already released it)
        if state["status"] == "RUNNING" and final_sid:
            if final_sid != old_sid:
                journal(args.run_id, "SESSION_REPLACED", reason="REATTACH_TO_RECV_SID", old_sid=old_sid)
            if fallback_seen:
                try:
                    hy = bash_run(session_hygiene_script(final_sid, state["r_url"]), timeout=90)
                    reaped = [l.split("=", 1)[1] for l in hy.stdout.splitlines() if l.startswith("RUNTIME_REAPED=")]
                    if reaped:
                        journal(args.run_id, "SESSION_HYGIENE", kept=final_sid, reaped=reaped)
                except (subprocess.TimeoutExpired, OSError):
                    pass
            state["session"] = {"sid": final_sid, "epoch": state["review_epoch"]}
        save_state(state)
    emit({"status": "OK", "send_result": send_result, "run_status": state["status"],
          "attachment_mode": "attachment-required" if files else "text-only",
          "last_r_verdict": state["last_r_verdict"],
          "next_action": state["next_action"],
          "files_uploaded": [Path(f).name for f, _ in delta_files],
          "files_skipped_unchanged": skipped,
          "reply_path": str(reply_file), "reply_bytes": reply_bytes})
    return EXIT_OK


def cmd_recv(args) -> int:
    state, code = _load_or_fail(args.run_id)
    if state is None:
        return code
    with RunLock(args.run_id):
        state = load_state(args.run_id)
        try:
            require_status(state, ("RUNNING",))
        except PermissionError as exc:
            emit({"status": "DENIED", "reason": f"recv requires RUNNING, run is {exc}"})
            return EXIT_DENIED
        sid = (state.get("session") or {}).get("sid") or ""
        rd = run_dir(args.run_id)
        reply_file = rd / f"recv_{int(time.time())}_{uuid.uuid4().hex[:6]}.txt"
        try:
            proc = bash_run(recv_script(sid, state["r_url"], to_posix(str(reply_file))), timeout=300)
        except subprocess.TimeoutExpired:
            emit({"status": "RECV_TIMEOUT"})
            return EXIT_ERR
        markers = parse_markers(proc.stdout)
        if markers.get("RUNTIME_RECV") == "ACQUIRE_FAILED":
            state["metrics"]["bridge_retries"] = int(state["metrics"].get("bridge_retries", 0)) + 1
            save_state(state)
            emit({"status": "BRIDGE_UNHEALTHY", "instruction": "recv could not attach; retry later (budget limited)."})
            return EXIT_ERR
        if markers.get("RUNTIME_RECV_SID"):
            state["session"] = {"sid": markers["RUNTIME_RECV_SID"], "epoch": state["review_epoch"]}
        reply_text = reply_file.read_text(encoding="utf-8", errors="replace") if reply_file.exists() else ""
        verdict, next_action = parse_verdict(reply_text)
        apply_verdict(state, verdict, next_action, reply_file, len(reply_text.encode("utf-8", errors="replace")))
        save_state(state)
    emit({"status": "OK", "last_r_verdict": state["last_r_verdict"],
          "next_action": state["next_action"], "reply_path": str(reply_file)})
    return EXIT_OK


def cmd_done(args) -> int:
    state, code = _load_or_fail(args.run_id)
    if state is None:
        return code
    with RunLock(args.run_id):
        state = load_state(args.run_id)
        if state["status"] == "DONE":
            emit({"status": "OK", "note": "already DONE"})
            return EXIT_OK
        if state["status"] != "RUNNING":
            emit({"status": "DENIED", "reason": f"done requires RUNNING, run is {state['status']}"})
            return EXIT_DENIED
        if state.get("last_r_verdict") != "PASS":
            emit({"status": "DENIED",
                  "reason": "done requires last_r_verdict=PASS (parsed by runtime from R reply, not self-reported)",
                  "last_r_verdict": state.get("last_r_verdict")})
            return EXIT_DENIED
        state["status"] = "DONE"
        state["metrics"]["finished_at"] = utc_now()
        state["next_action"] = "RUN complete (R PASS). No further actions."
        journal(args.run_id, "RUN_DONE")
        save_state(state)
    emit({"status": "OK", "run_status": "DONE", "metrics": state["metrics"]})
    return EXIT_OK


def cmd_metrics(args) -> int:
    state, code = _load_or_fail(args.run_id)
    if state is None:
        return code
    m = dict(state["metrics"])
    if m.get("started_at") and not m.get("finished_at"):
        m["elapsed_sec"] = round((datetime.now(timezone.utc) - datetime.fromisoformat(m["started_at"])).total_seconds())
    elif m.get("started_at") and m.get("finished_at"):
        m["elapsed_sec"] = round((datetime.fromisoformat(m["finished_at"]) - datetime.fromisoformat(m["started_at"])).total_seconds())
    emit({"status": "OK", "run_id": args.run_id, "run_status": state["status"], "metrics": m,
          "budgets": {"max_bridge_retries": MAX_BRIDGE_RETRIES, "max_session_recoveries": MAX_SESSION_RECOVERIES,
                      "max_verdict_requeries": MAX_VERDICT_REQUERIES}})
    return EXIT_OK


def cmd_health(args) -> int:
    health = ensure_bridge_ready(force=args.force)
    emit({"status": "OK" if health.get("ready") else "BRIDGE_UNHEALTHY", **health})
    return EXIT_OK if health.get("ready") else EXIT_ERR


# ---------------------------------------------------------------------------
# Production entry (P0-B): zero-documentation weak-Worker interface.
#   work   = GOAL file + explicit R_URL in, RUN + the single next command out.
#   report = worker report file in, R verdict out; PASS auto-finalizes.
# Workers never learn about epochs, sessions, transport, or the bridge.
# ---------------------------------------------------------------------------
def _run_cmd_path() -> str:
    return str(Path(__file__).resolve().parent / "run.cmd")


def cmd_work(args) -> int:
    if not args.r_url:
        emit({"status": "MISSING_R_URL",
              "instruction": "Stop. work requires --r-url explicitly provided by the user. "
                             "Do not inherit, guess, or create one. Ask the user for the R_URL."})
        return EXIT_MISSING_R_URL
    if not R_URL_RE.match(args.r_url):
        emit({"status": "INVALID_R_URL", "r_url": args.r_url,
              "instruction": "R_URL must look like https://chatgpt.com/c/<id>. Stop and ask the user."})
        return EXIT_MISSING_R_URL
    gf = Path(args.goal_file or "")
    if not gf.exists():
        emit({"status": "FILE_NOT_FOUND", "file": args.goal_file,
              "instruction": "work requires --goal-file <path to a UTF-8 text file with the GOAL>."})
        return EXIT_USAGE
    goal = gf.read_text(encoding="utf-8", errors="replace").strip()
    if not goal:
        emit({"status": "MISSING_GOAL", "instruction": "goal file is empty; work needs a real GOAL."})
        return EXIT_USAGE
    # Runtime-owned prerequisite chain: environment + daemon + browser (P0-A).
    # The worker never pre-opens anything; the Runtime brings the chain up.
    health = ensure_bridge_ready(force=True)
    if not health.get("ready"):
        detail = str(health.get("detail", ""))
        status = ("RUNTIME_ENV_BLOCKED" if detail.startswith("RUNTIME_ENV_BLOCKED")
                  else "RUNTIME_BROWSER_BLOCKED" if detail.startswith("RUNTIME_BROWSER_BLOCKED")
                  else "BRIDGE_UNHEALTHY")
        emit({"status": status, "detail": detail,
              "instruction": "Runtime could not bring the bridge up. Report this output to the user; "
                             "do not research the bridge, browser, or daemon."})
        return EXIT_ERR
    state = _new_run(goal, args.r_url, args.worker_id or "prod-worker")
    rid = state["run_id"]
    report_cmd = f'& "{_run_cmd_path()}" report --run-id {rid} --message-file <result file>'
    state["current_step"] = "work entry: bridge READY, GOAL recorded, awaiting execution"
    state["next_action"] = ("Bridge READY. Execute the GOAL now. When done (or when you need a review), "
                            "write your result to a UTF-8 text file and run: " + report_cmd)
    save_state(state)
    journal(rid, "WORK_ENTRY", goal_bytes=len(goal.encode("utf-8")), bridge="READY")
    emit({"status": "OK", "run_id": rid, "run_status": "RUNNING", "bridge": "READY",
          "goal": goal[:200],
          "next_action": state["next_action"],
          "next_command": report_cmd,
          "status_command": f'& "{_run_cmd_path()}" status --run-id {rid}',
          "instruction": "Do the GOAL. Then run next_command with your result file. "
                         "Repeat report until the runtime says DONE."})
    return EXIT_OK


def cmd_report(args) -> int:
    state, code = _load_or_fail(args.run_id)
    if state is None:
        return code
    mf = Path(args.message_file or "")
    if not mf.exists():
        emit({"status": "FILE_NOT_FOUND", "file": args.message_file,
              "instruction": "report requires --message-file <your report file>."})
        return EXIT_USAGE
    body = mf.read_text(encoding="utf-8", errors="replace")
    if not body.strip():
        emit({"status": "MISSING_MESSAGE", "instruction": "report file is empty."})
        return EXIT_USAGE
    files = args.file or []
    for f in files:
        if not Path(f).exists():
            emit({"status": "FILE_NOT_FOUND", "file": f})
            return EXIT_USAGE
    envelope = ("[Runtime V1 production report]\n"
                f"RUN: {args.run_id}\n"
                f"GOAL: {state['goal']}\n"
                "WORKER REPORT:\n" + body +
                "\n\n[Review request] Reply ONLY with the final verdict line: "
                "===REVIEW_VERDICT=== PASS or REWORK or BLOCKED "
                "(plus ===NEXT_ACTION=== instructions when REWORK).")
    env_file = run_dir(args.run_id) / f"report_{int(time.time())}_{uuid.uuid4().hex[:6]}.txt"
    atomic_write_text(env_file, envelope)
    journal(args.run_id, "REPORT", body_bytes=len(body), files=[Path(f).name for f in files])
    send_args = argparse.Namespace(run_id=args.run_id, message="", message_file=str(env_file),
                                   file=files, timeout=args.timeout, force_health=True)
    # Suppress inner command emits so report returns ONE clean JSON document.
    with contextlib.redirect_stdout(io.StringIO()):
        code = cmd_send(send_args)
        state_after = load_state(args.run_id)
        if code == EXIT_OK and state_after.get("last_r_verdict") == "PASS":
            cmd_done(argparse.Namespace(run_id=args.run_id))
    state = load_state(args.run_id)
    verdict = state.get("last_r_verdict")
    report_cmd = f'& "{_run_cmd_path()}" report --run-id {args.run_id} --message-file <updated result file>'
    if state.get("status") == "DONE":
        emit({"status": "OK", "run_id": args.run_id, "run_status": "DONE", "last_r_verdict": verdict,
              "result": "R verdict PASS. Run finalized and delivered. No further actions.",
              "reply_path": state.get("last_reply_path")})
        return EXIT_OK
    instruction = ("R verdict REWORK: do ONLY what R asked, then run next_command. "
                   if verdict == "REWORK" else
                   "Verdict not final (" + str(verdict) + "): re-report with fresh/updated content via next_command. "
                   if code == EXIT_OK else
                   "Report was not delivered. Report this output to the user; do not research the bridge.")
    emit({"status": "REPORTED", "run_id": args.run_id, "run_status": state.get("status"),
          "last_r_verdict": verdict, "r_instructions": state.get("next_action"),
          "next_command": report_cmd, "instruction": instruction})
    return code


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="runtime", description="Weak-AI Production Runtime V1 facade")
    sub = p.add_subparsers(dest="command", required=True)

    s = sub.add_parser("start")
    s.add_argument("--goal", default="")
    s.add_argument("--r-url", dest="r_url", default=None)
    s.add_argument("--worker-id", dest="worker_id", default=None)

    s = sub.add_parser("status"); s.add_argument("--run-id", dest="run_id", required=True)
    s = sub.add_parser("step")
    s.add_argument("--run-id", dest="run_id", required=True)
    s.add_argument("--current", required=True)
    s.add_argument("--next", required=True)
    s.add_argument("--checkpoint", default=None)

    s = sub.add_parser("directive")
    s.add_argument("--run-id", dest="run_id", required=True)
    s.add_argument("action")
    s.add_argument("--new-r-url", dest="new_r_url", default=None)
    s.add_argument("--note", default=None)

    s = sub.add_parser("send")
    s.add_argument("--run-id", dest="run_id", required=True)
    s.add_argument("--message", default="")
    s.add_argument("--message-file", dest="message_file", default=None)
    s.add_argument("--file", action="append")
    s.add_argument("--timeout", type=int, default=DEFAULT_SEND_TIMEOUT)
    s.add_argument("--force-health", dest="force_health", action="store_true")

    s = sub.add_parser("recv"); s.add_argument("--run-id", dest="run_id", required=True)
    s = sub.add_parser("done"); s.add_argument("--run-id", dest="run_id", required=True)
    s = sub.add_parser("metrics"); s.add_argument("--run-id", dest="run_id", required=True)
    s = sub.add_parser("health"); s.add_argument("--force", action="store_true")

    s = sub.add_parser("work")
    s.add_argument("--goal-file", dest="goal_file", required=True)
    s.add_argument("--r-url", dest="r_url", default=None)
    s.add_argument("--worker-id", dest="worker_id", default=None)

    s = sub.add_parser("report")
    s.add_argument("--run-id", dest="run_id", required=True)
    s.add_argument("--message-file", dest="message_file", required=True)
    s.add_argument("--file", action="append")
    s.add_argument("--timeout", type=int, default=DEFAULT_SEND_TIMEOUT)
    return p


def main() -> int:
    force_utf8_stdio()
    argv = sys.argv[1:]
    parser = build_parser()
    try:
        args = parser.parse_args(argv)
    except SystemExit as exc:
        cli_log(argv, None, "USAGE_ERROR", EXIT_USAGE)
        return EXIT_USAGE if exc.code else EXIT_OK
    handler = {
        "start": cmd_start, "status": cmd_status, "step": cmd_step, "directive": cmd_directive,
        "send": cmd_send, "recv": cmd_recv, "done": cmd_done, "metrics": cmd_metrics, "health": cmd_health,
        "work": cmd_work, "report": cmd_report,
    }[args.command]
    run_id = getattr(args, "run_id", None)
    try:
        code = handler(args)
        cli_log(argv, run_id, "OK", code)
        return code
    except FileNotFoundError:
        emit({"status": "RUN_NOT_FOUND", "run_id": run_id})
        cli_log(argv, run_id, "RUN_NOT_FOUND", EXIT_RUN_NOT_FOUND)
        return EXIT_RUN_NOT_FOUND
    except Exception as exc:  # noqa: BLE001 — facade must never dump internals to weak worker
        emit({"status": "RUNTIME_ERROR", "error_type": type(exc).__name__, "error": sanitize(str(exc))})
        cli_log(argv, run_id, "RUNTIME_ERROR", EXIT_ERR)
        return EXIT_ERR


if __name__ == "__main__":
    sys.exit(main())
