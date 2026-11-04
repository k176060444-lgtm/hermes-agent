"""Stage-2B-1 runner protocol / attestation / Job Object offline tests.

REMEDIALIZED CONTRACT (post-audit): build_launch_request carries the approved
command digest; receipts bind stage/role/harness/model/commit/command and the
process start time; verify_execution_identity takes the trusted manifest and
enforces validate_* itself; test seams are explicit and can never yield
attested=True; runner_health honestly reports no service; poll validates the
outbox before returning a receipt.

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
                       live_process_token, manifest_sha256,
                       orchestrator_sid, process_identity,
                       validate_launch_request, validate_receipt,
                       verify_execution_identity, verify_ledger_inaccessible,
                       verify_receipt_integrity)

IS_WIN = os.name == "nt"
SID_ORCH = orchestrator_sid() if IS_WIN else "S-1-5-21-ORCH-PLACEHOLDER"
SID_AGENTX = "S-1-5-21-1229371380-3680912533-2234981468-1002"

BINDINGS = {"soul_sha256": "a" * 64, "matrix_sha256": "b" * 64,
            "spec_sha256": "c" * 64, "intent_sha256": "d" * 64,
            "reviewed_commit": "0" * 40, "input_sha256": "e" * 64,
            "frozen_harness_sha256": "f" * 64,
            "frozen_harness_version": "stub 0.0"}
COMMAND_SHA = "4" * 64


def make_request(tmp_path, command_sha256=COMMAND_SHA):
    return build_launch_request(
        task={"task_id": "T-2B1"}, stage="2", role="worker", run_id=7,
        matrix_entry={"harness": "codex", "primary_model": "provider/model-x"},
        bindings=dict(BINDINGS), worktree_path=tmp_path / "wt",
        timeout_seconds=60, idempotency_key="idem-7",
        command_sha256=command_sha256)


def make_receipt(request, exe_path, *, sid=SID_AGENTX, groups=None,
                 status="COMPLETED", exit_code=0, pid=4242,
                 start_time=1000.0, manifest_sha=None):
    payload = {"schema_version": rn.RUNNER_SCHEMA_VERSION,
               "task_id": request["task_id"], "run_id": request["run_id"],
               "idempotency_key": request["idempotency_key"],
               "stage": request["stage"], "role": request["role"],
               "harness": request["harness"], "model": request["model"],
               "reviewed_commit": request["reviewed_commit"],
               "command_sha256": request["command_sha256"],
               "agent_pid": pid, "agent_token_sid": sid,
               "agent_group_sids": groups if groups is not None else [rn.SID_USERS],
               "launch_source": "runner-service",
               "exit_code": exit_code, "started_at": 1001.0,
               "finished_at": 1002.0, "process_start_time": start_time,
               "stdout_sha256": "1" * 64, "stderr_sha256": "2" * 64,
               "capture_meta_sha256": "3" * 64,
               "harness_exe_path": str(exe_path),
               "harness_exe_sha256": request["frozen_harness_sha256"],
               "harness_version": request["frozen_harness_version"],
               "runner_manifest_sha256": manifest_sha or "m" * 64,
               "status": status}
    return payload


def make_manifest(tmp_path, *, runner_exe=None, pin=SID_AGENTX,
                  task_id="T-2B1"):
    exe = runner_exe or (tmp_path / "runnerd.exe")
    exe.parent.mkdir(parents=True, exist_ok=True)
    if not exe.exists():
        exe.write_bytes(b"RUNNERD-IMAGE")
    return {"task_id": task_id,
            "spool_inbox": str(tmp_path / "spool" / "in"),
            "spool_outbox": str(tmp_path / "spool" / "out"),
            "expected_agent_sid": pin,
            "runner_exe": str(exe),
            "runner_exe_sha256": digest_file(exe)}


def provision_home(tmp_path, manifest):
    """S2B1F-002: a trusted manifest is one placed INSIDE the task home
    (snapshots/runner_manifest.json); helpers below read it from disk."""
    home = tmp_path / "ledger-home"
    (home / "snapshots").mkdir(parents=True, exist_ok=True)
    (home / "snapshots" / "runner_manifest.json").write_text(
        canonical(manifest), encoding="utf-8")
    return home


# ------------------------------------------------------------------- request
def test_request_binds_all_identity_fields(tmp_path):
    request = make_request(tmp_path)
    validate_launch_request(request)
    for field in ("task_id", "run_id", "role", "harness", "model",
                  "soul_sha256", "matrix_sha256", "spec_sha256", "intent_sha256",
                  "reviewed_commit", "worktree_path", "idempotency_key",
                  "command_sha256", "frozen_harness_version"):
        assert request[field], field
    body = canonical({k: v for k, v in request.items() if k != "request_sha256"})
    assert sha256(body.encode()) == request["request_sha256"]
    print("request digest self-consistent; all bindings present "
          "(self-hash is tamper-evident, NOT a signature)")


def test_request_tamper_detected(tmp_path):
    request = make_request(tmp_path)
    request["model"] = "provider/sneaky-model"
    with pytest.raises(RunnerAttestationError, match="digest mismatch"):
        validate_launch_request(request)


@pytest.mark.parametrize("drop", ["soul_sha256", "idempotency_key", "run_id",
                                  "command_sha256"])
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
                             timeout_seconds=1, idempotency_key="k",
                             command_sha256=COMMAND_SHA)


def test_binding_requires_digest_shape(tmp_path):
    weak = dict(BINDINGS, soul_sha256="short")
    with pytest.raises(RunnerAttestationError, match="soul_sha256"):
        build_launch_request(task={"task_id": "T"}, stage="2", role="worker",
                             run_id=1,
                             matrix_entry={"harness": "codex", "primary_model": "m"},
                             bindings=weak, worktree_path=tmp_path,
                             timeout_seconds=1, idempotency_key="k",
                             command_sha256=COMMAND_SHA)


def test_build_requires_command_digest(tmp_path):
    with pytest.raises(RunnerAttestationError, match="command_sha256"):
        build_launch_request(task={"task_id": "T"}, stage="2", role="worker",
                             run_id=1,
                             matrix_entry={"harness": "codex", "primary_model": "m"},
                             bindings=dict(BINDINGS), worktree_path=tmp_path,
                             timeout_seconds=1, idempotency_key="k",
                             command_sha256="short")


# ------------------------------------------------------------------- receipt
def test_receipt_bound_to_request(tmp_path):
    request = make_request(tmp_path)
    receipt = make_receipt(request, tmp_path / "harness.exe")
    validate_receipt(receipt, request)


@pytest.mark.parametrize("field,value", [
    ("run_id", 999), ("role", "reviewer"), ("model", "provider/other"),
    ("harness", "opencode"), ("stage", "9"), ("reviewed_commit", "1" * 40),
    ("command_sha256", "9" * 64),
])
def test_receipt_cross_binding_rejected(tmp_path, field, value):
    """S2B1-004: the receipt must echo every approved dimension."""
    request = make_request(tmp_path)
    receipt = make_receipt(request, tmp_path / "harness.exe")
    receipt[field] = value
    with pytest.raises(RunnerAttestationError, match="not bound to request"):
        validate_receipt(receipt, request)


def test_receipt_exe_drift_rejected(tmp_path):
    request = make_request(tmp_path)
    receipt = make_receipt(request, tmp_path / "harness.exe")
    receipt["harness_exe_sha256"] = "9" * 64
    with pytest.raises(RunnerAttestationError, match="frozen snapshot"):
        validate_receipt(receipt, request)


def test_receipt_version_drift_rejected(tmp_path):
    """S2B1-004: frozen harness version is now bound."""
    request = make_request(tmp_path)
    receipt = make_receipt(request, tmp_path / "harness.exe")
    receipt["harness_version"] = "stub 9.9"
    with pytest.raises(RunnerAttestationError, match="version differs"):
        validate_receipt(receipt, request)


@pytest.mark.parametrize("status,exit_code", [
    ("COMPLETED", 1), ("FAILED", 0), ("TIMEOUT", 3), ("KILLED", 2),
])
def test_receipt_status_exit_semantics(tmp_path, status, exit_code):
    """S2B1-015: contradictory status/exit_code receipts are refused."""
    request = make_request(tmp_path)
    receipt = make_receipt(request, tmp_path / "harness.exe",
                           status=status, exit_code=exit_code)
    with pytest.raises(RunnerAttestationError, match="contradiction"):
        validate_receipt(receipt, request)


def test_receipt_time_ordering_rejected(tmp_path):
    request = make_request(tmp_path)
    receipt = make_receipt(request, tmp_path / "harness.exe")
    receipt["finished_at"] = 1.0
    receipt["started_at"] = 2.0
    with pytest.raises(RunnerAttestationError, match="finished_at"):
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
          "lives solely in the live verify path")


# ---------------------------------------------------------------- attestation
_EXE_REF = [None]


def _stub_identity(sid=SID_AGENTX, groups=None, start_time=1000.0,
                   image=None, alive=True):
    def probe(pid):
        return {"pid": pid, "alive": alive, "start_time": start_time,
                "user_sid": sid,
                "group_sids": groups if groups is not None else [rn.SID_USERS],
                "image": image or str(_EXE_REF[0])}
    return probe


def _attest(tmp_path, *, receipt=None, request=None, probe=None, pin=SID_AGENTX):
    exe = tmp_path / "harness.exe"
    exe.write_bytes(b"exe")
    if request is None:
        bindings = dict(BINDINGS, frozen_harness_sha256=digest_file(exe))
        request = build_launch_request(
            task={"task_id": "T-2B1"}, stage="2", role="worker", run_id=7,
            matrix_entry={"harness": "codex", "primary_model": "provider/model-x"},
            bindings=bindings, worktree_path=tmp_path / "wt",
            timeout_seconds=60, idempotency_key="idem-7",
            command_sha256=COMMAND_SHA)
    receipt = receipt or make_receipt(request, exe, start_time=1000.0)
    manifest = make_manifest(tmp_path, pin=pin)
    home = provision_home(tmp_path, manifest)
    _EXE_REF[0] = exe
    return verify_execution_identity(receipt=receipt, request=request,
                                     home=home,
                                     orchestrator=SID_ORCH,
                                     identity_probe=probe)


def test_identity_without_valid_request_is_refused(tmp_path):
    """S2B1-001: verify enforces the request digest itself."""
    request = make_request(tmp_path)
    request["model"] = "provider/tampered"
    receipt = make_receipt(request, tmp_path / "harness.exe")
    with pytest.raises(RunnerAttestationError, match="digest mismatch"):
        _attest(tmp_path, request=request, receipt=receipt,
                probe=_stub_identity())


def test_identity_receipt_binding_enforced(tmp_path):
    request = make_request(tmp_path)
    receipt = make_receipt(request, tmp_path / "harness.exe")
    receipt["role"] = "reviewer"
    with pytest.raises(RunnerAttestationError, match="not bound to request"):
        _attest(tmp_path, request=request, receipt=receipt, probe=_stub_identity())


def test_identity_manifest_runner_exe_pinned(tmp_path):
    """S2B1-001: the manifest's runner executable digest is re-measured."""
    exe = tmp_path / "harness.exe"
    exe.write_bytes(b"exe")
    bindings = dict(BINDINGS, frozen_harness_sha256=digest_file(exe))
    request = build_launch_request(
        task={"task_id": "T-2B1"}, stage="2", role="worker", run_id=7,
        matrix_entry={"harness": "codex", "primary_model": "provider/model-x"},
        bindings=bindings, worktree_path=tmp_path / "wt",
        timeout_seconds=60, idempotency_key="idem-7", command_sha256=COMMAND_SHA)
    receipt = make_receipt(request, exe)
    manifest = make_manifest(tmp_path)
    manifest["runner_exe_sha256"] = "0" * 64
    home = provision_home(tmp_path, manifest)
    with pytest.raises(RunnerAttestationError, match="runner executable differs"):
        verify_execution_identity(receipt=receipt, request=request,
                                  home=home,
                                  orchestrator=SID_ORCH,
                                  identity_probe=_stub_identity())


