"""Operator-opt-in R25 Windows transport adapters; never used without activation.

The pipe server and dedicated signer identity are NOT created here. Deployment
must verify its ACL / peer provenance separately; KK itself cannot be treated
as a trustworthy QQ authenticator merely because a named pipe exists.
"""
from __future__ import annotations
import asyncio
import json
import os
import struct
import subprocess
from pathlib import Path
from typing import Any

PIPE_PATH = r"\\.\pipe\E32B-R25-Signer"
NODE_EXE = r"D:\Paseo-pipeline\runtime\node.exe"
R24_COMMIT = "bedc7b11b4da6b118c4f4f713c1b3ba5934e4a06"
PRODUCER_CLI = str(
    Path(r"C:\Users\KK\AppData\Local\hermes\hermes-agent\integrations\e32b")
    / R24_COMMIT / "repo" / "07-development" / "R24" / "hermes-entry-cli.mjs"
)
_MAX_WIRE_BYTES = 1_048_576


def _read_exact(handle: Any, size: int) -> bytes:
    import win32file
    chunks = []
    remaining = size
    while remaining:
        result, data = win32file.ReadFile(handle, remaining)
        if result != 0 or not data:
            raise OSError("R25_SIGNER_PIPE_TRUNCATED")
        chunks.append(data)
        remaining -= len(data)
    return b"".join(chunks)


def pipe_exchange_once(request: dict) -> dict:
    if os.name != "nt":
        raise OSError("R25_WINDOWS_PIPE_REQUIRED")
    import win32file
    import win32pipe
    raw = json.dumps(request, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    if len(raw) > _MAX_WIRE_BYTES:
        raise ValueError("R25_PIPE_REQUEST_TOO_LARGE")
    # Server must be provisioned under an independently protected principal.
    # WaitNamedPipe bounds connection acquisition, NOT server read latency.
    win32pipe.WaitNamedPipe(PIPE_PATH, 2000)
    handle = win32file.CreateFile(
        PIPE_PATH, win32file.GENERIC_READ | win32file.GENERIC_WRITE,
        0, None, win32file.OPEN_EXISTING, 0, None)
    try:
        win32file.WriteFile(handle, struct.pack(">I", len(raw)) + raw)
        n = struct.unpack(">I", _read_exact(handle, 4))[0]
        if n < 2 or n > _MAX_WIRE_BYTES:
            raise ValueError("R25_PIPE_RESPONSE_SIZE_INVALID")
        outcome = json.loads(_read_exact(handle, n).decode("utf-8"))
        if not isinstance(outcome, dict):
            raise ValueError("R25_PIPE_RESPONSE_INVALID")
        return outcome
    finally:
        win32file.CloseHandle(handle)


def pipe_request_once(event: dict) -> dict:
    return pipe_exchange_once({"schema": "E32B_R25_SIGNER_IPC_V1",
                               "op": "CONFIRM", "event": event})


def prepare_pending_once(proposal: dict) -> dict:
    return pipe_exchange_once({"schema": "E32B_R25_SIGNER_IPC_V1",
                               "op": "PREPARE", "proposal": proposal})


class NamedPipeSignerClient:
    async def __call__(self, event: dict) -> dict:
        return await asyncio.to_thread(pipe_request_once, event)


def publish_r24_once(signed_bytes: bytes) -> dict:
    if os.name != "nt":
        raise OSError("R25_WINDOWS_R24_REQUIRED")
    if not isinstance(signed_bytes, bytes) or not signed_bytes:
        raise TypeError("R25_CANONICAL_SIGNED_BYTES_REQUIRED")
    # Immutable CLI path and --submit verb. No shell and no caller arguments.
    if not Path(NODE_EXE).is_file() or not Path(PRODUCER_CLI).is_file():
        raise FileNotFoundError("R25_R24_RELEASE_NOT_PROVISIONED")
    result = subprocess.run(
        [NODE_EXE, PRODUCER_CLI, "--submit"], input=signed_bytes,
        stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, timeout=8,
        shell=False, check=False, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    output = json.loads(result.stdout.decode("utf-8"))
    if not isinstance(output, dict) or result.returncode not in (0, 2):
        raise ValueError("R25_R24_RESULT_UNKNOWN")
    return output


class PinnedR24Publisher:
    async def __call__(self, signed_bytes: bytes) -> dict:
        return await asyncio.to_thread(publish_r24_once, signed_bytes)
