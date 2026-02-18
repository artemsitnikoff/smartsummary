import logging
import random

from app.config import settings
from app.services.ai_client import AIClient
from app.services.telegram_service import TelegramService
from app.utils import strip_numbered_item

logger = logging.getLogger("smartsummary")

COMPLIMENT_PROMPT = """\
Ты — опытный семейный психолог, который помогает мужу наладить отношения с женой. \
Сгенерируй 3 варианта утреннего сообщения жене от мужа.

Правила:
- НЕ банальные комплименты вроде "ты красивая", "доброе утро солнышко", "ты лучшая"
- Сообщение должно показывать что муж ЗАМЕЧАЕТ мелочи, ценит её как личность
- Можно: подчеркнуть её силу характера, вспомнить что-то конкретное (как она смеётся, \
как она решает проблемы, как создаёт уют), вызвать улыбку, показать благодарность
- Тон: тёплый, искренний, без пафоса и слащавости. Как будто мужик реально сел и подумал
- Длина: 1-3 предложения. Это сообщение в телеграм, не письмо
- Иногда можно добавить лёгкий юмор или самоиронию
- Пиши на русском, разговорным языком
- НЕ начинай с "Доброе утро". Можно начать сразу с сути

Формат:
1. ...
2. ...
3. ...
Без вступления и пояснений, только 3 варианта."""


async def send_compliment():
    """Generate and send a morning compliment."""
    logger.info("=== COMPLIMENT JOB started")

    try:
        ai = AIClient.get()
        text = await ai.complete(COMPLIMENT_PROMPT, max_tokens=500, temperature=1.1)
        logger.info("<<< COMPLIMENT GPT RESPONSE:\n%s", text)

        variants = [line.strip() for line in text.split("\n") if line.strip()]
        compliment = strip_numbered_item(random.choice(variants))
        logger.info("=== Selected compliment: %s", compliment)

        tg = TelegramService.get()
        await tg.client.send_message(settings.wife_chat_id, compliment)
        logger.info("=== Compliment sent to wife (chat=%s)", settings.wife_chat_id)

    except Exception as e:
        logger.error("=== COMPLIMENT ERROR: %s", e, exc_info=True)
