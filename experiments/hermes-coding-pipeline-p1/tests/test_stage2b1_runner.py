"""Stage-2B-1 runner protocol / attestation / Job Object offline tests.

Windows live-token and Job-Object cases run only on 21bao Windows and use
nothing but the current process and harmless local python stubs (no models,
no network, disposable dirs). Everything else is fully portable.
"""
from __future__ import annotations

import os
import subprocess
import sys
import time
from pathlib import Path

import pytest

from p1 import runner as rn
from p1.contracts import canonical, digest_file, sha256
from p1.runner import (RunnerAttestationError, RunnerClient,
                       RunnerUnavailableError, build_launch_request,
                       live_process_token, orchestrator_sid,
                       validate_launch_request, validate_receipt,
                       verify_execution_identity, verify_ledger_inaccessible)

SID_KK = "S-1-5-21-1229371380-3680912533-2234981468-1001"
SID_AGENTX = "S-1-5-21-1229371380-3680912533-2234981468-1002"

BINDINGS = {"soul_sha256": "a" * 64, "matrix_sha256": "b" * 64,
            "spec_sha256": "c" * 64, "intent_sha256": "d" * 64,
            "reviewed_commit": "0" * 40, "input_sha256": "e" * 64,
            "frozen_harness_sha256": "f" * 64}


def make_request(tmp_path):
    return build_launch_request(
        task={"task_id": "T-2B1"}, stage="2", role="worker", run_id=7,
        matrix_entry={"harness": "codex", "primary_model": "provider/model-x"},
        bindings=dict(BINDINGS), worktree_path=tmp_path / "wt",
        timeout_seconds=60, idempotency_key="idem-7")


def make_receipt(request, exe_path, *, sid=SID_AGENTX, groups=None,
                 status="COMPLETED", exit_code=0, pid=4242):
    payload = {"schema_version": rn.RUNNER_SCHEMA_VERSION,
               "task_id": request["task_id"], "run_id": request["run_id"],
               "idempotency_key": request["idempotency_key"],
               "agent_pid": pid, "agent_token_sid": sid,
               "agent_group_sids": groups if groups is not None else [rn.SID_USERS],
               "launch_source": "runner-service",
               "exit_code": exit_code, "started_at": 1.0, "finished_at": 2.0,
               "stdout_sha256": "1" * 64, "stderr_sha256": "2" * 64,
               "capture_meta_sha256": "3" * 64,
               "harness_exe_path": str(exe_path),
               "harness_exe_sha256": request["frozen_harness_sha256"],
               "harness_version": "stub 0.0", "argv_sha256": "4" * 64,
               "status": status}
    return payload


# ------------------------------------------------------------------- request
def test_request_binds_all_identity_fields(tmp_path):
    request = make_request(tmp_path)
    validate_launch_request(request)
    for field in ("task_id", "run_id", "role", "harness", "model",
                  "soul_sha256", "matrix_sha256", "spec_sha256", "intent_sha256",
                  "reviewed_commit", "worktree_path", "idempotency_key"):
        assert request[field], field
    body = canonical({k: v for k, v in request.items() if k != "request_sha256"})
    assert sha256(body.encode()) == request["request_sha256"]
    print("request digest self-consistent; all bindings present")


def test_request_tamper_detected(tmp_path):
    request = make_request(tmp_path)
    request["model"] = "provider/sneaky-model"
    with pytest.raises(RunnerAttestationError, match="digest mismatch"):
        validate_launch_request(request)


@pytest.mark.parametrize("drop", ["soul_sha256", "idempotency_key", "run_id"])
def test_request_missing_field_rejected(tmp_path, drop):
    request = make_request(tmp_path)
    request.pop(drop)
    with pytest.raises(RunnerAttestationError, match="missing fields"):
        validate_launch_request(request)


