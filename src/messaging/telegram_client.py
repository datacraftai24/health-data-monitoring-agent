"""Telegram messaging client."""

import logging

import httpx

from src.config import settings

logger = logging.getLogger(__name__)


class TelegramClient:
    """Send messages via the Telegram Bot API."""

    def __init__(self):
        self.base_url = f"https://api.telegram.org/bot{settings.telegram_bot_token}"

    async def send_message(self, chat_id: int, text: str, parse_mode: str = "HTML") -> bool:
        """Send a text message to a Telegram chat."""
        try:
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    f"{self.base_url}/sendMessage",
                    json={
                        "chat_id": chat_id,
                        "text": text,
                        "parse_mode": parse_mode,
                    },
                )
                response.raise_for_status()
                logger.info("Telegram message sent to chat %s", chat_id)
                return True
        except Exception:
            logger.exception("Failed to send Telegram message to chat %s", chat_id)
            return False

    async def download_file(self, file_id: str) -> bytes | None:
        """Download a file from Telegram by file_id."""
        try:
            async with httpx.AsyncClient() as client:
                # Get file path
                response = await client.get(
                    f"{self.base_url}/getFile",
                    params={"file_id": file_id},
                )
                response.raise_for_status()
                file_path = response.json()["result"]["file_path"]

                # Download file
                file_url = (
                    f"https://api.telegram.org/file/bot{settings.telegram_bot_token}/{file_path}"
                )
                file_response = await client.get(file_url)
                file_response.raise_for_status()
                return file_response.content
        except Exception:
            logger.exception("Failed to download Telegram file %s", file_id)
            return None


telegram_client = TelegramClient()
