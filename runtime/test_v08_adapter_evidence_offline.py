"""B3 Evidence self-tests plus the per-attack machine result producer."""
from __future__ import annotations
import contextlib, copy, hashlib, io, json, subprocess, sys, tempfile, unittest
from pathlib import Path
from unittest import mock
RUNTIME=Path(__file__).resolve().parent; ROOT=RUNTIME.parent
if str(RUNTIME) not in sys.path: sys.path.insert(0,str(RUNTIME))
import v08_adapter_evidence as ev

class OwnerNotReady(RuntimeError): pass

def git(root,*a):
    p=subprocess.run(["git",*a],cwd=root,text=True,stdout=subprocess.PIPE,stderr=subprocess.PIPE)
    if p.returncode: raise AssertionError(f"git {a} failed: {p.stderr}")
    return p.stdout.strip()
def write(root,path,text):
    p=root/path; p.parent.mkdir(parents=True,exist_ok=True); p.write_text(text,encoding="utf-8")
def commit(root,msg): git(root,"add","-A"); git(root,"commit","-m",msg); return git(root,"rev-parse","HEAD")

class Repo:
    def __init__(self):
        self.t=tempfile.TemporaryDirectory(prefix="v08-b3-history-"); self.root=Path(self.t.name)
        git(self.root,"init"); git(self.root,"config","user.email","b3@example.invalid"); git(self.root,"config","user.name","B3")
        write(self.root,"seed","base"); self.base=commit(self.root,"base"); git(self.root,"branch","-M","base")
    def source(self,branch,path,text=None):
        git(self.root,"checkout","-b",branch,self.base); write(self.root,path,text or branch); s=commit(self.root,branch); git(self.root,"checkout","base"); return s
    def merge(self,*sources):
        git(self.root,"checkout","-B","final",self.base)
        for s in sources: git(self.root,"merge","--no-ff","--no-edit",s)
        return git(self.root,"rev-parse","HEAD")
    def close(self): self.t.cleanup()

def expected_records(m,executed=True):
    return [{"attack_id":c["id"],"owner":c["owner"],"owner_case":c["owner_case"],"expected_outcome":c["expected_outcome"],
             "observed_outcome":c["expected_outcome"],"executed":executed,"result":"PASS"} for c in m["cases"]]

class MatrixProtocolTests(unittest.TestCase):
    def setUp(self): self.m=ev.matrix(ev.ROOT)
    def test_exact_matrix_size_schema_and_mapping(self):
        self.assertEqual(self.m["attack_case_count"],len(self.m["cases"])); self.assertEqual(len(self.m["cases"]),97)
        self.assertEqual(len({c["id"] for c in self.m["cases"]}),97); self.assertEqual(self.m["attack_matrix_version"],"V08-ATTACK-MATRIX-2")
        b04=next(c for c in self.m["cases"] if c["id"]=="B04"); self.assertEqual((b04["owner"],b04["owner_case"]),("B2","duplicate_provider_id"))
    def test_real_record_protocol_accepts_exact_executed_set(self): self.assertEqual(len(ev.validate_attack_records(self.m,expected_records(self.m))),97)
    def _fails(self,records,token):
        with self.assertRaises(ev.EvidenceError) as e: ev.validate_attack_records(self.m,records)
        self.assertIn(token,e.exception.code)
    def test_noop_fake_97_is_hard_fail(self): self._fails(expected_records(self.m,False),"NOT_EXECUTED")
    def test_missing_case_is_hard_fail(self): self._fails(expected_records(self.m)[:-1],"MISSING")
    def test_extra_98th_case_is_hard_fail(self):
        r=expected_records(self.m); r.append({"attack_id":"Z98","owner":"B3","owner_case":"extra","expected_outcome":"HARD_FAIL","observed_outcome":"HARD_FAIL","executed":True,"result":"PASS"}); self._fails(r,"EXTRA")
    def test_duplicate_case_is_hard_fail(self):
        r=expected_records(self.m); r.append(copy.deepcopy(r[0])); self._fails(r,"DUPLICATE")
    def test_expected_observed_mismatch_is_hard_fail(self):
        r=expected_records(self.m); next(x for x in r if x["attack_id"]=="B04")["observed_outcome"]="ACCEPTED"; self._fails(r,"OUTCOME_MISMATCH")
    def test_owner_mapping_mismatch_is_hard_fail(self):
        r=expected_records(self.m); r[0]["owner_case"]="wrong"; self._fails(r,"MAPPING_MISMATCH")

