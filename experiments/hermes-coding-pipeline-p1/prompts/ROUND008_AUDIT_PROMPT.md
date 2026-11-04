# Hermes Coding Pipeline P1 — Round-008 Independent Audit

Auditor: **Qwen-Flash**. This is an independent review only; do not modify
source, tests, Souls, prior audit reports, live Hermes configuration, or remote
nodes.

## Fixed baseline

- Repository: `k176060444-lgtm/hermes-agent`
- Branch: `feature/p1-coding-pipeline-20261104`
- Scope: `experiments/hermes-coding-pipeline-p1/`
- Source commit: use the exact source SHA supplied in the developer handoff;
  verify it is the parent of the audit-report commit and do not audit a moving
  branch head.
- Previous audit report: `bc9b6cba32c79bbe1c9060332b459ae342e30fee`

Read `docs/ROUND_007_REMEDIATION.md`, `docs/KNOWN_LIMITATIONS.md`, the
Round-007 four-file report, `p1/trust.py`, and
`tests/test_remediation_round6.py`.

## Primary target: R7-001

Verify that `_windows_validate` receives the protected root explicitly and
identifies it by normalized path rather than list position. Independently test:

1. Protected root first and valid: accepted.
2. Protected root not first and valid: accepted.
3. Protected root not first and inheritance unprotected: rejected.
4. A reordered/substituted PowerShell response: rejected.
5. Duplicate or absent protected-root path: rejected.
6. Wrong owner or unexpected effective Allow principal on any child: rejected.

Check Windows path normalization semantics, case handling, drive prefixes,
separator normalization, and response path binding. Confirm no caller can
accidentally omit or misidentify the protected root.

## Carry-forward checks

- R6-001 remains FIXED only if the real Windows SQLite WAL close/reopen
  lifecycle test still executes and passes on 21bao. Do not count a skip as pass.
- R6-002 remains a documented P3 observation unless the code has materially
  changed; do not silently call it fixed.
- R5-005 must remain `MITIGATED_FAIL_CLOSED`; no same-SID subprocess may be
  treated as an authenticated separate-identity runner.
- R2-006 must remain `MITIGATED_FAIL_CLOSED`; no mock or self-reported A2A
  peer identity may be accepted as physical attestation.
- Verify no regression to Phase 3/4 parallel review, same-commit binding,
  Gate 0.2/A/B/5.9, 5/5/2 loop budgets, protected tests, event integrity,
  Pro-Audit's process-only remit, and integration fail-closed behavior.

## Environment and evidence

Run the full project suite on 21bao Windows and record collected/passed/failed/
skipped counts, exact Python/Git/PowerShell versions, and test exit codes. Run
the designated `test_r6_001_real_windows_sqlite_wal_recreation_under_protected_root`
on actual NTFS; it must not be skipped. Add isolated adversarial probes for
R7-001. Before and after testing, verify every source Git blob against the fixed
commit; report the checked count and mismatches.

Do not call paid models, real Codex/OpenCode agents, P0, 5bao/9bao/rusty, or
production services. Only use disposable audit scratch directories for ACL
mutation.

## Upload report

Upload exactly these four files under
`experiments/hermes-coding-pipeline-p1/audit_evidence/P1/round-008/`:

- `AUDIT_REPORT.md`
- `FINDINGS.json`
- `TEST_RESULTS.txt`
- `SCOPE.json`

The report must state `COMPLETE/INCOMPLETE`, `PASS/FAIL/CONDITIONAL`, each
finding disposition, new findings, Windows execution evidence, source integrity,
and real-integration release posture. Upload only the four Round-008 report
files; read each back and verify SHA-256. Stop after reporting.
