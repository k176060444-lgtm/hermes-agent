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
# DEF-01: a configuration defect must never be reported as a submission
# uncertainty (that would fake "a claim may have been consumed") and must
# never hijack an ordinary QQ conversation. These codes mean "nothing was
# consumed; treat the message as having no matching pending".
_CONFIG_MISSING_CODES = (
    "R26_GATEWAY_CLI_NOT_CONFIGURED",
    "R26_GATEWAY_CLI_PATH_UNEXPECTED",
    "R26_GATEWAY_NOT_ENABLED",
    "R26_GATEWAY_WINDOWS_REQUIRED",
    "R26_NODE_OVERRIDE_INVALID",
)


def _resolve_node_exe(env: dict | None = None) -> str:
    """DEF-06: controlled host override of the pinned Node executable.

    The default pin is unchanged for existing security tests. An override is
    accepted only when it is an absolute path whose executable name is in the
    whitelist; anything else fails closed.
    """
    env = os.environ if env is None else env
    value = env.get("E32B_R26_NODE_EXE", "")
    if not value:
        return NODE_EXE
    path = Path(value)
    if not path.is_absolute() or path.name.lower() not in ("node.exe", "node"):
        raise RuntimeError("R26_NODE_OVERRIDE_INVALID")
    return value


def _pending_db_path(env: dict | None = None) -> Path | None:
    """Host-level Pending SQLite location (mirrors host-key.mjs gatewayStatePaths)."""
    env = os.environ if env is None else env
    appdata = env.get("LOCALAPPDATA", "")
    if not isinstance(appdata, str) or not appdata:
        return None
    return Path(appdata) / "Paseo" / "E32B-R26" / "pending.sqlite"


def _configured_cli() -> str:
    # Host-level release configuration, common to all profiles. Not an
    # Agent/proposal-controlled command path; installer pins source/hash.
    value = os.environ.get("E32B_R26_GATEWAY_CLI", "")
    if not isinstance(value, str) or not value or not Path(value).is_absolute():
        raise RuntimeError("R26_GATEWAY_CLI_NOT_CONFIGURED")
    if not value.lower().endswith(r"\07-development\r26\gateway-local-cli.mjs"):
        raise RuntimeError("R26_GATEWAY_CLI_PATH_UNEXPECTED")
    return value


def invoke_local_gateway(op: str, payload: dict, *, platform: str | None = None) -> dict:
    if (platform or os.name) != "nt":
        raise RuntimeError("R26_GATEWAY_WINDOWS_REQUIRED")
    if os.environ.get("E32B_R26_GATEWAY_APPROVED") != "1":
        raise RuntimeError("R26_GATEWAY_NOT_ENABLED")
    if op not in _OP_SCHEMAS or not isinstance(payload, dict):
        raise ValueError("R26_GATEWAY_VERB_OR_PAYLOAD_INVALID")
    raw = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    if not raw or len(raw) > _MAX_WIRE:
        raise ValueError("R26_GATEWAY_INPUT_TOO_LARGE")
    node_exe = _resolve_node_exe()
    if op == "--confirm":
        pending_db = _pending_db_path()
        if pending_db is None or not pending_db.is_file():
            # DEF-01: without a Pending store nothing was ever registered or
            # consumed — a plain private chat must pass through untouched.
            return {"schema": _OP_SCHEMAS[op], "status": "NO_MATCHING_PENDING",
                    "qqMessage": None}
    proc = subprocess.run(
        [node_exe, _configured_cli(), op],
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
        except Exception as exc:
            text = str(exc)
            if any(code in text for code in _CONFIG_MISSING_CODES):
                # DEF-01: configuration defects consumed nothing; answer
                # honestly so the ordinary message flow is not hijacked.
                return {"status": "NO_MATCHING_PENDING", "qqMessage": None}
            # A claim might have been durably consumed before output was lost.
            # Never auto-retry one user confirmation or one R24 publication.
            return {"status": "SUBMISSION_UNCERTAIN",
                    "qqMessage": "确认结果不确定，请先查询任务状态，禁止自动重复提交。"}
        return result
