from aiogram.fsm.state import State, StatesGroup


class AdminServiceCreate(StatesGroup):
    entering_name = State()
    entering_description = State()
    entering_price = State()
    entering_duration = State()


class AdminServiceEdit(StatesGroup):
    entering_value = State()  # какое поле редактируем — в data["field"]


class AdminPortfolioAdd(StatesGroup):
    waiting_photo = State()
    waiting_caption = State()


class AdminScheduleTimeInput(StatesGroup):
    """Ввод времени начала/конца для рабочих часов или перерыва конкретного дня недели."""

    entering_start = State()
    entering_end = State()


class AdminExceptionCreate(StatesGroup):
    entering_date = State()
    choosing_kind = State()
    entering_start = State()
    entering_end = State()


class AdminProfileEdit(StatesGroup):
    entering_value = State()  # какое поле редактируем — в data["field"]
