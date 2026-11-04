from __future__ import annotations
import json
import sqlite3
from pathlib import Path
import pytest
from p1.contracts import canonical,digest_file,ContractError
from p1.workflow import Pipeline,PipelineError


def start(s):
    s["init"]()
    p=Pipeline(s["home"])
    out=p.run()
    assert out["stage"]=="gate0.2",out
    assert out["status"]=="WAITING_APPROVAL"
    return p


def approve(p,s):
    p.approve_spec("user","human-spec-approval-1",s["spec_sha"])
    return p.run()


def write_fixture(s,name,data):
    (s["fixtures"]/name).write_text(canonical(data)+"\n")


def test_complete_offline_flow_stops_before_deployment(scenario):
    s=scenario;p=start(s)
    out=approve(p,s)
    assert out["status"]=="WAITING_GATE_5_9",out
    assert out["stage"]=="gate5.9"
    assert s["worktree"].exists()
    assert "SIMULATION ONLY" in p.export_report()
    assert "ARBITRATION REPORT" in p.export_report()
    assert p.store.audit_events(p.task_id)==[]
    assert p.run()["status"]=="WAITING_GATE_5_9"
    assert not list(s["root"].rglob("*deploy*"))
    records=p.store.results(p.task_id)
    roles=[r["role"] for r in records]
    assert roles.index("spec_reviewer")<roles.index("tester_gate_a")
    assert roles.index("quality_reviewer")<roles.index("tester_gate_a")
    p.close()


def test_gate02_blocks_and_rejects_sha_mismatch(scenario):
    s=scenario;p=start(s)
    with pytest.raises(PipelineError,match="SHA mismatch"):
        p.approve_spec("user","approval","0"*64)
    assert p.status()["stage"]=="gate0.2"
    assert not s["worktree"].exists()
    p.close()


def test_gate01_mismatch_blocks_init(scenario):
    s=scenario;s["intent"].write_text("changed intent")
    with pytest.raises(ContractError,match="SHA mismatch"):
        s["init"]()


def test_review_pair_fails_and_retries_worker(scenario):
    s=scenario
    req={"verdict":"REQUEST_CHANGES","report":"Scope reviewed: main.py\nFix it","reviewed_commit":s["commit"],"spec_sha256":s["spec_sha"]}
    write_fixture(s,"3-spec_reviewer-1.json",req)
    p=start(s)
    out=approve(p,s)
    assert out["status"]=="WAITING_GATE_5_9",out
    assert out["round_a"]==2
    assert len([r for r in p.store.results(p.task_id) if r["role"]=="spec_reviewer"])==2
    assert len([r for r in p.store.results(p.task_id) if r["role"]=="quality_reviewer"])==2
    p.close()


def test_local_loop_five_rounds_stops(scenario):
    s=scenario
    bad={"verdict":"REQUEST_CHANGES","report":"Scope reviewed: main.py\nBugs","reviewed_commit":s["commit"],"spec_sha256":s["spec_sha"]}
    write_fixture(s,"3-spec_reviewer.json",bad)
    p=start(s)
    out=approve(p,s)
    assert out["status"]=="FAILED",out
    assert out["round_a"]==5
    assert len([r for r in p.store.results(p.task_id) if r["role"]=="spec_reviewer"])==5
    p.close()


def test_a2a_one_physical_host_never_passes(scenario):
    s=scenario
    a2a=json.loads((s["fixtures"]/"a2a.json").read_text())
    a2a["reports"]=a2a["reports"][:1]
    write_fixture(s,"a2a.json",a2a)
    p=start(s);out=approve(p,s)
    assert out["stage"]=="5.0"
    assert out["status"]=="BLOCKED"
    assert "quorum below 2" in out["last_error"]
    assert not list((s["home"]/"artifacts").glob("*_arbitrator.md"))
    p.close()


def test_gate_b_rejection_and_retry(scenario):
    s=scenario
    write_fixture(s,"5_3-arbitrator-1.json",{"verdict":"REJECT","reviewed_commit":s["commit"],"report":"REJECT - fixture"})
    p=start(s);out=approve(p,s)
    assert out["status"]=="WAITING_GATE_5_9",out
    assert out["round_b"]==2
    p.close()


def test_auditor_does_not_make_technical_judgement(scenario):
    s=scenario
    # An APPROVE_WITH_COMMENTS report passes; P1 does not inspect its technical opinion.
    p=start(s);out=approve(p,s)
    assert out["status"]=="WAITING_GATE_5_9"
    p.close()


