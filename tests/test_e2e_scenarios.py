"""Сквозные сценарии через реальный aiogram Dispatcher.

Telegram Bot API подменяется фейковой сессией (без сети), но диспетчер,
роутеры, FSM, фильтры и обращения к БД — настоящие. Это ближе всего к
`Обновлять бота вручную и проверять`, что описано в ТЗ (раздел 30), без
необходимости в реальном Telegram-аккаунте.
"""

from datetime import datetime, timezone

import pytest
from aiogram import Bot, Dispatcher
from aiogram.client.session.base import BaseSession
from aiogram.exceptions import TelegramBadRequest
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import CallbackQuery, Chat, Contact, Message, PhotoSize, Update
from aiogram.types import User as TgUser

from app.callbacks import (
    AdminApptCallback,
    AdminApptCancelCallback,
    AdminApptListCallback,
    AdminCalendarMonthCallback,
    AdminDayAppointmentsCallback,
    AdminExceptionDeleteCallback,
    AdminExceptionKindCallback,
    AdminMenuCallback,
    AdminPortfolioAddCallback,
    AdminProfileEditCallback,
    AdminScheduleActionCallback,
    AdminScheduleWeekdayCallback,
    AdminServiceEditCallback,
    CalendarDateCallback,
    CalendarMonthCallback,
    ConfirmCallback,
    MenuCallback,
    MyApptActionCallback,
    PortfolioCategoryCallback,
    ServiceSelectCallback,
    ServiceViewCallback,
    TimeSelectCallback,
)
from app.handlers.admin import admin_router
from app.handlers.client import client_router
from app.models import AppointmentStatus, BusinessProfile, PortfolioCategory, PortfolioItem, Service
from app.repositories.appointment_repo import AppointmentRepository
from app.repositories.portfolio_repo import PortfolioRepository
from app.repositories.schedule_repo import ScheduleRepository
from app.repositories.service_repo import ServiceRepository
from app.repositories.user_repo import UserRepository


class FakeSession(BaseSession):
    """Ловит все вызовы Telegram Bot API и возвращает правдоподобные ответы, не делая сетевых запросов."""

    def __init__(self) -> None:
        super().__init__()
        self.calls: list[str] = []
        self.sent_methods: list = []
        self._next_id = 1000
        # Отслеживаем, какие message_id сейчас фото-сообщения — чтобы честно
        # эмулировать реальное ограничение Telegram: editMessageText на фото не работает
        # (именно так и проявлялся баг с "лишним сообщением поверх альбома").
        self.photo_message_ids: set[int] = set()

    async def close(self) -> None:
        return None

    async def stream_content(self, *args, **kwargs):  # pragma: no cover - не используется в тестах
        raise NotImplementedError

    async def make_request(self, bot: Bot, method, timeout=None):
        name = type(method).__name__
        self.calls.append(name)
        self.sent_methods.append(method)

        if name == "AnswerCallbackQuery":
            return True
        if name == "DeleteMessage":
            self.photo_message_ids.discard(getattr(method, "message_id", None))
            return True
        if name == "GetMe":
            return TgUser(id=1, is_bot=True, first_name="Molly Lash Bot", username="molly_lash_bot")
        if name == "EditMessageText" and getattr(method, "message_id", None) in self.photo_message_ids:
            raise TelegramBadRequest(method=method, message="there is no text in the message to edit")

        chat_id = getattr(method, "chat_id", 1)

        if name == "SendMediaGroup":
            messages = []
            for _ in getattr(method, "media", []):
                self._next_id += 1
                self.photo_message_ids.add(self._next_id)
                messages.append(Message(message_id=self._next_id, date=datetime.now(timezone.utc), chat=Chat(id=chat_id, type="private")))
            return messages

        if name == "EditMessageMedia":
            mid = getattr(method, "message_id", None)
            if mid is not None:
                self.photo_message_ids.add(mid)
            return Message(message_id=mid or 0, date=datetime.now(timezone.utc), chat=Chat(id=chat_id, type="private"))

        self._next_id += 1
        if name == "SendPhoto":
            self.photo_message_ids.add(self._next_id)
        return Message(
            message_id=self._next_id,
            date=datetime.now(timezone.utc),
            chat=Chat(id=chat_id, type="private"),
            text=getattr(method, "text", None) or getattr(method, "caption", None),
        )


class _SessionHolder:
    """Позволяет middleware брать актуальную сессию текущего теста без пересоздания диспетчера."""

    session = None


class InjectSessionMiddleware:
    """Тестовый аналог DbSessionMiddleware: прокидывает уже открытую тестовую сессию вместо новой."""

    def __init__(self, holder: _SessionHolder):
        self.holder = holder

    async def __call__(self, handler, event, data):
        data["session"] = self.holder.session
        return await handler(event, data)


# Роутеры aiogram — одноразовые объекты (нельзя подключить к двум диспетчерам),
# поэтому Dispatcher и Bot создаются один раз на модуль, а тестовая БД-сессия
# и FSM-хранилище сбрасываются перед каждым тестом отдельной fixture ниже.


@pytest.fixture(scope="module")
def fake_session() -> FakeSession:
    return FakeSession()


@pytest.fixture(scope="module")
def bot(fake_session: FakeSession) -> Bot:
    return Bot(token="123456:TEST-TOKEN-NOT-REAL", session=fake_session)


@pytest.fixture(scope="module")
def session_holder() -> _SessionHolder:
    return _SessionHolder()


@pytest.fixture(scope="module")
def dp(session_holder: _SessionHolder) -> Dispatcher:
    dispatcher = Dispatcher(storage=MemoryStorage())
    dispatcher.update.middleware(InjectSessionMiddleware(session_holder))
    dispatcher.include_router(client_router)
    dispatcher.include_router(admin_router)
    return dispatcher


