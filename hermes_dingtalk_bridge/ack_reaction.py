from __future__ import annotations

import time
from typing import Optional

from .dingtalk_client import DingTalkClient

THINKING_REACTION_NAME = "🤔思考中"
THINKING_EMOTION_ID = "2659900"
THINKING_EMOTION_BACKGROUND_ID = "im_bg_1"
ATTACH_DELAYS_MS = (0, 400, 1200)
RECALL_DELAYS_MS = (0, 1500, 5000)


class AckReactionService:
    def __init__(self, client: DingTalkClient, logger) -> None:
        self.client = client
        self.logger = logger

    def attach(self, *, message_id: str, conversation_id: str, reaction_name: str = THINKING_REACTION_NAME) -> bool:
        return self._retry("reply", ATTACH_DELAYS_MS, message_id, conversation_id, reaction_name)

    def recall(self, *, message_id: str, conversation_id: str, reaction_name: str = THINKING_REACTION_NAME) -> bool:
        return self._retry("recall", RECALL_DELAYS_MS, message_id, conversation_id, reaction_name)

    def recall_after_min_visible(
        self,
        *,
        message_id: str,
        conversation_id: str,
        attached_at: float,
        reaction_name: str = THINKING_REACTION_NAME,
        min_visible_ms: int = 1200,
    ) -> bool:
        elapsed_ms = int((time.time() - attached_at) * 1000)
        remaining = max(0, min_visible_ms - elapsed_ms)
        if remaining > 0:
            time.sleep(remaining / 1000)
        return self.recall(message_id=message_id, conversation_id=conversation_id, reaction_name=reaction_name)

    def _retry(self, endpoint: str, delays_ms: tuple[int, ...], message_id: str, conversation_id: str, reaction_name: str) -> bool:
        for index, delay_ms in enumerate(delays_ms):
            if delay_ms > 0:
                time.sleep(delay_ms / 1000)
            try:
                self.client.post_openapi(
                    f"/v1.0/robot/emotion/{endpoint}",
                    {
                        "robotCode": self.client.config.client_id,
                        "openMsgId": message_id,
                        "openConversationId": conversation_id,
                        "emotionType": 2,
                        "emotionName": reaction_name,
                        "textEmotion": {
                            "emotionId": THINKING_EMOTION_ID,
                            "emotionName": reaction_name,
                            "text": reaction_name,
                            "backgroundId": THINKING_EMOTION_BACKGROUND_ID,
                        },
                    },
                )
                self.logger.info(
                    "DingTalk ack reaction %s succeeded for msg=%s conversation=%s attempt=%s/%s",
                    endpoint,
                    message_id,
                    conversation_id,
                    index + 1,
                    len(delays_ms),
                )
                return True
            except Exception as exc:
                self.logger.warning(
                    "DingTalk ack reaction %s failed for msg=%s conversation=%s attempt=%s/%s: %s",
                    endpoint,
                    message_id,
                    conversation_id,
                    index + 1,
                    len(delays_ms),
                    exc,
                )
        return False
