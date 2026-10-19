import asyncio
import logging

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import ErrorEvent

from app.config import settings
from app.handlers.admin import admin_router
from app.handlers.client import client_router
from app.middlewares.db import DbSessionMiddleware
from app.scheduler.jobs import setup_scheduler

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger(__name__)


async def on_error(event: ErrorEvent) -> None:
    """Страховка от 'молчаливых' падений: без этого необработанное исключение внутри
    хендлера просто логируется aiogram, а пользователь не видит вообще ничего —
    ни ответа, ни ошибки (ровно так проявлялся баг с конфликтом расписания)."""
    logger.exception("Необработанная ошибка при обработке апдейта", exc_info=event.exception)
    update = event.update
    try:
        if update.callback_query is not None:
            await update.callback_query.answer("Что-то пошло не так. Попробуйте ещё раз или вернитесь в главное меню.", show_alert=True)
        elif update.message is not None:
            await update.message.answer("Что-то пошло не так. Попробуйте ещё раз или отправьте /start.")
    except Exception:
        pass  # даже уведомление об ошибке не должно уронить бота


async def main() -> None:
    bot = Bot(token=settings.bot_token, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
    dispatcher = Dispatcher(storage=MemoryStorage())

    dispatcher.update.middleware(DbSessionMiddleware())
    dispatcher.error.register(on_error)
    dispatcher.include_router(client_router)
    dispatcher.include_router(admin_router)

    scheduler = setup_scheduler(bot)
    scheduler.start()
    logger.info("Планировщик напоминаний запущен")

    try:
        await bot.delete_webhook(drop_pending_updates=True)
        logger.info("Бот Molly Lash запущен")
        await dispatcher.start_polling(bot)
    finally:
        scheduler.shutdown(wait=False)
        await bot.session.close()


if __name__ == "__main__":
    asyncio.run(main())
