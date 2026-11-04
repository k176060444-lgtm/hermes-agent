"""R6-001 Windows SQLite WAL lifecycle, plus platform-independent ACL logic.

All real NTFS mutation is confined to a new pytest tmp_path. No live P1,
Hermes, service identity, credential, production filesystem or remote node.
"""
from __future__ import annotations

import base64
import json
import os
import sqlite3
import subprocess
from pathlib import Path

import pytest

from p1.trust import TrustBoundaryError, _windows_validate, validate_private_task_home
from p1 import trust


def _acl_records(root, children, *, root_protected=True, bad_child=None, bad_owner=None):
    paths = [root, *children]
    return [
        {"path": str(path), "owner": "S-1-5-21-123", "me": "S-1-5-21-123",
         "acl_protected": root_protected if i == 0 else False,
         "unexpected": ["S-1-1-0"] if i == bad_child else []}
        | ({"owner": "S-1-1-0"} if i == bad_owner else {})
        for i, path in enumerate(paths)
    ]


def _stub_windows_query(monkeypatch, records):
    class Result:
        returncode = 0
        stdout = json.dumps(records)
        stderr = ""
    monkeypatch.setattr(trust.subprocess, "run", lambda *a, **kw: Result())


def test_r6_001_protected_home_allows_safe_inherited_sqlite_children(monkeypatch, tmp_path):
    home = tmp_path / 'private'
    db = home / 'state.sqlite'
    wal = home / 'state.sqlite-wal'
    shm = home / 'state.sqlite-shm'
    records = _acl_records(home, [db, wal, shm])
    _stub_windows_query(monkeypatch, records)
    _windows_validate([home, db, wal, shm], protected_root=home)


def test_r6_001_unprotected_home_still_blocks(monkeypatch, tmp_path):
    home = tmp_path / 'private'
    db = home / 'state.sqlite'
    _stub_windows_query(monkeypatch, _acl_records(home, [db], root_protected=False))
    with pytest.raises(TrustBoundaryError, match='task root inherits'):
        _windows_validate([home, db], protected_root=home)


@pytest.mark.parametrize('kind', ['unexpected_principal', 'wrong_owner', 'misordered_response'])
def test_r6_001_inherited_children_still_require_safe_effective_acl(monkeypatch, tmp_path, kind):
    home = tmp_path / 'private'
    db = home / 'state.sqlite'
    wal = home / 'state.sqlite-wal'
    records = _acl_records(home, [db, wal],
                           bad_child=2 if kind == 'unexpected_principal' else None,
                           bad_owner=2 if kind == 'wrong_owner' else None)
    if kind == 'misordered_response':
        records[1], records[2] = records[2], records[1]
    _stub_windows_query(monkeypatch, records)
    with pytest.raises((TrustBoundaryError, ValueError)):
        _windows_validate([home, db, wal], protected_root=home)


def _run_powershell(script: str) -> None:
    encoded = base64.b64encode(script.encode('utf-16le')).decode('ascii')
    result = subprocess.run(['powershell.exe', '-NoProfile', '-NonInteractive',
                             '-EncodedCommand', encoded], capture_output=True,
                            text=True, errors='replace', timeout=35)
    assert result.returncode == 0, (result.stdout, result.stderr)


