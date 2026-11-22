"""R25 one-shot signer -> untrusted R24 bridge. No real key or QQ network."""
import base64
import io
import json
import os
import sys
import unittest
from unittest.mock import patch
from types import SimpleNamespace
from integrations.e32b_r25.hermes_plugin.backend import R25SignerPublisherBackend
from integrations.e32b_r25.hermes_plugin import transport, prepare_cli

REQUEST_ID = "TASKBIND01-" + "a" * 24

def signed_outcome(b=b'{"example":"signed canonical envelope"}'):
    return {"schema":"E32B_R25_SIGNER_OUTCOME_V1", "status":"SIGNED",
            "requestId":REQUEST_ID,
            "signedEnvelopeBase64":base64.b64encode(b).decode("ascii")}

class R25BackendTests(unittest.IsolatedAsyncioTestCase):
    async def test_one_shot_forward_to_r24_and_no_native_init_claim(self):
        counts = {"sign":0,"publish":0}
        async def signer(event):
            counts["sign"]+=1
            self.assertEqual(event["payload"]["message_id"],"qq-real-message")
            return signed_outcome()
        async def publisher(data):
            counts["publish"]+=1
            self.assertEqual(data,b'{"example":"signed canonical envelope"}')
            return {"schema":"E32B_HERMES_DISPATCH_V1",
                    "requestId":REQUEST_ID,"publishStatus":"PUBLISHED_UNTRUSTED",
                    "status":"PUBLISHED_TRIGGER_BLOCKED","qqMessage":"已发布，触发失败"}
        service=R25SignerPublisherBackend(signer,publisher)
        response=await service({"payload":{"message_id":"qq-real-message"}})
        self.assertEqual(response["status"],"PUBLISHED_TRIGGER_BLOCKED")
        self.assertFalse(response["nativeInitConfirmed"])
        self.assertEqual(counts,{"sign":1,"publish":1})

    async def test_no_pending_does_not_publish(self):
        calls=[]
        async def signer(event):
            return {"schema":"E32B_R25_SIGNER_OUTCOME_V1","status":"NO_MATCHING_PENDING"}
        async def publisher(bytes_):
            calls.append(bytes_)
        result=await R25SignerPublisherBackend(signer,publisher)({})
        self.assertEqual(result["status"],"NO_MATCHING_PENDING")
        self.assertEqual(calls,[])

    async def test_signer_result_uncertain_does_not_publish(self):
        calls=[]
        async def signer(event):
            raise OSError("lost signer reply")
        async def publisher(bytes_):
            calls.append(bytes_)
        result=await R25SignerPublisherBackend(signer,publisher)({})
        self.assertEqual(result["status"],"SIGNER_OUTCOME_UNCERTAIN")
        self.assertEqual(calls,[])

    async def test_bad_base64_fails_closed(self):
        called=[]
        async def signer(event):
            x=signed_outcome()
            x["signedEnvelopeBase64"]="not@base64"
            return x
        async def publisher(bytes_):
            called.append(bytes_)
        result=await R25SignerPublisherBackend(signer,publisher)({})
        self.assertEqual(result["status"],"SIGNER_OUTCOME_UNCERTAIN")
        self.assertEqual(called,[])

    async def test_publish_timeout_does_not_retry(self):
        calls=[]
        async def signer(event):
            return signed_outcome()
        async def publisher(data):
            calls.append(data)
            raise TimeoutError("stdout lost after publication")
        result=await R25SignerPublisherBackend(signer,publisher)({})
        self.assertEqual(result["status"],"SUBMISSION_UNCERTAIN")
        self.assertEqual(len(calls),1)

    async def test_unrecognized_r24_status_not_treated_as_published(self):
        async def signer(event):
            return signed_outcome()
        async def publisher(data):
            return {"schema":"E32B_HERMES_DISPATCH_V1","requestId":REQUEST_ID,
                    "publishStatus":"PUBLISHED_UNTRUSTED","status":"NATIVE_INIT_CONFIRMED"}
        result=await R25SignerPublisherBackend(signer,publisher)({})
        self.assertEqual(result["status"],"SUBMISSION_UNCERTAIN")

    async def test_no_arbitrary_encoded_bytes_on_rejection(self):
        called=[]
        async def signer(event):
            return {"schema":"E32B_R25_SIGNER_OUTCOME_V1",
                    "status":"REJECT_OR_DEFER","signedEnvelopeBase64":"YQ=="}
        async def publisher(data):
            called.append(data)
        result=await R25SignerPublisherBackend(signer,publisher)({})
        self.assertEqual(result["status"],"SIGNER_OUTCOME_UNCERTAIN")
        self.assertEqual(called,[])

