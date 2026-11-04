"""Round-005 remediation. Offline tests; Windows ACL test runs only on Windows."""
from __future__ import annotations

import base64
import json
import os
import subprocess
from pathlib import Path

import pytest

from p1.contracts import canonical, sha256, digest_file
from p1.trust import TrustBoundaryError, validate_private_task_home
from p1 import trust
from p1.workflow import Pipeline
from test_pipeline import start, approve


def test_r5_001_wal_shm_and_evidence_children_are_explicitly_inspected(tmp_path, monkeypatch):
    home = tmp_path / "task"
    home.mkdir()
    for item in ("state.sqlite", "state.sqlite-wal", "state.sqlite-shm"):
        (home / item).write_bytes(b"fixture")
    for sub in ("logs", "snapshots", "artifacts", "audit_evidence"):
        (home / sub).mkdir()
    checked = []
    monkeypatch.setattr(trust, "_windows_validate" if os.name == "nt" else "_posix_validate",
                        lambda paths: checked.extend(path.name for path in paths))
    validate_private_task_home(home, require_database=True)
    assert {"task", "state.sqlite", "state.sqlite-wal", "state.sqlite-shm",
            "logs", "snapshots", "artifacts", "audit_evidence"}.issubset(set(checked))


def test_r5_001_companion_symlink_is_not_accepted(tmp_path):
    home = tmp_path / "ledger"
    home.mkdir(mode=0o700)
    (home / "state.sqlite").write_bytes(b"fixture")
    os.chmod(home / "state.sqlite", 0o600)
    target = tmp_path / "other"
    target.write_bytes(b"other")
    try:
        (home / "state.sqlite-wal").symlink_to(target)
    except (OSError, NotImplementedError):
        pytest.skip("symlinks unavailable on this platform")
    with pytest.raises(TrustBoundaryError, match="linked"):
        validate_private_task_home(home, require_database=True)


def test_r5_002_capture_metadata_must_match_registered_run(scenario):
    s=scenario
    p=start(s)
    try:
        assert approve(p,s)["status"]=="WAITING_GATE_5_9"
        rid=p.store.start_run(p.task_id,"3","spec_reviewer","fixture-input",{})
        logs=s["home"] / "logs"
        stdout=logs/f"{rid}.stdout.bin"; stdout.write_bytes(b'{"verdict":"PASS"}')
        stderr=logs/f"{rid}.stderr.bin";stderr.write_bytes(b"")
        capture=logs/f"{rid}.capture.json"
        capture.write_text(canonical({"stdout_sha256":digest_file(stdout),
                                      "stderr_sha256":digest_file(stderr),
                                      "output_limit_exceeded":False,"timed_out":False})+"\n")
        payload={"verdict":"PASS"}
        details={"payload":payload,
                 "invocation":{"mode":"integration",
                               "stdout_sha256":digest_file(stdout),
                               "stderr_sha256":digest_file(stderr),
                               "capture_sha256":digest_file(capture)},
                 "logs":{"stdout":stdout.name,"stdout_sha256":digest_file(stdout),
                         "stderr":stderr.name,"stderr_sha256":digest_file(stderr),
                         "capture":capture.name,"capture_sha256":digest_file(capture)},
                 "report":None}
        p.store.finish_run(p.task_id,rid,"COMPLETED",sha256(canonical(payload).encode()),details)
        assert not p.store.audit_events(p.task_id)
        assert p.verify_evidence()["verdict"]=="COMPLIANT"
        capture.write_text(capture.read_text() + "CORRUPTED\n")
        bad=p.verify_evidence()
        assert bad["verdict"]=="NON_COMPLIANT"
        assert any("capture" in x for x in bad["errors"])
        with pytest.raises(Exception,match="evidence invalid"):
            p.export_report()
        capture.unlink()
        assert p.verify_evidence()["verdict"]=="NON_COMPLIANT"
    finally:
        p.close()


