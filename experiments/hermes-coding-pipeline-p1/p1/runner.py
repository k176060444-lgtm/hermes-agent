"""Trusted Agent-Runner protocol and offline orchestrator client (Stage-2B-1,
remediated after the independent Qwen-Flash audit of cc3a42cd).

Trust model
-----------
The Runner is a *separate OS-level process* that launches Harness Agents under
a dedicated Windows identity and records raw execution evidence. P1 never
grants trust from Runner *self-reports* (JSON fields such as ``isolated``).

Trust boundary that must stay explicit: ``request_sha256`` and every digest in
this protocol is a SELF-HASH over plain JSON. A self-hash proves tamper
evidence against accidental corruption ONLY; it is NOT a signature and it does
not authenticate the writer. Authenticity comes only from:

* OS facts the orchestrator measures itself on a LIVE process (token SID,
  group membership, image path, process creation time),
* digests rehashed from orchestrator-owned storage (never trusted from the
  receipt fields alone),
* the ledger DACL demonstrably excluding the agent principal,
* a runner manifest read from the PROTECTED task home (L3) whose pinned
  executable digest is re-measured from disk — structure and digest
  consistency (L1/L2) alone are explicitly NOT provenance and NOT identity.

Identity is proven in-flight only. After an execution ends, the orchestrator
may verify receipt INTEGRITY (structure, binding, capture re-hash) but must
never claim it re-attested a process that no longer exists; ``attested`` is
reserved for the live path.

Deployment reality (Stage-2B-1): no provisioned runner service or agentx
account exists on 21bao, therefore ``RunnerClient.launch`` fails closed for
any real execution and ``runner_health`` honestly reports the service as not
deployed. This module is the audited contract + offline machinery only. It
does NOT replace executor.py's hard gate; nothing here is wired to enable
real dispatch.
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
    "frozen_harness_version", "command_sha256",
    "request_sha256",
)

RECEIPT_REQUIRED_FIELDS = (
    "schema_version", "task_id", "run_id", "idempotency_key",
    "stage", "role", "harness", "model", "reviewed_commit",
    "agent_pid", "agent_token_sid", "agent_group_sids", "launch_source",
    "exit_code", "started_at", "finished_at", "process_start_time",
    "stdout_sha256", "stderr_sha256", "capture_meta_sha256",
    "harness_exe_path", "harness_exe_sha256", "harness_version",
    "command_sha256", "runner_manifest_sha256", "status",
)

# status -> exit_code semantics enforced by validate_receipt (S2B1-015).
_EXIT_SEMANTICS = {
    "COMPLETED": lambda code: code == 0,
    "FAILED": lambda code: isinstance(code, int) and not isinstance(code, bool)
                           and code != 0,
    "TIMEOUT": lambda code: code is None,
    "KILLED": lambda code: code is None,
}


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
                         idempotency_key: str,
                         command_sha256: str) -> dict:
    """Compose the fixed-field launch request from approved inputs only.

    ``matrix_entry`` supplies harness/model (never defaulted here);
    ``bindings`` must carry soul/matrix/spec/intent SHAs, reviewed_commit and
    the frozen harness snapshot (digest + version). ``command_sha256`` is the
    digest of the exact argv the approved adapter built (build_command output)
    - the receipt must echo it, closing the 'what actually ran' gap.
    """
    for key in ("soul_sha256", "matrix_sha256", "spec_sha256",
                "intent_sha256", "reviewed_commit", "input_sha256",
                "frozen_harness_sha256"):
        if not isinstance(bindings.get(key), str) or len(bindings[key]) < 16:
            raise RunnerAttestationError(f"launch binding missing/weak: {key}")
    if not isinstance(bindings.get("frozen_harness_version"), str) or \
            not bindings["frozen_harness_version"].strip():
        raise RunnerAttestationError("launch binding missing: frozen_harness_version")
    if not isinstance(command_sha256, str) or len(command_sha256) != 64:
        raise RunnerAttestationError("command_sha256 must be a sha256 hex of the approved argv")
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
            "reviewed_commit", "input_sha256", "frozen_harness_sha256",
            "frozen_harness_version")},
        "worktree_path": str(Path(worktree_path).resolve()),
        "timeout_seconds": int(timeout_seconds),
        "idempotency_key": idempotency_key,
        "command_sha256": command_sha256,
    }
    body = canonical({k: v for k, v in request.items() if k != "request_sha256"})
    request["request_sha256"] = _sha(body)  # SELF-HASH: tamper-evident, NOT a signature
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
                  "input_sha256", "frozen_harness_sha256", "command_sha256"):
        if not isinstance(request[field], str) or len(request[field]) < 64:
            raise RunnerAttestationError(f"launch field {field} is not a digest")
    if not isinstance(request["frozen_harness_version"], str) or \
            not request["frozen_harness_version"].strip():
        raise RunnerAttestationError("launch field frozen_harness_version missing")
    if not request["idempotency_key"]:
        raise RunnerAttestationError("idempotency key required")


def validate_receipt(receipt: dict, request: dict) -> None:
    """Structure + full cross-binding check for a Runner receipt.

    The receipt must echo stage/role/harness/model/reviewed_commit and the
    approved command digest (S2B1-004), its status must agree with the exit
    code (S2B1-015), and the runner manifest digest it names must be present.
    Self-report only; identity TRUST additionally requires the live
    verify_execution_identity() path (never available post-exit).
    """
    missing = [f for f in RECEIPT_REQUIRED_FIELDS if f not in receipt]
    if missing:
        raise RunnerAttestationError(f"receipt missing fields: {missing}")
    for key in ("task_id", "run_id", "idempotency_key", "stage", "role",
                "harness", "model", "reviewed_commit", "command_sha256"):
        if receipt[key] != request[key]:
            raise RunnerAttestationError(f"receipt {key} not bound to request")
    if receipt["status"] not in _RECEIPT_STATUSES:
        raise RunnerAttestationError("receipt status not recognized")
    if receipt["status"] == "UNKNOWN":
        raise RunnerAttestationError("UNKNOWN receipt is reconciliation-only")
    if not _EXIT_SEMANTICS[receipt["status"]](receipt["exit_code"]):
        raise RunnerAttestationError(
            f"receipt status/exit_code contradiction: "
            f"{receipt['status']} with exit_code={receipt['exit_code']!r}")
    for stamp in ("started_at", "finished_at", "process_start_time"):
        value = receipt[stamp]
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise RunnerAttestationError(f"receipt {stamp} must be a numeric timestamp")
    if receipt["finished_at"] < receipt["started_at"]:
        raise RunnerAttestationError("receipt finished_at precedes started_at")
    for key in ("stdout_sha256", "stderr_sha256", "capture_meta_sha256",
                "harness_exe_sha256", "command_sha256",
                "runner_manifest_sha256"):
        if not isinstance(receipt[key], str) or len(receipt[key]) != 64:
            raise RunnerAttestationError(f"receipt {key} is not a sha256 hex")
    if receipt["harness_exe_sha256"] != request["frozen_harness_sha256"]:
        raise RunnerAttestationError("harness executable differs from frozen snapshot")
    if receipt["harness_version"] != request["frozen_harness_version"]:
        raise RunnerAttestationError(
            "harness version differs from frozen snapshot: "
            f"{receipt['harness_version']!r} != {request['frozen_harness_version']!r}")
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
    kernel.GetExitCodeProcess.restype = wintypes.BOOL
    kernel.GetExitCodeProcess.argtypes = [HANDLE, ctypes.POINTER(wintypes.DWORD)]
    kernel.GetProcessTimes.restype = wintypes.BOOL
    kernel.GetProcessTimes.argtypes = [HANDLE, ctypes.POINTER(wintypes.FILETIME),
                                       ctypes.POINTER(wintypes.FILETIME),
                                       ctypes.POINTER(wintypes.FILETIME),
                                       ctypes.POINTER(wintypes.FILETIME)]
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


def _process_start_time(kernel, hproc) -> float:
    """Real process creation time as epoch seconds (FILETIME 100ns/1601)."""
    import ctypes
    from ctypes import wintypes

    creation = wintypes.FILETIME()
    exit_t = wintypes.FILETIME()
    kernel_t = wintypes.FILETIME()
    user_t = wintypes.FILETIME()
    if not kernel.GetProcessTimes(hproc, ctypes.byref(creation),
                                  ctypes.byref(exit_t), ctypes.byref(kernel_t),
                                  ctypes.byref(user_t)):
        raise RunnerAttestationError("GetProcessTimes failed")
    stamp = (creation.dwHighDateTime << 32) | creation.dwLowDateTime
    return stamp / 10_000_000.0 - 11_644_473_600.0


def process_identity(pid: int) -> dict:
    """Measure ONE live process instance end-to-end: liveness, creation time,
    token user SID, group SIDs and image path - all from the OS, all failing
    closed. A dead or recycled PID cannot produce this record."""
    if os.name != "nt":
        raise RunnerUnavailableError("process identity measurement is Windows-only")
    import ctypes
    from ctypes import wintypes

    kernel, advapi = _api()
    hproc = kernel.OpenProcess(0x1000, False, pid)  # QUERY_LIMITED_INFORMATION
    if not hproc:
        raise RunnerAttestationError(f"cannot open process {pid}")
    try:
        code = wintypes.DWORD()
        if not kernel.GetExitCodeProcess(hproc, ctypes.byref(code)):
            raise RunnerAttestationError(f"GetExitCodeProcess failed for {pid}")
        if code.value != 259:  # STILL_ACTIVE
            raise RunnerAttestationError(
                f"process {pid} has exited (exit={code.value}); identity cannot "
                "be attested post-exit - use verify_receipt_integrity instead")
        start_time = _process_start_time(kernel, hproc)
        token = wintypes.HANDLE()
        if not advapi.OpenProcessToken(hproc, 0x0008, ctypes.byref(token)):
            raise RunnerAttestationError(f"cannot open token of pid {pid}")
        try:
            user_sid = _query_token_sid(advapi, kernel, token, 1)
            groups = _query_token_groups(advapi, kernel, token)
        finally:
            kernel.CloseHandle(token)
        buffer = ctypes.create_unicode_buffer(32768)
        size = wintypes.DWORD(32768)
        if not kernel.QueryFullProcessImageNameW(hproc, 0, buffer, ctypes.byref(size)):
            raise RunnerAttestationError(f"image path query failed for pid {pid}")
        image = buffer.value
    finally:
        kernel.CloseHandle(hproc)
    return {"pid": pid, "alive": True, "start_time": start_time,
            "user_sid": user_sid, "group_sids": groups, "image": image}


def _assert_manifest_current(manifest: dict) -> None:
    """Re-verify the manifest shape and re-measure its pinned runner exe from
    disk, so a stale/edited manifest cannot ride through. NOTE (S2B1F-002):
    this proves STRUCTURE + LOCAL DIGEST CONSISTENCY only - provenance is
    established exclusively by _read_anchored_manifest() below."""
    for key in ("task_id", "spool_inbox", "spool_outbox", "expected_agent_sid",
                "runner_exe", "runner_exe_sha256"):
        if not manifest.get(key):
            raise RunnerAttestationError(f"runner manifest incomplete: {key}")
    if digest_file(Path(manifest["runner_exe"])) != manifest["runner_exe_sha256"]:
        raise RunnerAttestationError("runner executable differs from manifest pin")


MANIFEST_NAME = "runner_manifest.json"


def _read_anchored_manifest(home: Path, task_id: str) -> dict:
    """S2B1F-002 provenance anchor: the trusted manifest is read from the
    orchestrator-protected task HOME (snapshots/runner_manifest.json, the same
    directory P1 initialized under trust.validate_private_task_home) and is
    task-bound. A caller-CONSTRUCTED manifest dict is never trusted: shape
    validity and matching local digests prove self-consistency ONLY, not
    provisioning from protected state, and never identity attestation.

    The four conclusions must stay distinct:
      L1 field structure valid          <- _assert_manifest_current
      L2 digests mutually consistent    <- manifest_sha256 echo + capture rehash
      L3 manifest read from protected
         orchestrator task home         <- THIS function (plus the trust gate
                                           that protected the home at init)
      L4 runner/agent identity attested
         by live OS measurement         <- verify_execution_identity, live
         path only; verify_receipt_integrity never claims it."""
    path = Path(home) / "snapshots" / MANIFEST_NAME
    if not path.is_file():
        raise RunnerUnavailableError(
            "no anchored runner manifest in the protected task home; real "
            "execution stays blocked")
    manifest = read_json(path)
    _assert_manifest_current(manifest)
    if manifest["task_id"] != task_id:
        raise RunnerAttestationError(
            "anchored manifest is bound to a different task")
    return manifest


def manifest_sha256(manifest: dict) -> str:
    return hashlib.sha256(canonical(manifest).encode("utf-8")).hexdigest()


def verify_execution_identity(*, receipt: dict, request: dict, home: Path,
                              ledger_root: Path | None = None,
                              orchestrator: str | None = None,
                              identity_probe=None) -> dict:
    """Re-measure the agent process LIVE and cross-check the receipt.

    Enforcement chain (S2B1-001 + S2B1F-002): the launch request and receipt
    are validated and cross-bound FIRST; the manifest is read from the
    PROTECTED task HOME (never from a caller-supplied dict) and is task-bound;
    its pinned runner executable is re-measured from disk; the expected agent
    SID comes only from that anchored manifest.

    Every identity fact is measured from the OS on a live process instance
    (S2B1-002/003): token SID, groups, image path and the process creation
    time (which must match the receipt's ``process_start_time``, defeating
    PID reuse). The receipt's self-reported exe path is never used as the
    image source.

    ``identity_probe`` exists ONLY for unit tests. When provided, every check
    still runs and still raises on violation, but the result is forcibly
    marked ``attested=False`` with ``test_seam=True`` - a substitute can never
    obtain production trust. Note that even a live ``attested=True`` proves
    L4 for the measured PROCESS INSTANCE only; it does not retroactively
    attest finished executions (use verify_receipt_integrity, which by design
    can never return attested=True).
    """
    validate_launch_request(request)
    validate_receipt(receipt, request)
    manifest = _read_anchored_manifest(Path(home), request["task_id"])
    pin = manifest["expected_agent_sid"]
    if receipt["agent_token_sid"] != pin:
        raise RunnerAttestationError("receipt SID does not match manifest pin")
    orchestrator = orchestrator or orchestrator_sid()
    if identity_probe is None:
        if os.name != "nt":
            raise RunnerUnavailableError("live identity attestation is Windows-only")
        identity = process_identity(int(receipt["agent_pid"]))
        test_seam = False
    else:
        identity = identity_probe(int(receipt["agent_pid"]))
        test_seam = True
    if not identity.get("alive"):
        raise RunnerAttestationError("agent process is not live")
    if abs(float(identity["start_time"]) - float(receipt["process_start_time"])) > 0.0:
        raise RunnerAttestationError(
            "process creation time differs from receipt (PID reuse or stale receipt)")
    if identity["user_sid"] != receipt["agent_token_sid"]:
        raise RunnerAttestationError("live token SID differs from receipt")
    if identity["user_sid"] == orchestrator:
        raise RunnerAttestationError("agent runs with the orchestrator identity")
    if SID_ADMINISTRATORS in identity["group_sids"]:
        raise RunnerAttestationError("agent token carries Administrators")
    image = identity["image"]
    if os.path.normcase(image) != os.path.normcase(receipt["harness_exe_path"]):
        raise RunnerAttestationError("live executable path differs from receipt")
    if digest_file(Path(image)) != request["frozen_harness_sha256"]:
        raise RunnerAttestationError("harness digest differs from frozen snapshot")
    verify_ledger_inaccessible(Path(ledger_root or home), identity["user_sid"],
                               identity["group_sids"])
    result = {"attested": not test_seam, "user_sid": identity["user_sid"],
              "groups": sorted(identity["group_sids"]), "image": image,
              "start_time": identity["start_time"],
              "manifest_provenance": "anchored_task_home"}
    if test_seam:
        result["test_seam"] = True
        result["note"] = ("identity probe was a test substitute; attestation is "
                          "simulated and must never be treated as production trust")
    return result


def verify_receipt_integrity(*, receipt: dict, request: dict, home: Path,
                             capture_dir: Path | str | None = None) -> dict:
    """POST-EXIT receipt verification: structure, full request cross-binding,
    anchored task-home manifest echo and capture-digest re-hash from
    orchestrator-owned storage.

    S2B1F-002 semantics: this function certifies L1+L2 (and, via the home
    read, L3 provenance of the manifest) - it NEVER certifies L4.
    ``attested``/``runner_identity_attested`` are structurally False: a
    receipt for an exited process can only ever be integrity-verified;
    self-consistent fabricated files outside the protected home cannot pass
    the anchored manifest read, and passing integrity does not mean any
    runner identity was ever verified (S2B1-003 boundary).
    """
    validate_launch_request(request)
    validate_receipt(receipt, request)
    manifest = _read_anchored_manifest(Path(home), request["task_id"])
    expected_manifest = manifest_sha256(manifest)
    if receipt["runner_manifest_sha256"] != expected_manifest:
        raise RunnerAttestationError(
            "receipt was issued under a different runner manifest")
    if capture_dir is None:
        raise RunnerAttestationError(
            "capture re-hash unavailable: no orchestrator-owned capture_dir "
            "provided; receipt stays UNVERIFIED (fail closed)")
    root = Path(capture_dir)
    run_id = request["run_id"]
    for suffix, key in (("stdout.bin", "stdout_sha256"),
                        ("stderr.bin", "stderr_sha256"),
                        ("capture-meta.json", "capture_meta_sha256")):
        path = root / f"{run_id}.{suffix}"
        if not path.is_file():
            raise RunnerAttestationError(f"capture file missing: {path.name}")
        if digest_file(path) != receipt[key]:
            raise RunnerAttestationError(
                f"capture digest mismatch for {path.name}")
    return {"integrity_verified": True, "attested": False,
            "runner_identity_attested": False,
            "manifest_provenance": "anchored_task_home",
            "levels": {"L1_structure": True, "L2_digests": True,
                       "L3_manifest_anchored": True,
                       "L4_identity_attested": False},
            "note": ("post-exit integrity only: structure, binding, anchored "
                     "manifest echo and capture re-hash; NOT a runner identity "
                     "attestation and no path here can produce trusted "
                     "execution evidence (S2B1-009 closure)")
            }


_ACL_QUERY_MULTI = r'''
$ErrorActionPreference='Stop'
$paths = Get-Content -LiteralPath $env:P1_ACL_PATHS -Encoding UTF8 | ConvertFrom-Json
$out = @()
foreach($p in $paths){
  $acl=Get-Acl -LiteralPath $p
  $sids=@()
  foreach($rule in $acl.GetAccessRules($true,$true,[System.Security.Principal.SecurityIdentifier])){
    if($rule.AccessControlType -eq 'Allow'){$sids+=$rule.IdentityReference.Value}
  }
  $out += [pscustomobject]@{ path=$p; principals=@($sids|Select-Object -Unique) }
}
ConvertTo-Json -InputObject $out -Compress -Depth 4
'''


def _ledger_check_paths(ledger_root: Path) -> list:
    """Bounded enumeration: the root, the SQLite files (incl. live WAL/SHM)
    and the evidence directories. Missing optional files are skipped; the
    root must always exist."""
    root = Path(ledger_root)
    if not root.exists():
        raise RunnerAttestationError(f"ledger root missing: {root}")
    paths = [root]
    for name in ("state.sqlite", "state.sqlite-wal", "state.sqlite-shm"):
        candidate = root / name
        if candidate.exists():
            paths.append(candidate)
    for name in ("logs", "snapshots", "artifacts", "audit_evidence"):
        candidate = root / name
        if candidate.exists():
            paths.append(candidate)
    return paths


def _effective_allow_principals_many(paths: list) -> list:
    if os.name != "nt":
        raise RunnerUnavailableError("DACL query is Windows-only")
    import base64
    import json as _json
    import tempfile
    payload = _json.dumps([str(p) for p in paths]).encode("utf-8")
    with tempfile.NamedTemporaryFile("wb", suffix=".json", delete=False) as fh:
        fh.write(payload)
        list_path = fh.name
    try:
        env = dict(os.environ)
        env["P1_ACL_PATHS"] = list_path
        result = subprocess.run(
            ["powershell.exe", "-NoProfile", "-NonInteractive",
             "-EncodedCommand",
             base64.b64encode(_ACL_QUERY_MULTI.encode("utf-16le")).decode("ascii")],
            capture_output=True, text=True, errors="replace", timeout=60, env=env)
    finally:
        try:
            os.unlink(list_path)
        except OSError:
            pass
    if result.returncode:
        raise RunnerAttestationError("ledger DACL query failed")
    data = _json.loads(result.stdout)
    if not isinstance(data, list) or len(data) != len(paths):
        raise RunnerAttestationError("ledger DACL query shape invalid")
    for record, path in zip(data, paths):
        if not isinstance(record, dict) or record.get("path") != str(path):
            raise RunnerAttestationError("ledger DACL query path mismatch")
        if not isinstance(record.get("principals"), list):
            raise RunnerAttestationError("ledger DACL query principals invalid")
    return data


def verify_ledger_inaccessible(ledger_root: Path, agent_sid: str,
                               agent_group_sids: list, *, query=None) -> dict:
    """Fail closed unless NO checked ledger path (root, SQLite/WAL/SHM and the
    evidence directories - S2B1-007) carries an effective Allow ACE covering
    the agent user or any of its groups (plus Everyone / Authenticated
    Users). Any query failure raises; a clean result covers ONLY the enumerated
    paths, it does not prove arbitrary future children are unreachable."""
    paths = _ledger_check_paths(Path(ledger_root))
    runner = query or _effective_allow_principals_many
    records = runner(paths)
    if len(records) != len(paths):
        raise RunnerAttestationError("ledger DACL query returned wrong cardinality")
    watched = {agent_sid, *(agent_group_sids or []),
               SID_EVERYONE, SID_AUTHENTICATED_USERS}
    for record in records:
        principals = set(record["principals"])
        leak = sorted((principals & watched) - {SID_LOCAL_SYSTEM})
        if leak:
            raise RunnerAttestationError(
                f"ledger path {record['path']} exposes agent principals: {leak}")
    return {"paths_checked": [str(p) for p in paths]}


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
        for key in ("task_id", "spool_inbox", "spool_outbox",
                    "expected_agent_sid", "runner_exe", "runner_exe_sha256"):
            if not data.get(key):
                raise RunnerUnavailableError(f"runner manifest incomplete: {key}")
        if digest_file(Path(data["runner_exe"])) != data["runner_exe_sha256"]:
            raise RunnerAttestationError("runner executable differs from manifest pin")
        return data

    def runner_health(self) -> dict:
        """Honest health probe (S2B1-006): a provisioned manifest is reported
        as such, but service availability is FALSE until a real runner
        service with a liveness probe exists. Stage-2B-1 has no runner
        service, so this never claims an available runner."""
        if os.name != "nt":
            return {"available": False, "manifest_provisioned": False,
                    "service_liveness": "unknown",
                    "reason": "non-Windows host"}
        try:
            manifest = self.manifest()
            provisioned = True
        except RunnerError as exc:
            return {"available": False, "manifest_provisioned": False,
                    "service_liveness": "unknown",
                    "reason": f"manifest not usable: {exc}"[:200]}
        return {"available": False,
                "manifest_provisioned": provisioned,
                "expected_agent_sid": manifest["expected_agent_sid"],
                "service_liveness": "unknown",
                "reason": ("no runner service liveness probe exists in "
                           "Stage-2B-1; runner service is NOT deployed and "
                           "real execution stays blocked")}

    def launch(self, request: dict, stdin_text: str) -> dict:
        """Stage-2B-1: always refuses. When a runner exists, the future path
        writes request.json into the inbox (never outbox), waits, then
        validates + attests. Re-issues for the same run_id are refused: the
        ledger already contains an execution_dispatched intent (P1 semantics)
        and ambiguous dispatch is reconciliation-only."""
        validate_launch_request(request)
        health = self.runner_health()
        if health["available"]:
            raise RunnerUnavailableError("runner transport not implemented in Stage-2B-1")
        raise RunnerUnavailableError(
            f"runner not available: {health['reason']}")

    def poll(self, request: dict) -> dict:
        """Read the spool WITHOUT ever trusting it blindly (S2B1-005): a
        receipt from the outbox is structurally validated and cross-bound
        here; anything that fails validation comes back as RECEIPT_UNVERIFIED
        with reconciliation_required=True and must never be treated as final
        trusted evidence. Provenance of the outbox writer is still only
        ACL-based (Stage-2B-2 provisioning)."""
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
            receipt = read_json(receipt_path)
            try:
                validate_receipt(receipt, request)
                if receipt["runner_manifest_sha256"] != manifest_sha256(manifest):
                    raise RunnerAttestationError(
                        "receipt runner manifest digest mismatch")
            except (RunnerAttestationError, ValueError, TypeError) as exc:
                return {"state": "RECEIPT_UNVERIFIED", "receipt": receipt,
                        "validated": False, "reconciliation_required": True,
                        "reason": str(exc)[:300]}
            return {"state": "RECEIPT", "receipt": receipt, "validated": True,
                    "reconciliation_required": False}
        if request_path.is_file():
            return {"state": "DISPATCHED", "dispatched_at":
                    read_json(request_path).get("written_at")}
        return {"state": "NOT_DISPATCHED", "dispatched": None}
