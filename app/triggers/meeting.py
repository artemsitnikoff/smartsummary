import logging

from telethon import events

from app.services.bitrix_client import BitrixClient
from app.utils import parse_attendees, parse_meeting_time

logger = logging.getLogger("smartsummary")


async def handle_create_meeting(event: events.NewMessage.Event):
    chat_id = event.chat_id
    sender = event.sender_id
    text = event.raw_text or ""
    logger.info("*** TRIGGER: 'сделай встречу' in chat=%s from sender=%s", chat_id, sender)
    try:
        dt, err = parse_meeting_time(text)
        if err:
            await event.reply(err)
            return

        context = ""
        reply_msg = await event.get_reply_message()
        if reply_msg and reply_msg.raw_text:
            context = reply_msg.raw_text

        nicknames, emails = parse_attendees(text)
        bitrix = BitrixClient.get()

        attendee_ids: list[int] = []
        found_names: list[str] = []
        not_found: list[str] = []
        external_emails: list[str] = []

        for nick in nicknames:
            uid, full_name = await bitrix.find_user_by_nickname(nick)
            if uid:
                attendee_ids.append(uid)
                found_names.append(full_name or nick)
            else:
                not_found.append(f"@{nick}")

        invite_emails: list[str] = []
        for email in emails:
            try:
                uid, name = await bitrix.resolve_email_user(email)
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
        result = await bitrix.create_meeting(
            title=title,
            date=dt,
            description=description,
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
