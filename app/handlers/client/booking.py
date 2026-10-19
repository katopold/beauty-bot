from datetime import date, datetime, time

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery
from sqlalchemy.ext.asyncio import AsyncSession

from app.callbacks import (
    BackCallback,
    CalendarDateCallback,
    CalendarMonthCallback,
    ConfirmCallback,
    NoopCallback,
    ServiceSelectCallback,
    TimeSelectCallback,
)
from app.config import settings
from app.filters import is_admin
from app.handlers.render import show_text
from app.keyboards.client import after_booking_keyboard, calendar_keyboard, confirm_keyboard, main_menu_keyboard, time_selection_keyboard
from app.repositories.appointment_repo import AppointmentRepository
from app.repositories.business_repo import BusinessRepository
from app.repositories.service_repo import ServiceRepository
from app.repositories.user_repo import UserRepository
from app.services.booking import SlotUnavailableError, create_appointment, reschedule_appointment
from app.services.slots import get_available_slots, get_month_availability
from app.utils.formatting import MONTHS_NOMINATIVE, format_date_ru, format_price

router = Router(name="client_booking")


def _month_offset_for(target_date: date, now_local: datetime) -> int:
    return 0 if (target_date.year, target_date.month) == (now_local.year, now_local.month) else 1


def _shift_month(year: int, month: int, offset: int) -> tuple[int, int]:
    if offset <= 0:
        return year, month
    return (year + 1, 1) if month == 12 else (year, month + 1)


async def show_date_selection(
    callback: CallbackQuery, state: FSMContext, session: AsyncSession, month_offset: int = 0, answer: bool = True
) -> None:
    data = await state.get_data()
    back_to = "my_appt" if data.get("mode") == "reschedule" else "services"
    service = await ServiceRepository(session).get(data["service_id"])
    if service is None:
        await callback.answer("Услуга больше недоступна.", show_alert=True)
        return

    month_offset = 1 if month_offset >= 1 else 0
    now_local = datetime.now(settings.tzinfo)
    year, month = _shift_month(now_local.year, now_local.month, month_offset)

    exclude_id = data.get("appointment_id") if data.get("mode") == "reschedule" else None
    availability = await get_month_availability(session, service, year, month, now_local, settings.tzinfo, exclude_appointment_id=exclude_id)

    await state.update_data(month_offset=month_offset)

    text = f"🗓 {MONTHS_NOMINATIVE[month]} {year}\n\nВыберите дату:"
    keyboard = calendar_keyboard(year, month, availability, month_offset, now_local.date(), back_to=back_to)
    await show_text(callback, text, keyboard, answer=answer)


async def show_time_selection(callback: CallbackQuery, state: FSMContext, session: AsyncSession, target_date: date) -> None:
    data = await state.get_data()
    service = await ServiceRepository(session).get(data["service_id"])
    if service is None:
        await callback.answer("Услуга больше недоступна.", show_alert=True)
        return

    now_local = datetime.now(settings.tzinfo)
    exclude_id = data.get("appointment_id") if data.get("mode") == "reschedule" else None
    slots = await get_available_slots(
        session, service, target_date, now_local, settings.tzinfo, exclude_appointment_id=exclude_id
    )

    await state.update_data(date=target_date.isoformat())

    if not slots:
        text = f"На {format_date_ru(target_date)} нет свободных слотов. Выберите другую дату:"
        await callback.answer(text, show_alert=True)
        await show_date_selection(callback, state, session, month_offset=_month_offset_for(target_date, now_local), answer=False)
        return

    text = f"Выберите время на {format_date_ru(target_date)}:"
    await show_text(callback, text, time_selection_keyboard(slots))


async def show_confirmation(callback: CallbackQuery, state: FSMContext, session: AsyncSession) -> None:
    data = await state.get_data()
    service = await ServiceRepository(session).get(data["service_id"])
    target_date = date.fromisoformat(data["date"])
    text = (
        "📋 Проверьте запись\n\n"
        f"Услуга:\n{service.name}\n\n"
        f"Дата:\n{format_date_ru(target_date)}\n\n"
        f"Время:\n{data['time']}\n\n"
        f"Стоимость:\n{format_price(service.price)}\n\n"
        "Всё верно?"
    )
    await show_text(callback, text, confirm_keyboard())


