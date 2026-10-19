"""Расчёт свободных слотов для записи.

Логика намеренно разделена на чистые функции (легко тестировать без БД)
и обёртки, которые подтягивают график и существующие записи из БД.
"""

from calendar import monthrange
from dataclasses import dataclass
from datetime import date as date_type
from datetime import datetime, time, timedelta

STEP_MINUTES = 30


def _to_minutes(value: time) -> int:
    return value.hour * 60 + value.minute


def _from_minutes(value: int) -> time:
    return time(hour=value // 60, minute=value % 60)


@dataclass(frozen=True)
class WorkWindow:
    start: time
    end: time
    break_start: time | None = None
    break_end: time | None = None


def generate_working_slots(window: WorkWindow, duration_minutes: int, step_minutes: int = STEP_MINUTES) -> list[time]:
    """Возвращает список времён начала услуги, которые целиком помещаются
    в рабочее окно, не пересекая перерыв."""
    start_min = _to_minutes(window.start)
    end_min = _to_minutes(window.end)
    break_start_min = _to_minutes(window.break_start) if window.break_start else None
    break_end_min = _to_minutes(window.break_end) if window.break_end else None

    slots: list[time] = []
    candidate = start_min
    while candidate + duration_minutes <= end_min:
        slot_end = candidate + duration_minutes
        overlaps_break = (
            break_start_min is not None
            and break_end_min is not None
            and candidate < break_end_min
            and slot_end > break_start_min
        )
        if not overlaps_break:
            slots.append(_from_minutes(candidate))
        candidate += step_minutes
    return slots


def filter_out_busy(
    candidates: list[datetime],
    duration_minutes: int,
    busy_intervals: list[tuple[datetime, datetime]],
) -> list[datetime]:
    """Убирает кандидатов, пересекающихся с уже занятыми интервалами."""
    free: list[datetime] = []
    for start in candidates:
        end = start + timedelta(minutes=duration_minutes)
        if any(start < busy_end and end > busy_start for busy_start, busy_end in busy_intervals):
            continue
        free.append(start)
    return free


def filter_out_past(candidates: list[datetime], now: datetime) -> list[datetime]:
    return [c for c in candidates if c > now]


def resolve_work_window(exception, working_day) -> WorkWindow | None:
    """Собирает рабочее окно дня из исключения (если есть) или недельного графика.
    Возвращает None, если день выходной."""
    if exception is not None:
        if exception.is_day_off or exception.start_time is None or exception.end_time is None:
            return None
        return WorkWindow(start=exception.start_time, end=exception.end_time)

    if working_day is None or working_day.is_day_off or working_day.start_time is None or working_day.end_time is None:
        return None
    return WorkWindow(
        start=working_day.start_time,
        end=working_day.end_time,
        break_start=working_day.break_start,
        break_end=working_day.break_end,
    )


async def get_available_slots(
    session,
    service,
    target_date: date_type,
    now: datetime,
    tzinfo,
    exclude_appointment_id: int | None = None,
) -> list[datetime]:
    from app.repositories.appointment_repo import AppointmentRepository
    from app.repositories.schedule_repo import ScheduleRepository

    schedule_repo = ScheduleRepository(session)
    appointment_repo = AppointmentRepository(session)

    exception = await schedule_repo.get_exception(target_date)
    working_day = None if exception is not None else await schedule_repo.get_for_weekday(target_date.weekday())
    window = resolve_work_window(exception, working_day)
    if window is None:
        return []

    candidate_times = generate_working_slots(window, service.duration_minutes)
    candidates = [datetime.combine(target_date, t, tzinfo=tzinfo) for t in candidate_times]

    day_start = datetime.combine(target_date, time.min, tzinfo=tzinfo)
    day_end = day_start + timedelta(days=1)
    existing = await appointment_repo.list_confirmed_in_range(day_start, day_end, exclude_id=exclude_appointment_id)
    busy_intervals = [(a.start_at, a.end_at) for a in existing]

    candidates = filter_out_busy(candidates, service.duration_minutes, busy_intervals)
    if target_date == now.date():
        candidates = filter_out_past(candidates, now)
    return candidates


async def get_month_availability(
    session,
    service,
    year: int,
    month: int,
    now: datetime,
    tzinfo,
    exclude_appointment_id: int | None = None,
) -> dict[date_type, list[datetime] | None]:
    """Свободные слоты на каждый день месяца одним проходом (3 запроса к БД вместо
    одного на каждый день) — используется для отрисовки календаря.

    Значение `None` для дня означает выходной, пустой список — рабочий день,
    но все слоты заняты записями (когда стоит показывать значок "занято").
    """
    from app.repositories.appointment_repo import AppointmentRepository
    from app.repositories.schedule_repo import ScheduleRepository

    schedule_repo = ScheduleRepository(session)
    appointment_repo = AppointmentRepository(session)

    days_in_month = monthrange(year, month)[1]
    first_day = date_type(year, month, 1)
    last_day = date_type(year, month, days_in_month)

    week_by_weekday = {w.weekday: w for w in await schedule_repo.get_week()}
    exceptions_by_date = {e.date: e for e in await schedule_repo.list_exceptions_in_range(first_day, last_day)}

    month_start = datetime.combine(first_day, time.min, tzinfo=tzinfo)
    month_end = datetime.combine(last_day, time.min, tzinfo=tzinfo) + timedelta(days=1)
    appointments = await appointment_repo.list_confirmed_in_range(month_start, month_end, exclude_id=exclude_appointment_id)

    result: dict[date_type, list[datetime] | None] = {}
    for day_num in range(1, days_in_month + 1):
        current_date = date_type(year, month, day_num)
        window = resolve_work_window(exceptions_by_date.get(current_date), week_by_weekday.get(current_date.weekday()))
        if window is None:
            result[current_date] = None
            continue

        candidate_times = generate_working_slots(window, service.duration_minutes)
        candidates = [datetime.combine(current_date, t, tzinfo=tzinfo) for t in candidate_times]

        day_start = datetime.combine(current_date, time.min, tzinfo=tzinfo)
        day_end = day_start + timedelta(days=1)
        busy_intervals = [(a.start_at, a.end_at) for a in appointments if day_start <= a.start_at < day_end]

        candidates = filter_out_busy(candidates, service.duration_minutes, busy_intervals)
        if current_date == now.date():
            candidates = filter_out_past(candidates, now)
        result[current_date] = candidates

    return result


async def get_month_day_off_map(session, year: int, month: int) -> dict[date_type, bool]:
    """Для каждого дня месяца — выходной он или нет (по недельному графику/исключениям).
    Не зависит от услуги, в отличие от get_month_availability — используется в админке,
    где важен сам факт "рабочий/выходной", а не подбор слотов под конкретную услугу."""
    from app.repositories.schedule_repo import ScheduleRepository

    schedule_repo = ScheduleRepository(session)

    days_in_month = monthrange(year, month)[1]
    first_day = date_type(year, month, 1)
    last_day = date_type(year, month, days_in_month)

    week_by_weekday = {w.weekday: w for w in await schedule_repo.get_week()}
    exceptions_by_date = {e.date: e for e in await schedule_repo.list_exceptions_in_range(first_day, last_day)}

    result: dict[date_type, bool] = {}
    for day_num in range(1, days_in_month + 1):
        current_date = date_type(year, month, day_num)
        window = resolve_work_window(exceptions_by_date.get(current_date), week_by_weekday.get(current_date.weekday()))
        result[current_date] = window is None
    return result
