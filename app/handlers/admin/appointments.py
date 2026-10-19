from calendar import monthrange
from datetime import date, datetime, time, timedelta

from aiogram import F, Router
from aiogram.types import CallbackQuery
from sqlalchemy.ext.asyncio import AsyncSession

from app.callbacks import (
    AdminApptCallback,
    AdminApptCancelCallback,
    AdminApptListCallback,
    AdminCalendarMonthCallback,
    AdminDayAppointmentsCallback,
    AdminMenuCallback,
)
from app.config import settings
from app.filters import IsAdmin
from app.handlers.render import show_text
from app.keyboards.admin import (
    admin_appt_cancel_confirm_keyboard,
    admin_appt_detail_keyboard,
    admin_appts_list_keyboard,
    admin_appts_menu_keyboard,
    admin_calendar_keyboard,
    admin_day_appointments_keyboard,
)
from app.repositories.appointment_repo import AppointmentRepository
from app.services.booking import cancel_appointment
from app.services.slots import get_month_day_off_map
from app.utils.formatting import MONTHS_NOMINATIVE, format_date_ru, format_price

router = Router(name="admin_appointments")


def _day_bounds(day: date) -> tuple[datetime, datetime]:
    start = datetime.combine(day, time.min, tzinfo=settings.tzinfo)
    return start, start + timedelta(days=1)


def _parse_day_scope(scope: str) -> date | None:
    """scope вида 'day2026-08-28' -> date(2026,8,28); для 'upcoming' -> None."""
    if not scope.startswith("day"):
        return None
    return date.fromisoformat(scope[len("day") :])


async def _render_scope_list(callback: CallbackQuery, session: AsyncSession, scope: str) -> None:
    now = datetime.now(settings.tzinfo)
    appointments = await AppointmentRepository(session).list_upcoming(now, limit=15)

    if not appointments:
        text = "📅 Ближайшие записи\n\nЗаписей нет."
    else:
        lines = [
            f"{format_date_ru(appt.start_at.date())} {appt.start_at.strftime('%H:%M')} — "
            f"{appt.user.full_name} — {appt.service.name}"
            for appt in appointments
        ]
        text = "📅 Ближайшие записи\n\n" + "\n".join(lines)

    await show_text(callback, text, admin_appts_list_keyboard(appointments, scope))


async def _render_day_appointments(callback: CallbackQuery, session: AsyncSession, target_date: date) -> None:
    start, end = _day_bounds(target_date)
    appointments = await AppointmentRepository(session).list_for_day(start, end)

    title = f"📅 {format_date_ru(target_date)}"
    if not appointments:
        text = f"{title}\n\nЗаписей нет."
    else:
        lines = [f"{a.start_at.strftime('%H:%M')} — {a.user.full_name} — {a.service.name}" for a in appointments]
        text = f"{title}\n\n" + "\n".join(lines)

    await show_text(callback, text, admin_day_appointments_keyboard(appointments, target_date))


async def _render_list_for_scope(callback: CallbackQuery, session: AsyncSession, scope: str) -> None:
    day = _parse_day_scope(scope)
    if day is not None:
        await _render_day_appointments(callback, session, day)
    else:
        await _render_scope_list(callback, session, scope)


@router.callback_query(AdminMenuCallback.filter(F.action == "appts"), IsAdmin())
async def cb_admin_appts_menu(callback: CallbackQuery) -> None:
    await show_text(callback, "📅 Записи\n\nВыберите период:", admin_appts_menu_keyboard())


@router.callback_query(AdminApptListCallback.filter(), IsAdmin())
async def cb_admin_appts_list(callback: CallbackQuery, callback_data: AdminApptListCallback, session: AsyncSession) -> None:
    await _render_scope_list(callback, session, callback_data.scope)


