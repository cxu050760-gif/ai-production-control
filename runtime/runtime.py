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

Router V0.1 (Slice A) — minimal B/R role routing on the frozen transport:
  router-start --goal-file G --b-url B --r-url R [--worker-id ID] [--max-rounds N]
                create a router RUN holding BOTH role conversations
                (builder -> B, reviewer -> R); no transport yet
  router-step  --run-id ID [--timeout N]
                advance exactly one router phase (one transport exchange)
  router-run   --goal-file G --b-url B --r-url R [--worker-id ID] [--max-rounds N]
                create + auto-drive B -> R -> REWORK -> SAME B until terminal
                (user launches once; zero manual message copying)

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
YZ_LIB_DS = os.environ.get("APC_RUNTIME_YZ_LIB_DS", "/e/WB/workspace/2026-08-16-21-49-32/work/yz_ds_lib.sh")
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
CANDIDATE_SHA_RE = re.compile(r"^[0-9a-fA-F]{40}$")
R_URL_DS_RE = re.compile(r"^https://chat\.deepseek\.com/a/chat/s/[A-Za-z0-9-]{8,}$")


def is_valid_r_url(url: str) -> bool:
    """R_URL accepts either web host: ChatGPT or DeepSeek conversation."""
    return bool(R_URL_RE.match(url or "") or R_URL_DS_RE.match(url or ""))


def conv_id_of(r_url: str) -> tuple:
    """(host, conv_id): host in {'gpt','ds'}; conv_id unique per conversation."""
    m = CONV_ID_RE.search(r_url or "")
    if m:
        return "gpt", m.group(1)
    m = re.search(r"/a/chat/s/([A-Za-z0-9-]+)", r_url or "")
    if m:
        return "ds", m.group(1)
    return ("ds" if "deepseek.com" in (r_url or "") else "gpt"), "unknown"


def yz_lib_for(r_url: str) -> str:
    """Per-host bridge driver lib: DeepSeek RUNs load yz_ds_lib.sh."""
    return YZ_LIB_DS if conv_id_of(r_url)[0] == "ds" else YZ_LIB


def yz_mapfile_for(r_url: str) -> str:
    """Canonical sid mapfile path for this conversation (must match the lib)."""
    host, cid = conv_id_of(r_url)
    return f"/tmp/yz_conv_sid_ds_{cid}.txt" if host == "ds" else f"/tmp/yz_conv_sid_{cid}.txt"


DS_MODES = ("fast", "expert", "vision")
_DS_HARD_KW = ("架构", "设计", "根因", "重构", "审查", "评审", "排查", "诊断", "分析",
               "评估", "对比", "推理", "方案", "规划", "原因", "为什么", "总结",
               "diff", "review", "analyze", "root cause", "refactor", "design", "architecture")
_DS_IMG_EXT = (".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp")


def route_ds_mode(task_text: str = "", files=None) -> str:
    """DeepSeek 三模式路由(2026-09-01): 识图=图片附件, 专家=难任务(多关键词命中或长文本),
    其余=快速。优先级: APC_DS_MODE 显式指定 > 自动路由(APC_DS_ROUTE=0 可关) > fast。
    模式绑定会话且中途不可切:仅用于 ds host,在 acquire/reattach 阶段强制。"""
    forced = os.environ.get("APC_DS_MODE", "").strip().lower()
    if forced in DS_MODES:
        return forced
    if os.environ.get("APC_DS_ROUTE", "1").strip() == "0":
        return "fast"
    names = [Path(f).name.lower() for f in (files or [])]
    if any(n.endswith(_DS_IMG_EXT) for n in names):
        return "vision"
    text = (task_text or "").lower()
    hits = sum(1 for k in _DS_HARD_KW if k in text)
    if len(text) > 600 or hits >= 2:
        return "expert"
    return "fast"

