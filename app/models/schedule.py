from datetime import date as date_type
from datetime import time as time_type

from sqlalchemy import Boolean, Date, Integer, Time
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class WorkingSchedule(Base):
    """Регулярный недельный график работы мастера."""

    __tablename__ = "working_schedule"

    id: Mapped[int] = mapped_column(primary_key=True)
    weekday: Mapped[int] = mapped_column(Integer, unique=True)  # 0 = понедельник ... 6 = воскресенье
    is_day_off: Mapped[bool] = mapped_column(Boolean, default=False)
    start_time: Mapped[time_type | None] = mapped_column(Time, nullable=True)
    end_time: Mapped[time_type | None] = mapped_column(Time, nullable=True)
    break_start: Mapped[time_type | None] = mapped_column(Time, nullable=True)
    break_end: Mapped[time_type | None] = mapped_column(Time, nullable=True)


class ScheduleException(Base):
    """Точечное исключение из графика на конкретную дату (выходной/другие часы)."""

    __tablename__ = "schedule_exceptions"

    id: Mapped[int] = mapped_column(primary_key=True)
    date: Mapped[date_type] = mapped_column(Date, unique=True)
    is_day_off: Mapped[bool] = mapped_column(Boolean, default=True)
    start_time: Mapped[time_type | None] = mapped_column(Time, nullable=True)
    end_time: Mapped[time_type | None] = mapped_column(Time, nullable=True)
