from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
from sqlalchemy.ext.asyncio import AsyncSession

from app.callbacks import AdminMenuCallback, AdminServiceCallback, AdminServiceEditCallback
from app.filters import IsAdmin
from app.handlers.render import show_text
from app.keyboards.admin import (
    admin_cancel_input_keyboard,
    admin_service_delete_confirm_keyboard,
    admin_service_detail_keyboard,
    admin_services_list_keyboard,
)
from app.models import Service
from app.repositories.appointment_repo import AppointmentRepository
from app.repositories.service_repo import ServiceRepository
from app.states.admin import AdminServiceCreate, AdminServiceEdit
from app.utils.formatting import format_duration, format_price

router = Router(name="admin_services")

FIELD_PROMPTS = {
    "name": "Введите новое название услуги:",
    "description": "Введите новое описание услуги:",
    "price": "Введите новую цену в рублях (только число), например: 2500",
    "duration": "Введите новую длительность в минутах (только число), например: 120",
}


def _service_detail_text(service: Service) -> str:
    status = "Активна ✅" if service.is_active else "Отключена 🚫"
    description = service.description or "—"
    return (
        f"{service.name}\n\n"
        f"{description}\n\n"
        f"Цена: {format_price(service.price)}\n"
        f"Длительность: {format_duration(service.duration_minutes)}\n"
        f"Статус: {status}"
    )


async def _render_services_list(target, session: AsyncSession) -> None:
    services = await ServiceRepository(session).list_all()
    text = "💫 Услуги\n\nВыберите услугу для редактирования:" if services else "💫 Услуги\n\nПока не добавлено ни одной услуги."
    keyboard = admin_services_list_keyboard(services)
    if isinstance(target, CallbackQuery):
        await show_text(target, text, keyboard)
    else:
        await target.answer(text, reply_markup=keyboard)


@router.callback_query(AdminMenuCallback.filter(F.action == "services"), IsAdmin())
async def cb_admin_services_list(callback: CallbackQuery, state: FSMContext, session: AsyncSession) -> None:
    await state.clear()
    await _render_services_list(callback, session)


@router.callback_query(AdminServiceCallback.filter(), IsAdmin())
async def cb_admin_service_detail(callback: CallbackQuery, callback_data: AdminServiceCallback, session: AsyncSession) -> None:
    service = await ServiceRepository(session).get(callback_data.service_id)
    if service is None:
        await callback.answer("Услуга не найдена.", show_alert=True)
        return
    await show_text(callback, _service_detail_text(service), admin_service_detail_keyboard(service))


# --- Добавление новой услуги ---


@router.callback_query(AdminMenuCallback.filter(F.action == "service_add"), IsAdmin())
async def cb_admin_service_add_start(callback: CallbackQuery, state: FSMContext) -> None:
    await state.set_state(AdminServiceCreate.entering_name)
    await show_text(callback, "➕ Новая услуга\n\nВведите название услуги:", admin_cancel_input_keyboard())


@router.message(AdminServiceCreate.entering_name, IsAdmin())
async def admin_service_add_name(message: Message, state: FSMContext) -> None:
    name = message.text.strip()
    if not name:
        await message.answer("Название не может быть пустым. Введите название услуги:")
        return
    await state.update_data(name=name)
    await state.set_state(AdminServiceCreate.entering_description)
    await message.answer("Введите описание услуги (или «-», чтобы оставить пустым):")


@router.message(AdminServiceCreate.entering_description, IsAdmin())
async def admin_service_add_description(message: Message, state: FSMContext) -> None:
    text = message.text.strip()
    description = "" if text == "-" else text
    await state.update_data(description=description)
    await state.set_state(AdminServiceCreate.entering_price)
    await message.answer("Введите цену в рублях (только число), например: 2500")


@router.message(AdminServiceCreate.entering_price, IsAdmin())
async def admin_service_add_price(message: Message, state: FSMContext) -> None:
    try:
        price = int(message.text.strip())
        if price <= 0:
            raise ValueError
    except ValueError:
        await message.answer("Введите цену числом, например: 2500")
        return
    await state.update_data(price=price)
    await state.set_state(AdminServiceCreate.entering_duration)
    await message.answer("Введите длительность услуги в минутах (только число), например: 120")


