"""R26 multi-profile Gateway-local confirmation. All tests are offline."""
import asyncio
import io
import json
import os
import sys
import unittest
from types import SimpleNamespace
from unittest.mock import patch
from integrations.e32b_r26.hermes_plugin import register, create_opt_in_backend
from integrations.e32b_r26.hermes_plugin import local_backend, prepare_cli
from integrations.e32b_r25.hermes_plugin.bridge import R25QQHookBridge

USER="runtimeQQ_AaBb123"
def message(profile="xiaoshitou",msg="qq-real-001",text="好"):
    return {
        "platform":"qqbot","event_type":"message",
        "payload":{"user_id":USER,"chat_id":USER,"chat_type":"dm",
                   "message_id":msg,"text":text,"received_at_ms":1795310000000}
    }
def source():
    return {"user_id":USER,"chat_id":USER,"chat_type":"dm"}

class MultiProfileBridge(unittest.IsolatedAsyncioTestCase):
    async def test_runtime_session_namespace_reaches_local_backend(self):
        for profile in ("main","main~","xiaoshitou","another_agent"):
            found=[]
            async def backend(evt):
                found.append(evt)
                return {"status":"NO_MATCHING_PENDING","qqMessage":None}
            bridge=R25QQHookBridge(service=backend)
            event=message(profile=profile)
            bridge.on_gateway_platform_event(**event)
            session="agent:"+profile+":qqbot:dm:"+USER
            reply=await bridge.on_post_gateway_admission(
                session_key=session,platform="qqbot",source=source(),
                message_id="qq-real-001",text="好（引用内容不能算确认）")
            self.assertIsNone(reply)
            self.assertEqual(len(found),1)
            self.assertEqual(found[0]["gateway_session_key"],session)
            self.assertEqual(found[0]["payload"]["text"],"好")

    async def test_false_session_and_group_cannot_call_backend(self):
        called=[]
        async def backend(evt):
            called.append(evt)
            return {"status":"PUBLISHED_START_REQUESTED","qqMessage":"bad"}
        bridge=R25QQHookBridge(service=backend)
        bridge.on_gateway_platform_event(**message())
        self.assertIsNone(await bridge.on_post_gateway_admission(
            session_key="agent:unrelated:qqbot:dm:OTHER",
            platform="qqbot",source=source(),message_id="qq-real-001"))
        self.assertEqual(called,[])

    async def test_local_client_not_retrying_failed_confirm(self):
        client=local_backend.R26GatewayLocalBackend()
        with patch.object(local_backend,"invoke_local_gateway",
                          side_effect=TimeoutError("lost reply")) as mock:
            result=await client({"gateway_session_key":"agent:main:qqbot:dm:"+USER})
        self.assertEqual(result["status"],"SUBMISSION_UNCERTAIN")
        self.assertEqual(mock.call_count,1)

    async def test_local_client_passes_raw_event_and_returns_r26_response(self):
        client=local_backend.R26GatewayLocalBackend()
        evt=message()
        evt["gateway_session_key"]="agent:main:qqbot:dm:"+USER
        reply={"schema":"E32B_R26_GATEWAY_CONFIRM_V1",
               "status":"PUBLISHED_START_REQUESTED",
               "qqMessage":"已发布，未确认 Init"}
        with patch.object(local_backend,"invoke_local_gateway",return_value=reply) as mock:
            result=await client(evt)
        self.assertEqual(result,reply)
        self.assertEqual(mock.call_args.args,("--confirm",evt))

