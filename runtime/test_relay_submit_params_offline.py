#!/usr/bin/env python3
"""Hardening batch A 欠账补测（FINAL_PROMPT v16 §4-A 零测试扫描已知起点）。

Covers:
  R1  admission lease 续约分支成功路径（自己持有的过期租约同代续约 → renewed,
      admitted=True）—— P1-1：wiring 假 check 恒 OK，renew 从未被测试执行
  R2  续约被拒（期间被接管/吊销）→ renew-denied 且 admitted=False（fencing 不弱化）
  R3  check-OK 路径必须落 checks["lease"]（P3 KeyError 修复回归钉）
  R4  LEASE_REVOKED（非过期类拒绝）不得触发 renew（不可借续约复活已撤销权）
  E1  build_event --repo-path 注入 → event.repo_path 为注入值（GATE-5 硬编码消除）
  E2  build_event --review-packet 注入 → event.review_packet 为注入值；不存在的
      注入路径回落 REVIEW_PACKET_ROOT 目录（existsSync 语义）
  E3  build_event --evidence-path 多值注入 → event.evidence_paths 保序透传
  E4  build_event 全默认且注入路径不存在 → 回落遗留常量/允许根
  E5  cmd_submit argparse→build_event 接线：getattr 链把三参数正确传给 build_event
  E6  build_parser 参数面：--repo-path/--review-packet/--evidence-path 存在且 dest 正确
  D1  cmd_drive lease 门异常 → fail-closed 返回 2（P1-4：旧 catch-and-skip
      fail-open 已消除，drive 不再无授权推进）

All offline: 全部闸门/收件箱/账本以 mock 注入，不触真实 relay 状态、不写真实 state/。
"""
import argparse
import contextlib
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

HERE = Path(__file__).resolve().parent
SCRIPTS = HERE.parent / "scripts"
for p in (str(HERE), str(SCRIPTS)):
    if p not in sys.path:
        sys.path.insert(0, p)

import relay_autopilot as ra  # noqa: E402

GOAL = {"goal_id": "G-PARAM-1", "title": "Param test", "objective": "Do it."}


def _isolate_non_lease_gates():
    """把 cost/context 两闸钉在放行值，使被测分支只剩 lease 门逻辑。"""
    return (
        mock.patch.object(ra.cost_router, "load_policy", return_value={}),
        mock.patch.object(ra.cost_router, "load_registry_costs", return_value={}),
        mock.patch.object(ra.cost_router, "load_state", return_value={}),
        mock.patch.object(ra.cost_router, "do_route",
                          return_value={"verdict": "ALLOWED"}),
        mock.patch.object(ra.context_sufficiency, "route",
                          return_value={"decision": "PROCEED"}),
    )


