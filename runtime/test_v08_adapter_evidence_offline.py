"""B3 offline Evidence self-tests; production Adapter/Registry may be absent."""
from __future__ import annotations
import contextlib, io, json, subprocess, sys, tempfile, unittest
from pathlib import Path
R=Path(__file__).resolve().parent
if str(R) not in sys.path: sys.path.insert(0,str(R))
import v08_adapter_evidence as ev

ATTACK_CASE_IDS=('A01', 'A02', 'A03', 'A04', 'A05', 'A06', 'A07', 'A08', 'A09', 'A10', 'A11', 'A12', 'A13', 'A14', 'A15', 'F03', 'F04', 'F05', 'F06', 'F07', 'F09', 'G01', 'G02', 'G03', 'G04', 'G05', 'G06', 'H01', 'H02', 'H03', 'H04', 'H05')

def g(root,*a):
    p=subprocess.run(["git",*a],cwd=root,text=True,stdout=subprocess.PIPE,stderr=subprocess.PIPE)
    if p.returncode: raise AssertionError(f"git {a} failed {p.stderr}")
    return p.stdout.strip()
def w(root,p,s):
    q=root/p; q.parent.mkdir(parents=True,exist_ok=True); q.write_text(s,encoding="utf-8")
def c(root,msg):
    g(root,"add","-A"); g(root,"commit","-m",msg); return g(root,"rev-parse","HEAD")

class Repo:
    def __init__(self):
        self.t=tempfile.TemporaryDirectory(prefix="v08-b3-"); self.r=Path(self.t.name)
        g(self.r,"init"); g(self.r,"config","user.email","b3@example.invalid"); g(self.r,"config","user.name","B3")
        w(self.r,"seed","x"); self.base=c(self.r,"base"); g(self.r,"branch","-M","base")
    def source(self,b,p):
        g(self.r,"checkout","-b",b,self.base); w(self.r,p,b); s=c(self.r,b); g(self.r,"checkout","base"); return s
    def merge(self,ss):
        g(self.r,"checkout","-B","final",self.base)
        for s in ss:g(self.r,"merge","--no-ff","--no-edit",s)
        return g(self.r,"rev-parse","HEAD")
    def close(self): self.t.cleanup()

class Matrix(unittest.TestCase):
    def test_matrix(self):
        m=ev.matrix(ev.ROOT); ids=[x["id"] for x in m["cases"]]
        self.assertEqual(len(ids),97); self.assertEqual(len(ids),len(set(ids)))
        self.assertTrue(set(ATTACK_CASE_IDS)<=set(ids)); self.assertEqual(len(ev.PATHS),12)
        self.assertEqual(set().union(*(set(x) for x in ev.OWN.values())),set(ev.PATHS))
    def test_schema(self):
        self.assertEqual(ev.SCHEMA,"v0.8-adapter-evidence/1")
        self.assertEqual(len(ev.REQUIRED_FIELDS),22)

