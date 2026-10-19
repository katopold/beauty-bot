from aiogram import Bot
from apscheduler.schedulers.asyncio import AsyncIOScheduler

from app.config import settings
from app.database import async_session_maker
from app.services.reminders import send_due_reminders

REMINDER_CHECK_INTERVAL_MINUTES = 5


def setup_scheduler(bot: Bot) -> AsyncIOScheduler:
    scheduler = AsyncIOScheduler(timezone=settings.tzinfo)
    scheduler.add_job(
        send_due_reminders,
        trigger="interval",
        minutes=REMINDER_CHECK_INTERVAL_MINUTES,
        args=[bot, async_session_maker],
        id="send_due_reminders",
        replace_existing=True,
    )
    return scheduler