INTERNAL_STRINGS = [
    YZ_LIB,
    YZ_LIB_DS,
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


def _state_paths(run_id: str) -> tuple[Path, Path, Path, Path]:
    rd = run_dir(run_id)
    return (rd / "state.json", rd / "state.integrity.json",
            rd / "state.prev.json", rd / "state.prev.integrity.json")


def _read_json(path: Path) -> dict | None:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def _state_matches_integrity(state_path: Path, integrity_path: Path) -> bool:
    state_text = None
    try:
        state_text = state_path.read_text(encoding="utf-8")
    except OSError:
        return False
    integ = _read_json(integrity_path)
    if not integ:
        return False
    return (sha256_text(state_text) == integ.get("sha256")
            and json.loads(state_text).get("schema_version") == integ.get("schema_version"))


def verify_state(run_id: str) -> dict:
    sp, ip, pp, pip = _state_paths(run_id)
    if not sp.exists():
        return {"ok": False, "reason": "state missing", "run_id": run_id}
    if _state_matches_integrity(sp, ip):
        cur = _read_json(sp) or {}
        return {"ok": True, "reason": "integrity ok", "run_id": run_id,
                "revision": cur.get("revision"), "schema_version": cur.get("schema_version")}
    return {"ok": False, "reason": "integrity mismatch", "run_id": run_id}


def recover_state(run_id: str) -> dict:
    sp, ip, pp, pip = _state_paths(run_id)
    if _state_matches_integrity(sp, ip):
        return {"recovered": False, "reason": "current state already valid", "run_id": run_id}
    if not _state_matches_integrity(pp, pip):
        return {"recovered": False, "reason": "no valid known-good revision to recover", "run_id": run_id}
    prev_text = pp.read_text(encoding="utf-8")
    atomic_write_text(sp, prev_text)
    atomic_write_text(ip, pip.read_text(encoding="utf-8"))
    cur = _read_json(sp) or {}
    journal(run_id, "STATE_RECOVERED", revision=cur.get("revision"))
    return {"recovered": True, "reason": "restored previous known-good revision",
            "run_id": run_id, "revision": cur.get("revision")}


def load_state(run_id: str) -> dict:
    path = run_dir(run_id) / "state.json"
    if not path.exists():
        raise FileNotFoundError(run_id)
    return json.loads(path.read_text(encoding="utf-8"))


def save_state(state: dict) -> None:
    state["revision"] = int(state.get("revision", 0)) + 1
    state["updated_at"] = utc_now()
    sp, ip, pp, pip = _state_paths(state["run_id"])
    # Rotate the currently-validated state to known-good before overwriting, so a
    # corrupted write always leaves a recoverable previous revision (V0.3).
    if _state_matches_integrity(sp, ip):
        try:
            atomic_write_text(pp, sp.read_text(encoding="utf-8"))
            atomic_write_text(pip, ip.read_text(encoding="utf-8"))
        except OSError:
            pass
    text = json.dumps(state, ensure_ascii=False, indent=2, default=str)
    atomic_write_text(sp, text)
    atomic_write_text(ip, json.dumps({
        "revision": state["revision"],
        "schema_version": state.get("schema_version"),
        "sha256": sha256_text(text),
        "saved_at": utc_now(),
    }, ensure_ascii=False, indent=2))


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
def _seam_script_path(p: str) -> str:
    """Convert a /c/... posix path emitted by the Runtime back to a Windows
    path the seam (pure Python, no bash) can open."""
    m = re.match(r"^/([a-zA-Z])/(.*)$", p or "")
    return (m.group(1).upper() + ":/" + m.group(2)) if m else (p or "")


def _seam_script_log(log_path: str, entry: dict) -> None:
    if not log_path:
        return
    try:
        append_jsonl(Path(log_path), entry)
    except OSError:
        pass


def _seam_script_run(script: str) -> subprocess.CompletedProcess:
    """Deterministic scripted-transport seam (Slice A router acceptance).
    Test seam only (same status as the 1/OK/UPLOAD seams above): production
    never sets APC_RUNTIME_INJECT_BRIDGE_FAIL=SCRIPT.

    Script file (APC_RUNTIME_INJECT_SCRIPT_FILE) JSON shape:
      {"conversations": {<url>: {"sid": str, "replies": [..], "failures": [..],
                                 "fail_after": int, "fail_token": str}},
       "log": <jsonl path>}
    Per send: consumes one failure token first; else, when the deterministic
    schedule (fail_after/fail_token) is active and the number of replies
    already served to this URL is >= fail_after, returns fail_token instead of
    the next reply; else pops the next reply for the target conversation
    (durable cursor across processes), writes it to the script's reply file
    and returns the standard RUNTIME_* markers. fail_after/fail_token exist
    ONLY so tests can express "first N roundtrips succeed, the next one
    fails" (e.g. a SEND_FAILED after a REWORK); production never sets them.
    Every exchange is journaled to the log so tests can assert role->URL
    routing."""
    cfg_path = os.environ.get("APC_RUNTIME_INJECT_SCRIPT_FILE", "")
    try:
        cfg = json.loads(Path(cfg_path).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return subprocess.CompletedProcess([BASH], 1, "", "RUNTIME_SEAM_SCRIPT_MISSING")
    if "CLEANUP_OK" in script:
        return subprocess.CompletedProcess([BASH], 0, "CLEANUP_OK\n", "")
    if "SESS_HEALTH" in script:
        return subprocess.CompletedProcess([BASH], 0, "SESS_HEALTH=GEN=IDLE\n", "")
    m_url = re.search(r"RURL='([^']+)'", script)
    if not m_url:
        return subprocess.CompletedProcess([BASH], 0, "RUNTIME_SEAM_NO_URL\n", "")
    url = m_url.group(1)
    conv = dict((cfg.get("conversations") or {}).get(url) or {})
    sid = str(conv.get("sid") or "seamsid")
    sent = ""
    m_msg = re.search(r'MSG=\$\(cat "([^"]+)"\)', script)
    if m_msg:
        try:
            sent = Path(_seam_script_path(m_msg.group(1))).read_text(encoding="utf-8", errors="replace")
        except OSError:
            sent = ""
    m_stored = re.search(r"^SID='([^']*)'", script, re.M)
    reattach = "ACQ_MODE=reattach" in script
    entry = {"url": url, "sid": sid, "stored_sid": (m_stored.group(1) if m_stored else None),
             "reattach": reattach, "message": sent}
    cur_path = Path(cfg_path + ".cursor.json")
    try:
        cursors = json.loads(cur_path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        cursors = {}
    failures = list(conv.get("failures") or [])
    if failures:
        tok = str(failures.pop(0))
        conv["failures"] = failures
        cfg.setdefault("conversations", {})[url] = conv
        try:
            atomic_write_text(Path(cfg_path), json.dumps(cfg, ensure_ascii=False))
        except OSError:
            pass
        _seam_script_log(cfg.get("log"), {**entry, "result": tok})
        return subprocess.CompletedProcess([BASH], 0, "RUNTIME_SID=%s\nRUNTIME_SEND=%s\n" % (sid, tok), "")
    fail_after = int(conv.get("fail_after") or 0)
    fail_token = str(conv.get("fail_token") or "")
    if fail_after > 0 and fail_token and int(cursors.get(url, 0)) >= fail_after:
        _seam_script_log(cfg.get("log"), {**entry, "result": fail_token,
                                          "scheduled": "fail_after", "after": fail_after})
        return subprocess.CompletedProcess([BASH], 0, "RUNTIME_SID=%s\nRUNTIME_SEND=%s\n" % (sid, fail_token), "")
    idx = int(cursors.get(url, 0))
    replies = list(conv.get("replies") or [])
    reply = replies[idx] if idx < len(replies) else ""
    cursors[url] = idx + 1
    try:
        atomic_write_text(cur_path, json.dumps(cursors, ensure_ascii=False))
    except OSError:
        pass
    m_reply = re.search(r'yz_recv_last "\$SID" "([^"]+)"', script)
    if m_reply:
        try:
            Path(_seam_script_path(m_reply.group(1))).write_text(reply, encoding="utf-8")
        except OSError:
            pass
    _seam_script_log(cfg.get("log"), {**entry, "result": "DONE", "reply": reply})
    return subprocess.CompletedProcess(
        [BASH], 0,
        "RUNTIME_SID=%s\nRUNTIME_ACQ_MODE=%s\nRUNTIME_SEND=DONE\nRUNTIME_RECV_SID=%s\n"
        % (sid, "reattach" if reattach else "acquire", sid), "")


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
    if seam == "SCRIPT":
        # Deterministic scripted-transport seam (Slice A): per-conversation
        # replies from APC_RUNTIME_INJECT_SCRIPT_FILE. Real bridge untouched.
        return _seam_script_run(script)
    # 2026-09-01 加固:原 subprocess.run(timeout) 超时仅杀 bash 本体,
    # bsk 等孙进程继承管道句柄不关,run() 内部的无界 communicate 会永久阻塞
    # (现场:python+3bash 僵尸 20 分钟)。改为 Popen + 超时后 taskkill /T /F 杀整树。
    proc = subprocess.Popen(
        [BASH, "-c", script],
        stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        stdin=subprocess.DEVNULL,
        creationflags=subprocess.CREATE_NEW_PROCESS_GROUP,
    )
    try:
        out, err = proc.communicate(timeout=timeout)
    except subprocess.TimeoutExpired:
        subprocess.run(["taskkill", "/PID", str(proc.pid), "/T", "/F"],
                       capture_output=True)
        try:
            out, err = proc.communicate(timeout=15)
        except subprocess.TimeoutExpired:
            out, err = b"", b"RUNTIME_BASH_KILL_TREE_INCOMPLETE"
    return subprocess.CompletedProcess(
        [BASH], proc.returncode,
        (out or b"").decode("utf-8", errors="replace"),
        (err or b"").decode("utf-8", errors="replace"),
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
                stored_sid: str = "", ds_mode: str = "") -> str:
    # DeepSeek 的回形针选择器是 CSS module 哈希且随 composer 形态/模式页变化,每次上传前
    # 必须重发现;chooser 拦截在模式选择后偶发未就绪,ds 路径用 yz_ds_upload_once(内含
    # 重发现+3s 重试),gpt 路径保持原直调字节不变
    ds_upload = conv_id_of(r_url)[0] == "ds"
    uploads = []
    for f in files:
        leaf = Path(f).name
        stem = Path(f).stem
        # ChatGPT composer chips truncate long file names, so an exact long-stem
        # keyword can fail to match even when the attachment is present. Match on
        # a short sanitized prefix instead (adapter-side; canonical lib untouched).
        kw = re.sub(r"[^A-Za-z0-9_.-]", "", stem)[:16] or re.sub(r"[^A-Za-z0-9_.-]", "", leaf)[:8]
        if ds_upload:
            uploads.append(
                f'UPERR=$(yz_ds_upload_once "$SID" "{to_posix(f)}" 2>&1) '
                f'|| {{ echo "RUNTIME_UPLOAD_FAIL={leaf} stage=upload raw=$(printf %s "$UPERR" | tr -d \'\\r\\n\' | tail -c 160)"; exit 0; }}'
            )
        else:
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
  SID=$(yz_acquire_conv "$RURL" "$DSMODE")
  ACQ_MODE=acquire
fi
if [ "$SU" = "$RURLT" ] && [ "$G" = "IDLE" ] && [ -n "$DSMODE" ]; then
  ENS=$(yz_ds_ensure_mode "$SID" "$DSMODE")
  case "$ENS" in
    SWITCHED) ACQ_MODE=mode_switch ;;
    FAIL) SID=$(yz_acquire_conv "$RURLT" "$DSMODE"); ACQ_MODE=acquire ;;
  esac
fi
echo "RUNTIME_ACQ_MODE=$ACQ_MODE"
echo "RUNTIME_DBG=su=$SU g=$G"
"""
    else:
        acquire = ('SID=$(yz_acquire_conv "$RURL" "$DSMODE")\n'
                   'echo "RUNTIME_ACQ_MODE=acquire"\n'
                   'echo "RUNTIME_DBG=su=- g=-"\n')
    return f"""set -u
{PATH_PROLOGUE}
source {yz_lib_for(r_url)} >/dev/null 2>&1
RURL='{r_url}'
DSMODE='{ds_mode}'
{acquire}echo "RUNTIME_SID=$SID"
if [ -z "$SID" ]; then echo "RUNTIME_SEND=ACQUIRE_FAILED"; exit 0; fi
{upload_block}
MSG=$(cat "{msg_file_posix}")
RES=$(yz_send_text "$SID" "$MSG" {timeout})
echo "RUNTIME_SEND=$RES"
case "$RES" in DONE|DONE_NO_MARKER)
  yz_recv_last "$SID" "{reply_out_posix}"
  echo "RUNTIME_RECV_SID=$YZ_SID"
  NURL=""; DPMODE=""
  if [ -n "$DSMODE" ]; then
    NURL=$(yz_ds_finalize_new_conv "$SID" "$RURL")
    DPMODE=$(yz_ds_page_mode "$SID")
  fi
  echo "RUNTIME_NEW_URL=$NURL"
  echo "RUNTIME_DS_MODE=$DPMODE"