@pytest.fixture(autouse=True)
def _bind_session(session, session_holder: _SessionHolder, dp: Dispatcher):
    session_holder.session = session
    dp.storage.storage.clear()  # сброс FSM-состояний между тестами


@pytest.fixture(scope="module", autouse=True)
def _admin_settings():
    """IsAdmin-фильтр читает settings.admin_ids — временно добавляем тестового админа."""
    from app.config import settings

    original = settings.admin_ids_raw
    extra = str(ADMIN_ID)
    settings.admin_ids_raw = f"{original},{extra}" if original else extra
    yield
    settings.admin_ids_raw = original


CLIENT_ID = 555000111
ADMIN_ID = 777000222

CLIENT_USER = TgUser(id=CLIENT_ID, is_bot=False, first_name="Тест", username="test_client")
ADMIN_USER = TgUser(id=ADMIN_ID, is_bot=False, first_name="Мастер", username="master_admin")
CHAT = Chat(id=CLIENT_ID, type="private")
ADMIN_CHAT = Chat(id=ADMIN_ID, type="private")

_update_id = 0
_message_id = 0


def _next_update_id() -> int:
    global _update_id
    _update_id += 1
    return _update_id


def _next_message_id() -> int:
    global _message_id
    _message_id += 1
    return _message_id


def make_message(text: str, user: TgUser = CLIENT_USER, chat: Chat = CHAT, photo=None, contact=None) -> Message:
    return Message(
        message_id=_next_message_id(),
        date=datetime.now(timezone.utc),
        chat=chat,
        from_user=user,
        text=text if photo is None and contact is None else None,
        photo=photo,
        contact=contact,
        caption=text if photo is not None else None,
    )


def make_callback(data: str, source_message: Message, user: TgUser = CLIENT_USER) -> CallbackQuery:
    return CallbackQuery(
        id=str(_next_update_id()),
        from_user=user,
        chat_instance="test-chat-instance",
        data=data,
        message=source_message,
    )


async def feed_message(
    dp: Dispatcher, bot: Bot, text: str | None, user: TgUser = CLIENT_USER, chat: Chat = CHAT, photo=None, contact=None
) -> Message:
    msg = make_message(text, user=user, chat=chat, photo=photo, contact=contact)
    await dp.feed_update(bot, Update(update_id=_next_update_id(), message=msg))
    return msg


async def feed_callback(dp: Dispatcher, bot: Bot, data, source_message: Message, user: TgUser = CLIENT_USER) -> CallbackQuery:
    packed = data.pack() if hasattr(data, "pack") else data
    cq = make_callback(packed, source_message, user=user)
    await dp.feed_update(bot, Update(update_id=_next_update_id(), callback_query=cq))
    return cq


async def _seed_minimal(session):
    session.add(
        BusinessProfile(
            id=1,
            master_name="Molly",
            city="Екатеринбург",
            address="ул. Примерная, 10",
            about_text="Molly — мастер по наращиванию ресниц.",
            map_url="https://yandex.ru/maps/?text=test",
        )
    )
    service = Service(name="Классическое наращивание", description="Описание", price=2500, duration_minutes=120)
    session.add(service)
    await session.commit()
    return service


@pytest.mark.asyncio
async def test_full_client_booking_flow(session, working_schedule, dp, bot, fake_session):
    service = await _seed_minimal(session)

    root_msg = await feed_message(dp, bot, "/start")
    assert fake_session.calls[-1] == "SendMessage"  # /start ответил приветствием без ошибок

    # Клиент открывает "Услуги и запись"
    cq1 = await feed_callback(dp, bot, MenuCallback(action="services"), root_msg)
    # Открывает карточку услуги и нажимает "Записаться на эту услугу"
    cq1b = await feed_callback(dp, bot, ServiceViewCallback(service_id=service.id), cq1.message)
    cq2 = await feed_callback(dp, bot, ServiceSelectCallback(service_id=service.id), cq1b.message)

    # Определяем реальный доступный слот через репозиторий, чтобы тест не зависел от текущего часа
    from datetime import date as date_type, timedelta

    from app.config import settings
    from app.services.slots import get_available_slots

    target_date = date_type.today() + timedelta(days=1)  # берём "завтра", чтобы не упереться в прошедшее время
    now = datetime.now(settings.tzinfo)
    slots = await get_available_slots(session, service, target_date, now, settings.tzinfo)
    assert slots, "на завтра должны быть свободные слоты при пустом расписании"
    chosen_slot = slots[0]

    # Выбирает дату в календаре
    cq3 = await feed_callback(
        dp, bot, CalendarDateCallback(year=target_date.year, month=target_date.month, day=target_date.day), cq2.message
    )

    cq4 = await feed_callback(dp, bot, TimeSelectCallback(hhmm=chosen_slot.strftime("%H%M")), cq3.message)
    cq5 = await feed_callback(dp, bot, ConfirmCallback(action="confirm"), cq4.message)

    # Запись должна появиться в БД
    user = await UserRepository(session).get_by_telegram_id(CLIENT_ID)
    assert user is not None
    appt_repo = AppointmentRepository(session)
    appt = await appt_repo.get_nearest_active_for_user(user.id, now)
    assert appt is not None
    assert appt.service_id == service.id
    assert appt.start_at == chosen_slot
    assert appt.status == AppointmentStatus.CONFIRMED


