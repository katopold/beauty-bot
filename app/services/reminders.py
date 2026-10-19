from datetime import datetime, timedelta

from aiogram import Bot
from aiogram.exceptions import TelegramAPIError

from app.config import settings
from app.repositories.appointment_repo import AppointmentRepository
from app.repositories.business_repo import BusinessRepository
from app.utils.formatting import format_time


def build_reminder_24h_text(service_name: str, time_str: str, address: str) -> str:
    return "🔔 Напоминание о записи\n\n" f"Завтра у вас:\n\n" f"{service_name}\n" f"{time_str}\n\n" f"📍 {address}\n\n" "Ждём вас!"


def build_reminder_2h_text(service_name: str, time_str: str) -> str:
    lowered = service_name[0].lower() + service_name[1:] if service_name else service_name
    return f"🔔 Напоминание\n\nСегодня в {time_str} у вас запись на {lowered}.\n\nДо встречи!"


async def _safe_send(bot: Bot, chat_id: int, text: str) -> None:
    try:
        await bot.send_message(chat_id, text)
    except TelegramAPIError:
        pass  # демо: получатель мог заблокировать бота — не роняем джобу


async def send_due_reminders(bot: Bot, session_maker) -> None:
    """Периодическая проверка: кому пора отправить напоминание за 24ч / за 2ч."""
    now = datetime.now(settings.tzinfo)
    async with session_maker() as session:
        repo = AppointmentRepository(session)
        profile = await BusinessRepository(session).get()
        address = f"{profile.city}, {profile.address}" if profile else ""

        due_24h = await repo.list_needing_reminder(now, now, now + timedelta(hours=24), "reminder_24h_sent")
        for appt in due_24h:
            text = build_reminder_24h_text(appt.service.name, format_time(appt.start_at), address)
            await _safe_send(bot, appt.user.telegram_id, text)
            appt.reminder_24h_sent = True

        due_2h = await repo.list_needing_reminder(now, now, now + timedelta(hours=2), "reminder_2h_sent")
        for appt in due_2h:
            text = build_reminder_2h_text(appt.service.name, format_time(appt.start_at))
            await _safe_send(bot, appt.user.telegram_id, text)
            appt.reminder_2h_sent = True

        await session.commit()
