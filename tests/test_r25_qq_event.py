"""E32B R25 isolated QQ normalized-message emission regression tests.
No QQ connection, credential, Session DB or production path is accessed.
"""
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from gateway.platforms.qqbot.adapter import QQAdapter
from gateway.platforms.event import MessageType
from gateway.run_adapters import GatewayAdapterLifecycleMixin


class TestR25QQGatewayEvent(unittest.IsolatedAsyncioTestCase):
    def make_adapter(self):
        adapter = QQAdapter.__new__(QQAdapter)
        adapter._chat_type_map = {}
        adapter._process_attachments = AsyncMock(return_value={
            "voice_transcripts": [], "attachment_info": [],
            "image_urls": [], "image_media_types": [],
        })
        adapter._process_quoted_context = AsyncMock(return_value={
            "quote_block": "quoted: 批准", "image_urls": [], "image_media_types": [],
        })
        adapter._merge_quote_into = lambda text, quote: text + "\n" + quote
        adapter._detect_message_type = lambda images, media: MessageType.TEXT
        adapter.build_source = lambda **kwargs: SimpleNamespace(
            user_id=kwargs["user_id"], chat_id=kwargs["chat_id"])
        adapter.handle_message = AsyncMock()
        adapter._platform_event_handler = AsyncMock()
        return adapter

    async def test_direct_message_uses_raw_text_not_quoted_context(self):
        a = self.make_adapter()
        await a._ingest({"content": "好", "id": "qq-real-id"}, "qq-real-id",
                        "好", None, "2026-11-22T00:00:00+00:00",
                        chat_id="open-id", qq_chat_type="c2c", user_id="open-id",
                        chat_type="dm")
        a._platform_event_handler.assert_awaited_once()
        message, source = a._platform_event_handler.await_args.args
        self.assertEqual(message["platform"], "qqbot")
        self.assertEqual(message["event_type"], "message")
        self.assertEqual(message["payload"]["text"], "好")
        self.assertEqual(message["payload"]["message_id"], "qq-real-id")
        self.assertEqual(message["payload"]["user_id"], "open-id")
        self.assertEqual(message["payload"]["chat_type"], "dm")
        self.assertIsInstance(message["payload"]["received_at_ms"], int)
        self.assertEqual(source.user_id, "open-id")
        self.assertIn("quoted: 批准", a.handle_message.await_args.args[0].text)

    async def test_group_message_does_not_emit_confirmation_event(self):
        a = self.make_adapter()
        await a._ingest({}, "group-id", "批准", None, "",
                        chat_id="group-id", qq_chat_type="group",
                        user_id="member-openid", chat_type="group")
        a._platform_event_handler.assert_not_awaited()
        a.handle_message.assert_awaited_once()

    async def test_hook_failure_does_not_block_regular_qq_message(self):
        a = self.make_adapter()
        a._platform_event_handler = AsyncMock(side_effect=RuntimeError("observer down"))
        await a._ingest({}, "qq-id", "好", None, "",
                        chat_id="open-id", qq_chat_type="c2c",
                        user_id="open-id", chat_type="dm")
        a.handle_message.assert_awaited_once()

    async def test_quoted_only_message_does_not_trigger_confirmation(self):
        a = self.make_adapter()
        await a._ingest({}, "qq-id", "", None, "",
                        chat_id="open-id", qq_chat_type="c2c",
                        user_id="open-id", chat_type="dm")
        a._platform_event_handler.assert_not_awaited()
        a.handle_message.assert_awaited_once()

class TestR25GatewayAuthorization(unittest.IsolatedAsyncioTestCase):
    async def test_runner_gate_allows_only_authorized_source(self):
        class FakeRunner:
            _handle_gateway_platform_event = GatewayAdapterLifecycleMixin._handle_gateway_platform_event
            def __init__(self):
                self.authorized = False
            def _is_user_authorized_for_source(self, source):
                return self.authorized

        fake = FakeRunner()
        normalized = {"platform": "qqbot", "event_type": "message",
                      "payload": {"text": "批准", "message_id": "msg1"}}
        source = SimpleNamespace(user_id="qq-user")
        with patch("hermes_cli.lifecycle.has_hook", return_value=True) as has_hook, \\
             patch("hermes_cli.lifecycle.invoke_hook") as invoke:
            await fake._handle_gateway_platform_event(normalized, source)
            invoke.assert_not_called()
            fake.authorized = True
            await fake._handle_gateway_platform_event(normalized, source)
            invoke.assert_called_once_with("gateway_platform_event", **normalized)
            self.assertEqual(has_hook.call_count, 2)



if __name__ == "__main__":
    unittest.main()
