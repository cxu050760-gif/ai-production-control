"""V0.8 B3 machine Evidence. No Adapter/Registry implementation lives here."""
from __future__ import annotations
import argparse, ast, hashlib, json, os, re, subprocess, sys
from datetime import datetime, timezone
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
PY=sys.executable
BASE="a184e2bd1f42d62bae6d195814fe4bf5ac30be4e"
VERSION="V0.8"
SCHEMA="v0.8-adapter-evidence/1"
MATRIX_SCHEMA="v0.8-adapter-attack-matrix"
MATRIX_VERSION="V08-ATTACK-MATRIX-1"
SUCCESS="V08_ADAPTER_EVIDENCE_OK"

PATHS=(
"runtime/run.cmd","runtime/v08_adapter_contract.py","runtime/v08_adapter.py",
"runtime/fixtures/v08_fixture_worker.py","runtime/test_v08_adapter_core_offline.py",
"runtime/bootstrap.json","runtime/v08_adapter_registry.json",
"runtime/test_v08_adapter_registry_offline.py",
"runtime/fixtures/v08_adapter_registry_attack_cases.json",
"runtime/v08_adapter_evidence.py","runtime/test_v08_adapter_evidence_offline.py",
"runtime/fixtures/v08_adapter_attack_cases.json")
OWN={
"b1":PATHS[:5],
"b2":PATHS[5:9],
"b3":PATHS[9:]}
CORE=("runtime/v08_adapter_contract.py","runtime/v08_adapter.py")
ISOLATION=CORE+("runtime/fixtures/v08_fixture_worker.py",)
REGISTRY="runtime/v08_adapter_registry.json"
REQUIRED_FIELDS=(
"schema","version","accepted_base_sha","candidate_sha","b1_commit","b2_commit","b3_commit",
"changed_files","changed_file_hashes","test_command","exit_code","test_result","attack_case_id",
"attack_result","worker_replacement_proof","provider_separation_proof","artifact_integrity_proof",
"source_binding_proof","authority_isolation_proof","effect_isolation_proof",
"backward_regression_result","generated_at")
BRANDS=("chatgpt","workbuddy","codex","fixture-alpha","fixture-beta")
TRANSPORT=("bsk","daemon","marker","yz_lib","52900","chrome-extension","cft_executable",
"bsk_daemon_port","dom hack","click internals","bridge")
AUTH={"grant_authority","revoke_authority","set_authority","mutate_authority",
"mutate_authority_state","promote","promote_milestone","crown","crown_candidate",
"assign_verdict","set_verdict","reviewer_pass"}
EFFECT={"reserve_effect","effect_reservation","commit_effect","effect_wal","effect_wal_commit",
"authorize_effect","authorize_external_effect","execute_external_effect","external_effect_permission"}

class EvidenceError(RuntimeError):
    def __init__(self,code,status="HARD_FAIL"): self.code,self.status=code,status
    def __str__(self): return f"{self.status}:{self.code}"
def die(code,status="HARD_FAIL"): raise EvidenceError(code,status)
def sha(label,v):
    if not isinstance(v,str) or not re.fullmatch(r"[0-9a-f]{40}",v): die(f"{label}_BAD_SHA")
    return v
def run(root,*cmd,check=True):
    env=os.environ.copy(); env.update(PYTHONUTF8="1",PYTHONIOENCODING="utf-8")
    p=subprocess.run(cmd,cwd=root,text=True,stdout=subprocess.PIPE,stderr=subprocess.PIPE,env=env)
    if check and p.returncode: die(f"COMMAND_FAILED:{' '.join(cmd)}:{p.returncode}")
    return p
def gt(root,*a): return run(root,"git",*a).stdout.strip()
def exists(root,s): return run(root,"git","cat-file","-e",f"{s}^{{commit}}",check=False).returncode==0
def need_commit(root,label,s,status="HARD_FAIL"):
    sha(label,s)
    if not exists(root,s): die(f"{label}_NOT_FOUND",status)
def ancestor(root,a,b): return run(root,"git","merge-base","--is-ancestor",a,b,check=False).returncode==0
def need_ancestor(root,a,b,code):
    if not ancestor(root,a,b): die(code)

def name_status(text):
    out=[]
    if not text.strip(): return out
    for line in text.splitlines():
        p=line.split("\t")
        if len(p)!=2: die("DIFF_RENAME_COPY_OR_MALFORMED")
        st,path=p
        if st not in {"A","M"}: die(f"DIFF_STATUS:{st}:{path}")
        if not path or path.startswith("/") or "\\" in path: die(f"DIFF_PATH:{path}")
        out.append((st,path))
    return out