class LeaseRenewBranchTests(unittest.TestCase):
    """P1-1：admission lease 续约分支（878da28/294ce2e 引入，零测试欠账）。"""

    def _run(self, lease, check, renew=None):
        """在隔离沙箱中执行 admission_checks(require_gates=True)。

        返回 (admission 结果, renew 的 MagicMock 或 None——None 表示未挂 renew 桩,
        可用 assertIsNone 判定"未触发续约")。
        """
        old_wiring = ra._WIRING_AVAILABLE
        ra._WIRING_AVAILABLE = True
        self.addCleanup(setattr, ra, "_WIRING_AVAILABLE", old_wiring)
        renew_m = None
        with contextlib.ExitStack() as stack:
            for p in _isolate_non_lease_gates():
                stack.enter_context(p)
            stack.enter_context(mock.patch.object(
                ra.controller_lease, "load_lease", return_value=lease))
            stack.enter_context(mock.patch.object(
                ra.controller_lease, "check_execute_right", return_value=check))
            if renew is not None:
                renew_m = mock.MagicMock(return_value=renew)
                stack.enter_context(mock.patch.object(
                    ra.controller_lease, "renew", renew_m))
            res = ra.admission_checks(GOAL, require_gates=True)
        return res, renew_m

    def test_r1_renew_success_admits(self):
        lease = {"generation": 3, "holder": "relay_autopilot",
                 "expires_at": "2020-01-01T00:00:00Z"}
        res, renew_m = self._run(
            lease,
            {"ok": False, "reason": "LEASE_EXPIRED"},
            renew={"ok": True, "lease": {"generation": 3, "holder": "relay_autopilot"}})
        self.assertTrue(res["admitted"], res)
        self.assertEqual(renew_m.call_count, 1)
        renew_m.assert_called_with("relay_autopilot", 3)   # 同代续约
        chk = res["checks"]["lease"]
        self.assertEqual(chk.get("action"), "renewed")
        self.assertTrue(chk.get("ok"))
        self.assertEqual(chk.get("generation"), 3)

    def test_r2_renew_denied_fails_closed(self):
        lease = {"generation": 3, "holder": "relay_autopilot",
                 "expires_at": "2020-01-01T00:00:00Z"}
        res, _renew_m = self._run(
            lease,
            {"ok": False, "reason": "LEASE_EXPIRED"},
            renew={"ok": False, "reason": "LEASE_TAKEN_OVER"})
        self.assertFalse(res["admitted"])
        chk = res["checks"]["lease"]
        self.assertEqual(chk.get("action"), "renew-denied")
        self.assertFalse(chk.get("ok"))
        self.assertEqual(chk.get("reason"), "LEASE_TAKEN_OVER")
        self.assertTrue(any("lease-gate" in r for r in res["reasons"]), res["reasons"])

    def test_r3_check_ok_lands_checks_entry(self):
        """KeyError 回归钉：check-OK 路径必须先落 checks["lease"]（P3 修复锚）。"""
        lease = {"generation": 9, "holder": "relay_autopilot",
                 "expires_at": "2099-01-01T00:00:00Z"}
        res, renew_m = self._run(lease, {"ok": True, "reason": "OK"})
        self.assertTrue(res["admitted"])
        self.assertIsNone(renew_m)                       # 未挂 renew 桩亦不应触发
        self.assertEqual(res["checks"]["lease"], {"ok": True, "reason": "OK"})

    def test_r4_revoked_never_renews(self):
        """已撤销权不可借续约复活：非 LEASE_EXPIRED 拒绝不走 renew。"""
        lease = {"generation": 5, "holder": "relay_autopilot",
                 "expires_at": "2099-01-01T00:00:00Z"}
        res, renew_m = self._run(lease, {"ok": False, "reason": "LEASE_REVOKED"},
                                 renew={"ok": True, "lease": {"generation": 5}})
        self.assertFalse(res["admitted"])
        self.assertIsNotNone(renew_m)
        renew_m.assert_not_called()                      # renew 未被调用
        self.assertEqual(res["checks"]["lease"], {"ok": False, "reason": "LEASE_REVOKED"})


