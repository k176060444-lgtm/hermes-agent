# P1 Round-006 audit → Round-007 remediation candidate

**Audited source:** `a69d04084c72dae437fc79f1fb9eaed8152d1644`  
**Auditor report commit:** `6d301638043f61c68e3f76aeafa94b01b30229ba`  
**Auditor result:** `COMPLETE / CONDITIONAL`.  
**Status of this document:** developer remediation proposal awaiting Qwen-Flash independent Round-007 audit; **not** acceptance of 21bao real execution.

## Triage

| Finding | Developer disposition | Boundary / evidence |
|---|---|---|
| R6-001 (P2), Windows WAL/SHM lifecycle | **Candidate FIXED, pending real Windows verification** | Only the top-level task home is required to have a protected NTFS DACL. Every enumerated database, WAL, SHM and evidence subdirectory still must be owned by the current trusted SID and may grant Allow only to current SID, SYSTEM and Administrators. SQLite-created child objects with safe inherited ACEs are accepted. Unexpected Allow principals or owner mismatches remain blocking. No automatic ACL rewrites. |
| R6-002 (P3), per-evidence-file ACL enumeration | **Documented, NOT_FIXED / optional strengthening** | Existing directory ACL checks, owner-only protected task root and registered content digests remain. This revision does not recursively enumerate all files; directory traversal and privilege boundary remain required. Revisit if threat model expands. |
| R5-005 / R4-001, distinct agent identity | **MITIGATED_FAIL_CLOSED** | No independent SID-attested runner has been installed. Agent subprocess launch in real integration remains forbidden. A private task directory does not exclude malicious code executing under the orchestrator's own SID. |
| R2-006, real A2A transport/physical node attestations | **MITIGATED_FAIL_CLOSED** | External P0 integration has not been authenticated; no remote nodes were exercised. |

## Code change (minimal)

- `p1/trust.py::_windows_validate` checks the first requested path (trusted task root) for `AreAccessRulesProtected=True`. Child objects **do not** have to disable inherited permissions, but remain bound to owner and allowed effective principals via `GetAccessRules($true,$true)`. The ACL-response path/order is checked to guard against mixing records.
- No privileged ACL-modifying script is introduced. Existing PowerShell ACL query remains **read-only**.
- `tests/test_remediation_round6.py`: five platform-independent ACL-result tests and one **Windows-only real SQLite WAL lifecycle** test. The latter only protects a disposable pytest temp root, creates a real WAL database, closes/reopens it, and verifies that an additional Everyone Allow ACE on the WAL is rejected. It must be run and audited on 21bao Windows; Linux cannot certify it.

## Local validation by developer

- Platform: isolated Linux execution only; no live Hermes/21bao config, no paid provider, no P0, no production resources.
- `python -m pytest -q --disable-warnings --maxfail=1`: **112 passed, 2 skipped** (Windows-specific DACL tests skipped on Linux).
- Python compilation: see final commit validation record.
- No claim of 21bao NTFS lifecycle success. Qwen-Flash should independently reproduce both the **natural SQLite -wal/-shm creation** and a **clean close → recreate** cycle; test failure is a real blocker.

## Real integration release blockers (unchanged)

Real mode stays permanently blocked by the existing independent executor gate until a **different-SID audited agent runner**, native Codex/OpenCode and model identity receipts, test execution receipts, Gate approvals, external P0 role/host/wire attestations, Windows E: worktree/child-process cleanup and task-specific side-effect guard are all implemented and independently accepted. This code does **not** enable the live path or Phase 6/7.