@router.callback_query(AdminApptCallback.filter(), IsAdmin())
async def cb_admin_appt_detail(callback: CallbackQuery, callback_data: AdminApptCallback, session: AsyncSession) -> None:
    appointment = await AppointmentRepository(session).get(callback_data.appointment_id)
    if appointment is None:
        await callback.answer("Запись не найдена.", show_alert=True)
        return

    status_ru = "Подтверждена" if appointment.status.value == "confirmed" else "Отменена"
    username = f"@{appointment.user.username}" if appointment.user.username else "нет"
    phone = appointment.user.phone or "не указан"
    text = (
        f"Клиент:\n{appointment.user.full_name}\n\n"
        f"Username:\n{username}\n\n"
        f"Телефон:\n{phone}\n\n"
        f"Услуга:\n{appointment.service.name}\n\n"
        f"Дата:\n{format_date_ru(appointment.start_at.date())}\n\n"
        f"Время:\n{appointment.start_at.strftime('%H:%M')}\n\n"
        f"Стоимость:\n{format_price(appointment.price_at_booking)}\n\n"
        f"Статус:\n{status_ru}"
    )
    await show_text(callback, text, admin_appt_detail_keyboard(appointment, callback_data.scope))


@router.callback_query(AdminApptCancelCallback.filter(F.action == "ask"), IsAdmin())
async def cb_admin_appt_cancel_ask(callback: CallbackQuery, callback_data: AdminApptCancelCallback, session: AsyncSession) -> None:
    appointment = await AppointmentRepository(session).get(callback_data.appointment_id)
    if appointment is None:
        await callback.answer("Запись не найдена.", show_alert=True)
        return
    text = (
        "🗑 Удалить запись?\n\n"
        f"{appointment.user.full_name} — {appointment.service.name}\n"
        f"{format_date_ru(appointment.start_at.date())} {appointment.start_at.strftime('%H:%M')}\n\n"
        "Слот освободится для новых записей. Клиента об отмене нужно предупредить самостоятельно — "
        "бот не уведомляет его автоматически."
    )
    await show_text(callback, text, admin_appt_cancel_confirm_keyboard(appointment.id, callback_data.scope))


@router.callback_query(AdminApptCancelCallback.filter(F.action == "confirm"), IsAdmin())
async def cb_admin_appt_cancel_confirm(callback: CallbackQuery, callback_data: AdminApptCancelCallback, session: AsyncSession) -> None:
    appointment = await AppointmentRepository(session).get(callback_data.appointment_id)
    if appointment is None:
        await callback.answer("Запись не найдена.", show_alert=True)
        return
    await cancel_appointment(session, appointment)
    await callback.answer("Запись удалена, слот снова свободен.")
    await _render_list_for_scope(callback, session, callback_data.scope)


async def _month_appointment_counts(session: AsyncSession, year: int, month: int) -> dict[date, int]:
    first_day = date(year, month, 1)
    last_day = date(year, month, monthrange(year, month)[1])
    month_start = datetime.combine(first_day, time.min, tzinfo=settings.tzinfo)
    month_end = datetime.combine(last_day, time.min, tzinfo=settings.tzinfo) + timedelta(days=1)
    appointments = await AppointmentRepository(session).list_confirmed_in_range(month_start, month_end)

    counts: dict[date, int] = {}
    for appt in appointments:
        local_date = appt.start_at.astimezone(settings.tzinfo).date()
        counts[local_date] = counts.get(local_date, 0) + 1
    return counts


async def _render_admin_calendar(callback: CallbackQuery, session: AsyncSession, year: int, month: int) -> None:
    day_off_map = await get_month_day_off_map(session, year, month)
    counts = await _month_appointment_counts(session, year, month)
    text = f"🗓 {MONTHS_NOMINATIVE[month]} {year}\n\nВыберите дату, чтобы посмотреть записи:"
    await show_text(callback, text, admin_calendar_keyboard(year, month, day_off_map, counts))


@router.callback_query(AdminMenuCallback.filter(F.action == "appts_calendar"), IsAdmin())
async def cb_admin_appts_calendar_start(callback: CallbackQuery, session: AsyncSession) -> None:
    now = datetime.now(settings.tzinfo)
    await _render_admin_calendar(callback, session, now.year, now.month)


@router.callback_query(AdminCalendarMonthCallback.filter(), IsAdmin())
async def cb_admin_calendar_month(callback: CallbackQuery, callback_data: AdminCalendarMonthCallback, session: AsyncSession) -> None:
    await _render_admin_calendar(callback, session, callback_data.year, callback_data.month)


@router.callback_query(AdminDayAppointmentsCallback.filter(), IsAdmin())
async def cb_admin_day_appointments(callback: CallbackQuery, callback_data: AdminDayAppointmentsCallback, session: AsyncSession) -> None:
    target_date = date(callback_data.year, callback_data.month, callback_data.day)
    await _render_day_appointments(callback, session, target_date)
