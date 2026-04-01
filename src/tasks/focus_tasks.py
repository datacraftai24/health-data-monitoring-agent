"""Scheduled focus coaching tasks — proactive nudges that feel like a real coach.

Key design principles:
- Natural conversation, not command prompts. Don't say "/morning" — just coach.
- Check state before nagging. If win is logged, don't say "you didn't log your win."
- Include glucose context when making energy/productivity suggestions.
- Adapt tone based on streak and patterns (the coach evolves).
"""

import asyncio
import logging
from datetime import date, datetime, timedelta, timezone

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.ai.intent_router import intent_router
from src.messaging.telegram_client import telegram_client
from src.models.base import async_session
from src.models.focus import DailyFocus, FocusBlock, TodoItem
from src.models.glucose import GlucoseReading
from src.models.user import User
from src.tasks import celery_app
from src.utils.glucose_math import trend_arrow_to_label

logger = logging.getLogger(__name__)


async def _get_users(db: AsyncSession) -> list[User]:
    result = await db.execute(select(User).where(User.telegram_chat_id.isnot(None)))
    return result.scalars().all()


async def _get_daily(db: AsyncSession, user: User) -> DailyFocus | None:
    result = await db.execute(
        select(DailyFocus).where(DailyFocus.user_id == user.id, DailyFocus.date == date.today())
    )
    return result.scalar_one_or_none()


async def _get_glucose_context(db: AsyncSession, user: User) -> str:
    """Get glucose context line for coaching messages."""
    gr = await db.execute(
        select(GlucoseReading).where(GlucoseReading.user_id == user.id)
        .order_by(GlucoseReading.timestamp.desc()).limit(1)
    )
    glucose = gr.scalar_one_or_none()
    if not glucose:
        return ""

    trend = trend_arrow_to_label(glucose.trend_arrow) or "stable"
    if glucose.glucose_mmol < 4.5:
        return f"\n\n⚠️ Glucose is {glucose.glucose_mmol:.1f} — eat something first. Low fuel = low willpower."
    elif glucose.glucose_mmol > 9.0:
        return f"\n\n📈 Glucose at {glucose.glucose_mmol:.1f} and {trend}. Consider a walk before deep work."
    else:
        return f"\n\n🩸 Glucose: {glucose.glucose_mmol:.1f} ({trend}) — good energy for focus."


# ============================================================
# EVENING / NIGHT
# ============================================================

@celery_app.task(name="src.tasks.focus_tasks.evening_night_planning")
def evening_night_planning():
    asyncio.get_event_loop().run_until_complete(_evening_night_planning())


async def _evening_night_planning():
    async with async_session() as db:
        for user in await _get_users(db):
            try:
                daily = await _get_daily(db, user)

                # Stats
                blocks_done = 0
                total_min = 0
                phone = 0
                streak = 0
                if daily:
                    br = await db.execute(
                        select(func.count(FocusBlock.id), func.sum(FocusBlock.duration_minutes)).where(
                            FocusBlock.user_id == user.id,
                            FocusBlock.daily_focus_id == daily.id,
                            FocusBlock.completed.is_(True),
                        )
                    )
                    bc, tm = br.one()
                    blocks_done = bc or 0
                    total_min = tm or 0
                    phone = daily.phone_pickups
                    streak = daily.streak_count

                # Check what's already done — don't nag about completed items
                has_win = daily and daily.daily_win
                tomorrow = date.today() + timedelta(days=1)
                tr = await db.execute(
                    select(DailyFocus).where(DailyFocus.user_id == user.id, DailyFocus.date == tomorrow)
                )
                tomorrow_daily = tr.scalar_one_or_none()
                has_one_thing = tomorrow_daily and tomorrow_daily.one_thing

                todo_r = await db.execute(
                    select(func.count(TodoItem.id)).where(
                        TodoItem.user_id == user.id, TodoItem.created_for_date == tomorrow
                    )
                )
                has_todos = (todo_r.scalar() or 0) > 0

                # Build message — only ask for what's missing
                lines = [
                    f"🌙 <b>Day's done.</b>\n",
                    f"Score: {blocks_done} blocks ({total_min} min), {phone} phone pickups"
                ]
                if streak > 1:
                    lines.append(f"Streak: 🔥{streak}")

                todo_items = []
                if not has_win:
                    todo_items.append("Log your biggest WIN — what did you finish today?")
                if not has_one_thing:
                    todo_items.append("What's tomorrow's ONE thing?")
                if not has_todos:
                    todo_items.append("Set tomorrow's to-do list (just the top 3)")

                if todo_items:
                    lines.append("\nBefore bed:")
                    for item in todo_items:
                        lines.append(f"  • {item}")
                else:
                    lines.append("\n✅ Night planning is done. Sleep well.")

                msg = "\n".join(lines)
                await telegram_client.send_message(user.telegram_chat_id, msg)

                # Set pending input for the first missing item
                if not has_win:
                    await intent_router.set_pending_input(str(user.id), "awaiting_win", ttl=3600)
                elif not has_one_thing:
                    await intent_router.set_pending_input(str(user.id), "awaiting_onething", ttl=3600)
                elif not has_todos:
                    await intent_router.set_pending_input(str(user.id), "awaiting_todo", ttl=3600)

            except Exception:
                logger.exception("Error sending night planning to user %s", user.id)


