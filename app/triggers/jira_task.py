import logging
import re

from telethon import events

from app.config import settings
from app.services.jira_client import JiraClient

logger = logging.getLogger("smartsummary")


async def handle_create_task(event: events.NewMessage.Event):
    chat_id = event.chat_id
    sender = event.sender_id
    text = event.raw_text or ""
    logger.info("*** TRIGGER: 'создай задачу' in chat=%s from sender=%s", chat_id, sender)
    try:
        body = re.sub(r"(?i)^(сделай|создай)\s+задачу\s*", "", text).strip()
        key_match = re.search(r"\b([A-Z][A-Z0-9]{1,9})\b", body)
        if not key_match:
            await event.reply("❌ Укажи проект: Создай задачу DC")
            return
        project_key = key_match.group(1)

        reply_msg = await event.get_reply_message()
        if not reply_msg or not reply_msg.raw_text:
            await event.reply("❌ Реплайни на сообщение с текстом задачи")
            return

        full_text = reply_msg.raw_text.strip()
        short = full_text.split("\n")[0].split(". ")[0]
        summary = short[:100] if len(short) > 100 else short
        description = full_text

        jira = JiraClient.get()
        result = await jira.create_issue(project_key, summary, description)
        issue_key = result["key"]
        jira_base = settings.jira_url.rstrip("/")
        await event.reply(
            f"✅ Задача создана: {issue_key}\n"
            f"📝 {summary}\n"
            f"🔗 {jira_base}/browse/{issue_key}"
        )
        logger.info("*** Jira issue created: %s", issue_key)
    except Exception as e:
        logger.error("*** ERROR creating Jira issue: %s", e, exc_info=True)
        await event.reply(f"❌ Ошибка создания задачи: {e}")
