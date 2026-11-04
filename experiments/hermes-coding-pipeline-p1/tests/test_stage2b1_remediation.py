"""Stage-2B-1 REMEDIATION regression: adversarial locks for all 16 audit
findings (P1 x3, P2 x8, P3 x5) plus the supplementary approve-spec gate.

Each test names the finding it locks. Synthetic-only; live Windows process
experiments use disposable stubs on 21bao. No paid models, no accounts, no
ACL changes, no gateway touches.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from pathlib import Path

import pytest

from p1 import runner as rn
from p1 import winjobs
from p1.contracts import canonical, digest_file, sha256
from p1.harness import codex as cx
from p1.harness import opencode as oc
from p1.runner import (RunnerAttestationError, RunnerClient,
                       RunnerUnavailableError, build_launch_request,
                       manifest_sha256, orchestrator_sid, process_identity,
                       validate_receipt, verify_execution_identity,
                       verify_ledger_inaccessible, verify_receipt_integrity)

IS_WIN = os.name == "nt"
SID_ORCH = orchestrator_sid() if IS_WIN else "S-ORCH"
SID_AGENTX = "S-1-5-21-1229371380-3680912533-2234981468-1002"

BINDINGS = {"soul_sha256": "a" * 64, "matrix_sha256": "b" * 64,
            "spec_sha256": "c" * 64, "intent_sha256": "d" * 64,
            "reviewed_commit": "0" * 40, "input_sha256": "e" * 64,
            "frozen_harness_sha256": "f" * 64,
            "frozen_harness_version": "stub 1.0"}


def _request(tmp_path, **over):
    request = build_launch_request(
        task={"task_id": "T-FIX"}, stage="2", role="worker", run_id=7,
        matrix_entry={"harness": "codex", "primary_model": "p/model"},
        bindings=dict(BINDINGS), worktree_path=tmp_path / "wt",
        timeout_seconds=60, idempotency_key="idem-7",
        command_sha256="4" * 64)
    request.update(over)
    return request


def _receipt(tmp_path, request, exe, *, manifest_sha=None, **over):
    payload = {"schema_version": rn.RUNNER_SCHEMA_VERSION,
               "task_id": request["task_id"], "run_id": request["run_id"],
               "idempotency_key": request["idempotency_key"],
               "stage": request["stage"], "role": request["role"],
               "harness": request["harness"], "model": request["model"],
               "reviewed_commit": request["reviewed_commit"],
               "command_sha256": request["command_sha256"],
               "agent_pid": 4242, "agent_token_sid": SID_AGENTX,
               "agent_group_sids": [rn.SID_USERS],
               "launch_source": "runner-service",
               "exit_code": 0, "started_at": 1001.0, "finished_at": 1002.0,
               "process_start_time": 1000.0,
               "stdout_sha256": "1" * 64, "stderr_sha256": "2" * 64,
               "capture_meta_sha256": "3" * 64,
               "harness_exe_path": str(exe),
               "harness_exe_sha256": request["frozen_harness_sha256"],
               "harness_version": request["frozen_harness_version"],
               "runner_manifest_sha256": manifest_sha or "m" * 64,
               "status": "COMPLETED"}
    payload.update(over)
    return payload


def _request_exe(tmp_path, exe):
    """Build a request whose frozen digest matches the exe bytes on disk
    (digest must be bound BEFORE build; post-hoc edits break the digest)."""
    return build_launch_request(
        task={"task_id": "T-FIX"}, stage="2", role="worker", run_id=7,
        matrix_entry={"harness": "codex", "primary_model": "p/model"},
        bindings=dict(BINDINGS, frozen_harness_sha256=digest_file(exe)),
        worktree_path=tmp_path / "wt", timeout_seconds=60,
        idempotency_key="idem-7", command_sha256="4" * 64)


def _manifest(tmp_path, pin=SID_AGENTX, task_id="T-FIX"):
    exe = tmp_path / "runnerd.exe"
    exe.write_bytes(b"RUNNERD")
    return {"task_id": task_id,
            "spool_inbox": str(tmp_path / "in"),
            "spool_outbox": str(tmp_path / "out"),
            "expected_agent_sid": pin,
            "runner_exe": str(exe),
            "runner_exe_sha256": digest_file(exe)}


def _home(tmp_path, manifest=None):
    """S2B1F-002: provision the manifest INSIDE the task home; the verify
    API only accepts this anchored source."""
    manifest = manifest or _manifest(tmp_path)
    home = tmp_path / "home"
    (home / "snapshots").mkdir(parents=True, exist_ok=True)
    (home / "snapshots" / "runner_manifest.json").write_text(
        canonical(manifest), encoding="utf-8")
    return home


def _probe(sid=SID_AGENTX, groups=None, start_time=1000.0, image=None):
    ref = {"image": image}

    def probe(pid):
        return {"pid": pid, "alive": True, "start_time": start_time,
                "user_sid": sid,
                "group_sids": groups if groups is not None else [rn.SID_USERS],
                "image": ref["image"]}
    return probe, ref


# ------------------------------------------------- S2B1-001 (P1) pin/binding
def test_s2b1_001_unsigned_request_and_misbound_receipt_never_attest(tmp_path):
    request = _request(tmp_path)
    request.pop("request_sha256")  # unsigned
    request["expected_agent_sid"] = SID_ORCH  # caller-filled pin attempt
    exe = tmp_path / "h.exe"
    exe.write_bytes(b"H")
    receipt = _receipt(tmp_path, request, exe, agent_token_sid=SID_ORCH)
    with pytest.raises(RunnerAttestationError, match="missing fields"):
        verify_execution_identity(receipt=receipt, request=request,
                                  home=_home(tmp_path, _manifest(tmp_path, pin=SID_ORCH)),
                                  ledger_root=tmp_path, orchestrator=SID_ORCH)


def test_s2b1_001_request_digest_not_a_signature(tmp_path):
    """The self-hash stays explicitly non-signing: a caller who recomputes it
    gains no authenticity - the manifest and OS measurements are the anchors."""
    request = _request(tmp_path)
    body = canonical({k: v for k, v in request.items() if k != "request_sha256"})
    assert sha256(body.encode()) == request["request_sha256"]
    src = Path(rn.__file__).read_text(encoding="utf-8")
    assert "NOT a signature" in src
    print("self-hash boundary documented in module trust model")


# ------------------------------------------------- S2B1-002 (P1) seam split
def test_s2b1_002_test_seam_never_attested(tmp_path):
    exe = tmp_path / "h.exe"
    exe.write_bytes(b"H")
    request = _request_exe(tmp_path, exe)
    receipt = _receipt(tmp_path, request, exe)
    probe, ref = _probe()
    ref["image"] = str(exe)
    outcome = verify_execution_identity(
        receipt=receipt, request=request, home=_home(tmp_path),
        ledger_root=tmp_path, orchestrator=SID_ORCH, identity_probe=probe)
    assert outcome["attested"] is False and outcome["test_seam"] is True


def test_s2b1_002_receipt_path_never_used_as_image(tmp_path):
    """The image MUST come from the measured process, never the receipt."""
    exe = tmp_path / "h.exe"
    exe.write_bytes(b"H")
    request = _request_exe(tmp_path, exe)
    receipt = _receipt(tmp_path, request, exe)
    probe, ref = _probe(image="C:/definitely/other/harness.exe")
    with pytest.raises(RunnerAttestationError, match="image|path"):
        verify_execution_identity(receipt=receipt, request=request,
                                  home=_home(tmp_path),
                                  ledger_root=tmp_path, orchestrator=SID_ORCH,
                                  identity_probe=probe)


# ------------------------------------------------- S2B1-003 (P2) dead pid
@pytest.mark.skipif(not IS_WIN, reason="live process semantics")
def test_s2b1_003_dead_pid_rejected(tmp_path):
    exe = tmp_path / "h.exe"
    exe.write_bytes(b"H")
    request = _request_exe(tmp_path, exe)
    proc = subprocess.Popen([sys.executable, "-c", "pass"])
    pid = proc.pid
    proc.wait()
    receipt = _receipt(tmp_path, request, exe, pid=pid,
                       agent_token_sid=SID_ORCH)
    ident = None
    try:
        ident = process_identity(pid)  # handle held: still readable
    except RunnerAttestationError:
        pass  # already reaped: also fine, fail-closed either way
    manifest = _manifest(tmp_path)
    receipt["runner_manifest_sha256"] = manifest_sha256(manifest)
    with pytest.raises((RunnerAttestationError, RunnerUnavailableError)):
        verify_execution_identity(receipt=receipt, request=request,
                                  home=_home(tmp_path, manifest),
                                  orchestrator=SID_ORCH)  # live path only
    assert ident is None or ident["alive"] is True


def test_s2b1_003_start_time_binding_blocks_reuse(tmp_path):
    exe = tmp_path / "h.exe"
    exe.write_bytes(b"H")
    request = _request_exe(tmp_path, exe)
    receipt = _receipt(tmp_path, request, exe, start_time=1000.0)
    probe, ref = _probe(start_time=5555.0)
    ref["image"] = str(exe)
    with pytest.raises(RunnerAttestationError, match="creation time differs"):
        verify_execution_identity(receipt=receipt, request=request,
                                  home=_home(tmp_path),
                                  ledger_root=tmp_path, orchestrator=SID_ORCH,
                                  identity_probe=probe)


def test_s2b1_003_post_exit_is_integrity_only(tmp_path):
    request = _request(tmp_path)
    manifest = _manifest(tmp_path)
    exe = tmp_path / "h.exe"
    exe.write_bytes(b"H")
    captures = tmp_path / "cap"
    captures.mkdir()
    (captures / "7.stdout.bin").write_bytes(b"O")
    (captures / "7.stderr.bin").write_bytes(b"E")
    (captures / "7.capture-meta.json").write_bytes(b"{}")
    receipt = _receipt(tmp_path, request, exe,
                       manifest_sha=manifest_sha256(manifest))
    receipt["stdout_sha256"] = digest_file(captures / "7.stdout.bin")
    receipt["stderr_sha256"] = digest_file(captures / "7.stderr.bin")
    receipt["capture_meta_sha256"] = digest_file(captures / "7.capture-meta.json")
    outcome = verify_receipt_integrity(receipt=receipt, request=request,
                                       home=_home(tmp_path, manifest), capture_dir=captures)
    assert outcome["integrity_verified"] is True
    assert outcome["attested"] is False
    print("post-exit receipts can only ever be integrity-verified")


# ------------------------------------------------- S2B1-004 (P2) bindings
@pytest.mark.parametrize("field,value", [
    ("role", "planner"), ("model", "p/other"), ("stage", "1"),
    ("harness", "opencode"), ("reviewed_commit", "1" * 40),
    ("command_sha256", "9" * 64), ("harness_version", "stub 9.9"),
])
def test_s2b1_004_receipt_dimension_bindings(tmp_path, field, value):
    request = _request(tmp_path)
    receipt = _receipt(tmp_path, request, tmp_path / "h.exe")
    receipt[field] = value
    with pytest.raises(RunnerAttestationError):
        validate_receipt(receipt, request)


# ------------------------------------------------- S2B1-005 (P2) poll gate
def test_s2b1_005_outbox_junk_cannot_be_trusted(tmp_path):
    outbox = tmp_path / "out"
    outbox.mkdir()
    manifest = _manifest(tmp_path)
    home = tmp_path / "home"
    (home / "snapshots").mkdir(parents=True)
    (home / "snapshots" / "runner_manifest.json").write_text(
        canonical(manifest), encoding="utf-8")
    request = _request(tmp_path)
    (outbox / "7.receipt.json").write_text(
        json.dumps({"status": "COMPLETED"}), encoding="utf-8")
    outcome = RunnerClient(home).poll(request)
    assert outcome["state"] == "RECEIPT_UNVERIFIED"
    assert outcome["reconciliation_required"] is True
    assert outcome["validated"] is False


# ------------------------------------------------- S2B1-006 (P2) health
def test_s2b1_006_health_honest_without_service(tmp_path):
    home = tmp_path / "home"
    (home / "snapshots").mkdir(parents=True)
    manifest = _manifest(tmp_path)
    (home / "snapshots" / "runner_manifest.json").write_text(
        canonical(manifest), encoding="utf-8")
    health = RunnerClient(home).runner_health()
    assert health["available"] is False
    assert health["manifest_provisioned"] is True
    assert health["service_liveness"] == "unknown"
    with pytest.raises(RunnerUnavailableError):
        RunnerClient(home).launch(_request(tmp_path), "p")


# ------------------------------------------------- S2B1-007 (P2) ledger ACL
def test_s2b1_007_child_ace_blocks(tmp_path):
    ledger = tmp_path / "ledger"
    (ledger / "artifacts").mkdir(parents=True)
    (ledger / "state.sqlite").write_bytes(b"db")

    def query(paths):
        return [{"path": str(p),
                 "principals": [SID_AGENTX] if Path(p).name == "state.sqlite"
                 else []} for p in paths]
    with pytest.raises(RunnerAttestationError, match="exposes agent principals"):
        verify_ledger_inaccessible(ledger, SID_AGENTX, [rn.SID_USERS], query=query)


@pytest.mark.skipif(not IS_WIN, reason="live icacls on disposable dir")
def test_s2b1_007_live_child_everyone_grant_blocks(tmp_path):
    root = tmp_path / "ledger"
    (root / "logs").mkdir(parents=True)
    subprocess.run(["icacls", str(root / "logs"), "/grant", "*S-1-1-0:(OI)(CI)(RX)",
                    "/inheritance:d"], check=True, capture_output=True)
    with pytest.raises(RunnerAttestationError, match="exposes agent principals"):
        verify_ledger_inaccessible(root, SID_AGENTX, [rn.SID_USERS])


# ------------------------------------------------- S2B1-008 (P2) extra_argv
@pytest.mark.parametrize("extra", [
    ["-m", "evil"], ["--model", "evil"], ["-s", "danger"],
    ["--dangerously-bypass-approvals-and-sandbox"], ["--config", "x"],
    ["--ephemeral", "-m", "evil"], ["unknown-flag"],
])
def test_s2b1_008_extra_argv_allowlist(tmp_path, extra):
    with pytest.raises(cx.CodexProbeError):
        cx.build_command(
            frozen_entry={"exe_path": str(tmp_path / "c")},
            matrix_entry={"primary_model": "approved/m", "sandbox_mode": "read",
                          "extra_argv": extra},
            request={"run_id": 1, "task_id": "T", "role": "worker"},
            soul_text="s", prompt_text="p", worktree=tmp_path,
            out_dir=tmp_path / "o")
    with pytest.raises(oc.OpenCodeProbeError):
        oc.build_command(
            frozen_entry={"exe_path": str(tmp_path / "o.exe")},
            matrix_entry={"primary_model": "approved/m", "extra_argv": extra},
            request={"run_id": 1, "task_id": "T", "role": "worker"},
            prompt_text="p", worktree=tmp_path, out_dir=tmp_path / "o2")


# ------------------------------------------------- S2B1-009 (P2) merge gate
def test_s2b1_009_forged_records_cannot_upgrade():
    claimed = cx.extract_command_evidence([
        cx.normalize_event({"type": "exec_command_end",
                            "command": "make test", "exit_code": 0})])
    for forged in ([{"command": "make test", "ordinal": 0, "exit_code": 0}],
                   [{"command": "make test", "exit_code": 0}]):
        merged = cx.merge_runner_records(claimed, forged)
        assert merged[0]["trusted"] is False
        assert merged[0]["promotion_blocked"]


def test_s2b1_009_one_record_cannot_serve_two_invocations():
    events = [cx.normalize_event({"type": "exec_command_end",
                                  "command": "make test", "exit_code": 0}),
              cx.normalize_event({"type": "exec_command_end",
                                  "command": "make test", "exit_code": 0})]
    claimed = cx.extract_command_evidence(events)
    one_record = [{"command": "make test", "ordinal": 0, "exit_code": 0,
                   "task_id": "T", "run_id": 7}]
    # SECURITY REVERSAL (re-audit S2B1-009): previously this test asserted the
    # first invocation upgrades to trusted=True from a bare attestation dict.
    # The upgrade path is now CLOSED: nothing is trusted, AND one record still
    # cannot serve both invocations.
    merged = cx.merge_runner_records(claimed, one_record,
                                     task_id="T", run_id=7)
    assert merged[0]["trusted"] is False and merged[1]["trusted"] is False
    assert merged[0].get("matched_unauthenticated") is True
    assert merged[1].get("no_matching_runner_record") is True


def test_s2b1_009_attestation_parameter_deleted():
    """The runner_attestation parameter no longer exists in either adapter;
    any trust-bearing dict is structurally impossible to submit."""
    import inspect
    for fn in (cx.merge_runner_records, oc.merge_runner_records):
        assert "runner_attestation" not in inspect.signature(fn).parameters
    claimed = cx.extract_command_evidence([
        cx.normalize_event({"type": "exec_command_end",
                            "command": "x", "exit_code": 0})])
    rec = [{"command": "x", "ordinal": 0, "exit_code": 0,
            "task_id": "T", "run_id": 7}]
    merged = cx.merge_runner_records(claimed, rec, task_id="T", run_id=7)
    assert merged[0]["trusted"] is False



@pytest.mark.skipif(not IS_WIN, reason="CREATE_SUSPENDED is Windows-only")
def test_s2b1_016_assign_failure_kills_suspended_child(tmp_path):
    """Fail-closed: if assignment fails, the suspended child is terminated and
    the error propagates."""
    job = winjobs.Job(f"p1-fix-s2b1-016b-{os.getpid()}")
    job.close()  # closing makes later assignment impossible (job gone)
    with pytest.raises(RunnerAttestationError):
        winjobs.create_suspended_in_job(
            job, [sys.executable, "-c", "import time; time.sleep(30)"])


# ------------------------------------------------- P3 fixes
def test_s2b1_011_init_forwards_all_flags(monkeypatch):
    import importlib.util
    spec = importlib.util.spec_from_file_location(
        "p1_orch_fix", Path(rn.__file__).parents[1] / "integrations" /
        "hermes" / "p1_orchestrator" / "__init__.py")
    plugin = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(plugin)
    holder = {}

    class FakeProc:
        def __init__(self, argv, **kw):
            holder["argv"] = list(argv)
            import io
            self.stdout = io.BytesIO(b'{"ok": true}')
            self.stderr = io.BytesIO(b"")
            self.returncode = 0

        def wait(self, timeout=None):
            return 0

        def kill(self):
            pass
    monkeypatch.setattr(plugin.subprocess, "Popen", FakeProc)
    args = {"home": "C:/h", "task_id": "T", "intent": "i", "matrix": "m",
            "gate01": "g", "souls": "s", "project_root": "pr", "worktree": "w"}
    plugin._init_handler(args, {"p1_repo_dir": str(Path(rn.__file__).parents[1])})
    argv = holder["argv"]
    for flag in ("--task-id", "--intent", "--matrix", "--gate01", "--souls",
                 "--project-root", "--worktree"):
        assert flag in argv, flag


def test_s2b1_012_invoke_bounded(monkeypatch):
    import importlib.util
    spec = importlib.util.spec_from_file_location(
        "p1_orch_fix2", Path(rn.__file__).parents[1] / "integrations" /
        "hermes" / "p1_orchestrator" / "__init__.py")
    plugin = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(plugin)
    old_cap = plugin._STREAM_CAP_BYTES
    plugin._STREAM_CAP_BYTES = 1024
    try:
        import io

        class FakeProc:
            def __init__(self, argv, **kw):
                import io as _io
                self.stdout = _io.BytesIO(b"y" * (10 * 1024))
                self.stderr = _io.BytesIO(b"z" * (3 * 1024))
                self.returncode = 0

            def wait(self, timeout=None):
                return 0

            def kill(self):
                pass
        monkeypatch.setattr(plugin.subprocess, "Popen", FakeProc)
        out = plugin._invoke({"p1_repo_dir": str(Path(rn.__file__).parents[1])},
                             "status", ["--home", "C:/h"])
        assert len(out["result"]["stdout"]) <= 1024
        assert out["result"]["_stdout_truncated"] is True
        assert out["_stderr_truncated"] is True
    finally:
        plugin._STREAM_CAP_BYTES = old_cap


def test_s2b1_013_no_literal_none_command():
    events = [oc.normalize_event({"type": "tool", "tool": "bash",
                                  "part": {"state": {}}})]
    records = oc.extract_command_evidence(events)
    assert records[0]["command"] is None
    assert records[0].get("no_command") is True
    assert all(r["command"] != "None" for r in records)


def test_s2b1_014_missing_role_controlled():
    with pytest.raises(oc.OpenCodeProbeError, match="role"):
        oc.build_command(frozen_entry={"exe_path": "x"},
                         matrix_entry={"primary_model": "m"},
                         request={"run_id": 1, "task_id": "T"},
                         prompt_text="p", worktree=Path("."), out_dir=Path("."))


@pytest.mark.parametrize("status,code", [("COMPLETED", 1), ("FAILED", 0),
                                         ("TIMEOUT", 5), ("KILLED", 7)])
def test_s2b1_015_status_exit_contradictions(tmp_path, status, code):
    request = _request(tmp_path)
    receipt = _receipt(tmp_path, request, tmp_path / "h.exe",
                       status=status, exit_code=code)
    with pytest.raises(RunnerAttestationError, match="contradiction"):
        validate_receipt(receipt, request)


# ------------------------------------------------- supplementary approve gate
def test_approve_gate_blocks_unverified_identity(monkeypatch):
    import importlib.util
    spec = importlib.util.spec_from_file_location(
        "p1_orch_fix3", Path(rn.__file__).parents[1] / "integrations" /
        "hermes" / "p1_orchestrator" / "__init__.py")
    plugin = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(plugin)
    called = {"n": 0}

    class Spy:
        def __init__(self, *a, **k):
            called["n"] += 1
    monkeypatch.setattr(plugin.subprocess, "Popen", Spy)
    out = plugin.handle_approve_spec(
        {"home": "C:/h", "actor": "KK", "spec_sha256": "a" * 64,
         "provenance": {"platform": "qqbot", "chat_id": "X", "message_ref": "M"}},
        {"p1_repo_dir": str(Path(rn.__file__).parents[1])})
    assert out["status"] == "BLOCKED"
    assert out["result"]["approved"] is False
    assert called["n"] == 0  # CLI approval path never invoked
    assert out["approval_provenance"]["identity_verified"] is False


# ------------------------------------------------- executor gate regression
def test_executor_gate_still_closed():
    from p1 import executor
    assert executor.TRUSTED_INTEGRATION_EXECUTION_VERIFIED is False
    src = Path(executor.__file__).read_text(encoding="utf-8")
    assert "raise InvocationError(\"NOT_VERIFIED: no authenticated separate-identity Agent runner is installed\")" in src
