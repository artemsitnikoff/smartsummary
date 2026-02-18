import re

from telethon import TelegramClient, events

from app.chat_state import state
from app.config import settings
from app.triggers.auto_reply import handle_greenkeev, handle_sitnikov
from app.triggers.free_slots import handle_find_time
from app.triggers.jira_task import handle_create_task
from app.triggers.meeting import handle_create_meeting
from app.triggers.summarize import handle_summarize


def register_all(client: TelegramClient):
    @client.on(events.NewMessage(incoming=True, outgoing=True))
    async def on_new_message(event: events.NewMessage.Event):
        chat_id = event.chat_id
        sender = event.sender_id
        text = event.raw_text or ""

        if not text:
            return

        if sender == settings.my_user_id:
            state.track_outgoing(chat_id)

        if sender != settings.my_user_id:
            state.track_incoming(chat_id)

        if text.lower().strip() == "суммаризация":
            return await handle_summarize(event)

        if "ситников" in text.lower():
            await handle_sitnikov(event)

        if "гринкеев" in text.lower():
            await handle_greenkeev(event)

        if re.match(r"(?i)(сделай|создай)\s+задачу", text):
            return await handle_create_task(event)

        if re.match(r"(?i)найди\s+время", text):
            return await handle_find_time(event)

        if re.match(r"(?i)(сделай|создай)\s+встречу", text):
            return await handle_create_meeting(event)

        state.buffer_message(chat_id, sender, text, event.date)