@pytest.mark.asyncio
async def test_cancel_frees_slot_and_allows_rebooking(session, working_schedule, dp, bot):
    service = await _seed_minimal(session)

    from datetime import date as date_type, timedelta

    from app.config import settings
    from app.services.booking import create_appointment

    user = await UserRepository(session).get_or_create(CLIENT_ID, "test_client", "Тест")
    await session.commit()

    target_date = date_type.today() + timedelta(days=1)
    start_at = datetime.combine(target_date, datetime.min.time(), tzinfo=settings.tzinfo).replace(hour=12, minute=0)
    appointment = await create_appointment(session, user, service, start_at)

    root_msg = await feed_message(dp, bot, "/start")
    cq1 = await feed_callback(dp, bot, MenuCallback(action="my_appt"), root_msg)
    cq2 = await feed_callback(dp, bot, MyApptActionCallback(action="cancel"), cq1.message)
    await feed_callback(dp, bot, MyApptActionCallback(action="cancel_confirm"), cq2.message)

    appt_repo = AppointmentRepository(session)
    refreshed = await appt_repo.get(appointment.id)
    assert refreshed.status == AppointmentStatus.CANCELLED

    now = datetime.now(settings.tzinfo)
    assert await appt_repo.get_nearest_active_for_user(user.id, now) is None
    # Слот свободен -> можно забронировать заново
    new_appt = await create_appointment(session, user, service, start_at)
    assert new_appt.id is not None


@pytest.mark.asyncio
async def test_reschedule_via_ui_frees_old_slot_and_occupies_new(session, working_schedule, dp, bot):
    """Полный сценарий кнопки «🔄 Перенести»: Моя запись -> Перенести -> дата -> время -> подтвердить."""
    service = await _seed_minimal(session)

    from datetime import date as date_type, timedelta

    from app.config import settings
    from app.services.booking import create_appointment
    from app.services.slots import get_available_slots

    user = await UserRepository(session).get_or_create(CLIENT_ID, "test_client", "Тест")
    await session.commit()

    old_date = date_type.today() + timedelta(days=1)
    old_start = datetime.combine(old_date, datetime.min.time(), tzinfo=settings.tzinfo).replace(hour=12, minute=0)
    appointment = await create_appointment(session, user, service, old_start)

    root_msg = await feed_message(dp, bot, "/start")
    cq1 = await feed_callback(dp, bot, MenuCallback(action="my_appt"), root_msg)
    cq2 = await feed_callback(dp, bot, MyApptActionCallback(action="reschedule"), cq1.message)
    # Переносим на послезавтра, чтобы точно не совпасть со старым слотом
    new_date = date_type.today() + timedelta(days=2)
    cq3 = await feed_callback(
        dp, bot, CalendarDateCallback(year=new_date.year, month=new_date.month, day=new_date.day), cq2.message
    )

    now = datetime.now(settings.tzinfo)
    new_slots = await get_available_slots(session, service, new_date, now, settings.tzinfo, exclude_appointment_id=appointment.id)
    assert new_slots
    chosen = new_slots[0]

    cq4 = await feed_callback(dp, bot, TimeSelectCallback(hhmm=chosen.strftime("%H%M")), cq3.message)
    await feed_callback(dp, bot, ConfirmCallback(action="confirm"), cq4.message)

    appt_repo = AppointmentRepository(session)
    refreshed = await appt_repo.get(appointment.id)
    assert refreshed.status == AppointmentStatus.CONFIRMED
    assert refreshed.start_at == chosen
    assert refreshed.start_at != old_start

    # Старый слот снова свободен
    another = await create_appointment(session, user, service, old_start)
    assert another.id is not None
    # Новый слот занят перенесённой записью
    new_end = chosen + timedelta(minutes=service.duration_minutes)
    assert await appt_repo.has_overlap(chosen, new_end)


@pytest.mark.asyncio
async def test_admin_can_view_appointments_and_change_price(session, working_schedule, dp, bot):
    service = await _seed_minimal(session)

    from app.config import settings
    from app.services.booking import create_appointment

    client_user = await UserRepository(session).get_or_create(CLIENT_ID, "test_client", "Клиент Тест")
    await session.commit()
    today_start = datetime.now(settings.tzinfo).replace(hour=11, minute=0, second=0, microsecond=0)
    await create_appointment(session, client_user, service, today_start)

    root_msg = await feed_message(dp, bot, "/start", user=ADMIN_USER, chat=ADMIN_CHAT)
    cq1 = await feed_callback(dp, bot, MenuCallback(action="admin"), root_msg, user=ADMIN_USER)
    cq2 = await feed_callback(dp, bot, AdminMenuCallback(action="appts"), cq1.message, user=ADMIN_USER)
    await feed_callback(dp, bot, AdminApptListCallback(scope="upcoming"), cq2.message, user=ADMIN_USER)

    # Меняем цену услуги через FSM
    cq3 = await feed_callback(dp, bot, AdminMenuCallback(action="services"), cq2.message, user=ADMIN_USER)
    services = await ServiceRepository(session).list_all()
    svc_id = services[0].id
    cq4 = await feed_callback(
        dp, bot, AdminServiceEditCallback(service_id=svc_id, field="price"), cq3.message, user=ADMIN_USER
    )
    await feed_message(dp, bot, "3000", user=ADMIN_USER, chat=ADMIN_CHAT)

    updated = await ServiceRepository(session).get(svc_id)
    assert updated.price == 3000


@pytest.mark.asyncio
async def test_admin_test_reminder_sends_two_messages(session, working_schedule, dp, bot, fake_session):
    await _seed_minimal(session)
    root_msg = await feed_message(dp, bot, "/start", user=ADMIN_USER, chat=ADMIN_CHAT)
    cq1 = await feed_callback(dp, bot, MenuCallback(action="admin"), root_msg, user=ADMIN_USER)
    before = len([c for c in fake_session.calls if c == "SendMessage"])
    await feed_callback(dp, bot, AdminMenuCallback(action="test_reminder"), cq1.message, user=ADMIN_USER)
    after = len([c for c in fake_session.calls if c == "SendMessage"])
    assert after - before == 4  # 2 заголовка + 2 текста напоминаний


