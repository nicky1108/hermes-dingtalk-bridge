from __future__ import annotations

from .config import BridgeConfig
from .models import AccessDecision, InboundEvent


def decide_access(event: InboundEvent, config: BridgeConfig) -> AccessDecision:
    if event.sender_id and event.chatbot_user_id and event.sender_id == event.chatbot_user_id:
        return AccessDecision(False, "self message")

    if event.chat_type == "direct":
        if config.dm_allowlist and event.sender_id not in set(config.dm_allowlist):
            return AccessDecision(False, "sender not in dm allowlist")
        return AccessDecision(True, "direct message allowed")

    if config.group_allowlist and event.conversation_id not in set(config.group_allowlist):
        return AccessDecision(False, "conversation not in group allowlist")

    if config.require_mention_in_groups and not event.mentions_bot:
        return AccessDecision(False, "group message missing bot mention")

    return AccessDecision(True, "group message allowed")
