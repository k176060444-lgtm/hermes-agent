# P1 Round-004 findings → Round-005 remediation candidate

Source audit: `audit_evidence/P1/round-004/` at GitHub commit
`715664e02cf25c31f15bad998174a7e91c130425`; audited code
`888470d661085ee7a183184a74bf3b5a6cf6f556`.

**Scope: offline development only.** Do not deploy to 21bao or enable real model/P0 calls.

| Finding | Candidate disposition | Code and verification |
|---|---|---|
| R4-001 (P1) | **OS-trust-boundary enforcement for live mode; real Windows validation NOT_VERIFIED** | New `p1/trust.py` requires the task home and SQLite DB be private, owned by the trusted P1 process identity. POSIX owner/permissions enforced; Windows NTFS owner and non-inherited SID ACLs inspected with read-only PowerShell. `Pipeline.status()`, `run()`, `resume()`, `approve_spec()` and `verify_evidence()` check before accepting state/dispatch. A failed check is effective BLOCKED / NOT_VERIFIED and does not re-seal suspicious rows. Unit tests `test_r4_001_*` validate POSIX behavior only. |
| R4-002 (P3) | Candidate FIXED | `p1/gitops.py` now reads `git diff --name-status -z`, parses bytes, and uses `ls-tree -z` for exact path + blob/mode checks. Chinese filenames and names with tabs pass test-only additive checks. |
| R4-003 (P3) | Candidate FIXED | `status()` returns effective `NEEDS_RECONCILIATION` for any unresolved run, preserving `persisted_status` and listing the run IDs. `run()` and `resume()` do not silently ignore the orphan. Existing legacy unit test updated to require the stricter observable state. |
| R2-008 (P3) | Candidate FIXED for direct-child output memory bounds | A concurrent dual-pipe reader caps stdout/stderr at 8 MiB each. On overflow, the direct child is killed and results are rejected; output cap, bytes observed, truncated flags and exit status recorded in `logs/<run_id>.capture.json`. On timeout, bounded partial logs and timeout metadata are recorded. The Windows subprocess *descendant tree* kill guarantee remains NOT_VERIFIED. |
| R2-006 (P2) | **Still MITIGATED_FAIL_CLOSED** | External A2A original wire receipts, physical identity proof and fully authenticated binding are not implemented; all real integration paths remain disabled. |

## R4-001 trust boundary: actual scope, not a security claim beyond the facts

The selected audit-approved option is **single trusted operating-system identity
owns the entire P1 state home**. Live operation must be provisioned with a
**dedicated P1 service account** and task home accessible **only** by that
identity, the OS SYSTEM identity and necessary administrators. On Windows,
**disable ACL inheritance** for the home *and* `state.sqlite`, and remove grants
to `Users`, `Authenticated Users`, `Everyone` and unrelated principals.
On POSIX use 0700 for the home, 0600 for the database, with correct owner.

**Review/Worker/Tester subprocesses MUST NOT be executed under the same OS
security identity if they can access the P1 state home**, because a process with
all the orchestrator's identity privileges can invoke `Store._event` and fabricate
hash-chain-consistent approvals and runs. The OS-based option is **not** a
cryptographic trust anchor and cannot defend against a compromised trusted
service account, administrator, or fully privileged local process. External
HMAC/WORM attestation is an alternative future strengthening, not yet present.

Windows ACL checks have NOT been executed on 21bao; the runtime will refuse
live progress when checks fail or PowerShell cannot provide reliable DACL data.
The current version also separately refuses all real integrated invocations
until trusted model, test execution, P0 and human approval receipts are wired
and independently audited. Under a single same-user Hermes/Agent process model,
R4-001 is **not fully mitigated**: a separate process identity/isolated runner
must be established at Stage 2, or an external HMAC/WORM anchor implemented.

## Test accounting

On the isolated Linux test host, **101/101** offline tests pass, with one
pre-existing test's expectation legitimately updated to reflect R4-003. The
new cap path was exercised with a local stub process; it was not a real model.
No real 21bao/Hermes/Codex/OpenCode/P0 or paid execution was invoked.
