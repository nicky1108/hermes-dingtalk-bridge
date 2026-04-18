from __future__ import annotations

import sqlite3
import time
from pathlib import Path
from typing import Optional

from .models import ConversationBinding, MessageRecord, QuotedRef


class SessionStore:
    def __init__(self, path: Path, *, max_messages: int = 5000) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._max_messages = max_messages
        self._conn = sqlite3.connect(str(self.path), check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._init_db()

    def _init_db(self) -> None:
        self._conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS processed_messages (
                account_id TEXT NOT NULL,
                message_id TEXT NOT NULL,
                processed_at_ms INTEGER NOT NULL,
                PRIMARY KEY(account_id, message_id)
            );
            CREATE TABLE IF NOT EXISTS conversation_bindings (
                account_id TEXT NOT NULL,
                conversation_id TEXT NOT NULL,
                hermes_conversation TEXT NOT NULL,
                last_response_id TEXT,
                session_webhook TEXT,
                updated_at_ms INTEGER NOT NULL,
                PRIMARY KEY(account_id, conversation_id)
            );
            CREATE TABLE IF NOT EXISTS message_records (
                account_id TEXT NOT NULL,
                message_id TEXT NOT NULL,
                conversation_id TEXT NOT NULL,
                sender_id TEXT NOT NULL,
                sender_name TEXT NOT NULL,
                text TEXT NOT NULL,
                created_at_ms INTEGER NOT NULL,
                PRIMARY KEY(account_id, message_id)
            );
            """
        )
        self._conn.commit()

    def close(self) -> None:
        self._conn.close()

    def is_processed(self, account_id: str, message_id: str) -> bool:
        row = self._conn.execute(
            "SELECT 1 FROM processed_messages WHERE account_id = ? AND message_id = ?",
            (account_id, message_id),
        ).fetchone()
        return row is not None

    def mark_processed(self, account_id: str, message_id: str, *, now_ms: Optional[int] = None) -> None:
        self._conn.execute(
            "INSERT OR REPLACE INTO processed_messages(account_id, message_id, processed_at_ms) VALUES (?, ?, ?)",
            (account_id, message_id, now_ms or int(time.time() * 1000)),
        )
        self._conn.commit()

    def prune_processed(self, *, ttl_days: int) -> int:
        cutoff = int(time.time() * 1000) - ttl_days * 24 * 60 * 60 * 1000
        cur = self._conn.execute(
            "DELETE FROM processed_messages WHERE processed_at_ms < ?",
            (cutoff,),
        )
        self._conn.commit()
        return cur.rowcount

    def get_binding(self, account_id: str, conversation_id: str) -> Optional[ConversationBinding]:
        row = self._conn.execute(
            "SELECT * FROM conversation_bindings WHERE account_id = ? AND conversation_id = ?",
            (account_id, conversation_id),
        ).fetchone()
        if row is None:
            return None
        return ConversationBinding(
            account_id=row["account_id"],
            conversation_id=row["conversation_id"],
            hermes_conversation=row["hermes_conversation"],
            last_response_id=row["last_response_id"],
            session_webhook=row["session_webhook"],
            updated_at_ms=row["updated_at_ms"],
        )

    def upsert_binding(self, binding: ConversationBinding) -> None:
        self._conn.execute(
            """
            INSERT OR REPLACE INTO conversation_bindings(
                account_id, conversation_id, hermes_conversation, last_response_id, session_webhook, updated_at_ms
            ) VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                binding.account_id,
                binding.conversation_id,
                binding.hermes_conversation,
                binding.last_response_id,
                binding.session_webhook,
                binding.updated_at_ms or int(time.time() * 1000),
            ),
        )
        self._conn.commit()

    def remember_message(self, record: MessageRecord) -> None:
        self._conn.execute(
            """
            INSERT OR REPLACE INTO message_records(
                account_id, message_id, conversation_id, sender_id, sender_name, text, created_at_ms
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                record.account_id,
                record.message_id,
                record.conversation_id,
                record.sender_id,
                record.sender_name,
                record.text,
                record.created_at_ms,
            ),
        )
        self._conn.execute(
            "DELETE FROM message_records WHERE rowid NOT IN (SELECT rowid FROM message_records ORDER BY created_at_ms DESC LIMIT ?)",
            (self._max_messages,),
        )
        self._conn.commit()

    def get_quote(self, account_id: str, message_id: str) -> Optional[QuotedRef]:
        row = self._conn.execute(
            "SELECT message_id, sender_id, sender_name, text FROM message_records WHERE account_id = ? AND message_id = ?",
            (account_id, message_id),
        ).fetchone()
        if row is None:
            return None
        return QuotedRef(
            message_id=row["message_id"],
            sender_id=row["sender_id"],
            sender_name=row["sender_name"],
            text=row["text"],
        )
