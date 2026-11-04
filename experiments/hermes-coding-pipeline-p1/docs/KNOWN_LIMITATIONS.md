# Independent audit checklist / known limitations (candidate v0.1)

**This is a deliberately honest list, not a declaration of production readiness.**

1. **External execution wrappers missing.** Real Codex/OpenCode CLIs, model IDs and native Agent Soul wiring on 21bao are Stage 2. `config/adapters.template.json` is deliberately disabled. P1 currently expects a trusted executable to emit exactly one JSON envelope, whereas Codex/OpenCode native output formats may differ. A real adapter must be implemented and tested.
2. **Approval origin.** Gate 0.1 is represented by SHA-bound human approval metadata, not cryptographically authenticated approval. Gate 0.2 `actor` is a recorded string, not an integrated chat identity proof. P2/Hermes later must own trusted approval generation and validation.
3. **A2A P0 still evolving.** P1 defines adapter `submit/status/collect`, but does not create or modify P0. Real trusted physical-node attestation requires an independently verified trust source (not a self-reported node field or Boolean). Reject any claim that two JSON strings prove distinct physical hosts. Third-seat 600s is assigned to P0, not re-implemented in P1. Reconciliation/cancel APIs are specified but not yet implemented as active controls.
4. **Crash reconciliation is fail-closed, not auto-recovery.** `NEEDS_RECONCILIATION` does not auto-clear a possibly dispatched paid model call. Production-grade safe recovery requires querying real CLI/P0 job IDs, checking source and outputs, and deciding whether to record terminal status. Without that, task remains blocked.
5. **Soul vs physical permissions.** SHA inventory detects net changes on tracked and nonignored untracked files. A role could temporarily write/restore or mutate ignored files/out-of-tree resources. This lightweight design is the user's deliberate tradeoff; treat the risk as not eliminated.
6. **Full TDD/test evidence not yet enforced.** Structured final verdicts and coarse test result fields are checked. Real wrapper must provide original test commands, process exit codes and logs, authenticated to the invocation. Current mock tests only establish state-machine transitions, not quality or genuine TDD.
7. **Side-effect kill switch.** `safety_manifest` is a gate and user-attestation placeholder, not proof code-level side effects are disabled. Real integration must validate an actual task-specific Kill guard prior to running Worker/tests.
8. **Artifact provenance and Git commits.** Report SHA copies and SQLite event hashes do not supply external tamper-evident notarization. The source SKILL also requires audit evidence committed into `audit_evidence/` and Magpie `usage.jsonl` source cross-checks. These are not fully integrated; the external audit must classify them as outstanding.
9. **Compliance retrace origin.** The engine has bounded replay of a stage and downstream, and maps report artifact faults back to an origin stage. Restoring a historical Git base for a replay that crosses code-mutating stages is not fully proven. A case requiring destructive rollback must block for reconciliation rather than pretending to restore a clean chain.
10. **Model fallback.** Approved `backup_model` is recorded in the matrix but not automatically used. An uncertain primary invocation must be reconciled before fallback; silently retrying with a different model risks duplicate side effects. Stage 2 should define safe fallback conditions.
11. **Read-only independent test evidence.** Offline fixture tests are short and use only local disposable Git repositories. They do not validate Windows E: native path handling, real subprocess grandchildren/kill behavior, process timeouts, inter-user permission identity, Magpie originals, 5bao/9bao/rusty independence, or live Hermes plugin integration.
12. **Human Gate5.9.** Workflow stops at an explicit WAITING_GATE_5_9 state. That is a safety feature; this build contains **no operation** capable of approving or deploying to production.
13. **Audit source of truth.** SQLite event hashes detect accidental/simple edits but are not signed/externally anchored and should not be described as tamper-proof against an adversary who can rewrite both rows and hashes.
14. **GitHub initial branch.** Code is first published to an isolated feature branch under an existing user's `hermes-agent` repository because the connected GitHub action set cannot create a new repository. It must not be merged into `main` or treated as live Hermes code without separate approval.

### Severity guide for independent agent

- **BLOCKER:** bypass of Gate 0.2/5.9, forged PASS, false A2A quorum, uncontrolled external re-dispatch, modifying production.
- **HIGH:** incorrect retry/retrace budget, incomplete review join, model/role mismatches, meaningful evidence corruption.
- **MEDIUM:** missing validations, wrong artifact/role provenance, poor Windows compatibility, weak diagnostics.
- **LOW:** style, comments, optional refactoring. Avoid marking as blocking.