def test_build_refers_no_default_model(tmp_path):
    with pytest.raises(RunnerAttestationError, match="primary_model"):
        build_launch_request(task={"task_id": "T"}, stage="2", role="worker",
                             run_id=1, matrix_entry={"harness": "codex"},
                             bindings=dict(BINDINGS), worktree_path=tmp_path,
                             timeout_seconds=1, idempotency_key="k")


def test_binding_requires_digest_shape(tmp_path):
    weak = dict(BINDINGS, soul_sha256="short")
    with pytest.raises(RunnerAttestationError, match="soul_sha256"):
        build_launch_request(task={"task_id": "T"}, stage="2", role="worker",
                             run_id=1,
                             matrix_entry={"harness": "codex", "primary_model": "m"},
                             bindings=weak, worktree_path=tmp_path,
                             timeout_seconds=1, idempotency_key="k")


# ------------------------------------------------------------------- receipt
def test_receipt_bound_to_request(tmp_path):
    request = make_request(tmp_path)
    receipt = make_receipt(request, tmp_path / "harness.exe")
    validate_receipt(receipt, request)


def test_receipt_cross_run_rejected(tmp_path):
    request = make_request(tmp_path)
    receipt = make_receipt(request, tmp_path / "harness.exe")
    receipt["run_id"] = 999
    with pytest.raises(RunnerAttestationError, match="run_id"):
        validate_receipt(receipt, request)


def test_receipt_exe_drift_rejected(tmp_path):
    request = make_request(tmp_path)
    receipt = make_receipt(request, tmp_path / "harness.exe")
    receipt["harness_exe_sha256"] = "9" * 64
    with pytest.raises(RunnerAttestationError, match="frozen snapshot"):
        validate_receipt(receipt, request)


def test_unknown_status_is_reconcile_only(tmp_path):
    request = make_request(tmp_path)
    receipt = make_receipt(request, tmp_path / "harness.exe", status="UNKNOWN")
    with pytest.raises(RunnerAttestationError, match="reconciliation-only"):
        validate_receipt(receipt, request)


def test_isolated_boolean_grants_nothing(tmp_path):
    """A receipt stuffed with isolated:true must not change any verdict."""
    request = make_request(tmp_path)
    receipt = make_receipt(request, tmp_path / "harness.exe")
    receipt["isolated"] = True
    receipt["trusted"] = True
    receipt["self_attested_sid"] = rn.SID_LOCAL_SYSTEM
    validate_receipt(receipt, request)  # extra fields are inert, not authority
    print("self-reported booleans accepted-but-ignored by schema; authority "
          "lives solely in verify_execution_identity")


# ---------------------------------------------------------------- attestation
def _stub_probe():
    return None


def test_identity_rejects_orchestrator_sid(tmp_path):
    """Manifest mis-pinned to the orchestrator itself: the live measurement
    must still refuse to bless a same-identity agent."""
    request = make_request(tmp_path)
    request["expected_agent_sid"] = SID_KK
    exe = tmp_path / "harness.exe"
    exe.write_bytes(b"exe")
    request["frozen_harness_sha256"] = digest_file(exe)
    receipt = make_receipt(request, exe, sid=SID_KK)
    live = lambda pid: {"pid": pid, "user_sid": SID_KK, "group_sids": [rn.SID_USERS]}
    with pytest.raises(RunnerAttestationError, match="orchestrator identity"):
        verify_execution_identity(receipt=receipt, request=request,
                                  orchestrator=SID_KK, ledger_root=tmp_path,
                                  process_alive=live)


def test_identity_rejects_receipt_sid_off_pin(tmp_path):
    request = make_request(tmp_path)
    request["expected_agent_sid"] = SID_AGENTX
    exe = tmp_path / "harness.exe"
    exe.write_bytes(b"exe")
    request["frozen_harness_sha256"] = digest_file(exe)
    receipt = make_receipt(request, exe, sid="S-1-5-21-777")
    live = lambda pid: {"pid": pid, "user_sid": "S-1-5-21-777", "group_sids": []}
    with pytest.raises(RunnerAttestationError, match="does not match manifest pin"):
        verify_execution_identity(receipt=receipt, request=request,
                                  orchestrator=SID_KK, ledger_root=tmp_path,
                                  process_alive=live)


