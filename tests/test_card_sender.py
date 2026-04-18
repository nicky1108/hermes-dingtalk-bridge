import unittest

from hermes_dingtalk_bridge.card_sender import CardReplyService
from hermes_dingtalk_bridge.config import BridgeConfig


class _FakeClient:
    def __init__(self):
        self.config = BridgeConfig(client_id='cid', client_secret='sec', hermes_api_key='key')
        self.posts = []
        self.puts = []

    def post_openapi(self, path, payload):
        self.posts.append((path, payload))
        return {'ok': True}

    def put_openapi(self, path, payload):
        self.puts.append((path, payload))
        return {'ok': True}


class CardSenderTests(unittest.TestCase):
    def test_create_and_stream_finalize(self):
        client = _FakeClient()
        service = CardReplyService(client, logger=None)
        raw_payload = {
            'conversationType': '1',
            'senderId': 'u1',
            'senderStaffId': 'u1',
            'senderCorpId': 'corp',
            'conversationId': 'cidx',
            'msgId': 'm1',
        }
        out_track_id = service.send_card_reply(raw_payload, 'hello card', 'tpl.schema')
        self.assertTrue(out_track_id)
        self.assertEqual(client.posts[0][0], '/v1.0/card/instances/createAndDeliver')
        body = client.posts[0][1]
        self.assertEqual(body['cardTemplateId'], 'tpl.schema')
        self.assertEqual(body['cardData']['cardParamMap']['content'], '')
        self.assertEqual(client.puts[0][0], '/v1.0/card/streaming')
        self.assertEqual(client.puts[0][1]['key'], 'content')
        self.assertEqual(client.puts[0][1]['content'], 'hello card')
        self.assertTrue(client.puts[0][1]['isFinalize'])
