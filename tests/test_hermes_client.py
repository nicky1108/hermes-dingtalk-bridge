import unittest

from hermes_dingtalk_bridge.config import BridgeConfig
from hermes_dingtalk_bridge.hermes_client import HermesClient


class HermesClientToolEventTests(unittest.TestCase):
    def test_formats_search_files_event(self):
        event = {
            "item": {
                "type": "function_call",
                "name": "search_files",
                "arguments": '{"pattern":"SOUL.md","target":"files","path":".","limit":5}',
            }
        }
        line = HermesClient._tool_event_message(event, done=False)
        self.assertEqual(line, '🔎 search_files: "SOUL.md"')

    def test_formats_terminal_event(self):
        event = {
            "item": {
                "type": "function_call",
                "name": "terminal",
                "arguments": '{"command":"date \'+%F %T %Z\' && pwd","timeout":30}',
            }
        }
        line = HermesClient._tool_event_message(event, done=False)
        self.assertIn('💻 terminal: "', line)
        self.assertIn("date '+%F %T %Z' && pwd", line)

    def test_skips_done_event(self):
        event = {
            "item": {
                "type": "function_call",
                "name": "search_files",
                "arguments": '{"pattern":"README.md"}',
            }
        }
        self.assertIsNone(HermesClient._tool_event_message(event, done=True))

    def test_stream_timeout_uses_dedicated_read_timeout(self):
        client = HermesClient(
            BridgeConfig(
                client_id='c',
                client_secret='s',
                hermes_api_key='k',
                request_timeout_seconds=15,
                stream_read_timeout_seconds=240,
            )
        )
        self.assertEqual(client._stream_timeout(), (15, 240))
