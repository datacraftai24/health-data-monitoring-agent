"""Scheduled focus coaching tasks — proactive nudges that drive the user's day."""

import asyncio
import logging
from datetime import date, datetime, timedelta, timezone

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.ai.agents.focus_agent import RITUAL_ITEMS, focus_agent
from src.messaging.telegram_client import telegram_client
from src.models.base import async_session
from src.models.focus import DailyFocus, FocusBlock, ParkedIdea, TodoItem
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


# ============================================================
# EVENING / NIGHT NUDGES (starting tonight)
# ============================================================

@celery_app.task(name="src.tasks.focus_tasks.evening_night_planning")
def evening_night_planning():
    """9:00 PM — Night planning prompt."""
    asyncio.get_event_loop().run_until_complete(_evening_night_planning())


async def _evening_night_planning():
    async with async_session() as db:
        for user in await _get_users(db):
            try:
                daily = await _get_daily(db, user)

                # Today's stats
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

                msg = (
                    f"🌙 <b>Night planning time.</b>\n\n"
                    f"Today's score: {blocks_done}/4 blocks, {phone} phone pickups, streak 🔥{streak}\n\n"
                    f"Before bed, do these 3 things:\n\n"
                    f"1️⃣ What was your ONE WIN today?\n"
                    f"   /1win [your biggest win]\n\n"
                    f"2️⃣ Set tomorrow's ONE thing:\n"
                    f"   /onething [task]\n\n"
                    f"3️⃣ Set tomorrow's to-do list:\n"
                    f"   /todo [task 1]\n"
                    f"   /todo [task 2]\n"
                    f"   /todo [task 3]\n\n"
                    f"Type /tonight to see what's left to set."
                )
                await telegram_client.send_message(user.telegram_chat_id, msg)
            except Exception:
                logger.exception("Error sending night planning to user %s", user.id)


@celery_app.task(name="src.tasks.focus_tasks.night_planning_incomplete")
def night_planning_incomplete():
    """9:45 PM — Nudge if night planning isn't done."""
    asyncio.get_event_loop().run_until_complete(_night_planning_incomplete())


async def _night_planning_incomplete():
    async with async_session() as db:
        for user in await _get_users(db):
            try:
                daily = await _get_daily(db, user)
                missing = []

                if not daily or not daily.daily_win:
                    missing.append("You didn't log today's win. What did you FINISH? /1win")

                # Check tomorrow's one thing
                tomorrow = date.today() + timedelta(days=1)
                tr = await db.execute(
                    select(DailyFocus).where(DailyFocus.user_id == user.id, DailyFocus.date == tomorrow)
                )
                tomorrow_daily = tr.scalar_one_or_none()
                if not tomorrow_daily or not tomorrow_daily.one_thing:
                    missing.append("No ONE thing set for tomorrow. You'll drift. /onething [task]")

                todo_r = await db.execute(
                    select(func.count(TodoItem.id)).where(
                        TodoItem.user_id == user.id, TodoItem.created_for_date == tomorrow
                    )
                )
                if (todo_r.scalar() or 0) == 0:
                    missing.append("No to-do list. Tomorrow starts with chaos. /todo [task]")

                if missing:
                    msg = "⏰ <b>Night planning isn't done.</b>\n\n" + "\n".join(f"• {m}" for m in missing)
                    msg += "\n\nFinish it now. Takes 2 minutes."
                    await telegram_client.send_message(user.telegram_chat_id, msg)
            except Exception:
                logger.exception("Error sending night incomplete to user %s", user.id)


# ============================================================
# MORNING NUDGES
# ============================================================

@celery_app.task(name="src.tasks.focus_tasks.morning_activation_nudge")
def morning_activation_nudge():
    """8:15 AM weekdays — Morning activation check."""
    asyncio.get_event_loop().run_until_complete(_morning_activation_nudge())


async def _morning_activation_nudge():
    async with async_session() as db:
        for user in await _get_users(db):
            try:
                daily = await _get_daily(db, user)
                if daily and daily.ritual_completed_at:
                    continue

                # Include tomorrow's todos (set last night)
                today = date.today()
                todo_r = await db.execute(
                    select(TodoItem).where(
                        TodoItem.user_id == user.id, TodoItem.created_for_date == today
                    ).order_by(TodoItem.priority)
                )
                todos = todo_r.scalars().all()

                one_thing = daily.one_thing if daily else None
                todo_lines = ""
                if todos:
                    todo_lines = "\n📝 To-dos:\n" + "\n".join(f"  {i}. {t.text}" for i, t in enumerate(todos, 1))

                one_line = f"\n🎯 ONE THING: {one_thing}" if one_thing else ""

                msg = (
                    f"☀️ <b>Morning activation check.</b> /morning\n"
                    f"{one_line}"
                    f"{todo_lines}\n\n"
                    f"Activate first. Then execute."
                )
                await telegram_client.send_message(user.telegram_chat_id, msg)
            except Exception:
                logger.exception("Error sending morning nudge to user %s", user.id)


@celery_app.task(name="src.tasks.focus_tasks.morning_escalation")
def morning_escalation():
    """8:35 AM weekdays — Escalation if not activated."""
    asyncio.get_event_loop().run_until_complete(_morning_escalation())


