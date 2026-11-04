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
from .gitops import git, head, inventory, inventory_hash, create_worktree, clean, index_digest, test_path, test_commit_transition
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
    if task.get("adapter_sha256"):
        if digest_file(snap/"adapters.json")!=task["adapter_sha256"]:
            raise PipelineError("frozen adapter configuration tampering")
    if task.get("safety_sha256"):
        if digest_file(snap/"safety.json")!=task["safety_sha256"]:
            raise PipelineError("frozen safety manifest tampering")
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
    if (home/"state.sqlite").exists() or (home/"snapshots").exists():
        raise ContractError("task home already initialized; incomplete initialization requires explicit cleanup")
    project_root=project_root.resolve()
    if not clean(project_root):
        raise ContractError("project_root must be a clean Git repository")
    # Planner reads project_root. Refuse a different base commit that it did not read.
    base_commit=git(project_root,"rev-parse","--verify",f"{base_ref}^{{commit}}")
    if base_commit!=head(project_root):
        raise ContractError("Planner source HEAD must equal resolved worktree base commit")
    adapter_bytes=adapter_config.read_bytes() if adapter_config else None
    safety_bytes=safety_manifest.read_bytes() if safety_manifest else None
    if safety_bytes is not None:
        try:safety_data=json.loads(safety_bytes)
        except (ValueError,UnicodeError) as exc:
            raise ContractError("invalid safety manifest JSON") from exc
        if (not isinstance(safety_data,dict) or
            safety_data.get("live_side_effects_disabled") is not True or
            not safety_data.get("reviewed_by")):
            raise ContractError("safety manifest missing reviewed side-effect guard")
    root=home
    snapshots=snapshot_inputs(root,intent,matrix,approval,souls)
    try:
        if adapter_bytes is not None:
            atomic_write(root/"snapshots"/"adapters.json",adapter_bytes)
        if safety_bytes is not None:
            atomic_write(root/"snapshots"/"safety.json",safety_bytes)
        task={"task_id":task_id,"mode":mode,"stage":"0.2","status":"READY",
              "project_root":str(project_root),"worktree_path":str(worktree_path.resolve()),
              "base_ref":base_ref,"base_commit_sha":base_commit,
              "fixture_dir":str(fixture_dir.resolve()) if fixture_dir else None,
              "adapter_config":str(root/"snapshots"/"adapters.json") if adapter_bytes else None,
              "adapter_sha256":digest_file(root/"snapshots"/"adapters.json") if adapter_bytes else None,
              "safety_manifest":str(root/"snapshots"/"safety.json") if safety_bytes else None,
              "safety_sha256":digest_file(root/"snapshots"/"safety.json") if safety_bytes else None,
              "spec_sha256":None,"commit_sha":None,"review_commit_sha":None,
              "round_a":1,"round_b":1,"compliance_retraces":0,
              "a2a_job_id":None,"a2a_submitted_commit":None,
              "report_shas":{},"audit_shas":{},"audit_history":[],"last_error":None,
              "final_arbitration_report":None,"arbitration_case_sha256":None,
              "protected_tests":{},"phase_input_commits":{},**snapshots}
        store=Store(home/"state.sqlite")
        try:store.create(task)
        finally:store.close()
        return task
    except Exception:
        # Task directory was absent on entry. If initialization fails, it is
        # not eligible for resume. Best-effort remove only this attempt's DB.
        shutil.rmtree(home/"snapshots",ignore_errors=True)
        for suffix in ("","-wal","-shm"):
            (home/("state.sqlite"+suffix)).unlink(missing_ok=True)
        raise


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
        task["audit_shas"][path.name]=digest_file(path)
        self._save(task,"step_audited",rec)
        return rec

    def _violation(self,task:dict,stage:str,errors:list[str]):
        if not errors:return False
        if task["compliance_retraces"]>=2:
            self._block(task,"compliance retrace cap exceeded: "+"; ".join(errors),"FAILED")
            return True
        # Repeating a role against a changed source baseline is not a safe repair.
        # It requires explicit reconciliation, not an automatic second LLM call.
        if stage not in ("0.2","1") and task.get("commit_sha"):
            repo=Path(task["worktree_path"])
            historical=task.get("phase_input_commits",{}).get(stage)
            if (historical is None or not repo.exists() or
                head(repo)!=historical or head(repo)!=task["commit_sha"] or not clean(repo)):
                self._block(task,"compliance replay unsafe: historical Git input baseline changed/dirty", "NEEDS_RECONCILIATION")
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
        before_head=head(workdir)
        expected=task["base_commit_sha"] if stage=="0.2" else task.get("commit_sha")
        if expected and before_head!=expected:
            raise PipelineError(f"role {role}: Git HEAD differs from recorded input commit; reconcile")
        if not clean(workdir):
            raise PipelineError(f"role {role}: worktree not clean before execution; reconcile")
        before=inventory(workdir)
        before_index=index_digest(workdir)
        hashes=read_json(task_root/"snapshots"/"soul_hashes.json")
        inp=sha256(canonical({"task_id":task["task_id"],"stage":stage,"role":role,
                    "matrix_sha256":task["matrix_sha256"],"intent_sha256":task["intent_sha256"],
                    "spec_sha256":task["spec_sha256"],"commit_sha":before_head,
                    "case_sha256":task.get("arbitration_case_sha256"),
                    "soul_sha256":hashes[role]}).encode())
        run_id=self.store.start_run(task["task_id"],stage,role,inp,{"before_head":before_head,
              "before_index":before_index,"before_digest":inventory_hash(before)})
        # Write-before-dispatch + RUNNING row: crashes cannot silently redispatch.
        envelope=invoke(task,role,stage,task_root,attempt,run_id)
        after=inventory(workdir)
        after_head=head(workdir)
        after_index=index_digest(workdir)
        audit=audit_role(task,role,stage,envelope,before,after,before_head,after_head,
                         hashes[role],task_root,before_index,after_index)
        if role in ("worker","worker_remediation"):
            if not clean(workdir):
                audit["errors"].append("Worker left uncommitted or staged changes")
            for file,expected_sha in task.get("protected_tests",{}).items():
                if after.get(file)!=expected_sha:
                    audit["errors"].append(f"Worker changed/deleted protected Tester exam: {file}")
        if role in ("tester_gate_a","tester_gate_b"):
            if not clean(workdir):
                audit["errors"].append("Tester left uncommitted or staged changes")
            valid,delta=test_commit_transition(workdir,before_head,after_head)
            if not valid:
                audit["errors"].append(f"Tester changed HEAD outside additive test-only commits: {delta}")
            # Gate A preserves baseline tests and the new challenge; Gate B may
            # only ADD tests. Do not accept a changed/deleted pre-existing exam.
            if not audit["errors"]:
                task["protected_tests"].update({k:v for k,v in after.items() if test_path(k)})
        if audit["errors"]:
            audit["verdict"]="NON_COMPLIANT"
        payload=envelope["payload"]
        output_sha=sha256(canonical(payload).encode())
        stdout=task_root/"logs"/f"{run_id}.stdout.json" if envelope["mode"]=="fixture" else task_root/"logs"/f"{run_id}.stdout.bin"
        stderr=task_root/"logs"/f"{run_id}.stderr.bin"
        if not stdout.is_file() or not stderr.is_file():
            audit["errors"].append("raw invocation logs missing")
            audit["verdict"]="NON_COMPLIANT"
        log_info={"stdout":stdout.name,"stdout_sha256":digest_file(stdout) if stdout.is_file() else None,
                  "stderr":stderr.name,"stderr_sha256":digest_file(stderr) if stderr.is_file() else None}
        report_entry=None
        if isinstance(payload.get("report"),str) and payload["report"].strip():
            name=f"{run_id:04d}_{stage.replace('.','_')}_{role}.md"
            report_path=task_root/"artifacts"/name
            atomic_write(report_path,payload["report"])
            report_entry={"name":name,"sha256":digest_file(report_path)}
            for old in list(task["report_shas"]):
                if old.endswith("_"+role+".md"):
                    del task["report_shas"][old]
            task["report_shas"][name]=report_entry["sha256"]
        details={"role":role,"stage":stage,"run_id":run_id,"before_head":before_head,
                 "after_head":after_head,"before_index":before_index,"after_index":after_index,
                 "before_digest":inventory_hash(before),"after_digest":inventory_hash(after),
                 "invocation":{key:envelope[key] for key in
                      ("mode","exit_code","stdout_sha256","stderr_sha256","command","assignment")},
                 "logs":log_info,"report":report_entry,"audit":audit,"payload":payload}
        self.store.finish_run(task["task_id"],run_id,"COMPLETED",output_sha,details)
        return payload,audit

    def _review_pair(self,task:dict)->None:
        repo=Path(task["worktree_path"])
        expected_head=head(repo)
        if expected_head!=task["commit_sha"] or not clean(repo):
            self._block(task,"review pair Git baseline mismatch/dirty", "NEEDS_RECONCILIATION");return
        attempt=task["round_a"]
        def one(role:str,stage:str):
            db=Store(self.root/"state.sqlite")
            try:
                worker=Pipeline.__new__(Pipeline)
                worker.root=self.root;worker.store=db;worker.task_id=self.task_id
                return worker._run_role(dict(task),stage,role,attempt)
            finally:db.close()
        results={};errors=[]
        with ThreadPoolExecutor(max_workers=2,thread_name_prefix="p1-review") as pool:
            futures={role:pool.submit(one,role,stage) for role,stage in
                     (("spec_reviewer","3"),("quality_reviewer","4"))}
            for role,future in futures.items():
                try:results[role]=future.result()
                except Exception as exc:errors.append(f"{role}: {exc}")
        if errors:
            self._block(task,"parallel reviewer execution uncertain: "+"; ".join(errors),"NEEDS_RECONCILIATION");return
        source_changed=head(repo)!=expected_head or not clean(repo)
        # Register reports from exact persisted run IDs, never a glob or a later file.
        for role in ("spec_reviewer","quality_reviewer"):
            candidates=[r for r in self.store.results(self.task_id)
                        if r["role"]==role and r["stage"] in ("3","4") and r["status"]=="COMPLETED"]
            if candidates:
                detail=json.loads(candidates[-1]["details"])
                report=detail.get("report")
                if report:task["report_shas"][report["name"]]=report["sha256"]
        # Both independent audit records must be retained even if first fails.
        violations=[]
        for role,(payload,audit) in results.items():
            self._audit_record(task,"3" if role=="spec_reviewer" else "4",audit,role)
            violations.extend(f"{role}: {e}" for e in audit["errors"])
        if source_changed:
            self._block(task,"review pair changed source/index; both audits retained", "NEEDS_RECONCILIATION");return
        if violations:
            self._violation(task,"3+4",violations);return
        verdicts={role:res[0].get("verdict") for role,res in results.items()}
        unresolved=any(any(isinstance(f,dict) and f.get("category")=="QUESTION"
                           and f.get("resolved") is not True for f in res[0].get("findings",[]))
                       for res in results.values())
        if unresolved or any(v in ("QUESTION","NEEDS_SPECIALIST") for v in verdicts.values()):
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

    def _prepare_arbitration_case(self,task:dict)->None:
        # The arbitrator must be given a fixed case manifest that P1 can verify.
        required=("05_0_blind_review.json","_worker_remediation.md","_tester_gate_b.md")
        for suffix in required:
            if not any(name.endswith(suffix) for name in task["report_shas"]):
                raise PipelineError(f"arbitration case incomplete: {suffix}")
        documents={name:sha for name,sha in task["report_shas"].items()
                   if name!="ARBITRATION_CASE.json" and name!="PROCESS_COMPLIANCE_REPORT.md"}
        case={"task_id":task["task_id"],"commit_sha":task["commit_sha"],
              "spec_sha256":task["spec_sha256"],"matrix_sha256":task["matrix_sha256"],
              "review_commit_sha":task["review_commit_sha"],"evidence":documents}
        output=self.root/"artifacts"/"ARBITRATION_CASE.json"
        atomic_write(output,canonical(case)+"\n")
        task["arbitration_case_sha256"]=digest_file(output)
        task["report_shas"][output.name]=task["arbitration_case_sha256"]

    def _phase_role(self,task:dict,stage:str,role:str,attempt:int,next_stage:str,passes:set[str],retry:str|None=None):
        payload,audit=self._run_role(task,stage,role,attempt)
        self._audit_record(task,stage,audit,role)
        if self._violation(task,stage,audit["errors"]):return
        verdict=payload.get("verdict")
        if role in ("tester_gate_a","tester_gate_b"):
            # Commit from test-only descendant is now the precise downstream
            # baseline; test-only ancestry and clean tree verified in _run_role.
            task["commit_sha"]=head(Path(task["worktree_path"]))
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
            task["proposed_spec_sha256"]=digest_file(self.root/"snapshots"/"TASK_SPEC.md")
            self._advance(task,"gate0.2");task["status"]="WAITING_APPROVAL";self._save(task,"gate02_wait")
            return
        if stage in ("2","5.1"):
            new_commit=head(Path(task["worktree_path"]))
            if stage=="5.1" and new_commit==task.get("commit_sha"):
                reason=payload.get("no_op_reason")
                if payload.get("no_op") is not True or not isinstance(reason,str) or not reason.strip():
                    self._violation(task,stage,["no-op remediation requires structured no_op=true and nonempty no_op_reason"]);return
                # A no-op is permissible only when upstream blind reports have
                # no actionable blocking finding. Otherwise new code evidence
                # or explicit adjudication is required, not a keyword in prose.
                collection=read_json(self.root/"artifacts"/"05_0_blind_review.json")
                actionables=any(r.get("verdict")=="REQUEST_CHANGES" or any(
                    isinstance(f,dict) and f.get("severity") in ("P0","P1","BLOCKER","IMPORTANT")
                    for f in r.get("findings",[])) for r in collection.get("reports",[]))
                if actionables:
                    self._block(task,"no-op prohibited with unresolved actionable blind findings", "WAITING_CLARIFICATION");return
            task["commit_sha"]=new_commit
            if stage=="2":task["review_commit_sha"]=new_commit
        if stage=="5.2":
            checks=payload.get("checks")
            if not isinstance(checks,dict) or any(checks.get(x)!="PASS" for x in ("smoke","canary","regression")):
                self._retry_b(task,"Gate B test evidence incomplete");return
            self._prepare_arbitration_case(task)
        if stage=="5.3":
            matches=[name for name in task["report_shas"] if name.endswith("_arbitrator.md")]
            if len(matches)!=1:
                self._block(task,"missing or ambiguous current arbitrator report","BLOCKED");return
            task["final_arbitration_report"]=matches[0]
        self._advance(task,next_stage)

    def _phase_worktree(self,task:dict):
        if task.get("safety_manifest"):
            safety=read_json(Path(task["safety_manifest"]))
            if safety.get("live_side_effects_disabled") is not True or not safety.get("reviewed_by"):
                self._block(task,"side effects manifest missing safety review");return
        elif task["mode"]=="integration":
            self._block(task,"side effects manifest mandatory for integration mode");return
        if head(Path(task["project_root"]))!=task["base_commit_sha"]:
            self._block(task,"Planner Git baseline moved before worktree creation","NEEDS_RECONCILIATION");return
        detail=create_worktree(Path(task["project_root"]),Path(task["worktree_path"]),task["task_id"],task["base_commit_sha"],task["mode"]=="offline_fixture")
        task["commit_sha"]=detail["commit_sha"]
        self._audit_record(task,"1",{"verdict":"COMPLIANT","errors":[],"warnings": ["side-effect control is an integration prerequisite"] if task["mode"]=="offline_fixture" else []},"orchestrator")
        self._advance(task,"2")

    def _phase_a2a(self,task:dict):
        matrix=read_json(self.root/"snapshots"/"matrix.json")
        if not task["a2a_job_id"]:
            request={"task_id":task["task_id"],"commit_sha":task["commit_sha"],
                     "matrix_sha256":task["matrix_sha256"],"spec_sha256":task["spec_sha256"],
                     "souls_sha256":task["souls_sha256"],
                     "blind_roles":{r:matrix["roles"][r] for r in ("blind_a","blind_b","blind_c")},
                     "idempotency_key":f"{task['task_id']}:5.0:{task['commit_sha']}"}
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
        state=status.get("state")
        if state in ("FAILED","CANCELLED","REJECTED","EXPIRED"):
            detail={key:str(status.get(key,""))[:350] for key in ("state","code","reason") if key in status}
            self._save(task,"a2a_terminal",detail)
            self._block(task,f"A2A terminal state: {state}","BLOCKED");return
        if state not in ("COMPLETED","QUORUM_MET"):
            if state not in ("SUBMITTED","QUEUED","PENDING","RUNNING","WAITING","IN_PROGRESS"):
                self._block(task,f"A2A unknown state: {state}","NEEDS_RECONCILIATION");return
            task["status"]="WAITING_EXTERNAL"
            self._save(task,"a2a_wait",{"state":state});return
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
        verdicts={r.get("verdict") for r in collection["reports"] if isinstance(r,dict)}
        if verdicts & {"QUESTION","NEEDS_SPECIALIST"}:
            self._block(task,"A2A review needs clarification/specialist","WAITING_CLARIFICATION");return
        self._advance(task,"5.1")

    def _gate02_errors(self,task:dict)->list[str]:
        if task["stage"] in ("0.2","gate0.2"):
            return []
        errors=[]
        if not task.get("spec_sha256"):
            return ["Gate 0.2 approved TASK_SPEC SHA missing"]
        events=self.store.db.execute("SELECT kind,payload FROM events WHERE task_id=? ORDER BY id",
                                     (self.task_id,)).fetchall()
        approvals=[]
        for row in events:
            if row["kind"]=="gate02_approved":
                try:approvals.append(json.loads(row["payload"]))
                except ValueError:pass
        if not any(x.get("spec_sha256")==task["spec_sha256"] and x.get("actor") and x.get("approval_id")
                   for x in approvals):
            errors.append("Gate 0.2 approval event missing/mismatched")
        return errors

    def verify_evidence(self)->dict:
        task=self.store.load(self.task_id)
        problems=self.store.audit_events(self.task_id)
        problems.extend(self._gate02_errors(task))
        try:
            require_snapshot(task,self.root)
        except (PipelineError,ContractError,OSError) as exc:
            problems.append(str(exc))
        for name,expected in task.get("report_shas",{}).items():
            path=self.root/"artifacts"/name
            if not path.is_file() or digest_file(path)!=expected:
                problems.append(f"artifact SHA mismatch: {name}")
        if task.get("protected_tests"):
            try:
                current_files=inventory(Path(task["worktree_path"]))
                for name,expected in task["protected_tests"].items():
                    if current_files.get(name)!=expected:
                        problems.append(f"protected Tester exam missing/changed: {name}")
            except (OSError,ContractError) as exc:
                problems.append(f"protected exam inspection unavailable: {exc}")
        for name,expected in task.get("audit_shas",{}).items():
            path=self.root/"audit_evidence"/name
            if not path.is_file() or digest_file(path)!=expected:
                problems.append(f"step audit SHA mismatch: {name}")
        for run in self.store.results(self.task_id):
            if run["status"]!="COMPLETED":
                problems.append(f"unverified run status: {run['id']} {run['status']}")
                continue
            try:
                detail=json.loads(run["details"])
                if sha256(canonical(detail["payload"]).encode())!=run["output_sha"]:
                    problems.append(f"run output SHA mismatch: {run['id']}")
                invocation=detail["invocation"]
                for stream in ("stdout","stderr"):
                    info=detail["logs"]
                    rel=info[stream]
                    if Path(rel).name!=rel or not rel.startswith(f"{run['id']}."):
                        problems.append(f"unsafe run log reference: {run['id']} {stream}")
                        continue
                    path=self.root/"logs"/rel
                    expected=info[f"{stream}_sha256"]
                    if not path.is_file() or digest_file(path)!=expected or invocation[f"{stream}_sha256"]!=expected:
                        problems.append(f"raw role log SHA mismatch: {run['id']} {stream}")
                entry=detail.get("report")
                if entry:
                    path=self.root/"artifacts"/entry["name"]
                    if not path.is_file() or digest_file(path)!=entry["sha256"]:
                        problems.append(f"run report SHA mismatch: {run['id']}")
            except (KeyError,TypeError,ValueError,OSError) as exc:
                problems.append(f"malformed run record: {run['id']}: {exc}")
        if task["stage"]=="gate5.9" and task["status"]=="WAITING_GATE_5_9":
            repo=Path(task["worktree_path"])
            try:
                if head(repo)!=task["commit_sha"] or not clean(repo):
                    problems.append("Gate 5.9 Git commit/worktree mismatch")
            except (ContractError,OSError) as exc:
                problems.append(f"Gate 5.9 Git state unavailable: {exc}")
            current=task.get("final_arbitration_report")
            if not current or current not in task.get("report_shas",{}):
                problems.append("Gate 5.9 arbitrator report not registered")
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
        # Ignore only the *prior* final report when recomputing 5.85 after a
        # legal replay; all underlying stage reports remain independently checked.
        saved_final=task["report_shas"].pop("PROCESS_COMPLIANCE_REPORT.md",None)
        evidence=self.verify_evidence()
        errors=list(evidence["errors"])
        for rel,expected in task["report_shas"].items():
            path=self.root/"artifacts"/rel
            if not path.exists() or digest_file(path)!=expected:
                errors.append(f"report artifact missing/changed: {rel}")
        for record in task["audit_history"]:
            if record["verdict"]!="COMPLIANT":
                # Historic violations are retained in log; only unresolved latest
                # stage audit is relevant to final compliance. This is checked below.
                pass
        latest={}
        for record in task["audit_history"]:
            latest[record["stage"]+":"+record["role"]]=record
        errors.extend(f"unresolved audit: {k}" for k,v in latest.items()
                      if v["verdict"]!="COMPLIANT" and k!="5.85:pro_audit")
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
            if any(e.startswith("event ") or e=="journal empty" or
                   e.startswith("task row") or e.startswith("task state journal") for e in errors):
                self._block(task,"immutable event journal invalid: "+"; ".join(errors),"BLOCKED");return
            origins=[]
            order={s:i for i,s in enumerate(("0.2","1","2","3+4","4.5","5.0","5.1","5.2","5.3","5.85"))}
            for err in errors:
                if err.startswith(("report artifact missing/changed: ","artifact SHA mismatch: ")):
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
            integrity=self.store.audit_events(self.task_id)
            if integrity:
                raise PipelineError("approval journal integrity failure: "+"; ".join(integrity))
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
            integrity=self.store.audit_events(self.task_id)+self._gate02_errors(task)
            if integrity:
                # Never rewrite a tampered task row: preserve forensic journal.
                result=self.status()
                result["status"]="BLOCKED"
                result["last_error"]="pre-dispatch integrity failure: "+"; ".join(integrity)
                return result
            if task["mode"]=="integration":
                # Contract for real signed provider, test and A2A evidence is not
                # available in P1 v0.2: no real agent calls or apparent green gates.
                self._block(task,"integration is NOT_VERIFIED; trusted runner and A2A attestation unavailable", "BLOCKED")
                return self.status()
            if task["status"]=="RUNNING":
                self._block(task,"previous phase was RUNNING without a confirmed terminal result; reconcile before redispatch","NEEDS_RECONCILIATION")
                return self.status()
            for _ in range(max_steps):
                if task["stage"] not in STEP_STAGES:raise PipelineError("unrecognized stage")
                if task["status"] in ("WAITING_APPROVAL","WAITING_GATE_5_9","BLOCKED","FAILED","NEEDS_RECONCILIATION","WAITING_CLARIFICATION","WAITING_EXTERNAL"):
                    break
                if self.store.running(self.task_id):
                    self._block(task,"ambiguous RUNNING invocation; reconcile externally before resume", "NEEDS_RECONCILIATION");break
                integrity=self.store.audit_events(self.task_id)+self._gate02_errors(task)
                if integrity:
                    # A phase that finds a broken chain must not rewrite the row.
                    result=self.status()
                    result["status"]="BLOCKED"
                    result["last_error"]="pre-phase integrity failure: "+"; ".join(integrity)
                    return result
                try:
                    require_snapshot(task,self.root)
                    stage=task["stage"]
                    if stage not in ("0.2","gate0.2","1","5.85","gate5.9") and task.get("commit_sha"):
                        task.setdefault("phase_input_commits",{})[stage]=task["commit_sha"]
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
            # Do not seal an untrusted task row with a new valid journal event.
            problems=self.store.audit_events(self.task_id)+self._gate02_errors(task)
            if problems:
                raise PipelineError("resume preflight integrity failure: "+"; ".join(problems))
            require_snapshot(task,self.root)
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
        # No glob selection. Read the two exact registered artifacts once and
        # verify those SAME bytes under the task process lock.
        with exclusive_lock(self.root/".task.lock"):
            task=self.store.load(self.task_id)
            if task["status"]!="WAITING_GATE_5_9" or task["stage"]!="gate5.9":
                raise PipelineError("final report unavailable before Gate 5.9")
            verification=self.verify_evidence()
            if verification["errors"]:
                raise PipelineError("Gate 5.9 evidence invalid: "+"; ".join(verification["errors"]))
            arbitration=task.get("final_arbitration_report")
            final="PROCESS_COMPLIANCE_REPORT.md"
            if not arbitration or arbitration not in task["report_shas"] or final not in task["report_shas"]:
                raise PipelineError("final reports not registered")
            documents=[]
            for name in (arbitration,final):
                path=self.root/"artifacts"/name
                content=path.read_bytes()
                if sha256(content)!=task["report_shas"][name]:
                    raise PipelineError(f"final document tampered: {name}")
                documents.append(content.decode("utf-8"))
            return "\n\n===== FULL DOCUMENT BOUNDARY =====\n\n".join(documents)
