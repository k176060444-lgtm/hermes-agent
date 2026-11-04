"""p1_orchestrator — DRAFT Hermes plugin (uninstalled, audit-only).

Hermes remains the only Orchestrator; this surface merely shells the audited
`python -m p1` CLI. Every handler:
* refuses until p1_repo_dir is an explicitly configured absolute path,
* never runs `pip install`, never touches live profiles/gateways,
* enforces structured approval provenance for approve-spec: a bare nickname
  string is NOT an approval credential. Message-level identity verification
  remains an open Stage-2 item; provenance is recorded as
  `hermes-unverified:{platform}:{chat_id}:{message_ref}` so ledgers always
  show the trust state.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

TOOLSET = "p1"
_TIMEOUT = 900

_COMMANDS = {
    "p1_init": "init",
    "p1_run": "run",
    "p1_status": "status",
    "p1_reconcile": "reconcile",
    "p1_approve_spec": "approve-spec",
    "p1_audit": "audit",
    "p1_export": "export",
}


class ConfigError(RuntimeError):
    pass


def _repo_dir(config: dict) -> Path:
    raw = (config or {}).get("p1_repo_dir") or ""
    if not raw or not os.path.isabs(raw):
        raise ConfigError("p1_repo_dir must be an explicit absolute path")
    path = Path(raw)
    if not (path / "p1" / "cli.py").is_file():
        raise ConfigError("p1_repo_dir does not contain the P1 package")
    return path


def _python(config: dict) -> str:
    raw = (config or {}).get("python_executable") or sys.executable
    if not os.path.isabs(raw):
        raise ConfigError("python_executable must be absolute")
    return raw


def _invoke(config: dict, command: str, args: list) -> dict:
    argv = [_python(config), "-B", "-m", "p1", command, *args]
    result = subprocess.run(argv, cwd=str(_repo_dir(config)), capture_output=True,
                            text=True, errors="replace", timeout=_TIMEOUT)
    payload: dict = {}
    if result.stdout.strip():
        try:
            payload = json.loads(result.stdout)
        except ValueError:
            payload = {"stdout": result.stdout}
    return {"exit_code": result.returncode, "result": payload,
            "stderr": result.stderr.strip()[:500]}


def _require_home(args: dict) -> list:
    home = args.get("home")
    if not home or not os.path.isabs(str(home)):
        raise ConfigError("home must be an absolute P1 task path")
    return ["--home", str(home)]


def handle_approve_spec(args: dict, config: dict) -> dict:
    provenance = args.get("provenance") or {}
    for key in ("platform", "chat_id", "message_ref"):
        if not str(provenance.get(key, "")).strip():
            raise ConfigError(
                f"approval provenance requires non-empty {key!r}; "
                "nickname-only approval is refused")
    handle = str(args.get("actor", "")).strip()
    if not handle:
        raise ConfigError("actor handle required (recorded, not trusted)")
    approval_id = "hermes-unverified:{}:{}:{}".format(
        provenance["platform"], provenance["chat_id"], provenance["message_ref"])
    spec_sha = str(args.get("spec_sha256", ""))
    if len(spec_sha) != 64:
        raise ConfigError("spec_sha256 must be a full sha256 hex")
    argv = _require_home(args) + ["--actor", handle, "--approval-id", approval_id,
                                  "--spec-sha256", spec_sha]
    out = _invoke(config, "approve-spec", argv)
    out["approval_provenance"] = dict(provenance, actor_handle=handle,
                                      identity_verified=False)
    return out


_SCHEMAS = {
    "p1_init": {"type": "object", "properties": {
        "home": {"type": "string"}, "task_id": {"type": "string"},
        "intent": {"type": "string"}, "matrix": {"type": "string"},
        "gate01": {"type": "string"}, "souls": {"type": "string"},
        "project_root": {"type": "string"}, "worktree": {"type": "string"},
        "mode": {"type": "string", "enum": ["offline_fixture", "integration"]},
        "fixtures": {"type": "string"}, "adapters": {"type": "string"},
        "safety_manifest": {"type": "string"}, "base_ref": {"type": "string"}},
        "required": ["home", "task_id", "intent", "matrix", "gate01", "souls",
                      "project_root", "worktree"]},
    "p1_run": {"type": "object", "properties": {
        "home": {"type": "string"}, "max_steps": {"type": "integer"}},
        "required": ["home"]},
    "p1_status": {"type": "object", "properties": {"home": {"type": "string"}},
                  "required": ["home"]},
    "p1_reconcile": {"type": "object", "properties": {"home": {"type": "string"}},
                     "required": ["home"]},
    "p1_approve_spec": {"type": "object", "properties": {
        "home": {"type": "string"}, "actor": {"type": "string"},
        "spec_sha256": {"type": "string"},
        "provenance": {"type": "object",
                        "properties": {"platform": {"type": "string"},
                                       "chat_id": {"type": "string"},
                                       "message_ref": {"type": "string"}}}},
        "required": ["home", "actor", "spec_sha256", "provenance"]},
    "p1_audit": {"type": "object", "properties": {"home": {"type": "string"}},
                 "required": ["home"]},
    "p1_export": {"type": "object", "properties": {"home": {"type": "string"}},
                  "required": ["home"]},
}


def _simple_handler(command: str):
    def handler(args: dict, config: dict) -> dict:
        argv = _require_home(args)
        if command == "run" and args.get("max_steps"):
            argv += ["--max-steps", str(int(args["max_steps"]))]
        return _invoke(config, command, argv)
    return handler


def register(ctx) -> None:
    """Register the draft tool surface on a Hermes plugin context.

    Stage-2B-1 DOES NOT call this on any live gateway; it exists so the audit
    can verify the exact future shape (same ctx.register_tool pattern as the
    a2a/google_meet plugins)."""
    for name, command in _COMMANDS.items():
        if command == "approve-spec":
            handler = handle_approve_spec
        else:
            handler = _simple_handler(command)
        ctx.register_tool(
            name=name, toolset=TOOLSET, schema=_SCHEMAS[name],
            description=f"P1 {command} (draft; uninstalled)",
            handler=lambda args, _h=handler: _h(args, getattr(ctx, "config", {})))
