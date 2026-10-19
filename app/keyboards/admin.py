from calendar import monthrange
from datetime import date

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder

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
    AdminPortfolioCatCallback,
    AdminPortfolioDeleteCallback,
    AdminProfileEditCallback,
    AdminScheduleActionCallback,
    AdminScheduleWeekdayCallback,
    AdminServiceCallback,
    AdminServiceEditCallback,
    MenuCallback,
    NoopCallback,
)
from app.models import (
    CATEGORY_TITLES,
    Appointment,
    AppointmentStatus,
    BusinessProfile,
    PortfolioCategory,
    PortfolioItem,
    ScheduleException,
    Service,
    WorkingSchedule,
)
from app.utils.formatting import WEEKDAY_NAMES, WEEKDAY_SHORT, format_date_ru, format_price


def admin_back_button() -> InlineKeyboardButton:
    return InlineKeyboardButton(text="⚙️ Админ-панель", callback_data=MenuCallback(action="admin").pack())


def admin_main_keyboard() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text="📅 Записи", callback_data=AdminMenuCallback(action="appts").pack()))
    builder.row(InlineKeyboardButton(text="🕐 Расписание", callback_data=AdminMenuCallback(action="schedule").pack()))
    builder.row(InlineKeyboardButton(text="💫 Услуги", callback_data=AdminMenuCallback(action="services").pack()))
    builder.row(InlineKeyboardButton(text="📸 Портфолио", callback_data=AdminMenuCallback(action="portfolio").pack()))
    builder.row(InlineKeyboardButton(text="🏢 О мастере", callback_data=AdminMenuCallback(action="profile").pack()))
    builder.row(InlineKeyboardButton(text="🧪 Тестовое напоминание", callback_data=AdminMenuCallback(action="test_reminder").pack()))
    builder.row(InlineKeyboardButton(text="🏠 Главное меню", callback_data=MenuCallback(action="main").pack()))
    return builder.as_markup()


def admin_appts_menu_keyboard() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text="📅 Ближайшие записи", callback_data=AdminApptListCallback(scope="upcoming").pack()))
    builder.row(InlineKeyboardButton(text="🗓 Календарь", callback_data=AdminMenuCallback(action="appts_calendar").pack()))
    builder.row(admin_back_button())
    return builder.as_markup()


def admin_appts_list_keyboard(appointments: list[Appointment], scope: str) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for appt in appointments:
        client_name = appt.user.full_name
        label = f"{appt.start_at.strftime('%H:%M')} — {client_name} — {appt.service.name}"
        builder.row(InlineKeyboardButton(text=label, callback_data=AdminApptCallback(appointment_id=appt.id, scope=scope).pack()))
    builder.row(InlineKeyboardButton(text="↩️ Назад", callback_data=AdminMenuCallback(action="appts").pack()))
    builder.row(admin_back_button())
    return builder.as_markup()


def admin_appt_detail_keyboard(appointment: Appointment, scope: str) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    if appointment.status == AppointmentStatus.CONFIRMED:
        builder.row(
            InlineKeyboardButton(
                text="🗑 Удалить запись",
                callback_data=AdminApptCancelCallback(appointment_id=appointment.id, scope=scope, action="ask").pack(),
            )
        )
    if scope.startswith("day"):
        day = date.fromisoformat(scope[len("day") :])
        back_callback = AdminDayAppointmentsCallback(year=day.year, month=day.month, day=day.day).pack()
    else:
        back_callback = AdminApptListCallback(scope=scope).pack()
    builder.row(InlineKeyboardButton(text="↩️ К списку", callback_data=back_callback))
    builder.row(admin_back_button())
    return builder.as_markup()


def admin_appt_cancel_confirm_keyboard(appointment_id: int, scope: str) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(
            text="✅ Да, удалить",
            callback_data=AdminApptCancelCallback(appointment_id=appointment_id, scope=scope, action="confirm").pack(),
        ),
        InlineKeyboardButton(text="↩️ Отмена", callback_data=AdminApptCallback(appointment_id=appointment_id, scope=scope).pack()),
    )
    return builder.as_markup()


