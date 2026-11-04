"""Round-001 audit regression probes: fail-closed behavior on disposable repositories.

These do NOT establish trust in live model execution, real 21bao, or remote P0.
"""
from __future__ import annotations
import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from p1 import contracts
from p1.a2a import validate_collection
from p1.audit import audit_role
from p1.contracts import ContractError, canonical, digest_file, read_json
from p1.gitops import git, head, index_digest, inventory
from p1.state import StateError
from p1.workflow import Pipeline, PipelineError, initialize, require_snapshot
from test_pipeline import start, approve, write_fixture


def test_p001_forged_a2a_identity_cannot_pass_real_mode(scenario):
    s=scenario; task={"task_id":"TEST-001","mode":"integration","commit_sha":s["commit"],
                       "matrix_sha256":digest_file(s["matrix"]), "spec_sha256":s["spec_sha"],
                       "souls_sha256":"unknown"}
    r=read_json(s["fixtures"]/"a2a.json")
    for item in r["reports"]:
        item["trusted_physical_identity_attestation"]=True
        item["attestation_reference"]="ANY-CLAIM"
    assert any("NOT_VERIFIED" in e for e in validate_collection(task,read_json(s["matrix"]),r,s["home"]))


@pytest.mark.parametrize("verdict", ["QUESTION", "NEEDS_SPECIALIST"])
def test_p002_a2a_question_stops_pipeline(scenario, verdict):
    s=scenario
    fixture=read_json(s["fixtures"]/"a2a.json")
    fixture["reports"][0]["verdict"]=verdict
    write_fixture(s,"a2a.json",fixture)
    p=start(s)
    try:
        out=approve(p,s)
        assert out["status"]=="WAITING_CLARIFICATION"
        assert out["stage"]=="5.0"
        assert not list((s["home"]/"artifacts").glob("*_arbitrator.md"))
    finally:p.close()


def test_p003_and_021_integration_never_trusts_stub(scenario):
    s=scenario
    adapters=s["root"]/"adapters.json"
    adapters.write_text(canonical({"harnesses":{"codex":{"argv":[sys.executable,"-c","print('PASS')"],
                                                             "explicitly_authorized":True}}})+"\n")
    initialize(s["home"],"TEST-001",s["intent"],s["matrix"],s["gate01"],
               Path(__file__).resolve().parents[1]/"souls",s["project"],s["worktree"],
               "integration", adapter_config=adapters)
    p=Pipeline(s["home"])
    try:
        out=p.run()
        assert out["status"]=="BLOCKED"
        assert "NOT_VERIFIED" in out["last_error"]
        assert p.store.results(p.task_id)==[]
    finally:p.close()


def test_p004_dirty_worker_cannot_get_reviewed(scenario,monkeypatch):
    s=scenario
    import p1.workflow as wf
    original=wf.invoke
    def dirty(task,role,stage,root,attempt,run_id):
        result=original(task,role,stage,root,attempt,run_id)
        if role=="worker":
            (Path(task["worktree_path"])/"main.py").write_text("print('UNCOMMITTED')\n")
        return result
    monkeypatch.setattr(wf,"invoke",dirty)
    p=start(s)
    try:
        out=approve(p,s)
        assert out["status"]=="NEEDS_RECONCILIATION"
        assert not any(x["role"]=="spec_reviewer" for x in p.store.results(p.task_id))
    finally:p.close()


def test_p005_arbitrator_case_is_fixed_and_registered(scenario):
    s=scenario;p=start(s)
    try:
        assert approve(p,s)["status"]=="WAITING_GATE_5_9"
        task=p.store.load(p.task_id)
        case=read_json(s["home"]/"artifacts"/"ARBITRATION_CASE.json")
        assert case["commit_sha"]==task["commit_sha"]
        assert "05_0_blind_review.json" in case["evidence"]
        assert any(k.endswith("_tester_gate_b.md") for k in case["evidence"])
        assert task["arbitration_case_sha256"]==digest_file(s["home"]/"artifacts"/"ARBITRATION_CASE.json")
    finally:p.close()


def test_p007_rogue_final_report_is_not_exported(scenario):
    s=scenario;p=start(s)
    try:
        assert approve(p,s)["status"]=="WAITING_GATE_5_9"
        rogue=s["home"]/"artifacts"/"9999_5_3_arbitrator.md"
        rogue.write_text("UNREGISTERED-INJECTION")
        content=p.export_report()
        assert "UNREGISTERED-INJECTION" not in content
        assert "ARBITRATION REPORT" in content
    finally:p.close()


