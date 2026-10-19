from aiogram import F, Router
from aiogram.filters import CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message, ReplyKeyboardRemove
from sqlalchemy.ext.asyncio import AsyncSession

from app.callbacks import MenuCallback
from app.filters import is_admin
from app.handlers.render import show_text
from app.keyboards.client import SKIP_PHONE_TEXT, main_menu_keyboard, phone_request_keyboard
from app.repositories.user_repo import UserRepository

router = Router(name="client_start")

GREETING = (
    "Привет!\n\n"
    "Я демо-бот Recomo.\n\n"
    "Здесь вы можете посмотреть услуги, портфолио и самостоятельно записаться на процедуру.\n\n"
    "Выберите действие:"
)

PHONE_REQUEST_TEXT = (
    "📱 Поделитесь номером телефона — мастер сможет позвонить вам, если вы не ответите в "
    "Telegram перед визитом.\n\n"
    "Это необязательно, можно пропустить."
)


@router.message(CommandStart())
async def cmd_start(message: Message, session: AsyncSession, state: FSMContext) -> None:
    await state.clear()
    user_repo = UserRepository(session)
    user = await user_repo.get_or_create(
        telegram_id=message.from_user.id,
        username=message.from_user.username,
        full_name=message.from_user.full_name,
    )
    await session.commit()

    if user.phone is None and not user.phone_skipped:
        await message.answer(PHONE_REQUEST_TEXT, reply_markup=phone_request_keyboard())
        return

    await message.answer(GREETING, reply_markup=main_menu_keyboard(is_admin(message.from_user.id)))


@router.message(F.contact)
async def on_phone_shared(message: Message, session: AsyncSession) -> None:
    user_repo = UserRepository(session)
    user = await user_repo.get_by_telegram_id(message.from_user.id)
    if user is None:
        return
    await user_repo.set_phone(user, message.contact.phone_number)
    await session.commit()
    await message.answer("Спасибо! Номер сохранён.", reply_markup=ReplyKeyboardRemove())
    await message.answer(GREETING, reply_markup=main_menu_keyboard(is_admin(message.from_user.id)))


@router.message(F.text == SKIP_PHONE_TEXT)
async def on_phone_skipped(message: Message, session: AsyncSession) -> None:
    user_repo = UserRepository(session)
    user = await user_repo.get_by_telegram_id(message.from_user.id)
    if user is not None:
        await user_repo.mark_phone_skipped(user)
        await session.commit()
    await message.answer("Хорошо, пропускаем.", reply_markup=ReplyKeyboardRemove())
    await message.answer(GREETING, reply_markup=main_menu_keyboard(is_admin(message.from_user.id)))


@router.callback_query(MenuCallback.filter(F.action == "main"))
async def cb_main_menu(callback: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    await show_text(callback, GREETING, main_menu_keyboard(is_admin(callback.from_user.id)))
