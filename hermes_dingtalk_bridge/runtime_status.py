from __future__ import annotations

import json
import threading
import time
from pathlib import Path
from typing import Any

from .config import BridgeConfig


def _status_path(config: BridgeConfig) -> Path:
    return config.store_path.with_suffix('.status.json')


def write_runtime_status(config: BridgeConfig, **patch: Any) -> None:
    path = _status_path(config)
    path.parent.mkdir(parents=True, exist_ok=True)
    current: dict[str, Any] = {}
    if path.exists():
        try:
            current = json.loads(path.read_text(encoding='utf-8'))
            if not isinstance(current, dict):
                current = {}
        except Exception:
            current = {}
    current.update(patch)
    current['updated_at'] = time.time()
    path.write_text(json.dumps(current, indent=2, ensure_ascii=False), encoding='utf-8')


def initialize_runtime_status(config: BridgeConfig, *, source: str) -> None:
    write_runtime_status(
        config,
        running=True,
        source=source,
        reply_mode=config.reply_mode,
        account_id=config.account_id,
        card_template_id=config.card_template_id,
        ack_reaction_enabled=config.ack_reaction_enabled,
        thread_name=threading.current_thread().name,
        started_at=time.time(),
        last_error=None,
    )


def mark_runtime_error(config: BridgeConfig, message: str) -> None:
    write_runtime_status(config, last_error=message)


def mark_runtime_stopped(config: BridgeConfig, *, reason: str) -> None:
    write_runtime_status(config, running=False, stop_reason=reason, stopped_at=time.time())


def mark_inbound(config: BridgeConfig, *, message_id: str, conversation_id: str) -> None:
    write_runtime_status(
        config,
        last_inbound_at=time.time(),
        last_message_id=message_id,
        last_conversation_id=conversation_id,
    )


def status_path(config: BridgeConfig) -> Path:
    return _status_path(config)
