"""R25 plugin registration. Source package is NOT auto-installed into Hermes."""
from .bridge import R25QQHookBridge

def register(ctx):
    # Disabled without a separately provisioned, authenticated service.
    # The Agent cannot register a "sign this text" tool through this plugin.
    bridge = R25QQHookBridge(service=None)
    ctx.register_hook("gateway_platform_event", bridge.on_gateway_platform_event)
    ctx.register_hook("post_gateway_admission", bridge.on_post_gateway_admission)
