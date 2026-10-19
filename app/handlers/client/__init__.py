from aiogram import Router

from app.handlers.client import about, address, booking, my_appointment, portfolio, services, start

client_router = Router(name="client")
client_router.include_router(start.router)
client_router.include_router(services.router)
client_router.include_router(portfolio.router)
client_router.include_router(booking.router)
client_router.include_router(my_appointment.router)
client_router.include_router(address.router)
client_router.include_router(about.router)
