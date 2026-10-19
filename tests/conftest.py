import os
from datetime import time as time_type

import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.models import Base, WorkingSchedule

TEST_DATABASE_URL = os.environ.get(
    "TEST_DATABASE_URL", "postgresql+asyncpg://postgres:postgres@localhost:5544/beauty_demo_test"
)


@pytest_asyncio.fixture()
async def session():
    engine = create_async_engine(TEST_DATABASE_URL)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)

    session_maker = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
    async with session_maker() as db_session:
        yield db_session

    await engine.dispose()


@pytest_asyncio.fixture()
async def working_schedule(session: AsyncSession) -> list[WorkingSchedule]:
    """Пн-Пт 10:00-19:00 с перерывом 14:00-15:00, Сб 11:00-16:00, Вс выходной."""
    schedule = [
        WorkingSchedule(
            weekday=i,
            is_day_off=False,
            start_time=time_type(10, 0),
            end_time=time_type(19, 0),
            break_start=time_type(14, 0),
            break_end=time_type(15, 0),
        )
        for i in range(5)
    ]
    schedule.append(
        WorkingSchedule(weekday=5, is_day_off=False, start_time=time_type(11, 0), end_time=time_type(16, 0))
    )
    schedule.append(WorkingSchedule(weekday=6, is_day_off=True))
    session.add_all(schedule)
    await session.commit()
    return schedule
