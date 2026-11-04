"""p1_orchestrator — DRAFT Hermes plugin (uninstalled, audit-only).

Remediated after the Stage-2B-1 independent audit:
* bounded capture: subprocess output is pumped with a hard per-stream cap at
  COLLECTION time (S2B1-012), not truncated after an unbounded read;
* p1_init forwards every required CLI flag (S2B1-011);
* p1_approve_spec FAILS CLOSED (supplementary security review): the
  `hermes-unverified:` provenance only records an UNVERIFIED session origin.
  It is NOT a verified human approval identity, and while that binding is
  missing this handler must not be able to trigger a real Gate 0.2 approval.
  The gap "gateway-integrated approval identity binding" stays open and is
  tracked as NOT_VERIFIED for Stage-2B-2.

Hermes remains the only Orchestrator; this surface merely shells the audited
`python -m p1` CLI. Every handler:
* refuses until p1_repo_dir is an explicitly configured absolute path,
* never runs `pip install`, never touches live profiles/gateways.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import threading
from pathlib import Path

TOOLSET = "p1"
_TIMEOUT = 900
_STREAM_CAP_BYTES = 1 * 1024 * 1024  # S2B1-012: bounded at collection time

_COMMANDS = {
    "p1_init": "init",
    "p1_run": "run",
    "p1_status": "status",
    "p1_reconcile": "reconcile",
    "p1_approve_spec": "approve-spec",
    "p1_audit": "audit",
    "p1_export": "export",
}

# CLI `init` requires all of these flags (p1/cli.py); the plugin schema and
# the handler must forward them all (S2B1-011).
_INIT_REQUIRED = ("task_id", "intent", "matrix", "gate01", "souls",
                  "project_root", "worktree")
_INIT_OPTIONAL = ("mode", "fixtures", "adapters", "safety_manifest", "base_ref")


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


def _pump(stream, sink: list, cap: int, state: dict) -> None:
    """Read a subprocess stream in chunks, keeping at most ``cap`` bytes;
    everything beyond the cap is drained and DISCARDED so memory stays
    bounded even for a runaway child (S2B1-012)."""
    kept = 0
    try:
        while True:
            chunk = stream.read(65536)
            if not chunk:
                break
            if kept < cap:
                room = cap - kept
                sink.append(chunk[:room])
                kept += len(chunk[:room])
            if kept >= cap:
                state["truncated"] = True  # keep draining, discard the rest
    finally:
        try:
            stream.close()
        except Exception:
            pass


def _invoke(config: dict, command: str, args: list) -> dict:
    argv = [_python(config), "-B", "-m", "p1", command, *args]
    proc = subprocess.Popen(argv, cwd=str(_repo_dir(config)),
                            stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    out_chunks: list = []
    err_chunks: list = []
    out_state: dict = {}
    err_state: dict = {}
    threads = [
        threading.Thread(target=_pump, args=(proc.stdout, out_chunks,
                                             _STREAM_CAP_BYTES, out_state)),
        threading.Thread(target=_pump, args=(proc.stderr, err_chunks,
                                             _STREAM_CAP_BYTES, err_state)),
    ]
    for thread in threads:
        thread.daemon = True
        thread.start()
    try:
        proc.wait(timeout=_TIMEOUT)
    except subprocess.TimeoutExpired:
        proc.kill()
        proc.wait()
        raise
    for thread in threads:
        thread.join(timeout=10)
    stdout = b"".join(out_chunks).decode("utf-8", errors="replace")
    stderr = b"".join(err_chunks).decode("utf-8", errors="replace")
    payload: dict = {}
    if stdout.strip():
        try:
            payload = json.loads(stdout)
        except ValueError:
            payload = {"stdout": stdout}
    if out_state.get("truncated"):
        payload["_stdout_truncated"] = True
        payload["_stdout_cap_bytes"] = _STREAM_CAP_BYTES
    return {"exit_code": proc.returncode, "result": payload,
            "stderr": stderr[:500],
            "_stderr_truncated": bool(err_state.get("truncated"))}


def _require_home(args: dict) -> list:
    home = args.get("home")
    if not home or not os.path.isabs(str(home)):
        raise ConfigError("home must be an absolute P1 task path")
    return ["--home", str(home)]


def _init_handler(args: dict, config: dict) -> dict:
    """Forward EVERY required init flag (S2B1-011)."""
    argv = _require_home(args)
    for key in _INIT_REQUIRED:
        value = args.get(key)
        if not value or not str(value).strip():
            raise ConfigError(f"p1_init requires {key!r}")
        argv += ["--" + key.replace("_", "-"), str(value)]
    for key in _INIT_OPTIONAL:
        if args.get(key):
            argv += ["--" + key.replace("_", "-"), str(args[key])]
    return _invoke(config, "init", argv)


def handle_approve_spec(args: dict, config: dict) -> dict:
    """Approval provenance records an UNVERIFIED session origin; it is NOT a
    verified approval identity. Until a trusted session-identity binding
    exists (Stage-2B-2 acceptance item), this handler must NOT be able to
    trigger a real Gate 0.2 approval - fail closed (supplementary review)."""
    provenance = args.get("provenance") or {}
    for key in ("platform", "chat_id", "message_ref"):
        if not str(provenance.get(key, "")).strip():
            raise ConfigError(
                f"approval provenance requires non-empty {key!r}; "
                "nickname-only approval is refused")
    handle = str(args.get("actor", "")).strip()
    if not handle:
        raise ConfigError("actor handle required (recorded, not trusted)")
    spec_sha = str(args.get("spec_sha256", ""))
    if len(spec_sha) != 64:
        raise ConfigError("spec_sha256 must be a full sha256 hex")
    approval_id = "hermes-unverified:{}:{}:{}".format(
        provenance["platform"], provenance["chat_id"], provenance["message_ref"])
    # FAIL CLOSED: do not invoke the CLI approval path. The identity behind
    # this provenance has never been verified.
    return {"exit_code": None, "status": "BLOCKED",
            "result": {"approved": False},
            "approval_provenance": dict(provenance, actor_handle=handle,
                                        identity_verified=False),
            "approval_id": approval_id,
            "reason": ("approval identity is UNVERIFIED; triggering Gate 0.2 "
                       "from an unverified session origin is refused "
                       "(fail-closed, Stage-2B-2 must bind verified identity)")}


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


_HANDLERS = {"init": _init_handler, "approve-spec": handle_approve_spec}


def register(ctx) -> None:
    """Register the draft tool surface on a Hermes plugin context.

    Stage-2B-1 DOES NOT call this on any live gateway; it exists so the audit
    can verify the exact future shape (same ctx.register_tool pattern as the
    a2a/google_meet plugins)."""
    for name, command in _COMMANDS.items():
        handler = _HANDLERS.get(command) or _simple_handler(command)
        ctx.register_tool(
            name=name, toolset=TOOLSET, schema=_SCHEMAS[name],
            description=f"P1 {command} (draft; uninstalled)",
            handler=lambda args, _h=handler: _h(args, getattr(ctx, "config", {})))
