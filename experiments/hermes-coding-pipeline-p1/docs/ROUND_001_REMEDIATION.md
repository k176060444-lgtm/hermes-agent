# P1 Round-001 audit triage and remediation (candidate for independent Round-002)

- **Audited baseline:** `13d282596b9afee734996bb7a28ece1ace97c537`
- **Independent report commit:** `a72e13a987ca490ec73c9c9456741c0bd4e8df39`
- **Independent conclusion:** `COMPLETE / FAIL`; 9 P0, 13 P1, 7 P2, 0 P3.
- **Source:** `audit_evidence/P1/round-001/` (left unchanged).
- **Remediation mode:** isolated offline coding and regression tests only. No real Codex/OpenCode, P0, Debian nodes, 21bao or production paths accessed.
- **Assessment:** The reproduction evidence is substantive; findings are accepted as defect reports. Where the needed trusted execution/identity protocol is unavailable, this revision must **fail closed** instead of inventing evidence.

## Finding disposition

| Finding | Response in candidate | Confidence / restriction |
|---|---|---|
| P1-001 P0 | Real A2A collection always rejects unsupported physical identity attestations, including self-reported booleans. | **BLOCKED pending P0 identity trust contract**; not a real identity verifier. |
| P1-002 P0 | A2A `QUESTION` / `NEEDS_SPECIALIST` wait for clarification; distinguish invalid verdict, terminal failures and `REQUEST_CHANGES`. | Offline regression. |
| P1-003 P0 | `integration` explicitly blocked before any role dispatch because trusted test execution receipts do not yet exist. | **BLOCKED pending trusted test executor**; no real tests certified. |
| P1-004 P0 | Before and after each role, require clean Git index + worktree; refuse any uncommitted Worker work. | Offline regression. |
| P1-005 P0 | Freeze an arbitration case manifest with task, commit, spec, matrix and original evidence hashes. | Manifest presence is **not proof model read the case**; integration still BLOCKED. |
| P1-006 P1 | Preserve Tester A test-file content hashes; worker cannot change/delete the preserved exam. | Offline regression. Temporary write/restore not detectable with snapshots. |
| P1-007 P0 | Export only the exact registered arbitrator report and compliance report; check all evidence and SHA of the same bytes read. | Offline regression. |
| P1-008 P1 | Exclude historical `5.85:pro_audit` NON_COMPLIANT from the current audit pass decision. | Offline regression. |
| P1-009 P1 | Resolve a fixed base commit before Planner, require Planner HEAD equals it, create worktree from the frozen SHA. | Offline regression. |
| P1-010 P1 | Local roles required on the sole Windows primary node declared in the matrix; blind roles required on Debian nodes. | Offline regression. This does not authenticate the physical executing computer. |
| P1-011 P1 | Reject blank/incomplete Soul contracts; freeze bytes and hashes. | Offline regression. Actual native Soul loading still NOT_VERIFIED. |
| P1-012 P2 | Always preserve both completed parallel reviewers' independent audits before judging the join. | Offline regression. |
| P1-013 P2 | Return nonzero CLI process status on `FAILED`, `BLOCKED`, `NEEDS_RECONCILIATION` and failed `audit`. | Offline regression. |
| P1-014 P0 | Validate Gate 0.1 from in-memory bytes and atomically publish those exact bytes; eliminate validate-then-copy race. | Offline regression. Human identity provenance remains NOT_VERIFIED. |
| P1-015 P0 | Hash each stored task row into the corresponding event, verify state/journal before dispatch, independently recheck Gate 0.2 approval event and spec SHA. | Stops **row-only tampering**; local adversary with full DB/event write can rebuild chain; external trust anchor is still required for that threat model. |
| P1-016 P1 | Preserve each role's raw stdout/stderr with SHA in run detail; recheck in final audit and export. | Offline regression. |
| P1-017 P1 | Hash Git index blob IDs, stage entries and modes before/after read-only roles. | Offline regression. |
| P1-018 P1 | Tester commits must be additive descendants affecting only test paths; new commit becomes downstream baseline. | Offline regression. |
| P1-019 P1 | Refuse role dispatch if Git HEAD is different from persisted stage input; block unsafe compliance replay for reconciliation. | Offline regression. Full destructive rollback intentionally not implemented. |
| P1-020 P1 | Any unresolved structured reviewer QUESTION forces clarification even when top-level says APPROVE. | Offline regression. |
| P1-021 P0 | No real execution allowed until trustworthy runner/model provenance exists; explicit simulated payload is rejected by compliance. | **BLOCKED pending integration**. |
| P1-022 P1 | Worker and remediation Worker require real nonempty report; no-op remediation must explain why. | Offline regression. |
| P1-023 P2 | Require exactly three distinct blind candidate nodes and a one-to-one role mapping. | Offline regression. |
| P1-024 P2 | Terminal A2A `FAILED`, `CANCELLED`, `REJECTED`, `EXPIRED` block; unknown status needs reconciliation. | Offline regression. |
| P1-025 P2 | Save bounded partial stdout/stderr and timeout metadata before reporting invocation uncertainty. | Test with injected subprocess timeout only. |
| P1-026 P2 | Validate all input/Soul bytes before atomic snapshot publication; failed validation does not poison retried init. | Offline regression. |
| P1-027 P1 | Verify journal and Gate 0.2 approval before every phase dispatch, rather than waiting for 5.85. | Offline regression. |
| P1-028 P1 | Freeze adapter and safety configuration bytes and hashes; reject changes to frozen copies. | Offline regression. Real executable binary/code identity remains unverified. |
| P1-029 P2 | Add approved spec SHA, Soul manifest SHA and all blind role assignment data to P0 submit request; check returned matching fields when available. | **P0 schema negotiation pending**; never assert real binding until independently validated. |

## Mandatory second independent audit

A second agent must read the latest **source commit** and **preserved original findings**; execute regression tests and attempt to reproduce each exploit against the new revision. In particular:

1. Probe the verified-FALSE integration entry point without enabling live paid models or remote services; there must be no dispatch.
2. Probe row-only tampering, Gate 0.2 bypass, raw stdout replacement, unregistered arbitration report injection, Git index-only change and uncommitted Worker code.
3. Probe 3+4 truly parallel independent results/audits and failing reviewer paths.
4. Probe Tester A exam weakening, tester HEAD rewrites and source baseline drift before replay.
5. Probe A2A QUESTION/NEEDS_SPECIALIST, fake physical identities and P0 terminal FAILED statuses.
6. Confirm absence of any P1 commands that can deploy, modify production, call live remote reviewers or authorize Gate 5.9.

Do not treat mock passing tests as independent proof of external provenance. Send the next audited report to `audit_evidence/P1/round-002/` on the same branch, keeping `round-001/` immutable. Categorize partial fixes or unresolved integration boundaries explicitly; do not declare `PASS` merely because fake external calls are blocked.
