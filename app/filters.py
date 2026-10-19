from aiogram.filters import BaseFilter
from aiogram.types import CallbackQuery, Message

from app.config import settings


def is_admin(telegram_id: int) -> bool:
    return telegram_id in settings.admin_ids


class IsAdmin(BaseFilter):
    async def __call__(self, event: Message | CallbackQuery) -> bool:
        return is_admin(event.from_user.id)
