# P1 Round-003 independent-audit remediation — Round-004 candidate

**Source audit:** GitHub report commit `e544d5e0cc1471c7844baf5c6f0ba10dbbd3db81`, reviewing source commit `2fd65c1269dcb29391ffac1579745c1dddfe04f5`.

**Status:** offline candidate only. New independent Round-004 audit required. No real 21bao, Codex/OpenCode, paid model, P0/A2A, or production tests performed. `integration` remains hard BLOCKED.

## Findings disposition proposed for independent verification

| Finding | Changes | Regression evidence |
|---|---|---|
| R3-001 (P2) | `p1/gitops.py` now treats `test_path()` as an explicit test-module filename whitelist, not all files under `tests/`. Newly added `conftest.py`, `pytest.ini`, `pyproject.toml`, `__init__.py` and arbitrary helper files are disallowed. `test_commit_transition()` also checks that added Git tree entries are regular blobs, not symlinks/submodules. Existing tests are immutable for Tester A/B as in previous round. | `tests/test_remediation_round3.py`: rejected collection-control filenames; both Tester A/B adding a `conftest.py` result in NON_COMPLIANT; normal new `test_*.py` remains accepted at Tester A. |
| R3-002 (P2) | `p1/state.py` verifies every dispatch/finish event references an existing run row; every run row has an exact dispatch event; stage, role and input SHA agree with the dispatch event; finished records agree with the finish event. Duplicate dispatch/finish events are rejected. This closes run deletion and stage/role substitution without invalidating in-flight RUNNING runs. | Offline probes delete a completed run, change stage/role/input SHA, and duplicate a finish journal event; each is detected. Tampered evidence blocks export. |
| R3-003 (P3) | `Pipeline.status()` now reports effective `BLOCKED` and `persisted_status` with read-only `integrity_preflight` diagnostic when current persisted state contradicts the journal or Gate 0.2 approval. It **does not** overwrite task rows or events, preserving the forensic evidence. | Tampered task row yields BLOCKED observation while SQLite task status and event count remain unchanged. |

## Known limitations / deliberately not changed

* R2-006: raw external A2A wire receipt, physical-node attestations and real protocol binding remain NOT_VERIFIED. `integration` is still fail-closed, not ready.
* R2-008: unbounded stdout/stderr `capture_output` remains a known **P3 non-blocking** issue for later stream-bounded logging. Not falsely marked FIXED.
* A whitelisted test module is not guaranteed to be free of arbitrary runtime side effects merely by its filename. The policy prevents the specific collection-control-file bypass, not every conceivable runtime test manipulation.
* SQLite local hash chaining detects partial local record tampering but is not an external trusted ledger against a privileged actor able to rewrite all local state and its trust anchor.
* Live Codex/OpenCode identities, real test execution receipts, P0 provenance, actual Windows E: worktree, full hard-crash recovery and kill guard remain NOT_VERIFIED.

## Local developer validation

From this isolated candidate project directory:

```
python -m pytest -q --disable-warnings
python -m compileall -q p1
python -m p1 --help
```

Result: **93/93 offline pytest cases PASS**, 0 failures; compileall and CLI help PASS. This extends the previously independently reviewed 64 original cases with 29 parameterized/new regression cases. These are offline fixture tests; the Round-004 auditor must rerun them independently and independently re-check the two original defect reproductions.

## Strict unchanged workflow

Hermes is the Orchestrator, P1 is its deterministic internal engine. P1 receives approved intent plus approved 12-role matrix and begins at Phase 0.2; Human Gate 0.2 remains required. Phase 3/4 execute concurrently against the same commit, with separate reports and audits. Gate A/B and the 5/5/2 budgets are unchanged. P1 ends at Gate 5.9 and neither deploys nor cleans production. External P0 A2A orchestration remains a separate service.
