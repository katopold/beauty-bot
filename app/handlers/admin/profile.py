from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
from sqlalchemy.ext.asyncio import AsyncSession

from app.callbacks import AdminMenuCallback, AdminProfileEditCallback
from app.filters import IsAdmin
from app.handlers.render import show_text
from app.keyboards.admin import admin_profile_cancel_keyboard, admin_profile_keyboard
from app.models import BusinessProfile
from app.repositories.business_repo import BusinessRepository
from app.states.admin import AdminProfileEdit

router = Router(name="admin_profile")

FIELD_LABELS = {
    "master_name": "Имя мастера",
    "city": "Город",
    "address": "Адрес",
    "about_text": "Текст «О мастере»",
    "map_url": "Ссылка на карту",
}

FIELD_PROMPTS = {
    "master_name": "Введите имя мастера, например: Molly",
    "city": "Введите город, например: Екатеринбург",
    "address": "Введите адрес, например: ул. Примерная, 10",
    "about_text": "Введите текст раздела «О мастере» (можно в несколько строк):",
    "map_url": "Введите ссылку на карту (Яндекс.Карты, Google Maps и т.п.), например: https://yandex.ru/maps/?text=...",
}


def _profile_text(profile: BusinessProfile) -> str:
    def _or_placeholder(value: str) -> str:
        return value if value else "— не заполнено —"

    return (
        "🏢 Данные о мастере\n\n"
        f"Имя мастера:\n{_or_placeholder(profile.master_name)}\n\n"
        f"Город:\n{_or_placeholder(profile.city)}\n\n"
        f"Адрес:\n{_or_placeholder(profile.address)}\n\n"
        f"О мастере:\n{_or_placeholder(profile.about_text)}\n\n"
        f"Ссылка на карту:\n{_or_placeholder(profile.map_url)}"
    )


@router.callback_query(AdminMenuCallback.filter(F.action == "profile"), IsAdmin())
async def cb_admin_profile(callback: CallbackQuery, state: FSMContext, session: AsyncSession) -> None:
    await state.clear()
    profile = await BusinessRepository(session).get_or_create()
    await session.commit()
    await show_text(callback, _profile_text(profile), admin_profile_keyboard(profile))


@router.callback_query(AdminProfileEditCallback.filter(), IsAdmin())
async def cb_admin_profile_edit_field(callback: CallbackQuery, callback_data: AdminProfileEditCallback, state: FSMContext) -> None:
    await state.set_state(AdminProfileEdit.entering_value)
    await state.update_data(field=callback_data.field)
    label = FIELD_LABELS[callback_data.field]
    prompt = FIELD_PROMPTS[callback_data.field]
    await show_text(callback, f"✏️ {label}\n\n{prompt}", admin_profile_cancel_keyboard())


@router.message(AdminProfileEdit.entering_value, IsAdmin())
async def admin_profile_enter_value(message: Message, state: FSMContext, session: AsyncSession) -> None:
    value = (message.text or "").strip()
    if not value:
        await message.answer("Значение не может быть пустым. Введите текст ещё раз:")
        return

    data = await state.get_data()
    field = data["field"]

    repo = BusinessRepository(session)
    profile = await repo.get_or_create()
    setattr(profile, field, value)
    await session.commit()
    await state.clear()

    await message.answer(f"✅ Изменения сохранены.\n\n{_profile_text(profile)}", reply_markup=admin_profile_keyboard(profile))
