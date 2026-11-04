# p1_orchestrator — DRAFT Hermes plugin (NOT installed)

This directory is an auditable draft only. It has deliberately NOT been
copied into any live Hermes profile (`default`, `ling`, `xiaoshitou`,
`xiaomati`), NOT registered on any gateway, and NOT scheduled.

* Purpose: expose the seven P1 operations (`init/run/status/reconcile/
  approve-spec/audit/export`) as Hermes tools by shelling the audited
  `python -m p1` CLI with fixed argv construction.
* Refusal posture: every handler raises unless `p1_repo_dir` is an explicit
  absolute path containing the P1 package; there is no implicit default.
* Approval provenance: `p1_approve_spec` requires structured
  `provenance{platform, chat_id, message_ref}`. The generated approval id is
  prefixed `hermes-unverified:` and every result carries
  `identity_verified=False`. Turning that into a verified session-identity
  binding is a Stage-2B-2 acceptance item; until then this plugin must not be
  considered an approval trust anchor.
* Installation (future, requires explicit user approval): copy this folder to
  `<profile>/plugins/p1_orchestrator`, restart the gateway via the approved
  procedure, then `p1_status` first, never auto `p1_run`.
