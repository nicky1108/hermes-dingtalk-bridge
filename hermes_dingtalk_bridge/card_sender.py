from __future__ import annotations

import hashlib
import uuid
from typing import Optional

from .dingtalk_client import DingTalkClient


def _space_payload(raw_payload: dict, client_id: str) -> dict:
    conversation_type = str(raw_payload.get("conversationType", "1"))
    if conversation_type == "2":
        return {
            "openSpaceId": f"dtv1.card//IM_GROUP.{raw_payload.get('conversationId')}",
            "imGroupOpenDeliverModel": {
                "robotCode": client_id,
                "extension": {"dynamicSummary": "true"},
            },
        }
    sender_staff_id = raw_payload.get("senderStaffId") or raw_payload.get("senderId")
    return {
        "openSpaceId": f"dtv1.card//IM_ROBOT.{sender_staff_id}",
        "imRobotOpenDeliverModel": {
            "spaceType": "IM_ROBOT",
            "robotCode": client_id,
            "extension": {"dynamicSummary": "true"},
        },
    }


class CardReplyService:
    """Simplified DingTalk AI-card flow following soimy's createAndDeliver + streaming pattern.

    This bridge currently assumes the target template exposes a single card variable key: `content`.
    """

    CONTENT_KEY = "content"
    CONFIG_KEY = "config"

    def __init__(self, client: DingTalkClient, logger) -> None:
        self.client = client
        self.logger = logger

    def send_card_reply(self, raw_payload: dict, text: str, template_id: str) -> Optional[str]:
        out_track_id = self._gen_out_track_id(raw_payload)
        self._create_and_deliver(raw_payload, template_id, out_track_id)
        self._stream_finalize(out_track_id, text)
        if self.logger:
            self.logger.info(
                "DingTalk card reply sent out_track_id=%s template_id=%s content_key=%s",
                out_track_id,
                template_id,
                self.CONTENT_KEY,
            )
        return out_track_id

    def _create_and_deliver(self, raw_payload: dict, template_id: str, out_track_id: str) -> None:
        create_body = {
            "cardTemplateId": template_id,
            "outTrackId": out_track_id,
            "cardData": {
                "cardParamMap": {
                    self.CONFIG_KEY: '{"autoLayout":true,"enableForward":true}',
                    self.CONTENT_KEY: "",
                }
            },
            "callbackType": "STREAM",
            "imGroupOpenSpaceModel": {"supportForward": True},
            "imRobotOpenSpaceModel": {"supportForward": True},
            "userIdType": 1,
            **_space_payload(raw_payload, self.client.config.client_id),
        }
        self.client.post_openapi("/v1.0/card/instances/createAndDeliver", create_body)

    def _stream_finalize(self, out_track_id: str, text: str) -> None:
        stream_body = {
            "outTrackId": out_track_id,
            "guid": str(uuid.uuid4()),
            "key": self.CONTENT_KEY,
            "content": text,
            "isFull": True,
            "isFinalize": True,
            "isError": False,
        }
        self.client.put_openapi("/v1.0/card/streaming", stream_body)

    @staticmethod
    def _gen_out_track_id(raw_payload: dict) -> str:
        factor = "%s_%s_%s_%s_%s" % (
            raw_payload.get("senderId", ""),
            raw_payload.get("senderCorpId", ""),
            raw_payload.get("conversationId", ""),
            raw_payload.get("msgId", raw_payload.get("messageId", "")),
            str(uuid.uuid1()),
        )
        digest = hashlib.sha256()
        digest.update(factor.encode("utf-8"))
        return digest.hexdigest()
