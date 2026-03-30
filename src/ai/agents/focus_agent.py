"""Focus agent — handles all focus system commands and coaching."""

import logging
from datetime import date, datetime, timedelta, timezone

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.engine.memory_manager import memory_manager
from src.models.focus import DailyFocus, FocusBlock, ParkedIdea, TodoItem, TuneRequest
from src.models.glucose import GlucoseReading
from src.models.user import User
from src.utils.glucose_math import trend_arrow_to_label

logger = logging.getLogger(__name__)

RITUAL_ITEMS = [
    ("ritual_shower", "Shower"),
    ("ritual_real_clothes", "Real clothes on"),
    ("ritual_face_ice", "Face in ice water"),
    ("ritual_phone_away", "Phone in another room"),
    ("ritual_one_thing_set", "ONE thing decided"),
]


class FocusAgent:
    """Handles all focus system commands."""

    async def handle(self, message: str, user: User, db: AsyncSession) -> tuple[str, list | None]:
        """Route focus command and return (response_text, optional_buttons)."""
        cmd = message.strip()
        cmd_lower = cmd.lower()

        if cmd_lower.startswith("/morning"):
            return await self._morning(user, db)
        elif cmd_lower.startswith("/onething"):
            task = cmd[len("/onething"):].strip()
            return await self._onething(user, db, task)
        elif cmd_lower.startswith("/done"):
            return await self._done(user, db)
        elif cmd_lower.startswith("/focus"):
            task = cmd[len("/focus"):].strip()
            return await self._focus_start(user, db, task)
        elif cmd_lower.startswith("/stop"):
            return await self._focus_stop(user, db)
        elif cmd_lower.startswith("/park"):
            idea = cmd[len("/park"):].strip()
            return await self._park(user, db, idea)
        elif cmd_lower.startswith("/phone"):
            return await self._phone(user, db)
        elif cmd_lower.startswith("/1win"):
            win = cmd[len("/1win"):].strip()
            return await self._daily_win(user, db, win)
        elif cmd_lower.startswith("/win"):
            win = cmd[len("/win"):].strip()
            return await self._daily_win(user, db, win)
        elif cmd_lower.startswith("/todone"):
            num = cmd[len("/todone"):].strip()
            return await self._todone(user, db, num)
        elif cmd_lower.startswith("/todolist"):
            return await self._todolist(user, db)
        elif cmd_lower.startswith("/todoclear"):
            return await self._todoclear(user, db)
        elif cmd_lower.startswith("/todo"):
            task = cmd[len("/todo"):].strip()
            return await self._todo(user, db, task)
        elif cmd_lower.startswith("/tonight"):
            return await self._tonight(user, db)
        elif cmd_lower.startswith("/tune"):
            if cmd_lower.startswith("/tuneapply"):
                return await self._tune_apply(user, db, cmd[len("/tuneapply"):].strip())
            elif cmd_lower.startswith("/tunereject"):
                return await self._tune_reject(user, db, cmd[len("/tunereject"):].strip())
            else:
                request = cmd[len("/tune"):].strip()
                return await self._tune(user, db, request)
        elif cmd_lower.startswith("/ideas"):
            return await self._ideas(user, db)
        elif cmd_lower.startswith("/status"):
            return await self._status(user, db)
        else:
            return "Unknown focus command. Type /help for available commands.", None

    async def _get_or_create_daily(self, user: User, db: AsyncSession) -> DailyFocus:
        """Get or create today's DailyFocus record."""
        today = date.today()
        result = await db.execute(
            select(DailyFocus).where(DailyFocus.user_id == user.id, DailyFocus.date == today)
        )
        daily = result.scalar_one_or_none()
        if not daily:
            # Calculate streak
            yesterday = today - timedelta(days=1)
            prev = await db.execute(
                select(DailyFocus).where(DailyFocus.user_id == user.id, DailyFocus.date == yesterday)
            )
            prev_daily = prev.scalar_one_or_none()
            streak = (prev_daily.streak_count if prev_daily and prev_daily.ritual_completed_at else 0)

            daily = DailyFocus(user_id=user.id, date=today, streak_count=streak)
            db.add(daily)
            await db.commit()
            await db.refresh(daily)
        return daily

    # --- /morning ---
    async def _morning(self, user: User, db: AsyncSession):
        daily = await self._get_or_create_daily(user, db)

        if daily.ritual_completed_at:
            return f"Already activated today. Streak: 🔥 {daily.streak_count}. Get to work.", None

        # Build checklist with inline buttons
        buttons = []
        for field, label in RITUAL_ITEMS:
            checked = getattr(daily, field, False)
            icon = "✅" if checked else "⬜"
            buttons.append([{"text": f"{icon} {label}", "callback_data": f"ritual_{field}"}])

        return "⚡ <b>Morning Activation</b>\nTap each item to check off:", buttons

    async def handle_ritual_callback(self, field: str, user: User, db: AsyncSession) -> tuple[str, list | None]:
        """Toggle a ritual item and return updated checklist."""
        daily = await self._get_or_create_daily(user, db)

        current = getattr(daily, field, False)
        setattr(daily, field, not current)

        # Check if all complete
        all_done = all(getattr(daily, f, False) for f, _ in RITUAL_ITEMS)
        if all_done and not daily.ritual_completed_at:
            daily.ritual_completed_at = datetime.now(timezone.utc)
            daily.streak_count += 1
            await db.commit()

            await memory_manager.update(
                db, str(user.id), "current_streak", str(daily.streak_count), "focus"
            )

            return (
                f"⚡ <b>Activation complete!</b> Streak: 🔥 {daily.streak_count} days.\n"
                f"Now set your ONE thing: /onething [task]",
                None,
            )

        await db.commit()

        # Return updated checklist
        buttons = []
        for f, label in RITUAL_ITEMS:
            checked = getattr(daily, f, False)
            icon = "✅" if checked else "⬜"
            buttons.append([{"text": f"{icon} {label}", "callback_data": f"ritual_{f}"}])

        return "⚡ <b>Morning Activation</b>\nTap each item to check off:", buttons

    # --- /onething ---
    async def _onething(self, user, db, task):
        if not task:
            return "Usage: /onething [task description]\nExample: /onething Finish API integration", None

        daily = await self._get_or_create_daily(user, db)

        if daily.one_thing and not daily.one_thing_done:
            return (
                f"Your ONE thing is already: <b>{daily.one_thing}</b>\n"
                f"Send /onething [new task] again to replace it.",
                None,
            )

        daily.one_thing = task
        daily.one_thing_set_at = datetime.now(timezone.utc)
        daily.one_thing_done = False
        await db.commit()

        return (
            f"🎯 <b>ONE THING locked:</b>\n→ {task}\n\n"
            f"This is the only thing that matters today.\n"
            f"I'll check in at 11 AM and 3 PM.",
            None,
        )

    # --- /done ---
    async def _done(self, user, db):
        daily = await self._get_or_create_daily(user, db)

        if not daily.one_thing:
            return "No ONE thing set. Use /onething [task] first.", None
        if daily.one_thing_done:
            return f"Already done: {daily.one_thing} ✅", None

        daily.one_thing_done = True
        daily.one_thing_done_at = datetime.now(timezone.utc)
        await db.commit()

        time_str = datetime.now().strftime("%I:%M %p")
        return f"✅ <b>ONE THING DONE:</b> {daily.one_thing}\nCompleted at {time_str}. That's a win.", None

    # --- /focus + /stop ---
    async def _focus_start(self, user, db, task):
        daily = await self._get_or_create_daily(user, db)

        # Count today's blocks
        blocks_result = await db.execute(
            select(func.count(FocusBlock.id)).where(
                FocusBlock.user_id == user.id, FocusBlock.daily_focus_id == daily.id
            )
        )
        block_count = blocks_result.scalar() or 0

        if block_count >= 4:
            return "Max 4 blocks per day reached. Rest up for tomorrow.", None

        # Check for active block
        active = await db.execute(
            select(FocusBlock).where(
                FocusBlock.user_id == user.id,
                FocusBlock.daily_focus_id == daily.id,
                FocusBlock.ended_at.is_(None),
            )
        )
        if active.scalar_one_or_none():
            return "🚫 You already have an active focus block. /stop to end it first.", None

        block = FocusBlock(
            user_id=user.id,
            daily_focus_id=daily.id,
            block_number=block_count + 1,
            label=f"Deep Work #{block_count + 1}",
            started_at=datetime.now(timezone.utc),
            task_description=task or None,
        )
        db.add(block)
        await db.commit()

        task_line = f"Task: {task}\n" if task else ""
        return (
            f"⏱ <b>FOCUS BLOCK #{block_count + 1} STARTED</b>\n"
            f"{task_line}"
            f"Phone away. Single task. No switching.\n\n"
            f"Type /stop when done, or /park to capture a stray idea.",
            None,
        )

    async def _focus_stop(self, user, db):
        daily = await self._get_or_create_daily(user, db)

        result = await db.execute(
            select(FocusBlock).where(
                FocusBlock.user_id == user.id,
                FocusBlock.daily_focus_id == daily.id,
                FocusBlock.ended_at.is_(None),
            )
        )
        block = result.scalar_one_or_none()
        if not block:
            return "No active focus block to stop.", None

        block.ended_at = datetime.now(timezone.utc)
        duration = int((block.ended_at - block.started_at).total_seconds() / 60)
        block.duration_minutes = duration
        block.completed = duration >= 15
        await db.commit()

        # Total today
        total_result = await db.execute(
            select(func.sum(FocusBlock.duration_minutes)).where(
                FocusBlock.user_id == user.id,
                FocusBlock.daily_focus_id == daily.id,
                FocusBlock.completed.is_(True),
            )
        )
        total_min = total_result.scalar() or 0

        task_line = f"Task: {block.task_description}\n" if block.task_description else ""
        status = "✅" if block.completed else "⚠️ (under 15 min, doesn't count)"

        return (
            f"{status} <b>Block #{block.block_number} complete: {duration} minutes</b>\n"
            f"{task_line}"
            f"Total today: {total_min // 60}h {total_min % 60}m\n\n"
            f"Take a break.",
            None,
        )

    async def is_in_focus_block(self, user: User, db: AsyncSession) -> bool:
        """Check if user has an active focus block."""
        today = date.today()
        result = await db.execute(
            select(DailyFocus).where(DailyFocus.user_id == user.id, DailyFocus.date == today)
        )
        daily = result.scalar_one_or_none()
        if not daily:
            return False

        active = await db.execute(
            select(FocusBlock).where(
                FocusBlock.user_id == user.id,
                FocusBlock.daily_focus_id == daily.id,
                FocusBlock.ended_at.is_(None),
            )
        )
        return active.scalar_one_or_none() is not None

    # --- /park ---
    async def _park(self, user, db, idea):
        if not idea:
            return "Usage: /park [idea]\nExample: /park Build pickleball booking SaaS", None

        db.add(ParkedIdea(user_id=user.id, text=idea))
        await db.commit()

        count_result = await db.execute(
            select(func.count(ParkedIdea.id)).where(
                ParkedIdea.user_id == user.id,
                ParkedIdea.reviewed.is_(False),
            )
        )
        count = count_result.scalar() or 0

        return f"💡 <b>PARKED:</b> {idea}\n[{count} ideas parked]\n\nReview on Sunday. Back to work.", None

    # --- /phone ---
    async def _phone(self, user, db):
        daily = await self._get_or_create_daily(user, db)
        daily.phone_pickups += 1
        await db.commit()

        n = daily.phone_pickups
        if n <= 5:
            status = "✅ On track. Keep it up."
        elif n <= 10:
            status = "⚠️ Getting distracted. Put it in another room."
        else:
            status = "🔴 Phone is winning today. Lock it away for the next block."

        return f"📱 Phone pickup #{n} today\n\n{status}", None

    # --- /1win / /win ---
    async def _daily_win(self, user, db, win):
        if not win:
            return "Usage: /1win [your biggest win today]\nExample: /1win Shipped the API integration", None

        daily = await self._get_or_create_daily(user, db)
        old_win = daily.daily_win
        daily.daily_win = win
        daily.daily_win_set_at = datetime.now(timezone.utc)
        await db.commit()

        if old_win:
            return (
                f"🏆 <b>WIN UPDATED</b> (replacing previous):\n→ {win}\n"
                f"Previous was: {old_win}\n\n"
                f"Now set tomorrow:\n/onething [task]\n/todo [task]",
                None,
            )

        return (
            f"🏆 <b>TODAY'S WIN:</b>\n→ {win}\n\n"
            f"Logged at {datetime.now().strftime('%I:%M %p')}.\n\n"
            f"Now set tomorrow:\n/onething [task]\n/todo [task]",
            None,
        )

    # --- /todo ---
    async def _todo(self, user, db, task):
        if not task:
            return "Usage: /todo [task]\nExample: /todo Review API docs", None

        hour = datetime.now().hour
        target_date = date.today() if hour < 18 else date.today() + timedelta(days=1)

        count_result = await db.execute(
            select(func.count(TodoItem.id)).where(
                TodoItem.user_id == user.id, TodoItem.created_for_date == target_date
            )
        )
        count = count_result.scalar() or 0

        if count >= 7:
            return "Max 7 to-dos per day. You haven't prioritized. Remove one first.", None

        db.add(TodoItem(user_id=user.id, text=task, priority=count, created_for_date=target_date))
        await db.commit()

        # Show full list
        return await self._todolist_for_date(user, db, target_date, "today" if hour < 18 else "tomorrow")

    async def _todone(self, user, db, num_str):
        try:
            num = int(num_str)
        except (ValueError, TypeError):
            return "Usage: /todone [number]\nExample: /todone 2", None

        today = date.today()
        result = await db.execute(
            select(TodoItem).where(
                TodoItem.user_id == user.id, TodoItem.created_for_date == today
            ).order_by(TodoItem.priority)
        )
        todos = result.scalars().all()

        if num < 1 or num > len(todos):
            return f"Invalid number. You have {len(todos)} to-dos.", None

        todo = todos[num - 1]
        todo.completed = True
        todo.completed_at = datetime.now(timezone.utc)
        await db.commit()

        return await self._todolist_for_date(user, db, today, "today")

    async def _todolist(self, user, db):
        return await self._todolist_for_date(user, db, date.today(), "today")

    async def _todolist_for_date(self, user, db, target_date, label):
        result = await db.execute(
            select(TodoItem).where(
                TodoItem.user_id == user.id, TodoItem.created_for_date == target_date
            ).order_by(TodoItem.priority)
        )
        todos = result.scalars().all()

        if not todos:
            return f"📝 No to-dos for {label}. Add with /todo [task]", None

        lines = [f"📝 <b>{label.title()}'s list:</b>"]
        for i, t in enumerate(todos, 1):
            icon = "✅" if t.completed else f"{i}."
            lines.append(f"  {icon} {t.text}")
        lines.append(f"\n/todone [number] to check off.")
        return "\n".join(lines), None

    async def _todoclear(self, user, db):
        tomorrow = date.today() + timedelta(days=1)
        result = await db.execute(
            select(TodoItem).where(
                TodoItem.user_id == user.id, TodoItem.created_for_date == tomorrow
            )
        )
        for todo in result.scalars().all():
            await db.delete(todo)
        await db.commit()
        return "Tomorrow's to-do list cleared.", None

    # --- /tonight ---
    async def _tonight(self, user, db):
        daily = await self._get_or_create_daily(user, db)
        tomorrow = date.today() + timedelta(days=1)

        lines = ["🌙 <b>NIGHT PLANNING STATUS</b>", ""]

        # Win
        if daily.daily_win:
            lines.append(f"✅ 1 Win logged: {daily.daily_win}")
        else:
            lines.append("⬜ No win logged. /1win [description]")

        # Tomorrow's one thing
        tomorrow_result = await db.execute(
            select(DailyFocus).where(DailyFocus.user_id == user.id, DailyFocus.date == tomorrow)
        )
        tomorrow_daily = tomorrow_result.scalar_one_or_none()
        if tomorrow_daily and tomorrow_daily.one_thing:
            lines.append(f"✅ ONE thing set: {tomorrow_daily.one_thing}")
        else:
            lines.append("⬜ No ONE thing for tomorrow. /onething [task]")

        # Tomorrow's todos
        todo_result = await db.execute(
            select(func.count(TodoItem.id)).where(
                TodoItem.user_id == user.id, TodoItem.created_for_date == tomorrow
            )
        )
        todo_count = todo_result.scalar() or 0
        if todo_count > 0:
            lines.append(f"✅ {todo_count} to-dos set for tomorrow")
        else:
            lines.append("⬜ No to-do list. /todo [task]")

        return "\n".join(lines), None

    # --- /tune ---
    async def _tune(self, user, db, request):
        if not request:
            return "Usage: /tune [adjustment request]\nExample: /tune Move morning activation to 7:30 AM", None

        db.add(TuneRequest(user_id=user.id, request_text=request))
        await db.commit()

        count_result = await db.execute(
            select(func.count(TuneRequest.id)).where(
                TuneRequest.user_id == user.id, TuneRequest.status == "pending"
            )
        )
        count = count_result.scalar() or 0

        return (
            f"🔧 <b>TUNE REQUEST LOGGED:</b>\n\"{request}\"\n\n"
            f"This won't change anything today.\n"
            f"Tune requests are reviewed during Sunday weekly review.\n"
            f"[{count}] pending tune requests.",
            None,
        )

    async def _tune_apply(self, user, db, num_str):
        return "Tune apply available during Sunday weekly review. /ideas", None

    async def _tune_reject(self, user, db, num_str):
        return "Tune reject available during Sunday weekly review. /ideas", None

    # --- /ideas ---
    async def _ideas(self, user, db):
        today = date.today()
        if today.weekday() != 6:  # 6 = Sunday
            daily = await self._get_or_create_daily(user, db)
            return (
                f"🚫 Ideas are reviewed on Sundays only.\n"
                f"Today's job is execution, not exploration.\n"
                f"Your ONE thing: {daily.one_thing or 'Not set. /onething [task]'}",
                None,
            )

        result = await db.execute(
            select(ParkedIdea).where(
                ParkedIdea.user_id == user.id, ParkedIdea.reviewed.is_(False)
            ).order_by(ParkedIdea.parked_at)
        )
        ideas = result.scalars().all()

        if not ideas:
            return "No parked ideas to review. Clean week!", None

        lines = [f"💡 <b>PARKED IDEAS REVIEW</b>", ""]
        for i, idea in enumerate(ideas, 1):
            time_str = idea.parked_at.strftime("%a %I:%M %p")
            lines.append(f"{i}. {idea.text} ({time_str})")
        lines.append(f"\nFor each, reply: /idea [number] [pursue/discard/defer]")

        return "\n".join(lines), None

    # --- /status ---
    async def _status(self, user, db):
        daily = await self._get_or_create_daily(user, db)

        # Focus blocks
        blocks_result = await db.execute(
            select(func.count(FocusBlock.id), func.sum(FocusBlock.duration_minutes)).where(
                FocusBlock.user_id == user.id,
                FocusBlock.daily_focus_id == daily.id,
                FocusBlock.completed.is_(True),
            )
        )
        block_count, total_min = blocks_result.one()
        total_min = total_min or 0

        # Parked ideas today
        ideas_result = await db.execute(
            select(func.count(ParkedIdea.id)).where(
                ParkedIdea.user_id == user.id, ParkedIdea.reviewed.is_(False)
            )
        )
        ideas_count = ideas_result.scalar() or 0

        lines = [
            f"📊 <b>TODAY — {date.today().strftime('%B %d, %Y')}</b>",
            "",
        ]

        # Morning
        if daily.ritual_completed_at:
            lines.append(f"⚡ Morning: ✅ Complete ({daily.ritual_completed_at.strftime('%I:%M %p')})")
        else:
            done = sum(1 for f, _ in RITUAL_ITEMS if getattr(daily, f, False))
            lines.append(f"⚡ Morning: {done}/5 — /morning")

        # ONE thing
        if daily.one_thing:
            status = "✅ DONE" if daily.one_thing_done else "IN PROGRESS"
            lines.append(f"🎯 ONE thing: {daily.one_thing} [{status}]")
        else:
            lines.append("🎯 ONE thing: Not set — /onething [task]")

        lines.append(f"⏱ Focus: {block_count or 0}/4 blocks | {total_min // 60}h {total_min % 60}m")
        lines.append(f"💡 Parked: {ideas_count} ideas")
        lines.append(f"📱 Phone: {daily.phone_pickups} pickups")
        lines.append(f"🔥 Streak: {daily.streak_count} days")

        # Glucose if available
        glucose_result = await db.execute(
            select(GlucoseReading)
            .where(GlucoseReading.user_id == user.id)
            .order_by(GlucoseReading.timestamp.desc())
            .limit(1)
        )
        latest = glucose_result.scalar_one_or_none()
        if latest:
            lines.append(f"\n📈 Glucose: {latest.glucose_mmol:.1f} mmol/L ({trend_arrow_to_label(latest.trend_arrow)})")

        return "\n".join(lines), None


focus_agent = FocusAgent()