def test_identity_rejects_admin_member(tmp_path):
    request = make_request(tmp_path)
    request["expected_agent_sid"] = SID_AGENTX
    exe = tmp_path / "harness.exe"
    exe.write_bytes(b"exe")
    request["frozen_harness_sha256"] = digest_file(exe)
    receipt = make_receipt(request, exe, groups=[rn.SID_ADMINISTRATORS, rn.SID_USERS])
    live = lambda pid: {"pid": pid, "user_sid": SID_AGENTX,
                        "group_sids": [rn.SID_ADMINISTRATORS, rn.SID_USERS]}
    with pytest.raises(RunnerAttestationError, match="Administrators"):
        verify_execution_identity(receipt=receipt, request=request,
                                  orchestrator=SID_KK, ledger_root=tmp_path,
                                  process_alive=live)


def test_identity_requires_pinned_sid(tmp_path):
    request = make_request(tmp_path)
    exe = tmp_path / "harness.exe"
    exe.write_bytes(b"exe")
    request["frozen_harness_sha256"] = digest_file(exe)
    receipt = make_receipt(request, exe)
    live = lambda pid: {"pid": pid, "user_sid": SID_AGENTX, "group_sids": []}
    with pytest.raises(RunnerAttestationError, match="pinned"):
        verify_execution_identity(receipt=receipt, request=request,
                                  orchestrator=SID_KK, ledger_root=tmp_path,
                                  process_alive=live)


def test_identity_rejects_receipt_live_sid_divergence(tmp_path):
    request = make_request(tmp_path)
    request["expected_agent_sid"] = SID_AGENTX
    exe = tmp_path / "harness.exe"
    exe.write_bytes(b"exe")
    request["frozen_harness_sha256"] = digest_file(exe)
    receipt = make_receipt(request, exe, sid=SID_AGENTX)
    live = lambda pid: {"pid": pid, "user_sid": "S-1-5-21-999", "group_sids": []}
    with pytest.raises(RunnerAttestationError, match="differs from receipt"):
        verify_execution_identity(receipt=receipt, request=request,
                                  orchestrator=SID_KK, ledger_root=tmp_path,
                                  process_alive=live)


def test_identity_rejects_exe_digest_drift(tmp_path):
    request = make_request(tmp_path)
    request["expected_agent_sid"] = SID_AGENTX
    exe = tmp_path / "harness.exe"
    exe.write_bytes(b"exe")
    request["frozen_harness_sha256"] = "f" * 64  # frozen pin != actual bytes
    receipt = make_receipt(request, exe)
    live = lambda pid: {"pid": pid, "user_sid": SID_AGENTX, "group_sids": []}
    with pytest.raises(RunnerAttestationError, match="frozen snapshot"):
        verify_execution_identity(receipt=receipt, request=request,
                                  orchestrator=SID_KK, ledger_root=tmp_path,
                                  process_alive=live)


def test_ledger_check_blocks_exposed_dacl(tmp_path):
    ledger = tmp_path / "ledger"; ledger.mkdir()
    leaky = {ledger: [SID_AGENTX, rn.SID_USERS]}
    query = lambda path: leaky[path]
    with pytest.raises(RunnerAttestationError, match="exposes agent principals"):
        verify_ledger_inaccessible(ledger, SID_AGENTX, [rn.SID_USERS], query=query)


