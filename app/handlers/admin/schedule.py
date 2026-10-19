"""Управление графиком: недельное расписание + разовые особые дни (праздники и т.п.).

Ключевое правило (обсуждено и согласовано с владельцем бота): изменение графика
НИКОГДА не отменяет существующие подтверждённые записи автоматически. Если
новое расписание конфликтует с уже забронированным временем, бот показывает
список затронутых записей и просит администратора явно подтвердить сохранение
(запись при этом остаётся активной — отменить/перенести её можно вручную через
«📅 Записи»).
"""

from datetime import date, datetime, time

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
from sqlalchemy.ext.asyncio import AsyncSession

from app.callbacks import (
    AdminExceptionDeleteCallback,
    AdminExceptionKindCallback,
    AdminMenuCallback,
    AdminScheduleActionCallback,
    AdminScheduleWeekdayCallback,
)
from app.config import settings
from app.filters import IsAdmin
from app.handlers.render import show_text
from app.keyboards.admin import (
    admin_exception_cancel_keyboard,
    admin_exception_kind_keyboard,
    admin_exceptions_list_keyboard,
    admin_schedule_cancel_keyboard,
    admin_schedule_conflict_keyboard,
    admin_schedule_hub_keyboard,
    admin_schedule_weekday_detail_keyboard,
    admin_schedule_weekday_list_keyboard,
)
from app.models import Appointment, WorkingSchedule
from app.repositories.schedule_repo import ScheduleRepository
from app.services.schedule_conflicts import find_date_conflicts, find_weekday_conflicts
from app.services.slots import WorkWindow
from app.states.admin import AdminExceptionCreate, AdminScheduleTimeInput
from app.utils.formatting import WEEKDAY_NAMES, format_date_ru

router = Router(name="admin_schedule")


def _parse_time(text: str | None) -> time | None:
    if not text:
        return None
    try:
        return datetime.strptime(text.strip(), "%H:%M").time()
    except ValueError:
        return None


def _parse_date(text: str | None) -> date | None:
    if not text:
        return None
    try:
        return datetime.strptime(text.strip(), "%d.%m.%Y").date()
    except ValueError:
        return None


async def _respond(target: CallbackQuery | Message, text: str, keyboard) -> None:
    if isinstance(target, CallbackQuery):
        await show_text(target, text, keyboard)
    else:
        await target.answer(text, reply_markup=keyboard)


def _weekday_detail_text(ws: WorkingSchedule) -> str:
    name = WEEKDAY_NAMES[ws.weekday]
    if ws.is_day_off:
        return f"{name}\n\nВыходной день."
    lines = [name, "", f"Часы работы: {ws.start_time.strftime('%H:%M')}–{ws.end_time.strftime('%H:%M')}"]
    if ws.break_start and ws.break_end:
        lines.append(f"Перерыв: {ws.break_start.strftime('%H:%M')}–{ws.break_end.strftime('%H:%M')}")
    else:
        lines.append("Перерыв: нет")
    return "\n".join(lines)


def _conflict_text(conflicts: list[Appointment], description: str) -> str:
    lines = [f"⚠️ {description}", "", "На это время уже есть подтверждённые записи:"]
    for appt in conflicts:
        local = appt.start_at.astimezone(settings.tzinfo)
        lines.append(f"• {format_date_ru(local.date())} {local.strftime('%H:%M')} — {appt.user.full_name} — {appt.service.name}")
    lines.append("")
    lines.append(
        "Эти записи не будут отменены автоматически — при необходимости "
        "отмените или перенесите их вручную через «📅 Записи»."
    )
    lines.append("Сохранить изменение графика всё равно?")
    return "\n".join(lines)


