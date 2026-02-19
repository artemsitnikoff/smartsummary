"""Export current session file to a StringSession for use in .env"""

import asyncio

from telethon import TelegramClient
from telethon.sessions import StringSession

from app.config import settings


async def main():
    # Read existing session file
    client = TelegramClient(
        settings.session_name,
        settings.api_id,
        settings.api_hash,
    )
    await client.connect()

    if not await client.is_user_authorized():
        print("ERROR: Session not authorized. Run auth.py first.")
        await client.disconnect()
        return

    me = await client.get_me()
    print(f"Authorized as: {me.first_name} (@{me.username})")

    # Export to StringSession
    string_session = StringSession.save(client.session)
    print(f"\nAdd this to .env on the server:\n")
    print(f"TELEGRAM_SESSION={string_session}")

    await client.disconnect()


if __name__ == "__main__":
    asyncio.run(main())