def admin_day_appointments_keyboard(appointments: list[Appointment], target_date: date) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    scope = f"day{target_date.isoformat()}"  # без ":" — он зарезервирован как разделитель callback_data
    for appt in appointments:
        label = f"{appt.start_at.strftime('%H:%M')} — {appt.user.full_name} — {appt.service.name}"
        builder.row(InlineKeyboardButton(text=label, callback_data=AdminApptCallback(appointment_id=appt.id, scope=scope).pack()))
    builder.row(
        InlineKeyboardButton(
            text="↩️ К календарю",
            callback_data=AdminCalendarMonthCallback(year=target_date.year, month=target_date.month).pack(),
        )
    )
    builder.row(admin_back_button())
    return builder.as_markup()


def admin_calendar_keyboard(
    year: int, month: int, day_off_map: dict[date, bool], appointment_counts: dict[date, int]
) -> InlineKeyboardMarkup:
    """Календарь для админки: в отличие от клиентского, прошлые месяцы и дни доступны
    (мастеру может понадобиться посмотреть историю), а на кнопках — значок 🌙 для
    выходных и число записей, если они есть в этот день."""
    builder = InlineKeyboardBuilder()

    noop = NoopCallback().pack()
    builder.row(*(InlineKeyboardButton(text=WEEKDAY_SHORT[i], callback_data=noop) for i in range(7)))

    first_weekday, days_in_month = monthrange(year, month)
    cells: list[InlineKeyboardButton] = [InlineKeyboardButton(text=" ", callback_data=noop) for _ in range(first_weekday)]

    for day_num in range(1, days_in_month + 1):
        current = date(year, month, day_num)
        label = str(day_num)
        if day_off_map.get(current):
            label += "🌙"
        count = appointment_counts.get(current, 0)
        if count:
            label += f"·{count}"
        cells.append(
            InlineKeyboardButton(
                text=label, callback_data=AdminDayAppointmentsCallback(year=year, month=month, day=day_num).pack()
            )
        )

    while len(cells) % 7 != 0:
        cells.append(InlineKeyboardButton(text=" ", callback_data=noop))
    for i in range(0, len(cells), 7):
        builder.row(*cells[i : i + 7])

    prev_year, prev_month = (year - 1, 12) if month == 1 else (year, month - 1)
    next_year, next_month = (year + 1, 1) if month == 12 else (year, month + 1)
    builder.row(
        InlineKeyboardButton(text="◀️", callback_data=AdminCalendarMonthCallback(year=prev_year, month=prev_month).pack()),
        InlineKeyboardButton(text="▶️", callback_data=AdminCalendarMonthCallback(year=next_year, month=next_month).pack()),
    )
    builder.row(InlineKeyboardButton(text="↩️ Назад", callback_data=AdminMenuCallback(action="appts").pack()))
    builder.row(admin_back_button())
    return builder.as_markup()


def admin_services_list_keyboard(services: list[Service]) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for service in services:
        status = "" if service.is_active else " (откл.)"
        builder.row(
            InlineKeyboardButton(
                text=f"{service.name} — {format_price(service.price)}{status}",
                callback_data=AdminServiceCallback(service_id=service.id).pack(),
            )
        )
    builder.row(InlineKeyboardButton(text="➕ Добавить услугу", callback_data=AdminMenuCallback(action="service_add").pack()))
    builder.row(admin_back_button())
    return builder.as_markup()


def admin_service_detail_keyboard(service: Service) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text="✏️ Название", callback_data=AdminServiceEditCallback(service_id=service.id, field="name").pack()))
    builder.row(
        InlineKeyboardButton(text="✏️ Описание", callback_data=AdminServiceEditCallback(service_id=service.id, field="description").pack())
    )
    builder.row(InlineKeyboardButton(text="💰 Цена", callback_data=AdminServiceEditCallback(service_id=service.id, field="price").pack()))
    builder.row(
        InlineKeyboardButton(text="⏱ Длительность", callback_data=AdminServiceEditCallback(service_id=service.id, field="duration").pack())
    )
    toggle_text = "🚫 Отключить" if service.is_active else "✅ Включить"
    builder.row(InlineKeyboardButton(text=toggle_text, callback_data=AdminServiceEditCallback(service_id=service.id, field="toggle").pack()))
    builder.row(InlineKeyboardButton(text="🗑 Удалить", callback_data=AdminServiceEditCallback(service_id=service.id, field="delete").pack()))
    builder.row(InlineKeyboardButton(text="↩️ К списку услуг", callback_data=AdminMenuCallback(action="services").pack()))
    builder.row(admin_back_button())
    return builder.as_markup()