def test_orphan_execution_blocks_resume(scenario):
    s=scenario;p=start(s)
    p.store.start_run(p.task_id,"0.2","planner","abc",{})
    # Cannot resume an unknown in-flight role call.
    with pytest.raises(PipelineError):p.resume()
    # Human cannot pretend it is complete just by invoking run.
    out=p.run()
    assert out["status"]=="WAITING_APPROVAL"  # still gated; orphan to reconcile on active step
    p.close()


def test_event_chain_tampering_detected(scenario):
    s=scenario;p=start(s)
    with p.store.db:
        p.store.db.execute("UPDATE events SET kind='hacked' WHERE id=1")
    assert p.store.audit_events(p.task_id)
    p.close()


def test_frozen_matrix_tampering_halts(scenario):
    s=scenario;p=start(s)
    (s["home"]/"snapshots"/"matrix.json").write_text("{}")
    with pytest.raises(PipelineError,match="frozen input tampering"):
        p.approve_spec("user","approve",s["spec_sha"])
    p.close()


def test_untrusted_a2a_identity_real_mode_fail_closed(scenario):
    s=scenario
    from p1.a2a import validate_collection
    from p1.contracts import read_json
    matrix=read_json(s["matrix"]);collection=read_json(s["fixtures"]/"a2a.json")
    fake={"task_id":"TEST-001","mode":"integration","commit_sha":s["commit"],"matrix_sha256":digest_file(s["matrix"])}
    assert any("attestation" in e for e in validate_collection(fake,matrix,collection,s["root"]))


def test_noncompliant_reviewer_retrace_max_two(scenario):
    s=scenario
    # Even though the technical verdict is APPROVE, wrong review commit is a
    # material input mismatch, and two replays cannot magically excuse it.
    bad={"verdict":"APPROVE","report":"Scope reviewed: wrong commit","reviewed_commit":"0"*40,"spec_sha256":s["spec_sha"]}
    write_fixture(s,"3-spec_reviewer.json",bad)
    p=start(s);out=approve(p,s)
    assert out["status"]=="FAILED",out
    assert out["compliance_retraces"]==2
    assert out["round_a"]==1  # compliance replay budget separate from technical loop
    assert len([x for x in p.store.results(p.task_id) if x["role"]=="spec_reviewer"])==3
    assert not list((s["home"]/"artifacts").glob("*_tester_gate_a.md"))
    p.close()


def test_unfinished_running_phase_not_auto_restarted(scenario):
    s=scenario;p=start(s)
    # After spec approval the next stage is worktree initialization. Simulate
    # a crash after phase_enter and before a clean exit.
    p.approve_spec("user","approval",s["spec_sha"])
    task=p.store.load(p.task_id);task["status"]="RUNNING"
    p.store.save(task,"simulated_process_crash")
    out=p.run()
    assert out["status"]=="NEEDS_RECONCILIATION"
    assert not s["worktree"].exists()
    p.close()


def test_a2a_same_node_two_labels_not_quorum(scenario):
    s=scenario;p=start(s)
    a2a=json.loads((s["fixtures"]/"a2a.json").read_text())
    a2a["reports"][1]["node"]="5bao"
    a2a["reports"][1]["physical_host_id"]="fraudulent-alias"
    write_fixture(s,"a2a.json",a2a)
    out=approve(p,s)
    assert out["stage"]=="5.0" and out["status"]=="BLOCKED"
    assert "duplicate/empty" in out["last_error"]
    p.close()


def test_report_hash_tamper_detected_even_after_gate59(scenario):
    s=scenario;p=start(s);out=approve(p,s)
    assert out["status"]=="WAITING_GATE_5_9"
    report=s["home"]/"artifacts"/"PROCESS_COMPLIANCE_REPORT.md"
    report.write_text("tampered")
    verification=p.verify_evidence()
    assert verification["verdict"]=="NON_COMPLIANT"
    assert any("PROCESS_COMPLIANCE_REPORT" in e for e in verification["errors"])
    p.close()


def test_gate_b_five_rounds_hard_stop(scenario):
    s=scenario
    fail={"verdict":"REJECT","reviewed_commit":s["commit"],"report":"REJECT"}
    write_fixture(s,"5_3-arbitrator.json",fail)
    p=start(s);out=approve(p,s)
    assert out["status"]=="FAILED" and out["round_b"]==5,out
    assert len([x for x in p.store.results(p.task_id) if x["role"]=="arbitrator"])==5
    p.close()


def test_missing_soul_rejected(scenario):
    s=scenario
    missing=s["root"]/"incomplete-souls";missing.mkdir()
    from p1.workflow import initialize
    with pytest.raises(ContractError,match="missing Soul"):
        initialize(s["home"],"TEST-001",s["intent"],s["matrix"],s["gate01"],missing,s["project"],s["worktree"],"offline_fixture",fixture_dir=s["fixtures"])