class R25TransportContractTests(unittest.TestCase):
    def test_pipe_and_producer_paths_are_fixed(self):
        self.assertEqual(transport.PIPE_PATH, r"\\.\pipe\E32B-R25-Signer")
        self.assertIn(transport.R24_COMMIT,transport.PRODUCER_CLI)
        self.assertTrue(transport.PRODUCER_CLI.endswith(
            r"R24\hermes-entry-cli.mjs"))

    def test_pipe_client_explicit_access_excludes_create_instance(self):
        # 0x4 is FILE_CREATE_PIPE_INSTANCE / FILE_APPEND_DATA.
        self.assertEqual(transport.PIPE_CLIENT_ACCESS, 0x0012019B)
        self.assertEqual(transport.PIPE_CLIENT_ACCESS & 0x4, 0)
        self.assertEqual(transport.PIPE_CLIENT_ACCESS & 0x3, 0x3)
        self.assertEqual(transport.PIPE_CLIENT_ACCESS & 0xC0000, 0)

    def test_pipe_client_access_used_for_framed_exchange_with_mock_win32(self):
        # Only mock APIs: no live pipe, user approval, signer or R24 call.
        calls = []
        reply = b'{"status":"NO_MATCHING_PENDING"}'
        incoming = [len(reply).to_bytes(4, "big"), reply]
        handle = object()
        fake_file = SimpleNamespace(
            OPEN_EXISTING=3,
            CreateFile=lambda *args: (calls.append(args) or handle),
            WriteFile=lambda h, data: (0, len(data)),
            ReadFile=lambda h, size: (0, incoming.pop(0)),
            CloseHandle=lambda h: None,
        )
        fake_pipe = SimpleNamespace(WaitNamedPipe=lambda path, ms: None)
        with (patch.object(transport.os, "name", "nt"),
              patch.dict(sys.modules, {"win32file": fake_file, "win32pipe": fake_pipe})):
            result = transport.pipe_exchange_once({"op":"CONFIRM","schema":"TEST"})
        self.assertEqual(result["status"], "NO_MATCHING_PENDING")
        self.assertEqual(calls[0][1], transport.PIPE_CLIENT_ACCESS)
        self.assertEqual(calls[0][1] & 0x4, 0)

    def test_prepare_op_uses_dedicated_schema_without_real_pipe(self):
        proposal={"request":{"schema":"E32B_REQUEST_V1"},"sessionKey":"example"}
        with patch.object(transport,"pipe_exchange_once",return_value={
            "schema":"E32B_R25_SIGNER_PREPARE_V1",
            "status":"WAIT_USER_CONFIRMATION"}) as rpc:
            reply=transport.prepare_pending_once(proposal)
        self.assertEqual(reply["status"],"WAIT_USER_CONFIRMATION")
        self.assertEqual(rpc.call_args.args[0]["op"],"PREPARE")
        self.assertEqual(rpc.call_args.args[0]["proposal"],proposal)

    @unittest.skipUnless(os.name=="nt","Windows CLI activation contract")
    def test_prepare_cli_opt_in_and_exact_verb(self):
        proposal={"request":{"schema":"E32B_REQUEST_V1"}}
        payload=json.dumps(proposal).encode("utf-8")
        inp=io.TextIOWrapper(io.BytesIO(payload),encoding="utf-8")
        out=io.StringIO()
        receipt={"schema":"E32B_R25_SIGNER_PREPARE_V1",
                 "status":"WAIT_USER_CONFIRMATION","qqMessage":"请批准测试任务"}
        with (patch.object(sys,"stdin",inp),patch.object(sys,"stdout",out),
              patch.object(sys,"argv",["prepare_cli","--prepare"]),
              patch.dict(os.environ,{"E32B_R25_SERVICE_APPROVED":"1"}),
              patch.object(prepare_cli,"prepare_pending_once",return_value=receipt) as call):
            exit_code=prepare_cli.main()
        self.assertEqual(exit_code,0)
        self.assertEqual(call.call_count,1)
        self.assertEqual(json.loads(out.getvalue())["status"],"WAIT_USER_CONFIRMATION")


if __name__=="__main__":
    unittest.main()
