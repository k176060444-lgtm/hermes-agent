# Hermes Coding Pipeline P1 — candidate implementation

**Status: Round-003 FAIL remediation candidate for independent Round-004 audit; offline tests only. Strict real integration hard-blocked; not approved for 21bao use, live calls or deployment.**

P1 receives two outputs from Hermes Gate 0.1: (1) approved user intent and goals, and (2) approved 12-role Harness/model/node matrix. It programmatically controls Phase 0.2 through Gate 5.9. Hermes remains the human-facing Orchestrator; P1 is its deterministic execution kernel. P2 intent/matrix conversation automation and Phase 6/7 deployment/cleanup are explicitly excluded.

## Workflow

```
Gate 0.1 approved inputs
  -> Phase 0.2 Planner candidate TASK_SPEC
  -> HUMAN Gate 0.2 (freeze exact SHA)
  -> 1 worktree -> 2 Worker TDD
  -> [3 Spec Reviewer || 4 Quality Reviewer] (SAME COMMIT, independent reports/audits)
  -> 4.5 Tester Gate A -> Gate A (local loop max 5 rounds, inclusive)
  -> 5.0 external P0 A2A (at least 2 DISTINCT physical nodes)
  -> 5.1 remediation -> 5.2 Tester B -> 5.3 Arbitrator
  -> Gate B (remediation loop max 5 rounds, inclusive)
  -> 5.85 final compliance aggregate
  -> HUMAN Gate 5.9 WAITING ONLY (NO DEPLOYMENT)
```

Each phase exit has lightweight compliance checks: approved inputs/Soul, role/phase/result evidence and source fingerprints. Audit checks process and deliverables, **not technical correctness or style**. A substantive noncompliance requiring a rerun consumes one of **2 global compliance retraces**. Evidence uncertainty blocks for reconciliation rather than fabricating success. `APPROVE_WITH_COMMENTS` may pass review; `QUESTION` and `NEEDS_SPECIALIST` pause for clarification.

## Explicit boundaries

- Only `21bao` (Windows) is expected for local roles. `5bao`, `9bao`, `rusty` (Debian) are remote A2A candidates. Names and Harness/models live in `config/role_matrix.template.json`, not embedded in the role dispatcher. The P0 adapter, not P1, selects and runs remote agents.
- `souls/*.md` are canonical, source-controlled role instruction contracts. Installing them as **native Codex and OpenCode agent configurations** is **P1 Stage 2 in a new session**, not done here. Soul instructions alone do not physically prevent writes; P1 uses before/after inventory plus role-audit rules. A write-then-restore operation is not detectable from final SHA alone.
- The template matrix deliberately contains `null` models and will be rejected until filled with genuinely approved model identifiers. Harness bindings in the template are **candidate defaults**, not immutable roles hardcoded in Python.
- The code can run disposable Git worktrees in offline mode. **All `integration` execution currently fails closed at the workflow entry**, before launching any role, because trusted model execution, genuine test receipts and physical-node attestation are not available. This is a deliberately unimplemented Stage 2 contract, **not a successful live adapter**. Native Windows `E:` worktree, safety manifest and live side-effect guards remain NOT_VERIFIED.
- A trusted, independently auditable Codex/OpenCode execution protocol and a trusted P0 adapter must be supplied and tested before the real-integration hard lock can be removed, and any such removal needs a new independent audit. The sample adapter file has disabled authorizations; it is not a working system integration.
- No `deploy`, `merge`, `push`, `production reload`, `cleanup production` or `Gate 5.9 approve-and-release` command is provided.

## Layout