def test_ledger_check_passes_private_dacl(tmp_path):
    ledger = tmp_path / "ledger"; ledger.mkdir()
    query = lambda path: [SID_KK, rn.SID_LOCAL_SYSTEM, rn.SID_ADMINISTRATORS]
    with pytest.raises(RunnerAttestationError, match="exposes"):
        # Administrators itself is in the watched set: an agent-less admin-only
        # home still fails the strict rule unless agent groups exclude it;
        # verify the function treats Administrators as leak signal.
        verify_ledger_inaccessible(ledger, SID_AGENTX, [rn.SID_USERS, rn.SID_ADMINISTRATORS],
                                   query=query)
    # a genuinely agent-free DACL (no agent groups at all):
    verify_ledger_inaccessible(ledger, SID_AGENTX, [], query=query)
    print("ledger DACL verifier: exposed -> blocked; agent-free -> pass")


# ------------------------------------------------------------------- client
def test_client_fails_closed_without_manifest(tmp_path):
    client = RunnerClient(tmp_path)
    health = client.runner_health()
    assert health["available"] is False
    request = make_request(tmp_path)
    with pytest.raises(RunnerUnavailableError, match="not provisioned"):
        client.launch(request, "prompt")


def test_client_rejects_manifest_without_pin(tmp_path):
    snapshot = tmp_path / "snapshots"; snapshot.mkdir()
    manifest = snapshot / "runner_manifest.json"
    manifest.write_text('{"spool_inbox": "/x"}\n', encoding="utf-8")
    client = RunnerClient(tmp_path)
    with pytest.raises(RunnerUnavailableError, match="incomplete"):
        client.manifest()


def test_client_poll_not_dispatched(tmp_path):
    client = RunnerClient(tmp_path)
    request = make_request(tmp_path)
    assert client.poll(request)["state"] == "NO_RUNNER"


# ------------------------------------------------------------------- win32
@pytest.mark.skipif(os.name != "nt", reason="live token API is Windows-only")
def test_windows_live_token_of_self():
    info = live_process_token(os.getpid())
    orch = orchestrator_sid()
    assert info["user_sid"] == orch
    assert rn.SID_ADMINISTRATORS in info["group_sids"]  # KK is admin: proves
    # the probe sees real group membership -- exactly why agentx must fail this
    print(f"live token probe verified: {orch}, groups={len(info['group_sids'])}")


@pytest.mark.skipif(os.name != "nt", reason="Job Objects are Windows-only")
def test_windows_job_object_kills_descendant_tree():
    from p1 import winjobs
    script = (
        "import subprocess,sys,time\n"
        "time.sleep(0.5)\n"
        "child=subprocess.Popen([sys.executable,'-c',"
        "'import time;[time.sleep(0.2) for _ in range(300)]'],"
        "stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)\n"
        "print(child.pid,flush=True)\n"
        "[time.sleep(0.2) for _ in range(300)]\n")
    parent = subprocess.Popen([sys.executable, "-c", script],
                              stdout=subprocess.PIPE, text=True)
    job = winjobs.Job(f"p1-stage2b1-{os.getpid()}")
    try:
        job.assign_pid(parent.pid)  # before the grandchild exists
        grandchild_pid = int(parent.stdout.readline().strip())
        assert winjobs.process_alive(parent.pid) and winjobs.process_alive(grandchild_pid)
        job.terminate()
        deadline = time.monotonic() + 10
        while time.monotonic() < deadline and (winjobs.process_alive(parent.pid)
                                               or winjobs.process_alive(grandchild_pid)):
            time.sleep(0.1)
        assert not winjobs.process_alive(parent.pid)
        assert not winjobs.process_alive(grandchild_pid)
        print("job object killed the full 2-generation tree")
    finally:
        job.close()
        for proc in (parent,):
            try:
                proc.kill()
            except OSError:
                pass


@pytest.mark.skipif(os.name == "nt", reason="fail-closed check for POSIX hosts")
def test_posix_paths_fail_closed():
    from p1 import winjobs
    with pytest.raises(NotImplementedError):
        winjobs.Job("nope")
    with pytest.raises(RunnerUnavailableError):
        orchestrator_sid()
