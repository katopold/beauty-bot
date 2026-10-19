from calendar import monthrange
from datetime import date, datetime

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup, KeyboardButton, ReplyKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder, ReplyKeyboardBuilder

from app.callbacks import (
    BackCallback,
    CalendarDateCallback,
    CalendarMonthCallback,
    ConfirmCallback,
    MenuCallback,
    MyApptActionCallback,
    NoopCallback,
    PortfolioCategoryCallback,
    ServiceSelectCallback,
    ServiceViewCallback,
    TimeSelectCallback,
)
from app.models import CATEGORY_TITLES, PortfolioCategory, Service
from app.utils.formatting import WEEKDAY_SHORT, format_price


SKIP_PHONE_TEXT = "Пропустить"


def phone_request_keyboard() -> ReplyKeyboardMarkup:
    builder = ReplyKeyboardBuilder()
    builder.row(KeyboardButton(text="📱 Поделиться номером", request_contact=True))
    builder.row(KeyboardButton(text=SKIP_PHONE_TEXT))
    return builder.as_markup(resize_keyboard=True, one_time_keyboard=True)


def main_menu_keyboard(is_admin: bool) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text="💫 Услуги и запись", callback_data=MenuCallback(action="services").pack()))
    builder.row(InlineKeyboardButton(text="📸 Портфолио", callback_data=MenuCallback(action="portfolio").pack()))
    builder.row(InlineKeyboardButton(text="📍 Адрес", callback_data=MenuCallback(action="address").pack()))
    builder.row(InlineKeyboardButton(text="ℹ️ О мастере", callback_data=MenuCallback(action="about").pack()))
    builder.row(InlineKeyboardButton(text="📋 Моя запись", callback_data=MenuCallback(action="my_appt").pack()))
    if is_admin:
        builder.row(InlineKeyboardButton(text="⚙️ Админ-панель", callback_data=MenuCallback(action="admin").pack()))
    return builder.as_markup()


def back_to_main_button() -> InlineKeyboardButton:
    return InlineKeyboardButton(text="🏠 Главное меню", callback_data=MenuCallback(action="main").pack())


def services_list_keyboard(services: list[Service]) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for service in services:
        builder.row(
            InlineKeyboardButton(
                text=f"{service.name} — {format_price(service.price)}",
                callback_data=ServiceViewCallback(service_id=service.id).pack(),
            )
        )
    builder.row(back_to_main_button())
    return builder.as_markup()


def service_card_keyboard(service_id: int) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(
            text="📅 Записаться на эту услугу",
            callback_data=ServiceSelectCallback(service_id=service_id).pack(),
        )
    )
    builder.row(InlineKeyboardButton(text="↩️ К списку услуг", callback_data=MenuCallback(action="services").pack()))
    builder.row(back_to_main_button())
    return builder.as_markup()


def calendar_keyboard(
    year: int,
    month: int,
    availability: dict[date, list | None],
    month_offset: int,
    today: date,
    back_to: str = "services",
) -> InlineKeyboardMarkup:
    """Календарь на месяц. Прошедшие дни некликабельны, выходные (по графику мастера)
    помечены значком 🌙, дни без единого свободного слота — значком 🚫 (оба типа дней
    остаются кликабельными — нажатие поясняет, что дата недоступна)."""
    builder = InlineKeyboardBuilder()

    noop = NoopCallback().pack()
    builder.row(*(InlineKeyboardButton(text=WEEKDAY_SHORT[i], callback_data=noop) for i in range(7)))

    first_weekday, days_in_month = monthrange(year, month)  # monthrange: понедельник = 0
    cells: list[InlineKeyboardButton] = [InlineKeyboardButton(text=" ", callback_data=noop) for _ in range(first_weekday)]

    for day_num in range(1, days_in_month + 1):
        current = date(year, month, day_num)
        if current < today:
            cells.append(InlineKeyboardButton(text=str(day_num), callback_data=noop))
            continue
        slots = availability.get(current)
        if slots is None:
            text = f"{day_num}🌙"
        elif slots == []:
            text = f"{day_num}🚫"
        else:
            text = str(day_num)
        cells.append(
            InlineKeyboardButton(
                text=text, callback_data=CalendarDateCallback(year=year, month=month, day=day_num).pack()
            )
        )

    while len(cells) % 7 != 0:
        cells.append(InlineKeyboardButton(text=" ", callback_data=noop))

    for i in range(0, len(cells), 7):
        builder.row(*cells[i : i + 7])

    nav_row = []
    if month_offset == 1:
        nav_row.append(InlineKeyboardButton(text="◀️ Текущий месяц", callback_data=CalendarMonthCallback(offset=0).pack()))
    else:
        nav_row.append(InlineKeyboardButton(text="Следующий месяц ▶️", callback_data=CalendarMonthCallback(offset=1).pack()))
    builder.row(*nav_row)

    if back_to == "my_appt":
        back_button = InlineKeyboardButton(text="↩️ К записи", callback_data=BackCallback(to="my_appt").pack())
    else:
        back_button = InlineKeyboardButton(text="↩️ К списку услуг", callback_data=MenuCallback(action="services").pack())
    builder.row(back_button)
    builder.row(back_to_main_button())
    return builder.as_markup()