def test_p007_and_016_tampered_report_or_stdout_blocks_export(scenario):
    s=scenario;p=start(s)
    try:
        assert approve(p,s)["status"]=="WAITING_GATE_5_9"
        log=s["home"]/"logs"/f"{p.store.results(p.task_id)[0]['id']}.stdout.json"
        log.write_text("CORRUPTED LOG",encoding="utf-8")
        assert p.verify_evidence()["verdict"]=="NON_COMPLIANT"
        with pytest.raises(PipelineError,match="evidence invalid"):
            p.export_report()
    finally:p.close()


def test_p008_old_final_audit_does_not_poison_recomputed_final(scenario):
    s=scenario;p=start(s)
    try:
        p.approve_spec("user","approval",s["spec_sha"])
        assert p.run(max_steps=8)["stage"]=="5.85"
        task=p.store.load(p.task_id)
        p._audit_record(task,"5.85",{"verdict":"NON_COMPLIANT","errors":["FIXED OLD ISSUE"],"warnings":[]},"pro_audit")
        assert p.run()["status"]=="WAITING_GATE_5_9"
    finally:p.close()


def test_p009_planner_and_worktree_must_share_base_commit(scenario):
    s=scenario
    root=s["project"]
    (root/"second.txt").write_text("new committed content\n")
    git(root,"add","second.txt")
    git(root,"commit","-m","second")
    with pytest.raises(ContractError,match="Planner source HEAD"):
        initialize(s["home"],"TEST-001",s["intent"],s["matrix"],s["gate01"],
                   Path(__file__).resolve().parents[1]/"souls",root,s["worktree"],
                   "offline_fixture",fixture_dir=s["fixtures"],base_ref="HEAD~1")


def test_p010_local_roles_cannot_run_on_debian_node(scenario):
    s=scenario;matrix=read_json(s["matrix"])
    matrix["roles"]["planner"]["node"]="5bao"
    with pytest.raises(ContractError,match="Windows primary"):
        contracts.validate_matrix(matrix)


def test_p011_blank_soul_contract_is_rejected(scenario):
    s=scenario;tmp=s["root"]/"empty-souls"
    shutil.copytree(Path(__file__).resolve().parents[1]/"souls",tmp)
    (tmp/"planner.md").write_text("")
    with pytest.raises(ContractError,match="invalid or empty Soul"):
        initialize(s["home"],"TEST-001",s["intent"],s["matrix"],s["gate01"],tmp,
                   s["project"],s["worktree"],"offline_fixture",fixture_dir=s["fixtures"])
    assert not (s["home"]/"snapshots").exists()


def test_p012_both_parallel_audit_records_survive_first_violation(scenario):
    s=scenario
    write_fixture(s,"3-spec_reviewer.json",{"verdict":"APPROVE","reviewed_commit":"0"*40,
                                           "spec_sha256":s["spec_sha"],"report":"mismatched commit"})
    p=start(s)
    try:
        approve(p,s)
        hist=p.store.load(p.task_id)["audit_history"]
        assert sum(1 for a in hist if a["role"]=="spec_reviewer")==3
        assert sum(1 for a in hist if a["role"]=="quality_reviewer")==3
    finally:p.close()


def test_p013_failed_run_nonzero_cli_exit(scenario,capsys):
    s=scenario
    write_fixture(s,"3-spec_reviewer.json",{"verdict":"REQUEST_CHANGES","report":"genuine failure",
                                      "reviewed_commit":s["commit"],"spec_sha256":s["spec_sha"]})
    p=start(s)
    try:assert approve(p,s)["status"]=="FAILED"
    finally:p.close()
    from p1.cli import main
    assert main(["run","--home",str(s["home"])])==10


def test_p014_gate01_snapshot_cannot_race_copy(scenario,monkeypatch):
    s=scenario
    true_approval=s["gate01"].read_bytes()
    original=contracts.os.replace
    changed=[False]
    def mutate(src,dst):
        if str(dst).endswith("snapshots") and not changed[0]:
            changed[0]=True
            bad=read_json(s["gate01"]);bad["approved"]=False
            s["gate01"].write_text(canonical(bad)+"\n")
        return original(src,dst)
    monkeypatch.setattr(contracts.os,"replace",mutate)
    s["init"]()
    frozen=(s["home"]/"snapshots"/"gate01.json").read_bytes()
    assert frozen==true_approval
    assert read_json(s["gate01"])["approved"] is False


def test_p015_task_row_edit_cannot_skip_gate02(scenario):
    s=scenario;p=start(s)
    try:
        task=p.store.load(p.task_id)
        task.update(stage="1",status="READY")
        with p.store.db:
            p.store.db.execute("UPDATE tasks SET data=? WHERE task_id=?",(canonical(task),p.task_id))
        assert p.store.audit_events(p.task_id)
        assert p.run()["status"]=="BLOCKED"
        assert not s["worktree"].exists()
    finally:p.close()


