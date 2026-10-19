from sqlalchemy import String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class BusinessProfile(Base):
    """Единственная строка с информацией о мастере/салоне (singleton, id=1)."""

    __tablename__ = "business_profile"

    id: Mapped[int] = mapped_column(primary_key=True)
    master_name: Mapped[str] = mapped_column(String(255))
    city: Mapped[str] = mapped_column(String(255))
    address: Mapped[str] = mapped_column(String(255))
    about_text: Mapped[str] = mapped_column(Text)
    map_url: Mapped[str] = mapped_column(String(512))
