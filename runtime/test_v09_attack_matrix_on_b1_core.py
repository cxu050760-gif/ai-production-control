#!/usr/bin/env python3
"""V0.9 attack matrix re-measurement on the v0.9-b1 authority/effect core (CLOSE line).

Measurement-side adaptation only. All 36 case bodies, IDs, mutations and expected
outcomes are imported UNMODIFIED from ``runtime/test_v09_attack_matrix_offline.py``
(the frozen b2 publication, byte-identical to ``b2@f74d48e``). This file changes no
attack mutation; it adapts the harness to b1's actual core semantics.

Frozen originals are never edited: the V0.9 CLOSE build spec forbids it
(V09_CLOSE_BUILD_SPEC.md §0.2, §4.2) and the b1 runner is a T0 deliverable
(V09_CLOSE_BUILD_SPEC.md T0 item b).

Adaptation declaration (each item cites its authorising clause)
---------------------------------------------------------------
AD-1  ``Fixture.authorization``
      b1's ``Controller.scoped_authorization`` never mints authority ("Controller
      self-grant is forbidden", controller.py:318) -- the permanent constraint
      recorded in V09_CLOSE_BUILD_SPEC.md §3 (D 类, R13). The harness therefore
      issues authorizations through the external-authority path
      ``store.issue_decision_nonce`` -> ``store.grant_authorization``, i.e. the
      harness plays the user's controlled entry (V14-FROZEN Human Gate Trust Root).
      Pattern is identical to b1's own tests/test_v09_authority_store.py.

AD-2  ``Fixture.intent``
      b1's ``execute_effect`` requires explicit ``effect_type`` and
      ``data_classification`` intent fields (controller.py:338-343); the v0.8
      fixture assumed them implicitly. The adapter supplies AI_MESSAGE / PUBLIC.

AD-3  Authorization resource binding
      Granted with ``resource="resource-a"`` to match the default intent resource
      (v0.8 ``scoped_authorization`` passed resource=destination internally).

AD-4  Restart simulation (required by V09_CLOSE_BUILD_SPEC.md T6 / CASE_ID V09-R21)
      "不同 Controller 实例（重启/恢复后的进程）" is realised by closing the
      fixture's Controller and constructing a NEW ``Controller`` over the SAME
      state root / config, which yields a new ``controller_instance_id`` and
      ``process_start_identity``. No product code is involved; this is the
      measurement-side realisation of the T6 IMPLEMENTATION_BOUNDARY judgement
      "请求方实例 ≠ 记录实例" and of V14-FROZEN §27A process/generation semantics.
      The recovered instance then re-authorizes through the AD-1 external
      controlled entry before replaying the same logical effect: the surviving
      authorization row is identity-bound to the previous controller instance,
      so replaying with it measures the identity precheck rather than the dedup
      branch under test. Re-authorization is also the shape T6 itself sanctions
      ("实际重试只在 TASK-3 对账完成后以新显式授权进行"). The replayed intent is
      byte-identical to the frozen R21 body, so the logical effect identity --
      and therefore the dedup hit -- is unchanged.

AD-5  R18 adjudicated expectation override (BUILDER_RULING_R18.md §3)
      R18 expectation is revised by adjudication, not by construction: gate code
      is unchanged. Quoting R18_SEMANTIC_ANALYSIS.md §5 verbatim:

        "裁决：采用解读 B —— slot 是身份组成，不是唯一性容器。"
        "语义定性：同 slot、不同 payload = 两个不同的逻辑效果
        （不同 effect_intent_hash ⇒ 不同 logical_effect_id，依据〔F4〕），
        各自经完整闸门链（授权、配额、scope、WAL）独立通过后合法执行，可以共存。"
        "矩阵原期望 `CONFLICT_OR_DENY` 为规范不支持的单方面解读，予以**修订**；
        修订以裁决记录绑定规范 SHA，属裁决收口，不是静默改动，也不是"收绿"。"
        "处置：R18 以"**期望修订 + 裁决记录**"收口，**不施工**（闸门代码零改动）。"

      Adjudicated expectation = ALLOW_DISTINCT_EFFECT. Match criteria (per ruling
      §3, deliberately stronger than "ALLOW happened to be observed"):
        observed ALLOW  AND  external_effect_count == 2
        AND the two executions carry two DISTINCT logical_effect_id
        AND both are independent reservations (neither is a dedup hit).
      The identity assertions are made by querying the fixture's ``actions`` table
      from this measurement-side file; the frozen fixture and frozen runner stay
      byte-unchanged apart from the T0-authorised ``spec_anchor`` metadata field.

Faithful probe (carried over from the b1 re-measurement, V09_CLOSE_BUILD_SPEC.md
§2 CASE V09-R34 and 用户裁决 4): R34 is additionally exercised with the unknown
effect_type on BOTH the authorization and the intent, because the plain matrix
pass measures a type *mismatch* rather than the unknown-type attack.
"""
from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict
from pathlib import Path