@pytest.mark.asyncio
async def test_admin_portfolio_add_photo_flow(session, working_schedule, dp, bot):
    await _seed_minimal(session)
    root_msg = await feed_message(dp, bot, "/start", user=ADMIN_USER, chat=ADMIN_CHAT)
    cq1 = await feed_callback(dp, bot, MenuCallback(action="admin"), root_msg, user=ADMIN_USER)
    cq2 = await feed_callback(dp, bot, AdminMenuCallback(action="portfolio"), cq1.message, user=ADMIN_USER)
    cq3 = await feed_callback(
        dp, bot, AdminPortfolioAddCallback(category=PortfolioCategory.CLASSIC.value), cq2.message, user=ADMIN_USER
    )

    photo = [PhotoSize(file_id="fake_file_id_123", file_unique_id="uniq123", width=800, height=800)]
    await feed_message(dp, bot, None, user=ADMIN_USER, chat=ADMIN_CHAT, photo=photo)
    await feed_message(dp, bot, "Отличный результат!", user=ADMIN_USER, chat=ADMIN_CHAT)

    items = await PortfolioRepository(session).list_by_category(PortfolioCategory.CLASSIC)
    assert len(items) == 1
    assert items[0].file_id == "fake_file_id_123"
    assert items[0].caption == "Отличный результат!"


@pytest.mark.asyncio
async def test_schedule_change_conflict_requires_explicit_confirm(session, working_schedule, dp, bot):
    """Сценарий из обсуждения: запись на 15:00, мастер хочет сделать день с 16:00.

    Ожидание: сохранение без подтверждения НЕ применяет изменение (запись важнее
    молчаливой перезаписи графика), а после явного подтверждения — применяет,
    и старая запись остаётся как есть (её никто не трогает).
    """
    service = await _seed_minimal(session)
    from datetime import date as date_type, timedelta

    from app.config import settings
    from app.services.booking import create_appointment

    client_user = await UserRepository(session).get_or_create(CLIENT_ID, "test_client", "Анна")
    await session.commit()

    monday = date_type.today()
    while monday.weekday() != 0:
        monday += timedelta(days=1)
    if monday <= datetime.now(settings.tzinfo).date():
        monday += timedelta(days=7)
    existing_start = datetime.combine(monday, datetime.min.time(), tzinfo=settings.tzinfo).replace(hour=15, minute=0)
    await create_appointment(session, client_user, service, existing_start)  # 15:00-17:00

    root_msg = await feed_message(dp, bot, "/start", user=ADMIN_USER, chat=ADMIN_CHAT)
    cq1 = await feed_callback(dp, bot, MenuCallback(action="admin"), root_msg, user=ADMIN_USER)
    cq2 = await feed_callback(dp, bot, AdminMenuCallback(action="schedule_edit"), cq1.message, user=ADMIN_USER)
    cq3 = await feed_callback(dp, bot, AdminScheduleWeekdayCallback(weekday=0), cq2.message, user=ADMIN_USER)
    cq4 = await feed_callback(
        dp, bot, AdminScheduleActionCallback(weekday=0, action="edit_hours"), cq3.message, user=ADMIN_USER
    )
    msg1 = await feed_message(dp, bot, "16:00", user=ADMIN_USER, chat=ADMIN_CHAT)
    msg2 = await feed_message(dp, bot, "19:00", user=ADMIN_USER, chat=ADMIN_CHAT)

    # После ввода часов график ЕЩЁ не должен поменяться — есть конфликтующая запись
    ws = await ScheduleRepository(session).get_for_weekday(0)
    assert ws.start_time.strftime("%H:%M") == "10:00"

    # Подтверждаем изменение, несмотря на предупреждение
    await feed_callback(dp, bot, AdminMenuCallback(action="schedule_apply_pending"), msg2, user=ADMIN_USER)

    ws = await ScheduleRepository(session).get_for_weekday(0)
    assert ws.start_time.strftime("%H:%M") == "16:00"
    assert ws.end_time.strftime("%H:%M") == "19:00"

    # Старая запись на 15:00 никуда не делась — её никто не тронул
    appt_repo = AppointmentRepository(session)
    refreshed = await appt_repo.get_nearest_active_for_user(client_user.id, datetime.now(settings.tzinfo))
    assert refreshed is not None
    assert refreshed.start_at == existing_start
    assert refreshed.status == AppointmentStatus.CONFIRMED


@pytest.mark.asyncio
async def test_schedule_change_without_conflict_applies_immediately(session, working_schedule, dp, bot):
    root_msg = await feed_message(dp, bot, "/start", user=ADMIN_USER, chat=ADMIN_CHAT)
    cq1 = await feed_callback(dp, bot, MenuCallback(action="admin"), root_msg, user=ADMIN_USER)
    cq2 = await feed_callback(dp, bot, AdminMenuCallback(action="schedule_edit"), cq1.message, user=ADMIN_USER)
    cq3 = await feed_callback(dp, bot, AdminScheduleWeekdayCallback(weekday=1), cq2.message, user=ADMIN_USER)
    cq4 = await feed_callback(
        dp, bot, AdminScheduleActionCallback(weekday=1, action="edit_hours"), cq3.message, user=ADMIN_USER
    )
    await feed_message(dp, bot, "09:00", user=ADMIN_USER, chat=ADMIN_CHAT)
    await feed_message(dp, bot, "18:00", user=ADMIN_USER, chat=ADMIN_CHAT)

    ws = await ScheduleRepository(session).get_for_weekday(1)
    assert ws.start_time.strftime("%H:%M") == "09:00"
    assert ws.end_time.strftime("%H:%M") == "18:00"


