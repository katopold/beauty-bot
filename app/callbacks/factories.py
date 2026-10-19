from aiogram.filters.callback_data import CallbackData


class MenuCallback(CallbackData, prefix="menu"):
    action: str  # services, portfolio, address, about, my_appt, admin, main


class ServiceViewCallback(CallbackData, prefix="svc"):
    service_id: int


class ServiceSelectCallback(CallbackData, prefix="svcsel"):
    service_id: int  # выбрать услугу и перейти к выбору даты


class CalendarDateCallback(CallbackData, prefix="caldate"):
    year: int
    month: int
    day: int


class CalendarMonthCallback(CallbackData, prefix="calmon"):
    offset: int  # 0 = текущий месяц, 1 = следующий


class NoopCallback(CallbackData, prefix="noop"):
    """Некликабельные ячейки календаря (пустые клетки, заголовок дней недели)."""


class TimeSelectCallback(CallbackData, prefix="time"):
    hhmm: str  # "1500" (без двоеточия — оно зарезервировано как разделитель callback_data)


class ConfirmCallback(CallbackData, prefix="conf"):
    action: str  # confirm, back, cancel


class BackCallback(CallbackData, prefix="back"):
    to: str  # куда вернуться: date, my_appt


class PortfolioCategoryCallback(CallbackData, prefix="pfcat"):
    category: str
    index: int = 0


class MyApptActionCallback(CallbackData, prefix="myappt"):
    action: str  # cancel, cancel_confirm, cancel_abort, reschedule


# --- Админка ---


class AdminMenuCallback(CallbackData, prefix="adm"):
    action: str  # appts, schedule, services, portfolio, clients, test_reminder, main


class AdminApptListCallback(CallbackData, prefix="admal"):
    scope: str  # today, tomorrow, upcoming


class AdminApptCallback(CallbackData, prefix="admap"):
    appointment_id: int
    scope: str = "today"


class AdminApptCancelCallback(CallbackData, prefix="admapc"):
    appointment_id: int
    scope: str
    action: str  # ask, confirm


class AdminServiceListCallback(CallbackData, prefix="admsl"):
    pass


class AdminServiceCallback(CallbackData, prefix="adms"):
    service_id: int


class AdminServiceEditCallback(CallbackData, prefix="admse"):
    service_id: int
    field: str  # name, description, price, duration, toggle, delete, delete_confirm


class AdminPortfolioCatCallback(CallbackData, prefix="admpc"):
    category: str


class AdminPortfolioAddCallback(CallbackData, prefix="admpa"):
    category: str


class AdminPortfolioDeleteCallback(CallbackData, prefix="admpd"):
    item_id: int
    category: str


class AdminScheduleWeekdayCallback(CallbackData, prefix="admsw"):
    weekday: int


class AdminScheduleActionCallback(CallbackData, prefix="admsa"):
    weekday: int
    action: str  # toggle, edit_hours, edit_break, remove_break


class AdminExceptionDeleteCallback(CallbackData, prefix="admexd"):
    exception_id: int


class AdminExceptionKindCallback(CallbackData, prefix="admexk"):
    kind: str  # day_off, custom


class AdminProfileEditCallback(CallbackData, prefix="admpr"):
    field: str  # master_name, city, address, about_text, map_url


class AdminCalendarMonthCallback(CallbackData, prefix="admcalm"):
    year: int
    month: int


class AdminDayAppointmentsCallback(CallbackData, prefix="admday"):
    year: int
    month: int
    day: int
