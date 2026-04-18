from __future__ import annotations

import hashlib
import json
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
            },
        }
    sender_staff_id = raw_payload.get("senderStaffId") or raw_payload.get("senderId")
    return {
        "openSpaceId": f"dtv1.card//IM_ROBOT.{sender_staff_id}",
        "imRobotOpenDeliverModel": {"spaceType": "IM_ROBOT"},
    }


class CardReplyService:
    def __init__(self, client: DingTalkClient, logger) -> None:
        self.client = client
        self.logger = logger

    def send_card_reply(self, raw_payload: dict, text: str, template_id: str) -> Optional[str]:
        out_track_id = self._gen_out_track_id(raw_payload)
        create_body = {
            "cardTemplateId": template_id,
            "outTrackId": out_track_id,
            "cardData": {
                "cardParamMap": {
                    "content": text,
                    "markdown": text,
                    "text": text,
                    "body": text,
                    "message": text,
                    "answer": text,
                    "title": "Hermes",
                }
            },
            "callbackType": "STREAM",
            "imGroupOpenSpaceModel": {"supportForward": True},
            "imRobotOpenSpaceModel": {"supportForward": True},
        }
        self.client.post_openapi("/v1.0/card/instances", create_body)
        deliver_body = {
            "outTrackId": out_track_id,
            "userIdType": 1,
            **_space_payload(raw_payload, self.client.config.client_id),
        }
        self.client.post_openapi("/v1.0/card/instances/deliver", deliver_body)
        self.logger.info("DingTalk card reply sent out_track_id=%s template_id=%s", out_track_id, template_id)
        return out_track_id

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
