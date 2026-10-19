from sqlalchemy.ext.asyncio import AsyncSession

from app.models import BusinessProfile

PROFILE_ID = 1


class BusinessRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def get(self) -> BusinessProfile | None:
        return await self.session.get(BusinessProfile, PROFILE_ID)

    async def get_or_create(self) -> BusinessProfile:
        profile = await self.get()
        if profile is not None:
            return profile
        profile = BusinessProfile(
            id=PROFILE_ID, master_name="", city="", address="", about_text="", map_url=""
        )
        self.session.add(profile)
        await self.session.flush()
        return profile
