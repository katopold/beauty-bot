from datetime import datetime, timedelta

from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Appointment, Service, User
from app.repositories.appointment_repo import AppointmentRepository


class SlotUnavailableError(Exception):
    """Слот уже занят другой записью (перехвачен гонкой конкурентных запросов)."""


async def create_appointment(session: AsyncSession, user: User, service: Service, start_at: datetime) -> Appointment:
    end_at = start_at + timedelta(minutes=service.duration_minutes)
    repo = AppointmentRepository(session)
    if await repo.has_overlap(start_at, end_at):
        raise SlotUnavailableError()
    appointment = await repo.create(
        user_id=user.id, service_id=service.id, start_at=start_at, end_at=end_at, price=service.price
    )
    await session.commit()
    return appointment


async def cancel_appointment(session: AsyncSession, appointment: Appointment) -> None:
    repo = AppointmentRepository(session)
    await repo.cancel(appointment)
    await session.commit()


async def reschedule_appointment(
    session: AsyncSession, appointment: Appointment, new_start_at: datetime, duration_minutes: int
) -> Appointment:
    new_end_at = new_start_at + timedelta(minutes=duration_minutes)
    repo = AppointmentRepository(session)
    if await repo.has_overlap(new_start_at, new_end_at, exclude_id=appointment.id):
        raise SlotUnavailableError()
    await repo.reschedule(appointment, new_start_at, new_end_at)
    await session.commit()
    return appointment
