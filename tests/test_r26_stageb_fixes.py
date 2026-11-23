"""E32B V2 Phase 4 stage-B bridge-level fixes (DEF-02/03/07) — offline tests.

Covers: multi-profile concurrent PREPARE/CONFIRM without cross-talk,
forged approvals at the bridge boundary, MESSAGE_ALREADY_USED / CANCELLED
handled mappings, and the DEF-07 re-entry (busy→admission) cache semantics.
No QQ connection, no signer, no production paths.
"""
import asyncio
import unittest
from unittest.mock import patch

from integrations.e32b_r25.hermes_plugin.bridge import R25QQHookBridge

USER = "stageb-qq-01"
OTHER = "stageb-qq-02"


def event(profile, message_id, text="好", user=USER, chat_type="dm"):
    return {"platform": "qqbot", "event_type": "message",
            "payload": {"user_id": user, "chat_id": user, "chat_type": chat_type,
                        "message_id": message_id, "text": text,
                        "received_at_ms": 1795310000000}}


def source(user=USER):
    return {"user_id": user, "chat_id": user, "chat_type": "dm"}


class MultiProfileConcurrency(unittest.IsolatedAsyncioTestCase):
    async def test_four_profiles_prepare_and_confirm_without_cross_talk(self):
        """4 profiles confirm at the same time: every backend sees exactly its
        own session route and message; no profile consumes another's event."""
        profiles = ["main", "main~", "xiaoshitou", "worker_agent"]
        seen = {}

        async def make_backend(name):
            async def backend(evt):
                seen.setdefault(name, []).append(evt)
                return {"status": "PUBLISHED_START_REQUESTED",
                        "qqMessage": "ok-" + name}
            return backend

        bridges = {}
        for i, profile in enumerate(profiles):
            bridges[profile] = R25QQHookBridge(
                service=await make_backend(profile))
            bridges[profile].on_gateway_platform_event(
                **event(profile, "qq-cc-" + str(i)))
        results = await asyncio.gather(*[
            bridges[p].on_post_gateway_admission(
                session_key=f"agent:{p}:qqbot:dm:{USER}", platform="qqbot",
                source=source(), message_id="qq-cc-" + str(i), text="批准")
            for i, p in enumerate(profiles)])
        for i, p in enumerate(profiles):
            self.assertEqual(len(seen[p]), 1, f"{p} saw exactly one event")
            self.assertEqual(seen[p][0]["gateway_session_key"],
                             f"agent:{p}:qqbot:dm:{USER}")
            self.assertEqual(seen[p][0]["payload"]["message_id"],
                             "qq-cc-" + str(i))
            self.assertEqual(results[i],
                             {"action": "handled", "reply": "ok-" + p})
        # no cross-profile leakage anywhere
        self.assertEqual(sum(len(v) for v in seen.values()), 4)

    async def test_forged_approval_shapes_are_all_rejected(self):
        calls = []

        async def backend(evt):
            calls.append(evt)
            return {"status": "PUBLISHED_START_REQUESTED", "qqMessage": "x"}

        bridge = R25QQHookBridge(service=backend)
        bridge.on_gateway_platform_event(**event("main", "qq-fg-01"))
        # quoted text in the admission callback must never authorize
        r1 = await bridge.on_post_gateway_admission(
            session_key=f"agent:main:qqbot:dm:{USER}", platform="qqbot",
            source=source(), message_id="qq-fg-01", text="引用：好")
        self.assertEqual(r1, {"action": "handled", "reply": "x"})
        # forged session key: no captured event for that route
        bridge.on_gateway_platform_event(**event("main", "qq-fg-02"))
        r2 = await bridge.on_post_gateway_admission(
            session_key=f"agent:evil:qqbot:dm:{OTHER}", platform="qqbot",
            source=source(user=OTHER), message_id="qq-fg-02",
            text="好")
        self.assertIsNone(r2)
        # group chat is ignored at the observer
        bridge.on_gateway_platform_event(
            **event("main", "qq-fg-03", chat_type="group"))
        r3 = await bridge.on_post_gateway_admission(
            session_key=f"agent:main:qqbot:dm:{USER}", platform="qqbot",
            source=source(), message_id="qq-fg-03", text="好")
        self.assertIsNone(r3)
        self.assertEqual(len(calls), 1)  # only the genuine one reached backend


