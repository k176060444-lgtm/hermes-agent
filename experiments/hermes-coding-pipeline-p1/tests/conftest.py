from __future__ import annotations
import json
import subprocess
from pathlib import Path
import pytest
from p1.contracts import digest_file, sha256, canonical, ROLE_NAMES
from p1.workflow import initialize


def cmd(*args, cwd):
    return subprocess.check_output(["git",*args],cwd=cwd,stderr=subprocess.STDOUT,text=True).strip()

@pytest.fixture
def scenario(tmp_path):
    project=tmp_path/"project"
    project.mkdir()
    cmd("init","-q",cwd=project)
    cmd("config","user.name","P1 Tests",cwd=project)
    cmd("config","user.email","p1-tests@example.invalid",cwd=project)
    (project/"main.py").write_text("print('ready')\n")
    (project/"tests").mkdir()
    (project/"tests"/"test_main.py").write_text("def test_ok(): assert True\n")
    cmd("add",".",cwd=project)
    cmd("commit","-qm","initial",cwd=project)
    commit=cmd("rev-parse","HEAD",cwd=project)
    inputs=tmp_path/"inputs";inputs.mkdir()
    intent=inputs/"intent.md";intent.write_text("# User approved intent\nBuild a fixture-only change.\n")
    roles={
      "planner":("codex","read_only"),"worker":("opencode","workspace_write"),
      "spec_reviewer":("opencode","read_only"),"quality_reviewer":("codex","read_only"),
      "tester_gate_a":("codex","test_files_only"),"worker_remediation":("opencode","workspace_write"),
      "tester_gate_b":("opencode","test_files_only"),"arbitrator":("codex","read_only"),
      "pro_audit":("opencode","read_only"),
      "blind_a":("external_a2a","read_only"),"blind_b":("external_a2a","read_only"),"blind_c":("external_a2a","read_only")
    }
    matrix={"schema_version":1,"nodes":{"21bao":{"platform":"windows"},"5bao":{"platform":"debian"},"9bao":{"platform":"debian"},"rusty":{"platform":"debian"}},
        "roles":{key:{"node":("5bao" if key=="blind_a" else "9bao" if key=="blind_b" else "rusty" if key=="blind_c" else "21bao"),"harness":harness,"primary_model":"fixture-only-model" if not key.startswith("blind_") else None,"backup_model":None,"permission":permission} for key,(harness,permission) in roles.items()},
        "blind_review":{"minimum_distinct_physical_nodes":2,"third_seat_grace_seconds":600,"candidates":["5bao","9bao","rusty"]}}
    matrix_file=inputs/"matrix.json";matrix_file.write_text(canonical(matrix)+"\n")
    soul_dir=Path(__file__).resolve().parents[1]/"souls"
    approved_souls={role:digest_file(soul_dir/f"{role}.md") for role in ROLE_NAMES}
    soul_sha=sha256((canonical(approved_souls)+"\n").encode())
    approval={"gate":"0.1","approved":True,"approved_by":"user","approved_at":"2026-11-04T00:00:00+08:00","approval_id":"offline-approval-001","intent_sha256":digest_file(intent),"matrix_sha256":digest_file(matrix_file),"souls_sha256":soul_sha}
    gate01=inputs/"gate01.json";gate01.write_text(canonical(approval)+"\n")
    fixtures=tmp_path/"fixtures";fixtures.mkdir()
    spec="# TASK_SPEC\n\n- Build a fixture-only module.\n"
    specsha=sha256(spec.encode())
    outputs={
      "0_2-planner.json":{"verdict":"PASS","task_spec":spec},
      "2-worker.json":{"verdict":"PASS","report":"Worker implementation complete (SIMULATED)."},
      "3-spec_reviewer.json":{"verdict":"APPROVE","report":"Scope reviewed: main.py\nAPPROVE (SIMULATED).","reviewed_commit":commit,"spec_sha256":specsha},
      "4-quality_reviewer.json":{"verdict":"APPROVE_WITH_COMMENTS","report":"Scope reviewed: main.py\nNo BLOCKER (SIMULATED).","reviewed_commit":commit,"spec_sha256":specsha},
      "4_5-tester_gate_a.json":{"verdict":"GATE_A_PASS","report":"GATE_A_PASS (SIMULATED)."},
      "5_1-worker_remediation.json":{"verdict":"PASS","report":"No P0/P1 to remediate (SIMULATED).",
                                      "no_op":True,"no_op_reason":"All reported issues were already resolved in the reviewed revision."},
      "5_2-tester_gate_b.json":{"verdict":"GATE_B_PASS","checks":{"smoke":"PASS","canary":"PASS","regression":"PASS"},"report":"GATE_B_PASS (SIMULATED)."},
      "5_3-arbitrator.json":{"verdict":"PASS","report":"ARBITRATION REPORT (SIMULATED)\nPASS","reviewed_commit":commit}
    }
    for name,result in outputs.items():
        (fixtures/name).write_text(canonical(result)+"\n")
    review={"task_id":"TEST-001","commit_sha":commit,"matrix_sha256":digest_file(matrix_file),
      "reports":[{"node":node,"physical_host_id":node+"-fixture-host","commit_sha":commit,"verdict":"APPROVE","report":"SIMULATED"} for node in ("5bao","9bao")]}
    (fixtures/"a2a.json").write_text(canonical(review)+"\n")
    home=tmp_path/"p1-state";wt=tmp_path/"worktrees"/"wt-TEST-001"
    soul_dir=Path(__file__).resolve().parents[1]/"souls"
    def init():
        return initialize(home,"TEST-001",intent,matrix_file,gate01,soul_dir,project,wt,"offline_fixture",fixture_dir=fixtures)
    return {"root":tmp_path,"project":project,"commit":commit,"inputs":inputs,"intent":intent,"matrix":matrix_file,"gate01":gate01,"fixtures":fixtures,"spec":spec,"spec_sha":specsha,"home":home,"worktree":wt,"init":init}
