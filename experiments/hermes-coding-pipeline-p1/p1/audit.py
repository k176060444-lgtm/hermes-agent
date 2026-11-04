"""Lightweight compliance-only checks (not code/architecture opinions)."""
from __future__ import annotations
from pathlib import Path
from typing import Any
from .contracts import READ_ONLY_ROLES, TEST_ONLY_ROLES, digest_file, read_json
from .gitops import changed, test_path


def audit_role(task:dict, role:str, stage:str, envelope:dict, before:dict[str,str], after:dict[str,str],
               before_head:str|None, after_head:str|None, soul_expected:str, task_root:Path,
               before_index:str|None=None, after_index:str|None=None)->dict[str,Any]:
    """Checks narrow authorization, provenance and required output shape.

    Does not evaluate correctness of implementation, style, security or test quality.
    """
    errors=[]; warnings=[]
    if digest_file(task_root/"snapshots"/"souls"/f"{role}.md")!=soul_expected:
        errors.append("role Soul modified since Gate 0.1 snapshot")
    assignment=read_json(task_root/"snapshots"/"matrix.json")["roles"].get(role)
    if envelope.get("assignment")!=assignment:
        errors.append("actual role invocation assignment differs from approved matrix")
    payload=envelope.get("payload",{})
    if not isinstance(payload,dict):
        errors.append("missing structured role output")
        payload={}
    if envelope.get("exit_code")!=0:
        errors.append("executor returned nonzero status")
    if task["mode"]=="integration":
        if envelope.get("mode")!="integration":
            errors.append("fixture result prohibited in integration mode")
        if payload.get("mode")=="fixture" or payload.get("simulated") is True:
            errors.append("simulated payload prohibited in integration mode")
        # No trusted provider/agent/test provenance verifier yet. Must fail closed.
        errors.append("integration role provenance unverified; no trusted runner attestation")
    if task["mode"]=="offline_fixture":
        warnings.append("SIMULATED: mock result is not proof of a real agent execution")
    if role in READ_ONLY_ROLES and before!=after:
        errors.append(f"read-only role {role} changed Git-visible source/test files")
    if role in READ_ONLY_ROLES and before_index is not None and before_index!=after_index:
        errors.append(f"read-only role {role} changed Git index")
    if role in READ_ONLY_ROLES and before_head and before_head!=after_head:
        errors.append(f"read-only role {role} changed Git HEAD")
    if role in TEST_ONLY_ROLES:
        for p in sorted(changed(before,after)):
            if not test_path(p):
                errors.append(f"test-only role touched non-test path: {p}")
            elif p in before:
                errors.append(f"Tester changed/deleted existing test: {p}")
        for file, expected_sha in task.get("protected_tests",{}).items():
            if after.get(file)!=expected_sha:
                errors.append(f"Tester changed/deleted protected exam: {file}")
        if before_head!=after_head and before_head:
            warnings.append("Tester changed HEAD; ancestry and commit-diff check required at workflow gate")
    if role!="planner" and not isinstance(payload.get("report"),str):
        errors.append(f"{role} missing required report")
    elif role!="planner" and not payload.get("report","").strip():
        errors.append(f"{role} missing required report")
    if role=="planner" and not payload.get("task_spec","").strip():
        errors.append("Planner missing TASK_SPEC content")
    if role in {"spec_reviewer","quality_reviewer"}:
        if payload.get("reviewed_commit")!=before_head:
            errors.append(f"{role} reviewed wrong commit")
        if payload.get("spec_sha256")!=task.get("spec_sha256"):
            errors.append(f"{role} referenced wrong TASK_SPEC SHA")
    if role=="arbitrator":
        if payload.get("reviewed_commit")!=task.get("commit_sha"):
            errors.append("Arbitrator cited wrong final commit")
        if not task.get("arbitration_case_sha256"):
            errors.append("Arbitrator missing fixed case manifest")
    if role in {"spec_reviewer", "quality_reviewer"}:
        findings=payload.get("findings",[])
        if not isinstance(findings,list):
            errors.append("reviewer findings must be a structured list")
        else:
            for item in findings:
                if isinstance(item, dict) and item.get("category")=="QUESTION" and item.get("resolved") is not True:
                    warnings.append("unresolved QUESTION: requires clarification before Gate A")
    return {"verdict":"NON_COMPLIANT" if errors else "COMPLIANT","errors":errors,"warnings":warnings}
