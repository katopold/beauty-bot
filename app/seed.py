"""Наполнение БД демонстрационными данными.

Запуск: python -m app.seed
Предполагается, что миграции Alembic уже применены (таблицы существуют).
Скрипт идемпотентен: если бизнес-профиль уже создан, повторный запуск ничего не делает.
"""

import asyncio
from datetime import datetime, time, timedelta
from urllib.parse import quote

from app.config import settings
from app.database import async_session_maker
from app.models import Appointment, AppointmentStatus, BusinessProfile, Service, User, WorkingSchedule

DEMO_SERVICES = [
    dict(
        name="Классическое наращивание",
        description="Натуральный эффект с аккуратным удлинением ресниц.",
        price=2500,
        duration_minutes=120,
    ),
    dict(
        name="2D",
        description="Объёмный эффект из пучков по 2 реснички — выразительный, но естественный взгляд.",
        price=2800,
        duration_minutes=135,
    ),
    dict(
        name="3D",
        description="Максимальный объём из пучков по 3 реснички для яркого, выразительного взгляда.",
        price=3200,
        duration_minutes=150,
    ),
    dict(
        name="Ламинирование ресниц",
        description="Уход и укладка натуральных ресниц: объём, изгиб и блеск без наращивания.",
        price=2000,
        duration_minutes=60,
    ),
]

WORKDAY = dict(start_time=time(10, 0), end_time=time(19, 0), break_start=time(14, 0), break_end=time(15, 0), is_day_off=False)
SATURDAY = dict(start_time=time(11, 0), end_time=time(16, 0), break_start=None, break_end=None, is_day_off=False)
SUNDAY = dict(start_time=None, end_time=None, break_start=None, break_end=None, is_day_off=True)

WEEK_SCHEDULE = {0: WORKDAY, 1: WORKDAY, 2: WORKDAY, 3: WORKDAY, 4: WORKDAY, 5: SATURDAY, 6: SUNDAY}

DEMO_CLIENTS = [
    dict(telegram_id=999000001, username="anna_demo", full_name="Анна"),
    dict(telegram_id=999000002, username="maria_demo", full_name="Мария"),
    dict(telegram_id=999000003, username="elena_demo", full_name="Елена"),
]


async def seed() -> None:
    async with async_session_maker() as session:
        existing_profile = await session.get(BusinessProfile, 1)
        if existing_profile is not None:
            print("Демо-данные уже загружены — пропускаю (BusinessProfile с id=1 уже существует).")
            return

        city = "Екатеринбург"
        address = "ул. Примерная, 10"
        map_query = quote(f"{city}, {address}")
        session.add(
            BusinessProfile(
                id=1,
                master_name="Molly",
                city=city,
                address=address,
                about_text=(
                    "Molly — мастер по наращиванию ресниц.\n\n"
                    "Работаю в Екатеринбурге.\n"
                    "Специализация — естественные и объёмные эффекты.\n\n"
                    "Для записи используйте кнопку «Записаться»."
                ),
                map_url=f"https://yandex.ru/maps/?text={map_query}",
            )
        )

        services: dict[str, Service] = {}
        for order, data in enumerate(DEMO_SERVICES):
            service = Service(sort_order=order, **data)
            session.add(service)
            services[data["name"]] = service

        for weekday, params in WEEK_SCHEDULE.items():
            session.add(WorkingSchedule(weekday=weekday, **params))

        users: dict[str, User] = {}
        for data in DEMO_CLIENTS:
            user = User(**data)
            session.add(user)
            users[data["full_name"]] = user

        await session.flush()

        now = datetime.now(settings.tzinfo)
        today = now.date()
        tomorrow = today + timedelta(days=1)
        classic = services["Классическое наращивание"]

        demo_appointments = [
            (users["Анна"], today, time(13, 0)),
            (users["Мария"], tomorrow, time(11, 0)),
            (users["Елена"], tomorrow, time(16, 0)),
        ]
        for user, day, start_time in demo_appointments:
            start_at = datetime.combine(day, start_time, tzinfo=settings.tzinfo)
            end_at = start_at + timedelta(minutes=classic.duration_minutes)
            session.add(
                Appointment(
                    user=user,
                    service=classic,
                    start_at=start_at,
                    end_at=end_at,
                    price_at_booking=classic.price,
                    status=AppointmentStatus.CONFIRMED,
                )
            )

        await session.commit()
        print("Демо-данные успешно загружены: услуги, расписание, бизнес-профиль, демо-клиенты и демо-записи.")


if __name__ == "__main__":
    asyncio.run(seed())