@celery_app.task(name="src.tasks.focus_tasks.night_planning_incomplete")
def night_planning_incomplete():
    asyncio.get_event_loop().run_until_complete(_night_planning_incomplete())


async def _night_planning_incomplete():
    async with async_session() as db:
        for user in await _get_users(db):
            try:
                daily = await _get_daily(db, user)
                missing = []

                # Only nag about things that are actually missing
                if not daily or not daily.daily_win:
                    missing.append("No win logged.")

                tomorrow = date.today() + timedelta(days=1)
                tr = await db.execute(
                    select(DailyFocus).where(DailyFocus.user_id == user.id, DailyFocus.date == tomorrow)
                )
                tomorrow_daily = tr.scalar_one_or_none()
                if not tomorrow_daily or not tomorrow_daily.one_thing:
                    missing.append("No ONE thing for tomorrow.")

                todo_r = await db.execute(
                    select(func.count(TodoItem.id)).where(
                        TodoItem.user_id == user.id, TodoItem.created_for_date == tomorrow
                    )
                )
                if (todo_r.scalar() or 0) == 0:
                    missing.append("No to-do list for tomorrow.")

                if missing:
                    msg = (
                        "⏰ Still incomplete:\n"
                        + "\n".join(f"  • {m}" for m in missing)
                        + "\n\n2 minutes. Then sleep."
                    )
                    await telegram_client.send_message(user.telegram_chat_id, msg)
                # If nothing is missing, don't send anything — they're done
            except Exception:
                logger.exception("Error sending night incomplete to user %s", user.id)


# ============================================================
# MORNING — Natural coaching, not commands
# ============================================================

@celery_app.task(name="src.tasks.focus_tasks.morning_activation_nudge")
def morning_activation_nudge():
    asyncio.get_event_loop().run_until_complete(_morning_activation_nudge())


async def _morning_activation_nudge():
    """8:15 AM — Natural morning check-in. Not a command prompt."""
    async with async_session() as db:
        for user in await _get_users(db):
            try:
                daily = await _get_daily(db, user)
                if daily and daily.ritual_completed_at:
                    continue

                # Get what they planned last night
                today = date.today()
                one_thing = daily.one_thing if daily else None

                todo_r = await db.execute(
                    select(TodoItem).where(
                        TodoItem.user_id == user.id, TodoItem.created_for_date == today
                    ).order_by(TodoItem.priority)
                )
                todos = todo_r.scalars().all()

                glucose_ctx = await _get_glucose_context(db, user)

                # Natural coaching message — no /morning command
                lines = ["☀️ <b>Good morning.</b>\n"]

                if one_thing:
                    lines.append(f"Today's ONE thing: <b>{one_thing}</b>")
                else:
                    lines.append("You didn't set a ONE thing last night. What's the most important thing today?")

                if todos:
                    lines.append("\nYour plan:")
                    for i, t in enumerate(todos, 1):
                        lines.append(f"  {i}. {t.task}")

                lines.append(glucose_ctx)

                if not one_thing:
                    lines.append("\nTell me your ONE thing and let's get started.")
                    await intent_router.set_pending_input(str(user.id), "awaiting_onething", ttl=3600)
                else:
                    lines.append("\nReady? Start your first focus block when you're set.")

                await telegram_client.send_message(user.telegram_chat_id, "\n".join(lines))
            except Exception:
                logger.exception("Error sending morning nudge to user %s", user.id)


@celery_app.task(name="src.tasks.focus_tasks.morning_escalation")
def morning_escalation():
    asyncio.get_event_loop().run_until_complete(_morning_escalation())


async def _morning_escalation():
    """8:35 AM — Gentle escalation if not activated."""
    async with async_session() as db:
        for user in await _get_users(db):
            try:
                daily = await _get_daily(db, user)
                if daily and daily.ritual_completed_at:
                    continue

                # Check if they at least replied to the morning message
                has_blocks = False
                if daily:
                    br = await db.execute(
                        select(func.count(FocusBlock.id)).where(
                            FocusBlock.user_id == user.id, FocusBlock.daily_focus_id == daily.id
                        )
                    )
                    has_blocks = (br.scalar() or 0) > 0

                if has_blocks:
                    continue  # They're working, don't nag

                await telegram_client.send_message(
                    user.telegram_chat_id,
                    "Hey — 20 minutes since the morning check-in.\n"
                    "What's holding you up? Tell me and let's fix it.",
                )
            except Exception:
                logger.exception("Error sending escalation to user %s", user.id)


