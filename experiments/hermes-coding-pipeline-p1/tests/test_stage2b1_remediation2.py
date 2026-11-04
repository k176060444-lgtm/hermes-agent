"""Round-2 remediation adversarial suite (independent re-audit S2B1-009 +
S2B1F-002). Every case is a SECURITY assertion: the trust-promotion path is
CLOSED, and fabricated manifests can never masquerade as identity attestation.

Fixtures are REUSED from the proven round-1 remediation suite (same
schema-v2 request/receipt builders) so nothing here diverges from the real
contract. Offline only: no accounts, no ACLs, no services, no paid models,
no real execution.
"""
import inspect
from pathlib import Path

import pytest

from p1 import runner
from p1.contracts import digest_file
from p1.harness import codex as cx
from p1.harness import opencode as oc
from p1.runner import (RunnerAttestationError, RunnerUnavailableError,
                       manifest_sha256, verify_execution_identity,
                       verify_receipt_integrity)

from test_stage2b1_remediation import (SID_AGENTX, SID_ORCH, _home, _manifest,
                                       _probe, _receipt, _request,
                                       _request_exe)


def _claimed(command="pytest -q", exit_code=0):
    return cx.extract_command_evidence([
        cx.normalize_event({"type": "exec_command_end",
                            "command": command, "exit_code": exit_code})])


def _record(command="pytest -q", *, ordinal=0, exit_code=0,
            task_id="T-FIX", run_id=7, **extra):
    rec = {"command": command, "ordinal": ordinal, "exit_code": exit_code,
           "task_id": task_id, "run_id": run_id}
    rec.update(extra)
    return rec


# --------------------------------------------------------- S2B1-009 closure
@pytest.mark.parametrize("adapter", (cx, oc), ids=("codex", "opencode"))
@pytest.mark.parametrize("attestation", (
    {"attested": True},
    {"attested": True, "test_seam": False},
    {"attested": True, "runner_identity_attested": True, "source": "runnerd"},
))
def test_bare_or_seamed_attestation_dicts_cannot_upgrade(adapter, attestation):
    """The trust parameter is GONE: submitting any trust-bearing dict is a
    TypeError, and even byte-perfect agreement keeps trusted=False."""
    assert "runner_attestation" not in inspect.signature(
        adapter.merge_runner_records).parameters
    with pytest.raises(TypeError):
        adapter.merge_runner_records(_claimed(), [_record()],
                                     runner_attestation=attestation)
    merged = adapter.merge_runner_records(_claimed(), [_record()],
                                          task_id="T-FIX", run_id=7)
    assert merged[0]["trusted"] is False
    assert merged[0]["source"] == "cli-event-self-report"


@pytest.mark.parametrize("adapter", (cx, oc), ids=("codex", "opencode"))
def test_same_ordinal_different_command(adapter):
    merged = adapter.merge_runner_records(
        _claimed("pytest -q"), [_record("rm -rf /")],
        task_id="T-FIX", run_id=7)
    assert merged[0]["trusted"] is False
    assert merged[0].get("command_mismatch") is True


@pytest.mark.parametrize("adapter", (cx, oc), ids=("codex", "opencode"))
def test_same_command_different_ordinal_no_reuse(adapter):
    """Ordinal 1 claim vs ordinal 0 record: no pairing, no trust."""
    claimed = _claimed()
    claimed[0]["ordinal"] = 1
    merged = adapter.merge_runner_records(claimed, [_record()],
                                          task_id="T-FIX", run_id=7)
    assert merged[0]["trusted"] is False
    assert merged[0].get("no_matching_runner_record") is True


@pytest.mark.parametrize("adapter", (cx, oc), ids=("codex", "opencode"))
def test_duplicate_ordinal_never_silently_overwrites(adapter):
    claimed = cx.extract_command_evidence([
        cx.normalize_event({"type": "exec_command_end", "command": "a",
                            "exit_code": 0}),
        cx.normalize_event({"type": "exec_command_end", "command": "a",
                            "exit_code": 0})])
    records = [_record("a", ordinal=0), _record("a", ordinal=0)]
    merged = adapter.merge_runner_records(claimed, records,
                                          task_id="T-FIX", run_id=7)
    assert all(m["trusted"] is False for m in merged)
    # the entry whose ordinal collides with TWO records is flagged ambiguous
    # (never a silent last-wins overwrite); the other has no match at all
    assert merged[0].get("duplicate_ordinal") is True
    assert merged[1].get("no_matching_runner_record") is True


@pytest.mark.parametrize("adapter", (cx, oc), ids=("codex", "opencode"))
def test_missing_ordinal_record_cannot_be_reused(adapter):
    """Records without an ordinal never pair by command string."""
    rec = _record()
    rec.pop("ordinal")
    merged = adapter.merge_runner_records(_claimed(), [rec],
                                          task_id="T-FIX", run_id=7)
    assert merged[0]["trusted"] is False
    assert merged[0].get("no_matching_runner_record") is True


@pytest.mark.parametrize("adapter", (cx, oc), ids=("codex", "opencode"))
def test_cross_task_or_run_records_flagged(adapter):
    for bad in (_record(task_id="T-OTHER"), _record(run_id=99)):
        merged = adapter.merge_runner_records(_claimed(), [bad],
                                              task_id="T-FIX", run_id=7)
        assert merged[0]["trusted"] is False
        assert merged[0].get("cross_execution_binding") is True


