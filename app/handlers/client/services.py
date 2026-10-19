from aiogram import F, Router
from aiogram.types import CallbackQuery
from sqlalchemy.ext.asyncio import AsyncSession

from app.callbacks import MenuCallback, ServiceViewCallback
from app.handlers.render import show_text
from app.keyboards.client import service_card_keyboard, services_list_keyboard
from app.repositories.service_repo import ServiceRepository
from app.utils.formatting import format_duration, format_price

router = Router(name="client_services")


@router.callback_query(MenuCallback.filter(F.action == "services"))
async def cb_services_list(callback: CallbackQuery, session: AsyncSession) -> None:
    services = await ServiceRepository(session).list_active()
    text = "💫 Услуги и запись\n\nВыберите услугу, чтобы посмотреть подробности и записаться:"
    await show_text(callback, text, services_list_keyboard(services))


@router.callback_query(ServiceViewCallback.filter())
async def cb_service_view(callback: CallbackQuery, callback_data: ServiceViewCallback, session: AsyncSession) -> None:
    service = await ServiceRepository(session).get(callback_data.service_id)
    if service is None or not service.is_active:
        await callback.answer("Эта услуга больше недоступна.", show_alert=True)
        return

    description = service.description or "Описание уточняйте у мастера."
    text = (
        f"{service.name}\n\n"
        f"{description}\n\n"
        f"Цена: {format_price(service.price)}\n"
        f"Длительность: {format_duration(service.duration_minutes)}"
    )
    await show_text(callback, text, service_card_keyboard(service.id))
