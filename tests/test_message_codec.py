import unittest

from hermes_dingtalk_bridge.config import BridgeConfig
from hermes_dingtalk_bridge.message_codec import build_conversation_name, build_hermes_input
from hermes_dingtalk_bridge.models import InboundEvent, QuotedRef


class MessageCodecTests(unittest.TestCase):
    def test_builds_conversation_name(self):
        cfg = BridgeConfig(client_id="c", client_secret="s", hermes_api_key="k")
        self.assertEqual(build_conversation_name(cfg, "default", "cid1"), "dingtalk:default:cid1")

    def test_build_input_includes_quote(self):
        cfg = BridgeConfig(client_id="c", client_secret="s", hermes_api_key="k")
        event = InboundEvent(
            account_id="default",
            message_id="m1",
            conversation_id="cid1",
            conversation_title="Group",
            chat_type="group",
            sender_id="u1",
            sender_name="Alice",
            sender_staff_id=None,
            chatbot_user_id="bot",
            text="hello world",
            quoted=QuotedRef(message_id="m0", sender_name="Bob", text="quoted text"),
            raw_payload={},
        )
        rendered = build_hermes_input(event, cfg)
        self.assertIn("[QuotedMessage]", rendered)
        self.assertIn("quoted text", rendered)
