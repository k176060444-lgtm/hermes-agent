"""One-shot QQ confirmation backend. No secret/key/IPC is created here.

The signer callback MUST be bound to a separately configured and approved
transport and is not a source of QQ provenance. The publisher callback wraps
the unchanged R24 --submit entry; only it can access the KK-owned inbox.
"""
from __future__ import annotations
import base64
import binascii
import re
from typing import Any, Awaitable, Callable

_ID = re.compile(r"^[A-Za-z0-9_-]{4,64}-[a-f0-9]{24}$")
_MAX_SIGNED_WIRE = 1_400_000
_PUBLISHED = frozenset(("PUBLISHED_START_REQUESTED", "PUBLISHED_TRIGGER_BLOCKED"))

class R25SignerPublisherBackend:
    def __init__(self, signer: Callable[[dict], Awaitable[dict]],
                 publisher: Callable[[bytes], Awaitable[dict]]):
        if not callable(signer) or not callable(publisher):
            raise TypeError("R25 signer and publisher callbacks are required")
        self.signer, self.publisher = signer, publisher

    async def __call__(self, event: dict) -> dict:
        # The dual gateway hooks supply this event; THIS code cannot authenticate
        # QQ origin against a hostile same-KK process.
        try:
            outcome = await self.signer(event)
        except Exception:
            # A signer may already have consumed this QQ message.
            return {"status": "SIGNER_OUTCOME_UNCERTAIN"}
        if not isinstance(outcome, dict) or outcome.get("schema") != "E32B_R25_SIGNER_OUTCOME_V1":
            return {"status": "SIGNER_OUTCOME_UNCERTAIN"}
        status = outcome.get("status")
        if status != "SIGNED":
            if "signedEnvelopeBase64" in outcome:
                return {"status": "SIGNER_OUTCOME_UNCERTAIN"}
            if status in ("NO_MATCHING_PENDING", "IGNORED_EVENT", "IGNORED_SOURCE",
                          "STALE_EVENT", "AMBIGUOUS", "REJECT_OR_DEFER",
                          "MULTIPLE_PENDING_NEED_TASK_ID", "MESSAGE_ALREADY_USED",
                          "SIGNING_BLOCKED"):
                return {"status": status, "qqMessage": outcome.get("qqMessage")}
            return {"status": "SIGNER_OUTCOME_UNCERTAIN"}
        request_id, encoded = outcome.get("requestId"), outcome.get("signedEnvelopeBase64")
        if (not isinstance(request_id, str) or not _ID.fullmatch(request_id)
                or not isinstance(encoded, str) or not 0 < len(encoded) <= _MAX_SIGNED_WIRE):
            return {"status": "SIGNER_OUTCOME_UNCERTAIN"}
        try:
            signed_bytes = base64.b64decode(encoded, validate=True)
            if base64.b64encode(signed_bytes).decode("ascii") != encoded:
                raise ValueError("noncanonical Base64")
        except (ValueError, binascii.Error):
            return {"status": "SIGNER_OUTCOME_UNCERTAIN"}
        # No retry: R24 publish may have succeeded even if output was lost.
        try:
            result = await self.publisher(signed_bytes)
        except Exception:
            return {"status": "SUBMISSION_UNCERTAIN", "requestId": request_id}
        if (not isinstance(result, dict)
                or result.get("schema") != "E32B_HERMES_DISPATCH_V1"
                or result.get("requestId") != request_id
                or result.get("publishStatus") != "PUBLISHED_UNTRUSTED"
                or result.get("status") not in _PUBLISHED):
            return {"status": "SUBMISSION_UNCERTAIN", "requestId": request_id}
        return {"status": result["status"], "requestId": request_id,
                "qqMessage": result.get("qqMessage"),
                "nativeInitConfirmed": False, "automaticRetryAllowed": False}
