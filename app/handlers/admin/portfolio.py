from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
from sqlalchemy.ext.asyncio import AsyncSession

from app.callbacks import AdminMenuCallback, AdminPortfolioAddCallback, AdminPortfolioCatCallback, AdminPortfolioDeleteCallback
from app.filters import IsAdmin
from app.handlers.render import show_text
from app.keyboards.admin import (
    admin_portfolio_cancel_keyboard,
    admin_portfolio_category_keyboard,
    admin_portfolio_menu_keyboard,
    admin_skip_caption_keyboard,
)
from app.models import CATEGORY_TITLES, PortfolioCategory
from app.repositories.portfolio_repo import PortfolioRepository
from app.states.admin import AdminPortfolioAdd

router = Router(name="admin_portfolio")


async def _render_category(target, session: AsyncSession, category: PortfolioCategory) -> None:
    items = await PortfolioRepository(session).list_by_category(category)
    title = CATEGORY_TITLES[category]
    text = f"📸 {title}\n\nФото в этой категории: {len(items)}"
    keyboard = admin_portfolio_category_keyboard(category, items)
    if isinstance(target, CallbackQuery):
        await show_text(target, text, keyboard)
    else:
        await target.answer(text, reply_markup=keyboard)


@router.callback_query(AdminMenuCallback.filter(F.action == "portfolio"), IsAdmin())
async def cb_admin_portfolio_menu(callback: CallbackQuery, state: FSMContext, session: AsyncSession) -> None:
    await state.clear()
    counts = await PortfolioRepository(session).count_by_category()
    await show_text(callback, "📸 Портфолио\n\nВыберите категорию:", admin_portfolio_menu_keyboard(counts))


@router.callback_query(AdminPortfolioCatCallback.filter(), IsAdmin())
async def cb_admin_portfolio_category(callback: CallbackQuery, callback_data: AdminPortfolioCatCallback, session: AsyncSession) -> None:
    category = PortfolioCategory(callback_data.category)
    await _render_category(callback, session, category)


@router.callback_query(AdminPortfolioAddCallback.filter(), IsAdmin())
async def cb_admin_portfolio_add_start(callback: CallbackQuery, callback_data: AdminPortfolioAddCallback, state: FSMContext) -> None:
    category = PortfolioCategory(callback_data.category)
    await state.set_state(AdminPortfolioAdd.waiting_photo)
    await state.update_data(category=category.value)
    title = CATEGORY_TITLES[category]
    text = f"📸 Добавление фото — {title}\n\nОтправьте фотографию:"
    await show_text(callback, text, admin_portfolio_cancel_keyboard())


@router.message(AdminPortfolioAdd.waiting_photo, F.photo, IsAdmin())
async def admin_portfolio_photo_received(message: Message, state: FSMContext) -> None:
    file_id = message.photo[-1].file_id
    await state.update_data(file_id=file_id)
    await state.set_state(AdminPortfolioAdd.waiting_caption)
    await message.answer("Добавьте подпись к фото или нажмите «Пропустить»:", reply_markup=admin_skip_caption_keyboard())


@router.message(AdminPortfolioAdd.waiting_photo, IsAdmin())
async def admin_portfolio_photo_missing(message: Message) -> None:
    await message.answer("Пожалуйста, отправьте именно фотографию.")


async def _save_portfolio_item(session: AsyncSession, state: FSMContext, caption: str | None) -> PortfolioCategory:
    data = await state.get_data()
    category = PortfolioCategory(data["category"])
    await PortfolioRepository(session).add(category=category, file_id=data["file_id"], caption=caption)
    await session.commit()
    await state.clear()
    return category


@router.message(AdminPortfolioAdd.waiting_caption, IsAdmin())
async def admin_portfolio_caption_received(message: Message, state: FSMContext, session: AsyncSession) -> None:
    caption = message.text.strip() if message.text else None
    category = await _save_portfolio_item(session, state, caption or None)
    await message.answer(f"✅ Фото добавлено в категорию «{CATEGORY_TITLES[category]}».")
    await _render_category(message, session, category)


@router.callback_query(AdminMenuCallback.filter(F.action == "portfolio_skip_caption"), AdminPortfolioAdd.waiting_caption, IsAdmin())
async def cb_admin_portfolio_skip_caption(callback: CallbackQuery, state: FSMContext, session: AsyncSession) -> None:
    category = await _save_portfolio_item(session, state, None)
    await callback.answer("Фото добавлено.")
    await _render_category(callback, session, category)


@router.callback_query(AdminPortfolioDeleteCallback.filter(), IsAdmin())
async def cb_admin_portfolio_delete(callback: CallbackQuery, callback_data: AdminPortfolioDeleteCallback, session: AsyncSession) -> None:
    repo = PortfolioRepository(session)
    item = await repo.get(callback_data.item_id)
    if item is not None:
        await repo.delete(item)
        await session.commit()
    category = PortfolioCategory(callback_data.category)
    await callback.answer("Фото удалено.")
    await _render_category(callback, session, category)
