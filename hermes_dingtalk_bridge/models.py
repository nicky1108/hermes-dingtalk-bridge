from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional


@dataclass
class AttachmentRef:
    media_type: str
    download_code: Optional[str] = None
    file_name: Optional[str] = None
    mime_type: Optional[str] = None
    size_bytes: Optional[int] = None


@dataclass
class QuotedRef:
    message_id: str
    sender_id: Optional[str] = None
    sender_name: Optional[str] = None
    text: Optional[str] = None


@dataclass
class InboundEvent:
    account_id: str
    message_id: str
    conversation_id: str
    conversation_title: Optional[str]
    chat_type: str
    sender_id: str
    sender_name: str
    sender_staff_id: Optional[str]
    chatbot_user_id: Optional[str]
    text: str
    mentions: tuple[str, ...] = ()
    mentions_bot: bool = False
    session_webhook: Optional[str] = None
    quoted: Optional[QuotedRef] = None
    attachments: tuple[AttachmentRef, ...] = ()
    created_at_ms: Optional[int] = None
    raw_payload: dict[str, Any] = field(default_factory=dict)


@dataclass
class AccessDecision:
    allowed: bool
    reason: str


@dataclass
class HermesReply:
    text: str
    response_id: Optional[str] = None
    conversation: Optional[str] = None
    raw_response: dict[str, Any] = field(default_factory=dict)


@dataclass
class ConversationBinding:
    account_id: str
    conversation_id: str
    hermes_conversation: str
    last_response_id: Optional[str] = None
    session_webhook: Optional[str] = None
    updated_at_ms: Optional[int] = None


@dataclass
class MessageRecord:
    account_id: str
    message_id: str
    conversation_id: str
    sender_id: str
    sender_name: str
    text: str
    created_at_ms: int


@dataclass
class BridgeStatus:
    ok: bool
    message: str
    details: dict[str, Any] = field(default_factory=dict)
