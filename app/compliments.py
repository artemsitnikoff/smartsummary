import logging
import random

from openai import AsyncOpenAI

from app.config import settings
from app.telegram_client import get_client

logger = logging.getLogger("smartsummary")

_openai_client: AsyncOpenAI | None = None


def get_openai_client() -> AsyncOpenAI:
    global _openai_client
    if _openai_client is None:
        _openai_client = AsyncOpenAI(api_key=settings.openai_api_key)
    return _openai_client


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
        ai = get_openai_client()
        response = await ai.chat.completions.create(
            model=settings.openai_model,
            max_completion_tokens=500,
            temperature=1.1,
            messages=[{"role": "user", "content": COMPLIMENT_PROMPT}],
        )

        text = response.choices[0].message.content.strip()
        logger.info("<<< COMPLIMENT GPT RESPONSE:\n%s", text)

        variants = [line.strip() for line in text.split("\n") if line.strip()]
        compliment = random.choice(variants)
        # убираем нумерацию
        if len(compliment) > 2 and compliment[0].isdigit() and compliment[1] in ".)":
            compliment = compliment[2:].strip()

        logger.info("=== Selected compliment: %s", compliment)

        client = get_client()
        await client.send_message(settings.wife_chat_id, compliment)
        logger.info("=== Compliment sent to wife (chat=%s)", settings.wife_chat_id)

    except Exception as e:
        logger.error("=== COMPLIMENT ERROR: %s", e, exc_info=True)
