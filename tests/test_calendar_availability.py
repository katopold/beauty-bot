from calendar import monthrange
from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

import pytest

from app.models import Service
from app.repositories.appointment_repo import AppointmentRepository
from app.services.slots import get_month_availability

TZ = ZoneInfo("Asia/Yekaterinburg")


def _next_month(year: int, month: int) -> tuple[int, int]:
    return (year + 1, 1) if month == 12 else (year, month + 1)


@pytest.mark.asyncio
async def test_month_availability_covers_every_day_of_month_no_more_no_less(session, working_schedule):
    service = Service(name="Классика", description="", price=2500, duration_minutes=120)
    session.add(service)
    await session.commit()

    year, month = 2027, 2  # февраль — хороший тест на количество дней (28/29)
    now = datetime(year, 1, 15, 9, 0, tzinfo=TZ)
    availability = await get_month_availability(session, service, year, month, now, TZ)

    days_in_month = monthrange(year, month)[1]
    assert len(availability) == days_in_month
    assert date(year, month, days_in_month) in availability
    next_year, next_month = _next_month(year, month)
    assert date(next_year, next_month, 1) not in availability


@pytest.mark.asyncio
async def test_month_availability_marks_day_off_as_none(session, working_schedule):
    service = Service(name="Классика", description="", price=2500, duration_minutes=120)
    session.add(service)
    await session.commit()

    # 2026-08-30 — воскресенье (выходной по стандартному графику фикстуры)
    now = datetime(2026, 8, 1, 9, 0, tzinfo=TZ)
    availability = await get_month_availability(session, service, 2026, 8, now, TZ)

    assert availability[date(2026, 8, 30)] is None


@pytest.mark.asyncio
async def test_month_availability_marks_fully_booked_working_day_as_empty_list(session, working_schedule):
    service = Service(name="Классика", description="", price=2500, duration_minutes=120)
    session.add(service)
    await session.commit()
    await session.flush()

    from app.models import User

    user = User(telegram_id=555, username="u", full_name="Клиент")
    session.add(user)
    await session.commit()

    # 2026-08-24 — понедельник, рабочий день 10:00-19:00 с перерывом 14:00-15:00
    monday = date(2026, 8, 24)
    repo = AppointmentRepository(session)
    # Занимаем всё рабочее время двумя длинными записями: 10:00-14:00 и 15:00-19:00
    await repo.create(
        user_id=user.id,
        service_id=service.id,
        start_at=datetime.combine(monday, time(10, 0), tzinfo=TZ),
        end_at=datetime.combine(monday, time(14, 0), tzinfo=TZ),
        price=service.price,
    )
    await repo.create(
        user_id=user.id,
        service_id=service.id,
        start_at=datetime.combine(monday, time(15, 0), tzinfo=TZ),
        end_at=datetime.combine(monday, time(19, 0), tzinfo=TZ),
        price=service.price,
    )
    await session.commit()

    now = datetime(2026, 8, 1, 9, 0, tzinfo=TZ)
    availability = await get_month_availability(session, service, 2026, 8, now, TZ)

    assert availability[monday] == []


@pytest.mark.asyncio
async def test_month_availability_partially_booked_day_has_remaining_slots(session, working_schedule):
    service = Service(name="Классика", description="", price=2500, duration_minutes=120)
    session.add(service)
    await session.commit()

    from app.models import User

    user = User(telegram_id=556, username="u2", full_name="Клиент 2")
    session.add(user)
    await session.commit()

    monday = date(2026, 8, 24)
    repo = AppointmentRepository(session)
    await repo.create(
        user_id=user.id,
        service_id=service.id,
        start_at=datetime.combine(monday, time(10, 0), tzinfo=TZ),
        end_at=datetime.combine(monday, time(12, 0), tzinfo=TZ),
        price=service.price,
    )
    await session.commit()

    now = datetime(2026, 8, 1, 9, 0, tzinfo=TZ)
    availability = await get_month_availability(session, service, 2026, 8, now, TZ)

    assert availability[monday] != []
    assert availability[monday] is not None
    assert datetime.combine(monday, time(10, 0), tzinfo=TZ) not in availability[monday]  # занято
    assert datetime.combine(monday, time(12, 0), tzinfo=TZ) in availability[monday]  # свободно сразу после


@pytest.mark.asyncio
async def test_month_availability_excludes_appointment_being_rescheduled(session, working_schedule):
    service = Service(name="Классика", description="", price=2500, duration_minutes=120)
    session.add(service)
    await session.commit()

    from app.models import User

    user = User(telegram_id=557, username="u3", full_name="Клиент 3")
    session.add(user)
    await session.commit()

    monday = date(2026, 8, 24)
    repo = AppointmentRepository(session)
    appt = await repo.create(
        user_id=user.id,
        service_id=service.id,
        start_at=datetime.combine(monday, time(10, 0), tzinfo=TZ),
        end_at=datetime.combine(monday, time(14, 0), tzinfo=TZ),
        price=service.price,
    )
    await repo.create(
        user_id=user.id,
        service_id=service.id,
        start_at=datetime.combine(monday, time(15, 0), tzinfo=TZ),
        end_at=datetime.combine(monday, time(19, 0), tzinfo=TZ),
        price=service.price,
    )
    await session.commit()

    now = datetime(2026, 8, 1, 9, 0, tzinfo=TZ)

    without_exclude = await get_month_availability(session, service, 2026, 8, now, TZ)
    assert without_exclude[monday] == []

    with_exclude = await get_month_availability(session, service, 2026, 8, now, TZ, exclude_appointment_id=appt.id)
    assert with_exclude[monday] != []  # своя же запись больше не блокирует день
