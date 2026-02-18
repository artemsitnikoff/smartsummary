import asyncio
import logging
from contextlib import asynccontextmanager
from datetime import datetime
from zoneinfo import ZoneInfo

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from fastapi import FastAPI

from app.api.routes import router
from app.config import settings
from app.date_experiment import setup_experiment_handler
from app.services.bitrix_client import BitrixClient
from app.services.jira_client import JiraClient
from app.services.telegram_service import TelegramService
from app.triggers import register_all

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("smartsummary")

scheduler = AsyncIOScheduler()


async def get_today_dialogs() -> list[int]:
    """Get today's personal (1-on-1) chats + configured report groups."""
    tz = ZoneInfo(settings.timezone)
    start_of_day = datetime.now(tz).replace(hour=0, minute=0, second=0, microsecond=0)

    tg = TelegramService.get()
    dialogs = await tg.client.get_dialogs()
    today_chats = []
    for d in dialogs:
        if not d.date or d.date.astimezone(tz) < start_of_day:
            continue
        if d.is_user:
            today_chats.append(d.id)
        elif d.id in settings.report_group_ids:
            today_chats.append(d.id)

    logger.info(
        "=== Found %d dialogs for report (%d personal + groups from config)",
        len(today_chats),
        sum(1 for d in dialogs if d.is_user and d.date and d.date.astimezone(tz) >= start_of_day),
    )
    return today_chats


async def daily_summary_job():
    """Summarizes each chat with today's messages, then sends overall analysis."""
    from app.summarizer import build_daily_overview, summarize_single_chat

    today_chats = await get_today_dialogs()

    if not today_chats:
        logger.info("=== No chats with messages today, skipping")
        return

    tg = TelegramService.get()
    chat_summaries = []
    parts = []

    for chat_id in today_chats:
        try:
            result = await summarize_single_chat(chat_id)
            if result is None:
                continue
            name, link, summary = result
            summary_html = tg.clean_html(summary)
            block = f"#summary\n📋 <b>{name}</b>\n{link}\n\n{summary_html}"
            parts.append(block)
            chat_summaries.append((name, summary))
            logger.info("=== Summarized chat: %s", name)
        except Exception as e:
            logger.error("=== DAILY SUMMARY ERROR for chat %s: %s", chat_id, e, exc_info=True)

    if not chat_summaries:
        await tg.client.send_message("me", "📋 Дневной отчёт: за сегодня нет чатов с сообщениями.")
        return

    full_text = "\n\n━━━━━━━━━━━━━━━\n\n".join(parts)
    await tg.send_long_message(full_text)
    logger.info("=== Daily summaries sent: %d chats", len(chat_summaries))

    await asyncio.sleep(2)
    try:
        overview = await build_daily_overview(chat_summaries)
        overview_html = tg.clean_html(overview)
        await tg.send_long_message(f"#summary\n📊 <b>Обзор дня</b>\n\n{overview_html}")
        logger.info("=== Daily overview sent")
    except Exception as e:
        logger.error("=== DAILY OVERVIEW ERROR: %s", e, exc_info=True)


@asynccontextmanager
async def lifespan(app: FastAPI):
    tg = TelegramService.get()
    await tg.connect()
    if not await tg.is_authorized():
        await tg.disconnect()
        raise RuntimeError(
            "Telegram session not authorized. Run 'python auth.py' first."
        )

    register_all(tg.client)
    setup_experiment_handler(tg.client)
    await tg.client.catch_up()

    scheduler.add_job(
        daily_summary_job,
        CronTrigger(hour=23, minute=15, timezone=settings.timezone),
        id="daily_summary",
    )
    scheduler.start()
    logger.info("=== Scheduler started: daily at 23:15 [%s]", settings.timezone)

    yield

    scheduler.shutdown()
    await tg.disconnect()
    await BitrixClient.get().close()
    await JiraClient.get().close()


app = FastAPI(title="SmartSummary", lifespan=lifespan)
app.include_router(router, prefix="/api")
