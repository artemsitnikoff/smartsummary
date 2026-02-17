import asyncio

from app.config import settings
from telethon import TelegramClient


async def main():
    client = TelegramClient(
        settings.session_name,
        settings.api_id,
        settings.api_hash,
    )
    await client.start()
    me = await client.get_me()
    print(f"Authorized as: {me.first_name} (@{me.username})")
    await client.disconnect()


if __name__ == "__main__":
    asyncio.run(main())
