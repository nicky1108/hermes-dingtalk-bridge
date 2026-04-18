import tempfile
import unittest
from pathlib import Path

from hermes_dingtalk_bridge.models import ConversationBinding, MessageRecord
from hermes_dingtalk_bridge.session_store import SessionStore


class SessionStoreTests(unittest.TestCase):
    def test_binding_round_trip_and_quote_lookup(self):
        with tempfile.TemporaryDirectory() as td:
            store = SessionStore(Path(td) / "store.db")
            binding = ConversationBinding(
                account_id="default",
                conversation_id="cid1",
                hermes_conversation="dingtalk:default:cid1",
                last_response_id="resp1",
                session_webhook="https://api.dingtalk.com/x",
                updated_at_ms=1,
            )
            store.upsert_binding(binding)
            loaded = store.get_binding("default", "cid1")
            self.assertEqual(loaded.last_response_id, "resp1")
            store.remember_message(
                MessageRecord(
                    account_id="default",
                    message_id="m1",
                    conversation_id="cid1",
                    sender_id="u1",
                    sender_name="Alice",
                    text="hello",
                    created_at_ms=1,
                )
            )
            quote = store.get_quote("default", "m1")
            self.assertEqual(quote.text, "hello")
            store.close()