def test_identity_manifest_argument_is_gone_unanchored_dicts_impossible(tmp_path):
    """S2B1F-002: the API no longer accepts a caller-supplied manifest dict;
    trust requires the anchored file inside the task home."""
    import inspect
    params = inspect.signature(verify_execution_identity).parameters
    assert "manifest" not in params
    assert "home" in params
    request = make_request(tmp_path)
    receipt = make_receipt(request, tmp_path / "harness.exe")
    with pytest.raises(RunnerUnavailableError, match="no anchored runner manifest"):
        verify_execution_identity(receipt=receipt, request=request,
                                  home=tmp_path / "no-such-home",
                                  orchestrator=SID_ORCH,
                                  identity_probe=_stub_identity())


def test_identity_anchored_manifest_other_task_rejected(tmp_path):
    """A perfectly valid manifest anchored in home but bound to ANOTHER task
    must not authorize this task's execution."""
    exe = tmp_path / "harness.exe"
    exe.write_bytes(b"exe")
    bindings = dict(BINDINGS, frozen_harness_sha256=digest_file(exe))
    request = build_launch_request(
        task={"task_id": "T-2B1"}, stage="2", role="worker", run_id=7,
        matrix_entry={"harness": "codex", "primary_model": "provider/model-x"},
        bindings=bindings, worktree_path=tmp_path / "wt",
        timeout_seconds=60, idempotency_key="idem-7", command_sha256=COMMAND_SHA)
    receipt = make_receipt(request, exe)
    manifest = make_manifest(tmp_path, task_id="T-OTHER")
    home = provision_home(tmp_path, manifest)
    with pytest.raises(RunnerAttestationError, match="different task"):
        verify_execution_identity(receipt=receipt, request=request, home=home,
                                  orchestrator=SID_ORCH,
                                  identity_probe=_stub_identity())


