import logging

from telethon import events

logger = logging.getLogger("smartsummary")


async def handle_summarize(event: events.NewMessage.Event):
    chat_id = event.chat_id
    sender = event.sender_id
    logger.info("*** TRIGGER: 'суммаризация' in chat=%s from sender=%s", chat_id, sender)
    try:
        from app.summarizer import summarize_chat_for_trigger

        summary = await summarize_chat_for_trigger(chat_id)
        await event.reply(f"#summary\n\n{summary}", parse_mode="html")
        logger.info("*** SENT summary reply to chat=%s", chat_id)
    except Exception as e:
        logger.error("*** ERROR summarizing: %s", e, exc_info=True)
