"""Проверка: не «осиротит» ли изменение графика уже подтверждённые записи.

Изменения графика никогда не отменяют записи автоматически — мы только
находим записи, которые перестанут помещаться в новый график, и даём
администратору решить самому (см. handlers/admin/schedule.py).
"""

from datetime import datetime, time, timedelta
from datetime import date as date_type

from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models import Appointment
from app.repositories.appointment_repo import AppointmentRepository
from app.services.slots import WorkWindow

# Насколько далеко вперёд ищем записи при проверке еженедельного графика.
# Клиенты бронируют не дальше чем на 7 дней вперёд, но берём с запасом —
# на случай данных, добавленных вручную (сид, будущие интеграции).
WEEKLY_CONFLICT_LOOKAHEAD_LIMIT = 500


def fits_window(start: time, end: time, window: WorkWindow) -> bool:
    if start < window.start or end > window.end:
        return False
    if window.break_start is not None and window.break_end is not None:
        if start < window.break_end and end > window.break_start:
            return False
    return True


async def find_date_conflicts(
    session: AsyncSession, target_date: date_type, window: WorkWindow | None
) -> list[Appointment]:
    """Записи на `target_date`, которые не поместятся в `window` (None = весь день выходной)."""
    day_start = datetime.combine(target_date, time.min, tzinfo=settings.tzinfo)
    day_end = day_start + timedelta(days=1)
    appointments = await AppointmentRepository(session).list_confirmed_in_range(day_start, day_end)

    if window is None:
        return appointments

    conflicts = []
    for appt in appointments:
        local_start = appt.start_at.astimezone(settings.tzinfo).time()
        local_end = appt.end_at.astimezone(settings.tzinfo).time()
        if not fits_window(local_start, local_end, window):
            conflicts.append(appt)
    return conflicts


async def find_weekday_conflicts(
    session: AsyncSession, weekday: int, window: WorkWindow | None
) -> list[Appointment]:
    """Будущие записи на день недели `weekday` (0=Пн), не помещающиеся в `window`."""
    now = datetime.now(settings.tzinfo)
    upcoming = await AppointmentRepository(session).list_upcoming(now, limit=WEEKLY_CONFLICT_LOOKAHEAD_LIMIT)

    conflicts = []
    for appt in upcoming:
        local_start_dt = appt.start_at.astimezone(settings.tzinfo)
        if local_start_dt.weekday() != weekday:
            continue
        if window is None:
            conflicts.append(appt)
            continue
        local_end = appt.end_at.astimezone(settings.tzinfo).time()
        if not fits_window(local_start_dt.time(), local_end, window):
            conflicts.append(appt)
    return conflicts
