from aiogram import F, Router
from aiogram.types import CallbackQuery

from app.callbacks import AdminMenuCallback
from app.filters import IsAdmin
from app.services.reminders import build_reminder_24h_text, build_reminder_2h_text

router = Router(name="admin_reminders")


@router.callback_query(AdminMenuCallback.filter(F.action == "test_reminder"), IsAdmin())
async def cb_admin_test_reminder(callback: CallbackQuery) -> None:
    text_24h = build_reminder_24h_text("Классическое наращивание", "15:00", "Екатеринбург, ул. Примерная, 10")
    text_2h = build_reminder_2h_text("Классическое наращивание", "15:00")

    await callback.message.answer("🧪 Пример напоминания за 24 часа:")
    await callback.message.answer(text_24h)
    await callback.message.answer("🧪 Пример напоминания за 2 часа:")
    await callback.message.answer(text_2h)
    await callback.answer("Тестовые напоминания отправлены.")
