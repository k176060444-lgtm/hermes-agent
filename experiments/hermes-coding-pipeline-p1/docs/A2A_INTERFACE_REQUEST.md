# P0 A2A interface contract request (not implementation)

Owner: **separate P0 session**. P1 must NOT refactor or operate A2A on remote Debian hosts.

Requested stable P0 adapter contract (JSON stdin/stdout using trusted local executable or service):

- `submit` with `(task_id, reviewed_commit_sha, approved_matrix_sha, immutable task contract/role data, idempotency_key)` -> `job_id`. Repeated same idempotency key must return the original Job ID rather than create duplicate work.
- `status(job_id)` -> SUBMITTED / RUNNING / WAITING / QUORUM_MET / COMPLETED / FAILED / UNKNOWN, plus diagnosis and progress. Ambiguous/timeout does not mean failed.
- `collect(job_id)` -> raw report bytes with hashes, task/commit/contract bindings, approved actual Harness/model, reviewer identity and independently checked physical host identity.
- `reconcile(job_id|idempotency_key)` -> prove whether work was dispatched and find orphaned jobs after restart, without re-dispatch.
- `cancel(job_id)` -> best-effort cancellation and truthful terminal status, not false claim of termination.

Quorum is **at least two reports from distinct approved physical Debian hosts** among 5bao, 9bao, rusty. Third host may contribute within up to 600 seconds after quorum; P0 decides waiting and stop. P1 must not count one host twice, nor interpret `QUORUM_MET` alone as technical APPROVE. If physical-node attestation/provenance cannot be verified, P1 BLOCKS. The current adapter design contains placeholder checks and MUST undergo security audit against fabricated node fields.

Required P0 confirmations before Stage 2 integration:

1. Exact installed P0 version/adapter API, not hypothetical module names.
2. Which upstream configuration is immutable / signed / independently trustworthy.
3. Trusted mapping between P0 reviewer account/node identity and physical Debian machine.
4. Real report schema and byte-level digest algorithm.
5. Which statuses mean final report (vs 2/3 quorum).
6. Safe idempotent submit semantics and recovery after ambiguous timeout.
7. Whether P0 already emits a normalized JSON envelope; who hosts the wrapper.
8. Location / ownership of original remote evidence (no fake copied report).

P1 intentionally allows offline mocked reports only in `offline_fixture` mode and labels them `SIMULATED`.
