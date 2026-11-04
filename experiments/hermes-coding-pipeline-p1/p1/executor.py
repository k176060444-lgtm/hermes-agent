"""Execute exactly one configured role. CLI adapter config comes from the task.

No implicit authentication, provider fallback, model discovery or shell execution.
Actual Codex/OpenCode wrapper commands are deferred to the 21bao integration session.
"""
from __future__ import annotations
import json
import os
import subprocess
import threading
from pathlib import Path
from typing import Any
from .contracts import atomic_write, canonical, ContractError, digest_file, read_json, sha256


class InvocationError(RuntimeError):
    pass

# This is a code-level integration gate, not a user-controlled JSON field.
# Stage 2 must implement and independently audit trusted execution provenance.
TRUSTED_INTEGRATION_EXECUTION_VERIFIED = False


# The actual provider/test/A2A evidence protocol is still NOT_VERIFIED.
# Nevertheless, no subprocess can exhaust the orchestrator's memory by
# writing unbounded stdout/stderr once trusted integration is enabled.
MAX_CAPTURE_BYTES_PER_STREAM = 8 * 1024 * 1024


def _capture_bounded(argv: list[str], cwd: Path, env: dict[str, str],
                     timeout_seconds: int, *, limit: int = MAX_CAPTURE_BYTES_PER_STREAM):
    """Read both output pipes concurrently with an absolute per-stream cap.

    Exceeding the cap kills the direct child and refuses the result. This is
    NOT a Windows descendant-process guarantee (Stage 2 must verify that).
    Return (CompletedProcess, capture_metadata); metadata lengths describe
    bytes actually observed, not the unknown full size of an aborted stream.
    """
    if limit < 1 or limit > MAX_CAPTURE_BYTES_PER_STREAM:
        raise InvocationError('invalid capture limit')
    child = subprocess.Popen(argv, cwd=cwd, env=env, stdin=subprocess.DEVNULL,
                             stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    outputs = {"stdout": bytearray(), "stderr": bytearray()}
    observed = {"stdout": 0, "stderr": 0}
    truncated = {"stdout": False, "stderr": False}
    overflow = threading.Event()
    threads = []

    def drain(stream, name):
        try:
            while True:
                block = stream.read(65536)
                if not block:
                    break
                observed[name] += len(block)
                remaining = max(0, limit - len(outputs[name]))
                outputs[name].extend(block[:remaining])
                if len(block) > remaining:
                    truncated[name] = True
                    overflow.set()
                    try: child.kill()
                    except OSError: pass
                    break
        finally:
            stream.close()

    for name, stream in (("stdout", child.stdout), ("stderr", child.stderr)):
        thread = threading.Thread(target=drain, args=(stream, name), daemon=True)
        thread.start()
        threads.append(thread)
    timed_out = False
    try:
        child.wait(timeout=timeout_seconds)
    except subprocess.TimeoutExpired:
        timed_out = True
        child.kill()
        child.wait()
    finally:
        for thread in threads:
            thread.join(timeout=10)
    metadata = {
        "limit_per_stream_bytes": limit,
        "stdout_bytes_observed": observed["stdout"],
        "stderr_bytes_observed": observed["stderr"],
        "stdout_truncated": truncated["stdout"],
        "stderr_truncated": truncated["stderr"],
        "timed_out": timed_out,
        "output_limit_exceeded": overflow.is_set(),
        "returncode": child.returncode,
    }
    outcome = subprocess.CompletedProcess(argv, child.returncode,
                                          bytes(outputs["stdout"]),
                                          bytes(outputs["stderr"]))
    return outcome, metadata


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
    # subprocess.Popen would inherit the orchestrator's security identity and
    # could read/write its ledger. P1 does not implement a separately
    # authenticated runner service yet; an adapter JSON boolean cannot stand
    # in for a verified Windows token or external trusted execution receipt.
    # This independent gate must be replaced only after Stage-2 implements
    # and audits a real isolated-identity runner protocol.
    raise InvocationError("NOT_VERIFIED: no authenticated separate-identity Agent runner is installed")
    adapter_file=task_root/"snapshots"/"adapters.json"
    if (not task.get("adapter_sha256") or not adapter_file.is_file() or
            digest_file(adapter_file)!=task["adapter_sha256"]):
        raise InvocationError("frozen adapter snapshot missing or mismatched")
    adapters=read_json(adapter_file)
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
        outcome, capture = _capture_bounded(argv,workdir,env,int(profile.get("timeout_seconds",900)))
    except (OSError, ValueError) as exc:
        raise InvocationError(f"trusted runner could not start: {type(exc).__name__}") from exc
    out=logs/f"{run_id}.stdout.bin"; err=logs/f"{run_id}.stderr.bin"
    atomic_write(out,outcome.stdout); atomic_write(err,outcome.stderr)
    capture_file = logs / f"{run_id}.capture.json"
    atomic_write(capture_file, canonical({
        **capture, "stdout_sha256":digest_file(out), "stderr_sha256":digest_file(err)})+"\n")
    if capture["timed_out"]:
        atomic_write(logs/f"{run_id}.timeout.json", canonical({
            "timeout_seconds":int(profile.get("timeout_seconds",900)),
            **capture,"stdout_sha256":digest_file(out),"stderr_sha256":digest_file(err)})+"\n")
        raise InvocationError("runner timed out; partial bounded logs saved; needs reconciliation")
    if capture["output_limit_exceeded"]:
        raise InvocationError("runner output limit exceeded; bounded logs saved; needs reconciliation")
    if outcome.returncode:
        raise InvocationError(f"runner exit={outcome.returncode}; see logs/{run_id}.stderr.bin")
    try:
        payload=json.loads(outcome.stdout.decode("utf-8"))
    except (ValueError,UnicodeError) as exc:
        raise InvocationError("runner stdout is not one valid UTF-8 JSON result envelope") from exc
    if not isinstance(payload,dict):
        raise InvocationError("runner envelope must be a JSON object")
    return {"payload":payload,"mode":"integration","exit_code":outcome.returncode,
            "stdout_sha256":digest_file(out),"stderr_sha256":digest_file(err),
            "capture_sha256":digest_file(capture_file),
            "assignment":assignment,"command":argv,"run_id":run_id}
