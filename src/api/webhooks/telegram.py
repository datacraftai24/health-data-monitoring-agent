"""Telegram bot webhook — routes messages through intent classifier to specialized agents."""

import logging

from fastapi import APIRouter, Depends, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.ai.agents.focus_agent import focus_agent
from src.ai.agents.food_agent import food_agent
from src.ai.agents.general_agent import general_agent
from src.ai.agents.health_agent import health_agent
from src.ai.intent_router import intent_router
from src.messaging.telegram_client import telegram_client
from src.messaging.throttler import throttler
from src.models.base import get_db
from src.models.conversation import ConversationLog
from src.models.user import User

logger = logging.getLogger(__name__)

router = APIRouter()

HELP_TEXT = """<b>MetaboCoach Commands:</b>

<b>Health:</b>
📸 Send a food photo — instant analysis + glucose tracking
✍️ Describe your meal — "had 2 paneer paratha with salad"
/glucose — Current glucose reading
/calories — Calorie & protein progress

<b>Focus:</b>
/morning — Morning activation checklist
/onething [task] — Set today's ONE thing
/done — Mark ONE thing complete
/focus [task] — Start a focus block
/stop — End focus block
/park [idea] — Park an idea for Sunday review
/phone — Log phone pickup
/1win [description] — Log today's biggest win
/todo [task] — Add to-do item
/todone [number] — Check off a to-do
/tonight — Night planning status

<b>Other:</b>
/status — Full daily dashboard
/tune [request] — Request a system adjustment
/ideas — Review parked ideas (Sundays)
/pause — Pause notifications 2 hours
/help — This message"""


@router.post("/telegram")
async def telegram_webhook(request: Request, db: AsyncSession = Depends(get_db)):
    """Handle incoming Telegram messages via intent router → agent dispatch."""
    update = await request.json()

    # Callback queries (inline button presses)
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
        has_photo = "photo" in message
        text = message.get("text", "") or message.get("caption", "")

        # Quick command shortcuts
        if text.strip().lower() in ("/start",):
            await telegram_client.send_message(
                chat_id,
                "Welcome to MetaboCoach! 🏥\n\n"
                "I'm your personal health + focus coaching assistant.\n\n"
                "📸 Send a <b>food photo</b> for instant analysis\n"
                "🎯 /morning to start your day\n"
                "❓ Ask me anything about glucose or nutrition\n\n"
                "Type /help for all commands.",
            )
            return {"ok": True}

        if text.strip().lower() == "/help":
            await telegram_client.send_message(chat_id, HELP_TEXT)
            return {"ok": True}

        if text.strip().lower().startswith("/pause"):
            await throttler.pause_for_user(str(user.id), hours=2)
            await telegram_client.send_message(chat_id, "Notifications paused for 2 hours. 🔇")
            return {"ok": True}

        if text.strip().lower() == "/log":
            await telegram_client.send_message(
                chat_id,
                "📸 Send a photo of your meal, or describe it:\n"
                'e.g. "had 2 paneer paratha with salad and chai"',
            )
            return {"ok": True}

        # Check if in focus block — block non-health messages
        if not has_photo and not text.strip().lower().startswith(("/stop", "/park", "/phone")):
            in_focus = await focus_agent.is_in_focus_block(user, db)
            intent = await intent_router.classify(text, has_photo)
            if in_focus and intent not in ("food_log", "glucose_check", "health_status", "focus_command"):
                await telegram_client.send_message(
                    chat_id,
                    "🚫 You're in a focus block.\n"
                    "/park [idea] to capture it, or /stop to end the block.\n"
                    "Back to work.",
                )
                return {"ok": True}
        else:
            intent = await intent_router.classify(text, has_photo)

        # Log incoming message
        db.add(ConversationLog(
            user_id=user.id, direction="in", intent=intent,
            message=text or "[photo]", has_photo=has_photo,
        ))
        await db.commit()

        # Route to agent
        response = None
        agent_name = None

        if intent == "food_log" and has_photo:
            agent_name = "food"
            photo_id = message["photo"][-1]["file_id"]
            photo_bytes = await telegram_client.download_file(photo_id)
            if not photo_bytes:
                await telegram_client.send_message(chat_id, "Couldn't download the photo. Try again?")
                return {"ok": True}
            await telegram_client.send_message(chat_id, "Analyzing your meal... 🔍")
            caption = message.get("caption", "")
            response = await food_agent.handle_photo(photo_bytes, caption, user, chat_id, db)
            await telegram_client.send_message(chat_id, response)

        elif intent == "food_log":
            agent_name = "food"
            await telegram_client.send_message(chat_id, "Analyzing... 🔍")
            response = await food_agent.handle_text(text, user, chat_id, db)
            await telegram_client.send_message(chat_id, response)

        elif intent in ("glucose_check", "health_status"):
            agent_name = "health"
            response = await health_agent.handle(text, user, db)
            await telegram_client.send_message(chat_id, response)

        elif intent == "focus_command":
            agent_name = "focus"
            response, buttons = await focus_agent.handle(text, user, db)
            if buttons:
                await telegram_client.send_message_with_quick_replies(chat_id, response, buttons)
            else:
                await telegram_client.send_message(chat_id, response)

        else:
            agent_name = "general"
            response = await general_agent.handle(text, user, db)
            await telegram_client.send_message(chat_id, response)

        # Log outgoing response
        if response:
            db.add(ConversationLog(
                user_id=user.id, direction="out", intent=intent,
                agent=agent_name, message=response[:2000],
            ))
            await db.commit()

    except Exception:
        logger.exception("Error processing Telegram message from chat %s", chat_id)
        await telegram_client.send_message(chat_id, "Sorry, something went wrong. Please try again.")

    return {"ok": True}


async def _handle_callback(callback_query: dict, db: AsyncSession):
    """Handle inline keyboard button presses."""
    callback_id = callback_query["id"]
    data = callback_query.get("data", "")
    chat_id = callback_query["message"]["chat"]["id"]

    result = await db.execute(select(User).where(User.telegram_chat_id == chat_id))
    user = result.scalar_one_or_none()
    if not user:
        await telegram_client.answer_callback_query(callback_id)
        return {"ok": True}

    # Morning ritual toggles
    if data.startswith("ritual_"):
        field = data[len("ritual_"):]
        response, buttons = await focus_agent.handle_ritual_callback(field, user, db)
        await telegram_client.answer_callback_query(callback_id, "Updated!")
        if buttons:
            # Edit the original message with updated checklist
            msg_id = callback_query["message"]["message_id"]
            await telegram_client.send_message_with_quick_replies(chat_id, response, buttons)
        else:
            await telegram_client.send_message(chat_id, response)

    elif data == "meal_accurate":
        await telegram_client.answer_callback_query(callback_id, "Logged! ✅")
        await telegram_client.send_message(
            chat_id, "Meal logged! I'll check your glucose in ~60 min to see the impact."
        )

    elif data == "meal_inaccurate":
        await telegram_client.answer_callback_query(callback_id, "Got it.")
        await telegram_client.send_message(
            chat_id,
            "Sorry about that! Describe what you actually had "
            'and I\'ll re-analyze. e.g. "it was actually 1 paratha not 2"',
        )

    else:
        await telegram_client.answer_callback_query(callback_id)

    return {"ok": True}
