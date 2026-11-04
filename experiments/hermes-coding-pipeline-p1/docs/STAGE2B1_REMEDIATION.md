# Stage-2B-1 Remediation Report — 16/16 findings addressed (FAIL -> fixed pending re-audit)

Branch: `fix/p1-stage2b1-remediation` (fork of audit-report commit
`47f7e18b0025bb6b271de6bf234f14c6741984a1`; full dev + audit history preserved;
no historical audit report touched). Remediation scope ONLY: no Stage-2B-2
deployment, no accounts, no ACLs, no gateway changes, no paid calls.

## P1 (3/3)

| ID | Finding (audit) | Remediation | Tests |
|---|---|---|---|
| S2B1-001 | Agent SID not manifest-bound; verify enforced nothing | `verify_execution_identity(receipt, request, manifest, ...)` now (a) calls `validate_launch_request` + `validate_receipt` first, (b) takes `expected_agent_sid` ONLY from the `manifest` argument and cross-checks receipt SID against it, (c) re-measures the manifest's pinned runner exe from disk (`_assert_manifest_current`). `expected_agent_sid` is no longer read from the request anywhere. Self-hash boundary (`request_sha256` is tamper-evidence, NOT a signature) is documented in the module trust model. | `test_identity_without_valid_request_is_refused`, `test_identity_receipt_binding_enforced`, `test_identity_manifest_runner_exe_pinned`, `test_s2b1_001_*` |
| S2B1-002 | `process_alive` seam fused liveness with identity; receipt path used as image | Split into `process_identity(pid)` = one OS measurement of liveness + creation time + token SID/groups + image path (all ctypes, all fail-closed). The only injection point is `identity_probe=`, and when present the result is FORCED to `attested=False` + `test_seam=True` regardless of checks passing. The image ALWAYS comes from the measured process; the receipt self-reported path is never digested. | `test_s2b1_002_test_seam_never_attested`, `test_s2b1_002_receipt_path_never_used_as_image`, `test_test_seam_never_attests`, `test_windows_process_identity_self` (live) |
| S2B1-010 | `render_agent_markdown(permissions={"auto":"allow"})` emitted `auto: allow` | Any non-`deny` value for a `DEFAULT_DENY_PERMISSIONS` key now raises `OpenCodeProbeError`; `auto` is emitted as `deny` unconditionally. Docstring states the rendered markdown declares intent only — actual CLI enforcement is Stage-2B-2 live verification (NOT_VERIFIED). | `test_agent_render_refuses_auto_allow`, `test_agent_render_forces_auto_deny`, `test_s2b1_010_*` |

## P2 (8/8)

