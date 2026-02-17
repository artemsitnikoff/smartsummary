from telethon import TelegramClient

from app.config import settings

_client: TelegramClient | None = None


def get_client() -> TelegramClient:
    global _client
    if _client is None:
        _client = TelegramClient(
            settings.session_name,
            settings.api_id,
            settings.api_hash,
        )
    return _client
