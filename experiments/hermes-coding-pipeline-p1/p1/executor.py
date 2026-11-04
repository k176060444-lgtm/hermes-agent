"""Execute exactly one configured role. CLI adapter config comes from the task.

No implicit authentication, provider fallback, model discovery or shell execution.
Actual Codex/OpenCode wrapper commands are deferred to the 21bao integration session.
"""
from __future__ import annotations
import json
import os
import subprocess
from pathlib import Path
from typing import Any
from .contracts import atomic_write, canonical, ContractError, digest_file, read_json, sha256


class InvocationError(RuntimeError):
    pass

# This is a code-level integration gate, not a user-controlled JSON field.
# Stage 2 must implement and independently audit trusted execution provenance.
TRUSTED_INTEGRATION_EXECUTION_VERIFIED = False


def invoke(task: dict, role: str, stage: str, task_root: Path, attempt: int, run_id: int) -> dict[str, Any]:
    assignment = read_json(task_root/"snapshots"/"matrix.json")["roles"][role]
    mode=task["mode"]
    logs=task_root/"logs"; logs.mkdir(exist_ok=True)
    if mode == "offline_fixture":
        fixtures=Path(task["fixture_dir"])
        name=f"{stage.replace('.','_')}-{role}-{attempt}.json"
        source=fixtures/name
        if not source.exists():
            source=fixtures/f"{stage.replace('.','_')}-{role}.json"
        if not source.exists():
            raise InvocationError(f"fixture missing: {source.name}")
        result=read_json(source)
        raw=canonical(result)+"\n"
        atomic_write(logs/f"{run_id}.stdout.json",raw)
        atomic_write(logs/f"{run_id}.stderr.bin", b"")
        return {"payload":result,"mode":"fixture","exit_code":0,"stdout_sha256":sha256(raw.encode()),"stderr_sha256":sha256(b""),"assignment":assignment,"command":[],"run_id":run_id}

    if mode != "integration":
        raise InvocationError(f"unsupported mode: {mode}")
    # Independent audit P1-001/003/005/021: an arbitrary local wrapper cannot
    # prove the provider/model actually ran, read the full case or ran tests.
    # No trustworthy runner-verification protocol has been integrated yet.
    # Never call a paid model and then treat its self-reported JSON as evidence.
    if not TRUSTED_INTEGRATION_EXECUTION_VERIFIED:
        raise InvocationError("integration execution disabled: trusted Harness provenance and test attestation are NOT_VERIFIED")
    adapters=read_json(Path(task["adapter_config"]))
    profile=adapters.get("harnesses",{}).get(assignment["harness"])
    if not isinstance(profile,dict) or not profile.get("argv"):
        raise InvocationError(f"no configured command adapter for {assignment['harness']}")
    if not isinstance(profile["argv"],list) or any(not isinstance(x,str) for x in profile["argv"]):
        raise InvocationError("adapter argv must be a list of strings")
    if not profile.get("explicitly_authorized",False):
        raise InvocationError("real executor disabled until explicitly authorized in adapter config")
    workdir=Path(task["worktree_path"]) if stage!="0.2" else Path(task["project_root"])
    values={
        "task_id":task["task_id"],"role":role,"phase":stage,
        "harness":assignment["harness"],"model":assignment["primary_model"],
        "soul":str(task_root/"snapshots"/"souls"/f"{role}.md"),
        "intent":str(task_root/"snapshots"/"intent.md"),
        "spec":str(task_root/"snapshots"/"TASK_SPEC.md"),
        "worktree":str(workdir),"report_dir":str(task_root/"artifacts"),
        "matrix":str(task_root/"snapshots"/"matrix.json"),
    }
    try:
        argv=[piece.format_map(values) for piece in profile["argv"]]
    except KeyError as exc:
        raise InvocationError(f"unrecognized adapter placeholder: {exc}") from exc
    if not Path(argv[0]).is_absolute():
        raise InvocationError("real runner executable must use an absolute path")
    # No shell; no arbitrary environment variables from the role matrix.
    env=os.environ.copy()
    env["P1_ROLE"]=role
    env["P1_MODEL"]=assignment["primary_model"]
    env["P1_HARNESS"]=assignment["harness"]
    env["P1_OUTPUT_DIR"]=str(task_root/"artifacts")
    try:
        outcome=subprocess.run(argv,cwd=workdir,capture_output=True,timeout=int(profile.get("timeout_seconds",900)),env=env)
    except subprocess.TimeoutExpired as exc:
        # Exception holds useful partial evidence; save before reconciliation.
        atomic_write(logs/f"{run_id}.stdout.bin", exc.stdout or b"")
        atomic_write(logs/f"{run_id}.stderr.bin", exc.stderr or b"")
        atomic_write(logs/f"{run_id}.timeout.json", canonical({"timeout_seconds":exc.timeout,
            "stdout_sha256":digest_file(logs/f"{run_id}.stdout.bin"),
            "stderr_sha256":digest_file(logs/f"{run_id}.stderr.bin")})+"\n")
        raise InvocationError("runner timed out; external execution state needs reconciliation") from exc
    out=logs/f"{run_id}.stdout.bin"; err=logs/f"{run_id}.stderr.bin"
    atomic_write(out,outcome.stdout); atomic_write(err,outcome.stderr)
    if outcome.returncode:
        raise InvocationError(f"runner exit={outcome.returncode}; see logs/{run_id}.stderr.bin")
    try:
        payload=json.loads(outcome.stdout.decode("utf-8"))
    except (ValueError,UnicodeError) as exc:
        raise InvocationError("runner stdout is not one valid UTF-8 JSON result envelope") from exc
    if not isinstance(payload,dict):
        raise InvocationError("runner envelope must be a JSON object")
    return {"payload":payload,"mode":"integration","exit_code":outcome.returncode,"stdout_sha256":digest_file(out),"stderr_sha256":digest_file(err),"assignment":assignment,"command":argv,"run_id":run_id}
