from __future__ import annotations

from .config import BridgeConfig
from .models import InboundEvent, QuotedRef


def build_conversation_name(config: BridgeConfig, account_id: str, conversation_id: str) -> str:
    return f"{config.conversation_prefix}:{account_id}:{conversation_id}"


def strip_leading_mentions(text: str) -> str:
    stripped = text.strip()
    while stripped.startswith("@"):
        parts = stripped.split(maxsplit=1)
        if len(parts) == 1:
            return ""
        stripped = parts[1].lstrip()
    return stripped


def _render_quote(quote: QuotedRef | None) -> str:
    if not quote:
        return ""
    sender = quote.sender_name or quote.sender_id or "unknown"
    text = (quote.text or "").strip()
    if len(text) > 500:
        text = text[:500] + "…"
    return (
        "[QuotedMessage]\n"
        f"From: {sender}\n"
        f"MessageId: {quote.message_id}\n"
        f"Text: {text}\n\n"
    )


def build_hermes_input(event: InboundEvent, config: BridgeConfig, quote: QuotedRef | None = None) -> str:
    sender_id = event.sender_id or "unknown"
    sender_name = event.sender_name or sender_id
    title = event.conversation_title or event.conversation_id
    user_text = strip_leading_mentions(event.text)
    attachment_lines = ""
    if event.attachments:
        rendered = [f"- {attachment.media_type} ({attachment.file_name or 'unnamed'})" for attachment in event.attachments]
        attachment_lines = "[Attachments]\n" + "\n".join(rendered) + "\n\n"
    return (
        f"[Platform] DingTalk\n"
        f"[AccountId] {event.account_id}\n"
        f"[ChatType] {event.chat_type}\n"
        f"[ConversationId] {event.conversation_id}\n"
        f"[ConversationTitle] {title}\n"
        f"[SenderId] {sender_id}\n"
        f"[SenderName] {sender_name}\n\n"
        f"{_render_quote(quote or event.quoted)}"
        f"{attachment_lines}"
        f"User message:\n{user_text.strip()}"
    ).strip()