;; esac
exit 0
"""


def recv_script(sid: str, r_url: str, reply_out_posix: str) -> str:
    return f"""set -u
{PATH_PROLOGUE}
source {yz_lib_for(r_url)} >/dev/null 2>&1
RURL='{r_url}'
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
    stop = f'"$DEV" session stop "{sid}" >/dev/null 2>&1' if sid else "true"
    return f"""set -u
{PATH_PROLOGUE}
source {yz_lib_for(r_url)} >/dev/null 2>&1
{stop}
rm -f "{yz_mapfile_for(r_url)}"
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
source {yz_lib_for(r_url)} >/dev/null 2>&1
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
    _host, conv_id = conv_id_of(r_url)
    return f"""set -u
{PATH_PROLOGUE}
source {yz_lib_for(r_url)} >/dev/null 2>&1
for s in $("$DEV" session list 2>/dev/null | grep -oE '^[a-z]{{4}}'); do
  u=$("$DEV" evaluate --session "$s" "location.href" 2>/dev/null | tr -d '\\r\\n')
  case "$u" in
    *{conv_id}*)
      if [ "$s" != "{keep_sid}" ]; then "$DEV" session stop "$s" >/dev/null 2>&1; echo "RUNTIME_REAPED=$s"; fi
    ;;
  esac
done
echo "{keep_sid}" > "{yz_mapfile_for(r_url)}"
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
    # Review Result Return (V0.1-FIX-REVIEW-RESULT-RETURN): persist a structured,
    # reload-safe binding of this R verdict to the RUN and — when they were
    # supplied at review time — to the Candidate / Evidence under review. This
    # block is written for EVERY verdict branch (including the BLOCKED early
    # return below) so the result never fails to reach durable Runtime state.
    if not state.get("review_id"):
        state["review_id"] = "REV-%s-%s" % (datetime.now().strftime("%Y%m%d-%H%M%S"), uuid.uuid4().hex[:4])
    state["review_result"] = {
        "run_id": state["run_id"],
        "review_id": state["review_id"],
        "candidate_commit": state.get("candidate_commit"),
        "evidence_id": state.get("evidence_id"),
        "verdict": state["last_r_verdict"],
        "next_action": (next_action or "")[:4000],
        "reply_path": str(reply_path),
        "reply_bytes": reply_bytes,
        "returned_at": utc_now(),
    }
    journal(state["run_id"], "REVIEW_RESULT_RETURN", review_id=state["review_id"],
            verdict=state["last_r_verdict"], candidate_commit=state.get("candidate_commit"),
            evidence_id=state.get("evidence_id"), reply_bytes=reply_bytes)
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


def _apply_review_bindings(state: dict, candidate_commit: str | None, evidence_id: str | None,
                           review_id: str | None) -> dict | None:
    """Review Result Return (V0.1-FIX-REVIEW-RESULT-RETURN): validate + persist the
    Candidate / Evidence / Review identity bound to this RUN (RUN_ID is implicit).
    Returns an error doc (caller emits it + EXIT_USAGE, nothing persisted) or None
    when accepted. Empty/None inputs leave any existing durable binding untouched;
    when a candidate is bound and no explicit review id is given, REVIEW_ID reuses
    the existing RUN identity (run_id + review_epoch)."""
    cand = (candidate_commit or "").strip().lower()
    if cand and not CANDIDATE_SHA_RE.fullmatch(cand):
        return {"status": "INVALID_CANDIDATE_COMMIT", "candidate_commit": candidate_commit,
                "instruction": "--candidate-commit must be a full 40-hex commit SHA when provided."}
    ev = clean_text(evidence_id or "")[:256].strip()
    rv = clean_text(review_id or "")[:256].strip()
    if cand:
        state["candidate_commit"] = cand
    if ev:
        state["evidence_id"] = ev
    if rv:
        state["review_id"] = rv
    elif cand and not state.get("review_id"):
        state["review_id"] = "%s#epoch%s" % (state["run_id"], state.get("review_epoch", 1))
    return None


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
        "candidate_commit": None,
        "evidence_id": None,
        "review_id": None,
        "review_result": None,
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
    if not is_valid_r_url(args.r_url):
        emit({"status": "INVALID_R_URL", "r_url": args.r_url,
              "instruction": "R_URL must be a ChatGPT (https://chatgpt.com/c/<id>) or DeepSeek "
                             "(https://chat.deepseek.com/a/chat/s/<id>) conversation. Stop and ask the user."})
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


