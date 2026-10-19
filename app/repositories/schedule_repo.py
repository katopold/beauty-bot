from datetime import date as date_type
from datetime import time as time_type

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import ScheduleException, WorkingSchedule


class ScheduleRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def get_week(self) -> list[WorkingSchedule]:
        result = await self.session.execute(select(WorkingSchedule).order_by(WorkingSchedule.weekday))
        return list(result.scalars().all())

    async def get_for_weekday(self, weekday: int) -> WorkingSchedule | None:
        result = await self.session.execute(select(WorkingSchedule).where(WorkingSchedule.weekday == weekday))
        return result.scalar_one_or_none()

    async def get_exception(self, day: date_type) -> ScheduleException | None:
        result = await self.session.execute(select(ScheduleException).where(ScheduleException.date == day))
        return result.scalar_one_or_none()

    async def list_exceptions_in_range(self, start: date_type, end: date_type) -> list[ScheduleException]:
        result = await self.session.execute(
            select(ScheduleException).where(ScheduleException.date >= start, ScheduleException.date <= end)
        )
        return list(result.scalars().all())

    async def list_exceptions(self, from_date: date_type | None = None) -> list[ScheduleException]:
        stmt = select(ScheduleException).order_by(ScheduleException.date)
        if from_date is not None:
            stmt = stmt.where(ScheduleException.date >= from_date)
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def get_exception_by_id(self, exception_id: int) -> ScheduleException | None:
        return await self.session.get(ScheduleException, exception_id)

    async def upsert_exception(
        self, day: date_type, is_day_off: bool, start_time: time_type | None, end_time: time_type | None
    ) -> ScheduleException:
        """Создаёт особый день на дату `day`, заменяя существующий, если он уже был."""
        existing = await self.get_exception(day)
        if existing is not None:
            await self.session.delete(existing)
            await self.session.flush()
        exception = ScheduleException(date=day, is_day_off=is_day_off, start_time=start_time, end_time=end_time)
        self.session.add(exception)
        await self.session.flush()
        return exception

    async def delete_exception(self, exception: ScheduleException) -> None:
        await self.session.delete(exception)
        await self.session.flush()
