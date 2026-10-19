from aiogram import Router

from app.handlers.admin import appointments, panel, portfolio, profile, reminders, schedule, services

admin_router = Router(name="admin")
admin_router.include_router(panel.router)
admin_router.include_router(appointments.router)
admin_router.include_router(services.router)
admin_router.include_router(portfolio.router)
admin_router.include_router(schedule.router)
admin_router.include_router(profile.router)
admin_router.include_router(reminders.router)
