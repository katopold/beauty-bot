from datetime import datetime

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery
from sqlalchemy.ext.asyncio import AsyncSession

from app.callbacks import BackCallback, MenuCallback, MyApptActionCallback
from app.config import settings
from app.handlers.client.booking import show_date_selection
from app.handlers.render import show_text
from app.keyboards.client import (
    after_booking_keyboard,
    cancel_confirm_keyboard,
    my_appointment_keyboard,
    no_active_appointment_keyboard,
)
from app.models import Appointment
from app.repositories.appointment_repo import AppointmentRepository
from app.repositories.business_repo import BusinessRepository
from app.repositories.user_repo import UserRepository
from app.services.booking import cancel_appointment
from app.utils.formatting import format_date_ru, format_price

router = Router(name="client_my_appointment")


def _appointment_text(appointment: Appointment, profile) -> str:
    return (
        "📋 Ваша запись\n\n"
        f"{appointment.service.name}\n\n"
        f"{format_date_ru(appointment.start_at.date())}\n"
        f"{appointment.start_at.strftime('%H:%M')}\n\n"
        f"{format_price(appointment.price_at_booking)}\n\n"
        f"📍 {profile.city}, {profile.address}"
    )


async def _get_active_appointment(session: AsyncSession, telegram_id: int) -> Appointment | None:
    user = await UserRepository(session).get_by_telegram_id(telegram_id)
    if user is None:
        return None
    now = datetime.now(settings.tzinfo)
    return await AppointmentRepository(session).get_nearest_active_for_user(user.id, now)


@router.callback_query(MenuCallback.filter(F.action == "my_appt"))
async def cb_my_appointment(callback: CallbackQuery, session: AsyncSession) -> None:
    appointment = await _get_active_appointment(session, callback.from_user.id)
    if appointment is None:
        text = "У вас пока нет активных записей."
        await show_text(callback, text, no_active_appointment_keyboard())
        return
    profile = await BusinessRepository(session).get()
    await show_text(callback, _appointment_text(appointment, profile), my_appointment_keyboard())


@router.callback_query(MyApptActionCallback.filter(F.action == "cancel"))
async def cb_appt_cancel_ask(callback: CallbackQuery, session: AsyncSession) -> None:
    appointment = await _get_active_appointment(session, callback.from_user.id)
    if appointment is None:
        await callback.answer("Запись не найдена.", show_alert=True)
        return
    profile = await BusinessRepository(session).get()
    text = _appointment_text(appointment, profile) + "\n\nТочно отменить эту запись?"
    await show_text(callback, text, cancel_confirm_keyboard())


@router.callback_query(MyApptActionCallback.filter(F.action == "cancel_confirm"))
async def cb_appt_cancel_confirm(callback: CallbackQuery, session: AsyncSession) -> None:
    appointment = await _get_active_appointment(session, callback.from_user.id)
    if appointment is None:
        await callback.answer("Запись не найдена.", show_alert=True)
        return
    await cancel_appointment(session, appointment)
    text = "❌ Запись отменена.\n\nСлот снова свободен для записи."
    await show_text(callback, text, after_booking_keyboard())


@router.callback_query(MyApptActionCallback.filter(F.action == "cancel_abort"))
async def cb_appt_cancel_abort(callback: CallbackQuery, session: AsyncSession) -> None:
    await cb_my_appointment(callback, session)


@router.callback_query(MyApptActionCallback.filter(F.action == "reschedule"))
async def cb_appt_reschedule_start(callback: CallbackQuery, state: FSMContext, session: AsyncSession) -> None:
    appointment = await _get_active_appointment(session, callback.from_user.id)
    if appointment is None:
        await callback.answer("Запись не найдена.", show_alert=True)
        return
    await state.update_data(mode="reschedule", service_id=appointment.service_id, appointment_id=appointment.id)
    await show_date_selection(callback, state, session)


@router.callback_query(BackCallback.filter(F.to == "my_appt"))
async def cb_back_to_my_appointment(callback: CallbackQuery, session: AsyncSession) -> None:
    await cb_my_appointment(callback, session)
