"""Round-002 FAIL findings converted to regression checks; all test work isolated."""
from __future__ import annotations
import json
import shutil
import sys
import subprocess
from pathlib import Path
import pytest
from p1.contracts import ContractError, canonical, digest_file, read_json, atomic_write
from p1.gitops import git, head, clean, hidden_index_flags, index_digest
from p1.workflow import Pipeline, PipelineError, initialize
from test_pipeline import start, approve, write_fixture


def commit(repo:Path, message:str):
    git(repo,"add","-A")
    git(repo,"-c","user.name=P1 Tests","-c","user.email=fixture@example.invalid","commit","-m",message)


@pytest.mark.parametrize("flag",["--assume-unchanged","--skip-worktree"])
def test_round2_hidden_git_flags_cannot_hide_content_changes(scenario, flag):
    s=scenario;repo=s["project"]
    p=repo/"main.py"
    p.write_text("print('changed')\n")
    git(repo,"update-index",flag,"main.py")
    assert hidden_index_flags(repo)
    assert not clean(repo)
    with pytest.raises(ContractError,match="clean Git"):
        s["init"]()


def test_round2_test_commit_must_only_add_new_test_file(scenario):
    from p1.gitops import test_commit_transition
    s=scenario;repo=s["project"]
    old=head(repo)
    (repo/"tests"/"test_main.py").write_text("def test_ok(): assert False\n")
    commit(repo,"weaken original exam")
    assert test_commit_transition(repo,old,head(repo))[0] is False


@pytest.mark.parametrize("stage",["tester_gate_a","tester_gate_b"])
def test_round2_tester_cannot_rewrite_or_delete_baseline_exam(scenario,monkeypatch,stage):
    s=scenario
    import p1.workflow as wf
    original=wf.invoke
    def adversarial(task,role,phase,root,attempt,run_id):
        result=original(task,role,phase,root,attempt,run_id)
        if role==stage:
            repo=Path(task["worktree_path"])
            t=repo/"tests"/"test_main.py"
            if stage=="tester_gate_a":
                t.unlink()
            else:
                t.write_text("def test_ok(): assert True # weakened\n")
            commit(repo,"tester changed existing exam")
        return result
    monkeypatch.setattr(wf,"invoke",adversarial)
    p=start(s)
    try:
        out=approve(p,s)
        assert out["status"]!="WAITING_GATE_5_9",out
        assert any("Tester" in a["errors"][0] or a["verdict"]=="NON_COMPLIANT"
                   for a in p.store.load(p.task_id)["audit_history"] if a["role"]==stage)
    finally:p.close()


def test_round2_run_metadata_forgery_is_detected(scenario):
    s=scenario;p=start(s)
    try:
        assert approve(p,s)["status"]=="WAITING_GATE_5_9"
        run=p.store.results(p.task_id)[0]
        details=json.loads(run["details"])
        stdout=s["home"] / "logs" / details["logs"]["stdout"]
        stdout.write_text("CHANGED RAW EXECUTION OUTPUT\n")
        replacement=digest_file(stdout)
        details["logs"]["stdout_sha256"]=replacement
        details["invocation"]["stdout_sha256"]=replacement
        with p.store.db:
            p.store.db.execute("UPDATE runs SET details=? WHERE id=?",(canonical(details),run["id"]))
        issues=p.store.audit_events(p.task_id)
        assert any("run details" in msg for msg in issues),issues
        assert p.verify_evidence()["verdict"]=="NON_COMPLIANT"
        with pytest.raises(PipelineError,match="evidence invalid"):
            p.export_report()
    finally:p.close()


def test_round2_resume_refuses_tampered_a2a_state_without_resealing(scenario,monkeypatch):
    s=scenario
    import p1.workflow as wf
    original=wf.call_adapter
    def fake(task,root,op,request):
        if op=="status":return {"state":"RUNNING"}
        return original(task,root,op,request)
    monkeypatch.setattr(wf,"call_adapter",fake)
    p=start(s)
    try:
        assert approve(p,s)["status"]=="WAITING_EXTERNAL"
        data=p.store.load(p.task_id)
        data["a2a_job_id"]="FORGED-LOCAL-ID"
        with p.store.db:
            p.store.db.execute("UPDATE tasks SET data=? WHERE task_id=?",(canonical(data),p.task_id))
        assert p.store.audit_events(p.task_id)
        count_before=p.store.db.execute("SELECT count(*) FROM events").fetchone()[0]
        with pytest.raises(PipelineError,match="resume preflight integrity failure"):
            p.resume()
        assert p.store.db.execute("SELECT count(*) FROM events").fetchone()[0]==count_before
        assert p.store.audit_events(p.task_id)
    finally:p.close()


def test_round2_noop_does_not_use_keywords(scenario):
    s=scenario
    write_fixture(s,"5_1-worker_remediation.json",{
      "verdict":"PASS", "report":"No modifications required after review.",
      "no_op":True,"no_op_reason":"All reported issues were already resolved in the reviewed revision."})
    p=start(s)
    try:
        assert approve(p,s)["status"]=="WAITING_GATE_5_9"
        assert p.status()["compliance_retraces"]==0
    finally:p.close()


def test_round2_noop_with_only_magic_keywords_is_rejected(scenario):
    s=scenario
    write_fixture(s,"5_1-worker_remediation.json",{
       "verdict":"PASS","report":"no P0 no defect no-op 无需整改"})
    p=start(s)
    try:
        result=approve(p,s)
        assert result["status"]=="FAILED"
        assert "no-op remediation requires structured" in result["last_error"]
    finally:p.close()


