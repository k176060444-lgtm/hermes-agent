# Round-005 independent code audit prompt

Repository: `k176060444-lgtm/hermes-agent`
Branch: `feature/p1-coding-pipeline-20261104`
Code: `experiments/hermes-coding-pipeline-p1/`

Pin the **new code commit SHA** provided by the developer, do not audit the moving
branch head. Read `docs/ROUND_004_REMEDIATION.md`, prior Round-004 report at
`audit_evidence/P1/round-004/`, and the actual changed source and tests.

## Mandatory decisions

1. R4-001 (P1): inspect the *enforced* trust boundary, not merely a threat-model
   paragraph. Verify `status`, `verify_evidence`, `run`, `resume`, `approve-spec`
   fail closed if the task home/SQLite is shared or ACL verification fails.
   Audit the Windows PowerShell SIDs/ACL query statically; Windows runtime is
   NOT_VERIFIED unless you actually run it on an isolated Windows fixture.
   Critically distinguish same-OS-identity attackers (still trusted under this
   design) from a different OS identity with task DB write rights. Check whether
   the actual 21bao process layout can meet the trust assumption; if not,
   **do not declare R4-001 fully fixed for real integration**.
2. R4-002 (P3): validate non-ASCII/spaces/tab/test-only Git paths; ensure
   `git diff --name-status -z` and `ls-tree -z` do not weaken rejection of
   symlinks, collection controls, rewrites and deletions.
3. R4-003 (P3): test orphan RUNNING run at Gate 5.9 as well as before Gate 0.2;
   effective status must demand reconciliation without rewriting the state row.
4. R2-008 (P3): verify memory-bounded streaming for both pipes; overflow,
   timeouts, non-JSON output and normal JSON; check metadata and direct-child
   termination. Do **not** claim the Windows descendant process problem solved.
5. R2-006 and all real integration gaps remain NOT_VERIFIED / FAIL_CLOSED.
6. Regression: same-commit parallel reviewers, 5/5/2, the three human Gates,
   Tester exam add-only, evidence/export checks, no real model/A2A calls.

You may use disposable local Git fixtures and local stub subprocesses only.
Do not alter actual P1 source, souls, configs or other rounds' evidence.
Do not connect to real 5bao, 9bao, rusty or production. Preserve distinctions:
FIXED / MITIGATED_FAIL_CLOSED / NOT_FIXED / REGRESSION / NOT_VERIFIED.

Save findings at:
`experiments/hermes-coding-pipeline-p1/audit_evidence/P1/round-005/`
Files: `AUDIT_REPORT.md`, `FINDINGS.json`, `TEST_RESULTS.txt`, `SCOPE.json`.
Use `AUDIT_STATUS: INCOMPLETE` when necessary; never claim a failed-closed
integration path is a completed real-system verification.
Commit reports only and provide report commit SHA, source commit SHA, and links.
