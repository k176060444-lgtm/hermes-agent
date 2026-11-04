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
                         runner_attestation: dict | None = None) -> list:
    """Upgrade claimed evidence ONLY on exact per-invocation agreement with
    runner-recorded observations, and ONLY when the caller supplies a live
    ``runner_attestation`` produced by runner.verify_execution_identity
    (attested=True, not a test seam). Without that attestation every record
    stays trusted=False and is marked as awaiting Stage-2B-2 authentication -
    there is no real runner yet, so simulated 'trusted' results are
    impossible by construction (S2B1-009).

    Matching is per-invocation: each runner record is consumed at most once
    and is paired with the claimed entry of the SAME ordinal, so one receipt
    record can never validate two different invocations of the same command.
    """
    attested = bool(runner_attestation and runner_attestation.get("attested") is True
                    and not runner_attestation.get("test_seam"))
    by_ordinal: dict[int, dict] = {}
    if attested:
        for record in runner_records or []:
            if isinstance(record, dict) and isinstance(record.get("command"), str) \
                    and isinstance(record.get("ordinal"), int):
                by_ordinal[record["ordinal"]] = record
    merged = []
    consumed: set[int] = set()
    for item in claimed:
        entry = dict(item)
        entry["promotion_blocked"] = None if attested else \
            "no authenticated runner attestation (awaiting Stage-2B-2)"
        ordinal = item.get("ordinal")
        match = by_ordinal.get(ordinal) if isinstance(ordinal, int) else None
        if match is None and isinstance(ordinal, int) and attested:
            entry["no_matching_runner_record"] = True
        if match is not None and ordinal not in consumed:
            if match.get("exit_code") == item.get("claimed_exit"):
                entry["trusted"] = True
                entry["source"] = "runner-observed-agreement"
                consumed.add(ordinal)
            else:
                entry["contradiction"] = True
        elif match is not None:
            entry["contradiction"] = True  # record already consumed once
        merged.append(entry)
    return merged
