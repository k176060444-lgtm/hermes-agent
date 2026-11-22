"""R26 reusable 21bao QQ confirmation plugin for any Hermes profile.

No separate Windows Signer/Pipe, no hardcoded QQ user ID or profile.
Inert until explicitly enabled in the approved Gateway host deployment.
"""
from __future__ import annotations
import os

from integrations.e32b_r25.hermes_plugin.bridge import R25QQHookBridge


def create_opt_in_backend():
    if os.name != "nt" or os.environ.get("E32B_R26_GATEWAY_APPROVED") != "1":
        return None
    from .local_backend import R26GatewayLocalBackend
    return R26GatewayLocalBackend()


def register(ctx):
    # The Gateway's existing busy hook name remains fixed across profiles.
    # Do NOT register the superseded R25 plugin at the same time.
    # R26 local subprocess may need up to 25s; Gateway must not time out
    # first and route a real approval reply back into the LLM turn.
    bridge = R25QQHookBridge(service=create_opt_in_backend(),
                             service_timeout_seconds=30.0)
    ctx.register_hook("gateway_platform_event", bridge.on_gateway_platform_event)
    ctx.register_hook("post_gateway_admission", bridge.on_post_gateway_admission)
    ctx.register_hook("r25_qq_busy_confirmation", bridge.on_post_gateway_admission)