async def _apply_pending_change(session: AsyncSession, pending: dict) -> str:
    schedule_repo = ScheduleRepository(session)
    kind = pending["kind"]

    if kind == "weekday_toggle_off":
        ws = await schedule_repo.get_for_weekday(pending["weekday"])
        ws.is_day_off = not ws.is_day_off
        if not ws.is_day_off and ws.start_time is None:
            ws.start_time, ws.end_time = time(10, 0), time(19, 0)
        await session.commit()
        return "Теперь выходной." if ws.is_day_off else "Теперь рабочий день."

    if kind == "weekday_hours":
        ws = await schedule_repo.get_for_weekday(pending["weekday"])
        ws.is_day_off = False
        ws.start_time = time.fromisoformat(pending["start"])
        ws.end_time = time.fromisoformat(pending["end"])
        if ws.break_start and not (ws.start_time <= ws.break_start and ws.break_end <= ws.end_time):
            ws.break_start = None
            ws.break_end = None
        await session.commit()
        return "Часы работы обновлены."

    if kind == "weekday_break":
        ws = await schedule_repo.get_for_weekday(pending["weekday"])
        ws.break_start = time.fromisoformat(pending["start"])
        ws.break_end = time.fromisoformat(pending["end"])
        await session.commit()
        return "Перерыв обновлён."

    if kind == "weekday_break_remove":
        ws = await schedule_repo.get_for_weekday(pending["weekday"])
        ws.break_start = None
        ws.break_end = None
        await session.commit()
        return "Перерыв убран."

    if kind == "exception_add":
        day = date.fromisoformat(pending["date"])
        start = time.fromisoformat(pending["start"]) if pending.get("start") else None
        end = time.fromisoformat(pending["end"]) if pending.get("end") else None
        await schedule_repo.upsert_exception(day, pending["is_day_off"], start, end)
        await session.commit()
        return "Особый день сохранён."

    raise ValueError(f"Неизвестный тип изменения графика: {kind}")


async def _after_apply(target: CallbackQuery | Message, session: AsyncSession, pending: dict, result_text: str) -> None:
    if pending["kind"] == "exception_add":
        exceptions = await ScheduleRepository(session).list_exceptions(from_date=datetime.now(settings.tzinfo).date())
        await _respond(target, f"✅ {result_text}", admin_exceptions_list_keyboard(exceptions))
        return
    ws = await ScheduleRepository(session).get_for_weekday(pending["weekday"])
    await _respond(target, f"✅ {result_text}\n\n{_weekday_detail_text(ws)}", admin_schedule_weekday_detail_keyboard(ws))


async def _finalize(
    target: CallbackQuery | Message,
    state: FSMContext,
    session: AsyncSession,
    pending: dict,
    conflicts: list[Appointment],
    description: str,
) -> None:
    if not conflicts:
        result_text = await _apply_pending_change(session, pending)
        await _after_apply(target, session, pending, result_text)
        return
    await state.update_data(pending_schedule_change=pending)
    await _respond(target, _conflict_text(conflicts, description), admin_schedule_conflict_keyboard())


async def _render_hub(target: CallbackQuery | Message, session: AsyncSession) -> None:
    week = await ScheduleRepository(session).get_week()
    by_weekday = {w.weekday: w for w in week}
    lines = ["🕐 Расписание работы\n"]
    for weekday in range(7):
        ws = by_weekday.get(weekday)
        name = WEEKDAY_NAMES[weekday]
        if ws is None or ws.is_day_off:
            lines.append(f"{name}: выходной")
            continue
        line = f"{name}: {ws.start_time.strftime('%H:%M')}–{ws.end_time.strftime('%H:%M')}"
        if ws.break_start and ws.break_end:
            line += f" (перерыв {ws.break_start.strftime('%H:%M')}–{ws.break_end.strftime('%H:%M')})"
        lines.append(line)
    await _respond(target, "\n".join(lines), admin_schedule_hub_keyboard())


# --- Хаб и просмотр/редактирование недельного графика ---


@router.callback_query(AdminMenuCallback.filter(F.action == "schedule"), IsAdmin())
async def cb_admin_schedule(callback: CallbackQuery, state: FSMContext, session: AsyncSession) -> None:
    await state.clear()
    await _render_hub(callback, session)


@router.callback_query(AdminMenuCallback.filter(F.action == "schedule_edit"), IsAdmin())
async def cb_admin_schedule_edit_list(callback: CallbackQuery, session: AsyncSession) -> None:
    week = await ScheduleRepository(session).get_week()
    await show_text(callback, "✏️ Изменить график\n\nВыберите день недели:", admin_schedule_weekday_list_keyboard(week))