def _taskgraph_path() -> Path:
    return STATE_ROOT / "tasks.json"


def _load_taskgraph() -> dict:
    p = _taskgraph_path()
    if not p.exists():
        return {"schema_version": 1, "tasks": {}}
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {"schema_version": 1, "tasks": {}}


def _save_taskgraph(g: dict) -> None:
    atomic_write_text(_taskgraph_path(), json.dumps(g, ensure_ascii=False, indent=2))


def _ready_tasks(g: dict) -> list[str]:
    tasks = g.get("tasks", {})
    out = []
    for tid, t in tasks.items():
        if t.get("state") in ("DONE", "BLOCKED"):
            continue
        deps = t.get("deps", [])
        if all(tasks.get(d, {}).get("state") == "DONE" for d in deps):
            out.append(tid)
    return sorted(out)


def cmd_task_add(args) -> int:
    g = _load_taskgraph()
    tasks = g.setdefault("tasks", {})
    if args.task_id in tasks:
        emit({"status": "DENIED", "reason": f"task {args.task_id} already exists"})
        return EXIT_DENIED
    tasks[args.task_id] = {
        "task_id": args.task_id,
        "deps": [d for d in (args.dep or [])],
        "state": args.state or "READY",
        "owner": args.owner or "",
        "artifact": args.artifact or "",
        "updated_at": utc_now(),
    }
    _save_taskgraph(g)
    emit({"status": "OK", "task_id": args.task_id, "ready": _ready_tasks(g)})
    return EXIT_OK


def cmd_task_update(args) -> int:
    g = _load_taskgraph()
    t = g.get("tasks", {}).get(args.task_id)
    if t is None:
        emit({"status": "RUN_NOT_FOUND", "reason": f"task {args.task_id} missing"})
        return EXIT_RUN_NOT_FOUND
    if args.state:
        t["state"] = args.state
    if args.owner is not None:
        t["owner"] = args.owner
    if args.artifact is not None:
        t["artifact"] = args.artifact
    t["updated_at"] = utc_now()
    _save_taskgraph(g)
    emit({"status": "OK", "task_id": args.task_id, "state": t["state"], "ready": _ready_tasks(g)})
    return EXIT_OK


def cmd_task_list(args) -> int:
    g = _load_taskgraph()
    emit({"status": "OK", "tasks": g.get("tasks", {}), "ready": _ready_tasks(g)})
    return EXIT_OK


def cmd_status(args) -> int:
    state, code = _load_or_fail(args.run_id)
    if state is None:
        return code
    out = dict(state)
    out["allowed_actions"] = allowed_actions(state)
    emit(out)
    return EXIT_OK


def cmd_state_verify(args) -> int:
    result = verify_state(args.run_id)
    emit(result)
    return EXIT_OK if result.get("ok") else EXIT_ERR


def cmd_state_recover(args) -> int:
    result = recover_state(args.run_id)
    emit(result)
    return EXIT_OK if result.get("recovered") or result.get("reason") == "current state already valid" else EXIT_ERR


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
    if args.new_r_url and not is_valid_r_url(args.new_r_url):
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
        # Review Result Return: bind Candidate/Evidence/Review identity to this RUN
        # durably BEFORE transport, so the binding survives even if the send fails
        # and is present in state when R's structured verdict returns.
        bind_err = _apply_review_bindings(state, getattr(args, "candidate_commit", None),
                                          getattr(args, "evidence_id", None),
                                          getattr(args, "review_id", None))
        if bind_err:
            emit(bind_err)
            return EXIT_USAGE
        if getattr(args, "candidate_commit", None) or getattr(args, "evidence_id", None) \
                or getattr(args, "review_id", None):
            save_state(state)
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
        # DeepSeek 三模式路由(仅 ds host):识图=图片附件,专家=难任务,其余=快速;
        # 模式绑定会话,不匹配时由 ds lib 在 acquire/reattach 阶段转新对话并回写新 URL。
        ds_mode = ""
        if conv_id_of(state["r_url"])[0] == "ds":
            ds_mode = route_ds_mode(args.message, [f for f, _ in delta_files])
        while True:
            script = send_script(state["r_url"], to_posix(str(msg_file)),
                                 [f for f, _ in delta_files], to_posix(str(reply_file)), args.timeout,
                                 stored_sid=stored_sid, ds_mode=ds_mode)
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
        # DeepSeek 模式切换会开新会话:按 RUNTIME_NEW_URL 重定向 RUN 的 r_url,
        # 后续 requery/recv/cleanup 全部走新会话。
        new_r_url = markers.get("RUNTIME_NEW_URL", "")
        if (new_r_url and conv_id_of(state["r_url"])[0] == "ds"
                and R_URL_DS_RE.match(new_r_url) and new_r_url != state["r_url"]):
            journal(args.run_id, "DS_MODE_RETARGET", old_r_url=state["r_url"], new_r_url=new_r_url,
                    ds_mode=ds_mode)
            state["r_url"] = new_r_url
            save_state(state)
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
                ds_mode=ds_mode, final_ds_mode=markers.get("RUNTIME_DS_MODE", ""),
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
          "review_result": state.get("review_result"),
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
        # Review Result Return: allow (late) binding of Candidate/Evidence/Review
        # identity on the recv path as well; durable before any verdict is applied.
        bind_err = _apply_review_bindings(state, getattr(args, "candidate_commit", None),
                                          getattr(args, "evidence_id", None),
                                          getattr(args, "review_id", None))
        if bind_err:
            emit(bind_err)
            return EXIT_USAGE
        if getattr(args, "candidate_commit", None) or getattr(args, "evidence_id", None) \
                or getattr(args, "review_id", None):
            save_state(state)
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
    if not is_valid_r_url(args.r_url):
        emit({"status": "INVALID_R_URL", "r_url": args.r_url,
              "instruction": "R_URL must be a ChatGPT (https://chatgpt.com/c/<id>) or DeepSeek "
                             "(https://chat.deepseek.com/a/chat/s/<id>) conversation. Stop and ask the user."})
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
# Router V0.1 (Slice A) — minimal B/R role routing on the frozen transport.
#
# Frozen behaviour contract (V0.1 Slice A acceptance, AC-1..AC-11):
#   builder  -> state.role_urls["builder"]  (B conversation only)
#   reviewer -> state.role_urls["reviewer"] (R conversation only)
#   reviewer REWORK -> Runtime auto-builds the rework message and routes it
#   back to the SAME builder conversation; user copy-paste = 0.
# Reuses the frozen bridge scripts (send_script / session machinery), durable
# state, verdict protocol and HARD_BLOCKED terminal semantics. Legacy
# single-R_URL commands are not modified. Phase machine (state["router"]):
#   SEND_GOAL_TO_BUILDER -> SEND_TO_REVIEWER
#     -> PASS: ROUTED_PASS (status DONE, the only PASS path)
#     -> REWORK (round < max): SEND_REWORK_TO_BUILDER -> SEND_TO_REVIEWER ...
#     -> REWORK (round >= max) / BLOCKED / NO_VERDICT / transport budget:
#        HARD_BLOCKED (never PASS)
#
# Continuation (Transport/Continuation Recovery Lite, AC-T5 / AC-T6):
#   router-run   creates a NEW router RUN then drives it in-process.
#   router-step  advances EXACTLY ONE pending phase then exits (frozen).
#   router-continue attaches to an EXISTING router RUN by --run-id and drives
#     the SAME RUN / SAME durable state / SAME role binding forward through its
#     pending phases to a terminal/bounded outcome. It is the deterministic
#     mechanism that guarantees a phase-completed RUN is never left zombie
#     (RUNNING + pending phase + no live driver). Terminal RUNs are reported,
#     never resurrected; transport failure hard-blocks and can never PASS.
#     router-step / router-run behaviour is unchanged (additive command only).
# ---------------------------------------------------------------------------
ROUTER_MODE = "router-v0.1"
ROUTER_MAX_ROUNDS_DEFAULT = 3
ROUTER_BUILDER_OUTPUT_CAP = 20000
ROUTER_PHASES_PENDING = ("SEND_GOAL_TO_BUILDER", "SEND_TO_REVIEWER", "SEND_REWORK_TO_BUILDER")


