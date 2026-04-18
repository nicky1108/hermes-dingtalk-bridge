from __future__ import annotations

import logging


def configure_logging(level: str = "INFO") -> logging.Logger:
    resolved = getattr(logging, level.upper(), logging.INFO)
    logging.basicConfig(
        level=resolved,
        format="%(asctime)s %(levelname)s %(name)s - %(message)s",
    )
    return logging.getLogger("hermes_dingtalk_bridge")