@pytest.mark.skipif(os.name != 'nt', reason='Real NTFS WAL lifecycle requires Windows')
def test_r6_001_real_windows_sqlite_wal_recreation_under_protected_root(tmp_path):
    """Reproduce R6-001 with real Win32 DACL and SQLite WAL churn.

    Protect only root; leave SQLite-generated children with inherited owner
    permissions. Both original and re-created WAL/SHM must validate. A real
    unexpected ACE on the WAL still blocks. Uses only this new temporary dir.
    """
    home = tmp_path / 'isolated-wal-ledger'
    home.mkdir()
    quoted = str(home).replace("'", "''")
    _run_powershell(r'''
$ErrorActionPreference = 'Stop'
$path = '__HOME__'
$me = [Security.Principal.WindowsIdentity]::GetCurrent().User
$acl = Get-Acl -LiteralPath $path
$acl.SetAccessRuleProtection($true, $false)
foreach ($entry in @($acl.Access)) { $acl.PurgeAccessRules($entry.IdentityReference) }
$flags = [Security.AccessControl.InheritanceFlags]'ContainerInherit,ObjectInherit'
$rule = [Security.AccessControl.FileSystemAccessRule]::new(
    $me, [Security.AccessControl.FileSystemRights]::FullControl, $flags,
    [Security.AccessControl.PropagationFlags]::None,
    [Security.AccessControl.AccessControlType]::Allow)
$acl.AddAccessRule($rule)
Set-Acl -LiteralPath $path -AclObject $acl
'''.replace('__HOME__', quoted))

    database = home / 'state.sqlite'
    with sqlite3.connect(database) as db:
        assert db.execute('PRAGMA journal_mode=WAL').fetchone()[0].lower() == 'wal'
        db.execute('CREATE TABLE evidence (value TEXT)')
        db.execute('INSERT INTO evidence VALUES (?)', ('before-close',))
        db.commit()
        assert (home / 'state.sqlite-wal').exists()
        validate_private_task_home(home, require_database=True)
    # SQLite clean close may remove WAL/SHM. Recreating them must be valid.
    with sqlite3.connect(database) as db:
        assert db.execute('PRAGMA journal_mode=WAL').fetchone()[0].lower() == 'wal'
        db.execute('INSERT INTO evidence VALUES (?)', ('after-reopen',))
        db.commit()
        assert (home / 'state.sqlite-wal').exists()
        validate_private_task_home(home, require_database=True)
        wal_path = str(home / 'state.sqlite-wal').replace("'", "''")
        _run_powershell(r'''
$ErrorActionPreference = 'Stop'
$path = '__WAL__'
$acl = Get-Acl -LiteralPath $path
$everyone = [Security.Principal.SecurityIdentifier]::new('S-1-1-0')
$rule = [Security.AccessControl.FileSystemAccessRule]::new(
    $everyone, [Security.AccessControl.FileSystemRights]::Read,
    [Security.AccessControl.AccessControlType]::Allow)
$acl.AddAccessRule($rule)
Set-Acl -LiteralPath $path -AclObject $acl
'''.replace('__WAL__', wal_path))
        with pytest.raises(TrustBoundaryError, match='other principals'):
            validate_private_task_home(home, require_database=True)


def test_r7_001_protected_root_is_identified_by_path_not_position(monkeypatch, tmp_path):
    home = tmp_path / 'private'
    db = home / 'state.sqlite'
    # Deliberately put the database before the root. The protected-root rule
    # must still apply to the root path, not whichever record happens to be 0.
    records = _acl_records(db, [home])
    records[1]['acl_protected'] = False
    _stub_windows_query(monkeypatch, records)
    with pytest.raises(TrustBoundaryError, match='task root inherits'):
        _windows_validate([db, home], protected_root=home)


def test_r7_001_protected_root_can_be_non_first_when_acl_is_safe(monkeypatch, tmp_path):
    home = tmp_path / 'private'
    db = home / 'state.sqlite'
    records = _acl_records(db, [home])
    records[1]['acl_protected'] = True
    _stub_windows_query(monkeypatch, records)
    _windows_validate([db, home], protected_root=home)


@pytest.mark.parametrize('requested_paths', ['missing', 'duplicate'])
def test_r7_001_protected_root_must_be_present_exactly_once(monkeypatch, tmp_path, requested_paths):
    home = tmp_path / 'private'
    db = home / 'state.sqlite'
    if requested_paths == 'missing':
        paths = [db]
        records = _acl_records(db, [])
    else:
        paths = [home, db, home]
        records = _acl_records(home, [db, home])
    _stub_windows_query(monkeypatch, records)
    with pytest.raises(TrustBoundaryError, match='protected root must appear exactly once'):
        _windows_validate(paths, protected_root=home)