@router.callback_query(AdminScheduleWeekdayCallback.filter(), IsAdmin())
async def cb_admin_schedule_weekday_detail(
    callback: CallbackQuery, callback_data: AdminScheduleWeekdayCallback, session: AsyncSession
) -> None:
    ws = await ScheduleRepository(session).get_for_weekday(callback_data.weekday)
    await show_text(callback, _weekday_detail_text(ws), admin_schedule_weekday_detail_keyboard(ws))


@router.callback_query(AdminScheduleActionCallback.filter(), IsAdmin())
async def cb_admin_schedule_action(
    callback: CallbackQuery, callback_data: AdminScheduleActionCallback, state: FSMContext, session: AsyncSession
) -> None:
    weekday = callback_data.weekday
    action = callback_data.action
    ws = await ScheduleRepository(session).get_for_weekday(weekday)

    if action == "toggle":
        pending = {"kind": "weekday_toggle_off", "weekday": weekday}
        if ws.is_day_off:
            await _finalize(callback, state, session, pending, [], f"{WEEKDAY_NAMES[weekday]} снова станет рабочим днём.")
        else:
            conflicts = await find_weekday_conflicts(session, weekday, None)
            await _finalize(callback, state, session, pending, conflicts, f"{WEEKDAY_NAMES[weekday]} станет выходным.")
        return

    if action == "remove_break":
        pending = {"kind": "weekday_break_remove", "weekday": weekday}
        await _finalize(callback, state, session, pending, [], "")
        return

    if action == "edit_hours":
        await state.set_state(AdminScheduleTimeInput.entering_start)
        await state.update_data(weekday=weekday, mode="hours")
        await show_text(
            callback,
            f"⏰ {WEEKDAY_NAMES[weekday]}\n\nВведите время начала работы, например 10:00:",
            admin_schedule_cancel_keyboard(weekday),
        )
        return

    if action == "edit_break":
        if ws.is_day_off:
            await callback.answer("Сначала сделайте день рабочим.", show_alert=True)
            return
        await state.set_state(AdminScheduleTimeInput.entering_start)
        await state.update_data(weekday=weekday, mode="break")
        await show_text(
            callback,
            f"☕ {WEEKDAY_NAMES[weekday]}\n\nВведите время начала перерыва, например 14:00:",
            admin_schedule_cancel_keyboard(weekday),
        )
        return


@router.message(AdminScheduleTimeInput.entering_start, IsAdmin())
async def admin_schedule_time_start(message: Message, state: FSMContext) -> None:
    value = _parse_time(message.text)
    if value is None:
        await message.answer("Введите время в формате ЧЧ:ММ, например 10:00")
        return
    await state.update_data(start=value.strftime("%H:%M"))
    await state.set_state(AdminScheduleTimeInput.entering_end)
    data = await state.get_data()
    prompt = (
        "Введите время окончания перерыва, например 15:00:"
        if data.get("mode") == "break"
        else "Введите время окончания работы, например 19:00:"
    )
    await message.answer(prompt)


