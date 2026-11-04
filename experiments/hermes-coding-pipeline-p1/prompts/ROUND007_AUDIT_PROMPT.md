# P1 Round-007 independent audit — Qwen-Flash

**Review a fixed Git commit, not a moving branch HEAD.** Read `docs/ROUND_006_REMEDIATION.md` and the four original Round-006 reports under `audit_evidence/P1/round-006/`, then read the changed source and regression test. The developer's pass count is not audit evidence.

## Required independent checks

1. **R6-001: Windows NTFS SQLite lifecycle** (priority): on an auditor-created one-time scratch directory under Windows, protect only the root ACL and set inheritable FullControl for the designated SID; then create state.sqlite and WAL/SHM naturally. Verify the root remains protected, SQLite children may have inherited owner-only ACEs, and `validate_private_task_home()` accepts. Close and reopen the SQLite connection so WAL/SHM are recreated; validation must still accept. Grant `Everyone` Read on one child WAL in the *disposable* directory and verify fail-closed. Also test root inheritance enabled, an unexpected Allow principal on a child, wrong owner, symlink/reparse handling and inconsistent query response shape where feasible. Do not touch Hermes/real tasks.
2. **R6-002: scope note**: confirm contents of child evidence files with independent DACL changes are not individually enumerated. Evaluate according to the documented trust model; report separately as informational/remaining rather than presenting it as solved.
3. **Run actual Windows product suite**: report collected/passed/failed/skipped separately and cite the Windows-only WAL lifecycle result. The developer's Linux outcome was 112 passed/2 skipped; do not copy those numbers as Windows evidence.
4. **Regression**: Phase 3/4 parallel same SHA and independent compliance, Gate 0.2/A/B/5.9, Tester exam immutability, 5/5/2 budgets, immutable ledger run references, A2A integration fail-closed. Verify that neither the real Harness runner nor P0 nodes were called.
5. **Trust boundary**: maintain R5-005/R4-001 as `MITIGATED_FAIL_CLOSED` absent actual distinct-SID trusted runner. Keep R2-006 physical A2A identity/receipts `MITIGATED_FAIL_CLOSED`. Never misclassify the OS trust checks as proof against same-SID arbitrary code.

Use only offline local testing and repository reads. No live Codex/OpenCode, paid model calls, real P0, A2A nodes, or production side effects. Keep P1 code read-only, work in disposable clones when needed. Do not fabricate results or force PASS.

Submit four independent reports to `experiments/hermes-coding-pipeline-p1/audit_evidence/P1/round-007/`: `AUDIT_REPORT.md`, `FINDINGS.json`, `TEST_RESULTS.txt`, `SCOPE.json`. Include tested source commit/tree, issue classifications and file:line proof, actual commands and exit codes, test provenance, unchanged source blob verification, unresolved integration items and final verdict. Upload only the four new report files, verify all returned bytes, provide report commit URL and SHA, then stop for developer remediation.
