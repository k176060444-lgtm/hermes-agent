"""Explicit OS trust boundary for future real P1 tasks.

This enforces the 'single trusted operating-system identity owns the task
ledger' model. It is NOT a claim that a privileged process running as that
same identity cannot append convincing events. Such a process is inside the
trusted computing base; it must not be used to execute untrusted Agent code.

Offline fixtures intentionally do not claim this boundary. Real integration
remains independently disabled pending trustworthy Harness/P0/approval receipts.
"""
from __future__ import annotations

import json
import os
import stat
import subprocess
from pathlib import Path


class TrustBoundaryError(RuntimeError):
    pass


_WINDOWS_ACL_SCRIPT = r'''
$ErrorActionPreference = 'Stop'
$me = [System.Security.Principal.WindowsIdentity]::GetCurrent().User.Value
$allowed = @($me, 'S-1-5-18', 'S-1-5-32-544')
$all = @()
foreach ($path in $args) {
  $acl = Get-Acl -LiteralPath $path
  $owner = $acl.GetOwner([System.Security.Principal.SecurityIdentifier]).Value
  $bad = @()
  foreach ($rule in $acl.GetAccessRules($true, $true,
                   [System.Security.Principal.SecurityIdentifier])) {
    if ($rule.AccessControlType -eq 'Allow' -and
        $allowed -notcontains $rule.IdentityReference.Value) {
      $bad += $rule.IdentityReference.Value
    }
  }
  $all += @{ path=$path; owner=$owner; me=$me;
             acl_protected=$acl.AreAccessRulesProtected; unexpected=$bad }
}
ConvertTo-Json -InputObject @($all) -Compress -Depth 4
'''


def _windows_validate(paths: list[Path]) -> None:
    # PS is query-only. P1 never silently rewrites a user's NTFS ACLs.
    import base64
    # -EncodedCommand does not reliably forward trailing argv as $args in all
    # Windows PowerShell versions. Embed escaped string literals in the
    # encoded script instead, never concatenate them into shell commands.
    ps_paths = ",".join("'" + str(p).replace("'", "''") + "'" for p in paths)
    script = _WINDOWS_ACL_SCRIPT.replace('in $args)', 'in @(' + ps_paths + '))')
    encoded = base64.b64encode(script.encode('utf-16le')).decode('ascii')
    cmd = ['powershell.exe', '-NoProfile', '-NonInteractive',
           '-EncodedCommand', encoded]
    try:
        result = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                text=True, errors='replace', timeout=20)
        if result.returncode:
            raise TrustBoundaryError('Windows NTFS ACL inspection failed')
        data = json.loads(result.stdout)
        if not isinstance(data, list) or len(data) != len(paths):
            raise ValueError('unexpected ACL result cardinality')
        for rec in data:
            if not rec.get('acl_protected'):
                raise TrustBoundaryError('NTFS ACL inherits permissions: ' + rec.get('path', '?'))
            if rec.get('owner') != rec.get('me'):
                raise TrustBoundaryError('NTFS task state not owned by current identity')
            if rec.get('unexpected'):
                raise TrustBoundaryError('NTFS task state grants access to other principals')
    except (OSError, ValueError, subprocess.TimeoutExpired) as exc:
        raise TrustBoundaryError('cannot independently verify Windows NTFS task ACLs') from exc


def _posix_validate(paths: list[Path]) -> None:
    if not hasattr(os, 'geteuid'):
        raise TrustBoundaryError('POSIX owner verification unavailable')
    for path in paths:
        info = path.lstat()
        if stat.S_ISLNK(info.st_mode):
            raise TrustBoundaryError('task state path must not be symbolic link')
        if info.st_uid != os.geteuid():
            raise TrustBoundaryError('task state owner differs from P1 process')
        if info.st_mode & 0o077:
            raise TrustBoundaryError('task state has group/other permissions')


def validate_private_task_home(home: Path, *, require_database: bool) -> None:
    """Fail closed unless the task state belongs to one trusted OS identity.

    Caller must provision a dedicated process identity and prevent Agent
    subprocesses from reading/writing this directory. The check alone cannot
    distinguish different processes under the SAME OS identity.
    """
    home = Path(home).absolute()
    paths = [home]
    if require_database:
        paths.append(home / 'state.sqlite')
    for path in paths:
        if not path.exists() or path.is_symlink():
            raise TrustBoundaryError('private task state path missing or linked')
    if os.name == 'nt':
        _windows_validate(paths)
    elif os.name == 'posix':
        _posix_validate(paths)
    else:
        raise TrustBoundaryError('unsupported OS for trusted task-state isolation')
