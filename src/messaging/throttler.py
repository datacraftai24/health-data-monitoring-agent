"""Message throttling to prevent notification fatigue."""

import logging
from datetime import datetime, timedelta

import redis.asyncio as redis

from src.config import settings

logger = logging.getLogger(__name__)

MAX_MESSAGES_PER_DAY = 8
MIN_GAP_MINUTES = 30
CRITICAL_GLUCOSE_THRESHOLD = 3.9  # Bypass throttle below this


class MessageThrottler:
    """Rate-limit outgoing messages per user to prevent notification fatigue."""

    def __init__(self):
        self._redis: redis.Redis | None = None

    @property
    def redis_client(self) -> redis.Redis:
        if self._redis is None:
            self._redis = redis.from_url(settings.redis_url)
        return self._redis

    async def should_send(
        self,
        user_id: str,
        priority: str,
        glucose_value: float | None = None,
    ) -> bool:
        """Check if a message should be sent based on throttling rules.

        Args:
            user_id: The user to check.
            priority: Alert priority (critical, high, medium, low).
            glucose_value: Current glucose if available.

        Returns:
            True if the message should be sent.
        """
        # Critical alerts and dangerously low glucose bypass all throttling
        if priority == "critical":
            return True
        if glucose_value is not None and glucose_value < CRITICAL_GLUCOSE_THRESHOLD:
            return True

        r = self.redis_client
        day_key = f"throttle:{user_id}:count:{datetime.utcnow().date()}"
        last_key = f"throttle:{user_id}:last_sent"

        # Check daily count
        count = await r.get(day_key)
        if count and int(count) >= MAX_MESSAGES_PER_DAY:
            logger.info("Throttled: user %s hit daily limit (%s msgs)", user_id, count)
            return False

        # Check minimum gap
        last_sent = await r.get(last_key)
        if last_sent:
            last_time = datetime.fromisoformat(last_sent.decode())
            if datetime.utcnow() - last_time < timedelta(minutes=MIN_GAP_MINUTES):
                logger.info("Throttled: user %s min gap not met", user_id)
                return False

        return True

    async def record_sent(self, user_id: str):
        """Record that a message was sent to a user."""
        r = self.redis_client
        day_key = f"throttle:{user_id}:count:{datetime.utcnow().date()}"
        last_key = f"throttle:{user_id}:last_sent"

        pipe = r.pipeline()
        pipe.incr(day_key)
        pipe.expire(day_key, 86400)  # TTL 24 hours
        pipe.set(last_key, datetime.utcnow().isoformat())
        pipe.expire(last_key, 86400)
        await pipe.execute()

    async def pause_for_user(self, user_id: str, hours: int = 2):
        """Pause all non-critical messages for a user (e.g., user replies 'STOP')."""
        r = self.redis_client
        pause_key = f"throttle:{user_id}:paused"
        await r.set(pause_key, "1", ex=hours * 3600)

    async def is_paused(self, user_id: str) -> bool:
        """Check if a user has paused notifications."""
        r = self.redis_client
        return bool(await r.get(f"throttle:{user_id}:paused"))


throttler = MessageThrottler()
