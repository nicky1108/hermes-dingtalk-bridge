from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

import yaml


DEFAULT_HERMES_API_BASE = "http://127.0.0.1:8642/v1"
DEFAULT_STORE_PATH = Path.home() / ".hermes" / "dingtalk-bridge.db"
DEFAULT_CONFIG_PATH = Path.home() / ".hermes" / "dingtalk-bridge.yaml"
DEFAULT_ENV_PATH = Path.home() / ".hermes" / ".env"
DEFAULT_MESSAGE_CHUNK_SIZE = 3500


@dataclass
class BridgeConfig:
    client_id: str = ""
    client_secret: str = ""
    hermes_api_base: str = DEFAULT_HERMES_API_BASE
    hermes_api_key: str = ""
    hermes_model: str = "hermes-agent"
    account_id: str = "default"
    conversation_prefix: str = "dingtalk"
    store_path: Path = DEFAULT_STORE_PATH
    log_level: str = "INFO"
    require_mention_in_groups: bool = True
    group_allowlist: tuple[str, ...] = ()
    dm_allowlist: tuple[str, ...] = ()
    session_ttl_days: int = 7
    initial_reconnect_delay_ms: int = 1000
    max_reconnect_delay_ms: int = 60000
    reconnect_jitter: float = 0.3
    inactivity_reconnect_seconds: int = 0
    request_timeout_seconds: int = 60
    stream_read_timeout_seconds: int = 300
    message_chunk_size: int = DEFAULT_MESSAGE_CHUNK_SIZE
    session_store_max_messages: int = 5000
    include_metadata_header: bool = True
    reply_mode: str = "markdown"
    card_template_id: str = ""
    ack_reaction_enabled: bool = True
    ack_reaction_name: str = "🤔思考中"
    hermes_healthcheck_interval_seconds: int = 20
    hermes_healthcheck_max_failures: int = 3
    config_path: Path = DEFAULT_CONFIG_PATH

    def validate(self) -> list[str]:
        errors: list[str] = []
        if not self.client_id:
            errors.append("missing client_id")
        if not self.client_secret:
            errors.append("missing client_secret")
        if not self.hermes_api_key:
            errors.append("missing hermes_api_key")
        if not self.hermes_api_base:
            errors.append("missing hermes_api_base")
        if self.initial_reconnect_delay_ms <= 0:
            errors.append("initial_reconnect_delay_ms must be > 0")
        if self.max_reconnect_delay_ms < self.initial_reconnect_delay_ms:
            errors.append("max_reconnect_delay_ms must be >= initial_reconnect_delay_ms")
        if not 0 <= self.reconnect_jitter <= 1:
            errors.append("reconnect_jitter must be between 0 and 1")
        if self.session_ttl_days <= 0:
            errors.append("session_ttl_days must be > 0")
        if self.message_chunk_size <= 0:
            errors.append("message_chunk_size must be > 0")
        if self.stream_read_timeout_seconds <= 0:
            errors.append("stream_read_timeout_seconds must be > 0")
        if self.reply_mode not in {"markdown", "card"}:
            errors.append("reply_mode must be markdown or card")
        if self.reply_mode == "card" and not self.card_template_id:
            errors.append("card_template_id is required when reply_mode=card")
        return errors


def _as_tuple(value: Any) -> tuple[str, ...]:
    if value is None:
        return ()
    if isinstance(value, str):
        parts = [segment.strip() for segment in value.split(",")]
        return tuple(segment for segment in parts if segment)
    if isinstance(value, Iterable):
        out: list[str] = []
        for item in value:
            text = str(item).strip()
            if text:
                out.append(text)
        return tuple(out)
    return ()


def _as_bool(value: Any, default: bool) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    text = str(value).strip().lower()
    if text in {"1", "true", "yes", "on"}:
        return True
    if text in {"0", "false", "no", "off"}:
        return False
    return default