async def _morning_escalation():
    async with async_session() as db:
        for user in await _get_users(db):
            try:
                daily = await _get_daily(db, user)
                if daily and daily.ritual_completed_at:
                    continue
                await telegram_client.send_message(
                    user.telegram_chat_id,
                    "⏰ You're drifting. It's 8:35 and activation isn't done.\n"
                    "15-minute rule: start within 60 seconds of reading this.\n/morning",
                )
            except Exception:
                logger.exception("Error sending escalation to user %s", user.id)


@celery_app.task(name="src.tasks.focus_tasks.morning_late_escalation")
def morning_late_escalation():
    """9:00 AM weekdays — Late escalation."""
    asyncio.get_event_loop().run_until_complete(_morning_late_escalation())


async def _morning_late_escalation():
    async with async_session() as db:
        for user in await _get_users(db):
            try:
                daily = await _get_daily(db, user)
                if daily and daily.ritual_completed_at:
                    continue

                # Check if any focus blocks started
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
                        "🔴 It's 9:00. Work starts NOW. No activation. No focus blocks.\n"
                        "This is the pattern. You know what to do.\n"
                        "/morning → /onething → /focus\n"
                        "Right now. Not in 15 minutes.",
                    )
            except Exception:
                logger.exception("Error sending late escalation to user %s", user.id)


# ============================================================
# DAY CHECK-INS
# ============================================================

@celery_app.task(name="src.tasks.focus_tasks.mid_morning_checkin")
def mid_morning_checkin():
    """10:30 AM weekdays — Check in on ONE thing."""
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

                # Include glucose context
                gr = await db.execute(
                    select(GlucoseReading).where(GlucoseReading.user_id == user.id)
                    .order_by(GlucoseReading.timestamp.desc()).limit(1)
                )
                glucose = gr.scalar_one_or_none()
                glucose_line = ""
                if glucose:
                    glucose_line = f"\n📈 Glucose: {glucose.glucose_mmol:.1f} mmol/L ({trend_arrow_to_label(glucose.trend_arrow)})"

                await telegram_client.send_message(
                    user.telegram_chat_id,
                    f"📍 <b>10:30 AM check-in.</b>\n"
                    f"ONE thing: <b>{daily.one_thing}</b>\n"
                    f"Status? Still on it or did something pull you away?"
                    f"{glucose_line}",
                )
            except Exception:
                logger.exception("Error sending mid-morning check to user %s", user.id)


@celery_app.task(name="src.tasks.focus_tasks.afternoon_block_reminder")
def afternoon_block_reminder():
    """1:25 PM weekdays — Afternoon block reminder."""
    asyncio.get_event_loop().run_until_complete(_afternoon_block_reminder())


async def _afternoon_block_reminder():
    async with async_session() as db:
        for user in await _get_users(db):
            try:
                daily = await _get_daily(db, user)
                one_thing = daily.one_thing if daily else "not set"

                # Pre-block glucose check
                gr = await db.execute(
                    select(GlucoseReading).where(GlucoseReading.user_id == user.id)
                    .order_by(GlucoseReading.timestamp.desc()).limit(1)
                )
                glucose = gr.scalar_one_or_none()
                glucose_warning = ""
                if glucose and glucose.glucose_mmol < 4.5:
                    glucose_warning = (
                        f"\n\n⚠️ Your glucose is at {glucose.glucose_mmol:.1f} and low.\n"
                        f"Eat something before starting. Low glucose = low willpower."
                    )

                await telegram_client.send_message(
                    user.telegram_chat_id,
                    f"⏱ <b>Afternoon block starts in 5 minutes.</b>\n"
                    f"Phone away. /focus\n"
                    f"ONE thing: {one_thing} — is it done yet?"
                    f"{glucose_warning}",
                )
            except Exception:
                logger.exception("Error sending afternoon reminder to user %s", user.id)


@celery_app.task(name="src.tasks.focus_tasks.builder_block_reminder")
def builder_block_reminder():
    """3:15 PM weekdays — Builder block prompt."""
    asyncio.get_event_loop().run_until_complete(_builder_block_reminder())


async def _builder_block_reminder():
    async with async_session() as db:
        for user in await _get_users(db):
            try:
                await telegram_client.send_message(
                    user.telegram_chat_id,
                    "🔨 <b>Builder block.</b> What are you building today?\n"
                    "ResidenceHive / EB-1A / MetaboCoach — pick one. /focus",
                )
            except Exception:
                logger.exception("Error sending builder reminder to user %s", user.id)


@celery_app.task(name="src.tasks.focus_tasks.day_closing")
def day_closing():
    """5:00 PM weekdays — Day closing."""
    asyncio.get_event_loop().run_until_complete(_day_closing())


async def _day_closing():
    async with async_session() as db:
        for user in await _get_users(db):
            try:
                await telegram_client.send_message(
                    user.telegram_chat_id,
                    "🌅 <b>Day closing in 1 hour.</b>\n"
                    "Log what you FINISHED: /1win [description]\n"
                    "Not what you started. What you finished.",
                )
            except Exception:
                logger.exception("Error sending day closing to user %s", user.id)