def admin_service_delete_confirm_keyboard(service_id: int) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(
            text="✅ Да, удалить", callback_data=AdminServiceEditCallback(service_id=service_id, field="delete_confirm").pack()
        ),
        InlineKeyboardButton(text="↩️ Отмена", callback_data=AdminServiceCallback(service_id=service_id).pack()),
    )
    return builder.as_markup()


def admin_portfolio_menu_keyboard(counts: dict[PortfolioCategory, int]) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for category in PortfolioCategory:
        title = CATEGORY_TITLES[category]
        builder.row(
            InlineKeyboardButton(
                text=f"{title} ({counts.get(category, 0)})",
                callback_data=AdminPortfolioCatCallback(category=category.value).pack(),
            )
        )
    builder.row(admin_back_button())
    return builder.as_markup()


def admin_portfolio_category_keyboard(category: PortfolioCategory, items: list[PortfolioItem]) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for i, item in enumerate(items, start=1):
        builder.row(
            InlineKeyboardButton(
                text=f"🗑 Удалить фото №{i}",
                callback_data=AdminPortfolioDeleteCallback(item_id=item.id, category=category.value).pack(),
            )
        )
    builder.row(
        InlineKeyboardButton(text="➕ Добавить фото", callback_data=AdminPortfolioAddCallback(category=category.value).pack())
    )
    builder.row(InlineKeyboardButton(text="↩️ К категориям", callback_data=AdminMenuCallback(action="portfolio").pack()))
    builder.row(admin_back_button())
    return builder.as_markup()


def admin_cancel_input_keyboard() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text="❌ Отменить ввод", callback_data=AdminMenuCallback(action="services").pack()))
    return builder.as_markup()


def admin_simple_back_keyboard() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.row(admin_back_button())
    return builder.as_markup()


def admin_portfolio_cancel_keyboard() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text="❌ Отменить", callback_data=AdminMenuCallback(action="portfolio").pack()))
    return builder.as_markup()


def admin_skip_caption_keyboard() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text="Пропустить подпись", callback_data=AdminMenuCallback(action="portfolio_skip_caption").pack()))
    return builder.as_markup()


# --- Расписание: недельный график и разовые особые дни ---


def admin_schedule_hub_keyboard() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text="✏️ Изменить график", callback_data=AdminMenuCallback(action="schedule_edit").pack()))
    builder.row(InlineKeyboardButton(text="📅 Особые дни", callback_data=AdminMenuCallback(action="exceptions").pack()))
    builder.row(admin_back_button())
    return builder.as_markup()


def admin_schedule_weekday_list_keyboard(week: list[WorkingSchedule]) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    by_weekday = {w.weekday: w for w in week}
    for weekday in range(7):
        ws = by_weekday.get(weekday)
        suffix = " (выходной)" if ws is None or ws.is_day_off else f" ({ws.start_time.strftime('%H:%M')}–{ws.end_time.strftime('%H:%M')})"
        builder.row(
            InlineKeyboardButton(
                text=f"{WEEKDAY_NAMES[weekday]}{suffix}", callback_data=AdminScheduleWeekdayCallback(weekday=weekday).pack()
            )
        )
    builder.row(InlineKeyboardButton(text="↩️ К расписанию", callback_data=AdminMenuCallback(action="schedule").pack()))
    builder.row(admin_back_button())
    return builder.as_markup()


