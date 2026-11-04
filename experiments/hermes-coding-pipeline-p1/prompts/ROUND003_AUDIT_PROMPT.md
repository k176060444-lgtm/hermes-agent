# Hermes Coding Pipeline P1 — Round-003 independent code review

Repository: `k176060444-lgtm/hermes-agent`

Branch: `feature/p1-coding-pipeline-20261104`

Code directory: `experiments/hermes-coding-pipeline-p1/`

**Audited source commit MUST be fixed by the operator at invocation time** to the code remediation commit (not the later audit-report commit). Never silently switch source tree while investigating.

## Objectives

Review Round-002 `audit_evidence/P1/round-002/{AUDIT_REPORT.md,FINDINGS.json,SCOPE.json,TEST_RESULTS.txt}` and `docs/ROUND_002_REMEDIATION.md`. Verify against the code (not the remediation prose) each unresolved Round-001 finding: `P1-004`, `P1-006`, `P1-015`, `P1-016`, `P1-017`, `P1-019`, and regression `P1-022`. Then independently reassess Round-002 new `R2-001`–`R2-012` and look for regressions in changed code.

Essential checks:

* Git assume-unchanged / skip-worktree and actual file-vs-index content (check CRLF filters and Windows paths).
* Tester A may not delete/edit pre-existing tests; Tester B may not weaken Gate A exams, and worker may not weaken protected tests. Verify test-only commit diff semantics.
* `resume()` cannot seal modified state into trusted event history before journal/Gate 0.2 checks.
* `runs.details` and log files bound through immutable run-finish event journal; avoid treating self-recomputed checksums as independent trust anchors.
* Replay from earlier development stage cannot silently switch to an unrelated later commit; verify behavior on real local commits.
* Structured no-op reason accepts valid wording, rejects unverifiable/unresolved issues without consuming unbounded retry budgets.
* Gate 0.1 approval binds exactly the 12 role Soul hashes; invalid template/approval is rejected.
* Adapter commands are always sourced from frozen snapshots, and `integration` remains fail-closed including library-level A2A entry point.
* Phase 3/4 still run concurrently, same commit, independent report and compliance audit; no change to 5/5/2 limits or Gate 5.9 stop.

Pro-Audit must inspect **workflow compliance and upstream/downstream evidence only**, not redo the professional code-quality judgment. Distinguish code correctness defects from future real environment integration gaps. Real Codex/OpenCode, physical Debian nodes, Magpie/provider identity, human signer and live production controls are **NOT_VERIFIED**.

Execute only local, offline, disposable tests; never modify audited source, existing Soul, production profiles or A2A hosts, never call real paid models. Preserve actual stdout, command exit code and test case list; tests that assert a bug is reproduced must not be described as product tests passing.

Create a new `audit_evidence/P1/round-003/` with exactly these required report artifacts:

* `AUDIT_REPORT.md` – COMPLETE/INCOMPLETE, PASS/FAIL/CONDITIONAL, evidence and per-finding dispositions
* `FINDINGS.json` – recheck each Round-002 original finding ID and any new issues with severity, file:line, reproduction and fix suggestion
* `TEST_RESULTS.txt` – commands, exit codes, counts and limitations
* `SCOPE.json` – audited code SHA, time, host, scope, simulation/live distinction

Push only those four audit files to the same feature branch; never edit the code under review or overwrite Round-001/002 evidence. Re-read each uploaded file and provide report commit SHA and its audited source SHA. **Do not approve real 21bao integration based solely on offline tests or a fail-closed mode.**