def _load_yaml(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    return data if isinstance(data, dict) else {}


def _pick_nested(config: dict[str, Any]) -> dict[str, Any]:
    for key in ("dingtalk_bridge", "plugins", "hermes_dingtalk"):
        current = config.get(key)
        if key == "plugins" and isinstance(current, dict):
            nested = current.get("hermes_dingtalk")
            if isinstance(nested, dict):
                return nested
        if isinstance(current, dict):
            return current
    return config


def _load_dotenv(path: Path) -> dict[str, str]:
    if not path.exists():
        return {}
    data: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8", errors="ignore").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        data[key.strip()] = value.strip().strip('"').strip("'")
    return data


def _env_lookup(name: str, dotenv: dict[str, str], default: Any = None) -> Any:
    return os.getenv(name, dotenv.get(name, default))


def load_config(config_path: str | Path | None = None) -> BridgeConfig:
    explicit_path = Path(config_path).expanduser() if config_path else None
    path = explicit_path or Path(os.getenv("HERMES_DINGTALK_CONFIG", DEFAULT_CONFIG_PATH)).expanduser()
    raw = _pick_nested(_load_yaml(path))

    hermes_config_path = Path.home() / ".hermes" / "config.yaml"
    if hermes_config_path != path and hermes_config_path.exists():
        hermes_raw = _pick_nested(_load_yaml(hermes_config_path))
        merged = {**hermes_raw, **raw}
    else:
        merged = dict(raw)

    dotenv = _load_dotenv(DEFAULT_ENV_PATH)
    client_id = _env_lookup("HERMES_DINGTALK_CLIENT_ID", dotenv)
    if not client_id:
        client_id = _env_lookup("DINGTALK_CLIENT_ID", dotenv, merged.get("client_id", ""))
    client_secret = _env_lookup("HERMES_DINGTALK_CLIENT_SECRET", dotenv)
    if not client_secret:
        client_secret = _env_lookup("DINGTALK_CLIENT_SECRET", dotenv, merged.get("client_secret", ""))
    hermes_api_key = _env_lookup("API_SERVER_KEY", dotenv)
    if not hermes_api_key:
        hermes_api_key = _env_lookup("HERMES_DINGTALK_HERMES_API_KEY", dotenv, merged.get("hermes_api_key", ""))

    cfg = BridgeConfig(
        client_id=str(client_id or "").strip(),
        client_secret=str(client_secret or "").strip(),
        hermes_api_base=str(_env_lookup("HERMES_DINGTALK_HERMES_API_BASE", dotenv, merged.get("hermes_api_base", DEFAULT_HERMES_API_BASE))).rstrip("/"),
        hermes_api_key=str(hermes_api_key or "").strip(),
        hermes_model=str(_env_lookup("HERMES_DINGTALK_MODEL", dotenv, merged.get("hermes_model", "hermes-agent"))).strip(),
        account_id=str(_env_lookup("HERMES_DINGTALK_ACCOUNT_ID", dotenv, merged.get("account_id", "default"))).strip() or "default",
        conversation_prefix=str(_env_lookup("HERMES_DINGTALK_CONVERSATION_PREFIX", dotenv, merged.get("conversation_prefix", "dingtalk"))).strip() or "dingtalk",
        store_path=Path(_env_lookup("HERMES_DINGTALK_STORE_PATH", dotenv, merged.get("store_path", DEFAULT_STORE_PATH))).expanduser(),
        log_level=str(_env_lookup("HERMES_DINGTALK_LOG_LEVEL", dotenv, merged.get("log_level", "INFO"))).strip() or "INFO",
        require_mention_in_groups=_as_bool(_env_lookup("HERMES_DINGTALK_REQUIRE_MENTION_IN_GROUPS", dotenv, merged.get("require_mention_in_groups")), True),
        group_allowlist=_as_tuple(_env_lookup("HERMES_DINGTALK_GROUP_ALLOWLIST", dotenv, merged.get("group_allowlist"))),
        dm_allowlist=_as_tuple(_env_lookup("HERMES_DINGTALK_DM_ALLOWLIST", dotenv, merged.get("dm_allowlist"))),
        session_ttl_days=int(_env_lookup("HERMES_DINGTALK_SESSION_TTL_DAYS", dotenv, merged.get("session_ttl_days", 7))),
        initial_reconnect_delay_ms=int(_env_lookup("HERMES_DINGTALK_INITIAL_RECONNECT_DELAY_MS", dotenv, merged.get("initial_reconnect_delay_ms", 1000))),
        max_reconnect_delay_ms=int(_env_lookup("HERMES_DINGTALK_MAX_RECONNECT_DELAY_MS", dotenv, merged.get("max_reconnect_delay_ms", 60000))),
        reconnect_jitter=float(_env_lookup("HERMES_DINGTALK_RECONNECT_JITTER", dotenv, merged.get("reconnect_jitter", 0.3))),
        inactivity_reconnect_seconds=int(_env_lookup("HERMES_DINGTALK_INACTIVITY_RECONNECT_SECONDS", dotenv, merged.get("inactivity_reconnect_seconds", 0))),
        request_timeout_seconds=int(_env_lookup("HERMES_DINGTALK_REQUEST_TIMEOUT_SECONDS", dotenv, merged.get("request_timeout_seconds", 60))),
        stream_read_timeout_seconds=int(_env_lookup("HERMES_DINGTALK_STREAM_READ_TIMEOUT_SECONDS", dotenv, merged.get("stream_read_timeout_seconds", 300))),
        message_chunk_size=int(_env_lookup("HERMES_DINGTALK_MESSAGE_CHUNK_SIZE", dotenv, merged.get("message_chunk_size", DEFAULT_MESSAGE_CHUNK_SIZE))),
        session_store_max_messages=int(_env_lookup("HERMES_DINGTALK_SESSION_STORE_MAX_MESSAGES", dotenv, merged.get("session_store_max_messages", 5000))),
        include_metadata_header=_as_bool(_env_lookup("HERMES_DINGTALK_INCLUDE_METADATA_HEADER", dotenv, merged.get("include_metadata_header")), True),
        reply_mode=str(_env_lookup("HERMES_DINGTALK_REPLY_MODE", dotenv, merged.get("reply_mode", "markdown"))).strip() or "markdown",
        card_template_id=str(_env_lookup("HERMES_DINGTALK_CARD_TEMPLATE_ID", dotenv, merged.get("card_template_id", ""))).strip(),
        ack_reaction_enabled=_as_bool(_env_lookup("HERMES_DINGTALK_ACK_REACTION_ENABLED", dotenv, merged.get("ack_reaction_enabled")), True),
        ack_reaction_name=str(_env_lookup("HERMES_DINGTALK_ACK_REACTION_NAME", dotenv, merged.get("ack_reaction_name", "🤔思考中"))).strip() or "🤔思考中",
        hermes_healthcheck_interval_seconds=int(_env_lookup("HERMES_DINGTALK_HERMES_HEALTHCHECK_INTERVAL_SECONDS", dotenv, merged.get("hermes_healthcheck_interval_seconds", 20))),
        hermes_healthcheck_max_failures=int(_env_lookup("HERMES_DINGTALK_HERMES_HEALTHCHECK_MAX_FAILURES", dotenv, merged.get("hermes_healthcheck_max_failures", 3))),
        config_path=path,
    )
    return cfg