class RelayExplicitInputContractTests(unittest.TestCase):
    """P1-1/P1-2（外审 R-REWORK 20260901）：relay 三项参数显式输入契约。

    缺任一项或任一路径不存在必须 rc=2，且失败必须发生在
    admission/build_event/投递之前；mock 模式不受影响。
    """

    def _relay_args(self, mode="relay", repo=None, packet=None, evidence=None):
        return argparse.Namespace(
            goal_file="g.json", mode=mode, candidate_commit="a" * 40,
            repo_path=repo, review_packet=packet, evidence_path=evidence)

    def _run(self, args, tmp):
        repo = Path(tmp) / "repo"
        repo.mkdir(exist_ok=True)
        pkt = Path(tmp) / "packet.txt"
        pkt.write_text("p", encoding="utf-8")
        ev1 = Path(tmp) / "ev1.json"
        ev1.write_text("{}", encoding="utf-8")
        args.repo_path = args.repo_path if args.repo_path != "@tmp_repo" else str(repo)
        args.review_packet = args.review_packet if args.review_packet != "@tmp_pkt" else str(pkt)
        if args.evidence_path == "@tmp_ev":
            args.evidence_path = [str(ev1)]
        elif isinstance(args.evidence_path, list) and "@tmp_ev" in args.evidence_path:
            args.evidence_path = [
                str(ev1) if e == "@tmp_ev" else e for e in args.evidence_path]
        admission_m = mock.MagicMock(
            return_value={"admitted": True, "checks": {}, "reasons": []})
        with mock.patch.object(ra, "load_json", return_value=dict(GOAL)), \
             mock.patch.object(ra, "admission_checks", admission_m), \
             mock.patch.object(ra, "ledger", return_value=None):
            rc = ra.cmd_submit(args)
        return rc, admission_m

    def test_n1_relay_repo_missing_rejected_before_admission(self):
        with tempfile.TemporaryDirectory() as tmp:
            rc, adm = self._run(self._relay_args(repo="X:\\no\\such\\repo",
                                                 packet="@tmp_pkt", evidence="@tmp_ev"), tmp)
        self.assertEqual(rc, 2)
        adm.assert_not_called()

    def test_n2_relay_evidence_absent_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            rc, adm = self._run(self._relay_args(repo="@tmp_repo",
                                                 packet="@tmp_pkt", evidence=None), tmp)
        self.assertEqual(rc, 2)
        adm.assert_not_called()

    def test_n3_relay_mixed_evidence_missing_one_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            rc, adm = self._run(self._relay_args(
                repo="@tmp_repo", packet="@tmp_pkt",
                evidence=["@tmp_ev", "X:\\no\\such\\ev.json"]), tmp)
        self.assertEqual(rc, 2)
        adm.assert_not_called()

    def test_n4_relay_packet_absent_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            rc, adm = self._run(self._relay_args(repo="@tmp_repo",
                                                 packet=None, evidence="@tmp_ev"), tmp)
        self.assertEqual(rc, 2)
        adm.assert_not_called()

    def _build(self, **kwargs):
        """与 BuildEventParamTests._build 同构（本类本地副本）。"""
        exists = kwargs.pop("_exists", None)
        with contextlib.ExitStack() as stack:
            stack.enter_context(mock.patch.object(
                ra, "load_relay_config",
                return_value={"project_id": "P-TEST",
                              "automation": {"current_milestone": "V1.1"}}))
            stack.enter_context(mock.patch.object(
                ra, "load_builder_binding",
                return_value={"provider": "prov", "model": "mod",
                              "conversation_id": "conv", "generation": 7}))
            if exists is not None:
                stack.enter_context(mock.patch.object(
                    ra.os.path, "exists", return_value=exists))
            return ra.build_event(GOAL, 42, None, **kwargs)

    def test_n5_build_event_relay_contract_enforced(self):
        with self.assertRaises(ValueError):
            self._build(relay_mode=True)          # 全缺省
        with self.assertRaises(ValueError):
            self._build(relay_mode=True, repo_path="X:\\no\\repo",
                        review_packet=None, evidence_paths=None)
        with self.assertRaises(ValueError):
            self._build(relay_mode=True, repo_path="X:\\no\\repo",
                        review_packet=None,
                        evidence_paths=["X:\\no\\ev.json"])

    def test_n6_relay_all_valid_passes_contract(self):
        import subprocess as sp
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp) / "repo"
            repo.mkdir()
            sp.run(["git", "init", "-q", str(repo)], check=True)
            sp.run(["git", "-C", str(repo), "-c", "user.email=t@t", "-c",
                    "user.name=t", "commit", "--allow-empty", "-q",
                    "-m", "init"], check=True)
            head = sp.run(["git", "-C", str(repo), "rev-parse", "HEAD"],
                          capture_output=True, text=True).stdout.strip()
            pkt = Path(tmp) / "packet.txt"
            pkt.write_text("p", encoding="utf-8")
            ev1 = Path(tmp) / "ev1.json"
            ev1.write_text("{}", encoding="utf-8")
            args = self._relay_args(repo=str(repo), packet=str(pkt),
                                    evidence=[str(ev1)])
            args.candidate_commit = head
            admission_m = mock.MagicMock(
                return_value={"admitted": True, "checks": {}, "reasons": []})
            build_m = mock.MagicMock(return_value={
                "event_id": "EV-T", "run_id": "RUN-T", "task_id": "TASK-T"})
            with tempfile.TemporaryDirectory() as inbox:
                with mock.patch.object(ra, "load_json", return_value=dict(GOAL)), \
                     mock.patch.object(ra, "admission_checks", admission_m), \
                     mock.patch.object(ra, "build_event", build_m), \
                     mock.patch.object(ra, "save_json", return_value=None), \
                     mock.patch.object(ra, "ledger", return_value=None), \
                     mock.patch.object(ra, "SANDBOX_INBOX", inbox):
                    rc = ra.cmd_submit(args)
            self.assertEqual(rc, 0)
            admission_m.assert_called_once()
            build_m.assert_called_once()

    def test_n7_relay_fabricated_commit_rejected_before_admission(self):
        """R-终裁 REWORK：40-hex 格式合法但对象不存在的伪造 commit 必须
        在 admission 前 rc=2（git cat-file -e 校验）。"""
        import subprocess as sp
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp) / "repo"
            repo.mkdir()
            sp.run(["git", "init", "-q", str(repo)], check=True)
            sp.run(["git", "-C", str(repo), "-c", "user.email=t@t", "-c",
                    "user.name=t", "commit", "--allow-empty", "-q",
                    "-m", "init"], check=True)
            pkt = Path(tmp) / "packet.txt"
            pkt.write_text("p", encoding="utf-8")
            ev1 = Path(tmp) / "ev1.json"
            ev1.write_text("{}", encoding="utf-8")
            args = self._relay_args(repo=str(repo), packet=str(pkt),
                                    evidence=[str(ev1)])
            args.candidate_commit = "f" * 40   # 格式合法、对象不存在
            admission_m = mock.MagicMock(
                return_value={"admitted": True, "checks": {}, "reasons": []})
            with mock.patch.object(ra, "load_json", return_value=dict(GOAL)), \
                 mock.patch.object(ra, "admission_checks", admission_m), \
                 mock.patch.object(ra, "ledger", return_value=None):
                rc = ra.cmd_submit(args)
        self.assertEqual(rc, 2)
        admission_m.assert_not_called()


