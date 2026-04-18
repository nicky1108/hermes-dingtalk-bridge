"""Hermes plugin entrypoint for the standalone DingTalk bridge."""

from __future__ import annotations

import sys
from pathlib import Path

_PLUGIN_ROOT = Path(__file__).resolve().parent
if str(_PLUGIN_ROOT) not in sys.path:
    sys.path.insert(0, str(_PLUGIN_ROOT))

from hermes_dingtalk_bridge.plugin import register

__all__ = ["register"]
