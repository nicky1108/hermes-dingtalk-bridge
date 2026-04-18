from __future__ import annotations

import asyncio
import atexit
import sys
import threading
from typing import Optional

from .config import load_config
from .logging_utils import configure_logging
from .service import BridgeService

_bridge_thread: Optional[threading.Thread] = None
_bridge_service: Optional[BridgeService] = None


def should_autostart_in_process() -> bool:
    argv = [arg.lower() for arg in sys.argv]
    return any(arg == 'gateway' for arg in argv) and any(arg == 'run' for arg in argv)


def _start_bridge(reason: str) -> None:
    global _bridge_thread, _bridge_service
    if _bridge_thread is not None:
        return
    config = load_config()
    logger = configure_logging(config.log_level)
    errors = config.validate()
    if errors:
        logger.warning('Hermes DingTalk bridge autostart skipped (%s): %s', reason, '; '.join(errors))
        return
    _bridge_service = BridgeService(config)

    def runner() -> None:
        asyncio.run(_bridge_service.run())

    _bridge_thread = threading.Thread(target=runner, name='hermes-dingtalk-bridge', daemon=True)
    _bridge_thread.start()
    logger.info('Hermes DingTalk bridge autostarted inside gateway process via %s', reason)
    atexit.register(stop_bridge)


def autostart_bridge_if_gateway() -> None:
    if not should_autostart_in_process():
        return
    _start_bridge('plugin-register')


def autostart_bridge_from_gateway_hook() -> None:
    _start_bridge('gateway-hook')


def stop_bridge() -> None:
    global _bridge_service
    if _bridge_service is not None:
        _bridge_service.shutdown()
        _bridge_service = None