class BuildEventParamTests(unittest.TestCase):
    """P1-2：--repo-path/--review-packet/--evidence-path 三参数与 build_event 接线。"""

    def _patches(self, exists=None):
        ps = [
            mock.patch.object(ra, "load_relay_config",
                              return_value={"project_id": "P-TEST",
                                            "automation": {"current_milestone": "V1.1"}}),
            mock.patch.object(ra, "load_builder_binding",
                              return_value={"provider": "prov", "model": "mod",
                                            "conversation_id": "conv", "generation": 7}),
        ]
        if exists is not None:
            ps.append(mock.patch.object(ra.os.path, "exists", return_value=exists))
        return ps

    def _build(self, **kwargs):
        exists = kwargs.pop("_exists", None)
        with contextlib.ExitStack() as stack:
            for p in self._patches(exists=exists):
                stack.enter_context(p)
            return ra.build_event(GOAL, 42, None, **kwargs)

    def test_e1_repo_path_injected(self):
        ev = self._build(repo_path="X:\\real\\repo")
        self.assertEqual(ev["repo_path"], "X:\\real\\repo")

    def test_e2_review_packet_injected_and_fallback(self):
        import os as _os
        with tempfile.TemporaryDirectory() as d:
            real = Path(d) / "packet_exists.txt"
            real.write_text("packet", encoding="utf-8")
            ev = self._build(review_packet=str(real))
            self.assertEqual(ev["review_packet"], str(real))
        # P2-3（盲审 fa5406f）：显式注入路径不存在 → fail-closed 抛错，
        # 不再静默回落 round18 遗留根（会话串台根因）。
        self.assertFalse(_os.path.exists("X:\\pk\\missing.txt"))
        with self.assertRaises(ValueError):
            self._build(review_packet="X:\\pk\\missing.txt")
        # 未注入（None）且默认 packet 不存在 → 仍回落 packet 允许根目录
        ev2 = self._build(_exists=False)
        self.assertEqual(ev2["review_packet"], ra.REVIEW_PACKET_ROOT)

    def test_e3_evidence_paths_passthrough(self):
        evs = ["X:\\ev\\one", "X:\\ev\\two"]
        ev = self._build(evidence_paths=evs)
        self.assertEqual(ev["evidence_paths"], evs)

    def test_e4_defaults_fall_back_when_missing(self):
        ev = self._build(_exists=False)
        self.assertEqual(ev["repo_path"], ra.ALLOWED_REPO_ROOT)
        self.assertEqual(ev["review_packet"], ra.REVIEW_PACKET_ROOT)
        self.assertEqual(ev["evidence_paths"], [ra.ALLOWED_EVIDENCE_ROOT])


