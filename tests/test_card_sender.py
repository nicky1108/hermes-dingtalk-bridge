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

    def test_create_handle_and_stream_multiple_updates(self):
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
        handle = service.create_card_reply(raw_payload, 'tpl.schema', initial_text='处理中')
        handle.update('处理中\n\n当前回复：\nhello')
        handle.update('处理完成\n\n当前回复：\nhello world', finalize=True)
        self.assertEqual(client.posts[0][0], '/v1.0/card/instances/createAndDeliver')
        self.assertEqual(len(client.puts), 3)
        self.assertFalse(client.puts[0][1]['isFinalize'])
        self.assertEqual(client.puts[0][1]['content'], '处理中')
        self.assertEqual(client.puts[1][1]['content'], '处理中\n\n当前回复：\nhello')
        self.assertTrue(client.puts[2][1]['isFinalize'])
