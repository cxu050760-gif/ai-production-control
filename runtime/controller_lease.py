# -*- coding: utf-8 -*-
"""controller_lease.py \u2014 \u00a734 Controller \u7ea7 fencing \u7f3a\u53e3\u8865\u9f50 (V1.1-blackbox)

\u5baa\u6cd5 :1226-1242 \u9650\u5236: \u201c\u5982\u679c\u65e7 Controller \u672a\u6b7b\u4ea1\uff0c\u65b0
Controller \u5df2\u7ecf\u63a5\u7ba1\u2026\u65b0 generation \u63a5\u7ba1: \u8001\u7684\u7acb\u5373
\u5931\u53bb Effect Authority\u201d\u3002

D4 \u63d0\u4f9b\u7684 SingleInstanceLock=\u4e92\u65a5\uff08\u4e0d\u8ba9\u65b0\u7684\u8d77\u6765\uff09\u3001
epoch=\u4efb\u52a1\u7ea7\u6388\u6743\u4ee3\uff0c\u4e0d\u8986\u76d6\u201c\u8001 Controller \u672a\u6b7b\u3001\u65b0
\u5df2\u63a5\u7ba1\u65f6\u8001\u6743\u5931\u6548\u201d\u7684 Controller \u7ea7 fencing\u3002

\u672c\u6a21\u5757\u8865\u9f50\u63d0\u4f9b\u542f\u7528\u4ef6\u7ea7 fencing token\uff1a
- Lease / Generation / Fencing Token \uff1a\u5355\u4e00 `state/controller_lease.json`\uff0c
  \u542b {generation, holder, issued_at, expires_at}\u3002
- `acquire`: \u65b0 Controller \u63a5\u7ba1 = generation+1 \u4e0b\u5199\uff08\u8001\u7684\u7acb\u5373\u8d85\u65f6\uff09\u3002
- `check_execute_right`: \u6267\u884c effect \u524d\u5fc5\u9a8c\u81ea\u5df1\u4ecd\u662f\u5f53\u524d\u5408\u6cd5\u4ee3\u3002
  STALE_GENERATION/LEASE_EXPIRED/LEASE_REVOKED -> \u62d2\u7edd\u6267\u884c\uff08\u8001\u6743\u5931\u6548\uff09\u3002
\u4e0e parallel_scheduler \u72ec\u7acb\u3001\u4e0d\u6539\u52a8\u5df2\u6709\u7ed3\u6784\uff1b\u8c03\u7528\u8005
\uff08relay_autopilot\u7b49\uff09\u81ea\u884c\u9009\u62e9\u4f55\u65f6 acquire / check\u3002

GATE-2#6 (hardening 2026-08-31):
- acquire/renew/revoke \u52a0\u8de8\u8fdb\u7a0b\u6587\u4ef6\u9501\uff08O_CREAT|O_EXCL \u539f\u5b50\u521b\u5efa\uff09\uff0c
  \u4fee\u590d\u201c\u5e76\u53d1 acquire \u5f97\u5230\u76f8\u540c generation\u201d\u7684 fencing \u7ade\u6001\u3002
- save_lease \u5199 tmp \u540e fsync \u518d os.replace\uff0c\u65ad\u7535\u4e0d\u7559\u6b8b\u7f3a lease\u3002
- revoked \u6807\u5fd7\u6b64\u524d\u4ece\u4e0d\u88ab\u68c0\u67e5\uff1a\u73b0\u5728 check_execute_right \u5fc5\u67e5\uff0c
  \u5e76\u65b0\u589e revoke() API + CLI \u5b50\u547d\u4ee4\u3002
- expires_at \u7578\u5f62\u65f6\u6b64\u524d\u629b ValueError\uff08\u8c03\u7528\u65b9 catch-and-skip
  \u5373 fail-open\uff09\uff1a\u73b0\u5728\u6309 LEASE_EXPIRED \u62d2\u7edd\uff08fail-closed\uff09\u3002
"""

import json
import os
import argparse
import datetime
import time
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

