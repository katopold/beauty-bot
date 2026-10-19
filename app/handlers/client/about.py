from aiogram import F, Router
from aiogram.types import CallbackQuery
from sqlalchemy.ext.asyncio import AsyncSession

from app.callbacks import MenuCallback
from app.handlers.render import show_text
from app.keyboards.client import simple_back_keyboard
from app.repositories.business_repo import BusinessRepository

router = Router(name="client_about")


@router.callback_query(MenuCallback.filter(F.action == "about"))
async def cb_about(callback: CallbackQuery, session: AsyncSession) -> None:
    profile = await BusinessRepository(session).get()
    text = f"ℹ️ О мастере\n\n{profile.about_text}"
    await show_text(callback, text, simple_back_keyboard())
