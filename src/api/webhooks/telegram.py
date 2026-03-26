"""Telegram bot webhook handler — primary user interface for MetaboCoach."""

import logging

from fastapi import APIRouter, Depends, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.ai.conversation import conversation_engine
from src.ingestion.food import process_food_photo, process_food_text
from src.messaging.telegram_client import telegram_client
from src.messaging.throttler import throttler
from src.models.base import get_db
from src.models.user import User

logger = logging.getLogger(__name__)

router = APIRouter()

HELP_TEXT = """<b>MetaboCoach Commands:</b>

📸 <b>Send a food photo</b> — instant nutritional analysis
✍️ <b>Describe your meal</b> — "had 2 paneer paratha with salad"

<b>Commands:</b>
/status — Today's health snapshot
/glucose — Current glucose reading
/calories — Calorie & protein progress
/log — Log a meal (send photo or text after)
/pause — Pause notifications for 2 hours
/help — Show this help message

<b>Tips:</b>
• Add a caption to food photos for better accuracy
• I'll remind you to walk after high-carb meals
• I learn your personal food responses over time"""


@router.post("/telegram")
async def telegram_webhook(request: Request, db: AsyncSession = Depends(get_db)):
    """Handle incoming Telegram messages and callback queries."""
    update = await request.json()

    # Handle inline keyboard button presses
    if "callback_query" in update:
        return await _handle_callback(update["callback_query"], db)

    message = update.get("message", {})
    if not message:
        return {"ok": True}

    chat_id = message["chat"]["id"]
    result = await db.execute(select(User).where(User.telegram_chat_id == chat_id))
    user = result.scalar_one_or_none()

    if not user:
        logger.warning("Unknown Telegram user: chat_id=%s", chat_id)
        await telegram_client.send_message(
            chat_id,
            "Hi! You're not registered yet. Please set up your account first.\n"
            "Share your chat ID with your admin: <code>{}</code>".format(chat_id),
        )
        return {"ok": True}

    try:
        if "photo" in message:
            await _handle_photo(message, user, chat_id)
        elif "text" in message:
            await _handle_text(message["text"], user, chat_id)
        elif "voice" in message:
            await telegram_client.send_message(
                chat_id, "Voice notes aren't supported yet. Please type your meal or send a photo."
            )
    except Exception:
        logger.exception("Error processing Telegram message from chat %s", chat_id)
        await telegram_client.send_message(
            chat_id, "Sorry, something went wrong. Please try again."
        )

    return {"ok": True}


async def _handle_photo(message: dict, user: User, chat_id: int):
    """Process a food photo from the user."""
    photo_id = message["photo"][-1]["file_id"]
    photo_bytes = await telegram_client.download_file(photo_id)
    if photo_bytes is None:
        await telegram_client.send_message(chat_id, "Couldn't download the photo. Try again?")
        return

    caption = message.get("caption", "")

    # Send a "processing" message
    await telegram_client.send_message(chat_id, "Analyzing your meal... 🔍")

    analysis = await process_food_photo(
        photo_bytes=photo_bytes,
        user=user,
        caption=caption,
    )
    response_text = _format_meal_response(analysis)

    # Send response with accuracy feedback buttons
    await telegram_client.send_message_with_quick_replies(
        chat_id,
        response_text,
        buttons=[[
            {"text": "✅ Looks right", "callback_data": "meal_accurate"},
            {"text": "❌ Not accurate", "callback_data": "meal_inaccurate"},
        ]],
    )


