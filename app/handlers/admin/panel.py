from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery

from app.callbacks import MenuCallback
from app.filters import IsAdmin
from app.handlers.render import show_text
from app.keyboards.admin import admin_main_keyboard

router = Router(name="admin_panel")

ADMIN_TITLE = "⚙️ Админ-панель"


@router.callback_query(MenuCallback.filter(F.action == "admin"), IsAdmin())
async def cb_admin_panel(callback: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    await show_text(callback, ADMIN_TITLE, admin_main_keyboard())
