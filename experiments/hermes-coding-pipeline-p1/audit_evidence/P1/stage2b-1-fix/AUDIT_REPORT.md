# Stage-2B-1 Remediation Independent Re-Audit Report (auditor: Qwen-Flash)

- Repo: `k176060444-lgtm/hermes-agent`  Branch: `fix/p1-stage2b1-remediation`
- Re-audited remediation commit (fixed): `c08e0f9738643edce0d49e39f465ff10cb8aaee4` (tree `87b93c80206db8480c9bb78e9fdd0236fb460505`)
- Parent = previous audit-report commit `47f7e18b0025bb6b271de6bf234f14c6741984a1`; original FAIL source `cc3a42cd0e5992bc64ed0bdabafd67cae71e3227`
- Platform: 21bao Windows 10 LTSC 19044, Python 3.11.15, git 2.54.0.windows.1
- Audit status: **COMPLETE**  Code verdict: **CONDITIONAL** (15/16 FIXED; S2B1-009 NOT_FIXED partial; 1 new P3; no new P0/P1)
- Mode: read-only. No source/test/report modification; no accounts, ACLs, gateway, paid models, remote nodes.

## 1. Baseline integrity (VERIFIED_SOURCE)
107/107 files fetched from the FIXED commit by Git blob API, sha1-blob re-hashed
0 mismatch before and after all test runs; probe-copy audited sources also 0
mismatch post-run. Compare 47f7e18b...c08e0f97 = exactly the 11 declared files;
core engine (executor/workflow/state/trust/a2a/contracts/gitops/audit), all
round-001..007 reports and the four stage2b-1 reports byte-identical to their
upstream blobs. Moving HEAD was never used as baseline.

## 2. Per-finding re-verification (16 items, reproducible in FINDINGS.json)
- **S2B1-001 FIXED**: `verify_execution_identity` (runner.py:482-484) now forces
  `validate_launch_request` + `validate_receipt` + manifest shape/disk re-measure
  first; the pin is read ONLY from the `manifest` argument (:485); post-build
  `expected_agent_sid` addition on a request breaks the digest and is refused
  (auditor probe fa3). Self-hash boundary ("tamper-evident, NOT a signature")
  is declared in the module docstring and at the computation site (:144).
- **S2B1-002 FIXED**: liveness/token/image/creation-time fused into ONE OS
  measurement `process_identity` (Windows-only, fail-closed); the injected
  `identity_probe` path executes every rejection check but is FORCED to
  `attested=False` + `test_seam=True` (:515-521); image never comes from the
  receipt path. Probes fa2 + developer locks pass.
- **S2B1-003 FIXED**: dead-PID gap from the previous audit round is CLOSED —
  `process_identity` checks `STILL_ACTIVE` and refuses exited processes even
  while a handle is held (live probe fc1 on 21bao); strict creation-time
  equality blocks PID reuse (fc2, deterministic double-read); post-exit
  verification is a separate `verify_receipt_integrity` that can never return
  `attested=True` (fa1 asserts attested False), and fails closed without
  orchestrator-owned capture files.
- **S2B1-004 FIXED**: receipt schema now binds stage/role/harness/model/
  reviewed_commit/command_sha256/harness_version; all 10 tamper cases refused
  (fd1 matrix).
- **S2B1-005 FIXED**: `poll()` validates structure, request cross-binding and
  manifest echo; junk outbox => RECEIPT_UNVERIFIED + reconciliation_required
  (fd10); a fully bound receipt => validated RECEIPT.
- **S2B1-006 FIXED**: `runner_health` never reports available; fabricated
  complete manifest still yields available=False + 'NOT deployed' (fa4).
- **S2B1-007 FIXED (as scoped)**: bounded enumeration root + SQLite/WAL/SHM +
  evidence dirs in one batched PowerShell query; child-only exposure blocks
  (fd11); live icacls child Everyone grant on 21bao blocks (fd12). Honest
  limitation retained: coverage is only the enumerated paths; real agentx
  ACCESS_DENIED proof remains Stage-2B-2.
- **S2B1-008 FIXED**: strict per-adapter allowlist (codex {--ephemeral},
  opencode {--pure}) with reserved-flag blacklist; -m/--model/-s/--config/
  bypass/unknown/positional all raise in both adapters (fd5, 8x2 cases).
- **S2B1-009 NOT_FIXED (partial)**: the provenance gate is a caller-supplied
  plain dict convention, not verification. Auditor reproductions on 21bao:
  (fb1) bare `{"attested": true}` upgrades CLI self-report to trusted=True;
  (fb2) a runner record with the SAME ordinal but a COMPLETELY DIFFERENT
  command still upgrades ("runner-observed-agreement" across unrelated
  commands — ordinal pairing ignores command identity); (fb4) duplicate
  ordinals silently last-wins; (fb6/fb9) records carry no task/run binding,
  so a record minted for one run upgrades another run's claim in both
  adapters. The previous round asked records to be "bound by (command,
  invocation ordinal/pid)" from an attested path; only ordinal keying and a
  non-authenticable gate flag were implemented. Impact remains P2 (no
  consumer wired, zero dispatch), but the evidence-upgrade trust rule is NOT
  enforced and the developer's own remediation test codifies the bare-dict
  upgrade as expected behavior.