@celery_app.task(name="src.tasks.focus_tasks.morning_late_escalation")
def morning_late_escalation():
    asyncio.get_event_loop().run_until_complete(_morning_late_escalation())


async def _morning_late_escalation():
    """9:00 AM — Direct but not robotic."""
    async with async_session() as db:
        for user in await _get_users(db):
            try:
                daily = await _get_daily(db, user)
                if daily and daily.ritual_completed_at:
                    continue

                has_blocks = False
                if daily:
                    br = await db.execute(
                        select(func.count(FocusBlock.id)).where(
                            FocusBlock.user_id == user.id, FocusBlock.daily_focus_id == daily.id
                        )
                    )
                    has_blocks = (br.scalar() or 0) > 0

                if not has_blocks:
                    await telegram_client.send_message(
                        user.telegram_chat_id,
                        "It's 9. The morning is slipping.\n"
                        "Pick ONE thing. Start a focus block. That's it.\n\n"
                        "What are you working on right now?",
                    )
                    await intent_router.set_pending_input(str(user.id), "awaiting_onething", ttl=1800)
            except Exception:
                logger.exception("Error sending late escalation to user %s", user.id)


# ============================================================
# DAY CHECK-INS
# ============================================================

@celery_app.task(name="src.tasks.focus_tasks.mid_morning_checkin")
def mid_morning_checkin():
    asyncio.get_event_loop().run_until_complete(_mid_morning_checkin())


async def _mid_morning_checkin():
    async with async_session() as db:
        for user in await _get_users(db):
            try:
                daily = await _get_daily(db, user)
                if not daily or not daily.one_thing:
                    continue
                if daily.one_thing_done:
                    continue

                glucose_ctx = await _get_glucose_context(db, user)
                await telegram_client.send_message(
                    user.telegram_chat_id,
                    f"📍 <b>Quick check.</b>\n"
                    f"ONE thing: <b>{daily.one_thing}</b>\n"
                    f"How's it going? Still on it?"
                    f"{glucose_ctx}",
                )
            except Exception:
                logger.exception("Error sending mid-morning check to user %s", user.id)


@celery_app.task(name="src.tasks.focus_tasks.afternoon_block_reminder")
def afternoon_block_reminder():
    asyncio.get_event_loop().run_until_complete(_afternoon_block_reminder())


async def _afternoon_block_reminder():
    async with async_session() as db:
        for user in await _get_users(db):
            try:
                daily = await _get_daily(db, user)
                one_thing = daily.one_thing if daily else None

                glucose_ctx = await _get_glucose_context(db, user)

                one_line = f"\n{daily.one_thing} — done yet?" if one_thing and not daily.one_thing_done else ""
                await telegram_client.send_message(
                    user.telegram_chat_id,
                    f"⏱ <b>Afternoon block.</b> Phone away, deep work time."
                    f"{one_line}"
                    f"{glucose_ctx}",
                )
            except Exception:
                logger.exception("Error sending afternoon reminder to user %s", user.id)


@celery_app.task(name="src.tasks.focus_tasks.builder_block_reminder")
def builder_block_reminder():
    asyncio.get_event_loop().run_until_complete(_builder_block_reminder())


async def _builder_block_reminder():
    async with async_session() as db:
        for user in await _get_users(db):
            try:
                glucose_ctx = await _get_glucose_context(db, user)
                await telegram_client.send_message(
                    user.telegram_chat_id,
                    f"🔨 <b>Builder block.</b> What are you shipping this afternoon?"
                    f"{glucose_ctx}",
                )
            except Exception:
                logger.exception("Error sending builder reminder to user %s", user.id)


@celery_app.task(name="src.tasks.focus_tasks.day_closing")
def day_closing():
    asyncio.get_event_loop().run_until_complete(_day_closing())


async def _day_closing():
    async with async_session() as db:
        for user in await _get_users(db):
            try:
                daily = await _get_daily(db, user)

                # Don't ask for win if already logged
                if daily and daily.daily_win:
                    continue

                await telegram_client.send_message(
                    user.telegram_chat_id,
                    "🌅 <b>Wrapping up.</b>\n"
                    "What did you FINISH today? Not started — finished.\n\n"
                    "Tell me your biggest win.",
                )
                await intent_router.set_pending_input(str(user.id), "awaiting_win", ttl=3600)
            except Exception:
                logger.exception("Error sending day closing to user %s", user.id)