def test_r5_005_same_identity_local_agent_cannot_be_enabled_by_legacy_flag(scenario, monkeypatch):
    from p1 import executor
    s=scenario;s["init"]()
    monkeypatch.setattr(executor,"TRUSTED_INTEGRATION_EXECUTION_VERIFIED",True)
    task={"mode":"integration","task_id":"TEST-001",
          "project_root":str(s["project"]),"worktree_path":str(s["project"])}
    with pytest.raises(executor.InvocationError,match="separate-identity Agent runner"):
        executor.invoke(task,"planner","0.2",s["home"],1,909)
    assert not list((s["home"] / "logs").glob("909.*"))


@pytest.mark.skipif(os.name!='nt',reason='Real NTFS DACL regression runs on 21bao/Windows')
def test_r5_004_windows_ntfs_acl_positive_negative(tmp_path):
    """Only manipulates our disposable pytest directory. Never real task ACLs."""
    home=tmp_path/'test-private-p1-state';home.mkdir()
    db=home/'state.sqlite';db.write_bytes(b'fake local db')
    wal=home/'state.sqlite-wal';wal.write_bytes(b'fake wal')
    shm=home/'state.sqlite-shm';shm.write_bytes(b'fake shm')
    logs=home/'logs';logs.mkdir()
    paths=[home,db,wal,shm,logs]
    literal=','.join("'"+str(p).replace("'","''")+"'" for p in paths)
    script=r'''$ErrorActionPreference='Stop'
$me=[Security.Principal.WindowsIdentity]::GetCurrent().User
foreach($path in @(__PATHS__)) {
  $acl=Get-Acl -LiteralPath $path
  $acl.SetAccessRuleProtection($true,$false)
  foreach($entry in @($acl.Access)) { $acl.PurgeAccessRules($entry.IdentityReference) }
  if((Get-Item -LiteralPath $path).PSIsContainer) {
    $flags=[Security.AccessControl.InheritanceFlags]'ContainerInherit, ObjectInherit'
  } else { $flags=[Security.AccessControl.InheritanceFlags]::None }
  $rule=[Security.AccessControl.FileSystemAccessRule]::new($me,
     [Security.AccessControl.FileSystemRights]::FullControl,$flags,
     [Security.AccessControl.PropagationFlags]::None,
     [Security.AccessControl.AccessControlType]::Allow)
  $acl.AddAccessRule($rule)
  Set-Acl -LiteralPath $path -AclObject $acl
}
'''.replace('__PATHS__',literal)
    command=['powershell.exe','-NoProfile','-NonInteractive','-EncodedCommand',
             base64.b64encode(script.encode('utf-16le')).decode('ascii')]
    result=subprocess.run(command,capture_output=True,text=True,errors='replace',timeout=30)
    assert result.returncode==0,(result.stdout,result.stderr)
    validate_private_task_home(home,require_database=True)
    # Give the separate WAL file one unexpected ACE; this must block.
    name=str(wal).replace("'","''")
    script=r'''$acl=Get-Acl -LiteralPath '__FILE__'
$everyone=[Security.Principal.SecurityIdentifier]::new('S-1-1-0')
$rule=[Security.AccessControl.FileSystemAccessRule]::new($everyone,
   [Security.AccessControl.FileSystemRights]::Read,
   [Security.AccessControl.AccessControlType]::Allow)
$acl.AddAccessRule($rule);Set-Acl -LiteralPath '__FILE__' -AclObject $acl
'''.replace('__FILE__',name)
    result=subprocess.run(['powershell.exe','-NoProfile','-NonInteractive','-EncodedCommand',
                base64.b64encode(script.encode('utf-16le')).decode('ascii')],
                capture_output=True,text=True,errors='replace',timeout=30)
    assert result.returncode==0,(result.stdout,result.stderr)
    with pytest.raises(TrustBoundaryError,match='other principals'):
        validate_private_task_home(home,require_database=True)
