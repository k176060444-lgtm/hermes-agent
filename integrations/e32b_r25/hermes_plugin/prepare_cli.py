"""Operator-provisioned R25 PREPARE entry point. Never signs or publishes.

Accepts a pre-validated R24 E32B_REQUEST_V1 proposal plus QQ route from
stdin, then registers a pending confirmation with the isolated signer.
The returned qqMessage is for Hermes to show to the real user.
"""
from __future__ import annotations
import json
import os
import sys
from .transport import prepare_pending_once

_LIMIT = 1_048_576

def main() -> int:
    if sys.argv[1:] != ["--prepare"] or os.name != "nt":
        print("R25_PREPARE_USAGE_INVALID",file=sys.stderr)
        return 2
    if os.environ.get("E32B_R25_SERVICE_APPROVED") != "1":
        print("R25_SERVICE_NOT_PROVISIONED",file=sys.stderr)
        return 32
    try:
        raw = sys.stdin.buffer.read(_LIMIT + 1)
        if len(raw) > _LIMIT or not raw:
            raise ValueError("R25_PREPARE_REQUEST_SIZE_INVALID")
        proposal = json.loads(raw.decode("utf-8"))
        if not isinstance(proposal,dict):
            raise ValueError("R25_PREPARE_REQUEST_INVALID")
        result=prepare_pending_once(proposal)
        if (not isinstance(result,dict) or
            result.get("schema")!="E32B_R25_SIGNER_PREPARE_V1" or
            result.get("status")!="WAIT_USER_CONFIRMATION" or
            not isinstance(result.get("qqMessage"),str)):
            raise ValueError("R25_PREPARE_RESPONSE_INVALID")
        print(json.dumps(result,ensure_ascii=False,separators=(",",":")))
        return 0
    except Exception:
        print("R25_PREPARE_FAILED",file=sys.stderr)
        return 35

if __name__=="__main__":
    raise SystemExit(main())