class SubmitWiringTests(unittest.TestCase):
    """cmd_submit 的 getattr 链 + build_parser 参数面（P1-2 接线钉）。"""

    def test_e5_cmd_submit_passes_three_params_to_build_event(self):
        # P2-3 后：显式 review_packet 必须真实存在 → 用临时文件注入
        with tempfile.TemporaryDirectory() as pkd:
            packet = Path(pkd) / "packet.txt"
            packet.write_text("packet", encoding="utf-8")
            args = argparse.Namespace(
                goal_file="g.json", mode="mock", candidate_commit=None,
                repo_path="X:\\real\\repo", review_packet=str(packet),
                evidence_path=["X:\\e1", "X:\\e2"])
            captured = {}

            def fake_build_event(goal, seq, commit, relay_mode=False, **kw):
                captured.update(kw)
                captured["relay_mode"] = relay_mode
                captured["commit"] = commit
                return {"event_id": "EV-T", "run_id": "RUN-T", "task_id": "TASK-T"}

            with tempfile.TemporaryDirectory() as inbox:
                with mock.patch.object(ra, "load_json", return_value=dict(GOAL)), \
                     mock.patch.object(ra, "admission_checks",
                                       return_value={"admitted": True, "checks": {}, "reasons": []}), \
                     mock.patch.object(ra, "build_event", side_effect=fake_build_event), \
                     mock.patch.object(ra, "save_json", return_value=None) as sj, \
                     mock.patch.object(ra, "ledger", return_value=None), \
                     mock.patch.object(ra, "SANDBOX_INBOX", inbox):
                    rc = ra.cmd_submit(args)
        self.assertEqual(rc, 0)
        self.assertEqual(captured.get("repo_path"), "X:\\real\\repo")
        self.assertEqual(Path(captured.get("review_packet")), packet)
        self.assertEqual(captured.get("evidence_paths"), ["X:\\e1", "X:\\e2"])
        self.assertFalse(captured.get("relay_mode"))
        sj.assert_called_once()

    def test_e6_parser_surface(self):
        parser = ra.build_parser()
        hex40 = "a" * 40
        ns = parser.parse_args([
            "submit", "--goal-file", "g.json", "--mode", "relay",
            "--candidate-commit", hex40,
            "--repo-path", "X:\\r", "--review-packet", "X:\\p",
            "--evidence-path", "X:\\e1", "--evidence-path", "X:\\e2"])
        self.assertIs(ns.func, ra.cmd_submit)
        self.assertEqual(ns.repo_path, "X:\\r")
        self.assertEqual(ns.review_packet, "X:\\p")
        self.assertEqual(ns.evidence_path, ["X:\\e1", "X:\\e2"])
        self.assertEqual(ns.candidate_commit, hex40)
        self.assertEqual(ns.mode, "relay")

    def test_e7_cmd_submit_missing_packet_fails_closed(self):
        """P2-3：显式 --review-packet 不存在 → cmd_submit 直接拒（rc=2），
        且不得进入 admission/build_event。"""
        args = argparse.Namespace(
            goal_file="g.json", mode="relay", candidate_commit=None,
            repo_path=None, review_packet="X:\\pk\\missing.txt",
            evidence_path=None)
        admission_m = mock.MagicMock(
            return_value={"admitted": True, "checks": {}, "reasons": []})
        with mock.patch.object(ra, "load_json", return_value=dict(GOAL)), \
             mock.patch.object(ra, "admission_checks", admission_m), \
             mock.patch.object(ra, "ledger", return_value=None):
            rc = ra.cmd_submit(args)
        self.assertEqual(rc, 2)
        admission_m.assert_not_called()


