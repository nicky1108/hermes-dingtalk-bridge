import unittest

from hermes_dingtalk_bridge.inbound_parser import parse_inbound_message


class InboundParserTests(unittest.TestCase):
    def test_parses_text_and_mentions(self):
        payload = {
            "msgId": "msg-1",
            "conversationId": "cid-1",
            "conversationType": "2",
            "conversationTitle": "Test Group",
            "senderId": "user-1",
            "senderNick": "Alice",
            "chatbotUserId": "bot-1",
            "text": {"content": "@bot hello"},
            "atUsers": [{"dingtalkId": "bot-1"}],
            "sessionWebhook": "https://api.dingtalk.com/test",
        }
        event = parse_inbound_message(payload, account_id="default")
        self.assertEqual(event.chat_type, "group")
        self.assertTrue(event.mentions_bot)
        self.assertEqual(event.text, "@bot hello")
        self.assertEqual(event.sender_name, "Alice")
