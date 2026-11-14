from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class Instrument(Base):
    __tablename__ = "instruments"

    __table_args__ = (
        CheckConstraint(
            "asset_type IN ('stock', 'etf')",
            name="ck_instruments_asset_type",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)

    symbol: Mapped[str] = mapped_column(
        String(20),
        unique=True,
        index=True,
    )

    name: Mapped[str] = mapped_column(String(200))

    asset_type: Mapped[str] = mapped_column(String(12))

    currency: Mapped[str] = mapped_column(
        String(3),
        default="USD",
    )

    is_active: Mapped[bool] = mapped_column(default=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
    )
