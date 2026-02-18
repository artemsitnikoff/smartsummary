import asyncio
import re

from telethon import TelegramClient

from app.config import settings

TG_MSG_LIMIT = 4096


class TelegramService:
    _instance: "TelegramService | None" = None

    def __init__(self):
        self._client = TelegramClient(
            settings.session_name, settings.api_id, settings.api_hash
        )

    @classmethod
    def get(cls) -> "TelegramService":
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    @property
    def client(self) -> TelegramClient:
        return self._client

    async def connect(self):
        await self._client.connect()

    async def disconnect(self):
        await self._client.disconnect()

    async def is_authorized(self) -> bool:
        return await self._client.is_user_authorized()

    @staticmethod
    def clean_html(text: str) -> str:
        """Convert markdown bold to HTML, strip unsupported tags."""
        text = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", text)
        text = re.sub(r"<br\s*/?>", "\n", text)
        text = re.sub(
            r"</?(?!b|/b|i|/i|u|/u|s|/s|a|/a|code|/code|pre|/pre)[^>]+>", "", text
        )
        return text

    async def send_long_message(self, text: str, parse_mode: str = "html"):
        """Send a message to Saved Messages, splitting if > 4096 chars."""
        while text:
            if len(text) <= TG_MSG_LIMIT:
                await self._client.send_message("me", text, parse_mode=parse_mode)
                break
            cut = text.rfind("\n", 0, TG_MSG_LIMIT)
            if cut == -1:
                cut = TG_MSG_LIMIT
            await self._client.send_message("me", text[:cut], parse_mode=parse_mode)
            text = text[cut:].lstrip("\n")
            await asyncio.sleep(2)
