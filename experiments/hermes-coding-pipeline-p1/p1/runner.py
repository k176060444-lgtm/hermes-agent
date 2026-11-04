"""Trusted Agent-Runner protocol and offline orchestrator client (Stage-2B-1).

Trust model
-----------
The Runner is a *separate OS-level process* that launches Harness Agents under
a dedicated Windows identity and records raw execution evidence. P1 never
grants trust from Runner *self-reports* (JSON fields such as ``isolated``).
Trust comes only from OS facts the orchestrator measures itself:

* the live process token SID (never equal to the orchestrator SID) and group
  membership (never Administrators),
* the executable path/digest on disk matching the frozen task snapshot,
* the ledger DACL demonstrably excluding the agent principal,
* bounded capture/receipt digests rehashed from orchestrator-owned storage.

Deployment reality (Stage-2B-1): no provisioned runner service or agentx
account exists on 21bao, therefore ``RunnerClient.launch`` fails closed for
any real execution. This module is the audited contract + offline machinery
only. It does NOT replace executor.py's hard gate; nothing here is wired to
enable real dispatch.
"""
from __future__ import annotations

import hashlib
import os
import subprocess
import time
from pathlib import Path
from typing import Any

from .contracts import canonical, digest_file, read_json

RUNNER_SCHEMA_VERSION = 1

# Fixed, non-configurable well-known SIDs used for identity assertions.
SID_LOCAL_SYSTEM = "S-1-5-18"
SID_ADMINISTRATORS = "S-1-5-32-544"
SID_EVERYONE = "S-1-1-0"
SID_AUTHENTICATED_USERS = "S-1-5-11"
SID_USERS = "S-1-5-32-545"

_RECEIPT_STATUSES = {"COMPLETED", "FAILED", "TIMEOUT", "KILLED", "UNKNOWN"}

LAUNCH_REQUIRED_FIELDS = (
    "schema_version", "task_id", "run_id", "stage", "role",
    "harness", "model", "soul_sha256", "matrix_sha256", "spec_sha256",
    "intent_sha256", "reviewed_commit", "worktree_path", "input_sha256",
    "idempotency_key", "timeout_seconds", "frozen_harness_sha256",
    "request_sha256",
)

RECEIPT_REQUIRED_FIELDS = (
    "schema_version", "task_id", "run_id", "idempotency_key",
    "agent_pid", "agent_token_sid", "agent_group_sids", "launch_source",
    "exit_code", "started_at", "finished_at",
    "stdout_sha256", "stderr_sha256", "capture_meta_sha256",
    "harness_exe_path", "harness_exe_sha256", "harness_version",
    "argv_sha256", "status",
)


class RunnerError(RuntimeError):
    pass


class RunnerUnavailableError(RunnerError):
    """No provisioned runner: real execution is impossible and stays blocked."""


class RunnerAttestationError(RunnerError):
    """A live or bound verification failed: never dispatch on top of it."""