@router.message(AdminScheduleTimeInput.entering_end, IsAdmin())
async def admin_schedule_time_end(message: Message, state: FSMContext, session: AsyncSession) -> None:
    end_value = _parse_time(message.text)
    if end_value is None:
        await message.answer("Введите время в формате ЧЧ:ММ, например 19:00")
        return

    data = await state.get_data()
    weekday = data["weekday"]
    mode = data["mode"]
    start_value = time.fromisoformat(data["start"])

    if end_value <= start_value:
        await message.answer("Время окончания должно быть позже времени начала. Введите время окончания ещё раз:")
        return

    ws = await ScheduleRepository(session).get_for_weekday(weekday)

    if mode == "hours":
        pending = {
            "kind": "weekday_hours",
            "weekday": weekday,
            "start": start_value.strftime("%H:%M"),
            "end": end_value.strftime("%H:%M"),
        }
        window = WorkWindow(start=start_value, end=end_value, break_start=ws.break_start, break_end=ws.break_end)
        description = f"{WEEKDAY_NAMES[weekday]}: часы работы изменятся на {start_value.strftime('%H:%M')}–{end_value.strftime('%H:%M')}."
    else:
        if not (ws.start_time <= start_value and end_value <= ws.end_time):
            await state.set_state(AdminScheduleTimeInput.entering_start)
            await message.answer(
                f"Перерыв должен быть внутри рабочих часов ({ws.start_time.strftime('%H:%M')}–{ws.end_time.strftime('%H:%M')}). "
                "Введите время начала перерыва ещё раз:"
            )
            return
        pending = {
            "kind": "weekday_break",
            "weekday": weekday,
            "start": start_value.strftime("%H:%M"),
            "end": end_value.strftime("%H:%M"),
        }
        window = WorkWindow(start=ws.start_time, end=ws.end_time, break_start=start_value, break_end=end_value)
        description = f"{WEEKDAY_NAMES[weekday]}: перерыв изменится на {start_value.strftime('%H:%M')}–{end_value.strftime('%H:%M')}."

    conflicts = await find_weekday_conflicts(session, weekday, window)
    await state.set_state(None)
    await _finalize(message, state, session, pending, conflicts, description)


# --- Разовые особые дни ---


@router.callback_query(AdminMenuCallback.filter(F.action == "exceptions"), IsAdmin())
async def cb_admin_exceptions_list(callback: CallbackQuery, state: FSMContext, session: AsyncSession) -> None:
    await state.clear()
    exceptions = await ScheduleRepository(session).list_exceptions(from_date=datetime.now(settings.tzinfo).date())
    text = "📅 Особые дни\n\nРазовый выходной (праздник) или день с другими часами работы."
    if not exceptions:
        text += "\n\nПока не добавлено ни одного особого дня."
    await show_text(callback, text, admin_exceptions_list_keyboard(exceptions))


@router.callback_query(AdminMenuCallback.filter(F.action == "exception_add"), IsAdmin())
async def cb_admin_exception_add_start(callback: CallbackQuery, state: FSMContext) -> None:
    await state.set_state(AdminExceptionCreate.entering_date)
    await show_text(
        callback, "➕ Особый день\n\nВведите дату в формате ДД.ММ.ГГГГ, например 23.02.2027:", admin_exception_cancel_keyboard()
    )


@router.message(AdminExceptionCreate.entering_date, IsAdmin())
async def admin_exception_enter_date(message: Message, state: FSMContext) -> None:
    day = _parse_date(message.text)
    if day is None:
        await message.answer("Не получилось распознать дату. Введите в формате ДД.ММ.ГГГГ, например 23.02.2027:")
        return
    today = datetime.now(settings.tzinfo).date()
    if day < today:
        await message.answer("Дата уже в прошлом. Введите будущую дату:")
        return
    await state.update_data(date=day.isoformat())
    await state.set_state(AdminExceptionCreate.choosing_kind)
    await message.answer(f"Дата: {format_date_ru(day)}.\n\nЧто сделать с этим днём?", reply_markup=admin_exception_kind_keyboard())


@router.callback_query(AdminExceptionKindCallback.filter(F.kind == "day_off"), AdminExceptionCreate.choosing_kind, IsAdmin())
async def cb_admin_exception_day_off(callback: CallbackQuery, state: FSMContext, session: AsyncSession) -> None:
    data = await state.get_data()
    day = date.fromisoformat(data["date"])
    pending = {"kind": "exception_add", "date": data["date"], "is_day_off": True, "start": None, "end": None}
    conflicts = await find_date_conflicts(session, day, None)
    await state.set_state(None)
    await _finalize(callback, state, session, pending, conflicts, f"{format_date_ru(day)} станет выходным.")


@router.callback_query(AdminExceptionKindCallback.filter(F.kind == "custom"), AdminExceptionCreate.choosing_kind, IsAdmin())
async def cb_admin_exception_custom_hours(callback: CallbackQuery, state: FSMContext) -> None:
    await state.set_state(AdminExceptionCreate.entering_start)
    await show_text(callback, "Введите время начала работы, например 10:00:", admin_exception_cancel_keyboard())


