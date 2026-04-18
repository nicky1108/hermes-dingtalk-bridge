from __future__ import annotations

import asyncio
import contextlib
import logging
import threading
import time
from collections import defaultdict

from .access_control import decide_access
from .ack_reaction import AckReactionService
from .card_sender import CardReplyHandle
from .config import BridgeConfig
from .connection_manager import ConnectionManager
from .dingtalk_client import DingTalkClient, DingTalkStreamRunner
from .hermes_client import HermesClient, HermesStreamFallbackRequested
from .inbound_parser import parse_inbound_message
from .message_codec import build_conversation_name, build_hermes_input
from .models import BridgeStatus, ConversationBinding, MessageRecord
from .outbound_sender import OutboundSender
from .session_store import SessionStore
from .runtime_status import initialize_runtime_status, mark_inbound, mark_runtime_error, mark_runtime_stopped, status_path

logger = logging.getLogger(__name__)


class CardProgressReporter:
    def __init__(self, sender: OutboundSender, event, logger) -> None:
        self._sender = sender
        self._event = event
        self._logger = logger
        self._handle: CardReplyHandle | None = None
        self._lock = threading.Lock()
        self._progress_lines = [
            "已接收钉钉消息",
            "正在整理上下文",
        ]
        self._tool_lines: list[str] = []
        self._answer_text = ""
        self._phase = "starting"
        self._last_push_at = 0.0
        self._last_pushed_answer_length = 0
        self._last_pushed_content = ""
        self._disabled = False

    @property
    def active(self) -> bool:
        return not self._disabled and self._handle is not None

    @property
    def card_handle(self) -> CardReplyHandle | None:
        return self._handle

    def start(self) -> None:
        handle = self._sender.start_card_reply(self._event, self._render_locked())
        if handle is None:
            self._disabled = True
            return
        self._handle = handle

    def mark_context_ready(self, *, has_quote: bool, attachment_count: int) -> None:
        details: list[str] = ["上下文已整理"]
        if has_quote:
            details.append("包含引用消息")
        if attachment_count:
            details.append(f"附件 {attachment_count} 个")
        with self._lock:
            self._phase = "waiting"
            self._progress_lines = [
                "已接收钉钉消息",
                "已整理上下文" + (f"（{'，'.join(details[1:])}）" if len(details) > 1 else ""),
                "正在请求 Hermes 生成回复",
            ]
            self._push_locked(force=True)

    def on_tool_event(self, message: str) -> None:
        with self._lock:
            if message not in self._tool_lines:
                self._tool_lines.append(message)
            self._push_locked(force=True)

    def on_text_delta(self, delta: str) -> None:
        with self._lock:
            self._phase = "streaming"
            self._answer_text += delta
            self._push_locked()

    def finalize(self, answer: str) -> None:
        with self._lock:
            self._phase = "done"
            self._answer_text = answer.strip()
            self._progress_lines = [
                "已接收钉钉消息",
                "已整理上下文",
                "已获取 Hermes 回复",
                "已回写当前卡片",
            ]
            self._push_locked(force=True, finalize=True)

    def fail(self, exc: Exception) -> None:
        with self._lock:
            self._phase = "error"
            self._tool_lines.append(f"处理失败: {str(exc).strip()[:200] or exc.__class__.__name__}")
            self._push_locked(force=True, finalize=True, is_error=True)

    def _push_locked(self, *, force: bool = False, finalize: bool = False, is_error: bool = False) -> None:
        if not self.active:
            return
        now = time.monotonic()
        if not force and now - self._last_push_at < 0.35 and len(self._answer_text) - self._last_pushed_answer_length < 120:
            return
        content = self._render_locked()
        if not force and content == self._last_pushed_content:
            return
        if not self._sender.update_card_reply(self._handle, content, finalize=finalize, is_error=is_error):
            self._disabled = True
            return
        self._last_push_at = now
        self._last_pushed_answer_length = len(self._answer_text)
        self._last_pushed_content = content

    def _render_locked(self) -> str:
        title = {
            "starting": "处理中",
            "waiting": "处理中",
            "streaming": "正在生成回复",
            "done": "处理完成",
            "error": "处理失败",
        }.get(self._phase, "处理中")
        lines = [title, "", "处理进度："]
        for item in self._progress_lines:
            lines.append(f"- {item}")
        if self._tool_lines:
            lines.extend(["", "工具与步骤摘要："])
            for item in self._tool_lines[-6:]:
                lines.append(f"- {item}")
        lines.extend(["", "当前回复：", ""])
        if self._answer_text.strip():
            lines.append(self._answer_text.strip())
        elif self._phase == "error":
            lines.append("当前请求未能完成，请查看上面的错误摘要。")
        else:
            lines.append("正在生成，请稍候…")
        return "\n".join(lines).strip()


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
        initialize_runtime_status(self.config, source="bridge-service")
        self.store.prune_processed(ttl_days=self.config.session_ttl_days)
        health_task = asyncio.create_task(self._monitor_hermes_health())
        try:
            await self._connection_manager.run_forever()
        finally:
            health_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await health_task
            mark_runtime_stopped(self.config, reason="service-run-exit")

    def shutdown(self) -> None:
        logger.info("Shutting down Hermes DingTalk bridge")
        mark_runtime_stopped(self.config, reason="shutdown")
        try:
            self._connection_manager.stop()
        except Exception as exc:  # pragma: no cover - defensive shutdown path
            logger.debug("Ignoring bridge stop error during shutdown: %s", exc)
        try:
            self.store.close()
        except Exception as exc:  # pragma: no cover
            logger.debug("Ignoring bridge store close error during shutdown: %s", exc)

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
                    mark_runtime_error(self.config, f"Hermes health monitor threshold reached after {failures} failures")
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
        if event.message_id and event.conversation_id:
            mark_inbound(self.config, message_id=event.message_id, conversation_id=event.conversation_id)
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
                progress = CardProgressReporter(self.sender, event, logger)
                binding = self.store.get_binding(event.account_id, event.conversation_id)
                conversation = binding.hermes_conversation if binding else build_conversation_name(
                    self.config, event.account_id, event.conversation_id
                )
                progress.start()
                quote = event.quoted
                if quote and not quote.text and quote.message_id:
                    stored_quote = self.store.get_quote(event.account_id, quote.message_id)
                    if stored_quote is not None:
                        quote = stored_quote
                progress.mark_context_ready(
                    has_quote=quote is not None,
                    attachment_count=len(event.attachments),
                )
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
                try:
                    reply = await asyncio.to_thread(
                        self.hermes.create_response_stream if progress.active else self.hermes.create_response,
                        conversation=conversation,
                        input_text=hermes_input,
                        previous_response_id=binding.last_response_id if binding else None,
                        metadata=metadata,
                        **(
                            {
                                "on_text_delta": progress.on_text_delta,
                                "on_tool_event": progress.on_tool_event,
                            }
                            if progress.active
                            else {}
                        ),
                    )
                except HermesStreamFallbackRequested:
                    progress.on_tool_event("当前 Hermes 服务未提供增量事件，已回退到普通回复模式")
                    reply = await asyncio.to_thread(
                        self.hermes.create_response,
                        conversation=conversation,
                        input_text=hermes_input,
                        previous_response_id=binding.last_response_id if binding else None,
                        metadata=metadata,
                    )
                logger.info("Hermes reply for %s: %r", event.message_id, reply.text[:200])
                progress.finalize(reply.text)
                if not progress.active:
                    await self.sender.send_reply(event, reply.text, card_handle=progress.card_handle)
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
            except Exception as exc:
                progress.fail(exc)
                raise
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
            "runtime_status_path": str(status_path(self.config)),
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
