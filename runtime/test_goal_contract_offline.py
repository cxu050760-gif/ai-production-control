#!/usr/bin/env python3
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import goal_contract_lite as gc


class FakeRuntime:
    EXIT_OK = 0
    EXIT_DENIED = 5
    EXIT_HARD_BLOCKED = 6
    ROUTER_MODE = "router-v0.1"

    def __init__(self, root: Path):
        self.root = root
        self.journal_events = []
        self.saved = []
        self.sent = []

    def run_dir(self, rid):
        p = self.root / "runs" / rid
        p.mkdir(parents=True, exist_ok=True)
        return p

    def atomic_write_text(self, path, text):
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        Path(path).write_text(text, encoding="utf-8")

    def save_state(self, state):
        state["revision"] = int(state.get("revision", 0)) + 1
        self.saved.append(json.loads(json.dumps(state)))
        self.atomic_write_text(self.run_dir(state["run_id"]) / "state.json", json.dumps(state))

    def journal(self, rid, event, **kw):
        self.journal_events.append((event, kw))

    def load_state(self, rid):
        return json.loads((self.run_dir(rid) / "state.json").read_text())

    def hard_block(self, state, reason):
        state["status"] = "HARD_BLOCKED"
        state["blocked_reason"] = reason
        self.save_state(state)

    def emit(self, obj):
        self.last_emit = obj


def base_state():
    return {
        "run_id": "RUN-20260823-223000-abcd",
        "revision": 0,
        "goal": "Build X",
        "status": "RUNNING",
        "last_r_verdict": None,
        "last_r_next_action": "",
        "last_reply_path": None,
        "last_reply_bytes": 0,
        "last_action_fingerprint": None,
        "current_step": "start",
        "next_action": "go",
        "mode": "router-v0.1",
        "router": {"phase": "SEND_GOAL_TO_BUILDER", "round": 0,
                   "last_builder_reply_path": None, "last_builder_reply_bytes": 0,
                   "last_review_reply_path": None, "pending_rework": ""},
    }


class GoalContractLiteTests(unittest.TestCase):
    def setUp(self):
        self.td = tempfile.TemporaryDirectory()
        self.root = Path(self.td.name)
        self.rt = FakeRuntime(self.root)

    def tearDown(self):
        self.td.cleanup()

    def bind(self, state=None):
        state = state or base_state()
        c = gc.build_contract("Build X", ["A", "B"], ["C"], revision=1)
        gc.persist_contract(self.rt, state, c, event="GOAL_CONTRACT_CREATED")
        return state, c

    def test_c1_contract_freezes_goal_acceptance_constraints(self):
        c = gc.build_contract("\nBuild   X\n", ["  A  ", "B"], [" C "])
        self.assertEqual(c["goal"], "Build   X")
        self.assertEqual(c["acceptance_criteria"], ["A", "B"])
        self.assertEqual(c["constraints"], ["C"])

    def test_c2_same_content_has_stable_identity(self):
        a = gc.build_contract("Build X", ["A"], ["C"])
        b = gc.build_contract("\r\nBuild X\r\n", [" A "], [" C "], revision=9)
        self.assertEqual(a["contract_hash"], b["contract_hash"])

    def test_c3_state_journal_and_contract_file_binding(self):
        state, c = self.bind()
        self.assertEqual(state["goal_contract_hash"], c["contract_hash"])
        self.assertTrue(Path(state["goal_contract_path"]).is_file())
        self.assertEqual(self.rt.journal_events[-1][0], "GOAL_CONTRACT_CREATED")
        self.assertEqual(self.rt.journal_events[-1][1]["goal_contract_hash"], c["contract_hash"])

    def test_c7_missing_contract_fails_closed_validation(self):
        with self.assertRaises(gc.GoalContractError):
            gc.require_contract(self.rt, base_state())

    def test_c8_tampered_state_hash_fails_closed(self):
        state, _ = self.bind()
        state["goal_contract_hash"] = "0" * 64
        with self.assertRaises(gc.GoalContractError):
            gc.require_contract(self.rt, state)

    def test_c9_cross_process_style_reload_keeps_same_identity(self):
        state, c = self.bind()
        reloaded = self.rt.load_state(state["run_id"])
        self.assertEqual(gc.require_contract(self.rt, reloaded)["contract_hash"], c["contract_hash"])

    def test_builder_reply_requires_exact_contract_hash(self):
        c = gc.build_contract("Build X", ["A"], [])
        gc._assert_reply_binding(f"ok\nGOAL_CONTRACT_HASH={c['contract_hash']}\n", c["contract_hash"], required=True, actor="builder")
        with self.assertRaises(gc.GoalContractError):
            gc._assert_reply_binding("no marker", c["contract_hash"], required=True, actor="builder")
        with self.assertRaises(gc.GoalContractError):
            gc._assert_reply_binding("GOAL_CONTRACT_HASH=" + "f" * 64, c["contract_hash"], required=True, actor="builder")

    def test_review_binding_contains_same_identity_and_contract(self):
        _, c = self.bind()
        text = gc._binding_block(c)
        self.assertIn("GOAL_CONTRACT_HASH=" + c["contract_hash"], text)
        self.assertIn("ACCEPTANCE_CRITERIA", text)
        self.assertIn("CONSTRAINTS", text)

    def test_c6_same_content_is_not_a_new_identity(self):
        a = gc.build_contract("Build X", ["A"], ["C"], revision=1)
        b = gc.build_contract("Build X", ["A"], ["C"], revision=2)
        self.assertEqual(a["contract_hash"], b["contract_hash"])

    def test_changed_goal_acceptance_or_constraints_changes_identity(self):
        base = gc.build_contract("Build X", ["A"], ["C"])
        self.assertNotEqual(base["contract_hash"], gc.build_contract("Build Y", ["A"], ["C"])["contract_hash"])
        self.assertNotEqual(base["contract_hash"], gc.build_contract("Build X", ["B"], ["C"])["contract_hash"])
        self.assertNotEqual(base["contract_hash"], gc.build_contract("Build X", ["A"], ["D"])["contract_hash"])

    def test_contract_input_parser_supports_repeat_and_files(self):
        af = self.root / "acceptance.txt"; af.write_text("A\nB\n", encoding="utf-8")
        cf = self.root / "constraints.json"; cf.write_text('["C","D"]', encoding="utf-8")
        cleaned, opts = gc._extract_contract_options([
            "router-run", "--goal-file", "g.txt", "--acceptance", "A0",
            "--acceptance-file", str(af), "--constraints-file", str(cf),
        ])
        self.assertEqual(cleaned, ["router-run", "--goal-file", "g.txt"])
        self.assertEqual(opts["acceptance"], ["A0", "A", "B"])
        self.assertEqual(opts["constraints"], ["C", "D"])

    def test_persistent_contract_file_tamper_is_detected(self):
        state, _ = self.bind()
        Path(state["goal_contract_path"]).write_text("{}", encoding="utf-8")
        with self.assertRaises(gc.GoalContractError):
            gc.require_contract(self.rt, state)


