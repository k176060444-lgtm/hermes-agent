# Stage-2B-1 Independent Audit Report (auditor: Qwen-Flash)

- Repo: `k176060444-lgtm/hermes-agent`  Branch: `feature/p1-stage2b-20261104`
- Audited source commit (fixed): `cc3a42cd0e5992bc64ed0bdabafd67cae71e3227` (tree `ce01db59ed980bdd99b18685c572149163f1c5eb`)
- Parent: `38c76de3f7e8b47951b01d430806fffe10fe1cdc`  Round-007 audited source: `cda5f4873c253d5926c86d84b7ada138427b9bc7` (report `bc9b6cba32c79bbe1c9060332b459ae342e30fee`)
- Platform: 21bao Windows 10 LTSC, Python 3.11.15, git version 2.54.0.windows.1
- Audit status: **COMPLETE**  Code verdict: **FAIL** (3x P1, 8x P2, 5x P3; no P0)
- Mode: read-only audit; no source, ACL, account, gateway, remote node or paid-model change.

## 1. Baseline integrity (VERIFIED_SOURCE)
100/100 files of the fixed commit fetched via Git blob API and re-hashed: 0 mismatch before AND after the test runs (blob recheck re-run post-suite). Diff vs audited Round-007 source: 5 changed files (README, KNOWN_LIMITATIONS, p1/trust.py=R7-001 carry, tests round5 stub, tests round6) + 19 new files; executor/workflow/state/a2a/contracts/gitops/audit blobs byte-identical to `cda5f48`. No moving HEAD used.

## 2. What genuinely works (independently re-verified on 21bao Windows)
- **Fail-closed dispatch**: `TRUSTED_INTEGRATION_EXECUTION_VERIFIED=False`, both executor raises intact; grep proves `p1/runner.py`, `p1/winjobs.py`, `p1/harness/*` are imported by NO p1 runtime module - pure library, zero real dispatch path. Architecture requirement held.
- **Self-reported booleans grant nothing**: `isolated:true` in a receipt is inert (probe a01); no code path reads it.
- **Live OS identity measurement works**: `live_process_token`/`live_process_image` return the real KK SID + 14 groups / actual image path on 21bao (probes a08/a09); SID==orchestrator and Administrators-membership are rejected even when receipt/manifest self-consistent (dev tests + probes a07).
- **Frozen harness re-hash from disk**: swapped binary with stale live report is blocked (b06); version drift and capability loss blocked (b07); model/sandbox required, no hidden defaults (b04); argv built only from matrix (b05 positive part).
- **CLI self-report vs runner record split exists** (b09: every extracted record trusted=False) - but see S2B1-009 for the missing provenance gate on the upgrade side.
- **Job Object core semantics verified live**: two-generation kill via close (d01), holder-crash KILL_ON_JOB_CLOSE kills member (d04), bad-pid assign rejected (d03). Independent wrapper only - NOT integrated into any runner (S2B1-016 residual race).
- **Plugin draft is inert**: refuses without explicit absolute p1_repo_dir (c02), never auto-registers (c06), no install/service/ACL code (c05), approval provenance mandatory and every approval marked identity_verified=False (c03); CLI failure codes surfaced honestly (c01/c03).
- **UNKNOWN receipts are reconciliation-only** (a11); request digest tampering caught (a12); weak bindings rejected (a13); client without manifest blocks launch (a14); manifest pinning the orchestrator SID reports unavailable (a17).

## 3. Findings (16; full evidence in FINDINGS.json)
Severity: P0 0 / P1 3 / P2 8 / P3 5.

The three P1s are the audit-brief core questions answered NO:
- **S2B1-001**: the agent SID is NOT bound to a trusted manifest at the verify layer. `expected_agent_sid` is a caller-fillable request field; `verify_execution_identity` never calls `validate_launch_request`/`validate_receipt`, so an unsigned request with a fully misbound receipt attests (probe a09c, 21bao). No dispatch path exists today, which is why this is P1 and not P0 - but it is the exact seam Stage-2B-2 wiring will hit.
- **S2B1-002**: `probe = process_alive or live_process_token` fuses liveness and identity into one injectable seam; a dict-returning fake replaces live token measurement AND skips the live image query (receipt path digested instead). The brief's 'process_alive vs live_process_token separation' requirement is not met.
- **S2B1-010**: reproduced exactly as the brief demanded - `render_agent_markdown(permissions={'auto':'allow'})` emits `auto: allow`, violating the module's own 'auto always denied' rule.