def _router_conv_id(url: str) -> str:
    """Host-qualified conversation identity ('gpt:<id>'/'ds:<id>'); '' if unknown."""
    host, cid = conv_id_of(url or "")
    return f"{host}:{cid}" if cid != "unknown" else ""


def _router_create(goal: str, b_url: str, r_url: str, worker_id: str, max_rounds: int) -> dict:
    """Create a router RUN durably holding BOTH role conversations. Role URLs
    are taken explicitly per RUN — never inherited from any other RUN."""
    state = _new_run(goal, r_url, worker_id)
    state["mode"] = ROUTER_MODE
    state["role_urls"] = {"builder": b_url, "reviewer": r_url}
    state["role_sessions"] = {"builder": {"sid": None, "epoch": 1},
                              "reviewer": {"sid": None, "epoch": 1}}
    state["router"] = {"phase": "SEND_GOAL_TO_BUILDER", "round": 0,
                       "max_rounds": int(max_rounds),
                       "last_builder_reply_path": None,
                       "last_builder_reply_bytes": 0,
                       "last_review_reply_path": None,
                       "pending_rework": ""}
    state["current_step"] = "router: created, awaiting goal dispatch to builder"
    state["next_action"] = "router-step / router-run: dispatch GOAL to the builder conversation"
    save_state(state)
    journal(state["run_id"], "ROUTER_RUN_CREATED", b_url=b_url, r_url=r_url,
            max_rounds=int(max_rounds), worker=state["worker_identity"])
    return state


def _router_review_envelope(state: dict, builder_reply: str, round_no: int) -> str:
    body = builder_reply[:ROUTER_BUILDER_OUTPUT_CAP]
    note = ("\n[... builder output truncated by router ...]"
            if len(builder_reply) > ROUTER_BUILDER_OUTPUT_CAP else "")
    return ("[Router V0.1 review request | round %d]\n"
            "RUN: %s\nGOAL: %s\n\nBUILDER OUTPUT:\n%s%s\n\n"
            "[Review request] Reply ONLY with the final verdict line: "
            "===REVIEW_VERDICT=== PASS or REWORK or BLOCKED "
            "(plus ===NEXT_ACTION=== instructions when REWORK)."
            % (round_no, state["run_id"], state["goal"], body, note))


def _router_rework_message(next_action: str, round_no: int) -> str:
    return ("[Router V0.1 | REWORK round %d]\n"
            "Reviewer verdict: REWORK\n"
            "Reviewer required changes (NEXT_ACTION):\n%s\n\n"
            "Rework ONLY what the reviewer asked above, then reply with the "
            "updated complete result."
            % (round_no, (next_action or "").strip() or "(no NEXT_ACTION provided)"))


def _router_send_to_role(state: dict, role: str, message: str, timeout: int) -> tuple[str, Path]:
    """One durable send to a role's OWN conversation (never the other role's).
    Returns (reply_text, reply_path). Updates the role session slot, metrics
    and journal. Raises RuntimeError when transport fails beyond budget; the
    caller converts that into durable HARD_BLOCKED (never PASS)."""
    r_url = state["role_urls"][role]
    rd = run_dir(state["run_id"])
    epoch = state["role_sessions"][role].get("epoch", 1)
    stored_sid = state["role_sessions"][role].get("sid") or ""
    msg_file = rd / f"router_{role}_msg_{int(time.time())}_{uuid.uuid4().hex[:6]}.txt"
    atomic_write_text(msg_file, message)
    reply_file = rd / (f"router_{role}_reply_round{state['router']['round']}_"
                       f"{int(time.time())}_{uuid.uuid4().hex[:6]}.txt")
    while True:
        script = send_script(r_url, to_posix(str(msg_file)), [],
                             to_posix(str(reply_file)), timeout, stored_sid=stored_sid)
        t0 = time.time()
        try:
            proc = bash_run(script, timeout=timeout + 240)
            markers = parse_markers(proc.stdout)
            result = markers.get("RUNTIME_SEND", "NO_RESULT")
        except subprocess.TimeoutExpired:
            result, markers = "RUNTIME_TIMEOUT", {}
        except OSError as exc:
            result, markers = f"RUNTIME_ERROR:{exc}", {}
        state["metrics"]["r_wait_time_sec"] = round(
            float(state["metrics"].get("r_wait_time_sec", 0)) + (time.time() - t0), 1)
        if result in ("DONE", "DONE_NO_MARKER"):
            break
        sid = markers.get("RUNTIME_SID") or stored_sid
        if result in ("ACQUIRE_FAILED", "SEND_FAILED"):
            state["metrics"]["session_recoveries"] = int(state["metrics"].get("session_recoveries", 0)) + 1
            if state["metrics"]["session_recoveries"] > MAX_SESSION_RECOVERIES:
                raise RuntimeError(f"router transport to {role} failed beyond budget ({result})")
            journal(state["run_id"], "ROUTER_SESSION_REPLACED", role=role, reason=result, old_sid=sid)
            try:
                bash_run(session_cleanup_script(sid, r_url), timeout=60)
            except (subprocess.TimeoutExpired, OSError):
                pass
            state["role_sessions"][role] = {"sid": None, "epoch": epoch}
            stored_sid = ""
        else:
            state["metrics"]["bridge_retries"] = int(state["metrics"].get("bridge_retries", 0)) + 1
            if state["metrics"]["bridge_retries"] > MAX_BRIDGE_RETRIES:
                raise RuntimeError(f"router transport to {role} failed beyond budget ({result})")
        save_state(state)
        time.sleep(2)
    final_sid = markers.get("RUNTIME_RECV_SID") or markers.get("RUNTIME_SID") or stored_sid
    if final_sid:
        state["role_sessions"][role] = {"sid": final_sid, "epoch": epoch}
    state["metrics"]["r_roundtrips"] = int(state["metrics"].get("r_roundtrips", 0)) + 1
    reply_text = reply_file.read_text(encoding="utf-8", errors="replace") if reply_file.exists() else ""
    journal(state["run_id"], "ROUTER_SEND", role=role, phase=state["router"]["phase"],
            round=state["router"]["round"], result=result, sid=final_sid,
            reply_path=str(reply_file),
            reply_bytes=len(reply_text.encode("utf-8", errors="replace")))
    return reply_text, reply_file