class LocalCommand(unittest.TestCase):
    def test_no_enabled_host_is_inert(self):
        with patch.dict(os.environ,{},clear=True):
            self.assertIsNone(create_opt_in_backend())

    def test_one_generic_plugin_registers_original_busy_hook(self):
        class FakeCtx:
            def __init__(self):self.hooks=[]
            def register_hook(self,name,fn):self.hooks.append(name)
        ctx=FakeCtx()
        register(ctx)
        self.assertEqual(ctx.hooks,[
            "gateway_platform_event","post_gateway_admission",
            "r25_qq_busy_confirmation"
        ])

    def test_r26_backend_timeout_exceeds_node_subprocess_budget(self):
        class FakeCtx:
            def __init__(self): self.hooks = {}
            def register_hook(self,name,callback): self.hooks[name] = callback
        ctx = FakeCtx()
        register(ctx)
        hook = ctx.hooks["post_gateway_admission"].__self__
        self.assertEqual(hook.service_timeout_seconds, 30.0)
        self.assertGreater(hook.service_timeout_seconds, 25.0)
        # R25 plugin remains at its independent 18s default.
        self.assertEqual(R25QQHookBridge().service_timeout_seconds, 18.0)

    def test_local_node_exec_has_fixed_verb_no_shell_and_no_password(self):
        result={"schema":"E32B_R26_GATEWAY_PREPARE_V1",
                "status":"WAIT_USER_CONFIRMATION","qqMessage":"待确认"}
        expected=SimpleNamespace(returncode=0,
              stdout=json.dumps(result).encode("utf-8"))
        payload={"sessionKey":"agent:anyAgent:qqbot:dm:"+USER,
                 "userId":USER,"chatId":USER}
        with (patch.dict(os.environ,{"E32B_R26_GATEWAY_APPROVED":"1"}),
              patch.object(local_backend,"_configured_cli",
                           return_value=r"C:\e32b-r26\07-development\R26\gateway-local-cli.mjs"),
              patch.object(local_backend.subprocess,"run",return_value=expected) as run):
            out=local_backend.invoke_local_gateway("--prepare",payload,platform="nt")
        self.assertEqual(out["status"],"WAIT_USER_CONFIRMATION")
        self.assertEqual(run.call_count,1)
        args=run.call_args.args[0]
        self.assertEqual(args[0],local_backend.NODE_EXE)
        self.assertEqual(args[-1],"--prepare")
        self.assertFalse(run.call_args.kwargs["shell"])
        self.assertEqual(json.loads(run.call_args.kwargs["input"]),payload)

    def test_disabled_host_cannot_fork_local_node(self):
        with (patch.dict(os.environ,{},clear=True),
              patch.object(local_backend.subprocess,"run") as run):
            with self.assertRaisesRegex(RuntimeError,"R26_GATEWAY_NOT_ENABLED"):
                local_backend.invoke_local_gateway("--confirm",{},platform="nt")
        run.assert_not_called()

    def test_prepared_result_schema_is_checked(self):
        result={"schema":"WRONG","status":"WAIT_USER_CONFIRMATION"}
        bad=SimpleNamespace(returncode=0,stdout=json.dumps(result).encode())
        with (patch.dict(os.environ,{"E32B_R26_GATEWAY_APPROVED":"1"}),
              patch.object(local_backend,"_configured_cli",return_value=r"C:\R26\07-development\R26\gateway-local-cli.mjs"),
              patch.object(local_backend.subprocess,"run",return_value=bad)):
            with self.assertRaisesRegex(RuntimeError,"R26_GATEWAY_OUTCOME_UNKNOWN"):
                local_backend.invoke_local_gateway("--prepare",{},platform="nt")

    def test_runtime_prepare_profile_namespace_comes_from_hermes_api(self):
        basic={"userId":USER,"chatId":USER,"chatType":"dm"}
        default=prepare_cli.bind_runtime_proposal(basic,profile="default")
        main=prepare_cli.bind_runtime_proposal(basic,profile="main")
        another=prepare_cli.bind_runtime_proposal(basic,profile="worker_agent")
        self.assertEqual(default["sessionKey"],"agent:main:qqbot:dm:"+USER)
        self.assertEqual(main["sessionKey"],"agent:main~:qqbot:dm:"+USER)
        self.assertEqual(another["sessionKey"],"agent:worker_agent:qqbot:dm:"+USER)
        self.assertNotEqual(default["sessionKey"],main["sessionKey"])
        self.assertNotIn("sessionKey",basic)

    def test_prepare_mismatched_explicit_session_is_rejected(self):
        payload={"userId":USER,"chatId":USER,
                 "sessionKey":"agent:other:qqbot:dm:"+USER}
        with self.assertRaisesRegex(ValueError,"R26_PREPARE_SESSION_MISMATCH"):
            prepare_cli.bind_runtime_proposal(payload,profile="xiaoshitou")
        with self.assertRaisesRegex(ValueError,"R26_PREPARE_ROUTE_INVALID"):
            prepare_cli.bind_runtime_proposal(
                {"userId":USER,"chatId":"foreign"},profile="default")

    def test_prepare_cli_calls_only_prepare_never_confirm_or_publish(self):
        payload={"request":{"schema":"E32B_REQUEST_V1"},
                 "sessionKey":"agent:other:qqbot:dm:"+USER,
                 "userId":USER,"chatId":USER}
        input_stream=SimpleNamespace(buffer=io.BytesIO(json.dumps(payload).encode("utf-8")))
        output=io.StringIO()
        receipt={"schema":"E32B_R26_GATEWAY_PREPARE_V1",
                 "status":"WAIT_USER_CONFIRMATION",
                 "qqMessage":"Coding 任务待确认"}
        with (patch.object(sys,"argv",["prepare_cli","--prepare"]),
              patch.object(prepare_cli.os,"name","nt"),
              patch.dict(os.environ,{"E32B_R26_GATEWAY_APPROVED":"1"}),
              patch("hermes_cli.profiles.current_profile_name",return_value="other"),
              patch.object(sys,"stdin",input_stream),
              patch.object(sys,"stdout",output),
              patch.object(prepare_cli,"prepare_local_pending",return_value=receipt) as call):
            rc=prepare_cli.main()
        self.assertEqual(rc,0)
        self.assertEqual(call.call_args.args[0],payload)
        self.assertEqual(json.loads(output.getvalue())["status"],"WAIT_USER_CONFIRMATION")


if __name__=="__main__":
    unittest.main()