- `p1/contracts.py` — validation, approved input snapshots, Soul hashes
- `p1/state.py` — SQLite task state, hash-chained events, invocation journal, process lock
- `p1/workflow.py` — exact stages, approval gates, parallel review fan-out/join, 5/5/2 loops, Gate 5.9 stop
- `p1/executor.py` — fixture-mode and configurable non-shell real wrapper subprocess boundary
- `p1/a2a.py` — external P0 only; no direct node dispatch, with quorum and provenance checks
- `p1/audit.py` — non-technical compliance checks
- `p1/gitops.py` — Git snapshot/diff and worktree creation
- `souls/` — 12 versioned role responsibilities, boundaries and output expectations
- `config/` — defaults/templates; **never add secrets**
- `tests/` — offline tests, fake agents, local temporary Git repos, no paid provider calls; Round-001 regression probes in `tests/test_remediation_round1.py`
- `prompts/AGENT_AUDIT_PROMPT.md` — external agent's mandatory read-only coding audit prompt
- `prompts/STAGE2_NEW_SESSION_PROMPT.md` — handoff for separate real-config session
- `audit_evidence/P1/` — standardized audit drop path on GitHub branch

## Test locally (no Codex/OpenCode required)

```bash
python -m pytest -q
python -m compileall -q p1
python -m p1 --help
```

To construct a personal disposable task, provide a clean Git repo and a separate worktree path, plus:

1. `intent.md` containing already-approved intent;
2. `matrix.json` with all twelve roles, actual model strings, and approved `21bao`/blind nodes;
3. `gate01.json` with a human approval ID and SHA256 digests **of the exact input file bytes**;
4. directory of twelve Soul markdown files;
5. mock fixture result JSONs for each stage (only for `offline_fixture`).

```bash
python -m p1 init --home ./local-state --task-id TASK-001 \
  --intent ./intent.md --matrix ./matrix.json --gate01 ./gate01.json \
  --souls ./souls --project-root /tmp/disposable-git-repo \
  --worktree /tmp/disposable-worktrees/wt-TASK-001 \
  --mode offline_fixture --fixtures ./fixtures
python -m p1 run --home ./local-state
# status = WAITING_APPROVAL at Gate 0.2
python -m p1 status --home ./local-state
# Human compares TASK_SPEC and explicitly approves the printed SHA:
python -m p1 approve-spec --home ./local-state --actor USER \
  --approval-id HUMAN-APPROVAL-ID --spec-sha256 64_HEX_BYTES
python -m p1 run --home ./local-state
python -m p1 audit --home ./local-state
python -m p1 export --home ./local-state
```

**Warning:** Offline `WAITING_GATE_5_9` is only a flow simulation, never a real production authorization. The generated case file prominently says `SIMULATION ONLY`.

## Audit, remediation and GitHub handoff

External audit agents must review **the exact P1 Git commit**, then upload reports to `audit_evidence/P1/round-001/`, `round-002/`, etc. Each round is append-only. Do not mutate code during the audit step, and do not edit existing audit reports. Provide commit SHA, tested environment, commands, exit statuses, reproducible file:line findings and whether evidence is real or mock. The developer then triages, fixes only justified findings, runs tests, commits changes, and requests a new independent audit round. See `prompts/AGENT_AUDIT_PROMPT.md`.

## Important unverified / unfinished edges

See [`docs/ROUND_001_REMEDIATION.md`](docs/ROUND_001_REMEDIATION.md) for the complete 29-finding disposition and [`docs/KNOWN_LIMITATIONS.md`](docs/KNOWN_LIMITATIONS.md) for remaining blockers. Key blockers before real execution: trust of external job reports/physical identity; verified Codex/OpenCode wrapper outputs and role permissions on 21bao; real Magpie provenance; live-safe side-effect Kill guard; independent human-approval provenance; managed Git evidence commits and recovery after ambiguous external invocations. Passing mocks does not waive these blockers.

### Round-002 FAIL remediation candidate

The latest changes respond to Round-002 audit report `541c25a` (which audited `7ef210a`). See `docs/ROUND_002_REMEDIATION.md` and `prompts/ROUND003_AUDIT_PROMPT.md` for the exact verification boundary. Approval file now must bind all 12 Role Soul hashes (`souls_sha256`). Real integration remains **NOT_VERIFIED and disabled**; successful offline fixtures cannot authorize 21bao live calls or production release.
