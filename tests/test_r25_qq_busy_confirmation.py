"""R25 real busy-lane interception tests: isolate source, do not start Gateway."""
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from gateway.config import Platform
from gateway.run_inbound import GatewayInboundMixin
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


if __name__ == "__main__":
    unittest.main()