class GitGates(unittest.TestCase):
    def setUp(self):
        self.x=Repo(); self.own={"b1":("a",),"b2":("b",),"b3":("c",)}
        self.b1=self.x.source("b1","a"); self.b2=self.x.source("b2","b"); self.b3=self.x.source("b3","c")
        self.can=self.x.merge([self.b1,self.b2,self.b3])
    def tearDown(self): self.x.close()
    def fails(self,fn,text,status=None):
        with self.assertRaises(ev.EvidenceError) as z:fn()
        self.assertIn(text,z.exception.code)
        if status:self.assertEqual(z.exception.status,status)
    def test_exact_paths_and_provenance(self):
        r=ev.exact_paths(self.x.r,self.x.base,self.can,("a","b","c")); self.assertEqual(len(r),3)
        p=ev.provenance(self.x.r,self.can,{"b1":self.b1,"b2":self.b2,"b3":self.b3},self.x.base,self.own)
        self.assertEqual(set(p),{"b1","b2","b3"})
    def test_extra_and_missing_path(self):
        w(self.x.r,"extra","x"); bad=c(self.x.r,"extra")
        self.fails(lambda:ev.exact_paths(self.x.r,self.x.base,bad,("a","b","c")),"CHANGED_PATH_COUNT")
        self.fails(lambda:ev.exact_paths(self.x.r,self.x.base,self.can,("a","b","c","d")),"CHANGED_PATH_COUNT")
    def test_rename_shape(self):
        self.fails(lambda:ev.name_status("R100\told\tnew"),"DIFF_RENAME")
    def test_missing_source_not_ready(self):
        self.fails(lambda:ev.provenance(self.x.r,self.can,{"b1":"0"*40,"b2":self.b2,"b3":self.b3},self.x.base,self.own),"B1_COMMIT_NOT_FOUND","NOT_READY")
    def test_out_of_ownership(self):
        g(self.x.r,"checkout","-B","bad",self.x.base); w(self.x.r,"a","a"); w(self.x.r,"oops","x"); bad=c(self.x.r,"bad")
        self.fails(lambda:ev.provenance(self.x.r,bad,{"b1":bad,"b2":self.b2,"b3":self.b3},self.x.base,self.own),"B1_OUT_OF_OWNERSHIP")
    def test_wrong_base(self):
        g(self.x.r,"checkout","--orphan","orphan"); g(self.x.r,"rm","-rf","."); w(self.x.r,"a","x"); o=c(self.x.r,"orphan")
        self.fails(lambda:ev.provenance(self.x.r,o,{"b1":o,"b2":self.b2,"b3":self.b3},self.x.base,self.own),"B1_NOT_FROM_BASE")
    def test_post_source_tamper(self):
        g(self.x.r,"checkout","-B","tamper",self.can); w(self.x.r,"a","tampered"); bad=c(self.x.r,"tamper")
        self.fails(lambda:ev.provenance(self.x.r,bad,{"b1":self.b1,"b2":self.b2,"b3":self.b3},self.x.base,self.own),"B1_POST_SOURCE_TAMPER")
    def test_candidate_missing(self):
        self.fails(lambda:ev.need_commit(self.x.r,"CANDIDATE","f"*40),"CANDIDATE_NOT_FOUND")
    def test_candidate_not_descendant(self):
        g(self.x.r,"checkout","--orphan","orphan2"); g(self.x.r,"rm","-rf","."); w(self.x.r,"z","z"); o=c(self.x.r,"o")
        self.fails(lambda:ev.need_ancestor(self.x.r,self.x.base,o,"CANDIDATE_NOT_FROM_BASE"),"CANDIDATE_NOT_FROM_BASE")

class Static(unittest.TestCase):
    def test_generic_kind_allowed(self):
        self.assertEqual(ev.identity_findings('def f(provider_kind,worker_id,r):\n if not worker_id:return None\n if provider_kind=="API_MODEL":return r[worker_id]\n return r[worker_id]'),[])
    def test_identity_and_brands_rejected(self):
        self.assertTrue(ev.identity_findings('def f(worker_id):\n if worker_id=="fixture-alpha":return 1'))
        self.assertTrue(ev.identity_findings('def f(k):\n if k=="ChatGPT":return 1'))
    def test_authority_and_effect_rejected(self):
        a,e=ev.isolation_findings('def f():\n promote_milestone()\n return {"reviewer_verdict":"PASS"}'); self.assertTrue(a); self.assertFalse(e)
        a,e=ev.isolation_findings('def f():\n reserve_effect()'); self.assertFalse(a); self.assertTrue(e)

class Runner(unittest.TestCase):
    def test_missing_args_not_ready(self):
        s=io.StringIO()
        with contextlib.redirect_stdout(s): rc=ev.main([])
        out=s.getvalue(); self.assertEqual(rc,3); self.assertIn("V08_EVIDENCE_STATUS=NOT_READY",out); self.assertNotIn(ev.SUCCESS,out)
        self.assertEqual(json.loads(out.splitlines()[0])["status"],"NOT_READY")
    def test_failing_command_closed(self):
        with tempfile.TemporaryDirectory() as d:
            with self.assertRaises(ev.EvidenceError): ev.checked(Path(d),sys.executable,"-c","raise SystemExit(7)")
    def test_single_final_success_print(self):
        s=Path(ev.__file__).read_text(); needle='print(f"{SUCCESS} candidate={a.candidate}")'
        self.assertEqual(s.count(needle),1); self.assertGreater(s.index(needle),s.index("r=build("))

if __name__=="__main__":unittest.main(verbosity=2)