@router.message(AdminServiceCreate.entering_duration, IsAdmin())
async def admin_service_add_duration(message: Message, state: FSMContext, session: AsyncSession) -> None:
    try:
        duration = int(message.text.strip())
        if duration <= 0:
            raise ValueError
    except ValueError:
        await message.answer("Введите длительность числом (в минутах), например: 120")
        return

    data = await state.get_data()
    service = await ServiceRepository(session).create(
        name=data["name"], description=data.get("description", ""), price=data["price"], duration_minutes=duration
    )
    await session.commit()
    await state.clear()
    await message.answer(f"✅ Услуга добавлена.\n\n{_service_detail_text(service)}", reply_markup=admin_service_detail_keyboard(service))


# --- Редактирование поля услуги ---


@router.callback_query(AdminServiceEditCallback.filter(F.field.in_({"name", "description", "price", "duration"})), IsAdmin())
async def cb_admin_service_edit_field(callback: CallbackQuery, callback_data: AdminServiceEditCallback, state: FSMContext) -> None:
    await state.set_state(AdminServiceEdit.entering_value)
    await state.update_data(service_id=callback_data.service_id, field=callback_data.field)
    await show_text(callback, FIELD_PROMPTS[callback_data.field], admin_cancel_input_keyboard())


@router.message(AdminServiceEdit.entering_value, IsAdmin())
async def admin_service_edit_value(message: Message, state: FSMContext, session: AsyncSession) -> None:
    data = await state.get_data()
    service = await ServiceRepository(session).get(data["service_id"])
    if service is None:
        await state.clear()
        await message.answer("Услуга больше не существует.")
        return

    field = data["field"]
    raw = message.text.strip()

    if field == "name":
        if not raw:
            await message.answer("Название не может быть пустым. Введите название услуги:")
            return
        service.name = raw
    elif field == "description":
        service.description = "" if raw == "-" else raw
    elif field == "price":
        try:
            price = int(raw)
            if price <= 0:
                raise ValueError
        except ValueError:
            await message.answer("Введите цену числом, например: 2500")
            return
        service.price = price
    elif field == "duration":
        try:
            duration = int(raw)
            if duration <= 0:
                raise ValueError
        except ValueError:
            await message.answer("Введите длительность числом (в минутах), например: 120")
            return
        service.duration_minutes = duration

    await session.commit()
    await state.clear()
    await message.answer(f"✅ Изменения сохранены.\n\n{_service_detail_text(service)}", reply_markup=admin_service_detail_keyboard(service))


# --- Включение/отключение и удаление ---


@router.callback_query(AdminServiceEditCallback.filter(F.field == "toggle"), IsAdmin())
async def cb_admin_service_toggle(callback: CallbackQuery, callback_data: AdminServiceEditCallback, session: AsyncSession) -> None:
    service = await ServiceRepository(session).get(callback_data.service_id)
    if service is None:
        await callback.answer("Услуга не найдена.", show_alert=True)
        return
    service.is_active = not service.is_active
    await session.commit()
    await show_text(callback, _service_detail_text(service), admin_service_detail_keyboard(service))


@router.callback_query(AdminServiceEditCallback.filter(F.field == "delete"), IsAdmin())
async def cb_admin_service_delete_ask(callback: CallbackQuery, callback_data: AdminServiceEditCallback, session: AsyncSession) -> None:
    service = await ServiceRepository(session).get(callback_data.service_id)
    if service is None:
        await callback.answer("Услуга не найдена.", show_alert=True)
        return
    if await AppointmentRepository(session).exists_for_service(service.id):
        await callback.answer(
            "У этой услуги уже есть записи, удалить её нельзя. Вместо этого отключите её (🚫 Отключить).",
            show_alert=True,
        )
        return
    text = f"Удалить услугу «{service.name}»?\nЭто действие необратимо."
    await show_text(callback, text, admin_service_delete_confirm_keyboard(service.id))


@router.callback_query(AdminServiceEditCallback.filter(F.field == "delete_confirm"), IsAdmin())
async def cb_admin_service_delete_confirm(callback: CallbackQuery, callback_data: AdminServiceEditCallback, session: AsyncSession) -> None:
    service = await ServiceRepository(session).get(callback_data.service_id)
    if service is not None:
        await ServiceRepository(session).delete(service)
        await session.commit()
    await callback.answer("Услуга удалена.")
    await _render_services_list(callback, session)
