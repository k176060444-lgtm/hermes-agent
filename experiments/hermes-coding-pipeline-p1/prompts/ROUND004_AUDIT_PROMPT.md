# Hermes Coding Pipeline P1 — independent Round-004 audit

Review the **exact candidate source commit** identified in the invoking task, not the latest branch HEAD after audit reports are added. This is a **read-only code review and disposable local/offline test task**; do not run real Codex/OpenCode, paid providers, P0, Debian peers, or production operations.

Repository: `k176060444-lgtm/hermes-agent`.
Branch: `feature/p1-coding-pipeline-20261104`.
Project: `experiments/hermes-coding-pipeline-p1/`.
Previous audit: `audit_evidence/P1/round-003/`, report commit `e544d5e0cc1471c7844baf5c6f0ba10dbbd3db81`.
Read `docs/ROUND_003_REMEDIATION.md`, the original Round-003 `AUDIT_REPORT.md` and `FINDINGS.json`, changed source files and test code.

## Mandatory checks

1. **R3-001**: independent reproduction that Tester Gate A/B cannot add `tests/conftest.py` to suppress existing pytest collection and reach Gate 5.9 COMPLIANT. Also probe `pytest.ini`, `pyproject.toml`, `__init__.py`, symlinked `test_*.py`, and a normal legitimate `test_new_case.py`; look for false positives or alternate paths. Verify the upstream/downstream protected exam hashes remain unchanged.
2. **R3-002**: run deletion; change stage, role or input SHA; duplicate dispatch/finish; malformed run IDs; missing dispatch/finish; unfinished runs. Ensure event-chain validation and `verify_evidence`/`export_report` block as appropriate without breaking interrupted RUNNING recovery or concurrent Phase 3/4.
3. **R3-003**: status reports effective read-only BLOCKED on corrupted state while preserving the original task row and journal. Do not inadvertently "re-seal" damaged evidence.
4. Verify original 64 tests and the added Round-003 tests without modifying source. Check no regressions to human Gate 0.2, two parallel reviewers, Gate A/B, 5/5/2 budgets, fixed versioned Soul/matrix, strict Gate 5.9 output and external P0-only A2A boundary.
5. **Known incomplete**: R2-006 (external A2A raw receipt/authenticity) remains MITIGATED_FAIL_CLOSED; R2-008 (unbounded subprocess stdout/stderr) remains a nonblocking P3. Do not claim real integration is ready merely because offline tests pass.

Pro-Audit is intentionally limited to process, assignment, input/output versions and compliance evidence; technical code quality is for the independently tasked code auditor. Do not reject harmless style or cosmetic issues.

## Deliverables

Add **only** these new files under `audit_evidence/P1/round-004/` on the P1 development branch:

- `AUDIT_REPORT.md`: COMPLETE/INCOMPLETE, PASS/FAIL/CONDITIONAL; proof and issue classifications.
- `FINDINGS.json`: R3-001, R3-002, R3-003 individual verdicts (FIXED / MITIGATED_FAIL_CLOSED / NOT_FIXED / REGRESSION / NOT_VERIFIED) plus any new issues with evidence and severity.
- `TEST_RESULTS.txt`: actual commands, exit status, test results, what was simulated, reproducible probes.
- `SCOPE.json`: exact audited source SHA/tree, time, host, file inventory, external/unverified limitations.

Never edit source, tests, Soul or previous audit rounds. Save progressive evidence; if interrupted, submit `AUDIT_STATUS: INCOMPLETE` rather than inventing results. After upload, read back the four files, give report commit SHA and immutable source commit. Real integration on 21bao remains disallowed until separate authorization and trusted interfaces are completed.
