# P1 Round-002 independent-audit remediation — candidate for Round-003

**Source**: independent audit at GitHub commit `541c25a20334b9cb1c77fe7bb34a2e13965eaeeb`, assessing `7ef210a90bc3cd8ec3d230d1901f0fbd7715015c`.

**Status**: local remediation candidate; no independent Round-003 verdict yet. No production approval; `integration` mode remains code-blocked. No real Codex/OpenCode, P0, Debian, Magpie or 21bao environment calls made during developer tests.

## Mandatory findings disposition (pending independent confirmation)

| IDs | Candidate code changes | Verification |
|---|---|---|
| P1-004, P1-017 | `gitops.clean` now rejects assume-unchanged/skip-worktree index bits and recomputes checked-out tracked blobs against the actual index, not just `git status`. `index_digest` binds flags. | Round2 hidden-flag regression checks |
| P1-006, R2-001 | Tester A and B may add test files, but cannot overwrite/delete any pre-existing test; protected tests from previous phases verified for both Tester and Worker; final evidence verifies protected test content. | Tester deletion/rewrite probes, test-only commit transition probe |
| P1-015, R2-002 | `resume()` validates event/state journal and Gate0.2 **before** writing `external_poll_resumed`. On tainted preflight it raises and leaves original event chain available for inspection. `run` preflight no longer rewrites corrupt row. | SQLite job-id tamper with event count preservation |
| P1-016, R2-003 | Every completed run's canonical `details` SHA is bound to a hashed finish event; verification independently matches the current runs table, including invocation log hashes. | Combined stdout plus details forgery probe |
| P1-019 | Phase entry captures its input Git SHA; compliant retrace into a historical development phase on a new SHA fails closed with `NEEDS_RECONCILIATION`. No automatic Git history rewriting. | Real local remediation commit followed by earlier worker artifact corruption |
| P1-022, R2-004 | Eliminated keyword-substring parsing. No-commit remediation requires `no_op=true`, nonempty `no_op_reason`, and no actionable unresolved remote findings. | Legitimate English no-op reason / keyword-only fake reason |

## Secondary findings

| IDs | Candidate treatment | Remaining caveat |
|---|---|---|
| R2-005 | Gate0.1 approval now binds `souls_sha256` (canonical all 12 per-role Soul SHA manifest). Initialization rejects modified Soul bytes. Updated `gate01.template.json` and test fixture. | This strengthens the Gate0.1 *contract*, but true human signer identity is unverified. |
| R2-006 | A2A report must be nonblank string; optional/required role assignment binding checked. | Full raw remote transport receipt and independently trusted role/host identity remain unimplemented; integration remains blocked. |
| R2-007 | Both role and A2A adapters read only the frozen adapters snapshot with digest validation, not mutable task path. | Trusted external executable identity remains unverified. |
| R2-009 | A2A failure state/code/reason now recorded as a bounded event diagnostic. | Live log redaction and P0 protocol still to be integrated; keep diagnostic untrusted. |
| R2-010 | Safety manifest is parsed and side-effect guard shape validated at init. | Live kill-guard behavior remains unverified. |
| R2-011 | Failed initialization removes this attempt's snapshot and SQLite files, allowing clean reinitialization in local test. | Crash/power-loss transactional init on Windows E: remains unverified. |
| R2-012 | Library `call_adapter()` now hard-blocks real execution independently of normal pipeline entry. | Actual trusted P0 adapter implementation is a separate workstream. |
| R2-008 | **Not yet fixed**: live subprocess stdout/stderr still use unbounded `capture_output`. | Non-blocking P3 hardening; must be addressed before live lengthy runs. |

## Regression validation

From project root on isolated host:

```text
python -m pytest -q
python -m compileall -q p1 tests
```

At this developer iteration: **64/64 offline tests passed**, consisting of 47 previous tests plus 17 additional tests in `tests/test_remediation_round2.py`. These are local, isolated Git fixture tests, not real Agent/P0 tests. The Round-003 auditor must independently reproduce and reclassify issues rather than accepting this statement.

## Operational boundaries

* P1 remains scoped to Phase 0.2 through Gate 5.9, not Phase 6/7.
* Phase 3/4 independent reviewers stay parallel and same-commit.
* Gate 0.2 remains human approval; loop limits 5/5/2 unchanged.
* `integration` execution still fails closed until evidence of trusted role/model, test execution and P0 physical identity is available.
* DB event hashes protect against **partial edits**, not a privileged local adversary rewriting all event rows, runs and the local trust anchor. Cross-trust-boundary signed/WORM anchoring is a separate design and security decision.
* Reconciliation for altered historical commit deliberately stops for manual reconciliation rather than attempting a guessed automatic reset.
