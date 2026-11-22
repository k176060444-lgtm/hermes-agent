"""R25 real busy-lane interception tests: isolate source, do not start Gateway."""
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from gateway.config import Platform
from gateway.run_inbound import GatewayInboundMixin
from gateway.run_busy import GatewayBusySessionMixin
from gateway.platforms.base import BasePlatformAdapter
from gateway.run_inbound_consumer import run_post_admission_hook, R25_BUSY_HOOK
from gateway.session import SessionSource


OPENID = "qq-test-user-01"
SESSION_KEY = "agent:main:qqbot:dm:" + OPENID


class BusyRunner:
    def __init__(self, internal=False):
        self.busy_fallbacks = 0
        self.internal = internal

    async def _hm_admit_event(self, event):
        return event, event.source, self.internal

    def _is_stale_restart_redelivery(self, event):
        return False

    def _hm_estop_gate(self, event, source, is_internal):
        return None

    def _session_key_for_source(self, source):
        return SESSION_KEY

    async def _hm_pending_reply_intercepts(self, event, source, key):
        return None

    def _hm_evict_idle_stale_agent(self, key):
        pass

    def _is_session_running(self, key):
        return True

    def _hm_evict_reaped_agent(self, key):
        pass

    async def _hm_handle_running_session_message(self, event, source, key):
        self.busy_fallbacks += 1
        return "ORIGINAL_BUSY_PATH"


def make_event(platform=Platform.QQBOT, chat_type="dm", message_id="qq-confirm-id"):
    source = SessionSource(platform=platform, chat_id=OPENID,
                           chat_type=chat_type, user_id=OPENID)
    return SimpleNamespace(source=source, message_id=message_id, text="好")


class R25BusyLaneTests(unittest.IsolatedAsyncioTestCase):
    async def call_actual_busy_lane(self, runner, event, hook):
        with (patch("gateway.run_inbound_consumer.run_post_admission_hook", hook),
              patch("hermes_cli.observability.shared_metrics_events.record_gateway_slash_command")):
            return await GatewayInboundMixin._handle_message(runner, event)

    async def test_busy_qq_confirmation_intercepts_before_interrupt(self):
        runner = BusyRunner()
        hook = AsyncMock(return_value=(True, "请求已发布，等待 Controller 处理"))
        result = await self.call_actual_busy_lane(runner, make_event(), hook)
        self.assertEqual(result, "请求已发布，等待 Controller 处理")
        self.assertEqual(runner.busy_fallbacks, 0)
        hook.assert_awaited_once()
        self.assertEqual(hook.await_args.kwargs["hook_name"], R25_BUSY_HOOK)

    async def test_busy_qq_without_pending_follows_existing_mode(self):
        runner = BusyRunner()
        hook = AsyncMock(return_value=(False, None))
        result = await self.call_actual_busy_lane(runner, make_event(), hook)
        self.assertEqual(result, "ORIGINAL_BUSY_PATH")
        self.assertEqual(runner.busy_fallbacks, 1)
        hook.assert_awaited_once()

    async def test_busy_group_ignored_by_confirmation(self):
        runner = BusyRunner()
        hook = AsyncMock(return_value=(True, "MUST_NOT_REPLY"))
        result = await self.call_actual_busy_lane(runner, make_event(chat_type="group"), hook)
        self.assertEqual(result, "ORIGINAL_BUSY_PATH")
        hook.assert_not_awaited()

    async def test_busy_other_platform_ignored_by_confirmation(self):
        runner = BusyRunner()
        hook = AsyncMock(return_value=(True, "MUST_NOT_REPLY"))
        result = await self.call_actual_busy_lane(runner, make_event(platform=Platform.TELEGRAM), hook)
        self.assertEqual(result, "ORIGINAL_BUSY_PATH")
        hook.assert_not_awaited()

    async def test_busy_internal_message_ignored_by_confirmation(self):
        runner = BusyRunner(internal=True)
        hook = AsyncMock(return_value=(True, "MUST_NOT_REPLY"))
        result = await self.call_actual_busy_lane(runner, make_event(), hook)
        self.assertEqual(result, "ORIGINAL_BUSY_PATH")
        hook.assert_not_awaited()

    async def test_busy_callback_dispatches_only_r25_hook(self):
        runner = SimpleNamespace(config=SimpleNamespace(multiplex_profiles=False))
        origin = SessionSource(platform=Platform.QQBOT, chat_id=OPENID,
                               chat_type="dm", user_id=OPENID)
        event = SimpleNamespace(message_id="qq-id", text="好")
        invoke = AsyncMock(return_value=[{"action": "handled", "reply": "R25 consumed"}])
        with (patch("hermes_cli.lifecycle.has_hook", return_value=True),
              patch("hermes_cli.lifecycle.ainvoke_hook", invoke)):
            handled, reply = await run_post_admission_hook(
                runner, event, origin, SESSION_KEY, hook_name=R25_BUSY_HOOK)
        self.assertTrue(handled)
        self.assertEqual(reply, "R25 consumed")
        self.assertEqual(invoke.await_args.args[0], R25_BUSY_HOOK)