def _sha(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def build_launch_request(*, task: dict, stage: str, role: str, run_id: int,
                         matrix_entry: dict, bindings: dict,
                         worktree_path: Path, timeout_seconds: int,
                         idempotency_key: str) -> dict:
    """Compose the fixed-field launch request from approved inputs only.

    ``matrix_entry`` supplies harness/model (never defaulted here);
    ``bindings`` must carry soul/matrix/spec/intent SHAs and reviewed_commit.
    """
    for key in ("soul_sha256", "matrix_sha256", "spec_sha256",
                "intent_sha256", "reviewed_commit", "input_sha256",
                "frozen_harness_sha256"):
        if not isinstance(bindings.get(key), str) or len(bindings[key]) < 16:
            raise RunnerAttestationError(f"launch binding missing/weak: {key}")
    if not matrix_entry.get("harness") or not matrix_entry.get("primary_model"):
        raise RunnerAttestationError("matrix entry must name harness and primary_model")
    request = {
        "schema_version": RUNNER_SCHEMA_VERSION,
        "task_id": task["task_id"],
        "run_id": run_id,
        "stage": stage,
        "role": role,
        "harness": matrix_entry["harness"],
        "model": matrix_entry["primary_model"],
        **{key: bindings[key] for key in
           ("soul_sha256", "matrix_sha256", "spec_sha256", "intent_sha256",
            "reviewed_commit", "input_sha256", "frozen_harness_sha256")},
        "worktree_path": str(Path(worktree_path).resolve()),
        "timeout_seconds": int(timeout_seconds),
        "idempotency_key": idempotency_key,
    }
    body = canonical({k: v for k, v in request.items() if k != "request_sha256"})
    request["request_sha256"] = _sha(body)
    return request


def validate_launch_request(request: dict) -> None:
    missing = [f for f in LAUNCH_REQUIRED_FIELDS if f not in request]
    if missing:
        raise RunnerAttestationError(f"launch request missing fields: {missing}")
    if request["schema_version"] != RUNNER_SCHEMA_VERSION:
        raise RunnerAttestationError("unsupported runner schema version")
    body = canonical({k: v for k, v in request.items() if k != "request_sha256"})
    if _sha(body) != request["request_sha256"]:
        raise RunnerAttestationError("launch request digest mismatch (tampered?)")
    for field in ("soul_sha256", "matrix_sha256", "spec_sha256", "intent_sha256",
                  "input_sha256", "frozen_harness_sha256"):
        if not isinstance(request[field], str) or len(request[field]) < 64:
            raise RunnerAttestationError(f"launch field {field} is not a digest")
    if not request["idempotency_key"]:
        raise RunnerAttestationError("idempotency key required")


def validate_receipt(receipt: dict, request: dict) -> None:
    """Structure + cross-binding check for a Runner receipt. Self-report only;
    identity TRUST additionally requires verify_execution_identity()."""
    missing = [f for f in RECEIPT_REQUIRED_FIELDS if f not in receipt]
    if missing:
        raise RunnerAttestationError(f"receipt missing fields: {missing}")
    for key in ("task_id", "run_id", "idempotency_key"):
        if receipt[key] != request[key]:
            raise RunnerAttestationError(f"receipt {key} not bound to request")
    if receipt["status"] not in _RECEIPT_STATUSES:
        raise RunnerAttestationError("receipt status not recognized")
    for key in ("stdout_sha256", "stderr_sha256", "capture_meta_sha256",
                "harness_exe_sha256", "argv_sha256"):
        if not isinstance(receipt[key], str) or len(receipt[key]) != 64:
            raise RunnerAttestationError(f"receipt {key} is not a sha256 hex")
    if receipt["harness_exe_sha256"] != request["frozen_harness_sha256"]:
        raise RunnerAttestationError("harness executable differs from frozen snapshot")
    if receipt["schema_version"] != RUNNER_SCHEMA_VERSION:
        raise RunnerAttestationError("receipt schema version mismatch")
    if receipt["status"] == "UNKNOWN":
        raise RunnerAttestationError("UNKNOWN receipt is reconciliation-only")


# ---------------------------------------------------------------- live OS side
_API = None


def _api():
    """Configure kernel32/advapi32 signatures once; 64-bit HANDLEs must never
    be truncated by the default restype."""
    global _API
    if _API is not None:
        return _API
    if os.name != "nt":
        raise RunnerUnavailableError("Windows identity APIs are unavailable")
    import ctypes
    from ctypes import wintypes

    kernel = ctypes.windll.kernel32
    advapi = ctypes.windll.advapi32
    HANDLE = wintypes.HANDLE
    kernel.GetCurrentProcess.restype = HANDLE
    kernel.OpenProcess.restype = HANDLE
    kernel.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
    kernel.CloseHandle.argtypes = [HANDLE]
    kernel.QueryFullProcessImageNameW.argtypes = [HANDLE, wintypes.DWORD,
                                                  wintypes.LPWSTR,
                                                  ctypes.POINTER(wintypes.DWORD)]
    kernel.QueryFullProcessImageNameW.restype = wintypes.BOOL
    kernel.LocalFree.argtypes = [ctypes.c_void_p]
    advapi.OpenProcessToken.restype = wintypes.BOOL
    advapi.OpenProcessToken.argtypes = [HANDLE, wintypes.DWORD,
                                        ctypes.POINTER(HANDLE)]
    advapi.GetTokenInformation.restype = wintypes.BOOL
    advapi.GetTokenInformation.argtypes = [HANDLE, ctypes.c_int, ctypes.c_void_p,
                                           wintypes.DWORD,
                                           ctypes.POINTER(wintypes.DWORD)]
    advapi.ConvertSidToStringSidW.restype = wintypes.BOOL
    advapi.ConvertSidToStringSidW.argtypes = [ctypes.c_void_p,
                                              ctypes.POINTER(ctypes.c_wchar_p)]
    _API = (kernel, advapi)
    return _API


def orchestrator_sid() -> str:
    if os.name != "nt":
        raise RunnerUnavailableError("orchestrator identity attestation is Windows-only")
    import ctypes
    from ctypes import wintypes

    kernel, advapi = _api()
    token = wintypes.HANDLE()
    if not advapi.OpenProcessToken(kernel.GetCurrentProcess(), 0x0008,
                                   ctypes.byref(token)):
        raise RunnerAttestationError("OpenProcessToken failed for orchestrator")
    try:
        return _query_token_sid(advapi, kernel, token, 1)
    finally:
        kernel.CloseHandle(token)


def _query_token_info(advapi, kernel, token, info_class: int):
    """GetTokenInformation two-phase call. The probe phase passes a real 4-8
    byte scratch buffer (never NULL) so the out size is trustworthy; returns
    the raw result buffer."""
    import ctypes
    from ctypes import wintypes

    size = wintypes.DWORD()
    scratch = ctypes.create_string_buffer(8)
    advapi.GetTokenInformation(token, info_class, scratch, 8, ctypes.byref(size))
    if not size.value:
        raise RunnerAttestationError(f"token info {info_class}: zero reported size")
    buf = ctypes.create_string_buffer(size.value)
    if not advapi.GetTokenInformation(token, info_class, buf, size, ctypes.byref(size)):
        raise RunnerAttestationError(f"GetTokenInformation({info_class}) failed")
    return buf


def _convert_sid(advapi, kernel, sid_ptr: int) -> str:
    import ctypes

    if not sid_ptr:
        raise RunnerAttestationError("null SID pointer")
    string_sid = ctypes.c_wchar_p()
    if not advapi.ConvertSidToStringSidW(ctypes.c_void_p(sid_ptr),
                                         ctypes.byref(string_sid)):
        raise RunnerAttestationError("ConvertSidToStringSidW failed")
    value = string_sid.value
    kernel.LocalFree(ctypes.c_void_p(ctypes.cast(string_sid, ctypes.c_void_p).value))
    if not value:
        raise RunnerAttestationError("empty converted SID")
    return str(value)


def _query_token_sid(advapi, kernel, token, info_class: int) -> str:
    import ctypes

    buf = _query_token_info(advapi, kernel, token, info_class)
    if info_class != 1:  # TOKEN_USER = 1 (not 20!)
        raise RunnerAttestationError("unsupported info class for single sid")
    ptr = ctypes.cast(buf, ctypes.POINTER(ctypes.c_void_p))[0]
    return _convert_sid(advapi, kernel, ptr)


def live_process_token(pid: int) -> dict:
    """Measured user SID + group SIDs of a live process. Windows only, fails
    closed. This is the authoritative identity source, not receipt fields."""
    if os.name != "nt":
        raise RunnerUnavailableError("live token query is Windows-only")
    import ctypes
    from ctypes import wintypes

    kernel, advapi = _api()
    hproc = kernel.OpenProcess(0x1000, False, pid)
    if not hproc:
        raise RunnerAttestationError(f"cannot open process {pid}")
    try:
        token = wintypes.HANDLE()
        if not advapi.OpenProcessToken(hproc, 0x0008, ctypes.byref(token)):
            raise RunnerAttestationError(f"cannot open token of pid {pid}")
        try:
            user_sid = _query_token_sid(advapi, kernel, token, 1)
            groups = _query_token_groups(advapi, kernel, token)
        finally:
            kernel.CloseHandle(token)
    finally:
        kernel.CloseHandle(hproc)
    return {"pid": pid, "user_sid": user_sid, "group_sids": groups}


def _query_token_groups(advapi, kernel, token) -> list:
    import ctypes
    from ctypes import wintypes

    TOKEN_GROUPS = 2
    buf = _query_token_info(advapi, kernel, token, TOKEN_GROUPS)
    count = ctypes.cast(buf, ctypes.POINTER(wintypes.DWORD))[0]
    # TOKEN_GROUPS (x64): DWORD GroupCount; 4-byte padding; then an INLINE
    # array of SID_AND_ATTRIBUTES {PSID Sid; DWORD Attributes} (16 bytes each).
    entry_size = 2 * ctypes.sizeof(ctypes.c_void_p)
    sids = []
    for index in range(count):
        sid_ptr = ctypes.c_void_p.from_buffer_copy(
            buf, ctypes.sizeof(ctypes.c_void_p) + index * entry_size).value
        sids.append(_convert_sid(advapi, kernel, sid_ptr))
    return sids


def live_process_image(pid: int) -> str:
    if os.name != "nt":
        raise RunnerUnavailableError("live image query is Windows-only")
    import ctypes
    from ctypes import wintypes

    kernel, _ = _api()
    hproc = kernel.OpenProcess(0x1000, False, pid)
    if not hproc:
        raise RunnerAttestationError(f"cannot open process {pid}")
    try:
        buffer = ctypes.create_unicode_buffer(32768)
        size = wintypes.DWORD(32768)
        if not kernel.QueryFullProcessImageNameW(hproc, 0, buffer, ctypes.byref(size)):
            raise RunnerAttestationError(f"image path query failed for pid {pid}")
        return buffer.value
    finally:
        kernel.CloseHandle(hproc)


def verify_execution_identity(*, receipt: dict, request: dict,
                              orchestrator: str, ledger_root: Path,
                              process_alive=None) -> dict:
    """Re-measure the agent process live and cross-check the receipt.

    Every check reads the OS, never the JSON: token SID, group membership,
    executable path+digest vs the frozen snapshot, ledger DACL exposure.
    Raises RunnerAttestationError on any violation.
    """
    probe = process_alive or live_process_token
    expected = request.get("expected_agent_sid")
    if not expected:
        raise RunnerAttestationError("no expected agent SID pinned in manifest")
    if receipt["agent_token_sid"] != expected:
        raise RunnerAttestationError("receipt SID does not match manifest pin")
    live = probe(int(receipt["agent_pid"]))
    if live["user_sid"] != receipt["agent_token_sid"]:
        raise RunnerAttestationError("live token SID differs from receipt")
    if live["user_sid"] == orchestrator:
        raise RunnerAttestationError("agent runs with the orchestrator identity")
    if SID_ADMINISTRATORS in live["group_sids"]:
        raise RunnerAttestationError("agent token carries Administrators")
    if process_alive is None:
        image = live_process_image(int(receipt["agent_pid"]))
        if os.path.normcase(image) != os.path.normcase(receipt["harness_exe_path"]):
            raise RunnerAttestationError("live executable path differs from receipt")
    else:
        image = receipt["harness_exe_path"]
    if digest_file(Path(image)) != request["frozen_harness_sha256"]:
        raise RunnerAttestationError("harness digest differs from frozen snapshot")
    verify_ledger_inaccessible(ledger_root, live["user_sid"], live["group_sids"])
    return {"attested": True, "user_sid": live["user_sid"],
            "groups": sorted(live["group_sids"]), "image": image}


def verify_ledger_inaccessible(ledger_root: Path, agent_sid: str,
                               agent_group_sids: list, *, query=None) -> None:
    """Fail closed unless the ledger root DACL grants NO effective Allow ACE
    covering the agent user or any of its groups (plus Everyone /
    Authenticated Users / Users which every standard account carries)."""
    runner = query or _effective_allow_principals
    principals = set(runner(ledger_root))
    # EVERYONE / AUTHENTICATED_USERS are in every token; USERS is added only
    # when the measured agent token actually carries it. Administrators is NOT
    # watched here: it is the declared TCB allowlist of trust.py, and the
    # separate group-membership check above already forbids an agent from
    # holding it.
    watched = {agent_sid, *(agent_group_sids or []),
               SID_EVERYONE, SID_AUTHENTICATED_USERS}
    leak = sorted((principals & watched) - {SID_LOCAL_SYSTEM})
    if leak:
        raise RunnerAttestationError(
            f"ledger root DACL exposes agent principals: {leak}")


_ACL_QUERY = r'''
$ErrorActionPreference='Stop'
$acl=Get-Acl -LiteralPath $args[0]
$sids=@()
foreach($rule in $acl.GetAccessRules($true,$true,[System.Security.Principal.SecurityIdentifier])){
  if($rule.AccessControlType -eq 'Allow'){$sids+=$rule.IdentityReference.Value}
}
ConvertTo-Json -InputObject @($sids|Select-Object -Unique) -Compress
'''


def _effective_allow_principals(path: Path) -> list:
    if os.name != "nt":
        raise RunnerUnavailableError("DACL query is Windows-only")
    import base64
    script = _ACL_QUERY.replace("$args[0]", "'" + str(path).replace("'", "''") + "'")
    encoded = base64.b64encode(script.encode("utf-16le")).decode("ascii")
    result = subprocess.run(["powershell.exe", "-NoProfile", "-NonInteractive",
                             "-EncodedCommand", encoded],
                            capture_output=True, text=True, errors="replace", timeout=20)
    if result.returncode:
        raise RunnerAttestationError("ledger DACL query failed")
    import json as _json
    data = _json.loads(result.stdout)
    if not isinstance(data, list):
        raise RunnerAttestationError("ledger DACL query shape invalid")
    return [str(x) for x in data]


# ---------------------------------------------------------------- client
class RunnerClient:
    """Offline-capable orchestrator-side client. Real launch requires a
    provisioned runner manifest (Stage-2B-2); without it every launch fails
    closed. Nothing here re-dispatches an ambiguous execution."""

    def __init__(self, home: Path, manifest_path: Path | None = None):
        self.home = Path(home)
        self.manifest_path = manifest_path or (self.home / "snapshots" / "runner_manifest.json")

    def manifest(self) -> dict:
        if not self.manifest_path.is_file():
            raise RunnerUnavailableError(
                "no trusted runner manifest provisioned; real execution stays blocked")
        data = read_json(self.manifest_path)
        for key in ("spool_inbox", "spool_outbox", "expected_agent_sid",
                    "runner_exe", "runner_exe_sha256"):
            if not data.get(key):
                raise RunnerUnavailableError(f"runner manifest incomplete: {key}")
        if digest_file(Path(data["runner_exe"])) != data["runner_exe_sha256"]:
            raise RunnerAttestationError("runner executable differs from manifest pin")
        return data

    def runner_health(self) -> dict:
        """Read-only probe: does a provisioned runner service exist AND is the
        agent account actually distinct from this process?"""
        if os.name != "nt":
            return {"available": False, "reason": "non-Windows host"}
        try:
            manifest = self.manifest()
            orch = orchestrator_sid()
            if manifest["expected_agent_sid"] == orch:
                return {"available": False, "reason": "agent SID equals orchestrator SID"}
            return {"available": True, "reason": "manifest provisioned",
                    "expected_agent_sid": manifest["expected_agent_sid"]}
        except RunnerError as exc:
            return {"available": False, "reason": str(exc)[:200]}

    def launch(self, request: dict, stdin_text: str) -> dict:
        """Stage-2B-1: always refuses. When a runner exists, the future path
        writes request.json into the inbox (never outbox), waits, then
        validates + attests. Re-issues for the same run_id are refused: the
        ledger already contains an execution_dispatched intent (P1 semantics)
        and ambiguous dispatch is reconciliation-only."""
        validate_launch_request(request)
        health = self.runner_health()
        if not health["available"]:
            raise RunnerUnavailableError(
                f"runner not provisioned/attested: {health['reason']}")
        raise RunnerUnavailableError(
            "runner transport not implemented in Stage-2B-1 by design")

    def poll(self, request: dict) -> dict:
        validate_launch_request(request)
        if not self.manifest_path.is_file():
            return {"state": "NO_RUNNER", "dispatched": None}
        try:
            manifest = self.manifest()
        except RunnerUnavailableError:
            return {"state": "NO_RUNNER", "dispatched": None}
        receipt_path = Path(manifest["spool_outbox"]) / f"{request['run_id']}.receipt.json"
        request_path = Path(manifest["spool_inbox"]) / f"{request['run_id']}.request.json"
        if receipt_path.is_file():
            return {"state": "RECEIPT", "receipt": read_json(receipt_path)}
        if request_path.is_file():
            return {"state": "DISPATCHED", "dispatched_at":
                    read_json(request_path).get("written_at")}
        return {"state": "NOT_DISPATCHED", "dispatched": None}