def test_round2_replay_after_remediation_commit_requires_reconciliation(scenario,monkeypatch):
    s=scenario
    import p1.workflow as wf
    original=wf.invoke
    def change(task,role,stage,root,attempt,run_id):
        result=original(task,role,stage,root,attempt,run_id)
        if role=="worker_remediation":
            repo=Path(task["worktree_path"])
            (repo/"main.py").write_text("print('remediated')\n")
            commit(repo,"remediation commit")
            write_fixture(s,"5_3-arbitrator.json",{
                "verdict":"PASS","report":"Arbitration approved (fixture)",
                "reviewed_commit":head(repo)})
        return result
    monkeypatch.setattr(wf,"invoke",change)
    p=start(s)
    try:
        p.approve_spec("user","approved",s["spec_sha"])
        assert p.run(max_steps=8)["stage"]=="5.85"
        task=p.store.load(p.task_id)
        assert head(s["worktree"])==task["commit_sha"]
        assert task["phase_input_commits"]["2"]!=task["commit_sha"]
        name=next(x for x in task["report_shas"] if x.endswith("_worker.md"))
        (s["home"]/"artifacts"/name).write_text("INVALIDATED REPORT")
        out=p.run()
        assert out["status"]=="NEEDS_RECONCILIATION",out
        assert out["compliance_retraces"]==0
    finally:p.close()


def test_round2_soul_has_to_match_approval_fingerprint(scenario):
    s=scenario
    soul=Path(__file__).resolve().parents[1]/"souls"
    copy=s["root"] / "different-valid-souls"
    shutil.copytree(soul,copy)
    with (copy/"planner.md").open("a") as stream:
        stream.write("\nThis is a different authorized role behavior instruction.\n")
    with pytest.raises(ContractError,match="Soul SHA mismatch"):
        initialize(s["home"],"TEST-001",s["intent"],s["matrix"],s["gate01"],copy,
                   s["project"],s["worktree"],"offline_fixture",fixture_dir=s["fixtures"])


def test_round2_direct_a2a_call_fails_closed(scenario):
    from p1.a2a import call_adapter
    s=scenario
    task={"mode":"integration","adapter_config":"/tmp/fake.json"}
    with pytest.raises(ContractError,match="NOT_VERIFIED"):
        call_adapter(task,s["home"],"submit",{})


def test_round2_invalid_safety_rejected_at_initialization(scenario):
    s=scenario
    m=s["root"]/"invalid-safety.json"
    m.write_text('{"live_side_effects_disabled":false,"reviewed_by":"nobody"}')
    with pytest.raises(ContractError,match="safety manifest"):
        initialize(s["home"],"TEST-001",s["intent"],s["matrix"],s["gate01"],
                   Path(__file__).resolve().parents[1]/"souls",s["project"],s["worktree"],
                   "offline_fixture",fixture_dir=s["fixtures"],safety_manifest=m)


def test_round2_a2a_collection_rejects_nonstr_report(scenario):
    from p1.a2a import validate_collection
    s=scenario;matrix=read_json(s["matrix"])
    data=read_json(s["fixtures"]/"a2a.json")
    data["reports"][0]["report"]={"fake":"report"}
    task={"mode":"offline_fixture","task_id":"TEST-001","commit_sha":s["commit"],
          "matrix_sha256":digest_file(s["matrix"]),"spec_sha256":s["spec_sha"]}
    assert "A2A report missing/invalid verdict/content" in validate_collection(task,matrix,data,s["home"])


def test_round2_a2a_roles_must_match_frozen_matrix(scenario):
    from p1.a2a import validate_collection
    s=scenario; matrix=read_json(s["matrix"])
    result=read_json(s["fixtures"]/"a2a.json")
    result["blind_roles"]={"blind_a":{"node":"wrong"}}
    task={"mode":"offline_fixture","task_id":"TEST-001","commit_sha":s["commit"],
          "matrix_sha256":digest_file(s["matrix"]),"spec_sha256":s["spec_sha"]}
    assert any("blind_roles" in x for x in validate_collection(task,matrix,result,s["home"]))


def test_round2_partial_db_creation_is_cleaned_before_retry(scenario,monkeypatch):
    import p1.workflow as wf
    s=scenario
    real_store=wf.Store
    def db_open_then_error(path):
        handle=real_store(path)
        handle.close()
        raise OSError("injected storage initialization fault")
    monkeypatch.setattr(wf,"Store",db_open_then_error)
    with pytest.raises(OSError,match="injected storage"):
        s["init"]()
    assert not (s["home"]/"snapshots").exists()
    assert not (s["home"]/"state.sqlite").exists()
    monkeypatch.setattr(wf,"Store",real_store)
    s["init"]()
    assert (s["home"]/"state.sqlite").exists()


def test_round2_executor_refuses_local_adapter_even_when_flag_is_set(scenario,monkeypatch):
    import p1.executor as ex
    s=scenario;s["init"]()
    trusted=s["home"] / "snapshots" / "adapters.json"
    runner=canonical({"harnesses":{"codex":{
        "argv":[sys.executable,"-c","print('\"TRUSTED\"')"],
        "explicitly_authorized":True}}})+"\n"
    atomic_write(trusted,runner)
    task={"mode":"integration","task_id":"TEST-001","project_root":str(s["project"]),
          "worktree_path":str(s["project"]),"adapter_config":"/local/unapproved.json",
          "adapter_sha256":digest_file(trusted)}
    monkeypatch.setattr(ex,"TRUSTED_INTEGRATION_EXECUTION_VERIFIED",True)
    # Even if a stale flag is toggled by mistake, in-process subprocess calls
    # are forbidden until a separately authenticated identity runner exists.
    with pytest.raises(ex.InvocationError,match="separate-identity Agent runner"):
        ex.invoke(task,"planner","0.2",s["home"],1,903)