def test_identity_rejects_orchestrator_sid(tmp_path):
    """Manifest mis-pinned to the orchestrator itself: the live measurement
    must still refuse to bless a same-identity agent."""
    exe = tmp_path / "harness.exe"
    exe.write_bytes(b"exe")
    bindings = dict(BINDINGS, frozen_harness_sha256=digest_file(exe))
    request = build_launch_request(
        task={"task_id": "T-2B1"}, stage="2", role="worker", run_id=7,
        matrix_entry={"harness": "codex", "primary_model": "provider/model-x"},
        bindings=bindings, worktree_path=tmp_path / "wt",
        timeout_seconds=60, idempotency_key="idem-7", command_sha256=COMMAND_SHA)
    receipt = make_receipt(request, exe, sid=SID_ORCH)
    with pytest.raises(RunnerAttestationError, match="orchestrator identity"):
        _attest(tmp_path, request=request, receipt=receipt,
                probe=_stub_identity(sid=SID_ORCH), pin=SID_ORCH)


def test_identity_rejects_receipt_sid_off_pin(tmp_path):
    exe = tmp_path / "harness.exe"
    exe.write_bytes(b"exe")
    bindings = dict(BINDINGS, frozen_harness_sha256=digest_file(exe))
    request = build_launch_request(
        task={"task_id": "T-2B1"}, stage="2", role="worker", run_id=7,
        matrix_entry={"harness": "codex", "primary_model": "provider/model-x"},
        bindings=bindings, worktree_path=tmp_path / "wt",
        timeout_seconds=60, idempotency_key="idem-7", command_sha256=COMMAND_SHA)
    receipt = make_receipt(request, exe, sid="S-1-5-21-777")
    with pytest.raises(RunnerAttestationError, match="does not match manifest pin"):
        _attest(tmp_path, request=request, receipt=receipt,
                probe=_stub_identity(sid="S-1-5-21-777"))


