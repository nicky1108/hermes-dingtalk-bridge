from __future__ import annotations

import sqlite3
from pathlib import Path

from .card_sender import CardReplyService
from .config import load_config
from .dingtalk_client import DingTalkClient


def main() -> int:
    cfg = load_config(Path.home() / '.hermes' / 'dingtalk-bridge.yaml')
    db = Path.home() / '.hermes' / 'dingtalk-bridge.db'
    conn = sqlite3.connect(db)
    conn.row_factory = sqlite3.Row
    row = conn.execute('SELECT sender_id, sender_name, conversation_id, message_id FROM message_records ORDER BY created_at_ms DESC LIMIT 1').fetchone()
    conn.close()
    if row is None:
        print('no recent inbound message found')
        return 1
    raw_payload = {
        'conversationType': '1',
        'senderId': row['sender_id'],
        'senderStaffId': row['sender_id'],
        'senderNick': row['sender_name'],
        'senderCorpId': '',
        'conversationId': row['conversation_id'],
        'msgId': row['message_id'],
    }
    service = CardReplyService(DingTalkClient(cfg), logger=__import__('logging').getLogger('card-probe'))
    out = service.send_card_reply(raw_payload, 'card 权限复测（streaming content）', cfg.card_template_id)
    print('out_track_id', out)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