def exact_paths(root,base,candidate,expected=PATHS):
    rows=name_status(gt(root,"diff","--name-status",f"{base}..{candidate}","--"))
    got=[p for _,p in rows]
    if len(got)!=len(set(got)): die("DUPLICATE_CHANGED_PATH")
    if len(got)!=len(expected): die(f"CHANGED_PATH_COUNT:{len(got)}")
    extra=sorted(set(got)-set(expected)); missing=sorted(set(expected)-set(got))
    if extra: die("EXTRA_CHANGED_PATH:"+",".join(extra))
    if missing: die("MISSING_CHANGED_PATH:"+",".join(missing))
    return rows

def blob(root,c,p):
    q=run(root,"git","rev-parse",f"{c}:{p}",check=False)
    if q.returncode: die(f"PATH_MISSING:{c}:{p}")
    return q.stdout.strip()
def bytes_at(root,c,p):
    q=subprocess.run(["git","show",f"{c}:{p}"],cwd=root,stdout=subprocess.PIPE,stderr=subprocess.PIPE)
    if q.returncode: die(f"PATH_READ_FAIL:{c}:{p}")
    return q.stdout
def text_at(root,c,p):
    try:return bytes_at(root,c,p).decode()
    except UnicodeDecodeError: die(f"NON_UTF8:{p}")

def provenance(root,candidate,sources,base=BASE,ownership=OWN):
    proof={}
    for b in ("b1","b2","b3"):
        s=sources.get(b,""); need_commit(root,b.upper()+"_COMMIT",s,"NOT_READY")
        if s==base: die(f"{b.upper()}_EQUALS_BASE")
        need_ancestor(root,base,s,f"{b.upper()}_NOT_FROM_BASE")
        need_ancestor(root,s,candidate,f"{b.upper()}_NOT_ANCESTOR_CANDIDATE")
        rows=name_status(gt(root,"diff","--name-status",f"{base}..{s}","--")); got=[p for _,p in rows]
        exp=set(ownership[b])
        if set(got)-exp: die(f"{b.upper()}_OUT_OF_OWNERSHIP")
        if exp-set(got): die(f"{b.upper()}_MISSING_OWNED_PATH")
        binds={}
        for p in ownership[b]:
            if blob(root,s,p)!=blob(root,candidate,p): die(f"{b.upper()}_POST_SOURCE_TAMPER:{p}")
            binds[p]=blob(root,candidate,p)
        proof[b]={"commit":s,"paths":got,"candidate_blob_binding":binds}
    return proof

def matrix(root=ROOT):
    p=root/"runtime/fixtures/v08_adapter_attack_cases.json"
    if not p.exists(): die("ATTACK_MATRIX_MISSING","NOT_READY")
    try:m=json.loads(p.read_text(encoding="utf-8"))
    except Exception: die("ATTACK_MATRIX_MALFORMED")
    if m.get("schema")!=MATRIX_SCHEMA or m.get("version")!=VERSION or m.get("attack_matrix_version")!=MATRIX_VERSION or m.get("accepted_base_sha")!=BASE:
        die("ATTACK_MATRIX_BINDING")
    cs=m.get("cases")
    if not isinstance(cs,list) or not cs: die("ATTACK_MATRIX_EMPTY")
    ids=[x.get("id") for x in cs]
    if len(ids)!=len(set(ids)) or any(not isinstance(x,str) for x in ids): die("ATTACK_MATRIX_IDS")
    cats={x.get("category") for x in cs}
    need={"scope_git","registry","adapter_contract","artifact","worker_replacement","provider_separation","authority_isolation","effect_isolation"}
    if cats!=need: die("ATTACK_MATRIX_CATEGORIES")
    return m

def attack_binding(root,candidate,m):
    by={}
    for x in m["cases"]: by.setdefault(x["owner_test"],[]).append(x["id"])
    for p,ids in by.items():
        s=text_at(root,candidate,p)
        miss=[i for i in ids if not re.search(rf"\b{re.escape(i)}\b",s)]
        if miss: die(f"ATTACK_NOT_BOUND:{p}:{','.join(miss)}")
    return {k:sorted(v) for k,v in sorted(by.items())}

def _names(n):
    z=set()
    for x in ast.walk(n):
        if isinstance(x,ast.Name): z.add(x.id.lower())
        elif isinstance(x,ast.Attribute): z.add(x.attr.lower())
    return z