@pytest.mark.asyncio
async def test_one_off_holiday_exception_blocks_that_date_only(session, working_schedule, dp, bot):
    """Разовый выходной (праздник) на конкретную дату — остальные дни недели не затрагивает."""
    from datetime import date as date_type, timedelta

    from app.config import settings
    from app.services.slots import get_available_slots

    service = await _seed_minimal(session)
    holiday = date_type.today() + timedelta(days=10)
    while holiday.weekday() == 6:  # избегаем воскресенья, которое и так выходной
        holiday += timedelta(days=1)

    root_msg = await feed_message(dp, bot, "/start", user=ADMIN_USER, chat=ADMIN_CHAT)
    cq1 = await feed_callback(dp, bot, MenuCallback(action="admin"), root_msg, user=ADMIN_USER)
    cq2 = await feed_callback(dp, bot, AdminMenuCallback(action="exceptions"), cq1.message, user=ADMIN_USER)
    cq3 = await feed_callback(dp, bot, AdminMenuCallback(action="exception_add"), cq2.message, user=ADMIN_USER)
    msg1 = await feed_message(dp, bot, holiday.strftime("%d.%m.%Y"), user=ADMIN_USER, chat=ADMIN_CHAT)
    await feed_callback(dp, bot, AdminExceptionKindCallback(kind="day_off"), msg1, user=ADMIN_USER)

    now = datetime.now(settings.tzinfo)
    slots_on_holiday = await get_available_slots(session, service, holiday, now, settings.tzinfo)
    assert slots_on_holiday == []

    day_after = holiday + timedelta(days=1)
    if day_after.weekday() != 6:
        slots_after = await get_available_slots(session, service, day_after, now, settings.tzinfo)
        assert slots_after  # соседний день не затронут


@pytest.mark.asyncio
async def test_exception_day_off_conflict_shows_warning_not_silent_failure(session, working_schedule, dp, bot, fake_session):
    """Регресс на баг: разовый выходной на дату с уже существующей записью раньше падал
    молча (MissingGreenlet при обращении к appt.user/appt.service без eager loading в
    list_confirmed_in_range) — админ не видел ни ошибки, ни предупреждения, ничего.
    Теперь должно показываться предупреждение с конфликтующей записью."""
    from datetime import date as date_type, timedelta

    from app.config import settings
    from app.repositories.appointment_repo import AppointmentRepository
    from app.repositories.schedule_repo import ScheduleRepository
    from app.services.booking import create_appointment

    service = await _seed_minimal(session)
    client_user = await UserRepository(session).get_or_create(CLIENT_ID, "test_client", "Анна")
    await session.commit()

    target_day = date_type.today() + timedelta(days=10)
    while target_day.weekday() == 6:
        target_day += timedelta(days=1)
    start_at = datetime.combine(target_day, datetime.min.time(), tzinfo=settings.tzinfo).replace(hour=11, minute=0)
    appointment = await create_appointment(session, client_user, service, start_at)

    root_msg = await feed_message(dp, bot, "/start", user=ADMIN_USER, chat=ADMIN_CHAT)
    cq1 = await feed_callback(dp, bot, MenuCallback(action="admin"), root_msg, user=ADMIN_USER)
    cq2 = await feed_callback(dp, bot, AdminMenuCallback(action="exceptions"), cq1.message, user=ADMIN_USER)
    cq3 = await feed_callback(dp, bot, AdminMenuCallback(action="exception_add"), cq2.message, user=ADMIN_USER)
    msg1 = await feed_message(dp, bot, target_day.strftime("%d.%m.%Y"), user=ADMIN_USER, chat=ADMIN_CHAT)

    before = len(fake_session.calls)
    cq4 = await feed_callback(dp, bot, AdminExceptionKindCallback(kind="day_off"), msg1, user=ADMIN_USER)
    calls_after = fake_session.calls[before:]
    # Раньше здесь не было вообще никакого вызова API — тихое падение внутри хендлера
    assert calls_after, "хендлер должен был хоть что-то ответить, а не упасть молча"
    assert "AnswerCallbackQuery" in calls_after or "EditMessageText" in calls_after or "SendMessage" in calls_after

    # Исключение ещё не должно быть применено — ждём подтверждения
    schedule_repo = ScheduleRepository(session)
    assert await schedule_repo.get_exception(target_day) is None

    # Запись должна быть всё ещё на месте (никто её не тронул)
    appt_repo = AppointmentRepository(session)
    refreshed = await appt_repo.get(appointment.id)
    assert refreshed.status == AppointmentStatus.CONFIRMED

    # Подтверждаем — теперь исключение применяется
    await feed_callback(dp, bot, AdminMenuCallback(action="schedule_apply_pending"), cq4.message, user=ADMIN_USER)
    exception = await schedule_repo.get_exception(target_day)
    assert exception is not None
    assert exception.is_day_off is True

    # Запись всё ещё не тронута — отмена/перенос остаются на усмотрение админа
    refreshed_after = await appt_repo.get(appointment.id)
    assert refreshed_after.status == AppointmentStatus.CONFIRMED


@pytest.mark.asyncio
async def test_portfolio_stays_in_one_message_and_cleans_up_on_exit(session, working_schedule, dp, bot, fake_session):
    """Портфолио не должно плодить новые сообщения: главный экран — просто список
    категорий (без фото), выбор категории/пролистывание меняет то же самое сообщение
    (editMessageMedia), а уход в другой раздел удаляет фото-сообщение и заменяет его
    текстом — лишних сообщений в чате не остаётся."""
    repo = PortfolioRepository(session)
    for i in range(3):
        await repo.add(PortfolioCategory.CLASSIC, file_id=f"classic_{i}", caption=f"Работа {i}")
    await session.commit()

    root_msg = await feed_message(dp, bot, "/start")

    # 1. Открываем портфолио из текстового меню -> список категорий, без фото,
    #    сообщение просто редактируется на месте (никаких новых сообщений).
    before = len(fake_session.calls)
    await feed_callback(dp, bot, MenuCallback(action="portfolio"), root_msg)
    calls = fake_session.calls[before:]
    assert calls == ["EditMessageText", "AnswerCallbackQuery"]

    # Тестовый харнесс не отслеживает автоматически, каким стало сообщение после
    # _show_photo (в отличие от настоящего Telegram) — поэтому дальше явно эмулируем
    # "сейчас на экране фото-сообщение", чтобы проверить ветку editMessageMedia.
    photo_message = Message(
        message_id=_next_message_id(),
        date=datetime.now(timezone.utc),
        chat=CHAT,
        photo=[PhotoSize(file_id="whatever", file_unique_id="u", width=10, height=10)],
    )

    # 2. Заходим в категорию — сообщение уже фото, значит меняем его НА МЕСТЕ, без новых сообщений.
    before = len(fake_session.calls)
    await feed_callback(dp, bot, PortfolioCategoryCallback(category=PortfolioCategory.CLASSIC.value), photo_message)
    calls = fake_session.calls[before:]
    assert calls == ["EditMessageMedia", "AnswerCallbackQuery"]  # никаких SendPhoto/SendMessage/DeleteMessage

    # 3. Листаем "Следующее фото" — снова редактирование того же сообщения, не новое.
    before = len(fake_session.calls)
    await feed_callback(dp, bot, PortfolioCategoryCallback(category=PortfolioCategory.CLASSIC.value, index=1), photo_message)
    calls = fake_session.calls[before:]
    assert calls == ["EditMessageMedia", "AnswerCallbackQuery"]

    # 4. Уходим в главное меню — фото-сообщение должно быть удалено, а не оставлено в чате.
    before = len(fake_session.calls)
    await feed_callback(dp, bot, MenuCallback(action="main"), photo_message)
    calls = fake_session.calls[before:]
    assert "DeleteMessage" in calls  # старое фото-сообщение подчищено
    assert "SendMessage" in calls  # и заменено обычным текстовым меню


