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


# Strict allowlist for matrix extra_argv (S2B1-008): ONLY these exact tokens
# may appear. Anything else - including reserved overrides (-m/--model,
# -s/--sandbox, -C/--cd, --json, --config, sandbox bypass switches) and
# unknown flags - is rejected. Values are not accepted either: extra_argv is
# boolean flags only.
EXTRA_ARGV_ALLOWLIST = {"--ephemeral"}

_RESERVED_TOKENS = {"-m", "--model", "-s", "--sandbox", "-C", "--cd",
                    "--json", "--config", "--dangerously-bypass-approvals-and-sandbox",
                    "--output-last-message", "--output-schema"}


def check_extra_argv(extra: list, *, allowlist: set | None = None,
                     reserved: set | None = None,
                     error: type[Exception] | None = None) -> None:
    """Shared strict allowlist check for both adapters. Raises the adapter
    error class on any violation."""
    error = error or CodexProbeError
    allowed = EXTRA_ARGV_ALLOWLIST if allowlist is None else set(allowlist)
    reserved = _RESERVED_TOKENS if reserved is None else set(reserved)
    for item in extra:
        if not isinstance(item, str) or not item.startswith("-"):
            raise error(f"extra_argv must be allowlisted boolean flags, got {item!r}")
        if item in reserved:
            raise error(f"extra_argv may not override reserved flag {item!r}")
        if item not in allowed:
            raise error(
                f"extra_argv flag {item!r} is not in the strict allowlist "
                f"{sorted(allowed)}; approval matrix must be re-issued")


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
    check_extra_argv(extra)  # S2B1-008: strict allowlist, no override path
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    last_msg = out_dir / f"{request['run_id']}.last-message.txt"
    argv = [exe, "exec", "--json",
            "-m", model, "-s", sandbox,
            "-C", str(Path(worktree).resolve()),
            "--output-last-message", str(last_msg)]
    argv += list(extra)
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
    ordinal = 0
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
                    "ordinal": ordinal,
                    "claimed_exit": candidate.get("exit_code", candidate.get("exit")),
                    "source": "cli-event-self-report",
                    "trusted": False,
                })
                ordinal += 1
                break
    return records


def merge_runner_records(claimed: list, runner_records: list, *,
                         task_id: str | None = None,
                         run_id: int | None = None) -> list:
    """DIAGNOSTIC comparison ONLY - the trust-promotion path is CLOSED (S2B1-009).

    No caller-supplied value (a dict, a boolean, an 'attestation', a manifest,
    a self-hash or an agreement between CLI events and runner records) can ever
    set ``trusted=True`` here. Every returned entry keeps ``trusted=False``
    and ``source='cli-event-self-report'`` with an explicit
    ``promotion_blocked`` reason. Production-grade execution-evidence
    authentication is a SEPARATE Stage-2B-2 design + acceptance item and is
    deliberately not implemented early.

    The function still diagnoses agreement/conflict, and enforces the identity
    boundaries the re-audit found missing:
    * ``command_mismatch`` - same ordinal but a different command string;
    * ``duplicate_ordinal`` - two runner records claim the same invocation
      ordinal (silent last-wins overwrite is forbidden, both stay untrusted);
    * ``cross_execution_binding`` - the record's task_id/run_id disagree with
      the supplied execution context, or the record carries no binding at all
      (``unbound_execution_context``) while a context was supplied;
    * ``exit_code_mismatch`` - same command/instance but a different exit code
      (this is a contradiction; it is recorded, never promoted);
    * ``matched_unauthenticated`` - everything agrees, yet trust stays false
      because no authenticated runner source exists in Stage-2B-1.
    """
    records = [r for r in (runner_records or []) if isinstance(r, dict)]
    ordinal_count: dict = {}
    for record in records:
        ordinal = record.get("ordinal")
        if isinstance(ordinal, int):
            ordinal_count[ordinal] = ordinal_count.get(ordinal, 0) + 1

    merged = []
    for item in claimed:
        entry = dict(item)
        entry["trusted"] = False
        entry["source"] = item.get("source", "cli-event-self-report")
        entry["promotion_blocked"] = (
            "trust-promotion path closed in Stage-2B-1 (S2B1-009); "
            "authenticated runner evidence is a Stage-2B-2 design item")
        ordinal = item.get("ordinal")
        matches = [r for r in records if isinstance(ordinal, int)
                   and r.get("ordinal") == ordinal]
        if ordinal_count.get(ordinal, 0) > 1:
            entry["duplicate_ordinal"] = True
        if not matches:
            if isinstance(ordinal, int):
                entry["no_matching_runner_record"] = True
            merged.append(entry)
            continue
        record = matches[0]
        if record.get("command") != item.get("command"):
            entry["command_mismatch"] = True
            merged.append(entry)
            continue
        if task_id is not None or run_id is not None:
            if record.get("task_id") != task_id or record.get("run_id") != run_id:
                entry["cross_execution_binding"] = True
            elif record.get("exit_code") != item.get("claimed_exit"):
                entry["exit_code_mismatch"] = True
            else:
                entry["matched_unauthenticated"] = True
            merged.append(entry)
            continue
        # No execution context supplied: even a byte-identical command/exit
        # cannot be proven to belong to THIS invocation.
        entry["unbound_execution_context"] = True
        if record.get("exit_code") != item.get("claimed_exit"):
            entry["exit_code_mismatch"] = True
        else:
            entry["matched_unauthenticated"] = True
        merged.append(entry)
    return merged
