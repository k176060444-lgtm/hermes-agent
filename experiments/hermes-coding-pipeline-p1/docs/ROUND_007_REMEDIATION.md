# Round-007 Remediation — R7-001

## Disposition

Round-007 (Qwen-Flash) concluded `CONDITIONAL`, with R6-001 `FIXED` after real
21bao Windows NTFS/SQLite WAL lifecycle verification. The only newly raised
item was R7-001 (P3 informational): `_windows_validate()` identified the
protected root by `index == 0`. Current production construction places
`home` first and validates response paths positionally, so the auditor found no
reachable exploit; this was an avoidable implementation coupling.

This remediation changes the internal helper contract to require an explicit
`protected_root` argument. The protected-root check is now selected by a
normalized path identity comparison, not by the record's list index. Existing
per-index response-to-request path binding remains in place to reject reordered
or substituted PowerShell records. The task root must still have inheritance
protection enabled; all enumerated children must still have the current owner
and no unexpected effective Allow principals. No ACL is rewritten by P1.

## Regression coverage

- Root is not first in the requested path list and is unprotected: rejected.
- Root is not first and is correctly protected: accepted.
- Existing root-first protected/unprotected cases remain covered.
- Reordered PowerShell response remains rejected.
- Duplicate or absent protected-root path: rejected.
- Real Windows R6-001 lifecycle test remains in the suite and must be run on
  21bao by the independent auditor; it was not executed in this Linux run.

## Local verification

- `python -m pytest -q`: **116 passed, 2 skipped** (Linux environment).
- Skips are platform-specific Windows NTFS / POSIX-only tests as marked by the
  suite; this result is not a substitute for Windows validation.
- `python -m compileall -q p1 tests`: PASS.
- `python -m p1 --help`: PASS (CLI entry point and command registry load).

## Deliberately not changed

- R6-002 remains a documented P3 informational observation. Recursive
  per-file DACL enumeration is not added in this narrow correction.
- R5-005 remains `MITIGATED_FAIL_CLOSED`: no authenticated separate-identity
  Agent runner exists.
- R2-006 remains `MITIGATED_FAIL_CLOSED`: no trusted P0/A2A wire receipt or
  physical-node attestation.
- No real Harness, model, remote peer, E: worktree, production config, or
  production deployment was invoked or modified.

## Release posture

This is an offline remediation candidate only. It does not authorize 21bao
real execution. Integration remains fail-closed pending separate-identity
runner, P0/A2A attestation, real invocation/test/approval receipts, Windows
E: validation, descendant-process cleanup, and production kill-guard evidence.
