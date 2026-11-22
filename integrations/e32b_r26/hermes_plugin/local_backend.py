"""R26: one-shot local Node Gateway bridge shared by every 21bao profile.

No P5Signer account, Signer Pipe, Windows password, per-Agent signing key or
fixed QQ OpenID. Gateway's own original-message + admitted-session hook is
the normal source of CONFIRM; same-KK hostile-shell spoofing is NOT prevented.
"""
from __future__ import annotations

import asyncio
import json
import os
import subprocess
from pathlib import Path

NODE_EXE = r"D:\Paseo-pipeline\runtime\node.exe"
_MAX_WIRE = 1_048_576
_MAX_RESPONSE = 1_500_000
_OP_SCHEMAS = {
    "--prepare": "E32B_R26_GATEWAY_PREPARE_V1",
    "--confirm": "E32B_R26_GATEWAY_CONFIRM_V1",
}


def _configured_cli() -> str:
    # Host-level release configuration, common to all profiles. Not an
    # Agent/proposal-controlled command path; installer pins source/hash.
    value = os.environ.get("E32B_R26_GATEWAY_CLI", "")
    if not isinstance(value, str) or not value or not Path(value).is_absolute():
        raise RuntimeError("R26_GATEWAY_CLI_NOT_CONFIGURED")
    if not value.lower().endswith(r"\07-development\r26\gateway-local-cli.mjs"):
        raise RuntimeError("R26_GATEWAY_CLI_PATH_UNEXPECTED")
    return value


def invoke_local_gateway(op: str, payload: dict) -> dict:
    if os.name != "nt":
        raise RuntimeError("R26_GATEWAY_WINDOWS_REQUIRED")
    if os.environ.get("E32B_R26_GATEWAY_APPROVED") != "1":
        raise RuntimeError("R26_GATEWAY_NOT_ENABLED")
    if op not in _OP_SCHEMAS or not isinstance(payload, dict):
        raise ValueError("R26_GATEWAY_VERB_OR_PAYLOAD_INVALID")
    raw = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    if not raw or len(raw) > _MAX_WIRE:
        raise ValueError("R26_GATEWAY_INPUT_TOO_LARGE")
    proc = subprocess.run(
        [NODE_EXE, _configured_cli(), op],
        input=raw, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
        timeout=25, shell=False, check=False,
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0)
    )
    if proc.returncode != 0 or len(proc.stdout) > _MAX_RESPONSE:
        raise RuntimeError("R26_GATEWAY_OUTCOME_UNKNOWN")
    try:
        response = json.loads(proc.stdout.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise RuntimeError("R26_GATEWAY_OUTCOME_UNKNOWN") from exc
    if (not isinstance(response, dict) or
            response.get("schema") != _OP_SCHEMAS[op] or
            not isinstance(response.get("status"), str)):
        raise RuntimeError("R26_GATEWAY_OUTCOME_UNKNOWN")
    return response


def prepare_local_pending(proposal: dict) -> dict:
    return invoke_local_gateway("--prepare", proposal)


class R26GatewayLocalBackend:
    async def __call__(self, admitted_event: dict) -> dict:
        # This is called by R25QQHookBridge AFTER original-event correlation
        # and Gateway authorization. Do not expose as a model-facing tool.
        if not isinstance(admitted_event, dict) or not isinstance(
                admitted_event.get("gateway_session_key"), str):
            return {"status": "SIGNER_OUTCOME_UNCERTAIN"}
        try:
            result = await asyncio.to_thread(invoke_local_gateway,
                                             "--confirm", admitted_event)
        except Exception:
            # A claim might have been durably consumed before output was lost.
            # Never auto-retry one user confirmation or one R24 publication.
            return {"status": "SUBMISSION_UNCERTAIN",
                    "qqMessage": "确认结果不确定，请先查询任务状态，禁止自动重复提交。"}
        return result