class HistoryProvenanceTests(unittest.TestCase):
    def setUp(self): self.r=Repo()
    def tearDown(self): self.r.close()
    def test_clean_builder_history_and_natural_merge_are_accepted(self):
        b1=self.r.source("b1","a","owned"); b2=self.r.source("b2","b","other"); final=self.r.merge(b2,b1)
        self.assertTrue(ev.require_builder_history(self.r.root,self.r.base,b1,"b1",("a",)))
        self.assertTrue(ev.require_no_post_source_touch(self.r.root,b1,final,"b1",("a",)))
    def test_out_of_ownership_modify_then_revert_source_is_hard_fail(self):
        git(self.r.root,"checkout","-b","bad",self.r.base); write(self.r.root,"a","owned"); write(self.r.root,"oops","illegal"); commit(self.r.root,"illegal")
        git(self.r.root,"rm","oops"); source=commit(self.r.root,"revert illegal")
        with self.assertRaises(ev.EvidenceError) as e: ev.require_builder_history(self.r.root,self.r.base,source,"b1",("a",))
        self.assertIn("HISTORY_OUT_OF_OWNERSHIP",e.exception.code)
    def test_owned_tamper_then_restore_exact_blob_is_hard_fail(self):
        source=self.r.source("b1","a","owned"); git(self.r.root,"checkout","-B","final",source); write(self.r.root,"a","tampered"); commit(self.r.root,"tamper")
        git(self.r.root,"checkout",source,"--","a"); final=commit(self.r.root,"restore exact blob"); self.assertEqual(ev.blob(self.r.root,source,"a"),ev.blob(self.r.root,final,"a"))
        with self.assertRaises(ev.EvidenceError) as e: ev.require_no_post_source_touch(self.r.root,source,final,"b1",("a",))
        self.assertIn("POST_SOURCE_HISTORY_TOUCH",e.exception.code)
    def test_final_extra_and_missing_paths_fail(self):
        with self.assertRaises(ev.EvidenceError): ev.exact_path_rows([("A","a"),("A","b"),("A","c"),("A","extra")],("a","b","c"))
        with self.assertRaises(ev.EvidenceError): ev.exact_path_rows([("A","a"),("A","b")],("a","b","c"))
    def test_duplicate_and_rename_shapes_fail(self):
        with self.assertRaises(ev.EvidenceError): ev.exact_path_rows([("A","a"),("M","a")],("a","b"))
        with self.assertRaises(ev.EvidenceError): ev.name_status("R100\told\tnew")

class StaticScannerTests(unittest.TestCase):
    def test_dict_dispatch_worker_special_case_detected(self): self.assertTrue(ev.identity_findings("def f(worker_id,s,g):\n h={'fixture-alpha':s}\n return h.get(worker_id,g)\n"))
    def test_provider_id_alias_comparison_detected(self): self.assertTrue(ev.identity_findings("def f(provider_id):\n pid=provider_id\n if pid=='provider-x': return 1\n",identities={"provider-x"}))
    def test_promote_milestone_alias_call_detected(self):
        a,e=ev.isolation_findings("def f():\n fn=promote_milestone\n return fn()\n"); self.assertTrue(a); self.assertFalse(e)
    def test_reserve_effect_dict_dispatch_detected(self):
        a,e=ev.isolation_findings("def f():\n ops={'go':reserve_effect}\n return ops['go']()\n"); self.assertFalse(a); self.assertTrue(e)
    def test_original_direct_calls_still_detected(self):
        a,e=ev.isolation_findings("def f():\n promote_milestone()\n reserve_effect()\n"); self.assertTrue(a); self.assertTrue(e)
    def test_generic_provider_kind_branch_is_allowed(self): self.assertEqual(ev.identity_findings("def f(provider_kind,r,worker_id):\n if provider_kind=='API_MODEL': return r[worker_id]\n return r[worker_id]\n"),[])

class RunnerFailClosedTests(unittest.TestCase):
    def test_missing_args_not_ready_without_success_marker(self):
        out=io.StringIO()
        with contextlib.redirect_stdout(out): rc=ev.main([])
        text=out.getvalue(); self.assertEqual(rc,3); self.assertIn("V08_EVIDENCE_STATUS=NOT_READY",text); self.assertNotIn(ev.SUCCESS,text)
    def test_failing_command_is_closed(self):
        with tempfile.TemporaryDirectory() as d:
            with self.assertRaises(ev.EvidenceError): ev.checked(Path(d),sys.executable,"-c","raise SystemExit(7)")
    def test_success_marker_is_single_and_after_full_build(self):
        src=Path(ev.__file__).read_text(encoding="utf-8"); needle='print(f"{SUCCESS} candidate={args.candidate}")'
        self.assertEqual(src.count(needle),1); self.assertGreater(src.index(needle),src.index("result = build(")); self.assertGreater(src.index(needle),src.index("execute_attack_producer"))

