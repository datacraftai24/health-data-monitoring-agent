"""Telegram bot webhook handler."""

import logging

from fastapi import APIRouter, Depends, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.ai.conversation import conversation_engine
from src.ingestion.food import process_food_photo, process_food_text
from src.messaging.telegram_client import telegram_client
from src.models.base import get_db
from src.models.user import User

logger = logging.getLogger(__name__)

router = APIRouter()


@router.post("/telegram")
async def telegram_webhook(request: Request, db: AsyncSession = Depends(get_db)):
    """Handle incoming Telegram messages."""
    update = await request.json()
    message = update.get("message", {})

    if not message:
        return {"ok": True}

    chat_id = message["chat"]["id"]
    result = await db.execute(select(User).where(User.telegram_chat_id == chat_id))
    user = result.scalar_one_or_none()

    if not user:
        logger.warning("Unknown Telegram user: chat_id=%s", chat_id)
        await telegram_client.send_message(
            chat_id, "Hi! You're not registered yet. Please set up your account first."
        )
        return {"ok": True}

    try:
        if "photo" in message:
            # Get highest resolution photo
            photo_id = message["photo"][-1]["file_id"]
            photo_bytes = await telegram_client.download_file(photo_id)
            if photo_bytes is None:
                await telegram_client.send_message(chat_id, "Couldn't download the photo. Try again?")
                return {"ok": True}

            caption = message.get("caption", "")
            analysis = await process_food_photo(
                photo_bytes=photo_bytes,
                user=user,
                caption=caption,
            )
            response_text = _format_meal_response(analysis)

        elif "text" in message:
            text = message["text"]

            # Handle commands
            if text.startswith("/start"):
                response_text = (
                    "Welcome to MetaboCoach! 🏥\n\n"
                    "Send me a food photo or describe what you're eating.\n"
                    "Ask me anything about your glucose, nutrition, or health."
                )
            elif text.startswith("/status"):
                response_text = await conversation_engine.respond(
                    user_message="How am I doing today?",
                    user_context={"name": user.name, "hba1c": user.hba1c},
                )
            else:
                food_keywords = ["had", "ate", "eating", "having", "lunch", "dinner", "breakfast", "snack"]
                is_food = any(kw in text.lower() for kw in food_keywords)

                if is_food:
                    analysis = await process_food_text(text=text, user=user)
                    response_text = _format_meal_response(analysis)
                else:
                    response_text = await conversation_engine.respond(
                        user_message=text,
                        user_context={"name": user.name, "hba1c": user.hba1c},
                    )
        else:
            return {"ok": True}

        await telegram_client.send_message(chat_id, response_text)
    except Exception:
        logger.exception("Error processing Telegram message from chat %s", chat_id)
        await telegram_client.send_message(
            chat_id, "Sorry, something went wrong. Please try again."
        )

    return {"ok": True}


def _format_meal_response(analysis) -> str:
    """Format meal analysis into a Telegram-friendly message."""
    items_text = ", ".join(item.name for item in analysis.items) if analysis.items else "your meal"

    lines = [
        f"<b>Meal:</b> {items_text}",
        f"📊 ~{analysis.total_calories} cal | "
        f"{analysis.total_protein_g:.0f}g protein | {analysis.total_carbs_g:.0f}g carbs",
    ]

    if analysis.predicted_spike > 2.0:
        lines.append(f"⚠️ Predicted spike: +{analysis.predicted_spike:.1f} mmol/L")

    if analysis.crash_risk in ("medium", "high"):
        lines.append(f"⚡ Crash risk: {analysis.crash_risk}")

    if analysis.recommendation:
        lines.append(f"💡 {analysis.recommendation}")

    return "\n".join(lines)
