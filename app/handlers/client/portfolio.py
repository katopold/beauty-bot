from aiogram import F, Router
from aiogram.exceptions import TelegramBadRequest
from aiogram.types import CallbackQuery, InlineKeyboardMarkup, InputMediaPhoto
from sqlalchemy.ext.asyncio import AsyncSession

from app.callbacks import MenuCallback, PortfolioCategoryCallback
from app.handlers.render import show_text
from app.keyboards.client import portfolio_categories_keyboard, portfolio_empty_category_keyboard, portfolio_gallery_keyboard
from app.models import CATEGORY_TITLES, PortfolioCategory
from app.repositories.portfolio_repo import PortfolioRepository

router = Router(name="client_portfolio")


async def _show_photo(callback: CallbackQuery, file_id: str, caption: str, keyboard: InlineKeyboardMarkup) -> None:
    """Показывает фото на месте текущего сообщения — без отправки новых. Если текущее
    сообщение уже фото, меняет его "на лету" (editMessageMedia); если текстовое —
    старое удаляется и вместо него отправляется фото (та же логика, что и в show_text,
    но для медиа, а не для текста). Когда пользователь потом уходит с экрана портфолио,
    show_text на следующем шаге точно так же удалит это фото-сообщение — лишних
    сообщений в чате не остаётся."""
    if callback.message.photo:
        try:
            await callback.message.edit_media(InputMediaPhoto(media=file_id, caption=caption), reply_markup=keyboard)
            await callback.answer()
            return
        except TelegramBadRequest:
            pass
    try:
        await callback.message.delete()
    except TelegramBadRequest:
        pass
    await callback.message.answer_photo(file_id, caption=caption, reply_markup=keyboard)
    await callback.answer()


@router.callback_query(MenuCallback.filter(F.action == "portfolio"))
async def cb_portfolio_home(callback: CallbackQuery) -> None:
    text = "📸 Портфолио\n\nВыберите категорию:"
    await show_text(callback, text, portfolio_categories_keyboard())


@router.callback_query(PortfolioCategoryCallback.filter())
async def cb_portfolio_category(callback: CallbackQuery, callback_data: PortfolioCategoryCallback, session: AsyncSession) -> None:
    category = PortfolioCategory(callback_data.category)
    title = CATEGORY_TITLES[category]
    items = await PortfolioRepository(session).list_by_category(category)

    if not items:
        text = f"📸 {title}\n\nПока нет фото в этой категории — скоро добавим!"
        await show_text(callback, text, portfolio_empty_category_keyboard())
        return

    index = max(0, min(callback_data.index, len(items) - 1))
    item = items[index]
    caption = f"📸 {title} ({index + 1}/{len(items)})"
    if item.caption:
        caption += f"\n\n{item.caption}"

    keyboard = portfolio_gallery_keyboard(category, index, len(items))
    await _show_photo(callback, item.file_id, caption, keyboard)
