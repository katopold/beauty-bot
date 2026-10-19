from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

import pytest

from app.models import Service
from app.services.slots import WorkWindow, filter_out_busy, filter_out_past, generate_working_slots, get_available_slots

TZ = ZoneInfo("Asia/Yekaterinburg")


def test_generate_slots_basic_step():
    window = WorkWindow(start=time(10, 0), end=time(12, 0))
    slots = generate_working_slots(window, duration_minutes=60, step_minutes=30)
    assert slots == [time(10, 0), time(10, 30), time(11, 0)]


def test_generate_slots_duration_must_fit_before_closing():
    # Услуга 2 часа, рабочий день заканчивается в 19:00 -> последний слот в 17:00
    window = WorkWindow(start=time(10, 0), end=time(19, 0))
    slots = generate_working_slots(window, duration_minutes=120, step_minutes=30)
    assert slots[-1] == time(17, 0)
    assert time(17, 30) not in slots


def test_generate_slots_excludes_break_overlap():
    window = WorkWindow(start=time(10, 0), end=time(19, 0), break_start=time(14, 0), break_end=time(15, 0))
    slots = generate_working_slots(window, duration_minutes=120, step_minutes=30)
    # Слот 13:00-15:00 пересекает перерыв (14:00-15:00) -> должен быть исключён
    assert time(13, 0) not in slots
    # Слот 13:30-15:30 тоже пересекает перерыв
    assert time(13, 30) not in slots
    # Слот, начинающийся ровно с конца перерыва, должен остаться
    assert time(15, 0) in slots
    # Слот, заканчивающийся ровно к началу перерыва, должен остаться
    assert time(12, 0) in slots


def test_generate_slots_short_service_fits_around_break():
    window = WorkWindow(start=time(10, 0), end=time(19, 0), break_start=time(14, 0), break_end=time(15, 0))
    slots = generate_working_slots(window, duration_minutes=30, step_minutes=30)
    assert time(13, 30) in slots  # заканчивается ровно к началу перерыва
    assert time(14, 0) not in slots  # начинается в перерыве
    assert time(14, 30) not in slots  # тоже внутри перерыва
    assert time(15, 0) in slots  # начинается сразу после перерыва


def test_filter_out_busy_removes_overlapping_candidates():
    day = date(2026, 1, 5)
    candidates = [datetime.combine(day, t, tzinfo=TZ) for t in (time(10, 0), time(11, 0), time(12, 0))]
    busy_start = datetime.combine(day, time(10, 30), tzinfo=TZ)
    busy_end = datetime.combine(day, time(11, 30), tzinfo=TZ)
    free = filter_out_busy(candidates, duration_minutes=60, busy_intervals=[(busy_start, busy_end)])
    assert candidates[0] not in free  # 10:00-11:00 пересекает занятый интервал
    assert candidates[1] not in free  # 11:00-12:00 пересекает занятый интервал
    assert candidates[2] in free  # 12:00-13:00 свободен


def test_filter_out_past_keeps_only_future_slots():
    now = datetime(2026, 1, 5, 12, 0, tzinfo=TZ)
    candidates = [now - timedelta(minutes=30), now, now + timedelta(minutes=30)]
    free = filter_out_past(candidates, now)
    assert free == [now + timedelta(minutes=30)]


@pytest.mark.asyncio
async def test_get_available_slots_returns_empty_on_day_off(session, working_schedule):
    service = Service(name="Классика", description="", price=2500, duration_minutes=120)
    session.add(service)
    await session.commit()

    sunday = date(2026, 8, 30)  # воскресенье
    assert sunday.weekday() == 6
    now = datetime(2026, 8, 24, 9, 0, tzinfo=TZ)
    slots = await get_available_slots(session, service, sunday, now, TZ)
    assert slots == []


@pytest.mark.asyncio
async def test_get_available_slots_respects_saturday_hours(session, working_schedule):
    service = Service(name="Классика", description="", price=2500, duration_minutes=120)
    session.add(service)
    await session.commit()

    saturday = date(2026, 8, 29)
    assert saturday.weekday() == 5
    now = datetime(2026, 8, 24, 9, 0, tzinfo=TZ)
    slots = await get_available_slots(session, service, saturday, now, TZ)
    # Суббота 11:00-16:00, услуга 2 часа -> последний слот в 14:00
    assert slots[0].time() == time(11, 0)
    assert slots[-1].time() == time(14, 0)