def _strings(n): return [x.value.lower() for x in ast.walk(n) if isinstance(x,ast.Constant) and isinstance(x.value,str)]
def identity_findings(src,path="<memory>"):
    try:t=ast.parse(src,path)
    except SyntaxError: die(f"CORE_SYNTAX:{path}")
    out=[]
    for n in ast.walk(t):
        if isinstance(n,(ast.If,ast.IfExp,ast.While)):
            vals=_strings(n.test)
            if any(any(b in v for b in BRANDS) for v in vals): out.append(f"{path}:{n.lineno}:brand")
            names=_names(n.test)
            watched=any(x.endswith("provider_id") or x.endswith("worker_id") for x in names)
            literals=[v for v in vals if v not in {"provider_id","worker_id"}]
            if watched and literals and isinstance(n.test,(ast.Compare,ast.Call,ast.BoolOp,ast.BinOp)): out.append(f"{path}:{n.lineno}:identity")
        elif isinstance(n,ast.Match):
            names=_names(n.subject)
            if any(x.endswith("provider_id") or x.endswith("worker_id") for x in names):
                if any(_strings(c.pattern) for c in n.cases): out.append(f"{path}:{n.lineno}:match")
    return out
def isolation_findings(src,path="<memory>"):
    try:t=ast.parse(src,path)
    except SyntaxError: die(f"ISOLATION_SYNTAX:{path}")
    a=[]; e=[]
    for n in ast.walk(t):
        if isinstance(n,ast.Call):
            f=n.func.id.lower() if isinstance(n.func,ast.Name) else n.func.attr.lower() if isinstance(n.func,ast.Attribute) else ""
            if f in AUTH:a.append(f"{path}:{n.lineno}:{f}")
            if f in EFFECT:e.append(f"{path}:{n.lineno}:{f}")
        if isinstance(n,ast.Dict):
            for k,v in zip(n.keys,n.values):
                if isinstance(k,ast.Constant) and str(k.value).lower() in {"verdict","reviewer_verdict"} and isinstance(v,ast.Constant) and v.value=="PASS":
                    a.append(f"{path}:{n.lineno}:reviewer-pass")
    return a,e
def static_gates(root,candidate):
    ids=[]
    for p in CORE: ids+=identity_findings(text_at(root,candidate,p),p)
    if ids: die("IDENTITY_CORE_BRANCH:"+"|".join(ids[:5]))
    a=[];e=[]
    for p in ISOLATION:
        x,y=isolation_findings(text_at(root,candidate,p),p); a+=x;e+=y
    if a: die("AUTHORITY_ISOLATION:"+"|".join(a[:5]))
    if e: die("EFFECT_ISOLATION:"+"|".join(e[:5]))
    leaks=[]
    for p in (REGISTRY,)+ISOLATION:
        s=text_at(root,candidate,p).lower()
        leaks += [f"{p}:{x}" for x in TRANSPORT if x in s]
    if leaks: die("TRANSPORT_LEAK:"+"|".join(leaks[:5]))
    return {"identity":{"status":"PASS","paths":list(CORE)},"authority":{"status":"PASS","paths":list(ISOLATION)},
            "effect":{"status":"PASS","paths":list(ISOLATION)},"transport":{"status":"PASS","paths":[REGISTRY,*ISOLATION]}}

def checked(root,*cmd):
    p=run(root,*cmd,check=False)
    r={"command":" ".join(cmd),"exit_code":p.returncode,"stdout_tail":p.stdout[-1000:],"stderr_tail":p.stderr[-1000:]}
    if p.returncode: die(f"TEST_FAILED:{r['command']}:{p.returncode}")
    return r
def not_ready(a,missing):
    now=datetime.now(timezone.utc).isoformat()
    r={k:None for k in REQUIRED_FIELDS}; r.update(schema=SCHEMA,version=VERSION,status="NOT_READY",accepted_base_sha=BASE,
      candidate_sha=a.candidate,b1_commit=a.b1_commit,b2_commit=a.b2_commit,b3_commit=a.b3_commit,changed_files=[],
      changed_file_hashes={},test_command=[],exit_code=3,test_result="NOT_READY",attack_case_id=[],attack_result={},
      worker_replacement_proof={"status":"NOT_READY"},provider_separation_proof={"status":"NOT_READY"},
      artifact_integrity_proof={"status":"NOT_READY"},source_binding_proof={"status":"NOT_READY"},
      authority_isolation_proof={"status":"NOT_READY"},effect_isolation_proof={"status":"NOT_READY"},
      backward_regression_result={"status":"NOT_READY"},generated_at=now,missing_required=missing)
    return r