def _router_finalize_pass(state: dict, reply_file: Path, reply_text: str) -> None:
    state["last_r_verdict"] = "PASS"
    state["last_reply_path"] = str(reply_file)
    state["last_reply_bytes"] = len(reply_text.encode("utf-8", errors="replace"))
    state["router"]["phase"] = "ROUTED_PASS"
    state["status"] = "DONE"
    state["metrics"]["finished_at"] = utc_now()
    state["current_step"] = "router: reviewer PASS, RUN finalized"
    state["next_action"] = "Router RUN complete (reviewer PASS). No further actions."
    journal(state["run_id"], "ROUTER_DONE", rounds=state["router"]["round"])
    save_state(state)


def _router_step(state: dict, timeout: int) -> dict:
    """Advance exactly one pending router phase (one transport exchange).
    Caller holds RunLock. Terminal outcomes: DONE via PASS only, otherwise
    durable HARD_BLOCKED — timeout / UNKNOWN can never become PASS."""
    if state.get("mode") != ROUTER_MODE:
        raise PermissionError("not a router RUN")
    phase = state["router"]["phase"]
    if phase not in ROUTER_PHASES_PENDING:
        return {"stepped": False, "phase": phase, "run_status": state["status"]}
    # health gate: a transiently unhealthy bridge keeps the phase (retryable);
    # only an exhausted budget hard-blocks (same semantics as legacy send).
    health = bridge_health(force=False)
    if not health.get("ready"):
        state["metrics"]["bridge_retries"] = int(state["metrics"].get("bridge_retries", 0)) + 1
        if state["metrics"]["bridge_retries"] > MAX_BRIDGE_RETRIES:
            hard_block(state, "router bridge health failed beyond retry budget: "
                       + str(health.get("detail", "")))
            return {"stepped": False, "status": "HARD_BLOCKED", "run_status": state["status"]}
        save_state(state)
        return {"stepped": False, "status": "BRIDGE_UNHEALTHY",
                "detail": health.get("detail", ""), "run_status": state["status"]}
    if phase in ("SEND_GOAL_TO_BUILDER", "SEND_REWORK_TO_BUILDER"):
        message = (state["goal"] if phase == "SEND_GOAL_TO_BUILDER"
                   else _router_rework_message(state["router"].get("pending_rework", ""),
                                               state["router"]["round"]))
        reply, reply_file = _router_send_to_role(state, "builder", message, timeout)
        state["router"]["last_builder_reply_path"] = str(reply_file)
        state["router"]["last_builder_reply_bytes"] = len(reply.encode("utf-8", errors="replace"))
        state["router"]["phase"] = "SEND_TO_REVIEWER"
        state["current_step"] = "router: builder replied (round %d); review pending" % state["router"]["round"]
        state["next_action"] = "router-step: route builder output to the reviewer conversation"
        save_state(state)
        return {"stepped": True, "role": "builder", "phase": "SEND_TO_REVIEWER",
                "reply_path": str(reply_file), "run_status": state["status"]}
    # phase == SEND_TO_REVIEWER
    builder_path = state["router"].get("last_builder_reply_path") or ""
    builder_reply = ""
    if builder_path and Path(builder_path).exists():
        builder_reply = Path(builder_path).read_text(encoding="utf-8", errors="replace")
    envelope = _router_review_envelope(state, builder_reply, state["router"]["round"])
    reply, reply_file = _router_send_to_role(state, "reviewer", envelope, timeout)
    verdict, next_action = parse_verdict(reply)
    requeries = 0
    while verdict is None and requeries < MAX_VERDICT_REQUERIES:
        requeries += 1
        state["metrics"]["verdict_requeries_used"] = int(state["metrics"].get("verdict_requeries_used", 0)) + 1
        save_state(state)
        rq, rq_file = _router_send_to_role(state, "reviewer", REQUERY_TEXT, 180)
        reply, reply_file = rq, rq_file
        verdict, next_action = parse_verdict(reply)
    state["last_r_verdict"] = verdict or "NO_VERDICT"
    state["last_reply_path"] = str(reply_file)
    state["last_reply_bytes"] = len(reply.encode("utf-8", errors="replace"))
    if next_action and verdict in ("PASS", "REWORK"):
        state["last_r_next_action"] = next_action
    state["router"]["last_review_reply_path"] = str(reply_file)
    step = {"stepped": True, "role": "reviewer", "verdict": state["last_r_verdict"]}
    if verdict == "PASS":
        _router_finalize_pass(state, reply_file, reply)
        step.update(phase="ROUTED_PASS", run_status="DONE")
    elif verdict == "REWORK":
        if state["router"]["round"] >= int(state["router"]["max_rounds"]):
            hard_block(state, "ROUTER_MAX_ROUNDS_EXCEEDED: reviewer still REWORK after %d rework round(s)"
                       % state["router"]["round"])
            step.update(phase="MAX_ROUNDS_EXCEEDED", run_status="HARD_BLOCKED")
        else:
            state["router"]["round"] = int(state["router"]["round"]) + 1
            state["metrics"]["rework_count"] = int(state["metrics"].get("rework_count", 0)) + 1
            state["router"]["pending_rework"] = next_action
            state["router"]["phase"] = "SEND_REWORK_TO_BUILDER"
            state["current_step"] = ("router: reviewer REWORK (round %d); returning to SAME builder"
                                     % state["router"]["round"])
            state["next_action"] = "router-step: auto-send the rework message to the same builder conversation"
            journal(state["run_id"], "ROUTER_REWORK", round=state["router"]["round"],
                    next_action=sanitize(next_action))
            save_state(state)
            step.update(phase="SEND_REWORK_TO_BUILDER", run_status="RUNNING")
    elif verdict == "BLOCKED":
        hard_block(state, "R verdict BLOCKED: " + next_action[:500])
        step.update(phase="REVIEWER_BLOCKED", run_status="HARD_BLOCKED")
    else:
        hard_block(state, "ROUTER_NO_VERDICT: reviewer reply unparseable after bounded requeries")
        step.update(phase="NO_VERDICT", run_status="HARD_BLOCKED")
    return step


