from __future__ import annotations

import asyncio
import random
import time
from typing import Protocol

from .config import BridgeConfig


class SupportsRunner(Protocol):
    async def run_once(self) -> None: ...
    def request_stop(self) -> None: ...


class ConnectionManager:
    def __init__(self, config: BridgeConfig, runner_factory, logger) -> None:
        self.config = config
        self.runner_factory = runner_factory
        self.logger = logger
        self._stop = False
        self._runner: SupportsRunner | None = None
        self._last_activity = time.monotonic()

    def notify_activity(self) -> None:
        self._last_activity = time.monotonic()

    def stop(self) -> None:
        self._stop = True
        if self._runner is not None:
            self._runner.request_stop()

    async def run_forever(self) -> None:
        delay = self.config.initial_reconnect_delay_ms / 1000.0
        while not self._stop:
            self._runner = self.runner_factory()
            self.notify_activity()
            watchdog = None
            try:
                watchdog = asyncio.create_task(self._watchdog())
                await self._runner.run_once()
                if self._stop:
                    break
                self.logger.warning("DingTalk stream stopped; reconnecting")
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                if self._stop:
                    break
                self.logger.warning("DingTalk stream failed: %s", exc)
            finally:
                if watchdog is not None:
                    watchdog.cancel()
                    with contextlib.suppress(asyncio.CancelledError):
                        await watchdog
            if self._stop:
                break
            sleep_for = _apply_jitter(delay, self.config.reconnect_jitter)
            self.logger.info("Reconnecting to DingTalk in %.2fs", sleep_for)
            await asyncio.sleep(sleep_for)
            delay = min(delay * 2, self.config.max_reconnect_delay_ms / 1000.0)

    async def _watchdog(self) -> None:
        if self.config.inactivity_reconnect_seconds <= 0:
            while not self._stop:
                await asyncio.sleep(3600)
            return
        while not self._stop:
            await asyncio.sleep(max(5, self.config.inactivity_reconnect_seconds // 3 or 1))
            idle = time.monotonic() - self._last_activity
            if idle >= self.config.inactivity_reconnect_seconds:
                self.logger.warning(
                    "No DingTalk activity for %.1fs; forcing reconnect", idle
                )
                if self._runner is not None:
                    self._runner.request_stop()
                self.notify_activity()


def _apply_jitter(delay_seconds: float, jitter: float) -> float:
    if jitter <= 0:
        return delay_seconds
    spread = delay_seconds * jitter
    return max(0.1, delay_seconds + random.uniform(-spread, spread))


import contextlib
