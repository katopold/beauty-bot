import enum
from datetime import datetime

from sqlalchemy import Boolean, DateTime, Enum, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class PortfolioCategory(str, enum.Enum):
    CLASSIC = "classic"
    VOLUME_2D = "2d"
    VOLUME_3D = "3d"
    LAMINATION = "lamination"


CATEGORY_TITLES: dict[PortfolioCategory, str] = {
    PortfolioCategory.CLASSIC: "Классика",
    PortfolioCategory.VOLUME_2D: "2D",
    PortfolioCategory.VOLUME_3D: "3D",
    PortfolioCategory.LAMINATION: "Ламинирование",
}


class PortfolioItem(Base):
    __tablename__ = "portfolio_items"

    id: Mapped[int] = mapped_column(primary_key=True)
    category: Mapped[PortfolioCategory] = mapped_column(Enum(PortfolioCategory, name="portfolio_category"))
    file_id: Mapped[str] = mapped_column(String(255))
    caption: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
