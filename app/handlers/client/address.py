from aiogram import F, Router
from aiogram.types import CallbackQuery
from sqlalchemy.ext.asyncio import AsyncSession

from app.callbacks import MenuCallback
from app.handlers.render import show_text
from app.keyboards.client import address_keyboard
from app.repositories.business_repo import BusinessRepository

router = Router(name="client_address")


@router.callback_query(MenuCallback.filter(F.action == "address"))
async def cb_address(callback: CallbackQuery, session: AsyncSession) -> None:
    profile = await BusinessRepository(session).get()
    text = (
        f"📍 Адрес\n\n"
        f"{profile.city}\n"
        f"{profile.address}\n\n"
        f"⏰ Работаем по предварительной записи."
    )
    await show_text(callback, text, address_keyboard(profile.map_url))