@pytest.mark.asyncio
async def test_portfolio_empty_category_shows_friendly_message(session, working_schedule, dp, bot):
    root_msg = await feed_message(dp, bot, "/start")
    cq1 = await feed_callback(dp, bot, MenuCallback(action="portfolio"), root_msg)
    await feed_callback(dp, bot, PortfolioCategoryCallback(category=PortfolioCategory.LAMINATION.value), cq1.message)
    # Не должно упасть с ошибкой — просто дружелюбное сообщение (проверяется отсутствием исключения)


def _calendar_button_texts(method) -> list[str]:
    keyboard = method.reply_markup
    return [btn.text for row in keyboard.inline_keyboard for btn in row]


def _last_method_with_keyboard(fake_session: "FakeSession"):
    for method in reversed(fake_session.sent_methods):
        if getattr(method, "reply_markup", None) is not None:
            return method
    raise AssertionError("не найдено ни одного сообщения с клавиатурой")


@pytest.mark.asyncio
async def test_calendar_marks_fully_booked_day_with_icon(session, working_schedule, dp, bot, fake_session):
    """Ровно фича из запроса: день, где все рабочие часы заняты записями, помечен значком на кнопке."""
    from datetime import date as date_type, timedelta

    from app.config import settings

    service = await _seed_minimal(session)
    user = await UserRepository(session).get_or_create(999888777, "other_client", "Другой клиент")
    await session.commit()

    # Услуга 2 часа, суббота у нас 11:00-16:00 без перерыва -> ровно 2.5 слота,
    # забронируем все три возможных старта (11:00, 12:00(нет, шаг 30мин)...),
    # проще: бронируем весь рабочий день сплошным интервалом одной длинной "росписью" через несколько записей.
    saturday = date_type.today()
    while saturday.weekday() != 5:
        saturday += timedelta(days=1)
    if saturday <= datetime.now(settings.tzinfo).date():
        saturday += timedelta(days=7)

    tz = settings.tzinfo
    # Занимаем всё окно 11:00-16:00 (суббота) двумя записями подряд по 2.5 часа каждая
    from app.services.booking import create_appointment
    from app.repositories.service_repo import ServiceRepository

    real_service = await ServiceRepository(session).get(service.id)
    slot1_start = datetime.combine(saturday, datetime.min.time(), tzinfo=tz).replace(hour=11, minute=0)
    await create_appointment(session, user, real_service, slot1_start)  # 11:00-13:00
    slot2_start = datetime.combine(saturday, datetime.min.time(), tzinfo=tz).replace(hour=13, minute=0)
    await create_appointment(session, user, real_service, slot2_start)  # 13:00-15:00
    # Остаётся 15:00-16:00 (1 час) — этого не хватит для 2-часовой услуги -> день полностью занят

    root_msg = await feed_message(dp, bot, "/start")
    cq1 = await feed_callback(dp, bot, MenuCallback(action="services"), root_msg)
    cq2 = await feed_callback(dp, bot, ServiceViewCallback(service_id=service.id), cq1.message)
    before = len(fake_session.sent_methods)
    await feed_callback(dp, bot, ServiceSelectCallback(service_id=service.id), cq2.message)
    if saturday.month != datetime.now(tz).month:
        # суббота попала в следующий месяц -> переключаемся
        await feed_callback(dp, bot, CalendarMonthCallback(offset=1), cq2.message)

    calendar_method = _last_method_with_keyboard(fake_session)
    texts = _calendar_button_texts(calendar_method)
    assert f"{saturday.day}🚫" in texts, f"ожидали значок занятости на {saturday.day}, получили кнопки: {texts}"


@pytest.mark.asyncio
async def test_calendar_shows_correct_number_of_days_and_month_switch(session, working_schedule, dp, bot, fake_session):
    from calendar import monthrange
    from datetime import date as date_type

    service = await _seed_minimal(session)
    root_msg = await feed_message(dp, bot, "/start")
    cq1 = await feed_callback(dp, bot, MenuCallback(action="services"), root_msg)
    cq2 = await feed_callback(dp, bot, ServiceViewCallback(service_id=service.id), cq1.message)
    await feed_callback(dp, bot, ServiceSelectCallback(service_id=service.id), cq2.message)

    today = date_type.today()
    days_in_month = monthrange(today.year, today.month)[1]
    texts = _calendar_button_texts(_last_method_with_keyboard(fake_session))
    day_numbers = {t.rstrip("🚫") for t in texts if t.strip() and t.strip() not in ("Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Вс") and "месяц" not in t}
    assert str(days_in_month) in day_numbers
    assert str(days_in_month + 1) not in day_numbers  # дня, которого не существует, быть не должно

    # Переключаемся на следующий месяц и обратно
    cq_next = await feed_callback(dp, bot, CalendarMonthCallback(offset=1), cq2.message)
    next_month_texts = _calendar_button_texts(_last_method_with_keyboard(fake_session))
    assert "◀️ Текущий месяц" in next_month_texts

    await feed_callback(dp, bot, CalendarMonthCallback(offset=0), cq_next.message)
    back_texts = _calendar_button_texts(_last_method_with_keyboard(fake_session))
    assert "Следующий месяц ▶️" in back_texts


