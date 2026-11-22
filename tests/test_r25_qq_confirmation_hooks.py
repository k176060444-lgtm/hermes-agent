"""Isolated R25 dual-hook QQ confirmation tests (no QQ connection or signer)."""
import unittest
from integrations.e32b_r25.hermes_plugin.bridge import R25QQHookBridge
from integrations.e32b_r25.hermes_plugin import register
from gateway.run_inbound_consumer import run_post_admission_hook
from gateway.session import SessionSource
from gateway.config import Platform
from types import SimpleNamespace
from unittest.mock import patch, AsyncMock

OPENID = "qq-user-01"
SESSION = "agent:main:qqbot:dm:" + OPENID


def source():
    return {"user_id": OPENID, "chat_id": OPENID, "chat_type": "dm"}


def capture(bridge, *, message_id="qq-msg-01", text="批准",
            chat_type="dm", user_id=OPENID):
    bridge.on_gateway_platform_event(
        platform="qqbot", event_type="message",
        payload={"user_id": user_id, "chat_id": user_id,
                 "chat_type": chat_type, "message_id": message_id,
                 "text": text, "received_at_ms": 1795310000000})


class R25QQDualHookTests(unittest.IsolatedAsyncioTestCase):
    async def test_admitted_raw_approval_is_consumed_with_direct_reply(self):
        calls = []
        async def service(event):
            calls.append(event)
            return {"status": "PUBLISHED_START_REQUESTED",
                    "qqMessage": "已提交，但 Init 尚未确认"}
        b = R25QQHookBridge(service=service)
        capture(b)
        result = await b.on_post_gateway_admission(
            session_key=SESSION, platform="qqbot", source=source(),
            message_id="qq-msg-01", text="引用：别人的批准")
        self.assertEqual(result, {"action": "handled", "reply": "已提交，但 Init 尚未确认"})
        self.assertEqual(calls[0]["payload"]["text"], "批准")
        # One admitted message cannot reuse the same captured event.
        second = await b.on_post_gateway_admission(
            session_key=SESSION, platform="qqbot", source=source(),
            message_id="qq-msg-01", text="批准")
        self.assertIsNone(second)
        self.assertEqual(len(calls), 1)

    async def test_session_role_user_without_raw_event_is_never_approval(self):
        called = []
        async def service(event):
            called.append(event)
            return {"status": "PUBLISHED_START_REQUESTED", "qqMessage": "ok"}
        b = R25QQHookBridge(service=service)
        result = await b.on_post_gateway_admission(
            session_key=SESSION, platform="qqbot", source=source(),
            message_id="synthetic-session-id", text="批准")
        self.assertIsNone(result)
        self.assertEqual(called, [])

    async def test_group_and_mismatched_identity_are_ignored(self):
        called = []
        async def service(event):
            called.append(event)
            return {"status": "PUBLISHED_START_REQUESTED", "qqMessage": "ok"}
        b = R25QQHookBridge(service=service)
        capture(b, chat_type="group")
        self.assertIsNone(await b.on_post_gateway_admission(
            session_key=SESSION, platform="qqbot", source=source(),
            message_id="qq-msg-01", text="批准"))
        capture(b, message_id="qq-msg-02")
        wrong = {"user_id": OPENID, "chat_id": OPENID, "chat_type": "group"}
        self.assertIsNone(await b.on_post_gateway_admission(
            session_key=SESSION, platform="qqbot", source=wrong,
            message_id="qq-msg-02", text="批准"))
        self.assertEqual(called, [])

    async def test_unrelated_non_pending_conversation_is_not_swallowed(self):
        calls = []
        async def service(event):
            calls.append(event)
            return {"status": "NO_MATCHING_PENDING", "qqMessage": None}
        b = R25QQHookBridge(service=service)
        capture(b, text="好")
        result = await b.on_post_gateway_admission(
            session_key=SESSION, platform="qqbot", source=source(),
            message_id="qq-msg-01", text="好")
        self.assertIsNone(result)
        self.assertEqual(len(calls), 1)

    async def test_service_fails_closed_without_false_reply(self):
        async def broken(event):
            raise RuntimeError("signer unavailable")
        b = R25QQHookBridge(service=broken)
        capture(b)
        result = await b.on_post_gateway_admission(
            session_key=SESSION, platform="qqbot", source=source(),
            message_id="qq-msg-01", text="批准")
        self.assertIsNone(result)

    async def test_first_raw_payload_wins_over_replayed_event(self):
        captured = []
        async def service(event):
            captured.append(event)
            return {"status": "MULTIPLE_PENDING_NEED_TASK_ID"}
        b = R25QQHookBridge(service=service)
        capture(b, text="不批准")
        capture(b, text="批准")
        result = await b.on_post_gateway_admission(
            session_key=SESSION, platform="qqbot", source=source(),
            message_id="qq-msg-01", text="批准")
        self.assertEqual(result["action"], "handled")
        self.assertEqual(captured[0]["payload"]["text"], "不批准")

    async def test_source_plugin_registers_both_hooks_without_agent_approval_tool(self):
        class FakeCtx:
            def __init__(self): self.calls = []
            def register_hook(self, name, callback): self.calls.append((name, callback))
        ctx = FakeCtx()
        register(ctx)
        self.assertEqual([name for name, _ in ctx.calls],
                         ["gateway_platform_event", "post_gateway_admission",
                          "r25_qq_busy_confirmation"])
        self.assertTrue(all(callable(cb) for _, cb in ctx.calls))


    async def test_real_gateway_post_admission_runner_consumes_hook_reply(self):
        class Runner:
            config = SimpleNamespace(multiplex_profiles=False)
        runner = Runner()
        origin = SessionSource(platform=Platform.QQBOT,chat_id=OPENID,
                               chat_type="dm",user_id=OPENID)
        event = SimpleNamespace(message_id="real-qq-id",text="扩展引用：别人说批准")
        async_hook = AsyncMock(return_value=[{"action": "handled", "reply": "确认已发布，尚未验证 Init"}])
        with (patch("hermes_cli.lifecycle.has_hook", return_value=True),
              patch("hermes_cli.lifecycle.ainvoke_hook", async_hook)):
            consumed, reply = await run_post_admission_hook(runner,event,origin,SESSION)
        self.assertTrue(consumed)
        self.assertEqual(reply, "确认已发布，尚未验证 Init")
        self.assertEqual(async_hook.await_args.args[0], "post_gateway_admission")
        self.assertEqual(async_hook.await_args.kwargs["session_key"],SESSION)

    async def test_real_gateway_post_admission_keeps_normal_turn_if_unhandled(self):
        class Runner:
            config = SimpleNamespace(multiplex_profiles=False)
        runner = Runner()
        origin = SessionSource(platform=Platform.QQBOT,chat_id=OPENID,
                               chat_type="dm",user_id=OPENID)
        event = SimpleNamespace(message_id="real-qq-id",text="普通消息")
        with (patch("hermes_cli.lifecycle.has_hook",return_value=True),
              patch("hermes_cli.lifecycle.ainvoke_hook",AsyncMock(return_value=[None]))):
            consumed,reply=await run_post_admission_hook(runner,event,origin,SESSION)
        self.assertFalse(consumed)
        self.assertIsNone(reply)

    async def test_unconfigured_plugin_does_not_consume_any_message(self):
        b = R25QQHookBridge()
        capture(b)
        self.assertIsNone(await b.on_post_gateway_admission(
            session_key=SESSION, platform="qqbot", source=source(),
            message_id="qq-msg-01", text="批准"))


if __name__ == "__main__":
    unittest.main()
