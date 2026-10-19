from datetime import date, datetime, time
from zoneinfo import ZoneInfo

import pytest

from app.models import AppointmentStatus, Service, User
from app.repositories.appointment_repo import AppointmentRepository
from app.services.booking import SlotUnavailableError, cancel_appointment, create_appointment, reschedule_appointment

TZ = ZoneInfo("Asia/Yekaterinburg")


@pytest.fixture()
def booking_day() -> date:
    return date(2026, 8, 24)  # понедельник


async def _make_user_and_service(session):
    user = User(telegram_id=111, username="client", full_name="Тестовый клиент")
    service = Service(name="Классика", description="", price=2500, duration_minutes=120)
    session.add_all([user, service])
    await session.commit()
    return user, service


@pytest.mark.asyncio
async def test_create_appointment_success(session, booking_day):
    user, service = await _make_user_and_service(session)
    start_at = datetime.combine(booking_day, time(12, 0), tzinfo=TZ)

    appointment = await create_appointment(session, user, service, start_at)

    assert appointment.id is not None
    assert appointment.status == AppointmentStatus.CONFIRMED
    assert appointment.end_at == start_at.replace(hour=14)
    assert appointment.price_at_booking == service.price


@pytest.mark.asyncio
async def test_create_appointment_rejects_overlap(session, booking_day):
    user, service = await _make_user_and_service(session)
    start_at = datetime.combine(booking_day, time(12, 0), tzinfo=TZ)
    await create_appointment(session, user, service, start_at)

    overlapping_start = datetime.combine(booking_day, time(13, 0), tzinfo=TZ)
    with pytest.raises(SlotUnavailableError):
        await create_appointment(session, user, service, overlapping_start)


@pytest.mark.asyncio
async def test_create_appointment_allows_back_to_back_slots(session, booking_day):
    user, service = await _make_user_and_service(session)
    first_start = datetime.combine(booking_day, time(10, 0), tzinfo=TZ)
    await create_appointment(session, user, service, first_start)

    # Начинается ровно в момент окончания первой записи (12:00) -> не пересекается
    second_start = datetime.combine(booking_day, time(12, 0), tzinfo=TZ)
    appointment = await create_appointment(session, user, service, second_start)
    assert appointment.id is not None


@pytest.mark.asyncio
async def test_cancel_appointment_frees_slot(session, booking_day):
    user, service = await _make_user_and_service(session)
    start_at = datetime.combine(booking_day, time(12, 0), tzinfo=TZ)
    appointment = await create_appointment(session, user, service, start_at)

    await cancel_appointment(session, appointment)
    assert appointment.status == AppointmentStatus.CANCELLED

    # Тот же слот снова можно забронировать
    new_appointment = await create_appointment(session, user, service, start_at)
    assert new_appointment.id is not None


@pytest.mark.asyncio
async def test_reschedule_frees_old_slot_and_occupies_new(session, booking_day):
    user, service = await _make_user_and_service(session)
    original_start = datetime.combine(booking_day, time(12, 0), tzinfo=TZ)
    appointment = await create_appointment(session, user, service, original_start)

    new_start = datetime.combine(booking_day, time(16, 0), tzinfo=TZ)
    await reschedule_appointment(session, appointment, new_start, service.duration_minutes)

    assert appointment.start_at == new_start
    assert appointment.status == AppointmentStatus.CONFIRMED

    # Старый слот (12:00) снова свободен
    another_appointment = await create_appointment(session, user, service, original_start)
    assert another_appointment.id is not None

    # Новый слот (16:00) занят перенесённой записью
    repo = AppointmentRepository(session)
    assert await repo.has_overlap(new_start, new_start.replace(hour=18))


@pytest.mark.asyncio
async def test_reschedule_rejects_overlap_with_other_appointment(session, booking_day):
    user, service = await _make_user_and_service(session)
    appointment_a = await create_appointment(session, user, service, datetime.combine(booking_day, time(10, 0), tzinfo=TZ))
    appointment_b = await create_appointment(session, user, service, datetime.combine(booking_day, time(16, 0), tzinfo=TZ))

    with pytest.raises(SlotUnavailableError):
        await reschedule_appointment(
            session, appointment_b, datetime.combine(booking_day, time(11, 0), tzinfo=TZ), service.duration_minutes
        )

    # Запись B не должна была измениться после неудачной попытки переноса
    assert appointment_b.start_at == datetime.combine(booking_day, time(16, 0), tzinfo=TZ)
    assert appointment_a.status == AppointmentStatus.CONFIRMED