SCHEMA = "v1.1-controller-lease"
LEASE_FILE = "state/controller_lease.json"
DEFAULT_LEASE_SECONDS = 600
DEFAULT_LOCK_TIMEOUT = 5.0
STALE_LOCK_SECONDS = 10.0

# \u5224\u5b9a\u7ed3\u679c
OK = "OK"
STALE_GENERATION = "STALE_GENERATION"
LEASE_EXPIRED = "LEASE_EXPIRED"
NO_LEASE = "NO_LEASE"
LEASE_REVOKED = "LEASE_REVOKED"


class LeaseLockTimeout(RuntimeError):
    """GATE-2#6: another holder kept the lease lock past the timeout."""


# \u7528\u6237\u63a7\u5236\u5728 state/ \u4e0b\uff0c\u5df2\u88ab .gitignore \u8986\u76d6\uff08B3\uff09


def _repo_root() -> Path:
    return Path(__file__).resolve().parent.parent


def _now_iso() -> str:
    return datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def _utc_from_iso(s: str) -> datetime.datetime:
    return datetime.datetime.fromisoformat(s.replace("Z", "+00:00"))


def default_lease_path() -> str:
    # GATE-3 补强（v16 §4-A 欠账清零 2026-08-31）：遵守 APC_RUNTIME_STATE_ROOT
    # 测试缝（与 runtime.py/harness_verify.py 同约定）。此前本模块恒解析仓根真实
    # state/controller_lease.json，导致全套件回归中 admission 用例对真实租约做
    # 读/续约（audit hook 实证 24 次访问、600s 过期后真实 renew 写入——时间依赖
    # 性 state 污染）。生产/自动化服务不设该 env，行为与此前完全一致。
    env_root = os.environ.get("APC_RUNTIME_STATE_ROOT")
    if env_root:
        return os.path.join(env_root, LEASE_FILE)
    return os.path.join(str(_repo_root()), LEASE_FILE)