@pytest.mark.parametrize("adapter", (cx, oc), ids=("codex", "opencode"))
def test_one_record_cannot_upgrade_two_execution_instances(adapter):
    claimed = cx.extract_command_evidence([
        cx.normalize_event({"type": "exec_command_end", "command": "a",
                            "exit_code": 0}),
        cx.normalize_event({"type": "exec_command_end", "command": "a",
                            "exit_code": 0})])
    merged = adapter.merge_runner_records(claimed, [_record("a")],
                                          task_id="T-FIX", run_id=7)
    assert merged[0]["trusted"] is False and merged[1]["trusted"] is False
    assert merged[0].get("matched_unauthenticated") is True
    assert merged[1].get("no_matching_runner_record") is True


@pytest.mark.parametrize("adapter", (cx, oc), ids=("codex", "opencode"))
def test_same_command_and_exit_but_unbound_is_not_trusted(adapter):
    """No execution context supplied => the record is provably unbound."""
    merged = adapter.merge_runner_records(_claimed(), [_record()])
    assert merged[0]["trusted"] is False
    assert merged[0].get("unbound_execution_context") is True


@pytest.mark.parametrize("adapter", (cx, oc), ids=("codex", "opencode"))
def test_exit_code_conflict_is_contradiction_not_trust(adapter):
    merged = adapter.merge_runner_records(
        _claimed("pytest -q", 0), [_record(exit_code=1)],
        task_id="T-FIX", run_id=7)
    assert merged[0]["trusted"] is False
    assert merged[0].get("exit_code_mismatch") is True


@pytest.mark.parametrize("adapter", (cx, oc), ids=("codex", "opencode"))
def test_source_claims_inside_records_are_inert(adapter):
    """A record that CLAIMS runner provenance (source/attested/signature)
    changes nothing - no dict field can influence trust."""
    merged = adapter.merge_runner_records(
        _claimed(), [_record(source="runnerd", attested=True,
                             signature="deadbeef")],
        task_id="T-FIX", run_id=7)
    assert merged[0]["trusted"] is False
    assert merged[0]["source"] == "cli-event-self-report"


# ------------------------------------------------- S2B1F-002 manifest anchor
def test_manifest_parameter_is_gone_from_both_verifiers():
    for fn in (runner.verify_execution_identity,
               runner.verify_receipt_integrity):
        params = inspect.signature(fn).parameters
        assert "manifest" not in params
        assert "home" in params


def test_self_consistent_fabrication_never_claims_identity(tmp_path):
    """Re-audit extra test A: caller-made manifest + receipt + capture files.
    Without an anchored manifest the verifier fails closed; with one, integrity
    passes but L4 (identity) is structurally False."""
    request = _request(tmp_path)
    exe = tmp_path / "h.exe"
    exe.write_bytes(b"H")
    manifest = _manifest(tmp_path)
    receipt = _receipt(tmp_path, request, exe,
                       manifest_sha=manifest_sha256(manifest))
    captures = tmp_path / "cap"
    captures.mkdir()
    (captures / "7.stdout.bin").write_bytes(b"O")
    (captures / "7.stderr.bin").write_bytes(b"E")
    (captures / "7.capture-meta.json").write_bytes(b"{}")
    receipt["stdout_sha256"] = digest_file(captures / "7.stdout.bin")
    receipt["stderr_sha256"] = digest_file(captures / "7.stderr.bin")
    receipt["capture_meta_sha256"] = digest_file(
        captures / "7.capture-meta.json")

    with pytest.raises(RunnerUnavailableError,
                       match="no anchored runner manifest"):
        verify_receipt_integrity(receipt=receipt, request=request,
                                 home=tmp_path / "empty-home",
                                 capture_dir=captures)

    out = verify_receipt_integrity(receipt=receipt, request=request,
                                   home=_home(tmp_path, manifest),
                                   capture_dir=captures)
    assert out["integrity_verified"] is True
    assert out["attested"] is False
    assert out["runner_identity_attested"] is False
    assert out["levels"] == {"L1_structure": True, "L2_digests": True,
                             "L3_manifest_anchored": True,
                             "L4_identity_attested": False}
    assert "NOT a runner identity" in out["note"]


def test_anchored_manifest_other_task_rejected(tmp_path):
    """A valid manifest anchored in the home but bound to ANOTHER task must
    not authorize this task's execution."""
    request = _request(tmp_path)
    exe = tmp_path / "h.exe"
    exe.write_bytes(b"H")
    manifest = _manifest(tmp_path, task_id="T-OTHER")
    receipt = _receipt(tmp_path, request, exe,
                       manifest_sha=manifest_sha256(manifest))
    probe, ref = _probe()
    ref["image"] = str(exe)
    with pytest.raises(RunnerAttestationError, match="different task"):
        verify_execution_identity(receipt=receipt, request=request,
                                  home=_home(tmp_path, manifest),
                                  orchestrator=SID_ORCH,
                                  identity_probe=probe)


def test_live_seam_and_merge_compose_no_trusted_evidence(tmp_path):
    """Even composing a seam 'pass' (attested=False/test_seam=True) with the
    merge path yields zero trusted records anywhere."""
    exe = tmp_path / "h.exe"
    exe.write_bytes(b"H")
    request = _request_exe(tmp_path, exe)
    receipt = _receipt(tmp_path, request, exe)
    probe, ref = _probe()
    ref["image"] = str(exe)
    ident = verify_execution_identity(receipt=receipt, request=request,
                                      home=_home(tmp_path),
                                      orchestrator=SID_ORCH,
                                      identity_probe=probe)
    assert ident["attested"] is False and ident["test_seam"] is True
    assert ident["manifest_provenance"] == "anchored_task_home"
    merged = cx.merge_runner_records(_claimed(), [_record("pytest -q")],
                                     task_id=request["task_id"],
                                     run_id=request["run_id"])
    assert merged[0]["trusted"] is False
    print("no composed path produces trusted=True in Stage-2B-1")
