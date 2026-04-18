import asyncio
import tempfile
import unittest
from pathlib import Path

from hermes_dingtalk_bridge.config import BridgeConfig
from hermes_dingtalk_bridge.models import HermesReply
from hermes_dingtalk_bridge.service import BridgeService


class _FakeHermesClient:
    def __init__(self):
        self.calls = []

    def health(self):
        return {"status": "ok"}

    def create_response(self, **kwargs):
        self.calls.append(kwargs)
        return HermesReply(text="hello from hermes", response_id="resp-1", conversation=kwargs["conversation"], raw_response={})

    def create_response_stream(self, **kwargs):
        self.calls.append(kwargs)
        on_tool_event = kwargs.get("on_tool_event")
        on_text_delta = kwargs.get("on_text_delta")
        if on_tool_event:
            on_tool_event("正在调用工具: search_docs")
        if on_text_delta:
            on_text_delta("hello ")
            on_text_delta("from hermes")
        return HermesReply(text="hello from hermes", response_id="resp-1", conversation=kwargs["conversation"], raw_response={})


class _FakeDingTalkClient:
    def __init__(self, config):
        self.config = config
        self.session_messages = []
        self.proactive_messages = []
        self.posts = []
        self.puts = []

    def send_session_markdown(self, webhook, text):
        self.session_messages.append((webhook, text))
        return {"ok": True}

    def send_proactive_markdown(self, conversation_id, text):
        self.proactive_messages.append((conversation_id, text))
        return {"ok": True}

    def post_openapi(self, path, payload):
        self.posts.append((path, payload))
        return {"ok": True}

    def put_openapi(self, path, payload):
        self.puts.append((path, payload))
        return {"ok": True}


class ServiceTests(unittest.TestCase):
    def test_handles_inbound_message(self):
        with tempfile.TemporaryDirectory() as td:
            cfg = BridgeConfig(
                client_id="client",
                client_secret="secret",
                hermes_api_key="key",
                store_path=Path(td) / "store.db",
                ack_reaction_enabled=False,
            )
            service = BridgeService(cfg)
            service.hermes = _FakeHermesClient()
            fake_dingtalk = _FakeDingTalkClient(cfg)
            service.dingtalk = fake_dingtalk
            service.sender.client = fake_dingtalk
            service.sender.card_replies.client = fake_dingtalk
            payload = {
                "msgId": "m1",
                "conversationId": "user-1",
                "conversationType": "1",
                "senderId": "user-1",
                "senderNick": "Alice",
                "text": {"content": "hello"},
                "sessionWebhook": "https://api.dingtalk.com/webhook",
            }
            asyncio.run(service.handle_raw_message(payload))
            self.assertEqual(len(fake_dingtalk.session_messages), 1)
            self.assertEqual(fake_dingtalk.session_messages[0][1], "hello from hermes")
            self.assertEqual(len(service.hermes.calls), 1)
            service.store.close()

    def test_streams_progress_into_card_mode(self):
        with tempfile.TemporaryDirectory() as td:
            cfg = BridgeConfig(
                client_id="client",
                client_secret="secret",
                hermes_api_key="key",
                store_path=Path(td) / "store.db",
                ack_reaction_enabled=False,
                reply_mode="card",
                card_template_id="tpl.schema",
            )
            service = BridgeService(cfg)
            service.hermes = _FakeHermesClient()
            fake_dingtalk = _FakeDingTalkClient(cfg)
            service.dingtalk = fake_dingtalk
            service.sender.client = fake_dingtalk
            service.sender.card_replies.client = fake_dingtalk
            payload = {
                "msgId": "m1",
                "conversationId": "user-1",
                "conversationType": "1",
                "senderId": "user-1",
                "senderNick": "Alice",
                "text": {"content": "hello"},
                "sessionWebhook": "https://api.dingtalk.com/webhook",
            }
            asyncio.run(service.handle_raw_message(payload))
            self.assertEqual(len(fake_dingtalk.posts), 1)
            self.assertGreaterEqual(len(fake_dingtalk.puts), 3)
            self.assertIn("处理中", fake_dingtalk.puts[0][1]["content"])
            self.assertIn("正在调用工具: search_docs", fake_dingtalk.puts[-1][1]["content"])
            self.assertIn("hello from hermes", fake_dingtalk.puts[-1][1]["content"])
            self.assertTrue(fake_dingtalk.puts[-1][1]["isFinalize"])
            self.assertEqual(fake_dingtalk.session_messages, [])
            service.store.close()
