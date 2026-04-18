import json
import tempfile
import unittest
from pathlib import Path

from hermes_dingtalk_bridge.config import BridgeConfig
from hermes_dingtalk_bridge.runtime_status import initialize_runtime_status, mark_inbound, mark_runtime_stopped, status_path


class RuntimeStatusTests(unittest.TestCase):
    def test_runtime_status_lifecycle(self):
        with tempfile.TemporaryDirectory() as td:
            cfg = BridgeConfig(client_id='c', client_secret='s', hermes_api_key='k', store_path=Path(td) / 'store.db')
            initialize_runtime_status(cfg, source='test')
            path = status_path(cfg)
            self.assertTrue(path.exists())
            data = json.loads(path.read_text(encoding='utf-8'))
            self.assertTrue(data['running'])
            self.assertEqual(data['source'], 'test')
            mark_inbound(cfg, message_id='m1', conversation_id='c1')
            data = json.loads(path.read_text(encoding='utf-8'))
            self.assertEqual(data['last_message_id'], 'm1')
            mark_runtime_stopped(cfg, reason='done')
            data = json.loads(path.read_text(encoding='utf-8'))
            self.assertFalse(data['running'])
            self.assertEqual(data['stop_reason'], 'done')