| ID | Remediation | Tests |
|---|---|---|
| S2B1-003 | Receipt gains `process_start_time`; live verify binds the measured `GetProcessTimes` creation time to the receipt (PID reuse blocked); dead PID in live mode raises "identity cannot be attested post-exit". New `verify_receipt_integrity` handles post-exit: structure + full binding + manifest echo + capture re-hash from orchestrator-owned `capture_dir` (absent dir => fail closed), always `attested=False`. | `test_s2b1_003_dead_pid_rejected` (live), `test_s2b1_003_start_time_binding_blocks_reuse`, `test_s2b1_003_post_exit_is_integrity_only`, `test_windows_process_identity_self`, `test_receipt_integrity_*` |
| S2B1-004 | Receipt schema now REQUIRES and cross-binds `stage/role/harness/model/reviewed_commit/command_sha256/harness_version`; request gains `command_sha256` (approved argv digest from `build_command`) + `frozen_harness_version`; `validate_receipt` refuses any echo mismatch. | `test_receipt_cross_binding_rejected` (7 params), `test_receipt_version_drift_rejected`, `test_s2b1_004_*` |
| S2B1-005 | `poll()` validates the outbox receipt (structure + full binding + manifest digest echo) BEFORE returning; failures return `state=RECEIPT_UNVERIFIED, validated=False, reconciliation_required=True` and can never be final evidence. | `test_client_poll_rejects_junk_receipt`, `test_client_poll_accepts_bound_receipt`, `test_s2b1_005_*` |
| S2B1-006 | `runner_health` never returns `available=True`: it reports `manifest_provisioned` + `available=False` + `service_liveness="unknown"` with an explicit "runner service is NOT deployed" reason. `launch` refuses correspondingly. | `test_client_health_reports_service_not_deployed`, `test_s2b1_006_*` |
| S2B1-007 | `verify_ledger_inaccessible` enumerates root + `state.sqlite`/`-wal`/`-shm` (when present) + `logs/snapshots/artifacts/audit_evidence` dirs in ONE batched PowerShell ACL query; any exposure on ANY checked path blocks; query failures raise. Docstring: coverage is limited to enumerated paths, not a proof for arbitrary future children; real ACCESS_DENIED proof under agentx stays Stage-2B-2 (NOT_VERIFIED). | `test_ledger_check_blocks_exposed_dacl` (child-only leak), `test_s2b1_007_child_ace_blocks`, `test_s2b1_007_live_child_everyone_grant_blocks` (live icacls) |
| S2B1-008 | Strict allowlist `EXTRA_ARGV_ALLOWLIST` (`codex: {"--ephemeral"}`, `opencode: {"--pure"}`) via shared `check_extra_argv`: non-allowlisted flags, value-carrying tokens, positional args and ALL reserved overrides (`-m/--model`, `-s/--sandbox`, `-C/--cd`, `--json`, `--config`, bypass switches) are rejected. The stray `item.format()` interpolation on extra_argv is gone. | `test_extra_argv_overrides_are_rejected` (7 params), `test_opencode_argv_rejects_override_flags`, `test_s2b1_008_*` (14 combined) |
| S2B1-009 | `merge_runner_records` requires `runner_attestation` from the LIVE verify path (`attested=True`, `test_seam` rejected); without it every record stays `trusted=False` with `promotion_blocked` reason. Pairing is per-invocation ordinal; each record is consumed once (`no_matching_runner_record` on the unpaired twin). With no real runner in this stage, everything remains untrusted by construction. | `test_merge_requires_authenticated_runner_attestation`, `test_merge_pairs_per_invocation_with_attestation`, `test_s2b1_009_*` (4) |
| S2B1-016 | New `winjobs.create_suspended_in_job`: `CreateProcessW(CREATE_SUSPENDED)` -> `AssignProcessToJobObject` -> `ResumeThread`, with terminate-and-raise on any failure. The escape window (children born between spawn and assign) is structurally closed because the child cannot fork while suspended. The agentx-identity launch path (CreateProcessWithLogonW) stays explicitly unimplemented. | `test_s2b1_016_suspended_spawn_closes_escape_window` (live), `test_s2b1_016_assign_failure_kills_suspended_child` (live) |

## P3 (5/5)

| ID | Remediation | Tests |
|---|---|---|
| S2B1-011 | Dedicated `_init_handler` forwards `--task-id/--intent/--matrix/--gate01/--souls/--project-root/--worktree` (+ optional mode/fixtures/adapters/safety-manifest/base-ref); missing required args raise `ConfigError`. | `test_init_handler_forwards_all_required_flags`, `test_init_handler_requires_every_required_flag`, `test_s2b1_011_init_forwards_all_flags` |
| S2B1-012 | `_invoke` now pumps stdout/stderr through `_pump` with a hard 1 MiB per-stream cap at COLLECTION time (beyond-cap bytes are drained and discarded); truncation flags surface in the result. | `test_invoke_caps_streams_at_collection_time`, `test_s2b1_012_invoke_bounded` |
| S2B1-013 | Command-less bash events render `{"command": None, "no_command": True}` and are unbindable in merge (never the literal "None"). | `test_opencode_bash_event_without_command_is_unbindable`, `test_s2b1_013_no_literal_none_command` |
| S2B1-014 | `opencode.build_command` validates `request["role"]` first and raises `OpenCodeProbeError` (no bare KeyError). | `test_opencode_missing_role_is_controlled_error`, `test_s2b1_014_missing_role_controlled` |
| S2B1-015 | `validate_receipt` enforces status/exit semantics: COMPLETED=>0, FAILED=>nonzero int, TIMEOUT=>None, KILLED=>None; plus timestamp sanity (finished>=started). | `test_receipt_status_exit_semantics` (4 params), `test_s2b1_015_*` (4 params) |