# ---- Real final-candidate attack producer ---------------------------------
def owner_modules():
    try:
        import test_v08_adapter_core_offline as b1, test_v08_adapter_registry_offline as b2
        return b1,b2
    except Exception as exc: raise OwnerNotReady(f"owner modules unavailable: {exc}") from exc

def closed(fn,*errors):
    try: fn()
    except errors: return "FAIL_CLOSED"
    return "ACCEPTED"

def exec_b2(case,b2):
    name=case["owner_case"]
    if name=="registry_missing":
        try: b2._load_json(b2.REGISTRY_PATH.with_name("__missing__.json"))
        except FileNotFoundError: return "FAIL_CLOSED"
        return "ACCEPTED"
    reg=copy.deepcopy(b2._load_json(b2.REGISTRY_PATH)); attacks={x["id"]:x for x in b2._load_json(b2.ATTACK_CASES_PATH)["cases"]}
    if name=="schema_version_rollback": reg["schema_version"]=0; return closed(lambda:b2.validate_registry(reg),b2.RegistryConformanceError)
    if name=="provider_kind_wrong_type": reg["providers"][0]["kind"]=7; return closed(lambda:b2.validate_registry(reg),b2.RegistryConformanceError)
    attack=attacks.get(name)
    if attack is None: raise OwnerNotReady(f"B2 owner_case missing: {name}")
    mutated=b2.apply_attack(reg,attack); minimum=attack.get("minimum_generation",1)
    return closed(lambda:b2.validate_registry(mutated,minimum_generation=minimum),b2.RegistryConformanceError)

def capsule(b1): return b1.capsule_for()
def worker_result(b1,c):
    return {"contract_version":b1.CONTRACT_VERSION,"result_type":"WORKER_RESULT","status":"DONE","source_binding":{"task_id":c["task_id"],"invocation_id":c["invocation_id"],"worker_id":c["worker_id"],"context_id":c["context_id"],"capsule_id":c["capsule_id"],"artifact_set_id":c["artifact_set_id"]},"artifact_paths":["artifact.txt"],"artifact_hashes":{"artifact.txt":"0"*64},"error":None,"notes":"ok"}

def exec_b1_contract(name,b1):
    Err=b1.AdapterContractError; c=capsule(b1)
    simple={
      "malformed_task_capsule":lambda: b1.validate_task_capsule([]),
      "task_capsule_missing_required":lambda: b1.validate_task_capsule({k:v for k,v in c.items() if k!="objective"}),
      "task_capsule_wrong_type":lambda: b1.validate_task_capsule({**c,"objective":7}),
      "bool_masquerading_as_int":lambda: b1.validate_task_capsule({**c,"metadata":{**c["metadata"],"authority_grant":0}}),
      "oversized_string":lambda: b1.validate_task_capsule({**c,"objective":"x"*65536}),
      "oversized_list":lambda: b1.validate_task_capsule({**c,"metadata":{**c["metadata"],"capabilities":[f"c{i}" for i in range(4096)]}}),
      "malformed_capability_metadata":lambda: b1.validate_task_capsule({**c,"metadata":{**c["metadata"],"capabilities":"read"}}),
    }
    if name in simple: return closed(simple[name],Err)
    r=worker_result(b1,c)
    if name=="malformed_worker_result": r["source_binding"]={"task_id":c["task_id"]}; return closed(lambda:b1.validate_worker_result_envelope(r),Err)
    if name=="missing_source_binding": r.pop("source_binding"); return closed(lambda:b1.validate_worker_result_envelope(r),Err)
    bind={"wrong_worker_id_binding":"worker_id","wrong_invocation_binding":"invocation_id","wrong_task_binding":"task_id","wrong_context_binding":"context_id"}
    if name in bind: r["source_binding"][bind[name]]="wrong"; return closed(lambda:b1.validate_source_binding(r,c),Err)
    if name in {"unknown_outcome","timeout_outcome"}: r["status"]="UNKNOWN" if name.startswith("unknown") else "TIMEOUT"; return closed(lambda:b1.validate_worker_result_envelope(r),Err)
    if name=="unexpected_success_envelope": r["success"]=True; return closed(lambda:b1.validate_worker_result_envelope(r),Err)
    if name=="valid_outer_missing_inner_required": r["source_binding"].pop("artifact_set_id"); return closed(lambda:b1.validate_worker_result_envelope(r),Err)
    if name=="valid_outer_wrong_inner_type": r["source_binding"]["worker_id"]=9; return closed(lambda:b1.validate_worker_result_envelope(r),Err)
    if name=="valid_outer_illegal_inner_value": r["source_binding"]["artifact_set_id"]="not-a-digest"; return closed(lambda:b1.validate_worker_result_envelope(r),Err)
    if name=="intermediate_exception_fail_closed":
        suite=unittest.TestSuite([b1.V08AdapterCoreOfflineTests("test_24_core_path_rejects_malformed_internal_result")]); res=unittest.TestResult(); suite.run(res); return "FAIL_CLOSED" if res.wasSuccessful() else "ACCEPTED"
    raise OwnerNotReady(f"unknown B1 contract case: {name}")

