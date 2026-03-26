"""Message dispatcher — routes messages to the correct channel."""

import logging

from src.messaging.throttler import throttler
from src.messaging.whatsapp_client import whatsapp_client
from src.messaging.telegram_client import telegram_client
from src.models.user import User

logger = logging.getLogger(__name__)


class MessageDispatcher:
    """Route outgoing messages to the user's preferred channel."""

    async def send(
        self,
        user: User,
        message: str,
        priority: str = "medium",
        glucose_value: float | None = None,
        force: bool = False,
    ) -> bool:
        """Send a message to the user via their preferred channel.

        Args:
            user: Target user.
            message: Message text.
            priority: Alert priority for throttling.
            glucose_value: Current glucose if relevant.
            force: Bypass throttling.

        Returns:
            True if message was sent successfully.
        """
        user_id = str(user.id)

        # Check if user paused notifications
        if not force and await throttler.is_paused(user_id):
            if priority != "critical":
                logger.info("User %s has paused notifications, skipping", user_id)
                return False

        # Check throttle
        if not force and not await throttler.should_send(user_id, priority, glucose_value):
            return False

        # Send via preferred channel (Telegram is primary, WhatsApp is future/secondary)
        success = False
        if user.preferred_channel == "telegram" and user.telegram_chat_id:
            success = await telegram_client.send_message(user.telegram_chat_id, message)
        elif user.preferred_channel == "whatsapp" and user.phone:
            sid = await whatsapp_client.send_message(user.phone, message)
            success = sid is not None
        else:
            # Fallback: try telegram first, then whatsapp
            if user.telegram_chat_id:
                success = await telegram_client.send_message(user.telegram_chat_id, message)
            if not success and user.phone:
                sid = await whatsapp_client.send_message(user.phone, message)
                success = sid is not None

        if success:
            await throttler.record_sent(user_id)
            logger.info("Message dispatched to user %s via %s", user_id, user.preferred_channel)
        else:
            logger.error("Failed to dispatch message to user %s", user_id)

        return success


dispatcher = MessageDispatcher()