async def _handle_text(text: str, user: User, chat_id: int):
    """Process a text message from the user."""
    cmd = text.strip().lower()

    # Bot commands
    if cmd.startswith("/start"):
        await telegram_client.send_message(
            chat_id,
            "Welcome to MetaboCoach! 🏥\n\n"
            "I'm your personal metabolic health assistant.\n\n"
            "📸 Send me a <b>food photo</b> for instant analysis\n"
            "✍️ Or just <b>describe what you're eating</b>\n"
            "❓ Ask me anything about your glucose or nutrition\n\n"
            "Type /help for all commands.",
        )
        return

    if cmd.startswith("/help"):
        await telegram_client.send_message(chat_id, HELP_TEXT)
        return

    if cmd.startswith("/status"):
        response = await conversation_engine.respond(
            user_message="Give me today's health snapshot — glucose, calories, protein, steps.",
            user_context=_user_context(user),
        )
        await telegram_client.send_message(chat_id, response)
        return

    if cmd.startswith("/glucose"):
        response = await conversation_engine.respond(
            user_message="What is my current glucose level and trend?",
            user_context=_user_context(user),
        )
        await telegram_client.send_message(chat_id, response)
        return

    if cmd.startswith("/calories"):
        response = await conversation_engine.respond(
            user_message="Show my calorie and protein progress for today.",
            user_context=_user_context(user),
        )
        await telegram_client.send_message(chat_id, response)
        return

    if cmd.startswith("/log"):
        await telegram_client.send_message(
            chat_id,
            "📸 Send a photo of your meal, or describe it:\n"
            "e.g. \"had 2 paneer paratha with salad and chai\"",
        )
        return

    if cmd.startswith("/pause"):
        await throttler.pause_for_user(str(user.id), hours=2)
        await telegram_client.send_message(chat_id, "Notifications paused for 2 hours. 🔇")
        return

    # Natural language — detect food logging vs general chat
    food_keywords = [
        "had", "ate", "eating", "having", "lunch", "dinner", "breakfast",
        "snack", "drank", "drinking", "cooked", "made", "ordered",
    ]
    is_food = any(kw in cmd.split() for kw in food_keywords)

    if is_food:
        await telegram_client.send_message(chat_id, "Analyzing... 🔍")
        analysis = await process_food_text(text=text, user=user)
        response_text = _format_meal_response(analysis)
        await telegram_client.send_message_with_quick_replies(
            chat_id,
            response_text,
            buttons=[[
                {"text": "✅ Looks right", "callback_data": "meal_accurate"},
                {"text": "❌ Not accurate", "callback_data": "meal_inaccurate"},
            ]],
        )
    else:
        response = await conversation_engine.respond(
            user_message=text,
            user_context=_user_context(user),
        )
        await telegram_client.send_message(chat_id, response)


async def _handle_callback(callback_query: dict, db: AsyncSession):
    """Handle inline keyboard button presses."""
    callback_id = callback_query["id"]
    data = callback_query.get("data", "")
    chat_id = callback_query["message"]["chat"]["id"]

    if data == "meal_accurate":
        await telegram_client.answer_callback_query(callback_id, "Great! Logged. ✅")
        await telegram_client.send_message(
            chat_id, "Meal logged! I'll check your glucose in ~60 min to see the impact."
        )
    elif data == "meal_inaccurate":
        await telegram_client.answer_callback_query(callback_id, "Got it, let me know what's off.")
        await telegram_client.send_message(
            chat_id,
            "Sorry about that! Please describe what you actually had "
            "and I'll re-analyze. e.g. \"it was actually 1 paratha not 2\"",
        )
    else:
        await telegram_client.answer_callback_query(callback_id)

    return {"ok": True}


def _user_context(user: User) -> dict:
    """Build user context dict for the conversation engine."""
    return {
        "name": user.name,
        "hba1c": user.hba1c,
        "weight_kg": user.weight_kg,
        "daily_calorie_target": user.daily_calorie_target,
        "daily_protein_target_g": user.daily_protein_target_g,
    }


def _format_meal_response(analysis) -> str:
    """Format meal analysis into a Telegram-friendly message."""
    items_text = ", ".join(item.name for item in analysis.items) if analysis.items else "your meal"

    lines = [
        f"<b>Meal:</b> {items_text}",
        f"📊 ~{analysis.total_calories} cal | "
        f"{analysis.total_protein_g:.0f}g protein | {analysis.total_carbs_g:.0f}g carbs | "
        f"{analysis.total_fat_g:.0f}g fat",
    ]

    if analysis.predicted_spike > 2.0:
        lines.append(f"⚠️ Predicted spike: +{analysis.predicted_spike:.1f} mmol/L")

    if analysis.crash_risk in ("medium", "high"):
        lines.append(f"⚡ Crash risk: {analysis.crash_risk}")

    if analysis.recommendation:
        lines.append(f"\n💡 {analysis.recommendation}")

    return "\n".join(lines)
