from __future__ import annotations

from typing import Any, Iterable

from .models import AttachmentRef, InboundEvent, QuotedRef


def _get(payload: dict[str, Any], *names: str, default: Any = None) -> Any:
    for name in names:
        if name in payload and payload[name] is not None:
            return payload[name]
    return default


def _extract_text(payload: dict[str, Any]) -> str:
    text = _get(payload, "text", default=None)
    if isinstance(text, dict):
        content = text.get("content")
        if content:
            return str(content).strip()
    if hasattr(text, "content"):
        content = getattr(text, "content", None)
        if content:
            return str(content).strip()
    if isinstance(text, str) and text.strip():
        return text.strip()

    rich = _get(payload, "richText", "rich_text", default=None)
    if isinstance(rich, list):
        parts = [str(item.get("text", "")).strip() for item in rich if isinstance(item, dict)]
        collapsed = " ".join(part for part in parts if part)
        if collapsed:
            return collapsed

    rich_container = _get(payload, "richTextContent", "rich_text_content", default=None)
    if isinstance(rich_container, dict):
        rich_list = rich_container.get("richTextList") or rich_container.get("rich_text_list") or []
        if isinstance(rich_list, list):
            parts = [str(item.get("text", "")).strip() for item in rich_list if isinstance(item, dict)]
            collapsed = " ".join(part for part in parts if part)
            if collapsed:
                return collapsed

    content = _get(payload, "content", default=None)
    if isinstance(content, str):
        return content.strip()
    return ""


def _extract_mentions(payload: dict[str, Any], chatbot_user_id: str | None) -> tuple[tuple[str, ...], bool]:
    raw_mentions = _get(payload, "atUsers", "at_users", "mentions", default=())
    mentions: list[str] = []
    mentions_bot = bool(_get(payload, "isInAtList", "is_in_at_list", default=False))
    if isinstance(raw_mentions, Iterable) and not isinstance(raw_mentions, (str, bytes, dict)):
        for item in raw_mentions:
            if isinstance(item, dict):
                for key in ("dingtalkId", "staffId", "userid", "userId"):
                    value = item.get(key)
                    if value:
                        text = str(value).strip()
                        if text:
                            mentions.append(text)
                            if chatbot_user_id and text == chatbot_user_id:
                                mentions_bot = True
            elif item:
                text = str(item).strip()
                if text:
                    mentions.append(text)
                    if chatbot_user_id and text == chatbot_user_id:
                        mentions_bot = True
    return tuple(dict.fromkeys(mentions)), mentions_bot


def _extract_quote(payload: dict[str, Any], account_id: str) -> QuotedRef | None:
    quoted = _get(payload, "quoted", "quote", default=None)
    if isinstance(quoted, dict):
        message_id = _get(quoted, "messageId", "msgId", "message_id", default="")
        if message_id:
            return QuotedRef(
                message_id=str(message_id),
                sender_id=_get(quoted, "senderId", "sender_id", default=None),
                sender_name=_get(quoted, "senderNick", "sender_name", default=None),
                text=_get(quoted, "text", "content", default=None),
            )
    quoted_msg_id = _get(payload, "quoteMsgId", "quotedMsgId", "quoted_msg_id", default=None)
    if quoted_msg_id:
        return QuotedRef(message_id=str(quoted_msg_id))
    return None


def _extract_attachments(payload: dict[str, Any]) -> tuple[AttachmentRef, ...]:
    attachments: list[AttachmentRef] = []
    media_type = _get(payload, "msgtype", "messageType", "message_type", default=None)
    download_code = _get(payload, "downloadCode", "download_code", default=None)
    if media_type and media_type not in {"text", "markdown"}:
        attachments.append(
            AttachmentRef(
                media_type=str(media_type),
                download_code=str(download_code) if download_code else None,
                file_name=_get(payload, "fileName", "file_name", default=None),
                mime_type=_get(payload, "mimeType", "mime_type", default=None),
                size_bytes=int(_get(payload, "fileSize", "file_size", default=0) or 0) or None,
            )
        )
    return tuple(attachments)


def parse_inbound_message(payload: dict[str, Any], *, account_id: str) -> InboundEvent:
    chatbot_user_id = _get(payload, "chatbotUserId", "chatbot_user_id", default=None)
    conversation_type = str(_get(payload, "conversationType", "conversation_type", default="1"))
    chat_type = "group" if conversation_type == "2" else "direct"
    sender_id = str(_get(payload, "senderStaffId", "sender_staff_id", "senderId", "sender_id", default="")).strip()
    sender_original_id = str(_get(payload, "senderId", "sender_id", default=sender_id)).strip()
    mentions, mentions_bot = _extract_mentions(payload, chatbot_user_id)
    return InboundEvent(
        account_id=account_id,
        message_id=str(_get(payload, "msgId", "messageId", "message_id", default="")).strip(),
        conversation_id=str(_get(payload, "conversationId", "conversation_id", default="")).strip(),
        conversation_title=_get(payload, "conversationTitle", "conversation_title", default=None),
        chat_type=chat_type,
        sender_id=sender_id or sender_original_id,
        sender_name=str(_get(payload, "senderNick", "sender_nick", default="Unknown")).strip() or "Unknown",
        sender_staff_id=sender_id or None,
        chatbot_user_id=str(chatbot_user_id).strip() if chatbot_user_id else None,
        text=_extract_text(payload),
        mentions=mentions,
        mentions_bot=mentions_bot,
        session_webhook=_get(payload, "sessionWebhook", "session_webhook", default=None),
        quoted=_extract_quote(payload, account_id),
        attachments=_extract_attachments(payload),
        created_at_ms=int(_get(payload, "createAt", "create_at", default=0) or 0) or None,
        raw_payload=dict(payload),
    )