@pytest.mark.asyncio
async def test_admin_calendar_marks_day_off_and_appointment_count(session, working_schedule, dp, bot, fake_session):
    from datetime import date as date_type, timedelta

    from app.config import settings
    from app.services.booking import create_appointment

    service = await _seed_minimal(session)
    client_user = await UserRepository(session).get_or_create(CLIENT_ID, "test_client", "Клиент")
    await session.commit()

    # Понедельник с двумя записями -> должен показать счётчик "·2"
    monday = date_type.today() + timedelta(days=1)
    while monday.weekday() != 0:
        monday += timedelta(days=1)
    tz = settings.tzinfo
    await create_appointment(session, client_user, service, datetime.combine(monday, datetime.min.time(), tzinfo=tz).replace(hour=11))
    await create_appointment(session, client_user, service, datetime.combine(monday, datetime.min.time(), tzinfo=tz).replace(hour=16))

    # Ближайшее воскресенье -> выходной по умолчанию, должно быть с 🌙
    sunday = monday
    while sunday.weekday() != 6:
        sunday += timedelta(days=1)

    root_msg = await feed_message(dp, bot, "/start", user=ADMIN_USER, chat=ADMIN_CHAT)
    cq1 = await feed_callback(dp, bot, MenuCallback(action="admin"), root_msg, user=ADMIN_USER)
    cq2 = await feed_callback(dp, bot, AdminMenuCallback(action="appts"), cq1.message, user=ADMIN_USER)
    await feed_callback(dp, bot, AdminMenuCallback(action="appts_calendar"), cq2.message, user=ADMIN_USER)

    texts = _calendar_button_texts(_last_method_with_keyboard(fake_session))
    if monday.month == datetime.now(tz).month:
        assert f"{monday.day}·2" in texts
    if sunday.month == datetime.now(tz).month:
        assert f"{sunday.day}🌙" in texts


@pytest.mark.asyncio
async def test_admin_calendar_day_tap_shows_appointments_and_detail(session, working_schedule, dp, bot):
    from datetime import date as date_type, timedelta

    from app.config import settings
    from app.services.booking import create_appointment

    service = await _seed_minimal(session)
    client_user = await UserRepository(session).get_or_create(CLIENT_ID, "test_client", "Клиент Календарь")
    await session.commit()

    target_day = date_type.today() + timedelta(days=3)
    tz = settings.tzinfo
    appt = await create_appointment(
        session, client_user, service, datetime.combine(target_day, datetime.min.time(), tzinfo=tz).replace(hour=12)
    )

    root_msg = await feed_message(dp, bot, "/start", user=ADMIN_USER, chat=ADMIN_CHAT)
    cq1 = await feed_callback(dp, bot, MenuCallback(action="admin"), root_msg, user=ADMIN_USER)
    cq2 = await feed_callback(dp, bot, AdminMenuCallback(action="appts"), cq1.message, user=ADMIN_USER)
    cq3 = await feed_callback(dp, bot, AdminMenuCallback(action="appts_calendar"), cq2.message, user=ADMIN_USER)

    cq4 = await feed_callback(
        dp, bot, AdminDayAppointmentsCallback(year=target_day.year, month=target_day.month, day=target_day.day), cq3.message,
        user=ADMIN_USER,
    )
    cq5 = await feed_callback(dp, bot, AdminApptCallback(appointment_id=appt.id, scope=f"day{target_day.isoformat()}"), cq4.message, user=ADMIN_USER)

    # "Назад" из детали записи должен вернуть к списку дня, а не упасть
    await feed_callback(
        dp, bot, AdminDayAppointmentsCallback(year=target_day.year, month=target_day.month, day=target_day.day), cq5.message,
        user=ADMIN_USER,
    )
    # "Назад к календарю" должен сработать без ошибок
    await feed_callback(dp, bot, AdminCalendarMonthCallback(year=target_day.year, month=target_day.month), cq4.message, user=ADMIN_USER)


@pytest.mark.asyncio
async def test_admin_can_delete_appointment(session, working_schedule, dp, bot):
    """Админ удаляет (отменяет) запись через карточку — слот освобождается, статус CANCELLED."""
    from datetime import date as date_type, timedelta

    from app.config import settings
    from app.services.booking import create_appointment

    service = await _seed_minimal(session)
    client_user = await UserRepository(session).get_or_create(CLIENT_ID, "test_client", "Клиент на удаление")
    await session.commit()

    target_day = date_type.today() + timedelta(days=2)
    start_at = datetime.combine(target_day, datetime.min.time(), tzinfo=settings.tzinfo).replace(hour=11)
    appt = await create_appointment(session, client_user, service, start_at)

    root_msg = await feed_message(dp, bot, "/start", user=ADMIN_USER, chat=ADMIN_CHAT)
    cq1 = await feed_callback(dp, bot, MenuCallback(action="admin"), root_msg, user=ADMIN_USER)
    cq2 = await feed_callback(dp, bot, AdminMenuCallback(action="appts"), cq1.message, user=ADMIN_USER)
    cq3 = await feed_callback(dp, bot, AdminApptListCallback(scope="upcoming"), cq2.message, user=ADMIN_USER)
    cq4 = await feed_callback(dp, bot, AdminApptCallback(appointment_id=appt.id, scope="upcoming"), cq3.message, user=ADMIN_USER)

    # Кнопка удаления должна вести на подтверждение, а не удалять сразу
    cq5 = await feed_callback(dp, bot, AdminApptCancelCallback(appointment_id=appt.id, scope="upcoming", action="ask"), cq4.message, user=ADMIN_USER)

    appt_repo = AppointmentRepository(session)
    still_confirmed = await appt_repo.get(appt.id)
    assert still_confirmed.status == AppointmentStatus.CONFIRMED  # ещё не удалена, ждём подтверждения

    await feed_callback(dp, bot, AdminApptCancelCallback(appointment_id=appt.id, scope="upcoming", action="confirm"), cq5.message, user=ADMIN_USER)

    deleted = await appt_repo.get(appt.id)
    assert deleted.status == AppointmentStatus.CANCELLED

    # Слот освободился -> можно забронировать заново
    new_appt = await create_appointment(session, client_user, service, start_at)
    assert new_appt.id is not None