def time_selection_keyboard(slots: list[datetime]) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    row: list[InlineKeyboardButton] = []
    for slot in slots:
        row.append(
            InlineKeyboardButton(text=slot.strftime("%H:%M"), callback_data=TimeSelectCallback(hhmm=slot.strftime("%H%M")).pack())
        )
        if len(row) == 3:
            builder.row(*row)
            row = []
    if row:
        builder.row(*row)
    builder.row(InlineKeyboardButton(text="↩️ Другая дата", callback_data=BackCallback(to="date").pack()))
    builder.row(back_to_main_button())
    return builder.as_markup()


def confirm_keyboard() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text="✅ Подтвердить", callback_data=ConfirmCallback(action="confirm").pack()))
    builder.row(
        InlineKeyboardButton(text="↩️ Назад", callback_data=ConfirmCallback(action="back").pack()),
        InlineKeyboardButton(text="❌ Отмена", callback_data=ConfirmCallback(action="cancel").pack()),
    )
    return builder.as_markup()


def after_booking_keyboard() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.row(back_to_main_button())
    return builder.as_markup()


def portfolio_categories_keyboard() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for category in PortfolioCategory:
        builder.row(
            InlineKeyboardButton(
                text=CATEGORY_TITLES[category],
                callback_data=PortfolioCategoryCallback(category=category.value).pack(),
            )
        )
    builder.row(back_to_main_button())
    return builder.as_markup()


def portfolio_empty_category_keyboard() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text="↩️ К категориям", callback_data=MenuCallback(action="portfolio").pack()))
    builder.row(back_to_main_button())
    return builder.as_markup()


def portfolio_gallery_keyboard(category: PortfolioCategory, index: int, total: int) -> InlineKeyboardMarkup:
    """Клавиатура галереи: одно фото на экран (то самое сообщение, что уже показано),
    пролистывание меняет фото в том же сообщении (editMessageMedia), новых сообщений не создаёт."""
    builder = InlineKeyboardBuilder()
    nav_row = []
    if index > 0:
        nav_row.append(
            InlineKeyboardButton(
                text="⬅️ Пред.", callback_data=PortfolioCategoryCallback(category=category.value, index=index - 1).pack()
            )
        )
    if index < total - 1:
        nav_row.append(
            InlineKeyboardButton(
                text="След. ➡️", callback_data=PortfolioCategoryCallback(category=category.value, index=index + 1).pack()
            )
        )
    if nav_row:
        builder.row(*nav_row)
    builder.row(InlineKeyboardButton(text="↩️ К категориям", callback_data=MenuCallback(action="portfolio").pack()))
    builder.row(back_to_main_button())
    return builder.as_markup()


def address_keyboard(map_url: str) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text="📍 Открыть на карте", url=map_url))
    builder.row(back_to_main_button())
    return builder.as_markup()


def simple_back_keyboard() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.row(back_to_main_button())
    return builder.as_markup()


def my_appointment_keyboard() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(text="❌ Отменить", callback_data=MyApptActionCallback(action="cancel").pack()),
        InlineKeyboardButton(text="🔄 Перенести", callback_data=MyApptActionCallback(action="reschedule").pack()),
    )
    builder.row(back_to_main_button())
    return builder.as_markup()


def cancel_confirm_keyboard() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(text="✅ Да, отменить", callback_data=MyApptActionCallback(action="cancel_confirm").pack()),
        InlineKeyboardButton(text="↩️ Нет", callback_data=MyApptActionCallback(action="cancel_abort").pack()),
    )
    return builder.as_markup()


def no_active_appointment_keyboard() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text="💫 Услуги и запись", callback_data=MenuCallback(action="services").pack()))
    builder.row(back_to_main_button())
    return builder.as_markup()
