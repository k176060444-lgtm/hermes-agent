# Stage-2B-1 Round-2 Remediation — Independent Re-audit Prompt (Qwen-Flash)

You are the INDEPENDENT audit agent again. Audit ONLY; do not remediate, do
not deploy, do not enable real coding execution.

## Fixed baseline
* Repo: k176060444-lgtm/hermes-agent
* Branch: fix/p1-stage2b1-remediation2
* Directory: experiments/hermes-coding-pipeline-p1/
* Round-2 remediation commit: <FILL after commit>
* Its parent (re-audit report commit): c36577b763318822fc251680012e83b6ff6d62d2
* Round-1 remediation commit: c08e0f9738643edce0d49e39f465ff10cb8aaee4
* Do NOT audit a moving branch HEAD; pin the exact commit, verify the tree
  and every changed blob before and after tests.

Required reading: docs/STAGE2B1_REMEDIATION2.md, the four re-audit reports
under audit_evidence/P1/stage2b-1-fix/, and every file changed in the round-2
commit (expect: p1/harness/codex.py, p1/harness/opencode.py, p1/runner.py,
tests/test_stage2b1_{harness,runner,remediation}.py,
tests/test_stage2b1_remediation2.py, docs/STAGE2B1_REMEDIATION2.md,
prompts/STAGE2B1_REMEDIATION2_AUDIT_PROMPT.md).

## 1. S2B1-009 closure verification (the only P2)
Independently reproduce, on BOTH adapters, and with your own probes (do not
run only the developer suite):
* `runner_attestation=` now raises TypeError; no signature carries it.
* Every agreement path — byte-perfect command+ordinal+exit+task/run match —
  still returns trusted=False; source stays 'cli-event-self-report'.
* Same ordinal + different command → command_mismatch, never trust.
* Same command + different ordinal → no pairing.
* Duplicate ordinal → ambiguous flag, never silent last-wins.
* Missing ordinal on a record → cannot pair by command string.
* Cross task_id/run_id → cross_execution_binding.
* No execution context → unbound_execution_context.
* Exit-code conflict → exit_code_mismatch (contradiction, not trust).
* One record cannot serve two invocations.
* Records carrying source/attested/signature fields are inert.
* Grep the whole tree for any surviving path that can set trusted=True from
  caller data; confirm none exists outside normalize_event's own
  trusted=False defaults.
* Confirm the round-1 tests that encoded the upgrade as correct behaviour
  were REVERSED into negative assertions, not deleted.

## 2. S2B1F-002 anchoring verification
* verify_execution_identity / verify_receipt_integrity take `home`, not
  `manifest`; a caller dict cannot reach them.
* Reproduce extra-test A from the re-audit: fabricate manifest+receipt+
  captures. Without an anchored file → RunnerUnavailableError fail-closed.
  With one → integrity_verified=True but attested=False,
  runner_identity_attested=False, levels L4=False.
* Anchored manifest bound to another task → rejected.
* Check the honesty of the residual boundary: home anchoring proves
  orchestrator-side storage, NOT runner provisioning; docs/code must not
  claim L3 = full provenance or L4.
* Confirm manifest_sha256 echo still binds receipt→manifest and the pinned
  runner exe is re-measured from disk.

## 3. Regression of the 15 FIXED items
Spot-reproduce at least: S2B1-001 (unsigned/misbound never attested),
S2B1-002 (seam ⇒ attested=False/test_seam=True), S2B1-003 (dead PID,
start-time mismatch, post-exit integrity-only), S2B1-005 (junk outbox ⇒
RECEIPT_UNVERIFIED), S2B1-006 (honest health), S2B1-008 (allowlist),
S2B1-010 (auto:allow rejected), S2B1-016 (CREATE_SUSPENDED path intact),
approve gate fail-closed. Any regression is a finding.

## 4. Full Windows regression (21bao)
Run the whole suite; parse JUnit XML yourself: collected/passed/failed/
errors/skipped/exit code. Developer claim is a statement to verify, not a
fact. Skipped must never be counted as passed. Confirm the 5 POSIX skips and
that Windows live cases actually execute.

## 5. Boundaries
No code/test/soul/historical-audit modification. No accounts, no production
ACLs, no service registration, no plugin install, no gateway restart, no paid
models, no P0/remote nodes. One-shot isolated dirs only for live probes,
cleaned afterwards.

## 6. Deliverables
Four files under audit_evidence/P1/stage2b-1-fix2/ (AUDIT_REPORT.md,
FINDINGS.json, TEST_RESULTS.txt, SCOPE.json), committed on top of the
round-2 commit, read back file-by-file with SHA-256. Report must state:
S2B1-009 final status; S2B1F-002 final status; regression verdict for the 15;
new findings with P0–P3; actual Windows numbers; whether ANY caller-
constructible path to trusted=True exists; remaining NOT_VERIFIED boundaries;
final verdict PASS/FAIL/CONDITIONAL; fixed commit, report commit, links.
Do not presume green. If any real trust bypass survives, grade it honestly.