def test_identity_rejects_admin_member(tmp_path):
    exe = tmp_path / "harness.exe"
    exe.write_bytes(b"exe")
    bindings = dict(BINDINGS, frozen_harness_sha256=digest_file(exe))
    request = build_launch_request(
        task={"task_id": "T-2B1"}, stage="2", role="worker", run_id=7,
        matrix_entry={"harness": "codex", "primary_model": "provider/model-x"},
        bindings=bindings, worktree_path=tmp_path / "wt",
        timeout_seconds=60, idempotency_key="idem-7", command_sha256=COMMAND_SHA)
    receipt = make_receipt(request, exe,
                           groups=[rn.SID_ADMINISTRATORS, rn.SID_USERS])
    with pytest.raises(RunnerAttestationError, match="Administrators"):
        _attest(tmp_path, request=request, receipt=receipt,
                probe=_stub_identity(groups=[rn.SID_ADMINISTRATORS, rn.SID_USERS]))


def test_identity_rejects_receipt_live_sid_divergence(tmp_path):
    exe = tmp_path / "harness.exe"
    exe.write_bytes(b"exe")
    bindings = dict(BINDINGS, frozen_harness_sha256=digest_file(exe))
    request = build_launch_request(
        task={"task_id": "T-2B1"}, stage="2", role="worker", run_id=7,
        matrix_entry={"harness": "codex", "primary_model": "provider/model-x"},
        bindings=bindings, worktree_path=tmp_path / "wt",
        timeout_seconds=60, idempotency_key="idem-7", command_sha256=COMMAND_SHA)
    receipt = make_receipt(request, exe, sid=SID_AGENTX)
    with pytest.raises(RunnerAttestationError, match="differs from receipt"):
        _attest(tmp_path, request=request, receipt=receipt,
                probe=_stub_identity(sid="S-1-5-21-999"))


