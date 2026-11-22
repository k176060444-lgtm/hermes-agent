"""R25 one-shot signer -> untrusted R24 bridge. No real key or QQ network."""
import base64
import unittest
from integrations.e32b_r25.hermes_plugin.backend import R25SignerPublisherBackend

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

if __name__=="__main__":
    unittest.main()