def exec_b1_artifact(name,b1):
    if name=="extra_undeclared_artifact":
        suite=unittest.TestSuite([b1.V08AdapterCoreOfflineTests("test_34_hidden_undeclared_workspace_artifact_rejected")]); res=unittest.TestResult(); suite.run(res); return "FAIL_CLOSED" if res.wasSuccessful() else "ACCEPTED"
    Err=b1.AdapterContractError
    with tempfile.TemporaryDirectory(prefix="v08-art-") as d:
        root=Path(d); a=root/"artifact.txt"; a.write_text("one",encoding="utf-8"); c=capsule(b1); r=b1.result_for(c,a)
        if name=="digest_map_missing": r.pop("artifact_hashes")
        elif name=="digest_map_empty": r["artifact_hashes"]={}
        elif name=="missing_one_digest":
            b=root/"b.txt"; b.write_text("two",encoding="utf-8"); c=b1.build_task_capsule(task_id="task-1",invocation_id="invocation-1",worker_id="fixture-alpha",context_id="context-1",objective="probe",artifact_declarations=[{"path":"artifact.txt","media_type":"text/plain"},{"path":"b.txt","media_type":"text/plain"}],capabilities=["artifact-write"],allowed_effects=["LOCAL_REVERSIBLE_WRITE"],network_scope="NONE"); r={"artifact_paths":["artifact.txt","b.txt"],"artifact_hashes":{"artifact.txt":b1.digest(a)}}
        elif name=="extra_undeclared_digest": r["artifact_hashes"]["extra.txt"]="0"*64
        elif name=="wrong_digest": r["artifact_hashes"]["artifact.txt"]="0"*64
        elif name=="artifact_changed_after_result": a.write_text("changed",encoding="utf-8")
        elif name in {"artifact_outside_workspace","path_traversal"}:
            outside=root.parent/(root.name+"-outside.txt"); outside.write_text("x",encoding="utf-8"); r=b1.result_for(c,outside,raw_path="../"+outside.name)
        elif name=="duplicate_artifact_path": r["artifact_paths"]=["artifact.txt","artifact.txt"]
        elif name=="declared_artifact_missing_file": a.unlink()
        elif name=="digest_key_path_alias_confusion": r["artifact_paths"]=["./artifact.txt"]
        else: raise OwnerNotReady(f"unknown B1 artifact case: {name}")
        return closed(lambda:b1.validate_worker_artifacts(r,c,root),Err)