## Supplementary security review (approve-spec)

`p1_approve_spec` previously DID invoke the CLI approval path with only a
`hermes-unverified:` provenance pointer — i.e. it could trigger Gate 0.2 from
an unverified session origin. Now the handler FAILS CLOSED: provenance is
validated and recorded, `approval_id` keeps the `hermes-unverified:` prefix,
`identity_verified=False` is asserted, and the CLI approval path is NEVER
invoked (`status="BLOCKED"`). The gap "gateway-integrated approval identity
binding" is logged as a NOT_VERIFIED Stage-2B-2 acceptance item.
Tests: `test_approve_fails_closed_on_unverified_identity`, `test_approve_gate_blocks_unverified_identity`.

## Test-contract changes (old tests updated, none skipped-as-green)

1. `build_launch_request` gained required `command_sha256` — all request
   builders updated (old 4-arg calls would fail closed anyway).
2. Receipt schema gained 8 required fields; all receipt fixtures updated.
3. `verify_execution_identity` signature changed (manifest is now a required
   argument; `process_alive` seam replaced by `identity_probe` that can never
   attest) — all identity tests rewritten against the new contract, same
   security assertions preserved (same-SID refusal, Administrators refusal,
   divergence refusal, drift refusal).
4. `runner_health`/`poll` response shapes changed — client tests assert the
   honest shapes.
5. `verify_ledger_inaccessible` query seam changed shape (paths -> records);
   the two ledger tests were rewritten and EXTENDED (child-leak case added).
6. `merge_runner_records` gained the attestation gate — upgrade tests now
   supply a live attestation AND verify the negative (forged/seam lists).
7. `render_agent_markdown` now rejects auto:allow — the old reproduce-case
   test became the refusal test; `auto: deny` default case kept.
8. Plugin tests moved from `subprocess.run` stubs to `Popen` stubs (new
   bounded-capture implementation); approve-spec test asserts BLOCKED.

## Model configuration boundary (unchanged, per user decision)

Hermes remains the sole model-configuration source; P1 consumes only the
approved 12-role matrix; adapters pass/freeze matrix model IDs; no model
catalog/resolver added; no hardcoded model names introduced (argv builders
take matrix values only).

## Test statistics (21bao Windows, Python 3.11.15)

See TEST_RESULTS in the delivery message: pre-remediation baseline
166/161/5/0/0; post-remediation full suite run recorded from JUnit XML in the
same environment (exact counts in the completion report). All real
integration gates remain zero-dispatch (`TRUSTED_INTEGRATION_EXECUTION_VERIFIED=False`,
executor raises intact — asserted by `test_executor_gate_still_closed`).

## Still MITIGATED_FAIL_CLOSED / NOT_VERIFIED (unchanged by design)

- R5-005 separate-identity executor: MITIGATED_FAIL_CLOSED (no agentx account).
- R2-006 P0 A2A transport + physical identity: MITIGATED_FAIL_CLOSED.
- Runner service/transport/agentx provisioning: NOT_VERIFIED (Stage-2B-2).
- OpenCode permission-field CLI enforcement: NOT_VERIFIED (needs real CLI).
- Real Codex/OpenCode event schemas vs installed CLIs: NOT_VERIFIED.
- Gateway-integrated approval identity binding: NOT_VERIFIED (approve-spec now
  fails closed until then).
- Production E: worktrees, gateway restart end-to-end: NOT_VERIFIED.
- Ledger child-coverage: bounded enumeration now; full ACCESS_DENIED proof
  under a real agent identity: Stage-2B-2.