def test_p017_index_only_modification_detected(scenario):
    s=scenario;s["init"]();p=Pipeline(s["home"])
    try:
        repo=s["project"]
        before=inventory(repo);index0=index_digest(repo)
        original=(repo/"main.py").read_bytes()
        (repo/"main.py").write_bytes(original+b"# staged\n")
        git(repo,"add","main.py")
        (repo/"main.py").write_bytes(original)
        after=inventory(repo);index1=index_digest(repo)
        assert before==after and index0!=index1
        role="quality_reviewer"
        hashes=read_json(s["home"]/"snapshots"/"soul_hashes.json")
        task=p.store.load(p.task_id)
        envelope={"mode":"fixture","exit_code":0,"payload":{"report":"reviewed","verdict":"APPROVE",
                  "reviewed_commit":head(repo),"spec_sha256":None}}
        result=audit_role(task,role,"4",envelope,before,after,head(repo),head(repo),hashes[role],s["home"],index0,index1)
        assert result["verdict"]=="NON_COMPLIANT"
        assert any("Git index" in e for e in result["errors"])
    finally:p.close()


def test_p019_moved_worktree_head_requires_reconciliation(scenario):
    s=scenario;p=start(s)
    try:
        p.approve_spec("user","approval",s["spec_sha"])
        assert p.run(max_steps=1)["stage"]=="2"
        git(s["worktree"],"-c","user.name=test","-c","user.email=a@b.invalid","commit","--allow-empty","-m","unplanned")
        assert p.run()["status"]=="NEEDS_RECONCILIATION"
        assert not any(r["role"]=="spec_reviewer" for r in p.store.results(p.task_id))
    finally:p.close()


def test_p020_unresolved_question_wins_over_top_level_approve(scenario):
    s=scenario
    write_fixture(s,"3-spec_reviewer.json",{"verdict":"APPROVE","report":"question remains",
                  "reviewed_commit":s["commit"],"spec_sha256":s["spec_sha"],
                  "findings":[{"category":"QUESTION","resolved":False}]})
    p=start(s)
    try:assert approve(p,s)["status"]=="WAITING_CLARIFICATION"
    finally:p.close()


def test_p022_worker_pass_without_report_never_passes(scenario):
    s=scenario
    write_fixture(s,"2-worker.json",{"verdict":"PASS"})
    p=start(s)
    try:
        out=approve(p,s)
        assert out["status"]=="FAILED"
        assert out["compliance_retraces"]==2
    finally:p.close()


def test_p023_duplicate_blind_candidates_rejected(scenario):
    m=read_json(scenario["matrix"])
    m["roles"]["blind_c"]["node"]="5bao"
    m["blind_review"]["candidates"]=["5bao","5bao","9bao"]
    with pytest.raises(ContractError,match="distinct blind"):
        contracts.validate_matrix(m)


def test_p024_terminal_a2a_failed_is_terminal(scenario,monkeypatch):
    s=scenario;import p1.workflow as wf
    def fake(task,root,op,request):
        if op=="submit":return {"job_id":"OFFLINE-REMOTE-JOB"}
        if op=="status":return {"state":"FAILED"}
        raise AssertionError(op)
    monkeypatch.setattr(wf,"call_adapter",fake)
    p=start(s)
    try:
        out=approve(p,s)
        assert out["stage"]=="5.0" and out["status"]=="BLOCKED"
        with pytest.raises(PipelineError,match="resume not allowed"):
            p.resume()
    finally:p.close()


def test_p026_failed_init_does_not_poison_retries(scenario):
    s=scenario;missing=s["root"]/"missing-souls";missing.mkdir()
    with pytest.raises(ContractError):
        initialize(s["home"],"TEST-001",s["intent"],s["matrix"],s["gate01"],missing,
                   s["project"],s["worktree"],"offline_fixture",fixture_dir=s["fixtures"])
    assert not (s["home"]/"snapshots").exists()
    assert s["init"]()["status"]=="READY"


def test_p027_corrupt_event_journal_stops_before_dispatch(scenario):
    s=scenario;p=start(s)
    try:
        p.approve_spec("user","approved",s["spec_sha"])
        with p.store.db:
            p.store.db.execute("UPDATE events SET kind='TAMPERED' WHERE task_id=? AND id=(SELECT min(id) FROM events WHERE task_id=?)",(p.task_id,p.task_id))
        assert p.store.audit_events(p.task_id)
        assert p.run()["status"]=="BLOCKED"
        assert not s["worktree"].exists()
    finally:p.close()


def test_p028_external_adapter_config_cannot_mutate_snapshot(scenario):
    s=scenario;a=s["root"]/"adapters.json";a.write_text('{"harnesses":{}}')
    initialize(s["home"],"TEST-001",s["intent"],s["matrix"],s["gate01"],
               Path(__file__).resolve().parents[1]/"souls",s["project"],s["worktree"],
               "integration",adapter_config=a)
    p=Pipeline(s["home"])
    try:
        task=p.store.load(p.task_id)
        a.write_text('{"harnesses":{"codex":{"argv":["EVIL"]}}}')
        require_snapshot(task,s["home"])
        (s["home"]/"snapshots"/"adapters.json").write_text("{}")
        with pytest.raises(PipelineError,match="adapter configuration tampering"):
            require_snapshot(task,s["home"])
    finally:p.close()


