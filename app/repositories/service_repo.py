from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Service


class ServiceRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def list_active(self) -> list[Service]:
        result = await self.session.execute(
            select(Service).where(Service.is_active.is_(True)).order_by(Service.sort_order, Service.id)
        )
        return list(result.scalars().all())

    async def list_all(self) -> list[Service]:
        result = await self.session.execute(select(Service).order_by(Service.sort_order, Service.id))
        return list(result.scalars().all())

    async def get(self, service_id: int) -> Service | None:
        return await self.session.get(Service, service_id)

    async def create(self, name: str, description: str, price: int, duration_minutes: int) -> Service:
        service = Service(name=name, description=description, price=price, duration_minutes=duration_minutes)
        self.session.add(service)
        await self.session.flush()
        return service

    async def delete(self, service: Service) -> None:
        await self.session.delete(service)
        await self.session.flush()