@pytest.mark.asyncio
async def test_admin_can_edit_business_profile(session, working_schedule, dp, bot):
    """Админ может создать/изменить данные о мастере через бот, без ручной правки БД."""
    from app.repositories.business_repo import BusinessRepository

    root_msg = await feed_message(dp, bot, "/start", user=ADMIN_USER, chat=ADMIN_CHAT)
    cq1 = await feed_callback(dp, bot, MenuCallback(action="admin"), root_msg, user=ADMIN_USER)

    # Профиля ещё нет -> первое открытие должно создать пустую заготовку, а не упасть
    cq2 = await feed_callback(dp, bot, AdminMenuCallback(action="profile"), cq1.message, user=ADMIN_USER)
    repo = BusinessRepository(session)
    profile = await repo.get()
    assert profile is not None

    cq3 = await feed_callback(dp, bot, AdminProfileEditCallback(field="master_name"), cq2.message, user=ADMIN_USER)
    await feed_message(dp, bot, "Molly", user=ADMIN_USER, chat=ADMIN_CHAT)

    cq4 = await feed_callback(dp, bot, AdminProfileEditCallback(field="city"), cq2.message, user=ADMIN_USER)
    await feed_message(dp, bot, "Екатеринбург", user=ADMIN_USER, chat=ADMIN_CHAT)

    updated = await repo.get()
    assert updated.master_name == "Molly"
    assert updated.city == "Екатеринбург"


@pytest.mark.asyncio
async def test_new_user_is_asked_for_phone_and_sharing_saves_it(session, working_schedule, dp, bot, fake_session):
    """/start у нового клиента сначала спрашивает телефон (необязательно), и только
    после ответа показывает обычное меню."""
    before = len(fake_session.calls)
    await feed_message(dp, bot, "/start")
    calls = fake_session.calls[before:]
    assert calls == ["SendMessage"]  # только запрос телефона, не главное меню

    user = await UserRepository(session).get_by_telegram_id(CLIENT_ID)
    assert user is not None
    assert user.phone is None

    contact = Contact(phone_number="+79991234567", first_name="Тест", user_id=CLIENT_ID)
    before = len(fake_session.calls)
    await feed_message(dp, bot, None, contact=contact)
    calls = fake_session.calls[before:]
    assert calls == ["SendMessage", "SendMessage"]  # "спасибо" + главное меню

    updated = await UserRepository(session).get_by_telegram_id(CLIENT_ID)
    assert updated.phone == "+79991234567"


@pytest.mark.asyncio
async def test_phone_request_can_be_skipped_and_is_not_asked_again(session, working_schedule, dp, bot, fake_session):
    from app.handlers.client.start import PHONE_REQUEST_TEXT

    await feed_message(dp, bot, "/start")
    await feed_message(dp, bot, "Пропустить")

    user = await UserRepository(session).get_by_telegram_id(CLIENT_ID)
    assert user.phone is None
    assert user.phone_skipped is True

    # Второй /start НЕ должен снова спрашивать телефон — сразу главное меню
    before = len(fake_session.sent_methods)
    await feed_message(dp, bot, "/start")
    new_methods = fake_session.sent_methods[before:]
    texts = [getattr(m, "text", None) for m in new_methods]
    assert PHONE_REQUEST_TEXT not in texts


@pytest.mark.asyncio
async def test_admin_appointment_detail_shows_phone(session, working_schedule, dp, bot, fake_session):
    from datetime import date as date_type, timedelta

    from app.config import settings
    from app.services.booking import create_appointment

    service = await _seed_minimal(session)
    user_repo = UserRepository(session)
    client_user = await user_repo.get_or_create(CLIENT_ID, "test_client", "Клиент С Телефоном")
    await user_repo.set_phone(client_user, "+79997654321")
    await session.commit()

    target_day = date_type.today() + timedelta(days=2)
    start_at = datetime.combine(target_day, datetime.min.time(), tzinfo=settings.tzinfo).replace(hour=11)
    appt = await create_appointment(session, client_user, service, start_at)

    root_msg = await feed_message(dp, bot, "/start", user=ADMIN_USER, chat=ADMIN_CHAT)
    cq1 = await feed_callback(dp, bot, MenuCallback(action="admin"), root_msg, user=ADMIN_USER)
    cq2 = await feed_callback(dp, bot, AdminMenuCallback(action="appts"), cq1.message, user=ADMIN_USER)
    cq3 = await feed_callback(dp, bot, AdminApptListCallback(scope="upcoming"), cq2.message, user=ADMIN_USER)
    await feed_callback(dp, bot, AdminApptCallback(appointment_id=appt.id, scope="upcoming"), cq3.message, user=ADMIN_USER)

    method = _last_method_with_keyboard(fake_session)
    text = getattr(method, "text", None) or ""
    assert "+79997654321" in text
    assert "@test_client" in text  # юзернейм клиента тоже должен быть в карточке
