# Stage-2B-1 — Round-2 Targeted Remediation (S2B1-009 + S2B1F-002)

Branch: `fix/p1-stage2b1-remediation2`
Parent commit (independent re-audit report): `c36577b763318822fc251680012e83b6ff6d62d2`
Round-1 remediation commit: `c08e0f9738643edce0d49e39f465ff10cb8aaee4`
Scope: ONLY the remaining re-audit findings. The 15 already-FIXED items, the
state machine, the executor hard gate, historical audits and every other file
are untouched by design.

## S2B1-009 (P2) — trust-promotion path CLOSED, not narrowed

Re-audit evidence: a caller-fabricated `runner_attestation={"attested": true}`
dict upgraded CLI self-reports to `trusted=True`; ordinal pairing ignored
command identity; records carried no task/run binding; duplicate ordinals
silently last-won.

Fix (this round):

* `merge_runner_records()` in BOTH adapters (Codex and OpenCode share one
  implementation) no longer accepts ANY trust-bearing parameter. The
  `runner_attestation` keyword is deleted — submitting it is a `TypeError`.
* Every returned entry is structurally pinned to `trusted=False` and
  `source='cli-event-self-report'` with an explicit `promotion_blocked`
  reason. No dict field (`attested`, `test_seam`, `source`, `signature`, …)
  inside a record can influence trust: records are data, never authority.
* Diagnostic comparison is retained and made instance-strict:
  `command_mismatch` (same ordinal, different command),
  `duplicate_ordinal` (collision is ambiguous, never last-wins),
  `cross_execution_binding` (record task_id/run_id ≠ supplied context),
  `unbound_execution_context` (no context supplied → provably unbound),
  `exit_code_mismatch` (agreement on command but contradiction on exit code),
  `matched_unauthenticated` (everything agrees — still untrusted).
* One record can never serve two invocations: pairing is per-ordinal and the
  unmatched twin is flagged `no_matching_runner_record`.
* The production-grade authenticated-evidence entry point is deliberately NOT
  implemented early: it is a Stage-2B-2 design + acceptance item (real runner
  service, OS-attested launch, per-invocation signed observations). Until it
  exists and passes its own audit, this path stays closed.
* Round-1 tests that ASSERTED the bare-dict upgrade as correct behaviour were
  REVERSED into negative security assertions (see
  `test_s2b1_009_one_record_cannot_serve_two_invocations` and
  `test_s2b1_009_attestation_parameter_deleted`); nothing was deleted to
  obtain green.

## S2B1F-002 (P3) — manifest provenance anchored; four levels kept distinct

Re-audit evidence: a caller-constructed manifest + receipt + capture set is
self-consistent and could set `integrity_verified=True`, while the API took
the manifest as a plain argument, blurring "trusted manifest" with
"well-formed dict".

Fix (this round) — minimal, in-scope anchoring:

* `verify_execution_identity()` and `verify_receipt_integrity()` no longer
  take a `manifest` dict. They take `home` (the orchestrator-protected task
  HOME created at P1 init under `trust.validate_private_task_home`) and read
  `snapshots/runner_manifest.json` from disk via `_read_anchored_manifest()`.
* The anchored manifest must be task-bound (`manifest["task_id"] ==
  request["task_id"]`) and its pinned runner executable is re-measured from
  disk on every call.
* The four conclusions are now machine-separated and named in code:
  * **L1 field structure valid** — `_assert_manifest_current` shape check;
  * **L2 digests mutually consistent** — manifest echo + capture re-hash;
  * **L3 manifest read from protected orchestrator task home** — the anchored
    file read (plus the trust gate that protected the home at init);
  * **L4 runner/agent identity attested by live OS measurement** — ONLY the
    live `verify_execution_identity` path (and only there with `attested=True`
    when no test seam is present).
* `verify_receipt_integrity()` returns explicit `levels` +
  `runner_identity_attested=False` + a note that integrity is NOT identity.
  `manifest_provenance="anchored_task_home"` appears in both verifier results
  so downstream code and reports can never read an unanchored pass as trust.
* Residual boundary (honest): the home anchoring proves the manifest came
  from the orchestrator's own protected task directory, NOT that a real
  runner provisioned it — no runner service exists yet. Stage-2B-2 must add
  the runner-side signature/service liveness proof; that remains
  `NOT_VERIFIED` and is listed below, not pretended complete.

## Changed files (this round)

* `p1/harness/codex.py` — `merge_runner_records()` rewritten (closed path).
* `p1/harness/opencode.py` — re-export updated to the new signature.
* `p1/runner.py` — `_read_anchored_manifest()`, `MANIFEST_NAME`, verifier
  signatures `manifest= → home=`, `task_id` required in manifest, module
  trust-model docstring updated with L1–L4 wording.
* `tests/test_stage2b1_harness.py` — merge tests reversed to negative
  assertions; opencode merge expectations updated.
* `tests/test_stage2b1_runner.py` — fixtures anchor manifests in the home;
  new tests: parameter-deletion, no-home fail-closed, other-task rejection,
  integrity level map assertions.
* `tests/test_stage2b1_remediation.py` — call sites migrated; the two
  round-1 tests that encoded the upgrade path were REVERSED, not removed.
* `tests/test_stage2b1_remediation2.py` — NEW round-2 adversarial suite
  (28 cases): bare/seamed attestation dicts × both adapters, ordinal/command
  cross-matching, duplicate & missing ordinal, cross task/run, one-record-
  two-invocations, unbound context, exit-code conflict, inert source claims,
  manifest-parameter deletion, self-consistent fabrication → L4=False,
  other-task anchored manifest, seam+merge composition yields zero trust.

## Windows regression (21bao)

See TEST_RESULTS recorded in the delivery report: full suite run against this
commit; counts read from JUnit XML, skipped never counted as passed.

## Still NOT_VERIFIED after this round (unchanged boundaries)

* Real runner service, transport and runner-side manifest signature (L3→
  full provenance; Stage-2B-2).
* Dedicated `agentx` Windows identity and production NTFS ACLs; today every
  live experiment runs as the caller `KK` (S2B1-016 FIXED_MECHANISM caveat).
* Real Codex/OpenCode paid execution, event schema and receipts.
* Gateway-integrated approval identity binding (`p1_approve_spec` stays
  fail-closed).
* P0 physical identity, remote nodes, production E: worktree, crash
  recovery.
* executor double hard gate: still closed; zero real dispatch.

No deployment, no accounts, no ACL changes, no plugin install, no service
registration, no gateway modification, no paid model calls were performed in
this round.
