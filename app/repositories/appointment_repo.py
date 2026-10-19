from datetime import datetime

from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models import Appointment, AppointmentStatus, Service, User


class AppointmentRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def get(self, appointment_id: int) -> Appointment | None:
        result = await self.session.execute(
            select(Appointment)
            .options(selectinload(Appointment.service), selectinload(Appointment.user))
            .where(Appointment.id == appointment_id)
        )
        return result.scalar_one_or_none()

    async def list_confirmed_in_range(
        self, range_start: datetime, range_end: datetime, exclude_id: int | None = None
    ) -> list[Appointment]:
        """Подтверждённые записи, пересекающиеся с полуинтервалом [range_start, range_end)."""
        conditions = [
            Appointment.status == AppointmentStatus.CONFIRMED,
            Appointment.start_at < range_end,
            Appointment.end_at > range_start,
        ]
        if exclude_id is not None:
            conditions.append(Appointment.id != exclude_id)
        result = await self.session.execute(
            select(Appointment)
            .options(selectinload(Appointment.service), selectinload(Appointment.user))
            .where(and_(*conditions))
        )
        return list(result.scalars().all())

    async def has_overlap(self, start_at: datetime, end_at: datetime, exclude_id: int | None = None) -> bool:
        appointments = await self.list_confirmed_in_range(start_at, end_at, exclude_id=exclude_id)
        return len(appointments) > 0

    async def create(self, user_id: int, service_id: int, start_at: datetime, end_at: datetime, price: int) -> Appointment:
        appointment = Appointment(
            user_id=user_id,
            service_id=service_id,
            start_at=start_at,
            end_at=end_at,
            price_at_booking=price,
            status=AppointmentStatus.CONFIRMED,
        )
        self.session.add(appointment)
        await self.session.flush()
        return appointment

    async def get_nearest_active_for_user(self, user_id: int, now: datetime) -> Appointment | None:
        result = await self.session.execute(
            select(Appointment)
            .options(selectinload(Appointment.service))
            .where(
                Appointment.user_id == user_id,
                Appointment.status == AppointmentStatus.CONFIRMED,
                Appointment.end_at > now,
            )
            .order_by(Appointment.start_at)
            .limit(1)
        )
        return result.scalar_one_or_none()

    async def cancel(self, appointment: Appointment) -> None:
        appointment.status = AppointmentStatus.CANCELLED
        await self.session.flush()

    async def reschedule(self, appointment: Appointment, start_at: datetime, end_at: datetime) -> None:
        appointment.start_at = start_at
        appointment.end_at = end_at
        appointment.reminder_24h_sent = False
        appointment.reminder_2h_sent = False
        await self.session.flush()

    async def list_for_day(self, day_start: datetime, day_end: datetime) -> list[Appointment]:
        result = await self.session.execute(
            select(Appointment)
            .options(selectinload(Appointment.service), selectinload(Appointment.user))
            .where(
                Appointment.status == AppointmentStatus.CONFIRMED,
                Appointment.start_at >= day_start,
                Appointment.start_at < day_end,
            )
            .order_by(Appointment.start_at)
        )
        return list(result.scalars().all())

    async def list_upcoming(self, after: datetime, limit: int = 20) -> list[Appointment]:
        result = await self.session.execute(
            select(Appointment)
            .options(selectinload(Appointment.service), selectinload(Appointment.user))
            .where(Appointment.status == AppointmentStatus.CONFIRMED, Appointment.start_at >= after)
            .order_by(Appointment.start_at)
            .limit(limit)
        )
        return list(result.scalars().all())

    async def exists_for_service(self, service_id: int) -> bool:
        result = await self.session.execute(select(Appointment.id).where(Appointment.service_id == service_id).limit(1))
        return result.scalar_one_or_none() is not None

    async def list_needing_reminder(
        self, now: datetime, window_start: datetime, window_end: datetime, sent_flag: str
    ) -> list[Appointment]:
        flag_column = getattr(Appointment, sent_flag)
        result = await self.session.execute(
            select(Appointment)
            .options(selectinload(Appointment.service), selectinload(Appointment.user))
            .where(
                Appointment.status == AppointmentStatus.CONFIRMED,
                flag_column.is_(False),
                Appointment.start_at > now,
                Appointment.start_at >= window_start,
                Appointment.start_at < window_end,
            )
        )
        return list(result.scalars().all())
