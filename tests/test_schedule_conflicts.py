from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

import pytest

from app.models import Service, User
from app.services.booking import create_appointment
from app.services.schedule_conflicts import find_date_conflicts, find_weekday_conflicts
from app.services.slots import WorkWindow

TZ = ZoneInfo("Asia/Yekaterinburg")


def _next_weekday(weekday: int) -> date:
    """Ближайшая будущая дата с этим днём недели (0=Пн) — find_weekday_conflicts смотрит только вперёд."""
    today = datetime.now(TZ).date()
    days_ahead = (weekday - today.weekday()) % 7
    days_ahead = days_ahead or 7  # если сегодня и есть нужный день недели — берём следующую неделю
    return today + timedelta(days=days_ahead)


async def _make_user_and_service(session):
    user = User(telegram_id=222, username="client", full_name="Клиент")
    service = Service(name="Классика", description="", price=2500, duration_minutes=120)
    session.add_all([user, service])
    await session.commit()
    return user, service


@pytest.mark.asyncio
async def test_find_date_conflicts_detects_appointment_before_new_start(session, working_schedule):
    """Ровно сценарий из обсуждения: запись на 15:00, мастер хочет начинать день с 16:00."""
    user, service = await _make_user_and_service(session)
    monday = date(2026, 8, 24)
    assert monday.weekday() == 0
    start_at = datetime.combine(monday, time(15, 0), tzinfo=TZ)
    await create_appointment(session, user, service, start_at)  # запись 15:00-17:00

    new_window = WorkWindow(start=time(16, 0), end=time(19, 0))
    conflicts = await find_date_conflicts(session, monday, new_window)

    assert len(conflicts) == 1
    assert conflicts[0].start_at == start_at


@pytest.mark.asyncio
async def test_find_date_conflicts_empty_when_appointment_fits_new_window(session, working_schedule):
    user, service = await _make_user_and_service(session)
    monday = date(2026, 8, 24)
    start_at = datetime.combine(monday, time(16, 0), tzinfo=TZ)
    await create_appointment(session, user, service, start_at)  # запись 16:00-18:00

    new_window = WorkWindow(start=time(16, 0), end=time(19, 0))
    conflicts = await find_date_conflicts(session, monday, new_window)

    assert conflicts == []


@pytest.mark.asyncio
async def test_find_date_conflicts_all_appointments_conflict_when_day_off(session, working_schedule):
    user, service = await _make_user_and_service(session)
    monday = date(2026, 8, 24)
    start_at = datetime.combine(monday, time(11, 0), tzinfo=TZ)
    await create_appointment(session, user, service, start_at)

    conflicts = await find_date_conflicts(session, monday, None)  # None = день становится выходным

    assert len(conflicts) == 1


@pytest.mark.asyncio
async def test_find_date_conflicts_detects_break_overlap(session, working_schedule):
    user, service = await _make_user_and_service(session)
    monday = date(2026, 8, 24)
    # Запись 13:00-15:00 (это ДО появления перерыва — бронируем как будто перерыва ещё не было)
    start_at = datetime.combine(monday, time(13, 0), tzinfo=TZ)
    from app.repositories.appointment_repo import AppointmentRepository
    from datetime import timedelta

    repo = AppointmentRepository(session)
    await repo.create(user_id=user.id, service_id=service.id, start_at=start_at, end_at=start_at + timedelta(minutes=120), price=service.price)
    await session.commit()

    # Новый перерыв 14:00-15:00 пересекает эту запись
    new_window = WorkWindow(start=time(10, 0), end=time(19, 0), break_start=time(14, 0), break_end=time(15, 0))
    conflicts = await find_date_conflicts(session, monday, new_window)

    assert len(conflicts) == 1


@pytest.mark.asyncio
async def test_find_weekday_conflicts_checks_future_occurrences_of_weekday(session, working_schedule):
    user, service = await _make_user_and_service(session)
    next_monday = _next_weekday(0)
    start_at = datetime.combine(next_monday, time(17, 0), tzinfo=TZ)
    await create_appointment(session, user, service, start_at)  # 17:00-19:00, попадает в текущие часы Пн (10-19)

    # Сокращаем рабочий день понедельника до 18:00 -> запись 17:00-19:00 больше не помещается
    new_window = WorkWindow(start=time(10, 0), end=time(18, 0))
    conflicts = await find_weekday_conflicts(session, weekday=0, window=new_window)

    assert len(conflicts) == 1
    assert conflicts[0].start_at == start_at


@pytest.mark.asyncio
async def test_find_weekday_conflicts_ignores_other_weekdays(session, working_schedule):
    user, service = await _make_user_and_service(session)
    tuesday = _next_weekday(1)
    start_at = datetime.combine(tuesday, time(17, 0), tzinfo=TZ)
    await create_appointment(session, user, service, start_at)

    # Проверяем конфликты для понедельника (weekday=0) — вторничная запись не должна попасть
    conflicts = await find_weekday_conflicts(session, weekday=0, window=WorkWindow(start=time(10, 0), end=time(12, 0)))

    assert conflicts == []


@pytest.mark.asyncio
async def test_find_weekday_conflicts_none_window_means_all_conflict(session, working_schedule):
    user, service = await _make_user_and_service(session)
    monday = _next_weekday(0)
    start_at = datetime.combine(monday, time(11, 0), tzinfo=TZ)
    await create_appointment(session, user, service, start_at)

    conflicts = await find_weekday_conflicts(session, weekday=0, window=None)

    assert len(conflicts) == 1
