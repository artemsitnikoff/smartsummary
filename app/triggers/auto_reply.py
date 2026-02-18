import logging
import random

from telethon import events

from app.services.ai_client import AIClient
from app.utils import strip_numbered_item

logger = logging.getLogger("smartsummary")

PIG_FACTS_PROMPT = """\
Придумай 3 МАКСИМАЛЬНО РЕДКИХ и малоизвестных факта о свиньях, хряках или поросятах. \
НЕ пиши банальщину вроде "свиньи умные", "свиньи чистоплотные", "у свиней хорошая память", \
"свиньи не потеют", "свиньи общаются звуками" — это все знают. \
Копай глубже: редкие породы, странные исторические случаи, необычная анатомия, \
дикие рекорды, военное применение, свиньи в космосе/науке/искусстве, \
генетические аномалии, кулинарные традиции разных стран, мифология, суды над свиньями \
в средневековье, свиньи-детекторы, гибриды — чем безумнее тем лучше. \
Каждый факт — 1-2 предложения. Формат:
1. ...
2. ...
3. ...
Без вступления и заключения, только факты. Каждый раз выдавай НОВЫЕ факты, не повторяйся."""

SENECA_PROMPT = """\
Напиши 3 цитаты Сенеки (Луций Анней Сенека, стоик). \
Бери РАЗНЫЕ произведения: "Нравственные письма к Луцилию", "О краткости жизни", \
"О блаженной жизни", "О гневе", "О стойкости мудреца", "О провидении" и др. \
Цитаты должны быть глубокие, философские, про жизнь, время, смерть, мужество, судьбу. \
НЕ повторяй самые заезженные ("Пока мы откладываем жизнь..." и т.п.). \
Каждая цитата — 1-2 предложения. Формат:
1. ...
2. ...
3. ...
Без вступления, без указания источника, только сами цитаты. Каждый раз НОВЫЕ."""


async def _pick_one(text: str) -> str:
    lines = [line.strip() for line in text.split("\n") if line.strip()]
    return strip_numbered_item(random.choice(lines))


async def handle_sitnikov(event: events.NewMessage.Event):
    chat_id = event.chat_id
    sender = event.sender_id
    logger.info("*** TRIGGER: 'ситников' in chat=%s from sender=%s", chat_id, sender)
    try:
        ai = AIClient.get()
        text = await ai.complete(SENECA_PROMPT, max_tokens=500, temperature=1.2)
        logger.info("<<< GPT SENECA RESPONSE:\n%s", text)
        quote = await _pick_one(text)
        logger.info("=== Selected Seneca quote: %s", quote)
        await event.reply(quote)
    except Exception as e:
        logger.error("*** ERROR getting Seneca quote: %s", e, exc_info=True)


async def handle_greenkeev(event: events.NewMessage.Event):
    chat_id = event.chat_id
    sender = event.sender_id
    logger.info("*** TRIGGER: 'гринкеев' in chat=%s from sender=%s", chat_id, sender)
    logger.info("*** Message: %s", event.raw_text)
    try:
        ai = AIClient.get()
        text = await ai.complete(PIG_FACTS_PROMPT, max_tokens=500, temperature=1.2)
        logger.info("<<< GPT RESPONSE (full):\n%s", text)
        fact = await _pick_one(text)
        logger.info("=== Selected fact: %s", fact)
        await event.reply(fact)
    except Exception as e:
        logger.error("*** ERROR getting pig fact: %s", e, exc_info=True)
