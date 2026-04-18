from __future__ import annotations

import asyncio
import logging
import time
from collections import defaultdict

from .access_control import decide_access
from .ack_reaction import AckReactionService
from .config import BridgeConfig
from .connection_manager import ConnectionManager
from .dingtalk_client import DingTalkClient, DingTalkStreamRunner
from .hermes_client import HermesClient
from .inbound_parser import parse_inbound_message
from .message_codec import build_conversation_name, build_hermes_input
from .models import BridgeStatus, ConversationBinding, MessageRecord
from .outbound_sender import OutboundSender
from .session_store import SessionStore

logger = logging.getLogger(__name__)


class BridgeService:
    def __init__(self, config: BridgeConfig) -> None:
        self.config = config
        self.store = SessionStore(config.store_path, max_messages=config.session_store_max_messages)
        self.dingtalk = DingTalkClient(config)
        self.hermes = HermesClient(config)
        self.sender = OutboundSender(config, self.dingtalk, logger=logger)
        self.ack_reactions = AckReactionService(self.dingtalk, logger)
        self._locks: dict[str, asyncio.Lock] = defaultdict(asyncio.Lock)
        self._connection_manager = ConnectionManager(
            config,
            runner_factory=lambda: DingTalkStreamRunner(config, self.handle_raw_message),
            logger=logger,
        )

    async def run(self) -> None:
        logger.info(
            "Starting Hermes DingTalk bridge for account=%s conversation_prefix=%s reply_mode=%s",
            self.config.account_id,
            self.config.conversation_prefix,
            self.config.reply_mode,
        )
        self.store.prune_processed(ttl_days=self.config.session_ttl_days)
        health_task = asyncio.create_task(self._monitor_hermes_health())
        try:
            await self._connection_manager.run_forever()
        finally:
            health_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await health_task

    def shutdown(self) -> None:
        logger.info("Shutting down Hermes DingTalk bridge")
        self._connection_manager.stop()
        self.store.close()

    async def _monitor_hermes_health(self) -> None:
        failures = 0
        interval = max(5, self.config.hermes_healthcheck_interval_seconds)
        while True:
            await asyncio.sleep(interval)
            try:
                await asyncio.to_thread(self.hermes.health)
                failures = 0
            except Exception as exc:
                failures += 1
                logger.warning(
                    "Hermes health monitor failure %s/%s: %s",
                    failures,
                    self.config.hermes_healthcheck_max_failures,
                    exc,
                )
                if failures >= self.config.hermes_healthcheck_max_failures:
                    logger.error("Hermes health monitor reached failure threshold; stopping bridge")
                    self._connection_manager.stop()
                    return

    async def handle_raw_message(self, payload: dict) -> None:
        self._connection_manager.notify_activity()
        logger.info("Raw callback payload keys=%s", sorted(payload.keys()))
        event = parse_inbound_message(payload, account_id=self.config.account_id)
        logger.info(
            "Parsed inbound event message_id=%s conversation_id=%s chat_type=%s sender_id=%s mentions_bot=%s text=%r",
            event.message_id,
            event.conversation_id,
            event.chat_type,
            event.sender_id,
            event.mentions_bot,
            event.text,
        )
        if not event.message_id or not event.conversation_id:
            logger.debug("Skipping DingTalk message without ids: %s", payload)
            return
        if self.store.is_processed(event.account_id, event.message_id):
            logger.debug("Skipping duplicate DingTalk message %s", event.message_id)
            return
        lock = self._locks[event.conversation_id]
        async with lock:
            if self.store.is_processed(event.account_id, event.message_id):
                return
            decision = decide_access(event, self.config)
            logger.info("Access decision for %s: allowed=%s reason=%s", event.message_id, decision.allowed, decision.reason)
            if not decision.allowed:
                self.store.mark_processed(event.account_id, event.message_id)
                return

            reaction_attached_at: float | None = None
            if self.config.ack_reaction_enabled:
                attached = await asyncio.to_thread(
                    self.ack_reactions.attach,
                    message_id=event.message_id,
                    conversation_id=event.conversation_id,
                    reaction_name=self.config.ack_reaction_name,
                )
                if attached:
                    reaction_attached_at = time.time()

            try:
                binding = self.store.get_binding(event.account_id, event.conversation_id)
                conversation = binding.hermes_conversation if binding else build_conversation_name(
                    self.config, event.account_id, event.conversation_id
                )
                quote = event.quoted
                if quote and not quote.text and quote.message_id:
                    stored_quote = self.store.get_quote(event.account_id, quote.message_id)
                    if stored_quote is not None:
                        quote = stored_quote
                hermes_input = build_hermes_input(event, self.config, quote)
                metadata = {
                    "platform": "dingtalk",
                    "account_id": event.account_id,
                    "chat_type": event.chat_type,
                    "conversation_id": event.conversation_id,
                    "sender_id": event.sender_id,
                    "sender_name": event.sender_name,
                    "message_id": event.message_id,
                }
                logger.info("Sending message %s to Hermes conversation=%s", event.message_id, conversation)
                reply = await asyncio.to_thread(
                    self.hermes.create_response,
                    conversation=conversation,
                    input_text=hermes_input,
                    previous_response_id=binding.last_response_id if binding else None,
                    metadata=metadata,
                )
                logger.info("Hermes reply for %s: %r", event.message_id, reply.text[:200])
                await self.sender.send_reply(event, reply.text)
                logger.info("Reply dispatched back to DingTalk for %s", event.message_id)
                now_ms = event.created_at_ms or int(time.time() * 1000)
                self.store.upsert_binding(
                    ConversationBinding(
                        account_id=event.account_id,
                        conversation_id=event.conversation_id,
                        hermes_conversation=conversation,
                        last_response_id=reply.response_id,
                        session_webhook=event.session_webhook,
                        updated_at_ms=now_ms,
                    )
                )
                self.store.remember_message(
                    MessageRecord(
                        account_id=event.account_id,
                        message_id=event.message_id,
                        conversation_id=event.conversation_id,
                        sender_id=event.sender_id,
                        sender_name=event.sender_name,
                        text=event.text,
                        created_at_ms=now_ms,
                    )
                )
                self.store.mark_processed(event.account_id, event.message_id, now_ms=now_ms)
            finally:
                if reaction_attached_at is not None:
                    await asyncio.to_thread(
                        self.ack_reactions.recall_after_min_visible,
                        message_id=event.message_id,
                        conversation_id=event.conversation_id,
                        attached_at=reaction_attached_at,
                        reaction_name=self.config.ack_reaction_name,
                    )

    def doctor(self) -> BridgeStatus:
        errors = self.config.validate()
        details = {
            "config_path": str(self.config.config_path),
            "store_path": str(self.config.store_path),
            "hermes_api_base": self.config.hermes_api_base,
            "reply_mode": self.config.reply_mode,
            "card_template_id": self.config.card_template_id,
        }
        if errors:
            return BridgeStatus(False, "; ".join(errors), details)
        try:
            health = self.hermes.health()
            details["hermes_health"] = health
        except Exception as exc:
            return BridgeStatus(False, f"Hermes health check failed: {exc}", details)
        try:
            token = self.dingtalk.get_access_token()
            details["dingtalk_access_token"] = {"ok": bool(token), "prefix": token[:6] if token else ""}
        except Exception as exc:
            return BridgeStatus(False, f"DingTalk credential check failed: {exc}", details)
        return BridgeStatus(True, "ok", details)


import contextlib
