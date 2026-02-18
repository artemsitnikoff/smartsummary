import logging
from datetime import datetime
from zoneinfo import ZoneInfo

from app.config import settings
from app.services.ai_client import AIClient
from app.services.telegram_service import TelegramService

logger = logging.getLogger("smartsummary")

TASK_SUMMARY_PROMPT = """\
Проанализируй эту переписку из Telegram чата.

Сделай:
1. <b>Краткое резюме</b> — о чём шла речь (2-3 предложения)
2. <b>Задачи и ответственные</b> — кто какие задачи взял на себя или кому что поручили. \
Формат: "Имя — задача". Если задач нет — напиши "Явных задач не обнаружено."
3. <b>Ключевые решения</b> — что было решено или согласовано

Пиши на русском, кратко и по делу. Для выделения используй HTML-тег <b>...</b>, НЕ markdown.

Переписка:
"""

DAILY_OVERVIEW_PROMPT = """\
Ты получишь саммари нескольких Telegram чатов за день. \
Проанализируй их и составь ОБЩИЙ ОТЧЁТ ДНЯ.

Формат:
1. <b>🔑 Главное за день</b> — 3-5 самых важных вещей из ВСЕХ чатов. \
Каждый пункт выдели <b>жирным</b>. Это должны быть ключевые решения, критичные задачи, важные договорённости.
2. <b>📌 Все задачи</b> — сводный список задач из всех чатов: "Имя — задача (чат)". \
Если задач нет — пропусти этот блок.
3. <b>⚠️ Требует внимания</b> — что может забыться или где есть риски/дедлайны. \
Если нечего — пропусти.

Пиши на русском. Кратко, по делу. Используй HTML-теги <b>...</b> для выделения важного.

Саммари чатов:
"""


def _format_messages(msgs: list[dict]) -> str:
    return "\n".join(
        f"[{m['date']}] {m.get('sender', m.get('sender_id', '?'))}: {m['text']}"
        for m in msgs
    )


async def _fetch_messages(chat_id: int, since: datetime | None = None, limit: int = 500) -> list[dict]:
    """Fetch messages from a chat. If `since` is given, only messages after that time."""
    tg = TelegramService.get()
    client = tg.client

    if since:
        tz = ZoneInfo(settings.timezone)
        now = datetime.now(tz)
        messages = await client.get_messages(chat_id, limit=limit, offset_date=now)
        result = []
        for m in messages:
            if not m.raw_text:
                continue
            msg_time = m.date.astimezone(tz)
            if msg_time < since:
                break
            result.append({
                "sender": getattr(m.sender, "first_name", str(m.sender_id)),
                "text": m.raw_text,
                "date": m.date.isoformat(),
            })
        return result
    else:
        messages = await client.get_messages(chat_id, limit=limit)
        return [
            {
                "sender": getattr(m.sender, "first_name", str(m.sender_id)),
                "text": m.raw_text or "",
                "date": m.date.isoformat(),
            }
            for m in messages
            if m.raw_text
        ]


async def _summarize_messages(msgs: list[dict], max_tokens: int = 1024) -> str:
    """Run GPT summarization on a list of messages."""
    conversation = _format_messages(msgs)
    ai = AIClient.get()
    return await ai.complete(TASK_SUMMARY_PROMPT + conversation, max_tokens=max_tokens)


async def summarize(chat_id: int, use_buffer: bool = False, limit: int = 200) -> str:
    if use_buffer:
        from app.chat_state import state
        msgs = state.get_messages(chat_id)
    else:
        msgs = await _fetch_messages(chat_id, limit=limit)

    if not msgs:
        return "Нет сообщений для суммаризации."

    logger.info(">>> SUMMARIZE REQUEST: chat=%s, messages=%d", chat_id, len(msgs))
    result = await _summarize_messages(msgs)
    logger.info("<<< SUMMARIZE RESPONSE:\n%s", result)
    return result


async def summarize_chat_for_trigger(chat_id: int) -> str:
    """Summarize today's messages for in-chat trigger."""
    tz = ZoneInfo(settings.timezone)
    start_of_day = datetime.now(tz).replace(hour=0, minute=0, second=0, microsecond=0)

    msgs = await _fetch_messages(chat_id, since=start_of_day)
    if not msgs:
        return "За сегодня в этом чате нет сообщений."

    logger.info(">>> TRIGGER SUMMARIZE: chat=%s, messages=%d", chat_id, len(msgs))
    result = await _summarize_messages(msgs)
    logger.info("<<< TRIGGER SUMMARIZE RESPONSE:\n%s", result)
    return result


def _build_chat_link(entity) -> str:
    from telethon.tl.types import Channel, Chat, User

    if isinstance(entity, User):
        name = entity.first_name or str(entity.id)
        if entity.last_name:
            name += f" {entity.last_name}"
        if entity.username:
            return f'<a href="https://t.me/{entity.username}">{name}</a>'
        return f'<a href="tg://user?id={entity.id}">{name}</a>'

    if isinstance(entity, Channel):
        name = entity.title or str(entity.id)
        if entity.username:
            return f'<a href="https://t.me/{entity.username}">{name}</a>'
        channel_id = entity.id
        return f'<a href="https://t.me/c/{channel_id}/1">{name}</a>'

    if isinstance(entity, Chat):
        name = entity.title or str(entity.id)
        return name

    return str(getattr(entity, "title", None) or getattr(entity, "first_name", str(entity)))


async def summarize_single_chat(chat_id: int) -> tuple[str, str, str] | None:
    """Summarize a single chat's today messages.

    Returns (chat_name, chat_link_html, summary_text) or None if no messages.
    """
    tg = TelegramService.get()
    client = tg.client
    try:
        entity = await client.get_entity(chat_id)
    except Exception as e:
        logger.error("Error getting entity for chat %s: %s", chat_id, e)
        return None

    chat_name = getattr(entity, "title", None) or getattr(entity, "first_name", str(chat_id))
    chat_link = _build_chat_link(entity)

    tz = ZoneInfo(settings.timezone)
    start_of_day = datetime.now(tz).replace(hour=0, minute=0, second=0, microsecond=0)
    msgs = await _fetch_messages(chat_id, since=start_of_day)
    if not msgs:
        return None

    logger.info(">>> SINGLE CHAT SUMMARY: chat=%s (%s), messages=%d", chat_id, chat_name, len(msgs))
    summary = await _summarize_messages(msgs)
    logger.info("<<< SINGLE CHAT SUMMARY for %s:\n%s", chat_name, summary)
    return chat_name, chat_link, summary


async def build_daily_overview(chat_summaries: list[tuple[str, str]]) -> str:
    parts = []
    for name, summary in chat_summaries:
        short = summary[:500] + "..." if len(summary) > 500 else summary
        parts.append(f"--- {name} ---\n{short}")

    full_text = "\n\n".join(parts)
    logger.info(">>> DAILY OVERVIEW: %d chats, input length: %d chars", len(chat_summaries), len(full_text))

    ai = AIClient.get()
    result = await ai.complete(DAILY_OVERVIEW_PROMPT + full_text, max_tokens=1500)
    logger.info("<<< DAILY OVERVIEW RESPONSE:\n%s", result)
    return result
