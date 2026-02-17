import logging
import random
import re
from collections import defaultdict, deque
from datetime import datetime

from openai import AsyncOpenAI
from telethon import TelegramClient, events

from app.bitrix import create_meeting, find_user_by_nickname, resolve_email_user
from app.config import settings

logger = logging.getLogger("smartsummary")

monitored_chats: set[int] = set()
message_buffer: dict[int, deque] = defaultdict(lambda: deque(maxlen=500))

# чаты в которых я писал сегодня (для дневного саммари)
today_active_chats: set[int] = set()

# все чаты с входящими сообщениями за день (для вечерней сводки)
today_incoming_chats: set[int] = set()

_openai_client: AsyncOpenAI | None = None


def get_openai_client() -> AsyncOpenAI:
    global _openai_client
    if _openai_client is None:
        _openai_client = AsyncOpenAI(api_key=settings.openai_api_key)
    return _openai_client


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


async def get_pig_fact() -> str:
    client = get_openai_client()

    logger.info(">>> GPT REQUEST [%s]", settings.openai_model)
    logger.info(">>> Prompt: %s", PIG_FACTS_PROMPT[:100] + "...")

    response = await client.chat.completions.create(
        model=settings.openai_model,
        max_completion_tokens=500,
        temperature=1.2,
        messages=[{"role": "user", "content": PIG_FACTS_PROMPT}],
    )

    text = response.choices[0].message.content.strip()
    logger.info("<<< GPT RESPONSE (full):\n%s", text)

    facts = [line.strip() for line in text.split("\n") if line.strip()]
    fact = random.choice(facts)
    # убираем нумерацию "1. ", "2. " и т.д.
    if len(fact) > 2 and fact[0].isdigit() and fact[1] in ".)":
        fact = fact[2:].strip()

    logger.info("=== Selected fact: %s", fact)
    return fact


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


async def get_seneca_quote() -> str:
    client = get_openai_client()

    logger.info(">>> GPT REQUEST [%s] seneca", settings.openai_model)

    response = await client.chat.completions.create(
        model=settings.openai_model,
        max_completion_tokens=500,
        temperature=1.2,
        messages=[{"role": "user", "content": SENECA_PROMPT}],
    )

    text = response.choices[0].message.content.strip()
    logger.info("<<< GPT SENECA RESPONSE:\n%s", text)

    quotes = [line.strip() for line in text.split("\n") if line.strip()]
    quote = random.choice(quotes)
    if len(quote) > 2 and quote[0].isdigit() and quote[1] in ".)":
        quote = quote[2:].strip()

    logger.info("=== Selected Seneca quote: %s", quote)
    return quote


MONTHS_RU = {
    "января": 1, "февраля": 2, "марта": 3, "апреля": 4,
    "мая": 5, "июня": 6, "июля": 7, "августа": 8,
    "сентября": 9, "октября": 10, "ноября": 11, "декабря": 12,
    "январь": 1, "февраль": 2, "март": 3, "апрель": 4,
    "май": 5, "июнь": 6, "июль": 7, "август": 8,
    "сентябрь": 9, "октябрь": 10, "ноябрь": 11, "декабрь": 12,
}


def parse_meeting_time(text: str) -> tuple[datetime | None, str | None]:
    """Parse time and date from 'сделай встречу 1600 27 февраля'.

    Returns (datetime, error_message). If parsing fails, datetime is None.
    """
    # strip the command prefix
    body = re.sub(r"(?i)^(сделай|создай)\s+встречу\s*", "", text).strip()

    # parse time: 3-4 digits like 1600, 900
    time_match = re.search(r"\b(\d{3,4})\b", body)
    if not time_match:
        return None, "Укажи время, например: сделай встречу 1600 27 февраля"
    raw_time = time_match.group(1).zfill(4)
    hour, minute = int(raw_time[:2]), int(raw_time[2:])
    if not (0 <= hour <= 23 and 0 <= minute <= 59):
        return None, f"Некорректное время: {raw_time}"

    # parse date: "DD месяц"
    now = datetime.now()
    date_match = re.search(
        r"(\d{1,2})\s+(" + "|".join(MONTHS_RU.keys()) + r")",
        body.lower(),
    )
    if date_match:
        day = int(date_match.group(1))
        month = MONTHS_RU[date_match.group(2)]
        year = now.year
        try:
            dt = datetime(year, month, day, hour, minute)
        except ValueError:
            return None, f"Некорректная дата: {day}.{month:02d}"
        # if the date has passed this year, use next year
        if dt < now:
            dt = dt.replace(year=year + 1)
    else:
        dt = datetime(now.year, now.month, now.day, hour, minute)

    return dt, None


EMAIL_RE = re.compile(r"[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+")
NICK_RE = re.compile(r"@(\w+)")


def parse_attendees(text: str) -> tuple[list[str], list[str]]:
    """Extract @nicknames and emails from meeting command text.

    Returns (nicknames_without_at, emails).
    """
    emails = EMAIL_RE.findall(text)
    # remove emails from text so @domain parts don't get picked up as nicknames
    cleaned = text
    for email in emails:
        cleaned = cleaned.replace(email, "")
    nicknames = NICK_RE.findall(cleaned)
    return nicknames, emails


