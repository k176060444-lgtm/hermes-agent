"""``post_gateway_admission``: let a plugin consume an admitted inbound message (#129958).

``GatewayInboundMixin._handle_message`` fires it once per non-internal message that survived
authorization, bot admission, pause/drain, pending-reply intercepts, the running-session lane and
idle slash-command dispatch, inside the claimed session slot. It runs under the message's ROUTED
profile scope: the receiving bot's handler binds the transport home (auth reads its ``.env``), which
differs from the runtime home when that bot serves a chat for another profile.

Fail-open: a callback that raises, times out or returns anything other than
``{"action": "handled"}`` is logged/ignored and the message proceeds to the agent, so one buggy
plugin can never blackhole a profile's traffic. The payload is a plain snapshot, never live
runner/session-store handles.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
from typing import Any, Optional, Tuple

logger = logging.getLogger(__name__)

POST_ADMISSION_HOOK = "post_gateway_admission"
R25_BUSY_HOOK = "r25_qq_busy_confirmation"


def _routed_scope(runner: Any, source: Any):
    if not getattr(getattr(runner, "config", None), "multiplex_profiles", False):
        return contextlib.nullcontext()
    from gateway.run import _async_profile_runtime_scope
    return _async_profile_runtime_scope(runner._resolve_profile_home_for_source(source))


async def run_post_admission_hook(
    runner: Any, event: Any, source: Any, session_key: str,
    *, hook_name: str = POST_ADMISSION_HOOK
) -> tuple[bool, Optional[str]]:
    """Return ``(handled, reply)``; unhandled leaves the original idle/busy route unchanged.

    The busy variant uses a dedicated R25 hook instead of dispatching all
    post_gateway_admission plugins into an in-flight Agent message.
    """
    try:
        async with _routed_scope(runner, source):
            from hermes_cli.lifecycle import ainvoke_hook, has_hook
            if hook_name not in (POST_ADMISSION_HOOK, R25_BUSY_HOOK):
                return False, None
            if not has_hook(hook_name):
                return False, None
            results = await ainvoke_hook(
                hook_name, session_key=session_key,
                platform=source.platform.value if source.platform else "",
                source=source.to_dict(), message_id=event.message_id, text=event.text or "",
            )
    except asyncio.CancelledError:
        raise
    except Exception:
        logger.warning("%s failed; continuing with the normal message path", hook_name, exc_info=True)
        return False, None
    for result in results:
        if isinstance(result, dict) and result.get("action") == "handled":
            reply = result.get("reply")
            logger.info("%s: a plugin handled the message for session %s", hook_name, session_key)
            return True, reply if isinstance(reply, str) and reply.strip() else None
    return False, None
