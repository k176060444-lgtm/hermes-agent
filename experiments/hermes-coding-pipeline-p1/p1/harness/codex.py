"""Codex CLI adapter (Stage-2B-1): probing, frozen capabilities, argv build,
synthetic-safe event parsing. No model/provider name is hard-coded; every
runtime choice comes from the approved matrix entry and the frozen snapshot.

IMPORTANT trust split:
* ``extract_command_evidence`` reports what the CLI *event stream claims*.
  These records carry ``trusted=False`` by construction.
* Exit codes become trusted only when the Runner receipt's recorded process
  observation matches (``merge_runner_records``). Without a Runner receipt the
  data stays self-reported and cannot satisfy a test-execution requirement.
"""
from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path
from typing import Any, Iterator

from ..contracts import sha256
from . import HarnessVersionError

ADAPTER_NAME = "codex"

# capability token -> literal this CLI version must echo when asked
CAPABILITY_TOKENS = {
    "exec_noninteractive": "Run Codex non-interactively",
    "json_events": "--json",
    "output_schema": "--output-schema",
    "last_message_file": "--output-last-message",
    "model_flag": "--model",
    "sandbox_flag": "--sandbox",
    "cd_flag": "--cd",
    "resume": "Resume a previous session",
    "ephemeral": "--ephemeral",
    "stdin_instructions": "instructions are read from stdin",
}


class CodexProbeError(RuntimeError):
    pass


def _text(run_result) -> str:
    return (run_result.stdout or "") + (run_result.stderr or "")


def probe(exe_path: str, *, run=subprocess.run, timeout: int = 20) -> dict:
    """Local-only capability probe (--version/--help). Never a model call."""
    if not os.path.isabs(exe_path):
        raise CodexProbeError("codex executable must be pinned by absolute path")
    version = run([exe_path, "--version"], capture_output=True, text=True,
                  errors="replace", timeout=timeout)
    if version.returncode:
        raise CodexProbeError("codex --version failed")
    help_main = run([exe_path, "--help"], capture_output=True, text=True,
                    errors="replace", timeout=timeout)
    help_exec = run([exe_path, "exec", "--help"], capture_output=True, text=True,
                    errors="replace", timeout=timeout)
    combined = _text(version) + _text(help_main) + _text(help_exec)
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
            f"installed codex lacks capabilities {missing}; re-approval required")


def build_command(*, frozen_entry: dict, matrix_entry: dict, request: dict,
                  soul_text: str, prompt_text: str, worktree: Path,
                  out_dir: Path) -> dict:
    """Compose the launch argv for one role invocation.

    Model/sandbox/extra flags come from the APPROVED matrix entry only; the
    frozen entry pins the executable. The role Soul is delivered as initial
    instructions over stdin together with the task prompt (contracted as
    ``<soul>\\n\\n<prompt>``); a real end-to-end behaviour check of instruction
    scoping belongs to Stage-2B-2 acceptance (NOT_VERIFIED here).
    """
    exe = frozen_entry["exe_path"]
    model = matrix_entry.get("primary_model")
    sandbox = matrix_entry.get("sandbox_mode")
    extra = matrix_entry.get("extra_argv", [])
    if not model or not sandbox:
        raise CodexProbeError("matrix entry must approve primary_model and sandbox_mode")
    if not isinstance(extra, list) or any(not isinstance(x, str) for x in extra):
        raise CodexProbeError("matrix extra_argv must be a list of strings")
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    last_msg = out_dir / f"{request['run_id']}.last-message.txt"
    argv = [exe, "exec", "--json",
            "-m", model, "-s", sandbox,
            "-C", str(Path(worktree).resolve()),
            "--output-last-message", str(last_msg)]
    argv += [item.format(run_dir=str(out_dir), run_id=request["run_id"]) for item in extra]
    argv.append("-")  # instructions/prompt from stdin
    stdin_text = soul_text.rstrip() + "\n\n" + prompt_text.rstrip() + "\n"
    return {"argv": argv, "stdin_text": stdin_text,
            "last_message_path": str(last_message := last_msg),
            "command_sha256": sha256(canonical_join(argv).encode("utf-8"))}


def canonical_join(parts: list) -> str:
    return "\x00".join(parts)


def parse_events(raw_text: str) -> Iterator[dict]:
    """Walk codex --json JSONL. Unknown event shapes pass through tagged
    ``unknown``; nothing is silently dropped."""
    for line in raw_text.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            event = json.loads(line)
        except ValueError:
            yield {"kind": "unparseable", "raw_sha256": sha256(line.encode("utf-8"))}
            continue
        if not isinstance(event, dict):
            yield {"kind": "unknown", "value_type": type(event).__name__}
            continue
        yield normalize_event(event)


def normalize_event(event: dict) -> dict:
    etype = event.get("type") or event.get("msg", {}).get("type") or "unknown"
    base = {"kind": str(etype), "raw": event}
    if etype in ("session_id", "session_created"):
        base["session_ref"] = str(event.get("session_id") or event.get("id") or "")
    if "rollout_path" in event:
        base["rollout_path"] = str(event["rollout_path"])
    return base


def extract_session_ref(events: list) -> dict:
    refs = {"session_id": None, "rollout_path": None}
    for event in events:
        if event.get("session_ref") and not refs["session_id"]:
            refs["session_id"] = event["session_ref"]
        raw = event.get("raw") or {}
        for key in ("rollout_path",):
            value = raw.get(key) or (raw.get("msg") or {}).get(key)
            if value and not refs[key]:
                refs[key] = str(value)
    return refs


def extract_command_evidence(events: list) -> list:
    """CLI-self-reported command activity. Every record: trusted=False."""
    records = []
    for event in events:
        raw = event.get("raw") or {}
        candidates = [raw, raw.get("msg") or {}, raw.get("item") or {}]
        for candidate in candidates:
            if not isinstance(candidate, dict):
                continue
            command = candidate.get("command")
            if isinstance(command, str) and command:
                records.append({
                    "command": command,
                    "claimed_exit": candidate.get("exit_code", candidate.get("exit")),
                    "source": "cli-event-self-report",
                    "trusted": False,
                })
                break
    return records


def merge_runner_records(claimed: list, runner_records: list) -> list:
    """Upgrade claimed evidence ONLY on exact command agreement with the
    runner-recorded observation (pid-level wrapper capture)."""
    by_command: dict[str, dict] = {}
    for record in runner_records or []:
        if isinstance(record, dict) and isinstance(record.get("command"), str):
            by_command[record["command"]] = record
    merged = []
    for item in claimed:
        match = by_command.get(item["command"])
        entry = dict(item)
        if match is not None and match.get("exit_code") == item.get("claimed_exit"):
            entry["trusted"] = True
            entry["source"] = "runner-observed-agreement"
        elif match is not None:
            entry["contradiction"] = True
        merged.append(entry)
    return merged
