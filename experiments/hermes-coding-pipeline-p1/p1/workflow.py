"""Authoritative Phase 0.2 -> Gate 5.9 state machine. No deployment verbs."""
from __future__ import annotations
import json
import shutil
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any
from .contracts import (ContractError, atomic_write, canonical, digest_file,
                        read_json, sha256, snapshot_inputs, safe_task_id,
                        PASS_REVIEW)
from .state import Store, StateError, exclusive_lock
from .gitops import git, head, inventory, inventory_hash, create_worktree
from .audit import audit_role
from .executor import invoke
from .a2a import call_adapter,validate_collection

class PipelineError(RuntimeError):
    pass

ROLE_STAGE={"0.2":"planner","2":"worker","3":"spec_reviewer","4":"quality_reviewer",
            "4.5":"tester_gate_a","5.1":"worker_remediation","5.2":"tester_gate_b","5.3":"arbitrator"}
STEP_STAGES=("0.2","gate0.2","1","2","3+4","4.5","5.0","5.1","5.2","5.3","5.85","gate5.9")


def require_snapshot(task:dict, root:Path)->dict:
    snap=root/"snapshots"
    names={"intent_sha256":"intent.md","matrix_sha256":"matrix.json","approval_sha256":"gate01.json","souls_sha256":"soul_hashes.json"}
    for key,filename in names.items():
        if not (snap/filename).exists() or digest_file(snap/filename)!=task[key]:
            raise PipelineError(f"frozen input tampering: {filename}")
    matrix=read_json(snap/"matrix.json")
    hashes=read_json(snap/"soul_hashes.json")
    for role,expected in hashes.items():
        if digest_file(snap/"souls"/f"{role}.md")!=expected:
            raise PipelineError(f"frozen Soul tampering: {role}")
    if task.get("spec_sha256") and digest_file(snap/"TASK_SPEC.md")!=task["spec_sha256"]:
        raise PipelineError("frozen TASK_SPEC tampering")
    return matrix


def initialize(home:Path, task_id:str, intent:Path, matrix:Path, approval:Path, souls:Path,
               project_root:Path, worktree_path:Path, mode:str,
               fixture_dir:Path|None=None, adapter_config:Path|None=None, base_ref:str="HEAD",
               safety_manifest:Path|None=None)->dict:
    safe_task_id(task_id)
    if mode not in ("offline_fixture","integration"):
        raise ContractError("mode must be offline_fixture or integration")
    if mode=="offline_fixture" and not fixture_dir:
        raise ContractError("offline_fixture requires fixture_dir")
    if mode=="integration" and not adapter_config:
        raise ContractError("integration requires adapter_config")
    home=home.resolve()
    if (home/"state.sqlite").exists():
        raise ContractError("task home already initialized")
    root=home
    snapshots=snapshot_inputs(root,intent,matrix,approval,souls)
    task={"task_id":task_id,"mode":mode,"stage":"0.2","status":"READY",
          "project_root":str(project_root.resolve()),"worktree_path":str(worktree_path.resolve()),
          "base_ref":base_ref,"fixture_dir":str(fixture_dir.resolve()) if fixture_dir else None,
          "adapter_config":str(adapter_config.resolve()) if adapter_config else None,
          "safety_manifest":str(safety_manifest.resolve()) if safety_manifest else None,
          "spec_sha256":None,"commit_sha":None,"review_commit_sha":None,
          "round_a":1,"round_b":1,"compliance_retraces":0,
          "a2a_job_id":None,"a2a_submitted_commit":None,
          "report_shas":{},"audit_history":[],"last_error":None,**snapshots}
    store=Store(home/"state.sqlite")
    try:store.create(task)
    finally:store.close()
    return task


