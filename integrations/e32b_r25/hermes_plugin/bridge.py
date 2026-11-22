"""R25 QQ approval hook bridge — source-only, no key and no Agent approval authority.

Receives original QQ C2C text via the authorized gateway_platform_event
observer, then correlates it with post_gateway_admission (after the Gateway
has admitted a real message) to return a direct QQ reply without an LLM turn.

The backend must be an independently bound confirmation service. No backend is
configured by default: without one, ordinary Hermes processing is unchanged.
This is not an IPC authentication boundary or a signer.
"""
from __future__ import annotations

import asyncio
from collections import OrderedDict
from dataclasses import dataclass
from threading import RLock
from time import monotonic
from typing import Any, Awaitable, Callable, Optional


@dataclass(frozen=True)
class CapturedQQMessage:
    user_id: str
    chat_id: str
    message_id: str
    text: str
    received_at_ms: int
    captured_at: float


class R25QQHookBridge:
    def __init__(self, service: Optional[Callable[[dict], Awaitable[dict]]] = None,
                 *, clock: Callable[[], float] = monotonic,
                 ttl_seconds: float = 120.0, limit: int = 256) -> None:
        self.service = service
        self.clock = clock
        self.ttl_seconds = ttl_seconds
        self.limit = limit
        self._lock = RLock()
        self._events: OrderedDict[tuple[str, str], CapturedQQMessage] = OrderedDict()

    def _expire(self, now: float) -> None:
        for key, data in list(self._events.items()):
            if now - data.captured_at > self.ttl_seconds:
                self._events.pop(key, None)

    def on_gateway_platform_event(self, platform: str = "", event_type: str = "",
                                  payload: Optional[dict] = None, **kwargs: Any) -> None:
        # GatewayRunner checks _is_user_authorized_for_source before this
        # observer is called. We retain no SDK object, Session row or tool text.
        if platform != "qqbot" or event_type != "message" or not isinstance(payload, dict):
            return
        if payload.get("chat_type") != "dm":
            return
        user_id, chat_id, message_id = (payload.get(x) for x in
                                        ("user_id", "chat_id", "message_id"))
        content, arrival = payload.get("text"), payload.get("received_at_ms")
        if (not isinstance(user_id, str) or not user_id or
                not isinstance(chat_id, str) or chat_id != user_id or
                not isinstance(message_id, str) or not 0 < len(message_id) <= 512 or
                not isinstance(content, str) or not 0 < len(content) <= 160 or
                not isinstance(arrival, int) or arrival <= 0):
            return
        now = self.clock()
        with self._lock:
            self._expire(now)
            key = (user_id, message_id)
            # First original event wins; same message ID must not change text.
            if key in self._events:
                return
            self._events[key] = CapturedQQMessage(
                user_id, chat_id, message_id, content, arrival, now)
            while len(self._events) > self.limit:
                self._events.popitem(last=False)

    async def on_post_gateway_admission(self, *, session_key: str = "",
                                        platform: str = "", source: Optional[dict] = None,
                                        message_id: Optional[str] = None,
                                        text: str = "", **kwargs: Any):
        # The post-admission hook is called by Hermes after actual authorization.
        # IMPORTANT: its 'text' argument can include a quote/attachment; ignore it.
        if self.service is None or platform != "qqbot" or not isinstance(source, dict):
            return None
        if source.get("chat_type") != "dm":
            return None
        user_id, chat_id = source.get("user_id"), source.get("chat_id")
        if (not isinstance(user_id, str) or not user_id or chat_id != user_id or
                not isinstance(message_id, str) or
                not isinstance(session_key, str) or
                not session_key.endswith(":qqbot:dm:" + user_id)):
            return None

        with self._lock:
            self._expire(self.clock())
            original = self._events.pop((user_id, message_id), None)
        if original is None or original.chat_id != chat_id:
            return None

        trusted_shape = {
            "platform": "qqbot", "event_type": "message",
            "payload": {
                "user_id": original.user_id, "chat_id": original.chat_id,
                "chat_type": "dm", "message_id": original.message_id,
                "text": original.text, "received_at_ms": original.received_at_ms,
            }
        }
        # The service may perform a local IPC call; bound its duration so a
        # broken signer cannot stall the Gateway's entire message lane.
        try:
            result = self.service(trusted_shape)
            if asyncio.iscoroutine(result) or asyncio.isfuture(result):
                result = await asyncio.wait_for(result, timeout=18.0)
        except Exception:
            # No fake approval. Hermes can continue normally on backend failure.
            return None
        if not isinstance(result, dict):
            return None
        status = result.get("status")
        if status in ("NO_MATCHING_PENDING", "IGNORED_EVENT", "IGNORED_SOURCE",
                      "STALE_EVENT", "AMBIGUOUS"):
            return None
        replies = {
            "REJECT_OR_DEFER": "本次 Coding 任务没有获得批准，尚未提交。请明确确认后再继续。",
            "MULTIPLE_PENDING_NEED_TASK_ID": "存在多项待确认任务，请回复“批准 <任务ID>”。",
            "MESSAGE_ALREADY_USED": "这条确认消息已处理，不会重复提交任务。",
            "SIGNING_BLOCKED": "确认已收到，但后台签名失败，任务未提交，请核查。",
            "SUBMISSION_UNCERTAIN": "请求提交状态尚不明确，禁止自动重试，请先查询状态。",
            "SIGNER_OUTCOME_UNCERTAIN": "后台确认结果不确定，请查询任务状态，不要重复授权或提交。",
        }
        message = result.get("qqMessage")
        if not isinstance(message, str) or not message.strip():
            message = replies.get(status)
        if status not in replies and status not in ("PUBLISHED_START_REQUESTED",
                                                       "PUBLISHED_TRIGGER_BLOCKED"):
            return None
        if not isinstance(message, str) or not message.strip():
            return None
        return {"action": "handled", "reply": message}