@router.callback_query(ServiceSelectCallback.filter())
async def cb_service_select(callback: CallbackQuery, callback_data: ServiceSelectCallback, state: FSMContext, session: AsyncSession) -> None:
    data = await state.get_data()
    mode = data.get("mode") or "new"
    await state.update_data(mode=mode, service_id=callback_data.service_id)
    await show_date_selection(callback, state, session)


@router.callback_query(CalendarMonthCallback.filter())
async def cb_calendar_month(callback: CallbackQuery, callback_data: CalendarMonthCallback, state: FSMContext, session: AsyncSession) -> None:
    await show_date_selection(callback, state, session, month_offset=callback_data.offset)


@router.callback_query(CalendarDateCallback.filter())
async def cb_calendar_date(callback: CallbackQuery, callback_data: CalendarDateCallback, state: FSMContext, session: AsyncSession) -> None:
    target_date = date(callback_data.year, callback_data.month, callback_data.day)
    await show_time_selection(callback, state, session, target_date)


@router.callback_query(NoopCallback.filter())
async def cb_noop(callback: CallbackQuery) -> None:
    await callback.answer()


@router.callback_query(BackCallback.filter(F.to == "date"))
async def cb_back_to_date(callback: CallbackQuery, state: FSMContext, session: AsyncSession) -> None:
    data = await state.get_data()
    await show_date_selection(callback, state, session, month_offset=data.get("month_offset", 0))


@router.callback_query(TimeSelectCallback.filter())
async def cb_time_select(callback: CallbackQuery, callback_data: TimeSelectCallback, state: FSMContext, session: AsyncSession) -> None:
    hhmm = callback_data.hhmm
    time_str = f"{hhmm[:2]}:{hhmm[2:]}"
    await state.update_data(time=time_str)
    await show_confirmation(callback, state, session)


@router.callback_query(ConfirmCallback.filter(F.action == "back"))
async def cb_confirm_back(callback: CallbackQuery, state: FSMContext, session: AsyncSession) -> None:
    data = await state.get_data()
    target_date = date.fromisoformat(data["date"])
    await show_time_selection(callback, state, session, target_date)


@router.callback_query(ConfirmCallback.filter(F.action == "cancel"))
async def cb_confirm_cancel(callback: CallbackQuery, state: FSMContext) -> None:
    from app.handlers.client.start import GREETING

    await state.clear()
    text = "Запись отменена.\n\n" + GREETING
    await show_text(callback, text, main_menu_keyboard(is_admin(callback.from_user.id)))


@router.callback_query(ConfirmCallback.filter(F.action == "confirm"))
async def cb_confirm(callback: CallbackQuery, state: FSMContext, session: AsyncSession) -> None:
    data = await state.get_data()
    service = await ServiceRepository(session).get(data["service_id"])
    target_date = date.fromisoformat(data["date"])
    hour, minute = map(int, data["time"].split(":"))
    start_at = datetime.combine(target_date, time(hour=hour, minute=minute), tzinfo=settings.tzinfo)

    user = await UserRepository(session).get_or_create(
        callback.from_user.id, callback.from_user.username, callback.from_user.full_name
    )

    mode = data.get("mode", "new")
    try:
        if mode == "reschedule":
            appointment = await AppointmentRepository(session).get(data["appointment_id"])
            if appointment is None:
                await callback.answer("Запись не найдена.", show_alert=True)
                return
            await reschedule_appointment(session, appointment, start_at, service.duration_minutes)
            verb_text = "🔄 Запись перенесена!"
        else:
            await create_appointment(session, user, service, start_at)
            verb_text = "✅ Вы записаны!"
    except SlotUnavailableError:
        await callback.answer("Увы, этот слот только что заняли. Выберите другое время.", show_alert=True)
        await show_time_selection(callback, state, session, target_date)
        return

    profile = await BusinessRepository(session).get()
    text = (
        f"{verb_text}\n\n"
        f"{service.name}\n"
        f"{format_date_ru(target_date)} в {data['time']}\n\n"
        f"Стоимость: {format_price(service.price)}\n\n"
        f"📍 {profile.city}, {profile.address}\n\n"
        "Мы напомним вам о визите заранее."
    )
    await state.clear()
    await show_text(callback, text, after_booking_keyboard())
