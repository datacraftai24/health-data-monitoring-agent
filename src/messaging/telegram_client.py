"""Telegram messaging client — primary messaging channel for MetaboCoach."""

import logging

import httpx

from src.config import settings

logger = logging.getLogger(__name__)


class TelegramClient:
    """Send messages via the Telegram Bot API.

    Telegram is the primary channel because:
    - Free, unlimited messages
    - Native photo uploads with captions
    - Inline keyboards for quick replies
    - Bot commands (/status, /log, /help)
    - No business verification needed
    """

    def __init__(self):
        self.base_url = f"https://api.telegram.org/bot{settings.telegram_bot_token}"

    async def send_message(
        self,
        chat_id: int,
        text: str,
        parse_mode: str = "HTML",
        reply_markup: dict | None = None,
    ) -> bool:
        """Send a text message to a Telegram chat. Auto-splits if > 4096 chars."""
        # Telegram limit is 4096 chars per message
        if len(text) > 4096:
            chunks = self._split_message(text)
            success = True
            for i, chunk in enumerate(chunks):
                markup = reply_markup if i == len(chunks) - 1 else None
                ok = await self._send_single(chat_id, chunk, parse_mode, markup)
                success = success and ok
            return success
        return await self._send_single(chat_id, text, parse_mode, reply_markup)

    async def _send_single(
        self, chat_id: int, text: str, parse_mode: str, reply_markup: dict | None
    ) -> bool:
        try:
            async with httpx.AsyncClient() as client:
                payload = {
                    "chat_id": chat_id,
                    "text": text,
                    "parse_mode": parse_mode,
                }
                if reply_markup:
                    payload["reply_markup"] = reply_markup

                response = await client.post(
                    f"{self.base_url}/sendMessage",
                    json=payload,
                    timeout=15,
                )
                response.raise_for_status()
                logger.info("Telegram message sent to chat %s", chat_id)
                return True
        except Exception:
            logger.exception("Failed to send Telegram message to chat %s", chat_id)
            return False

    @staticmethod
    def _split_message(text: str, limit: int = 4096) -> list[str]:
        """Split long text into chunks at newline boundaries."""
        chunks = []
        while len(text) > limit:
            split_at = text.rfind("\n", 0, limit)
            if split_at == -1:
                split_at = limit
            chunks.append(text[:split_at])
            text = text[split_at:].lstrip("\n")
        if text:
            chunks.append(text)
        return chunks

    async def send_message_with_quick_replies(
        self,
        chat_id: int,
        text: str,
        buttons: list[list[dict]],
    ) -> bool:
        """Send a message with inline keyboard buttons.

        Example buttons:
            [[{"text": "Yes", "callback_data": "confirm_yes"},
              {"text": "No", "callback_data": "confirm_no"}]]
        """
        reply_markup = {"inline_keyboard": buttons}
        return await self.send_message(chat_id, text, reply_markup=reply_markup)

    async def send_photo(
        self,
        chat_id: int,
        photo_url: str,
        caption: str = "",
    ) -> bool:
        """Send a photo to a Telegram chat."""
        try:
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    f"{self.base_url}/sendPhoto",
                    json={
                        "chat_id": chat_id,
                        "photo": photo_url,
                        "caption": caption,
                        "parse_mode": "HTML",
                    },
                )
                response.raise_for_status()
                return True
        except Exception:
            logger.exception("Failed to send Telegram photo to chat %s", chat_id)
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

    async def answer_callback_query(self, callback_query_id: str, text: str = "") -> bool:
        """Answer an inline keyboard button press."""
        try:
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    f"{self.base_url}/answerCallbackQuery",
                    json={
                        "callback_query_id": callback_query_id,
                        "text": text,
                    },
                )
                response.raise_for_status()
                return True
        except Exception:
            logger.exception("Failed to answer callback query %s", callback_query_id)
            return False

    async def set_webhook(self, webhook_url: str) -> bool:
        """Register the webhook URL with Telegram."""
        try:
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    f"{self.base_url}/setWebhook",
                    json={"url": webhook_url},
                    timeout=10,
                )
                response.raise_for_status()
                logger.info("Telegram webhook set to %s", webhook_url)
                return True
        except Exception:
            logger.exception("Failed to set Telegram webhook")
            return False

    async def set_bot_commands(self) -> bool:
        """Register bot commands for the command menu in Telegram."""
        commands = [
            {"command": "start", "description": "Get started with MetaboCoach"},
            {"command": "status", "description": "Today's health snapshot"},
            {"command": "log", "description": "Log a meal (send photo or text after)"},
            {"command": "glucose", "description": "Current glucose reading"},
            {"command": "calories", "description": "Today's calorie & protein progress"},
            {"command": "help", "description": "How to use MetaboCoach"},
            {"command": "pause", "description": "Pause notifications for 2 hours"},
        ]
        try:
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    f"{self.base_url}/setMyCommands",
                    json={"commands": commands},
                )
                response.raise_for_status()
                logger.info("Telegram bot commands registered")
                return True
        except Exception:
            logger.exception("Failed to set bot commands")
            return False


telegram_client = TelegramClient()