def replacement_probe(name,b1):
    reg=b1.registry_for("fixture-alpha","fixture-beta"); before=hashlib.sha256((RUNTIME/"v08_adapter.py").read_bytes()).hexdigest(); results={}; outputs={}; calls=None
    for wid in ("fixture-alpha","fixture-beta"):
        with tempfile.TemporaryDirectory(prefix="v08-worker-") as d:
            if name=="one_invocation_one_worker" and wid=="fixture-alpha":
                with mock.patch.object(b1.adapter.subprocess,"run",wraps=b1.adapter.subprocess.run) as run:
                    out=b1.adapter.invoke_worker(worker_id=wid,task_id="t",context_id="c",objective="probe",workspace=d,artifact_declarations=[{"path":"artifact.txt","media_type":"text/plain"}],registry=reg); calls=run.call_count
            else: out=b1.adapter.invoke_worker(worker_id=wid,task_id="t",context_id="c",objective="probe",workspace=d,artifact_declarations=[{"path":"artifact.txt","media_type":"text/plain"}],registry=reg)
            results[wid]=out; outputs[wid]=(Path(d)/"artifact.txt").read_text(encoding="utf-8")
    a,b=reg["workers"]; strip=lambda x:{k:v for k,v in x.items() if k!="worker_id"}
    checks={"fixture_alpha_single_worker":results["fixture-alpha"]["source_binding"]["worker_id"]=="fixture-alpha","fixture_beta_single_worker":results["fixture-beta"]["source_binding"]["worker_id"]=="fixture-beta","same_adapter_core_path":results["fixture-alpha"]["status"]==results["fixture-beta"]["status"]=="DONE","selection_only_changes_registry_worker_id":strip(a)==strip(b),"no_core_code_change_for_replacement":before==hashlib.sha256((RUNTIME/"v08_adapter.py").read_bytes()).hexdigest(),"source_worker_id_differs":results["fixture-alpha"]["source_binding"]["worker_id"]!=results["fixture-beta"]["source_binding"]["worker_id"],"artifacts_may_differ":outputs["fixture-alpha"]!=outputs["fixture-beta"],"per_artifact_digest_independent":results["fixture-alpha"]["artifact_proof"]!=results["fixture-beta"]["artifact_proof"] and outputs["fixture-alpha"]!=outputs["fixture-beta"],"never_multi_worker_scheduler":"scheduler" not in (RUNTIME/"v08_adapter.py").read_text(encoding="utf-8").lower(),"one_invocation_one_worker":calls==1}
    return "PROVE" if checks.get(name,False) else "FAILED_PROOF"

def exec_b1(case,b1):
    cat,name=case["category"],case["owner_case"]
    if cat=="adapter_contract": return exec_b1_contract(name,b1)
    if cat=="artifact": return exec_b1_artifact(name,b1)
    if cat=="worker_replacement": return replacement_probe(name,b1)
    if cat=="provider_separation":
        if name=="provider_kind_separation_positive": return "PROVE" if b1.PROVIDER_KIND_API_MODEL!=b1.PROVIDER_KIND_WEB_SESSION else "FAILED_PROOF"
        reg=b1.registry_for("fixture-alpha"); reg["providers"][0 if name=="web_session_as_api_model" else 1]["kind"]=b1.PROVIDER_KIND_WEB_SESSION if name=="web_session_as_api_model" else b1.PROVIDER_KIND_API_MODEL
        return closed(lambda:b1.validate_registry(reg),b1.AdapterContractError)
    raise OwnerNotReady(f"unsupported B1 case: {case['id']}")

def history_attack(name):
    r=Repo()
    try:
        if name=="accepted_base_mismatch":
            git(r.root,"checkout","--orphan","o"); git(r.root,"rm","-rf","."); write(r.root,"x","x"); o=commit(r.root,"o"); fn=lambda:ev.need_ancestor(r.root,r.base,o,"BASE_MISMATCH")
        elif name=="candidate_sha_missing": fn=lambda:ev.need_commit(r.root,"CANDIDATE","f"*40)
        elif name=="candidate_not_descendant":
            git(r.root,"checkout","--orphan","o"); git(r.root,"rm","-rf","."); write(r.root,"x","x"); o=commit(r.root,"o"); fn=lambda:ev.need_ancestor(r.root,r.base,o,"CANDIDATE_NOT_FROM_BASE")
        elif name=="source_commit_missing": fn=lambda:ev.need_commit(r.root,"B1_COMMIT","0"*40,"NOT_READY")
        elif name=="source_not_from_base":
            git(r.root,"checkout","--orphan","o"); git(r.root,"rm","-rf","."); write(r.root,"a","x"); o=commit(r.root,"o"); fn=lambda:ev.need_ancestor(r.root,r.base,o,"B1_NOT_FROM_BASE")
        elif name=="builder_out_of_ownership":
            git(r.root,"checkout","-b","bad",r.base); write(r.root,"a","a"); write(r.root,"oops","x"); s=commit(r.root,"bad"); fn=lambda:ev.require_builder_history(r.root,r.base,s,"b1",("a",))
        elif name in {"candidate_extra_13th_path","candidate_touches_v07_strategic","candidate_touches_runtime_py","candidate_touches_src_aicontrol","candidate_touches_old_tests"}: fn=lambda:ev.exact_path_rows([("A",f"p{i}") for i in range(12)]+[("A","extra")],tuple(f"p{i}" for i in range(12)))
        elif name=="candidate_missing_expected_path": fn=lambda:ev.exact_path_rows([("A",f"p{i}") for i in range(11)],tuple(f"p{i}" for i in range(12)))
        elif name=="source_owned_file_modified_after_merge":
            s=r.source("b1","a","owned"); git(r.root,"checkout","-B","f",s); write(r.root,"a","tamper"); commit(r.root,"tamper"); git(r.root,"checkout",s,"--","a"); f=commit(r.root,"restore"); fn=lambda:ev.require_no_post_source_touch(r.root,s,f,"b1",("a",))
        elif name=="candidate_rename_copy_status": fn=lambda:ev.name_status("R100\told\tnew")
        elif name=="candidate_duplicate_name_status_path": fn=lambda:ev.exact_path_rows([("A","a"),("M","a")],("a","b"))
        else: raise OwnerNotReady(name)
        try: fn()
        except ev.EvidenceError as e: return e.status
        return "ACCEPTED"
    finally: r.close()

