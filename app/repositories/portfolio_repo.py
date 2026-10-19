from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import PortfolioCategory, PortfolioItem


class PortfolioRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def list_by_category(self, category: PortfolioCategory, limit: int | None = None) -> list[PortfolioItem]:
        stmt = (
            select(PortfolioItem)
            .where(PortfolioItem.category == category, PortfolioItem.is_active.is_(True))
            .order_by(PortfolioItem.created_at.desc())
        )
        if limit is not None:
            stmt = stmt.limit(limit)
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def get(self, item_id: int) -> PortfolioItem | None:
        return await self.session.get(PortfolioItem, item_id)

    async def add(self, category: PortfolioCategory, file_id: str, caption: str | None) -> PortfolioItem:
        item = PortfolioItem(category=category, file_id=file_id, caption=caption)
        self.session.add(item)
        await self.session.flush()
        return item

    async def delete(self, item: PortfolioItem) -> None:
        await self.session.delete(item)
        await self.session.flush()

    async def count_by_category(self) -> dict[PortfolioCategory, int]:
        items = await self.session.execute(select(PortfolioItem).where(PortfolioItem.is_active.is_(True)))
        counts: dict[PortfolioCategory, int] = {cat: 0 for cat in PortfolioCategory}
        for item in items.scalars().all():
            counts[item.category] += 1
        return counts
