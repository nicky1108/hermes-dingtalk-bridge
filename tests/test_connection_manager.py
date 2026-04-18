import asyncio
import unittest

from hermes_dingtalk_bridge.config import BridgeConfig
from hermes_dingtalk_bridge.connection_manager import ConnectionManager


class _FakeLogger:
    def __init__(self):
        self.lines = []

    def warning(self, *args, **kwargs):
        self.lines.append(("warning", args))

    def info(self, *args, **kwargs):
        self.lines.append(("info", args))


class _FakeRunner:
    def __init__(self, outcomes, manager):
        self.outcomes = outcomes
        self.manager = manager
        self.stop_requested = False

    async def run_once(self):
        outcome = self.outcomes.pop(0)
        if outcome == "fail":
            raise RuntimeError("boom")
        if outcome == "stop":
            self.manager.stop()
            return
        await asyncio.sleep(0)

    def request_stop(self):
        self.stop_requested = True


class ConnectionManagerTests(unittest.IsolatedAsyncioTestCase):
    async def test_reconnects_after_failure(self):
        cfg = BridgeConfig(
            client_id="c",
            client_secret="s",
            hermes_api_key="k",
            initial_reconnect_delay_ms=1,
            max_reconnect_delay_ms=2,
        )
        logger = _FakeLogger()
        outcomes = ["fail", "stop"]
        manager = None

        def factory():
            return _FakeRunner(outcomes, manager)

        manager = ConnectionManager(cfg, factory, logger)
        await manager.run_forever()
        self.assertEqual(outcomes, [])