def _router_validate_urls(b_url: str | None, r_url: str | None) -> tuple[dict | None, int]:
    """Shared B/R URL validation. Returns (error_doc, exit_code) or (None, 0)."""
    if not b_url:
        return ({"status": "MISSING_B_URL",
                 "instruction": "Stop. router commands require --b-url explicitly provided (the frozen "
                                "builder conversation). Do not inherit, guess, or create one."},
                EXIT_MISSING_R_URL)
    if not is_valid_r_url(b_url):
        return ({"status": "INVALID_B_URL", "b_url": b_url,
                 "instruction": "B_URL must be a ChatGPT (https://chatgpt.com/c/<id>) or DeepSeek "
                                "(https://chat.deepseek.com/a/chat/s/<id>) conversation. Stop and ask the user."},
                EXIT_MISSING_R_URL)
    if not r_url:
        return ({"status": "MISSING_R_URL",
                 "instruction": "Stop. router commands require --r-url explicitly provided (the frozen "
                                "reviewer conversation). Do not inherit, guess, or create one."},
                EXIT_MISSING_R_URL)
    if not is_valid_r_url(r_url):
        return ({"status": "INVALID_R_URL", "r_url": r_url,
                 "instruction": "R_URL must be a ChatGPT (https://chatgpt.com/c/<id>) or DeepSeek "
                                "(https://chat.deepseek.com/a/chat/s/<id>) conversation. Stop and ask the user."},
                EXIT_MISSING_R_URL)
    cb, cr = _router_conv_id(b_url), _router_conv_id(r_url)
    if cb and cb == cr:
        return ({"status": "ROUTER_SAME_CONVERSATION", "conversation": cb,
                 "instruction": "B_URL and R_URL must be two different conversations; builder and "
                                "reviewer roles can never share one conversation."},
                EXIT_USAGE)
    return None, 0


def _router_load_goal(args) -> tuple[str | None, dict | None, int]:
    gf = Path(args.goal_file or "")
    if not gf.exists():
        return None, ({"status": "FILE_NOT_FOUND", "file": args.goal_file,
                       "instruction": "router commands require --goal-file <UTF-8 text file with the GOAL>."}), EXIT_USAGE
    goal = gf.read_text(encoding="utf-8", errors="replace").strip()
    if not goal:
        return None, ({"status": "MISSING_GOAL",
                       "instruction": "goal file is empty; the router needs a real GOAL."}), EXIT_USAGE
    return goal, None, 0


def cmd_router_start(args) -> int:
    err, code = _router_validate_urls(args.b_url, args.r_url)
    if err:
        emit(err)
        return code
    goal, err, code = _router_load_goal(args)
    if err:
        emit(err)
        return code
    if args.max_rounds < 0:
        emit({"status": "INVALID_MAX_ROUNDS", "instruction": "--max-rounds must be >= 0."})
        return EXIT_USAGE
    state = _router_create(goal, args.b_url, args.r_url,
                           args.worker_id or "router-v0.1", args.max_rounds)
    emit({"status": "OK", "run_id": state["run_id"], "mode": ROUTER_MODE,
          "phase": state["router"]["phase"], "role_urls": state["role_urls"],
          "next_command": f'& "{_run_cmd_path()}" router-step --run-id {state["run_id"]}'})
    return EXIT_OK


def cmd_router_step(args) -> int:
    state, code = _load_or_fail(args.run_id)
    if state is None:
        return code
    if state.get("mode") != ROUTER_MODE:
        emit({"status": "DENIED",
              "reason": "router-step requires a router RUN (mode=%s)" % state.get("mode")})
        return EXIT_DENIED
    if state["status"] != "RUNNING":
        emit({"status": state["status"], "stepped": False, "run_id": args.run_id,
              "phase": state["router"]["phase"],
              "note": "router RUN is terminal; nothing to step"})
        return EXIT_OK if state["status"] == "DONE" else EXIT_HARD_BLOCKED if state["status"] == "HARD_BLOCKED" else EXIT_ERR
    with RunLock(args.run_id):
        state = load_state(args.run_id)
        if state["status"] != "RUNNING":
            emit({"status": state["status"], "stepped": False, "run_id": args.run_id,
                  "phase": state["router"]["phase"]})
            return EXIT_OK if state["status"] == "DONE" else EXIT_ERR
        try:
            step = _router_step(state, args.timeout)
        except RuntimeError as exc:
            hard_block(state, "router transport failure: %s" % exc)
            emit({"status": "HARD_BLOCKED", "run_id": args.run_id,
                  "reason": state.get("blocked_reason", "")})
            return EXIT_HARD_BLOCKED
    step["run_id"] = args.run_id
    if step.get("status") == "BRIDGE_UNHEALTHY":
        emit(step)
        return EXIT_ERR
    if step.get("run_status") == "HARD_BLOCKED":
        step["status"] = "HARD_BLOCKED"
        emit(step)
        return EXIT_HARD_BLOCKED
    step["status"] = "OK"
    emit(step)
    return EXIT_OK


def _router_drive(rid: str, timeout: int, max_rounds: int) -> list[dict]:
    """Drive one EXISTING router RUN forward through its pending phases.

    Shared continuation core for router-run (immediately after it creates the
    RUN) and router-continue (attaching to an already-created RUN). Same RUN
    id, same durable state, same role binding; bounded step budget; fail-closed
    on transport failure (never PASS). This is the deterministic mechanism that
    prevents a router RUN from being left RUNNING with a pending phase and no
    live driver (AC-T5 / AC-T6).
    """
    steps: list[dict] = []
    cap = 2 * (int(max_rounds) + 2) + 4
    for _ in range(cap):
        with RunLock(rid):
            st = load_state(rid)
            if st["status"] != "RUNNING" or st["router"]["phase"] not in ROUTER_PHASES_PENDING:
                break
            try:
                step = _router_step(st, timeout)
            except RuntimeError as exc:
                hard_block(st, "router transport failure: %s" % exc)
                steps.append({"status": "HARD_BLOCKED"})
                break
        steps.append(step)
        if not step.get("stepped"):
            break
    return steps


def cmd_router_run(args) -> int:
    err, code = _router_validate_urls(args.b_url, args.r_url)
    if err:
        emit(err)
        return code
    goal, err, code = _router_load_goal(args)
    if err:
        emit(err)
        return code
    if args.max_rounds < 0:
        emit({"status": "INVALID_MAX_ROUNDS", "instruction": "--max-rounds must be >= 0."})
        return EXIT_USAGE
    # Runtime-owned prerequisite chain (same as production `work` entry).
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
    state = _router_create(goal, args.b_url, args.r_url,
                           args.worker_id or "router-v0.1", args.max_rounds)
    rid = state["run_id"]
    steps = _router_drive(rid, args.timeout, args.max_rounds)
    final = load_state(rid)
    if final["status"] == "DONE":
        status = "ROUTED_PASS"
    elif final["status"] == "HARD_BLOCKED":
        status = "HARD_BLOCKED"
    else:
        status = "IN_PROGRESS"
    emit({"status": status, "run_id": rid, "run_status": final["status"],
          "mode": ROUTER_MODE, "phase": final["router"]["phase"],
          "rounds": final["router"]["round"], "last_r_verdict": final.get("last_r_verdict"),
          "role_urls": final["role_urls"],
          "builder_session": final["role_sessions"]["builder"].get("sid"),
          "reviewer_session": final["role_sessions"]["reviewer"].get("sid"),
          "steps_executed": len(steps),
          "state_path": str(run_dir(rid) / "state.json"),
          "instruction": ("ROUTED_PASS=delivered; HARD_BLOCKED=read blocked_reason and report; "
                          "IN_PROGRESS=re-run router-step to continue from the durable phase.")})
    return EXIT_OK if status == "ROUTED_PASS" else (EXIT_HARD_BLOCKED if status == "HARD_BLOCKED" else EXIT_ERR)