RUNTIME = HERE / "runtime.py"
ADAPTER = HERE / "goal_contract_lite.py"
PYTHON = sys.executable
B1 = "https://chatgpt.com/c/b0b0aaaa-1111-2222-3333-000000000001"
R1 = "https://chatgpt.com/c/1e1ebbbb-1111-2222-3333-000000000002"


def _msys(p: Path) -> str:
    s = str(p).replace("\\", "/")
    return "/" + s[0].lower() + s[2:] if len(s) > 1 and s[1] == ":" else s


def _ready_wrapper(root: Path) -> str:
    p = root / "ready.sh"
    p.write_text(
        "#!/bin/bash\ncase \"$1\" in status) echo 'Bridge: READY'; echo 'Browser: chrome'; "
        "echo 'Instance: deadbeef'; echo 'Upload: READY'; exit 0;; *) exit 2;; esac\n",
        encoding="utf-8",
    )
    return _msys(p)


def _script_env(root: Path, conversations: dict) -> tuple[dict, Path]:
    log = root / "transport.jsonl"
    cfg = root / "script.json"
    cfg.write_text(json.dumps({"conversations": conversations, "log": str(log)}), encoding="utf-8")
    env = dict(os.environ)
    env["APC_RUNTIME_STATE_ROOT"] = str(root / "state")
    env["APC_RUNTIME_BRIDGE_WRAPPER"] = _ready_wrapper(root)
    env["APC_RUNTIME_INJECT_BRIDGE_FAIL"] = "SCRIPT"
    env["APC_RUNTIME_INJECT_SCRIPT_FILE"] = str(cfg)
    env.pop("PYTHONIOENCODING", None)
    return env, log


def _run_json(script: Path, argv: list[str], env: dict) -> tuple[int, dict, str]:
    proc = __import__("subprocess").run(
        [PYTHON, str(script), *argv], capture_output=True, text=True,
        encoding="utf-8", errors="replace", env=env, timeout=180,
    )
    try:
        out = json.loads(proc.stdout)
    except ValueError:
        out = {"_raw": proc.stdout}
    return proc.returncode, out, proc.stdout + proc.stderr


