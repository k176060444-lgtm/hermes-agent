# P1 Round-002 independent remediation audit prompt

You are an **independent software engineering auditor**. Review the new, exact P1 remediation source commit; do not rely on developer assertions or previous passing tests as proof.

**GitHub:** `k176060444-lgtm/hermes-agent`  
**Branch:** `feature/p1-coding-pipeline-20261104`  
**Project root:** `experiments/hermes-coding-pipeline-p1/`  
**Original audited source commit:** `13d282596b9afee734996bb7a28ece1ace97c537`  
**Original independent FAIL report commit:** `a72e13a987ca490ec73c9c9456741c0bd4e8df39`  
**New remediation source commit:** determine from GitHub branch HEAD and **freeze the exact SHA before auditing**.

### Required reading

1. `audit_evidence/P1/round-001/AUDIT_REPORT.md`, `FINDINGS.json`, `SCOPE.json`, `TEST_RESULTS.txt` from GitHub.
2. `docs/ROUND_001_REMEDIATION.md` — developer explanations are hypotheses, not proof.
3. Full updated `p1/` source, tests, Soul contracts, adapter templates and limitations.

### Audit tasks

- Re-run all original project tests and the newly added regression probes in an **isolated local checkout**, without real Codex/OpenCode providers, remote A2A or production access.
- Independently re-check each of 29 Round-001 findings by ID. Classify as `FIXED`, `MITIGATED_FAIL_CLOSED`, `PARTIAL`, `OPEN`, or `NOT_VERIFIED`, explaining exact code and test evidence.
- Pay special attention to Gate 0.2 row tamper and original approval provenance; working-tree/index cleanliness and protected tests; parallel Spec/Quality audit records; A2A verdict handling and distinct host trust; exact final arbitrator/report provenance; Phase 5.85 historical verdict replay; and third-party adapter trust.
- Evaluate whether new protections introduce regressions or new problems, including false blocks from harmless outputs and infinite compliance retries.
- Explicitly verify **integration stays blocked** until genuine provider/test/host attestations exist. A deliberately blocked integration is not a fully implemented solution or evidence of real-agent readiness.
- Confirm no production deployment, main-branch write, remote node mutation or paid provider calls are required.

### Output and GitHub write boundary

Upload **only** the new audit files under:

`experiments/hermes-coding-pipeline-p1/audit_evidence/P1/round-002/`

Required outputs: `AUDIT_REPORT.md`, `FINDINGS.json`, `TEST_RESULTS.txt`, `SCOPE.json`, plus optional `REPRODUCTIONS.md`. Do **not** alter original Round-001 reports, code, tests, Soul or configuration.

Reports must capture the exact audited source SHA, test commands, actual exit codes, any test fixture adaptations, reasons for severity changes, and remaining `NOT_VERIFIED` controls. Do not convert an integration blocker into a PASS by terminology. If interrupted, commit `AUDIT_STATUS: INCOMPLETE` with verified partial evidence rather than guessing.

Final return: audit verdict, remediation source SHA, number of findings fixed vs mitigated/open, GitHub audit report commit SHA and URLs. Stop for developer triage.