def _lease_lock(path: Path, timeout: float = DEFAULT_LOCK_TIMEOUT) -> Tuple[int, Path]:
    """GATE-2#6: cross-process exclusive lock around lease read-modify-write.

    acquire/renew/revoke are read->mutate->write sequences; without a lock two
    concurrent callers could compute the same generation+1 and both win
    (fencing broken). Uses O_CREAT|O_EXCL atomic file creation, self-heals a
    stale lock older than STALE_LOCK_SECONDS, and raises LeaseLockTimeout
    (fail-closed) rather than proceeding unlocked.
    """
    lock_path = Path(str(path) + ".lock")
    deadline = time.monotonic() + max(0.0, float(timeout))
    # The lock may be taken before save_lease ever ran (first acquire on a
    # fresh state root): the parent directory must exist for O_CREAT to work.
    try:
        lock_path.parent.mkdir(parents=True, exist_ok=True)
    except OSError:
        pass
    while True:
        try:
            fd = os.open(str(lock_path), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            return fd, lock_path
        except FileExistsError:
            try:
                if time.time() - lock_path.stat().st_mtime > STALE_LOCK_SECONDS:
                    # P2-3 (internal review): stale reclaim via rename-steal —
                    # os.rename is atomic and the unique winner gets the
                    # reclaim; losers retry the O_EXCL loop and hit the fresh
                    # lock (fail-closed LeaseLockTimeout at worst, never two
                    # holders). Works on POSIX too (where unlink succeeds even
                    # on open files).
                    steal = Path(str(lock_path) + f".stolen-{os.getpid()}-{time.monotonic_ns()}")
                    try:
                        os.rename(str(lock_path), str(steal))
                    except OSError:
                        time.sleep(0.02)
                        continue  # another reclaimer stole it first
                    try:
                        os.remove(str(steal))
                    except OSError:
                        pass
                    continue  # reclaimed: retry O_EXCL on the now-free path
            except OSError:
                pass
            if time.monotonic() >= deadline:
                raise LeaseLockTimeout(f"lease lock busy: {lock_path}")
            time.sleep(0.02)


def _release_lease_lock(fd: int, lock_path: Path) -> None:
    try:
        os.close(fd)
    finally:
        try:
            os.remove(str(lock_path))
        except OSError:
            pass


def load_lease(path: Optional[str] = None) -> Optional[Dict[str, Any]]:
    p = Path(path) if path else Path(default_lease_path())
    try:
        data = json.loads(p.read_text(encoding="utf-8", errors="replace"))
    except Exception:
        return None
    if not isinstance(data, dict) or data.get("schema") != SCHEMA:
        return None
    return data


def save_lease(lease: Dict[str, Any], path: Optional[str] = None) -> Path:
    p = Path(path) if path else Path(default_lease_path())
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = str(p) + f".tmp-{os.getpid()}"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(lease, fh, ensure_ascii=False, indent=2)
        # GATE-2#6: fsync before rename so a crash cannot leave a torn lease
        # file (the fencing token must survive power loss to remain provable).
        fh.flush()
        os.fsync(fh.fileno())
    os.replace(tmp, str(p))
    return p


def acquire(controller_id: str, ttl_seconds: int = DEFAULT_LEASE_SECONDS,
            path: Optional[str] = None,
            now: Optional[datetime.datetime] = None,
            lock_timeout: float = DEFAULT_LOCK_TIMEOUT) -> Dict[str, Any]:
    """\u65b0 Controller \u63a5\u7ba1: generation + 1 \uff08\u8001\u7684\u7acb\u5373\u8d85\u65f6\uff09\u3002

    \u4e0d\u4f9d\u8d56\u8001 lease \u662f\u5426\u6b7b\u4ea1\uff1a\u65b0\u63a5\u7ba1\u5373\u7b97\u5360\u4f4d\u3002
    \u8fd4\u56de\u65b0 lease\uff08\u542b\u65b0 generation + \u6211\u7684 holder \u5757\uff09\u3002
    \u8c03\u7528\u8005\u5e94\u5c06\u8fd4\u56de\u7684 generation \u6301\u6709\u4e3a\u81ea\u5df1\u7684\u6267\u884c\u4ee3\u5272
    \uff08\u5728\u5b9e\u9645\u6267\u884c effect \u524d check_execute_right\uff09\u3002

    GATE-2#6: read-modify-write \u73b0\u5728\u5728\u8de8\u8fdb\u7a0b\u6587\u4ef6\u9501\u4e0b\u4e32\u884c\u5316\u3002
    """
    now = now or datetime.datetime.now(datetime.timezone.utc)
    p = Path(path) if path else Path(default_lease_path())
    fd, lock_path = _lease_lock(p, timeout=lock_timeout)
    try:
        prev = load_lease(path)
        gen = int(prev.get("generation", 0)) + 1 if prev else 1
        issued_at = now.isoformat(timespec="seconds").replace("+00:00", "Z")
        expires_at = (now + datetime.timedelta(seconds=int(ttl_seconds))).isoformat(timespec="seconds").replace("+00:00", "Z")
        lease = {
            "schema": SCHEMA,
            "generation": gen,
            "holder": controller_id,
            "issued_at": issued_at,
            "expires_at": expires_at,
            "ttl_seconds": int(ttl_seconds),
            "previous_generation": int(prev.get("generation", 0)) if prev else 0,
            "revoked": False,
            "revoked_at": None,
            "revoke_reason": None,
            "non_authority": True,
        }
        save_lease(lease, path)
    finally:
        _release_lease_lock(fd, lock_path)
    return lease


def renew(controller_id: str, generation: int, ttl_seconds: int = DEFAULT_LEASE_SECONDS,
          path: Optional[str] = None, now: Optional[datetime.datetime] = None) -> Dict[str, Any]:
    """\u540c\u4ee3\u6301\u6709\u8005\u7eed\u7ea6\uff1a\u4ec5\u5f53 generation \u4ecd\u662f\u5f53\u524d\u4ee3\u4e14 holder \u5339\u914d\u3002

    GATE-2#6: read-modify-write \u5728\u8de8\u8fdb\u7a0b\u6587\u4ef6\u9501\u4e0b\u4e32\u884c\u5316\u3002
    """
    now = now or datetime.datetime.now(datetime.timezone.utc)
    p = Path(path) if path else Path(default_lease_path())
    fd, lock_path = _lease_lock(p)
    try:
        cur = load_lease(path)
        if not cur:
            return {"schema": SCHEMA, "ok": False, "reason": NO_LEASE, "error": "no lease installed"}
        if int(cur.get("generation", 0)) != int(generation):
            return {"schema": SCHEMA, "ok": False, "reason": STALE_GENERATION,
                    "error": f"current generation {cur.get('generation')} != mine {generation}"}
        if cur.get("holder") != controller_id:
            return {"schema": SCHEMA, "ok": False, "reason": STALE_GENERATION,
                    "error": "lease held by another controller"}
        if cur.get("revoked"):
            # GATE-2#6: a revoked lease must not be renewable (revoke would be
            # bypassable otherwise). Fresh authority requires a new acquire.
            return {"schema": SCHEMA, "ok": False, "reason": LEASE_REVOKED,
                    "error": (f"lease revoked at {cur.get('revoked_at')}; "
                              "renewal denied — acquire a new generation")}

        # \u65f6\u95f4\u5230\u671f\u4e86\u4e5f\u5141\u8bb8\u540c\u4ee3\u7eed\u7ea6\uff08\u9650\u5236: \u53ea\u6709\u540c\u4ee3\u540c holder \u53ef\u7eed\uff09
        issued_at = now.isoformat(timespec="seconds").replace("+00:00", "Z")
        new = dict(cur)
        new["issued_at"] = issued_at
        new["expires_at"] = (now + datetime.timedelta(seconds=int(ttl_seconds))).isoformat(timespec="seconds").replace("+00:00", "Z")
        new["ttl_seconds"] = int(ttl_seconds)
        new["renewed_at"] = issued_at
        save_lease(new, path)
    finally:
        _release_lease_lock(fd, lock_path)
    # Success/failure return the same envelope (ok/reason/lease): callers
    # branch on ok and must never parse a bare lease dict. (P3 fix)
    return {"schema": SCHEMA, "ok": True, "reason": OK, "lease": new}


def check_execute_right(controller_id: str, generation: int,
                        path: Optional[str] = None,
                        now: Optional[datetime.datetime] = None) -> Dict[str, Any]:
    """\u6267\u884c effect \u524d\u6821\u9a8c\uff1a\u81ea\u5df1\u662f\u5426\u4ecd\u662f\u5f53\u524d\u5408\u6cd5\u6267\u884c\u4ee3\u3002

    \u8fd4\u56de: {ok: bool, reason: OK|STALE_GENERATION|LEASE_EXPIRED|NO_LEASE|LEASE_REVOKED, lease: ...}
    """
    now = now or datetime.datetime.now(datetime.timezone.utc)
    cur = load_lease(path)
    if not cur:
        return {"schema": SCHEMA, "ok": False, "reason": NO_LEASE,
                "error": "no lease installed (fail-closed: cannot prove authority)"}
    if cur.get("revoked"):
        # GATE-2#6: the revoked flag previously existed but was never checked.
        return {"schema": SCHEMA, "ok": False, "reason": LEASE_REVOKED,
                "error": (f"lease revoked at {cur.get('revoked_at')}: "
                          f"{cur.get('revoke_reason') or 'no reason recorded'}")}
    if int(cur.get("generation", 0)) != int(generation):
        return {"schema": SCHEMA, "ok": False, "reason": STALE_GENERATION,
                "error": (f"my generation {generation} < current generation "
                          f"{cur.get('generation')}: old authority revoked (\u00a734)" )}
    if cur.get("holder") != controller_id:
        return {"schema": SCHEMA, "ok": False, "reason": STALE_GENERATION,
                "error": "lease held by another controller; this instance has no authority"}
    # GATE-2#6: a malformed expires_at previously raised ValueError out of
    # this check (and callers skipped the gate -> fail-open). Unparsable
    # expiry cannot prove validity, so it is treated as expired (fail-closed).
    try:
        expires_at = _utc_from_iso(cur.get("expires_at", "")) if cur.get("expires_at") else None
    except (ValueError, TypeError):
        return {"schema": SCHEMA, "ok": False, "reason": LEASE_EXPIRED,
                "error": ("lease expires_at malformed (fail-closed: "
                          "cannot prove validity); renew or re-acquire")}
    if expires_at is not None and now > expires_at:
        return {"schema": SCHEMA, "ok": False, "reason": LEASE_EXPIRED,
                "error": "lease expired; renew the lease before executing effects"}
    return {"schema": SCHEMA, "ok": True, "reason": OK, "lease": cur}


def revoke(path: Optional[str] = None, *, reason: str = "",
           now: Optional[datetime.datetime] = None) -> Dict[str, Any]:
    """GATE-2#6: revoke the current lease immediately.

    The old holder loses Effect Authority at once (\u00a734). A later acquire
    starts a fresh non-revoked generation. Locks the file like acquire.
    """
    now = now or datetime.datetime.now(datetime.timezone.utc)
    p = Path(path) if path else Path(default_lease_path())
    fd, lock_path = _lease_lock(p)
    try:
        cur = load_lease(path)
        if not cur:
            return {"schema": SCHEMA, "ok": False, "reason": NO_LEASE, "error": "no lease installed"}
        cur["revoked"] = True
        cur["revoked_at"] = now.isoformat(timespec="seconds").replace("+00:00", "Z")
        cur["revoke_reason"] = str(reason or "revoked by operator")
        save_lease(cur, path)
    finally:
        _release_lease_lock(fd, lock_path)
    return {"schema": SCHEMA, "ok": True, "reason": OK, "lease": cur}


def cmd_acquire(args: argparse.Namespace) -> int:
    result = acquire(args.controller, ttl_seconds=args.ttl)
    print(json.dumps({"schema": SCHEMA, "ok": True, "generation": result["generation"],
                      "holder": result["holder"], "expires_at": result["expires_at"]},
                     ensure_ascii=False, indent=2))
    return 0


def cmd_check(args: argparse.Namespace) -> int:
    r = check_execute_right(args.controller, int(args.generation))
    print(json.dumps(r, ensure_ascii=False, indent=2, default=str))
    return 0 if r["ok"] else 2


def cmd_revoke(args: argparse.Namespace) -> int:
    r = revoke(reason=args.reason)
    print(json.dumps(r, ensure_ascii=False, indent=2, default=str))
    return 0 if r["ok"] else 2


def cmd_status(args: argparse.Namespace) -> int:
    lease = load_lease()
    if not lease:
        print(json.dumps({"schema": SCHEMA, "lease": None}))
        return 0
    print(json.dumps({"schema": SCHEMA, "lease": lease}, ensure_ascii=False, indent=2, default=str))
    return 0


def main(argv=None):
    parser = argparse.ArgumentParser(description="\u00a734 Controller \u7ea7 fencing Token (lease)")
    sub = parser.add_subparsers(dest="cmd", required=True)
    p_a = sub.add_parser("acquire", help="\u65b0 Controller \u63a5\u7ba1 (generation+1)")
    p_a.add_argument("--controller", required=True)
    p_a.add_argument("--ttl", type=int, default=DEFAULT_LEASE_SECONDS)
    p_a.set_defaults(func=cmd_acquire)
    p_c = sub.add_parser("check", help="\u6267\u884c\u524d\u9a8c\u8bc1\u81ea\u5df1\u662f\u5f53\u524d\u4ee3")
    p_c.add_argument("--controller", required=True)
    p_c.add_argument("--generation", required=True)
    p_c.set_defaults(func=cmd_check)
    p_r = sub.add_parser("revoke", help="GATE-2#6: \u7acb\u5373\u64a4\u9500\u5f53\u524d lease\uff08\u65e7\u6743\u7acb\u5373\u5931\u6548\uff09")
    p_r.add_argument("--reason", default="")
    p_r.set_defaults(func=cmd_revoke)
    p_s = sub.add_parser("status", help="\u5f53\u524d lease")
    p_s.set_defaults(func=cmd_status)
    args = parser.parse_args(argv)
    try:
        return args.func(args)
    except KeyboardInterrupt:
        return 130
    except Exception as exc:  # noqa: BLE001
        print(f"ERROR: {exc}", file=__import__("sys").stderr)
        return 1


if __name__ == "__main__":
    import sys
    sys.exit(main())
