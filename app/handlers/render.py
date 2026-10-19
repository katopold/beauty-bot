from aiogram.exceptions import TelegramBadRequest
from aiogram.types import CallbackQuery, InlineKeyboardMarkup


async def show_text(
    callback: CallbackQuery, text: str, keyboard: InlineKeyboardMarkup, answer: bool = True, force_new: bool = False
) -> None:
    """Показывает текстовое сообщение вместо текущего.

    Редактирует текущее сообщение, если оно тоже текстовое; если текущее сообщение
    содержит медиа (например, фото из портфолио), редактирование текста невозможно —
    старое сообщение удаляется и отправляется новое.

    `force_new=True` всегда удаляет старое и отправляет новое, даже если editing было бы
    возможно — нужно, когда перед этим сообщением в чат только что отправили что-то ещё
    (например, альбом с фото), и редактирование "в старом месте" сломало бы порядок
    сообщений (старый текст оказался бы выше свежего альбома).
    """
    if not force_new:
        try:
            await callback.message.edit_text(text, reply_markup=keyboard)
            if answer:
                try:
                    await callback.answer()
                except TelegramBadRequest:
                    pass
            return
        except TelegramBadRequest:
            pass

    try:
        await callback.message.delete()
    except TelegramBadRequest:
        pass
    await callback.message.answer(text, reply_markup=keyboard)
    if answer:
        try:
            await callback.answer()
        except TelegramBadRequest:
            pass