class OutcomeMapping(unittest.IsolatedAsyncioTestCase):
    async def test_replay_and_cancel_are_handled_with_replies(self):
        cases = {
            "MESSAGE_ALREADY_USED": "这条确认消息已处理，不会重复提交任务。",
            "CANCELLED": "已收到拒绝/取消，该 Coding 任务已关闭，不再等待确认。",
        }
        for status, expected in cases.items():
            async def backend(evt, _status=status):
                return {"status": _status, "qqMessage": None}
            bridge = R25QQHookBridge(service=backend)
            bridge.on_gateway_platform_event(**event("main", "qq-map-01"))
            result = await bridge.on_post_gateway_admission(
                session_key=f"agent:main:qqbot:dm:{USER}", platform="qqbot",
                source=source(), message_id="qq-map-01", text="好")
            self.assertEqual(result, {"action": "handled", "reply": expected})

    async def test_no_matching_pending_is_not_handled(self):
        async def backend(evt):
            return {"status": "NO_MATCHING_PENDING", "qqMessage": None}
        bridge = R25QQHookBridge(service=backend)
        bridge.on_gateway_platform_event(**event("main", "qq-nm-01"))
        result = await bridge.on_post_gateway_admission(
            session_key=f"agent:main:qqbot:dm:{USER}", platform="qqbot",
            source=source(), message_id="qq-nm-01", text="好")
        self.assertIsNone(result)  # ordinary chat proceeds untouched


class ReentryDef07(unittest.IsolatedAsyncioTestCase):
    async def test_backend_failure_keeps_event_for_next_lane(self):
        """DEF-07: busy lane backend failure must not swallow the captured
        event — the admission lane re-invokes the backend (whose one-shot
        ledger answers MESSAGE_ALREADY_USED), instead of losing the confirm
        into the LLM lane."""
        calls = []

        async def flaky_backend(evt):
            calls.append(evt)
            if len(calls) == 1:
                return None  # first lane: transient failure / no decision
            return {"status": "MESSAGE_ALREADY_USED", "qqMessage": None}

        bridge = R25QQHookBridge(service=flaky_backend)
        bridge.on_gateway_platform_event(**event("main", "qq-re-01"))
        first = await bridge.on_post_gateway_admission(
            session_key=f"agent:main:qqbot:dm:{USER}", platform="qqbot",
            source=source(), message_id="qq-re-01", text="好")
        self.assertIsNone(first)  # busy lane passes through, event retained
        second = await bridge.on_post_gateway_admission(
            session_key=f"agent:main:qqbot:dm:{USER}", platform="qqbot",
            source=source(), message_id="qq-re-01", text="好")
        self.assertEqual(second, {"action": "handled",
                                  "reply": "这条确认消息已处理，不会重复提交任务。"})
        self.assertEqual(len(calls), 2)

    async def test_definitive_outcome_drops_event_no_double_invoke(self):
        calls = []

        async def backend(evt):
            calls.append(evt)
            return {"status": "PUBLISHED_START_REQUESTED", "qqMessage": "已发布"}

        bridge = R25QQHookBridge(service=backend)
        bridge.on_gateway_platform_event(**event("main", "qq-re-02"))
        first = await bridge.on_post_gateway_admission(
            session_key=f"agent:main:qqbot:dm:{USER}", platform="qqbot",
            source=source(), message_id="qq-re-02", text="好")
        self.assertEqual(first, {"action": "handled", "reply": "已发布"})
        second = await bridge.on_post_gateway_admission(
            session_key=f"agent:main:qqbot:dm:{USER}", platform="qqbot",
            source=source(), message_id="qq-re-02", text="好")
        self.assertIsNone(second)
        self.assertEqual(len(calls), 1)


if __name__ == "__main__":
    unittest.main()