RUNTIME_DIR = Path(__file__).resolve().parent
ROOT = RUNTIME_DIR.parent
for _p in (str(ROOT / "src"), str(RUNTIME_DIR)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import test_v09_attack_matrix_offline as mx  # noqa: E402

from aicontrol.controller import Controller  # noqa: E402

PROTOCOL = "V09_ATTACK_RESULT_JSONL_1"
CORE_UNDER_TEST = "v0.9-b1/authority-effect-core"

ADAPTATION_NOTES = {
    "AD-1": "authorization issued via external authority (decision nonce + grant), not Controller self-grant",
    "AD-2": "intent carries explicit effect_type/data_classification required by b1 execute_effect",
    "AD-3": "authorization resource bound to intent resource (resource-a), not destination",
    "AD-4": "restart simulated by a NEW Controller instance over the same state root (V09-R21)",
    "AD-5": "R18 expectation revised by adjudication to ALLOW_DISTINCT_EFFECT with identity assertions",
}

R18_ADJUDICATED_EXPECTATION = "ALLOW_DISTINCT_EFFECT"

_orig_intent = mx.Fixture.intent


def patched_authorization(
    self,
    *,
    provider: str = "provider-a",
    destination: str = "destination-a",
    purpose: str = "v09-test",
    effect_type: str = "AI_MESSAGE",
    max_effect_count: int = 3,
):
    """AD-1 + AD-3: mint authority through the external controlled-entry path."""
    resource = "resource-a"
    identity = self.controller.controller_instance_id
    scope = {
        "provider": provider,
        "destination": destination,
        "resource": resource,
        "purpose": purpose,
        "effect_type": effect_type,
        "data_classes": ["PUBLIC"],
        "identity": identity,
    }
    nonce = self.controller.store.issue_decision_nonce(
        self.task_id, scope, user_decision_reference="external-authority:v09-close"
    )
    return self.controller.store.grant_authorization(
        self.task_id,
        nonce["decision_nonce"],
        scope,
        provider=provider,
        resource=resource,
        purpose=purpose,
        effect_type=effect_type,
        max_effect_count=max_effect_count,
    )


def patched_intent(self, *, effect_type: str = "AI_MESSAGE", data_classification: str = "PUBLIC", **kwargs):
    """AD-2: b1 execute_effect requires these intent fields explicitly."""
    intent = _orig_intent(self, **kwargs)
    intent["effect_type"] = effect_type
    intent["data_classification"] = data_classification
    return intent


mx.Fixture.authorization = patched_authorization
mx.Fixture.intent = patched_intent


def restart_fixture(fx):
    """AD-4: give the fixture a brand new Controller instance over the same state root."""
    fx.controller.close()
    fx.controller = Controller(fx.config_path)
    fx.lease = fx.controller.acquire_lease()
    return fx


def r21_restarted_case(case):
    """V09-R21 measured across a restart (AD-4), not in the same live instance."""
    fx = mx.Fixture()
    try:
        auth2, reservation, reality = mx._crown_unknown(fx, slot="crown-r21")
        restart_fixture(fx)
        replay_auth = fx.authorization(max_effect_count=4)
        replay = fx.execute(
            auth=replay_auth,
            intent=fx.intent(slot="crown-r21"),
            adapter=reality.succeed,
            resource_id="crown-r21-restart",
        )
        observed = (
            "RECONCILE_FIRST"
            if (replay.get("reconciliation_required") is True and reality.real_effect_count == 1)
            else "DEDUPLICATED_WITHOUT_RECONCILE"
        )
        return mx._obs(
            case,
            observed,
            external_effect_count=reality.real_effect_count,
            final_effect_status=fx.action_status(reservation),
            reconciliation_result="REQUIRED",
            authorization_identity=replay_auth["authorization_id"],
            detail="AD-4: replay issued by a new Controller instance over the same state root",
        )
    finally:
        fx.close()


def r18_adjudicated_case(case):
    """AD-5: R18 scored against the adjudicated expectation with identity proofs."""
    case = dict(case)
    case["expected_outcome"] = R18_ADJUDICATED_EXPECTATION
    fx = mx.Fixture()
    try:
        auth = fx.authorization(max_effect_count=4)
        reality = mx.CountedExternalReality()
        fx.execute(
            auth=auth,
            intent=fx.intent(slot="same-slot-diff", payload="payload-one"),
            adapter=reality.succeed,
            resource_id="conflict-r1",
        )
        try:
            fx.execute(
                auth=auth,
                intent=fx.intent(slot="same-slot-diff", payload="payload-two"),
                adapter=reality.succeed,
                resource_id="conflict-r2",
            )
        except mx.GateDenied as exc:
            return mx._obs(case, "CONFLICT_OR_DENY", external_effect_count=reality.real_effect_count, detail=str(exc))
        rows = fx.controller.store.connection.execute(
            "SELECT logical_effect_id, logical_effect_slot, attempt_id, effect_intent_hash,"
            " COUNT(*) OVER (PARTITION BY logical_effect_id) AS copies"
            " FROM actions WHERE task_id=?",
            (fx.task_id,),
        ).fetchall()
        distinct_ids = {row["logical_effect_id"] for row in rows}
        same_slot = {row["logical_effect_slot"] for row in rows}
        distinct_hashes = {row["effect_intent_hash"] for row in rows}
        independent = len(rows) == 2 and all(row["copies"] == 1 for row in rows)
        ok = (
            reality.real_effect_count == 2
            and len(distinct_ids) == 2
            and len(distinct_hashes) == 2
            and len(same_slot) == 1
            and independent
        )
        return mx._obs(
            case,
            "ALLOW_DISTINCT_EFFECT" if ok else "ALLOW_NOT_DISTINCT",
            external_effect_count=reality.real_effect_count,
            detail=(
                f"AD-5 identity proof: slots={sorted(same_slot)} "
                f"logical_effect_ids={len(distinct_ids)} intent_hashes={len(distinct_hashes)} "
                f"action_rows={len(rows)} independent_reservations={independent}"
            ),
        )
    finally:
        fx.close()


def r34_faithful_probe():
    """R34 with the unknown effect_type on BOTH authorization and intent."""
    fx = mx.Fixture()
    try:
        weird_auth = fx.authorization(effect_type="TOTALLY_UNKNOWN_EFFECT_TYPE", max_effect_count=1)
        reality = mx.CountedExternalReality()
        try:
            fx.execute(
                auth=weird_auth,
                intent=fx.intent(slot="unknown-effect-type", effect_type="TOTALLY_UNKNOWN_EFFECT_TYPE"),
                adapter=reality.succeed,
            )
        except Exception as exc:
            return {
                "test_id": "V09-R34-FAITHFUL",
                "expected_outcome": "FAIL_CLOSED",
                "observed_outcome": "FAIL_CLOSED",
                "external_effect_count": reality.real_effect_count,
                "matched": True,
                "detail": f"{type(exc).__name__}: {exc}",
            }
        return {
            "test_id": "V09-R34-FAITHFUL",
            "expected_outcome": "FAIL_CLOSED",
            "observed_outcome": "ALLOW",
            "external_effect_count": reality.real_effect_count,
            "matched": False,
            "detail": "unknown effect_type accepted end-to-end",
        }
    finally:
        fx.close()


CASE_OVERRIDES = {
    "V09-R18": r18_adjudicated_case,
    "V09-R21": r21_restarted_case,
}


def run_matrix():
    matrix = mx.load_matrix()
    spec_anchor = matrix.get("spec_anchor")
    results = []
    for case in matrix["cases"]:
        runner = CASE_OVERRIDES.get(case["id"])
        try:
            if runner is not None:
                obs = runner(case)
            else:
                obs = mx.run_case(case)
            entry = asdict(obs) | {"matched": obs.matched, "harness": "ok", "adaptation": runner is not None}
        except Exception as exc:
            entry = {
                "test_id": case["id"],
                "owner_case": case["owner_case"],
                "expected_outcome": R18_ADJUDICATED_EXPECTATION if case["id"] == "V09-R18" else case["expected_outcome"],
                "observed_outcome": "HARNESS_ERROR",
                "detail": f"{type(exc).__name__}: {exc}",
                "matched": False,
                "harness": "error",
                "adaptation": case["id"] in CASE_OVERRIDES,
            }
        results.append(entry)
    return matrix, spec_anchor, results


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--jsonl", help="write per-case V09_ATTACK_RESULT_JSONL_1 records here")
    parser.add_argument("--candidate", default="UNCOMMITTED", help="candidate SHA bound into evidence")
    args = parser.parse_args(argv)

    matrix, spec_anchor, results = run_matrix()
    extra = r34_faithful_probe()
    matched = sum(1 for r in results if r["matched"])
    summary = {
        "protocol": PROTOCOL,
        "core_under_test": CORE_UNDER_TEST,
        "candidate_sha": args.candidate,
        "spec_anchor": spec_anchor,
        "matrix_source": "runtime/fixtures/v09_authority_effect_attack_cases.json (frozen b2原件 + T0 spec_anchor)",
        "runner_source": "runtime/test_v09_attack_matrix_offline.py (case bodies unmodified; AD-1..AD-5)",
        "adaptations": ADAPTATION_NOTES,
        "case_count": len(results),
        "matched": matched,
        "red": len(results) - matched,
    }
    if args.jsonl:
        out = Path(args.jsonl)
        out.parent.mkdir(parents=True, exist_ok=True)
        lines = [json.dumps({"protocol": PROTOCOL, **summary}, sort_keys=True)]
        lines += [
            json.dumps({"protocol": PROTOCOL, "candidate_sha": args.candidate, "spec_anchor": spec_anchor, **r}, sort_keys=True)
            for r in results
        ]
        lines.append(json.dumps({"protocol": PROTOCOL, "candidate_sha": args.candidate, "spec_anchor": spec_anchor, **extra}, sort_keys=True))
        out.write_text("".join(line + "\n" for line in lines), encoding="utf-8")
    print(json.dumps(summary, indent=1, sort_keys=True))
    for r in results:
        flag = "MATCH " if r["matched"] else "MISMATCH"
        print(f"{r['test_id']:9s} exp={r['expected_outcome']:26s} obs={r['observed_outcome']:28s} {flag} | {str(r.get('detail', ''))[:88]}")
    flag = "MATCH " if extra["matched"] else "MISMATCH"
    print(f"{extra['test_id']:18s} exp={extra['expected_outcome']:12s} obs={extra['observed_outcome']:12s} {flag} | {extra['detail'][:88]}")
    print(f"jsonl={'written to ' + args.jsonl if args.jsonl else 'not requested'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