class Pipeline:
    def __init__(self,home:Path):
        self.root=home.resolve()
        self.store=Store(self.root/"state.sqlite")
        rows=self.store.db.execute("SELECT task_id FROM tasks").fetchall()
        if len(rows)!=1:
            raise PipelineError("state must contain exactly one task")
        self.task_id=rows[0][0]

    def close(self):self.store.close()

    def status(self)->dict:
        task=self.store.load(self.task_id)
        return {key:task.get(key) for key in ("task_id","mode","stage","status","round_a","round_b","compliance_retraces","commit_sha","spec_sha256","a2a_job_id","last_error")}

    def _save(self,task:dict,event:str,detail:dict|None=None):
        self.store.save(task,event,detail)

    def _block(self,task:dict,why:str, status:str="BLOCKED"):
        task["status"]=status;task["last_error"]=why
        self._save(task,"blocked",{"stage":task["stage"],"reason":why,"status":status})

    def _advance(self,task:dict, stage:str):
        task["stage"]=stage;task["status"]="READY";task["last_error"]=None
        self._save(task,"stage_advanced")

    def _audit_record(self,task:dict,stage:str,report:dict,role:str):
        rec={"stage":stage,"role":role,"verdict":report["verdict"],"errors":report["errors"],"warnings":report["warnings"],"timestamp":time.time()}
        task["audit_history"].append(rec)
        name=stage.replace(".","_").replace("+","_")
        n=len(task["audit_history"])
        path=self.root/"audit_evidence"/f"{n:04d}_{name}_{role}.json"
        atomic_write(path,canonical(rec)+"\n")
        self._save(task,"step_audited",rec)
        return rec

    def _violation(self,task:dict,stage:str,errors:list[str]):
        if not errors:return False
        if task["compliance_retraces"]>=2:
            self._block(task,"compliance retrace cap exceeded: "+"; ".join(errors),"FAILED")
            return True
        task["compliance_retraces"]+=1
        # Retrying exactly the affected stage with its downstream stages is the
        # smallest safe replay; a corrupted input or approval instead blocks.
        if stage=="0.2":
            task["spec_sha256"]=None
        if stage=="3+4":task["stage"]="3+4"
        else:task["stage"]=stage
        task["status"]="READY"
        task["last_error"]="compliance replay: "+"; ".join(errors)
        self._save(task,"compliance_retrace",{"stage":stage,"count":task["compliance_retraces"],"errors":errors})
        return True

    def _run_role(self,task:dict,stage:str,role:str,attempt:int)->tuple[dict,dict]:
        task_root=self.root
        workdir=Path(task["project_root"] if stage=="0.2" else task["worktree_path"])
        before=inventory(workdir)
        before_head=head(workdir)
        hashes=read_json(task_root/"snapshots"/"soul_hashes.json")
        inp=sha256(canonical({"task_id":task["task_id"],"stage":stage,"role":role,
                    "matrix_sha256":task["matrix_sha256"],"intent_sha256":task["intent_sha256"],
                    "spec_sha256":task["spec_sha256"],"commit_sha":before_head,"soul_sha256":hashes[role]}).encode())
        run_id=self.store.start_run(task["task_id"],stage,role,inp,{"before_head":before_head,"before_digest":inventory_hash(before)})
        # Crash after start_run must never silently redispatch; resume blocks on RUNNING.
        envelope=invoke(task,role,stage,task_root,attempt,run_id)
        after=inventory(workdir)
        after_head=head(workdir)
        audit=audit_role(task,role,stage,envelope,before,after,before_head,after_head,hashes[role],task_root)
        payload=envelope["payload"]
        output_sha=sha256(canonical(payload).encode())
        details={"role":role,"stage":stage,"run_id":run_id,"before_head":before_head,"after_head":after_head,
                 "before_digest":inventory_hash(before),"after_digest":inventory_hash(after),
                 "invocation":{key:envelope[key] for key in ("mode","exit_code","stdout_sha256","stderr_sha256","command","assignment")},
                 "audit":audit,"payload":payload}
        self.store.finish_run(task["task_id"],run_id,"COMPLETED",output_sha,details)
        # Reports are P1-owned copies outside the reviewed source worktree.
        if payload.get("report"):
            name=f"{run_id:04d}_{stage.replace('.','_')}_{role}.md"
            file=task_root/"artifacts"/name
            atomic_write(file,payload["report"])
            for old in list(task["report_shas"]):
                if old.endswith("_"+role+".md"):
                    del task["report_shas"][old]
            task["report_shas"][name]=digest_file(file)
        return payload,audit

    def _review_pair(self,task:dict)->None:
        # Future threads run only external processes; SQLite stays on parent thread.
        repo=Path(task["worktree_path"])
        expected_head=head(repo)
        if expected_head!=task["commit_sha"]:
            self._block(task,"review pair input HEAD mismatch", "NEEDS_RECONCILIATION");return
        attempt=task["round_a"]
        # Each worker uses its own DB connection to allow independent persisted dispatches.
        # Worker object is NOT allowed to make phase transitions.
        def one(role:str,stage:str):
            db=Store(self.root/"state.sqlite")
            try:
                worker=Pipeline.__new__(Pipeline)
                worker.root=self.root;worker.store=db;worker.task_id=self.task_id
                return worker._run_role(dict(task),stage,role,attempt)
            finally:db.close()
        results={}; errors=[]
        with ThreadPoolExecutor(max_workers=2,thread_name_prefix="p1-review") as pool:
            futures={role:pool.submit(one,role,stage) for role,stage in (("spec_reviewer","3"),("quality_reviewer","4"))}
            for role,future in futures.items():
                try:results[role]=future.result()
                except Exception as exc:errors.append(f"{role}: {exc}")
        if errors:
            self._block(task,"parallel reviewer execution uncertain: "+"; ".join(errors),"NEEDS_RECONCILIATION");return
        if head(repo)!=expected_head:
            self._violation(task,"3+4",["review pair source HEAD changed"]);return
        for name in ("spec_reviewer","quality_reviewer"):
            matching=sorted((self.root/"artifacts").glob(f"*_{name}.md"))
            if matching:
                task["report_shas"][matching[-1].name]=digest_file(matching[-1])
        for role,(payload,audit) in results.items():
            self._audit_record(task,"3" if role=="spec_reviewer" else "4",audit,role)
            if audit["errors"]:
                self._violation(task,"3+4",[f"{role}: {e}" for e in audit["errors"]]);return
        verdicts={role:res[0].get("verdict") for role,res in results.items()}
        if any(verdict in ("QUESTION","NEEDS_SPECIALIST") for verdict in verdicts.values()):
            self._block(task,f"review requires clarification/specialist: {verdicts}","WAITING_CLARIFICATION");return
        if not all(v in PASS_REVIEW for v in verdicts.values()):
            self._retry_a(task,f"dual review did not pass: {verdicts}");return
        self._advance(task,"4.5")

    def _retry_a(self,task:dict,why:str):
        if task["round_a"]>=5:
            self._block(task,"Gate A max 5 development rounds exhausted: "+why,"FAILED");return
        task["round_a"]+=1
        self._advance(task,"2")

    def _retry_b(self,task:dict,why:str):
        if task["round_b"]>=5:
            self._block(task,"Gate B max 5 remediation rounds exhausted: "+why,"FAILED");return
        task["round_b"]+=1
        self._advance(task,"5.1")

    def _phase_role(self,task:dict,stage:str,role:str,attempt:int,next_stage:str,passes:set[str],retry:str|None=None):
        payload,audit=self._run_role(task,stage,role,attempt)
        self._audit_record(task,stage,audit,role)
        if self._violation(task,stage,audit["errors"]):return
        verdict=payload.get("verdict")
        if verdict in ("QUESTION","NEEDS_SPECIALIST"):
            self._block(task,f"{role} requests clarification/specialist", "WAITING_CLARIFICATION");return
        if verdict not in passes:
            if retry=="a":self._retry_a(task,f"{role} verdict: {verdict}")
            elif retry=="b":self._retry_b(task,f"{role} verdict: {verdict}")
            else:self._block(task,f"{role} verdict: {verdict}","FAILED")
            return
        if stage=="0.2":
            spec=payload.get("task_spec","")
            atomic_write(self.root/"snapshots"/"TASK_SPEC.md",spec)
            # Planner outputs candidate spec; Gate 0.2 freezes its SHA.
            task["proposed_spec_sha256"]=digest_file(self.root/"snapshots"/"TASK_SPEC.md")
            self._advance(task,"gate0.2");task["status"]="WAITING_APPROVAL";self._save(task,"gate02_wait")
            return
        if stage in ("2","5.1"):
            task["commit_sha"]=head(Path(task["worktree_path"]))
            if stage=="2":task["review_commit_sha"]=task["commit_sha"]
        if stage=="5.2":
            checks=payload.get("checks")
            if not isinstance(checks,dict) or any(checks.get(x)!="PASS" for x in ("smoke","canary","regression")):
                self._retry_b(task,"Gate B test evidence incomplete");return
        self._advance(task,next_stage)

    def _phase_worktree(self,task:dict):
        if task.get("safety_manifest"):
            safety=read_json(Path(task["safety_manifest"]))
            if safety.get("live_side_effects_disabled") is not True or not safety.get("reviewed_by"):
                self._block(task,"side effects manifest missing safety review");return
        elif task["mode"]=="integration":
            self._block(task,"side effects manifest mandatory for integration mode");return
        detail=create_worktree(Path(task["project_root"]),Path(task["worktree_path"]),task["task_id"],task["base_ref"],task["mode"]=="offline_fixture")
        task["commit_sha"]=detail["commit_sha"]
        self._audit_record(task,"1",{"verdict":"COMPLIANT","errors":[],"warnings": ["side-effect control is an integration prerequisite"] if task["mode"]=="offline_fixture" else []},"orchestrator")
        self._advance(task,"2")

    def _phase_a2a(self,task:dict):
        matrix=read_json(self.root/"snapshots"/"matrix.json")
        if not task["a2a_job_id"]:
            request={"task_id":task["task_id"],"commit_sha":task["commit_sha"],"matrix_sha256":task["matrix_sha256"],"idempotency_key":f"{task['task_id']}:5.0:{task['commit_sha']}"}
            # Write intent before dispatch. If process dies before Job ID return,
            # NEVER submit again: adapter must reconcile by idempotency key.
            task["a2a_submitted_commit"]=task["commit_sha"]
            task["a2a_submission_pending"]=True
            self._save(task,"a2a_dispatch_intent",request)
            response=call_adapter(task,self.root,"submit",request)
            if not response.get("job_id"):
                self._block(task,"A2A submit response missing job_id","NEEDS_RECONCILIATION");return
            task["a2a_job_id"]=response["job_id"]
            task["a2a_submission_pending"]=False
            self._save(task,"a2a_submitted",{"job_id":task["a2a_job_id"]})
        status=call_adapter(task,self.root,"status",{"job_id":task["a2a_job_id"]})
        if status.get("state") not in ("COMPLETED","QUORUM_MET"):
            task["status"]="WAITING_EXTERNAL"
            self._save(task,"a2a_wait",{"state":status.get("state")});return
        collection=call_adapter(task,self.root,"collect",{"job_id":task["a2a_job_id"]})
        errors=validate_collection(task,matrix,collection,self.root)
        audit={"verdict":"NON_COMPLIANT" if errors else "COMPLIANT","errors":errors,
               "warnings":["SIMULATED A2A reports" ] if task["mode"]=="offline_fixture" else []}
        self._audit_record(task,"5.0",audit,"a2a_external")
        if errors:
            # External evidence shortage is never fixed by fake P1 replay.
            self._block(task,"A2A report invalid: "+"; ".join(errors),"BLOCKED");return
        report=self.root/"artifacts"/"05_0_blind_review.json"
        atomic_write(report,canonical(collection)+"\n")
        task["report_shas"][report.name]=digest_file(report)
        self._advance(task,"5.1")

    def verify_evidence(self)->dict:
        task=self.store.load(self.task_id)
        problems=self.store.audit_events(self.task_id)
        try:
            require_snapshot(task,self.root)
        except (PipelineError,OSError) as exc:
            problems.append(str(exc))
        for name,expected in task["report_shas"].items():
            path=self.root/"artifacts"/name
            if not path.is_file() or digest_file(path)!=expected:
                problems.append(f"artifact SHA mismatch: {name}")
        return {"verdict":"COMPLIANT" if not problems else "NON_COMPLIANT","errors":problems}

    @staticmethod
    def _replay_origin(filename:str)->str|None:
        roles=(
            ("_spec_reviewer.md","3+4"),("_quality_reviewer.md","3+4"),
            ("_tester_gate_a.md","4.5"),("_tester_gate_b.md","5.2"),
            ("_worker_remediation.md","5.1"),("_arbitrator.md","5.3"),
            ("_worker.md","2"),
        )
        for suffix,stage in roles:
            if filename.endswith(suffix):return stage
        if filename=="05_0_blind_review.json":return "5.0"
        return None

    def _phase_final_audit(self,task:dict):
        errors=self.store.audit_events(self.task_id)
        for rel,expected in task["report_shas"].items():
            candidates=[self.root/"artifacts"/rel]
            if not candidates[0].exists() or digest_file(candidates[0])!=expected:
                errors.append(f"report artifact missing/changed: {rel}")
        for record in task["audit_history"]:
            if record["verdict"]!="COMPLIANT":
                # Historic violations are retained in log; only unresolved latest
                # stage audit is relevant to final compliance. This is checked below.
                pass
        latest={}
        for record in task["audit_history"]:
            latest[record["stage"]+":"+record["role"]]=record
        errors.extend(f"unresolved audit: {k}" for k,v in latest.items() if v["verdict"]!="COMPLIANT")
        if task["mode"]=="integration" and not any(x["stage"]=="5.0" for x in task["audit_history"]):
            errors.append("missing real A2A audit")
        path=self.root/"artifacts"/"PROCESS_COMPLIANCE_REPORT.md"
        content="# P1 PROCESS COMPLIANCE REPORT\n\n"
        content+=f"Task: `{task['task_id']}`\n\nMode: `{task['mode']}`\n\n"
        content+="Verdict: **"+("NON_COMPLIANT" if errors else "COMPLIANT")+"**\n\n"
        content+="## Audited stages\n\n"
        for record in task["audit_history"]:
            content+=f"- {record['stage']} / {record['role']}: {record['verdict']}\n"
        if errors:
            content+="\n## Findings\n\n"+"\n".join("- "+s for s in errors)+"\n"
        if task["mode"]=="offline_fixture":
            content+="\n**SIMULATION ONLY: not evidence of real model execution or production readiness.**\n"
        atomic_write(path,content)
        task["report_shas"][path.name]=digest_file(path)
        self._audit_record(task,"5.85",{"verdict":"NON_COMPLIANT" if errors else "COMPLIANT","errors":errors,"warnings":[]},"pro_audit")
        if errors:
            # A damaged journal/approval cannot be repaired by model reruns.
            if any(e.startswith("event ") or e=="journal empty" for e in errors):
                self._block(task,"immutable event journal invalid: "+"; ".join(errors),"BLOCKED");return
            origins=[]
            order={s:i for i,s in enumerate(("0.2","1","2","3+4","4.5","5.0","5.1","5.2","5.3","5.85"))}
            for err in errors:
                if err.startswith("report artifact missing/changed: "):
                    origin=self._replay_origin(err.split(": ",1)[1])
                    if origin:origins.append(origin)
                elif err.startswith("unresolved audit:"):
                    marker=err.split(": ",1)[1].split(":",1)[0]
                    origins.append("3+4" if marker in {"3","4"} else marker)
            if not origins:
                self._block(task,"cannot safely identify origin of compliance discrepancy: "+"; ".join(errors),"BLOCKED");return
            earliest=min(origins,key=lambda x:order.get(x,999))
            self._violation(task,earliest,errors);return
        task["status"]="WAITING_GATE_5_9"
        task["stage"]="gate5.9"
        self._save(task,"gate59_reached",{"report":str(path),"mode":task["mode"]})

    def approve_spec(self,actor:str,approval_id:str,expected_sha:str):
        with exclusive_lock(self.root/".task.lock"):
            task=self.store.load(self.task_id)
            require_snapshot(task,self.root)
            if task["stage"]!="gate0.2" or task["status"]!="WAITING_APPROVAL":
                raise PipelineError("Gate 0.2 is not awaiting approval")
            if not actor.strip() or not approval_id.strip():
                raise PipelineError("actor and approval ID required")
            got=digest_file(self.root/"snapshots"/"TASK_SPEC.md")
            if got!=expected_sha or got!=task.get("proposed_spec_sha256"):
                raise PipelineError("Gate 0.2 spec SHA mismatch")
            task["spec_sha256"]=got
            self._save(task,"gate02_approved",{"actor":actor,"approval_id":approval_id,"spec_sha256":got})
            self._advance(task,"1")

    def run(self,max_steps:int=40)->dict:
        with exclusive_lock(self.root/".task.lock"):
            task=self.store.load(self.task_id)
            if task["status"]=="RUNNING":
                self._block(task,"previous phase was RUNNING without a confirmed terminal result; reconcile before redispatch","NEEDS_RECONCILIATION")
                return self.status()
            for _ in range(max_steps):
                if task["stage"] not in STEP_STAGES:raise PipelineError("unrecognized stage")
                if task["status"] in ("WAITING_APPROVAL","WAITING_GATE_5_9","BLOCKED","FAILED","NEEDS_RECONCILIATION","WAITING_CLARIFICATION","WAITING_EXTERNAL"):
                    break
                if self.store.running(self.task_id):
                    self._block(task,"ambiguous RUNNING invocation; reconcile externally before resume", "NEEDS_RECONCILIATION");break
                try:
                    require_snapshot(task,self.root)
                    stage=task["stage"]
                    task["status"]="RUNNING"
                    self._save(task,"phase_enter",{"stage":stage})
                    if stage=="0.2":
                        self._phase_role(task,stage,"planner",1,"gate0.2",{"PASS"})
                    elif stage=="1":self._phase_worktree(task)
                    elif stage=="2":self._phase_role(task,stage,"worker",task["round_a"],"3+4",{"PASS"})
                    elif stage=="3+4":self._review_pair(task)
                    elif stage=="4.5":self._phase_role(task,stage,"tester_gate_a",task["round_a"],"5.0",{"GATE_A_PASS","PASS"},"a")
                    elif stage=="5.0":self._phase_a2a(task)
                    elif stage=="5.1":self._phase_role(task,stage,"worker_remediation",task["round_b"],"5.2",{"PASS"})
                    elif stage=="5.2":self._phase_role(task,stage,"tester_gate_b",task["round_b"],"5.3",{"GATE_B_PASS","PASS"},"b")
                    elif stage=="5.3":self._phase_role(task,stage,"arbitrator",task["round_b"],"5.85",{"PASS"},"b")
                    elif stage=="5.85":self._phase_final_audit(task)
                    else:break
                except Exception as exc:
                    self._block(task,f"stage execution error: {type(exc).__name__}: {exc}","NEEDS_RECONCILIATION")
                    break
                if task["status"]=="WAITING_EXTERNAL":break
            else:
                if task["status"]=="RUNNING":
                    task["status"]="READY"
                    self._save(task,"cooperative_yield")
            return self.status()

    def resume(self,max_steps:int=40)->dict:
        with exclusive_lock(self.root/".task.lock"):
            task=self.store.load(self.task_id)
            if task["status"]=="WAITING_EXTERNAL" and task["stage"]=="5.0":
                task["status"]="READY"
                self._save(task,"external_poll_resumed")
            elif task["status"]!="READY":
                raise PipelineError("resume not allowed; outstanding approval, reconciliation, failure or manual decision")
        return self.run(max_steps=max_steps)

    def reconcile(self)->dict:
        task=self.store.load(self.task_id)
        return {"status":self.status(),"unfinished_invocations":self.store.running(self.task_id),
                "event_chain_errors":self.store.audit_events(self.task_id),
                "warning":"Read-only report. Ambiguous invocations are never auto-cleared/replayed."}

    def export_report(self)->str:
        task=self.store.load(self.task_id)
        if task["status"]!="WAITING_GATE_5_9":
            raise PipelineError("final report unavailable before Gate 5.9")
        reports=[self.root/"artifacts"/"PROCESS_COMPLIANCE_REPORT.md"]
        files=list((self.root/"artifacts").glob("*_5_3_arbitrator.md"))
        if not files:raise PipelineError("arbitrator report missing")
        reports=[files[-1],*reports]
        return "\n\n===== FULL DOCUMENT BOUNDARY =====\n\n".join(path.read_text(encoding="utf-8") for path in reports)
