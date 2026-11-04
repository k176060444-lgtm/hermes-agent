"""Regression tests for Round-003 findings. Offline Git fixtures only."""
from __future__ import annotations
import json
from pathlib import Path
import pytest
from p1 import gitops, workflow
from p1.contracts import canonical
from p1.workflow import PipelineError
from test_pipeline import start, approve


@pytest.mark.parametrize("path",[
    "tests/conftest.py", "tests/__init__.py", "tests/helpers.py",
    "tests/pytest_plugins.py", "pytest.ini", "tox.ini", "setup.cfg",
    "pyproject.toml", "sitecustomize.py", "tests/sitecustomize.py",
    "tests/utils/test_helpers.txt", "tests/test_something.py/../conftest.py",
])
def test_r3_001_collection_and_import_controls_are_not_tester_cases(path):
    assert gitops.test_path(path) is False


@pytest.mark.parametrize("path",[
    "tests/test_boundary.py", "tests/more/test_edge.py", "test_parser.py",
    "tests/parser_test.py", "tests/suite.test.ts", "tests/suite.spec.tsx",
    "tests/suite.test.js", "tests/suite_test.go",
])
def test_r3_001_true_test_modules_remain_addable(path):
    assert gitops.test_path(path)


def _git_commit(repo: Path, message: str):
    gitops.git(repo, "add", "-A")
    gitops.git(repo, "commit", "-m", message)


@pytest.mark.parametrize("role", ["tester_gate_a", "tester_gate_b"])
def test_r3_001_tester_control_file_cannot_pass_gate59(scenario, monkeypatch, role):
    s=scenario
    original=workflow.invoke
    def adulterated(task, current_role, stage, root, attempt, run_id):
        envelope=original(task,current_role,stage,root,attempt,run_id)
        if current_role==role:
            repo=Path(task["worktree_path"])
            (repo/"tests"/"conftest.py").write_text(
                'collect_ignore_glob = ["test_*.py"]\n',encoding="utf-8")
            _git_commit(repo,"fixture: tester added collection controller")
        return envelope
    monkeypatch.setattr(workflow,"invoke",adulterated)
    p=start(s)
    try:
        result=approve(p,s)
        assert result["status"] != "WAITING_GATE_5_9",result
        entries=[x for x in p.store.load(p.task_id)["audit_history"] if x["role"]==role]
        assert entries and entries[-1]["verdict"]=="NON_COMPLIANT",entries
        assert any("non-test" in str(x) or "test-only" in str(x) or "outside additive" in str(x)
                   for x in entries[-1]["errors"]),entries
    finally:
        p.close()


def test_r3_001_tester_can_still_add_real_test_case(scenario,monkeypatch):
    s=scenario
    original=workflow.invoke
    def add_test(task, role, stage, root, attempt, run_id):
        result=original(task,role,stage,root,attempt,run_id)
        if role=="tester_gate_a":
            repo=Path(task["worktree_path"])
            (repo/"tests"/"test_new_scenario.py").write_text("def test_new_scenario(): assert True\n")
            _git_commit(repo,"fixture: add valid test case")
        return result
    monkeypatch.setattr(workflow,"invoke",add_test)
    p=start(s)
    try:
        outcome=approve(p,s)
        # This scenario's downstream A2A fixture still references its original
        # commit, so the full pipeline appropriately stops at its A2A binding.
        # The point here is that the legitimate new test was NOT rejected by
        # the Tester stage compliance gate.
        tester=[a for a in p.store.load(p.task_id)["audit_history"]
                if a["role"]=="tester_gate_a"]
        assert tester and tester[-1]["verdict"]=="COMPLIANT",(outcome,tester)
        assert (s["worktree"]/"tests"/"test_new_scenario.py").is_file()
    finally:
        p.close()


@pytest.mark.parametrize("field,new_value",[("stage","not-a-phase"),("role","forged_role"),("input_sha","0"*64)])
def test_r3_002_dispatch_metadata_mutation_is_detected(scenario,field,new_value):
    s=scenario;p=start(s)
    try:
        assert approve(p,s)["status"]=="WAITING_GATE_5_9"
        entry=p.store.results(p.task_id)[0]
        with p.store.db:
            p.store.db.execute(f"UPDATE runs SET {field}=? WHERE id=?",(new_value,entry["id"]))
        errors=p.store.audit_events(p.task_id)
        assert any("stage/role/input differs" in item for item in errors),errors
        assert p.verify_evidence()["verdict"]=="NON_COMPLIANT"
        with pytest.raises(PipelineError,match="evidence invalid"):
            p.export_report()
    finally:
        p.close()


def test_r3_002_deleted_run_row_is_detected(scenario):
    s=scenario;p=start(s)
    try:
        assert approve(p,s)["status"]=="WAITING_GATE_5_9"
        run=p.store.results(p.task_id)[0]
        with p.store.db:
            p.store.db.execute("DELETE FROM runs WHERE id=?",(run["id"],))
        errors=p.store.audit_events(p.task_id)
        assert any("has no run row" in e for e in errors),errors
        assert p.verify_evidence()["verdict"]=="NON_COMPLIANT"
        with pytest.raises(PipelineError,match="evidence invalid"):
            p.export_report()
    finally:
        p.close()


def test_r3_002_duplicate_finished_journal_is_detected(scenario):
    s=scenario;p=start(s)
    try:
        assert approve(p,s)["status"]=="WAITING_GATE_5_9"
        rows=p.store.db.execute("SELECT payload FROM events WHERE kind='execution_finished' AND task_id=? ORDER BY id LIMIT 1",(p.task_id,)).fetchall()
        assert rows
        data=json.loads(rows[0][0]); data.pop("_task_sha256",None)
        # Simulate a formally valid appended journal entry (no run row modified).
        with p.store.db:
            p.store._event(p.task_id,"execution_finished",data)
        assert any("duplicate finish event" in e for e in p.store.audit_events(p.task_id))
    finally:
        p.close()


def test_r3_003_status_observes_block_without_resealing_tampered_task(scenario):
    s=scenario; p=start(s)
    try:
        assert approve(p,s)["status"]=="WAITING_GATE_5_9"
        original=p.store.load(p.task_id)
        tampered=dict(original)
        tampered["a2a_job_id"]="UNTRUSTED-JOB"
        before=p.store.db.execute("SELECT count(*) FROM events WHERE task_id=?",(p.task_id,)).fetchone()[0]
        with p.store.db:
            p.store.db.execute("UPDATE tasks SET data=? WHERE task_id=?",(canonical(tampered),p.task_id))
        result=p.status()
        assert result["status"]=="BLOCKED"
        assert result["persisted_status"]=="WAITING_GATE_5_9"
        assert result["integrity_preflight"]=="FAILED"
        assert "task row" in str(result["integrity_errors"])
        assert p.store.load(p.task_id)["status"]=="WAITING_GATE_5_9"
        after=p.store.db.execute("SELECT count(*) FROM events WHERE task_id=?",(p.task_id,)).fetchone()[0]
        assert after==before
    finally:
        p.close()