def test_identity_rejects_start_time_mismatch(tmp_path):
    """S2B1-003: PID reuse / stale receipt is defeated by the creation-time
    binding."""
    exe = tmp_path / "harness.exe"
    exe.write_bytes(b"exe")
    bindings = dict(BINDINGS, frozen_harness_sha256=digest_file(exe))
    request = build_launch_request(
        task={"task_id": "T-2B1"}, stage="2", role="worker", run_id=7,
        matrix_entry={"harness": "codex", "primary_model": "provider/model-x"},
        bindings=bindings, worktree_path=tmp_path / "wt",
        timeout_seconds=60, idempotency_key="idem-7", command_sha256=COMMAND_SHA)
    receipt = make_receipt(request, exe, start_time=1000.0)
    with pytest.raises(RunnerAttestationError, match="creation time differs"):
        _attest(tmp_path, request=request, receipt=receipt,
                probe=_stub_identity(start_time=9999.0))


def test_identity_rejects_exe_digest_drift(tmp_path):
    """Frozen pin differs from the actual bytes on disk -> refused."""
    exe = tmp_path / "harness.exe"
    exe.write_bytes(b"exe")
    request = build_launch_request(
        task={"task_id": "T-2B1"}, stage="2", role="worker", run_id=7,
        matrix_entry={"harness": "codex", "primary_model": "provider/model-x"},
        bindings=dict(BINDINGS), worktree_path=tmp_path / "wt",
        timeout_seconds=60, idempotency_key="idem-7", command_sha256=COMMAND_SHA)
    receipt = make_receipt(request, exe)
    with pytest.raises(RunnerAttestationError, match="frozen snapshot"):
        _attest(tmp_path, request=request, receipt=receipt,
                probe=_stub_identity())


def test_test_seam_never_attests(tmp_path):
    """S2B1-002: the unit-test substitute runs every check but can NEVER
    yield attested=True."""
    outcome = _attest(tmp_path, probe=_stub_identity())
    assert outcome["attested"] is False
    assert outcome["test_seam"] is True
    assert "test substitute" in outcome["note"]
    print("test seam result explicitly unattested")


def test_ledger_check_blocks_exposed_dacl(tmp_path):
    """S2B1-007: child paths are enumerated; a leak on ANY checked path
    blocks."""
    ledger = tmp_path / "ledger"
    (ledger / "logs").mkdir(parents=True)
    (ledger / "state.sqlite").write_bytes(b"db")

    def query(paths):
        records = []
        for path in paths:
            principals = []
            if Path(path).name == "logs":  # leak ONLY on a child
                principals = [SID_AGENTX]
            records.append({"path": str(path), "principals": principals})
        return records
    with pytest.raises(RunnerAttestationError, match="exposes agent principals"):
        verify_ledger_inaccessible(ledger, SID_AGENTX, [rn.SID_USERS], query=query)


