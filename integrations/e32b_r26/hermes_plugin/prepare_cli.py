"""Shared R26 PREPARE entrypoint. Runs on the originating Hermes Agent turn.

The request includes that Agent's actual runtime Gateway session_key and
qqbot source route. Node persists Pending and later confirms ONLY when its
Gateway post-admission hook sees a matching original QQ message. This
CLI cannot approve or sign a request by itself.
"""
from __future__ import annotations
import json
import os
import sys
from .local_backend import prepare_local_pending

_MAX = 1_048_576

def main() -> int:
    if sys.argv[1:] != ["--prepare"] or os.name != "nt":
        print("R26_PREPARE_USAGE_INVALID", file=sys.stderr)
        return 2
    if os.environ.get("E32B_R26_GATEWAY_APPROVED") != "1":
        print("R26_GATEWAY_NOT_ENABLED", file=sys.stderr)
        return 32
    try:
        data=sys.stdin.buffer.read(_MAX+1)
        if not data or len(data)>_MAX:
            raise ValueError("R26_PREPARE_INPUT_SIZE_INVALID")
        proposal=json.loads(data.decode("utf-8"))
        if not isinstance(proposal,dict):
            raise ValueError("R26_PREPARE_INPUT_INVALID")
        result=prepare_local_pending(proposal)
        if (result.get("schema")!="E32B_R26_GATEWAY_PREPARE_V1" or
                result.get("status")!="WAIT_USER_CONFIRMATION" or
                not isinstance(result.get("qqMessage"),str) or
                not result["qqMessage"]):
            raise ValueError("R26_PREPARE_RESPONSE_INVALID")
        print(json.dumps(result,ensure_ascii=False,separators=(",",":")))
        return 0
    except Exception:
        print("R26_PREPARE_FAILED", file=sys.stderr)
        return 35

if __name__=="__main__":
    raise SystemExit(main())