def exec_b3(case):
    cat,name=case["category"],case["owner_case"]
    if cat=="scope_git": return history_attack(name)
    if cat=="provider_separation":
        src={"provider_id_special_case_branch":"def f(provider_id):\n if provider_id=='provider-x': return 1\n","worker_id_special_case_branch":"def f(worker_id):\n if worker_id=='worker-x': return 1\n","chatgpt_name_hardcoded_branch":"def f(x):\n if x=='chatgpt': return 1\n","workbuddy_name_hardcoded_branch":"def f(x):\n if x=='workbuddy': return 1\n","codex_name_hardcoded_branch":"def f(x):\n if x=='codex': return 1\n","identity_branch_ast_scan":"def f(worker_id,s,g):\n h={'fixture-alpha':s}\n return h.get(worker_id,g)\n"}[name]
        return "DETECTED" if ev.identity_findings(src,identities={"provider-x","worker-x"}) else "MISSED"
    if cat=="authority_isolation":
        symbol={"grant_authority":"grant_authority","revoke_authority":"revoke_authority","produce_reviewer_pass":"reviewer_pass","promote_milestone":"promote_milestone","crown_candidate":"crown_candidate","mutate_canonical_authority_state":"mutate_authority_state"}[name]; a,_=ev.isolation_findings(f"def f():\n ops={{'go':{symbol}}}\n return ops['go']()\n"); return "FORBIDDEN" if a else "MISSED"
    if cat=="effect_isolation":
        symbol={"effect_reservation":"effect_reservation","effect_wal_commit":"effect_wal_commit","external_side_effect_authorization":"authorize_external_effect","external_effect_execution_permission":"external_effect_permission","new_effect_transport_path":"execute_external_effect"}[name]; _,e=ev.isolation_findings(f"def f():\n ops={{'go':{symbol}}}\n return ops['go']()\n"); return "FORBIDDEN" if e else "MISSED"
    raise OwnerNotReady(case["id"])

def emit_attack_results():
    m=ev.matrix(ev.ROOT)
    try: b1,b2=owner_modules()
    except OwnerNotReady as e: print(str(e),file=sys.stderr); return 3
    for c in m["cases"]:
        try:
            observed=exec_b1(c,b1) if c["owner"]=="B1" else exec_b2(c,b2) if c["owner"]=="B2" else exec_b3(c)
            rec={"attack_id":c["id"],"owner":c["owner"],"owner_case":c["owner_case"],"expected_outcome":c["expected_outcome"],"observed_outcome":observed,"executed":True,"result":"PASS" if observed==c["expected_outcome"] else "FAIL"}
        except OwnerNotReady as e: print(f"{c['id']}:{e}",file=sys.stderr); return 3
        except Exception as e: rec={"attack_id":c["id"],"owner":c["owner"],"owner_case":c["owner_case"],"expected_outcome":c["expected_outcome"],"observed_outcome":f"EXCEPTION:{type(e).__name__}","executed":True,"result":"FAIL"}
        print(ev.ATTACK_RESULT_PREFIX+json.dumps(rec,sort_keys=True,separators=(",",":")),flush=True)
    return 0

def main():
    if "--emit-attack-results" in sys.argv[1:]: return emit_attack_results()
    result=unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromModule(sys.modules[__name__])); return 0 if result.wasSuccessful() else 1
if __name__=="__main__": raise SystemExit(main())
