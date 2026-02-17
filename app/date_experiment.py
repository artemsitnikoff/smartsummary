"""
Эксперимент: автономный диалог с коллегами через GPT.
Все участники дали информированное согласие.
"""

import asyncio
import logging

from openai import AsyncOpenAI
from telethon import TelegramClient, events

from app.config import settings

logger = logging.getLogger("smartsummary")

SYSTEM_PROMPT_TEMPLATE = """\
Ты — Артём, пишешь коллеге {name} в телеге. Хочешь позвать на кофе/обед. \
Ты обычный живой чувак, не робот.

Как писать:
- Как реальный человек в мессенджере, можно без заглавных, с опечатками даже
- Коротко: 1-2 предложения, иногда вообще пару слов
- Без пафоса, без красивых фраз, без "давай вытащу тебя" и прочей книжности
- Примеры нормального тона: "слушай, пошли на кофе?", "го обедать?", "чё делаешь, может кофе?"
- Юмор простой, бытовой, не вымученный
- Если отказ жёсткий ("нет", "отстань", "хватит") — "ок)" и всё, не пиши больше
- Если "занята"/"не могу" — предложи другое время один раз
- Отвечай ТОЛЬКО текстом сообщения
"""

STOP_WORDS = ["отстань", "хватит", "стоп", "прекрати", "не пиши", "заканчивай"]


class DateExperiment:
    def __init__(self, chat_id: int, name: str):
        self.chat_id = chat_id
        self.name = name
        self.active = False
        self.conversation: list[dict] = []
        self.openai: AsyncOpenAI | None = None
        self.client: TelegramClient | None = None
        self._reply_count = 0
        self._max_replies = 15

    def _get_openai(self) -> AsyncOpenAI:
        if self.openai is None:
            self.openai = AsyncOpenAI(api_key=settings.openai_api_key)
        return self.openai

    @property
    def system_prompt(self) -> str:
        return SYSTEM_PROMPT_TEMPLATE.format(name=self.name)

    async def _generate_reply(self, her_message: str | None = None) -> str:
        if her_message:
            self.conversation.append({"role": "user", "content": her_message})

        messages = [{"role": "system", "content": self.system_prompt}] + self.conversation

        ai = self._get_openai()
        response = await ai.chat.completions.create(
            model=settings.openai_model,
            max_completion_tokens=200,
            temperature=0.9,
            messages=messages,
        )

        reply = response.choices[0].message.content.strip()
        self.conversation.append({"role": "assistant", "content": reply})
        logger.info("<<< EXPERIMENT [%s] GPT reply: %s", self.name, reply)
        return reply

    async def start(self, client: TelegramClient):
        self.client = client
        self.active = True
        self.conversation = []
        self._reply_count = 0

        self.conversation.append({
            "role": "user",
            "content": f"Начни разговор с {self.name}. Напиши первое сообщение — поздоровайся и сразу предложи кофе или обед."
        })

        first_msg = await self._generate_reply()
        self.conversation = [{"role": "assistant", "content": first_msg}]

        await client.send_message(self.chat_id, first_msg)
        logger.info(">>> EXPERIMENT [%s] started, first message: %s", self.name, first_msg)

    async def handle_reply(self, event: events.NewMessage.Event):
        if not self.active:
            return

        text = event.raw_text or ""
        if not text:
            return

        logger.info(">>> EXPERIMENT [%s] incoming: %s", self.name, text)

        text_lower = text.lower()
        if any(w in text_lower for w in STOP_WORDS):
            logger.info(">>> EXPERIMENT [%s]: stop word, ending", self.name)
            await event.reply("Ок, без проблем! Хорошего дня 👋")
            self.stop()
            return

        self._reply_count += 1
        if self._reply_count >= self._max_replies:
            logger.info(">>> EXPERIMENT [%s]: max replies, ending", self.name)
            await event.reply("Ладно, побегу работать. Хорошего дня!")
            self.stop()
            return

        reply = await self._generate_reply(text)
        await asyncio.sleep(2)
        await event.reply(reply)

    async def nudge(self, client: TelegramClient):
        """Отправить напоминание, не дожидаясь ответа."""
        if not self.active:
            return None
        self.conversation.append({
            "role": "user",
            "content": "(она молчит, напиши ей ещё раз — напомни о себе, коротко и с юмором)"
        })
        reply = await self._generate_reply()
        # убираем фейковую "user" инструкцию из истории
        self.conversation = [m for m in self.conversation if m.get("content") != "(она молчит, напиши ей ещё раз — напомни о себе, коротко и с юмором)"]
        await client.send_message(self.chat_id, reply)
        logger.info(">>> EXPERIMENT [%s] nudge sent: %s", self.name, reply)
        return reply

    def stop(self):
        self.active = False
        logger.info(">>> EXPERIMENT [%s] stopped. Exchanges: %d", self.name, self._reply_count)


# Реестр активных экспериментов: chat_id -> DateExperiment
experiments: dict[int, DateExperiment] = {}


def get_or_create(chat_id: int, name: str) -> DateExperiment:
    if chat_id not in experiments:
        experiments[chat_id] = DateExperiment(chat_id, name)
    return experiments[chat_id]


def setup_experiment_handler(client: TelegramClient):
    @client.on(events.NewMessage(incoming=True))
    async def on_experiment_reply(event: events.NewMessage.Event):
        chat_id = event.chat_id
        exp = experiments.get(chat_id)
        if exp and exp.active and event.sender_id == chat_id:
            await exp.handle_reply(event)
