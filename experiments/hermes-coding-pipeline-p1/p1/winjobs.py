"""Windows Job Object wrapper: bounded descendant-process lifecycle.

The trusted Runner puts every Harness Agent tree into a per-run Job Object so
timeout/cancel/abandonment terminates the FULL descendant tree, not only the
direct child (closing the R2-008 residual). Windows only; on other platforms
every entry point fails closed with NotImplementedError.
"""
from __future__ import annotations

import ctypes
import os
from ctypes import wintypes
from pathlib import Path

from .runner import RunnerAttestationError, RunnerUnavailableError

_JOB_OBJECT_EXTENDED_LIMIT_INFORMATION = 9
_JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE = 0x00002000
_PROCESS_SET_QUOTA = 0x0100
_PROCESS_TERMINATE = 0x0001
_STILL_ACTIVE = 259


class _IO_COUNTERS(ctypes.Structure):
    _fields_ = [("ReadOperationCount", ctypes.c_ulonglong),
                ("WriteOperationCount", ctypes.c_ulonglong),
                ("OtherOperationCount", ctypes.c_ulonglong),
                ("ReadTransferCount", ctypes.c_ulonglong),
                ("WriteTransferCount", ctypes.c_ulonglong),
                ("OtherTransferCount", ctypes.c_ulonglong)]


class _BasicLimitInformation(ctypes.Structure):
    _fields_ = [("PerProcessUserTimeLimit", ctypes.c_longlong),
                ("PerJobUserTimeLimit", ctypes.c_longlong),
                ("LimitFlags", wintypes.DWORD),
                ("MinimumWorkingSetSize", ctypes.c_size_t),
                ("MaximumWorkingSetSize", ctypes.c_size_t),
                ("ActiveProcessLimit", wintypes.DWORD),
                ("Affinity", ctypes.c_size_t),
                ("PriorityClass", wintypes.DWORD),
                ("SchedulingClass", wintypes.DWORD)]


class _ExtendedLimitInformation(ctypes.Structure):
    _fields_ = [("BasicLimitInformation", _BasicLimitInformation),
                ("IoInfo", _IO_COUNTERS),
                ("ProcessMemoryLimit", ctypes.c_size_t),
                ("JobMemoryLimit", ctypes.c_size_t),
                ("PeakProcessMemoryUsed", ctypes.c_size_t),
                ("JobPeakMemoryUsed", ctypes.c_size_t)]


def _require_nt() -> None:
    if os.name != "nt":
        raise NotImplementedError("Job Objects are Windows-only")


def _kernel():
    from .runner import _api
    kernel, _ = _api()
    import ctypes
    from ctypes import wintypes
    if not getattr(kernel, "_p1_jobs_configured", False):
        kernel.CreateJobObjectW.restype = wintypes.HANDLE
        kernel.CreateJobObjectW.argtypes = [ctypes.c_void_p, wintypes.LPCWSTR]
        kernel.SetInformationJobObject.restype = wintypes.BOOL
        kernel.SetInformationJobObject.argtypes = [wintypes.HANDLE, ctypes.c_int,
                                                   ctypes.c_void_p, wintypes.DWORD]
        kernel.AssignProcessToJobObject.restype = wintypes.BOOL
        kernel.AssignProcessToJobObject.argtypes = [wintypes.HANDLE, wintypes.HANDLE]
        kernel.TerminateJobObject.restype = wintypes.BOOL
        kernel.TerminateJobObject.argtypes = [wintypes.HANDLE, wintypes.UINT]
        kernel.GetExitCodeProcess.restype = wintypes.BOOL
        kernel.GetExitCodeProcess.argtypes = [wintypes.HANDLE,
                                              ctypes.POINTER(wintypes.DWORD)]
        kernel.CreateProcessW.restype = wintypes.BOOL
        kernel.CreateProcessW.argtypes = [
            wintypes.LPCWSTR, wintypes.LPWSTR, ctypes.c_void_p, ctypes.c_void_p,
            wintypes.BOOL, wintypes.DWORD, ctypes.c_void_p, wintypes.LPCWSTR,
            ctypes.c_void_p, ctypes.c_void_p]
        kernel.ResumeThread.restype = wintypes.DWORD
        kernel.ResumeThread.argtypes = [wintypes.HANDLE]
        kernel.TerminateProcess.restype = wintypes.BOOL
        kernel.TerminateProcess.argtypes = [wintypes.HANDLE, wintypes.UINT]
        kernel.WaitForSingleObject.restype = wintypes.DWORD
        kernel.WaitForSingleObject.argtypes = [wintypes.HANDLE, wintypes.DWORD]
        kernel._p1_jobs_configured = True
    return kernel


class _StartupInfoW(ctypes.Structure):
    _fields_ = [("cb", wintypes.DWORD),
                ("lpReserved", wintypes.LPWSTR),
                ("lpDesktop", wintypes.LPWSTR),
                ("lpTitle", wintypes.LPWSTR),
                ("dwX", wintypes.DWORD),
                ("dwY", wintypes.DWORD),
                ("dwXSize", wintypes.DWORD),
                ("dwYSize", wintypes.DWORD),
                ("dwXCountChars", wintypes.DWORD),
                ("dwYCountChars", wintypes.DWORD),
                ("dwFillAttribute", wintypes.DWORD),
                ("dwFlags", wintypes.DWORD),
                ("wShowWindow", wintypes.WORD),
                ("cbReserved2", wintypes.WORD),
                ("lpReserved2", ctypes.c_void_p),
                ("hStdInput", wintypes.HANDLE),
                ("hStdOutput", wintypes.HANDLE),
                ("hStdError", wintypes.HANDLE)]


