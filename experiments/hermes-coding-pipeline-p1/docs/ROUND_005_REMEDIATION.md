# P1 Round-005 findings → Round-006 remediation candidate

**Audit baseline:** `3be86f69b87d7f69c0f739d31615c5e0feda751b`; original Round-005 report commit `9eb543de791a98f7bad4b5ebf1fd1b2aa6836df9`. The report is authoritative; this document records developer *candidates*, not independent findings closed.

**Scope:** Isolated Python changes and local tests only. No 21bao Hermes/Agent configuration, live Codex/OpenCode, P0 node, paid model or production resources were touched.

| Finding | Candidate disposition | Implementation and remaining proof |
|---|---|---|
| R5-001 P3 | Candidate FIXED locally | `p1/trust.py` now inspects SQLite `state.sqlite-wal` and `state.sqlite-shm` **when present**, as well as existing `snapshots/`, `logs/`, `artifacts/`, `audit_evidence/` paths. Missing/linked mandatory ledger paths fail closed. Private ownership and ACL expectations are unchanged. Verified with isolated path enumeration and symlink tests; actual Windows DACL must be independently audited. Parent directories are intentionally not required to have private DACL: traversal visibility is not an authorization grant to the ledger. |
| R5-002 P3 | Candidate FIXED for successful integrated executions | `p1/executor.py` hashes `logs/<run_id>.capture.json`; the workflow binds its digest into both the stored run details and the hash-chained `execution_finished` event. `verify_evidence()` checks the exact file, its SHA and inner stdout/stderr SHA references. Timeout/overflow leave an unfinished run; **they cannot be considered COMPLIANT**, and `status` requires reconciliation. The timeout JSON is still only diagnostic until a Stage-2 terminal failure receipt is designed. |
| R5-003 P3 | Candidate FIXED | Windows-compatible test filename uses a Unicode name with spaces. POSIX-only tab filename has a separate `skipif(os.name == 'nt')` test. Tests no longer try to create Windows-invalid filesystem names. |
| R5-004 P2 | Windows test added; NOT_VERIFIED on developer Linux | Added an actual Windows NTFS DACL positive/negative test in `tests/test_remediation_round5.py`. It constructs **only** a disposable pytest directory, uses `Set-Acl` to make allowed private DACL, and then grants Everyone on the WAL file to confirm rejection. It runs on Windows and intentionally skips Linux. Must be run by Qwen-Flash on 21bao; neither its PASS nor DACL availability is claimed here. |
| R5-005 P2 | **MITIGATED_FAIL_CLOSED, not FIXED** | `invoke()` now has an additional unconditional gate that rejects the ordinary local `subprocess.Popen` runner even if the legacy `TRUSTED_INTEGRATION_EXECUTION_VERIFIED` flag is erroneously enabled. The direct local runner inherits the orchestrator's identity and could otherwise access the ledger. There is **no verified separate-user service / token SID attestation in P1 yet**; proper Stage-2 service isolation or an independently protected signing authority must be engineered and audited before enabling live execution. A configuration field asserting `isolated=true` must NEVER count as proof. Offline fixture state is explicitly non-evidentiary. |

## Test evidence (developer)

- Local Linux/Python 3.13, pytest: **107 passed, 1 skipped**. Skip is a Windows-only NTFS ACL test (the POSIX tab-name test runs here). A Windows deployment may skip the tab-name test but **must run the ACL test**; it has not been executed by this developer.
- Python bytecode compilation: separate local command; no real Harness invocation.
- Direct-call integration check: even monkeypatching `TRUSTED_INTEGRATION_EXECUTION_VERIFIED=True` cannot execute a same-identity local runner; legacy tests were updated **because the legitimate specification has strengthened**. This does not prove a separate-identity runner exists.
- Capture integrity test registers a completed synthetic run, verifies the raw capture metadata, then tampers with/deletes the capture file; verification and Gate 5.9 export must fail.

## Stage-2 identity architecture still required

1. Provision a **dedicated service/process identity** owning P1 state and approvals; no Worker/Reviewer/Tester process may access or run with that identity.
2. Do **not** launch a coding Agent as an ordinary child with the service identity. Use a separately authenticated runner under a distinct OS identity or a verified independent signing/approval authority.
3. Verify the **actual OS token SID** or equivalent trusted identity of the executor **prior to releasing job inputs**, not a claim printed by the untrusted Agent. The runner must not be able to read/write the state directory.
4. Bind a real approved Harness/model invocation, logs, test receipts, approval identity and P0 source to the task and versioned contract. Keep `TRUSTED_INTEGRATION_EXECUTION_VERIFIED=False` until independent acceptance.
5. Stop at Gate 5.9. Phase 6/7 remain out of scope.

**Not finished:** R2-006 real A2A wire receipts and true host identity, reliable Windows descendant process control, live Codex/OpenCode/API-model receipt provenance, Gate 0.1/0.2 identity chain, and E: worktree/side-effect acceptance. Offline green tests are not real integration evidence.
