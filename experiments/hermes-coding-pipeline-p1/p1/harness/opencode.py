"""OpenCode CLI adapter (Stage-2B-1). Same trust split as the Codex adapter:
CLI event data is self-report until the Runner records agree.

Role Souls map onto OpenCode *agents*: one declarative agent definition per
role (subagent mode, approved model pinned, permission deny-list). The exact
agent-file schema of the installed CLI must be confirmed live in Stage-2B-2
(NOT_VERIFIED); this module renders the structure and binds digests, and a
format mismatch therefore fails closed at acceptance time, not silently.
"""
from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path
from typing import Any, Iterator

from ..contracts import sha256
from . import HarnessVersionError

ADAPTER_NAME = "opencode"

CAPABILITY_TOKENS = {
    "run_noninteractive": "run opencode with a message",
    "json_format": "--format",
    "agent_flag": "--agent",
    "model_flag": "--model",
    "dir_flag": "--dir",
    "session_continue": "--session",
    "session_export": "export session data as JSON",
    "title_flag": "--title",
    "pure_flag": "--pure",
    "server_attach": "--attach",
}

# Permissions an Agent must never hold for pipeline roles; the renderer emits
# deny entries and Stage-2B-2 verifies the CLI enforces them.
DEFAULT_DENY_PERMISSIONS = ("auto",)


class OpenCodeProbeError(RuntimeError):
    pass


def _text(run_result) -> str:
    return (run_result.stdout or "") + (run_result.stderr or "")


def probe(exe_path: str, *, run=subprocess.run, timeout: int = 20) -> dict:
    if not os.path.isabs(exe_path):
        raise OpenCodeProbeError("opencode executable must be pinned by absolute path")
    version = run([exe_path, "--version"], capture_output=True, text=True,
                  errors="replace", timeout=timeout)
    if version.returncode:
        raise OpenCodeProbeError("opencode --version failed")
    help_main = run([exe_path, "--help"], capture_output=True, text=True,
                    errors="replace", timeout=timeout)
    help_run = run([exe_path, "run", "--help"], capture_output=True, text=True,
                   errors="replace", timeout=timeout)
    combined = _text(version) + _text(help_main) + _text(help_run)
    return {"harness": ADAPTER_NAME,
            "version": _text(version).strip().splitlines()[0][:80],
            "capabilities": detect_capabilities(combined),
            "probe_sha256": sha256(combined.encode("utf-8"))}


def detect_capabilities(help_text: str) -> dict:
    return {name: (token in help_text) for name, token in CAPABILITY_TOKENS.items()}


def require_capabilities(capabilities: dict) -> None:
    missing = sorted(name for name, ok in capabilities.items() if not ok)
    if missing:
        raise HarnessVersionError(
            f"installed opencode lacks capabilities {missing}; re-approval required")


def render_agent_markdown(*, role: str, model: str, soul_text: str,
                          description: str,
                          permissions: dict | None = None) -> str:
    """Deterministic agent definition for one pipeline role.

    Front matter pins the approved model and a permission posture:
    default deny for anything not explicitly allowed by the matrix entry;
    ``auto`` approval is always denied (it would let the CLI self-approve).
    """
    if not role or not model:
        raise OpenCodeProbeError("agent render needs role and approved model")
    perms = dict(permissions or {})
    lines = ["---",
             f"description: {description}",
             "mode: subagent",
             f"model: {model}",
             "hidden: true",
             "permission:"]
    rendered = set()
    for key in sorted(set(perms) | set(DEFAULT_DENY_PERMISSIONS)):
        value = "deny" if key in DEFAULT_DENY_PERMISSIONS and key not in perms else perms.get(key, "ask")
        if value not in ("allow", "ask", "deny"):
            raise OpenCodeProbeError(f"invalid permission value for {key}: {value}")
        lines.append(f"  {key}: {value}")
        rendered.add(key)
    lines += ["---", "", soul_text.rstrip(), ""]
    return "\n".join(lines)


def agent_digest(markdown: str) -> str:
    return sha256(markdown.encode("utf-8"))


def build_command(*, frozen_entry: dict, matrix_entry: dict, request: dict,
                  prompt_text: str, worktree: Path, out_dir: Path) -> dict:
    exe = frozen_entry["exe_path"]
    model = matrix_entry.get("primary_model")
    agent_name = matrix_entry.get("agent_name") or request["role"]
    if not model:
        raise OpenCodeProbeError("matrix entry must approve primary_model")
    extra = matrix_entry.get("extra_argv", [])
    if not isinstance(extra, list) or any(not isinstance(x, str) for x in extra):
        raise OpenCodeProbeError("matrix extra_argv must be a list of strings")
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    argv = [exe, "run", "--format", "json",
            "-m", model,
            "--agent", agent_name,
            "--dir", str(Path(worktree).resolve()),
            "--title", f"p1-{request['task_id']}-r{request['run_id']}",
            prompt_text]
    argv += extra
    stdin_text = ""
    return {"argv": argv, "stdin_text": stdin_text,
            "result_path": str(out_dir / f"{request['run_id']}.events.jsonl"),
            "command_sha256": sha256("\x00".join(argv).encode("utf-8"))}


def export_command(*, frozen_entry: dict, session_id: str) -> list:
    if not session_id:
        raise OpenCodeProbeError("session id required for export")
    return [frozen_entry["exe_path"], "export", session_id]


def parse_events(raw_text: str) -> Iterator[dict]:
    for line in raw_text.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            event = json.loads(line)
        except ValueError:
            yield {"kind": "unparseable", "raw_sha256": sha256(line.encode("utf-8"))}
            continue
        if isinstance(event, dict):
            yield normalize_event(event)
        else:
            yield {"kind": "unknown", "value_type": type(event).__name__}


def normalize_event(event: dict) -> dict:
    etype = event.get("type") or (event.get("part") or {}).get("type") or "unknown"
    base = {"kind": str(etype), "raw": event}
    for key in ("sessionID", "session_id"):
        if event.get(key):
            base["session_ref"] = str(event[key])
            break
    return base


def extract_session_ref(events: list) -> dict:
    session_id = None
    for event in events:
        if event.get("session_ref"):
            session_id = event["session_ref"]
            break
    return {"session_id": session_id, "export_required_for_final_evidence": True}


def extract_command_evidence(events: list) -> list:
    records = []
    for event in events:
        raw = event.get("raw") or {}
        part = raw.get("part") or {}
        tool = raw.get("tool") or part.get("tool")
        state = part.get("state") or {}
        command = None
        for holder in (raw, part, state):
            if isinstance(holder, dict):
                input_data = holder.get("input") if isinstance(holder.get("input"), dict) else {}
                command = holder.get("command") or input_data.get("command")
                if command:
                    break
        if tool in ("bash", "shell") or command:
            records.append({
                "command": command if isinstance(command, str) else str(command),
                "claimed_exit": state.get("exit") if isinstance(state, dict) else None,
                "source": "cli-event-self-report",
                "trusted": False,
            })
    return records


def merge_runner_records(claimed: list, runner_records: list) -> list:
    by_command: dict[str, dict] = {}
    for record in runner_records or []:
        if isinstance(record, dict) and isinstance(record.get("command"), str):
            by_command[record["command"]] = record
    merged = []
    for item in claimed:
        entry = dict(item)
        match = by_command.get(item["command"])
        if match is not None and match.get("exit_code") == item.get("claimed_exit"):
            entry["trusted"] = True
            entry["source"] = "runner-observed-agreement"
        elif match is not None:
            entry["contradiction"] = True
        merged.append(entry)
    return merged
