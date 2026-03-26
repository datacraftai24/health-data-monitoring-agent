"""WhatsApp messaging via Twilio."""

import logging

from twilio.rest import Client

from src.config import settings

logger = logging.getLogger(__name__)


class WhatsAppClient:
    """Send messages via WhatsApp using Twilio API."""

    def __init__(self):
        self._client: Client | None = None

    @property
    def client(self) -> Client:
        if self._client is None:
            self._client = Client(settings.twilio_account_sid, settings.twilio_auth_token)
        return self._client

    async def send_message(self, to_phone: str, body: str) -> str | None:
        """Send a WhatsApp message.

        Args:
            to_phone: Phone number in format 'whatsapp:+1234567890'
            body: Message text

        Returns:
            Message SID if successful, None otherwise.
        """
        if not to_phone.startswith("whatsapp:"):
            to_phone = f"whatsapp:{to_phone}"

        try:
            message = self.client.messages.create(
                from_=settings.twilio_whatsapp_from,
                body=body,
                to=to_phone,
            )
            logger.info("WhatsApp message sent to %s (SID: %s)", to_phone, message.sid)
            return message.sid
        except Exception:
            logger.exception("Failed to send WhatsApp message to %s", to_phone)
            return None

    async def send_media(self, to_phone: str, body: str, media_url: str) -> str | None:
        """Send a WhatsApp message with media attachment."""
        if not to_phone.startswith("whatsapp:"):
            to_phone = f"whatsapp:{to_phone}"

        try:
            message = self.client.messages.create(
                from_=settings.twilio_whatsapp_from,
                body=body,
                media_url=[media_url],
                to=to_phone,
            )
            return message.sid
        except Exception:
            logger.exception("Failed to send WhatsApp media to %s", to_phone)
            return None


whatsapp_client = WhatsAppClient()
