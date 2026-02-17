import logging
from datetime import datetime, timedelta, timezone

from openai import AsyncOpenAI

from app.config import settings
from app.monitor import get_messages as get_buffered_messages
from app.telegram_client import get_client

logger = logging.getLogger("smartsummary")

_openai_client: AsyncOpenAI | None = None

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


def get_openai_client() -> AsyncOpenAI:
    global _openai_client
    if _openai_client is None:
        _openai_client = AsyncOpenAI(api_key=settings.openai_api_key)
    return _openai_client


async def fetch_messages(chat_id: int, limit: int = 200) -> list[dict]:
    client = get_client()
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


async def fetch_today_messages(chat_id: int) -> list[dict]:
    """Fetch messages from today only (Novosibirsk timezone)."""
    from zoneinfo import ZoneInfo

    tz = ZoneInfo(settings.timezone)
    now = datetime.now(tz)
    start_of_day = now.replace(hour=0, minute=0, second=0, microsecond=0)

    client = get_client()
    messages = await client.get_messages(
        chat_id,
        limit=500,
        offset_date=now,
    )
    result = []
    for m in messages:
        if not m.raw_text:
            continue
        msg_time = m.date.astimezone(tz)
        if msg_time < start_of_day:
            break
        result.append({
            "sender": getattr(m.sender, "first_name", str(m.sender_id)),
            "text": m.raw_text,
            "date": m.date.isoformat(),
        })
    return result


def _format_messages(msgs: list[dict]) -> str:
    return "\n".join(
        f"[{m['date']}] {m.get('sender', m.get('sender_id', '?'))}: {m['text']}"
        for m in msgs
    )


async def summarize(chat_id: int, use_buffer: bool = False, limit: int = 200) -> str:
    if use_buffer:
        msgs = get_buffered_messages(chat_id)
    else:
        msgs = await fetch_messages(chat_id, limit=limit)

    if not msgs:
        return "Нет сообщений для суммаризации."

    conversation = _format_messages(msgs)
    logger.info(">>> SUMMARIZE REQUEST: chat=%s, messages=%d", chat_id, len(msgs))

    ai = get_openai_client()
    response = await ai.chat.completions.create(
        model=settings.openai_model,
        max_completion_tokens=1024,
        messages=[{"role": "user", "content": TASK_SUMMARY_PROMPT + conversation}],
    )

    result = response.choices[0].message.content.strip()
    logger.info("<<< SUMMARIZE RESPONSE:\n%s", result)
    return result


async def summarize_chat_for_trigger(chat_id: int) -> str:
    """Summarize today's messages for in-chat trigger."""
    msgs = await fetch_today_messages(chat_id)
    if not msgs:
        return "За сегодня в этом чате нет сообщений."

    conversation = _format_messages(msgs)
    logger.info(">>> TRIGGER SUMMARIZE: chat=%s, messages=%d", chat_id, len(msgs))

    ai = get_openai_client()
    response = await ai.chat.completions.create(
        model=settings.openai_model,
        max_completion_tokens=1024,
        messages=[{"role": "user", "content": TASK_SUMMARY_PROMPT + conversation}],
    )

    result = response.choices[0].message.content.strip()
    logger.info("<<< TRIGGER SUMMARIZE RESPONSE:\n%s", result)
    return result


def _build_chat_link(entity) -> str:
    """Build a clickable Telegram link for a chat entity (HTML format)."""
    from telethon.tl.types import User, Channel, Chat

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
        # private channel/group: strip -100 prefix
        channel_id = entity.id
        return f'<a href="https://t.me/c/{channel_id}/1">{name}</a>'

    if isinstance(entity, Chat):
        name = entity.title or str(entity.id)
        return name  # basic groups have no deep link

    return str(getattr(entity, "title", None) or getattr(entity, "first_name", str(entity)))


async def summarize_single_chat(chat_id: int) -> tuple[str, str, str] | None:
    """Summarize a single chat's today messages.

    Returns (chat_name, chat_link_html, summary_text) or None if no messages.
    """
    client = get_client()
    try:
        entity = await client.get_entity(chat_id)
    except Exception as e:
        logger.error("Error getting entity for chat %s: %s", chat_id, e)
        return None

    chat_name = getattr(entity, "title", None) or getattr(entity, "first_name", str(chat_id))
    chat_link = _build_chat_link(entity)

    msgs = await fetch_today_messages(chat_id)
    if not msgs:
        return None

    conversation = _format_messages(msgs)
    logger.info(">>> SINGLE CHAT SUMMARY: chat=%s (%s), messages=%d", chat_id, chat_name, len(msgs))

    ai = get_openai_client()
    response = await ai.chat.completions.create(
        model=settings.openai_model,
        max_completion_tokens=1024,
        messages=[{"role": "user", "content": TASK_SUMMARY_PROMPT + conversation}],
    )

    summary = response.choices[0].message.content.strip()
    logger.info("<<< SINGLE CHAT SUMMARY for %s:\n%s", chat_name, summary)
    return chat_name, chat_link, summary


async def build_daily_overview(chat_summaries: list[tuple[str, str]]) -> str:
    """Build an overall daily analysis from individual chat summaries.

    Args:
        chat_summaries: list of (chat_name, summary_text) tuples.

    Returns:
        HTML-formatted overview text.
    """
    parts = []
    for name, summary in chat_summaries:
        # обрезаем каждый саммари до ~500 символов чтобы не перегрузить контекст
        short = summary[:500] + "..." if len(summary) > 500 else summary
        parts.append(f"--- {name} ---\n{short}")

    full_text = "\n\n".join(parts)
    logger.info(">>> DAILY OVERVIEW: %d chats, input length: %d chars", len(chat_summaries), len(full_text))

    ai = get_openai_client()
    response = await ai.chat.completions.create(
        model=settings.openai_model,
        max_completion_tokens=1500,
        messages=[{"role": "user", "content": DAILY_OVERVIEW_PROMPT + full_text}],
    )

    result = response.choices[0].message.content.strip()
    logger.info("<<< DAILY OVERVIEW RESPONSE:\n%s", result)
    return result