class RelayLockReverifyTests(unittest.TestCase):
    """P2-2/P3-4：relay acquire_lock rename-steal 复验钉测。

    模拟竞争：A 读到 stale → 在 A rename 之前，B 已偷走 stale 并重建新鲜锁；
    A 的 rename 偷到的是 B 的新鲜锁 → 复验必须恢复 B 的锁并 SKIP，绝双持有者。
    """

    def _lock_env(self):
        td = tempfile.TemporaryDirectory()
        self.addCleanup(td.cleanup)
        lock_dir = Path(td.name) / "autopilot-locks"
        lock_dir.mkdir()
        return td, lock_dir

    def test_v2_never_steals_fresh_rebuild(self):
        import json as _json
        from datetime import datetime, timedelta, timezone
        td, lock_dir = self._lock_env()
        lock_json = lock_dir / "lock.json"
        old_at = (datetime.now(timezone.utc) - timedelta(seconds=400)).isoformat()
        lock_json.write_text(_json.dumps({"token": "OLD", "at": old_at}),
                             encoding="utf-8")
        real_rename = ra.os.rename
        state = {"swapped": False}

        def swapping_rename(src, dst):
            if str(src) == str(lock_json) and not state["swapped"]:
                state["swapped"] = True
                lock_json.unlink()
                lock_json.write_text(_json.dumps(
                    {"token": "B", "at": datetime.now(timezone.utc).isoformat()}),
                    encoding="utf-8")
            return real_rename(src, dst)

        with mock.patch.object(ra, "LOCK_DIR", str(lock_dir)), \
             mock.patch.object(ra.os, "rename", side_effect=swapping_rename):
            token = ra.acquire_lock()
        self.assertIsNone(token, "偷到新鲜锁必须 SKIP")
        info = _json.loads(lock_json.read_text(encoding="utf-8"))
        self.assertEqual(info["token"], "B", "活跃持有者的锁必须原样保留")
        leftovers = [p for p in lock_dir.glob("lock.stolen-*")]
        self.assertEqual(leftovers, [])

    def test_v3_fresh_empty_claim_not_stolen(self):
        """P3-2：O_EXCL 后尚未 flush 的新鲜空锁 = 认领进行中，绝不接管。"""
        td, lock_dir = self._lock_env()
        lock_json = lock_dir / "lock.json"
        lock_json.write_bytes(b"")  # 新鲜空壳
        with mock.patch.object(ra, "LOCK_DIR", str(lock_dir)):
            token = ra.acquire_lock()
        self.assertIsNone(token)
        self.assertEqual(lock_json.stat().st_size, 0, "新鲜空锁不得被删除/覆盖")

    def test_v4_stale_takeover_still_works(self):
        """正向钉：真 stale 锁的接管路径不因复验而失效。"""
        import json as _json
        from datetime import datetime, timedelta, timezone
        td, lock_dir = self._lock_env()
        lock_json = lock_dir / "lock.json"
        old_at = (datetime.now(timezone.utc) - timedelta(seconds=400)).isoformat()
        lock_json.write_text(_json.dumps({"token": "OLD", "at": old_at}),
                             encoding="utf-8")
        with mock.patch.object(ra, "LOCK_DIR", str(lock_dir)):
            token = ra.acquire_lock()
        self.assertIsNotNone(token)
        info = _json.loads(lock_json.read_text(encoding="utf-8"))
        self.assertEqual(info["token"], token)


class DriveLeaseGateFailClosedTests(unittest.TestCase):
    """P1-4：cmd_drive lease 门异常必须 fail-closed（旧 catch-and-skip 已消除）。"""

    def test_d1_gate_error_returns_2_without_lock(self):
        args = argparse.Namespace(watch=False, mode_review="PASS", max_reworks=8,
                                  interval=0.0, max_wait=0.0)
        boom = mock.MagicMock(side_effect=RuntimeError("state corrupted"))
        # acquire_lock 若被触达即响亮失败（不得在门坏后继续执行）
        with mock.patch.object(ra, "_WIRING_AVAILABLE", True), \
             mock.patch.multiple(ra.controller_lease,
                                 load_lease=boom,
                                 check_execute_right=mock.MagicMock(),
                                 renew=mock.MagicMock()), \
             mock.patch.object(ra, "acquire_lock",
                               side_effect=AssertionError("must not reach acquire_lock")), \
             mock.patch.object(ra, "ledger", return_value=None):
            rc = ra.cmd_drive(args)
        self.assertEqual(rc, 2)
        self.assertEqual(boom.call_count, 1)


if __name__ == "__main__":
    unittest.main()