class _ProcessInformation(ctypes.Structure):
    _fields_ = [("hProcess", wintypes.HANDLE),
                ("hThread", wintypes.HANDLE),
                ("dwProcessId", wintypes.DWORD),
                ("dwThreadId", wintypes.DWORD)]


CREATE_SUSPENDED = 0x00000004
_CREATE_UNICODE_ENV = 0x00000400
_STILL_ACTIVE = 259
_INVALID_HANDLE = ctypes.c_void_p(-1).value or 0


def _quote_command(argv: list) -> str:
    import subprocess as _sp
    return _sp.list2cmdline([str(a) for a in argv])


def create_suspended_in_job(job, argv: list, *, cwd: str | None = None) -> int:
    """Spawn ``argv`` CREATE_SUSPENDED, assign it to ``job`` BEFORE its first
    instruction runs, then resume. Any failure along the way kills the
    suspended process and raises - the escape window of spawn-then-assign
    (audit S2B1-016) is structurally closed because the process cannot create
    descendants while suspended. NOTE: this helper runs the child under the
    CALLER's identity; the dedicated agentx-identity launch path
    (CreateProcessWithLogonW + pinned credentials) remains a Stage-2B-2
    provisioning item and stays fail-closed/unimplemented."""
    _require_nt()
    kernel = _kernel()
    command_line = _quote_command(argv)
    si = _StartupInfoW()
    si.cb = ctypes.sizeof(si)
    pi = _ProcessInformation()
    created = kernel.CreateProcessW(
        None, ctypes.create_unicode_buffer(command_line), None, None, False,
        CREATE_SUSPENDED | _CREATE_UNICODE_ENV, None,
        ctypes.create_unicode_buffer(cwd) if cwd else None,
        ctypes.byref(si), ctypes.byref(pi))
    if not created:
        raise RunnerAttestationError(
            f"CreateProcessW(CREATE_SUSPENDED) failed for {argv[0]!r}")
    pid = int(pi.dwProcessId)
    try:
        if not kernel.AssignProcessToJobObject(job.handle, pi.hProcess):
            raise RunnerAttestationError(
                f"AssignProcessToJobObject failed for pid {pid}")
        if kernel.ResumeThread(pi.hThread) == 0xFFFFFFFF:
            raise RunnerAttestationError(f"ResumeThread failed for pid {pid}")
    except BaseException:
        kernel.TerminateProcess(pi.hProcess, 1)
        kernel.CloseHandle(pi.hThread)
        kernel.CloseHandle(pi.hProcess)
        raise
    kernel.CloseHandle(pi.hThread)
    kernel.CloseHandle(pi.hProcess)
    return pid


class Job:
    """One named kernel job with KILL_ON_JOB_CLOSE semantics."""

    def __init__(self, name: str):
        _require_nt()
        if not name:
            raise ValueError("job name required")
        kernel = _kernel()
        self.handle = kernel.CreateJobObjectW(None, name)
        if not self.handle:
            raise RunnerAttestationError(f"CreateJobObjectW failed for {name}")
        info = _ExtendedLimitInformation()
        info.BasicLimitInformation.LimitFlags = _JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
        ok = kernel.SetInformationJobObject(
            self.handle, _JOB_OBJECT_EXTENDED_LIMIT_INFORMATION,
            ctypes.byref(info), ctypes.sizeof(info))
        if not ok:
            kernel.CloseHandle(self.handle)
            self.handle = None
            raise RunnerAttestationError("SetInformationJobObject failed")

    def assign_pid(self, pid: int) -> None:
        _require_nt()
        kernel = _kernel()
        hproc = kernel.OpenProcess(_PROCESS_SET_QUOTA | _PROCESS_TERMINATE, False, pid)
        if not hproc:
            raise RunnerAttestationError(f"cannot open pid {pid} for job assignment")
        try:
            if not kernel.AssignProcessToJobObject(self.handle, hproc):
                raise RunnerAttestationError(f"AssignProcessToJobObject failed for pid {pid}")
        finally:
            kernel.CloseHandle(hproc)

    def terminate(self) -> None:
        _require_nt()
        kernel = _kernel()
        if not kernel.TerminateJobObject(self.handle, 1):
            raise RunnerAttestationError("TerminateJobObject failed")

    def close(self) -> None:
        if getattr(self, "handle", None):
            kernel = _kernel()
            kernel.CloseHandle(self.handle)  # kills members via KILL_ON_JOB_CLOSE
            self.handle = None


def process_alive(pid: int, timeout_seconds: float = 2.0) -> bool:
    _require_nt()
    kernel = _kernel()
    hproc = kernel.OpenProcess(0x1000, False, pid)  # QUERY_LIMITED_INFORMATION
    if not hproc:
        return False
    try:
        code = wintypes.DWORD()
        if not kernel.GetExitCodeProcess(hproc, ctypes.byref(code)):
            return False
        return code.value == _STILL_ACTIVE
    finally:
        kernel.CloseHandle(hproc)
