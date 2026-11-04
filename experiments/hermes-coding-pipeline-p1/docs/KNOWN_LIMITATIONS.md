# Independent audit checklist / known limitations (post Round-001 remediation candidate)

**This is a deliberately honest list, not a declaration of production readiness.**

1. **External execution wrappers missing.** Real Codex/OpenCode CLIs, model IDs and native Agent Soul wiring on 21bao are Stage 2. **All integration launches currently fail closed**, even if the sample adapter claims authorized; removing this hard lock is a separate future audited change. `config/adapters.template.json` is deliberately disabled. P1 currently expects a trusted executable to emit exactly one JSON envelope, whereas Codex/OpenCode native output formats may differ. A real adapter must be implemented and tested.
2. **Approval origin.** Gate 0.1 is represented by SHA-bound human approval metadata, not cryptographically authenticated approval. Gate 0.2 `actor` is a recorded string, not an integrated chat identity proof. P2/Hermes later must own trusted approval generation and validation.
3. **A2A P0 still evolving.** P1 defines adapter `submit/status/collect`, but does not create or modify P0. Real trusted physical-node attestation requires an independently verified trust source (not a self-reported node field or Boolean). Reject any claim that two JSON strings prove distinct physical hosts. Third-seat 600s is assigned to P0, not re-implemented in P1. Reconciliation/cancel APIs are specified but not yet implemented as active controls.
4. **Crash reconciliation is fail-closed, not auto-recovery.** `NEEDS_RECONCILIATION` does not auto-clear a possibly dispatched paid model call. Production-grade safe recovery requires querying real CLI/P0 job IDs, checking source and outputs, and deciding whether to record terminal status. Without that, task remains blocked.
5. **Soul vs physical permissions.** Git worktree inventory and index hashes detect net changes to Git-visible files, staged entries and file modes. A role could temporarily write/restore or mutate ignored files/out-of-tree resources. This lightweight design is the user's deliberate tradeoff; treat the risk as not eliminated.
6. **Full TDD/test evidence not yet enforced.** Structured final verdicts and coarse test result fields are checked in **simulation mode only**; live workflow must remain BLOCKED until trusted test command execution receipts are implemented. Real wrapper must provide original test commands, process exit codes and logs, authenticated to the invocation. Current mock tests only establish state-machine transitions, not quality or genuine TDD.
7. **Side-effect kill switch.** `safety_manifest` is a gate and user-attestation placeholder, not proof code-level side effects are disabled. Real integration must validate an actual task-specific Kill guard prior to running Worker/tests.
8. **Artifact provenance and Git commits.** The new raw log digest checks, exact registered final-report export and task-row-to-event hash binding cover several observed local tampering bugs, **but none supplies external tamper-evident notarization**. The source SKILL also requires audit evidence committed into `audit_evidence/` and Magpie `usage.jsonl` source cross-checks. These are not fully integrated; the external audit must classify them as outstanding.
9. **Compliance retrace origin.** The engine has bounded replay of a stage and downstream, and maps report artifact faults back to an origin stage. Restoring a historical Git base for a replay that crosses code-mutating stages is not fully proven. A case requiring destructive rollback must block for reconciliation rather than pretending to restore a clean chain.
10. **Model fallback.** Approved `backup_model` is recorded in the matrix but not automatically used. An uncertain primary invocation must be reconciled before fallback; silently retrying with a different model risks duplicate side effects. Stage 2 should define safe fallback conditions.
11. **Read-only independent test evidence.** Offline fixture tests are short and use only local disposable Git repositories. They do not validate Windows E: native path handling, real subprocess grandchildren/kill behavior, process timeouts, inter-user permission identity, Magpie originals, 5bao/9bao/rusty independence, or live Hermes plugin integration.
12. **Human Gate5.9.** Workflow stops at an explicit WAITING_GATE_5_9 state. That is a safety feature; this build contains **no operation** capable of approving or deploying to production.
13. **Audit source of truth.** SQLite event hashes and the new row-state seals detect accidental/simple edits, but are not signed/externally anchored and should not be described as tamper-proof against an adversary who can rewrite both rows and hashes.
14. **GitHub initial branch.** Code is first published to an isolated feature branch under an existing user's `hermes-agent` repository because the connected GitHub action set cannot create a new repository. It must not be merged into `main` or treated as live Hermes code without separate approval.

### Severity guide for independent agent

- **BLOCKER:** bypass of Gate 0.2/5.9, forged PASS, false A2A quorum, uncontrolled external re-dispatch, modifying production.
- **HIGH:** incorrect retry/retrace budget, incomplete review join, model/role mismatches, meaningful evidence corruption.
- **MEDIUM:** missing validations, wrong artifact/role provenance, poor Windows compatibility, weak diagnostics.
- **LOW:** style, comments, optional refactoring. Avoid marking as blocking.

15. **Audit Round-001 was FAIL.** See `ROUND_001_REMEDIATION.md` for the 29 finding dispositions; the candidate needs independent Round-002 review. All real-execution and privileged local-state attacker guarantees remain unverified.

### Round-002 candidate remediations (independent Round-003 audit pending)

See `ROUND_002_REMEDIATION.md`. Gate0.1 now requires a `souls_sha256` fingerprint in the approval object. No-op remediation requires structured `no_op=true` and a nonblank `no_op_reason` rather than matching English/Chinese substrings. Developer tests are offline fixtures only; they do not establish actual Harness, test receipt, A2A identity or Windows E: readiness. Live subprocess output is not yet size-bounded (R2-008), and a fully privileged actor capable of rewriting an entire local event chain still requires a separate trust anchor.

### Round-004 remediation candidate (independent Round-005 audit pending)

- **R4-001:** Live-mode P1 ledger enforces a single-trusted-OS-identity private
  task-home boundary (see `p1/trust.py`). The Windows NTFS check is **not yet
  validated on 21bao**. This is **not a defense against a same-user process**:
  Worker/Reviewer/Tester must not have the orchestrator's OS identity with
  access to task home. Otherwise a chain-external HMAC/WORM anchor is required.
  Integration remains disabled regardless of ACL result.
- **R4-002/R4-003:** NUL-delimited Git parsing and effective orphan-run
  reconciliation have isolated regressions.
- **R2-008:** Direct-child stdout/stderr now have bounded capture and evidence
  metadata. Real Windows descendant-process cleanup is still NOT_VERIFIED.
- **R2-006:** External A2A wire receipts and physical identity remain fail closed.

### Round-005 remediation candidate (independent Round-006 audit pending)

See `ROUND_005_REMEDIATION.md`. Windows-specific DACL unit tests have been
added but not executed on 21bao by the developer; the Stage-2 requirement for
a dedicated independent runner OS identity remains **NOT_VERIFIED**, and a
plain local subprocess remains forcibly disabled even if the old provenance
Boolean were toggled. The task ledger's hash chain does not prove that the
trusted OS account itself was uncompromised. WAL/SHM paths and run capture
metadata have additional local checks. External P0 transport receipts and
real agent/test/approval provenance remain unavailable.