def cmd_router_continue(args) -> int:
    """Deterministic same-RUN continuation (AC-T5 / AC-T6).

    Attaches to an EXISTING router RUN (no new RUN, no new role binding) and
    drives it forward through its pending phases to a terminal or bounded
    outcome. Resolves the zombie state 'RUNNING + pending phase + no live
    driver': after a phase completed and the previous driver process exited,
    router-continue resumes the SAME RUN / SAME state / SAME role binding at
    the NEXT PHASE. Idempotent and fail-closed: a terminal RUN is reported and
    never resurrected; transport failure hard-blocks and can never PASS.
    """
    state, code = _load_or_fail(args.run_id)
    if state is None:
        return code
    if state.get("mode") != ROUTER_MODE:
        emit({"status": "DENIED",
              "reason": "router-continue requires a router RUN (mode=%s)" % state.get("mode")})
        return EXIT_DENIED
    rid = args.run_id
    if state["status"] != "RUNNING":
        emit({"status": state["status"], "continued": False, "run_id": rid,
              "run_status": state["status"], "mode": ROUTER_MODE,
              "phase": state["router"]["phase"],
              "note": "router RUN is terminal; nothing to continue (not resurrected)"})
        return EXIT_OK if state["status"] == "DONE" else EXIT_HARD_BLOCKED
    # Runtime-owned prerequisite chain (same as router-run / production `work`).
    health = ensure_bridge_ready(force=True)
    if not health.get("ready"):
        detail = str(health.get("detail", ""))
        status = ("RUNTIME_ENV_BLOCKED" if detail.startswith("RUNTIME_ENV_BLOCKED")
                  else "RUNTIME_BROWSER_BLOCKED" if detail.startswith("RUNTIME_BROWSER_BLOCKED")
                  else "BRIDGE_UNHEALTHY")
        emit({"status": status, "detail": detail, "continued": False, "run_id": rid,
              "instruction": "Runtime could not bring the bridge up. Report this output to the user; "
                             "do not research the bridge, browser, or daemon."})
        return EXIT_ERR
    journal(rid, "ROUTER_CONTINUE", phase=state["router"]["phase"])
    max_rounds = int(state["router"].get("max_rounds", ROUTER_MAX_ROUNDS_DEFAULT))
    steps = _router_drive(rid, args.timeout, max_rounds)
    final = load_state(rid)
    if final["status"] == "DONE":
        status = "ROUTED_PASS"
    elif final["status"] == "HARD_BLOCKED":
        status = "HARD_BLOCKED"
    else:
        status = "IN_PROGRESS"
    emit({"status": status, "continued": True, "run_id": rid, "run_status": final["status"],
          "mode": ROUTER_MODE, "phase": final["router"]["phase"],
          "rounds": final["router"]["round"], "last_r_verdict": final.get("last_r_verdict"),
          "role_urls": final["role_urls"],
          "builder_session": final["role_sessions"]["builder"].get("sid"),
          "reviewer_session": final["role_sessions"]["reviewer"].get("sid"),
          "steps_executed": len(steps),
          "state_path": str(run_dir(rid) / "state.json"),
          "instruction": ("ROUTED_PASS=delivered; HARD_BLOCKED=read blocked_reason and report; "
                          "IN_PROGRESS=re-run router-continue to keep driving the same durable RUN.")})
    return EXIT_OK if status == "ROUTED_PASS" else (EXIT_HARD_BLOCKED if status == "HARD_BLOCKED" else EXIT_ERR)


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
    s = sub.add_parser("state-verify"); s.add_argument("--run-id", dest="run_id", required=True)
    s = sub.add_parser("state-recover"); s.add_argument("--run-id", dest="run_id", required=True)
    s = sub.add_parser("task-add")
    s.add_argument("--task-id", dest="task_id", required=True)
    s.add_argument("--dep", action="append", default=[])
    s.add_argument("--state", default="READY")
    s.add_argument("--owner", default="")
    s.add_argument("--artifact", default="")
    s = sub.add_parser("task-update")
    s.add_argument("--task-id", dest="task_id", required=True)
    s.add_argument("--state", default=None)
    s.add_argument("--owner", default=None)
    s.add_argument("--artifact", default=None)
    s = sub.add_parser("task-list")
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
    s.add_argument("--candidate-commit", dest="candidate_commit", default=None)
    s.add_argument("--evidence-id", dest="evidence_id", default=None)
    s.add_argument("--review-id", dest="review_id", default=None)

    s = sub.add_parser("recv")
    s.add_argument("--run-id", dest="run_id", required=True)
    s.add_argument("--candidate-commit", dest="candidate_commit", default=None)
    s.add_argument("--evidence-id", dest="evidence_id", default=None)
    s.add_argument("--review-id", dest="review_id", default=None)
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

    s = sub.add_parser("router-start")
    s.add_argument("--goal-file", dest="goal_file", required=True)
    s.add_argument("--b-url", dest="b_url", default=None)
    s.add_argument("--r-url", dest="r_url", default=None)
    s.add_argument("--worker-id", dest="worker_id", default=None)
    s.add_argument("--max-rounds", dest="max_rounds", type=int, default=ROUTER_MAX_ROUNDS_DEFAULT)

    s = sub.add_parser("router-step")
    s.add_argument("--run-id", dest="run_id", required=True)
    s.add_argument("--timeout", type=int, default=DEFAULT_SEND_TIMEOUT)

    s = sub.add_parser("router-run")
    s.add_argument("--goal-file", dest="goal_file", required=True)
    s.add_argument("--b-url", dest="b_url", default=None)
    s.add_argument("--r-url", dest="r_url", default=None)
    s.add_argument("--worker-id", dest="worker_id", default=None)
    s.add_argument("--max-rounds", dest="max_rounds", type=int, default=ROUTER_MAX_ROUNDS_DEFAULT)
    s.add_argument("--timeout", type=int, default=DEFAULT_SEND_TIMEOUT)

    s = sub.add_parser("router-continue")
    s.add_argument("--run-id", dest="run_id", required=True)
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
        "state-verify": cmd_state_verify, "state-recover": cmd_state_recover,
        "task-add": cmd_task_add, "task-update": cmd_task_update, "task-list": cmd_task_list,
        "send": cmd_send, "recv": cmd_recv, "done": cmd_done, "metrics": cmd_metrics, "health": cmd_health,
        "work": cmd_work, "report": cmd_report,
        "router-start": cmd_router_start, "router-step": cmd_router_step, "router-run": cmd_router_run,
        "router-continue": cmd_router_continue,
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