def test_ledger_check_passes_private_dacl(tmp_path):
    ledger = tmp_path / "ledger"
    (ledger / "snapshots").mkdir(parents=True)

    def query(paths):
        return [{"path": str(path), "principals": [rn.SID_LOCAL_SYSTEM]}
                for path in paths]
    outcome = verify_ledger_inaccessible(ledger, SID_AGENTX, [rn.SID_USERS],
                                         query=query)
    assert len(outcome["paths_checked"]) == 2  # root + snapshots
    print("ledger DACL verifier: enumerated child paths clean -> pass")


def test_receipt_integrity_requires_capture_dir(tmp_path):
    """S2B1-003/005 boundary: post-exit verification without orchestrator-
    owned capture files fails closed."""
    request = make_request(tmp_path)
    manifest = make_manifest(tmp_path)
    receipt = make_receipt(request, tmp_path / "harness.exe",
                           manifest_sha=manifest_sha256(manifest))
    with pytest.raises(RunnerAttestationError, match="capture re-hash unavailable"):
        verify_receipt_integrity(receipt=receipt, request=request,
                                 home=provision_home(tmp_path, manifest), capture_dir=None)


def test_receipt_integrity_rehashes_captures(tmp_path):
    request = make_request(tmp_path)
    manifest = make_manifest(tmp_path)
    captures = tmp_path / "captures"
    captures.mkdir()
    (captures / "7.stdout.bin").write_bytes(b"OUT")
    (captures / "7.stderr.bin").write_bytes(b"ERR")
    (captures / "7.capture-meta.json").write_bytes(b"{}")
    receipt = make_receipt(request, tmp_path / "harness.exe",
                           manifest_sha=manifest_sha256(manifest))
    receipt["stdout_sha256"] = digest_file(captures / "7.stdout.bin")
    receipt["stderr_sha256"] = digest_file(captures / "7.stderr.bin")
    receipt["capture_meta_sha256"] = digest_file(captures / "7.capture-meta.json")
    outcome = verify_receipt_integrity(receipt=receipt, request=request,
                                       home=provision_home(tmp_path, manifest), capture_dir=captures)
    assert outcome["integrity_verified"] is True
    assert outcome["attested"] is False  # never a live identity claim
    assert outcome["runner_identity_attested"] is False
    assert outcome["levels"]["L4_identity_attested"] is False
    assert outcome["levels"]["L3_manifest_anchored"] is True
    (captures / "7.stdout.bin").write_bytes(b"TAMPERED")
    with pytest.raises(RunnerAttestationError, match="capture digest mismatch"):
        verify_receipt_integrity(receipt=receipt, request=request,
                                 home=provision_home(tmp_path, manifest), capture_dir=captures)


def test_receipt_integrity_rejects_foreign_manifest(tmp_path):
    request = make_request(tmp_path)
    manifest = make_manifest(tmp_path)
    receipt = make_receipt(request, tmp_path / "harness.exe",
                           manifest_sha="e" * 64)
    with pytest.raises(RunnerAttestationError, match="different runner manifest"):
        verify_receipt_integrity(receipt=receipt, request=request,
                                 home=provision_home(tmp_path, manifest), capture_dir=tmp_path)


# ------------------------------------------------------------------- client
def test_client_fails_closed_without_manifest(tmp_path):
    client = RunnerClient(tmp_path)
    health = client.runner_health()
    assert health["available"] is False
    assert health["manifest_provisioned"] is False
    request = make_request(tmp_path)
    with pytest.raises(RunnerUnavailableError):
        client.launch(request, "prompt")