def setup_handlers(client: TelegramClient):
    @client.on(events.NewMessage(incoming=True, outgoing=True))
    async def on_new_message(event: events.NewMessage.Event):
        chat_id = event.chat_id
        sender = event.sender_id
        text = event.raw_text or ""

        if not text:
            return

        logger.debug("[msg] chat=%s sender=%s text=%s", chat_id, sender, text[:80])

        # трекаем чаты где я писал (для дневного саммари)
        if sender == settings.my_user_id:
            today_active_chats.add(chat_id)

        # трекаем все чаты с входящими (для вечерней сводки)
        if sender != settings.my_user_id:
            today_incoming_chats.add(chat_id)

        # триггер "Суммаризация" — суммаризирую этот чат
        if text.lower().strip() == "суммаризация":
            logger.info("*** TRIGGER: 'суммаризация' in chat=%s from sender=%s", chat_id, sender)
            try:
                from app.summarizer import summarize_chat_for_trigger
                summary = await summarize_chat_for_trigger(chat_id)
                await event.reply(f"#summary\n\n{summary}", parse_mode="html")
                logger.info("*** SENT summary reply to chat=%s", chat_id)
            except Exception as e:
                logger.error("*** ERROR summarizing: %s", e, exc_info=True)
            return

        # авто-ответ на "Ситников" — цитата Сенеки
        if "ситников" in text.lower():
            logger.info("*** TRIGGER: 'ситников' in chat=%s from sender=%s", chat_id, sender)
            try:
                quote = await get_seneca_quote()
                await event.reply(quote)
                logger.info("*** SENT Seneca reply: %s", quote)
            except Exception as e:
                logger.error("*** ERROR getting Seneca quote: %s", e, exc_info=True)

        # авто-ответ на "Гринкеев"
        if "гринкеев" in text.lower():
            logger.info("*** TRIGGER: 'гринкеев' in chat=%s from sender=%s", chat_id, sender)
            logger.info("*** Message: %s", text)
            try:
                fact = await get_pig_fact()
                await event.reply(fact)
                logger.info("*** SENT reply: %s", fact)
            except Exception as e:
                logger.error("*** ERROR getting pig fact: %s", e, exc_info=True)

        # триггер "сделай встречу"
        if re.match(r"(?i)(сделай|создай)\s+встречу", text):
            logger.info("*** TRIGGER: 'сделай встречу' in chat=%s from sender=%s", chat_id, sender)
            try:
                dt, err = parse_meeting_time(text)
                if err:
                    await event.reply(err)
                    return

                # контекст из цитируемого сообщения
                context = ""
                reply_msg = await event.get_reply_message()
                if reply_msg and reply_msg.raw_text:
                    context = reply_msg.raw_text

                # парсим участников
                nicknames, emails = parse_attendees(text)
                attendee_ids: list[int] = []
                found_names: list[str] = []
                not_found: list[str] = []
                external_emails: list[str] = []

                for nick in nicknames:
                    uid, full_name = await find_user_by_nickname(nick)
                    if uid:
                        attendee_ids.append(uid)
                        found_names.append(full_name or nick)
                    else:
                        not_found.append(f"@{nick}")

                invite_emails: list[str] = []
                for email in emails:
                    try:
                        uid, name = await resolve_email_user(email)
                        if uid:
                            attendee_ids.append(uid)
                            external_emails.append(f"{name} ({email})" if name else email)
                        else:
                            invite_emails.append(email)
                    except Exception as e:
                        logger.error("Failed to find user by email %s: %s", email, e)
                        invite_emails.append(email)

                title = context[:80] if context else "Встреча"
                description = context or ""
                if invite_emails:
                    description += "\n\nПригласить по email: " + ", ".join(invite_emails)
                result = await create_meeting(
                    title=title, date=dt, description=description,
                    attendee_ids=attendee_ids if attendee_ids else None,
                )

                event_id = result.get("id", "?")
                reply_text = f"✅ Встреча создана: {dt:%d.%m.%Y} в {dt:%H:%M} (id: {event_id})"
                if found_names:
                    reply_text += f"\n👥 Участники: {', '.join(found_names)}"
                if external_emails:
                    reply_text += f"\n👥 По email: {', '.join(external_emails)}"
                if invite_emails:
                    reply_text += f"\n📧 В описании (пригласить вручную): {', '.join(invite_emails)}"
                if not_found:
                    reply_text += f"\n⚠️ Не найден: {', '.join(not_found)}"
                if context:
                    reply_text += f"\n📝 {context}"
                await event.reply(reply_text)
                logger.info("*** SENT meeting reply: %s", reply_text)
            except Exception as e:
                logger.error("*** ERROR creating meeting: %s", e, exc_info=True)
            return

        # буферизация для мониторимых чатов
        if chat_id in monitored_chats:
            message_buffer[chat_id].append({
                "sender_id": sender,
                "text": text,
                "date": event.date.isoformat(),
            })


def get_active_chats() -> list[int]:
    return list(today_active_chats)


def clear_active_chats():
    today_active_chats.clear()


def get_incoming_chats() -> list[int]:
    return list(today_incoming_chats)


def clear_incoming_chats():
    today_incoming_chats.clear()


def add_chat(chat_id: int):
    monitored_chats.add(chat_id)


def remove_chat(chat_id: int):
    monitored_chats.discard(chat_id)


def get_monitored() -> list[int]:
    return list(monitored_chats)


def get_messages(chat_id: int) -> list[dict]:
    return list(message_buffer.get(chat_id, []))