class R25AdapterRealBusyHandlerTests(unittest.IsolatedAsyncioTestCase):
    class Runner:
        def __init__(self, authorized=True):
            self.authorized = authorized
            self._draining = False
            self.sent = []
            self.adapter = object()

        def _is_user_authorized_for_source(self, source):
            return self.authorized

        def _admit_bot_message_for_source(self, source):
            return True

        def _effective_busy_input_mode(self, source):
            return "interrupt"

        async def _route_plaintext_approval_while_busy(self, event, key):
            return False

        def _delivery_adapter_for(self, source):
            return self.adapter

        async def _send_busy_ack_reply(self, event, adapter, message):
            self.sent.append(message)

    @staticmethod
    def event(platform=Platform.QQBOT, chat_type="dm"):
        source = SessionSource(platform=platform, chat_id=OPENID,
                               chat_type=chat_type, user_id=OPENID)
        return SimpleNamespace(source=source, message_id="qq-busy-real",
                               text="批准", internal=False, allow_gateway_control=True)

    async def test_adapter_busy_confirmation_is_handled_without_interrupt(self):
        runner = self.Runner()
        event = self.event()
        hook = AsyncMock(return_value=(True, "请求已发布，等待 P1 验证"))
        with patch("gateway.run_inbound_consumer.run_post_admission_hook", hook):
            accepted = await GatewayBusySessionMixin._handle_active_session_busy_message(
                runner, event, SESSION_KEY)
        self.assertTrue(accepted)
        self.assertEqual(runner.sent, ["请求已发布，等待 P1 验证"])
        self.assertTrue(event._gateway_accepted)
        self.assertEqual(hook.await_args.kwargs["hook_name"], R25_BUSY_HOOK)

    async def test_adapter_busy_no_pending_defers_to_existing_busy_handler(self):
        runner = self.Runner()
        runner.adapter = None  # Existing branch returns False -> base handles queue.
        hook = AsyncMock(return_value=(False, None))
        with patch("gateway.run_inbound_consumer.run_post_admission_hook", hook):
            accepted = await GatewayBusySessionMixin._handle_active_session_busy_message(
                runner, self.event(), SESSION_KEY)
        self.assertFalse(accepted)
        self.assertEqual(runner.sent, [])
        hook.assert_awaited_once()

    async def test_adapter_busy_untrusted_sender_is_rejected_before_hook(self):
        runner = self.Runner(authorized=False)
        hook = AsyncMock(return_value=(True, "MUST_NOT_SEND"))
        with patch("gateway.run_inbound_consumer.run_post_admission_hook", hook):
            accepted = await GatewayBusySessionMixin._handle_active_session_busy_message(
                runner, self.event(), SESSION_KEY)
        self.assertTrue(accepted)
        hook.assert_not_awaited()
        self.assertEqual(runner.sent, [])

    async def test_adapter_busy_group_cannot_approve(self):
        runner = self.Runner()
        runner.adapter = None
        hook = AsyncMock(return_value=(True, "MUST_NOT_SEND"))
        with patch("gateway.run_inbound_consumer.run_post_admission_hook", hook):
            accepted = await GatewayBusySessionMixin._handle_active_session_busy_message(
                runner, self.event(chat_type="group"), SESSION_KEY)
        self.assertFalse(accepted)
        hook.assert_not_awaited()

    async def test_base_adapter_active_session_dispatches_to_busy_callback(self):
        class Adapter:
            def __init__(self):
                self._active_sessions = {SESSION_KEY: object()}
                self._pending_messages = {}
                self._busy_session_handler = AsyncMock(return_value=True)
            def _canonicalize(self, source):
                return None
        adapter=Adapter()
        event=SimpleNamespace(source=self.event().source,
                              allow_gateway_control=False,
                              get_command=lambda:None,
                              internal=False, message_id="qq-real")
        await BasePlatformAdapter._handle_message_while_active(
            adapter,event,SESSION_KEY)
        adapter._busy_session_handler.assert_awaited_once_with(event, SESSION_KEY)


if __name__ == "__main__":
    unittest.main()