def test_client_health_reports_service_not_deployed(tmp_path):
    """S2B1-006: a complete manifest must NOT flip available=True while no
    runner service exists."""
    snapshot = tmp_path / "snapshots"
    snapshot.mkdir(parents=True)
    manifest = make_manifest(tmp_path)
    (snapshot / "runner_manifest.json").write_text(
        canonical(manifest), encoding="utf-8")
    client = RunnerClient(tmp_path)
    health = client.runner_health()
    assert health["manifest_provisioned"] is True
    assert health["available"] is False
    assert "NOT deployed" in health["reason"]
    with pytest.raises(RunnerUnavailableError):
        client.launch(make_request(tmp_path), "prompt")


def test_client_rejects_manifest_without_pin(tmp_path):
    snapshot = tmp_path / "snapshots"
    snapshot.mkdir()
    manifest = snapshot / "runner_manifest.json"
    manifest.write_text('{"spool_inbox": "/x"}\n', encoding="utf-8")
    client = RunnerClient(tmp_path)
    with pytest.raises(RunnerUnavailableError, match="incomplete"):
        client.manifest()


def test_client_poll_not_dispatched(tmp_path):
    client = RunnerClient(tmp_path)
    request = make_request(tmp_path)
    assert client.poll(request)["state"] == "NO_RUNNER"


def test_client_poll_rejects_junk_receipt(tmp_path):
    """S2B1-005: garbage in the outbox can never come back as trusted."""
    snapshot = tmp_path / "snapshots"
    snapshot.mkdir(parents=True)
    outbox = tmp_path / "spool" / "out"
    outbox.mkdir(parents=True)
    manifest = make_manifest(tmp_path)
    (snapshot / "runner_manifest.json").write_text(
        canonical(manifest), encoding="utf-8")
    request = make_request(tmp_path)
    (outbox / "7.receipt.json").write_text(
        '{"status": "COMPLETED", "agent_pid": 1, "anything": 1}',
        encoding="utf-8")
    outcome = RunnerClient(tmp_path).poll(request)
    assert outcome["state"] == "RECEIPT_UNVERIFIED"
    assert outcome["validated"] is False
    assert outcome["reconciliation_required"] is True


def test_client_poll_accepts_bound_receipt(tmp_path):
    snapshot = tmp_path / "snapshots"
    snapshot.mkdir(parents=True)
    outbox = tmp_path / "spool" / "out"
    outbox.mkdir(parents=True)
    manifest = make_manifest(tmp_path)
    (snapshot / "runner_manifest.json").write_text(
        canonical(manifest), encoding="utf-8")
    request = make_request(tmp_path)
    receipt = make_receipt(request, tmp_path / "harness.exe",
                           manifest_sha=manifest_sha256(manifest))
    (outbox / "7.receipt.json").write_text(
        canonical(receipt), encoding="utf-8")
    outcome = RunnerClient(tmp_path).poll(request)
    assert outcome["state"] == "RECEIPT"
    assert outcome["validated"] is True
    assert outcome["reconciliation_required"] is False


# ------------------------------------------------------------------- win32
@pytest.mark.skipif(not IS_WIN, reason="live token API is Windows-only")
def test_windows_live_token_of_self():
    info = live_process_token(os.getpid())
    orch = orchestrator_sid()
    assert info["user_sid"] == orch
    assert rn.SID_ADMINISTRATORS in info["group_sids"]  # KK is admin: proves
    # the probe sees real group membership -- exactly why agentx must fail this
    print(f"live token probe verified: {orch}, groups={len(info['group_sids'])}")


@pytest.mark.skipif(not IS_WIN, reason="process identity is Windows-only")
def test_windows_process_identity_self():
    """S2B1-002/003 positive control: full instance measurement on a live
    process (liveness + creation time + SID + groups + image)."""
    ident = process_identity(os.getpid())
    assert ident["alive"] is True
    assert ident["user_sid"] == SID_ORCH
    assert ident["start_time"] > 1_500_000_000  # sane epoch seconds
    assert Path(ident["image"]).is_file()
    with pytest.raises(RunnerAttestationError, match="exited|cannot open"):
        process_identity(999999)


@pytest.mark.skipif(not IS_WIN, reason="Job Objects are Windows-only")
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