@unittest.skipUnless(RUNTIME.exists(), "real runtime.py unavailable in Builder sandbox")
class GoalContractRuntimeIntegrationTests(unittest.TestCase):
    def setUp(self):
        self.td = tempfile.TemporaryDirectory()
        self.root = Path(self.td.name)

    def tearDown(self):
        self.td.cleanup()

    def test_c4_c5_router_b_r_rework_same_contract_identity(self):
        goal = self.root / "goal.txt"
        goal.write_text("Build a header.\nKeep scope minimal.", encoding="utf-8")
        contract = gc.build_contract(goal.read_text(), ["Header is correct"], ["No scope expansion"])
        h = contract["contract_hash"]
        convs = {
            B1: {"sid": "bsid-contract", "replies": [
                f"candidate v1\nGOAL_CONTRACT_HASH={h}",
                f"candidate v2 fixed\nGOAL_CONTRACT_HASH={h}",
            ]},
            R1: {"sid": "rsid-contract", "replies": [
                "===REVIEW_VERDICT=== REWORK\n===NEXT_ACTION=== Fix header.",
                "===REVIEW_VERDICT=== PASS",
            ]},
        }
        env, log = _script_env(self.root, convs)
        code, out, raw = _run_json(ADAPTER, [
            "router-run", "--goal-file", str(goal), "--b-url", B1, "--r-url", R1,
            "--acceptance", "Header is correct", "--constraint", "No scope expansion",
            "--max-rounds", "2", "--timeout", "30",
        ], env)
        self.assertEqual(code, 0, raw[-1000:])
        self.assertEqual(out.get("status"), "ROUTED_PASS", raw[-1000:])
        state_path = Path(out["state_path"])
        state = json.loads(state_path.read_text(encoding="utf-8"))
        self.assertEqual(state["goal_contract_hash"], h)
        self.assertEqual(state["goal_contract_revision"], 1)
        self.assertEqual(state["status"], "DONE")
        events = [json.loads(line) for line in (state_path.parent / "journal.jsonl").read_text(encoding="utf-8").splitlines()]
        self.assertTrue(any(e.get("event") == "GOAL_CONTRACT_CREATED" and e.get("goal_contract_hash") == h for e in events))
        messages = [json.loads(line)["message"] for line in log.read_text(encoding="utf-8").splitlines()]
        self.assertEqual(len(messages), 4)
        self.assertTrue(all(f"GOAL_CONTRACT_HASH={h}" in message for message in messages))
        self.assertIn("Header is correct", messages[0])
        self.assertIn("No scope expansion", messages[0])
        self.assertIn("REWORK", messages[2])

    def test_c7_legacy_run_without_contract_is_hard_blocked_by_official_adapter(self):
        env = dict(os.environ)
        env["APC_RUNTIME_STATE_ROOT"] = str(self.root / "state")
        code, out, raw = _run_json(RUNTIME, ["start", "--goal", "legacy goal", "--r-url", R1], env)
        self.assertEqual(code, 0, raw)
        rid = out["run_id"]
        code, blocked, raw = _run_json(ADAPTER, [
            "step", "--run-id", rid, "--current", "x", "--next", "y",
        ], env)
        self.assertEqual(code, 6, raw)
        self.assertEqual(blocked.get("status"), "HARD_BLOCKED")
        state = json.loads((Path(env["APC_RUNTIME_STATE_ROOT"]) / "runs" / rid / "state.json").read_text())
        self.assertEqual(state["status"], "HARD_BLOCKED")
        self.assertIn("GOAL_CONTRACT_BLOCKED", state.get("blocked_reason", ""))

    def test_c8_builder_candidate_hash_mismatch_is_hard_blocked(self):
        goal = self.root / "goal.txt"; goal.write_text("Build X", encoding="utf-8")
        convs = {
            B1: {"sid": "bsid-bad", "replies": [f"candidate\nGOAL_CONTRACT_HASH={'f'*64}"]},
            R1: {"sid": "rsid-unused", "replies": ["===REVIEW_VERDICT=== PASS"]},
        }
        env, _ = _script_env(self.root, convs)
        code, out, raw = _run_json(ADAPTER, [
            "router-run", "--goal-file", str(goal), "--b-url", B1, "--r-url", R1,
            "--acceptance", "A", "--max-rounds", "1", "--timeout", "30",
        ], env)
        self.assertEqual(code, 6, raw[-1000:])
        self.assertEqual(out.get("status"), "HARD_BLOCKED")
        state = json.loads((Path(env["APC_RUNTIME_STATE_ROOT"]) / "runs" / out["run_id"] / "state.json").read_text())
        self.assertIn("Goal Contract identity mismatch", state.get("blocked_reason", ""))

    def test_c6_explicit_contract_revision_changes_hash_and_invalidates_old_review(self):
        goal = self.root / "goal.txt"; goal.write_text("Build X", encoding="utf-8")
        env = dict(os.environ)
        env["APC_RUNTIME_STATE_ROOT"] = str(self.root / "state")
        code, out, raw = _run_json(ADAPTER, [
            "router-start", "--goal-file", str(goal), "--b-url", B1, "--r-url", R1,
            "--acceptance", "A",
        ], env)
        self.assertEqual(code, 0, raw)
        rid = out["run_id"]
        state_path = Path(env["APC_RUNTIME_STATE_ROOT"]) / "runs" / rid / "state.json"
        before = json.loads(state_path.read_text())
        old_hash = before["goal_contract_hash"]
        code, revised, raw = _run_json(ADAPTER, [
            "contract-revise", "--run-id", rid, "--acceptance", "A2",
            "--note", "explicit user acceptance change",
        ], env)
        self.assertEqual(code, 0, raw)
        self.assertEqual(revised["goal_contract_revision"], 2)
        self.assertNotEqual(revised["goal_contract_hash"], old_hash)
        after = json.loads(state_path.read_text())
        self.assertEqual(after["router"]["phase"], "SEND_GOAL_TO_BUILDER")
        self.assertIsNone(after["last_r_verdict"])
        self.assertTrue((state_path.parent / "goal_contract_v0001.json").is_file())
        self.assertTrue((state_path.parent / "goal_contract_v0002.json").is_file())

    def test_c6_change_scope_cannot_bypass_contract_revision(self):
        env = dict(os.environ)
        env["APC_RUNTIME_STATE_ROOT"] = str(self.root / "state")
        code, out, raw = _run_json(ADAPTER, [
            "start", "--goal", "G", "--r-url", R1,
            "--acceptance", "A", "--constraint", "C",
        ], env)
        self.assertEqual(code, 0, raw)
        rid = out["run_id"]
        state_path = Path(env["APC_RUNTIME_STATE_ROOT"]) / "runs" / rid / "state.json"
        before = json.loads(state_path.read_text(encoding="utf-8"))
        code, out, raw = _run_json(ADAPTER, [
            "directive", "--run-id", rid, "CHANGE_SCOPE", "--note", "secret constraint change",
        ], env)
        self.assertEqual(code, 5, raw)
        self.assertEqual(out["status"], "DENIED")
        after = json.loads(state_path.read_text(encoding="utf-8"))
        self.assertEqual(after["goal_contract_hash"], before["goal_contract_hash"])
        self.assertEqual(after["goal_contract_revision"], 1)

    def test_c7_router_continue_guard_blocks_missing_contract(self):
        goal = self.root / "goal.txt"; goal.write_text("Build X", encoding="utf-8")
        env, _ = _script_env(self.root, {B1: {"sid": "b", "replies": ["x"]}, R1: {"sid": "r", "replies": ["y"]}})
        code, out, raw = _run_json(ADAPTER, [
            "router-start", "--goal-file", str(goal), "--b-url", B1, "--r-url", R1, "--acceptance", "A",
        ], env)
        self.assertEqual(code, 0, raw)
        rid = out["run_id"]
        state_path = Path(env["APC_RUNTIME_STATE_ROOT"]) / "runs" / rid / "state.json"
        state = json.loads(state_path.read_text(encoding="utf-8"))
        state.pop("goal_contract", None)  # corrupt: contract missing from RUN state
        state_path.write_text(json.dumps(state), encoding="utf-8")
        code, out, raw = _run_json(ADAPTER, ["router-continue", "--run-id", rid], env)
        self.assertEqual(code, 6, raw[-500:])
        self.assertEqual(out.get("status"), "HARD_BLOCKED")

    def test_c7_router_continue_drives_same_contract_identity(self):
        goal = self.root / "goal.txt"; goal.write_text("Build a header.", encoding="utf-8")
        h = gc.build_contract(goal.read_text(), ["Header is correct"])["contract_hash"]
        convs = {
            B1: {"sid": "bsid-rc", "replies": [f"candidate v1\nGOAL_CONTRACT_HASH={h}"]},
            R1: {"sid": "rsid-rc", "replies": ["===REVIEW_VERDICT=== PASS"]},
        }
        env, log = _script_env(self.root, convs)
        code, out, raw = _run_json(ADAPTER, [
            "router-start", "--goal-file", str(goal), "--b-url", B1, "--r-url", R1, "--acceptance", "Header is correct",
        ], env)
        self.assertEqual(code, 0, raw)
        rid = out["run_id"]
        code, out, raw = _run_json(ADAPTER, ["router-continue", "--run-id", rid, "--timeout", "30"], env)
        self.assertEqual(code, 0, raw[-1000:])
        self.assertEqual(out.get("status"), "ROUTED_PASS", raw[-1000:])
        state = json.loads(Path(out["state_path"]).read_text(encoding="utf-8"))
        self.assertEqual(state["goal_contract_hash"], h)
        self.assertEqual(state["status"], "DONE")


if __name__ == "__main__":
    unittest.main(verbosity=2)
