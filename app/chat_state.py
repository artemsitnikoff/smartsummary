from collections import defaultdict, deque
from datetime import datetime


class ChatState:
    def __init__(self):
        self.monitored: set[int] = set()
        self.buffer: dict[int, deque] = defaultdict(lambda: deque(maxlen=500))
        self.today_active: set[int] = set()
        self.today_incoming: set[int] = set()

    def track_outgoing(self, chat_id: int):
        self.today_active.add(chat_id)

    def track_incoming(self, chat_id: int):
        self.today_incoming.add(chat_id)

    def buffer_message(self, chat_id: int, sender_id: int, text: str, date: datetime):
        if chat_id in self.monitored:
            self.buffer[chat_id].append({
                "sender_id": sender_id,
                "text": text,
                "date": date.isoformat(),
            })

    def clear_daily(self):
        self.today_active.clear()
        self.today_incoming.clear()

    def add_monitored(self, chat_id: int):
        self.monitored.add(chat_id)

    def remove_monitored(self, chat_id: int):
        self.monitored.discard(chat_id)

    def get_monitored(self) -> list[int]:
        return list(self.monitored)

    def get_active_chats(self) -> list[int]:
        return list(self.today_active)

    def get_incoming_chats(self) -> list[int]:
        return list(self.today_incoming)

    def get_messages(self, chat_id: int) -> list[dict]:
        return list(self.buffer.get(chat_id, []))


state = ChatState()