def build(root,candidate,b1,b2,b3):
    need_commit(root,"ACCEPTED_BASE",BASE); need_commit(root,"CANDIDATE",candidate)
    need_ancestor(root,BASE,candidate,"CANDIDATE_NOT_FROM_BASE")
    if gt(root,"rev-parse","HEAD")!=candidate: die("HEAD_MISMATCH")
    if gt(root,"status","--porcelain"): die("WORKTREE_DIRTY")
    rows=exact_paths(root,BASE,candidate)
    prov=provenance(root,candidate,{"b1":b1,"b2":b2,"b3":b3})
    m=matrix(root); binding=attack_binding(root,candidate,m); st=static_gates(root,candidate)
    new=[(PY,"runtime/test_v08_adapter_core_offline.py"),(PY,"runtime/test_v08_adapter_registry_offline.py"),(PY,"runtime/test_v08_adapter_evidence_offline.py")]
    reg=[("git","diff","--check",f"{BASE}..{candidate}"),(PY,"-m","compileall","runtime","src","tests"),
         (PY,"-m","unittest","discover","-s","runtime","-p","test_*_offline.py"),(PY,"tests/test_core.py")]
    results=[checked(root,*c) for c in new+reg]
    ids=[x["id"] for x in m["cases"]]; by=lambda p:[x for x in ids if x.startswith(p)]
    hashes={p:hashlib.sha256(bytes_at(root,candidate,p)).hexdigest() for p in PATHS}
    return {"schema":SCHEMA,"version":VERSION,"status":"PASS","accepted_base_sha":BASE,"candidate_sha":candidate,
    "b1_commit":b1,"b2_commit":b2,"b3_commit":b3,"changed_files":[{"status":s,"path":p} for s,p in rows],
    "changed_file_hashes":hashes,"test_command":[x["command"] for x in results],"exit_code":0,"test_result":"PASS",
    "attack_case_id":ids,"attack_result":{x:"PASS" for x in ids},"attack_case_test_binding":binding,
    "worker_replacement_proof":{"status":"PASS","attack_case_ids":by("E"),"single_worker":True,"same_core_path":True,"multi_worker_scheduler":False},
    "provider_separation_proof":{"status":"PASS","attack_case_ids":by("F"),"api_model_not_web_session":True,"static":st["identity"],"transport":st["transport"]},
    "artifact_integrity_proof":{"status":"PASS","attack_case_ids":by("D"),"per_artifact_digest":True},
    "source_binding_proof":{"status":"PASS","builders":prov},"authority_isolation_proof":{**st["authority"],"attack_case_ids":by("G")},
    "effect_isolation_proof":{**st["effect"],"attack_case_ids":by("H")},
    "backward_regression_result":{"status":"PASS","covers":["Official Entry","B/R Router","Goal Contract","state recovery","Effect Safety","EC","V0.7 Strategic Brain","V0.7 C","V0.7 Strategic Reuse","V0.7 Strategic Integration","tests/test_core.py"],"commands":results[len(new):]},
    "generated_at":datetime.now(timezone.utc).isoformat()}

def main(argv=None):
    p=argparse.ArgumentParser()
    for x in ("candidate","b1-commit","b2-commit","b3-commit"): p.add_argument("--"+x)
    a=p.parse_args(argv); missing=[k for k,v in vars(a).items() if not v]
    if missing:
        print(json.dumps(not_ready(a,missing),sort_keys=True)); print("V08_EVIDENCE_STATUS=NOT_READY"); return 3
    try:r=build(ROOT,sha("CANDIDATE",a.candidate),sha("B1",a.b1_commit),sha("B2",a.b2_commit),sha("B3",a.b3_commit))
    except EvidenceError as e:
        print(json.dumps({"schema":SCHEMA,"version":VERSION,"status":e.status,"accepted_base_sha":BASE,"candidate_sha":a.candidate,
        "b1_commit":a.b1_commit,"b2_commit":a.b2_commit,"b3_commit":a.b3_commit,"exit_code":2 if e.status=="HARD_FAIL" else 3,
        "test_result":e.status,"failure_code":e.code,"generated_at":datetime.now(timezone.utc).isoformat()},sort_keys=True))
        print("V08_EVIDENCE_STATUS="+e.status); return 2 if e.status=="HARD_FAIL" else 3
    print(json.dumps(r,sort_keys=True)); print(f"{SUCCESS} candidate={a.candidate}"); return 0
if __name__=="__main__": raise SystemExit(main())
