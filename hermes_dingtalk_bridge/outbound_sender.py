from __future__ import annotations

from .card_sender import CardReplyService
from .config import BridgeConfig
from .models import InboundEvent


class OutboundSender:
    def __init__(self, config: BridgeConfig, dingtalk_client, logger=None) -> None:
        self.config = config
        self.client = dingtalk_client
        self.logger = logger
        self.card_replies = CardReplyService(dingtalk_client, logger)

    @staticmethod
    def _chunk(text: str, size: int) -> list[str]:
        if len(text) <= size:
            return [text]
        chunks: list[str] = []
        current = text
        while current:
            if len(current) <= size:
                chunks.append(current)
                break
            split_at = current.rfind("\n", 0, size)
            if split_at <= 0:
                split_at = size
            chunks.append(current[:split_at].rstrip())
            current = current[split_at:].lstrip()
        return [chunk for chunk in chunks if chunk]

    async def send_reply(self, event: InboundEvent, text: str) -> None:
        body = text.strip() or "(Hermes returned an empty reply.)"
        if self.config.reply_mode == "card" and self.config.card_template_id:
            card_instance_id = self.card_replies.send_card_reply(
                event.raw_payload,
                body,
                self.config.card_template_id,
            )
            if card_instance_id:
                return
            if self.logger:
                self.logger.warning("Falling back to markdown reply after card delivery failure")
        for chunk in self._chunk(body, self.config.message_chunk_size):
            if event.session_webhook:
                self.client.send_session_markdown(event.session_webhook, chunk)
            else:
                self.client.send_proactive_markdown(event.conversation_id, chunk)
