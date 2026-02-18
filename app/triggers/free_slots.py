import logging
from datetime import datetime, timedelta

from telethon import events

from app.services.bitrix_client import BitrixClient
from app.utils import DAY_NAMES_RU, merge_intervals, parse_attendees, parse_bitrix_dt

logger = logging.getLogger("smartsummary")


async def handle_find_time(event: events.NewMessage.Event):
    chat_id = event.chat_id
    sender = event.sender_id
    text = event.raw_text or ""
    logger.info("*** TRIGGER: 'найди время' in chat=%s from sender=%s", chat_id, sender)
    try:
        nicknames, _ = parse_attendees(text)
        if not nicknames:
            await event.reply("Укажи участников: Найди время @nick1 @nick2")
            return

        bitrix = BitrixClient.get()

        user_ids: list[int] = []
        user_names: list[str] = []
        not_found: list[str] = []
        for nick in nicknames:
            uid, full_name = await bitrix.find_user_by_nickname(nick)
            if uid:
                user_ids.append(uid)
                user_names.append(f"@{nick}")
            else:
                not_found.append(f"@{nick}")

        if not user_ids:
            msg = "❌ Никого не удалось найти в Bitrix"
            if not_found:
                msg += f"\n⚠️ Не найден: {', '.join(not_found)}"
            await event.reply(msg)
            return

        today = datetime.now().date()
        work_days: list = []
        d = today
        while len(work_days) < 5:
            if d.weekday() < 5:
                work_days.append(d)
            d += timedelta(days=1)

        date_from = work_days[0].strftime("%Y-%m-%d")
        date_to = work_days[-1].strftime("%Y-%m-%d")

        accessibility = await bitrix.get_users_accessibility(user_ids, date_from, date_to)

        lines: list[str] = []
        lines.append(f"📅 Свободные слоты для {', '.join(user_names)}:")
        if not_found:
            lines.append(f"⚠️ Не найден: {', '.join(not_found)}")
        lines.append("")

        for day in work_days:
            day_start = datetime.combine(day, datetime.min.time().replace(hour=9))
            day_end = datetime.combine(day, datetime.min.time().replace(hour=19))

            busy_intervals: list[tuple[datetime, datetime]] = []
            for uid in user_ids:
                slots = accessibility.get(str(uid), [])
                for slot in slots:
                    acc = slot.get("ACCESSIBILITY", "busy")
                    if acc in ("free",):
                        continue
                    try:
                        dt_from = parse_bitrix_dt(slot["DATE_FROM"])
                        dt_to = parse_bitrix_dt(slot["DATE_TO"])
                        offset_from = int(slot.get("~USER_OFFSET_FROM", 0))
                        offset_to = int(slot.get("~USER_OFFSET_TO", 0))
                        dt_from -= timedelta(seconds=offset_from)
                        dt_to -= timedelta(seconds=offset_to)
                    except Exception as e:
                        logger.warning("Skip slot parse error: %s | %s", e, slot)
                        continue
                    if dt_to <= day_start or dt_from >= day_end:
                        continue
                    busy_intervals.append((
                        max(dt_from, day_start),
                        min(dt_to, day_end),
                    ))

            merged = merge_intervals(busy_intervals)

            free_slots: list[tuple[datetime, datetime]] = []
            cursor = day_start
            for b_start, b_end in merged:
                if cursor < b_start:
                    free_slots.append((cursor, b_start))
                cursor = max(cursor, b_end)
            if cursor < day_end:
                free_slots.append((cursor, day_end))

            free_slots = [
                (s, e) for s, e in free_slots if (e - s) >= timedelta(minutes=30)
            ]

            day_label = f"{DAY_NAMES_RU[day.weekday()]}, {day.strftime('%d.%m')}"
            if not free_slots:
                lines.append(f"{day_label}:")
                lines.append("  нет свободных слотов")
            else:
                lines.append(f"{day_label}:")
                for slot_start, slot_end in free_slots:
                    s = slot_start.strftime("%H:%M")
                    e = slot_end.strftime("%H:%M")
                    suffix = " (весь день)" if s == "09:00" and e == "19:00" else ""
                    lines.append(f"  {s}–{e}{suffix}")
            lines.append("")

        await event.reply("\n".join(lines).rstrip())
        logger.info("*** SENT free slots for %s", user_names)
    except Exception as e:
        logger.error("*** ERROR finding free time: %s", e, exc_info=True)
        await event.reply(f"❌ Не удалось найти свободное время: {e}")