@router.message(AdminExceptionCreate.entering_start, IsAdmin())
async def admin_exception_enter_start(message: Message, state: FSMContext) -> None:
    value = _parse_time(message.text)
    if value is None:
        await message.answer("Введите время в формате ЧЧ:ММ, например 10:00")
        return
    await state.update_data(start=value.strftime("%H:%M"))
    await state.set_state(AdminExceptionCreate.entering_end)
    await message.answer("Введите время окончания работы, например 19:00:")


@router.message(AdminExceptionCreate.entering_end, IsAdmin())
async def admin_exception_enter_end(message: Message, state: FSMContext, session: AsyncSession) -> None:
    end_value = _parse_time(message.text)
    if end_value is None:
        await message.answer("Введите время в формате ЧЧ:ММ, например 19:00")
        return

    data = await state.get_data()
    start_value = time.fromisoformat(data["start"])
    if end_value <= start_value:
        await message.answer("Время окончания должно быть позже времени начала. Введите ещё раз:")
        return

    day = date.fromisoformat(data["date"])
    pending = {
        "kind": "exception_add",
        "date": data["date"],
        "is_day_off": False,
        "start": start_value.strftime("%H:%M"),
        "end": end_value.strftime("%H:%M"),
    }
    window = WorkWindow(start=start_value, end=end_value)
    conflicts = await find_date_conflicts(session, day, window)
    await state.set_state(None)
    description = f"{format_date_ru(day)}: часы работы — {start_value.strftime('%H:%M')}–{end_value.strftime('%H:%M')}."
    await _finalize(message, state, session, pending, conflicts, description)


@router.callback_query(AdminExceptionDeleteCallback.filter(), IsAdmin())
async def cb_admin_exception_delete(callback: CallbackQuery, callback_data: AdminExceptionDeleteCallback, session: AsyncSession) -> None:
    repo = ScheduleRepository(session)
    exception = await repo.get_exception_by_id(callback_data.exception_id)
    if exception is not None:
        await repo.delete_exception(exception)
        await session.commit()
    exceptions = await repo.list_exceptions(from_date=datetime.now(settings.tzinfo).date())
    await callback.answer("Особый день удалён.")
    text = "📅 Особые дни"
    if not exceptions:
        text += "\n\nПока не добавлено ни одного особого дня."
    await show_text(callback, text, admin_exceptions_list_keyboard(exceptions))


# --- Подтверждение/отмена изменения при конфликте с записями ---


@router.callback_query(AdminMenuCallback.filter(F.action == "schedule_apply_pending"), IsAdmin())
async def cb_schedule_apply_pending(callback: CallbackQuery, state: FSMContext, session: AsyncSession) -> None:
    data = await state.get_data()
    pending = data.get("pending_schedule_change")
    if not pending:
        await callback.answer("Нечего сохранять.", show_alert=True)
        return
    result_text = await _apply_pending_change(session, pending)
    await state.update_data(pending_schedule_change=None)
    await _after_apply(callback, session, pending, result_text)


@router.callback_query(AdminMenuCallback.filter(F.action == "schedule_cancel_pending"), IsAdmin())
async def cb_schedule_cancel_pending(callback: CallbackQuery, state: FSMContext, session: AsyncSession) -> None:
    data = await state.get_data()
    pending = data.get("pending_schedule_change")
    await state.update_data(pending_schedule_change=None)
    await callback.answer("Изменение отменено.")

    if pending and pending["kind"] == "exception_add":
        exceptions = await ScheduleRepository(session).list_exceptions(from_date=datetime.now(settings.tzinfo).date())
        await show_text(callback, "📅 Особые дни", admin_exceptions_list_keyboard(exceptions))
    elif pending:
        ws = await ScheduleRepository(session).get_for_weekday(pending["weekday"])
        await show_text(callback, _weekday_detail_text(ws), admin_schedule_weekday_detail_keyboard(ws))
    else:
        await _render_hub(callback, session)