def test_p029_a2a_submit_includes_approved_spec_and_souls(scenario,monkeypatch):
    s=scenario;seen=[];import p1.workflow as wf
    def fake(task,root,op,request):
        if op=="submit":
            seen.append(request)
            return {"job_id":"LOCAL-JOB"}
        if op=="status":return {"state":"RUNNING"}
        raise AssertionError(op)
    monkeypatch.setattr(wf,"call_adapter",fake)
    p=start(s)
    try:
        p.approve_spec("user","approved",s["spec_sha"])
        assert p.run()["status"]=="WAITING_EXTERNAL"
        assert seen[0]["spec_sha256"]==s["spec_sha"]
        assert seen[0]["souls_sha256"]==p.store.load(p.task_id)["souls_sha256"]
        assert set(seen[0]["blind_roles"])=={"blind_a","blind_b","blind_c"}
    finally:p.close()


def test_p006_tester_a_exam_cannot_be_weakened_by_worker(scenario,monkeypatch):
    s=scenario
    from p1 import workflow as wf
    original=wf.invoke
    write_fixture(s,"4_5-tester_gate_a-1.json",{"verdict":"FAIL","report":"new exam catches defect"})
    def modify(task,role,stage,root,attempt,run_id):
        result=original(task,role,stage,root,attempt,run_id)
        repo=Path(task["worktree_path"])
        path=repo/"tests"/"test_adversarial.py"
        if role=="tester_gate_a" and attempt==1:
            path.write_text("def test_adversarial(): assert False\n")
            git(repo,"add","tests/test_adversarial.py")
            git(repo,"commit","-m","tester exam")
        if role=="worker" and attempt==2:
            path.write_text("def test_adversarial(): assert True\n")
            git(repo,"add","tests/test_adversarial.py")
            git(repo,"commit","-m","unauthorized exam weakening")
        return result
    monkeypatch.setattr(wf,"invoke",modify)
    p=start(s)
    try:
        out=approve(p,s)
        assert out["status"]=="NEEDS_RECONCILIATION"
        assert "protected Tester exam" in str(p.store.results(p.task_id)[-1]["details"])
    finally:p.close()


def test_p018_tester_cannot_replace_git_head_with_divergent_commit(scenario,monkeypatch):
    s=scenario
    from p1 import workflow as wf
    original=wf.invoke
    def fake(task,role,stage,root,attempt,run_id):
        result=original(task,role,stage,root,attempt,run_id)
        if role=="tester_gate_b":
            repo=Path(task["worktree_path"])
            tree=git(repo,"rev-parse","HEAD^{tree}")
            divergent=git(repo,"commit-tree",tree,"-m","unrelated-root")
            git(repo,"update-ref","HEAD",divergent)
        return result
    monkeypatch.setattr(wf,"invoke",fake)
    p=start(s)
    try:
        out=approve(p,s)
        assert out["status"]=="NEEDS_RECONCILIATION"
        assert not any(r["role"]=="arbitrator" for r in p.store.results(p.task_id))
    finally:p.close()


def test_p025_timeout_keeps_partial_stdout_stderr(scenario):
    """Exercise the bounded local capture helper; not trusted integration."""
    s=scenario
    from p1.executor import _capture_bounded
    code=("import sys,time;"
          "sys.stdout.buffer.write(b'PARTIAL-STDOUT');sys.stdout.flush();"
          "sys.stderr.buffer.write(b'PARTIAL-STDERR');sys.stderr.flush();"
          "time.sleep(10)")
    outcome,meta=_capture_bounded([sys.executable,"-c",code],s["project"],{},1)
    assert outcome.stdout==b"PARTIAL-STDOUT"
    assert outcome.stderr==b"PARTIAL-STDERR"
    assert meta["timed_out"] is True
    assert meta["stdout_truncated"] is False


def test_real_invoke_refuses_same_identity_local_runner_even_if_provenance_flag_set(scenario,monkeypatch):
    s=scenario;s["init"]()
    import p1.executor as ex
    monkeypatch.setattr(ex,"TRUSTED_INTEGRATION_EXECUTION_VERIFIED",True)
    task={"mode":"integration","task_id":"TEST-001", "project_root":str(s["project"]),
          "worktree_path":str(s["project"])}
    with pytest.raises(ex.InvocationError,match="separate-identity Agent runner"):
        ex.invoke(task,"planner","0.2",s["home"],1,901)
    assert not list((s["home"]/"logs").glob("901.*"))