def admin_schedule_weekday_detail_keyboard(ws: WorkingSchedule) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    if ws.is_day_off:
        builder.row(
            InlineKeyboardButton(text="🔄 Сделать рабочим", callback_data=AdminScheduleActionCallback(weekday=ws.weekday, action="toggle").pack())
        )
    else:
        builder.row(
            InlineKeyboardButton(text="🔄 Сделать выходным", callback_data=AdminScheduleActionCallback(weekday=ws.weekday, action="toggle").pack())
        )
        builder.row(
            InlineKeyboardButton(text="⏰ Изменить часы", callback_data=AdminScheduleActionCallback(weekday=ws.weekday, action="edit_hours").pack())
        )
        builder.row(
            InlineKeyboardButton(text="☕ Изменить перерыв", callback_data=AdminScheduleActionCallback(weekday=ws.weekday, action="edit_break").pack())
        )
        if ws.break_start and ws.break_end:
            builder.row(
                InlineKeyboardButton(
                    text="🚫 Убрать перерыв", callback_data=AdminScheduleActionCallback(weekday=ws.weekday, action="remove_break").pack()
                )
            )
    builder.row(InlineKeyboardButton(text="↩️ К списку дней", callback_data=AdminMenuCallback(action="schedule_edit").pack()))
    builder.row(admin_back_button())
    return builder.as_markup()


def admin_schedule_cancel_keyboard(weekday: int) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text="❌ Отменить ввод", callback_data=AdminScheduleWeekdayCallback(weekday=weekday).pack()))
    return builder.as_markup()


def admin_schedule_conflict_keyboard() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text="✅ Сохранить всё равно", callback_data=AdminMenuCallback(action="schedule_apply_pending").pack()))
    builder.row(InlineKeyboardButton(text="↩️ Отмена", callback_data=AdminMenuCallback(action="schedule_cancel_pending").pack()))
    return builder.as_markup()


def admin_exceptions_list_keyboard(exceptions: list[ScheduleException]) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for exc in exceptions:
        if exc.is_day_off:
            suffix = "выходной"
        else:
            suffix = f"{exc.start_time.strftime('%H:%M')}–{exc.end_time.strftime('%H:%M')}"
        builder.row(
            InlineKeyboardButton(
                text=f"🗑 {format_date_ru(exc.date)} — {suffix}",
                callback_data=AdminExceptionDeleteCallback(exception_id=exc.id).pack(),
            )
        )
    builder.row(InlineKeyboardButton(text="➕ Добавить особый день", callback_data=AdminMenuCallback(action="exception_add").pack()))
    builder.row(InlineKeyboardButton(text="↩️ К расписанию", callback_data=AdminMenuCallback(action="schedule").pack()))
    builder.row(admin_back_button())
    return builder.as_markup()


def admin_exception_cancel_keyboard() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text="❌ Отменить", callback_data=AdminMenuCallback(action="exceptions").pack()))
    return builder.as_markup()


def admin_exception_kind_keyboard() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text="📴 Сделать выходным", callback_data=AdminExceptionKindCallback(kind="day_off").pack()))
    builder.row(InlineKeyboardButton(text="🕐 Свои часы работы", callback_data=AdminExceptionKindCallback(kind="custom").pack()))
    builder.row(InlineKeyboardButton(text="❌ Отменить", callback_data=AdminMenuCallback(action="exceptions").pack()))
    return builder.as_markup()


# --- Данные о мастере (BusinessProfile) ---


def admin_profile_keyboard(profile: BusinessProfile | None) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text="✏️ Имя мастера", callback_data=AdminProfileEditCallback(field="master_name").pack()))
    builder.row(InlineKeyboardButton(text="✏️ Город", callback_data=AdminProfileEditCallback(field="city").pack()))
    builder.row(InlineKeyboardButton(text="✏️ Адрес", callback_data=AdminProfileEditCallback(field="address").pack()))
    builder.row(InlineKeyboardButton(text="✏️ Текст «О мастере»", callback_data=AdminProfileEditCallback(field="about_text").pack()))
    builder.row(InlineKeyboardButton(text="✏️ Ссылка на карту", callback_data=AdminProfileEditCallback(field="map_url").pack()))
    builder.row(admin_back_button())
    return builder.as_markup()


def admin_profile_cancel_keyboard() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text="❌ Отменить ввод", callback_data=AdminMenuCallback(action="profile").pack()))
    return builder.as_markup()
