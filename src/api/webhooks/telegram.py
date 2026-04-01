"""Telegram bot webhook — routes messages through intent classifier to specialized agents.

Key behaviors:
- Pending input: If the agent asked for specific input (ONE thing, win, etc.),
  the next message bypasses intent router and goes directly to the expected handler.
- Context extraction: After every meaningful exchange, we extract and update the
  user's persistent context profile (who they are, what they're working on, patterns).
- Meal fallback: If food photo analysis returns 0 calories, asks for text description.
"""

import logging

from fastapi import APIRouter, Depends, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.ai.agents.focus_agent import focus_agent
from src.ai.agents.food_agent import food_agent
from src.ai.agents.general_agent import general_agent
from src.ai.agents.health_agent import health_agent
from src.ai.intent_router import intent_router
from src.engine.user_context import user_context_manager
from src.messaging.telegram_client import telegram_client
from src.messaging.throttler import throttler
from src.models.base import get_db
from src.models.conversation import ConversationLog
from src.models.user import User

logger = logging.getLogger(__name__)

router = APIRouter()

HELP_TEXT = """<b>MetaboCoach</b>

<b>Just talk to me naturally.</b> I understand context.

<b>Health:</b>
📸 Send a food photo — instant analysis + glucose tracking
✍️ Describe your meal — "had 2 paneer paratha with salad"
Ask about glucose, calories, or health anytime

<b>Focus:</b>
Tell me your ONE thing for today
Say "done" when you finish it
Ask for your to-do list anytime
Tell me what you need to do and I'll remember it

<b>Commands (optional):</b>
/status — Full daily dashboard
/todo [task] — Add a task
/focus [task] — Start a focus block
/stop — End focus block
/park [idea] — Save for later
/pause — Mute notifications 2 hours
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
                "I'm your personal health + focus coach.\n\n"
                "📸 Send a <b>food photo</b> for instant analysis\n"
                "🎯 Tell me what you're working on today\n"
                "❓ Ask me anything about glucose or nutrition\n\n"
                "Just talk to me naturally. Type /help for all options.",
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

        # --- Check for pending input (context-aware parsing) ---
        user_id = str(user.id)
        pending = await intent_router.get_pending_input(user_id)
        if pending and not has_photo and not text.startswith("/"):
            await intent_router.clear_pending_input(user_id)
            response, buttons, agent_name = await _handle_pending_input(
                pending, text, user, db
            )
            if response:
                await _send_and_log(
                    chat_id, response, buttons, user, db, text, agent_name, "pending_" + pending
                )
                return {"ok": True}

        # --- Normal intent classification ---
        # Check focus block state
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
        buttons = None
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

            # Meal photo fallback: if analysis returned 0 calories, ask for text
            if "~0 cal" in response or "0g protein | 0g carbs | 0g fat" in response:
                response = (
                    "I couldn't identify the food in that photo clearly.\n\n"
                    "Could you describe what you're eating? For example:\n"
                    '"rice, sabzi, and paysam"'
                )
                # Set pending input so the next message gets routed to food
                await intent_router.set_pending_input(user_id, "awaiting_food_description")

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

            # If the focus agent just asked for ONE thing or win, set pending input
            if response and "set your ONE thing" in response.lower():
                await intent_router.set_pending_input(user_id, "awaiting_onething")
            elif response and "log your win" in response.lower():
                await intent_router.set_pending_input(user_id, "awaiting_win")

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

        # Extract and update user context profile (async, non-blocking)
        if response and text:
            try:
                await user_context_manager.extract_and_update(db, user, text, response)
            except Exception:
                logger.debug("Context extraction failed (non-critical)")

    except Exception:
        logger.exception("Error processing Telegram message from chat %s", chat_id)
        await telegram_client.send_message(chat_id, "Sorry, something went wrong. Please try again.")

    return {"ok": True}


async def _handle_pending_input(
    pending: str, text: str, user: User, db: AsyncSession
) -> tuple[str | None, list | None, str | None]:
    """Handle a message when we're expecting specific input from the user."""

    if pending == "awaiting_onething":
        # Treat this message as the ONE thing
        response, buttons = await focus_agent.handle(f"/onething {text}", user, db)
        return response, buttons, "focus"

    elif pending == "awaiting_win":
        # Treat this message as the daily win
        response, buttons = await focus_agent.handle(f"/1win {text}", user, db)
        return response, buttons, "focus"

    elif pending == "awaiting_food_description":
        # Treat this message as food description (fallback from failed photo)
        response = await food_agent.handle_text(text, user, 0, db)
        return response, None, "food"

    elif pending == "awaiting_todo":
        response, buttons = await focus_agent.handle(f"/todo {text}", user, db)
        return response, buttons, "focus"

    return None, None, None


async def _send_and_log(
    chat_id: int, response: str, buttons: list | None,
    user: User, db: AsyncSession, user_msg: str, agent_name: str, intent: str,
):
    """Send response and log the conversation."""
    if buttons:
        await telegram_client.send_message_with_quick_replies(chat_id, response, buttons)
    else:
        await telegram_client.send_message(chat_id, response)

    db.add(ConversationLog(
        user_id=user.id, direction="in", intent=intent,
        message=user_msg, has_photo=False,
    ))
    db.add(ConversationLog(
        user_id=user.id, direction="out", intent=intent,
        agent=agent_name, message=response[:2000],
    ))
    await db.commit()

    # Extract context
    try:
        await user_context_manager.extract_and_update(db, user, user_msg, response)
    except Exception:
        pass


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

    if data == "meal_accurate":
        await telegram_client.answer_callback_query(callback_id, "Logged. ✅")
        await telegram_client.send_message(
            chat_id, "Meal logged! I'll check your glucose in ~60 min."
        )
    elif data == "meal_inaccurate":
        await telegram_client.answer_callback_query(callback_id, "Got it.")
        await telegram_client.send_message(
            chat_id,
            "What did you actually have? Describe it and I'll re-analyze.",
        )
        await intent_router.set_pending_input(str(user.id), "awaiting_food_description")
    elif data.startswith("ritual_"):
        # Morning ritual checkbox
        response, buttons = await focus_agent.handle(f"/{data}", user, db)
        await telegram_client.answer_callback_query(callback_id, "✅")
        if response:
            if buttons:
                await telegram_client.send_message_with_quick_replies(chat_id, response, buttons)
            else:
                await telegram_client.send_message(chat_id, response)
    else:
        await telegram_client.answer_callback_query(callback_id)

    return {"ok": True}
