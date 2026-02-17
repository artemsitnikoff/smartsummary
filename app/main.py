import asyncio
import logging
import re
from contextlib import asynccontextmanager

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

from fastapi import FastAPI

from app.api.routes import router
from app.config import settings

from app.date_experiment import setup_experiment_handler
from app.monitor import setup_handlers
from app.telegram_client import get_client

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("smartsummary")

scheduler = AsyncIOScheduler()


async def get_today_dialogs() -> list[int]:
    """Get today's personal (1-on-1) chats + configured report groups."""
    from datetime import datetime
    from zoneinfo import ZoneInfo

    tz = ZoneInfo(settings.timezone)
    start_of_day = datetime.now(tz).replace(hour=0, minute=0, second=0, microsecond=0)

    client = get_client()
    dialogs = await client.get_dialogs()
    today_chats = []
    for d in dialogs:
        if not d.date or d.date.astimezone(tz) < start_of_day:
            continue
        # личные чаты (не группы, не каналы)
        if d.is_user:
            today_chats.append(d.id)
        # группы из справочника
        elif d.id in settings.report_group_ids:
            today_chats.append(d.id)

    logger.info("=== Found %d dialogs for report (%d personal + groups from config)",
                len(today_chats), sum(1 for d in dialogs if d.is_user and d.date and d.date.astimezone(tz) >= start_of_day))
    return today_chats


TG_MSG_LIMIT = 4096


def clean_html(text: str) -> str:
    """Convert markdown to Telegram-safe HTML."""
    # **bold** → <b>bold</b>
    text = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", text)
    # <br>, <br/>, <br /> → newline
    text = re.sub(r"<br\s*/?>", "\n", text)
    # strip unsupported HTML tags (keep only b, i, u, s, a, code, pre)
    text = re.sub(r"</?(?!b|/b|i|/i|u|/u|s|/s|a|/a|code|/code|pre|/pre)[^>]+>", "", text)
    return text


async def send_long_message(client, text: str, parse_mode: str = "html"):
    """Send a message to Saved Messages, splitting if > 4096 chars."""
    while text:
        if len(text) <= TG_MSG_LIMIT:
            await client.send_message("me", text, parse_mode=parse_mode)
            break
        # ищем последний перенос строки до лимита
        cut = text.rfind("\n", 0, TG_MSG_LIMIT)
        if cut == -1:
            cut = TG_MSG_LIMIT
        await client.send_message("me", text[:cut], parse_mode=parse_mode)
        text = text[cut:].lstrip("\n")
        await asyncio.sleep(2)


async def daily_summary_job():
    """Summarizes each chat with today's messages, then sends overall analysis."""
    from app.summarizer import summarize_single_chat, build_daily_overview

    today_chats = await get_today_dialogs()

    if not today_chats:
        logger.info("=== No chats with messages today, skipping")
        return

    client = get_client()
    chat_summaries = []
    parts = []  # блоки текста для группировки

    for chat_id in today_chats:
        try:
            result = await summarize_single_chat(chat_id)
            if result is None:
                continue
            name, link, summary = result
            summary_html = clean_html(summary)
            block = f"#summary\n📋 <b>{name}</b>\n{link}\n\n{summary_html}"
            parts.append(block)
            chat_summaries.append((name, summary))
            logger.info("=== Summarized chat: %s", name)
        except Exception as e:
            logger.error("=== DAILY SUMMARY ERROR for chat %s: %s", chat_id, e, exc_info=True)

    if not chat_summaries:
        await client.send_message("me", "📋 Дневной отчёт: за сегодня нет чатов с сообщениями.")
        return

    # группируем блоки в сообщения по ~4096 символов
    full_text = "\n\n━━━━━━━━━━━━━━━\n\n".join(parts)
    await send_long_message(client, full_text)
    logger.info("=== Daily summaries sent: %d chats", len(chat_summaries))

    # финальный обзор дня
    await asyncio.sleep(2)
    try:
        overview = await build_daily_overview(chat_summaries)
        overview_html = clean_html(overview)
        await send_long_message(client, f"#summary\n📊 <b>Обзор дня</b>\n\n{overview_html}")
        logger.info("=== Daily overview sent")
    except Exception as e:
        logger.error("=== DAILY OVERVIEW ERROR: %s", e, exc_info=True)


@asynccontextmanager
async def lifespan(app: FastAPI):
    client = get_client()
    await client.connect()
    if not await client.is_user_authorized():
        await client.disconnect()
        raise RuntimeError(
            "Telegram session not authorized. Run 'python auth.py' first."
        )
    setup_handlers(client)
    setup_experiment_handler(client)

    # расписание: дневной отчёт
    scheduler.add_job(
        daily_summary_job,
        CronTrigger(hour=23, minute=15, timezone=settings.timezone),
        id="daily_summary",
    )
    scheduler.start()
    logger.info("=== Scheduler started: daily at 23:15 [%s]", settings.timezone)

    yield

    scheduler.shutdown()
    await client.disconnect()


app = FastAPI(title="SmartSummary", lifespan=lifespan)
app.include_router(router, prefix="/api")
