import unittest

from hermes_dingtalk_bridge.access_control import decide_access
from hermes_dingtalk_bridge.config import BridgeConfig
from hermes_dingtalk_bridge.models import InboundEvent


class AccessControlTests(unittest.TestCase):
    def _event(self, **overrides):
        data = dict(
            account_id="default",
            message_id="m1",
            conversation_id="cid1",
            conversation_title="g",
            chat_type="group",
            sender_id="u1",
            sender_name="Alice",
            sender_staff_id=None,
            chatbot_user_id="bot",
            text="hi",
            mentions=(),
            mentions_bot=False,
            session_webhook=None,
            quoted=None,
            attachments=(),
            created_at_ms=1,
            raw_payload={},
        )
        data.update(overrides)
        return InboundEvent(**data)

    def test_group_requires_mention(self):
        cfg = BridgeConfig(client_id="c", client_secret="s", hermes_api_key="k")
        decision = decide_access(self._event(), cfg)
        self.assertFalse(decision.allowed)

    def test_direct_allowlist(self):
        cfg = BridgeConfig(client_id="c", client_secret="s", hermes_api_key="k", dm_allowlist=("u1",))
        event = self._event(chat_type="direct")
        self.assertTrue(decide_access(event, cfg).allowed)
