"""E32B R25 QQ confirmation plugin. Inert unless operator explicitly opts in."""
from __future__ import annotations
import os
from .bridge import R25QQHookBridge


def create_opt_in_backend():
    # Source-only wiring. Enabling the environment variable is NOT a production
    # approval and does not authenticate same-user IPC. Provision a dedicated
    # signer, verify the pipe identity/ACL and install R24 assets first.
    if os.name != "nt" or os.environ.get("E32B_R25_SERVICE_APPROVED") != "1":
        return None
    from .backend import R25SignerPublisherBackend
    from .transport import NamedPipeSignerClient, PinnedR24Publisher
    return R25SignerPublisherBackend(NamedPipeSignerClient(), PinnedR24Publisher())


def register(ctx):
    # No model-facing approval tool; the two hooks share exactly one QQ
    # original-message correlation cache, then call the same backend.
    bridge = R25QQHookBridge(service=create_opt_in_backend())
    ctx.register_hook("gateway_platform_event", bridge.on_gateway_platform_event)
    ctx.register_hook("post_gateway_admission", bridge.on_post_gateway_admission)
    ctx.register_hook("r25_qq_busy_confirmation", bridge.on_post_gateway_admission)