- **S2B1-010 FIXED**: `permissions={"auto":"allow"}` raises OpenCodeProbeError;
  auto renders deny always (fd4).
- **S2B1-011 FIXED**: dedicated init handler forwards all 8 required flags
  (fd6 argv assertions); missing flag raises ConfigError.
- **S2B1-012 FIXED**: bounded pumping at collection time with truncated flags
  (fd7: 128 KiB produced into a 2 KiB cap, kept <= cap).
- **S2B1-013 FIXED**: command-less bash events => command None + no_command,
  unbindable in merge (fd8).
- **S2B1-014 FIXED**: missing role raises OpenCodeProbeError (fd8).
- **S2B1-015 FIXED**: status/exit_code contradiction refused (fd2, 4 cases);
  UNKNOWN reconciliation-only; timestamp ordering/type enforced (fd3).
- **S2B1-016 FIXED (mechanism, live-verified)**: `create_suspended_in_job`
  CREATE_SUSPENDED -> assign -> resume; on 21bao the post-resume grandchild is
  inside the job and the whole tree dies on terminate (fc3); assignment
  failure terminates the suspended child which NEVER executes (fc4 marker-file
  proof). Boundary honest: helper spawns under the CALLER's (KK) identity
  (fc5 measured user_sid == orchestrator) — NOT the provisioned agentx runner.

## 3. Mandatory extra adversarial tests
- **A. Manifest trust provenance** (fa1/fa2 + S2B1F-002): a wholly
  caller-fabricated manifest dict (valid shape, digest matching a file the
  caller itself wrote) satisfies every structural check; `integrity_verified=True`
  therefore proves SELF-CONSISTENCY only. The code correctly keeps
  `attested=False` and documents that integrity is not identity; the residual
  gap is that no anchored provenance (client-read protected path, signed
  issuance) exists when verify/integrity are called directly with a dict.
  The 4 conclusions must remain distinct: field shape valid / local digest
  match / provisioned from protected orchestrator state / runner process
  identity attested — only the first two are machine-checked today.
- **B. Runner-record forgery** (fb1-fb9): see S2B1-009 NOT_FIXED above.
- **C. Real process / Job boundary** (fc1-fc5): dead-PID attestation refused;
  creation-time mismatch refused; suspended spawn closes the escape window;
  assign-failure fail-closed terminates; helper runs under caller identity —
  explicitly must not be described as an agentx-identity runner. All confirmed.

## 4. Supplementary + regression
- approve-spec fails closed: BLOCKED, approved=False, identity_verified=False,
  Popen invocation count zero (fd9). Gap "gateway approval identity binding"
  stays NOT_VERIFIED.
- Executor gate INTACT: flag False, both raises (executor.py:121,129), and
  grep proves NO p1 runtime module imports runner/winjobs/harness (fd13) —
  the remediation layer remains a pure library with zero dispatch.
- Phase 3/4 parallel, Gate 0.2/A/B/5.9, 5/5/2 budgets, SQLite event chain:
  full original suite re-passed unchanged (248 collected), R5/R6/R7 Windows
  ACL/WAL cases genuinely executed (9 windows-live cases not skipped).
- Historical audit reports and all upstream remediation docs/tests (incl.
  test_remediation_round5/6) byte-identical to parent blobs.
- R7-001 carry: trust.py unchanged in this commit (still 38c76de state),
  separately covered by Round-007 audit; no relaxation introduced here.

## 5. Test statistics (auditor's own runs)
- Project suite from fixed snapshot: **248 collected / 243 passed / 0 failed /
  0 errors / 5 skipped** (POSIX-only list verified by name), exit code 0,
  179.0s — DEVELOPER CLAIM MATCHES (previously in Stage-2B-1 they reported a
  wrong "161 collected"; this round 248/243/5 is internally consistent:
  248 = 243 + 5).
- Independent auditor probes: **51 unique cases, 51 passed, 0 skipped on this
  host** (11 Windows skipif guards active), incl. live Job/Object, icacls,
  dead-PID, suspended-spawn experiments in disposable dirs (self-cleaned).
  Initial 1 failure was an auditor fixture typo (missing mkdir), disclosed and
  corrected; no audited source modified.

## 6. Verdict and gates
- **CONDITIONAL**: all three original P1 findings are genuinely fixed with live
  Windows evidence; the real-integration path remains zero-dispatch fail-closed;
  BUT **S2B1-009 remains NOT_FIXED** — evidence upgrade must not trust a
  caller-supplied attestation boolean, and per-record (command, task/run)
  identity binding is still absent — plus new P3 S2B1F-002 (manifest provenance
  anchoring) and pre-existing Stage-2B-2 NOT_VERIFIED boundaries (real runner
  service/transport, agentx identity, real CLI event schemas, gateway approval
  identity binding, production worktrees, P0 A2A).
- Remediation of S2B1-009 is required before this layer may be wired into any
  dispatch path; P1 remains NOT approved for 21bao production use and
  Stage-2B-2 deployment stays blocked pending user approval.
