# P1 workflow, accepted decisions and control semantics

## Ownership and goal

Hermes is the **Orchestrator** and intent interlocutor. P2 (later) will formalize the two pre-coding discussions: (A) understand the user's intent, goals, strategies and desired results; (B) present editable default 12-role Harness/model matrix and receive human approval. P1 consumes **both approved outputs** and an explicit Gate 0.1 approval reference. P1 runs from Phase 0.2 Planner until it produces the Gate 5.9 dossier and stops awaiting user approval to deploy.

P1 never replaces Planner's autonomous technical planning with its own. P1 never substitutes a fabricated blind review or a Hermes-produced arbitration decision.

## Phase table

| Stage | Owner | Programmatic output / transition |
|---|---|---|
| 0.2 | Planner | TASK_SPEC candidate; WAITING Gate 0.2 |
| Gate 0.2 | Human | Explicit spec SHA approval; immutable basis |
| 1 | P1 deterministic action | Isolated Git worktree, baseline SHA, side-effect guard prerequisite |
| 2 | Worker | TDD coding, commits, report |
| 3 + 4 | Spec + Quality | **Approved parallel** independent review of identical SHA/spec, separate output and compliance; join barrier |
| 4.5 | Tester A | Test-only additions and Gate A report; feedback to Phase 2 |
| 5.0 | External P0 | A2A job and accepted independent real blind reports; minimum 2 physically distinct hosts, optional third grace 600 seconds enforced by P0 |
| 5.1 | Worker remediation | Fix P0/P1 findings or explicit documented no-op, evidence |
| 5.2 | Tester B | Smoke + canary + no-cache regression evidence |
| 5.3 | Independent Arbitrator | Full case review after final test; PASS/REJECT |
| 5.85 | P1 Pro-Audit policy | Consolidated process-only compliance report |
| Gate 5.9 | Human | Present original complete Arbitration and Pro-Audit reports; P1 stops |

Phase 6 deployment and Phase 7 cleanup are **not implemented**.

## Bounded cycles

- **Local Gate A:** at most 5 Worker rounds (in this candidate, first execution = round 1; if user intended 5 retries instead, clarify before production integration). Any Spec, Quality or Tester A failure returns to Phase 2. Both reviewers must review a new commit after any Worker change.
- **Final Gate B:** at most 5 remediation rounds (first execution = round 1). Tester B or Arbitrator failures return to Phase 5.1, with new independent final testing and arbitration.
- **Global process compliance:** at most 2 reruns of the affected phase chain. Third substantive non-compliance fails. Evidence insufficiency with unknown execution outcome is blocked for reconciliation, **not blindly counted as a rerun**.

## Trust / failure boundaries

The workflow records an execution intent and external invocation before it runs a Harness. A crash while a task was RUNNING is ambiguous; P1 must not dispatch the same call again automatically. `reconcile` is read-only and exposes unfinished invocations. Recovering an ambiguous external call will require verified Harness/P0-specific reconciliation logic in Stage 2. There is no "force clear all" command to fake completion.

Review agents execute on the same source snapshot. P1 checks Git-visible pre/post source inventory and HEAD. It does not claim airtight OS sandbox protection; write-restore and deliberately ignored files are limitations of this lightweight policy. REPORT files go in the P1 evidence directory rather than the reviewed worktree to avoid shared file overwrite.

Each role execution is tied to a frozen role Soul SHA, approved matrix SHA, original intent SHA, target spec SHA and source commit. The original output and logs must be stored by a **trusted wrapper**; P1 does not count a model's self-report as evidence that a command/test actually ran.

Evidence produced from fixtures is conspicuously labeled. P1 must reject fixture-mode data for real acceptance. The current implementation checks controlled local wrappers and P0 adapter fields, but true attestation of physical hosts, model provenance and original Magpie logs is not yet fully implemented. **No real execution acceptance is claimed.**

## Approved process deviations from source SKILL

1. Phase 3 and 4 are **parallel**, on same SHA, with two independent reports and two compliance audits; join occurs before Tester A.
2. Global compliance retrace limit is **2** (rather than original 1).
3. Pro-Audit role is reinterpreted as process-only per-stage compliance policy plus 5.85 consolidated report; it does not make technical verdicts.
4. Reviewers are Soul-bound and source-SHA audited, without making physical read-only sandboxing a blocking P1 development prerequisite; residual risk acknowledged.
5. P1 is limited to Gate 0.1 handoff -> Gate 5.9 wait. P0 A2A details are external, and P2 conversation/matrix preparation is a later project.

Remaining explicit decisions, such as original SKILL's fixed Harness references versus zero hardcoding and the precise meaning of "5 rounds", are tracked rather than silently rewriting the source.