P2 highlights: dead/recycled PID still attests (S2B1-003); receipts cannot prove the approved model/role/commit/argv ran (S2B1-004); poll() returns unvalidated outbox JSON (S2B1-005); runner_health says available with no service running (S2B1-006); ledger check is root-only (S2B1-007, MITIGATED_FAIL_CLOSED); extra_argv can override -m/-s and inject sandbox-bypass flags (S2B1-008); merge_runner_records upgrades trusted from any caller-supplied list and reuses one record across invocations (S2B1-009); Job assign race lets pre-assignment descendants escape (S2B1-016). P3: plugin init drops 7 required flags (S2B1-011); unbounded stdout capture in plugin (S2B1-012); literal 'None' command records (S2B1-013); bare KeyError path (S2B1-014); status/exit_code never cross-checked (S2B1-015, MITIGATED_FAIL_CLOSED).

## 4. Carried changes re-check (38c76de, not yet Round-008-audited)
- **R7-001/38c76de** = `VERIFIED_CARRY` - trust.py protected_root is path-identified (normcase+abspath), required exactly once, root record matched by path not position; r7_001 x4 + r6_001 x6 + r5_001 x2 all PASS in auditor-run Windows suite; real WAL recreation test ran 1.314s PASS. No relaxation found.
- **round5-stub-fix** = `ACCEPTED_TOOLING` - test_remediation_round5.py stub widened to **kwargs only; still asserts the same inspected-name set; no product semantics changed.
- **executor-gate** = `INTACT` - TRUSTED_INTEGRATION_EXECUTION_VERIFIED=False; both raises present (executor.py:121,129); grep proves runner/winjobs/harness are NOT imported by any p1 runtime module - pure library, zero dispatch path.
- **R5-005** = `MITIGATED_FAIL_CLOSED` - no provisioned agentx identity/service; runner layer is offline contract only.
- **R2-006** = `MITIGATED_FAIL_CLOSED` - P0/A2A untouched; no transport, no physical identity.
Conclusion: the R7-001 carry is sound on 21bao (path-identified protected root, exactly-once assertion, real WAL lifecycle test PASS 1.314s in auditor-run suite); the round5 stub fix is test-tooling only. This is a supplementary check, not a substitute for Round-008.

## 5. Test statistics (auditor's own runs, not copied from developer)
See TEST_RESULTS.txt. Key correction: the developer summary '161 collected / 161 passed / 5 skipped' is internally inconsistent. JUnit XML from the fixed snapshot: **166 collected / 161 passed / 0 failed / 0 errors / 5 skipped** (all 5 skips are POSIX-only cases; the Windows WAL/ACL cases genuinely executed and passed).

## 6. Verdict and boundaries
- Code verdict **FAIL**: three P1 identity/binding defects must be remediated before any Stage-2B-2 wiring; none currently opens a dispatch path, so the pipeline remains safely blocked (the fail-closed architecture itself PASSED every attack we tried).
- NOT_VERIFIED (unchanged): real runner service/transport, agentx account and live separate-identity attestation, real Codex/OpenCode event schemas against installed CLIs, real model/test receipts, P0 A2A physical identity (R2-006), gateway-integrated approval identity binding, production E: worktrees.
- P1 must NOT be declared runnable on 21bao. Stage-2B-2 provisioning stays blocked pending developer remediation of S2B1-001/-002/-010 (at minimum) and user approval.
- Auditor fixture disclosure: 3 of my own initial probe expectations were wrong (Popen handle-retention semantics, venv base-interpreter image path, docstring negation match); corrected to factual assertions before final evidence. No audited source was modified to make any test pass.
